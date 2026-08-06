---
name: bili-daily-update-check
description: Check whether Feishu Base creators marked 是否持续跟踪=true published Bilibili videos today using Trae Work, download only today's new videos, write successful rows to the Feishu 视频 table, and write a 爬取任务日志 record. Use when the user asks for 当天更新检查，今日新增视频，每日增量爬取，or to check followed/tracked Bilibili creators for new videos today.
---

# Bili Daily Update Check - Trae Work Skill

## Scope

Use this skill in the current project root directory.

This skill reuses the project script:

```powershell
python .\download_bili_following_latest.py
```

Daily mode must use `--only-today`. This keeps the run focused on videos whose metadata publish date is today's local date and prevents historical missing videos from being written as daily updates.

## Required Skills

Before debugging or changing the workflow, read:

- `.\.agents\skills\lark-base\SKILL.md`
- `.\.agents\skills\bilibili-download\SKILL.md`

The broader baseline/full-backfill workflow is documented in sibling project skill:

- `.agents\skills\bili-following-latest\SKILL.md`

## Daily Pipeline

Run from the project root:

```powershell
Set-Location 'Current Project Directory'
python .\download_bili_following_latest.py --only-today --retries 1
```

By default, each newly downloaded video also gets first-stage enrichment:

- local `video-description.txt`
- local cover path from the downloaded cover file
- local `comments.json` with up to 50 top-level comments
- local `metrics-snapshot.json`
- local `subtitles/` files when Bilibili exposes manual or auto subtitles
- a linked row in the Feishu `视频数据快照` table

The public reply API can expose the total reply count while returning only a small visible subset of comment bodies. Check `comments.json` fields `total_count`, `fetched_count`, and `partial`; `partial=true` means full comment text still needs a logged-in/WBI-signed comment crawler.

Use this when comments should be skipped for speed or because Bilibili blocks the reply API:

```powershell
python .\download_bili_following_latest.py --only-today --skip-comments --retries 1
```

For a specific date, use:

```powershell
python .\download_bili_following_latest.py --only-today --published-date 2026-06-19 --retries 1
```

After the daily download finishes, run postprocessing for BVIDs from the latest download manifest:

```powershell
python .\postprocess_bili_videos.py --latest-download-manifest --model small --device cuda
```

Then, for each newly postprocessed video with `postprocess/speech-clean.txt`, the Trae Work automation should read the cleaned 口播稿 itself and write these Feishu `视频` fields as authored content:

- `内容摘要`
- `关键要点`

Do not copy `postprocess/summary.md` into those fields. That file is local extractive reference material only.

Finally, collect comment insight for the same latest-download manifest:

```powershell
python .\sync_bilibili_comments_to_feishu.py --latest-download-manifest --max-comment-table-rows 30 --delay-ms 5000 --reply-delay-ms 2000 --api-retries 3 --retry-delay-ms 60000 --stop-after-412 2
```

Comment storage policy:

- Full fetched comments are kept locally as JSONL under `downloads/comments/<BVID>/`.
- Feishu `视频评论` stores only a bounded representative subset by default: high-like comments, pain points, controversy, and topic leads. Rows are deduplicated by normalized comment text before writing.
- The `视频` table stores the human-facing fields: `高赞评论摘要`, `用户痛点`, `评论里的争议点`, `可延展选题`, `代表评论`, `评论明细入表数`, and `评论存储策略`.
- Use `--max-comment-table-rows -1` only for a deliberate full comment-table backfill.

Postprocess policy:

- Prefer downloaded source subtitles and skip Whisper when usable subtitles exist.
- If no usable source subtitles exist, run Whisper ASR only for videos up to 1 hour (`--max-duration-seconds 3600` is the default).
- Videos over 1 hour without usable source subtitles should stay `转写状态=无需转写`; do not pass `--include-long` unless the user explicitly asks.

Use a smoke run only after code changes:

```powershell
python .\download_bili_following_latest.py --only-today --max-creators 1 --max-total-videos 1 --retries 1
```

## Behavior

The script still checks each tracked creator's latest 3 Bilibili videos and skips any BVID already in the Feishu `视频` table.

For a new BVID:

1. Download through the `bilibili-download` backend.
2. Read compatible metadata from `<BVID>.info.json`.
3. If `--only-today` is enabled and `发布时间` date is not the target date, record it as `skipped_not_today` in the manifest and do not write a Feishu `视频` row.
4. If it is today's video, write local description, metrics, cover, and comments artifacts.
5. Write the `视频` row and include `关联博主`, local media path, metadata path, download status, description path, cover path, comments path, comment status, and fetched comment count.
6. After video rows are created, write linked `视频数据快照` rows.
7. Write one `爬取任务日志` row at the end.
8. Postprocess new videos from the latest manifest into local口播稿 artifacts.
9. Agent reads the cleaned口播稿 and writes `内容摘要` / `关键要点`.
10. Sync bounded comment insights and representative comments for the same latest manifest.

## Expected Report

Report the latest manifest summary:

- `downloaded`: new videos published on the target date and written to Feishu
- `skipped_existing`: BVIDs already in Feishu
- `skipped_not_today`: new/unwritten BVIDs found but published outside the target date
- `failed`: list/download/write failures
- `created_video_records`: Feishu `视频` rows created
- `created_metric_snapshots`: Feishu `视频数据快照` rows created
- postprocess summary: processed / skipped / failed
- content field update count: `内容摘要` / `关键要点`
- comment sync summary: processed / failed / fetched_rows / new_rows / representative rows written
- manifest path
- failure examples

## Verification

After a run, verify local files and duplicates:

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

## Time Cost Model

Read `references/time-cost.md` when explaining runtime or optimizing the daily check.

The short version:

- Listing latest videos can be slow when Bilibili rejects space APIs and the script falls back to Playwright search pages.
- Downloading and ffmpeg merging is the main cost when many videos are new.
- Comment fetching adds one or more Bilibili reply API calls per new video. It is non-fatal and can be disabled with `--skip-comments`.
- Feishu writes are usually minor, but Windows command-line length requires project-local `@json` payload files.

## Boundaries

- Do not print, export, or persist Cookie plaintext.
- Do not widen search terms to force a third result; only write rows when author matching is reliable.
- Comment fetching is best-effort. A comment API failure should write `评论抓取状态=失败` and keep the video record valid. A `partial=true` comments file is a partial success, not a fatal failure.
- Keep Feishu writes under `lark-cli --profile cli_a974a338c2f85cb2 ... --as user`.
- If user auth expires, recover user auth rather than falling back to bot writes.
