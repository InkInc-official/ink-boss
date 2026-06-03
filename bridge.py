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
        import platform as _plat
        self._is_windows     = _plat.system() == "Windows"
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

        # Windows: 複数pywebviewウィンドウ管理
        self.win_windows:     dict = {}
        self._win_hwnds:      dict = {}
        self._main_window             = None
        self._main_hwnd_cache         = None
        self._win_create_lock         = None
        self._creating_sids:  set  = set()

        # Windows: create_windowをGUIスレッドから呼ぶためのキュー
        # main.pyの webview.start(func=...) 内でキューを処理する
        if self._is_windows:
            import queue
            self._pending_q = queue.Queue()
        else:
            self._pending_q = None

        # Windows(EdgeChromium)ではQWebEngineViewは使わないため
        # QWebEngineView関連シグナルのみスキップする。
        if not self._is_windows:
            self.create_view_signal.connect(self._create_view, Q)
            self.show_view_signal.connect(self._show_view, Q)
            self.hide_all_signal.connect(self._hide_all, Q)
            self.remove_view_signal.connect(self._remove_view, Q)
            self.reload_view_signal.connect(self._reload_view, Q)
            self.hibernate_view_signal.connect(self._hibernate_view, Q)
            self.wake_view_signal.connect(self._wake_view, Q)
            self.init_views_signal.connect(self._init_views, Q)

        self.context_menu_signal.connect(self._show_context_menu, Q)
        self.add_dialog_signal.connect(self._show_add_dialog, Q)
        self.settings_signal.connect(self._show_settings, Q)
        self.add_group_dialog_signal.connect(self._show_add_group_dialog, Q)
        self.group_menu_signal.connect(self._show_group_menu, Q)
        self.add_group_signal.connect(self._add_group, Q)
        self.del_group_signal.connect(self._del_group, Q)

    # ────────────────────────────────────
    # Windows用 複数ウィンドウ管理（SetParent子ウィンドウ方式）
    # ────────────────────────────────────

    def _get_hwnd(self, title_contains: str) -> int | None:
        """タイトルでHWNDを取得（トップレベル + 全子ウィンドウを検索）"""
        import win32gui
        found = []

        # トップレベルウィンドウから検索
        def cb(h, _):
            try:
                if title_contains in win32gui.GetWindowText(h):
                    found.append(h)
            except Exception:
                pass
        win32gui.EnumWindows(cb, None)
        if found:
            return found[0]

        # メイン子ウィンドウからも検索（SetParent後）
        main_hwnd = getattr(self, "_main_hwnd_cache", None)
        if main_hwnd:
            try:
                win32gui.EnumChildWindows(main_hwnd, cb, None)
            except Exception:
                pass

        return found[0] if found else None

    def _get_main_hwnd(self) -> int | None:
        """メインウィンドウのHWNDを返す（pywebviewウィンドウから直接取得）"""
        if getattr(self, "_main_hwnd_cache", None):
            return self._main_hwnd_cache
        # pywebviewウィンドウのタイトルは可変なのでHWNDを直接取得
        # on_shownで_main_hwnd_cacheをセットしておくことが前提
        # フォールバック: タイトル完全一致で検索
        import win32gui, win32process, os
        pid = os.getpid()
        found = []
        def cb(h, _):
            try:
                t = win32gui.GetWindowText(h)
                # 完全一致のみ（「Ink Boss - エクスプローラー」などを除外）
                if t == "Ink Boss":
                    _, p = win32process.GetWindowThreadProcessId(h)
                    if p == pid:
                        found.append(h)
            except Exception:
                pass
        win32gui.EnumWindows(cb, None)
        if found:
            self._main_hwnd_cache = found[0]
        return self._main_hwnd_cache

    def _embed_hwnd(self, sub_hwnd: int, main_hwnd: int, x: int, y: int, w: int, h: int):
        """sub_hwndをmain_hwndの子ウィンドウとして埋め込む"""
        import win32gui, win32con, ctypes
        try:
            style = win32gui.GetWindowLong(sub_hwnd, win32con.GWL_STYLE)
            new_style = (style | 0x40000000) & ~win32con.WS_POPUP & ~win32con.WS_CAPTION
            win32gui.SetWindowLong(sub_hwnd, win32con.GWL_STYLE, new_style)
            ctypes.windll.user32.SetParent(sub_hwnd, main_hwnd)
            ctypes.windll.user32.MoveWindow(sub_hwnd, x, y, w, h, True)
            win32gui.ShowWindow(sub_hwnd, win32con.SW_SHOW)
            SWP_FRAMECHANGED = 0x0020
            SWP_NOACTIVATE   = 0x0010
            ctypes.windll.user32.SetWindowPos(
                sub_hwnd, 0, x, y, w, h,
                SWP_FRAMECHANGED | SWP_NOACTIVATE
            )
            print(f"[embed] {sub_hwnd} → {main_hwnd} at ({x},{y},{w},{h})", flush=True)
            return True
        except Exception as e:
            print(f"[embed] error: {e}", flush=True)
            return False


    @staticmethod
    def _move_offscreen(hwnd):
        """HWNDを画面外に退避（サイズ維持、WebView2が描画し続けるため黒画面にならない）"""
        import ctypes
        try:
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left or 1280
            h = rect.bottom - rect.top or 850
            ctypes.windll.user32.MoveWindow(hwnd, -w - 200, 0, w, h, False)
        except Exception:
            pass

    def _get_service_rect(self) -> tuple[int, int, int, int]:
        """サービス表示領域の座標を返す"""
        from config import SIDEBAR_W, URLBAR_H
        main = self._main_window
        if main:
            w = main.width  - SIDEBAR_W - getattr(self, "_aide_w", 0)
            h = main.height - URLBAR_H
            return SIDEBAR_W, URLBAR_H, w, h
        return 208, 40, 1072, 810

    def win_create(self, sid: str, url: str):
        """Windows: サービス用の隠しpywebviewウィンドウを作成"""
        if sid in self.win_windows:
            return
        import webview, os, pathlib, threading

        self.urls[sid] = url
        self.hibernated.add(sid)

        profile_dir = pathlib.Path.home() / ".inkboss" / "profiles" / sid
        profile_dir.mkdir(parents=True, exist_ok=True)
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = str(profile_dir)

        main = self._main_window
        w = webview.create_window(
            f"InkBoss-{sid}",
            url=url,
            width=main.width  if main else 1280,
            height=main.height if main else 850,
            hidden=True,
            frameless=True,
            easy_drag=False,
            background_color="#080810",
        )
        self.win_windows[sid] = w

        def on_shown(s=sid):
            # on_shownはpywebviewの内部スレッドから呼ばれる
            # win32gui操作はGUIスレッド(_pending_q)経由で行う
            def _do_embed():
                import win32gui, win32con
                main_hwnd = self._get_main_hwnd()
                sub_hwnd  = self._get_hwnd(f"InkBoss-{s}")
                if main_hwnd and sub_hwnd:
                    self._win_hwnds[s] = sub_hwnd
                    x, y, ww, hh = self._get_service_rect()
                    self._embed_hwnd(sub_hwnd, main_hwnd, x, y, ww, hh)
                    # 画面外に退避（サイズ維持）
                    self._move_offscreen(sub_hwnd)
                    print(f"[win_create] embedded & hidden: {s} hwnd={sub_hwnd}", flush=True)
                    # このサービスが表示待ちなら即表示
                    if self.active_id == s:
                        self._show_hwnd_now(s, sub_hwnd)
                else:
                    print(f"[win_create] HWND not found: main={main_hwnd} sub={sub_hwnd}", flush=True)
                    # リトライをスケジュール（0.5秒後に再度_pending_qへ）
                    import time
                    def _retry():
                        time.sleep(0.5)
                        if self._pending_q:
                            self._pending_q.put(_do_embed)
                    threading.Thread(target=_retry, daemon=True).start()

            # 0.3秒待ってからGUIスレッドに投入（WebView2の初期化完了を待つ）
            def _schedule():
                import time
                time.sleep(0.3)
                if self._pending_q:
                    self._pending_q.put(_do_embed)
            threading.Thread(target=_schedule, daemon=True).start()

        w.events.shown += on_shown
        print(f"[win_create] {sid} url={url}", flush=True)

    def _get_sub_hwnd(self, sid: str) -> int | None:
        """キャッシュからサービスのHWNDを返す。なければ再検索"""
        cached = self._win_hwnds.get(sid)
        if cached:
            return cached
        # フォールバック: タイトルで再検索（EnumWindowsとEnumChildWindows両方試す）
        import win32gui, ctypes
        title = f"InkBoss-{sid}"
        # まずトップレベルから
        h = self._get_hwnd(title)
        if h:
            self._win_hwnds[sid] = h
            return h
        # 次にメイン子ウィンドウから
        main_hwnd = self._get_main_hwnd()
        if main_hwnd:
            found = []
            def cb(h2, _):
                try:
                    if title in win32gui.GetWindowText(h2):
                        found.append(h2)
                except Exception:
                    pass
            try:
                win32gui.EnumChildWindows(main_hwnd, cb, None)
            except Exception:
                pass
            if found:
                self._win_hwnds[sid] = found[0]
                return found[0]
        return None

    def win_show(self, sid: str):
        """Windows: 指定サービスのウィンドウを前面に出し、他を隠す"""
        import ctypes, win32gui, win32con

        # 他のサービスウィンドウを画面外に退避（サイズ維持）
        for s, h in self._win_hwnds.items():
            if s != sid and h:
                self._move_offscreen(h)

        self.hibernated.discard(sid)
        self.active_id = sid

        sub_hwnd = self._win_hwnds.get(sid)

        if sub_hwnd:
            # embed済み → 即表示
            self._show_hwnd_now(sid, sub_hwnd)
        else:
            # 未embed → on_shown_lazyの_do_embedが完了次第active_idを見て自動表示される
            # JSには即座にwoke通知（UIのローディング表示のため）
            js_eval(f"window.dispatchEvent(new CustomEvent('service-woke',{{detail:'{sid}'}}))")

    def _show_hwnd_now(self, sid: str, sub_hwnd: int):
        """HWNDが確定しているサービスを即座に表示（GUIスレッドから呼ぶこと）"""
        import win32gui, win32con, ctypes
        main_hwnd = self._get_main_hwnd()
        if not main_hwnd:
            return
        x, y, w, h = self._get_service_rect()
        parent = ctypes.windll.user32.GetParent(sub_hwnd)
        if parent != main_hwnd:
            self._embed_hwnd(sub_hwnd, main_hwnd, x, y, w, h)
        else:
            ctypes.windll.user32.MoveWindow(sub_hwnd, x, y, w, h, True)
            win32gui.ShowWindow(sub_hwnd, win32con.SW_SHOW)
        print(f"[win_show] shown: {sid} hwnd={sub_hwnd}", flush=True)
        js_eval(f"window.dispatchEvent(new CustomEvent('service-woke',{{detail:'{sid}'}}))")

    def win_update_geometry(self, aide_w: int = 0):
        """Windows: リサイズ・Aide開閉時にアクティブサービスの位置を更新"""
        self._aide_w = aide_w
        if not self.active_id:
            return
        sub_hwnd = self._get_sub_hwnd(self.active_id)
        if not sub_hwnd:
            return
        import ctypes
        x, y, w, h = self._get_service_rect()
        ctypes.windll.user32.MoveWindow(sub_hwnd, x, y, w, h, True)



    def win_remove(self, sid: str):
        """Windows: サービスウィンドウを破棄
        win_removeはremove_serviceの_do_remove(_pending_q)から呼ばれる。
        destroy()はGUIスレッドからのデッドロックを避けるため別スレッドで実行。
        """
        import win32gui, win32con, ctypes
        h = self._win_hwnds.get(sid)
        if h:
            try:
                self._move_offscreen(h)
                ctypes.windll.user32.SetParent(h, 0)
                style = win32gui.GetWindowLong(h, win32con.GWL_STYLE)
                win32gui.SetWindowLong(h, win32con.GWL_STYLE,
                    (style & ~0x40000000) | win32con.WS_POPUP)
                # SetParent解除後は画面外のまま（_move_offscreen済み）
            except Exception as e:
                print(f"[win_remove] detach error: {e}", flush=True)

        # 管理情報を先にクリア
        w = self.win_windows.pop(sid, None)
        self._win_hwnds.pop(sid, None)
        self._creating_sids.discard(sid)
        self.urls.pop(sid, None)
        self.hibernated.discard(sid)
        if self.active_id == sid:
            self.active_id = None

        # js_evalでservice-removedを発火（storeからも削除）
        try:
            js_eval(f"window.dispatchEvent(new CustomEvent('service-removed',{{detail:'{sid}'}}))")
        except Exception:
            pass

        # destroy()はpywebviewの内部スレッドで実行（GUIスレッド外）
        if w:
            import threading, time
            def _destroy_later():
                time.sleep(0.3)
                try:
                    w.destroy()
                    print(f"[win_remove] destroyed: {sid}", flush=True)
                except Exception as e:
                    print(f"[win_remove] destroy error (ignored): {e}", flush=True)
            threading.Thread(target=_destroy_later, daemon=True).start()
        print(f"[win_remove] cleanup done: {sid}", flush=True)

    def win_reload(self, sid: str):
        """Windows: サービスウィンドウをリロード"""
        if sid in self.win_windows and sid not in self.hibernated:
            try:
                self.win_windows[sid].load_url(self.urls.get(sid, "about:blank"))
            except Exception:
                pass

    def win_hibernate(self, sid: str):
        """Windows: サービスを休止"""
        import ctypes
        self.hibernated.add(sid)
        h = self._get_sub_hwnd(sid)
        if h:
            self._move_offscreen(h)
        if self.active_id == sid:
            self.active_id = None

    def win_wake(self, sid: str):
        """Windows: サービスを復帰"""
        self.hibernated.discard(sid)
        self.win_show(sid)

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
        print(f"[bridge] container set: {type(widget).__name__ if widget else 'None'}", flush=True)

    def _get_container(self):
        """
        containerを返す。Noneの場合はQApplicationのトップレベルウィジェットから
        最大ウィンドウをフォールバックとして使用する。
        QWebEngineViewの親がNoneだとウィンドウに描画されないため必須。
        """
        if self.container is not None:
            return self.container
        # フォールバック: 最大の可視トップレベルウィジェット
        from PySide6.QtWidgets import QApplication
        widgets = [w for w in QApplication.topLevelWidgets()
                   if w.isVisible() and w.width() > 400]
        if widgets:
            fallback = max(widgets, key=lambda w: w.width() * w.height())
            print(f"[bridge] container fallback: {type(fallback).__name__} "
                  f"{fallback.width()}x{fallback.height()}", flush=True)
            return fallback
        return None

    # ────────────────────────────────────
    # WebView 操作
    # ────────────────────────────────────
    @Slot(str, str)
    def _create_view(self, sid: str, url: str):
        if sid in self.views:
            return
        self.urls[sid] = url

        container = self._get_container()
        if container is None:
            # コンテナがまだ準備できていない場合は500ms後に再試行
            print(f"[_create_view] container not ready for {sid}, retry in 500ms", flush=True)
            QTimer.singleShot(500, lambda: self._create_view(sid, url))
            return

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
        view = QWebEngineView(container)
        view.setPage(page)
        view.setUrl(QUrl("about:blank"))
        self.hibernated.add(sid)
        view.hide()
        self.profiles[sid] = profile
        self.views[sid] = view
        print(f"[_create_view] created: {sid} container={type(container).__name__}", flush=True)

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
        g = {"id": f"group_{uuid.uuid4().hex[:8]}", "name": name, "collapsed": True}
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
