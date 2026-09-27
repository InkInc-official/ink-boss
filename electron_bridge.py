"""
electron_bridge.py — Electron helper client (B1 follow overlay)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

def _resolve_base_dir() -> Path:
    """electron-engine/ を探す基準ディレクトリ。

    - 開発時（python3 main.py で直接実行）: このファイル自身の場所。
    - PyInstallerでパッケージ化された実行ファイルから起動時
      （--onedir。sys.frozen が真になる）: 実行ファイル自身の
      ディレクトリ。electron-engine/ はPyInstallerのdatasには含めず
      （270MB超あり、展開・アーカイブのコストが無駄に大きいため）、
      パッケージ側で実行ファイルと同じ階層に直接コピーする設計
      なので、sys._MEIPASS ではなく sys.executable を基準にする。

    OS固有のパス（/usr/lib/ink-boss 等）はここに一切書かない。
    実行ファイルの場所からの相対解決のみに留めることで、将来
    Windows版をPyInstallerでビルドする際も同じロジックがそのまま
    使える（Windows対応の実装自体は別途必要だが、このパス解決は
    そのままで良いはず）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ENGINE_DIR = _resolve_base_dir() / "electron-engine"
READY_PREFIX = "INK_ELECTRON_READY port="
ADD_SERVICE_PREFIX = "INK_ELECTRON_ADD_SERVICE "
START_TIMEOUT_S = 25.0


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = 5.0) -> dict:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _electron_looks_installed(bin_path: Path) -> bool:
    if not bin_path.exists():
        return False
    pkg_dir = bin_path.parent.parent / "electron"
    dist = pkg_dir / "dist"
    if dist.is_dir():
        for name in ("electron", "electron.exe"):
            if (dist / name).exists():
                return True
        try:
            return any(dist.iterdir())
        except OSError:
            return False
    return bin_path.is_file() and os.access(bin_path, os.X_OK)


def resolve_electron_binary() -> str | None:
    candidates = [
        ENGINE_DIR / "node_modules" / ".bin" / "electron",
    ]
    which = shutil.which("electron")
    if which:
        candidates.append(Path(which))
    candidates.append(
        Path.home() / "Applications" / "largs-hub-0.1.30" / "node_modules" / ".bin" / "electron"
    )
    for c in candidates:
        if _electron_looks_installed(c):
            return str(c)
    return None


def _read_cmdline(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return ""


def _read_ppid(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            stat = f.read()
        after = stat.rsplit(")", 1)[-1].split()
        return int(after[1])
    except (OSError, IndexError, ValueError):
        return None


def _descendant_pids(root_pid: int) -> set[int]:
    """root_pid自身とその子孫プロセスのPID集合（main.py の同名関数と同じ考え方）。"""
    children_map: dict[int, list[int]] = {}
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            ppid = _read_ppid(int(entry))
            if ppid is not None:
                children_map.setdefault(ppid, []).append(int(entry))
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


def cleanup_orphaned_electron_processes() -> None:
    """前回の異常終了（Qt側クラッシュ・SIGKILL・ハードウォッチドッグの
    os._exit等）でElectronヘルパーの終了処理が走らなかった場合、
    electron-engineのメインプロセス（と、その配下のrenderer/gpu-process
    等）が孤児プロセスとして残り続けることがある。renderer が長時間
    残存するとGPUメモリを消費し続け、後続のセッションで描画不良
    （画面が真っ黒になる等）の一因になりうる。

    新しいElectronヘルパーを起動する前に、このengine-engine/main.js を
    起動コマンドに持つプロセスを探し、その親プロセスが既に存在しない
    （＝init/systemdに再親化された孤児）ものだけを対象に、プロセス
    ツリーごと終了させる。まだ生きている親を持つプロセス（＝今まさに
    動いている別のInk Bossインスタンス）は誤って巻き込まないよう、
    対象から除外する。"""
    marker = str(ENGINE_DIR / "main.js")
    try:
        pids = [int(e) for e in os.listdir("/proc") if e.isdigit()]
    except OSError:
        return

    orphan_roots: list[int] = []
    for pid in pids:
        cmdline = _read_cmdline(pid)
        if marker not in cmdline or "--type=" in cmdline:
            continue  # 子プロセス（renderer/gpu-process等）はメインプロセス経由でまとめて処理する
        ppid = _read_ppid(pid)
        # ppid==1（init/systemdへの再親化）は「元の親がもう存在しない」ことの
        # 確実な印。ここをうっかり「親が生きている」扱いにすると、実際には
        # 孤児化したプロセスを一生見逃してしまう（実機で確認済みのバグ）。
        parent_alive = ppid is not None and ppid not in (0, 1) and os.path.exists(f"/proc/{ppid}")
        if parent_alive:
            continue  # 生きている親を持つ＝別の現行インスタンス。触らない
        orphan_roots.append(pid)

    if not orphan_roots:
        return

    targets: set[int] = set()
    for root in orphan_roots:
        targets |= _descendant_pids(root)

    print(f"[ElectronEngine] cleanup: found orphaned electron-engine process tree {sorted(targets)}", flush=True)
    import signal
    import time as _time

    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception as e:
            print(f"[ElectronEngine] cleanup: SIGTERM {pid} failed: {e}", flush=True)

    deadline = _time.time() + 3.0
    while _time.time() < deadline:
        if not any(os.path.exists(f"/proc/{pid}") for pid in targets):
            break
        _time.sleep(0.2)

    for pid in targets:
        if os.path.exists(f"/proc/{pid}"):
            try:
                os.kill(pid, signal.SIGKILL)
                print(f"[ElectronEngine] cleanup: SIGKILL {pid} (did not exit on SIGTERM)", flush=True)
            except ProcessLookupError:
                pass
            except Exception as e:
                print(f"[ElectronEngine] cleanup: SIGKILL {pid} failed: {e}", flush=True)


class ElectronEngine:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._port: int | None = None
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._failed = False
        self._stderr_tail: list[str] = []
        self.active_sid: str | None = None
        # active_sid は hide_all() 等で None にクリアされる（「今どのsidが
        # 対象か」の意味）ため、「今まさにウィンドウが表示されているか」を
        # 別途持つ。applicationStateChanged からの重複 show() 抑止に使う。
        self.is_shown: bool = False
        # ページ内右クリック「Ink Bossに追加」用。main.js がstdoutに
        # INK_ELECTRON_ADD_SERVICE <url> を出力したときに呼ばれる
        # （バックグラウンドスレッドから呼ばれるため、呼び出し側で
        # Qtメインスレッドへの受け渡しを行うこと）。
        self.on_add_service_requested: Callable[[str], None] | None = None

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    def is_available(self) -> bool:
        if self._failed or self._port is None:
            return False
        if self._proc is not None and self._proc.poll() is not None:
            return False
        return True

    def start(self) -> bool:
        with self._lock:
            if self.is_available():
                return True
            try:
                cleanup_orphaned_electron_processes()
            except Exception as e:
                print(f"[ElectronEngine] cleanup skipped (error): {e}", flush=True)
            binary = resolve_electron_binary()
            if not binary:
                print(
                    "[ElectronEngine] electron not found — "
                    "cd electron-engine && npm install",
                    flush=True,
                )
                self._failed = True
                return False
            if not (ENGINE_DIR / "main.js").exists():
                print(f"[ElectronEngine] missing main.js in {ENGINE_DIR}", flush=True)
                self._failed = True
                return False

            env = os.environ.copy()
            env["INK_ELECTRON_PORT"] = "0"
            try:
                from ime import log_ime_env
                log_ime_env("Electron子プロセスへ渡す環境変数", env)
            except Exception:
                pass
            cmd = [binary, str(ENGINE_DIR / "main.js")]
            if sys.platform.startswith("linux"):
                cmd = [binary, "--no-sandbox", str(ENGINE_DIR / "main.js")]

            print(f"[ElectronEngine] starting: {' '.join(cmd)}", flush=True)
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=str(ENGINE_DIR),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
            except Exception as e:
                print(f"[ElectronEngine] spawn failed: {e}", flush=True)
                self._failed = True
                return False

            threading.Thread(target=self._read_stdout, daemon=True).start()
            threading.Thread(target=self._read_stderr, daemon=True).start()

            if not self._ready.wait(timeout=START_TIMEOUT_S) or self._port is None:
                print(
                    f"[ElectronEngine] ready timeout. stderr={self._stderr_tail[-6:]}",
                    flush=True,
                )
                self._safe_kill()
                self._failed = True
                return False

            print(f"[ElectronEngine] ready 127.0.0.1:{self._port}", flush=True)
            return True

    def _read_stdout(self) -> None:
        assert self._proc and self._proc.stdout
        try:
            for line in self._proc.stdout:
                line = line.rstrip("\n")
                if line.startswith(READY_PREFIX):
                    try:
                        self._port = int(line[len(READY_PREFIX) :].strip())
                        self._ready.set()
                    except ValueError:
                        pass
                elif line.startswith(ADD_SERVICE_PREFIX):
                    url = line[len(ADD_SERVICE_PREFIX) :].strip()
                    if url and self.on_add_service_requested:
                        try:
                            self.on_add_service_requested(url)
                        except Exception:
                            pass
                elif line:
                    print(f"[electron-engine] {line}", flush=True)
        except Exception:
            pass

    def _read_stderr(self) -> None:
        assert self._proc and self._proc.stderr
        try:
            for line in self._proc.stderr:
                line = line.rstrip("\n")
                self._stderr_tail.append(line)
                if len(self._stderr_tail) > 40:
                    self._stderr_tail = self._stderr_tail[-40:]
                low = line.lower()
                if any(k in low for k in ("error", "fail", "ready", "listening", "created", "shutdown", "quit", "crash", "recover")):
                    print(f"[electron-engine:err] {line}", flush=True)
        except Exception:
            pass

    def _safe_kill(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        except Exception:
            pass
        self._proc = None
        self._port = None

    def shutdown(self, timeout: float = 3.0) -> None:
        """
        Electron ヘルパーを終了する。HTTP /shutdown が返らなくても
        timeout 秒で強制 kill し、呼び出し側をブロックし続けない。
        二重呼び出しは即 return。
        """
        print(f"[Close] electron shutdown start (timeout={timeout})", flush=True)
        with self._lock:
            if self._proc is None and self._port is None:
                print("[Close] electron already shut down", flush=True)
                return
            proc = self._proc
            port = self._port
            available = (
                not self._failed
                and port is not None
                and proc is not None
                and proc.poll() is None
            )

            if available:
                # HTTP は短タイムアウト。ハングしてもここで止まる時間を制限する
                try:
                    print("[Close] electron POST /shutdown …", flush=True)
                    _http_json(
                        "POST",
                        f"http://127.0.0.1:{port}/shutdown",
                        {},
                        timeout=min(1.5, timeout),
                    )
                    print("[Close] electron shutdown HTTP ok", flush=True)
                except Exception as e:
                    print(f"[Close] electron shutdown HTTP failed/timeout: {e}", flush=True)

                # プロセス終了待ち（残り時間）
                if proc is not None:
                    try:
                        wait_s = max(0.5, timeout - 1.5)
                        print(f"[Close] electron wait(pid={proc.pid}, {wait_s}s) …", flush=True)
                        proc.wait(timeout=wait_s)
                        print("[Close] electron process exited", flush=True)
                    except subprocess.TimeoutExpired:
                        print("[Close] electron wait timeout → terminate/kill", flush=True)
                        try:
                            proc.terminate()
                            try:
                                proc.wait(timeout=1.0)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                                proc.wait(timeout=1.0)
                        except Exception as e:
                            print(f"[Close] electron kill error: {e}", flush=True)
                    except Exception as e:
                        print(f"[Close] electron wait error: {e}", flush=True)
            else:
                print("[Close] electron not available — safe_kill", flush=True)
                self._safe_kill()

            self._port = None
            self._proc = None
            self.active_sid = None
            self.is_shown = False
            print("[Close] electron shutdown done", flush=True)

    def _base(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def _post(self, path: str, body: dict, timeout: float = 5.0) -> dict:
        if not self.is_available():
            return {"ok": False, "error": "unavailable"}
        try:
            return _http_json("POST", self._base() + path, body, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"[ElectronEngine] POST {path} failed: {e}", flush=True)
            return {"ok": False, "error": str(e)}

    def _get(self, path: str, timeout: float = 3.0) -> dict:
        if not self.is_available():
            return {"ok": False, "error": "unavailable"}
        try:
            return _http_json("GET", self._base() + path, None, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return {"ok": False, "error": str(e)}

    def create(self, sid: str, url: str, muted: bool = False, load_now: bool = False) -> dict:
        return self._post("/create", {"sid": sid, "url": url, "muted": muted, "loadNow": load_now})

    def show(self, sid: str, url: str, x: int, y: int, w: int, h: int) -> dict:
        r = self._post(
            "/show",
            {"sid": sid, "url": url, "x": int(x), "y": int(y), "w": int(w), "h": int(h)},
            timeout=15.0,
        )
        if r.get("ok"):
            self.active_sid = sid
            self.is_shown = True
        return r

    def hide_all(self) -> dict:
        self.active_sid = None
        self.is_shown = False
        return self._post("/hide_all", {})

    def bounds(self, sid: str, x: int, y: int, w: int, h: int) -> dict:
        return self._post(
            "/bounds",
            {"sid": sid, "x": int(x), "y": int(y), "w": int(w), "h": int(h)},
            timeout=2.0,
        )

    def hibernate(self, sid: str) -> dict:
        if self.active_sid == sid:
            self.active_sid = None
            self.is_shown = False
        return self._post("/hibernate", {"sid": sid})

    def wake(self, sid: str, url: str) -> dict:
        return self._post("/wake", {"sid": sid, "url": url})

    def reload(self, sid: str) -> dict:
        return self._post("/reload", {"sid": sid})

    def remove(self, sid: str) -> dict:
        if self.active_sid == sid:
            self.active_sid = None
            self.is_shown = False
        return self._post("/remove", {"sid": sid})

    def get_hibernated_ids(self) -> list[str]:
        r = self._get("/hibernated")
        if r.get("ok"):
            return list(r.get("ids") or [])
        return []

    def get_awake_ids(self) -> list[str]:
        """実際にウィンドウが生成・ロード済み（休止ではない）のsid一覧。
        起動時に一度もcreate/showされていないサービスはここに含まれない
        （= 呼び出し側で「休止扱い」として解釈すべき）。"""
        return self.get_awake_state()[0]

    def get_awake_state(self) -> tuple[list[str], list[str]]:
        """(起動済みsid一覧, うち現在音声を出力中のsid一覧) を1回の問い合わせで返す。"""
        r = self._get("/hibernated")
        if r.get("ok"):
            return list(r.get("awake") or []), list(r.get("audible") or [])
        return [], []

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    def set_always_on_top(self, sid: str, on_top: bool) -> dict:
        return self._post("/setAlwaysOnTop", {"sid": sid, "onTop": on_top})
