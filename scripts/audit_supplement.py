# -*- coding: utf-8 -*-
"""补充审计：durations / labels / degree 脏值 / company 空值 / 跨源重复细节。"""
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROWS = json.load(open(os.path.join(ROOT, "data", "raw", "jobs_master.json"), encoding="utf-8"))
N = len(ROWS)

print("== 1. durations 内容分布（非空 %d 行）==" % sum(1 for r in ROWS if r.get("durations")))
dc = Counter()
for r in ROWS:
    for d in (r.get("durations") or []):
        dc[d] += 1
for k, v in dc.most_common(25):
    print(f"   {k:12s}{v}")

print("\n== 2. labels 内容分布（Top25）==")
lc = Counter()
for r in ROWS:
    for d in (r.get("labels") or []):
        lc[d] += 1
for k, v in lc.most_common(25):
    print(f"   {k:20s}{v}")

print("\n== 3. duration 拆解可行性 ==")
import re
WK = re.compile(r"(\d)\s*天/周")
MO = re.compile(r"(\d+)\s*个月")
wk_ok = mo_ok = 0
for r in ROWS:
    blob = " ".join(str(x) for x in (r.get("durations") or []) + (r.get("labels") or []))
    if WK.search(blob):
        wk_ok += 1
    if MO.search(blob):
        mo_ok += 1
print(f"   能解析出「N天/周」: {wk_ok} / {N} ({wk_ok/N*100:.1f}%)")
print(f"   能解析出「N个月」  : {mo_ok} / {N} ({mo_ok/N*100:.1f}%)")

print("\n== 4. degree 脏值 ==")
deg = Counter(r.get("degree") for r in ROWS)
for k, v in deg.most_common():
    flag = "  <-- 疑似脏值" if k in ("经验不限", "初中及以下") or (k and "经验" in k) else ""
    print(f"   {str(k):10s}{v}{flag}")

print("\n== 5. company 为空的行（%d）按来源 ==" % sum(1 for r in ROWS if not (r.get("company") or "").strip()))
print("  ", dict(Counter(r["source"] for r in ROWS if not (r.get("company") or "").strip())))

print("\n== 6. 跨源同名岗位（title+company 相同但来源不同）==")
g = defaultdict(list)
for r in ROWS:
    c = (r.get("company") or "").strip()
    if not c:
        continue
    g[(r.get("title"), c)].append(r)
cross = {k: v for k, v in g.items() if len({x["source"] for x in v}) > 1}
print("   跨源重复组数:", len(cross))
for k, v in list(cross.items())[:6]:
    print(f"   {k[0]} | {k[1]}")
    for x in v:
        print(f"      - {x['source']:6s} {x['job_id']:20s} url={bool(x.get('url'))}")

print("\n== 7. 同源同名重复（title+company+source 相同）==")
g2 = defaultdict(list)
for r in ROWS:
    c = (r.get("company") or "").strip()
    g2[(r.get("title"), c, r["source"])].append(r)
same = {k: v for k, v in g2.items() if len(v) > 1}
print("   同源重复组数:", len(same), "涉及行数:", sum(len(v) for v in same.values()))
for k, v in list(same.items())[:5]:
    print(f"   {k[0][:30]} | {k[1] or '(公司空)'} | {k[2]} ×{len(v)}")
    for x in v[:3]:
        print(f"      job_id={x['job_id']} url={(x.get('url') or '')[:60]}")

print("\n== 8. company_open_jobs / company_bosses / company_industry 分布 ==")
for f in ("company_open_jobs", "company_bosses"):
    vals = [r.get(f) for r in ROWS if isinstance(r.get(f), (int, float))]
    nz = [v for v in vals if v]
    print(f"   {f}: 有值 {len(vals)}, 非零 {len(nz)}, 最大 {max(vals) if vals else 0}")
ci = Counter(r.get("company_industry") for r in ROWS)
print("   company_industry Top8:", ci.most_common(8))

print("\n== 9. keyword / slug 关系（决定是否存储）==")
ks = Counter((r.get("keyword"), r.get("slug")) for r in ROWS)
print("   (keyword, slug) 组合数:", len(ks))
print("   样例:", list(ks.items())[:5])

print("\n== 10. primary_stack 分布 ==")
print("  ", dict(Counter(r.get("primary_stack") for r in ROWS).most_common()))
