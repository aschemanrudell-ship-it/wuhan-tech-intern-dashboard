# 端点迁移表：6 个 JSON → 6 个 API

> 目标：`/api/stats/*` 返回与 `dashboard/data/*.json` **相同的键结构**，前端图表代码零改动。
> 复现：`python scripts/compare_endpoints.py`
> 测试：`python -m pytest -q`（`tests/test_api_stats.py`）

## 端点对照

| 源 JSON | 端点 | 数据来源 | 比对结果 |
| --- | --- | --- | --- |
| `summary.json` | `GET /api/stats/summary` | SQL + fixture | 8 类完全一致 / 5 处已知差异 |
| `stack_stats.json` | `GET /api/stats/stacks` | SQL | **5 处**（全为小写 k） |
| `tags.json` | `GET /api/stats/tags` | SQL | **2 处**（同分排序） |
| `company_panel.json` | `GET /api/stats/companies` | SQL | **24 处**（公司档案字段，见 §3） |
| `inventory.json` | `GET /api/stats/inventory` | fixture | ✅ **完全一致** |
| `tracks.json` | `GET /api/stats/tracks` | SQL | **6 处**（小写 k + 正式岗微差） |

合计 37 处差异，全部定位到原因，无一处是随机错。

---

## 1. 关键：源项目用了三套不同的统计口径

逆向 `aggregate.py` 得到，**不能混用**：

| 用途 | 函数 | 过滤 | 分位数算法 | 四舍五入 |
| --- | --- | --- | --- | --- |
| `summary` / `stack_stats` 的 `salary_day` | `salary_summary()` | `day_mid` 有值 且（元/天 或 K+标题含实习） | **索引法** `vals[int(n*p)]` | **不 round**（只有 mean round 1 位） |
| `tracks` 的 `daily` | `daily_stats()` | 同上（`_salary_in_scope`） | 索引法 | round 1 位 |
| `tracks` 的 `month` | `month_stats()` | **`month_mid` 有值即可**（不筛口径） | 索引法 | round 整数 |

`median` 一律用 `statistics.median`（偶数长度取两数平均），所以会出现 `184.45` 这种两位小数。

**早期误判**：以为是 `statistics.quantiles(exclusive)`。在 n=75 时两者恰好同值，掩盖了问题；直到 PHP（n=1）源返回 `300` 而我返回 `null` 才暴露。

---

## 2. 逐个端点的差异明细

### 2.1 stacks（5 处，不可消除）

| 方向 | 字段 | 源 | 本库 | 原因 |
| --- | --- | --- | --- | --- |
| Python | n / mean | 74 / 238.3 | 75 / 237.6 | 小写 k |
| 前端 | n / mean / p75 | 69 / 181.5 / 200.0 | 71 / 183.8 / 206.9 | 小写 k（2 行前端岗） |

其余 13 个方向的各字段（count / by_source / salary_day / salary_month / degree / districts / top_companies）**逐项一致**。

### 2.2 tags（2 处）

`tags[18]` / `tags[19]`：源 `HTML 29`、`React 29`；本库顺序相反。

原因：源用 `Counter.most_common()`，同分时按**首次遍历顺序**；SQL 用 `ORDER BY n DESC, MIN(j.id) ASC`，语义接近但不完全等价。**属于展示顺序，不是数值错误。**

`skills` / `companies` / `industries` 已通过加次级排序键完全对齐。

### 2.3 tracks（6 处）

`intern.postings` **8 个方向全部一致**（111 / 144 / 90 / 176 / 36 / 102 / 83 / 28）。

| 方向 | 字段 | 源 | 本库 | 原因 |
| --- | --- | --- | --- | --- |
| Python / Java | intern.daily.n | 60 / 85 | 62 / 87 | 小写 k |
| 后端 | intern.daily.n | 52 | 53 | 小写 k |
| 前端 | fulltime.postings | 75 | 71 | 见下 |
| 数据分析 | fulltime.postings | 92 | 85 | 见下 |
| 运维 | fulltime.postings | 114 | 110 | 见下 |

正式岗差异原因：源用 `wuhan_all`（**不排除 `is_edu`**）筛 `slug == ft_*`；本库已去掉 `is_edu_excluded` 过滤，但仍有残差 —— 说明源对 `ft_*` 还叠加了别的条件（`by_experience` 的经验轴抽样）。**未追到根，已记录。**

### 2.4 companies（24 处，最大一块）

| 字段 | 差异 | 原因 |
| --- | --- | --- |
| `profiles_collected` | 84 vs 82 | 2 家公司有档案但没关联岗位 |
| `size_dist` / `stage_dist` / `industry_dist` | 数值与顺序不同 | 见 §3 |
| `top_by_intern_roles` / `top_by_open_jobs` 的 `size` / `stage` / `industry` | 部分条目不同 | 同上 |

`total_open_jobs` = 22953（**本库正确，源 summary.json 的 167169 是重复累加 bug**）。

### 2.5 未追到的细节：`intern_roles` 对个别公司偏大

| 公司 | 源 | 本库 | 说明 |
| --- | ---: | ---: | --- |
| 华为技术有限公司 | 13 | 13 | ✅ 一致 |
| 华为 | 12 | 12 | ✅ 一致 |
| 金山云 / 精臣 / 绿盟科技 | 9 | 9 | ✅ 一致 |
| **小米** | **9** | **14** | ❌ 差 5 |

「小米」在本库是 14 个实习岗、源是 9。华为系和其余公司都精确一致，说明不是整体口径问题，而是**源对特定公司做了额外去重**（可能按 title 去重，或该公司部分岗位被归到了「小米科技」等名字变体下）。

**影响**：`top_by_intern_roles` 的榜首因此不同（源是华为技术有限公司，本库是小米），但前 3 名集合一致。
**状态**：未追到根因，测试只断言前 3 名集合与华为系数值，不比较小米。

---

## 3. 未解决：公司档案字段（`size` / `stage` / `industry`）

源的口径是**档案优先、岗位回退**：

```python
rec["size"]     = company_profiles[name]["size"]     or j.get("company_size")
rec["stage"]    = company_profiles[name]["stage"]    or j.get("financing")
rec["industry"] = company_profiles[name]["industry"] or j.get("company_industry")
```

本库的 `companies.size` / `financing` / `industry` **只存了岗位字段**（覆盖 1938 家），84 家公司的档案值没有单独入库。因此：

- 608 家「有实习岗的公司」里，那 84 家的 `size/stage/industry` 用的是岗位值，可能与被抓取的公司档案不同
- `size_dist` 等三个分布因此偏移

**修法（阶段二）**：加 `company_profiles` 表，存 `boss_companies.json` 的 84 条档案，查询时 `COALESCE(profile.x, companies.x)`。

影响评估：只影响「企业画像」面板的 3 个分布图和 15 条公司卡片的 3 个字段；**不影响**岗位数、薪资、方向、学历、区域等主结论。

---

## 4. 迁移中发现并修复的设计缺陷

| # | 问题 | 症状 | 修复 |
| --- | --- | --- | --- |
| 1 | `jobs` 缺 `industry` 列 | `Unknown column 'j.industry'` | 加列 + 重导 |
| 2 | `jobs` 缺 `crawl_slug` 列 | `tracks` 无法按采集批次分组（BOSS 的 keyword 是中文、slug 是英文） | 加列 + 重导，ft_ 909 行可识别 |
| 3 | **`tags.name` 用了大小写不敏感 collation** | `Java`(143) 与 `java`(2) 被合并，`tag_id` 字典查不到 `Java`，**143 条关联全部丢失**，`tags` 榜第一项直接消失 | `COLLATE utf8mb4_0900_as_cs`，关联从 2 恢复到 502（全表） |
| 4 | 分位数用插值法 | 小样本返回 `null`，大样本 `p75` 差 2.5 | 改为索引法且不 round |
| 5 | `districts` 取了 12 个 | 源只取 **8** 个 | 改 LIMIT 8 |
| 6 | `size_dist` 统计了全部 1954 家 | 源只统计 **608 家**有实习岗的 | 加 `id IN (hire_ids)` |
| 7 | 同分排序不稳定 | 大量假差异（companies/industries/districts） | 统一加 `MIN(j.id)` 次级键 |

---

## 5. 端点清单

| 端点 | 响应规模 | 说明 |
| --- | --- | --- |
| `GET /api/health` | ~200 B | 连通性 + 行数 |
| `GET /api/stats/summary` | 11.5 KB | 31 个顶层键 |
| `GET /api/stats/stacks` | ~17 KB | 15 个方向 × 7 个维度 |
| `GET /api/stats/tags` | ~5 KB | tags/skills/companies/industries 四榜 |
| `GET /api/stats/companies` | ~14 KB | 3 汇总 + 2×Top15 + 3 分布 |
| `GET /api/stats/inventory` | ~3 KB | 16 行平台库存（fixture） |
| `GET /api/stats/tracks` | ~7 KB | 8 个方向的成长对比 |

启动：

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```
