"""把逐条结果写成 Markdown 报告：结论、改好的列表、要补/核对/定、逐条改动。只用标准库。"""
from __future__ import annotations

from typing import List

from ref_check import Checked
from ref_render import Opts

LEVEL_NAME = {"补": "要你补", "核": "要你核对", "问": "要你定", "改": "已改"}
STD_LINE = {
    "2025": "GB/T 7714—2025《信息与文献 参考文献著录规则》（2025-12-02 发布，2026-07-01 实施，代替 GB/T 7714—2015）",
    "2015": "GB/T 7714—2015《信息与文献 参考文献著录规则》（已被 GB/T 7714—2025 代替，2025 版 2026-07-01 实施）",
}
SCHOOL_LINE = "学校或期刊另有模板、示例的，以学校/期刊为准：把规范里参考文献那一页发来，按它再改一遍"


def marks(c: Checked) -> str:
    need = [i.field for i in c.ref.issues if i.level == "补"]
    return f"【待补：{'、'.join(dict.fromkeys(need))}】" if need else ""


def fixed_list(items: List[Checked], with_marks: bool = True) -> str:
    return "\n".join(f"[{n}] {c.text}{marks(c) if with_marks else ''}" for n, c in enumerate(items, 1))


def counts(items: List[Checked]) -> dict:
    def lv(c: Checked, x: str) -> bool:
        return any(i.level == x for i in c.ref.issues)
    return {"total": len(items), "need": sum(lv(c, "补") for c in items), "check": sum(lv(c, "核") for c in items),
            "ask": sum(lv(c, "问") for c in items), "changed": sum(lv(c, "改") for c in items),
            "clean": sum(not c.ref.issues for c in items)}


def head(items: List[Checked], opts: Opts, notes: List[str], title: str) -> List[str]:
    k = counts(items)
    punct = {"half": "半角加空格", "mixed": "中文逗号冒号括号全角（照 2025 原文排版）", "tight": "半角不加空格"}[opts.punct]
    etal = "「, 等」/「, et al.」" if opts.etal_comma else "「 等」/「 et al.」"
    L = [f"# {title}", "",
         f"- 依据：{STD_LINE[opts.edition]}；顺序编码制；标点{punct}；著者超过 {opts.max_authors} 人列前 {opts.max_authors} 人加{etal}",
         f"- {SCHOOL_LINE}",
         f"- 共 {k['total']} 条：已改 {k['changed']} 条，要你补 {k['need']} 条，要你核对 {k['check']} 条，要你定 {k['ask']} 条，原本合格 {k['clean']} 条",
         "- 缺的页码、卷期、DOI、出版地、引用日期一律不编，在改好的列表里标【待补：xx】"]
    L += [f"- {n}" for n in notes]
    return L + [""]


def body(items: List[Checked]) -> List[str]:
    L = ["## 改好的列表", "", "```", fixed_list(items), "```", ""]
    for lvl, name, tip in (("补", "要你补（原文没有，脚本不编）", "照原文出处（期刊官网、知网文章页、图书版权页）补上，补完删掉【待补】。"),
                           ("核", "要你核对", "脚本按规则推断或发现可疑，对一眼原文。"),
                           ("问", "要你定", "国标留了余地，或要看学校、期刊的规定。")):
        rows = [(n, i) for n, c in enumerate(items, 1) for i in c.ref.issues if i.level == lvl]
        if rows:
            L += [f"## {name}", "", tip, "", "| 条目 | 项目 | 说明 |", "|---|---|---|"]
            L += [f"| [{n}] | {i.field} | {i.msg} |" for n, i in rows]
            L.append("")
    L += ["## 逐条改了什么", ""]
    for n, c in enumerate(items, 1):
        if not c.ref.issues:
            continue
        L.append(f"**[{n}]** 原文：{c.ref.raw}")
        L.append(f"　　改为：{c.text}{marks(c)}")
        L += [f"　　- {LEVEL_NAME[i.level]}（{i.field}）：{i.msg}" for i in c.ref.issues]
        if not any(i.level == "改" for i in c.ref.issues):
            L.append("　　- 格式：一字未改，只标了上面这些要你补 / 核对 / 定的项")
        L.append("")
    ok = [f"[{n}]" for n, c in enumerate(items, 1) if not c.ref.issues]
    if ok:
        L += ["原本合格、一字未改：" + "、".join(ok), ""]
    return L
