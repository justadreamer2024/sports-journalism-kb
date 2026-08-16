#!/usr/bin/env python3
"""
体育新闻研究知识库 - 新文献自动翻译队列
================================================================
把国际文献的中文摘要(abstract_cn)翻译缺口自动补齐。

设计:
  - 标记: fetch_incremental 入库国际文献时置 data_quality_status='pending_translate'
  - 本脚本扫描待译队列, 若环境配置了翻译/LLM 密钥则调用 API 自动翻译并写回 abstract_cn;
    若未配置密钥, 仅统计队列规模并提示(安全 no-op, 不阻塞调度器)。

密钥(任选其一, 环境变量或 config/translate_config.json):
  DEEPSEEK_API_KEY            -> base=https://api.deepseek.com/v1, model=deepseek-chat
  OPENAI_API_KEY              -> base=https://api.openai.com/v1,   model=env OPENAI_MODEL|gpt-4o-mini
  TRANSLATE_API_KEY + TRANSLATE_BASE_URL + TRANSLATE_MODEL  -> 通用 OpenAI 兼容接口

用法:
  python3.11 scripts/translate_pending.py              # 处理待译队列(有密钥才真翻译)
  python3.11 scripts/translate_pending.py --limit 20   # 本次最多译 N 篇
  python3.11 scripts/translate_pending.py --dry-run    # 只统计不翻译
"""
import os
import sys
import json
import time
import re
import sqlite3
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db')
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'translate_config.json')
USAGE_PATH = os.path.join(PROJECT_ROOT, 'config', 'translation_usage.json')

# 免费额度安全阈值: 累计消耗达到免费额度的该比例即停止并请示(绝不擅自越界/触发费用)
SAFE_THRESHOLD = 0.95


def resolve_api_config():
    """解析翻译配置; 返回含 'backend' 字段的字典, 无可用后端返回 None。

    后端优先级（免费优先，收费可选）:
      mymemory            -> 免费无密钥 (MyMemory 公共 API, 每日约 500 词限额, 适合小批量演示)
      baidu               -> 免费额度 (百度翻译开放平台, 需 appid+密钥, 认证后约 100 万字符/月)
      deepseek/openai/通用 -> 收费 LLM (原逻辑, 可选)
    """
    cfg_file = {}
    if os.path.exists(CONFIG_PATH):
        try:
            cfg_file = json.load(open(CONFIG_PATH, encoding='utf-8')) or {}
        except Exception:
            cfg_file = {}

    backend = (os.environ.get('FREE_BACKEND') or cfg_file.get('backend') or '').lower()

    # 1) 百度翻译免费额度 (需 appid + 密钥, 零费用)
    baidu_id = os.environ.get('BAIDU_APP_ID') or cfg_file.get('baidu_app_id')
    baidu_secret = os.environ.get('BAIDU_APP_KEY') or cfg_file.get('baidu_secret')
    if backend == 'baidu' and baidu_id and baidu_secret:
        return {'backend': 'baidu', 'app_id': baidu_id, 'secret': baidu_secret}

    # 2) MyMemory 免费无密钥 (零注册, 每日限额, 适合小批量)
    if backend == 'mymemory':
        return {'backend': 'mymemory'}

    # 3) 显式通用收费 LLM (环境变量)
    key = os.environ.get('TRANSLATE_API_KEY')
    if key:
        return {'backend': 'llm',
                'base': os.environ.get('TRANSLATE_BASE_URL', 'https://api.openai.com/v1').rstrip('/'),
                'model': os.environ.get('TRANSLATE_MODEL', 'gpt-4o-mini'),
                'key': key}
    # 4) DeepSeek (收费, 可选)
    ds = os.environ.get('DEEPSEEK_API_KEY')
    if ds:
        return {'backend': 'llm', 'base': 'https://api.deepseek.com/v1', 'model': 'deepseek-chat', 'key': ds}
    # 5) OpenAI (收费, 可选)
    oa = os.environ.get('OPENAI_API_KEY')
    if oa:
        return {'backend': 'llm', 'base': 'https://api.openai.com/v1',
                'model': os.environ.get('OPENAI_MODEL', 'gpt-4o-mini'), 'key': oa}
    # 6) 配置文件中的收费 LLM
    if cfg_file.get('api_key'):
        return {'backend': 'llm',
                'base': (cfg_file.get('base_url') or 'https://api.openai.com/v1').rstrip('/'),
                'model': cfg_file.get('model', 'gpt-4o-mini'),
                'key': cfg_file['api_key']}
    return None


def load_cfg_file():
    """读取 translate_config.json（容错）。"""
    if os.path.exists(CONFIG_PATH):
        try:
            return json.load(open(CONFIG_PATH, encoding='utf-8')) or {}
        except Exception:
            pass
    return {}


def free_quota_chars():
    """免费额度字符数（可在 config 的 free_quota_chars 覆盖, 默认 1,000,000）。"""
    return int(load_cfg_file().get('free_quota_chars') or 1_000_000)


def load_usage():
    """读取本计费周期(自然月)累计翻译字符数; 跨月自动重置。返回 (period, chars)。"""
    import datetime
    now = datetime.datetime.now()
    period = f"{now.year}-{now.month:02d}"
    try:
        d = json.load(open(USAGE_PATH, encoding='utf-8'))
        if d.get('period') == period:
            return period, int(d.get('chars', 0))
    except Exception:
        pass
    return period, 0


def save_usage(period, chars):
    try:
        json.dump({'period': period, 'chars': chars},
                  open(USAGE_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    except Exception:
        pass


def translate_via_api(cfg, text):
    """调用 OpenAI 兼容 chat/completions 翻译摘要。"""
    import requests
    url = f"{cfg['base']}/chat/completions"
    headers = {'Authorization': f"Bearer {cfg['key']}", 'Content-Type': 'application/json'}
    payload = {
        'model': cfg['model'],
        'messages': [
            {'role': 'system', 'content': '你是体育新闻研究领域的学术翻译，将以下外文文献摘要准确、专业地译为简体中文，'
                                          '保留学术术语与专有名词（期刊名、理论名、人名可保留原文或音译）。只输出译文本身，不要解释、不要引号。'},
            {'role': 'user', 'content': text},
        ],
        'temperature': 0.2,
        'max_tokens': 800,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=40)
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content'].strip()


def translate_via_mymemory(text):
    """免费无密钥翻译 (MyMemory 公共 API, 英->中)。

    限制: 单次查询 <=500 字符, 每日约 500 词配额。故按句子切到 ~450 字符分块翻译后拼接,
    仅适合小批量/演示; 全量请用百度免费额度后端。
    """
    import requests, re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, buf = [], ''
    for s in sentences:
        # 超长句(如学术 'Purpose...' 句型)按 450 字符硬切, 绕过 MyMemory 500 字符上限
        if len(s) > 450:
            if buf:
                chunks.append(buf); buf = ''
            for i in range(0, len(s), 450):
                chunks.append(s[i:i + 450])
            continue
        if len(buf) + len(s) + 1 <= 450:
            buf = (buf + ' ' + s).strip()
        else:
            if buf:
                chunks.append(buf)
            buf = s
    if buf:
        chunks.append(buf)
    out = []
    for ch in chunks:
        if not ch.strip():
            continue
        resp = requests.get('https://api.mymemory.translated.net/get',
                            params={'q': ch, 'langpair': 'en|zh-CN'}, timeout=20)
        d = resp.json()
        t = d.get('responseData', {}).get('translatedText') if d.get('responseStatus') == 200 else None
        if t:
            out.append(t)
        else:
            raise RuntimeError(f"MyMemory 失败: {d.get('responseStatus')} {d.get('responseDetails')}")
        time.sleep(0.4)  # 放慢, 避免触发限流
    return ''.join(out)


def translate_via_baidu(cfg, text):
    """免费额度翻译 (百度翻译开放平台, 需 appid+密钥, 认证后约 100 万字符/月)。

    错误码 54004 = 账户余额/免费额度不足, 需充值或激活认证 → 抛 QuotaExhausted 由 run() 捕获并停止请示。
    """
    import requests, hashlib, random, string
    salt = ''.join(random.choices(string.digits, k=8))
    sign = hashlib.md5((cfg['app_id'] + text + salt + cfg['secret']).encode('utf-8')).hexdigest()
    resp = requests.get('https://fanyi-api.baidu.com/api/trans/vip/translate',
                        params={'q': text, 'from': 'auto', 'to': 'zh', 'appid': cfg['app_id'],
                                'salt': salt, 'sign': sign}, timeout=20)
    d = resp.json()
    if 'trans_result' in d:
        return ''.join(r['dst'] for r in d['trans_result'])
    code = str(d.get('error_code'))
    msg = d.get('error_msg', '')
    if code == '54004':
        # 免费额度耗尽或需激活认证: 明确抛出, 绝不重试/绝不触发付费
        raise QuotaExhausted(f"百度免费额度不足(54004): 需完成个人认证激活额度或充值, 已停止。{msg}")
    raise RuntimeError(f"百度翻译失败: {code} {msg}")


class QuotaExhausted(Exception):
    """免费额度耗尽/需充值信号, run() 捕获后停止整批并请示。"""
    pass


def has_cjk(text):
    """判断文本是否含中文(已是中文则无需翻译)。"""
    return bool(re.search(r'[\u4e00-\u9fff]', text or ''))


def fetch_queue(limit):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # 注: language 字段偶有错标(中文文献误标 en), 故 SQL 多取一些,
    # 在 Python 层用 has_cjk 过滤掉"摘要本身已是中文"的噪声后再截断到 limit。
    rows = conn.execute(
        """SELECT id, title, abstract FROM literature
           WHERE language != 'zh'
             AND abstract IS NOT NULL AND abstract != ''
             AND (abstract_cn IS NULL OR abstract_cn = '')
             AND (data_quality_status = 'pending_translate' OR data_quality_status = 'new')
             AND region = 'international'
           ORDER BY created_at DESC, id DESC LIMIT ?""",
        (max(limit * 4, 50),)
    ).fetchall()
    conn.close()
    # 跳过摘要本身已是中文的文献(如Crossref收录的中文标题论文)
    filtered = [r for r in rows if not has_cjk(r['abstract'])]
    return filtered[:limit]


def run(limit=30, dry_run=False):
    queue = fetch_queue(limit)
    total_pending = fetch_queue(99999)  # 全量待译规模(用于报告)
    cfg = resolve_api_config()

    print(f"🔤 待译队列: 本次处理 {len(queue)} 篇 (全库待译约 {len(total_pending)} 篇)")
    if not cfg:
        print("⚠️ 未检测到任何翻译配置 → 仅统计队列, 不执行翻译。")
        print("   免费方案(无需花钱):")
        print("     · MyMemory 零注册: config/translate_config.json 设 \"backend\":\"mymemory\"")
        print("     · 百度免费额度:   config/translate_config.json 设 \"backend\":\"baidu\" + baidu_app_id/baidu_secret")
        print("   收费可选: DEEPSEEK_API_KEY / OPENAI_API_KEY / TRANSLATE_API_KEY 或 config 的 api_key")
        if dry_run:
            for r in queue[:10]:
                print(f"   · [{r['id']}] {r['title'][:60]}")
        return {'translated': 0, 'queued': len(queue), 'total_pending': len(total_pending), 'api': False}

    if dry_run:
        print("🟡 dry-run: 以下将翻译(实际不写库):")
        for r in queue[:10]:
            print(f"   · [{r['id']}] {r['title'][:60]}")
        return {'translated': 0, 'queued': len(queue), 'total_pending': len(total_pending), 'api': True}

    # ---- 免费额度监控 (仅对免费后端 baidu / mymemory 生效) ----
    free_monitor = cfg['backend'] in ('baidu', 'mymemory')
    period, used_chars = load_usage()
    free_quota = free_quota_chars()
    quota_hit = False
    if free_monitor:
        pct = (used_chars / free_quota * 100) if free_quota else 0
        print(f"💡 免费额度监控[{cfg['backend']}]: 本计费周期({period})已用 {used_chars:,} / 免费 {free_quota:,} 字符 ({pct:.1f}%)")
        if free_quota * SAFE_THRESHOLD - used_chars <= 0:
            print("🛑 已达免费额度安全上限(95%), 停止翻译并请示用户; 不擅自充值或切换付费通道。")
            return {'translated': 0, 'failed': 0, 'queued': len(queue),
                    'total_pending': len(total_pending), 'api': True, 'quota_hit': True}

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    translated = 0
    failed = 0
    translated_chars = 0
    for r in queue:
        try:
            if cfg['backend'] == 'mymemory':
                cn = translate_via_mymemory(r['abstract'])
            elif cfg['backend'] == 'baidu':
                cn = translate_via_baidu(cfg, r['abstract'])
                time.sleep(1)  # 百度标准版 QPS=1 限流
            else:
                cn = translate_via_api(cfg, r['abstract'])
            if not cn:
                failed += 1
                continue
            conn.execute(
                "UPDATE literature SET abstract_cn=?, data_quality_status='translated', updated_at=datetime('now') WHERE id=?",
                (cn, r['id'])
            )
            conn.commit()
            translated += 1
            translated_chars += len(r['abstract'] or '')
            if translated % 10 == 0:
                print(f"   ✓ 已译 {translated}/{len(queue)} (本轮累计 {translated_chars:,} 字符, 均在免费额度内)")
        except QuotaExhausted as qe:
            quota_hit = True
            print(f"   🛑 {qe}")  # 触达免费额度上限: 停止整批, 等待用户指示
            break
        except Exception as e:
            failed += 1
            print(f"   ✗ [{r['id']}] 翻译失败: {e}")
            time.sleep(1)
    conn.close()

    # 更新本周期累计消耗
    if free_monitor:
        total_used = used_chars + translated_chars
        save_usage(period, total_used)
    else:
        total_used = used_chars

    if quota_hit:
        print(f"🛑 翻译在 {translated} 篇后触达免费额度上限(百度54004), 已停止。")
        print(f"   本轮消耗 {translated_chars:,} 字符; 本计费周期累计 {total_used:,} / {free_quota:,}。")
        print(f"   ⚠️ 按约定未擅自充值/触发付费。请确认下一步: 完成个人认证激活免费额度 / 授权其他免费通道 / 批准充值。")
    else:
        print(f"✅ 本轮翻译完成: 成功 {translated} 篇, 失败 {failed} 篇, 消耗约 {translated_chars:,} 字符")
        if free_monitor:
            pct = (total_used / free_quota * 100) if free_quota else 0
            print(f"   💡 免费额度: 本周期累计 {total_used:,} / {free_quota:,} 字符 ({pct:.1f}%), 未触发任何费用")
    return {'translated': translated, 'failed': failed, 'chars': translated_chars, 'queued': len(queue),
            'total_pending': len(total_pending), 'api': True, 'quota_hit': quota_hit}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=30)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    run(limit=args.limit, dry_run=args.dry_run)
