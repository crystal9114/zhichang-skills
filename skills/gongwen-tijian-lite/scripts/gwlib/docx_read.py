"""只用标准库（zipfile + xml）读 docx 里的真实字体、字号、行距、页边距、页码。"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET

from .errors import GwError
from .model import Doc, FooterInfo, Para, Run, Section
from .units import em_of, family, tw_to_mm

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
MAX_TOTAL = 60 * 1024 * 1024


def q(tag: str) -> str:
    return f"{{{W}}}{tag}"


def wattr(el, name: str):
    return None if el is None else el.get(q(name))


def _parse(data: bytes, name: str):
    head = data[:4096].upper()
    if b"<!ENTITY" in head or b"<!DOCTYPE" in head:
        raise GwError("E04", f"{name} 含外部实体声明")
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise GwError("E03", f"{name} 解析失败：{e}") from e


def _toggle(el) -> bool:
    if el is None:
        return False
    v = el.get(q("val"))
    return v not in ("0", "false", "off")


class _Styles:
    def __init__(self, root, theme_ea: str | None):
        self.defaults_r = None
        self.defaults_p = None
        self.styles: dict[str, object] = {}
        self.default_p_style: str | None = None
        self.theme_ea = theme_ea
        if root is None:
            return
        dd = root.find(q("docDefaults"))
        if dd is not None:
            self.defaults_r = dd.find(f"{q('rPrDefault')}/{q('rPr')}")
            self.defaults_p = dd.find(f"{q('pPrDefault')}/{q('pPr')}")
        for st in root.findall(q("style")):
            sid = st.get(q("styleId"))
            self.styles[sid] = st
            if st.get(q("type")) == "paragraph" and st.get(q("default")) == "1":
                self.default_p_style = sid

    def chain(self, sid: str | None) -> list:
        out, seen = [], set()
        while sid and sid in self.styles and sid not in seen:
            seen.add(sid)
            out.append(self.styles[sid])
            b = self.styles[sid].find(q("basedOn"))
            sid = wattr(b, "val")
        return list(reversed(out))

    def rpr_layers(self, pstyle: str | None, rstyle: str | None, direct) -> list:
        layers = [self.defaults_r]
        for st in self.chain(pstyle or self.default_p_style):
            layers.append(st.find(q("rPr")))
        for st in self.chain(rstyle):
            layers.append(st.find(q("rPr")))
        layers.append(direct)
        return [x for x in layers if x is not None]

    def ppr_layers(self, pstyle: str | None, direct) -> list:
        layers = [self.defaults_p]
        for st in self.chain(pstyle or self.default_p_style):
            layers.append(st.find(q("pPr")))
        layers.append(direct)
        return [x for x in layers if x is not None]


def _font_of(layers: list, cjk: bool, theme_ea: str | None) -> str | None:
    name = None
    for rpr in layers:
        rf = rpr.find(q("rFonts"))
        if rf is None:
            continue
        if cjk:
            v = rf.get(q("eastAsia"))
            if v:
                name = v
            elif rf.get(q("eastAsiaTheme")):
                name = theme_ea or name
        else:
            v = rf.get(q("ascii")) or rf.get(q("hAnsi"))
            if v:
                name = v
    return family(name) if name else None


def _size_of(layers: list) -> float | None:
    sz = None
    for rpr in layers:
        v = wattr(rpr.find(q("sz")), "val")
        if v:
            try:
                sz = float(v) / 2
            except ValueError:
                pass
    return sz


def _bold_of(layers: list) -> bool:
    b = False
    for rpr in layers:
        el = rpr.find(q("b"))
        if el is not None:
            b = _toggle(el)
    return b


def _color_of(layers: list) -> str | None:
    c = None
    for rpr in layers:
        v = wattr(rpr.find(q("color")), "val")
        if v:
            c = None if v.lower() == "auto" else v.upper()
    return c


def _run_text(r) -> str:
    out = []
    for ch in r:
        if ch.tag == q("t"):
            out.append(ch.text or "")
        elif ch.tag == q("tab"):
            out.append("\t")
        elif ch.tag in (q("br"), q("cr")):
            if ch.get(q("type")) != "page":
                out.append("\n")
    return "".join(out)


def _iter_runs(p):
    """段落里的 run（含超链接、修订插入、智能标签里的），不含删除的和文本框里的。"""
    for ch in p:
        if ch.tag == q("r"):
            yield ch
        elif ch.tag in (q("hyperlink"), q("ins"), q("smartTag"), q("sdt"), q("fldSimple")):
            sub = ch.find(q("sdtContent")) if ch.tag == q("sdt") else ch
            if sub is not None:
                yield from _iter_runs(sub)


def _ppr_values(layers: list) -> dict:
    v = {"jc": "left", "left": 0.0, "right": 0.0, "first": 0.0, "line": None, "rule": "auto", "mult": 1.0,
         "before": 0.0, "after": 0.0, "left_chars": None, "right_chars": None, "first_chars": None,
         "left_tw": 0.0, "right_tw": 0.0, "first_tw": 0.0, "pbb": False}
    for ppr in layers:
        jc = wattr(ppr.find(q("jc")), "val")
        if jc:
            v["jc"] = {"distribute": "both", "justify": "both", "start": "left", "end": "right"}.get(jc, jc)
        ind = ppr.find(q("ind"))
        if ind is not None:
            for key, attr, chars in (("left_tw", "left", "leftChars"), ("left_tw", "start", None),
                                     ("right_tw", "right", "rightChars"), ("right_tw", "end", None)):
                if ind.get(q(attr)) is not None:
                    v[key] = float(ind.get(q(attr)))
                if chars and ind.get(q(chars)) is not None:
                    v[chars.replace("Chars", "_chars")] = float(ind.get(q(chars))) / 100
            if ind.get(q("firstLine")) is not None:
                v["first_tw"] = float(ind.get(q("firstLine")))
                v["first_chars"] = None
            if ind.get(q("hanging")) is not None:
                v["first_tw"] = -float(ind.get(q("hanging")))
                v["first_chars"] = None
            if ind.get(q("firstLineChars")) is not None:
                v["first_chars"] = float(ind.get(q("firstLineChars"))) / 100
            if ind.get(q("hangingChars")) is not None:
                v["first_chars"] = -float(ind.get(q("hangingChars"))) / 100
        sp = ppr.find(q("spacing"))
        if sp is not None:
            if sp.get(q("line")) is not None:
                line = float(sp.get(q("line")))
                rule = sp.get(q("lineRule")) or "auto"
                v["rule"] = rule
                if rule == "auto":
                    v["mult"], v["line"] = line / 240, None
                else:
                    v["line"], v["mult"] = line / 20, 1.0
            if sp.get(q("before")) is not None:
                v["before"] = float(sp.get(q("before"))) / 20
            if sp.get(q("after")) is not None:
                v["after"] = float(sp.get(q("after"))) / 20
            for nm, key in (("beforeLines", "before"), ("afterLines", "after")):
                if sp.get(q(nm)) not in (None, "0"):
                    v[key] = max(v[key], float(sp.get(q(nm))) / 100 * 16)
            if sp.get(q("beforeAutospacing")) == "1":
                v["before"] = max(v["before"], 14.0)
            if sp.get(q("afterAutospacing")) == "1":
                v["after"] = max(v["after"], 14.0)
        if ppr.find(q("pageBreakBefore")) is not None:
            v["pbb"] = _toggle(ppr.find(q("pageBreakBefore")))
    return v


def _read_para(p, styles: _Styles, idx: int, in_table: bool) -> Para | None:
    ppr = p.find(q("pPr"))
    pstyle = wattr(ppr.find(q("pStyle")), "val") if ppr is not None else None
    pv = _ppr_values(styles.ppr_layers(pstyle, ppr))
    runs: list[Run] = []
    for r in _iter_runs(p):
        text = _run_text(r)
        if not text:
            continue
        rpr = r.find(q("rPr"))
        rstyle = wattr(rpr.find(q("rStyle")), "val") if rpr is not None else None
        layers = styles.rpr_layers(pstyle, rstyle, rpr)
        cjk = any("㐀" <= c <= "鿿" or "豈" <= c <= "﫿" for c in text)
        runs.append(Run(text, _font_of(layers, cjk, styles.theme_ea), _size_of(layers), _bold_of(layers),
                        _color_of(layers)))
    text = "".join(r.text for r in runs)
    has_drawing = p.find(f".//{q('drawing')}") is not None or p.find(f".//{q('pict')}") is not None
    size = next((r.size for r in runs if r.size), None) or _size_of(styles.rpr_layers(pstyle, None, None))
    left = pv["left_chars"] if pv["left_chars"] is not None else em_of(pv["left_tw"], size)
    right = pv["right_chars"] if pv["right_chars"] is not None else em_of(pv["right_tw"], size)
    first = pv["first_chars"] if pv["first_chars"] is not None else em_of(pv["first_tw"], size)
    if not text.strip() and not has_drawing:
        return None
    return Para(idx=idx, text=text, runs=runs, jc=pv["jc"], left_em=left, right_em=right, first_em=first,
                line_pt=pv["line"], line_rule=pv["rule"], line_mult=pv["mult"], before_pt=pv["before"],
                after_pt=pv["after"], in_table=in_table, has_drawing=has_drawing,
                has_numpr=bool(ppr is not None and ppr.find(f"{q('numPr')}/{q('numId')}") is not None),
                page_break_before=pv["pbb"], raw_text_len=len(text), node=p)


def _body_blocks(body):
    """按文档顺序给出 (段落节点, 是否在表格里)。"""
    for ch in body:
        if ch.tag == q("p"):
            yield ch, False
        elif ch.tag == q("tbl"):
            for p in ch.iter(q("p")):
                yield p, True
        elif ch.tag == q("sdt"):
            c = ch.find(q("sdtContent"))
            if c is not None:
                yield from _body_blocks(c)


def _sectpr_to_section(sp, rels: dict, zf: zipfile.ZipFile, styles: _Styles) -> Section:
    pg = sp.find(q("pgSz"))
    mar = sp.find(q("pgMar"))
    w = float(wattr(pg, "w") or 11906)
    h = float(wattr(pg, "h") or 16838)
    landscape = wattr(pg, "orient") == "landscape"

    def m(name: str, default: float) -> float:
        v = wattr(mar, name)
        return tw_to_mm(float(v)) if v is not None else tw_to_mm(default)

    grid = sp.find(q("docGrid"))
    sec = Section(w_mm=tw_to_mm(w), h_mm=tw_to_mm(h), top=m("top", 1440), bottom=m("bottom", 1440),
                  left=m("left", 1800), right=m("right", 1800), landscape=landscape,
                  grid_type=wattr(grid, "type"),
                  line_pitch=int(wattr(grid, "linePitch")) if wattr(grid, "linePitch") else None,
                  char_space=int(wattr(grid, "charSpace")) if wattr(grid, "charSpace") else None,
                  title_pg=sp.find(q("titlePg")) is not None)
    if sec.landscape and sec.w_mm < sec.h_mm:
        sec.w_mm, sec.h_mm = sec.h_mm, sec.w_mm
    for ref in sp.findall(q("footerReference")):
        rid = ref.get(f"{{{R}}}id")
        target = rels.get(rid)
        if not target:
            continue
        path = "word/" + target.lstrip("/").replace("word/", "", 1) if not target.startswith("/") else target.lstrip("/")
        try:
            root = _parse(zf.read(path), path)
        except KeyError:
            continue
        sec.footers.append(_read_footer(root, wattr(ref, "type") or "default", styles))
    return sec


def _read_footer(root, kind: str, styles: _Styles) -> FooterInfo:
    has_page, parts, jc, left, right, font, size = False, [], "left", 0.0, 0.0, None, None
    for p in root.iter(q("p")):
        ppr = p.find(q("pPr"))
        pstyle = wattr(ppr.find(q("pStyle")), "val") if ppr is not None else None
        pv = _ppr_values(styles.ppr_layers(pstyle, ppr))
        in_field = False
        text = []
        for el in p.iter():
            if el.tag == q("fldSimple") and "PAGE" in (el.get(q("instr")) or "").upper():
                has_page = True
                text.append("#")
            elif el.tag == q("instrText") and "PAGE" in (el.text or "").upper():
                has_page = True
                text.append("#")
                in_field = True
            elif el.tag == q("fldChar") and el.get(q("fldCharType")) == "end":
                in_field = False
            elif el.tag == q("t") and not in_field:
                text.append(el.text or "")
        line = "".join(text)
        if line.strip() and not parts:
            jc, left, right = pv["jc"], em_of(pv["left_tw"], 14), em_of(pv["right_tw"], 14)
            if pv["left_chars"] is not None:
                left = pv["left_chars"]
            if pv["right_chars"] is not None:
                right = pv["right_chars"]
            for r in _iter_runs(p):
                rpr = r.find(q("rPr"))
                layers = styles.rpr_layers(pstyle, wattr(rpr.find(q("rStyle")), "val") if rpr is not None else None, rpr)
                font = font or _font_of(layers, False, styles.theme_ea) or _font_of(layers, True, styles.theme_ea)
                size = size or _size_of(layers)
        if line.strip():
            parts.append(line)
    return FooterInfo(kind=kind, text=" ".join(parts), has_page=has_page, jc=jc, left_em=left, right_em=right,
                      font=font, size=size)


def _theme_ea(zf: zipfile.ZipFile) -> str | None:
    try:
        root = _parse(zf.read("word/theme/theme1.xml"), "theme1.xml")
    except (KeyError, GwError):
        return None
    for font in root.iter(f"{{{A}}}font"):
        if font.get("script") == "Hans" and font.get("typeface"):
            return font.get("typeface")
    return None


def read_docx(path: str) -> Doc:
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise GwError("E03", "不是 zip 结构") from e
    with zf:
        if sum(i.file_size for i in zf.infolist()) > MAX_TOTAL:
            raise GwError("E04", "解压后超过 60MB")
        try:
            doc_root = _parse(zf.read("word/document.xml"), "document.xml")
        except KeyError as e:
            raise GwError("E03", "缺少 word/document.xml") from e
        styles_root = _parse(zf.read("word/styles.xml"), "styles.xml") if "word/styles.xml" in zf.namelist() else None
        styles = _Styles(styles_root, _theme_ea(zf))
        rels: dict[str, str] = {}
        if "word/_rels/document.xml.rels" in zf.namelist():
            for rel in _parse(zf.read("word/_rels/document.xml.rels"), "rels").iter():
                if rel.get("Id") and rel.get("Target"):
                    rels[rel.get("Id")] = rel.get("Target")
        even_odd = False
        if "word/settings.xml" in zf.namelist():
            even_odd = _parse(zf.read("word/settings.xml"), "settings.xml").find(q("evenAndOddHeaders")) is not None
        body = doc_root.find(q("body"))
        if body is None:
            raise GwError("E03", "document.xml 没有正文")
        paras, n = [], 0
        for p, in_tbl in _body_blocks(body):
            para = _read_para(p, styles, n + 1, in_tbl)
            if para is not None:
                n += 1
                paras.append(para)
        sections, seen = [], []
        for sp in body.iter(q("sectPr")):
            if sp.find(q("pgSz")) is None:
                continue
            sec = _sectpr_to_section(sp, rels, zf, styles)
            key = (round(sec.top), round(sec.bottom), round(sec.left), round(sec.right), round(sec.w_mm))
            if key not in seen:
                seen.append(key)
                sections.append(sec)
        norm_size = _size_of(styles.rpr_layers(None, None, None)) or 10.5
    if not paras or not "".join(p.text for p in paras).strip():
        raise GwError("E05")
    return Doc(kind="docx", paras=paras, sections=sections, even_odd=even_odd, base_size=norm_size)
