"""
dialogs/settings.py - 設定ダイアログ
Ink Boss / Ink Inc.

ViewBridgeから呼ばれる設定画面（一般・AI/LLM・データ の3タブ）。
"""

import json
import subprocess
import urllib.request
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTabWidget, QWidget,
    QGridLayout, QFrame, QScrollArea, QTextEdit, QFileDialog,
)
from PySide6.QtCore import Qt, QTimer
from config import DIALOG_STYLE, save_config


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

    # モデル管理
    ai_l.addWidget(sec_lbl("モデル管理"))
    RECOMMENDED = [
        ("gemma2:9b",       "Gemma 2 9B",     "高品質（Google）"),
        ("qwen2.5:3b",      "Qwen 2.5 3B",    "軽量・多言語対応"),
        ("qwen2.5:7b",      "Qwen 2.5 7B",    "バランス型・多言語"),
        ("llama3.2:latest", "Llama 3.2",      "Meta製汎用モデル"),
        ("mistral:7b",      "Mistral 7B",     "高品質・フランス製"),
    ]

    try:
        with urllib.request.urlopen(
            f"{config.get('llm', {}).get('ollamaUrl', 'http://localhost:11434')}/api/tags",
            timeout=3,
        ) as r:
            installed_models = [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        installed_models = []

    current_model = config.get("llm", {}).get("ollamaModel", "")
    model_buttons = {}

    for model_id, model_name, model_desc in RECOMMENDED:
        row_w = QFrame()
        row_w.setObjectName("card")
        row_l = QHBoxLayout(row_w)
        row_l.setContentsMargins(12, 8, 12, 8)
        col_l = QVBoxLayout()
        col_l.setSpacing(1)
        nm = QLabel(model_name)
        nm.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 12px;")
        ds = QLabel(model_desc)
        ds.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 10px;")
        col_l.addWidget(nm)
        col_l.addWidget(ds)
        row_l.addLayout(col_l)
        row_l.addStretch()

        is_installed = any(model_id.split(":")[0] in m for m in installed_models)
        is_selected  = bool(current_model and current_model == model_id)
        st_lbl = QLabel("✓" if is_installed else "")
        st_lbl.setStyleSheet("color: rgba(100,255,150,0.6); font-size: 11px;")
        row_l.addWidget(st_lbl)

        if is_selected:
            ab = QPushButton("使用中")
            ab.setStyleSheet(
                "QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;"
                "border:1px solid rgba(100,255,150,0.4);color:rgba(100,255,150,0.8);background:transparent;}"
            )
        elif is_installed:
            ab = QPushButton("選択")
            ab.setStyleSheet(
                "QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;"
                "border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.6);background:transparent;}"
                "QPushButton:hover{border:1px solid rgba(255,255,255,0.4);color:white;}"
            )
        else:
            ab = QPushButton("ダウンロード")
            ab.setStyleSheet(
                "QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;"
                "border:1px solid rgba(100,200,255,0.3);color:rgba(100,200,255,0.7);background:transparent;}"
                "QPushButton:hover{border:1px solid rgba(100,200,255,0.6);color:rgba(100,200,255,1.0);}"
            )
        row_l.addWidget(ab)
        model_buttons[model_id] = ab
        ai_l.addWidget(row_w)

        def make_cb(mid=model_id, btn=ab, slb=st_lbl, inst=is_installed):
            if inst:
                def on_sel(checked=False, m=mid, b=btn):
                    if "llm" not in config:
                        config["llm"] = {}
                    config["llm"]["ollamaModel"] = m
                    config["llm"]["backend"] = "ollama"
                    save_config(config)
                    for k, v in model_buttons.items():
                        if k == m:
                            v.setText("使用中")
                            v.setStyleSheet(
                                "QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;"
                                "border:1px solid rgba(100,255,150,0.4);color:rgba(100,255,150,0.8);background:transparent;}"
                            )
                        elif v.text() == "使用中":
                            v.setText("選択")
                            v.setStyleSheet(
                                "QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;"
                                "border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.6);background:transparent;}"
                                "QPushButton:hover{border:1px solid rgba(255,255,255,0.4);color:white;}"
                            )
                    progress_lbl.setText(f"✓ {m} を選択しました")
                btn.clicked.connect(on_sel)
            else:
                def on_dl(m=mid, b=btn, s=slb):
                    import threading
                    from PySide6.QtCore import QMetaObject, Q_ARG
                    b.setEnabled(False)
                    b.setText("DL中...")
                    def do_pull():
                        try:
                            proc = subprocess.Popen(
                                ["ollama", "pull", m],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            )
                            for line in proc.stdout:
                                QMetaObject.invokeMethod(progress_lbl, "setText",
                                    Qt.ConnectionType.QueuedConnection,
                                    Q_ARG(str, line.strip()[:80]))
                            proc.wait()
                            if proc.returncode == 0:
                                QMetaObject.invokeMethod(s, "setText",
                                    Qt.ConnectionType.QueuedConnection, Q_ARG(str, "✓"))
                                QMetaObject.invokeMethod(b, "setText",
                                    Qt.ConnectionType.QueuedConnection, Q_ARG(str, "選択"))
                                b.setEnabled(True)
                                b.setStyleSheet(
                                    "QPushButton{border-radius:6px;padding:4px 10px;font-size:11px;"
                                    "border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.6);background:transparent;}"
                                )
                                if "llm" not in config:
                                    config["llm"] = {}
                                config["llm"]["ollamaModel"] = m
                                config["llm"]["backend"] = "ollama"
                                save_config(config)
                            else:
                                QMetaObject.invokeMethod(progress_lbl, "setText",
                                    Qt.ConnectionType.QueuedConnection,
                                    Q_ARG(str, "ダウンロード失敗"))
                                b.setEnabled(True)
                        except Exception as e:
                            QMetaObject.invokeMethod(progress_lbl, "setText",
                                Qt.ConnectionType.QueuedConnection, Q_ARG(str, f"エラー: {e}"))
                            b.setEnabled(True)
                    threading.Thread(target=do_pull, daemon=True).start()
                btn.clicked.connect(on_dl)
        make_cb()

    # APIキー
    ai_l.addWidget(sec_lbl("CLAUDE API キー"))
    claude_in = text_input(config.get("llm", {}).get("claudeApiKey", ""), "sk-ant-...")
    claude_in.setEchoMode(QLineEdit.EchoMode.Password)
    ai_l.addWidget(claude_in)

    ai_l.addWidget(sec_lbl("GEMINI API キー"))
    gemini_in = text_input(config.get("llm", {}).get("geminiApiKey", ""), "AIza...")
    gemini_in.setEchoMode(QLineEdit.EchoMode.Password)
    ai_l.addWidget(gemini_in)

    ai_save = QPushButton("APIキーを保存")
    ai_save.setObjectName("addBtn")
    save_msg = QLabel("")
    save_msg.setStyleSheet("color: rgba(100,255,150,0.7); font-size: 11px;")

    def on_ai_save():
        if "llm" not in config:
            config["llm"] = {}
        config["llm"].update({
            "claudeApiKey": claude_in.text().strip(),
            "geminiApiKey": gemini_in.text().strip(),
        })
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

    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
