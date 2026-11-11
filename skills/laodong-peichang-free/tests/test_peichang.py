"""peichang.py 单测：口径正例 + 反向用例（超范围数、0 元、空值、乱码参数都要回 E 码，不能甩堆栈）。

  python3 -m pytest products/laodong-peichang-lite/tests -q
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from decimal import Decimal
from datetime import date

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "peichang.py"
sys.path.insert(0, str(ROOT / "scripts"))

from ldlib import calc, case as casemod, dates, laws  # noqa: E402

APPLY = "2026-11-03"


def run(*args: str) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60)
    assert "Traceback" not in p.stdout + p.stderr, p.stdout + p.stderr
    return p.returncode, p.stdout


def quick(*args: str) -> str:
    rc, out = run("quick", "--apply", APPLY, *args)
    assert rc == 0, out
    return out


def facts(**kw) -> calc.Facts:
    base = dict(entry=date(2021, 3, 15), leave=date(2026, 9, 30), apply=date(2026, 11, 3), wage=Decimal(15000),
                wage_src="测试", reason="illegal_dismissal", city="上海", contract="签了", al_years=None)
    base.update(kw)
    return calc.Facts(**base)


# ---------- 年限折算 ----------
@pytest.mark.parametrize("start,end,months", [
    ("2026-01-01", "2026-03-31", 0.5),       # 3 个月
    ("2025-11-10", "2026-10-09", 1.0),       # 11 个月，满 6 个月按 1 年
    ("2023-01-01", "2026-06-30", 4.0),       # 3 年 6 个月
    ("2023-01-01", "2026-02-28", 3.5),       # 3 年 2 个月
    ("2021-04-01", "2021-08-31", 0.5),       # 5 个月整
    ("2021-04-01", "2021-09-01", 0.5),       # 5 个月零 1 天：仍不满 6 个月（参考源在这里跳成 1）
    ("2021-03-15", "2026-03-14", 5.0),       # 整 5 年，没有零头
])
def test_comp_months(start, end, months):
    sp = dates.span(dates.parse(start, "s"), dates.parse(end, "e"))
    assert dates.comp_months(sp) == months


def test_illegal_2n_not_add_notice():
    res = calc.compute(facts())
    assert [i.key for i in res.claimed] == ["2n"]
    assert res.total == Decimal("180000.00")


def test_cap_links_12_years():
    res = calc.compute(facts(entry=date(2011, 1, 1), leave=date(2026, 6, 30), wage=Decimal(50000),
                             reason="employer_negotiated", city="北京"))
    n = next(i for i in res.items if i.key == "n")
    assert n.amount == Decimal("436176.00")            # 36348 × 12
    assert "12 年" in "".join(n.detail)


def test_no_cap_no_12_limit():
    res = calc.compute(facts(entry=date(2010, 1, 1), leave=date(2026, 6, 30), wage=Decimal(10000),
                             reason="employer_negotiated", city="北京"))
    n = next(i for i in res.items if i.key == "n")
    assert n.amount == Decimal("170000.00")            # 16.5 年 → 17 个月，不封顶也不受 12 年限
    assert "不受 12 年上限" in "".join(n.detail)


def test_split_2008():
    res = calc.compute(facts(entry=date(1999, 1, 1), leave=date(2026, 6, 30), wage=Decimal(10000),
                             reason="employer_negotiated", city="长沙"))
    assert next(i for i in res.items if i.key == "n").amount == Decimal("280000.00")


def test_objective_notice_unknown_not_in_total():
    res = calc.compute(facts(entry=date(2022, 7, 1), leave=date(2026, 10, 15), wage=Decimal(12000),
                             reason="objective", city="北京", notice="未知"))
    assert res.total == Decimal("54000.00")
    assert any("30 天" in q for q, _ in res.questions)
    res2 = calc.compute(facts(entry=date(2022, 7, 1), leave=date(2026, 10, 15), wage=Decimal(12000),
                              reason="objective", city="北京", notice="没有"))
    assert res2.total == Decimal("66000.00")


def test_double_wage_max_11_months():
    res = calc.compute(facts(entry=date(2025, 3, 1), leave=date(2026, 10, 31), wage=Decimal(9000),
                             reason="employee_resign", contract="没签"))
    d = next(i for i in res.items if i.key == "double")
    assert d.amount == Decimal("99000.00")             # 9000 × 11
    assert res.total == Decimal("99000.00")


def test_double_wage_late_signing():
    res = calc.compute(facts(entry=date(2026, 1, 5), leave=date(2026, 10, 30), wage=Decimal(8000),
                             reason="employee_resign", contract="补签", signed_date=date(2026, 6, 5)))
    d = next(i for i in res.items if i.key == "double")
    assert d.amount == Decimal("32000.00")             # 2026-02-05 至 2026-06-04，4 个月


def test_double_wage_time_barred_monthly():
    res = calc.compute(facts(entry=date(2024, 1, 1), leave=date(2025, 12, 31), apply=date(2026, 11, 3),
                             wage=Decimal(6000), reason="employee_resign", contract="没签"))
    d = next(i for i in res.items if i.key == "double")
    assert d.amount == 0 and not d.claim                # 二倍工资到 2024-12-31 止，2025-12-31 已过


def test_annual_leave_200_percent():
    res = calc.compute(facts(entry=date(2020, 1, 1), leave=date(2026, 6, 30), wage=Decimal(21750),
                             reason="employee_resign", al_years=Decimal(6)))
    lv = next(i for i in res.items if i.key == "leave")
    assert lv.amount == Decimal("4000.00")             # 181/365×5=2.47→2 天；1000×2×2


def test_time_barred_total_zero():
    res = calc.compute(facts(leave=date(2024, 9, 30), apply=date(2026, 11, 3)))
    assert res.total == 0 and res.barred


def test_unknown_reason_no_conclusion():
    res = calc.compute(facts(reason="unknown"))
    assert not res.reason_confirmed and res.total == 0


def test_misconduct_listed_as_disputed_2n():
    res = calc.compute(facts(reason="misconduct"))
    assert [i.key for i in res.claimed] == ["2n"]
    assert any("存疑" in d for d in res.doubts)


def test_laws_full_name():
    s = laws.cite(("LCL-47", "LCL-87", "REG-25"))
    assert s == "《中华人民共和国劳动合同法》第四十七条、第八十七条；《中华人民共和国劳动合同法实施条例》第二十五条"


# ---------- 命令行 ----------
def test_cli_quick_text_has_judge_lines():
    out = quick("--entry", "2021-03-15", "--leave", "2026-09-30", "--wage", "15000", "--reason", "违法解除",
                "--city", "上海", "--contract", "签了")
    assert "180,000.00" in out
    assert "《中华人民共和国劳动合同法》第四十八条、第八十七条、第四十七条" in out
    assert "以当地劳动人事争议仲裁委员会" in out
    assert "截止 2027-09-30" in out


def test_cli_parts_bonus_divided():
    out = quick("--entry", "2023-01-01", "--leave", "2026-06-30", "--parts", "基本工资=6000,绩效=2000,年终奖=24000",
                "--reason", "employer_negotiated", "--city", "上海", "--contract", "签了")
    assert "10,000.00 × 4 个月 = 40,000.00" in out
    assert "年终奖" in out and "存疑" in out


def test_cli_check_asks_reason_first():
    rc, out = run("check", "--leave", "2026-09-30", "--apply", APPLY)
    assert rc == 0 and "谁提出解除" in out and "未过" in out


def test_cli_check_stop_flag():
    rc, out = run("check", "--flags", "外包,境外", "--apply", APPLY)
    assert rc == 0 and "外包" in out and "境外" in out


@pytest.mark.parametrize("args,code", [
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "0"], "E04"),
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "-5"], "E04"),
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "99999999999"], "E04"),
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "一万"], "E04"),
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "nan"], "E04"),
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", ""], "E05"),
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff"], "E05"),
    (["quick", "--entry", "", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "8000"], "E05"),
    (["quick", "--years", "-3", "--reason", "layoff", "--wage", "8000"], "E04"),
    (["quick", "--years", "99", "--reason", "layoff", "--wage", "8000"], "E04"),
    (["quick", "--entry", "2021-02-30", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "8000"], "E03"),
    (["quick", "--entry", "2023-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "8000"], "E03"),
    (["quick", "--entry", "1900-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "8000"], "E03"),
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "跑路", "--wage", "8000"], "E06"),
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "8000", "--flags", "火星"], "E06"),
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "8000", "--flags", "派遣"], "E07"),
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "8000", "--flags", "刑事"], "E07"),
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "8000", "--contract", "补签"], "E05"),
    (["quick", "--entry", "2021-01-01"], "E08"),
    (["quick", "--nope"], "E08"),
    (["bogus"], "E08"),
    (["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "8000", "--al-prev", "abc"], "E04"),
    (["check", "--leave", "昨天"], "E03"),
])
def test_cli_errors_have_code(args, code):
    rc, out = run(*args)
    assert rc != 0
    assert f"错误码：{code}" in out and "怎么办：" in out


def test_unexpected_exception_wrapped(monkeypatch, capsys):
    import peichang  # noqa: PLC0415

    def boom(*a, **k):
        raise ZeroDivisionError("x")
    monkeypatch.setattr(peichang.calc, "compute", boom)
    rc = peichang.main(["quick", "--entry", "2021-01-01", "--leave", "2022-01-01", "--reason", "layoff", "--wage", "8000"])
    out = capsys.readouterr().out
    assert rc == 9 and "E99" in out and "Traceback" not in out


def test_help_is_chinese():
    rc, out = run("quick", "-h")
    assert rc == 0 and "用法" in out and "离职方式" in out


def test_reason_alias_and_flags():
    assert casemod.reason_code("违法解除") == "illegal_dismissal"
    assert casemod.flag_set("派遣、外包") == {"dispatch", "outsourcing"}


def test_years_assumed_exact():
    out = quick("--years", "4", "--leave", "2026-10-31", "--wage", "7000", "--reason", "layoff", "--contract", "签了")
    assert "7,000.00 × 4 个月 = 28,000.00" in out and "假设" in out


def test_rough_marks_premise():
    out = quick("--years", "4", "--leave", "2026-10-31", "--wage", "7000", "--reason", "违法解除", "--flags", "派遣", "--rough")
    assert "粗算，不是结论" in out and "劳务派遣" in out and "56,000.00" in out


# ---------- 【回答开头照抄】【还要问（逐条照抄）】：五种情形由脚本打出整句 ----------
HEAD, ASK = "【回答开头照抄】", "【还要问（逐条照抄）】"


def sections(out: str) -> tuple[str, list[str]]:
    assert HEAD in out and ASK in out, out
    head = out.split(HEAD, 1)[1].split("\n## ", 1)[0]
    asks = [ln for ln in out.split(ASK, 1)[1].split("\n## ", 1)[0].splitlines() if ln[:1].isdigit()]
    return head, asks


def test_lead_dispatch_rough_range_not_conclusion():
    out = quick("--years", "4", "--wage", "7000", "--reason", "unknown", "--flags", "派遣", "--rough")
    head, asks = sections(out)
    assert "不能直接按普通辞退算出确定金额" in head and "第九十二条第二款" in head
    assert "28,000.00 元到违法解除赔偿金 2N 约 56,000.00 元" in head and "不是结论" in head
    assert "首要下一步" in head and "律师" in head and "仲裁委员会" in head
    assert any("派遣公司签的" in a for a in asks) and any("待岗" in a for a in asks)
    assert out.index(HEAD) < out.index("## 结论")


def test_lead_dispatch_rough_conclusion_is_range():
    out = quick("--years", "4", "--wage", "7000", "--reason", "违法解除", "--flags", "派遣", "--rough")
    assert "## 结论（粗算区间，不是结论）" in out
    assert "可主张合计" not in out and "粗算参考 " not in out


def test_lead_outsourcing_check_without_wage():
    rc, out = run("check", "--flags", "外包", "--reason", "unknown", "--apply", APPLY)
    assert rc == 0
    head, asks = sections(out)
    assert "外包驻场不能直接按普通辞退给出确定金额" in head and "不是向甲方" in head and "首要下一步" in head
    assert len([a for a in asks if "签的" in a or "发的" in a or "交的" in a]) == 3   # 合同、工资、社保分三问


def test_lead_overseas_mainland_law_only():
    rc, out = run("check", "--flags", "境外", "--reason", "unknown", "--apply", APPLY)
    head, asks = sections(out)
    assert head.split("\n> ", 1)[1].startswith("本技能只按中国大陆劳动法测算")
    assert "涉外劳动的律师" in head
    assert any("境外公司签的" in a for a in asks)


def test_lead_fuzzy_years_asks_exact_dates():
    out = quick("--years", "3多", "--wage", "10000", "--reason", "unknown")
    head, asks = sections(out)
    assert "3.5 个月" in head and "4 个月" in head and "35,000.00 元或 40,000.00 元" in head
    assert "N+1 只在单位依《中华人民共和国劳动合同法》第四十条解除" in head
    assert any("准确的入职日" in a for a in asks) and any("准确的离职日" in a for a in asks)
    assert any("提前 30 天书面通知" in a for a in asks)


def test_lead_transfer_separate_questions():
    out = quick("--years", "4", "--wage", "7000", "--reason", "unknown", "--flags", "调岗")
    head, asks = sections(out)
    assert "自己辞职一般没有经济补偿" in head and "第三十八条" in head and "个人原因" in head
    joined = "\n".join(asks)
    for k in ("工资有没有降", "书面通知", "拖欠或克扣", "足额交社保"):
        assert sum(k in a for a in asks) == 1, joined   # 四件事各占一问，不合并
    assert "调岗有没有降薪、有没有书面通知，单位有没有欠薪" not in out


def test_lead_plain_case_has_conclusion_base_and_limitation():
    out = quick("--entry", "2021-03-15", "--leave", "2026-09-30", "--wage", "15000", "--reason", "违法解除", "--city", "上海")
    head = out.split(HEAD, 1)[1].split("\n## ", 1)[0]
    assert "如果单位拿不出合法解除的理由和证据，你可以主张合计 180,000.00 元" in head
    assert "扣社保、个税之前，不是到手工资" in head
    assert "截止 2027-09-30" in head and "《中华人民共和国劳动争议调解仲裁法》第二十七条" in head
    assert ASK not in out          # 事实齐全，没有必须追问的


def test_lead_barred_asks_interruption():
    out = quick("--entry", "2019-03-01", "--leave", "2024-08-31", "--wage", "10000", "--reason", "裁员")
    head, asks = sections(out)
    assert "已过一年仲裁时效" in head and "第二十七条第二款" in head
    assert any("书面找单位要过钱" in a for a in asks)


def test_lead_misconduct_no_flat_total():
    out = quick("--entry", "2024-02-20", "--leave", "2026-10-20", "--wage", "9000", "--reason", "misconduct", "--city", "深圳")
    head = out.split(HEAD, 1)[1].split("\n## ", 1)[0]
    assert "可以主张合计" not in head


def test_years_bad_suffix_is_e04():
    rc, out = run("quick", "--years", "三年多", "--wage", "7000", "--reason", "unknown", "--apply", APPLY)
    assert rc != 0 and "E04" in out


def test_lead_criminal_out_of_scope_and_police():
    rc, out = run("check", "--flags", "刑事", "--reason", "unknown", "--apply", APPLY)
    head, asks = sections(out)
    assert head.split("\n> ", 1)[1].startswith("刑事部分不在本技能范围")
    assert "公安机关" in head and "劳动监察" in head and "劳动仲裁" in head and "第二百七十六条之一" in head
    assert "职务侵占" in head and "由单位承担举证责任" in head
    assert any("报警指控你" in a for a in asks) and any("解除理由" in a for a in asks)


def test_lead_pregnant_2n_or_continue():
    out = quick("--entry", "2024-09-01", "--leave", "2026-10-31", "--wage", "12000", "--reason", "objective",
                "--flags", "孕期", "--city", "上海")
    head, _ = sections(out) if ASK in out else (out.split(HEAD, 1)[1].split("\n## ", 1)[0], [])
    assert "第四十二条" in head and "2N 60,000.00 元" in head and "继续履行劳动合同" in head and "N 30,000.00 元不算合法了结" in head


def test_lead_misconduct_burden_on_employer():
    out = quick("--entry", "2024-02-20", "--leave", "2026-10-20", "--wage", "9000", "--reason", "misconduct", "--city", "深圳")
    head, asks = sections(out)
    assert "由单位承担举证责任" in head and "2N 54,000.00 元" in head and "不是一定能拿到" in head
    assert any("哪一条规章制度" in a for a in asks) and any("签收" in a for a in asks) and any("证据" in a for a in asks)


def test_capped_note_local_caliber():
    out = quick("--entry", "2011-01-01", "--leave", "2026-06-30", "--wage", "50000", "--reason", "协商-单位提出", "--city", "北京")
    concl = out.split("## 结论", 1)[1].split("\n## ", 1)[0]
    assert "封顶线以当地人社部门公布数和劳动人事争议仲裁委员会的口径为准" in concl


def test_check_accepts_fuzzy_years():
    rc, out = run("check", "--years", "3多", "--wage", "10000", "--reason", "unknown", "--apply", APPLY)
    assert rc == 0, out
    head, asks = sections(out)
    assert "35,000.00 元或 40,000.00 元" in head and any("准确的入职日" in a for a in asks)
