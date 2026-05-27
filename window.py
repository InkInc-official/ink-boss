"""
window.py - ウィンドウ初期化・イベントハンドラ
Ink Boss / Ink Inc.

on_shown / on_resized / find_container を管理する。
タイトルバー非表示・背景透過防止・ウィンドウIDキャッシュもここで行う。
"""

import subprocess
import threading
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPalette, QColor

from config import SIDEBAR_W, URLBAR_H
from bridge import set_win_id, get_win_id


def get_rect(window, aide_w: int = 0) -> tuple[int, int, int, int]:
    """WebViewの表示領域を返す。"""
    return SIDEBAR_W, URLBAR_H, window.width - SIDEBAR_W - aide_w, window.height - URLBAR_H


def find_container(main_win):
    """pywebviewのQWidgetコンテナを探して返す。見つからなければmain_winを返す。"""
    for child in main_win.children():
        if type(child).__name__ == "WebView":
            for gc in child.children():
                if type(gc).__name__ == "QWidget":
                    return gc
    return main_win


def on_shown(window, bridge, icon_path: Path, aide_width_getter) -> None:
    """
    pywebviewのshownイベントハンドラ。

    Args:
        window:           pywebview.Window
        bridge:           ViewBridgeインスタンス
        icon_path:        アイコンファイルパス
        aide_width_getter: () → int  現在の_aide_width
    """
    # タイトルバー非表示 & ウィンドウIDキャッシュ
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

    # Qtウィンドウを取得
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
        # 背景透過防止
        palette = main_win.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#080810"))
        main_win.setPalette(palette)
        main_win.setAutoFillBackground(True)
        container = find_container(main_win)
        print(f"[container] {type(container).__name__}", flush=True)
        bridge.set_container(container)

    # Qtメインスレッドでサービスを初期化
    bridge.init_views_signal.emit()

    # リサイズイベント
    def on_resized(width, height):
        if bridge.active_id:
            x, y, w, h = get_rect(window, aide_width_getter())
            bridge.show_view_signal.emit(bridge.active_id, x, y, w, h)

    window.events.resized += on_resized
