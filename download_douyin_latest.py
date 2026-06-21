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
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
DEFAULT_CREATORS_PATH = ROOT / "douyin-creators.json"
DEFAULT_OUT_ROOT = ROOT / "downloads" / "douyin"
MANIFEST_ROOT = ROOT / "downloads" / "manifests"
DOUYIN_DOWNLOAD_SCRIPT = Path(r"%USERPROFILE%\.agents\skills\douyin-download\scripts\dy_yt.py")
BRIDGE_SCRIPT_CANDIDATES = [
    ROOT / ".agents" / "skills" / "douyin-comments" / "scripts" / "douyin_cdp_bridge.mjs",
    Path(r"%USERPROFILE%\.agents\skills\douyin-download\scripts\douyin_cdp_bridge.mjs"),
]
REFERER = "https://www.douyin.com/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
CDP_HOST = "127.0.0.1"
CDP_PORT = 9333
CDP_BRIDGE_URL = os.environ.get("DOUYIN_CDP_BRIDGE_URL", "http://127.0.0.1:3457").rstrip("/")
BRIDGE_TABS = {}
NEXT_BRIDGE_TAB_ID = 1


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ts_slug():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def command_env():
    env = os.environ.copy()
    env.pop("HERMES_HOME", None)
    env.pop("HERMES_GIT_BASH_PATH", None)
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
            f"stdout:\n{result.stdout[-3000:]}\n"
            f"stderr:\n{result.stderr[-3000:]}"
        )
    return result


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8")


def safe_name(value, max_len=80):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or ""))
    value = re.sub(r"\s+", " ", value).strip(" .")
    return (value or "untitled")[:max_len]


def unique_key(base, used):
    key = safe_name(base, max_len=64).lower()
    key = re.sub(r"[^a-z0-9_.-]+", "_", key)
    key = key.strip("._-") or "douyin_creator"
    candidate = key
    counter = 2
    while candidate in used:
        candidate = f"{key}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def resolve_bridge_script():
    for path in BRIDGE_SCRIPT_CANDIDATES:
        if path.exists():
            return path
    raise RuntimeError(
        "Douyin CDP bridge script not found. Checked: "
        + ", ".join(str(path) for path in BRIDGE_SCRIPT_CANDIDATES)
    )


def http_json(url, payload=None, timeout=60):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
            raise RuntimeError(body.get("error") or text) from exc
        except json.JSONDecodeError:
            raise RuntimeError(text or str(exc)) from exc
    body = json.loads(text or "{}")
    if body.get("ok") is False:
        raise RuntimeError(body.get("error") or text)
    return body


def ensure_cdp_bridge():
    try:
        return http_json(f"{CDP_BRIDGE_URL}/health", timeout=3)
    except Exception as first_error:
        script = resolve_bridge_script()
        env = command_env()
        parsed = urlparse(CDP_BRIDGE_URL)
        if parsed.port:
            env["DOUYIN_CDP_BRIDGE_PORT"] = str(parsed.port)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            ["node", str(script)],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        deadline = time.time() + 90
        last_error = first_error
        while time.time() < deadline:
            try:
                return http_json(f"{CDP_BRIDGE_URL}/health", timeout=5)
            except Exception as exc:
                last_error = exc
                time.sleep(1)
        raise RuntimeError(f"Douyin CDP bridge did not become ready at {CDP_BRIDGE_URL}: {last_error}") from last_error


def page_expression(code):
    code = str(code or "").strip()
    if (
        code.startswith("() =>")
        or code.startswith("async () =>")
        or code.startswith("function")
        or code.startswith("async function")
    ):
        return f"({code})()"
    return code


def cdp_run(steps, tab=None, timeout=90):
    global NEXT_BRIDGE_TAB_ID
    ensure_cdp_bridge()
    current = BRIDGE_TABS.get(tab) if tab else None
    tab_alias = tab
    result_steps = []
    for step in steps:
        if "newTab" in step:
            spec = step["newTab"]
            if isinstance(spec, dict):
                url = spec.get("url") or "about:blank"
                background = bool(spec.get("background", False))
            elif spec is True:
                url = "about:blank"
                background = False
            else:
                url = str(spec)
                background = False
            opened = http_json(
                f"{CDP_BRIDGE_URL}/new",
                {"url": url, "background": background},
                timeout=timeout,
            )
            tab_alias = f"t{NEXT_BRIDGE_TAB_ID}"
            NEXT_BRIDGE_TAB_ID += 1
            current = {
                "targetId": opened["targetId"],
                "sessionId": opened["sessionId"],
            }
            BRIDGE_TABS[tab_alias] = current
            result_steps.append({"action": "newTab", "status": "ok", "output": opened})
        elif "goto" in step:
            if not current:
                raise RuntimeError("goto requires an open tab")
            target = step["goto"].get("url") if isinstance(step["goto"], dict) else step["goto"]
            expr = f"(() => {{ const url = {json.dumps(str(target))}; setTimeout(() => {{ window.location.href = url; }}, 0); return url; }})()"
            output = http_json(
                f"{CDP_BRIDGE_URL}/eval",
                {"sessionId": current["sessionId"], "expression": expr, "timeoutMs": timeout * 1000},
                timeout=timeout + 15,
            ).get("value")
            result_steps.append({"action": "goto", "status": "ok", "output": output})
        elif "sleep" in step:
            time.sleep(max(0, float(step["sleep"])) / 1000)
            result_steps.append({"action": "sleep", "status": "ok"})
        elif "pageFunction" in step:
            if not current:
                raise RuntimeError("pageFunction requires an open tab")
            output = http_json(
                f"{CDP_BRIDGE_URL}/eval",
                {
                    "sessionId": current["sessionId"],
                    "expression": page_expression(step["pageFunction"]),
                    "timeoutMs": timeout * 1000,
                },
                timeout=timeout + 15,
            ).get("value")
            result_steps.append({"action": "pageFunction", "status": "ok", "output": output})
        elif "closeTab" in step:
            close_alias = step["closeTab"] if isinstance(step["closeTab"], str) else tab_alias
            target = BRIDGE_TABS.pop(close_alias, None) or current
            if target:
                http_json(f"{CDP_BRIDGE_URL}/close", {"targetId": target["targetId"]}, timeout=timeout)
            result_steps.append({"action": "closeTab", "status": "ok"})
        else:
            raise RuntimeError(f"Unsupported bridge CDP step: {step}")
    return {"status": "ok", "tab": tab_alias, "steps": result_steps}


def new_tab_step(url):
    return {"newTab": {"url": url, "background": False}}


def unwrap_cdp_value(value):
    if not isinstance(value, dict) or "type" not in value:
        return value
    value_type = value.get("type")
    if value_type in {"string", "number", "boolean"}:
        return value.get("value")
    if value_type in {"null", "undefined"}:
        return None
    if value_type == "array":
        return [unwrap_cdp_value(item) for item in value.get("items", [])]
    if value_type == "object":
        return {key: unwrap_cdp_value(item) for key, item in value.get("entries", {}).items()}
    return value.get("value")


def page_function_value(data):
    for step in data.get("steps", []):
        if step.get("action") == "pageFunction":
            return unwrap_cdp_value(step.get("output"))
    return None


def close_cdp_tab(tab):
    if not tab:
        return
    try:
        cdp_run([{"closeTab": tab}], tab=tab, timeout=15)
    except Exception:
        pass


def load_creators(args):
    if args.from_feishu and not args.creator_url:
        return load_feishu_creators(args)

    items = []
    if args.creator_url:
        items.extend({"url": url} for url in args.creator_url)
    else:
        with Path(args.creators).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            payload = payload.get("creators", [])
        if not isinstance(payload, list):
            raise RuntimeError("creator config must be a list or an object with a creators list")
        items.extend(payload)

    used = set()
    creators = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, str):
            item = {"url": item}
        url = str(item.get("url") or "").strip()
        if not url:
            raise RuntimeError(f"creator item #{index} has no url")
        name = str(item.get("name") or item.get("key") or f"douyin_creator_{index}").strip()
        key = item.get("key") or name
        creators.append(
            {
                "key": unique_key(key, used),
                "name": name,
                "url": url,
            }
        )
    return creators


def plain_url(value):
    text = str(value or "").strip()
    match = re.search(r"https?://[^\s)\]]+", text)
    return match.group(0) if match else text


def douyin_user_url(value):
    url = plain_url(value)
    match = re.search(r"https?://(?:www\.)?douyin\.com/user/[^?\s)\]]+", url)
    return match.group(0) if match else ""


def load_feishu_creators(args):
    import download_bili_following_latest as bili

    config = bili.load_config()
    table_id = config["tables"]["creators"]["table_id"]
    available = bili.field_names(config, table_id)
    required = ["博主名称", "抖音主页链接", "抖音SecUID", "抖音持续跟踪"]
    missing = [field for field in required if field not in available]
    if missing:
        raise RuntimeError(
            "Feishu creator table is missing Douyin fields: "
            + ", ".join(missing)
            + ". Run sync_douyin_to_feishu.py once to create the fields, or add them in Feishu."
        )
    fields = [
        "博主名称",
        "B站MID",
        "主页链接",
        "抖音主页链接",
        "抖音SecUID",
        "抖音持续跟踪",
        "平台",
    ]
    rows = bili.list_records(config, table_id, [field for field in fields if field in available])
    used = set()
    creators = []
    for row in rows:
        if row.get("抖音持续跟踪") is not True:
            continue
        if args.skip_bili_linked_creators and str(row.get("B站MID") or "").strip():
            print(f"Skip Douyin creator with Bili MID: {row.get('博主名称') or row['_record_id']}")
            continue
        name = str(row.get("博主名称") or "").strip() or "抖音博主"
        url = douyin_user_url(row.get("抖音主页链接")) or douyin_user_url(row.get("主页链接"))
        sec_uid = str(row.get("抖音SecUID") or "").strip()
        if not url and sec_uid:
            url = f"https://www.douyin.com/user/{sec_uid}"
        if not url:
            print(f"Skip Douyin creator without homepage: {name}")
            continue
        key = unique_key(f"feishu_{row['_record_id']}", used)
        creators.append(
            {
                "key": key,
                "name": name,
                "url": url,
                "record_id": row["_record_id"],
                "sec_uid": sec_uid or extract_sec_uid(url),
                "source": "feishu",
            }
        )
    if args.max_creators:
        creators = creators[: args.max_creators]
    return creators


def extract_sec_uid(url):
    match = re.search(r"/user/([^/?#\s)\]]+)", str(url or ""))
    return match.group(1) if match else ""


def load_existing_feishu_aweme_ids(args):
    if not args.from_feishu or not args.skip_existing_feishu:
        return set()
    import download_bili_following_latest as bili

    config = bili.load_config()
    table_id = config["tables"]["videos"]["table_id"]
    available = bili.field_names(config, table_id)
    fields = [field for field in ["平台", "平台视频ID", "视频链接"] if field in available]
    if not fields:
        return set()
    rows = bili.list_records(config, table_id, fields)
    ids = set()
    for row in rows:
        platform = row.get("平台")
        if isinstance(platform, list):
            is_douyin = "抖音" in platform
        else:
            is_douyin = str(platform or "") == "抖音"
        platform_id = str(row.get("平台视频ID") or "").strip()
        if is_douyin and platform_id:
            ids.add(platform_id)
        link_id = extract_aweme_id(str(row.get("视频链接") or ""))
        if link_id:
            ids.add(link_id)
    return ids


def extract_aweme_id(url):
    match = re.search(r"/video/(\d+)", url or "")
    return match.group(1) if match else ""


def clean_card_title(text):
    lines = []
    for raw in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if line in {"置顶", "Pinned"}:
            continue
        if re.fullmatch(r"[\d.,万wW]+", line):
            continue
        lines.append(line)
    return lines[0] if lines else ""


def select_latest_cards(cards, limit):
    selected = []
    saw_pin_marker = any(card.get("is_pinned") for card in cards)
    for card in cards:
        if card.get("is_pinned"):
            continue
        reason = "first_non_pinned_after_skipping_pinned" if saw_pin_marker else "first_visible_no_pin_marker"
        card = dict(card)
        card["selection_reason"] = reason
        selected.append(card)
        if len(selected) >= limit:
            return selected
    for card in cards[:limit]:
        card = dict(card)
        card["selection_reason"] = "all_visible_candidates_marked_pinned"
        selected.append(card)
    return selected


def fetch_latest_cards(creator, limit):
    tab = None
    try:
        print(f"[parse] {creator['key']} opening Douyin homepage")
        data = cdp_run([new_tab_step("https://www.douyin.com"), {"sleep": 2500}], timeout=90)
        tab = data.get("tab")
        print(f"[parse] {creator['key']} opening creator page")
        cdp_run(
            [
                {"goto": creator["url"]},
                {"sleep": 8000},
                {
                    "pageFunction": """() => {
                        window.scrollTo(0, Math.min(document.body.scrollHeight || 0, 1200));
                        return true;
                    }"""
                },
                {"sleep": 2500},
                {"pageFunction": "() => window.scrollTo(0, 0) || true"},
                {"sleep": 1000},
            ],
            tab=tab,
            timeout=120,
        )
        js_code = """() => {
            const absolutize = (href) => {
                try { return new URL(href, location.href).href.split('?')[0]; }
                catch { return ''; }
            };
            const imgSrc = (root) => {
                const img = root?.querySelector?.('img');
                if (!img) return '';
                return img.currentSrc || img.src || img.getAttribute('data-src') ||
                    img.getAttribute('data-lazy-src') || img.getAttribute('srcset')?.split(/[ ,]/)[0] || '';
            };
            const cardRoot = (a) => {
                let node = a;
                for (let i = 0; i < 7 && node; i++) {
                    const text = (node.innerText || '').trim();
                    if (text.length > 8 && node.querySelectorAll?.('a[href*="/video/"]').length <= 3) return node;
                    node = node.parentElement;
                }
                return a;
            };
            const cards = [];
            const seen = new Set();
            for (const a of document.querySelectorAll('a[href*="/video/"]')) {
                const videoUrl = absolutize(a.href || a.getAttribute('href') || '');
                const match = videoUrl.match(/\\/video\\/(\\d+)/);
                if (!match || seen.has(match[1])) continue;
                seen.add(match[1]);
                const root = cardRoot(a);
                const text = (root?.innerText || a.innerText || a.getAttribute('aria-label') || '').trim();
                const title = a.getAttribute('title') || a.getAttribute('aria-label') || text.split('\\n').find(Boolean) || document.title || '';
                const rect = a.getBoundingClientRect();
                cards.push({
                    aweme_id: match[1],
                    video_url: videoUrl,
                    title,
                    text,
                    cover_url: imgSrc(root || a),
                    is_pinned: /(^|\\n|\\s)(置顶|Pinned)(\\n|\\s|$)/i.test(text),
                    source: 'anchor',
                    top: Math.round(rect.top + window.scrollY),
                    left: Math.round(rect.left + window.scrollX)
                });
            }
            if (cards.length === 0) {
                const html = document.documentElement.innerHTML;
                const re = /https?:\\\\?\\/?\\\\?\\/www\\.douyin\\.com\\\\?\\/video\\\\?\\/(\\d+)/g;
                let match;
                while ((match = re.exec(html)) && cards.length < 20) {
                    if (seen.has(match[1])) continue;
                    seen.add(match[1]);
                    cards.push({
                        aweme_id: match[1],
                        video_url: `https://www.douyin.com/video/${match[1]}`,
                        title: document.title || '',
                        text: '',
                        cover_url: '',
                        is_pinned: false,
                        source: 'html-regex',
                        top: cards.length,
                        left: 0
                    });
                }
            }
            return {
                page_url: location.href,
                page_title: document.title,
                cards: cards.sort((a, b) => (a.top - b.top) || (a.left - b.left))
            };
        }"""
        data = cdp_run([{"pageFunction": js_code}], tab=tab, timeout=60)
        payload = page_function_value(data) or {}
        cards = payload.get("cards") or []
        cleaned = []
        for rank, card in enumerate(cards, start=1):
            aweme_id = str(card.get("aweme_id") or "")
            if not aweme_id:
                continue
            title = clean_card_title(card.get("title") or card.get("text") or payload.get("page_title"))
            cleaned.append(
                {
                    "rank": rank,
                    "aweme_id": aweme_id,
                    "video_url": card.get("video_url") or f"https://www.douyin.com/video/{aweme_id}",
                    "title": title,
                    "raw_text": card.get("text") or "",
                    "cover_url": card.get("cover_url") or "",
                    "is_pinned": bool(card.get("is_pinned")),
                    "source": card.get("source") or "unknown",
                }
            )
        selected = select_latest_cards(cleaned, limit)
        return {
            "creator": creator,
            "page_url": payload.get("page_url") or creator["url"],
            "page_title": payload.get("page_title") or "",
            "candidates": cleaned,
            "selected": selected,
        }
    finally:
        close_cdp_tab(tab)


def fetch_video_metadata(video_url):
    tab = None
    try:
        data = cdp_run([new_tab_step(video_url), {"sleep": 6500}], timeout=90)
        tab = data.get("tab")
        js_code = """() => {
            const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content || '';
            const prop = (name) => document.querySelector(`meta[property="${name}"]`)?.content || '';
            const text = document.body?.innerText || '';
            const video = document.querySelector('video');
            return {
                page_url: location.href,
                title: prop('og:title') || meta('twitter:title') || document.title || '',
                description: prop('og:description') || meta('description') || '',
                cover_url: prop('og:image') || meta('twitter:image') || '',
                body_excerpt: text.slice(0, 2000),
                video_current_src: video?.currentSrc || video?.src || ''
            };
        }"""
        data = cdp_run([{"pageFunction": js_code}], tab=tab, timeout=60)
        return page_function_value(data) or {}
    finally:
        close_cdp_tab(tab)


def download_url(url, path):
    if not url:
        return False
    try:
        request = urllib.request.Request(url, headers={"Referer": REFERER, "User-Agent": USER_AGENT})
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(request, timeout=60) as response, path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        return path.exists() and path.stat().st_size > 0
    except Exception:
        return False


def download_direct(url, output_path, label):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[download] {label}: {url[:90]}...")
    request = urllib.request.Request(url, headers={"Referer": REFERER, "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response, output_path.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"downloaded empty {label} file: {output_path}")
    return output_path


def merge_streams(video_stream_path, audio_stream_path, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            str(video_stream_path),
            "-i",
            str(audio_stream_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            "-shortest",
            str(output_path),
        ],
        timeout=60 * 10,
    )
    return output_path


def get_media_urls_from_performance(tab):
    cdp_run(
        [
            {
                "pageFunction": """() => {
                    const video = document.querySelector('video');
                    if (!video) return false;
                    video.muted = true;
                    const playPromise = video.play?.();
                    if (playPromise?.catch) playPromise.catch(() => {});
                    return true;
                }"""
            },
            {"sleep": 3500},
        ],
        tab=tab,
        timeout=60,
    )
    js_code = """() => {
        const mediaRe = /media-(video|audio)|mime_type=video_mp4|v\\d+-web\\.douyinvod\\.com/i;
        const urls = [...new Set(
            performance.getEntriesByType('resource')
                .map(entry => entry.name)
                .filter(url => mediaRe.test(url))
        )];
        return urls.map(url => {
            let br = 0;
            try {
                const parsed = new URL(url);
                br = Number(parsed.searchParams.get('br') || parsed.searchParams.get('bt') || 0);
            } catch {}
            const lower = url.toLowerCase();
            const kind = lower.includes('media-audio')
                ? 'audio'
                : lower.includes('media-video')
                    ? 'video'
                    : 'unknown';
            return {url, kind, br};
        });
    }"""
    data = cdp_run([{"pageFunction": js_code}], tab=tab, timeout=60)
    media = page_function_value(data) or []
    media = [item for item in media if isinstance(item, dict) and item.get("url")]
    videos = [item for item in media if item.get("kind") == "video"]
    audios = [item for item in media if item.get("kind") == "audio"]
    best_video = max(videos, key=lambda item: item.get("br") or 0, default=None)
    best_audio = max(audios, key=lambda item: item.get("br") or 0, default=None)
    return best_video, best_audio, media


def extract_video_streams(video_url):
    tab = None
    try:
        data = cdp_run([new_tab_step(video_url), {"sleep": 7000}], timeout=90)
        tab = data.get("tab")
        js_code = """() => {
            const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content || '';
            const prop = (name) => document.querySelector(`meta[property="${name}"]`)?.content || '';
            const video = document.querySelector('video');
            return {
                page_url: location.href,
                title: prop('og:title') || meta('twitter:title') || document.title || '',
                description: prop('og:description') || meta('description') || '',
                cover_url: prop('og:image') || meta('twitter:image') || '',
                video_current_src: video?.currentSrc || video?.src || ''
            };
        }"""
        data = cdp_run([{"pageFunction": js_code}], tab=tab, timeout=60)
        page_meta = page_function_value(data) or {}
        current_src = page_meta.get("video_current_src") or ""
        if current_src and not current_src.startswith("blob:"):
            return {
                "mode": "currentSrc",
                "video_url": current_src,
                "audio_url": None,
                "page_metadata": page_meta,
                "media_resources": [],
            }

        best_video, best_audio, media = get_media_urls_from_performance(tab)
        if not best_video:
            raise RuntimeError(f"found {len(media)} media-like resources, but no media-video URL")
        return {
            "mode": "performance",
            "video_url": best_video["url"],
            "audio_url": (best_audio or {}).get("url"),
            "page_metadata": page_meta,
            "media_resources": media,
        }
    finally:
        close_cdp_tab(tab)


def download_current_src(media_url, output_template):
    result = run_command(
        [
            "yt-dlp",
            "--add-headers",
            f"Referer:{REFERER}",
            "--add-headers",
            f"User-Agent:{USER_AGENT}",
            "-o",
            str(output_template),
            media_url,
        ],
        timeout=60 * 10,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "yt-dlp failed for Douyin currentSrc\n"
            f"exit: {result.returncode}\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-2000:]}"
        )
    return result.stdout + result.stderr


def extract_cover_from_video(video_path, cover_path):
    run_command(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-ss",
            "1",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(cover_path),
        ],
        timeout=120,
    )
    return cover_path.exists() and cover_path.stat().st_size > 0


def find_downloaded_video(video_dir):
    candidates = []
    for path in video_dir.glob("video.*"):
        if path.suffix.lower() in {".mp4", ".m4v", ".mov", ".webm", ".mkv"} and path.stat().st_size > 0:
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_size)


def download_video(video_url, video_dir):
    video_dir.mkdir(parents=True, exist_ok=True)
    stream_info = extract_video_streams(video_url)
    log_text = json.dumps(
        {
            "mode": stream_info["mode"],
            "page_url": stream_info.get("page_metadata", {}).get("page_url"),
            "media_resource_count": len(stream_info.get("media_resources") or []),
        },
        ensure_ascii=False,
    )
    if stream_info["mode"] == "currentSrc":
        download_current_src(stream_info["video_url"], video_dir / "video.%(ext)s")
        video_path = find_downloaded_video(video_dir)
    else:
        final_path = video_dir / "video.mp4"
        with tempfile.TemporaryDirectory(prefix="douyin_streams_") as tmpdir:
            tmpdir = Path(tmpdir)
            video_stream_path = download_direct(stream_info["video_url"], tmpdir / "video.mp4", "video stream")
            audio_url = stream_info.get("audio_url")
            if audio_url:
                audio_stream_path = download_direct(audio_url, tmpdir / "audio.m4a", "audio stream")
                video_path = merge_streams(video_stream_path, audio_stream_path, final_path)
            else:
                shutil.copy2(video_stream_path, final_path)
                video_path = final_path
    if not video_path or not video_path.exists() or video_path.stat().st_size <= 0:
        raise RuntimeError(f"download completed but no usable video file was found in {video_dir}")
    if video_path.name != "video.mp4" and video_path.suffix.lower() == ".mp4" and not (video_dir / "video.mp4").exists():
        target = video_dir / "video.mp4"
        video_path.replace(target)
        video_path = target
    return video_path, log_text, stream_info


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


def extract_audio(video_path, audio_path, *, force=False):
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
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
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
    drop_lines = {
        "谢谢观看",
        "感谢观看",
        "字幕由Amara.org社区提供",
        "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目",
    }
    for raw_line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            if lines and not seen_blank:
                lines.append("")
            seen_blank = True
            continue
        seen_blank = False
        if line in drop_lines:
            continue
        if re.fullmatch(r".*(字幕|翻译)\s*(by|BY|By)\s*.*", line):
            continue
        lines.append(line)
    return "\n".join(lines).strip() + ("\n" if lines else "")


def process_transcript(video_path, video_dir, args):
    transcript_dir = video_dir / "transcript"
    audio_path = transcript_dir / "audio_16k.wav"
    asr_dir = transcript_dir / "asr"
    extracted = extract_audio(video_path, audio_path, force=args.force)
    txt_path = transcribe_audio(
        audio_path,
        asr_dir,
        model=args.model,
        language=args.language,
        device=args.device,
        threads=args.threads,
        initial_prompt=args.initial_prompt,
        force=args.force,
    )
    raw_text = txt_path.read_text(encoding="utf-8", errors="replace")
    clean_text = normalize_transcript(raw_text)
    raw_path = transcript_dir / "speech-raw.txt"
    clean_path = transcript_dir / "speech-clean.txt"
    write_text(raw_path, raw_text)
    write_text(clean_path, clean_text)
    return {
        "audio_path": str(audio_path),
        "audio_extracted": extracted,
        "asr_dir": str(asr_dir),
        "speech_raw_path": str(raw_path),
        "speech_clean_path": str(clean_path),
        "speech_chars": len(re.sub(r"\s+", "", clean_text)),
    }


def build_description(selected, page_meta):
    pieces = []
    title = page_meta.get("title") or selected.get("title") or ""
    description = page_meta.get("description") or ""
    if title:
        pieces.append(f"Title: {title}")
    if description and description != title:
        pieces.append(f"Description: {description}")
    raw_text = selected.get("raw_text") or ""
    if raw_text and raw_text not in "\n".join(pieces):
        pieces.append(f"Card text:\n{raw_text}")
    return "\n\n".join(pieces).strip() + ("\n" if pieces else "")


def process_selected_video(creator, selected, out_root, args):
    aweme_id = selected["aweme_id"]
    video_dir = out_root / creator["key"] / aweme_id
    video_dir.mkdir(parents=True, exist_ok=True)
    started_at = now_str()
    page_meta = fetch_video_metadata(selected["video_url"])
    if page_meta.get("title") and not selected.get("title"):
        selected["title"] = clean_card_title(page_meta["title"])
    if page_meta.get("cover_url") and not selected.get("cover_url"):
        selected["cover_url"] = page_meta["cover_url"]

    video_path, download_log, stream_info = download_video(selected["video_url"], video_dir)
    if stream_info.get("page_metadata"):
        page_meta = {**stream_info["page_metadata"], **{k: v for k, v in page_meta.items() if v}}
    cover_path = video_dir / "cover.jpg"
    cover_downloaded = download_url(selected.get("cover_url") or page_meta.get("cover_url"), cover_path)
    if not cover_downloaded:
        extract_cover_from_video(video_path, cover_path)

    description_text = build_description(selected, page_meta)
    description_path = video_dir / "video-description.txt"
    write_text(description_path, description_text)

    duration = ffprobe_duration(video_path)
    transcript = None
    if args.transcribe:
        transcript = process_transcript(video_path, video_dir, args)

    metadata = {
        "platform": "douyin",
        "fetched_at": now_str(),
        "creator": creator,
        "aweme_id": aweme_id,
        "video_url": selected["video_url"],
        "selection_reason": selected.get("selection_reason"),
        "selected_card": selected,
        "page_metadata": page_meta,
        "stream_info": {
            "mode": stream_info.get("mode"),
            "media_resource_count": len(stream_info.get("media_resources") or []),
        },
        "duration_seconds": duration,
        "files": {
            "video_path": str(video_path),
            "description_path": str(description_path),
            "cover_path": str(cover_path) if cover_path.exists() else None,
            "transcript": transcript,
        },
    }
    metadata_path = video_dir / "metadata.json"
    write_json(metadata_path, metadata)

    manifest = {
        "ok": True,
        "started_at": started_at,
        "ended_at": now_str(),
        "creator": creator,
        "aweme_id": aweme_id,
        "video_url": selected["video_url"],
        "video_dir": str(video_dir),
        "video_path": str(video_path),
        "metadata_path": str(metadata_path),
        "description_path": str(description_path),
        "cover_path": str(cover_path) if cover_path.exists() else None,
        "transcript": transcript,
        "download_log_tail": download_log[-3000:],
    }
    manifest_path = video_dir / "manifest.json"
    write_json(manifest_path, manifest)
    return manifest


def parse_args():
    parser = argparse.ArgumentParser(description="Download latest videos from isolated Douyin creators.")
    parser.add_argument("--creators", default=str(DEFAULT_CREATORS_PATH), help="Path to douyin creators JSON.")
    parser.add_argument("--creator-url", action="append", help="Douyin creator homepage URL. Can be repeated.")
    parser.add_argument("--from-feishu", action="store_true", help="Load Douyin creators from Feishu 博主 table.")
    parser.add_argument("--max-creators", type=int, default=None)
    parser.add_argument(
        "--skip-bili-linked-creators",
        action="store_true",
        help="With --from-feishu, skip Douyin rows that also have B站MID.",
    )
    parser.add_argument("--videos-per-creator", type=int, default=1)
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--dry-run", action="store_true", help="Only parse latest video URLs; do not download.")
    parser.add_argument(
        "--skip-existing-feishu",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When --from-feishu is used, skip aweme IDs already present in Feishu 视频 table.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--transcribe", action="store_true", help="Run Whisper after download.")
    group.add_argument("--skip-transcribe", action="store_true", help="Do not run Whisper.")
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--initial-prompt", default="")
    parser.add_argument("--force", action="store_true", help="Regenerate audio/transcript even if present.")
    parser.add_argument("--bridge-url", default=CDP_BRIDGE_URL, help="Persistent local Douyin CDP bridge URL.")
    parser.add_argument("--cdp-host", default="127.0.0.1", help="Legacy option kept for compatibility; bridge mode ignores it.")
    parser.add_argument("--cdp-port", type=int, default=9333, help="Legacy option kept for compatibility; bridge mode ignores it.")
    return parser.parse_args()


def main():
    args = parse_args()
    global CDP_HOST, CDP_PORT, CDP_BRIDGE_URL
    CDP_HOST = args.cdp_host
    CDP_PORT = args.cdp_port
    CDP_BRIDGE_URL = args.bridge_url.rstrip("/")
    if args.videos_per_creator < 1:
        raise RuntimeError("--videos-per-creator must be >= 1")
    args.transcribe = bool(args.transcribe and not args.skip_transcribe)

    creators = load_creators(args)
    existing_aweme_ids = load_existing_feishu_aweme_ids(args)
    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        out_root = ROOT / out_root
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)
    out_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "platform": "douyin",
        "started_at": now_str(),
        "dry_run": args.dry_run,
        "transcribe": args.transcribe,
        "out_root": str(out_root),
        "creators": creators,
        "successes": [],
        "would_download": [],
        "skipped_existing": [],
        "failures": [],
        "parsed": [],
        "summary": {},
    }

    for creator in creators:
        try:
            parsed = fetch_latest_cards(creator, args.videos_per_creator)
            manifest["parsed"].append(parsed)
            selected = parsed.get("selected") or []
            print(f"[parse] {creator['key']} candidates={len(parsed.get('candidates') or [])} selected={len(selected)}")
            if not selected:
                raise RuntimeError("no selectable Douyin videos found on creator homepage")
            if args.dry_run:
                for item in selected:
                    if item["aweme_id"] in existing_aweme_ids:
                        status = "skipped_existing"
                        manifest["skipped_existing"].append(
                            {
                                "creator": creator,
                                "aweme_id": item["aweme_id"],
                                "video_url": item["video_url"],
                                "reason": "already_in_feishu",
                                "dry_run": True,
                            }
                        )
                    else:
                        status = "would_download"
                        manifest["would_download"].append(
                            {
                                "creator": creator,
                                "aweme_id": item["aweme_id"],
                                "video_url": item["video_url"],
                                "dry_run": True,
                            }
                        )
                    print(f"[dry-run] {creator['key']} {item['aweme_id']} {item['video_url']} {status}")
                continue
            for item in selected:
                if item["aweme_id"] in existing_aweme_ids:
                    skipped = {
                        "creator": creator,
                        "aweme_id": item["aweme_id"],
                        "video_url": item["video_url"],
                        "reason": "already_in_feishu",
                    }
                    manifest["skipped_existing"].append(skipped)
                    print(f"[skip] {creator['key']} {item['aweme_id']} already in Feishu")
                    continue
                print(f"[download] {creator['key']} {item['aweme_id']}")
                success = process_selected_video(creator, item, out_root, args)
                manifest["successes"].append(success)
                existing_aweme_ids.add(item["aweme_id"])
                print(f"[done] {creator['key']} {item['aweme_id']} -> {success['video_path']}")
        except Exception as exc:
            failure = {
                "creator": creator,
                "error": str(exc)[-3000:],
                "time": now_str(),
            }
            manifest["failures"].append(failure)
            print(f"[failed] {creator['key']}: {exc}")

    manifest["ended_at"] = now_str()
    manifest["summary"] = {
        "creators": len(creators),
        "downloaded": len(manifest["successes"]),
        "would_download": len(manifest["would_download"]),
        "skipped_existing": len(manifest["skipped_existing"]),
        "failed": len(manifest["failures"]),
        "dry_run": args.dry_run,
        "transcribe": args.transcribe,
    }
    manifest_path = MANIFEST_ROOT / f"{ts_slug()}-douyin-latest-download.json"
    write_json(manifest_path, manifest)
    print(json.dumps({"manifest": str(manifest_path), "summary": manifest["summary"]}, ensure_ascii=False, indent=2))
    if manifest["failures"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
