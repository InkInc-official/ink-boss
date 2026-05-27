"""
ime.py - IME自動検出・プラグインリンク
Ink Boss / Ink Inc.

すべてのimport・QApplication生成より前に呼ぶこと。
配布対応：fcitx5 / ibus を自動検出し、PySide6へプラグインを自動リンクする。

使い方:
    from ime import setup_ime
    ime_backend = setup_ime()
    print(f"[IME] backend={ime_backend}")
"""

import os
import subprocess
import shutil
from pathlib import Path


def setup_ime() -> str:
    """
    IMEバックエンドを自動検出し、PySide6プラグインをリンクして環境変数を設定する。

    Returns:
        str: 検出・設定されたバックエンド名
             "fcitx5(via ibus)" | "ibus" | "fcitx5(not running)" | "none"
    """
    try:
        import PySide6
        pyside_plugin_dir = (
            Path(PySide6.__file__).parent / "Qt" / "plugins" / "platforminputcontexts"
        )
    except Exception:
        return "none"

    sys_plugin_dirs = [
        Path("/usr/lib/x86_64-linux-gnu/qt6/plugins/platforminputcontexts"),
        Path("/usr/lib/qt6/plugins/platforminputcontexts"),
        Path("/usr/lib/aarch64-linux-gnu/qt6/plugins/platforminputcontexts"),
    ]

    def _link_plugin(name: str) -> bool:
        """システムのプラグインをPySide6ディレクトリにリンク（なければコピー）"""
        dst = pyside_plugin_dir / name
        if dst.exists() or dst.is_symlink():
            return True
        for sys_dir in sys_plugin_dirs:
            src = sys_dir / name
            if src.exists():
                try:
                    os.symlink(src, dst)
                    return True
                except PermissionError:
                    try:
                        shutil.copy2(src, dst)
                        return True
                    except Exception:
                        pass
        return False

    fcitx5_running = (
        subprocess.run(["pgrep", "-x", "fcitx5"], capture_output=True).returncode == 0
    )
    ibus_running = (
        subprocess.run(["pgrep", "-x", "ibus-daemon"], capture_output=True).returncode == 0
    )

    if fcitx5_running:
        _link_plugin("libfcitx5platforminputcontextplugin.so")
        os.environ["QT_IM_MODULE"]  = "ibus"
        os.environ["XMODIFIERS"]    = "@im=ibus"
        os.environ["GTK_IM_MODULE"] = "ibus"
        os.environ["INPUT_METHOD"]  = "ibus"
        os.environ["SDL_IM_MODULE"] = "ibus"
        existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            existing + " --ozone-platform-hint=auto"
        ).strip()
        return "fcitx5(via ibus)"

    elif ibus_running:
        _link_plugin("libibusplatforminputcontextplugin.so")
        os.environ["QT_IM_MODULE"]  = "ibus"
        os.environ["XMODIFIERS"]    = "@im=ibus"
        os.environ["GTK_IM_MODULE"] = "ibus"
        os.environ["INPUT_METHOD"]  = "ibus"
        return "ibus"

    else:
        if _link_plugin("libfcitx5platforminputcontextplugin.so"):
            os.environ["QT_IM_MODULE"]  = "fcitx"
            os.environ["XMODIFIERS"]    = "@im=fcitx"
            os.environ["GTK_IM_MODULE"] = "fcitx"
            return "fcitx5(not running)"
        return "none"
