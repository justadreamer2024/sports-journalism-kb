#!/usr/bin/env python3
"""生成最新周报并发送到邮箱（动态统计，修正硬编码问题）"""
import os
import sys
import sqlite3
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scheduler import weekly_summary
from email_sender import load_config, send_email

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db')

def get_db_stats():
    """从数据库动态读取最新统计，避免硬编码过时数字"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    total = c.execute('SELECT COUNT(*) FROM literature').fetchone()[0]
    domestic = c.execute("SELECT COUNT(*) FROM literature WHERE region='domestic'").fetchone()[0]
    international = c.execute("SELECT COUNT(*) FROM literature WHERE region='international'").fetchone()[0]
    # 本周新增
    today = date.today()
    ws = today - timedelta(days=today.weekday())
    we = ws + timedelta(days=6)
    new_lit = c.execute(
        "SELECT COUNT(*) FROM literature WHERE date(created_at) BETWEEN ? AND ?",
        (ws.isoformat(), we.isoformat())
    ).fetchone()[0]
    # 分类分布
    cats = c.execute(
        "SELECT category1, COUNT(*) as c FROM literature WHERE category1 IS NOT NULL AND category1 != '' GROUP BY category1 ORDER BY c DESC LIMIT 5"
    ).fetchall()
    # 语种
    langs = c.execute(
        "SELECT language, COUNT(*) as c FROM literature GROUP BY language"
    ).fetchall()
    lang_map = {'zh':'中文','en':'英文','de':'德文','fr':'法文','ja':'日文','es':'西语','ko':'韩文'}
    lang_str = '/'.join(sorted({lang_map.get(r['language'], r['language']) for r in langs}))
    conn.close()
    return {
        'total': total, 'domestic': domestic, 'international': international,
        'new_lit': new_lit, 'cats': cats, 'lang_str': lang_str,
        'week_number': today.isocalendar()[1], 'week_start': ws.isoformat(), 'week_end': we.isoformat()
    }

def main():
    print("📋 生成周报（动态统计）...")
    summary = weekly_summary()
    stats = get_db_stats()

    # 保存到文件
    week_file = os.path.join(PROJECT_ROOT, 'output', 'weekly', f'Weekly_2026_W{stats["week_number"]}.md')
    os.makedirs(os.path.dirname(week_file), exist_ok=True)
    with open(week_file, 'w', encoding='utf-8') as f:
        f.write(summary)
    print(f"✅ 周报已保存: {week_file}")

    # 发送邮件
    config = load_config()
    recipient = config.get('recipient', 'mengxiangjun@gmail.com')

    # 邮件HTML版（动态生成，所有数字从数据库读取）
    cat_items = '\n'.join([
        f'<li><strong>{c["category1"]}</strong>：{c["c"]} 篇</li>' for c in stats['cats']
    ])
    html = f"""
    <div style="font-family:'PingFang SC','Microsoft YaHei',sans-serif;max-width:620px;margin:0 auto;padding:20px;color:#333;">
        <h2 style="color:#1a6db5;border-bottom:2px solid #1a6db5;padding-bottom:10px;">📋 体育新闻研究周报 · 第{stats['week_number']}周</h2>
        <p>您好！这是您本周的体育新闻研究动态摘要，基于知识库最新 <strong>{stats['total']} 篇文献</strong> 动态生成。</p>

        <h3 style="color:#1a3a5c;">📊 知识库总览</h3>
        <table style="border-collapse:collapse;width:100%;font-size:13px;">
            <tr><td style="padding:6px;border:1px solid #ddd;"><strong>总文献</strong></td><td style="padding:6px;border:1px solid #ddd;">{stats['total']} 篇</td></tr>
            <tr><td style="padding:6px;border:1px solid #ddd;"><strong>国际文献</strong></td><td style="padding:6px;border:1px solid #ddd;">{stats['international']} 篇</td></tr>
            <tr><td style="padding:6px;border:1px solid #ddd;"><strong>国内文献</strong></td><td style="padding:6px;border:1px solid #ddd;">{stats['domestic']} 篇</td></tr>
            <tr><td style="padding:6px;border:1px solid #ddd;"><strong>🆕 本周新增</strong></td><td style="padding:6px;border:1px solid #ddd;">{stats['new_lit']} 篇</td></tr>
            <tr><td style="padding:6px;border:1px solid #ddd;"><strong>语言覆盖</strong></td><td style="padding:6px;border:1px solid #ddd;">{stats['lang_str']}</td></tr>
        </table>

        <h3 style="color:#1a3a5c;">🔬 主要研究主题</h3>
        <ul style="line-height:1.8;">
            {cat_items}
        </ul>

        <h3 style="color:#1a3a5c;">📄 完整周报</h3>
        <p>本周完整周报（含前沿研究、重点主题、最近收录文献）请见下方正文。</p>

        <p style="color:#888;font-size:12px;border-top:1px solid #eee;padding-top:12px;margin-top:20px;">
            此邮件由体育新闻研究知识库自动生成<br>
            发送时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}
        </p>
    </div>
    """

    ok, msg = send_email(
        subject=f"📋 体育新闻研究周报 - 第{stats['week_number']}周 ({datetime.now().strftime('%Y-%m-%d')})",
        body_html=html,
        body_text=summary
    )
    print(f"{'✅' if ok else '❌'} 邮件发送: {msg}")
    print(f"   收件人: {recipient}")

if __name__ == '__main__':
    main()
