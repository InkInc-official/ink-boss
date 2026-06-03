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
import platform as _platform
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IME設定：すべてのimport・QApplication生成より前に必須
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from ime import setup_ime
_ime_backend = setup_ime()
print(f"[IME] backend={_ime_backend}", flush=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Linux専用: Chromiumフラグ（QApplication生成前に追加）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if _platform.system() != "Windows":
    _chromium_flags = ["--ozone-platform-hint=auto", "--enable-features=UseOzonePlatform"]
    for _flag in _chromium_flags:
        if _flag not in sys.argv:
            sys.argv.append(_flag)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Qt / pywebview
# Windows: QApplicationはpywebviewに任せる（競合防止）
# Linux:   QApplicationを先に作る（QtWebEngine必須）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import webview

_IS_WINDOWS = _platform.system() == "Windows"

if _IS_WINDOWS:
    # Windowsでは QApplication を作らない
    # pywebview が EdgeChromium(WebView2) + 独自ループで管理する
    qt_app = None
else:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    qt_app = QApplication.instance() or QApplication(sys.argv)
    _icon_path_early = Path(__file__).parent / "frontend" / "public" / "icon.png"
    if _icon_path_early.exists():
        qt_app.setWindowIcon(QIcon(str(_icon_path_early)))

from config import load_config, save_config
from bridge import ViewBridge
from api    import InkBossAPI
from window import on_shown, get_rect
from auth   import verify, save_license_key_to_config
from updater import check_update, download_and_install, CURRENT_VERSION

icon_path = Path(__file__).parent / "frontend" / "public" / "icon.png"

# 設定・ブリッジ
config = load_config()
bridge = ViewBridge(qt_app, config)

# Aide幅（set_aide_widthで更新される）
_aide_width = 0

def _get_aide_width() -> int:
    return _aide_width


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# アップデート確認（Windows: pywebviewダイアログ / Linux: Qt）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _check_and_show_update() -> None:
    import threading, time
    result = {}
    done = threading.Event()

    def _check():
        try:
            result.update(check_update())
        except Exception as e:
            print(f"[Updater] check failed: {e}", flush=True)
        finally:
            done.set()

    t = threading.Thread(target=_check, daemon=True)
    t.start()

    # 最大8秒待機（Qtがある場合はprocessEventsで回す）
    import time
    deadline = time.time() + 8.0
    while not done.is_set() and time.time() < deadline:
        if qt_app:
            qt_app.processEvents()
        time.sleep(0.05)

    if not result.get("available"):
        return

    latest = result["latest_version"]
    notes  = result.get("release_notes") or "詳細はGitHubをご確認ください。"

    if _IS_WINDOWS:
        # pywebviewのネイティブダイアログ（QApplicationなし環境用）
        if webview.windows:
            answer = webview.windows[0].create_confirmation_dialog(
                "アップデートあり",
                f"v{CURRENT_VERSION} → v{latest}\n\n今すぐ更新しますか？"
            )
            if answer and result.get("download_url"):
                download_and_install(result["download_url"], lambda *a: None)
    else:
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
        from PySide6.QtCore import Qt
        dl_url = result.get("download_url")
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
        root.addSpacing(20)
        btn_row = QHBoxLayout()
        skip_btn   = QPushButton("後で");   skip_btn.setObjectName("skipBtn")
        update_btn = QPushButton("今すぐ更新"); update_btn.setObjectName("updateBtn")
        btn_row.addWidget(skip_btn); btn_row.addWidget(update_btn)
        root.addLayout(btn_row)
        skip_btn.clicked.connect(dialog.reject)
        update_btn.clicked.connect(lambda: (download_and_install(dl_url, lambda *a: None), dialog.accept()) if dl_url else None)
        dialog.exec()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ロック画面（ライセンス未認証時）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _show_lock_screen(reason: str) -> None:
    if _IS_WINDOWS:
        # Windowsでは pywebview ウィンドウ起動前なので tkinter で代替
        try:
            import tkinter as tk
            from tkinter import messagebox, simpledialog
            root = tk.Tk(); root.withdraw()
            REASON_MSG = {
                "invalid_key":   "キーが無効です。",
                "inactive":      "このライセンスは無効化されています。",
                "machine_limit": "登録台数の上限（2台）に達しています。",
                "offline":       "サーバーに接続できませんでした。",
            }
            msg = REASON_MSG.get(reason, "")
            key = simpledialog.askstring(
                "Ink Boss - ライセンス認証",
                f"{msg}\nライセンスキーを入力してください（INK-XXXX-XXXX-XXXX）：",
                parent=root
            )
            if key:
                result = verify(key.strip())
                if result["valid"]:
                    save_license_key_to_config(config, key.strip())
                    save_config(config)
                    messagebox.showinfo("認証成功", "認証しました。再起動します。")
                    import subprocess
                    subprocess.Popen([sys.executable] + sys.argv)
                else:
                    messagebox.showerror("認証失敗", "キーが無効です。")
            root.destroy()
        except Exception as e:
            print(f"[LockScreen] tkinter error: {e}", flush=True)
    else:
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont
        import subprocess
        REASON_MSG = {
            "invalid_key":   "キーが無効です。正しいキーを入力してください。",
            "inactive":      "このライセンスは無効化されています。\n所長にお問い合わせください。",
            "machine_limit": "登録台数の上限（2台）に達しています。\n所長にお問い合わせください。",
            "offline":       "サーバーに接続できませんでした。\nネットワーク接続を確認してください。",
            "error":         "認証中にエラーが発生しました。",
        }
        msg = REASON_MSG.get(reason, "")
        dialog = QDialog()
        dialog.setWindowTitle("Ink Boss")
        dialog.setMinimumWidth(460)
        dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dialog.setStyleSheet("""
            QDialog { background-color: #080810; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; }
            QLabel { color: white; border: none; background: transparent; }
            QLineEdit {
                background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.15);
                border-radius: 10px; padding: 14px 16px; color: white; font-size: 15px; letter-spacing: 2px;
            }
            QLineEdit:focus { border: 1px solid rgba(255,255,255,0.35); }
            QPushButton#authBtn {
                background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.2);
                border-radius: 10px; padding: 14px; color: white; font-size: 14px; font-weight: bold;
            }
            QPushButton#authBtn:hover { background: rgba(255,255,255,0.13); }
        """)
        root = QVBoxLayout(dialog)
        root.setContentsMargins(48, 44, 48, 44); root.setSpacing(0)
        title = QLabel("🖊️  Ink Boss")
        title.setFont(QFont("monospace", 22, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title); root.addSpacing(12)
        desc = QLabel("ご利用にはライセンスキーが必要です。\n所長より発行されたキーを入力してください。")
        desc.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 13px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter); desc.setWordWrap(True)
        root.addWidget(desc); root.addSpacing(24)
        err_label = QLabel(msg)
        err_label.setStyleSheet("color: rgba(240,90,90,0.9); font-size: 12px; background: rgba(240,90,90,0.1); border: 1px solid rgba(240,90,90,0.3); border-radius: 8px; padding: 10px 14px;")
        err_label.setAlignment(Qt.AlignmentFlag.AlignCenter); err_label.setWordWrap(True)
        err_label.setVisible(bool(msg))
        root.addWidget(err_label)
        if msg: root.addSpacing(16)
        key_input = QLineEdit()
        key_input.setPlaceholderText("INK-XXXX-XXXX-XXXX")
        key_input.setText(config.get("license_key", ""))
        key_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(key_input); root.addSpacing(20)
        auth_btn = QPushButton("認証する"); auth_btn.setObjectName("authBtn")
        root.addWidget(auth_btn); root.addSpacing(10)
        status_label = QLabel("")
        status_label.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 12px;")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(status_label)
        def on_auth():
            key = key_input.text().strip()
            if not key:
                err_label.setText("キーを入力してください"); err_label.setVisible(True); return
            auth_btn.setEnabled(False); status_label.setText("認証中..."); qt_app.processEvents()
            result = verify(key)
            if result["valid"]:
                save_license_key_to_config(config, key); save_config(config)
                status_label.setText("✅ 認証成功。Ink Bossを起動します..."); qt_app.processEvents()
                dialog.accept()
                subprocess.Popen([sys.executable] + sys.argv)
            else:
                auth_btn.setEnabled(True)
                reason_map = {"invalid_key": "キーが無効です。", "inactive": "無効化されています。", "machine_limit": "台数上限です。", "offline": "接続できません。"}
                err_label.setText(reason_map.get(result["reason"], "認証に失敗しました。")); err_label.setVisible(True); status_label.setText("")
        auth_btn.clicked.connect(on_auth); key_input.returnPressed.connect(on_auth)
        dialog.exec()


def main():
    import threading, time

    # ── ライセンス認証 ──────────────────────────
    license_key = config.get("license_key", "").strip()
    auth_result: dict = {"valid": False, "reason": "no_key", "from_cache": False}

    if license_key:
        done = threading.Event()
        def _verify():
            auth_result.update(verify(license_key))
            done.set()
        threading.Thread(target=_verify, daemon=True).start()
        deadline = time.time() + 12.0
        while not done.is_set() and time.time() < deadline:
            if qt_app:
                qt_app.processEvents()
            time.sleep(0.05)
        if not done.is_set():
            auth_result.update({"valid": False, "reason": "offline"})

    if not auth_result["valid"]:
        _show_lock_screen(auth_result["reason"])
        return

    print(f"[Auth] 認証OK (reason={auth_result['reason']}, cache={auth_result['from_cache']})", flush=True)

    # ── アップデート確認（Windowsはwebview起動後に行う）──
    if not _IS_WINDOWS:
        _check_and_show_update()

    # ── Ink Boss 起動 ───────────────────────────
    api = InkBossAPI(
        config=config,
        bridge=bridge,
        get_rect_fn=get_rect,
        aide_width_getter=_get_aide_width,
    )
    _orig_set = api.set_aide_width
    def _set_aide_width_patched(width):
        global _aide_width
        _aide_width = int(width)
        _orig_set(width)
    api.set_aide_width = _set_aide_width_patched

    # ── ローカルHTTPサーバー（マルチスレッド）──────
    import os, http.server, socketserver
    _dist_dir = Path(__file__).parent / "frontend" / "dist"
    if _dist_dir.exists():
        os.chdir(str(_dist_dir))

        class _ThreadingHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a): pass
            def end_headers(self):
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                super().end_headers()

        class _ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            allow_reuse_address = True
            daemon_threads = True

        _httpd = _ThreadingServer(("127.0.0.1", 0), _ThreadingHandler)
        _port  = _httpd.server_address[1]
        threading.Thread(target=_httpd.serve_forever, daemon=True).start()
        _url = f"http://127.0.0.1:{_port}/index.html"
    else:
        _url = "http://localhost:5174"
    print(f"[WebView] url={_url}", flush=True)

    # ── pywebview ウィンドウ生成 ─────────────────
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
        # WindowsではQt操作を一切しない（ブラックアウト防止）
        if not _IS_WINDOWS and icon_path.exists() and qt_app:
            from PySide6.QtGui import QIcon
            qt_app.setWindowIcon(QIcon(str(icon_path)))
        on_shown(
            window=window,
            bridge=bridge,
            icon_path=icon_path,
            aide_width_getter=_get_aide_width,
        )
        if _IS_WINDOWS:
            bridge._main_window = window
            import win32gui, win32process, os as _os, time as _t
            _t.sleep(0.5)
            _pid = _os.getpid()
            _found = []
            def _cb(h, _):
                try:
                    t = win32gui.GetWindowText(h)
                    if t == "Ink Boss":
                        _, p = win32process.GetWindowThreadProcessId(h)
                        if p == _pid:
                            _found.append(h)
                except Exception:
                    pass
            win32gui.EnumWindows(_cb, None)
            if _found:
                bridge._main_hwnd_cache = _found[0]
                print(f"[win_init] main hwnd cached: {_found[0]}", flush=True)
            else:
                print("[win_init] WARNING: main hwnd not found!", flush=True)
            print("[win_init] lazy-load mode: windows created on first click", flush=True)
            # アップデートチェックはGitHub Releases v1.0.0公開後に有効化する
            # 現状は404エラーになるためスキップ
            # threading.Thread(target=_check_and_show_update, daemon=True).start()

    window.events.shown += _on_shown

    if _IS_WINDOWS:
        # func引数に渡した関数はGUIスレッドのメインループ内で実行される
        # pending_qからcreate_windowをGUIスレッドで処理するため最も安全
        import queue as _queue

        def _gui_func():
            import time as _t
            while True:
                try:
                    fn = bridge._pending_q.get_nowait()
                    fn()
                except _queue.Empty:
                    _t.sleep(0.01)   # 0.05→0.01: キュー処理レスポンス改善
                except Exception as e:
                    print(f"[gui_func] error: {e}", flush=True)
                    _t.sleep(0.01)

        webview.start(func=_gui_func)
    else:
        webview.start(gui="qt")


if __name__ == "__main__":
    main()
