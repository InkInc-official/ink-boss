"""
dialogs/add_workspace.py - ワークスペース作成ダイアログ
Ink Boss / Ink Inc.
"""

import json
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)
from PySide6.QtCore import Qt
from config import DIALOG_STYLE, save_config
import workspaces as ws_mod


def show_add_workspace_dialog(config: dict, js_eval_fn) -> None:
    dialog = QDialog()
    dialog.setWindowTitle("ワークスペースを作成")
    dialog.setMinimumWidth(350)
    dialog.setStyleSheet(DIALOG_STYLE)
    dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(12)
    layout.setContentsMargins(24, 24, 24, 24)

    layout.addWidget(QLabel("ワークスペース名"))
    name_input = QLineEdit()
    name_input.setPlaceholderText("配信")
    layout.addWidget(name_input)

    btn_layout = QHBoxLayout()
    cancel_btn = QPushButton("キャンセル")
    add_btn    = QPushButton("作成")
    add_btn.setObjectName("addBtn")
    btn_layout.addWidget(cancel_btn)
    btn_layout.addWidget(add_btn)
    layout.addLayout(btn_layout)

    cancel_btn.clicked.connect(dialog.reject)

    def on_accept():
        name = name_input.text().strip()
        if not name:
            return
        ws = ws_mod.add_workspace(config, name)
        ws_mod.set_active(config, ws["id"])  # 作ったらそのまま切り替える
        save_config(config)
        js_eval_fn(f"window.dispatchEvent(new CustomEvent('workspace-added',{{detail:{json.dumps(ws)}}}));")
        dialog.accept()

    add_btn.clicked.connect(on_accept)
    name_input.returnPressed.connect(on_accept)
    name_input.setFocus()
    dialog.exec()
