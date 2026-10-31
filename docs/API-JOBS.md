# 岗位列表与详情端点

> `GET /api/jobs` / `GET /api/jobs/<job_uid>`
> 这是**前端唯一必须改代码**的地方：把内存筛选/排序换成 SQL。
> 验证方式：`tests/test_api_jobs.py` 用源快照在 Python 里照抄前端 `applyFilters`，
> 对 17 种筛选组合**逐条对拍**（结果集必须完全相同）。

---

## 1. 为什么要对拍，而不是只看数字

前端的筛选逻辑写在 `app.js` 里：

```javascript
if (source && j.source !== source) return false;
if (stack && !(j.stacks || []).includes(stack)) return false;
if (degree && j.degree !== degree) return false;
if (salaryOnly && !j.day_mid) return false;
if (q && !`${j.title} ${j.company}`.toLowerCase().includes(q.toLowerCase())) return false;
```

搬到 SQL 后有几个容易错的地方：

| 风险点 | 后果 |
| --- | --- |
| `salaryOnly` 用 `day_mid` 还是 `intern_daily_sample` | 会差 141 行（645 vs 504） |
| `stack` 是多对多，忘了 `EXISTS` 就会漏/重 | 行数翻倍或漏行 |
| `q` 的大小写 | MySQL 的 `_ci` collation 默认不区分，与 JS 的 `toLowerCase` 一致，但不能靠猜 |
| `q` 含 `%` / `_` | 被当通配符，搜「100%」命中全表 |
| 窗口范围 | 前端表格只显示实习口径 **1096 行**，不是 3013 |

所以测试不是「断言 total 等于某个数」，而是**两种实现跑同一组筛选，比较 uid 集合**。

---

## 2. 对拍结果

17 种组合全部一致（`tests/test_api_jobs.py::FilterParityTest`）：

| 组合 | total |
| --- | ---: |
| 无筛选 | 1096 |
| `stack=Python` | 154 |
| `stack=Java` | 175 |
| `stack=算法/AI` | 209 |
| `degree=本科` | 647 |
| `degree=硕士` | 136 |
| `source=BOSS直聘` | 953 |
| `source=智联招聘` | 87 |
| `q=python` | 29 |
| `q=实习` | 757 |
| `q=工程师` | 数条 |
| `salary_only=1` | **645** |
| `stack=Python&degree=本科` | **107** |
| `stack=Java&salary_only=1` | — |
| `stack=Python&q=算法` | — |
| `source=BOSS直聘&degree=本科` | — |
| `stack=不存在` | 0 |

`stack=Python&degree=本科 = 107` 与 `stack_stats.json` 里 `Python.degree.本科` 精确一致，交叉验证通过。

---

## 3. 参数

| 参数 | 取值 | 默认 | 校验 |
| --- | --- | --- | --- |
| `page` | 1..100000 | 1 | 非整数或越界 → 400 |
| `page_size` | 1..**200** | 20 | 越界 → 400（防止拉全表） |
| `source` | 来源名，如 `BOSS直聘` | — | 精确匹配 |
| `stack` | 方向名，如 `Python` | — | 数组成员 |
| `degree` | `本科`/`硕士`/… | — | 精确匹配 |
| `q` | 任意字符串 | — | 对 title+company 做包含（`%`/`_` 已转义） |
| `salary_only` | `1`/`true` | 关 | `day_mid` 非空（**与前端一致，宽口径**） |
| `intern_daily_only` | `1`/`true` | 关 | `intern_daily_sample=1`（严口径，本库新增） |
| `sort` | `daypay`/`salary`/`title`/`company`/`publish`/`degree`/`stacks` | `daypay` | **白名单**，非法 → 400 |
| `order` | `asc`/`desc` | `desc` | 非法 → 400 |

`sort` 用白名单映射到列名，用户输入**不会**进入 SQL 字符串。

`degree` 排序用 `FIELD(j.degree,'不限','中专/高中','大专','本科','硕士','博士')`，
复现前端的自定义顺序（不是字典序）。

### 关于 `salary_only` 的口径

前端用的是 `day_mid` 非空（645 行），**包含**由「元/月」折算来的值。
本库保留了原语义，另加 `intern_daily_only=1`（504 行）供严格场景使用。

**没有偷偷改口径** —— 迁移时保持行为一致优先，权衡记录在此。

---

## 4. 响应

```json
{
  "items": [
    {
      "job_uid": "boss-...", "title": "...", "company": "...",
      "source": "BOSS直聘", "city": "武汉", "district": "洪山区",
      "degree": "本科", "experience": "在校/应届",
      "salary_raw": "150-200元/天", "salary_unit": "DAY",
      "day_mid": 175.0, "month_mid": null,
      "is_intern": 1, "title_has_intern": 1, "intern_daily_sample": 1,
      "primary_stack": "Python", "industry": "计算机软件",
      "publish_time": null, "url": "https://...",
      "stacks": ["Python", "数据分析"],
      "tags": ["MySQL", "Linux"],
      "labels": ["本科", "5天/周"]
    }
  ],
  "total": 1096,
  "page": 1,
  "page_size": 20,
  "pages": 55,
  "sort": {"key": "daypay", "order": "desc"},
  "applied_filters": {},
  "scope": "实习口径：is_wuhan=1 AND is_intern=1 AND is_edu_excluded=0"
}
```

`stacks` / `tags` / `labels` 是**批量补的**（每页 3 次查询，不是每行 3 次）。
`tests/test_api_jobs.py::test_relations_not_n_plus_one` 用 `CaptureQueriesContext`
断言整页查询数 ≤ 8。

---

## 5. 详情端点

`GET /api/jobs/<job_uid>`

- `job_uid` 里可能有中文和 `|`（猎聘的 ID 就是这样），所以路由用 `<path:job_uid>`
- 返回主记录 + `stacks`/`tags`/`labels` + `jd`（`null` 表示没有正文，3013 行里只有 156 行有）
- 不存在 → **404 + `{"error":"not_found"}`**（不是 200 空对象）

---

## 6. 已知限制

| 限制 | 说明 |
| --- | --- |
| `LIMIT/OFFSET` 深分页 | `page=5000` 时 MySQL 要扫 10 万行。当前 1096 行无影响；数据量上去需改 keyset（`WHERE id > last_id`） |
| 字符串排序与 JS 不完全等价 | SQL 用 collation 排序，JS 用 `localeCompare('zh-CN')`。数值排序已验证单调，中文标题排序可能有细微差异，属展示层 |
| `q` 只有 `%kw%` | 左侧通配符用不上索引，3013 行全表扫可接受（实测 < 10ms）；数据量上去要换全文索引 |
| 没有 `offset` 参数 | 只暴露 `page`，避免「page 与 offset 冲突」的歧义 |
