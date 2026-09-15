# app/ 旧実装 要約（削除前メモ）

2026-09-15 の監査で、`app/`（`python3 -m app` 起動）はルート実装（`main.py` /
`api.py` / `bridge.py` / `electron_bridge.py` + `frontend/`）とは別系統の、
**Electronを一切使わない純正Qt実装**であることが判明。README.md の説明とも
食い違っており、混乱を避けるため削除した。将来ルート側にタブ機能等を
移植する際の参考用に、構成だけここに残す。

## 全体設計

- pywebview / React を使わず、`QMainWindow`（[main_window.py](app/main_window.py)）
  1枚に全UIをネイティブQtウィジェットで実装していた。
- 「通常サービスはQtWebEngineをアプリ内に埋め込み、Google系サービスだけは
  実Chromium（システムのChromium/Chrome）をアプリ内に埋め込む」という
  二段構え。ルート実装の「サービスごとにQt/Electronを選べる」方式とは
  設計思想が異なる（Electronという第三のエンジンは存在しない）。

## ファイル構成と役割

| ファイル | 役割 |
|---|---|
| `main.py` | エントリポイント。単一インスタンスロック（QLockFile）あり。 |
| `main_window.py` | メインウィンドウ本体。`closeEvent`でLocalStorageバックアップ→終了の安全策を実装済み（4秒の保険タイマーあり）。 |
| `webview_manager.py` | サービスごとのQWebEngineProfile管理（セッション分離）、子タブ生成、Google向けUA/Client Hints偽装。 |
| `chrome_embed.py` | Google系サービス用に実Chromium(Ecosia等)をアプリ内埋め込み。プロファイル二重起動防止・残留プロセス掃除ロジックあり。 |
| `tab_manager.py` | **1サービス内で複数タブを開く機能の中核。** 親タブ+子タブのデータモデルとシグナル管理。ルート実装には対応物が存在しない。 |
| `tab_strip.py` | タブ帯（サイドの縦タブUI）の描画。子タブがあるときだけ表示。 |
| `sidebar.py` | ネイティブQtによるサービス一覧（グループ折りたたみ・DnD・ファビコン）。ReactのSidebar.tsxと機能的に重複するQt版。 |
| `settings_dialog.py` | 設定ダイアログ（一般/AI・LLM/グループ/データタブ）。`from auth import ...`の残骸あり（try/exceptでフォールバックしており実害なし）。 |
| `session_backup.py` | Discordのメールログイン等、LocalStorageのtokenをJSONへバックアップ/復元。QtWebEngineが終了タイミングによってはLSをディスクに書ききらない問題への対策。 |
| `browser_launcher.py` | システム上のChromium系ブラウザ検出・プロファイルパス解決。`chrome_embed.py`と共有。 |
| `favicon_cache.py` | Google Favicon APIでアイコン取得・ローカルキャッシュ。 |
| `aide_panel.py` | 右パネルのAIアシスタント（旧InkAide.tsx相当）。 |
| `auth_popup.py` | OAuthポップアップ。親と同じQWebEngineProfileを使い、親タブをURL上書きしない設計（白画面・セッション破壊防止）。 |
| `styles.py` | ダークテーマ共通スタイル。 |

## ルート実装への移植を検討する際のポイント

- **タブ機能**: `tab_manager.py`のデータモデル（親タブ/子タブ、`strip_tabs`の
  表示ルール＝子が1つもなければ帯を出さない）はそのまま参考にしやすい設計。
  ルート実装で同等機能を作る場合、Python側は`TabManager`相当のクラスを
  `api.py`/`bridge.py`に追加し、フロントは`frontend/src`に新規タブ帯コンポー
  ネントを作る必要がある（Reactに直接移植できるコードはない）。
- **LocalStorageバックアップ**（`session_backup.py`）: QtWebEngine終了時の
  データロスト対策として、ルート実装（Qtエンジン使用時）でも同様の問題が
  起きうるなら参考になる。
- **Google埋め込み**（`chrome_embed.py`）: ルート実装はQtWebEngine自体を
  Google向けエンジンとして使っており、実Chromium埋め込みは採用していない。
  必要になった場合の実装例として参照可。
