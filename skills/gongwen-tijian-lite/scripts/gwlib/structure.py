"""把段落分角色：版头、标题、主送机关、正文、层次标题、附件说明、署名、日期、附注、版记、附件页。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import Doc, Para

CN_NUM = "一二三四五六七八九十百"
DOCNO_RE = re.compile(r"[^\s〔\[\(（【{｛]{1,12}\s*[〔\[\(（【{｛]\s*\d{2,4}\s*[〕\]\)）】}｝]\s*[第]?\s*\d{1,5}\s*号")
DATE_ANY = (r"(?:\d{2,4}\s*[年./\-－]\s*\d{1,2}\s*[月./\-－]\s*\d{1,2}\s*日?"
            r"|[〇○零一二三四五六七八九]{2,4}年[一二三四五六七八九十]{1,3}月[一二三四五六七八九十]{1,3}日)")
DATE_LINE = re.compile(r"^\s*" + DATE_ANY + r"\s*$")
ATT_NOTE = re.compile(r"^[\s　]*附件\s*[：:]")
ATT_PAGE = re.compile(r"^[\s　]*附件\s*\d*[\s　]*$")
CC_LINE = re.compile(r"^[\s　]*(抄送|主送)\s*[：:]")
PRINT_LINE = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日\s*印发")
NOTE_LINE = re.compile(r"^[\s　]*[（(].{2,80}[）)][\s　]*$")
ORG_TAIL = re.compile(r"(政府|办公室|办公厅|委员会|局|厅|部|院|校|学校|大学|学院|公司|集团|中心|处|科|所|站|馆|社|协会|总会|银行|党委|党组|支部|委|办|会)$")
REC_RE = re.compile(r"[：:]$")


def cn_to_int(s: str) -> int | None:
    vals = {c: i + 1 for i, c in enumerate("一二三四五六七八九")}
    if not s or "百" in s:
        return None
    if s == "十":
        return 10
    if "十" in s:
        a, _, b = s.partition("十")
        if (a and a not in vals) or (b and b not in vals):
            return None
        return (vals[a] if a else 1) * 10 + (vals[b] if b else 0)
    return vals.get(s) if len(s) == 1 else None


LEVEL_RES = (
    (1, re.compile(rf"^[\s　]*([{CN_NUM}]+)(、)")),
    (2, re.compile(rf"^[\s　]*（([{CN_NUM}]+)）")),
    (3, re.compile(r"^[\s　]*(\d{1,2})([.．])(?!\d)")),
    (4, re.compile(r"^[\s　]*（(\d{1,2})）")),
)
LEVEL_BAD = (
    (1, re.compile(rf"^[\s　]*([{CN_NUM}]+)([.．,，])(?![{CN_NUM}\d])"), "一级序号后应是顿号「、」"),
    (2, re.compile(rf"^[\s　]*\(([{CN_NUM}]+)\)"), "二级序号的括号要用全角「（ ）」"),
    (2, re.compile(rf"^[\s　]*（([{CN_NUM}]+)）[、.．]"), "二级序号「（一）」后面不加标点"),
    (3, re.compile(r"^[\s　]*(\d{1,2})[、，]"), "三级序号写成「1.」，不是「1、」"),
    (3, re.compile(r"^[\s　]*(\d{1,2})[)）](?!\d)"), "三级序号写成「1.」，不是「1)」"),
    (4, re.compile(r"^[\s　]*\((\d{1,2})\)"), "四级序号的括号要用全角「（1）」"),
    (4, re.compile(r"^[\s　]*（(\d{1,2})）[、.．]"), "四级序号「（1）」后面不加标点"),
)


@dataclass
class Layout:
    roles: dict[int, str] = field(default_factory=dict)
    title: list[int] = field(default_factory=list)
    recipient: int | None = None
    main_end: int = 0
    date: int | None = None
    signature: int | None = None
    att_notes: list[int] = field(default_factory=list)
    att_pages: list[int] = field(default_factory=list)
    docno: int | None = None
    head: list[int] = field(default_factory=list)
    footer_blocks: list[int] = field(default_factory=list)
    note: int | None = None
    levels: dict[int, tuple[int, int | None, bool, str]] = field(default_factory=dict)

    def role(self, idx: int) -> str:
        return self.roles.get(idx, "body")


def _is_red(p: Para) -> bool:
    return any((r.color or "").upper() in ("FF0000", "C00000", "E60000", "EE0000") for r in p.runs)


def _big_center(p: Para) -> bool:
    sizes = [r.size for r in p.runs if r.size]
    return p.jc == "center" or bool(sizes and max(sizes) >= 20)


def _is_head_line(p: Para) -> bool:
    t = p.text.strip()
    if len(t) >= 40:
        return False
    return bool(_is_red(p) or re.fullmatch(r"\d{6}", t) or re.fullmatch(r"[特加平]急|(绝密|机密|秘密)★?.*", t)
                or (DOCNO_RE.search(t) and not t.endswith("：")) or re.search(r"文\s*件$", t))


def analyze(doc: Doc) -> Layout:
    lay = Layout()
    free = [p for p in doc.paras if not p.in_table]
    for p in doc.paras:
        if p.in_table:
            lay.roles[p.idx] = "table"
    att_start = next((k for k, p in enumerate(free) if k > 2 and ATT_PAGE.match(p.text)), None)
    main = free[:att_start] if att_start is not None else free
    if att_start is not None:
        for p in free[att_start:]:
            lay.roles[p.idx] = "attach_page"
            if ATT_PAGE.match(p.text):
                lay.att_pages.append(p.idx)
    m = len(main)
    if not m:
        return lay
    lay.main_end = main[-1].idx
    i = 0
    while i < m and _is_head_line(main[i]):
        lay.roles[main[i].idx] = "head"
        lay.head.append(main[i].idx)
        if DOCNO_RE.search(main[i].text) and lay.docno is None:
            lay.docno = main[i].idx
        i += 1
    if i < m:
        first = main[i]
        t0 = first.text.strip()
        if not (REC_RE.search(t0) and len(t0) <= 100):
            lay.title.append(first.idx)
            j = i + 1
            while j < m and len(lay.title) < 3:
                p = main[j]
                t = p.text.strip()
                if _big_center(p) and _big_center(first) and len(t) <= 40 and "。" not in t and not REC_RE.search(t):
                    lay.title.append(p.idx)
                    j += 1
                else:
                    break
            i = j
        for idx in lay.title:
            lay.roles[idx] = "title"
    if i < m:
        t = main[i].text.strip()
        if REC_RE.search(t) and len(t) <= 120 and "。" not in t and not ATT_NOTE.match(t) \
                and not any(rx.match(t) for _, rx in LEVEL_RES):
            lay.recipient = main[i].idx
            lay.roles[main[i].idx] = "recipient"
            i += 1
    body_start = i
    k = m - 1
    while k >= body_start and (CC_LINE.match(main[k].text) or PRINT_LINE.search(main[k].text)):
        lay.roles[main[k].idx] = "footer_block"
        lay.footer_blocks.append(main[k].idx)
        k -= 1
    while k >= body_start and ATT_NOTE.match(main[k].text):
        k -= 1  # 附件说明排在日期后面的错位写法，仍要能找到日期；角色稍后统一标
    if k >= body_start and NOTE_LINE.match(main[k].text) \
            and not re.match(r"^[\s　]*[（(][一二三四五六七八九十\d]+[）)]", main[k].text):
        lay.roles[main[k].idx] = "note"
        lay.note = main[k].idx
        k -= 1
    if k >= body_start and DATE_LINE.match(main[k].text):
        lay.date = main[k].idx
        lay.roles[main[k].idx] = "date"
        k -= 1
        if k >= body_start:
            t = main[k].text.strip()
            if len(t) <= 40 and not re.search(r"[。！？；：:]$", t) and not ATT_NOTE.match(t) \
                    and (ORG_TAIL.search(t) or main[k].jc in ("right", "center")) \
                    and not any(rx.match(t) for _, rx in LEVEL_RES):
                lay.signature = main[k].idx
                lay.roles[main[k].idx] = "signature"
                k -= 1
    # 附件说明：以「附件：」开头，后面缩进的续行也算
    pos = {p.idx: n for n, p in enumerate(main)}
    for p in main:
        if ATT_NOTE.match(p.text) and lay.roles.get(p.idx) is None:
            lay.roles[p.idx] = "att_note"
            lay.att_notes.append(p.idx)
            n = pos[p.idx] + 1
            while n < m and lay.roles.get(main[n].idx) is None and len(main[n].text.strip()) <= 80 \
                    and re.match(r"^([\s　]+\S|\d{1,2}[.．、]\s*\S)", main[n].text) \
                    and not any(rx.match(main[n].text) for lv, rx in LEVEL_RES if lv in (1, 2, 4)) \
                    and (n > body_start):
                lay.roles[main[n].idx] = "att_note"
                lay.att_notes.append(main[n].idx)
                n += 1
    for p in main:
        if lay.roles.get(p.idx) is not None:
            continue
        for lvl, rx in LEVEL_RES:
            mt = rx.match(p.text)
            if mt:
                val = cn_to_int(mt.group(1)) if lvl in (1, 2) else int(mt.group(1))
                lay.levels[p.idx] = (lvl, val, True, "")
                break
        else:
            for lvl, rx, why in LEVEL_BAD:
                mt = rx.match(p.text)
                if mt and len(p.text.strip()) > 3:
                    val = cn_to_int(mt.group(1)) if lvl in (1, 2) else int(mt.group(1))
                    lay.levels[p.idx] = (lvl, val, False, why)
                    break
    return lay


def heading_span(p: Para, info: tuple[int, int | None, bool, str]) -> int:
    """层次标题占的字数：序号加标题语到第一个句读为止，整段是短句就整段，长段只算序号。"""
    t = p.text.rstrip()
    stripped = t.lstrip(" 　")
    lead = len(t) - len(stripped)
    cut = len(stripped)
    for mark in ("。", "；", "：", "！", "？"):
        pos = stripped.find(mark)
        if 0 <= pos < cut:
            cut = pos
    mt = None
    for lv, rx in LEVEL_RES:
        if lv == info[0]:
            mt = rx.match(t)
    tok = (len(mt.group(0)) - lead) if mt else 0
    if cut == len(stripped) and len(stripped) > 40:
        cut = tok
    return lead + max(cut, tok)
