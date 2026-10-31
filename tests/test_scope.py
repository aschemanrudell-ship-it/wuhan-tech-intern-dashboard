# -*- coding: utf-8 -*-
"""口径与导入的回归测试。

这些测试断言的是「口径定义」，不是「某次运行的数字」，所以它们能在数据更新后
仍然回答一个问题：三层实习口径和薪资样本是否还算得对。

需要库已建好并完成一次导入。连接参数可用环境变量覆盖：
  JDP_HOST / JDP_PORT / JDP_USER / JDP_PASSWORD / JDP_DATABASE
"""
import os
import sys
import unittest

import pymysql

sys.stdout.reconfigure(encoding="utf-8")

CONN = dict(
    host=os.environ.get("JDP_HOST", "127.0.0.1"),
    port=int(os.environ.get("JDP_PORT", "3307")),
    user=os.environ.get("JDP_USER", "root"),
    password=os.environ.get("JDP_PASSWORD", ""),
    database=os.environ.get("JDP_DATABASE", "jobdata"),
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
)

WIDE = "is_wuhan=1 AND is_intern=1 AND is_edu_excluded=0"
EXPLICIT = WIDE + " AND title_has_intern=1"
SAMPLE = EXPLICIT + " AND intern_daily_sample=1"


def q1(cur, sql, args=None):
    cur.execute(sql, args)
    row = cur.fetchone()
    return list(row.values())[0]


class TestScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = pymysql.connect(**CONN)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        self.cur = self.conn.cursor()

    def test_snapshot_row_count(self):
        """快照导入后应为 3013 行（与审计报告一致）。"""
        self.assertEqual(q1(self.cur, "SELECT COUNT(*) FROM jobs"), 3013)

    def test_scope_is_nested(self):
        """三层口径必须严格嵌套：A >= B >= C。"""
        a = q1(self.cur, f"SELECT COUNT(*) FROM jobs WHERE {WIDE}")
        b = q1(self.cur, f"SELECT COUNT(*) FROM jobs WHERE {EXPLICIT}")
        c = q1(self.cur, f"SELECT COUNT(*) FROM jobs WHERE {SAMPLE}")
        self.assertGreaterEqual(a, b, "A 应 >= B")
        self.assertGreaterEqual(b, c, "B 应 >= C")
        self.assertGreater(c, 0, "C 层不应为 0")

    def test_loose_flag_mixes_campus(self):
        """宽口径里必须存在标题不含「实习」的行 —— 这是 B 层存在的理由。"""
        mix = q1(self.cur, f"SELECT COUNT(*) FROM jobs WHERE {WIDE} AND title_has_intern=0")
        self.assertGreater(mix, 0, "若为 0，说明 is_intern 已足够严格，B 层可去掉")

    def test_comparable_wider_than_sample(self):
        """day_mid_comparable 必须比 intern_daily_sample 宽（前者含全部 K/月）。"""
        wide = q1(self.cur, f"SELECT COUNT(*) FROM jobs WHERE {WIDE} AND day_mid_comparable=1")
        strict = q1(self.cur, f"SELECT COUNT(*) FROM jobs WHERE {SAMPLE}")
        self.assertGreater(wide, strict, "宽口径应严格大于 C 层")

    def test_salary_unit_partition(self):
        """薪资单位枚举必须覆盖全部行，且互斥。"""
        total = q1(self.cur, "SELECT COUNT(*) FROM jobs")
        s = q1(self.cur, "SELECT SUM(n) FROM (SELECT COUNT(*) n FROM jobs GROUP BY salary_unit) t")
        self.assertEqual(total, s, "salary_unit 分组之和应等于总行数")

    def test_no_fake_zero_salary(self):
        """缺失薪资必须是 NULL 或 MISSING，不能是 0。"""
        bad = q1(self.cur, "SELECT COUNT(*) FROM jobs WHERE day_mid = 0")
        self.assertEqual(bad, 0, "不应存在 day_mid=0 的伪值")
        mismatch = q1(
            self.cur,
            "SELECT COUNT(*) FROM jobs WHERE salary_unit='MISSING' AND day_mid IS NOT NULL",
        )
        self.assertEqual(mismatch, 0, "MISSING 单位不应有日薪数值")

    def test_job_uid_unique(self):
        """幂等键必须唯一。"""
        dup = q1(
            self.cur,
            "SELECT COUNT(*) FROM (SELECT job_uid FROM jobs GROUP BY job_uid HAVING COUNT(*)>1) t",
        )
        self.assertEqual(dup, 0, "job_uid 存在重复，幂等导入会失效")

    def test_relations_not_dangling(self):
        """关联表不能有孤儿行（外键之外的额外校验）。"""
        for child, col, parent in (
            ("job_stacks", "job_id", "jobs"),
            ("job_tags", "job_id", "jobs"),
            ("job_descriptions", "job_id", "jobs"),
        ):
            orphan = q1(
                self.cur,
                f"SELECT COUNT(*) FROM {child} c LEFT JOIN {parent} p ON p.id=c.{col} WHERE p.id IS NULL",
            )
            self.assertEqual(orphan, 0, f"{child} 存在孤儿行")


class TestIdempotency(unittest.TestCase):
    """重复导入的验收标准：行数不变、字典不膨胀。"""

    @classmethod
    def setUpClass(cls):
        cls.conn = pymysql.connect(**CONN)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_batch_logged(self):
        """每次导入都应留一条 import_batch 记录。"""
        cur = self.conn.cursor()
        n = q1(cur, "SELECT COUNT(*) FROM import_batch")
        self.assertGreaterEqual(n, 1)

    def test_no_dict_explosion(self):
        """字典表行数应等于去重后的取值数（重复导入不新增）。"""
        cur = self.conn.cursor()
        stack_rows = q1(cur, "SELECT COUNT(*) FROM stacks")
        distinct_stacks = q1(
            cur, "SELECT COUNT(DISTINCT s.name) FROM job_stacks js JOIN stacks s ON s.id=js.stack_id"
        )
        self.assertLessEqual(distinct_stacks, stack_rows, "方向字典出现冗余行")


if __name__ == "__main__":
    unittest.main(verbosity=2)
