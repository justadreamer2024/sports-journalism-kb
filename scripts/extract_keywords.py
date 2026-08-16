#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从标题+摘要提取高质量关键词（#140 / #118 剩余项）
==================================================
背景：589篇文献缺关键词，但均有摘要+DOI。Crossref 对多数体育期刊 subject 字段为空，
无法从 API 获取作者关键词，需从标题+摘要智能提取。

方法（三层级）：
  1. 受控词表匹配 —— 76个研究主题英文名 + 体育新闻领域高频术语词典，
     标题命中权重最高、摘要命中次之，保留有意义的复合短语；
  2. 主题词（从标题+摘要共同命中的研究主题优先）；
  3. 高频词兜底 —— 对无任何词表命中的文献，用 TF 加权的领域词兜底。

格式保持既有规范："; " 分隔的小写短语，默认最多 6 个。
只更新 keywords 为空的文献（幂等），支持断点续传。

用法：
  python3.11 scripts/extract_keywords.py [--limit N] [--dry-run]
"""
import sqlite3
import re
import sys
import logging
from collections import Counter

DB = '/workspace/sports-journalism-kb/database/knowledge_base.db'
MAX_KW = 6

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('kw')

# ---------------------------------------------------------------------------
# 受控词表：研究主题英文名（来自 research_topics.name_en）
# ---------------------------------------------------------------------------
TOPIC_TERMS = [
    'sports journalism theory', 'sports communication', 'sports media industry',
    'sports journalism practice', 'sports and new media', 'international sports communication',
    'sports journalism ethics', 'sports journalism education', 'history of sports journalism',
    'sports and gender', 'sports and politics', 'esports journalism',
    'sports journalism and technology', 'sports journalism audience', 'sports media law',
    'sports media criticism', 'discourse analysis', 'professionalism',
    'narratology', 'framing theory', 'news values', 'social responsibility',
    'communication effects', 'media events', 'political economy', 'communication theory',
    'health communication', 'business models', 'broadcasting rights', 'platform economy',
    'media convergence', 'on-site major event coverage', 'sports event reporting',
    'sports data journalism', 'writing and editing', 'sports photography', 'visual communication',
    'live broadcast', 'reporter professional skills', 'social media and sports',
    'ai and sports journalism', 'short video', 'algorithmic distribution',
    'new media content production', 'discourse power', 'cross-cultural communication',
    'china sports image', 'global media landscape', 'ethical violations', 'privacy protection',
    'gambling and media ethics', 'cyber violence', 'public opinion', 'curriculum development',
    'talent cultivation', 'discipline construction', 'chinese sports media history',
    'global sports media history', 'journalist biographies', 'women sports coverage',
    'gender equality in media', 'masculinity and sports media', 'lgbtq in sports media',
    'politicization of sports', 'sports diplomacy', 'nationalism and sports media',
    'esports reporting', 'esports broadcasting', 'esports and traditional sports',
    'automated reporting', 'tech innovation', 'data and tech governance', 'sports fandom',
    'audience behavior', 'participatory communication', 'broadcasting rights law',
    'media regulation', 'media discourse analysis', 'critical media studies',
]

# 扩展领域术语词典（含常见同义词/变体，正则匹配）
DOMAIN_TERMS = [
    'sports journalism', 'sport journalism', 'sports media', 'sport media',
    'sports broadcasting', 'sport broadcasting', 'sports news', 'sport news',
    'digital media', 'new media', 'social media', 'online journalism',
    'media coverage', 'news coverage', 'media representation',
    'gender', 'women in sport', 'female athletes', 'sexism', 'masculinity',
    'ethics', 'ethical', 'professional values', 'objectivity',
    'framing', 'agenda setting', 'news values', 'gatekeeping',
    'artificial intelligence', 'automation', 'algorithm', 'machine learning',
    'data journalism', 'visualization', 'augmented reality', 'virtual reality',
    'fandom', 'fan culture', 'fan engagement', 'audience', 'viewers', 'readers',
    'television', 'broadcasting', 'streaming', 'live stream', 'podcast',
    'advertising', 'sponsorship', 'branding', 'commercialization',
    'twitter', 'x platform', 'facebook', 'instagram', 'tiktok', 'youtube',
    'hashtag', 'user generated content', 'citizen journalism',
    'paralympics', 'olympics', 'olympic games', 'world cup', 'super bowl',
    'nba', 'football', 'soccer', 'basketball', 'tennis', 'formula 1', 'cycling',
    'mega event', 'sport event', 'tournament', 'championship',
    'disability sport', 'para sport', 'inclusion', 'diversity',
    'representation', 'stereotype', 'minority', 'race', 'ethnicity',
    'politics', 'nationalism', 'patriotism', 'diplomacy', 'soft power',
    'esports', 'e-sports', 'gaming', 'video game',
    'copyright', 'intellectual property', 'rights fee', 'piracy',
    'regulation', 'policy', 'governance', 'media law',
    'qualitative', 'quantitative', 'content analysis', 'interviews', 'survey',
    'framing analysis', 'discourse analysis', 'case study', 'ethnography',
    'crisis communication', 'public relations', 'risk communication',
    'health communication', 'mental health', 'concussion',
    'youth sport', 'grassroots', 'community', 'local media',
    'mobile', 'smartphone', 'second screen', 'multi-platform',
    'ownership', 'monopoly', 'concentration', 'media economics',
    'partisan', 'polarization', 'bias', 'credibility', 'trust',
    'citizen sport', 'participatory', 'engagement', 'interactivity',
    'newsroom', 'reporter', 'correspondent', 'freelance', 'workplace',
    'marketing', 'relationship marketing', 'brand', 'entrepreneurship',
    'labor', 'precarity', 'pandemic', 'covid', 'cyberbullying', 'bullying',
    'mental health', 'wellbeing', 'burnout', 'anxiety',
    'athlete', 'athletes', 'coach', 'referee', 'professional sport',
    'activism', 'advocacy', 'protest', 'social justice', 'black lives matter',
    'empathy', 'emotion', 'affective', 'feeling',
    'concussion', 'injury', 'player welfare',
    'credibility', 'trust', 'source', 'anonymous source',
    'newsroom culture', 'work conditions', 'job satisfaction', 'career',
    'freedom of the press', 'access', 'press conference', 'interviewing',
    'remote work', 'teleworking', 'home office',
    'fantasy sport', 'gaming community', 'video games',
    'consumption', 'consumer behavior', 'viewer behavior',
    'analytics', 'metrics', 'engagement metrics', 'clickbait',
    'verification', 'fact checking', 'misinformation', 'disinformation',
    'climate change', 'environmental', 'sustainability',
    'local news', 'hyperlocal', 'community journalism',
    'diversity', 'inclusion', 'equity', 'minority representation',
    'disability', 'paralympic', 'ableism',
]

# 停用词（避免产出无意义单词）
STOPWORDS = set("""the a an and of to in for on with by that this is are was were as at from or be been
its their his her we they it sports study research article paper also more about between how what
who when which such using use used based findings results result shows show suggest suggest suggest
examined examine examines examined explore explores explores explore investigate investigates
find found data analysis analyses effect effects impact implications role play plays examine the
""".split())


def build_regex(term):
    """把短语转成正则（可匹配变体）"""
    return r'\b' + re.sub(r'\s+', r'\\s+', re.escape(term.strip().lower()))


def extract(record):
    """从单条文献(title+abstract+language)提取关键词列表"""
    title = (record['title'] or '').lower()
    abstract = (record['abstract'] or '').lower()
    text = title + ' ' + abstract

    # 1) 标题命中研究主题/领域词 —— 最高权重
    title_hits = []
    for t in TOPIC_TERMS + DOMAIN_TERMS:
        t = t.strip()
        if re.search(build_regex(t), title):
            title_hits.append(t)
    # 2) 摘要命中研究主题 —— 次高权重
    abstract_topic_hits = []
    for t in TOPIC_TERMS:
        if re.search(build_regex(t), abstract):
            abstract_topic_hits.append(t)
    # 3) 摘要命中的领域词（需排除研究主题重复）
    abstract_domain_hits = []
    for t in DOMAIN_TERMS:
        if t not in title_hits and t not in abstract_topic_hits and \
           re.search(build_regex(t), abstract):
            abstract_domain_hits.append(t)

    # 按"先主题后领域、标题优先"排序，去重
    ordered = []
    seen = set()
    for group in (title_hits, abstract_topic_hits, abstract_domain_hits):
        for t in group:
            t = t.strip()
            if t not in seen:
                seen.add(t)
                ordered.append(t)

    # 短语去冗余：若一个长短语已包含更短的（如 women in sport ⊂ women sports coverage 不算），
    # 保留更具体/更长的。这里简单保留全部，交由后续做"具体优先"。
    final = []
    # 已收集足够则返回
    if len(ordered) >= 2:
        # 压缩过长的主题短语名，保留可读的领域短语
        result = []
        for t in ordered:
            if len(result) >= MAX_KW:
                break
            result.append(t)
        return dedupe_plurals(result)

    # 不足2个时，结合词表命中 + 高频短语提取补足
    result = list(ordered)
    if len(result) < MAX_KW:
        bigrams = extract_bigrams(title, abstract)
        for b in bigrams:
            if b not in result and len(result) < MAX_KW:
                result.append(b)
    if result:
        return dedupe_plurals(result)

    # 无任何命中的极端兜底
    return extract_fallback(text)


def extract_fallback(text):
    """无受控词命中时的兜底：抽取高信息量单词/短语"""
    words = re.findall(r'[a-z][a-z\-]{4,}', text)
    c = Counter(w for w in words if w not in STOPWORDS)
    top = c.most_common(MAX_KW)
    return [w for w, _ in top if w != 'sports']


# 允许出现在短语第二位的介词/连词（构成如 "media coverage", "women in sport"）
_BIGRAM_BRIDGE = {'in', 'of', 'and', 'for', 'on', 'with', 'by', 'the'}


def extract_bigrams(title, abstract, max_bg=6):
    """从标题+摘要中提取高频实义双词短语（含 stopword-bridge 型）"""
    text = (title + '  ' + abstract).lower()
    text = re.sub(r'[^a-z\s\-]', ' ', text)
    # 1) 纯名词性 bigram：两个实词
    tokens = text.split()
    bigrams = []
    for i in range(len(tokens) - 1):
        w1, w2 = tokens[i], tokens[i + 1]
        if w1 in STOPWORDS or w2 in STOPWORDS:
            continue
        # 过滤无意义单复数词
        if w1 in ('sport', 'sports', 'study', 'studies', 'media') and \
           w2 in ('sport', 'sports', 'media', 'journalism'):
            continue
        bigrams.append((w1, w2))
    # 2) bridge 型 bigram：w1 - bridge - w2（如 media in sport）
    bridge_bigrams = []
    for i in range(len(tokens) - 2):
        w1, w2, w3 = tokens[i], tokens[i + 1], tokens[i + 2]
        if w2 in _BIGRAM_BRIDGE and w1 not in STOPWORDS and w3 not in STOPWORDS:
            bridge_bigrams.append(f'{w1} {w2} {w3}')

    cnt = Counter(' '.join(b) for b in bigrams)
    # 桥接短语权重更高（更贴合主题）
    for phrase in bridge_bigrams:
        cnt[phrase] += 1

    # 词表组合白名单：这些 low_info 词在与特定词组合时仍是有意义关键词
    def _meaningful(ph):
        words = ph.split()
        if len(words) < 2:
            return False
        # 排除以虚词/碎片结尾的（specifically, although, has, rm, time, without...）
        bad_end = {'specifically', 'although', 'has', 'have', 'had', 'were', 'was',
                   'however', 'also', 'rm', 'time', 'without', 'perspective',
                   'revisiting', 'critiquing', 'examining', 'contextualizing',
                   'rebooting', 'continuing', 'search', 'evolution', 'remedy',
                   'decline', 'influence', 'sympathies', 'dispute', 'pilot',
                   'study', 'studies', 'research', 'article', 'paper', 'based',
                   'using', 'about', 'this', 'that', 'these', 'those',
                   'marketing', 'journalism', 'coverage', 'theory', 'analysis',
                   'practice', 'relations', 'communication', 'management',
                   'perspectives', 'specifically', 'relational'}
        if words[-1] in bad_end:
            return False
        # 排除含噪词（全局）
        bad_any = {'the', 'this', 'that', 'these', 'those', 's', 'although',
                   'specifically', 'has', 'have', 'had', 'rm', 'without', 'also',
                   'examining', 'critiquing', 'revisiting', 'contextualizing',
                   'rebooting', 'continuing', 'examined', 'exploring',
                   'understanding', 'analyzing', 'studying'}
        if any(w in bad_any for w in words):
            return False
        # 词表短语（social media, fantasy sport 等）应保留
        for t in TOPIC_TERMS + DOMAIN_TERMS:
            if t in ph:
                return True
        # 排除两个都是"媒介/体育"泛词组合（如 sport media 交给词表处理）
        generic = {'sport', 'sports', 'media', 'study', 'studies', 'research'}
        if all(w in generic for w in words):
            return False
        return True

    filtered = [(ph, n) for ph, n in cnt.most_common(max_bg * 4) if _meaningful(ph)]
    title_l = title.lower()
    keep = []
    for ph, n in filtered:
        if n >= 2 or (ph.split()[0] in title_l):
            keep.append(ph)
        if len(keep) >= max_bg:
            break
    return keep


def dedupe_plurals(kws):
    """去重单复数（athlete/athletes）与极端冗余"""
    out = []
    for kw in kws:
        w = kw.strip()
        if not w:
            continue
        # 单复数去重：若单数形式已存在，跳过复数
        singular = w[:-1] if w.endswith('s') and len(w) > 4 else None
        if singular and singular in out:
            continue
        out.append(w)
    return out


def main():
    args = sys.argv[1:]
    limit = None
    dry = '--dry-run' in args
    for i, a in enumerate(args):
        if a == '--limit' and i + 1 < len(args):
            limit = int(args[i + 1])

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute('''SELECT id, title, abstract, language, category1 FROM literature
                   WHERE (keywords IS NULL OR keywords='')
                     AND title IS NOT NULL AND title != ''
                   ORDER BY id''')
    targets = cur.fetchall()
    log.info(f'缺关键词的文献(含无摘要,将用标题提取): {len(targets)} 篇')

    if limit:
        targets = targets[:limit]

    updated = 0
    for rec in targets:
        kw = extract(rec)
        # 无摘要文献：用已关联的中文分类(category1)补充关键词，保证可检索
        if (not rec['abstract'] or not str(rec['abstract']).strip()) and rec['category1']:
            cat = str(rec['category1']).strip()
            if cat and cat not in kw:
                kw = kw + [cat]
        if kw:
            kw_str = '; '.join(kw)
            if dry:
                print(f"[DRY] #{rec['id']} | {rec['title'][:50]} -> {kw_str}")
                continue
            cur.execute("UPDATE literature SET keywords=?, updated_at=datetime('now') WHERE id=?",
                        (kw_str, rec['id']))
            updated += 1
            if updated % 50 == 0:
                conn.commit()
                log.info(f'进度: {updated}/{len(targets)}')

    conn.commit()
    if dry:
        log.info(f'DRY-RUN 结束，预览 {len(targets)} 篇，未写入数据库')
    else:
        log.info(f'完成！更新 {updated} 篇关键词')
        cur.execute("SELECT COUNT(*) FROM literature WHERE (keywords IS NULL OR keywords='')")
        print(f'  剩余缺keywords: {cur.fetchone()[0]}')
    conn.close()


if __name__ == '__main__':
    main()
