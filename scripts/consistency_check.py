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
    os.path.join(PROJECT_ROOT, 'scripts', 'cloud_runner.py'),
    os.path.join(PROJECT_ROOT, 'scripts', 'local_scheduler.py'),
    os.path.join(PROJECT_ROOT, 'scripts', 'health_check.py'),
    os.path.join(PROJECT_ROOT, 'scripts', 'kb_params.py'),
    os.path.join(PROJECT_ROOT, 'scripts', 'update_github_pages.py'),
    os.path.join(PROJECT_ROOT, 'scripts', 'sync_github_pages.sh'),
    os.path.join(PROJECT_ROOT, 'scripts', 'build_static_site.py'),
    os.path.join(PROJECT_ROOT, 'scripts', 'fetch_tykx_official.py'),
    os.path.join(PROJECT_ROOT, 'scripts', 'fetch_tykx_scnu.py'),
    os.path.join(PROJECT_ROOT, 'config', 'parameters.json'),
    os.path.join(PROJECT_ROOT, 'docs', 'DEPLOY_PARAMS_FROZEN.md'),
    os.path.join(PROJECT_ROOT, 'docs', 'PARAMS_FROZEN.md'),
    os.path.join(PROJECT_ROOT, 'docs', 'COLLECTION_SKILLS_FROZEN.md'),
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
    'daemon_scheduler.py',       # 2026-08-17 归档：被 cloud_runner.py 取代
    'push_repo.py',              # 2026-08-17 归档：一次性部署
    'setup_cloud.py',            # 2026-08-17 归档：一次性初始化
    'run_abstract_backfill_loop.py',   # 2026-08-17 归档：历史补摘要
    'run_backfill_after_batchA.py',    # 2026-08-17 归档：历史接力
    'cleanup_shell_noise.py',    # 2026-08-17 归档：一次性清理
    'apply_abstract_cn_batch56.py',    # 2026-08-17 删除：与 archive 重复
]



def check_paths():
    # 脱敏部署包识别：无真实 email/wechat 配置但有 .template.json -> 部署包（密钥由安装时填入），
    # 跳过对敏感配置的缺失告警（与 health_check.py 的 is_package 逻辑保持一致）。
    sensitive = [os.path.join(PROJECT_ROOT, 'config', 'email_config.json'),
                 os.path.join(PROJECT_ROOT, 'config', 'wechat_config.json')]
    is_package = (not os.path.exists(sensitive[0])) and os.path.exists(
        os.path.join(PROJECT_ROOT, 'config', 'email_config.template.json'))
    check_paths_list = [p for p in CORE_PATHS if not (is_package and p in sensitive)]

    missing = [p for p in check_paths_list if not os.path.exists(p)]
    if missing:
        print("❌ 缺失的权威路径:")
        for p in missing:
            print(f"   {p}")
        return False
    suffix = '（脱敏部署包，跳过敏感配置检查）' if is_package else ''
    print(f"✅ 核心权威路径全部存在（{len(check_paths_list)} 项）{suffix}")
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
    """检查旧 github_actions/ 目录已归档（不再用 auto_fetch/rebuild_site 旧脚本，统一走 scripts/fetch_incremental.py）。"""
    legacy = os.path.join(PROJECT_ROOT, 'github_actions')
    if os.path.exists(legacy):
        print("❌ 旧目录 github_actions/ 仍存在于根目录（应归档到 scripts/archive/github_actions_legacy/）")
        return False
    print("✅ 旧 github_actions/ 目录已归档（现行云端统一走 scripts/cloud_runner.py）")
    return True


def check_workflow():
    """检查仓库根 cloud_scheduler.yml（现行唯一权威调度，2026-08-17 起替代废弃的 weekly_update.yml）。"""
    gh_dir = os.path.join(PROJECT_ROOT, '.github')
    # 部署包/便携运行环境不含 .github（云端专属），跳过云端工作流检查
    if not os.path.exists(gh_dir):
        print("ℹ️ 便携运行环境（无 .github/），跳过云端工作流检查（主库权威校验见 .github/workflows/cloud_scheduler.yml）")
        return True
    wf = os.path.join(gh_dir, 'workflows', 'cloud_scheduler.yml')
    if not os.path.exists(wf):
        print("❌ 缺失 cloud_scheduler.yml（仓库根，权威调度）")
        return False
    with open(wf, encoding='utf-8') as f:
        content = f.read()
    if 'cloud_runner.py' not in content:
        print("❌ cloud_scheduler.yml 未调用 cloud_runner.py（应为云端调度入口）")
        return False
    if 'workflow_dispatch' not in content:
        print("⚠️ cloud_scheduler.yml 未配置 workflow_dispatch 手动触发")
    print("✅ cloud_scheduler.yml 正确（调用 cloud_runner.py，仓库根权威）")
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
