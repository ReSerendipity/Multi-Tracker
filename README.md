# AI博主爬取

Local ingestion scripts for tracking AI creators on Bilibili, Douyin, Xiaohongshu, and Kuaishou, downloading recent videos, creating transcript artifacts, and syncing selected metadata back to Feishu Base.

## What Is Included

- `download_bili_following_latest.py`: load tracked Bilibili creators from Feishu Base, download latest videos, collect first-stage metadata, and write task records.
- `postprocess_bili_videos.py`: backfill Bilibili subtitles or Whisper transcripts for local downloads.
- `sync_bilibili_comments_to_feishu.py`: fetch and sync representative Bilibili comments into Feishu.
- `download_douyin_latest.py`: download latest videos from configured Douyin creators.
- `sync_douyin_to_feishu.py`: sync local Douyin download artifacts into Feishu.
- `enrich_douyin_feishu.py`: backfill Douyin insight fields from local artifacts.
- `download_xiaohongshu_latest.py`: download latest videos from configured Xiaohongshu creators.
- `sync_xiaohongshu_to_feishu.py`: sync local Xiaohongshu download artifacts into Feishu.
- `download_kuaishou_latest.py`: download latest videos from configured Kuaishou creators.
- `sync_kuaishou_to_feishu.py`: sync local Kuaishou download artifacts into Feishu.
- `write_transcript_content_to_feishu.py`: write agent-authored transcript summaries and key points to Feishu, then verify them by readback.
- `publish_transcript_docs_to_feishu.py`: create or update Feishu docs from local transcripts and write document URLs back to Base.
- `.agents/skills/video-transcript-doc-writer/`: turn cleaned transcripts into structured, readable spoken-script curation JSON.
- `.agents/skills/`: project-local Codex skills for repeated crawl/comment workflows.

## Source of Truth (Authoritative Files)

This repository intentionally keeps **three git-tracked copies** of the core
download/sync scripts, so searching by filename returns several hits. Only one
is authoritative; the other two are **read-only export snapshots**. Always edit
the root copy, and only re-copy into a snapshot when it needs refreshing.

- **Authoritative source — the repository root** (this directory, next to
  `README.md`, `start.ps1`, `requirements.txt`). The files to change are the
  root-level `download_douyin_latest.py`, `sync_douyin_to_feishu.py`,
  `download_bili_following_latest.py`, `sync_bilibili_comments_to_feishu.py`, and so on.
- `分享包_多平台博主追踪系统/` — a **share/submission export bundle** (its own
  `README.md` says it is packaged for a TraeWork 活动投稿分享; it carries its own
  `LICENSE.md`, `CONTRIBUTING.md`, `docs/`, and a full copy of `.agents/skills/`).
  Generated output; regenerate by copying from root.
- `repro-package/` — a **minimal B站 reproduction extract** (its `README.md` calls it
  “从完整项目里提取的 B站最小可用版本”; only a few scripts). Regenerate by copying from root.

For any script, the authoritative path is the repository-root file; every copy
under `分享包_多平台博主追踪系统/` or `repro-package/` is a downstream snapshot of that root file.
The root `.agents/skills/` tree is likewise the authoritative skills source.
See [`AGENTS.md`](./AGENTS.md) for the full rule.

## Local Setup

1. Create a virtual environment and install the Python dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Copy the example config and fill in local Feishu Base values:

   ```powershell
   Copy-Item .\feishu-base-config.example.json .\feishu-base-config.json
   ```

3. Make sure the external CLIs used by the workflows are available in your shell:

   - `python`
   - `lark-cli`
   - `ffmpeg`
   - `yt-dlp` or the project Bilibili download backend
   - `whisper` for ASR post-processing
   - `node` for CDP-based comment tools

4. Verify the environment before the first run:

   ```powershell
   python .\check_environment.py
   ```

5. Runtime outputs are intentionally ignored by git. Downloaded media, transcripts, manifests, browser profiles, QR codes, and local Feishu config stay on the local machine.

## Common Commands

Run the cross-platform latest-video workflow:

```powershell
python .\download_all_platform_latest.py --platform all
```

Run Bilibili latest-video ingestion only:

```powershell
python .\download_bili_following_latest.py --videos-per-creator 3
```

Run Bilibili transcript post-processing:

```powershell
python .\postprocess_bili_videos.py --model large-v3-turbo --device cuda
```

Run Douyin latest-video download:

```powershell
python .\download_douyin_latest.py --videos-per-creator 1
```

Run Xiaohongshu latest-video download:

```powershell
python .\download_xiaohongshu_latest.py --from-feishu --videos-per-creator 1
```

Run Kuaishou latest-video download:

```powershell
python .\download_kuaishou_latest.py --from-feishu --videos-per-creator 1
```

Preview transcript content writeback and doc publishing without writing Feishu:

```powershell
python .\write_transcript_content_to_feishu.py --curation-file .\downloads\manifests\YOUR_CURATION.json --record-id YOUR_RECORD_ID --dry-run
python .\publish_transcript_docs_to_feishu.py --record-id YOUR_RECORD_ID --update-existing --curation-file .\downloads\manifests\YOUR_CURATION.json --parent-position my_library --dry-run
```

## Codex Automation Example

See [`CODEX_AUTOMATION_EXAMPLE.md`](./CODEX_AUTOMATION_EXAMPLE.md) for a Codex App daily automation example covering Bilibili/Douyin ingestion, machine transcription, agent-written readable spoken scripts, Feishu document publishing, manifest verification, and concise failure reporting.

## License

Released under the [Apache License 2.0](./LICENSE). Copyright 2026 ReSerendipity.
