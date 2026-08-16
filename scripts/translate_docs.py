#!/usr/bin/env python3
"""
体育新闻研究知识库 - 文献翻译产出脚本
从数据库提取外文文献的中文摘要，生成规范的翻译文档。

用法:
  python3.11 scripts/translate_docs.py            # 生成全部语种翻译文档
  python3.11 scripts/translate_docs.py --lang en  # 只生成英文翻译
  python3.11 scripts/translate_docs.py --latest 5 # 只处理最新N篇
"""
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_manager import get_db

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSLATION_DIR = os.path.join(PROJECT_ROOT, 'output', 'translations')

# 语种名称映射
LANG_NAMES = {
    'en': ('英文', 'English'),
    'de': ('德文', 'Deutsch'),
    'fr': ('法文', 'Français'),
    'ja': ('日文', '日本語'),
    'es': ('西班牙文', 'Español'),
    'ko': ('韩文', '한국어'),
    'ru': ('俄文', 'Русский'),
    'ar': ('阿拉伯文', 'العربية'),
    'zh': ('中文', '中文'),
}

def generate_translation_docs(lang_filter=None, latest=None):
    """生成翻译文档"""
    os.makedirs(TRANSLATION_DIR, exist_ok=True)
    
    conn = get_db()
    conn.row_factory = __import__('sqlite3').Row
    
    # 查询外文且有中文摘要的文献
    query = """SELECT * FROM literature 
               WHERE language != 'zh' 
                 AND abstract_cn IS NOT NULL AND abstract_cn != ''"""
    params = []
    
    if lang_filter:
        query += " AND language = ?"
        params.append(lang_filter)
    
    query += " ORDER BY year DESC, id DESC"
    
    if latest:
        query += " LIMIT ?"
        params.append(latest)
    
    rows = conn.execute(query, params).fetchall()
    
    if not rows:
        print("⚠️ 没有找到需要翻译的文献")
        return []
    
    # 按语种分组
    by_lang = {}
    for r in rows:
        lang = r['language']
        by_lang.setdefault(lang, []).append(dict(r))
    
    generated = []
    for lang, items in by_lang.items():
        lang_zh, lang_en = LANG_NAMES.get(lang, (lang, lang))
        
        # 生成单语种翻译文档
        doc = f"""# {lang_zh}体育新闻研究文献翻译集
# Translated Abstracts: {lang_en} Sports Journalism Research

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}
> 语种：{lang_zh} | 文献数：{len(items)}

---
"""
        for i, r in enumerate(items, 1):
            doc += f"""
## {i}. {r['title']}

- **作者**: {r['author']}
- **年份**: {r['year'] or '未知'}
- **来源**: {r['source_name'] or '未知'}
- **分类**: {r['category1'] or '未分类'}

### 原文摘要
{r['abstract'] or '（无原文摘要）'}

### 中文翻译
{r['abstract_cn'] or '（无中文翻译）'}

### 关键词
原文：{r['keywords'] or '无'}  
中文：{r['keywords_cn'] or '无'}

---
"""
        
        filename = f"translated_{lang}_{datetime.now().strftime('%Y%m%d')}.md"
        filepath = os.path.join(TRANSLATION_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(doc)
        
        generated.append({
            'lang': lang,
            'count': len(items),
            'file': filepath
        })
        print(f"✅ 已生成{lang_zh}翻译文档: {filepath} ({len(items)}篇)")
    
    conn.close()
    return generated

def generate_translation_summary():
    """生成翻译总览文档"""
    generated = generate_translation_docs()
    
    if not generated:
        return
    
    summary = f"""# 📖 体育新闻研究多语种文献翻译总览

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}

## 翻译统计

| 语种 | 已翻译文献数 |
|------|------------|
"""
    total = 0
    for g in generated:
        summary += f"| {LANG_NAMES.get(g['lang'],(g['lang'],g['lang']))[0]} | {g['count']} 篇 |\n"
        total += g['count']
    
    summary += f"| **合计** | **{total} 篇** |\n\n"
    summary += "## 翻译文档索引\n\n"
    for g in generated:
        lang_zh = LANG_NAMES.get(g['lang'],(g['lang'],g['lang']))[0]
        summary += f"- **{lang_zh}**：`output/translations/{os.path.basename(g['file'])}`\n"
    
    summary += f"\n---\n*由体育新闻研究知识库自动生成*\n"
    
    filepath = os.path.join(TRANSLATION_DIR, 'README.md')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(summary)
    print(f"✅ 翻译总览已生成: {filepath}")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--lang', help='指定语种')
    parser.add_argument('--latest', type=int, help='只处理最新N篇')
    args = parser.parse_args()
    
    if args.lang:
        generate_translation_docs(lang_filter=args.lang, latest=args.latest)
    else:
        generate_translation_summary()
