# 🗂️ 体育新闻研究知识库 — 主索引 / 单一事实源（防遗忘）

> **本文件是项目的"防遗忘主索引"**。所有固化过的操作、参数、权威来源集中于此。
> 任何后续操作**先查本文件**，避免重复做已做过的事、或误用已废弃的路径。
> 最后更新：2026-08-16（清理空壳噪声 + 翻译/同步状态核对）

---

## 一、单一事实源（一切以这里为准）

| 事项 | 唯一权威位置 | 说明 |
|------|-------------|------|
| **数据唯一事实源** | `database/knowledge_base.db` | SQLite，当前 **12249 篇**（国内10397/国际1852，含 NCPSSD 采集国内文献 + 官网直采） |
| **权威静态站产物** | `web/static_site/` | `build_static_site.py` 生成，含 research_map.html |
| **本地→线上部署** | `scripts/update_github_pages.py` | Contents API，真实推送 |
| **一键部署入口** | `bash scripts/sync_github_pages.sh` | 凭证校验 + 调 update_github_pages.py |
| **真实调度入口** | `.github/workflows/cloud_scheduler.yml` | **GitHub Actions 云端 7×24**（2026-08-16 迁移，沙箱休眠无影响） |
| **本地调度入口** | `scripts/local_scheduler.py` | **本地化部署（Windows/macOS/Linux）跨平台守护进程**，替代已归档 daemon_scheduler，任务与云端对齐并触发三级自检 |
| **部署参数固化** | `docs/DEPLOY_PARAMS_FROZEN.md` | 仓库/IP/凭证/同步记录权威版 |
| **翻译技能固化** | `docs/TRANSLATION_SKILL_FROZEN.md` | 免费额度机制/监控红线/月度调度/资源清单权威版 |
| **采集技能固化** | `docs/COLLECTION_SKILLS_FROZEN.md` | 三条采集链路（NCPSSD/体育科学官网/主题弱项）的可复用方法权威版 |
| **参数固化** | `config/parameters.json`（机器）+ `docs/PARAMS_FROZEN.md`（人类） | 全部词表/检索参数/主题/期刊映射的**单一事实源**（`scripts/kb_params.py` 加载） |
| **运维技能固化** | `docs/RUNBOOK.md` | 已验证的命令与踩坑 |
| **三级自检机制** | `scripts/health_check.py` + `docs/HEALTH_CHECK.md` | 每日/每周/每月自动自检（完整性/一致性/可用性），并入云端调度 |
| **云端调度架构** | `docs/CLOUD_SCHEDULER.md` | 守护迁云端 7×24 的方案/机制/维护 |
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

## 三、定期任务（GitHub Actions 云端 7×24，无需本地常驻）

> **2026-08-16 迁移完成**：原本地沙箱守护进程 `daemon_scheduler.py`（PID 2459860）已停止，
> 全部定时任务改由 `.github/workflows/cloud_scheduler.yml` 在 GitHub 云端运行，
> 不受沙箱休眠影响。本地代码 `scripts/daemon_scheduler.py` 仅作逻辑参考，不再常驻。

> **2026-08-17 本地部署补充**：云端用 `cloud_runner.py`；**本地化部署（Windows/macOS/Linux）用
> `scripts/local_scheduler.py`**（跨平台守护进程，日志写 `output/daemon.log`、备份写 `output/backup/`，
> 不用 `/tmp`）。它替代已归档的 `daemon_scheduler.py`，定时任务与云端对齐，并在每日/每周/月度任务
> 末尾触发 `health_check.py` 三级自检。本地 `start.bat`/`start_mac.sh`/`start.sh` 均调用 `local_scheduler.py`。

| 任务 | 云端 cron (UTC) | 北京时间 | 说明 |
|------|----------------|----------|------|
| 每日动态推送 | `0 0 * * *` / `0 12 * * *` | 08:00 / 20:00 | 邮件 + 微信（密钥来自 GitHub Secrets） |
| 持续跟踪 | `0 19 * * *` | 03:00 | 增量抓取 → 自动翻译队列 → 重建站点 → git 部署 |
| 每周周报 | `0 1 * * 1` | 周一 09:00 | 邮件 + 微信 |
| 月度翻译 | `10 1 1 * *` | 每月1日 09:10 | 百度免费额度优先翻急需 + 剩余上报 + 资源建议 |
| DB 持久化备份 | `0 */6 * * *` | 每6小时 | 把权威 DB 回写仓库 |

- **权威 DB 持久化**：`database/knowledge_base.db` 提交进仓库（云端 `git add -f` 回写），不再依赖本地文件。
- **密钥**：邮件/微信/百度 共 12 项存于仓库 **GitHub Secrets**（加密，不进公开仓库）；`scripts/cloud_runner.py` 运行时从 env 注入 `config/`。
- **手动触发**：仓库 Actions 页 → Cloud Scheduler → Run workflow → 选 `dispatch-test/daily/weekly/track/monthly/backup`。
- 详见 `docs/CLOUD_SCHEDULER.md`。

---

## 四、已归档（勿再直接运行）⚠️

> 这些脚本已归档到 `scripts/archive/`，功能已完成或已被新脚本取代。**不要再运行它们**，避免重复或误用旧逻辑。

| 归档脚本 | 取代者/说明 |
|----------|------------|
| `deploy_github.sh` | 已被 `update_github_pages.py` / `sync_github_pages.sh` 取代 |
| `apply_abstract_cn_batch9~49.py`（41个） | 翻译已全部写入数据库 |
| `apply_abstract_cn.py`、`batch2~8` | 翻译已写入数据库 |
| `import_literature.py` | 历史导入 |
| `setup_cron.sh` | 已迁移至 `.github/workflows/cloud_scheduler.yml` 云端调度 |
| `generate_worldcup_pdf.py`、`send_worldcup_pdf_email.py` | 一次性任务 |
| `daemon_scheduler.py` | **2026-08-17 归档**：被 `cloud_runner.py`（云端权威）取代，避免本地/云端并发重复抓取推送 |
| `push_repo.py`、`setup_cloud.py` | **2026-08-17 归档**：一次性初始部署/初始化脚本 |
| `run_abstract_backfill_loop.py`、`run_backfill_after_batchA.py` | **2026-08-17 归档**：历史补摘要接力任务 |
| `cleanup_shell_noise.py` | **2026-08-17 归档**：固定 12 条空壳噪声的一次性清理 |
| `apply_abstract_cn_batch56.py`（顶层） | **2026-08-17 删除**：与 `archive/apply_abstract_cn_batch56.py` 完全重复 |

---

## 五、过时/非权威目录（勿误用）⚠️

| 目录 | 内容 | 为什么不能当权威 |
|------|------|-----------------|
| `web/public/` | 管理界面前端 | 非静态站部署源（当年 `deploy_github.sh` 误用对象） |
| `github_actions/` | **2026-08-17 已整体归档**到 `scripts/archive/github_actions_legacy/` | 含旧 `auto_fetch.py`（PER_QUERY=20，与现行 fetch_incremental 漂移）与 217 条旧快照；现行云端统一走 `scripts/cloud_runner.py` |
| `deploy_package/site/` | 217条旧快照 | 一次性交付包 |

---

## 六、待办 / 已知状态

- ✅ **翻译覆盖**：77.6%（1309/1687）——据库最新（abstract_cn 非空），README 与数据库一致（2026-08-16 更新）
- ✅ **关键词覆盖**：99.4%（1677/1687）——已完成（45.3%→99.4%）
- ✅ **空壳噪声清理（2026-08-16）**：移除 12 篇运动医学刊栏目/期刊简介空壳，库 1699→1687（国内435/国际1252），见 `docs/CLEANUP_SHELL_NOISE_20260816.md`
- ⚠️ **待译队列**：363 篇英文文献（约 58,469 字符）待翻译；百度免费额度 2026-08 已用尽（剩余 0）、本月翻译暂停，待 9 月额度重置或新资源后由 `translate_pending.py` 补译（见 `docs/TRANSLATED_LITERATURE_REPORT_20260816.md`、`docs/pending_translation_list_20260816.csv`）
- ⚠️ **灰色地带**：~16 篇运动医学/生理/心理期刊论文（含"体育+媒体"词误入），待用户裁决严格度
- ✅ **GitHub Pages 线上同步：已实测跑通**（2026-08-16 多次复核）。机制为 `update_github_pages.py` 经 GitHub **Contents API** 推送（`curl --resolve api.github.com:443:140.82.112.6 -u 凭证`，凭证取自 `~/.git-credentials`），**不依赖本地 git 仓库**。本次先推送 README/index.html 成功、data.json 偶发 401 后单独重试成功（4039 KB），线上三件套齐备。
- ⚠️ 本地 `sports-journalism-kb/` 不是 git 仓库（无需是）；勿用 `git log/remote` 验证部署，应直接跑 `python3 scripts/update_github_pages.py` 或用 `curl --resolve` 查 API。
- ℹ️ **GHA 管线定位**：云端每周自动抓取 Crossref 增量，独立维护线上站点（不回写本地库）；本地仍是权威数据源
- ✅ **NCPSSD 白名单批量采集（2026-08-16 重大突破）**：打通国家哲社文献中心**免登录**采集链路（期刊列表→详情→目录→文章详情），批量采集 8 本主要体育期刊 2015-2025 全量题录，库 1687→**10475 篇**。脚本 `scripts/fetch_ncpssd_whitelist.py`。详见 `docs/ncpssd_progress_report_20260816.md`
- ✅ **NCPSSD 摘要补抓（2026-08-17 完成）**：`networkidle`→`load` 等待策略优化提速 20 倍（每篇 3.6s），自动流水线补完，论文摘要覆盖率 **99.5%**（剩余为编委会/总目次等非论文栏目）。权威库 39M 已同步部署包 + 云端 GitHub（`scripts/push_db_to_github.py`）
- ✅ **官方期刊官网免费渠道验证（2026-08-16）**：《体育科学》官网 `tykx.xml-journal.net` 免登录可采全文+摘要（服务端渲染，含 HTML 全文）；《体育学刊》官网仅目次无全文。详见 `docs/journal_official_websites_free_access_20260816.md`
- ✅ **体育科学官网采集（2026-08-17，任务1 完成）**：`scripts/fetch_tykx_official.py` 打通 NCPSSD 未收录的最核心期刊官网，采集 **1081 篇**（2015-2026 全量），含中英文摘要/作者/关键词/DOI。`collected_by='official_website'`
- ✅ **体育学刊官网采集（2026-08-17，任务2 完成）**：`scripts/fetch_tykx_scnu.py` 打通 `tyxk.scnu.edu.cn/book/` 免费全文渠道，2019-2026 扫描全量，体育新闻/传播相关入库 **143 篇**（中英标题/作者/中英摘要/关键词/PDF全文）。`data_source='tykx_scnu_official'`
- ✅ **主题弱项定向采集（2026-08-17，任务2 完成）**：`scripts/fetch_theme_weakspots.py` 补齐 5 大弱项主题国际文献 **550 篇**（性别144/电竞137/国际传播107/技术89/伦理73），较采集前提升 20-50 倍；`scripts/clean_theme_weakspots.py` 质量清理。详见 `docs/theme_weakspots_progress_20260817.md`
- ✅ **权威库同步（2026-08-17）**：总文献 **12249 篇**（国内10397/国际1852），43M 权威库已同步部署包 + 云端 GitHub，FTS 索引与主表完全同步
- ⚠️ **国内文献已补齐（NCPSSD + 官网直采）**：原短板（国内 435 篇）已大幅充实，国内文献达 10397 篇；仍有部分新闻传播类期刊（现代传播、新闻记者等）免费官网渠道有限，待走微信公众号/知网题录补充
- ✅ **系统性治理（2026-08-17）**：全面梳理代码/功能/参数，达成"数据统一、信息一致、功能不冲突"：
  - **归档去重**：6 个过时/一次性脚本归档、1 个重复脚本删除（见上文"四、已归档"），顶层 .py 36→29。
  - **参数固化**：新建 `config/parameters.json`（机器）+ `docs/PARAMS_FROZEN.md`（人类）+ `scripts/kb_params.py`（加载），全部词表/检索参数/主题/期刊映射**单一事实源**，已逐项校验与现有脚本完全一致。
  - **采集技能固化**：新建 `docs/COLLECTION_SKILLS_FROZEN.md`，三条采集链路（NCPSSD/体育科学官网/主题弱项）方法固化，可随时复跑。
  - **职责边界澄清**：两套 `send_email` 为明确分工非冲突；调度器统一到 `cloud_runner.py`（云端权威）。
- ⚠️ **存量待办（治理后遗留）**：① 部分脚本仍硬编码 `/workspace` 绝对路径（`extract_keywords*.py`/`fill_missing_fields.py` 等），云端 Actions 可能失败，待迁移到 `env_config`/`kb_params`。
  - ✅ **② 已解决（2026-08-17）**：`docs/DEPLOY_PARAMS_FROZEN.md` 已修正为现行 `cloud_scheduler.yml`。
  - ✅ **③ 已解决（2026-08-17）**：`github_actions/` 旧目录已整体归档到 `scripts/archive/github_actions_legacy/`。
- ✅ **三级自检机制（2026-08-17 建立）**：`scripts/health_check.py` 实现每日(轻量)/每周(完整)/每月(深度)三级自检，**并入** `cloud_runner.py` 的 daily/weekly/monthly（不新增 job），异常自动告警+安全项自动修复。详见 `docs/HEALTH_CHECK.md`。当前系统实测全部通过（DB完整性ok、FTS同步12106/12106、无参数漂移、文档一致）。

---

## 七、遇到操作前必读（防遗忘检查单）

1. **[查这里]** 本文件是否已记录该操作？有则按权威来源做，不再重复探索。
2. **数据** 改数据→先改 `database/knowledge_base.db`（唯一事实源）。
3. **站点** 重建站点→ `python3 scripts/build_static_site.py`（产出 `web/static_site/`）。
4. **部署** 同步线上→ `bash scripts/sync_github_pages.sh`。
5. **采集** 新增采集→按 `docs/COLLECTION_SKILLS_FROZEN.md` 走对应链路（NCPSSD/官网/主题弱项），勿重新探索。
6. **改参数** 改词表/检索/主题/期刊→**先改 `config/parameters.json`**，再 `python3 scripts/kb_params.py` 验证，新脚本一律 `from kb_params import ...`（勿在脚本内另起词表）。
7. **勿动** 归档脚本 / 非权威目录（见四、五）。
8. **文档** 更新参数/操作→同步更新 `docs/PARAMS_FROZEN.md`、`docs/DEPLOY_PARAMS_FROZEN.md` 和本文件。

---

*本文件是防遗忘主索引，改动任何参数/路径/权威来源时务必同步更新。*
