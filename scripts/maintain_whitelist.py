#!/usr/bin/env python3
"""
国内体育新闻期刊白名单 · 定期维护脚本
=========================================
功能：
  1. 校验白名单 JSON 配置完整性（期刊数量、字段齐全）
  2. 核对白名单期刊与数据库 journals 表的一致性（缺失/差异）
  3. 核验白名单期刊免费渠道 URL 的可访问性（连通性检测）
  4. 生成维护报告 docs/journal_whitelist_report_YYYYMMDD.md
用法：
  python scripts/maintain_whitelist.py            # 完整维护
  python scripts/maintain_whitelist.py --urlcheck # 仅校验URL连通性
  python scripts/maintain_whitelist.py --sync     # 同步白名单到journals表
"""
import os
import sys
import json
import sqlite3
import socket
import datetime
import urllib.request
import urllib.error

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHITELIST_PATH = os.path.join(PROJECT_ROOT, 'config', 'journal_whitelist.json')
DB_PATH = os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db')
DOCS_DIR = os.path.join(PROJECT_ROOT, 'docs')


def load_whitelist():
    """加载白名单配置"""
    with open(WHITELIST_PATH, encoding='utf-8') as f:
        return json.load(f)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    return conn


def check_url(url, timeout=8):
    """检测URL连通性，返回 (可访问, 状态描述)"""
    if not url or url in ('https://ncpssd.org', 'https://www.ncpssd.org'):
        # ncpssd 需要 JS 渲染/可能有反爬，用 TCP 连接测试主机可达性
        host = url.split('/')[2] if '//' in url else ''
        try:
            socket.create_connection((host, 443), timeout=timeout)
            return True, f"TCP可达({host})"
        except Exception as e:
            return False, f"TCP不可达({host}:{e})"
    try:
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=timeout)
        return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        # 403/405 也可能是可达（有反爬），算半可用
        if e.code in (403, 405, 404):
            return e.code != 404, f"HTTP {e.code}(可能反爬/需浏览器)"
        return True, f"HTTP {e.code}"
    except Exception as e:
        return False, f"不可达({e})"


def sync_whitelist_to_db(wl):
    """同步白名单期刊到 journals 表"""
    conn = get_db()
    cur = conn.cursor()
    updated = inserted = 0
    for j in wl.get('期刊清单', []):
        name = j.get('刊名', '')
        db_name = j.get('DB名', name)  # 优先用数据库中的规范名匹配
        if not name:
            continue
        url = j.get('官网URL', j.get('免费渠道', [''])[0])
        note = "白名单免费渠道: " + "/".join(j.get('免费渠道', []))
        cur.execute("UPDATE journals SET url=?, notes=CASE WHEN notes IS NULL OR notes='' THEN ? ELSE notes||' | '||? END WHERE name=? OR name_cn=?",
                    (url, note, note, db_name, db_name))
        updated += cur.rowcount
        if cur.rowcount == 0:
            issn = j.get('ISSN', '')
            publisher = j.get('主办', '')
            iscore = 1 if 'CSSCI' in j.get('核心级别', '') or '北大核心' in j.get('核心级别', '') else 0
            cur.execute("INSERT OR IGNORE INTO journals(name,name_cn,issn,publisher,country,language,impact_factor,category,is_core,is_open_access,url,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (db_name, db_name, issn, publisher, 'CN', 'zh', None, '体育/新闻传播', iscore, 0, url, note))
            inserted += cur.rowcount
    conn.commit()
    conn.close()
    return updated, inserted


def main():
    today = datetime.date.today().isoformat()
    args = sys.argv[1:]
    do_urlcheck = '--urlcheck' in args
    do_sync = '--sync' in args

    wl = load_whitelist()
    journals = wl.get('期刊清单', [])
    print(f"=== 白名单期刊维护报告 · {today} ===")
    print(f"白名单版本: {wl.get('版本','')}")
    print(f"期刊总数: {len(journals)} 本")

    # 1. 白名单配置完整性
    missing_field = []
    for j in journals:
        for f in ['刊名', 'ISSN', '免费渠道']:
            if not j.get(f):
                missing_field.append(f"{j.get('刊名','?')}缺{f}")
    print(f"\n[1] 配置完整性: {'✅ 全部字段齐全' if not missing_field else '⚠️ ' + '; '.join(missing_field)}")

    # 2. 与数据库一致性
    conn = get_db()
    db_names = set(r[0] for r in conn.execute("SELECT name FROM journals"))
    wl_names = set(j.get('DB名', j['刊名']) for j in journals)
    missing_in_db = wl_names - db_names
    print(f"[2] 与数据库一致性: journals表{len(db_names)}本, 白名单{len(wl_names)}本")
    if missing_in_db:
        print(f"    ⚠️ 白名单有但DB缺: {missing_in_db}")
    else:
        print("    ✅ 白名单期刊全部在数据库中")

    # 3. URL 连通性
    if do_urlcheck:
        print("\n[3] 渠道URL连通性核验:")
        url_ok = url_fail = url_none = 0
        for j in journals:
            url = j.get('官网URL') or j.get('url', '')
            # 只检测真正的 http(s) URL；渠道名(如 NCPSSD/编辑部官网)不做网络检测
            if not url or not url.startswith('http'):
                url_none += 1
                continue
            ok, desc = check_url(url)
            if ok:
                url_ok += 1
            else:
                url_fail += 1
                print(f"    ⚠️ {j['刊名']}: {url} → {desc}")
        print(f"    可访问 {url_ok} 个, 异常 {url_fail} 个, 无官网URL(靠渠道采集) {url_none} 个")

    # 4. 同步到数据库
    if do_sync:
        u, i = sync_whitelist_to_db(wl)
        print(f"\n[4] 同步白名单到journals表: 更新{u}, 新增{i}")

    # 生成报告文件
    os.makedirs(DOCS_DIR, exist_ok=True)
    report = os.path.join(DOCS_DIR, f'journal_whitelist_report_{today}.md')
    lines = [f"# 白名单期刊维护报告 · {today}",
             "", f"- 白名单版本: {wl.get('版本','')}",
             f"- 期刊总数: {len(journals)} 本",
             f"- 数据库 journals 表: {len(db_names)} 本",
             "", "## 白名单期刊清单", "",
             "| 刊名 | ISSN | 分类 | 核心级别 | 免费渠道 | 官网URL |",
             "|---|---|---|---|---|---|"]
    for j in journals:
        lines.append(f"| {j.get('刊名','')} | {j.get('ISSN','')} | {j.get('分类','')} | {j.get('核心级别','')} | {'/'.join(j.get('免费渠道',[]))} | {j.get('官网URL','') or '-'} |")
    lines += ["", "## 维护建议", "", wl.get('维护更新机制',''), "", f"生成时间: {today}"]
    with open(report, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"\n✅ 维护报告已生成: {report}")
    conn.close()


if __name__ == '__main__':
    main()
