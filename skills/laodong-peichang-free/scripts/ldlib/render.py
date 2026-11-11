"""把测算结果和体检结果排成能直接贴进回答的中文文本；--json 时给结构化数据。"""
from __future__ import annotations

from . import laws, lead
from .model import Result, fmt

FOOT = ("说明：以上按你提供的事实、由本地脚本按法条测算，不是法律意见；标「存疑」的和各地口径不一的地方，"
        "以当地劳动人事争议仲裁委员会的口径为准。劳动仲裁不收费（《中华人民共和国劳动争议调解仲裁法》第五十三条）。")


def quick_text(res: Result) -> str:
    out = ["# 劳动争议赔偿速算结果", ""]
    if res.lead:
        out += lead.text(res.lead)
    if res.rough:
        out += ["## 粗算，不是结论",
                "下面按「普通劳动关系、向和你签劳动合同的单位主张」粗算，只当参考数；这类情形要先弄清下面几点，金额以律师或仲裁委核定为准："]
        out += [f"- {s}" for s in res.rough] + [""]
    if res.guessed:
        out += ["## 按假设估，不是结论",
                "入职日或离职日是按用户的大概说法反推或默认的（见「假设」），零头差几天就可能差半个月。回答里要把下面的数写成「按假设估」，"
                "并先问准确的入职日、离职日。", ""]
    out += ["## 按这些事实算的"] + [f"- {x}" for x in res.facts] + [""]
    if not res.reason_confirmed:
        out += ["## 结论", "**离职方式还没问清，不下结论。** 下面「各情形对比」只是区间，问清是谁提出解除、单位给的理由之后再定是 0、N、N+1 还是 2N。", ""]
    elif res.claimed and res.rough:
        n_amt, dn_amt = res.scenarios[1][1], res.scenarios[3][1]
        out += ["## 结论（粗算区间，不是结论）",
                f"**不出确定金额。按普通劳动关系粗算只能给区间：经济补偿 N 约 {fmt(n_amt)} 元到违法解除赔偿金 2N 约 {fmt(dn_amt)} 元**；"
                "要先弄清上面「粗算，不是结论」里的几点，金额以律师或劳动人事争议仲裁委员会核定为准。", ""]
    elif res.claimed:
        out += ["## 结论", f"**可主张合计 {fmt(res.total)} 元**（{len(res.claimed)} 项，逐项见下）", ""]
    elif res.barred:
        out += ["## 结论", f"**这些项目本来能要 {fmt(sum(i.amount for i in res.barred))} 元，但都已过一年仲裁时效，按目前事实可主张 0 元。**"
                "先问清离职后有没有书面催要、投诉或单位答应付钱的记录（会让时效中断、重新算一年）。", ""]
    else:
        out += ["## 结论", "**按目前事实，没有可以主张的经济补偿或赔偿金。**", ""]
    if res.notes:
        out += [f"- {n}" for n in res.notes] + [""]
    shown = [it for it in res.items
             if not (it.key in ("n", "notice", "2n") and (not res.reason_confirmed or (not it.claim and not it.barred)))]
    if shown:
        out.append("## 逐项")          # 不适用的解除类项目只放在对比表里
    for it in shown:
        tag = "" if it.claim else ("（已过时效，不计入合计）" if it.barred else "（不计入合计）")
        out += [f"### {it.title}：{fmt(it.amount)} 元{tag}",
                f"- 算式：{it.formula_text}"]
        out += [f"- {d}" for d in it.detail]
        out.append(f"- 依据：{laws.cite(it.laws)}")
        out.append(f"- 时效：{it.limitation.status}。{it.limitation.note}（《中华人民共和国劳动争议调解仲裁法》第二十七条）")
        out += [f"- 存疑：{d}" for d in it.doubts]
        out.append("")
    out += ["## 各情形对比（离职方式不同，金额怎么变；只有问清离职方式的那一行才是结论）", "",
            "| 情形 | 金额(元) | 算式 |", "|---|---|---|"]
    out += [f"| {n} | {fmt(a)} | {w} |" for n, a, w in res.scenarios]
    out.append("")
    if res.cautions:
        out += ["## 要特别注意"] + [f"- {c}" for c in res.cautions] + [""]
    if res.doubts:
        out += ["## 存疑与地方口径"] + [f"- 存疑：{d}" for d in res.doubts] + [""]
    if res.assumptions:
        out += ["## 假设"] + [f"- {a}" for a in res.assumptions] + [""]
    if res.questions:
        out += ["## 还要问（会改变结果）"] + [f"- {q}：{w}" for q, w in res.questions] + [""]
    out.append(FOOT)
    return "\n".join(out) + "\n"


def quick_json(res: Result) -> dict:
    return {
        **(lead.as_json(res.lead) if res.lead else {}),
        "结论": ((f"粗算区间 N {fmt(res.scenarios[1][1])} 元到 2N {fmt(res.scenarios[3][1])} 元，不是结论" if res.rough
                 else f"可主张合计 {fmt(res.total)} 元") if res.reason_confirmed else "离职方式未确认，不下结论"),
        "粗算前提": res.rough, "结论补充": res.notes,
        "按这些事实算的": res.facts,
        "逐项": [{"项目": i.title, "金额": fmt(i.amount), "计入合计": i.claim and i.amount > 0, "算式": i.formula_text,
                "过程": list(i.detail), "依据": laws.cite(i.laws),
                "时效": f"{i.limitation.status}：{i.limitation.note}", "存疑": list(i.doubts)} for i in res.items],
        "各情形对比": [{"情形": n, "金额": fmt(a), "算式": w} for n, a, w in res.scenarios],
        "要特别注意": res.cautions, "存疑与地方口径": res.doubts, "假设": res.assumptions,
        "还要问": [{"问": q, "为什么": w} for q, w in res.questions], "说明": FOOT,
    }


def check_text(chk: dict) -> str:
    out = ["# 劳动争议体检结果（先问清再算）", ""]
    if chk.get("回答开头照抄") or chk.get("还要问（逐条照抄）"):
        out += lead.text(lead.Lead(list(chk.get("回答开头照抄", [])), list(chk.get("还要问（逐条照抄）", []))))
    if chk["要停下转律师的"]:
        out += ["## 要停下、不出金额的情形"] + [f"- {s}" for s in chk["要停下转律师的"]] + [""]
    if chk["要特别注意的"]:
        out += ["## 要特别注意"] + [f"- {s}" for s in chk["要特别注意的"]] + [""]
    t = chk.get("仲裁时效")
    if t:
        out += ["## 仲裁时效",
                f"- 离职日 {t['离职日']}，一般截止 {t['一般截止日']}，按 {t['按哪天判']} 判：**{t['状态']}**"
                + (f"（还剩 {t['剩余天数']} 天）" if t['剩余天数'] >= 0 else f"（已超过 {-t['剩余天数']} 天）"),
                f"- 依据：{t['依据']}", ""]
    if chk["要先问的"]:
        out += ["## 要先问用户的（按顺序）"] + [f"{i}. {q['问']}——{q['为什么']}" for i, q in enumerate(chk["要先问的"], 1)] + [""]
    else:
        out += ["## 要先问用户的", "- 关键事实都有了，可以跑 quick 算钱。", ""]
    out.append(FOOT)
    return "\n".join(out) + "\n"
