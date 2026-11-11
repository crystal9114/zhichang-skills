"""读 references/avg-wage.md 的社平工资表（唯一数据源，改表就改这一处），按城市和解除年份挑数。"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

TABLE = Path(__file__).resolve().parents[2] / "references" / "avg-wage.md"


@lru_cache(maxsize=1)
def rows() -> tuple[dict, ...]:
    out = []
    if not TABLE.is_file():
        return ()
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 10 and cells[1].isdigit() and re.fullmatch(r"\d+", cells[2]):
            out.append({"city": cells[0], "year": int(cells[1]), "value": Decimal(cells[2]), "basis": cells[5],
                        "level": cells[6], "org": cells[7], "date": cells[8], "url": cells[9]})
    return tuple(out)


def norm_city(s: str) -> str:
    return re.sub(r"(市|区|县)$", "", str(s or "").strip())


def lookup(case: dict, leave: date) -> dict:
    need = leave.year - 1
    if case.get("avg_wage") not in (None, ""):
        v = Decimal(str(case["avg_wage"]).replace(",", ""))
        yr = case.get("avg_wage_year") or need
        return {"value": v, "city": norm_city(case.get("city") or "当地"), "level": "买家提供",
                "note": f"买家提供：{yr} 年度当地职工月平均工资 {v} 元", "stale": ""}
    city = norm_city(case.get("city") or "")
    hits = [r for r in rows() if r["city"] == city]
    if not city or not hits:
        return {"value": None, "city": city, "level": "",
                "note": (f"表里没有「{city}」的社平工资" if city else "没写城市") +
                        "，未做三倍封顶判断：月工资较高时请提供当地人社局公布的上年度职工月平均工资（用 --avg-wage 给）"}
    exact = [r for r in hits if r["year"] == need]
    older = sorted((r for r in hits if r["year"] < need), key=lambda r: -r["year"])
    newer = sorted((r for r in hits if r["year"] > need), key=lambda r: r["year"])
    r = (exact or older or newer)[0]
    note = f"{r['year']} 年度 {r['value']} 元/月，{r['basis']}，{r['org']} {r['date']} 公布（{r['level']}），出处 {r['url']}"
    stale = ""
    if r["year"] != need:
        stale = (f"{city} 在 {leave.year} 年解除应该用 {need} 年度的社平工资，表里只有 {r['year']} 年度的 {r['value']} 元；"
                 f"以当地人社局公布的 {need} 年度数为准")
    if r["level"] != "市级原文":
        stale = (stale + "；" if stale else "") + f"{city} 这个数是省级社保口径，市里给经济补偿封顶可能用别的口径，接近封顶线时请核当地人社局公布数"
    return {"value": r["value"], "city": city, "level": r["level"], "note": note, "stale": stale}
