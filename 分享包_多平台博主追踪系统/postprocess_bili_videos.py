import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import download_bili_following_latest as base


ROOT = Path(__file__).resolve().parent
MANIFEST_ROOT = ROOT / "downloads" / "manifests"
POSTPROCESS_DIRNAME = "postprocess"
SOURCE_SUBTITLE_EXTS = {".srt", ".vtt", ".json"}
SUMMARY_FIELDS = {
    "内容摘要": {
        "type": "text",
        "name": "内容摘要",
        "description": "由 Agent 阅读清洗口播稿后生成，不由本地抽取程序自动填充。",
    },
    "关键要点": {
        "type": "text",
        "name": "关键要点",
        "description": "由 Agent 阅读清洗口播稿后提炼，不由本地抽取程序自动填充。",
    },
}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ts_slug():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)


def read_text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def latest_manifest_path(pattern):
    matches = list(MANIFEST_ROOT.glob(pattern))
    if not matches:
        raise RuntimeError(f"no manifest found for pattern: {pattern}")
    return max(matches, key=lambda p: p.stat().st_mtime)


def bvids_from_download_manifest(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    bvids = []
    for item in data.get("successes") or []:
        bvid = str(item.get("bvid") or "").strip()
        if bvid:
            bvids.append(bvid)
    return set(bvids)


def run_command(args, *, timeout=None, check=True):
    result = subprocess.run(
        base.normalize_command(args),
        cwd=ROOT,
        env=base.command_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            "command failed\n"
            f"args: {args}\n"
            f"exit: {result.returncode}\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )
    return result


def safe_name(value, max_len=70):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or ""))
    value = re.sub(r"\s+", " ", value).strip(" .")
    return (value or "untitled")[:max_len]


def media_sort_key(path):
    match = re.match(r"^(\d+)[-_]", path.name)
    if match:
        return (int(match.group(1)), path.name)
    match = re.search(r"(\d+)", path.name)
    return (int(match.group(1)) if match else 10**9, path.name)


def bvid_dir_from_row(row):
    info_path = row.get("元数据文件路径")
    if info_path and Path(str(info_path)).exists():
        return Path(str(info_path)).parent
    video_path = row.get("视频文件路径")
    if video_path and Path(str(video_path)).exists():
        path = Path(str(video_path))
        for parent in [path.parent, *path.parents]:
            if parent.name.startswith("BV"):
                return parent
    return None


def find_media_parts(row):
    bvid_dir = bvid_dir_from_row(row)
    candidates = []
    if bvid_dir and bvid_dir.exists():
        candidates = [
            path
            for path in bvid_dir.rglob("*.mp4")
            if path.is_file()
            and POSTPROCESS_DIRNAME not in path.parts
            and not path.name.endswith(".section.mp4")
        ]
    video_path = row.get("视频文件路径")
    if video_path and Path(str(video_path)).exists():
        path = Path(str(video_path))
        if path not in candidates:
            candidates.append(path)
    candidates = sorted(set(candidates), key=media_sort_key)
    return candidates


def find_source_subtitles(bvid_dir):
    if not bvid_dir or not bvid_dir.exists():
        return []
    candidates = []
    for path in bvid_dir.rglob("*"):
        if not path.is_file():
            continue
        parts_lower = {part.lower() for part in path.parts}
        if POSTPROCESS_DIRNAME.lower() in parts_lower:
            continue
        if "subtitles" not in parts_lower and not path.name.lower().startswith("subtitle"):
            continue
        if path.suffix.lower() not in SOURCE_SUBTITLE_EXTS:
            continue
        candidates.append(path)

    def subtitle_sort_key(path):
        name = path.name.lower()
        lang_score = 0
        for index, marker in enumerate(["zh-hans", "zh-cn", "zh", "ai-zh", "auto"]):
            if marker in name:
                lang_score = index
                break
        else:
            lang_score = 99
        ext_score = {".srt": 0, ".vtt": 1, ".json": 2}.get(path.suffix.lower(), 9)
        return (lang_score, ext_score, path.name)

    return sorted(candidates, key=subtitle_sort_key)


def strip_subtitle_line(line):
    line = re.sub(r"<[^>]+>", "", line)
    line = re.sub(r"\{\\[^}]+\}", "", line)
    return line.strip()


def parse_timed_subtitle(path):
    lines = []
    for raw in read_text(path).splitlines():
        line = raw.strip("\ufeff").strip()
        if not line:
            continue
        if line.upper() == "WEBVTT" or line.upper().startswith(("NOTE", "STYLE", "REGION")):
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if "-->" in line:
            continue
        line = strip_subtitle_line(line)
        if line:
            lines.append(line)
    return "\n".join(dedupe_adjacent_lines(lines))


def parse_json_subtitle(path):
    payload = json.loads(read_text(path))
    lines = []
    if isinstance(payload, dict) and isinstance(payload.get("body"), list):
        for item in payload["body"]:
            if isinstance(item, dict):
                text = item.get("content") or item.get("text")
                if text:
                    lines.append(strip_subtitle_line(str(text)))
    elif isinstance(payload, dict) and isinstance(payload.get("events"), list):
        for event in payload["events"]:
            for segment in event.get("segs") or []:
                text = segment.get("utf8")
                if text:
                    lines.append(strip_subtitle_line(str(text)))
    return "\n".join(dedupe_adjacent_lines([line for line in lines if line]))


def dedupe_adjacent_lines(lines):
    deduped = []
    for line in lines:
        if deduped and deduped[-1] == line:
            continue
        deduped.append(line)
    return deduped


def load_best_source_subtitle(bvid_dir, min_chars):
    for path in find_source_subtitles(bvid_dir):
        try:
            if path.suffix.lower() == ".json":
                text = parse_json_subtitle(path)
            else:
                text = parse_timed_subtitle(path)
        except Exception:
            continue
        if len(re.sub(r"\s+", "", text)) >= min_chars:
            return path, text
    return None, ""


def ffprobe_duration(path):
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def extract_audio(media_path, audio_path, *, force=False):
    if audio_path.exists() and audio_path.stat().st_size > 0 and not force:
        return False
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            str(media_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            str(audio_path),
        ],
        timeout=60 * 30,
    )
    return True


def transcribe_audio(audio_path, asr_dir, *, model, language, device, threads, initial_prompt, force=False):
    asr_dir.mkdir(parents=True, exist_ok=True)
    txt_path = asr_dir / f"{audio_path.stem}.txt"
    json_path = asr_dir / f"{audio_path.stem}.json"
    if txt_path.exists() and json_path.exists() and not force:
        return txt_path
    args = [
        "whisper",
        str(audio_path),
        "--model",
        model,
        "--device",
        device,
        "--fp16",
        "True" if str(device).lower().startswith("cuda") else "False",
        "--language",
        language,
        "--task",
        "transcribe",
        "--output_dir",
        str(asr_dir),
        "--output_format",
        "all",
        "--verbose",
        "False",
        "--condition_on_previous_text",
        "False",
    ]
    if initial_prompt:
        args.extend(["--initial_prompt", initial_prompt])
    if threads:
        args.extend(["--threads", str(threads)])
    run_command(args, timeout=60 * 60 * 8)
    if not txt_path.exists():
        produced = list(asr_dir.glob("*.txt"))
        if produced:
            return produced[0]
        raise RuntimeError(f"Whisper did not create txt output for {audio_path}")
    return txt_path


def normalize_transcript(text):
    lines = []
    seen_blank = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if not seen_blank and lines:
                lines.append("")
            seen_blank = True
            continue
        seen_blank = False
        line = re.sub(r"\s+", " ", line)
        if line in {"谢谢观看", "感谢观看", "字幕由Amara.org社区提供", "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目"}:
            continue
        if re.fullmatch(r"字幕\s*(by|BY|By)?\s*.+", line):
            continue
        if re.fullmatch(r".*(字幕|翻译)\s*(by|BY|By)\s*.*", line):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sentences(text):
    parts = re.split(r"(?<=[。！？!?；;])\s*", text.replace("\n", " "))
    return [part.strip() for part in parts if len(part.strip()) >= 12]


def summarize_local(row, cleaned_text, description_text, metrics):
    title = row.get("视频标题") or row.get("BVID") or ""
    sentences = split_sentences(cleaned_text)
    keywords = [
        "AI",
        "模型",
        "智能体",
        "工具",
        "流程",
        "方法",
        "案例",
        "数据",
        "内容",
        "视频",
        "产品",
        "代码",
    ]
    scored = []
    for idx, sentence in enumerate(sentences):
        score = sum(1 for key in keywords if key.lower() in sentence.lower())
        score += max(0, 5 - idx * 0.05)
        scored.append((score, idx, sentence))
    selected = [item[2] for item in sorted(scored, key=lambda x: (-x[0], x[1]))[:8]]
    selected = sorted(selected, key=lambda sentence: sentences.index(sentence) if sentence in sentences else 10**9)
    desc = description_text.strip() if description_text else ""
    metric_bits = []
    if metrics:
        for key in ["播放量", "点赞量", "收藏数", "投币数", "分享数", "评论数", "弹幕数"]:
            value = metrics.get(key)
            if value is not None:
                metric_bits.append(f"{key}: {value}")
    overview_source = cleaned_text.strip() or desc
    overview = overview_source[:600].strip()
    key_points = [f"- {sentence}" for sentence in selected]
    md = [
        f"# {title}",
        "",
        f"- BVID: {row.get('BVID') or ''}",
        f"- 视频链接: {row.get('视频链接') or ''}",
        f"- 本文件性质: 本地自动抽取参考，不是最终内容摘要或关键要点",
    ]
    if metric_bits:
        md.append(f"- 数据快照: {'; '.join(metric_bits)}")
    if desc:
        md.extend(["", "## 视频文案", "", desc])
    md.extend(["", "## 自动抽取参考：原文开头", "", overview])
    if selected:
        md.extend(["", "## 自动抽取参考：候选句"])
        md.extend(key_points)
    return {
        "markdown": "\n".join(md).strip() + "\n",
        "summary_method": "local-extractive",
    }


def read_optional_text(path):
    if path and Path(str(path)).exists():
        return read_text(str(path))
    return ""


def read_metrics(row):
    bvid_dir = bvid_dir_from_row(row)
    if not bvid_dir:
        return {}
    path = bvid_dir / "metrics-snapshot.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload.get("metrics") or {}


def update_video_record(config, record_id, patch):
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as handle:
        json.dump(patch, handle, ensure_ascii=False)
        payload_path = Path(handle.name)
    try:
        return base.run_lark(
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
        )
    finally:
        payload_path.unlink(missing_ok=True)


def ensure_summary_fields(config):
    table_id = config["tables"]["videos"]["table_id"]
    existing = base.field_names(config, table_id)
    missing = []
    for name, spec in SUMMARY_FIELDS.items():
        if name in existing:
            continue
        base.run_lark(
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
        )
        missing.append(name)
    if missing:
        print(f"Added summary fields: {', '.join(missing)}")


def create_task_log_with_retry(config, started_at, ended_at, success_count, failure_count, manifest_path, summary, *, task_name, task_type, target_scope):
    last_error = None
    for attempt in range(4):
        try:
            base.create_task_log(
                config,
                started_at,
                ended_at,
                success_count,
                failure_count,
                manifest_path,
                summary,
                task_name=task_name,
                task_type=task_type,
                target_scope=target_scope,
            )
            return True
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
    print(f"[warn] task log write failed: {last_error}", file=sys.stderr)
    return False


def process_video(config, row, args):
    bvid = str(row.get("BVID") or "").strip()
    record_id = row["_record_id"]
    if not bvid:
        return {"status": "skipped", "reason": "missing_bvid", "record_id": record_id}
    bvid_dir = bvid_dir_from_row(row)
    post_dir = bvid_dir / POSTPROCESS_DIRNAME if bvid_dir else None
    if bvid_dir and not args.ignore_source_subtitles and not args.audio_only:
        subtitle_path, subtitle_text = load_best_source_subtitle(bvid_dir, args.min_transcript_chars)
        if subtitle_path:
            raw_path = post_dir / "speech-raw.txt"
            clean_path = post_dir / "speech-clean.txt"
            write_text(raw_path, f"## Source subtitle ({subtitle_path})\n\n{subtitle_text.strip()}\n")
            cleaned_text = normalize_transcript(subtitle_text)
            write_text(clean_path, cleaned_text + "\n")

            description_text = read_optional_text(bvid_dir / "video-description.txt")
            metrics = read_metrics(row)
            summary = summarize_local(row, cleaned_text, description_text, metrics)
            summary_md = summary["markdown"]
            summary_path = post_dir / "summary.md"
            write_text(summary_path, summary_md)

            process_manifest = {
                "bvid": bvid,
                "record_id": record_id,
                "processed_at": now_str(),
                "source": "subtitle",
                "subtitle_path": str(subtitle_path),
                "raw_transcript_path": str(raw_path),
                "clean_transcript_path": str(clean_path),
                "summary_path": str(summary_path),
            }
            process_manifest_path = post_dir / "postprocess-manifest.json"
            write_json(process_manifest_path, process_manifest)

            patch = {
                "音频文件路径": str(subtitle_path),
                "音频状态": "跳过",
                "转写状态": "已转写",
                "原始文案路径": str(raw_path),
                "清洗文案路径": str(clean_path),
                "摘要/选题备注": "口播稿来源: B站字幕，未运行 Whisper ASR。",
                "最近采集时间": now_str(),
            }
            if not args.dry_run:
                update_video_record(config, record_id, patch)
            return {
                "status": "subtitle_done",
                "bvid": bvid,
                "record_id": record_id,
                "subtitle_path": str(subtitle_path),
                "raw_transcript_path": str(raw_path),
                "clean_transcript_path": str(clean_path),
                "summary_path": str(summary_path),
            }

    duration = row.get("时长秒")
    if args.max_duration_seconds and duration and duration > args.max_duration_seconds:
        patch = {
            "音频状态": "跳过",
            "转写状态": "无需转写",
            "摘要/选题备注": f"跳过 ASR：视频时长 {int(duration)} 秒超过阈值 {args.max_duration_seconds} 秒，且未发现可复用字幕。",
            "最近采集时间": now_str(),
        }
        if not args.dry_run:
            update_video_record(config, record_id, patch)
        return {"status": "skipped_long", "bvid": bvid, "duration": duration}

    if not bvid_dir:
        raise RuntimeError("cannot locate local BVID directory")
    audio_dir = post_dir / "audio"
    asr_dir = post_dir / "asr"
    media_parts = find_media_parts(row)
    if args.max_parts:
        media_parts = media_parts[: args.max_parts]
    if not media_parts:
        raise RuntimeError("no local mp4 media files found")

    audio_manifest = []
    for index, media_path in enumerate(media_parts, start=1):
        audio_path = audio_dir / f"part-{index:03d}.m4a"
        extracted = extract_audio(media_path, audio_path, force=args.force_audio)
        audio_manifest.append(
            {
                "part": index,
                "media_path": str(media_path),
                "audio_path": str(audio_path),
                "duration": ffprobe_duration(media_path),
                "extracted": extracted,
            }
        )
    audio_manifest_path = audio_dir / "audio-manifest.json"
    write_json(audio_manifest_path, {"bvid": bvid, "created_at": now_str(), "parts": audio_manifest})

    if args.audio_only:
        patch = {
            "音频文件路径": str(audio_manifest_path if len(audio_manifest) > 1 else audio_manifest[0]["audio_path"]),
            "音频状态": "已下载",
            "最近采集时间": now_str(),
        }
        if not args.dry_run:
            update_video_record(config, record_id, patch)
        return {"status": "audio_done", "bvid": bvid, "audio_parts": len(audio_manifest)}

    raw_parts = []
    for item in audio_manifest:
        audio_path = Path(item["audio_path"])
        part_asr_dir = asr_dir / f"part-{int(item['part']):03d}"
        txt_path = transcribe_audio(
            audio_path,
            part_asr_dir,
            model=args.model,
            language=args.language,
            device=args.device,
            threads=args.threads,
            initial_prompt=args.initial_prompt,
            force=args.force_asr,
        )
        raw_parts.append((item["part"], txt_path, read_text(txt_path)))

    raw_path = post_dir / "speech-raw.txt"
    raw_text = []
    for part, txt_path, text in raw_parts:
        raw_text.append(f"## Part {part:03d} ({txt_path})\n\n{text.strip()}")
    write_text(raw_path, "\n\n".join(raw_text).strip() + "\n")

    clean_path = post_dir / "speech-clean.txt"
    cleaned_text = normalize_transcript("\n\n".join(text for _, _, text in raw_parts))
    write_text(clean_path, cleaned_text + "\n")

    description_text = read_optional_text(bvid_dir / "video-description.txt")
    metrics = read_metrics(row)
    has_speech = len(re.sub(r"\s+", "", cleaned_text)) >= args.min_transcript_chars
    summary = summarize_local(row, cleaned_text if has_speech else "", description_text, metrics)
    summary_md = summary["markdown"]
    summary_path = post_dir / "summary.md"
    write_text(summary_path, summary_md)

    process_manifest = {
        "bvid": bvid,
        "record_id": record_id,
        "processed_at": now_str(),
        "model": args.model,
        "device": args.device,
        "language": args.language,
        "media_parts": len(media_parts),
        "audio_manifest_path": str(audio_manifest_path),
        "raw_transcript_path": str(raw_path),
        "clean_transcript_path": str(clean_path),
        "summary_path": str(summary_path),
    }
    process_manifest_path = post_dir / "postprocess-manifest.json"
    write_json(process_manifest_path, process_manifest)

    patch = {
        "音频文件路径": str(audio_manifest_path if len(audio_manifest) > 1 else audio_manifest[0]["audio_path"]),
        "音频状态": "已下载",
        "转写状态": "已转写" if has_speech else "无需转写",
        "原始文案路径": str(raw_path),
        "清洗文案路径": str(clean_path),
        "最近采集时间": now_str(),
    }
    if not args.dry_run:
        update_video_record(config, record_id, patch)
    return {
        "status": "processed",
        "bvid": bvid,
        "record_id": record_id,
        "media_parts": len(media_parts),
        "audio_path": patch["音频文件路径"],
        "raw_transcript_path": str(raw_path),
        "clean_transcript_path": str(clean_path),
        "summary_path": str(summary_path),
        "has_speech": has_speech,
    }


def should_process(row, args):
    if getattr(args, "bvid_filter", None) and str(row.get("BVID") or "").strip() not in args.bvid_filter:
        return False
    if args.bvid and str(row.get("BVID") or "").strip() != args.bvid:
        return False
    if args.record_id and row.get("_record_id") != args.record_id:
        return False
    if not args.force and not args.audio_only:
        status = row.get("转写状态")
        if isinstance(status, list):
            status = status[0] if status else None
        if status == "无需转写":
            return False
        if status == "已转写" and row.get("原始文案路径") and row.get("清洗文案路径"):
            return False
    if not args.force and args.audio_only:
        status = row.get("音频状态")
        if isinstance(status, list):
            status = status[0] if status else None
        if status in {"已下载", "跳过"} and row.get("音频文件路径"):
            return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--initial-prompt", default="")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-videos", type=int)
    parser.add_argument("--bvid")
    parser.add_argument("--record-id")
    parser.add_argument("--download-manifest", help="Only process BVIDs in this bili-latest-download manifest.")
    parser.add_argument("--latest-download-manifest", action="store_true", help="Only process BVIDs in the latest bili-latest-download manifest.")
    parser.add_argument("--max-duration-seconds", type=int, default=60 * 60)
    parser.add_argument("--min-transcript-chars", type=int, default=30)
    parser.add_argument("--include-long", action="store_true")
    parser.add_argument("--ignore-source-subtitles", action="store_true")
    parser.add_argument("--max-parts", type=int)
    parser.add_argument("--audio-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--force-audio", action="store_true")
    parser.add_argument("--force-asr", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.include_long:
        args.max_duration_seconds = None
    if args.latest_download_manifest:
        args.download_manifest = str(latest_manifest_path("*-bili-latest-download.json"))
    args.bvid_filter = bvids_from_download_manifest(args.download_manifest) if args.download_manifest else None

    started_at = now_str()
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = MANIFEST_ROOT / f"{ts_slug()}-bili-postprocess.json"
    manifest = {
        "started_at": started_at,
        "model": args.model,
        "device": args.device,
        "language": args.language,
        "max_duration_seconds": args.max_duration_seconds,
        "audio_only": args.audio_only,
        "source_download_manifest": args.download_manifest,
        "successes": [],
        "skipped": [],
        "failures": [],
    }
    write_json(manifest_path, manifest)

    config = base.load_config()
    ensure_summary_fields(config)
    rows = base.list_records(
        config,
        config["tables"]["videos"]["table_id"],
        [
            "视频标题",
            "BVID",
            "视频链接",
            "视频文件路径",
            "元数据文件路径",
            "时长秒",
            "音频文件路径",
            "音频状态",
            "转写状态",
            "原始文案路径",
            "清洗文案路径",
            "视频文案路径",
            "摘要/选题备注",
        ],
    )
    processed = 0
    for row in rows:
        if not should_process(row, args):
            continue
        if args.max_videos is not None and processed >= args.max_videos:
            break
        bvid = row.get("BVID")
        print(f"[postprocess] {bvid} {row.get('视频标题') or ''}")
        try:
            result = process_video(config, row, args)
            if result["status"].startswith("skipped"):
                manifest["skipped"].append(result)
                print(f"  skipped: {result['status']}")
            else:
                manifest["successes"].append(result)
                print(f"  done: {result['status']}")
            processed += 1
        except Exception as exc:
            error = {
                "bvid": bvid,
                "record_id": row.get("_record_id"),
                "stage": "postprocess",
                "error": str(exc)[-2000:],
            }
            manifest["failures"].append(error)
            patch = {
                "音频状态": "失败",
                "转写状态": "失败",
                "摘要/选题备注": f"后处理失败: {str(exc)[-800:]}",
                "最近采集时间": now_str(),
            }
            if not args.dry_run and row.get("_record_id"):
                try:
                    update_video_record(config, row["_record_id"], patch)
                except Exception as write_exc:
                    error["writeback_error"] = str(write_exc)[-1000:]
            print(f"  failed: {str(exc).splitlines()[-1] if str(exc).splitlines() else exc}")
            processed += 1
        manifest["ended_at"] = now_str()
        manifest["summary"] = {
            "processed": len(manifest["successes"]),
            "skipped": len(manifest["skipped"]),
            "failed": len(manifest["failures"]),
        }
        write_json(manifest_path, manifest)

    manifest["ended_at"] = now_str()
    manifest["summary"] = {
        "processed": len(manifest["successes"]),
        "skipped": len(manifest["skipped"]),
        "failed": len(manifest["failures"]),
    }
    write_json(manifest_path, manifest)
    failures_summary = "; ".join(f"{f.get('bvid')}: {f.get('error', '')[:80]}" for f in manifest["failures"][:10])
    task_name = "视频后处理：音频提取" if args.audio_only else "视频后处理：字幕/ASR口播稿与参考材料"
    task_type = "音频提取" if args.audio_only else "ASR转写"
    if not args.dry_run:
        create_task_log_with_retry(
            config,
            started_at,
            manifest["ended_at"],
            len(manifest["successes"]),
            len(manifest["failures"]),
            manifest_path,
            failures_summary,
            task_name=task_name,
            task_type=task_type,
            target_scope=f"飞书视频表：已下载视频；max_duration_seconds={args.max_duration_seconds}",
        )
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise
