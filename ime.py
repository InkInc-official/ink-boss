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
import re
import subprocess
import shutil
from pathlib import Path


def _machine_id() -> str | None:
    for path in ("/var/lib/dbus/machine-id", "/etc/machine-id"):
        try:
            mid = Path(path).read_text().strip()
            if mid:
                return mid
        except OSError:
            continue
    return None


def _ibus_address_files() -> list[Path]:
    """Qtのibusプラグインがibusバスのアドレスファイルとして探すパス
    （~/.config/ibus/bus/<machine-id>-<host>-<display番号>）。
    Waylandセッション上のXWayland等では WAYLAND_DISPLAY 名のファイルになる。"""
    mid = _machine_id()
    if not mid:
        return []
    cfg = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    bus_dir = cfg / "ibus" / "bus"
    names = []
    display = os.environ.get("DISPLAY", "")
    if display:
        host, _, rest = display.partition(":")
        names.append(f"{mid}-{host or 'unix'}-{rest.split('.')[0] or '0'}")
    wayland = os.environ.get("WAYLAND_DISPLAY")
    if wayland:
        names.append(f"{mid}-unix-{wayland}")
    if not names:
        names.append(f"{mid}-unix-0")
    return [bus_dir / n for n in names]


def ibus_bus_alive() -> tuple[bool, str]:
    """ibusバス（ibus-daemon、または fcitx5 の ibus フロントエンド）が実際に
    接続可能な状態かを、アドレスファイルとそのデーモンPIDの生存で判定する。

    「ibus-daemon というプロセスがいるか」では判定できない。fcitx5 は自前の
    ibusフロントエンドが ibus-daemon 無しでも同じアドレスファイルを作るため、
    ibus-daemon 不在の環境でも同梱ibusプラグイン経由でfcitx5に接続できる
    （隔離環境で実証済み: fcitx5側に frontend:ibus の入力コンテキストが作られる）。
    逆に、前回セッションの古いファイル（PIDが死んでいる）は接続できないので除外する。"""
    for f in _ibus_address_files():
        try:
            text = f.read_text()
        except OSError:
            continue
        m = re.search(r"^IBUS_DAEMON_PID=(\d+)", text, re.MULTILINE)
        if m and Path(f"/proc/{m.group(1)}").exists():
            return True, str(f)
    return False, ""


def setup_ime() -> str:
    """
    IMEバックエンドを自動検出し、PySide6プラグインをリンクして環境変数を設定する。

    Returns:
        str: 検出・設定されたバックエンド名
             "fcitx5(via ibus)"                            … ibus-daemon 経由
             "fcitx5(via ibus frontend, no ibus-daemon)"    … fcitx5のibusフロントエンド経由
             "fcitx5(direct, no ibus)"                      … ibusバスが無く、fcitx5へ直接接続
             "ibus" | "ibus(no daemon)" | "fcitx5(not running)" | "none"
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

    def _apply_env(module: str) -> None:
        """IM関連の環境変数を強制上書きする（setdefault 禁止。シェルの
        QT_IM_MODULE=fcitx 等が残っていると意図した経路にならない）"""
        os.environ["QT_IM_MODULE"] = module
        os.environ["XMODIFIERS"] = f"@im={module}"
        os.environ["GTK_IM_MODULE"] = module
        os.environ["INPUT_METHOD"] = module
        os.environ["SDL_IM_MODULE"] = module

    fcitx5_running = (
        subprocess.run(["pgrep", "-x", "fcitx5"], capture_output=True).returncode == 0
    )
    ibus_running = (
        subprocess.run(["pgrep", "-x", "ibus-daemon"], capture_output=True).returncode == 0
    )

    ibus_bus_ok, ibus_bus_file = ibus_bus_alive()

    # 重要:
    # システムの libfcitx5platforminputcontextplugin.so は distro の Qt6 向けで、
    # pip の PySide6 同梱 Qt とは PRIVATE_API が合わずロードに失敗する
    # （Qt_6_PRIVATE_API の undefined symbol。実機で確認済み）。
    # → 基本は PySide6 同梱の ibus プラグインを使い、fcitx5 の ibus フロントエンドへ繋ぐ。
    #   ibus-daemon が居なくても、fcitx5 の ibus フロントエンドが有効なら
    #   ibusのアドレスファイルが作られ、同じ経路で接続できる。
    if fcitx5_running:
        _link_plugin("libfcitx5platforminputcontextplugin.so")  # 直接接続用（環境によっては動く）
        _link_plugin("libibusplatforminputcontextplugin.so")
        if ibus_running or ibus_bus_ok:
            _apply_env("ibus")
            if ibus_running:
                backend = "fcitx5(via ibus)"
            else:
                backend = "fcitx5(via ibus frontend, no ibus-daemon)"
                print(f"[IME] ibus-daemon は無いが、fcitx5のibusフロントエンドが有効: {ibus_bus_file}", flush=True)
            return backend
        # ibus-daemon も、fcitx5のibusフロントエンドが作るアドレスファイルも無い
        # ＝ ibus経路では接続先が無い。fcitx5 のネイティブQtプラグインへ直接接続する。
        _apply_env("fcitx")
        print(
            "[IME] 注意: ibusバスが見つからないため fcitx5 へ直接接続します。"
            "ネイティブプラグインがPySide6同梱Qtとバージョン不一致でロードできない環境では"
            "IMEが有効になりません。その場合は fcitx5-configtool の「アドオン」で"
            "「IBus フロントエンド」を有効にしてください。",
            flush=True,
        )
        return "fcitx5(direct, no ibus)"

    elif ibus_running:
        _link_plugin("libibusplatforminputcontextplugin.so")
        os.environ["QT_IM_MODULE"] = "ibus"
        os.environ["XMODIFIERS"] = "@im=ibus"
        os.environ["GTK_IM_MODULE"] = "ibus"
        os.environ["INPUT_METHOD"] = "ibus"
        return "ibus"

    else:
        # デーモン未起動時も ibus プラグイン優先（後から fcitx5 が上がるケース）
        if _link_plugin("libibusplatforminputcontextplugin.so"):
            os.environ["QT_IM_MODULE"] = "ibus"
            os.environ["XMODIFIERS"] = "@im=ibus"
            os.environ["GTK_IM_MODULE"] = "ibus"
            return "ibus(no daemon)"
        if _link_plugin("libfcitx5platforminputcontextplugin.so"):
            os.environ["QT_IM_MODULE"] = "fcitx"
            os.environ["XMODIFIERS"] = "@im=fcitx"
            os.environ["GTK_IM_MODULE"] = "fcitx"
            return "fcitx5(not running)"
        return "none"
