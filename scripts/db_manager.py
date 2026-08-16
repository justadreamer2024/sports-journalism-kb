#!/usr/bin/env python3
"""体育新闻研究知识库 - 数据库初始化与管理脚本"""

import sqlite3
import os
import sys
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'database', 'knowledge_base.db')
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'database', 'schema.sql')

def init_database():
    """初始化数据库"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema_sql = f.read()
    
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    print(f"✅ 数据库初始化完成: {DB_PATH}")

def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def add_literature(conn, data: dict) -> int:
    """添加文献"""
    # 移除空的doi避免UNIQUE约束冲突（空字符串不是有效的唯一标识）
    clean_data = {k: v for k, v in data.items() if v is not None and v != ''}
    
    # 如果doi是空的，不插入该字段
    fields = [k for k in clean_data.keys()]
    placeholders = [f":{f}" for f in fields]
    
    try:
        sql = f"INSERT INTO literature ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
        cur = conn.execute(sql, clean_data)
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        # doi冲突，跳过
        return None

def add_scholar(conn, data: dict) -> int:
    """添加学者"""
    sql = """INSERT OR IGNORE INTO scholars (name, name_native, institution, country, research_fields, 
             email, google_scholar_id, orcid, researchgate_url, publication_count, h_index, total_citations, bio)
             VALUES (:name, :name_native, :institution, :country, :research_fields, 
             :email, :google_scholar_id, :orcid, :researchgate_url, :publication_count, :h_index, :total_citations, :bio)"""
    cur = conn.execute(sql, data)
    conn.commit()
    return cur.lastrowid

def link_literature_scholar(conn, lit_id: int, scholar_id: int, role: str = 'author'):
    """关联文献与学者"""
    conn.execute(
        "INSERT OR IGNORE INTO literature_scholars (literature_id, scholar_id, role) VALUES (?, ?, ?)",
        (lit_id, scholar_id, role)
    )
    conn.commit()

def add_trend(conn, data: dict) -> int:
    """添加研究动态"""
    cur = conn.execute(
        """INSERT INTO research_trends (title, description, source, source_url, category, importance, 
           language, region, related_literature, related_topics, published_date, notes)
           VALUES (:title, :description, :source, :source_url, :category, :importance,
           :language, :region, :related_literature, :related_topics, :published_date, :notes)""",
        data
    )
    conn.commit()
    return cur.lastrowid

def search_literature(conn, query: str, region: str = None, limit: int = 50):
    """全文搜索文献"""
    if region:
        sql = """SELECT l.* FROM literature l 
                 JOIN literature_fts f ON l.id = f.rowid
                 WHERE literature_fts MATCH ? AND l.region = ?
                 ORDER BY rank LIMIT ?"""
        return conn.execute(sql, (query, region, limit)).fetchall()
    else:
        sql = """SELECT l.* FROM literature l 
                 JOIN literature_fts f ON l.id = f.rowid
                 WHERE literature_fts MATCH ?
                 ORDER BY rank LIMIT ?"""
        return conn.execute(sql, (query, limit)).fetchall()

def get_stats(conn):
    """获取知识库统计"""
    stats = {}
    stats['total_literature'] = conn.execute("SELECT COUNT(*) FROM literature").fetchone()[0]
    stats['domestic'] = conn.execute("SELECT COUNT(*) FROM literature WHERE region='domestic'").fetchone()[0]
    stats['international'] = conn.execute("SELECT COUNT(*) FROM literature WHERE region='international'").fetchone()[0]
    stats['total_scholars'] = conn.execute("SELECT COUNT(*) FROM scholars").fetchone()[0]
    stats['total_topics'] = conn.execute("SELECT COUNT(*) FROM research_topics").fetchone()[0]
    stats['total_trends'] = conn.execute("SELECT COUNT(*) FROM research_trends").fetchone()[0]
    stats['by_language'] = {row[0]: row[1] for row in conn.execute(
        "SELECT language, COUNT(*) FROM literature GROUP BY language").fetchall()}
    stats['by_year'] = {str(row[0]): row[1] for row in conn.execute(
        "SELECT year, COUNT(*) FROM literature WHERE year IS NOT NULL GROUP BY year ORDER BY year").fetchall()}
    return stats

if __name__ == '__main__':
    init_database()
