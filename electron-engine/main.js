/**
 * Ink Boss — Electron Engine Helper (B1: follow overlay, no reparent)
 *
 * - Fixed userData under ~/.config/ink-boss/electron-userdata  → session persistence
 * - partition persist:inkboss-{sid}                             → multi-account
 * - show/hide + setBounds only                                 → no SetParent
 * - HTTP JSON on 127.0.0.1                                      → Python control
 * - stdout: INK_ELECTRON_READY port=<n>
 */

const { app, BrowserWindow, session, shell, Menu, clipboard } = require("electron");
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
// renderer-process-gone後、まだ再読み込みできていないsid。
// isCrashed()相当のAPIはこのElectronバージョンには無いため、
// render-process-goneイベントで自前追跡する（詳細はcreateServiceWindow参照）。
/** @type {Set<string>} */
const crashed = new Set();
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
    // 位置・サイズはQt側からのapplyBounds呼び出しのみで制御する設計
    // （B1: reparentせず毎フレームbounds同期）。resizable未指定だと
    // frame:falseでもOS側のウィンドウ端ドラッグでユーザーが自由に
    // リサイズできてしまい、設計から逸脱する（hide_all()に不具合が
    // 再発した場合、任意サイズに拡大されたこのウィンドウが画面全体を
    // 覆い操作不能になるリスクもある）。
    resizable: false,
    // skipTaskbar（_NET_WM_STATE_SKIP_TASKBAR）だけではBudgie/Mutter系WMで
    // タスクバーに別アイコンが出るのを実機で確認したため、Linux専用の
    // ウィンドウタイプヒントでも「タスクバーに出すべきでない補助ウィンドウ」
    // であることを伝える。
    type: "utility",
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

  // コンストラクタの skipTaskbar オプションだけでは、Linuxの一部の
  // ウィンドウマネージャー（Budgie/Mutter等）で _NET_WM_STATE_SKIP_TASKBAR
  // が実際には付与されないことを実機で確認したため、明示的にも呼ぶ。
  try {
    win.setSkipTaskbar(true);
  } catch (_) {}

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

  // 【デバッグ専用・調査完了後に削除】IME(fcitx5)不具合の切り分け用。
  // 診断のために外部ターミナルへ切り替えると、Ink Boss自身の「フォーカスが
  // 外れたらElectronを隠す」仕組みが働いてしまい、検証中のウィンドウの表示
  // 状態が変わってしまう（＝診断行為自体が症状を変えてしまう）ため、
  // ウィンドウ切り替えなしで診断情報を取れるようにする。
  // globalShortcutではなくbefore-input-eventにしているのは、システム全体で
  // F12を奪うと他アプリのDevTools等と衝突するため、「このElectronウィンドウが
  // 実際にフォーカスされている時だけ」に限定するため。
  win.webContents.on("before-input-event", (event, input) => {
    if (input.type === "keyDown" && input.key === "F12" && !input.control && !input.alt && !input.meta) {
      event.preventDefault();
      win.webContents
        .executeJavaScript(
          "(() => { const e = document.activeElement; if (!e) return 'null'; " +
          "return e.tagName + (e.id ? '#'+e.id : '') + " +
          "' isContentEditable=' + e.isContentEditable + " +
          "' hasFocus=' + document.hasFocus(); })()"
        )
        .then((info) => {
          process.stdout.write(`INK_ELECTRON_IME_DEBUG ${sid} ${info}\n`);
        })
        .catch((err) => {
          process.stdout.write(`INK_ELECTRON_IME_DEBUG ${sid} (JS取得失敗:${err})\n`);
        });
    }
  });

  // ページ内右クリックメニュー。ElectronはQtWebEngineと違いデフォルトの
  // ネイティブコンテキストメニューを持たないため、標準的なブラウザ項目
  // （戻る/進む/再読み込み、選択時のコピー、入力欄でのカット/コピー/
  // 貼り付け等）を自前で組み立てたうえで、末尾に「Ink Bossに追加」を
  // 追加する。クリック時は既存のstdoutマーカー行の仕組み
  // （INK_ELECTRON_READY と同様のパターン）でPython側へURLを伝える。
  // renderer-process-gone（クラッシュ・GPUプロセス絡みの異常終了等）への対応。
  // 以前はこのイベントを一切監視しておらず、クラッシュしたウィンドウは
  // BrowserWindow自体は生きたまま（windows Mapにも残ったまま）中身の
  // rendererだけが失われ、以後どの操作（クリック/ダブルクリック/右クリック
  // 「復帰」）を試しても画面が真っ暗のまま戻らない不具合があった
  // （showService/wakeServiceのどちらもwin.isDestroyed()しか見ておらず、
  // 「windowはあるがrendererは死んでいる」状態を検知できなかったため。
  // 実機でrendererを意図的にクラッシュさせて再現・確認済み）。
  // 表示中なら即座に自前でloadURLして自己修復し、非表示中でも
  // crashedフラグを立てておき、次にshow/wakeされた際に必ず
  // 再読み込みしてから表示するようにする。
  win.webContents.on("render-process-gone", (_event, details) => {
    console.error(
      `[electron-engine] render-process-gone sid=${sid} reason=${details.reason} exitCode=${details.exitCode}`
    );
    crashed.add(sid);
    if (activeId === sid && win.isVisible()) {
      const target = urls.get(sid) || "about:blank";
      console.error(`[electron-engine] sid=${sid} was visible — auto-recovering (loadURL ${target})`);
      crashed.delete(sid);
      try {
        win.loadURL(target);
      } catch (_) {}
    }
  });

  win.webContents.on("context-menu", (_event, params) => {
    const nav = win.webContents.navigationHistory;
    const template = [];
    if (params.isEditable) {
      template.push(
        { label: "切り取り", role: "cut", enabled: params.editFlags.canCut },
        { label: "コピー", role: "copy", enabled: params.editFlags.canCopy },
        { label: "貼り付け", role: "paste", enabled: params.editFlags.canPaste },
        { label: "すべて選択", role: "selectAll" },
        { type: "separator" },
      );
    } else if (params.selectionText) {
      template.push({ label: "コピー", role: "copy" }, { type: "separator" });
    }
    template.push(
      { label: "戻る", enabled: nav.canGoBack(), click: () => nav.goBack() },
      { label: "進む", enabled: nav.canGoForward(), click: () => nav.goForward() },
      { label: "再読み込み", click: () => win.webContents.reload() },
    );
    if (params.linkURL) {
      template.push(
        { type: "separator" },
        { label: "リンクのURLをコピー", click: () => clipboard.writeText(params.linkURL) },
      );
    }
    template.push(
      { type: "separator" },
      {
        label: "Ink Bossに追加",
        click: () => {
          process.stdout.write(`INK_ELECTRON_ADD_SERVICE ${params.pageURL}\n`);
        },
      },
    );
    Menu.buildFromTemplate(template).popup({ window: win });
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

  // show_service 自体を冪等にする。
  // Electronの BrowserWindow.show() は公式ドキュメント上も
  // 「表示してフォーカスを与える」処理であり、既に表示・アクティブ済みの
  // ウィンドウに対して再度呼ぶだけでOS/WM側のフォーカスイベントが
  // 再発火しうる（特に type:'utility' + focusable:true は、WM自身が
  // map時に自動でフォーカスを付与することがあり、Electron側の
  // isFocused() チェックでは検知できない）。
  // 対象sidが既にactiveかつ可視状態なら、show()/focus() 自体を
  // 呼ばずに座標更新だけ行う。
  const alreadyActive = activeId === sid && win.isVisible() && !hibernated.has(sid) && !crashed.has(sid);

  if (!alreadyActive) {
    hideAllExcept(sid);
  }
  applyBounds(win, bounds);

  if (hibernated.has(sid)) {
    const url = urls.get(sid) || "about:blank";
    if (url && url !== "about:blank") {
      win.loadURL(url);
      hibernated.delete(sid);
    }
  } else if (crashed.has(sid)) {
    // renderer-process-gone後、非表示中だったために自動復帰できず
    // 持ち越されたクラッシュ。表示前に必ず読み直す。
    const url = urls.get(sid) || "about:blank";
    console.error(`[electron-engine] sid=${sid} recovering from previous crash before show (loadURL ${url})`);
    try {
      win.loadURL(url);
    } catch (_) {}
  }
  crashed.delete(sid);

  if (!alreadyActive) {
    win.show();
    // 一部WMは skipTaskbar をマップ前に設定しても無視するため、
    // 表示（マップ）後にも再度呼んで確実にタスクバーへ出さないようにする。
    try {
      win.setSkipTaskbar(true);
    } catch (_) {}
    if (!win.isFocused()) {
      win.focus();
    }
    win.setFullScreen(false);
  }
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
  crashed.delete(sid);  // about:blankへのloadURLで既にrendererは回復済み
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
  crashed.delete(sid);
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
  crashed.delete(sid);
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
        crashed: [...crashed],
        userData: USER_DATA,
      });
    }
    if (req.method === "GET" && route === "/hibernated") {
      // ids: 明示的に休止扱い（生成済みだが未ロード）のsid一覧。
      // awake: 実際にウィンドウが生成され、ロード済み（休止ではない）のsid一覧。
      // 起動時に一度もcreate/showされていないサービス（Python側の
      // _init_viewsはElectronサービスを起動時に作らない設計）は、
      // どちらにも含まれない ＝ Python側では「休止扱い」として
      // 解釈する（get_hibernated_idsのコメント参照）。
      const awake = [...windows.keys()].filter((sid) => !hibernated.has(sid));
      // audible: 現在音声を出力中のsid（自動休止の除外判定に使う）
      const audible = awake.filter((sid) => {
        const w = windows.get(sid);
        return w && !w.isDestroyed() && w.webContents.isCurrentlyAudible();
      });
      return sendJson(res, 200, { ok: true, ids: [...hibernated], awake, audible });
    }
    if (req.method === "GET" && route === "/pageText") {
      // Ink Aide（AIによるページ要約）用。Qt側（bridge.pyのpage_text_cache）
      // はloadFinished/urlChanged時にPython側からrunJavaScriptして能動的に
      // キャッシュしているが、Electron側には同等の仕組みがなかったため、
      // Electronホストのサービス（Ecosia等）ではInk Aideがページ内容を
      // 一切取得できていなかった（実機報告で発見）。ここでは対象sidの
      // webContentsへその場でexecuteJavaScriptし、document.body.innerText
      // を返すことで、Qt側と同じ「ページの可視テキスト全文」を渡す。
      const sid = u.searchParams.get("sid");
      if (!sid) return sendJson(res, 400, { ok: false, error: "sid_required" });
      const win = windows.get(sid);
      if (!win || win.isDestroyed()) return sendJson(res, 404, { ok: false, error: "not_found" });
      try {
        const text = await win.webContents.executeJavaScript(
          "document.body ? document.body.innerText : ''"
        );
        return sendJson(res, 200, { ok: true, text: String(text || "") });
      } catch (err) {
        return sendJson(res, 500, {
          ok: false,
          error: String(err && err.message ? err.message : err),
        });
      }
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
      console.error(`[electron-engine] [SHUTDOWN] ${Date.now()} /shutdown received — flushing sessions then quitting`);
      app.isQuitting = true;

      const FLUSH_TIMEOUT_MS = 2000;

      // 1サービス分のセッションをディスクへflush。
      // flushStorageData() はコールバック/Promiseを返さない fire-and-forget
      // API のため待てない。cookies.flushStore() はPromiseを返すのでそちらを
      // 待ち、両方合わせて FLUSH_TIMEOUT_MS でタイムアウトさせる
      // （①の教訓通り、無限待機は避ける）。
      const flushWindow = (sid, win) =>
        new Promise((resolve) => {
          let done = false;
          const finish = () => {
            if (done) return;
            done = true;
            resolve();
          };
          const timer = setTimeout(() => {
            console.error(`[electron-engine] [SHUTDOWN] flush timeout sid=${sid}`);
            finish();
          }, FLUSH_TIMEOUT_MS);
          try {
            const ses = win.webContents.session;
            try {
              ses.flushStorageData();
            } catch (e) {
              console.error(`[electron-engine] [SHUTDOWN] flushStorageData error sid=${sid}: ${e}`);
            }
            Promise.resolve(ses.cookies.flushStore())
              .then(() => {
                console.error(`[electron-engine] [SHUTDOWN] flush complete sid=${sid}`);
              })
              .catch((e) => {
                console.error(`[electron-engine] [SHUTDOWN] cookies.flushStore error sid=${sid}: ${e}`);
              })
              .finally(() => {
                clearTimeout(timer);
                finish();
              });
          } catch (e) {
            console.error(`[electron-engine] [SHUTDOWN] flush setup error sid=${sid}: ${e}`);
            clearTimeout(timer);
            finish();
          }
        });

      const entries = Array.from(windows.entries()).filter(
        ([, win]) => win && !win.isDestroyed()
      );

      Promise.all(entries.map(([sid, win]) => flushWindow(sid, win)))
        .then(() => {
          console.error(`[electron-engine] [SHUTDOWN] all sessions flushed (or timed out) — closing windows`);
        })
        .finally(() => {
          for (const [sid, win] of entries) {
            try {
              if (win && !win.isDestroyed()) {
                win.close(); // destroy() ではなく通常の終了フローを通す
              }
            } catch (e) {
              console.error(`[electron-engine] [SHUTDOWN] close error sid=${sid}: ${e}`);
            }
          }
          windows.clear();
          try {
            if (server) server.close();
          } catch (_) {}
          setTimeout(() => {
            console.error(`[electron-engine] [SHUTDOWN] ${Date.now()} calling app.quit()`);
            try {
              app.quit();
            } catch (_) {
              process.exit(0);
            }
          }, 50);
        });

      // 最終保険: flush・close・quitのどこがハングしても必ず終了する
      setTimeout(() => {
        console.error(`[electron-engine] [SHUTDOWN] ${Date.now()} HARD process.exit(0) (safety deadline)`);
        process.exit(0);
      }, FLUSH_TIMEOUT_MS + 1500);
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
  console.error(`[electron-engine] [DIAG-SHUTDOWN] ${Date.now()} before-quit event fired`);
  app.isQuitting = true;
});
app.on("will-quit", () => {
  console.error(`[electron-engine] [DIAG-SHUTDOWN] ${Date.now()} will-quit event fired`);
});
app.on("quit", () => {
  console.error(`[electron-engine] [DIAG-SHUTDOWN] ${Date.now()} quit event fired`);
});
process.on("exit", (code) => {
  console.error(`[electron-engine] [DIAG-SHUTDOWN] ${Date.now()} process 'exit' event, code=${code}`);
});

process.on("SIGTERM", () => {
  app.isQuitting = true;
  app.quit();
});
process.on("SIGINT", () => {
  app.isQuitting = true;
  app.quit();
});
