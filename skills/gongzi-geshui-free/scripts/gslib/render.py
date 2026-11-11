"""把计算结果写成能直接贴进回答的中文文本：输入与假设、逐月表、逐月算式、变化原因、年终奖比对、依据。"""
from __future__ import annotations

from decimal import Decimal

from .engine import BonusCompare, Month, Result, pct, zone_report
from .rules import bonus_tax_separate, money

CHECKED = "2026-11-03"
POLICY_BASE = ("累计预扣法：国家税务总局公告2018年第61号（居民个人工资薪金所得预扣预缴）；"
               "税率表：《中华人民共和国个人所得税法》综合所得税率表")
POLICY_BONUS = ("年终奖单独计税：财政部 税务总局公告2023年第30号，全年一次性奖金可不并入当年综合所得单独计税，"
                "政策执行到2027年12月31日；全年一次性奖金包括年终奖、年终加薪（13薪、年终双薪）、年薪和绩效工资兑现，"
                "一个纳税年度每人只能用一次，半年奖、季度奖不能单独计税，并入发放当月工资")
POLICY_PENSION = ("个人养老金：每年缴费上限12000元，可在工资预扣时扣除（每月最多1000）；领取时单独按3%计税，"
                  "边际税率越高抵税效果越明显，3%档的人基本只是延后交税（财政部 税务总局公告2022年第34号）")
POLICY_60K = "6万元减除费用：国家税务总局公告2020年第19号（上年1~12月都在本单位领工资且全年工资薪金不超过6万元）"
POLICY_FIRST = "首次就业减除费用从1月起算：国家税务总局公告2020年第13号（当年首次取得工资薪金）"
POLICY_SPECIAL = "专项附加扣除标准：国发〔2023〕13号（子女教育、3岁以下婴幼儿照护每人每月2000，赡养老人独生子女每月3000等）"
POLICY_SI = "社保公积金：个人缴费比例和基数上下限由各地每年公布，地方社保比例以当地为准；本结果按你给的数算"
POLICY_SETTLE = ("预扣不是最终结果：次年3月1日至6月30日年度汇算多退少补；全年综合所得收入不超过12万元或补税不超过400元的可免办，"
                 "年终奖计税方式也可在汇算时于个税App里改选")


def yuan(x: Decimal) -> str:
    return f"{money(x):,.2f}"


def quick_text(res: Result) -> str:
    p = res.plan
    out = ["【输入与假设】"]
    out += [f"- {a}" for a in p.assumptions]
    out += ["", "【逐月个税与到手】",
            "| 月份 | 应发 | 三险个人 | 公积金个人 | 本月个税 | 年终奖税 | 到手 | 累计应纳税所得额 | 预扣率 |",
            "|---|---|---|---|---|---|---|---|---|"]
    for m in res.months:
        bonus = f"+奖{yuan(m.bonus_cash)}" if m.bonus_cash else ""
        out.append(f"| {m.mo}月 | {yuan(m.income)}{bonus} | {yuan(m.si)} | {yuan(m.hf_paid)} | {yuan(m.tax)} | "
                   f"{yuan(m.bonus_tax)} | {yuan(m.net)} | {yuan(m.cum_taxable)} | {pct(m.rate)} |")
    out.append(f"| 合计 | | | | {yuan(sum((m.tax for m in res.months), Decimal(0)))} | "
               f"{yuan(sum((m.bonus_tax for m in res.months), Decimal(0)))} | {yuan(res.total_net)} | | |")
    out += ["", "【逐月算式】（累计应纳税所得额 = 累计收入 − 累计免税收入 − 累计减除费用 − 累计专项扣除 − 累计专项附加扣除 − 累计其他扣除；"
            "本月个税 = 累计应纳税所得额 × 预扣率 − 速算扣除数 − 累计已预扣）"]
    out += [formula(m) for m in res.months]
    out += ["", "【个税和到手为什么变了】"]
    out += [f"- {j}" for j in res.jumps] or ["- 各月个税没有上涨，到手没有变化。"]
    out += [f"- {n}" for n in res.notes]
    if res.compare:
        out += ["", *bonus_text(res.compare, p.bonus_month, p.bonus_mode)]
    out += ["", f"【全年合计】{p.start}~{p.end}月 工资个税 {yuan(sum((m.tax for m in res.months), Decimal(0)))} 元"
            + (f"，年终奖税 {yuan(sum((m.bonus_tax for m in res.months), Decimal(0)))} 元" if p.bonus else "")
            + f"，个税合计 {yuan(res.total_tax)} 元，到手合计 {yuan(res.total_net)} 元。"]
    out += ["", *policy_lines(p)]
    return "\n".join(out)


def formula(m: Month) -> str:
    inc = f"累计收入 {yuan(m.cum_income)}"
    parts = [inc]
    if m.cum_tax_free:
        parts.append(f"免税 {yuan(m.cum_tax_free)}")
    parts.append(f"减除费用 {yuan(m.cum_fee)}（{m.fee_note}）")
    parts.append(f"专项扣除 {yuan(m.cum_si)}")
    if m.cum_special:
        parts.append(f"专项附加 {yuan(m.cum_special)}")
    if m.cum_other:
        parts.append(f"其他扣除 {yuan(m.cum_other)}")
    head = " − ".join(parts)
    raw = m.cum_income - m.cum_tax_free - m.cum_fee - m.cum_si - m.cum_special - m.cum_other
    zero = "（≤0 按 0）" if raw <= 0 else ""
    line = (f"{m.mo}月：{head} = {yuan(raw)}{zero}；累计应纳税额 {yuan(m.cum_taxable)}×{pct(m.rate)}−{m.quick:,} = "
            f"{yuan(m.cum_tax)}；减已预扣 {yuan(m.prev_withheld)}，本月个税 {yuan(m.tax)}")
    if m.cum_tax - m.prev_withheld < 0:
        line += "（算出负数按 0，本月不退）"
    if m.bonus_in:
        line += f"；本月累计收入里含并入的年终奖 {yuan(m.bonus_in)}"
    if m.excess:
        line += f"；含单位公积金超标并入 {yuan(m.excess)}"
    if m.bonus_tax:
        line += f"；另有年终奖单独计税 {yuan(m.bonus_tax)}"
    return line


def bonus_text(c: BonusCompare, month: int, mode: str) -> list[str]:
    out = ["【年终奖：单独计税 vs 并入综合所得】",
           f"- 单独计税：{yuan(c.bonus)} ÷ 12 = {yuan(c.bonus / 12)}，落月度税率表 {pct(c.sep_rate)} 档，"
           f"{yuan(c.bonus)} × {pct(c.sep_rate)} − {c.sep_quick:,} = {yuan(c.sep_bonus_tax)}（速算扣除数只减一次，不乘 12）",
           f"- 工资部分全年应纳税所得额 W = {yuan(c.wage_taxable)}，工资全年税 {yuan(c.wage_tax)}",
           f"- 单独计税全年合计 = {yuan(c.wage_tax)} + {yuan(c.sep_bonus_tax)} = {yuan(c.sep_total)}",
           f"- 并入综合所得全年合计 = 年度税率表({yuan(c.wage_taxable)} + {yuan(c.bonus)}) = {yuan(c.merge_total)}",
           f"- 结论：{c.better}更省，全年少交 {yuan(c.saving)} 元" + ("（两种一样，选单独计税省事）" if not c.saving else "")]
    if c.wage_taxable < 0:
        out.append(f"- 工资部分扣除没用完（W 为负 {yuan(c.wage_taxable)}），并入能把没用完的扣除抵掉。")
    out.append(f"- 上面逐月表里 {month} 月按「{'单独计税' if mode == 'separate' else '并入当月工资'}」预扣；"
               "单位预扣选哪种不是最终结果，次年汇算时还能在个税App改选。")
    out += ["", "【临界点提醒】"]
    if c.dead_zone:
        out += zone_report(c.bonus) + list(c.fixes)
    else:
        out += zone_report(c.bonus)
    return out


def bonus_only_text(b: Decimal, year: int) -> str:
    from .rules import MONTHLY, bracket  # noqa: PLC0415
    rate, quick = bracket(b / 12, MONTHLY)
    tax = bonus_tax_separate(b)
    zone = zone_report(b)
    out = ["【回答要点】（整段抄进回答正文，不放代码块）",
           f"- 年终奖单独计税：{yuan(b)}÷12={yuan(b / 12)}，落 {pct(rate)} 档，{yuan(b)}×{pct(rate)}−{quick:,}={yuan(tax)} 元，"
           f"税后到手 {yuan(b - tax)} 元。",
           f"- {zone[0].lstrip('⚠ ')}", *[f"- {z.strip()}" for z in zone[1:]],
           "- 要比较单独计税和并入综合所得哪个更省，需要你的每月工资（税前）、社保公积金个人扣款、专项附加扣除。",
           f"- {POLICY_BONUS}。", "",
           "【年终奖单独计税】",
           f"- {yuan(b)} ÷ 12 = {yuan(b / 12)}，落月度税率表 {pct(rate)} 档，{yuan(b)} × {pct(rate)} − {quick:,} = {yuan(tax)}",
           f"- 年终奖税 {yuan(tax)} 元，税后到手 {yuan(b - tax)} 元（这笔不扣社保公积金）",
           "", "【临界点提醒】", *zone_report(b), "",
           "【还差什么】要比较「单独计税」和「并入综合所得」哪个省，需要全年工资情况（每月应发、社保公积金个人、专项附加扣除），"
           "用 quick 加 --bonus 再算一次。", "",
           "【依据与适用期限】", f"- {POLICY_BONUS}", f"- {POLICY_SETTLE}", f"- 口径核对日期 {CHECKED}"]
    if year > 2027:
        out.append(f"- 注意：你算的是 {year} 年，单独计税政策目前只明确执行到 2027 年 12 月 31 日，之后以届时公告为准。")
    return "\n".join(out)


def policy_lines(p) -> list[str]:
    out = ["【依据与适用期限】", f"- {POLICY_BASE}"]
    if p.bonus:
        out.append(f"- {POLICY_BONUS}")
        if p.year > 2027:
            out.append(f"- 注意：你算的是 {p.year} 年，单独计税政策目前只明确执行到 2027 年 12 月 31 日，之后以届时公告为准。")
    if p.sixty_k:
        out.append(f"- {POLICY_60K}；员工可以不适用，单位要按规定确认")
    if p.first_job:
        out.append(f"- {POLICY_FIRST}；员工要向单位作出今年首次就业的承诺")
    if any(p.special.values()):
        out.append(f"- {POLICY_SPECIAL}；金额以个税App里确认的为准")
    if any(p.other.values()):
        out.append(f"- {POLICY_PENSION}；其他扣除里如有商业健康险，每年上限2400元")
    out.append(f"- {POLICY_SI}")
    if p.start > 1 and not p.first_job:
        out.append("- 年中入职：减除费用从入职月起算。如果今年入职前在别的单位领过工资，两边各自预扣，次年汇算常要补税；"
                   "如果今年是第一次领工资（如应届生），加 --first-job 重算，减除费用从 1 月起算")
    out.append(f"- {POLICY_SETTLE}")
    out.append(f"- 口径核对日期 {CHECKED}")
    return out


def zones_text() -> str:
    from .rules import bonus_dead_zones  # noqa: PLC0415
    out = ["【年终奖单独计税「多发反而少拿」区间】（不含两端；发到下限最划算，要多发就发过上限）",
           "| 区间（元） | 发到下限的税 | 下限多发 1 元的税 | 多发 1 元多交 |", "|---|---|---|---|"]
    for t, end in bonus_dead_zones():
        a, b = bonus_tax_separate(t), bonus_tax_separate(t + 1)
        out.append(f"| {yuan(t)} ~ {yuan(end)} | {yuan(a)} | {yuan(b)} | {yuan(b - a)} |")
    out += ["", "怎么用：先看年终奖落不落在区间里；落进去就降到下限（多出部分并入当月工资发）或提到上限以上。",
            "单独计税还是并入更省，要看全年工资：用 quick 加 --bonus 算。", "",
            "【依据与适用期限】", f"- {POLICY_BONUS}", f"- 口径核对日期 {CHECKED}"]
    return "\n".join(out)
