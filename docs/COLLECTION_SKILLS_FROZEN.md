# 🎯 文献采集技能固化手册（FROZEN）

> 体育新闻研究知识库 · 国内/国际文献采集链路
> 固化日期：2026-08-17 ｜ 最后复核：2026-08-17 ｜ 状态：**三链路已验证，可随时复跑**

本手册固化本项目**已验证可用的全部文献采集方法**，作为后续每次采集的权威依据。**新采集任务先查本文件**，按对应链路直接调用，避免重复探索、避免用错脚本、避免破坏既有数据。

> ⚠️ 修改本文件或底层采集脚本前，先征得项目 owner 确认；修改词表/参数请走 `config/parameters.json` 单一事实源（详见 `docs/PARAMS_FROZEN.md`）。

---

## 一、总览：三条采集链路（互不冲突，分工明确）

| 链路 | 主脚本 | 数据源 | 覆盖范围 | collected_by | 状态 |
|------|--------|--------|----------|--------------|------|
| **L1 · NCPSSD 白名单** | `fetch_ncpssd_whitelist.py` | 国家哲社文献中心（免登录） | 国内 32 本白名单期刊题录+摘要 | `ncpssd` | ✅ 已跑通全量 |
| **L2 · 体育科学官网** | `fetch_tykx_official.py` | 《体育科学》官网 `tykx.xml-journal.net`（免登录） | 体育科学 2015-2026 全量 | `official_website` | ✅ 已跑通全量 |
| **L3 · 主题弱项定向** | `fetch_theme_weakspots.py` + `clean_theme_weakspots.py` | Crossref / OpenAlex | 5 大弱项主题国际文献回溯 | `theme_weakspot` | ✅ 已跑通全量 |

> 另有 **L0 · 持续增量**（`fetch_incremental.py`，Crossref/OpenAlex 按游标增量，供云端每日跟踪）——属于"常规跟踪"而非"补强采集"，本手册聚焦 L1-L3 三条主动补强链路。

---

## 二、L1 · NCPSSD 白名单采集（国内核心期刊）

### 2.1 能力
- 打通国家哲社文献中心**免登录**采集链路：期刊列表 → 详情 → 目录 → 文章详情。
- 批量采集白名单 32 本期刊（体育学核心 + 新闻传播类含体育论文）题录 + 摘要。
- 内置**体育相关性过滤**（`SPORT_WORDS`，纯体育刊整本收、新闻传播刊按标题过滤）。

### 2.2 运行方式（`scripts/fetch_ncpssd_whitelist.py`）
```bash
# 抓默认范围（最近 2 年白名单全部期刊）
python3.11 scripts/fetch_ncpssd_whitelist.py

# 指定年份范围
python3.11 scripts/fetch_ncpssd_whitelist.py --years 2018 2026

# 只抓指定期刊
python3.11 scripts/fetch_ncpssd_whitelist.py --journals 体育文化导刊,中国体育科技

# 抓取文章详情摘要（需渲染，较慢）
python3.11 scripts/fetch_ncpssd_whitelist.py --abstract

# 摘要补抓：只补缺摘要的 N 篇（N 为该批最多补抓数）
python3.11 scripts/fetch_ncpssd_whitelist.py --abstract-backfill 100

# 只统计不写库
python3.11 scripts/fetch_ncpssd_whitelist.py --dry-run
```

### 2.3 关键参数（权威定义见 `config/parameters.json`）
- 期刊→(gch, ISSN, CN, 类别)：内置 `JOURNAL_GCH`（32 本），或 `--discover` 动态发现。
- 过滤词：`SPORT_WORDS`（中文体育相关 152 词）、`NEWS_SOURCES`（需过滤的新闻传播刊）。

### 2.4 质量红线
- **纯体育类期刊**（体育文化导刊、各体育学院学报等）整本皆为体育内容，**不过滤**。
- **新闻传播类期刊**（中国记者/新闻界/国际新闻界/新闻与传播研究等）仅部分文章与体育相关，**必须按标题关键词筛选**，剔除与体育无关文献。
- 采集约束：仅从免费公开渠道采集**元数据+摘要**，不复制全文、不碰商业付费库（知网/万方/维普付费部分）、不侵权。

### 2.5 断点续抓
- 进度存于 `config/ncpssd_fetch_state.json`（`toc_done`：`刊名|gch|年|期` → 该期已采篇数/新增）。中断后重跑**自动跳过已完成期次**。
- `toc_skip` 记录跳过的期次（如空期、500 错误）。

### 2.6 故障排查
| 现象 | 原因 | 处理 |
|------|------|------|
| 目录页抓 0 篇 | 文章列表 JS 异步渲染，requests 抓不到 | 用 Playwright（`--force-js` 或默认 JS 渲染） |
| 单篇 500 错误 | 个别文章服务器端异常 | 非代码问题，重跑该期即可 |
| 摘要抓不到 | 等待策略不足 | 采用 `wait_until='load'` + 600ms（每篇约 3.6s，比 networkidle 快 20 倍） |

---

## 三、L2 · 体育科学官网采集（核心期刊官网直采）

### 3.1 能力
- 《体育科学》是**核心期刊但 NCPSSD 未收录**，官网 `tykx.xml-journal.net`（XML-Journal 平台）**免登录可采**。
- 抓取中英文摘要、作者、关键词、ISSN、卷期、DOI，并清理"AI辅读"等噪声后缀。

### 3.2 运行方式（`scripts/fetch_tykx_official.py`）
```bash
# 默认采集 2015-2026 全期
python3 fetch_tykx_official.py

# 指定年份区间
python3 fetch_tykx_official.py --start 2020 --end 2026

# 试运行不写库
python3 fetch_tykx_official.py --dry-run

# 只补摘要（不重新抓题录）
python3 fetch_tykx_official.py --abstract-only
```

### 3.3 关键技术点
- **目录页**：文章列表为 JS 异步加载 → 必须用 **Playwright networkidle 渲染** + 文本正则解析"标题/作者/年份卷期页 DOI"。
- **详情页**：服务端渲染 → 用 **requests + BeautifulSoup** 解析 meta 标签（citation_title/authors/keywords/issn/volume/year）+ `abstract-cn`/`abstract-en` 容器。
- **DOI 正则**：`([\w.\-/]+?)(?:\?|\s|$)`（已修正截断问题）。
- **入库**：`collected_by='official_website'`、`data_source='tykx_official'`；中文摘要写入 `abstract` 与 `abstract_cn` 双字段。

### 3.4 借鉴到其他期刊官网
- **方法论可复用**：凡"NCPSSD 未收录但有官网免费渠道"的期刊，均可用 L2 模式（目录页 Playwright + 详情页 requests + meta/容器解析）。
- 已验证：**《体育学刊》官网仅目次无全文**（可采目次题录，正文需其他渠道）。
- 待拓展：体育教育学刊、现代传播、新闻记者等官网渠道（见 `docs/journal_official_websites_free_access_20260816.md`）。

---

## 四、L3 · 主题弱项定向采集（国际文献补强）

### 4.1 能力
- 针对知识库**5 大弱项主题**（体育与性别/电竞新闻/体育新闻与技术/体育新闻伦理/体育国际传播），通过 Crossref/OpenAlex 按中英文检索词**历史回溯**。
- 复用 L0 `fetch_incremental` 的质量红线（`passes_filter`）与规范化函数，确保入库质量。

### 4.2 运行方式（`scripts/fetch_theme_weakspots.py`）
```bash
# 全部弱项主题
python3 scripts/fetch_theme_weakspots.py

# 单主题 / 多主题
python3 scripts/fetch_theme_weakspots.py --themes 电竞新闻
python3 scripts/fetch_theme_weakspots.py --themes 体育与性别,体育新闻伦理

# 只采 2024 年以来
python3 scripts/fetch_theme_weakspots.py --start-year 2024

# 试运行
python3 scripts/fetch_theme_weakspots.py --dry-run
```

### 4.3 质量清理（`scripts/clean_theme_weakspots.py`）
```bash
# 只报告不删除
python3 scripts/clean_theme_weakspots.py --dry-run

# 生成质量报告
python3 scripts/clean_theme_weakspots.py --report
```
- **清理原则**：只剔 `HARD_NOISE` 强噪声（材料/化学/医学/金融等明显非体育研究），**不做主题词强约束**——避免误删实际相关的体育媒体/传播研究（如 Sports and Media Culture）。
- 入库标记：`collected_by='theme_weakspot'`、`data_quality_status='pending_translate'`（待进翻译队列）。

### 4.4 关键参数（权威定义见 `config/parameters.json`）
- `THEME_QUERIES`：5 主题 × 9 中英文检索词。
- `THEME_CATEGORY`：主题→分类标签映射。
- `--start-year` 默认 2010、`--per-theme` 默认 60。

---

## 五、采集后标准化动作（三条链路通用）

1. **同步权威库三处**：主库 `database/knowledge_base.db` = 部署包 `/workspace/sports-kb-local-deploy` = 云端 GitHub。
   ```bash
   # 推送 DB 到云端（git 克隆+提交推送，规避 Contents API 50MB 限制）
   python3 scripts/push_db_to_github.py
   ```
2. **重建静态站**：`python3 scripts/build_static_site.py`（产出 `web/static_site/`）。
3. **同步线上**：`bash scripts/sync_github_pages.sh`（调 `update_github_pages.py`）。
4. **国际文献**：进翻译队列，由 `translate_pending.py` 补译 `abstract_cn`（受免费额度监控，见 `docs/TRANSLATION_SKILL_FROZEN.md`）。

---

## 六、固化状态（已验证，2026-08-17）

- ✅ **L1 NCPSSD**：已采集国内 8703 篇（摘要覆盖 99.5%，剩余为编委会/总目次等非论文栏目）。
- ✅ **L2 体育科学官网**：已采集 1081 篇（2015-2026 全量，含中英文摘要/作者/关键词/DOI）。
- ✅ **L3 主题弱项**：已采集并清理 550 篇国际文献（性别144/电竞137/国际传播107/技术89/伦理73），较采集前提升 20-50 倍。
- ✅ **权威库三处同步**：总文献 **12106 篇**（国内10254/国际1852），FTS 索引与主表完全同步。
- ✅ **统一参数**：全部词表/检索参数已固化于 `config/parameters.json`（`scripts/kb_params.py` 加载，经校验与脚本完全一致）。

---

## 七、待拓展方向（基于本手册方法论）

- 其余核心期刊官网渠道：体育教育学刊、现代传播、新闻记者、新闻与写作（官网免费渠道调研见 `docs/journal_official_websites_free_access_20260816.md`）。
- 体育文化导刊 2018-2024、武汉体院 2020-2025、体育与科学 2019-2025 题录补全（可复用 L2 官网模式）。
- 新增弱项主题（如"体育新闻史""体育新闻教育"）→ 在 `config/parameters.json` 的 `THEME_QUERIES` 增加主题词后跑 L3。

---

*本文档为采集技能的权威固化版本，如有更新请同步修改并标注日期。*
