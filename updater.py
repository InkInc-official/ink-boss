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

load_dotenv(Path(__file__).parent / ".env")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 設定
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GITHUB_OWNER = "InkInc-official"
GITHUB_REPO  = "ink-boss"
GITHUB_PAT   = os.getenv("GITHUB_PAT", "")

# 現在のバージョン（リリース時に更新する）
CURRENT_VERSION = "1.0.0"

# アセット名（OS別）
ASSET_NAME = {
    "Linux":   "ink-boss.deb",
    "Windows": "ink-boss-setup.exe",
}.get(platform.system(), "ink-boss.deb")


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

    # アセットのダウンロードURLを探す
    download_url = None
    for asset in release.get("assets", []):
        if asset["name"] == ASSET_NAME:
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
    save_path = Path.home() / "Downloads" / ASSET_NAME
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
        if platform.system() == "Linux":
            subprocess.Popen(
                ["pkexec", "dpkg", "-i", str(save_path)],
                start_new_session=True,
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
