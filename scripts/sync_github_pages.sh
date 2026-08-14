#!/usr/bin/env bash
# =============================================================================
# 一键同步最新静态站点到 GitHub Pages 线上
#
# 说明：
#   1. 读取有效凭证（优先 GITHUB_TOKEN 环境变量，其次 ~/.git-credentials）
#   2. 调用 update_github_pages.py 同步 README.md / data.json / index.html
#   3. 验证线上仓库最新提交
#
# 用法：
#   bash scripts/sync_github_pages.sh
#
# 依赖：
#   - update_github_pages.py（已内置凭证读取 + --resolve 绕过机制）
#   - 有效凭证存在于 ~/.git-credentials 或 GITHUB_TOKEN 环境变量
# =============================================================================
set -e
cd "$(dirname "$0")/.."

echo "=============================================="
echo " 🔄 同步体育新闻研究知识库到 GitHub Pages"
echo "=============================================="

# 1. 检查本地静态站点存在
if [ ! -f "web/static_site/data.json" ]; then
    echo "❌ 本地静态站点不存在: web/static_site/data.json"
    exit 1
fi

# 2. 优先获取 github-connector OAuth token（可选，若已存在 GITHUB_TOKEN 则跳过）
if [ -z "$GITHUB_TOKEN" ] && [ -f /root/.codebuddy/skills/github-connector/scripts/get_token.sh ]; then
    echo "⏳ 获取 github-connector OAuth token ..."
    source /root/.codebuddy/skills/github-connector/scripts/get_token.sh github >/dev/null 2>&1 || true
fi

# 3. 校验凭证是否有效
CRED=""
if [ -f "$HOME/.git-credentials" ]; then
    CRED=$(sed -E 's|https://([^@]*)@github.com|\1|' "$HOME/.git-credentials" 2>/dev/null)
fi
if [ -z "$CRED" ] && [ -n "$GITHUB_TOKEN" ]; then
    CRED="justadreamer2024:$GITHUB_TOKEN"
fi
if [ -z "$CRED" ]; then
    echo "❌ 未找到有效 GitHub 凭证（~/.git-credentials 或 GITHUB_TOKEN）"
    exit 1
fi

# 校验认证
AUTH_CHECK=$(curl -s --resolve api.github.com:443:140.82.112.6 -u "$CRED" \
    "https://api.github.com/user" --max-time 15 2>/dev/null | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('login',''))" 2>/dev/null || echo "")
if [ "$AUTH_CHECK" != "justadreamer2024" ]; then
    echo "❌ GitHub 认证失败（请重新授权）。当前登录: '$AUTH_CHECK'"
    exit 1
fi
echo "✅ GitHub 认证有效: $AUTH_CHECK"

# 4. 执行同步
echo ""
echo "⏳ 同步站点文件 ..."
python3 scripts/update_github_pages.py

# 5. 验证线上最新提交
echo ""
echo "=============================================="
echo " ✅ 线上仓库最新提交"
echo "=============================================="
curl -s --resolve api.github.com:443:140.82.112.6 -u "$CRED" \
    "https://api.github.com/repos/justadreamer2024/sports-journalism-kb/commits?per_page=3" \
    --max-time 20 2>/dev/null | python3 -c \
    "import sys,json; [print(f\"  {c['sha'][:10]}  {c['commit']['message'][:50]}\") for c in json.load(sys.stdin)]" 2>/dev/null || echo "  (无法获取提交记录)"

echo ""
echo "🌐 公网访问: https://justadreamer2024.github.io/sports-journalism-kb/"
echo "   （公网需 1-2 分钟完成 Pages 重建）"
