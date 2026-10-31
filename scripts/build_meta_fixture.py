# -*- coding: utf-8 -*-
"""从源 summary.json 抽出「采集元数据」6 个字段，落到 fixtures/collection_meta.json。

这些字段不是从 jobs 表算出来的（是采集过程本身的记录），所以单独存放，
API 原样返回，保证与前端现有形状一致。
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open(os.path.join(ROOT, "data", "raw", "summary.json"), encoding="utf-8"))

META_KEYS = ["boss_meta", "boss_keywords_collected", "boss_coverage_note",
             "platform_inventory", "data_notes"]

meta = {k: S.get(k) for k in META_KEYS}
meta["_note"] = (
    "本文件是采集元数据，不是从 jobs 表算出来的。"
    "boss_meta / boss_keywords_collected / boss_coverage_note / data_notes 描述本次抓取的覆盖情况；"
    "platform_inventory 是平台自报的结果总数（resCount / positionCount），不是库里行数。"
)

out_dir = os.path.join(ROOT, "fixtures")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "collection_meta.json")
json.dump(meta, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"wrote {out_path}")
for k in META_KEYS:
    v = meta[k]
    n = len(v) if isinstance(v, (list, dict)) else "-"
    print(f"  {k:26s} {type(v).__name__:6s} {n}")
