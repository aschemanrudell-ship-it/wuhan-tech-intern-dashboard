# -*- coding: utf-8 -*-
"""把源 summary.json 的每个字段映射成 SQL，并逐字段比对。

用途：在写 Django 视图之前，先用纯 SQL 把口径钉死；比对结果作为
      docs/SUMMARY-MAPPING.md 的证据来源。

运行：python scripts/compare_to_source.py
"""
import json
import os
import statistics
import sys
from decimal import Decimal

import pymysql

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open(os.path.join(ROOT, "data", "raw", "summary.json"), encoding="utf-8"))

conn = pymysql.connect(host="127.0.0.1", port=3307, user="root", database="jobdata",
                       charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()

# 实习口径（与源脚本 aggregate.py 的 wuhan_intern 一致）
WIDE = "j.is_wuhan=1 AND j.is_intern=1 AND j.is_edu_excluded=0"


def one(sql, args=None):
    cur.execute(sql, args)
    r = cur.fetchone()
    if not r:
        return None
    v = list(r.values())[0]
    return float(v) if isinstance(v, Decimal) else v


def rows(sql, args=None):
    cur.execute(sql, args)
    return cur.fetchall()


def pct(values, p):
    """复现源项目用的分位数算法：statistics.quantiles 的 exclusive 方法。"""
    v = sorted(values)
    if len(v) < 2:
        return None
    return statistics.quantiles(v, n=4)[{0.25: 0, 0.5: 1, 0.75: 2}[p]]


def salary_stats(stack_name=None):
    """某方向的日薪统计（源口径：intern_daily_sample）。

    注意：stack_name 为 None 时**不能** JOIN job_stacks —— 否则没有技术栈的
    岗位会被排除，all_interns 的样本量会从 504 掉到 412。
    """
    if stack_name:
        sql = (f"SELECT DISTINCT j.id, j.day_mid FROM jobs j "
               f"JOIN job_stacks js ON js.job_id=j.id JOIN stacks s ON s.id=js.stack_id "
               f"WHERE {WIDE} AND j.intern_daily_sample=1 AND s.name=%s")
        args = (stack_name,)
    else:
        sql = (f"SELECT j.id, j.day_mid FROM jobs j "
               f"WHERE {WIDE} AND j.intern_daily_sample=1")
        args = None
    cur.execute(sql, args)
    vals = [float(r["day_mid"]) for r in cur.fetchall()]
    if not vals:
        return {"n": 0}
    v = sorted(vals)
    return {
        "n": len(v), "min": v[0], "p25": pct(v, 0.25), "median": pct(v, 0.5),
        "p75": pct(v, 0.75), "max": v[-1], "mean": round(sum(v) / len(v), 1),
    }


out = {}
out["total_rows"] = one("SELECT COUNT(*) FROM jobs")
out["wuhan_rows"] = one("SELECT COUNT(*) FROM jobs WHERE is_wuhan=1")
out["wuhan_interns"] = one(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE}")
out["wuhan_tech_interns"] = one(
    f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND EXISTS(SELECT 1 FROM job_stacks js WHERE js.job_id=j.id)")
out["wuhan_nontech_interns"] = out["wuhan_interns"] - out["wuhan_tech_interns"]

out["salary_scope"] = {
    "daily": one(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.salary_unit='DAY'"),
    "monthly_k": one(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.salary_unit IN ('K_MONTH','K_MONTH_X')"),
    "no_salary": one(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.salary_unit='MISSING'"),
}
out["intern_salary_known"] = out["salary_scope"]["daily"] + out["salary_scope"]["monthly_k"]
out["daily_sample_n"] = one(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.intern_daily_sample=1")

out["by_source"] = {r["name"]: r["n"] for r in rows(
    f"SELECT s.name, COUNT(*) n FROM jobs j JOIN sources s ON s.id=j.source_id WHERE {WIDE} GROUP BY s.name")}
out["generated_from"] = {r["name"]: r["n"] for r in rows(
    "SELECT s.name, COUNT(*) n FROM jobs j JOIN sources s ON s.id=j.source_id GROUP BY s.name")}
out["by_degree"] = {r["degree"]: r["n"] for r in rows(
    f"SELECT j.degree, COUNT(*) n FROM jobs j WHERE {WIDE} GROUP BY j.degree ORDER BY n DESC")}
out["stack_counts"] = {r["name"]: r["n"] for r in rows(
    f"SELECT s.name, COUNT(*) n FROM jobs j JOIN job_stacks js ON js.job_id=j.id "
    f"JOIN stacks s ON s.id=js.stack_id WHERE {WIDE} GROUP BY s.name ORDER BY n DESC")}
out["districts"] = {r["district"]: r["n"] for r in rows(
    f"SELECT j.district, COUNT(*) n FROM jobs j WHERE {WIDE} AND j.district IS NOT NULL "
    f"GROUP BY j.district ORDER BY n DESC LIMIT 12")}

out["python"] = {"count": out["stack_counts"].get("Python"), "salary": salary_stats("Python")}
out["java"] = {"count": out["stack_counts"].get("Java"), "salary": salary_stats("Java")}
out["salary_stats"] = {"python": out["python"]["salary"], "java": out["java"]["salary"],
                       "all_interns": salary_stats(None)}
out["both"] = one(
    f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} "
    f"AND EXISTS(SELECT 1 FROM job_stacks js JOIN stacks s ON s.id=js.stack_id WHERE js.job_id=j.id AND s.name='Python') "
    f"AND EXISTS(SELECT 1 FROM job_stacks js JOIN stacks s ON s.id=js.stack_id WHERE js.job_id=j.id AND s.name='Java')")

BUCKETS = [("≤100", None, 100), ("100-150", 100, 150), ("150-200", 150, 200),
           ("200-300", 200, 300), (">300", 300, None)]
cur.execute(f"SELECT j.day_mid FROM jobs j WHERE {WIDE} AND j.intern_daily_sample=1")
all_vals = [float(r["day_mid"]) for r in cur.fetchall()]
out["salary_hist_all"] = [
    {"name": name, "count": sum(1 for v in all_vals if (lo is None or v > lo) and (hi is None or v <= hi))}
    for name, lo, hi in BUCKETS]

hist_by_stack = {}
for st in ["Python", "Java", "算法/AI", "前端"]:
    cur.execute(
        f"SELECT DISTINCT j.id, j.day_mid FROM jobs j "
        f"JOIN job_stacks js ON js.job_id=j.id JOIN stacks s ON s.id=js.stack_id "
        f"WHERE {WIDE} AND j.intern_daily_sample=1 AND s.name=%s", (st,))
    vals = [float(r["day_mid"]) for r in cur.fetchall()]
    hist_by_stack[st] = [
        {"name": name, "count": sum(1 for v in vals if (lo is None or v > lo) and (hi is None or v <= hi))}
        for name, lo, hi in BUCKETS
    ]
out["salary_hist_by_stack"] = hist_by_stack

out["salary_by_source"] = {}
for r in rows("SELECT id, name FROM sources ORDER BY id"):
    sid, name = r["id"], r["name"]
    out["salary_by_source"][name] = {
        "positions": one(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.source_id=%s", (sid,)),
        "with_salary": one(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.source_id=%s "
                           f"AND j.salary_unit<>'MISSING'", (sid,)),
        "daily": one(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.source_id=%s "
                     f"AND j.salary_unit='DAY'", (sid,)),
        "monthly_k": one(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.source_id=%s "
                         f"AND j.salary_unit IN ('K_MONTH','K_MONTH_X')", (sid,)),
    }

out["company_panel"] = {
    "profiles_collected": one(
        "SELECT COUNT(*) FROM companies WHERE open_jobs IS NOT NULL OR boss_count IS NOT NULL"),
    "companies_hiring_interns": one(
        f"SELECT COUNT(DISTINCT j.company_id) FROM jobs j JOIN sources s ON s.id=j.source_id "
        f"WHERE {WIDE} AND s.code='boss'"),
    "total_open_jobs": one(
        f"SELECT COALESCE(SUM(c.open_jobs),0) FROM companies c WHERE c.id IN "
        f"(SELECT DISTINCT j.company_id FROM jobs j JOIN sources s ON s.id=j.source_id "
        f" WHERE {WIDE} AND s.code='boss' AND j.company_id IS NOT NULL)"),
}

out["top_tags"] = [[r["name"], r["n"]] for r in rows(
    f"SELECT t.name, COUNT(*) n FROM jobs j JOIN job_tags jt ON jt.job_id=j.id "
    f"JOIN tags t ON t.id=jt.tag_id WHERE {WIDE} GROUP BY t.name ORDER BY n DESC LIMIT 30")]
out["top_companies"] = [[r["name"], r["n"]] for r in rows(
    f"SELECT c.name, COUNT(*) n FROM jobs j JOIN companies c ON c.id=j.company_id "
    f"WHERE {WIDE} GROUP BY c.name ORDER BY n DESC LIMIT 15")]
out["top_industries"] = [[r["industry"], r["n"]] for r in rows(
    f"SELECT j.industry, COUNT(*) n FROM jobs j WHERE {WIDE} AND j.industry IS NOT NULL "
    f"GROUP BY j.industry ORDER BY n DESC LIMIT 12")]

# ---------------------------------------------------------------- 比对
print("== 逐字段比对（本库 vs 源 summary.json）==\n")
print(f"{'字段':26s}{'源':>12s}{'本库':>12s}  结果")
for k in ["total_rows", "wuhan_rows", "wuhan_interns", "wuhan_tech_interns",
          "wuhan_nontech_interns", "intern_salary_known", "daily_sample_n", "both"]:
    src_v = S["salary_stats"]["all_interns"]["n"] if k == "daily_sample_n" else S.get(k)
    got = out[k]
    print(f"{k:26s}{str(src_v):>12s}{str(got):>12s}  {'OK' if src_v == got else '差异'}")

print()
for k in ["salary_scope", "by_source", "by_degree", "stack_counts", "generated_from",
          "districts", "company_panel", "salary_hist_all", "salary_by_source"]:
    src_v, got = S.get(k), out[k]
    if src_v == got:
        print(f"{k:26s}  OK 完全一致")
        continue
    print(f"{k:26s}  差异")
    if isinstance(src_v, dict) and isinstance(got, dict):
        for kk in sorted(set(src_v) | set(got), key=str):
            if src_v.get(kk) != got.get(kk):
                print(f"      {kk}: 源={src_v.get(kk)} 本库={got.get(kk)}")
    elif isinstance(src_v, list) and isinstance(got, list):
        for a, b in zip(src_v, got):
            if a != b:
                print(f"      {a} vs {b}")

print()
for sub in ["python", "java", "all_interns"]:
    a, b = S["salary_stats"].get(sub), out["salary_stats"].get(sub)
    print(f"salary_stats.{sub}: {'OK 完全一致' if a == b else '差异'}")
    if a != b:
        print(f"      源  ={a}")
        print(f"      本库={b}")

for k in ("python", "java"):
    same = S[k]["count"] == out[k]["count"]
    print(f"{k}.count: 源={S[k]['count']} 本库={out[k]['count']} {'OK' if same else '差异'}")

os.makedirs(os.path.join(ROOT, "work"), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, "work", "reproduced.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1, default=str)
print("\n-> work/reproduced.json")
conn.close()
