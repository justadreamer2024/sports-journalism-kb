#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从中文标题提取关键词（#118 剩余项：173篇书评/editorial文献）
这些文献（多为IJSC书评/编辑部文章）天然无英文摘要，无法用英文词表或API提取。
本脚本基于中文体育新闻领域词典，从 title_cn 提取关键词，闭环补齐 keywords。

用法：
  python3.11 scripts/extract_keywords_cn.py [--dry-run]
"""
import sqlite3
import sys

DB = '/workspace/sports-journalism-kb/database/knowledge_base.db'

# 中文体育新闻/媒体领域词典（按优先级排序，长词在前）
CN_TERMS = [
    # 体育新闻/媒体核心
    '体育新闻', '体育传播', '体育媒体', '体育媒介', '新闻业', '新闻学', '新闻报道',
    '记者', '新闻工作者', '媒体', '媒介', '传播', '广播电视', '广播', '电视', '报纸',
    '新媒体', '数字媒体', '社交媒体', '自媒体', '体育评论', '新闻价值', '新闻伦理',
    '新闻专业主义', '新闻教育', '新闻史', '媒体产业', '媒体经济学',
    # 体育分类
    '体育', '运动', '奥运会', '奥林匹克', '足球', '篮球', '网球', '棒球', '橄榄球',
    '高尔夫', '赛车', '电竞', '电子竞技', '体育赛事', '大型体育赛事', '体育产业',
    '职业体育', '体育管理', '体育组织', '体育治理', '体育政策', '体育法', '体育营销',
    '体育消费', '体育文化', '体育社会', '体育社会学', '体育心理学',
    # 社会/政治维度
    '性别', '女性', '女性主义', '种族', '移民', '难民', '残障', '残疾人', '包容',
    '平等', '政治', '外交', '民族主义', '国家形象', '地缘政治', '人权',
    '社会阶层', '阶层', '阶级', '社会资本', '文化资本', '社会融合', '社区',
    # 技术/新媒体
    '人工智能', '算法', '数据新闻', '大数据', '技术', '数字化转型', '流媒体',
    '直播', '短视频', '平台', '游戏', '虚拟现实', '增强现实',
    # 专题
    '腐败', '博彩', '兴奋剂', '精神健康', '心理健康', '伤病', '脑震荡', '健康传播',
    '脑损伤', '成瘾', '身体活动', '体育参与', '青少年体育', '体育教育', '体育课',
    '教练', '运动员', '球迷', '粉丝', '观众', '受众',
    '书评', '书籍', '教材', '手册', '导言', '编辑前言', '更正启事',
    # 跨领域
    '传播策略', '公共外交', '国际传播', '跨文化', '全球', '国际',
    '经济', '商业', '金融', '融资', '版权', '赞助', '广告', '品牌',
]

# 停用/冗余词
STOP = {'一种', '一种的', '在', '的', '与', '和', '及', '从', '到', '对', '看', '中', '探',
        '论', '研究', '分析', '路径', '视角', '视野', '最新', '深入', '及时', '启示',
        '世界', '反思', '重思', '当代'}


def extract_cn(title):
    """从中文标题提取关键词"""
    if not title:
        return []
    hits = []
    matched_ranges = []
    for term in CN_TERMS:
        if term in title:
            hits.append(term)
    # 去重，按标题出现顺序
    seen = set()
    ordered = []
    for term in CN_TERMS:
        if term in title and term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered[:8]


def main():
    dry = '--dry-run' in sys.argv
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('''SELECT id, title_cn FROM literature
                   WHERE (abstract IS NULL OR abstract='')
                     AND (keywords IS NULL OR keywords='')
                   ORDER BY id''')
    rows = cur.fetchall()
    print(f'缺摘要缺关键词的书评/editorial文献: {len(rows)} 篇')

    updated = 0
    no_kw = 0
    for r in rows:
        kw = extract_cn(r['title_cn'])
        if not kw:
            no_kw += 1
            continue
        kw_str = '; '.join(kw)
        if dry:
            print(f"[DRY] #{r['id']} {r['title_cn'][:40]} -> {kw_str}")
            continue
        cur.execute("UPDATE literature SET keywords=?, updated_at=datetime('now') WHERE id=?",
                    (kw_str, r['id']))
        updated += 1
    conn.commit()
    if dry:
        print(f'DRY-RUN 预览 {len(rows)-no_kw} 篇，未写入')
    else:
        print(f'完成！更新 {updated} 篇关键词（{no_kw} 篇无词表命中）')
        cur.execute("SELECT COUNT(*) FROM literature WHERE (keywords IS NULL OR keywords='')")
        print(f'  全库剩余缺keywords: {cur.fetchone()[0]}')
    conn.close()


if __name__ == '__main__':
    main()
