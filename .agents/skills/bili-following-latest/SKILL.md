---
name: bili-following-latest
description: Run the AI博主爬取 project workflow that downloads the latest Bilibili videos for Feishu Base creators marked 是否持续跟踪=true, writes successful downloads to the Feishu 视频 table, and writes a 爬取任务日志 record. Use when the user asks to crawl/download/update tracked Bilibili creators, 最新三条视频, 持续跟踪博主, or rerun the current project's Feishu+Bilibili batch pipeline.
---

# Bili Following Latest

## Scope

Use this skill only in `%PROJECTS%\codexProjects\AI博主爬取`.

The reusable implementation is the project script:

```powershell
python .\download_bili_following_latest.py
```

It reads `feishu-base-config.json`, loads creators from the Feishu `博主` table where `是否持续跟踪=true`, lists each creator's latest videos, downloads missing BVIDs to `downloads/videos/<MID>/<BVID>/`, writes new rows to the Feishu `视频` table, and writes one row to `爬取任务日志`.

For each new downloaded video, the script also writes first-stage enrichment artifacts:

- `video-description.txt` from Bilibili投稿简介/文案
- `metrics-snapshot.json` from metadata `raw.data.stat`
- `comments.json` from the Bilibili reply API, unless `--skip-comments` is used
- `subtitles/` from `bilibili-download` when Bilibili exposes manual or auto subtitles
- one linked row in the Feishu `视频数据快照` table

The public reply API can expose the total reply count while returning only a small visible subset of comment bodies. Check `comments.json` fields `total_count`, `fetched_count`, and `partial`; `partial=true` means a logged-in/WBI-signed comment crawler is needed for full comment text.

When syncing full logged-in comments into Feishu, keep complete raw comments in local JSONL and write only a bounded representative subset to the `视频评论` table by default. The subset is deduplicated by normalized comment text before writing. Use `sync_bilibili_comments_to_feishu.py --max-comment-table-rows 30` for normal runs; use `--max-comment-table-rows -1` only for an intentional full detail backfill.

## Postprocess Policy

Use the project postprocess script for local audio/subtitle transcript and transcript-artifact backfill:

```powershell
python .\postprocess_bili_videos.py --model small --device cuda
```

Current policy:

- Prefer source subtitles from the downloaded `subtitles/` directory. If usable subtitles exist, write `speech-raw.txt`, `speech-clean.txt`, and local reference notes from subtitles and do not run Whisper.
- If no usable source subtitles exist, run Whisper ASR only when `时长秒 <= 3600` by default.
- Videos over 1 hour without usable source subtitles should be marked `转写状态=无需转写`; do not use `--include-long` unless the user explicitly overrides this policy.
- This machine has a CUDA-capable NVIDIA GPU; use `--device cuda` for ASR unless debugging CPU behavior.
- The Feishu fields `内容摘要` and `关键要点` are agent-authored fields. Do not populate them from the local extractive script output. When the user asks for these fields, read `postprocess/speech-clean.txt` yourself, synthesize a concise content summary and opinion-level bullet points, then write those fields explicitly.

## Required Skills

Before editing or debugging this workflow, read:

- `%USERPROFILE%\.agents\skills\lark-base\SKILL.md`
- `%USERPROFILE%\.agents\skills\bilibili-download\SKILL.md`

The batch script already embeds the important environment hygiene for `lark-cli`: remove `HERMES_HOME` and `HERMES_GIT_BASH_PATH`, set `LARK_CLI_NO_PROXY=1`, and force UTF-8 for Python subprocesses.

## Normal Workflow

1. Work from the project root:

```powershell
Set-Location '%PROJECTS%\codexProjects\AI博主爬取'
```

2. Confirm dependencies and syntax:

```powershell
python -m py_compile .\download_bili_following_latest.py
lark-cli --profile cli_a974a338c2f85cb2 auth status --verify
```

3. Run a one-video smoke test when the pipeline has changed:

```powershell
python .\download_bili_following_latest.py --max-creators 1 --max-total-videos 1 --retries 1
```

4. Run the full batch:

```powershell
python .\download_bili_following_latest.py --retries 1
```

To backfill first-stage enrichment for videos that are already in the Feishu `视频` table and already have local metadata:

```powershell
python .\download_bili_following_latest.py --enrich-existing --comment-limit 50
```

Use `--max-existing-videos N` for a small verification run, and `--skip-comments` when only local description/cover/metric snapshots should be filled.

5. Report these fields from the latest manifest:

- downloaded
- failed
- skipped_existing
- created_video_records
- created_metric_snapshots
- manifest path
- failure examples

## Script Behavior

The script currently uses this fallback order:

1. `yt-dlp` flat playlist for a creator's Bilibili space.
2. Playwright-rendered Bilibili search page filtered to cards whose author text matches the creator name.
3. For each video, the `bilibili-download` script at `%USERPROFILE%\.agents\skills\bilibili-download\scripts\download_bilibili.py`.
4. That download script falls back from `yt-dlp` 412 errors to Bilibili Web APIs and `ffmpeg` merge.
5. After media and metadata exist, the project script extracts Bilibili description, cover path, comment JSON, and metric snapshot artifacts.
6. After Feishu `视频` rows are created, it writes linked `视频数据快照` rows using the created video record IDs.

Do not rely on `yt-dlp --cookies-from-browser chrome` as the only path. On this machine it has failed with Chrome Cookie DPAPI/decryption errors. Do not print, export, or persist Cookie plaintext.

## Output Contract

Successful videos should have:

- media under `downloads/videos/<MID>/<BVID>/`
- compatible metadata file `downloads/videos/<MID>/<BVID>/<BVID>.info.json`
- Feishu `视频` row with `BVID`, `关联博主`, `视频文件路径`, `元数据文件路径`, `视频下载状态=已下载`
- Feishu `视频` row enriched with `视频文案路径`, `封面文件路径`, `评论文件路径`, `评论抓取状态`, and `已抓评论数`
- linked Feishu `视频数据快照` row with 播放量、点赞量、投币数、收藏数、分享数、评论数、弹幕数
- manifest under `downloads/manifests/`
- one task log row in `爬取任务日志`

## Verification

After a full run, verify:

```powershell
@'
import json, pathlib, collections
import download_bili_following_latest as d
m = max(pathlib.Path('downloads/manifests').glob('*-bili-latest-download.json'), key=lambda p: p.stat().st_mtime)
man = json.loads(m.read_text(encoding='utf-8'))
missing = [s for s in man['successes'] if not pathlib.Path(s['video_path']).exists() or not pathlib.Path(s['info_path']).exists()]
cfg = d.load_config()
rows = d.list_records(cfg, cfg['tables']['videos']['table_id'], ['BVID'])
counts = collections.Counter(str(r.get('BVID') or '').strip() for r in rows if r.get('BVID'))
print(json.dumps({'manifest': str(m), 'summary': man['summary'], 'missing_local_success_files': len(missing), 'duplicate_bvids': {k:v for k,v in counts.items() if v > 1}}, ensure_ascii=False, indent=2))
'@ | python -
```

Also inspect the latest task log row if the user asks for Feishu-side proof.

## Known Failure Modes

See `references/run-notes.md` for details from the 2026-06-19 successful run.

Handle failures conservatively:

- If Bilibili list APIs return 412/352/403, use the script's Playwright search fallback; do not use broad keyword results that can mix other authors.
- If a video's playurl API returns no usable stream, keep it as a failure unless the user provides a logged-in cookies file or explicitly asks for a retry strategy.
- If `lark-cli` rejects `@file`, ensure payload files are relative to the project root, not absolute temp paths.
- If Windows reports command line length errors, write batch payloads to project-local JSON files and pass `--json @relative-path`.
