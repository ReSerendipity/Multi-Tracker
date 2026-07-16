# Codex 定时任务示例

这个示例用于 Codex App 的 Automation，不是 Windows 计划任务，也不会在克隆仓库后自动安装。

## 创建方式

在 Codex App 中新建 Automation，并填写：

- 名称：`Bili Douyin daily update check`
- 项目：当前仓库根目录
- 执行环境：本地
- 频率：每天一次，例如 19:00
- Prompt：复制下面的内容

## Prompt

```text
在当前项目根目录执行公开版 AI 博主日更流程。只运行仓库现有的 B站和抖音流程，不修改代码，不输出或保存 Cookie 明文。

1. 运行：python .\download_all_platform_latest.py --platform all --stop-on-error
2. 检查退出码，以及本次生成的 downloads\manifests\*-all-platform-latest.json、*-bili-latest-download.json 和 *-douyin-latest-download.json。只有当抖音 download manifest 的 successes 不为空时，才要求本次存在 *-douyin-feishu-sync.json；没有新增抖音视频时，不要把缺少 sync manifest 误报为失败。其他预期 manifest 缺失或退出码非零时，明确报告失败，不得声称任务完成。
3. 只有当本次 B站下载 manifest 的 successes 不为空时，运行：python .\postprocess_bili_videos.py --latest-download-manifest --model large-v3-turbo --device cuda。若机器没有可用 CUDA，改用 --device cpu。
4. 检查最新 *-bili-postprocess.json，并确认 successes 中的 speech-raw.txt、speech-clean.txt、summary.md 和 postprocess-manifest.json 文件真实存在。
5. 对本次新增且有清洗转写稿的 B站和抖音视频，先完整读取 .agents\skills\video-transcript-doc-writer\SKILL.md 和 references\curation-json.md，然后逐条读取 speech-clean.txt。B站 record_id 和 clean_transcript_path 来自 *-bili-postprocess.json；抖音 record_id 来自 *-douyin-feishu-sync.json 的 created_videos，并按 aweme_id 匹配 *-douyin-latest-download.json 中的 transcript.speech_clean_path。
6. 按 skill 为每条视频生成 curation JSON，保存到 downloads\manifests\。每条记录必须同时包含 source_transcript_path、content_summary、key_points、quality_note 和 readable_sections。content_summary 与 key_points 必须来自本次对完整清洗稿的阅读，不得复制 postprocess\summary.md 或其他本地抽取式结果。
7. 口播稿（可读版）必须保持原始顺序、原意和说话风格，保留例子、步骤、数字、限制和结尾；不得把内容摘要或关键要点扩写成正文，也不得写成“作者认为”式第三人称摘要。计算去除空白后的可读版/清洗稿长度比例，通常不得低于 50%；低于 50% 默认视为摘要化失败并重写。确认 readable_sections 非空、章节标题具体、主要段落均被覆盖。
8. 对每个 record_id 先 dry-run，再把内容字段写回飞书：python .\write_transcript_content_to_feishu.py --curation-file <curation-json> --record-id <record_id> --dry-run；验证通过后去掉 --dry-run，并增加 --manifest-output <writeback-manifest>。检查 writeback manifest 为 updated=1、verified=1、failed=0；未通过写后回读校验时不得继续发布文档。
9. 字段写回验证成功后，对同一 record_id 先预览再发布：python .\publish_transcript_docs_to_feishu.py --record-id <record_id> --update-existing --curation-file <curation-json> --parent-position my_library --dry-run；预览成功后去掉 --dry-run，并增加 --manifest-output <doc-manifest>。检查发布 manifest 为 created=1 或 updated=1，且 failed=0；已有文档必须保持原 URL 不变。确认 Base 的 视频口播稿 字段已写入飞书文档 URL，文档中同时出现内容摘要、关键要点、口播稿（可读版）和原始转写稿与来源说明。
10. 最终用中文简洁报告：B站和抖音各自新增、跳过、失败数量，机器转写数量，内容字段写回/验证数量，可读版口播稿生成/发布数量，相关 manifest 路径，以及具体异常。不要输出 Cookie、签名 URL 或其他登录凭据。
```

这里的后处理不是把 ASR 文本直接上传，而是由 Codex 读取完整清洗稿后生成 curation JSON。发布后的飞书文档同时包含 `口播稿（可读版）` 和 `原始转写稿与来源说明`，便于阅读和追溯。
