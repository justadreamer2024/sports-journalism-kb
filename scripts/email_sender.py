#!/usr/bin/env python3
"""邮件发送模块 - 读取配置文件并发送邮件"""

import json
import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'email_config.json')

def load_config():
    """加载邮箱配置"""
    if not os.path.exists(CONFIG_PATH):
        print("❌ 邮箱配置文件不存在")
        return None
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def send_email(subject, body_html=None, body_text=None):
    """发送邮件（支持 HTML + MIMEApplication 附件）

    注意：与 `scheduler.send_email(subject, body, content_type, related_summary_id)` 是两个独立实现。
    本版（email_sender 版）支持 HTML/附件，返回 (bool, str)；`scheduler` 版写 email_logs 记录，用于每日动态/周报。

    Args:
        subject: 邮件主题
        body_html: HTML内容(可选)
        body_text: 纯文本内容(可选)
    Returns:
        (bool, str): 是否成功, 错误信息
    """
    config = load_config()
    if not config:
        return False, "配置加载失败"
    
    sender = config.get('sender')
    recipient = config.get('recipient')
    if not sender or not recipient:
        return False, "发件人或收件人邮箱未配置"
    
    try:
        from email import utils
        from email.header import Header
        from email.utils import formataddr
        
        msg = MIMEMultipart('alternative')
        # 用 formataddr 正确处理中文 display name (RFC2047 编码)
        msg['From'] = formataddr((str(Header('Sports Journalism KB', 'utf-8')), sender))
        msg['To'] = recipient
        msg['Subject'] = str(Header(subject, 'utf-8'))
        msg['Date'] = utils.formatdate(localtime=True)
        
        if body_text:
            msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
        if body_html:
            msg.attach(MIMEText(body_html, 'html', 'utf-8'))
        if not body_text and not body_html:
            msg.attach(MIMEText('', 'plain', 'utf-8'))
        
        server = smtplib.SMTP(config.get('smtp_server', 'smtp.qq.com'), config.get('smtp_port', 587))
        server.ehlo()
        if config.get('use_starttls', True):
            server.starttls()
            server.ehlo()
        server.login(sender, config.get('password', ''))
        server.sendmail(sender, [recipient], msg.as_string())
        server.quit()
        
        return True, "发送成功"
    except smtplib.SMTPAuthenticationError as e:
        return False, f"SMTP认证失败(授权码可能错误): {e}"
    except smtplib.SMTPException as e:
        return False, f"SMTP错误: {e}"
    except Exception as e:
        return False, f"发送失败: {e}"

def send_daily_report():
    """发送每日研究报告"""
    # 简单生成报告内容
    body_text = f"""📡 体育新闻研究知识库 - 每日动态

━━━━━━━━━━━━━━━━━━━━
📊 知识库概况
━━━━━━━━━━━━━━━━━━━━
• 总文献: 249 篇
• 国内: 118 篇 | 国际: 131 篇
• 涵盖语种: 7 种

━━━━━━━━━━━━━━━━━━━━
🔬 热门研究主题
━━━━━━━━━━━━━━━━━━━━
• AI与体育新闻深度融合 (热度极高)
• 体育国际传播话语权 (热度极高)
• 社交媒体体育新闻转型 (热度高)

━━━━━━━━━━━━━━━━━━━━
📧 此邮件由体育新闻研究知识库自动生成
发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    
    return send_email(
        subject=f"📡 体育新闻研究知识库测试邮件 - {datetime.now().strftime('%Y-%m-%d')}",
        body_text=body_text
    )

if __name__ == '__main__':
    print("📧 测试邮件发送...")
    ok, msg = send_daily_report()
    if ok:
        print("✅ 邮件发送成功！请检查 mengxiangjun@gmail.com")
    else:
        print(f"❌ 邮件发送失败: {msg}")
