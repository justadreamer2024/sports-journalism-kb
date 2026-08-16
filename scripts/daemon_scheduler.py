#!/usr/bin/env python3
"""
体育新闻研究知识库 - 会话内后台定时调度器
弥补沙箱无cron守护进程的不足。

功能:
  - 每日 08:00 推送邮件+微信动态
  - 每日 20:00 推送邮件+微信动态
  - 每周一 09:00 生成并推送周报
  - 每月 1 日 09:10 月度翻译(百度免费额度优先翻急需 + 剩余上报 + 资源建议)
  - 每6小时 自动同步关键文件到本地备份

用法:
  nohup python3.11 scripts/daemon_scheduler.py > /tmp/sports_kb_daemon.log 2>&1 &
"""
import os
import sys
import time
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import schedule

from scheduler import daily_update, weekly_summary, send_email, _send_wechat_daily, PROJECT_ROOT

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/tmp/sports_kb_daemon.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('sports_kb_daemon')

def job_daily_push(tag='morning'):
    """每日动态推送（邮件+微信）"""
    try:
        log.info(f"[{tag}] 开始每日动态推送")
        report = daily_update()
        # 邮件
        send_email(f"📡 体育新闻研究每日动态 - {datetime.now().strftime('%Y-%m-%d')}", report)
        # 微信
        ok, msg = _send_wechat_daily()
        log.info(f"[{tag}] 微信推送: {msg}")
        log.info(f"[{tag}] 每日推送完成")
    except Exception as e:
        log.error(f"[{tag}] 推送失败: {e}")

def job_weekly():
    """每周摘要推送"""
    try:
        log.info("[weekly] 开始生成周报")
        summary = weekly_summary()
        week_file = os.path.join(PROJECT_ROOT, 'output', 'weekly',
                                f"Weekly_{datetime.now().strftime('%Y_W%W')}.md")
        os.makedirs(os.path.dirname(week_file), exist_ok=True)
        with open(week_file, 'w', encoding='utf-8') as f:
            f.write(summary)
        # 邮件
        send_email(f"📋 体育新闻研究周报 - 第{datetime.now().isocalendar()[1]}周", summary)
        # 微信
        ok, msg = _send_wechat_daily()
        log.info(f"[weekly] 微信推送: {msg}")
        log.info(f"[weekly] 周报已保存: {week_file}")
    except Exception as e:
        log.error(f"[weekly] 失败: {e}")

def job_backup():
    """本地备份"""
    try:
        import tarfile
        backup_file = f"/tmp/sports_kb_auto_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.tar.gz"
        with tarfile.open(backup_file, 'w:gz') as tar:
            for path in ['database', 'config', 'data/raw']:
                p = os.path.join(PROJECT_ROOT, path)
                if os.path.exists(p):
                    tar.add(p, arcname=path)
        log.info(f"[backup] 备份完成: {backup_file}")
    except Exception as e:
        log.error(f"[backup] 失败: {e}")

def send_alert(subject, msg):
    """异常告警：邮件 + 微信(若已配置)。失败不影响主流程。"""
    try:
        send_email(subject, msg)
    except Exception as e:
        log.error(f"[alert] 邮件告警失败: {e}")
    try:
        from wechat_pusher import WeChatPusher
        wc = WeChatPusher()
        if wc.is_configured():
            openid = wc.config.get('user_openid')
            if openid:
                wc.send_text_message(openid, msg[:800])
    except Exception as e:
        log.error(f"[alert] 微信告警失败: {e}")


def build_monthly_translate_report(stdout, remaining):
    """生成《月度翻译报告》: 本月执行摘要 + 剩余待译 + 更多免费/付费资源建议。"""
    lines = [
        "# 🌐 体育新闻知识库 · 月度翻译报告",
        "",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 一、本月翻译执行摘要",
    ]
    for l in (stdout or '').strip().splitlines():
        if any(k in l for k in ['✅', '🛑', '💡', '本轮', '免费额度', '消耗', '已译']):
            lines.append(f"  {l.strip()}")
    lines += [
        "",
        f"## 二、📌 剩余待译: **{remaining} 篇**",
        "",
    ]
    if remaining > 0:
        lines += [
            "百度免费额度(认证后约 100 万字符/月)当前未激活或已用尽, 剩余文献暂未能翻译。",
            "按你的要求, 以下为可推进的【更多免费 / 付费资源】方案, 请择一授权:",
            "",
            "**🔹 免费资源(优先)**",
            "1. 完成百度翻译『个人认证 / 实名认证』→ 免费额度自动激活(零费用, 推荐)",
            "2. 再注册一个已认证的百度标准版账号(额外 ~200 万字符/月)",
            "3. 腾讯云机器翻译 / 阿里云机器翻译(各有免费额度, 需分别注册)",
            "4. MyMemory 公共 API(零注册, 但每日仅 ~500 词, 仅应急)",
            "",
            "**🔸 付费资源(需你明确授权后启用)**",
            "- DeepSeek / OpenAI / 百度翻译高级版(配置密钥后即自动接入, 按量计费)",
            "",
            "👉 请回复: ①已认证百度(可立即重跑) / ②提供其他免费密钥 / ③授权某付费资源。",
        ]
    else:
        lines.append("✅ 全部待译文献已翻译完成, 无剩余。")
    lines.append("")
    lines.append("> 本邮件由调度器自动生成; 任何付费动作均需你亲自确认后才会执行。")
    return "\n".join(lines)


def job_monthly_translate():
    """每月用百度免费额度【优先翻译急需的】(最近抓取者优先), 剩余自动上报并附资源建议。"""
    try:
        import subprocess
        log.info("[monthly_translate] 开始月度翻译(优先急需: 最近增量抓取者优先)...")
        r = subprocess.run(
            [sys.executable, os.path.join(PROJECT_ROOT, 'scripts', 'translate_pending.py')],
            capture_output=True, text=True, timeout=300)
        out = r.stdout or ''
        for line in out.strip().splitlines()[-12:]:
            log.info(f"[monthly_translate] {line}")
        # 统计剩余待译(真实英文待译: pending/new + 无abstract_cn + 非中文语种)
        import sqlite3
        conn = sqlite3.connect(os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db'))
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM literature WHERE data_quality_status IN ('pending_translate','new') "
                    "AND (abstract_cn IS NULL OR abstract_cn='') AND language!='zh'")
        remaining = cur.fetchone()[0]
        conn.close()
        # 生成报告并上报
        report = build_monthly_translate_report(out, remaining)
        send_email(f"🌐 月度翻译报告 - {datetime.now().strftime('%Y-%m')}", report)
        # 微信文本推送(若已配置)
        try:
            from wechat_pusher import WeChatPusher
            wc = WeChatPusher()
            if wc.is_configured():
                openid = wc.config.get('user_openid')
                if openid:
                    wc.send_text_message(openid, report[:800])
        except Exception as e:
            log.error(f"[monthly_translate] 微信推送失败: {e}")
        log.info(f"✅ [monthly_translate] 完成, 剩余待译 {remaining} 篇, 报告已发送")
    except Exception as e:
        log.error(f"[monthly_translate] 失败: {e}")
        send_alert("⚠️ 月度翻译异常", f"job_monthly_translate 异常:\n{e}")


def job_monthly_gate():
    """月度闸门: 每月 1 号触发 job_monthly_translate(schedule 无 .month 支持, 用每日判断兜底)。"""
    if datetime.now().day == 1:
        job_monthly_translate()


def job_track():
    """持续跟踪最新研究成果：增量抓取 -> 自动翻译队列 -> 重建站点 -> 同步线上"""
    try:
        import subprocess
        log.info("🔍 [track] 开始增量抓取最新文献(多源+质量过滤)...")
        r = subprocess.run(
            [sys.executable, os.path.join(PROJECT_ROOT, 'scripts', 'fetch_incremental.py')],
            capture_output=True, text=True, timeout=600)
        for line in (r.stdout or '').strip().splitlines()[-8:]:
            log.info(f"[track] {line}")
        if r.returncode != 0:
            log.warning(f"[track] 抓取退出码非0: {r.returncode}")
        # 自动翻译队列(无密钥时仅统计, 不阻塞)
        log.info("[track] 处理自动翻译队列...")
        subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, 'scripts', 'translate_pending.py')],
                      capture_output=True, text=True, timeout=300)
        # 重建静态站点
        log.info("[track] 重建静态站点...")
        subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, 'scripts', 'build_static_site.py')],
                      capture_output=True, text=True, timeout=300)
        # 同步线上 GitHub Pages
        log.info("[track] 同步线上 GitHub Pages...")
        subprocess.run(['bash', os.path.join(PROJECT_ROOT, 'scripts', 'sync_github_pages.sh')],
                      capture_output=True, text=True, timeout=300)
        log.info("✅ [track] 持续跟踪一轮完成")
    except Exception as e:
        log.error(f"[track] 失败: {e}")
        send_alert("⚠️ 体育新闻知识库·持续跟踪异常", f"job_track 执行异常:\n{e}")


PID_FILE = '/tmp/sports_kb_daemon.pid'


def acquire_pid_lock():
    """PID 单例锁：避免守护进程多实例并发破坏数据库。"""
    if os.path.exists(PID_FILE):
        try:
            old = int(open(PID_FILE).read().strip())
            os.kill(old, 0)  # 进程存活则抛 OSError
            print(f"⚠️ 调度器已在运行 (PID {old})，本实例退出以避免多实例。")
            sys.exit(0)
        except (OSError, ValueError):
            pass  # 旧 PID 失效，覆盖
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


def main():
    acquire_pid_lock()
    import atexit
    atexit.register(lambda: os.path.exists(PID_FILE) and os.path.getsize(PID_FILE) and open(PID_FILE).read().strip() == str(os.getpid()) and os.remove(PID_FILE))
    log.info("=" * 50)
    log.info("🚀 体育新闻研究知识库 - 后台调度器启动")
    log.info(f"📅 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 50)
    
    # 每日 08:00
    schedule.every().day.at("08:00").do(job_daily_push, tag='morning')
    # 每日 20:00
    schedule.every().day.at("20:00").do(job_daily_push, tag='evening')
    # 每周一 09:00
    schedule.every().monday.at("09:00").do(job_weekly)
    # 每日 03:00 持续跟踪最新研究成果（增量抓取 -> 重建 -> 同步）
    schedule.every().day.at("03:00").do(job_track)
    # 每6小时备份
    schedule.every(6).hours.do(job_backup)
    # 月度翻译闸门: 每日 09:10 检查, 仅每月 1 号执行(优先翻急需 + 剩余上报 + 资源建议)
    schedule.every().day.at("09:10").do(job_monthly_gate)

    log.info("已注册定时任务:")
    log.info("  - 每日 08:00 / 20:00 推送动态")
    log.info("  - 每周一 09:00 推送周报")
    log.info("  - 每日 03:00 持续跟踪最新研究成果(增量抓取)")
    log.info("  - 每月 1 日 09:10 月度翻译(优先急需 + 剩余上报 + 资源建议)")
    log.info("  - 每6小时 本地备份")
    log.info("调度器进入循环运行...")

    # 立即执行一次备份确保初始状态
    job_backup()

    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            log.error(f"调度循环异常(已自动恢复): {e}")
        time.sleep(30)

if __name__ == '__main__':
    main()
