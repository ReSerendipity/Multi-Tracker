---
name: video-transcript-doc-writer
description: "为 AI博主爬取 项目读取本地清洗转写稿，并在保持原意、顺序和说话风格的前提下，生成 publish_transcript_docs_to_feishu.py 所需的可读版口播稿 curation JSON。"
---

# 视频口播稿文档写作

## 目标

读取完整的 `speech-clean.txt`，一次生成 `内容摘要`、`关键要点` 和结构化的 `口播稿（可读版）`。本 skill 只生成 curation JSON；字段写回和飞书文档发布由项目脚本完成。

## 必要输入

- 飞书视频 `record_id`。
- 视频标题、平台、创作者和可用时的原视频 URL。
- 本地 `speech-clean.txt` 或飞书 `清洗文案路径`。
- 可用时的 `内容摘要`、`关键要点`，仅用于理解，不得直接扩写成正文。

## 工作流程

1. 完整读取清洗转写稿；长稿按原顺序分块，并维护连续大纲。
2. 按 `references/curation-json.md` 创建以 `record_id` 为键的 curation JSON：
   - `content_summary`：简洁说明视频讲了什么，不得照抄本地 `summary.md`。
   - `key_points`：保留具体结论、方法、限制或重要事实，不写空泛套话。
   - `readable_sections`：完整的可读版口播稿，不是摘要和要点的扩写。
3. 把零散口语整理成完整句子和有意义的章节：
   - 保持原始顺序、原意和第一人称/演示/评测口吻。
   - 保留产品名、数字、例子、操作步骤、限制、转折和结论。
   - 只修正上下文能够确认的 ASR 错误；不确定内容保留原词并写进 `quality_note`。
   - 不得写成第三人称摘要，不使用反复的“作者认为”“作者说”。
4. 将 JSON 保存到 `downloads/manifests/`，使用可识别的文件名。
5. 检查压缩空白后的可读版长度。通常不得低于原清洗稿的 50%；低于 50% 默认视为摘要化失败并重写。只有原稿大量重复时才允许更短，并在 `quality_note` 说明。
6. 先预览，再把摘要和关键要点写回飞书视频表：

```powershell
python .\write_transcript_content_to_feishu.py --curation-file <curation-json> --record-id <record_id> --dry-run
python .\write_transcript_content_to_feishu.py --curation-file <curation-json> --record-id <record_id> --manifest-output <writeback-manifest>
```

7. 确认写回 manifest 为 `updated=1`、`verified=1`、`failed=0` 后，先预览，再创建飞书文档：

```powershell
python .\publish_transcript_docs_to_feishu.py --record-id <record_id> --update-existing --curation-file <curation-json> --parent-position my_library --dry-run
python .\publish_transcript_docs_to_feishu.py --record-id <record_id> --update-existing --curation-file <curation-json> --parent-position my_library --manifest-output <manifest-json>
```

8. 核验发布 manifest：`created=1` 或 `updated=1`，且 `failed=0`；确认 Base 的 `内容摘要`、`关键要点` 和 `视频口播稿` URL 均已写入。更新已有文档时 URL 必须保持不变。

## 写作标准

- 短视频通常使用 4-8 个具体章节；10-20 分钟的教程、评测或叙事视频通常需要 10 个以上章节。
- 每段优先控制在 80-220 个中文字符，但完整性优先。
- 叙事类内容按剧情推进，保留因果关系、人物行为、冲突、反转和结局。
- 教程/评测按操作或论证推进，保留前提、步骤、设置、例子、结果、限制和作者判断。
- 不得用“整理稿”“首先”“然后”“总结”等空泛标题凑章节。
- 可读版必须能够逐段对应回原始口播，不能只剩核心观点。
