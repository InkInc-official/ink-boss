"""
window.py - ウィンドウ初期化・イベントハンドラ
Ink Boss / Ink Inc.

【重要】Windows(EdgeChromium/WebView2)では Qt API を一切使わない。
Qt の QApplication.topLevelWidgets() / setWindowFlags() / show() を
WebView2プロセス内で呼ぶと、WebView2のレンダリングコンテキストが
破壊されてブラックアウトする。9つのAIが同一原因を指摘済み。

Windows: ctypes / pywin32 のみ使用
Linux:   PySide6 / Qt を使用
"""

import platform
import subprocess
import threading
from pathlib import Path

from config import SIDEBAR_W, URLBAR_H
from bridge import set_win_id, get_win_id

_IS_WINDOWS = platform.system() == "Windows"


def get_rect(window, aide_w: int = 0) -> tuple[int, int, int, int]:
    """WebViewの表示領域を返す。"""
    return SIDEBAR_W, URLBAR_H, window.width - SIDEBAR_W - aide_w, window.height - URLBAR_H


# Linux専用: PySide6のimportはWindowsでは行わない
if not _IS_WINDOWS:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon, QPalette, QColor

    def find_container(main_win):
        for child in main_win.children():
            if type(child).__name__ == "WebView":
                for gc in child.children():
                    if type(gc).__name__ == "QWidget":
                        return gc
        return main_win

    def _find_main_win():
        widgets = QApplication.topLevelWidgets()
        for w in widgets:
            if w.isVisible() and w.windowTitle() == "Ink Boss":
                return w
        visible = [w for w in widgets if w.isVisible() and w.width() > 400 and w.height() > 400]
        if visible:
            return max(visible, key=lambda w: w.width() * w.height())
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            for w in widgets:
                if w.findChildren(QWebEngineView):
                    return w
        except Exception:
            pass
        return None


def on_shown(window, bridge, icon_path: Path, aide_width_getter) -> None:
    """pywebviewのshownイベントハンドラ。"""

    if _IS_WINDOWS:
        # Windows(EdgeChromium): ctypes/Qt操作は一切しない
        # frameless=TrueはpywebviewのWebView2が管理する
        # タスクバーアイコンはPyInstallerの--iconオプションで設定する
        print("[on_shown] Windows/EdgeChromium: skip all native ops", flush=True)

    else:
        # Linux(QtWebEngine): Qt操作はここだけ
        def hide_titlebar():
            import time
            time.sleep(1.0)
            result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
            win_id = None
            for line in result.stdout.splitlines():
                if "Ink Boss" in line:
                    win_id = line.split()[0]
                    break
            if win_id:
                set_win_id(win_id)
                subprocess.run(
                    ["xprop", "-id", win_id, "-f", "_MOTIF_WM_HINTS", "32c",
                     "-set", "_MOTIF_WM_HINTS", "0x2, 0x0, 0x0, 0x0, 0x0"],
                    check=False,
                )
                print(f"titlebar hidden: {win_id}", flush=True)
        threading.Thread(target=hide_titlebar, daemon=True).start()

        def _setup_container():
            from PySide6.QtCore import QTimer
            def _do():
                main_win = _find_main_win()
                if main_win is None:
                    QTimer.singleShot(500, _do)
                    return
                if icon_path.exists():
                    main_win.setWindowIcon(QIcon(str(icon_path)))
                palette = main_win.palette()
                palette.setColor(QPalette.ColorRole.Window, QColor("#080810"))
                main_win.setPalette(palette)
                main_win.setAutoFillBackground(True)
                container = find_container(main_win)
                print(f"[container] {type(container).__name__}", flush=True)
                bridge.set_container(container)
                bridge.init_views_signal.emit()
            QTimer.singleShot(0, _do)
        _setup_container()

    # リサイズイベント
    def on_resized(width, height):
        if _IS_WINDOWS:
            bridge.win_update_geometry(aide_width_getter())
        else:
            if bridge.active_id:
                x, y, w, h = get_rect(window, aide_width_getter())
                bridge.show_view_signal.emit(bridge.active_id, x, y, w, h)

    window.events.resized += on_resized
