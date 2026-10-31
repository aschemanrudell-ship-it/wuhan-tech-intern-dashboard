# -*- coding: utf-8 -*-
"""同步 README / HANDOFF / 登记表的状态（UTF-8 安全，替代 PowerShell 替换）。"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"D:\AIProjects\DeepSeek Harness"

README_REPLACEMENTS = [
    ("| Paged `/api/jobs` | ❌ not started |",
     "| Paged `/api/jobs` | ✅ server-side filter + sort + paging — `docs/API-JOBS.md` |"),
    ("| Test suite | ✅ **53 tests + 149 subtests pass** |",
     "| Test suite | ✅ **68 tests + 166 subtests pass** |"),
    ("| **Django API** | ✅ **7 endpoints live**: `health` + 6 × `stats/*` |",
     "| **Django API** | ✅ **9 endpoints live**: `health` + 6 × `stats/*` + `/jobs` + `/jobs/<uid>` |"),
]

HANDOFF_REPLACEMENTS = [
    ("- 25 个测试全过（`tests/test_scope.py` 11 + `tests/test_api_summary.py` 14）",
     "- **9 个 API 端点全部跑通**，包含 `/api/jobs` 分页/筛选/排序与详情\n"
     "- **68 个测试 + 166 subtests 全过**（scope 11 / summary 14 / stats 28 / jobs 15）\n"
     "- `/api/jobs` 与内存过滤**逐条对拍**：17 种筛选组合的结果集完全相同"),
    ("- 其余 5 个 stats 端点（stacks / tags / companies / inventory / tracks）\n"
     "- 分页 `/api/jobs` 与前端切 API",
     "- 前端切 API（`renderTable` + 3 个筛选函数）\n"
     "- 登录/收藏的接口（表和约束已建）"),
    ("Step 2  其余 5 个 stats 端点（stacks / tags / companies / inventory / tracks，返回同形状）\n"
     "Step 3  /api/jobs 分页 + 服务端筛选（前端改 3 个函数，见 FRONTEND-COMPAT.md）",
     "Step 2  ✅ 已完成：其余 5 个 stats 端点\n"
     "Step 3  ✅ 已完成：/api/jobs 分页 + 服务端筛选（17 组对拍通过）；剩前端改 3 个函数"),
]

REGISTRY_REPLACEMENTS = [
    ("七个 API 端点", "九个 API 端点"),
    ("**53 passed, 149 subtests passed**", "**68 passed, 166 subtests passed**"),
    ("前端切 API 未开始", "新增 `/api/jobs` 分页筛选与 `/api/jobs/<uid>` 详情（与内存过滤 17 组对拍一致）；前端切 API 未开始"),
]


def patch(path, repls, label):
    text = open(path, encoding="utf-8").read()
    n = 0
    for old, new in repls:
        if old in text:
            text = text.replace(old, new)
            n += 1
        else:
            print(f"  [{label}] 未命中: {old[:48]!r}")
    if n:
        open(path, "w", encoding="utf-8", newline="\n").write(text)
    print(f"  [{label}] 替换 {n}/{len(repls)}")


print("更新文件:")
patch(f"{ROOT}\\JobDataPlatform\\README.md", README_REPLACEMENTS, "README")
patch(f"{ROOT}\\JobDataPlatform\\docs\\HANDOFF.md", HANDOFF_REPLACEMENTS, "HANDOFF")
patch(f"{ROOT}\\PROJECTS.md", REGISTRY_REPLACEMENTS, "PROJECTS")
