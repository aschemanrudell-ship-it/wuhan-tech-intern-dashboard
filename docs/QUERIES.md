# 查询清单与实测结果

> 每条查询都标明：服务哪个页面、参数、SQL、**实测结果**。
> 实测环境：MySQL 8.4.8 / 端口 3307 / 库 `jobdata` / 3013 行。
> 所有"实测"数字均由 `scripts/verify_queries.py` 从库中直接算出，非估算。

---

## 口径约定（先看这个，否则数字对不上）

实习范围不是一层，是三层。**每层都实测过，数字来自库本身。**

| 层 | 定义 | 实测行数 | 用途 |
| --- | --- | ---: | --- |
| **A 宽口径实习** | `is_intern=1`（源数据判定，含"应届/校招"命中） | **1096** | 与源项目对齐的上位口径 |
| **B 明确实习** | A 且标题含"实习"（`title_has_intern=1`） | **765** | 只保留标题写明实习的岗位 |
| **C 明确实习 + 日薪样本** | B 且 `intern_daily_sample=1` | **484** | **薪资统计用这一层** |

C 层的构成：元/天 **392** 行 + 标题含实习的 K/月 **92** 行。

> 另有 `day_mid_comparable=1`（只按单位判，含全部 K/月）= **623** 行，**不要用**——它把社招月薪也算进来了。

**与源项目数字的对照**：

| 指标 | 源 `summary.json` | 本库 C 层 | 说明 |
| --- | ---: | ---: | --- |
| Python 薪资样本 n | 74 | **74** | ✅ 完全一致 |
| Java 薪资样本 n | 99 | 96 | 差 3：源脚本允许"元/天但标题不含实习"，C 层要求标题含实习 |
| Python 日薪中位 | 175.0 | **175.0** | ✅ 一致 |
| 算法/AI 日薪中位 | 183.9 | **183.9** | ✅ 一致 |

> 源脚本用大小写敏感的 `"K" in salary_raw`，漏掉 5 行小写 `k`（`3-5k`、`3-6k`、`4-7k`、`4-8k`）。本库用 `[kK]` 修正，因此 `intern_daily_sample` 总数 504 比源脚本 499 多 5。

### C 层的已知缺陷（8 行，未解决）

C 层里混进了 8 行**月薪 > 10000** 的岗位，它们不是真正的实习薪资：

| 标题 | 公司 | 月薪 | 问题类型 |
| --- | --- | ---: | --- |
| 暑期实习/互联网-技术类 | 北京某大型互联网短视频平台上市公司 | 32500 | 匿名大厂，实为正式岗 |
| 深度学习算法工程师（实习工程师） | 北京某小型工业机器人智能应用公司 | 22500 | 异地 |
| (工作地:杭州)2022年校招实习生-JAVA/C/C++ | 阿里巴巴集团 | 20500 | **异地 + 2022 届过期** |
| 触觉仿真算法工程师（应届/实习） | 华威科 | 20000 | 校招口径 |
| 前沿部署工程师(FDE)-校招需实习 | 元气森林 | 18500 | 校招岗 |
| 多模态算法工程师—27届实习转正 | 多比特 | 16500 | 实习转正，薪资偏正式 |
| Web 全栈工程师及实习生招聘 | 湖北辰千空间 | 16000 | 正式岗与实习混招 |
| 可实习/可带朋友 写字楼坐班客服岗 | 武汉奈伟信息科技 | 10500 | **非技术岗（客服）** |

**结论：「标题含实习」这一个判据不足以识别真实习。** 要彻底解决，需要在导入层再加四类排除：异地（标题含城市名）、过期届别（2022/22届）、非技术岗（客服/销售/运营）、校招（含"校招/正编/应届"且无"实习"）。这些**当前没做**，所以任何"实习薪资中位数"的结论都受这 8 行影响。8 / 484 = 1.7%，对中位数影响有限（中位 175 未被拉高），但对 **P75 和最大值影响明显**。

---

## Q1 岗位列表（核心页）

**服务**：看板 ⑨ 岗位明细面板
**参数**：`city`（固定武汉）、`stacks[]`、`degree`、`intern_only`、`salary_only`、`source`、`page`、`page_size`、`sort`

```sql
SELECT j.job_uid, j.title, c.name AS company, j.city, j.district,
       j.degree, j.is_intern, j.salary_raw, j.salary_unit,
       j.day_mid, j.intern_daily_sample, j.publish_time, j.url
FROM jobs j
LEFT JOIN companies c ON c.id = j.company_id
WHERE j.is_wuhan = 1
  AND j.is_edu_excluded = 0
  AND (:intern_only = 0 OR j.is_intern = 1)
  AND (:explicit_intern_only = 0 OR j.title_has_intern = 1)
  AND (:degree IS NULL OR j.degree = :degree)
  AND (:salary_only = 0 OR j.intern_daily_sample = 1)
  AND (:source_id IS NULL OR j.source_id = :source_id)
  AND (:no_stack_filter = 1 OR EXISTS (
        SELECT 1 FROM job_stacks js
        WHERE js.job_id = j.id AND js.stack_id IN (:stack_ids)
      ))
-- 排序必须让「明确实习 + 有日薪样本」的岗位优先，否则会把校招高薪岗顶到第一屏
ORDER BY (j.title_has_intern = 1 AND j.intern_daily_sample = 1) DESC,
         j.day_mid IS NULL, j.day_mid DESC
LIMIT :limit OFFSET :offset;
```

**实测**（条件：`is_intern=1 AND title_has_intern=1 AND intern_daily_sample=1`，按薪资降序前 6 条）：

| title | company | salary_raw | day_mid |
| --- | --- | --- | ---: |
| 暑期实习/互联网-技术类 | 北京某大型互联网短视频平台上市公司 | 25-40K | 1494.20 |
| 深度学习算法工程师（实习工程师） | 北京某小型工业机器人智能应用公司 | 20-25K | 1034.50 |
| (工作地:杭州)2022年校招实习生-JAVA/C/C++ | 阿里巴巴集团 | 20-21K | 942.50 |
| 触觉仿真算法工程师（应届/实习） | 华威科 | 15-25K·15薪 | 919.60 |
| 前沿部署工程师(FDE)-校招需实习(A181961) | 元气森林 | 15-22K·14薪 | 850.60 |
| 多模态算法工程师—27届实习转正 | 多比特 | 13-20K·14薪 | 758.60 |

> ⚠️ **这 6 条全是上一节说的 8 行异常。** 也就是说：只要按薪资降序，第一屏必然被这 8 行占据，而它们不是真实实习薪资。
> **这直接决定了 Q1 不能只按 `day_mid DESC` 排序**，必须在应用层决定：要么加月薪上界过滤，要么默认按 `publish_time` 排序（但 94% NULL），要么让用户显式选择"仅看真实习"。
> **这是尚未解决的设计问题，不是已完成的功能。**

---

## Q2 岗位详情

**服务**：点击岗位卡片展开详情
**参数**：`job_uid`

```sql
-- 主记录
SELECT j.*, c.name AS company_name, c.size, c.financing, c.industry,
       c.open_jobs, c.boss_count, s.name AS source_name
FROM jobs j
LEFT JOIN companies c ON c.id = j.company_id
JOIN sources s ON s.id = j.source_id
WHERE j.job_uid = :job_uid;

-- 方向 / 技能 / 标签 / JD（4 条小查询，按 job_id 取）
SELECT st.name FROM job_stacks js JOIN stacks st ON st.id = js.stack_id
WHERE js.job_id = :job_id ORDER BY js.ordinal;

SELECT t.name FROM job_tags jt JOIN tags t ON t.id = jt.tag_id WHERE jt.job_id = :job_id;

SELECT d.name FROM job_label_links l JOIN job_label_dict d ON d.id = l.label_id WHERE l.job_id = :job_id;

SELECT content, char_count FROM job_descriptions WHERE job_id = :job_id;
```

**实测**：`job_descriptions` 共 156 行，即 3013 条里 **5.2%** 能取到 JD 正文；其余返回空集（不是空字符串，是没这行）。

---

## Q3 方向统计

**服务**：看板 ② 技术方向需求对比
**参数**：`intern_only`

```sql
SELECT s.name AS stack, COUNT(*) AS job_count
FROM job_stacks js
JOIN stacks s ON s.id = js.stack_id
JOIN jobs j   ON j.id = js.job_id
WHERE j.is_wuhan = 1 AND j.is_intern = 1 AND j.is_edu_excluded = 0
GROUP BY s.name
ORDER BY job_count DESC;
```

**实测（15 个方向，与源项目 `summary.json` 的 `stack_counts` 逐项一致）**：

| 方向 | 岗位数 | | 方向 | 岗位数 |
| --- | ---: | --- | --- | ---: |
| 算法/AI | 209 | | 大数据 | 52 |
| Java | 175 | | 网络安全 | 37 |
| Python | 154 | | Go | 33 |
| C/C++ | 145 | | 数据标注 | 14 |
| 前端 | 137 | | Android/iOS | 10 |
| 数据分析 | 91 | | .NET/C# | 10 |
| 测试 | 75 | | PHP | 6 |
| 运维/云 | 61 | | | |

> 各项之和 1209 > 1096，因为一个岗位可命中多个方向（多对多）。

---

## Q4 方向薪资分布

**服务**：看板 ⑤ 薪资分析（箱线图）
**参数**：`stack`、口径固定为严口径

```sql
WITH scoped AS (
  SELECT s.name AS stack, j.day_mid
  FROM job_stacks js
  JOIN stacks s ON s.id = js.stack_id
  JOIN jobs j   ON j.id = js.job_id
  WHERE j.is_wuhan = 1 AND j.is_intern = 1 AND j.is_edu_excluded = 0
    AND j.title_has_intern = 1          -- C 层：明确实习
    AND j.intern_daily_sample = 1       -- C 层：可折算日薪
    AND s.name IN (:stacks)
), ranked AS (
  SELECT stack, day_mid,
         ROW_NUMBER() OVER (PARTITION BY stack ORDER BY day_mid) AS rn,
         COUNT(*)     OVER (PARTITION BY stack)                 AS cnt
  FROM scoped
)
SELECT stack, MAX(cnt) AS n,
       ROUND(MIN(day_mid),1) AS min_v,
       ROUND(AVG(CASE WHEN rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2)) THEN day_mid END),1) AS median,
       ROUND(MAX(day_mid),1) AS max_v
FROM ranked GROUP BY stack ORDER BY n DESC;
```

**实测（C 层）**：

| 方向 | n | 中位（元/天） |
| --- | ---: | ---: |
| Java | 96 | 175.0 |
| 算法/AI | 96 | 183.9 |
| Python | 74 | 175.0 |

**换口径会导致结论变化（这是必须用 C 层的直接证据）**：

| 口径 | Java n / 中位 | Python n / 中位 |
| --- | --- | --- |
| 宽口径 `day_mid_comparable=1` | 127 / 175.0 | 92 / **202.5** |
| 严口径 `intern_daily_sample=1`（不加标题条件） | 99 / 175.0 | 75 / 175.0 |
| **C 层（明确实习 + 日薪样本）** | **96 / 175.0** | **74 / 175.0** |

用错口径，Python 中位数会从 175 虚高到 202.5（+27.5 元/天）。

> MySQL 8 没有 `PERCENTILE_CONT`，中位数用 `ROW_NUMBER` + `COUNT` 窗口函数取两中位点平均。P25/P75 同理把 `(cnt+1)/2` 换成 `(cnt+1)/4`、`3*(cnt+1)/4`。

---

## Q5 学历分布

**服务**：看板 ⑥ 学历要求

```sql
SELECT degree, COUNT(*) AS n
FROM jobs
WHERE is_wuhan = 1 AND is_intern = 1 AND is_edu_excluded = 0
GROUP BY degree ORDER BY n DESC;
```

**实测**：

| degree | n |
| --- | ---: |
| 本科 | 647 |
| 大专 | 163 |
| 硕士 | 136 |
| 不限 | 119 |
| 博士 | 16 |
| 中专/高中 | 15 |

> 合计 1096 ✓。源数据里 `degree` 有 4 行 `经验不限`、2 行 `初中及以下` 脏值，导入时已归一到 `不限`，原文保留在 `degree_raw`。

---

## Q6 公司维度

**服务**：看板 ⑦⑧ 公司分布与企业画像

```sql
SELECT c.name, c.size, c.financing, c.industry, c.open_jobs,
       COUNT(j.id) AS job_count
FROM companies c
JOIN jobs j ON j.company_id = c.id
WHERE j.is_wuhan = 1 AND j.is_intern = 1 AND j.is_edu_excluded = 0
GROUP BY c.id
ORDER BY job_count DESC
LIMIT 20;
```

**实测**：参与在招实习的公司 608 家（与源项目 `summary.json` 的 `companies_hiring_interns` 一致）。
`companies` 表共 1954 行（全部快照里的公司），其中 `open_jobs` 只有 358 行有值（88.1% 缺失）。

---

## Q7 收藏（含权限落点）

**服务**：我的收藏页

```sql
-- 我的收藏（user_id 必须来自会话，不可来自请求参数）
SELECT j.job_uid, j.title, c.name AS company, j.salary_raw, f.created_at
FROM favorites f
JOIN jobs j ON j.id = f.job_id
LEFT JOIN companies c ON c.id = j.company_id
WHERE f.user_id = :session_user_id
ORDER BY f.created_at DESC
LIMIT :limit OFFSET :offset;

-- 收藏（幂等）
INSERT IGNORE INTO favorites (user_id, job_id) VALUES (:session_user_id, :job_id);

-- 取消收藏（必须带 user_id，否则等于允许删别人的）
DELETE FROM favorites WHERE user_id = :session_user_id AND job_id = :job_id;
```

**权限验证（必做）**：

1. 用户 A 收藏 job 1；用户 B 登录后调 `DELETE /api/favorites/1` → 期望 **0 行受影响**，A 的收藏仍在
2. 未登录调 `GET /api/favorites` → 期望 **401**
3. 同一用户重复收藏同一岗位 → `INSERT IGNORE` + `UNIQUE(user_id, job_id)` → 收藏数**不变**

**实测**：`favorites` 当前 0 行（未导入用户数据），上述三条需在接口层实现后用接口测试验证。

---

## Q8 标题关键词搜索

**服务**：看板 ⑨ 的搜索框

```sql
SELECT j.job_uid, j.title, c.name AS company, j.salary_raw
FROM jobs j
LEFT JOIN companies c ON c.id = j.company_id
WHERE j.is_wuhan = 1 AND j.is_edu_excluded = 0
  AND j.title LIKE CONCAT('%', :kw, '%')
ORDER BY j.is_intern DESC, j.publish_time IS NULL, j.publish_time DESC
LIMIT :limit OFFSET :offset;
```

**实测**：`kw = 'python'` → 命中 **468** 条（不区分大小写，因 collation 为 `utf8mb4_0900_ai_ci`）。

> 左侧通配符 `%kw%` **无法使用 B+Tree 索引**，3013 行下全表扫描可接受（实测 < 10ms，见 `docs/INDEX-STUDY.md`）。数据量上去需换 ngram 全文索引或外部检索，属阶段二。

---

## 跨源同名的查询方式（不合并，只标记）

```sql
-- 找出库里的跨源同名组
SELECT dup_group_key, GROUP_CONCAT(DISTINCT s.name) AS sources, COUNT(*) AS n
FROM jobs j JOIN sources s ON s.id = j.source_id
WHERE dup_group_key IS NOT NULL
GROUP BY dup_group_key
HAVING COUNT(DISTINCT s.name) > 1;
```

**实测**：跨源同名 **2 组**（`AI算法实习生（CV模型训练与智能算法方向）| 中望软件`、`临床统计分析实习生 | 宏韧医药`）。
同源同名 **64 组 / 158 行**（主要是猎聘「某知名公司」不同城市同名岗、智联重复发布）。
**均不做物理合并**，只在展示层提示"同名岗位 N 个"。
