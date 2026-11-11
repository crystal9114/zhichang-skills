"""逐条校对：缺什么要买家补、什么可疑要核对、什么已经改好。只用确定的规则，不编页码、不编 DOI。"""
from __future__ import annotations

import copy
import datetime as dt
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from ref_model import CARRIERS_2015, CARRIERS_2025, DOI_VALID, TYPE_NAMES, TYPES_2015, TYPES_2025, Ref, load_tsv
from ref_parse import parse_entry, split_entries
from ref_render import Opts, render

_PLACES: Dict[str, str] = {}


@dataclass
class Checked:
    ref: Ref
    text: str          # 改好的著录（不含序号）


def places() -> Dict[str, str]:
    if not _PLACES:
        _PLACES.update(load_tsv("places.txt"))
    return _PLACES


def need(ref: Ref, fld: str, what: str) -> None:
    ref.add("补", fld, what)


def check_required(ref: Ref, opts: Opts) -> None:
    t, e25 = ref.type, opts.edition == "2025"
    if not ref.title:
        need(ref, "题名", "缺题名")
    if not ref.authors and t not in ("S", "N", ""):
        need(ref, "著者", "原文没有著者，不替你编：照原文补个人或机构名（知网文章页、期刊官网可查）；确实没有著者的，告诉我，按无著者从题名起著录")
    if t == "J":
        if not ref.container:
            need(ref, "刊名", "缺刊名")
        if not ref.year and not ref.date:
            need(ref, "出版年", "缺出版年，去哪查：知网文章页或期刊官网该期目录")
        if not ref.volume and not ref.issue and not ref.date:
            need(ref, "卷期", "卷号和期号都没有，至少补一项（只有期号写成「年(期)」）；去哪查：知网文章页或期刊官网该期目录")
        if not ref.pages and not ref.date:
            need(ref, "页码", "期刊论文的起止页码（或文章编号）要写，不要估；去哪查：知网文章页（页码一栏）或期刊官网该期目录、PDF 首页页眉")
    elif t == "N":
        if not ref.date:
            need(ref, "出版日期", "报纸要写出版日期 YYYY-MM-DD")
        if not ref.issue:
            need(ref, "版次", "报纸要写版次，如「(15)」")
    elif t == "P":
        if not ref.subtitle_no:
            need(ref, "专利号", "缺专利号或申请号，写在题名后「: 号码」")
        if not ref.date:
            need(ref, "公告日期", "缺公告（公开）日期 YYYY-MM-DD")
        if e25 and ref.subtitle_no and not re.match(r"\s*[A-Z]{2}", ref.subtitle_no):
            ref.add("问", "专利号", "2025 版专利号带国别前缀（中国专利写 CN，如 CN200610171314.3），请照专利文献原文补，"
                    "不确定是哪国专利就别加；引用了具体页的还可加引文页码")
    elif t == "S":
        if not ref.subtitle_no:
            need(ref, "标准编号", "缺标准编号，如 GB/T 7714—2015")
        if not e25 and not (ref.place and ref.publisher):
            ref.add("问", "出版项", "2015 版标准按专著著录要写「出版地: 出版者, 出版年」（多为 北京: 中国标准出版社），不少学校不要求；要补请给出版信息")
    elif t in ("EB", "DS", "PP"):
        if not ref.url:
            need(ref, "获取和访问路径", "网络资源要写网址")
        if not ref.cite_date:
            need(ref, "引用日期", "引用日期是你自己打开这个网页的那天 [YYYY-MM-DD]，只有你知道，不能替你填；告诉我是哪天，可用 --cite-date 统一补")
    elif t in ("M", "D", "R", "C", "G", "A", "CM") or (ref.analytic and t):
        if ref.analytic and not ref.container:
            need(ref, "出处", "析出文献「//」后面要写所在图书或论文集的题名")
        is_conf25 = e25 and t == "C" and ref.analytic and not ref.publisher
        is_rep_dated = t == "R" and (ref.date or (ref.online and ref.update_date)) and not ref.publisher
        if t == "R" and ref.online and not (ref.publisher or ref.date or ref.update_date):
            need(ref, "出版项", "网络版报告要写发布日期（如「(2013-04-16)」）或「出版地: 出版者, 年」，请照原网页补")
        elif not is_conf25 and not is_rep_dated:
            if not ref.publisher:
                need(ref, "出版者" if t != "D" else "学位授予单位", "缺出版者；去哪查：图书版权页或出版社官网" if t != "D" else "缺学位授予单位；去哪查：学位论文封面或知网学位论文页")
            if not ref.place:
                guess = places().get(ref.publisher.strip()) if ref.publisher else None
                if guess:
                    ref.place = guess
                    ref.add("核", "出版地", f"原文缺出版地，按「{ref.publisher}」所在地补「{guess}」，请核对")
                else:
                    need(ref, "出版地" if t != "D" else "授予单位所在地", "缺出版地（城市名）；去哪查：图书版权页（CIP 数据里「出版发行」一行）或出版社官网；实在查不到可写「[出版地不详]」")
            if not ref.year:
                need(ref, "出版年", "缺出版年；去哪查：图书版权页（「版次」一行）、学位论文封面或出版社官网")
        if ref.analytic and not ref.pages:
            need(ref, "页码", "析出文献要写它在书或论文集里的起止页码；去哪查：论文集目录或知网会议论文页")
        if t == "D" and e25 and not ref.pages:
            ref.add("问", "引文页码", "2025 版学位论文「引文页码」有则必备：引用了具体页就补上页码")
    if ref.online and t not in ("EB", "DS", "PP"):
        if not ref.url:
            need(ref, "获取和访问路径", f"[{t}/OL] 是网络版，要写网址")
        if not e25 and not ref.cite_date:
            need(ref, "引用日期", f"2015 版 [{t}/OL] 要写引用日期 [YYYY-MM-DD]（你访问的那天），请补")
    if opts.require_doi and t == "J" and not ref.doi:
        ref.add("补", "DOI", "学校/期刊要求写 DOI：请到期刊官网或知网文章页照抄，没有就说没有，不要编")


def check_values(ref: Ref, opts: Opts, today: dt.date) -> None:
    valid_t = TYPES_2025 if opts.edition == "2025" else TYPES_2015
    if ref.type and ref.type not in valid_t:
        ref.add("核", "类型标识", f"[{ref.type}] 不是 GB/T 7714—{opts.edition} 的类型代码" +
                ("（[PP] 预印本是 2025 版才有的，2015 版可用 [Z] 或按 [EB/OL]）" if ref.type == "PP" else ""))
    valid_c = CARRIERS_2025 if opts.edition == "2025" else CARRIERS_2015
    if ref.carrier and ref.carrier not in valid_c:
        ref.add("核", "载体标识", f"/{ref.carrier} 不是国标载体代码（联机网络写 /OL）")
    if ref.type == "EB" and not ref.carrier:
        ref.carrier = "OL"
        ref.add("改", "类型标识", "网页一定是联机网络资源，[EB] 改为 [EB/OL]")
    if ref.type in ("DS", "PP") and not ref.carrier and ref.url:
        ref.carrier = "OL"
        ref.add("改", "类型标识", f"[{ref.type}] 有网址，改为 [{ref.type}/OL]")
    y = re.search(r"\d{4}", ref.year or "")
    if y and int(y.group()) > today.year:
        ref.add("核", "出版年", f"出版年 {ref.year} 晚于今年，请核对（期刊提前在线出版、已排进下一年卷期的可忽略）")
    elif y and int(y.group()) < 1400:
        ref.add("核", "出版年", f"出版年 {ref.year} 不合常理，请核对")
    for fld, val in (("引用日期", ref.cite_date), ("更新日期", ref.update_date), ("出版日期", ref.date)):
        if not val:
            continue
        try:
            d = dt.date.fromisoformat(val)
        except ValueError:
            ref.add("核", fld, f"{fld}「{val}」不是有效日期，格式应为 YYYY-MM-DD")
            continue
        if d > today:
            ref.add("核", fld, f"{fld} {val} 晚于今天，请核对")
    if ref.cite_date and ref.update_date and ref.cite_date < ref.update_date:
        ref.add("核", "引用日期", "引用日期早于更新日期，不可能先引用后发布，请核对")
    if ref.doi and not DOI_VALID.match(ref.doi):
        ref.add("核", "DOI", f"DOI「{ref.doi}」格式不对（应以 10.xxxx/ 开头），请对照原文照抄")
    if ref.lang == "zh" and re.search(r"et\s*al", ref.raw, re.I):
        ref.add("改", "著者", "中文文献省略著者用「等」，不用 et al.")
    if ref.lang == "en" and re.search(r"[,，]\s*等", ref.raw):
        ref.add("改", "著者", "西文文献省略著者用「et al.」，不用「等」")
    if ref.source_style == "apa":
        ref.add("改", "整体", "原文是 APA 写法，已按国标重排（姓在前、名缩写、加类型标识、年份移到出版项）")
    if re.search(r"[，：；（）［］．]", ref.raw.replace(ref.title, "")) and opts.punct != "mixed":
        ref.add("改", "标点", "著录符号统一为半角（逗号、冒号、括号、方括号）")


def check_entry(raw: str, no: Optional[int], opts: Opts, today: dt.date, cite_date: str = "",
                hook: Optional[Callable[[Ref], None]] = None) -> Checked:
    ref = parse_entry(raw, no)
    if hook and ref.parsed:
        hook(ref)
    if not ref.parsed:
        ref.add("核", "整体", "这条拆不开（可能缺分隔符或类型标识），原样保留；请照原文补全或告诉我它是哪类文献")
        return Checked(ref, ref.raw)
    if cite_date and ref.online or (cite_date and ref.type in ("EB", "DS", "PP")):
        if not ref.cite_date:
            ref.cite_date = cite_date
            ref.add("改", "引用日期", f"按你给的访问日期补引用日期 [{cite_date}]")
    check_values(ref, opts, today)
    check_required(ref, opts)
    if ref.year_first and opts.style == "numeric":
        ref.add("改", "整体", "原文是著者-出版年制写法（年份在著者后），已按顺序编码制把出版年移回出版项")
    r2 = copy.deepcopy(ref)
    text = render(r2, opts)
    raw = re.sub(r"^\s*[\[［]?\d+[\]］.．、]?\s*", "", ref.raw)
    if not any(i.field in ("标点", "标准", "整体", "引用日期") for i in r2.issues) and (_punct(text) != _punct(raw) or (
            not any(i.level == "改" for i in r2.issues) and _squash(text) != _squash(raw))):
        r2.add("改", "格式", "标点、空格按国标统一（全角改半角、符号后空一格、页码连接号用「-」）")
    return Checked(r2, text)


def _punct(s: str) -> str:
    return re.sub(r"[\w\u3400-\u9fff\s]", "", s).rstrip(".")


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s).rstrip(".")


def title_key(ref: Ref) -> str:
    return re.sub(r"[\W_]+", "", ref.title.lower())


def check_list(text: str, opts: Opts, today: Optional[dt.date] = None, cite_date: str = "",
               hook: Optional[Callable[[Ref], None]] = None) -> List[Checked]:
    return check_items(split_entries(text), opts, today, cite_date, hook)


def check_items(pairs: List[Tuple[Optional[int], str]], opts: Opts, today: Optional[dt.date] = None,
                cite_date: str = "", hook: Optional[Callable[[Ref], None]] = None) -> List[Checked]:
    today = today or dt.date.today()
    items = [check_entry(raw, no, opts, today, cite_date, hook) for no, raw in pairs]
    seen: Dict[str, int] = {}
    for i, c in enumerate(items, 1):
        k = title_key(c.ref)
        if len(k) >= 6:
            if k in seen:
                c.ref.add("核", "重复", f"和第 {seen[k]} 条题名相同，可能重复著录；顺序编码制同一文献只编一个号")
            else:
                seen[k] = i
    nos = [c.ref.no for c in items if c.ref.no is not None]
    if nos:
        expect = list(range(1, len(items) + 1))
        if nos != expect[: len(nos)]:
            dup = sorted({n for n in nos if nos.count(n) > 1})
            gaps = sorted(set(range(1, max(nos) + 1)) - set(nos))
            msg = []
            if dup:
                msg.append(f"序号 {dup} 重复")
            if gaps:
                msg.append(f"跳号 {gaps}")
            if not msg:
                msg.append("序号没有从 1 连续往下排")
            items[0].ref.add("改", "序号", "原列表" + "、".join(msg) + "，已按条目顺序重新编号；正文里的引注号要跟着改")
    return items


def type_name(code: str) -> str:
    return TYPE_NAMES.get(code, "未知")
