# CDP 版 B站抓取完整指南

> 本文档记录了通过 Chrome DevTools Protocol (CDP) 连接已登录的 Edge 浏览器，抓取 B站视频、评论并同步到飞书多维表格的完整工作流。
> 
> 这是经过实际验证、可稳定运行的方案。

---

## 📋 方案特点

| 特性 | 说明 |
|------|------|
| **登录态** | 复用浏览器已登录的 Cookie，无需手动提取 |
| **风控绕过** | 通过真实浏览器访问，避开 API 风控限制 |
| **完整数据** | 视频、封面、评论、统计数据、文案全部抓取 |
| **飞书预览** | 封面图以附件形式上传，画册视图直接预览 |
| **数据关联** | 博主 → 视频 → 评论 → 数据快照 多表关联 |

---

## 🏗️ 架构概览

```
Edge 浏览器（调试模式，端口 9222）
    │
    ├── CDP 连接 → 获取视频列表、统计数据、评论
    └── Cookie 传递 → yt-dlp 下载视频
                        │
                        ▼
                  本地 downloads/ 目录
                        │
                        ▼
                  飞书多维表格
                   ├── 博主表
                   ├── 视频表（含封面附件、文案）
                   ├── 视频数据快照表
                   └── 视频评论表
```

---

## ⚙️ 环境准备

### 1. 调试模式浏览器

使用独立的 Edge 用户数据目录，避免干扰日常浏览：

```powershell
# 启动调试模式 Edge（使用专用 profile）
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
    --remote-debugging-port=9222 `
    --user-data-dir="%USERPROFILE%\edge-debug-profile"
```

首次启动后，在打开的浏览器中登录 B站账号。

### 2. 验证登录状态

```powershell
cd "%USERPROFILE%\Multi-platform information management tool"
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
python _test_cdp_login.py
```

预期输出：`✅ 已登录 - 用户名: XXX, 等级: LvX`

### 3. 飞书配置

配置文件 `feishu-base-config.json` 需包含：

```json
{
  "base_token": "ZCf1bxiooaqQHPsEKQAcIaARndf",
  "profile": "default",
  "tables": {
    "creators":             { "table_id": "tblx1hxfoi1Y4lk0" },
    "videos":               { "table_id": "tblux1rdtJBP1hMZ" },
    "video_metric_snapshots": { "table_id": "tblMVVv7wijHCULu" },
    "video_comments":       { "table_id": "tblK0TcSZujbYEUA" },
    "crawl_task_logs":      { "table_id": "tblyaxXKEvaXX5DI" }
  }
}
```

验证飞书 CLI 登录：

```powershell
lark-cli auth status --verify
```

---

## 🚀 完整运行流程

### 第一步：启动调试浏览器

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
    --remote-debugging-port=9222 `
    --user-data-dir="%USERPROFILE%\edge-debug-profile"
```

### 第二步：运行 CDP 抓取脚本

```powershell
cd "%USERPROFILE%\Multi-platform information management tool"
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
$env:LARK_CLI_NO_PROXY = "1"

# 每个博主抓 3 个视频，每视频抓 50 条评论
.\.venv\Scripts\python.exe cdp_bili_download.py `
    --videos-per-creator 3 `
    --comment-limit 50
```

### 第三步：上传封面和文案到飞书

```powershell
.\.venv\Scripts\python.exe _upload_to_feishu.py
```

完成后，在飞书表格的「封面预览」画册视图中可以直接看到封面大图。

---

## 📁 核心文件说明

| 文件 | 作用 |
|------|------|
| `cdp_bili_download.py` | **主脚本**：CDP 连接、视频列表、下载、评论、飞书写入 |
| `_upload_to_feishu.py` | 补充上传封面附件和视频文案到飞书 |
| `_write_snapshots.py` | 写入数据快照（视频记录已存在时单独补快照） |
| `_rewrite_to_feishu.py` | 从本地 downloads 目录重建飞书记录（修复/迁移用） |
| `_test_cdp_login.py` | 测试 CDP 连接和 B站登录状态 |
| `_list_fields.py` | 辅助脚本：列出飞书表的字段名和类型 |
| `feishu-base-config.json` | 飞书多维表格配置 |

---

## 📊 飞书表格结构

### 博主表（creators）
- 平台、博主昵称、主页链接、粉丝数、是否持续追踪
- 关联字段：视频列表

### 视频表（videos）
| 字段 | 类型 | 说明 |
|------|------|------|
| BVID | 文本 | 视频唯一标识 |
| 平台 | 文本 | B站/抖音等 |
| 视频标题 | 文本 | |
| 封面 | 附件 | 封面图片，画册视图可预览 |
| 视频文案 | 文本 | 视频描述/简介 |
| 关联博主 | 关联 | 链接到博主表 |
| 视频下载状态 | 文本 | 已下载/失败 |
| 评论抓取状态 | 文本 | 已抓取/未抓取 |
| 已抓评论数 | 数字 | |
| 视频链接 | 文本 | B站视频链接 |
| 时长秒 | 数字 | |
| 发布时间 | 日期 | |
| 评论明细 | 关联 | 链接到评论表 |
| 各种路径字段 | 文本 | 本地文件路径（视频、封面、元数据等） |

### 视频数据快照表（video_metric_snapshots）
- 关联视频、播放量、点赞量、投币数、收藏数、分享数、评论数、弹幕数、粉丝数快照、快照时间

### 视频评论表（video_comments）
- 评论内容、用户昵称、用户ID、点赞数、回复数、评论时间、评论层级、关联视频

---

## 🔍 视图说明

| 视图 | 类型 | 用途 |
|------|------|------|
| Grid View | 网格 | 默认表格视图，查看所有字段 |
| 封面预览 | 画册 | 大图卡片形式浏览视频封面 |

切换方式：飞书表格左上角视图下拉菜单。

---

## 📂 本地输出目录结构

```
downloads/videos/
└── <MID>/                    # 博主 MID
    └── <BVID>/               # 视频 BV 号
        ├── <BVID>.mp4        # 视频文件
        ├── <BVID>.cover.jpg  # 封面图
        ├── <BVID>.info.json  # yt-dlp 元数据
        ├── video-description.txt  # 视频描述
        ├── comments.jsonl    # 评论数据（JSONL）
        └── metrics-snapshot.json  # 统计数据快照
```

---

## 🔧 常用操作

### 检查 CDP 连接

```powershell
python _test_cdp_login.py
```

### 只下载不写飞书

```powershell
python cdp_bili_download.py --videos-per-creator 1 --comment-limit 10 --dry-run
```

### 补写飞书记录（本地有文件、飞书丢了）

```powershell
# 写视频记录
python _rewrite_to_feishu.py

# 写数据快照
python _write_snapshots.py

# 上传封面和文案
python _upload_to_feishu.py
```

### 查看飞书表字段

```powershell
lark-cli --profile default base +field-list --as user `
    --base-token ZCf1bxiooaqQHPsEKQAcIaARndf `
    --table-id tblux1rdtJBP1hMZ --format json | python _list_fields.py
```

---

## ❓ 常见问题

### Q: 浏览器启动了但连不上？

确保调试端口正确，且没有其他 Edge 进程占用：

```powershell
# 检查端口
netstat -ano | findstr 9222

# 如果被占了，杀掉所有 Edge 进程重试
Get-Process msedge | Stop-Process -Force
```

### Q: 视频下载超时？

大视频（如毕导的长视频）可能超 300 秒限制。修改 `cdp_bili_download.py` 中的超时时间，或单独手动下载。

### Q: 飞书字段找不到？

字段名变了的时候，重新 list 一下再确认：

```powershell
lark-cli --profile default base +field-list --as user `
    --base-token ZCf1bxiooaqQHPsEKQAcIaARndf `
    --table-id <table_id> --format json | python _list_fields.py
```

### Q: 附件上传报错 "unsafe file path"？

lark-cli 的附件上传只接受相对路径。脚本里已经处理成相对路径了，确保运行目录是项目根目录。

### Q: 画册视图看不到封面？

检查视图是否正确选择：左上角 → 切换到「封面预览」。如果还是没有，确认视频记录的"封面"字段有值（有 file_token）。

---

## 📝 版本历史

- **v1.0** - 初始版本，CDP 完整流程跑通（视频下载 + 评论抓取 + 飞书同步 + 封面附件）
