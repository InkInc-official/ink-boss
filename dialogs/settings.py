"""
dialogs/settings.py - 設定ダイアログ
Ink Boss / Ink Inc.

ViewBridgeから呼ばれる設定画面（一般・AI/LLM・データ・About の4タブ）。
"""

import json
import os
import shutil
import signal
import subprocess
import threading
import urllib.request
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTabWidget, QWidget,
    QGridLayout, QFrame, QScrollArea, QTextEdit, QFileDialog,
    QInputDialog, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from config import DIALOG_STYLE, save_config
from updater import CURRENT_VERSION
from sysenv import get_clean_subprocess_env

# 非モーダル(.show())のダイアログはPython側の参照が切れるとGCされて
# 消えてしまうため、開いている間はここで保持する。
_open_dialogs: list = []

# ローカルAI(Ollama)の標準モデル。軽量で動作が安定しているためこれ一本を既定にする
DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"


# ─────────────────────────────────────────────────────────
# Ollama の検出・インストール
#
# 【申し送り（将来のWindows対応向け）】
# ここのOllamaインストール処理（curl -fsSL .../install.sh | sh、sudo権限を
# 要する）は Linux 専用の実装。Windowsには sudo という概念自体が無く、
# Ollama公式のインストール手順もWindowsでは全く別物（.exeインストーラー等）に
# なる。将来Windows対応に着手する際は、find_ollama() の探索パス
# （/usr/local/bin 等）、run_ollama_install() 全体、プロセスグループ終了
# （os.killpg / start_new_session はPOSIX専用）をOS判定で分岐させるか、
# Windows版では別の実装に置き換える必要がある。
# ─────────────────────────────────────────────────────────
OLLAMA_INSTALL_CMD = "curl -fsSL https://ollama.com/install.sh | sh"
OLLAMA_INSTALL_TIMEOUT_S = 900
OLLAMA_ADMIN_HINT = (
    "Ollamaのインストールには管理者権限が必要です。難しく感じる場合は、"
    "代わりにClaude/Gemini/DeepSeekのAPIキーを設定する方法もあります"
    "（AI/LLMタブ参照）"
)
# PATHに無くても代表的な配置先にあれば見つける（テストでは差し替え可能にしてある）
_OLLAMA_FALLBACK_PATHS = (
    Path("/usr/local/bin/ollama"),
    Path("/usr/bin/ollama"),
)
OLLAMA_NOT_INSTALLED_MSG = "Ollamaが未インストールです。先に上の「Ollamaをインストール」を実行してください。"


def find_ollama() -> str | None:
    """ollama コマンドの実在を毎回確認する（キャッシュしない）。
    GUI（デスクトップランチャー）から起動されたアプリはPATHが狭いことが
    あるため、shutil.which に加えて代表的な配置先も探す。"""
    found = shutil.which("ollama")
    if found:
        return found
    for cand in (*_OLLAMA_FALLBACK_PATHS, Path.home() / ".local" / "bin" / "ollama"):
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def _tail_lines(text: str, n: int = 5) -> str:
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return "\n".join(l[:200] for l in lines[-n:])


def _install_failure_message(detail: str) -> str:
    parts = ["Ollamaのインストールに失敗しました。"]
    if detail:
        parts.append(detail)
    parts.append("ターミナルで次のコマンドを実行してください:\n  " + OLLAMA_INSTALL_CMD)
    parts.append(OLLAMA_ADMIN_HINT)
    return "\n".join(parts)


def run_ollama_install(on_done) -> None:
    """公式インストールスクリプトをバックグラウンドで実行し、終了後に
    on_done(ok, message) を呼ぶ（ワーカースレッドから呼ばれるため、UI更新は
    Signal経由で行うこと）。

    成功判定は「終了コード0」だけでは不十分で、必ず find_ollama() で
    実際にバイナリが存在することを確認する。`curl ... | sh` はパイプの
    終了コードが末尾の sh のものになるため、curlが無い・接続できない場合でも
    sh が空入力を受けて 0 で終了し、実際には何もインストールされていないのに
    「成功」になる不具合があった（実機で確認済み）。そのため set -o pipefail
    も併用している。"""
    def _worker():
        if shutil.which("curl") is None:
            on_done(False, _install_failure_message(
                "curl が見つかりません。先に「sudo apt install curl」を実行してください。"
            ))
            return
        try:
            # curlはInk Boss自身のバイナリではない外部コマンドのため、
            # PyInstaller由来のLD_LIBRARY_PATH等を取り除いた環境で呼ぶ
            # （sysenv.py参照。創作PCの実機報告で発見:
            #   curl: .../libssl.so.3: version `OPENSSL_3.2.0' not found
            # 同梱の(異なるバージョンの)libssl.so.3をシステムのcurlが
            # 誤ってロードしてしまい失敗していた。dbus-send・Electron本体
            # に続き3回目の同じ構造のバグだったため、個別対応ではなく
            # get_clean_subprocess_env()での共通対策に切り替えた）。
            # start_new_session: タイムアウト時に sh 側の子プロセスごと止められるようにする
            proc = subprocess.Popen(
                ["bash", "-c", "set -o pipefail; " + OLLAMA_INSTALL_CMD],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=True,
                env=get_clean_subprocess_env(),
            )
            try:
                out, err = proc.communicate(timeout=OLLAMA_INSTALL_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    pass
                proc.communicate()
                on_done(False, _install_failure_message(
                    f"{OLLAMA_INSTALL_TIMEOUT_S // 60}分以内に完了しませんでした。"
                ))
                return
        except Exception as e:
            on_done(False, _install_failure_message(str(e)))
            return

        if proc.returncode == 0 and find_ollama() is not None:
            on_done(True, "インストール完了！")
        else:
            detail = _tail_lines(err) or _tail_lines(out)
            if proc.returncode == 0:
                detail = (detail + "\n" if detail else "") + "インストールは終了しましたが、ollamaコマンドが見つかりません。"
            on_done(False, _install_failure_message(detail))

    threading.Thread(target=_worker, daemon=True).start()


class _InstallSignals(QObject):
    """Ollamaインストールのワーカースレッド → UIスレッドへの通知用"""
    done = Signal(bool, str)   # (成功?, メッセージ)


class _PullSignals(QObject):
    """ollama pull のワーカースレッド → UIスレッドへの通知用"""
    progress = Signal(str)
    finished = Signal(bool, str)   # (成功?, モデル名 or エラー文)


def pull_ollama_model(model: str, on_progress=None, on_done=None) -> None:
    """`ollama pull <model>` をバックグラウンドスレッドで実行する。
    on_progress(line) / on_done(ok, model_or_error) はワーカースレッドから
    呼ばれるため、UI更新はSignal経由（_PullSignals）で行うこと。"""
    def _worker():
        # 未インストールのままpullを試みると生のFileNotFoundErrorが出るだけなので、
        # 実行前に実在を確認して分かりやすい案内を返す
        ollama_bin = find_ollama()
        if ollama_bin is None:
            if on_done:
                on_done(False, OLLAMA_NOT_INSTALLED_MSG)
            return
        try:
            # ollamaもInk Boss自身のバイナリではない外部コマンド
            # （システムにインストールされたGo製バイナリ）のため、念のため
            # 同じくサニタイズした環境で呼ぶ（sysenv.py参照）。
            proc = subprocess.Popen(
                [ollama_bin, "pull", model],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                env=get_clean_subprocess_env(),
            )
            last = ""
            for line in proc.stdout:
                last = line.strip()
                if on_progress and last:
                    on_progress(last[:80])
            proc.wait()
            if on_done:
                on_done(proc.returncode == 0, model if proc.returncode == 0 else (last or "ダウンロード失敗"))
        except Exception as e:  # ollama未インストール等
            if on_done:
                on_done(False, str(e))

    threading.Thread(target=_worker, daemon=True).start()


def _confirm_dialog(parent, text: str, yes_label: str, no_label: str) -> bool:
    """他のダイアログと見た目を揃えた確認ダイアログ（QMessageBoxは
    スタイルの都合で正しく描画されないため使わない）。"""
    d = QDialog()   # 親を付けない（他のダイアログと同じ。モーダルはexec()で担保）
    d.setWindowTitle("確認")
    d.setMinimumWidth(360)
    d.setStyleSheet(DIALOG_STYLE)
    d.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
    lay = QVBoxLayout(d)
    lay.setSpacing(12)
    lay.setContentsMargins(24, 24, 24, 24)
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lay.addWidget(lbl)
    row = QHBoxLayout()
    no_btn = QPushButton(no_label)
    yes_btn = QPushButton(yes_label)
    yes_btn.setObjectName("addBtn")
    row.addWidget(no_btn)
    row.addWidget(yes_btn)
    lay.addLayout(row)
    no_btn.clicked.connect(d.reject)
    yes_btn.clicked.connect(d.accept)
    return d.exec() == QDialog.DialogCode.Accepted


def show_settings_dialog(config: dict, js_eval_fn):
    """
    設定ダイアログを表示する。

    Args:
        config:     現在のconfig dict（直接書き換える）
        js_eval_fn: JSイベント発火用関数 js_eval(js_str)
    """
    dialog = QDialog()
    dialog.setWindowTitle("設定")
    dialog.setMinimumSize(540, 520)
    dialog.setStyleSheet(DIALOG_STYLE)
    dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)

    main_layout = QVBoxLayout(dialog)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    # ヘッダー
    header = QWidget()
    header.setStyleSheet("border-bottom: 1px solid rgba(255,255,255,0.05);")
    hl = QHBoxLayout(header)
    hl.setContentsMargins(20, 14, 20, 14)
    title = QLabel("設定")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: bold; letter-spacing: 2px;")
    hl.addWidget(title)
    hl.addStretch()
    close_btn = QPushButton("×")
    close_btn.setStyleSheet(
        "border: none; color: rgba(255,255,255,0.3); font-size: 18px; padding: 2px 8px;"
    )
    close_btn.clicked.connect(dialog.reject)
    hl.addWidget(close_btn)
    main_layout.addWidget(header)

    tabs = QTabWidget()
    main_layout.addWidget(tabs)

    # ────────────────────────────────────
    # タブ①: 一般
    # ────────────────────────────────────
    gen = QWidget()
    gen_l = QVBoxLayout(gen)
    gen_l.setContentsMargins(20, 20, 20, 20)
    gen_l.setSpacing(12)

    lbl = QLabel("休止モード")
    lbl.setStyleSheet(
        "color: rgba(255,255,255,0.35); font-size: 10px; font-family: monospace; letter-spacing: 1px;"
    )
    gen_l.addWidget(lbl)
    desc = QLabel("非アクティブなサービスを指定時間後に自動休止してメモリを解放します")
    desc.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 11px;")
    desc.setWordWrap(True)
    gen_l.addWidget(desc)

    hib_grid = QGridLayout()
    hib_grid.setSpacing(8)
    hib_options = [(0, "無効"), (5, "5分"), (10, "10分"), (15, "15分"), (30, "30分"), (60, "1時間")]
    current_hib = config.get("hibernate_minutes", 10)
    hib_btns = []
    active_s = (
        "QPushButton{border-radius:8px;padding:8px;font-size:13px;"
        "border:1px solid rgba(255,255,255,0.3);background:rgba(255,255,255,0.1);color:white;}"
    )
    inactive_s = (
        "QPushButton{border-radius:8px;padding:8px;font-size:13px;"
        "border:1px solid rgba(255,255,255,0.08);color:rgba(255,255,255,0.4);background:transparent;}"
        "QPushButton:hover{border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.7);}"
    )

    def make_hib_btn(val, label_text, is_active):
        btn = QPushButton(label_text)
        btn.setStyleSheet(active_s if is_active else inactive_s)
        # clicked は checked(bool) を第1引数で渡すため、受け流さないと v が False で上書きされる
        def on_click(_checked=False, v=val):
            config["hibernate_minutes"] = v
            save_config(config)
            for b, bv in hib_btns:
                b.setStyleSheet(active_s if bv == v else inactive_s)
            js_eval_fn(f"window.dispatchEvent(new CustomEvent('hibernate-changed',{{detail:{v}}}));")
        btn.clicked.connect(on_click)
        return btn

    for i, (val, label_text) in enumerate(hib_options):
        btn = make_hib_btn(val, label_text, val == current_hib)
        hib_btns.append((btn, val))
        hib_grid.addWidget(btn, i // 3, i % 3)
    gen_l.addLayout(hib_grid)

    # ナレッジ
    gen_l.addSpacing(12)
    know_lbl = QLabel("ナレッジ（自己紹介・背景）")
    know_lbl.setStyleSheet(
        "color: rgba(255,255,255,0.35); font-size: 10px; font-family: monospace; letter-spacing: 1px;"
    )
    gen_l.addWidget(know_lbl)
    know_desc = QLabel("AIへの自己紹介です。感想ボタン使用時に活用されます（200文字以内）")
    know_desc.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 11px;")
    know_desc.setWordWrap(True)
    gen_l.addWidget(know_desc)

    know_input = QTextEdit()
    know_input.setPlaceholderText(
        "例：ライバー事務所の所長で精神保健福祉士です。配信業界のマーケティングやメンタルケアに興味があります。"
    )
    know_input.setMaximumHeight(80)
    know_input.setPlainText(config.get("knowledge", ""))
    know_input.setStyleSheet(
        "background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);"
        "border-radius: 8px; padding: 8px; color: white; font-size: 12px;"
    )
    gen_l.addWidget(know_input)

    know_save = QPushButton("保存")
    know_save.setObjectName("addBtn")
    know_save_msg = QLabel("")
    know_save_msg.setStyleSheet("color: rgba(100,255,150,0.7); font-size: 11px;")

    def on_know_save():
        text = know_input.toPlainText().strip()[:200]
        config["knowledge"] = text
        save_config(config)
        know_save_msg.setText("✓ 保存しました")
        QTimer.singleShot(2000, lambda: know_save_msg.setText(""))

    know_save.clicked.connect(on_know_save)
    gen_l.addWidget(know_save)
    gen_l.addWidget(know_save_msg)
    gen_l.addStretch()
    tabs.addTab(gen, "一般")
    # ────────────────────────────────────
    # タブ②: AI / LLM
    # ────────────────────────────────────
    ai_w = QWidget()
    ai_scroll = QScrollArea()
    ai_scroll.setWidgetResizable(True)
    ai_scroll.setStyleSheet("QScrollArea{border:none;}")
    ai_scroll.setWidget(ai_w)
    ai_l = QVBoxLayout(ai_w)
    ai_l.setContentsMargins(20, 20, 20, 20)
    ai_l.setSpacing(10)

    def sec_lbl(text):
        l = QLabel(text)
        l.setStyleSheet(
            "color: rgba(255,255,255,0.35); font-size: 10px; font-family: monospace; letter-spacing: 1px;"
        )
        return l

    def text_input(val="", placeholder=""):
        i = QLineEdit()
        i.setText(val)
        i.setPlaceholderText(placeholder)
        return i

    # Ollamaインストール
    ai_l.addWidget(sec_lbl("OLLAMA"))
    ollama_row = QHBoxLayout()
    ollama_status = QLabel("確認中...")
    ollama_status.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 12px;")
    ollama_row.addWidget(ollama_status)
    ollama_row.addStretch()
    install_btn = QPushButton("Ollamaをインストール")
    install_btn.setStyleSheet(
        "QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;"
        "border:1px solid rgba(255,255,255,0.15);color:rgba(255,255,255,0.5);background:transparent;}"
        "QPushButton:hover{border:1px solid rgba(255,255,255,0.3);color:white;}"
    )
    ollama_row.addWidget(install_btn)
    ai_l.addLayout(ollama_row)

    progress_lbl = QLabel("")
    progress_lbl.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 10px;")
    progress_lbl.setWordWrap(True)
    progress_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    ai_l.addWidget(progress_lbl)

    install_signals = _InstallSignals(dialog)

    def refresh_ollama_status():
        """ollamaの実在を毎回確認して表示を更新する（起動時1回だけの判定にしない）"""
        if find_ollama() is not None:
            ollama_status.setText("✓ Ollama インストール済み")
            ollama_status.setStyleSheet("color: rgba(100,255,150,0.7); font-size: 12px;")
            install_btn.setVisible(False)
        else:
            ollama_status.setText("✗ Ollamaが見つかりません")
            ollama_status.setStyleSheet("color: rgba(255,100,100,0.7); font-size: 12px;")
            install_btn.setVisible(True)
            install_btn.setEnabled(True)

    refresh_ollama_status()

    def on_install_done(ok, message):
        progress_lbl.setText(message)
        refresh_ollama_status()
        if ok:
            # 未導入のため出していたモデルDLの案内を消し、DLボタンを有効な状態に戻す
            model_msg.setText("")
        refresh_default_row()

    install_signals.done.connect(on_install_done)

    def on_install_ollama():
        install_btn.setEnabled(False)
        progress_lbl.setText("インストール中...（数分かかることがあります）")
        run_ollama_install(install_signals.done.emit)

    install_btn.clicked.connect(lambda checked=False: on_install_ollama())

    SELECTED_STYLE = (
        "QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;"
        "border:1px solid rgba(100,255,150,0.4);color:rgba(100,255,150,0.8);background:transparent;}"
    )
    UNSELECTED_STYLE = (
        "QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;"
        "border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.6);background:transparent;}"
        "QPushButton:hover{border:1px solid rgba(255,255,255,0.4);color:white;}"
    )
    DOWNLOAD_STYLE = (
        "QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;"
        "border:1px solid rgba(100,200,255,0.3);color:rgba(100,200,255,0.7);background:transparent;}"
        "QPushButton:hover{border:1px solid rgba(100,200,255,0.6);color:rgba(100,200,255,1.0);}"
    )
    if "llm" not in config:
        config["llm"] = {}
    ollama_url = config["llm"].get("ollamaUrl", "http://localhost:11434")

    def fetch_installed_models():
        """`ollama list` 相当（/api/tags）。Ollamaに接続できない場合は None。"""
        try:
            with urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=3) as r:
                return [m["name"] for m in json.loads(r.read()).get("models", [])]
        except Exception:
            return None

    def model_installed(name, installed):
        if not installed:
            return False
        return name in installed or (":" not in name and f"{name}:latest" in installed)

    def current_model():
        return config["llm"].get("ollamaModel") or DEFAULT_OLLAMA_MODEL

    model_state = {"installed": fetch_installed_models()}
    pull_signals = _PullSignals(dialog)

    # --- AIモデル（ローカルAI） ---
    # 標準は qwen2.5:3b 一本。上級者向けに別モデルへ「その場で標準として
    # 上書き」できる（標準と別モデルを並行して記憶する仕組みは持たない）。
    ai_l.addWidget(sec_lbl("AIモデル（ローカルAI）"))
    model_card = QFrame()
    model_card.setObjectName("card")
    model_row = QHBoxLayout(model_card)
    model_row.setContentsMargins(12, 8, 12, 8)
    model_col = QVBoxLayout()
    model_col.setSpacing(1)
    model_nm = QLabel("Qwen2.5 3B（標準）")
    model_nm.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 12px;")
    model_ds = QLabel(f"軽量・日本語対応・無料（{DEFAULT_OLLAMA_MODEL}）")
    model_ds.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 10px;")
    model_col.addWidget(model_nm)
    model_col.addWidget(model_ds)
    model_row.addLayout(model_col)
    model_row.addStretch()
    default_btn = QPushButton("")
    model_row.addWidget(default_btn)
    ai_l.addWidget(model_card)

    model_msg = QLabel("")
    model_msg.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 10px;")
    model_msg.setWordWrap(True)
    ai_l.addWidget(model_msg)

    default_mode = {"v": "download"}

    def refresh_default_row():
        have = model_installed(DEFAULT_OLLAMA_MODEL, model_state["installed"])
        default_btn.setEnabled(True)
        if not have:
            default_mode["v"] = "download"
            default_btn.setText("ダウンロード")
            default_btn.setStyleSheet(DOWNLOAD_STYLE)
        elif current_model() == DEFAULT_OLLAMA_MODEL:
            default_mode["v"] = "none"
            default_btn.setText("使用中")
            default_btn.setStyleSheet(SELECTED_STYLE)
        else:
            default_mode["v"] = "select"
            default_btn.setText("選択")
            default_btn.setStyleSheet(UNSELECTED_STYLE)

    def set_model(name):
        config["llm"]["ollamaModel"] = name
        save_config(config)
        refresh_default_row()
        refresh_scan_list()
        model_msg.setText(f"✓ モデルを {name} に設定しました")

    def on_pull_progress(line):
        model_msg.setText(line)

    def on_pull_finished(ok, info):
        model_state["installed"] = fetch_installed_models()
        if ok:
            model_msg.setText(f"✓ {info} のダウンロードが完了しました")
            if info == DEFAULT_OLLAMA_MODEL:
                set_model(DEFAULT_OLLAMA_MODEL)
                model_msg.setText(f"✓ {info} のダウンロードが完了しました")
            else:
                refresh_scan_list()
        elif info == OLLAMA_NOT_INSTALLED_MSG:
            model_msg.setText(info)
            refresh_ollama_status()
        else:
            model_msg.setText(f"ダウンロード失敗: {info}")
        refresh_default_row()

    pull_signals.progress.connect(on_pull_progress)
    pull_signals.finished.connect(on_pull_finished)

    def on_default_btn():
        if default_mode["v"] == "download":
            # Ollama未導入ならpullを実行せず案内だけ出す
            if find_ollama() is None:
                refresh_ollama_status()
                model_msg.setText(OLLAMA_NOT_INSTALLED_MSG)
                return
            default_btn.setEnabled(False)
            default_btn.setText("DL中...")
            model_msg.setText("ダウンロードを開始します...")
            pull_ollama_model(DEFAULT_OLLAMA_MODEL, pull_signals.progress.emit, pull_signals.finished.emit)
        elif default_mode["v"] == "select":
            set_model(DEFAULT_OLLAMA_MODEL)

    default_btn.clicked.connect(lambda checked=False: on_default_btn())
    refresh_default_row()
    if find_ollama() is None:
        model_msg.setText(OLLAMA_NOT_INSTALLED_MSG)

    # --- 折りたたみ: 他のモデルを使う（上級者向け） ---
    adv_toggle = QPushButton("▶ 他のモデルを使う（上級者向け）")
    adv_toggle.setStyleSheet(
        "QPushButton{border:none;text-align:left;padding:4px 0;font-size:11px;color:rgba(255,255,255,0.45);background:transparent;}"
        "QPushButton:hover{color:white;}"
    )
    ai_l.addWidget(adv_toggle)
    adv_box = QWidget()
    adv_l = QVBoxLayout(adv_box)
    adv_l.setContentsMargins(0, 0, 0, 0)
    adv_l.setSpacing(6)
    adv_box.setVisible(False)   # デフォルトは閉じておく
    ai_l.addWidget(adv_box)

    def on_adv_toggle():
        vis = not adv_box.isVisible()
        adv_box.setVisible(vis)
        adv_toggle.setText(("▼" if vis else "▶") + " 他のモデルを使う（上級者向け）")

    adv_toggle.clicked.connect(lambda checked=False: on_adv_toggle())

    scan_btn = QPushButton("PC内のモデルをスキャン")
    adv_l.addWidget(scan_btn)
    scan_list_w = QWidget()
    scan_list_l = QVBoxLayout(scan_list_w)
    scan_list_l.setContentsMargins(0, 0, 0, 0)
    scan_list_l.setSpacing(4)
    adv_l.addWidget(scan_list_w)
    scanned = {"done": False}

    def refresh_scan_list():
        if not scanned["done"]:
            return
        while scan_list_l.count():
            it = scan_list_l.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        installed = model_state["installed"]
        if installed is None:
            msg = QLabel("Ollamaに接続できません（起動しているか確認してください）")
            msg.setStyleSheet("color: rgba(255,100,100,0.7); font-size: 11px;")
            scan_list_l.addWidget(msg)
            return
        if not installed:
            msg = QLabel("インストール済みのモデルはありません")
            msg.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 11px;")
            scan_list_l.addWidget(msg)
            return
        for name in installed:
            row = QFrame()
            row.setObjectName("card")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 4, 10, 4)
            nl = QLabel(name)
            nl.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 11px;")
            rl.addWidget(nl)
            rl.addStretch()
            in_use = name == current_model()
            b = QPushButton("使用中" if in_use else "選択")
            b.setStyleSheet(SELECTED_STYLE if in_use else UNSELECTED_STYLE)
            if not in_use:
                b.clicked.connect(lambda checked=False, n=name: set_model(n))
            rl.addWidget(b)
            scan_list_l.addWidget(row)

    def on_scan():
        model_state["installed"] = fetch_installed_models()
        scanned["done"] = True
        refresh_scan_list()
        refresh_default_row()

    scan_btn.clicked.connect(lambda checked=False: on_scan())

    custom_lbl = QLabel("モデル名を直接入力（未取得のモデルも指定できます）")
    custom_lbl.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 10px;")
    adv_l.addWidget(custom_lbl)
    custom_row = QHBoxLayout()
    custom_in = text_input("", "例: llama3.2:3b")
    custom_row.addWidget(custom_in)
    custom_btn = QPushButton("設定")
    custom_row.addWidget(custom_btn)
    adv_l.addLayout(custom_row)

    def on_custom_set():
        name = custom_in.text().strip()
        if not name:
            return
        installed = fetch_installed_models()
        model_state["installed"] = installed
        set_model(name)
        if installed is not None and not model_installed(name, installed):
            if find_ollama() is None:
                model_msg.setText(OLLAMA_NOT_INSTALLED_MSG)
            elif _confirm_dialog(
                dialog,
                f"{name} はまだダウンロードされていません。\n今ダウンロードしますか？",
                "ダウンロードする", "設定だけ行う",
            ):
                model_msg.setText(f"{name} のダウンロードを開始します...")
                pull_ollama_model(name, pull_signals.progress.emit, pull_signals.finished.emit)
            else:
                model_msg.setText(f"✓ {name} に設定しました（未取得です。後で ollama pull {name} を実行してください）")
        custom_in.clear()

    custom_btn.clicked.connect(lambda checked=False: on_custom_set())

    # AIバックエンド選択（Claude / Gemini / DeepSeek / ローカルAI の切替）
    ai_l.addWidget(sec_lbl("AIバックエンド"))
    current_backend = config["llm"].get("backend", "ollama")
    backend_buttons: dict = {}

    def make_backend_row(bid, name, desc):
        row_w = QFrame()
        row_w.setObjectName("card")
        row_l = QHBoxLayout(row_w)
        row_l.setContentsMargins(12, 8, 12, 8)
        col_l = QVBoxLayout()
        col_l.setSpacing(1)
        nm = QLabel(name)
        nm.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 12px;")
        ds = QLabel(desc)
        ds.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 10px;")
        col_l.addWidget(nm)
        col_l.addWidget(ds)
        row_l.addLayout(col_l)
        row_l.addStretch()
        btn = QPushButton("使用中" if current_backend == bid else "選択")
        btn.setStyleSheet(SELECTED_STYLE if current_backend == bid else UNSELECTED_STYLE)
        row_l.addWidget(btn)
        backend_buttons[bid] = btn
        ai_l.addWidget(row_w)
        return row_l, btn

    def select_backend(bid):
        config["llm"]["backend"] = bid
        save_config(config)
        for k, v in backend_buttons.items():
            if k == bid:
                v.setText("使用中")
                v.setStyleSheet(SELECTED_STYLE)
            elif v.text() == "使用中":
                v.setText("選択")
                v.setStyleSheet(UNSELECTED_STYLE)
        progress_lbl.setText(f"✓ {bid} を選択しました")

    _, ollama_btn = make_backend_row(
        "ollama", "ローカルAI（Ollama・無料）", "PC内で動作・追加コストなし"
    )
    ollama_btn.clicked.connect(lambda checked=False: select_backend("ollama"))

    # --- API系バックエンド（Claude / Gemini / DeepSeek） ---
    API_BACKENDS = [
        ("claude",   "Claude API",   "高品質・要APIキー",   "claudeApiKey",   "sk-ant-..."),
        ("gemini",   "Gemini API",   "無料枠あり",           "geminiApiKey",   "AIza..."),
        ("deepseek", "DeepSeek API", "低コスト・高性能",     "deepseekApiKey", "sk-..."),
    ]
    key_inputs: dict = {}
    for bid, name, desc, key_field, placeholder in API_BACKENDS:
        _, btn = make_backend_row(bid, name, desc)
        btn.clicked.connect(lambda checked=False, b=bid: select_backend(b))
        ai_l.addWidget(sec_lbl(f"{name} キー"))
        key_in = text_input(config["llm"].get(key_field, ""), placeholder)
        key_in.setEchoMode(QLineEdit.EchoMode.Password)
        ai_l.addWidget(key_in)
        key_inputs[key_field] = key_in

    ai_save = QPushButton("APIキーを保存")
    ai_save.setObjectName("addBtn")
    save_msg = QLabel("")
    save_msg.setStyleSheet("color: rgba(100,255,150,0.7); font-size: 11px;")

    def on_ai_save():
        if "llm" not in config:
            config["llm"] = {}
        config["llm"].update({field: inp.text().strip() for field, inp in key_inputs.items()})
        save_config(config)
        save_msg.setText("✓ 保存しました")
        QTimer.singleShot(2000, lambda: save_msg.setText(""))

    ai_save.clicked.connect(on_ai_save)
    ai_l.addWidget(ai_save)
    ai_l.addWidget(save_msg)
    ai_l.addStretch()
    tabs.addTab(ai_scroll, "AI / LLM")

    # ────────────────────────────────────
    # タブ③: データ
    # ────────────────────────────────────
    data_w = QWidget()
    data_l = QVBoxLayout(data_w)
    data_l.setContentsMargins(20, 20, 20, 20)
    data_l.setSpacing(10)

    exp_btn = QPushButton("設定をエクスポート（JSON）")
    def on_export():
        path, _ = QFileDialog.getSaveFileName(dialog, "保存先", "ink-boss-config.json", "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
    exp_btn.clicked.connect(on_export)
    data_l.addWidget(exp_btn)

    imp_btn = QPushButton("設定をインポート（JSON）")
    def on_import():
        path, _ = QFileDialog.getOpenFileName(dialog, "ファイルを選択", "", "JSON (*.json)")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                new_cfg = json.load(f)
            config.clear()
            config.update(new_cfg)
            save_config(config)
            js_eval_fn("window.dispatchEvent(new CustomEvent('config-imported'));")
            dialog.accept()
    imp_btn.clicked.connect(on_import)
    data_l.addWidget(imp_btn)
    data_l.addStretch()
    tabs.addTab(data_w, "データ")

    # ────────────────────────────────────
    # タブ④: About
    # ────────────────────────────────────
    about_w = QWidget()
    about_l = QVBoxLayout(about_w)
    about_l.setContentsMargins(20, 20, 20, 20)
    about_l.setSpacing(10)

    app_name = QLabel("INK BOSS")
    app_name.setStyleSheet(
        "color: white; font-size: 18px; font-weight: bold; letter-spacing: 2px;"
    )
    about_l.addWidget(app_name)

    version_lbl = QLabel(f"v{CURRENT_VERSION}")
    version_lbl.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 12px; font-family: monospace;")
    about_l.addWidget(version_lbl)

    about_l.addSpacing(8)
    desc_lbl = QLabel(
        "All your services. One place. No compromises.\n"
        "サービスごとにQt / Electronエンジンを選べるデュアルエンジン方式のマルチサービス統合アプリ。"
    )
    desc_lbl.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 11px;")
    desc_lbl.setWordWrap(True)
    about_l.addWidget(desc_lbl)

    about_l.addSpacing(8)
    links_lbl = QLabel(
        '<a href="https://github.com/InkInc-official" style="color:rgba(255,255,255,0.5);">GitHub: InkInc-official</a><br>'
        '<a href="https://inkinc-hp.vercel.app/" style="color:rgba(255,255,255,0.5);">Web: Ink Inc.</a><br>'
        '<a href="https://x.com/InkInc_Info" style="color:rgba(255,255,255,0.5);">X: @InkInc_Info</a>'
    )
    links_lbl.setOpenExternalLinks(True)
    links_lbl.setStyleSheet("font-size: 11px;")
    about_l.addWidget(links_lbl)

    about_l.addStretch()
    license_lbl = QLabel("MIT License — © 2026 黒井葉跡 / Ink Inc.")
    license_lbl.setStyleSheet("color: rgba(255,255,255,0.25); font-size: 10px;")
    about_l.addWidget(license_lbl)
    tabs.addTab(about_w, "About")

    # 非モーダル表示（.show()）は、この関数を抜けるとローカル変数 dialog への
    # 参照が切れて即GCされ、ウィンドウが一切表示されない（または一瞬で消える）。
    # モジュールレベルで参照を保持し、閉じられたら解放する。
    _open_dialogs.append(dialog)
    dialog.finished.connect(lambda _=None, d=dialog: _open_dialogs.remove(d) if d in _open_dialogs else None)

    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog
