"""参考文献的数据结构、常量和小工具。只用标准库。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

DATA = Path(__file__).resolve().parent / "data"

# 文献类型标识（两版共有的 + 2025 新增 PP；EB 在 2015 是电子公告，在 2025 是网站、网页）
TYPE_NAMES: Dict[str, str] = {
    "M": "图书/专著", "C": "会议录/会议论文", "G": "汇编", "N": "报纸", "J": "期刊",
    "D": "学位论文", "R": "报告", "S": "标准", "P": "专利", "DB": "数据库",
    "CP": "计算机程序", "EB": "电子公告/网页", "A": "档案", "CM": "地图/舆图",
    "DS": "数据集", "PP": "预印本", "Z": "其他",
}
TYPES_2015 = set(TYPE_NAMES) - {"PP"}
TYPES_2025 = set(TYPE_NAMES)
CARRIERS_2015 = {"MT", "DK", "CD", "OL"}
CARRIERS_2025 = CARRIERS_2015 | {"MM"}

# 常见的错写 → 正确代码
TYPE_ALIASES: Dict[str, str] = {
    "学位论文": "D", "硕士论文": "D", "博士论文": "D", "THESIS": "D", "DISSERTATION": "D",
    "期刊": "J", "图书": "M", "专著": "M", "BOOK": "M", "会议": "C", "报纸": "N",
    "标准": "S", "专利": "P", "报告": "R", "网页": "EB", "网站": "EB", "WEB": "EB",
    "ONLINE": "EB", "预印本": "PP", "数据集": "DS",
}

CJK = re.compile(r"[㐀-鿿぀-ヿ豈-﫿]")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s，。；、]+[^\s，。；、.,;)\]）]", re.I)
DOI_RE = re.compile(r"(?:DOI\s*[:：]?\s*|https?://(?:dx\.)?doi\.org/)(10\.\d{4,9}/[^\s，；。]+?)(?=[.。,，;；]?\s*$|[.。,，;；]?\s+)", re.I)
DOI_VALID = re.compile(r"^10\.\d{4,9}/\S+$")
DATE_RE = re.compile(r"(\d{4})\s*[-–—/年.]\s*(\d{1,2})\s*[-–—/月.]\s*(\d{1,2})日?")


@dataclass
class Issue:
    """一条问题。level：改＝脚本已改好；补＝缺信息要买家补；核＝可疑要买家核对；问＝要看学校/期刊规定。"""
    level: str
    field: str
    msg: str


@dataclass
class Ref:
    raw: str
    no: Optional[int] = None            # 原列表里的序号
    lang: str = "zh"                     # zh / en
    authors: List[str] = field(default_factory=list)
    had_etal: bool = False
    title: str = ""
    subtitle_no: str = ""                # 标准号、专利号、报告编号（题名后「：xxx」）
    type: str = ""
    carrier: str = ""
    other_resp: str = ""                 # 「张三，译」这类其他责任者
    container_authors: List[str] = field(default_factory=list)
    container: str = ""                  # 刊名、报纸名、文集名、会议名
    analytic: bool = False               # 是否有「//」
    edition: str = ""
    place: str = ""
    publisher: str = ""
    year: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    date: str = ""                       # 报纸出版日期、专利公告日期、报告发布日期
    update_date: str = ""                # 电子资源创建/更新日期
    cite_date: str = ""                  # 引用日期
    url: str = ""
    doi: str = ""
    pid: str = ""                        # CSTR 等其他永久标识符原文
    version: str = ""                    # 数据集、预印本版本
    parsed: bool = True                  # 结构有没有解析成功
    source_style: str = "gb"             # gb / apa
    year_first: bool = False             # 原文是著者-出版年制写法
    issues: List[Issue] = field(default_factory=list)

    def add(self, level: str, fld: str, msg: str) -> None:
        if not any(i.level == level and i.field == fld and i.msg == msg for i in self.issues):
            self.issues.append(Issue(level, fld, msg))

    @property
    def online(self) -> bool:
        return self.carrier == "OL"


def has_cjk(s: str) -> bool:
    return bool(CJK.search(s or ""))


def norm_date(s: str) -> str:
    """2013-3-6、2013年3月6日、2013/03/06 → 2013-03-06；不是日期原样返回。"""
    m = DATE_RE.search(s or "")
    if not m:
        return (s or "").strip()
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def load_tsv(name: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    p = DATA / name
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "\t" not in line:
            continue
        k, v = line.split("\t", 1)
        out[k.strip()] = v.strip()
    return out
