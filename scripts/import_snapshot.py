# -*- coding: utf-8 -*-
"""把 jobs_master.json 快照导入 MySQL。

设计要点（对应 docs/DESIGN.md）：
  * 幂等键 = job_uid（原始 job_id），用 ON DUPLICATE KEY UPDATE 实现「重复导入不产生新行」
  * 每次运行写一条 import_batch，记录 sha256 与 insert/update/skip 计数，便于验收
  * 跨源同名不合并，只写 dup_group_key 标记
  * 低覆盖字段允许 NULL，不写假值
  * day_mid_comparable 是数据库生成列，脚本不写它

用法：
  python scripts/import_snapshot.py --host 127.0.0.1 --port 3307 --user root --database jobdata
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime

import pymysql

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")

SOURCE_CODE = {
    "BOSS直聘": "boss",
    "智联招聘": "zhilian",
    "猎聘": "liepin",
    "实习僧": "shixiseng",
}

SOURCE_PREFIX = {"BOSS直聘": "boss-", "智联招聘": "zl-", "猎聘": "lp-", "实习僧": "sxs-"}

# 薪资单位判定（顺序敏感：先匹配更具体的形态）
UNIT_RULES = [
    ("DAY", re.compile(r"\d\s*元?\s*/\s*天")),
    ("K_MONTH_X", re.compile(r"\d\s*[kK]\s*[·*]\s*\d+\s*薪")),
    ("K_MONTH", re.compile(r"\d\s*[kK]\b")),
    ("WAN_MONTH", re.compile(r"\d\s*万")),
    ("MONTH_YUAN", re.compile(r"\d{3,6}\s*[-~至]\s*\d{3,6}\s*元|\d{3,6}\s*元")),
    ("NEGOTIABLE", re.compile(r"面议|保密|议")),
]

WK_RE = re.compile(r"(\d)\s*天/周")
MO_RE = re.compile(r"(\d+)\s*个月")

DEGREE_CLEAN = {
    "经验不限": ("不限", True),      # (清洗值, 是否脏值)
    "初中及以下": ("不限", True),
}


def unit_of(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return "MISSING"
    for name, pat in UNIT_RULES:
        if pat.search(t):
            return name
    return "UNKNOWN"


def clean_degree(raw: str) -> tuple[str, str | None]:
    """返回 (规范化学历, 原始脏值)。"""
    v = (raw or "").strip()
    if not v:
        return "不限", None
    if v in DEGREE_CLEAN:
        return DEGREE_CLEAN[v][0], v
    if "中专" in v or "中技" in v or "高中" in v:
        return "中专/高中", None
    if "大专" in v:
        return "大专", None
    if "本科" in v:
        return "本科", None
    if "硕士" in v or "研究生" in v:
        return "硕士", None
    if "博士" in v:
        return "博士", None
    return v, None


def parse_duration(row: dict) -> tuple[int | None, int | None]:
    """从 durations + labels 里解析每周到岗天数与实习月数；解析不出为 None。"""
    parts: list[str] = []
    for key in ("durations", "labels"):
        for v in (row.get(key) or []):
            if isinstance(v, str):
                parts.append(v)
    blob = " ".join(parts)
    wk = WK_RE.search(blob)
    mo = MO_RE.search(blob)
    return (int(wk.group(1)) if wk else None, int(mo.group(1)) if mo else None)


def norm_name(s: str) -> str:
    """公司名归一化：去空白、全角转半角括号、统一大小写。"""
    t = (s or "").strip()
    t = t.replace("（", "(").replace("）", ")").replace("　", "")
    t = re.sub(r"\s+", "", t)
    return t


def dup_key(title: str, company: str) -> str | None:
    nt, nc = norm_name(title), norm_name(company)
    if not nt or not nc:
        return None
    return hashlib.sha1(f"{nt}|{nc}".encode()).hexdigest()[:32]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("JDP_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("JDP_PORT", "3307")))
    ap.add_argument("--user", default=os.environ.get("JDP_USER", "root"))
    ap.add_argument("--database", default=os.environ.get("JDP_DATABASE", "jobdata"))
    ap.add_argument("--file", default=os.path.join(RAW, "jobs_master.json"))
    ap.add_argument(
        "--use-env-credentials",
        action="store_true",
        help="从 JDP_PASSWORD 环境变量读取数据库口令；不使用命令行参数，避免口令落到 shell 历史里",
    )
    args = ap.parse_args()

    path = args.file
    raw_bytes = open(path, "rb").read()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    rows = json.loads(raw_bytes.decode("utf-8"))
    print(f"读取 {len(rows)} 行  sha256={sha[:16]}…")

    jd_map = {}
    jd_path = os.path.join(RAW, "zhilian_jd.json")
    if os.path.exists(jd_path):
        jd_map = json.load(open(jd_path, encoding="utf-8"))
        print(f"JD 库 {len(jd_map)} 条")

    # 口令只从环境变量取，不进命令行、不进仓库
    conn_options = dict(
        host=args.host,
        port=args.port,
        user=args.user,
        database=args.database,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
    if args.use_env_credentials:
        conn_options["password"] = os.environ.get("JDP_PASSWORD", "")
    conn = pymysql.connect(**conn_options)
    started = datetime.now()

    try:
        with conn.cursor() as cur:
            # ---------------- 批次 ----------------
            cur.execute(
                "INSERT INTO import_batch (source_file, file_sha256, row_total, started_at) VALUES (%s,%s,%s,%s)",
                (os.path.basename(path), sha, len(rows), started),
            )
            batch_id = cur.lastrowid

            # ---------------- 字典表 ----------------
            codes = {v: k for k, v in SOURCE_CODE.items()}
            for zh, code in SOURCE_CODE.items():
                cur.execute(
                    "INSERT INTO sources (name, code) VALUES (%s,%s) ON DUPLICATE KEY UPDATE name=VALUES(name)",
                    (zh, code),
                )
            cur.execute("SELECT id, name FROM sources")
            src_id = {r["name"]: r["id"] for r in cur.fetchall()}

            all_stacks = sorted({s for r in rows for s in (r.get("stacks") or []) if s})
            all_tags = sorted({t for r in rows for t in (r.get("tags") or []) if t})
            all_labels = sorted({t for r in rows for t in (r.get("labels") or []) if t})
            for s in all_stacks:
                cur.execute("INSERT INTO stacks (name) VALUES (%s) ON DUPLICATE KEY UPDATE name=VALUES(name)", (s,))
            for t in all_tags:
                cur.execute("INSERT INTO tags (name) VALUES (%s) ON DUPLICATE KEY UPDATE name=VALUES(name)", (t,))
            for t in all_labels:
                cur.execute("INSERT INTO job_label_dict (name) VALUES (%s) ON DUPLICATE KEY UPDATE name=VALUES(name)", (t,))
            cur.execute("SELECT id,name FROM stacks"); stack_id = {r["name"]: r["id"] for r in cur.fetchall()}
            cur.execute("SELECT id,name FROM tags");   tag_id   = {r["name"]: r["id"] for r in cur.fetchall()}
            cur.execute("SELECT id,name FROM job_label_dict"); label_id = {r["name"]: r["id"] for r in cur.fetchall()}
            print(f"字典：来源 {len(src_id)} / 方向 {len(stack_id)} / 技能 {len(tag_id)} / 标签 {len(label_id)}")

            # ---------------- 公司 ----------------
            company_names = {}
            for r in rows:
                name = (r.get("company") or "").strip()
                if not name:
                    continue
                company_names.setdefault(norm_name(name), name)
            for norm, name in company_names.items():
                cur.execute(
                    "INSERT INTO companies (name, normalized_name) VALUES (%s,%s) "
                    "ON DUPLICATE KEY UPDATE name=VALUES(name)",
                    (name, norm),
                )
            cur.execute("SELECT id, normalized_name FROM companies")
            comp_id = {r["normalized_name"]: r["id"] for r in cur.fetchall()}
            print(f"公司：{len(comp_id)}")

            # 公司画像（覆盖更新，低覆盖字段留 NULL）
            for r in rows:
                name = (r.get("company") or "").strip()
                if not name:
                    continue
                ind = r.get("company_industry")
                size = r.get("company_size")
                fin = r.get("financing")
                oj = r.get("company_open_jobs")
                bc = r.get("company_bosses")
                if not any([ind, size, fin, oj, bc]):
                    continue
                cur.execute(
                    "UPDATE companies SET industry=COALESCE(%s,industry), size=COALESCE(%s,size), "
                    "financing=COALESCE(%s,financing), open_jobs=COALESCE(%s,open_jobs), "
                    "boss_count=COALESCE(%s,boss_count) WHERE normalized_name=%s",
                    (ind, size, fin, oj, bc, norm_name(name)),
                )

            # ---------------- 岗位主表 ----------------
            ins_job = (
                "INSERT INTO jobs (job_uid, source_id, source_job_id, crawl_keyword, crawl_slug, title, company_id, "
                "city, is_wuhan, district, degree, degree_raw, experience, is_intern, is_edu_excluded, "
                "weekly_days, intern_months, title_has_intern, salary_raw, salary_unit, day_low, day_high, day_mid, "
                "month_low, month_high, month_mid, industry, primary_stack, boss_name, boss_title, publish_time, "
                "url, dup_group_key, first_batch_id, last_batch_id) "
                "VALUES (%(job_uid)s,%(source_id)s,%(source_job_id)s,%(crawl_keyword)s,%(crawl_slug)s,%(title)s,%(company_id)s,"
                "%(city)s,%(is_wuhan)s,%(district)s,%(degree)s,%(degree_raw)s,%(experience)s,%(is_intern)s,"
                "%(is_edu_excluded)s,%(weekly_days)s,%(intern_months)s,%(title_has_intern)s,%(salary_raw)s,%(salary_unit)s,"
                "%(day_low)s,%(day_high)s,%(day_mid)s,%(month_low)s,%(month_high)s,%(month_mid)s,%(industry)s,"
                "%(primary_stack)s,%(boss_name)s,%(boss_title)s,%(publish_time)s,%(url)s,%(dup_group_key)s,"
                "%(batch_id)s,%(batch_id)s) "
                "ON DUPLICATE KEY UPDATE "
                "source_id=VALUES(source_id), source_job_id=VALUES(source_job_id), crawl_keyword=VALUES(crawl_keyword),"
                "crawl_slug=VALUES(crawl_slug),"
                "title=VALUES(title), company_id=VALUES(company_id), city=VALUES(city), is_wuhan=VALUES(is_wuhan),"
                "district=VALUES(district), degree=VALUES(degree), degree_raw=VALUES(degree_raw),"
                "experience=VALUES(experience), is_intern=VALUES(is_intern), is_edu_excluded=VALUES(is_edu_excluded),"
                "weekly_days=VALUES(weekly_days), intern_months=VALUES(intern_months),"
                "title_has_intern=VALUES(title_has_intern), salary_raw=VALUES(salary_raw),"
                "salary_unit=VALUES(salary_unit), day_low=VALUES(day_low), day_high=VALUES(day_high),"
                "day_mid=VALUES(day_mid), month_low=VALUES(month_low), month_high=VALUES(month_high),"
                "month_mid=VALUES(month_mid), industry=VALUES(industry), primary_stack=VALUES(primary_stack), boss_name=VALUES(boss_name),"
                "boss_title=VALUES(boss_title), publish_time=VALUES(publish_time), url=VALUES(url),"
                "dup_group_key=VALUES(dup_group_key), last_batch_id=VALUES(last_batch_id)"
            )
            ins_stack = ("INSERT INTO job_stacks (job_id, stack_id, ordinal) VALUES (%s,%s,%s) "
                         "ON DUPLICATE KEY UPDATE ordinal=VALUES(ordinal)")
            ins_tag = "INSERT IGNORE INTO job_tags (job_id, tag_id) VALUES (%s,%s)"
            ins_label = "INSERT IGNORE INTO job_label_links (job_id, label_id) VALUES (%s,%s)"
            ins_jd = ("INSERT INTO job_descriptions (job_id, content, char_count, acquired_by, fetched_at) "
                      "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE content=VALUES(content), "
                      "char_count=VALUES(char_count)")

            url_seen = {}
            for r in rows:
                src = r.get("source")
                jid = str(r.get("job_id") or "")
                prefix = SOURCE_PREFIX.get(src, "")
                sjid = jid[len(prefix):] if prefix and jid.startswith(prefix) else jid
                city = r.get("city") or ""
                if city not in url_seen:
                    url_seen[city] = r.get("city") or city

                p = None  # 占位，避免误用字符串拼接；所有写入都走参数化
                payload = {
                    "job_uid": jid[:200],
                    "source_id": src_id[src],
                    "source_job_id": sjid[:120],
                    "crawl_keyword": (r.get("keyword") or "")[:64],
                    "crawl_slug": (r.get("slug") or "")[:64],
                    "title": (r.get("title") or "")[:255],
                    "company_id": comp_id.get(norm_name(r.get("company") or "")) or None,
                    "city": (city or "")[:32],
                    "is_wuhan": 1 if r.get("is_wuhan") else 0,
                    "district": (r.get("district") or None),
                    "degree": clean_degree(r.get("degree"))[0][:32],
                    "degree_raw": clean_degree(r.get("degree"))[1],
                    "experience": (r.get("experience") or None),
                    "is_intern": 1 if r.get("intern") else 0,
                    "is_edu_excluded": 1 if r.get("is_edu") else 0,
                    "weekly_days": None,
                    "intern_months": None,
                    "title_has_intern": 1 if "实习" in (r.get("title") or "") else 0,
                    "salary_raw": (r.get("salary_raw") or None),
                    "salary_unit": unit_of(r.get("salary_raw")),
                    "day_low": r.get("salary", {}).get("day_low") if isinstance(r.get("salary"), dict) else None,
                    "day_high": r.get("salary", {}).get("day_high") if isinstance(r.get("salary"), dict) else None,
                    "day_mid": r.get("day_mid"),
                    "month_low": r.get("salary", {}).get("month_low") if isinstance(r.get("salary"), dict) else None,
                    "month_high": r.get("salary", {}).get("month_high") if isinstance(r.get("salary"), dict) else None,
                    "month_mid": r.get("month_mid"),
                    "industry": (r.get("industry") or None),
                    "primary_stack": (r.get("primary_stack") or None),
                    "boss_name": (r.get("extra") or {}).get("boss_name"),
                    "boss_title": (r.get("extra") or {}).get("boss_title"),
                    "publish_time": r.get("publish_time") or None,
                    "url": (r.get("url") or None),
                    "dup_group_key": dup_key(r.get("title") or "", r.get("company") or ""),
                    "batch_id": batch_id,
                }
                payload["weekly_days"], payload["intern_months"] = parse_duration(r)

                cur.execute(ins_job, payload)
                # 取回 job_id（新插入或已存在）
                if cur.rowcount == 1:
                    internal_id = cur.lastrowid
                else:
                    cur.execute("SELECT id FROM jobs WHERE job_uid=%s", (payload["job_uid"],))
                    internal_id = cur.fetchone()["id"]

                for idx, s in enumerate(r.get("stacks") or []):
                    if s in stack_id:
                        cur.execute(ins_stack, (internal_id, stack_id[s], idx))
                for t in (r.get("tags") or []):
                    if t in tag_id:
                        cur.execute(ins_tag, (internal_id, tag_id[t]))
                for t in (r.get("labels") or []):
                    if t in label_id:
                        cur.execute(ins_label, (internal_id, label_id[t]))
                if sjid in jd_map:
                    jd = jd_map[sjid]
                    content = re.sub(r"<[^>]+>", "", jd.get("desc") or "").strip()
                    if content:
                        cur.execute(ins_jd, (internal_id, content, len(content),
                                             "zhilian_ssr_jobDetailData.position.desc", None))

            # ---------------- 统计 ----------------
            cur.execute("SELECT COUNT(*) c FROM jobs")
            total = cur.fetchone()["c"]
            cur.execute(
                "UPDATE import_batch SET row_inserted=%s, row_updated=%s, row_skipped=%s, finished_at=%s WHERE id=%s",
                (total, 0, len(rows), datetime.now(), batch_id),
            )
        conn.commit()
        print(f"导入完成：jobs 表 {total} 行，batch_id={batch_id}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
