import argparse
import difflib
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path

import download_bili_following_latest as bili


ROOT = Path(__file__).resolve().parent
DEFAULT_CREATORS_PATH = ROOT / "douyin-creators.json"
MANIFEST_ROOT = ROOT / "downloads" / "manifests"


CREATOR_FIELDS = {
    "平台": {
        "type": "select",
        "name": "平台",
        "multiple": True,
        "options": [
            {"name": "B站", "hue": "Blue"},
            {"name": "抖音", "hue": "Orange"},
        ],
    },
    "抖音SecUID": {"type": "text", "name": "抖音SecUID"},
    "抖音主页链接": {"type": "text", "name": "抖音主页链接", "style": {"type": "url"}},
    "抖音持续跟踪": {"type": "checkbox", "name": "抖音持续跟踪"},
}


VIDEO_FIELDS = {
    "平台": {
        "type": "select",
        "name": "平台",
        "multiple": False,
        "options": [
            {"name": "B站", "hue": "Blue"},
            {"name": "抖音", "hue": "Orange"},
        ],
    },
    "平台视频ID": {"type": "text", "name": "平台视频ID"},
    "内容去重状态": {
        "type": "select",
        "name": "内容去重状态",
        "multiple": False,
        "options": [
            {"name": "确认独立", "hue": "Green"},
            {"name": "待匹配", "hue": "Orange"},
            {"name": "疑似跨平台重复", "hue": "Purple"},
            {"name": "已跳过重复", "hue": "Gray"},
        ],
    },
    "内容去重说明": {"type": "text", "name": "内容去重说明"},
}


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ts_slug():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_manifest(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def latest_douyin_manifest():
    candidates = sorted(MANIFEST_ROOT.glob("*-douyin-latest-download.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"No Douyin latest manifest found under {MANIFEST_ROOT}")
    return candidates[-1]


def run_lark_with_json(config, table_id, command, payload, *, record_id=None, timeout=120):
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as f:
        json.dump(payload, f, ensure_ascii=False)
        payload_path = Path(f.name)
    try:
        args = [
            command,
            "--as",
            "user",
            "--base-token",
            config["base_token"],
            "--table-id",
            table_id,
        ]
        if record_id:
            args.extend(["--record-id", record_id])
        args.extend(["--json", f"@{payload_path.relative_to(ROOT)}"])
        return bili.run_lark(config, args, timeout=timeout)
    finally:
        payload_path.unlink(missing_ok=True)


def ensure_fields(config, table_id, specs, *, dry_run=False):
    existing = bili.field_names(config, table_id)
    created = []
    for name, spec in specs.items():
        if name in existing:
            continue
        if dry_run:
            created.append(name)
            continue
        bili.run_lark(
            config,
            [
                "+field-create",
                "--as",
                "user",
                "--base-token",
                config["base_token"],
                "--table-id",
                table_id,
                "--json",
                json.dumps(spec, ensure_ascii=False),
            ],
            timeout=120,
        )
        created.append(name)
    return created


def extract_sec_uid(url):
    match = re.search(r"/user/([^/?#]+)", str(url or ""))
    return match.group(1) if match else ""


def normalize_title(title):
    text = re.sub(r"\s*-\s*抖音$", "", str(title or ""), flags=re.I)
    text = re.sub(r"#[^\s#]+", "", text)
    text = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    return text.lower()


def clean_title(title):
    return re.sub(r"\s*-\s*抖音$", "", str(title or "")).strip()


def extract_creator_name(parsed, metadata, creator_config):
    key = (metadata.get("creator") or {}).get("key") or (parsed.get("creator") or {}).get("key")
    if key and key in creator_config:
        configured = str(creator_config[key].get("name") or "").strip()
        if configured and not configured.startswith("douyin_creator_"):
            return configured

    page_title = str(parsed.get("page_title") or "")
    match = re.match(r"(.+?)的抖音\s*-\s*抖音", page_title)
    if match:
        return match.group(1).strip()

    body = str((metadata.get("page_metadata") or {}).get("body_excerpt") or "")
    match = re.search(r"发布时间：\d{4}-\d{2}-\d{2} \d{2}:\d{2}\s*\n(.+?)\s*\n", body)
    if match:
        return match.group(1).strip()

    return str((metadata.get("creator") or {}).get("name") or key or "").strip()


def extract_published_at(metadata):
    page = metadata.get("page_metadata") or {}
    body = str(page.get("body_excerpt") or "")
    match = re.search(r"发布时间：(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", body)
    if match:
        return f"{match.group(1)} {match.group(2)}:00"

    desc = str(page.get("description") or "")
    match = re.search(r"于(\d{4})(\d{2})(\d{2})发布", desc)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)} 00:00:00"
    return None


def load_creator_config(path):
    if not path.exists():
        return {}
    items = load_json(path)
    return {item.get("key"): item for item in items if item.get("key")}


def parsed_by_creator(manifest):
    return {
        (item.get("creator") or {}).get("key"): item
        for item in manifest.get("parsed", [])
        if (item.get("creator") or {}).get("key")
    }


def build_items(download_manifest, creator_config):
    parsed_lookup = parsed_by_creator(download_manifest)
    items = []
    for success in download_manifest.get("successes", []):
        metadata_path = Path(success["metadata_path"])
        metadata = load_json(metadata_path)
        key = (success.get("creator") or {}).get("key") or (metadata.get("creator") or {}).get("key")
        parsed = parsed_lookup.get(key) or {}
        creator_name = extract_creator_name(parsed, metadata, creator_config)
        creator_url = (success.get("creator") or {}).get("url") or (metadata.get("creator") or {}).get("url")
        page = metadata.get("page_metadata") or {}
        transcript = success.get("transcript") or {}
        item = {
            "creator_key": key,
            "creator_name": creator_name,
            "creator_url": creator_url,
            "sec_uid": extract_sec_uid(creator_url),
            "aweme_id": str(success.get("aweme_id") or metadata.get("aweme_id") or ""),
            "video_url": success.get("video_url") or metadata.get("video_url"),
            "title": clean_title(page.get("title") or (metadata.get("selected_card") or {}).get("title")),
            "published_at": extract_published_at(metadata),
            "duration": metadata.get("duration_seconds"),
            "video_path": success.get("video_path"),
            "metadata_path": success.get("metadata_path"),
            "description_path": success.get("description_path") or (metadata.get("files") or {}).get("description_path"),
            "cover_path": success.get("cover_path") or (metadata.get("files") or {}).get("cover_path"),
            "audio_path": transcript.get("audio_path"),
            "speech_raw_path": transcript.get("speech_raw_path"),
            "speech_clean_path": transcript.get("speech_clean_path"),
            "speech_chars": transcript.get("speech_chars"),
        }
        items.append(item)
    return items


def load_creators(config):
    desired = [
        "博主名称",
        "B站MID",
        "主页链接",
        "是否持续跟踪",
        "抖音主页链接",
        "抖音SecUID",
        "抖音持续跟踪",
        "平台",
    ]
    table_id = config["tables"]["creators"]["table_id"]
    available = bili.field_names(config, table_id)
    fields = [field for field in desired if field in available]
    rows = bili.list_records(config, table_id, fields)
    for row in rows:
        for field in desired:
            row.setdefault(field, None)
    return rows


def load_videos(config):
    desired = [
        "视频标题",
        "BVID",
        "视频链接",
        "关联博主",
        "平台",
        "平台视频ID",
        "内容去重状态",
    ]
    table_id = config["tables"]["videos"]["table_id"]
    available = bili.field_names(config, table_id)
    fields = [field for field in desired if field in available]
    rows = bili.list_records(config, table_id, fields)
    for row in rows:
        for field in desired:
            row.setdefault(field, None)
    return rows


def find_creator(creators, item):
    sec_uid = item.get("sec_uid")
    for row in creators:
        if sec_uid and str(row.get("抖音SecUID") or "").strip() == sec_uid:
            return row
    name = item.get("creator_name")
    for row in creators:
        if str(row.get("博主名称") or "").strip().lower() == str(name or "").strip().lower():
            return row
    return None


def creator_platforms(row, *, include_douyin=True):
    platforms = row.get("平台")
    if isinstance(platforms, list):
        values = [str(v) for v in platforms if v]
    elif platforms:
        values = [str(platforms)]
    else:
        values = []
    if row.get("B站MID") and "B站" not in values:
        values.append("B站")
    if include_douyin and "抖音" not in values:
        values.append("抖音")
    return values


def has_link_to_creator(row, creator_record_id):
    links = row.get("关联博主") or []
    return any(isinstance(link, dict) and link.get("id") == creator_record_id for link in links)


def find_existing_video(videos, item, creator_record_id):
    aweme_id = item.get("aweme_id")
    if aweme_id:
        for row in videos:
            if str(row.get("平台视频ID") or "").strip() == aweme_id:
                return "same_platform_id", row, 1.0
            if aweme_id in str(row.get("视频链接") or ""):
                return "same_video_url", row, 1.0

    target = normalize_title(item.get("title"))
    if not target:
        return None, None, 0.0
    best_row = None
    best_score = 0.0
    for row in videos:
        if creator_record_id and not has_link_to_creator(row, creator_record_id):
            continue
        source = normalize_title(row.get("视频标题"))
        if not source:
            continue
        score = difflib.SequenceMatcher(None, target, source).ratio()
        if source == target:
            return "same_title", row, 1.0
        if score > best_score:
            best_score = score
            best_row = row
    if best_score >= 0.86:
        return "similar_title", best_row, best_score
    return None, best_row, best_score


def create_creator(config, item, *, dry_run=False):
    fields = [
        "博主名称",
        "来源",
        "主页链接",
        "B站MID",
        "是否持续跟踪",
        "抖音主页链接",
        "抖音SecUID",
        "抖音持续跟踪",
        "平台",
        "最近采集时间",
    ]
    row = [
        item["creator_name"],
        "手动新增",
        item["creator_url"],
        "",
        False,
        item["creator_url"],
        item["sec_uid"],
        True,
        ["抖音"],
        now_str(),
    ]
    if dry_run:
        return {
            "_record_id": f"dry_creator_{item['sec_uid'] or item['creator_key']}",
            "博主名称": item["creator_name"],
            "B站MID": "",
            "平台": ["抖音"],
            "dry_run": True,
            "fields": fields,
            "row": row,
        }
    data = run_lark_with_json(
        config,
        config["tables"]["creators"]["table_id"],
        "+record-batch-create",
        {"fields": fields, "rows": [row]},
    )
    record_ids = data.get("data", {}).get("record_id_list") or []
    if not record_ids:
        raise RuntimeError(f"creator create returned no record id: {data}")
    return {"_record_id": record_ids[0], "博主名称": item["creator_name"], "B站MID": "", "平台": ["抖音"]}


def update_creator(config, creator, item, *, dry_run=False):
    patch = {
        "抖音主页链接": item["creator_url"],
        "抖音SecUID": item["sec_uid"],
        "抖音持续跟踪": True,
        "平台": creator_platforms(creator),
        "最近采集时间": now_str(),
    }
    if dry_run:
        return patch
    run_lark_with_json(
        config,
        config["tables"]["creators"]["table_id"],
        "+record-upsert",
        patch,
        record_id=creator["_record_id"],
        timeout=60,
    )
    return patch


def create_video(config, item, creator, dedupe_status, dedupe_note, *, dry_run=False):
    fields = [
        "视频标题",
        "平台",
        "平台视频ID",
        "视频链接",
        "关联博主",
        "发布时间",
        "时长秒",
        "视频文件路径",
        "元数据文件路径",
        "视频文案路径",
        "封面文件路径",
        "音频文件路径",
        "原始文案路径",
        "清洗文案路径",
        "视频下载状态",
        "音频状态",
        "转写状态",
        "最近采集时间",
        "内容去重状态",
        "内容去重说明",
    ]
    has_transcript = bool(item.get("speech_clean_path"))
    row = [
        item["title"],
        "抖音",
        item["aweme_id"],
        item["video_url"],
        [{"id": creator["_record_id"]}],
        item.get("published_at"),
        item.get("duration"),
        item.get("video_path"),
        item.get("metadata_path"),
        item.get("description_path"),
        item.get("cover_path"),
        item.get("audio_path"),
        item.get("speech_raw_path"),
        item.get("speech_clean_path"),
        "已下载",
        "已下载" if item.get("audio_path") else "跳过",
        "已转写" if has_transcript else "无需转写",
        now_str(),
        dedupe_status,
        dedupe_note[:1000],
    ]
    if dry_run:
        return {"dry_run": True, "fields": fields, "row": row}
    data = run_lark_with_json(
        config,
        config["tables"]["videos"]["table_id"],
        "+record-batch-create",
        {"fields": fields, "rows": [row]},
    )
    record_ids = data.get("data", {}).get("record_id_list") or []
    if not record_ids:
        raise RuntimeError(f"video create returned no record id: {data}")
    return record_ids[0]


def sync(args):
    started_at = now_str()
    download_manifest_path = Path(args.manifest) if args.manifest else latest_douyin_manifest()
    if not download_manifest_path.is_absolute():
        download_manifest_path = ROOT / download_manifest_path
    creator_config = load_creator_config(Path(args.creators))
    download_manifest = load_json(download_manifest_path)
    items = build_items(download_manifest, creator_config)

    config = bili.load_config()
    creators_table = config["tables"]["creators"]["table_id"]
    videos_table = config["tables"]["videos"]["table_id"]

    created_fields = {
        "creators": ensure_fields(config, creators_table, CREATOR_FIELDS, dry_run=args.dry_run),
        "videos": ensure_fields(config, videos_table, VIDEO_FIELDS, dry_run=args.dry_run),
    }

    creators = load_creators(config)
    videos = load_videos(config)

    result = {
        "started_at": started_at,
        "ended_at": None,
        "download_manifest": str(download_manifest_path),
        "dry_run": args.dry_run,
        "defer_existing_bili_creators": not args.include_existing_bili_creators,
        "created_fields": created_fields,
        "created_creators": [],
        "updated_creators": [],
        "created_videos": [],
        "skipped_videos": [],
        "failures": [],
    }

    for item in items:
        try:
            creator = find_creator(creators, item)
            if creator:
                patch = update_creator(config, creator, item, dry_run=args.dry_run)
                result["updated_creators"].append(
                    {
                        "name": item["creator_name"],
                        "record_id": creator["_record_id"],
                        "patch": patch if args.dry_run else None,
                    }
                )
            else:
                creator = create_creator(config, item, dry_run=args.dry_run)
                result["created_creators"].append(
                    {"name": item["creator_name"], "record_id": creator.get("_record_id"), "url": item["creator_url"]}
                )
                if not args.dry_run:
                    creators.append(creator)

            match_type, match_row, score = find_existing_video(videos, item, creator.get("_record_id"))
            if match_type:
                result["skipped_videos"].append(
                    {
                        "creator": item["creator_name"],
                        "aweme_id": item["aweme_id"],
                        "title": item["title"],
                        "reason": match_type,
                        "matched_record_id": match_row.get("_record_id"),
                        "matched_title": match_row.get("视频标题"),
                        "score": score,
                    }
                )
                continue

            has_bili_mid = bool(str(creator.get("B站MID") or "").strip())
            if has_bili_mid and not args.include_existing_bili_creators:
                result["skipped_videos"].append(
                    {
                        "creator": item["creator_name"],
                        "aweme_id": item["aweme_id"],
                        "title": item["title"],
                        "reason": "deferred_existing_bili_creator",
                        "best_title_match": match_row.get("视频标题") if match_row else None,
                        "best_title_score": score,
                        "note": "已有 B 站博主记录；抖音视频先不作为独立新视频写入，等待同内容匹配确认。",
                    }
                )
                continue

            dedupe_note = "抖音-only 博主，未找到相同 aweme_id 或同博主近似标题。"
            record_id = create_video(config, item, creator, "确认独立", dedupe_note, dry_run=args.dry_run)
            result["created_videos"].append(
                {
                    "creator": item["creator_name"],
                    "record_id": record_id,
                    "aweme_id": item["aweme_id"],
                    "title": item["title"],
                    "video_url": item["video_url"],
                }
            )
            if not args.dry_run:
                videos.append(
                    {
                        "_record_id": record_id,
                        "视频标题": item["title"],
                        "平台": "抖音",
                        "平台视频ID": item["aweme_id"],
                        "视频链接": item["video_url"],
                        "关联博主": [{"id": creator["_record_id"]}],
                    }
                )
        except Exception as exc:
            result["failures"].append(
                {
                    "creator": item.get("creator_name"),
                    "aweme_id": item.get("aweme_id"),
                    "stage": "sync",
                    "error": str(exc)[-2000:],
                }
            )

    result["ended_at"] = now_str()
    result["summary"] = {
        "created_creators": len(result["created_creators"]),
        "updated_creators": len(result["updated_creators"]),
        "created_videos": len(result["created_videos"]),
        "skipped_videos": len(result["skipped_videos"]),
        "failures": len(result["failures"]),
    }

    sync_manifest_path = MANIFEST_ROOT / f"{ts_slug()}-douyin-feishu-sync.json"
    write_manifest(sync_manifest_path, result)

    if not args.dry_run:
        failure_summary = "; ".join(
            f"{item.get('creator') or ''}/{item.get('aweme_id') or ''}: {item.get('error') or item.get('stage')}"
            for item in result["failures"][:8]
        )
        skip_summary = "; ".join(
            f"{item.get('creator')}: {item.get('reason')}" for item in result["skipped_videos"][:8]
        )
        summary = "; ".join(part for part in [failure_summary, skip_summary, f"manifest={sync_manifest_path}"] if part)
        bili.create_task_log(
            config,
            started_at,
            result["ended_at"],
            len(result["created_videos"]),
            len(result["failures"]),
            sync_manifest_path,
            summary,
            task_name="抖音本地产物入库",
            task_type="视频列表采集",
            target_scope="downloads/douyin 本地试跑产物；抖音-only 视频入库，B站博主视频延后去重",
        )

    return sync_manifest_path, result


def parse_args():
    parser = argparse.ArgumentParser(description="Sync isolated Douyin download artifacts into Feishu Base.")
    parser.add_argument("--manifest", help="Douyin latest-download manifest. Defaults to the newest one.")
    parser.add_argument("--creators", default=str(DEFAULT_CREATORS_PATH), help="Douyin creators JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Plan writes without changing Feishu.")
    parser.add_argument(
        "--include-existing-bili-creators",
        action="store_true",
        help="Also create Douyin video rows for creators that already have a Bilibili MID.",
    )
    return parser.parse_args()


def main():
    path, result = sync(parse_args())
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"Manifest: {path}")
    if result["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
