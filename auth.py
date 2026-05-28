"""
auth.py - ライセンス認証処理
Ink Boss / Ink Inc.

起動時にライセンスキーとマシンIDをInk FormのAPIに送信し、
認証結果をキャッシュする。
キャッシュ有効期限は7日間。
"""

import json
import hashlib
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 設定
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ink FormのngrokエンドポイントURL（変更になった場合はここだけ変える）
LICENSE_API_URL = "https://goofball-marital-lying.ngrok-free.dev/api/license/verify"

# キャッシュ有効期限（日数）
CACHE_DAYS = 7

# キャッシュファイルのパス（config.pyのCONFIG_DIRと同じ場所に置く）
AUTH_CACHE_FILE = Path.home() / ".config" / "ink-boss" / "auth_cache.json"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# マシンID取得
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_machine_id() -> str:
    """PCのマシンIDを取得する（Linux専用）"""
    try:
        return Path("/etc/machine-id").read_text().strip()
    except Exception:
        # フォールバック：ホスト名のハッシュ
        import socket
        return hashlib.md5(socket.gethostname().encode()).hexdigest()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# キャッシュ操作
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _load_cache() -> dict:
    """キャッシュファイルを読み込む"""
    try:
        if AUTH_CACHE_FILE.exists():
            return json.loads(AUTH_CACHE_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_cache(license_key: str) -> None:
    """認証成功時にキャッシュを保存する"""
    cache = {
        "license_key": license_key,
        "cached_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(days=CACHE_DAYS)).isoformat(),
    }
    AUTH_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def _clear_cache() -> None:
    """キャッシュを削除する"""
    try:
        AUTH_CACHE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _is_cache_valid(license_key: str) -> bool:
    """キャッシュが有効かどうかを確認する"""
    cache = _load_cache()
    if not cache:
        return False
    # キーが一致しているか
    if cache.get("license_key") != license_key:
        return False
    # 有効期限内か
    try:
        expires_at = datetime.fromisoformat(cache["expires_at"])
        return datetime.now() < expires_at
    except Exception:
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 認証メイン処理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def verify(license_key: str) -> dict:
    """
    ライセンスキーを認証する。

    Returns:
        {
            "valid": bool,
            "reason": str,   # "ok" | "cache" | "invalid_key" | "inactive"
                             # "machine_limit" | "offline" | "error"
            "from_cache": bool,
        }
    """
    license_key = license_key.strip()

    if not license_key:
        return {"valid": False, "reason": "no_key", "from_cache": False}

    # キャッシュが有効なら即OKを返す
    if _is_cache_valid(license_key):
        print("[Auth] キャッシュ有効 → 認証スキップ", flush=True)
        return {"valid": True, "reason": "cache", "from_cache": True}

    # APIに問い合わせ
    machine_id = get_machine_id()
    print(f"[Auth] API認証開始: key={license_key[:8]}... machine={machine_id[:8]}...", flush=True)

    try:
        import urllib.request
        payload = json.dumps({
            "license_key": license_key,
            "machine_id": machine_id,
        }).encode("utf-8")

        req = urllib.request.Request(
            LICENSE_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "ngrok-skip-browser-warning": "1",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as res:
            result = json.loads(res.read().decode("utf-8"))

        print(f"[Auth] API結果: {result}", flush=True)

        if result.get("valid"):
            _save_cache(license_key)
            return {"valid": True, "reason": result.get("reason", "ok"), "from_cache": False}
        else:
            _clear_cache()
            return {"valid": False, "reason": result.get("reason", "error"), "from_cache": False}

    except Exception as e:
        print(f"[Auth] API接続失敗: {e}", flush=True)
        # オフライン時はキャッシュを再確認（期限切れでも一時的に許可しない）
        return {"valid": False, "reason": "offline", "from_cache": False}


def get_cached_key() -> str:
    """保存済みのライセンスキーを返す（設定画面表示用）"""
    cache = _load_cache()
    return cache.get("license_key", "")


def save_license_key_to_config(config: dict, license_key: str) -> None:
    """ライセンスキーをconfigに保存する"""
    config["license_key"] = license_key.strip()
