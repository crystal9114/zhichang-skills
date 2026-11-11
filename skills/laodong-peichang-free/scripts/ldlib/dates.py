"""日期与年限：工作年限拆成年、月、日；经济补偿月数；工作日计数。全部纯函数。"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from .errors import fail

LCL_START = date(2008, 1, 1)   # 劳动合同法施行日


def parse(text: object, field: str) -> date:
    if isinstance(text, date):
        return text
    s = str(text or "").strip()
    m = re.fullmatch(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", s)
    if not m:
        raise fail("E03", f"「{field}」不是日期：{s or '（空）'}", "写成 2024-03-15 这种格式；只记得月份的，问清是几号，或写当月 1 日并在假设里注明", 3)
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        raise fail("E03", f"「{field}」日期不存在：{s}", "核对月份和日子（比如 2 月没有 30 日）", 3) from None


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


@dataclass(frozen=True)
class Span:
    years: int
    months: int
    days: int

    def text(self) -> str:
        parts = ([f"{self.years}年"] if self.years else []) + ([f"{self.months}个月"] if self.months else [])
        if self.days:
            parts.append(("零" if parts else "") + f"{self.days}天")
        return "".join(parts) or "0天"


def span(start: date, end_inclusive: date) -> Span:
    """start 当天到 end_inclusive 当天（含两头）的年、月、日。2021-03-15 到 2026-03-14 = 5 年 0 月 0 天。
    与 Excel 的 DATEDIF(start, end+1, "Y"/"YM"/"MD") 一致。"""
    end = end_inclusive + timedelta(days=1)
    if end <= start:
        return Span(0, 0, 0)
    total = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        total -= 1
    anchor = add_months(start, total)
    while anchor > end:          # 月末日子对不齐时退一个月
        total -= 1
        anchor = add_months(start, total)
    return Span(total // 12, total % 12, (end - anchor).days)


def comp_months(s: Span) -> float:
    """劳动合同法第四十七条：每满一年一个月；六个月以上不满一年按一年；不满六个月给半个月。"""
    if s.months >= 6:
        return s.years + 1.0
    if s.months > 0 or s.days > 0:
        return s.years + 0.5
    return float(s.years)


def old_comp_months(s: Span) -> float:
    """2008 年前的旧口径（劳部发〔1994〕481 号）：每满一年一个月，不满一年按一年。"""
    return float(s.years + (1 if (s.months or s.days) else 0))


def workdays(start: date, end_inclusive: date) -> int:
    """周一到周五的天数（与 Excel NETWORKDAYS 不带假日表时一致）。"""
    if end_inclusive < start:
        return 0
    n, d = 0, start
    while d <= end_inclusive:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return n


def whole_months_and_rest(start: date, end_inclusive: date) -> tuple[int, date | None]:
    """整月数 + 零头起始日（没有零头返回 None）。用于二倍工资、违法试用期这种「按月、零头按日」的期间。"""
    if end_inclusive < start:
        return 0, None
    n = 0
    while add_months(start, n + 1) - timedelta(days=1) <= end_inclusive:
        n += 1
    rest = add_months(start, n)
    return n, (rest if rest <= end_inclusive else None)


def plus_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:           # 2 月 29 日
        return d.replace(year=d.year + n, day=28)
