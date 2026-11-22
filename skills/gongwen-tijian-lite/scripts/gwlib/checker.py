"""体检总入口：读文件 → 分角色 → 跑全部规则 → 排序 → 出清单和【体检结论】。"""
from __future__ import annotations

import os

from . import rules_layout, rules_para, rules_text
from .clauses import make
from .docx_read import read_docx
from .errors import GwError
from .model import Doc, Issue
from .structure import analyze
from .txt_read import read_txt

SEV_RANK = {"必改": 0, "建议": 1, "人工": 2}


def load(path: str) -> Doc:
    if not os.path.isfile(path):
        raise GwError("E01", path)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        try:
            doc = read_docx(path)
        except GwError:
            raise
        except (OSError, ValueError, KeyError) as e:
            raise GwError("E03", str(e)) from e
    elif ext == ".txt":
        try:
            doc = read_txt(path)
        except OSError as e:
            raise GwError("E01", str(e)) from e
    else:
        raise GwError("E02", ext or "无扩展名")
    doc.filename = os.path.basename(path)
    return doc


def manual_items(doc: Doc, lay, txt: bool) -> list[Issue]:
    items = []
    if lay.date:
        items.append("印章位置：端正、居中下压署名和成文日期，顶端上距正文一行之内，不压正文（第7.3.5.1条）")
    if lay.head:
        items.append("红色发文机关标志、发文字号下4mm的红色分隔线（第7.2.4、7.2.7条）")
    if lay.footer_blocks:
        items.append("版记分隔线粗细、版记是否在末页（第7.4.1条）")
    if len("".join(p.text for p in doc.paras if p.idx in lay.title)) > 22:
        items.append("标题回行是否词意完整、排列对称（第7.3.1条）")
    if not txt:
        items.append("页码一字线上距版心下边缘 7mm（第7.5条），脚本只读得到字体和位置，量不出这段距离")
    if any(p.has_numpr for p in doc.paras):
        items.append(f"有 {sum(p.has_numpr for p in doc.paras)} 段用了 Word 自动编号，序号不在文字里，序号体检没覆盖这些段")
    if any(p.in_table for p in doc.paras):
        items.append("表格里的版式（字体、对齐、表头位置）脚本没有逐项核对")
    items.append("文号、日期、机关全称、数字内容本身对不对，要你对照原始材料核实")
    return [make("H01", t) for t in items]


def run_check(path: str, forced_type: str | None = None) -> tuple[Doc, list[Issue], list[Issue], str | None]:
    doc = load(path)
    txt = doc.kind == "txt"
    lay = analyze(doc)
    dtype = rules_para.doc_type(doc, lay, forced_type)
    issues: list[Issue] = []
    if not txt:
        issues += rules_layout.check_page(doc, lay)
        issues += rules_layout.check_footer(doc, lay)
        issues += rules_para.check_body(doc, lay)
    issues += rules_para.check_title(doc, lay, dtype, txt)
    issues += rules_para.check_dtype_body(doc, lay, dtype)
    issues += rules_para.check_levels(doc, lay)
    issues += rules_para.check_recipient(doc, lay, dtype, txt)
    issues += rules_para.check_docno(doc, lay, txt)
    issues += rules_para.check_tail(doc, lay, dtype, txt)
    issues += rules_para.check_attach(doc, lay, txt)
    issues += rules_para.check_note_and_cc(doc, lay, txt)
    issues += rules_text.check_punct(doc, lay)
    issues += rules_text.check_numbers(doc, lay)
    issues.sort(key=lambda i: (SEV_RANK[i.sev], i.prio, i.paras[0] if i.paras else 0))
    return doc, issues, manual_items(doc, lay, txt), dtype
