---
name: bilibili-comments
description: Fetch and export all comments from a Bilibili video, including first-level comments and second-level replies, through the user's already logged-in Chrome browser. Use when the user asks to crawl, download, export, save, or analyze comments for a Bilibili/B站/哔哩哔哩 video URL, BV id, or av id.
---

# Bilibili Comments

## Workflow

Use the bundled script for comment export. Do not manually copy cookies.

1. Ensure Chrome is open and remote debugging is enabled at `chrome://inspect/#remote-debugging`.
2. Run:

```powershell
node .\scripts\fetch_comments.mjs --video "https://www.bilibili.com/video/BVxxxx" --output ".\bili-comments.jsonl"
```

3. For a quick smoke test, limit root comments:

```powershell
node .\scripts\fetch_comments.mjs --video "BVxxxx" --max-root 20 --no-replies --output ".\sample.jsonl"
```

4. For multiple videos, always use batch mode so one Node process keeps one CDP websocket connection open across all videos:

```powershell
node .\scripts\fetch_comments.mjs --videos-file ".\videos.json" --output-dir ".\comments"
```

`videos.json` must be a JSON array. Entries can be strings or objects:

```json
[
  "BVxxxx",
  { "video": "https://www.bilibili.com/video/BVyyyy", "bvid": "BVyyyy", "output": "comments/BVyyyy.jsonl" }
]
```

5. Report the output path and counts: root comments, reply comments, total rows, and duplicate skips.

## Script Options

- `--video <url|BV|av>`: Required. Bilibili video URL, BV id, or av id.
- `--videos-file <file>`: Optional batch mode. Use this for more than one video to avoid reconnecting to Chrome for every video.
- `--output-dir <dir>`: Optional batch output directory. Used with `--videos-file`.
- `--output <file>`: Optional. Defaults to `bilibili_comments_<BV-or-aid>_<timestamp>.jsonl` in the current directory.
- `--max-root <n>`: Optional. Limit first-level comments for testing.
- `--no-replies`: Optional. Export only first-level comments.
- `--delay-ms <n>`: Optional. Delay between root-comment API pages. Default `500`.
- `--reply-delay-ms <n>`: Optional. Delay between reply API pages. Default `300`.
- `--keep-tab`: Optional. Keep the temporary Bilibili tab open for debugging.

## Output Schema

Each JSONL row uses this shape:

```json
{
  "comment_id": "303482460912",
  "parent_comment_id": "0",
  "root_comment_id": "303482460912",
  "level": 1,
  "create_time": 1779613639,
  "video_id": "116618478750430",
  "bvid": "BV...",
  "content": "评论正文",
  "user_id": "1655181908",
  "nickname": "用户名",
  "sex": "保密",
  "sign": "",
  "avatar": "https://...",
  "sub_comment_count": "13",
  "like_count": 60,
  "last_modify_ts": 1781857457856
}
```

`parent_comment_id` is `0` for first-level comments. For replies, it comes from Bilibili's `parent` field; `root_comment_id` identifies the first-level thread.

## Reliability Notes

- The script fetches from inside the logged-in Chrome page context, so it uses the browser's current Bilibili login state without printing or exporting cookies.
- Chrome remote debugging is a server, but each Node run is still a new CDP client websocket connection. Batch mode avoids repeated client connections inside a multi-video crawl.
- If connection times out, ask the user to keep Chrome open, confirm any browser authorization dialog, and retry.
- If `chrome://inspect/#remote-debugging` shows no running server, ask the user to toggle "Allow remote debugging for this browser instance" off and on.
- For very large videos, increase delays instead of running tight loops.
