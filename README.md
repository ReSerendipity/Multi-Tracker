# AI博主爬取

Local ingestion scripts for tracking AI creators on Bilibili and Douyin, downloading recent videos, creating transcript artifacts, and syncing selected metadata back to Feishu Base.

## What Is Included

- `download_bili_following_latest.py`: load tracked Bilibili creators from Feishu Base, download latest videos, collect first-stage metadata, and write task records.
- `postprocess_bili_videos.py`: backfill Bilibili subtitles or Whisper transcripts for local downloads.
- `sync_bilibili_comments_to_feishu.py`: fetch and sync representative Bilibili comments into Feishu.
- `download_douyin_latest.py`: download latest videos from configured Douyin creators.
- `sync_douyin_to_feishu.py`: sync local Douyin download artifacts into Feishu.
- `enrich_douyin_feishu.py`: backfill Douyin insight fields from local artifacts.
- `publish_transcript_docs_to_feishu.py`: create Feishu docs from local transcripts and write document URLs back to Base.
- `.agents/skills/`: project-local Codex skills for repeated crawl/comment workflows.

## Local Setup

1. Copy the example config and fill in local Feishu Base values:

   ```powershell
   Copy-Item .\feishu-base-config.example.json .\feishu-base-config.json
   ```

2. Make sure the external CLIs used by the workflows are available in your shell:

   - `python`
   - `lark-cli`
   - `ffmpeg`
   - `yt-dlp` or the project Bilibili download backend
   - `whisper` for ASR post-processing
   - `node` for CDP-based comment tools

3. Runtime outputs are intentionally ignored by git. Downloaded media, transcripts, manifests, browser profiles, QR codes, and local Feishu config stay on the local machine.

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

Preview transcript doc publishing without writing Feishu:

```powershell
python .\publish_transcript_docs_to_feishu.py --dry-run
```
