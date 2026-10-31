# 前端兼容方案：静态 JSON → API

> 前提：**视觉完全保留。** `index.html` 的 10 个面板结构、`style.css` 全部规则、ECharts 配色与图表类型都不动。
> 只改数据获取方式。本文按「改什么 / 不改什么 / 怎么验收」组织。

## 1. 现状（来自现有 `dashboard/app.js` 实测）

```js
const FILES = ['jobs_master.json','summary.json','stack_stats.json','tags.json',
               'company_panel.json','inventory.json','tracks.json'];
async function load() {
  // 并发 fetch 7 个静态文件，全部进内存
  const r = await fetch(`data/${f}`, { cache: 'no-store' });
}
```

| 文件 | 体积 | 行数 | 用途 |
| --- | ---: | ---: | --- |
| `jobs_master.json` | 1738 KB | 3013 | 岗位明细表 + 客户端筛选 + 部分图表现算 |
| `summary.json` | 16 KB | — | KPI 卡片、薪资直方图、学历分布、区域 |
| `stack_stats.json` | 17 KB | — | 方向 × 薪资/学历/区域/公司 |
| `tags.json` | 5.4 KB | — | 技能标签词频 |
| `company_panel.json` | 14 KB | — | 企业端画像 4 张图 |
| `inventory.json` | 3.1 KB | — | 平台库存量对比 |
| `tracks.json` | 7.5 KB | — | 方向成长曲线 |

**核心矛盾**：只有 `jobs_master.json` 大到必须服务端分页（1.7 MB / 3013 条），其余 6 个都是小聚合结果。

## 2. 改造策略：分两批，先易后难

### 第一批：6 个聚合文件 → 同形状 API（前端零改动）

| 现文件 | 新端点 | 返回结构 |
| --- | --- | --- |
| `summary.json` | `GET /api/stats/summary` | **完全相同的 JSON** |
| `stack_stats.json` | `GET /api/stats/stacks` | 相同 |
| `tags.json` | `GET /api/stats/tags` | 相同 |
| `company_panel.json` | `GET /api/stats/companies` | 相同 |
| `inventory.json` | `GET /api/stats/inventory` | 相同 |
| `tracks.json` | `GET /api/stats/tracks` | 相同 |

做法：后端用同一套聚合 SQL 生成与现在完全一致的 JSON 形状，前端 `fetch` 的 URL 换掉即可。**图表代码一行不用改。**

好处：可以逐个面板迁移、逐个比对数字，出问题能立刻定位是数据还是接口的错。

### 第二批：`jobs_master.json` → 分页 + 服务端筛选（改动集中在这里）

| # | 现在 | 改成 | 影响的函数 |
| --- | --- | --- | --- |
| 1 | 全量 3013 条进内存 | `GET /api/jobs?page=1&page_size=20` 返回 `{items, total, page, page_size}` | `load()`、`renderTable()` |
| 2 | `applyFilters()` 在内存 filter | 筛选条件变 query 参数，每次变更重新请求 | `applyFilters()`、`initFilters()` |
| 3 | `sortedRows()` 前端排序 | 排序变 `?sort=day_mid&order=desc` | `sortedRows()` |
| 4 | 表格分页靠前端切片 | 用返回的 `total` 算页数，翻页发请求 | `renderTable()` |
| 5 | 无登录 | 收藏需登录，`fetch` 带 token | 新增：登录页 + `authFetch()` |

**唯一需要重写的函数是 `renderTable()` 和筛选相关的 3 个函数**，图表函数不受影响。

## 3. 保留不动的部分（逐项确认）

| 项 | 说明 |
| --- | --- |
| `index.html` 的 10 个 `<section>` | 结构原样 |
| 15 个 ECharts 容器 id | `chartStack` / `chartPlatform` / `chartTracks` / `chartTracksGrowth` / `chartInventory` / `chartSalaryDist` / `chartSalaryStack` / `chartDegree` / `chartWeeks` / `chartCompanies` / `chartTags` / `chartCompanyOpen` / `chartCompanySize` / `chartCompanyStage` / `chartCompanyIndustry` |
| 6 个 HTML 表格 | `salaryTable` / `durationTable` / `companyTable` / `inventoryTable` / `tracksTable` / `jobTable` |
| `style.css` 全部 | 不动 |
| `vendor/echarts.min.js` + CDN 回退 | 不动 |
| `renderInsights()` 的结论文案 | 不动（但结论里的数字要跟着新口径复核，见 §5） |
| 响应式 `resize` 处理 | 不动 |

## 4. 数据形状兼容约定

分页接口返回：

```json
{
  "items": [ { "job_uid": "zl-...", "title": "...", "company": "...", "day_mid": 175.0, ... } ],
  "total": 1096,
  "page": 1,
  "page_size": 20,
  "applied_filters": { "stacks": ["Python"], "degree": "本科" }
}
```

字段名**沿用现有 `jobs_master.json` 的键名**（`job_uid` 除外，它是新主键；旧代码用的 `url`/`title`/`company` 等保持不变），这样 `renderTable()` 的行渲染模板几乎不用改。

## 5. 必须同步修正的地方（容易被忽略）

现有前端有些数字是用**旧口径**算的，切 API 时必须一起改，否则前后矛盾：

| 位置 | 现在 | 应改为 |
| --- | --- | --- |
| `renderKpis()` 的 Python/Java 薪资 | 用内存里 `day_mid` 现算 | 调 `/api/stats/salary?scope=C`，用 C 层口径 |
| `isScope()` 判定 | `salaryText` 含"元/天" 或 "K"+标题含实习 | 直接用 `intern_daily_sample && title_has_intern` |
| `renderInsights()` 里"Python 中位 175" | 硬编码风险 | 从 API 返回值渲染，不写死 |

> 这一条是**真实风险点**：前端现在自己算 `stats()` 分位数，后端也会算，两边口径不一致就会出现"图表和表格对不上"。**约定：所有分位数只由后端算，前端只渲染。**

## 6. 迁移顺序（每步都可验收）

```
Step 1  /api/stats/summary       → 换 URL，比对 KPI 卡片 6 个数字
Step 2  /api/stats/stacks        → 比对方向条形图 15 个值
Step 3  /api/stats/{tags,companies,inventory,tracks} → 逐面板比对
Step 4  /api/jobs 分页           → 表格能用，total 与手工 SQL 一致
Step 5  服务端筛选/排序          → 筛选结果条数 === SQL 计数
Step 6  登录 + 收藏              → 权限三连测（见 QUERIES.md Q7）
```

## 7. 验收标准（可执行）

| # | 检查 | 通过标准 |
| --- | --- | --- |
| 1 | 同一筛选条件 | 前端显示条数 == API `total` == 手工 SQL `COUNT(*)` |
| 2 | 方向条形图 | 15 个值与 `docs/QUERIES.md` Q3 实测表逐项相同 |
| 3 | Python 薪资中位 | 页面显示 == SQL 算出的 175.0 |
| 4 | 视觉回归 | 10 个面板截图与改造前逐像素对比（字体/配色/布局不变） |
| 5 | 无登录访问收藏 | 返回 401 |
| 6 | A 用户删 B 用户收藏 | 0 行受影响，B 的收藏仍在 |

## 8. 过渡期兜底

新增 `GET /api/jobs?legacy=1`，返回全量 3013 条（仅开发环境开启）。
用途：迁移过程中某个面板还没切完时继续可用，也方便"新旧数字逐项对比"。
**上线前必须关闭此开关**——否则等于没做分页。

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
