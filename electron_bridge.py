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
from typing import Any

ENGINE_DIR = Path(__file__).resolve().parent / "electron-engine"
READY_PREFIX = "INK_ELECTRON_READY port="
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
                if any(k in low for k in ("error", "fail", "ready", "listening", "created", "shutdown", "quit")):
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

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    def set_always_on_top(self, sid: str, on_top: bool) -> dict:
        return self._post("/setAlwaysOnTop", {"sid": sid, "onTop": on_top})
