# AI博主爬取 - 完整运行指南

## 📋 前置条件

- Windows 10/11
- Python 3.8+
- Node.js（用于 CDP 脚本）
- Edge 浏览器（或 Chrome）
- 飞书账号和多维表格

---

## 第一步：激活虚拟环境

```powershell
cd "%USERPROFILE%\Multi-platform information management tool"

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 验证环境
python --version
pip list
```

---

## 第二步：检查环境完整性

```powershell
# 运行环境检查脚本
python check_environment.py
```

预期输出：所有检查项显示 `[OK]`

---

## 第三步：配置飞书多维表格

### 3.1 编辑配置文件

```powershell
notepad feishu-base-config.json
```

### 3.2 填入以下信息

```json
{
  "base_name": "你的多维表格名称",
  "base_token": "从URL获取的token",
  "base_url": "https://xxx.feishu.cn/base/XXX",
  "profile": "default",
  "tables": {
    "creators": {"name": "博主", "table_id": "tblXXX"},
    "videos": {"name": "视频", "table_id": "tblXXX"},
    "video_metric_snapshots": {"name": "视频数据快照", "table_id": "tblXXX"},
    "crawl_task_logs": {"name": "爬取任务日志", "table_id": "tblXXX"},
    "video_comments": {"name": "视频评论", "table_id": "tblXXX"}
  },
  "platforms": {
    "bilibili": {"enabled": true, "name": "B站"},
    "douyin": {"enabled": true, "name": "抖音"},
    "xiaohongshu": {"enabled": true, "name": "小红书"},
    "kuaishou": {"enabled": true, "name": "快手"}
  }
}
```

### 3.3 如何获取配置值

1. 打开飞书多维表格
2. URL 格式：`https://xxx.feishu.cn/base/XXX?table=tblYYY`
3. `base_token` = `/base/` 后面的部分（如 `XXX`）
4. `table_id` = `?table=` 后面的部分（如 `tblYYY`）

---

## 第四步：安装 lark-cli（飞书命令行工具）

```powershell
# 方法1: npm 安装
npm install -g @larksuite/cli

# 方法2: 从飞书开放平台下载
# https://open.feishu.cn/document/home/develop-a-gadget/development-tools

# 验证安装
lark-cli --version
```

---

## 第五步：登录 lark-cli

```powershell
# 登录（会显示二维码，用飞书扫码）
lark-cli auth login --profile default

# 验证登录状态
lark-cli auth status --verify
```

预期输出：`Profile "default" is authenticated`

---

## 第六步：启动浏览器远程调试

### 6.1 关闭所有 Edge/Chrome 窗口

### 6.2 启动 Edge 远程调试

```powershell
# Edge 命令
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222

# 或 Chrome 命令
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

### 6.3 在浏览器中登录各平台

- 登录 B站：https://www.bilibili.com
- 登录抖音：https://www.douyin.com
- 登录小红书：https://www.xiaohongshu.com
- 登录快手：https://www.kuaishou.com

---

## 第七步：测试运行

### 7.1 测试 B站单个博主下载

```powershell
# 使用 Edge 浏览器
python download_bili_following_latest.py --max-creators 1 --max-total-videos 1 --browser edge

# 或使用 Chrome
python download_bili_following_latest.py --max-creators 1 --max-total-videos 1 --browser chrome
```

### 7.2 检查下载结果

```powershell
# 查看下载的视频
dir downloads\videos\

# 查看清单文件
dir downloads\manifests\
```

---

## 第八步：正式运行

### 8.1 运行全平台下载

```powershell
python download_all_platform_latest.py --platform all
```

### 8.2 或单独运行各平台

```powershell
# B站下载
python download_bili_following_latest.py --videos-per-creator 3 --browser edge

# 抖音下载
python download_douyin_latest.py --videos-per-creator 1

# 小红书下载
python download_xiaohongshu_latest.py --from-feishu --videos-per-creator 1

# 快手下载
python download_kuaishou_latest.py --from-feishu --videos-per-creator 1
```

---

## 第九步：后处理（B站转写）

```powershell
# 使用 Whisper 进行语音转写
python postprocess_bili_videos.py --model large-v3-turbo --device cuda

# 如果没有 GPU，使用 CPU
python postprocess_bili_videos.py --model large-v3-turbo --device cpu
```

---

## 第十步：同步到飞书

```powershell
# 同步 B站评论
python sync_bilibili_comments_to_feishu.py --max-comment-table-rows 30

# 同步抖音数据
python sync_douyin_to_feishu.py

# 同步小红书数据
python sync_xiaohongshu_to_feishu.py

# 同步快手数据
python sync_kuaishou_to_feishu.py
```

---

## 🚀 快速启动命令（一键执行）

```powershell
cd "%USERPROFILE%\Multi-platform information management tool"

# 激活环境
.\.venv\Scripts\Activate.ps1

# 设置 PATH（包含 ffmpeg）
$env:PATH = "%USERPROFILE%\Multi-platform information management tool\tools;" + $env:PATH

# 运行全平台下载
python download_all_platform_latest.py --platform all

# 运行 B站转写
python postprocess_bili_videos.py --model large-v3-turbo --device cuda
```

---

## ⚠️ 常见问题

### 问题1：lark-cli 连接失败
```powershell
# 重新登录
lark-cli auth login --profile default
```

### 问题2：浏览器 cookies 读取失败
```powershell
# 确保浏览器已关闭并重新启动远程调试
# 关闭所有浏览器窗口后运行：
msedge.exe --remote-debugging-port=9222
```

### 问题3：ffmpeg 未找到
```powershell
# 设置 PATH
$env:PATH = "%USERPROFILE%\Multi-platform information management tool\tools;" + $env:PATH
```

### 问题4：Whisper 模型下载慢
```powershell
# 使用较小的模型
python postprocess_bili_videos.py --model small --device cpu
```

---

## 📁 输出目录结构

```
downloads/
├── videos/              # 下载的视频文件
│   ├── bilibili/
│   ├── douyin/
│   ├── xiaohongshu/
│   └── kuaishou/
├── manifests/           # 运行清单和日志
├── comments/            # 评论数据
└── postprocess/         # 转写后的文本
```

---

## 📊 验证成功

运行完成后检查：

1. `downloads/videos/` 目录下有视频文件
2. `downloads/manifests/` 目录下有 JSON 清单文件
3. 飞书多维表格中新增了视频记录
4. （可选）飞书文档中有转写稿内容
