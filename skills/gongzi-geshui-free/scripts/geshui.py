#!/usr/bin/env python3
"""工资个税速算（居民个人工资薪金 + 全年一次性奖金），只用 Python 标准库。

  python3 scripts/geshui.py quick --income 15000 --si 1575 --hf 1050 --special 2000 --bonus 30000
      单人按月算全年逐月个税和到手（累计预扣法），带年终奖两种算法比对和临界点提醒
  python3 scripts/geshui.py quick --income 20000 --base 20000 --si-rate 10.5 --hf-rate 7
      不知道社保扣多少时，给缴费基数和个人比例，由脚本算
  python3 scripts/geshui.py bonus --bonus 37000
      只给年终奖：单独计税的税、到手、是否落在「多发反而少拿」区间
  python3 scripts/geshui.py zones
      列出全部 6 段「多发反而少拿」区间（问「年终奖怎么发最省」又没给金额时）
  python3 scripts/geshui.py scope labor --amount 8000
      超出范围的所得（labor 劳务报酬 / royalty 稿酬 / business 经营所得 --profit [--getihu] /
      foreign 非居民工资 --income / allowance 外籍补贴 / avoid 避税要求）：固定开头 + 基本算式 + 找谁确认
金额可以写 15000、1.5万、1.5w、12k，脚本会换算并在输出里写明。

quick 常用参数（金额都按「每月」写，只写数字）：
  --income 每月应发（税前）       --income-from 7=18000 从 7 月起应发改成 18000（可写多个）
  --income-set 6=30000 只有 6 月应发是 30000（如当月发绩效、补发工资，可写多个）
  --si 三险个人合计               --hf 公积金个人
  --base 缴费基数 --si-rate 三险个人比例%（不写按 10.5） --hf-rate 公积金个人比例%（不写按 0）
  --si-from 7=2300 从 7 月起三险个人改成 2300（社保基数每年调整时用）
  --special 专项附加扣除每月合计   --special-from 5=3000 从 5 月起专项附加改成 3000
  --other 其他扣除（个人养老金、商业健康险等每月可扣额）  --tax-free 每月免税收入
  --start 入职月（年中入职）      --end 算到几月（默认 12）
  --first-job 今年首次就业（减除费用从 1 月起算）
  --sixty-k   上年 1~12 月都在本单位且全年工资≤6 万（1 月起按 6 万减除）
  --bonus 年终奖  --bonus-month 发放月（默认 12）  --bonus-mode separate|merge 预扣时单独计税或并入当月
  --year 纳税年度（默认 2026）
退出码：0 成功；2 参数写法不对；3 数值不合规；4 参数互相矛盾；9 未预料的错误（都打印 E 码 + 原因 + 怎么办）。
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gslib import engine, keypoints, render, scope  # noqa: E402
from gslib.errors import GsError  # noqa: E402
from gslib.rules import money  # noqa: E402

Z = Decimal("0")
DEFAULT_SI_RATE = Decimal("10.5")


class CnParser(argparse.ArgumentParser):
    """参数写错时不甩英文用法，统一成 E01。"""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise GsError("E01", f"参数写法不对：{cn_message(message)}")


ARGPARSE_CN = (
    (r"the following arguments are required: (.*)", r"缺少必填参数 \1"),
    (r"unrecognized arguments: (.*)", r"不认识的参数 \1"),
    (r"argument (\S+): invalid int value: '(.*)'", r"\1 要写整数，收到「\2」"),
    (r"argument (\S+): invalid choice: '(.*)' \(choose from (.*)\)", r"\1 只能是 \3，收到「\2」"),
    (r"argument (\S+): expected one argument", r"\1 后面要跟一个值"),
    (r"argument (\S+): ambiguous option: (.*)", r"参数 \1 写得不完整，可能是 \2"),
)


def cn_message(message: str) -> str:
    """argparse 自带的英文报错换成中文；认不出的原样保留在括号里。"""
    import re  # noqa: PLC0415
    for pat, rep in ARGPARSE_CN:
        if re.fullmatch(pat, message):
            return re.sub(pat, rep, message).replace("cmd", "子命令 quick 或 bonus")
    return f"（{message}）"


UNITS = (("万元", 10000), ("万", 10000), ("w", 10000), ("W", 10000), ("千元", 1000), ("千", 1000), ("k", 1000),
         ("K", 1000), ("元", 1))
CONVERTED: list[str] = []      # 本次运行里换算过的写法，写进【输入与假设】


def amount(x: str | None, what: str) -> Decimal:
    if x is None or str(x).strip() == "":
        return Z
    raw = str(x).strip()
    s, mult = raw.replace(",", "").replace("，", ""), 1
    for unit, m in UNITS:
        if s.endswith(unit):
            s, mult = s[: -len(unit)].strip(), m
            break
    try:
        d = Decimal(s) * mult
    except InvalidOperation:
        raise GsError("E02", f"{what}要写数字，收到「{x}」") from None
    if not d.is_finite():
        raise GsError("E02", f"{what}要写有限的数字，收到「{x}」")
    if mult != 1:
        CONVERTED.append(f"{raw} → {d.normalize():f}")
    return d


def month_pairs(items: list[str] | None, what: str) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {}
    for it in items or []:
        if "=" not in it:
            raise GsError("E01", f"{what}要写成 月份=金额，如 7=18000，收到「{it}」")
        k, v = it.split("=", 1)
        try:
            mo = int(k.strip())
        except ValueError:
            raise GsError("E03", f"{what}的月份要写整数，收到「{k}」") from None
        engine.check_month(mo, what)
        out[mo] = engine.check_amount(amount(v, what), what)
    return out


def spread(base: Decimal, frm: dict[int, Decimal], months: range) -> dict[int, Decimal]:
    """每月同一个数，从某月起改成新数（--xx-from）。"""
    out, cur = {}, base
    for mo in months:
        cur = frm.get(mo, cur)
        out[mo] = cur
    return out


def build_plan(a: argparse.Namespace) -> engine.Plan:
    start, end = engine.check_month(a.start, "--start 入职月"), engine.check_month(a.end, "--end 截止月")
    if end < start:
        raise GsError("E03", f"截止月 {end} 早于入职月 {start}")
    if a.first_job and a.sixty_k:
        raise GsError("E06", "--first-job（今年首次就业）和 --sixty-k（上年全年在本单位）不可能同时成立")
    if a.sixty_k and start > 1:
        raise GsError("E06", "--sixty-k 要求上年 1~12 月都在本单位领工资，本年应从 1 月算，不能同时写 --start")
    months = range(start, end + 1)
    notes: list[str] = [f"计税月份：{start}~{end}月，共 {end - start + 1} 个月，只算本单位发的工资"]
    if not str(a.income).strip():
        raise GsError("E02", "--income 每月应发是空的", "写每月税前应发金额，如 --income 15000；不知道就先问用户")
    inc = engine.check_amount(amount(a.income, "--income 每月应发"), "--income 每月应发")
    income = spread(inc, month_pairs(a.income_from, "--income-from"), months)
    income.update({m: v for m, v in month_pairs(a.income_set, "--income-set").items() if m in months})
    notes.append(income_note(income))

    si, hf, hfd, exc = si_hf(a, months, income, notes)
    sp = engine.check_amount(amount(a.special, "--special 专项附加扣除"), "--special 专项附加扣除")
    special = spread(sp, month_pairs(a.special_from, "--special-from"), months)
    if max(special.values()) > Decimal("20000"):
        raise GsError("E05", f"专项附加扣除每月 {max(special.values())} 元，远超各项标准之和",
                      "核对是不是把全年数当成了每月数；各项标准见 references/tax-rules.md 第 4 节")
    notes.append("专项附加扣除：" + (vary_note(special) if any(special.values()) else "未填，按 0 算（如有子女、房贷房租、赡养老人等，补上会少交税）"))
    other = {m: engine.check_amount(amount(a.other, "--other 其他扣除"), "--other 其他扣除") for m in months}
    if a.other:
        notes.append(f"其他扣除每月 {render.yuan(other[start])}（个人养老金每年上限 12000，即每月 1000）")
    tax_free = {m: engine.check_amount(amount(a.tax_free, "--tax-free"), "--tax-free") for m in months}
    if a.tax_free:
        notes.append(f"免税收入每月 {render.yuan(tax_free[start])}（含在应发里，不计税）")

    bonus = engine.check_amount(amount(a.bonus, "--bonus 年终奖"), "--bonus 年终奖", engine.MAX_BONUS)
    bm = engine.check_month(a.bonus_month, "--bonus-month 年终奖发放月")
    if bonus and bm not in months:
        raise GsError("E03", f"年终奖发放月 {bm} 不在计税月份 {start}~{end} 里")
    if bonus:
        notes.append(f"年终奖 {render.yuan(bonus)}，{bm} 月发，逐月表按「{'单独计税' if a.bonus_mode == 'separate' else '并入当月工资'}」预扣")
    if a.first_job:
        notes.append("减除费用：今年首次就业，从 1 月起算（入职当月累计减除费用 = 5000 × 当月月份）")
    elif a.sixty_k:
        notes.append("减除费用：适用 6 万元标准，1 月起累计减除费用直接按 60000，累计收入不超过 6 万的月份不预扣")
    else:
        notes.append("减除费用：每月 5000，从" + ("入职月" if start > 1 else "1 月") + "起累计")
    if any(v > income[m] for m, v in si.items()):
        notes.append("注意：有月份三险个人比应发还多，请核对金额")
    if CONVERTED:
        notes.insert(0, "金额写法换算：" + "；".join(dict.fromkeys(CONVERTED)))
    if not bonus:
        notes.append("年终奖：未填。如有年终奖（含 13 薪、年终双薪），加 --bonus 金额，比较单独计税和并入综合所得哪个省")
    return engine.Plan(start, end, income, si, hf, hfd, exc, special, other, tax_free, a.first_job, a.sixty_k,
                       bonus, bm, a.bonus_mode, a.year, tuple(notes))


def si_hf(a: argparse.Namespace, months: range, income: dict[int, Decimal], notes: list[str]):
    if a.base is not None:
        base = engine.check_amount(amount(a.base, "--base 缴费基数"), "--base 缴费基数")
        rate = amount(a.si_rate, "--si-rate") if a.si_rate is not None else DEFAULT_SI_RATE
        hrate = amount(a.hf_rate, "--hf-rate") if a.hf_rate is not None else Z
        if not (Z <= rate <= 30 and Z <= hrate <= 30):
            raise GsError("E05", f"个人比例 社保 {rate}% / 公积金 {hrate}% 不合常理", "比例写百分数里的数字，如 10.5、7")
        si_m = money(base * rate / 100)
        hf_m, hfd_m, exc_m, hf_note = engine.hf_split(base, hrate)
        assumed = "（未给比例，按养老 8% + 医疗 2% + 失业 0.5% = 10.5% 假设）" if a.si_rate is None else ""
        notes.append(f"三险个人：基数 {render.yuan(base)} × {rate}% = {render.yuan(si_m)}/月{assumed}")
        notes.append(f"公积金个人：基数 {render.yuan(base)} × {hrate}% = {render.yuan(hf_m)}/月"
                     + ("（未给比例，按 0 算；有公积金的加 --hf-rate）" if a.hf_rate is None else ""))
        if hf_note:
            notes.append(hf_note)
        si = spread(si_m, month_pairs(a.si_from, "--si-from"), months)
        return si, {m: hf_m for m in months}, {m: hfd_m for m in months}, {m: exc_m for m in months}
    if a.si_rate is not None or a.hf_rate is not None:
        raise GsError("E01", "写了比例（--si-rate/--hf-rate）却没写缴费基数 --base", "加上 --base 基数，或直接用 --si/--hf 写每月金额")
    si_m = engine.check_amount(amount(a.si, "--si 三险个人"), "--si 三险个人")
    hf_m = engine.check_amount(amount(a.hf, "--hf 公积金个人"), "--hf 公积金个人")
    si = spread(si_m, month_pairs(a.si_from, "--si-from"), months)
    if a.si is None and a.hf is None and not a.si_from:
        notes.append("社保公积金：未填，按 0 算——实际到手会比下表少、个税会比下表略多，请补上个人缴纳金额或缴费基数")
    else:
        notes.append(f"三险个人：{vary_note(si)}；公积金个人：每月 {render.yuan(hf_m)}（按你给的金额，未核对比例上限）")
    return si, {m: hf_m for m in months}, {m: hf_m for m in months}, {m: Z for m in months}


def vary_note(d: dict[int, Decimal]) -> str:
    ms = sorted(d)
    segs, s = [], ms[0]
    for i, m in enumerate(ms):
        if i + 1 == len(ms) or d[ms[i + 1]] != d[m]:
            segs.append(f"{s}~{m}月 {render.yuan(d[m])}" if s != m else f"{m}月 {render.yuan(d[m])}")
            s = ms[i + 1] if i + 1 < len(ms) else s
    return "每月 " + render.yuan(d[ms[0]]) if len(segs) == 1 else "，".join(segs)


def income_note(d: dict[int, Decimal]) -> str:
    return "每月应发（税前）：" + vary_note(d)


def cmd_quick(a: argparse.Namespace) -> int:
    res = engine.run(build_plan(a))
    print(keypoints.text(res) + "\n\n" + render.quick_text(res))
    return 0


def cmd_scope(a: argparse.Namespace) -> int:
    def opt(x: str | None, what: str) -> Decimal | None:
        return None if x is None else engine.check_amount(amount(x, what), what, engine.MAX_BONUS)
    print(scope.run(a.kind, opt(a.amount, "--amount"), opt(a.profit, "--profit"), opt(a.income, "--income"), a.getihu))
    return 0


def cmd_bonus(a: argparse.Namespace) -> int:
    b = engine.check_amount(amount(a.bonus, "--bonus 年终奖"), "--bonus 年终奖", engine.MAX_BONUS)
    if b <= 0:
        raise GsError("E04", "年终奖要大于 0", "写实际要发的年终奖金额，如 --bonus 36000")
    body = render.bonus_only_text(b, a.year)
    if CONVERTED:
        conv = "；".join(f"{x.split(' → ')[0]} 即 {x.split(' → ')[1]} 元" for x in dict.fromkeys(CONVERTED))
        head, rest = body.split("\n", 1)
        body = f"{head}\n- 金额换算：{conv}。\n{rest}"
    print(body)
    return 0


def cmd_zones(_a: argparse.Namespace) -> int:
    print(render.zones_text())
    return 0


def build_parser() -> CnParser:
    p = CnParser(prog="geshui.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=CnParser)
    q = sub.add_parser("quick", help="单人逐月个税和到手")
    q.add_argument("--income", required=True)
    q.add_argument("--income-from", action="append")
    q.add_argument("--income-set", action="append")
    q.add_argument("--si")
    q.add_argument("--hf")
    q.add_argument("--si-from", action="append")
    q.add_argument("--base")
    q.add_argument("--si-rate")
    q.add_argument("--hf-rate")
    q.add_argument("--special", default="0")
    q.add_argument("--special-from", action="append")
    q.add_argument("--other", default="")
    q.add_argument("--tax-free", default="")
    q.add_argument("--start", type=int, default=1)
    q.add_argument("--end", type=int, default=12)
    q.add_argument("--first-job", action="store_true")
    q.add_argument("--sixty-k", action="store_true")
    q.add_argument("--bonus", default="0")
    q.add_argument("--bonus-month", type=int, default=12)
    q.add_argument("--bonus-mode", choices=["separate", "merge"], default="separate")
    q.add_argument("--year", type=int, default=2026)
    b = sub.add_parser("bonus", help="只算年终奖单独计税和临界点")
    b.add_argument("--bonus", required=True)
    b.add_argument("--year", type=int, default=2026)
    sub.add_parser("zones", help="列出年终奖单独计税全部「多发反而少拿」区间")
    sc = sub.add_parser("scope", help="超出范围的所得：劳务报酬、稿酬、经营所得、外籍、避税")
    sc.add_argument("kind", choices=["labor", "royalty", "business", "foreign", "allowance", "avoid"])
    sc.add_argument("--amount", help="劳务报酬、稿酬每次收入")
    sc.add_argument("--profit", help="经营所得全年利润")
    sc.add_argument("--income", help="非居民个人当月工资")
    sc.add_argument("--getihu", action="store_true", help="是个体工商户（适用减半）")
    return p


def main(argv: list[str] | None = None) -> int:
    CONVERTED.clear()
    try:
        a = build_parser().parse_args(argv)
        return {"quick": cmd_quick, "bonus": cmd_bonus, "zones": cmd_zones, "scope": cmd_scope}[a.cmd](a)
    except GsError as e:
        print(e.text())
        return e.exit_code()
    except SystemExit as e:          # -h 正常退出
        return int(e.code or 0) if isinstance(e.code, int) else 0
    except Exception as e:  # noqa: BLE001  最外层兜底：不甩堆栈
        err = GsError("E09", f"脚本内部出错（{type(e).__name__}）")
        print(err.text())
        return err.exit_code()


if __name__ == "__main__":
    sys.exit(main())
