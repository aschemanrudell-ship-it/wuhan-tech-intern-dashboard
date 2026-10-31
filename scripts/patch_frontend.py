# -*- coding: utf-8 -*-
"""改写 dashboard/app.js 的数据层：JSON 文件 → API。

只改三处，**不动任何 render 函数**：
  1. FILES 常量 → API 端点表
  2. load()        → 并发请求 API，组装出与原来完全相同的形状
  3. boot 里的数源注释

保留 `data.jobs_master` / `data.summary` / … 这些键名不变，所以
renderKpis / renderStackChart / … 全部原样工作。
"""
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
P = pathlib.Path(__file__).resolve().parent.parent / "static" / "dashboard" / "app.js"
src = P.read_text(encoding="utf-8")

# ---------------------------------------------------------------- 1. FILES → API
old_files = re.search(r"const FILES = \[[^\]]*\];", src)
if not old_files:
    print("!! 未找到 FILES 常量")
    sys.exit(1)

new_files = """const API = '/api';
  /* 数据源：全部改为后端 API。
     键名与原来的 JSON 文件一一对应（jobs_master / summary / stack_stats / …），
     所以下面的 render* 函数一行都不用改。 */
  const ENDPOINTS = {
    summary:       `${API}/stats/summary`,
    stack_stats:   `${API}/stats/stacks`,
    tags:          `${API}/stats/tags`,
    company_panel: `${API}/stats/companies`,
    inventory:     `${API}/stats/inventory`,
    tracks:        `${API}/stats/tracks`,
    // jobs_master 走 legacy 全量接口：图表需要全量数组做聚合。
    // 表格的分页化放在下一步（见 docs/FRONTEND-COMPAT.md Step 4）。
    jobs_master:   `${API}/jobs?legacy=1&sort=daypay&order=desc`,
  };"""
src = src.replace(old_files.group(0), new_files, 1)

# ---------------------------------------------------------------- 2. load() → fetch API
old_load = re.search(r"async function load\(\) \{.*?\n  \}", src, re.S)
if not old_load:
    print("!! 未找到 load()")
    sys.exit(1)

new_load = """async function load() {
    /* 并发拉 7 个端点；任何一个失败都直接抛出，避免页面半渲染。 */
    const names = Object.keys(ENDPOINTS);
    const results = await Promise.all(names.map(async (name) => {
      const url = ENDPOINTS[name];
      const r = await fetch(url, { cache: 'no-store' });
      if (!r.ok) {
        const body = await r.text().catch(() => '');
        throw new Error(`${name} 读取失败 (${r.status}) ${body.slice(0, 120)}`);
      }
      return [name, await r.json()];
    }));

    const out = {};
    for (const [name, data] of results) {
      // jobs_master 端点返回裸数组（兼容原 jobs_master.json 形状）；
      // 其余端点直接就是原 JSON 形状。
      out[name] = name === 'jobs_master'
        ? (Array.isArray(data) ? data : (data.items || []))
        : data;
    }
    return out;
  }"""
src = src.replace(old_load.group(0), new_load, 1)

# ---------------------------------------------------------------- 3. 顶部注释补充
if "数据源：后端 API" not in src.split("\n")[0:6]:
    lines = src.split("\n")
    lines.insert(0, "/* 数据源已切换为后端 API（原为 data/*.json）。见 docs/FRONTEND-COMPAT.md */")
    src = "\n".join(lines)

P.write_text(src, encoding="utf-8")
print(f"已改写 {P}")
print(f"  文件 {len(src)} 字符")
for probe, label in [
    ("const ENDPOINTS", "端点表"),
    ("/api/stats/summary", "summary 端点"),
    ("/api/jobs?legacy=1", "jobs legacy 端点"),
    ("data.items || []", "jobs 解包"),
    ("function renderTable()", "renderTable 保留"),
    ("function renderKpis(", "renderKpis 保留"),
]:
    print(f"  {label:16s}{'OK' if probe in src else 'MISS'}")
