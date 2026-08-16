# 🩺 三级自检机制（HEALTH CHECK）· 固化手册

> 体育新闻研究知识库 · 系统完整性/一致性/可用性常态化自检
> 建立日期：2026-08-17 ｜ 状态：✅ 已实现并验证，随云端调度运行

本机制让系统**每天/每周/每月自动自检**，及时发现并自动修复问题，保持知识库长期健康。这是 owner 建议"建立固定自检功能"的落地实现。

---

## 一、设计原则（owner 已确认）

| 决策点 | 选定方案 |
|--------|---------|
| **接入方式** | 并入现有云端任务（不新增独立 job，避免重复拉取 DB） |
| **通知策略** | 异常才告警 + 每周/每月定期健康摘要（每日正常静默，不打扰） |
| **异常处理** | 可自动修复且安全的项自动修复并记录；不可自动修复的才告警请 owner 处理 |
| **安全红线** | 绝不自动改动数据内容、删除文献、改凭证；只做"检查+安全修复+提醒" |

---

## 二、三级自检档位

| 档位 | 频率 | 深度 | 通知 |
|------|------|------|------|
| **daily** | 每日 | 轻量健康：关键路径、DB完整性、FTS同步、废弃脚本残留 | 仅异常时告警（正常静默） |
| **weekly** | 每周 | 完整一致性 + 数据质量摘要（consistency_check 全量 + 统计） | 发周度健康摘要 |
| **monthly** | 每月 | 深度治理：参数词表漂移、文档声称值、调度配置、归档残留 | 发月度健康报告 |

---

## 三、各档位检查项

### daily（轻量健康）
| 检查项 | 说明 | 可自动修复? |
|--------|------|------------|
| 关键路径存在性 | 9 项权威路径/脚本均存在 | 否（缺失即需人工） |
| 数据库完整性 | `PRAGMA integrity_check = ok` | 否（损坏需人工） |
| FTS 索引同步 | `literature` 与 `literature_fts` 行数一致 | ✅ 自动重建索引 |
| 废弃脚本残留 | scripts/ 根目录无已归档脚本 | 否（提醒人工归档） |

### weekly（完整一致性 + 数据质量）
- daily 全部检查项
- 数据质量统计：总量、国内/国际、摘要覆盖、中文摘要（翻译覆盖）、缺摘要数
- 文档声称值：README/主索引声称的文献数与实际比对
- DB 备份时效：DB 最近修改是否超 24h（提醒备份任务是否正常）

### monthly（深度治理）
- weekly 全部检查项
- **参数词表漂移**：`parameters.json` 与 `fetch_incremental` 实际定义逐项比对（EN_QUERIES/CN_QUERIES/SPORT_TOKENS/MEDIA_TOKENS/CORE_TERMS/ESPORTS_TOKENS/HARD_BLACKLIST/RULES/PER_QUERY/MIN_YEAR）
- **调度配置完整性**：`cloud_runner.py` 是否接入 daily/weekly/monthly 三级自检

---

## 四、运行方式（`scripts/health_check.py`）

```bash
python3 scripts/health_check.py daily      # 每日轻量
python3 scripts/health_check.py weekly     # 每周完整
python3 scripts/health_check.py monthly    # 每月深度
python3 scripts/health_check.py daily --notify-only  # 只打印不发送（调试）
```

**退出码**：
- `0` = 正常（每日静默；每周/每月发摘要）
- `2` = 有告警但已自动修复（已记录）
- `3` = 有异常需人工处理（已发告警）

**通知通道**：复用 `scheduler.send_email`（邮件）+ `wechat_pusher`（微信），不新增独立通道。

**日志**：每次自检结果写入 `output/health/{level}_{YYYYMMDD}.md`。

---

## 五、接入方式（并入云端调度）

已接入 `scripts/cloud_runner.py`，随现有任务运行（不新增独立 job）：
- `run_daily()` 末尾 → `_health('daily')`
- `run_weekly()` 末尾 → `_health('weekly')`
- `run_monthly()` 末尾 → `_health('monthly')`

通过 `cloud_scheduler.yml` 现有 cron 触发（每日 08:00/20:00、每周一 09:00、每月1日 09:10），无需改 cron 配置。

---

## 六、自动修复能力（安全范围）

| 可自动修复项 | 修复动作 | 安全依据 |
|-------------|---------|---------|
| FTS 索引不同步 | 调用 `build_static_site.py` 重建索引 | 重建索引不改数据内容 |
| 文档统计过时 | 仅提醒（README/主索引声称值），由 owner 或治理脚本更新 | 不擅自改文档 |

**绝不自动修复**（发告警请 owner 处理）：数据库损坏、关键脚本缺失、密钥/凭证失效、参数词表漂移、废弃脚本残留（保守不删）。

---

## 七、故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| 每日自检无输出 | 正常静默（daily 通过时不发通知） | 属预期；查看 `output/health/daily_*.md` |
| 每周收到健康摘要 | weekly 正常发送 | 属预期，查看摘要内容 |
| 收到"需人工处理"告警 | 有 failed 项 | 按报告清单逐项处理（如 DB 损坏、密钥失效） |
| 参数漂移告警 | parameters.json 与脚本词表不一致 | 统一改 `config/parameters.json`，勿在脚本内另起词表 |
| 自检脚本自身报错 | 脚本 bug 或环境异常 | 查看 `output/health/` 日志，手动重跑对应档位 |

---

## 八、固化状态（已验证，2026-08-17）

- ✅ `scripts/health_check.py` 三级自检实现，daily/weekly/monthly 均实测通过（退出码 0）
- ✅ 已接入 `cloud_runner.py` 的 run_daily/run_weekly/run_monthly（并入式，不新增 job）
- ✅ 自动修复能力（FTS 重建）与通知通道（邮件+微信）已验证可调用
- ✅ 全部检查项在当前系统上通过：DB 完整性 ok、FTS 同步 12249/12249、无参数漂移、文档一致
- ✅ 已同步到本地部署包

---

*本机制为知识库常态化自检的权威固化版本，如有更新请同步修改并标注日期。*
