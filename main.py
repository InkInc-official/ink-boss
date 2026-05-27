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

from config import load_config
from bridge import ViewBridge
from api    import InkBossAPI
from window import on_shown, get_rect

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


def main():
    # APIインスタンス生成
    api = InkBossAPI(
        config=config,
        bridge=bridge,
        get_rect_fn=get_rect,
        aide_width_getter=_get_aide_width,
    )
    # set_aide_widthはAPIがInkBossAPI._aide_width_valを持つが、
    # グローバル_aide_widthとの同期のためラップする
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
