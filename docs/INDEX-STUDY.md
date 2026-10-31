# 索引验证记录

> 原则：**先测再决定**。这里记录实测，包括「无效」和「反而更慢」的结果。
> 环境：MySQL 8.4.8 / 端口 3307 / 库 `jobdata` / `jobs` 表 3013 行。

## 测量方法（以及为什么第一次方法错了）

| 方法 | 结论 |
| --- | --- |
| `Measure-Command` 包 mysql 客户端 5 次取中位 | ❌ **无效**：单次 78–94 ms，几乎全是客户端连接开销，查询本身只有 2 ms，差异被噪声淹没 |
| `EXPLAIN`（估算） | ✅ 看 `type` / `key` / `rows` / `Extra`，判断是否用索引、是否 filesort |
| **`EXPLAIN ANALYZE`（实测）** | ✅ **唯一可信的耗时来源**：直接给出 `actual time` |

**教训：用客户端往返时间评估查询性能是错的。** 必须看 `EXPLAIN ANALYZE` 的 `actual time`，或开 `performance_schema`。

---

## 实验 1：C3 `(is_wuhan, is_intern, is_edu_excluded)`

被验证的查询（Q1 的过滤 + 排序）：

```sql
SELECT j.id FROM jobs j
WHERE j.is_wuhan=1 AND j.is_intern=1 AND j.is_edu_excluded=0 AND j.degree='本科'
ORDER BY j.day_mid DESC LIMIT 20;
```

### 执行计划对比

| | type | key | rows | cost | Extra |
| --- | --- | --- | ---: | ---: | --- |
| 无索引 | `ALL` | NULL | 2849 | 309 | Using where; Using filesort |
| 有索引 | `ref` | `idx_jobs_scope` | 1096 | 82.2 | Using where; Using filesort |

**索引确实被优化器选中**，扫描行数从 2849 降到 1096，成本估算从 309 降到 82.2。
→ 我之前「3013 行小表下索引不会被选中」的假设，**在这个查询上是错的**。

### 实际耗时（EXPLAIN ANALYZE）

| | actual time | rows |
| --- | ---: | ---: |
| 无索引 | **2.13 ms** | 20 |
| 有索引 | **2.73 ms** | 20 |

### 结论：**无效，且略有害**

- 扫描行数减少了 61%，但**实际执行反而慢了 0.6 ms**
- 原因：`ORDER BY day_mid DESC` 仍需 **filesort**（索引里没有 `day_mid`），
  索引带来的「减少扫描」被「索引查找 + 回表」抵消
- 写入侧还要多维护一个索引

**处理：删除该索引。** 不要因为「成本估算更低」就保留它——估算不等于实测。

---

## 实验 2：为什么 filesort 消不掉

`ORDER BY day_mid DESC` 要避免排序，必须让索引直接提供有序数据。候选：

```sql
-- 候选：把排序键放进索引
ALTER TABLE jobs ADD KEY idx_jobs_scope_day (is_wuhan, is_intern, is_edu_excluded, day_mid);
```

预期：`Extra` 里 `Using filesort` 消失，变成 `Using index condition` 或直接有序扫描。
**尚未实测**（下次做）。

注意 `day_mid` 有 901 行 NULL（29.9%），NULL 在升/降序中的位置会影响能否走索引排序，需一并验证。

---

## 结论汇总

| 候选 | 状态 | 结论 |
| --- | --- | --- |
| C1 `jobs(job_uid)` UNIQUE | ✅ 已建 | 幂等必需，与性能无关 |
| C2 `favorites(user_id, job_id)` UNIQUE | ✅ 已建 | 防重复收藏 + 权限落点，必需 |
| C3 `(is_wuhan, is_intern, is_edu_excluded)` | ❌ **实测无效，已删** | 扫描减少但实际更慢，filesort 未解决 |
| C4 `(degree)` | ⏳ 未测 | 8 个取值，预期选择性低 |
| C5 `(day_mid)` | ⏳ 未测 | 901 行 NULL，需先确认 NULL 对排序的影响 |
| C6 `(publish_time)` | ⏳ 未测 | 94.3% 为 NULL，预期收益极低 |
| C7 `job_stacks(stack_id, job_id)` | ✅ 已建（schema 中） | 辅助索引，未单独测量 |
| C8 `(company_id, publish_time)` | ⏳ 未测 | |
| C9 `(day_mid_comparable, day_mid)` | ⏳ 未测 | Q4 组合查询，最可能有效 |
| C10 `title(20)` 前缀索引 | ⏳ 未测 | 预期无效（`LIKE '%kw%'` 用不上） |

**下一步必须先做**：把 `jobs` 复制到 20 万行。3013 行下所有索引实验都在噪声区，2 ms 的差异没有工程意义。
造量方法（待实现）：

```sql
CREATE TABLE jobs_bench LIKE jobs;
INSERT INTO jobs_bench SELECT * FROM jobs;          -- 重复 6~7 次 ≈ 20 万行
-- 注意：job_uid 有 UNIQUE 约束，造量时需去掉或改写
```
