"""数据结构：单项结果、整案结果。金额一律 Decimal，只在每项最后一步四舍五入到分。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(x: Decimal | float | int) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(x: Decimal | float | int) -> str:
    return f"{money(x):,.2f}"


@dataclass(frozen=True)
class Limitation:
    status: str              # 未过 / 临近 / 已过 / 部分已过
    deadline: date | None
    note: str


@dataclass
class Item:
    key: str
    title: str
    laws: tuple[str, ...]              # references/laws.md 里的编号
    amount: Decimal
    formula_text: str                  # 带数的一行算式
    limitation: Limitation
    claim: bool = True                 # 是否计入「可主张合计」
    detail: tuple[str, ...] = ()       # 年限折算、封顶判断这类过程
    doubts: tuple[str, ...] = ()       # 存疑、地方口径
    barred: bool = False               # 本来适用、但已过仲裁时效


@dataclass
class Result:
    facts: list[str]                                   # 按什么事实算的（回显）
    items: list[Item]
    scenarios: list[tuple[str, Decimal, str]]          # (情形, 金额, 算式)
    reason_confirmed: bool = True
    assumptions: list[str] = field(default_factory=list)
    doubts: list[str] = field(default_factory=list)    # 整案层面的存疑和地方口径
    questions: list[tuple[str, str]] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    rough: list[str] = field(default_factory=list)     # 粗算时的停止情形说明
    guessed: bool = False                              # 入职日或离职日是反推/默认的
    notes: list[str] = field(default_factory=list)     # 结论下面必须说的话（如「主动辞职没有 N」）
    lead: object = None                                # ldlib.lead.Lead：回答开头照抄、还要问（逐条照抄）

    @property
    def claimed(self) -> list[Item]:
        return [i for i in self.items if i.claim and i.amount > 0]

    @property
    def barred(self) -> list[Item]:
        return [i for i in self.items if i.barred and i.amount > 0]

    @property
    def total(self) -> Decimal:
        return money(sum((i.amount for i in self.claimed), Decimal(0)))
