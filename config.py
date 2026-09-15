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
# サービスの engine マイグレーション
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# デュアルエンジン方式の導入以前に追加されたサービスは "engine" キーを
# 持たない。フロント側(ServiceModal.tsx の suggestEngine)と同じ判定基準で
# 一度だけ補完し、以降は明示的な値として永続化する。
_GOOGLE_ENGINE_HINTS = (
    "google.",
    "youtube.",
    "gmail.",
    "accounts.google",
    "googleapis.",
    "docs.google",
    "drive.google",
    "meet.google",
    "calendar.google",
)


def _suggest_engine(url: str) -> str:
    host = (url or "").strip().lower()
    host = host.replace("https://", "").replace("http://", "").split("/")[0]
    if any(hint in host for hint in _GOOGLE_ENGINE_HINTS):
        return "qt"
    return "electron"


def _migrate_service_engines(config: dict) -> bool:
    """engine 未設定のサービスに qt/electron を補完する。変更があれば True。"""
    changed = False
    for svc in config.get("services", []):
        if not svc.get("engine"):
            svc["engine"] = _suggest_engine(svc.get("url", ""))
            print(
                f"[config] Migrated engine for '{svc.get('name')}' -> {svc['engine']}",
                flush=True,
            )
            changed = True
    return changed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 設定 I/O
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def load_config() -> dict:
    """config.jsonを読み込む。存在しなければデフォルト値を返す。
    存在する場合は、デフォルト値とマージして、新しい設定項目も反映されるようにする。
    """
    print("[config] load_config started.", flush=True) # debug
    loaded_config = DEFAULT_CONFIG.copy() # デフォルト設定で初期化
    print(f"[config] Initial loaded_config: {json.dumps(loaded_config, ensure_ascii=False)}", flush=True) # debug

    if CONFIG_FILE.exists():
        print(f"[config] {CONFIG_FILE} exists.", flush=True) # debug
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            print(f"[config] Loaded user_config from file: {json.dumps(user_config, ensure_ascii=False)}", flush=True) # debug

            # 既存の設定とデフォルト設定をマージする
            for key, default_value in DEFAULT_CONFIG.items():
                if key == "services":
                    # services はユーザーが設定したものなので、デフォルト値ではなくuser_configのものを優先する
                    if "services" in user_config:
                        loaded_config["services"] = user_config["services"]
                        print(f"[config] Merging: Used user_config for 'services'", flush=True) # debug
                elif key == "groups":
                    # groups はユーザーが設定したものなので、デフォルト値ではなくuser_configのものを優先する
                    if "groups" in user_config:
                        loaded_config["groups"] = user_config["groups"]
                        print(f"[config] Merging: Used user_config for 'groups'", flush=True) # debug
                else:
                    # その他のキーは、user_configにあればそれを使用、なければDEFAULT_CONFIGの値を使用
                    if key in user_config:
                        # 型が異なる場合はDEFAULT_CONFIGの型に合わせる試み
                        if isinstance(default_value, int) and isinstance(user_config[key], bool):
                            # hibernate_minutes: false のようなケースに対応
                            loaded_config[key] = default_value # デフォルト値に戻す
                            print(f"[config] Merging: Corrected type for '{key}', reset to default.", flush=True) # debug
                        else:
                            loaded_config[key] = user_config[key]
                            print(f"[config] Merging: Updated '{key}' from user_config", flush=True) # debug
                    else:
                        loaded_config[key] = default_value
                        print(f"[config] Merging: Added default '{key}'", flush=True) # debug

        except json.JSONDecodeError:
            print(f"[config] config.json is corrupted, using default config. Path: {CONFIG_FILE}", flush=True)
            # 破損している場合はデフォルト設定をそのまま使用
            return DEFAULT_CONFIG.copy()
    else:
        print(f"[config] {CONFIG_FILE} does not exist. Using default config.", flush=True) # debug

    if _migrate_service_engines(loaded_config):
        save_config(loaded_config)

    print(f"[config] Final loaded_config before return: {json.dumps(loaded_config, ensure_ascii=False)}", flush=True) # debug
    return loaded_config
def save_config(config: dict) -> None:
    """configをconfig.jsonに書き込む。"""
    print(f"[config] save_config called. Config to save: {json.dumps(config, ensure_ascii=False)}", flush=True) # debug
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"[config] save_config completed. File: {CONFIG_FILE}", flush=True) # debug
