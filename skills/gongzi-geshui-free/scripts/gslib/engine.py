"""单人逐月累计预扣 + 年终奖两种算法比对。纯计算，不打印；每一步的中间数都留着给 render 写算式。"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .errors import GsError
from .rules import (ANNUAL, HF_RATE_CAP, MONTH_FEE, MONTHLY, YEAR_FEE_60K, annual_tax, bonus_dead_zones,
                    bonus_tax_separate, bracket, in_dead_zone, money)

Z = Decimal("0")
MAX_MONTHLY = Decimal("10000000")     # 单月金额上限：超过多半是多打了 0
MAX_BONUS = Decimal("100000000")


@dataclass(frozen=True)
class Plan:
    """一个人一年在本单位的情况。各 dict 是 月份 → 当月金额，已经展开到每个计税月。"""
    start: int
    end: int
    income: dict[int, Decimal]
    si: dict[int, Decimal]                 # 三险个人（养老、医疗、失业）
    hf: dict[int, Decimal]                 # 公积金个人实缴
    hf_deduct: dict[int, Decimal]          # 公积金个人可税前扣除的部分（≤12%）
    hf_employer_excess: dict[int, Decimal]  # 单位超 12% 部分，要并入工资计税
    special: dict[int, Decimal]
    other: dict[int, Decimal]
    tax_free: dict[int, Decimal]
    first_job: bool = False
    sixty_k: bool = False
    bonus: Decimal = Z
    bonus_month: int = 12
    bonus_mode: str = "separate"           # separate 单独计税 / merge 并入当月工资预扣
    year: int = 2026
    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Month:
    mo: int
    income: Decimal
    excess: Decimal                         # 单位公积金超标并入的计税收入
    bonus_in: Decimal                       # 并入方式时本月并进来的年终奖
    si: Decimal
    hf_paid: Decimal
    hf_deduct: Decimal
    special: Decimal
    other: Decimal
    tax_free: Decimal
    cum_income: Decimal
    cum_tax_free: Decimal
    cum_fee: Decimal
    cum_si: Decimal                          # 累计专项扣除（三险 + 公积金可扣部分）
    cum_special: Decimal
    cum_other: Decimal
    cum_taxable: Decimal
    rate: Decimal
    quick: int
    cum_tax: Decimal
    prev_withheld: Decimal
    tax: Decimal
    bonus_cash: Decimal                      # 本月发的年终奖（到手里要加）
    bonus_tax: Decimal                       # 单独计税的奖金税
    net: Decimal
    fee_note: str


@dataclass(frozen=True)
class BonusCompare:
    bonus: Decimal
    wage_taxable: Decimal                   # 工资部分全年应纳税所得额 W（可为负）
    wage_tax: Decimal
    sep_bonus_tax: Decimal
    sep_rate: Decimal
    sep_quick: int
    sep_total: Decimal
    merge_total: Decimal
    better: str
    saving: Decimal
    dead_zone: tuple[Decimal, Decimal] | None
    fixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Result:
    plan: Plan
    months: tuple[Month, ...]
    jumps: tuple[str, ...]
    compare: BonusCompare | None
    total_tax: Decimal
    total_net: Decimal
    notes: tuple[str, ...] = field(default=())


def check_month(mo: int, what: str) -> int:
    if not 1 <= mo <= 12:
        raise GsError("E03", f"{what}写的是 {mo}，月份只能是 1~12")
    return mo


def check_amount(x: Decimal, what: str, cap: Decimal = MAX_MONTHLY) -> Decimal:
    if x < 0:
        raise GsError("E04", f"{what}是负数（{x}）")
    if x > cap:
        raise GsError("E05", f"{what} {x} 元超出合理范围（上限 {cap}）")
    return x


def fee_of(plan: Plan, mo: int) -> tuple[Decimal, str]:
    """到本月为止的累计减除费用和口径说明。"""
    if plan.sixty_k:
        return YEAR_FEE_60K, "上年 1~12 月都在本单位且全年工资≤6万：1 月起累计减除费用直接按 60000"
    if plan.first_job:
        return MONTH_FEE * mo, f"今年首次就业：减除费用从 1 月起算，5000×{mo}"
    n = mo - plan.start + 1
    return MONTH_FEE * n, f"5000×在本单位{n}个月"


def run(plan: Plan) -> Result:
    rows: list[Month] = []
    jumps: list[str] = []
    cum = dict(income=Z, tax_free=Z, si=Z, special=Z, other=Z)
    withheld = Z
    for mo in range(plan.start, plan.end + 1):
        inc, exc = plan.income[mo], plan.hf_employer_excess[mo]
        b_in = plan.bonus if (plan.bonus > 0 and plan.bonus_mode == "merge" and mo == plan.bonus_month) else Z
        si, hfd, sp, oth, tf = plan.si[mo], plan.hf_deduct[mo], plan.special[mo], plan.other[mo], plan.tax_free[mo]
        cum = dict(income=cum["income"] + inc + exc + b_in, tax_free=cum["tax_free"] + tf, si=cum["si"] + si + hfd,
                   special=cum["special"] + sp, other=cum["other"] + oth)
        fee, note = fee_of(plan, mo)
        raw = cum["income"] - cum["tax_free"] - fee - cum["si"] - cum["special"] - cum["other"]
        taxable = max(Z, raw)
        rate, quick = bracket(taxable, ANNUAL)
        cum_tax = annual_tax(taxable)
        tax = max(Z, money(cum_tax - withheld))
        b_cash = plan.bonus if (plan.bonus > 0 and mo == plan.bonus_month) else Z
        b_tax = bonus_tax_separate(plan.bonus) if (b_cash > 0 and plan.bonus_mode == "separate") else Z
        net = money(inc + b_cash - si - plan.hf[mo] - tax - b_tax)
        row = Month(mo, inc, exc, b_in, si, plan.hf[mo], hfd, sp, oth, tf, cum["income"], cum["tax_free"], fee,
                    cum["si"], cum["special"], cum["other"], taxable, rate, quick, cum_tax, withheld, tax,
                    b_cash, b_tax, net, note)
        if rows:
            jumps += explain_jump(rows[-1], row)
            jumps += explain_net(rows[-1], row)
        rows.append(row)
        withheld = withheld + tax
    total_tax = sum((r.tax + r.bonus_tax for r in rows), Z)
    total_net = sum((r.net for r in rows), Z)
    notes = []
    final = annual_tax(rows[-1].cum_taxable)
    if withheld > final:
        notes.append(f"中途有月份收入低于扣除，按规定当月不退税：全年已预扣 {withheld}，按全年累计应纳 {final}，"
                     f"多出的 {money(withheld - final)} 元在次年 3~6 月年度汇算时申请退回")
    return Result(plan, tuple(rows), tuple(jumps), compare_bonus(plan, rows), money(total_tax), money(total_net),
                  tuple(notes))


def explain_jump(prev: Month, cur: Month) -> list[str]:
    """本月个税比上月多出来时，说清楚是哪一步变了。"""
    if cur.tax <= prev.tax:
        return []
    up = money(cur.tax - prev.tax)
    if cur.rate > prev.rate:
        low = next(lo for lo, _h, r, _q in ANNUAL if r == cur.rate)
        return [f"{cur.mo}月个税比{prev.mo}月多 {y(up)} 元：累计应纳税所得额到 {y(cur.cum_taxable)}，跨过 {low:,} 元，"
                f"税率从 {pct(prev.rate)} 升到 {pct(cur.rate)}（只有超过 {low:,} 的部分按 {pct(cur.rate)}）。"
                f"这是累计预扣法的正常现象，全年总税额不会因此多交，只是前低后高。"]
    if cur.income + cur.bonus_in != prev.income + prev.bonus_in:
        return [f"{cur.mo}月个税比{prev.mo}月多 {y(up)} 元：本月计税收入 {y(cur.income + cur.bonus_in)}"
                f"（上月 {y(prev.income + prev.bonus_in)}）变了，税率仍是 {pct(cur.rate)}。"]
    if prev.cum_taxable == 0 and cur.cum_taxable > 0:
        return [f"{cur.mo}月开始扣税：累计收入超过了累计扣除，此前月份累计应纳税所得额为 0。"]
    same = (cur.excess, cur.si, cur.hf_deduct, cur.special, cur.other, cur.tax_free) == \
        (prev.excess, prev.si, prev.hf_deduct, prev.special, prev.other, prev.tax_free)
    if same and prev.cum_tax > 0 and prev.cum_taxable - (cur.cum_taxable - prev.cum_taxable) < \
            next(lo for lo, _h, r, _q in ANNUAL if r == cur.rate):
        return [f"{cur.mo}月个税比{prev.mo}月多 {y(up)} 元：上月累计刚跨进 {pct(cur.rate)} 档，只有超过部分按新税率；"
                f"本月整月都按 {pct(cur.rate)}，所以又高一截。全年总税额不变。"]
    return [f"{cur.mo}月个税比{prev.mo}月多 {y(up)} 元：扣除项（社保公积金、专项附加、其他扣除）比上月少了。"]


def explain_net(prev: Month, cur: Month) -> list[str]:
    """到手变了、但不是因为个税跳档时（调社保基数、涨薪、扣除变化），把每一项的增减拆开写。"""
    if cur.net == prev.net or cur.bonus_cash or prev.bonus_cash:
        return []
    parts = []
    for name, a, b, sign in (("应发", prev.income, cur.income, 1), ("三险个人", prev.si, cur.si, -1),
                             ("公积金个人", prev.hf_paid, cur.hf_paid, -1), ("个税", prev.tax, cur.tax, -1)):
        if a != b:
            verb = "多" if b > a else "少"
            parts.append(f"{name}从 {y(a)} 变成 {y(b)}（{verb} {y(abs(b - a))}）")
    if not parts or parts == [p for p in parts if p.startswith("个税")]:
        return []
    d = cur.net - prev.net
    return [f"{cur.mo}月到手比{prev.mo}月{'多' if d > 0 else '少'} {y(abs(d))} 元：" + "，".join(parts) + "。"]


def compare_bonus(plan: Plan, rows: list[Month]) -> BonusCompare | None:
    b = plan.bonus
    if b <= 0:
        return None
    last = rows[-1]
    w = (last.cum_income - last.bonus_in) - last.cum_tax_free - last.cum_fee - last.cum_si - last.cum_special \
        - last.cum_other
    wage_tax = annual_tax(w)
    sep_b = bonus_tax_separate(b)
    rate, quick = bracket(b / 12, MONTHLY)
    sep_total = money(wage_tax + sep_b)
    merge_total = annual_tax(w + b)
    better = "单独计税" if sep_total <= merge_total else "并入综合所得"
    dz = in_dead_zone(b)
    return BonusCompare(b, w, wage_tax, sep_b, rate, quick, sep_total, merge_total, better,
                        money(abs(merge_total - sep_total)), dz, dead_zone_fixes(b, w, dz))


def dead_zone_fixes(b: Decimal, w: Decimal, dz: tuple[Decimal, Decimal] | None) -> tuple[str, ...]:
    """奖金落进「多发反而少拿」区间时，两种改法各让员工实际多拿多少。"""
    if not dz:
        return ()
    t, end = dz
    keep_now = b - bonus_tax_separate(b)
    moved = b - t
    extra = annual_tax(w + moved) - annual_tax(w)          # 挪进工资的部分要按工资边际税率交的税
    keep_fix1 = t - bonus_tax_separate(t) + moved - extra
    return (f"改法一：年终奖降到 {y(t)}，多出的 {y(moved)} 元改在当月工资里发。奖金税从 {y(bonus_tax_separate(b))} 降到 "
            f"{y(bonus_tax_separate(t))}，挪进工资的 {y(moved)} 元多交 {y(money(extra))} 元，员工净多拿 {y(money(keep_fix1 - keep_now))} 元。"
            f"公司总支出不变（钱只是换了名目），省的是员工的税。",
            f"改法二：年终奖提到 {y(end)} 以上（公司要多花 {y(money(end - b))} 元，员工税后才追平发 {y(t)} 时的水平）。")


def zone_report(b: Decimal) -> list[str]:
    """只给奖金金额时：在不在临界区间、离下一个临界点多远。"""
    out = []
    dz = in_dead_zone(b)
    if dz:
        t, end = dz
        out.append(f"⚠ {y(b)} 落在 {y(t)}~{y(end)} 的「多发反而少拿」区间：发 {y(t)} 税 {y(bonus_tax_separate(t))}，"
                   f"到手 {y(money(t - bonus_tax_separate(t)))}；发 {y(b)} 税 {y(bonus_tax_separate(b))}，"
                   f"到手 {y(money(b - bonus_tax_separate(b)))}，多发 {y(money(b - t))} 元到手反而少 "
                   f"{y(money((t - bonus_tax_separate(t)) - (b - bonus_tax_separate(b))))} 元。")
        out.append(f"   改法：降到 {y(t)}（多出部分并入工资发），或提到 {y(end)} 以上。")
        return out
    for t, end in bonus_dead_zones():
        if b == t:
            out.append(f"正好落在临界点 {y(t)} 上：这是这一档税后最划算的金额，再多发 1 元税就跳到 "
                       f"{y(bonus_tax_separate(t + 1))}；要多发就直接发到 {y(end)} 以上。")
            return out
        if b < t:
            out.append(f"不在临界区间。往上最近的临界点是 {y(t)}：别发到 {y(t)}~{y(end)} 之间（不含两端），"
                       f"那一段多发反而少拿；现在离 {y(t)} 还有 {y(money(t - b))} 元。")
            return out
    out.append("不在临界区间（已超过最高档临界区间）。")
    return out


def y(x) -> str:
    """金额统一写成千分位两位小数。"""
    return f"{money(Decimal(x)):,.2f}"


def pct(rate: Decimal) -> str:
    return f"{int(rate * 100)}%"


def hf_split(base: Decimal, rate_pct: Decimal) -> tuple[Decimal, Decimal, Decimal, str]:
    """公积金：个人实缴、可扣部分、单位超标并入额（假设单位比例同个人）、说明。"""
    paid = money(base * rate_pct / 100)
    cap = HF_RATE_CAP * 100
    if rate_pct <= cap:
        return paid, paid, Z, ""
    deduct = money(base * HF_RATE_CAP)
    excess = money(paid - deduct)
    return paid, deduct, excess, (
        f"公积金比例 {rate_pct}% 超过 12%：个人每月实缴 {paid}，只有 {deduct}（基数×12%）能税前扣除，"
        f"超出的 {excess} 元不能扣；单位超缴部分要并入个人工资计税，这里按单位比例同为 {rate_pct}% 算，"
        f"每月并入 {excess} 元（财税〔2006〕10号）。缴存基数也不能超过当地上年职工月平均工资 3 倍，以当地公布为准。")
