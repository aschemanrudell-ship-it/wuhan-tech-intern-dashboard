# -*- coding: utf-8 -*-
"""弄清 summary.json 的 salary_scope 与当前 jobs_master 的 5 行差异。"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, "data", "raw", "jobs_master.json"), encoding="utf-8"))
wi = [r for r in D if r.get("is_wuhan") and r.get("intern") and not r.get("is_edu")]

has_day = [r for r in wi if "元/天" in (r.get("salary_raw") or "")]
has_k = [r for r in wi if "K" in (r.get("salary_raw") or "")]
has_kx = [r for r in wi if "K" in (r.get("salary_raw") or "") and "薪" in (r.get("salary_raw") or "")]
none_val = [r for r in wi if not (r.get("salary_raw") or "").strip()]
other = [r for r in wi if (r.get("salary_raw") or "").strip()
         and "元/天" not in r["salary_raw"] and "K" not in r["salary_raw"]]

print("实习口径行数:", len(wi))
print("  含'元/天':", len(has_day))
print("  含'K'    :", len(has_k), " 其中带倍薪:", len(has_kx))
print("  两者兼有 :", len([r for r in wi if "元/天" in (r.get("salary_raw") or "") and "K" in (r.get("salary_raw") or "")]))
print("  值为空   :", len(none_val))
print("  其他口径 :", len(other))
print("  校验:", len(has_day) + len(has_k) + len(none_val) + len(other))

s = json.load(open(os.path.join(ROOT, "data", "raw", "summary.json"), encoding="utf-8"))
print("\nsummary.json salary_scope:", s.get("salary_scope"))
print("summary.json intern_salary_known:", s.get("intern_salary_known"))
print("summary.json wuhan_interns:", s.get("wuhan_interns"))

# 严格 / 宽松
strict = [r for r in wi if (r.get("day_mid") and ("元/天" in (r.get("salary_raw") or "")
          or ("K" in (r.get("salary_raw") or "") and "实习" in (r.get("title") or ""))))]
loose = [r for r in wi if r.get("day_mid") and ("元/天" in (r.get("salary_raw") or "") or "K" in (r.get("salary_raw") or ""))]
print("\n严格口径(_in_scope，源脚本):", len(strict))
print("宽松口径(所有日薪/K):", len(loose))
