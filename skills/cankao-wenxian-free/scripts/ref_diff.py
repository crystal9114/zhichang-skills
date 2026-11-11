"""2015 版列表转 2025 版：逐条判断 GB/T 7714—2015 与 GB/T 7714—2025 的 6 处规则差异命中了哪几处。只用标准库。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from ref_model import Ref
from ref_render import name_parts

PREPRINT_HOSTS = re.compile(r"arxiv\.org|biorxiv\.org|medrxiv\.org|chinaxiv\.org|ssrn\.com|preprints\.org|"
                            r"researchsquare\.com|psyarxiv|osf\.io/preprints|techrxiv\.org", re.I)


@dataclass(frozen=True)
class Rule:
    no: int
    name: str
    old: str
    new: str


RULES: List[Rule] = [
    Rule(1, "西文、拼音姓的大小写", "姓全大写：SMITH J A", "姓首字母大写：Smith J A"),
    Rule(2, "在线文献的引用日期", "所有 /OL 文献都写 [引用日期]",
         "只有网站网页 [EB/OL]、数据集 [DS/OL]、预印本 [PP/OL] 写；[J/OL] [M/OL] [D/OL] 等不写"),
    Rule(3, "标准的标准号位置", "题名: 标准号[S]. 出版地: 出版者, 年.", "标准号 标准名称[S].（编号在前，不著录出版项）"),
    Rule(4, "报告、专利的著录格式", "报告按图书写出版项；专利：题名: 专利号[P]. 公告日期.",
         "报告可写「题名: 报告编号[R]. 发布日期: 页码.」；专利号带国别前缀（如 CN），可加引文页码"),
    Rule(5, "学位论文的引文页码", "引文页码可选", "引文页码有则必备"),
    Rule(6, "新增预印本类型 [PP]", "没有 [PP]，预印本按 [EB/OL] 或 [Z] 著录", "预印本用 [PP/OL]"),
]


@dataclass
class Hits:
    by_rule: Dict[int, List[int]] = field(default_factory=lambda: {r.no: [] for r in RULES})
    notes: Dict[int, List[str]] = field(default_factory=lambda: {r.no: [] for r in RULES})

    def hit(self, rule: int, n: int, note: str) -> None:
        if n not in self.by_rule[rule]:
            self.by_rule[rule].append(n)
            self.notes[rule].append(f"[{n}] {note}")


def is_latin_person(tok: str) -> bool:
    p = name_parts(tok)
    return p is not None and len(p[0]) > 1


def mark_preprint(ref: Ref) -> bool:
    """2015 列表里写成 [EB/OL]、[Z]、[J/OL] 的预印本（网址是预印本平台）→ 2025 改 [PP/OL]。返回是否改了。"""
    if ref.type == "PP":
        return False
    if ref.url and PREPRINT_HOSTS.search(ref.url) and ref.type in ("EB", "Z", "J", ""):
        old = f"[{ref.type}{'/' + ref.carrier if ref.carrier else ''}]" if ref.type else "（无类型标识）"
        ref.type, ref.carrier = "PP", "OL"
        ref.add("改", "类型标识", f"网址是预印本平台，2025 版预印本用 [PP/OL]，原文 {old} 已改")
        return True
    return False


def scan(n: int, ref: Ref, hits: Hits, preprint_changed: bool) -> None:
    """ref 是从 2015 版原文拆出的字段（未排版前），n 是条目序号。"""
    latin = [a for a in ref.authors + ref.container_authors if is_latin_person(a)]
    if latin:
        hits.hit(1, n, f"西文/拼音姓 {len(latin)} 处改为首字母大写")
    if ref.cite_date and ref.online and ref.type not in ("EB", "DS", "PP"):
        hits.hit(2, n, f"[{ref.type}/OL] 的引用日期 [{ref.cite_date}] 删去")
    if ref.type == "S":
        hits.hit(3, n, "标准号移到标准名称前，出版项删去")
    if ref.type == "R":
        hits.hit(4, n, "报告：有报告编号和发布日期的按 2025 写法；原文只有出版项的仍可照出版项著录")
    if ref.type == "P":
        no = ref.subtitle_no or ""
        tip = "专利号已带国别前缀" if re.match(r"\s*[A-Z]{2}", no) else "专利号建议带国别前缀（如 CN），请对照原文补"
        hits.hit(4, n, f"专利：{tip}；引用了具体页的加引文页码")
    if ref.type == "D":
        tip = "原文已有引文页码" if ref.pages else "引用了具体页的要补引文页码"
        hits.hit(5, n, f"学位论文：{tip}")
    if ref.type == "PP" or preprint_changed:
        hits.hit(6, n, "预印本著录为 [PP/OL]，要写引用日期")


def section(hits: Hits) -> List[str]:
    got = [r for r in RULES if hits.by_rule[r.no]]
    miss = [r for r in RULES if not hits.by_rule[r.no]]
    L = ["## 2015 → 2025：6 处规则差异命中情况", "",
         f"命中 {len(got)} 处：" + ("、".join(f"{r.no}. {r.name}" for r in got) if got else "无") + "。",
         "未命中：" + ("、".join(f"{r.no}. {r.name}" for r in miss) if miss else "无") + "。", "",
         "| # | 差异 | GB/T 7714—2015 | GB/T 7714—2025 | 命中条目 |", "|---|---|---|---|---|"]
    for r in RULES:
        nums = "、".join(f"[{x}]" for x in hits.by_rule[r.no]) or "未命中"
        L.append(f"| {r.no} | {r.name} | {r.old} | {r.new} | {nums} |")
    L.append("")
    if not got:
        L.append("这份列表没有碰到 6 处差异里的任何一处：这几条照 2015 版写的格式，在 2025 版下写法不变。")
    for r in got:
        L.append(f"- 第 {r.no} 处（{r.name}）：" + "；".join(hits.notes[r.no]))
    L.append("")
    return L
