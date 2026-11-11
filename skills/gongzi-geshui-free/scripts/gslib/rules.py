"""税率表与计税公式。口径见 references/tax-rules.md，核对日期 2026-11-03。

只放会被计算用到的常数和纯函数，不读文件、不打印。
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# 综合所得年度税率表（累计预扣预缴、并入综合所得都用它）：(下限, 上限, 税率, 速算扣除数)
ANNUAL = (
    (0, 36000, Decimal("0.03"), 0),
    (36000, 144000, Decimal("0.10"), 2520),
    (144000, 300000, Decimal("0.20"), 16920),
    (300000, 420000, Decimal("0.25"), 31920),
    (420000, 660000, Decimal("0.30"), 52920),
    (660000, 960000, Decimal("0.35"), 85920),
    (960000, None, Decimal("0.45"), 181920),
)

# 按月换算后的综合所得税率表（全年一次性奖金单独计税用）
MONTHLY = (
    (0, 3000, Decimal("0.03"), 0),
    (3000, 12000, Decimal("0.10"), 210),
    (12000, 25000, Decimal("0.20"), 1410),
    (25000, 35000, Decimal("0.25"), 2660),
    (35000, 55000, Decimal("0.30"), 4410),
    (55000, 80000, Decimal("0.35"), 7160),
    (80000, None, Decimal("0.45"), 15160),
)

MONTH_FEE = Decimal("5000")          # 每月减除费用
YEAR_FEE_60K = Decimal("60000")      # 国家税务总局公告2020年第19号：上年同单位全年≤6万，本年1月起按6万扣
HF_RATE_CAP = Decimal("0.12")        # 住房公积金个人比例超过 12% 的部分不得税前扣除

# 专项附加扣除每月标准（国发〔2023〕13号起）。脚本不拿它算税，只在表里填的数明显超标时提醒。
SPECIAL_CAPS = {
    "子女教育": Decimal("2000"),      # 每个子女
    "婴幼儿照护": Decimal("2000"),    # 每个 3 岁以下婴幼儿
    "赡养老人": Decimal("3000"),      # 独生子女；非独生每人每月不超过 1500
    "住房贷款利息": Decimal("1000"),
    "住房租金": Decimal("1500"),      # 直辖市、省会等；其他城市 1100 或 800
    "继续教育": Decimal("400"),       # 学历继续教育；职业资格是取得证书当年一次 3600
}

CENT = Decimal("0.01")


def money(x) -> Decimal:
    """四舍五入到分。"""
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def bracket(x: Decimal, table) -> tuple[Decimal, int]:
    """找税率档：下限 < x ≤ 上限（x ≤ 0 落第一档）。返回 (税率, 速算扣除数)。"""
    for low, high, rate, quick in table:
        if high is None or x <= high:
            return rate, quick
    raise AssertionError("税率表没有封顶档")


def annual_tax(taxable: Decimal) -> Decimal:
    """按年度税率表算应纳税额（累计应纳税所得额 ≤ 0 时为 0）。"""
    if taxable <= 0:
        return Decimal("0")
    rate, quick = bracket(taxable, ANNUAL)
    return money(taxable * rate - quick)


def bonus_tax_separate(bonus: Decimal) -> Decimal:
    """全年一次性奖金单独计税：奖金 ÷ 12 找月度税率档，奖金 × 税率 − 速算扣除数（只减一次）。"""
    if bonus <= 0:
        return Decimal("0")
    rate, quick = bracket(bonus / 12, MONTHLY)
    return money(bonus * rate - quick)


def bonus_dead_zones() -> list[tuple[Decimal, Decimal]]:
    """单独计税的「多发反而少拿」区间：从档位临界点 T 起，到税后金额追平 T 的税后金额为止。"""
    zones = []
    for i in range(len(MONTHLY) - 1):
        t = Decimal(MONTHLY[i][1]) * 12
        keep_at_t = t - bonus_tax_separate(t)
        rate, quick = MONTHLY[i + 1][2], MONTHLY[i + 1][3]
        # 超过 T 后到手 = B − (B × rate − quick)；令其等于 keep_at_t
        end = (keep_at_t - quick) / (1 - rate)
        zones.append((t, money(end)))
    return zones


def in_dead_zone(bonus: Decimal) -> tuple[Decimal, Decimal] | None:
    for t, end in bonus_dead_zones():
        if t < bonus < end:
            return t, end
    return None
