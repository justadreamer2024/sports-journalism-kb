# 🗂️ 体育新闻研究知识库 — 主索引 / 单一事实源（防遗忘）

> **本文件是项目的"防遗忘主索引"**。所有固化过的操作、参数、权威来源集中于此。
> 任何后续操作**先查本文件**，避免重复做已做过的事、或误用已废弃的路径。
> 最后更新：2026-08-15（治理后）

---

## 一、单一事实源（一切以这里为准）

| 事项 | 唯一权威位置 | 说明 |
|------|-------------|------|
| **数据唯一事实源** | `database/knowledge_base.db` | SQLite，当前 1394 篇（国内428/国际966） |
| **权威静态站产物** | `web/static_site/` | `build_static_site.py` 生成，含 research_map.html |
| **本地→线上部署** | `scripts/update_github_pages.py` | Contents API，真实推送 |
| **一键部署入口** | `bash scripts/sync_github_pages.sh` | 凭证校验 + 调 update_github_pages.py |
| **真实调度入口** | `scripts/daemon_scheduler.py` | 常驻守护，PM2/start.sh 启动 |
| **部署参数固化** | `docs/DEPLOY_PARAMS_FROZEN.md` | 仓库/IP/凭证/同步记录权威版 |
| **运维技能固化** | `docs/RUNBOOK.md` | 已验证的命令与踩坑 |
| **线上站点** | `https://justadreamer2024.github.io/sports-journalism-kb/` | GitHub Pages |

---

## 二、GitHub 部署（最易"遗忘"的操作）

### 核心参数
- 仓库：`justadreamer2024/sports-journalism-kb`（main 分支，公开）
- Pages：`https://justadreamer2024.github.io/sports-journalism-kb/`
- api.github.com 真实IP：`140.82.112.6`（用 `--resolve` 绕过沙箱 DNS 劫持）
- github.io CDN IP：`185.199.108.153`（用 `--resolve` 访问线上）
- 有效凭证：`~/.git-credentials`（`用户名:token` 格式），认证用 `-u "用户名:token"`，**不是** Bearer

### 如何部署（唯一正确方式）
```bash
cd /workspace/sports-journalism-kb
bash scripts/sync_github_pages.sh
# 或: python3 scripts/update_github_pages.py
```

### 防遗忘关键点（本次治理确认）
- ✅ **`deploy_github.sh` 已废弃**（指向旧 web/public 249条，归档到 archive/）
- ✅ **线上根目录**存 `data.json`/`index.html`（**不是** `site/` 子目录）
- ✅ GHA 脚本 `SITE_DIR = REPO_ROOT`（已修正），workflow `git add data.json index.html`
- ⚠️ 硬编码 token（ghp_ 开头）已失效，统一走 `~/.git-credentials` store 凭证

---

## 三、定期任务（调度器内置，无需 cron）

由 `daemon_scheduler.py` 常驻守护执行：
| 任务 | 时间 | 说明 |
|------|------|------|
| 每日动态推送 | 08:00 / 20:00 | 邮件 + 微信 |
| 每周周报 | 周一 09:00 | 邮件 + 微信 |
| 本地备份 | 每6小时 | 打包到 /tmp |

> 启动：`bash start.sh` 或 `pm2 start scripts/daemon_scheduler.py`

---

## 四、已归档（勿再直接运行）⚠️

> 这些脚本已归档到 `scripts/archive/`，功能已完成或已被新脚本取代。**不要再运行它们**，避免重复或误用旧逻辑。

| 归档脚本 | 取代者/说明 |
|----------|------------|
| `deploy_github.sh` | 已被 `update_github_pages.py` / `sync_github_pages.sh` 取代 |
| `apply_abstract_cn_batch9~49.py`（41个） | 翻译已全部写入数据库 |
| `apply_abstract_cn.py`、`batch2~8` | 翻译已写入数据库 |
| `import_literature.py` | 历史导入 |
| `setup_cron.sh` | 已改用 `daemon_scheduler.py` 常驻调度 |
| `generate_worldcup_pdf.py`、`send_worldcup_pdf_email.py` | 一次性任务 |

---

## 五、过时/非权威目录（勿误用）⚠️

| 目录 | 内容 | 为什么不能当权威 |
|------|------|-----------------|
| `web/public/` | 管理界面前端 | 非静态站部署源（当年 `deploy_github.sh` 误用对象） |
| `github_actions/site/` | 217条旧快照 | 已过时，GHA 脚本已改指向根目录 |
| `deploy_package/site/` | 217条旧快照 | 一次性交付包 |

---

## 六、待办 / 已知状态

- ✅ **翻译覆盖**：91.0%（1111/1221）——README 与数据库一致
- 🔄 **任务#118**：补齐缺失的 abstract/keywords 字段（keywords 缺口762篇，因 Crossref 429 限流暂停）
- ℹ️ **GHA 管线定位**：云端每周自动抓取 Crossref 增量，独立维护线上站点（不回写本地库）；本地仍是权威数据源

---

## 七、遇到操作前必读（防遗忘检查单）

1. **[查这里]** 本文件是否已记录该操作？有则按权威来源做，不再重复探索。
2. **数据** 改数据→先改 `database/knowledge_base.db`（唯一事实源）。
3. **站点** 重建站点→ `python3 scripts/build_static_site.py`（产出 `web/static_site/`）。
4. **部署** 同步线上→ `bash scripts/sync_github_pages.sh`。
5. **勿动** 归档脚本 / 非权威目录（见四、五）。
6. **文档** 更新参数/操作→同步更新 `docs/DEPLOY_PARAMS_FROZEN.md` 和本文件。

---

*本文件是防遗忘主索引，改动任何参数/路径/权威来源时务必同步更新。*
