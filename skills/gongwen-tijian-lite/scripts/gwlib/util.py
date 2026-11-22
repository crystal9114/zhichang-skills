"""规则共用的小工具。"""
from __future__ import annotations

import re
from collections import Counter

from .model import Para
from .units import is_cjk, size_name


def snip(text: str, n: int = 28) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return t if len(t) <= n else t[:n] + "…"


def ranges(idxs: list[int]) -> str:
    """[1,2,3,7] → 第1-3、7段"""
    idxs = sorted(set(idxs))
    if not idxs:
        return ""
    out, start, prev = [], idxs[0], idxs[0]
    for i in idxs[1:] + [None]:
        if i is not None and i == prev + 1:
            prev = i
            continue
        out.append(str(start) if start == prev else f"{start}-{prev}")
        if i is not None:
            start = prev = i
    return "第" + "、".join(out) + "段"


def dominant(p: Para, start: int = 0, end: int | None = None):
    """区间内汉字最多的 (字体, 字号)；汉字太少返回 (None, None, 0)。"""
    fonts, sizes, n = Counter(), Counter(), 0
    pos = 0
    for ch, font, size, _bold in p.chars():
        if start <= pos < (end if end is not None else 10 ** 9) and is_cjk(ch):
            fonts[font or "未指定"] += 1
            sizes[size] += 1
            n += 1
        pos += 1
    if not n:
        return None, None, 0
    return fonts.most_common(1)[0][0], sizes.most_common(1)[0][0], n


def font_share(p: Para, want: str, start: int = 0, end: int | None = None) -> float:
    pos, hit, n = 0, 0, 0
    for ch, font, _s, _b in p.chars():
        if start <= pos < (end if end is not None else 10 ** 9) and is_cjk(ch):
            n += 1
            hit += (font == want)
        pos += 1
    return hit / n if n else 1.0


def size_is(size: float | None, want: float) -> bool:
    return size is not None and abs(size - want) <= 0.26


def size_label(size: float | None) -> str:
    return "未设字号" if size is None else size_name(size)


def lead_spaces(text: str) -> int:
    return len(text) - len(text.lstrip(" 　"))
