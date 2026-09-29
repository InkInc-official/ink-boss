"""
api.py - InkBossAPI
Ink Boss / Ink Inc.

pywebview js_api + dual-engine routing (qt | electron).
"""

from __future__ import annotations

import json
import threading
import time
import uuid

import webview

from config import save_config
from bridge import js_eval
from sysenv import get_clean_subprocess_env


class InkBossAPI:
    def __init__(
        self,
        config: dict,
        bridge,
        get_rect_fn,
        aide_width_getter,
        electron=None,
        get_screen_rect_fn=None,
    ):
        self._config = config
        self._bridge = bridge
        self._get_rect = get_rect_fn
        self._get_screen_rect = get_screen_rect_fn
        self._electron = electron
        self._aide_width = aide_width_getter
        self._aide_width_val = 0
        self._dragging = False
        self._active_engine: str | None = None
        # 自動休止用: sid -> 最後にアクティブだった時刻(epoch秒)
        self._last_active: dict[str, float] = {}
        self._audible_logged: set[str] = set()
        # 「今ユーザーが見ているサービス」。bridge.active_id は Electron へ切替える際に
        # キュー経由で実行される _hide_all() が None に上書きしてしまう（実機で確認）ため、
        # 自動休止の除外判定には使えない。show_service で記録する専用の値を使う。
        self._active_sid: str | None = None
        self._active_set_at: float = 0.0

    # ── helpers ───────────────────────────────────────────
    def _find_service(self, sid: str) -> dict | None:
        return next((s for s in self._config.get("services", []) if s["id"] == sid), None)

    def _service_engine(self, sid: str) -> str:
        svc = self._find_service(sid)
        if not svc:
            return "qt"
        eng = (svc.get("engine") or "qt").lower()
        return "electron" if eng in ("electron", "e") else "qt"

    def _screen_rect(self, window, aide_w: int) -> tuple[int, int, int, int]:
        if self._get_screen_rect:
            return self._get_screen_rect(window, aide_w)
        x, y, w, h = self._get_rect(window, aide_w)
        wx = int(getattr(window, "x", 0) or 0)
        wy = int(getattr(window, "y", 0) or 0)
        return wx + x, wy + y, w, h

    def _hide_other_engine(self, keep: str) -> None:
        import time as _t
        print(f"[TIMING2] {_t.time():.3f} _hide_other_engine(keep={keep!r}) called", flush=True)
        if keep != "qt":
            try:
                print(f"[TIMING2] {_t.time():.3f} _hide_other_engine: emitting hide_all_signal (keep={keep!r} != 'qt')", flush=True)
                self._bridge.hide_all_signal.emit()
            except Exception as e:
                print(f"[api] hide qt failed: {e}", flush=True)
        if keep != "electron" and self._electron and self._electron.is_available():
            try:
                self._electron.hide_all()
            except Exception as e:
                print(f"[api] hide electron failed: {e}", flush=True)

    def _destroy_engine_view(self, sid: str, eng: str | None = None) -> None:
        eng = eng or self._service_engine(sid)
        try:
            if eng == "electron":
                if self._electron and self._electron.is_available():
                    self._electron.remove(sid)
            else:
                self._bridge.remove_view_signal.emit(sid)
        except Exception as e:
            print(f"[api] destroy view {sid}/{eng}: {e}", flush=True)

    # ── 自動休止（hibernate_minutes） ──────────────────────
    AUTO_HIBERNATE_TICK_S = 10

    def start_auto_hibernate(self) -> None:
        threading.Thread(target=self._auto_hibernate_loop, daemon=True).start()

    def _auto_hibernate_minutes(self) -> int:
        """0以下・未設定・bool(過去の不具合で保存されたFalse)は「無効」扱い。"""
        v = self._config.get("hibernate_minutes", 0)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            return 0
        return int(v)

    def _awake_state(self) -> tuple[set[str], set[str]]:
        """(起動済み（休止していない）sid, うち現在音声を出力中のsid)。Qt/Electron両方。"""
        known = {s["id"] for s in self._config.get("services", [])}
        awake = {
            sid for sid in list(self._bridge.views)
            if sid not in self._bridge.hibernated
        }
        audible = set(self._bridge.audible)
        if self._electron and self._electron.is_available():
            try:
                e_awake, e_audible = self._electron.get_awake_state()
                awake.update(e_awake)
                audible.update(e_audible)
            except Exception as e:
                print(f"[auto-hibernate] electron awake query failed: {e}", flush=True)
        return awake & known, audible & awake

    def _auto_hibernate_tick(self, now: float | None = None) -> None:
        minutes = self._auto_hibernate_minutes()
        if minutes <= 0:
            # 無効: 何もしない。古い記録が残ると再有効化直後に即休止されるため破棄だけ行う
            self._last_active.clear()
            return
        now = time.time() if now is None else now
        limit = minutes * 60
        awake, audible = self._awake_state()
        # 休止/削除された場合は解除（復帰後に永久に除外され続けるのを防ぐ）。
        # ただし表示直後は起動(wake)が完了しておらずawakeに未反映のことがあるため猶予を置く
        if self._active_sid and self._active_sid not in awake and now - self._active_set_at > 5:
            self._active_sid = None
        active = self._active_sid or self._bridge.active_id
        if active:
            self._last_active[active] = now
        # 音声/動画を再生中のサービスは非アクティブでも休止しない。
        # 記録時刻を更新し続けるので、再生停止時点から設定時間の計測が始まる
        for sid in audible:
            self._last_active[sid] = now
        if audible != self._audible_logged:
            print(f"[auto-hibernate] audible services (skipped): {sorted(audible)}", flush=True)
            self._audible_logged = set(audible)
        for sid in list(self._last_active):
            if sid not in awake:
                del self._last_active[sid]
        for sid in awake:
            if sid == active:
                continue  # 今見ているサービスは休止しない
            last = self._last_active.setdefault(sid, now)
            if now - last >= limit:
                svc = self._find_service(sid)
                print(
                    f"[auto-hibernate] {sid} ({(svc or {}).get('name')}) "
                    f"inactive {int(now - last)}s >= {limit}s → hibernate",
                    flush=True,
                )
                self._last_active.pop(sid, None)
                try:
                    self.hibernate_service(sid)
                    js_eval(
                        f"window.dispatchEvent(new CustomEvent('service-hibernated',"
                        f"{{detail:{json.dumps(sid)}}}))"
                    )
                except Exception as e:
                    print(f"[auto-hibernate] hibernate {sid} failed: {e}", flush=True)

    def _auto_hibernate_loop(self) -> None:
        print(f"[auto-hibernate] timer started (tick={self.AUTO_HIBERNATE_TICK_S}s)", flush=True)
        while True:
            time.sleep(self.AUTO_HIBERNATE_TICK_S)
            try:
                self._auto_hibernate_tick()
            except Exception as e:
                print(f"[auto-hibernate] tick error: {e}", flush=True)

    def sync_active_overlay(self) -> None:
        """B1: drag/resize 中に Electron をコンテンツ領域へ追従させる。

        【申し送り（未対応・様子見中）】ここで使う bridge.active_id は、Electron へ
        切り替える際にキュー経由で実行される bridge._hide_all() が None に上書きする
        ことがある（自動休止の実装中に実機で確認）。そのため Electron 表示中に
        ウィンドウを動かしても追従しない可能性がある。現時点で症状の報告は無いため
        未修正。「Electron表示中にウィンドウを動かすと追従がおかしい」等の症状が出たら、
        自動休止と同様に show_service で記録している self._active_sid を使うことを検討。"""
        sid = self._bridge.active_id
        if not sid or self._service_engine(sid) != "electron":
            return
        if not self._electron or not self._electron.is_available():
            return
        w = webview.windows[0] if webview.windows else None
        if not w:
            return
        try:
            sx, sy, sw, sh = self._screen_rect(w, self._aide_width_val)
            self._electron.bounds(sid, sx, sy, sw, sh)
        except Exception as e:
            print(f"[api] sync_active_overlay: {e}", flush=True)

    # ── config ────────────────────────────────────────────
    def get_config(self):
        return self._config

    def update_llm_config(self, updates):
        self._config.setdefault("llm", {}).update(updates)
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

    # ── services ──────────────────────────────────────────
    def add_service(self, name, url, group_id=None, engine="qt"):
        eng = (engine or "qt").lower()
        if eng not in ("qt", "electron"):
            eng = "qt"
        svc = {
            "id": f"service_{uuid.uuid4().hex[:8]}",
            "name": name,
            "url": url,
            "muted": False,
            "groupId": group_id,
            "engine": eng,
        }
        self._config.setdefault("services", []).append(svc)
        save_config(self._config)
        try:
            if eng == "electron":
                if self._electron and self._electron.is_available():
                    self._electron.create(svc["id"], url, load_now=False)
            else:
                self._bridge.create_view_signal.emit(svc["id"], url)
        except Exception as e:
            print(f"[api] add_service create failed: {e}", flush=True)
        return svc

    def update_service(self, sid, updates):
        prev_eng = self._service_engine(sid)
        for s in self._config.get("services", []):
            if s["id"] == sid:
                s.update(updates or {})
                if "engine" in (updates or {}):
                    eng = (updates.get("engine") or "qt").lower()
                    s["engine"] = eng if eng in ("qt", "electron") else "qt"
                break
        save_config(self._config)

        new_eng = self._service_engine(sid)
        if new_eng != prev_eng:
            self._destroy_engine_view(sid, prev_eng)
            svc = self._find_service(sid)
            url = (svc or {}).get("url") or "about:blank"
            try:
                if new_eng == "electron":
                    if self._electron and self._electron.is_available():
                        self._electron.create(sid, url, load_now=False)
                else:
                    self._bridge.create_view_signal.emit(sid, url)
            except Exception as e:
                print(f"[api] engine switch failed: {e}", flush=True)

    def remove_service(self, sid):
        eng = self._service_engine(sid)
        self._config["services"] = [s for s in self._config.get("services", []) if s["id"] != sid]
        save_config(self._config)
        if self._bridge.active_id == sid:
            self._bridge.active_id = None
            self._active_engine = None
        self._destroy_engine_view(sid, eng)

    def move_service(self, sid, gid):
        for s in self._config.get("services", []):
            if s["id"] == sid:
                s["groupId"] = gid or None
                break
        save_config(self._config)

    def copy_service(self, sid, gid):
        orig = self._find_service(sid)
        if not orig:
            return {}
        eng = (orig.get("engine") or "qt").lower()
        if eng not in ("qt", "electron"):
            eng = "qt"
        new_svc = {
            "id": f"service_{uuid.uuid4().hex[:8]}",
            "name": orig["name"],
            "url": orig["url"],
            "muted": False,
            "groupId": gid,
            "engine": eng,
            "icon": orig.get("icon"),
        }
        self._config.setdefault("services", []).append(new_svc)
        save_config(self._config)
        try:
            if eng == "electron":
                if self._electron and self._electron.is_available():
                    self._electron.create(new_svc["id"], new_svc["url"], load_now=False)
            else:
                self._bridge.create_view_signal.emit(new_svc["id"], new_svc["url"])
        except Exception as e:
            print(f"[api] copy_service create failed: {e}", flush=True)
        return new_svc

    def show_service(self, sid):
        import time as _t
        print(f"[TIMING2] {_t.time():.3f} show_service({sid}) CALLED, hibernated={sid in self._bridge.hibernated}", flush=True)
        w = webview.windows[0] if webview.windows else None
        if not w:
            return
        _now = time.time()
        _prev = self._active_sid or self._bridge.active_id
        if _prev and _prev != sid:
            self._last_active[_prev] = _now
        self._last_active[sid] = _now
        self._active_sid = sid
        self._active_set_at = _now
        aide_w = self._aide_width_val
        eng = self._service_engine(sid)
        svc = self._find_service(sid)
        url = (svc or {}).get("url") or self._bridge.urls.get(sid, "about:blank")

        if eng == "electron":
            self._hide_other_engine("electron")
            if not self._electron or not self._electron.is_available():
                print(f"[api] show_service({sid}): electron unavailable", flush=True)
                js_eval(
                    "window.dispatchEvent(new CustomEvent('engine-error',"
                    f"{{detail:{{sid:{json.dumps(sid)},engine:'electron',"
                    "message:'Electronエンジン未起動。electron-engine で npm install してください。'}}}}))"
                )
                return
            sx, sy, sw, sh = self._screen_rect(w, aide_w)

            def _do():
                try:
                    self._electron.show(sid, url, sx, sy, sw, sh)
                    js_eval(
                        f"window.dispatchEvent(new CustomEvent('service-woke',"
                        f"{{detail:{json.dumps(sid)}}}))"
                    )
                except Exception as e:
                    print(f"[api] electron show failed: {e}", flush=True)

            threading.Thread(target=_do, daemon=True).start()
            self._active_engine = "electron"
            self._bridge.active_id = sid
            return

        # Qt
        self._hide_other_engine("qt")
        self._active_engine = "qt"
        # ensure view exists (lazy safety)
        if sid not in self._bridge.views:
            self._bridge.create_view_signal.emit(sid, url)
        if sid in self._bridge.hibernated:
            x, y, ww, h = self._get_rect(w, aide_w)
            # 300ms後の表示ディレイは bridge.py 側（Qtメインスレッド）で
            # スケジュールする。js_api呼び出しスレッド（Qtイベントループを
            # 持たない）で直接QTimer.singleShotを使うと発火しないため。
            self._bridge.wake_and_show_signal.emit(sid, self._bridge.urls.get(sid, url), x, y, ww, h)
        else:
            x, y, ww, h = self._get_rect(w, aide_w)
            self._bridge.show_view_signal.emit(sid, x, y, ww, h)

    def hide_service(self):
        try:
            self._bridge.hide_all_signal.emit()
        except Exception:
            pass
        if self._electron and self._electron.is_available():
            try:
                self._electron.hide_all()
            except Exception:
                pass
        self._active_engine = None

    def hibernate_service(self, sid):
        if self._service_engine(sid) == "electron":
            if self._electron and self._electron.is_available():
                self._electron.hibernate(sid)
            if self._bridge.active_id == sid:
                self._bridge.active_id = None
        else:
            self._bridge.hibernate_view_signal.emit(sid)

    def wake_service(self, sid):
        svc = self._find_service(sid)
        url = (svc or {}).get("url") or self._bridge.urls.get(sid, "about:blank")
        if self._service_engine(sid) == "electron":
            if self._electron and self._electron.is_available():
                self._electron.wake(sid, url)
                js_eval(
                    f"window.dispatchEvent(new CustomEvent('service-woke',"
                    f"{{detail:{json.dumps(sid)}}}))"
                )
        else:
            self._bridge.wake_view_signal.emit(sid, url)

    def get_hibernated_ids(self):
        """「休止していないサービス（＝実際にロード済みで起動が重い
        原因になりうるもの）」を差し引く方式で計算する。

        以前は「明示的に休止済みと記録されているsid」を集める方式
        だったが、_init_views は起動時にQtサービスのみ作成し
        Electronサービスは一切作成しない設計（重い処理を避けるための
        意図的なlazy化）のため、起動直後で一度もクリックされていない
        Electronサービスはそもそも main.js の hibernated セットに
        存在せず、「休止していない」と誤判定されていた。実機で確認した
        ところ、グループに属しているかどうかとは無関係に、Electron
        エンジンのサービス全般でこの誤判定が起きていた（ユーザーの
        環境ではグループ内サービスにElectronエンジンが多かったため
        「グループのサービスだけ休止しない」ように見えていたと推測）。
        設定にある全サービスから「実際に起動中(awake)」なものを
        差し引くことで、一度も触られていないサービスは常に休止扱いに
        なるよう修正した。"""
        all_ids = {s["id"] for s in self._config.get("services", [])}
        awake_ids = {sid for sid in self._bridge.views if sid not in self._bridge.hibernated}
        if self._electron and self._electron.is_available():
            try:
                awake_ids.update(self._electron.get_awake_ids())
            except Exception:
                pass
        return list(all_ids - awake_ids)

    def reload_service(self, sid):
        if self._service_engine(sid) == "electron":
            if self._electron and self._electron.is_available():
                self._electron.reload(sid)
        else:
            self._bridge.reload_view_signal.emit(sid)

    def sync_geometry(self, sid):
        w = webview.windows[0] if webview.windows else None
        if not w or not sid:
            return
        if self._service_engine(sid) == "electron":
            if self._electron and self._electron.is_available():
                sx, sy, sw, sh = self._screen_rect(w, self._aide_width_val)
                self._electron.bounds(sid, sx, sy, sw, sh)
            return
        x, y, ww, h = self._get_rect(w, self._aide_width_val)
        self._bridge.update_geometry(sid, x, y, ww, h)

    def reorder_services(self, service_ids):
        id_order = list(service_ids or [])
        self._config["services"].sort(
            key=lambda s: id_order.index(s["id"]) if s["id"] in id_order else 999
        )
        save_config(self._config)

    # ── groups ────────────────────────────────────────────
    def add_group(self, name):
        g = {"id": f"group_{uuid.uuid4().hex[:8]}", "name": name, "collapsed": False}
        self._config.setdefault("groups", []).append(g)
        save_config(self._config)
        return g

    def update_group(self, gid, name):
        for g in self._config.get("groups", []):
            if g["id"] == gid:
                g["name"] = name
                break
        save_config(self._config)

    def remove_group(self, gid, delete_services):
        self._config["groups"] = [g for g in self._config.get("groups", []) if g["id"] != gid]
        if delete_services:
            to_rm = [s for s in self._config.get("services", []) if s.get("groupId") == gid]
            self._config["services"] = [
                s for s in self._config.get("services", []) if s.get("groupId") != gid
            ]
            for s in to_rm:
                self._destroy_engine_view(s["id"], (s.get("engine") or "qt").lower())
        else:
            for s in self._config.get("services", []):
                if s.get("groupId") == gid:
                    s["groupId"] = None
        save_config(self._config)

    def reorder_groups(self, group_ids):
        id_order = list(group_ids or [])
        self._config["groups"].sort(
            key=lambda g: id_order.index(g["id"]) if g["id"] in id_order else 999
        )
        save_config(self._config)

    # ── dialogs ───────────────────────────────────────────
    def show_context_menu(self, sid, name, x, y, is_hib, groups_json):
        # x,y はスクリーン座標を期待（フロントで変換済み）
        self._bridge.context_menu_signal.emit(sid, name, int(x), int(y), bool(is_hib), groups_json)

    def show_add_service_dialog(self, group_id=None):
        self._bridge.add_dialog_signal.emit(group_id or "")

    def show_add_group_dialog(self):
        self._bridge.add_group_dialog_signal.emit()

    def show_group_context_menu(self, gid, name, x, y):
        self._bridge.group_menu_signal.emit(gid, name, int(x), int(y))

    def show_settings_dialog(self):
        self._bridge.settings_signal.emit()

    # ── window ────────────────────────────────────────────
    def close_window(self):
        """
        ×ボタン終了。JS API スレッドから呼ばれる。
        QTimer は別スレッドからだと発火しないことがあるため、
        ViewBridge.app_shutdown_signal（QueuedConnection）で Qt メインへ渡す。
        並行してハードウォッチドッグを必ず武装する。
        """
        import os
        import time

        print("[Close] close_window start (js_api thread)", flush=True)
        if getattr(self, "_closing", False):
            print("[Close] already closing — ignore", flush=True)
            return
        self._closing = True

        # ハード保険: どの経路がハングしても 4 秒でプロセスを終わらせる
        def _hard_watchdog():
            time.sleep(4.0)
            print("[Close] HARD watchdog — os._exit(0)", flush=True)
            os._exit(0)

        threading.Thread(target=_hard_watchdog, daemon=True, name="close-watchdog").start()
        print("[Close] hard watchdog armed (4000ms)", flush=True)

        # Qt メインスレッドへ（QueuedConnection）
        try:
            self._bridge.app_shutdown_signal.emit()
            print("[Close] app_shutdown_signal emitted", flush=True)
        except Exception as e:
            print(f"[Close] signal emit failed: {e} — inline fallback", flush=True)
            self._shutdown_for_exit()

    def _shutdown_for_exit(self) -> None:
        """正規終了シーケンス（Qt メインスレッド想定。必ずログを残す）。"""
        import os
        import time

        print("[Close] closeEvent start", flush=True)
        t0 = time.time()

        print("[Close][Step 1/5] Electron shutdown start", flush=True)
        # 1) Electron を先に落とす（セッション flush）— 最大 3 秒、必ず戻る
        print("[Close] electron shutdown request sent", flush=True)
        if self._electron is not None:
            try:
                # メインスレッドを長く塞がないよう、別スレッドで待って join(3s)
                err = [None]

                def _el():
                    try:
                        self._electron.shutdown(timeout=2.5)
                    except Exception as e:
                        err[0] = e

                th = threading.Thread(target=_el, daemon=True)
                th.start()
                th.join(timeout=3.0)
                if th.is_alive():
                    print("[Close] electron shutdown still running after 3s — continue", flush=True)
                elif err[0]:
                    print(f"[Close] electron shutdown error: {err[0]}", flush=True)
                else:
                    print("[Close] electron shutdown confirmed", flush=True)
            except Exception as e:
                print(f"[Close] electron shutdown outer error: {e}", flush=True)
        else:
            print("[Close] no electron engine", flush=True)
        print("[Close][Step 1/5] Electron shutdown end", flush=True)

        print("[Close][Step 2/5] Qt views cleanup start", flush=True)
        # 2) Qt WebEngine view を同期的に破棄（シグナル往復だと終了中に詰まる）
        print("[Close] qt views cleanup start", flush=True)
        try:
            self._bridge._hide_all()
        except Exception as e:
            print(f"[Close] hide_all: {e}", flush=True)
        try:
            for sid in list(getattr(self._bridge, "views", {}).keys()):
                try:
                    self._bridge._remove_view(sid)
                except Exception as e:
                    print(f"[Close] remove_view {sid}: {e}", flush=True)
        except Exception as e:
            print(f"[Close] qt views loop: {e}", flush=True)
        print("[Close] qt views cleanup done", flush=True)
        print("[Close][Step 2/5] Qt views cleanup end", flush=True)

        print("[Close][Step 3/5] Destroying webview window start", flush=True)
        # 3) pywebview ウィンドウ破棄
        print("[Close] destroying webview window", flush=True)
        try:
            if webview.windows:
                webview.windows[0].destroy()
                print("[Close] webview.destroy() called", flush=True)
            else:
                print("[Close] no webview windows", flush=True)
        except Exception as e:
            print(f"[Close] webview.destroy error: {e}", flush=True)
        print("[Close][Step 3/5] Destroying webview window end", flush=True)

        print("[Close][Step 4/5] Calling QApplication.quit() start", flush=True)
        # 4) QApplication.quit
        print("[Close] calling QApplication.quit()", flush=True)
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.quit()
                print("[Close] QApplication.quit() issued", flush=True)
            else:
                print("[Close] no QApplication instance", flush=True)
        except Exception as e:
            print(f"[Close] QApplication.quit error: {e}", flush=True)
        print("[Close][Step 4/5] Calling QApplication.quit() end", flush=True)

        elapsed = time.time() - t0
        print(f"[Close] closeEvent sequence finished in {elapsed:.2f}s", flush=True)

        print("[Close][Step 5/5] Soft watchdog arming", flush=True)
        # 5) ソフト保険（メインスレッドに残る場合）: 1.2s 後 os._exit
        def _soft_exit():
            time.sleep(1.2)
            print("[Close] soft watchdog — os._exit(0)", flush=True)
            os._exit(0)

        threading.Thread(target=_soft_exit, daemon=True, name="close-soft").start()
        print("[Close] soft watchdog armed (1200ms)", flush=True)
        print("[Close][Step 5/5] Soft watchdog armed end", flush=True)
    def minimize_window(self):
        # 最小化前にオーバーレイを隠す
        if self._electron and self._electron.is_available():
            try:
                self._electron.hide_all()
            except Exception:
                pass
        if webview.windows:
            webview.windows[0].minimize()

    def toggle_maximize(self):
        if webview.windows:
            webview.windows[0].toggle_fullscreen()

    def update_title(self, title):
        # frameless 時は OS タイトルは見えないが互換のため残す
        w = webview.windows[0] if webview.windows else None
        if w:
            try:
                w.title = title or "Ink Boss"
            except Exception:
                pass

    def set_aide_width(self, width):
        self._aide_width_val = int(width)
        sid = self._bridge.active_id
        w = webview.windows[0] if webview.windows else None
        if not w or not sid:
            return
        if self._service_engine(sid) == "electron":
            if self._electron and self._electron.is_available():
                sx, sy, sw, sh = self._screen_rect(w, self._aide_width_val)
                self._electron.bounds(sid, sx, sy, sw, sh)
            return
        x, y, ww, h = self._get_rect(w, self._aide_width_val)
        self._bridge.show_view_signal.emit(sid, x, y, ww, h)

    def get_page_text(self, service_id):
        # Qt側はloadFinished/urlChanged時にPython側から能動的に
        # runJavaScriptしてpage_text_cacheへ溜めている（bridge.py参照）が、
        # Electron側には同等の仕組みがなかったため、Electronホストの
        # サービス（Ecosia等）ではInk Aideがページ内容を取得できず、
        # 常に「具体的にどのページについて要約すべきか教えてください」
        # という空振りの応答になっていた（実機報告で発見）。
        # electron-engine/main.jsの/pageTextエンドポイント（その場で
        # document.body.innerTextを取得）を呼び出して同じ内容を渡す。
        if self._service_engine(service_id) == "electron":
            if self._electron and self._electron.is_available():
                return self._electron.get_page_text(service_id)
            return ""
        return self._bridge.page_text_cache.get(service_id, "")

    def drag_window(self):
        pass

    def drag_start(self):
        """A1: TopBar ドラッグ。B1: ドラッグ中も Electron を追従。"""
        import subprocess
        import time
        from bridge import get_win_id

        if self._dragging:
            return

        # wmctrl/xdotoolはInk Boss自身のバイナリではない外部コマンドのため、
        # PyInstaller由来のLD_LIBRARY_PATH等を取り除いた環境で呼ぶ
        # （sysenv.py参照）。ドラッグループは60fps相当で呼ばれるため、
        # ループの外で一度だけ作って使い回す。
        clean_env = get_clean_subprocess_env()

        win_id = get_win_id()
        if not win_id:
            result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, env=clean_env)
            for line in result.stdout.splitlines():
                if "Ink Boss" in line:
                    win_id = line.split()[0]
                    break
        if not win_id:
            return

        def _get_mouse_pos():
            r = subprocess.run(
                ["xdotool", "getmouselocation", "--shell"],
                capture_output=True, text=True, env=clean_env,
            )
            x = y = 0
            for line in r.stdout.splitlines():
                if line.startswith("X="):
                    x = int(line.split("=")[1])
                elif line.startswith("Y="):
                    y = int(line.split("=")[1])
            return x, y

        def _get_win_pos():
            r = subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", win_id],
                capture_output=True,
                text=True,
                env=clean_env,
            )
            x = y = 0
            for line in r.stdout.splitlines():
                if line.startswith("X="):
                    x = int(line.split("=")[1])
                elif line.startswith("Y="):
                    y = int(line.split("=")[1])
            return x, y

        mx0, my0 = _get_mouse_pos()
        wx0, wy0 = _get_win_pos()
        self._dragging = True
        # ドラッグ中は Electron を一旦 hide するとズレが目立たないが、
        # B1 UX は「ついてくる」なので毎フレーム bounds 同期する。

        def _drag_loop():
            last_sync = 0.0
            while self._dragging:
                mx, my = _get_mouse_pos()
                dx, dy = mx - mx0, my - my0
                if dx != 0 or dy != 0:
                    subprocess.run(
                        ["wmctrl", "-ir", win_id, "-e", f"0,{wx0 + dx},{wy0 + dy},-1,-1"],
                        check=False, env=clean_env,
                    )
                    # pywebview window.x/y も更新（screen_rect 用）
                    try:
                        w = webview.windows[0] if webview.windows else None
                        if w is not None:
                            # 内部座標が古いままだと bounds がずれるので
                            # xdotool の実座標を信頼して screen_rect 側で再計算
                            pass
                    except Exception:
                        pass
                    now = time.time()
                    if now - last_sync > 0.016:
                        last_sync = now
                        self._sync_overlay_from_win_pos(wx0 + dx, wy0 + dy)
                time.sleep(0.016)
            # ドラッグ終了後に最終同期
            try:
                wx, wy = _get_win_pos()
                self._sync_overlay_from_win_pos(wx, wy)
            except Exception:
                pass

        threading.Thread(target=_drag_loop, daemon=True).start()

    def _sync_overlay_from_win_pos(self, win_x: int, win_y: int) -> None:
        sid = self._bridge.active_id
        if not sid or self._service_engine(sid) != "electron":
            return
        if not self._electron or not self._electron.is_available():
            return
        w = webview.windows[0] if webview.windows else None
        if not w:
            return
        from config import SIDEBAR_W, URLBAR_H

        aide = self._aide_width_val
        ww = max(1, int(getattr(w, "width", 1280) or 1280) - SIDEBAR_W - aide)
        hh = max(1, int(getattr(w, "height", 850) or 850) - URLBAR_H)
        sx = int(win_x) + SIDEBAR_W
        sy = int(win_y) + URLBAR_H
        try:
            self._electron.bounds(sid, sx, sy, ww, hh)
        except Exception:
            pass

    def drag_end(self):
        self._dragging = False
        # 最終位置同期
        try:
            self.sync_active_overlay()
        except Exception:
            pass

    def drag_window_by(self, dx, dy):
        import subprocess
        from bridge import get_win_id

        win_id = get_win_id()
        if not win_id:
            return
        clean_env = get_clean_subprocess_env()
        pos = subprocess.run(
            ["xdotool", "getwindowgeometry", "--shell", win_id],
            capture_output=True,
            text=True,
            env=clean_env,
        )
        x = y = 0
        for line in pos.stdout.splitlines():
            if line.startswith("X="):
                x = int(line.split("=")[1])
            elif line.startswith("Y="):
                y = int(line.split("=")[1])
        subprocess.run(
            ["wmctrl", "-ir", win_id, "-e", f"0,{x + int(dx)},{y + int(dy)},-1,-1"],
            check=False, env=clean_env,
        )
        self._sync_overlay_from_win_pos(x + int(dx), y + int(dy))
