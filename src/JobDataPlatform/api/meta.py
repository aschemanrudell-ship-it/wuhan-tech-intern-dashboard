"""采集元数据（不是从 jobs 表算出来的字段）。

来源：fixtures/collection_meta.json（由 scripts/build_meta_fixture.py 从源快照抽出）。
"""
import json
import os
from functools import lru_cache

from django.conf import settings

META_PATH = os.path.join(settings.BASE_DIR, "fixtures", "collection_meta.json")


@lru_cache(maxsize=1)
def collection_meta():
    if not os.path.exists(META_PATH):
        return {
            "boss_meta": [],
            "boss_keywords_collected": [],
            "boss_coverage_note": "fixture 缺失：请先运行 python scripts/build_meta_fixture.py",
            "platform_inventory": {},
            "data_notes": [],
        }
    return json.load(open(META_PATH, encoding="utf-8"))
