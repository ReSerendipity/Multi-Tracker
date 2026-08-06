#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import net from "node:net";
import crypto from "node:crypto";

const mixinKeyEncTab = [
  46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
  27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
  37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
  22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
];

function usage() {
  console.log(`Usage:
  node fetch_comments.mjs --video <url|BV|av> [--output comments.jsonl]
  node fetch_comments.mjs --videos-file videos.json --output-dir comments-dir

Options:
  --video <url|BV|av>       Required. Bilibili video URL, BV id, or av id.
  --videos-file <file>      JSON array of videos for batch mode. Reuses one Chrome CDP connection.
  --output-dir <dir>        Output directory for batch mode.
  --output <file>           Output JSONL path.
  --max-root <n>            Limit first-level comments for testing.
  --no-replies              Do not fetch second-level replies.
  --delay-ms <n>            Delay between root comment pages. Default: 500.
  --reply-delay-ms <n>      Delay between reply pages. Default: 300.
  --api-retries <n>         Retries for transient Bilibili API failures. Default: 2.
  --retry-delay-ms <n>      Base delay before retrying transient API failures. Default: 15000.
  --stop-after-412 <n>      Stop a batch after this many consecutive HTTP 412 failures. Default: 3.
  --keep-tab                Keep the temporary Bilibili tab open.
  --cdp-endpoint <ws-url>   Optional explicit browser websocket endpoint.
`);
}

function parseArgs(argv) {
  const out = {
    includeReplies: true,
    delayMs: 500,
    replyDelayMs: 300,
    apiRetries: 2,
    retryDelayMs: 15000,
    stopAfter412: 3,
    ps: 20,
    replyPs: 20,
    mode: 3,
    keepTab: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const next = () => {
      if (i + 1 >= argv.length) throw new Error(`Missing value for ${arg}`);
      return argv[++i];
    };
    if (arg === "--help" || arg === "-h") out.help = true;
    else if (arg === "--video") out.video = next();
    else if (arg === "--videos-file") out.videosFile = next();
    else if (arg === "--output-dir") out.outputDir = next();
    else if (arg === "--output") out.output = next();
    else if (arg === "--max-root") out.maxRoot = Number(next());
    else if (arg === "--no-replies") out.includeReplies = false;
    else if (arg === "--delay-ms") out.delayMs = Number(next());
    else if (arg === "--reply-delay-ms") out.replyDelayMs = Number(next());
    else if (arg === "--api-retries") out.apiRetries = Number(next());
    else if (arg === "--retry-delay-ms") out.retryDelayMs = Number(next());
    else if (arg === "--stop-after-412") out.stopAfter412 = Number(next());
    else if (arg === "--keep-tab") out.keepTab = true;
    else if (arg === "--cdp-endpoint") out.cdpEndpoint = next();
    else throw new Error(`Unknown argument: ${arg}`);
  }
  return out;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function extractVideoId(input) {
  const raw = String(input || "").trim();
  const bv = raw.match(/BV[0-9A-Za-z]{10}/i)?.[0];
  if (bv) return { type: "bvid", value: bv };
  const av = raw.match(/(?:^|\/|av)(\d{5,})/i)?.[1];
  if (av) return { type: "aid", value: av };
  throw new Error(`Cannot find BV or av id in: ${input}`);
}

function videoPageUrl(videoId) {
  if (videoId.type === "bvid") return `https://www.bilibili.com/video/${videoId.value}`;
  return `https://www.bilibili.com/video/av${videoId.value}`;
}

function defaultOutputName(videoId) {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "").replace("T", "_");
  return path.resolve(`bilibili_comments_${videoId.value}_${stamp}.jsonl`);
}

function activePortFiles() {
  const files = [];
  const home = os.homedir();
  if (process.platform === "win32") {
    const local = process.env.LOCALAPPDATA || path.join(home, "AppData", "Local");
    files.push(
      path.join(local, "Google", "Chrome", "User Data", "DevToolsActivePort"),
      path.join(local, "Chromium", "User Data", "DevToolsActivePort"),
    );
  } else if (process.platform === "darwin") {
    files.push(
      path.join(home, "Library", "Application Support", "Google", "Chrome", "DevToolsActivePort"),
      path.join(home, "Library", "Application Support", "Chromium", "DevToolsActivePort"),
    );
  } else {
    files.push(
      path.join(home, ".config", "google-chrome", "DevToolsActivePort"),
      path.join(home, ".config", "chromium", "DevToolsActivePort"),
    );
  }
  return files;
}

function checkPort(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection(port, "127.0.0.1");
    const timer = setTimeout(() => {
      socket.destroy();
      resolve(false);
    }, 1500);
    socket.once("connect", () => {
      clearTimeout(timer);
      socket.destroy();
      resolve(true);
    });
    socket.once("error", () => {
      clearTimeout(timer);
      resolve(false);
    });
  });
}

async function discoverEndpoint(explicit) {
  if (explicit) return explicit;
  for (const file of activePortFiles()) {
    try {
      const lines = fs.readFileSync(file, "utf8").trim().split(/\r?\n/).filter(Boolean);
      const port = Number(lines[0]);
      const wsPath = lines[1];
      if (port > 0 && wsPath && await checkPort(port)) {
        return `ws://127.0.0.1:${port}${wsPath}`;
      }
    } catch {
      // Try next location.
    }
  }
  throw new Error("Chrome remote debugging endpoint not found. Open chrome://inspect/#remote-debugging and enable remote debugging.");
}

class CdpClient {
  constructor(endpoint) {
    this.endpoint = endpoint;
    this.ws = null;
    this.nextId = 0;
    this.pending = new Map();
  }

  connect(timeoutMs = 60000) {
    return new Promise((resolve, reject) => {
      const WS = globalThis.WebSocket;
      if (!WS) {
        reject(new Error("Node.js WebSocket is unavailable. Use Node.js 22+."));
        return;
      }
      const timer = setTimeout(() => reject(new Error(`Timed out connecting to ${this.endpoint}`)), timeoutMs);
      this.ws = new WS(this.endpoint);

      const onOpen = () => {
        clearTimeout(timer);
        resolve();
      };
      const onError = (event) => {
        clearTimeout(timer);
        reject(new Error(event?.message || event?.error?.message || "WebSocket connection failed"));
      };
      const onMessage = (event) => {
        const data = typeof event.data === "string" ? event.data : Buffer.from(event.data).toString("utf8");
        const msg = JSON.parse(data);
        if (msg.id && this.pending.has(msg.id)) {
          const { resolve: ok, reject: bad, timer: t } = this.pending.get(msg.id);
          clearTimeout(t);
          this.pending.delete(msg.id);
          if (msg.error) bad(new Error(`${msg.error.message || "CDP error"} ${JSON.stringify(msg.error.data || "")}`));
          else ok(msg.result);
        }
      };

      this.ws.addEventListener("open", onOpen, { once: true });
      this.ws.addEventListener("error", onError, { once: true });
      this.ws.addEventListener("message", onMessage);
    });
  }

  send(method, params = {}, sessionId = null, timeoutMs = 30000) {
    return new Promise((resolve, reject) => {
      const id = ++this.nextId;
      const payload = { id, method, params };
      if (sessionId) payload.sessionId = sessionId;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP command timed out: ${method}`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      this.ws.send(JSON.stringify(payload));
    });
  }

  close() {
    try {
      this.ws?.close();
    } catch {
      // Ignore close errors.
    }
  }
}

async function evalInPage(cdp, sessionId, fn, args = [], timeoutMs = 30000) {
  const expression = `(${fn.toString()})(...${JSON.stringify(args)})`;
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  }, sessionId, timeoutMs);
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text || "Runtime.evaluate failed");
  }
  return result.result?.value;
}

async function browserFetchJson(cdp, sessionId, url) {
  const result = await evalInPage(cdp, sessionId, async (targetUrl) => {
    const res = await fetch(targetUrl, {
      credentials: "include",
      headers: {
        "accept": "application/json, text/plain, */*",
      },
    });
    const text = await res.text();
    let json = null;
    try {
      json = JSON.parse(text);
    } catch {
      return { ok: res.ok, status: res.status, text };
    }
    return { ok: res.ok, status: res.status, json };
  }, [url], 45000);

  if (!result?.ok) {
    const error = new Error(`HTTP ${result?.status || "unknown"} for ${url}`);
    error.status = result?.status;
    error.url = url;
    throw error;
  }
  if (!result.json || result.json.code !== 0) {
    const error = new Error(`Bilibili API error for ${url}: ${JSON.stringify(result.json)}`);
    error.code = result.json?.code;
    error.url = url;
    throw error;
  }
  return result.json.data;
}

function isRetryableApiError(error) {
  return error?.status === 412
    || error?.status === 429
    || error?.status === 500
    || error?.status === 502
    || error?.status === 503
    || error?.status === 504;
}

function getMixinKey(imgKey, subKey) {
  const raw = `${imgKey}${subKey}`;
  return mixinKeyEncTab.map((n) => raw[n]).join("").slice(0, 32);
}

function fileKey(url) {
  const name = String(url || "").split("/").pop() || "";
  return name.split(".")[0];
}

function signParams(params, wbi) {
  const signed = { ...params, wts: Math.floor(Date.now() / 1000) };
  const keys = Object.keys(signed).sort();
  const query = keys.map((key) => {
    const value = String(signed[key]).replace(/[!'()*]/g, "");
    return `${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
  }).join("&");
  const wRid = crypto.createHash("md5").update(query + wbi.mixinKey).digest("hex");
  return `${query}&w_rid=${wRid}`;
}

async function signedGet(cdp, sessionId, uri, params, wbi, args) {
  for (let attempt = 0; ; attempt++) {
    const query = signParams(params, wbi);
    try {
      return await browserFetchJson(cdp, sessionId, `https://api.bilibili.com${uri}?${query}`);
    } catch (error) {
      if (!isRetryableApiError(error) || attempt >= args.apiRetries) throw error;
      const waitMs = args.retryDelayMs * (attempt + 1);
      console.error(`[bilibili-comments] retry ${attempt + 1}/${args.apiRetries} after ${error.message}; wait ${waitMs}ms`);
      await sleep(waitMs);
    }
  }
}

function normalizeComment(comment, video, level) {
  const member = comment.member || {};
  const content = comment.content || {};
  const root = String(comment.root && comment.root !== 0 ? comment.root : comment.rpid);
  return {
    comment_id: String(comment.rpid),
    parent_comment_id: String(comment.parent || 0),
    root_comment_id: level === 1 ? String(comment.rpid) : root,
    level,
    create_time: comment.ctime,
    video_id: String(video.aid),
    bvid: video.bvid || "",
    content: content.message || "",
    user_id: String(member.mid || ""),
    nickname: member.uname || "",
    sex: member.sex || "",
    sign: member.sign || "",
    avatar: member.avatar || "",
    sub_comment_count: String(comment.rcount || 0),
    like_count: comment.like || 0,
    last_modify_ts: Date.now(),
  };
}

function writeJsonLine(stream, item) {
  stream.write(`${JSON.stringify(item)}\n`);
}

async function fetchOneVideo(cdp, args, videoInput, outputPath) {
  const videoId = extractVideoId(videoInput);
  const output = path.resolve(outputPath || defaultOutputName(videoId));
  fs.mkdirSync(path.dirname(output), { recursive: true });

  let targetId = null;
  let sessionId = null;
  const seen = new Set();
  const rootsForReplies = [];
  const stats = {
    output,
    video: videoInput,
    bvid: videoId.type === "bvid" ? videoId.value : "",
    aid: videoId.type === "aid" ? videoId.value : "",
    root_comments: 0,
    reply_comments: 0,
    total_rows: 0,
    duplicate_skips: 0,
    roots_with_replies: 0,
    declared_reply_count: 0,
  };

  const stream = fs.createWriteStream(output, { flags: "w", encoding: "utf8" });

  try {
    const created = await cdp.send("Target.createTarget", { url: videoPageUrl(videoId), newWindow: false });
    targetId = created.targetId;
    const attached = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
    sessionId = attached.sessionId;
    await cdp.send("Runtime.enable", {}, sessionId);
    await sleep(2500);

    const viewParams = videoId.type === "bvid"
      ? `bvid=${encodeURIComponent(videoId.value)}`
      : `aid=${encodeURIComponent(videoId.value)}`;
    const view = await browserFetchJson(cdp, sessionId, `https://api.bilibili.com/x/web-interface/view?${viewParams}`);
    const video = { aid: view.aid, bvid: view.bvid, title: view.title, stat_reply: view.stat?.reply };
    stats.bvid = video.bvid || stats.bvid;
    stats.aid = String(video.aid || stats.aid || "");
    stats.title = video.title || "";

    const nav = await browserFetchJson(cdp, sessionId, "https://api.bilibili.com/x/web-interface/nav");
    const imgKey = fileKey(nav.wbi_img?.img_url);
    const subKey = fileKey(nav.wbi_img?.sub_url);
    if (!imgKey || !subKey) throw new Error("Cannot read Bilibili WBI keys from nav response");
    const wbi = { mixinKey: getMixinKey(imgKey, subKey) };

    console.error(`[bilibili-comments] video: ${video.bvid || video.aid} | ${video.title || ""}`);
    console.error(`[bilibili-comments] login: ${nav.isLogin ? "yes" : "no"}${nav.uname ? ` (${nav.uname})` : ""}`);

    let next = 0;
    while (true) {
      const data = await signedGet(cdp, sessionId, "/x/v2/reply/wbi/main", {
        oid: video.aid,
        type: 1,
        mode: args.mode,
        ps: args.ps,
        next,
      }, wbi, args);

      let replies = Array.isArray(data.replies) ? data.replies : [];
      if (args.maxRoot && stats.root_comments + replies.length > args.maxRoot) {
        replies = replies.slice(0, args.maxRoot - stats.root_comments);
      }

      for (const comment of replies) {
        const id = String(comment.rpid);
        if (seen.has(id)) {
          stats.duplicate_skips++;
          continue;
        }
        seen.add(id);
        writeJsonLine(stream, normalizeComment(comment, video, 1));
        stats.root_comments++;
        stats.total_rows++;
        const rcount = Number(comment.rcount || 0);
        if (args.includeReplies && rcount > 0) {
          rootsForReplies.push({ rpid: comment.rpid, rcount });
          stats.roots_with_replies++;
          stats.declared_reply_count += rcount;
        }
      }

      console.error(`[bilibili-comments] roots: ${stats.root_comments}${video.stat_reply ? ` / page total ${video.stat_reply}` : ""}`);
      if (data.cursor?.is_end || replies.length === 0 || (args.maxRoot && stats.root_comments >= args.maxRoot)) break;
      next = data.cursor?.next;
      if (next === undefined || next === null) break;
      await sleep(args.delayMs);
    }

    if (args.includeReplies) {
      let index = 0;
      for (const root of rootsForReplies) {
        index++;
        let pn = 1;
        while (true) {
          const data = await signedGet(cdp, sessionId, "/x/v2/reply/reply", {
            oid: video.aid,
            type: 1,
            mode: args.mode,
            ps: args.replyPs,
            pn,
            root: root.rpid,
          }, wbi, args);

          const list = Array.isArray(data.replies) ? data.replies : [];
          for (const comment of list) {
            const id = String(comment.rpid);
            if (seen.has(id)) {
              stats.duplicate_skips++;
              continue;
            }
            seen.add(id);
            writeJsonLine(stream, normalizeComment(comment, video, 2));
            stats.reply_comments++;
            stats.total_rows++;
          }

          const count = Number(data.page?.count || 0);
          if (list.length === 0 || count <= pn * args.replyPs) break;
          pn++;
          await sleep(args.replyDelayMs);
        }

        if (index % 20 === 0 || index === rootsForReplies.length) {
          console.error(`[bilibili-comments] reply roots: ${index}/${rootsForReplies.length}, replies: ${stats.reply_comments}`);
        }
        await sleep(args.replyDelayMs);
      }
    }
  } finally {
    await new Promise((resolve) => stream.end(resolve));
    if (targetId && !args.keepTab) {
      try {
        await cdp.send("Target.closeTarget", { targetId }, null, 5000);
      } catch {
        // Ignore tab close errors.
      }
    }
  }

  return stats;
}

function loadBatchJobs(args) {
  if (!args.videosFile) return [];
  const raw = JSON.parse(fs.readFileSync(args.videosFile, "utf8"));
  if (!Array.isArray(raw)) throw new Error("--videos-file must contain a JSON array");
  return raw.map((item) => {
    if (typeof item === "string") return { video: item };
    if (item && typeof item === "object" && item.video) return item;
    if (item && typeof item === "object" && item.bvid) return { ...item, video: item.bvid };
    throw new Error(`Invalid batch video entry: ${JSON.stringify(item)}`);
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    usage();
    return;
  }
  if (!args.video && !args.videosFile) throw new Error("--video or --videos-file is required");
  if (args.video && args.videosFile) throw new Error("Use either --video or --videos-file, not both");
  if (args.maxRoot !== undefined && (!Number.isFinite(args.maxRoot) || args.maxRoot <= 0)) {
    throw new Error("--max-root must be a positive number");
  }

  const endpoint = await discoverEndpoint(args.cdpEndpoint);
  console.error(`[bilibili-comments] connecting Chrome CDP: ${endpoint}`);
  const cdp = new CdpClient(endpoint);
  await cdp.connect();

  try {
    if (args.videosFile) {
      const outputDir = path.resolve(args.outputDir || ".");
      const jobs = loadBatchJobs(args);
      const results = [];
      let consecutive412 = 0;
      for (const job of jobs) {
        const videoId = extractVideoId(job.video);
        const output = path.resolve(job.output || path.join(outputDir, `${videoId.value}.jsonl`));
        try {
          const result = await fetchOneVideo(cdp, args, job.video, output);
          results.push(result);
          consecutive412 = 0;
        } catch (error) {
          if (error?.status === 412 || String(error?.message || "").includes("HTTP 412")) {
            consecutive412++;
          } else {
            consecutive412 = 0;
          }
          results.push({
            output,
            video: job.video,
            bvid: job.bvid || (videoId.type === "bvid" ? videoId.value : ""),
            aid: videoId.type === "aid" ? videoId.value : "",
            error: error.message,
          });
          console.error(`[bilibili-comments] video failed: ${job.video}: ${error.message}`);
          if (args.stopAfter412 > 0 && consecutive412 >= args.stopAfter412) {
            const message = `stopped after ${consecutive412} consecutive HTTP 412 failures`;
            console.error(`[bilibili-comments] ${message}`);
            for (const remaining of jobs.slice(jobs.indexOf(job) + 1)) {
              const remainingId = extractVideoId(remaining.video);
              results.push({
                output: path.resolve(remaining.output || path.join(outputDir, `${remainingId.value}.jsonl`)),
                video: remaining.video,
                bvid: remaining.bvid || (remainingId.type === "bvid" ? remainingId.value : ""),
                aid: remainingId.type === "aid" ? remainingId.value : "",
                error: message,
                skipped: true,
              });
            }
            break;
          }
        }
      }
      console.log(JSON.stringify({
        output_dir: outputDir,
        videos: results,
        total_rows: results.reduce((sum, item) => sum + Number(item.total_rows || 0), 0),
        failed: results.filter((item) => item.error).length,
      }, null, 2));
      return;
    }

    const videoId = extractVideoId(args.video);
    const output = path.resolve(args.output || defaultOutputName(videoId));
    const stats = await fetchOneVideo(cdp, args, args.video, output);
    console.log(JSON.stringify(stats, null, 2));
  } finally {
    cdp.close();
  }
}

main().catch((error) => {
  console.error(`[bilibili-comments] ERROR: ${error.message}`);
  process.exit(1);
});
