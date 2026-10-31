# -*- coding: utf-8 -*-
"""列出 summary.json 的完整结构，判断哪些字段能从 jobs 表算出、哪些不能。"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open(os.path.join(ROOT, "data", "raw", "summary.json"), encoding="utf-8"))

print("顶层键数:", len(S))
print()
for k, v in S.items():
    t = type(v).__name__
    if isinstance(v, list):
        print(f"{k:24s} list[{len(v)}]  首项: {json.dumps(v[0], ensure_ascii=False)[:90] if v else '空'}")
    elif isinstance(v, dict):
        print(f"{k:24s} dict({len(v)})  键: {list(v.keys())[:8]}")
    else:
        s = json.dumps(v, ensure_ascii=False)
        print(f"{k:24s} {t:6s} {s[:90]}")
