#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成研究地图可视化（方法×理论×主题）
输出：交互式 HTML 研究地图
"""
import sqlite3
import json
import os
import collections

# 项目根目录（相对脚本定位，避免硬编码 /workspace）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db')
# 中间数据输出到项目内 .tmp（避免 /tmp 临时文件依赖链）
TMP_DIR = os.path.join(PROJECT_ROOT, 'scripts', '.tmp')
os.makedirs(TMP_DIR, exist_ok=True)
DATA_OUT = os.path.join(TMP_DIR, 'research_map_data.json')

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # ============ 1. 基础统计 ============
    c.execute("SELECT COUNT(*) FROM literature")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM research_topics")
    topic_count = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT research_method) FROM literature WHERE research_method!=''")
    method_count = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT theoretical_framework) FROM literature WHERE theoretical_framework!=''")
    theory_count = c.fetchone()[0]

    # ============ 2. 研究方法分布 ============
    c.execute("""
        SELECT research_method, COUNT(*) as cnt FROM literature
        WHERE research_method!='' AND research_method!='待补'
        GROUP BY research_method ORDER BY cnt DESC
    """)
    methods = [dict(r) for r in c.fetchall()]
    # 合并相近方法（按主方法归类）
    def main_method(m):
        m = m.replace('、', ',').replace('，', ',')
        parts = [p.strip() for p in m.split(',')]
        return parts[0] if parts else m
    method_agg = collections.Counter()
    for r in methods:
        method_agg[main_method(r['research_method'])] += r['cnt']
    method_dist = method_agg.most_common(15)

    # ============ 3. 理论框架分布 ============
    c.execute("""
        SELECT theoretical_framework, COUNT(*) as cnt FROM literature
        WHERE theoretical_framework!='' AND theoretical_framework!='待补'
        GROUP BY theoretical_framework ORDER BY cnt DESC
    """)
    theories = [dict(r) for r in c.fetchall()]
    theory_agg = collections.Counter()
    for r in theories:
        tf = r['theoretical_framework']
        # 取主理论（第一个）
        main_tf = tf.split('、')[0].split(',')[0].strip()
        theory_agg[main_tf] += r['cnt']
    theory_dist = theory_agg.most_common(12)

    # ============ 4. 主题热度 ============
    c.execute("""
        SELECT rt.name, COUNT(lt.literature_id) as cnt
        FROM research_topics rt
        LEFT JOIN literature_topics lt ON rt.id = lt.topic_id
        GROUP BY rt.id ORDER BY cnt DESC LIMIT 20
    """)
    topic_heat = [(r['name'], r['cnt']) for r in c.fetchall()]

    # ============ 5. 方法×主题矩阵 ============
    # 使用 category1 作为主题维度，主方法作为方法维度
    c.execute("""
        SELECT category1, research_method, COUNT(*) as cnt
        FROM literature
        WHERE research_method!='' AND research_method!='待补' AND category1!=''
        GROUP BY category1, research_method
    """)
    rows = [dict(r) for r in c.fetchall()]
    # 归类主方法
    for r in rows:
        r['mm'] = main_method(r['research_method'])

    # 分类列表（按文献数排序）
    c.execute("SELECT category1, COUNT(*) as cnt FROM literature WHERE category1!='' GROUP BY category1 ORDER BY cnt DESC")
    cats = [(r['category1'], r['cnt']) for r in c.fetchall()]

    # 主要方法列表（前10）
    top_methods = [m for m, _ in method_dist[:10]]
    top_methods += [m for m, _ in method_dist[10:14]] if len(method_dist) >= 11 else []
    top_methods = list(dict.fromkeys(top_methods))  # 去重保序

    # 构建矩阵
    method_topic_matrix = []
    for cat, _ in cats:
        row = {'category': cat}
        cat_total = 0
        for m in top_methods:
            v = sum(r['cnt'] for r in rows if r['category1'] == cat and r['mm'] == m)
            row[m] = v
            cat_total += v
        row['_total'] = cat_total
        method_topic_matrix.append(row)

    # ============ 6. 理论×主题矩阵 ============
    top_theories = [t for t, _ in theory_dist[:10]]
    theory_rows = []
    c.execute("""
        SELECT category1, theoretical_framework, COUNT(*) as cnt
        FROM literature
        WHERE theoretical_framework!='' AND theoretical_framework!='待补' AND category1!=''
        GROUP BY category1, theoretical_framework
    """)
    trows = [dict(r) for r in c.fetchall()]
    for r in trows:
        r['mt'] = r['theoretical_framework'].split('、')[0].split(',')[0].strip()

    theory_topic_matrix = []
    for cat, _ in cats:
        row = {'category': cat}
        for t in top_theories:
            row[t] = sum(r['cnt'] for r in trows if r['category1'] == cat and r['mt'] == t)
        theory_topic_matrix.append(row)

    # ============ 组装数据 ============
    data = {
        'total': total,
        'topic_count': topic_count,
        'method_count': method_count,
        'theory_count': theory_count,
        'method_dist': method_dist,
        'theory_dist': theory_dist,
        'topic_heat': topic_heat,
        'method_topic_matrix': method_topic_matrix,
        'theory_topic_matrix': theory_topic_matrix,
        'top_methods': top_methods,
        'top_theories': top_theories,
        'cats': cats,
        'generated_at': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'),
    }

    with open(DATA_OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print(f"数据准备完成！")
    print(f"  文献总数: {total}")
    print(f"  主题数: {topic_count}, 方法类型: {method_count}, 理论框架: {theory_count}")
    print(f"  主方法({len(top_methods)}): {top_methods}")
    print(f"  主理论({len(top_theories)}): {top_theories}")
    print(f"  分类数: {len(cats)}")
    print(f"  方法×主题矩阵: {len(method_topic_matrix)} 行")
    print(f"  理论×主题矩阵: {len(theory_topic_matrix)} 行")
    conn.close()

if __name__ == "__main__":
    main()
