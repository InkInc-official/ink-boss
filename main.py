import sys
import os

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IME設定：すべてのimport・QApplication生成より前に設定必須
# 配布対応：fcitx5 / ibus を自動検出し、PySide6へプラグインを自動リンク
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _setup_ime():
    import subprocess, shutil
    from pathlib import Path

    # PySide6のplatforminputcontextsディレクトリを取得
    try:
        import PySide6
        pyside_plugin_dir = Path(PySide6.__file__).parent / "Qt" / "plugins" / "platforminputcontexts"
    except Exception:
        return "none"

    # システム側のQt6プラグインディレクトリ候補
    sys_plugin_dirs = [
        Path("/usr/lib/x86_64-linux-gnu/qt6/plugins/platforminputcontexts"),
        Path("/usr/lib/qt6/plugins/platforminputcontexts"),
        Path("/usr/lib/aarch64-linux-gnu/qt6/plugins/platforminputcontexts"),
    ]

    def _link_plugin(name):
        """システムのプラグインをPySide6ディレクトリにリンク（なければコピー）"""
        dst = pyside_plugin_dir / name
        if dst.exists() or dst.is_symlink():
            return True
        for sys_dir in sys_plugin_dirs:
            src = sys_dir / name
            if src.exists():
                try:
                    os.symlink(src, dst)
                    return True
                except PermissionError:
                    try:
                        shutil.copy2(src, dst)
                        return True
                    except Exception:
                        pass
        return False

    # fcitx5が起動中か確認
    fcitx5_running = subprocess.run(
        ["pgrep", "-x", "fcitx5"], capture_output=True).returncode == 0

    # ibusが起動中か確認
    ibus_running = subprocess.run(
        ["pgrep", "-x", "ibus-daemon"], capture_output=True).returncode == 0

    if fcitx5_running:
        _link_plugin("libfcitx5platforminputcontextplugin.so")
        # QWebEngineView（Chromium）はXIMではなくibusプロトコルで通信する
        # fcitx5はibusフロントエンドを内蔵しているのでibus経由で接続する
        os.environ["QT_IM_MODULE"]  = "ibus"
        os.environ["XMODIFIERS"]    = "@im=ibus"
        os.environ["GTK_IM_MODULE"] = "ibus"
        os.environ["INPUT_METHOD"]  = "ibus"
        os.environ["SDL_IM_MODULE"] = "ibus"
        # EcosiaブラウザのChromiumと同じフラグでIMEを有効化
        existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            existing + " --ozone-platform-hint=auto"
        ).strip()
        return "fcitx5(via ibus)"
    elif ibus_running:
        _link_plugin("libibusplatforminputcontextplugin.so")
        os.environ["QT_IM_MODULE"]  = "ibus"
        os.environ["XMODIFIERS"]    = "@im=ibus"
        os.environ["GTK_IM_MODULE"] = "ibus"
        os.environ["INPUT_METHOD"]  = "ibus"
        return "ibus"
    else:
        # どちらも起動していない場合はfcitx5を優先試行
        if _link_plugin("libfcitx5platforminputcontextplugin.so"):
            os.environ["QT_IM_MODULE"]  = "fcitx"
            os.environ["XMODIFIERS"]    = "@im=fcitx"
            os.environ["GTK_IM_MODULE"] = "fcitx"
            return "fcitx5(not running)"
        return "none"

_ime_backend = _setup_ime()
print(f"[IME] backend={_ime_backend}", flush=True)


import json
import uuid
import time
import webview
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineSettings
from PySide6.QtCore import QUrl, QRect, QObject, Signal, Slot, QTimer, Qt
from PySide6.QtGui import QIcon

CONFIG_DIR = Path.home() / ".config" / "ink-boss"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

SIDEBAR_W = 208
URLBAR_H  = 40

DEFAULT_CONFIG = {
    "version": "2.0.0",
    "theme": "dark",
    "llm": {"backend": "ollama", "ollamaUrl": "http://localhost:11434",
            "ollamaModel": "llama3", "claudeApiKey": "", "geminiApiKey": ""},
    "hibernate_minutes": 10,
    "services": [],
    "groups": [],
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

Q = Qt.ConnectionType.QueuedConnection

DIALOG_STYLE = """
QDialog { background-color: #111118; color: white; }
QLabel { color: rgba(255,255,255,0.5); font-size: 12px; }
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
QFrame#card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08); border-radius: 10px;
}
QTabWidget::pane { border: none; background-color: #111118; }
QTabBar::tab {
    background: transparent; color: rgba(255,255,255,0.4);
    padding: 8px 16px; border-radius: 8px; font-size: 13px; min-width: 70px;
}
QTabBar::tab:selected {
    background: rgba(255,255,255,0.1); color: white;
    border: 1px solid rgba(255,255,255,0.15);
}
QTabBar::tab:hover { color: rgba(255,255,255,0.7); }
"""

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


class ViewBridge(QObject):
    create_view_signal    = Signal(str, str)
    show_view_signal      = Signal(str, int, int, int, int)
    hide_all_signal       = Signal()
    remove_view_signal    = Signal(str)
    reload_view_signal    = Signal(str)
    hibernate_view_signal = Signal(str)
    wake_view_signal      = Signal(str, str)
    context_menu_signal   = Signal(str, str, int, int, bool, str)
    add_dialog_signal     = Signal(str)
    settings_signal       = Signal()
    add_group_dialog_signal = Signal()
    group_menu_signal       = Signal(str, str, int, int)
    add_group_signal      = Signal(str)
    del_group_signal      = Signal(str)
    init_views_signal     = Signal()  # サービス初期化用

    def __init__(self, qt_app, config):
        super().__init__()
        self.qt_app     = qt_app
        self.config     = config
        self.views           = {}
        self.profiles        = {}
        self.urls            = {}
        self.hibernated      = set()
        self.active_id       = None
        self.container       = None
        self._active_menu    = None
        self._pending_js     = None
        self.page_text_cache = {}

        self.create_view_signal.connect(self._create_view, Q)
        self.show_view_signal.connect(self._show_view, Q)
        self.hide_all_signal.connect(self._hide_all, Q)
        self.remove_view_signal.connect(self._remove_view, Q)
        self.reload_view_signal.connect(self._reload_view, Q)
        self.hibernate_view_signal.connect(self._hibernate_view, Q)
        self.wake_view_signal.connect(self._wake_view, Q)
        self.context_menu_signal.connect(self._show_context_menu, Q)
        self.add_dialog_signal.connect(self._show_add_dialog, Q)
        self.settings_signal.connect(self._show_settings, Q)
        self.add_group_dialog_signal.connect(self._show_add_group_dialog, Q)
        self.group_menu_signal.connect(self._show_group_menu, Q)
        self.add_group_signal.connect(self._add_group, Q)
        self.del_group_signal.connect(self._del_group, Q)
        self.init_views_signal.connect(self._init_views, Q)

    @Slot()
    def _init_views(self):
        print(f"[_init_views] services={len(self.config.get('services', []))}", flush=True)
        for svc in self.config.get("services", []):
            print(f"[_init_views] emit create_view: {svc['id']}", flush=True)
            self.create_view_signal.emit(svc["id"], svc["url"])

    def set_container(self, widget):
        self.container = widget

    @Slot(str, str)
    def _create_view(self, sid, url):
        if sid in self.views:
            return
        self.urls[sid] = url
        profile = QWebEngineProfile(sid, self.qt_app)
        profile.setPersistentStoragePath(str(SESSIONS_DIR / sid))
        profile.setHttpUserAgent(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = QWebEnginePage(profile, self.qt_app)
        # IME有効化
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        view = QWebEngineView(self.container)
        view.setPage(page)
        view.setUrl(QUrl("about:blank"))
        self.hibernated.add(sid)
        view.hide()
        self.profiles[sid] = profile
        self.views[sid] = view

        def _push_text(text, s=sid):
            if text and len(text.strip()) > 10:
                self.page_text_cache[s] = text
                payload = json.dumps({"sid": s, "text": text[:4000]})
                js_eval(f"window.dispatchEvent(new CustomEvent('page-text-ready',{{detail:{payload}}}))")

        def on_load_finished(ok, s=sid):
            if not ok: return
            v = self.views.get(s)
            if v is None: return
            if v.url().toString() in ("about:blank", "", "about:blank#blocked"): return
            print(f"[cache:load] {s}", flush=True)
            v.page().runJavaScript("document.body.innerText", _push_text)
        view.loadFinished.connect(on_load_finished)

        def on_url_changed(url, s=sid):
            url_str = url.toString()
            if url_str in ("about:blank", "", "about:blank#blocked"): return
            from PySide6.QtCore import QTimer
            def delayed():
                v = self.views.get(s)
                if v: v.page().runJavaScript("document.body.innerText", _push_text)
            QTimer.singleShot(1500, delayed)
        view.urlChanged.connect(on_url_changed)

    @Slot(str, int, int, int, int)
    def _show_view(self, sid, x, y, w, h):
        for s, v in self.views.items():
            if s != sid:
                v.hide()
        if sid not in self.views:
            return
        view = self.views[sid]
        print(f"_show_view: x={x} y={y} w={w} h={h}", flush=True)
        view.setGeometry(QRect(x, y, w, h))
        view.show()
        view.raise_()
        view.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        for child in view.findChildren(type(view)):
            child.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        # X11フォーカスをpywebviewのウィンドウに移しXIM接続を確立（IME有効化）
        if _win_id:
            import subprocess, threading
            def _force_focus(wid_hex):
                import time
                time.sleep(0.2)
                subprocess.run(["wmctrl", "-ia", wid_hex],
                               check=False, capture_output=True)
                time.sleep(0.1)
                # XIMクライアント再接続：fcitx5にフォーカス通知を送る
                subprocess.run(["fcitx5-remote", "-o"],
                               check=False, capture_output=True)
            threading.Thread(
                target=_force_focus, args=(_win_id,), daemon=True).start()
        self.active_id = sid

    @Slot()
    def _hide_all(self):
        for v in self.views.values():
            v.hide()
        self.active_id = None

    @Slot(str)
    def _remove_view(self, sid):
        if sid in self.views:
            self.views[sid].hide()
            self.views[sid].setParent(None)
            self.views[sid].deleteLater()
            del self.views[sid]
        self.profiles.pop(sid, None)
        self.urls.pop(sid, None)
        self.hibernated.discard(sid)
        if self.active_id == sid:
            self.active_id = None

    @Slot(str)
    def _reload_view(self, sid):
        if sid in self.views and sid not in self.hibernated:
            self.views[sid].reload()

    @Slot(str)
    def _hibernate_view(self, sid):
        if sid in self.views and sid not in self.hibernated:
            self.views[sid].setUrl(QUrl("about:blank"))
            self.hibernated.add(sid)
            if self.active_id == sid:
                self.views[sid].hide()
                self.active_id = None

    @Slot(str, str)
    def _wake_view(self, sid, url):
        if sid in self.views:
            self.views[sid].setUrl(QUrl(url))
            self.hibernated.discard(sid)
            js_eval(f"window.dispatchEvent(new CustomEvent('service-woke',{{detail:'{sid}'}}))") 

    @Slot(str, str, int, int, bool, str)
    def _show_context_menu(self, sid, name, x, y, is_hib, groups_json):
        from PySide6.QtWidgets import QMenu
        from PySide6.QtCore import QPoint

        if self._active_menu:
            self._active_menu.close()

        groups = json.loads(groups_json)
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

        action = menu.exec(QPoint(x, y))
        self._active_menu = None

        if not action:
            return
        if action == rename_a:
            self._do_rename(sid, name)
        elif action == delete_a:
            self._do_delete(sid, name)
        elif action == toggle_a:
            if is_hib:
                self._wake_view(sid, self.urls.get(sid, "about:blank"))
                js_eval(f"window.dispatchEvent(new CustomEvent('service-woke',{{detail:'{sid}'}}));")
            else:
                self._hibernate_view(sid)
                js_eval(f"window.dispatchEvent(new CustomEvent('service-hibernated',{{detail:'{sid}'}}));")
        else:
            aid = id(action)
            if aid in move_map:
                gid = move_map[aid]
                for s in self.config["services"]:
                    if s["id"] == sid:
                        s["groupId"] = gid; break
                save_config(self.config)
                js_eval(f"window.dispatchEvent(new CustomEvent('service-moved',{{detail:{{id:'{sid}',groupId:'{gid}'}}}}));")
            elif aid in copy_map:
                gid = copy_map[aid]
                orig = next((s for s in self.config["services"] if s["id"] == sid), None)
                if orig:
                    new_svc = {"id": f"service_{uuid.uuid4().hex[:8]}",
                               "name": orig["name"], "url": orig["url"],
                               "muted": False, "groupId": gid}
                    self.config["services"].append(new_svc)
                    save_config(self.config)
                    self._create_view(new_svc["id"], new_svc["url"])
                    js_eval(f"window.dispatchEvent(new CustomEvent('service-copied',{{detail:{json.dumps(new_svc)}}}));")

    @Slot(str)
    def _add_group(self, name):
        import threading
        g = {"id": f"group_{uuid.uuid4().hex[:8]}", "name": name, "collapsed": False}
        self.config["groups"].append(g)
        save_config(self.config)
        threading.Thread(target=lambda: js_eval(f"window.dispatchEvent(new CustomEvent('group-added',{{detail:{json.dumps(g)}}}));"), daemon=True).start()

    @Slot(str)
    def _del_group(self, gid):
        import threading
        self.config["groups"] = [x for x in self.config["groups"] if x["id"] != gid]
        for s in self.config["services"]:
            if s.get("groupId") == gid:
                s["groupId"] = None
        save_config(self.config)
        threading.Thread(target=lambda: js_eval(f"window.dispatchEvent(new CustomEvent('group-removed',{{detail:'{gid}'}}));"), daemon=True).start()

    @Slot(str, str, int, int)
    def _show_group_menu(self, gid, name, x, y):
        from PySide6.QtWidgets import QMenu
        from PySide6.QtCore import QPoint
        if self._active_menu:
            self._active_menu.close()
        menu = QMenu()
        menu.setStyleSheet(MENU_STYLE)
        self._active_menu = menu
        rename_a = menu.addAction("名前を変更")
        menu.addSeparator()
        delete_a = menu.addAction("削除")
        action = menu.exec(QPoint(x, y))
        self._active_menu = None
        if not action:
            return
        if action == rename_a:
            self._rename_group(gid, name)
        elif action == delete_a:
            self._delete_group(gid, name)

    def _rename_group(self, gid, current_name):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
        dialog = QDialog()
        dialog.setWindowTitle("グループ名を変更")
        dialog.setMinimumWidth(350)
        dialog.setStyleSheet(DIALOG_STYLE)
        dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel("新しいグループ名"))
        name_input = QLineEdit(current_name)
        layout.addWidget(name_input)
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("キャンセル")
        ok_btn = QPushButton("変更")
        ok_btn.setObjectName("addBtn")
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)
        cancel_btn.clicked.connect(dialog.close)
        def on_ok():
            new_name = name_input.text().strip()
            if new_name:
                for g in self.config["groups"]:
                    if g["id"] == gid:
                        g["name"] = new_name
                        break
                save_config(self.config)
                js_eval(f"window.dispatchEvent(new CustomEvent('group-renamed',{{detail:{{id:'{gid}',name:{json.dumps(new_name)}}}}}))")
            dialog.close()
        ok_btn.clicked.connect(on_ok)
        name_input.setFocus()
        name_input.selectAll()
        dialog.exec()

    def _delete_group(self, gid, name):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        dialog = QDialog()
        dialog.setWindowTitle("グループを削除")
        dialog.setMinimumWidth(320)
        dialog.setStyleSheet(DIALOG_STYLE)
        dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel(f"「{name}」を削除しますか？\nサービスはグループ解除されます。"))
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("キャンセル")
        del_btn = QPushButton("削除する")
        del_btn.setObjectName("addBtn")
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(del_btn)
        layout.addLayout(btn_layout)
        cancel_btn.clicked.connect(dialog.close)
        def on_delete():
            self.config["groups"] = [g for g in self.config["groups"] if g["id"] != gid]
            for s in self.config["services"]:
                if s.get("groupId") == gid:
                    s["groupId"] = None
            save_config(self.config)
            js_eval(f"window.dispatchEvent(new CustomEvent('group-removed',{{detail:'{gid}'}}));")
            dialog.close()
        del_btn.clicked.connect(on_delete)
        dialog.exec()

    @Slot()
    def _show_add_group_dialog(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
        dialog = QDialog()
        dialog.setWindowTitle("グループを追加")
        dialog.setMinimumWidth(350)
        dialog.setStyleSheet(DIALOG_STYLE)
        dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel("グループ名"))
        name_input = QLineEdit()
        name_input.setPlaceholderText("SNS")
        layout.addWidget(name_input)
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("キャンセル")
        add_btn = QPushButton("追加")
        add_btn.setObjectName("addBtn")
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(add_btn)
        layout.addLayout(btn_layout)
        cancel_btn.clicked.connect(dialog.close)
        def on_accept():
            name = name_input.text().strip()
            if not name:
                return
            g = {"id": f"group_{uuid.uuid4().hex[:8]}", "name": name, "collapsed": False}
            self.config["groups"].append(g)
            save_config(self.config)
            js_eval(f"window.dispatchEvent(new CustomEvent('group-added',{{detail:{json.dumps(g)}}}));")
            dialog.close()
        add_btn.clicked.connect(on_accept)
        name_input.setFocus()
        dialog.exec()

    def _do_rename(self, sid, current_name):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
        dialog = QDialog()
        dialog.setWindowTitle("名前を変更")
        dialog.setMinimumWidth(350)
        dialog.setStyleSheet(DIALOG_STYLE)
        dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel("新しい名前"))
        name_input = QLineEdit(current_name)
        layout.addWidget(name_input)
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("キャンセル")
        ok_btn = QPushButton("変更")
        ok_btn.setObjectName("addBtn")
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)
        cancel_btn.clicked.connect(dialog.reject)
        def on_ok():
            new_name = name_input.text().strip()
            if new_name:
                for s in self.config["services"]:
                    if s["id"] == sid:
                        s["name"] = new_name; break
                save_config(self.config)
                js_eval(f"window.dispatchEvent(new CustomEvent('service-renamed',{{detail:{{id:'{sid}',name:{json.dumps(new_name)}}}}}))")
            dialog.accept()
        ok_btn.clicked.connect(on_ok)
        name_input.setFocus()
        name_input.selectAll()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _do_delete(self, sid, name):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        dialog = QDialog()
        dialog.setWindowTitle("削除確認")
        dialog.setMinimumWidth(320)
        dialog.setStyleSheet(DIALOG_STYLE)
        dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel(f"「{name}」を削除しますか？"))
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("キャンセル")
        del_btn = QPushButton("削除する")
        del_btn.setObjectName("addBtn")
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(del_btn)
        layout.addLayout(btn_layout)
        cancel_btn.clicked.connect(dialog.reject)
        def on_delete():
            self.config["services"] = [s for s in self.config["services"] if s["id"] != sid]
            save_config(self.config)
            self._remove_view(sid)
            js_eval(f"window.dispatchEvent(new CustomEvent('service-removed',{{detail:'{sid}'}}));")
            dialog.accept()
        del_btn.clicked.connect(on_delete)
        dialog.exec()

    @Slot(str)
    def _show_add_dialog(self, group_id_str):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox
        group_id = group_id_str or None
        groups = self.config.get("groups", [])

        dialog = QDialog()
        dialog.setWindowTitle("サービスを追加")
        dialog.setMinimumWidth(400)
        dialog.setStyleSheet(DIALOG_STYLE)
        dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
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

        cancel_btn.clicked.connect(dialog.close)
        def on_accept():
            print("on_accept called", flush=True)
            name = name_input.text().strip()
            url = url_input.text().strip()
            if not name or not url:
                return
            if not url.startswith("http"):
                url = f"https://{url}"
            gid = (group_combo.currentData() or None) if group_combo else (group_id or None)
            svc = {"id": f"service_{uuid.uuid4().hex[:8]}",
                   "name": name, "url": url, "muted": False, "groupId": gid or None}
            self.config["services"].append(svc)
            save_config(self.config)
            self._create_view(svc["id"], url)
            js_eval(f"window.dispatchEvent(new CustomEvent('service-added',{{detail:{json.dumps(svc)}}}));")
            dialog.close()
        add_btn.clicked.connect(on_accept)
        name_input.setFocus()
        dialog.exec()

    @Slot()
    def _show_settings(self):
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
            QPushButton, QComboBox, QTabWidget, QWidget, QGridLayout, QFrame, QScrollArea
        )

        dialog = QDialog()
        dialog.setWindowTitle("設定")
        dialog.setMinimumSize(540, 520)
        dialog.setStyleSheet(DIALOG_STYLE)
        dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("border-bottom: 1px solid rgba(255,255,255,0.05);")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 14, 20, 14)
        title = QLabel("設定")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold; letter-spacing: 2px;")
        hl.addWidget(title)
        hl.addStretch()
        close_btn = QPushButton("×")
        close_btn.setStyleSheet("border: none; color: rgba(255,255,255,0.3); font-size: 18px; padding: 2px 8px;")
        close_btn.clicked.connect(dialog.reject)
        hl.addWidget(close_btn)
        main_layout.addWidget(header)

        tabs = QTabWidget()
        main_layout.addWidget(tabs)

        # 一般
        gen = QWidget()
        gen_l = QVBoxLayout(gen)
        gen_l.setContentsMargins(20, 20, 20, 20)
        gen_l.setSpacing(12)
        lbl = QLabel("休止モード")
        lbl.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 10px; font-family: monospace; letter-spacing: 1px;")
        gen_l.addWidget(lbl)
        desc = QLabel("非アクティブなサービスを指定時間後に自動休止してメモリを解放します")
        desc.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 11px;")
        desc.setWordWrap(True)
        gen_l.addWidget(desc)
        hib_grid = QGridLayout()
        hib_grid.setSpacing(8)
        hib_options = [(0,"無効"),(5,"5分"),(10,"10分"),(15,"15分"),(30,"30分"),(60,"1時間")]
        current_hib = self.config.get("hibernate_minutes", 10)
        hib_btns = []
        active_s = "QPushButton{border-radius:8px;padding:8px;font-size:13px;border:1px solid rgba(255,255,255,0.3);background:rgba(255,255,255,0.1);color:white;}"
        inactive_s = "QPushButton{border-radius:8px;padding:8px;font-size:13px;border:1px solid rgba(255,255,255,0.08);color:rgba(255,255,255,0.4);background:transparent;}QPushButton:hover{border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.7);}"
        def make_hib(val, lbl2, is_active):
            btn = QPushButton(lbl2)
            btn.setStyleSheet(active_s if is_active else inactive_s)
            def on_click(v=val):
                self.config["hibernate_minutes"] = v
                save_config(self.config)
                for b, bv in hib_btns:
                    b.setStyleSheet(active_s if bv == v else inactive_s)
                js_eval(f"window.dispatchEvent(new CustomEvent('hibernate-changed',{{detail:{v}}}));")
            btn.clicked.connect(on_click)
            return btn
        for i, (val, lbl2) in enumerate(hib_options):
            btn = make_hib(val, lbl2, val == current_hib)
            hib_btns.append((btn, val))
            hib_grid.addWidget(btn, i // 3, i % 3)
        gen_l.addLayout(hib_grid)

        # ナレッジ
        gen_l.addSpacing(12)
        know_lbl = QLabel("ナレッジ（自己紹介・背景）")
        know_lbl.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 10px; font-family: monospace; letter-spacing: 1px;")
        gen_l.addWidget(know_lbl)
        know_desc = QLabel("AIへの自己紹介です。感想ボタン使用時に活用されます（200文字以内）")
        know_desc.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 11px;")
        know_desc.setWordWrap(True)
        gen_l.addWidget(know_desc)
        from PySide6.QtWidgets import QTextEdit
        know_input = QTextEdit()
        know_input.setPlaceholderText("例：ライバー事務所の所長で精神保健福祉士です。配信業界のマーケティングやメンタルケアに興味があります。")
        know_input.setMaximumHeight(80)
        know_input.setPlainText(self.config.get("knowledge", ""))
        know_input.setStyleSheet("background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 8px; color: white; font-size: 12px;")
        gen_l.addWidget(know_input)
        know_save = QPushButton("保存")
        know_save.setObjectName("addBtn")
        know_save_msg = QLabel("")
        know_save_msg.setStyleSheet("color: rgba(100,255,150,0.7); font-size: 11px;")
        def on_know_save():
            text = know_input.toPlainText().strip()[:200]
            self.config["knowledge"] = text
            save_config(self.config)
            know_save_msg.setText("✓ 保存しました")
            from PySide6.QtCore import QTimer as _QT3
            _QT3.singleShot(2000, lambda: know_save_msg.setText(""))
        know_save.clicked.connect(on_know_save)
        gen_l.addWidget(know_save)
        gen_l.addWidget(know_save_msg)
        gen_l.addStretch()
        tabs.addTab(gen, "一般")

        # AI/LLM
        ai_w = QWidget()
        ai_scroll = QScrollArea()
        ai_scroll.setWidgetResizable(True)
        ai_scroll.setStyleSheet("QScrollArea{border:none;}")
        ai_scroll.setWidget(ai_w)
        ai_l = QVBoxLayout(ai_w)
        ai_l.setContentsMargins(20, 20, 20, 20)
        ai_l.setSpacing(10)

        def sec_lbl(text):
            l = QLabel(text)
            l.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 10px; font-family: monospace; letter-spacing: 1px;")
            return l
        def text_input(val="", placeholder=""):
            i = QLineEdit()
            i.setText(val)
            i.setPlaceholderText(placeholder)
            return i

        # Ollamaインストール
        ai_l.addWidget(sec_lbl("OLLAMA"))
        ollama_row = QHBoxLayout()
        ollama_status = QLabel("確認中...")
        ollama_status.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 12px;")
        ollama_row.addWidget(ollama_status)
        ollama_row.addStretch()
        install_btn = QPushButton("Ollamaをインストール")
        install_btn.setStyleSheet("QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;border:1px solid rgba(255,255,255,0.15);color:rgba(255,255,255,0.5);background:transparent;}QPushButton:hover{border:1px solid rgba(255,255,255,0.3);color:white;}")
        ollama_row.addWidget(install_btn)
        ai_l.addLayout(ollama_row)

        import subprocess as _sp, urllib.request, json as _j
        ollama_installed = _sp.run(["which","ollama"], capture_output=True).returncode == 0
        if ollama_installed:
            ollama_status.setText("✓ Ollama インストール済み")
            ollama_status.setStyleSheet("color: rgba(100,255,150,0.7); font-size: 12px;")
            install_btn.setVisible(False)
        else:
            ollama_status.setText("✗ Ollamaが見つかりません")
            ollama_status.setStyleSheet("color: rgba(255,100,100,0.7); font-size: 12px;")

        progress_lbl = QLabel("")
        progress_lbl.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 10px;")
        progress_lbl.setWordWrap(True)
        ai_l.addWidget(progress_lbl)

        def on_install_ollama():
            install_btn.setEnabled(False)
            progress_lbl.setText("インストール中...")
            import threading
            def do_install():
                try:
                    result = _sp.run(
                        ["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
                        capture_output=True, text=True, timeout=120
                    )
                    from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                    if result.returncode == 0:
                        QMetaObject.invokeMethod(ollama_status, "setText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, "✓ Ollama インストール済み"))
                        ollama_status.setStyleSheet("color: rgba(100,255,150,0.7); font-size: 12px;")
                        QMetaObject.invokeMethod(progress_lbl, "setText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, "インストール完了！"))
                        QMetaObject.invokeMethod(install_btn, "setVisible", Qt.ConnectionType.QueuedConnection, Q_ARG(bool, False))
                    else:
                        QMetaObject.invokeMethod(progress_lbl, "setText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, f"エラー: {result.stderr[:100]}"))
                        install_btn.setEnabled(True)
                except Exception as e:
                    from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                    QMetaObject.invokeMethod(progress_lbl, "setText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, f"エラー: {e}"))
                    install_btn.setEnabled(True)
            threading.Thread(target=do_install, daemon=True).start()
        install_btn.clicked.connect(on_install_ollama)

        # モデル管理
        ai_l.addWidget(sec_lbl("モデル管理"))
        RECOMMENDED = [
            ("gemma2:9b",       "Gemma 2 9B",     "高品質（Google）"),
            ("qwen2.5:3b",      "Qwen 2.5 3B",    "軽量・多言語対応"),
            ("qwen2.5:7b",      "Qwen 2.5 7B",    "バランス型・多言語"),
            ("llama3.2:latest", "Llama 3.2",      "Meta製汎用モデル"),
            ("mistral:7b",      "Mistral 7B",     "高品質・フランス製"),
        ]
        try:
            with _j and urllib.request.urlopen(
                f"{self.config.get('llm',{}).get('ollamaUrl','http://localhost:11434')}/api/tags", timeout=3
            ) as r:
                installed_models = [m["name"] for m in _j.loads(r.read()).get("models",[])]
        except:
            installed_models = []

        current_model = self.config.get("llm",{}).get("ollamaModel","")
        model_buttons = {}

        for model_id, model_name, model_desc in RECOMMENDED:
            row_w = QFrame()
            row_w.setObjectName("card")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(12, 8, 12, 8)
            col_l = QVBoxLayout()
            col_l.setSpacing(1)
            nm = QLabel(model_name)
            nm.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 12px;")
            ds = QLabel(model_desc)
            ds.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 10px;")
            col_l.addWidget(nm)
            col_l.addWidget(ds)
            row_l.addLayout(col_l)
            row_l.addStretch()
            is_installed = any(model_id.split(":")[0] in m for m in installed_models)
            is_selected = bool(current_model and current_model == model_id)
            st_lbl = QLabel("✓" if is_installed else "")
            st_lbl.setStyleSheet("color: rgba(100,255,150,0.6); font-size: 11px;")
            row_l.addWidget(st_lbl)
            if is_selected:
                ab = QPushButton("使用中")
                ab.setStyleSheet("QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;border:1px solid rgba(100,255,150,0.4);color:rgba(100,255,150,0.8);background:transparent;}")
            elif is_installed:
                ab = QPushButton("選択")
                ab.setStyleSheet("QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.6);background:transparent;}QPushButton:hover{border:1px solid rgba(255,255,255,0.4);color:white;}")
            else:
                ab = QPushButton("ダウンロード")
                ab.setStyleSheet("QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;border:1px solid rgba(100,200,255,0.3);color:rgba(100,200,255,0.7);background:transparent;}QPushButton:hover{border:1px solid rgba(100,200,255,0.6);color:rgba(100,200,255,1.0);}")
            row_l.addWidget(ab)
            model_buttons[model_id] = ab
            ai_l.addWidget(row_w)

            def make_cb(mid=model_id, btn=ab, slb=st_lbl, inst=is_installed):
                if inst:
                    def on_sel(checked=False, m=mid, b=btn):
                        if "llm" not in self.config: self.config["llm"] = {}
                        self.config["llm"]["ollamaModel"] = m
                        self.config["llm"]["backend"] = "ollama"
                        save_config(self.config)
                        for k, v in model_buttons.items():
                            if k == m:
                                v.setText("使用中")
                                v.setStyleSheet("QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;border:1px solid rgba(100,255,150,0.4);color:rgba(100,255,150,0.8);background:transparent;}")
                            elif v.text() == "使用中":
                                v.setText("選択")
                                v.setStyleSheet("QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.6);background:transparent;}QPushButton:hover{border:1px solid rgba(255,255,255,0.4);color:white;}")
                        progress_lbl.setText(f"✓ {m} を選択しました")
                    btn.clicked.connect(on_sel)
                else:
                    def on_dl(m=mid, b=btn, s=slb):
                        b.setEnabled(False)
                        b.setText("DL中...")
                        import threading
                        def do_pull():
                            try:
                                proc = _sp.Popen(["ollama","pull",m], stdout=_sp.PIPE, stderr=_sp.STDOUT, text=True)
                                for line in proc.stdout:
                                    from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                                    QMetaObject.invokeMethod(progress_lbl, "setText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, line.strip()[:80]))
                                proc.wait()
                                from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                                if proc.returncode == 0:
                                    QMetaObject.invokeMethod(s, "setText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, "✓"))
                                    QMetaObject.invokeMethod(b, "setText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, "選択"))
                                    b.setEnabled(True)
                                    b.setStyleSheet("QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.6);background:transparent;}")
                                    if "llm" not in self.config: self.config["llm"] = {}
                                    self.config["llm"]["ollamaModel"] = m
                                    self.config["llm"]["backend"] = "ollama"
                                    save_config(self.config)
                                else:
                                    QMetaObject.invokeMethod(progress_lbl, "setText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, "ダウンロード失敗"))
                                    b.setEnabled(True)
                            except Exception as e:
                                from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                                QMetaObject.invokeMethod(progress_lbl, "setText", Qt.ConnectionType.QueuedConnection, Q_ARG(str, f"エラー: {e}"))
                                b.setEnabled(True)
                        threading.Thread(target=do_pull, daemon=True).start()
                    btn.clicked.connect(on_dl)
            make_cb()

        # APIキー
        ai_l.addWidget(sec_lbl("CLAUDE API キー"))
        claude_in = text_input(self.config.get("llm",{}).get("claudeApiKey",""), "sk-ant-...")
        claude_in.setEchoMode(QLineEdit.EchoMode.Password)
        ai_l.addWidget(claude_in)
        ai_l.addWidget(sec_lbl("GEMINI API キー"))
        gemini_in = text_input(self.config.get("llm",{}).get("geminiApiKey",""), "AIza...")
        gemini_in.setEchoMode(QLineEdit.EchoMode.Password)
        ai_l.addWidget(gemini_in)
        ai_save = QPushButton("APIキーを保存")
        ai_save.setObjectName("addBtn")
        save_msg = QLabel("")
        save_msg.setStyleSheet("color: rgba(100,255,150,0.7); font-size: 11px;")
        def on_ai_save():
            if "llm" not in self.config: self.config["llm"] = {}
            self.config["llm"].update({
                "claudeApiKey": claude_in.text().strip(),
                "geminiApiKey": gemini_in.text().strip(),
            })
            save_config(self.config)
            save_msg.setText("✓ 保存しました")
            from PySide6.QtCore import QTimer as _QT2
            _QT2.singleShot(2000, lambda: save_msg.setText(""))
        ai_save.clicked.connect(on_ai_save)
        ai_l.addWidget(ai_save)
        ai_l.addWidget(save_msg)
        ai_l.addStretch()
        tabs.addTab(ai_scroll, "AI / LLM")



        # データ
        data_w = QWidget()
        data_l = QVBoxLayout(data_w)
        data_l.setContentsMargins(20, 20, 20, 20)
        data_l.setSpacing(10)
        exp_btn = QPushButton("設定をエクスポート（JSON）")
        def on_export():
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(dialog, "保存先", "ink-boss-config.json", "JSON (*.json)")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, ensure_ascii=False, indent=2)
        exp_btn.clicked.connect(on_export)
        data_l.addWidget(exp_btn)
        imp_btn = QPushButton("設定をインポート（JSON）")
        def on_import():
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(dialog, "ファイルを選択", "", "JSON (*.json)")
            if path:
                with open(path, "r", encoding="utf-8") as f:
                    new_cfg = json.load(f)
                self.config.clear()
                self.config.update(new_cfg)
                save_config(self.config)
                js_eval("window.dispatchEvent(new CustomEvent('config-imported'));")
                dialog.accept()
        imp_btn.clicked.connect(on_import)
        data_l.addWidget(imp_btn)
        data_l.addStretch()
        tabs.addTab(data_w, "データ")
        self._settings_dialog = dialog

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def update_geometry(self, sid, x, y, w, h):
        if sid in self.views and sid == self.active_id:
            self.show_view_signal.emit(sid, x, y, w, h)


def js_eval(js: str):
    import threading
    def _eval():
        try:
            if webview.windows:
                webview.windows[0].evaluate_js(js)
        except:
            pass
    threading.Thread(target=_eval, daemon=True).start()


# QApplication生成前にChromiumフラグをsys.argvに追加（全QWebEngineViewに適用）
# --ozone-platform-hint=autoはEcosiaブラウザと同じフラグでfcitx5/ibusを自動検出する
_chromium_flags = ["--ozone-platform-hint=auto", "--enable-features=UseOzonePlatform"]
for _flag in _chromium_flags:
    if _flag not in sys.argv:
        sys.argv.append(_flag)

qt_app = QApplication.instance() or QApplication(sys.argv)
icon_path = Path(__file__).parent / "frontend" / "public" / "icon.png"
if icon_path.exists():
    qt_app.setWindowIcon(QIcon(str(icon_path)))

config = load_config()
bridge = ViewBridge(qt_app, config)
_aide_width = 0
_win_id = None  # wmctrlウィンドウIDキャッシュ


def get_rect(window, aide_w=0):
    return SIDEBAR_W, URLBAR_H, window.width - SIDEBAR_W - aide_w, window.height - URLBAR_H


class InkBossAPI:
    def get_config(self): return config

    def add_service(self, name, url, group_id=None):
        svc = {"id": f"service_{uuid.uuid4().hex[:8]}",
               "name": name, "url": url, "muted": False, "groupId": group_id}
        config["services"].append(svc)
        save_config(config)
        bridge.create_view_signal.emit(svc["id"], url)
        return svc

    def update_service(self, sid, updates):
        for s in config["services"]:
            if s["id"] == sid:
                s.update(updates); break
        save_config(config)

    def remove_service(self, sid):
        config["services"] = [s for s in config["services"] if s["id"] != sid]
        save_config(config)
        bridge.remove_view_signal.emit(sid)

    def move_service(self, sid, gid):
        for s in config["services"]:
            if s["id"] == sid:
                s["groupId"] = gid; break
        save_config(config)

    def copy_service(self, sid, gid):
        orig = next((s for s in config["services"] if s["id"] == sid), None)
        if not orig: return {}
        new_svc = {"id": f"service_{uuid.uuid4().hex[:8]}",
                   "name": orig["name"], "url": orig["url"],
                   "muted": False, "groupId": gid}
        config["services"].append(new_svc)
        save_config(config)
        bridge.create_view_signal.emit(new_svc["id"], new_svc["url"])
        return new_svc

    def add_group(self, name):
        g = {"id": f"group_{uuid.uuid4().hex[:8]}", "name": name, "collapsed": False}
        config["groups"].append(g)
        save_config(config)
        return g

    def update_group(self, gid, name):
        for g in config["groups"]:
            if g["id"] == gid:
                g["name"] = name; break
        save_config(config)

    def remove_group(self, gid, delete_services):
        config["groups"] = [g for g in config["groups"] if g["id"] != gid]
        if delete_services:
            to_rm = [s["id"] for s in config["services"] if s.get("groupId") == gid]
            config["services"] = [s for s in config["services"] if s.get("groupId") != gid]
            for sid in to_rm:
                bridge.remove_view_signal.emit(sid)
        else:
            for s in config["services"]:
                if s.get("groupId") == gid:
                    s["groupId"] = None
        save_config(config)

    def update_llm_config(self, updates):
        config["llm"].update(updates); save_config(config)

    def update_hibernate_minutes(self, minutes):
        config["hibernate_minutes"] = int(minutes); save_config(config)

    def export_config(self): return json.dumps(config, ensure_ascii=False, indent=2)

    def import_config(self, json_str):
        new = json.loads(json_str)
        config.clear(); config.update(new); save_config(config)

    def show_service(self, sid):
        w = webview.windows[0] if webview.windows else None
        if not w: return
        if sid in bridge.hibernated:
            bridge.wake_view_signal.emit(sid, bridge.urls.get(sid, "about:blank"))
            # wake（setUrl）完了後にshowするため少し遅延
            x, y, ww, h = get_rect(w, _aide_width)
            QTimer.singleShot(300, lambda: bridge.show_view_signal.emit(sid, x, y, ww, h))
        else:
            x, y, ww, h = get_rect(w, _aide_width)
            bridge.show_view_signal.emit(sid, x, y, ww, h)

    def hide_service(self): bridge.hide_all_signal.emit()

    def hibernate_service(self, sid): bridge.hibernate_view_signal.emit(sid)

    def wake_service(self, sid):
        bridge.wake_view_signal.emit(sid, bridge.urls.get(sid, "about:blank"))

    def get_hibernated_ids(self): return list(bridge.hibernated)

    def reload_service(self, sid): bridge.reload_view_signal.emit(sid)

    def sync_geometry(self, sid):
        w = webview.windows[0] if webview.windows else None
        if not w or not sid: return
        x, y, ww, h = get_rect(w, _aide_width)
        bridge.update_geometry(sid, x, y, ww, h)

    def show_context_menu(self, sid, name, x, y, is_hib, groups_json):
        bridge.context_menu_signal.emit(sid, name, int(x), int(y), bool(is_hib), groups_json)

    def show_add_service_dialog(self, group_id=None):
        bridge.add_dialog_signal.emit(group_id or "")

    def show_add_group_dialog(self):
        bridge.add_group_dialog_signal.emit()

    def show_group_context_menu(self, gid, name, x, y):
        bridge.group_menu_signal.emit(gid, name, int(x), int(y))

    def reorder_groups(self, group_ids):
        id_order = list(group_ids)
        config["groups"].sort(key=lambda g: id_order.index(g["id"]) if g["id"] in id_order else 999)
        save_config(config)

    def show_settings_dialog(self):
        bridge.settings_signal.emit()

    def close_window(self):
        if webview.windows: webview.windows[0].destroy()

    def minimize_window(self):
        if webview.windows: webview.windows[0].minimize()

    def toggle_maximize(self):
        if webview.windows: webview.windows[0].toggle_fullscreen()

    def drag_window(self): pass

    def update_title(self, title):
        """タイトルバーにURLを表示"""
        w = webview.windows[0] if webview.windows else None
        if w:
            w.title = title

    def set_aide_width(self, width):
        global _aide_width
        _aide_width = int(width)
        w = webview.windows[0] if webview.windows else None
        if not w or not bridge.active_id: return
        x, y, ww, h = get_rect(w, _aide_width)
        bridge.show_view_signal.emit(bridge.active_id, x, y, ww, h)

    def get_page_text(self, service_id):
        return bridge.page_text_cache.get(service_id, "")


    def drag_start(self):
        """ドラッグ開始：キャッシュ済みウィンドウIDでマウス追跡スレッドを起動"""
        import subprocess, threading

        # 二重起動防止
        if getattr(self, "_dragging", False):
            return

        # ウィンドウIDの取得（キャッシュ優先）
        win_id = _win_id
        if not win_id:
            result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if "Ink Boss" in line:
                    win_id = line.split()[0]
                    break
        if not win_id:
            return

        def _get_mouse_pos():
            r = subprocess.run(["xdotool", "getmouselocation", "--shell"],
                               capture_output=True, text=True)
            x, y = 0, 0
            for line in r.stdout.splitlines():
                if line.startswith("X="): x = int(line.split("=")[1])
                elif line.startswith("Y="): y = int(line.split("=")[1])
            return x, y

        def _get_win_pos():
            r = subprocess.run(["xdotool", "getwindowgeometry", "--shell", win_id],
                               capture_output=True, text=True)
            x, y = 0, 0
            for line in r.stdout.splitlines():
                if line.startswith("X="): x = int(line.split("=")[1])
                elif line.startswith("Y="): y = int(line.split("=")[1])
            return x, y

        # 初期位置を確定してからフラグを立ててループ開始（点滅防止）
        mx0, my0 = _get_mouse_pos()
        wx0, wy0 = _get_win_pos()
        self._dragging = True

        def _drag_loop():
            import time
            while getattr(self, "_dragging", False):
                mx, my = _get_mouse_pos()
                dx, dy = mx - mx0, my - my0
                if dx != 0 or dy != 0:
                    subprocess.run([
                        "wmctrl", "-ir", win_id, "-e",
                        f"0,{wx0+dx},{wy0+dy},-1,-1"
                    ], check=False)
                time.sleep(0.016)  # ~60fps

        threading.Thread(target=_drag_loop, daemon=True).start()

    def drag_end(self):
        """ドラッグ終了"""
        self._dragging = False

    def drag_window_by(self, dx, dy):
        """後方互換：単発移動（既存呼び出しが残っている場合のフォールバック）"""
        import subprocess
        w = webview.windows[0] if webview.windows else None
        if not w: return
        result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
        win_id = None
        for line in result.stdout.splitlines():
            if "Ink Boss" in line:
                win_id = line.split()[0]
                break
        if win_id:
            pos_result = subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", win_id],
                capture_output=True, text=True)
            x, y = 0, 0
            for line in pos_result.stdout.splitlines():
                if line.startswith("X="): x = int(line.split("=")[1])
                elif line.startswith("Y="): y = int(line.split("=")[1])
            subprocess.run([
                "wmctrl", "-ir", win_id, "-e",
                f"0,{x+int(dx)},{y+int(dy)},-1,-1"
            ], check=False)


_timer = None
_timer_ref = None


def find_container(main_win):
    for child in main_win.children():
        if type(child).__name__ == "WebView":
            for gc in child.children():
                if type(gc).__name__ == "QWidget":
                    return gc
    return main_win


def on_shown(window):
    global _timer
    # xpropでタイトルバーを削除、同時にウィンドウIDをキャッシュ
    import subprocess, threading
    def hide_titlebar():
        global _win_id
        import time
        time.sleep(1.0)
        result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
        win_id = None
        for line in result.stdout.splitlines():
            if "Ink Boss" in line:
                win_id = line.split()[0]
                break
        if win_id:
            _win_id = win_id  # グローバルにキャッシュ
            subprocess.run(["xprop", "-id", win_id, "-f", "_MOTIF_WM_HINTS", "32c",
                "-set", "_MOTIF_WM_HINTS", "0x2, 0x0, 0x0, 0x0, 0x0"], check=False)
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
        # 背景透過防止：ウィンドウ背景色を明示セット
        from PySide6.QtGui import QPalette, QColor
        palette = main_win.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#080810"))
        main_win.setPalette(palette)
        main_win.setAutoFillBackground(True)
        container = find_container(main_win)
        print(f"[container] {type(container).__name__}", flush=True)
        bridge.set_container(container)

    # bridgeのQtメインスレッドでサービスを初期化
    bridge.init_views_signal.emit()

    global _timer_ref
    def on_resized(width, height):
        if bridge.active_id:
            x, y, w, h = get_rect(window, _aide_width)
            bridge.show_view_signal.emit(bridge.active_id, x, y, w, h)
    window.events.resized += on_resized

    # resizedが縮小時に発火しない場合の保険としてJSからも監視
    # JSのsetIntervalは削除（on_resizedで対応済み）


def main():
    window = webview.create_window(
        "Ink Boss",
        url="http://localhost:5174",
        js_api=InkBossAPI(),
        width=1280,
        height=850,
        min_size=(800, 600),
        background_color="#080810",
    )
    window.events.shown += lambda: on_shown(window)
    webview.start(gui="qt")


if __name__ == "__main__":
    main()
