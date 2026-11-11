"""按 GB/T 7714（2015 或 2025）把字段排成一条著录。顺序编码制、著者-出版年制两种。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from ref_model import Ref, has_cjk

PARTICLES = {"van", "von", "der", "den", "de", "da", "di", "du", "del", "della", "des", "dos", "le", "la", "ter", "ten", "bin", "al"}
ORG = re.compile(r"(University|Society|Organization|Organisation|Inc\b|Department|Association|Institute|Committee|Ltd|"
                 r"Center|Centre|Agency|Office|Bureau|Group|Ministry|Council|Foundation|Federation|Laboratory|"
                 r"Commission|Library|Museum|Academy|Corporation|Company|\bIHME\b|\bWHO\b)", re.I)
PINYIN_SURNAMES = set("""li wang zhang liu chen yang huang zhao wu zhou xu sun ma zhu hu guo he gao lin luo zheng liang xie song
tang han feng deng cao peng zeng xiao tian dong yuan pan cai jiang yu du ye cheng wei su lv lu ding ren shen yao jin jia fu fan
fang shi tan liao zou xiong qiu qin jiang yin xue yan duan lei hou long hao kong shao mao wan gu lai qian wen niu hong gong
kang ou bai cui mo""".split())


@dataclass(frozen=True)
class Opts:
    edition: str = "2015"          # 2015 / 2025
    style: str = "numeric"         # numeric / author-year
    punct: str = "half"            # half：半角加空格；mixed：照 2025 原文排版（中文逗号冒号括号全角）；tight：半角不加空格
    dash: str = "-"
    max_authors: int = 3
    upper_surname: bool = True     # 西文和拼音姓全大写（2015 惯例）；2025 默认首字母大写
    keep_cite_date: bool = False   # 2025 版期刊、图书等在线文献原文带的引用日期是否保留
    require_doi: bool = False
    etal_comma: bool = True        # 「肖书海, 等」；个别学校要「肖书海 等」

    @property
    def dot(self) -> str:
        return "." if self.punct == "tight" else ". "

    @property
    def colon(self) -> str:
        return {"half": ": ", "mixed": "：", "tight": ":"}[self.punct]

    @property
    def comma(self) -> str:
        return {"half": ", ", "mixed": "，", "tight": ","}[self.punct]

    @property
    def lp(self) -> str:
        return "（" if self.punct == "mixed" else "("

    @property
    def rp(self) -> str:
        return "）" if self.punct == "mixed" else ")"


def make_opts(edition: str = "2015", **kw) -> Opts:
    if "upper_surname" not in kw or kw["upper_surname"] is None:
        kw["upper_surname"] = edition == "2015"
    kw = {k: v for k, v in kw.items() if v is not None}
    return Opts(edition=edition, **kw)


# ---------- 人名 ----------

def _cap(word: str) -> str:
    return " ".join("-".join("'".join(p[:1].upper() + p[1:].lower() for p in w.split("'")) for w in sp.split("-"))
                    for sp in word.split(" "))


def name_parts(tok: str):
    """西文名 → (姓, [名或缩写], 后缀, 是否按「名在前」理解)。中文、机构返回 None。"""
    t = tok.strip()
    if has_cjk(t) or ORG.search(t) or not t:
        return None
    suffix = ""
    m = re.search(r"[,，]?\s*\b(Jr|Sr|II|III|IV)\.?$", t)
    if m:
        suffix, t = m.group(1), t[:m.start()].strip()
    words = [w for w in re.split(r"\s+", t.replace(".", ". ").strip()) if w]
    words = [w.rstrip(".") for w in words]
    if not words:
        return None
    def is_init(w: str) -> bool:
        return bool(re.fullmatch(r"[A-Z]{1,3}|[A-Z]-[A-Z]", w)) and not (len(w) > 1 and w in ("LI", "WU", "HU", "XU", "MA", "HE", "YU", "LU", "DU", "GU", "FU", "SU"))
    # 姓 + 缩写名：Smith J A / SMITH JA
    if len(words) >= 2 and not is_init(words[0]) and all(is_init(w) for w in words[1:]):
        inits = []
        for w in words[1:]:
            inits += list(w.replace("-", "")) if re.fullmatch(r"[A-Z]{2,3}", w) else [w]
        return words[0], inits, suffix, False
    # 缩写名 + 姓：J A Smith
    if len(words) >= 2 and all(is_init(w) for w in words[:-1]) and not is_init(words[-1]):
        return words[-1], [c for w in words[:-1] for c in (list(w) if re.fullmatch(r"[A-Z]{2,3}", w) else [w])], suffix, False
    # 带前缀的姓：van der Waals J D / De Morgan A
    low = [w.lower() for w in words]
    k = 0
    while k < len(words) - 1 and low[k] in PARTICLES:
        k += 1
    if k and all(is_init(w) for w in words[k + 1:]):
        return " ".join(words[:k + 1]), words[k + 1:], suffix, False
    if len(words) == 1:
        return words[0], [], suffix, False
    # 全是完整单词：拼音姓在前（Li Jiangning）或姓全大写（SMITH John）照姓在前；否则按「名 姓」理解
    if low[0] in PINYIN_SURNAMES or words[0].isupper():
        return words[0], words[1:], suffix, False
    return words[-1], words[:-1], suffix, True


def fmt_name(tok: str, opts: Opts, ref: Ref) -> str:
    t = tok.strip()
    if has_cjk(t):
        return t if re.search(r"[A-Za-z]", t) else re.sub(r"\s+", "", t)
    p = name_parts(t)
    if p is None:
        return t
    fam, given, suffix, flipped = p
    if flipped:
        ref.add("核", "著者", f"「{t}」按名在前、姓在后理解，排成姓在前；若「{given[0] if given else ''}」才是姓请告诉我")
    pinyin = fam.lower() in PINYIN_SURNAMES and given and all(len(g) > 1 and g.isalpha() for g in given)
    fam_out = fam.upper() if opts.upper_surname else (_cap(fam) if fam.isupper() or fam.islower() else fam)
    if fam_out != fam and len(fam) > 1:
        ref.add("改", "著者", "西文、拼音姓按 " + ("2015 版惯例全大写（SMITH J A）" if opts.upper_surname else
                                              "2025 版首字母大写（Smith J A）"))
    if pinyin:
        g = " ".join(_cap(x) for x in given)
        out = f"{fam_out} {g}"
    else:
        inits = []
        for g in given:
            if re.fullmatch(r"[A-Z]-[A-Z]", g):
                inits.append(g)
            elif "-" in g:
                inits.append("-".join(x[:1].upper() for x in g.split("-") if x))
            else:
                inits.append(g[:1].upper())
        out = " ".join([fam_out] + inits)
    return f"{out} {suffix}".strip()


def fmt_authors(names: List[str], had_etal: bool, ref: Ref, opts: Opts, label: str = "著者") -> str:
    if not names:
        return ""
    zh = ref.lang == "zh"
    etal = "等" if zh else "et al."
    out = [fmt_name(n, opts, ref) for n in names]
    if len(out) > opts.max_authors:
        ref.add("改", label, f"{label} {len(out)} 人，超过 {opts.max_authors} 人只列前 {opts.max_authors} 人，后加「{etal}」")
        out, had_etal = out[:opts.max_authors], True
    elif had_etal and len(out) < opts.max_authors:
        ref.add("补", label, f"原文只列了 {len(out)} 位{label}就写了「{etal}」，不替你编人名（认得这篇文献也不凭记忆补），两种改法："
                f"原文作者多于 {opts.max_authors} 人 → 照原文补第 {len(out) + 1}~{opts.max_authors} 位再加「{etal}」；"
                f"原文就这 {len(out)} 位 → 删掉「{etal}」")
    s = opts.comma.join(out)
    if had_etal:
        s += (opts.comma if opts.etal_comma else " ") + etal
    return s


# ---------- 其他字段 ----------

def fmt_pages(p: str, opts: Opts, ref: Ref) -> str:
    if not p:
        return ""
    s = re.sub(r"^(?:pp?\.|第)\s*|\s*页$", "", p.strip(), flags=re.I)
    s = re.sub(r"\s*[-–—~～－]+\s*", opts.dash, s)
    s = re.sub(r"\s*[,，]\s*", ",", s)
    m = re.fullmatch(r"(\d+)" + re.escape(opts.dash) + r"(\d+)", s)
    if m:
        a, b = m.groups()
        if len(b) < len(a):
            full = a[: len(a) - len(b)] + b
            ref.add("改", "页码", f"止页「{b}」是简写，补全为 {a}{opts.dash}{full}")
            b = full
            s = f"{a}{opts.dash}{b}"
        if int(b) < int(a):
            ref.add("核", "页码", f"起页 {a} 大于止页 {b}，请对照原文核对")
    return s


def fmt_edition(e: str, ref: Ref) -> str:
    if not e:
        return ""
    s = e.strip().rstrip(".")
    if re.fullmatch(r"第?\s*1\s*版|1st\s*ed(?:ition)?", s, re.I):
        ref.add("改", "版本", f"「{e}」：第 1 版不著录，已删")
        return ""
    m = re.fullmatch(r"第\s*(\d+)\s*版", s)
    if m:
        ref.add("改", "版本", f"「{e}」改为「{m.group(1)}版」")
        return f"{m.group(1)}版"
    m = re.fullmatch(r"(\d+(?:st|nd|rd|th))\s*ed(?:ition)?", s, re.I)
    if m:
        return f"{m.group(1)} ed."
    return s if not re.search(r"ed$", s) else s + "."


def fmt_title(t: str, ref: Ref, opts: Opts) -> str:
    t = t.strip().rstrip(".．。")
    if ref.lang == "zh":
        t = re.sub(r"\s*[:：]\s*", opts.colon.strip() + (" " if opts.punct == "half" else ""), t, count=1)
    else:
        t = re.sub(r"\s*:\s*", ": ", t, count=1)
    return t


def marker(ref: Ref) -> str:
    return f"[{ref.type}{'/' + ref.carrier if ref.carrier else ''}]" if ref.type else ""


def year_of(ref: Ref) -> str:
    return re.sub(r"[^\dA-Za-z\[\]]", "", ref.year) if ref.year else ""


def render(ref: Ref, opts: Opts) -> str:
    """一条参考文献的著录正文（不含序号）。"""
    if not ref.parsed:
        return ref.raw
    o, ay, e25 = opts, opts.style == "author-year", opts.edition == "2025"
    parts: List[str] = []
    au = fmt_authors(ref.authors, ref.had_etal, ref, o)
    if ay:
        au = au or ("佚名" if ref.lang == "zh" else "Anon")
        y = year_of(ref) or _ay_year(ref)
        parts.append(f"{au}{o.comma}{y}" if y else au)
    elif au:
        parts.append(au)
    title = fmt_title(ref.title, ref, o)
    if ref.type == "S" and ref.subtitle_no:
        no = re.sub(r"\s*[-–—]\s*(\d{4})$", "—\\1", ref.subtitle_no) if e25 else ref.subtitle_no
        title = f"{no} {title}" if e25 else f"{title}{o.colon}{no}"
        if e25 and (ref.place or ref.publisher or not ref.title.startswith(ref.subtitle_no)):
            ref.add("改", "标准", "2025 版标准著录为「标准号 标准名称[S]」：编号移到名称前，出版地、出版者和出版年这组出版项不再著录；标准号里的年份（如 —2015）照留")
    elif ref.subtitle_no:
        title = f"{title}{o.colon}{ref.subtitle_no}"
    t = title + marker(ref)
    tail = _source(ref, o, ay, e25)
    if ref.analytic:
        resp = (o.dot + ref.other_resp) if ref.other_resp else ""
        parts.append(t + resp + "//" + tail)
    else:
        if ref.other_resp:
            t += o.dot + _resp(ref.other_resp, o)
        ed = fmt_edition(ref.edition, ref)
        if ed:
            t += o.dot + ed
        parts.append(t + (((" " if o.punct != "tight" else "") if t.endswith(".") else o.dot) + tail if tail else ""))
    out = ""
    for p in (x for x in parts if x):
        out = p if not out else out + (" " if out.endswith(".") else o.dot) + p
    out = _links(out, ref, o, e25)
    return out


def _resp(s: str, o: Opts) -> str:
    return re.sub(r"\s*[,，]\s*", o.comma, s.strip())


def _ay_year(ref: Ref) -> str:
    d = ref.update_date or ref.date
    if d:
        ref.add("改", "出版年", f"著者-出版年制要出版年，原文没有，取{('更新日期' if ref.update_date else '发布日期')} {d} 的年份")
        return d[:4]
    if ref.cite_date:
        ref.add("改", "出版年", f"原文没有出版年，按惯例取引用日期 {ref.cite_date} 的年份并加方括号")
        return f"[{ref.cite_date[:4]}]"
    return ""


def _pub(ref: Ref, o: Opts, ay: bool, with_year: bool = True) -> str:
    s = ""
    if ref.place or ref.publisher:
        if ref.place and ref.publisher:
            s = f"{ref.place}{o.colon}{ref.publisher}"
        else:   # 缺的那项不替买家写「不详」，留给【待补】
            s = ref.place or ref.publisher
    y = year_of(ref)
    if y and with_year and not ay:
        s = f"{s}{o.comma}{y}" if s else y
    pg = fmt_pages(ref.pages, o, ref)
    if pg:
        s = f"{s}{o.colon}{pg}" if s else pg
    return s


def _source(ref: Ref, o: Opts, ay: bool, e25: bool) -> str:
    t = ref.type
    if ref.analytic:
        ca = fmt_authors(ref.container_authors, False, ref, o, "图书责任者") if ref.container_authors else ""
        head = (ca + o.dot if ca else "") + fmt_title(ref.container, ref, o)
        ed = fmt_edition(ref.edition, ref)
        if ed:
            head += o.dot + ed
        pub = _pub(ref, o, ay)
        if not ref.place and not ref.publisher and t == "C":
            y = "" if ay else year_of(ref)
            pg = fmt_pages(ref.pages, o, ref)
            return head + (o.comma + y if y else "") + (o.colon + pg if pg else "")
        return head + (o.dot + pub if pub else "")
    if t == "J":
        s = ref.container
        if ref.date and not (ref.volume or ref.issue or ref.year):
            return f"{s}{o.comma}{ref.date}"
        if not ay and ref.year:
            s += o.comma + year_of(ref)
        if ref.volume:
            s += o.comma + ref.volume
        if ref.issue:
            s += f"{o.lp}{_issue(ref.issue)}{o.rp}"
        pg = fmt_pages(ref.pages, o, ref)
        if pg:
            s += o.colon + pg
        return s
    if t == "N":
        s = f"{ref.container}{o.comma}{ref.date}"
        if ref.issue:
            s += f"{o.lp}{ref.issue}{o.rp}"
        return s
    if t == "P":
        s = ref.date
        pg = fmt_pages(ref.pages, o, ref)
        return s + (o.colon + pg if pg and s else "")
    if t == "S" and e25:
        return ""
    if t == "R" and ref.date and not ref.publisher:
        pg = fmt_pages(ref.pages, o, ref)
        return ref.date + (o.colon + pg if pg else "")
    if t in ("EB", "DS", "PP", "CP", "DB"):
        bits = []
        if ref.version:
            bits.append(ref.version)
        pub = _pub(ref, o, ay) if (ref.place or ref.publisher or ref.year) and t == "EB" else ""
        if t in ("DS", "PP") and ref.publisher:
            pub = ref.publisher
        if pub:
            bits.append(pub)
        return o.dot.join(bits)
    return _pub(ref, o, ay)


def _issue(s: str) -> str:
    return re.sub(r"\s*[,，、/]\s*", "/", s.strip())


def _links(body: str, ref: Ref, o: Opts, e25: bool) -> str:
    dates = ""
    want_cite = ref.cite_date and (not e25 or ref.type in ("EB", "DS", "PP") or o.keep_cite_date)
    if ref.cite_date and not want_cite:
        ref.add("改", "引用日期", f"2025 版只有网站网页、数据集、预印本著录引用日期，[{ref.type}] 原文的 [{ref.cite_date}] 已删")
    if ref.type in ("EB", "DS", "PP", "R") and ref.update_date:
        dates += f"{o.lp}{ref.update_date}{o.rp}"
    if want_cite:
        dates += f"[{ref.cite_date}]"
    if dates:
        if ref.type in ("EB",) or (ref.type == "R" and not ref.publisher) or ref.type in ("DS", "PP"):
            joiner = "" if ref.type in ("DS", "PP") and ref.publisher and not body.endswith("]") else o.dot
            body = body + joiner + dates
        else:
            body += dates
    url, doi = ref.url, ref.doi
    if url and not ref.online:
        # 印刷本带了网址：2015、2025 都只给电子资源著录获取路径
        ref.add("问", "获取和访问路径", "原文有网址但类型标识没有 /OL：引自网络版就改成 [" + ref.type + "/OL]" +
                ("" if e25 else " 并补引用日期") + "；引自印刷版就删网址。脚本先原样保留，等你定")
    if url and doi and (e25 and doi.lower() in url.lower()):
        doi = ""
    if url and doi and not e25 and "doi.org/" in url.lower() and not ref.online:
        url = ""
    if url:
        body += o.dot + url
    if doi:
        body += o.dot + "DOI: " + doi
    if ref.pid:
        body += o.dot + ref.pid
    return body + "."
