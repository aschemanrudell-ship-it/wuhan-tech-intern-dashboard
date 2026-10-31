"""岗位列表/详情视图。

参数校验失败一律返回 400 + 结构化 JSON（前端不能收到 HTML）。
"""
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from . import jobs as jobs_q

log = logging.getLogger("JobDataPlatform")


def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _json_array(data, status=200):
    """数组响应：JsonResponse 默认 safe=True 只接受 dict。"""
    return JsonResponse(data, status=status, safe=False,
                        json_dumps_params={"ensure_ascii": False})


def _bad(msg, field=None):
    return _json({"error": "bad_request", "field": field, "detail": msg}, status=400)


def _parse_int(raw, default, lo, hi, field):
    """返回 (value, error_response)。"""
    if raw is None or raw == "":
        return default, None
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None, _bad(f"{field} 必须是整数，收到 {raw!r}", field)
    if v < lo or v > hi:
        return None, _bad(f"{field} 必须在 {lo}..{hi} 之间，收到 {v}", field)
    return v, None


@require_GET
def job_list(request):
    q = request.GET

    page, err = _parse_int(q.get("page"), 1, 1, 100000, "page")
    if err:
        return err
    page_size, err = _parse_int(q.get("page_size"), jobs_q.DEFAULT_PAGE_SIZE,
                                1, jobs_q.MAX_PAGE_SIZE, "page_size")
    if err:
        return err

    sort = (q.get("sort") or "daypay").lower()
    if sort not in jobs_q.SORT_KEYS:
        return _bad(f"sort 只支持 {sorted(jobs_q.SORT_KEYS)}，收到 {sort!r}", "sort")
    order = (q.get("order") or "desc").lower()
    if order not in ("asc", "desc"):
        return _bad("order 只支持 asc/desc", "order")

    # legacy 全量模式只在 DEBUG 下开放：它是前端迁移期的兼容层，
    # 上线后仍然可用的全量导出等于没做分页。
    legacy = q.get("legacy") in ("1", "true", "True")
    if legacy:
        if not settings.DEBUG:
            return _bad("legacy 模式仅在 DEBUG 下可用", "legacy")
        try:
            return _json_array(jobs_q.legacy_jobs())
        except Exception as e:                                 # noqa: BLE001
            log.exception("legacy_jobs failed")
            return _json({"error": "legacy_failed", "detail": str(e)}, status=500)

    filters = {
        "source": (q.get("source") or "").strip(),
        "stack": (q.get("stack") or "").strip(),
        "degree": (q.get("degree") or "").strip(),
        "q": (q.get("q") or "").strip(),
        "salary_only": q.get("salary_only") in ("1", "true", "True"),
        "intern_daily_only": q.get("intern_daily_only") in ("1", "true", "True"),
    }

    try:
        payload = jobs_q.list_jobs(filters, page=page, page_size=page_size,
                                   sort=sort, order=order)
    except Exception as e:                                     # noqa: BLE001
        log.exception("job_list failed")
        return _json({"error": "query_failed", "detail": str(e)}, status=500)
    return _json(payload)


@require_GET
def job_detail(request, job_uid):
    if not job_uid or len(job_uid) > 200:
        return _bad("job_uid 长度非法", "job_uid")
    try:
        payload = jobs_q.get_job(job_uid)
    except Exception as e:                                     # noqa: BLE001
        log.exception("job_detail failed")
        return _json({"error": "query_failed", "detail": str(e)}, status=500)
    if payload is None:
        return _json({"error": "not_found", "job_uid": job_uid}, status=404)
    return _json(payload)
