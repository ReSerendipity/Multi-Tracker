# 多平台博主追踪系统

一套完整的多平台视频博主追踪工具，支持 B站、抖音、小红书、快手四大平台的视频下载、评论抓取、数据同步和内容转写。所有数据自动同步到飞书多维表格，实现一站式博主内容管理。

---

## 📌 重要声明

本项目由 **Doro** 创作，用于 TraeWork 活动投稿分享。使用前请务必阅读 [LICENSE.md](./LICENSE.md) 了解使用条款和免责声明。

⚠️ **请遵守各平台服务条款，尊重知识产权，仅限个人学习研究使用**。

### 👤 关于作者

- **抖音/小红书**: 有缘自然重逢  
- **飞书社区**: Doro  
- **项目来源**: TraeWork 的 100 种用法 活动投稿

---

## 功能列表

### 四平台视频下载
- **B站**：通过 CDP（Chrome DevTools Protocol）连接已登录浏览器，抓取关注列表博主的最新视频
- **抖音**：CDP 桥接方式抓取博主主页最新视频
- **小红书**：CDP 桥接方式抓取博主笔记/视频
- **快手**：CDP 桥接方式抓取博主最新视频
- **全平台一键执行**：`download_all_platform_latest.py` 统一调度

### 飞书多维表格同步
- 博主信息管理（平台、昵称、主页链接、粉丝数等）
- 视频元数据同步（标题、封面、发布时间、时长、播放量等）
- 视频数据快照（记录播放/点赞/收藏/评论等数据随时间变化）
- 评论数据同步（支持多级评论、点赞数、用户信息）
- 爬取任务日志（记录每次运行的成功/失败统计）

### 评论抓取
- B站评论：直接通过 CDP 抓取，支持一级/二级评论
- 抖音评论：CDP 桥接脚本抓取
- 小红书评论：CDP 桥接脚本抓取
- 快手评论：CDP 桥接脚本抓取

### Whisper 语音转写
- 本地 Whisper 模型转写（支持 CPU/GPU）
- 自动生成字幕文件和清洗后的文本
- 生成内容摘要和关键要点

### 飞书文档发布
- 将转写稿整理为结构化口播稿
- 自动发布到飞书文档
- 文档链接回写到多维表格

---

## 前置条件

| 工具 | 版本要求 | 说明 |
|------|----------|------|
| **Python** | 3.8+ | 运行核心脚本 |
| **Node.js** | 16+ | 运行 CDP 桥接脚本和 Playwright |
| **lark-cli** | 最新版 | 飞书命令行工具，用于操作多维表格 |
| **FFmpeg** | 最新版 | 视频处理和 Whisper 依赖 |
| **yt-dlp** | 最新版 | B站视频下载后端 |
| **飞书账号** | - | 需要有飞书多维表格权限 |
| **Edge/Chrome 浏览器** | - | 用于 CDP 连接，需提前登录各平台 |

---

## 快速开始

### 第一步：安装依赖

```powershell
# 进入项目目录
cd "分享包_多平台博主追踪系统"

# 创建并激活虚拟环境（推荐）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Node.js 依赖（用于 CDP 桥接）
npm install
```

### 第二步：配置飞书

1. 复制配置模板：

```powershell
Copy-Item .\feishu-base-config.example.json .\feishu-base-config.json
```

2. 编辑 `feishu-base-config.json`，填入你的飞书多维表格信息：
   - `base_token`：从多维表格 URL 中 `/base/` 后面的部分获取
   - `table_id`：各张表的 ID（博主表、视频表等）
   - 各表的创建方法请参考 `docs/飞书表结构指南.md`

3. 安装并登录 lark-cli：

```powershell
# 安装（如未安装）
npm install -g @anthropic/lark-cli

# 登录（扫码）
lark-cli auth login --profile default

# 验证登录
lark-cli auth status --verify
```

### 第三步：启动调试浏览器

```powershell
# 启动 Edge（推荐）
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
    --remote-debugging-port=9222 `
    --user-data-dir="C:\edge-debug-profile"

# 或启动 Chrome
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
    --remote-debugging-port=9222 `
    --user-data-dir="C:\chrome-debug-profile"
```

在打开的浏览器中，分别登录以下平台：
- B站：https://www.bilibili.com
- 抖音：https://www.douyin.com
- 小红书：https://www.xiaohongshu.com
- 快手：https://www.kuaishou.com

### 第四步：环境检查

```powershell
python check_environment.py
```

确保所有检查项显示 `[OK]`。

### 第五步：开始使用

**全平台一键下载：**
```powershell
python download_all_platform_latest.py --platform all
```

**单独运行各平台：**
```powershell
# B站
python download_bili_following_latest.py --videos-per-creator 3

# 抖音
python download_douyin_latest.py --videos-per-creator 1

# 小红书
python download_xiaohongshu_latest.py --from-feishu --videos-per-creator 1

# 快手
python download_kuaishou_latest.py --from-feishu --videos-per-creator 1
```

**同步评论到飞书：**
```powershell
# B站评论
python sync_bilibili_comments_to_feishu.py

# 抖音数据同步
python sync_douyin_to_feishu.py

# 小红书数据同步
python sync_xiaohongshu_to_feishu.py

# 快手数据同步
python sync_kuaishou_to_feishu.py
```

**语音转写（B站）：**
```powershell
# GPU 加速（推荐）
python postprocess_bili_videos.py --model large-v3-turbo --device cuda

# CPU 运行
python postprocess_bili_videos.py --model large-v3-turbo --device cpu
```

**一键启动（使用 start.ps1）：**
```powershell
.\start.ps1 check        # 环境检查
.\start.ps1 all          # 全平台下载
.\start.ps1 bili         # B站下载
.\start.ps1 douyin       # 抖音下载
.\start.ps1 postprocess  # B站转写
```

---

## 目录结构说明

```
分享包_多平台博主追踪系统/
├── .agents/
│   └── skills/                          # Trae Work 技能文件
│       ├── bili-daily-update-check/     # B 站日更检查技能
│       ├── bili-following-latest/       # B 站关注列表最新视频
│       ├── bilibili-comments/           # B 站评论抓取
│       ├── douyin-comments/             # 抖音评论抓取
│       ├── kuaishou-comments/           # 快手评论抓取
│       ├── xiaohongshu-comments/        # 小红书评论抓取
│       └── video-transcript-doc-writer/ # 视频转写稿文档生成
├── docs/                                # 文档目录
│   ├── README_CN.md                     # 项目说明（中文版）
│   ├── RUN_GUIDE.md                     # 完整运行指南
│   ├── TRAE_WORK_AUTOMATION_EXAMPLE.md  # Trae Work 自动化示例
│   ├── CDP_BILI_GUIDE.md                # CDP B 站抓取指南
│   └── 飞书表结构指南.md                 # 飞书多维表格建表指南
├── scripts/                             # CDP 桥接脚本
│   ├── douyin_cdp_bridge.mjs            # 抖音 CDP 桥接
│   ├── fetch_douyin_comments.py         # 抖音评论抓取
│   ├── fetch_douyin_comments_cdp.mjs    # 抖音评论 CDP 脚本
│   ├── xiaohongshu_cdp_bridge.mjs       # 小红书 CDP 桥接
│   └── kuaishou_cdp_bridge.mjs          # 快手 CDP 桥接
├── downloads/                           # 下载输出目录（运行时生成）
│   ├── videos/                          # 视频文件
│   ├── manifests/                       # 运行清单和日志
│   ├── comments/                        # 评论数据
│   └── postprocess/                     # 转写后的文本
├── download_bili_following_latest.py    # B站下载主脚本
├── download_douyin_latest.py            # 抖音下载主脚本
├── download_xiaohongshu_latest.py       # 小红书下载主脚本
├── download_kuaishou_latest.py          # 快手下载主脚本
├── download_all_platform_latest.py      # 全平台统一调度
├── sync_bilibili_comments_to_feishu.py  # B站评论同步到飞书
├── sync_douyin_to_feishu.py             # 抖音数据同步到飞书
├── sync_xiaohongshu_to_feishu.py        # 小红书数据同步到飞书
├── sync_kuaishou_to_feishu.py           # 快手数据同步到飞书
├── postprocess_bili_videos.py           # B站视频后处理（转写）
├── publish_transcript_docs_to_feishu.py # 发布转写稿文档到飞书
├── write_transcript_content_to_feishu.py # 转写内容写回飞书表格
├── cdp_bili_download.py                 # CDP 方式 B站下载（备用）
├── fetch_bili_following.py              # 获取 B站关注列表
├── fetch_bili_following.js              # B站关注列表 JS 脚本
├── import_bili_following_to_feishu.py   # 导入 B站关注列表到飞书
├── enrich_douyin_feishu.py              # 补充抖音飞书数据
├── update_creators_tracking.py          # 更新博主跟踪状态
├── check_environment.py                 # 环境检查脚本
├── feishu-base-config.example.json      # 飞书配置模板
├── requirements.txt                     # Python 依赖
├── package.json                         # Node.js 依赖
├── start.ps1                            # 一键启动脚本
└── README.md                            # 本文件
```

---

## 飞书表结构说明

需要在飞书多维表格中创建以下 5 张表。详细字段说明请参考 `docs/飞书表结构指南.md`。

### 1. 博主表（creators）
存储博主基本信息，是所有数据的入口。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 博主名称 | 文本 | 博主昵称/名称 |
| 平台 | 单选 | B站 / 抖音 / 小红书 / 快手 |
| 平台用户ID | 文本 | 各平台的唯一标识（MID/sec_uid等） |
| 主页链接 | 文本 | 博主主页 URL |
| 粉丝数 | 数字 | 当前粉丝数量 |
| 是否持续跟踪 | 复选框 | 是否纳入日常追踪 |
| 视频列表 | 关联 | 关联到视频表 |
| 备注 | 文本 | 可选备注信息 |

### 2. 视频表（videos）
存储视频元数据和下载状态。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 视频标题 | 文本 | 视频标题 |
| 平台 | 单选 | B站 / 抖音 / 小红书 / 快手 |
| 视频ID | 文本 | BVID / aweme_id / note_id 等 |
| 视频链接 | 文本 | 视频页面 URL |
| 关联博主 | 关联 | 关联到博主表 |
| 发布时间 | 日期 | 视频发布时间 |
| 时长秒 | 数字 | 视频时长（秒） |
| 封面 | 附件 | 视频封面图 |
| 视频文案 | 文本 | 视频描述/简介 |
| 视频下载状态 | 单选 | 未下载 / 已下载 / 下载失败 |
| 评论抓取状态 | 单选 | 未抓取 / 已抓取 / 抓取失败 |
| 已抓评论数 | 数字 | 已抓取的评论数量 |
| 最近采集时间 | 日期 | 最后一次采集的时间 |
| 视频文件路径 | 文本 | 本地视频文件路径 |
| 口播稿文档 | 文本 | 飞书文档链接 |
| 内容摘要 | 文本 | AI 生成的内容摘要 |
| 关键要点 | 文本 | AI 提取的关键要点 |

### 3. 视频评论表（video_comments）
存储视频的评论数据。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 评论内容 | 文本 | 评论文字内容 |
| 用户昵称 | 文本 | 评论者昵称 |
| 用户ID | 文本 | 评论者平台ID |
| 点赞数 | 数字 | 评论获得的点赞数 |
| 回复数 | 数字 | 评论的回复数量 |
| 评论层级 | 单选 | 一级 / 二级 |
| 关联视频 | 关联 | 关联到视频表 |
| 评论时间 | 日期 | 评论发布时间 |
| 平台 | 单选 | B站 / 抖音 / 小红书 / 快手 |

### 4. 视频数据快照表（video_metric_snapshots）
记录视频数据随时间的变化。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 关联视频 | 关联 | 关联到视频表 |
| 快照时间 | 日期 | 数据采集时间 |
| 播放量 | 数字 | 播放次数 |
| 点赞量 | 数字 | 点赞次数 |
| 投币数 | 数字 | B站投币数 |
| 收藏数 | 数字 | 收藏次数 |
| 分享数 | 数字 | 分享次数 |
| 评论数 | 数字 | 评论数量 |
| 弹幕数 | 数字 | B站弹幕数 |
| 粉丝数快照 | 数字 | 博主当时的粉丝数 |

### 5. 爬取任务日志表（crawl_task_logs）
记录每次爬取任务的执行情况。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 任务名称 | 文本 | 任务描述 |
| 平台 | 单选 | B站 / 抖音 / 小红书 / 快手 / 全平台 |
| 开始时间 | 日期 | 任务开始时间 |
| 结束时间 | 日期 | 任务结束时间 |
| 状态 | 单选 | 成功 / 部分成功 / 失败 |
| 成功数量 | 数字 | 成功处理的视频数 |
| 跳过数量 | 数字 | 跳过的视频数 |
| 失败数量 | 数字 | 失败的视频数 |
| 错误信息 | 文本 | 错误详情 |
| 清单文件路径 | 文本 | 本次运行的 manifest 文件路径 |

---

## 常见问题

### Q: CDP 连接失败怎么办？
A: 确认浏览器已经启动并开启了 9222 调试端口。可以访问 http://127.0.0.1:9222/json 验证是否有返回。如果被其他进程占用，杀掉所有浏览器进程后重试。

### Q: 飞书 API 报错 not_found？
A: 大概率是字段名或表 ID 不对。先用 `lark-cli base +field-list` 检查表的真实字段名，确保配置文件中的 table_id 正确。

### Q: 附件上传报 "unsafe file path"？
A: lark-cli 的附件上传只接受相对路径。确保运行目录是项目根目录，脚本内部已经处理成相对路径。

### Q: Whisper 模型下载慢？
A: 可以先使用较小的模型测试：`python postprocess_bili_videos.py --model small --device cpu`。模型会自动下载并缓存。

### Q: 抖音/小红书/快手登录态失效？
A: 在调试浏览器中重新登录对应平台即可。CDP 方式会自动复用浏览器的 Cookie。

### Q: 如何添加新的博主？
A: 在飞书博主表中新增一条记录，填写平台、博主名称和平台用户ID，勾选"是否持续跟踪"即可。下次运行时会自动抓取。

### Q: 更多详细文档在哪？
A: 请查看 `docs/` 目录下的文档：
- `RUN_GUIDE.md` - 完整运行指南（分步详解）
- `飞书表结构指南.md` - 详细的建表说明
- `CDP_BILI_GUIDE.md` - B 站 CDP 抓取专项指南
- `TRAE_WORK_AUTOMATION_EXAMPLE.md` - Trae Work 自动化配置示例
