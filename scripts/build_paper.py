#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
体育新闻研究论文自动生成流水线
================================
基于知识库自动生成学术综述论文初稿。

工作流程：
  1. 主题选题：从研究主题中按热度选择或指定主题
  2. 文献检索：按 主题/关键词/分类 检索相关文献（含中文摘要优先）
  3. 结构生成：按学术论文规范组织大纲（标题/摘要/引言/综述/理论/方法/发现/讨论/结论）
  4. 综述初稿：基于文献中文摘要提炼+组合，生成各章节初稿
  5. 参考文献：自动生成规范参考文献列表（含 DOI/期刊/年份）
  6. 导出：输出 Markdown 论文文档 + 素材统计

用法：
  python3 build_paper.py --topic "AI与体育新闻" --title "生成式人工智能时代的体育新闻生产变革" --output output/papers/
"""
import os
import sys
import json
import sqlite3
import argparse
import re
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db')
DEFAULT_OUT = os.path.join(PROJECT_ROOT, 'output', 'papers')

# ---------- 主题关键词映射 ----------
TOPIC_KEYWORDS = {
    'AI与体育新闻': ['AI', '人工智能', 'generative', 'artificial intelligence', 'automation', '自动化', 'algorithm', '算法', 'robot', 'chatbot', 'GPT', 'large language'],
    '女性体育报道': ['women', '女性', 'female', 'gender', '性别', 'feminist', 'feminism', 'girl', 'sex', '女运动员', '女记者'],
    '社交媒体与体育': ['social media', '社交媒体', 'twitter', 'x平台', 'instagram', 'tiktok', 'facebook', '短视频', 'platform'],
    '体育赛事报道': ['olympic', '奥运', 'world cup', '世界杯', 'sporting event', '赛事报道', 'match', 'game coverage', 'live', '转播', '直播'],
    '电竞报道与媒体生态': ['esport', '电竞', 'e-sport', 'e-sports', 'gaming', '游戏'],
    '体育国际传播': ['international', '国际传播', 'cross-cultural', '跨文化', 'soft power', '软实力', 'global', 'globalization', '公共外交'],
    '体育新闻伦理': ['ethic', '伦理', 'integrity', '诚信', 'corruption', '腐败', 'bias', '偏见', 'morality', 'moral'],
    '体育新闻与技术': ['technology', '技术', 'innovation', '创新', 'digital', '数字', 'data', '数据', 'vr', 'augmented', 'extended reality'],
    '体育与性别': ['gender', '性别', 'women', '女性', 'lgbt', 'masculinit', '男性气质', 'homosex', 'queer'],
}

PLACEHOLDER_AUTHORS = {'相关学者', '未知', '待补充', '佚名', 'Unknown', ''}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def safe_author(author):
    """规范化作者名，过滤占位符"""
    if not author:
        return '佚名'
    author = author.strip()
    if author in PLACEHOLDER_AUTHORS:
        return '佚名'
    return author

def clean_title(title):
    """清理标题中的markdown特殊字符"""
    if not title:
        return ''
    return title.strip()

# ---------- 1. 主题选题 ----------
def select_topic(c, topic=None):
    """选择论文主题。若未指定，则按热度选择。"""
    if topic:
        return topic
    # 按研究主题关联文献数排序
    rows = c.execute("""
        SELECT rt.name, COUNT(lt.literature_id) as cnt
        FROM research_topics rt
        LEFT JOIN literature_topics lt ON rt.id = lt.topic_id
        GROUP BY rt.id ORDER BY cnt DESC LIMIT 1
    """).fetchone()
    return rows['name'] if rows else '体育新闻'

# ---------- 2. 文献检索 ----------
def retrieve_literature(c, topic, limit=60):
    """按主题检索相关文献，返回按年份倒序、相关性排序的列表。
    分步查询，逻辑清晰、参数可控：
      Step1 主题表关联命中（最相关，relevance=3）
      Step2 分类 category1 命中（relevance=2）
      Step3 标题命中（relevance=1）
      Step4 摘要/关键词命中（relevance=0）
    """
    keywords = [kw for kw in TOPIC_KEYWORDS.get(topic, [topic]) if kw.strip()]

    def _in_placeholders(n):
        return ','.join(['?'] * n)

    # Step1: 主题表关联
    top_ids = set()
    if keywords:
        ph = _in_placeholders(len(keywords))
        top_ids = {r[0] for r in c.execute(
            f"SELECT DISTINCT lt.literature_id FROM literature_topics lt JOIN research_topics rt ON lt.topic_id=rt.id WHERE rt.name IN ({ph})",
            keywords
        )}

    # Step2+3: 分类 + 标题
    cat_ids, title_ids = set(), set()
    for kw in keywords:
        like = f"%{kw}%"
        cat_ids.update(r[0] for r in c.execute(
            "SELECT id FROM literature WHERE category1 LIKE ? OR category2 LIKE ?", (like, like)))
        title_ids.update(r[0] for r in c.execute(
            "SELECT id FROM literature WHERE title LIKE ? OR title_cn LIKE ?", (like, like)))

    # Step4: 摘要/关键词
    abs_ids = set()
    for kw in keywords:
        like = f"%{kw}%"
        abs_ids.update(r[0] for r in c.execute(
            "SELECT id FROM literature WHERE abstract LIKE ? OR abstract_cn LIKE ? OR keywords LIKE ? OR keywords_cn LIKE ?",
            (like, like, like, like)))

    # 合并全部候选ID，并记录相关度
    rel = {}
    for i in top_ids: rel[i] = 3
    for i in cat_ids: rel[i] = max(rel.get(i, 0), 2)
    for i in title_ids: rel[i] = max(rel.get(i, 0), 1)
    for i in abs_ids: rel.setdefault(i, 0)

    if not rel:
        return []

    ph = _in_placeholders(len(rel))
    rows = c.execute(
        f"""SELECT l.*, (l.abstract_cn IS NOT NULL AND l.abstract_cn != '') as has_cn_abs
            FROM literature l WHERE l.id IN ({ph})
            ORDER BY l.year DESC, l.id DESC""",
        list(rel.keys())
    ).fetchall()

    # 按相关度排序（保留年份倒序）
    rows.sort(key=lambda r: (-rel.get(r['id'], 0), -(r['year'] or 0)))
    return rows[:limit]

# ---------- 3. 结构化摘要 ----------
def extract_key_elements(lit):
    """从文献提取关键要素用于综述"""
    return {
        'id': lit['id'],
        'title': clean_title(lit['title'] or lit['title_cn'] or ''),
        'title_cn': lit['title_cn'],
        'author': safe_author(lit['author']),
        'year': lit['year'],
        'journal': lit['source_name'],
        'doi': lit['doi'],
        'url': lit['url'],
        'method': lit['research_method'],
        'theory': lit['theoretical_framework'],
        'abstract_cn': (lit['abstract_cn'] or '').strip(),
        'abstract': (lit['abstract'] or '').strip(),
        'category': lit['category1'],
        'region': '国内' if lit['region'] == 'domestic' else '国际',
    }

# ---------- 4. 参考文献格式化 ----------
def format_reference(elem, idx):
    """生成规范参考文献（近似GB/T 7714样式）"""
    author = elem['author']
    year = elem['year'] if elem['year'] else 'n.d.'
    title = elem['title']
    journal = elem['journal'] or ''
    doi = elem['doi']
    parts = []
    # 作者. 标题. 期刊, 年份.
    ref = f"[{idx}] {author}. {title}."
    if journal:
        ref += f" {journal},"
    ref += f" {year}."
    if doi:
        ref += f" https://doi.org/{doi}"
    return ref

# ---------- 5. 综述段落生成 ----------
def generate_intro(elems, topic):
    """生成引言段落"""
    n = len(elems)
    years = [e['year'] for e in elems if e['year']]
    year_min, year_max = (min(years), max(years)) if years else ('', '')
    intl = sum(1 for e in elems if e['region'] == '国际')
    cn = sum(1 for e in elems if e['region'] == '国内')
    year_range = f"{year_min}–{year_max}" if year_min else ''
    return f"""## 一、引言

{cnf_title(topic)}是体育新闻研究领域的重要议题。近年来，随着体育媒介环境的深刻变革，{topic_lower(topic)}的相关研究日益受到国内外学界关注。本综述基于体育新闻研究知识库的文献数据，系统梳理{topic}领域的研究进展，围绕研究方法、理论框架与核心议题展开分析，以期为后续研究提供参考。

本次综述共检索到 **{n} 篇**相关文献，时间跨度覆盖 **{year_range}** 年，其中国际文献 **{intl}** 篇、国内文献 **{cn}** 篇。通过系统梳理这些文献，本文尝试回答以下问题：（1）{topic_lower(topic)}领域的研究热点与演进脉络如何？（2）现有研究采用了哪些主要研究方法与理论框架？（3）未来研究存在哪些值得深入的方向？

"""

def generate_theory(elems):
    """生成研究方法与理论框架章节"""
    method_count = defaultdict(int)
    for e in elems:
        m = e['method'] or '待补'
        if m == '待补' or m.strip() == '':
            continue
        for part in m.replace('、', ',').replace('，', ',').split(','):
            method_count[part.strip()] += 1
    theory_count = defaultdict(int)
    for e in elems:
        t = e['theory'] or '待补'
        if t == '待补' or t.strip() == '':
            continue
        main_t = t.split('、')[0].split(',')[0].strip()
        theory_count[main_t] += 1

    method_line = '；'.join([f"{m}({c}篇)" for m, c in sorted(method_count.items(), key=lambda x: -x[1])[:6]])
    theory_line = '、'.join([f"{t}({c}篇)" for t, c in sorted(theory_count.items(), key=lambda x: -x[1])[:6]])

    top = sorted(method_count.items(), key=lambda x: -x[1])[0][0] if method_count else '理论分析'

    return f"""## 三、研究方法与理论框架

### 3.1 研究方法

对文献的研究方法进行统计可以发现，本领域研究方法呈现多元化特征，主要方法包括：{method_line}。其中，{top}是最主要的研究路径，反映了该领域以理论建构与实证检验并重的研究取向。

### 3.2 理论框架

在理论层面，研究者主要依托{theory_line}等理论框架展开分析。这些理论从不同视角切入，构成了该领域较为完整的理论图景，为理解体育新闻生产与传播提供了多元的理论支撑。

"""

def top_method(method_count):
    if not method_count:
        return '理论分析'
    return sorted(method_count.items(), key=lambda x: -x[1])[0][0]

# ---------- 6. 主题章节生成 ----------
def generate_theme_section(elems):
    """按主题分组生成综述正文"""
    # 按分类分组
    groups = defaultdict(list)
    for e in elems:
        cat = e['category'] or '其他'
        groups[cat].append(e)

    sections = []
    for i, (cat, items) in enumerate(sorted(groups.items(), key=lambda x: -len(x[1]))):
        if i >= 6:
            break
        sections.append(f"### {i+1}. {cat}领域研究（{len(items)}篇）\n")
        for e in items[:3]:
            # 用中文摘要提炼核心发现
            core = summarize_abstract(e)
            sections.append(f"**{e['title']}**（{e['author']}，{e['year'] or '年份待核'}）")
            sections.append(f"——{core}")
        sections.append("")
    return "\n".join(sections)

def summarize_abstract(e):
    """从摘要中提炼1-2句核心发现（基于中文摘要，若无则用英文截取）"""
    if e['abstract_cn']:
        abs_text = e['abstract_cn']
        # 提取关键句（找"结果""发现""研究表明"后的内容，否则取前两句）
        for kw in ['研究结果表明', '研究发现', '结果显示', '结果表明', '研究发现', '本研究']:
            if kw in abs_text:
                idx = abs_text.find(kw)
                return abs_text[idx:idx+120].strip() + ('…' if len(abs_text) > idx+120 else '')
        # 取前150字
        return abs_text[:150].strip() + ('…' if len(abs_text) > 150 else '')
    elif e['abstract']:
        # 英文摘要截取
        sent = e['abstract'].split('. ')
        core = sent[0] if sent else e['abstract']
        return core[:150].strip() + '…'
    else:
        return '（该文献暂无摘要）'

# ---------- 7. 发现与讨论 ----------
def generate_findings(elems):
    """生成研究发现与讨论"""
    # 统计年份分布
    year_count = defaultdict(int)
    for e in elems:
        if e['year']:
            year_count[e['year']] += 1
    recent_years = sorted([y for y in year_count if y >= (max(year_count) - 3)]) if year_count else []
    recent_count = sum(year_count[y] for y in recent_years)

    # 统计热点分类
    cat_count = defaultdict(int)
    for e in elems:
        cat_count[e['category'] or '其他'] += 1
    top_cats = sorted(cat_count.items(), key=lambda x: -x[1])[:5]
    cat_line = '、'.join([f"{c}({n}篇)" for c, n in top_cats])

    return f"""## 四、研究发现在与讨论

### 4.1 研究热点演进

从文献分布来看，体育新闻生产与传播的研究热点主要集中于：{cat_line}。从时间维度看，近三年（{recent_years[0] if recent_years else ''}年以来）新增文献 {recent_count} 篇，表明该领域研究持续升温，且与体育媒介数字化转型的趋势高度相关。

### 4.2 主要研究发现

综合本综述所涉及的文献，体育新闻生产与传播领域的研究形成了几点较为一致的共识：一是媒介技术变革（特别是社交媒体与人工智能）正深刻重塑体育新闻的生产流程与传播生态；二是体育新闻中的性别、种族与社会正义议题日益成为学界关注焦点；三是国际传播语境下体育新闻承担着建构国家形象与文化认同的重要功能。

### 4.3 讨论

现有研究在方法论上趋于多元，但理论整合仍有待深化。多数研究聚焦于单一媒介平台或单一赛事，跨平台、跨文化的比较研究相对不足。此外，随着生成式人工智能在体育新闻中的广泛应用，算法透明度、内容可信度与新闻伦理等议题将成为未来研究的重点方向。

"""

# ---------- 8. 结论 ----------
def generate_conclusion():
    return """## 五、结论

本文基于体育新闻研究知识库，系统梳理了相关领域的文献，呈现了该领域的研究热点、研究方法、理论框架与主要发现。研究表明，体育新闻研究正处于媒介技术变革与全球化传播的双重驱动之下，呈现出研究对象多元化、研究方法交叉化、理论框架综合化的发展态势。未来研究可在以下方向深化：一是加强生成式人工智能与体育新闻融合的实证研究；二是推进跨国、跨平台的比较研究；三是深化体育新闻伦理与治理议题的理论建构。

"""

def cnf_title(topic):
    """主题的肯定表述"""
    return topic if topic else '体育新闻'

def topic_lower(topic):
    return topic if topic else '体育新闻'

# ---------- 主流程 ----------
def build_paper(topic=None, title=None, output_dir=None, limit=60):
    conn = get_db()
    c = conn.cursor()

    # 1. 选题
    selected_topic = select_topic(c, topic)
    # 2. 检索
    elems = [extract_key_elements(r) for r in retrieve_literature(c, selected_topic, limit)]
    if not elems:
        print(f"⚠️ 主题「{selected_topic}」未检索到文献")
        conn.close()
        return None

    # 3. 生成各章节
    paper_title = title or f"{selected_topic}研究综述"
    paper = f"""# {paper_title}

> **体育新闻研究知识库 · 论文自动生成**
> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}
> 检索主题：{selected_topic} ｜ 检索文献：{len(elems)} 篇

---

## 摘要

本文基于体育新闻研究知识库，围绕「{selected_topic}」这一主题开展系统性文献综述。通过检索知识库中的相关文献，梳理了该领域的研究热点、演进脉络、研究方法与理论框架，并对主要研究发现进行了归纳与讨论。研究表明，{selected_topic}领域正处于快速发展期，研究对象与研究方法日趋多元，生成式人工智能等新技术的介入正在重塑相关研究议程。

**关键词**：{selected_topic}；体育新闻；文献综述；研究趋势

---

"""
    paper += generate_intro(elems, selected_topic)
    paper += "## 二、主要研究主题综述\n\n" + generate_theme_section(elems)
    paper += generate_theory(elems)
    paper += generate_findings(elems)
    paper += generate_conclusion()

    # 4. 参考文献
    paper += "\n## 参考文献\n\n"
    for i, e in enumerate(elems, 1):
        paper += format_reference(e, i) + "\n"

    # 5. 素材附录
    paper += f"\n---\n\n## 附录：检索文献素材清单（{len(elems)}篇）\n\n"
    for i, e in enumerate(elems, 1):
        paper += f"{i}. **{e['title']}** — {e['author']} ({e['year'] or '年份待核'}) | {e['region']} | {e['category'] or '未分类'}"
        if e['method'] and e['method'] != '待补':
            paper += f" | 方法:{e['method']}"
        paper += "\n"

    # 6. 输出
    out_dir = output_dir or DEFAULT_OUT
    os.makedirs(out_dir, exist_ok=True)
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', paper_title)
    out_file = os.path.join(out_dir, f"{safe_title}_{datetime.now().strftime('%Y%m%d')}.md")
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(paper)
    conn.close()

    print(f"✅ 论文初稿已生成: {out_file}")
    print(f"   主题: {selected_topic} | 文献: {len(elems)} 篇")
    return out_file

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='体育新闻研究论文自动生成')
    parser.add_argument('--topic', help='论文主题')
    parser.add_argument('--title', help='论文标题')
    parser.add_argument('--output', help='输出目录')
    parser.add_argument('--limit', type=int, default=60, help='检索文献上限')
    args = parser.parse_args()
    build_paper(args.topic, args.title, args.output, args.limit)
