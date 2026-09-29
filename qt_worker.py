import sys
import os
import json
import time
import uuid
import socket
import threading
import subprocess

from sysenv import get_clean_subprocess_env

os.environ["QT_IM_MODULE"] = "fcitx5"
os.environ["XMODIFIERS"] = "@im=fcitx5"
os.environ["GTK_IM_MODULE"] = "fcitx5"

from PySide6.QtWidgets import (
    QApplication, QMenu, QMessageBox, QInputDialog,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QWidget
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PySide6.QtCore import QUrl, QRect, QObject, Signal, Slot, QTimer, Qt, QPoint
from PySide6.QtGui import QIcon, QWindow
from pathlib import Path

SESSIONS_DIR = Path.home() / ".config" / "ink-boss" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
SOCKET_PORT = 19876

MENU_STYLE = """
QMenu {
    background-color: #111118;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 10px; padding: 4px;
    color: rgba(255,255,255,0.75); font-size: 13px;
}
QMenu::item { padding: 7px 16px; border-radius: 6px; min-width: 160px; }
QMenu::item:selected { background-color: rgba(255,255,255,0.08); color: white; }
QMenu::separator { height: 1px; background: rgba(255,255,255,0.07); margin: 3px 8px; }
"""

DIALOG_STYLE = """
QDialog { background-color: #111118; color: white; }
QLabel { color: rgba(255,255,255,0.5); font-size: 11px; }
QLineEdit {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px; padding: 8px 12px;
    color: white; font-size: 13px;
}
QLineEdit:focus { border: 1px solid rgba(255,255,255,0.3); }
QPushButton {
    border-radius: 8px; padding: 8px 16px; font-size: 13px;
    border: 1px solid rgba(255,255,255,0.15);
    color: rgba(255,255,255,0.6); background: transparent;
}
QPushButton:hover { background: rgba(255,255,255,0.08); color: white; }
QPushButton#addBtn { border: 1px solid rgba(255,255,255,0.4); color: white; }
QComboBox {
    background: #111118; border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px; padding: 8px 12px; color: white; font-size: 13px;
}
QComboBox QAbstractItemView {
    background: #111118; color: white;
    selection-background-color: rgba(255,255,255,0.1);
}
"""

SIDEBAR_W  = 208
URLBAR_H   = 40
TITLEBAR_H = 39


def xdo_reparent(child_wid: int, parent_wid: int, x: int, y: int):
    """X11 xdotoolでウィンドウを埋め込む"""
    try:
        clean_env = get_clean_subprocess_env()
        subprocess.run(
            ["xdotool", "windowreparent",
             str(child_wid), str(parent_wid)],
            check=False, capture_output=True, env=clean_env)
        subprocess.run(
            ["xdotool", "windowmove", "--sync",
             str(child_wid), str(x), str(y)],
            check=False, capture_output=True, env=clean_env)
    except FileNotFoundError:
        pass  # xdotoolが無い場合はスキップ


class Commander(QObject):
    cmd_signal = Signal(dict)

    def __init__(self):
        super().__init__()
        self.cmd_signal.connect(self.dispatch, Qt.ConnectionType.QueuedConnection)
        self._send_conn = None
        self._send_lock = threading.Lock()
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", SOCKET_PORT))
        srv.listen(5)
        print("qt_worker: listening", flush=True)
        while True:
            conn, _ = srv.accept()
            threading.Thread(
                target=self._handle_conn, args=(conn,), daemon=True).start()

    def _handle_conn(self, conn):
        buf = ""
        first = True
        with conn:
            while True:
                try:
                    data = conn.recv(4096)
                    if not data:
                        break
                    buf += data.decode("utf-8")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        if not line.strip():
                            continue
                        try:
                            cmd = json.loads(line)
                            if first and cmd.get("action") == "register_send":
                                first = False
                                with self._send_lock:
                                    self._send_conn = conn
                                print("qt_worker: send channel registered", flush=True)
                                # 接続を維持
                                while True:
                                    try:
                                        if not conn.recv(1):
                                            break
                                    except:
                                        break
                                return
                            first = False
                            self.cmd_signal.emit(cmd)
                        except:
                            pass
                except:
                    break

    def send_event(self, event: dict):
        with self._send_lock:
            if self._send_conn:
                try:
                    self._send_conn.sendall(
                        (json.dumps(event) + "\n").encode("utf-8"))
                except:
                    self._send_conn = None

    @Slot(dict)
    def dispatch(self, cmd):
        manager.handle(cmd)


class WebViewManager:
    def __init__(self, qt_app):
        self.qt_app = qt_app
        self.views = {}
        self.profiles = {}
        self.urls = {}
        self.hibernated = set()
        self.active_id = None
        self._active_dialog = None
        self._active_menu = None
        self._parent_win_id = None  # pywebviewのX11ウィンドウID
        self._win_x = 0
        self._win_y = 0
        self._win_w = 1280
        self._win_h = 850
        # X11経由でpywebviewウィンドウを追跡するタイマー
        self._follow_timer = QTimer()
        self._follow_timer.setInterval(100)
        self._follow_timer.timeout.connect(self._follow_window)
        self._follow_timer.start()

    def handle(self, cmd: dict):
        action = cmd.get("action")
        handlers = {
            "set_window_id":     self.set_window_id,
            "create_view":       self.create_view,
            "show_view":         self.show_view,
            "hide_all":          self.hide_all,
            "remove_view":       self.remove_view,
            "reload_view":       self.reload_view,
            "hibernate_view":    self.hibernate_view,
            "wake_view":         self.wake_view,
            "show_context_menu": self.show_context_menu,
            "show_add_dialog":   self.show_add_dialog,
        }
        if action in handlers:
            handlers[action](cmd)

    def set_window_id(self, cmd):
        """pywebviewのX11ウィンドウIDを受け取る"""
        self._parent_win_id = cmd["win_id"]
        self._win_x = cmd.get("x", 0)
        self._win_y = cmd.get("y", 0)
        self._win_w = cmd.get("w", 1280)
        self._win_h = cmd.get("h", 850)
        print(f"qt_worker: win pos=({self._win_x},{self._win_y}) "
              f"size={self._win_w}x{self._win_h}", flush=True)
        commander.send_event({"event": "ready"})

    def create_view(self, cmd):
        sid, url = cmd["service_id"], cmd["url"]
        if sid in self.views:
            return
        self.urls[sid] = url
        profile = QWebEngineProfile(sid, self.qt_app)
        profile.setPersistentStoragePath(str(SESSIONS_DIR / sid))
        page = QWebEnginePage(profile, self.qt_app)

        # 独立したウィンドウレスウィジェットとして作成
        view = QWebEngineView()
        view.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        view.setPage(page)
        view.setUrl(QUrl("about:blank"))
        self.hibernated.add(sid)
        view.hide()
        self.profiles[sid] = profile
        self.views[sid] = view
        print(f"qt_worker: created view {sid}", flush=True)

    def show_view(self, cmd):
        sid = cmd["service_id"]
        rel_x = cmd["x"]
        rel_y = cmd["y"]
        w = cmd["w"]
        h = cmd["h"]
        abs_x = self._win_x + rel_x
        abs_y = self._win_y + TITLEBAR_H + rel_y
        for s, v in self.views.items():
            if s != sid:
                v.hide()
        if sid not in self.views:
            return
        view = self.views[sid]
        view.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        view.setGeometry(QRect(abs_x, abs_y, w, h))
        view.show()
        view.raise_()
        view.activateWindow()
        self.active_id = sid
        print(f"qt_worker: show {sid} abs=({abs_x},{abs_y}) {w}x{h}", flush=True)

    def hide_all(self, cmd):
        for v in self.views.values():
            v.hide()
        self.active_id = None

    def remove_view(self, cmd):
        sid = cmd["service_id"]
        if sid in self.views:
            self.views[sid].hide()
            self.views[sid].setParent(None)
            self.views[sid].deleteLater()
            del self.views[sid]
        if sid in self.profiles:
            del self.profiles[sid]
        self.urls.pop(sid, None)
        self.hibernated.discard(sid)
        if self.active_id == sid:
            self.active_id = None

    def reload_view(self, cmd):
        sid = cmd["service_id"]
        if sid in self.views and sid not in self.hibernated:
            self.views[sid].reload()

    def hibernate_view(self, cmd):
        sid = cmd["service_id"]
        if sid in self.views and sid not in self.hibernated:
            self.views[sid].setUrl(QUrl("about:blank"))
            self.hibernated.add(sid)
            if self.active_id == sid:
                self.views[sid].hide()
                self.active_id = None

    def wake_view(self, cmd):
        sid = cmd["service_id"]
        url = cmd.get("url", self.urls.get(sid, "about:blank"))
        if sid in self.views:
            self.views[sid].setUrl(QUrl(url))
            self.hibernated.discard(sid)

    def set_window_pos(self, cmd):
        """ウィンドウ移動時に座標を更新"""
        self._win_x = cmd.get("x", self._win_x)
        self._win_y = cmd.get("y", self._win_y)
        self._win_w = cmd.get("w", self._win_w)
        self._win_h = cmd.get("h", self._win_h)

    def _follow_window(self):
        if not self.active_id or self.active_id not in self.views:
            return
    # pywebviewのウィンドウ位置をQtから直接取得
        for w in self.qt_app.topLevelWidgets():
            name = type(w).__name__
            if w.isVisible() and w.width() > 800 and name != "QWebEngineView":
                g = w.geometry()
                new_x = g.x()
                new_y = g.y()
                if new_x != self._win_x or new_y != self._win_y:
                    self._win_x = new_x
                    self._win_y = new_y
                    self._win_w = g.width()
                    self._win_h = g.height()
                break
    # アクティブなviewを正しい位置に配置
        x = self._win_x + SIDEBAR_W
        y = self._win_y + TITLEBAR_H + URLBAR_H
        w = self._win_w - SIDEBAR_W
        h = self._win_h - TITLEBAR_H - URLBAR_H
        view = self.views[self.active_id]
        if view.geometry() != QRect(x, y, w, h):
            view.setGeometry(QRect(x, y, w, h))


    def show_context_menu(self, cmd):
        sid = cmd["service_id"]
        name = cmd["service_name"]
        x, y = cmd["x"], cmd["y"]
        is_hib = cmd["is_hibernated"]
        groups = cmd.get("groups", [])

        if self._active_menu:
            self._active_menu.close()
            self._active_menu = None

        menu = QMenu()
        menu.setStyleSheet(MENU_STYLE)
        self._active_menu = menu

        rename_a = menu.addAction("名前を変更")
        menu.addSeparator()

        move_map, copy_map = {}, {}
        if groups:
            mm = menu.addMenu("グループに移動")
            mm.setStyleSheet(MENU_STYLE)
            for g in groups:
                a = mm.addAction(g["name"])
                move_map[id(a)] = g["id"]
            cm = menu.addMenu("グループにコピー")
            cm.setStyleSheet(MENU_STYLE)
            for g in groups:
                a = cm.addAction(g["name"])
                copy_map[id(a)] = g["id"]
            menu.addSeparator()

        toggle_a = menu.addAction("復帰" if is_hib else "休止")
        menu.addSeparator()
        delete_a = menu.addAction("削除")

        menu.popup(QPoint(x, y))
        menu.aboutToHide.connect(lambda: setattr(self, '_active_menu', None))
        return  # popupは非同期なのでreturn

        if not action:
            return

        if action == rename_a:
            new_name, ok = QInputDialog.getText(
                None, "名前を変更", "新しい名前:", text=name)
            if ok and new_name.strip():
                commander.send_event({
                    "event": "rename_service",
                    "service_id": sid, "name": new_name.strip()})
            return

        if action == delete_a:
            reply = QMessageBox.question(
                None, "削除確認", f"「{name}」を削除しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.remove_view({"service_id": sid})
                commander.send_event({"event": "remove_service", "service_id": sid})
            return

        if action == toggle_a:
            if is_hib:
                url = self.urls.get(sid, "about:blank")
                self.wake_view({"service_id": sid, "url": url})
                commander.send_event({"event": "service_woke", "service_id": sid})
            else:
                self.hibernate_view({"service_id": sid})
                commander.send_event({"event": "service_hibernated", "service_id": sid})
            return

        aid = id(action)
        if aid in move_map:
            commander.send_event({
                "event": "move_service",
                "service_id": sid, "group_id": move_map[aid]})
        elif aid in copy_map:
            commander.send_event({
                "event": "copy_service",
                "service_id": sid, "group_id": copy_map[aid]})

    def show_add_dialog(self, cmd):
        groups = cmd.get("groups", [])
        dialog = QDialog()
        dialog.setWindowTitle("サービスを追加")
        dialog.setMinimumWidth(400)
        dialog.setStyleSheet(DIALOG_STYLE)
        dialog.setWindowFlags(
            dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        layout.addWidget(QLabel("名前"))
        name_input = QLineEdit()
        name_input.setPlaceholderText("Discord")
        layout.addWidget(name_input)

        layout.addWidget(QLabel("URL"))
        url_input = QLineEdit()
        url_input.setPlaceholderText("https://discord.com/app")
        layout.addWidget(url_input)

        group_combo = None
        if groups:
            layout.addWidget(QLabel("グループ（任意）"))
            group_combo = QComboBox()
            group_combo.addItem("グループなし", "")
            for g in groups:
                group_combo.addItem(g["name"], g["id"])
            layout.addWidget(group_combo)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("キャンセル")
        add_btn = QPushButton("追加")
        add_btn.setObjectName("addBtn")
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(add_btn)
        layout.addLayout(btn_layout)

        def on_accept():
            name = name_input.text().strip()
            url = url_input.text().strip()
            if not name or not url:
                return
            if not url.startswith("http"):
                url = f"https://{url}"
            gid = group_combo.currentData() if group_combo else None
            commander.send_event({
                "event": "add_service",
                "name": name, "url": url, "group_id": gid or None
            })
            dialog.close()

        cancel_btn.clicked.connect(dialog.close)
        add_btn.clicked.connect(on_accept)
        name_input.setFocus()
        self._active_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()


qt_app = QApplication(sys.argv)
icon_path = Path(__file__).parent / "frontend" / "public" / "icon.png"
if icon_path.exists():
    qt_app.setWindowIcon(QIcon(str(icon_path)))

manager = WebViewManager(qt_app)
commander = Commander()

# main.pyが接続してきたらreadyを送信
def send_initial_ready():
    # send_connが確立されるまで待つ
    for _ in range(30):
        if commander._send_conn:
            commander.send_event({"event": "ready"})
            print("qt_worker: sent initial ready", flush=True)
            return
        time.sleep(0.3)

threading.Thread(target=send_initial_ready, daemon=True).start()
qt_app.exec()
