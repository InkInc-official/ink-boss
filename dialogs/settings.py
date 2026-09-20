"""
dialogs/settings.py - 設定ダイアログ
Ink Boss / Ink Inc.

ViewBridgeから呼ばれる設定画面（一般・AI/LLM・データ・About の4タブ）。
"""

import json
import subprocess
import urllib.request
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTabWidget, QWidget,
    QGridLayout, QFrame, QScrollArea, QTextEdit, QFileDialog,
    QInputDialog, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from config import DIALOG_STYLE, save_config
from updater import CURRENT_VERSION

# 非モーダル(.show())のダイアログはPython側の参照が切れるとGCされて
# 消えてしまうため、開いている間はここで保持する。
_open_dialogs: list = []

# ローカルAI(Ollama)の標準モデル。軽量で動作が安定しているためこれ一本を既定にする
DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"


class _PullSignals(QObject):
    """ollama pull のワーカースレッド → UIスレッドへの通知用"""
    progress = Signal(str)
    finished = Signal(bool, str)   # (成功?, モデル名 or エラー文)


def pull_ollama_model(model: str, on_progress=None, on_done=None) -> None:
    """`ollama pull <model>` をバックグラウンドスレッドで実行する。
    on_progress(line) / on_done(ok, model_or_error) はワーカースレッドから
    呼ばれるため、UI更新はSignal経由（_PullSignals）で行うこと。"""
    import threading

    def _worker():
        try:
            proc = subprocess.Popen(
                ["ollama", "pull", model],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
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

    ollama_installed = subprocess.run(["which", "ollama"], capture_output=True).returncode == 0
    if ollama_installed:
        ollama_status.setText("✓ Ollama インストール済み")
        ollama_status.setStyleSheet("color: rgba(100,255,150,0.7); font-size: 12px;")
        install_btn.setVisible(False)
    else:
        ollama_status.setText("✗ Ollamaが見つかりません")
        ollama_status.setStyleSheet("color: rgba(255,100,100,0.7); font-size: 12px;")

    progress_lbl = QLabel("")
    progress_lbl.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 10px;")
    progress_lbl.setWordWrap(True)
    ai_l.addWidget(progress_lbl)

    def on_install_ollama():
        import threading
        from PySide6.QtCore import QMetaObject, Q_ARG
        install_btn.setEnabled(False)
        progress_lbl.setText("インストール中...")
        def do_install():
            try:
                result = subprocess.run(
                    ["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    QMetaObject.invokeMethod(ollama_status, "setText",
                        Qt.ConnectionType.QueuedConnection, Q_ARG(str, "✓ Ollama インストール済み"))
                    ollama_status.setStyleSheet("color: rgba(100,255,150,0.7); font-size: 12px;")
                    QMetaObject.invokeMethod(progress_lbl, "setText",
                        Qt.ConnectionType.QueuedConnection, Q_ARG(str, "インストール完了！"))
                    QMetaObject.invokeMethod(install_btn, "setVisible",
                        Qt.ConnectionType.QueuedConnection, Q_ARG(bool, False))
                else:
                    QMetaObject.invokeMethod(progress_lbl, "setText",
                        Qt.ConnectionType.QueuedConnection, Q_ARG(str, f"エラー: {result.stderr[:100]}"))
                    install_btn.setEnabled(True)
            except Exception as e:
                QMetaObject.invokeMethod(progress_lbl, "setText",
                    Qt.ConnectionType.QueuedConnection, Q_ARG(str, f"エラー: {e}"))
                install_btn.setEnabled(True)
        threading.Thread(target=do_install, daemon=True).start()

    install_btn.clicked.connect(on_install_ollama)

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
        else:
            model_msg.setText(f"ダウンロード失敗: {info}")
        refresh_default_row()

    pull_signals.progress.connect(on_pull_progress)
    pull_signals.finished.connect(on_pull_finished)

    def on_default_btn():
        if default_mode["v"] == "download":
            default_btn.setEnabled(False)
            default_btn.setText("DL中...")
            model_msg.setText("ダウンロードを開始します...")
            pull_ollama_model(DEFAULT_OLLAMA_MODEL, pull_signals.progress.emit, pull_signals.finished.emit)
        elif default_mode["v"] == "select":
            set_model(DEFAULT_OLLAMA_MODEL)

    default_btn.clicked.connect(lambda checked=False: on_default_btn())
    refresh_default_row()

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
            if _confirm_dialog(
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
