#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《体育学刊》官网免费采集脚本（requests，服务端渲染）
================================================================
来源：https://tyxk.scnu.edu.cn/ （教育部主管、华南理工/华南师大主办，CSSCI/北大核心）
方式：全部 requests + BeautifulSoup，无需 Playwright，速度快、无验证码。

链路：
  过刊目录 /book/{year}nian/di{issue}qi/  ->  文章卡片(h5.card-title > a，含标题+详情URL)
  文章详情 /a/{YYYYMMDD}/{id}.html        ->  标题/作者/单位/中英摘要/关键词/DOI/分类号 + PDF链接

入库：literature 表，collected_by='official_website'，is_core=1，region='domestic'
      正文取自摘要（官网详情页含完整中英摘要，正文在 PDF 中，full_text_available=1）

目录页结构（两种兼容，统一用 h5 a[href] 宽松选择 + URL 格式甄别）：
  2025+   : <h5 class="card-title"><a href=详情页>
  2023-2024: <h5><a href=详情页>（无 card-title class）

已知数据源限制：
  - 2019-2023（及部分2024）老结构详情页只含单位行、中英摘要/关键词，不含作者姓名行，
    作者信息仅存在于 PDF 全文。故这部分文章 author 留空（客观缺失，非解析缺陷）。
  - 新结构（2025+）详情页含完整作者行（可带数字脚注），作者解析完整。

用法：
  python3 fetch_tykx_scnu.py                 # 默认采集 2019-2026 全期
  python3 fetch_tykx_scnu.py --start 2023 --end 2026
  python3 fetch_tykx_scnu.py --dry-run       # 试运行不写库
  python3 fetch_tykx_scnu.py --sport-only    # 只入库体育新闻/传播相关文章（推荐）
"""
import os, sys, re, time, json, logging, sqlite3, argparse
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('tykx_scnu')

BASE = 'https://tyxk.scnu.edu.cn'
BOOK_URL = BASE + '/book/{year}nian/di{issue}qi/'

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
SLEEP = 0.6  # 请求间隔(秒)，礼貌限速

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, 'database', 'knowledge_base.db')

session = requests.Session()
session.headers.update({'User-Agent': UA, 'Referer': BASE + '/'})

# 体育新闻/传播/媒体相关关键词（判定是否体育新闻研究相关）
SPORT_MEDIA_WORDS = (
    '新闻', '媒体', '传播', '报道', '记者', '电视', '直播', '转播', '广播', '网络',
    '微信', '微博', '短视频', '抖音', '媒介', '舆情', '话语', '叙事', '宣传', '受众',
    '粉丝', '球迷', '品牌', '广告', '营销', '版权', '赛事传播', '体育传播', '新媒体',
    '社交媒体', '新闻价值', '传媒', '信息', '数字媒体', '可视化', '赛事报道',
)


def http_get(url, retries=3):
    """带重试的 GET 请求，返回 HTML 文本或 None。
    强制用 UTF-8 解码（站点为 UTF-8 但响应头无 charset，requests 默认误判 ISO-8859-1）。"""
    for i in range(retries):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200:
                # 优先用 apparent_encoding；本站为 utf-8
                enc = (r.apparent_encoding or 'utf-8').lower()
                if enc not in ('utf-8', 'utf8'):
                    enc = 'utf-8'
                return r.content.decode(enc, errors='replace')
            log.warning('HTTP %d: %s', r.status_code, url)
        except requests.RequestException as e:
            log.warning('请求失败(%d/3) %s: %s', i + 1, url, str(e)[:60])
        time.sleep(1 + i)
    return None


def discover_issues(start_year, end_year):
    """从过刊总目录页 /book/ 动态发现 (year, issue_key, url) 列表。
    处理各期 URL 不一致（如 2026年第3期为 di3qi_）。"""
    html = http_get(BASE + '/book/')
    if not html:
        log.error('过刊总目录抓取失败')
        return []
    soup = BeautifulSoup(html, 'html.parser')
    issues = []
    seen = set()
    for a in soup.select('a[href]'):
        href = a['href']
        m = re.search(r'/book/(\d{4})nian/(di\d+qi)_?/?$', href)
        if not m:
            continue
        year = int(m.group(1))
        if not (start_year <= year <= end_year):
            continue
        key = m.group(2)
        # 提取期号数字
        im = re.search(r'di(\d+)qi', key)
        issue_num = int(im.group(1)) if im else 0
        # 去重（同一期可能多个链接）
        sig = (year, issue_num)
        if sig in seen:
            continue
        seen.add(sig)
        issues.append({'year': year, 'issue': issue_num, 'issue_key': key,
                       'url': href})
    issues.sort(key=lambda x: (x['year'], x['issue']))
    log.info('发现 %d 期次目录(含 URL)', len(issues))
    return issues


def fetch_issue(year, issue, issue_url=None):
    """抓取一期过刊目录，返回文章卡片列表 [{title, url}]。issue_url 为真实目录 URL。"""
    url = issue_url or BOOK_URL.format(year=year, issue=issue)
    html = http_get(url)
    if not html:
        log.warning('目录抓取失败: %s', url)
        return None
    soup = BeautifulSoup(html, 'html.parser')
    arts = []
    # 栏目名（误作文章的导航项）
    section_names = ('探索与争鸣', '运动项目文化研究', '体育人文社会学', '学校体育',
                     '运动人体科学', '体育新闻学', '体育史', '奥林匹克研究', '编辑工作',
                     '期刊全文', '友情链接', '栏目', '目录', '体育产业', '体育教育')
    # 文章卡片：兼容两种结构——
    #   2025+：<h5 class="card-title"><a href=详情页>
    #   2023-2024：<h5><a href=详情页>（无 card-title class）
    # 统一用 h5 a[href] 宽松选择，靠 URL 格式(/a/日期/数字.html)甄别真文章、排除导航公告
    for a in soup.select('h5 a[href]'):
        title = a.get_text(' ', strip=True)
        href = a.get('href', '')
        if not title or title in section_names:
            continue
        # 排除导航/公告（详情页 URL 形如 /a/日期/数字.html）
        m = re.search(r'/a/(\d{8})/(\d+)\.html', href)
        if not m:
            continue
        arts.append({'title': title, 'url': href, 'year': year, 'issue': issue})
    # 去重
    seen = set()
    uniq = []
    for a in arts:
        if a['url'] not in seen:
            seen.add(a['url'])
            uniq.append(a)
    return uniq


def fetch_detail(art):
    """抓取文章详情，返回补充字段。"""
    html = http_get(art['url'])
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    detail = {}

    # 标题（页内主标题）
    title_el = soup.select_one('h1') or soup.select_one('h2.page-title') or soup.select_one('.article-title')
    if title_el:
        detail['title'] = title_el.get_text(' ', strip=True)

    # 作者行：作者行是中文姓名（可带数字脚注），用逗号/顿号连接多个作者，
    # 且以作者姓名开头、不以 '(' 开头（单位行才以 '(' 开头）。
    # 样例："于素梅，王晓燕"、"赵锋1，宋继新1，宋健2"、"陈作松"、"孟欢欢1，2，舒为平1"
    author = ''
    for p in soup.find_all('p'):
        t = p.get_text(' ', strip=True)
        compact = t.replace(' ', '')
        # 排除含关键词/元信息的段落
        if any(k in compact for k in ('摘要', '关键词', '分类号', '文章编号', '参考文献',
                                      '基金项目', '作者简介', '中图分类号', 'Abstract',
                                      '发布时间', '浏览', '阅读', '点击', '收稿', '修回')):
            continue
        # 单位行以 '(' 开头，天然排除
        if compact.startswith('('):
            continue
        # 作者行通常是短行（姓名+脚注，一般 <40 字符）
        if not (1 < len(compact) < 40):
            continue
        # 判定：以中文姓名（可带西文名/间隔号）开头，且含中文姓名主体
        zh_chars = re.findall(r'[\u4e00-\u9fa5]', compact)
        if not re.match(r'^[\u4e00-\u9fa5·A-Za-z]', compact):
            continue
        # 至少有 2 个汉字（单字姓或复姓 + 名，至少 2 字）才像人名
        if len(zh_chars) < 2:
            continue
        # 排除仍混入导航/标语的行：作者行通常含逗号/顿号/数字脚注或为单人姓名，
        # 且不含机构特征词
        if any(k in compact for k in ('大学', '学院', '研究院', '研究所', '编辑部',
                                      '主管', '主办', '期刊', '关注', '教育部')):
            continue
        author = compact
        break

    # 单位行：形如 "(1. 北京邮电大学 ... ；2. 中山大学 ...)" 或 "(中国教育科学研究院，北京 100088)"
    affiliation = ''
    for p in soup.find_all('p'):
        t = p.get_text(' ', strip=True)
        compact = t.replace(' ', '')
        # 以 '(' 开头且含中文（机构名），即为单位/署名地址行
        if compact.startswith('(') and re.search(r'[\u4e00-\u9fa5]', compact):
            affiliation = compact
            break

    # 中英文摘要
    abs_cn, abs_en = '', ''
    for p in soup.find_all('p'):
        t = p.get_text(' ', strip=True)
        compact = t.replace(' ', '')
        if compact.startswith('摘要') and not abs_cn:
            abs_cn = re.sub(r'^摘要\s*[：:]?', '', compact).strip()
        if compact.lower().startswith('abstract') and not abs_en:
            abs_en = re.sub(r'^abstract\s*[：:]?', '', compact, flags=re.I).strip()

    # 关键词
    kw_cn, kw_en = '', ''
    for p in soup.find_all('p'):
        t = p.get_text(' ', strip=True)
        compact = t.replace(' ', '')
        if compact.startswith('关键词') and not kw_cn:
            kw_cn = re.sub(r'^关键词\s*[：:]?', '', compact).strip()
        if compact.lower().startswith('keywords') and not kw_en:
            kw_en = re.sub(r'^keywords\s*[：:]?', '', compact, flags=re.I).strip()

    # 文章编号(含DOI) / 分类号
    article_id, doi = '', ''
    for p in soup.find_all('p'):
        t = p.get_text(' ', strip=True)
        compact = t.replace(' ', '')
        # 注：Python3 中 \w 匹配 Unicode 词字符(含中文)，须用 [A-Za-z0-9\-] 限定纯 ASCII
        m = re.search(r'文章编号[：:]?\s*([A-Za-z0-9\-()]+)', compact)
        if m:
            article_id = m.group(1)
        m = re.search(r'DOI[：:]?\s*([A-Za-z0-9.\-/]+)', compact, re.I)
        if m:
            doi = m.group(1)
        m = re.search(r'中图分类号[：:]?\s*([A-Za-z0-9\-]+)', compact)
        if m:
            detail['category_code'] = m.group(1)

    # PDF 下载链接（处理协议相对/绝对/相对三类 URL）
    pdf_url = ''
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '.pdf' in href.lower():
            if href.startswith('http://') or href.startswith('https://'):
                pdf_url = href
            elif href.startswith('//'):
                pdf_url = 'https:' + href
            elif href.startswith('/'):
                pdf_url = BASE + href
            else:
                pdf_url = BASE + '/' + href
            break

    detail.update({
        'author': author, 'affiliation': affiliation,
        'abstract_cn': abs_cn, 'abstract_en': abs_en,
        'keywords_cn': kw_cn, 'keywords_en': kw_en,
        'article_id': article_id, 'doi': doi, 'pdf_url': pdf_url,
    })
    return detail


def is_sport_media(title, abstract=''):
    """判定是否体育新闻/传播相关（标题或摘要含关键词）。"""
    text = (title or '') + (abstract or '')
    return any(w in text for w in SPORT_MEDIA_WORDS)


def get_conn():
    return sqlite3.connect(DB_PATH)


def upsert_article(conn, art, dry_run=False):
    """去重入库。url 用官网详情页作唯一键。"""
    if not art.get('url') or not art.get('title'):
        return False
    cur = conn.execute("SELECT id FROM literature WHERE url=? OR title=?",
                       (art['url'], art['title']))
    if cur.fetchone():
        return False
    if dry_run:
        return True
    abstract = art.get('abstract_cn') or ''
    keywords = art.get('keywords_cn') or ''
    author = (art.get('author') or '').rstrip('，, ')
    year = art.get('year')
    conn.execute(
        """INSERT OR IGNORE INTO literature
           (title, title_cn, author, year, source_type, source_name, issue,
            pages, url, region, language, abstract, abstract_cn, keywords,
            collected_by, is_core, full_text_available, doi, data_source)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (art['title'], art['title'], author,
         year, 'journal', '体育学刊', str(art.get('issue', '')),
         '', art['url'], 'domestic', 'zh',
         abstract, abstract, keywords, 'official_website', 1,
         1 if art.get('abstract_en') else 0, art.get('doi', ''), 'tykx_scnu_official'))
    return True


def run(start_year, end_year, dry_run=False, sport_only=False):
    conn = get_conn()
    total_added = 0
    total_scanned = 0
    total_sport = 0
    # 从过刊总目录动态发现各期 URL（解决 diNqi 后缀不一致）
    issues = discover_issues(start_year, end_year)
    for it in issues:
        year, issue = it['year'], it['issue']
        arts = fetch_issue(year, issue, it['url'])
        if arts is None:
            continue
        if not arts:
            continue
        log.info('%d年第%d期: %d篇', year, issue, len(arts))
        for art in arts:
            total_scanned += 1
            detail = fetch_detail(art)
            art.update(detail)
            # 体育新闻相关筛选
            if sport_only and not is_sport_media(art.get('title', ''), art.get('abstract_cn', '')):
                continue
            total_sport += 1
            if upsert_article(conn, art, dry_run):
                total_added += 1
            time.sleep(SLEEP)
        conn.commit()
        time.sleep(SLEEP)
    conn.close()
    log.info('采集完成: 扫描 %d 篇，体育相关 %d 篇，新增 %d 篇(去重后)',
             total_scanned, total_sport, total_added)
    return total_added


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='《体育学刊》官网免费采集')
    ap.add_argument('--start', type=int, default=2019, help='起始年份')
    ap.add_argument('--end', type=int, default=2026, help='结束年份')
    ap.add_argument('--dry-run', action='store_true', help='试运行不写库')
    ap.add_argument('--sport-only', action='store_true', help='只入库体育新闻/传播相关文章')
    args = ap.parse_args()
    run(args.start, args.end, args.dry_run, args.sport_only)
