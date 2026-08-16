#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补齐文献缺失字段（#118）
目标：
1. 用 Crossref API 抓取缺失的 abstract（摘要）和 keywords（关键词/subject）
2. 用 Semantic Scholar API 作为补充（Crossref 无 abstract 时）
3. 高价值文献优先处理
4. 带重试、限速、断点续传

用法：
  python3.11 scripts/fill_missing_fields.py [--abstract] [--keywords] [--limit N] [--resume]
"""
import sqlite3
import time
import json
import os
import sys
import requests
import logging
import re

DB = '/workspace/sports-journalism-kb/database/knowledge_base.db'
PROGRESS_FILE = '/workspace/sports-journalism-kb/scripts/.fill_progress.json'
USER_AGENT = 'SportsJournalismKB/1.0 (research project; mailto:research@example.com)'

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('fill')

# Crossref mailto（提升限流额度）
CROSSREF_MAILTO = 'research@example.com'


def normalize_doi(doi):
    if not doi:
        return None
    doi = doi.strip()
    # 去掉可能的前缀
    for prefix in ('https://doi.org/', 'http://doi.org/', 'doi:'):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
    return doi.strip()


def fetch_crossref(doi, retries=3):
    """通过 Crossref 抓取 abstract 和 subject(keywords)"""
    doi = normalize_doi(doi)
    if not doi:
        return {}
    url = f'https://api.crossref.org/works/{doi}'
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=15, headers={
                'User-Agent': USER_AGENT,
                'mailto': CROSSREF_MAILTO,
            })
            if r.status_code == 200:
                d = r.json().get('message', {})
                abstract = d.get('abstract', '')
                if abstract:
                    # 清理JATS XML标签
                    abstract = re.sub(r'<[^>]+>', '', abstract)
                    abstract = re.sub(r'\s+', ' ', abstract).strip()
                # subject 作为关键词（有些期刊无subject，用author keywords）
                keywords = []
                subjects = d.get('subject', [])
                if subjects:
                    keywords = [s.strip() for s in subjects if s.strip()]
                # 部分期刊用 "author keyword" 字段
                # Crossref 没有专门 keywords 字段，subject 是最接近的
                return {'abstract': abstract, 'keywords': keywords}
            elif r.status_code == 404:
                return {}
            else:
                log.warning(f'Crossref {doi} HTTP {r.status_code}')
        except Exception as e:
            log.warning(f'Crossref {doi} 错误: {e}')
        time.sleep(2 * (attempt + 1))
    return {}


def fetch_semanticscholar(doi, retries=3):
    """通过 Semantic Scholar 抓取 abstract"""
    doi = normalize_doi(doi)
    if not doi:
        return {}
    url = f'https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}'
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=15, params={
                'fields': 'title,abstract,externalIds,tldr'
            }, headers={'User-Agent': USER_AGENT})
            if r.status_code == 200:
                d = r.json()
                abstract = d.get('abstract') or ''
                return {'abstract': abstract}
            elif r.status_code == 429:
                log.warning('SemanticScholar 429 限流，等待10秒')
                time.sleep(10)
                continue
            elif r.status_code == 404:
                return {}
        except Exception as e:
            log.warning(f'SemanticScholar {doi} 错误: {e}')
        time.sleep(3 * (attempt + 1))
    return {}


def extract_keywords_from_abstract(abstract, max_kw=5):
    """从摘要中提取候选关键词（兜底方案）"""
    # 简单启发式：抽取高频学术术语
    stopwords = {'the','a','an','and','of','to','in','for','on','with','by','that',
                 'this','is','are','was','were','as','at','from','or','be','been','its',
                 'their','his','her','we','they','it','sports','study','research','article',
                 'paper','also','more','about','between','how','what','who','when','which'}
    words = re.findall(r'[A-Za-z][A-Za-z\-]{4,}', abstract or '')
    freq = {}
    for w in words:
        lw = w.lower()
        if lw in stopwords:
            continue
        freq[lw] = freq.get(lw, 0) + 1
    top = sorted(freq.items(), key=lambda x: -x[1])[:max_kw]
    return [w for w, c in top]


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {'processed_ids': []}


def save_progress(processed_ids):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({'processed_ids': processed_ids}, f)


def main():
    args = sys.argv[1:]
    do_abstract = '--abstract' in args
    do_keywords = '--keywords' in args
    no_crossref = '--no-crossref' in args
    limit = None
    resume = '--resume' in args
    for i, a in enumerate(args):
        if a == '--limit' and i + 1 < len(args):
            limit = int(args[i + 1])
    if not do_abstract and not do_keywords:
        do_abstract = do_keywords = True  # 默认两者都做

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 收集需要补 abstract 的文献
    abstract_targets = []
    if do_abstract:
        cur.execute('''SELECT id, doi, abstract FROM literature
                       WHERE (abstract IS NULL OR abstract='')
                         AND doi IS NOT NULL AND doi != ''
                       ORDER BY id''')
        for r in cur.fetchall():
            abstract_targets.append({'id': r['id'], 'doi': r['doi']})

    # 收集需要补 keywords 的文献
    keyword_targets = []
    if do_keywords:
        cur.execute('''SELECT id, doi, keywords FROM literature
                       WHERE (keywords IS NULL OR keywords='')
                         AND doi IS NOT NULL AND doi != ''
                       ORDER BY id''')
        for r in cur.fetchall():
            keyword_targets.append({'id': r['id'], 'doi': r['doi']})

    # 合并去重（同一篇文献可能两项都缺）
    all_targets = {t['id']: t['doi'] for t in abstract_targets + keyword_targets}

    log.info(f'缺abstract: {len(abstract_targets)} 篇')
    log.info(f'缺keywords: {len(keyword_targets)} 篇')
    log.info(f'合并去重后需处理: {len(all_targets)} 篇')

    if resume:
        processed = load_progress()['processed_ids']
        processed_set = set(processed)
        all_targets = {k: v for k, v in all_targets.items() if k not in processed_set}
        log.info(f'断点续传，跳过已处理 {len(processed_set)} 篇，剩余 {len(all_targets)} 篇')
        processed_ids = processed
    else:
        processed_ids = []

    if limit:
        all_targets = dict(list(all_targets.items())[:limit])

    fetched_abstract = 0
    fetched_keywords = 0
    api_hits = 0

    for idx, (lit_id, doi) in enumerate(all_targets.items()):
        # 优先用 Semantic Scholar 抓 abstract（命中率高）
        ss = fetch_semanticscholar(doi)
        api_hits += 1
        abstract_val = ss.get('abstract', '')
        time.sleep(1.0)  # Semantic Scholar 限速较严

        # Crossref 补充 subject 关键词（可跳过，规避限流）
        keywords_val = []
        if not no_crossref:
            cr = fetch_crossref(doi)
            api_hits += 1
            keywords_val = cr.get('keywords', [])
        time.sleep(0.4)

        # 更新数据库
        updates = []
        params = []
        if do_abstract and abstract_val:
            updates.append('abstract=?')
            params.append(abstract_val)
        if do_keywords and keywords_val:
            # keywords 存为逗号分隔或JSON? 检查现有格式
            kw_str = ', '.join(keywords_val[:8])
            updates.append('keywords=?')
            params.append(kw_str)
        elif do_keywords and not keywords_val and abstract_val:
            # 兜底：从摘要抽关键词
            kw = extract_keywords_from_abstract(abstract_val)
            if kw:
                updates.append('keywords=?')
                params.append(', '.join(kw))

        if updates:
            updates.append('updated_at=datetime("now")')
            params.append(lit_id)
            cur.execute(f'UPDATE literature SET {", ".join(updates)} WHERE id=?', params)
            conn.commit()
            if 'abstract=?' in updates:
                fetched_abstract += 1
            if 'keywords=?' in updates:
                fetched_keywords += 1

        processed_ids.append(lit_id)
        if (idx + 1) % 20 == 0:
            save_progress(processed_ids)
            log.info(f'进度: {idx+1}/{len(all_targets)} | 补摘要{fetched_abstract} | 补关键词{fetched_keywords}')

    save_progress(processed_ids)
    log.info('=' * 50)
    log.info(f'完成！共处理 {len(all_targets)} 篇')
    log.info(f'  补全摘要: {fetched_abstract} 篇')
    log.info(f'  补全关键词: {fetched_keywords} 篇')
    log.info(f'  API调用次数: {api_hits}')

    # 统计结果
    if do_abstract:
        cur.execute('SELECT COUNT(*) FROM literature WHERE (abstract IS NULL OR abstract=\'\')')
        print(f'  剩余缺abstract: {cur.fetchone()[0]}')
    if do_keywords:
        cur.execute('SELECT COUNT(*) FROM literature WHERE (keywords IS NULL OR keywords=\'\')')
        print(f'  剩余缺keywords: {cur.fetchone()[0]}')
    conn.close()


if __name__ == '__main__':
    main()
