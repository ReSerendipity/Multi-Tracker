# 多平台博主追踪系统 - B站复现包

这是从完整项目里提取的 B站最小可用版本，用来验证和复现核心流程。

## 文件说明

```
download_bili_following_latest.py   # B站视频下载 + 飞书同步（主脚本）
sync_bilibili_comments_to_feishu.py # B站评论同步到飞书
cdp_bili_download.py                # CDP 方式下载 B站视频（备用方案）
check_environment.py                # 环境检查脚本
feishu-base-config.example.json     # 飞书配置模板
requirements.txt                    # Python 依赖
RUN_GUIDE.md                        # 详细运行指南
```

## 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

### 2. 配置飞书

把 `feishu-base-config.example.json` 复制为 `feishu-base-config.json`，填入你的飞书多维表格信息：

- `base_token`：从多维表格 URL 里 `/base/` 后面那串
- `table_id`：博主表、视频表等各表的 ID

### 3. 启动带调试端口的 Chrome

```powershell
# Windows
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\chrome-cdp-bili"
```

在打开的浏览器里登录 B站账号。

### 4. 运行环境检查

```powershell
python check_environment.py
```

确保所有检查项都通过。

### 5. 开始下载

```powershell
python download_bili_following_latest.py --videos-per-creator 3
```

### 6. 同步评论（可选）

```powershell
python sync_bilibili_comments_to_feishu.py
```

## 飞书表结构

需要在飞书多维表格里建以下几张表：

### 博主表（creators）
- 博主名称（文本）
- B站MID（文本）
- 平台（单选：B站/抖音/小红书/快手）
- 是否持续跟踪（复选框）

### 视频表（videos）
- 视频标题（文本）
- BVID（文本）
- AID（文本）
- 平台（单选）
- 视频链接（文本）
- 关联博主（关联）
- 发布时间（日期）
- 时长秒（数字）
- 封面（附件）
- 视频文件路径（文本）
- 视频下载状态（文本）
- 评论抓取状态（文本）
- 已抓评论数（数字）
- 最近采集时间（日期）

### 视频评论表（video_comments）
- 评论内容（文本）
- 用户昵称（文本）
- 点赞数（数字）
- 评论层级（单选：一级/二级）
- 关联视频（关联）
- 评论时间（日期）

## 常见问题

**Q: 报 CDP 连接失败？**
A: 确认 Chrome 已经启动并开了 9222 调试端口。可以访问 http://127.0.0.1:9222/json 看看有没有返回。

**Q: 飞书 API 报错 not_found？**
A: 大概率是字段名不对。先用 `lark-cli base +field-list` 查一下表的真实字段名。

**Q: 附件上传报 unsafe file path？**
A: 必须用相对路径，不能用绝对路径。脚本里已经处理好了，如果你自己改了代码注意一下。

更多问题看 `RUN_GUIDE.md`。
