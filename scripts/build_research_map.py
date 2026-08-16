#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成研究地图HTML可视化（方法×理论×主题）
采用纯静态 HTML + CSS 方案，确保无头渲染、打印、导出都稳定
"""
import json
import os

# 项目根目录（相对脚本定位，与 build_research_map_data.py 一致）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR = os.path.join(PROJECT_ROOT, 'scripts', '.tmp')
DATA_IN = os.path.join(TMP_DIR, 'research_map_data.json')
HTML_OUT = os.path.join(TMP_DIR, 'research_map.html')

def load_data():
    with open(DATA_IN, encoding='utf-8') as f:
        return json.load(f)

def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def heat_color(v, maxv, palette):
    """根据值返回颜色（从 palette 插值）"""
    if maxv == 0:
        idx = 0
    else:
        ratio = v / maxv
        idx = int(ratio * (len(palette) - 1))
        idx = max(0, min(idx, len(palette) - 1))
    return palette[idx]

def build_html(d):
    total = d['total']
    topic_count = d['topic_count']
    method_count = d['method_count']
    theory_count = d['theory_count']
    generated_at = d['generated_at']

    method_dist = d['method_dist']  # 已按高->低排序
    theory_dist = d['theory_dist']
    topic_heat = d['topic_heat']

    max_method = max(v for _, v in method_dist) if method_dist else 1
    max_theory = max(v for _, v in theory_dist) if theory_dist else 1
    max_topic = max(v for _, v in topic_heat) if topic_heat else 1

    # 渐变色系
    blue_palette = ['#eff6ff','#dbeafe','#bfdbfe','#93c5fd','#60a5fa','#3b82f6','#2563eb','#1d4ed8','#1e40af','#1e3a8a']
    pink_palette = ['#fff1f2','#ffe4e6','#fecdd3','#fda4af','#fb7185','#f43f5e','#e11d48','#be123c','#9f1239','#881337']

    # ========== 1. 方法分布（CSS横向条形图，静态）==========
    method_bars = []
    for name, val in reversed(method_dist):  # 从低到高，最大的在最下面
        pct = val / max_method * 100
        method_bars.append(f"""
        <div class="bar-row">
          <div class="bar-label">{name}</div>
          <div class="bar-wrap">
            <div class="bar" style="width:{pct:.1f}%;"></div>
            <span class="bar-num">{val}</span>
          </div>
        </div>""")
    method_html = '\n'.join(method_bars)

    # ========== 2. 理论框架分布（静态环形图用 conic-gradient）==========
    # 累积百分比
    total_theory = sum(v for _, v in theory_dist)
    theory_donut = []
    colors_theory = ['#3b82f6','#ec4899','#f59e0b','#10b981','#8b5cf6','#06b6d4','#ef4444','#84cc16','#6366f1','#a855f7','#f43f5e','#14b8a6']
    start = 0
    conic_parts = []
    for i, (name, val) in enumerate(theory_dist):
        pct = val / total_theory * 100
        end = start + pct
        color = colors_theory[i % len(colors_theory)]
        conic_parts.append(f"{color} {start:.2f}% {end:.2f}%")
        theory_donut.append(f"""
        <div class="legend-item"><span class="dot" style="background:{color}"></span><span>{name} <strong>{val}</strong> ({pct:.1f}%)</span></div>
        """)
        start = end
    donut_style = ','.join(conic_parts)

    # ========== 3. 主题热度（CSS横向条形图）==========
    topic_bars = []
    for name, val in reversed(topic_heat):
        pct = val / max_topic * 100
        topic_bars.append(f"""
        <div class="bar-row">
          <div class="bar-label topic-label">{name}</div>
          <div class="bar-wrap">
            <div class="bar topic" style="width:{pct:.1f}%;"></div>
            <span class="bar-num">{val}</span>
          </div>
        </div>""")
    topic_html = '\n'.join(topic_bars)

    # ========== 4. 方法×主题热力图 ==========
    top_methods = d['top_methods']
    matrix = d['method_topic_matrix']
    max_m = max(row.get(m, 0) for row in matrix for m in top_methods) if matrix else 1
    # 表头
    thead_m = ''.join(f'<th>{m}</th>' for m in top_methods)
    rows_m = []
    for row in matrix:
        tds = []
        for m in top_methods:
            v = row.get(m, 0)
            color = heat_color(v, max_m, blue_palette)
            text_color = '#fff' if v > max_m * 0.5 else '#1f2937'
            tds.append(f'<td style="background:{color};color:{text_color}">{v}</td>')
        rows_m.append(f'<tr><td class="row-label">{row["category"]}</td>' + ''.join(tds) + '</tr>')
    heat_m_html = f'<table class="heat-table"><thead><tr><th class="row-label">主题\\方法</th>{thead_m}</tr></thead><tbody>' + '\n'.join(rows_m) + '</tbody></table>'

    # ========== 5. 理论×主题热力图 ==========
    top_theories = d['top_theories']
    matrix_t = d['theory_topic_matrix']
    max_t = max(row.get(t, 0) for row in matrix_t for t in top_theories) if matrix_t else 1
    thead_t = ''.join(f'<th>{t}</th>' for t in top_theories)
    rows_t = []
    for row in matrix_t:
        tds = []
        for t in top_theories:
            v = row.get(t, 0)
            color = heat_color(v, max_t, pink_palette)
            text_color = '#fff' if v > max_t * 0.5 else '#1f2937'
            tds.append(f'<td style="background:{color};color:{text_color}">{v}</td>')
        rows_t.append(f'<tr><td class="row-label">{row["category"]}</td>' + ''.join(tds) + '</tr>')
    heat_t_html = f'<table class="heat-table theory"><thead><tr><th class="row-label">主题\\理论</th>{thead_t}</tr></thead><tbody>' + '\n'.join(rows_t) + '</tbody></table>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>体育新闻研究地图 · 方法×理论×主题</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB",sans-serif; background:#f4f6fb; color:#1a2b4a; line-height:1.5; }}
  .header {{ background:linear-gradient(135deg,#1e3a8a,#3b82f6); color:#fff; padding:36px 40px; }}
  .header h1 {{ font-size:28px; margin-bottom:8px; }}
  .header p {{ opacity:.85; font-size:14px; }}
  .stats {{ display:flex; gap:16px; margin-top:20px; flex-wrap:wrap; }}
  .stat-card {{ background:rgba(255,255,255,.12); backdrop-filter:blur(4px); border-radius:12px; padding:14px 24px; min-width:130px; }}
  .stat-card .num {{ font-size:30px; font-weight:bold; }}
  .stat-card .lbl {{ font-size:12px; opacity:.8; margin-top:2px; }}
  .container {{ max-width:1280px; margin:0 auto; padding:24px 20px 60px; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
  .grid.full {{ grid-template-columns:1fr; }}
  .card {{ background:#fff; border-radius:14px; padding:20px; box-shadow:0 2px 12px rgba(30,58,138,.08); }}
  .card h2 {{ font-size:16px; color:#1e3a8a; margin-bottom:4px; display:flex; align-items:center; gap:8px; }}
  .card .desc {{ font-size:12px; color:#6b7280; margin-bottom:16px; }}

  /* 条形图 */
  .bar-row {{ display:flex; align-items:center; margin-bottom:7px; font-size:12px; }}
  .bar-label {{ width:90px; text-align:right; padding-right:10px; color:#374151; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .bar-label.topic-label {{ width:120px; }}
  .bar-wrap {{ flex:1; display:flex; align-items:center; gap:8px; min-width:0; }}
  .bar {{ height:16px; border-radius:3px; background:linear-gradient(90deg,#1e3a8a,#3b82f6); min-width:2px; transition:width .8s ease; }}
  .bar.topic {{ background:linear-gradient(90deg,#1e3a8a,#60a5fa); }}
  .bar-num {{ font-size:11px; color:#4b5563; min-width:28px; }}

  /* 环形图 */
  .donut-wrap {{ display:flex; align-items:center; justify-content:center; gap:30px; flex-wrap:wrap; min-height:280px; }}
  .donut {{ width:220px; height:220px; border-radius:50%; background:conic-gradient({donut_style}); position:relative; }}
  .donut::after {{ content:''; position:absolute; inset:36px; background:#fff; border-radius:50%; }}
  .donut-inner {{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; z-index:1; }}
  .donut-inner .big {{ font-size:26px; font-weight:bold; color:#1e3a8a; }}
  .donut-inner .small {{ font-size:12px; color:#6b7280; }}
  .legend {{ display:grid; grid-template-columns:1fr; gap:6px; font-size:12px; max-width:260px; }}
  .legend-item {{ display:flex; align-items:center; gap:8px; color:#4b5563; }}
  .legend-item strong {{ color:#1e3a8a; margin:0 4px; }}
  .dot {{ width:12px; height:12px; border-radius:2px; flex-shrink:0; }}

  /* 热力图 */
  .heat-table {{ width:100%; border-collapse:collapse; font-size:11px; }}
  .heat-table th, .heat-table td {{ padding:6px 4px; text-align:center; border:1px solid #e5e7eb; }}
  .heat-table th {{ background:#f8fafc; color:#374151; font-weight:600; }}
  .heat-table td {{ min-width:38px; }}
  .row-label {{ text-align:left !important; padding-left:8px; background:#f8fafc; font-weight:600; color:#374151; white-space:nowrap; }}

  .footer {{ text-align:center; color:#9ca3af; font-size:12px; margin-top:30px; padding:20px; }}
  @media(max-width:900px) {{ .grid {{ grid-template-columns:1fr; }} .bar-label {{ width:80px; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>🏟️ 体育新闻研究地图</h1>
  <p>研究方法 × 理论框架 × 研究主题 · 三维交叉分析 · 知识库可视化 ({generated_at})</p>
  <div class="stats">
    <div class="stat-card"><div class="num">{total}</div><div class="lbl">文献总数</div></div>
    <div class="stat-card"><div class="num">{method_count}</div><div class="lbl">研究方法类型</div></div>
    <div class="stat-card"><div class="num">{theory_count}</div><div class="lbl">理论框架</div></div>
    <div class="stat-card"><div class="num">{topic_count}</div><div class="lbl">研究主题</div></div>
    <div class="stat-card"><div class="num">{len(d['cats'])}</div><div class="lbl">学科分类</div></div>
  </div>
</div>

<div class="container">
  <div class="grid">
    <div class="card">
      <h2>📊 研究方法分布</h2>
      <div class="desc">全部文献所采用的研究方法类型统计（按主方法归类，从低到高）</div>
      {method_html}
    </div>
    <div class="card">
      <h2>🧠 理论框架分布</h2>
      <div class="desc">文献所依托的主要理论框架分布</div>
      <div class="donut-wrap">
        <div class="donut">
          <div class="donut-inner"><div class="big">{len(theory_dist)}</div><div class="small">主要理论</div></div>
        </div>
        <div class="legend">
          {''.join(theory_donut)}
        </div>
      </div>
    </div>
  </div>

  <div class="grid full" style="margin-top:20px;">
    <div class="card">
      <h2>🔥 研究主题热度</h2>
      <div class="desc">知识库76个研究主题中文献关联量最高的20个主题</div>
      {topic_html}
    </div>
  </div>

  <div class="grid" style="margin-top:20px;">
    <div class="card">
      <h2>🔬 研究方法 × 研究主题 热力图</h2>
      <div class="desc">颜色越深表示该主题下采用该方法的文献越多</div>
      {heat_m_html}
    </div>
    <div class="card">
      <h2>🎓 理论框架 × 研究主题 热力图</h2>
      <div class="desc">颜色越深表示该主题下依托该理论的文献越多</div>
      {heat_t_html}
    </div>
  </div>

  <div class="footer">
    体育新闻研究知识库 · 智能大脑可视化 · 研究地图 v1.0
  </div>
</div>
</body>
</html>
"""
    OUT_DIR = TMP_DIR
    OUT_FILE = HTML_OUT
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    size = os.path.getsize(OUT_FILE)
    print(f"✅ 研究地图已生成: {OUT_FILE} ({size/1024:.0f} KB)")

if __name__ == "__main__":
    d = load_data()
    build_html(d)
