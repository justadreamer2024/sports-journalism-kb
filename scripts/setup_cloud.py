#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性助手：完成云端 7x24 的剩余初始化
  1. 创建 GitHub Release `db-snapshot` 并上传当前 knowledge_base.db(5MB)
     作为跨运行持久化的权威 DB。
  2. 用 pynacl 经 GitHub API 加密创建仓库 Secrets(邮件/微信/百度)，
     使云端通知开箱可用（密钥不落明文，不进仓库）。

用法: python3 scripts/setup_cloud.py
"""
import os
import sys
import json
import base64
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER_REPO = "justadreamer2024/sports-journalism-kb"
API = "https://api.github.com/repos/%s" % OWNER_REPO
UPLOAD = "https://uploads.github.com/repos/%s/releases/{}/assets" % OWNER_REPO
RESOLVE = "--resolve"
RESOLVE_HOST = "api.github.com:443:140.82.112.6"
UPLOAD_HOST = "uploads.github.com:443:140.82.112.6"
DB_PATH = os.path.join(ROOT, "database", "knowledge_base.db")
TAG = "db-snapshot"

CRED = None
gc = os.path.expanduser("~/.git-credentials")
for line in open(gc):
    if "github.com" in line:
        CRED = line.strip().split("//")[1].split("@")[0]
        break
assert CRED, "未找到 ~/.git-credentials"


def api(method, url, body=None):
    cmd = ["curl", "-s", RESOLVE, RESOLVE_HOST, "-u", CRED, "-X", method, url,
           "-H", "Content-Type: application/json"]
    if body is not None:
        cmd += ["-d", json.dumps(body)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    try:
        return json.loads(r.stdout), r.returncode
    except Exception:
        return {"raw": r.stdout, "stderr": r.stderr}, r.returncode


# ============ 1) Release + DB 上传 ============
def ensure_release():
    d, rc = api("GET", f"{API}/releases/tags/{TAG}")
    if "id" in d:
        print(f"✅ Release 已存在 id={d['id']}")
        return d["id"]
    d, rc = api("POST", f"{API}/releases",
                {"tag_name": TAG, "name": "DB Snapshot (云端持久化)",
                 "body": "知识库权威 DB，由云端调度器读写。", "draft": False, "prerelease": False})
    if "id" in d:
        print(f"✅ Release 已创建 id={d['id']}")
        return d["id"]
    print("❌ 创建 Release 失败:", d)
    sys.exit(1)


def upload_db(rel_id):
    # 若已存在同名资产则先删后传
    rel, _ = api("GET", f"{API}/releases/{rel_id}")
    for a in rel.get("assets", []):
        if a["name"] == "knowledge_base.db":
            api("DELETE", f"{API}/releases/assets/{a['id']}")
            print("🗑️ 已删除旧 DB 资产")
    print(f"⏳ 上传 DB({os.path.getsize(DB_PATH)/1024/1024:.1f}MB)...")
    r = subprocess.run(
        ["curl", "-s", RESOLVE, UPLOAD_HOST, "-u", CRED,
         "-H", "Content-Type: application/octet-stream",
         "--data-binary", f"@{DB_PATH}",
         f"{UPLOAD.format(rel_id)}?name=knowledge_base.db"],
        capture_output=True, text=True, timeout=300)
    try:
        d = json.loads(r.stdout)
        if d.get("name") == "knowledge_base.db":
            print(f"✅ DB 已上传为 Release 资产 (size={d.get('size')})")
        else:
            print("❌ DB 上传异常:", r.stdout[:200], r.stderr[:200])
    except Exception:
        print("❌ DB 上传解析失败:", r.stdout[:200], r.stderr[:200])


# ============ 2) Secrets 注入 ============
def get_public_key():
    d, _ = api("GET", f"{API}/actions/secrets/public_key")
    return d["key"], d["key_id"]


def set_secret(name, value, pubkey_b64, key_id):
    from nacl.public import PublicKey, SealedBox
    pub = PublicKey(base64.b64decode(pubkey_b64))
    ct = SealedBox(pub).encrypt(value.encode("utf-8"))
    enc = base64.b64encode(ct).decode()
    d, rc = api("PUT", f"{API}/actions/secrets/{name}",
                {"encrypted_value": enc, "key_id": key_id})
    if rc in (201, 204):
        print(f"✅ 密钥已设置: {name}")
    else:
        print(f"⚠️ 密钥设置返回({rc}): {name} :: {d}")


def main():
    # 1) DB
    assert os.path.exists(DB_PATH), "本地 DB 不存在"
    rid = ensure_release()
    upload_db(rid)

    # 2) Secrets
    pubkey_b64, key_id = get_public_key()
    # 读取本地真实配置作为密钥值（不写死在脚本里）
    ec = json.load(open(os.path.join(ROOT, "config", "email_config.json"), encoding="utf-8"))
    wc = json.load(open(os.path.join(ROOT, "config", "wechat_config.json"), encoding="utf-8"))
    bd = json.load(open(os.path.join(ROOT, "config", "translate_config.json"), encoding="utf-8"))

    secrets = {
        "EMAIL_SMTP_SERVER": str(ec.get("smtp_server", "smtp.qq.com")),
        "EMAIL_SMTP_PORT": str(ec.get("smtp_port", 587)),
        "EMAIL_SENDER": ec.get("sender", ""),
        "EMAIL_PASSWORD": ec.get("password", ""),
        "EMAIL_RECIPIENT": ec.get("recipient", ""),
        "WECHAT_APP_ID": wc.get("app_id", ""),
        "WECHAT_APP_SECRET": wc.get("app_secret", ""),
        "WECHAT_TEMPLATE_ID": wc.get("template_id", ""),
        "WECHAT_OPENID": wc.get("user_openid", ""),
        "BAIDU_APP_ID": bd.get("baidu_app_id", ""),
        "BAIDU_SECRET": bd.get("baidu_secret", ""),
        "BAIDU_FREE_QUOTA": str(bd.get("free_quota_chars", 81595)),
    }
    for k, v in secrets.items():
        if v:
            set_secret(k, v, pubkey_b64, key_id)
        else:
            print(f"ℹ️ 跳过空值: {k}")
    print("=== 初始化完成 ===")


if __name__ == "__main__":
    main()
