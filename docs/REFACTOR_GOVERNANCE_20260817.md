# 🛠️ 系统性治理报告（2026-08-17）

> 响应 owner 请求："全面回顾和梳理现有的代码和功能，力求数据统一、信息一致、功能不冲突，然后将一些好的功能和方法固化为技能保存下来，参数也固化下来以便各功能调用。"
> 治理日期：2026-08-17 ｜ 状态：✅ 完成

---

## 一、治理目标与成果一览

| 目标 | 完成情况 |
|------|---------|
| **全面梳理代码/功能** | ✅ 盘点 36 个顶层脚本 + archive 71 个脚本，输出完整功能清单 |
| **功能不冲突** | ✅ 归档 6 个过时/重复脚本、删除 1 个重复脚本、归档 1 个历史残留目录 |
| **数据统一** | ✅ 数据库(12106) = 部署包 = 云端一致；README 统计修正 |
| **信息一致** | ✅ 修复 README 过时统计(1687→12106)、修正文档漂移、一致性校验全通过 |
| **固化技能** | ✅ 新增 `docs/COLLECTION_SKILLS_FROZEN.md`（3条采集链路方法固化） |
| **固化参数** | ✅ 新增 `config/parameters.json` + `docs/PARAMS_FROZEN.md` + `scripts/kb_params.py` |

---

## 二、代码/功能梳理（脚本清单）

**顶层 30 个在用 .py（治理后）**：

| 类别 | 脚本 |
|------|------|
| 采集类(6) | fetch_incremental / fetch_ncpssd_whitelist / fetch_tykx_official / fetch_theme_weakspots / maintain_whitelist |
| 清理质量(7) | clean_ncpssd_news / clean_theme_weakspots / fill_missing_fields / extract_keywords / extract_keywords_cn / data_governance / consistency_check |
| 构建部署(8) | build_static_site / build_research_map / build_research_map_data / build_paper / build_deploy_package / update_github_pages / push_db_to_github / sync_github_pages.sh / sync_to_cloud.sh |
| 调度推送(7) | scheduler / cloud_runner / email_sender / wechat_pusher / generate_weekly / translate_pending / translate_docs |
| 底座/其他(4) | db_manager / env_config / kb_params / research_brain |

---

## 三、功能去重（消除冲突）

### 3.1 归档到 `scripts/archive/`（6个）
| 脚本 | 原因 |
|------|------|
| `daemon_scheduler.py` | 被 `cloud_runner.py`（云端权威）取代，避免本地/云端并发重复抓取推送 |
| `push_repo.py` | 一次性初始部署 |
| `setup_cloud.py` | 一次性云端初始化 |
| `run_abstract_backfill_loop.py` | 历史补摘要接力任务 |
| `run_backfill_after_batchA.py` | 历史补摘要接力任务 |
| `cleanup_shell_noise.py` | 固定12条空壳噪声的一次性清理 |

### 3.2 删除（1个）
| 脚本 | 原因 |
|------|------|
| `apply_abstract_cn_batch56.py` | 与 `archive/apply_abstract_cn_batch56.py` 完全重复 |

### 3.3 归档历史残留目录（1个）
| 目录 | 原因 |
|------|------|
| `github_actions/` → `archive/github_actions_legacy/` | 含旧 `auto_fetch.py`（PER_QUERY=20，词表与现行漂移）和 217 条旧快照；现行云端统一走 `cloud_runner.py` |

### 3.4 职责边界澄清（无需改代码的"伪冲突"）
| 事项 | 说明 |
|------|------|
| 两套 `send_email` | `scheduler.send_email()`（写 email_logs，简单文本）与 `email_sender.send_email()`（支持 HTML/附件）为**明确分工**；`weekly_summary()` 只生成数据不发信，`generate_weekly.py` 不会重复发信 |
| 调度器 | 统一到 `cloud_runner.py`（云端权威） |

---

## 四、参数固化（核心成果）⭐

### 4.1 新建 `config/parameters.json`（机器可读单一事实源）
集中固化：
- **检索参数**：PER_QUERY=25 / MIN_YEAR=2010 / MAILTO / THEME_START_YEAR=2010 / THEME_PER_THEME=60
- **增量检索词**：EN_QUERIES(8) / CN_QUERIES(6)
- **质量过滤词表**：SPORT_TOKENS(40) / MEDIA_TOKENS(72) / CORE_TERMS(16) / ESPORTS_TOKENS(4) / HARD_BLACKLIST(59)
- **分类规则**：RULES(13类)
- **主题弱项**：THEME_QUERIES(5主题×9词) / THEME_CATEGORY
- **国内期刊过滤词**：SPORT_WORDS(152) / PURE_SPORT_KEYWORDS / NEWS_SOURCES(10)
- **主题清理噪声**：HARD_NOISE(20)
- **期刊映射**：JOURNAL_GCH(32本)
- **调度cron**：cloud_scheduler.yml 7条

### 4.2 新建 `scripts/kb_params.py`（加载模块）
`from kb_params import SPORT_TOKENS, RULES, ...` 供各脚本 import，**单一事实源**。

### 4.3 新建 `docs/PARAMS_FROZEN.md`（人类可读权威版）
含全部参数对照 + 职责边界 + 调度表 + 维护红线。

> ✅ **已校验**：`kb_params.py` 加载的 20 项词表/参数与 `fetch_incremental`/`fetch_ncpssd_whitelist`/`fetch_theme_weakspots`/`clean_theme_weakspots` 逐项比对**完全一致**，无漂移。

---

## 五、技能固化（核心成果）⭐

### 5.1 新建 `docs/COLLECTION_SKILLS_FROZEN.md`
仿照 `TRANSLATION_SKILL_FROZEN.md` 模式，固化三条已验证采集链路：
- **L1 · NCPSSD 白名单采集**（`fetch_ncpssd_whitelist.py`）：能力/运行方式/断点续抓/故障排查
- **L2 · 体育科学官网采集**（`fetch_tykx_official.py`）：Playwright+requests 混合模式，方法论可复用到其他期刊官网
- **L3 · 主题弱项定向采集**（`fetch_theme_weakspots.py` + `clean_theme_weakspots.py`）：质量红线/清理原则
- 附采集后标准化动作（同步三处 + 重建站点 + 翻译队列）+ 待拓展方向

### 5.2 既有固化文档
- `docs/DEPLOY_PARAMS_FROZEN.md`（修正 Workflow 漂移）
- `docs/TRANSLATION_SKILL_FROZEN.md`
- `docs/RUNBOOK.md`

---

## 六、数据/信息一致性（核心成果）⭐

| 修复项 | 修复前 | 修复后 |
|--------|--------|--------|
| README 总文献数 | 1687 篇 | **12106 篇**（国内10254/国际1852） |
| README 国内/国际 | 435/1252 | **10254/1852** |
| README 翻译/关键词覆盖 | 过时(71.3%/99.4%) | **20.9%(2420/11561) / 22.7%(2743/12106)** |
| README 架构描述 | daemon_scheduler 常驻(已废弃) | **cloud_runner 云端权威 + kb_params 统一参数** |
| 硬编码绝对路径 | extract_keywords/extract_keywords_cn/fill_missing_fields/update_github_pages 用 `/workspace/...` | **统一走 `env_config.DB_PATH`/`STATIC_SITE`（可移植）** |
| 文档漂移 | DEPLOY_PARAMS_FROZEN 引用废弃 weekly_update.yml | **修正为 cloud_scheduler.yml** |
| consistency_check | 报 daemon_scheduler 缺失、检查旧 github_actions | **全部更新，主库校验通过** |

**三处同步**：主库 `sports-journalism-kb/` = 部署包 `sports-kb-local-deploy/`（scripts/config/docs 已对齐）| 云端 GitHub 数据库已同步（commit fdba647）。

---

## 七、一致性校验（最终通过 ✅）

```
✅ 核心权威路径全部存在（18 项）
✅ 数据库: 总 12106（国内10254/国际1852）| 翻译覆盖 20.9%（2420/11561）
✅ 无废弃脚本残留
✅ 旧 github_actions/ 目录已归档
✅ cloud_scheduler.yml 正确（调用 cloud_runner.py）
✅ 校验全部通过，项目状态一致
```

---

## 八、存量待办（治理后遗留，供后续推进）

1. **翻译队列**：550 篇主题弱项国际文献（pending_translate）+ 其他待译，受百度免费额度限制（2026-08 已用尽，9 月重置后续译）。
2. **其余核心期刊官网渠道**：体育教育学刊、现代传播、新闻记者、新闻与写作（可复用 L2 官网模式，调研见 `docs/journal_official_websites_free_access_20260816.md`）。
3. **题录补全**：体育文化导刊 2018-2024、武汉体院 2020-2025、体育与科学 2019-2025。
4. **新增弱项主题**：可在 `config/parameters.json` 的 `THEME_QUERIES` 增词后跑 L3。
5. **基于主题弱项数据生成论文**：`build_paper.py` 可基于知识库自动生成综述初稿。

---

*本报告为 2026-08-17 系统性治理的完整记录，供 owner 复核。*
