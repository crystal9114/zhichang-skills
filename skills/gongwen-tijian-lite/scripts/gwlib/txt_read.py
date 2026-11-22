"""txt 只有文字，没有字体行距页边距，只能查文字项。"""
from __future__ import annotations

from .errors import GwError
from .model import Doc, Para


def read_txt(path: str) -> Doc:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise GwError("E06")
    if "\x00" in text[:2000]:
        raise GwError("E06", "像是二进制文件")
    paras, n = [], 0
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.strip():
            n += 1
            paras.append(Para(idx=n, text=line.rstrip()))
    if not paras:
        raise GwError("E05")
    return Doc(kind="txt", paras=paras)
