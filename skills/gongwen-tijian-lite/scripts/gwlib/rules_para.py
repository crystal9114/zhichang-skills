"""标题、正文、层次、主送机关、发文字号、署名日期、附件说明、附注、版记。"""
from __future__ import annotations

import re
from collections import Counter

from .clauses import make
from .model import Doc, Issue, Para
from .structure import ATT_NOTE, DATE_ANY, LEVEL_RES, Layout, heading_span
from .units import is_cjk, size_name, text_em
from .util import dominant, font_share, lead_spaces, ranges, size_is, size_label, snip

LEVEL_FONT = {1: "黑体", 2: "楷体", 3: "仿宋", 4: "仿宋"}
LEVEL_NAME = {1: "一级「一、」", 2: "二级「（一）」", 3: "三级「1.」", 4: "四级「（1）」"}
DOC_TYPES = ("通知", "通报", "报告", "请示", "批复", "函", "意见", "决定", "公告", "通告", "议案", "纪要", "命令", "决议", "公报")


def doc_type(doc: Doc, lay: Layout, forced: str | None = None) -> str | None:
    if forced:
        return forced
    if not lay.title:
        return None
    title = "".join(p.text.strip() for p in doc.paras if p.idx in lay.title)
    title = re.sub(r"[》」”\s]+$", "", title)
    if "请示报告" in title:
        return "请示报告"
    for t in sorted(DOC_TYPES, key=len, reverse=True):
        if title.endswith(t):
            return t
    return None


def _grp(idxs, doc):
    by = {p.idx: p for p in doc.paras}
    return by[idxs[0]].text if idxs else ""


def check_title(doc: Doc, lay: Layout, dtype: str | None, txt: bool) -> list[Issue]:
    out: list[Issue] = []
    by = {p.idx: p for p in doc.paras}
    if not lay.title:
        return out
    tps = [by[i] for i in lay.title]
    full = "".join(p.text.strip() for p in tps)
    if not txt:
        fonts = Counter()
        for p in tps:
            f, _s, n = dominant(p)
            if f:
                fonts[f] += n
        if fonts and fonts.most_common(1)[0][0] != "小标宋":
            f = fonts.most_common(1)[0][0]
            bold = any(r.bold for p in tps for r in p.runs)
            out.append(make("T01", f"标题用的是「{f}」{'加粗' if bold else ''}，应为小标宋体", lay.title, full))
        sizes = Counter(dominant(p)[1] for p in tps if dominant(p)[1])
        if sizes and not size_is(sizes.most_common(1)[0][0], 22):
            out.append(make("T02", f"标题是{size_label(sizes.most_common(1)[0][0])}，应为二号（22磅）", lay.title, full))
        off = [p.idx for p in tps if p.jc != "center" and lead_spaces(p.text) < 2]
        sp = [p.idx for p in tps if p.jc != "center" and lead_spaces(p.text) >= 2]
        if off:
            out.append(make("T03", f"标题没有居中（当前{_jc(by[off[0]].jc)}）", off, full))
        if sp:
            out.append(make("S01", "标题靠行首空格顶成居中，换字体或换行就会歪", sp, by[sp[0]].text.strip(),
                            fix="删掉空格，段落对齐设为居中"))
    if re.search(r"[。，；！？,.;]$", full) or re.search(r"[，。；]", full):
        out.append(make("T04", "标题里有句号、逗号或分号" if not re.search(r"[。.]$", full) else "标题末尾有句号", lay.title, full))
    if dtype == "请示报告":
        out.append(make("T06", "标题写成「请示报告」：请示和报告是两个文种，不能合写", lay.title, full))
    elif dtype is None:
        out.append(make("T05", "标题末尾没看到文种（通知、请示、报告、函、意见、决定等）", lay.title, full))
    elif dtype == "请示":
        core = re.sub(r"^关于|的请示$", "", full)
        if re.search(r"[和并及与、]", core) and len(core) >= 10:
            out.append(make("T09", f"标题里连着几件事（「{snip(core, 18)}」），请示要一文一事，请核对", lay.title, full))
    return out


def _jc(jc: str) -> str:
    return {"center": "居中", "right": "居右", "left": "居左", "both": "两端对齐"}.get(jc, jc)


def check_dtype_body(doc: Doc, lay: Layout, dtype: str | None) -> list[Issue]:
    out: list[Issue] = []
    if not dtype or dtype == "请示报告":
        return out
    body = [p for p in doc.paras if lay.role(p.idx) in ("body", "att_note") or p.idx in lay.levels]
    req = re.compile(r"(妥否[，,]?请批示|请批示|请批复|请审批|请予批准|请予审批|请审阅批示|请予同意|请批准)")
    hits = [p for p in body if req.search(p.text)]
    if dtype in ("通知", "通报", "决定", "公告", "通告", "意见", "批复", "纪要", "命令") and hits:
        out.append(make("T07", f"这是「{dtype}」，却出现了请示用语「{req.search(hits[0].text).group(1)}」", [p.idx for p in hits],
                        hits[0].text))
    if dtype == "报告":
        hit2 = [p for p in body if re.search(r"(请批示|请批准|请批复|请予批准|妥否)", p.text)]
        if hit2:
            out.append(make("T08", "报告里夹带了请示事项（出现请求批准、批示的话）", [p.idx for p in hit2], hit2[0].text))
    if dtype == "请示":
        if not any(re.search(r"(请批示|请批复|请予批准|请予同意|妥否|恳请|拟请|请求|请予|请审批|请批准|请同意)", p.text) for p in body):
            out.append(make("T10", "全文没有明确的请求语（如「妥否，请批示」「请予批准」）"))
        tail = [p for p in body if p.text.strip().startswith("特此报告")]
        if tail:
            out.append(make("T07", "请示的结语写成「特此报告」，那是报告的收尾语", [tail[0].idx], tail[0].text))
        rec = {p.idx: p for p in doc.paras}.get(lay.recipient or -1)
        if rec and len(re.split(r"[、，,]", rec.text.strip().rstrip("：:"))) >= 2:
            out.append(make("T09", "请示的主送机关有两个以上，请示原则上只主送一个上级机关", [rec.idx], rec.text))
    return out


def check_body(doc: Doc, lay: Layout) -> list[Issue]:
    out: list[Issue] = []
    by = {p.idx: p for p in doc.paras}
    paras = [p for p in doc.paras if (lay.role(p.idx) == "body" or p.idx in lay.levels) and p.runs and not p.has_drawing]
    fontbad: dict[str, list[int]] = {}
    sizebad: dict[str, list[int]] = {}
    indbad, spaceind, linebad, spacebad, colorbad = [], [], [], [], []
    for p in paras:
        info = lay.levels.get(p.idx)
        span = heading_span(p, info) if info else 0
        if info and info[0] in (1, 2) and span >= len(p.text.rstrip()):
            f, s, n = None, dominant(p)[1], 0
        else:
            f, s, n = dominant(p, span, None)
            if info:
                s = dominant(p)[1]
        if n >= 4 and f and f != "仿宋":
            fontbad.setdefault(f, []).append(p.idx)
        if s and not size_is(s, 16) and len(p.text.strip()) >= 4:
            sizebad.setdefault(size_label(s), []).append(p.idx)
        if len(p.text.strip()) >= 4:
            ls = lead_spaces(p.text)
            if ls >= 2:
                spaceind.append(p.idx)
            elif p.jc not in ("center", "right") and (not 1.7 <= p.left_em + p.first_em <= 2.3 or p.left_em > 0.5):
                indbad.append(p.idx)
        if any(r.color and r.color not in ("000000",) for r in p.runs):
            colorbad.append(p.idx)
        if p.before_pt >= 3 or p.after_pt >= 3:
            spacebad.append(p.idx)
    if fontbad:
        n_all = sum(len(v) for v in fontbad.values())
        desc = "、".join(f"{k}（{len(v)}段）" for k, v in fontbad.items())
        first = min(i for v in fontbad.values() for i in v)
        out.append(make("B01", f"正文共 {n_all} 段不是仿宋：{desc}", [i for v in fontbad.values() for i in v], by[first].text))
    if sizebad:
        n_all = sum(len(v) for v in sizebad.values())
        desc = "、".join(f"{k}（{len(v)}段）" for k, v in sizebad.items())
        first = min(i for v in sizebad.values() for i in v)
        out.append(make("B02", f"正文共 {n_all} 段不是三号：{desc}", [i for v in sizebad.values() for i in v], by[first].text))
    if indbad:
        p0 = by[indbad[0]]
        out.append(make("B03", f"共 {len(indbad)} 段首行缩进不是 2 字（例：首行缩进 {p0.first_em:g} 字、左缩进 {p0.left_em:g} 字）",
                        indbad, p0.text))
    if spaceind:
        out.append(make("S01", f"共 {len(spaceind)} 段用行首空格代替缩进，字体或字号一变就对不齐", spaceind, by[spaceind[0]].text.strip()))
    if colorbad:
        cn = _color_name(by[colorbad[0]])
        out.append(make("B06", f"共 {len(colorbad)} 段文字不是黑色（例：{cn}）", colorbad, by[colorbad[0]].text))
    if spacebad:
        q = by[spacebad[0]]
        out.append(make("B05", f"共 {len(spacebad)} 段设了段前或段后间距（例：段前 {q.before_pt:g} 磅、段后 {q.after_pt:g} 磅），"
                               "会占掉版心行数", spacebad, q.text))
    modes: dict[str, list[int]] = {}
    for p in paras:
        if len(p.text.strip()) < 20:
            continue
        if p.line_rule in ("exact", "atLeast") and p.line_pt:
            key = "ok" if 26 <= p.line_pt <= 30 else f"固定值{p.line_pt:g}磅"
        else:
            key = f"{p.line_mult:g}倍行距"
        modes.setdefault(key, []).append(p.idx)
    if doc.sections and doc.sections[0].grid_type == "linesAndChars" and doc.sections[0].line_pitch:
        modes.pop("1倍行距", None)
    if len(modes) > 1:
        desc = "、".join(f"{'固定值28磅左右' if k == 'ok' else k}（{len(v)}段）" for k, v in modes.items())
        allp = [i for v in modes.values() for i in v]
        out.append(make("B04", f"正文行距不统一：{desc}", allp, by[allp[0]].text))
    elif modes and "ok" not in modes:
        k, v = next(iter(modes.items()))
        out.append(make("B04", f"正文行距是{k}（{len(v)} 段），不是 28 磅左右的固定值，每页排不成 22 行", v, by[v[0]].text))
    return out


def check_levels(doc: Doc, lay: Layout) -> list[Issue]:
    out: list[Issue] = []
    by = {p.idx: p for p in doc.paras}
    badfont: dict[int, dict[str, list[int]]] = {}
    for idx, info in lay.levels.items():
        p = by[idx]
        if not p.runs:
            continue
        span = heading_span(p, info)
        want = LEVEL_FONT[info[0]]
        if font_share(p, want, 0, max(span, 1)) < 0.8:
            f, _s, n = dominant(p, 0, max(span, 1))
            if n:
                badfont.setdefault(info[0], {}).setdefault(f or "未指定", []).append(idx)
    for lvl, d in sorted(badfont.items()):
        allp = [i for v in d.values() for i in v]
        desc = "、".join(f"{k}（{len(v)}处）" for k, v in d.items())
        out.append(make("L01", f"{LEVEL_NAME[lvl]}标题应为{LEVEL_FONT[lvl]}，实际{desc}", allp, by[allp[0]].text))
    bad = [(i, info) for i, info in sorted(lay.levels.items()) if not info[2]]
    shown = bad[:4]
    for i, info in shown:
        out.append(make("L03", info[3], [i], by[i].text))
    if len(bad) > 4:
        out.append(make("L03", f"另有 {len(bad) - 4} 处序号写法同类问题", [i for i, _ in bad[4:]], by[bad[4][0]].text))
    counters = {1: 0, 2: 0, 3: 0, 4: 0}
    seq_issues = []
    for idx in sorted(lay.levels):
        lvl, val, ok, _why = lay.levels[idx]
        if val is None:
            continue
        want = counters[lvl] + 1
        if val != want:
            kind = "跳号" if val > want else "重号或倒退"
            more = "" if val > want else f"（这一级前面已经写过「{_seq(lvl, val)}」，这里又写了一次）"
            seq_issues.append((idx, f"{LEVEL_NAME[lvl]}序号{kind}：这里应为「{_seq(lvl, want)}」，实际写成「{_seq(lvl, val)}」{more}"))
        counters[lvl] = val
        for deeper in range(lvl + 1, 5):
            counters[deeper] = 0
    for idx, what in seq_issues[:5]:
        out.append(make("L02", what, [idx], by[idx].text))
    if len(seq_issues) > 5:
        out.append(make("L02", f"另有 {len(seq_issues) - 5} 处序号不连续", [i for i, _ in seq_issues[5:]], by[seq_issues[5][0]].text))
    return out


def check_recipient(doc: Doc, lay: Layout, dtype: str | None, txt: bool) -> list[Issue]:
    out: list[Issue] = []
    by = {p.idx: p for p in doc.paras}
    if lay.recipient is None:
        if dtype in ("请示", "报告", "函", "批复") and lay.title:
            out.append(make("R03", f"这是「{dtype}」，标题下没看到主送机关（以全角冒号结尾的一行）"))
        return out
    p = by[lay.recipient]
    t = p.text.strip()
    if t.endswith(":"):
        out.append(make("R01", "主送机关末尾是半角冒号「:」", [p.idx], t))
    if not txt and (p.left_em > 0.5 or p.first_em > 0.5 or lead_spaces(p.text) >= 1):
        out.append(make("R02", f"主送机关没有顶格（首行缩进 {p.first_em:g} 字、左缩进 {p.left_em:g} 字）", [p.idx], t))
    if not txt and p.runs:
        f, s, n = dominant(p)
        if n and (f != "仿宋" or not size_is(s, 16)):
            out.append(make("B01", f"主送机关用的是 {f}、{size_label(s)}，应为仿宋三号", [p.idx], t))
    return out


DOCNO_FINE = re.compile(r"([^\s〔\[\(（【{｛]{1,12}?)\s*([〔\[\(（【{｛])\s*(\d{2,4})\s*([〕\]\)）】}｝])\s*(第)?\s*(\d{1,5})\s*号")


def check_docno(doc: Doc, lay: Layout, txt: bool) -> list[Issue]:
    out: list[Issue] = []
    by = {p.idx: p for p in doc.paras}
    cands = [by[i] for i in lay.head] + [p for p in doc.paras[:8] if p.idx not in lay.head and lay.role(p.idx) in ("title", "head")]
    p = next((c for c in cands if DOCNO_FINE.search(c.text)), None)
    if p is None:
        return out
    m = DOCNO_FINE.search(p.text)
    code, op, year, cl, di, seq = m.groups()
    t = p.text.strip()
    if (op, cl) != ("〔", "〕"):
        out.append(make("N01", f"发文字号里的年份括号是「{op}{year}{cl}」，应用六角括号「〔{year}〕」", [p.idx], t))
    if len(year) != 4:
        out.append(make("N02", f"发文字号里的年份是「{year}」，应写全称 4 位", [p.idx], t))
    if di or seq.startswith("0"):
        out.append(make("N03", "发文字号的序号带了「第」字或前面补了 0", [p.idx], t))
    if not txt and p.jc != "center" and not re.search(r"签发人", "".join(x.text for x in doc.paras[:6])):
        out.append(make("N04", f"发文字号没有居中（当前{_jc(p.jc)}）", [p.idx], t))
    dm = by.get(lay.date or -1)
    if dm:
        ym = re.search(r"(\d{4})\s*年", dm.text)
        if ym and len(year) == 4 and ym.group(1) != year:
            out.append(make("N05", f"发文字号年份 {year} 与成文日期年份 {ym.group(1)} 不一致", [p.idx, dm.idx], t))
    return out


def date_problems(text: str) -> list[str]:
    t = text.strip()
    why = []
    if re.search(r"[〇○零一二三四五六七八九]{2,4}\s*年", t):
        why.append("用了汉字数字，应用阿拉伯数字")
    if re.search(r"(?<!\d)\d{2}\s*年", t):
        why.append("年份没写全称")
    if re.search(r"(?<![\d])0\d\s*月|月\s*0\d\s*日?", t):
        why.append("月或日编了虚位（03、05 应写 3、5）")
    if re.search(r"\d\s*[./\-－]\s*\d{1,2}\s*[./\-－]\s*\d", t):
        why.append("用了点号、横线或斜线分隔，应写「年」「月」「日」")
    if re.search(r"\d\s+[年月日]|[年月]\s+\d", t):
        why.append("数字和年月日之间有空格")
    if re.search(r"\d\s*月\s*\d{1,2}\s*$", t) or (re.search(r"月", t) and not re.search(r"日\s*$", t) and re.search(r"\d\s*$", t)):
        why.append("最后缺「日」字")
    return why


def _span(p: Para):
    w = text_em(p.text.strip())
    if p.jc == "right":
        end = 28 - p.right_em
        return end - w, end
    if p.jc == "center":
        c = 14 + (p.left_em - p.right_em) / 2
        return c - w / 2, c + w / 2
    start = p.left_em + max(p.first_em, 0) + lead_spaces(p.text)
    return start, start + w



def _color_name(p: Para) -> str:
    """把文字颜色翻成人话：蓝色、红色这类，认不出的写十六进制。"""
    hexv = next((r.color for r in p.runs if r.color and r.color != "000000"), "")
    try:
        r_, g_, b_ = (int(hexv[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return f"颜色 {hexv}"
    if b_ > max(r_, g_) + 40:
        name = "蓝色"
    elif r_ > max(g_, b_) + 40:
        name = "红色"
    elif g_ > max(r_, b_) + 40:
        name = "绿色"
    else:
        name = "非黑颜色"
    return f"{name}（{hexv}）"



_CN_DIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_to_int(t: str) -> int | None:
    """一到三十一的汉字数字转阿拉伯数字，认不出返回 None。"""
    if not t:
        return None
    if "十" in t:
        head, _, tail = t.partition("十")
        tens = _CN_DIGIT.get(head, 1) if head else 1
        ones = _CN_DIGIT.get(tail, 0) if tail else 0
        return tens * 10 + ones if (not head or head in _CN_DIGIT) and (not tail or tail in _CN_DIGIT) else None
    return _CN_DIGIT.get(t)


def _date_parts(text: str) -> tuple[int, int, int] | None:
    """从「2026.1.20」「二〇二六年一月二十日」这类写法取年月日，取不出返回 None（只用来写改法示例）。"""
    m = re.fullmatch(r"\s*(\d{4})\s*[.\-/年]\s*(\d{1,2})\s*[.\-/月]\s*(\d{1,2})\s*日?\s*", text)
    if m:
        return int(m[1]), int(m[2]), int(m[3])
    m = re.fullmatch(r"\s*([〇零一二三四五六七八九]{4})年\s*([一二三四五六七八九十]{1,3})月\s*([一二三四五六七八九十]{1,3})日\s*", text)
    if not m:
        return None
    year = int("".join(str(_CN_DIGIT[c]) for c in m[1]))
    month, day = _cn_to_int(m[2]), _cn_to_int(m[3])
    return (year, month, day) if month and day else None



def _seq(level: int, n: int) -> str:
    """第 level 级序号写成文里的样子：一、 （一） 1. （1）。"""
    zh = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二", "十三", "十四", "十五",
          "十六", "十七", "十八", "十九", "二十"]
    c = zh[n] if 0 <= n < len(zh) else str(n)
    return {1: f"{c}、", 2: f"（{c}）", 3: f"{n}.", 4: f"（{n}）"}[level]


def check_tail(doc: Doc, lay: Layout, dtype: str | None, txt: bool) -> list[Issue]:
    out: list[Issue] = []
    by = {p.idx: p for p in doc.paras}
    d = by.get(lay.date or -1)
    if d is None:
        last = [p for p in doc.paras if p.idx <= lay.main_end][-6:]
        mixed = next((p for p in reversed(last) if DATE_ANY and re.search(DATE_ANY, p.text) and lay.role(p.idx) in ("body", "signature")
                      and len(p.text.strip()) < 50), None)
        if mixed:
            why = date_problems(mixed.text)
            out.append(make("D02", "成文日期没有单独成行（和署名或正文挤在一行）" + ("；" + "、".join(why) if why else ""),
                            [mixed.idx], mixed.text))
        elif dtype not in ("纪要", "公告") and lay.title and not any(re.search(DATE_ANY, p.text) for p in last):
            out.append(make("D02", "没看到成文日期（应在正文下方单独一行）"))
        return out
    why = date_problems(d.text)
    if why:
        ymd = _date_parts(d.text)
        how = f"改成「{ymd[0]}年{ymd[1]}月{ymd[2]}日」（对照原稿确认日期无误后手改）" if ymd else None
        out.append(make("D01", f"成文日期「{d.text.strip()}」：" + "；".join(why), [d.idx], d.text, how))
    s = by.get(lay.signature or -1)
    if s is None and dtype != "纪要":
        out.append(make("D05", "成文日期上一行没有发文机关署名", [d.idx], d.text))
    if txt:
        return out
    if d.runs:
        f, sz, n = dominant(d)
        if n and (f != "仿宋" or not size_is(sz, 16)):
            out.append(make("D04", f"成文日期用的是 {f}、{size_label(sz)}，应为仿宋三号", [d.idx], d.text))
    if s is not None:
        sa, ea = _span(s)
        sb, eb = _span(d)
        center_ok = abs((sa + ea) / 2 - (sb + eb) / 2) <= 1.2
        shift_ok = abs((sb - sa) - 2) <= 1.0 or (eb - sb > ea - sa and abs((28 - eb) - 2) <= 1.0)
        if not (center_ok or shift_ok):
            out.append(make("D03", f"署名和日期的位置对不上：署名居中位置 {(sa + ea) / 2:.1f} 字、日期 {(sb + eb) / 2:.1f} 字，"
                                   "既不是居中对齐，也不是日期首字右移两字", [s.idx, d.idx], f"{s.text.strip()} / {d.text.strip()}"))
    return out


def check_attach(doc: Doc, lay: Layout, txt: bool) -> list[Issue]:
    out: list[Issue] = []
    by = {p.idx: p for p in doc.paras}
    if lay.att_notes:
        first = by[lay.att_notes[0]]
        t = first.text
        if re.match(r"^[\s　]*附件\s*:", t):
            out.append(make("A01", "附件说明里「附件」后面是半角冒号", [first.idx], t))
        if not txt and lead_spaces(t) < 2 and first.left_em + first.first_em < 1.5:
            out.append(make("A02", f"附件说明没有左空二字（缩进 {first.left_em + first.first_em:g} 字）", [first.idx], t))
        names = [by[i].text for i in lay.att_notes]
        body = re.sub(r"^[\s　]*附件\s*[：:]\s*", "", names[0])
        items = [re.sub(r"^[\s　]*\d{1,2}[.．、]\s*", "", s).strip() for s in [body] + names[1:] if s.strip()]
        numbered = [bool(re.match(r"^[\s　]*\d{1,2}[.．、]", s)) for s in [body] + names[1:]]
        if len(items) >= 2 and not all(numbered):
            out.append(make("A03", "有多个附件，但没有用阿拉伯数字标序号", lay.att_notes, t))
        elif len(items) == 1 and numbered[0]:
            out.append(make("A03", "只有一个附件，不用编序号", lay.att_notes, t))
        if any(re.search(r"[。；，、.;,]$", x) for x in items):
            bad = next(i for i, x in zip(lay.att_notes, items) if re.search(r"[。；，、.;,]$", x))
            out.append(make("A04", "附件名称后面加了标点", [bad], by[bad].text))
        if lay.date and first.idx > lay.date:
            out.append(make("A05", "附件说明排在成文日期之后", [first.idx], t))
        if not lay.att_pages and not txt:
            out.append(make("A06", "附件说明里写了附件，但文档里没有单独的附件页"))
    if lay.att_pages and not txt:
        p = by[lay.att_pages[0]]
        f, _s, n = dominant(p)
        bad = []
        if n and f != "黑体":
            bad.append(f"用的是{f}（应黑体）")
        if p.jc != "left" or p.left_em > 0.5 or p.first_em > 0.5:
            bad.append("没有顶格")
        if bad:
            out.append(make("A07", "附件页第一行" + "、".join(bad), [p.idx], p.text))
    return out


def check_note_and_cc(doc: Doc, lay: Layout, txt: bool) -> list[Issue]:
    out: list[Issue] = []
    by = {p.idx: p for p in doc.paras}
    if lay.note:
        p = by[lay.note]
        if re.match(r"^[\s　]*\(", p.text):
            out.append(make("M01", "附注用了半角括号，应为全角圆括号「（ ）」", [p.idx], p.text))
        elif not txt and lead_spaces(p.text) < 2 and p.left_em + p.first_em < 1.5:
            out.append(make("M01", "附注没有左空二字", [p.idx], p.text))
    for i in lay.footer_blocks:
        p = by[i]
        t = p.text.strip()
        if re.match(r"^(抄送|主送)\s*:", t):
            out.append(make("V01", "版记里「抄送」后面是半角冒号", [i], t))
        if t.startswith(("抄送", "主送")) and not t.endswith("。"):
            out.append(make("V02", "抄送机关最后一个名称后面没有句号", [i], t))
        m = re.search(r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)\s*印发", t)
        if m:
            why = date_problems(m.group(1))
            if why:
                out.append(make("V03", "印发日期：" + "；".join(why), [i], t))
        if not txt and p.runs:
            f, s, n = dominant(p)
            if n and (f != "仿宋" or not size_is(s, 14)):
                out.append(make("V04", f"版记这一行用的是 {f}、{size_label(s)}，应为仿宋四号", [i], t))
    return out
