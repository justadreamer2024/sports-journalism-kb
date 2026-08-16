#!/usr/bin/env python3
"""
体育新闻研究知识库 - 本地增量抓取脚本 (持续跟踪最新研究成果) v2
================================================================
多源可插拔架构：Crossref（国际/英文）+ OpenAlex（含中文/多语种），
统一走 去重 → 质量过滤(只保留体育新闻类) → 分类 → 入库 流水线。

质量红线（用户明确）：只收「体育新闻 / 体育传播 / 体育媒体 / 体育报道」类
研究成果，严格剔除运动医学、运动生理、训练、体教接受度等无关文献。

用法:
  python3.11 scripts/fetch_incremental.py                 # 游标增量(默认)
  python3.11 scripts/fetch_incremental.py --from 2025-01-01
  python3.11 scripts/fetch_incremental.py --dry-run       # 只统计不入库
  python3.11 scripts/fetch_incremental.py --no-cursor     # 忽略游标,用 --from
"""
import os
import sys
import re
import json
import time
import sqlite3
import argparse
from datetime import datetime, timedelta
import urllib.request
import urllib.parse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db')
STATE_FILE = os.path.join(PROJECT_ROOT, 'config', 'fetch_state.json')
PER_QUERY = 25
MAILTO = 'research@example.com'  # 礼貌请求标识
MIN_YEAR = 2010                 # 年份下限(游标已保证近期,此处兜底)

# ---------- 检索词 ----------
EN_QUERIES = [
    'sports journalism', 'sports media', 'sport communication',
    'sports reporting', 'sports news', 'sports broadcasting',
    'sports digital media', 'esports journalism',
]
CN_QUERIES = ['体育新闻', '体育传播', '体育媒体', '体育报道', '体育转播', '电子竞技 新闻']

# ---------- 质量过滤词表（红线：只保留体育新闻类） ----------
# 体育领域词（任一出现即视为"体育"域）
SPORT_TOKENS = [
    'sport', 'sports', 'athlet', 'esport', 'e-sport', 'olympic', 'olymp',
    'football', 'soccer', 'basketball', 'baseball', 'volleyball', 'tennis',
    'cricket', 'rugby', 'hockey', 'gymnast', 'ski', 'swim', 'cycling',
    'marathon', 'fifa', 'nba', 'nfl', 'uefa', 'world cup', 'games',
    '体育', '运动', '电竞', '电子竞技', '奥运', '足球', '篮球', '排球',
    '网球', '滑雪', '游泳', '田径', '赛事',
]
# 媒体/传播/报道/产业词（任一出现即视为"新闻传播"域）
MEDIA_TOKENS = [
    'journalism', 'journalistic', 'journalist', 'media', 'news', 'broadcast',
    'communicat', 'report', 'reporting', 'press', 'coverage', 'publication',
    'publish', 'editorial', 'column', 'narrative', 'discourse', 'storytell',
    'audience', 'reader', 'viewer', 'commentary', 'newspaper', 'magazine',
    'tabloid', 'podcast', 'streaming', 'platform', 'social media',
    'facebook', 'twitter', 'instagram', 'tiktok', 'youtube', 'weibo', 'wechat',
    'digital media', 'print', 'headline', 'opinion',
    '新闻', '媒体', '传播', '报道', '转播', '广播', '出版', '期刊', '受众',
    '读者', '观众', '社论', '叙事', '话语', '平台',
    # 体育媒体产业侧
    'market', 'business', 'econom', 'industr', 'sponsor', 'brand',
    'advertis', 'commerce', 'rights', 'marketing',
    '市场', '产业', '商业', '赞助', '品牌', '版权', '营销',
]
# 复合核心词（天然兼具体育+新闻，直接通过）
CORE_TERMS = [
    'sports journalism', 'sport journalism', 'sports media', 'sport media',
    'sports communication', 'sports reporting', 'sports news',
    'sports broadcasting', 'esports journalism', 'sports writing',
    '体育新闻', '体育传播', '体育媒体', '体育报道', '体育转播', '体育写作',
]
# 电竞研究整体在域内（对应"电竞新闻"分类），标题含电竞词即视为体育新闻类
ESPORTS_TOKENS = ['esport', 'e-sport', '电竞', '电子竞技']
# 强黑名单（标题命中即直接剔除，运动医学/生理/无关商业等）
HARD_BLACKLIST = [
    'hypertension', 'arterial', 'anemia', 'iron deficien', 'diabet', 'obes',
    'overweight', 'acl', 'cruciate', 'surgery', 'surgical', 'rehabilit',
    'physiolog', 'conservation', 'wildlife', 'zoolog', 'botan', 'clinical',
    'patient', 'therapy', 'chemotherap', 'oncology', 'umkm', 'small and medium',
    'tourism', 'yoga', 'pilates', 'cardiac', 'heart rate', 'muscle',
    'exercise training', 'physical activity', 'physical education',
    'injury', 'nutrit', 'concussion', 'endurance', 'sport science',
    'sports science', 'sport sciences', '体育科学', '运动医学',
    '运动生理', '高血压', '糖尿病', '肥胖', '手术', '康复', '临床', '患者',
    '治疗', '癌症', '野生动物', '保护', '旅游', '瑜伽', '肌肉', '体能训练',
    '体育教育',
]

# 分类规则（与历史保持一致）
RULES = [
    ('电竞新闻', ['esport', 'e-sport', '电竞', '电子竞技', 'video game', 'gaming']),
    ('体育与性别', ['gender', 'women', 'female', 'masculin', 'sexism', '性别', '女性']),
    ('体育与政治', ['politic', 'nation', 'government', 'olympics', 'olympic', '政治', '奥运']),
    ('体育与新媒体', ['social media', 'twitter', 'facebook', 'instagram', 'tiktok', 'digital', 'online', 'platform', '新媒体', '社交媒体']),
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


def passes_filter(title, abstract=''):
    """质量红线：只保留体育新闻类研究成果。返回 True 表示入库。"""
    t = (title or '').lower()
    a = (abstract or '').lower()
    # 1) 标题强命中黑名单 -> 直接剔除（运动医学/生理/无关商业）
    if any(b in t for b in HARD_BLACKLIST):
        return False
    # 2) 复合核心词 -> 天然体育+新闻，通过
    if any(c in t for c in CORE_TERMS):
        return True
    # 2.5) 电竞研究整体在域内（对应"电竞新闻"分类），标题含电竞词即通过
    if any(e in t for e in ESPORTS_TOKENS):
        return True
    # 3) 双信号：体育域词(标题) ∩ 媒体/传播域词（标题或摘要任一满足）
    ta = t + ' ' + a
    has_sport = any(s in ta for s in SPORT_TOKENS)
    has_media = any(m in ta for m in MEDIA_TOKENS)
    return has_sport and has_media


def fetch_crossref(query, from_date):
    """Crossref 抓取，带 429 限流指数退避重试。"""
    url = 'https://api.crossref.org/works'
    params = {
        'query': query,
        'rows': PER_QUERY,
        'filter': f'from-pub-date:{from_date}',
        'select': 'DOI,title,author,container-title,issued,abstract,published',
        'mailto': MAILTO,
    }
    last_err = None
    for attempt in range(4):  # 0,1,2,3 -> 退避 0,2,4,8s
        try:
            req = urllib.request.Request(
                url + '?' + urllib.parse.urlencode(params),
                headers={'User-Agent': f'SportsJournalismKB/2.0 (mailto:{MAILTO})'}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            return data['message']['items']
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                time.sleep(2 ** attempt)
                continue
            break
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    print(f'  [Crossref] "{query}" 抓取失败: {last_err}')
    return []


def normalize_crossref(item):
    doi = item.get('DOI', '')
    title = clean_text((item.get('title', ['']) or [''])[0]) if item.get('title') else ''
    if not title:
        return None
    authors = []
    for au in item.get('author', [])[:8]:
        name = ' '.join(filter(None, [au.get('given', ''), au.get('family', '')])).strip()
        if name:
            authors.append(name)
    author_str = '、'.join(authors) if authors else '相关学者'
    journal = clean_text((item.get('container-title', ['']) or [''])[0]) if item.get('container-title') else ''
    raw = item.get('abstract', '')
    abstract = clean_text(raw)[:800] if raw else ''
    year = extract_year(item.get('issued')) or extract_year(item.get('published'))
    return {
        'title': title, 'author': author_str, 'author_affiliation': None,
        'year': year, 'source_type': 'journal', 'source_name': journal or '学术期刊',
        'doi': doi or None, 'url': f'https://doi.org/{doi}' if doi else None,
        'region': 'international', 'language': 'en', 'abstract': abstract,
        'project_relevance': '来自: 本地增量抓取(Crossref)',
    }


def fetch_openalex(query, from_date):
    """OpenAlex 抓取（含中文/多语种），带 429 退避重试。"""
    url = ('https://api.openalex.org/works?search=' + urllib.parse.quote(query) +
           f'&filter=from_publication_date:{from_date}&per_page={PER_QUERY}&mailto={MAILTO}')
    last_err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                url, headers={'User-Agent': f'SportsJournalismKB/2.0 (mailto:{MAILTO})'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            return data.get('results', [])
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                time.sleep(2 ** attempt)
                continue
            break
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    print(f'  [OpenAlex] "{query}" 抓取失败: {last_err}')
    return []


def _reconstruct_abstract(inv_idx):
    """OpenAlex 摘要以 inverted index 存储，需重建。"""
    if not inv_idx:
        return ''
    words = []
    for w, idxs in inv_idx.items():
        for i in idxs:
            words.append((i, w))
    words.sort()
    return ' '.join(w for _, w in words)


def _lang_code(item):
    L = item.get('language')
    if isinstance(L, dict):
        return (L.get('code') or 'en').lower()
    if isinstance(L, str):
        return L.lower()
    return 'en'


def normalize_openalex(item):
    title = clean_text(item.get('display_name', '') or '')
    if not title:
        return None
    authors = []
    for au in (item.get('authorships') or [])[:8]:
        nm = au.get('author', {}).get('display_name', '')
        if nm:
            authors.append(nm)
    author_str = '、'.join(authors) if authors else '相关学者'
    src = item.get('primary_location', {}).get('source', {}) or {}
    journal = clean_text(src.get('display_name', '') or '')
    raw_abs = item.get('abstract') or _reconstruct_abstract(item.get('abstract_inverted_index'))
    abstract = clean_text(raw_abs)[:800] if raw_abs else ''
    year = item.get('publication_year')
    doi = (item.get('ids', {}) or {}).get('doi')
    doi = doi.replace('https://doi.org/', '') if doi else None
    lang = _lang_code(item)
    region = 'domestic' if lang == 'zh' else 'international'
    return {
        'title': title, 'author': author_str, 'author_affiliation': None,
        'year': year, 'source_type': 'journal', 'source_name': journal or '学术期刊',
        'doi': doi, 'url': f'https://doi.org/{doi}' if doi else (item.get('id') or None),
        'region': region, 'language': lang, 'abstract': abstract,
        'project_relevance': '来自: 本地增量抓取(OpenAlex)',
    }


def guess_category(title):
    t = (title or '').lower()
    for cat, kws in RULES:
        for kw in kws:
            if kw in t:
                return cat
    return '体育新闻理论'


def extract_year(issued):
    try:
        dp = issued.get('date-parts', [[None]])
        return dp[0][0] if dp and dp[0] and dp[0][0] else None
    except Exception:
        return None


def clean_text(s):
    if not s:
        return ''
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def load_cursor():
    """读取游标：上次成功抓取日期；无则回退最近30天。"""
    today = datetime.now()
    fallback = (today - timedelta(days=30)).strftime('%Y-%m-%d')
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, encoding='utf-8') as f:
                st = json.load(f)
            cur = st.get('last_cursor')
            if cur:
                return max(cur, fallback)
    except Exception:
        pass
    return fallback


def save_cursor():
    today = datetime.now().strftime('%Y-%m-%d')
    st = {}
    if os.path.exists(STATE_FILE):
        try:
            st = json.load(open(STATE_FILE, encoding='utf-8'))
        except Exception:
            st = {}
    st['last_cursor'] = today
    st['last_run'] = datetime.now().isoformat(timespec='seconds')
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def ensure_fetch_log(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS fetch_log (
        id INTEGER PRIMARY KEY,
        run_at TEXT, source TEXT, query TEXT,
        fetched INTEGER, new_inserted INTEGER, dup_skipped INTEGER,
        filtered_out INTEGER, failed INTEGER, cursor_from TEXT, duration_sec REAL
    )""")


def get_topic_map(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM research_topics")
    return {name: tid for tid, name in cur.fetchall()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='from_date', default=None, help='抓取起始出版日期(覆盖游标)')
    ap.add_argument('--dry-run', action='store_true', help='只统计不入库')
    ap.add_argument('--no-cursor', action='store_true', help='忽略游标')
    args = ap.parse_args()

    cursor = args.from_date or (load_cursor() if not args.no_cursor else
                                (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d'))
    print(f'🔍 本地增量抓取 (from-pub-date >= {cursor})  [游标机制]')
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    ensure_fetch_log(conn)

    cur = conn.cursor()
    cur.execute("SELECT doi FROM literature WHERE doi IS NOT NULL")
    existing_dois = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT lower(title) FROM literature WHERE title IS NOT NULL")
    existing_titles = {r[0] for r in cur.fetchall()}
    topic_map = get_topic_map(conn)

    sources = [
        ('crossref', fetch_crossref, EN_QUERIES),
        ('openalex', fetch_openalex, EN_QUERIES + CN_QUERIES),
    ]

    new_rows = []
    seen = set()
    run_stats = {'cursor_from': cursor, 'by_source': {}, 'by_category': {}, 'total_new': 0,
                 'total_fetched': 0, 'total_filtered': 0, 'total_dup': 0, 'total_failed': 0,
                 'samples': []}
    run_start = time.time()

    for sname, fetcher, queries in sources:
        for q in queries:
            t0 = time.time()
            items = fetcher(q, cursor)
            fetched = len(items)
            norm = []
            filtered = 0
            for it in items:
                row = (normalize_crossref(it) if sname == 'crossref' else normalize_openalex(it))
                if not row:
                    continue
                # 质量红线：只保留体育新闻类
                if not passes_filter(row['title'], row['abstract']):
                    filtered += 1
                    continue
                key = (row['doi'] or row['title'].strip().lower())
                if not key or key in existing_dois or key in existing_titles or key in seen:
                    continue
                if not row['year'] or row['year'] < MIN_YEAR:
                    continue
                seen.add(key)
                norm.append(row)
            # 入库/统计
            inserted = 0
            for r in norm:
                if args.dry_run:
                    continue
                cols = ['title','author','author_affiliation','year','source_type','source_name',
                        'doi','url','region','language','category1','abstract','keywords',
                        'project_relevance','collected_by','data_source','data_quality_status',
                        'created_at','updated_at']
                cat = guess_category(r['title'])
                r['category1'] = cat
                # 国际文献标记待译队列；中文文献无需翻译
                r['data_quality_status'] = 'pending_translate' if r['region'] == 'international' else 'new'
                r['collected_by'] = 'fetch_incremental'
                r['data_source'] = sname
                r['keywords'] = ''
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                r['created_at'] = now
                r['updated_at'] = now
                vals = [r.get(c) for c in cols]
                cur.execute(f"INSERT INTO literature ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})", vals)
                lid = cur.lastrowid
                tid = topic_map.get(cat)
                if tid:
                    cur.execute("INSERT OR IGNORE INTO literature_topics (literature_id, topic_id, relevance) VALUES (?,?,?)",
                                (lid, tid, 1))
                inserted += 1
                # 统计分类
                run_stats['by_category'][cat] = run_stats['by_category'].get(cat, 0) + 1
                if len(run_stats['samples']) < 15:
                    run_stats['samples'].append(f"[{r['year']}] {r['title'][:60]} | {cat}")
            conn.commit()
            dup = fetched - len(norm) - filtered
            failed = 0
            if not args.dry_run:
                cur.execute("""INSERT INTO fetch_log (run_at,source,query,fetched,new_inserted,
                    dup_skipped,filtered_out,failed,cursor_from,duration_sec)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (datetime.now().isoformat(timespec='seconds'), sname, q, fetched, inserted,
                     max(dup, 0), filtered, failed, cursor, round(time.time()-t0, 2)))
                conn.commit()
            run_stats['by_source'][sname] = run_stats['by_source'].get(sname, 0) + inserted
            run_stats['total_new'] += inserted
            run_stats['total_fetched'] += fetched
            run_stats['total_filtered'] += filtered
            run_stats['total_dup'] += max(dup, 0)
            tag = 'crossref' if sname == 'crossref' else 'OpenAlex'
            print(f'  [{tag}] "{q}" 抓到 {fetched} | 过滤(非体育新闻) {filtered} | 新增 {inserted}')

    print(f'\n✅ 本轮入库新文献: {run_stats["total_new"]} 篇 '
          f'(Crossref +{run_stats["by_source"].get("crossref",0)}, '
          f'OpenAlex +{run_stats["by_source"].get("openalex",0)})')
    print(f'   过滤掉的非体育新闻类: {run_stats["total_filtered"]} 篇 | 去重跳过: {run_stats["total_dup"]} 篇')

    if args.dry_run:
        for s in run_stats['samples']:
            print(f'  + {s}')
        conn.close()
        return run_stats

    if run_stats['total_new'] == 0:
        print('📊 无新增，主库已是最新前沿。')
    else:
        # 入库后补关键词
        conn.close()
        print('🔤 正在为新文献提取关键词...')
        os.system(f'{sys.executable} {os.path.join(PROJECT_ROOT, "scripts", "extract_keywords.py")}')
        # 更新游标
        save_cursor()
        run_stats['run_at'] = datetime.now().isoformat(timespec='seconds')
        _save_track_result(run_stats)
        return run_stats

    conn.close()
    if run_stats['total_new'] == 0:
        save_cursor()  # 即便无新增也推进游标
    run_stats['run_at'] = datetime.now().isoformat(timespec='seconds')
    _save_track_result(run_stats)
    return run_stats


def _save_track_result(stats):
    """把本轮跟踪成果写入 state，供日报/周报读取。"""
    path = os.path.join(PROJECT_ROOT, 'config', 'last_track_result.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({
            'run_at': stats.get('run_at', datetime.now().isoformat(timespec='seconds')),
            'total_new': stats['total_new'],
            'by_source': stats.get('by_source', {}),
            'by_category': stats.get('by_category', {}),
            'samples': stats.get('samples', []),
        }, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    st = main()
    print(f'\n=== 本轮新增 {st["total_new"]} 篇 ===')
    sys.exit(0)
