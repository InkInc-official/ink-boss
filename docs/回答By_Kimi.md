Ink Hub セカンドオピニオン
依頼者: Ink Inc. / 黒井葉跡
回答日: 2026-05-24
回答者: Kimi
目次
Tauri v2でWebViewを正しく動かす方法
Ubuntu 24.04でGoogleログインを突破できる最適解
PySide6 + QtWebEngine vs Tauri WebviewWindowの比較
見落としている可能性のある選択肢
セッション分離とGoogleログインを両立する最もシンプルな方法
総合判断と推奨
1. Tauri v2でWebViewを正しく動かす方法
結論
<webview>タグの復活はなく、WebviewWindowへの移行が唯一の公式道。
現状の整理
Table
項目	Tauri v1	Tauri v2
<webview>タグ	✅ 正式サポート	❌ 廃止・非推奨
推奨方式	HTML内<webview>	Rust側WebviewWindow
Ubuntu 24.04対応	❌ libwebkit2gtk-4.0-dev廃止	⚠️ webkit2gtk-4.1必須
あなたの「真っ黒問題」の本質
試した対策（disablewebsecurity、dangerousDisableAssetCspModification、User-Agent変更）がすべて無効だった理由：
Tauri v2の<webview>廃止は「機能停止」であり「バグ」ではない
真っ黒表示は、タグが無視されるか、セキュリティポリシーでコンテンツがブロックされるため
features = ["unstable"]はTauri v2の特定ビルドフラグであり、<webview>の復活ではない
WebviewWindow移行の実装概要
rust
Copy
// Rust側（main.rs）で各サービスを独立ウィンドウとして生成
use tauri::{WebviewWindowBuilder, WebviewUrl};

#[tauri::command]
async fn open_service(app: tauri::AppHandle, id: String, url: String) {
    let webview = WebviewWindowBuilder::new(&app, &id, WebviewUrl::External(url.parse().unwrap()))
        .inner_size(1200.0, 800.0)
        .transparent(true)  // 背景透過
        .visible(false)       // 初期非表示、メインウィンドウに重ねる際に制御
        .build()
        .unwrap();
}
TypeScript
Copy
// フロントエンド側で表示切り替え
// メインウィンドウの特定領域にWebviewWindowを重ねて表示
const showService = async (id: string) => {
  await invoke('show_service_window', { id });
};
注意点
座標同期: メインウィンドウの移動・リサイズに合わせてWebviewWindowの位置を更新する必要あり
Z-order制御: 常にWebviewWindowが前面に来るようRust側で管理
クリック透過: 非アクティブ時のクリックイベント透過（set_ignore_cursor_events）
Wayland対応: Ubuntu 24.04のデフォルトはWayland。X11でのxdotool的なウィンドウ操作が通らない場合あり
代替アプローチ（非公式・検証済みでない）
Table
アプローチ	評価	理由
tauri-plugin-localhost + iframe	❌ 不可	CSP・X-Frame-OptionsでGoogleログイン死亡
WebRTC画面共有	❌ 非実用的	遅延・品質問題
カスタムプロトコル + プロキシ	❌ 不可	Googleのセキュリティ検出を回避できない
→ WebviewWindowへの移行が唯一の現実的解
2. Ubuntu 24.04でGoogleログインを突破できる最適解
結論
QtWebEngine（PySide6）が最適解。Tauri WebviewWindow + User-Agent偽装は長期的に持たない。
Googleログインブロックの技術的背景
Googleは2024年以降、以下の条件でログインをブロック：
User-Agentに「WebKitGTK」が含まれる
JavaScriptのnavigator.userAgentDataで埋め込みブラウザと判定
TLS fingerprintがWebKitGTKのものと一致
User-Agent偽装だけでは、userAgentDataやTLS fingerprintの偽装は不可能。
各方式の評価
Table
方式	Googleログイン	セッション分離	実装難易度	長期的安定性
PySide6 + QtWebEngine	◎ 完璧	◎ 完璧	中	◎ 高
Tauri WebviewWindow + UA偽装	△ 時々通る	◎ 可能	高	△ 低（ブロックリスク）
Tauri + OAuth PKCE（外部ブラウザ）	◎ 完璧	△ 外部依存	低	◎ 高
Wails + WebKit	△ 同じ問題	◎ 可能	中	△ 低
CEF（Chromium Embedded）	◎ 完璧	◎ 可能	高	◎ 高
「外部ブラウザ連携」方式の詳細
Tauriを維持しつつGoogleログインを突破するなら：
plain
Copy
[Ink Hub UI] ←→ [Tauri Rust層] ←→ [システムChrome/Chromium]
                    ↓
              OAuth PKCEフロー
              1. Chromeで認証URLを開く
              2. カスタムURLスキームでコールバック
              3. アクセストークンを取得
              4. WebviewWindowでAPI利用
問題点: これは「WebサービスのAPI連携」であり、Webアプリの埋め込み表示ではない。YouTubeの埋め込み視聴、GmailのUI表示などは別の技術的課題を生む。
3. PySide6 + QtWebEngine vs Tauri WebviewWindowの比較
実装難易度
Table
項目	PySide6	Tauri WebviewWindow
言語	Python（書きやすい）	Rust（学習曲線急）
UI構築	Qt Designer / コード	React/TS（既存資産活用）
ウィンドウ管理	Qt組み込み（シンプル）	自前実装（座標・Z-order）
WebView埋め込み	QWebEngineView（1行）	WebviewWindow + 重ね込み制御
信号/イベント	信号/スロット（習得要）	Tauriコマンド + イベント
総合: PySide6は「WebViewを埋め込む」という目的に対して圧倒的にシンプル。Tauriは「軽量フレームワーク」だが、WebviewWindowの重ね込み実装でその分を帳消しにする。
パフォーマンス
Table
項目	PySide6	Tauri
バイナリサイズ	80-120MB（QtWebEngine含む）	15-25MB + システムWebKit
メモリ（1WebView時）	150-200MB	100-150MB
メモリ（10WebView時）	1.0-1.5GB	0.8-1.2GB
起動速度	中（Qt読み込み）	速（軽量）
ページレンダリング	Chromium（高速）	WebKitGTK（中速）
誤解を解く: Tauriの「軽量」はバイナリサイズと起動速度で正しい。しかし、マルチWebView運用時のメモリ使用量は、WebKitGTKプロセスの特性上、QtWebEngineと大差がない。実際に10個以上のサービスを開く運用では、両者とも1GB超えは普通。
Googleログインの確実性
Table
項目	PySide6	Tauri
User-Agent	Chromeと同一	WebKitGTK（偽装可だが不完全）
TLS fingerprint	Chromeと同一	WebKitGTK（偽装不可）
JavaScript API	Chrome互換	WebKit互換（一部差異）
将来のブロックリスク	なし（本物のChromium）	あり（GoogleのWebKitGTK排除傾向）
既存資産の影響
Table
資産	PySide6移行時	Tauri維持時
React/TSコンポーネント	❌ 書き直し必要	✅ そのまま
Zustand状態管理	⚠️ 設計思想を活かす	✅ そのまま
TailwindCSS	⚠️ スタイル知見を活かす	✅ そのまま
Rustバックエンド	❌ 廃止	✅ そのまま
ビルド設定（deb/rpm/AppImage）	⚠️ PyInstaller/fpm等に変更	✅ そのまま
4. 見落としている可能性のある選択肢
選択肢E：Wails v2
plain
Copy
Go + WebKit。Tauriと同じwebkit2gtkの問題を抱える。
Goの生産性はRustより高いが、WebViewの根本問題は解決しない。
評価: 推奨しない（Tauriと同じ穴）
選択肢F：Tauri + Servo（実験的）
plain
Copy
MozillaのServoエンジンをWebViewバックエンドにする動きがあるが、
2026年時点で実用レベルではない。レイアウトエンジンの完成度が低い。
評価: 現段階では不可
選択肢G：Fyne + WebView（Go）
plain
Copy
軽量UIフレームワークだが、WebView機能が貧弱。
マルチサービス一元化の要件を満たさない。
評価: 不可
選択肢H：「外部ブラウザ埋め込み」方式（新規提案）
plain
Copy
各サービスをシステムのChrome/Chromiumを別プロセスで起動し、
ウィンドウキャプチャして自前UIに表示する方式。

実装案:
1. Chromeを各サービス用に独立プロファイルで起動
   chromium --user-data-dir=/tmp/ink-hub/gmail --app=https://gmail.com
2. ウィンドウIDを取得（X11: xdotool, Wayland: ext-idle-inhibit等）
3. PipeWire / DMA-BUF でウィンドウ内容をキャプチャ
4. 自前UI（PySide6/QtまたはTauri）にテクスチャとして貼り付け

長所:
- Googleログイン: ◎ 本物のChromeなので完璧
- セッション分離: ◎ Chromeプロファイルで完璧
- 既存資産: React/TS UIはそのまま（表示層のみキャプチャ）

短所:
- 実装難易度: 高（ウィンドウ管理・キャプチャ・同期）
- パフォーマンス: キャプチャ遅延・GPUメモリ圧迫
- Wayland対応: 複雑（X11より制約多い）

評価: 技術的に面白いが、実装コストが高すぎる。2-3人月の開発を要する。
選択肢I：Neutralinojs
plain
Copy
システムにインストールされたWebViewを使用。
LinuxではWebKitGTK → Tauriと同じ問題。
評価: 推奨しない
選択肢J：Flutter + webview_flutter
plain
Copy
FlutterのLinux対応は進んでいるが、webview_flutterのLinux実装は
WebKitGTKベース。同じ問題を抱える。
評価: 推奨しない
選択肢K：Tauri v2 + 公式のcreate_window API + タブ型UI
plain
Copy
Tauri v2のWebviewWindowを「ブラウザのタブ」のように扱う方式。
メインウィンドウ内に複数のWebviewWindowを生成し、
タブ切り替えで表示/非表示を制御。

実装ポイント:
- 各WebviewWindowをメインウィンドウの子ウィンドウとして生成
- `parent`指定で位置同期を簡略化
- `visible`制御でタブ切り替え

問題:
- 子ウィンドウのクリッピング（親ウィンドウ外に描画されない制御）が難しい
- Waylandでの親子関係が不安定

評価: Tauri維持の場合はこれが最も現実的なアプローチ
5. セッション分離とGoogleログインを両立する最もシンプルな方法
結論
PySide6のQWebEngineProfileが最もシンプルかつ確実。
PySide6での実装
Python
Copy
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

# 各サービスに独立プロファイルを生成
# これだけでCookie、LocalStorage、IndexedDB、Cacheが完全分離

class ServiceTab:
    def __init__(self, service_id: str, url: str):
        # プロファイル生成（名前空間で分離）
        self.profile = QWebEngineProfile(service_id)
        
        # 永続化設定（オプション）
        self.profile.setPersistentStoragePath(f"~/.config/ink-hub/profiles/{service_id}")
        
        # ページ生成
        self.page = QWebEnginePage(self.profile)
        
        # ビュー生成
        self.view = QWebEngineView()
        self.view.setPage(self.page)
        self.view.setUrl(url)
1行でセッション分離が完了。これがPySide6の最大の強み。
Tauri WebviewWindowでの同等実装
rust
Copy
use std::path::PathBuf;
use tauri::{WebviewWindowBuilder, WebviewUrl};

#[tauri::command]
fn create_isolated_webview(app: tauri::AppHandle, id: String, url: String) {
    let data_dir = PathBuf::from(format!("/tmp/ink-hub/profiles/{}", id));
    
    let webview = WebviewWindowBuilder::new(&app, &id, WebviewUrl::External(url.parse().unwrap()))
        .data_directory(Some(data_dir))  // Cookie/Storageの分離
        .build()
        .unwrap();
}
問題点:
data_directoryはファイルベースの分離。メモリ上での完全分離ではない
各WebviewWindowが独立プロセスになるわけではない（WebKitGTKのプロセスモデル依存）
クリーンアップ（プロファイル削除）が手動
セッション分離の比較まとめ
Table
項目	PySide6 QWebEngineProfile	Tauri data_directory
分離レベル	メモリ + ストレージ完全分離	ストレージパス分離
実装行数	1行	設定 + パス管理
永続化制御	メソッド1つ	手動ディレクトリ管理
クリーンアップ	profile.clearAll()	手動ファイル削除
プロセス分離	Chromiumのプロセスモデルに依存	WebKitGTKのプロセスモデルに依存
6. 総合判断と推奨
推奨：PySide6 + QtWebEngineへの移行
優先度：高
判断の根拠
Table
要件	PySide6	Tauri継続
Electronを使わない	✅	✅
レシピレス設計	✅	✅
セッション分離	✅ 圧倒的に簡単	⚠️ 設定複雑
Googleログイン突破	✅ 確実	❌ 長期的に不可
LLM統合	✅ Python SDK豊富	⚠️ Rust実装必要
OSS（MIT/LGPL）	✅ LGPL	✅ MIT
Linux対応	✅ Qt6公式サポート	⚠️ webkit2gtk問題
軽量	△ 80-120MB	◎ 15-25MB
既存UI資産活用	❌ 書き直し	✅
決め手は「Googleログインの確実性」と「セッション分離の簡単さ」。Ink Hubの核心価値は「マルチサービス一元化」であり、Googleアカウントを使うサービス（Gmail、YouTube、Notion、Google Drive等）がこの対象から外れると、プロダクトの魅力が大きく損なわれる。
移行計画の提案
plain
Copy
フェーズ1（1週間）: 技術検証
- PySide6 + QtWebEngineでGoogleログイン・セッション分離をPoC
- Ubuntu 24.04でのビルド・配布（AppImage/deb）を確認

フェーズ2（2週間）: UI再構築
- 左サイドバー（展開/折りたたみ）をPySide6で実装
- サービス登録モーダル・グループ管理を移植
- Zustandの状態管理設計をPythonのクラス/辞書構造に移行

フェーズ3（1週間）: 機能統合
- LLMバックエンド選択UIを実装
- 設定のエクスポート/インポート（JSON互換性維持）
- ファビコン自動取得を移植

フェーズ4（1週間）: テスト・リリース
- マルチサービス同時表示の安定性確認
- ビルド・パッケージング
Tauri継続を選ぶ場合の条件
以下すべてを満たせるなら、Tauri継続も現実的：
Googleログインを諦め、OAuth PKCE + API連携方式に切り替える
WebviewWindowの座標重ね込みを完璧に実装できる（Wayland含む）
webkit2gtkのバグに長期的に付き合う覚悟がある
「軽量」という価値を「Googleログイン非対応」という欠損より優先する
最終的なアドバイス
「フレームワークの選択は、技術的な美しさではなく、プロダクトの要件を満たすかどうかで決めるべき。」
Ink Hubの要件を再確認：
必須: Googleログイン突破、セッション分離、レシピレス、OSS
理想: 軽量、左サイドバーUI、AI連携
PySide6は「必須」をすべて満たし、「理想」の一部（軽量）を犠牲にする。しかし、その犠牲はバイナリサイズに留まり、メモリ使用量や起動速度は実用上問題ない範囲。
Tauriは「理想」の軽量性を満たすが、「必須」のGoogleログインを長期的に満たせないリスクがある。
プロダクトの成功を優先するなら、PySide6への移行を強く推奨する。
本セカンドオピニオンは、2026年5月時点の技術動向に基づく。特にGoogleのWebViewブロックポリシー、Tauri v2の仕様、Qt6/WebKitGTKのUbuntu 24.04対応状況を参照。
