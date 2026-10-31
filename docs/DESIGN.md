# 招聘数据服务平台 · 阶段一设计

> 范围：数据接入 → MySQL → 服务化（查询 / 统计 / 收藏）→ 测试 → 部署。
> 不含检索、不含大模型。所有数字来自 `docs/FIELD-AUDIT.md`（`scripts/audit_fields.py` 实测）。
> 快照：2026-10-12，3013 行，31 字段。

---

## 1. 数据审计结论（决定后面所有设计的事实）

| 事实 | 数据 | 影响 |
| --- | --- | --- |
| `job_id` 全局唯一 | 3013 行 / 3013 distinct，0 重复 | 可直接作为业务幂等键 |
| `job_id` 最大长度 92，猎聘的含中文与管道符 | 如 `lp-Python\|Python开发工程师 【 上海-青浦区 】\|某知名公司` | 列宽要留 200+，不能当 URL 参数裸传 |
| `url` 有 74 行为空 | 集中在猎聘 | 详情跳转要允许 NULL |
| `company` 有 86 行为空 | 全部来自 BOSS | `(title, company)` 不能作唯一键 |
| `(title, company)` 重复 66 组 / 162 行 | 同源重复 64 组、跨源重复仅 **2 组** | 跨源去重收益极小，见 §3 |
| `publish_time` 缺失 94.3% | 只有 172 行（全部智联） | 时间维度极稀疏，排序要有兜底 |
| `durations` 缺失 96.2% | 仅 113 行有值 | 但 `labels` 能补一部分，合并后 20.1% 可解析 |
| `labels` 缺失 21.9% | 2352 行有值，132 种取值 | 含「5天/周」「3个月」「本科」等，是实习条件的主要来源 |
| JD 正文覆盖 5.2% | 156/3013，全部来自智联 | 单独建表，不拖累主表 |
| 薪资单位有 9 种形态 | K/月 1163、缺失 840、元/天 561、K/月(倍薪) 306、元/月区间 92、万/月 28、面议 17… | 必须有显式单位字段，不能只存数字 |
| `company_industry` / `bosses` / `open_jobs` 缺失 88–90% | 只有 358 行 | 放公司表，允许 NULL，不参与核心筛选 |
| `degree` 有脏值 | `经验不限` 4 行、`初中及以下` 2 行 | 导入时要清洗或标脏 |

---

## 2. 唯一标识

### 2.1 用 `job_id` 作为业务唯一键

`jobs.job_uid VARCHAR(200) NOT NULL UNIQUE`，直接存原始 `job_id`。

理由：实测 3013 行无重复，且已带来源前缀（`zl-` / `lp-` / `boss-`），天然跨源不冲突。

**另外单独存 `source` 和 `source_job_id`**：把前缀剥掉存原始 ID，方便将来按平台重建 URL 或补抓详情页。

### 2.2 代理主键

`jobs.id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY`。

理由：`job_uid` 最长 92 字符且含中文，作为聚簇索引主键会让所有二级索引都背上 92 字节的键；自增 BIGINT 让 InnoDB 顺序写入、二级索引轻量。

---

## 3. 幂等导入 vs 跨源去重（两件不同的事）

### 3.1 重复导入幂等（必须做）

| 项 | 设计 |
| --- | --- |
| 幂等键 | `job_uid` |
| 写入方式 | `INSERT ... ON DUPLICATE KEY UPDATE`（或先 SELECT 再 UPDATE） |
| 判定标准 | **同一份快照导入两次，`SELECT COUNT(*)` 不变，`updated_at` 变化** |
| 需要更新哪些列 | 除 `created_at` 外的全部业务列（薪资/学历/标签可能变） |
| 需要保留哪些列 | `created_at`（首次入库时间）、`first_seen_at` |
| 快照批次 | 建 `import_batch` 表（batch_id、来源文件、行数、sha256、开始/结束时间），`jobs.batch_id` 记录最后一次写入批次 |

**验收**：同一文件连导两次 → 行数 3013 → 3013；`updated_at` 第二次批量刷新；`created_at` 不变。

### 3.2 跨源去重（**不做物理合并**）

实测只有 **2 组**跨源重复：

```
AI算法实习生（CV模型训练与智能算法方向） | 中望软件     → 智联 zl-40891899314 + BOSS boss-eb5be...
临床统计分析实习生 | 宏韧医药                     → 智联 zl-40535986714 + BOSS boss-bb733...
```

**设计：不合并，只打标记。**

- 加 `dup_group_key VARCHAR(200) NULL`，导入时用 `(title, company)` 归一化后算哈希写入
- 查询时默认不过滤，前端可选「合并同岗」开关
- 理由：两个来源的薪资、学历、到岗要求可能不同，物理合并会丢信息；且只有 2 组，收益远小于风险

> 另一类重复是**同源同名**（64 组 / 158 行），主要是猎聘的「某知名公司」不同城市同名岗位、以及智联同一岗位重复发布。这类用 `job_uid` 判不了（job_id 不同），但也不应合并——它们是不同城市的真实岗位。**处理方式：只在展示层标注「同名岗位 N 个」，不做删除。**

---

## 4. 字段取舍

### 4.1 保留（含低覆盖）

| 字段 | 缺失率 | 为什么留 | 落在哪 |
| --- | --- | --- | --- |
| `publish_time` | 94.3% | **用户明确要求**；唯一时间维度，172 行可做数据新鲜度分析 | `jobs.publish_time DATETIME NULL` |
| `source` | 0% | **用户明确要求**；所有按来源的统计都依赖它 | `jobs.source` + `sources` 字典表 |
| JD 正文 | 94.8% 缺 | **用户明确要求**；阶段二的检索依赖它 | 独立表 `job_descriptions` |
| `durations` | 96.2% | 实习条件核心，且 `labels` 能补 | 拆成 `weekly_days` / `intern_months` 两列 |
| `labels` | 21.9% | 实习条件主要来源 | `job_labels` 关联表 |
| `company_industry` / `bosses` / `open_jobs` | 88–90% | 公司画像，展示用 | `companies` 表，允许 NULL |
| `extra.boss_name` / `boss_title` / `welfare` | 47% | 招聘者信息 + 福利，展示用 | `jobs` / `job_welfare` |

### 4.2 拆分（原文进 JSON/关联，不硬塞一列）

| 原字段 | 拆成 |
| --- | --- |
| `salary_raw` + `salary`（嵌套） | `salary_raw` 原文 + `salary_unit` 枚举 + `day_low/high/mid` + `month_low/high/mid`（见 §5） |
| `durations` / `labels` 里的「5天/周」「3个月」 | `jobs.weekly_days TINYINT NULL`、`jobs.intern_months TINYINT NULL`（正则解析，解析不出为 NULL） |
| `stacks`（数组） | `stacks` 字典表 + `job_stacks` 关联表 |
| `tags`（数组，1762 种） | `tags` 字典表 + `job_tags` 关联表 |
| `welfare`（数组） | `job_welfare` 关联表（或 JSON 列，见 §7 权衡） |

### 4.3 丢弃

| 字段 | 理由 |
| --- | --- |
| `salary.note` | 与 `salary_unit` 重复 |
| `extra.origin` | 采集内部标记，非业务数据（若将来做数据血缘，放 `import_batch`） |
| `page` / `pageSize` 类采集痕迹 | 无业务价值 |
| `is_edu` | 导入时已用于过滤，落库后作为 `is_edu_excluded` 布尔保留即可，不参与查询 |

> `keyword` / `slug` 实测是同一套值（42 种，`(keyword, slug)` 组合数 = 42），**只保留一个** `crawl_keyword`，用于回溯「这条数据是哪个搜索词召回的」。

---

## 5. 薪资单位模型

### 5.1 枚举

| `salary_unit` | 实测行数 | 语义 | day_mid 可算 |
| --- | ---: | --- | --- |
| `DAY` | 561 | 元/天 | ✅ 直接 |
| `K_MONTH` | 1163 | K/月 | ✅ ÷21.75 |
| `K_MONTH_X` | 306 | K/月·N薪 | ✅ ÷21.75（倍薪只影响年包，不影响月薪） |
| `MONTH_YUAN` | 94 | 元/月（区间 92 + 单值 2） | ⚠️ 只有 82 行算出，其余因区间异常 |
| `WAN_MONTH` | 28 | 万/月 | ❌ 解析器未支持 |
| `NEGOTIABLE` | 17 | 面议/保密 | ❌ |
| `UNKNOWN` | 4 | 未识别 | ❌ |
| `MISSING` | 840 | 字段为空 | ❌ |

**合计校验：561+1163+306+94+28+17+4+840 = 3013 ✅**

### 5.2 关键设计：口径分三层，不能只分「有/无日薪」

`day_mid` 有值的行 2112（29.9% 缺失），但这 2112 里混着「元/月」「万/月」口径折算出来的值，也混着社招高薪岗。**建库后实测**得出必须分三层：

| 层 | 条件 | 实测行数 | 说明 |
| --- | --- | ---: | --- |
| A 宽口径实习 | `is_intern=1` | 1096 | 源数据判定含"应届/校招"，其中 **331 行标题不含"实习"** |
| B 明确实习 | A + `title_has_intern=1` | 765 | 只保留标题写明实习的 |
| **C 日薪样本** | B + `intern_daily_sample=1` | **484** | 元/天 392 + 含实习 K/月 92 |

落库时做成两列生成列：

```sql
title_has_intern    TINYINT(1) NOT NULL          -- 普通列，导入时写入
day_mid_comparable  AS (salary_unit IN ('DAY','K_MONTH','K_MONTH_X')) STORED       -- 宽：623
intern_daily_sample AS (unit IN ('DAY','K_MONTH','K_MONTH_X')
                        AND (unit='DAY' OR title_has_intern=1)) STORED              -- 504
```

统计实习薪资时用 **B ∩ C = 484 行**（`title_has_intern=1 AND intern_daily_sample=1`）。

**验证结果**（`docs/QUERIES.md` Q4）：用 C 层算出 Python n=74 / 中位 175.0，与源项目 `summary.json` 完全一致；换成宽口径会变成 n=92 / 中位 202.5，虚高 27.5 元/天。

### 5.3 C 层的已知缺陷（**未解决**）

C 层 484 行里有 8 行月薪 > 10000，实为异地/过期/校招/非技术岗（明细见 `docs/QUERIES.md` 口径章节）。
「标题含实习」这个单一判据不够，还需四类排除：异地、过期届别、非技术岗、校招。**当前没做。**

后果：按 `day_mid DESC` 排序时，第一屏必然被这 8 行占据。Q1 的排序必须特殊处理（见 `docs/QUERIES.md` Q1）。

### 5.4 折算常数

`1 月 = 21.75 工作日`（沿用源项目），存为应用层常量，不写死在 SQL 里。

---

## 6. 真实查询场景（表结构从这 8 条推出来）

> 每条都写清：谁触发、过滤什么、排什么、要多少行。**这是推导表的唯一依据。**

| # | 场景 | 过滤 | 排序 | 分页 | 涉及表 |
| --- | --- | --- | --- | --- | --- |
| Q1 | 岗位列表（核心） | 城市 + 一个或多个方向 + 学历 + 实习/正式 + 有无薪资 + 来源 | 薪资降序 / 发布时间降序 | 20/页 | jobs, job_stacks, companies |
| Q2 | 岗位详情 | 单个 `job_uid` | — | — | jobs, companies, job_stacks, job_tags, job_labels, job_descriptions |
| Q3 | 方向统计 | 城市 + 实习/正式 | 岗位数降序 | — | jobs, job_stacks, stacks |
| Q4 | 方向薪资分布 | 城市 + 方向 + 实习 + `day_mid_comparable` | — | — | jobs, job_stacks |
| Q5 | 学历分布 | 城市 + 实习 | 计数降序 | — | jobs |
| Q6 | 公司维度 | 公司 ID 或名称 | 岗位数降序 | 20/页 | companies, jobs |
| Q7 | 收藏 | 用户 ID | 收藏时间降序 | 20/页 | favorites, jobs |
| Q8 | 标题关键词搜索 | `title LIKE '%kw%'` | 相关度/时间 | 20/页 | jobs |

补充约束（从数据事实推出，不是假设）：

- Q1 必须支持「一次查多个方向」——因为 `stacks` 是多值，21.5% 的岗位命中 2 个及以上方向
- Q4 的分母必须是 `day_mid_comparable = 1`，否则会把社招月薪混进实习日薪
- Q7 的前提是「只能看自己的」——需要 `user_id` 过滤，这是权限验证的落点
- Q8 用 `LIKE '%kw%'` 会全表扫描，**在 3013 行下可接受**，数据量上去后要换全文索引（阶段二再议）

---

## 7. 表结构推导

**表不是按「应该有几张」定的，而是按「哪条查询需要」定的。**

| 表 | 由哪条查询逼出来 | 说明 |
| --- | --- | --- |
| `sources` | Q1 的来源筛选、Q3 的分来源统计 | 4 个取值，字典表 |
| `companies` | Q1 展示公司信息、Q6 公司维度 | 公司名重复率高（1954 种），单独拆表避免冗余 |
| `jobs` | 全部 | 主表 |
| `stacks` | Q1/Q3/Q4 | 15 个方向，字典表 |
| `job_stacks` | Q1 多方向筛选、Q3 按方向计数 | 多对多，必须独立表才能建索引 |
| `tags` + `job_tags` | Q2 展示技能标签 | 1762 种取值；**若只为展示而不筛选，可退化为 JSON 列**（见下方权衡） |
| `job_labels` | Q2 展示到岗条件 | 132 种取值，同 `tags` 的权衡 |
| `job_descriptions` | Q2 展示 JD | 大文本、5.2% 覆盖，必须独立 |
| `users` | Q7 | 收藏需要主体 |
| `favorites` | Q7 | 用户×岗位，唯一约束 |
| `import_batch` | §3.1 幂等与追溯 | 记录每次导入 |

### 7.1 `tags` / `job_labels` / `job_welfare` 的两条路线（待实测决定）

| 路线 | 优点 | 缺点 | 适用 |
| --- | --- | --- | --- |
| A. 字典表 + 关联表 | 可筛选、可统计、索引规范 | JOIN 变多，导入逻辑复杂 | 要按技能筛选时 |
| B. JSON 列 + MySQL 8 多值索引 | 写入简单，读取一次成型 | 多值索引有使用限制，统计要 `JSON_TABLE` | 只展示不筛选时 |

**决定方式**：阶段一先按 A（因为技能筛选是 Q1 的合理扩展），并在 `docs/INDEX-STUDY.md` 里用实测对比 B 的查询耗时。**不预先断言哪个更好。**

---

## 8. 索引候选与验证方法

### 8.1 候选（只是候选，**必须验证后才建**）

| # | 候选索引 | 服务的查询 | 假设 |
| --- | --- | --- | --- |
| C1 | `jobs(job_uid)` UNIQUE | 幂等导入、Q2 详情 | 必需，与性能无关 |
| C2 | `favorites(user_id, job_id)` UNIQUE | Q7 + 防重复收藏 | 必需，与性能无关 |
| C3 | `jobs(is_wuhan, intern, is_edu)` | Q1/Q3/Q5 的前置过滤 | 选择性待测 |
| C4 | `jobs(degree)` | Q1 学历筛选、Q5 | 8 个取值，选择性低 |
| C5 | `jobs(day_mid)` | Q1 薪资排序、Q4 | 排序能否走索引待测 |
| C6 | `jobs(publish_time)` | Q1 时间排序 | 94.3% 为 NULL，待测 |
| C7 | `job_stacks(stack_id, job_id)` | Q1 按方向反查、Q3 计数 | 覆盖索引可能性 |
| C8 | `job_stacks(job_id, stack_id)` | Q2 取岗位的所有方向 | 与 C7 是否都需要待测 |
| C9 | `jobs(company_id)` | Q6 | 外键常用 |
| C10 | `jobs(title(20))` 前缀索引 | Q8 | `LIKE '%kw%'` 用不上，**预计无效** |

### 8.2 验证方法（这是重点，不能跳过）

**前置问题：3013 行是小表，MySQL 优化器大概率直接全表扫描，加索引测不出差异。** 必须两步：

1. **造量**：把 `jobs` 按规则复制到 **20 万 / 50 万行**（保持字段分布），在真实量级上测；
2. **小表对照**：在 3013 行上用 `FORCE INDEX(C3)` / `IGNORE INDEX(C3)` 跑同一查询，记录执行计划差异，用来说明「为什么小表下优化器不选索引」。

**测量流程（每条候选索引都走一遍）**：

```
1. 固定 3 条代表查询，写成 .sql 文件
2. 关闭查询缓存（MySQL 8 默认无 QC，确认 query_cache_type）
3. 每条查询跑 5 次，丢弃第 1 次（预热），取后 4 次中位数
4. EXPLAIN 记录：type / possible_keys / key / key_len / rows / filtered / Extra
5. 建索引 → 重跑同样流程
6. 记录优化前后：耗时、扫描行数、是否回表
7. 结论写进 docs/INDEX-STUDY.md（表格：查询 / 索引 / 前耗时 / 后耗时 / Extra 变化）
```

**必须如实记录的三种结果**：

- 有效（耗时下降且执行计划改变）
- 无效（耗时无变化，说明优化器不选或数据量不够）
- 有害（写入变慢、优化器选错索引）

> 不允许出现「加了索引所以更快」这种无数据的结论。

### 8.3 明确不预先断言的

- ❌ 「`(city, degree, salary)` 联合索引有效」—— 这是上一版拍脑袋的写法，已删除
- ✅ 先跑 Q1 的真实 SQL，看 `EXPLAIN` 再说

---

## 9. 前端兼容：静态 JSON → API

现有看板前端（`wuhan-intern-dashboard/dashboard/`）通过 `fetch('data/*.json')` 读 7 个文件。

### 9.1 保留不动的

- `index.html` 的 10 个面板结构、CSS 全部、ECharts 配置与配色、图表类型、响应式
- 结论卡片、筛选器 UI 样式

### 9.2 必须改的 4 处

| # | 现状 | 改成 | 影响面 |
| --- | --- | --- | --- |
| 1 | `load()` 一次性 `fetch` 7 个 JSON，全量 3013 条进内存 | 分页接口 `GET /api/jobs?page=&page_size=20` | **最大改动**：客户端筛选失效，要改成服务端筛选 |
| 2 | 前端 `applyFilters()` 在内存里过滤 | 筛选条件变 query params：`?city=&stacks=&degree=&intern=&salary_only=&source=` | 筛选器 onChange 要触发请求 |
| 3 | `summary.json` / `stack_stats.json` 里的预计算指标 | `GET /api/stats/overview`、`/api/stats/stacks`、`/api/stats/salary` | 返回结构可保持现有形状，减小前端改动 |
| 4 | 无鉴权，收藏功能不存在 | 登录 + `GET/POST/DELETE /api/favorites` | 新增登录页；`fetch` 要带 token |

### 9.3 兼容策略：让 API 返回现有 JSON 形状

`summary.json`、`stack_stats.json`、`tags.json`、`company_panel.json`、`inventory.json`、`tracks.json` 这 6 个是**聚合结果**，量小。**阶段一让 API 原样返回同结构**，前端这几个面板一行不用改。

只有 `jobs_master.json`（3013 条、1.7MB）必须改成服务端分页。

**过渡方案**：保留 `GET /api/jobs?legacy=1` 返回全量（限 debug），便于逐面板迁移、逐个比对数字是否一致。

### 9.4 验收

- 同一组筛选条件，前端筛选结果条数 == API 返回 `total` == 手工 SQL 计数
- 10 个面板的图表数值与直接读静态 JSON 时一致（逐面板截图对比）

---

## 10. 阶段一不做

- 不做检索 / 向量库 / RAG
- 不做 JD 补抓（现有 5.2% 覆盖照实存，缺就是 NULL）
- 不做缓存、消息队列、多租户
- 不改看板视觉
- 不追求表数和接口数

## 11. 交付物清单

| 文件 | 内容 |
| --- | --- |
| `docs/FIELD-AUDIT.md` | 字段审计实测报告 |
| `docs/DESIGN.md` | 本文档 |
| `sql/schema.sql` | 可执行建表 SQL |
| `sql/index-candidates.sql` | 索引候选（注释形式，验证后再启用） |
| `docs/QUERIES.md` | 8 条查询的 SQL 草案 + 预期结果 |
| `docs/INDEX-STUDY.md` | 索引验证记录（建库后填） |
| `docs/FRONTEND-COMPAT.md` | 前端改造清单（本文 §9 展开） |
