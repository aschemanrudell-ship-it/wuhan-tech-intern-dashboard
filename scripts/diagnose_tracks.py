# -*- coding: utf-8 -*-
"""诊断 tracks 端点的差异（postings / daily.n / fulltime.postings）。"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "JobDataPlatform.settings")
sys.stdout.reconfigure(encoding="utf-8")

import django                                                            # noqa: E402
django.setup()
from django.test import Client                                            # noqa: E402

api = {r["direction"]: r for r in Client().get("/api/stats/tracks").json()["rows"]}
src = {r["direction"]: r for r in
       json.load(open(os.path.join(ROOT, "data/raw/dashboard/tracks.json"), encoding="utf-8"))["rows"]}

print(f"{'方向':10s}{'int.postings':>16s}{'daily.n':>14s}{'ft.postings':>16s}")
print(f"{'':10s}{'源':>8s}{'API':>8s}{'源':>7s}{'API':>7s}{'源':>8s}{'API':>8s}")
for d in src:
    a, b = src[d], api.get(d, {"intern": {"postings": 0, "daily": {"n": 0}},
                               "fulltime": {"postings": 0}})
    print(f"{d:10s}{a['intern']['postings']:8d}{b['intern']['postings']:8d}"
          f"{a['intern']['daily']['n']:7d}{b['intern']['daily']['n']:7d}"
          f"{a['fulltime']['postings']:8d}{b['fulltime']['postings']:8d}")

print("\n源 intern.keywords:")
for d in src:
    print(f"  {d:10s}{src[d]['intern']['keywords']}")
