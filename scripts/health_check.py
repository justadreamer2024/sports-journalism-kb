#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
体育新闻研究知识库 · 三级自检脚本（健康检查）
===============================================
维护系统完整性 / 一致性 / 可用性的常态化自检机制。
设计为三档频率（daily / weekly / monthly），供云端调度并入现有任务调用。

档位与深度：
  daily   -> 轻量健康检查：关键路径/脚本存在、DB可打开且完整性ok、FTS同步、
             废弃脚本残留。**仅异常时告警**（正常静默），不打扰。
  weekly  -> 完整一致性 + 数据质量摘要：调用 consistency_check 全量校验，
             输出健康摘要（总量/翻译进度/缺字段/异常清单）。正常发周度健康摘要。
  monthly -> 深度治理检查：参数词表漂移、文档声称值与实际比对、调度配置完整性、
             归档残留。生成月度健康报告。

自动修复原则（owner 已确认）：
  - 可自动修复且安全项（FTS索引重建、废弃脚本标注、文档统计修正提示）-> 自动修复并记录。
  - 不可自动修复项（DB损坏、密钥失效、凭证缺失）-> 发告警，请 owner 人工处理。
  - 绝不自动改动数据内容/删除文献/改凭证。

用法：
  python3 scripts/health_check.py daily    # 每日轻量
  python3 scripts/health_check.py weekly   # 每周完整
  python3 scripts/health_check.py monthly  # 每月深度
  python3 scripts/health_check.py --notify-only  # 只打印不发送（调试）

通知：复用 scheduler.send_email（邮件）+ wechat_pusher（微信），异常时发告警。
退出码：0=正常；2=有异常但已自动修复；3=有异常需人工处理。
"""
import os
import sys
import re
import json
import sqlite3
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'scripts'))
DB = os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db')
HEALTH_LOG = os.path.join(PROJECT_ROOT, 'output', 'health')

# ---------------- 结果收集 ----------------
class Result:
    def __init__(self):
        self.passed = []    # (项, 说明)
        self.warned = []    # (项, 说明, 是否自动修复)
        self.failed = []    # (项, 说明) 需人工处理

R = Result()

def ok(name, note=''):
    R.passed.append((name, note))

def warn(name, note, fixed=False):
    R.warned.append((name, note, fixed))

def fail(name, note):
    R.failed.append((name, note))


# ---------------- 通知 ----------------
def notify(subject, body, notify_only=False):
    if notify_only:
        print(f"\n[通知预览] {subject}\n{body}\n")
        return
    # 邮件
    try:
        from scheduler import send_email
        send_email(subject, body, content_type='health_check')
        print(f"📧 邮件已发送: {subject}")
    except Exception as e:
        print(f"⚠️ 邮件发送失败: {e}")
    # 微信（仅异常/关键时）
    try:
        from wechat_pusher import WeChatPusher
        w = WeChatPusher()
        if hasattr(w, 'send_text'):
            w.send_text(f"{subject}\n\n{body[:500]}")
            print("💬 微信已推送")
    except Exception as e:
        print(f"⚠️ 微信推送失败: {e}")


# ---------------- 检查项 ----------------
def check_paths():
    """关键路径/脚本存在性（daily+weekly+monthly）
    识别部署包脱敏环境：无 email_config.json/wechat_config.json 但有 .template.json 时，
    属脱敏部署包（真实密钥由部署时填入），跳过敏感配置检查。"""
    core = [
        DB,
        os.path.join(PROJECT_ROOT, 'scripts', 'db_manager.py'),
        os.path.join(PROJECT_ROOT, 'scripts', 'scheduler.py'),
        os.path.join(PROJECT_ROOT, 'scripts', 'cloud_runner.py'),
        os.path.join(PROJECT_ROOT, 'scripts', 'kb_params.py'),
        os.path.join(PROJECT_ROOT, 'scripts', 'consistency_check.py'),
        os.path.join(PROJECT_ROOT, 'config', 'parameters.json'),
    ]
    # 敏感配置：仅在非脱敏环境（存在真实配置或环境非部署包）才检查
    sensitive = [
        os.path.join(PROJECT_ROOT, 'config', 'email_config.json'),
        os.path.join(PROJECT_ROOT, 'config', 'wechat_config.json'),
    ]
    is_package = (not os.path.exists(sensitive[0])) and os.path.exists(
        os.path.join(PROJECT_ROOT, 'config', 'email_config.template.json'))
    if not is_package:
        core.extend(sensitive)

    missing = [p for p in core if not os.path.exists(p)]
    if missing:
        fail('关键路径', f'缺失: {missing}')
    else:
        suffix = '（脱敏部署包，跳过敏感配置检查）' if is_package else ''
        ok('关键路径', f'{len(core)} 项权威路径均存在{suffix}')


def check_db_integrity():
    """DB 可打开 + integrity（daily+weekly+monthly）"""
    try:
        conn = sqlite3.connect(DB)
        integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
        conn.close()
        if integrity == 'ok':
            ok('数据库完整性', 'PRAGMA integrity_check = ok')
        else:
            fail('数据库完整性', f'integrity_check = {integrity}（需人工处理，勿自动修复）')
    except Exception as e:
        fail('数据库可打开', f'连接失败: {e}（需人工处理）')


def check_fts_sync(auto_fix=True):
    """FTS 索引与主表同步（daily+weekly+monthly）。可自动修复：重建索引。"""
    try:
        conn = sqlite3.connect(DB)
        lit = conn.execute("SELECT COUNT(*) FROM literature").fetchone()[0]
        fts = conn.execute("SELECT COUNT(*) FROM literature_fts").fetchone()[0]
        conn.close()
        if lit == fts:
            ok('FTS索引同步', f'literature={lit} / fts={fts}')
        else:
            note = f'FTS 与主表不同步（literature={lit} / fts={fts}）'
            if auto_fix:
                try:
                    import subprocess
                    _r = subprocess.run(
                        [sys.executable, os.path.join(PROJECT_ROOT, 'scripts', 'build_static_site.py')],
                        capture_output=True, text=True, timeout=300)
                    conn2 = sqlite3.connect(DB)
                    fts2 = conn2.execute("SELECT COUNT(*) FROM literature_fts").fetchone()[0]
                    conn2.close()
                    if fts2 == lit:
                        warn('FTS索引同步', note + ' -> 已重建修复', fixed=True)
                    else:
                        warn('FTS索引同步', note + f' -> 重建后仍不同步（fts={fts2}）', fixed=False)
                except Exception as e:
                    warn('FTS索引同步', note + f' -> 重建失败: {e}', fixed=False)
            else:
                warn('FTS索引同步', note, fixed=False)
    except Exception as e:
        fail('FTS索引检查', f'失败: {e}')


def check_archived_residue():
    """废弃脚本残留（daily+weekly+monthly）。可自动修复：不删，仅标注提醒。"""
    archived = ['daemon_scheduler.py', 'push_repo.py', 'setup_cloud.py',
                'run_abstract_backfill_loop.py', 'run_backfill_after_batchA.py',
                'cleanup_shell_noise.py', 'apply_abstract_cn_batch56.py']
    found = [f for f in archived if os.path.exists(os.path.join(PROJECT_ROOT, 'scripts', f))]
    if found:
        # 不自动删除（保守），仅告警提醒归档
        warn('废弃脚本残留', f'scripts/ 下存在应归档的脚本: {found}', fixed=False)
    else:
        ok('废弃脚本', '无废弃脚本残留')


def check_db_stats(level):
    """数据质量统计（weekly+monthly）"""
    try:
        conn = sqlite3.connect(DB)
        total = conn.execute("SELECT COUNT(*) FROM literature").fetchone()[0]
        dom = conn.execute("SELECT COUNT(*) FROM literature WHERE region='domestic'").fetchone()[0]
        inter = conn.execute("SELECT COUNT(*) FROM literature WHERE region='international'").fetchone()[0]
        abs_all = conn.execute("SELECT COUNT(*) FROM literature WHERE abstract IS NOT NULL AND abstract!=''").fetchone()[0]
        abs_cn = conn.execute("SELECT COUNT(*) FROM literature WHERE abstract_cn IS NOT NULL AND abstract_cn!=''").fetchone()[0]
        miss_abs = conn.execute("SELECT COUNT(*) FROM literature WHERE (abstract IS NULL OR abstract='')").fetchone()[0]
        conn.close()
        cov = f"{abs_cn/abs_all*100:.1f}%" if abs_all else "N/A"
        note = (f"总 {total}（国内{dom}/国际{inter}）| 摘要覆盖 {abs_all}/{total} | "
                f"中文摘要 {abs_cn}（翻译覆盖{cov}）| 缺摘要 {miss_abs}")
        ok('数据质量', note)
        return total
    except Exception as e:
        fail('数据质量统计', f'失败: {e}')
        return None


def check_doc_claim(level):
    """文档声称值与数据库比对（weekly+monthly）。可自动修复：无（仅提醒）。"""
    try:
        conn = sqlite3.connect(DB)
        total = conn.execute("SELECT COUNT(*) FROM literature").fetchone()[0]
        conn.close()
        claimed = None
        for doc in ("README.md", os.path.join('docs', 'PROJECT_MASTER_INDEX.md')):
            p = os.path.join(PROJECT_ROOT, doc)
            if os.path.exists(p):
                m = re.search(r"总文献数\*\*\s*\|\s*(\d+)", open(p, encoding="utf-8").read())
                if m:
                    claimed = int(m.group(1))
                    break
        if claimed is not None and total != claimed:
            warn('文档声称值', f'README/主索引声称 {claimed} 篇，实际 {total} 篇（需人工更新文档）', fixed=False)
        else:
            ok('文档声称值', f'文档与数据库一致（{total} 篇）')
    except Exception as e:
        warn('文档声称值', f'检查失败: {e}', fixed=False)


def check_params_drift(level):
    """参数词表漂移（monthly）：parameters.json 与 fetch_incremental 实际定义比对。"""
    try:
        import importlib.util
        # 加载 kb_params
        import kb_params as kp
        # 加载 fetch_incremental
        spec = importlib.util.spec_from_file_location(
            'fi_mod', os.path.join(PROJECT_ROOT, 'scripts', 'fetch_incremental.py'))
        fi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fi)
        drifts = []
        for name in ('EN_QUERIES', 'CN_QUERIES', 'SPORT_TOKENS', 'MEDIA_TOKENS',
                     'CORE_TERMS', 'ESPORTS_TOKENS', 'HARD_BLACKLIST', 'RULES',
                     'PER_QUERY', 'MIN_YEAR'):
            if getattr(kp, name, None) != getattr(fi, name, None):
                drifts.append(name)
        if drifts:
            warn('参数漂移', f'parameters.json 与 fetch_incremental 不一致: {drifts}（需人工统一）', fixed=False)
        else:
            ok('参数漂移', 'parameters.json 与脚本词表完全一致，无漂移')
    except Exception as e:
        warn('参数漂移', f'检查失败: {e}', fixed=False)


def check_scheduler_config(level):
    """调度配置完整性（monthly）：自检并入 cloud_runner（daily/weekly/monthly），确认接入点存在。"""
    runner = os.path.join(PROJECT_ROOT, 'scripts', 'cloud_runner.py')
    if not os.path.exists(runner):
        warn('调度配置', 'cloud_runner.py 缺失（需人工处理）', fixed=False)
        return
    content = open(runner, encoding='utf-8').read()
    has_daily = "_health('daily')" in content
    has_weekly = "_health('weekly')" in content
    has_monthly = "_health('monthly')" in content
    missing = [lv for lv, ok_ in (('daily', has_daily), ('weekly', has_weekly),
                                   ('monthly', has_monthly)) if not ok_]
    if missing:
        warn('调度配置', f'cloud_runner.py 未接入自检: {missing}（需补充）', fixed=False)
    else:
        ok('调度配置', 'cloud_runner.py 已接入 daily/weekly/monthly 三级自检')


def check_backup_recent(level):
    """DB 备份时效（weekly+monthly）。仅提醒。"""
    try:
        db_mtime = os.path.getmtime(DB)
        db_dt = datetime.fromtimestamp(db_mtime)
        age_h = (datetime.now() - db_dt).total_seconds() / 3600
        if age_h > 24:
            warn('DB备份时效', f'DB 最近修改在 {age_h:.1f}h 前（若超过1天需检查云端备份任务）', fixed=False)
        else:
            ok('DB时效', f'DB 最近修改于 {db_dt:%m-%d %H:%M}（{age_h:.1f}h 前）')
    except Exception as e:
        warn('DB备份时效', f'检查失败: {e}', fixed=False)


# ---------------- 各档位入口 ----------------
def run(level, notify_only=False):
    level = level.lower()
    R.__init__()  # 重置

    print(f"🩺 三级自检 [{level}] - {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 56)

    # daily 基础（所有档都做）
    check_paths()
    check_db_integrity()
    check_fts_sync()
    check_archived_residue()

    if level in ('weekly', 'monthly'):
        check_db_stats(level)
        check_doc_claim(level)
        check_backup_recent(level)

    if level == 'monthly':
        check_params_drift(level)
        check_scheduler_config(level)

    # 汇总
    print()
    for name, note in R.passed:
        print(f"  ✅ {name}: {note}")
    for name, note, fixed in R.warned:
        mark = "🛠️已修复" if fixed else "⚠️"
        print(f"  {mark} {name}: {note}")
    for name, note in R.failed:
        print(f"  ❌ {name}: {note}")

    has_fail = len(R.failed) > 0
    has_unfixed_warn = any(not f for _, _, f in R.warned)
    print("=" * 56)

    # 组织报告
    subject = f"🩺 知识库自检[{level}] - {datetime.now():%Y-%m-%d}"
    body_lines = [f"# 🩺 体育新闻知识库自检报告（{level}）", "",
                  f"生成时间: {datetime.now():%Y-%m-%d %H:%M}", ""]
    body_lines.append("## ✅ 正常项")
    body_lines += [f"- {n}: {note}" for n, note in R.passed] or ["- （无）"]
    if R.warned:
        body_lines.append("")
        body_lines.append("## ⚠️ 提醒/自动修复")
        body_lines += [f"- {n}: {note}" + ("（已自动修复）" if f else "") for n, note, f in R.warned]
    if R.failed:
        body_lines.append("")
        body_lines.append("## ❌ 需人工处理")
        body_lines += [f"- {n}: {note}" for n, note in R.failed]
    body = "\n".join(body_lines)

    # 持久化日志
    os.makedirs(HEALTH_LOG, exist_ok=True)
    logf = os.path.join(HEALTH_LOG, f"{level}_{datetime.now():%Y%m%d}.md")
    with open(logf, 'w', encoding='utf-8') as f:
        f.write(body)

    # 通知策略
    if has_fail or has_unfixed_warn:
        # 有异常/未修复告警 -> 必发
        notify(subject, body, notify_only)
        print(f"🔔 有{'异常' if has_fail else '未修复告警'}，已通知")
        return 3 if has_fail else 2
    elif level == 'weekly' or level == 'monthly':
        # 定期摘要（每周/每月即使正常也发一次健康摘要）
        if level == 'weekly':
            notify(subject, body, notify_only)
            print("📋 周度健康摘要已发送")
        # 月度只在有内容时发，正常月度随月度翻译报告，不单独打扰
    else:
        # daily 正常 -> 静默
        print("✅ 每日自检通过，无异常，静默")

    return 0


def main():
    args = sys.argv[1:]
    notify_only = '--notify-only' in args
    levels = [a for a in args if a in ('daily', 'weekly', 'monthly')]
    level = levels[0] if levels else 'daily'
    return run(level, notify_only)


if __name__ == '__main__':
    sys.exit(main())
