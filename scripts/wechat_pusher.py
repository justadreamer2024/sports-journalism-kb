#!/usr/bin/env python3
"""微信公众号推送模块 - 使用测试号(AppID/AppSecret)

用法:
  1. 在微信测试号后台 https://mp.weixin.qq.com/debug/cgi-bin/sandbox
     获取 appID 和 appsecret
  2. 把 appID/appsecret 填入 config/wechat_config.json
  3. 运行本脚本测试

发送模板消息需要:
  - 在测试号后台添加一个模板，拿到模板ID
  - 在测试号后台把你自己的微信号加入测试号管理（用于获取openid）
"""

import json
import os
import sys
import time
import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'wechat_config.json')

class WeChatPusher:
    def __init__(self):
        self.access_token = None
        self.token_expires = 0
        self._load_config()

    def _load_config(self):
        """加载微信配置"""
        if not os.path.exists(CONFIG_PATH):
            self.config = {}
            return
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

    def is_configured(self):
        """检查是否已配置"""
        return bool(self.config.get('app_id') and self.config.get('app_secret'))

    def _get_access_token(self):
        """获取 access_token（缓存到过期）"""
        if self.access_token and time.time() < self.token_expires:
            return self.access_token
        
        url = "https://api.weixin.qq.com/cgi-bin/token"
        params = {
            'grant_type': 'client_credential',
            'appid': self.config['app_id'],
            'secret': self.config['app_secret']
        }
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        
        if 'access_token' in data:
            self.access_token = data['access_token']
            self.token_expires = time.time() + data.get('expires_in', 7200) - 200
            return self.access_token
        else:
            raise Exception(f"获取access_token失败: {data}")

    def get_user_openid(self):
        """获取测试号管理列表中的用户OpenID"""
        token = self._get_access_token()
        url = f"https://api.weixin.qq.com/cgi-bin/user/get"
        params = {'access_token': token}
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if 'data' in data:
            return data['data'].get('openid', [])
        return []

    def send_template_message(self, openid, template_id, data_dict, url=''):
        """发送模板消息
        Args:
            url: 用户点击模板消息跳转的详情链接。测试号环境下，
                 若传空字符串则不显示"详情"跳转，避免点击报错。
        """
        token = self._get_access_token()
        api_url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={token}"
        payload = {
            "touser": openid,
            "template_id": template_id,
            "url": url,
            "data": data_dict
        }
        resp = requests.post(api_url, json=payload, timeout=15)
        result = resp.json()
        if result.get('errcode') == 0:
            return True, "发送成功"
        else:
            return False, f"发送失败: {result}"

    def send_text_message(self, openid, content):
        """发送文本消息（客服消息接口，测试号可用）"""
        token = self._get_access_token()
        url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={token}"
        payload = {
            "touser": openid,
            "msgtype": "text",
            "text": {"content": content}
        }
        resp = requests.post(url, json=payload, timeout=15)
        result = resp.json()
        if result.get('errcode') == 0:
            return True, "发送成功"
        else:
            return False, f"发送失败: {result}"

def test_wechat():
    """测试微信推送"""
    wc = WeChatPusher()
    if not wc.is_configured():
        print("❌ 微信尚未配置")
        print("   请编辑 config/wechat_config.json 填入 app_id 和 app_secret")
        return
    
    print("✅ 微信配置已加载")
    
    # 获取用户列表
    try:
        openids = wc.get_user_openid()
        print(f"  已关注的用户数: {len(openids)}")
        if openids:
            print(f"  用户OpenID: {openids[0]}")
    except Exception as e:
        print(f"  获取用户失败: {e}")

def send_daily_wechat(stats=None, date_str=None, detail_url=''):
    """发送每日研究动态到微信
    模板结构（已确认）:
      今日研究动态{{date.DATA}}
      研究主题：{{topic.DATA}}
      最新发现：{{finding.DATA}}
      新增文献：{{new_count.DATA}}
      推荐阅读：{{reading.DATA}}
      {{remark.DATA}}
    Args:
        stats: 自定义统计信息
        date_str: 日期字符串
        detail_url: 点击"详情"跳转的链接，必须为空字符串或有效公网URL
    """
    wc = WeChatPusher()
    if not wc.is_configured():
        return False, "微信未配置"
    
    openid = wc.config.get('user_openid')
    template_id = wc.config.get('template_id')
    if not openid or not template_id:
        return False, "OpenID或模板ID未配置"
    
    from datetime import datetime
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    # 从知识库获取真实的最新文献信息（比固定默认值更有价值）
    try:
        import os
        import sqlite3
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from db_manager import get_db
        conn = get_db()
        conn.row_factory = sqlite3.Row
        # 最新文献（按收录时序倒序，与邮件推送保持一致）
        latest = conn.execute(
            "SELECT title, author, year, source_name, abstract, keywords FROM literature "
            "ORDER BY id DESC LIMIT 3"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM literature").fetchone()[0]
        # 今日新增（基于updated_at）
        today_str = date_str
        new_today = conn.execute(
            "SELECT COUNT(*) FROM literature WHERE date(updated_at) >= ?", (today_str,)
        ).fetchone()[0]
        # 最热门主题
        hot = conn.execute(
            "SELECT name FROM research_topics WHERE hot_level > 0 "
            "ORDER BY hot_level DESC LIMIT 1"
        ).fetchone()
        conn.close()

        # 处理作者占位符
        def _clean_author(a):
            a = (a or '').strip()
            if not a or a in ('相关学者', 'Unknown', '未知'):
                return ''
            return a

        # 组装字段（微信模板字段需简短，但保留有效信息）
        topic = hot['name'] if hot else '体育新闻研究'
        # 最新发现：最新1篇文献的标题+作者+期刊
        if latest:
            l0 = latest[0]
            title0 = (l0['title'] or '').strip()
            author0 = _clean_author(l0['author'])
            journal0 = (l0['source_name'] or '').strip()
            year0 = l0['year'] if l0['year'] else '?'
            parts = []
            if title0:
                parts.append(title0[:24])
            if author0:
                parts.append(f"作者：{author0[:12]}")
            if journal0:
                parts.append(journal0[:15])
            if year0 and year0 != '?':
                parts.append(str(year0))
            finding = '；'.join(parts) if parts else "持续跟踪最新研究成果"
        else:
            finding = "持续跟踪最新研究成果"
        # 新增/文献总数
        if new_today > 0:
            new_count = f"今日新增{new_today}篇，累计{total}篇"
        else:
            new_count = f"知识库累计{total}篇文献"
        # 推荐阅读：最新第2篇文献的标题+作者
        if len(latest) > 1:
            l1 = latest[1]
            title1 = (l1['title'] or '').strip()
            author1 = _clean_author(l1['author'])
            journal1 = (l1['source_name'] or '').strip()
            read_parts = []
            if title1:
                read_parts.append(title1[:20])
            if author1:
                read_parts.append(author1[:10])
            elif journal1:
                read_parts.append(journal1[:12])
            reading = '；'.join(read_parts) if read_parts else "进入知识库查看全部文献"
        else:
            reading = "进入知识库查看全部文献"
    except Exception as e:
        topic = "AI与体育新闻"
        finding = "知识库已收录最新研究（更新中）"
        new_count = "更多内容见邮件"
        reading = "进入知识库查看详细"
    
    if stats:
        topic = stats.get('topic', topic)
        finding = stats.get('finding', finding)
        new_count = stats.get('new_count', new_count)
        reading = stats.get('reading', reading)
    
    # 默认不提供详情URL（空字符串），微信消息下方不显示"详情"按钮，避免报错
    # 若提供了有效公网URL，则显示详情跳转
    detail_url = detail_url if detail_url else ''
    
    data = {
        'date': {'value': date_str},
        'topic': {'value': topic},
        'finding': {'value': finding},
        'new_count': {'value': new_count},
        'reading': {'value': reading},
        'remark': {'value': '更多内容见邮件或知识库管理界面'},
    }
    
    return wc.send_template_message(openid, template_id, data, url=detail_url)

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'send':
        ok, msg = send_daily_wechat()
        print("结果:", msg)
    else:
        test_wechat()
