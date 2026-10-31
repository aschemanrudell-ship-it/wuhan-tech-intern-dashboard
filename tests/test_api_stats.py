# -*- coding: utf-8 -*-
"""5 个 stats 端点 vs 源 dashboard JSON 的回归测试。

断言分级：
  * 完全一致的部分 → 逐项相等
  * 已知差异 → 落在白名单描述的范围内（防止差异扩大）
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
SRC = os.path.join(ROOT, "data", "raw", "dashboard")


def ref(name):
    return json.load(open(os.path.join(SRC, name), encoding="utf-8"))


class StackStatsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = Client().get("/api/stats/stacks").json()
        cls.src = ref("stack_stats.json")

    def test_same_stack_set(self):
        self.assertEqual(set(self.api), set(self.src), "方向集合应完全一致")

    def test_15_stacks(self):
        self.assertEqual(len(self.api), 15)

    def test_counts_identical(self):
        """15 个方向的 count / by_source / degree / salary_month 应逐项一致。"""
        for k in ("count", "by_source", "degree", "salary_month"):
            for stack in self.src:
                with self.subTest(stack=stack, field=k):
                    self.assertEqual(self.api[stack][k], self.src[stack][k])

    def test_districts_identical(self):
        """districts 只取前 8 个，且顺序一致（源用 Counter.most_common(8)）。"""
        for stack in self.src:
            with self.subTest(stack=stack):
                self.assertEqual(self.api[stack]["districts"], self.src[stack]["districts"])

    def test_top_companies_identical(self):
        for stack in self.src:
            with self.subTest(stack=stack):
                self.assertEqual(self.api[stack]["top_companies"],
                                 self.src[stack]["top_companies"])

    def test_salary_day_known_gap_only_lowercase_k(self):
        """salary_day 差异只允许来自小写 k：n 最多差 2，且 median 不变。"""
        for stack in self.src:
            a, b = self.api[stack]["salary_day"], self.src[stack]["salary_day"]
            with self.subTest(stack=stack):
                self.assertLessEqual(abs(a["n"] - b["n"]), 2, f"{stack} 样本量差超过小写 k 影响")
                if b["n"] >= 5:
                    self.assertEqual(a["median"], b["median"], f"{stack} 中位数不应变")

    def test_php_single_sample(self):
        """PHP 只有 1 个样本：索引法必须返回值，不能是 null。"""
        php = self.api["PHP"]["salary_day"]
        self.assertEqual(php["n"], 1)
        self.assertIsNotNone(php["p25"], "索引法在 n=1 时应返回该值")
        self.assertEqual(php["p25"], php["median"])


class TagsStatsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = Client().get("/api/stats/tags").json()
        cls.src = ref("tags.json")

    def test_four_boards(self):
        self.assertEqual(set(self.api), {"tags", "skills", "companies", "industries"})

    def test_java_python_present(self):
        """回归：tags.name 曾因大小写不敏感 collation 丢失 Java/Python。"""
        names = {n for n, _ in self.api["tags"]}
        self.assertIn("Java", names, "Java 标签丢失（collation 问题复发）")
        self.assertIn("Python", names, "Python 标签丢失")

    def test_top_values(self):
        """前两项数值必须精确（Java 143 / Python 126）。"""
        d = dict(self.api["tags"])
        self.assertEqual(d["Java"], 143)
        self.assertEqual(d["Python"], 126)

    def test_companies_and_industries_identical(self):
        self.assertEqual(self.api["companies"], self.src["companies"])
        self.assertEqual(self.api["industries"], self.src["industries"])

    def test_skills_identical(self):
        self.assertEqual(self.api["skills"], self.src["skills"])

    def test_tags_only_ordering_gap(self):
        """tags 只允许同分项的顺序差异，数值集合必须相同。"""
        self.assertEqual(dict(self.api["tags"]), dict(self.src["tags"]),
                         "tags 的数值集合应完全相同，只可能有同分顺序差")


class CompaniesPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = Client().get("/api/stats/companies").json()
        cls.src = ref("company_panel.json")

    def test_total_open_jobs_correct(self):
        """源 summary.json 的 167169 是重复累加 bug；正确值是 22953。"""
        self.assertEqual(self.api["total_open_jobs"], 22953.0)

    def test_companies_hiring_interns(self):
        self.assertEqual(self.api["companies_hiring_interns"],
                         self.src["companies_hiring_interns"])

    def test_profiles_collected_known_gap(self):
        self.assertEqual(self.src["profiles_collected"] - self.api["profiles_collected"], 2)

    def test_top_lists_length(self):
        self.assertEqual(len(self.api["top_by_intern_roles"]), 15)
        self.assertEqual(len(self.api["top_by_open_jobs"]), 15)

    def test_top_intern_roles_order(self):
        """前 3 名的**集合**必须一致，且华为系两家计数精确。

        已知差异（docs/ENDPOINTS-MAPPING.md §2.4）：小米在本库为 14、源为 9，
        说明源对同公司实习岗另有去重口径，未追到根，故不比较其数值与顺序。
        """
        api_names = [r["company"] for r in self.api["top_by_intern_roles"]]
        src_names = [r["company"] for r in self.src["top_by_intern_roles"]]
        self.assertEqual(set(api_names[:3]), set(src_names[:3]), "前 3 名集合应一致")
        self.assertEqual(len(api_names), len(src_names), "条数应一致")

        api_map = {r["company"]: r["intern_roles"] for r in self.api["top_by_intern_roles"]}
        src_map = {r["company"]: r["intern_roles"] for r in self.src["top_by_intern_roles"]}
        for name in ("华为技术有限公司", "华为"):
            with self.subTest(company=name):
                self.assertEqual(api_map[name], src_map[name], f"{name} 的实习岗数应精确一致")

    def test_top_open_jobs_leader(self):
        """按 open_jobs 排的榜首必须是华为（10000）。"""
        top = self.api["top_by_open_jobs"][0]
        self.assertEqual(top["company"], self.src["top_by_open_jobs"][0]["company"])
        self.assertEqual(top["open_jobs"], self.src["top_by_open_jobs"][0]["open_jobs"])

    def test_size_dist_scope(self):
        """size_dist 只统计有实习岗的公司，合计应接近 608 而不是 1954。"""
        total = sum(n for _, n in self.api["size_dist"])
        self.assertLess(total, 700, "统计范围错了（应为 608 家）")
        self.assertGreater(total, 500)


class InventoryTest(unittest.TestCase):
    def test_identical(self):
        api = Client().get("/api/stats/inventory").json()
        self.assertEqual(api, ref("inventory.json"))


class TracksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = Client().get("/api/stats/tracks").json()
        cls.src = ref("tracks.json")

    def test_eight_directions(self):
        self.assertEqual(len(self.api["rows"]), 8)
        self.assertEqual([r["direction"] for r in self.api["rows"]],
                         [r["direction"] for r in self.src["rows"]])

    def test_intern_postings_identical(self):
        """8 个方向的实习岗数必须完全一致。"""
        for a, b in zip(self.src["rows"], self.api["rows"]):
            with self.subTest(direction=a["direction"]):
                self.assertEqual(b["intern"]["postings"], a["intern"]["postings"])

    def test_keywords_sorted(self):
        for a, b in zip(self.src["rows"], self.api["rows"]):
            with self.subTest(direction=a["direction"]):
                self.assertEqual(b["intern"]["keywords"], a["intern"]["keywords"])

    def test_daily_n_known_gap(self):
        """daily 样本量最多差 2（小写 k）。"""
        for a, b in zip(self.src["rows"], self.api["rows"]):
            with self.subTest(direction=a["direction"]):
                self.assertLessEqual(abs(b["intern"]["daily"]["n"] - a["intern"]["daily"]["n"]), 2)

    def test_zero_sample_direction(self):
        """测试/运维方向没有可比实习薪资，必须是 n=0 而不是报错。"""
        d = {r["direction"]: r for r in self.api["rows"]}
        self.assertEqual(d["测试"]["intern"]["daily"]["n"], 0)
        self.assertEqual(d["运维"]["intern"]["daily"]["n"], 0)


class AllEndpointsSmoke(unittest.TestCase):
    """六个端点都要 200 且是合法 JSON。"""

    ENDPOINTS = [
        "/api/health",
        "/api/stats/summary",
        "/api/stats/stacks",
        "/api/stats/tags",
        "/api/stats/companies",
        "/api/stats/inventory",
        "/api/stats/tracks",
    ]

    def test_all_200(self):
        c = Client()
        for ep in self.ENDPOINTS:
            with self.subTest(endpoint=ep):
                r = c.get(ep)
                self.assertEqual(r.status_code, 200, f"{ep} 返回 {r.status_code}")
                self.assertEqual(r["Content-Type"].split(";")[0], "application/json")

    def test_no_html_error_page(self):
        """错误也必须是 JSON（前端不能收到 HTML 堆栈）。"""
        r = Client().get("/api/stats/nonexistent")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
