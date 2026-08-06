---
name: douyin-comments
description: Fetch and export structured comments from a Douyin video only through the user's already logged-in Chrome/CDP browser session. Use when the user provides a Douyin video URL, aweme_id, or an existing downloaded Douyin video directory and asks to crawl, download, save, export, inspect, or prepare comments without writing Feishu; abort rather than fetching public/limited samples when login state is unavailable.
---

# Douyin Comments - Trae Work Skill

Use this skill with Trae Work to fetch Douyin video comments into local JSON/JSONL files. A logged-in Douyin browser session is mandatory; public/limited non-login samples are not useful for this workflow. Keep it isolated from the Bilibili workflow and from the existing Douyin download/Feishu sync pipeline unless the user explicitly asks to integrate it later.

## Workflow

1. Require the user's existing Chrome session with Douyin login state and remote debugging enabled. For large/comment-tree captures, use the project-local CDP bridge at `http://127.0.0.1:3457`; it keeps one browser-level CDP connection alive so repeated runs do not repeatedly ask for Chrome remote-debugging authorization. Do not export, print, or save cookies.
2. Before fetching comments, run `--check-login-only` when the CDP port or browser profile is uncertain.
3. Run the bundled Python script with one of:
   - `--video-url "https://www.douyin.com/video/<aweme_id>"`
   - `--aweme-id <aweme_id>`
   - `--video-dir "<downloaded Douyin video directory>"`
   For large videos or when reply threads matter, prefer the bundled Node CDP script. It auto-starts the local bridge when needed:
   - `node scripts\fetch_douyin_comments_cdp.mjs --video-url "https://www.douyin.com/video/<aweme_id>" --out-dir "<dir>"`
4. Save results locally first. Do not write Feishu by default.
5. Use conservative request pacing. Do not run tight loops against Douyin comment endpoints.
6. Report the JSONL path, JSON bundle path, manifest path, comment count, API pagination state, and any login/anti-bot/reply-fetch limitations.

## Quick Start

Check that `9222` is a logged-in Douyin browser before fetching:

```powershell
python .\scripts\fetch_douyin_comments.py --aweme-id 7649032724493192486 --cdp-port 9222 --check-login-only
```

```powershell
python .\scripts\fetch_douyin_comments.py --aweme-id 7649032724493192486 --out-dir .\downloads\douyin\douyin_creator_2\7649032724493192486\comments --max-comments 50 --max-pages 3 --cdp-port 9222
```

Start the local CDP bridge once if you want to keep the authorization stable across many runs:

```powershell
node .\scripts\douyin_cdp_bridge.mjs
```

Large-video comment tree capture through the persistent CDP bridge:

```powershell
node .\scripts\fetch_douyin_comments_cdp.mjs --video-url "https://www.douyin.com/video/7634931976520224043" --out-dir .\downloads\douyin-comments\7634931976520224043-cdp-node-full --page-size 50 --reply-batch-size 10 --delay-ms 500 --batch-delay-ms 3000
```

Use a downloaded video directory when available:

```powershell
python .\scripts\fetch_douyin_comments.py --video-dir .\downloads\douyin\douyin_creator_2\7649032724493192486 --max-comments 50 --max-pages 3 --cdp-port 9222
```

Preview the resolved target without fetching:

```powershell
python .\scripts\fetch_douyin_comments.py --video-url "https://www.douyin.com/video/7649032724493192486" --out-dir .\downloads\douyin-comments\7649032724493192486 --dry-run
```

## Script Options

- `--video-url <url>`: Douyin video URL. Short links are not resolved by this script; open them in the browser first or provide the final `/video/<aweme_id>` URL.
- `--aweme-id <id>`: Douyin aweme id.
- `--video-dir <dir>`: Existing downloaded Douyin video directory. The script reads `manifest.json` or `metadata.json` to find `aweme_id` and `video_url`.
- `--out <file>`: JSONL output path. When omitted, the script writes `comments.jsonl` under the output directory.
- `--out-dir <dir>`: Output directory. Defaults to `<video-dir>\comments` when `--video-dir` is used, otherwise `downloads\douyin-comments\<aweme_id>`.
- `--max-comments <n>`: Stop after this many rows. `0` means no explicit row cap.
- `--max-pages <n>`: Maximum root-comment pages to request.
- `--page-size <n>`: Root-comment page size, default `20`.
- `--cdp-proxy-url <url>`: Optional `web-access` CDP Proxy URL. Default is `http://127.0.0.1:3456`; pass an empty string to disable proxy use.
- `--cdp-host <host>` and `--cdp-port <port>`: Raw Chrome DevTools endpoint used as a fallback. Default is `127.0.0.1:9222`, the expected logged-in daily Chrome session.
- `--delay-ms <n>`: Delay between API pages, default `1500`.
- `--jitter-ms <n>`: Extra random delay up to this many milliseconds, default `700`.
- `--require-login` / `--no-require-login`: Login is required by default. Use `--no-require-login` only for diagnostics; do not use it for real comment collection.
- `--include-replies`: Also call reply endpoints for root comments with replies. Off by default because Douyin reply endpoints are more likely to hang or trigger anti-bot checks.
- `--no-replies`: Compatibility alias for root-comment-only mode.
- `--reply-max-pages <n>`: Maximum reply pages per root comment when `--include-replies` is enabled.
- `--request-timeout-ms <n>`: Browser-side fetch timeout for each API request.
- `--check-login-only`: Open the Douyin page and verify login state without calling comment APIs.
- `--dry-run`: Resolve inputs and output paths without opening Chrome or writing files.
- `--keep-tab`: Leave the temporary Douyin tab open for manual debugging.

Node CDP script options:

- `--bridge-url <url>`: Local persistent CDP bridge URL. Default is `http://127.0.0.1:3457`, or `DOUYIN_CDP_BRIDGE_URL` when set.
- `--direct-cdp`: Diagnostic mode only. It connects directly to Chrome's browser-level DevTools websocket for that single process and can trigger repeated Chrome remote-debugging authorization prompts on repeated runs.
- `--eval-timeout-ms <n>`: Maximum browser evaluation time for root/reply batches, default `300000`.
- `--reply-batch-size <n>`: Number of root comments with missing replies to process per browser evaluation batch.
- `--batch-delay-ms <n>`: Delay between reply batches. Keep this conservative for Douyin.

## Output Schema

Each JSONL row is one comment or reply:

```json
{
  "comment_id": "7652699611227964219",
  "text": "评论正文",
  "user_name": "用户名",
  "user_id": "435843912701303",
  "sec_uid": "MS4w...",
  "like_count": 1,
  "reply_count": 0,
  "create_time": 1781782977,
  "ip_label": "福建",
  "parent_id": null,
  "aweme_id": "7649032724493192486",
  "level": 1,
  "raw": {}
}
```

Unavailable fields are `null`. The script also writes:

- `comments.jsonl`: one JSON row per comment/reply.
- `comments.json`: bundle with run metadata and all rows.
- `comments-manifest.json`: counts, API paging state, output paths, errors, and limitation notes.

The Node CDP script writes:

- `comments-root.json`: root comment API result and reported total.
- `reply-batch-*.json`: per-batch signed reply fetch results.
- `comments-all.json`: merged root and reply rows plus counts and reply errors.
- `comments-all.jsonl`: one merged comment/reply row per line.
- `comments-all.csv`: spreadsheet-friendly export.
- `metadata.json`: run metadata and final counts.

## Reliability Notes

- The script calls Douyin's web comment API from inside the opened Douyin page with `credentials: "include"`, so Chrome supplies the browser session without exposing cookie values to disk or stdout.
- The script first tries `web-access` CDP Proxy at `http://127.0.0.1:3456`, because that path reuses the user's authorized daily Chrome connection and port-guard behavior. If the proxy is unavailable, it falls back to raw Chrome DevTools.
- In raw CDP fallback mode, if `9222` returns `404` for `/json/version`, it tries the `DevToolsActivePort` websocket path used by Chrome's browser-level debugger.
- Confirm the CDP port belongs to the logged-in Chrome profile. A temporary `cdp-skill-chrome-profile-<port>` session is not the user's normal logged-in Chrome and must not be used unless the user logged into Douyin there too.
- If the page shows `请先登录后发表评论` or `登录后即可参与互动讨论`, the script aborts before calling comment APIs. Do not fall back to treating `metadata.json.page_metadata.body_excerpt` as comments.
- If the API returns empty data, CAPTCHA, or nonzero `status_code`, report that as an access/fengkong condition.
- Reply endpoints can be more brittle than the root list endpoint. Only enable them with `--include-replies`; replies are fetched after root comments, one root comment at a time with pacing between calls. When reply fetches fail or time out, keep root comments and record reply errors in the manifest.
- For large videos, use `fetch_douyin_comments_cdp.mjs`. It follows the older `douyin-video-capture` approach: root comments from `/comment/list/`, reply threads from signed `/comment/list/reply/`, and `window.byted_acrawler.frontierSign(...)` to generate `X-Bogus` in the logged-in page. It does not require the OpenCLI Browser Bridge extension.
- The Node CDP script uses `douyin_cdp_bridge.mjs` by default. The bridge is a local-only HTTP wrapper that holds the Chrome CDP websocket open; routine comment crawls should go through it instead of `--direct-cdp`.
- Douyin can report a larger `total` than the number of root comments the web API actually paginates. Always report both `reported_total` and `total_saved`; do not claim true full coverage when `total_saved` is lower or reply errors remain.
- For later Feishu integration, map `comment_id` to the comment table dedupe key, `aweme_id` to the video table platform video id, and `parent_id` to root/reply relationships. Keep this as an explicit opt-in sync step.
