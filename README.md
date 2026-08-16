# 🏅 体育新闻研究知识库

> Sports Journalism Research Knowledge Base  
> 多语种 · 全年代 · 数据库驱动 · 动态跟踪

---

## 📊 项目概况

| 维度 | 数据 |
|------|------|
| **总文献数** | 12249 篇（经多源增量抓取 + NCPSSD 白名单 + 官网直采 + 主题弱项补强） |
| **国内文献** | 10397 篇（NCPSSD + 体育科学/体育学刊官网为主源） |
| **国际文献** | 1852 篇（含 Crossref / OpenAlex 抓取） |
| **核心学者** | 12 位（scholars表） |
| **涵盖语种** | 11 种（中/英/德/法/日/西/韩/葡/瑞/匈等） |
| **研究分类** | 15 个一级分类（分类规则见 `config/parameters.json`） |
| **摘要覆盖** | 95.4%（11688/12249 有摘要） |
| **翻译覆盖** | 中文摘要 2547 篇（占国际文献中需译部分；百度免费额度 2026-08 已用尽，9 月重置后续译） |
| **关键词覆盖** | 23.4%（2867/12249） |
| **数据库类型** | SQLite + FTS5全文搜索 |
| **管理界面** | Web应用（FastAPI + 静态前端） |
| **云备份** | 云端 GitHub Actions 7×24 + DB 持久化 |
| **定时任务** | 云端每日动态 + 持续跟踪 + 每周摘要 + 月度翻译 + DB备份 + **三级自检** |

## 📁 项目结构

> 2026-08-15 治理后统一：**`database/knowledge_base.db` 是唯一数据源，`web/static_site/` 是唯一权威静态站**。

```
sports-journalism-kb/
├── database/               # 数据库（唯一权威数据源，1687篇）
│   ├── schema.sql          # 数据库Schema
│   └── knowledge_base.db   # SQLite数据库文件
├── data/
│   ├── raw/                # 原始文献数据（Markdown）
│   │   ├── international_literature.md  # 国际文献汇编
│   │   └── domestic_literature.md       # 国内文献汇编
│   └── processed/          # 处理后数据
├── web/                    # Web管理界面 + 权威静态站
│   ├── api/server.py       # FastAPI后端
│   ├── public/             # 管理界面前端（非部署站，勿误用）
│   └── static_site/        # ⭐唯一权威静态站（部署来源）
├── scripts/                # 工具脚本
│   ├── db_manager.py       # 数据库管理（基础依赖层）
│   ├── scheduler.py        # 调度逻辑库（任务集）
│   ├── cloud_runner.py     # ⭐云端调度入口（GitHub Actions 调用）
│   ├── local_scheduler.py  # ⭐本地调度守护进程（Windows/macOS/Linux 跨平台，含三级自检）
│   ├── kb_params.py        # ⭐统一参数加载（config/parameters.json 单一事实源）
│   ├── env_config.py       # 统一路径/凭据管理（可移植）
│   ├── fetch_incremental.py# 多源增量抓取（Crossref+OpenAlex，质量红线权威）
│   ├── fetch_ncpssd_whitelist.py  # NCPSSD 白名单批量采集（国内）
│   ├── fetch_tykx_official.py     # 体育科学官网采集
│   ├── fetch_theme_weakspots.py   # 主题弱项定向采集（国际补强）
│   ├── build_static_site.py# 重建权威静态站
│   ├── update_github_pages.py  # ⭐本地→线上部署（Contents API）
│   ├── sync_github_pages.sh    # 一键部署包装脚本
│   ├── email_sender.py     # 邮件发送模块
│   ├── wechat_pusher.py    # 微信推送模块
│   └── archive/            # 已归档的一次性脚本（勿直接运行）
├── .github/workflows/cloud_scheduler.yml  # ⭐云端调度（唯一权威，7×24）
├── config/                 # 配置
│   ├── parameters.json     # ⭐统一参数/词表/主题/期刊（单一事实源）
│   ├── journal_whitelist.json   # 期刊白名单资源库
│   ├── email_config.json / wechat_config.json / translate_config.json
│   └── ...
├── output/                 # 产出
│   ├── weekly/             # 每周摘要
│   ├── reports/            # 研究报告
│   └── translations/       # 翻译文件
├── docs/                   # 文档
│   ├── DEPLOY_PARAMS_FROZEN.md   # ⭐部署参数固化（权威）
│   ├── PARAMS_FROZEN.md          # ⭐全项目参数固化（权威）
│   ├── COLLECTION_SKILLS_FROZEN.md # ⭐采集技能固化（权威）
│   ├── TRANSLATION_SKILL_FROZEN.md # ⭐翻译技能固化（权威）
│   ├── RUNBOOK.md               # 运维手册
│   └── ...
└── README.md
```

> ⚠️ **防遗忘要点**：部署统一走 `scripts/update_github_pages.py`（一键：`bash scripts/sync_github_pages.sh`）。
> 旧脚本 `deploy_github.sh`、`import_literature.py`、`setup_cron.sh`、`daemon_scheduler.py`、55个 `apply_abstract_cn_batch*.py` 等均已归档到 `scripts/archive/`，**请勿再直接运行**。改参数先改 `config/parameters.json`。

## 🚀 快速启动

### 1. 启动API服务器
```bash
cd sports-journalism-kb
python3.11 web/api/server.py
# 访问 http://localhost:8765
```

### 2. 生成每周摘要
```bash
python3.11 scripts/generate_weekly.py
```

### 3. 部署到 GitHub Pages
```bash
bash scripts/sync_github_pages.sh
# 或: python3 scripts/update_github_pages.py
```

### 4. 采集/翻译/部署（按需）
```bash
# 新增采集（详见 docs/COLLECTION_SKILLS_FROZEN.md）
python3 scripts/fetch_ncpssd_whitelist.py      # NCPSSD 白名单
python3 scripts/fetch_tykx_official.py          # 体育科学官网
python3 scripts/fetch_theme_weakspots.py        # 主题弱项
# 翻译待译队列（受免费额度监控）
python3 scripts/translate_pending.py
```

### 5. 定时调度（云端 7×24，无需本地常驻）
```bash
# 全部定时任务由 GitHub Actions .github/workflows/cloud_scheduler.yml 在云端运行
# 本地沙箱休眠不影响；手动触发：仓库 Actions → Cloud Scheduler → Run workflow
```

## 🔬 核心研究主题

| 主题 | 热度 | 说明 |
|------|------|------|
| AI与体育新闻 | ⭐⭐⭐⭐⭐ | AI写作、自动化报道、LLM影响 |
| 体育国际传播话语权 | ⭐⭐⭐⭐⭐ | 中国话语体系、文化折扣 |
| 社交媒体体育新闻 | ⭐⭐⭐⭐ | TikTok/短视频、运动员自媒体 |
| 女性体育报道 | ⭐⭐⭐⭐ | 性别平等、刻板印象 |
| 新质生产力与体育 | ⭐⭐⭐⭐ | 产业数字化、媒体转型 |
| 电竞新闻与传播 | ⭐⭐⭐ | 报道规范、与传统比较 |

## 📧 定时推送（云端 `cloud_scheduler.yml` 7×24 调度，详见 `docs/CLOUD_SCHEDULER.md`）

- **每日 08:00 / 20:00**: 研究动态邮件 + 微信 + 每日自检（异常才告警）
- **持续跟踪 03:00**: 增量抓取 → 翻译队列 → 重建站点 → 部署
- **每周一 09:00**: 周报摘要 + 每周健康自检摘要
- **每月 1 日**: 月度翻译 + 月度深度自检 + 白名单维护
- **每周三 09:30**: NCPSSD 白名单采集
- **每 6 小时**: DB 持久化备份（云端回写仓库）

> 🩺 **三级自检**：`scripts/health_check.py` 每日/每周/每月自动检查系统完整性/一致性/可用性（详见 `docs/HEALTH_CHECK.md`），异常自动告警并修复安全项。

## 🔐 部署与安全说明

- GitHub Pages 线上站点：`https://justadreamer2024.github.io/sports-journalism-kb/`（仓库当前为**公开**）
- 部署方式：`bash scripts/sync_github_pages.sh`（详见 `docs/DEPLOY_PARAMS_FROZEN.md`）
- 数据权威来源：`database/knowledge_base.db`
- API 需要密码认证（待配置）

---

*项目启动: 2026-08-11 | 持续更新中*
