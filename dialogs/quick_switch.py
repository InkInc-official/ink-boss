"""
dialogs/quick_switch.py - クイック切替（Ctrl+Alt+K）
Ink Boss / Ink Inc.

名前（またはURL）で絞り込み、サービス／ワークスペースへ移動する小さな検索窓。
  ↑↓ で選択 / Enter で移動 / Esc で閉じる
戻り値: ("service", サービスID) / ("workspace", ワークスペースID) / None
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel,
)
from PySide6.QtCore import Qt
from config import DIALOG_STYLE
import workspaces as ws_mod

_LIST_STYLE = """
QListWidget {
    background: transparent; border: none; outline: none;
    color: rgba(255,255,255,0.8); font-size: 13px;
}
QListWidget::item { padding: 7px 10px; border-radius: 8px; }
QListWidget::item:selected { background: rgba(255,255,255,0.1); color: white; }
"""


class _SearchInput(QLineEdit):
    """↑↓ / PageUp/PageDown を一覧の選択移動に回す（入力欄にフォーカスしたまま操作できる）。"""

    def __init__(self, lst: QListWidget):
        super().__init__()
        self._lst = lst

    def keyPressEvent(self, ev):
        step = {
            Qt.Key.Key_Down: 1, Qt.Key.Key_Up: -1,
            Qt.Key.Key_PageDown: 8, Qt.Key.Key_PageUp: -8,
        }.get(ev.key())
        if step is not None and self._lst.count():
            row = max(0, min(self._lst.count() - 1, self._lst.currentRow() + step))
            self._lst.setCurrentRow(row)
            return
        super().keyPressEvent(ev)


def _entries(config: dict):
    """(表示名, 検索用テキスト, ("service"|"workspace", id)) の一覧。"""
    out = []
    for i, w in enumerate([{"id": ws_mod.ALL_ID, "name": "すべて"}] + list(config.get("workspaces", []))):
        out.append((f"[WS {i}]  {w.get('name', '')}", f"ws {i} ワークスペース {w.get('name', '')}".lower(),
                    ("workspace", w["id"])))
    for s in config.get("services", []):
        name = s.get("name", "")
        out.append((name, f"{name} {s.get('url', '')}".lower(), ("service", s["id"])))
    return out


def show_quick_switch_dialog(config: dict):
    entries = _entries(config)

    dialog = QDialog()
    dialog.setWindowTitle("クイック切替")
    dialog.setFixedSize(460, 380)
    dialog.setStyleSheet(DIALOG_STYLE)
    dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 16, 16, 12)
    layout.setSpacing(10)

    lst = QListWidget()
    lst.setStyleSheet(_LIST_STYLE)
    lst.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    inp = _SearchInput(lst)
    inp.setPlaceholderText("サービス名・ワークスペース名で検索")
    layout.addWidget(inp)
    layout.addWidget(lst)
    hint = QLabel("↑↓ 選択　Enter 移動　Esc 閉じる")
    hint.setStyleSheet("color: rgba(255,255,255,0.25); font-size: 10px;")
    layout.addWidget(hint)

    result = {"value": None}

    def refill(text: str = ""):
        q = text.strip().lower()
        lst.clear()
        for label, hay, target in entries:
            if all(tok in hay for tok in q.split()):
                it = QListWidgetItem(label)
                it.setData(Qt.ItemDataRole.UserRole, target)
                lst.addItem(it)
        if lst.count():
            lst.setCurrentRow(0)

    def accept_current(*_):
        it = lst.currentItem()
        if it is None:
            return
        result["value"] = it.data(Qt.ItemDataRole.UserRole)
        dialog.accept()

    inp.textChanged.connect(refill)
    inp.returnPressed.connect(accept_current)
    lst.itemDoubleClicked.connect(accept_current)
    refill()
    inp.setFocus()
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    inp.setFocus()
    dialog.exec()
    return result["value"]
