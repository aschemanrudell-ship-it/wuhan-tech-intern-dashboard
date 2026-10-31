"""岗位列表与详情端点。

设计目标：把前端 `app.js` 里的内存筛选/排序搬到 SQL，且结果必须逐条对得上
（tests/test_api_jobs.py 用内存实现做对拍）。

前端语义（app.js applyFilters / sortedRows）：
  filters: source 精确、stack 数组成员、degree 精确、q 对 title+company 做小写包含、
           salaryOnly = day_mid 非空
  sort:    salary→month_mid、daypay→day_mid、stacks→join(','), degree→自定义顺序、
           其余字段字符串比较
  rows:    state.rows = interns（只含实习口径 1096 行）
"""
import json
import os

from django.db import connection

WIDE = "j.is_wuhan=1 AND j.is_intern=1 AND j.is_edu_excluded=0"

# 排序白名单：只允许这些键，避免把用户输入拼进 SQL
SORT_KEYS = {
    "daypay": "j.day_mid",
    "salary": "j.month_mid",
    "title": "j.title",
    "company": "c.name",
    "publish": "j.publish_time",
    "degree": "FIELD(j.degree,'不限','中专/高中','大专','本科','硕士','博士')",
    "stacks": "j.primary_stack",
}

# degree 的自定义顺序（与前端 ['不限','大专','本科','硕士','博士'] 对齐，另加中专/高中）
DEGREE_ORDER = ["不限", "中专/高中", "大专", "本科", "硕士", "博士"]

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 20
MAX_LEGACY_ROWS = 5000          # legacy 全量模式的上限，防止被当成导出接口滥用


def _f(v):
    from decimal import Decimal
    return float(v) if isinstance(v, Decimal) else v


def _rows(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [{c: _f(v) for c, v in zip(cols, r)} for r in cur.fetchall()]


def _scalar(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        r = cur.fetchone()
        return _f(r[0]) if r else None


def build_where(f):
    """根据筛选条件拼 WHERE，返回 (sql_fragment, params)。

    所有值都走参数占位符；只有排序键经过白名单映射。
    """
    where = [WIDE]
    params = []

    if f.get("source"):
        where.append("s.name = %s")
        params.append(f["source"])
    if f.get("stack"):
        where.append(
            "EXISTS (SELECT 1 FROM job_stacks js JOIN stacks st ON st.id=js.stack_id "
            "        WHERE js.job_id=j.id AND st.name=%s)")
        params.append(f["stack"])
    if f.get("degree"):
        where.append("j.degree = %s")
        params.append(f["degree"])
    if f.get("salary_only"):
        # 与前端一致：day_mid 非空（宽口径，含元/月折算值）
        where.append("j.day_mid IS NOT NULL")
    if f.get("intern_daily_only"):
        # 额外提供严口径开关，供"只看可比实习日薪"的场景
        where.append("j.intern_daily_sample = 1")
    if f.get("q"):
        # LIKE 里的 % 和 _ 是通配符，用户搜「100%」「a_b」会被误当模式，
        # 必须转义后再拼（参数化只防注入，不防通配符语义）。
        raw = f["q"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{raw}%"
        where.append("(j.title LIKE %s ESCAPE '\\\\' OR c.name LIKE %s ESCAPE '\\\\')")
        params.extend([like, like])

    return " AND ".join(where), params


BASE_FROM = ("FROM jobs j "
             "JOIN sources s ON s.id=j.source_id "
             "LEFT JOIN companies c ON c.id=j.company_id")


def _attach_relations(items):
    """批量补 stacks / tags / labels，避免每行一次查询（N+1）。"""
    if not items:
        return items
    ids = [it["id"] for it in items]
    ph = ",".join(["%s"] * len(ids))

    stacks = {}
    for r in _rows(f"SELECT js.job_id, st.name FROM job_stacks js "
                   f"JOIN stacks st ON st.id=js.stack_id "
                   f"WHERE js.job_id IN ({ph}) ORDER BY js.job_id, js.ordinal", tuple(ids)):
        stacks.setdefault(r["job_id"], []).append(r["name"])

    tags = {}
    for r in _rows(f"SELECT jt.job_id, t.name FROM job_tags jt JOIN tags t ON t.id=jt.tag_id "
                   f"WHERE jt.job_id IN ({ph})", tuple(ids)):
        tags.setdefault(r["job_id"], []).append(r["name"])

    labels = {}
    for r in _rows(f"SELECT jl.job_id, d.name FROM job_label_links jl "
                   f"JOIN job_label_dict d ON d.id=jl.label_id "
                   f"WHERE jl.job_id IN ({ph})", tuple(ids)):
        labels.setdefault(r["job_id"], []).append(r["name"])

    for it in items:
        it["stacks"] = sorted(stacks.get(it["id"], []))
        it["tags"] = sorted(tags.get(it["id"], []))
        it["labels"] = sorted(labels.get(it["id"], []))
    return items


def legacy_jobs():
    """迁移期兼容接口：返回与 jobs_master.json **完全相同的数组**。

    为什么直读原始快照而不是查库
    ---------------------------
    前端的 19 个 render 函数依赖原始字段结构（`j.intern` 布尔、`j.salary.day_low`、
    `j.durations` 字符串数组、`j.extra.boss_name` …），库里是规范化后的列，
    形状不同、且 `durations` 原文没保存（只解析成了数字）。

    因此先把「URL 换掉、视觉零变化」这一步和「字段映射」解耦：
      Step A（本函数）  → 前端只改 URL，验证 100% 等价
      Step B（下一轮）  → 表格走 /api/jobs 分页，图表改吃 /api/stats/* 聚合

    只在 DEBUG 下开放；上线前必须删除，否则等于没做分页。
    """
    from django.conf import settings
    path = os.path.join(settings.BASE_DIR, "data", "raw", "jobs_master.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def list_jobs(filters, page=1, page_size=DEFAULT_PAGE_SIZE,
              sort="daypay", order="desc"):
    """分页岗位列表。

    legacy=True 时忽略分页，一次返回全部（受 MAX_LEGACY_ROWS 限制）。
    用途：前端迁移期仍需要全量数据算图表；**生产必须关闭**（见 views_jobs 的开关）。
    """
    where, params = build_where(filters)

    total = _scalar(f"SELECT COUNT(*) {BASE_FROM} WHERE {where}", tuple(params) or None)

    col = SORT_KEYS.get(sort, SORT_KEYS["daypay"])
    direction = "DESC" if str(order).lower() != "asc" else "ASC"
    if sort in ("daypay", "salary", "publish"):
        # 数值/时间列：NULL 恒排末尾，避免翻页时 NULL 行位置漂移
        order_sql = f"{col} IS NULL, {col} {direction}"
    else:
        order_sql = f"{col} {direction}"

    offset = (page - 1) * page_size
    items = _rows(
        f"SELECT j.id, j.job_uid, j.title, c.name AS company, s.name AS source, "
        f"       j.city, j.district, j.degree, j.experience, j.salary_raw, "
        f"       j.salary_unit, j.day_mid, j.month_mid, j.is_intern, "
        f"       j.title_has_intern, j.intern_daily_sample, j.primary_stack, "
        f"       j.industry, j.publish_time, j.url {BASE_FROM} "
        f"WHERE {where} ORDER BY {order_sql}, j.id ASC LIMIT %s OFFSET %s",
        tuple(params) + (page_size, offset))

    _attach_relations(items)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
        "sort": {"key": sort, "order": direction.lower()},
        "applied_filters": {k: v for k, v in filters.items() if v},
        "scope": "实习口径：is_wuhan=1 AND is_intern=1 AND is_edu_excluded=0",
    }


def get_job(job_uid):
    """岗位详情：主记录 + stacks/tags/labels + JD 正文（可能没有）。"""
    rows = _rows(
        f"SELECT j.*, c.name AS company_name, c.size AS company_size, "
        f"       c.financing, c.industry AS company_industry, c.open_jobs, "
        f"       c.boss_count, s.name AS source_name {BASE_FROM} "
        f"WHERE j.job_uid=%s", (job_uid,))
    if not rows:
        return None
    job = rows[0]
    job.pop("id", None) if False else None
    for k in ("company_id", "source_id", "first_batch_id", "last_batch_id"):
        job.pop(k, None)

    _attach_relations([job])

    jd = _rows("SELECT content, char_count FROM job_descriptions WHERE job_id=%s",
               (rows[0]["id"],))
    job["jd"] = jd[0] if jd else None
    job.pop("id", None)
    return job
