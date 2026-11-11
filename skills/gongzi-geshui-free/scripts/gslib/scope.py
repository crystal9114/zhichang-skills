"""超出范围的几类所得：固定开头 + 那一类自己的基本算式 + 会改变结果的因素 + 找谁确认。

不并进工资的累计预扣；口径见 references/out-of-scope.md。
"""
from __future__ import annotations

from decimal import Decimal

from .errors import GsError
from .rules import MONTHLY, bracket, money

OPEN = ("这一类（{kind}）不归本技能计算，本技能只算居民个人工资薪金和年终奖；下面给基本算法和方向，"
        "具体以单位和主管税务机关确认为准。")
LABOR = ((Decimal(20000), Decimal("0.2"), 0), (Decimal(50000), Decimal("0.3"), 2000), (None, Decimal("0.4"), 7000))
BUSINESS = ((30000, Decimal("0.05"), 0), (90000, Decimal("0.10"), 1500), (300000, Decimal("0.20"), 10500),
            (500000, Decimal("0.30"), 40500), (None, Decimal("0.35"), 65500))


def y(x) -> str:
    return f"{money(Decimal(x)):,.2f}"


def pick(x: Decimal, table) -> tuple[Decimal, int]:
    for top, rate, quick in table:
        if top is None or x <= top:
            return rate, quick
    raise AssertionError


def need(x: Decimal | None, what: str) -> Decimal:
    if x is None:
        raise GsError("E01", f"这一类要给 {what}", "照 python3 scripts/geshui.py scope -h 的写法补上这个参数")
    return x


def labor(amount: Decimal, kind: str = "劳务报酬") -> list[str]:
    amount = need(amount, "--amount 每次收入")
    if amount <= 800:
        base, how = Decimal(0), f"{y(amount)} 不超过 800，减除费用后为 0"
    elif amount <= 4000:
        base, how = amount - 800, f"{y(amount)} − 800 = {y(amount - 800)}"
    else:
        base, how = amount * Decimal("0.8"), f"{y(amount)} × (1 − 20%) = {y(amount * Decimal('0.8'))}"
    base = max(Decimal(0), base)
    if kind == "稿酬":
        base70 = base * Decimal("0.7")
        tax = money(base70 * Decimal("0.2"))
        calc = f"{how}，× 70% = {y(base70)}，× 20% = {y(tax)} 元"
    else:
        rate, quick = pick(base, LABOR)
        tax = money(base * rate - quick)
        calc = f"{how}，× {int(rate * 100)}%" + (f" − {quick:,}" if quick else "") + f" = {y(tax)} 元"
    return [OPEN.format(kind=kind),
            f"预扣：{calc}；到手 {y(amount - tax)} 元（每次收入单独预扣，同一项目一个月内多次取得的合并为一次）。",
            "不进工资的累计预扣，支付方在扣缴端按「劳务报酬所得」单独申报，次月 15 日内申报缴款；本单位员工的工资不能改成劳务报酬发。",
            f"年度汇算：次年 3 月 1 日至 6 月 30 日，劳务报酬按收入 × 80%（稿酬 × 56%）并入当年综合所得，和工资一起按年度税率表重算，"
            f"多退少补；工资部分在 3% 档以内的，这笔 {y(amount)} 汇算时只按 3% 算，平时多预扣的大部分能退回。",
            "会改变结果的：是不是同一项目同月多次取得、对方给的是税前还是税后金额（税后要反推含税收入）。"]


def business(profit: Decimal, getihu: bool) -> list[str]:
    profit = need(profit, "--profit 全年利润（收入减成本费用）")
    taxable = max(Decimal(0), profit - 60000)
    rate, quick = pick(taxable, BUSINESS)
    tax = money(taxable * rate - quick)
    out = [OPEN.format(kind="经营所得"),
           f"按查账征收、业主没有别的综合所得、没有专项扣除假设：{y(profit)} − 60,000（业主减除费用）= {y(taxable)}，"
           f"× {int(rate * 100)}% − {quick:,} = {y(tax)} 元。",
           "经营所得五级超额累进 5%~35%（3 万以内 5%；3~9 万 10%/1500；9~30 万 20%/10500；30~50 万 30%/40500；"
           "50 万以上 35%/65500），按年计算，按月或按季预缴（季度终了 15 日内），次年 3 月 31 日前汇算清缴。"]
    if getihu:
        out.append(f"个体工商户年应纳税所得额不超过 200 万元的部分减半征收（财政部 税务总局公告2023年第12号，执行到2027年12月31日）："
                   f"{y(tax)} ÷ 2 = {y(money(tax / 2))} 元。")
    else:
        out.append("个人独资企业、合伙企业不适用个体工商户减半政策；投资者给自己发的「工资」不能在经营所得前扣除，要并回利润一起算。")
    out.append("会改变结果的：「赚的」是收入还是利润、成本费用怎么认、是不是核定征收、业主有没有在别处领工资。建议问主管税务机关或会计。")
    return out


def foreign(income: Decimal) -> list[str]:
    income = need(income, "--income 当月工资")
    taxable = max(Decimal(0), income - 5000)
    rate, quick = bracket(taxable, MONTHLY)
    tax = money(taxable * rate - quick)
    return [OPEN.format(kind="外籍人员、非居民个人工资"),
            "先判身份：一个纳税年度在境内累计居住满 183 天的是居民个人，照常累计预扣；不满 183 天的是非居民个人。",
            f"非居民个人按月算、不累计、不能扣专项附加扣除：({y(income)} − 5,000) = {y(taxable)}，按月度税率表 "
            f"× {int(rate * 100)}% − {quick:,} = {y(tax)} 元/月（假设全部是境内工作期间、境内支付）。",
            "会改变结果的：境内居住天数（90 天、183 天两条线）、境内外工作天数和支付地（财政部 税务总局公告2019年第35号）、税收协定。"
            "这几项不同，结果会差很多，建议请税务专业人士确认。",
            "外籍个人以实报实销形式取得的住房补贴、伙食补贴、搬迁费、探亲费、语言训练费、子女教育费等按规定免税，"
            "政策执行到2027年12月31日（财政部 税务总局公告2023年第29号）；和专项附加扣除只能二选一，一个纳税年度内不能变更。"]


def allowance() -> list[str]:
    return [OPEN.format(kind="外籍人员补贴免税"),
            "外籍个人以非现金或实报实销形式取得的住房补贴、伙食补贴、洗衣费、搬迁费、出差补贴、探亲费、语言训练费、子女教育费，"
            "按规定可以免征个人所得税，政策执行到2027年12月31日（财政部 税务总局公告2023年第29号）。",
            "这项优惠和住房租金、子女教育等专项附加扣除只能二选一，一个纳税年度内不能变更。",
            "要合理数额、有凭证、实报实销；直接发现金补贴的不免税。是否适用、凭证要求以单位和主管税务机关确认为准。"]


def avoid() -> list[str]:
    return ["这个不做：把员工工资拆成劳务费或咨询费、拿发票报销冲抵工资、做两套工资表、找人代领，都属于少报工资薪金，"
            "可能被认定为偷逃个税；用别人的发票报销还可能涉及虚开发票。",
            "风险：补缴税款、按日加收万分之五滞纳金、处少缴税款 50% 以上 5 倍以下罚款，情节严重的涉及逃税罪；"
            "单位作为扣缴义务人同样要担责。本单位员工的工资不能改成劳务报酬发。",
            "合法能少交的（能算的用 quick 算出前后对比）：① 年终奖在单独计税和并入之间选省的那个（--bonus）；"
            "② 年终奖避开「多发反而少拿」区间（zones）；③ 专项附加扣除填全（子女教育、婴幼儿照护、赡养老人、房贷利息或房租、继续教育）；"
            "④ 个人养老金每年最多 12000 元税前扣除（--other 1000）；⑤ 公积金在 12% 以内按实际工资基数足额缴（个人部分可税前扣）。"]


def run(kind: str, amount: Decimal | None, profit: Decimal | None, income: Decimal | None, getihu: bool) -> str:
    table = {"labor": lambda: labor(amount), "royalty": lambda: labor(amount, "稿酬"),
             "business": lambda: business(profit, getihu), "foreign": lambda: foreign(income),
             "allowance": allowance, "avoid": avoid}
    lines = table[kind]()
    return "\n".join(["【回答要点】（整段抄进回答正文，不放代码块）", *[f"- {x}" for x in lines],
                      "- 口径核对日期 2026-11-03"])
