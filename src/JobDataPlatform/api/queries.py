"""统计查询层。

所有 SQL 集中在这里，视图只做参数校验和 JSON 包装。
口径与源项目 `summary.json` 对齐，见 docs/SUMMARY-MAPPING.md。
"""
from decimal import Decimal

from django.db import connection

# 实习口径（与源脚本 aggregate.py 的 wuhan_intern 一致）
WIDE = "j.is_wuhan=1 AND j.is_intern=1 AND j.is_edu_excluded=0"

SALARY_BUCKETS = [
    ("≤100", None, 100),
    ("100-150", 100, 150),
    ("150-200", 150, 200),
    ("200-300", 200, 300),
    (">300", 300, None),
]


def _to_float(v):
    return float(v) if isinstance(v, Decimal) else v


def rows(sql, params=None):
    """执行 SQL，返回 dict 列表。"""
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [{c: _to_float(v) for c, v in zip(cols, r)} for r in cur.fetchall()]


def scalar(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        r = cur.fetchone()
        return _to_float(r[0]) if r else None


def pct(values, p):
    """分位数：源项目用的是**索引法** vals[int(n*p)]，且**不做四舍五入**。

    早前误判为 statistics.quantiles(exclusive)。在 n=75 这类样本上两者恰好同值，
    但小样本会分叉（PHP n=1：索引法返回该值，插值法返回 None），
    且源实现不 round（会看到 184.45 这种两位小数）。
    """
    v = sorted(values)
    if not v:
        return None
    return v[min(int(len(v) * p), len(v) - 1)]


def _day_mids(stack_name=None):
    """取日薪样本。

    stack_name 为 None 时**不 JOIN** job_stacks —— 否则没有技术栈的岗位会被排除，
    all_interns 的样本量会从 504 掉到 412（已在开发中验证过这个坑）。
    """
    if stack_name:
        sql = (
            f"SELECT DISTINCT j.id, j.day_mid FROM jobs j "
            f"JOIN job_stacks js ON js.job_id=j.id JOIN stacks s ON s.id=js.stack_id "
            f"WHERE {WIDE} AND j.intern_daily_sample=1 AND s.name=%s"
        )
        rs = rows(sql, (stack_name,))
    else:
        rs = rows(f"SELECT j.id, j.day_mid FROM jobs j WHERE {WIDE} AND j.intern_daily_sample=1")
    return [float(r["day_mid"]) for r in rs]


def salary_stats(stack_name=None):
    v = sorted(_day_mids(stack_name))
    if not v:
        return {"n": 0, "min": None, "p25": None, "median": None,
                "p75": None, "max": None, "mean": None}
    return {
        "n": len(v),
        "min": v[0],
        "p25": pct(v, 0.25),
        "median": pct(v, 0.5),
        "p75": pct(v, 0.75),
        "max": v[-1],
        "mean": round(sum(v) / len(v), 1),
    }


def histogram(values):
    return [
        {"name": name,
         "count": sum(1 for v in values if (lo is None or v > lo) and (hi is None or v <= hi))}
        for name, lo, hi in SALARY_BUCKETS
    ]


def summary():
    """复现源 summary.json 的可计算部分（23 个字段）。

    6 个采集元数据字段（boss_meta / boss_coverage_note / data_notes /
    platform_inventory / boss_keywords_collected）不在这里，由 meta.py 提供。
    """
    out = {}
    out["total_rows"] = scalar("SELECT COUNT(*) FROM jobs")
    out["wuhan_rows"] = scalar("SELECT COUNT(*) FROM jobs WHERE is_wuhan=1")
    out["wuhan_interns"] = scalar(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE}")
    out["wuhan_tech_interns"] = scalar(
        f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} "
        f"AND EXISTS(SELECT 1 FROM job_stacks js WHERE js.job_id=j.id)")
    out["wuhan_nontech_interns"] = out["wuhan_interns"] - out["wuhan_tech_interns"]

    out["salary_scope"] = {
        "daily": scalar(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.salary_unit='DAY'"),
        "monthly_k": scalar(
            f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.salary_unit IN ('K_MONTH','K_MONTH_X')"),
        "no_salary": scalar(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.salary_unit='MISSING'"),
    }
    out["intern_salary_known"] = out["salary_scope"]["daily"] + out["salary_scope"]["monthly_k"]
    out["daily_sample_n"] = scalar(
        f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.intern_daily_sample=1")

    out["generated_from"] = {r["name"]: r["n"] for r in rows(
        "SELECT s.name, COUNT(*) n FROM jobs j JOIN sources s ON s.id=j.source_id GROUP BY s.name")}
    out["by_source"] = {r["name"]: r["n"] for r in rows(
        f"SELECT s.name, COUNT(*) n FROM jobs j JOIN sources s ON s.id=j.source_id "
        f"WHERE {WIDE} GROUP BY s.name")}
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
    out["salary_stats"] = {
        "python": out["python"]["salary"],
        "java": out["java"]["salary"],
        "all_interns": salary_stats(None),
        "note": "统计口径：实习岗本人报价；「元/天」直接采用，「K/月」按 21.75 个工作日折算为日薪；"
                "不含「元/月」社招口径。样本 = intern_daily_sample。",
    }
    out["both"] = scalar(
        f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} "
        f"AND EXISTS(SELECT 1 FROM job_stacks js JOIN stacks s ON s.id=js.stack_id "
        f"           WHERE js.job_id=j.id AND s.name='Python') "
        f"AND EXISTS(SELECT 1 FROM job_stacks js JOIN stacks s ON s.id=js.stack_id "
        f"           WHERE js.job_id=j.id AND s.name='Java')")

    all_vals = _day_mids(None)
    out["salary_hist_all"] = histogram(all_vals)
    out["salary_hist_by_stack"] = {
        st: histogram(_day_mids(st)) for st in ("Python", "Java", "算法/AI", "前端")
    }

    out["salary_by_source"] = {}
    for r in rows("SELECT id, name FROM sources ORDER BY id"):
        sid, name = r["id"], r["name"]
        out["salary_by_source"][name] = {
            "positions": scalar(f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.source_id=%s", (sid,)),
            "with_salary": scalar(
                f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.source_id=%s "
                f"AND j.salary_unit<>'MISSING'", (sid,)),
            "daily": scalar(
                f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.source_id=%s "
                f"AND j.salary_unit='DAY'", (sid,)),
            "monthly_k": scalar(
                f"SELECT COUNT(*) FROM jobs j WHERE {WIDE} AND j.source_id=%s "
                f"AND j.salary_unit IN ('K_MONTH','K_MONTH_X')", (sid,)),
        }

    out["company_panel"] = {
        "profiles_collected": scalar(
            "SELECT COUNT(*) FROM companies WHERE open_jobs IS NOT NULL OR boss_count IS NOT NULL"),
        "companies_hiring_interns": scalar(
            f"SELECT COUNT(DISTINCT j.company_id) FROM jobs j JOIN sources s ON s.id=j.source_id "
            f"WHERE {WIDE} AND s.code='boss'"),
        "total_open_jobs": scalar(
            f"SELECT COALESCE(SUM(c.open_jobs),0) FROM companies c WHERE c.id IN "
            f"(SELECT DISTINCT j.company_id FROM jobs j JOIN sources s ON s.id=j.source_id "
            f" WHERE {WIDE} AND s.code='boss' AND j.company_id IS NOT NULL)"),
    }

    out["top_tags"] = [[r["name"], r["n"]] for r in rows(
        f"SELECT t.name, COUNT(*) n FROM jobs j JOIN job_tags jt ON jt.job_id=j.id "
        f"JOIN tags t ON t.id=jt.tag_id WHERE {WIDE} GROUP BY t.name ORDER BY n DESC LIMIT 30")]
    out["top_skills"] = out["top_tags"]
    out["top_companies"] = [[r["name"], r["n"]] for r in rows(
        f"SELECT c.name, COUNT(*) n FROM jobs j JOIN companies c ON c.id=j.company_id "
        f"WHERE {WIDE} GROUP BY c.name ORDER BY n DESC LIMIT 15")]
    out["top_industries"] = [[r["industry"], r["n"]] for r in rows(
        f"SELECT j.industry, COUNT(*) n FROM jobs j WHERE {WIDE} AND j.industry IS NOT NULL "
        f"GROUP BY j.industry ORDER BY n DESC LIMIT 12")]
    return out


def health():
    """健康检查：数据库可达 + 关键表行数。"""
    return {
        "database": scalar("SELECT DATABASE()"),
        "jobs": scalar("SELECT COUNT(*) FROM jobs"),
        "companies": scalar("SELECT COUNT(*) FROM companies"),
        "job_stacks": scalar("SELECT COUNT(*) FROM job_stacks"),
        "job_descriptions": scalar("SELECT COUNT(*) FROM job_descriptions"),
        "mysql_version": scalar("SELECT VERSION()"),
    }
