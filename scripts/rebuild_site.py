#!/usr/bin/env python3
"""
体育新闻研究知识库 - 站点重建脚本 (GitHub Actions 用)
=====================================================
用更新后的 data.json 重新生成 index.html。

关键点:
  - index.html 是自包含单文件，数据内嵌在 <script>const DATA = {...}</script>
  - 保留现有 index.html 的模板、样式、功能逻辑，只替换数据部分
  - 这样 GitHub Actions 每次运行都能产出最新数据的站点
"""
import os
import sys
import json
import re
from datetime import datetime
from json import JSONDecoder

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = REPO_ROOT
DATA_FILE = os.path.join(SITE_DIR, 'data.json')
INDEX_FILE = os.path.join(SITE_DIR, 'index.html')


def rebuild():
    # 读取数据
    if not os.path.exists(DATA_FILE):
        print('❌ 未找到 data.json，无法重建')
        return False
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 读取现有 index.html（作为模板）
    if not os.path.exists(INDEX_FILE):
        print('❌ 未找到 index.html，无法重建（需要初始模板）')
        return False
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    # 定位 "const DATA = " 之后的数据起点
    marker = re.search(r'const DATA\s*=\s*', html)
    if not marker:
        print('❌ 无法在 index.html 中定位 const DATA，请确认模板格式')
        return False
    data_start = html.find('{', marker.end())
    if data_start < 0:
        print('❌ 未找到数据起点 {')
        return False

    # 用标准 JSON 解码器定位数据对象真正的结束位置（避免正则括号错配）
    decoder = JSONDecoder()
    try:
        _, data_end_rel = decoder.raw_decode(html[data_start:])
    except Exception as e:
        print(f'❌ 解析现有内嵌数据失败: {e}')
        return False
    data_end = data_start + data_end_rel

    # 生成新的 JSON 数据（内嵌进 JS，需转义 </script> 防止提前闭合 script 标签）
    data_json = json.dumps(data, ensure_ascii=False)
    data_json = data_json.replace('</script>', '<\\/script>')

    # 重建：保留 "const DATA = " 之前 + 新数据 + 数据对象结束之后的所有内容
    new_html = html[:marker.end()] + data_json + html[data_end:]

    # 更新生成时间显示（如果有 genTime）
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    new_html = new_html.replace(
        '<span id="genTime"></span>',
        f'<span id="genTime">{now}</span>'
    )

    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f'✅ 站点已重建: {INDEX_FILE}')
    print(f'   data.json 文献数: {data.get("stats", {}).get("total", "?")}')
    print(f'   生成时间: {now}')
    return True


if __name__ == '__main__':
    ok = rebuild()
    sys.exit(0 if ok else 1)
