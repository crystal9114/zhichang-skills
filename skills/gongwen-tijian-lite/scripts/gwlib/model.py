"""体检用的数据结构：文档、段落、问题。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Run:
    text: str
    font: str | None = None      # 归一后的字体族，None 表示文件里没指定
    size: float | None = None    # 磅
    bold: bool = False
    color: str | None = None     # 十六进制，None/auto 视为黑


@dataclass
class Para:
    idx: int                     # 第几段（只数非空段，从 1 起）
    text: str
    runs: list[Run] = field(default_factory=list)
    jc: str = "left"             # left / center / right / both
    left_em: float = 0.0         # 左缩进，单位：字
    right_em: float = 0.0
    first_em: float = 0.0        # 首行缩进（负数为悬挂）
    line_pt: float | None = None  # 行距磅数（固定值/最小值），倍数行距为 None
    line_rule: str = "auto"      # auto / exact / atLeast
    line_mult: float = 1.0
    before_pt: float = 0.0
    after_pt: float = 0.0
    in_table: bool = False
    has_drawing: bool = False
    has_numpr: bool = False
    page_break_before: bool = False
    raw_text_len: int = 0
    node: object = None          # 原始 XML 节点（只读，供一键改定位）

    def chars(self) -> list[tuple[str, str | None, float | None, bool]]:
        out = []
        for r in self.runs:
            for ch in r.text:
                out.append((ch, r.font, r.size, r.bold))
        return out


@dataclass
class FooterInfo:
    kind: str                    # default / even / first
    text: str                    # PAGE 域用 # 代替
    has_page: bool
    jc: str = "left"
    left_em: float = 0.0
    right_em: float = 0.0
    font: str | None = None
    size: float | None = None


@dataclass
class Section:
    w_mm: float
    h_mm: float
    top: float
    bottom: float
    left: float
    right: float
    landscape: bool = False
    grid_type: str | None = None
    line_pitch: int | None = None   # 二十分之一磅
    char_space: int | None = None   # 四千零九十六分之一磅
    title_pg: bool = False
    footers: list[FooterInfo] = field(default_factory=list)
    mirror: bool = False


@dataclass
class Doc:
    kind: str                    # docx / txt
    paras: list[Para]
    sections: list[Section] = field(default_factory=list)
    even_odd: bool = False
    base_size: float = 10.5      # Normal 样式字号，文档网格的字宽基准
    filename: str = ""


@dataclass
class Issue:
    rule: str
    sev: str                     # 必改 / 建议 / 人工
    cat: str
    what: str
    clause: str
    fix: str
    paras: list[int] = field(default_factory=list)
    snippet: str = ""
    prio: int = 50
