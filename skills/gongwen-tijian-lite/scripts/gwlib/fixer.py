"""一键改格式：只动字体、字号、对齐、缩进、行距、页边距、页码，不改任何文字。需要 python-docx。"""
from __future__ import annotations

import os
import shutil

from . import checker, report
from .docx_read import _body_blocks, _iter_runs, _run_text, q
from .errors import GwError
from .structure import LEVEL_RES, analyze, heading_span
from .units import text_em

LEVEL_FONT = {1: "黑体", 2: "楷体_GB2312", 3: "仿宋_GB2312", 4: "仿宋_GB2312"}
BODY, TITLE = "仿宋_GB2312", "方正小标宋简体"


def _need_docx():
    try:
        import docx  # noqa: F401
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        return docx, OxmlElement, qn
    except ImportError as e:
        raise GwError("E07") from e


def _text_of(p) -> str:
    return "".join(_run_text(r) for r in _iter_runs(p))


def _child(parent, tag: str, qn, OxmlElement, first: bool = False):
    el = parent.find(qn(tag))
    if el is None:
        el = OxmlElement(tag)
        parent.insert(0, el) if first else parent.append(el)
    return el


def _set_run(r, font, size, qn, OxmlElement):
    rpr = r.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        r.insert(0, rpr)
    for tag in ("w:rStyle",):
        pass
    rf = _child(rpr, "w:rFonts", qn, OxmlElement, first=True)
    for a in list(rf.attrib):
        del rf.attrib[a]
    for k in ("w:ascii", "w:hAnsi", "w:eastAsia"):
        rf.set(qn(k), font)
    for tag in ("w:sz", "w:szCs"):
        _child(rpr, tag, qn, OxmlElement).set(qn("w:val"), str(int(size * 2)))
    for tag in ("w:b", "w:bCs"):
        el = rpr.find(qn(tag))
        if el is not None:
            rpr.remove(el)
    col = rpr.find(qn("w:color"))
    if col is not None:
        rpr.remove(col)


def _set_ppr(p, qn, OxmlElement, jc: str, first=0, left=0, right=0, line=579):
    ppr = _child(p, "w:pPr", qn, OxmlElement, first=True)
    _child(ppr, "w:jc", qn, OxmlElement).set(qn("w:val"), jc)
    ind = _child(ppr, "w:ind", qn, OxmlElement)
    for a in list(ind.attrib):
        del ind.attrib[a]
    ind.set(qn("w:firstLineChars"), str(int(first * 100)))
    ind.set(qn("w:leftChars"), str(int(left * 100)))
    ind.set(qn("w:rightChars"), str(int(right * 100)))
    sp = _child(ppr, "w:spacing", qn, OxmlElement)
    for a in list(sp.attrib):
        del sp.attrib[a]
    sp.set(qn("w:line"), str(line))
    sp.set(qn("w:lineRule"), "exact")
    sp.set(qn("w:before"), "0")
    sp.set(qn("w:after"), "0")
    order = ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "numPr", "pBdr", "shd", "tabs", "spacing", "ind", "jc"]
    kids = list(ppr)
    kids.sort(key=lambda e: order.index(e.tag.split("}")[1]) if e.tag.split("}")[1] in order else 99)
    for k in kids:
        ppr.remove(k)
    for k in kids:
        ppr.append(k)


def _fonts_for(p, font_head, font_body, size, span, qn, OxmlElement):
    pos = 0
    for r in _iter_runs(p):
        t = _run_text(r)
        _set_run(r, font_head if pos < span else font_body, size, qn, OxmlElement)
        pos += len(t)


def _fix_section(sec, qn, OxmlElement):
    from docx.shared import Mm
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.orientation = 0
    sec.top_margin, sec.bottom_margin, sec.left_margin, sec.right_margin = Mm(37), Mm(35), Mm(28), Mm(26)
    g = _child(sec._sectPr, "w:docGrid", qn, OxmlElement)
    g.set(qn("w:type"), "linesAndChars")
    g.set(qn("w:linePitch"), "579")
    g.set(qn("w:charSpace"), "-842")


def _footer(doc, sec, qn, OxmlElement):
    doc.settings.odd_and_even_pages_header_footer = True
    sec.different_first_page_header_footer = False
    for kind, ft in (("default", sec.footer), ("even", sec.even_page_footer)):
        ft.is_linked_to_previous = False
        p = ft.paragraphs[0]._p
        for ch in list(p):
            p.remove(ch)
        jc = "right" if kind == "default" else "left"
        _set_ppr(p, qn, OxmlElement, jc, left=1 if jc == "left" else 0, right=1 if jc == "right" else 0, line=280)
        for kind2, txt in (("t", "— "), ("begin", None), ("instr", " PAGE "), ("separate", None), ("t", "1"), ("end", None), ("t", " —")):
            r = OxmlElement("w:r")
            p.append(r)
            _set_run(r, "宋体", 14, qn, OxmlElement)
            if kind2 == "t":
                t = OxmlElement("w:t")
                t.text = txt
                t.set(qn("xml:space"), "preserve")
                r.append(t)
            elif kind2 == "instr":
                t = OxmlElement("w:instrText")
                t.text = txt
                t.set(qn("xml:space"), "preserve")
                r.append(t)
            else:
                fc = OxmlElement("w:fldChar")
                fc.set(qn("w:fldCharType"), kind2)
                r.append(fc)


def fix_file(src: str, out: str | None, dtype: str | None) -> str:
    docx, OxmlElement, qn = _need_docx()
    if not src.lower().endswith(".docx"):
        raise GwError("E02", "一键改只支持 .docx；txt 没有格式可改，请先粘进 Word")
    doc0, before, _m, dt = checker.run_check(src, dtype)
    lay = analyze(doc0)
    out = out or os.path.join("out", os.path.splitext(os.path.basename(src))[0] + "-已改格式.docx")
    if os.path.abspath(out) == os.path.abspath(src):
        raise GwError("E09", "输出文件不能覆盖原文件")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        shutil.copyfile(src, out)
        d = docx.Document(out)
    except OSError as e:
        raise GwError("E09", str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise GwError("E03", f"{type(e).__name__}") from e
    body = d.element.body
    nodes = [p for p, _t in _body_blocks(body) if _text_of(p).strip() or p.find(f".//{q('drawing')}") is not None
             or p.find(f".//{q('pict')}") is not None]
    by = {p.idx: p for p in doc0.paras}
    if len(nodes) != len(doc0.paras) or any(_text_of(n) != by[i + 1].text for i, n in enumerate(nodes)):
        raise GwError("E10", "段落对不上号，为避免改坏文件已停止；请只按体检清单手改")
    for sec in d.sections:
        _fix_section(sec, qn, OxmlElement)
    _footer(d, d.sections[0], qn, OxmlElement)
    d.styles["Normal"].font.size = docx.shared.Pt(16)
    date_w = text_em(by[lay.date].text.strip()) if lay.date else 0
    for i, n in enumerate(nodes):
        idx = i + 1
        role, p = lay.role(idx), by[idx]
        if role in ("table", "head") or p.has_drawing and not p.text.strip():
            continue
        t = p.text
        if role == "title":
            _set_ppr(n, qn, OxmlElement, "center", line=640)
            _fonts_for(n, TITLE, TITLE, 22, 0, qn, OxmlElement)
        elif role == "recipient":
            _set_ppr(n, qn, OxmlElement, "left")
            _fonts_for(n, BODY, BODY, 16, 0, qn, OxmlElement)
        elif role == "attach_page":
            first = idx in lay.att_pages
            _set_ppr(n, qn, OxmlElement, "left" if first else "both", first=0 if first else 2)
            _fonts_for(n, "黑体" if first else BODY, BODY, 16, len(t) if first else 0, qn, OxmlElement)
        elif role == "date":
            _set_ppr(n, qn, OxmlElement, "right", right=4)
            _fonts_for(n, BODY, BODY, 16, 0, qn, OxmlElement)
        elif role == "signature":
            right = max(0.0, 4 - (text_em(t.strip()) - date_w) / 2) if date_w else 4
            _set_ppr(n, qn, OxmlElement, "right", right=round(right, 2))
            _fonts_for(n, BODY, BODY, 16, 0, qn, OxmlElement)
        elif role == "att_note":
            _set_ppr(n, qn, OxmlElement, "left", left=2 if idx == lay.att_notes[0] else 5)
            _fonts_for(n, BODY, BODY, 16, 0, qn, OxmlElement)
        elif role == "note":
            _set_ppr(n, qn, OxmlElement, "left", left=2)
            _fonts_for(n, BODY, BODY, 16, 0, qn, OxmlElement)
        elif role == "footer_block":
            _set_ppr(n, qn, OxmlElement, "left", left=1)
            _fonts_for(n, BODY, BODY, 14, 0, qn, OxmlElement)
        else:
            info = lay.levels.get(idx)
            span = heading_span(p, info) if info else 0
            head_font = LEVEL_FONT[info[0]] if info else BODY
            _set_ppr(n, qn, OxmlElement, "both", first=2)
            _fonts_for(n, head_font, BODY, 16, span, qn, OxmlElement)
    try:
        d.save(out)
    except OSError as e:
        raise GwError("E09", str(e)) from e
    doc1, after, manual, _dt = checker.run_check(out, dtype)
    if [p.text for p in doc1.paras] != [p.text for p in doc0.paras]:
        os.remove(out)
        raise GwError("E10", "改完后文字和原文不一致，已删除结果文件；请只按体检清单手改")
    b = [i for i in before if i.sev != "人工"]
    a = [i for i in after if i.sev != "人工"]
    done = len(b) - len(a)
    head = (f"【改格式结论】已在副本「{os.path.basename(out)}」上改完版式（文字一个字没动）："
            f"体检问题由 {len(b)} 处降到 {len(a)} 处，版式类处理了 {max(done, 0)} 处；"
            f"剩下 {len(a)} 处要改文字或要你定，见下面清单。原文件未改动。")
    return head + "\n\n" + report.render(doc1, after, manual, dt, after_fix=True)
