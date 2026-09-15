/**
 * Ink Boss — Electron Engine Helper (B1: follow overlay, no reparent)
 *
 * - Fixed userData under ~/.config/ink-boss/electron-userdata  → session persistence
 * - partition persist:inkboss-{sid}                             → multi-account
 * - show/hide + setBounds only                                 → no SetParent
 * - HTTP JSON on 127.0.0.1                                      → Python control
 * - stdout: INK_ELECTRON_READY port=<n>
 */

const { app, BrowserWindow, session, shell } = require("electron");
const http = require("http");
const path = require("path");
const fs = require("fs");
const os = require("os");

// MUST be before ready — stable path for Discord/token disk flush
const USER_DATA = path.join(os.homedir(), ".config", "ink-boss", "electron-userdata");
fs.mkdirSync(USER_DATA, { recursive: true });
app.setPath("userData", USER_DATA);

// 同一 userData を複数プロセスが同時に掴むと Cookies/Login Data の
// SQLiteが壊れうる（セッション消失の一因になりうる）。二重起動防止。
if (!app.requestSingleInstanceLock()) {
  console.error("[electron-engine] another instance already holds userData — exiting");
  app.quit();
  process.exit(0);
}

/** @type {Map<string, BrowserWindow>} */
const windows = new Map();
/** @type {Set<string>} */
const hibernated = new Set();
/** @type {Map<string, string>} */
const urls = new Map();
/** @type {string | null} */
let activeId = null;
/** @type {http.Server | null} */
let server = null;

function spoofSession(ses) {
  const chromeVersion = process.versions.chrome || "124.0.0.0";
  const major = chromeVersion.split(".")[0];
  const ua =
    `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ` +
    `(KHTML, like Gecko) Chrome/${chromeVersion} Safari/537.36`;
  try {
    ses.setUserAgent(ua);
  } catch (_) {}
  try {
    ses.webRequest.onBeforeSendHeaders((details, callback) => {
      details.requestHeaders["Sec-CH-UA"] =
        `"Not)A;Brand";v="99", "Google Chrome";v="${major}", "Chromium";v="${major}"`;
      details.requestHeaders["Sec-CH-UA-Mobile"] = "?0";
      details.requestHeaders["Sec-CH-UA-Platform"] = '"Linux"';
      callback({ requestHeaders: details.requestHeaders });
    });
  } catch (_) {}
  return ua;
}

function createServiceWindow(sid, url, opts = {}) {
  if (windows.has(sid) && !windows.get(sid).isDestroyed()) {
    return windows.get(sid);
  }

  const partition = `persist:inkboss-${sid}`;
  const ses = session.fromPartition(partition, { cache: true });
  const ua = spoofSession(ses);

  const win = new BrowserWindow({
    show: false,
    frame: false,
    backgroundColor: "#080810",
    skipTaskbar: true,
    autoHideMenuBar: true,
    focusable: true,
    alwaysOnTop: true,
    wmClass: "InkBoss",
    fullscreen: false,
    width: 800,
    height: 600,
    webPreferences: {
      partition,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: true,
    },
  });

  try {
    win.webContents.setUserAgent(ua);
  } catch (_) {}

  win.webContents.setWindowOpenHandler(({ url: openUrl }) => {
    try {
      const u = new URL(openUrl);
      if (u.protocol === "http:" || u.protocol === "https:") {
        win.webContents.loadURL(openUrl);
        return { action: "deny" };
      }
    } catch (_) {}
    shell.openExternal(openUrl).catch(() => {});
    return { action: "deny" };
  });

  win.on("close", (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      win.hide();
      if (activeId === sid) activeId = null;
    }
  });

  urls.set(sid, url || "about:blank");
  if (opts.muted) win.webContents.setAudioMuted(true);

  if (opts.loadNow && url && url !== "about:blank") {
    win.loadURL(url);
    hibernated.delete(sid);
  } else {
    win.loadURL("about:blank");
    hibernated.add(sid);
  }

  windows.set(sid, win);
  console.error(`[electron-engine] created sid=${sid} partition=${partition}`);
  return win;
}

function hideAllExcept(keepSid = null) {
  for (const [sid, win] of windows) {
    if (sid === keepSid) continue;
    if (win && !win.isDestroyed()) win.hide();
  }
  if (!keepSid) activeId = null;
}

function applyBounds(win, bounds) {
  const { x, y, w, h } = bounds || {};
  if (
    Number.isFinite(x) &&
    Number.isFinite(y) &&
    Number.isFinite(w) &&
    Number.isFinite(h) &&
    w > 1 &&
    h > 1
  ) {
    win.setBounds({
      x: Math.round(x),
      y: Math.round(y),
      width: Math.round(w),
      height: Math.round(h),
    });
  }
}

function showService(sid, bounds) {
  const win = windows.get(sid);
  if (!win || win.isDestroyed()) return { ok: false, error: "not_found" };

  hideAllExcept(sid);
  applyBounds(win, bounds);

  if (hibernated.has(sid)) {
    const url = urls.get(sid) || "about:blank";
    if (url && url !== "about:blank") {
      win.loadURL(url);
      hibernated.delete(sid);
    }
  }

  win.show();
  win.focus();
  win.setFullScreen(false);
  activeId = sid;
  return { ok: true, sid };
}

function setBounds(sid, bounds) {
  const win = windows.get(sid);
  if (!win || win.isDestroyed()) return { ok: false, error: "not_found" };
  applyBounds(win, bounds);
  return { ok: true };
}

function hibernateService(sid) {
  const win = windows.get(sid);
  if (!win || win.isDestroyed()) return { ok: false, error: "not_found" };
  try {
    win.loadURL("about:blank");
  } catch (_) {}
  hibernated.add(sid);
  win.hide();
  if (activeId === sid) activeId = null;
  return { ok: true };
}

function wakeService(sid, url) {
  const win = windows.get(sid);
  if (!win || win.isDestroyed()) return { ok: false, error: "not_found" };
  if (url) urls.set(sid, url);
  const target = urls.get(sid) || url || "about:blank";
  try {
    win.loadURL(target);
  } catch (_) {}
  hibernated.delete(sid);
  return { ok: true };
}

function removeService(sid) {
  const win = windows.get(sid);
  if (win && !win.isDestroyed()) {
    try {
      win.destroy();
    } catch (_) {}
  }
  windows.delete(sid);
  urls.delete(sid);
  hibernated.delete(sid);
  if (activeId === sid) activeId = null;
  return { ok: true };
}

function reloadService(sid) {
  const win = windows.get(sid);
  if (!win || win.isDestroyed() || hibernated.has(sid)) {
    return { ok: false, error: "not_found_or_hibernated" };
  }
  try {
    win.webContents.reload();
  } catch (_) {}
  return { ok: true };
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      if (!raw) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch (e) {
        reject(e);
      }
    });
    req.on("error", reject);
  });
}

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

async function handleRequest(req, res) {
  const remote = req.socket.remoteAddress;
  if (remote && remote !== "127.0.0.1" && remote !== "::1" && remote !== ":ffff:127.0.0.1") {
    return sendJson(res, 403, { ok: false, error: "forbidden" });
  }

  const u = new URL(req.url || "/", "http://127.0.0.1");
  const route = u.pathname;
  let body = {};
  if (req.method === "POST") {
    try {
      body = await readBody(req);
    } catch {
      return sendJson(res, 400, { ok: false, error: "invalid_json" });
    }
  }

  try {
    if (req.method === "GET" && route === "/health") {
      return sendJson(res, 200, {
        ok: true,
        activeId,
        windows: [...windows.keys()],
        hibernated: [...hibernated],
        userData: USER_DATA,
      });
    }
    if (req.method === "GET" && route === "/hibernated") {
      return sendJson(res, 200, { ok: true, ids: [...hibernated] });
    }
    if (req.method === "POST" && route === "/create") {
      const { sid, url: svcUrl, muted, loadNow } = body;
      if (!sid) return sendJson(res, 400, { ok: false, error: "sid_required" });
      createServiceWindow(sid, svcUrl || "about:blank", {
        muted: !!muted,
        loadNow: !!loadNow,
      });
      if (svcUrl) urls.set(sid, svcUrl);
      return sendJson(res, 200, { ok: true, sid });
    }
    if (req.method === "POST" && route === "/show") {
      const { sid, x, y, w, h, url: svcUrl } = body;
      if (!sid) return sendJson(res, 400, { ok: false, error: "sid_required" });
      if (!windows.has(sid) || windows.get(sid).isDestroyed()) {
        createServiceWindow(sid, svcUrl || urls.get(sid) || "about:blank", {
          loadNow: true,
        });
      } else if (svcUrl) {
        urls.set(sid, svcUrl);
      }
      return sendJson(res, 200, showService(sid, { x, y, w, h }));
    }
    if (req.method === "POST" && route === "/hide") {
      const { sid } = body;
      if (sid) {
        const win = windows.get(sid);
        if (win && !win.isDestroyed()) win.hide();
        if (activeId === sid) activeId = null;
      } else {
        hideAllExcept(null);
      }
      return sendJson(res, 200, { ok: true });
    }
    if (req.method === "POST" && route === "/hide_all") {
      hideAllExcept(null);
      return sendJson(res, 200, { ok: true });
    }
    if (req.method === "POST" && route === "/bounds") {
      return sendJson(res, 200, setBounds(body.sid, body));
    }
    if (req.method === "POST" && route === "/hibernate") {
      return sendJson(res, 200, hibernateService(body.sid));
    }
    if (req.method === "POST" && route === "/wake") {
      return sendJson(res, 200, wakeService(body.sid, body.url));
    }
    if (req.method === "POST" && route === "/reload") {
      return sendJson(res, 200, reloadService(body.sid));
    }
    if (req.method === "POST" && route === "/setAlwaysOnTop") {
      const { sid, onTop } = body;
      const win = windows.get(sid);
      if (!win || win.isDestroyed()) return sendJson(res, 400, { ok: false, error: "not_found" });
      win.setAlwaysOnTop(!!onTop);
      return sendJson(res, 200, { ok: true });
    }
    if (req.method === "POST" && route === "/remove") {
      return sendJson(res, 200, removeService(body.sid));
    }
    if (req.method === "POST" && route === "/shutdown") {
      // 先にレスポンスを返して Python 側をブロックさせない
      sendJson(res, 200, { ok: true });
      console.error("[electron-engine] /shutdown received — quitting");
      app.isQuitting = true;
      // セッション flush: ビュー破棄 → 少し待って quit
      try {
        for (const [, win] of windows) {
          try {
            if (win && !win.isDestroyed()) win.destroy();
          } catch (_) {}
        }
        windows.clear();
      } catch (_) {}
      // サーバーも閉じる
      try {
        if (server) server.close();
      } catch (_) {}
      // 短時間で quit。ハングしても親が kill する
      setTimeout(() => {
        try {
          app.quit();
        } catch (_) {
          process.exit(0);
        }
      }, 100);
      // 最終保険
      setTimeout(() => process.exit(0), 1500);
      return;
    }
    return sendJson(res, 404, { ok: false, error: "not_found" });
  } catch (err) {
    console.error("[electron-engine] handler error", err);
    return sendJson(res, 500, {
      ok: false,
      error: String(err && err.message ? err.message : err),
    });
  }
}

function startServer() {
  const preferred = parseInt(process.env.INK_ELECTRON_PORT || "0", 10) || 0;
  server = http.createServer((req, res) => {
    handleRequest(req, res);
  });
  server.listen(preferred, "127.0.0.1", () => {
    const addr = server.address();
    const port = typeof addr === "object" && addr ? addr.port : preferred;
    process.stdout.write(`INK_ELECTRON_READY port=${port}\n`);
    console.error(`[electron-engine] listening 127.0.0.1:${port} userData=${USER_DATA}`);
  });
}

app.whenReady().then(() => startServer());

app.on("window-all-closed", (e) => {
  /* keep alive until /shutdown */
});

app.on("before-quit", () => {
  app.isQuitting = true;
});

process.on("SIGTERM", () => {
  app.isQuitting = true;
  app.quit();
});
process.on("SIGINT", () => {
  app.isQuitting = true;
  app.quit();
});
