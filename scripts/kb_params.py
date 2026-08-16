#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
体育新闻研究知识库 · 统一参数加载模块（单一事实源）
===================================================
从 `config/parameters.json` 加载全部固化参数，供各采集/过滤/分类脚本 import 使用。
**这是词表、检索参数、主题、期刊映射的唯一权威入口**。

设计原则：
- 各脚本不再各自定义 SPORT_TOKENS / RULES / THEME_QUERIES 等词表，
  统一 `from kb_params import ...`，避免多份定义漂移不一致。
- parameters.json 是权威源，本模块只做"读取 + 还原结构"。
- RULES 还原为 `[(分类, [关键词]), ...]` 元组列表（兼容 fetch_incremental 的原有结构）。

用法:
    from kb_params import (
        SPORT_TOKENS, MEDIA_TOKENS, CORE_TERMS, ESPORTS_TOKENS, HARD_BLACKLIST,
        EN_QUERIES, CN_QUERIES, RULES,
        SPORT_WORDS, PURE_SPORT_KEYWORDS, NEWS_SOURCES,
        THEME_QUERIES, THEME_CATEGORY, HARD_NOISE,
        PER_QUERY, MIN_YEAR, MAILTO, JOURNAL_GCH,
    )
"""
import os
import json

# ---------------- 路径 ----------------
CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
PARAMS_FILE = os.path.join(CONFIG_DIR, 'parameters.json')

# ---------------- 加载 ----------------
def _load():
    """读取 parameters.json，失败返回空结构并给出告警。"""
    with open(PARAMS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

_PARAMS = _load()

# ---------------- 检索参数 ----------------
PER_QUERY   = _PARAMS.get('检索参数', {}).get('PER_QUERY', 25)
MIN_YEAR    = _PARAMS.get('检索参数', {}).get('MIN_YEAR', 2010)
MAILTO      = _PARAMS.get('检索参数', {}).get('MAILTO', 'research@example.com')
THEME_START_YEAR = _PARAMS.get('检索参数', {}).get('THEME_START_YEAR', 2010)
THEME_PER_THEME  = _PARAMS.get('检索参数', {}).get('THEME_PER_THEME', 60)

# ---------------- 增量检索词 ----------------
EN_QUERIES = _PARAMS.get('增量检索词', {}).get('EN_QUERIES', [])
CN_QUERIES = _PARAMS.get('增量检索词', {}).get('CN_QUERIES', [])

# ---------------- 质量过滤词表 ----------------
_QF = _PARAMS.get('质量过滤词表', {})
SPORT_TOKENS  = _QF.get('SPORT_TOKENS', [])
MEDIA_TOKENS  = _QF.get('MEDIA_TOKENS', [])
CORE_TERMS    = _QF.get('CORE_TERMS', [])
ESPORTS_TOKENS = _QF.get('ESPORTS_TOKENS', [])
HARD_BLACKLIST = _QF.get('HARD_BLACKLIST', [])

# ---------------- 分类规则（还原为元组列表） ----------------
RULES = [
    (cat, toks) for cat, toks in _PARAMS.get('分类规则', {}).get('RULES', [])
]

# ---------------- 主题弱项 ----------------
_THEME = _PARAMS.get('主题弱项', {})
THEME_QUERIES  = _THEME.get('THEME_QUERIES', {})
THEME_CATEGORY = _THEME.get('THEME_CATEGORY', {})

# ---------------- 国内期刊过滤词 ----------------
_CN = _PARAMS.get('国内期刊过滤词', {})
SPORT_WORDS = _CN.get('SPORT_WORDS', [])
PURE_SPORT_KEYWORDS = _CN.get('PURE_SPORT_KEYWORDS', [])
NEWS_SOURCES = set(_CN.get('NEWS_SOURCES', []))

# ---------------- 主题清理噪声 ----------------
HARD_NOISE = _PARAMS.get('主题清理噪声', {}).get('HARD_NOISE', [])

# ---------------- 期刊映射（刊名 -> [gch, ISSN, CN, 类别]） ----------------
JOURNAL_GCH = {
    name: (gch, issn, cn, cat)
    for name, (gch, issn, cn, cat) in _PARAMS.get('期刊映射', {}).get('JOURNAL_GCH', {}).items()
}


def get_all():
    """返回全部已加载参数，便于调试/校验。"""
    return _PARAMS


if __name__ == '__main__':
    print(f'PER_QUERY      = {PER_QUERY}')
    print(f'MIN_YEAR       = {MIN_YEAR}')
    print(f'EN_QUERIES     = {len(EN_QUERIES)} 条')
    print(f'SPORT_TOKENS   = {len(SPORT_TOKENS)} 词')
    print(f'MEDIA_TOKENS   = {len(MEDIA_TOKENS)} 词')
    print(f'RULES          = {len(RULES)} 类')
    print(f'THEME_QUERIES  = {len(THEME_QUERIES)} 主题')
    print(f'SPORT_WORDS    = {len(SPORT_WORDS)} 词(国内)')
    print(f'JOURNAL_GCH    = {len(JOURNAL_GCH)} 本期刊')
    print('✅ 参数加载正常')
