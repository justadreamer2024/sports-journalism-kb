#!/usr/bin/env python3
"""
体育新闻研究知识库 - 智能大脑（研究讨论引擎）
基于知识库的检索增强式研究讨论助手。

功能:
  - 主题检索：输入研究话题，检索知识库相关文献
  - 研究地图：分析某主题的学者网络、方法、理论
  - 讨论记录：保存讨论内容，供后续形成论文
  - 洞察生成：从文献中提炼研究趋势和空白
"""
import os
import sys
import json
from datetime import datetime
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_manager import get_db

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISCUSSION_DIR = os.path.join(PROJECT_ROOT, 'output', 'discussions')

class ResearchBrain:
    """研究智能大脑"""

    def __init__(self):
        os.makedirs(DISCUSSION_DIR, exist_ok=True)
        self.conn = get_db()
        self.conn.row_factory = __import__('sqlite3').Row

    def search_topic(self, query, region='', limit=15):
        """检索知识库相关文献"""
        conditions = ["(title LIKE ? OR abstract LIKE ? OR keywords LIKE ? OR title_cn LIKE ? OR abstract_cn LIKE ? OR keywords_cn LIKE ?)"]
        params = [f"%{query}%"] * 6
        if region:
            conditions.append("region=?")
            params.append(region)
        sql = f"SELECT * FROM literature WHERE {' AND '.join(conditions)} ORDER BY year DESC, citation_count DESC LIMIT ?"
        params.append(limit)
        return self.conn.execute(sql, params).fetchall()

    def get_topic_map(self, topic):
        """生成研究主题地图"""
        results = self.search_topic(topic, limit=30)
        if not results:
            return None
        
        # 学者分析
        authors = Counter()
        for r in results:
            for a in (r['author'] or '').split(','):
                a = a.strip()
                if a and a not in ('Unknown', '相关学者'):
                    authors[a] += 1
        
        # 方法分析
        methods = Counter()
        for r in results:
            if r['research_method']:
                methods[r['research_method']] += 1
        
        # 理论分析
        theories = Counter()
        for r in results:
            if r['theoretical_framework']:
                theories[r['theoretical_framework']] += 1
        
        # 年代分布
        years = Counter()
        for r in results:
            if r['year']:
                decades = (r['year'] // 10) * 10
                years[f"{decades}s"] += 1
        
        return {
            'topic': topic,
            'total': len(results),
            'top_authors': authors.most_common(8),
            'top_methods': methods.most_common(5),
            'top_theories': theories.most_common(5),
            'year_dist': dict(sorted(years.items())),
            'results': [dict(r) for r in results]
        }

    def analyze_research_gap(self, topic):
        """分析研究空白"""
        results = self.search_topic(topic, limit=30)
        if not results:
            return "未找到相关研究"
        
        # 最新文献年份
        latest_year = max((r['year'] or 0) for r in results)
        
        # 检查国内/国际覆盖
        regions = Counter(r['region'] for r in results)
        langs = Counter(r['language'] for r in results)
        
        gap_analysis = {
            '最新文献年份': latest_year,
            '区域分布': dict(regions),
            '语种分布': dict(langs),
            '研究相对薄弱领域': []
        }
        
        # 分析薄弱领域
        if 'zh' not in langs:
            gap_analysis['研究相对薄弱领域'].append('中文文献相对稀缺')
        if latest_year < 2023:
            gap_analysis['研究相对薄弱领域'].append(f'最新研究停留在{latest_year}年，近两年产出少')
        if regions.get('international', 0) > regions.get('domestic', 0) * 2:
            gap_analysis['研究相对薄弱领域'].append('国内研究相对不足')
        
        return gap_analysis

    def save_discussion(self, topic, content, insights=''):
        """保存讨论记录"""
        filename = f"discussion_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        filepath = os.path.join(DISCUSSION_DIR, filename)
        
        doc = f"""# 💬 研究讨论记录

> 主题：{topic}
> 时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}

## 讨论内容
{content}

## 研究洞察
{insights}

---
*由体育新闻研究知识库智能大脑生成*
"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(doc)
        
        # 记录到数据库
        self.conn.execute("""
            INSERT INTO research_trends (title, description, category, importance, language, region, notes)
            VALUES (?, ?, '讨论记录', 'normal', 'zh', 'international', ?)
        """, (f"讨论：{topic}", content[:500], insights[:500]))
        self.conn.commit()
        
        return filepath

    def generate_insights(self, topic_map):
        """生成研究洞察"""
        if not topic_map:
            return "暂无足够数据"
        
        insights = []
        insights.append(f"围绕「{topic_map['topic']}」共检索到 {topic_map['total']} 篇相关文献")
        
        if topic_map['top_authors']:
            top = topic_map['top_authors'][0]
            insights.append(f"核心学者：{top[0]}（{top[1]}篇）")
        
        years = topic_map['year_dist']
        if years:
            latest = list(years.keys())[-1]
            insights.append(f"研究热度近年{'上升' if len(years)>=2 else '起步'}，最新集中在{latest}")
        
        if topic_map['top_theories']:
            insights.append(f"常用理论：{topic_map['top_theories'][0][0]}")
        
        return "；".join(insights)


def cli():
    import argparse
    parser = argparse.ArgumentParser(description='体育新闻研究智能大脑')
    parser.add_argument('topic', help='研究主题')
    parser.add_argument('--map', action='store_true', help='生成研究地图')
    parser.add_argument('--gap', action='store_true', help='分析研究空白')
    parser.add_argument('--discuss', help='记录讨论内容')
    parser.add_argument('--region', default='', help='限定区域')
    args = parser.parse_args()
    
    brain = ResearchBrain()
    
    print(f"🧠 智能大脑分析：「{args.topic}」")
    print("=" * 50)
    
    if args.map:
        topic_map = brain.get_topic_map(args.topic)
        if topic_map:
            print(f"\n📊 研究地图")
            print(f"  相关文献: {topic_map['total']} 篇")
            if topic_map['top_authors']:
                print(f"  核心学者: {', '.join(f'{a}({c})' for a,c in topic_map['top_authors'][:5])}")
            if topic_map['top_theories']:
                print(f"  常用理论: {', '.join(t for t,_ in topic_map['top_theories'][:3])}")
            if topic_map['year_dist']:
                print(f"  年代分布: {topic_map['year_dist']}")
    
    if args.gap:
        gap = brain.analyze_research_gap(args.topic)
        print(f"\n🔍 研究空白分析")
        if isinstance(gap, dict):
            for k, v in gap.items():
                print(f"  {k}: {v}")
    
    if args.discuss:
        filepath = brain.save_discussion(args.topic, args.discuss)
        print(f"\n💬 讨论已保存: {filepath}")
    
    if not args.map and not args.gap and not args.discuss:
        # 默认模式：展示相关文献
        results = brain.search_topic(args.topic, region=args.region)
        print(f"\n📚 相关文献 ({len(results)} 篇):")
        for r in results[:10]:
            print(f"  [{r['year']}] {r['title'][:50]} - {r['author'][:20]} ({r['region']})")


if __name__ == '__main__':
    cli()
