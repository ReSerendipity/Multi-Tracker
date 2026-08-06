import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import download_bili_following_latest as base
import postprocess_bili_videos as postprocess


ROOT = Path(__file__).resolve().parent
MANIFEST_ROOT = ROOT / "downloads" / "manifests"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ts_slug():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def resolve_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_curation_file(path):
    payload = json.loads(resolve_path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "records" in payload:
        payload = payload["records"]
    if not isinstance(payload, dict) or not payload:
        raise ValueError("curation file must contain a non-empty record mapping")
    return payload


def normalize_key_points(value):
    if isinstance(value, list):
        points = [str(item).strip().lstrip("-• ").strip() for item in value if str(item).strip()]
        if not points:
            raise ValueError("key_points cannot be empty")
        return "\n".join(f"- {item}" for item in points)
    if not isinstance(value, str):
        raise ValueError("key_points must be a string or list")
    text = value.strip()
    if not text:
        raise ValueError("key_points cannot be empty")
    return text


def normalize_readable_sections(value, record_id):
    sections = value.get("readable_sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError(f"readable_sections is required for {record_id}")
    normalized = []
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise ValueError(f"readable_sections[{index}] must be an object for {record_id}")
        heading = str(section.get("heading") or "").strip()
        paragraphs = section.get("paragraphs")
        if not heading:
            raise ValueError(f"readable_sections[{index}].heading is required for {record_id}")
        if not isinstance(paragraphs, list) or not paragraphs:
            raise ValueError(f"readable_sections[{index}].paragraphs is required for {record_id}")
        paragraphs = [str(item).strip() for item in paragraphs if str(item).strip()]
        if not paragraphs:
            raise ValueError(f"readable_sections[{index}].paragraphs cannot be empty for {record_id}")
        normalized.append({"heading": heading, "paragraphs": paragraphs})
    return normalized


def compact_length(value):
    return len("".join(str(value or "").split()))


def normalize_record(record_id, value):
    if not isinstance(value, dict):
        raise ValueError(f"curation for {record_id} must be an object")
    summary_value = value.get("content_summary")
    if summary_value is None:
        summary_value = value.get("内容摘要")
    if summary_value is None:
        summary_value = ""
    if not isinstance(summary_value, str):
        raise ValueError(f"content_summary must be a string for {record_id}")
    summary = summary_value.strip()
    if not summary:
        raise ValueError(f"content_summary is required for {record_id}")
    key_points = normalize_key_points(value.get("key_points") or value.get("关键要点"))
    readable_sections = normalize_readable_sections(value, record_id)
    readable_text = "\n".join(
        paragraph for section in readable_sections for paragraph in section["paragraphs"]
    )
    source_path = str(value.get("source_transcript_path") or "").strip()
    readable_ratio = None
    if source_path:
        resolved = Path(source_path)
        if not resolved.is_absolute():
            resolved = ROOT / resolved
        if not resolved.is_file():
            raise FileNotFoundError(f"source transcript not found for {record_id}: {resolved}")
        source_path = str(resolved)
        source_text = resolved.read_text(encoding="utf-8", errors="replace")
        source_chars = compact_length(source_text)
        readable_chars = compact_length(readable_text)
        readable_ratio = round(readable_chars / source_chars, 4) if source_chars else None
        allow_short = value.get("allow_short_readable") is True
        quality_note = str(value.get("quality_note") or "").strip()
        if readable_ratio is not None and readable_ratio < 0.5:
            if not allow_short:
                raise ValueError(
                    f"readable transcript ratio is below 0.5 for {record_id}: {readable_ratio}"
                )
            if not quality_note:
                raise ValueError(f"quality_note is required when allow_short_readable=true for {record_id}")
    return {
        "record_id": str(record_id),
        "content_summary": summary,
        "key_points": key_points,
        "source_transcript_path": source_path or None,
        "readable_ratio": readable_ratio,
    }


def load_requested_records(path, record_id=None):
    curations = load_curation_file(path)
    if record_id:
        if record_id not in curations:
            raise ValueError(f"record_id not found in curation file: {record_id}")
        curations = {record_id: curations[record_id]}
    return [normalize_record(key, value) for key, value in curations.items()]


def upsert_content_fields(config, item):
    patch = {
        "内容摘要": item["content_summary"],
        "关键要点": item["key_points"],
    }
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as handle:
        json.dump(patch, handle, ensure_ascii=False)
        payload_path = Path(handle.name)
    try:
        base.run_lark(
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
                item["record_id"],
                "--json",
                f"@{payload_path.relative_to(ROOT)}",
            ],
            timeout=60,
        )
    finally:
        payload_path.unlink(missing_ok=True)
    return patch


def readback_records(config, record_ids):
    rows = base.list_records(
        config,
        config["tables"]["videos"]["table_id"],
        ["内容摘要", "关键要点"],
    )
    wanted = set(record_ids)
    return {row["_record_id"]: row for row in rows if row.get("_record_id") in wanted}


def verify_readback(items, rows_by_id):
    verified = []
    failures = []
    for item in items:
        row = rows_by_id.get(item["record_id"])
        if not row:
            failures.append({"record_id": item["record_id"], "error": "record missing during readback"})
            continue
        actual_summary = str(row.get("内容摘要") or "").strip()
        actual_points = str(row.get("关键要点") or "").strip()
        if actual_summary != item["content_summary"] or actual_points != item["key_points"]:
            failures.append(
                {
                    "record_id": item["record_id"],
                    "error": "readback mismatch",
                    "summary_matches": actual_summary == item["content_summary"],
                    "key_points_match": actual_points == item["key_points"],
                }
            )
            continue
        verified.append({"record_id": item["record_id"], "verified": True})
    return verified, failures


def parse_args():
    parser = argparse.ArgumentParser(description="Write agent-authored transcript summary and key points to Feishu video rows.")
    parser.add_argument("--curation-file", required=True, help="Curation JSON containing content_summary and key_points per record.")
    parser.add_argument("--record-id", help="Only write one record from the curation file.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and show planned patches without writing Feishu.")
    parser.add_argument("--manifest-output", help="Optional output manifest path.")
    return parser.parse_args()


def main():
    args = parse_args()
    curation_path = resolve_path(args.curation_file)
    manifest_path = (
        Path(args.manifest_output)
        if args.manifest_output
        else MANIFEST_ROOT / f"{ts_slug()}-transcript-content-writeback.json"
    )
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    manifest = {
        "started_at": now_str(),
        "ended_at": None,
        "curation_file": str(curation_path),
        "dry_run": args.dry_run,
        "planned": [],
        "updated": [],
        "verified": [],
        "failures": [],
        "summary": {},
    }
    try:
        items = load_requested_records(curation_path, args.record_id)
        manifest["planned"] = [
            {
                "record_id": item["record_id"],
                "content_summary": item["content_summary"],
                "key_points": item["key_points"],
                "source_transcript_path": item["source_transcript_path"],
                "readable_ratio": item["readable_ratio"],
            }
            for item in items
        ]
        if args.dry_run:
            return 0

        config = base.load_config()
        postprocess.ensure_summary_fields(config)
        for item in items:
            try:
                patch = upsert_content_fields(config, item)
                manifest["updated"].append({"record_id": item["record_id"], "patch": patch})
            except Exception as exc:
                manifest["failures"].append({"record_id": item["record_id"], "stage": "write", "error": str(exc)})
                break

        if not manifest["failures"]:
            rows_by_id = readback_records(config, [item["record_id"] for item in items])
            manifest["verified"], verification_failures = verify_readback(items, rows_by_id)
            manifest["failures"].extend(verification_failures)
        return 1 if manifest["failures"] else 0
    except Exception as exc:
        manifest["failures"].append({"stage": "validation", "error": str(exc)})
        return 1
    finally:
        manifest["ended_at"] = now_str()
        manifest["summary"] = {
            "planned": len(manifest["planned"]),
            "updated": len(manifest["updated"]),
            "verified": len(manifest["verified"]),
            "failed": len(manifest["failures"]),
            "dry_run": args.dry_run,
            "manifest_path": str(manifest_path),
        }
        write_json(manifest_path, manifest)
        for failure in manifest["failures"]:
            print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
        print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    raise SystemExit(main())
