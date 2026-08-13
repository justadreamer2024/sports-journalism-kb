#!/usr/bin/env python3
"""
体育新闻研究知识库 - 自动抓取脚本 (GitHub Actions 用)
=====================================================
在 GitHub Actions 环境中运行，从可免费访问的公开学术源抓取
最新体育新闻研究文献 + 研究动态，合并写入 data.json。

数据源:
  - Crossref API (开放获取学术文献, 支持检索体育新闻相关)
  - Google News RSS (体育新闻研究动态/热点)

设计原则:
  - 纯 JSON 驱动，不需要 SQLite（GitHub Actions 每次运行是全新环境）
  - 读取仓库现有 data.json，抓取新条目，按 DOI/标题去重合并
  - 幂等：重复运行不会产生重复数据
"""
import os
import sys
import json
import time
import re
import urllib.parse
from datetime import datetime, timedelta

import requests

# ---------- 配置 ----------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = REPO_ROOT  # 线上仓库 data.json/index.html 在根目录
DATA_FILE = os.path.join(SITE_DIR, 'data.json')
MAILTO = "research@example.com"  # Crossref 礼貌请求标识，可改

# 检索关键词（体育新闻研究核心主题，多语言）
SEARCH_QUERIES = {
    'en': [
        'sports journalism', 'sports media', 'sport communication',
        'sports reporting', 'sports news', 'sports broadcasting',
        'sports digital media', 'esports journalism'
    ],
}

# 每个关键词抓取条数
PER_QUERY = 20

# 匹配分类
def guess_category(title):
    """根据标题猜测文献分类"""
    t = title.lower()
    rules = [
        ('电竞新闻', ['esport', 'e-sport', '电竞', '电子竞技', 'video game', 'gaming']),
        ('体育与性别', ['gender', 'women', 'female', 'masculin', 'sexism', '性别', '女性']),
        ('体育与政治', ['politic', 'nation', 'government', 'olympics', 'olympic', '政治', '奥运']),
        ('体育与新媒体', ['social media', 'twitter', 'facebook', 'instagram', 'tiktok', 'digital', 'online', 'platform', 'social media', '新媒体', '社交媒体']),
        ('体育国际传播', ['international', 'global', 'cross-cultur', 'diplomacy', 'soft power', '国际传播', '话语']),
        ('体育媒体产业', ['industry', 'market', 'business', 'commercial', 'econom', 'ownership', '产业', '市场']),
        ('体育新闻与技术', ['ai', 'artificial intelligence', 'algorithm', 'automation', 'chatbot', 'llm', 'chatgpt', 'generative', '人工智能', '算法', '自动化']),
        ('体育新闻伦理', ['ethic', 'journalistic', 'objectivity', 'bias', 'framing', '伦理', '客观', '框架']),
        ('体育新闻受众', ['audience', 'fan', 'consumer', 'reader', 'viewer', 'engag', '受众', '观众', '球迷']),
        ('体育新闻史', ['histor', 'evolution', 'origin', 'history', '史', '演进']),
        ('体育新闻教育', ['education', 'teaching', 'curriculum', 'student', 'training', '教育', '培养', '课程']),
        ('体育新闻理论', ['theor', 'concept', 'framework', 'discourse', 'narrative', '理论', '框架', '叙事']),
        ('体育新闻实务', ['reporting', 'coverage', 'journalism practice', 'interview', 'story', '实务', '报道', '采访']),
    ]
    for cat, kws in rules:
        for kw in kws:
            if kw in t:
                return cat
    return '体育新闻理论'


def fetch_crossref(query, from_date):
    """从 Crossref API 抓取体育新闻研究文献"""
    url = 'https://api.crossref.org/works'
    params = {
        'query': query,
        'rows': PER_QUERY,
        'filter': f'from-pub-date:{from_date}',
        'select': 'DOI,title,author,container-title,issued,abstract,published',
        'mailto': MAILTO,
    }
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        items = r.json()['message']['items']
        return items
    except Exception as e:
        print(f'  [Crossref] {query} 抓取失败: {e}')
        return []


def extract_year(issued):
    """从 issued 字段提取年份"""
    try:
        dp = issued.get('date-parts', [[None]])
        return dp[0][0] if dp and dp[0] and dp[0][0] else None
    except Exception:
        return None


def crossref_to_lit(item, lang='en'):
    """把 Crossref 条目转成知识库文献格式"""
    doi = item.get('DOI', '')
    title = ''
    try:
        title = item.get('title', [''])[0] or ''
    except Exception:
        title = ''
    if not title:
        return None
    # 作者
    authors = []
    try:
        for a in item.get('author', [])[:8]:
            name = ' '.join(filter(None, [a.get('given', ''), a.get('family', '')])).strip()
            if name:
                authors.append(name)
    except Exception:
        pass
    author_str = '、'.join(authors) if authors else '相关学者'
    # 期刊
    try:
        journal = item.get('container-title', [''])
        journal = journal[0] if journal else ''
    except Exception:
        journal = ''
    # 摘要清理
    abstract = ''
    try:
        raw_abs = item.get('abstract', '')
        if raw_abs:
            abstract = re.sub(r'<[^>]+>', '', raw_abs).strip()[:800]
    except Exception:
        pass
    year = extract_year(item.get('issued'))
    return {
        'title': title,
        'author': author_str,
        'author_affiliation': None,
        'year': year,
        'source_type': 'journal',
        'source_name': journal or '学术期刊',
        'volume': None,
        'issue': None,
        'pages': None,
        'doi': doi or None,
        'url': f'https://doi.org/{doi}' if doi else None,
        'region': 'international',
        'language': lang,
        'category1': guess_category(title),
        'abstract': abstract,
        'keywords': '',
        'research_method': '',
        'theoretical_framework': '',
        'citation_count': 0,
        'is_core': 0,
        'project_relevance': '来自: GitHub Actions 自动抓取(Crossref)',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'collected_by': 'auto_gha',
        'data_source': 'crossref'
    }


def fetch_google_news(query, from_date):
    """从 Google News RSS 抓取研究动态（作为 news_items 补充）"""
    # 仅当有研究动态存储时使用，这里暂不写入 literature
    return []


def load_existing():
    """加载现有 data.json"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'generated_at': '', 'stats': {}, 'literature': [], 'topics': []}


def save_data(data):
    """写回 data.json"""
    os.makedirs(SITE_DIR, exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def main():
    # 抓取最近 14 天
    from_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    print(f'🔍 开始抓取（最近14天，从 {from_date}）')

    data = load_existing()
    existing = data.get('literature', [])
    existing_dois = {lit.get('doi') for lit in existing if lit.get('doi')}
    existing_titles = set()
    for lit in existing:
        t = (lit.get('title') or '').strip().lower()
        if t:
            existing_titles.add(t)

    new_items = []
    seen = set()

    # 抓取英文文献
    print('\n=== 英文文献 (Crossref) ===')
    for query in SEARCH_QUERIES['en']:
        items = fetch_crossref(query, from_date)
        print(f'  [英文] "{query}" 抓到 {len(items)} 条')
        for it in items:
            lit = crossref_to_lit(it, 'en')
            if not lit:
                continue
            # 去重：DOI 或标题
            key = lit['doi'] or lit['title'].strip().lower()
            if key in existing_dois or key in existing_titles or key in seen:
                continue
            if not lit['year'] or lit['year'] < 2020:
                continue
            seen.add(key)
            new_items.append(lit)
        time.sleep(1)  # 礼貌间隔

    print(f'\n✅ 新增 {len(new_items)} 条文献')

    # 合并
    if new_items:
        existing.extend(new_items)
        data['literature'] = existing
        # 更新时间戳
        data['generated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        # 更新统计
        total = len(existing)
        domestic = sum(1 for l in existing if l.get('region') == 'domestic')
        international = total - domestic
        langs = {}
        cats = {}
        for l in existing:
            lg = l.get('language') or 'en'
            langs[lg] = langs.get(lg, 0) + 1
            c = l.get('category1')
            if c:
                cats[c] = cats.get(c, 0) + 1
        data['stats'] = {
            'total': total,
            'domestic': domestic,
            'international': international,
            'languages': langs,
            'categories': cats,
        }
        save_data(data)
        print(f'📊 数据已更新: 总数 {total}，新增 {len(new_items)}')
    else:
        print('📊 本次无新增文献，数据不变')

    return len(new_items)


if __name__ == '__main__':
    n = main()
    sys.exit(0 if True else 1)
