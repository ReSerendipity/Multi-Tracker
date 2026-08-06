import argparse
import difflib
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path

import download_bili_following_latest as bili


ROOT = Path(__file__).resolve().parent
DEFAULT_CREATORS_PATH = ROOT / "xiaohongshu-creators.json"
MANIFEST_ROOT = ROOT / "downloads" / "manifests"


CREATOR_FIELDS = {
    "平台": {
        "type": "select",
        "name": "平台",
        "multiple": True,
        "options": [
            {"name": "B站", "hue": "Blue"},
            {"name": "抖音", "hue": "Orange"},
            {"name": "小红书", "hue": "Red"},
        ],
    },
    "小红书用户ID": {"type": "text", "name": "小红书用户ID"},
    "小红书主页链接": {"type": "text", "name": "小红书主页链接", "style": {"type": "url"}},
    "小红书持续跟踪": {"type": "checkbox", "name": "小红书持续跟踪"},
}


VIDEO_FIELDS = {
    "平台": {
        "type": "select",
        "name": "平台",
        "multiple": False,
        "options": [
            {"name": "B站", "hue": "Blue"},
            {"name": "抖音", "hue": "Orange"},
            {"name": "小红书", "hue": "Red"},
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


def latest_xiaohongshu_manifest():
    candidates = sorted(MANIFEST_ROOT.glob("*-xiaohongshu-latest-download.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"No Xiaohongshu latest manifest found under {MANIFEST_ROOT}")
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


def extract_user_id(url):
    match = re.search(r"/user/profile/([^/?#]+)", str(url or ""))
    return match.group(1) if match else ""


def normalize_title(title):
    text = re.sub(r"\s*-\s*小红书$", "", str(title or ""), flags=re.I)
    text = re.sub(r"#[^\s#]+", "", text)
    text = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    return text.lower()


def clean_title(title):
    return re.sub(r"\s*-\s*小红书$", "", str(title or "")).strip()


def extract_creator_name(parsed, metadata, creator_config):
    key = (metadata.get("creator") or {}).get("key") or (parsed.get("creator") or {}).get("key")
    if key and key in creator_config:
        configured = str(creator_config[key].get("name") or "").strip()
        if configured and not configured.startswith("xiaohongshu_creator_"):
            return configured

    page_title = str(parsed.get("page_title") or "")
    match = re.match(r"(.+?)的小红书\s*-\s*小红书", page_title)
    if match:
        return match.group(1).strip()

    body = str((metadata.get("page_metadata") or {}).get("body_excerpt") or "")
    match = re.search(r"发布时间：(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", body)
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
            "user_id": extract_user_id(creator_url),
            "note_id": str(success.get("note_id") or metadata.get("note_id") or ""),
            "note_url": success.get("note_url") or metadata.get("note_url"),
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
        "小红书主页链接",
        "小红书用户ID",
        "小红书持续跟踪",
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
    user_id = item.get("user_id")
    for row in creators:
        if user_id and str(row.get("小红书用户ID") or "").strip() == user_id:
            return row
    name = item.get("creator_name")
    for row in creators:
        if str(row.get("博主名称") or "").strip().lower() == str(name or "").strip().lower():
            return row
    return None


def creator_platforms(row, *, include_xiaohongshu=True):
    platforms = row.get("平台")
    if isinstance(platforms, list):
        values = [str(v) for v in platforms if v]
    elif platforms:
        values = [str(platforms)]
    else:
        values = []
    if include_xiaohongshu and "小红书" not in values:
        values.append("小红书")
    return values


def find_existing_video(videos, item):
    note_id = item.get("note_id")
    for row in videos:
        platform_id = str(row.get("平台视频ID") or "").strip()
        if platform_id and platform_id == note_id:
            return row
    return None


def normalize_for_dedup(text):
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


def similarity(a, b):
    return difflib.SequenceMatcher(None, normalize_for_dedup(a), normalize_for_dedup(b)).ratio()


def detect_cross_platform_duplicate(item, videos, creators):
    title = item.get("title") or ""
    creator_name = item.get("creator_name") or ""
    if not title:
        return None, None, 0.0

    for row in videos:
        existing_title = row.get("视频标题") or ""
        existing_platform = row.get("平台") or ""
        if existing_platform in ("小红书", ""):
            continue
        sim = similarity(title, existing_title)
        if sim > 0.85:
            return row, "疑似跨平台重复", sim

    return None, None, 0.0


def sync_to_feishu(args):
    config = bili.load_config()
    download_manifest = load_json(args.manifest) if args.manifest else load_json(latest_xiaohongshu_manifest())
    creator_config = load_creator_config(DEFAULT_CREATORS_PATH)

    creators_table_id = config["tables"]["creators"]["table_id"]
    videos_table_id = config["tables"]["videos"]["table_id"]
    logs_table_id = config["tables"]["crawl_task_logs"]["table_id"]

    created_fields = ensure_fields(config, creators_table_id, CREATOR_FIELDS, dry_run=args.dry_run)
    created_fields += ensure_fields(config, videos_table_id, VIDEO_FIELDS, dry_run=args.dry_run)
    if created_fields and not args.dry_run:
        print(f"[ensure-fields] created: {created_fields}")

    items = build_items(download_manifest, creator_config)
    creators = load_creators(config)
    videos = load_videos(config)

    result = {
        "started_at": now_str(),
        "manifest": str(args.manifest) if args.manifest else str(latest_xiaohongshu_manifest()),
        "items": len(items),
        "creator_rows_created": 0,
        "creator_rows_updated": 0,
        "video_rows_created": 0,
        "video_rows_skipped_existing": 0,
        "video_rows_duplicate": 0,
        "dry_run": args.dry_run,
        "failures": [],
        "video_details": [],
        "log_record_id": None,
    }

    for item in items:
        try:
            creator_row = find_creator(creators, item)
            if not creator_row:
                if args.dry_run:
                    print(f"[dry-run] creator row would be created for {item['creator_name']}")
                    result["creator_rows_created"] += 1
                else:
                    payload = {
                        "fields": {
                            "博主名称": item["creator_name"],
                            "主页链接": {"link": item["creator_url"], "text": item["creator_name"]},
                            "小红书主页链接": {"link": item["creator_url"], "text": item["creator_name"]},
                            "小红书用户ID": item.get("user_id") or "",
                            "小红书持续跟踪": True,
                            "平台": creator_platforms({}, include_xiaohongshu=True),
                        }
                    }
                    resp = run_lark_with_json(config, creators_table_id, "record-create", payload)
                    record_id = (resp.get("record") or {}).get("record_id") or ""
                    print(f"[feishu] creator row created: {item['creator_name']} ({record_id})")
                    result["creator_rows_created"] += 1
                    creators.append(
                        {
                            "_record_id": record_id,
                            "博主名称": item["creator_name"],
                            "小红书用户ID": item.get("user_id") or "",
                            "小红书主页链接": item["creator_url"],
                            "平台": ["小红书"],
                        }
                    )
            else:
                updates = {}
                if not str(creator_row.get("小红书用户ID") or "").strip() and item.get("user_id"):
                    updates["小红书用户ID"] = item["user_id"]
                if not str(creator_row.get("小红书主页链接") or "").strip():
                    updates["小红书主页链接"] = {"link": item["creator_url"], "text": item["creator_name"]}
                if "小红书" not in (creator_row.get("平台") or []):
                    updates["平台"] = creator_platforms(creator_row, include_xiaohongshu=True)
                if updates and not args.dry_run:
                    run_lark_with_json(
                        config,
                        creators_table_id,
                        "record-update",
                        {"fields": updates},
                        record_id=creator_row["_record_id"],
                    )
                    result["creator_rows_updated"] += 1

            existing_video = find_existing_video(videos, item)
            if existing_video:
                print(f"[skip] video already in Feishu: {item['note_id']}")
                result["video_rows_skipped_existing"] += 1
                result["video_details"].append(
                    {
                        "note_id": item["note_id"],
                        "title": item["title"],
                        "status": "skipped_existing",
                    }
                )
                continue

            dup_row, dup_status, dup_sim = detect_cross_platform_duplicate(item, videos, creators)
            if dup_row and not args.allow_duplicates:
                print(f"[dedup] {item['note_id']} similar to {dup_row.get('BVID') or dup_row.get('平台视频ID')} (sim={dup_sim:.2f})")
                result["video_rows_duplicate"] += 1
                result["video_details"].append(
                    {
                        "note_id": item["note_id"],
                        "title": item["title"],
                        "status": "duplicate",
                        "duplicate_of": dup_row.get("BVID") or dup_row.get("平台视频ID"),
                        "similarity": round(dup_sim, 3),
                    }
                )
                if not args.dry_run:
                    run_lark_with_json(
                        config,
                        videos_table_id,
                        "record-create",
                        {
                            "fields": {
                                "视频标题": item["title"],
                                "平台": "小红书",
                                "平台视频ID": item["note_id"],
                                "视频链接": {"link": item["note_url"], "text": item["title"]},
                                "关联博主": item["creator_name"],
                                "内容去重状态": dup_status,
                                "内容去重说明": f"相似度 {dup_sim:.2f}，疑似与 {dup_row.get('BVID') or dup_row.get('平台视频ID')} 重复",
                            }
                        },
                    )
                continue

            if args.dry_run:
                print(f"[dry-run] video row would be created: {item['note_id']} {item['title']}")
                result["video_rows_created"] += 1
            else:
                fields = {
                    "视频标题": item["title"],
                    "平台": "小红书",
                    "平台视频ID": item["note_id"],
                    "视频链接": {"link": item["note_url"], "text": item["title"]},
                    "关联博主": item["creator_name"],
                    "内容去重状态": "待匹配",
                }
                if item.get("published_at"):
                    fields["发布时间"] = item["published_at"]
                if item.get("duration"):
                    fields["时长秒"] = item["duration"]
                if item.get("description_path"):
                    try:
                        desc = Path(item["description_path"]).read_text(encoding="utf-8", errors="replace")
                        fields["视频简介"] = desc[:2000]
                    except Exception:
                        pass
                if item.get("speech_clean_path"):
                    try:
                        transcript = Path(item["speech_clean_path"]).read_text(encoding="utf-8", errors="replace")
                        fields["转写稿"] = transcript[:50000]
                        fields["转写状态"] = "已完成"
                    except Exception:
                        pass
                if item.get("speech_chars"):
                    fields["转写字符数"] = item["speech_chars"]

                resp = run_lark_with_json(config, videos_table_id, "record-create", {"fields": fields})
                record_id = (resp.get("record") or {}).get("record_id") or ""
                print(f"[feishu] video row created: {item['note_id']} ({record_id})")
                result["video_rows_created"] += 1
                result["video_details"].append(
                    {
                        "note_id": item["note_id"],
                        "title": item["title"],
                        "status": "created",
                        "record_id": record_id,
                    }
                )
                videos.append(
                    {
                        "_record_id": record_id,
                        "视频标题": item["title"],
                        "平台": "小红书",
                        "平台视频ID": item["note_id"],
                    }
                )
        except Exception as exc:
            result["failures"].append({"item": item.get("note_id"), "error": str(exc)[-2000:]})
            print(f"[failed] {item.get('note_id')}: {exc}")

    result["ended_at"] = now_str()
    result["summary"] = {
        "items": result["items"],
        "creator_rows_created": result["creator_rows_created"],
        "creator_rows_updated": result["creator_rows_updated"],
        "video_rows_created": result["video_rows_created"],
        "video_rows_skipped_existing": result["video_rows_skipped_existing"],
        "video_rows_duplicate": result["video_rows_duplicate"],
        "failed": len(result["failures"]),
        "dry_run": args.dry_run,
    }

    if not args.dry_run:
        try:
            log_payload = {
                "fields": {
                    "任务类型": "小红书同步",
                    "开始时间": result["started_at"],
                    "结束时间": result["ended_at"],
                    "成功数": result["video_rows_created"],
                    "跳过数": result["video_rows_skipped_existing"],
                    "失败数": len(result["failures"]),
                    "详情": json.dumps(result["summary"], ensure_ascii=False),
                }
            }
            resp = run_lark_with_json(config, logs_table_id, "record-create", log_payload)
            result["log_record_id"] = (resp.get("record") or {}).get("record_id") or ""
        except Exception:
            pass

    manifest_path = MANIFEST_ROOT / f"{ts_slug()}-xiaohongshu-feishu-sync.json"
    write_manifest(manifest_path, result)
    print(json.dumps({"manifest": str(manifest_path), "summary": result["summary"]}, ensure_ascii=False, indent=2))
    if result["failures"]:
        sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="Sync Xiaohongshu download artifacts into Feishu Base.")
    parser.add_argument("--manifest", help="Path to Xiaohongshu download manifest JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write Feishu records.")
    parser.add_argument("--allow-duplicates", action="store_true", help="Skip cross-platform dedup check.")
    return parser.parse_args()


if __name__ == "__main__":
    parse_and_run = parse_args()
    sync_to_feishu(parse_and_run)