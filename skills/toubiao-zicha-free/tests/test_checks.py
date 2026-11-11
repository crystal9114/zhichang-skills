"""checks.py 的单测。只用标准库：python3 -m unittest discover -s tests"""
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import checks  # noqa: E402


def run(*argv: str) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = checks.main(list(argv))
    return code, buf.getvalue()


class ValidityTest(unittest.TestCase):
    def test_enough(self):
        code, out = run("validity", "--required", "90", "--promised", "90")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("满足"))

    def test_short_without_source(self):
        _, out = run("validity", "--required", "90", "--promised", "60")
        self.assertIn("不满足", out)
        self.assertIn("投标无效", out)
        self.assertIn("致命", out)

    def test_short_with_source_names_the_place(self):
        _, out = run("validity", "--required", "90", "--promised", "30", "--source", "报价表备注")
        self.assertIn("报价表备注写的有效期 30 天短于招标文件要求 90 天，单列一行判", out)
        self.assertIn("投标无效", out)


class CoverTest(unittest.TestCase):
    def test_auth_short_carries_tender_rule_sentence(self):
        _, out = run("cover", "--deadline", "2026-11-20", "--days", "90", "--until", "2026-12-31",
                     "--what", "授权委托书")
        self.assertIn("不满足", out)
        self.assertIn("2027-02-18", out)
        self.assertIn("2027-02-17", out)
        self.assertIn("风险高", out)
        self.assertIn("以招标文件对授权期限的要求为准", out)
        self.assertNotIn("投标无效", out)

    def test_auth_ok_still_carries_sentence(self):
        _, out = run("cover", "--deadline", "2026-11-20", "--days", "90", "--until", "2027-03-31",
                     "--what", "授权委托书")
        self.assertTrue(out.startswith("满足"))
        self.assertIn("以招标文件对授权期限的要求为准", out)

    def test_guarantee_short_is_fatal_with_basis(self):
        _, out = run("cover", "--deadline", "2026-12-10", "--days", "90", "--until", "2027-02-28",
                     "--what", "投标保函")
        self.assertIn("2027-03-10", out)
        self.assertIn("差 10 天", out)
        self.assertIn("风险致命", out)
        self.assertIn("投标保证金有效期应当与投标有效期一致", out)

    def test_one_day_short_is_doubtful(self):
        _, out = run("cover", "--deadline", "2026-12-10", "--days", "90", "--until", "2027-03-09",
                     "--what", "投标保函")
        self.assertTrue(out.startswith("存疑"))

    def test_bad_date(self):
        code, _ = run("cover", "--deadline", "2026-13-40", "--days", "90", "--until", "2027-03-09")
        self.assertEqual(code, 2)


class LatestTest(unittest.TestCase):
    def test_reverse_deadline(self):
        _, out = run("latest", "--until", "2027-03-01", "--days", "90")
        self.assertIn("2026-12-01", out)
        self.assertIn("请告诉我投标截止日", out)


class OtherChecksTest(unittest.TestCase):
    def test_amount_mismatch(self):
        _, out = run("amount", "--upper", "壹佰贰拾叁万肆仟伍佰元整", "--lower", "¥1,234,050.00")
        self.assertIn("1,234,500.00", out)
        self.assertIn("差 450.00 元", out)

    def test_cap(self):
        _, out = run("cap", "--bid", "760000", "--cap", "80万")
        self.assertTrue(out.startswith("满足"))

    def test_cert_same_day(self):
        _, out = run("cert", "--deadline", "2026-11-25", "--until", "2026-11-25", "--what", "安全生产许可证")
        self.assertTrue(out.startswith("存疑"))

    def test_months_missing(self):
        _, out = run("months", "--need", "2026-05:2026-10", "--have", "2026-04:2026-09")
        self.assertIn("2026-10", out)
        self.assertTrue(out.startswith("不满足"))


T09 = [
    "P4|投标有效期120日；投标保证金5万元，须从投标人基本账户转出，截止时间前到账；接受联合体投标。",
    "P10|投标文件未按要求签字盖章的，否决其投标。",
    "P31|投标报价超过招标控制价的，否决投标。",
    "P45|投标函须由法定代表人或其委托代理人签字并加盖单位章；授权委托书须附法定代表人身份证复印件。",
]


class ChecklistTest(unittest.TestCase):
    def rows(self, rule, clauses):
        args = ["checklist", "--rule", rule]
        for c in clauses:
            args += ["--clause", c]
        code, out = run(*args)
        self.assertEqual(code, 0)
        return [ln for ln in out.splitlines() if ln.startswith("| ") and not ln.startswith("| 序号")], out

    def test_tender_only_rows(self):
        rows, out = self.rows("依法招标", T09)
        cats = [r.split(" | ")[1] for r in rows]
        for c in ("有效期", "投标担保·金额", "投标担保·到账时间", "投标担保·付款账户", "联合体投标", "签署·总括", "报价",
                  "签署·签字人资格", "签署·签字", "签署·盖章", "签署·授权委托书", "签署·授权委托书附件"):
            self.assertIn(c, cats)
        self.assertTrue(all(" | 待填 | 待填 | " in r for r in rows))
        self.assertIn("| 序号 | 类别 | 招标页码 | 条款原文 | 依据 |", out)

    def test_basic_account_cites_second_paragraph_only(self):
        rows, _ = self.rows("依法招标", T09)
        basic = next(r for r in rows if "付款账户" in r)
        self.assertIn("第二十六条第二款", basic)
        self.assertNotIn("第二十六条第一款", basic)
        amount = next(r for r in rows if "投标担保·金额" in r)
        self.assertNotIn("第二十六条", amount)

    def test_every_row_has_tender_page(self):
        rows, _ = self.rows("依法招标", T09)
        self.assertTrue(all(r.split(" | ")[2].startswith("P") for r in rows))

    def test_joint_states_legal_requirement(self):
        rows, _ = self.rows("依法招标", T09)
        joint = next(r for r in rows if "联合体" in r)
        self.assertIn("共同投标协议", joint)
        self.assertIn("第五十一条第（二）项", joint)

    def test_gov_rule_never_cites_bidding_regulation(self):
        rows, _ = self.rows("政府采购", ["P5|投标有效期90日；投标保证金2万元，以保函形式提交，保函有效期不短于投标有效期",
                                      "P9|投标函须加盖单位公章"])
        self.assertTrue(rows)
        self.assertTrue(all("招标投标法实施条例" not in r for r in rows))
        self.assertTrue(any("87号令第二十三条" in r for r in rows))

    def test_term_only_guarantee_sentence(self):
        rows, _ = self.rows("依法招标", ["P6|保函有效期不得短于投标有效期"])
        self.assertEqual(len(rows), 1)
        self.assertIn("第二十六条第一款", rows[0])

    def test_bad_clause(self):
        code, _ = run("checklist", "--rule", "依法招标", "--clause", "没有竖线")
        self.assertEqual(code, 2)


def run_err(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = checks.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class BadInputTest(unittest.TestCase):
    """意外输入一律回一句能照着改的中文提示，不出 Python 堆栈。"""

    def test_days_overflow_is_friendly(self):
        code, out, err = run_err("cover", "--deadline", "2026-12-10", "--days", "99999999", "--until", "2027-02-28")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("[E09]", err)
        self.assertNotIn("Traceback", err)

    def test_unexpected_error_is_friendly(self):
        def boom(_):
            raise TypeError("x")
        orig = checks.validity
        try:
            checks.validity = boom   # build_parser 在 main 里现建，换掉后生效
            code, _, err = run_err("validity", "--required", "90", "--promised", "60")
        finally:
            checks.validity = orig
        self.assertEqual(code, 2)
        self.assertIn("[E09]", err)

    def test_upper_without_digits(self):
        code, _, err = run_err("amount", "--upper", "万万", "--lower", "1")
        self.assertEqual(code, 2)
        self.assertIn("[E08]", err)

    def test_zero_cap(self):
        code, _, err = run_err("cap", "--bid", "760000", "--cap", "0")
        self.assertEqual(code, 2)
        self.assertIn("[E08]", err)

    def test_zero_budget(self):
        code, _, err = run_err("deposit", "--required", "2万", "--paid", "20000", "--budget", "0")
        self.assertEqual(code, 2)
        self.assertIn("[E08]", err)

    def test_zero_upper_still_ok(self):
        code, out = run("amount", "--upper", "零元整", "--lower", "0")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("满足"))


if __name__ == "__main__":
    unittest.main()
