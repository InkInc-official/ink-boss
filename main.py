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
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from config import load_config, save_config
from bridge import ViewBridge
from api    import InkBossAPI
from window import on_shown, get_rect
from auth   import verify, get_cached_key, save_license_key_to_config

# QApplication
qt_app = QApplication.instance() or QApplication(sys.argv)
icon_path = Path(__file__).parent / "frontend" / "public" / "icon.png"
if icon_path.exists():
    qt_app.setWindowIcon(QIcon(str(icon_path)))

# 設定・ブリッジ
config = load_config()
bridge = ViewBridge(qt_app, config)

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
def _show_lock_screen(reason: str) -> None:
    """ライセンス未認証時のロック画面"""
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from auth import verify, save_license_key_to_config
    import subprocess

    REASON_MSG = {
        "invalid_key":  "キーが無効です。正しいキーを入力してください。",
        "inactive":     "このライセンスは無効化されています。\n所長にお問い合わせください。",
        "machine_limit":"登録台数の上限（2台）に達しています。\n所長にお問い合わせください。",
        "offline":      "サーバーに接続できませんでした。\nネットワーク接続を確認してください。",
        "error":        "認証中にエラーが発生しました。",
    }
    msg = REASON_MSG.get(reason, "")

    dialog = QDialog()
    dialog.setWindowTitle("Ink Boss")
    dialog.setMinimumWidth(460)
    dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
    dialog.setStyleSheet("""
        QDialog {
            background-color: #080810;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
        }
        QLabel { color: white; border: none; background: transparent; }
        QLineEdit {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 14px 16px;
            color: white;
            font-size: 15px;
            letter-spacing: 2px;
        }
        QLineEdit:focus { border: 1px solid rgba(255,255,255,0.35); }
        QPushButton#authBtn {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 10px;
            padding: 14px;
            color: white;
            font-size: 14px;
            font-weight: bold;
        }
        QPushButton#authBtn:hover { background: rgba(255,255,255,0.13); }
        QPushButton#authBtn:disabled { opacity: 0.35; }
    """)

    root = QVBoxLayout(dialog)
    root.setContentsMargins(48, 44, 48, 44)
    root.setSpacing(0)

    # タイトル
    title = QLabel("🖊️  Ink Boss")
    title.setFont(QFont("monospace", 22, QFont.Weight.Bold))
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root.addWidget(title)
    root.addSpacing(12)

    # 説明
    desc = QLabel("ご利用にはライセンスキーが必要です。\n所長より発行されたキーを入力してください。")
    desc.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 13px;")
    desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
    desc.setWordWrap(True)
    root.addWidget(desc)
    root.addSpacing(24)

    # エラー表示（エラー時のみ）
    err_label = QLabel(msg)
    err_label.setStyleSheet(
        "color: rgba(240,90,90,0.9); font-size: 12px;"
        "background: rgba(240,90,90,0.1); border: 1px solid rgba(240,90,90,0.3);"
        "border-radius: 8px; padding: 10px 14px;"
    )
    err_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    err_label.setWordWrap(True)
    err_label.setVisible(bool(msg))
    root.addWidget(err_label)
    if msg:
        root.addSpacing(16)

    # キー入力
    key_input = QLineEdit()
    key_input.setPlaceholderText("INK-XXXX-XXXX-XXXX")
    key_input.setText(config.get("license_key", ""))
    key_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root.addWidget(key_input)
    root.addSpacing(20)

    # 認証ボタン
    auth_btn = QPushButton("認証する")
    auth_btn.setObjectName("authBtn")
    root.addWidget(auth_btn)
    root.addSpacing(10)

    status_label = QLabel("")
    status_label.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 12px;")
    status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    root.addWidget(status_label)

    def on_auth():
        key = key_input.text().strip()
        if not key:
            err_label.setText("キーを入力してください")
            err_label.setVisible(True)
            return
        auth_btn.setEnabled(False)
        status_label.setText("認証中...")
        qt_app.processEvents()
        result = verify(key)
        if result["valid"]:
            save_license_key_to_config(config, key)
            save_config(config)
            status_label.setText("✅ 認証成功。Ink Bossを起動します...")
            qt_app.processEvents()
            dialog.accept()
            subprocess.Popen([sys.executable] + sys.argv)
        else:
            auth_btn.setEnabled(True)
            reason_map = {
                "invalid_key":  "キーが無効です。正しいキーを入力してください。",
                "inactive":     "このライセンスは無効化されています。所長にお問い合わせください。",
                "machine_limit":"登録台数の上限（2台）に達しています。所長にお問い合わせください。",
                "offline":      "サーバーに接続できません。ネットワークを確認してください。",
            }
            err_label.setText(reason_map.get(result["reason"], "認証に失敗しました。"))
            err_label.setVisible(True)
            status_label.setText("")

    auth_btn.clicked.connect(on_auth)
    key_input.returnPressed.connect(on_auth)
    dialog.exec()


def main():
    # ── ライセンス認証 ──────────────────────────
    license_key = config.get("license_key", "").strip()
    auth_result = verify(license_key) if license_key else {"valid": False, "reason": "no_key", "from_cache": False}

    if not auth_result["valid"]:
        _show_lock_screen(auth_result["reason"])
        return

    print(f"[Auth] 認証OK (reason={auth_result['reason']}, cache={auth_result['from_cache']})", flush=True)

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

    window = webview.create_window(
        "Ink Boss",
        url="http://localhost:5174",
        js_api=api,
        width=1280,
        height=850,
        min_size=(800, 600),
        background_color="#080810",
    )
    window.events.shown += lambda: on_shown(
        window=window,
        bridge=bridge,
        icon_path=icon_path,
        aide_width_getter=_get_aide_width,
    )
    webview.start(gui="qt")


if __name__ == "__main__":
    main()
