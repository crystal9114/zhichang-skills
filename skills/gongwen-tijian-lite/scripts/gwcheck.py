#!/usr/bin/env python3
"""公文格式离线体检入口。全程本机运行，不联网、不注册。

用法：
  python3 scripts/gwcheck.py check 文件.docx [--json] [--type 通知]   体检，出问题清单和【体检结论】
  python3 scripts/gwcheck.py fix 文件.docx [--out 新文件.docx]         按版式项在副本上改格式（不改文字）
  python3 scripts/gwcheck.py rules                                     列出全部体检项和依据
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gwlib.errors import GwError  # noqa: E402


def _args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="gwcheck.py", add_help=False)
    ap.add_argument("cmd", nargs="?")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--type", dest="dtype")
    ap.add_argument("--out")
    ap.add_argument("-h", "--help", action="store_true")
    try:
        a, rest = ap.parse_known_args(argv)
    except SystemExit as e:
        raise GwError("E08") from e
    if rest or a.help or a.cmd not in ("check", "fix", "rules") or (a.cmd != "rules" and not a.file):
        raise GwError("E08", " ".join(rest))
    return a


def _write(path: str, text: str) -> None:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        raise GwError("E09", str(e)) from e


def main(argv: list[str]) -> int:
    a = _args(argv)
    if a.cmd == "rules":
        from gwlib.clauses import CLAUSES
        for rid, (cat, sev, clause, how, _p) in CLAUSES.items():
            if sev != "人工":
                print(f"{rid} [{sev}] {cat}｜{clause}｜{how}")
        return 0
    if a.cmd == "check":
        from gwlib import checker, report
        try:
            doc, issues, manual, dtype = checker.run_check(a.file, a.dtype)
        except GwError:
            raise
        except Exception as e:  # noqa: BLE001  体检里任何一步出错都转成 E10
            raise GwError("E10", f"{type(e).__name__}: {e}") from e
        text = report.to_json(doc, issues, manual, dtype) if a.json else report.render(doc, issues, manual, dtype)
        if a.out:
            _write(a.out, text)
        print(text)
        return 0
    from gwlib import fixer
    print(fixer.fix_file(a.file, a.out, a.dtype))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except GwError as e:
        print(e.render())
        sys.exit(2)
    except KeyboardInterrupt:
        print("【E99】已中断\n怎么办：重新运行一次")
        sys.exit(2)
    except Exception as e:  # noqa: BLE001  最外层兜底：不甩堆栈
        print(GwError("E99", f"{type(e).__name__}").render())
        sys.exit(2)
