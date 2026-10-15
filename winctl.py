"""
winctl.py - ウィンドウ操作・プロセスツリー探索のOS差異吸収層
Ink Boss / Ink Inc.

これまで window.py / api.py / bridge.py / main.py / electron_bridge.py に
散らばっていた「OS依存のウィンドウ操作」を、ここ1か所に集約する。

  Linux(X11)  : xdotool / wmctrl / xprop と /proc を呼ぶ。中身は集約前の
                各ファイルのコードをそのまま移したもの（動作は変えない）。
                外部コマンドは必ず sysenv.get_clean_subprocess_env() 経由で
                呼ぶ（詳細は sysenv.py のdocstring）。
  Windows     : 【未実装】(2)の段階では入口だけ。各関数に TODO(win) を置いてあり、
                手順(4)でctypes(user32)による実装を入れる。未実装の間は
                「何もしない／取得できなかった(None・False・空集合)」を返すので、
                呼び出し側は None/False を必ず許容すること。
  その他(macOS等): 対象外。Windowsと同じ「未実装」扱い。

ウィンドウIDは呼び出し側との互換のため、これまでと同じ型を保つ:
  - 文字列で受け渡すID（bridge.set_win_id / get_win_id が保持する値）: str
  - アクティブ窓・自プロセス窓の判定に使う集合の要素: int
Windows実装では str(hwnd) / int(hwnd) をそれぞれ返す想定。

呼び出し側のルール:
  - OS固有コマンドを直接 subprocess で呼ばず、必ずこのモジュールを経由する。
  - 戻り値が None/False/空のときは「この環境では取れなかった」と解釈し、
    従来どおりのフォールバック動作（座標はpywebview内部値を使う等）に倒す。
"""

from __future__ import annotations

import os
import subprocess
import sys

from sysenv import get_clean_subprocess_env

IS_LINUX = sys.platform.startswith("linux")
IS_WINDOWS = sys.platform == "win32"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 内部ヘルパー（Linux / X11）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _parse_xy_shell(stdout: str) -> tuple[int | None, int | None]:
    """xdotool の --shell 出力（X=.. / Y=.. の行）から座標を取り出す。"""
    x: int | None = None
    y: int | None = None
    for line in stdout.splitlines():
        if line.startswith("X="):
            x = int(line.split("=")[1])
        elif line.startswith("Y="):
            y = int(line.split("=")[1])
    return x, y


def _list_windows_with_pid(timeout: float) -> list[tuple[str, int, str]] | None:
    """`wmctrl -lp` の各行を (ウィンドウID文字列, PID, 行全体) にして返す。
    wmctrlが使えない・失敗した場合は None。"""
    try:
        result = subprocess.run(
            ["wmctrl", "-lp"], capture_output=True, text=True,
            env=get_clean_subprocess_env(), timeout=timeout,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    rows: list[tuple[str, int, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 3:
            continue
        try:
            win_pid = int(parts[2])
        except ValueError:
            continue
        rows.append((parts[0], win_pid, line))
    return rows


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# プロセスツリー
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def descendant_pids(root_pid: int) -> set[int]:
    """root_pid自身と、その子孫プロセスのPID集合を返す。

    Electron(Chromium)はマルチプロセス構成のため、メインプロセスのPID単体では
    renderer/gpu-process/zygote/utility等の子プロセスと一致しない。プロセス
    ツリー全体を辿って初めて「自分たちのウィンドウ」を正しく判定できる。
    Linuxでは /proc を使う（サブプロセス起動なし）。"""
    if IS_LINUX:
        children_map: dict[int, list[int]] = {}
        try:
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                pid = int(entry)
                try:
                    with open(f"/proc/{pid}/stat", "r") as f:
                        stat = f.read()
                    after = stat.rsplit(")", 1)[-1].split()
                    ppid = int(after[1])
                except (OSError, IndexError, ValueError):
                    continue
                children_map.setdefault(ppid, []).append(pid)
        except OSError:
            return {root_pid}

        result = {root_pid}
        stack = [root_pid]
        while stack:
            p = stack.pop()
            for c in children_map.get(p, []):
                if c not in result:
                    result.add(c)
                    stack.append(c)
        return result

    # TODO(win): CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS) で親子関係を辿る。
    return {root_pid}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ウィンドウの特定
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def find_own_window_id(title_substr: str) -> str | None:
    """タイトルに title_substr を含み、かつ自プロセス(os.getpid())が所有する
    ウィンドウのIDを返す。見つからない・取得不能なら None。

    タイトル一致だけで判定すると、(1) Ink Bossを複数同時起動した場合に別
    インスタンスの窓を、(2) 無関係な外部アプリの窓（タイトルにたまたま同じ文字列を
    含むブラウザ等）を、誤って「自分の窓」として掴む実害があった（実機確認済み）。
    そのためタイトル一致に加えてPID一致も要求する。自プロセスはサンドボックス
    されていないので _NET_WM_PID は常に正しいホスト側PIDを報告する。"""
    if IS_LINUX:
        rows = _list_windows_with_pid(timeout=2.0)
        if rows is None:
            return None
        my_pid = os.getpid()
        for win_id, win_pid, line in rows:
            if win_pid == my_pid and title_substr in line:
                return win_id
        return None

    # TODO(win): EnumWindows + GetWindowThreadProcessId + GetWindowTextW。
    #            QtのwinId()を使えるならそちらの方が確実（タイトル検索不要）。
    return None


def get_own_window_ids(root_pids: set[int]) -> set[int]:
    """root_pids（自分たちのQt本体・Electronヘルパー等のPID）自身と、その子孫プロセス
    全てが所有するウィンドウIDの集合を返す。取得不能なら空集合。

    「今アクティブな窓が自分たちのものか」を、PIDではなくウィンドウIDの比較で
    判定するための材料（Flatpak等でサンドボックスされた外部アプリはPIDを
    コンテナ内の見かけの値で報告するため、PIDでは「外部アプリ」を判別できない）。"""
    all_descendants: set[int] = set()
    for pid in root_pids:
        all_descendants |= descendant_pids(pid)

    if IS_LINUX:
        rows = _list_windows_with_pid(timeout=0.3)
        if rows is None:
            return set()
        own_ids: set[int] = set()
        for win_id, win_pid, _line in rows:
            try:
                win_id_int = int(win_id, 16)
            except ValueError:
                continue
            if win_pid in all_descendants:
                own_ids.add(win_id_int)
        return own_ids

    # TODO(win): EnumWindows で全トップレベル窓を列挙し、所有PIDが all_descendants に
    #            含まれるHWNDを集める。
    return set()


def get_active_window_id() -> int | None:
    """現在OSがアクティブとみなしているウィンドウのID。判定不能なら None。

    以前はPIDを取得して比較していたが、サンドボックスされたアプリのPIDは使えない
    （get_own_window_ids参照）。ウィンドウID自体はサンドボックス下でも正しく
    採番されるため、IDの比較に切り替えている。
    Qtメインスレッドをブロックしないよう、短いタイムアウトで打ち切る。"""
    if IS_LINUX:
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True, text=True, timeout=0.3,
                env=get_clean_subprocess_env(),
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
        except Exception:
            pass
        return None

    # TODO(win): GetForegroundWindow()
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 座標の取得・移動
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_window_position(win_id: str, timeout: float | None = None) -> tuple[int, int] | None:
    """ウィンドウ左上の画面絶対座標 (x, y)。取得できなければ None。"""
    if IS_LINUX:
        try:
            r = subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", win_id],
                capture_output=True, text=True, timeout=timeout,
                env=get_clean_subprocess_env(),
            )
            x, y = _parse_xy_shell(r.stdout)
        except Exception:
            return None
        if x is None or y is None:
            return None
        return x, y

    # TODO(win): GetWindowRect(hwnd)。DPIスケーリング時はPer-Monitor DPI Aware前提で
    #            Qt/pywebview/Electronの座標系（物理px or 論理px）を揃えること。
    return None


def get_mouse_position() -> tuple[int, int] | None:
    """マウスカーソルの画面絶対座標 (x, y)。取得できなければ None。"""
    if IS_LINUX:
        try:
            r = subprocess.run(
                ["xdotool", "getmouselocation", "--shell"],
                capture_output=True, text=True,
                env=get_clean_subprocess_env(),
            )
            x, y = _parse_xy_shell(r.stdout)
        except Exception:
            return None
        if x is None or y is None:
            return None
        return x, y

    # TODO(win): GetCursorPos
    return None


def move_window(win_id: str, x: int, y: int) -> bool:
    """ウィンドウを画面絶対座標 (x, y) へ移動する（サイズは変えない）。成功したら True。"""
    if IS_LINUX:
        try:
            r = subprocess.run(
                ["wmctrl", "-ir", win_id, "-e", f"0,{x},{y},-1,-1"],
                check=False, env=get_clean_subprocess_env(),
            )
        except Exception:
            return False
        return r.returncode == 0

    # TODO(win): SetWindowPos(hwnd, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
    return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 窓の状態・フォーカス・装飾
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def toggle_maximize(win_id: str) -> bool:
    """最大化／元に戻すを切り替える。成功したら True（Falseなら呼び出し側が
    pywebviewのtoggle_fullscreen等へフォールバックする）。

    toggle_fullscreen() だと画面全体を覆って上部パネルや下部ドックまで隠れるため、
    ウィンドウマネージャの最大化(_NET_WM_STATE_MAXIMIZED)で作業領域に収める。"""
    if IS_LINUX:
        try:
            r = subprocess.run(
                ["wmctrl", "-ir", win_id, "-b",
                 "toggle,maximized_vert,maximized_horz"],
                capture_output=True, timeout=2,
                env=get_clean_subprocess_env(),
            )
            return r.returncode == 0
        except Exception as e:
            print(f"[toggle_maximize] wmctrl: {e}", flush=True)
            return False

    # TODO(win): IsZoomed(hwnd) を見て ShowWindow(SW_MAXIMIZE / SW_RESTORE)
    return False


def activate_window(win_id: str) -> None:
    """ウィンドウへ（キーボード）フォーカスを強制的に移す。"""
    if IS_LINUX:
        try:
            subprocess.run(
                ["wmctrl", "-ia", win_id],
                check=False, capture_output=True,
                env=get_clean_subprocess_env(),
            )
        except Exception:
            pass
        return

    # TODO(win): SetForegroundWindow（フォーカス奪取制限があるため
    #            AttachThreadInput等の迂回が要る可能性あり）
    return


def ime_enable() -> None:
    """窓へフォーカスを移した直後に、IMEを有効化させる。
    Linuxはfcitx5向け（ibus環境ではコマンドが無いだけで何も起きない）。
    WindowsはOS標準のIMEがフォーカスに追従するため基本的に不要。"""
    if IS_LINUX:
        try:
            subprocess.run(
                ["fcitx5-remote", "-o"],
                check=False, capture_output=True,
                env=get_clean_subprocess_env(),
            )
        except Exception:
            pass
        return
    return


def remove_decorations(win_id: str) -> None:
    """OSのタイトルバー・枠を消す（pywebviewのframeless=Trueと二重でも害は少ない）。"""
    if IS_LINUX:
        try:
            subprocess.run(
                [
                    "xprop", "-id", win_id,
                    "-f", "_MOTIF_WM_HINTS", "32c",
                    "-set", "_MOTIF_WM_HINTS", "0x2, 0x0, 0x0, 0x0, 0x0",
                ],
                check=False, env=get_clean_subprocess_env(),
            )
        except Exception:
            pass
        return

    # TODO(win): 基本は pywebview の frameless=True で足りる見込み。足りなければ
    #            SetWindowLongPtr で WS_CAPTION / WS_THICKFRAME を調整。
    return
