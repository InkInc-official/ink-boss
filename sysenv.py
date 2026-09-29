"""
sysenv.py - 外部システムコマンド呼び出し用の環境サニタイズヘルパー
Ink Boss / Ink Inc.

PyInstaller(--onedir)でパッケージ化された実行ファイルは、ブートローダーが
同梱ライブラリ（_internal/配下）をシステムのライブラリより優先させるため
LD_LIBRARY_PATHを書き換える。さらに、PySide6が間接的に依存するGTK/GI関連の
PyInstallerランタイムフック（pyi_rth_gtk.py等）が、GTK_PATH・
GTK_EXE_PREFIX・GTK_DATA_PREFIX・GI_TYPELIB_PATHを_internal配下へ向ける。

この汚染された環境を、Ink Boss自身のバイナリ（PySide6本体やElectron本体を
除く、システムに元から入っている外部コマンド）のsubprocessへそのまま
継承させると、それらのコマンドがシステムのライブラリではなく同梱の
（ABIが異なる可能性がある）ライブラリを誤ってロードしてしまい、原因の
分かりにくいバージョン不一致エラーで失敗する。実際にこのバグを3回踏んだ:

  1. dbus-send: libdbus-1.so.3のバージョン不一致
     （"version `LIBDBUS_PRIVATE_1.16.2' not found"、IME診断機能）
  2. Electron本体: libgtk-3.so.0のバージョン不一致
     （fcitx5用GTKモジュールが正しくロードされない）
  3. curl: libssl.so.3のバージョン不一致
     （"version `OPENSSL_3.2.0' not found"、Ollamaインストール）

外部システムコマンド（curl, dbus-send, wmctrl, xdotool, xprop,
fcitx5-remote, pgrep, dpkg, pkexec, ollama等 — Ink Boss自身がビルドした
バイナリではないもの全て）をsubprocessで呼ぶ箇所は、必ずこのモジュールの
get_clean_subprocess_env()を通した環境を渡すこと。個別に
os.environ.copy()してLD_LIBRARY_PATHだけ消す、といった対策をその場限りで
繰り返すと、同じバグが4件目5件目と再発し続ける（実際に3回繰り返した後に
この共通化を行った）。

Electron本体の起動（electron_bridge.py）のように、追加で他の環境変数の
設定も必要な場合は、まずこのヘルパーで土台を作ってから追加設定を重ねる。
"""

import os

# PyInstallerのブートローダー、および間接依存するGTK/GIランタイムフック
# (pyi_rth_gtk.py等)が_internal配下を指すよう書き換える環境変数。
_POLLUTED_ENV_KEYS = (
    "GTK_PATH",
    "GTK_EXE_PREFIX",
    "GTK_DATA_PREFIX",
    "GI_TYPELIB_PATH",
)


def get_clean_subprocess_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """外部システムコマンド（Ink Boss自身のバイナリではないもの）を
    subprocessで呼ぶ際に渡す、サニタイズ済みの環境変数辞書を返す。

    base_env省略時は現在のプロセス環境(os.environ)をコピーして使う。

    - LD_LIBRARY_PATH: PyInstallerがLD_LIBRARY_PATH_ORIGへ元の値を退避
      している場合（ユーザーが元々LD_LIBRARY_PATHを設定していた場合）は
      それを復元し、なければ削除する（同梱の_internalを外部コマンドに
      見せない）。
    - GTK_PATH / GTK_EXE_PREFIX / GTK_DATA_PREFIX / GI_TYPELIB_PATH:
      外部コマンド自身には無関係なため単純に削除する。

    GTK_IM_MODULE・XMODIFIERS・DISPLAY等、IME判定や表示に必要な変数は
    一切変更しない。"""
    env = dict(base_env) if base_env is not None else os.environ.copy()
    orig_ld = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if orig_ld is not None:
        env["LD_LIBRARY_PATH"] = orig_ld
    else:
        env.pop("LD_LIBRARY_PATH", None)
    for key in _POLLUTED_ENV_KEYS:
        env.pop(key, None)
    return env
