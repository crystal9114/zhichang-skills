"""【回答要点】：把结论、关键数、该写的依据压成几句整话，答题时整段抄进正文。"""
from __future__ import annotations

from decimal import Decimal

from .engine import Month, Result, pct, zone_report
from .render import (POLICY_60K, POLICY_BONUS, POLICY_FIRST, POLICY_PENSION, POLICY_SETTLE, POLICY_SI, yuan)


def segments(months: tuple[Month, ...], attr: str) -> str:
    """把逐月数压成「1~3月 285.00，4月 425.00，5~12月 950.00」。"""
    out, i = [], 0
    while i < len(months):
        j = i
        val = getattr(months[i], attr)
        while j + 1 < len(months) and getattr(months[j + 1], attr) == val:
            j += 1
        a, b = months[i].mo, months[j].mo
        out.append(f"{a}~{b}月每月 {yuan(val)}" if a != b else f"{a}月 {yuan(val)}")
        i = j + 1
    return "，".join(out)


def points(res: Result) -> list[str]:
    p, ms = res.plan, res.months
    out: list[str] = []
    for a in p.assumptions:
        if a.startswith("金额写法换算："):
            pairs = a.split("：", 1)[1].split("；")
            out.append("金额换算：" + "；".join(f"{x.split(' → ')[0]} 即 {x.split(' → ')[1]} 元" for x in pairs) + "。")
    first = ms[0]
    out.append(f"每月扣款：三险个人 {yuan(first.si)} 元，公积金个人 {yuan(first.hf_paid)} 元"
               + (f"（其中可税前扣除 {yuan(first.hf_deduct)} 元）" if first.hf_deduct != first.hf_paid else "")
               + (f"，专项附加扣除 {yuan(p.special[p.start])} 元" if p.special[p.start] else "") + "。")
    span = f"{p.start}~{p.end}月" if p.start != p.end else f"{p.start}月"
    out.append(f"逐月个税：{segments(ms, 'tax')}；{span}工资个税合计 "
               f"{yuan(sum((m.tax for m in ms), Decimal(0)))} 元。")
    out.append(f"逐月到手：{segments(ms, 'net')}。")
    out += res.jumps
    c = res.compare
    if c:
        out.append(f"年终奖单独计税：{yuan(c.bonus)}÷12={yuan(c.bonus / 12)}，落 {pct(c.sep_rate)} 档，"
                   f"{yuan(c.bonus)}×{pct(c.sep_rate)}−{c.sep_quick:,}={yuan(c.sep_bonus_tax)} 元。")
        out.append(f"全年合计：单独计税 {yuan(c.sep_total)} 元，并入综合所得 {yuan(c.merge_total)} 元，"
                   f"{c.better}更省 {yuan(c.saving)} 元。")
        if c.wage_taxable < 0:
            out.append(f"并入更省的原因：工资部分扣除没用完（全年应纳税所得额 {yuan(c.wage_taxable)}），并入能把它抵掉。")
        zone = zone_report(c.bonus)
        out.append("临界：" + zone[0].lstrip("⚠ "))
        if c.dead_zone:
            out += list(c.fixes)
        out.append(POLICY_BONUS + "。")
    if not c:
        out.append("年终奖：这次没算。如有年终奖（含 13 薪），要比较单独计税和并入综合所得两种方式，给出金额再算。")
    if p.sixty_k:
        out.append(POLICY_60K + "；员工可以选择不适用，单位要按规定确认。")
    if p.first_job:
        out.append(POLICY_FIRST + "；员工要向单位作出今年首次就业的书面承诺，单位才能这样预扣。")
    elif p.start > 1:
        out.append("如果今年入职前没领过工资（如应届生），属于首次就业，减除费用从 1 月起算，个税会更少，"
                   "加 --first-job 重算并向单位承诺首次就业。")
    if first.excess:
        out.append(f"公积金超 12%：个人每月实缴 {yuan(first.hf_paid)} 元，只有 {yuan(first.hf_deduct)} 元（基数×12%）能税前扣除，"
                   f"超出的 {yuan(first.hf_paid - first.hf_deduct)} 元不能扣；单位超过 12% 缴存的部分每月 {yuan(first.excess)} 元"
                   f"要并入个人当月工资计税（按单位比例同个人假设）。缴存基数也不能超过当地上年职工月平均工资 3 倍，"
                   f"超过的部分同样不能扣，以当地公布为准（财税〔2006〕10号）。")
    if any(p.other.values()):
        out.append(POLICY_PENSION + "。")
    for a in p.assumptions:
        if ("按 0 算" in a or "假设" in a or a.startswith("注意")) and "超过 12%" not in a:
            out.append("要你确认：" + a.lstrip("- ") + ("" if a.endswith("。") else "。"))
    out.append(POLICY_SI + "。")
    out.append(POLICY_SETTLE + "。")
    return out


def text(res: Result) -> str:
    return "\n".join(["【回答要点】（整段抄进回答正文，不放代码块）", *[f"- {x}" for x in points(res)]])
