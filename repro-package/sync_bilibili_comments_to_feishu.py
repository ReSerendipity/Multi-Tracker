import argparse
import json
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import download_bili_following_latest as base
import postprocess_bili_videos as postprocess


ROOT = Path(__file__).resolve().parent
COMMENTS_ROOT = ROOT / "downloads" / "comments"
MANIFEST_ROOT = ROOT / "downloads" / "manifests"
COMMENTS_SKILL_SCRIPT = ROOT / ".agents" / "skills" / "bilibili-comments" / "scripts" / "fetch_comments.mjs"
COMMENTS_TABLE_NAME = "视频评论"
COMMENTS_TABLE_CONFIG_KEY = "video_comments"
CONTENT_VIEW_NAME = "内容选题视图"

COMMENT_TABLE_FIELDS = [
    {"type": "text", "name": "评论ID", "description": "Bilibili rpid，作为业务去重键。"},
    {
        "type": "link",
        "name": "关联视频",
        "link_table": "tblqopduciJ1pCyr",
        "bidirectional": True,
        "bidirectional_link_field_name": "评论明细",
    },
    {"type": "text", "name": "BVID"},
    {"type": "number", "name": "评论层级", "style": {"type": "plain", "precision": 0}},
    {"type": "text", "name": "父评论ID"},
    {"type": "text", "name": "根评论ID"},
    {"type": "text", "name": "评论内容"},
    {"type": "text", "name": "用户昵称"},
    {"type": "text", "name": "用户ID"},
    {"type": "text", "name": "用户性别"},
    {"type": "text", "name": "用户签名"},
    {"type": "text", "name": "头像链接", "style": {"type": "url"}},
    {"type": "number", "name": "点赞数", "style": {"type": "plain", "precision": 0, "thousands_separator": True}},
    {"type": "number", "name": "回复数", "style": {"type": "plain", "precision": 0, "thousands_separator": True}},
    {"type": "datetime", "name": "评论时间", "style": {"format": "yyyy-MM-dd HH:mm"}},
    {"type": "datetime", "name": "采集时间", "style": {"format": "yyyy-MM-dd HH:mm"}},
    {"type": "checkbox", "name": "是否高价值"},
    {
        "type": "select",
        "name": "评论标签",
        "multiple": True,
        "options": [
            {"name": "痛点", "hue": "Red"},
            {"name": "争议", "hue": "Orange"},
            {"name": "求教程", "hue": "Blue"},
            {"name": "补充信息", "hue": "Green"},
            {"name": "赞同观点", "hue": "Lime"},
            {"name": "反对观点", "hue": "Carmine"},
            {"name": "选题线索", "hue": "Purple"},
            {"name": "无效", "hue": "Gray"},
        ],
    },
    {"type": "text", "name": "评论洞察备注"},
]

VIDEO_INSIGHT_FIELDS = {
    "高赞评论摘要": {"type": "text", "name": "高赞评论摘要"},
    "用户痛点": {"type": "text", "name": "用户痛点"},
    "评论里的争议点": {"type": "text", "name": "评论里的争议点"},
    "可延展选题": {"type": "text", "name": "可延展选题"},
    "代表评论": {"type": "text", "name": "代表评论"},
    "评论采集时间": {"type": "datetime", "name": "评论采集时间", "style": {"format": "yyyy-MM-dd HH:mm"}},
    "评论明细入表数": {"type": "number", "name": "评论明细入表数", "style": {"type": "plain", "precision": 0}},
    "评论存储策略": {"type": "text", "name": "评论存储策略"},
}

CONTENT_VIEW_VISIBLE_FIELDS = [
    "视频标题",
    "内容摘要",
    "关键要点",
    "高赞评论摘要",
    "用户痛点",
    "评论里的争议点",
    "可延展选题",
    "代表评论",
    "视频链接",
    "关联博主",
    "发布时间",
    "已抓评论数",
    "评论采集时间",
    "评论抓取状态",
    "BVID",
]

PAIN_KEYWORDS = [
    "怎么",
    "如何",
    "哪里",
    "求",
    "有没有",
    "能不能",
    "教程",
    "链接",
    "下载",
    "报错",
    "安装",
    "不会",
    "怎么办",
    "?",
    "？",
]
CONTROVERSY_KEYWORDS = [
    "不是",
    "但是",
    "然而",
    "错",
    "假",
    "离谱",
    "质疑",
    "反对",
    "不对",
    "没用",
    "问题",
    "争议",
]
JUNK_PATTERNS = ["已赞", "置顶", "哈哈哈", "666", "第一", "来了"]


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


def truncate(value, limit):
    value = str(value or "").replace("\r", " ").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def epoch_to_datetime(value):
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return None


def run_lark_with_temp_json(config, args, payload, timeout=60):
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False)
        payload_path = Path(handle.name)
    try:
        return base.run_lark(config, [*args, "--json", f"@{payload_path.relative_to(ROOT)}"], timeout=timeout)
    finally:
        payload_path.unlink(missing_ok=True)


def table_id_by_name(config, name):
    data = base.run_lark(
        config,
        ["+table-list", "--as", "user", "--base-token", config["base_token"]],
    )
    for table in data["data"]["tables"]:
        if table["name"] == name:
            return table["id"]
    return None


def save_table_to_config(config, table_id):
    tables = config.setdefault("tables", {})
    current = tables.get(COMMENTS_TABLE_CONFIG_KEY) or {}
    if current.get("table_id") == table_id and current.get("name") == COMMENTS_TABLE_NAME:
        return
    tables[COMMENTS_TABLE_CONFIG_KEY] = {"name": COMMENTS_TABLE_NAME, "table_id": table_id}
    write_json(base.CONFIG_PATH, config)


def ensure_comment_table(config):
    video_table_id = config["tables"]["videos"]["table_id"]
    fields = []
    for spec in COMMENT_TABLE_FIELDS:
        spec = dict(spec)
        if spec.get("name") == "关联视频":
            spec["link_table"] = video_table_id
        fields.append(spec)

    table_id = (config.get("tables", {}).get(COMMENTS_TABLE_CONFIG_KEY) or {}).get("table_id")
    if table_id:
        try:
            base.field_names(config, table_id)
            return table_id
        except Exception:
            table_id = None

    table_id = table_id_by_name(config, COMMENTS_TABLE_NAME)
    if not table_id:
        data = base.run_lark(
            config,
            [
                "+table-create",
                "--as",
                "user",
                "--base-token",
                config["base_token"],
                "--name",
                COMMENTS_TABLE_NAME,
                "--fields",
                json.dumps(fields, ensure_ascii=False),
            ],
            timeout=120,
        )
        table_id = data["data"]["table"]["id"]
    save_table_to_config(config, table_id)
    ensure_fields(config, table_id, fields)
    return table_id


def ensure_fields(config, table_id, specs):
    existing = base.field_names(config, table_id)
    for spec in specs:
        if spec["name"] in existing:
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
            timeout=60,
        )


def ensure_video_insight_fields(config):
    video_table_id = config["tables"]["videos"]["table_id"]
    ensure_fields(config, video_table_id, VIDEO_INSIGHT_FIELDS.values())


def update_content_view(config):
    video_table_id = config["tables"]["videos"]["table_id"]
    data = base.run_lark(
        config,
        ["+view-list", "--as", "user", "--base-token", config["base_token"], "--table-id", video_table_id],
    )
    view_id = None
    for view in data["data"]["views"]:
        if view["name"] == CONTENT_VIEW_NAME:
            view_id = view["id"]
            break
    if not view_id:
        return None
    payload = {"visible_fields": CONTENT_VIEW_VISIBLE_FIELDS}
    try:
        base.run_lark(
            config,
            [
                "+view-set-visible-fields",
                "--as",
                "user",
                "--base-token",
                config["base_token"],
                "--table-id",
                video_table_id,
                "--view-id",
                view_id,
                "--json",
                json.dumps(payload, ensure_ascii=False),
            ],
            timeout=60,
        )
    except RuntimeError as exc:
        if "no operation produced" not in str(exc):
            raise
    return view_id


def list_filtered_records(config, table_id, fields, filter_json=None):
    rows = []
    offset = 0
    while True:
        args = [
            "+record-list",
            "--as",
            "user",
            "--base-token",
            config["base_token"],
            "--table-id",
            table_id,
            "--limit",
            "200",
            "--offset",
            str(offset),
        ]
        for field in fields:
            args.extend(["--field-id", field])
        if filter_json:
            args.extend(["--filter-json", json.dumps(filter_json, ensure_ascii=False)])
        data = base.run_lark(config, args, timeout=60)
        payload = data["data"]
        names = payload["fields"]
        for record_id, values in zip(payload["record_id_list"], payload["data"]):
            row = dict(zip(names, values))
            row["_record_id"] = record_id
            rows.append(row)
        if not payload.get("has_more"):
            break
        offset += 200
    return rows


def list_existing_comment_ids(config, table_id, bvid=None):
    fields = ["评论ID"]
    filter_json = None
    if bvid:
        fields.append("BVID")
        filter_json = {"logic": "and", "conditions": [["BVID", "==", bvid]]}
    rows = list_filtered_records(config, table_id, fields, filter_json=filter_json)
    ids = set()
    for row in rows:
        if bvid and str(row.get("BVID") or "").strip() != bvid:
            continue
        comment_id = str(row.get("评论ID") or "").strip()
        if comment_id:
            ids.add(comment_id)
    return ids


def list_existing_comment_keys(config, table_id, bvid=None):
    fields = ["评论ID", "评论内容"]
    filter_json = None
    if bvid:
        fields.append("BVID")
        filter_json = {"logic": "and", "conditions": [["BVID", "==", bvid]]}
    rows = list_filtered_records(config, table_id, fields, filter_json=filter_json)
    ids = set()
    text_keys = set()
    for row in rows:
        if bvid and str(row.get("BVID") or "").strip() != bvid:
            continue
        comment_id = str(row.get("评论ID") or "").strip()
        if comment_id:
            ids.add(comment_id)
        text_key = normalize_comment_text(row.get("评论内容"))
        if text_key:
            text_keys.add(text_key)
    return ids, text_keys


def select_has(value, option):
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                text = item.get("text") or item.get("name") or item.get("value")
            else:
                text = item
            if str(text or "").strip() == option:
                return True
        return False
    return option in str(value or "")


def load_video_rows(config, bvid=None, limit=None, offset=0, only_failed=False, bvids=None):
    rows = base.list_records(
        config,
        config["tables"]["videos"]["table_id"],
        ["视频标题", "BVID", "视频链接", "评论抓取状态", "已抓评论数"],
    )
    out = []
    for row in rows:
        row_bvid = str(row.get("BVID") or "").strip()
        if not row_bvid:
            continue
        if bvid and row_bvid != bvid:
            continue
        if bvids is not None and row_bvid not in bvids:
            continue
        if only_failed and not select_has(row.get("评论抓取状态"), "失败"):
            continue
        out.append(row)
    if bvid:
        return out
    if offset:
        out = out[offset:]
    if limit is not None:
        out = out[:limit]
    return out


def fetch_comments(
    video,
    output_path,
    *,
    max_root=None,
    no_replies=False,
    delay_ms=500,
    reply_delay_ms=300,
    api_retries=2,
    retry_delay_ms=15000,
    stop_after_412=3,
):
    if not COMMENTS_SKILL_SCRIPT.exists():
        raise RuntimeError(f"comments skill script not found: {COMMENTS_SKILL_SCRIPT}")
    args = [
        "node",
        str(COMMENTS_SKILL_SCRIPT),
        "--video",
        video,
        "--output",
        str(output_path),
        "--delay-ms",
        str(delay_ms),
        "--reply-delay-ms",
        str(reply_delay_ms),
        "--api-retries",
        str(api_retries),
        "--retry-delay-ms",
        str(retry_delay_ms),
        "--stop-after-412",
        str(stop_after_412),
    ]
    if max_root:
        args.extend(["--max-root", str(max_root)])
    if no_replies:
        args.append("--no-replies")
    result = subprocess.run(
        base.normalize_command(args),
        cwd=ROOT,
        env=base.command_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60 * 60 * 4,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout)[-2000:])
    stats = base.safe_json_from_stdout(result.stdout)
    stats["stderr"] = result.stderr
    return stats


def fetch_comments_batch(
    jobs,
    *,
    max_root=None,
    no_replies=False,
    delay_ms=500,
    reply_delay_ms=300,
    api_retries=2,
    retry_delay_ms=15000,
    stop_after_412=3,
):
    if not COMMENTS_SKILL_SCRIPT.exists():
        raise RuntimeError(f"comments skill script not found: {COMMENTS_SKILL_SCRIPT}")
    batch_dir = COMMENTS_ROOT / f"batch-{ts_slug()}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    videos_file = batch_dir / "videos.json"
    write_json(videos_file, jobs)
    args = [
        "node",
        str(COMMENTS_SKILL_SCRIPT),
        "--videos-file",
        str(videos_file),
        "--output-dir",
        str(batch_dir),
        "--delay-ms",
        str(delay_ms),
        "--reply-delay-ms",
        str(reply_delay_ms),
        "--api-retries",
        str(api_retries),
        "--retry-delay-ms",
        str(retry_delay_ms),
        "--stop-after-412",
        str(stop_after_412),
    ]
    if max_root:
        args.extend(["--max-root", str(max_root)])
    if no_replies:
        args.append("--no-replies")
    result = subprocess.run(
        base.normalize_command(args),
        cwd=ROOT,
        env=base.command_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60 * 60 * 4,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout)[-2000:])
    stats = base.safe_json_from_stdout(result.stdout)
    stats["stderr"] = result.stderr
    stats["batch_dir"] = str(batch_dir)
    stats["videos_file"] = str(videos_file)
    return stats


def read_jsonl(path):
    items = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def comment_score(comment):
    return int(comment.get("like_count") or 0) + int(comment.get("sub_comment_count") or 0) * 2


def is_junk(content):
    text = str(content or "").strip()
    if len(text) < 4:
        return True
    return any(text == pattern for pattern in JUNK_PATTERNS)


def normalize_comment_text(comment_or_text):
    if isinstance(comment_or_text, dict):
        text = comment_or_text.get("content")
    else:
        text = comment_or_text
    return "".join(str(text or "").strip().lower().split())


def unique_comments_by_content(comments):
    out = []
    seen = set()
    for comment in comments:
        key = normalize_comment_text(comment)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(comment)
    return out


def has_any(text, keywords):
    lower = str(text or "").lower()
    return any(keyword.lower() in lower for keyword in keywords)


def label_comment(comment):
    content = comment.get("content") or ""
    labels = []
    if has_any(content, PAIN_KEYWORDS):
        labels.append("痛点")
        if "教程" in content or "怎么" in content or "如何" in content:
            labels.append("求教程")
    if has_any(content, CONTROVERSY_KEYWORDS):
        labels.append("争议")
    if comment_score(comment) >= 20 and content and not is_junk(content):
        labels.append("选题线索")
    return list(dict.fromkeys(labels))


def insight_note(comment):
    labels = label_comment(comment)
    if not labels:
        return ""
    return "；".join(labels)


def build_video_insights(comments):
    valid = unique_comments_by_content(
        [c for c in comments if str(c.get("content") or "").strip() and not is_junk(c.get("content"))]
    )
    top = sorted(valid, key=comment_score, reverse=True)[:8]
    pain = [c for c in valid if has_any(c.get("content"), PAIN_KEYWORDS)]
    pain = sorted(pain, key=comment_score, reverse=True)[:6]
    controversy = [c for c in valid if has_any(c.get("content"), CONTROVERSY_KEYWORDS)]
    controversy = sorted(controversy, key=comment_score, reverse=True)[:6]

    def line(c):
        return f"- [{int(c.get('like_count') or 0)}赞] {truncate(c.get('nickname'), 20)}：{truncate(c.get('content'), 120)}"

    root_count = sum(1 for c in comments if int(c.get("level") or 0) == 1)
    reply_count = sum(1 for c in comments if int(c.get("level") or 0) == 2)
    high_summary = [
        f"本次抓取 {len(comments)} 条评论：一级 {root_count} 条，回复 {reply_count} 条。",
    ]
    if top:
        high_summary.append("高赞评论主要是：")
        high_summary.extend(line(c) for c in top[:5])
    else:
        high_summary.append("没有足够有效评论可提炼高赞摘要。")

    topic_lines = []
    if pain:
        topic_lines.append("可做评论答疑/教程：围绕用户反复追问的问题展开。")
        topic_lines.extend(line(c) for c in pain[:3])
    if controversy:
        topic_lines.append("可做争议澄清/对比：把评论里的质疑点逐条回应。")
        topic_lines.extend(line(c) for c in controversy[:3])
    if not topic_lines:
        topic_lines.append("评论中暂未出现明显可延展问题，建议先看高赞代表评论。")

    return {
        "高赞评论摘要": truncate("\n".join(high_summary), 1800),
        "用户痛点": truncate("\n".join(line(c) for c in pain) if pain else "未发现明显用户痛点评论。", 1800),
        "评论里的争议点": truncate(
            "\n".join(line(c) for c in controversy) if controversy else "未发现明显争议评论。",
            1800,
        ),
        "可延展选题": truncate("\n".join(topic_lines), 1800),
        "代表评论": truncate("\n".join(line(c) for c in top[:5]) if top else "有效代表评论不足。", 1800),
    }


def select_representative_comments(comments, limit):
    if limit is None or limit < 0:
        return comments
    if limit == 0:
        return []

    valid = unique_comments_by_content(
        [c for c in comments if str(c.get("content") or "").strip() and not is_junk(c.get("content"))]
    )
    buckets = [
        sorted(valid, key=comment_score, reverse=True),
        sorted([c for c in valid if has_any(c.get("content"), PAIN_KEYWORDS)], key=comment_score, reverse=True),
        sorted([c for c in valid if has_any(c.get("content"), CONTROVERSY_KEYWORDS)], key=comment_score, reverse=True),
        sorted([c for c in valid if int(c.get("level") or 0) == 1], key=comment_score, reverse=True),
    ]

    selected = []
    seen_ids = set()
    seen_text = set()

    def add(comment):
        comment_id = str(comment.get("comment_id") or "")
        text_key = normalize_comment_text(comment)
        if not comment_id or comment_id in seen_ids or not text_key or text_key in seen_text:
            return
        seen_ids.add(comment_id)
        seen_text.add(text_key)
        selected.append(comment)

    per_bucket = max(3, limit // 3)
    for bucket in buckets:
        for comment in bucket[:per_bucket]:
            if len(selected) >= limit:
                return selected
            add(comment)

    for comment in sorted(valid, key=comment_score, reverse=True):
        if len(selected) >= limit:
            break
        add(comment)
    return selected


def comment_to_row(comment, video_record_id, captured_at):
    labels = label_comment(comment)
    return [
        str(comment.get("comment_id") or ""),
        [{"id": video_record_id}],
        str(comment.get("bvid") or ""),
        int(comment.get("level") or 0),
        str(comment.get("parent_comment_id") or "0"),
        str(comment.get("root_comment_id") or ""),
        str(comment.get("content") or ""),
        str(comment.get("nickname") or ""),
        str(comment.get("user_id") or ""),
        str(comment.get("sex") or ""),
        truncate(comment.get("sign"), 500),
        str(comment.get("avatar") or ""),
        int(comment.get("like_count") or 0),
        int(comment.get("sub_comment_count") or 0),
        epoch_to_datetime(comment.get("create_time")),
        captured_at,
        bool(labels and "无效" not in labels and comment_score(comment) >= 20),
        labels,
        insight_note(comment),
    ]


def batch_create_records(config, table_id, fields, rows):
    created = []
    for start in range(0, len(rows), 200):
        chunk = rows[start : start + 200]
        payload = {"fields": fields, "rows": chunk}
        data = run_lark_with_temp_json(
            config,
            [
                "+record-batch-create",
                "--as",
                "user",
                "--base-token",
                config["base_token"],
                "--table-id",
                table_id,
            ],
            payload,
            timeout=120,
        )
        created.extend(data.get("data", {}).get("record_id_list") or [])
        time.sleep(0.4)
    return created


def sync_one_video(config, comments_table_id, row, args):
    bvid = str(row.get("BVID") or "").strip()
    video = str(row.get("视频链接") or "").strip() or bvid
    video_record_id = row["_record_id"]
    out_dir = COMMENTS_ROOT / bvid
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{ts_slug()}-comments.jsonl"
    captured_at = now_str()

    stats = fetch_comments(
        video,
        output_path,
        max_root=args.max_root,
        no_replies=args.no_replies,
        delay_ms=args.delay_ms,
        reply_delay_ms=args.reply_delay_ms,
        api_retries=args.api_retries,
        retry_delay_ms=args.retry_delay_ms,
        stop_after_412=args.stop_after_412,
    )
    return write_comments_for_video(config, comments_table_id, row, output_path, captured_at, args, stats)


def write_comments_for_video(config, comments_table_id, row, output_path, captured_at, args, stats):
    bvid = str(row.get("BVID") or "").strip()
    video_record_id = row["_record_id"]
    comments = read_jsonl(output_path)
    existing_ids, existing_text_keys = list_existing_comment_keys(config, comments_table_id, bvid=bvid)
    comments_for_table = select_representative_comments(comments, args.max_comment_table_rows)
    new_comments = [
        c
        for c in comments_for_table
        if str(c.get("comment_id") or "") not in existing_ids
        and normalize_comment_text(c) not in existing_text_keys
    ]

    fields = [spec["name"] for spec in COMMENT_TABLE_FIELDS]
    rows = [comment_to_row(comment, video_record_id, captured_at) for comment in new_comments]
    created_ids = []
    if rows and not args.dry_run:
        created_ids = batch_create_records(config, comments_table_id, fields, rows)

    insights = build_video_insights(comments)
    patch = {
        **insights,
        "评论文件路径": str(output_path),
        "评论抓取状态": "已抓取",
        "已抓评论数": len(comments),
        "评论采集时间": captured_at,
        "评论明细入表数": len(comments_for_table),
        "评论存储策略": (
            "完整评论保存在本地 JSONL；飞书视频评论表仅保存代表评论。"
            if args.max_comment_table_rows >= 0
            else "完整评论保存在本地 JSONL；飞书视频评论表保存全部评论明细。"
        ),
        "最近采集时间": captured_at,
    }
    if not args.dry_run:
        postprocess.update_video_record(config, video_record_id, patch)
    return {
        "bvid": bvid,
        "video_record_id": video_record_id,
        "output_path": str(output_path),
        "fetched_rows": len(comments),
        "table_candidate_rows": len(comments_for_table),
        "new_rows": len(new_comments),
        "created_records": len(created_ids),
        "stats": {k: v for k, v in stats.items() if k != "stderr"},
    }


def sync_video_batch(config, comments_table_id, rows, args):
    captured_at = now_str()
    jobs = []
    by_bvid = {}
    for row in rows:
        bvid = str(row.get("BVID") or "").strip()
        if not bvid:
            continue
        out_dir = COMMENTS_ROOT / bvid
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{ts_slug()}-comments.jsonl"
        video = str(row.get("视频链接") or "").strip() or bvid
        jobs.append({"video": video, "bvid": bvid, "output": str(output_path)})
        by_bvid[bvid] = {"row": row, "output_path": output_path}
    stats = fetch_comments_batch(
        jobs,
        max_root=args.max_root,
        no_replies=args.no_replies,
        delay_ms=args.delay_ms,
        reply_delay_ms=args.reply_delay_ms,
        api_retries=args.api_retries,
        retry_delay_ms=args.retry_delay_ms,
        stop_after_412=args.stop_after_412,
    )
    results = []
    failures = []
    for item in stats.get("videos") or []:
        bvid = str(item.get("bvid") or "")
        if not bvid:
            try:
                bvid = Path(str(item.get("output") or "")).parent.name
            except Exception:
                bvid = ""
        if not bvid and item.get("video"):
            bvid = str(item["video"]).split("/")[-1].strip()
        job = by_bvid.get(bvid)
        if not job:
            failures.append({"bvid": bvid, "error": f"cannot map batch result: {item}"})
            continue
        if item.get("error"):
            failures.append({"bvid": bvid, "record_id": job["row"].get("_record_id"), "error": item["error"]})
            continue
        try:
            results.append(
                write_comments_for_video(
                    config,
                    comments_table_id,
                    job["row"],
                    job["output_path"],
                    captured_at,
                    args,
                    item,
                )
            )
        except Exception as exc:
            failures.append({"bvid": bvid, "record_id": job["row"].get("_record_id"), "error": str(exc)[-2000:]})
    return results, failures, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bvid", help="Only sync one BVID.")
    parser.add_argument("--download-manifest", help="Only sync BVIDs in this bili-latest-download manifest.")
    parser.add_argument("--latest-download-manifest", action="store_true", help="Only sync BVIDs in the latest bili-latest-download manifest.")
    parser.add_argument("--max-videos", type=int, help="Limit videos processed in this run.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many video rows before applying --max-videos.")
    parser.add_argument("--only-failed", action="store_true", help="Only retry videos whose comment status is 失败.")
    parser.add_argument("--max-root", type=int, help="Limit root comments for smoke tests.")
    parser.add_argument("--no-replies", action="store_true", help="Only fetch first-level comments.")
    parser.add_argument("--delay-ms", type=int, default=500)
    parser.add_argument("--reply-delay-ms", type=int, default=300)
    parser.add_argument("--api-retries", type=int, default=2)
    parser.add_argument("--retry-delay-ms", type=int, default=15000)
    parser.add_argument("--stop-after-412", type=int, default=3)
    parser.add_argument(
        "--max-comment-table-rows",
        type=int,
        default=30,
        help="Max representative comment rows written to the Feishu comments table per video. Use 0 for no detail rows, -1 for all rows. Full JSONL is always kept locally.",
    )
    parser.add_argument("--skip-view-update", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.latest_download_manifest:
        args.download_manifest = str(latest_manifest_path("*-bili-latest-download.json"))
    bvid_filter = bvids_from_download_manifest(args.download_manifest) if args.download_manifest else None

    started_at = now_str()
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = MANIFEST_ROOT / f"{ts_slug()}-bili-comments-sync.json"
    manifest = {
        "started_at": started_at,
        "max_root": args.max_root,
        "no_replies": args.no_replies,
        "max_comment_table_rows": args.max_comment_table_rows,
        "source_download_manifest": args.download_manifest,
        "successes": [],
        "failures": [],
    }
    write_json(manifest_path, manifest)

    config = base.load_config()
    comments_table_id = ensure_comment_table(config)
    config = base.load_config()
    ensure_video_insight_fields(config)
    if not args.skip_view_update:
        manifest["content_view_id"] = update_content_view(config)

    rows = load_video_rows(
        config,
        bvid=args.bvid,
        limit=args.max_videos,
        offset=args.offset,
        only_failed=args.only_failed,
        bvids=bvid_filter,
    )
    if len(rows) > 1:
        print(f"[comments] batch offset={args.offset} count={len(rows)}")
        try:
            results, failures, batch_stats = sync_video_batch(config, comments_table_id, rows, args)
            manifest["batch_stats"] = {k: v for k, v in batch_stats.items() if k != "stderr"}
            for result in results:
                manifest["successes"].append(result)
                print(f"  {result['bvid']}: fetched={result['fetched_rows']} new={result['new_rows']}")
            for failure in failures:
                manifest["failures"].append(failure)
                row = next((candidate for candidate in rows if candidate.get("BVID") == failure.get("bvid")), None)
                if not args.dry_run and row and row.get("_record_id"):
                    try:
                        postprocess.update_video_record(
                            config,
                            row["_record_id"],
                            {"评论抓取状态": "失败", "最近采集时间": now_str()},
                        )
                    except Exception as write_exc:
                        failure["writeback_error"] = str(write_exc)[-1000:]
                print(f"  {failure.get('bvid')}: failed={failure.get('error')}")
        except Exception as exc:
            for row in rows:
                failure = {"bvid": row.get("BVID"), "record_id": row.get("_record_id"), "error": str(exc)[-2000:]}
                manifest["failures"].append(failure)
                print(f"  {row.get('BVID')}: failed={str(exc).splitlines()[-1] if str(exc).splitlines() else exc}")
        rows = []

    for row in rows:
        bvid = str(row.get("BVID") or "").strip()
        print(f"[comments] {bvid} {row.get('视频标题') or ''}")
        try:
            result = sync_one_video(config, comments_table_id, row, args)
            manifest["successes"].append(result)
            print(f"  fetched={result['fetched_rows']} new={result['new_rows']}")
        except Exception as exc:
            failure = {"bvid": bvid, "record_id": row.get("_record_id"), "error": str(exc)[-2000:]}
            manifest["failures"].append(failure)
            if not args.dry_run and row.get("_record_id"):
                try:
                    postprocess.update_video_record(
                        config,
                        row["_record_id"],
                        {
                            "评论抓取状态": "失败",
                            "最近采集时间": now_str(),
                        },
                    )
                except Exception as write_exc:
                    failure["writeback_error"] = str(write_exc)[-1000:]
            print(f"  failed: {str(exc).splitlines()[-1] if str(exc).splitlines() else exc}")
        manifest["ended_at"] = now_str()
        manifest["summary"] = {
            "processed": len(manifest["successes"]),
            "failed": len(manifest["failures"]),
            "fetched_rows": sum(item["fetched_rows"] for item in manifest["successes"]),
            "new_rows": sum(item["new_rows"] for item in manifest["successes"]),
        }
        write_json(manifest_path, manifest)

    manifest["ended_at"] = now_str()
    manifest["summary"] = {
        "processed": len(manifest["successes"]),
        "failed": len(manifest["failures"]),
        "fetched_rows": sum(item["fetched_rows"] for item in manifest["successes"]),
        "new_rows": sum(item["new_rows"] for item in manifest["successes"]),
    }
    write_json(manifest_path, manifest)
    failures_summary = "; ".join(f"{f.get('bvid')}: {f.get('error', '')[:80]}" for f in manifest["failures"][:10])
    if not args.dry_run:
        postprocess.create_task_log_with_retry(
            config,
            started_at,
            manifest["ended_at"],
            len(manifest["successes"]),
            len(manifest["failures"]),
            manifest_path,
            failures_summary,
            task_name="同步 B 站视频评论",
            task_type="评论采集",
            target_scope=f"飞书视频表：{args.bvid or '全部视频'}",
        )
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
