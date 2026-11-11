"""逐项测算：经济补偿 N、代通知金、违法解除赔偿金 2N、未签书面合同二倍工资差额、未休年休假工资、仲裁时效。

口径（依据见 references/calc-rules.md，法条原文见 references/laws.md）：
- 工作年限：入职当天到解除当天（含两头）。
- 经济补偿月工资：离职前 12 个月平均应得工资（含奖金津贴补贴），低于最低工资按最低工资。
- 月工资高于当地上年度职工月平均工资三倍：基数按三倍、年限最多 12 年（只在封顶时才有 12 年上限）。
- 日工资 = 月工资 ÷ 21.75；按月计的期间（二倍工资）整月 × 月工资 + 零头工作日 × 日工资。
- 金额只在每一项最后一步四舍五入到分。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from . import avgwage, case as casemod, dates, lead
from .errors import fail
from .model import Item, Limitation, Result, fmt, money

D0 = Decimal(0)
D2175 = Decimal("21.75")
N_REASONS = {"employer_negotiated", "objective", "layoff", "contract_expired", "employee_forced", "closure"}
DISPUTED = {"misconduct", "probation_fail"}
LOCAL = "以当地劳动人事争议仲裁委员会的口径为准"


@dataclass
class Facts:
    entry: date
    leave: date
    apply: date
    wage: Decimal
    wage_src: str
    reason: str
    city: str = ""
    avg_wage: Decimal | None = None
    min_wage: Decimal | None = None
    last_wage: Decimal | None = None
    ot_in: Decimal = D0
    notice: str = "未知"             # 有 / 没有 / 未知（只对 objective 有意义）
    contract: str = ""              # 签了 / 没签 / 补签 / ""（没说）
    signed_date: date | None = None
    renew_declined: bool = False
    al_years: Decimal | None = None
    al_taken: Decimal = D0
    al_prev: dict[int, Decimal] = field(default_factory=dict)
    flags: set[str] = field(default_factory=set)
    wage_doubts: list[str] = field(default_factory=list)
    guesses: list[str] = field(default_factory=list)
    rough: bool = False
    years_fuzzy: int | None = None   # 用户说「X 年多」或带小数的年数：零头说不准，lead 段给两种月数
    entry_guessed: bool = False
    leave_guessed: bool = False


def mtext(m: Decimal) -> str:
    return f"{m:.1f}".rstrip("0").rstrip(".")


def lim(leave: date, apply: date, extra: str = "") -> Limitation:
    deadline = dates.plus_years(leave, 1)
    left = (deadline - apply).days
    status = "已过" if left < 0 else ("临近" if left <= 30 else "未过")
    note = (f"从离职日 {leave} 起一年，截止 {deadline}；按 {apply} 申请"
            + (f"还剩 {left} 天" if left >= 0 else f"已超过 {-left} 天"))
    return Limitation(status, deadline, note + (f"；{extra}" if extra else ""))


class Calc:
    def __init__(self, f: Facts):
        self.f = f
        self.assumptions: list[str] = list(f.guesses)
        self.doubts: list[str] = list(f.wage_doubts)
        self.questions: list[tuple[str, str]] = []
        self.facts: list[str] = []

    # ---------- 基数 ----------
    def setup(self) -> None:
        f = self.f
        if f.leave < f.entry:
            raise fail("E03", f"离职日 {f.leave} 早于入职日 {f.entry}", "核对两个日期是不是写反了", 3)
        if f.entry.year < 1950 or f.leave.year > f.apply.year + 2:
            raise fail("E03", f"日期超出合理范围（入职 {f.entry}，离职 {f.leave}）", "核对年份", 3)
        self.base = max(f.wage, f.min_wage) if f.min_wage is not None else f.wage
        if f.min_wage is not None and f.min_wage > f.wage:
            self.assumptions.append(f"月工资 {fmt(f.wage)} 低于当地最低工资 {fmt(f.min_wage)}，经济补偿按最低工资算")
        self.base_no_ot = max(self.base - f.ot_in, D0)
        self.facts += [f"入职 {f.entry}，离职 {f.leave}，按 {f.apply} 判时效",
                       f"月工资 {fmt(f.wage)} 元（{f.wage_src}）",
                       f"离职方式：{casemod.REASONS[f.reason][0]}（代码 {f.reason}）"]
        if "买家报的" in f.wage_src:
            self.doubts.append("月工资按你报的一个数当作离职前 12 个月平均应得工资；如果只报了基本工资、没算绩效提成奖金补贴，会少算，"
                               "请按工资条或银行流水的税前应发核一次")
        info = avgwage.lookup({"city": f.city, "avg_wage": f.avg_wage}, f.leave)
        self.avg = info["value"]
        self.cap3 = self.avg * 3 if self.avg is not None else None
        if self.avg is not None:
            self.facts.append(f"当地上年度职工月平均工资：{info['city']} {fmt(self.avg)} 元/月（{info['note']}），三倍封顶线 {fmt(self.cap3)} 元")
            if info.get("stale") and self.base > self.avg * Decimal("2.4"):
                self.doubts.append(info["stale"] + "；" + LOCAL)
        else:
            if self.base >= Decimal("15000"):
                self.doubts.append(info["note"] + "（存疑：月工资可能超过三倍封顶线）；" + LOCAL)
            else:
                self.assumptions.append(info["note"])
        self.capped = self.cap3 is not None and self.base > self.cap3

    # ---------- N 的核心 ----------
    def n_core(self, split_2008: bool) -> tuple[Decimal, Decimal, str, list[str], list[str]]:
        """返回（月数，金额，算式，过程，存疑）。split_2008：2008 年前入职的 N 分段算（2N 不分段）。"""
        f = self.f
        detail: list[str] = []
        doubts: list[str] = []
        split = split_2008 and f.entry < dates.LCL_START
        start = dates.LCL_START if split else f.entry
        sp = dates.span(start, f.leave)
        m = Decimal(str(dates.comp_months(sp)))
        rule = ("零头满 6 个月按 1 年" if sp.months >= 6 else
                "零头不满 6 个月按半个月" if (sp.months or sp.days) else "没有零头")
        detail.append(f"月工资按离职前 12 个月平均税前应发算（扣社保个税之前，不是到手工资），含绩效、提成、奖金、津贴、补贴：{fmt(self.base)} 元")
        detail.append(f"工作年限（{'2008-01-01 起' if split else '入职起'}，从入职当天算到离职当天、含两头）{sp.text()} → 按第四十七条折算 {mtext(m)} 个月（{rule}）")
        if self.cap3 is not None:
            if self.capped:
                used_base, used_m = self.cap3, min(m, Decimal(12))
                detail.append(f"月工资 {fmt(self.base)} 高于三倍封顶线 {fmt(self.cap3)}：基数按 {fmt(self.cap3)}，"
                              f"年限最多 12 年 → 按 {mtext(used_m)} 个月")
            else:
                used_base, used_m = self.base, m
                detail.append(f"月工资 {fmt(self.base)} 没超过三倍封顶线 {fmt(self.cap3)}：不封顶，也不受 12 年上限限制，按实际 {mtext(m)} 个月")
        else:
            used_base, used_m = self.base, m
            detail.append("当地社平工资没核到，没做三倍封顶判断（存疑）")
        amount = used_base * used_m
        text = f"{fmt(used_base)} × {mtext(used_m)} 个月"
        if split:
            pre = dates.span(f.entry, dates.LCL_START - timedelta(days=1))
            pm = Decimal(dates.old_comp_months(pre))
            if f.reason in ("contract_expired", "employee_forced"):
                pm_used, note = D0, "2008 年前到期终止、员工提出解除的，按当时规定一般不给经济补偿"
            elif f.reason in ("employer_negotiated", "objective"):
                pm_used, note = min(pm, Decimal(12)), "按当时规定每满一年一个月、不满一年按一年，协商解除和不能胜任最多 12 个月"
            else:
                pm_used, note = pm, "按当时规定每满一年一个月、不满一年按一年"
            detail.append(f"2008 年前工作年限 {pre.text()} → {mtext(pm_used)} 个月（{note}，《中华人民共和国劳动合同法》第九十七条第三款）")
            amount += self.base * pm_used
            text += f"（2008 年后段）+ {fmt(self.base)} × {mtext(pm_used)} 个月（2008 年前段）"
            doubts.append("2008 年前的工作年限按当时规定（劳部发〔1994〕481号）算，各地对封顶和适用情形理解不一，金额较大时请律师按当地口径复核；" + LOCAL)
        return used_m, money(amount), text, detail, doubts

    def item_n(self, claim: bool) -> Item:
        m, amt, text, detail, doubts = self.n_core(True)
        laws = ("LCL-46", "LCL-47", "REG-27") + (("LCL-97",) if self.f.entry < dates.LCL_START else ())
        return Item("n", "经济补偿（N）", laws, amt, f"{text} = {fmt(amt)} 元", lim(self.f.leave, self.f.apply),
                    claim, tuple(detail), tuple(doubts))

    def item_notice(self, claim: bool) -> Item:
        f = self.f
        last = f.last_wage if f.last_wage is not None else self.base
        if f.last_wage is None and f.reason == "objective":
            self.assumptions.append("代通知金按上一个月工资；没单独给上月工资，用月平均工资代替")
        return Item("notice", "代通知金（N+1 的 1）", ("LCL-40", "REG-20"), money(last),
                    f"上一个月工资 {fmt(last)} 元（不封顶）", lim(f.leave, f.apply), claim,
                    ("只在单位依第四十条解除、又没提前 30 天书面通知时有；裁员、协商解除、违法解除都没有这一项",))

    def item_2n(self, claim: bool) -> Item:
        m, amt, text, detail, doubts = self.n_core(False)
        amt2 = money(amt * 2)
        detail.append("年限从用工之日起算（《中华人民共和国劳动合同法实施条例》第二十五条），拿了 2N 就不再另付 N 和代通知金")
        return Item("2n", "违法解除赔偿金（2N）", ("LCL-48", "LCL-87", "REG-25", "LCL-47"), amt2,
                    f"{text} × 2 = {fmt(amt2)} 元", lim(self.f.leave, self.f.apply), claim, tuple(detail), tuple(doubts))

    # ---------- 二倍工资 ----------
    def item_double(self) -> Item | None:
        f = self.f
        if f.contract not in ("没签", "补签"):
            return None
        start = dates.add_months(f.entry, 1)                 # 满一个月的次日
        year_end = dates.add_months(f.entry, 12) - timedelta(days=1)
        end = min(year_end, f.leave)
        why_end = "用工满一年的前一日，满一年视为已订立无固定期限劳动合同" if end == year_end else "离职日"
        if f.contract == "补签":
            if f.signed_date is None:
                raise fail("E05", "说了补签但没给补签日期", "加 --signed-date 2025-06-01（补签合同那天）", 4)
            if f.signed_date - timedelta(days=1) < end:
                end, why_end = f.signed_date - timedelta(days=1), "补签合同前一日"
        if end < start:
            return None
        base = self.base_no_ot
        n, rest = dates.whole_months_and_rest(start, end)
        wd = dates.workdays(rest, end) if rest else 0
        full = money(base * n + base / D2175 * wd)
        whole_deadline = dates.plus_years(end, 1)
        cut = dates.plus_years(f.apply, -1)
        m_start = max(start, cut)
        if m_start <= end:
            n2, rest2 = dates.whole_months_and_rest(m_start, end)
            wd2 = dates.workdays(rest2, end) if rest2 else 0
            monthly = money(base * n2 + base / D2175 * wd2)
        else:
            monthly = D0
        if f.apply <= whole_deadline:
            amt = full
            status = "未过" if (whole_deadline - f.apply).days > 30 else "临近"
            note = f"整体起算：从二倍工资最后一天 {end} 起一年，到 {whole_deadline}，按全额主张"
        elif monthly > 0:
            amt, status = monthly, "部分已过"
            note = f"整体起算口径已过（{whole_deadline}）；按逐月起算，申请日前一年内的部分 {fmt(monthly)} 元还能主张"
        else:
            amt, status = D0, "已过"
            note = f"二倍工资最后一天 {end} 起一年（{whole_deadline}）已过，申请日前一年内也没有未签合同的月份"
        detail = [f"期间：{start}（用工满一个月的次日）至 {end}（{why_end}），{n} 个整月" + (f" + {wd} 个工作日" if wd else ""),
                  f"基数：剔除加班费后的月工资 {fmt(base)} 元；「二倍」里有一倍已经发了，只补差额那一倍，最多 11 个月"]
        doubts = [f"二倍工资的时效起算有两种口径：整体起算（按全额 {fmt(full)} 元）和逐月起算（只算申请日前一年内的 {fmt(monthly)} 元），"
                  "各地都有采用，" + LOCAL,
                  "二倍工资的基数是否剔除不固定的奖金、提成，各地不一，" + LOCAL]
        if f.contract == "没签" and f.leave >= dates.add_months(f.entry, 12):
            detail.append("用工满一年仍未签，视为已订立无固定期限劳动合同（《中华人民共和国劳动合同法》第十四条第三款），满一年后不再算二倍工资")
        formula = f"{fmt(base)} × {n} 个月" + (f" + {fmt(base)} ÷ 21.75 × {wd} 个工作日" if wd else "") + f" = {fmt(full)} 元"
        if amt != full:
            formula += f"；时效内可主张 {fmt(amt)} 元"
        return Item("double", "未签书面劳动合同二倍工资差额", ("LCL-10", "LCL-82", "LCL-14", "REG-6", "REG-7", "LDAL-27"),
                    amt, formula, Limitation(status, whole_deadline, note), amt > 0, tuple(detail), tuple(doubts))

    # ---------- 未休年休假 ----------
    def item_leave(self) -> Item | None:
        f = self.f
        if f.al_years is None:
            return None
        ent = 0 if f.al_years < 1 else 5 if f.al_years < 10 else 10 if f.al_years < 20 else 15
        start = max(date(f.leave.year, 1, 1), f.entry)
        passed = (f.leave - start).days + 1
        owed = max(0, math.floor(Decimal(passed) / 365 * ent - f.al_taken))
        daily = self.base_no_ot / D2175
        total = daily * owed * 2
        days_total = Decimal(owed)
        detail = [f"累计工作年限 {mtext(f.al_years)} 年 → 全年应休 {ent} 天（满1年5天、满10年10天、满20年15天）",
                  f"离职当年折算：{passed} ÷ 365 × {ent} − 已休 {mtext(f.al_taken)} = {owed} 天（不足 1 整天不算）",
                  f"日工资 = 剔除加班费的月工资 {fmt(self.base_no_ot)} ÷ 21.75 = {daily:.2f} 元"]
        doubts: list[str] = []
        if f.entry > dates.add_months(f.leave, -12) and f.al_years < 1:
            detail.append("累计工作不满 1 年（所有单位加起来），还不享受年休假")
        for y, d in sorted(f.al_prev.items()):
            due = min(date(y + 1, 12, 31), f.leave)
            deadline = dates.plus_years(due, 1)
            if f.apply <= deadline:
                total += daily * d * 2
                days_total += d
                detail.append(f"{y} 年未休 {mtext(d)} 天：在时效内（最晚安排到 {due}，时效到 {deadline}）")
            else:
                detail.append(f"{y} 年未休 {mtext(d)} 天：已过时效（{deadline}），不计")
        if f.al_prev:
            doubts.append("往年未休年假的时效起算，有的地方从次年 12 月 31 日起算、有的从离职日起算，" + LOCAL)
        amt = money(total)
        if amt <= 0:
            if ent == 0:
                self.assumptions.append("累计工作不满 1 年，不享受带薪年休假，未休年假工资为 0")
            else:
                self.assumptions.append(f"离职当年按 {passed} ÷ 365 × {ent} 天折算、减去已休 {mtext(f.al_taken)} 天后不足 1 整天，"
                                        "没有未休年假工资（《企业职工带薪年休假实施办法》第十二条）")
            return None
        return Item("leave", "未休年休假工资", ("PLR-3", "PLR-5", "PLM-10", "PLM-11", "PLM-12"), amt,
                    f"{fmt(self.base_no_ot)} ÷ 21.75 × {mtext(days_total)} 天 × 200% = {fmt(amt)} 元（法条的 300% 里含已发的 100%，另付 200%）",
                    lim(f.leave, f.apply), True, tuple(detail), tuple(doubts))

    # ---------- 汇总 ----------
    def run(self) -> Result:
        self.setup()
        f = self.f
        reason = f.reason
        protected = [k for k in ("pregnant", "medical_period", "near_retire_15y") if k in f.flags]
        illegal = reason == "illegal_dismissal" or (reason in ("objective", "layoff", "contract_expired") and bool(protected))
        if illegal and reason != "illegal_dismissal":
            self.doubts.append("属于《中华人民共和国劳动合同法》第四十二条不得解除的情形，单位按第四十条、第四十一条解除或到期终止的，"
                               "按违法解除或违法终止主张 2N（到期的要顺延，第四十五条）")
        if reason == "contract_expired" and f.renew_declined:
            self.assumptions.append("单位维持或提高原条件续签、员工不同意的，到期终止不给经济补偿（第四十六条第五项）")
        known = reason != "unknown"
        n_claim = known and reason in N_REASONS and not illegal and not (reason == "contract_expired" and f.renew_declined)
        notice_claim = known and reason == "objective" and not illegal and f.notice == "没有"
        if reason == "objective" and f.notice == "未知" and not illegal:
            self.questions.append(("单位有没有提前 30 天书面通知", "没提前通知要多付一个月工资（代通知金），下面没算进合计"))
        n_item, no_item, dn_item = self.item_n(n_claim), self.item_notice(notice_claim), self.item_2n(illegal)
        if reason in DISPUTED:
            dn_item.claim = True
            self.doubts.append("单位以过错或试用期不合格解除：理由和证据成立的不赔；单位举证不了、制度没公示或程序违法的，按违法解除主张 2N"
                               "（解除是否合法由单位承担举证责任，法释〔2020〕26号第四十四条）。下面按 2N 列，单位理由成立时这项为 0，属于存疑项")
        items = [n_item, no_item, dn_item]
        for it in (self.item_double(), self.item_leave()):
            if it is not None:
                items.append(it)
        lead_topics = f.flags & {"transfer", "dispatch", "outsourcing", "overseas"}
        if not known and not lead_topics:
            self.questions.insert(0, ("还没走、只是被调岗或被排挤的：调岗有没有降薪、有没有书面通知，单位有没有欠薪或少缴社保",
                                      "自己辞职一般是 0；只有欠薪、未足额缴社保、未按约定提供劳动条件等第三十八条情形并以此书面解除才有 N"))
        if not known and "transfer" not in f.flags:
            self.questions.insert(0, ("是谁提出解除的、单位给的理由是什么（解除通知、离职证明或聊天记录上怎么写的）；如果单位以不能胜任、医疗期满、客观情况变化解除，有没有提前 30 天书面通知",
                                      "离职方式决定是 0、N、N+1 还是 2N；没提前 30 天书面通知才有代通知金"))
        if f.contract == "":
            self.questions.append(("签没签书面劳动合同", "入职超过一个月没签的，可以另要二倍工资差额，最多 11 个月；没说就没算"))
        if f.al_years is None:
            self.questions.append(("参加工作累计多少年、今年休过几天年假", "离职当年没休完的年假要按日工资 200% 补；没给就没算"))
        if any(it.claim and it.limitation.status == "临近" for it in items):
            self.doubts.append("快到一年时效了：单位答应过付钱（有聊天记录、邮件、短信）属于对方同意履行，你书面催要过也算，时效从那天起中断、重新计算一年"
                               "（《中华人民共和国劳动争议调解仲裁法》第二十七条第二款），把这些记录留好；是否认定中断以当地劳动人事争议仲裁委员会为准，截止日前递交仲裁申请最稳")
        for it in items:
            if it.claim and it.limitation.status == "已过":
                it.claim, it.barred = False, True
                dl = it.limitation.deadline
                self.doubts.append(f"「{it.title}」已过仲裁时效（{it.limitation.note}），没算进合计。时效可以中断：如果在 {dl} 之前向单位书面主张过、"
                                   "向劳动监察或仲裁委求助过、或单位同意过付钱，从那天起重新计算一年（《中华人民共和国劳动争议调解仲裁法》第二十七条第二款），"
                                   "还在新的一年内的可以加回来；是否中断以当地劳动人事争议仲裁委员会认定为准")
        scen = [("员工主动辞职 / 员工提出协商解除", D0, "不给经济补偿"),
                ("单位提出协商解除、到期不续、裁员、员工因欠薪欠社保被迫离职（N）", n_item.amount, n_item.formula_text),
                ("单位依第四十条解除且没提前 30 天书面通知（N+1）", money(n_item.amount + no_item.amount),
                 f"{fmt(n_item.amount)} + {fmt(no_item.amount)}"),
                ("单位违法解除（2N，不再另付 N 和代通知金）", dn_item.amount, dn_item.formula_text)]
        if not known:
            for it in items[:3]:
                it.claim = False
        cautions = [casemod.CAUTION_FLAGS[k] for k in protected]
        notes: list[str] = [f"月工资基数 {fmt(self.base)} 元：按离职前 12 个月平均税前应发算（扣社保、个税之前，不是到手工资），含绩效、提成、奖金、津贴、补贴，年终奖 ÷12"]
        if reason in ("employee_resign", "employee_negotiated"):
            notes.append(f"{casemod.REASONS[reason][0]}：没有经济补偿 N，也没有代通知金和 2N（《中华人民共和国劳动合同法》第四十六条列的情形里没有这一种）。"
                         "例外：如果是因为单位欠薪、未足额缴社保、未按约定提供劳动条件等第三十八条情形、并以此书面解除的，改按被迫离职算 N")
        if reason in ("layoff", "employer_negotiated", "contract_expired", "employee_forced", "closure"):
            notes.append("这种离职方式法定没有代通知金：代通知金（N+1 的 1）只在单位依第四十条解除、又没提前 30 天书面通知时才有；"
                         "单位愿意多给一个月，属于协商多给的，不是法定")
        if self.capped:
            notes.append(f"月工资超过当地上年度职工月平均工资三倍要封顶：按 {fmt(self.cap3)} 元算、年限最多 12 年。用哪一年、哪个口径的社平工资"
                         "（全口径还是城镇非私营）各地不一，封顶线以当地人社部门公布数和劳动人事争议仲裁委员会的口径为准")
        if illegal:
            notes.append("违法解除是否成立由仲裁委认定：如果单位拿不出合法解除的理由和证据（解除是否合法由单位承担举证责任，法释〔2020〕26号第四十四条），可以主张 2N；"
                         "也可以选择要求继续履行劳动合同，不要 2N（第四十八条）")
        res = Result(self.facts, items, scen, known, self.assumptions, self.doubts, self.questions, cautions)
        res.notes = notes
        res.guessed = bool(f.guesses)
        res.lead = lead.build(f.flags, n_amt=n_item.amount, dn_amt=dn_item.amount,
                              base=self.cap3 if self.capped else self.base, capped=self.capped,
                              years_fuzzy=f.years_fuzzy, entry_guessed=f.entry_guessed, leave_guessed=f.leave_guessed,
                              reason_known=known, reason=reason, protected_hit=(protected[0] if illegal and reason != "illegal_dismissal" and protected else ""))
        stops = f.flags & set(casemod.STOP_FLAGS)
        if known and not stops:
            claimed = [i for i in items if i.claim and i.amount > 0]
            barred = [i for i in items if i.barred and i.amount > 0]
            total = money(sum((i.amount for i in claimed), D0))
            if reason in DISPUTED:
                concl = ""
            elif claimed and illegal:
                concl = (f"如果单位拿不出合法解除的理由和证据，你可以主张合计 {fmt(total)} 元（{'、'.join(i.title for i in claimed)}，"
                         "逐项算式见下）；违法解除是否成立由劳动人事争议仲裁委员会认定。")
            elif claimed:
                concl = f"按你给的事实，可以主张合计 {fmt(total)} 元（{'、'.join(i.title for i in claimed)}，逐项算式见下）。"
            elif barred:
                concl = (f"这些项目本来能要 {fmt(sum(i.amount for i in barred))} 元，但都已过一年仲裁时效，按目前事实可主张 0 元；"
                         "先确认有没有让时效中断的记录，有的话还能加回来。")
            else:
                concl = "按目前事实，没有可以主张的经济补偿或赔偿金。"
            main = next((i for i in items if i.claim or i.barred), items[0])
            lead.general(res.lead, conclusion=concl, notes=notes, limitation=main.limitation.note, barred=bool(barred))
        return res


def compute(f: Facts) -> Result:
    stops = [casemod.STOP_FLAGS[k] for k in casemod.STOP_FLAGS if k in f.flags]
    if stops and not f.rough:
        raise fail("E07", "；".join(stops),
                   "这类情形不出确定金额：照上面说的先走程序、找对的人；用户要个参考数，加 --rough 按普通劳动关系粗算（输出会标明前提）", 5)
    res = Calc(f).run()
    res.rough = stops
    return res
