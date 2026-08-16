#!/usr/bin/env python3
"""
体育新闻研究知识库 - 定时任务调度器
功能：
1. 每日两次邮件推送研究动态
2. 每周生成研究摘要
3. 定期搜索最新文献
4. 自动同步到云盘
"""

import os
import sys
import json
import subprocess
import sqlite3
from datetime import datetime, timedelta, date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_manager import get_db, get_stats, add_trend

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db')

# ============================================
# 邮件推送配置（从配置文件读取）
# ============================================
EMAIL_CONFIG = {
    'smtp_server': os.environ.get('SMTP_SERVER', 'smtp.qq.com'),
    'smtp_port': int(os.environ.get('SMTP_PORT', '587')),
    'sender': os.environ.get('SENDER_EMAIL', ''),
    'password': os.environ.get('SENDER_PASSWORD', ''),
    'recipient': os.environ.get('RECIPIENT_EMAIL', ''),
}

def _load_email_config():
    """从配置文件加载邮箱设置"""
    cfg_path = os.path.join(PROJECT_ROOT, 'config', 'email_config.json')
    if os.path.exists(cfg_path):
        try:
            import json
            with open(cfg_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k in ['smtp_server', 'smtp_port', 'sender', 'password', 'recipient']:
                if data.get(k):
                    EMAIL_CONFIG[k] = data[k]
            if data.get('use_starttls') is not None:
                EMAIL_CONFIG['use_starttls'] = data['use_starttls']
            return True
        except Exception as e:
            print(f"⚠️ 邮箱配置文件读取失败: {e}")
    return False

_load_email_config()

# ============================================
# 每日更新任务
# ============================================
def _format_lit(lit):
    """把一条文献（sqlite3.Row）格式化为可读文本"""
    def _g(key, default=''):
        """安全取值"""
        try:
            v = lit[key]
            return v if v is not None else default
        except (KeyError, IndexError):
            return default
    title = _g('title')
    raw_author = _g('author') or ''
    # 处理占位符/缺失作者，展示更专业
    if not raw_author.strip() or raw_author.strip() in ('相关学者', 'Unknown', '未知', '待补充', '佚名'):
        author = '作者信息待补充'
    else:
        author = raw_author
    year = _g('year') or '年份待核'
    journal = _g('source_name')
    region = '国内' if _g('region') == 'domestic' else '国际'
    lang_map = {'zh':'中文','en':'英文','de':'德文','fr':'法文','ja':'日文','es':'西语','ko':'韩文'}
    lang = lang_map.get(_g('language'), _g('language'))
    cat = _g('category1') or '未分类'
    abstract = _g('abstract').strip()
    keywords = _g('keywords')
    doi = _g('doi')
    url = _g('url')

    lines = []
    lines.append(f"📌 {title}")
    lines.append(f"   👤 作者：{author}")
    meta = f"   🏷 分类：{cat} | {region} | {lang}"
    if journal:
        meta += f" | 📰 {journal}"
    meta += f" | 📅 {year}"
    lines.append(meta)
    if abstract:
        abs_short = abstract[:200] + ('…' if len(abstract) > 200 else '')
        lines.append(f"   📝 摘要：{abs_short}")
    if keywords:
        lines.append(f"   🔑 关键词：{keywords[:100]}")
    if doi:
        lines.append(f"   🔗 DOI：{doi}")
    elif url and url.startswith('http'):
        lines.append(f"   🔗 来源：{url}")
    return '\n'.join(lines)


def daily_track_section():
    """持续跟踪动态(供每日推送)：读取最近一轮 job_track 成果。"""
    p = os.path.join(PROJECT_ROOT, 'config', 'last_track_result.json')
    if not os.path.exists(p):
        return ''
    try:
        st = json.load(open(p, encoding='utf-8'))
    except Exception:
        return ''
    run_at = st.get('run_at', '未知')
    total = st.get('total_new', 0)
    by_src = st.get('by_source', {})
    src_str = '，'.join(f"{k}+{v}" for k, v in by_src.items()) if by_src else '—'
    cats = st.get('by_category', {})
    top = sorted(cats.items(), key=lambda x: -x[1])[:5]
    cat_str = '、'.join(f"{c}({n})" for c, n in top) if top else '—'
    return f"""
━━━━━━━━━━━━━━━━━━━━━━
🔄 持续跟踪动态（最近一轮 {run_at}）
━━━━━━━━━━━━━━━━━━━━━━━━
• 本轮新增前沿文献：**{total} 篇**（{src_str}）
• 涌现主题：{cat_str}

"""


def weekly_track_section(ws, we):
    """本周持续跟踪汇总(供周报)：聚合 fetch_log 本周记录。"""
    conn = get_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT source, SUM(new_inserted) ni, SUM(filtered_out) fo FROM fetch_log "
        "WHERE date(run_at) BETWEEN ? AND ? GROUP BY source",
        (ws, we)).fetchall()
    conn.close()
    if not rows:
        return "（本周无持续跟踪抓取记录）\n"
    lines, tot_new, tot_filt = [], 0, 0
    for r in rows:
        ni, fo = r['ni'] or 0, r['fo'] or 0
        lines.append(f"- {r['source']}：新增 {ni} 篇，自动过滤非体育新闻类 {fo} 篇")
        tot_new += ni
        tot_filt += fo
    return (f"本周持续跟踪共新增 **{tot_new}** 篇前沿文献，自动过滤无关文献 {tot_filt} 篇：\n"
            + '\n'.join(lines) + '\n')


def daily_update():
    """每日研究动态更新 - 展示最新文献的完整信息"""
    conn = get_db()
    conn.row_factory = sqlite3.Row

    # 知识库概况
    stats = get_stats(conn)

    # 最新研究成果：优先按年份倒序展示最前沿研究，同一年份内按收录时序倒序
    # （年份体现"研究内容的新"，id 体现"收录的新"，两者兼顾）
    latest_lits = conn.execute(
        "SELECT * FROM literature ORDER BY year DESC, id DESC LIMIT 10"
    ).fetchall()

    # 近期新增（近7天，基于created_at，反映知识库近期的实际更新）
    today = datetime.now().strftime('%Y-%m-%d')
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    new_recent = conn.execute(
        "SELECT COUNT(*) FROM literature WHERE date(created_at) BETWEEN ? AND ?",
        (week_ago, today)
    ).fetchone()[0]

    conn.close()

    # 标题根据是否有近期新增区分
    if new_recent > 0:
        section_title = f"🆕 近7天新增 {new_recent} 篇 · 最新研究成果精选（{len(latest_lits)} 篇）"
    else:
        section_title = f"📌 最新研究成果精选（最新 {len(latest_lits)} 篇）"

    report = f"""📡 体育新闻研究知识库 · 每日研究动态
{datetime.now().strftime('%Y-%m-%d %H:%M')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 知识库概况
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 总文献：{stats['total_literature']} 篇
• 国内：{stats['domestic']} 篇 | 国际：{stats['international']} 篇
• 涵盖语种：{len(stats['by_language'])} 种
   ({', '.join(f'{k}语{v}' for k,v in stats['by_language'].items())})
• 核心学者：{stats['total_scholars']} 位 | 研究主题：{stats['total_topics']} 个

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{section_title}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    for i, lit in enumerate(latest_lits, 1):
        report += f"\n【{i}】{_format_lit(lit)}\n"

    report += daily_track_section()

    report += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 近期值得关注的主题
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    conn2 = get_db()
    conn2.row_factory = sqlite3.Row
    hot_topics = conn2.execute(
        "SELECT name, hot_level FROM research_topics WHERE hot_level > 0 ORDER BY hot_level DESC LIMIT 5"
    ).fetchall()
    for t in hot_topics:
        stars = '★' * (t['hot_level'] // 20) + '☆' * (5 - t['hot_level'] // 20)
        report += f"• {t['name']} {stars} (热度{t['hot_level']})\n"
    conn2.close()

    report += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 使用提示
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 最新文献详情（摘要/作者/期刊/DOI）已完整展示
• 完整知识库请访问：GitHub Pages 公网站点
• 可通过智能大脑与研究助手深度探讨任意主题
• 每周一将收到本周研究摘要周报

📧 此邮件由体育新闻研究知识库自动生成
"""
    return report

# ============================================
# 每周摘要任务
# ============================================
def weekly_summary():
    """生成每周研究摘要

    修正统计逻辑：
    1. 「本周新增」= 本周（周一~周日）内 created_at 落在本周的文献数，
       真实反映本周知识库入库/更新的增量，而非总量。
    2. 「本周前沿研究」= 本周新增文献中发表年份最新的若干篇，
       真正反映本周采集到的学术前沿动态。
    3. 「本周重点主题」= 本周新增文献的分类分布（非全库分布）。
    4. 同一周多次调用采用 upsert，避免重复记录。
    """
    conn = get_db()
    conn.row_factory = sqlite3.Row

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    week_number = today.isocalendar()[1]
    ws = week_start.isoformat()
    we = week_end.isoformat()

    # ---------- 全库总量 ----------
    total_lit = conn.execute('SELECT COUNT(*) FROM literature').fetchone()[0]
    domestic = conn.execute("SELECT COUNT(*) FROM literature WHERE region='domestic'").fetchone()[0]
    international = conn.execute("SELECT COUNT(*) FROM literature WHERE region='international'").fetchone()[0]

    # ---------- 本周新增（增量，基于 created_at 落在本周） ----------
    new_lit = conn.execute(
        "SELECT COUNT(*) FROM literature WHERE date(created_at) BETWEEN ? AND ?",
        (ws, we)
    ).fetchone()[0]

    # 本周新增的分类分布（本周重点主题）
    week_cats = conn.execute(
        "SELECT category1, COUNT(*) as c FROM literature "
        "WHERE category1 IS NOT NULL AND category1 != '' AND date(created_at) BETWEEN ? AND ? "
        "GROUP BY category1 ORDER BY c DESC",
        (ws, we)
    ).fetchall()

    # ---------- 本周前沿研究（本周新增文献中发表年份最新者） ----------
    if new_lit > 0:
        frontier = conn.execute(
            "SELECT title, author, year, region, language, source_name FROM literature "
            "WHERE date(created_at) BETWEEN ? AND ? "
            "ORDER BY year DESC, id DESC LIMIT 12",
            (ws, we)
        ).fetchall()
    else:
        frontier = []

    # ---------- 最近收录（全库最新 id，作为补充） ----------
    recent = conn.execute(
        "SELECT title, author, year, region, language FROM literature ORDER BY id DESC LIMIT 8"
    ).fetchall()

    # ---------- 全库分类分布 ----------
    cats = conn.execute(
        "SELECT category1, COUNT(*) as c FROM literature WHERE category1 IS NOT NULL AND category1 != '' GROUP BY category1 ORDER BY c DESC"
    ).fetchall()

    # ---------- 生成摘要 ----------
    summary = f"""# 📋 体育新闻研究周报 — 第{week_number}周 ({ws} ~ {we})

---

## 📊 知识库总览

| 指标 | 数量 |
|------|------|
| 总文献数 | {total_lit} 篇 |
| 国内文献 | {domestic} 篇 |
| 国际文献 | {international} 篇 |
| 🆕 本周新增 | {new_lit} 篇 |

> 「本周新增」= 本周入库/更新的文献增量，反映本周知识库最新动态。

## 🆕 本周前沿研究（本周新增 · 发表年份最新）

"""
    if frontier:
        for i, r in enumerate(frontier, 1):
            region_flag = '🇨🇳' if r['region'] == 'domestic' else '🌍'
            year_str = str(r['year']) if r['year'] else '年份待核'
            author_raw = (r['author'] or '').strip()
            if not author_raw or author_raw in ('Unknown', '相关学者', '未知', '待补充', '佚名'):
                author_str = '作者待核'
            else:
                author_str = author_raw
            jnl = f" · {r['source_name']}" if r['source_name'] else ''
            summary += f"{i}. {region_flag} **{r['title'][:85]}** — {author_str} ({year_str}){jnl}\n"
    else:
        summary += "（本周暂无新增文献）\n"

    summary += f"\n## 🏆 本周重点主题（本周新增文献分布）\n\n"
    if week_cats:
        for cat in week_cats[:10]:
            summary += f"- **{cat['category1']}**: {cat['c']} 篇\n"
    else:
        summary += "- （本周暂无新增）\n"

    summary += f"\n## 📚 最近收录文献\n\n"
    for i, r in enumerate(recent[:8]):
        region_flag = '🇨🇳' if r['region'] == 'domestic' else '🌍'
        year_str = str(r['year']) if r['year'] else '年份待核'
        author_raw = (r['author'] or '').strip()
        if not author_raw or author_raw in ('Unknown', '相关学者', '未知', '待补充', '佚名'):
            author_str = '作者待核'
        else:
            author_str = author_raw
        summary += f"{i+1}. {region_flag} **{r['title'][:80]}** — {author_str} ({year_str})\n"

    summary += f"\n## 🔬 全库研究分类分布（累计）\n\n"
    for cat in cats[:10]:
        summary += f"- **{cat['category1']}**: {cat['c']} 篇\n"

    summary += f"\n## 🔄 本周持续跟踪\n\n"
    summary += weekly_track_section(ws, we)
    summary += f"\n## 🔔 下周重点\n\n"
    summary += "- [ ] 跟踪最新期刊出版\n"
    summary += "- [ ] 更新热门主题文献\n"
    summary += "- [ ] 翻译重点外文文献摘要\n"
    summary += "- [ ] 整理可撰写论文的主题\n"

    summary += f"\n---\n*自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*"

    # ---------- 存入数据库（upsert，同一周覆盖更新避免重复） ----------
    hot_topics_str = ', '.join([c['category1'] for c in week_cats[:5]]) if week_cats else ''
    conn.execute("""
        INSERT INTO weekly_summaries (week_start, week_end, week_number, summary_content,
        key_findings, new_literature_count, new_trends_count, hot_topics, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', datetime('now'))
        ON CONFLICT(week_start, week_number) DO UPDATE SET
          summary_content=excluded.summary_content,
          key_findings=excluded.key_findings,
          new_literature_count=excluded.new_literature_count,
          new_trends_count=excluded.new_trends_count,
          hot_topics=excluded.hot_topics,
          status='draft',
          updated_at=datetime('now')
    """, (
        ws, we, week_number, summary,
        f"第{week_number}周研究摘要；本周新增{new_lit}篇", new_lit,
        len(frontier), hot_topics_str
    ))
    conn.commit()
    conn.close()

    return summary

# ============================================
# 文献搜索任务
# ============================================
def search_new_literature():
    """搜索最新文献"""
    # 这个函数会被定时调用，实际搜索由Agent执行
    # 此处记录任务日志
    conn = get_db()
    conn.execute("""
        INSERT INTO task_logs (task_name, task_type, status, result_summary)
        VALUES (?, ?, 'completed', ?)
    """, (
        f"auto_search_{datetime.now().strftime('%Y%m%d_%H%M')}",
        'search',
        f'定时搜索触发于 {datetime.now().isoformat()}'
    ))
    conn.commit()
    conn.close()
    return True

# ============================================
# 邮件发送
# ============================================
def send_email(subject, body, content_type='daily_update', related_summary_id=None):
    """发送邮件，并写入 email_logs 记录。

    注意：与 `email_sender.send_email(subject, body_html, body_text)`（支持 HTML 附件）是两个独立实现。
    本版（scheduler 版）用于每日动态/周报，写 email_logs 记录；`email_sender` 版用于带 HTML/附件的邮件。
    """
    if not EMAIL_CONFIG['sender'] or not EMAIL_CONFIG['recipient']:
        print("⚠️ 邮件未配置，跳过发送")
        print(f"   主题: {subject}")
        print(f"   内容预览: {body[:200]}...")
        return False

    status = 'failed'
    error_msg = ''
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.header import Header
        from email.utils import formataddr, formatdate

        msg = MIMEMultipart('alternative')
        msg['From'] = formataddr((str(Header('Sports Journalism KB', 'utf-8')), EMAIL_CONFIG['sender']))
        msg['To'] = EMAIL_CONFIG['recipient']
        msg['Subject'] = str(Header(subject, 'utf-8'))
        msg['Date'] = formatdate(localtime=True)

        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(EMAIL_CONFIG['sender'], EMAIL_CONFIG['password'])
        server.sendmail(EMAIL_CONFIG['sender'], [EMAIL_CONFIG['recipient']], msg.as_string())
        server.quit()

        status = 'sent'
        print(f"✅ 邮件已发送: {subject}")
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 邮件发送失败: {e}")

    # 写入邮件日志（无论成功失败都记录）
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO email_logs (recipient, subject, content_type, related_summary_id,
                                    status, sent_at, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            EMAIL_CONFIG['recipient'], subject, content_type,
            related_summary_id, status,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S') if status == 'sent' else None,
            error_msg if status == 'failed' else None
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ 写入邮件日志失败: {e}")

    return status == 'sent'

# ============================================
# 命令行接口
# ============================================
def _send_wechat_daily():
    """发送微信每日动态（信息全部取自数据库真实数据）"""
    try:
        from wechat_pusher import send_daily_wechat
        # 让 send_daily_wechat 内部从数据库获取真实信息，不传 stats 覆盖
        # （避免用固定默认值覆盖真实的标题/作者/期刊信息）
        return send_daily_wechat()
    except Exception as e:
        print(f"⚠️ 微信推送失败: {e}")
        return False, str(e)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='体育新闻研究知识库 - 定时任务')
    parser.add_argument('action', choices=['daily', 'weekly', 'search', 'send-report'],
                       help='执行的操作')
    parser.add_argument('--send-email', action='store_true', help='同时发送邮件')
    parser.add_argument('--send-wechat', action='store_true', help='同时发送微信')
    
    args = parser.parse_args()
    
    if args.action == 'daily':
        print("📡 执行每日更新...")
        report = daily_update()
        print(report)
        if args.send_email:
            send_email(f"📡 体育新闻研究每日动态 - {datetime.now().strftime('%Y-%m-%d')}", report)
        if args.send_wechat:
            ok, msg = _send_wechat_daily()
            print(f"  微信推送: {msg}")
    
    elif args.action == 'weekly':
        print("📋 生成每周摘要...")
        summary = weekly_summary()
        print(summary)
        # 保存到文件
        week_file = os.path.join(PROJECT_ROOT, 'output', 'weekly', 
                                f"Weekly_{datetime.now().strftime('%Y_W%W')}.md")
        os.makedirs(os.path.dirname(week_file), exist_ok=True)
        with open(week_file, 'w', encoding='utf-8') as f:
            f.write(summary)
        print(f"\n✅ 周报已保存: {week_file}")
        if args.send_email:
            # 关联最新一条周报记录
            try:
                conn = get_db()
                sid = conn.execute("SELECT MAX(id) FROM weekly_summaries").fetchone()[0]
                conn.close()
            except Exception:
                sid = None
            send_email(f"📋 体育新闻研究周报 - 第{datetime.now().isocalendar()[1]}周",
                       summary, content_type='weekly_digest', related_summary_id=sid)
        if args.send_wechat:
            ok, msg = _send_wechat_daily()
            print(f"  微信推送: {msg}")
    
    elif args.action == 'search':
        print("🔍 触发文献搜索...")
        search_new_literature()
    
    elif args.action == 'send-report':
        print("📧 发送报告...")
        report = daily_update()
        send_email("📡 体育新闻研究知识库报告", report)
