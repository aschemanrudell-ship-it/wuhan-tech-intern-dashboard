# summary.json → SQL 映射表

> 目标：`GET /api/stats/summary` 返回与 `dashboard/data/summary.json` **相同的键结构**，前端零改动。
> 验证方式：`tests/test_api_summary.py`（14 项，其中 8 项断言完全一致、6 项断言差异在白名单内）。
> 复现：`python scripts/compare_to_source.py`

---

## 1. 29 个源字段的来源

| # | 源字段 | 来源 | 一致性 |
| --- | --- | --- | --- |
| 1 | `total_rows` | `SELECT COUNT(*) FROM jobs` | ✅ 完全一致 |
| 2 | `wuhan_rows` | `WHERE is_wuhan=1` | ✅ |
| 3 | `wuhan_interns` | `is_wuhan=1 AND is_intern=1 AND is_edu_excluded=0` | ✅ 1096 |
| 4 | `wuhan_tech_interns` | 上式 + `EXISTS(job_stacks)` | ✅ 850 |
| 5 | `wuhan_nontech_interns` | 1096 − 850 | ✅ 246 |
| 6 | `intern_salary_known` | `salary_scope.daily + salary_scope.monthly_k` | ⚠️ 623 vs 618（见 §2.1） |
| 7 | `salary_scope` | 按 `salary_unit` 分组计数 | ⚠️ `monthly_k` 211 vs 206 |
| 8 | `salary_by_source` | 4 个来源 × 4 个计数 | ⚠️ 猎聘 `monthly_k` 5 vs 0（见 §2.1） |
| 9 | `salary_stats.python` | `intern_daily_sample=1` + 方向 Python | ⚠️ n 75 vs 74（见 §2.2） |
| 10 | `salary_stats.java` | 同上，方向 Java | ✅ **完全一致** |
| 11 | `salary_stats.all_interns` | `intern_daily_sample=1`（不 JOIN 方向） | ⚠️ n 504 vs 499（见 §2.3） |
| 12 | `python.count` | `job_stacks` 命中 Python | ✅ 154 |
| 13 | `java.count` | 命中 Java | ✅ 175 |
| 14 | `both` | 同时命中 Python 与 Java | ✅ 54 |
| 15 | `by_source` | 实习口径按来源分组 | ✅ 完全一致 |
| 16 | `by_degree` | 实习口径按学历分组 | ✅ 完全一致 |
| 17 | `stack_counts` | 15 个方向的计数 | ✅ **完全一致** |
| 18 | `salary_hist_all` | 5 个薪资区间桶 | ⚠️ 2 个桶差（见 §2.1） |
| 19 | `salary_hist_by_stack` | Python/Java/算法/前端 × 5 桶 | ⚠️ 同上 |
| 20 | `company_panel.profiles_collected` | `companies` 里 `open_jobs` 或 `boss_count` 非空 | ⚠️ 82 vs 84（见 §2.4） |
| 21 | `company_panel.companies_hiring_interns` | BOSS 来源去重公司数 | ✅ 608 |
| 22 | `company_panel.total_open_jobs` | 去重公司 `open_jobs` 求和 | ⚠️ **源有 bug**（见 §2.5） |
| 23 | `top_tags` | `job_tags` 频次 | ⚠️ 见 §2.6 |
| 24 | `top_skills` | 同 `top_tags`（源里两者口径不同，本库先合并） | ⚠️ 见 §2.6 |
| 25 | `top_companies` | `companies` 按岗位数 | ✅ |
| 26 | `top_industries` | `jobs.industry` 频次 | 新增列才支持（见 §3） |
| 27 | `districts` | 实习口径按区 | ✅ 完全一致 |
| 28 | `generated_from` | 全量按来源 | ✅ 完全一致 |
| 29 | `boss_meta` / `boss_keywords_collected` / `boss_coverage_note` / `platform_inventory` / `data_notes` | **fixtures/collection_meta.json**（采集元数据，非 SQL） | ✅ 原样返回 |

新增字段（源里没有，本库补充）：

| 字段 | 含义 |
| --- | --- |
| `daily_sample_n` | `intern_daily_sample=1` 的行数（真正进薪资统计的样本量） |
| `scope_notes` | 返回口径的自描述，避免调用方猜数字怎么来的 |

---

## 2. 已知差异（全部已定位原因）

### 2.1 小写 `k` 导致的 5 行差异（源脚本 bug）

源脚本 `aggregate.py` 用 **大小写敏感** 的 `"K" in salary_raw` 判断月薪：
```python
is_monthly = "K" in raw            # 漏掉 "3-5k"、"3-6k"、"4-7k"、"4-8k"
```
实测这 5 行全是小写 `k`，其中 **5 行里 4 行来自猎聘**（这就是 `salary_by_source.猎聘.monthly_k` 源=0 而本库=5 的原因）。

| 指标 | 源 | 本库 | 差 |
| --- | ---: | ---: | ---: |
| `salary_scope.monthly_k` | 206 | 211 | +5 |
| `intern_salary_known` | 618 | 623 | +5 |
| `daily_sample_n` | 499 | 504 | +5 |
| `salary_hist_all` 的 `150-200` | 147 | 148 | +1 |
| `salary_hist_all` 的 `200-300` | 102 | 106 | +4 |

本库用 `[kK]` 修正，**多出的 5 行是源脚本漏算的真实数据**，不是本库多算。

### 2.2 Python 薪资样本 75 vs 74

5 行小写 `k` 里有 1 行是 Python 岗。分位数完全不受影响：

| 指标 | 源 | 本库 |
| --- | ---: | ---: |
| n | 74 | 75 |
| min / p25 / median / p75 / max | 75 / 140 / **175** / 250 / 1494.2 | 完全相同 |
| mean | 238.3 | 237.6（多 1 个低值样本拉低） |

### 2.3 全量实习样本 504 vs 499

同上，样本从 499 增到 504，中位数从 160.9 变 165.0、p75 从 220.0 变 223.75。**这是数据修正后的结果，不是口径漂移。**

### 2.4 `profiles_collected` 82 vs 84

- 源 84 = `fetch_boss_companies.py` 抓取到的公司主页数量
- 本库 82 = 能从 `companies` 表反查出画像字段（`open_jobs` / `boss_count` 非空）的公司数
- **差的 2 家**：画像存在，但没有任何岗位关联到它们，导入时未写入 `companies`
- 处理：接受 82；若要精确还原 84，需要把公司档案单独入库（阶段二）

### 2.5 `total_open_jobs`：源有 bug，本库正确

| 来源 | 值 | 说明 |
| --- | ---: | --- |
| `summary.json` | 167169 | `aggregate.py:917` 对**每条岗位**累加 `company_open_jobs`，同一公司出现 N 次就加 N 次 |
| `company_panel.json` | 22953 | 对**去重后的公司**求和 —— 正确值 |
| 本库 API | **22953** | 采用正确口径 |

**源项目自己的两个文件互相矛盾**，本库选了对的那个。

### 2.6 `top_skills` 与 `top_tags` 未拆分

源里两者口径不同：`tags` 含非技能噪声（如"本科""不接受居家办公"），`skills` 已过滤。
本库暂时返回同一个值。**要拆分需要加噪声词表过滤，阶段一未做。**

---

## 3. 设计变更记录（验证中发现的问题）

| 问题 | 发现方式 | 处理 |
| --- | --- | --- |
| `jobs` 表漏了 `industry` 列 | Q 比对时 `Unknown column 'j.industry'` | 加列 + 改导入 + 重建表重导，`top_industries` 才可用 |
| `salary_stats(all_interns)` 少算 92 行 | 算出 412，源是 499 | 根因：`stack_name=None` 时仍 JOIN `job_stacks`，把无技术栈岗位排除了。改为不 JOIN 后 = 504 |
| 分位数算法不一致 | `p75` 算出 247.5，源是 250 | 源用 `statistics.quantiles(n=4)` 的 **exclusive** 法（位置 `(n+1)p`），不是 numpy 的 linear（`(n-1)p`） |
| `intern_salary_known` 语义搞错 | 一度返回 504（样本量） | 源里它 = `daily + monthly_k`（有明码薪资字段），**不是**可统计样本；样本另设 `daily_sample_n` |

---

## 4. 端点

| 端点 | 用途 | 响应 |
| --- | --- | --- |
| `GET /api/health` | 连通性与行数自检 | `{database, jobs, companies, job_stacks, job_descriptions, mysql_version}` |
| `GET /api/stats/summary` | 替代 `data/summary.json` | 31 个顶层键（29 源 + `daily_sample_n` + `scope_notes`） |

启动：

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
# 然后
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/stats/summary
```
