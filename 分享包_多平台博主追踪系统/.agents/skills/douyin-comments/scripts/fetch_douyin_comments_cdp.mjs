#!/usr/bin/env node
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const AWEME_ID_RE = /\b\d{16,22}\b/;
const DEFAULT_BRIDGE_URL = "http://127.0.0.1:3457";

function parseArgs(argv) {
  const args = {
    url: null,
    out: null,
    pageSize: 50,
    maxPages: 100,
    replyBatchSize: 10,
    delayMs: 250,
    batchDelayMs: 2500,
    initialWaitMs: 8000,
    requestTimeoutMs: 15000,
    evalTimeoutMs: 300000,
    bridgeUrl: process.env.DOUYIN_CDP_BRIDGE_URL || DEFAULT_BRIDGE_URL,
    directCdp: false,
    keepTab: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--video-url") args.url = argv[++i];
    else if (arg === "--aweme-id") args.url = argv[++i];
    else if (arg === "--out-dir") args.out = argv[++i];
    else if (arg === "--page-size") args.pageSize = Number(argv[++i]);
    else if (arg === "--max-pages") args.maxPages = Number(argv[++i]);
    else if (arg === "--reply-batch-size") args.replyBatchSize = Number(argv[++i]);
    else if (arg === "--delay-ms") args.delayMs = Number(argv[++i]);
    else if (arg === "--batch-delay-ms") args.batchDelayMs = Number(argv[++i]);
    else if (arg === "--initial-wait-ms") args.initialWaitMs = Number(argv[++i]);
    else if (arg === "--request-timeout-ms") args.requestTimeoutMs = Number(argv[++i]);
    else if (arg === "--eval-timeout-ms") args.evalTimeoutMs = Number(argv[++i]);
    else if (arg === "--bridge-url") args.bridgeUrl = argv[++i];
    else if (arg === "--direct-cdp") args.directCdp = true;
    else if (arg === "--keep-tab") args.keepTab = true;
    else if (!args.url) args.url = arg;
    else throw new Error(`Unknown argument: ${arg}`);
  }
  if (!args.url) throw new Error("Provide --video-url, --aweme-id, or a Douyin video URL.");
  return args;
}

function extractAwemeId(input) {
  const text = String(input || "");
  try {
    const url = new URL(text);
    for (const key of ["modal_id", "aweme_id", "item_id"]) {
      const value = url.searchParams.get(key);
      if (value && AWEME_ID_RE.test(value)) return value.match(AWEME_ID_RE)[0];
    }
    const match = url.pathname.match(/\/(?:video|share\/video)\/(\d{16,22})/);
    if (match) return match[1];
  } catch {
    // Fall through.
  }
  const match = text.match(AWEME_ID_RE);
  if (match) return match[0];
  throw new Error("Could not extract aweme_id.");
}

function readDevToolsActivePort() {
  const candidates = [];
  if (process.platform === "win32") {
    const local = process.env.LOCALAPPDATA || "";
    candidates.push(
      path.join(local, "Google", "Chrome", "User Data", "DevToolsActivePort"),
      path.join(local, "Chromium", "User Data", "DevToolsActivePort"),
    );
  } else if (process.platform === "darwin") {
    const home = os.homedir();
    candidates.push(
      path.join(home, "Library/Application Support/Google/Chrome/DevToolsActivePort"),
      path.join(home, "Library/Application Support/Chromium/DevToolsActivePort"),
    );
  } else {
    const home = os.homedir();
    candidates.push(
      path.join(home, ".config/google-chrome/DevToolsActivePort"),
      path.join(home, ".config/chromium/DevToolsActivePort"),
    );
  }
  for (const file of candidates) {
    try {
      const [port, wsPath] = fs.readFileSync(file, "utf8").trim().split(/\r?\n/);
      if (port && wsPath) return { port: Number(port), wsPath, file };
    } catch {
      // Continue.
    }
  }
  throw new Error("Could not find Chrome DevToolsActivePort. Enable remote debugging in the logged-in Chrome profile.");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function httpJson(url, options = {}) {
  const response = await fetch(url, {
    method: options.method || "GET",
    headers: options.body ? { "content-type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });
  const text = await response.text();
  let payload = null;
  try {
    payload = JSON.parse(text);
  } catch {
    payload = { ok: false, error: text };
  }
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || `HTTP ${response.status} from ${url}`);
  }
  return payload;
}

async function waitForBridge(bridgeUrl, timeoutMs = 90000) {
  const started = Date.now();
  let lastError = null;
  while (Date.now() - started < timeoutMs) {
    try {
      return await httpJson(`${bridgeUrl}/health`);
    } catch (error) {
      lastError = error;
      await sleep(1000);
    }
  }
  throw new Error(`CDP bridge did not become ready at ${bridgeUrl}: ${lastError?.message || "timeout"}`);
}

async function ensureBridge(bridgeUrl) {
  try {
    return await httpJson(`${bridgeUrl}/health`);
  } catch {
    const bridgeScript = path.join(path.dirname(fileURLToPath(import.meta.url)), "douyin_cdp_bridge.mjs");
    const env = { ...process.env };
    try {
      const parsed = new URL(bridgeUrl);
      if (parsed.port) env.DOUYIN_CDP_BRIDGE_PORT = parsed.port;
    } catch {
      // Let the bridge use its default port; waitForBridge will report a clear URL error.
    }
    spawn(process.execPath, [bridgeScript], {
      detached: true,
      stdio: "ignore",
      windowsHide: true,
      env,
    }).unref();
    return await waitForBridge(bridgeUrl);
  }
}

function safeWriteJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 2), "utf8");
}

function writeJsonl(file, rows) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, rows.map((row) => JSON.stringify(row)).join("\n") + "\n", "utf8");
}

function csvEscape(value) {
  return `"${String(value ?? "").replace(/"/g, '""').replace(/\r?\n/g, "\\n")}"`;
}

function writeCsv(file, rows) {
  const header = ["type", "cid", "parent_cid", "nickname", "uid", "sec_uid", "text", "create_time", "digg_count", "ip_label"];
  const lines = [header.join(",")];
  for (const row of rows) {
    lines.push([
      row.type,
      row.cid,
      row.parent_cid || "",
      row.user?.nickname || "",
      row.user?.uid || "",
      row.user?.sec_uid || "",
      row.text || "",
      row.create_time || "",
      row.digg_count || 0,
      row.ip_label || "",
    ].map(csvEscape).join(","));
  }
  fs.writeFileSync(file, lines.join("\n"), "utf8");
}

function normalizeInlineReply(reply, parentCid) {
  return {
    cid: reply?.cid ? String(reply.cid) : "",
    parent_cid: String(parentCid),
    text: reply?.text || "",
    create_time: reply?.create_time || null,
    digg_count: reply?.digg_count || 0,
    ip_label: reply?.ip_label || reply?.ip_label_text || "",
    reply_to_reply_id: reply?.reply_to_reply_id || "",
    user: {
      uid: reply?.user?.uid ? String(reply.user.uid) : "",
      sec_uid: reply?.user?.sec_uid || "",
      nickname: reply?.user?.nickname || "",
      unique_id: reply?.user?.unique_id || "",
    },
    raw: reply,
  };
}

class CDP {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 1;
    this.pending = new Map();
    ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      if (!msg.id || !this.pending.has(msg.id)) return;
      const { resolve, reject, timer } = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      clearTimeout(timer);
      if (msg.error) reject(new Error(`CDP ${msg.id} failed: ${JSON.stringify(msg.error)}`));
      else resolve(msg.result || {});
    });
  }

  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`WebSocket connect timed out: ${url}`)), 30000);
      ws.addEventListener("open", () => {
        clearTimeout(timer);
        resolve();
      }, { once: true });
      ws.addEventListener("error", (event) => {
        clearTimeout(timer);
        reject(new Error(`WebSocket error: ${event.message || "unknown"}`));
      }, { once: true });
    });
    return new CDP(ws);
  }

  send(method, params = {}, sessionId = null, timeoutMs = 30000) {
    const id = this.nextId++;
    const message = { id, method, params };
    if (sessionId) message.sessionId = sessionId;
    const promise = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP command timed out: ${method}`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
    });
    this.ws.send(JSON.stringify(message));
    return promise;
  }

  close() {
    this.ws.close();
  }
}

async function evaluate(cdp, sessionId, expression, timeoutMs) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
    timeout: timeoutMs,
  }, sessionId, timeoutMs + 10000);
  if (result.exceptionDetails) {
    const text = result.exceptionDetails.exception?.description || result.exceptionDetails.text || JSON.stringify(result.exceptionDetails);
    throw new Error(`Browser evaluation failed: ${text}`);
  }
  return result.result?.value;
}

class BridgeClient {
  constructor(bridgeUrl) {
    this.bridgeUrl = bridgeUrl.replace(/\/$/, "");
  }

  async open(url) {
    const created = await httpJson(`${this.bridgeUrl}/new`, { method: "POST", body: { url } });
    return created;
  }

  async evaluate(sessionId, expression, timeoutMs) {
    const result = await httpJson(`${this.bridgeUrl}/eval`, {
      method: "POST",
      body: { sessionId, expression, timeoutMs },
    });
    return result.value;
  }

  async closeTarget(targetId) {
    await httpJson(`${this.bridgeUrl}/close`, { method: "POST", body: { targetId } });
  }

  close() {}
}

class DirectClient {
  constructor(cdp) {
    this.cdp = cdp;
  }

  async open(url) {
    const created = await this.cdp.send("Target.createTarget", { url, background: true }, null, 30000);
    const attached = await this.cdp.send("Target.attachToTarget", { targetId: created.targetId, flatten: true }, null, 30000);
    await this.cdp.send("Runtime.enable", {}, attached.sessionId, 30000);
    return { targetId: created.targetId, sessionId: attached.sessionId };
  }

  async evaluate(sessionId, expression, timeoutMs) {
    return await evaluate(this.cdp, sessionId, expression, timeoutMs);
  }

  async closeTarget(targetId) {
    await this.cdp.send("Target.closeTarget", { targetId }, null, 30000);
  }

  close() {
    this.cdp.close();
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const awemeId = extractAwemeId(args.url);
  const videoUrl = `https://www.douyin.com/video/${awemeId}`;
  const outDir = path.resolve(args.out || path.join("downloads", "douyin-comments", awemeId));
  fs.mkdirSync(outDir, { recursive: true });

  let client = null;
  let active = null;
  if (args.directCdp) {
    active = readDevToolsActivePort();
    const cdp = await CDP.connect(`ws://127.0.0.1:${active.port}${active.wsPath}`);
    client = new DirectClient(cdp);
  } else {
    const health = await ensureBridge(args.bridgeUrl);
    client = new BridgeClient(args.bridgeUrl);
    active = {
      port: health.chrome_port || null,
      file: health.devtools_active_port || "held by douyin_cdp_bridge",
    };
  }
  let targetId = null;
  let sessionId = null;
  const metadata = {
    aweme_id: awemeId,
    video_url: videoUrl,
    out_dir: outDir,
    cdp_mode: args.directCdp ? "direct" : "bridge",
    bridge_url: args.directCdp ? null : args.bridgeUrl,
    devtools_active_port: { port: active.port, path: active.file },
    started_at: new Date().toISOString(),
    steps: [],
  };
  const note = (step, data = {}) => {
    metadata.steps.push({ step, at: new Date().toISOString(), ...data });
    console.error(`[douyin-cdp] ${step}${Object.keys(data).length ? " " + JSON.stringify(data) : ""}`);
    safeWriteJson(path.join(outDir, "metadata.json"), metadata);
  };

  try {
    note("opening-video-page");
    const opened = await client.open(videoUrl);
    targetId = opened.targetId;
    sessionId = opened.sessionId;
    await sleep(args.initialWaitMs);

    note("fetching-root-comments");
    const rootJson = await client.evaluate(sessionId, `(
      async () => {
        const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
        const withTimeout = (p, ms) => Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), ms))]);
        const signUrl = (url) => {
          if (window.byted_acrawler?.frontierSign) {
            const signed = window.byted_acrawler.frontierSign(url.pathname + url.search);
            if (signed && signed["X-Bogus"]) url.searchParams.set("X-Bogus", signed["X-Bogus"]);
          }
          return url;
        };
        const norm = (c) => ({
          cid: c.cid ? String(c.cid) : "",
          text: c.text || "",
          create_time: c.create_time || null,
          digg_count: c.digg_count || 0,
          reply_comment_total: c.reply_comment_total || c.reply_comment_count || 0,
          ip_label: c.ip_label || c.ip_label_text || "",
          user: {
            uid: c.user?.uid ? String(c.user.uid) : "",
            sec_uid: c.user?.sec_uid || "",
            nickname: c.user?.nickname || "",
            unique_id: c.user?.unique_id || "",
          },
          raw: c,
        });
        const base = performance.getEntriesByType("resource")
          .map((entry) => entry.name)
          .find((url) => url.includes("/comment/list/") && !url.includes("/comment/list/reply/") && url.includes("aweme_id=${awemeId}")) || "";
        const roots = [];
        const seen = new Set();
        let duplicates = 0;
        let cursor = 0;
        let hasMore = 1;
        let reportedTotal = null;
        let pages = 0;
        while (hasMore && pages < ${args.maxPages}) {
          const url = base ? new URL(base) : new URL("https://www.douyin.com/aweme/v1/web/comment/list/");
          url.searchParams.delete("X-Bogus");
          if (!base) {
            for (const [key, value] of Object.entries({
              device_platform: "webapp",
              aid: "6383",
              channel: "channel_pc_web",
              aweme_id: "${awemeId}",
              item_type: "0",
            })) url.searchParams.set(key, value);
          }
          url.searchParams.set("aweme_id", "${awemeId}");
          url.searchParams.set("cursor", String(cursor));
          url.searchParams.set("count", String(${args.pageSize}));
          signUrl(url);
          const payload = await withTimeout(fetch(url.toString(), {
            credentials: "include",
            headers: { accept: "application/json, text/plain, */*" },
          }).then(async (response) => {
            const text = await response.text();
            try { return JSON.parse(text); }
            catch { return { status_code: -1, status_msg: "json_parse_failed", body_excerpt: text.slice(0, 300) }; }
          }), ${args.requestTimeoutMs});
          if (payload.status_code !== undefined && payload.status_code !== 0) {
            return JSON.stringify({ ok: false, stage: "root_api", payload, roots, reported_total: reportedTotal, pages, cursor, has_more: hasMore });
          }
          reportedTotal = payload.total ?? reportedTotal;
          for (const c of (payload.comments || [])) {
            const row = norm(c);
            if (row.cid && seen.has(row.cid)) {
              duplicates++;
              continue;
            }
            if (row.cid) seen.add(row.cid);
            roots.push(row);
          }
          cursor = payload.cursor;
          hasMore = payload.has_more ? 1 : 0;
          pages++;
          if (!(payload.comments || []).length) break;
          await sleep(${args.delayMs});
        }
        return JSON.stringify({
          ok: true,
          aweme_id: "${awemeId}",
          reported_total: reportedTotal,
          fetched_root_comments: roots.length,
          duplicate_roots_removed: duplicates,
          root_pages: pages,
          has_more: hasMore,
          cursor,
          comments: roots,
        });
      }
    )()`, args.evalTimeoutMs);
    const rootData = JSON.parse(rootJson);
    safeWriteJson(path.join(outDir, "comments-root.json"), rootData);
    if (!rootData.ok) throw new Error(`Root comment fetch failed: ${JSON.stringify(rootData).slice(0, 1000)}`);
    note("root-comments-complete", {
      reported_total: rootData.reported_total,
      root_count: rootData.fetched_root_comments,
      duplicate_roots_removed: rootData.duplicate_roots_removed,
      pages: rootData.root_pages,
    });

    const inlineReplies = [];
    const inlineReplyCountByParent = new Map();
    for (const root of rootData.comments) {
      const items = Array.isArray(root.raw?.reply_comment) ? root.raw.reply_comment : [];
      for (const item of items) {
        inlineReplies.push(normalizeInlineReply(item, root.cid));
      }
      if (items.length) inlineReplyCountByParent.set(root.cid, items.length);
    }
    const rootsWithReplies = rootData.comments.filter((row) => {
      const declared = row.reply_comment_total || 0;
      const inlined = inlineReplyCountByParent.get(row.cid) || 0;
      return declared > inlined;
    });
    const replies = [...inlineReplies];
    const replyErrors = [];
    note("fetching-reply-comments", { roots_with_missing_replies: rootsWithReplies.length, inline_replies: inlineReplies.length });
    for (let i = 0; i < rootsWithReplies.length; i += args.replyBatchSize) {
      const batch = rootsWithReplies.slice(i, i + args.replyBatchSize).map((row) => ({
        cid: row.cid,
        reply_comment_total: row.reply_comment_total,
      }));
      const encoded = Buffer.from(JSON.stringify(batch), "utf8").toString("base64");
      const batchJson = await client.evaluate(sessionId, `(
        async () => {
          const batch = JSON.parse(atob("${encoded}"));
          const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
          const withTimeout = (p, ms) => Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), ms))]);
          const signUrl = (url) => {
            const signed = window.byted_acrawler?.frontierSign
              ? window.byted_acrawler.frontierSign(url.pathname + url.search)
              : null;
            if (signed && signed["X-Bogus"]) url.searchParams.set("X-Bogus", signed["X-Bogus"]);
            return url;
          };
          const norm = (c, parentCid) => ({
            cid: c.cid ? String(c.cid) : "",
            parent_cid: String(parentCid),
            text: c.text || "",
            create_time: c.create_time || null,
            digg_count: c.digg_count || 0,
            ip_label: c.ip_label || c.ip_label_text || "",
            reply_to_reply_id: c.reply_to_reply_id || "",
            user: {
              uid: c.user?.uid ? String(c.user.uid) : "",
              sec_uid: c.user?.sec_uid || "",
              nickname: c.user?.nickname || "",
              unique_id: c.user?.unique_id || "",
            },
            raw: c,
          });
          const replies = [];
          const errors = [];
          for (const item of batch) {
            let cursor = 0;
            let hasMore = 1;
            let pages = 0;
            while (hasMore && pages < 30) {
              const url = new URL("https://www.douyin.com/aweme/v1/web/comment/list/reply/");
              for (const [key, value] of Object.entries({
                device_platform: "webapp",
                aid: "6383",
                channel: "channel_pc_web",
                item_id: "${awemeId}",
                comment_id: item.cid,
                cursor: String(cursor),
                count: String(${args.pageSize}),
              })) url.searchParams.set(key, value);
              signUrl(url);
              try {
                const payload = await withTimeout(fetch(url.toString(), {
                  credentials: "include",
                  headers: { accept: "application/json, text/plain, */*" },
                }).then(async (response) => {
                  const text = await response.text();
                  try { return JSON.parse(text); }
                  catch { return { status_code: -1, status_msg: "json_parse_failed", body_excerpt: text.slice(0, 300) }; }
                }), ${args.requestTimeoutMs});
                if (payload.status_code !== undefined && payload.status_code !== 0) {
                  errors.push({ cid: item.cid, declared: item.reply_comment_total, status_code: payload.status_code, status_msg: payload.status_msg || payload.message || "", body_excerpt: payload.body_excerpt || "" });
                  break;
                }
                for (const reply of (payload.comments || [])) replies.push(norm(reply, item.cid));
                cursor = payload.cursor;
                hasMore = payload.has_more ? 1 : 0;
                pages++;
                if (!(payload.comments || []).length) break;
                await sleep(${args.delayMs});
              } catch (error) {
                errors.push({ cid: item.cid, declared: item.reply_comment_total, error: String(error && error.message || error) });
                break;
              }
            }
          }
          return JSON.stringify({ batch_start: ${i}, batch_count: batch.length, replies, errors });
        }
      )()`, args.evalTimeoutMs);
      const batchData = JSON.parse(batchJson);
      replies.push(...(batchData.replies || []));
      replyErrors.push(...(batchData.errors || []));
      safeWriteJson(path.join(outDir, `reply-batch-${i}.json`), batchData);
      note("reply-batch-complete", {
        batch_start: i,
        batch_count: batchData.batch_count,
        replies: batchData.replies?.length || 0,
        errors: batchData.errors?.length || 0,
      });
      await sleep(args.batchDelayMs);
    }

    const comments = [];
    const seen = new Set();
    for (const root of rootData.comments) {
      if (root.cid && seen.has(root.cid)) continue;
      if (root.cid) seen.add(root.cid);
      comments.push({ type: "root", ...root, parent_cid: null });
    }
    let replyDuplicatesRemoved = 0;
    for (const reply of replies) {
      if (reply.cid && seen.has(reply.cid)) {
        replyDuplicatesRemoved++;
        continue;
      }
      if (reply.cid) seen.add(reply.cid);
      comments.push({ type: "reply", ...reply, reply_comment_total: 0 });
    }

    const all = {
      aweme_id: awemeId,
      video_url: videoUrl,
      source: "Chrome DevToolsActivePort: /comment/list/ plus signed /comment/list/reply/",
      reported_total: rootData.reported_total,
      root_count: rootData.fetched_root_comments,
      root_pages: rootData.root_pages,
      root_duplicates_removed: rootData.duplicate_roots_removed,
      reply_declared_total: rootData.comments.reduce((sum, row) => sum + (row.reply_comment_total || 0), 0),
      inline_replies: inlineReplies.length,
      reply_fetched_raw: replies.length,
      reply_duplicates_removed: replyDuplicatesRemoved,
      total_saved: comments.length,
      reply_errors: replyErrors,
      comments,
    };
    safeWriteJson(path.join(outDir, "comments-all.json"), all);
    writeJsonl(path.join(outDir, "comments-all.jsonl"), comments);
    writeCsv(path.join(outDir, "comments-all.csv"), comments);
    metadata.finished_at = new Date().toISOString();
    metadata.comments = {
      reported_total: all.reported_total,
      root_count: all.root_count,
      reply_declared_total: all.reply_declared_total,
      inline_replies: all.inline_replies,
      reply_fetched_raw: all.reply_fetched_raw,
      reply_duplicates_removed: all.reply_duplicates_removed,
      total_saved: all.total_saved,
      reply_errors: all.reply_errors.length,
    };
    safeWriteJson(path.join(outDir, "metadata.json"), metadata);
    console.log(JSON.stringify(metadata, null, 2));
  } finally {
    if (targetId && !args.keepTab) {
      try {
        await client.closeTarget(targetId);
      } catch {
        // Ignore cleanup errors.
      }
    }
    client.close();
  }
}

main().catch((error) => {
  console.error(`[douyin-cdp] ERROR: ${error.message}`);
  process.exit(1);
});
