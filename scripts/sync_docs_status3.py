# -*- coding: utf-8 -*-
"""前端切换完成后的文档同步（第三轮）。"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\AIProjects\DeepSeek Harness\JobDataPlatform"
REPO = r"D:\AIProjects\DeepSeek Harness"


def patch(path, repls, label, append=None):
    text = open(path, encoding="utf-8").read()
    n = 0
    for old, new in repls:
        if old in text:
            text = text.replace(old, new)
            n += 1
        else:
            print(f"  [{label}] 未命中: {old[:46]!r}")
    if append:
        text = text.rstrip() + "\n\n" + append.strip() + "\n"
        n += 1
    if n:
        open(path, "w", encoding="utf-8", newline="\n").write(text)
    print(f"  [{label}] 更新 {n} 处")


GEN_TIME = r"""
---

## 9. 实施结果（Step A 完成）

看板已从 `data/*.json` 切到 `JobDataPlatform/static/dashboard/`，数据源全部走 API。

### 改了什么

| 位置 | 改动 |
| --- | --- |
| `app.js` 的 `FILES` 常量 | 换成 `ENDPOINTS` 表，7 个地址指向 `/api/stats/*` 与 `/api/jobs?legacy=1` |
| `app.js` 的 `load()` | 改为 `Promise.all` 并发请求，组装出与原来**同名的键**（`jobs_master` / `summary` / …） |
| 其余 19 个 `render*` 函数 | **一行未动** |
| `index.html` / `style.css` | **未动** |

### 验证方式与结果

1. 原版（`python -m http.server` 指向旧目录）与新版各截一张整页图：
   **尺寸完全相同 1280×6568**。
2. 提取两页 `document.body.innerText` 逐字符对比：

```
长度: 78232 vs 78232
不同字符位置数: 2
差异区间: 位置 78171..78172
  原版 '06'   新版 '27'      ← 页脚的生成时间戳
```

**78 232 个字符里只有 2 个不同，且是时间戳。** 所有 KPI、图表数据、表格行、结论文案完全一致。

3. 控制台：两版都只有 `favicon.ico 404`，**没有 JS 错误**。

### 当前形态

`/api/jobs?legacy=1` 返回**原始 jobs_master.json 的数组**（3013 条，2.95 MB）。

因为前端的 19 个 render 函数依赖原始字段形状（`j.intern` 布尔、`j.salary.day_low`、
`j.durations` 字符串数组、`j.extra.boss_name`），而库里是规范化列、`durations` 原文也没保存。

**这是有意为之的过渡层**：先把「URL 换掉、视觉零变化」和「字段映射」解耦，
每步都能独立验证。它只在 `DEBUG=1` 下开放，生产环境返回 400。

### 下一步（Step B，未做）

| 项 | 现状 | 目标 |
| --- | --- | --- |
| 表格 | 一次拉 3013 条在内存分页 | 走 `/api/jobs` 分页（已验证 17 组对拍一致） |
| 方向分布图 | 前端从 `interns` 数组现算 | 用 `summary.stack_counts` |
| 薪资直方图 | 现算 | 用 `summary.salary_hist_all` |
| 学历/区域/公司 | 现算 | 用 `summary.by_degree` / `districts` / `top_companies` |
| 每周到岗天数 | 现算 | **缺对应端点**，需新增 `/api/stats/durations` |
| `legacy=1` | 存在 | **删除** |

做完 Step B 才能去掉那 2.95 MB 的全量下载。

### 口径差异（切换时保持原行为，未擅自改）

前端表格用的是 `wuhan.filter(j => j.intern)` = **1139 条**
（**不排除** `is_edu`），而 `summary.json` 与 `/api/jobs` 默认是 **1096 条**。

切换时保留了前端的 1139，因为目标是"视觉与数字不变"。
若要让两边统一，需要改前端筛选条件 —— 这属于产品决策，不是迁移。
"""


patch(f"{ROOT}/docs/FRONTEND-COMPAT.md",
      [],
      "FRONTEND-COMPAT",
      append=GEN_TIME)

patch(f"{ROOT}/README.md", [
    ("| Frontend switch | ❌ not started — plan in `docs/FRONTEND-COMPAT.md` |",
     "| Frontend switch | ✅ **live** — `static/dashboard/` reads the API, text-diff vs original = 2 chars (timestamp) |"),
    ("| **Django API** | ✅ **16 endpoints**: health + 6×stats + 2×jobs + 4×auth + 3×favorites |",
     "| **Django API** | ✅ **16 endpoints**: health + 6×stats + 2×jobs + 4×auth + 3×favorites |\n"
     "| Dashboard | ✅ served at `/static/dashboard/index.html`, data from API |"),
], "README")

patch(f"{ROOT}/docs/HANDOFF.md", [
    ("- 前端切 API（`renderTable` + 3 个筛选函数）\n"
     "- 令牌刷新、登录限流（当前都没有）",
     "- 前端 Step B：表格改服务端分页、图表改吃 stats 聚合、删掉 `legacy=1`\n"
     "- 令牌刷新、登录限流（当前都没有）"),
], "HANDOFF")

patch(f"{REPO}/PROJECTS.md", [
    ("前端切 API 未开始",
     "**看板已切到 API**：`static/dashboard/` 从 `/api/stats/*` 取数，与原页面文本逐字符对比"
     "78232 字符中仅 2 个不同（时间戳），视觉与数字零变化；`legacy=1` 过渡接口仍存在（下一步删除）"),
], "PROJECTS")
