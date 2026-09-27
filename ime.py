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

import glob
import os
import re
import socket
import subprocess
import shutil
from pathlib import Path


# [IME-DEBUG] ログで出す環境変数。子プロセス（Qt本体・Electron）が実際に受け取る値を
# 「上書きした後」の状態で確認するためのもの（起動前の値だけでは、IMEが効かない原因が
# 上書きにあるのかシステム側にあるのか切り分けられない）。
_IME_ENV_KEYS = (
    "QT_IM_MODULE", "GTK_IM_MODULE", "XMODIFIERS", "INPUT_METHOD", "SDL_IM_MODULE",
    "DISPLAY", "WAYLAND_DISPLAY", "XDG_SESSION_TYPE", "QT_PLUGIN_PATH",
)


def describe_ime_env(env=None) -> str:
    env = os.environ if env is None else env
    return " ".join(f"{k}={env.get(k) if env.get(k) is not None else '(未設定)'}" for k in _IME_ENV_KEYS)


def log_ime_env(label: str, env=None) -> None:
    """例: [IME-DEBUG] Electron子プロセスへ渡す環境変数: QT_IM_MODULE=ibus GTK_IM_MODULE=fcitx ..."""
    print(f"[IME-DEBUG] {label}: {describe_ime_env(env)}", flush=True)


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
    （~/.config/ibus/bus/<machine-id>-<host>-<display>）。

    Qtは WAYLAND_DISPLAY が設定されていればそちらを優先して
    「-unix-<WAYLAND_DISPLAY>」を、無ければ DISPLAY から「-unix-<番号>」を開く
    （strace で確認済み。両方設定されている混在環境でも wayland 側を開く）。
    fcitx5 は X11 セッション（WAYLAND_DISPLAY 未設定）でも、同一内容の
    「-unix-<番号>」「-unix-wayland-0」の2ファイルを常に作る（同じアドレス・同じPID）
    ため、2ファイルが併存していること自体は環境変数混在の兆候ではない。"""
    mid = _machine_id()
    if not mid:
        return []
    cfg = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    bus_dir = cfg / "ibus" / "bus"
    wayland = os.environ.get("WAYLAND_DISPLAY")
    display = os.environ.get("DISPLAY", "")
    if wayland:
        name = f"{mid}-unix-{wayland}"
    elif display:
        host, _, rest = display.partition(":")
        name = f"{mid}-{host or 'unix'}-{rest.split('.')[0] or '0'}"
    else:
        name = f"{mid}-unix-0"
    return [bus_dir / name]


def _ibus_socket_connectable(address: str) -> bool | None:
    """IBUS_ADDRESS の unix ソケットに実際に接続できるか。
    True/False。判定できない形式（tcp等）は None（＝否定しない）。"""
    for part in address.split(","):
        if part.startswith("unix:path="):
            target = part[len("unix:path="):]
        elif part.startswith("unix:abstract="):
            target = "\0" + part[len("unix:abstract="):]
        else:
            continue
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.connect(target)
            return True
        except OSError:
            return False
        finally:
            s.close()
    return None


def ibus_bus_status() -> list[dict]:
    """Qtが開くアドレスファイルの状態（存在・PID生存・ソケット接続可否）。"""
    out = []
    for f in _ibus_address_files():
        st = {"file": str(f), "exists": False, "pid": None, "pid_alive": False, "socket_ok": None}
        try:
            text = f.read_text()
        except OSError:
            out.append(st)
            continue
        st["exists"] = True
        m = re.search(r"^IBUS_DAEMON_PID=(\d+)", text, re.MULTILINE)
        if m:
            st["pid"] = int(m.group(1))
            st["pid_alive"] = Path(f"/proc/{m.group(1)}").exists()
        a = re.search(r"^IBUS_ADDRESS=(.+)$", text, re.MULTILINE)
        if a and st["pid_alive"]:
            st["socket_ok"] = _ibus_socket_connectable(a.group(1).strip())
        out.append(st)
    return out


def ibus_bus_alive() -> tuple[bool, str]:
    """ibusバス（ibus-daemon、または fcitx5 の ibus フロントエンド）が実際に
    接続可能な状態かを判定する。アドレスファイルの存在に加え、記載PIDの生存と、
    ソケットへの実接続で確認する。

    「ibus-daemon というプロセスがいるか」では判定できない。fcitx5 は自前の
    ibusフロントエンドが ibus-daemon 無しでも同じアドレスファイルを作るため、
    ibus-daemon 不在の環境でも同梱ibusプラグイン経由でfcitx5に接続できる
    （隔離環境で実証済み: fcitx5側に frontend:ibus の入力コンテキストが作られる）。
    逆に、前回セッションの古いファイル（PIDが死んでいる／PIDが別プロセスに再利用
    されてソケットが無い）は接続できないので除外する。"""
    for st in ibus_bus_status():
        if st["exists"] and st["pid_alive"] and st["socket_ok"] is not False:
            return True, st["file"]
    return False, ""


def _gtk_immodule_exists(name: str) -> bool:
    """GTK3 の入力メソッドモジュール（im-<name>.so）が導入されているか。
    Electron(Chromium/GTK)のIMEは GTK_IM_MODULE のモジュールが実在しないと
    一切接続されない（隔離環境で確認済み）。"""
    patterns = [
        f"/usr/lib/*/gtk-3.0/*/immodules/im-{name}.so",
        f"/usr/lib/gtk-3.0/*/immodules/im-{name}.so",
        f"/usr/lib64/gtk-3.0/*/immodules/im-{name}.so",
    ]
    return any(glob.glob(p) for p in patterns)


def _setup_ime_impl() -> str:
    """
    IMEバックエンドを自動検出し、PySide6プラグインをリンクして環境変数を設定する。

    Returns:
        str: 検出・設定されたバックエンド名
             "fcitx5(via ibus)"                            … ibus-daemon 経由
             "fcitx5(via ibus frontend, no ibus-daemon)"    … fcitx5のibusフロントエンド経由
             "fcitx5(direct, no ibus)"                      … ibusバスが無く、fcitx5へ直接接続
             "ibus" | "ibus(no daemon)" | "fcitx5(not running)" | "none"
    """
    log_ime_env("setup_ime呼び出し前（システム側の値）")
    system_env = {k: os.environ.get(k) for k in ("QT_IM_MODULE", "GTK_IM_MODULE", "XMODIFIERS")}
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

    def _native_fcitx_plugin_loadable() -> tuple[bool, str]:
        """システムのfcitx5用Qtプラグインを、いまのQt(PySide6同梱)が実際にロードできるか。
        QPluginLoader でQt自身に判定させる（PRIVATE_APIの不一致は dlopen で失敗する）。
        ロードできるのは PySide6 のQtとdistroのQt6が一致している環境に限られる。"""
        try:
            from PySide6.QtCore import QPluginLoader
        except Exception as e:
            return False, f"QPluginLoader を使えません: {e}"
        for d in sys_plugin_dirs:
            cand = d / "libfcitx5platforminputcontextplugin.so"
            if cand.exists():
                loader = QPluginLoader(str(cand))
                ok = loader.load()
                err = "" if ok else loader.errorString()
                if ok:
                    loader.unload()
                return ok, err
        return False, "システムにfcitx5用Qtプラグインが見つかりません"

    def _apply_env(qt_module: str, gtk_module: str | None = None, xim: str | None = None,
                   keep: frozenset = frozenset()) -> None:
        """IM関連の環境変数を上書きする（setdefault 禁止。シェルの
        QT_IM_MODULE=fcitx 等が残っていると意図した経路にならない）。

        Qt（同梱ibusプラグイン）と GTK（Electron/Chromium）は別経路なので
        別々に指定できる。GTK_IM_MODULE は Electron サブプロセスにも継承される。
        keep に "qt" / "gtk" / "xim" を入れた項目は、システム側が既に設定している
        値を尊重して上書きしない。"""
        gtk_module = gtk_module or qt_module
        if "qt" not in keep:
            os.environ["QT_IM_MODULE"] = qt_module
            os.environ["INPUT_METHOD"] = qt_module
            os.environ["SDL_IM_MODULE"] = qt_module
        if "xim" not in keep:
            os.environ["XMODIFIERS"] = f"@im={xim or qt_module}"
        if "gtk" not in keep:
            os.environ["GTK_IM_MODULE"] = gtk_module

    def _decide_keep() -> frozenset:
        """システム側が既に fcitx（fcitx5 の互換名 "fcitx"/"fcitx5"）を設定している場合、
        上書きせずにそのまま使える項目を判定する。

        - GTK / XMODIFIERS: fcitx系ならそのまま尊重して問題ない（GTKはABI安定、
          XIMはfcitx5が提供）。ただし GTK は fcitx5 の GTKモジュールが実在する場合のみ。
        - Qt: システムのfcitx5用ネイティブプラグインは、PySide6同梱のQt(6.11.1)と
          distroのQt6のバージョンが違うとロードできない(Qt_6_PRIVATE_API)。尊重して
          もロードできなければQt側のIMEが無効になるだけなので、QPluginLoaderで
          「実際にロードできる」ことを確認できた場合だけ尊重する。"""
        fcitx_names = ("fcitx", "fcitx5")
        keep = set()
        qt_sys = system_env["QT_IM_MODULE"] or ""
        if qt_sys in fcitx_names:
            ok, err = _native_fcitx_plugin_loadable()
            if ok:
                keep.add("qt")
                print(f"[IME] システムのQT_IM_MODULE={qt_sys}を尊重（ネイティブfcitx5プラグインはロード可能）", flush=True)
            else:
                print(
                    f"[IME] システムのQT_IM_MODULE={qt_sys}は尊重できません"
                    f"（PySide6同梱Qtではfcitx5用プラグインをロードできない）: {err[:160]}"
                    " → 同梱ibusプラグイン経由に切り替えます",
                    flush=True,
                )
        gtk_sys = system_env["GTK_IM_MODULE"] or ""
        if gtk_sys in fcitx_names and _gtk_immodule_exists("fcitx5"):
            keep.add("gtk")
            print(f"[IME] システムのGTK_IM_MODULE={gtk_sys}を尊重", flush=True)
        xm_sys = system_env["XMODIFIERS"] or ""
        if xm_sys.startswith(("@im=fcitx",)):
            keep.add("xim")
            print(f"[IME] システムのXMODIFIERS={xm_sys}を尊重", flush=True)
        return frozenset(keep)

    def _pick_gtk_module_for_fcitx5() -> str:
        """fcitx5 利用時の GTK_IM_MODULE（＝Electronサービスの日本語入力）。
        fcitx5のGTKモジュール(im-fcitx5.so)があれば、それを明示的に指定する
        （ibus不要で直接接続でき、GTKはABI安定のためQtのようなバージョン不一致も無い）。

        隔離環境での実測: GTK_IM_MODULE=ibus のまま ibus用GTKモジュールが無くても、
        fcitx5のGTKモジュールがあればGTKがロケール既定のモジュールへフォールバック
        して接続できる。ただしそれは暗黙のフォールバック頼みなので、明示指定して
        挙動を決定的にする。fcitx5/ibus どちらのGTKモジュールも無い場合は、
        どの値にしてもElectron側のIMEは接続されない（実測）。"""
        if _gtk_immodule_exists("fcitx5"):
            return "fcitx"
        if _gtk_immodule_exists("ibus"):
            return "ibus"
        print(
            "[IME] 注意: GTK用のfcitx5/ibusモジュールが見つかりません。Electronエンジンの"
            "サービスで日本語入力できない可能性があります。fcitx5-frontend-gtk3 を"
            "インストールしてください（例: sudo apt install fcitx5-frontend-gtk3）。",
            flush=True,
        )
        return "fcitx"

    fcitx5_running = (
        subprocess.run(["pgrep", "-x", "fcitx5"], capture_output=True).returncode == 0
    )
    ibus_running = (
        subprocess.run(["pgrep", "-x", "ibus-daemon"], capture_output=True).returncode == 0
    )

    ibus_bus_ok, ibus_bus_file = ibus_bus_alive()
    if fcitx5_running or ibus_running:
        for st in ibus_bus_status():
            if not st["exists"]:
                print(f"[IME] ibusバス: アドレスファイルなし（Qtが探す場所: {st['file']}）", flush=True)
            else:
                sock = {True: "接続OK", False: "接続NG", None: "不明"}[st["socket_ok"]]
                print(
                    f"[IME] ibusバス: {st['file']} pid={st['pid']}"
                    f"({'生存' if st['pid_alive'] else '死亡'}) socket={sock}",
                    flush=True,
                )

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
        gtk_mod = _pick_gtk_module_for_fcitx5()
        keep = _decide_keep()
        if "qt" in keep:
            # システムのfcitx設定をそのまま使う（ネイティブfcitx5プラグインがロード可能な環境）
            _apply_env(system_env["QT_IM_MODULE"], gtk_mod, xim="fcitx", keep=keep)
            return "fcitx5(system env kept, native)"
        if ibus_running or ibus_bus_ok:
            # Qt: 同梱ibusプラグイン → fcitx5のibusフロントエンド(またはibus-daemon)
            # XIM は ibus-daemon が居ればそのまま、居なければ fcitx5 のXIMを指す
            _apply_env("ibus", gtk_mod, xim=None if ibus_running else "fcitx", keep=keep)
            if ibus_running:
                backend = "fcitx5(via ibus)"
            else:
                backend = "fcitx5(via ibus frontend, no ibus-daemon)"
                print(f"[IME] ibus-daemon は無いが、fcitx5のibusフロントエンドが有効: {ibus_bus_file}", flush=True)
            print(f"[IME] Qt=ibus / GTK(Electron)={gtk_mod}", flush=True)
            return backend
        # ibus-daemon も、fcitx5のibusフロントエンドが作るアドレスファイルも無い
        # ＝ ibus経路では接続先が無い。fcitx5 のネイティブQtプラグインへ直接接続する。
        _apply_env("fcitx", gtk_mod, keep=keep)
        print(
            "[IME] 注意: ibusバスが見つからないため fcitx5 へ直接接続します。"
            "ネイティブプラグインがPySide6同梱Qtとバージョン不一致でロードできない環境では"
            "Qt側のIMEが有効になりません。その場合は fcitx5-configtool の「アドオン」で"
            "「IBus フロントエンド」を有効にしてください。",
            flush=True,
        )
        print(f"[IME] Qt=fcitx / GTK(Electron)={gtk_mod}", flush=True)
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


def setup_ime() -> str:
    """IMEバックエンドを自動検出して環境変数を設定する（詳細は _setup_ime_impl）。
    どの分岐で返っても、上書き後の値を必ず [IME-DEBUG] として出力する。"""
    backend = _setup_ime_impl()
    log_ime_env("setup_ime による上書き後")
    return backend


# ─────────────────────────────────────────────────────────
# 【デバッグ専用・調査完了後に削除】IME(fcitx5)不具合の切り分け用。
#
# 外部ターミナルへ切り替えて dbus-send を打つと、Ink Boss自身の
# 「フォーカスが外れたらElectronを隠す」仕組み(main.pyのフォーカス
# 監視)が働いてしまい、検証中のウィンドウの表示状態が変わってしまう
# （＝診断行為自体が症状に影響する）。ウィンドウ切り替えなしで
# 診断情報を取れるよう、Electron側でF12が押されたときにPythonの
# プロセス内からfcitx5へ直接問い合わせ、ログファイルに書き出す。
# ─────────────────────────────────────────────────────────
IME_DEBUG_LOG = Path.home() / ".config" / "ink-boss" / "ime-debug.log"


def dump_ime_debug_info(sid: str, active_element: str = "") -> None:
    """fcitx5のDebugInfo（dbus-send相当）と、その時点のIME関連環境変数、
    Webページ側の実際のフォーカス要素（document.activeElement）を
    IME_DEBUG_LOG に追記する。main.jsでF12が押されたとき、
    electron_bridge.ElectronEngine.on_ime_debug_requested 経由で呼ばれる。"""
    import datetime
    import os
    import subprocess as sp

    lines = [f"===== {datetime.datetime.now().isoformat()} sid={sid} ====="]
    lines.append(describe_ime_env())
    lines.append(f"document.activeElement: {active_element or '(取得できず)'}")

    try:
        # PyInstaller(--onedir)でパッケージされた実行ファイルはブートローダーが
        # LD_LIBRARY_PATHに同梱の_internalディレクトリ（古いバージョンの
        # libdbus-1.so.3等を含む）を追加してから起動する。この環境をそのまま
        # 子プロセスに継承させると、システムのdbus-sendが誤って同梱ライブラリを
        # ロードしようとして次のようなバージョン不一致エラーで失敗する:
        #   dbus-send: .../libdbus-1.so.3: version `LIBDBUS_PRIVATE_1.16.2' not found
        # （創作PCの実機検証で発見。Ink Boss本体の動作には影響しないため、
        # この診断用サブプロセス呼び出しに限定してLD_LIBRARY_PATHを取り除く。）
        debug_env = os.environ.copy()
        debug_env.pop("LD_LIBRARY_PATH", None)
        result = sp.run(
            [
                "dbus-send", "--session", "--print-reply",
                "--dest=org.fcitx.Fcitx5", "/controller",
                "org.fcitx.Fcitx.Controller1.DebugInfo",
            ],
            capture_output=True, text=True, timeout=5, env=debug_env,
        )
        out = result.stdout or result.stderr
        ic_lines = [ln.strip() for ln in out.splitlines() if "IC [" in ln]
        if ic_lines:
            lines.append("fcitx5 IC一覧:")
            lines.extend(f"  {ln}" for ln in ic_lines)
        else:
            lines.append(f"fcitx5 DebugInfo: IC行なし（生出力）: {out[:300]!r}")
    except Exception as e:
        lines.append(f"fcitx5 DebugInfo取得失敗: {e}")

    try:
        IME_DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(IME_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
        print(f"[IME-DEBUG] ログを書き出しました: {IME_DEBUG_LOG}", flush=True)
    except Exception as e:
        print(f"[IME-DEBUG] ログ書き出し失敗: {e}", flush=True)
