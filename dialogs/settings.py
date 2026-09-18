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
from PySide6.QtCore import Qt, QTimer
from config import DIALOG_STYLE, save_config
from updater import CURRENT_VERSION

# 非モーダル(.show())のダイアログはPython側の参照が切れるとGCされて
# 消えてしまうため、開いている間はここで保持する。
_open_dialogs: list = []


def show_settings_dialog(config: dict, js_eval_fn) -> None:
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
        def on_click(v=val):
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

    # AIバックエンド選択
    # 以前はOllamaモデルを5種類から選ぶUIだったが、qwen2.5:3b一本に
    # 統一（軽量で動作が安定しているため）。あわせて、Claude/Gemini/
    # DeepSeekを含む「バックエンド選択」自体をここで一元化する
    # （以前はモデル選択ボタンでしかbackendを切り替えられず、
    # Claude/GeminiのAPIキーを入力しても選択する手段が無かった）。
    ai_l.addWidget(sec_lbl("AIバックエンド"))

    OLLAMA_MODEL = "qwen2.5:3b"
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

    try:
        with urllib.request.urlopen(
            f"{config.get('llm', {}).get('ollamaUrl', 'http://localhost:11434')}/api/tags",
            timeout=3,
        ) as r:
            installed_models = [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        installed_models = []

    current_backend = config.get("llm", {}).get("backend", "ollama")
    ollama_model_installed = any(OLLAMA_MODEL.split(":")[0] in m for m in installed_models)
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
        if "llm" not in config:
            config["llm"] = {}
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

    # --- ローカルAI（Ollama・qwen2.5:3b固定） ---
    ollama_row_l, ollama_btn = make_backend_row(
        "ollama", "ローカルAI（Ollama・無料）", "PC内で動作・追加コストなし"
    )
    ollama_status_lbl = QLabel("✓" if ollama_model_installed else "")
    ollama_status_lbl.setStyleSheet("color: rgba(100,255,150,0.6); font-size: 11px;")
    ollama_row_l.insertWidget(1, ollama_status_lbl)

    if ollama_model_installed:
        ollama_btn.clicked.connect(lambda: select_backend("ollama"))
    else:
        ollama_btn.setText("ダウンロード")
        ollama_btn.setStyleSheet(DOWNLOAD_STYLE)

        def on_dl_ollama():
            import threading
            from PySide6.QtCore import QMetaObject, Q_ARG
            ollama_btn.setEnabled(False)
            ollama_btn.setText("DL中...")

            def do_pull():
                try:
                    proc = subprocess.Popen(
                        ["ollama", "pull", OLLAMA_MODEL],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    )
                    for line in proc.stdout:
                        QMetaObject.invokeMethod(progress_lbl, "setText",
                            Qt.ConnectionType.QueuedConnection,
                            Q_ARG(str, line.strip()[:80]))
                    proc.wait()
                    if proc.returncode == 0:
                        QMetaObject.invokeMethod(ollama_status_lbl, "setText",
                            Qt.ConnectionType.QueuedConnection, Q_ARG(str, "✓"))
                        ollama_btn.setEnabled(True)
                        select_backend("ollama")
                    else:
                        QMetaObject.invokeMethod(progress_lbl, "setText",
                            Qt.ConnectionType.QueuedConnection,
                            Q_ARG(str, "ダウンロード失敗"))
                        ollama_btn.setEnabled(True)
                except Exception as e:
                    QMetaObject.invokeMethod(progress_lbl, "setText",
                        Qt.ConnectionType.QueuedConnection, Q_ARG(str, f"エラー: {e}"))
                    ollama_btn.setEnabled(True)
            threading.Thread(target=do_pull, daemon=True).start()

        ollama_btn.clicked.connect(on_dl_ollama)
    if "llm" not in config:
        config["llm"] = {}
    config["llm"]["ollamaModel"] = OLLAMA_MODEL

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
        key_in = text_input(config.get("llm", {}).get(key_field, ""), placeholder)
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
