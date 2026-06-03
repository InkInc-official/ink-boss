"""
api.py - InkBossAPI
Ink Boss / Ink Inc.

pywebviewのjs_apiとして登録するクラス。
JSからPythonの機能を呼び出す橋渡しをする。
"""

import json
import platform as _platform
import uuid
import webview

from config import save_config
from bridge import js_eval

_IS_WINDOWS = _platform.system() == "Windows"

# Linux専用: QTimerのimportはWindowsでは行わない（WebView2破壊防止）
if not _IS_WINDOWS:
    from PySide6.QtCore import QTimer


class InkBossAPI:
    """pywebview js_api クラス。メソッドはすべてJSから呼び出される。"""

    def __init__(self, config: dict, bridge, get_rect_fn, aide_width_getter):
        """
        Args:
            config:           共有configオブジェクト
            bridge:           ViewBridgeインスタンス
            get_rect_fn:      get_rect(window, aide_w) → (x,y,w,h)
            aide_width_getter: () → int  現在の_aide_width
        """
        self._config          = config
        self._bridge          = bridge
        self._get_rect        = get_rect_fn
        self._aide_width      = aide_width_getter   # callable
        self._aide_width_val  = 0                   # 実値（set_aide_widthで更新）

    # ────────────────────────────────────
    # 設定
    # ────────────────────────────────────
    def get_config(self):
        return self._config

    def update_llm_config(self, updates):
        self._config["llm"].update(updates)
        save_config(self._config)

    def update_hibernate_minutes(self, minutes):
        self._config["hibernate_minutes"] = int(minutes)
        save_config(self._config)

    def export_config(self):
        return json.dumps(self._config, ensure_ascii=False, indent=2)

    def import_config(self, json_str):
        new = json.loads(json_str)
        self._config.clear()
        self._config.update(new)
        save_config(self._config)

    # ────────────────────────────────────
    # サービス
    # ────────────────────────────────────
    def add_service(self, name, url, group_id=None):
        import platform
        svc = {
            "id": f"service_{uuid.uuid4().hex[:8]}",
            "name": name, "url": url, "muted": False, "groupId": group_id,
        }
        self._config["services"].append(svc)
        save_config(self._config)
        if platform.system() == "Windows":
            self._bridge.win_create(svc["id"], url)
        else:
            self._bridge.create_view_signal.emit(svc["id"], url)
        return svc

    def update_service(self, sid, updates):
        for s in self._config["services"]:
            if s["id"] == sid:
                s.update(updates)
                break
        save_config(self._config)

    def remove_service(self, sid):
        import platform
        print(f"[remove_service] called: {sid}", flush=True)
        self._config["services"] = [s for s in self._config["services"] if s["id"] != sid]
        save_config(self._config)
        print(f"[remove_service] config saved, platform={platform.system()}", flush=True)
        if platform.system() == "Windows":
            def _do_remove():
                print(f"[remove_service] _do_remove executing: {sid}", flush=True)
                self._bridge.win_remove(sid)
            if self._bridge._pending_q is not None:
                self._bridge._pending_q.put(_do_remove)
                print(f"[remove_service] queued _do_remove: {sid}", flush=True)
            else:
                _do_remove()
        else:
            self._bridge.remove_view_signal.emit(sid)

    def move_service(self, sid, gid):
        for s in self._config["services"]:
            if s["id"] == sid:
                s["groupId"] = gid
                break
        save_config(self._config)

    def copy_service(self, sid, gid):
        orig = next((s for s in self._config["services"] if s["id"] == sid), None)
        if not orig:
            return {}
        new_svc = {
            "id": f"service_{uuid.uuid4().hex[:8]}",
            "name": orig["name"], "url": orig["url"],
            "muted": False, "groupId": gid,
        }
        self._config["services"].append(new_svc)
        save_config(self._config)
        if _IS_WINDOWS:
            self._bridge.win_create(new_svc["id"], new_svc["url"])
        else:
            self._bridge.create_view_signal.emit(new_svc["id"], new_svc["url"])
        return new_svc

    def show_service(self, sid):
        import platform, threading
        print(f"[show_service] called: {sid}", flush=True)
        if platform.system() == "Windows":
            svc = next((s for s in self._config["services"] if s["id"] == sid), None)
            if not svc:
                return

            # 同じサービスへの連続呼び出しを防ぐ（dblclick等でclick+dblclick両方発火するため）
            if self._bridge.active_id == sid and sid in self._bridge._win_hwnds:
                print(f"[show_service] already active, skip: {sid}", flush=True)
                return

            self._bridge.active_id = sid
            self._bridge.hibernated.discard(sid)

            # 他のウィンドウを画面外退避（SW_HIDEは黒画面の原因のため使わない）
            for s, h in self._bridge._win_hwnds.items():
                if s != sid and h:
                    self._bridge._move_offscreen(h)

            if sid in self._bridge._win_hwnds:
                self._bridge._show_hwnd_now(sid, self._bridge._win_hwnds[sid])
                return

            if sid in self._bridge.win_windows:
                self._bridge.win_show(sid)
                return

            if not hasattr(self._bridge, "_creating_sids"):
                self._bridge._creating_sids = set()
            if sid in self._bridge._creating_sids:
                self._bridge.win_show(sid)
                return
            self._bridge._creating_sids.add(sid)

            from bridge import js_eval
            js_eval(f"window.dispatchEvent(new CustomEvent('service-woke',{{detail:\'{sid}\'}}))") 

            def _do_create(s=sid, service=svc):
                import os, pathlib, webview as _webview, time
                print(f"[lazy] creating window for: {s}", flush=True)
                profile_dir = pathlib.Path.home() / ".inkboss" / "profiles" / s
                profile_dir.mkdir(parents=True, exist_ok=True)
                os.environ["WEBVIEW2_USER_DATA_FOLDER"] = str(profile_dir)
                print(f"[lazy] profile set: {s}", flush=True)
                self._bridge.urls[s] = service["url"]
                main_win = self._bridge._main_window
                print(f"[lazy] calling create_window: {s}", flush=True)
                w = _webview.create_window(
                    f"InkBoss-{s}",
                    url=service["url"],
                    width=main_win.width  if main_win else 1280,
                    height=main_win.height if main_win else 850,
                    hidden=True, frameless=True, easy_drag=False,
                    background_color="#080810",
                )
                self._bridge.win_windows[s] = w
                print(f"[lazy] create_window done: {s}", flush=True)

                def on_shown_lazy(ss=s):
                    print(f"[lazy] on_shown_lazy called: {ss}", flush=True)
                    def _wait_then_embed():
                        import time
                        sub_hwnd = None
                        deadline = time.time() + 20.0
                        while time.time() < deadline:
                            sub_hwnd = self._bridge._get_hwnd(f"InkBoss-{ss}")
                            if sub_hwnd:
                                break
                            time.sleep(0.2)
                        self._bridge._creating_sids.discard(ss)
                        if not sub_hwnd:
                            print(f"[lazy] HWND not found: {ss}", flush=True)
                            return
                        def _do_embed_gui():
                            import ctypes, win32gui, win32con
                            main_hwnd = self._bridge._get_main_hwnd()
                            if not main_hwnd:
                                return
                            self._bridge._win_hwnds[ss] = sub_hwnd
                            x, y, ww, hh = self._bridge._get_service_rect()
                            self._bridge._embed_hwnd(sub_hwnd, main_hwnd, x, y, ww, hh)
                            if self._bridge.active_id == ss:
                                ctypes.windll.user32.MoveWindow(sub_hwnd, x, y, ww, hh, True)
                                win32gui.ShowWindow(sub_hwnd, win32con.SW_SHOW)
                                print(f"[lazy] shown: {ss} hwnd={sub_hwnd}", flush=True)
                                js_eval(f"window.dispatchEvent(new CustomEvent(\'service-woke\',{{detail:\'{ss}\'}}))") 
                            else:
                                self._bridge._move_offscreen(sub_hwnd)
                                print(f"[lazy] embedded (not active): {ss}", flush=True)
                        if self._bridge._pending_q is not None:
                            self._bridge._pending_q.put(_do_embed_gui)
                        else:
                            _do_embed_gui()
                    threading.Thread(target=_wait_then_embed, daemon=True).start()

                w.events.shown += on_shown_lazy
                def on_loaded_lazy(ss=s):
                    if ss not in self._bridge._win_hwnds:
                        print(f"[lazy] on_loaded_lazy fallback: {ss}", flush=True)
                        on_shown_lazy(ss)
                w.events.loaded += on_loaded_lazy

            if self._bridge._pending_q is not None:
                print(f"[show_service] queuing _do_create for: {sid}", flush=True)
                self._bridge._pending_q.put(_do_create)
                print(f"[show_service] queued: {sid}", flush=True)
            else:
                threading.Thread(target=_do_create, daemon=True).start()
            return

    def hide_service(self):
        import platform
        if platform.system() == "Windows":
            pass  # 廃止済み（HWND管理はshow_service内で完結）
        else:
            self._bridge.hide_all_signal.emit()

    def hibernate_service(self, sid):
        import platform
        if platform.system() == "Windows":
            self._bridge.win_hibernate(sid)
        else:
            self._bridge.hibernate_view_signal.emit(sid)

    def wake_service(self, sid):
        import platform
        if platform.system() == "Windows":
            self._bridge.win_wake(sid)
        else:
            self._bridge.wake_view_signal.emit(sid, self._bridge.urls.get(sid, "about:blank"))

    def get_hibernated_ids(self):
        import platform
        if platform.system() == "Windows":
            # 完全遅延ロード: 起動時は全サービスをhibernated扱い
            all_ids = [s["id"] for s in self._config.get("services", [])]
            self._bridge.hibernated.update(all_ids)
        return list(self._bridge.hibernated)

    def reload_service(self, sid):
        import platform
        if platform.system() == "Windows":
            self._bridge.win_reload(sid)
        else:
            self._bridge.reload_view_signal.emit(sid)

    def sync_geometry(self, sid):
        w = webview.windows[0] if webview.windows else None
        if not w or not sid:
            return
        x, y, ww, h = self._get_rect(w, self._aide_width_val)
        self._bridge.update_geometry(sid, x, y, ww, h)

    def poll_gui_queue(self):
        """JSから定期的に呼ばれる。GUIキューの処理をGUIスレッドで実行する。"""
        poll_fn = getattr(self._bridge, "_poll_gui_queue", None)
        if poll_fn:
            poll_fn()

    # ────────────────────────────────────
    # コンテキスト（知識）
    # ────────────────────────────────────
    def save_knowledge(self, text: str):
        """InkAideで使うコンテキスト（自己紹介）を保存する。"""
        self._config["knowledge"] = str(text)[:200]
        save_config(self._config)

    # ────────────────────────────────────
    # Ollama管理
    # ────────────────────────────────────
    def install_ollama(self):
        """OllamaをWindowsにインストールする（公式インストーラーをブラウザで開く）。"""
        import subprocess, platform
        if platform.system() == "Windows":
            subprocess.Popen(["start", "https://ollama.com/download"], shell=True)
            return "ブラウザでOllamaダウンロードページを開きました"
        else:
            return "Linuxでは: curl -fsSL https://ollama.com/install.sh | sh"

    def pull_ollama_model(self, model_name: str):
        """Ollamaモデルをダウンロードする。"""
        import subprocess, threading
        url = self._config.get("llm", {}).get("ollamaUrl", "http://localhost:11434")
        def _pull():
            try:
                import urllib.request, json as _json
                req = urllib.request.Request(
                    f"{url}/api/pull",
                    data=_json.dumps({"name": model_name, "stream": False}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=300) as resp:
                    resp.read()
                from bridge import js_eval
                js_eval(f"window.dispatchEvent(new CustomEvent('ollama-pull-done',{{detail:'{model_name}'}}))")
            except Exception as e:
                print(f"[ollama pull] error: {e}", flush=True)
        threading.Thread(target=_pull, daemon=True).start()
        return f"{model_name} のダウンロードを開始しました"

    # ────────────────────────────────────
    # グループ
    # ────────────────────────────────────
    def add_group(self, name):
        g = {"id": f"group_{uuid.uuid4().hex[:8]}", "name": name, "collapsed": True}
        self._config["groups"].append(g)
        save_config(self._config)
        return g

    def update_group(self, gid, name):
        for g in self._config["groups"]:
            if g["id"] == gid:
                g["name"] = name
                break
        save_config(self._config)

    def update_group_collapsed(self, gid, collapsed):
        """グループの折りたたみ状態を永続化する。"""
        for g in self._config["groups"]:
            if g["id"] == gid:
                g["collapsed"] = bool(collapsed)
                break
        save_config(self._config)

    def remove_group(self, gid, delete_services):
        self._config["groups"] = [g for g in self._config["groups"] if g["id"] != gid]
        if delete_services:
            to_rm = [s["id"] for s in self._config["services"] if s.get("groupId") == gid]
            self._config["services"] = [
                s for s in self._config["services"] if s.get("groupId") != gid
            ]
            for sid in to_rm:
                if _IS_WINDOWS:
                    self._bridge.win_remove(sid)
                else:
                    self._bridge.remove_view_signal.emit(sid)
        else:
            for s in self._config["services"]:
                if s.get("groupId") == gid:
                    s["groupId"] = None
        save_config(self._config)

    def reorder_groups(self, group_ids):
        id_order = list(group_ids)
        self._config["groups"].sort(
            key=lambda g: id_order.index(g["id"]) if g["id"] in id_order else 999
        )
        save_config(self._config)

    def save_service_order(self, service_ids):
        """D&D後のサービス並び順を永続化する。"""
        id_order = list(service_ids)
        self._config["services"].sort(
            key=lambda s: id_order.index(s["id"]) if s["id"] in id_order else 999
        )
        save_config(self._config)

    # ────────────────────────────────────
    # ダイアログ
    # ────────────────────────────────────
    def show_context_menu(self, sid, name, x, y, is_hib, groups_json):
        import platform
        if platform.system() == "Windows":
            from bridge import js_eval
            import json
            # サイドバー上の右クリックなのでHWND退避は不要
            payload = json.dumps({
                "sid": sid, "name": name, "x": x, "y": y,
                "isHib": bool(is_hib), "groups": json.loads(groups_json) if groups_json else []
            })
            js_eval(f"window.dispatchEvent(new CustomEvent('show-context-menu',{{detail:{payload}}}))")
        else:
            from config import SIDEBAR_W
            self._bridge.context_menu_signal.emit(sid, name, int(x) + SIDEBAR_W, int(y), bool(is_hib), groups_json)



    def show_add_service_dialog(self, group_id=None):
        import platform
        if platform.system() == "Windows":
            from bridge import js_eval
            gid = group_id or ""
            js_eval(f"window.dispatchEvent(new CustomEvent('show-add-service-dialog',{{detail:'{gid}'}}))") 
        else:
            self._bridge.add_dialog_signal.emit(group_id or "")

    def show_add_group_dialog(self):
        import platform
        if platform.system() == "Windows":
            from bridge import js_eval
            js_eval("window.dispatchEvent(new CustomEvent('show-add-group-dialog'))")
        else:
            self._bridge.add_group_dialog_signal.emit()

    def show_group_context_menu(self, gid, name, x, y):
        import platform
        if platform.system() == "Windows":
            from bridge import js_eval
            import json
            # サイドバー上の右クリックなのでHWND退避は不要
            payload = json.dumps({"gid": gid, "name": name, "x": x, "y": y})
            js_eval(f"window.dispatchEvent(new CustomEvent('show-group-context-menu',{{detail:{payload}}}))")
        else:
            from config import SIDEBAR_W
            self._bridge.group_menu_signal.emit(gid, name, int(x) + SIDEBAR_W, int(y))

    def show_settings_dialog(self):
        import platform
        if platform.system() == "Windows":
            from bridge import js_eval
            js_eval("window.dispatchEvent(new CustomEvent('show-settings-dialog'))")
        else:
            self._bridge.settings_signal.emit()

    # ────────────────────────────────────
    # ウィンドウ
    # ────────────────────────────────────
    def close_window(self):
        if webview.windows:
            webview.windows[0].destroy()

    def minimize_window(self):
        if webview.windows:
            webview.windows[0].minimize()

    def toggle_maximize(self):
        if webview.windows:
            webview.windows[0].toggle_fullscreen()

    def update_title(self, title):
        w = webview.windows[0] if webview.windows else None
        if w:
            w.title = title

    def set_aide_width(self, width):
        import platform
        self._aide_width_val = int(width)
        if platform.system() == "Windows":
            self._bridge.win_update_geometry(self._aide_width_val)
            return
        w = webview.windows[0] if webview.windows else None
        if not w or not self._bridge.active_id:
            return
        x, y, ww, h = self._get_rect(w, self._aide_width_val)
        self._bridge.show_view_signal.emit(self._bridge.active_id, x, y, ww, h)

    def get_page_text(self, service_id):
        return self._bridge.page_text_cache.get(service_id, "")

    def drag_window(self):
        pass  # 後方互換

    def _get_hwnd_cached(self):
        """HWNDをキャッシュして返す。タイトル変更後も有効。"""
        import platform
        if platform.system() != "Windows":
            return None
        # キャッシュ済みなら返す
        if getattr(self, "_hwnd_cache", None):
            return self._hwnd_cache
        try:
            import win32gui
            import win32process
            import os
            cur_pid = os.getpid()
            found = []
            def _cb(h, _):
                if not win32gui.IsWindowVisible(h):
                    return
                try:
                    _, pid = win32process.GetWindowThreadProcessId(h)
                    if pid == cur_pid:
                        found.append(h)
                except Exception:
                    pass
            win32gui.EnumWindows(_cb, None)
            # 同一プロセスの最大ウィンドウを選ぶ
            if found:
                self._hwnd_cache = max(found, key=lambda h: win32gui.GetWindowRect(h)[2] - win32gui.GetWindowRect(h)[0])
                return self._hwnd_cache
        except Exception:
            pass
        return None

    def drag_start(self):
        """ドラッグ開始：OS別にウィンドウ移動を実装"""
        import platform
        import threading
        if getattr(self, "_dragging", False):
            return
        self._dragging = True
        if platform.system() == "Windows":
            try:
                import win32api, win32con, win32gui
                # bridgeのメインHWNDキャッシュを使用
                hwnd = self._bridge._get_main_hwnd()
                if not hwnd:
                    self._dragging = False
                    return
                mx0, my0 = win32api.GetCursorPos()
                rx, ry, _, _ = win32gui.GetWindowRect(hwnd)
                def _drag_loop():
                    import time
                    while getattr(self, "_dragging", False):
                        # マウスボタンが離されたら自動停止
                        if not (win32api.GetKeyState(win32con.VK_LBUTTON) & 0x8000):
                            self._dragging = False
                            break
                        mx, my = win32api.GetCursorPos()
                        dx, dy = mx - mx0, my - my0
                        if dx != 0 or dy != 0:
                            win32gui.SetWindowPos(
                                hwnd, 0, rx + dx, ry + dy, 0, 0,
                                win32con.SWP_NOSIZE | win32con.SWP_NOZORDER
                            )
                        time.sleep(0.016)
                threading.Thread(target=_drag_loop, daemon=True).start()
            except ImportError:
                self._dragging = False
        else:
            # Linux: xdotool + wmctrl
            import subprocess
            from bridge import get_win_id
            win_id = get_win_id()
            if not win_id:
                result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
                for line in result.stdout.splitlines():
                    if "Ink Boss" in line:
                        win_id = line.split()[0]
                        break
            if not win_id:
                self._dragging = False
                return
            def _get_mouse_pos():
                r = subprocess.run(["xdotool", "getmouselocation", "--shell"], capture_output=True, text=True)
                x, y = 0, 0
                for line in r.stdout.splitlines():
                    if line.startswith("X="): x = int(line.split("=")[1])
                    elif line.startswith("Y="): y = int(line.split("=")[1])
                return x, y
            def _get_win_pos():
                r = subprocess.run(["xdotool", "getwindowgeometry", "--shell", win_id], capture_output=True, text=True)
                x, y = 0, 0
                for line in r.stdout.splitlines():
                    if line.startswith("X="): x = int(line.split("=")[1])
                    elif line.startswith("Y="): y = int(line.split("=")[1])
                return x, y
            mx0, my0 = _get_mouse_pos()
            wx0, wy0 = _get_win_pos()
            def _drag_loop():
                import time
                while getattr(self, "_dragging", False):
                    mx, my = _get_mouse_pos()
                    dx, dy = mx - mx0, my - my0
                    if dx != 0 or dy != 0:
                        subprocess.run(["wmctrl", "-ir", win_id, "-e", f"0,{wx0+dx},{wy0+dy},-1,-1"], check=False)
                    time.sleep(0.016)
            import threading
            threading.Thread(target=_drag_loop, daemon=True).start()

    def drag_end(self):
        self._dragging = False

    def drag_window_by(self, dx, dy):
        """後方互換：単発移動フォールバック"""
        import subprocess
        w = webview.windows[0] if webview.windows else None
        if not w:
            return
        result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
        win_id = None
        for line in result.stdout.splitlines():
            if "Ink Boss" in line:
                win_id = line.split()[0]
                break
        if win_id:
            pos_result = subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", win_id],
                capture_output=True, text=True,
            )
            x, y = 0, 0
            for line in pos_result.stdout.splitlines():
                if line.startswith("X="):
                    x = int(line.split("=")[1])
                elif line.startswith("Y="):
                    y = int(line.split("=")[1])
            subprocess.run(
                ["wmctrl", "-ir", win_id, "-e", f"0,{x+int(dx)},{y+int(dy)},-1,-1"],
                check=False,
            )
