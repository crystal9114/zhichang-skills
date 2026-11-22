"""统一错误码：脚本入口只抛 GwError，最外层打成「E 码 + 中文原因 + 怎么办」，不甩堆栈。"""
from __future__ import annotations

CODES = {
    "E01": ("读不到文件", "确认路径对、文件没被占用；文件在别的电脑上就先拷到本机"),
    "E02": ("这种文件类型不支持", "只收 .docx 和 .txt。.doc、.wps 先在 Word 或 WPS 里另存为 .docx（要查字体行距就得有 .docx）；也可以把文字粘进 .txt，只查文字项；PDF、图片没有字体行距信息，同样只能粘文字进 .txt"),
    "E03": ("文件打不开，不是完整的 docx", "用 Word 或 WPS 打开确认能正常显示，再另存为 .docx 重试；加密文件先去掉密码"),
    "E04": ("文件异常：体积过大或含不安全内容", "docx 解压后超过 60MB 或含外部实体声明，不处理；换一份正常导出的 docx"),
    "E05": ("文件里没有可检查的文字", "确认文件有正文；扫描件或图片版没有文字层，请先转成可编辑文字"),
    "E06": ("txt 编码认不出来", "用记事本另存为 UTF-8 编码再试"),
    "E07": ("一键改需要 python-docx，本机没装", "运行 python3 -m pip install python-docx 后重试；不想装就只用体检清单，按清单手改"),
    "E08": ("命令参数不对", "看用法：python3 scripts/gwcheck.py check 文件.docx"),
    "E09": ("结果文件写不进去", "换一个能写的输出目录，或不加 --out 直接看屏幕输出"),
    "E10": ("体检过程中某一步出错", "把文件另存一份重试；仍然出错就只看已出的清单，并把文件交给人工核对"),
    "E99": ("没有预料到的错误", "重试一次；仍失败就改用人工核对，并记下文件名和这条编号"),
}


class GwError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code if code in CODES else "E99"
        self.detail = detail
        super().__init__(f"{self.code} {CODES[self.code][0]} {detail}".strip())

    def render(self) -> str:
        why, todo = CODES[self.code]
        extra = f"（{self.detail}）" if self.detail else ""
        return f"【{self.code}】{why}{extra}\n怎么办：{todo}"
