"""API 视图。

端点清单（阶段一）：
  GET /api/health            —— 数据库连通与关键表行数
  GET /api/stats/summary     —— 替代 data/summary.json
  GET /api/stats/stacks      —— 替代 data/stack_stats.json
  GET /api/stats/tags        —— 替代 data/tags.json
  GET /api/stats/companies   —— 替代 data/company_panel.json
  GET /api/stats/inventory   —— 替代 data/inventory.json（读 fixture）
  GET /api/stats/tracks      —— 替代 data/tracks.json
"""
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from . import queries, stats_extra
from .meta import collection_meta

log = logging.getLogger("JobDataPlatform")


def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _guard(fn, label):
    """统一的错误兜底：失败时返回结构化错误，不吐 HTML 堆栈。"""
    try:
        return _json(fn())
    except Exception as e:                                     # noqa: BLE001
        log.exception("%s failed", label)
        return _json({"error": "query_failed", "endpoint": label, "detail": str(e)}, status=500)


@require_GET
def health(request):
    try:
        return _json(queries.health())
    except Exception as e:                                     # noqa: BLE001
        log.exception("health check failed")
        return _json({"error": "database_unavailable", "detail": str(e)}, status=503)


@require_GET
def stats_summary(request):
    try:
        payload = queries.summary()
    except Exception as e:                                     # noqa: BLE001
        log.exception("summary aggregation failed")
        return _json({"error": "aggregation_failed", "detail": str(e)}, status=500)

    meta = collection_meta()
    payload["boss_meta"] = meta.get("boss_meta", [])
    payload["boss_keywords_collected"] = meta.get("boss_keywords_collected", [])
    payload["boss_coverage_note"] = meta.get("boss_coverage_note", "")
    payload["platform_inventory"] = meta.get("platform_inventory", {})
    payload["data_notes"] = meta.get("data_notes", [])
    payload["scope_notes"] = {
        "intern_scope": "is_wuhan=1 AND is_intern=1 AND is_edu_excluded=0",
        "intern_scope_rows": payload.get("wuhan_interns"),
        "daily_sample": "intern_daily_sample=1（元/天，或标题含「实习」的 K/月）",
        "daily_sample_rows": payload.get("daily_sample_n"),
        "intern_salary_known": "有明码薪资字段 = daily + monthly_k，不等于可统计样本",
        "source_of_truth": "docs/SUMMARY-MAPPING.md",
    }
    return _json(payload)


@require_GET
def stats_stacks(request):
    return _guard(stats_extra.stack_stats, "stats_stacks")


@require_GET
def stats_tags(request):
    return _guard(stats_extra.tags_stats, "stats_tags")


@require_GET
def stats_companies(request):
    return _guard(stats_extra.companies_panel, "stats_companies")


@require_GET
def stats_inventory(request):
    return _guard(stats_extra.inventory, "stats_inventory")


@require_GET
def stats_tracks(request):
    return _guard(stats_extra.tracks, "stats_tracks")
