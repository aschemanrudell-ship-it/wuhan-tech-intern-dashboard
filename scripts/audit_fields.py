# -*- coding: utf-8 -*-
"""字段审计：对 data/raw/jobs_master.json 做类型/缺失率/基数/唯一性/薪资单位统计。

产出：
  work/audit.json     —— 机器可读的完整审计结果
  docs/FIELD-AUDIT.md —— 人读报告

不修改任何源数据，只读。
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
DOCS = os.path.join(ROOT, "docs")
WORK = os.path.join(ROOT, "work")
os.makedirs(WORK, exist_ok=True)
os.makedirs(DOCS, exist_ok=True)

ROWS = json.load(open(os.path.join(RAW, "jobs_master.json"), encoding="utf-8"))
JD = json.load(open(os.path.join(RAW, "zhilian_jd.json"), encoding="utf-8"))
N = len(ROWS)


def pytype(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "dict"
    return type(v).__name__


def is_empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def flat_json(v, limit=120) -> str:
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "…"


# ---------------------------------------------------------------- 字段级审计
# 注意：必须区分「键不存在」与「键存在但值为空」。
# 早期版本用 nonempty = N - empty，会把缺失键的行算成非空（durations 因此被虚报为 2950）。
ALL_KEYS = sorted({k for r in ROWS for k in r.keys()})

fields: dict[str, dict] = {
    k: {"types": Counter(), "present": 0, "empty": 0, "values": Counter(), "max_len": 0, "samples": []}
    for k in ALL_KEYS
}

for r in ROWS:
    for k in ALL_KEYS:
        if k not in r:            # 键缺失：不计入 present
            continue
        v = r[k]
        f = fields[k]
        f["present"] += 1
        f["types"][pytype(v)] += 1
        if is_empty(v):
            f["empty"] += 1
            continue
        try:
            f["values"][flat_json(v, 200)] += 1
        except TypeError:
            pass
        ln = len(v) if isinstance(v, (str, list, dict)) else len(str(v))
        f["max_len"] = max(f["max_len"], ln)
        if len(f["samples"]) < 3 and flat_json(v) not in f["samples"]:
            f["samples"].append(flat_json(v))

audit_fields = []
for k, f in fields.items():
    nonempty = f["present"] - f["empty"]
    missing_key = N - f["present"]
    audit_fields.append({
        "field": k,
        "types": dict(f["types"]),
        "present": f["present"],
        "missing_key": missing_key,
        "nonempty": nonempty,
        "empty": f["empty"],
        "null_rate": round((f["empty"] + missing_key) / N, 4),
        "distinct": len(f["values"]),
        "cardinality_ratio": round(len(f["values"]) / nonempty, 4) if nonempty else 0.0,
        "max_len": f["max_len"],
        "samples": f["samples"][:3],
    })
audit_fields.sort(key=lambda x: (-(x["empty"] + x["missing_key"]), x["field"]))

# ---------------------------------------------------------------- 嵌套字段展开
nested = {}
for parent in ("salary", "extra"):
    keys = Counter()
    empty = Counter()
    for r in ROWS:
        obj = r.get(parent) or {}
        if not isinstance(obj, dict):
            continue
        for kk, vv in obj.items():
            keys[kk] += 1
            if is_empty(vv):
                empty[kk] += 1
    nested[parent] = {
        "subfields": [{
            "subfield": kk,
            "present": n,
            "empty": empty[kk],
            "null_rate": round(empty[kk] / n, 4) if n else 1.0,
        } for kk, n in keys.most_common()]
    }

# ---------------------------------------------------------------- 唯一标识
def uniq_count(keyfn):
    seen = Counter()
    for r in ROWS:
        seen[keyfn(r)] += 1
    dup = {k: v for k, v in seen.items() if v > 1}
    return {
        "distinct": len(seen),
        "duplicate_keys": len(dup),
        "dup_rows": sum(v for v in dup.values()),
        "top_dups": sorted(dup.items(), key=lambda kv: -kv[1])[:5],
    }


identity = {
    "job_id_alone": uniq_count(lambda r: r.get("job_id")),
    "(source, job_id)": uniq_count(lambda r: (r.get("source"), r.get("job_id"))),
    "url": uniq_count(lambda r: r.get("url")),
    "(source, url)": uniq_count(lambda r: (r.get("source"), r.get("url"))),
    "(title, company)": uniq_count(lambda r: (r.get("title"), r.get("company"))),
    "(title, company, source)": uniq_count(lambda r: (r.get("title"), r.get("company"), r.get("source"))),
}

# ---------------------------------------------------------------- 来源
source_dist = Counter(r.get("source") for r in ROWS)

# ---------------------------------------------------------------- 薪资单位
UNIT_RULES = [
    ("元/天", re.compile(r"\d\s*元?\s*/\s*天")),
    ("K/月(倍薪)", re.compile(r"\d\s*[kK]\s*[·*]\s*\d+\s*薪")),
    ("K/月", re.compile(r"\d\s*[kK]\b")),
    ("万/月", re.compile(r"\d\s*万")),
    ("元/月(区间)", re.compile(r"\d{3,6}\s*[-~至]\s*\d{3,6}\s*元")),
    ("元/月(单值)", re.compile(r"\d{3,6}\s*元")),
    ("面议/保密", re.compile(r"面议|保密|议")),
]


def unit_of(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return "缺失"
    for name, pat in UNIT_RULES:
        if pat.search(t):
            return name
    return "未识别"


unit_dist = Counter(unit_of(r.get("salary_raw")) for r in ROWS)
unit_by_source = defaultdict(Counter)
for r in ROWS:
    unit_by_source[r.get("source")][unit_of(r.get("salary_raw"))] += 1

# day_mid 可用性（按单位）
day_mid_avail = defaultdict(lambda: [0, 0])
for r in ROWS:
    u = unit_of(r.get("salary_raw"))
    day_mid_avail[u][0] += 1
    if r.get("day_mid") is not None:
        day_mid_avail[u][1] += 1

# ---------------------------------------------------------------- JD 覆盖
jd_keys = set(JD.keys())
zl_prefix = "zl-"


def jid(r):
    v = str(r.get("job_id") or "")
    return v[len(zl_prefix):] if v.startswith(zl_prefix) else v


jd_have = sum(1 for r in ROWS if jid(r) in jd_keys)
jd_by_source = Counter()
for r in ROWS:
    if jid(r) in jd_keys:
        jd_by_source[r.get("source")] += 1
jd_lens = [len(v.get("desc") or "") for v in JD.values()]
jd_completeness = {
    "rows_with_jd": jd_have,
    "coverage": round(jd_have / N, 4),
    "by_source": dict(jd_by_source),
    "jd_library_size": len(JD),
    "jd_len_min": min(jd_lens) if jd_lens else 0,
    "jd_len_median": sorted(jd_lens)[len(jd_lens) // 2] if jd_lens else 0,
    "jd_len_max": max(jd_lens) if jd_lens else 0,
}

# ---------------------------------------------------------------- 业务子集规模
def cnt(pred):
    return sum(1 for r in ROWS if pred(r))


biz = {
    "total": N,
    "is_wuhan": cnt(lambda r: r.get("is_wuhan")),
    "intern": cnt(lambda r: r.get("intern")),
    "is_edu_excluded": cnt(lambda r: r.get("is_edu")),
    "wuhan_intern": cnt(lambda r: r.get("is_wuhan") and r.get("intern") and not r.get("is_edu")),
    "wuhan_intern_tech": cnt(lambda r: r.get("is_wuhan") and r.get("intern") and not r.get("is_edu") and r.get("stacks")),
    "wuhan_intern_with_day_mid": cnt(lambda r: r.get("is_wuhan") and r.get("intern") and not r.get("is_edu") and r.get("day_mid")),
    "degree_values": dict(Counter(r.get("degree") for r in ROWS).most_common()),
}

result = {
    "rows": N,
    "fields": audit_fields,
    "nested": nested,
    "identity": identity,
    "source_dist": dict(source_dist),
    "salary_units": dict(unit_dist),
    "salary_units_by_source": {k: dict(v) for k, v in unit_by_source.items()},
    "day_mid_availability": {k: {"total": v[0], "with_day_mid": v[1]} for k, v in day_mid_avail.items()},
    "jd": jd_completeness,
    "biz": biz,
}
json.dump(result, open(os.path.join(WORK, "audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- Markdown 报告
L = []
A = L.append
A("# 字段审计报告\n")
A(f"- 数据文件：`data/raw/jobs_master.json`")
A(f"- 总行数：**{N}**")
A(f"- 字段数：**{len(audit_fields)}**（含 2 个嵌套对象 `salary` / `extra`）")
A(f"- 快照日期：2026-10-12（源项目一次性抓取）")
A(f"- 生成方式：`scripts/audit_fields.py`，只读源文件\n")

A("## 1. 字段总览\n")
A("按缺失量降序。`缺失率` = （键不存在 + 键存在但为空）/ 总行数；`非空` 只统计键存在且值非空的行。")
A("`基数比` = 去重值数 / 非空行数，接近 1 表示近似唯一。\n")
A("| 字段 | 类型 | 键存在 | 键缺失 | 值为空 | 非空 | 缺失率 | 去重值 | 基数比 | 最大长度 |")
A("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
for f in audit_fields:
    t = "/".join(f"{k}" for k in f["types"])
    A(f"| `{f['field']}` | {t} | {f['present']} | {f['missing_key']} | {f['empty']} | {f['nonempty']} | {f['null_rate']*100:.1f}% | {f['distinct']} | {f['cardinality_ratio']:.2f} | {f['max_len']} |")

A("\n### 1.1 嵌套对象 `salary`\n")
A("| 子字段 | 存在 | 空 | 缺失率 |")
A("| --- | ---: | ---: | ---: |")
for s in nested["salary"]["subfields"]:
    A(f"| `salary.{s['subfield']}` | {s['present']} | {s['empty']} | {s['null_rate']*100:.1f}% |")

A("\n### 1.2 嵌套对象 `extra`\n")
A("| 子字段 | 存在 | 空 | 缺失率 |")
A("| --- | ---: | ---: | ---: |")
for s in nested["extra"]["subfields"]:
    A(f"| `extra.{s['subfield']}` | {s['present']} | {s['empty']} | {s['null_rate']*100:.1f}% |")

A("\n### 1.3 样例值\n")
A("| 字段 | 样例 |")
A("| --- | --- |")
for f in audit_fields[:24]:
    s = " ／ ".join(x.replace("|", "\\|") for x in f["samples"][:2])
    A(f"| `{f['field']}` | {s} |")

A("\n## 2. 唯一标识候选\n")
A("| 候选键 | 去重后 | 重复键数 | 涉及行数 | 结论 |")
A("| --- | ---: | ---: | ---: | --- |")
for k, v in identity.items():
    ok = "✅ 唯一" if v["duplicate_keys"] == 0 else f"⚠️ {v['duplicate_keys']} 个键重复"
    A(f"| `{k}` | {v['distinct']} | {v['duplicate_keys']} | {v['dup_rows']} | {ok} |")

A("\n### 2.1 重复样例\n")
for k, v in identity.items():
    if v["duplicate_keys"] == 0:
        continue
    A(f"**`{k}`** 前 3 组重复：\n")
    A("```")
    for key, times in v["top_dups"][:3]:
        A(f"{key}  ×{times}")
    A("```\n")

A("\n## 3. 来源分布\n")
A("| 来源 | 行数 | 占比 |")
A("| --- | ---: | ---: |")
for k, v in source_dist.most_common():
    A(f"| {k} | {v} | {v/N*100:.1f}% |")

A("\n## 4. 薪资单位\n")
A("| 单位形态 | 行数 | 占比 | 其中 day_mid 可算 |")
A("| --- | ---: | ---: | ---: |")
for k, v in unit_dist.most_common():
    d = day_mid_avail.get(k, [0, 0])
    A(f"| {k} | {v} | {v/N*100:.1f}% | {d[1]}/{d[0]} |")

A("\n### 4.1 按来源 × 单位\n")
srcs = [s for s, _ in source_dist.most_common()]
units = [u for u, _ in unit_dist.most_common()]
A("| 来源 | " + " | ".join(units) + " |")
A("| --- | " + " | ".join("---:" for _ in units) + " |")
for s in srcs:
    row = [str(unit_by_source[s].get(u, 0)) for u in units]
    A(f"| {s} | " + " | ".join(row) + " |")

A("\n## 5. JD 正文覆盖\n")
A(f"- 有 JD 正文的行：**{jd_completeness['rows_with_jd']}** / {N}（{jd_completeness['coverage']*100:.1f}%）")
A(f"- JD 库总条数：{jd_completeness['jd_library_size']}")
A(f"- JD 长度：最短 {jd_completeness['jd_len_min']} / 中位 {jd_completeness['jd_len_median']} / 最长 {jd_completeness['jd_len_max']} 字")
A(f"- 按来源：{jd_completeness['by_source'] or '无'}\n")

A("## 6. 业务子集规模\n")
A("| 子集 | 行数 |")
A("| --- | ---: |")
for k, v in biz.items():
    if k == "degree_values":
        continue
    A(f"| {k} | {v} |")
A(f"\n学历取值分布：`{biz['degree_values']}`")

open(os.path.join(DOCS, "FIELD-AUDIT.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")

print(f"rows={N} fields={len(audit_fields)}")
print("identity:", {k: (v['distinct'], v['duplicate_keys']) for k, v in identity.items()})
print("salary units:", dict(unit_dist))
print("jd coverage:", jd_completeness['rows_with_jd'], "/", N)
print("wrote docs/FIELD-AUDIT.md and work/audit.json")
