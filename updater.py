"""
updater.py - 自動更新処理
Ink Boss / Ink Inc.

起動時にGitHub Releasesで最新バージョンを確認し、
新しいバージョンがあればダイアログを表示して更新する。
"""

import os
import sys
import json
import platform
import subprocess
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

from sysenv import get_clean_subprocess_env

load_dotenv(Path(__file__).parent / ".env")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 設定
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GITHUB_OWNER = "InkInc-official"
GITHUB_REPO  = "ink-boss"
GITHUB_PAT   = os.getenv("GITHUB_PAT", "")

def _read_version() -> str:
    """プロジェクトルートのVERSIONファイルを読む。build_deb.shのVERSION
    変数もこの同じファイルを読むようにしており、単一の情報源にしている
    （以前はbuild_deb.shのVERSIONとupdater.pyのCURRENT_VERSIONをそれぞれ
    手動で上げる運用にしていたが、CURRENT_VERSIONの更新を忘れて古い
    バージョン表示のままになる不具合が実際に起きたため統一した）。

    PyInstaller(--onedir)でパッケージされた場合、datasで指定した
    ファイルは実行ファイルと同じ階層ではなく_internal/配下に展開される
    （実機のdist/ink-boss/_internal/で確認済み）ため、sys._MEIPASS
    （--onedirでも_internal/を指す）を優先的に見る。それも無ければ
    実行ファイル自身の隣、開発時（python3 main.py直接実行）は
    このファイル自身の隣を見る。"""
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "VERSION")
        candidates.append(Path(sys.executable).resolve().parent / "VERSION")
    else:
        candidates.append(Path(__file__).resolve().parent / "VERSION")
    for c in candidates:
        try:
            v = c.read_text(encoding="utf-8").strip()
            if v:
                return v
        except OSError:
            continue
    return "0.0.0"


# 現在のバージョン（VERSIONファイルから読む。手動で書き換えない）
CURRENT_VERSION = _read_version()

# アセットの拡張子（OS別）。実際のファイル名は build_deb.sh の命名規則
# （例: ink-boss_1.0.3_amd64.deb）によりバージョンごとに変わるため、
# 固定ファイル名での完全一致ではなく拡張子での判定に変更した
# （実機で「ダウンロードURLが見つかりません」エラーを確認・修正）。
ASSET_EXT = {
    "Linux":   ".deb",
    "Windows": ".exe",
}.get(platform.system(), ".deb")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# バージョン比較
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _parse_version(v: str) -> tuple:
    """'1.2.3' → (1, 2, 3)"""
    v = v.lstrip("v")
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0, 0, 0)


def _is_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GitHub API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _fetch_latest_release() -> dict | None:
    """GitHub APIで最新リリース情報を取得する"""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_PAT:
        headers["Authorization"] = f"Bearer {GITHUB_PAT}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as e:
        print(f"[Updater] GitHub API接続失敗: {e}", flush=True)
        return None


def check_update() -> dict:
    """
    アップデートを確認する。

    Returns:
        {
            "available": bool,
            "latest_version": str,
            "download_url": str | None,
            "release_notes": str,
        }
    """
    release = _fetch_latest_release()
    if not release:
        return {"available": False, "latest_version": CURRENT_VERSION,
                "download_url": None, "release_notes": ""}

    latest_version = release.get("tag_name", "").lstrip("v")
    release_notes  = release.get("body", "")

    if not _is_newer(latest_version, CURRENT_VERSION):
        print(f"[Updater] 最新版です ({CURRENT_VERSION})", flush=True)
        return {"available": False, "latest_version": latest_version,
                "download_url": None, "release_notes": ""}

    # アセットのダウンロードURLを探す（バージョンごとにファイル名が変わるため拡張子で判定）
    download_url = None
    for asset in release.get("assets", []):
        if asset.get("name", "").endswith(ASSET_EXT):
            download_url = asset["browser_download_url"]
            break

    print(f"[Updater] 新バージョン検出: {CURRENT_VERSION} → {latest_version}", flush=True)
    return {
        "available": True,
        "latest_version": latest_version,
        "download_url": download_url,
        "release_notes": release_notes,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ダウンロード＆インストール
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def download_and_install(download_url: str, progress_callback=None) -> bool:
    """
    アップデートをダウンロードしてインストールする。

    Args:
        download_url:      ダウンロードURL
        progress_callback: (downloaded_bytes, total_bytes) → None
    Returns:
        成功したかどうか
    """
    # ファイル名はダウンロードURLの末尾から取る（バージョンごとに変わるため）
    filename = download_url.rstrip("/").rsplit("/", 1)[-1] or f"ink-boss{ASSET_EXT}"
    save_path = Path.home() / "Downloads" / filename
    headers = {}
    if GITHUB_PAT:
        headers["Authorization"] = f"Bearer {GITHUB_PAT}"

    try:
        req = urllib.request.Request(download_url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as res:
            total = int(res.headers.get("Content-Length", 0))
            downloaded = 0
            chunk = 8192
            with open(save_path, "wb") as f:
                while True:
                    data = res.read(chunk)
                    if not data:
                        break
                    f.write(data)
                    downloaded += len(data)
                    if progress_callback:
                        progress_callback(downloaded, total)

        print(f"[Updater] ダウンロード完了: {save_path}", flush=True)

        # インストール実行
        # pkexec/dpkgはInk Boss自身のバイナリではない外部コマンドのため、
        # PyInstaller由来のLD_LIBRARY_PATH等を取り除いた環境で呼ぶ
        # （sysenv.py参照。pkexecはroot権限で別途起動されるが、環境の
        # 継承経路を信用せず明示的にサニタイズしておく）。
        if platform.system() == "Linux":
            subprocess.Popen(
                ["pkexec", "dpkg", "-i", str(save_path)],
                start_new_session=True,
                env=get_clean_subprocess_env(),
            )
        elif platform.system() == "Windows":
            subprocess.Popen(
                [str(save_path), "/S"],  # サイレントインストール
                start_new_session=True,
            )
        return True

    except Exception as e:
        print(f"[Updater] ダウンロード失敗: {e}", flush=True)
        return False
