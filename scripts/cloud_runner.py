#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
云端调度入口（由 GitHub Actions 调用，替代本地沙箱守护进程 daemon_scheduler.py）。

设计目标：让"持续跟踪 / 每日推送 / 周报 / 月度翻译 / 备份"全部在 GitHub 云端 7x24 运行，
不受本地沙箱休眠影响。

职责：
  1. 从 Release 资产(db-snapshot / knowledge_base.db)拉取【权威 DB】，运行结束后回写，
     实现 DB 跨运行持久化（仓库本身不提交 DB，避免体积膨胀）。
  2. 从 GitHub Secrets(以环境变量形式注入)把密钥写入 config 文件，
     使现有 scheduler / wechat_pusher / translate_pending 无需改动即可工作。
  3. 按 $1 指定的作业执行；track 作业完成后通过 git + GITHUB_TOKEN 部署静态站点到 Pages。

作业映射（见 .github/workflows/cloud_scheduler.yml）：
  daily   -> 每日动态推送（邮件 + 微信）
  weekly  -> 每周一研究摘要（邮件 + 微信）
  track   -> 增量抓取 -> 自动翻译队列 -> 重建站点 -> git 部署
  monthly -> 每月1日百度免费额度优先翻急需 + 剩余上报 + 资源建议
  backup  -> 仅把当前 DB 回写 Release 资产（持久化）
  dispatch-test -> 拉取 DB 并打印统计，验证管线（无副作用）

用法：
  python3 scripts/cloud_runner.py <job>
"""

import os
import sys
import json
import time
import shutil
import subprocess
from datetime import datetime

# ---- 路径 ----
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # 仓库根（PROJECT_ROOT）
sys.path.insert(0, HERE)                           # 让 scheduler / db_manager 可导入
DB_DIR = os.path.join(ROOT, 'database')
DB_PATH = os.path.join(DB_DIR, 'knowledge_base.db')
CONFIG_DIR = os.path.join(ROOT, 'config')
SITE_DIR = os.path.join(ROOT, 'web', 'static_site')
RELEASE_TAG = 'db-snapshot'
ASSET_NAME = 'knowledge_base.db'

GH_REPO = os.environ.get('GITHUB_REPOSITORY', 'justadreamer2024/sports-journalism-kb')


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# ============================================================
# 1) DB 持久化（GitHub Release 资产）
# ============================================================
def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def pull_db():
    """从 Release 资产拉取权威 DB 到 database/。优先 gh，回退 REST API。"""
    os.makedirs(DB_DIR, exist_ok=True)
    # 优先 gh（GitHub Actions 中已用 GITHUB_TOKEN 预认证）
    try:
        r = _run(['gh', 'release', 'download', RELEASE_TAG, '-p', ASSET_NAME,
                  '-D', DB_DIR], timeout=180)
        if r.returncode == 0 and os.path.exists(DB_PATH):
            log("✅ 已从 Release 资产拉取 DB (gh)")
            return True
        else:
            log(f"⚠️ gh 拉取 DB 未成功(rc={r.returncode}): {r.stderr[-200:]}")
    except Exception as e:
        log(f"⚠️ gh 拉取异常: {e}")
    # 回退：REST API（需要 GITHUB_TOKEN）
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        try:
            # 取资产下载地址
            api = (f"https://api.github.com/repos/{GH_REPO}/releases/tags/{RELEASE_TAG}")
            out = _run(['curl', '-s', '--resolve', 'api.github.com:443:140.82.112.6',
                        '-H', f'Authorization: Bearer {token}', api], timeout=30)
            rel = json.loads(out.stdout)
            asset = next((a for a in rel.get('assets', []) if a['name'] == ASSET_NAME), None)
            if asset:
                dl = _run(['curl', '-sL', '--resolve', 'api.github.com:443:140.82.112.6',
                           '-H', f'Authorization: Bearer {token}',
                           '-o', DB_PATH, asset['url']], timeout=180)
                if dl.returncode == 0 and os.path.exists(DB_PATH):
                    log("✅ 已从 Release 资产拉取 DB (REST)")
                    return True
        except Exception as e:
            log(f"⚠️ REST 拉取异常: {e}")
    if not os.path.exists(DB_PATH):
        # 最后兜底：用 schema 初始化空库（仅首次极端情况）
        log("⚠️ 未找到 Release 资产 DB，尝试用 schema 初始化空库")
        try:
            from db_manager import init_database
            init_database()
            return True
        except Exception as e:
            log(f"❌ DB 初始化失败: {e}")
            return False
    return os.path.exists(DB_PATH)


def push_db():
    """把当前 DB 回写 Release 资产（覆盖）。"""
    if not os.path.exists(DB_PATH):
        log("⚠️ 无 DB 可回写，跳过")
        return False
    try:
        r = _run(['gh', 'release', 'upload', RELEASE_TAG, DB_PATH, '--clobber'], timeout=240)
        if r.returncode == 0:
            log("✅ DB 已回写 Release 资产 (gh)")
            return True
        log(f"⚠️ gh 回写失败(rc={r.returncode}): {r.stderr[-200:]}")
    except Exception as e:
        log(f"⚠️ gh 回写异常: {e}")
    return False


# ============================================================
# 2) 密钥从 Secrets(env) 注入 config 文件
# ============================================================
def inject_secrets():
    """把 GitHub Secrets(环境变量)写入 config/*.json，使现有模块开箱即用。
    若某组密钥缺失，则保留仓库内的脱敏占位配置，相关通知会被模块自动跳过。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)

    email = {
        'smtp_server': os.environ.get('EMAIL_SMTP_SERVER', 'smtp.qq.com'),
        'smtp_port': int(os.environ.get('EMAIL_SMTP_PORT', '587')),
        'sender': os.environ.get('EMAIL_SENDER', ''),
        'password': os.environ.get('EMAIL_PASSWORD', ''),
        'recipient': os.environ.get('EMAIL_RECIPIENT', ''),
        'use_ssl': False,
        'use_starttls': True,
    }
    if email['sender'] and email['password']:
        with open(os.path.join(CONFIG_DIR, 'email_config.json'), 'w', encoding='utf-8') as f:
            json.dump(email, f, ensure_ascii=False, indent=2)
        log("✅ 已注入邮件配置")

    wc = {
        'app_id': os.environ.get('WECHAT_APP_ID', ''),
        'app_secret': os.environ.get('WECHAT_APP_SECRET', ''),
        'template_id': os.environ.get('WECHAT_TEMPLATE_ID', ''),
        'user_openid': os.environ.get('WECHAT_OPENID', ''),
    }
    if wc['app_id'] and wc['app_secret']:
        with open(os.path.join(CONFIG_DIR, 'wechat_config.json'), 'w', encoding='utf-8') as f:
            json.dump(wc, f, ensure_ascii=False, indent=2)
        log("✅ 已注入微信配置")

    bd = {
        'backend': 'baidu',
        'baidu_app_id': os.environ.get('BAIDU_APP_ID', ''),
        'baidu_secret': os.environ.get('BAIDU_SECRET', ''),
        'free_quota_chars': int(os.environ.get('BAIDU_FREE_QUOTA', '81595')),
    }
    if bd['baidu_app_id'] and bd['baidu_secret']:
        with open(os.path.join(CONFIG_DIR, 'translate_config.json'), 'w', encoding='utf-8') as f:
            json.dump(bd, f, ensure_ascii=False, indent=2)
        log("✅ 已注入百度翻译配置")


# ============================================================
# 3) 各作业实现
# ============================================================
def run_daily(tag='morning'):
    from scheduler import daily_update, send_email, _send_wechat_daily
    report = daily_update()
    try:
        send_email(f"📡 体育新闻研究每日动态 - {datetime.now():%Y-%m-%d}", report)
    except Exception as e:
        log(f"⚠️ 邮件推送跳过: {e}")
    try:
        _send_wechat_daily()
    except Exception as e:
        log(f"⚠️ 微信推送跳过: {e}")


def run_weekly():
    from scheduler import weekly_summary, send_email, _send_wechat_daily
    summary = weekly_summary()
    os.makedirs(os.path.join(ROOT, 'output', 'weekly'), exist_ok=True)
    wf = os.path.join(ROOT, 'output', 'weekly', f"Weekly_{datetime.now():%Y_W%W}.md")
    with open(wf, 'w', encoding='utf-8') as f:
        f.write(summary)
    try:
        sid = None
        try:
            import sqlite3
            c = __import__('db_manager').get_db()
            sid = c.execute("SELECT MAX(id) FROM weekly_summaries").fetchone()[0]
            c.close()
        except Exception:
            pass
        send_email(f"📋 体育新闻研究周报 - 第{datetime.now().isocalendar()[1]}周",
                   summary, content_type='weekly_digest', related_summary_id=sid)
    except Exception as e:
        log(f"⚠️ 邮件推送跳过: {e}")
    try:
        _send_wechat_daily()
    except Exception as e:
        log(f"⚠️ 微信推送跳过: {e}")


def run_track():
    """持续跟踪：增量抓取 -> 自动翻译队列 -> 重建站点 -> git 部署。"""
    log("🔍 [track] 增量抓取最新文献(多源 + 质量过滤)...")
    _run([sys.executable, os.path.join(HERE, 'fetch_incremental.py')], timeout=600)
    log("[track] 自动翻译队列(无密钥仅统计)...")
    _run([sys.executable, os.path.join(HERE, 'translate_pending.py')], timeout=300)
    log("[track] 重建静态站点...")
    _run([sys.executable, os.path.join(HERE, 'build_static_site.py')], timeout=300)
    log("[track] git 部署到 GitHub Pages...")
    deploy_git()


def run_monthly():
    """每月1日用百度免费额度优先翻急需 + 剩余上报 + 资源建议（与守护进程逻辑一致）。"""
    log("[monthly] 运行百度免费额度优先翻译...")
    _run([sys.executable, os.path.join(HERE, 'translate_pending.py')], timeout=300)
    import sqlite3
    c = __import__('db_manager').get_db()
    remaining = c.execute(
        "SELECT COUNT(*) FROM literature WHERE language='en' "
        "AND (translation_available=0 OR translation_available IS NULL) "
        "AND (abstract_cn IS NULL OR abstract_cn='')"
    ).fetchone()[0]
    c.close()
    try:
        from scheduler import send_email
        report = (
            f"# 🌐 体育新闻知识库 · 月度翻译报告\n\n"
            f"生成时间: {datetime.now():%Y-%m-%d %H:%M}\n\n"
            f"## 一、本月翻译执行摘要\n- 已运行百度免费额度优先翻译（急需优先）。\n\n"
            f"## 二、📌 剩余待译: **{remaining} 篇**\n\n"
            + (f"百度免费额度当前已用尽或未激活，剩余文献暂未能翻译。\n"
               f"请择一授权: ①完成百度实名认证激活额度 / ②提供其他免费密钥 / ③授权某付费资源。\n"
               if remaining > 0 else "✅ 全部待译文献已翻译完成，无剩余。\n")
            + "\n> 本邮件由云端调度器自动生成；任何付费动作均需你亲自确认后才会执行。\n"
        )
        send_email(f"🌐 月度翻译报告 - {datetime.now():%Y-%m}", report)
    except Exception as e:
        log(f"⚠️ 月度报告邮件跳过: {e}")


def run_backup():
    """仅持久化当前 DB 到 Release 资产。"""
    push_db()


def deploy_git():
    """把 web/static_site 产出的站点文件提交并推送到 main（Pages 源）。"""
    if not os.path.isdir(SITE_DIR):
        log("⚠️ 静态站未生成，跳过部署")
        return
    site_files = ['index.html', 'data.json', 'README.md', 'research_map.html']
    changed = False
    for f in site_files:
        src = os.path.join(SITE_DIR, f)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(ROOT, f))
            changed = True
    if not changed:
        log("⚠️ 无站点文件可部署")
        return

    token = os.environ.get('GITHUB_TOKEN')
    if token and GH_REPO:
        _run(['git', 'remote', 'set-url', 'origin',
              f'https://x-access-token:{token}@github.com/{GH_REPO}.git'])
    _run(['git', 'config', 'user.email', 'bot@sports-kb.local'])
    _run(['git', 'config', 'user.name', 'Cloud Scheduler'])
    _run(['git', 'add', *site_files])
    diff = _run(['git', 'diff', '--cached', '--quiet'])
    if diff.returncode == 0:
        log("📭 站点无变更，无需部署")
        return
    _run(['git', 'commit', '-m', f"🤖 自动更新知识库 {datetime.now():%Y-%m-%d %H:%M}"])
    pr = _run(['git', 'push', 'origin', 'HEAD'], timeout=120)
    log(f"🚀 部署完成 rc={pr.returncode} :: {pr.stdout[-160:]}{pr.stderr[-160:]}")


def run_dispatch_test():
    """验证管线：拉取 DB 并打印统计（无副作用）。"""
    import sqlite3
    c = __import__('db_manager').get_db()
    c.row_factory = sqlite3.Row
    total = c.execute("SELECT COUNT(*) FROM literature").fetchone()[0]
    trans = c.execute("SELECT COUNT(*) FROM literature WHERE abstract_cn IS NOT NULL AND abstract_cn<>''").fetchone()[0]
    c.close()
    log(f"✅ 管线验证通过：DB 可读，文献总数 {total}，已译 {trans}")


# ============================================================
# 入口
# ============================================================
def main():
    job = (sys.argv[1] if len(sys.argv) > 1 else 'dispatch-test').strip().lower()
    log(f"🚀 云端调度启动，作业={job}")

    inject_secrets()

    # 需要 DB 的作业先拉取
    if job in ('daily', 'weekly', 'track', 'monthly', 'backup', 'dispatch-test'):
        if not pull_db():
            log("❌ DB 拉取失败，终止")
            sys.exit(1)

    try:
        if job == 'daily':
            run_daily()
        elif job == 'weekly':
            run_weekly()
        elif job == 'track':
            run_track()
        elif job == 'monthly':
            run_monthly()
        elif job == 'backup':
            run_backup()
        elif job == 'dispatch-test':
            run_dispatch_test()
        else:
            log(f"⚠️ 未知作业: {job}")
            sys.exit(2)
    finally:
        # DB 写入型作业结束后回写持久化
        if job in ('track', 'backup', 'monthly'):
            push_db()

    log(f"✅ 作业 [{job}] 完成")


if __name__ == '__main__':
    main()
