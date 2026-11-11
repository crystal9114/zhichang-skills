"""按编号从 references/laws.md 取法条全称和条款号。文件缺了也不报错，退回内置的全称表。"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).resolve().parents[2] / "references" / "laws.md"

# 文件读不到时的兜底（和 laws.md 标题一致）
FALLBACK = {
    "LCL-10": "《中华人民共和国劳动合同法》第十条",
    "LCL-14": "《中华人民共和国劳动合同法》第十四条第三款",
    "LCL-38": "《中华人民共和国劳动合同法》第三十八条",
    "LCL-39": "《中华人民共和国劳动合同法》第三十九条",
    "LCL-40": "《中华人民共和国劳动合同法》第四十条",
    "LCL-41": "《中华人民共和国劳动合同法》第四十一条第一款",
    "LCL-42": "《中华人民共和国劳动合同法》第四十二条",
    "LCL-45": "《中华人民共和国劳动合同法》第四十五条",
    "LCL-46": "《中华人民共和国劳动合同法》第四十六条",
    "LCL-47": "《中华人民共和国劳动合同法》第四十七条",
    "LCL-48": "《中华人民共和国劳动合同法》第四十八条",
    "LCL-82": "《中华人民共和国劳动合同法》第八十二条",
    "LCL-87": "《中华人民共和国劳动合同法》第八十七条",
    "LCL-97": "《中华人民共和国劳动合同法》第九十七条第三款",
    "REG-6": "《中华人民共和国劳动合同法实施条例》第六条",
    "REG-7": "《中华人民共和国劳动合同法实施条例》第七条",
    "REG-20": "《中华人民共和国劳动合同法实施条例》第二十条",
    "REG-25": "《中华人民共和国劳动合同法实施条例》第二十五条",
    "REG-27": "《中华人民共和国劳动合同法实施条例》第二十七条",
    "LDAL-27": "《中华人民共和国劳动争议调解仲裁法》第二十七条",
    "PLR-3": "《职工带薪年休假条例》第三条",
    "PLR-5": "《职工带薪年休假条例》第五条",
    "PLM-10": "《企业职工带薪年休假实施办法》第十条",
    "PLM-11": "《企业职工带薪年休假实施办法》第十一条",
    "PLM-12": "《企业职工带薪年休假实施办法》第十二条",
    "SPI1-44": "《最高人民法院关于审理劳动争议案件适用法律问题的解释（一）》（法释〔2020〕26号）第四十四条",
}


@lru_cache(maxsize=1)
def library() -> dict[str, str]:
    out = dict(FALLBACK)
    try:
        text = FILE.read_text(encoding="utf-8")
    except OSError:
        return out
    for block in re.split(r"^### ", text, flags=re.M)[1:]:
        head = block.partition("\n")[0].strip()
        key, _, title = head.partition(" ")
        if title:
            out[key] = title.strip()
    return out


def title(key: str) -> str:
    return library().get(key, key)


def cite(keys: tuple[str, ...] | list[str]) -> str:
    """同一部法规的条款并在一起：《中华人民共和国劳动合同法》第四十八条、第八十七条；《……实施条例》第二十五条。"""
    groups: dict[str, list[str]] = {}
    for k in keys:
        t = title(k)
        name, sep, art = t.rpartition("》")
        if not sep or not art.startswith("第"):
            groups.setdefault(t, [])
            continue
        groups.setdefault(name + "》", []).append(art)
    return "；".join(n + "、".join(arts) for n, arts in groups.items())
