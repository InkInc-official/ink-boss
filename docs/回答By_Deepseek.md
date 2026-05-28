# Ink Hub セカンドオピニオン回答書

**回答日：** 2026年5月24日
**回答者：** DeepSeek（セカンドオピニオンAI）
**対象プロジェクト：** Ink Hub（Ink Inc. / 黒井葉跡）


## 総評

「レシピレス設計＋LLM統合＋Electron非依存」というコンセプトは非常に優れている。
しかし、Tauri v2のWebView真っ黒問題はクリティカルであり、移行を検討すべき。


## Q1. Tauri v2でWebViewを動かす方法は？

**結論：ない。**

Tauri v2は`<webview>`タグを廃止した。WebviewWindow方式は可能だが、タブUIとの統合が極めて困難。Rustで直接GTK WebViewを操作する方法もあるが、メンテナンス不能になる。


## Q2. Googleログインを突破できる最適解は？

**最適解：QtWebEngine（PySide6またはPyQt6）**

QtWebEngineはChromiumベースのため、Googleの埋め込みブラウザ検出を回避できる。特別なハックは不要。


## Q3. PySide6 vs Tauri WebviewWindow 比較

| 項目 | Tauri | PySide6 |
|------|-------|---------|
| 実装コード量 | ~500行 | ~100行 |
| セッション分離 | 複雑 | 3行で完了 |
| Googleログイン | 不安定 | 確実 |
| メモリ（3サービス） | ~90MB | ~200MB |

**判断：パフォーマンス差より確実性を優先すべき。** 200MBは現代のPCで問題にならない。


## Q4. 他の選択肢は？

- Wails + WebKitGTK：Tauriと同じ問題
- Ultralight/Servo/Sciter：未成熟または非対応
- システムChromium埋め込み：重く、ラッパーになる

**結論：「軽量」と「Googleログイン確実」の両立は不可能。** どちらかを妥協する必要がある。


## Q5. 最もシンプルな実装方法

PySide6 + QWebEngineProfileで約50行。

```python
import sys
from PySide6.QtWidgets *
from PySide6.QtWebEngineWidgets import *
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage

class ServiceTab(QWebEngineView):
    def __init__(self, url: str, name: str):
        self.profile = QWebEngineProfile(name)
        super().__init__()
        self.setPage(QWebEnginePage(self.profile, self))
        self.setUrl(QUrl(url))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ink Hub")
        self.setGeometry(100, 100, 1200, 800)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.tabs.removeTab)
        self.add_tab_button = QPushButton("+")
        self.add_tab_button.clicked.connect(self.add_new_tab)
        layout = QVBoxLayout()
        layout.addWidget(self.add_tab_button)
        layout.addWidget(self.tabs)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.add_service_tab("https://mail.google.com", "Gmail")

    def add_service_tab(self, url: str, name: str):
        tab = ServiceTab(url, name)
        self.tabs.addTab(tab, name)

    def add_new_tab(self):
        dialog = QDialog(self)
        layout = QFormLayout(dialog)
        url_input = QLineEdit()
        name_input = QLineEdit()
        layout.addRow("URL:", url_input)
        layout.addRow("名前:", name_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec():
            self.add_service_tab(url_input.text(), name_input.text())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
最終推奨
PySide6 + QtWebEngine を選ぶこと。

理由：

Googleログインが確実に動く（最重要）

実装が簡単（約50行で完成）

PythonなのでInk Memoryと共通言語

200MBのメモリは許容範囲

Tauriを続投するのは以下の場合のみ：

Googleログインを諦められる

メモリを絶対に100MB以下にしたい

次のアクション
上記コードでプロトタイプを作成し、Gmailログインをテストする

メモリ使用量を実測する

サイドバーUIをQListWidgetで再実装する

LLM統合機能を追加する

「動かない完璧な設計」より「動くシンプルな実装」を。

応援しています。