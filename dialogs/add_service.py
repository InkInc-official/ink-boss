"""
dialogs/add_service.py - サービス追加ダイアログ
Ink Boss / Ink Inc.
"""

import json
import uuid
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox,
)
from PySide6.QtCore import Qt, QTimer
from config import DIALOG_STYLE, save_config
import workspaces as ws_mod


def show_add_service_dialog(config: dict, js_eval_fn, create_view_fn, group_id: str = "", initial_url: str = "") -> None:
    wid_active = config.get("active_workspace", ws_mod.ALL_ID)
    if ws_mod.find(config, wid_active) is None:
        wid_active = ws_mod.ALL_ID
    workspaces = config.get("workspaces", [])
    gid_init = group_id or None

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

    layout.addWidget(QLabel("エンジン"))
    engine_combo = QComboBox()
    engine_combo.addItem("Qt（Googleログイン向け）", "qt")
    engine_combo.addItem("Electron（メール/パスワード向け）", "electron")
    engine_combo.setCurrentIndex(1)
    layout.addWidget(engine_combo)
    hint = QLabel("Googleログイン → Qt ／ メール+パスワード → Electron")
    hint.setWordWrap(True)
    hint.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 11px;")
    layout.addWidget(hint)

    def _suggest(text: str) -> None:
        t = text.lower()
        googleish = any(
            h in t
            for h in (
                "google.", "youtube.", "gmail.", "accounts.google",
                "docs.google", "drive.google", "meet.google",
            )
        )
        engine_combo.setCurrentIndex(0 if googleish else 1)

    url_input.textChanged.connect(_suggest)
    if initial_url:
        url_input.setText(initial_url)

    # 追加先のワークスペース（初期値は今開いているワークスペース）
    ws_combo = None
    if workspaces:
        layout.addWidget(QLabel("ワークスペース"))
        ws_combo = QComboBox()
        ws_combo.addItem("すべて", ws_mod.ALL_ID)
        for w in workspaces:
            ws_combo.addItem(w["name"], w["id"])
        idx = ws_combo.findData(wid_active)
        ws_combo.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addWidget(ws_combo)

    def _chosen_ws() -> str:
        return (ws_combo.currentData() if ws_combo else ws_mod.ALL_ID) or ws_mod.ALL_ID

    def _groups_for(wid: str) -> list:
        if ws_mod.is_all(wid):
            return config.get("groups", [])
        w = ws_mod.find(config, wid)
        return w["groups"] if w else []

    group_label = QLabel("グループ（任意）")
    group_combo = QComboBox()
    layout.addWidget(group_label)
    layout.addWidget(group_combo)

    def _fill_groups() -> None:
        group_combo.clear()
        gs = _groups_for(_chosen_ws())
        group_combo.addItem("グループなし", "")
        for g in gs:
            group_combo.addItem(g["name"], g["id"])
        # 呼び出し元がグループを指定していて、候補にあれば選んでおく
        if gid_init:
            i = group_combo.findData(gid_init)
            if i >= 0:
                group_combo.setCurrentIndex(i)
        visible = bool(gs)
        group_label.setVisible(visible)
        group_combo.setVisible(visible)

    _fill_groups()
    if ws_combo:
        ws_combo.currentIndexChanged.connect(lambda _=None: _fill_groups())

    btn_layout = QHBoxLayout()
    cancel_btn = QPushButton("キャンセル")
    add_btn = QPushButton("追加")
    add_btn.setObjectName("addBtn")
    btn_layout.addWidget(cancel_btn)
    btn_layout.addWidget(add_btn)
    layout.addLayout(btn_layout)

    cancel_btn.clicked.connect(dialog.reject)
    accepted = {"svc": None}

    def on_accept():
        name = name_input.text().strip()
        url = url_input.text().strip()
        if not name or not url:
            return
        if not url.startswith("http"):
            url = f"https://{url}"
        gid = group_combo.currentData() or None
        wid = _chosen_ws()
        in_ws = not ws_mod.is_all(wid)
        eng = engine_combo.currentData() or "qt"
        svc = {
            "id": f"service_{uuid.uuid4().hex[:8]}",
            "name": name,
            "url": url,
            "muted": False,
            "groupId": None if in_ws else (gid or None),
            "engine": eng,
        }
        config["services"].append(svc)
        ws_ids = []
        if in_ws:
            # 本体は1つだけ作り、選んだワークスペースに載せる
            ws_mod.add_service(config, wid, svc["id"], gid)
            ws_ids = [wid]
        save_config(config)
        svc = dict(svc)
        svc["workspaceIds"] = ws_ids
        svc["wsGroupId"] = (gid or None) if in_ws else None
        accepted["svc"] = svc
        dialog.accept()

    def on_finished():
        svc = accepted["svc"]
        if svc is None:
            return
        if (svc.get("engine") or "qt") != "electron":
            QTimer.singleShot(100, lambda: create_view_fn(svc["id"], svc["url"]))
        QTimer.singleShot(200, lambda: js_eval_fn(
            f"window.dispatchEvent(new CustomEvent('service-added',{{detail:{json.dumps(svc)}}}))"
        ))

    add_btn.clicked.connect(on_accept)
    name_input.returnPressed.connect(on_accept)
    url_input.returnPressed.connect(on_accept)
    dialog.finished.connect(on_finished)
    name_input.setFocus()
    dialog.exec()
