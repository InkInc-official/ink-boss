"""
window.py - ウィンドウ初期化・イベントハンドラ
Ink Boss / Ink Inc.

A1: OS タイトルバーを消し、React TopBar の ●●● を正とする。
B1: リサイズ時に Electron オーバーレイも追従。
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPalette, QColor
from PySide6.QtCore import Qt

from config import SIDEBAR_W, URLBAR_H
from bridge import set_win_id


def get_rect(window, aide_w: int = 0) -> tuple[int, int, int, int]:
    """コンテンツ領域（ウィンドウクライアント相対）。"""
    return (
        SIDEBAR_W,
        URLBAR_H,
        max(1, int(window.width) - SIDEBAR_W - aide_w),
        max(1, int(window.height) - URLBAR_H),
    )


def get_screen_rect(window, aide_w: int = 0) -> tuple[int, int, int, int]:
    """
    コンテンツ領域の画面絶対座標。
    Electron B1 オーバーレイ用。
    frameless 時は window.x/y がフレーム原点と一致しやすい。
    """
    x, y, w, h = get_rect(window, aide_w)
    wx = int(getattr(window, "x", 0) or 0)
    wy = int(getattr(window, "y", 0) or 0)
    # xdotool 実座標があれば優先（ドラッグ直後の pywebview 内部値が古いことがある）
    try:
        from bridge import get_win_id

        wid = get_win_id()
        if wid:
            r = subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", wid],
                capture_output=True,
                text=True,
                timeout=0.5,
            )
            for line in r.stdout.splitlines():
                if line.startswith("X="):
                    wx = int(line.split("=")[1])
                elif line.startswith("Y="):
                    wy = int(line.split("=")[1])
    except Exception:
        pass
    return wx + x, wy + y, w, h


def find_container(main_win):
    for child in main_win.children():
        if type(child).__name__ == "WebView":
            for gc in child.children():
                if type(gc).__name__ == "QWidget":
                    return gc
    return main_win


def on_shown(window, bridge, icon_path: Path, aide_width_getter) -> None:
    def hide_titlebar():
        import time

        time.sleep(0.4)
        result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
        win_id = None
        for line in result.stdout.splitlines():
            if "Ink Boss" in line:
                win_id = line.split()[0]
                break
        if not win_id:
            return
        set_win_id(win_id)
        # MOTIF: decorations off（frameless=True と二重でも害は少ない）
        subprocess.run(
            [
                "xprop",
                "-id",
                win_id,
                "-f",
                "_MOTIF_WM_HINTS",
                "32c",
                "-set",
                "_MOTIF_WM_HINTS",
                "0x2, 0x0, 0x0, 0x0, 0x0",
            ],
            check=False,
        )
        print(f"titlebar hidden: {win_id}", flush=True)

    threading.Thread(target=hide_titlebar, daemon=True).start()

    main_win = None
    for w in QApplication.topLevelWidgets():
        if w.isVisible() and w.windowTitle() == "Ink Boss":
            main_win = w
            break
    if main_win is None:
        for w in QApplication.topLevelWidgets():
            if w.isVisible() and w.width() > 800:
                main_win = w
                break

    if main_win:
        if icon_path.exists():
            main_win.setWindowIcon(QIcon(str(icon_path)))
        palette = main_win.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#080810"))
        main_win.setPalette(palette)
        main_win.setAutoFillBackground(True)
        # A1 補強: Qt 側でも frameless（Linux のみ・既に frameless でも安全）
        try:
            flags = main_win.windowFlags()
            if not (flags & Qt.WindowType.FramelessWindowHint):
                main_win.setWindowFlags(flags | Qt.WindowType.FramelessWindowHint)
                main_win.show()
        except Exception as e:
            print(f"[window] frameless flag: {e}", flush=True)
        container = find_container(main_win)
        print(f"[container] {type(container).__name__}", flush=True)
        bridge.set_container(container)

    bridge.init_views_signal.emit()

    def on_resized(width, height):
        sid = bridge.active_id
        if not sid:
            return
        svc = next((s for s in bridge.config.get("services", []) if s["id"] == sid), None)
        eng = ((svc or {}).get("engine") or "qt").lower()
        aide_w = aide_width_getter()
        if eng in ("electron", "e"):
            electron = getattr(bridge, "electron", None)
            if electron is not None and electron.is_available():
                sx, sy, sw, sh = get_screen_rect(window, aide_w)

                def _sync():
                    try:
                        electron.bounds(sid, sx, sy, sw, sh)
                    except Exception as e:
                        print(f"[on_resized] electron.bounds: {e}", flush=True)

                threading.Thread(target=_sync, daemon=True).start()
            return
        x, y, w, h = get_rect(window, aide_w)
        bridge.show_view_signal.emit(sid, x, y, w, h)

    window.events.resized += on_resized
