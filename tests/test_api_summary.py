# -*- coding: utf-8 -*-
"""把「API 返回值 vs 源 summary.json」的比对固化成测试。

两类断言：
  1. 完全一致的字段 → 必须逐字相等（回归保护）
  2. 已知差异字段   → 必须落在白名单描述的差异里（防止差异扩大而无人发现）
"""
import json
import os
import sys
import unittest

import django
from django.conf import settings

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "JobDataPlatform.settings")
if not settings.configured:
    django.setup()

from django.test import Client                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = json.load(open(os.path.join(ROOT, "data", "raw", "summary.json"), encoding="utf-8"))


class SummaryApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = Client().get("/api/stats/summary").json()

    # ---------------- 完全一致的部分 ----------------
    def test_identical_scalars(self):
        """这些字段必须与源完全一致，否则说明口径漂移。"""
        for k in ["total_rows", "wuhan_rows", "wuhan_interns", "wuhan_tech_interns",
                  "wuhan_nontech_interns", "both"]:
            with self.subTest(field=k):
                self.assertEqual(self.api[k], SRC[k], f"{k} 与源不一致")

    def test_identical_dicts(self):
        for k in ["generated_from", "by_source", "by_degree", "stack_counts", "districts"]:
            with self.subTest(field=k):
                self.assertEqual(self.api[k], SRC[k], f"{k} 与源不一致")

    def test_identical_stack_counts_values(self):
        """15 个方向的计数逐项对齐（这个是前端图表的数据源）。"""
        self.assertEqual(len(self.api["stack_counts"]), 15)
        self.assertEqual(self.api["stack_counts"], SRC["stack_counts"])

    def test_python_java_counts(self):
        self.assertEqual(self.api["python"]["count"], SRC["python"]["count"])
        self.assertEqual(self.api["java"]["count"], SRC["java"]["count"])

    def test_java_salary_identical(self):
        """Java 薪资样本与源完全一致（无小写 k 干扰）。"""
        self.assertEqual(self.api["salary_stats"]["java"], SRC["salary_stats"]["java"])

    # ---------------- 已知差异（白名单） ----------------
    def test_known_gap_lowercase_k(self):
        """源脚本用大小写敏感的 "K" in raw，漏了 5 行小写 k。

        预期：本库比源多 5 行（daily_sample_n 504 vs 499；monthly_k 211 vs 206）。
        """
        self.assertEqual(self.api["daily_sample_n"] - SRC["salary_stats"]["all_interns"]["n"], 5)
        self.assertEqual(
            self.api["salary_scope"]["monthly_k"] - SRC["salary_scope"]["monthly_k"], 5)
        self.assertEqual(self.api["intern_salary_known"] - SRC["intern_salary_known"], 5)

    def test_known_gap_python_sample_size(self):
        """小写 k 里有 1 个是 Python 岗 → Python 样本 75 vs 74，分位数不受影响。"""
        a, b = self.api["salary_stats"]["python"], SRC["salary_stats"]["python"]
        self.assertEqual(a["n"] - b["n"], 1)
        for q in ("min", "p25", "median", "p75", "max"):
            self.assertEqual(a[q], b[q], f"Python 的 {q} 不应因小写 k 而变")

    def test_known_gap_all_interns_median(self):
        """全量样本从 499 增到 504，中位数会变 —— 记录变化但不要求相等。"""
        a, b = self.api["salary_stats"]["all_interns"], SRC["salary_stats"]["all_interns"]
        self.assertEqual(a["n"] - b["n"], 5)
        self.assertEqual(a["max"], b["max"])
        self.assertNotEqual(a["median"], b["median"], "若相等说明样本没变，需复查")

    def test_known_gap_profiles_collected(self):
        """源 84 = 抓取的公司档案数；本库 82 = 能关联到岗位的公司数（2 家未关联）。"""
        self.assertEqual(SRC["company_panel"]["profiles_collected"] - 
                         self.api["company_panel"]["profiles_collected"], 2)

    def test_source_bug_total_open_jobs(self):
        """源 summary.json 的 total_open_jobs 是重复累加 bug 值；本库用去重后的正确值。

        company_panel.json 里源自己也写的是 22953，与 summary.json 矛盾。
        """
        self.assertEqual(self.api["company_panel"]["total_open_jobs"], 22953.0)
        self.assertGreater(SRC["company_panel"]["total_open_jobs"], 
                           self.api["company_panel"]["total_open_jobs"],
                           "源的错误值应远大于去重后的正确值")

    # ---------------- 形状 ----------------
    def test_shape_has_all_source_keys(self):
        """源 summary.json 的每个顶层键都应该在 API 返回里。"""
        missing = set(SRC) - set(self.api)
        self.assertEqual(missing, set(), f"API 缺少键: {missing}")

    def test_meta_fields_present(self):
        self.assertEqual(len(self.api["boss_meta"]), 32)
        self.assertEqual(len(self.api["boss_keywords_collected"]), 20)
        self.assertIn("platform_inventory", self.api)
        self.assertTrue(self.api["boss_coverage_note"])

    def test_scope_notes_self_describing(self):
        """返回值必须自带口径说明，避免调用方猜。"""
        notes = self.api["scope_notes"]
        self.assertIn("intern_scope", notes)
        self.assertEqual(notes["intern_scope_rows"], self.api["wuhan_interns"])
        self.assertEqual(notes["daily_sample_rows"], self.api["daily_sample_n"])


class HealthApiTest(unittest.TestCase):
    def test_health_ok(self):
        r = Client().get("/api/health")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["jobs"], 3013)
        self.assertEqual(d["job_descriptions"], 156)
        self.assertTrue(d["mysql_version"].startswith("8."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
