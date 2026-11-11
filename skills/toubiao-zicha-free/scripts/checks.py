"""把日期、金额这类「算错一个数就废标」的判断算死，不靠模型估。

  python3 scripts/checks.py validity --required 90 --promised 60 --source 投标函
  python3 scripts/checks.py cover --deadline 2026-12-10 --days 90 --until 2027-02-28 --what 投标保函
  python3 scripts/checks.py latest --until 2027-03-01 --days 90
  python3 scripts/checks.py checklist --rule 依法招标 --clause "P4|投标有效期120日；投标保证金5万元"
  python3 scripts/checks.py cert --deadline 2026-11-25 --until 2026-11-25 --what 安全生产许可证
  python3 scripts/checks.py amount --upper 壹佰贰拾叁万肆仟伍佰元整 --lower 1234050
  python3 scripts/checks.py cap --bid 760000 --cap 80万
  python3 scripts/checks.py deposit --required 2万 --paid 20000 --budget 100万
  python3 scripts/checks.py months --need 2026-05:2026-10 --have 2026-04:2026-09

每条输出一行结论：是否满足（满足/不满足/存疑）+ 一句原因，加 --json 输出 JSON 方便塞进偏离表。
口径：投标有效期从投标截止之日起算；保函、授权书要覆盖到「截止日 + N 天」才算稳（保守口径，
各地对起算日当天算不算第 1 天说法不一，差 1 天的判「存疑」并建议多留几天）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta

DIG = {c: i for i, c in enumerate("零壹贰叁肆伍陆柒捌玖")} | {c: i for i, c in enumerate("〇一二三四五六七八九")} | {"两": 2}
UNIT = {"拾": 10, "十": 10, "佰": 100, "百": 100, "仟": 1000, "千": 1000}


class CheckError(Exception):
    pass


def parse_date(s: str) -> date:
    m = re.fullmatch(r"\s*(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*日?\s*", s or "")
    if not m:
        raise CheckError(f"[E08] 日期「{s}」认不出，写成 2026-11-20")
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError as exc:
        raise CheckError(f"[E08] 日期「{s}」不存在（月或日超范围），先核对原文") from exc


def parse_upper(s: str) -> int:
    """中文大写金额 → 分。支持 亿/万/元(圆)/角/分/整(正)。"""
    s = re.sub(r"[\s人民币：:（）()]", "", s or "").replace("圆", "元").replace("正", "整")
    if not s or any(ch not in DIG and ch not in UNIT and ch not in "亿万元角分整" for ch in s):
        raise CheckError(f"[E08] 大写金额「{s}」里有认不出的字")
    if not any(ch in DIG for ch in s):
        raise CheckError(f"[E08] 大写金额「{s}」里没有数字，照开标一览表原文抄全，如 壹佰贰拾叁万肆仟伍佰元整")
    yuan, _, rest = s.partition("元") if "元" in s else (s, "", "")
    total = section = num = 0
    for ch in yuan:
        if ch in DIG:
            num = DIG[ch]
        elif ch in UNIT:
            section += (num or 1) * UNIT[ch]
            num = 0
        elif ch == "万":
            total += (section + num) * 10_000
            section = num = 0
        elif ch == "亿":
            total = (total + section + num) * 100_000_000
            section = num = 0
    total += section + num
    fen = total * 100
    m = re.search(r"([零壹贰叁肆伍陆柒捌玖])角", rest)
    fen += DIG[m.group(1)] * 10 if m else 0
    m = re.search(r"([零壹贰叁肆伍陆柒捌玖])分", rest)
    fen += DIG[m.group(1)] if m else 0
    return fen


def parse_lower(s: str) -> int:
    """小写金额 → 分。认 ¥、逗号、元、万元。"""
    t = re.sub(r"[\s¥￥,，人民币]", "", s or "")
    mult = 10_000 if t.endswith("万元") or t.endswith("万") else 1
    t = re.sub(r"(万元|万|元)$", "", t)
    if not re.fullmatch(r"\d+(\.\d{1,6})?", t):
        raise CheckError(f"[E08] 金额「{s}」认不出，写成 1234050 或 123.405万")
    return round(float(t) * mult * 100)


def positive(s: str, what: str) -> int:
    """限价、预算这类拿来比的基数，0 元说明抄错了，不往下算。"""
    fen = parse_lower(s)
    if fen <= 0:
        raise CheckError(f"[E08] {what}「{s}」是 0 元，先核对招标文件原文再算")
    return fen


def yuan(fen: int) -> str:
    return f"{fen / 100:,.2f} 元"


def r(status: str, why: str, **extra: object) -> dict:
    return {"status": status, "why": why, **extra}


def validity(a: argparse.Namespace) -> dict:
    src = (a.source or "").strip()
    if a.promised >= a.required:
        return r("满足", f"{src + '写的' if src else '承诺'} {a.promised} 天 ≥ 要求 {a.required} 天", risk="—")
    if src:
        return r("不满足", f"{src}写的有效期 {a.promised} 天短于招标文件要求 {a.required} 天，单列一行判；"
                 f"风险致命，投标无效（投标文件里别处写够了天数也一样，自相矛盾按短的算）。"
                 f"改法：删掉{src}这一句，或改成不少于 {a.required} 天", risk="致命")
    return r("不满足", f"承诺 {a.promised} 天 < 要求 {a.required} 天，风险致命，投标有效期不足按投标无效处理，"
             f"改成不少于 {a.required} 天", risk="致命")


AUTH_NOTE = "招标文件对授权期限有单独写法的，以招标文件对授权期限的要求为准"
GUARANTEE_NOTE = ("依据：招标文件对保函（保证金）有效期的要求；依法招标另有招标投标法实施条例第二十六条第一款"
                  "「投标保证金有效期应当与投标有效期一致」")


def _cover_kind(what: str) -> str:
    if "授权" in what or "委托" in what:
        return "auth"
    if any(k in what for k in ("保函", "保证金", "担保", "保险")):
        return "guarantee"
    return "other"


def cover(a: argparse.Namespace) -> dict:
    dl, until = parse_date(a.deadline), parse_date(a.until)
    end = dl + timedelta(days=a.days)
    what = a.what or "保函/授权书"
    kind = _cover_kind(what)
    calc = f"届满日 = 截止日 {dl} + {a.days} 天 = {end}（截止当天算第 1 天的口径是 {end - timedelta(days=1)}）"
    tail = {"auth": f"。{AUTH_NOTE}", "guarantee": f"。{GUARANTEE_NOTE}", "other": ""}[kind]
    if until >= end:
        return r("满足", f"{what}到 {until}，覆盖投标有效期届满日；{calc}{tail}", end=str(end), risk="—")
    if until >= end - timedelta(days=1):
        return r("存疑", f"{what}到 {until}，比保守届满日差 1 天，看起算日是否算第 1 天；{calc}；风险高，"
                 f"稳妥做法是延到 {end} 或之后{tail}", end=str(end), risk="高")
    risk = {"auth": "高", "guarantee": "致命"}.get(kind, "高")
    fix = ("把委托期限改到 " + f"{end} 或之后，或写「至投标有效期届满之日止」" if kind == "auth"
           else f"要求出具方延期到 {end} 或之后")
    return r("不满足", f"{what}到 {until}，早于投标有效期届满日，差 {(end - until).days} 天；{calc}；风险{risk}；"
             f"改法：{fix}{tail}", end=str(end), risk=risk)


def latest(a: argparse.Namespace) -> dict:
    """没给截止日时反推：到期日倒退 N 天就是最晚截止日。"""
    until = parse_date(a.until)
    last = until - timedelta(days=a.days)
    return r("待核", f"截止日在 {last} 及以前才够（{last} + {a.days} 天 = {until}），晚于 {last} 就不够；"
             f"请告诉我投标截止日", latest=str(last))


def cert(a: argparse.Namespace) -> dict:
    dl, until = parse_date(a.deadline), parse_date(a.until)
    what = a.what or "证书"
    if until < dl:
        return r("不满足", f"{what}有效期到 {until}，投标截止日 {dl} 时已过期，风险致命；附延续/换证后的新证，只有受理回执的先问代理机构认不认")
    if until == dl:
        return r("存疑", f"{what}恰好在截止日 {dl} 当天到期，风险高：截止时点还在有效期内，但资格审查在开标后，评审时可能已过期；附新证或延续受理材料，并书面问代理机构口径")
    if (until - dl).days <= 30:
        return r("满足", f"{what}到 {until}，截止日有效；30 天内到期，中标后签合同、履约时会被查，提前续")
    return r("满足", f"{what}到 {until}，截止日 {dl} 有效")


def amount(a: argparse.Namespace) -> dict:
    up, low = parse_upper(a.upper), parse_lower(a.lower)
    if up == low:
        return r("满足", f"大写 {yuan(up)} = 小写 {yuan(low)}")
    return r("不满足", f"大写是 {yuan(up)}，小写是 {yuan(low)}，差 {yuan(abs(up - low))}，风险高；政府采购按大写为准修正"
             f"（87号令第五十九条），修正后须投标人确认，不确认投标无效。交标前改成一致", upper=up / 100, lower=low / 100)


def cap(a: argparse.Namespace) -> dict:
    bid, c = parse_lower(a.bid), positive(a.cap, "限价/预算")
    if bid <= c:
        return r("满足", f"报价 {yuan(bid)} ≤ 限价/预算 {yuan(c)}")
    return r("不满足", f"报价 {yuan(bid)} 超过限价/预算 {yuan(c)}，超出 {yuan(bid - c)}，风险致命，超限价直接投标无效/否决")


def deposit(a: argparse.Namespace) -> dict:
    need, paid = parse_lower(a.required), parse_lower(a.paid)
    note = ""
    if a.budget:
        b = positive(a.budget, "预算/估算价")
        if need > b * 2 // 100:
            note = f"；另：要求的担保 {yuan(need)} 超过预算/估算价的 2%（{yuan(b * 2 // 100)}），招标文件本身可能违规，可在异议/质疑期限内提出"
    if paid >= need:
        return r("满足", f"提交 {yuan(paid)} ≥ 要求 {yuan(need)}{note}")
    return r("不满足", f"提交 {yuan(paid)} < 要求 {yuan(need)}，差 {yuan(need - paid)}，风险致命，未按要求提交投标担保按投标无效处理{note}")


def _months(spec: str) -> list[str]:
    m = re.fullmatch(r"(\d{4})-(\d{1,2}):(\d{4})-(\d{1,2})", spec or "")
    if not m:
        raise CheckError(f"[E08] 月份区间「{spec}」要写成 2026-05:2026-10")
    y, mo, y2, mo2 = map(int, m.groups())
    out = []
    while (y, mo) <= (y2, mo2):
        out.append(f"{y}-{mo:02d}")
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    return out


def months(a: argparse.Namespace) -> dict:
    need, have = _months(a.need), set(_months(a.have))
    miss = [m for m in need if m not in have]
    if not miss:
        return r("满足", f"要求的 {len(need)} 个月都在")
    return r("不满足", f"缺 {', '.join(miss)}（要求 {need[0]} 至 {need[-1]} 共 {len(need)} 个月），属资格证明不全，风险致命；补开含缺的月份的证明，月份以招标文件写明的为准", missing=miss)


# ───────── 只有招标文件：把抄下来的条款拆成固定表头的自查清单（格式 C） ─────────
# 每类一行的写法写死在这里，不靠模型记：页码、原文照用户给的，依据只引项目对应那一套、管这件事的那一条。
GOV, BID = "政府采购", "依法招标"
LAW = {
    "validity": {GOV: "87号令第二十三条：「投标文件中承诺的投标有效期应当不少于招标文件中载明的投标有效期」",
                 BID: "招标投标法实施条例第二十五条：「投标有效期从提交投标文件的截止之日起算」；第五十一条第（六）项："
                      "「投标文件没有对招标文件的实质性要求和条件作出响应」"},
    "deposit": {GOV: "87号令第六十三条第（一）项：「未按照招标文件的规定提交投标保证金的」",
                BID: "招标投标法实施条例没有专管保证金金额、到账的条，以招标文件为准"},
    "basic": {GOV: "政府采购法规没有基本户的条，以招标文件为准",
              BID: "招标投标法实施条例第二十六条第二款：「依法必须进行招标的项目的境内投标单位，以现金或者支票形式提交的"
                   "投标保证金应当从其基本账户转出」"},
    "deposit_term": {GOV: "以招标文件为准",
                     BID: "招标投标法实施条例第二十六条第一款：「投标保证金有效期应当与投标有效期一致」"},
    "joint": {GOV: "政府采购法第二十四条：「应当向采购人提交联合协议，载明联合体各方承担的工作和义务」",
              BID: "招标投标法实施条例第五十一条第（二）项：「投标联合体没有提交共同投标协议」"},
    "sign": {GOV: "87号令第六十三条第（二）项：「投标文件未按招标文件要求签署、盖章的」",
             BID: "招标投标法实施条例第五十一条第（一）项：「投标文件未经投标单位盖章和单位负责人签字」"},
    "cap": {GOV: "87号令第六十三条第（四）项：「报价超过招标文件中规定的预算金额或者最高限价的」",
            BID: "招标投标法实施条例第五十一条第（五）项：「投标报价低于成本或者高于招标文件设定的最高投标限价」"},
    "qual": {GOV: "87号令第六十三条第（三）项：「不具备招标文件中规定的资格要求的」",
             BID: "招标投标法实施条例第五十一条第（三）项：「投标人不符合国家或者招标文件规定的资格条件」"},
    "star": {GOV: "87号令第六十三条第（六）项：「法律、法规和招标文件规定的其他无效情形」",
             BID: "招标投标法实施条例第五十一条第（六）项：「投标文件没有对招标文件的实质性要求和条件作出响应」"},
}
HEAD_C = ("| 序号 | 类别 | 招标页码 | 条款原文 | 依据 | 要准备的材料 / 要签章的位置 | 我方响应 | 结论 | 风险 | 后果原话 | 打勾 |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|")


def _num(text: str, pat: str) -> str:
    m = re.search(pat, text)
    return m.group(1) if m else ""


def _row(cat: str, page: str, quote: str, law: str, prep: str, risk: str = "致命", result: str = "投标无效") -> dict:
    return {"cat": cat, "page": page, "quote": quote, "law": law, "prep": prep, "risk": risk, "result": result}


def _src(page: str, quote: str) -> str:
    return f"招标文件 {page}：{quote}"


def _validity_rows(page: str, q: str, rule: str) -> list[dict]:
    n = _num(q, r"有效期[^0-9]{0,8}(\d+)")
    prep = (f"投标函写投标有效期不少于 {n} 日（从投标截止之日起算）；报价表、承诺函里别另写更短的期限；"
            f"保函、授权委托书期限盖住届满日（截止日 + {n} 天，用 cover 子命令算）") if n else "投标函写的有效期不少于招标文件要求"
    return [_row("有效期", page, q, f"{_src(page, q)}；{LAW['validity'][rule]}", prep)]


def _deposit_rows(page: str, q: str, rule: str) -> list[dict]:
    rows = []
    res = "投标无效" if rule == GOV else "投标无效（以招标文件评标办法写法为准）"
    amt = _num(q, r"保证金[^0-9零壹贰叁肆伍陆柒捌玖一二三四五六七八九十]{0,6}([0-9.]+\s*万?元|[零壹贰叁肆伍陆柒捌玖拾佰仟万]+元)")
    term_only = not amt and ("有效期" in q) and not any(k in q for k in ("到账", "基本", "金额"))
    if not term_only:
        rows.append(_row("投标担保·金额", page, q, f"{_src(page, q)}；{LAW['deposit'][rule]}",
                         f"保证金 {amt or '按招标文件金额'} 足额，金额与招标文件逐位一致；形式按招标文件写的", "致命", res))
    if "到账" in q or "截止" in q:
        rows.append(_row("投标担保·到账时间", page, q, f"{_src(page, q)}；{LAW['deposit'][rule]}",
                         "投标截止时间前到账，留银行回单；跨行转账多留一两天", "致命", res))
    if "基本" in q:
        rows.append(_row("投标担保·付款账户", page, q, f"{_src(page, q)}；{LAW['basic'][rule]}",
                         "从投标人基本存款账户转出（一般户不行），附基本户开户证明或基本存款账户信息", "致命", res))
    if "有效期" in q or "保函" in q:
        rows.append(_row("投标担保·有效期", page, q, f"{_src(page, q)}；{LAW['deposit_term'][rule]}",
                         "保函（保证金）有效期不短于投标有效期，用 cover 子命令核到期日", "致命", res))
    return rows


def _sign_rows(page: str, q: str, rule: str) -> list[dict]:
    law = f"{_src(page, q)}；{LAW['sign'][rule]}"
    rows = []
    agent = next((k for k in ("委托代理人", "授权代表", "被授权人", "授权委托人") if k in q), "")
    if "法定代表人" in q or agent:
        who = f"法定代表人或其{agent}" if agent else "法定代表人本人（招标文件只写法定代表人的，别人签都不算）"
        rows.append(_row("签署·签字人资格", page, q, law, f"签字人只能是{who}，别人代签不算"))
    if "签字" in q or "签名" in q or "签署" in q:
        rows.append(_row("签署·签字", page, q, law, "签字处手写签名（电子标用个人 CA 签名），打印体、私章不算签字"))
    if "章" in q:
        seal = "单位章" if "单位章" in q else ("单位公章" if "公章" in q else "章")
        rows.append(_row("签署·盖章", page, q, law, f"格式页落款处加盖{seal}；合同章、部门章不能代替"))
    if agent:
        rows.append(_row("签署·授权委托书", page, q, _src(page, q),
                         f"{agent}签字的，附授权委托书（按招标文件格式），委托期限盖住投标有效期届满日",
                         "高", "以招标文件为准"))
    return rows


def _classify(page: str, q: str, rule: str) -> list[dict]:
    if "联合体" in q:
        if any(k in q for k in ("不接受", "不允许", "不得")):
            return [_row("联合体", page, q, _src(page, q), "以单个投标人名义投标，不组联合体")]
        risk = "致命" if rule == BID else "高"
        return [_row("联合体投标", page, q, f"{_src(page, q)}；{LAW['joint'][rule]}",
                     "组联合体投标的：提交共同投标协议（法定要求，招标文件这段没写，依据见左列），写明各方承担的工作和责任，"
                     "各方按要求签章；不组联合体的这一行划掉", risk, "投标无效" if rule == BID else "以招标文件为准")]
    if any(k in q for k in ("身份证", "授权委托书")) and "签字" not in q:
        return [_row("签署·授权委托书附件", page, q, _src(page, q),
                     "授权委托书后附法定代表人身份证复印件（按招标文件要求是否正反面、是否盖章）", "高", "以招标文件为准")]
    if "保证金" in q or "保函" in q or "担保" in q:
        return _deposit_rows(page, q, rule)
    if "有效期" in q:
        return _validity_rows(page, q, rule)
    if any(k in q for k in ("限价", "控制价", "预算")):
        return [_row("报价", page, q, f"{_src(page, q)}；{LAW['cap'][rule]}",
                     "报价不超过限价（等于不算超）；开标一览表、明细表、大小写一致")]
    if ("签字" in q or "盖章" in q or "签章" in q) and any(k in q for k in ("否决", "无效", "废标")) \
            and "投标函" not in q:
        return [_row("签署·总括", page, q, f"{_src(page, q)}；{LAW['sign'][rule]}",
                     "全册每个签字、盖章位置逐个过：投标函、开标一览表、授权委托书、承诺函、偏离表等格式页")]
    if "签字" in q or "签名" in q or "盖" in q:
        return _sign_rows(page, q, rule)
    if any(k in q for k in ("资格", "资质", "许可证", "业绩", "社保", "社会保障", "纳税", "信用", "裁判文书")):
        return [_row("资格要求", page, q, f"{_src(page, q)}；{LAW['qual'][rule]}", "按原文要求的证明逐项附上，看日期和有效期")]
    if q.lstrip().startswith(("★", "▲")) or "实质性" in q:
        return [_row("实质性条款", page, q, f"{_src(page, q)}；{LAW['star'][rule]}", "逐项响应，只能无偏离或正偏离")]
    if any(k in q for k in ("否决", "无效", "废标", "拒收", "不予受理")):
        return [_row("废标情形", page, q, _src(page, q), "按原文逐项对照")]
    return [_row("其他要求", page, q, _src(page, q), "按原文准备", "中", "以招标文件为准")]


def _split(clause: str) -> tuple[str, list[str]]:
    page, sep, text = clause.partition("|")
    if not sep:
        raise CheckError(f"[E08] 条款「{clause[:20]}」要写成「页码|原文」，如 \"P4|投标有效期120日\"")
    page = page.strip() or "页码未给"
    parts = [x.strip() for x in re.split(r"[；;。\n]", text) if x.strip()]
    if not parts:
        raise CheckError(f"[E08] 条款「{clause[:20]}」没有原文")
    return page, parts


def checklist(a: argparse.Namespace) -> dict:
    rule = a.rule
    rows = []
    for clause in a.clause:
        page, parts = _split(clause)
        for q in parts:
            rows.extend(_classify(page, q, rule))
    lines = [HEAD_C]
    for i, x in enumerate(rows, 1):
        cells = [str(i), x["cat"], x["page"], x["quote"], x["law"], x["prep"], "待填", "待填", x["risk"], x["result"], "□"]
        lines.append("| " + " | ".join(c.replace("|", "／") for c in cells) + " |")
    lines.append("")
    lines.append(f"共 {len(rows)} 行，按{rule}规则。「我方响应」「结论」待填：补发投标文件后接着逐条核。"
                 "「风险」「后果原话」是这条做不到时的后果。")
    return r("清单", "\n" + "\n".join(lines), rows=rows)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="输出 JSON")
    ap = argparse.ArgumentParser(description="投标日期、金额核算")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name: str, help_: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help_, parents=[common])   # 每个子命令都认 --json
    p = add("validity", "投标有效期天数")
    p.add_argument("--required", type=int, required=True)
    p.add_argument("--promised", type=int, required=True)
    p.add_argument("--source", help="投标文件里写这个天数的地方，如 投标函、报价表备注")
    p.set_defaults(fn=validity)
    p = add("latest", "没给截止日：按保函/授权书到期日反推最晚截止日")
    p.add_argument("--until", required=True)
    p.add_argument("--days", type=int, required=True)
    p.set_defaults(fn=latest)
    p = add("checklist", "只有招标文件：条款 → 固定表头自查清单")
    p.add_argument("--rule", choices=[GOV, BID], required=True)
    p.add_argument("--clause", action="append", required=True, help="页码|原文，可写多次")
    p.set_defaults(fn=checklist)
    p = add("cover", "保函、授权书是否覆盖投标有效期")
    p.add_argument("--deadline", required=True)
    p.add_argument("--days", type=int, required=True)
    p.add_argument("--until", required=True)
    p.add_argument("--what")
    p.set_defaults(fn=cover)
    p = add("cert", "证书在截止日是否有效")
    p.add_argument("--deadline", required=True)
    p.add_argument("--until", required=True)
    p.add_argument("--what")
    p.set_defaults(fn=cert)
    p = add("amount", "大小写金额是否一致")
    p.add_argument("--upper", required=True)
    p.add_argument("--lower", required=True)
    p.set_defaults(fn=amount)
    p = add("cap", "报价是否超限价/预算")
    p.add_argument("--bid", required=True)
    p.add_argument("--cap", required=True)
    p.set_defaults(fn=cap)
    p = add("deposit", "投标担保金额")
    p.add_argument("--required", required=True)
    p.add_argument("--paid", required=True)
    p.add_argument("--budget")
    p.set_defaults(fn=deposit)
    p = add("months", "社保、纳税月份是否齐")
    p.add_argument("--need", required=True)
    p.add_argument("--have", required=True)
    p.set_defaults(fn=months)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        res = args.fn(args)
    except CheckError as e:
        sys.stderr.write(f"{e}\n")
        return 2
    except Exception as e:  # noqa: BLE001  兜底：任何意外都回一句能照着改的话，不甩堆栈
        sys.stderr.write(f"[E09] 这组输入没算出来（{type(e).__name__}：{e}）。先核对日期、天数、金额是不是照原文抄的；"
                         "还不行就这一项按人工核对，在偏离表里标「存疑」\n")
        return 2
    text = res["why"].lstrip("\n") if res["status"] == "清单" else f"{res['status']}：{res['why']}"
    sys.stdout.write((json.dumps(res, ensure_ascii=False) if args.json else text) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
