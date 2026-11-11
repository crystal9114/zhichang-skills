"""统一的业务错误：E 码 + 中文原因 + 怎么办。码表同 references/errors.md。"""
from __future__ import annotations

# 退出码：0 成功；2 参数写法不对；3 数值不合规；4 参数互相矛盾；9 未预料的错误
EXIT = {"E01": 2, "E02": 3, "E03": 3, "E04": 3, "E05": 3, "E06": 4, "E09": 9}

FIX = {
    "E01": "照 python3 scripts/geshui.py quick -h 的写法改，金额只写数字，如 --income 15000",
    "E02": "金额只写数字（可带小数和千分位逗号），不要带「元」「万」「k」，如 1.5万 写成 15000",
    "E03": "月份写 1~12 的整数；年中入职用 --start 入职月，年终奖月份要落在计税月份里",
    "E04": "金额不能是负数；没有这一项就不写或写 0",
    "E05": "数额超出个人工资的合理范围，先核对是不是多打了 0，或把年薪当成了月薪",
    "E06": "去掉其中一个开关再算；拿不准就先问清楚再选",
    "E09": "把完整命令发给开发者；先按 references/manual.md 的手算步骤核算",
}


class GsError(Exception):
    """可预期的业务错误，入口统一打印成 E 码 + 原因 + 怎么办。"""

    def __init__(self, code: str, msg: str, fix: str = "") -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.fix = fix or FIX.get(code, "")

    def text(self) -> str:
        return f"[{self.code}] {self.msg}\n怎么办：{self.fix}"

    def exit_code(self) -> int:
        return EXIT.get(self.code, 9)
