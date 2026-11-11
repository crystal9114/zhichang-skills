"""geshui.py 单测：正向用官方口径的已知数，反向覆盖负数、0 元、空值、超范围、互斥参数、内部异常。

  python3 -m unittest discover -s tests      # 在技能包根目录跑，只用标准库
"""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import geshui  # noqa: E402
from gslib import engine  # noqa: E402
from gslib.rules import bonus_tax_separate  # noqa: E402


def plan(*argv: str) -> engine.Result:
    a = geshui.build_parser().parse_args(["quick", *argv])
    return engine.run(geshui.build_plan(a))


def taxes(res: engine.Result) -> list[D]:
    return [m.tax for m in res.months]


def cli(*argv: str) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = geshui.main(list(argv))
    return code, buf.getvalue()


class Cumulative(unittest.TestCase):
    def test_three_months_step_up(self) -> None:
        r = plan("--income", "30000", "--si", "4500", "--special", "2000", "--end", "3")
        self.assertEqual(taxes(r), [D("555.00"), D("625.00"), D("1850.00")])
        self.assertEqual([m.cum_taxable for m in r.months], [D("18500"), D("37000"), D("55500")])

    def test_cross_36000_in_march(self) -> None:
        r = plan("--income", "25000", "--si", "3500", "--special", "3000", "--end", "3")
        self.assertEqual(taxes(r), [D("405.00"), D("405.00"), D("720.00")])
        self.assertTrue(any("跨过 36,000" in j for j in r.jumps))

    def test_april_jump_explained(self) -> None:
        r = plan("--income", "20000", "--si", "3000", "--special", "2000", "--end", "4")
        self.assertEqual(taxes(r)[2:], [D("300.00"), D("580.00")])

    def test_mid_year_and_first_job(self) -> None:
        self.assertEqual(taxes(plan("--income", "20000", "--si", "3000", "--start", "7", "--end", "8")),
                         [D("360.00"), D("360.00")])
        self.assertEqual(taxes(plan("--income", "20000", "--si", "3000", "--start", "7", "--end", "8",
                                    "--first-job")), [D("0"), D("0")])

    def test_sixty_k(self) -> None:
        t = taxes(plan("--income", "6000", "--si", "600", "--sixty-k"))
        self.assertEqual(t[:11], [D("0")] * 11)
        self.assertEqual(t[11], D("144.00"))

    def test_raise_mid_year(self) -> None:
        r = plan("--income", "10000", "--income-from", "7=20000", "--si", "1000")
        self.assertEqual(r.months[6].income, D("20000"))
        self.assertEqual(r.months[5].income, D("10000"))

    def test_si_from_base_and_rates(self) -> None:
        r = plan("--income", "20000", "--base", "20000", "--si-rate", "10.5", "--hf-rate", "7", "--end", "1")
        m = r.months[0]
        self.assertEqual((m.si, m.hf_paid), (D("2100.00"), D("1400.00")))
        self.assertEqual(m.net, D("20000") - D("2100") - D("1400") - m.tax)

    def test_housing_fund_over_12pct(self) -> None:
        r = plan("--income", "30000", "--base", "30000", "--hf-rate", "15", "--end", "1")
        m = r.months[0]
        self.assertEqual((m.hf_paid, m.hf_deduct, m.excess), (D("4500.00"), D("3600.00"), D("900.00")))

    def test_drop_month_no_refund(self) -> None:
        r = plan("--income", "20000", "--income-set", "2=0", "--end", "3")
        self.assertEqual(r.months[1].tax, D("0"))
        self.assertTrue(all(m.tax >= 0 for m in r.months))


class Bonus(unittest.TestCase):
    def test_compare(self) -> None:
        c = plan("--income", "15000", "--si", "2250", "--special", "2000", "--bonus", "30000").compare
        self.assertEqual((c.sep_total, c.merge_total, c.better, c.saving),
                         (D("5280.00"), D("7380.00"), "单独计税", D("2100.00")))

    def test_merge_better_when_low_wage(self) -> None:
        c = plan("--income", "4000", "--bonus", "20000").compare
        self.assertLess(c.wage_taxable, 0)
        self.assertEqual(c.better, "并入综合所得")

    def test_dead_zone_and_fix(self) -> None:
        c = plan("--income", "12000", "--si", "1800", "--bonus", "37000").compare
        self.assertEqual(c.dead_zone, (D("36000"), D("38566.67")))
        self.assertIn("员工净多拿 2,310.00", c.fixes[0])
        self.assertEqual(bonus_tax_separate(D("36000")), D("1080.00"))
        self.assertEqual(bonus_tax_separate(D("36001")), D("3390.10"))

    def test_top_bracket_bonus(self) -> None:
        self.assertEqual(bonus_tax_separate(D("1200000")), D("524840.00"))

    def test_merge_mode_month(self) -> None:
        r = plan("--income", "15000", "--si", "2250", "--bonus", "30000", "--bonus-mode", "merge")
        self.assertEqual(r.months[-1].bonus_tax, D("0"))
        self.assertEqual(r.total_tax, r.compare.merge_total)

    def test_bonus_only_cli(self) -> None:
        code, out = cli("bonus", "--bonus", "37000")
        self.assertEqual(code, 0)
        self.assertIn("多发反而少拿", out)
        self.assertIn("2027年12月31日", out)

    def test_no_bonus_no_compare(self) -> None:
        self.assertIsNone(plan("--income", "8000").compare)


class Output(unittest.TestCase):
    def test_policy_lines_present(self) -> None:
        code, out = cli("quick", "--income", "15000", "--special", "2000", "--bonus", "30000")
        self.assertEqual(code, 0)
        for s in ("2023年第30号", "2027年12月31日", "地方社保比例以当地为准", "国发〔2023〕13号", "按 0 算"):
            self.assertIn(s, out)

    def test_unit_conversion(self) -> None:
        code, out = cli("quick", "--income", "1.2w", "--bonus", "3.6万", "--si", "1,800")
        self.assertEqual(code, 0)
        self.assertIn("1.2w → 12000", out)
        self.assertIn("3.6万 → 36000", out)
        self.assertIn("正好落在临界点 36,000.00", out)
        code, out = cli("quick", "--income", "12k")
        self.assertIn("12k → 12000", out)
        self.assertNotIn("3.6万", out)

    def test_zones(self) -> None:
        code, out = cli("zones")
        self.assertEqual(code, 0)
        self.assertIn("144,000.00 ~ 160,500.00", out)
        self.assertIn("2,310.10", out)

    def test_pension_and_no_bonus_lines(self) -> None:
        _, out = cli("quick", "--income", "25000", "--other", "1000")
        self.assertIn("领取时单独按3%计税", out)
        self.assertIn("年终奖：未填", out)

    def test_zero_income_ok(self) -> None:
        code, out = cli("quick", "--income", "0")
        self.assertEqual(code, 0)
        self.assertIn("个税合计 0.00", out)

    def test_help_exits_zero(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(geshui.main(["quick", "-h"]), 0)


class KeyPointsAndScope(unittest.TestCase):
    def test_keypoints_quick(self) -> None:
        _, out = cli("quick", "--income", "2万", "--base", "20000", "--si-rate", "10.5", "--hf-rate", "7")
        head = out.split("【输入与假设】")[0]
        self.assertTrue(head.startswith("【回答要点】"))
        self.assertIn("2万 即 20000 元", head)
        self.assertIn("三险个人 2,100.00 元，公积金个人 1,400.00 元", head)
        self.assertIn("1~3月每月 345.00", head)
        self.assertIn("年终奖：这次没算", head)

    def test_keypoints_policy(self) -> None:
        _, out = cli("quick", "--income", "6000", "--si", "600", "--sixty-k")
        self.assertIn("员工可以选择不适用，单位要按规定确认", out.split("【输入与假设】")[0])
        _, out = cli("quick", "--income", "9000", "--start", "7", "--first-job")
        self.assertIn("书面承诺", out.split("【输入与假设】")[0])

    def test_bonus_keypoints_conversion(self) -> None:
        _, out = cli("bonus", "--bonus", "3.6万")
        self.assertIn("3.6万 即 36000 元", out.split("【年终奖单独计税】")[0])

    def test_scope_numbers(self) -> None:
        _, out = cli("scope", "labor", "--amount", "8000")
        self.assertIn("1,280.00 元", out)
        _, out = cli("scope", "labor", "--amount", "3000")
        self.assertIn("440.00 元", out)
        _, out = cli("scope", "royalty", "--amount", "8000")
        self.assertIn("896.00 元", out)
        _, out = cli("scope", "business", "--profit", "300000", "--getihu")
        self.assertIn("37,500.00", out)
        self.assertIn("18,750.00", out)
        _, out = cli("scope", "foreign", "--income", "50000")
        self.assertIn("9,090.00 元/月", out)
        for kind in ("allowance", "avoid"):
            code, out = cli("scope", kind)
            self.assertEqual(code, 0)

    def test_scope_missing_and_bad(self) -> None:
        code, out = cli("scope", "labor")
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("[E01]"))
        code, out = cli("scope", "labor", "--amount", "-5")
        self.assertTrue(out.startswith("[E04]"))
        code, out = cli("scope", "xxx")
        self.assertTrue(out.startswith("[E01]"))
        code, out = cli("scope", "labor", "--amount", "0")
        self.assertEqual(code, 0)


class BadInput(unittest.TestCase):
    def assertErr(self, code: str, exit_code: int, *argv: str) -> None:
        rc, out = cli(*argv)
        self.assertEqual(rc, exit_code, out)
        self.assertTrue(out.startswith(f"[{code}]"), out)
        self.assertIn("怎么办：", out)
        self.assertNotIn("Traceback", out)

    def test_negative(self) -> None:
        self.assertErr("E04", 3, "quick", "--income", "-100")

    def test_text_amount(self) -> None:
        self.assertErr("E02", 3, "quick", "--income", "万")
        self.assertErr("E02", 3, "quick", "--income", "1.5万美元")
        self.assertErr("E02", 3, "quick", "--income", "abc")
        self.assertErr("E02", 3, "quick", "--income", "NaN")

    def test_empty_income(self) -> None:
        self.assertErr("E02", 3, "quick", "--income", "")

    def test_bad_month(self) -> None:
        self.assertErr("E03", 3, "quick", "--income", "8000", "--start", "13")
        self.assertErr("E03", 3, "quick", "--income", "8000", "--start", "9", "--end", "3")
        self.assertErr("E03", 3, "quick", "--income", "8000", "--start", "3", "--bonus", "1", "--bonus-month", "1")

    def test_too_big(self) -> None:
        self.assertErr("E05", 3, "quick", "--income", "99999999999")
        self.assertErr("E05", 3, "quick", "--income", "9000", "--special", "50000")

    def test_conflict(self) -> None:
        self.assertErr("E06", 4, "quick", "--income", "8000", "--first-job", "--sixty-k")
        self.assertErr("E06", 4, "quick", "--income", "8000", "--sixty-k", "--start", "3")

    def test_bad_args(self) -> None:
        self.assertErr("E01", 2, "quick")
        self.assertErr("E01", 2, "quick", "--income", "8000", "--wat")
        self.assertErr("E01", 2, "quick", "--income", "8000", "--hf-rate", "7")
        self.assertErr("E01", 2, "quick", "--income", "8000", "--income-from", "7:9000")

    def test_argparse_messages_in_chinese(self) -> None:
        for argv in (["quick"], ["quick", "--income", "1", "--start", "x"], ["foo"], ["quick", "--income"]):
            _, out = cli(*argv)
            for en in ("required", "invalid", "unrecognized", "expected"):
                self.assertNotIn(en, out)

    def test_bonus_zero(self) -> None:
        self.assertErr("E04", 3, "bonus", "--bonus", "0")

    def test_internal_error_no_traceback(self) -> None:
        with mock.patch.object(engine, "run", side_effect=ZeroDivisionError("x")):
            self.assertErr("E09", 9, "quick", "--income", "8000")

    def test_subprocess_clean(self) -> None:
        p = subprocess.run([sys.executable, str(ROOT / "scripts/geshui.py"), "quick", "--income", "x"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 3)
        self.assertEqual(p.stderr, "")


if __name__ == "__main__":
    unittest.main()
