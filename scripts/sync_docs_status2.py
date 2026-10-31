# -*- coding: utf-8 -*-
"""同步 README / HANDOFF / 登记表状态（第二轮）。"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\AIProjects\DeepSeek Harness"

README = [
    ("| Test suite | ✅ **68 tests + 166 subtests pass** |",
     "| Test suite | ✅ **98 tests + 169 subtests pass** |"),
    ("| **Django API** | ✅ **9 endpoints live**: `health` + 6 × `stats/*` + `/jobs` + `/jobs/<uid>` |",
     "| **Django API** | ✅ **16 endpoints**: health + 6×stats + 2×jobs + 4×auth + 3×favorites |"),
    ("| Frontend switch | ❌ not started — plan in `docs/FRONTEND-COMPAT.md` |",
     "| Auth + favorites | ✅ Bearer token, 3 acceptance tests pass — `docs/API-AUTH.md` |\n"
     "| Frontend switch | ❌ not started — plan in `docs/FRONTEND-COMPAT.md` |"),
]

HANDOFF = [
    ("- **68 个测试 + 166 subtests 全过**（scope 11 / summary 14 / stats 28 / jobs 15）",
     "- **98 个测试 + 169 subtests 全过**（scope 11 / summary 14 / stats 28 / jobs 15 / auth+收藏 30）\n"
     "- 认证用 Bearer token（库里只存 SHA-256），收藏三条验收项全部通过：\n"
     "  未登录 401、A 删不掉 B 的收藏、重复收藏幂等"),
    ("- 前端切 API（`renderTable` + 3 个筛选函数）\n"
     "- 登录/收藏的接口（表和约束已建）",
     "- 前端切 API（`renderTable` + 3 个筛选函数）\n"
     "- 令牌刷新、登录限流（当前都没有）"),
    ("Step 4  登录 + 收藏 + 三条权限测试",
     "Step 4  ✅ 已完成：登录 + 收藏 + 三条权限测试（Bearer token）"),
]

REGISTRY = [
    ("**68 passed, 166 subtests passed**", "**98 passed, 169 subtests passed**"),
    ("九个 API 端点", "十六个 API 端点"),
    ("新增 `/api/jobs` 分页筛选与 `/api/jobs/<uid>` 详情（与内存过滤 17 组对拍一致）；前端切 API 未开始",
     "新增 `/api/jobs` 分页筛选（与内存过滤 17 组对拍一致）、`/api/jobs/<uid>` 详情、"
     "4 个 auth 端点与 3 个收藏端点（Bearer token，令牌只存 SHA-256；未登录 401、越权删 0 行、重复收藏幂等三项验收通过）；"
     "前端切 API 未开始"),
]


def patch(path, repls, label):
    text = open(path, encoding="utf-8").read()
    n = 0
    for old, new in repls:
        if old in text:
            text = text.replace(old, new)
            n += 1
        else:
            print(f"  [{label}] 未命中: {old[:52]!r}")
    if n:
        open(path, "w", encoding="utf-8", newline="\n").write(text)
    print(f"  [{label}] {n}/{len(repls)}")


patch(f"{ROOT}\\JobDataPlatform\\README.md", README, "README")
patch(f"{ROOT}\\JobDataPlatform\\docs\\HANDOFF.md", HANDOFF, "HANDOFF")
patch(f"{ROOT}\\PROJECTS.md", REGISTRY, "PROJECTS")
