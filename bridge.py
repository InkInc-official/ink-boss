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
    wake_and_show_signal    = Signal(str, str, int, int, int, int)
    context_menu_signal     = Signal(str, str, int, int, bool, str)
    add_dialog_signal       = Signal(str)
    settings_signal         = Signal()
    add_group_dialog_signal = Signal()
    group_menu_signal       = Signal(str, str, int, int)
    add_group_signal        = Signal(str)
    del_group_signal        = Signal(str)
    init_views_signal       = Signal()   # サービス初期化用（on_shownから呼ぶ）
    # アプリ終了（JS スレッドからでも QueuedConnection で Qt メインスレッドへ）
    app_shutdown_signal     = Signal()

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
        self._shutdown_handler       = None  # callable set by main/api

        # シグナル接続
        self.create_view_signal.connect(self._create_view, Q)
        self.show_view_signal.connect(self._show_view, Q)
        self.hide_all_signal.connect(self._hide_all, Q)
        self.remove_view_signal.connect(self._remove_view, Q)
        self.reload_view_signal.connect(self._reload_view, Q)
        self.hibernate_view_signal.connect(self._hibernate_view, Q)
        self.wake_view_signal.connect(self._wake_view, Q)
        self.wake_and_show_signal.connect(self._wake_and_show, Q)
        self.context_menu_signal.connect(self._show_context_menu, Q)
        self.add_dialog_signal.connect(self._show_add_dialog, Q)
        self.settings_signal.connect(self._show_settings, Q)
        self.add_group_dialog_signal.connect(self._show_add_group_dialog, Q)
        self.group_menu_signal.connect(self._show_group_menu, Q)
        self.add_group_signal.connect(self._add_group, Q)
        self.del_group_signal.connect(self._del_group, Q)
        self.init_views_signal.connect(self._init_views, Q)
        self.app_shutdown_signal.connect(self._on_app_shutdown, Q)

    def set_shutdown_handler(self, fn) -> None:
        """終了処理コールバック（Qt メインスレッドで実行される）。"""
        self._shutdown_handler = fn

    @Slot()
    def _on_app_shutdown(self):
        print("[Close] app_shutdown_signal on Qt main thread", flush=True)
        fn = self._shutdown_handler
        if fn is None:
            print("[Close] no shutdown handler registered", flush=True)
            return
        try:
            fn()
        except Exception as e:
            print(f"[Close] shutdown handler error: {e}", flush=True)
            import os
            os._exit(1)

    # ────────────────────────────────────
    # 初期化
    # ────────────────────────────────────
    @Slot()
    def _init_views(self):
        """Qt エンジンのサービスのみ起動時作成。electron は helper 側 lazy。"""
        services = self.config.get("services", [])
        print(f"[_init_views] services={len(services)}", flush=True)
        for svc in services:
            eng = (svc.get("engine") or "qt").lower()
            if eng in ("electron", "e"):
                print(f"[_init_views] skip qt (electron): {svc['id']}", flush=True)
                continue
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

    @Slot(str, str)
    def _wake_view(self, sid: str, url: str):
        if sid in self.views:
            self.views[sid].setUrl(QUrl(url))
            self.hibernated.discard(sid)
            js_eval(f"window.dispatchEvent(new CustomEvent('service-woke',{{detail:'{sid}'}}))")

    @Slot(str, str, int, int, int, int)
    def _wake_and_show(self, sid: str, url: str, x: int, y: int, w: int, h: int):
        """休止復帰＋表示。300msの表示ディレイはここ（Qtメインスレッド上で
        QueuedConnection経由で実行される）でスケジュールする。
        api.py側（pywebviewのjs_api呼び出しスレッド＝Qtイベントループを
        持たないスレッド）でQTimer.singleShotを直接使うと、タイマーが
        実質的に発火しないままになる不具合があったため、ここに移した。"""
        self._wake_view(sid, url)
        QTimer.singleShot(300, lambda: self.show_view_signal.emit(sid, x, y, w, h))

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
        """安全に破棄。二重呼び出し・deleteLater 後アクセスを許容。"""
        try:
            view = self.views.pop(sid, None)
            if view is not None:
                try:
                    view.hide()
                except Exception:
                    pass
                try:
                    view.setParent(None)
                except Exception:
                    pass
                try:
                    view.deleteLater()
                except Exception:
                    pass
            prof = self.profiles.pop(sid, None)
            if prof is not None:
                try:
                    # 明示破棄はしない（Qt 所有）。参照だけ外す
                    pass
                except Exception:
                    pass
            self.urls.pop(sid, None)
            self.hibernated.discard(sid)
            self.page_text_cache.pop(sid, None)
            if self.active_id == sid:
                self.active_id = None
        except Exception as e:
            print(f"[bridge] _remove_view({sid}) error: {e}", flush=True)

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

    def update_geometry(self, sid: str, x: int, y: int, w: int, h: int):
        if sid in self.views and sid == self.active_id:
            self.show_view_signal.emit(sid, x, y, w, h)

    # ────────────────────────────────────
    # ダイアログ・メニュー
    # ────────────────────────────────────
    @Slot(str, str, int, int, bool, str)
    def _show_context_menu(self, sid, name, x, y, is_hib, groups_json):
        def _destroy_any(s: str) -> None:
            # Qt / Electron どちらでも安全に破棄（存在しない側は no-op）
            try:
                self._remove_view(s)
            except Exception as e:
                print(f"[bridge] qt remove {s}: {e}", flush=True)
            el = getattr(self, "electron", None)
            if el is not None and el.is_available():
                try:
                    el.remove(s)
                except Exception as e:
                    print(f"[bridge] electron remove {s}: {e}", flush=True)

        def _hibernate_any(s: str) -> None:
            svc = next((x for x in self.config.get("services", []) if x["id"] == s), None)
            eng = ((svc or {}).get("engine") or "qt").lower()
            if eng in ("electron", "e"):
                el = getattr(self, "electron", None)
                if el is not None and el.is_available():
                    el.hibernate(s)
                if self.active_id == s:
                    self.active_id = None
            else:
                self._hibernate_view(s)

        def _wake_any(s: str) -> None:
            svc = next((x for x in self.config.get("services", []) if x["id"] == s), None)
            url = (svc or {}).get("url") or self.urls.get(s, "about:blank")
            eng = ((svc or {}).get("engine") or "qt").lower()
            if eng in ("electron", "e"):
                el = getattr(self, "electron", None)
                if el is not None and el.is_available():
                    el.wake(s, url)
                js_eval(
                    f"window.dispatchEvent(new CustomEvent('service-woke',{{detail:'{s}'}}))"
                )
            else:
                self._wake_view(s, url)

        show_service_context_menu(
            sid=sid, name=name, x=x, y=y,
            is_hib=is_hib, groups_json=groups_json,
            config=self.config, js_eval_fn=js_eval,
            wake_view_fn=_wake_any,
            hibernate_view_fn=_hibernate_any,
            create_view_fn=self._create_view,
            remove_view_fn=_destroy_any,
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
