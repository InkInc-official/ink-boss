"""
platform_paths.py - OSごとの保存先パス
Ink Boss / Ink Inc.

設定・セッション・Electronのユーザーデータなど、アプリが書き込む場所の
OS差異をここに集める。標準ライブラリのみに依存する（循環importを避けるため、
config.py / ime.py など低レベルのモジュールからも安全に読み込める）。

  Linux・その他 : ~/.config/ink-boss   （従来どおり。XDG_CONFIG_HOMEは見ない:
                   既存ユーザーの保存先を変えないため）
  Windows       : %APPDATA%\\ink-boss  （APPDATAが無い環境では ~/AppData/Roaming/ink-boss）

【重要】electron-engine/main.js の USER_DATA も、同じ規則で
同じフォルダ配下(electron-userdata)を指すこと。片方だけ変えると、PythonとElectronで
保存先が食い違ってセッションが消える。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "ink-boss"


def config_dir() -> Path:
    """設定ファイル・セッション等の保存ディレクトリ（作成はしない）。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return root / APP_DIR_NAME
    return Path.home() / ".config" / APP_DIR_NAME
