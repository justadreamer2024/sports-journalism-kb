# 🔒 项目参数固化表（权威版）

> 体育新闻研究知识库 · 全部核心参数的权威定义
> 固化日期：2026-08-17 ｜ 最后复核：2026-08-17 ｜ 状态：✅ 与现有脚本逐项校验一致

本文件固化本项目**全部需跨功能复用的参数**（词表、检索参数、主题、期刊、路径、调度、职责边界）。**改任何参数前先查本文件**；参数的实际权威载体是 `config/parameters.json`（机器可读），本文件为人类可读对照版。

---

## 一、单一事实源（参数以哪里为准）

| 事项 | 权威位置 | 加载方式 | 说明 |
|------|---------|---------|------|
| **全部采集/过滤词表 + 检索参数 + 主题 + 期刊映射** | `config/parameters.json` | `scripts/kb_params.py`（`from kb_params import ...`） | **机器可读唯一权威源**，2026-08-17 建立并经校验与脚本完全一致 |
| 路径（PROJECT_ROOT/DB/STATIC_SITE） | `scripts/env_config.py` | `from env_config import PROJECT_ROOT, DB_PATH` | 自动探测，环境变量 `PROJECT_ROOT` 可覆盖 |
| 数据库连接 | `scripts/db_manager.py` | `get_db()` | 全库共用 DB 入口 |
| 期刊白名单资源库 | `config/journal_whitelist.json` | 各维护脚本 | 含免费渠道/采集方式/状态 |
| 翻译配置与免费额度 | `config/translate_config.json` | `scripts/translate_pending.py` | 详见 `docs/TRANSLATION_SKILL_FROZEN.md` |
| 邮件/微信/部署凭证 | `config/email_config.json` / `wechat_config.json` / `DEPLOY_KEYS.json` | `scripts/env_config.py` / 云端 Secrets | 云端用 GitHub Secrets 注入 |
| 调度 cron | `.github/workflows/cloud_scheduler.yml` | GitHub Actions | 唯一权威调度入口 |

---

## 二、路径与数据库参数

| 参数 | 值 | 权威定义 |
|------|-----|---------|
| 项目根 `PROJECT_ROOT` | 自动探测（`scripts/env_config.py`），环境变量可覆盖 | `env_config.detect_root()` |
| 数据库 `DB_PATH` | `database/knowledge_base.db` | `env_config.DB_PATH` |
| 静态站 `STATIC_SITE` | `web/static_site` | `env_config.STATIC_SITE` |
| 配置目录 `CONFIG_DIR` | `config/` | `env_config.CONFIG_DIR` |
| 增量游标 `fetch_state.json` | `config/fetch_state.json` | `fetch_incremental` |
| NCPSSD 进度 `ncpssd_fetch_state.json` | `config/ncpssd_fetch_state.json` | `fetch_ncpssd_whitelist` |
| 期刊白名单 `journal_whitelist.json` | `config/journal_whitelist.json` | 白名单维护 |

> ⚠️ **迁移建议**：仍有少数脚本（`extract_keywords*.py`、`fill_missing_fields.py` 等）硬编码 `/workspace/...` 绝对路径。云端 Actions 工作目录非 `/workspace`，新脚本一律用 `env_config`/`kb_params`；存量脚本逐步迁移，迁移前已评估：`fetch_incremental.py` 相对调用 `extract_keywords.py` 在云端可能失败，**已列入待办**。

---

## 三、检索参数（权威定义 `config/parameters.json` → `检索参数`）

| 参数 | 值 | 含义 |
|------|-----|------|
| `PER_QUERY` | 25 | 每源每查询最多条数 |
| `MAILTO` | `research@example.com` | Crossref 礼貌请求标识 |
| `MIN_YEAR` | 2010 | 增量年份下限兜底 |
| `THEME_START_YEAR` | 2010 | 主题弱项回溯起始年份 |
| `THEME_PER_THEME` | 60 | 每主题每源最多条数 |

---

## 四、增量检索词（`config/parameters.json` → `增量检索词`）

**`EN_QUERIES`**（8 条）：
`sports journalism` / `sports media` / `sport communication` / `sports reporting` / `sports news` / `sports broadcasting` / `sports digital media` / `esports journalism`

**`CN_QUERIES`**（6 条）：
`体育新闻` / `体育传播` / `体育媒体` / `体育报道` / `体育转播` / `电子竞技 新闻`

---

## 五、质量过滤词表（`config/parameters.json` → `质量过滤词表`）

> 这三套词表是"体育新闻类"质量红线，`fetch_incremental.passes_filter()` 的判定逻辑：
> 1) 标题命中 `HARD_BLACKLIST` → 剔除；2) 命中 `CORE_TERMS` → 通过；
> 3) 命中 `ESPORTS_TOKENS` → 通过；4) `SPORT_TOKENS`(体育域) ∩ `MEDIA_TOKENS`(媒体域) 双命中 → 通过。

| 词表 | 词数 | 说明 |
|------|------|------|
| `SPORT_TOKENS` | 40 | 体育域词（中英混合），任一命中即视为"体育"域 |
| `MEDIA_TOKENS` | 72 | 媒体/传播/报道/产业域词 |
| `CORE_TERMS` | 16 | 复合核心词（天然体育+新闻，直接通过） |
| `ESPORTS_TOKENS` | 4 | 电竞研究整体在域内 |
| `HARD_BLACKLIST` | 59 | 标题命中即剔除（运动医学/生理/无关商业等） |

**分类规则 `RULES`（13 类）**：电竞新闻 / 体育与性别 / 体育与政治 / 体育与新媒体 / 体育国际传播 / 体育媒体产业 / 体育新闻与技术 / 体育新闻伦理 / 体育新闻受众 / 体育新闻史 / 体育新闻教育 / 体育新闻理论 / 体育新闻实务（每类含中英文触发词）。

---

## 六、国内期刊过滤词（`config/parameters.json` → `国内期刊过滤词`）

> 用于 NCPSSD 链路（L1）：纯体育类期刊整本收录不过滤；**新闻传播类期刊**（`NEWS_SOURCES`）须按 `SPORT_WORDS` 过滤。

| 词表 | 词数 | 说明 |
|------|------|------|
| `SPORT_WORDS` | 152 | 中文体育相关词（领域/赛事/项目/产业/媒体场景） |
| `PURE_SPORT_KEYWORDS` | 5 | 纯体育类期刊整本收录 |
| `NEWS_SOURCES` | 10 | 需过滤的新闻传播类来源（中国记者/新闻界/国际新闻界/新闻与传播研究/青年记者/未来传播/科技传播/艺术传播研究/记者摇篮/新闻战线） |

---

## 七、主题弱项（`config/parameters.json` → `主题弱项`）

**`THEME_QUERIES`（5 主题 × 9 检索词）**：

| 主题 | 检索词数 | 中英文检索词（节选） |
|------|---------|---------------------|
| 体育与性别 | 9 | gender in sports media / women in sports journalism / female athletes media representation / ... / 体育 性别 媒体 / 体育 女性 传播 |
| 电竞新闻 | 9 | esports journalism / esports media coverage / esports broadcasting / ... / 电竞 新闻 / 电子竞技 报道 |
| 体育新闻与技术 | 9 | AI sports journalism / automated sports news / algorithm sports media / ... / 体育新闻 人工智能 / 体育 算法 传播 |
| 体育新闻伦理 | 9 | sports journalism ethics / sports media ethics / journalistic objectivity sports / ... / 体育新闻 伦理 / 体育媒体 失范 |
| 体育国际传播 | 9 | sports diplomacy international / sports soft power media / international sports communication / ... / 体育 国际传播 / 体育 对外传播 |

**`THEME_CATEGORY`**：主题 → 分类标签一一对应（同主题名）。

**主题清理噪声 `HARD_NOISE`（20 词）**：只剔强噪声（材料/化学/医学/金融等明显非体育研究）；**不做主题词强约束**，避免误删实际相关的体育媒体/传播研究。

---

## 八、期刊映射（`config/parameters.json` → `期刊映射`）

**`JOURNAL_GCH`（32 本期刊 → [gch, ISSN, CN, 类别]）**：
- **CSSCI 体育学来源刊**：中国体育科技 / 北京体育大学学报 / 武汉体育学院学报 / 天津体育学院学报 / 西安体育学院学报 / 首都体育学院学报 / 体育与科学 / 山东体育学院学报
- **体育文化专门**：体育文化导刊
- **体育学相关**：体育科学研究 / 四川体育科学 / 浙江体育科学 / 哈尔滨体育学院学报 / 当代体育科技 / 体育科研 / 体育科技文献通报 / 体育教育学刊 / 体育函授通讯 / 体育师友 / 体育研究与教育 / 青少年体育 / 运动精品
- **国际体育期刊**：运动与健康科学（英文）
- **新闻传播（需过滤）**：新闻与传播研究 / 国际新闻界 / 新闻界 / 青年记者 / 未来传播 / 科技传播 / 艺术传播研究 / 记者摇篮 / 中国记者

> 完整 gch/ISSN/CN 详见 `config/parameters.json`。⚠️ 该表与 `config/journal_whitelist.json` 的 `NCPSSD_gch` 字段语义重叠（32 本 vs 白名单 24 本），**以 `parameters.json` 的 `JOURNAL_GCH` 为采集执行权威**，白名单 json 为资源库权威。

---

## 九、职责边界（消除"功能冲突"误解）⭐

> 审计发现以下"疑似冲突"，经确认**均为明确分工，无需改动代码**，在此固化职责边界：

| 事项 | 实现 A | 实现 B | 职责边界 |
|------|--------|--------|---------|
| **邮件发送** | `scheduler.send_email()` | `email_sender.send_email()` | A 用于每日动态/周报，写 `email_logs` 记录（简单文本）；B 支持 HTML/附件（周报附带文件用）。`weekly_summary()` 只生成数据**不发信**，故 `generate_weekly.py` 不会重复发信 |
| **调度器** | `cloud_runner.py`（云端，权威） | `daemon_scheduler.py`（本地守护，**已归档**） | 云端 `cloud_runner.py` 是唯一权威入口；本地守护已停止并归档，避免两端并发重复抓取/推送 |
| **站点部署** | `push_db_to_github.py`（推 DB） | `update_github_pages.py`（推静态站） | 一个推数据库到仓库，一个推静态站到 Pages，职责不同，均保留 |

---

## 十、调度 cron（权威：`.github/workflows/cloud_scheduler.yml`）

| 任务 | 云端 cron (UTC) | 北京时间 | 说明 |
|------|----------------|----------|------|
| 每日动态推送 + 自检 | `0 0 * * *` / `0 12 * * *` | 08:00 / 20:00 | daily（并入 `health_check daily`） |
| 持续跟踪 | `0 19 * * *` | 03:00 | track |
| 每周周报 + 自检 | `0 1 * * 1` | 周一 09:00 | weekly（并入 `health_check weekly`） |
| 月度翻译 + 自检 | `10 1 1 * *` | 每月1日 09:10 | monthly（并入 `health_check monthly`） |
| 白名单维护 | `20 1 1 * *` | 每月1日 09:20 | whitelist |
| NCPSSD 采集 | `30 1 * * 3` | 每周三 09:30 | ncpssd |
| DB 备份 | `0 */6 * * *` | 每 6 小时 | backup |

> 📌 **自检机制**：三级自检（daily 轻量/weekly 完整/monthly 深度）已并入上述 daily/weekly/monthly 任务，脚本 `scripts/health_check.py`，详见 `docs/HEALTH_CHECK.md`。**无需改 cron 配置**。

> ✅ **已修正（2026-08-17）**：`docs/DEPLOY_PARAMS_FROZEN.md` 第五节已从废弃的 `weekly_update.yml` 修正为现行权威 `cloud_scheduler.yml`。

---

## 十一、词表/参数维护红线

1. **唯一权威**：任何词表/参数修改**先改 `config/parameters.json`**，再让脚本 `from kb_params import ...` 读取，禁止在脚本内另起炉灶。
2. **校验**：改后运行 `python3 scripts/kb_params.py` 确认加载正常；如改词表，重跑 `fetch_incremental.passes_filter` 相关链路验证不过滤失真。
3. **同步文档**：本文件（人类可读版）与 `parameters.json`（机器可读版）同步更新。
4. **不擅自付费/越界**：凭证、翻译额度等敏感参数遵循既有冻结文档（`DEPLOY_PARAMS_FROZEN.md` / `TRANSLATION_SKILL_FROZEN.md`）的红线。

---

*本文档为参数的权威固化版本，如有更新请同步修改 `config/parameters.json` 并标注日期。*
