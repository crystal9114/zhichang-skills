"""文字项：标点（GB/T 15834）、数字用法（GB/T 15835）。txt 和 docx 都查。"""
from __future__ import annotations

import re

from .clauses import make
from .model import Doc, Issue
from .structure import Layout, cn_to_int
from .util import snip

CJK = "一-鿿"
QUANT = "个元万亿人天年次条项名位台套件月日周份期家户岁倍米吨"


def _collect(doc: Doc, pat: re.Pattern, skip=lambda p: False):
    hits = []
    for p in doc.paras:
        if skip(p):
            continue
        m = pat.search(p.text)
        if m:
            hits.append((p.idx, m, p.text))
    return hits


def _emit(out: list[Issue], rule: str, what: str, hits, max_show: int = 1, fixed_fix: str | None = None) -> None:
    if not hits:
        return
    idxs = [h[0] for h in hits]
    first = hits[0]
    m = first[1]
    ctx = first[2][max(0, m.start() - 8): m.end() + 8]
    out.append(make(rule, f"{what}（共 {len(idxs)} 段，例：「{snip(ctx, 22)}」）", idxs, ctx, fix=fixed_fix))


def check_punct(doc: Doc, lay: Layout) -> list[Issue]:
    out: list[Issue] = []
    url = re.compile(r"https?://\S+|\S+@\S+\.\S+|\b[\w.-]+\.(?:com|cn|gov|org|net)\b")

    def clean(t: str) -> str:
        return url.sub(" ", t)

    class P:  # 去掉网址邮箱后的文本，避免误报
        pass

    cleaned = []
    for p in doc.paras:
        q = P()
        q.idx, q.text = p.idx, clean(p.text)
        cleaned.append(q)
    fake = type("D", (), {"paras": cleaned})()
    half = re.compile(rf"[{CJK}][,;!?](?!\d)|[{CJK}]:(?!\d)(?![/\\])|[{CJK}]\.(?![\d.a-zA-Z])|[,;:](?=[{CJK}])")
    _emit(out, "P01", "中文句子里夹着半角标点", _collect(fake, half, lambda p: p.idx == lay.recipient))
    par = re.compile(rf"[{CJK}]\(|\)[{CJK}]|\([{CJK}]|[{CJK}]\)")
    hits = [h for h in _collect(fake, par) if not re.match(r"^[\s　]*\([一二三四五六七八九十\d]+\)", h[2])]
    _emit(out, "P01", "括号用了半角「( )」", hits)
    _emit(out, "P02", "用了直引号「\"」或「'」", _collect(fake, re.compile(rf"[{CJK}\w]\"|\"[{CJK}\w]|[{CJK}]'|'[{CJK}]")))
    _emit(out, "P03", "标点重复叠用", _collect(doc, re.compile(r"[，。；：、]{2,}|[！？]{2,}")))
    _emit(out, "P04", "省略号没写成「……」", _collect(doc, re.compile(r"(?<![.。])\.{3,}(?!\.)|。{3,}|(?<!…)…(?!…)")))
    _emit(out, "P05", "破折号没写成「——」", _collect(doc, re.compile(rf"[{CJK}\d]\s*(?:--+|—)\s*[{CJK}]|[{CJK}]—[{CJK}]")))
    bad = []
    for p in doc.paras:
        for a, b in (("《", "》"), ("（", "）")):
            if p.text.count(a) != p.text.count(b):
                bad.append((p.idx, re.search(f"[{a}{b}]", p.text), p.text))
                break
    _emit(out, "P06", "括号或书名号不成对", bad)
    total_open, total_close = sum(p.text.count("“") for p in doc.paras), sum(p.text.count("”") for p in doc.paras)
    if total_open != total_close:
        out.append(make("P06", f"全文弯引号不成对（“ 有 {total_open} 个，” 有 {total_close} 个）"))
    nopunct = []
    for p in doc.paras:
        t = p.text.strip()
        if lay.role(p.idx) == "body" and p.idx not in lay.levels and len(t) >= 25 and not re.search(r"[。！？；：”）》…]$", t) \
                and not re.search(r"[\d.%]$", t):
            nopunct.append((p.idx, re.search(r".$", t), t))
    _emit(out, "P07", "段末没有句号等点号", nopunct)
    return out


def _ints(a: str, b: str):
    def conv(s):
        return int(s) if s.isdigit() else cn_to_int(s)
    return conv(a), conv(b)


def check_numbers(doc: Doc, lay: Layout) -> list[Issue]:
    out: list[Issue] = []
    _emit(out, "X01", "用了全角数字", _collect(doc, re.compile(r"[０-９]+")))
    approx = []
    pat = re.compile(rf"(?<![\d.])([一二三四五六七八九十]|\d)[、，]([一二三四五六七八九十]|\d)(?=[{QUANT}])")
    for p in doc.paras:
        for m in pat.finditer(p.text):
            a, b = _ints(m.group(1), m.group(2))
            if a and b and b == a + 1 and p.text[:m.start()].strip():
                approx.append((p.idx, m, p.text))
                break
    _emit(out, "X02", "相邻两个数表示概数时加了顿号或逗号", approx)
    _emit(out, "X03", "「约」和「左右」重复", _collect(doc, re.compile(rf"(约|大约|大概)\s*\d[\d.,]*\s*[万亿千百]?\s*[{CJK}]{{0,2}}\s*(左右|上下)")))
    _emit(out, "X04", "数值范围用了连字符", _collect(doc, re.compile(
        rf"(?<![\d./\-])\d+(?:\.\d+)?\s*[-－–]\s*\d+(?:\.\d+)?\s*(?:%|％|[{QUANT}]|公里|千米|平方|立方|万|亿)")))
    _emit(out, "X05", "年月日数字和汉字之间有空格", _collect(doc, re.compile(r"\d\s+[年月日]|[年月]\s+\d")))
    _emit(out, "X06", "年份写成汉字数字", _collect(doc, re.compile(r"[〇○零一二三四五六七八九]{4}\s*年"),
                                              skip=lambda p: p.idx == (lay.date or -1) or p.idx in lay.title))
    _emit(out, "X07", "百分数写成汉字", _collect(doc, re.compile(r"百分之[一二三四五六七八九十百零〇]+")))
    _emit(out, "X08", "日期用了点号、横线或斜线", _collect(
        doc, re.compile(r"(?<![\d.])(?:19|20)\d{2}\s*[./\-－]\s*\d{1,2}\s*[./\-－]\s*\d{1,2}(?![\d.])"),
        skip=lambda p: p.idx == (lay.date or -1) or lay.role(p.idx) == "head"))
    return out
