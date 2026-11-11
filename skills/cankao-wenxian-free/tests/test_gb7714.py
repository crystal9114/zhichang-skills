"""脚本回归测试：python3 -m unittest discover -s tests（只用标准库）。示例取自 GB/T 7714—2015 / 2025 附录的公开示例。"""
import datetime as dt
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(HERE))

from ref_check import check_list  # noqa: E402
from ref_render import make_opts  # noqa: E402

TODAY = dt.date(2026, 11, 3)
CLI = [sys.executable, str(HERE / "gb7714.py")]


def one(text, edition="2015", **kw):
    c = check_list(text, make_opts(edition, **kw), TODAY)[0]
    return c.text, [(i.level, i.field) for i in c.ref.issues]


def cli(*args, stdin=""):
    r = subprocess.run(CLI + list(args) + ["--today", "2026-11-03"], input=stdin.encode("utf-8"),
                       capture_output=True, timeout=60)
    return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8")


class Authors(unittest.TestCase):
    def test_more_than_three_zh(self):
        t, iss = one("袁训来, 陈哲, 肖书海, 王伟. 蓝田生物群[J]. 科学通报, 2012, 55(34): 3219-3227.")
        self.assertTrue(t.startswith("袁训来, 陈哲, 肖书海, 等. 蓝田生物群[J]"))
        self.assertIn(("改", "著者"), iss)

    def test_more_than_three_en_2015_upper(self):
        t, _ = one("Myburg A A, Grattapaglia D, Tuskan G A, Hellsten U. The genome of Eucalyptus grandis[J]. Nature, 2014, 510: 356-362.")
        self.assertTrue(t.startswith("MYBURG A A, GRATTAPAGLIA D, TUSKAN G A, et al. The genome"))

    def test_2025_title_case(self):
        t, _ = one("MYBURG A A, GRATTAPAGLIA D, TUSKAN G A, et al. The genome of Eucalyptus grandis[J]. Nature, 2014, 510: 356-362.", "2025")
        self.assertTrue(t.startswith("Myburg A A, Grattapaglia D, Tuskan G A, et al. The genome"))

    def test_three_exact_no_etal(self):
        t, _ = one("钱学森, 刘再复, 李四光. 某书[M]. 北京: 科学出版社, 1990.")
        self.assertNotIn("等", t.split(".")[0])

    def test_etal_with_too_few(self):
        _, iss = one("张三, 等. 某研究[J]. 某学报, 2020, 1(1): 1-5.")
        self.assertIn(("补", "著者"), iss)

    def test_org_with_he_not_split(self):
        t, _ = one("中华人民共和国国务院新闻办公室. 国防白皮书[R/OL]. (2013-04-16)[2014-06-11]. http://www.mod.gov.cn.")
        self.assertTrue(t.startswith("中华人民共和国国务院新闻办公室. 国防白皮书[R/OL]. (2013-04-16)[2014-06-11]."))

    def test_initials_dots_removed(self):
        t, _ = one("Smith J. A., Jones B. Title here[J]. Nature, 2020, 1(2): 3-4.")
        self.assertTrue(t.startswith("SMITH J A, JONES B. Title here"))


class Fields(unittest.TestCase):
    def test_missing_pages_not_invented(self):
        t, iss = one("李四. 某研究[J]. 某学报, 2020, 12(3).")
        self.assertIn(("补", "页码"), iss)
        self.assertNotRegex(t, r": \d")

    def test_missing_place_from_table(self):
        t, iss = one("吴云芳. 并列结构研究[D]. 北京大学, 2003.")
        self.assertIn("北京: 北京大学, 2003", t)
        self.assertIn(("核", "出版地"), iss)

    def test_unknown_publisher_place_asked(self):
        _, iss = one("王五. 某书[M]. 某某小出版社, 2003.")
        self.assertIn(("补", "出版地"), iss)

    def test_bad_type_alias(self):
        t, iss = one("王五. 某某研究[学位论文]. 上海: 复旦大学, 2019.")
        self.assertIn("[D]. 上海: 复旦大学, 2019", t)

    def test_page_dash_and_abbrev(self):
        t, iss = one("某甲. 题名[J]. 刊名, 2020, 5(2): 1234–56.")
        self.assertIn(": 1234-1256.", t)

    def test_edition(self):
        t, _ = one("库恩. 科学革命的结构[M]. 金吾伦, 译. 第2版. 北京: 北京大学出版社, 2012.")
        self.assertIn("金吾伦, 译. 2版. 北京: 北京大学出版社, 2012.", t)

    def test_first_edition_dropped(self):
        t, _ = one("某乙. 某书[M]. 第1版. 北京: 科学出版社, 2012.")
        self.assertNotIn("版.", t)

    def test_doi_normalised(self):
        t, _ = one("某甲. 题名[J]. 刊名, 2020, 5(2): 1-2. doi:10.1000/xyz123")
        self.assertTrue(t.endswith("DOI: 10.1000/xyz123."))

    def test_bad_doi_flagged(self):
        _, iss = one("某甲. 题名[J]. 刊名, 2020, 5(2): 1-2. DOI: 10.12/ab")
        self.assertIn(("核", "DOI"), iss)

    def test_web_needs_cite_date(self):
        _, iss = one("李强. 化解医患矛盾[EB/OL]. http://www.example.com/a.html.")
        self.assertIn(("补", "引用日期"), iss)

    def test_cite_date_future(self):
        _, iss = one("李强. 化解医患矛盾[EB/OL]. (2012-05-03)[2027-04-15]. http://www.example.com/a.html.")
        self.assertIn(("核", "引用日期"), iss)

    def test_2025_drops_cite_date_for_journal(self):
        t, iss = one("李炳穆. 韩国图书馆法[J/OL]. 图书情报工作, 2008, 52(6): 6-12[2013-10-25]. http://www.docin.com/p-1.html.", "2025")
        self.assertNotIn("2013-10-25", t)
        t15, _ = one("李炳穆. 韩国图书馆法[J/OL]. 图书情报工作, 2008, 52(6): 6-12[2013-10-25]. http://www.docin.com/p-1.html.")
        self.assertIn("6-12[2013-10-25]", t15)

    def test_standard_both_editions(self):
        t15, _ = one("信息与文献 参考文献著录规则: GB/T 7714—2015[S]. 北京: 中国标准出版社, 2015: 15.")
        self.assertTrue(t15.startswith("信息与文献 参考文献著录规则: GB/T 7714—2015[S]. 北京"))
        t25, _ = one("GB/T 3792-2021 信息与文献 资源描述[S].", "2025")
        self.assertEqual(t25, "GB/T 3792—2021 信息与文献 资源描述[S].")

    def test_apa_to_gb(self):
        t, _ = one("Vaswani, A., Shazeer, N., Parmar, N., & Uszkoreit, J. (2017). Attention is all you need. "
                   "Advances in Neural Information Processing Systems, 30, 5998–6008.")
        self.assertEqual(t, "VASWANI A, SHAZEER N, PARMAR N, et al. Attention is all you need[J]. "
                            "Advances in Neural Information Processing Systems, 2017, 30: 5998-6008.")

    def test_no_marker_analytic(self):
        t, iss = one("汪学军. 转基因生物安全管理//国家环境保护总局. 某某研讨会论文集. 北京: 中国环境科学出版社, 2002: 22-25.")
        self.assertTrue(t.startswith("汪学军. 转基因生物安全管理[C]//国家环境保护总局. 某某研讨会论文集."))

    def test_unparseable_kept(self):
        t, iss = one("科学 2019 某某 出 版社 研究 张 的 方法 北京")
        self.assertEqual(t, "科学 2019 某某 出 版社 研究 张 的 方法 北京")
        self.assertIn(("核", "整体"), iss)

    def test_newspaper(self):
        t, _ = one("丁文祥. 数字革命与竞争国际化[N]. 中国青年报, 2000-11-20(15).")
        self.assertEqual(t, "丁文祥. 数字革命与竞争国际化[N]. 中国青年报, 2000-11-20(15).")

    def test_analytic(self):
        t, _ = one("白书农. 植物开花研究[M]//李承森. 植物科学进展. 北京: 高等教育出版社, 1998: 146-163.")
        self.assertEqual(t, "白书农. 植物开花研究[M]//李承森. 植物科学进展. 北京: 高等教育出版社, 1998: 146-163.")

    def test_en_title_starting_with_article(self):
        t, iss = one("Wang X, Li Y. A study of graphs[J]. Nature, 2020, 1(2): 3-4.", "2025")
        self.assertTrue(t.startswith("Wang X, Li Y. A study of graphs[J]"))
        self.assertNotIn(("补", "著者"), iss)

    def test_missing_author_asked(self):
        _, iss = one("某研究报告全文[R]. 北京: 科学出版社, 2020.", "2025")
        self.assertIn(("补", "著者"), iss)

    def test_same_input_same_output(self):
        a = one("Smith J, Brown K, Lee M, Davis R. Deep learning[J]. Nature, 2019, 521(7553): 436-444.")
        b = one("Smith J, Brown K, Lee M, Davis R. Deep learning[J]. Nature, 2019, 521(7553): 436-444.")
        self.assertEqual(a, b)


class Upgrade(unittest.TestCase):
    LIST = ("[1] SMITH J, BROWN K. Deep learning[J]. Nature, 2019, 521(7553): 436-444.\n"
            "[2] 陈刚. 某某研究[J/OL]. 情报学报, 2019, 38(2): 100-110[2024-01-01]. https://kns.cnki.net/x.\n"
            "[3] 信息与文献 参考文献著录规则: GB/T 7714—2015[S]. 北京: 中国标准出版社, 2015.\n"
            "[4] 刘洋. 高校图书馆服务创新研究[D]. 武汉: 武汉大学, 2021.\n"
            "[5] VASWANI A, SHAZEER N, PARMAR N, et al. Attention is all you need[EB/OL]. (2017-06-12)[2024-03-01]. "
            "https://arxiv.org/abs/1706.03762.\n")

    def test_all_six_rules(self):
        code, out, _ = cli("upgrade", "-", stdin=self.LIST + "[6] 王强. 一种装置: CN201810123456.7[P]. 2019-05-10.\n")
        self.assertEqual(code, 0)
        self.assertIn("命中 6 处", out)
        self.assertIn("[1] Smith J, Brown K. Deep learning[J]", out)
        self.assertIn("[2] 陈刚. 某某研究[J/OL]. 情报学报, 2019, 38(2): 100-110. https://kns.cnki.net/x.", out)
        self.assertIn("[3] GB/T 7714—2015 信息与文献 参考文献著录规则[S].", out)
        self.assertIn("[PP/OL]. (2017-06-12)[2024-03-01]", out)
        self.assertIn("2026-07-01 实施", out)
        self.assertIn("以学校/期刊为准", out)

    def test_only_some_rules(self):
        code, out, _ = cli("upgrade", "-", stdin="[1] 王明. 机器学习导论[M]. 北京: 清华大学出版社, 2018.\n")
        self.assertEqual(code, 0)
        self.assertIn("命中 0 处", out)
        self.assertIn("未命中：1. 西文", out)


class Cli(unittest.TestCase):
    def test_fix_default_2025(self):
        code, out, _ = cli("fix", "-", stdin="李四. 某研究[J]. 某学报, 2020, 12(3).\n")
        self.assertEqual(code, 0)
        self.assertIn("GB/T 7714—2025", out)
        self.assertIn("【待补：页码】", out)

    def test_fix_2015(self):
        code, out, _ = cli("fix", "-", "--edition", "2015", stdin="Smith J. Deep[J]. Nature, 2019, 1(2): 3-4.\n")
        self.assertEqual(code, 0)
        self.assertIn("SMITH J. Deep[J]", out)

    def test_max_authors_all(self):
        code, out, _ = cli("fix", "-", "--max-authors", "50", stdin="甲, 乙, 丙, 丁. 题名[J]. 刊, 2020, 1(1): 1-2.\n")
        self.assertIn("甲, 乙, 丙, 丁. 题名", out)

    # 反向用例：空值、超范围数、0、错文件、错日期
    def test_empty_input(self):
        code, out, err = cli("fix", "-", stdin="   \n")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("E03"))
        self.assertNotIn("Traceback", err)

    def test_max_authors_zero(self):
        code, _, err = cli("fix", "-", "--max-authors", "0", stdin="甲. 题[J]. 刊, 2020, 1(1): 1-2.\n")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("E05"))

    def test_max_authors_too_big(self):
        code, _, err = cli("fix", "-", "--max-authors", "999", stdin="甲. 题[J]. 刊, 2020, 1(1): 1-2.\n")
        self.assertTrue(err.startswith("E05"))

    def test_max_authors_not_int(self):
        code, _, err = cli("fix", "-", "--max-authors", "三", stdin="甲. 题[J]. 刊, 2020, 1(1): 1-2.\n")
        self.assertTrue(err.startswith("E05"))
        self.assertNotIn("usage:", err)

    def test_bad_cite_date(self):
        for d in ("2024-13-40", "昨天", "1900-01-01", "2099-01-01"):
            code, _, err = cli("fix", "-", "--cite-date", d, stdin="甲. 题[EB/OL]. https://a.cn/x.\n")
            self.assertEqual(code, 2, d)
            self.assertTrue(err.startswith("E05"), d)

    def test_missing_file(self):
        code, _, err = cli("fix", "/no/such/file.txt")
        self.assertTrue(err.startswith("E01"))

    def test_docx_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "论文.docx"
            p.write_bytes(b"PK")
            code, _, err = cli("fix", str(p))
        self.assertTrue(err.startswith("E02"))

    def test_bad_mode(self):
        code, _, err = cli("apa", "-", stdin="甲. 题[J]. 刊, 2020, 1(1): 1-2.\n")
        self.assertTrue(err.startswith("E05"))
        self.assertNotIn("Traceback", err)

    def test_not_references(self):
        code, _, err = cli("fix", "-", stdin="今天天气很好我们去公园散步然后回家吃饭\n")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("E04"))

    def test_too_many(self):
        code, _, err = cli("fix", "-", stdin="甲. 题[J]. 刊, 2020, 1(1): 1-2.\n" * 501)
        self.assertTrue(err.startswith("E06"))


if __name__ == "__main__":
    unittest.main()
