"""
main.py - エントリーポイント
Ink Boss / Ink Inc.

起動コマンド:
    cd ~/InkTools/ink-boss
    pkill -f vite; fuser -k 5173/tcp 5174/tcp 2>/dev/null; sleep 1
    npm run dev --prefix frontend &
    sleep 4
    python3 main.py
"""

import sys

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IME設定：すべてのimport・QApplication生成より前に必須
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from ime import setup_ime
_ime_backend = setup_ime()
print(f"[IME] backend={_ime_backend}", flush=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Chromiumフラグ（QApplication生成前に追加）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_chromium_flags = ["--ozone-platform-hint=auto", "--enable-features=UseOzonePlatform"]
for _flag in _chromium_flags:
    if _flag not in sys.argv:
        sys.argv.append(_flag)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Qt / pywebview
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import webview
import json # ここを追加
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

from config import load_config, save_config
from bridge import ViewBridge
from api    import InkBossAPI
from window import on_shown, get_rect, get_screen_rect
from electron_bridge import ElectronEngine
from updater import check_update, download_and_install, CURRENT_VERSION
from electron_bridge import ElectronEngine

# QApplication
qt_app = QApplication.instance() or QApplication(sys.argv)
icon_path = Path(__file__).parent / "frontend" / "public" / "icon.png"
if icon_path.exists():
    qt_app.setWindowIcon(QIcon(str(icon_path)))

# 設定・ブリッジ
config = load_config()
print(f"[main] Config loaded after load_config(): {json.dumps(config, ensure_ascii=False)}", flush=True)
bridge = ViewBridge(qt_app, config)

# 第15章: Electron 常駐ヘルパー（失敗しても Qt のみで継続）
electron_engine = ElectronEngine()
bridge.electron = electron_engine

# Aide幅（set_aide_widthで更新される）
_aide_width = 0

def _get_aide_width() -> int:
    return _aide_width

def _set_aide_width(val: int) -> None:
    global _aide_width
    _aide_width = val


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ロック画面（ライセンス未認証時）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _check_and_show_update() -> None:
    """アップデートがあればダイアログを表示する"""
    from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
    from PySide6.QtCore import Qt, QThread, Signal

    # バックグラウンドでチェック
    import threading
    result = {}

    def _check():
        result.update(check_update())

    t = threading.Thread(target=_check, daemon=True)
    t.start()
    t.join(timeout=10)  # 最大10秒待つ

    if not result.get("available"):
        return

    latest  = result["latest_version"]
    dl_url  = result["download_url"]
    notes   = result["release_notes"] or "詳細はGitHubをご確認ください。"

    dialog = QDialog()
    dialog.setWindowTitle("Ink Boss アップデート")
    dialog.setMinimumWidth(420)
    dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
    dialog.setStyleSheet("""
        QDialog { background-color: #080810; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; }
        QLabel  { color: white; border: none; background: transparent; }
        QPushButton#updateBtn {
            background: rgba(100,200,255,0.12); border: 1px solid rgba(100,200,255,0.3);
            border-radius: 10px; padding: 12px; color: rgba(100,200,255,0.9);
            font-size: 14px; font-weight: bold;
        }
        QPushButton#updateBtn:hover { background: rgba(100,200,255,0.2); }
        QPushButton#skipBtn {
            background: transparent; border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px; padding: 12px; color: rgba(255,255,255,0.35); font-size: 13px;
        }
        QPushButton#skipBtn:hover { color: rgba(255,255,255,0.6); }
        QProgressBar {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 6px; height: 8px; text-align: center;
        }
        QProgressBar::chunk { background: rgba(100,200,255,0.6); border-radius: 6px; }
    """)
    root = QVBoxLayout(dialog)
    root.setContentsMargins(40, 36, 40, 36)
    root.setSpacing(0)

    title = QLabel("🎉  アップデートがあります")
    title.setStyleSheet("font-size: 16px; font-weight: bold;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root.addWidget(title)
    root.addSpacing(10)

    ver_label = QLabel(f"v{CURRENT_VERSION}  →  v{latest}")
    ver_label.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 13px; font-family: monospace;")
    ver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root.addWidget(ver_label)
    root.addSpacing(16)

    notes_label = QLabel(notes[:200] + ("..." if len(notes) > 200 else ""))
    notes_label.setStyleSheet(
        "color: rgba(255,255,255,0.4); font-size: 12px;"
        "background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07);"
        "border-radius: 8px; padding: 10px 12px;"
    )
    notes_label.setWordWrap(True)
    root.addWidget(notes_label)
    root.addSpacing(20)

    progress = QProgressBar()
    progress.setVisible(False)
    progress.setFixedHeight(8)
    root.addWidget(progress)

    status_label = QLabel("")
    status_label.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 12px;")
    status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root.addWidget(status_label)
    root.addSpacing(16)

    btn_row = QHBoxLayout()
    skip_btn   = QPushButton("後で")
    update_btn = QPushButton("今すぐ更新")
    skip_btn.setObjectName("skipBtn")
    update_btn.setObjectName("updateBtn")
    btn_row.addWidget(skip_btn)
    btn_row.addWidget(update_btn)
    root.addLayout(btn_row)

    skip_btn.clicked.connect(dialog.reject)

    def on_update():
        if not dl_url:
            status_label.setText("ダウンロードURLが見つかりません。GitHubを確認してください。")
            return
        update_btn.setEnabled(False)
        skip_btn.setEnabled(False)
        progress.setVisible(True)
        progress.setRange(0, 100)
        status_label.setText("ダウンロード中...")

        def _progress(dl, total):
            if total > 0:
                pct = int(dl / total * 100)
                progress.setValue(pct)
                status_label.setText(f"ダウンロード中... {pct}%")
            qt_app.processEvents()

        import threading
        def _do():
            ok = download_and_install(dl_url, _progress)
            if ok:
                status_label.setText("✅ インストール完了。再起動してください。")
                progress.setValue(100)
            else:
                status_label.setText("❌ ダウンロードに失敗しました。")
                update_btn.setEnabled(True)
                skip_btn.setEnabled(True)
            qt_app.processEvents()

        threading.Thread(target=_do, daemon=True).start()

    update_btn.clicked.connect(on_update)
    dialog.exec()


def main():
    # ── アップデート確認 ────────────────────────
    _check_and_show_update()

    # ── Electron ヘルパー常駐（第15.4章） ──
    try:
        electron_engine.start()
    except Exception as e:
        print(f"[main] ElectronEngine.start failed (Qt only): {e}", flush=True)

    # ── Ink Boss 起動 ───────────────────────────
    api = InkBossAPI(
        config=config,
        bridge=bridge,
        get_rect_fn=get_rect,
        aide_width_getter=_get_aide_width,
        electron=electron_engine,
        get_screen_rect_fn=get_screen_rect,
    )
    # 終了は bridge シグナル経由で Qt メインスレッド実行
    bridge.set_shutdown_handler(api._shutdown_for_exit)
    _orig_set = api.set_aide_width
    def _set_aide_width_patched(width):
        global _aide_width
        _aide_width = int(width)
        _orig_set(width)
    api.set_aide_width = _set_aide_width_patched

    # Qtアプリケーションのアクティブ状態変更を監視
    def _on_application_state_changed(state):
        # QApplicationは既にインポートされている
        # Qtは既にインポートされている
        # Qt.ApplicationActive は、ウィンドウがフォアグラウンドにある状態
        if state == Qt.ApplicationState.ApplicationActive:
            if electron_engine and electron_engine.is_available() and electron_engine.active_sid:
                print(f"[main] App active. Showing Electron '{electron_engine.active_sid}'.", flush=True)
                # api.show_service は ElectronService 側で show を呼ぶのでこれを使う
                # ただし、api.show_service は bounds の計算も伴うため、Qt側の main_window が active でないとダメ
                # 現状は main_window がまだ生成されていないか、bounds が未計算の場合があるので、
                # ElectronEngine に show_only_sid のようなメソッドを追加する方が確実
                # ただし、今回は応急処置としてダミーのboundsを渡し、ElectronEngine 側で無視させる
                electron_engine.show(electron_engine.active_sid, "", 0, 0, 0, 0) # ダミーのbounds
        # Qt.ApplicationInactive は、ウィンドウがバックグラウンドにある状態
        elif state == Qt.ApplicationState.ApplicationInactive:
            if electron_engine and electron_engine.is_available() and electron_engine.active_sid:
                print(f"[main] App inactive. Hiding all Electron windows.", flush=True)
                electron_engine.hide_all() # 全てのElectronウィンドウを非表示にする

    qt_app.applicationStateChanged.connect(_on_application_state_changed)
    print("[main] applicationStateChanged listener connected.", flush=True)

    # DEBインストール版かどうかを自動判定
    import os, http.server, socketserver, threading, atexit
    _dist_dir = Path(__file__).parent / "frontend" / "dist"
    _httpd = None
    if _dist_dir.exists():
        # ランダムポートでローカルHTTPサーバーを立てる
        # ThreadingMixIn 必須（仕様書）
        class _ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            allow_reuse_address = True
            daemon_threads = True

        os.chdir(str(_dist_dir))
        _handler = http.server.SimpleHTTPRequestHandler
        _handler.log_message = lambda *a: None  # ログ抑制
        _httpd = _ThreadedHTTPServer(("127.0.0.1", 0), _handler)
        _port  = _httpd.server_address[1]
        threading.Thread(target=_httpd.serve_forever, daemon=True).start()
        _url = f"http://127.0.0.1:{_port}/index.html"
    else:
        _url = "http://localhost:5174"
    print(f"[WebView] url={_url}", flush=True)

    # A1: frameless=True → OS タイトルバーなし。操作は React ●●● / TopBar ドラッグ
    window = webview.create_window(
        "Ink Boss",
        url=_url,
        js_api=api,
        width=1280,
        height=850,
        min_size=(800, 600),
        background_color="#080810",
        frameless=True,
        easy_drag=False,
    )
    def _on_shown():
        on_shown(
            window=window,
            bridge=bridge,
            icon_path=icon_path,
            aide_width_getter=_get_aide_width,
        )
        # 自動クローズ（検証用）: INK_BOSS_AUTO_CLOSE_SEC=2 python3 main.py
        # threading.Timer を使う（shown コールバックは Qt メインでないことがある）
        import os as _os
        import threading as _th
        _sec = _os.environ.get("INK_BOSS_AUTO_CLOSE_SEC", "").strip()
        if _sec:
            try:
                delay_s = max(0.5, float(_sec))
            except ValueError:
                delay_s = 2.0
            print(f"[Close] AUTO_CLOSE armed: {delay_s}s (threading.Timer)", flush=True)
            _th.Timer(delay_s, lambda: api.close_window()).start()

    window.events.shown += _on_shown

    # ウィンドウが閉じられたとき（destroy 後）の保険ログ
    def _on_closed():
        print("[Close] webview window closed event", flush=True)

    try:
        window.events.closed += _on_closed
    except Exception:
        pass

    # atexit は「すでに shutdown 済みなら即 return」前提。二重ハング防止。
    def _atexit_shutdown():
        print("[Close] atexit shutdown", flush=True)
        try:
            electron_engine.shutdown(timeout=2.0)
        except Exception as e:
            print(f"[Close] atexit electron: {e}", flush=True)
        try:
            if _httpd is not None:
                _httpd.shutdown()
        except Exception:
            pass

    atexit.register(_atexit_shutdown)

    print("[main] webview.start entering…", flush=True)
    webview.start(gui="qt")
    print("[main] webview.start returned", flush=True)

    # start() が返ったあと、子プロセスや非 daemon スレッドでハングしないよう片付ける
    try:
        electron_engine.shutdown(timeout=2.0)
    except Exception as e:
        print(f"[main] post-start electron shutdown: {e}", flush=True)
    try:
        if _httpd is not None:
            _httpd.shutdown()
    except Exception:
        pass

    print("[main] clean exit path — returning from main()", flush=True)
    # それでも残る場合の最終手段（数百ms以内）
    def _final_exit():
        import time
        time.sleep(0.4)
        print("[main] final os._exit(0)", flush=True)
        os._exit(0)

    threading.Thread(target=_final_exit, daemon=True).start()


if __name__ == "__main__":
    main()
