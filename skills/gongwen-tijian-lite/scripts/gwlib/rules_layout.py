"""页面、行数字数、页码。"""
from __future__ import annotations

import math
import re
from collections import Counter

from .clauses import make
from .model import Doc, Issue, Section
from .structure import Layout
from .util import dominant, size_is

PT_PER_MM = 72 / 25.4


def _body_paras(doc: Doc, lay: Layout):
    return [p for p in doc.paras if lay.role(p.idx) == "body" and p.idx not in lay.levels and len(p.text.strip()) >= 20]


def check_page(doc: Doc, lay: Layout) -> list[Issue]:
    out: list[Issue] = []
    multi = len(doc.sections) > 1
    body = _body_paras(doc, lay)
    for n, sec in enumerate(doc.sections, 1):
        tag = f"第{n}节：" if multi else ""
        if abs(sec.w_mm - 210) > 1 or abs(sec.h_mm - 297) > 1 or sec.landscape:
            out.append(make("G01", f"{tag}纸张是 {sec.w_mm:.0f}×{sec.h_mm:.0f}mm{'（横向）' if sec.landscape else ''}，应为 A4 纵向 210×297mm"))
        diffs = []
        for name, val, want in (("上", sec.top, 37), ("下", sec.bottom, 35), ("左", sec.left, 28), ("右", sec.right, 26)):
            if abs(val - want) > 1.2:
                diffs.append(f"{name}边距 {val:.1f}mm（应为 {want}±1mm）")
        if diffs:
            out.append(make("G02", tag + "；".join(diffs)))
        out.extend(_grid(sec, body, doc, tag))
        if n == 1:
            break
    return out


def _grid(sec: Section, body, doc: Doc, tag: str) -> list[Issue]:
    text_w = (sec.w_mm - sec.left - sec.right) * PT_PER_MM
    text_h = (sec.h_mm - sec.top - sec.bottom) * PT_PER_MM
    sizes = Counter(dominant(p)[1] for p in body if dominant(p)[1])
    body_size = sizes.most_common(1)[0][0] if sizes else 16.0
    cpl = lpp = None
    how = ""
    if sec.grid_type in ("linesAndChars", "lines") and sec.line_pitch:
        lpp = text_h / (sec.line_pitch / 20)
        how = f"文档网格行距 {sec.line_pitch / 20:g} 磅"
    if sec.grid_type == "linesAndChars" and sec.char_space is not None:
        cpl = text_w / (doc.base_size + sec.char_space / 4096)
    if lpp is None:
        lines = [p.line_pt for p in body if p.line_rule in ("exact", "atLeast") and p.line_pt]
        if lines:
            pt = Counter(lines).most_common(1)[0][0]
            lpp = text_h / pt
            how = f"固定行距 {pt:g} 磅"
    if cpl is None and body_size:
        cpl = text_w / body_size
    msgs = []
    if lpp is not None and math.floor(lpp + 0.05) != 22:
        msgs.append(f"按{how}，每页约 {lpp:.1f} 行（应为 22 行）")
    if cpl is not None and not 27.7 <= cpl <= 28.5:
        msgs.append(f"每行约 {cpl:.1f} 字（应为 28 字）" + ("，没设文档网格" if not sec.grid_type else ""))
    if msgs:
        return [make("G03", tag + "；".join(msgs))]
    return []


def check_footer(doc: Doc, lay: Layout) -> list[Issue]:
    if not doc.sections:
        return []
    sec = doc.sections[0]
    foots = {f.kind: f for f in sec.footers}
    pages = [f for f in sec.footers if f.has_page]
    if not pages:
        return [make("F01", "页脚里没有页码域（文档没有页码）")]
    out: list[Issue] = []
    odd = foots.get("default") if foots.get("default") and foots["default"].has_page else pages[0]
    txt = odd.text.strip()
    if not re.fullmatch(r"[—―─]\s*#\s*[—―─]", txt):
        if re.fullmatch(r"[-－–‐]\s*#\s*[-－–‐]", txt):
            why = f"页码写成「{txt}」，两侧是短横（半字线），标准要一字线「—」"
        else:
            why = f"页码写成「{txt}」，标准是数字左右各一条一字线「— 1 —」"
        out.append(make("F02", why))
    if odd.font != "宋体" or not size_is(odd.size, 14):
        sz = "未设字号" if odd.size is None else f"{odd.size:g}磅"
        out.append(make("F03", f"页码用的是 {odd.font or '未指定字体'}、{sz}，应为宋体四号（14磅）"))
    even = foots.get("even")
    if doc.even_odd and even and even.has_page:
        ok = odd.jc == "right" and even.jc == "left"
        if not ok:
            out.append(make("F04", f"开了奇偶页不同，但单页页码{_jc(odd.jc)}、双页页码{_jc(even.jc)}（应单页居右、双页居左）"))
    elif doc.even_odd and (not even or not even.has_page):
        out.append(make("F04", "开了奇偶页不同，但双数页的页脚没有页码"))
    else:
        out.append(make("F04", f"没有设「奇偶页不同」，所有页码都{_jc(odd.jc)}（应单页居右空一字、双页居左空一字）"))
    if odd.jc == "right" and odd.right_em < 0.5 and doc.even_odd:
        out.append(make("F04", "单页页码靠右没有空一字（页脚段落右缩进应为 1 字）"))
    if sec.title_pg:
        first = foots.get("first")
        if not first or not first.has_page:
            out.append(make("F05", "设了「首页不同」，首页没有页码"))
    return out


def _jc(jc: str) -> str:
    return {"center": "居中", "right": "居右", "left": "居左", "both": "两端对齐"}.get(jc, jc)
