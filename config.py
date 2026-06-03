"""
config.py - 定数・設定ファイル読み書き
Ink Boss / Ink Inc.

使い方:
    from config import (
        CONFIG_FILE, SESSIONS_DIR, SIDEBAR_W, URLBAR_H,
        DIALOG_STYLE, MENU_STYLE,
        load_config, save_config,
    )
"""

import json
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# パス定数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIG_DIR   = Path.home() / ".config" / "ink-boss"
CONFIG_FILE  = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# レイアウト定数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SIDEBAR_W = 208
URLBAR_H  = 40

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# デフォルト設定
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEFAULT_CONFIG: dict = {
    "version": "2.0.0",
    "theme": "dark",
    "llm": {
        "backend": "ollama",
        "ollamaUrl": "http://localhost:11434",
        "ollamaModel": "llama3",
        "claudeApiKey": "",
        "geminiApiKey": "",
    },
    "hibernate_minutes": 10,
    "knowledge": "",
    "services": [],
    "groups": [],
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# スタイル定数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DIALOG_STYLE = """
QDialog { background-color: #111118; color: white; }
QLabel { color: rgba(255,255,255,0.5); font-size: 12px; }
QLineEdit {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px; padding: 8px 12px;
    color: white; font-size: 13px;
}
QLineEdit:focus { border: 1px solid rgba(255,255,255,0.3); }
QPushButton {
    border-radius: 8px; padding: 8px 16px; font-size: 13px;
    border: 1px solid rgba(255,255,255,0.15);
    color: rgba(255,255,255,0.6); background: transparent;
}
QPushButton:hover { background: rgba(255,255,255,0.08); color: white; }
QPushButton#addBtn { border: 1px solid rgba(255,255,255,0.4); color: white; }
QComboBox {
    background: #111118; border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px; padding: 8px 12px; color: white; font-size: 13px;
}
QComboBox QAbstractItemView {
    background: #111118; color: white;
    selection-background-color: rgba(255,255,255,0.1);
}
QFrame#card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08); border-radius: 10px;
}
QTabWidget::pane { border: none; background-color: #111118; }
QTabBar::tab {
    background: transparent; color: rgba(255,255,255,0.4);
    padding: 8px 16px; border-radius: 8px; font-size: 13px; min-width: 70px;
}
QTabBar::tab:selected {
    background: rgba(255,255,255,0.1); color: white;
    border: 1px solid rgba(255,255,255,0.15);
}
QTabBar::tab:hover { color: rgba(255,255,255,0.7); }
"""

MENU_STYLE = """
QMenu {
    background-color: #111118;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 10px; padding: 4px;
    color: rgba(255,255,255,0.75); font-size: 13px;
}
QMenu::item { padding: 7px 16px; border-radius: 6px; min-width: 160px; }
QMenu::item:selected { background-color: rgba(255,255,255,0.08); color: white; }
QMenu::separator { height: 1px; background: rgba(255,255,255,0.07); margin: 3px 8px; }
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 設定 I/O
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def load_config() -> dict:
    """config.jsonを読み込む。存在しなければデフォルト値を返す。"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """configをconfig.jsonに書き込む。"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
