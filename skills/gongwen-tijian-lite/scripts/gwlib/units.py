"""字号、字体名归一，宽度估算。"""
from __future__ import annotations

SIZE_NAMES = {42.0: "初号", 36.0: "小初", 26.0: "一号", 24.0: "小一", 22.0: "二号", 18.0: "小二", 16.0: "三号",
              15.0: "小三", 14.0: "四号", 12.0: "小四", 10.5: "五号", 9.0: "小五"}
TW_PER_PT = 20
MM_PER_TW = 25.4 / 1440


def size_name(pt: float | None) -> str:
    if pt is None:
        return "未知字号"
    return SIZE_NAMES.get(round(pt * 2) / 2, f"{pt:g}磅")


def tw_to_mm(tw: float) -> float:
    return tw * MM_PER_TW


# 字体名归一：键是小写后的别名片段，值是体检里用的族名
_FAMILIES = (
    ("小标宋", "小标宋"), ("xiaobiaosong", "小标宋"), ("fzxbs", "小标宋"), ("fzxiaobiao", "小标宋"),
    ("仿宋", "仿宋"), ("fangsong", "仿宋"), ("fzfs", "仿宋"),
    ("黑体", "黑体"), ("simhei", "黑体"), ("fzhei", "黑体"), ("方正黑", "黑体"),
    ("楷体", "楷体"), ("kaiti", "楷体"), ("fzkai", "楷体"), ("方正楷", "楷体"),
    ("华文中宋", "华文中宋"), ("stzhongs", "华文中宋"),
    ("宋体", "宋体"), ("simsun", "宋体"), ("nsimsun", "宋体"), ("song", "宋体"),
)


def family(name: str | None) -> str:
    if not name:
        return "未指定"
    low = name.lower().replace(" ", "")
    for key, fam in _FAMILIES:
        if key in low:
            return fam
    return name


def is_cjk(ch: str) -> bool:
    return "\u3400" <= ch <= "\u9fff" or "\uf900" <= ch <= "\ufaff"


def char_em(ch: str) -> float:
    """估算一个字符占几个汉字宽：汉字和全角标点 1，西文字符 0.5。"""
    o = ord(ch)
    if o < 0x80:
        return 0.5
    if ch in "\u3000":
        return 1.0
    return 1.0


def text_em(text: str) -> float:
    return sum(char_em(c) for c in text)


def em_of(tw: float, size_pt: float | None) -> float:
    """缩进的二十分之一磅换算成「字」，没有字号时按三号字算。"""
    base = (size_pt or 16.0) * TW_PER_PT
    return tw / base if base else 0.0
