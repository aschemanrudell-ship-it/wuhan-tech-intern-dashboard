# -*- coding: utf-8 -*-
"""岗位列表端点 vs 内存过滤的对拍测试。

这是整个 jobs 端点最关键的验证：同一筛选条件下，
SQL 过滤的结果必须与源数据在 Python 里按前端语义过滤的结果**逐条相同**。

对拍基准是 data/raw/jobs_master.json（3013 行原始快照），
内存实现直接照抄前端 app.js 的 applyFilters。
"""
import json
import os
import sys
import unittest
import urllib.parse

import django
from django.conf import settings

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "JobDataPlatform.settings")
if not settings.configured:
    django.setup()

from django.test import Client                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = json.load(open(os.path.join(ROOT, "data", "raw", "jobs_master.json"), encoding="utf-8"))

# 前端表格只显示实习口径（app.js: state.rows = interns）
INTERNS = [j for j in RAW if j.get("is_wuhan") and j.get("intern") and not j.get("is_edu")]


def mem_filter(source=None, stack=None, degree=None, q=None, salary_only=False):
    """照抄 app.js 的 applyFilters。"""
    out = []
    for j in INTERNS:
        if source and j.get("source") != source:
            continue
        if stack and stack not in (j.get("stacks") or []):
            continue
        if degree and j.get("degree") != degree:
            continue
        if salary_only and not j.get("day_mid"):
            continue
        if q:
            blob = f"{j.get('title') or ''} {j.get('company') or ''}".lower()
            if q.lower() not in blob:
                continue
        out.append(j)
    return out


def api_all(params, page_size=200):
    """通过分页把结果全部取回，返回 (total, items)。"""
    c = Client()
    items, page, total = [], 1, None
    while True:
        qs = dict(params, page=page, page_size=page_size)
        url = "/api/jobs?" + urllib.parse.urlencode(qs)
        d = c.get(url).json()
        if total is None:
            total = d["total"]
        items.extend(d["items"])
        if page >= d["pages"] or not d["items"]:
            break
        page += 1
    return total, items


class FilterParityTest(unittest.TestCase):
    """每种筛选组合，SQL 与内存结果集必须完全相同。"""

    CASES = [
        ("无筛选", {}),
        ("stack=Python", {"stack": "Python"}),
        ("stack=Java", {"stack": "Java"}),
        ("stack=算法/AI", {"stack": "算法/AI"}),
        ("degree=本科", {"degree": "本科"}),
        ("degree=硕士", {"degree": "硕士"}),
        ("source=BOSS直聘", {"source": "BOSS直聘"}),
        ("source=智联招聘", {"source": "智联招聘"}),
        ("q=python", {"q": "python"}),
        ("q=实习", {"q": "实习"}),
        ("q=工程师", {"q": "工程师"}),
        ("salary_only=1", {"salary_only": "1"}),
        ("stack=Python&degree=本科", {"stack": "Python", "degree": "本科"}),
        ("stack=Java&salary_only=1", {"stack": "Java", "salary_only": "1"}),
        ("stack=Python&q=算法", {"stack": "Python", "q": "算法"}),
        ("source=实Boss&degree=本科", {"source": "BOSS直聘", "degree": "本科"}),
        ("stack=不存在", {"stack": "完全不存在的方向"}),
    ]

    def test_parity(self):
        for label, params in self.CASES:
            with self.subTest(case=label):
                f = {
                    "source": params.get("source"),
                    "stack": params.get("stack"),
                    "degree": params.get("degree"),
                    "q": params.get("q"),
                    "salary_only": params.get("salary_only") == "1",
                }
                expect = mem_filter(**f)
                expect_uids = sorted(j["job_id"] for j in expect)

                total, items = api_all(params)
                got_uids = sorted(i["job_uid"] for i in items)

                self.assertEqual(total, len(expect),
                                 f"{label}: total {total} != 内存 {len(expect)}")
                self.assertEqual(len(items), len(expect),
                                 f"{label}: 取回 {len(items)} 条 != 内存 {len(expect)} 条")
                self.assertEqual(got_uids, expect_uids,
                                 f"{label}: 结果集不同（缺失 {set(expect_uids)-set(got_uids)} / "
                                 f"多出 {set(got_uids)-set(expect_uids)}）")


class PaginationTest(unittest.TestCase):
    def test_no_overlap_no_gap(self):
        """翻完所有页，得到的 uid 集合必须与全量一致，且无重复。"""
        c = Client()
        first = c.get("/api/jobs?page=1&page_size=100").json()
        total, pages = first["total"], first["pages"]
        seen, page = [], 1
        while page <= pages:
            d = c.get(f"/api/jobs?page={page}&page_size=100").json()
            seen.extend(i["job_uid"] for i in d["items"])
            page += 1
        self.assertEqual(len(seen), total, "总条数不符")
        self.assertEqual(len(set(seen)), total, "存在重复行（排序不稳定）")

    def test_out_of_range_returns_empty(self):
        c = Client()
        d = c.get("/api/jobs?page=99999&page_size=20").json()
        self.assertEqual(d["items"], [])
        self.assertEqual(d["total"], 1096, "total 不应随页码变化")

    def test_page_size_bounds(self):
        c = Client()
        self.assertEqual(c.get("/api/jobs?page_size=0").status_code, 400)
        self.assertEqual(c.get("/api/jobs?page_size=201").status_code, 400)
        self.assertEqual(c.get("/api/jobs?page_size=200").status_code, 200)


class SortTest(unittest.TestCase):
    def test_daypay_desc_monotonic(self):
        c = Client()
        d = c.get("/api/jobs?sort=daypay&order=desc&page_size=200").json()
        vals = [i["day_mid"] for i in d["items"] if i["day_mid"] is not None]
        self.assertEqual(vals, sorted(vals, reverse=True), "daypay 降序不单调")
        self.assertEqual(d["sort"], {"key": "daypay", "order": "desc"})

    def test_sort_asc(self):
        c = Client()
        d = c.get("/api/jobs?sort=daypay&order=asc&page_size=50").json()
        vals = [i["day_mid"] for i in d["items"] if i["day_mid"] is not None]
        self.assertEqual(vals, sorted(vals), "daypay 升序不单调")

    def test_null_sorted_last(self):
        """NULL 薪资必须排在最后（否则翻页时位置漂移）。"""
        c = Client()
        d = c.get("/api/jobs?sort=daypay&order=desc&page_size=200").json()
        vals = [i["day_mid"] for i in d["items"]]
        first_null = next((k for k, v in enumerate(vals) if v is None), None)
        if first_null is not None:
            self.assertTrue(all(v is None for v in vals[first_null:]),
                            "NULL 之后又出现了非 NULL")

    def test_invalid_sort_rejected(self):
        c = Client()
        r = c.get("/api/jobs?sort=day_mid;DROP TABLE jobs")
        self.assertEqual(r.status_code, 400)
        self.assertIn("sort", r.json()["detail"])


class DetailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = Client().get("/api/jobs?page_size=1").json()
        cls.uid = d["items"][0]["job_uid"]

    def test_detail_ok(self):
        d = Client().get("/api/jobs/" + urllib.parse.quote(self.uid, safe="")).json()
        self.assertEqual(d["job_uid"], self.uid)
        self.assertIn("stacks", d)
        self.assertIn("jd", d)

    def test_detail_404(self):
        r = Client().get("/api/jobs/definitely-not-a-real-uid")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"], "not_found")

    def test_relations_not_n_plus_one(self):
        """列表页 20 条的 stacks/tags 必须一次批量取，不能每行查一次。"""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        c = Client()
        with CaptureQueriesContext(connection) as ctx:
            c.get("/api/jobs?page_size=20")
        # 预期：COUNT 1 + 主查询 1 + stacks 1 + tags 1 + labels 1 = 5 左右
        self.assertLessEqual(len(ctx), 8,
                             f"查询次数 {len(ctx)} 过多，疑似 N+1")


class LikeEscapeTest(unittest.TestCase):
    def test_percent_not_wildcard(self):
        """搜 '%' 不应命中全部。"""
        c = Client()
        d = c.get("/api/jobs?q=%25")   # URL 编码的 %
        self.assertLess(d.json()["total"], 1096, "% 被当成通配符了")

    def test_normal_query_still_works(self):
        c = Client()
        d = c.get("/api/jobs?q=python").json()
        self.assertGreater(d["total"], 0)


class ResponseShapeTest(unittest.TestCase):
    def test_keys(self):
        d = Client().get("/api/jobs").json()
        for k in ("items", "total", "page", "page_size", "pages", "sort",
                  "applied_filters", "scope"):
            self.assertIn(k, d, f"缺少键 {k}")

    def test_item_fields(self):
        d = Client().get("/api/jobs?page_size=1").json()
        item = d["items"][0]
        # 前端 renderTable 需要的字段
        for k in ("job_uid", "title", "company", "degree", "salary_raw",
                  "day_mid", "stacks", "url", "is_intern"):
            self.assertIn(k, item, f"item 缺少字段 {k}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
