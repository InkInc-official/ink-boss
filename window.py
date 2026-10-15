"""
window.py - ウィンドウ初期化・イベントハンドラ
Ink Boss / Ink Inc.

A1: OS タイトルバーを消し、React TopBar の ●●● を正とする。
B1: リサイズ時に Electron オーバーレイも追従。
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPalette, QColor
from PySide6.QtCore import Qt

import winctl
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
    # OS側の実座標があれば優先（ドラッグ直後の pywebview 内部値が古いことがある）。
    # 取得できない環境では pywebview 内部値のまま（winctl.get_window_position が None）。
    try:
        from bridge import get_win_id

        wid = get_win_id()
        if wid:
            pos = winctl.get_window_position(wid, timeout=0.5)
            if pos is not None:
                wx, wy = pos
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
        # タイトル一致だけでなく自プロセスのPID一致も要求する
        # （winctl.find_own_window_idのdocstring参照。無関係な外部アプリの
        # ウィンドウを誤って自分のものとして掴む実害のあるバグが
        # あったため）。
        win_id = winctl.find_own_window_id("Ink Boss")
        if not win_id:
            return
        set_win_id(win_id)
        # OSのタイトルバーを消す（frameless=True と二重でも害は少ない）
        winctl.remove_decorations(win_id)
        print(f"titlebar hidden: {win_id}", flush=True)
        if os.environ.get("INK_BOSS_WINDEBUG") and not getattr(on_shown, "_debug_started", False):
            on_shown._debug_started = True

            def _debug_loop():
                import time as _t
                last = None
                while True:
                    cur = winctl.debug_window_state(win_id)
                    if cur != last:
                        print(f"[WINDEBUG] {cur}", flush=True)
                        last = cur
                    _t.sleep(0.25)

            threading.Thread(target=_debug_loop, daemon=True).start()

    threading.Thread(target=hide_titlebar, daemon=True).start()

    def _setup_main_win():
        # Qtウィジェット操作はGUIスレッドで行う（pywebviewのshownコールバックは
        # ワーカースレッドで走るため、Windowsではここで直接触るとデッドロックする）
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
            # A1 補強: Qt 側でも frameless（Linuxのみ。Windowsはpywebviewの
            # frameless指定に任せ、再showによる点滅・不具合を避ける）
            if sys.platform.startswith("linux"):
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

    # キュー順序: set_container → init_views の順でGUIスレッドに届く
    bridge.run_on_gui_signal.emit(_setup_main_win)

    bridge.init_views_signal.emit()

    def on_resized(width, height):
        # 最小化中はQtが極小サイズ(数px)を通知してくる。その値でビューを
        # 1x1に縮めても意味がなく、復帰時のちらつき・不具合の元になるため無視。
        if int(width) <= SIDEBAR_W or int(height) <= URLBAR_H:
            return
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
