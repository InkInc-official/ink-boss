"""
dialogs/context_menu.py - サービス・グループのコンテキストメニュー
Ink Boss / Ink Inc.
"""

import json
import uuid
from PySide6.QtWidgets import (
    QMenu, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)
from PySide6.QtCore import Qt, QPoint
from config import DIALOG_STYLE, MENU_STYLE, save_config


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# サービス コンテキストメニュー
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def show_service_context_menu(
    sid: str, name: str, x: int, y: int,
    is_hib: bool, groups_json: str,
    config: dict, js_eval_fn,
    wake_view_fn, hibernate_view_fn,
    create_view_fn,
    active_menu_holder: list,   # [menu_or_None]
) -> None:
    """
    サービスの右クリックメニューを表示する。

    active_menu_holder: [None] の1要素リストを渡し、メニュー多重起動を防ぐ。
    """
    if active_menu_holder[0]:
        active_menu_holder[0].close()

    groups = json.loads(groups_json)
    menu = QMenu()
    menu.setStyleSheet(MENU_STYLE)
    active_menu_holder[0] = menu

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
    active_menu_holder[0] = None

    if not action:
        return

    if action == rename_a:
        _do_rename(sid, name, config, js_eval_fn)
    elif action == delete_a:
        _do_delete(sid, name, config, js_eval_fn, hibernate_view_fn)
    elif action == toggle_a:
        if is_hib:
            wake_view_fn(sid)
            js_eval_fn(f"window.dispatchEvent(new CustomEvent('service-woke',{{detail:'{sid}'}}));")
        else:
            hibernate_view_fn(sid)
            js_eval_fn(f"window.dispatchEvent(new CustomEvent('service-hibernated',{{detail:'{sid}'}}));")
    else:
        aid = id(action)
        if aid in move_map:
            gid = move_map[aid]
            for s in config["services"]:
                if s["id"] == sid:
                    s["groupId"] = gid
                    break
            save_config(config)
            js_eval_fn(f"window.dispatchEvent(new CustomEvent('service-moved',{{detail:{{id:'{sid}',groupId:'{gid}'}}}}));")
        elif aid in copy_map:
            gid = copy_map[aid]
            orig = next((s for s in config["services"] if s["id"] == sid), None)
            if orig:
                new_svc = {
                    "id": f"service_{uuid.uuid4().hex[:8]}",
                    "name": orig["name"], "url": orig["url"],
                    "muted": False, "groupId": gid,
                }
                config["services"].append(new_svc)
                save_config(config)
                create_view_fn(new_svc["id"], new_svc["url"])
                js_eval_fn(f"window.dispatchEvent(new CustomEvent('service-copied',{{detail:{json.dumps(new_svc)}}}));")


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
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


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
        remove_view_fn(sid)
        js_eval_fn(f"window.dispatchEvent(new CustomEvent('service-removed',{{detail:'{sid}'}}));")
        dialog.accept()

    del_btn.clicked.connect(on_delete)
    dialog.exec()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# グループ コンテキストメニュー
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def show_group_context_menu(
    gid: str, name: str, x: int, y: int,
    config: dict, js_eval_fn,
    active_menu_holder: list,
) -> None:
    """グループの右クリックメニューを表示する。"""
    if active_menu_holder[0]:
        active_menu_holder[0].close()
    menu = QMenu()
    menu.setStyleSheet(MENU_STYLE)
    active_menu_holder[0] = menu
    rename_a = menu.addAction("名前を変更")
    menu.addSeparator()
    delete_a = menu.addAction("削除")
    action = menu.exec(QPoint(x, y))
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
        js_eval_fn(f"window.dispatchEvent(new CustomEvent('group-removed',{{detail:'{gid}'}}));")
        dialog.close()

    del_btn.clicked.connect(on_delete)
    dialog.exec()
