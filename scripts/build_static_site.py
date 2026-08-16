#!/usr/bin/env python3
"""
体育新闻研究知识库 - 构建独立静态站点
生成一个无需后端、纯静态的部署包，可部署到任何静态托管平台
（GitHub Pages / Vercel / Cloudflare Pages / Netlify 等）

输出目录: web/static_site/
"""
import os
import sys
import json
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_manager import get_db

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'web', 'static_site')

# 语种/类型名称
LANG_NAMES = {'zh':'中文','en':'英文','de':'德文','fr':'法文','ja':'日文','es':'西语','ko':'韩文'}
TYPE_NAMES = {'journal':'期刊论文','book':'著作','thesis':'学位论文','conference':'会议论文'}

def export_data():
    """导出所有数据为JSON"""
    conn = get_db()
    conn.row_factory = __import__('sqlite3').Row
    
    data = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'stats': {
            'total': conn.execute("SELECT COUNT(*) FROM literature").fetchone()[0],
            'domestic': conn.execute("SELECT COUNT(*) FROM literature WHERE region='domestic'").fetchone()[0],
            'international': conn.execute("SELECT COUNT(*) FROM literature WHERE region='international'").fetchone()[0],
            'languages': {r[0]: r[1] for r in conn.execute("SELECT language, COUNT(*) FROM literature GROUP BY language").fetchall()},
            'categories': {r[0]: r[1] for r in conn.execute("SELECT category1, COUNT(*) FROM literature WHERE category1 IS NOT NULL AND category1!='' GROUP BY category1").fetchall()},
        },
        'literature': [dict(r) for r in conn.execute("SELECT * FROM literature ORDER BY year DESC, id DESC").fetchall()],
        'topics': [dict(r) for r in conn.execute("SELECT * FROM research_topics ORDER BY hot_level DESC").fetchall()],
    }
    # 规范化作者字段：占位符清空并打标记，供前端专业显示
    PLACEHOLDER = {'相关学者', '未知', '待补充', '佚名', 'Unknown', ''}
    for lit in data['literature']:
        auth = (lit.get('author') or '').strip()
        if auth in PLACEHOLDER or auth.startswith('相关学者'):
            lit['author'] = ''
            lit['author_pending'] = True
        else:
            lit['author_pending'] = False
    conn.close()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, 'data.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    return data

def build_index():
    """生成自包含的index.html（单文件，内嵌所有功能）"""
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>体育新闻研究知识库</title>
<style>
:root{--bg:#0f0f1a;--card:#1a1a2e;--text:#e0e0e0;--sub:#a0a0b0;--accent:#4f8cff;--accent2:#00d4aa;--border:#2a2a3e}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);line-height:1.6;min-height:100vh}
.container{max-width:1400px;margin:0 auto;padding:20px}
.header{background:linear-gradient(135deg,#1a1a3e,#0f0f2a);border-bottom:1px solid var(--border);padding:20px 0;position:sticky;top:0;z-index:100}
.header .container{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
.header h1{font-size:1.4rem;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:24px 0}
.stat{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px;text-align:center}
.stat .n{font-size:1.8rem;font-weight:700;color:var(--accent)}
.stat .l{font-size:.78rem;color:var(--sub);margin-top:4px}
.search{display:flex;gap:10px;margin:20px 0;flex-wrap:wrap}
.search input,.search select{padding:10px 14px;border:1px solid var(--border);border-radius:8px;background:var(--card);color:var(--text);font-size:.9rem;outline:none}
.search input{flex:1;min-width:200px}
.search input:focus,.search select:focus{border-color:var(--accent)}
button{padding:10px 18px;border:none;border-radius:8px;background:var(--accent);color:#fff;cursor:pointer;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th{text-align:left;padding:10px 14px;border-bottom:2px solid var(--border);color:var(--sub);font-size:.8rem}
td{padding:10px 14px;border-bottom:1px solid var(--border)}
tr:hover td{background:rgba(79,140,255,.05)}
.sub{color:var(--sub);font-size:.78rem;margin-top:2px}
.badge{padding:2px 8px;border-radius:12px;font-size:.75rem;font-weight:600}
.b-zh{background:rgba(79,140,255,.2);color:var(--accent)}
.b-en{background:rgba(0,212,170,.2);color:var(--accent2)}
.b-o{background:rgba(255,165,2,.2);color:#ffa502}
.pagination{display:flex;justify-content:center;gap:6px;margin:20px 0;flex-wrap:wrap}
.pagination button{padding:6px 12px;background:var(--card);border:1px solid var(--border);color:var(--text)}
.pagination button.active{background:var(--accent);border-color:var(--accent)}
.modal{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);z-index:200;align-items:center;justify-content:center}
.modal.active{display:flex}
.modal-body{background:var(--card);border:1px solid var(--border);border-radius:12px;max-width:700px;width:90%;max-height:80vh;overflow-y:auto;padding:24px}
.modal-body h2{margin-bottom:14px;color:var(--accent)}
.field{margin-bottom:10px}
.f-label{font-size:.75rem;color:var(--sub);font-weight:600}
.f-value{font-size:.9rem}
.abstract{background:rgba(79,140,255,.05);padding:14px;border-radius:8px;border-left:3px solid var(--accent);margin:10px 0}
.close{float:right;background:none;border:none;color:var(--sub);font-size:1.4rem;cursor:pointer}
.footer{text-align:center;color:var(--sub);font-size:.75rem;padding:20px 0;border-top:1px solid var(--border);margin-top:30px}
@media(max-width:768px){.search{flex-direction:column}}
</style>
</head>
<body>

<header class="header">
<div class="container">
<h1>🏅 体育新闻研究知识库</h1>
<span id="headerStats" style="color:var(--sub);font-size:.85rem">加载中...</span>
</div>
</header>

<div class="container">
<div class="stats" id="statsGrid"></div>

<div class="search">
<input type="text" id="q" placeholder="🔍 搜索标题、作者、关键词...">
<select id="region"><option value="">全部区域</option><option value="domestic">国内</option><option value="international">国际</option></select>
<select id="lang"><option value="">全部语种</option><option value="zh">中文</option><option value="en">英文</option><option value="de">德文</option><option value="fr">法文</option><option value="ja">日文</option><option value="es">西语</option><option value="ko">韩文</option></select>
<button onclick="render(1)">搜索</button>
<a href="research_map.html" target="_blank" style="display:inline-flex;align-items:center;gap:4px;padding:10px 18px;border-radius:8px;background:linear-gradient(135deg,#1e3a8a,#3b82f6);color:#fff;text-decoration:none;font-weight:600;font-size:.9rem;">🗺️ 研究地图</a>
</div>

<div style="overflow-x:auto"><table>
<thead><tr><th>标题</th><th>作者</th><th>年份</th><th>语种</th><th>类型</th><th>分类</th></tr></thead>
<tbody id="tbody"></tbody>
</table></div>

<div class="pagination" id="pagination"></div>
</div>

<div class="modal" id="modal">
<div class="modal-body" id="modalBody"></div>
</div>

<div class="footer">体育新闻研究知识库 · 静态部署版 · <span id="genTime"></span></div>

<script>
const DATA = __DATA_JSON__;
const LANG={zh:'中文',en:'英文',de:'德文',fr:'法文',ja:'日文',es:'西语',ko:'韩文'};
const TYPE={journal:'期刊',book:'著作',thesis:'学位',conference:'会议'};
let lit=DATA.literature, page=1, perPage=30;
document.getElementById('genTime').textContent='生成于 '+DATA.generated_at;
document.getElementById('headerStats').textContent=DATA.stats.total+' 篇 · '+Object.keys(DATA.stats.languages).length+' 语种';

// Stats
const sg=document.getElementById('statsGrid');
const items=[['总文献',DATA.stats.total],['国内',DATA.stats.domestic],['国际',DATA.stats.international],['语种',Object.keys(DATA.stats.languages).length],['分类',Object.keys(DATA.stats.categories).length]];
sg.innerHTML=items.map(([l,n])=>`<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('');

function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
function filter(){
  const q=document.getElementById('q').value.toLowerCase();
  const r=document.getElementById('region').value;
  const l=document.getElementById('lang').value;
  return lit.filter(x=>(!q||(x.title&&x.title.toLowerCase().includes(q))||(x.title_cn&&x.title_cn.toLowerCase().includes(q))||(x.author&&x.author.toLowerCase().includes(q))||(x.keywords&&x.keywords.toLowerCase().includes(q))||(x.keywords_cn&&x.keywords_cn.toLowerCase().includes(q)))&&(!r||x.region===r)&&(!l||x.language===l));
}
function render(p){
  page=p;const f=filter();const totalPages=Math.ceil(f.length/perPage);
  const start=(page-1)*perPage, end=Math.min(start+perPage,f.length);
  document.getElementById('tbody').innerHTML=f.slice(start,end).map(x=>`
  <tr><td style="cursor:pointer;color:var(--accent)" onclick="detail(${x.id})">${esc(x.title)}${x.title_cn&&x.title_cn!==x.title?`<div class="sub">${esc(x.title_cn)}</div>`:''}</td>
  <td>${x.author?esc(x.author.substring(0,30)):'<span style="color:#f59e0b">待核查</span>'}</td><td>${x.year||'-'}</td>
  <td><span class="badge ${x.language==='zh'?'b-zh':x.language==='en'?'b-en':'b-o'}">${LANG[x.language]||x.language}</span></td>
  <td>${TYPE[x.source_type]||x.source_type}</td><td>${x.category1||'-'}</td></tr>`).join('');
  document.getElementById('pagination').innerHTML=Array.from({length:totalPages},(_,i)=>i+1).map(i=>`<button class="${i===page?'active':''}" onclick="render(${i})">${i}</button>`).join('');
}
function detail(id){const x=lit.find(y=>y.id===id);document.getElementById('modalBody').innerHTML=`
<button class="close" onclick="document.getElementById('modal').classList.remove('active')">&times;</button>
<h2>${esc(x.title)}</h2>
${x.title_cn&&x.title_cn!==x.title?`<div class="field"><span class="f-label">中文标题</span><div class="f-value" style="color:var(--accent);font-size:1.05rem">${esc(x.title_cn)}</div></div>`:''}
<div class="field"><span class="f-label">作者</span><div class="f-value">${x.author?esc(x.author):'<span style="color:#f59e0b">待核查（信息不完整）</span>'}</div></div>
${x.author_affiliation?`<div class="field"><span class="f-label">单位</span><div class="f-value">${esc(x.author_affiliation)}</div></div>`:''}
<div class="field"><span class="f-label">年份/来源</span><div class="f-value">${x.year||'-'} | ${esc(x.source_name||'')} | ${TYPE[x.source_type]||x.source_type}</div></div>
${x.doi?`<div class="field"><span class="f-label">DOI</span><div class="f-value"><a href="https://doi.org/${x.doi}" target="_blank" style="color:var(--accent)">${x.doi}</a></div></div>`:''}
${x.url?`<div class="field"><span class="f-label">链接</span><div class="f-value"><a href="${x.url}" target="_blank" style="color:var(--accent)">${x.url}</a></div></div>`:''}
${x.abstract?`<div class="abstract"><span class="f-label">摘要</span><div>${esc(x.abstract)}</div></div>`:''}
${x.abstract_cn&&x.abstract_cn!==x.abstract?`<div class="abstract"><span class="f-label">中文摘要</span><div>${esc(x.abstract_cn)}</div></div>`:''}
<div class="field"><span class="f-label">关键词</span><div class="f-value">${esc(x.keywords||'')}${x.keywords_cn&&x.keywords_cn!==x.keywords?`<br>${esc(x.keywords_cn)}`:''}</div></div>
${x.research_method?`<div class="field"><span class="f-label">研究方法</span><div class="f-value">${esc(x.research_method)}</div></div>`:''}
${x.theoretical_framework?`<div class="field"><span class="f-label">理论框架</span><div class="f-value">${esc(x.theoretical_framework)}</div></div>`:''}
<div class="field"><span class="f-label">区域</span><div class="f-value">${x.region==='domestic'?'国内':'国际'}</div></div>`;
document.getElementById('modal').classList.add('active');
}
document.getElementById('q').addEventListener('keypress',e=>{if(e.key==='Enter')render(1)});
document.getElementById('modal').addEventListener('click',e=>{if(e.target===e.currentTarget)e.currentTarget.classList.remove('active')});
render(1);
</script>
</body>
</html>"""
    
    # 把 data.json 内容内嵌进 index.html
    with open(os.path.join(OUTPUT_DIR, 'data.json'), 'r', encoding='utf-8') as f:
        data_json = f.read()
    
    html = html.replace('__DATA_JSON__', data_json)
    with open(os.path.join(OUTPUT_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    
    return os.path.join(OUTPUT_DIR, 'index.html')

def build_readme(total_count):
    """生成部署说明（动态统计文献总数）"""
    readme = f"""# 体育新闻研究知识库 - 静态部署包

## 说明
这是一个完全自包含的静态站点，无需后端服务器，数据全部内嵌在 index.html 中。

## 部署方法（任选其一）

### 1. GitHub Pages
1. 创建 GitHub 私有仓库
2. 上传本目录所有文件到仓库
3. 仓库 Settings → Pages → 选择分支 → 部署

### 2. Vercel / Netlify / Cloudflare Pages
1. 注册对应平台账号
2. 上传/导入本目录
3. 一键部署

### 3. 本地打开
直接双击 index.html 即可浏览（无需网络）

## 更新数据
重新运行: `python3.11 scripts/build_static_site.py`

## 数据统计
- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
- 文献总数: {total_count}
"""
    with open(os.path.join(OUTPUT_DIR, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme)

def main():
    print("🏗️ 构建独立静态站点...")
    print(f"   输出目录: {OUTPUT_DIR}")
    
    # 清空旧目录
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    data = export_data()
    index_path = build_index()
    build_readme(data['stats']['total'])
    
    # 生成研究地图并复制到输出目录
    try:
        import subprocess
        subprocess.run(['python3', 'scripts/build_research_map.py'], cwd=PROJECT_ROOT, check=True)
        shutil.copy(os.path.join(PROJECT_ROOT, 'scripts', '.tmp', 'research_map.html'), os.path.join(OUTPUT_DIR, 'research_map.html'))
        print(f"   research_map.html: {OUTPUT_DIR}/research_map.html")
    except Exception as e:
        print(f"   ⚠️ 研究地图生成失败: {e}")
    
    size = os.path.getsize(index_path) / 1024
    print(f"✅ 静态站点构建完成!")
    print(f"   index.html: {index_path} ({size:.0f} KB)")
    print(f"   data.json:  {OUTPUT_DIR}/data.json")
    print(f"   README.md:  {OUTPUT_DIR}/README.md")
    print(f"\n📦 部署包已就绪，可部署到任何静态托管平台")

if __name__ == '__main__':
    main()
