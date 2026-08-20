# 体育新闻研究知识库 - 静态部署包

## 说明
这是一个完全自包含的静态站点，无需后端服务器，数据全部内嵌在 index.html 中。

## 部署方法（任选其一）

### 1. GitHub Pages
1. 创建 GitHub 私有仓库
2. 上传本目录所有文件到仓库
3. 仓库 Settings → Pages → 选择分支 → 部署

### 2. Vercel / Netlify / Cloudflare Pages
1. 注册对应平台账号
2. 上传/导入本目录
3. 一键部署

### 3. 本地打开
直接双击 index.html 即可浏览（无需网络）

## 更新数据
重新运行: `python3.11 scripts/build_static_site.py`

## 数据统计
- 生成时间: 2026-08-20 19:23
- 文献总数: 12300
