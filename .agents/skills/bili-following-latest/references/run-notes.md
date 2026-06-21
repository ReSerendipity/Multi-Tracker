# Run Notes

## 2026-06-19 Baseline

Project root:

```text
%PROJECTS%\codexProjects\AI博主爬取
```

Main script:

```text
download_bili_following_latest.py
```

Feishu config:

```text
feishu-base-config.json
```

Full run manifest:

```text
downloads/manifests/20260619-125803-bili-latest-download.json
```

Observed result:

```json
{
  "downloaded": 69,
  "skipped_existing": 1,
  "failed": 1,
  "created_video_records": 69
}
```

The skip was `BV1HML96hEvN`, already written by the small validation run.

The failure was:

```text
AI随风随风 / BV1v1Er6tE1n
```

Reason: `yt-dlp` metadata extraction hit HTTP 412, API fallback ran, but Bilibili playurl did not return a usable video stream. Only cover/metadata/playurl artifacts were saved; no mp4 was created, so no Feishu 视频 row was written for that BVID.

Verification from that run:

- Every success entry had a local mp4 and compatible info JSON.
- Feishu 视频 table had no duplicate BVIDs.
- Latest 爬取任务日志 row recorded 成功数量=69, 失败数量=1, 状态=部分失败.

## Current Hard Boundaries

- Do not print or persist Cookie plaintext.
- Do not use broad search terms to fill missing creator videos; author/card matching must be strict enough to avoid wrong-author rows.
- Keep Feishu writes through `lark-cli --profile cli_a974a338c2f85cb2 ... --as user`.
- If authorization expires, recover user auth through the Lark shared auth flow instead of falling back to bot writes.
