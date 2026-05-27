"""
dialogs/add_group.py - グループ追加ダイアログ
Ink Boss / Ink Inc.
"""

import json
import uuid
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)
from PySide6.QtCore import Qt
from config import DIALOG_STYLE, save_config


def show_add_group_dialog(config: dict, js_eval_fn) -> None:
    """
    グループ追加ダイアログを表示する。

    Args:
        config:     現在のconfig dict
        js_eval_fn: JSイベント発火用関数
    """
    dialog = QDialog()
    dialog.setWindowTitle("グループを追加")
    dialog.setMinimumWidth(350)
    dialog.setStyleSheet(DIALOG_STYLE)
    dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(12)
    layout.setContentsMargins(24, 24, 24, 24)

    layout.addWidget(QLabel("グループ名"))
    name_input = QLineEdit()
    name_input.setPlaceholderText("SNS")
    layout.addWidget(name_input)

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
        if not name:
            return
        g = {"id": f"group_{uuid.uuid4().hex[:8]}", "name": name, "collapsed": False}
        config["groups"].append(g)
        save_config(config)
        js_eval_fn(f"window.dispatchEvent(new CustomEvent('group-added',{{detail:{json.dumps(g)}}}));")
        dialog.close()

    add_btn.clicked.connect(on_accept)
    name_input.setFocus()
    dialog.exec()
