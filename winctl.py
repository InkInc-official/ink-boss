"""
winctl.py - ウィンドウ操作・プロセスツリー探索のOS差異吸収層
Ink Boss / Ink Inc.

これまで window.py / api.py / bridge.py / main.py / electron_bridge.py に
散らばっていた「OS依存のウィンドウ操作」を、ここ1か所に集約する。

  Linux(X11)  : xdotool / wmctrl / xprop と /proc を呼ぶ。中身は集約前の
                各ファイルのコードをそのまま移したもの（動作は変えない）。
                外部コマンドは必ず sysenv.get_clean_subprocess_env() 経由で
                呼ぶ（詳細は sysenv.py のdocstring）。
  Windows     : ctypes(user32 / kernel32)で実装。追加の依存パッケージは不要。
                ウィンドウIDは HWND を str(hwnd)(文字列ID) / int(hwnd)(集合・
                アクティブ窓) で返す。座標は物理ピクセル（QtはPer-Monitor DPI Aware
                で動くため、GetWindowRect/GetCursorPos/SetWindowPosが同じ座標系で
                揃う。ドラッグ移動のような「差分」の計算はそのまま成立する）。
                取得できない時は None・False・空集合を返すので、呼び出し側は
                None/False を必ず許容すること。
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
# 内部ヘルパー（Windows / ctypes）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_win_api = None


def _w():
    """user32/kernel32 を型付きで初期化して返す（初回のみ。Windows以外では呼ばない）。
    HWND/HANDLEは64bitでは64bit幅。argtypes/restypeを指定しないとctypesが
    32bit intとして扱い、ハンドルが壊れる。"""
    global _win_api
    if _win_api is not None:
        return _win_api
    import ctypes
    from ctypes import wintypes as wt

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
    user32.EnumWindows.restype = wt.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    user32.GetWindowThreadProcessId.restype = wt.DWORD
    user32.GetWindowTextLengthW.argtypes = [wt.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = [wt.HWND]
    user32.IsWindowVisible.restype = wt.BOOL
    user32.IsWindow.argtypes = [wt.HWND]
    user32.IsWindow.restype = wt.BOOL
    user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    user32.GetWindowRect.restype = wt.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
    user32.GetCursorPos.restype = wt.BOOL
    user32.SetWindowPos.argtypes = [
        wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wt.UINT,
    ]
    user32.SetWindowPos.restype = wt.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wt.HWND
    user32.IsZoomed.argtypes = [wt.HWND]
    user32.IsZoomed.restype = wt.BOOL
    user32.IsIconic.argtypes = [wt.HWND]
    user32.IsIconic.restype = wt.BOOL
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wt.BOOL
    user32.SetForegroundWindow.argtypes = [wt.HWND]
    user32.SetForegroundWindow.restype = wt.BOOL
    user32.BringWindowToTop.argtypes = [wt.HWND]
    user32.BringWindowToTop.restype = wt.BOOL
    user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
    user32.AttachThreadInput.restype = wt.BOOL
    user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wt.DWORD

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wt.DWORD),
            ("cntUsage", wt.DWORD),
            ("th32ProcessID", wt.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wt.DWORD),
            ("cntThreads", wt.DWORD),
            ("th32ParentProcessID", wt.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wt.DWORD),
            ("szExeFile", wt.WCHAR * 260),
        ]

    kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wt.BOOL
    kernel32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wt.BOOL
    kernel32.CloseHandle.argtypes = [wt.HANDLE]
    kernel32.CloseHandle.restype = wt.BOOL

    class _Api:
        pass

    api = _Api()
    api.ctypes = ctypes
    api.wt = wt
    api.user32 = user32
    api.kernel32 = kernel32
    api.WNDENUMPROC = WNDENUMPROC
    api.PROCESSENTRY32W = PROCESSENTRY32W
    _win_api = api
    return api


def _win_enum_windows() -> list[tuple[int, int]]:
    """全トップレベル窓を (hwnd, 所有PID) のリストで返す。"""
    a = _w()
    out: list[tuple[int, int]] = []

    def _cb(hwnd, _lparam):
        pid = a.wt.DWORD(0)
        a.user32.GetWindowThreadProcessId(hwnd, a.ctypes.byref(pid))
        out.append((int(hwnd), int(pid.value)))
        return True

    a.user32.EnumWindows(a.WNDENUMPROC(_cb), 0)
    return out


def _win_title(hwnd: int) -> str:
    a = _w()
    n = a.user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = a.ctypes.create_unicode_buffer(n + 1)
    a.user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _win_hwnd(win_id) -> int | None:
    """呼び出し側のID（str/int）→ HWND(int)。不正・存在しない窓なら None。"""
    try:
        hwnd = int(win_id)
    except (TypeError, ValueError):
        return None
    if not hwnd or not _w().user32.IsWindow(hwnd):
        return None
    return hwnd


# SetWindowPos / ShowWindow の定数
_SWP_NOSIZE = 0x0001
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_NOMOVE = 0x0002
_SWP_FRAMECHANGED = 0x0020
_GWL_STYLE = -16
_WS_MAXIMIZEBOX = 0x00010000
_WS_MINIMIZEBOX = 0x00020000
_WS_SYSMENU = 0x00080000
_SW_RESTORE = 9
_SW_MAXIMIZE = 3
_SW_MINIMIZE = 6


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

    if IS_WINDOWS:
        try:
            a = _w()
            TH32CS_SNAPPROCESS = 0x00000002
            snap = a.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if not snap or int(snap) == -1:
                return {root_pid}
            children_map: dict[int, list[int]] = {}
            try:
                entry = a.PROCESSENTRY32W()
                entry.dwSize = a.ctypes.sizeof(a.PROCESSENTRY32W)
                ok = a.kernel32.Process32FirstW(snap, a.ctypes.byref(entry))
                while ok:
                    children_map.setdefault(
                        int(entry.th32ParentProcessID), []
                    ).append(int(entry.th32ProcessID))
                    ok = a.kernel32.Process32NextW(snap, a.ctypes.byref(entry))
            finally:
                a.kernel32.CloseHandle(snap)
        except Exception:
            return {root_pid}
        # PIDは再利用される（親が死んだ後に別プロセスが同じPIDを得る）ので、
        # 自分自身を再訪しないよう visited で打ち切る。
        result = {root_pid}
        stack = [root_pid]
        while stack:
            p = stack.pop()
            for c in children_map.get(p, []):
                if c not in result:
                    result.add(c)
                    stack.append(c)
        return result

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

    if IS_WINDOWS:
        try:
            my_pid = os.getpid()
            a = _w()
            for hwnd, pid in _win_enum_windows():
                if pid != my_pid or not a.user32.IsWindowVisible(hwnd):
                    continue
                if title_substr in _win_title(hwnd):
                    return str(hwnd)
        except Exception:
            pass
        return None
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

    if IS_WINDOWS:
        try:
            return {
                hwnd for hwnd, pid in _win_enum_windows()
                if pid in all_descendants
            }
        except Exception:
            return set()
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

    if IS_WINDOWS:
        try:
            hwnd = _w().user32.GetForegroundWindow()
            return int(hwnd) if hwnd else None
        except Exception:
            return None
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

    if IS_WINDOWS:
        try:
            hwnd = _win_hwnd(win_id)
            if hwnd is None:
                return None
            a = _w()
            rect = a.wt.RECT()
            if not a.user32.GetWindowRect(hwnd, a.ctypes.byref(rect)):
                return None
            return int(rect.left), int(rect.top)
        except Exception:
            return None
    return None


def get_window_rect(win_id: str) -> tuple[int, int, int, int] | None:
    """ウィンドウ全体の画面絶対座標 (x, y, 幅, 高さ)。Windowsのみ実装。
    最小化中・取得不能・非Windowsでは None（呼び出し側は従来の取得方法に
    フォールバックする）。Electronオーバーレイを「Ink Bossの実際の大きさ」に
    ぴったり合わせるための、唯一の基準値として使う。"""
    if IS_WINDOWS:
        try:
            hwnd = _win_hwnd(win_id)
            if hwnd is None:
                return None
            a = _w()
            if a.user32.IsIconic(hwnd):
                return None
            rect = a.wt.RECT()
            if not a.user32.GetWindowRect(hwnd, a.ctypes.byref(rect)):
                return None
            w = int(rect.right - rect.left)
            h = int(rect.bottom - rect.top)
            if w <= 1 or h <= 1:
                return None
            return int(rect.left), int(rect.top), w, h
        except Exception:
            return None
    return None


def set_window_owner(child_hwnd, owner_win_id) -> bool:
    """child_hwnd のトップレベル窓の「オーナー窓」を owner_win_id に設定する
    （Windowsのみ）。オーナー付きの窓はOSが次を保証する:
      ・常にオーナーの手前に表示される（他アプリの手前にまでは出ない）
      ・オーナーが最小化されると一緒に隠れ、復帰すると一緒に戻る
      ・オーナーが最大化・移動・前面化されても z順の関係が保たれる
    Electronのオーバーレイを「Ink Bossに紐づける」ための仕組み。
    （GWLP_HWNDPARENT=-8 は、トップレベル窓ではオーナーを意味する）"""
    if not IS_WINDOWS:
        return False
    try:
        child = int(child_hwnd)
        owner = _win_hwnd(owner_win_id)
        if not child or owner is None or not _w().user32.IsWindow(child):
            return False
        u = _w().user32
        u.SetWindowLongPtrW(child, -8, owner)
        return int(u.GetWindowLongPtrW(child, -8)) == owner
    except Exception:
        return False


def get_window_pid(win_id) -> int | None:
    """ウィンドウを所有するプロセスのPID。Windowsのみ実装（他は None）。"""
    if IS_WINDOWS:
        try:
            hwnd = _win_hwnd(win_id)
            if hwnd is None:
                return None
            a = _w()
            pid = a.wt.DWORD(0)
            a.user32.GetWindowThreadProcessId(hwnd, a.ctypes.byref(pid))
            return int(pid.value) or None
        except Exception:
            return None
    return None


def is_minimized(win_id: str) -> bool | None:
    """最小化中なら True。判定不能・非Windowsなら None。"""
    if IS_WINDOWS:
        try:
            hwnd = _win_hwnd(win_id)
            if hwnd is None:
                return None
            return bool(_w().user32.IsIconic(hwnd))
        except Exception:
            return None
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

    if IS_WINDOWS:
        try:
            a = _w()
            pt = a.wt.POINT()
            if not a.user32.GetCursorPos(a.ctypes.byref(pt)):
                return None
            return int(pt.x), int(pt.y)
        except Exception:
            return None
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

    if IS_WINDOWS:
        try:
            hwnd = _win_hwnd(win_id)
            if hwnd is None:
                return False
            return bool(_w().user32.SetWindowPos(
                hwnd, None, int(x), int(y), 0, 0,
                _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE,
            ))
        except Exception:
            return False
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

    if IS_WINDOWS:
        try:
            hwnd = _win_hwnd(win_id)
            if hwnd is None:
                return False
            u = _w().user32
            u.ShowWindow(hwnd, _SW_RESTORE if u.IsZoomed(hwnd) else _SW_MAXIMIZE)
            return True
        except Exception as e:
            print(f"[toggle_maximize] win32: {e}", flush=True)
            return False
    return False


def minimize_window(win_id: str) -> bool:
    """最小化する。成功したら True（Falseなら呼び出し側がpywebviewのminimize()へ
    フォールバックする）。Linuxは従来どおりpywebview任せ（常にFalse）。

    Windowsでは toggle_maximize がネイティブ(ShowWindow)で最大化するため、
    最小化だけQt(setWindowState)で行うとQtの内部状態とOSの状態が食い違い、
    「最大化→最小化」の後に復帰できなくなる。両方ネイティブに揃える。"""
    if IS_WINDOWS:
        try:
            hwnd = _win_hwnd(win_id)
            if hwnd is None:
                return False
            _w().user32.ShowWindow(hwnd, _SW_MINIMIZE)
            return True
        except Exception:
            return False
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

    if IS_WINDOWS:
        try:
            hwnd = _win_hwnd(win_id)
            if hwnd is None:
                return
            a = _w()
            u = a.user32
            if u.IsIconic(hwnd):
                u.ShowWindow(hwnd, _SW_RESTORE)
            if u.SetForegroundWindow(hwnd):
                return
            # フォーカス奪取制限で失敗した場合: 現在の前面窓のスレッドに
            # 入力キューを一時的に接続して前面化する（標準的な迂回策）。
            fg = u.GetForegroundWindow()
            if not fg:
                return
            fg_tid = u.GetWindowThreadProcessId(fg, None)
            my_tid = a.kernel32.GetCurrentThreadId()
            if fg_tid and fg_tid != my_tid:
                u.AttachThreadInput(my_tid, fg_tid, True)
                try:
                    u.BringWindowToTop(hwnd)
                    u.SetForegroundWindow(hwnd)
                finally:
                    u.AttachThreadInput(my_tid, fg_tid, False)
        except Exception:
            pass
        return
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

    if IS_WINDOWS:
        # 枠(タイトルバー)自体は pywebview の frameless=True で既に消えている。
        # ただしQtのframeless窓は WS_MINIMIZEBOX / WS_SYSMENU を持たない
        # ポップアップ窓になり、最小化するとタスクバーのボタンを押しても
        # 復帰できなくなる（実機で確認）。見た目は変えずにこれらの属性だけ足す
        # （HWNDは変わらないのでウィンドウIDも維持される）。
        try:
            hwnd = _win_hwnd(win_id)
            if hwnd is None:
                return
            u = _w().user32
            before = int(u.GetWindowLongPtrW(hwnd, _GWL_STYLE))
            want = before | _WS_MINIMIZEBOX | _WS_MAXIMIZEBOX | _WS_SYSMENU
            if want != before:
                u.SetWindowLongPtrW(hwnd, _GWL_STYLE, want)
                u.SetWindowPos(
                    hwnd, None, 0, 0, 0, 0,
                    _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER
                    | _SWP_NOACTIVATE | _SWP_FRAMECHANGED,
                )
            after = int(u.GetWindowLongPtrW(hwnd, _GWL_STYLE))
            print(f"[winctl] style {before & 0xFFFFFFFF:#010x} -> {after & 0xFFFFFFFF:#010x}", flush=True)
        except Exception as e:
            print(f"[winctl] remove_decorations: {e}", flush=True)
        return
    return


def debug_window_state(win_id: str) -> str:
    """【診断用】窓の状態を1行の文字列にして返す（Windowsのみ。環境変数
    INK_BOSS_WINDEBUG=1 のときだけwindow.pyから定期的に呼ばれる）。
    最小化から復帰できない等の不具合で「窓が本当に表示されているか」を調べる。"""
    if not IS_WINDOWS:
        return ""
    try:
        a = _w()
        ct, wt = a.ctypes, a.wt
        u = a.user32
        hwnd = _win_hwnd(win_id)
        if hwnd is None:
            return f"hwnd={win_id} (存在しない)"
        rect = wt.RECT()
        u.GetWindowRect(hwnd, ct.byref(rect))
        style = int(u.GetWindowLongPtrW(hwnd, _GWL_STYLE)) & 0xFFFFFFFF
        ex = int(u.GetWindowLongPtrW(hwnd, -20)) & 0xFFFFFFFF
        cloaked = wt.DWORD(0)
        try:
            dwm = ct.WinDLL("dwmapi")
            dwm.DwmGetWindowAttribute(
                wt.HWND(hwnd), wt.DWORD(14), ct.byref(cloaked), wt.DWORD(4))
        except Exception:
            pass
        fg = u.GetForegroundWindow()
        return (
            f"hwnd={hwnd} rect=({rect.left},{rect.top},{rect.right},{rect.bottom}) "
            f"size={rect.right - rect.left}x{rect.bottom - rect.top} "
            f"visible={bool(u.IsWindowVisible(hwnd))} iconic={bool(u.IsIconic(hwnd))} "
            f"zoomed={bool(u.IsZoomed(hwnd))} cloaked={cloaked.value} "
            f"style={style:#010x} exstyle={ex:#010x} foreground={'self' if fg == hwnd else int(fg or 0)}"
        )
    except Exception as e:
        return f"debug error: {e}"
