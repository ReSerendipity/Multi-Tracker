#!/usr/bin/env node
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";

const PORT = Number(process.env.DOUYIN_CDP_BRIDGE_PORT || 3457);

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
  throw new Error("Could not find Chrome DevToolsActivePort.");
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      const text = Buffer.concat(chunks).toString("utf8");
      if (!text) return resolve({});
      try {
        resolve(JSON.parse(text));
      } catch (error) {
        reject(new Error(`Invalid JSON body: ${error.message}`));
      }
    });
    req.on("error", reject);
  });
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
      if (msg.error) reject(new Error(`CDP error: ${JSON.stringify(msg.error)}`));
      else resolve(msg.result || {});
    });
    ws.addEventListener("close", () => {
      for (const [id, pending] of this.pending.entries()) {
        clearTimeout(pending.timer);
        pending.reject(new Error("Chrome CDP websocket closed"));
        this.pending.delete(id);
      }
    });
  }

  static async connect() {
    const active = readDevToolsActivePort();
    const url = `ws://127.0.0.1:${active.port}${active.wsPath}`;
    const ws = new WebSocket(url);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`WebSocket connect timed out: ${url}`)), 60000);
      ws.addEventListener("open", () => {
        clearTimeout(timer);
        resolve();
      }, { once: true });
      ws.addEventListener("error", (event) => {
        clearTimeout(timer);
        reject(new Error(`WebSocket error: ${event.message || "unknown"}`));
      }, { once: true });
    });
    const cdp = new CDP(ws);
    cdp.active = active;
    return cdp;
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
}

let cdpInstance = null;
let cdpPromise = null;
async function getCdp() {
  if (cdpInstance?.ws.readyState === WebSocket.OPEN) return cdpInstance;
  if (!cdpPromise) {
    cdpPromise = CDP.connect()
      .then((cdp) => {
        cdpInstance = cdp;
        cdpPromise = null;
        return cdp;
      })
      .catch((error) => {
        cdpPromise = null;
        throw error;
      });
  }
  return cdpPromise;
}

function sendJson(res, status, payload) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
    if (req.method === "GET" && url.pathname === "/health") {
      const cdp = await getCdp();
      sendJson(res, 200, {
        ok: true,
        connected: cdp.ws.readyState === WebSocket.OPEN,
        chrome_port: cdp.active?.port,
        devtools_active_port: cdp.active?.file,
      });
      return;
    }
    if (req.method === "POST" && url.pathname === "/new") {
      const body = await readBody(req);
      if (!body.url) throw new Error("Missing url");
      const cdp = await getCdp();
      const created = await cdp.send("Target.createTarget", {
        url: body.url,
        background: body.background ?? true,
      }, null, 30000);
      const attached = await cdp.send("Target.attachToTarget", { targetId: created.targetId, flatten: true }, null, 30000);
      await cdp.send("Runtime.enable", {}, attached.sessionId, 30000);
      sendJson(res, 200, { targetId: created.targetId, sessionId: attached.sessionId });
      return;
    }
    if (req.method === "POST" && url.pathname === "/eval") {
      const body = await readBody(req);
      if (!body.sessionId || !body.expression) throw new Error("Missing sessionId or expression");
      const cdp = await getCdp();
      const timeoutMs = Number(body.timeoutMs || 300000);
      const result = await cdp.send("Runtime.evaluate", {
        expression: body.expression,
        awaitPromise: true,
        returnByValue: true,
        timeout: timeoutMs,
      }, body.sessionId, timeoutMs + 10000);
      if (result.exceptionDetails) {
        const text = result.exceptionDetails.exception?.description || result.exceptionDetails.text || JSON.stringify(result.exceptionDetails);
        sendJson(res, 500, { ok: false, error: text });
        return;
      }
      sendJson(res, 200, { ok: true, value: result.result?.value });
      return;
    }
    if (req.method === "POST" && url.pathname === "/close") {
      const body = await readBody(req);
      if (!body.targetId) throw new Error("Missing targetId");
      const cdp = await getCdp();
      await cdp.send("Target.closeTarget", { targetId: body.targetId }, null, 30000);
      sendJson(res, 200, { ok: true });
      return;
    }
    sendJson(res, 404, { ok: false, error: "Not found" });
  } catch (error) {
    sendJson(res, 500, { ok: false, error: error.message });
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.error(`[douyin-cdp-bridge] listening on http://127.0.0.1:${PORT}`);
  getCdp().then((cdp) => {
    console.error(`[douyin-cdp-bridge] connected to Chrome port ${cdp.active.port}`);
  }).catch((error) => {
    console.error(`[douyin-cdp-bridge] Chrome connection failed: ${error.message}`);
  });
});
