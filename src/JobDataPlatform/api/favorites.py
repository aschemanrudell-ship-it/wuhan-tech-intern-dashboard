"""收藏：列表 / 添加 / 取消。

三条安全要求（都在 tests/test_api_favorites.py 里断言）：
  1. 未登录 → 401
  2. 只能操作自己的收藏（`WHERE user_id = :me`，不是「先查再用」）
  3. 重复收藏幂等（UNIQUE(user_id, job_id) + INSERT IGNORE）
"""
import json

from django.db import connection
from django.http import JsonResponse

from .auth import _body, _rows, require_auth

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _scalar(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        r = cur.fetchone()
        return r[0] if r else None


def _exec(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


@require_auth
def favorite_collection(request):
    """GET  /api/favorites              → 列表（分页）
       POST /api/favorites {job_uid}   → 添加（幂等）

    同一个 URL 按 method 分派：/api/favorites 既是集合也是创建入口。
    早期把 add 放在 /api/favorites/add，结果 POST /api/favorites 被列表视图吃掉
    （它不校验 method），返回了 200 + 列表 —— 这类错误只有测试能抓住。
    """
    if request.method == "POST":
        return _add(request)
    if request.method != "GET":
        return _json({"error": "method_not_allowed",
                      "detail": "只支持 GET / POST"}, 405)
    return _list(request)


def _list(request):
    try:
        page = max(1, int(request.GET.get("page") or 1))
        page_size = int(request.GET.get("page_size") or DEFAULT_PAGE_SIZE)
    except (TypeError, ValueError):
        return _json({"error": "bad_request", "detail": "page/page_size 必须是整数"}, 400)
    page_size = min(MAX_PAGE_SIZE, max(1, page_size))
    me = request.user_row["id"]

    total = _scalar("SELECT COUNT(*) FROM favorites WHERE user_id=%s", (me,))
    items = _rows(
        "SELECT j.job_uid, j.title, c.name AS company, j.city, j.degree, "
        "       j.salary_raw, j.day_mid, j.url, f.created_at "
        "FROM favorites f "
        "JOIN jobs j ON j.id=f.job_id "
        "LEFT JOIN companies c ON c.id=j.company_id "
        "WHERE f.user_id=%s "
        "ORDER BY f.created_at DESC, f.id DESC "
        "LIMIT %s OFFSET %s", (me, page_size, (page - 1) * page_size))

    return _json({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    })


def _add(request):
    data, err = _body(request)
    if err:
        return err

    job_uid = (data.get("job_uid") or "").strip()
    if not job_uid:
        return _json({"error": "bad_request", "field": "job_uid",
                      "detail": "缺少 job_uid"}, 400)

    job = _rows("SELECT id FROM jobs WHERE job_uid=%s", (job_uid,))
    if not job:
        return _json({"error": "job_not_found", "job_uid": job_uid}, 404)

    me = request.user_row["id"]
    # INSERT IGNORE + UNIQUE(user_id, job_id) = 幂等，不必"先查后插"（那有竞态）
    _exec("INSERT IGNORE INTO favorites (user_id, job_id) VALUES (%s,%s)",
          (me, job[0]["id"]))
    total = _scalar("SELECT COUNT(*) FROM favorites WHERE user_id=%s", (me,))
    return _json({"ok": True, "job_uid": job_uid, "my_favorites": total}, 201)


@require_auth
def favorite_remove(request, job_uid):
    """DELETE /api/favorites/<job_uid>

    DELETE 必须带 user_id 条件 —— 否则等于允许删别人的收藏。
    """
    me = request.user_row["id"]
    job = _rows("SELECT id FROM jobs WHERE job_uid=%s", (job_uid,))
    if not job:
        return _json({"error": "job_not_found", "job_uid": job_uid}, 404)

    affected = _exec("DELETE FROM favorites WHERE user_id=%s AND job_id=%s",
                     (me, job[0]["id"]))
    total = _scalar("SELECT COUNT(*) FROM favorites WHERE user_id=%s", (me,))
    return _json({
        "ok": True,
        "removed": affected,
        "job_uid": job_uid,
        "my_favorites": total,
        # removed=0 表示「本来就没收藏」或「收藏属于别人」，两者对外不可区分
        "note": "removed=0 表示未收藏；不会删除其他用户的收藏",
    })
