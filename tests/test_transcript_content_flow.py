import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import publish_transcript_docs_to_feishu as publisher
import write_transcript_content_to_feishu as writeback


class TranscriptContentWritebackTests(unittest.TestCase):
    def test_normalize_record_uses_same_curation_for_fields_and_doc(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "speech-clean.txt"
            source.write_text("完整清洗稿。", encoding="utf-8")
            item = writeback.normalize_record(
                "rec-test",
                {
                    "source_transcript_path": str(source),
                    "content_summary": "视频介绍了一套可验证的处理方法。",
                    "key_points": ["先读取完整转写稿", "写回后必须重新读取核验"],
                    "readable_sections": [{"heading": "处理方法", "paragraphs": ["完整的可读版段落。"]}],
                },
            )
        self.assertEqual(item["record_id"], "rec-test")
        self.assertEqual(item["content_summary"], "视频介绍了一套可验证的处理方法。")
        self.assertEqual(item["key_points"], "- 先读取完整转写稿\n- 写回后必须重新读取核验")

    def test_missing_summary_fails_before_remote_write(self):
        with self.assertRaisesRegex(ValueError, "content_summary is required"):
            writeback.normalize_record(
                "rec-test",
                {
                    "content_summary": "",
                    "key_points": ["要点"],
                    "readable_sections": [{"heading": "章节", "paragraphs": ["段落"]}],
                },
            )

    def test_short_readable_version_fails_before_remote_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "speech-clean.txt"
            source.write_text("这是一段需要完整保留的原始口播内容。" * 20, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ratio is below 0.5"):
                writeback.normalize_record(
                    "rec-test",
                    {
                        "source_transcript_path": str(source),
                        "content_summary": "测试摘要。",
                        "key_points": ["测试要点。"],
                        "readable_sections": [{"heading": "过度摘要", "paragraphs": ["太短。"]}],
                    },
                )

    def test_readback_mismatch_is_reported(self):
        items = [
            {
                "record_id": "rec-test",
                "content_summary": "预期摘要",
                "key_points": "- 预期要点",
            }
        ]
        verified, failures = writeback.verify_readback(
            items,
            {"rec-test": {"_record_id": "rec-test", "内容摘要": "其他摘要", "关键要点": "- 预期要点"}},
        )
        self.assertEqual(verified, [])
        self.assertEqual(failures[0]["error"], "readback mismatch")
        self.assertFalse(failures[0]["summary_matches"])

    def test_cli_dry_run_validates_without_loading_feishu_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "speech-clean.txt"
            source.write_text("完整清洗稿。", encoding="utf-8")
            curation_path = root / "curation.json"
            curation_path.write_text(
                """{
  "records": {
    "rec-test": {
      "source_transcript_path": "%s",
      "content_summary": "测试摘要。",
      "key_points": ["测试要点。"],
      "readable_sections": [{"heading": "测试章节", "paragraphs": ["测试段落。"]}]
    }
  }
}""" % str(source).replace("\\", "\\\\"),
                encoding="utf-8",
            )
            manifest_path = root / "dry-run-manifest.json"
            argv = [
                "write_transcript_content_to_feishu.py",
                "--curation-file",
                str(curation_path),
                "--dry-run",
                "--manifest-output",
                str(manifest_path),
            ]
            with mock.patch("sys.argv", argv), mock.patch.object(
                writeback.base,
                "load_config",
                side_effect=AssertionError("dry-run must not load Feishu config"),
            ):
                self.assertEqual(writeback.main(), 0)
            manifest = writeback.json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["summary"]["planned"], 1)
        self.assertEqual(manifest["summary"]["updated"], 0)
        self.assertEqual(manifest["summary"]["failed"], 0)

    def test_published_doc_contains_fields_readable_version_and_raw_transcript(self):
        row = {
            "_record_id": "rec-test",
            "视频标题": "测试视频",
            "平台": "B站",
            "BVID": "BVTEST",
            "平台视频ID": "BVTEST",
            "内容摘要": "这是写回后的摘要。",
            "关键要点": "- 第一个要点\n- 第二个要点",
            "关联博主": [],
        }
        curation = {
            "quality_note": "由智能体基于完整清洗稿整理。",
            "readable_sections": [{"heading": "具体章节", "paragraphs": ["整理后的可读段落。"]}],
        }
        xml = publisher.build_doc_xml(
            row,
            "清洗文案路径",
            Path("speech-clean.txt"),
            "原始转写段落。",
            {},
            curation,
        )
        for expected in [
            "<h2>内容摘要</h2>",
            "这是写回后的摘要。",
            "<h2>关键要点</h2>",
            "<h2>口播稿（可读版）</h2>",
            "<h2>原始转写稿与来源说明</h2>",
            "原始转写段落。",
        ]:
            self.assertIn(expected, xml)

    def test_existing_doc_can_be_previewed_for_in_place_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "speech-clean.txt"
            transcript.write_text("原始转写段落。", encoding="utf-8")
            row = {
                "_record_id": "rec-test",
                "视频标题": "测试视频",
                "平台": "B站",
                "BVID": "BVTEST",
                "平台视频ID": "BVTEST",
                "内容摘要": "测试摘要。",
                "关键要点": "- 测试要点",
                "清洗文案路径": str(transcript),
                "视频口播稿": "https://example.feishu.cn/docx/existing",
                "关联博主": [],
            }
            curation = {
                "quality_note": "由智能体基于完整清洗稿整理。",
                "readable_sections": [{"heading": "具体章节", "paragraphs": ["整理后的可读段落。"]}],
            }
            args = SimpleNamespace(
                curation_file="curation.json",
                overwrite=False,
                update_existing=True,
                dry_run=True,
                retry_attempts=1,
                retry_delay_seconds=0,
                parent_token=None,
                parent_position="my_library",
            )
            result = publisher.process_row({}, row, {}, {"rec-test": curation}, args)
        self.assertEqual(result["status"], "updated")
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["will_update_existing"])
        self.assertEqual(result["doc_url"], "https://example.feishu.cn/docx/existing")


if __name__ == "__main__":
    unittest.main()
