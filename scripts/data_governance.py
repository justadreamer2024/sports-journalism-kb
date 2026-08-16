#!/usr/bin/env python3
"""
体育新闻研究知识库 - 数据质量治理模块
====================================
职责：
1. 为 literature 表新增 data_quality_status 字段
   - verified   : 信息完整、已核实，正式入库
   - needs_review : 信息不完整（作者/来源等缺失），等待核实
   - in_review  : 正在由 agent 核实中
2. 自动扫描并标记当前数据质量不合格的文献
3. 生成"待核查清单"（供 agent 逐一核实）
4. 提供核对完成后的状态更新接口（agent 调用）

用法：
  python3.11 data_governance.py scan      # 扫描并标记质量不合格文献
  python3.11 data_governance.py list      # 列出待核查文献清单
  python3.11 data_governance.py report    # 输出数据质量报告
"""
import os
import sys
import sqlite3
import json
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db')

# 作者占位符/缺失的判定规则（必须核查：作者不确切）
PLACEHOLDER_AUTHORS = {
    '', '相关学者', '未知', '待补充', '佚名', 'Unknown', 'N/A', '不详', None
}

# 来源为"相关XXX"占位（必须核查：来源不确切）
PLACEHOLDER_SOURCES = {'相关出版社', '相关期刊', '相关学报', '相关杂志'}

# 仅建议完善（来源是级别描述而非具体刊名，如"核心期刊"——保留但降低优先级）
SUGGEST_REFINE_SOURCES = {'核心期刊', '学术综述', '核心期刊/学术公众号', '学位论文'}

# 自媒体平台关键字（识别非正式学术来源）
# 注意：这里判断的是"来源是否是自媒体平台"，而非"是否在研究自媒体"
# 因此抖音号、公众号等（常见于正式论文的研究对象）不应出现在此列表中
SOCIAL_MEDIA_KEYWORDS = [
    '微信公众号', '微信订阅号', '搜狐号', '百家号', '头条号', '企鹅号',
    '网易号', '一点号', '大鱼号', 'UC号', '视频号文章', '知乎专栏',
    '自媒体平台', '公众号推文', '搜狐文章', '头条文章'
]

# 自媒体URL域名特征（正式期刊不会用这些域名）
SOCIAL_MEDIA_DOMAINS = [
    'sohu.com/a/', 'zhuanlan.zhihu.com', 'mp.weixin.qq.com',
    'baijiahao.baidu.com', 'weibo.com', 'toutiao.com', 'm.sohu.com'
]


def is_social_media(conn, lit):
    """判断一条文献是否来自自媒体平台（依据来源名称和URL，而非标题）"""
    source = (lit['source_name'] or '').lower()
    url = (lit['url'] or '').lower()
    # 来源名称含自媒体关键词
    for kw in SOCIAL_MEDIA_KEYWORDS:
        if kw.lower() in source:
            return True
    # URL域名匹配（精确匹配自媒体域名特征）
    for d in SOCIAL_MEDIA_DOMAINS:
        if d in url:
            return True
    return False

# 状态常量
STATUS_VERIFIED = 'verified'
STATUS_NEEDS_REVIEW = 'needs_review'
STATUS_IN_REVIEW = 'in_review'
STATUS_SOCIAL_MEDIA = 'social_media'  # 自媒体来源，默认不进入正式库


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn):
    """确保 data_quality_status 字段存在"""
    cols = [r[1] for r in conn.execute('PRAGMA table_info(literature)').fetchall()]
    if 'data_quality_status' not in cols:
        conn.execute(
            "ALTER TABLE literature ADD COLUMN data_quality_status TEXT DEFAULT 'verified'"
        )
        conn.commit()
        print("✅ 已新增 data_quality_status 字段")
    else:
        print("ℹ️ data_quality_status 字段已存在")


def scan(conn):
    """扫描并标记质量不合格的文献（作者/来源/摘要缺失）"""
    # 若字段尚未创建，先创建并提交
    cols = [r[1] for r in conn.execute('PRAGMA table_info(literature)').fetchall()]
    if 'data_quality_status' not in cols:
        conn.execute("ALTER TABLE literature ADD COLUMN data_quality_status TEXT DEFAULT 'verified'")
        conn.commit()
    rows = conn.execute("SELECT * FROM literature").fetchall()
    flagged = []
    social_media = []
    for r in rows:
        author = (r['author'] or '').strip()
        source = (r['source_name'] or '').strip()
        abstract = (r['abstract'] or '').strip()
        
        # 自媒体来源识别：优先处理
        if is_social_media(conn, r):
            social_media.append((r['id'], '自媒体来源'))
            conn.execute(
                "UPDATE literature SET source_type='social_media', data_quality_status=?, reviewer_notes=?, updated_at=? WHERE id=?",
                (STATUS_SOCIAL_MEDIA, '自媒体来源，非正式学术文献', datetime.now().isoformat(), r['id'])
            )
            continue
        
        reasons = []
        must_review = False
        # 必须核查：作者占位/缺失
        if author in PLACEHOLDER_AUTHORS or author.startswith('相关学者'):
            reasons.append('作者缺失/占位符')
            must_review = True
        # 必须核查：来源为"相关XXX"占位
        if source in PLACEHOLDER_SOURCES or (source.startswith('相关') and source not in SUGGEST_REFINE_SOURCES):
            reasons.append('来源不确切')
            must_review = True
        # 建议完善：来源是级别描述（核心期刊等），非硬错误
        elif source in SUGGEST_REFINE_SOURCES:
            reasons.append('来源为级别描述，建议补充具体刊名')
        # 无摘要是"待完善"，而非"必须核查"（核心著录信息完整即可正式入库）
        if not abstract:
            reasons.append('无摘要(待完善)')
        
        if must_review:
            flagged.append((r['id'], '; '.join(reasons)))
            conn.execute(
                "UPDATE literature SET data_quality_status=?, reviewer_notes=?, updated_at=? WHERE id=?",
                (STATUS_NEEDS_REVIEW, '; '.join(reasons), datetime.now().isoformat(), r['id'])
            )
        elif not abstract:
            # 仅缺摘要：保持 verified，但记录待完善建议
            conn.execute(
                "UPDATE literature SET reviewer_notes=?, updated_at=? WHERE id=?",
                ('无摘要(待完善)', datetime.now().isoformat(), r['id'])
            )
            flagged.append((r['id'], '无摘要(待完善)'))
    
    conn.commit()
    print(f"\n📋 扫描完成：共 {len(rows)} 篇")
    if social_media:
        print(f"   📱 识别自媒体 {len(social_media)} 篇: {[i[0] for i in social_media]}")
    hard = [f for f in flagged if '占位' in f[1] or '不确切' in f[1]]
    soft = [f for f in flagged if '待完善' in f[1]]
    print(f"   🔴 必须核查 {len(hard)} 篇（作者/来源缺失）")
    for fid, reason in hard:
        print(f"      - ID={fid}: {reason}")
    print(f"   🟡 建议完善 {len(soft)} 篇（无摘要）")
    return flagged


def list_needs_review(conn):
    """列出待核查文献"""
    rows = conn.execute(
        "SELECT * FROM literature WHERE data_quality_status IN ('needs_review','in_review') "
        "ORDER BY id"
    ).fetchall()
    return rows


def report(conn):
    """输出数据质量报告"""
    total = conn.execute("SELECT COUNT(*) FROM literature").fetchone()[0]
    verified = conn.execute(
        "SELECT COUNT(*) FROM literature WHERE data_quality_status='verified'"
    ).fetchone()[0]
    needs = conn.execute(
        "SELECT COUNT(*) FROM literature WHERE data_quality_status='needs_review'"
    ).fetchone()[0]
    in_review = conn.execute(
        "SELECT COUNT(*) FROM literature WHERE data_quality_status='in_review'"
    ).fetchone()[0]
    
    print("=" * 50)
    print("📊 数据质量报告")
    print("=" * 50)
    print(f"总文献数      : {total}")
    print(f"✅ 已核实入库  : {verified}")
    print(f"⚠️  待核查     : {needs}")
    print(f"🔄 核实中     : {in_review}")
    print(f"核实率        : {verified/total*100:.1f}%")
    print("=" * 50)
    return {'total': total, 'verified': verified, 'needs_review': needs, 'in_review': in_review}


def update_status(lit_id, new_status, reviewer_notes=''):
    """更新单篇文献的质量状态（供 agent 核对后调用）"""
    conn = _conn()
    conn.execute(
        "UPDATE literature SET data_quality_status=?, reviewer_notes=?, updated_at=? WHERE id=?",
        (new_status, reviewer_notes, datetime.now().isoformat(), lit_id)
    )
    conn.commit()
    conn.close()
    print(f"✅ 文献 ID={lit_id} 状态已更新为 {new_status}")


def export_review_list():
    """导出待核查清单（JSON，供 agent 处理）"""
    conn = _conn()
    rows = list_needs_review(conn)
    items = []
    for r in rows:
        items.append({
            'id': r['id'],
            'title': r['title'],
            'year': r['year'],
            'source_type': r['source_type'],
            'source_name': r['source_name'],
            'author': r['author'],
            'keywords': r['keywords'],
            'abstract': r['abstract'],
            'reasons': r['reviewer_notes'],
            'status': r['data_quality_status'],
        })
    conn.close()
    return items


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else 'report'
    conn = _conn()
    ensure_column(conn)
    
    if action == 'scan':
        # 先确保字段存在并提交，再重新连接避免 WAL 下 schema 变更可见性问题
        ensure_column(conn)
        conn.close()
        conn = _conn()
        scan(conn)
    elif action == 'remove_social_media':
        # 删除所有自媒体文章
        conn.execute("DELETE FROM literature WHERE source_type='social_media' OR data_quality_status='social_media'")
        conn.commit()
        print(f"✅ 已删除 {conn.total_changes} 篇自媒体文章")
    elif action == 'list_social_media':
        for r in conn.execute("SELECT id, title, source_name, data_quality_status FROM literature WHERE source_type='social_media' OR data_quality_status='social_media'").fetchall():
            print(f"ID={r['id']} | [{r['source_type']}] | {r['title'][:40]} | {r['data_quality_status']}")
    elif action == 'list':
        for r in list_needs_review(conn):
            print(f"ID={r['id']} | {r['year']} | [{r['source_type']}] | 作者=[{r['author']}] | {r['title'][:40]}")
    elif action == 'report':
        report(conn)
    elif action == 'export':
        data = export_review_list()
        out = os.path.join(PROJECT_ROOT, 'output', 'reports', 'review_list.json')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"📄 待核查清单已导出: {out} (共 {len(data)} 篇)")
    conn.close()
