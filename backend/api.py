import json
import uuid
import threading
import webview
from .config import save_config
from .bridge import js_eval

SIDEBAR_W = 208
URLBAR_H  = 40

def get_webview_rect(window):
    return SIDEBAR_W, URLBAR_H, window.width - SIDEBAR_W, window.height - URLBAR_H


class InkBossAPI:
    def __init__(self, bridge, config: dict):
        self.bridge = bridge
        self.config = config

    def get_config(self):
        return self.config

    def add_service(self, name, url, group_id=None):
        service = {
            "id": f"service_{uuid.uuid4().hex[:8]}",
            "name": name, "url": url,
            "muted": False, "groupId": group_id,
        }
        self.config["services"].append(service)
        save_config(self.config)
        self.bridge.create_view_signal.emit(service["id"], url)
        return service

    def update_service(self, service_id, updates):
        for s in self.config["services"]:
            if s["id"] == service_id:
                s.update(updates)
                break
        save_config(self.config)

    def remove_service(self, service_id):
        self.config["services"] = [
            s for s in self.config["services"] if s["id"] != service_id]
        save_config(self.config)
        self.bridge.remove_view_signal.emit(service_id)

    def move_service(self, service_id, group_id):
        for s in self.config["services"]:
            if s["id"] == service_id:
                s["groupId"] = group_id
                break
        save_config(self.config)

    def copy_service(self, service_id, group_id):
        original = next(
            (s for s in self.config["services"] if s["id"] == service_id), None)
        if not original:
            return {}
        new_service = {
            "id": f"service_{uuid.uuid4().hex[:8]}",
            "name": original["name"], "url": original["url"],
            "muted": False, "groupId": group_id,
        }
        self.config["services"].append(new_service)
        save_config(self.config)
        self.bridge.create_view_signal.emit(new_service["id"], new_service["url"])
        return new_service

    def add_group(self, name):
        group = {
            "id": f"group_{uuid.uuid4().hex[:8]}",
            "name": name, "collapsed": False,
        }
        self.config["groups"].append(group)
        save_config(self.config)
        return group

    def update_group(self, group_id, name):
        for g in self.config["groups"]:
            if g["id"] == group_id:
                g["name"] = name
                break
        save_config(self.config)

    def remove_group(self, group_id, delete_services):
        self.config["groups"] = [
            g for g in self.config["groups"] if g["id"] != group_id]
        if delete_services:
            to_remove = [s["id"] for s in self.config["services"]
                         if s.get("groupId") == group_id]
            self.config["services"] = [
                s for s in self.config["services"] if s.get("groupId") != group_id]
            for sid in to_remove:
                self.bridge.remove_view_signal.emit(sid)
        else:
            for s in self.config["services"]:
                if s.get("groupId") == group_id:
                    s["groupId"] = None
        save_config(self.config)

    def update_llm_config(self, updates):
        self.config["llm"].update(updates)
        save_config(self.config)

    def update_hibernate_minutes(self, minutes):
        self.config["hibernate_minutes"] = int(minutes)
        save_config(self.config)

    def export_config(self):
        return json.dumps(self.config, ensure_ascii=False, indent=2)

    def import_config(self, json_str):
        new_config = json.loads(json_str)
        self.config.clear()
        self.config.update(new_config)
        save_config(self.config)

    def show_service(self, service_id):
        """別スレッドで即return、処理はメインスレッドへ"""
        def _run():
            window = webview.windows[0] if webview.windows else None
            if not window:
                return
            if service_id in self.bridge.hibernated:
                url = self.bridge.urls.get(service_id, "about:blank")
                self.bridge.wake_view_signal.emit(service_id, url)
            x, y, w, h = get_webview_rect(window)
            self.bridge.show_view_signal.emit(service_id, x, y, w, h)
        threading.Thread(target=_run, daemon=True).start()

    def hide_service(self):
        self.bridge.hide_all_signal.emit()

    def hibernate_service(self, service_id):
        self.bridge.hibernate_view_signal.emit(service_id)

    def wake_service(self, service_id):
        def _run():
            url = self.bridge.urls.get(service_id, "about:blank")
            self.bridge.wake_view_signal.emit(service_id, url)
            window = webview.windows[0] if webview.windows else None
            if window:
                x, y, w, h = get_webview_rect(window)
                self.bridge.show_view_signal.emit(service_id, x, y, w, h)
        threading.Thread(target=_run, daemon=True).start()

    def get_hibernated_ids(self):
        return list(self.bridge.hibernated)

    def reload_service(self, service_id):
        self.bridge.reload_view_signal.emit(service_id)

    def sync_geometry(self, service_id):
        window = webview.windows[0] if webview.windows else None
        if not window or not service_id:
            return
        x, y, w, h = get_webview_rect(window)
        self.bridge.show_view_signal.emit(service_id, x, y, w, h)

    def show_context_menu(self, service_id, service_name, x, y, is_hibernated, groups_json):
        """別スレッドで即return"""
        def _run():
            self.bridge.context_menu_signal.emit(
                service_id, service_name, int(x), int(y),
                bool(is_hibernated), groups_json)
        threading.Thread(target=_run, daemon=True).start()

    def show_add_service_dialog(self, group_id=None):
        """別スレッドで即return"""
        def _run():
            self.bridge.show_add_dialog_signal.emit(group_id or "")
        threading.Thread(target=_run, daemon=True).start()

    def close_window(self):
        if webview.windows:
            webview.windows[0].destroy()

    def minimize_window(self):
        if webview.windows:
            webview.windows[0].minimize()

    def toggle_maximize(self):
        if webview.windows:
            webview.windows[0].toggle_fullscreen()

    def drag_window(self):
        pass
