# -*- coding: utf-8 -*-
"""逐端点比对 API 返回值 vs 源 dashboard JSON。

运行：python scripts/compare_endpoints.py
输出：每个端点的差异清单（含已知差异的分类）
"""
import json
import os
import sys

import django

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "JobDataPlatform.settings")
django.setup()

from django.test import Client                                  # noqa: E402

SRC = os.path.join(ROOT, "data", "raw", "dashboard")
C = Client()


def load(name):
    return json.load(open(os.path.join(SRC, name), encoding="utf-8"))


def diff(label, path, src, api, depth=0, max_report=6):
    """递归比较，返回差异条数。"""
    pad = "  " * (depth + 1)
    if isinstance(src, dict) and isinstance(api, dict):
        n = 0
        missing = set(src) - set(api)
        extra = set(api) - set(src)
        if missing:
            print(f"{pad}[{label}] 缺少键: {sorted(missing)}")
            n += len(missing)
        if extra:
            print(f"{pad}[{label}] 新增键: {sorted(extra)}")
        for k in sorted(set(src) & set(api), key=str):
            n += diff(f"{label}.{k}", f"{path}/{k}", src[k], api[k], depth + 1, max_report)
        return n
    if isinstance(src, list) and isinstance(api, list):
        if len(src) != len(api):
            print(f"{pad}[{label}] 长度不同: 源 {len(src)} vs API {len(api)}")
            return 1
        n = 0
        for i, (a, b) in enumerate(zip(src, api)):
            if a != b and n < max_report:
                print(f"{pad}[{label}][{i}] 源={json.dumps(a, ensure_ascii=False)[:90]}")
                print(f"{pad}{' ' * len(label)} API={json.dumps(b, ensure_ascii=False)[:90]}")
                n += 1
        return n
    if src != api:
        print(f"{pad}[{label}] 源={json.dumps(src, ensure_ascii=False)[:70]}  API={json.dumps(api, ensure_ascii=False)[:70]}")
        return 1
    return 0


def run(name, endpoint):
    src = load(name)
    r = C.get(endpoint)
    if r.status_code != 200:
        print(f"!! {endpoint} 返回 {r.status_code}: {r.content[:200]}")
        return 1
    api = r.json()
    print(f"\n=== {endpoint}  vs  {name} ===")
    n = diff(name, "", src, api)
    print(f"  -> 差异 {n} 处" if n else "  -> 完全一致")
    return n


total = 0
total += run("stack_stats.json", "/api/stats/stacks")
total += run("tags.json", "/api/stats/tags")
total += run("company_panel.json", "/api/stats/companies")
total += run("inventory.json", "/api/stats/inventory")
total += run("tracks.json", "/api/stats/tracks")

print(f"\n{'='*60}\n合计差异: {total}")
