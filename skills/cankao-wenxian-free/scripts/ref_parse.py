"""把一条参考文献原文拆成字段。认得：国标写法（2005/2015/2025，含知网、谷歌学术、百度学术导出）、
著者-出版年制写法、APA 英文写法。拆不开的标 parsed=False，原文保留，交给买家确认，绝不猜着补。"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ref_model import (DOI_RE, TYPE_ALIASES, URL_RE, Ref, has_cjk, norm_date)

NUM_PREFIX = re.compile(r"^\s*(?:[\[［【]\s*(\d{1,4})\s*[\]］】]|[(（]\s*(\d{1,4})\s*[)）]|(\d{1,4})\s*[.．、](?!\d))\s*")
MARKER = re.compile(r"[\[［【]\s*([A-Za-z]{1,2})\s*(?:[/／]\s*([A-Za-z0-9]{2}))?\s*[\]］】]")
ALIAS_MARKER = re.compile(r"[\[［【]\s*(" + "|".join(sorted(TYPE_ALIASES, key=len, reverse=True)) + r")\s*[\]］】]", re.I)
CITE_DATE = re.compile(r"[\[［]\s*(\d{4}\s*[-–—/年.]\s*\d{1,2}\s*[-–—/月.]\s*\d{1,2}日?)\s*[\]］]")
PAREN_DATE = re.compile(r"[(（]\s*(\d{4}\s*[-–—/]\s*\d{1,2}\s*[-–—/]\s*\d{1,2})\s*[)）]")
CSTR = re.compile(r"CSTR\s*[:：]\s*([\w.\-]+)", re.I)
SEP = re.compile(r"[.．。](?=\s|[^\s\d.])")
INITIAL_DOT = re.compile(r"(?:^|[\s,，])[A-Z]$")
ETAL = re.compile(r"(?:[,，]\s*|\s+)(等|et\s*al\.?|等人|et\s+al)\s*$", re.I)
STD_NO = re.compile(r"((?:GB|GB/T|GB/Z|GJB|JB|JB/T|YY|YY/T|HJ|NB/T|GY/T|QB|QB/T|WS|WS/T|CJJ|JGJ|SL|DL/T|JTG|TB|"
                    r"ISO|IEC|IEEE|ASTM|EN|DIN|JIS|T/[A-Z]+|DB\d{2}(?:/T)?)(?:/IEEE|/IEC)?\s*[\d.]+(?:\s*[-—–:]\s*\d{4})?)")
PATENT_NO = re.compile(r"((?:CN|ZL|US|JP|EP|WO|KR|AU|DE|GB|FR)?\s*\d[\d.]{6,}\s*[A-Z]?\d?)$")
EDITION = re.compile(r"^(第?\s*\d+\s*版|\d+(?:st|nd|rd|th)\s*ed(?:ition)?\.?|修订版|修订本|增订本|新\s*\d+\s*版|"
                     r"影印本|刻本|写本|抄本|Rev\.?\s*ed\.?|V\d[\d.]*|[\w ]*edition)$", re.I)
OTHER_RESP = re.compile(r"(译|编译|译注|校注|校|注|编|主编|等译|trans\.?|tr\.|ed\.|eds\.)$", re.I)
ORG_WORDS = re.compile(r"(University|Society|Organization|Organisation|Inc\b|Department|Association|Institute|"
                       r"Committee|Ltd|Center|Centre|Agency|Office|Bureau|Group|Ministry|Council|Foundation|"
                       r"Federation|Laboratory|Commission|Library|Museum|Academy|Corporation|Company|IHME|WHO)", re.I)
INITIALS = re.compile(r"^(?:[A-Z](?:[a-z])?\.?\s*-?\s*)+$")
APA = re.compile(r"^(?P<au>.+?)\s*\((?P<year>\d{4}[a-z]?|n\.\s*d\.)(?:,\s*[A-Za-z]+\.?(?:\s*\d{1,2})?)?\)\.\s*(?P<rest>.+)$")


def split_entries(text: str) -> List[Tuple[Optional[int], str]]:
    """一段文字 → [(原序号, 条目原文)]。有序号的按序号切（续行并入上一条），没有序号的一行一条。"""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [ln for ln in lines if ln.strip()]
    numbered = sum(1 for ln in lines if NUM_PREFIX.match(ln))
    out: List[Tuple[Optional[int], str]] = []
    if numbered and numbered >= len(lines) // 2:
        for ln in lines:
            m = NUM_PREFIX.match(ln)
            if m:
                no = int(next(g for g in m.groups() if g))
                out.append((no, ln[m.end():].strip()))
            elif out:
                no, prev = out[-1]
                joiner = "" if has_cjk(prev[-1:]) or prev.endswith(("/", "-")) else " "
                out[-1] = (no, prev + joiner + ln.strip())
            else:
                out.append((None, ln.strip()))
        return out
    return [(None, ln.strip()) for ln in lines]


# ---------- 著者 ----------

def split_names(seg: str) -> List[str]:
    seg = seg.strip().strip(".．。 ")
    parts = [p.strip() for p in re.split(r"[,，、;；]|\s+and\s+|\s*&\s*", seg) if p.strip()]
    # 「张三和李四」才拆；「中华人民共和国…」这类机构名里的「和」不拆
    parts = [x for p in parts for x in (p.split("和") if re.fullmatch(r"[一-鿿]{2,4}和[一-鿿]{2,4}", p) else [p])]
    # 「Smith, J. A., Jones, B.」这种姓和缩写名被逗号隔开的，两两并回去
    merged: List[str] = []
    for p in parts:
        if (merged and INITIALS.match(p) and not INITIALS.match(merged[-1]) and not has_cjk(p)
                and not re.search(r"(?:^|\s)[A-Z](?:\.|\s|$)", merged[-1])):
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged


def is_name(tok: str) -> bool:
    tok = tok.strip()
    if not tok:
        return False
    if has_cjk(tok):
        return bool(re.fullmatch(r"[㐀-鿿぀-ヿ·•（）()A-Za-z\s.]{1,40}", tok)) and not re.search(r"\d", tok)
    if ORG_WORDS.search(tok):
        return len(tok) <= 120
    return bool(re.fullmatch(r"[A-Za-zÀ-ÿ'’\-. ]{1,40}", tok)) and len(tok.split()) <= 5


def looks_like_authors(seg: str) -> Optional[Tuple[List[str], bool, str]]:
    """像著者项就返回 (著者列表, 原文有没有等/et al, 著者后带的出版年)，不像返回 None。"""
    s = seg.strip()
    year = ""
    m = re.search(r"[,，]\s*(\d{4}[a-z]?)$", s)
    if m:
        year, s = m.group(1), s[:m.start()].strip()
    etal = False
    m = ETAL.search(s)
    if m:
        etal, s = True, s[:m.start()].strip()
    if not s:
        return None
    names = split_names(s)
    if not names or len(names) > 40 or not all(is_name(n) for n in names):
        return None
    return names, etal, year


def split_authors_title(pre: str) -> Tuple[List[str], bool, str, str]:
    """著者. 题名 → (著者, 有等, 著者后出版年, 题名)。"""
    for m in SEP.finditer(pre):
        i = m.start()
        left = pre[:i]
        # 「Smith J. A. Title」里缩写名后的点不是分隔
        if INITIAL_DOT.search(left) and re.match(r"\s*(?:[A-Z]\.|[A-Z]\s*(?:[,，]|$)|[,，-])", pre[i + 1:]):
            continue
        hit = looks_like_authors(left)
        if hit:
            names, etal, year = hit
            return names, etal, year, pre[m.end():].strip()
        if len(left) > 80:
            break
    return [], False, "", pre.strip()


# ---------- 出版项 ----------

PUB_TAIL = re.compile(r"[,，]\s*(?P<year>c?\[?\d{4}[a-z]?\]?(?:\s*[(（][^)）]*[)）])?)\s*(?:[:：]\s*(?P<pages>[^:：]*?))?\s*[.．。]?\s*$")


def parse_pubinfo(s: str, ref: Ref, year_first: bool) -> bool:
    """「[其他责任者. ][版本. ]出版地: 出版者, 出版年: 页码」。成功返回 True 并写进 ref。"""
    s = s.strip().strip("．。").strip()
    if not s:
        return False
    head, year, pages = s, "", ""
    m = PUB_TAIL.search(s)
    if m and not year_first:
        head, year, pages = s[:m.start()], m.group("year"), (m.group("pages") or "")
    elif year_first:
        m2 = re.search(r"[:：]\s*([\d\-–—~～,，\s序扉页]+)\s*[.．。]?\s*$", s)
        if m2 and s.count(":") + s.count("：") >= 2:
            head, pages = s[:m2.start()], m2.group(1)
        elif m:   # 著者-出版年制原文里又写了出版年
            head, year, pages = s[:m.start()], m.group("year"), (m.group("pages") or "")
    colon = max(head.rfind(":"), head.rfind("："))
    if colon < 0:
        if year:
            # 「北京大学, 2003」这种缺出版地的
            segs = [x.strip() for x in re.split(r"[.．。]\s+", head) if x.strip()]
            for x in segs[:-1]:
                _take_pre_pub(x, ref)
            ref.publisher = segs[-1] if segs else ""
            ref.year, ref.pages = year, pages.strip()
            return bool(ref.publisher)
        return False
    before, ref.publisher = head[:colon], head[colon + 1:].strip().strip(",，")
    segs = [x.strip() for x in re.split(r"(?<![A-Z])[.．。]\s+", before) if x.strip()]
    if segs:
        ref.place = segs[-1]
        for x in segs[:-1]:
            _take_pre_pub(x, ref)
    ref.year = ref.year or year
    ref.pages = pages.strip()
    return bool(ref.publisher)


def _take_pre_pub(seg: str, ref: Ref) -> None:
    seg = seg.strip().strip("．。.")
    if EDITION.match(seg):
        ref.edition = seg
    elif OTHER_RESP.search(seg):
        ref.other_resp = seg
    elif seg:
        ref.other_resp = (ref.other_resp + "; " + seg).strip("; ") if ref.other_resp else seg


JOURNAL = re.compile(r"^(?P<j>.+?)\s*[,，]\s*(?P<year>\d{4}[a-z]?)\s*(?:[,，]\s*(?P<vol>[^,，(（:：]+?))?\s*"
                     r"(?:[(（]\s*(?P<iss>[^)）]{1,20}?)\s*[)）])?\s*(?:[:：]\s*(?P<pages>[^:：]+?))?\s*[.．。]?\s*$")
JOURNAL_AY = re.compile(r"^(?P<j>.+?)\s*(?:[,，]\s*(?P<vol>\d[^,，(（:：]*?))?\s*(?:[(（]\s*(?P<iss>[^)）]{1,20}?)\s*[)）])?\s*"
                        r"(?:[:：]\s*(?P<pages>[^:：]+?))?\s*[.．。]?\s*$")
NEWS = re.compile(r"^(?P<p>.+?)\s*[,，]\s*(?P<date>\d{4}\s*[-–—]\s*\d{1,2}\s*[-–—]\s*\d{1,2})\s*(?:[(（]\s*(?P<ed>[^)）]+?)\s*[)）])?\s*[.．。]?\s*$")
CONF25 = re.compile(r"^(?P<c>.+?)\s*[,，]\s*(?P<year>\d{4})\s*(?:[:：]\s*(?P<pages>[^:：]+?))?\s*[.．。]?\s*$")
DATE_ONLY = re.compile(r"^(?P<date>\d{4}\s*[-–—]\s*\d{1,2}\s*[-–—]\s*\d{1,2})\s*(?:[:：]\s*(?P<pages>[^:：]+?))?\s*[.．。]?\s*$")


def parse_journal(s: str, ref: Ref) -> bool:
    m = JOURNAL.match(s) if not ref.year_first else (JOURNAL_AY.match(s) or JOURNAL.match(s))
    if not m:
        return False
    g = m.groupdict()
    if not ref.year_first or g.get("year"):
        ref.year = g.get("year") or ref.year
    ref.container = g["j"].strip()
    ref.volume = (g.get("vol") or "").strip()
    ref.issue = (g.get("iss") or "").strip()
    ref.pages = (g.get("pages") or "").strip()
    if ref.year_first and not (ref.volume or ref.issue or ref.pages) and "," not in s and "，" not in s:
        return False
    return True


def parse_container(s: str, ref: Ref) -> bool:
    """「//」后面：[图书责任者. ]图书题名. [版本. ]出版地: 出版者, 年: 页码；或 2025 会议：会议名称, 年份: 页码。"""
    s = s.strip()
    probe = Ref(raw=s, year_first=ref.year_first)
    if parse_pubinfo(s, probe, ref.year_first) and probe.place:
        # 出版地之前的部分是「图书责任者. 图书题名. 版本」
        pre = s[: s.find(probe.place)] if probe.place in s else ""
        segs = [x.strip() for x in re.split(r"(?<![A-Z])[.．。]\s+", pre) if x.strip()]
        if segs and EDITION.match(segs[-1].strip(".")):
            ref.edition = segs.pop().strip(".")
        if len(segs) >= 2 and looks_like_authors(re.sub(r"(主编|编|ed\.|eds\.|\(eds?\.\))\s*$", "", segs[0], flags=re.I)):
            ref.container_authors = split_names(re.sub(r"(主编|编|ed\.|eds\.|\(eds?\.\))\s*$", "", segs[0], flags=re.I))
            ref.container = ". ".join(segs[1:])
        else:
            ref.container = ". ".join(segs)
        ref.place, ref.publisher = probe.place, probe.publisher
        ref.year = ref.year or probe.year
        ref.pages = probe.pages
        return bool(ref.container)
    m = CONF25.match(s)
    if m:
        ref.container, ref.year, ref.pages = m.group("c").strip(), ref.year or m.group("year"), (m.group("pages") or "").strip()
        return True
    ref.container = s.strip("．。. ")
    return bool(ref.container)


def take_title_number(ref: Ref) -> None:
    """标准号、专利号、报告编号从题名里拆出来。"""
    t = ref.title
    if ref.type == "S" or (not ref.type and STD_NO.search(t)):
        m = STD_NO.match(t)                 # 2005/2025 写法：编号在前
        if m:
            ref.subtitle_no, ref.title = m.group(1).strip(), t[m.end():].strip(" :：")
            return
        m = re.search(r"[:：]\s*" + STD_NO.pattern + r"\s*$", t)   # 2015 写法：题名: 编号
        if m:
            ref.subtitle_no, ref.title = m.group(1).strip(), t[:m.start()].strip()
            return
    if ref.type in ("P", ""):
        m = re.search(r"[:：]\s*" + PATENT_NO.pattern, t)
        if m:
            ref.subtitle_no, ref.title = m.group(1).replace(" ", ""), t[:m.start()].strip()
            if not ref.type:
                ref.type = "P"
            return
    if ref.type == "R":
        m = re.search(r"[:：]\s*([A-Z]{1,6}[-\s]?[A-Z0-9\-/ .]{2,30})$", t)
        if m and re.search(r"\d", m.group(1)):
            ref.subtitle_no, ref.title = m.group(1).strip(), t[:m.start()].strip()


# ---------- 主入口 ----------

def strip_tail_ids(s: str, ref: Ref) -> str:
    m = DOI_RE.search(s + " ") or re.search(r"\bDOI\s*[:：]\s*(\S+?)[.。]?(?=\s|$)", s, re.I)
    if m:
        ref.doi = m.group(1).rstrip(".。")
        s = (s[:m.start()] + " " + s[m.end():]).strip()
    m = CSTR.search(s)
    if m:
        ref.pid = "CSTR: " + m.group(1).rstrip(".")
        s = (s[:m.start()] + s[m.end():]).strip()
    for u in URL_RE.findall(s):
        if not ref.url:
            ref.url = u.rstrip(".。")
        s = s.replace(u, " ")
    if ref.url and re.search(r"doi\.org/(10\.\d{4,9}/\S+)", ref.url) and not ref.doi:
        ref.doi = re.search(r"doi\.org/(10\.\d{4,9}/\S+)", ref.url).group(1)
    m = CITE_DATE.search(s)
    if m:
        ref.cite_date = norm_date(m.group(1))
        s = (s[:m.start()] + s[m.end():])
    m = PAREN_DATE.search(s)
    if m and not re.search(r"\d{4}\s*[-–—]\s*\d{1,2}\s*[-–—]\s*\d{1,2}\s*$", s[:m.start()].strip()):
        ref.update_date = norm_date(m.group(1))
        s = s[:m.start()] + s[m.end():]
    s = re.sub(r"(?:获取和访问路径|访问路径|URL)\s*[:：]?\s*$", "", s.strip())
    s = re.sub(r"\s*[.．。]\s*[.．。]+", ".", s)
    return re.sub(r"\s{2,}", " ", s).strip().rstrip(".．。 ").strip()


def parse_apa(m: "re.Match[str]", ref: Ref) -> Ref:
    ref.source_style = "apa"
    ref.authors = split_names(m.group("au").replace("…", ","))
    ref.had_etal = bool(re.search(r"et al", m.group("au")))
    ref.year = "" if "n" in m.group("year") else m.group("year")
    rest = m.group("rest").strip()
    # 期刊：Title. Journal, 12(3), 45–67.
    mj = re.match(r"^(?P<t>.+?[.?!])\s+(?P<j>[^.]+?),\s*(?P<vol>\d+)(?:\((?P<iss>[^)]+)\))?(?:,\s*(?P<pages>[\w\-–]+))?\.?$", rest)
    mc = re.match(r"^(?P<t>.+?)\.\s+In\s+(?P<eds>.+?)\s*\(Eds?\.\),\s*(?P<book>.+?)\s*\(pp\.\s*(?P<pages>[\d\-–]+)\)\.\s*(?P<pub>.+?)\.?$", rest)
    if mc:
        ref.type, ref.analytic = "M", True
        ref.title = mc.group("t")
        ref.container_authors = split_names(mc.group("eds"))
        ref.container, ref.pages, ref.publisher = mc.group("book"), mc.group("pages"), mc.group("pub")
    elif mj:
        ref.type = "J"
        ref.title = mj.group("t").rstrip(".")
        ref.container, ref.volume = mj.group("j"), mj.group("vol")
        ref.issue, ref.pages = mj.group("iss") or "", mj.group("pages") or ""
    else:
        parts = [p.strip() for p in re.split(r"\.\s+", rest) if p.strip()]
        ref.title = parts[0] if parts else rest
        if len(parts) >= 2:
            ref.type = "M"
            ref.publisher = parts[-1].rstrip(".")
            ed = re.search(r"\((\d+(?:st|nd|rd|th)\s*ed\.?)\)", ref.title)
            if ed:
                ref.edition, ref.title = ed.group(1), ref.title.replace(ed.group(0), "").strip()
        else:
            ref.parsed = False
    ref.lang = "zh" if has_cjk(ref.title) else "en"
    return ref


def fullwidth_marks(s: str) -> str:
    """全角的方括号、句点、数字两边的括号和连接号先换成半角再拆；题名里的中文逗号、顿号不动。"""
    s = s.replace("［", "[").replace("］", "]").replace("【", "[").replace("】", "]")
    s = re.sub(r"\s*．\s*", ". ", s)
    s = re.sub(r"（\s*([\d/]+)\s*）", r"(\1)", s)
    s = re.sub(r"(?<=\d)\s*[－～]\s*(?=\d)", "-", s)
    return s.strip()


def parse_entry(raw: str, no: Optional[int] = None) -> Ref:
    ref = Ref(raw=raw.strip(), no=no)
    s = fullwidth_marks(ref.raw)
    m = NUM_PREFIX.match(s)
    if m and no is None:
        ref.no = int(next(g for g in m.groups() if g))
        s = s[m.end():]
    s = strip_tail_ids(s, ref)
    if not MARKER.search(s) and not ALIAS_MARKER.search(s):
        ma = APA.match(s)
        if ma and not has_cjk(s[:20]):
            return parse_apa(ma, ref)
    mk = MARKER.search(s)
    alias = ALIAS_MARKER.search(s)
    if alias and (not mk or alias.start() < mk.start()):
        ref.type = TYPE_ALIASES[alias.group(1).upper() if alias.group(1).isascii() else alias.group(1)]
        ref.add("改", "类型标识", f"「{alias.group(0)}」不是国标代码，改为 [{ref.type}]")
        pre, post = s[:alias.start()], s[alias.end():]
    elif mk:
        code = mk.group(1).upper()
        ref.type = code
        ref.carrier = (mk.group(2) or "").upper().replace("0", "O")
        if mk.group(1) != code or (mk.group(2) and mk.group(2) != ref.carrier):
            ref.add("改", "类型标识", f"「{mk.group(0)}」写法不规范，改为 [{code}{'/' + ref.carrier if ref.carrier else ''}]")
        pre, post = s[:mk.start()], s[mk.end():]
    else:
        pre, post = s, ""
    names, etal, ayear, rest = split_authors_title(pre)
    ref.authors, ref.had_etal = names, etal
    if ayear:
        ref.year, ref.year_first = ayear, True
    if not mk and not alias:
        # 没有类型标识：题名在第一个分隔符（或 //）前，后面是出处
        mm = SEP.search(rest)
        if "//" in rest and (not mm or rest.find("//") < mm.start()):
            rest, post = rest[:rest.find("//")], rest[rest.find("//"):]
        elif mm:
            rest, post = rest[:mm.start()], rest[mm.end():]
        else:
            post = ""
    ref.title = rest.strip().strip("．。.").strip()
    ref.lang = "zh" if has_cjk(ref.title) or (not ref.title and has_cjk(pre)) else "en"
    post = post.strip().lstrip(".．。").strip()
    if "//" in post[:80] or post.startswith("／／"):
        ref.analytic = True
        head, _, tail = post.replace("／／", "//").partition("//")
        if head.strip(" .．。"):
            ref.other_resp = head.strip(" .．。")
        post = tail
    elif post and OTHER_RESP.search(post.split(".")[0].split("．")[0].strip()) and ref.type not in ("J", "N"):
        first, _, post = _split_first(post)
        ref.other_resp = first
    take_title_number(ref)
    ok = _parse_post(post, ref)
    if not ref.type:
        _infer_type(ref, post)
    ref.parsed = (ok or ref.type in ("EB", "S") or (not post and bool(ref.title))) and bool(ref.type)
    if not ref.title:
        ref.parsed = False
    return ref


def _split_first(post: str) -> Tuple[str, str, str]:
    m = re.search(r"(?<=[^A-Z])[.．。]\s*", post)
    if not m:
        return post, "", ""
    return post[:m.start()].strip(), ".", post[m.end():]


def _parse_post(post: str, ref: Ref) -> bool:
    t = ref.type
    post = post.strip()
    if not post:
        return False
    if ref.analytic:
        return parse_container(post, ref)
    if not t and re.search(r"[:：][^,，:：]*?(出版社|书局|印书馆|出版|Press|Publish|大学|University)", post) and parse_pubinfo(post, ref, ref.year_first):
        return True
    if t == "J" or (not t and (JOURNAL.match(post) or (ref.year_first and JOURNAL_AY.match(post))) and not NEWS.match(post)):
        if parse_journal(post, ref):
            if not t:
                ref.type = "J"
                ref.add("核", "类型标识", "原文没有类型标识，按「刊名, 年, 卷(期): 页码」判为期刊 [J]，请核对")
            return True
        if t == "J":
            # 只有刊名和在线日期（2025 优先出版写法）
            mn = NEWS.match(post)
            if mn:
                ref.container, ref.date = mn.group("p").strip(), norm_date(mn.group("date"))
                return True
            ref.container = post
            return False
    if t == "N" or (not t and NEWS.match(post)):
        mn = NEWS.match(post)
        if mn:
            ref.container, ref.date, ref.issue = mn.group("p").strip(), norm_date(mn.group("date")), (mn.group("ed") or "")
            if not t:
                ref.type = "N"
                ref.add("核", "类型标识", "原文没有类型标识，按「报纸名, 日期(版次)」判为报纸 [N]，请核对")
            return True
        ref.container = post
        return False
    if t in ("P", "R") or (t == "" and DATE_ONLY.match(post)):
        md = DATE_ONLY.match(post)
        if md:
            ref.date, ref.pages = norm_date(md.group("date")), (md.group("pages") or "").strip()
            return True
    if t in ("EB", "DS", "PP", "CP", "DB"):
        segs = [x.strip() for x in re.split(r"(?<![A-Z])[.．。]\s+", post) if x.strip()]
        if segs and re.match(r"^(V\d[\d.]*|版本\s*\S+)$", segs[0]):
            ref.version = segs.pop(0)
        left = ". ".join(segs)
        if left and not parse_pubinfo(left, ref, ref.year_first):
            ref.publisher = left
        return True
    return parse_pubinfo(post, ref, ref.year_first)


def _infer_type(ref: Ref, post: str) -> None:
    text = f"{ref.title} {post} {ref.publisher}"
    if ref.analytic:
        conf = re.search(r"会议|论文集|研讨会|年会|Proceedings|Conference|Symposium|Workshop", ref.container, re.I)
        ref.type = "C" if conf else "M"
    elif re.search(r"学位论文|硕士|博士|thesis|dissertation", text, re.I) or (
            ref.publisher and re.search(r"(大学|学院|University|研究院|研究所|Institute of Technology)$", ref.publisher)
            and not re.search(r"出版社|Press", ref.publisher)):
        ref.type = "D"
    elif ref.subtitle_no and STD_NO.fullmatch(ref.subtitle_no):
        ref.type = "S"
    elif re.search(r"报告|白皮书|Report", ref.title, re.I) and ref.publisher:
        ref.type = "R"
    elif re.search(r"会议|论文集|Proceedings", ref.title, re.I) and ref.publisher:
        ref.type = "C"
    elif ref.publisher:
        ref.type = "M"
    elif ref.url:
        ref.type, ref.carrier = "EB", "OL"
    if ref.type:
        ref.add("核", "类型标识", f"原文没有类型标识，按内容判为 [{ref.type}{'/' + ref.carrier if ref.carrier else ''}]，请核对")
    else:
        ref.parsed = False
        ref.add("补", "类型标识", "原文没有类型标识，也看不出是哪类文献，请告诉我它是图书、期刊、学位论文还是别的")
