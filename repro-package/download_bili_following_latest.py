import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "feishu-base-config.json"
DOWNLOAD_ROOT = ROOT / "downloads"
VIDEOS_ROOT = DOWNLOAD_ROOT / "videos"
MANIFEST_ROOT = DOWNLOAD_ROOT / "manifests"
ARCHIVE_PATH = DOWNLOAD_ROOT / "download-archive.txt"
BILIBILI_DOWNLOAD_SCRIPT = Path(r"%USERPROFILE%\.agents\skills\bilibili-download\scripts\download_bilibili.py")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ts_slug():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def add_phase_seconds(manifest, phase, seconds):
    timings = manifest.setdefault("timings", {})
    phases = timings.setdefault("phase_seconds", {})
    phases[phase] = round(float(phases.get(phase) or 0) + float(seconds), 3)


def set_total_seconds(manifest, started_perf):
    timings = manifest.setdefault("timings", {})
    timings["total_seconds"] = round(time.perf_counter() - started_perf, 3)


def safe_json_from_stdout(stdout):
    decoder = json.JSONDecoder()
    start = stdout.find("{")
    if start < 0:
        raise RuntimeError(f"command did not return JSON: {stdout[:500]}")
    obj, _ = decoder.raw_decode(stdout[start:])
    return obj


def command_env():
    env = os.environ.copy()
    env.pop("HERMES_HOME", None)
    env.pop("HERMES_GIT_BASH_PATH", None)
    env["LARK_CLI_NO_PROXY"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def normalize_command(args):
    if not args:
        return args
    executable = shutil.which(args[0]) or args[0]
    suffix = Path(executable).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        return ["cmd", "/c", executable, *args[1:]]
    return [executable, *args[1:]]


def run_command(args, *, timeout=None, check=True):
    result = subprocess.run(
        normalize_command(args),
        cwd=ROOT,
        env=command_env(),
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


def run_lark(config, base_args, *, timeout=60):
    args = ["lark-cli", "--profile", config["profile"], "base", *base_args, "--format", "json"]
    result = run_command(args, timeout=timeout)
    data = safe_json_from_stdout(result.stdout)
    if not data.get("ok"):
        raise RuntimeError(f"lark-cli returned not ok: {json.dumps(data, ensure_ascii=False)[:2000]}")
    return data


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dirs():
    VIDEOS_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)
    ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE_PATH.touch(exist_ok=True)


def field_names(config, table_id):
    data = run_lark(
        config,
        [
            "+field-list",
            "--as",
            "user",
            "--base-token",
            config["base_token"],
            "--table-id",
            table_id,
        ],
    )
    return {field["name"]: field for field in data["data"]["fields"]}


def ensure_video_fields(config):
    table_id = config["tables"]["videos"]["table_id"]
    existing = field_names(config, table_id)
    missing = []
    wanted = {
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
        "视频文件路径": {"type": "text", "name": "视频文件路径"},
        "元数据文件路径": {"type": "text", "name": "元数据文件路径"},
        "视频文案路径": {"type": "text", "name": "视频文案路径"},
        "封面文件路径": {"type": "text", "name": "封面文件路径"},
        "评论文件路径": {"type": "text", "name": "评论文件路径"},
        "已抓评论数": {
            "type": "number",
            "name": "已抓评论数",
            "style": {
                "type": "plain",
                "precision": 0,
                "percentage": False,
                "thousands_separator": True,
            },
        },
        "视频下载状态": {
            "type": "select",
            "name": "视频下载状态",
            "multiple": False,
            "options": [
                {"name": "未下载", "hue": "Blue"},
                {"name": "已下载", "hue": "Green"},
                {"name": "失败", "hue": "Orange"},
                {"name": "跳过", "hue": "Purple"},
            ],
        },
        "评论抓取状态": {
            "type": "select",
            "name": "评论抓取状态",
            "multiple": False,
            "options": [
                {"name": "未抓取", "hue": "Blue"},
                {"name": "已抓取", "hue": "Green"},
                {"name": "失败", "hue": "Orange"},
                {"name": "跳过", "hue": "Purple"},
            ],
        },
    }
    for name, spec in wanted.items():
        if name in existing:
            continue
        run_lark(
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
        print(f"Added video fields: {', '.join(missing)}")


def list_records(config, table_id, fields):
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
        data = run_lark(config, args)
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


def load_creators(config, max_creators=None):
    table_id = config["tables"]["creators"]["table_id"]
    rows = list_records(
        config,
        table_id,
        ["博主名称", "B站MID", "主页链接", "是否持续跟踪"],
    )
    creators = []
    for row in rows:
        if row.get("是否持续跟踪") is not True:
            continue
        mid = str(row.get("B站MID") or "").strip()
        url = str(row.get("主页链接") or "").strip()
        name = str(row.get("博主名称") or "").strip()
        if not mid:
            match = re.search(r"space\.bilibili\.com/(\d+)", url)
            mid = match.group(1) if match else ""
        if not mid:
            print(f"Skip creator without MID: {name}")
            continue
        creators.append(
            {
                "name": name,
                "mid": mid,
                "space_url": f"https://space.bilibili.com/{mid}/video",
                "record_id": row["_record_id"],
            }
        )
    if max_creators:
        creators = creators[:max_creators]
    return creators


def existing_bvids(config):
    table_id = config["tables"]["videos"]["table_id"]
    rows = list_records(config, table_id, ["BVID"])
    return {str(row.get("BVID") or "").strip() for row in rows if row.get("BVID")}


def ytdlp_json_lines(args, timeout=60):
    result = run_command(args, timeout=timeout)
    entries = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        entries.append(json.loads(line))
    return entries, result.stderr


def fetch_latest_entries_from_search(creator, per_creator):
    js = r"""
const { chromium } = require('playwright');
const creator = process.argv[1];
const limit = Number(process.argv[2] || '3');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
  });
  const url = 'https://search.bilibili.com/all?keyword=' + encodeURIComponent(creator) + '&order=pubdate';
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(3500);
  const rows = await page.evaluate(({ creator, limit }) => {
    const out = [];
    const seen = new Set();
    for (const a of document.querySelectorAll('a[href*="/video/BV"]')) {
      const match = a.href.match(/\/video\/(BV[0-9A-Za-z]{10})/);
      if (!match || seen.has(match[1])) continue;
      const title = (a.textContent || '').trim();
      if (!title || /^稍后再看/.test(title)) continue;
      const card = a.closest('.video-list-item, .bili-video-card, .video-item, .video.matrix');
      const cardText = card ? (card.innerText || card.textContent || '').trim() : '';
      if (!cardText.includes(creator)) continue;
      seen.add(match[1]);
      out.push({ bvid: match[1], url: `https://www.bilibili.com/video/${match[1]}/`, title });
      if (out.length >= limit) break;
    }
    return out;
  }, { creator, limit });
  await browser.close();
  console.log(JSON.stringify(rows));
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
"""
    result = run_command(["node", "-e", js, creator["name"], str(per_creator)], timeout=90, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout)[-2000:])
    rows = json.loads(result.stdout.strip() or "[]")
    if not rows:
        raise RuntimeError(f"Bilibili search fallback returned no videos for {creator['name']}")
    return rows[:per_creator], result.stderr


def fetch_latest_entries(creator, per_creator):
    base_args = [
        "yt-dlp",
        "--no-update",
        "--flat-playlist",
        "--playlist-items",
        f"1:{per_creator}",
        "--dump-json",
    ]
    try:
        entries, stderr = ytdlp_json_lines([*base_args, creator["space_url"]], timeout=90)
    except Exception as exc:
        print("  list fallback: yt-dlp space listing failed, trying Bilibili search page")
        videos, search_stderr = fetch_latest_entries_from_search(creator, per_creator)
        warning = str(exc)[-1000:]
        if search_stderr.strip():
            warning = f"{warning}\n{search_stderr.strip()[-1000:]}"
        return videos, warning
    videos = []
    for entry in entries:
        bvid = entry.get("id") or entry.get("webpage_url_basename")
        url = entry.get("url") or entry.get("webpage_url")
        if not bvid:
            continue
        videos.append({"bvid": bvid, "url": url or f"https://www.bilibili.com/video/{bvid}"})
    return videos, stderr


def find_downloaded_files(out_dir, bvid):
    info_path = out_dir / f"{bvid}.info.json"
    media_candidates = []
    for path in out_dir.rglob("*"):
        if path.name.endswith(".info.json") or path.suffix.lower() in {".json", ".part", ".ytdl"}:
            continue
        if path.is_file() and path.suffix.lower() in {".mp4", ".m4a", ".webm", ".mkv", ".flv", ".m4s"}:
            media_candidates.append(path)
    media_candidates.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
    media_path = media_candidates[0] if media_candidates else None
    return media_path, info_path if info_path.exists() else None


def flatten_skill_output(out_dir, output_folder):
    source = Path(output_folder)
    if not source.exists() or source.resolve() == out_dir.resolve():
        return
    for child in source.iterdir():
        target = out_dir / child.name
        if target.exists():
            if target.is_dir() and child.is_dir():
                for nested in child.iterdir():
                    nested_target = target / nested.name
                    if nested_target.exists():
                        continue
                    shutil.move(str(nested), str(nested_target))
                continue
            continue
        shutil.move(str(child), str(target))
    try:
        source.rmdir()
    except OSError:
        pass


def write_compatible_info(out_dir, bvid, manifest):
    metadata_path = out_dir / "metadata.json"
    if not metadata_path.exists():
        metadata_path = next(out_dir.rglob("metadata.json"), None)
    info_path = out_dir / f"{bvid}.info.json"
    if not metadata_path or not metadata_path.exists():
        return info_path if info_path.exists() else None
    with metadata_path.open("r", encoding="utf-8") as f:
        metadata = json.load(f)
    raw_data = ((metadata.get("raw") or {}).get("data") or {}) if isinstance(metadata.get("raw"), dict) else {}
    info = dict(metadata)
    info.setdefault("id", metadata.get("id") or raw_data.get("bvid") or bvid)
    info.setdefault("display_id", bvid)
    info.setdefault("title", metadata.get("title") or raw_data.get("title") or bvid)
    info.setdefault("fulltitle", info["title"])
    info.setdefault("aid", raw_data.get("aid") or metadata.get("aid"))
    info.setdefault("aid_str", str(info.get("aid") or ""))
    info.setdefault("webpage_url", metadata.get("webpage_url") or f"https://www.bilibili.com/video/{bvid}")
    info.setdefault("duration", metadata.get("duration") or raw_data.get("duration"))
    if raw_data.get("pubdate") and not info.get("timestamp"):
        info["timestamp"] = raw_data["pubdate"]
    with info_path.open("w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return info_path


def metadata_from_view_payload(bvid, view_payload):
    data = view_payload.get("data") or {}
    return {
        "extractor": "bilibili-api-prefilter",
        "id": data.get("bvid") or bvid,
        "display_id": data.get("bvid") or bvid,
        "title": data.get("title") or bvid,
        "fulltitle": data.get("title") or bvid,
        "aid": data.get("aid"),
        "aid_str": str(data.get("aid") or ""),
        "duration": data.get("duration"),
        "timestamp": data.get("pubdate"),
        "thumbnail": data.get("pic"),
        "webpage_url": f"https://www.bilibili.com/video/{data.get('bvid') or bvid}",
        "uploader": (data.get("owner") or {}).get("name"),
        "entries": [
            {
                "id": data.get("bvid") or bvid,
                "title": page.get("part") or data.get("title"),
                "duration": page.get("duration"),
                "page": page.get("page"),
                "cid": page.get("cid"),
            }
            for page in data.get("pages") or []
        ],
        "raw": view_payload,
    }


def fetch_video_metadata(video):
    bvid = video["bvid"]
    query = urllib.parse.urlencode({"bvid": bvid})
    referer = video.get("url") or f"https://www.bilibili.com/video/{bvid}/"
    payload = api_get_json(f"https://api.bilibili.com/x/web-interface/view?{query}", referer=referer)
    if payload.get("code") != 0:
        raise RuntimeError(f"Bilibili view API failed: {payload.get('code')} {payload.get('message')}")
    if not isinstance(payload.get("data"), dict):
        raise RuntimeError("Bilibili view API returned no data")
    return payload


def write_lightweight_info(video, creator, view_payload):
    bvid = video["bvid"]
    out_dir = VIDEOS_ROOT / creator["mid"] / bvid
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = out_dir / "metadata.json"
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata_from_view_payload(bvid, view_payload), f, ensure_ascii=False, indent=2)
    info_path = write_compatible_info(out_dir, bvid, {})
    if not info_path:
        raise RuntimeError(f"could not write lightweight info for {bvid}")
    return info_path


def pages_count_from_view_payload(view_payload):
    data = view_payload.get("data") or {}
    return len(data.get("pages") or [])


def ytdlp_download_args(video, out_dir, bvid, *, use_cookies, browser="chrome"):
    args = [
        "yt-dlp",
        "--no-update",
        "--no-playlist",
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "--write-info-json",
        "--download-archive",
        str(ARCHIVE_PATH),
        "-o",
        str(out_dir / f"{bvid}.%(ext)s"),
    ]
    if use_cookies:
        args.extend(["--cookies-from-browser", browser])
    args.append(video["url"])
    return args


def download_video(video, creator, retries=1, use_cookies=True, browser="chrome"):
    bvid = video["bvid"]
    out_dir = VIDEOS_ROOT / creator["mid"] / bvid
    out_dir.mkdir(parents=True, exist_ok=True)
    existing_media, existing_info = find_downloaded_files(out_dir, bvid)
    if existing_media and existing_info:
        return existing_media, existing_info, "", "Reused existing local download."
    last_error = ""

    # Try bilibili-download script first if available
    if BILIBILI_DOWNLOAD_SCRIPT.exists():
        args = [
            sys.executable,
            str(BILIBILI_DOWNLOAD_SCRIPT),
            video["url"],
            "--out-dir",
            str(out_dir),
        ]
        fallback_note = "Downloaded with bilibili-download skill backend."
        for attempt in range(retries + 1):
            result = run_command(args, timeout=60 * 60 * 2, check=False)
            if result.returncode == 0:
                try:
                    skill_manifest = safe_json_from_stdout(result.stdout)
                except Exception:
                    skill_manifest = {}
                output_folder = skill_manifest.get("output_folder")
                if output_folder:
                    flatten_skill_output(out_dir, output_folder)
                info_path = write_compatible_info(out_dir, bvid, skill_manifest)
                media_path, found_info = find_downloaded_files(out_dir, bvid)
                info_path = info_path or found_info
                if media_path and info_path:
                    return media_path, info_path, result.stderr, fallback_note
                last_error = f"download command succeeded but expected files were not found in {out_dir}"
            else:
                last_error = (result.stderr or result.stdout)[-2000:]
            if attempt < retries:
                time.sleep(3)
        # If bilibili-download fails, fall through to yt-dlp
        print(f"  bilibili-download failed, trying yt-dlp fallback...")

    # Fallback: use yt-dlp directly
    print(f"  Downloading with yt-dlp...")
    # Try with cookies first, then fall back to no cookies
    cookie_modes = [use_cookies, False] if use_cookies else [False]
    for with_cookies in cookie_modes:
        if not with_cookies and use_cookies:
            print(f"  Cookie access failed, retrying without cookies...")
        args = ytdlp_download_args(video, out_dir, bvid, use_cookies=with_cookies, browser=browser)
        for attempt in range(retries + 1):
            result = run_command(args, timeout=60 * 60 * 2, check=False)
            if result.returncode == 0:
                media_path, info_path = find_downloaded_files(out_dir, bvid)
                if media_path and info_path:
                    cookie_note = "with cookies" if with_cookies else "without cookies"
                    return media_path, info_path, result.stderr, f"Downloaded with yt-dlp ({cookie_note})."
                last_error = f"yt-dlp succeeded but expected files were not found in {out_dir}"
            else:
                last_error = (result.stderr or result.stdout)[-2000:]
            if attempt < retries:
                time.sleep(3)
        # If cookie mode failed with cookie-related error, try without cookies
        if with_cookies and ("cookie" in last_error.lower() or "Could not copy" in last_error):
            continue
        break
    raise RuntimeError(last_error)


def read_info(info_path):
    with info_path.open("r", encoding="utf-8") as f:
        info = json.load(f)
    timestamp = info.get("timestamp")
    upload_date = info.get("upload_date")
    published = None
    if timestamp:
        published = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    elif upload_date and re.fullmatch(r"\d{8}", str(upload_date)):
        published = datetime.strptime(upload_date, "%Y%m%d").strftime("%Y-%m-%d 00:00:00")
    return {
        "title": info.get("title") or info.get("fulltitle") or info_path.stem.replace(".info", ""),
        "bvid": info.get("id") or info.get("display_id") or info_path.parent.name,
        "aid": str(info.get("aid") or info.get("aid_str") or ""),
        "webpage_url": info.get("webpage_url") or f"https://www.bilibili.com/video/{info_path.parent.name}",
        "published": published,
        "duration": int(info["duration"]) if isinstance(info.get("duration"), (int, float)) else None,
    }


def raw_data_from_info(info):
    raw = info.get("raw") if isinstance(info, dict) else {}
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        return raw["data"]
    return {}


def video_description_text(info, raw_data):
    desc = raw_data.get("desc")
    if desc:
        return str(desc)
    desc_v2 = raw_data.get("desc_v2")
    if isinstance(desc_v2, list):
        parts = []
        for item in desc_v2:
            if not isinstance(item, dict):
                continue
            text = item.get("raw_text") or item.get("text") or item.get("biz_id")
            if text:
                parts.append(str(text))
        if parts:
            return "\n".join(parts)
    return str(info.get("description") or raw_data.get("dynamic") or "")


def find_cover_file(out_dir):
    covers = [path for path in out_dir.rglob("cover.*") if path.is_file()]
    covers.sort(key=lambda path: path.stat().st_size if path.exists() else 0, reverse=True)
    return covers[0] if covers else None


def to_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def metric_snapshot_from_info(info):
    raw_data = raw_data_from_info(info)
    stat = raw_data.get("stat") if isinstance(raw_data.get("stat"), dict) else {}
    if not stat:
        return None
    return {
        "播放量": to_int(stat.get("view")),
        "点赞量": to_int(stat.get("like")),
        "投币数": to_int(stat.get("coin")),
        "收藏数": to_int(stat.get("favorite")),
        "分享数": to_int(stat.get("share")),
        "评论数": to_int(stat.get("reply")),
        "弹幕数": to_int(stat.get("danmaku")),
        "粉丝数快照": None,
        "备注": "source=metadata.raw.data.stat",
        "_raw_stat": stat,
    }


def api_get_json(url, *, referer, timeout=30):
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
    }
    request = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(urllib.request.getproxies()))
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
    return json.loads(payload.decode("utf-8", errors="replace"))


def normalize_reply(reply):
    member = reply.get("member") or {}
    content = reply.get("content") or {}
    return {
        "rpid": reply.get("rpid"),
        "mid": reply.get("mid") or member.get("mid"),
        "uname": member.get("uname"),
        "message": content.get("message"),
        "like": to_int(reply.get("like")),
        "ctime": datetime.fromtimestamp(reply["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(reply.get("ctime"), (int, float))
        else None,
        "replies_count": to_int(reply.get("rcount")),
        "replies": [normalize_reply(child) for child in (reply.get("replies") or [])],
    }


def fetch_comments(aid, bvid, limit):
    if not aid:
        raise RuntimeError("AID is missing, cannot fetch comments")
    comments = []
    pages = []
    total_count = None
    page_no = 1
    page_size = max(1, min(20, int(limit or 20)))
    referer = f"https://www.bilibili.com/video/{bvid}/"
    while len(comments) < limit:
        query = urllib.parse.urlencode(
            {
                "type": 1,
                "oid": aid,
                "sort": 2,
                "pn": page_no,
                "ps": page_size,
            }
        )
        payload = api_get_json(f"https://api.bilibili.com/x/v2/reply?{query}", referer=referer)
        pages.append(
            {
                "pn": page_no,
                "code": payload.get("code"),
                "message": payload.get("message"),
                "ttl": payload.get("ttl"),
            }
        )
        if payload.get("code") != 0:
            raise RuntimeError(f"Bilibili reply API failed: {payload.get('code')} {payload.get('message')}")
        data = payload.get("data") or {}
        page = data.get("page") or {}
        if total_count is None:
            total_count = to_int(page.get("count") or page.get("acount"))
        replies = data.get("replies") or []
        for reply in replies:
            comments.append(normalize_reply(reply))
            if len(comments) >= limit:
                break
        if len(replies) < page_size:
            break
        page_no += 1
        time.sleep(0.5)
    return {
        "pages": pages,
        "total_count": total_count,
        "fetched_count": len(comments[:limit]),
        "partial": bool(total_count is not None and len(comments[:limit]) < min(limit, total_count)),
        "comments": comments[:limit],
    }


def collect_video_artifacts(info_path, bvid, *, comment_limit, skip_comments):
    with info_path.open("r", encoding="utf-8") as f:
        info = json.load(f)
    raw_data = raw_data_from_info(info)
    out_dir = info_path.parent
    comment_seconds = 0.0

    description_path = out_dir / "video-description.txt"
    description_path.write_text(video_description_text(info, raw_data), encoding="utf-8")

    cover_path = find_cover_file(out_dir)

    metrics = metric_snapshot_from_info(info)
    metrics_path = out_dir / "metrics-snapshot.json"
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "captured_at": now_str(),
                "bvid": bvid,
                "aid": info.get("aid") or raw_data.get("aid"),
                "metrics": {k: v for k, v in (metrics or {}).items() if not k.startswith("_")},
                "raw_stat": (metrics or {}).get("_raw_stat"),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    comments_path = out_dir / "comments.json"
    comment_status = "跳过" if skip_comments or comment_limit <= 0 else "未抓取"
    comment_count = 0
    comment_error = ""
    if not skip_comments and comment_limit > 0:
        comment_started = time.perf_counter()
        try:
            comments_payload = fetch_comments(info.get("aid") or raw_data.get("aid"), bvid, comment_limit)
            comment_count = len(comments_payload["comments"])
            comment_status = "已抓取"
            payload = {
                "ok": True,
                "fetched_at": now_str(),
                "bvid": bvid,
                "aid": info.get("aid") or raw_data.get("aid"),
                "limit": comment_limit,
                **comments_payload,
            }
        except Exception as exc:
            comment_status = "失败"
            comment_error = str(exc)[-1000:]
            payload = {
                "ok": False,
                "fetched_at": now_str(),
                "bvid": bvid,
                "aid": info.get("aid") or raw_data.get("aid"),
                "limit": comment_limit,
                "error": comment_error,
                "comments": [],
            }
        with comments_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        comment_seconds += time.perf_counter() - comment_started

    return {
        "description_path": description_path,
        "cover_path": cover_path,
        "metrics_path": metrics_path,
        "metrics": metrics,
        "comments_path": comments_path if comments_path.exists() else None,
        "comment_status": comment_status,
        "comment_count": comment_count,
        "comment_error": comment_error,
        "comment_seconds": round(comment_seconds, 3),
    }


def date_part(value):
    return str(value or "").split(" ", 1)[0] if value else None


def write_manifest(path, manifest):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def batch_create_video_records(config, rows):
    if not rows:
        return []
    table_id = config["tables"]["videos"]["table_id"]
    fields = [
        "视频标题",
        "平台",
        "平台视频ID",
        "BVID",
        "AID",
        "视频链接",
        "关联博主",
        "发布时间",
        "时长秒",
        "视频文件路径",
        "元数据文件路径",
        "视频文案路径",
        "封面文件路径",
        "评论文件路径",
        "评论抓取状态",
        "已抓评论数",
        "视频下载状态",
        "音频状态",
        "转写状态",
        "最近采集时间",
    ]
    created_ids = []
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    for start in range(0, len(rows), 200):
        payload = {"fields": fields, "rows": rows[start : start + 200]}
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as f:
            json.dump(payload, f, ensure_ascii=False)
            payload_path = Path(f.name)
        try:
            data = run_lark(
                config,
                [
                    "+record-batch-create",
                    "--as",
                    "user",
                    "--base-token",
                    config["base_token"],
                    "--table-id",
                    table_id,
                    "--json",
                    f"@{payload_path.relative_to(ROOT)}",
                ],
                timeout=120,
            )
        finally:
            payload_path.unlink(missing_ok=True)
        created_ids.extend(data["data"].get("record_id_list", []))
    return created_ids


def batch_create_metric_snapshots(config, items):
    if not items:
        return []
    table_id = config["tables"]["video_metric_snapshots"]["table_id"]
    fields = [
        "关联视频",
        "快照时间",
        "播放量",
        "点赞量",
        "投币数",
        "收藏数",
        "分享数",
        "评论数",
        "弹幕数",
        "粉丝数快照",
        "备注",
    ]
    rows = []
    for item in items:
        metrics = item.get("metrics") or {}
        if not metrics:
            continue
        rows.append(
            [
                [{"id": item["video_record_id"]}],
                item.get("snapshot_time") or now_str(),
                metrics.get("播放量"),
                metrics.get("点赞量"),
                metrics.get("投币数"),
                metrics.get("收藏数"),
                metrics.get("分享数"),
                metrics.get("评论数"),
                metrics.get("弹幕数"),
                metrics.get("粉丝数快照"),
                f"BVID={item.get('bvid')}; {metrics.get('备注') or ''}; local={item.get('metrics_path')}",
            ]
        )
    if not rows:
        return []
    created_ids = []
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    for start in range(0, len(rows), 200):
        payload = {"fields": fields, "rows": rows[start : start + 200]}
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as f:
            json.dump(payload, f, ensure_ascii=False)
            payload_path = Path(f.name)
        try:
            data = run_lark(
                config,
                [
                    "+record-batch-create",
                    "--as",
                    "user",
                    "--base-token",
                    config["base_token"],
                    "--table-id",
                    table_id,
                    "--json",
                    f"@{payload_path.relative_to(ROOT)}",
                ],
                timeout=120,
            )
        finally:
            payload_path.unlink(missing_ok=True)
        created_ids.extend(data["data"].get("record_id_list", []))
    return created_ids


def update_video_record(config, record_id, patch):
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as f:
        json.dump(patch, f, ensure_ascii=False)
        payload_path = Path(f.name)
    try:
        return run_lark(
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


def create_task_log(
    config,
    started_at,
    ended_at,
    success_count,
    failure_count,
    manifest_path,
    summary,
    *,
    task_name="下载关注博主最新三条视频",
    task_type="视频列表采集",
    target_scope="飞书博主表：持续跟踪博主，每个最新3条",
):
    table_id = config["tables"]["crawl_task_logs"]["table_id"]
    payload = {
        "fields": [
            "任务名称",
            "开始时间",
            "结束时间",
            "任务类型",
            "状态",
            "目标范围",
            "成功数量",
            "失败数量",
            "错误摘要",
            "日志文件路径",
        ],
        "rows": [
            [
                task_name,
                started_at,
                ended_at,
                task_type,
                "成功" if failure_count == 0 else "部分失败",
                target_scope,
                success_count,
                failure_count,
                summary[:1000] if summary else "",
                str(manifest_path),
            ]
        ],
    }
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as f:
        json.dump(payload, f, ensure_ascii=False)
        payload_path = Path(f.name)
    try:
        run_lark(
            config,
            [
                "+record-batch-create",
                "--as",
                "user",
                "--base-token",
                config["base_token"],
                "--table-id",
                table_id,
                "--json",
                f"@{payload_path.relative_to(ROOT)}",
            ],
            timeout=60,
        )
    finally:
        payload_path.unlink(missing_ok=True)


def enrich_existing_videos(config, manifest, *, comment_limit, skip_comments, max_existing_videos=None):
    table_id = config["tables"]["videos"]["table_id"]
    rows = list_records(
        config,
        table_id,
        [
            "视频标题",
            "BVID",
            "视频文件路径",
            "元数据文件路径",
            "视频文案路径",
            "封面文件路径",
            "评论文件路径",
            "评论抓取状态",
            "已抓评论数",
            "指标快照",
        ],
    )
    snapshot_items = []
    processed = 0
    for row in rows:
        if max_existing_videos is not None and processed >= max_existing_videos:
            break
        bvid = str(row.get("BVID") or "").strip()
        info_raw = str(row.get("元数据文件路径") or "").strip()
        if not bvid or not info_raw:
            continue
        info_path = Path(info_raw)
        if not info_path.exists():
            failure = {
                "stage": "enrich_existing",
                "bvid": bvid,
                "record_id": row["_record_id"],
                "error": f"metadata file not found: {info_path}",
            }
            manifest["failures"].append(failure)
            continue
        try:
            artifacts = collect_video_artifacts(
                info_path,
                bvid,
                comment_limit=max(0, comment_limit),
                skip_comments=skip_comments,
            )
            patch = {
                "视频文案路径": str(artifacts["description_path"]) if artifacts.get("description_path") else None,
                "封面文件路径": str(artifacts["cover_path"]) if artifacts.get("cover_path") else None,
                "评论文件路径": str(artifacts["comments_path"]) if artifacts.get("comments_path") else None,
                "评论抓取状态": artifacts["comment_status"],
                "已抓评论数": artifacts["comment_count"],
                "最近采集时间": now_str(),
            }
            update_video_record(config, row["_record_id"], patch)
            item = {
                "bvid": bvid,
                "record_id": row["_record_id"],
                "title": row.get("视频标题"),
                "description_path": patch["视频文案路径"],
                "cover_path": patch["封面文件路径"],
                "comments_path": patch["评论文件路径"],
                "comment_status": patch["评论抓取状态"],
                "comment_count": patch["已抓评论数"],
                "metrics_path": str(artifacts["metrics_path"]) if artifacts.get("metrics_path") else None,
                "existing_metric_snapshot_count": len(row.get("指标快照") or []),
            }
            if artifacts.get("comment_error"):
                item["comment_error"] = artifacts["comment_error"]
            manifest["enriched_existing"].append(item)
            if artifacts.get("metrics") and not row.get("指标快照"):
                snapshot_items.append(
                    {
                        "video_record_id": row["_record_id"],
                        "bvid": bvid,
                        "metrics": artifacts["metrics"],
                        "metrics_path": artifacts.get("metrics_path"),
                        "snapshot_time": now_str(),
                    }
                )
            processed += 1
            write_manifest(Path(manifest["manifest_path"]), manifest)
            print(f"  enriched: {bvid} comments={item['comment_status']}:{item['comment_count']}")
        except Exception as exc:
            failure = {
                "stage": "enrich_existing",
                "bvid": bvid,
                "record_id": row["_record_id"],
                "error": str(exc)[-2000:],
            }
            manifest["failures"].append(failure)
            write_manifest(Path(manifest["manifest_path"]), manifest)
            print(f"  enrich failed: {bvid} {str(exc).splitlines()[-1] if str(exc).splitlines() else exc}")
    created_snapshot_ids = batch_create_metric_snapshots(config, snapshot_items)
    manifest["created_snapshot_record_ids"] = created_snapshot_ids
    return processed


def precheck(config):
    version_commands = {
        "yt-dlp": ["yt-dlp", "--version"],
        "ffmpeg": ["ffmpeg", "-version"],
        "lark-cli": ["lark-cli", "--version"],
    }
    for exe, command in version_commands.items():
        result = run_command(command, timeout=20, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"{exe} is not available")
    # Try auth status; if not supported (externally provided credentials), verify by listing tables
    auth = run_command(
        ["lark-cli", "--profile", config["profile"], "auth", "status", "--verify"],
        timeout=30,
        check=False,
    )
    if auth.returncode != 0:
        # Externally provided credentials — verify by making a simple API call
        verify = run_command(
            ["lark-cli", "--profile", config["profile"], "base", "+table-list", "--base-token", config["base_token"], "--as", "user"],
            timeout=30,
            check=False,
        )
        if verify.returncode != 0:
            raise RuntimeError("lark-cli user identity is not ready (failed to verify via base API)")
    elif '"user"' not in auth.stdout or '"status": "ready"' not in auth.stdout:
        raise RuntimeError("lark-cli user identity is not ready")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--videos-per-creator", type=int, default=3)
    parser.add_argument("--max-creators", type=int, default=None)
    parser.add_argument("--max-total-videos", type=int, default=None)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--comment-limit", type=int, default=50, help="Max top-level comments to fetch per new video.")
    parser.add_argument("--skip-comments", action="store_true", help="Do not fetch Bilibili comment content.")
    parser.add_argument("--enrich-existing", action="store_true", help="Backfill local artifacts and metric snapshots for existing video rows.")
    parser.add_argument("--max-existing-videos", type=int, default=None, help="Limit --enrich-existing processing.")
    parser.add_argument("--browser", default="chrome", choices=["chrome", "edge"], help="Browser to use for cookies (default: chrome).")
    parser.add_argument(
        "--only-today",
        action="store_true",
        help="Only write videos whose metadata publish date is today; older new BVIDs are skipped after metadata is read.",
    )
    parser.add_argument(
        "--published-date",
        default=None,
        help="Date used with --only-today, in YYYY-MM-DD. Defaults to today's local date.",
    )
    args = parser.parse_args()

    run_started_perf = time.perf_counter()
    started_at = now_str()
    target_date = args.published_date or datetime.now().strftime("%Y-%m-%d")
    ensure_dirs()
    config = load_config()
    manifest_path = MANIFEST_ROOT / f"{ts_slug()}-bili-latest-download.json"
    manifest = {
        "started_at": started_at,
        "base_url": config["base_url"],
        "videos_per_creator": args.videos_per_creator,
        "creators": [],
        "successes": [],
        "skipped_existing": [],
        "skipped_not_today": [],
        "failures": [],
        "created_record_ids": [],
        "created_snapshot_record_ids": [],
        "only_today": args.only_today,
        "target_date": target_date if args.only_today else None,
        "comment_limit": 0 if args.skip_comments else args.comment_limit,
        "manifest_path": str(manifest_path),
        "enriched_existing": [],
        "timings": {
            "phase_seconds": {
                "precheck": 0.0,
                "list": 0.0,
                "metadata": 0.0,
                "download": 0.0,
                "artifacts": 0.0,
                "comments": 0.0,
                "feishu_write": 0.0,
            }
        },
    }
    write_manifest(manifest_path, manifest)

    precheck_started = time.perf_counter()
    precheck(config)
    ensure_video_fields(config)
    add_phase_seconds(manifest, "precheck", time.perf_counter() - precheck_started)
    if args.enrich_existing:
        print("Enriching existing Feishu video records from local metadata.")
        processed = enrich_existing_videos(
            config,
            manifest,
            comment_limit=args.comment_limit,
            skip_comments=args.skip_comments,
            max_existing_videos=args.max_existing_videos,
        )
        manifest["ended_at"] = now_str()
        manifest["summary"] = {
            "enriched_existing": len(manifest["enriched_existing"]),
            "failed": len(manifest["failures"]),
            "updated_video_records": processed,
            "created_metric_snapshots": len(manifest.get("created_snapshot_record_ids") or []),
        }
        set_total_seconds(manifest, run_started_perf)
        write_manifest(manifest_path, manifest)
        failures_summary = "; ".join(
            f"{f.get('bvid', '')}: {f.get('stage')}" for f in manifest["failures"][:10]
        )
        create_task_log(
            config,
            started_at,
            manifest["ended_at"],
            len(manifest["enriched_existing"]),
            len(manifest["failures"]),
            manifest_path,
            failures_summary,
            task_name="补齐已下载视频基础信息",
            task_type="指标快照",
            target_scope="飞书视频表：已有本地元数据的视频记录",
        )
        print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
        print(f"Manifest: {manifest_path}")
        return

    creators = load_creators(config, args.max_creators)
    existing = existing_bvids(config)
    manifest["creator_count"] = len(creators)
    print(f"Loaded {len(creators)} tracked creators, {len(existing)} existing BVIDs in Feishu.")

    rows_to_create = []
    pending_writes = []
    total_seen = 0
    for creator in creators:
        print(f"[creator] {creator['name']} ({creator['mid']})")
        creator_result = {"name": creator["name"], "mid": creator["mid"], "videos": []}
        manifest["creators"].append(creator_result)
        list_started = time.perf_counter()
        try:
            videos, stderr = fetch_latest_entries(creator, args.videos_per_creator)
            if stderr.strip():
                creator_result["list_warnings"] = stderr.strip()[-1000:]
        except Exception as exc:
            failure = {"creator": creator, "stage": "list", "error": str(exc)}
            manifest["failures"].append(failure)
            write_manifest(manifest_path, manifest)
            print(f"  list failed: {exc}")
            continue
        finally:
            add_phase_seconds(manifest, "list", time.perf_counter() - list_started)
        for video in videos:
            if args.max_total_videos and total_seen >= args.max_total_videos:
                break
            total_seen += 1
            bvid = video["bvid"]
            print(f"  [video] {bvid}")
            item = {"bvid": bvid, "url": video["url"]}
            creator_result["videos"].append(item)
            if bvid in existing:
                item["status"] = "skipped_existing"
                manifest["skipped_existing"].append({"creator": creator["name"], "bvid": bvid})
                write_manifest(manifest_path, manifest)
                print("    skipped: already in Feishu")
                continue
            try:
                preflight_info = None
                preflight_payload = None
                if args.only_today:
                    metadata_started = time.perf_counter()
                    try:
                        preflight_payload = fetch_video_metadata(video)
                        info_path = write_lightweight_info(video, creator, preflight_payload)
                        preflight_info = read_info(info_path)
                        item["metadata_info_path"] = str(info_path)
                    except Exception as exc:
                        item["metadata_prefilter_error"] = str(exc)[-1000:]
                        print(f"    metadata prefilter failed, falling back to download: {exc}")
                    finally:
                        add_phase_seconds(manifest, "metadata", time.perf_counter() - metadata_started)

                    if preflight_info and preflight_info.get("published"):
                        if date_part(preflight_info["published"]) != target_date:
                            skip = {
                                "creator": creator["name"],
                                "mid": creator["mid"],
                                "bvid": bvid,
                                "published": preflight_info["published"],
                                "target_date": target_date,
                                "info_path": str(info_path),
                                "metadata_only": True,
                                "pages_count": pages_count_from_view_payload(preflight_payload or {}),
                                "duration": preflight_info.get("duration"),
                            }
                            manifest["skipped_not_today"].append(skip)
                            item.update(skip)
                            item["status"] = "skipped_not_today"
                            write_manifest(manifest_path, manifest)
                            print(f"    skipped before media download: published {preflight_info['published']}, target {target_date}")
                            continue
                    elif preflight_info:
                        item["metadata_prefilter_error"] = "published timestamp missing"
                        print("    metadata prefilter missing publish date, falling back to download")

                if args.skip_download:
                    raise RuntimeError("skip-download was requested")
                download_started = time.perf_counter()
                try:
                    media_path, info_path, stderr, fallback_note = download_video(
                        video, creator, retries=args.retries, browser=args.browser
                    )
                finally:
                    add_phase_seconds(manifest, "download", time.perf_counter() - download_started)
                info = read_info(info_path)
                if args.only_today and date_part(info.get("published")) != target_date:
                    skip = {
                        "creator": creator["name"],
                        "mid": creator["mid"],
                        "bvid": bvid,
                        "published": info.get("published"),
                        "target_date": target_date,
                        "info_path": str(info_path),
                        "metadata_only": False,
                        "media_downloaded_before_skip": True,
                        "duration": info.get("duration"),
                    }
                    manifest["skipped_not_today"].append(skip)
                    item.update(skip)
                    item["status"] = "skipped_not_today"
                    write_manifest(manifest_path, manifest)
                    print(f"    skipped: published {info.get('published') or 'unknown'}, target {target_date}")
                    continue
                artifacts_started = time.perf_counter()
                artifacts = collect_video_artifacts(
                    info_path,
                    bvid,
                    comment_limit=max(0, args.comment_limit),
                    skip_comments=args.skip_comments,
                )
                add_phase_seconds(manifest, "artifacts", time.perf_counter() - artifacts_started)
                add_phase_seconds(manifest, "comments", artifacts.get("comment_seconds") or 0)
                row = [
                    info["title"],
                    "B站",
                    bvid,
                    bvid,
                    info["aid"],
                    info["webpage_url"],
                    [{"id": creator["record_id"]}],
                    info["published"],
                    info["duration"],
                    str(media_path),
                    str(info_path),
                    str(artifacts["description_path"]) if artifacts.get("description_path") else None,
                    str(artifacts["cover_path"]) if artifacts.get("cover_path") else None,
                    str(artifacts["comments_path"]) if artifacts.get("comments_path") else None,
                    artifacts["comment_status"],
                    artifacts["comment_count"],
                    "已下载",
                    "未下载",
                    "未转写",
                    now_str(),
                ]
                rows_to_create.append(row)
                success = {
                    "creator": creator["name"],
                    "mid": creator["mid"],
                    "bvid": bvid,
                    "title": info["title"],
                    "video_path": str(media_path),
                    "info_path": str(info_path),
                    "description_path": str(artifacts["description_path"]) if artifacts.get("description_path") else None,
                    "cover_path": str(artifacts["cover_path"]) if artifacts.get("cover_path") else None,
                    "comments_path": str(artifacts["comments_path"]) if artifacts.get("comments_path") else None,
                    "comment_status": artifacts["comment_status"],
                    "comment_count": artifacts["comment_count"],
                    "metrics_path": str(artifacts["metrics_path"]) if artifacts.get("metrics_path") else None,
                }
                if artifacts.get("comment_error"):
                    success["comment_error"] = artifacts["comment_error"]
                if fallback_note:
                    success["note"] = fallback_note
                manifest["successes"].append(success)
                pending_writes.append(
                    {
                        "success": success,
                        "bvid": bvid,
                        "metrics": artifacts.get("metrics"),
                        "metrics_path": artifacts.get("metrics_path"),
                        "snapshot_time": now_str(),
                    }
                )
                existing.add(bvid)
                item.update(success)
                item["status"] = "downloaded"
                write_manifest(manifest_path, manifest)
                print(f"    downloaded: {media_path.name}")
            except Exception as exc:
                failure = {
                    "creator": creator["name"],
                    "mid": creator["mid"],
                    "bvid": bvid,
                    "url": video["url"],
                    "stage": "download",
                    "error": str(exc)[-2000:],
                }
                manifest["failures"].append(failure)
                item["status"] = "failed"
                item["error"] = failure["error"]
                write_manifest(manifest_path, manifest)
                print(f"    failed: {str(exc).splitlines()[-1] if str(exc).splitlines() else exc}")
        if args.max_total_videos and total_seen >= args.max_total_videos:
            break

    feishu_started = time.perf_counter()
    created_ids = batch_create_video_records(config, rows_to_create)
    manifest["created_record_ids"] = created_ids
    snapshot_items = []
    for item, record_id in zip(pending_writes, created_ids):
        item["success"]["record_id"] = record_id
        if item.get("metrics"):
            snapshot_items.append(
                {
                    "video_record_id": record_id,
                    "bvid": item["bvid"],
                    "metrics": item["metrics"],
                    "metrics_path": item.get("metrics_path"),
                    "snapshot_time": item.get("snapshot_time"),
                }
            )
    if len(created_ids) != len(pending_writes):
        manifest["failures"].append(
            {
                "stage": "video_record_write",
                "error": f"created {len(created_ids)} video records for {len(pending_writes)} pending rows",
            }
        )
    try:
        created_snapshot_ids = batch_create_metric_snapshots(config, snapshot_items)
        manifest["created_snapshot_record_ids"] = created_snapshot_ids
    except Exception as exc:
        manifest["failures"].append({"stage": "metric_snapshot_write", "error": str(exc)[-2000:]})
    manifest["ended_at"] = now_str()
    manifest["summary"] = {
        "downloaded": len(manifest["successes"]),
        "skipped_existing": len(manifest["skipped_existing"]),
        "skipped_not_today": len(manifest["skipped_not_today"]),
        "failed": len(manifest["failures"]),
        "created_video_records": len(created_ids),
        "created_metric_snapshots": len(manifest.get("created_snapshot_record_ids") or []),
    }

    failures_summary = "; ".join(
        f"{f.get('creator')} {f.get('bvid', '')}: {f.get('stage')}" for f in manifest["failures"][:10]
    )
    create_task_log(
        config,
        started_at,
        manifest["ended_at"],
        len(manifest["successes"]),
        len(manifest["failures"]),
        manifest_path,
        failures_summary,
    )
    add_phase_seconds(manifest, "feishu_write", time.perf_counter() - feishu_started)
    set_total_seconds(manifest, run_started_perf)
    write_manifest(manifest_path, manifest)
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise
