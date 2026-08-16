#!/bin/bash
# 体育新闻研究知识库 - 本地备份打包脚本（原"云盘同步"名不符实，已更正）
# 将关键数据文件打包备份到本地 /tmp。
# 注意：本脚本仅做本地 tar 打包，**不真正上传云盘**。
# 真正的腾讯网盘(tdrive)上传流程见 docs/RUNBOOK.md 第4节。

set -e

PROJECT_ROOT="/workspace/sports-journalism-kb"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SYNC_LOG="/tmp/sports_kb_sync_${TIMESTAMP}.log"

echo "🔄 开始本地备份打包... ($(date))" | tee $SYNC_LOG

# 需要同步的关键文件
FILES_TO_SYNC=(
    "$PROJECT_ROOT/database/knowledge_base.db"
    "$PROJECT_ROOT/data/raw/international_literature.md"
    "$PROJECT_ROOT/data/raw/domestic_literature.md"
)

for file in "${FILES_TO_SYNC[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ 文件就绪: $file ($(du -h "$file" | cut -f1))" | tee -a $SYNC_LOG
    else
        echo "  ⚠️ 文件不存在: $file" | tee -a $SYNC_LOG
    fi
done

# 打包备份
BACKUP_FILE="/tmp/sports_kb_backup_${TIMESTAMP}.tar.gz"
tar -czf "$BACKUP_FILE" -C /workspace sports-journalism-kb/database sports-journalism-kb/data sports-journalism-kb/output 2>/dev/null
echo "📦 备份打包完成: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))" | tee -a $SYNC_LOG

echo "✅ 本地备份完成 ($(date))" | tee -a $SYNC_LOG
echo "📝 日志: $SYNC_LOG"
echo "💡 如需真正上传腾讯云盘(tdrive)，请按 docs/RUNBOOK.md 第4节操作"
