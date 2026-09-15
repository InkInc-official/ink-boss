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


def show_add_service_dialog(config: dict, js_eval_fn, create_view_fn, group_id: str = "") -> None:
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

    cancel_btn.clicked.connect(dialog.reject)
    accepted = {"svc": None}

    def on_accept():
        name = name_input.text().strip()
        url = url_input.text().strip()
        if not name or not url:
            return
        if not url.startswith("http"):
            url = f"https://{url}"
        gid = (group_combo.currentData() or None) if group_combo else (gid_init or None)
        eng = engine_combo.currentData() or "qt"
        svc = {
            "id": f"service_{uuid.uuid4().hex[:8]}",
            "name": name,
            "url": url,
            "muted": False,
            "groupId": gid or None,
            "engine": eng,
        }
        config["services"].append(svc)
        save_config(config)
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
