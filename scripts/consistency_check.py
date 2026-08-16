#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
体育新闻研究知识库 - 一致性/防遗忘校验脚本
=================================================
每次操作前运行，检查项目关键路径、脚本引用、部署参数是否一致，
防止"做过但忘了"或"改了一处忘了另一处"。

用法：
    python3 scripts/consistency_check.py          # 完整校验
    python3 scripts/consistency_check.py --quick  # 快速校验（仅核心路径）

退出码：0=全部通过；1=存在问题（打印告警）
"""
import os
import sys
import sqlite3
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db')
STATIC = os.path.join(PROJECT_ROOT, 'web', 'static_site')

# 核心权威来源（必须存在）
CORE_PATHS = [
    DB,
    os.path.join(DB),  # database/knowledge_base.db
    os.path.join(STATIC, 'data.json'),
    os.path.join(STATIC, 'index.html'),
    os.path.join(PROJECT_ROOT, 'scripts', 'db_manager.py'),
    os.path.join(PROJECT_ROOT, 'scripts', 'scheduler.py'),
    os.path.join(PROJECT_ROOT, 'scripts', 'daemon_scheduler.py'),
    os.path.join(PROJECT_ROOT, 'scripts', 'update_github_pages.py'),
    os.path.join(PROJECT_ROOT, 'scripts', 'sync_github_pages.sh'),
    os.path.join(PROJECT_ROOT, 'scripts', 'build_static_site.py'),
    os.path.join(PROJECT_ROOT, 'docs', 'DEPLOY_PARAMS_FROZEN.md'),
    os.path.join(PROJECT_ROOT, 'docs', 'PROJECT_MASTER_INDEX.md'),
    os.path.join(PROJECT_ROOT, 'config', 'email_config.json'),
    os.path.join(PROJECT_ROOT, 'config', 'wechat_config.json'),
]

# 已废弃/归档脚本（不应在 scripts/ 根目录出现）
ARCHIVED_SCRIPTS = [
    'deploy_github.sh',
    'apply_abstract_cn.py',
    'import_literature.py',
    'setup_cron.sh',
]

# GHA 脚本关键配置（应指向根目录）
GHA_SCRIPTS = {
    'auto_fetch.py': 'SITE_DIR = REPO_ROOT',
    'rebuild_site.py': 'SITE_DIR = REPO_ROOT',
}


def check_paths():
    missing = [p for p in CORE_PATHS if not os.path.exists(p)]
    if missing:
        print("❌ 缺失的权威路径:")
        for p in missing:
            print(f"   {p}")
        return False
    print(f"✅ 核心权威路径全部存在（{len(CORE_PATHS)} 项）")
    return True


def check_db():
    try:
        conn = sqlite3.connect(DB)
        total = conn.execute("SELECT COUNT(*) FROM literature").fetchone()[0]
        domestic = conn.execute("SELECT COUNT(*) FROM literature WHERE region='domestic'").fetchone()[0]
        international = conn.execute("SELECT COUNT(*) FROM literature WHERE region='international'").fetchone()[0]
        abs_total = conn.execute("SELECT COUNT(*) FROM literature WHERE abstract IS NOT NULL AND abstract!=''").fetchone()[0]
        abs_cn = conn.execute("SELECT COUNT(*) FROM literature WHERE abstract_cn IS NOT NULL AND abstract_cn!=''").fetchone()[0]
        conn.close()
        coverage = f"{abs_cn/abs_total*100:.1f}%" if abs_total else "N/A"
        print(f"✅ 数据库: 总 {total}（国内{domestic}/国际{international}）| 翻译覆盖 {coverage}（{abs_cn}/{abs_total}）")
        # 动态读取主文档声称的文献数作为唯一事实源，避免写死导致下次变动又误报
        claimed = None
        for doc in ("README.md", "docs/PROJECT_MASTER_INDEX.md"):
            p = os.path.join(PROJECT_ROOT, doc)
            if os.path.exists(p):
                m = re.search(r"总文献数\*\*\s*\|\s*(\d+)", open(p, encoding="utf-8").read())
                if m:
                    claimed = int(m.group(1))
                    break
        if claimed is not None and total != claimed:
            print(f"   [WARN] 总文献数 {total} != 主文档声称 {claimed}，文档与数据库不一致")
            return False
        return True
    except Exception as e:
        print(f"❌ 数据库检查失败: {e}")
        return False


def check_archived():
    problems = []
    for name in ARCHIVED_SCRIPTS:
        if os.path.exists(os.path.join(PROJECT_ROOT, 'scripts', name)):
            problems.append(name)
    if problems:
        print("❌ 已废弃脚本仍存在于 scripts/ 根目录（应归档到 archive/）:")
        for n in problems:
            print(f"   scripts/{n}")
        return False
    print("✅ 无废弃脚本残留")
    return True


def check_gha():
    problems = []
    for fname, expected in GHA_SCRIPTS.items():
        path = os.path.join(PROJECT_ROOT, 'github_actions', 'scripts', fname)
        if not os.path.exists(path):
            problems.append(f"缺失 github_actions/scripts/{fname}")
            continue
        with open(path, encoding='utf-8') as f:
            content = f.read()
        if expected not in content:
            problems.append(f"{fname} 的 SITE_DIR 未指向 REPO_ROOT（可能改回 site/ 了）")
    if problems:
        print("❌ GHA 脚本问题:")
        for p in problems:
            print(f"   {p}")
        return False
    print("✅ GHA 脚本 SITE_DIR 均指向根目录")
    return True


def check_workflow():
    wf = os.path.join(PROJECT_ROOT, 'github_actions', '.github', 'workflows', 'weekly_update.yml')
    if not os.path.exists(wf):
        print("❌ 缺失 weekly_update.yml")
        return False
    with open(wf, encoding='utf-8') as f:
        content = f.read()
    if "git add site/" in content:
        print("❌ weekly_update.yml 仍在 git add site/（应为 data.json index.html）")
        return False
    if "git add data.json index.html" not in content:
        print("⚠️ weekly_update.yml 未显式 add data.json index.html")
    print("✅ weekly_update.yml 路径正确")
    return True


def main():
    print("=" * 56)
    print(" 🏅 体育新闻知识库 · 一致性/防遗忘校验")
    print("=" * 56)
    quick = '--quick' in sys.argv

    results = []
    results.append(check_paths())
    if not quick:
        results.append(check_db())
    results.append(check_archived())
    if not quick:
        results.append(check_gha())
        results.append(check_workflow())

    passed = all(results)
    print()
    print("=" * 56)
    if passed:
        print(" ✅ 校验全部通过，项目状态一致")
    else:
        print(" ⚠️ 发现问题，请根据上方告警修复")
    print("=" * 56)
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
