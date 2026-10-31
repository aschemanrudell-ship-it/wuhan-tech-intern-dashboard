# -*- coding: utf-8 -*-
"""Django settings — minimal, stage 1.

数据库是外部已存在的 MySQL（端口 3307 的独立实例），表由 sql/schema.sql 建好，
因此**不启用 Django 的 migrate 管理业务表**（业务表是 raw DDL 建的）。
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("JDP_SECRET_KEY", "dev-only-key-not-for-production")
DEBUG = os.environ.get("JDP_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]   # testserver 供 Django 测试客户端使用

INSTALLED_APPS = [
    # 阶段一只有只读 JSON 端点，不需要 auth/contenttypes；
    # 保留 staticfiles 以便将来直接托管看板静态资源。
    "django.contrib.staticfiles",
    "JobDataPlatform.api",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "JobDataPlatform.urls"
WSGI_APPLICATION = "JobDataPlatform.wsgi.application"

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]      # 迁移后的看板在 static/dashboard/
STATIC_ROOT = BASE_DIR / "static_collected"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("JDP_DATABASE", "jobdata"),
        "USER": os.environ.get("JDP_USER", "root"),
        "PASSWORD": os.environ.get("JDP_PASSWORD", ""),
        "HOST": os.environ.get("JDP_HOST", "127.0.0.1"),
        "PORT": os.environ.get("JDP_PORT", "3307"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        "CONN_MAX_AGE": 60,
    }
}

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = False

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"JobDataPlatform": {"handlers": ["console"], "level": "INFO"}},
}
