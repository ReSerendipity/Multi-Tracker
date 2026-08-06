# Curation JSON 规范

推荐格式：

```json
{
  "records": {
    "recxxxx": {
      "source_transcript_path": "downloads/videos/.../postprocess/speech-clean.txt",
      "content_summary": "简洁说明视频的主题、方法和结论。",
      "key_points": [
        "保留一个具体结论或方法。",
        "保留重要限制、数字或例子。"
      ],
      "quality_note": "由智能体在保持原意的前提下整理，并保守修正可确认的 ASR 错误。",
      "readable_sections": [
        {
          "heading": "具体的中文章节标题",
          "paragraphs": [
            "按原文顺序整理后的可读段落。",
            "保留例子、步骤和说话风格的下一段。"
          ]
        }
      ]
    }
  }
}
```

也可以直接使用 `record_id` 作为顶层键。

规则：

- `source_transcript_path`：推荐填写本次实际读取的清洗转写稿路径；写回脚本会验证文件存在。
- `content_summary`：必填，写入飞书 `内容摘要`；必须基于完整清洗稿，不得复制本地抽取式 `summary.md`。
- `key_points`：必填，字符串列表或非空文本，写入飞书 `关键要点`。
- `quality_note` 使用一句简洁中文说明生成方式及不确定的 ASR 内容。
- `readable_sections` 必填且不能为空。
- 每个章节必须包含非空的 `heading` 和 `paragraphs` 列表。
- 保持原文顺序，保留名称、数字、例子、步骤、限制、转折和结尾。
- 不得添加原文不存在的事实或观点。
- 压缩空白后的可读版长度通常不得低于清洗稿的 50%。
- 只有清洗稿确实存在大量重复时，才可设置 `"allow_short_readable": true`；此时必须在 `quality_note` 中说明压缩原因。
