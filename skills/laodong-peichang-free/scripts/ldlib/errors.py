"""统一错误：错误码 + 中文原因 + 怎么办，不打堆栈。码表见 references/errors.md。"""
from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class LdError(Exception):
    code: str
    reason: str
    fix: str
    exit_code: int = 2

    def text(self) -> str:
        return f"错误码：{self.code}\n原因：{self.reason}\n怎么办：{self.fix}\n"


def fail(code: str, reason: str, fix: str, exit_code: int = 2) -> LdError:
    return LdError(code, reason, fix, exit_code)


def report(err: LdError) -> int:
    sys.stdout.write(err.text())
    return err.exit_code


def unexpected(exc: BaseException) -> int:
    """兜底：任何没料到的异常都转成 E99，不往用户脸上甩英文堆栈。"""
    return report(fail("E99", f"脚本内部出错（{type(exc).__name__}）",
                       "把命令原样发给卖家排查；先按 references/calc-rules.md 的口径手算，并在回答里写明「未经脚本核对」", 9))
