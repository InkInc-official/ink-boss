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
from PySide6.QtCore import Qt
from config import DIALOG_STYLE, save_config


def show_add_service_dialog(config: dict, js_eval_fn, create_view_fn, group_id: str = "") -> None:
    """
    サービス追加ダイアログを表示する。

    Args:
        config:         現在のconfig dict
        js_eval_fn:     JSイベント発火用関数
        create_view_fn: bridge._create_view(sid, url) 相当の関数
        group_id:       初期選択グループID（任意）
    """
    groups = config.get("groups", [])
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

    group_combo = None
    if groups:
        layout.addWidget(QLabel("グループ（任意）"))
        group_combo = QComboBox()
        group_combo.addItem("グループなし", "")
        for g in groups:
            group_combo.addItem(g["name"], g["id"])
        layout.addWidget(group_combo)

    btn_layout = QHBoxLayout()
    cancel_btn = QPushButton("キャンセル")
    add_btn = QPushButton("追加")
    add_btn.setObjectName("addBtn")
    btn_layout.addWidget(cancel_btn)
    btn_layout.addWidget(add_btn)
    layout.addLayout(btn_layout)

    cancel_btn.clicked.connect(dialog.close)

    def on_accept():
        name = name_input.text().strip()
        url  = url_input.text().strip()
        if not name or not url:
            return
        if not url.startswith("http"):
            url = f"https://{url}"
        gid = (group_combo.currentData() or None) if group_combo else (gid_init or None)
        svc = {
            "id": f"service_{uuid.uuid4().hex[:8]}",
            "name": name, "url": url, "muted": False, "groupId": gid or None,
        }
        config["services"].append(svc)
        save_config(config)
        create_view_fn(svc["id"], url)
        js_eval_fn(f"window.dispatchEvent(new CustomEvent('service-added',{{detail:{json.dumps(svc)}}}));")
        dialog.close()

    add_btn.clicked.connect(on_accept)
    name_input.setFocus()
    dialog.exec()
