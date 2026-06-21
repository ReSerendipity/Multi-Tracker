import argparse
import html
import json
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import download_bili_following_latest as bili


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
MANIFEST_ROOT = ROOT / "downloads" / "manifests"
TRANSCRIPT_FIELD = "视频口播稿"
DEFAULT_PARENT_TOKEN = "SvqkwYpPxinVVgk5LPtcRqxnnke"

TRANSCRIPT_FIELD_SPEC = {
    "type": "text",
    "name": TRANSCRIPT_FIELD,
    "style": {"type": "url"},
    "description": "飞书文档 URL；文档内存放排版后的完整视频口播稿。",
}

VIDEO_FIELDS = [
    "视频标题",
    "平台",
    "平台视频ID",
    "BVID",
    "视频链接",
    "关联博主",
    "发布时间",
    "时长秒",
    "清洗文案路径",
    "原始文案路径",
    "视频文案路径",
    TRANSCRIPT_FIELD,
]

CREATOR_FIELDS = ["博主名称"]


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ts_slug():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)


def retryable_lark_error(exc):
    text = str(exc)
    return any(token in text for token in ['"retryable": true', "rate_limit", "99991400", "1254291"])


def retry_delay(base_delay, attempt):
    return min(float(base_delay) * (2 ** attempt), 180.0)


def run_command_with_retry(args, *, timeout, attempts, base_delay):
    last_exc = None
    for attempt in range(max(1, attempts)):
        try:
            return bili.run_command(args, timeout=timeout)
        except RuntimeError as exc:
            last_exc = exc
            if attempt >= attempts - 1 or not retryable_lark_error(exc):
                raise
            delay = retry_delay(base_delay, attempt)
            print(f"[warn] retryable lark-cli error, retrying in {delay:.1f}s ({attempt + 1}/{attempts})", file=sys.stderr)
            time.sleep(delay)
    raise last_exc


def run_lark_with_retry(config, base_args, *, timeout, attempts, base_delay):
    last_exc = None
    for attempt in range(max(1, attempts)):
        try:
            return bili.run_lark(config, base_args, timeout=timeout)
        except RuntimeError as exc:
            last_exc = exc
            if attempt >= attempts - 1 or not retryable_lark_error(exc):
                raise
            delay = retry_delay(base_delay, attempt)
            print(f"[warn] retryable base write error, retrying in {delay:.1f}s ({attempt + 1}/{attempts})", file=sys.stderr)
            time.sleep(delay)
    raise last_exc


def is_empty(value):
    return value is None or value == "" or value == []


def cell_has_platform(value, platform):
    if platform == "all":
        return True
    if isinstance(value, list):
        return platform in [str(item) for item in value if item]
    return str(value or "").strip() == platform


def infer_platform(row):
    platform = row.get("平台")
    if isinstance(platform, list) and platform:
        return str(platform[0])
    if platform:
        return str(platform)
    if row.get("BVID"):
        return "B站"
    if row.get("平台视频ID"):
        return "抖音"
    return ""


def extract_url(value):
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"\]\((https?://[^)]+)\)", text)
    if match:
        return match.group(1).strip()
    match = re.search(r"https?://\S+", text)
    return match.group(0).rstrip(").,，。") if match else text


def resolve_path(value):
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = ROOT / path
    return path


def pick_transcript_path(row):
    for field in ["清洗文案路径", "原始文案路径", "视频文案路径"]:
        path = resolve_path(row.get(field))
        if path and path.exists() and path.is_file():
            return field, path
    return None, None


def read_text(path):
    return path.read_text(encoding="utf-8", errors="replace")


def clean_transcript_paragraphs(text):
    text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?\s*-->\s*.+", line):
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if line.startswith("## Source subtitle"):
            continue
        lines.append(re.sub(r"\s+", " ", line))

    paragraphs = []
    current = []
    for line in lines:
        if not line:
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append(" ".join(current).strip())

    if not paragraphs and text.strip():
        paragraphs = [re.sub(r"\s+", " ", text.strip())]

    output = []
    for paragraph in paragraphs:
        if len(paragraph) <= 700:
            output.append(paragraph)
            continue
        sentences = re.split(r"(?<=[。！？!?；;])\s*", paragraph)
        chunk = ""
        for sentence in sentences:
            if not sentence:
                continue
            if chunk and len(chunk) + len(sentence) > 700:
                output.append(chunk.strip())
                chunk = sentence
            else:
                chunk += sentence
        if chunk:
            output.append(chunk.strip())

    return [item for item in output if item]


def xml_text(value):
    return html.escape(str(value or ""), quote=True)


def xml_url(value):
    return html.escape(extract_url(value), quote=True)


def creator_names(row, creators_by_record_id):
    names = []
    for item in row.get("关联博主") or []:
        if isinstance(item, dict):
            name = creators_by_record_id.get(item.get("id"))
            if name:
                names.append(name)
    return "、".join(names)


def doc_title(row, creators_by_record_id):
    platform = infer_platform(row) or "视频"
    creator = creator_names(row, creators_by_record_id)
    title = str(row.get("视频标题") or "").strip()
    video_id = str(row.get("BVID") or row.get("平台视频ID") or "").strip()
    parts = [platform]
    if creator:
        parts.append(creator)
    if title:
        parts.append(title)
    elif video_id:
        parts.append(video_id)
    return " - ".join(parts)[:120]


def build_doc_xml(row, source_field, source_path, transcript_text, creators_by_record_id):
    title = doc_title(row, creators_by_record_id)
    platform = infer_platform(row)
    creator = creator_names(row, creators_by_record_id)
    video_id = row.get("BVID") or row.get("平台视频ID") or ""
    video_url = xml_url(row.get("视频链接"))
    paragraphs = clean_transcript_paragraphs(transcript_text)

    info_rows = [
        ("平台", platform),
        ("博主", creator),
        ("视频标题", row.get("视频标题") or ""),
        ("平台视频ID", video_id),
        ("发布时间", row.get("发布时间") or ""),
        ("时长秒", row.get("时长秒") if row.get("时长秒") is not None else ""),
        ("口播稿来源", source_field),
        ("本地来源路径", str(source_path)),
        ("发布到文档时间", now_str()),
    ]
    table_rows = "\n".join(
        f"<tr><td>{xml_text(key)}</td><td>{xml_text(value)}</td></tr>" for key, value in info_rows if not is_empty(value)
    )

    body = [
        f"<title>{xml_text(title)}</title>",
        "<h1>视频口播稿</h1>",
        "<h2>基本信息</h2>",
        "<table><tbody>",
        table_rows,
        "</tbody></table>",
    ]
    if video_url:
        body.extend(["<h2>原视频链接</h2>", f'<p><a type="url-preview" href="{video_url}">打开原视频</a></p>'])
    body.append("<h2>正文口播稿</h2>")
    if paragraphs:
        body.extend(f"<p>{xml_text(paragraph)}</p>" for paragraph in paragraphs)
    else:
        body.append("<p>本地口播稿为空。</p>")
    return "\n".join(body)


def run_docs_create(config, xml_content, *, parent_token=None, parent_position=None, dry_run=False, attempts=6, base_delay=20.0):
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".xml", dir=tmp_dir, delete=False) as handle:
        handle.write(xml_content)
        content_path = Path(handle.name)
    try:
        args = [
            "lark-cli",
            "--profile",
            config["profile"],
            "docs",
            "+create",
            "--api-version",
            "v2",
            "--as",
            "user",
            "--content",
            f"@{content_path.relative_to(ROOT)}",
            "--format",
            "json",
        ]
        if parent_token:
            args.extend(["--parent-token", parent_token])
        if parent_position:
            args.extend(["--parent-position", parent_position])
        if dry_run:
            args.append("--dry-run")
        result = run_command_with_retry(args, timeout=180, attempts=attempts, base_delay=base_delay)
        data = bili.safe_json_from_stdout(result.stdout)
        if not data.get("ok"):
            raise RuntimeError(f"docs +create returned not ok: {json.dumps(data, ensure_ascii=False)[:2000]}")
        return data
    finally:
        content_path.unlink(missing_ok=True)


def update_video_doc_url(config, record_id, doc_url, *, attempts=6, base_delay=20.0):
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    payload = {TRANSCRIPT_FIELD: doc_url}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False)
        payload_path = Path(handle.name)
    try:
        return run_lark_with_retry(
            config,
            [
                "+record-upsert",
                "--as",
                "user",
                "--base-token",
                config["base_token"],
                "--table-id",
                config["tables"]["videos"]["table_id"],
                "--record-id",
                record_id,
                "--json",
                f"@{payload_path.relative_to(ROOT)}",
            ],
            timeout=60,
            attempts=attempts,
            base_delay=base_delay,
        )
    finally:
        payload_path.unlink(missing_ok=True)


def ensure_transcript_field(config, *, dry_run=False):
    table_id = config["tables"]["videos"]["table_id"]
    existing = bili.field_names(config, table_id)
    field = existing.get(TRANSCRIPT_FIELD)
    if field:
        return {"created": False, "field": field}
    if dry_run:
        return {"created": False, "would_create": True, "field": TRANSCRIPT_FIELD_SPEC}
    data = bili.run_lark(
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
            json.dumps(TRANSCRIPT_FIELD_SPEC, ensure_ascii=False),
        ],
        timeout=120,
    )
    return {"created": True, "field": data.get("data", {}).get("field")}


def load_creators(config):
    table_id = config["tables"]["creators"]["table_id"]
    available = bili.field_names(config, table_id)
    fields = [field for field in CREATOR_FIELDS if field in available]
    rows = bili.list_records(config, table_id, fields)
    return {row["_record_id"]: row.get("博主名称") for row in rows}


def load_video_rows(config):
    table_id = config["tables"]["videos"]["table_id"]
    available = bili.field_names(config, table_id)
    fields = [field for field in VIDEO_FIELDS if field in available]
    rows = bili.list_records(config, table_id, fields)
    for row in rows:
        for field in VIDEO_FIELDS:
            row.setdefault(field, None)
    return rows


def select_rows(rows, args):
    selected = []
    for row in rows:
        if args.record_id and row.get("_record_id") != args.record_id:
            continue
        if args.platform != "all":
            if not cell_has_platform(row.get("平台"), args.platform):
                inferred = infer_platform(row)
                if inferred != args.platform:
                    continue
        selected.append(row)
    limit = args.max_records
    if limit is None and not args.record_id and not args.all:
        limit = 1
    return selected[:limit] if limit is not None else selected


def process_row(config, row, creators_by_record_id, args):
    record_id = row["_record_id"]
    existing_url = extract_url(row.get(TRANSCRIPT_FIELD))
    if existing_url and not args.overwrite:
        return {
            "status": "skipped",
            "reason": "existing_doc_url",
            "record_id": record_id,
            "doc_url": existing_url,
        }

    source_field, source_path = pick_transcript_path(row)
    if not source_path:
        return {
            "status": "skipped",
            "reason": "missing_local_transcript",
            "record_id": record_id,
        }

    transcript_text = read_text(source_path)
    xml_content = build_doc_xml(row, source_field, source_path, transcript_text, creators_by_record_id)
    preview = {
        "record_id": record_id,
        "platform": infer_platform(row),
        "title": row.get("视频标题"),
        "doc_title": doc_title(row, creators_by_record_id),
        "source_transcript_path": str(source_path),
        "source_field": source_field,
        "paragraphs": len(clean_transcript_paragraphs(transcript_text)),
        "will_overwrite": bool(existing_url and args.overwrite),
    }
    if args.dry_run:
        return {"status": "created" if not existing_url else "updated", "dry_run": True, **preview}

    data = run_docs_create(
        config,
        xml_content,
        parent_token=args.parent_token,
        parent_position=args.parent_position,
        attempts=args.retry_attempts,
        base_delay=args.retry_delay_seconds,
    )
    document = data.get("data", {}).get("document") or {}
    doc_url = document.get("url")
    if not doc_url:
        raise RuntimeError(f"docs +create returned no document url: {json.dumps(data, ensure_ascii=False)[:2000]}")
    update_video_doc_url(config, record_id, doc_url, attempts=args.retry_attempts, base_delay=args.retry_delay_seconds)
    return {
        "status": "created",
        **preview,
        "doc_url": doc_url,
        "document_id": document.get("document_id"),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Create Feishu docs for local video transcripts and write document URLs back to the video table.")
    parser.add_argument("--record-id", help="Only process one Feishu video record.")
    parser.add_argument("--platform", choices=["B站", "抖音", "all"], default="all", help="Filter records by platform. Default: all.")
    parser.add_argument("--all", action="store_true", help="Process every matching historical video record. Without this, default is one record.")
    parser.add_argument("--max-records", type=int, help="Maximum records to process. Default: 1 unless --record-id is set.")
    parser.add_argument("--dry-run", action="store_true", help="Preview selected records without creating docs or writing Base.")
    parser.add_argument("--overwrite", action="store_true", help=f"Overwrite existing {TRANSCRIPT_FIELD} URLs. Default skips non-empty values.")
    parser.add_argument("--parent-token", help="Optional Feishu folder/wiki parent token for created docs.")
    parser.add_argument("--parent-position", help="Optional parent position such as my_library.")
    parser.add_argument("--manifest-output", help="Optional manifest output path.")
    parser.add_argument("--sleep-seconds", type=float, default=7.0, help="Seconds to wait between real document creations. Default: 7.")
    parser.add_argument("--retry-attempts", type=int, default=6, help="Retry attempts for retryable lark-cli rate-limit/write errors. Default: 6.")
    parser.add_argument("--retry-delay-seconds", type=float, default=20.0, help="Initial retry delay for retryable lark-cli errors. Default: 20.")
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.parent_token and not args.parent_position:
        args.parent_token = DEFAULT_PARENT_TOKEN
    started_at = now_str()
    config = bili.load_config()
    manifest_path = Path(args.manifest_output) if args.manifest_output else MANIFEST_ROOT / f"{ts_slug()}-transcript-docs.json"
    manifest = {
        "started_at": started_at,
        "ended_at": None,
        "base_name": config.get("base_name"),
        "base_token": config.get("base_token"),
        "video_table_id": config["tables"]["videos"]["table_id"],
        "field_name": TRANSCRIPT_FIELD,
        "field": None,
        "args": vars(args),
        "created": [],
        "skipped": [],
        "failed": [],
        "summary": {},
    }
    try:
        manifest["field"] = ensure_transcript_field(config, dry_run=args.dry_run)
        creators_by_record_id = load_creators(config)
        rows = select_rows(load_video_rows(config), args)
        if not rows:
            manifest["skipped"].append({"status": "skipped", "reason": "no_matching_records"})
            write_json(manifest_path, manifest)
        for index, row in enumerate(rows):
            try:
                result = process_row(config, row, creators_by_record_id, args)
                bucket = "created" if result.get("status") in {"created", "updated"} else "skipped"
                manifest[bucket].append(result)
                print(json.dumps(result, ensure_ascii=False))
            except Exception as exc:
                failure = {"status": "failed", "record_id": row.get("_record_id"), "error": str(exc)}
                manifest["failed"].append(failure)
                print(json.dumps(failure, ensure_ascii=False))
            write_json(manifest_path, manifest)
            if not args.dry_run and args.sleep_seconds > 0 and index < len(rows) - 1:
                time.sleep(args.sleep_seconds)
        manifest["ended_at"] = now_str()
        manifest["summary"] = {
            "created": len(manifest["created"]),
            "skipped": len(manifest["skipped"]),
            "failed": len(manifest["failed"]),
            "manifest_path": str(manifest_path),
            "dry_run": args.dry_run,
        }
        return 1 if manifest["failed"] else 0
    finally:
        write_json(manifest_path, manifest)
        print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    raise SystemExit(main())
