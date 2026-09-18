"""
dialogs/context_menu.py - サービス・グループのコンテキストメニュー
Ink Boss / Ink Inc.

- スクリーン座標 + 画面端クランプ
- アイコン変更
- 削除時は remove_view（hibernate ではない）
"""

import json
import uuid
from pathlib import Path

from PySide6.QtWidgets import (
    QMenu, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QApplication,
)
from PySide6.QtCore import Qt, QPoint
from config import DIALOG_STYLE, MENU_STYLE, save_config, CONFIG_DIR


def _clamp_menu_point(x: int, y: int, menu: QMenu) -> QPoint:
    """メニューが画面外に出ないようクランプ。"""
    screen = QApplication.primaryScreen()
    if screen is None:
        return QPoint(int(x), int(y))
    geo = screen.availableGeometry()
    menu.ensurePolished()
    # サイズ推定
    hint = menu.sizeHint()
    mw = max(hint.width(), 180)
    mh = max(hint.height(), 120)
    nx = int(x)
    ny = int(y)
    if nx + mw > geo.right():
        nx = geo.right() - mw - 4
    if ny + mh > geo.bottom():
        ny = geo.bottom() - mh - 4
    if nx < geo.left():
        nx = geo.left() + 4
    if ny < geo.top():
        ny = geo.top() + 4
    return QPoint(nx, ny)


def show_service_context_menu(
    sid: str, name: str, x: int, y: int,
    is_hib: bool, groups_json: str,
    config: dict, js_eval_fn,
    wake_view_fn, hibernate_view_fn,
    create_view_fn,
    remove_view_fn=None,
    navigate_view_fn=None,
    active_menu_holder: list | None = None,
) -> None:
    if active_menu_holder and active_menu_holder[0]:
        try:
            active_menu_holder[0].close()
        except Exception:
            pass

    groups = json.loads(groups_json) if groups_json else []
    menu = QMenu()
    menu.setStyleSheet(MENU_STYLE)
    if active_menu_holder is not None:
        active_menu_holder[0] = menu

    rename_a = menu.addAction("名前を変更")
    icon_a = menu.addAction("アイコンを変更…")
    url_a = menu.addAction("URLを変更…")
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

    # エンジン表示（非活性・情報のみ）と切替（別項目・要確認）
    svc = next((s for s in config.get("services", []) if s["id"] == sid), None)
    cur_eng = ((svc or {}).get("engine") or "qt").lower()
    eng_label = "Electron" if cur_eng == "electron" else "Qt"
    status_a = menu.addAction(f"現在のエンジン: {eng_label}")
    status_a.setEnabled(False)
    switch_a = menu.addAction("エンジンを切り替える…")
    menu.addSeparator()

    toggle_a = menu.addAction("復帰" if is_hib else "休止")
    menu.addSeparator()
    delete_a = menu.addAction("削除")

    pt = _clamp_menu_point(x, y, menu)
    action = menu.exec(pt)
    if active_menu_holder is not None:
        active_menu_holder[0] = None

    if not action:
        return

    if action == rename_a:
        _do_rename(sid, name, config, js_eval_fn)
    elif action == icon_a:
        _do_change_icon(sid, config, js_eval_fn)
    elif action == url_a:
        _do_change_url(sid, (svc or {}).get("url", ""), config, js_eval_fn, navigate_view_fn)
    elif action == switch_a:
        _do_toggle_engine(sid, name, config, js_eval_fn)
    elif action == delete_a:
        # 重要: hibernate ではなく remove
        rm = remove_view_fn or hibernate_view_fn
        _do_delete(sid, name, config, js_eval_fn, rm)
    elif action == toggle_a:
        if is_hib:
            wake_view_fn(sid)
            js_eval_fn(
                f"window.dispatchEvent(new CustomEvent('service-woke',{{detail:'{sid}'}}));"
            )
        else:
            hibernate_view_fn(sid)
            js_eval_fn(
                f"window.dispatchEvent(new CustomEvent('service-hibernated',{{detail:'{sid}'}}));"
            )
    else:
        aid = id(action)
        if aid in move_map:
            gid = move_map[aid]
            for s in config["services"]:
                if s["id"] == sid:
                    s["groupId"] = gid
                    break
            save_config(config)
            js_eval_fn(
                f"window.dispatchEvent(new CustomEvent('service-moved',"
                f"{{detail:{{id:'{sid}',groupId:'{gid}'}}}}));"
            )
        elif aid in copy_map:
            gid = copy_map[aid]
            orig = next((s for s in config["services"] if s["id"] == sid), None)
            if orig:
                eng = (orig.get("engine") or "qt").lower()
                new_svc = {
                    "id": f"service_{uuid.uuid4().hex[:8]}",
                    "name": orig["name"],
                    "url": orig["url"],
                    "muted": False,
                    "groupId": gid,
                    "engine": eng if eng in ("qt", "electron") else "qt",
                    "icon": orig.get("icon"),
                }
                config["services"].append(new_svc)
                save_config(config)
                if eng != "electron":
                    create_view_fn(new_svc["id"], new_svc["url"])
                js_eval_fn(
                    f"window.dispatchEvent(new CustomEvent('service-copied',"
                    f"{{detail:{json.dumps(new_svc)}}}));"
                )


def _do_rename(sid: str, current_name: str, config: dict, js_eval_fn) -> None:
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
            for s in config["services"]:
                if s["id"] == sid:
                    s["name"] = new_name
                    break
            save_config(config)
            js_eval_fn(
                f"window.dispatchEvent(new CustomEvent('service-renamed',"
                f"{{detail:{{id:'{sid}',name:{json.dumps(new_name)}}}}}))"
            )
        dialog.accept()

    ok_btn.clicked.connect(on_ok)
    name_input.setFocus()
    name_input.selectAll()
    dialog.exec()


def _do_change_icon(sid: str, config: dict, js_eval_fn) -> None:
    """ローカル画像を選んで services[].icon に保存。"""
    path, _ = QFileDialog.getOpenFileName(
        None,
        "アイコン画像を選択",
        str(Path.home()),
        "Images (*.png *.jpg *.jpeg *.webp *.ico *.svg)",
    )
    if not path:
        return
    icons_dir = CONFIG_DIR / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    src = Path(path)
    dest = icons_dir / f"{sid}{src.suffix.lower() or '.png'}"
    try:
        dest.write_bytes(src.read_bytes())
    except Exception as e:
        print(f"[icon] copy failed: {e}", flush=True)
        return
    # file:// URL でフロント img に渡す
    icon_url = dest.resolve().as_uri()
    for s in config.get("services", []):
        if s["id"] == sid:
            s["icon"] = icon_url
            break
    save_config(config)
    js_eval_fn(
        f"window.dispatchEvent(new CustomEvent('service-icon-changed',"
        f"{{detail:{{id:{json.dumps(sid)},icon:{json.dumps(icon_url)}}}}}))"
    )


def _do_change_url(sid: str, current_url: str, config: dict, js_eval_fn, navigate_fn) -> None:
    """URLを変更。ビュー（QWebEngineProfile / Electronのpartition）自体は
    sid単位で管理されているため、URLを変えるだけでは再作成されず、
    既存のセッション（Cookie/LocalStorage）は維持されたまま新URLに
    遷移する。"""
    dialog = QDialog()
    dialog.setWindowTitle("URLを変更")
    dialog.setMinimumWidth(420)
    dialog.setStyleSheet(DIALOG_STYLE)
    dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
    layout = QVBoxLayout(dialog)
    layout.setSpacing(12)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.addWidget(QLabel("新しいURL"))
    url_input = QLineEdit(current_url)
    layout.addWidget(url_input)
    btn_layout = QHBoxLayout()
    cancel_btn = QPushButton("キャンセル")
    ok_btn = QPushButton("変更")
    ok_btn.setObjectName("addBtn")
    btn_layout.addWidget(cancel_btn)
    btn_layout.addWidget(ok_btn)
    layout.addLayout(btn_layout)
    cancel_btn.clicked.connect(dialog.reject)

    def on_ok():
        new_url = url_input.text().strip()
        if not new_url:
            dialog.reject()
            return
        if not new_url.startswith("http"):
            new_url = f"https://{new_url}"
        for s in config["services"]:
            if s["id"] == sid:
                s["url"] = new_url
                break
        save_config(config)
        if navigate_fn:
            try:
                navigate_fn(sid, new_url)
            except Exception as e:
                print(f"[url] navigate failed: {e}", flush=True)
        js_eval_fn(
            f"window.dispatchEvent(new CustomEvent('service-url-changed',"
            f"{{detail:{{id:{json.dumps(sid)},url:{json.dumps(new_url)}}}}}))"
        )
        dialog.accept()

    ok_btn.clicked.connect(on_ok)
    url_input.setFocus()
    url_input.selectAll()
    dialog.exec()


def _do_toggle_engine(sid: str, name: str, config: dict, js_eval_fn) -> None:
    """エンジン切替は確認ダイアログを挟んでから実行（誤操作でのログイン状態消失を防ぐ）。
    切替自体はフロント経由で update_service に任せる（view 再作成のため）。"""
    svc = next((s for s in config.get("services", []) if s["id"] == sid), None)
    if svc is None:
        return
    cur = (svc.get("engine") or "qt").lower()
    new_eng = "qt" if cur == "electron" else "electron"
    cur_label = "Electron" if cur == "electron" else "Qt"
    new_label = "Electron" if new_eng == "electron" else "Qt"

    dialog = QDialog()
    dialog.setWindowTitle("エンジン切替の確認")
    dialog.setMinimumWidth(360)
    dialog.setStyleSheet(DIALOG_STYLE)
    dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
    layout = QVBoxLayout(dialog)
    layout.setSpacing(12)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.addWidget(QLabel(f"「{name}」を {cur_label} エンジンから {new_label} エンジンに切り替えますか？"))
    warn = QLabel("切替後、このサービスの現在のログイン状態は失われます（エンジンごとにセッションが別管理のため）。")
    warn.setWordWrap(True)
    layout.addWidget(warn)
    btn_layout = QHBoxLayout()
    cancel_btn = QPushButton("キャンセル")
    switch_btn = QPushButton("切り替える")
    switch_btn.setObjectName("addBtn")
    btn_layout.addWidget(cancel_btn)
    btn_layout.addWidget(switch_btn)
    layout.addLayout(btn_layout)
    cancel_btn.clicked.connect(dialog.reject)

    def on_switch():
        js_eval_fn(
            f"window.dispatchEvent(new CustomEvent('service-engine-changed',"
            f"{{detail:{{id:{json.dumps(sid)},engine:{json.dumps(new_eng)}}}}}))"
        )
        dialog.accept()

    switch_btn.clicked.connect(on_switch)
    dialog.exec()


def _do_delete(sid: str, name: str, config: dict, js_eval_fn, remove_view_fn) -> None:
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
        config["services"] = [s for s in config["services"] if s["id"] != sid]
        save_config(config)
        try:
            if remove_view_fn:
                remove_view_fn(sid)
        except Exception as e:
            print(f"[delete] remove_view: {e}", flush=True)
        # フロントはローカル state のみ更新（API 二重呼び出し防止）
        js_eval_fn(
            f"window.dispatchEvent(new CustomEvent('service-removed',{{detail:'{sid}'}}));"
        )
        dialog.accept()

    del_btn.clicked.connect(on_delete)
    dialog.exec()


def show_group_context_menu(
    gid: str, name: str, x: int, y: int,
    config: dict, js_eval_fn,
    active_menu_holder: list,
) -> None:
    if active_menu_holder[0]:
        try:
            active_menu_holder[0].close()
        except Exception:
            pass
    menu = QMenu()
    menu.setStyleSheet(MENU_STYLE)
    active_menu_holder[0] = menu
    rename_a = menu.addAction("名前を変更")
    menu.addSeparator()
    delete_a = menu.addAction("削除")
    pt = _clamp_menu_point(x, y, menu)
    action = menu.exec(pt)
    active_menu_holder[0] = None
    if not action:
        return
    if action == rename_a:
        _rename_group(gid, name, config, js_eval_fn)
    elif action == delete_a:
        _delete_group(gid, name, config, js_eval_fn)


def _rename_group(gid: str, current_name: str, config: dict, js_eval_fn) -> None:
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
            for g in config["groups"]:
                if g["id"] == gid:
                    g["name"] = new_name
                    break
            save_config(config)
            js_eval_fn(
                f"window.dispatchEvent(new CustomEvent('group-renamed',"
                f"{{detail:{{id:'{gid}',name:{json.dumps(new_name)}}}}}))"
            )
        dialog.close()

    ok_btn.clicked.connect(on_ok)
    name_input.setFocus()
    name_input.selectAll()
    dialog.exec()


def _delete_group(gid: str, name: str, config: dict, js_eval_fn) -> None:
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
        config["groups"] = [g for g in config["groups"] if g["id"] != gid]
        for s in config["services"]:
            if s.get("groupId") == gid:
                s["groupId"] = None
        save_config(config)
        js_eval_fn(
            f"window.dispatchEvent(new CustomEvent('group-removed',{{detail:'{gid}'}}));"
        )
        dialog.close()

    del_btn.clicked.connect(on_delete)
    dialog.exec()
