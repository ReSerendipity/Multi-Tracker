# AI博主爬取

本地数据采集脚本，用于跟踪B站、抖音、小红书和快手等平台的AI博主，下载最新视频，创建转写稿文件，并将选定的元数据同步回飞书多维表格。

## 包含内容

- `download_bili_following_latest.py`：从飞书多维表格加载跟踪的B站博主，下载最新视频，收集第一阶段元数据，并写入任务记录。
- `postprocess_bili_videos.py`：为本地下载的视频补充B站字幕或Whisper转写稿。
- `sync_bilibili_comments_to_feishu.py`：获取并同步代表性的B站评论到飞书。
- `download_douyin_latest.py`：从配置的抖音博主下载最新视频。
- `sync_douyin_to_feishu.py`：将本地抖音下载文件同步到飞书。
- `enrich_douyin_feishu.py`：从本地文件补充抖音洞察字段。
- `download_xiaohongshu_latest.py`：从配置的小红书博主下载最新视频。
- `sync_xiaohongshu_to_feishu.py`：将本地小红书下载文件同步到飞书。
- `download_kuaishou_latest.py`：从配置的快手博主下载最新视频。
- `sync_kuaishou_to_feishu.py`：将本地快手下载文件同步到飞书。
- `write_transcript_content_to_feishu.py`：将Agent生成的转写稿摘要和关键点写入飞书，然后通过回读验证。
- `publish_transcript_docs_to_feishu.py`：从本地转写稿创建或更新飞书文档，并将文档URL写回多维表格。
- `.agents/skills/video-transcript-doc-writer/`：将清洗后的转写稿转换为结构化的可读口播稿JSON。
- `.agents/skills/`：项目本地的Codex技能，用于重复的爬取/评论工作流程。

## 本地设置

1. 复制示例配置文件并填入本地飞书多维表格信息：

   ```powershell
   Copy-Item .\feishu-base-config.example.json .\feishu-base-config.json
   ```

2. 确保工作流程所需的外部CLI工具在您的shell中可用：

   - `python`
   - `lark-cli`
   - `ffmpeg`
   - `yt-dlp` 或项目B站下载后端
   - `whisper` 用于ASR后处理
   - `node` 用于基于CDP的评论工具

3. 运行时输出被git有意忽略。下载的媒体、转写稿、清单文件、浏览器配置文件、二维码和本地飞书配置将保留在本地机器上。

## 常用命令

运行跨平台最新视频工作流程：

```powershell
python .\download_all_platform_latest.py --platform all
```

仅运行B站最新视频采集：

```powershell
python .\download_bili_following_latest.py --videos-per-creator 3
```

运行B站转写稿后处理：

```powershell
python .\postprocess_bili_videos.py --model large-v3-turbo --device cuda
```

运行抖音最新视频下载：

```powershell
python .\download_douyin_latest.py --videos-per-creator 1
```

运行小红书最新视频下载：

```powershell
python .\download_xiaohongshu_latest.py --from-feishu --videos-per-creator 1
```

运行快手最新视频下载：

```powershell
python .\download_kuaishou_latest.py --from-feishu --videos-per-creator 1
```

预览转写稿内容回写和文档发布（不实际写入飞书）：

```powershell
python .\write_transcript_content_to_feishu.py --curation-file .\downloads\manifests\YOUR_CURATION.json --record-id YOUR_RECORD_ID --dry-run
python .\publish_transcript_docs_to_feishu.py --record-id YOUR_RECORD_ID --update-existing --curation-file .\downloads\manifests\YOUR_CURATION.json --parent-position my_library --dry-run
```

## Codex自动化示例

参见 [`CODEX_AUTOMATION_EXAMPLE.md`](./CODEX_AUTOMATION_EXAMPLE.md) 获取Codex App每日自动化示例，涵盖B站/抖音数据采集、机器转写、Agent生成可读口播稿、飞书文档发布、清单文件验证和简洁故障报告。