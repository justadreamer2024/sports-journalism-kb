#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
体育新闻研究知识库 - 本地后台守护调度器（跨平台）
=====================================================
面向本地化部署（Windows / macOS / Linux 通用）的常驻守护进程，
替代已归档的 daemon_scheduler.py（其日志/备份硬编码 /tmp，不兼容 Windows）。

功能（与云端 cloud_runner.py 任务对齐）：
  - 每日 08:00 / 20:00  推送研究动态（邮件 + 微信）
  - 每周一 09:00        生成并推送周报
  - 每日 03:00          持续跟踪最新文献（增量抓取 -> 翻译队列 -> 重建站点）
  - 每6小时             本地备份（写至 output/backup/，跨平台）
  - 每日 09:10          月度翻译闸门（仅每月1号：百度免费额度优先翻急需 + 剩余上报）
  - 每日 09:15          白名单期刊月度维护（仅每月1号）
  - 每两周(周三)09:30   NCPSSD 白名单期刊持续采集
  - 三级自检：daily/weekly 每次任务后触发 health_check.py；每月1号触发 monthly

日志：output/daemon.log（Windows/macOS/Linux 通用，不使用 /tmp）
单例：PID 锁 output/daemon.pid，避免多实例并发写库。

用法：
  # Windows
  start /min cmd /k "python scripts\local_scheduler.py"
  # macOS / Linux
  nohup python3 scripts/local_scheduler.py > output/daemon.log 2>&1 &
"""
import os
import sys
import time
import atexit
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import schedule
except ImportError:
    sys.exit("[错误] 缺少 schedule 库，请先运行 install.bat / install_mac.sh 安装依赖。")

from scheduler import daily_update, weekly_summary, send_email, _send_wechat_daily, PROJECT_ROOT

OUT_DIR = os.path.join(PROJECT_ROOT, 'output')
BACKUP_DIR = os.path.join(OUT_DIR, 'backup')
LOG_FILE = os.path.join(OUT_DIR, 'daemon.log')
PID_FILE = os.path.join(OUT_DIR, 'daemon.pid')
HERE = os.path.dirname(os.path.abspath(__file__))

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# 日志配置（写入 output/daemon.log，Windows/macOS 均可用）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('local_scheduler')


def _run(script, args=None, timeout=300):
    """以子进程运行脚本并记录末尾日志。"""
    import subprocess
    cmd = [sys.executable, os.path.join(HERE, script)] + (args or [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        for line in (r.stdout or '').strip().splitlines()[-6:]:
            log.info(f"[{script}] {line}")
        return r
    except Exception as e:
        log.error(f"[{script}] 执行异常: {e}")
        return None


def _health(level):
    """并入式三级自检：调用 health_check.py <level>。异常不阻断主任务。"""
    try:
        log.info(f"🩺 [health:{level}] 运行自检...")
        _run('health_check.py', [level], timeout=120)
    except Exception as e:
        log.error(f"[health:{level}] 自检执行异常: {e}")


def job_daily_push(tag='morning'):
    """每日动态推送（邮件+微信），末尾触发 daily 自检。"""
    try:
        log.info(f"[{tag}] 开始每日动态推送")
        report = daily_update()
        send_email(f"📡 体育新闻研究每日动态 - {datetime.now():%Y-%m-%d}", report)
        ok, msg = _send_wechat_daily()
        log.info(f"[{tag}] 微信推送: {msg}")
    except Exception as e:
        log.error(f"[{tag}] 每日推送失败: {e}")
    _health('daily')


def job_weekly():
    """每周摘要推送，末尾触发 weekly 自检。"""
    try:
        log.info("[weekly] 开始生成周报")
        summary = weekly_summary()
        wf = os.path.join(OUT_DIR, 'weekly', f"Weekly_{datetime.now():%Y_W%W}.md")
        os.makedirs(os.path.dirname(wf), exist_ok=True)
        with open(wf, 'w', encoding='utf-8') as f:
            f.write(summary)
        send_email(f"📋 体育新闻研究周报 - 第{datetime.now().isocalendar()[1]}周", summary)
        ok, msg = _send_wechat_daily()
        log.info(f"[weekly] 微信推送: {msg}; 周报已保存: {wf}")
    except Exception as e:
        log.error(f"[weekly] 失败: {e}")
    _health('weekly')


def job_backup():
    """本地备份到 output/backup/（跨平台，不使用 /tmp）。"""
    try:
        import tarfile
        ts = datetime.now().strftime('%Y%m%d_%H%M')
        backup_file = os.path.join(BACKUP_DIR, f'auto_backup_{ts}.tar.gz')
        with tarfile.open(backup_file, 'w:gz') as tar:
            for path in ['database', 'config', 'data/raw']:
                p = os.path.join(PROJECT_ROOT, path)
                if os.path.exists(p):
                    tar.add(p, arcname=path)
        log.info(f"[backup] 备份完成: {backup_file}")
    except Exception as e:
        log.error(f"[backup] 失败: {e}")


def job_track():
    """持续跟踪：增量抓取 -> 自动翻译队列 -> 重建站点（本地无需 git 部署）。"""
    try:
        log.info("🔍 [track] 开始增量抓取最新文献(多源+质量过滤)...")
        _run('fetch_incremental.py', timeout=600)
        log.info("[track] 自动翻译队列(无密钥时仅统计)...")
        _run('translate_pending.py', timeout=300)
        log.info("[track] 重建静态站点...")
        _run('build_static_site.py', timeout=300)
    except Exception as e:
        log.error(f"[track] 失败: {e}")


def job_monthly_gate():
    """月度闸门：每月1号触发月度翻译（优先急需+剩余上报）。"""
    if datetime.now().day == 1:
        try:
            log.info("[monthly] 百度免费额度优先翻译(急需优先)...")
            _run('translate_pending.py', timeout=300)
            import sqlite3
            c = sqlite3.connect(os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db'))
            remaining = c.execute(
                "SELECT COUNT(*) FROM literature WHERE language='en' "
                "AND (translation_available=0 OR translation_available IS NULL) "
                "AND (abstract_cn IS NULL OR abstract_cn='')"
            ).fetchone()[0]
            c.close()
            send_email(
                f"🌐 月度翻译报告 - {datetime.now():%Y-%m}",
                f"# 🌐 体育新闻知识库 · 月度翻译报告\n\n生成时间: {datetime.now():%Y-%m-%d %H:%M}\n\n"
                f"## 📌 剩余待译: **{remaining} 篇**\n\n"
                + (f"百度免费额度已用尽或未激活。请择一授权: ①完成百度实名认证 / "
                   f"②提供其他免费密钥 / ③授权付费资源。\n" if remaining > 0 else "✅ 全部待译完成。\n")
                + "\n> 本邮件由本地调度器自动生成；付费动作需你亲自确认后才会执行。\n")
        except Exception as e:
            log.error(f"[monthly] 失败: {e}")
        _health('monthly')


def job_whitelist_maintain():
    """白名单期刊月度维护（仅每月1号）。"""
    if datetime.now().day == 1:
        try:
            log.info("[whitelist] 月度白名单期刊维护...")
            _run('maintain_whitelist.py', ['--sync'], timeout=300)
        except Exception as e:
            log.error(f"[whitelist] 白名单维护失败: {e}")


def job_ncpssd():
    """NCPSSD 白名单期刊持续采集（增量 + 质量清理 + 重建站点），每两周一次。"""
    try:
        log.info("[ncpssd] NCPSSD 白名单期刊采集(增量)...")
        _run('fetch_ncpssd_whitelist.py', ['--years', '2020', '2026'], timeout=1500)
        log.info("[ncpssd] 数据质量清理(体育相关性过滤)...")
        _run('clean_ncpssd_news.py', timeout=300)
        log.info("[ncpssd] 重建静态站点...")
        _run('build_static_site.py', timeout=300)
    except Exception as e:
        log.error(f"[ncpssd] 失败: {e}")


def acquire_pid_lock():
    """PID 单例锁：避免守护进程多实例并发破坏数据库。"""
    if os.path.exists(PID_FILE):
        try:
            old = int(open(PID_FILE).read().strip())
            os.kill(old, 0)
            print(f"⚠️ 调度器已在运行 (PID {old})，本实例退出以避免多实例。")
            sys.exit(0)
        except (OSError, ValueError):
            pass
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


def main():
    acquire_pid_lock()
    atexit.register(_cleanup_pid)
    log.info("=" * 50)
    log.info("🚀 体育新闻研究知识库 - 本地后台调度器启动（跨平台）")
    log.info(f"📅 当前时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info("=" * 50)

    schedule.every().day.at("08:00").do(job_daily_push, tag='morning')
    schedule.every().day.at("20:00").do(job_daily_push, tag='evening')
    schedule.every().monday.at("09:00").do(job_weekly)
    schedule.every().day.at("03:00").do(job_track)
    schedule.every(6).hours.do(job_backup)
    schedule.every().day.at("09:10").do(job_monthly_gate)
    schedule.every().day.at("09:15").do(job_whitelist_maintain)
    schedule.every().wednesday.at("09:30").do(job_ncpssd)

    log.info("已注册定时任务:")
    log.info("  - 每日 08:00 / 20:00 推送动态 (含 daily 自检)")
    log.info("  - 每周一 09:00 推送周报 (含 weekly 自检)")
    log.info("  - 每日 03:00 持续跟踪最新文献")
    log.info("  - 每月1日 09:10 月度翻译 + monthly 自检")
    log.info("  - 每月1日 09:15 白名单期刊维护")
    log.info("  - 每两周(周三) 09:30 NCPSSD 采集")
    log.info("  - 每6小时 本地备份")

    job_backup()

    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            log.error(f"调度循环异常(已自动恢复): {e}")
        time.sleep(30)


def _cleanup_pid():
    try:
        if os.path.exists(PID_FILE):
            if open(PID_FILE).read().strip() == str(os.getpid()):
                os.remove(PID_FILE)
    except Exception:
        pass


if __name__ == '__main__':
    main()
