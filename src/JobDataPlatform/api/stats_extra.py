"""其余 5 个 stats 端点的查询层。

与 queries.py 的分工：
  queries.py   —— /api/health、/api/stats/summary
  stats_extra  —— /api/stats/stacks、/tags、/companies、/inventory、/tracks

⚠️ 两套分位数算法，不能混用：
  * summary / stack_stats 系列 → statistics.quantiles(exclusive)，即位置 (n+1)*p
  * tracks 的 daily/month      → 源脚本的索引法 vals[int(n*p)]，且 month 四舍五入到整数
混用会导致数字对不上（p75 差 2.5）。
"""
import json
import os
import re
from statistics import median as _median

from django.conf import settings
from django.db import connection

WIDE = "j.is_wuhan=1 AND j.is_intern=1 AND j.is_edu_excluded=0"
DAYS_PER_MONTH = 21.75

# 技能标签噪声（与源项目 aggregate.py 的 NOISE_SKILL_RE 保持一致）
NOISE_SKILL_RE = re.compile(
    r"经验|办公|坐班|班制|福利|社保|月结|周结|津贴|补贴|补助|奖金|双休|大小周|做六休|长白班|不加班|"
    r"毕业|学历|本科|硕士|大专|博士|专业|在读|应届|年级|届|居家|远程|出差|地推|销售|客服|"
    r"普通话|英语|身高|形象|包吃|包住|五险|房补|餐补|交通|团建|下午茶|晋升|培训|带教|提供|接受"
)

# 成长曲线的方向 → 采集 slug 映射（硬编码，来自源项目 aggregate.py 的 DIRECTIONS）
TRACK_DIRECTIONS = [
    ("Python", ["boss_wuhan_python", "boss_wuhan_python_dev", "boss_wuhan_backend"], "ft_python"),
    ("Java", ["boss_wuhan_java", "boss_wuhan_java_dev", "boss_wuhan_backend"], "ft_java"),
    ("前端", ["boss_wuhan_front", "boss_wuhan_web"], "ft_front"),
    ("算法/AI", ["boss_wuhan_algo", "boss_wuhan_ai"], "ft_algo"),
    ("测试", ["boss_wuhan_test"], "ft_test"),
    ("数据分析", ["boss_wuhan_data"], "ft_data"),
    ("后端", ["boss_wuhan_backend"], "ft_backend"),
    ("运维", ["boss_wuhan_ops"], "ft_ops"),
]

FULLTIME_KEYWORDS_MAP = {
    "ft_python": "Python开发",
    "ft_java": "Java开发",
    "ft_front": "前端开发",
    "ft_backend": "后端开发",
    "ft_algo": "算法工程师",
    "ft_data": "数据分析师",
    "ft_test": "测试工程师",
    "ft_ops": "运维工程师",
}


# ------------------------------------------------------------------ 基础工具
def _f(v):
    from decimal import Decimal
    return float(v) if isinstance(v, Decimal) else v


def rows(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [{c: _f(v) for c, v in zip(cols, r)} for r in cur.fetchall()]


def scalar(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        r = cur.fetchone()
        return _f(r[0]) if r else None


def pct_exclusive(v, p):
    """statistics.quantiles 的 exclusive 法：位置 = (n+1)*p。"""
    v = sorted(v)
    n = len(v)
    if n < 2:
        return None
    k = (n + 1) * p
    if k < 1:
        return v[0]
    if k > n:
        return v[-1]
    lo = int(k)
    frac = k - lo
    return v[lo - 1] if frac == 0 else v[lo - 1] + (v[lo] - v[lo - 1]) * frac


def pct_index(v, p):
    """源脚本 daily_stats/month_stats 用的索引法：vals[int(n*p)]。"""
    v = sorted(v)
    if not v:
        return None
    i = int(len(v) * p)
    return v[min(i, len(v) - 1)]


def pct_index(v, p):
    """源脚本用的索引法：vals[int(n*p)]。

    这是**源项目实际使用的算法**（daily_stats / month_stats / stack_stats.salary_day）。
    注意 n=1 时 int(1*0.25)=0，仍返回该值，不会像插值法那样返回 None。
    """
    v = sorted(v)
    if not v:
        return None
    i = int(len(v) * p)
    return v[min(i, len(v) - 1)]


def salary_day_full(v):
    """{n,min,p25,median,p75,max,mean}，复现源 salary_summary。

    源实现里 min/p25/median/p75/max **都不做四舍五入**（只有 mean round 到 1 位），
    所以会看到 184.45 这种两位小数。加 round 会让数字对不上。
    """
    v = sorted(float(x) for x in v)
    if not v:
        return {"n": 0}
    n = len(v)
    return {
        "n": n,
        "min": v[0],
        "p25": v[int(n * 0.25)],
        "median": _median(v),
        "p75": v[int(n * 0.75)],
        "max": v[-1],
        "mean": round(sum(v) / n, 1),
    }


def daily_stats_exclusive(stack=None):
    """日薪统计（索引法分位）—— 服务 stack_stats / summary。"""
    if stack:
        rs = rows(f"SELECT DISTINCT j.id, j.day_mid FROM jobs j "
                  f"JOIN job_stacks js ON js.job_id=j.id JOIN stacks s ON s.id=js.stack_id "
                  f"WHERE {WIDE} AND j.intern_daily_sample=1 AND s.name=%s", (stack,))
    else:
        rs = rows(f"SELECT j.id, j.day_mid FROM jobs j WHERE {WIDE} AND j.intern_daily_sample=1")
    return salary_day_full([r["day_mid"] for r in rs])


# ------------------------------------------------------------------ stacks
def stack_stats():
    """15 个方向 × {count, by_source, salary_day, salary_month, degree, districts, top_companies}"""
    out = {}
    for r in rows("SELECT name FROM stacks ORDER BY name"):
        stack = r["name"]
        base = (f"FROM jobs j JOIN job_stacks js ON js.job_id=j.id "
                f"JOIN stacks s ON s.id=js.stack_id WHERE {WIDE} AND s.name=%s")
        count = scalar(f"SELECT COUNT(DISTINCT j.id) {base}", (stack,))
        by_source = {x["name"]: x["n"] for x in rows(
            f"SELECT src.name, COUNT(DISTINCT j.id) n FROM jobs j "
            f"JOIN job_stacks js ON js.job_id=j.id JOIN stacks s ON s.id=js.stack_id "
            f"JOIN sources src ON src.id=j.source_id WHERE {WIDE} AND s.name=%s "
            f"GROUP BY src.name", (stack,))}
        month_vals = [float(x["m"]) for x in rows(
            f"SELECT j.month_mid m FROM jobs j JOIN job_stacks js ON js.job_id=j.id "
            f"JOIN stacks s ON s.id=js.stack_id WHERE {WIDE} AND s.name=%s "
            f"AND j.month_mid IS NOT NULL", (stack,))]
        degree = {x["degree"]: x["n"] for x in rows(
            f"SELECT j.degree, COUNT(DISTINCT j.id) n FROM jobs j "
            f"JOIN job_stacks js ON js.job_id=j.id JOIN stacks s ON s.id=js.stack_id "
            f"WHERE {WIDE} AND s.name=%s GROUP BY j.degree ORDER BY n DESC", (stack,))}
        districts = {x["district"]: x["n"] for x in rows(
            f"SELECT j.district, COUNT(DISTINCT j.id) n, MIN(j.id) first_id FROM jobs j "
            f"JOIN job_stacks js ON js.job_id=j.id JOIN stacks s ON s.id=js.stack_id "
            f"WHERE {WIDE} AND s.name=%s AND j.district IS NOT NULL "
            f"GROUP BY j.district ORDER BY n DESC, first_id ASC LIMIT 8", (stack,))}
        top_companies = [[x["name"], x["n"]] for x in rows(
            f"SELECT c.name, COUNT(DISTINCT j.id) n, MIN(j.id) first_id FROM jobs j "
            f"JOIN job_stacks js ON js.job_id=j.id JOIN stacks s ON s.id=js.stack_id "
            f"JOIN companies c ON c.id=j.company_id "
            f"WHERE {WIDE} AND s.name=%s GROUP BY c.name "
            f"ORDER BY n DESC, first_id ASC LIMIT 8", (stack,))]
        out[stack] = {
            "count": count,
            "by_source": by_source,
            "salary_day": daily_stats_exclusive(stack),
            "salary_month": {"median": round(_median(month_vals), 1) if month_vals else None},
            "degree": degree,
            "districts": districts,
            "top_companies": top_companies,
        }
    return out


# ------------------------------------------------------------------ tags
def tags_stats():
    """tags（原始频次）/ skills（过滤噪声）/ companies / industries

    排序必须带次级键：源用 Counter.most_common()，同分时按**首次出现顺序**；
    只用 ORDER BY n DESC 会让同分项顺序随机，产生大量假差异。
    """
    raw_tags = [[r["name"], r["n"]] for r in rows(
        f"SELECT t.name, COUNT(*) n, MIN(j.id) fid FROM jobs j JOIN job_tags jt ON jt.job_id=j.id "
        f"JOIN tags t ON t.id=jt.tag_id WHERE {WIDE} GROUP BY t.name "
        f"ORDER BY n DESC, fid ASC LIMIT 40")]
    skill_rows = rows(
        f"SELECT t.name, COUNT(*) n, MIN(j.id) fid FROM jobs j JOIN job_tags jt ON jt.job_id=j.id "
        f"JOIN tags t ON t.id=jt.tag_id JOIN sources s ON s.id=j.source_id "
        f"WHERE {WIDE} AND s.code='boss' GROUP BY t.name ORDER BY n DESC, fid ASC")
    skills = [[r["name"], r["n"]] for r in skill_rows
              if r["name"] and not NOISE_SKILL_RE.search(r["name"]) and len(r["name"]) <= 16][:40]
    companies = [[r["name"], r["n"]] for r in rows(
        f"SELECT c.name, COUNT(*) n, MIN(j.id) fid FROM jobs j JOIN companies c ON c.id=j.company_id "
        f"WHERE {WIDE} GROUP BY c.name ORDER BY n DESC, fid ASC LIMIT 20")]
    industries = [[r["industry"], r["n"]] for r in rows(
        f"SELECT j.industry, COUNT(*) n, MIN(j.id) fid FROM jobs j "
        f"WHERE {WIDE} AND j.industry IS NOT NULL GROUP BY j.industry "
        f"ORDER BY n DESC, fid ASC LIMIT 15")]
    return {"tags": raw_tags, "skills": skills, "companies": companies, "industries": industries}


# ------------------------------------------------------------------ companies
def companies_panel():
    """企业端画像：汇总 + 两种 Top15 + 三个分布

    排序要复现源逻辑：
      top_by_intern_roles → sorted(key=(-intern_roles, -open_jobs))
      top_by_open_jobs    → sorted(key=(-open_jobs,))
    只用一个排序键会让同分公司的顺序与源不同。
    """
    def company_rows(order_by, limit=15):
        return rows(
            f"SELECT c.name AS company, c.open_jobs, c.boss_count AS bosses, c.size, "
            f"       c.financing AS stage, c.industry, COUNT(j.id) AS intern_roles "
            f"FROM companies c JOIN jobs j ON j.company_id=c.id "
            f"WHERE {WIDE} GROUP BY c.id ORDER BY {order_by} LIMIT {limit}")

    def fill_titles(items):
        """补该公司前 3 个实习岗标题 + 一个岗位链接。"""
        for it in items:
            t = rows(
                f"SELECT j.title, j.url FROM jobs j JOIN companies c ON c.id=j.company_id "
                f"WHERE {WIDE} AND c.name=%s ORDER BY j.id LIMIT 3", (it["company"],))
            it["intern_titles"] = [x["title"] for x in t]
            it["url"] = t[0]["url"] if t else None
        return items

    top_intern = fill_titles(company_rows("intern_roles DESC, c.open_jobs DESC"))
    top_open = fill_titles(company_rows("c.open_jobs DESC, intern_roles DESC"))

    # 注意：源项目的 size/stage/industry 分布只统计**有实习岗的公司**（608 家），
    # 不是 companies 表全部 1954 家 —— 范围不同会得出完全不同的分布。
    hire_ids = (f"SELECT DISTINCT j.company_id FROM jobs j JOIN sources s ON s.id=j.source_id "
                f"WHERE {WIDE} AND s.code='boss' AND j.company_id IS NOT NULL")
    size_dist = [[r["size"], r["n"]] for r in rows(
        f"SELECT c.size, COUNT(*) n FROM companies c WHERE c.size IS NOT NULL "
        f"AND c.id IN ({hire_ids}) GROUP BY c.size ORDER BY n DESC")]
    stage_dist = [[r["financing"], r["n"]] for r in rows(
        f"SELECT c.financing, COUNT(*) n FROM companies c WHERE c.financing IS NOT NULL "
        f"AND c.id IN ({hire_ids}) GROUP BY c.financing ORDER BY n DESC")]
    industry_dist = [[r["industry"], r["n"]] for r in rows(
        f"SELECT c.industry, COUNT(*) n FROM companies c WHERE c.industry IS NOT NULL "
        f"AND c.id IN ({hire_ids}) GROUP BY c.industry ORDER BY n DESC LIMIT 10")]

    return {
        "profiles_collected": scalar(
            "SELECT COUNT(*) FROM companies WHERE open_jobs IS NOT NULL OR boss_count IS NOT NULL"),
        "companies_hiring_interns": scalar(
            f"SELECT COUNT(DISTINCT j.company_id) FROM jobs j JOIN sources s ON s.id=j.source_id "
            f"WHERE {WIDE} AND s.code='boss'"),
        "total_open_jobs": scalar(
            f"SELECT COALESCE(SUM(c.open_jobs),0) FROM companies c WHERE c.id IN "
            f"(SELECT DISTINCT j.company_id FROM jobs j JOIN sources s ON s.id=j.source_id "
            f" WHERE {WIDE} AND s.code='boss' AND j.company_id IS NOT NULL)"),
        "top_by_intern_roles": top_intern,
        "top_by_open_jobs": top_open,
        "size_dist": size_dist,
        "stage_dist": stage_dist,
        "industry_dist": industry_dist,
    }


# ------------------------------------------------------------------ inventory
def inventory():
    """平台库存量。

    这是**采集时平台自报的 resCount/positionCount**，不能从 jobs 表算出来
    （库里只有我们抓到的行，没有平台总量），所以读 fixture。
    """
    path = os.path.join(settings.BASE_DIR, "fixtures", "inventory.json")
    if not os.path.exists(path):
        return {"generated_from": None, "note": "fixture 缺失：请运行 scripts/build_meta_fixture.py",
                "rows": []}
    return json.load(open(path, encoding="utf-8"))


# ------------------------------------------------------------------ tracks
def _month_mid_of(row):
    """源脚本 _month_mid：优先 month_mid，否则 day_mid × 21.75。"""
    if row.get("month_mid"):
        return row["month_mid"]
    if row.get("day_mid"):
        return round(row["day_mid"] * DAYS_PER_MONTH, 1)
    return None


def _daily_stats_tracks(rs):
    """源 daily_stats：_salary_in_scope 过滤 + 索引法分位 + round 1 位。"""
    v = sorted(float(r["day_mid"]) for r in rs if r.get("day_mid") and r.get("in_sample"))
    if not v:
        return {"n": 0}
    return {"n": len(v), "p25": round(pct_index(v, 0.25), 1),
            "median": round(_median(v), 1), "p75": round(pct_index(v, 0.75), 1),
            "max": round(v[-1], 1)}


def _month_stats_tracks(rs):
    """源 month_stats：_month_mid 非空即可（不筛口径）+ 索引法 + round 整数。"""
    v = sorted(x for x in (_month_mid_of(r) for r in rs) if x)
    if not v:
        return {"n": 0}
    return {"n": len(v), "p25": round(pct_index(v, 0.25)),
            "median": round(_median(v)), "p75": round(pct_index(v, 0.75)),
            "max": round(v[-1])}


def tracks():
    """8 个方向的「实习入口 → 正式岗」成长对比。"""
    out = {"note": (
        "实习=本次抓到的实习岗（可比薪资样本）；正式工=BOSS直聘武汉同方向社招/校招岗位"
        "（ft_* 关键词，含经验轴抽样）。月薪口径：正式工取 K/月 中位；"
        "实习按日薪×21.75 折算，用于观察「实习入口 → 正式岗」的成长空间。"), "rows": []}

    for label, intern_slugs, ft_slug in TRACK_DIRECTIONS:
        ph = ",".join(["%s"] * len(intern_slugs))
        intern_rows = rows(
            f"SELECT j.id, j.day_mid, j.month_mid, j.intern_daily_sample AS in_sample "
            f"FROM jobs j WHERE {WIDE} AND j.crawl_slug IN ({ph})", tuple(intern_slugs))
        # 源用 wuhan_all（**不排除 is_edu**）筛正式岗，加 is_edu_excluded 会少算几个
        ft_rows = rows(
            f"SELECT j.id, j.day_mid, j.month_mid, j.experience "
            f"FROM jobs j WHERE j.is_wuhan=1 AND j.is_intern=0 AND j.crawl_slug=%s", (ft_slug,))

        exp = {}
        for r in ft_rows:
            e = r["experience"] or "未标注"
            exp[e] = exp.get(e, 0) + 1

        out["rows"].append({
            "direction": label,
            "intern": {
                "postings": len(intern_rows),
                "daily": _daily_stats_tracks(intern_rows),
                "month": _month_stats_tracks(intern_rows),
                "keywords": sorted(intern_slugs),
            },
            "fulltime": {
                "postings": len(ft_rows),
                "month": _month_stats_tracks(ft_rows),
                "by_experience": dict(sorted(exp.items(), key=lambda kv: -kv[1])),
                "keywords": [FULLTIME_KEYWORDS_MAP.get(ft_slug, ft_slug)],
            },
        })
    return out
