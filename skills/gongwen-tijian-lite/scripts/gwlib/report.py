"""把问题清单排成文字，并打出【体检结论】整句。"""
from __future__ import annotations

import json

from .model import Doc, Issue
from .util import ranges

TXT_NOTE = "txt 只有文字，字体、字号、行距、页边距、页码没法查，要查这些请给 .docx"
CIRCLED = "①②③"
# 一键改能在副本上处理的体检项（只动版式）；清单里其余的要改文字，或要用户对照原稿定，不自动改
LAYOUT_RULES = frozenset(
    "G01 G02 G03 T01 T02 T03 B01 B02 B03 B04 B05 B06 L01 R02 D03 D04 A02 A07 F01 F02 F03 F04 F05 V04 N04 M01".split())


def _nums(ns: list[int]) -> str:
    return "、".join(str(n) for n in ns)


def notes(real: list[Issue], after_fix: bool, kind: str) -> list[str]:
    """脚本自己打出的「说明」：哪几条要改文字、哪几条是版式、下一步怎么办。回答原样贴，不另编。"""
    text_ns = [n for n, i in enumerate(real, 1) if i.rule not in LAYOUT_RULES]
    lay_ns = [n for n, i in enumerate(real, 1) if i.rule in LAYOUT_RULES]
    out = ["说明（脚本按上面的清单自动列出）："]
    if after_fix:
        out.append("- 文字没动：改前改后每一段文字已逐字核对一致，原文件没有覆盖。")
        out.append("- 请用 Word 或 WPS 打开副本看一遍，尤其是标题换行、印章位置、红头。")
        if text_ns:
            out.append(f"- 清单第 {_nums(text_ns)} 条要改文字，一键改不会动：请对照原稿确认后手改，改法见各条「改法」。")
        else:
            out.append("- 脚本能查的项目已无剩余问题。")
    elif real:
        if text_ns:
            out.append(f"- 清单第 {_nums(text_ns)} 条要改文字，或要你对照原稿确认：请手改，脚本不会自动改。")
        if lay_ns:
            out.append(f"- 清单第 {_nums(lay_ns)} 条是版式，可以在副本上一键改，文字不动。")
            if kind == "docx":
                out.append("- 要一键改，说一声：我在副本上运行 fix，不覆盖原文件。")
    else:
        out.append("- 脚本能查的项目没发现问题；不是说完全合规，上面「需要人工核对」几项请自己过一遍。")
    out.append("- 脚本只读文件里的真实写法，文号、日期、机关全称、数字是否属实核实不了，要对照原始材料。")
    return out


def short(i: Issue) -> str:
    what = i.what.split("（共")[0]
    return what if len(what) <= 40 else what[:40] + "…"


def conclusion(doc: Doc, issues: list[Issue], manual: list[Issue]) -> str:
    real = [i for i in issues if i.sev != "人工"]
    must = sum(i.sev == "必改" for i in real)
    cats = len({i.cat for i in real})
    name = doc.filename or "文件"
    tail = f"；另有 {len(manual)} 项脚本看不到、需要人工核对" if manual else ""
    if doc.kind == "txt":
        tail += f"；注意：{TXT_NOTE}"
    if not real:
        return f"【体检结论】「{name}」按脚本能查的项目没有发现问题（0 处）{tail}。"
    tops = "；".join(f"{CIRCLED[n]}{short(i)}（{i.clause.split('（')[0].strip()}）" for n, i in enumerate(real[:3]))
    return (f"【体检结论】「{name}」共发现 {len(real)} 处问题（必改 {must} 处、建议 {len(real) - must} 处），"
            f"涉及 {cats} 类；最要紧三条：{tops}{tail}。")


def render(doc: Doc, issues: list[Issue], manual: list[Issue], dtype: str | None, after_fix: bool = False) -> str:
    real = [i for i in issues if i.sev != "人工"]
    lines = [conclusion(doc, issues, manual), ""]
    lines.append(f"文件：{doc.filename}（{doc.kind}，共 {len(doc.paras)} 个非空段落，识别文种：{dtype or '未识别'}）")
    lines.append("")
    if real:
        lines.append("问题清单（按轻重排序）：")
        for n, i in enumerate(real, 1):
            where = ranges(i.paras) if i.paras else "全文或页面设置"
            lines.append(f"{n}. 【{i.sev}】{i.cat}｜位置：{where}")
            if i.snippet:
                lines.append(f"   原文：「{i.snippet.strip()[:36]}」")
            lines.append(f"   不合：{i.what}")
            lines.append(f"   依据：{i.clause}")
            lines.append(f"   改法：{i.fix}")
    if manual:
        lines.append("")
        lines.append("需要人工核对（脚本看不到）：")
        lines.extend(f"- {m.what}" for m in manual)
    lines.append("")
    lines.extend(notes(real, after_fix, doc.kind))
    return "\n".join(lines)


def to_json(doc: Doc, issues: list[Issue], manual: list[Issue], dtype: str | None) -> str:
    return json.dumps({
        "conclusion": conclusion(doc, issues, manual), "file": doc.filename, "kind": doc.kind, "doc_type": dtype,
        "issues": [{"rule": i.rule, "severity": i.sev, "category": i.cat, "paragraphs": i.paras, "snippet": i.snippet,
                    "problem": i.what, "clause": i.clause, "fix": i.fix} for i in issues if i.sev != "人工"],
        "manual": [m.what for m in manual]}, ensure_ascii=False, indent=2)
