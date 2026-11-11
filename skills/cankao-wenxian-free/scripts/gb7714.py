#!/usr/bin/env python3
"""参考文献 GB/T 7714 速改（精简版）。只用 Python 标准库，3.8 及以上，不联网，同一输入永远同一输出。

  python3 scripts/gb7714.py fix 列表.txt                    # 逐条改成 GB/T 7714—2025（默认）
  python3 scripts/gb7714.py fix 列表.txt --edition 2015     # 改成 2015 版
  python3 scripts/gb7714.py upgrade 列表.txt                # 2015 版列表转 2025 版，列出 6 处差异命中了哪几处
  python3 scripts/gb7714.py fix - <<'EOF'                   # 从标准输入读（直接贴列表）
  [1] ...
  EOF

全部参数见 references/script-usage.md；出错打印「E 码 + 原因 + 怎么办」，错误码表见 references/faq.md。
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import List, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ref_check import Checked, check_list  # noqa: E402
from ref_diff import Hits, mark_preprint, scan, section  # noqa: E402
from ref_model import Ref  # noqa: E402
from ref_parse import split_entries  # noqa: E402
from ref_render import make_opts  # noqa: E402
from ref_report import body, head  # noqa: E402

MAX_ENTRIES = 500
MAX_BYTES = 2_000_000
USAGE = "python3 scripts/gb7714.py fix|upgrade <列表.txt 或 -> [--edition 2025|2015]，全部参数见 references/script-usage.md"


class Fail(Exception):
    def __init__(self, code: str, why: str, fix: str):
        super().__init__(f"{code} {why}")
        self.code, self.why, self.fix = code, why, fix


class Parser(argparse.ArgumentParser):
    def print_help(self, file=None) -> None:  # -h 出中文说明
        lines = [__doc__.strip(), "", "参数："]
        for act in self._actions:
            if act.help == argparse.SUPPRESS:
                continue
            flag = ", ".join(act.option_strings) or act.dest
            choice = f"（可选：{' / '.join(act.choices)}）" if act.choices else ""
            lines.append(f"  {flag}{choice}：{act.help}")
        sys.stdout.write("\n".join(lines) + "\n")

    def error(self, message: str) -> None:  # 参数错：不出英文用法提示
        m = re.search(r"argument (\S+): invalid choice: '([^']*)'", message)
        if "required" in message:
            message = "少了模式（fix 或 upgrade）或输入"
        elif m:
            message = f"{m.group(1)} 不能取「{m.group(2)}」"
        elif "unrecognized arguments" in message:
            message = "不认识的参数 " + message.split(":", 1)[-1].strip()
        elif "invalid int value" in message:
            message = "这里要写整数"
        raise Fail("E05", f"参数不对（{message}）", USAGE)


def args_of(argv: List[str]) -> argparse.Namespace:
    ap = Parser(prog="gb7714.py", description="参考文献 GB/T 7714 速改（精简版）", add_help=False)
    ap.add_argument("-h", "--help", action="help", help="看这份说明")
    ap.add_argument("mode", choices=["fix", "upgrade"], help="fix：改成指定版本；upgrade：2015 版转 2025 版并列出规则差异")
    ap.add_argument("input", help="参考文献列表 .txt / .md，- 表示从标准输入读")
    ap.add_argument("--edition", choices=["2015", "2025"], default=None, help="fix 模式改成哪一版，默认 2025")
    ap.add_argument("--max-authors", type=int, default=3, help="著者列几位后加「等」，国标是 3；学校要求列全可设到 50")
    ap.add_argument("--no-etal-comma", action="store_true", help="「等 / et al.」前不加逗号（个别学校要求）")
    ap.add_argument("--punct", choices=["half", "mixed", "tight"], default="half",
                    help="half 半角加空格（默认）；mixed 中文逗号冒号括号全角；tight 半角不加空格")
    ap.add_argument("--cite-date", default="", help="你访问网页的日期 YYYY-MM-DD，缺引用日期的网络资源统一补这个")
    ap.add_argument("--require-doi", action="store_true", help="学校/期刊要求期刊论文写 DOI 时打开，缺的列进待补")
    ap.add_argument("--today", default=None, help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def read_text(path: str) -> str:
    if path == "-":
        raw = sys.stdin.buffer.read()
    else:
        p = Path(path)
        if not p.exists():
            raise Fail("E01", f"找不到文件 {path}", "检查路径和文件名；路径有空格要加引号；也可以用 - 从标准输入贴列表")
        if p.is_dir():
            raise Fail("E01", f"{path} 是文件夹，不是文件", "给参考文献列表的 .txt 文件路径")
        if p.suffix.lower() in (".docx", ".doc", ".wps", ".pdf", ".xlsx", ".xls"):
            raise Fail("E02", f"精简版只读文字，不读 {p.suffix} 文件",
                       "把参考文献列表复制出来存成 .txt（或直接贴进对话），再跑一次")
        if p.stat().st_size > MAX_BYTES:
            raise Fail("E06", "文件超过 2 MB，不像是参考文献列表", "只把参考文献那一段复制成 .txt 再跑")
        raw = p.read_bytes()
    for enc in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise Fail("E07", "文字编码认不出来", "用记事本打开后「另存为 → 编码选 UTF-8」再来")


def check_args(a: argparse.Namespace) -> dt.date:
    if a.max_authors < 1 or a.max_authors > 50:
        raise Fail("E05", f"--max-authors 只能是 1~50，现在是 {a.max_authors}", "国标是 3；学校要求列全就写 50")
    if a.cite_date:
        try:
            d = dt.date.fromisoformat(a.cite_date)
        except ValueError:
            raise Fail("E05", f"--cite-date「{a.cite_date}」不是有效日期", "写成 2026-11-03 这样的年-月-日")
        if d.year < 1990:
            raise Fail("E05", f"--cite-date {a.cite_date} 早于 1990 年", "引用日期是你打开网页的那天，请核对")
    try:
        today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    except ValueError:
        raise Fail("E05", "--today 格式不对", "写成 YYYY-MM-DD")
    if a.cite_date and dt.date.fromisoformat(a.cite_date) > today:
        raise Fail("E05", f"--cite-date {a.cite_date} 晚于今天", "引用日期是你已经打开过网页的那天，不能是将来")
    return today


def load_entries(a: argparse.Namespace) -> str:
    text = read_text(a.input)
    if not text.strip():
        raise Fail("E03", "输入是空的", "把参考文献列表贴进来，一行一条，带不带 [1] 序号都行")
    n = len(split_entries(text))
    if n == 0:
        raise Fail("E04", "没认出参考文献条目", "一行一条，例如：[1] 张三. 题名[J]. 刊名, 2020, 1(2): 3-4.")
    if n > MAX_ENTRIES:
        raise Fail("E06", f"一次 {n} 条，超过 {MAX_ENTRIES} 条上限", "分成几批，每批 500 条以内再跑")
    return text


def run(a: argparse.Namespace, today: dt.date) -> str:
    text = load_entries(a)
    edition = "2025" if a.mode == "upgrade" else (a.edition or "2025")
    opts = make_opts(edition, punct=a.punct, max_authors=a.max_authors, etal_comma=not a.no_etal_comma,
                     require_doi=a.require_doi)
    preprints: Set[str] = set()

    def hook(ref: Ref) -> None:   # upgrade：预印本平台网址的条目先改 [PP/OL] 再排版
        if a.mode == "upgrade" and mark_preprint(ref):
            preprints.add(ref.raw)

    items: List[Checked] = check_list(text, opts, today, a.cite_date, hook)
    if not items:
        raise Fail("E04", "没认出参考文献条目", "一行一条，例如：[1] 张三. 题名[J]. 刊名, 2020, 1(2): 3-4.")
    if all(not c.ref.parsed for c in items):
        raise Fail("E04", "每一条都拆不开，看起来不是参考文献列表",
                   "确认贴的是参考文献（著者. 题名[类型]. 出处），不是正文段落或表格")
    notes: List[str] = []
    if a.mode == "upgrade":
        hits = Hits()
        for n, c in enumerate(items, 1):
            scan(n, c.ref, hits, c.ref.raw in preprints)
        L = head(items, opts, ["输入按 GB/T 7714—2015 理解，逐条改成 GB/T 7714—2025"], "参考文献 2015 版 → 2025 版")
        L += section(hits) + body(items)
        L += ["其他 2025 版变化（不改著录结果，供参考）：「专著」改称「图书」；[EB] 改指网站、网页；DOI 改称永久标识符，"
              "网址里已含 DOI 的可不重复写；会议论文也可写成「[C]//会议名称, 会议年份: 页码.」。", ""]
    else:
        if a.max_authors != 3 or a.no_etal_comma:
            notes.append("著者按学校规定排：" + (f"超过 {a.max_authors} 人列前 {a.max_authors} 人加「等 / et al.」" if a.max_authors != 3 else "超过 3 人列前 3 人")
                         + ("，「等」前不加逗号" if a.no_etal_comma else "")
                         + "；这和 GB/T 7714 国标不同（国标：超过 3 人列前 3 人，后加「, 等」/「, et al.」，「等」前有逗号），此处按学校规定")
        if a.edition is None:
            notes.append("没指定版本，按现行的 GB/T 7714—2025 改；学校模板或期刊仍写 2015 的，加 --edition 2015 重跑")
        L = head(items, opts, notes, f"参考文献速改结果（GB/T 7714—{edition}）")
        L += body(items)
    return "\n".join(L).rstrip() + "\n"


def main(argv: List[str]) -> int:
    try:
        a = args_of(argv)
        today = check_args(a)
        sys.stdout.write(run(a, today))
        return 0
    except Fail as f:
        sys.stderr.write(f"{f.code} {f.why}\n怎么办：{f.fix}\n")
        return 2
    except SystemExit as e:   # --help 正常退出
        return int(e.code or 0)
    except KeyboardInterrupt:
        sys.stderr.write("E98 已取消\n")
        return 130
    except Exception as e:  # 最外层兜底：不打堆栈，给码和办法
        sys.stderr.write(f"E99 脚本内部出错（{type(e).__name__}）\n"
                         "怎么办：把出错的那几条单独存成 .txt 再跑，找出是哪一条；那条按 references/rules.md 手工改\n")
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
