# 交接说明（HANDOFF）

写给下一个接手的人（或下一个自己）。目标：能在 10 分钟内跑起来、知道哪些是真的、哪些还没做。

## 1. 一分钟了解状态

**已完成并验证的**

- 字段审计（`docs/FIELD-AUDIT.md`，脚本生成，非手写）
- 13 张表的 DDL，在 MySQL 8.4.8 上**实跑建成**
- 快照导入：3013 岗位 / 3753 方向关联 / 8495 技能关联 / 5197 标签关联 / 156 条 JD
- **幂等复导**：同一文件跑第二次，jobs 仍 3013 行、关联表行数不变、字典不膨胀
- 8 条查询写完并实测（`docs/QUERIES.md`），15 个技术方向计数与源项目 `summary.json` 逐项一致
- 三层实习口径 A/B/C = 1096 / 765 / 484；C 层 Python n=74 中位 175.0 与源一致
- **Django API 已跑通**：`/api/health` + `/api/stats/summary`，真实 HTTP 200、11564 字节、31 个键
- **API 与源 summary.json 逐字段比对**（`docs/SUMMARY-MAPPING.md`）：8 类字段完全一致，5 处差异全部定位到原因
- **9 个 API 端点全部跑通**，包含 `/api/jobs` 分页/筛选/排序与详情
- **98 个测试 + 169 subtests 全过**（scope 11 / summary 14 / stats 28 / jobs 15 / auth+收藏 30）
- 认证用 Bearer token（库里只存 SHA-256），收藏三条验收项全部通过：
  未登录 401、A 删不掉 B 的收藏、重复收藏幂等
- `/api/jobs` 与内存过滤**逐条对拍**：17 种筛选组合的结果集完全相同

**没做的（不要以为有）**

- 前端 Step B：表格改服务端分页、图表改吃 stats 聚合、删掉 `legacy=1`
- 令牌刷新、登录限流（当前都没有）
- 用户/收藏的接口（表和约束已建）
- 索引造量实测（只在 3013 行上测过 C3，结论是「无效已删」）

## 2. 环境

| 项 | 值 |
| --- | --- |
| Python | 3.14.3，venv 在 `.venv`，**MSYS2 布局：`.venv/bin/python.exe`，不是 `Scripts`** |
| MySQL | 8.4.8，**独立实例跑在 3307**，datadir `work/mysql-data/` |
| 驱动 | PyMySQL 2.2.8（装在项目 venv） |
| 用户原有 MySQL | 在 3306，root 有密码，**本项目没有碰它** |

> `.venv\Scripts` 是指向 `.venv\bin` 的 junction —— `verify-ai-project` 硬编码找 `.venv\Scripts\python.exe`，没有它会退化成系统 Python 并报 `No module named pytest`。重建命令：`cmd /c "mklink /J .venv\Scripts .venv\bin"`。

> 为什么用 3307 独立实例：本机 3306 的 root 口令未知，且不该为了验证去改别人的实例。
> `work/mysql-data/` 是一次性的，删掉重跑 `--initialize-insecure` 即可复位。

## 3. 从零跑起来

```powershell
cd 'D:\AIProjects\DeepSeek Harness\JobDataPlatform'

# 1) venv（已存在则跳过）
python -m venv .venv
.\.venv\bin\python.exe -m pip install pymysql pytest

# 2) 起独立 MySQL（前台占用一个终端，或后台跑）
$bin = 'C:\Program Files\MySQL\MySQL Server 8.4\bin'
& "$bin\mysqld.exe" --initialize-insecure --datadir="$PWD\work\mysql-data" --console   # 仅首次
& "$bin\mysqld.exe" --datadir="$PWD\work\mysql-data" --port=3307 --console --skip-mysqlx

# 3) 建库建表
& "$bin\mysql.exe" -u root -h 127.0.0.1 -P 3307 -e "CREATE DATABASE jobdata CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
cmd /c "`"$bin\mysql.exe`" -u root -h 127.0.0.1 -P 3307 jobdata < sql\schema.sql"

# 4) 导入（跑两次，验证幂等）
.\.venv\bin\python.exe scripts\import_snapshot.py --port 3307
.\.venv\bin\python.exe scripts\import_snapshot.py --port 3307

# 5) 验证
.\.venv\bin\python.exe scripts\audit_fields.py
.\.venv\bin\python.exe -m unittest discover -s tests -v      # 期望 10 tests OK
.\.venv\bin\python.exe -m pytest -q                          # 同一个文件，两套 runner 都能跑
```

## 4. 踩过的坑（省你时间）

| 坑 | 现象 | 处理 |
| --- | --- | --- |
| PowerShell 管道传 SQL 给 `mysql.exe` | `ERROR 1064 ... near 'boss / zhilian / liepin / shixiseng'`，SQL 里的引号被吃掉 | 用 `cmd /c "mysql ... < file.sql"` 重定向，不要 `Get-Content \| mysql` |
| `python -m venv` 在这个环境 | 生成的是 POSIX 布局 `.venv/bin`，不是 `.venv/Scripts` | 用 `.venv\bin\python.exe` |
| 系统 Python 装包 | `PEP 668` 报 externally-managed-environment | 一律在项目 venv 内安装 |
| `mysqld --initialize-insecure` 返回 exit 1 | 只是 stderr 有日志，实际成功 | 看日志最后一行 `Initialization - end` |
| 审计脚本第一版 | `nonempty = N - empty` 把"键不存在"算成非空，`durations` 虚报 2950（实际 113） | 已修为 `present / missing_key / empty` 三段统计 |
| 源聚合脚本 | 大小写敏感的 `"K" in salary_raw`，漏掉 5 行 `3-5k`/`4-8k` | 本项目用 `[kK]` 修正，导致 C 层比源脚本多 5 行 |
| `.gitignore` | 脚手架生成成**单行**，Git 不解析，`work/`（含数百 MB datadir）会被提交 | 已重写为多行 |

## 5. 数据结构要点（改动前必读）

```
jobs（主表，3013 行）
 ├─ source_id → sources（4）
 ├─ company_id → companies（1954，86 行为 NULL）
 ├─ first/last_batch_id → import_batch
 ├─ job_stacks → stacks（15）        3753 行
 ├─ job_tags → tags（2264）          8495 行
 ├─ job_label_links → job_label_dict（35）  5197 行
 └─ job_descriptions（1:1，156 行）

users → favorites（UNIQUE(user_id, job_id)）
```

**三个生成列，别手写它们**：

| 列 | 定义 | 实测 |
| --- | --- | ---: |
| `day_mid_comparable` | 单位层面可折算日薪 | 623 |
| `intern_daily_sample` | 元/天 或 标题含实习的 K/月 | 504 |
| `title_has_intern` | 普通列（非生成），导入时写入 | 765 |

**薪资统计用 `title_has_intern=1 AND intern_daily_sample=1` → 484 行**。用别的组合会得到不同的中位数（对比表见 `docs/QUERIES.md` Q4）。

## 6. 未解决的问题（按优先级）

1. **8 行高月薪假实习**（10K–32.5K，异地/2022 届/校招/客服）。`title_has_intern` 拦不住它们。
   需要加四类排除：异地城市、过期届别、非技术岗、校招。**没有依据就别拍阈值**，先看分布。
2. **索引零实测**。3013 行是小表，优化器会全表扫描，加索引大概率测不出差异。
   必须先把 `jobs` 造量到 20 万行再测，方法见 `docs/DESIGN.md` §8.2。
3. **`is_intern` 是宽口径**，1096 行里 331 行标题不含"实习"（靠"应届/校招"命中）。严格场景用 `title_has_intern`。
4. **JD 覆盖 5.2%**，只有智联有。要做检索必须先补抓 BOSS 详情页。

## 7. 下一步建议顺序

```
Step 1  ✅ 已完成：Django 骨架 + /api/stats/summary（31 键，与源逐字段比对）
Step 2  ✅ 已完成：其余 5 个 stats 端点
Step 3  ✅ 已完成：/api/jobs 分页 + 服务端筛选（17 组对拍通过）；剩前端改 3 个函数
Step 4  ✅ 已完成：登录 + 收藏 + 三条权限测试（Bearer token）
Step 5  jobs 造量到 20 万，实测索引候选
Step 6  定 8 行异常的处理规则（要数据支撑，不要拍脑袋）
```

## 8. 约束

- `data/raw/` 是冻结快照，**不要改**；源数据变了就重新导入。
- 不要碰 3306 上的 MySQL 实例。
- 不写密码进仓库；口令走 `JDP_PASSWORD` 环境变量 + `--use-env-credentials`。
- 所有写进 `docs/` 的数字必须能由 `scripts/` 下的脚本复现，不接受手抄。
