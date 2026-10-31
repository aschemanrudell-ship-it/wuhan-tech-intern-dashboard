"""URL 路由。"""
from django.urls import path

from . import auth, favorites, views, views_jobs

urlpatterns = [
    # 健康检查与统计
    path("health", views.health, name="health"),
    path("stats/summary", views.stats_summary, name="stats-summary"),
    path("stats/stacks", views.stats_stacks, name="stats-stacks"),
    path("stats/tags", views.stats_tags, name="stats-tags"),
    path("stats/companies", views.stats_companies, name="stats-companies"),
    path("stats/inventory", views.stats_inventory, name="stats-inventory"),
    path("stats/tracks", views.stats_tracks, name="stats-tracks"),

    # 岗位
    path("jobs", views_jobs.job_list, name="job-list"),
    path("jobs/<path:job_uid>", views_jobs.job_detail, name="job-detail"),

    # 认证
    path("auth/register", auth.register, name="auth-register"),
    path("auth/login", auth.login, name="auth-login"),
    path("auth/logout", auth.logout, name="auth-logout"),
    path("auth/me", auth.me, name="auth-me"),

    # 收藏（/favorites 按 method 分派：GET 列表 / POST 添加）
    path("favorites", favorites.favorite_collection, name="favorite-collection"),
    path("favorites/<path:job_uid>", favorites.favorite_remove, name="favorite-remove"),
]
