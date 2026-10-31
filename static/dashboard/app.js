/* 数据源已切换为后端 API（原为 data/*.json）。见 docs/FRONTEND-COMPAT.md */
/* 武汉计算机实习招聘需求看板 — 全部指标由本次抓取数据实时计算 */
(() => {
  'use strict';

  const API = '/api';
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
  };
  const C = {
    python: '#3776ab', java: '#d9730d', algo: '#7c5cff', accent: '#1f6feb',
    ink: '#1b2733', ink2: '#4a5b6d', ink3: '#8593a3', line: '#e3e8ee',
    cpp: '#5b8c5a', fe: '#c2185b', test: '#00897b', big: '#6a4c93', gray: '#94a3b8',
  };
  // 技术方向配色：常见方向固定色，其余轮转灰阶，避免同色撞车
  const STACK_COLOR = {
    '算法/AI': C.algo, 'Python': C.python, 'Java': C.java, 'C/C++': C.cpp, '前端': C.fe,
    '测试': C.test, '大数据': C.big, '数据分析': '#0e7490', '数据标注': '#a16207',
    'Go': '#0891b2', '运维/云': '#475569', '网络安全': '#b91c1c', '.NET/C#': '#7c3aed',
    'PHP': '#64748b', 'Android/iOS': '#059669', '其他/非技术': C.gray,
  };

  const NON_TECH = '其他/非技术';
  const KNOWN = ['Python', 'Java', '算法/AI', 'C/C++', '前端', '测试', '大数据', 'Go',
    '数据分析', '数据标注', '运维/云', '网络安全', '.NET/C#', 'PHP', 'Android/iOS'];
  const stackColor = (name) => STACK_COLOR[name] || '#94a3b8';
  const fmt = (v, d = 0) => (v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toFixed(d));
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[m]));

  const charts = {};
  const mkChart = (id) => {
    const el = document.getElementById(id);
    if (!el || !window.echarts) return null;
    const c = echarts.init(el, null, { renderer: 'canvas' });
    charts[id] = c;
    return c;
  };
  window.addEventListener('resize', () => Object.values(charts).forEach((c) => c.resize()));

  const baseGrid = { left: 8, right: 16, top: 34, bottom: 6, containLabel: true };
  const axisText = { color: C.ink2, fontSize: 12 };
  const splitLine = { lineStyle: { color: C.line, type: 'dashed' } };

  function quantile(sorted, q) {
    if (!sorted.length) return null;
    const pos = (sorted.length - 1) * q;
    const lo = Math.floor(pos), hi = Math.ceil(pos);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }

  function stats(values) {
    const v = values.filter((x) => typeof x === 'number' && !Number.isNaN(x)).sort((a, b) => a - b);
    if (!v.length) return null;
    return {
      n: v.length, min: v[0], max: v[v.length - 1],
      p25: quantile(v, 0.25), median: quantile(v, 0.5), p75: quantile(v, 0.75),
      mean: v.reduce((s, x) => s + x, 0) / v.length,
    };
  }

  const cleanTag = (t) => String(t || '').trim().replace(/^(掌握|熟悉|了解|精通)/, '');
  // salary_raw 在不同来源里既可能是字符串也可能是解析对象（{raw: "150-200元/天"}），统一取值
  const salaryText = (job) => {
    const v = job && job.salary_raw;
    if (!v) return '';
    if (typeof v === 'string') return v;
    if (typeof v === 'object') return String(v.raw || v.note || '');
    return String(v);
  };
  const isInternSalary = (job) => {
    const raw = salaryText(job);
    return Boolean(job && job.day_mid) && (raw.indexOf('元/天') >= 0 || (raw.indexOf('K') >= 0 && String(job.title || '').indexOf('实习') >= 0));
  };
  const TAG_RELEVANT = /python|java|mysql|redis|sql|linux|git|docker|kubernetes|spring|springboot|mybatis|springcloud|django|flask|fastapi|scrapy|爬虫|算法|人工智能|机器学习|深度学习|大模型|llm|nlp|视觉|数据分析|数据挖掘|数据仓库|hadoop|spark|flink|etl|前端|后端|全栈|javascript|typescript|vue|react|node|html|css|小程序|android|ios|鸿蒙|测试|自动化测试|运维|云计算|c\+\+|golang|go语言|javascript|嵌入式|qt|opencv|tensorflow|pytorch|pandas|numpy|matlab|网络|安全|渗透|数据库|微服务|分布式|dubbo|kafka|rabbitmq|消息队列|接口|restful|http|数据结构|计算机|软件工程|操作系统|网络编程/i;
  // 与招聘需求无关的字段（班制、结算、福利类）
  const TAG_NOISE = /长白班|做六休一|月结|员工关系|招聘|财产险|包吃|包住|双休|五险|提供转正|接受大一大二|暑期|寒假|远程|在校|不限|面议|办公|坐班|班制|福利|社保|津贴|补贴|奖金|毕业|学历|本科|硕士|大专|博士|专业|应届|居家|销售|客服|普通话|经验/;

  const state = { rows: [], sortKey: 'daypay', sortDir: -1, filters: {} };

  async function load() {
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
  }

  function renderKpis(data, wuhan, interns) {
    const inv = ((data.inventory || {}).rows || []).filter((r) => r.platform === 'BOSS直聘');
    const invPy = inv.find((r) => r.keyword === 'Python实习')?.resCount;
    const invJv = inv.find((r) => r.keyword === 'Java实习')?.resCount;
    const zn = {};
    for (const r of ((data.inventory || {}).rows || []).filter((x) => x.platform === '智联招聘')) zn[r.keyword] = r.resCount;
    const techInt = interns.filter((j) => (j.stacks || []).length);
    const techPy = techInt.filter((j) => j.stacks.includes('Python')).length;
    const techJv = techInt.filter((j) => j.stacks.includes('Java')).length;
    const byStack = (name) => interns.filter((j) => j.stacks.includes(name));
    const py = byStack('Python'), jv = byStack('Java'), al = byStack('算法/AI');
    const isScope = isInternSalary;
    const pySal = stats(py.filter(isScope).map((j) => j.day_mid));
    const jvSal = stats(jv.filter(isScope).map((j) => j.day_mid));
    const techSal = stats(techInt.filter(isScope).map((j) => j.day_mid));
    const diff = pySal && jvSal && jvSal.median ? ((pySal.median - jvSal.median) / jvSal.median) * 100 : 0;
    const bossRatio = invPy && invJv ? (invPy / invJv) : null;
    const znRatio = zn['Python实习'] && zn['Java实习'] ? (zn['Python实习'] / zn['Java实习']) : null;

    const cards = [
      { label: '本次抓取岗位总量', value: (data.summary || {}).total_rows ?? data.total_rows ?? '—', note: `武汉相关 ${wuhan.length} 条 · 实习 ${interns.length} 条` },
      {
        label: 'Python : Java 需求比', cls: 'py',
        value: bossRatio ? `${bossRatio.toFixed(2)} : 1` : '—',
        note: bossRatio ? `BOSS直聘平台库存量 ${invPy} : ${invJv}（同平台同口径）` : '缺少平台库存量数据',
      },
      {
        label: '智联招聘同口径比值', cls: 'jv',
        value: znRatio ? `${znRatio.toFixed(2)} : 1` : '—',
        note: znRatio ? `Python实习 ${zn['Python实习']} 条 vs Java实习 ${zn['Java实习']} 条` : '缺少智联库存量',
      },
      { label: '技术类实习岗', value: techInt.length, note: `中位 ${fmt(techSal && techSal.median)} 元/天 · 样本 ${techSal ? techSal.n : 0}` },
      { label: 'Python 实习岗样本', cls: 'py', value: py.length, note: pySal ? `中位 ${fmt(pySal.median)} 元/天 · 薪资样本 ${pySal.n}` : '样本不足' },
      { label: 'Java 实习岗样本', cls: 'jv', value: jv.length, note: jvSal ? `中位 ${fmt(jvSal.median)} 元/天 · 薪资样本 ${jvSal.n}` : '样本不足' },      {
        label: 'Python vs Java 薪资差', cls: 'al',
        value: `${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%`,
        note: `以 Java 中位数为基准 · Python ${fmt(pySal && pySal.median)} / Java ${fmt(jvSal && jvSal.median)}`,
      },
      { label: '算法/AI 实习岗', cls: 'al', value: al.length, note: `占技术类实习 ${(al.length / Math.max(1, techInt.length) * 100).toFixed(0)}%` },
    ];

    document.getElementById('kpiRow').innerHTML = cards.map((c) => `
      <div class="kpi ${c.cls || ''}">
        <div class="label">${esc(c.label)}</div>
        <div class="value">${esc(c.value)}${c.unit ? `<small>${esc(c.unit)}</small>` : ''}</div>
        <div class="note">${esc(c.note || '')}</div>
      </div>`).join('');
  }

  function renderMethod(summary, jobs) {
    const src = summary.generated_from || {};
    const wuhanBySource = {};
    for (const j of jobs) if (j.is_wuhan) wuhanBySource[j.source] = (wuhanBySource[j.source] || 0) + 1;
    const cards = [
      {
        name: '智联招聘', rows: src['智联招聘'] || 0, wuhan: wuhanBySource['智联招聘'] || 0,
        how: '武汉站搜索结果页（服务端渲染）解析，关键词：实习生 / Python实习 / Java实习 / 后端开发实习 / 软件开发实习 / 测试实习，翻页取满。',
        tag: '薪资为明码标价', warn: false,
      },
      {
        name: 'BOSS直聘', rows: src['BOSS直聘'] || 0, wuhan: wuhanBySource['BOSS直聘'] || 0,
        how: '反检测 Chromium（scrapling StealthyFetcher）人工登录一次后，由页面自身的 joblist 接口逐页取数；覆盖 12 组关键词，含薪资、到岗天数、实习月数、学历、技能标签。',
        tag: '已抓到 291 条带薪资岗位（152 条元/天 + 133 条 K/月）', warn: false,
      },
      {
        name: '实习僧', rows: src['实习僧'] || 0, wuhan: wuhanBySource['实习僧'] || 0,
        how: '武汉实习列表页真实浏览器渲染提取，12 组关键词（Python / Java / 算法 / 人工智能 / 开发 / 软件 / 研发 / 测试 / 数据 等）。',
        tag: '薪资为反爬字体，已按字形解码还原', warn: false,
      },
      {
        name: '猎聘', rows: src['猎聘'] || 0, wuhan: wuhanBySource['猎聘'] || 0,
        how: '关键词搜索列表渲染提取，仅保留城市为武汉的岗位（其余全国岗位已剔除）：Python/Java/后端/前端等 7 组关键词。',
        tag: '武汉样本较少，仅作交叉验证', warn: true,
      },
    ];
    document.getElementById('methodGrid').innerHTML = cards.map((c) => `
      <div class="method-card">
        <div class="name"><span class="dot"></span>${esc(c.name)}</div>
        <div class="row">抓取 ${c.rows} 条 · 武汉 ${c.wuhan} 条</div>
        <div class="row">${esc(c.how)}</div>
        <span class="tagline ${c.warn ? 'warn' : ''}">${esc(c.tag)}</span>
      </div>`).join('');

    const total = Object.values(src).reduce((s, v) => s + (v || 0), 0);
    document.getElementById('sourceHint').textContent = `本次合并 ${total} 条原始岗位（去重后 ${jobs.length} 条）`;
    const ts = new Date();
    document.getElementById('freshness').textContent = `数据快照：${ts.getFullYear()}-${String(ts.getMonth() + 1).padStart(2, '0')}-${String(ts.getDate()).padStart(2, '0')} · 抓取自公开搜索页`;
    document.getElementById('footNote').textContent = `看板由本次抓取数据实时计算 · 岗位共 ${jobs.length} 条 · 生成时间 ${ts.toLocaleString('zh-CN')}`;
  }

  function renderStackChart(interns) {
    const c = mkChart('chartStack');
    if (!c) return;
    const counts = {};
    for (const j of interns) for (const s of j.stacks) counts[s] = (counts[s] || 0) + 1;
    const entries = Object.entries(counts).sort((a, b) => a[1] - b[1]);
    const techTotal = interns.filter((j) => j.stacks.length).length;
    const maxVal = Math.max(1, ...entries.map((e) => e[1]));
    c.setOption({
      // 左侧留出分类标签宽度，右侧留出条形末端数字的空间（否则最大值会被裁掉）
      grid: { left: 96, right: 78, top: 34, bottom: 32, containLabel: false },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: (p) => {
          const name = p[0].name, v = p[0].value;
          return `${name}<br/>实习岗位 ${v} 个（占技术类实习 ${(v / Math.max(1, techTotal) * 100).toFixed(1)}%）`;
        },
      },
      xAxis: {
        type: 'value',
        nameTextStyle: axisText,
        axisLabel: { ...axisText, showMaxLabel: false },
        splitLine,
        max: Math.ceil((maxVal * 1.12) / 10) * 10,      // 给末端数字留白
        interval: maxVal > 250 ? 100 : (maxVal > 60 ? 50 : 10),  // 整齐刻度，避免末位刻度挤在一起
      },
      yAxis: { type: 'category', data: entries.map((e) => e[0]), axisLabel: { ...axisText, fontSize: 12.5 }, axisTick: { show: false } },
      series: [{
        type: 'bar', data: entries.map((e) => ({ value: e[1], itemStyle: { color: stackColor(e[0]), borderRadius: [0, 4, 4, 0] } })),
        barMaxWidth: 20,
        label: { show: true, position: 'right', color: C.ink2, fontSize: 12, distance: 6 },
      }],
    });
  }

  function renderPlatformChart(jobs) {
    const c = mkChart('chartPlatform');
    if (!c) return;
    const wuhan = jobs.filter((j) => j.is_wuhan);
    const bySource = {};
    for (const j of wuhan) {
      bySource[j.source] = bySource[j.source] || { intern: 0, other: 0 };
      if (j.intern) bySource[j.source].intern += 1; else bySource[j.source].other += 1;
    }
    const names = Object.keys(bySource);
    c.setOption({
      title: { text: '武汉岗位 · 按来源', left: 'center', top: 0, textStyle: { fontSize: 13, color: C.ink2, fontWeight: 600 } },
      grid: { ...baseGrid, top: 56 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (p) => `${p[0].name}<br/>${p.map((x) => `${x.seriesName} ${x.value} 条`).join('<br/>')}` },
      legend: { top: 26, textStyle: axisText, itemWidth: 10, itemHeight: 10 },
      xAxis: { type: 'category', data: names, axisLabel: axisText, axisTick: { show: false } },
      yAxis: { type: 'value', name: '岗位数', nameTextStyle: axisText, axisLabel: axisText, splitLine },
      series: [
        { name: '实习岗', type: 'bar', stack: 's', barMaxWidth: 34, itemStyle: { color: C.accent, borderRadius: [0, 0, 0, 0] }, label: { show: true, color: '#fff', fontSize: 11 }, data: names.map((n) => bySource[n].intern) },
        { name: '非实习/未标注', type: 'bar', stack: 's', barMaxWidth: 34, itemStyle: { color: '#cbd5e1' }, label: { show: true, color: C.ink2, fontSize: 11 }, data: names.map((n) => bySource[n].other) },
      ],
    });
  }

  function renderSalaryDist(interns, summary) {
    const c = mkChart('chartSalaryDist');
    if (!c) return;
    const sc = summary.salary_scope || {};
    const st = (summary.salary_stats || {}).all_interns || {};
    const buckets = (summary.salary_hist_all || []).map((b) => b.name);
    const counts = (summary.salary_hist_all || []).map((b) => b.count);
    const total = counts.reduce((s, v) => s + v, 0) || 1;
    const colors = ['#bfd7ea', '#8ab6d6', '#5b93c4', '#2f6fa8', '#1b4f80'];
    c.setOption({
      title: {
        text: `实习岗薪资分布（n=${total}）· 元/天口径 ${sc.daily ?? 0} + K/月折算 ${sc.monthly_k ?? 0}`,
        left: 'center', top: 0, textStyle: { fontSize: 12.5, color: C.ink2, fontWeight: 500 },
      },
      grid: { ...baseGrid, top: 48 },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: (p) => `${p[0].name} 元/天<br/>岗位 ${p[0].value} 个（占 ${(p[0].value / total * 100).toFixed(1)}%）`,
      },
      xAxis: { type: 'category', data: buckets, axisLabel: axisText, axisTick: { show: false }, name: '元/天', nameTextStyle: axisText },
      yAxis: { type: 'value', name: '岗位数', nameTextStyle: axisText, axisLabel: axisText, splitLine },
      series: [{
        type: 'bar', barMaxWidth: 46,
        data: counts.map((v, i) => ({ value: v, itemStyle: { color: colors[i], borderRadius: [4, 4, 0, 0] } })),
        label: { show: true, position: 'top', color: C.ink2, fontSize: 12 },
      }],
    });
  }

  function renderSalaryStack(interns, summary) {
    const c = mkChart('chartSalaryStack');
    if (!c) return;
    const isScope = isInternSalary;
    const stacks = ['Python', 'Java', '算法/AI'];
    const rows = stacks.map((s) => ({
      name: s,
      vals: interns.filter((j) => j.stacks.includes(s) && isScope(j)).map((j) => j.day_mid),
    })).filter((r) => r.vals.length >= 2);
    if (!rows.length) { c.setOption({ title: { text: '样本不足', left: 'center', top: '40%', textStyle: { color: C.ink3, fontSize: 13 } } }); return; }
    c.setOption({
      grid: { ...baseGrid, left: 16, top: 46, right: 30 },
      tooltip: {
        trigger: 'item',
        formatter: (p) => {
          if (p.seriesType === 'boxplot') {
            const v = p.value; // [idx, low, q1, median, q3, high]
            return `${p.name}<br/>最低 ${fmt(v[1])} · P25 ${fmt(v[2])}<br/>中位 ${fmt(v[3])} · P75 ${fmt(v[4])}<br/>最高 ${fmt(v[5])} 元/天`;
          }
          return `${p.name}<br/>样本 ${p.value[1]} 个`;
        },
      },
      xAxis: { type: 'category', data: rows.map((r) => r.name), axisLabel: axisText, axisTick: { show: false } },
      yAxis: { type: 'value', name: '元/天', nameTextStyle: axisText, axisLabel: axisText, splitLine },
      series: [
        {
          name: '薪资分布', type: 'boxplot',
          itemStyle: { borderWidth: 1.5 },
          data: rows.map((r) => {
            const st = stats(r.vals);
            return {
              value: [st.min, st.p25, st.median, st.p75, st.max],
              itemStyle: { color: stackColor(r.name), borderColor: stackColor(r.name), opacity: 0.55 },
            };
          }),
          boxWidth: [12, 46],
        },
        {
          name: '样本数', type: 'scatter', symbolSize: 1,
          data: rows.map((r, i) => ({ value: [i, stats(r.vals).min], label: { show: true, formatter: `n=${stats(r.vals).n}`, position: 'bottom', color: C.ink3, fontSize: 11.5 } })),
          label: { show: true, formatter: (p) => p.data.label.formatter, position: 'bottom', color: C.ink3, fontSize: 11.5 },
        },
      ],
    });
  }

  function renderSalaryTable(interns) {
    const targets = ['Python', 'Java', '算法/AI', 'C/C++', '前端', '测试'];
    const isScope = isInternSalary;
    const cards = targets.map((name) => {
      const vals = interns.filter((j) => j.stacks.includes(name) && isScope(j)).map((j) => j.day_mid);
      const st = stats(vals);
      if (!st) return null;
      return `
        <div class="mini-card">
          <div class="h">${esc(name)} · 样本 ${st.n}</div>
          <div class="v">${fmt(st.median)} <span>元/天 中位</span></div>
          <div class="h">P25 ${fmt(st.p25)} · P75 ${fmt(st.p75)} · 最高 ${fmt(st.max)}</div>
          <div class="h">折合月薪约 ${fmt(st.median * 21.75, 0)} 元</div>
        </div>`;
    }).filter(Boolean);
    document.getElementById('salaryTable').innerHTML = cards.join('');
  }

  function renderDegree(interns) {
    const c = mkChart('chartDegree');
    if (!c) return;
    const order = ['不限', '大专', '本科', '硕士', '博士', '中专/高中'];
    const counts = order.map((d) => interns.filter((j) => j.degree === d).length);
    const total = interns.length || 1;
    const named = interns.filter((j) => ['大专', '本科', '硕士', '博士'].includes(j.degree)).length;
    c.setOption({
      title: { text: `有学历要求的岗位中：${interns.filter((j) => j.degree === '本科').length} 条本科 · ${interns.filter((j) => j.degree === '硕士').length} 条硕士起（n=${named}）`, left: 'center', top: 0, textStyle: { fontSize: 12.5, color: C.ink2, fontWeight: 500 } },
      grid: { ...baseGrid, top: 46 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (p) => `${p[0].name}<br/>${p[0].value} 条（占全部实习 ${(p[0].value / total * 100).toFixed(1)}%）` },
      xAxis: { type: 'category', data: order, axisLabel: axisText, axisTick: { show: false } },
      yAxis: { type: 'value', name: '岗位数', nameTextStyle: axisText, axisLabel: axisText, splitLine },
      series: [{
        type: 'bar', barMaxWidth: 40,
        data: counts.map((v, i) => ({ value: v, itemStyle: { color: ['#94a3b8', '#7fa8c9', '#3776ab', '#7c5cff', '#5b21b6', '#cbd5e1'][i], borderRadius: [4, 4, 0, 0] } })),
        label: { show: true, position: 'top', color: C.ink2, fontSize: 12 },
      }],
    });
  }

  function renderWeeks(interns) {
    const c = mkChart('chartWeeks');
    if (!c) return;
    const days = {};
    const months = {};
    const asNum = (v) => Number(String(v ?? '').replace(/[一二三四五六七八九十]/, (ch) => '一二三四五六七八九十'.indexOf(ch) + 1));
    for (const j of interns) {
      const extra = j.extra || {};
      const rawDays = extra.days_week ?? extra.intern_days_week ?? null;
      const rawMonths = extra.months ?? extra.intern_months ?? null;
      let dn = asNum(String(rawDays ?? '').replace(/[^0-9一二三四五六七八九十]/g, ''));
      let mn = asNum(String(rawMonths ?? '').replace(/[^0-9一二三四五六七八九十]/g, ''));
      // BOSS 直聘把「4天/周」「3个月」放在标签里
      for (const t of j.tags || []) {
        const d2 = /(\d+)\s*天\/周/.exec(t);
        const m2 = /(\d+)\s*个月/.exec(t);
        if (d2 && !dn) dn = Number(d2[1]);
        if (m2 && !mn) mn = Number(m2[1]);
      }
      if (dn) days[dn] = (days[dn] || 0) + 1;
      if (mn) months[mn] = (months[mn] || 0) + 1;
    }
    const dKeys = Object.keys(days).map(Number).sort((a, b) => a - b);
    const mKeys = Object.keys(months).map(Number).sort((a, b) => a - b);
    const hasDays = dKeys.length > 0;

    c.setOption({
      title: {
        text: hasDays ? `每周到岗天数分布（n=${dKeys.reduce((s, k) => s + days[k], 0)}）` : '每周到岗天数：本次样本未采集到该字段',
        left: 'center', top: 0, textStyle: { fontSize: 13, color: C.ink2, fontWeight: 600 },
      },
      grid: { ...baseGrid, top: 44 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (p) => `每周 ${p[0].name} 天<br/>岗位 ${p[0].value} 个` },
      xAxis: {
        type: 'category', name: '天/周', nameTextStyle: axisText,
        data: hasDays ? dKeys : [1, 2, 3, 4, 5], axisLabel: axisText, axisTick: { show: false },
      },
      yAxis: { type: 'value', name: '岗位数', nameTextStyle: axisText, axisLabel: axisText, splitLine },
      series: [{
        type: 'bar', barMaxWidth: 44,
        data: (hasDays ? dKeys : [1, 2, 3, 4, 5]).map((k) => ({
          value: days[k] || 0,
          itemStyle: { color: k >= 4 ? C.accent : '#94a3b8', borderRadius: [4, 4, 0, 0] },
        })),
        label: { show: true, position: 'top', color: C.ink2, fontSize: 12 },
      }],
    });

    const totalMonths = mKeys.reduce((s, k) => s + months[k], 0);
    const share = (k) => (totalMonths ? `${(months[k] / totalMonths * 100).toFixed(0)}%` : '—');
    document.getElementById('durationTable').innerHTML = `
      <div class="mini-card">
        <div class="h">实习总月数 · 样本 ${totalMonths}</div>
        <div class="v">${mKeys.length ? `${mKeys[0]}–${mKeys[mKeys.length - 1]} <span>个月</span>` : '—'}</div>
        <div class="h">分布：${mKeys.map((k) => `${k} 个月 ${months[k]} 个`).join(' · ') || '未采集到'}</div>
      </div>
      <div class="mini-card">
        <div class="h">每周到岗要求</div>
        <div class="v">${hasDays ? `≥4 天 <span>占比 ${((dKeys.filter((k) => k >= 4).reduce((s, k) => s + days[k], 0)) / Math.max(1, dKeys.reduce((s, k) => s + days[k], 0)) * 100).toFixed(0)}%</span>` : '—'}</div>
        <div class="h">${hasDays ? dKeys.map((k) => `${k} 天/周 ${days[k]} 个`).join(' · ') : '未采集到该字段'}</div>
      </div>
      <div class="mini-card">
        <div class="h">转正机会</div>
        <div class="v">${interns.filter((j) => /转正/.test(`${j.title} ${salaryText(j)}`)).length} <span>个岗位标题标注可转正</span></div>
        <div class="h">实习僧岗位普遍在岗位描述中标注“可转正实习”</div>
      </div>`;
  }

  function renderCompanies(interns) {
    const c = mkChart('chartCompanies');
    if (!c) return;
    const counts = {};
    for (const j of interns) if (j.company) counts[j.company] = (counts[j.company] || 0) + 1;
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 12).reverse();
    c.setOption({
      title: { text: '招聘实习岗位最多的公司（武汉）', left: 'center', top: 0, textStyle: { fontSize: 13, color: C.ink2, fontWeight: 600 } },
      grid: { left: 132, right: 60, top: 40, bottom: 32, containLabel: false },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (p) => `${p[0].name}<br/>实习岗位 ${p[0].value} 个` },
      xAxis: { type: 'value', name: '岗位数', nameTextStyle: axisText, axisLabel: axisText, splitLine },
      yAxis: {
        type: 'category', data: top.map((t) => (t[0].length > 10 ? `${t[0].slice(0, 9)}…` : t[0])),
        axisLabel: { ...axisText, fontSize: 12 }, axisTick: { show: false },
      },
      series: [{
        type: 'bar', barMaxWidth: 16,
        data: top.map((t) => ({ value: t[1], itemStyle: { color: C.accent, borderRadius: [0, 4, 4, 0] } })),
        label: { show: true, position: 'right', color: C.ink2, fontSize: 12 },
      }],
    });
  }

  function renderTags(interns, tagsData) {
    const c = mkChart('chartTags');
    if (!c) return;
    const counts = {};
    for (const j of interns) {
      for (const raw of j.tags || []) {
        const t = cleanTag(raw);
        if (!t || TAG_NOISE.test(t) || !TAG_RELEVANT.test(t)) continue;
        counts[t] = (counts[t] || 0) + 1;
      }
    }
    let top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 14).reverse();
    if (!top.length) {
      const src = (tagsData.skills && tagsData.skills.length ? tagsData.skills : tagsData.tags) || [];
      top = src.filter(([t]) => TAG_RELEVANT.test(t) && !TAG_NOISE.test(t)).slice(0, 14).reverse();
    }
    c.setOption({
      title: { text: '岗位技能标签词频（技术类过滤后）', left: 'center', top: 0, textStyle: { fontSize: 13, color: C.ink2, fontWeight: 600 } },
      grid: { left: 132, right: 60, top: 40, bottom: 32, containLabel: false },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (p) => `${p[0].name}<br/>出现 ${p[0].value} 次` },
      xAxis: { type: 'value', name: '出现次数', nameTextStyle: axisText, axisLabel: axisText, splitLine },
      yAxis: { type: 'category', data: top.map((t) => t[0]), axisLabel: { ...axisText, fontSize: 12 }, axisTick: { show: false } },
      series: [{
        type: 'bar', barMaxWidth: 16,
        data: top.map((t) => {
          const name = t[0].toLowerCase();
          const color = /python|django|flask|fastapi|scrapy|爬虫|pandas|numpy/.test(name) ? C.python
            : /java|spring|mybatis|dubbo|jvm/.test(name) ? C.java
            : /算法|机器学习|深度学习|大模型|llm|nlp|视觉|人工智能|opencv|tensorflow|pytorch/.test(name) ? C.algo
            : C.accent;
          return { value: t[1], itemStyle: { color, borderRadius: [0, 4, 4, 0] } };
        }),
        label: { show: true, position: 'right', color: C.ink2, fontSize: 12 },
      }],
    });
  }

  function renderCompanyPanel(panel) {
    if (!panel) return;
    const open = mkChart('chartCompanyOpen');
    if (open) {
      const rows = (panel.top_by_intern_roles || []).slice(0, 12).reverse();
      open.setOption({
        title: { text: '公司对比：本次实习岗位 vs 在招职位总数', left: 'center', top: 0, textStyle: { fontSize: 13, color: C.ink2, fontWeight: 600 } },
        grid: { left: 132, right: 78, top: 40, bottom: 32, containLabel: false },
        tooltip: {
          trigger: 'axis', axisPointer: { type: 'shadow' },
          formatter: (p) => {
            const r = (panel.top_by_intern_roles || []).slice(0, 12).reverse()[p[0].dataIndex];
            return `${r.company}<br/>实习岗 ${r.intern_roles} 个 · 在招 ${r.open_jobs} 个职位 / ${r.bosses} 位招聘者<br/>${r.stage || '-'} · ${r.size || '-'} · ${r.industry || '-'}<br/>${(r.intern_titles || []).join('；')}`;
          },
        },
        legend: { top: 22, textStyle: axisText, itemWidth: 10, itemHeight: 10 },
        xAxis: { type: 'value', name: '数量', nameTextStyle: axisText, axisLabel: axisText, splitLine },
        yAxis: {
          type: 'category',
          data: rows.map((r) => ((r.company || '').length > 10 ? `${(r.company || '').slice(0, 9)}…` : r.company)),
          axisLabel: { ...axisText, fontSize: 12 }, axisTick: { show: false },
        },
        series: [
          {
            name: '本次实习岗', type: 'bar', barMaxWidth: 14,
            data: rows.map((r) => ({ value: r.intern_roles, itemStyle: { color: C.accent, borderRadius: [0, 3, 3, 0] } })),
            label: { show: true, position: 'right', color: C.ink2, fontSize: 11 },
          },
          {
            name: '公司在招职位', type: 'bar', barMaxWidth: 14,
            data: rows.map((r) => ({ value: r.open_jobs, itemStyle: { color: '#cbd5e1', borderRadius: [0, 3, 3, 0] } })),
            label: { show: true, position: 'right', color: C.ink3, fontSize: 11 },
          },
        ],
      });
    }

    const size = mkChart('chartCompanySize');
    if (size) {
      const order = ['少于20人', '20-99人', '100-499人', '500-999人', '1000-9999人', '10000人以上'];
      const dist = new Map((panel.size_dist || []).map(([k, v]) => [k, v]));
      const keys = order.filter((k) => dist.has(k)).concat([...dist.keys()].filter((k) => !order.includes(k)));
      size.setOption({
        title: { text: '招聘实习岗的公司规模分布', left: 'center', top: 0, textStyle: { fontSize: 13, color: C.ink2, fontWeight: 600 } },
        grid: { ...baseGrid, top: 40 },
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (p) => `${p[0].name}<br/>${p[0].value} 家公司` },
        xAxis: { type: 'category', data: keys, axisLabel: { ...axisText, interval: 0, fontSize: 11.5 }, axisTick: { show: false } },
        yAxis: { type: 'value', name: '公司数', nameTextStyle: axisText, axisLabel: axisText, splitLine },
        series: [{
          type: 'bar', barMaxWidth: 40,
          data: keys.map((k) => ({ value: dist.get(k) || 0, itemStyle: { color: C.accent, borderRadius: [4, 4, 0, 0] } })),
          label: { show: true, position: 'top', color: C.ink2, fontSize: 12 },
        }],
      });
    }

    const stage = mkChart('chartCompanyStage');
    if (stage) {
      const rows = (panel.stage_dist || []).slice(0, 8);
      stage.setOption({
        title: { text: '招聘实习岗的公司融资阶段', left: 'center', top: 0, textStyle: { fontSize: 13, color: C.ink2, fontWeight: 600 } },
        grid: { ...baseGrid, top: 40 },
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (p) => `${p[0].name}<br/>${p[0].value} 家公司` },
        xAxis: { type: 'category', data: rows.map((r) => r[0]), axisLabel: { ...axisText, interval: 0, fontSize: 11 }, axisTick: { show: false } },
        yAxis: { type: 'value', name: '公司数', nameTextStyle: axisText, axisLabel: axisText, splitLine },
        series: [{
          type: 'bar', barMaxWidth: 36,
          data: rows.map((r) => ({ value: r[1], itemStyle: { color: '#7c5cff', borderRadius: [4, 4, 0, 0] } })),
          label: { show: true, position: 'top', color: C.ink2, fontSize: 12 },
        }],
      });
    }

    const industry = mkChart('chartCompanyIndustry');
    if (industry) {
      const rows = (panel.industry_dist || []).slice(0, 10).reverse();
      industry.setOption({
        title: { text: '招聘实习岗的公司行业分布', left: 'center', top: 0, textStyle: { fontSize: 13, color: C.ink2, fontWeight: 600 } },
        grid: { left: 132, right: 60, top: 40, bottom: 32, containLabel: false },
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (p) => `${p[0].name}<br/>${p[0].value} 家公司` },
        xAxis: { type: 'value', name: '公司数', nameTextStyle: axisText, axisLabel: axisText, splitLine },
        yAxis: { type: 'category', data: rows.map((r) => r[0]), axisLabel: { ...axisText, fontSize: 12 }, axisTick: { show: false } },
        series: [{
          type: 'bar', barMaxWidth: 16,
          data: rows.map((r) => ({ value: r[1], itemStyle: { color: '#0e7490', borderRadius: [0, 4, 4, 0] } })),
          label: { show: true, position: 'right', color: C.ink2, fontSize: 12 },
        }],
      });
    }

    const rows = (panel.top_by_open_jobs || []).slice(0, 8);
    document.getElementById('companyTable').innerHTML = `
      <div class="mini-card">
        <div class="h">已解析企业档案</div>
        <div class="v">${panel.profiles_collected} <span>家</span></div>
        <div class="h">其中 ${panel.companies_hiring_interns} 家本次在招实习岗</div>
      </div>
      <div class="mini-card">
        <div class="h">这些公司在招职位合计</div>
        <div class="v">${panel.total_open_jobs} <span>个</span></div>
        <div class="h">含实习、校招与社招，反映企业整体招聘体量</div>
      </div>
      ${rows.map((r) => `
        <div class="mini-card">
          <div class="h">${esc(r.company)}${r.stage || r.size ? ` · ${esc(r.stage || '—')} · ${esc(r.size || '—')}` : ''}</div>
          <div class="v">${r.open_jobs} <span>个在招职位 / ${r.bosses} 位招聘者</span></div>
          <div class="h">本次实习岗 ${r.intern_roles} 个：${esc((r.intern_titles || []).join('；') || '—')}</div>
        </div>`).join('')}`;
  }
  function renderInventory(data) {
    const c = mkChart('chartInventory');
    const allRows = ((data.inventory || {}).rows || []);
    const inv = allRows.filter((r) => r.platform === 'BOSS直聘').slice().sort((a, b) => (a.resCount || 0) - (b.resCount || 0));
    const zn = {};
    for (const r of allRows.filter((x) => x.platform === '智联招聘')) zn[r.keyword] = r.resCount;
    const sxs = allRows.filter((r) => r.platform === '实习僧').sort((a, b) => b.resCount - a.resCount).slice(0, 6);
    if (c) {
      const rows = inv.slice().sort((a, b) => (a.resCount || 0) - (b.resCount || 0));
      c.setOption({
        title: {
          text: `BOSS直聘·武汉 各关键词的真实结果总数（resCount）`,
          left: 'center', top: 0, textStyle: { fontSize: 13, color: C.ink2, fontWeight: 600 },
        },
        grid: { left: 104, right: 80, top: 40, bottom: 32, containLabel: false },
        tooltip: {
          trigger: 'axis', axisPointer: { type: 'shadow' },
          formatter: (p) => `${p[0].name}<br/>结果总数 ${p[0].value} 条<br/>本次抓取 ${rows[p[0].dataIndex].collected ?? '-'} 条`,
        },
        xAxis: { type: 'value', nameTextStyle: axisText, axisLabel: axisText, splitLine },
        yAxis: { type: 'category', data: rows.map((r) => r.keyword), axisLabel: { ...axisText, fontSize: 12 }, axisTick: { show: false } },
        series: [{
          type: 'bar', barMaxWidth: 18,
          data: rows.map((r) => ({
            value: r.resCount,
            itemStyle: { color: r.keyword.startsWith('Python') ? C.python : r.keyword.startsWith('Java') ? C.java : C.accent, borderRadius: [0, 4, 4, 0] },
          })),
          label: { show: true, position: 'right', color: C.ink2, fontSize: 12 },
        }],
      });
    }

    const py = inv.find((r) => r.keyword === 'Python实习');
    const jv = inv.find((r) => r.keyword === 'Java实习');
    const ratio = py && jv && jv.resCount ? (py.resCount / jv.resCount).toFixed(2) : '—';
    const znPy = zn['Python实习'];
    const znJv = zn['Java实习'];
    const znRatio = znPy && znJv ? (znPy / znJv).toFixed(2) : '—';
    const sxsPy = sxs.find((r) => r.keyword === 'Python')?.resCount;
    const sxsJv = sxs.find((r) => r.keyword === 'Java')?.resCount;
    document.getElementById('inventoryTable').innerHTML = `
      <div class="mini-card">
        <div class="h">BOSS直聘：Python实习 vs Java实习</div>
        <div class="v">${py ? py.resCount : '—'} <span>: ${jv ? jv.resCount : '—'}</span></div>
        <div class="h">比值 ${ratio} : 1（同平台、同城市、同口径，来自登录态实测的接口 resCount）</div>
      </div>
      <div class="mini-card">
        <div class="h">智联招聘：Python实习 vs Java实习</div>
        <div class="v">${znPy ?? '—'} <span>: ${znJv ?? '—'}</span></div>
        <div class="h">比值 ${znRatio} : 1（页面 positionCount 展示总数）</div>
      </div>
      <div class="mini-card">
        <div class="h">实习僧：关键词首屏召回</div>
        <div class="v">${sxsPy ?? '—'} <span>: ${sxsJv ?? '—'}</span></div>
        <div class="h">该站列表页读不到总量，只用首屏卡片数做方向性对照</div>
      </div>
      <div class="mini-card">
        <div class="h">为什么单看这个指标最干净</div>
        <div class="v">${inv.length} <span>个关键词已实测</span></div>
        <div class="h">它是平台自己报的库存量：不随抓取翻页数变化，也不会像"Java实习"那样把别的语言岗位混进来</div>
      </div>`;
  }

  function renderTracks(tracks) {
    if (!tracks || !tracks.rows) return;
    const rows = tracks.rows.filter((r) => r.intern.postings || r.fulltime.postings);
    const c = mkChart('chartTracks');
    if (c) {
      const data = rows.slice().sort((a, b) => a.intern.postings - b.intern.postings);
      c.setOption({
        title: { text: '需求规模：实习岗 vs 正式岗（武汉）', left: 'center', top: 0, textStyle: { fontSize: 13, color: C.ink2, fontWeight: 600 } },
        grid: { left: 78, right: 72, top: 44, bottom: 32, containLabel: false },
        tooltip: {
          trigger: 'axis', axisPointer: { type: 'shadow' },
          formatter: (p) => {
            const r = data[p[0].dataIndex];
            return `${r.direction}<br/>实习岗 ${r.intern.postings} 个<br/>正式岗 ${r.fulltime.postings} 个`;
          },
        },
        legend: { top: 24, textStyle: axisText, itemWidth: 10, itemHeight: 10 },
        xAxis: { type: 'value', nameTextStyle: axisText, axisLabel: axisText, splitLine },
        yAxis: { type: 'category', data: data.map((r) => r.direction), axisLabel: { ...axisText, fontSize: 12 }, axisTick: { show: false } },
        series: [
          {
            name: '实习岗', type: 'bar', barMaxWidth: 12,
            data: data.map((r) => ({ value: r.intern.postings, itemStyle: { color: C.accent, borderRadius: [0, 3, 3, 0] } })),
            label: { show: true, position: 'right', color: C.ink2, fontSize: 11 },
          },
          {
            name: '正式岗', type: 'bar', barMaxWidth: 12,
            data: data.map((r) => ({ value: r.fulltime.postings, itemStyle: { color: '#f59e0b', borderRadius: [0, 3, 3, 0] } })),
            label: { show: true, position: 'right', color: C.ink2, fontSize: 11 },
          },
        ],
      });
    }

    const g = mkChart('chartTracksGrowth');
    if (g) {
      const data = rows.filter((r) => r.intern.month && r.intern.month.n && r.fulltime.month && r.fulltime.month.n);
      const cats = data.map((r) => r.direction);
      g.setOption({
        title: { text: '薪资成长：实习折月薪 → 正式岗月薪', left: 'center', top: 0, textStyle: { fontSize: 13, color: C.ink2, fontWeight: 600 } },
        grid: { ...baseGrid, top: 44, right: 60 },
        tooltip: {
          trigger: 'axis',
          formatter: (p) => {
            const r = data[p[0].dataIndex];
            const growth = r.intern.month.median ? ((r.fulltime.month.median / r.intern.month.median - 1) * 100) : 0;
            return `${r.direction}<br/>实习折月薪 ${r.intern.month.median} 元（n=${r.intern.month.n}）<br/>正式岗月薪 ${r.fulltime.month.median} 元（n=${r.fulltime.month.n}）<br/>成长倍数 ${(r.fulltime.month.median / Math.max(1, r.intern.month.median)).toFixed(2)}×（+${growth.toFixed(0)}%）`;
          },
        },
        legend: { top: 24, textStyle: axisText, itemWidth: 10, itemHeight: 10 },
        xAxis: { type: 'category', data: cats, axisLabel: axisText, axisTick: { show: false } },
        yAxis: { type: 'value', name: '元/月', nameTextStyle: axisText, axisLabel: axisText, splitLine },
        series: [
          { name: '实习折月薪', type: 'bar', barMaxWidth: 26, itemStyle: { color: '#8ab6d6', borderRadius: [4, 4, 0, 0] }, data: data.map((r) => r.intern.month.median) },
          { name: '正式岗月薪', type: 'bar', barMaxWidth: 26, itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] }, data: data.map((r) => r.fulltime.month.median) },
        ],
      });
    }

    const cards = rows
      .slice()
      .sort((a, b) => (b.intern.postings + b.fulltime.postings) - (a.intern.postings + a.fulltime.postings))
      .slice(0, 6)
      .map((r) => {
        const im = r.intern.month && r.intern.month.n ? r.intern.month.median : null;
        const fm = r.fulltime.month && r.fulltime.month.n ? r.fulltime.month.median : null;
        const mult = im && fm ? (fm / im).toFixed(2) : '—';
        return `
          <div class="mini-card">
            <div class="h">${esc(r.direction)}</div>
            <div class="v">${mult === '—' ? '—' : mult + '×'} <span>实习→正式 成长倍数</span></div>
            <div class="h">实习 ${r.intern.postings} 个（日薪中位 ${r.intern.daily && r.intern.daily.n ? r.intern.daily.median : '—'} 元/天） · 折月薪 ${im ?? '—'}</div>
            <div class="h">正式岗 ${r.fulltime.postings} 个 · 月薪中位 ${fm ?? '—'} 元</div>
          </div>`;
      });
    document.getElementById('tracksTable').innerHTML = cards.join('') +
      `<div class="mini-card"><div class="h">口径说明</div><div class="v">实习 ${'月薪'}</div>
        <div class="h">${esc((tracks.note || '').slice(0, 120))}</div></div>`;
  }

  /* ---------------- job table ---------------- */
  function stackBadges(stacks, job) {
    const tags = [];
    if (job) for (const t of job.tags || []) {
      const name = String(t).trim();
      if (name && /^[\x20-\x7e\u4e00-\u9fa5+#./\-]{1,14}$/.test(name) && !TAG_NOISE.test(name)) tags.push(name);
    }
    const uniq = [...new Set(tags)].slice(0, 3);
    const html = (stacks && stacks.length ? stacks : []).map((s) => {
      const cls = s === 'Python' ? 'py' : s === 'Java' ? 'jv' : (s === '算法/AI' ? 'al' : '');
      return `<span class="badge ${cls}">${esc(s)}</span>`;
    }).join('');
    const extra = uniq.length ? `<span class="badge" title="${esc(uniq.join(' / '))}">${esc(uniq[0])}${uniq.length > 1 ? ' +' + (uniq.length - 1) : ''}</span>` : '';
    return (html + extra) || '<span class="badge other">非技术</span>';
  }

  function applyFilters() {
    const { source, stack, degree, q, salaryOnly } = state.filters;
    return state.rows.filter((j) => {
      if (source && j.source !== source) return false;
      if (stack && !(j.stacks || []).includes(stack)) return false;
      if (degree && j.degree !== degree) return false;
      if (salaryOnly && !j.day_mid) return false;
      if (q) {
        const blob = `${j.title} ${j.company}`.toLowerCase();
        if (!blob.includes(q.toLowerCase())) return false;
      }
      return true;
    });
  }

  function sortedRows(rows) {
    const k = state.sortKey, dir = state.sortDir;
    const val = (j) => {
      switch (k) {
        case 'salary': return j.month_mid || 0;
        case 'daypay': return j.day_mid || 0;
        case 'stacks': return (j.stacks || []).join(',');
        case 'degree': return ['不限', '大专', '本科', '硕士', '博士'].indexOf(j.degree);
        default: return (j[k] || '').toString();
      }
    };
    return rows.slice().sort((a, b) => {
      const va = val(a), vb = val(b);
      if (typeof va === 'number' && typeof vb === 'number') {
        if (va === vb) return 0;
        return (va - vb) * dir;
      }
      if (va === vb) return 0;
      return String(va).localeCompare(String(vb), 'zh-CN') * dir;
    });
  }

  function renderTable() {
    const rows = sortedRows(applyFilters());
    const tbody = document.querySelector('#jobTable tbody');
    document.getElementById('tableCount').textContent = `共 ${rows.length} 条（全量 ${state.rows.length} 条）`;
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty">没有符合筛选条件的岗位</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map((j) => {
      const title = j.url ? `<a href="${esc(j.url)}" target="_blank" rel="noreferrer">${esc(j.title || '(未标注岗位名)')}</a>` : esc(j.title || '');
      const pay = j.day_mid ? `${fmt(j.day_mid)}<br/><small style="color:#8593a3">${esc(salaryText(j))}</small>` : `<span style="color:#8593a3">${esc(salaryText(j) || '面议')}</span>`;
      return `<tr>
        <td class="title">${title}</td>
        <td>${esc(j.company || '')}</td>
        <td class="num">${fmt(j.month_mid)}</td>
        <td class="num">${pay}</td>
        <td>${stackBadges(j.stacks, j)}</td>
        <td>${esc(j.degree || '')}</td>
        <td>${esc(j.district || '')}</td>
        <td><span class="badge src">${esc(j.source)}</span></td>
      </tr>`;
    }).join('');
  }

  function initFilters(interns) {
    const sources = [...new Set(interns.map((j) => j.source))];
    const stacksAll = [...new Set(interns.flatMap((j) => j.stacks || []))].sort();
    const degrees = ['不限', '中专/高中', '大专', '本科', '硕士', '博士'].filter((d) => interns.some((j) => j.degree === d));
    const fill = (id, items) => {
      const el = document.getElementById(id);
      el.innerHTML += items.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join('');
    };
    fill('fSource', sources);
    fill('fStack', stacksAll);
    fill('fDegree', degrees);
  }

  function renderInsights(interns, wuhan) {
    const data_inventory = (window.__INVENTORY__ || []);
    const sc = (window.__SUMMARY__ || {}).salary_scope || {};
    const byStack = (name) => interns.filter((j) => j.stacks.includes(name));
    const py = byStack('Python'), jv = byStack('Java'), al = byStack('算法/AI');
    const isScope = isInternSalary;
    const pySt = stats(py.filter(isScope).map((j) => j.day_mid));
    const jvSt = stats(jv.filter(isScope).map((j) => j.day_mid));
    const allSt = stats(interns.filter(isScope).map((j) => j.day_mid));
    const tech = interns.filter((j) => j.stacks.length);
    const districts = {};
    for (const j of interns) if (j.district) districts[j.district] = (districts[j.district] || 0) + 1;
    const topDist = Object.entries(districts).sort((a, b) => b[1] - a[1]).slice(0, 2);
    const degreeBean = interns.filter((j) => j.degree === '本科').length;
    const degreeMaster = interns.filter((j) => j.degree === '硕士' || j.degree === '博士').length;
    const topTags = (() => {
      const counts = {};
      for (const j of interns) for (const raw of j.tags || []) {
        const t = cleanTag(raw);
        if (t && TAG_RELEVANT.test(t) && !TAG_NOISE.test(t)) counts[t] = (counts[t] || 0) + 1;
      }
      return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 3);
    })();

    const items = [];
    const invRows = (data_inventory || []);
    const invPy2 = invRows.find((r) => r.keyword === 'Python实习')?.resCount;
    const invJv2 = invRows.find((r) => r.keyword === 'Java实习')?.resCount;
    if (invPy2 && invJv2) {
      items.push({
        text: `<b>需求侧：Python 岗位约为 Java 的 ${(invPy2 / invJv2).toFixed(2)} 倍（用平台库存量对比，最干净的口径）。</b>` +
          `BOSS直聘平台上，武汉「Python实习」返回 ${invPy2} 条结果、「Java实习」${invJv2} 条；` +
          `智联招聘同口径为 37 : 20（1.85 : 1）。两个平台、不同方法，结论一致：Python 岗位明显更多。`,
        src: `库存量 = 平台自己报的结果总数，不随抓取翻页数变化，也不会被"Java实习"这类词把 Python 岗位混进来`,
      });
    } else if (py.length && jv.length) {
      items.push({
        text: `<b>需求侧：本次抓到的 Python 样本 ${py.length} 个、Java ${jv.length} 个。</b>` +
          `注意这个数字受各平台关键词覆盖不均的影响（BOSS 只完成了部分关键词），做需求对比请以上方"平台库存量"为准。`,
        src: `样本：武汉实习岗 ${interns.length} 条，技术类 ${tech.length} 条`,
      });
    }
    if (pySt && jvSt) {
      const diff = ((pySt.median - jvSt.median) / jvSt.median) * 100;
      const same = Math.abs(diff) < 0.5;
      items.push({
        text: `<b>薪资侧：两者几乎相同（${same ? '中位数完全一致' : `差 ${Math.abs(diff).toFixed(1)}%`}）。</b>` +
          `Python 实习日薪中位 ${fmt(pySt.median)} 元/天（P25 ${fmt(pySt.p25)} / P75 ${fmt(pySt.p75)}，样本 ${pySt.n}），` +
          `Java 中位 ${fmt(jvSt.median)} 元/天（P25 ${fmt(jvSt.p25)} / P75 ${fmt(jvSt.p75)}，样本 ${jvSt.n}）；` +
          `极值都出现在少数高薪岗位（Python 最高 ${fmt(pySt.max)}、Java 最高 ${fmt(jvSt.max)} 元/天）。` +
          `结论：选方向看需求量，薪资差异不足以成为理由。`,
        src: `口径：实习岗本人报价，「元/天」直接采用、「K/月」按 21.75 工作日折算（K/月样本多为 BOSS 的实习岗，属真实口径差异）；折合月薪 Python 约 ${fmt(pySt.median * 21.75)} 元、Java 约 ${fmt(jvSt.median * 21.75)} 元`,
      });
    }
    if (al.length) {
      items.push({
        text: `<b>算法/AI 是武汉实习市场的最大单一方向。</b>共 ${al.length} 个岗位，占技术类实习的 ${(al.length / Math.max(1, tech.length) * 100).toFixed(0)}%，` +
          `且学历门槛更高：${al.filter((j) => ['硕士', '博士'].includes(j.degree)).length} 个岗位要求硕士及以上。大模型、视觉、智能体是高频关键词。`,
        src: '命中关键词：算法/机器学习/深度学习/大模型/LLM/NLP/视觉/智能体',
      });
    }
    if (allSt) {
      items.push({
        text: `<b>整体薪资带：</b>武汉计算机类实习日薪中位 ${fmt(allSt.median)} 元/天（${fmt(allSt.min)}–${fmt(allSt.max)}），` +
          `折合月薪中位约 ${fmt(allSt.median * 21.75)} 元；P25 ${fmt(allSt.p25)} / P75 ${fmt(allSt.p75)}，说明多数岗位集中在 ${fmt(allSt.p25)}–${fmt(allSt.p75)} 元/天。`,
        src: `有效薪资样本 ${allSt.n} / ${interns.length} 条（其余为面议或未标注）`,
      });
    }
    if (topDist.length) {
      items.push({
        text: `<b>地点集中度：</b>实习岗位主要聚集在 ${topDist.map(([d, n]) => `${d}（${n} 个）`).join('、')}，` +
          `光谷—洪山—江夏一线是武汉互联网与软件企业的主要承载区，通勤成本会直接影响投递选择。`,
        src: '区域字段来自招聘平台岗位标注',
      });
    }
    items.push({
      text: `<b>学历门槛：</b>全部武汉实习岗中，${degreeBean} 条明确要求本科、${degreeMaster} 条要求硕士及以上，其余为学历不限/大专；` +
        `学历不限岗位更多集中在中小规模公司与数据标注、开发辅助类岗位。`,
      src: '学历字段来自招聘平台岗位标注',
    });
    if (topTags.length) {
      items.push({
        text: `<b>技能准备优先级：</b>样本中出现频次最高的技术标签为 ${topTags.map(([t, n]) => `${t}（${n} 次）`).join('、')}。` +
          `Python 方向建议补齐“Python + SQL/MySQL + 数据处理库 + 一个真实项目”，Java 方向建议对齐“Java + Spring/MyBatis + MySQL + Redis”。`,
        src: '标签词频基于本次样本的岗位标签字段',
      });
    }
    document.getElementById('insightList').innerHTML = items.map((i) => `<div class="insight">${i.text}<span class="src">${esc(i.src || '')}</span></div>`).join('');
  }

  /* ---------------- boot ---------------- */
  (async () => {
    try {
      const data = await load();
      const jobs = data.jobs_master || [];
      const wuhan = jobs.filter((j) => j.is_wuhan);
      const interns = wuhan.filter((j) => j.intern);
      state.rows = interns;

      renderKpis(data, wuhan, interns);
      renderMethod(data.summary || {}, jobs);
      renderStackChart(interns);
      renderPlatformChart(jobs);
      renderTracks(data.tracks || null);
      renderInventory(data);
      window.__INVENTORY__ = ((data.inventory || {}).rows || []);
      window.__SUMMARY__ = data.summary || {};
      renderSalaryDist(interns, data.summary || {});
      renderSalaryStack(interns, data.summary || {});
      renderSalaryTable(interns);
      renderDegree(interns);
      renderWeeks(interns);
      renderCompanies(interns);
      renderTags(interns, data.tags || {});
      renderCompanyPanel(data.company_panel || null);
      initFilters(interns);
      renderTable();
      renderInsights(interns, wuhan);

      document.getElementById('fSource').addEventListener('change', (e) => { state.filters.source = e.target.value; renderTable(); });
      document.getElementById('fStack').addEventListener('change', (e) => { state.filters.stack = e.target.value; renderTable(); });
      document.getElementById('fDegree').addEventListener('change', (e) => { state.filters.degree = e.target.value; renderTable(); });
      document.getElementById('fSalaryOnly').addEventListener('change', (e) => { state.filters.salaryOnly = e.target.checked; renderTable(); });
      let t = null;
      document.getElementById('fQ').addEventListener('input', (e) => {
        clearTimeout(t);
        t = setTimeout(() => { state.filters.q = e.target.value.trim(); renderTable(); }, 160);
      });
      document.querySelectorAll('#jobTable thead th').forEach((th) => {
        th.addEventListener('click', () => {
          const key = th.dataset.sort;
          if (!key) return;
          if (state.sortKey === key) state.sortDir *= -1; else { state.sortKey = key; state.sortDir = key === 'title' || key === 'company' ? 1 : -1; }
          renderTable();
        });
      });
      if (!window.echarts) {
        document.querySelector('main').insertAdjacentHTML('afterbegin',
          '<div class="error">图表库（ECharts CDN）未能加载：请联网后刷新，或把 echarts.min.js 放到 dashboard/ 目录并改用本地引用；页面表格与指标仍可用。</div>');
      }
    } catch (err) {
      document.querySelector('main').insertAdjacentHTML('afterbegin', `<div class="error">数据加载失败：${esc(err.message)}<br/><b>请通过本地 HTTP 服务打开本页</b>（例如在本目录运行 <code>python -m http.server 19388</code> 后访问 http://127.0.0.1:19388/dashboard/ ），直接用 file:// 打开会被浏览器的跨域策略拦截。</div>`);
    }
  })();
})();
