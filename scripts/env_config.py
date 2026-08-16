#!/usr/bin/env python3
"""
体育新闻研究知识库 - 环境配置模块（可移植版）
=============================================
统一管理项目根路径和敏感配置，实现"即拷即用"：
  - 项目根目录自动探测（不依赖 /workspace 硬编码）
  - 敏感凭据优先从环境变量读取，其次从 config/*.json 读取
  - 环境变量优先级最高，方便部署时注入

用法:
    from env_config import PROJECT_ROOT, DB_PATH, get_config
"""
import os
import json
import sys
from pathlib import Path

# ============================================
# 项目根目录自动探测
# 优先级：环境变量 PROJECT_ROOT > 本文件所在目录的上级
# ============================================
def detect_root():
    env = os.environ.get('PROJECT_ROOT')
    if env and os.path.isdir(env):
        return env
    # 本文件位于 <root>/scripts/env_config.py
    return str(Path(__file__).resolve().parent.parent)

PROJECT_ROOT = detect_root()

# ============================================
# 常用路径
# ============================================
DB_PATH        = os.path.join(PROJECT_ROOT, 'database', 'knowledge_base.db')
SCHEMA_PATH    = os.path.join(PROJECT_ROOT, 'database', 'schema.sql')
DATA_DIR       = os.path.join(PROJECT_ROOT, 'data')
RAW_DIR        = os.path.join(DATA_DIR, 'raw')
OUTPUT_DIR     = os.path.join(PROJECT_ROOT, 'output')
REPORTS_DIR    = os.path.join(OUTPUT_DIR, 'reports')
WEEKLY_DIR     = os.path.join(OUTPUT_DIR, 'weekly')
WEB_DIR        = os.path.join(PROJECT_ROOT, 'web')
STATIC_SITE    = os.path.join(WEB_DIR, 'static_site')
CONFIG_DIR     = os.path.join(PROJECT_ROOT, 'config')

# ============================================
# 配置文件读取（含环境变量覆盖）
# ============================================
_CONFIG_CACHE = {}

def get_config(filename):
    """
    读取 config/<filename>.json，并允许环境变量覆盖每个键。
    环境变量命名规则：将键名转为大写作为环境变量名。
    例：config/email_config.json 的键 smtp_user 对应环境变量 SMTP_USER
    """
    if filename in _CONFIG_CACHE:
        return _CONFIG_CACHE[filename]

    path = os.path.join(CONFIG_DIR, filename)
    data = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except Exception:
                data = {}

    # 环境变量覆盖
    for key in list(data.keys()):
        env_val = os.environ.get(key.upper())
        if env_val is not None:
            data[key] = env_val

    _CONFIG_CACHE[filename] = data
    return data


def get_email_config():
    """获取邮件配置（环境变量优先）"""
    cfg = get_config('email_config.json')
    return {
        'smtp_server': cfg.get('smtp_server', 'smtp.qq.com'),
        'smtp_port': int(cfg.get('smtp_port', '587')),
        'smtp_user': cfg.get('smtp_user', ''),
        'smtp_password': cfg.get('smtp_password', ''),
        'from_addr': cfg.get('from_addr', cfg.get('smtp_user', '')),
        'to_addr': cfg.get('to_addr', ''),
    }


def get_wechat_config():
    """获取微信配置"""
    return get_config('wechat_config.json')


def get_github_token():
    """获取 GitHub Token（环境变量 GITHUB_TOKEN 优先）"""
    tok = os.environ.get('GITHUB_TOKEN')
    if tok:
        return tok
    # 兼容旧配置
    return get_config('github_config.json').get('token', '')


if __name__ == '__main__':
    print(f"PROJECT_ROOT = {PROJECT_ROOT}")
    print(f"DB_PATH      = {DB_PATH}")
    print(f"STATIC_SITE  = {STATIC_SITE}")
