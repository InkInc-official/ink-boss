import time
import json
import uuid
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PySide6.QtCore import QUrl, QRect, QObject, Signal, Slot, QTimer, Qt

from .config import SESSIONS_DIR, save_config

def js_eval(js: str):
    try:
        import webview
        if webview.windows:
            webview.windows[0].evaluate_js(js)
    except:
        pass


MENU_STYLE = """
QMenu {
    background-color: #111118;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 10px;
    padding: 4px;
    color: rgba(255,255,255,0.75);
    font-size: 13px;
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
QComboBox QAbstractItemView { background: #111118; color: white; selection-background-color: rgba(255,255,255,0.1); }
"""

Q = Qt.ConnectionType.QueuedConnection


class ViewBridge(QObject):
    # WebView操作シグナル（全てQueuedConnection）
    create_view_signal     = Signal(str, str)
    show_view_signal       = Signal(str, int, int, int, int)
    hide_all_signal        = Signal()
    remove_view_signal     = Signal(str)
    reload_view_signal     = Signal(str)
    hibernate_view_signal  = Signal(str)
    wake_view_signal       = Signal(str, str)
    # UI操作シグナル（全てQueuedConnection）
    context_menu_signal    = Signal(str, str, int, int, bool, str)
    show_add_dialog_signal = Signal(str)

    def __init__(self, qt_app, config_ref: dict):
        super().__init__()
        self.qt_app      = qt_app
        self.config      = config_ref
        self.views       = {}
        self.profiles    = {}
        self.urls        = {}
        self.hibernated  = set()
        self.last_active = {}
        self.active_id   = None
        self.container   = None
        self._active_dialog = None

        # 全シグナルをQueuedConnectionで接続
        self.create_view_signal.connect(self._create_view, Q)
        self.show_view_signal.connect(self._show_view, Q)
        self.hide_all_signal.connect(self._hide_all, Q)
        self.remove_view_signal.connect(self._remove_view, Q)
        self.reload_view_signal.connect(self._reload_view, Q)
        self.hibernate_view_signal.connect(self._hibernate_view, Q)
        self.wake_view_signal.connect(self._wake_view, Q)
        self.context_menu_signal.connect(self._show_context_menu, Q)
        self.show_add_dialog_signal.connect(self._show_add_dialog, Q)

    def set_container(self, widget):
        self.container = widget

    @Slot(str, str)
    def _create_view(self, service_id, url):
        if service_id in self.views:
            return
        self.urls[service_id] = url
        profile = QWebEngineProfile(service_id, self.qt_app)
        profile.setPersistentStoragePath(str(SESSIONS_DIR / service_id))
        page = QWebEnginePage(profile, self.qt_app)
        view = QWebEngineView(self.container)
        view.setPage(page)
        view.setUrl(QUrl("about:blank"))
        self.hibernated.add(service_id)
        view.hide()
        self.profiles[service_id] = profile
        self.views[service_id] = view

    @Slot(str, int, int, int, int)
    def _show_view(self, service_id, x, y, w, h):
        for sid, v in self.views.items():
            if sid != service_id:
                v.hide()
        if service_id not in self.views:
            return
        view = self.views[service_id]
        view.setGeometry(QRect(x, y, w, h))
        view.show()
        view.raise_()
        self.active_id = service_id
        self.last_active[service_id] = time.time()

    @Slot()
    def _hide_all(self):
        for v in self.views.values():
            v.hide()
        self.active_id = None

    @Slot(str)
    def _remove_view(self, service_id):
        if service_id in self.views:
            self.views[service_id].hide()
            self.views[service_id].setParent(None)
            self.views[service_id].deleteLater()
            del self.views[service_id]
        if service_id in self.profiles:
            del self.profiles[service_id]
        self.urls.pop(service_id, None)
        self.hibernated.discard(service_id)
        self.last_active.pop(service_id, None)
        if self.active_id == service_id:
            self.active_id = None

    @Slot(str)
    def _reload_view(self, service_id):
        if service_id in self.views and service_id not in self.hibernated:
            self.views[service_id].reload()

    @Slot(str)
    def _hibernate_view(self, service_id):
        if service_id in self.views and service_id not in self.hibernated:
            self.views[service_id].setUrl(QUrl("about:blank"))
            self.hibernated.add(service_id)
            if self.active_id == service_id:
                self.views[service_id].hide()
                self.active_id = None

    @Slot(str, str)
    def _wake_view(self, service_id, url):
        if service_id in self.views:
            self.views[service_id].setUrl(QUrl(url))
            self.hibernated.discard(service_id)
            self.last_active[service_id] = time.time()

    @Slot(str, str, int, int, bool, str)
    def _show_context_menu(self, service_id, service_name, x, y, is_hibernated, groups_json):
        from PySide6.QtWidgets import QMenu, QMessageBox, QInputDialog
        from PySide6.QtGui import QAction
        from PySide6.QtCore import QPoint

        groups_data = json.loads(groups_json)
        menu = QMenu()
        menu.setStyleSheet(MENU_STYLE)

        rename_action = menu.addAction("名前を変更")
        menu.addSeparator()

        move_actions = {}
        copy_actions = {}
        if groups_data:
            move_menu = menu.addMenu("グループに移動")
            move_menu.setStyleSheet(MENU_STYLE)
            for g in groups_data:
                a = move_menu.addAction(g["name"])
                move_actions[id(a)] = g["id"]

            copy_menu = menu.addMenu("グループにコピー")
            copy_menu.setStyleSheet(MENU_STYLE)
            for g in groups_data:
                a = copy_menu.addAction(g["name"])
                copy_actions[id(a)] = g["id"]

            menu.addSeparator()

        toggle_action = menu.addAction("復帰" if is_hibernated else "休止")
        menu.addSeparator()
        delete_action = menu.addAction("削除")

        action = menu.exec(QPoint(x, y))
        if action is None:
            return

        if action == rename_action:
            new_name, ok = QInputDialog.getText(
                None, "名前を変更", "新しい名前:", text=service_name)
            if ok and new_name.strip():
                for s in self.config["services"]:
                    if s["id"] == service_id:
                        s["name"] = new_name.strip()
                        break
                save_config(self.config)
                js_eval(f"window.dispatchEvent(new CustomEvent('service-renamed', {{detail: {{id: '{service_id}', name: {json.dumps(new_name.strip())}}}}}))")
            return

        if action == delete_action:
            reply = QMessageBox.question(
                None, "削除確認", f"「{service_name}」を削除しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.config["services"] = [
                    s for s in self.config["services"] if s["id"] != service_id]
                save_config(self.config)
                self._remove_view(service_id)
                js_eval(f"window.dispatchEvent(new CustomEvent('service-removed', {{detail: '{service_id}'}}));")
            return

        if action == toggle_action:
            if is_hibernated:
                url = self.urls.get(service_id, "about:blank")
                self._wake_view(service_id, url)
                js_eval(f"window.dispatchEvent(new CustomEvent('service-woke', {{detail: '{service_id}'}}));")
            else:
                self._hibernate_view(service_id)
                js_eval(f"window.dispatchEvent(new CustomEvent('service-hibernated', {{detail: '{service_id}'}}));")
            return

        aid = id(action)
        if aid in move_actions:
            gid = move_actions[aid]
            for s in self.config["services"]:
                if s["id"] == service_id:
                    s["groupId"] = gid
                    break
            save_config(self.config)
            js_eval(f"window.dispatchEvent(new CustomEvent('service-moved', {{detail: {{id: '{service_id}', groupId: '{gid}'}}}}))")
        elif aid in copy_actions:
            gid = copy_actions[aid]
            original = next(
                (s for s in self.config["services"] if s["id"] == service_id), None)
            if original:
                new_svc = {
                    "id": f"service_{uuid.uuid4().hex[:8]}",
                    "name": original["name"],
                    "url": original["url"],
                    "muted": False,
                    "groupId": gid,
                }
                self.config["services"].append(new_svc)
                save_config(self.config)
                self._create_view(new_svc["id"], new_svc["url"])
                js_eval(f"window.dispatchEvent(new CustomEvent('service-copied', {{detail: {json.dumps(new_svc)}}}))")

    @Slot(str)
    def _show_add_dialog(self, group_id_str):
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                        QLabel, QLineEdit, QPushButton, QComboBox)
        from PySide6.QtCore import Qt as QtCore

        group_id = group_id_str if group_id_str else None
        groups = self.config.get("groups", [])

        dialog = QDialog()
        dialog.setWindowTitle("サービスを追加")
        dialog.setMinimumWidth(400)
        dialog.setStyleSheet(DIALOG_STYLE)
        dialog.setWindowFlags(dialog.windowFlags() | QtCore.WindowStaysOnTopHint)

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
            gid = group_combo.currentData() if group_combo else (group_id or None)
            service = {
                "id": f"service_{uuid.uuid4().hex[:8]}",
                "name": name,
                "url": url,
                "muted": False,
                "groupId": gid or None,
            }
            self.config["services"].append(service)
            save_config(self.config)
            self._create_view(service["id"], url)
            js_eval(f"window.dispatchEvent(new CustomEvent('service-added', {{detail: {json.dumps(service)}}}))")
            dialog.close()

        cancel_btn.clicked.connect(dialog.close)
        add_btn.clicked.connect(on_accept)
        name_input.setFocus()

        self._active_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def update_geometry(self, service_id, x, y, w, h):
        if service_id in self.views and service_id == self.active_id:
            self.show_view_signal.emit(service_id, x, y, w, h)

    def check_hibernate(self, hibernate_minutes):
        if hibernate_minutes <= 0:
            return
        now = time.time()
        threshold = hibernate_minutes * 60
        for service_id, last in list(self.last_active.items()):
            if service_id == self.active_id:
                continue
            if service_id in self.hibernated:
                continue
            if now - last >= threshold:
                self._hibernate_view(service_id)
                js_eval(f"window.dispatchEvent(new CustomEvent('service-hibernated', {{detail: '{service_id}'}}));")
