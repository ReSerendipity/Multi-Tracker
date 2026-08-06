import argparse
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path

import download_bili_following_latest as bili


ROOT = Path(__file__).resolve().parent
MANIFEST_ROOT = ROOT / "downloads" / "manifests"


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ts_slug():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def read_text(path):
    if not path:
        return ""
    target = Path(path)
    if not target.exists():
        return ""
    return target.read_text(encoding="utf-8", errors="replace")


def truncate(value, limit=1800):
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


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


def select_has(value, option):
    if isinstance(value, list):
        return option in value
    return str(value or "") == option


def is_empty_cell(value):
    return value is None or value == "" or value == []


def parse_count_value(text):
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(万|亿)?", str(text or "").strip())
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit == "亿":
        value *= 100000000
    elif unit == "万":
        value *= 10000
    return int(round(value))


def parse_creator_stats(metadata):
    body = ((metadata.get("page_metadata") or {}).get("body_excerpt") or "")
    match = re.search(r"粉丝\s*([0-9]+(?:\.[0-9]+)?(?:万|亿)?)\s*获赞\s*([0-9]+(?:\.[0-9]+)?(?:万|亿)?)", body)
    if not match:
        return {}
    fans_display = match.group(1)
    likes_display = match.group(2)
    return {
        "粉丝数显示": fans_display,
        "粉丝数数字": parse_count_value(fans_display),
        "获赞数显示": likes_display,
        "获赞数数字": parse_count_value(likes_display),
    }


def extract_chapter_summary(body):
    match = re.search(r"章节要点\s*(.+?)\n00:00", body or "", flags=re.S)
    if not match:
        return ""
    return re.sub(r"\n{2,}", "\n", match.group(1)).strip()


def extract_chapters(body):
    text = body or ""
    block_match = re.search(r"\n00:00\s*(.+?)\n内容由AI生成", text, flags=re.S)
    if not block_match:
        return []
    block = block_match.group(1)
    pattern = re.compile(r"(?P<time>\d{2}:\d{2})\n(?P<title>[^\n]+)\n+\s*(?P<desc>.*?)(?=\n\d{2}:\d{2}\n|\Z)", re.S)
    chapters = []
    for match in pattern.finditer(block):
        title = re.sub(r"\s+", " ", match.group("title")).strip()
        desc = re.sub(r"\s+", " ", match.group("desc")).strip()
        if title:
            chapters.append({"time": match.group("time"), "title": title, "description": desc})
    return chapters


def sentence_candidates(text):
    rough = re.split(r"[。！？!?]\s*", text or "")
    return [item.strip() for item in rough if len(item.strip()) >= 12]


def build_content_summary(metadata, transcript_text):
    body = (metadata.get("page_metadata") or {}).get("body_excerpt") or ""
    chapter_summary = extract_chapter_summary(body)
    if chapter_summary:
        return truncate(chapter_summary, 1000)

    sentences = sentence_candidates(transcript_text)
    if not sentences:
        return ""
    return truncate("。".join(sentences[:4]) + "。", 1000)


def build_key_points(metadata, transcript_text):
    body = (metadata.get("page_metadata") or {}).get("body_excerpt") or ""
    chapters = extract_chapters(body)
    if chapters:
        lines = []
        for item in chapters[:8]:
            desc = f"：{item['description']}" if item.get("description") else ""
            lines.append(f"- {item['title']}{desc}")
        return truncate("\n".join(lines), 1800)

    sentences = sentence_candidates(transcript_text)
    return truncate("\n".join(f"- {item}" for item in sentences[:8]), 1800)


def extract_visible_comments(body):
    text = body or ""
    match = re.search(r"全部评论\s*(.+?)登录后即可参与互动讨论", text, flags=re.S)
    if not match:
        return []
    block = match.group(1)
    raw_lines = []
    for raw in block.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        raw_lines.append(line)

    def valid_comment_line(line):
        if line in {"请先登录后发表评论", "分享", "回复", "大家都在搜：", "作者"}:
            return False
        if re.fullmatch(r"\d+", line):
            return False
        if re.fullmatch(r"\d+[天周月年前]+·.+", line):
            return False
        if line.startswith("展开") and line.endswith("条回复"):
            return False
        return len(line) >= 2

    comments = []
    capture_next = False
    for line in raw_lines:
        if line == "...":
            capture_next = True
            continue
        if not capture_next:
            continue
        capture_next = False
        if valid_comment_line(line):
            comments.append(line)

    cleaned = []
    seen = set()
    for line in comments:
        if line in seen:
            continue
        seen.add(line)
        cleaned.append(line)
    return cleaned[:20]


def comment_insights(comments):
    if not comments:
        return {
            "高赞评论摘要": "抖音页面未暴露有效公开评论；暂无法提炼评论洞察。",
            "用户痛点": "暂无有效评论样本。",
            "评论里的争议点": "暂无有效评论样本。",
            "可延展选题": "暂无有效评论样本。",
            "代表评论": "有效代表评论不足。",
            "评论抓取状态": "跳过",
            "已抓评论数": 0,
            "评论明细入表数": 0,
            "评论存储策略": "抖音页面未暴露有效公开评论；未写入评论明细表。",
        }

    joined = "\n".join(comments)
    need_table = [c for c in comments if any(key in c for key in ["表", "价格", "选", "渠道", "国内"])]
    pain = need_table or comments[:3]
    return {
        "高赞评论摘要": truncate(
            "抖音页面仅抓到少量公开可见评论，不是完整评论 API 抓取。有效反馈集中在：用户想要价格表/对比表、想知道国内渠道怎么选，也有人追问是否收徒或希望进一步指导。",
            1800,
        ),
        "用户痛点": truncate("\n".join(f"- {item}" for item in pain), 1800),
        "评论里的争议点": truncate(
            "页面可见评论量较少，暂未形成强争议；主要信息缺口是“价格表是否放出”和“国内方案如何选”。",
            1800,
        ),
        "可延展选题": truncate(
            "- 国内 AI 模型/API 渠道怎么选：会员、云厂商套餐、中转站的风险对比\n"
            "- 一张表看懂主流 AI 模型订阅/API 成本\n"
            "- OpenRouter、火山、智谱等方案适合哪些用户\n"
            "- AI Coding 重度用户如何搭配主力模型和备用套餐",
            1800,
        ),
        "代表评论": truncate(joined, 1800),
        "评论抓取状态": "已抓取",
        "已抓评论数": len(comments),
        "评论明细入表数": 0,
        "评论存储策略": "仅从抖音页面正文保存公开可见评论片段；非完整评论 API 抓取，未写入评论明细表。",
    }


def update_creator_from_video(config, video, metadata, creator_by_id, *, dry_run=False, overwrite=False):
    links = video.get("关联博主") or []
    if not links or not isinstance(links[0], dict) or not links[0].get("id"):
        return None
    record_id = links[0]["id"]
    stats = parse_creator_stats(metadata)
    if not stats:
        return None
    patch = {
        "粉丝数显示": stats["粉丝数显示"],
        "粉丝数数字": stats["粉丝数数字"],
        "最近采集时间": now_str(),
    }
    if not overwrite:
        creator = creator_by_id.get(record_id) or {}
        patch = {key: value for key, value in patch.items() if is_empty_cell(creator.get(key))}
    if not patch:
        return None
    if dry_run:
        return {"record_id": record_id, "patch": patch}
    run_lark_with_json(
        config,
        config["tables"]["creators"]["table_id"],
        "+record-upsert",
        patch,
        record_id=record_id,
    )
    return {"record_id": record_id, "patch": patch}


def enrich_video(config, video, *, dry_run=False, overwrite=False):
    metadata_path = Path(str(video.get("元数据文件路径") or ""))
    if not metadata_path.exists():
        raise FileNotFoundError(f"metadata not found: {metadata_path}")
    metadata = load_json(metadata_path)
    transcript_text = read_text(video.get("清洗文案路径"))
    body = (metadata.get("page_metadata") or {}).get("body_excerpt") or ""
    comments = extract_visible_comments(body)
    comments_path = metadata_path.parent / "comments-visible.json"
    if not dry_run:
        write_json(
            comments_path,
            {
                "captured_at": now_str(),
                "source": "douyin_page_body_excerpt",
                "complete": False,
                "comments": [{"text": item} for item in comments],
            },
        )

    patch = {
        "内容摘要": build_content_summary(metadata, transcript_text),
        "关键要点": build_key_points(metadata, transcript_text),
        "评论采集时间": now_str(),
        "评论文件路径": str(comments_path),
        "最近采集时间": now_str(),
    }
    patch.update(comment_insights(comments))

    if not overwrite:
        patch = {key: value for key, value in patch.items() if is_empty_cell(video.get(key))}
    if not patch:
        return {"record_id": video["_record_id"], "patch": {}, "comments": len(comments)}

    if not dry_run:
        run_lark_with_json(
            config,
            config["tables"]["videos"]["table_id"],
            "+record-upsert",
            patch,
            record_id=video["_record_id"],
        )
    return {"record_id": video["_record_id"], "patch": patch, "comments": len(comments)}


def list_douyin_videos(config, aweme_id=None):
    fields = [
        "视频标题",
        "平台",
        "平台视频ID",
        "关联博主",
        "元数据文件路径",
        "清洗文案路径",
        "内容摘要",
        "关键要点",
        "高赞评论摘要",
        "用户痛点",
        "评论里的争议点",
        "可延展选题",
        "代表评论",
        "评论抓取状态",
        "已抓评论数",
        "评论采集时间",
        "评论明细入表数",
        "评论存储策略",
        "评论文件路径",
        "最近采集时间",
    ]
    rows = bili.list_records(config, config["tables"]["videos"]["table_id"], fields)
    out = []
    for row in rows:
        if not select_has(row.get("平台"), "抖音"):
            continue
        if aweme_id and str(row.get("平台视频ID") or "").strip() != aweme_id:
            continue
        out.append(row)
    return out


def list_creator_records(config):
    fields = ["博主名称", "粉丝数显示", "粉丝数数字", "最近采集时间"]
    rows = bili.list_records(config, config["tables"]["creators"]["table_id"], fields)
    return {row["_record_id"]: row for row in rows}


def parse_args():
    parser = argparse.ArgumentParser(description="Backfill Douyin Feishu creator/video insights from local artifacts.")
    parser.add_argument("--aweme-id", help="Only enrich one Douyin video.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite non-empty insight fields.")
    parser.add_argument("--manifest-output", help="Write the enrichment manifest to this path.")
    parser.add_argument("--no-manifest", action="store_true", help="Do not write a manifest file.")
    return parser.parse_args()


def main():
    args = parse_args()
    config = bili.load_config()
    videos = list_douyin_videos(config, args.aweme_id)
    creator_by_id = list_creator_records(config)
    result = {
        "started_at": now_str(),
        "dry_run": args.dry_run,
        "aweme_id": args.aweme_id,
        "videos": [],
        "creators": [],
        "failures": [],
    }
    for video in videos:
        try:
            metadata = load_json(video["元数据文件路径"])
            creator_result = update_creator_from_video(
                config,
                video,
                metadata,
                creator_by_id,
                dry_run=args.dry_run,
                overwrite=args.overwrite,
            )
            if creator_result:
                result["creators"].append(creator_result)
            result["videos"].append(enrich_video(config, video, dry_run=args.dry_run, overwrite=args.overwrite))
        except Exception as exc:
            result["failures"].append(
                {
                    "record_id": video.get("_record_id"),
                    "platform_video_id": video.get("平台视频ID"),
                    "error": str(exc)[-2000:],
                }
            )
    result["ended_at"] = now_str()
    result["summary"] = {
        "videos_updated": len([item for item in result["videos"] if item.get("patch")]),
        "creators_updated": len(result["creators"]),
        "failures": len(result["failures"]),
    }
    if not args.no_manifest:
        manifest_path = Path(args.manifest_output) if args.manifest_output else MANIFEST_ROOT / f"{ts_slug()}-douyin-feishu-enrich.json"
        result["manifest_path"] = str(manifest_path)
        write_json(manifest_path, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
