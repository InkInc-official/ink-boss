"""
bridge.py - ViewBridge
Ink Boss / Ink Inc.

QWebEngineViewの生成・表示・休止・復帰・削除を管理する。
JS↔Pythonのシグナル橋渡しもここで行う。
"""

import json
import threading
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineSettings, QWebEngineNewWindowRequest
)
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QRect, Qt, QUrl

from config import SESSIONS_DIR, save_config
from dialogs.settings     import show_settings_dialog
from dialogs.add_service  import show_add_service_dialog
from dialogs.add_group    import show_add_group_dialog
from dialogs.context_menu import show_service_context_menu, show_group_context_menu

Q = Qt.ConnectionType.QueuedConnection

# グローバル参照（window.pyで初期化後セット）
_win_id: str | None = None


def set_win_id(wid: str) -> None:
    global _win_id
    _win_id = wid


def get_win_id() -> str | None:
    return _win_id


class _CustomPage(QWebEnginePage):
    """
    Googleなどのリダイレクト型リンクを正しく処理するカスタムPage。

    デフォルトのQWebEnginePageは NavigationTypeLink を外部URLへ
    遷移しようとするとブロックすることがある。
    acceptNavigationRequest を常時Trueにして全ナビゲーションを許可する。
    また、target="_blank" などの新規ウィンドウ要求を同じViewで開く。
    """
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.newWindowRequested.connect(self._on_new_window)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        # すべてのナビゲーションを許可
        return True

    def _on_new_window(self, request: QWebEngineNewWindowRequest):
        # 新規ウィンドウ要求（target="_blank"等）は同じページで開く
        self.setUrl(request.requestedUrl())


class ViewBridge(QObject):
    # ─── シグナル定義 ───
    create_view_signal      = Signal(str, str)
    show_view_signal        = Signal(str, int, int, int, int)
    hide_all_signal         = Signal()
    remove_view_signal      = Signal(str)
    reload_view_signal      = Signal(str)
    hibernate_view_signal   = Signal(str)
    wake_view_signal        = Signal(str, str)
    context_menu_signal     = Signal(str, str, int, int, bool, str)
    add_dialog_signal       = Signal(str)
    settings_signal         = Signal()
    add_group_dialog_signal = Signal()
    group_menu_signal       = Signal(str, str, int, int)
    add_group_signal        = Signal(str)
    del_group_signal        = Signal(str)
    init_views_signal       = Signal()   # サービス初期化用（on_shownから呼ぶ）

    def __init__(self, qt_app, config: dict):
        super().__init__()
        self.qt_app          = qt_app
        self.config          = config
        self.views:           dict = {}
        self.profiles:        dict = {}
        self.urls:            dict = {}
        self.hibernated:      set  = set()
        self.active_id:       str | None = None
        self.container               = None
        self._active_menu            = None
        self._pending_js             = None
        self.page_text_cache: dict   = {}
        self._active_menu_holder     = [None]

        # シグナル接続
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

    # ────────────────────────────────────
    # 初期化
    # ────────────────────────────────────
    @Slot()
    def _init_views(self):
        print(f"[_init_views] services={len(self.config.get('services', []))}", flush=True)
        for svc in self.config.get("services", []):
            print(f"[_init_views] emit create_view: {svc['id']}", flush=True)
            self.create_view_signal.emit(svc["id"], svc["url"])

    def set_container(self, widget):
        self.container = widget

    # ────────────────────────────────────
    # WebView 操作
    # ────────────────────────────────────
    @Slot(str, str)
    def _create_view(self, sid: str, url: str):
        if sid in self.views:
            return
        self.urls[sid] = url
        profile = QWebEngineProfile(sid, self.qt_app)
        profile.setPersistentStoragePath(str(SESSIONS_DIR / sid))
        profile.setHttpUserAgent(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = _CustomPage(profile, self.qt_app)
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
                js_eval(
                    f"window.dispatchEvent(new CustomEvent('page-text-ready',{{detail:{payload}}}))"
                )

        def on_load_finished(ok, s=sid):
            if not ok:
                return
            v = self.views.get(s)
            if v is None:
                return
            if v.url().toString() in ("about:blank", "", "about:blank#blocked"):
                return
            print(f"[cache:load] {s}", flush=True)
            v.page().runJavaScript("document.body.innerText", _push_text)

        view.loadFinished.connect(on_load_finished)

        def on_url_changed(url_obj, s=sid):
            url_str = url_obj.toString()
            if url_str in ("about:blank", "", "about:blank#blocked"):
                return
            def delayed():
                v = self.views.get(s)
                if v:
                    v.page().runJavaScript("document.body.innerText", _push_text)
            QTimer.singleShot(1500, delayed)

        view.urlChanged.connect(on_url_changed)

    @Slot(str, int, int, int, int)
    def _show_view(self, sid: str, x: int, y: int, w: int, h: int):
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
        # IME有効化：X11フォーカスをメインウィンドウに移す
        wid = get_win_id()
        if wid:
            import subprocess
            def _force_focus(wid_hex):
                import time
                time.sleep(0.2)
                subprocess.run(["wmctrl", "-ia", wid_hex], check=False, capture_output=True)
                time.sleep(0.1)
                subprocess.run(["fcitx5-remote", "-o"], check=False, capture_output=True)
            threading.Thread(target=_force_focus, args=(wid,), daemon=True).start()
        self.active_id = sid

    @Slot()
    def _hide_all(self):
        for v in self.views.values():
            v.hide()
        self.active_id = None

    @Slot(str)
    def _remove_view(self, sid: str):
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
    def _reload_view(self, sid: str):
        if sid in self.views and sid not in self.hibernated:
            self.views[sid].reload()

    @Slot(str)
    def _hibernate_view(self, sid: str):
        from PySide6.QtCore import QUrl
        if sid in self.views and sid not in self.hibernated:
            self.views[sid].setUrl(QUrl("about:blank"))
            self.hibernated.add(sid)
            if self.active_id == sid:
                self.views[sid].hide()
                self.active_id = None

    @Slot(str, str)
    def _wake_view(self, sid: str, url: str):
        from PySide6.QtCore import QUrl
        if sid in self.views:
            self.views[sid].setUrl(QUrl(url))
            self.hibernated.discard(sid)
            js_eval(f"window.dispatchEvent(new CustomEvent('service-woke',{{detail:'{sid}'}}))") 

    def update_geometry(self, sid: str, x: int, y: int, w: int, h: int):
        if sid in self.views and sid == self.active_id:
            self.show_view_signal.emit(sid, x, y, w, h)

    # ────────────────────────────────────
    # ダイアログ・メニュー
    # ────────────────────────────────────
    @Slot(str, str, int, int, bool, str)
    def _show_context_menu(self, sid, name, x, y, is_hib, groups_json):
        show_service_context_menu(
            sid=sid, name=name, x=x, y=y,
            is_hib=is_hib, groups_json=groups_json,
            config=self.config, js_eval_fn=js_eval,
            wake_view_fn=lambda s: self._wake_view(s, self.urls.get(s, "about:blank")),
            hibernate_view_fn=self._hibernate_view,
            create_view_fn=self._create_view,
            active_menu_holder=self._active_menu_holder,
        )

    @Slot(str)
    def _show_add_dialog(self, group_id_str: str):
        show_add_service_dialog(
            config=self.config,
            js_eval_fn=js_eval,
            create_view_fn=self._create_view,
            group_id=group_id_str,
        )

    @Slot()
    def _show_settings(self):
        show_settings_dialog(config=self.config, js_eval_fn=js_eval)

    @Slot()
    def _show_add_group_dialog(self):
        show_add_group_dialog(config=self.config, js_eval_fn=js_eval)

    @Slot(str, str, int, int)
    def _show_group_menu(self, gid, name, x, y):
        show_group_context_menu(
            gid=gid, name=name, x=x, y=y,
            config=self.config, js_eval_fn=js_eval,
            active_menu_holder=self._active_menu_holder,
        )

    @Slot(str)
    def _add_group(self, name: str):
        import uuid
        g = {"id": f"group_{uuid.uuid4().hex[:8]}", "name": name, "collapsed": False}
        self.config["groups"].append(g)
        save_config(self.config)
        threading.Thread(
            target=lambda: js_eval(
                f"window.dispatchEvent(new CustomEvent('group-added',{{detail:{json.dumps(g)}}}));"
            ),
            daemon=True,
        ).start()

    @Slot(str)
    def _del_group(self, gid: str):
        self.config["groups"] = [x for x in self.config["groups"] if x["id"] != gid]
        for s in self.config["services"]:
            if s.get("groupId") == gid:
                s["groupId"] = None
        save_config(self.config)
        threading.Thread(
            target=lambda: js_eval(
                f"window.dispatchEvent(new CustomEvent('group-removed',{{detail:'{gid}'}}));"
            ),
            daemon=True,
        ).start()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# JS評価ユーティリティ（モジュールレベル）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def js_eval(js: str) -> None:
    """pywebviewウィンドウにJSを非同期評価させる。"""
    import webview
    def _eval():
        try:
            if webview.windows:
                webview.windows[0].evaluate_js(js)
        except Exception:
            pass
    threading.Thread(target=_eval, daemon=True).start()
