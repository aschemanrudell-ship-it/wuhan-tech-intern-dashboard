# -*- coding: utf-8 -*-
"""更新 PROJECTS.md 里 JobDataPlatform 一行的状态（UTF-8 安全）。

用 PowerShell 的 Get-Content/Set-Content 会按 ANSI 读取，中文会坏；这里统一用 UTF-8。
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

PATH = r"D:\AIProjects\DeepSeek Harness\PROJECTS.md"

REPLACEMENTS = [
    ("Django 未开始", "Django 6.1.2 已跑通两个端点"),
    ("阶段一设计验证完成，代码切片未开始",
     "阶段一骨架完成：设计 + 建表 + 导入 + 两个 API 端点"),
    ("Django API 与前端切 API 均未开始",
     "**Django API 已跑通**：`/api/health` + `/api/stats/summary`（31 键、真实 HTTP 200 / 11 564 字节），"
     "与源 summary.json 逐字段比对通过（8 类完全一致、5 处差异全部定位原因）；前端切 API 未开始"),
    ("`python -m unittest discover -s tests -v`（**10 tests OK**）",
     "`python -m pytest -q`（**25 passed, 11 subtests passed**）"),
    ("索引候选仅列出未实测", "索引 C3 实测无效已删除"),
]

text = open(PATH, encoding="utf-8").read()
target = None
for line in text.split("\n"):
    if line.startswith("| JobDataPlatform |"):
        target = line
        break

if target is None:
    print("!! 未找到 JobDataPlatform 行")
    sys.exit(1)

new_line = target
for old, new in REPLACEMENTS:
    if old not in new_line:
        print(f"!! 片段未命中: {old[:40]}")
        continue
    new_line = new_line.replace(old, new)

if new_line == target:
    print("无变化（可能已更新过）")
    sys.exit(0)

text = text.replace(target, new_line, 1)
open(PATH, "w", encoding="utf-8", newline="\n").write(text)

print("已更新，新行长度:", len(new_line))
for k in ["Django 6.1.2", "/api/stats/summary", "25 passed", "C3 实测无效"]:
    print(f"  {k:24s}{'✓' if k in new_line else '✗'}")
