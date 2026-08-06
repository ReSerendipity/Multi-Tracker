# Time Cost Notes

## Why the 2026-06-19 Full Run Took About One Hour

The expensive parts were Bilibili operations, not Feishu writes.

Primary costs:

1. Creator listing under Bilibili anti-bot limits.
   - Many `yt-dlp` space-list calls failed with Chrome cookie DPAPI errors or 412/352 responses.
   - The script then used Playwright-rendered search pages, which costs several seconds per creator.

2. Video download and merge.
   - Full backfill downloaded 69 videos.
   - Many downloads used the `bilibili-download` Web API fallback, then downloaded separate `.m4s` audio/video streams and merged with `ffmpeg`.

3. Retries and failed stream cases.
   - Some videos produced metadata/cover but no usable playurl stream.
   - The known failure from that run was `AI随风随风 / BV1v1Er6tE1n`.

4. Feishu write batching.
   - Feishu itself was not the hour-long bottleneck.
   - One issue was Windows command-line length for large JSON payloads; the project script now writes batch payloads to project-local `.tmp-lark/*.json` and passes `--json @relative-path`.

## Daily Check Expected Cost

After the baseline is in Feishu, most latest BVIDs should already exist, so daily runs should usually be much faster:

- If no creators updated, the run mostly pays listing cost.
- If a few creators updated, it pays listing cost plus only those downloads.
- `--only-today` prevents the daily task from filling historical gaps as if they were today's updates.

## Optimization Ideas

- Keep `视频` table populated with BVIDs so `skipped_existing` stops redundant downloads.
- Avoid relying on `--cookies-from-browser chrome`; use the public fallback paths unless the user explicitly provides a safe cookies file.
- If daily checks are still slow, add a separate lightweight listing cache per MID with last-seen BVIDs before attempting metadata/download.
