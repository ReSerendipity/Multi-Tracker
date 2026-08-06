import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import websocket


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CDP_HOST = "127.0.0.1"
DEFAULT_CDP_PORT = 9222
DEFAULT_CDP_PROXY_URL = "http://127.0.0.1:3456"


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


class DouyinCommentError(RuntimeError):
    pass


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ts_slug():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def http_json(url, *, method="GET", timeout=10, data=None, headers=None):
    body = None
    if data is not None:
        body = data.encode("utf-8") if isinstance(data, str) else data
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise DouyinCommentError(f"HTTP {exc.code} from {url}: {error_body[:1000]}") from exc


def http_text(url, *, method="GET", timeout=10):
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def devtools_base(host, port):
    return f"http://{host}:{int(port)}"


def ensure_cdp_available(host, port):
    try:
        return http_json(f"{devtools_base(host, port)}/json/version", timeout=5)
    except Exception as exc:
        raise DouyinCommentError(
            f"Chrome DevTools is not reachable at {host}:{port}. "
            "Start Chrome with remote debugging or use the project's existing CDP browser session. "
            f"Original error: {type(exc).__name__}: {exc}"
        ) from exc


def open_target_http(host, port, url):
    encoded = urllib.parse.quote(url, safe="")
    endpoint = f"{devtools_base(host, port)}/json/new?{encoded}"
    try:
        target = http_json(endpoint, method="PUT", timeout=10)
    except Exception:
        target = http_json(endpoint, method="GET", timeout=10)
    ws_url = target.get("webSocketDebuggerUrl")
    target_id = target.get("id")
    if not ws_url or not target_id:
        raise DouyinCommentError(f"DevTools did not return a usable tab target: {target}")
    return target_id, ws_url


def active_port_candidates():
    candidates = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.extend(
            [
                Path(local_app_data) / "Google" / "Chrome" / "User Data" / "DevToolsActivePort",
                Path(local_app_data) / "Chromium" / "User Data" / "DevToolsActivePort",
            ]
        )
    return candidates


def read_devtools_active_port(preferred_port):
    for path in active_port_candidates():
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        except OSError:
            continue
        if not lines:
            continue
        try:
            port = int(lines[0].strip())
        except ValueError:
            continue
        ws_path = lines[1].strip() if len(lines) > 1 else ""
        if preferred_port and port != int(preferred_port):
            continue
        if ws_path:
            return {"port": port, "ws_path": ws_path, "path": str(path)}
    return None


def close_target(host, port, target_id):
    if not target_id:
        return
    try:
        http_text(f"{devtools_base(host, port)}/json/close/{target_id}", timeout=5)
    except Exception:
        pass


def normalize_proxy_url(value):
    text = str(value or "").strip().rstrip("/")
    return text or None


def close_proxy_target(proxy_url, target_id):
    if not proxy_url or not target_id:
        return
    try:
        encoded = urllib.parse.quote(str(target_id), safe="")
        http_json(f"{proxy_url}/close?target={encoded}", timeout=10)
    except Exception:
        pass


class CDPSession:
    def __init__(self, ws_url, timeout=30, session_id=None):
        self.ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        self.next_id = 1
        self.session_id = session_id

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass

    def command(self, method, params=None, timeout=30, use_session=True):
        msg_id = self.next_id
        self.next_id += 1
        self.ws.settimeout(timeout)
        message = {"id": msg_id, "method": method, "params": params or {}}
        if self.session_id and use_session:
            message["sessionId"] = self.session_id
        self.ws.send(json.dumps(message))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") != msg_id:
                continue
            if "error" in message:
                raise DouyinCommentError(f"CDP {method} failed: {message['error']}")
            return message.get("result") or {}

    def evaluate(self, expression, timeout=120):
        result = self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
                "timeout": timeout * 1000,
            },
            timeout=timeout + 5,
        )
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            text = details.get("text") or details.get("exception", {}).get("description") or str(details)
            raise DouyinCommentError(f"Browser evaluation failed: {text}")
        remote = result.get("result") or {}
        if remote.get("type") == "undefined":
            return None
        if "value" in remote:
            return remote.get("value")
        if "description" in remote:
            return remote.get("description")
        return remote


class ProxySession:
    def __init__(self, proxy_url, target_id):
        self.proxy_url = proxy_url
        self.target_id = target_id

    def close(self):
        pass

    def command(self, method, params=None, timeout=30, use_session=True):
        if method == "Runtime.enable":
            return {}
        raise DouyinCommentError(f"CDP proxy session does not support direct command: {method}")

    def evaluate(self, expression, timeout=120):
        encoded = urllib.parse.quote(str(self.target_id), safe="")
        result = http_json(
            f"{self.proxy_url}/eval?target={encoded}",
            method="POST",
            data=expression,
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=timeout + 10,
        )
        if isinstance(result, dict) and result.get("error"):
            raise DouyinCommentError(f"Browser evaluation failed through CDP proxy: {result['error']}")
        if isinstance(result, dict) and "value" in result:
            return result.get("value")
        return result


def open_page_session_proxy(proxy_url, url):
    base = normalize_proxy_url(proxy_url)
    if not base:
        raise DouyinCommentError("CDP proxy URL is empty.")
    try:
        http_json(f"{base}/health", timeout=5)
    except Exception as exc:
        raise DouyinCommentError(f"CDP proxy is not reachable at {base}: {type(exc).__name__}: {exc}") from exc
    encoded = urllib.parse.quote(url, safe="")
    created = http_json(f"{base}/new?url={encoded}", timeout=60)
    target_id = created.get("targetId") if isinstance(created, dict) else None
    if not target_id:
        raise DouyinCommentError(f"CDP proxy did not return targetId: {created}")
    return {
        "mode": "web_access_proxy",
        "target_id": target_id,
        "session": ProxySession(base, target_id),
        "devtools_active_port": None,
        "cdp_proxy_url": base,
    }


def open_page_session(host, port, url, proxy_url=None):
    proxy_error = None
    if normalize_proxy_url(proxy_url):
        try:
            return open_page_session_proxy(proxy_url, url)
        except Exception as exc:
            proxy_error = exc
    try:
        target_id, ws_url = open_target_http(host, port, url)
        session = CDPSession(ws_url, timeout=30)
        return {
            "mode": "target_http",
            "target_id": target_id,
            "session": session,
            "devtools_active_port": None,
        }
    except Exception as http_exc:
        active = read_devtools_active_port(port)
        if not active:
            prefix = ""
            if proxy_error:
                prefix = f"The CDP proxy path also failed: {type(proxy_error).__name__}: {proxy_error}. "
            raise DouyinCommentError(
                f"{prefix}Could not create a Chrome tab through {host}:{port}. "
                "The standard /json/new endpoint failed and no matching DevToolsActivePort file was found. "
                f"Original error: {type(http_exc).__name__}: {http_exc}"
            ) from http_exc
        browser_ws_url = f"ws://{host}:{active['port']}{active['ws_path']}"
        session = CDPSession(browser_ws_url, timeout=30)
        target = session.command("Target.createTarget", {"url": url, "background": True}, timeout=20, use_session=False)
        target_id = target.get("targetId")
        if not target_id:
            raise DouyinCommentError(f"Target.createTarget returned no targetId: {target}")
        attached = session.command(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
            timeout=20,
            use_session=False,
        )
        session_id = attached.get("sessionId")
        if not session_id:
            raise DouyinCommentError(f"Target.attachToTarget returned no sessionId: {attached}")
        session.session_id = session_id
        return {
            "mode": "browser_devtools_active_port",
            "target_id": target_id,
            "session": session,
            "devtools_active_port": active,
        }


def extract_aweme_id(value):
    text = str(value or "")
    match = re.search(r"/video/(\d+)", text)
    if match:
        return match.group(1)
    match = re.fullmatch(r"\d{10,}", text.strip())
    if match:
        return match.group(0)
    return None


def resolve_from_video_dir(video_dir):
    base = Path(video_dir)
    if not base.exists():
        raise DouyinCommentError(f"--video-dir does not exist: {base}")
    data = {}
    for name in ("manifest.json", "metadata.json"):
        path = base / name
        if path.exists():
            payload = load_json(path)
            if isinstance(payload, dict):
                data.update(payload)
    aweme_id = str(data.get("aweme_id") or "").strip() or extract_aweme_id(data.get("video_url"))
    video_url = str(data.get("video_url") or "").strip()
    if aweme_id and not video_url:
        video_url = f"https://www.douyin.com/video/{aweme_id}"
    return aweme_id or None, video_url or None


def resolve_target(args):
    aweme_id = str(args.aweme_id or "").strip() or None
    video_url = str(args.video_url or "").strip() or None
    if args.video_dir:
        dir_aweme, dir_url = resolve_from_video_dir(args.video_dir)
        aweme_id = aweme_id or dir_aweme
        video_url = video_url or dir_url
    aweme_id = aweme_id or extract_aweme_id(video_url)
    if aweme_id and not video_url:
        video_url = f"https://www.douyin.com/video/{aweme_id}"
    if not aweme_id:
        raise DouyinCommentError("Provide --aweme-id, a final Douyin --video-url containing /video/<id>, or --video-dir with manifest.json/metadata.json.")
    return aweme_id, video_url


def resolve_outputs(args, aweme_id):
    if args.out:
        jsonl_path = Path(args.out)
        if not jsonl_path.is_absolute():
            jsonl_path = Path.cwd() / jsonl_path
        out_dir = jsonl_path.parent
    elif args.out_dir:
        out_dir = Path(args.out_dir)
        if not out_dir.is_absolute():
            out_dir = Path.cwd() / out_dir
        jsonl_path = out_dir / "comments.jsonl"
    elif args.video_dir:
        out_dir = Path(args.video_dir) / "comments"
        jsonl_path = out_dir / "comments.jsonl"
    else:
        out_dir = ROOT / "downloads" / "douyin-comments" / aweme_id
        jsonl_path = out_dir / "comments.jsonl"
    return out_dir, jsonl_path, out_dir / "comments.json", out_dir / "comments-manifest.json"


FETCH_SCRIPT = r"""
async function fetchDouyinComments(opts) {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const loginPromptVisible = () => {
    const bodyText = document.body?.innerText || "";
    return /请先登录后发表评论|登录后即可参与互动讨论/.test(bodyText);
  };
  const baseResult = () => ({
    page_url: location.href,
    page_title: document.title || "",
    login_prompt_visible: loginPromptVisible()
  });
  const emptyStats = () => ({
    pages: 0,
    total: null,
    has_more: false,
    next_cursor: 0,
    returned_rows: 0,
    duplicate_skips: 0,
    root_rows: 0,
    reply_rows: 0
  });
  const loginCheckError = () => ({
    stage: "login_check",
    error: "Douyin login prompt is visible; comment API fetch was skipped because login is required."
  });
  if (opts.check_login_only) {
    const promptVisible = loginPromptVisible();
    return {
      ok: !promptVisible,
      ...baseResult(),
      skipped_fetch: true,
      check_login_only: true,
      rows: [],
      stats: emptyStats(),
      page_errors: promptVisible ? [loginCheckError()] : [],
      reply_errors: []
    };
  }
  if (opts.require_login && loginPromptVisible()) {
    return {
      ok: false,
      ...baseResult(),
      skipped_fetch: true,
      check_login_only: false,
      rows: [],
      stats: emptyStats(),
      page_errors: [loginCheckError()],
      reply_errors: []
    };
  }
  const uaVersion = (navigator.userAgent.match(/Chrome\/([0-9.]+)/) || [])[1] || "";
  const common = {
    device_platform: "webapp",
    aid: "6383",
    channel: "channel_pc_web",
    item_type: "0",
    pc_client_type: "1",
    version_code: "190500",
    version_name: "19.5.0",
    cookie_enabled: String(navigator.cookieEnabled),
    screen_width: String(screen.width || 1920),
    screen_height: String(screen.height || 1080),
    browser_language: navigator.language || "zh-CN",
    browser_platform: navigator.platform || "Win32",
    browser_name: "Chrome",
    browser_version: uaVersion,
    browser_online: String(navigator.onLine),
    engine_name: "Blink",
    engine_version: uaVersion,
    os_name: "Windows",
    os_version: "10",
    cpu_core_num: String(navigator.hardwareConcurrency || 8),
    device_memory: String(navigator.deviceMemory || 8),
    platform: "PC",
    downlink: "10",
    effective_type: "4g",
    round_trip_time: "50"
  };
  const makeUrl = (path, params) => {
    const url = new URL(path, location.origin);
    Object.entries({...common, ...params}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
    });
    return url.toString();
  };
  const requestJson = async (path, params) => {
    const url = makeUrl(path, params);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), opts.request_timeout_ms);
    try {
      const response = await fetch(url, {
        credentials: "include",
        signal: controller.signal,
        headers: {accept: "application/json, text/plain, */*"}
      });
      const text = await response.text();
      let payload = null;
      try {
        payload = JSON.parse(text);
      } catch (error) {
        throw new Error(`Douyin returned non-JSON HTTP ${response.status}: ${text.slice(0, 300)}`);
      }
      if (!response.ok) {
        throw new Error(`Douyin HTTP ${response.status}: ${text.slice(0, 300)}`);
      }
      if (payload.status_code !== 0) {
        throw new Error(`Douyin API status_code=${payload.status_code}: ${(payload.status_msg || payload.message || text).slice(0, 300)}`);
      }
      return {url, payload};
    } finally {
      clearTimeout(timer);
    }
  };
  const intOrNull = (value) => {
    if (value === undefined || value === null || value === "") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const normalize = (comment, parentId, level) => {
    const user = comment?.user || {};
    const ipLabel = comment?.ip_label || comment?.label_text || comment?.ip_label_info?.text || null;
    return {
      comment_id: comment?.cid ? String(comment.cid) : null,
      text: comment?.text || null,
      user_name: user?.nickname || null,
      user_id: user?.uid ? String(user.uid) : null,
      sec_uid: user?.sec_uid || null,
      like_count: intOrNull(comment?.digg_count),
      reply_count: intOrNull(comment?.reply_comment_total ?? comment?.reply_comment_count ?? (Array.isArray(comment?.reply_comment) ? comment.reply_comment.length : null)),
      create_time: intOrNull(comment?.create_time),
      ip_label: ipLabel,
      parent_id: parentId ? String(parentId) : null,
      aweme_id: opts.aweme_id,
      level,
      raw: comment || null
    };
  };
  const rows = [];
  const seen = new Set();
  let duplicateSkips = 0;
  const pageErrors = [];
  const replyErrors = [];
  let cursor = 0;
  let hasMore = 1;
  let total = null;
  let pages = 0;
  const pushRow = (row) => {
    if (!row.comment_id) return false;
    if (seen.has(row.comment_id)) {
      duplicateSkips += 1;
      return false;
    }
    if (opts.max_comments > 0 && rows.length >= opts.max_comments) return false;
    seen.add(row.comment_id);
    rows.push(row);
    return true;
  };
  const roomLeft = () => opts.max_comments <= 0 || rows.length < opts.max_comments;
  while (roomLeft() && hasMore && pages < opts.max_pages) {
    let page;
    try {
      page = await requestJson("/aweme/v1/web/comment/list/", {
        aweme_id: opts.aweme_id,
        cursor,
        count: opts.page_size
      });
    } catch (error) {
      pageErrors.push({cursor, error: String(error && error.message || error)});
      break;
    }
    pages += 1;
    const payload = page.payload || {};
    const comments = Array.isArray(payload.comments) ? payload.comments : [];
    total = payload.total ?? total;
    cursor = payload.cursor ?? cursor;
    hasMore = payload.has_more ? 1 : 0;
    for (const comment of comments) {
      if (!roomLeft()) break;
      const rootRow = normalize(comment, null, 1);
      pushRow(rootRow);
      const inlineReplies = Array.isArray(comment?.reply_comment) ? comment.reply_comment : [];
      for (const reply of inlineReplies) {
        if (!roomLeft() || opts.no_replies) break;
        pushRow(normalize(reply, comment.cid, 2));
      }
      const replyTotal = rootRow.reply_count || 0;
      if (!opts.no_replies && roomLeft() && replyTotal > inlineReplies.length && comment?.cid) {
        let replyCursor = 0;
        let replyHasMore = 1;
        let replyPages = 0;
        while (roomLeft() && replyHasMore && replyPages < opts.reply_max_pages) {
          try {
            const replyPage = await requestJson("/aweme/v1/web/comment/list/reply/", {
              aweme_id: opts.aweme_id,
              item_id: opts.aweme_id,
              comment_id: comment.cid,
              cursor: replyCursor,
              count: Math.min(opts.page_size, 20)
            });
            replyPages += 1;
            const replyPayload = replyPage.payload || {};
            const replies = Array.isArray(replyPayload.comments) ? replyPayload.comments : [];
            for (const reply of replies) {
              if (!roomLeft()) break;
              pushRow(normalize(reply, comment.cid, 2));
            }
            replyCursor = replyPayload.cursor ?? replyCursor;
            replyHasMore = replyPayload.has_more ? 1 : 0;
            if (replies.length === 0) break;
            await sleep(opts.delay_ms + Math.floor(Math.random() * (opts.jitter_ms || 0)));
          } catch (error) {
            replyErrors.push({comment_id: String(comment.cid), cursor: replyCursor, error: String(error && error.message || error)});
            break;
          }
        }
      }
    }
    if (comments.length === 0) break;
    await sleep(opts.delay_ms + Math.floor(Math.random() * (opts.jitter_ms || 0)));
  }
  return {
    ok: pageErrors.length === 0,
    ...baseResult(),
    rows,
    stats: {
      pages,
      total,
      has_more: Boolean(hasMore),
      next_cursor: cursor,
      returned_rows: rows.length,
      duplicate_skips: duplicateSkips,
      root_rows: rows.filter((row) => row.level === 1).length,
      reply_rows: rows.filter((row) => row.level === 2).length
    },
    page_errors: pageErrors,
    reply_errors: replyErrors
  };
}
"""


FETCH_ROOT_PAGE_SCRIPT = r"""
async function fetchDouyinRootPage(opts) {
  const loginPromptVisible = () => {
    const bodyText = document.body ? document.body.innerText || "" : "";
    return /请先登录后发表评论|登录后即可参与互动讨论/.test(bodyText);
  };
  const intOrNull = (value) => {
    if (value === undefined || value === null || value === "") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const firstText = (...values) => {
    for (const value of values) {
      if (typeof value === "string" && value.trim()) return value.trim();
    }
    return null;
  };
  const textFromComment = (comment) => {
    const text = firstText(comment?.text, comment?.text_extra?.text, comment?.share_info?.share_desc);
    if (text) return text;
    if (Array.isArray(comment?.text_extra)) {
      return comment.text_extra.map((item) => item?.hashtag_name || item?.user_name || item?.text || "").join("").trim() || null;
    }
    return null;
  };
  const normalize = (comment, parentId, level) => {
    const user = comment?.user || {};
    const ipLabel = firstText(
      comment?.ip_label,
      comment?.ip_label_text,
      comment?.label_text,
      comment?.address,
      comment?.reply_to_reply_id ? null : comment?.location
    );
    return {
      comment_id: comment?.cid ? String(comment.cid) : null,
      text: textFromComment(comment),
      user_name: firstText(user?.nickname, user?.unique_id, user?.short_id),
      user_id: user?.uid ? String(user.uid) : null,
      sec_uid: user?.sec_uid || null,
      like_count: intOrNull(comment?.digg_count),
      reply_count: intOrNull(comment?.reply_comment_total ?? comment?.reply_comment_count ?? (Array.isArray(comment?.reply_comment) ? comment.reply_comment.length : null)),
      create_time: intOrNull(comment?.create_time),
      ip_label: ipLabel,
      parent_id: parentId ? String(parentId) : null,
      aweme_id: String(opts.aweme_id),
      level,
      raw: comment
    };
  };
  const base = () => ({
    page_url: location.href,
    page_title: document.title,
    login_prompt_visible: loginPromptVisible(),
    check_login_only: Boolean(opts.check_login_only)
  });
  if (opts.check_login_only) {
    return {
      ok: true,
      ...base(),
      skipped_fetch: true,
      rows: [],
      stats: {pages: 0, total: null, has_more: false, next_cursor: 0, returned_rows: 0, duplicate_skips: 0, root_rows: 0, reply_rows: 0},
      page_errors: loginPromptVisible() ? [{stage: "login_check", message: "Douyin page is showing a login-required comment prompt."}] : [],
      reply_errors: []
    };
  }
  if (opts.require_login && loginPromptVisible()) {
    return {
      ok: false,
      ...base(),
      skipped_fetch: true,
      rows: [],
      stats: {pages: 0, total: null, has_more: false, next_cursor: 0, returned_rows: 0, duplicate_skips: 0, root_rows: 0, reply_rows: 0},
      page_errors: [{stage: "login_check", message: "Douyin page is showing a login-required comment prompt; comment API fetch was skipped."}],
      reply_errors: []
    };
  }
  const signUrl = (url) => {
    if (window.byted_acrawler?.frontierSign) {
      const signed = window.byted_acrawler.frontierSign(url.pathname + url.search);
      if (signed && signed["X-Bogus"]) url.searchParams.set("X-Bogus", signed["X-Bogus"]);
    }
    return url;
  };
  const baseResource = performance.getEntriesByType("resource")
    .map((entry) => entry.name)
    .find((name) => name.includes("/comment/list/") && !name.includes("/comment/list/reply/") && name.includes("aweme_id=" + String(opts.aweme_id)));
  const url = baseResource ? new URL(baseResource) : new URL("https://www.douyin.com/aweme/v1/web/comment/list/");
  url.searchParams.delete("X-Bogus");
  if (!baseResource) {
    for (const [key, value] of Object.entries({
      device_platform: "webapp",
      aid: "6383",
      channel: "channel_pc_web",
      aweme_id: String(opts.aweme_id),
      item_type: "0"
    })) {
      url.searchParams.set(key, value);
    }
  }
  url.searchParams.set("aweme_id", String(opts.aweme_id));
  url.searchParams.set("cursor", String(opts.cursor || 0));
  url.searchParams.set("count", String(opts.page_size || 50));
  signUrl(url);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.request_timeout_ms || 15000);
  try {
    const response = await fetch(url.toString(), {
      credentials: "include",
      signal: controller.signal,
      headers: {"accept": "application/json, text/plain, */*"}
    });
    const text = await response.text();
    let payload = null;
    try {
      payload = JSON.parse(text);
    } catch (error) {
      return {
        ok: false,
        ...base(),
        rows: [],
        stats: {pages: 0, total: null, has_more: false, next_cursor: opts.cursor || 0, returned_rows: 0, duplicate_skips: 0, root_rows: 0, reply_rows: 0},
        page_errors: [{cursor: opts.cursor || 0, stage: "root_json_parse", status: response.status, body_excerpt: text.slice(0, 300)}],
        reply_errors: []
      };
    }
    if (!response.ok || (payload.status_code !== undefined && payload.status_code !== 0)) {
      return {
        ok: false,
        ...base(),
        rows: [],
        stats: {pages: 0, total: payload.total ?? null, has_more: false, next_cursor: opts.cursor || 0, returned_rows: 0, duplicate_skips: 0, root_rows: 0, reply_rows: 0},
        page_errors: [{
          cursor: opts.cursor || 0,
          stage: "root_api",
          status: response.status,
          status_code: payload.status_code ?? null,
          status_msg: payload.status_msg || payload.message || null,
          body_excerpt: text.slice(0, 300)
        }],
        reply_errors: []
      };
    }
    const comments = Array.isArray(payload.comments) ? payload.comments : [];
    const rows = [];
    for (const comment of comments) {
      rows.push(normalize(comment, null, 1));
      if (opts.include_inline_replies && Array.isArray(comment?.reply_comment)) {
        for (const reply of comment.reply_comment) {
          rows.push(normalize(reply, comment.cid, 2));
        }
      }
    }
    return {
      ok: true,
      ...base(),
      rows,
      stats: {
        pages: 1,
        total: payload.total ?? null,
        has_more: Boolean(payload.has_more),
        next_cursor: payload.cursor ?? opts.cursor ?? 0,
        returned_rows: rows.length,
        duplicate_skips: 0,
        root_rows: comments.length,
        reply_rows: rows.filter((row) => row.level === 2).length
      },
      page_errors: [],
      reply_errors: []
    };
  } catch (error) {
    return {
      ok: false,
      ...base(),
      rows: [],
      stats: {pages: 0, total: null, has_more: false, next_cursor: opts.cursor || 0, returned_rows: 0, duplicate_skips: 0, root_rows: 0, reply_rows: 0},
      page_errors: [{cursor: opts.cursor || 0, stage: "root_fetch", message: String(error && error.message || error)}],
      reply_errors: []
    };
  } finally {
    clearTimeout(timer);
  }
}
"""


FETCH_REPLY_PAGE_SCRIPT = r"""
async function fetchDouyinReplyPage(opts) {
  const intOrNull = (value) => {
    if (value === undefined || value === null || value === "") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const firstText = (...values) => {
    for (const value of values) {
      if (typeof value === "string" && value.trim()) return value.trim();
    }
    return null;
  };
  const textFromComment = (comment) => {
    const text = firstText(comment?.text, comment?.text_extra?.text, comment?.share_info?.share_desc);
    if (text) return text;
    if (Array.isArray(comment?.text_extra)) {
      return comment.text_extra.map((item) => item?.hashtag_name || item?.user_name || item?.text || "").join("").trim() || null;
    }
    return null;
  };
  const normalize = (comment, parentId, level) => {
    const user = comment?.user || {};
    const ipLabel = firstText(
      comment?.ip_label,
      comment?.ip_label_text,
      comment?.label_text,
      comment?.address,
      comment?.reply_to_reply_id ? null : comment?.location
    );
    return {
      comment_id: comment?.cid ? String(comment.cid) : null,
      text: textFromComment(comment),
      user_name: firstText(user?.nickname, user?.unique_id, user?.short_id),
      user_id: user?.uid ? String(user.uid) : null,
      sec_uid: user?.sec_uid || null,
      like_count: intOrNull(comment?.digg_count),
      reply_count: intOrNull(comment?.reply_comment_total ?? comment?.reply_comment_count ?? (Array.isArray(comment?.reply_comment) ? comment.reply_comment.length : null)),
      create_time: intOrNull(comment?.create_time),
      ip_label: ipLabel,
      parent_id: parentId ? String(parentId) : null,
      aweme_id: String(opts.aweme_id),
      level,
      raw: comment
    };
  };
  const signUrl = (url) => {
    if (window.byted_acrawler?.frontierSign) {
      const signed = window.byted_acrawler.frontierSign(url.pathname + url.search);
      if (signed && signed["X-Bogus"]) url.searchParams.set("X-Bogus", signed["X-Bogus"]);
    }
    return url;
  };
  const url = new URL("https://www.douyin.com/aweme/v1/web/comment/list/reply/");
  for (const [key, value] of Object.entries({
    device_platform: "webapp",
    aid: "6383",
    channel: "channel_pc_web",
    item_id: String(opts.aweme_id),
    comment_id: String(opts.comment_id),
    cursor: String(opts.cursor || 0),
    count: String(Math.min(opts.page_size || 50, 50))
  })) {
    url.searchParams.set(key, value);
  }
  signUrl(url);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.request_timeout_ms || 15000);
  try {
    const response = await fetch(url.toString(), {
      credentials: "include",
      signal: controller.signal,
      headers: {"accept": "application/json, text/plain, */*"}
    });
    const text = await response.text();
    let payload = null;
    try {
      payload = JSON.parse(text);
    } catch (error) {
      return {ok: false, rows: [], error: {stage: "reply_json_parse", status: response.status, body_excerpt: text.slice(0, 300)}};
    }
    if (!response.ok || (payload.status_code !== undefined && payload.status_code !== 0)) {
      return {
        ok: false,
        rows: [],
        error: {
          stage: "reply_api",
          status: response.status,
          status_code: payload.status_code ?? null,
          status_msg: payload.status_msg || payload.message || null,
          body_excerpt: text.slice(0, 300)
        }
      };
    }
    const replies = Array.isArray(payload.comments) ? payload.comments : [];
    return {
      ok: true,
      rows: replies.map((reply) => normalize(reply, opts.comment_id, 2)),
      has_more: Boolean(payload.has_more),
      next_cursor: payload.cursor ?? opts.cursor ?? 0,
      total: payload.total ?? null
    };
  } catch (error) {
    return {ok: false, rows: [], error: {stage: "reply_fetch", message: String(error && error.message || error)}};
  } finally {
    clearTimeout(timer);
  }
}
"""


def sleep_with_jitter(delay_ms, jitter_ms):
    delay = max(delay_ms, 0) / 1000
    jitter = random.uniform(0, max(jitter_ms, 0) / 1000) if jitter_ms else 0
    time.sleep(delay + jitter)


def fetch_root_pages(session, args, aweme_id):
    rows = []
    seen = set()
    page_errors = []
    duplicate_skips = 0
    cursor = 0
    has_more = True
    pages = 0
    total = None
    page_url = None
    page_title = None
    login_prompt_visible = False
    skipped_fetch = False
    check_login_only = False

    def room_left():
        return args.max_comments <= 0 or len(rows) < args.max_comments

    while room_left() and has_more and pages < args.max_pages:
        opts = {
            "aweme_id": aweme_id,
            "cursor": cursor,
            "page_size": args.page_size,
            "request_timeout_ms": args.request_timeout_ms,
            "require_login": args.require_login,
            "check_login_only": args.check_login_only,
            "include_inline_replies": args.include_replies and not args.no_replies,
        }
        expression = f"({FETCH_ROOT_PAGE_SCRIPT}\n)({json.dumps(opts, ensure_ascii=False)})"
        page = session.evaluate(expression, timeout=max(30, args.request_timeout_ms // 1000 + 20))
        if not isinstance(page, dict):
            raise DouyinCommentError(f"Unexpected root page result: {page!r}")
        page_url = page.get("page_url") or page_url
        page_title = page.get("page_title") or page_title
        login_prompt_visible = bool(page.get("login_prompt_visible"))
        skipped_fetch = bool(page.get("skipped_fetch"))
        check_login_only = bool(page.get("check_login_only"))
        stats = page.get("stats") or {}
        if stats.get("total") is not None:
            total = stats.get("total")
        cursor = stats.get("next_cursor", cursor)
        has_more = bool(stats.get("has_more"))
        if page.get("page_errors"):
            page_errors.extend(page.get("page_errors") or [])
            break
        if skipped_fetch or check_login_only:
            break
        page_rows = page.get("rows") or []
        pages += int(stats.get("pages") or 0)
        for row in page_rows:
            cid = row.get("comment_id")
            if cid and cid in seen:
                duplicate_skips += 1
                continue
            if cid:
                seen.add(cid)
            rows.append(row)
            if not room_left():
                break
        if not page_rows:
            break
        if has_more and room_left():
            sleep_with_jitter(args.delay_ms, args.jitter_ms)

    return {
        "ok": not page_errors,
        "page_url": page_url,
        "page_title": page_title,
        "login_prompt_visible": login_prompt_visible,
        "check_login_only": check_login_only,
        "skipped_fetch": skipped_fetch,
        "rows": rows,
        "stats": {
            "pages": pages,
            "total": total,
            "has_more": bool(has_more),
            "next_cursor": cursor,
            "returned_rows": len(rows),
            "duplicate_skips": duplicate_skips,
            "root_rows": sum(1 for row in rows if row.get("level") == 1),
            "reply_rows": sum(1 for row in rows if row.get("level") == 2),
        },
        "page_errors": page_errors,
        "reply_errors": [],
    }


def add_reply_rows(session, args, aweme_id, result):
    if args.no_replies or not args.include_replies or result.get("skipped_fetch"):
        return result
    rows = list(result.get("rows") or [])
    root_rows = [row for row in rows if row.get("level") == 1]
    seen = {row.get("comment_id") for row in rows if row.get("comment_id")}
    reply_errors = list(result.get("reply_errors") or [])
    existing_replies = {}
    for row in rows:
        if row.get("level") == 2 and row.get("parent_id"):
            existing_replies[row["parent_id"]] = existing_replies.get(row["parent_id"], 0) + 1

    def room_left():
        return args.max_comments <= 0 or len(rows) < args.max_comments

    for root in root_rows:
        if not room_left():
            break
        reply_count = root.get("reply_count") or 0
        if reply_count <= 0 or not root.get("comment_id"):
            continue
        if existing_replies.get(str(root["comment_id"]), 0) >= reply_count:
            continue
        cursor = 0
        has_more = True
        pages = 0
        while room_left() and has_more and pages < args.reply_max_pages:
            opts = {
                "aweme_id": aweme_id,
                "comment_id": root["comment_id"],
                "cursor": cursor,
                "page_size": args.page_size,
                "request_timeout_ms": args.request_timeout_ms,
            }
            expression = f"({FETCH_REPLY_PAGE_SCRIPT}\n)({json.dumps(opts, ensure_ascii=False)})"
            try:
                page = session.evaluate(expression, timeout=max(30, args.request_timeout_ms // 1000 + 20))
            except Exception as exc:
                reply_errors.append(
                    {
                        "comment_id": str(root["comment_id"]),
                        "cursor": cursor,
                        "error": {"stage": "reply_eval", "message": f"{type(exc).__name__}: {exc}"},
                    }
                )
                break
            pages += 1
            if not isinstance(page, dict) or not page.get("ok"):
                error = page.get("error") if isinstance(page, dict) else {"message": repr(page)}
                reply_errors.append({"comment_id": str(root["comment_id"]), "cursor": cursor, "error": error})
                break
            page_rows = page.get("rows") or []
            for reply in page_rows:
                cid = reply.get("comment_id")
                if cid and cid in seen:
                    continue
                if cid:
                    seen.add(cid)
                rows.append(reply)
                if reply.get("parent_id"):
                    existing_replies[reply["parent_id"]] = existing_replies.get(reply["parent_id"], 0) + 1
                if not room_left():
                    break
            cursor = page.get("next_cursor", cursor)
            has_more = bool(page.get("has_more"))
            if not page_rows:
                break
            if has_more and room_left():
                sleep_with_jitter(args.delay_ms, args.jitter_ms)
        if room_left():
            sleep_with_jitter(args.delay_ms, args.jitter_ms)

    stats = dict(result.get("stats") or {})
    stats["returned_rows"] = len(rows)
    stats["root_rows"] = sum(1 for row in rows if row.get("level") == 1)
    stats["reply_rows"] = sum(1 for row in rows if row.get("level") == 2)
    result["rows"] = rows
    result["stats"] = stats
    result["reply_errors"] = reply_errors
    return result


def fetch_comments(args, aweme_id, video_url):
    page = None
    session = None
    try:
        page = open_page_session(args.cdp_host, args.cdp_port, video_url, args.cdp_proxy_url)
        session = page["session"]
        session.command("Runtime.enable", timeout=10)
        time.sleep(max(args.initial_wait_ms, 0) / 1000)
        result = fetch_root_pages(session, args, aweme_id)
        result = add_reply_rows(session, args, aweme_id, result)
        result["cdp_mode"] = page.get("mode")
        if page.get("devtools_active_port"):
            result["devtools_active_port"] = page["devtools_active_port"]
        if page.get("cdp_proxy_url"):
            result["cdp_proxy_url"] = page["cdp_proxy_url"]
        return result
    finally:
        if page and page.get("target_id") and not args.keep_tab:
            try:
                if page.get("mode") == "web_access_proxy":
                    close_proxy_target(page.get("cdp_proxy_url"), page["target_id"])
                elif page.get("mode") == "browser_devtools_active_port" and session:
                    session.command("Target.closeTarget", {"targetId": page["target_id"]}, timeout=10, use_session=False)
                elif not args.keep_tab:
                    close_target(args.cdp_host, args.cdp_port, page["target_id"])
            except Exception:
                pass
        if session:
            session.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch Douyin comments through an existing Chrome/CDP browser session.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video-url", help="Final Douyin video URL, preferably https://www.douyin.com/video/<aweme_id>.")
    source.add_argument("--aweme-id", help="Douyin aweme id.")
    source.add_argument("--video-dir", help="Existing downloaded Douyin video directory containing manifest.json or metadata.json.")
    parser.add_argument("--out", help="JSONL output file. Defaults to comments.jsonl under the output directory.")
    parser.add_argument("--out-dir", help="Output directory. Defaults to <video-dir>/comments or downloads/douyin-comments/<aweme_id>.")
    parser.add_argument("--max-comments", type=int, default=0, help="Maximum rows to write. 0 means no explicit row cap.")
    parser.add_argument("--max-pages", type=int, default=20, help="Maximum root-comment pages to fetch.")
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--cdp-host", default=DEFAULT_CDP_HOST)
    parser.add_argument("--cdp-port", type=int, default=DEFAULT_CDP_PORT)
    parser.add_argument(
        "--cdp-proxy-url",
        default=DEFAULT_CDP_PROXY_URL,
        help="Optional web-access CDP Proxy URL. Default tries http://127.0.0.1:3456 before raw CDP; pass an empty string to disable.",
    )
    parser.add_argument(
        "--require-login",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require a logged-in Douyin browser session. Enabled by default; use --no-require-login only for diagnostics.",
    )
    parser.add_argument("--include-replies", action="store_true", help="Also fetch reply pages. Root comments only by default.")
    parser.add_argument("--no-replies", action="store_true", help="Compatibility alias for root-comment-only mode.")
    parser.add_argument("--reply-max-pages", type=int, default=3)
    parser.add_argument("--request-timeout-ms", type=int, default=15000)
    parser.add_argument("--eval-timeout-seconds", type=int, default=180)
    parser.add_argument("--initial-wait-ms", type=int, default=7000)
    parser.add_argument("--delay-ms", type=int, default=1500, help="Delay between Douyin API pages.")
    parser.add_argument("--jitter-ms", type=int, default=700, help="Random extra delay up to this many milliseconds.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve target and output paths without opening Chrome or writing files.")
    parser.add_argument("--check-login-only", action="store_true", help="Open the Douyin page and verify login state without calling comment APIs.")
    parser.add_argument("--keep-tab", action="store_true", help="Leave the temporary Douyin tab open for debugging.")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.max_comments < 0:
        raise DouyinCommentError("--max-comments must be >= 0")
    if args.max_pages < 1:
        raise DouyinCommentError("--max-pages must be >= 1")
    if args.page_size < 1:
        raise DouyinCommentError("--page-size must be >= 1")
    if args.delay_ms < 0 or args.jitter_ms < 0:
        raise DouyinCommentError("--delay-ms and --jitter-ms must be >= 0")
    aweme_id, video_url = resolve_target(args)
    out_dir, jsonl_path, json_path, manifest_path = resolve_outputs(args, aweme_id)
    plan = {
        "aweme_id": aweme_id,
        "video_url": video_url,
        "out_dir": str(out_dir),
        "jsonl_path": str(jsonl_path),
        "json_path": str(json_path),
        "manifest_path": str(manifest_path),
        "cdp": {"host": args.cdp_host, "port": args.cdp_port, "proxy_url": normalize_proxy_url(args.cdp_proxy_url)},
    }
    if args.dry_run:
        print(json.dumps({"dry_run": True, **plan}, ensure_ascii=False, indent=2))
        return

    started_at = now_str()
    result = fetch_comments(args, aweme_id, video_url)
    rows = result.get("rows") or []
    stats = result.get("stats") or {}
    total_count = stats.get("total")
    returned_roots = stats.get("root_rows") or 0
    returned_for_total = stats.get("returned_rows") if args.include_replies and not args.no_replies else returned_roots
    returned_for_total = returned_for_total or 0
    login_prompt_visible = bool(result.get("login_prompt_visible"))
    likely_complete = (
        not login_prompt_visible
        and
        not bool(stats.get("has_more"))
        and not result.get("page_errors")
        and not (isinstance(total_count, int) and total_count > returned_for_total)
    )
    bundle = {
        "platform": "douyin",
        "fetched_at": now_str(),
        "aweme_id": aweme_id,
        "video_url": video_url,
        "page_url": result.get("page_url"),
        "page_title": result.get("page_title"),
        "complete": likely_complete,
        "comments": rows,
        "stats": stats,
        "page_errors": result.get("page_errors") or [],
        "reply_errors": result.get("reply_errors") or [],
    }
    manifest = {
        "ok": not bool(result.get("page_errors")),
        "started_at": started_at,
        "ended_at": now_str(),
        **plan,
        "outputs": {
            "jsonl": str(jsonl_path),
            "json": str(json_path),
            "manifest": str(manifest_path),
        },
        "stats": stats,
        "login_prompt_visible": login_prompt_visible,
        "cdp_mode": result.get("cdp_mode"),
        "cdp_proxy_url": result.get("cdp_proxy_url"),
        "fetch_skipped": bool(result.get("skipped_fetch")),
        "check_login_only": bool(result.get("check_login_only")),
        "complete": likely_complete,
        "page_errors": result.get("page_errors") or [],
        "reply_errors": result.get("reply_errors") or [],
        "limitations": [],
    }
    if manifest["login_prompt_visible"]:
        manifest["limitations"].append("Douyin page displayed a login prompt; API results may be public-only or limited.")
    login_required_failed = bool(
        args.require_login
        and (
            manifest["login_prompt_visible"]
            or any((err or {}).get("stage") == "login_check" for err in manifest["page_errors"])
        )
    )
    if login_required_failed:
        manifest["ok"] = False
        manifest["limitations"].append("Login is required and the browser session did not pass the login check; no comment API fetch was attempted.")
    elif manifest["check_login_only"]:
        manifest["limitations"].append("Login check only; no comment API fetch was attempted.")
    if isinstance(total_count, int) and total_count > returned_for_total:
        unit = "comments/replies" if args.include_replies and not args.no_replies else "root comments"
        manifest["limitations"].append(
            f"Douyin API reported total={total_count}, but returned {returned_for_total} {unit} in fetched pages."
        )
    if manifest["reply_errors"]:
        manifest["limitations"].append("Some reply pages failed or timed out; root comments were kept and reply errors are recorded.")
    if (manifest["stats"].get("has_more") is True) or (args.max_comments > 0 and len(rows) >= args.max_comments):
        manifest["limitations"].append("Run stopped before exhausting all comments because max-comments or max-pages was reached.")
    if manifest["page_errors"] and not login_required_failed:
        manifest["limitations"].append("Root comment API failed or was blocked; check login state, CAPTCHA, and CDP browser health.")

    write_jsonl(jsonl_path, rows)
    write_json(json_path, bundle)
    write_json(manifest_path, manifest)
    print(json.dumps({"manifest": str(manifest_path), "summary": manifest["stats"], "limitations": manifest["limitations"]}, ensure_ascii=False, indent=2))
    if manifest["page_errors"] or login_required_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except DouyinCommentError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1)
