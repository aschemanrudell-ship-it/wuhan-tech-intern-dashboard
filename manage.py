#!/usr/bin/env python
"""Django 管理入口。"""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "src"))


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "JobDataPlatform.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()