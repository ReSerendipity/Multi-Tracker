# AGENTS.md — Repository Guidance

## Authoritative Source vs. Duplicate Copies

The same core download / sync scripts are committed in **three git-tracked
locations**, and a plain filename search returns several hits. Only one is the
source of truth. Edit it; treat the other two as read-only generated snapshots.

| Location | Role | Edit directly? |
| --- | --- | --- |
| `<repo root>/*.py` | **Authoritative source** — the code you actually run and maintain (alongside `README.md`, `start.ps1`, `requirements.txt`). | **Yes** |
| `分享包_多平台博主追踪系统/` | Share / submission **export bundle** (its `README.md` self-describes as a TraeWork 活动投稿分享 package; it carries its own `LICENSE.md`, `CONTRIBUTING.md`, `docs/`, and a full copy of `.agents/skills/`). | No — snapshot; regenerate by copying from root |
| `repro-package/` | Minimal B站 **reproduction extract** (its `README.md` self-describes as “从完整项目里提取的 B站最小可用版本”; only a handful of scripts). | No — snapshot; regenerate by copying from root |

### Rule

To change a download or sync script, edit the **repository-root** copy, for
example:

- `download_douyin_latest.py`
- `sync_douyin_to_feishu.py`
- `download_bili_following_latest.py`
- `sync_bilibili_comments_to_feishu.py`

Then — only if a snapshot must be refreshed — copy the updated root file into
`分享包_多平台博主追踪系统/` or `repro-package/`. Never make a snapshot the place where a
fix “lives”: the next regeneration from root would overwrite it.

### Mapping for any named script

For any script that appears in multiple locations, the authoritative file is
always the root file and each subdirectory copy is a **downstream snapshot of
it**. Example: `cdp_bili_download.py` exists at the root, under
`分享包_多平台博主追踪系统/`, and under `repro-package/` — the root file is the one to read
and edit; the other two are derived copies.

### Skills source

The authoritative skills tree is `<repo root>/.agents/skills/`. The copy under
`分享包_多平台博主追踪系统/.agents/skills/` is part of that export bundle, not a second source.
