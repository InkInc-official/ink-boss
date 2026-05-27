"""
api.py - InkBossAPI
Ink Boss / Ink Inc.

pywebviewのjs_apiとして登録するクラス。
JSからPythonの機能を呼び出す橋渡しをする。
"""

import json
import uuid
import webview
from PySide6.QtCore import QTimer

from config import save_config
from bridge import js_eval


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
        svc = {
            "id": f"service_{uuid.uuid4().hex[:8]}",
            "name": name, "url": url, "muted": False, "groupId": group_id,
        }
        self._config["services"].append(svc)
        save_config(self._config)
        self._bridge.create_view_signal.emit(svc["id"], url)
        return svc

    def update_service(self, sid, updates):
        for s in self._config["services"]:
            if s["id"] == sid:
                s.update(updates)
                break
        save_config(self._config)

    def remove_service(self, sid):
        self._config["services"] = [s for s in self._config["services"] if s["id"] != sid]
        save_config(self._config)
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
        self._bridge.create_view_signal.emit(new_svc["id"], new_svc["url"])
        return new_svc

    def show_service(self, sid):
        w = webview.windows[0] if webview.windows else None
        if not w:
            return
        aide_w = self._aide_width_val
        if sid in self._bridge.hibernated:
            self._bridge.wake_view_signal.emit(sid, self._bridge.urls.get(sid, "about:blank"))
            x, y, ww, h = self._get_rect(w, aide_w)
            QTimer.singleShot(300, lambda: self._bridge.show_view_signal.emit(sid, x, y, ww, h))
        else:
            x, y, ww, h = self._get_rect(w, aide_w)
            self._bridge.show_view_signal.emit(sid, x, y, ww, h)

    def hide_service(self):
        self._bridge.hide_all_signal.emit()

    def hibernate_service(self, sid):
        self._bridge.hibernate_view_signal.emit(sid)

    def wake_service(self, sid):
        self._bridge.wake_view_signal.emit(sid, self._bridge.urls.get(sid, "about:blank"))

    def get_hibernated_ids(self):
        return list(self._bridge.hibernated)

    def reload_service(self, sid):
        self._bridge.reload_view_signal.emit(sid)

    def sync_geometry(self, sid):
        w = webview.windows[0] if webview.windows else None
        if not w or not sid:
            return
        x, y, ww, h = self._get_rect(w, self._aide_width_val)
        self._bridge.update_geometry(sid, x, y, ww, h)

    # ────────────────────────────────────
    # グループ
    # ────────────────────────────────────
    def add_group(self, name):
        g = {"id": f"group_{uuid.uuid4().hex[:8]}", "name": name, "collapsed": False}
        self._config["groups"].append(g)
        save_config(self._config)
        return g

    def update_group(self, gid, name):
        for g in self._config["groups"]:
            if g["id"] == gid:
                g["name"] = name
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

    # ────────────────────────────────────
    # ダイアログ
    # ────────────────────────────────────
    def show_context_menu(self, sid, name, x, y, is_hib, groups_json):
        self._bridge.context_menu_signal.emit(sid, name, int(x), int(y), bool(is_hib), groups_json)

    def show_add_service_dialog(self, group_id=None):
        self._bridge.add_dialog_signal.emit(group_id or "")

    def show_add_group_dialog(self):
        self._bridge.add_group_dialog_signal.emit()

    def show_group_context_menu(self, gid, name, x, y):
        self._bridge.group_menu_signal.emit(gid, name, int(x), int(y))

    def show_settings_dialog(self):
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
        self._aide_width_val = int(width)
        w = webview.windows[0] if webview.windows else None
        if not w or not self._bridge.active_id:
            return
        x, y, ww, h = self._get_rect(w, self._aide_width_val)
        self._bridge.show_view_signal.emit(self._bridge.active_id, x, y, ww, h)

    def get_page_text(self, service_id):
        return self._bridge.page_text_cache.get(service_id, "")

    def drag_window(self):
        pass  # 後方互換

    def drag_start(self):
        """ドラッグ開始：キャッシュ済みウィンドウIDでマウス追跡スレッドを起動"""
        import subprocess
        import threading
        from bridge import get_win_id

        if getattr(self, "_dragging", False):
            return

        win_id = get_win_id()
        if not win_id:
            result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if "Ink Boss" in line:
                    win_id = line.split()[0]
                    break
        if not win_id:
            return

        def _get_mouse_pos():
            r = subprocess.run(
                ["xdotool", "getmouselocation", "--shell"], capture_output=True, text=True
            )
            x, y = 0, 0
            for line in r.stdout.splitlines():
                if line.startswith("X="):
                    x = int(line.split("=")[1])
                elif line.startswith("Y="):
                    y = int(line.split("=")[1])
            return x, y

        def _get_win_pos():
            r = subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", win_id],
                capture_output=True, text=True,
            )
            x, y = 0, 0
            for line in r.stdout.splitlines():
                if line.startswith("X="):
                    x = int(line.split("=")[1])
                elif line.startswith("Y="):
                    y = int(line.split("=")[1])
            return x, y

        mx0, my0 = _get_mouse_pos()
        wx0, wy0 = _get_win_pos()
        self._dragging = True

        def _drag_loop():
            import time
            while getattr(self, "_dragging", False):
                mx, my = _get_mouse_pos()
                dx, dy = mx - mx0, my - my0
                if dx != 0 or dy != 0:
                    subprocess.run(
                        ["wmctrl", "-ir", win_id, "-e", f"0,{wx0+dx},{wy0+dy},-1,-1"],
                        check=False,
                    )
                time.sleep(0.016)

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
