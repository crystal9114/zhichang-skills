#!/usr/bin/env python3
"""劳动争议赔偿速算。只用 Python 3.9+ 标准库，不联网、不写文件。

  python3 scripts/peichang.py check --leave 2025-09-30 --reason unknown           # 体检：要先问什么、时效、要不要停
  python3 scripts/peichang.py quick --entry 2021-03-15 --leave 2026-09-30 --wage 15000 --reason 违法解除 --city 上海

参数全表见 references/cli.md；离职方式、特殊情形代码见 references/codes.md；错误码见 references/errors.md。
退出码：0 成功；3~9 见 references/errors.md。任何异常都打印「错误码 + 原因 + 怎么办」，不打堆栈。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta
import json

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ldlib import calc, case as casemod, dates, lead, render  # noqa: E402
from ldlib.errors import LdError, fail, report as report_err, unexpected  # noqa: E402

ZH = {"usage: ": "用法：", "positional arguments": "位置参数", "options": "选项",
      "show this help message and exit": "显示这份帮助"}
ARG_ZH = {"the following arguments are required:": "缺少参数：", "unrecognized arguments:": "认不出的参数：",
          "invalid choice:": "取值不对：", "(choose from": "（可选", "expected one argument": "后面要跟一个值",
          "argument ": "参数 "}


class Parser(argparse.ArgumentParser):
    """参数错不甩英文：转成 E08。帮助文字换成中文表头。"""

    def error(self, message: str):  # type: ignore[override]
        for a, b in ARG_ZH.items():
            message = message.replace(a, b)
        raise fail("E08", f"命令参数不对：{message}", "照 references/cli.md 的写法改；先跑 python3 scripts/peichang.py quick -h 看参数", 2)

    def format_help(self) -> str:
        text = super().format_help()
        for a, b in ZH.items():
            text = text.replace(a, b)
        return text


def add_common(p: argparse.ArgumentParser, required: bool) -> None:
    p.add_argument("--entry", help="入职（实际开始上班）日期，如 2021-03-15")
    p.add_argument("--leave", help="离职（被解除、合同终止）日期；quick 不给就按 --apply 那天（标为假设）")
    p.add_argument("--reason", required=required, help="离职方式代码或中文别名，见 references/codes.md；没问清写 unknown")
    p.add_argument("--wage", help="离职前 12 个月平均每月税前应发（含奖金补贴）")
    p.add_argument("--wages12", help="逐月税前应发，逗号隔开，最多 12 个")
    p.add_argument("--parts", help="工资构成：基本工资=8000,绩效=2000,年终奖=24000（名字带「年」的除以 12）")
    p.add_argument("--city", default="", help="劳动合同履行地城市，用来查社平工资和三倍封顶")
    p.add_argument("--avg-wage", default=None, help="当地上年度职工月平均工资（表里没有这个城市时给）")
    p.add_argument("--apply", default=None, help="按哪天判时效（申请仲裁日），默认今天")
    p.add_argument("--contract", default="", choices=["", "签了", "没签", "补签"], help="书面劳动合同：签了 / 没签 / 补签")
    p.add_argument("--notice", default="未知", choices=["有", "没有", "未知"], help="第四十条解除时单位有没有提前 30 天书面通知")
    p.add_argument("--years", default=None, help="只知道干了几年时用（如 4、3.5；「3 年多」写 3多），按离职日往前反推入职日，标为假设")
    p.add_argument("--flags", default="", help="特殊情形，逗号隔开：派遣、工伤、外包、境外、刑事、孕期…… 见 references/codes.md")


def build(args: argparse.Namespace) -> calc.Facts:
    wage, src, wdoubts = casemod.wage_from(args.wage, args.wages12, args.parts)
    if wage is None:
        raise fail("E05", "没给工资", "加 --wage（月平均税前应发）、--wages12（逐月）或 --parts（工资构成）其中一个；不知道就先跑 check 问清", 4)
    apply = dates.parse(args.apply, "--apply") if args.apply else date.today()
    guess: list[str] = []
    years_fuzzy: int | None = None
    leave = dates.parse(args.leave, "--leave") if args.leave else apply
    if not args.leave:
        guess.append(f"没给离职日，按 {leave} 算（假设）；离职日会影响年限和时效，请核对")
    if args.entry:
        entry = dates.parse(args.entry, "--entry")
    elif args.years not in (None, ""):
        raw = str(args.years).strip()
        more = raw.endswith(("多", "+"))           # 「3多」「3+」= 用户说的「3 年多」
        yrs = casemod.num(raw.rstrip("多+").rstrip("年").strip(), "--years")
        if yrs > 60:
            raise fail("E04", f"--years {args.years} 超出合理范围", "写工作了几年，比如 4、3.5，「3 年多」写 3多", 4)
        months = int((yrs * 12).to_integral_value()) + (1 if more else 0)
        entry = dates.add_months(leave, -months) + timedelta(days=1)
        if more or yrs != yrs.to_integral_value():
            years_fuzzy = int(yrs)
        if more:
            guess.append(f"没给入职日，按「干了 {calc.mtext(yrs)} 年多」取 {calc.mtext(yrs)} 年零 1 个月反推为 {entry}（假设）；"
                         "零头满不满 6 个月决定 N 差半个月，请用户给准确入职日")
        else:
            guess.append(f"没给入职日，按「干了整 {calc.mtext(yrs)} 年」反推为 {entry}（假设）；零头差几天就可能差半个月，请用户给准确入职日")
    else:
        raise fail("E05", "没给入职日", "加 --entry 2021-03-15；只知道干了几年就加 --years 4（结果会标为假设）", 4)
    al_prev: dict[int, Decimal] = {}
    for seg in str(args.al_prev or "").replace("，", ",").split(","):
        if seg.strip():
            y, sep, d = seg.partition("=")
            if not sep or not y.strip().isdigit():
                raise fail("E04", f"--al-prev 这一段认不出：{seg}", "写成 2025=5（2025 年没休 5 天）", 4)
            al_prev[int(y)] = casemod.num(d, f"--al-prev {y}", allow_zero=True)
    opt = (lambda v, name, zero=False: casemod.num(v, name, zero) if v not in (None, "") else None)
    return calc.Facts(
        entry=entry, leave=leave, apply=apply, guesses=guess, rough=bool(getattr(args, "rough", False)),
        years_fuzzy=years_fuzzy, entry_guessed=not args.entry, leave_guessed=not args.leave,
        wage=wage, wage_src=src, reason=casemod.reason_code(args.reason) or "unknown", city=args.city,
        avg_wage=opt(args.avg_wage, "--avg-wage"), min_wage=opt(args.min_wage, "--min-wage"),
        last_wage=opt(args.last_wage, "--last-wage"), ot_in=opt(args.ot_in, "--ot-in", True) or Decimal(0),
        notice=args.notice, contract=args.contract,
        signed_date=dates.parse(args.signed_date, "--signed-date") if args.signed_date else None,
        renew_declined=args.renew_declined,
        al_years=opt(args.al_years, "--al-years", True), al_taken=opt(args.al_taken, "--al-taken", True) or Decimal(0),
        al_prev=al_prev, flags=casemod.flag_set(args.flags), wage_doubts=wdoubts)


def parser() -> Parser:
    ap = Parser(prog="peichang.py", description="劳动争议赔偿速算：check 体检、quick 算钱")
    sub = ap.add_subparsers(dest="cmd", parser_class=Parser)
    c = sub.add_parser("check", help="体检：要先问什么、时效、要不要停")
    add_common(c, False)
    q = sub.add_parser("quick", help="按法条逐项算钱（带算式、法条全称和条款号、时效、存疑）")
    add_common(q, True)
    q.add_argument("--min-wage", default=None, help="当地月最低工资标准（经济补偿基数不低于它）")
    q.add_argument("--last-wage", default=None, help="上一个月工资（代通知金用），默认用月平均工资")
    q.add_argument("--ot-in", default=None, help="月工资里平均含多少加班费（年假、二倍工资基数要剔除）")
    q.add_argument("--signed-date", default=None, help="补签书面合同那天（--contract 补签 时必填）")
    q.add_argument("--renew-declined", action="store_true", help="合同到期单位维持或提高条件续签、员工不同意")
    q.add_argument("--al-years", default=None, help="参加工作累计年数（含以前单位），算未休年假用")
    q.add_argument("--al-taken", default=None, help="离职当年已休年假天数")
    q.add_argument("--al-prev", default=None, help="往年没休的年假：2025=5")
    q.add_argument("--rough", action="store_true", help="派遣、外包、境外等不出结论的情形，按普通劳动关系粗算一个参考数（标明前提）")
    q.add_argument("--json", action="store_true", help="输出 JSON")
    c.add_argument("--json", action="store_true", help="输出 JSON")
    return ap


def main(argv: list[str]) -> int:
    try:
        ap = parser()
        args = ap.parse_args(argv)
        if not args.cmd:
            sys.stdout.write(ap.format_help())
            return 0
        if args.cmd == "check":
            apply = dates.parse(args.apply, "--apply") if args.apply else date.today()
            if args.entry:
                dates.parse(args.entry, "--entry")
            has_wage = any(v not in (None, "") for v in (args.wage, args.wages12, args.parts))
            flags = casemod.flag_set(args.flags)
            chk = casemod.check(args.entry, args.leave, args.reason, has_wage, args.city, args.avg_wage,
                                args.contract, flags, apply, args.notice)
            fuzzy = None
            if args.years not in (None, ""):
                raw = str(args.years).strip()
                yrs = casemod.num(raw.rstrip("多+").rstrip("年").strip(), "--years")
                if raw.endswith(("多", "+")) or yrs != yrs.to_integral_value():
                    fuzzy = int(yrs)
            wage_val = casemod.wage_from(args.wage, args.wages12, args.parts)[0] if has_wage else None
            ld = lead.build(flags, years_fuzzy=fuzzy, base=wage_val, reason_known=casemod.reason_code(args.reason) not in (None, "unknown"),
                            )
            chk = {**lead.as_json(ld), **chk} if ld else chk
            sys.stdout.write(json.dumps(chk, ensure_ascii=False, indent=2) + "\n" if args.json else render.check_text(chk))
            return 0
        res = calc.compute(build(args))
        sys.stdout.write(json.dumps(render.quick_json(res), ensure_ascii=False, indent=2) + "\n" if args.json
                         else render.quick_text(res))
        return 0
    except LdError as e:
        return report_err(e)
    except SystemExit as e:          # -h 正常退出
        return int(e.code or 0) if isinstance(e.code, int) else 0
    except KeyboardInterrupt:
        return report_err(fail("E98", "被中断了", "重新跑一次", 9))
    except Exception as e:  # noqa: BLE001  最外层兜底，不甩堆栈
        return unexpected(e)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
