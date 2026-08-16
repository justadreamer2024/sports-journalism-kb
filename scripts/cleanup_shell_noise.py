#!/usr/bin/env python3.11
"""清理空壳噪声文献（标题=期刊名/栏目的非论文条目）。

目标：12 篇
  - 1510~1520 : 'Society News'（来自运动医学期刊 Sports Health，全空）
  - 1796      : 标题即期刊名《The British Journal of Sports Medicine》（内容是期刊简介）
这些不是体育新闻研究成果，属用户明确剔除的"运动医学类"空壳。
"""
import sqlite3, json, datetime, os

DB = 'database/knowledge_base.db'
TARGETS = list(range(1510, 1521)) + [1796]

def main():
    assert os.path.exists(DB), DB
    c = sqlite3.connect(DB)
    cur = c.cursor()

    def cnt(sql):
        cur.execute(sql); return cur.fetchone()[0]

    before = dict(
        total=cnt("SELECT COUNT(*) FROM literature"),
        dom=cnt("SELECT COUNT(*) FROM literature WHERE region='domestic'"),
        intl=cnt("SELECT COUNT(*) FROM literature WHERE region='international'"),
        fts=cnt("SELECT COUNT(*) FROM literature_fts"),
    )

    # 1) 清理外联表（动态探测 literature_id 列）
    assoc = {}
    for t in ['literature_topics', 'literature_journals', 'literature_scholars']:
        try:
            cur.execute(f"PRAGMA table_info({t})")
            cols = [r[1] for r in cur.fetchall()]
            lid = 'literature_id' if 'literature_id' in cols else ('paper_id' if 'paper_id' in cols else None)
            if lid:
                cur.execute(f"DELETE FROM {t} WHERE {lid} IN ({','.join(map(str,TARGETS))})")
                assoc[t] = cur.rowcount
        except Exception as e:
            assoc[t] = f'ERR {e}'

    # 2) 删除主表
    qs = ','.join(map(str, TARGETS))
    cur.execute(f"DELETE FROM literature WHERE id IN ({qs})")
    deleted = cur.rowcount

    # 3) 重建 FTS。本库 FTS 为外部内容表(content='literature')且无同步触发器，
    #    是一次性 INSERT 构建的快照(与 literature 1:1)。'rebuild'/'delete' 特殊命令
    #    在本环境 sqlite 下报 'incomplete input'，故采用 DROP+重建+全量 INSERT，
    #    与原始状态等价（不引入回归）。
    cur.execute("DROP TABLE IF EXISTS literature_fts")
    cur.execute("""CREATE VIRTUAL TABLE literature_fts USING fts5(
        title, author, abstract, keywords, content='literature', content_rowid='id')""")
    cur.execute("INSERT INTO literature_fts(rowid, title, author, abstract, keywords) "
                "SELECT id, title, author, abstract, keywords FROM literature")

    c.commit()

    after = dict(
        total=cnt("SELECT COUNT(*) FROM literature"),
        dom=cnt("SELECT COUNT(*) FROM literature WHERE region='domestic'"),
        intl=cnt("SELECT COUNT(*) FROM literature WHERE region='international'"),
        fts=cnt("SELECT COUNT(*) FROM literature_fts"),
    )

    report = {
        'run_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'targets': TARGETS,
        'deleted_main': deleted,
        'assoc_cleanup': assoc,
        'before': before,
        'after': after,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    c.close()

if __name__ == '__main__':
    main()
