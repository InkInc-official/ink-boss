📋 セカンドオピニオン総括
黒井様、詳細な現状報告ありがとうございます。Ink Hubの「レシピ不要・LLM統合・非Electron・完全OSS」という方向性は明確であり、技術的負債を抱えずにFerdiumの課題を解決しようとする姿勢は高く評価できます。以下、ご質問の5点に技術的・実務的観点から回答します。
1. Tauri v2でWebViewを正しく動かす方法（WebviewWindow以外含む）
Tauri v2で<webview>タグが廃止されたのはアーキテクチャ上の決定であり、戻すことはできません。現状「真っ黒」になる主な原因は、webkit2gtk 2.52.3のハードウェアアクセラレーション/コンポジット描画との相性問題です。
試すべき即効策（放棄前に検証を）
bash
12345# 実行前に環境変数を付与して起動WEBKIT_DISABLE_COMPOSITING_MODE=1 \GDK_DEBUG=gl \WEBKIT_FORCE_WEB_PROCESS_LIMIT=1 \cargo tauri dev
WEBKIT_DISABLE_COMPOSITING_MODE=1：GPU描画を無効化し、CPUレンダリングにフォールバック（黒画面解消率高い）
GDK_DEBUG=gl：GLデバッグログ出力でドライバ衝突を特定
tauri.conf.jsonのbundle設定に"active": falseを一時的に設定し、開発環境のみで挙動を確認
WebviewWindow以外の現実的アプローチ
手法
実現性
備考
<iframe> + tauri-plugin-httpプロキシ
△
CSP回避は可能だが、Google系はiframe内でのOAuthをブロック
x11rb/wlrootsによる外部ブラウザEmbedding
✕
複雑すぎ、セッション分離・UI同期が困難
WebviewWindow + ウィンドウ位置同期
◎
公式推奨。tauri::window::Windowのset_position/set_sizeをメインウィンドウのリサイズイベントにバインドし、CSSでtransform: translateZ(0)でGPUコンポジットを安定化
👉 結論：Tauri v2継続ならWebviewWindow一択。黒画面は環境変数フラグで解消できる可能性が高いが、Googleログインの根本解決には繋がらない。
2. Ubuntu 24.04でGoogleログインを突破できるフレームワークの最適解
Googleは**「組み込みブラウザの検出（User-Agent・JS Feature Detection・Cookie Partitioning）」**により、非標準WebViewのOAuthログインを明示的にブロックしています。
フレームワーク
Ubuntu 24.04でのGoogleログイン
理由
Tauri v2 (webkit2gtk)
△ 不安定
webkit2gtkはChromium互換だが、Googleのセキュリティポリシーに抵触しやすく、UA偽装だけでは突破困難
PySide6/PyQt6 + QtWebEngine
◎ 安定
Chromiumベース（v120準拠）で標準ブラウザと同等のJS/COOKIES/Storage動作
CEF (Chromium Embedded Framework)
◎ 安定
純粋なChromium埋め込み。互換性最高だがバイナリ肥大・ビルド複雑
Wails / Neutralino / Dioxus
△
Linuxでは全てwebkit2gtk依存のため同課題
👉 最適解：
PySide6 + QtWebEngine が Ubuntu 24.04 上で「Googleログイン確実突破」を担保する唯一の実用的な選択肢です。
3. PySide6 + QtWebEngine vs Tauri WebviewWindow（実装難易度・パフォーマンス比較）
項目
PySide6 + QtWebEngine
Tauri v2 + WebviewWindow
言語・エコシステム
Python（LLM連携・非同期処理に最適）
Rust + React/TS（型安全・メモリ効率◎）
バイナリサイズ
~180MB（QtWebEngine + Chromium）
~15MB + libwebkit2gtk（システム依存）
メモリ使用量
250~400MB（サービス数に比例）
150~250MB（webkit2gtkプロセス共有）
Googleログイン
◎（Chromium準拠）
△（UA/CSP設定依存、不安定）
セッション分離
◎（QWebEngineProfileで完全分離）
◯（CookieManager + Storageパーティション管理）
UI実装難度
中（Reactを静的ファイル化しQWebEngineViewで読み込み、QWebChannelで双方向通信）
高（Rust側でWebviewWindow生成・位置同期・イベントブリッジ）
クロスプラットフォーム
◯（Linux/Win/Mac対応、WinはQtWebEngineが安定）
◎（公式ビルドパイプライン完備）
ライセンス
LGPLv3（動的リンク・プロセス分離でMIT準拠可能）
Apache-2.0/MIT（クリーン）
👉 トレードオフの整理：
機能確実性・開発速度・LLM統合の相性を優先 → PySide6 + QtWebEngine
軽量性・Rust資産・配布サイズを最優先 → Tauri v2（ただしGoogleログインは妥協またはハイブリッド化が必要）
4. 他に見落としている/検討すべき選択肢
選択肢
評価
備考
pywebview (backend: qt)
◎
QWebEngineをラップし、Python↔JS通信を標準化。UIはReact/Vueのまま維持可能
Tauri + ローカルChromiumプロキシ
△
通常サービスはTauri内、Google系のみsubprocessで別Chromium起動。実装が複雑化
CEF Python / rust-cef
✕
メンテナンス終了傾向・ビルド困難・バイナリ肥大
Slint / Sciter / Luna
✕
Chromium非採用のためGoogleログイン未解決
Electron系（NW.js, Photon）
✕
要件「非Electron」に抵触
👉 見落としがちな最有力候補：
pywebview + qt バックエンド です。
QtWebEngineの恩恵を受けつつ、Python側でセッション分離・LLM連携を一元管理
フロントエンドは既存のReact/TS/Viteビルド成果物をpywebviewのhttp_serverまたはlocal_fileでそのまま読み込み可能
window.pywebview.api経由でRust/Pythonのロジックを直接呼び出せるため、ブリッジ実装が大幅に簡略化
5. セッション分離 × Googleログインを両立する最簡実装
QWebEngineProfileを用いたサービス単位のプロファイル分離が最も確実です。
最小実装イメージ（Python + QtWebEngine）
python
1234567891011121314151617181920212223242526from PySide6.QtCore import QUrlfrom PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePagefrom PySide6.QtWebEngineWidgets import QWebEngineViewfrom PySide6.QtWidgets import QApplication, QMainWindowclass ServiceWebView(QWebEngineView):    def __init__(self, service_id: str, parent=None):        super().__init__(parent)        # サービスごとに独立したCookie/Storage/Cacheプロファイル        profile = QWebEngineProfile(f"ink_hub_{service_id}")        profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)                # Googleログイン用UA/CSP対策（必要に応じて調整）        profile.httpUserAgentChanged.connect(lambda ua: print(f"UA: {ua}"))                page = QWebEnginePage(profile, self)        self.setPage(page)        self.load(QUrl("https://accounts.google.com"))if __name__ == "__main__":    app = QApplication([])    win = QMainWindow()    win.resize(1024, 768)    win.setCentralWidget(ServiceWebView("youtube"))    win.show()    app.exec()
React UIとの連携方法
Viteでnpm run build → dist/ を出力
Python側で pywebview.create_window("Ink Hub", url="dist/index.html", backend="qt")
window.pywebview.api.set_session_data() 等でRust/Pythonロジックを呼び出し
LLM連携は asyncio + httpx/ollama ライブラリで非同期ストリーミング処理
🎯 推奨ロードマップ
mermaid





Code
Preview
即実行すべきこと（1週間以内）
WEBKIT_DISABLE_COMPOSITING_MODE=1 cargo tauri dev で黒画面解消するか検証
pip install PySide6 pywebview → 上記最小コードで YouTube/Googleログイン成功を確認
/usr/bin/time -v で両者の Max resident set size と Elapsed time を計測
pywebview で既存React UIがそのまま動くかプロトタイピング
💡 最終判断の指針
優先事項
推奨スタック
理由
Googleログイン確実突破 + LLM統合 + 開発速度
PySide6/pywebview + QtWebEngine
Chromium互換・Pythonエコシステム・セッション分離が標準搭載
配布サイズ最小 + Rust堅牢性 + Tauri資産継続
Tauri v2 + WebviewWindow
軽量だがGoogleログインは不安定・実装工数大
ハイブリッド（軽量化＋確実性）
Tauri UI + pywebviewサブプロセス
複雑だが両立可能。v1.0以降の最適化フェーズで検討
📌 Ink Inc. のビジョン「AIによる創造、人によるケア」を実現するには、技術選定は「完璧な軽量化」より「持続可能な開発フロー」を優先すべきです。PySide6/QtWebEngine は LGPLv3 ですが、動的リンク・プロセス分離・ソースコード公開を徹底すればMIT準拠のOSS配布は可能です。まずは pywebview + QWebEngineProfile で1サービスのログイン・セッション分離を実証し、データで判断することをお勧めします。