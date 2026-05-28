# Ink Boss 仕様書 v2.0
## Ink Inc. / 黒井葉跡

---

## 1. プロダクト概要

| 項目 | 内容 |
|---|---|
| プロダクト名 | Ink Boss |
| 旧称 | Ink Hub（v1.0、Tauri版） |
| 種別 | デスクトップアプリケーション（マルチサービス一元化ツール） |
| コンセプト | レシピ不要・URL登録だけで全サービスを一元管理する次世代ワークスペース |
| 開発元 | Ink Inc. / 黒井葉跡 |
| 対象ユーザー | 多数のWebサービスを一元管理したいユーザー・OSSコミュニティ |
| フレームワーク | pywebview + PySide6 + QtWebEngine + React/TypeScript |
| 対応OS | Linux（v2.0）→ Windows・Mac（将来対応） |
| ライセンス | MIT（pywebview/PySide6はLGPL、動的リンクで互換） |
| ステータス | PoC完了（Gmail突破・セッション分離確認済み） |

---

## 2. なぜTauriからpywebviewに移行したか

### Tauri v2の構造的問題

```
問題① <webview>タグがTauri v2で廃止
  └── WebView表示が真っ黒になる根本原因

問題② webkit2gtkはGoogleにブロックされる
  └── User-Agent偽装でも回避不可能
  └── TLS fingerprint・JS実行環境まで検査される
  └── FerdiumがGoogleログインできない理由と同じ

問題③ Ubuntu 24.04でTauri v1が動かない
  └── libwebkit2gtk-4.0-devが廃止済み
```

### 12AIによるセカンドオピニオンの結論

```
12AI中10AI → PySide6 + QtWebEngine推奨
根拠：
  - QtWebEngineはChromiumベース
  - Googleログインが確実に通る
  - QWebEngineProfileでセッション分離が1行で完了
  - Pythonで既存資産（Ink Memory等）と統一できる
```

### PoCで確認済みの事実

```
✅ Gmail（Googleログイン）突破確認
✅ Discord同時表示確認
✅ セッション分離（独立Cookie/Storage）確認
✅ Ubuntu 24.04での動作確認
```

---

## 3. Ferdiumとの差別化

| 機能 | Ferdium | Ink Boss |
|---|---|---|
| レシピ | 必要 | **不要** |
| フレームワーク | Electron（重い） | **pywebview + QtWebEngine** |
| Googleログイン | ❌ 不可 | **✅ 完全対応** |
| LLM統合 | なし | **3択対応** |
| セッション分離 | 対応 | **QWebEngineProfileで完璧** |
| OSSの綺麗さ | レシピ依存で複雑 | **クリーン** |
| 開発言語 | JavaScript/TypeScript | **Python + TypeScript** |

> 「Operaのariaを、すべてのサービスで。どのサービスでも、AIが読んでくれる。」

---

## 4. 技術スタック

### 4.1 アーキテクチャ

```
┌─────────────────────────────────────────────┐
│  Ink Boss                                    │
├─────────────────────────────────────────────┤
│  フロントエンド（React + TypeScript + Vite） │
│  ← 旧Ink Hub資産をそのまま流用              │
├─────────────────────────────────────────────┤
│  ブリッジ（pywebview）                       │
│  Python ↔ JavaScript通信を担当              │
├─────────────────────────────────────────────┤
│  バックエンド（Python）                      │
│  セッション管理・LLM連携・設定管理           │
├─────────────────────────────────────────────┤
│  WebViewエンジン（QtWebEngine / Chromium）   │
│  Googleログイン突破・完全セッション分離      │
└─────────────────────────────────────────────┘
```

### 4.2 スタック詳細

| レイヤー | 技術 |
|---|---|
| WebViewエンジン | QtWebEngine（Chromiumベース） |
| ブリッジ | pywebview |
| UIフレームワーク | PySide6 |
| フロントエンド | React + TypeScript + Vite |
| スタイリング | TailwindCSS |
| 状態管理 | Zustand |
| バックエンド | Python 3.x |
| セッション管理 | QWebEngineProfile（サービスごとに完全独立） |
| 設定保存 | JSON（ローカルファイル） |
| LLM連携 | Ollama API / Anthropic API / Gemini API |
| 配布 | PyInstaller → AppImage / deb |

### 4.3 セッション分離の実装方針

```python
# サービスごとに独立したプロファイルを生成
profile = QWebEngineProfile(service_id, app)
page = QWebEnginePage(profile, app)
view = QWebEngineView()
view.setPage(page)
view.setUrl(QUrl(service_url))

# これだけでCookie・LocalStorage・IndexedDB・Cacheが完全分離
# アプリ再起動後もセッションが維持される
```

---

## 5. 機能一覧

### 5.1 コア機能（v2.0実装予定）

| 機能 | 内容 |
|---|---|
| サービス登録 | URL・名前・アイコンを手動入力して登録 |
| WebView表示 | QtWebEngineで表示（Googleログイン対応） |
| セッション分離 | QWebEngineProfileでサービスごとに完全独立 |
| 左サイドバー | 登録サービスをアイコン+名前で縦に並べる |
| タブ切り替え | サイドバークリックでサービスを切り替え |
| グループ管理 | サービスをグループでまとめる |
| グループ名変更 | ダブルクリックでその場編集 |
| サービス移動 | 右クリック→別グループへ移動 |
| サービスコピー | 同じURLを複数グループに独立セッションで登録 |
| ドラッグ&ドロップ | サービスをグループに直接ドロップ |
| 設定エクスポート/インポート | JSON形式で設定を保存・復元 |
| トレイ常駐 | 最小化時にシステムトレイに格納 |

### 5.2 グループ・サービス操作仕様

**サービス右クリックメニュー**
```
┌─────────────────────┐
│ 編集                │
│ グループに移動    ▶ │
│ グループにコピー  ▶ │
│ ─────────────────── │
│ 削除                │
└─────────────────────┘
```

**グループヘッダー**
```
┌──────────────────────────┐
│ ▼ SNS   ✏️  ＋  🗑️       │
└──────────────────────────┘
  ↑ダブルクリックで名前編集
```

**グループ削除時の選択**
```
「サービスごと削除」
または
「グループ解除してルートへ移動」
```

**コピー登録の仕様**
```
同じURLを複数グループに登録する場合
└── service_idは別々に発行
└── セッションも独立（完全に別サービスとして扱う）
```

### 5.3 LLM統合機能（v2.0実装予定）

```
LLMバックエンド（3択）
├── Ollama（ローカル）← デフォルト・無料・完全オフライン
├── Claude API       ← 高精度・従量課金・ユーザー自前キー
└── Gemini API       ← 無料枠あり・取得容易・ユーザー自前キー
```

| 優先度 | 機能 | 内容 |
|---|---|---|
| 高 | 翻訳パネル | 選択テキスト→日本語をサイドパネルに表示 |
| 高 | ページ要約 | 表示中ページをLLMで3行要約 |
| 中 | コマンドパレット | Ctrl+Kで自然言語操作 |
| 中 | 通知サマリー | 全サービスの状態をAIが定期まとめ |
| 低 | Ink Memory連携 | マネジメントシステムとのデータ連携 |

### 5.4 将来機能（v3.0以降）

| 機能 | 優先度 |
|---|---|
| Windows対応 | 高 |
| Mac対応 | 中 |
| WebDAV/Nextcloud同期 | 中 |
| ワークスペース横断レポート | 低 |

---

## 6. UI設計

### 6.1 基本レイアウト

```
┌─────────────────────────────────────────┐
│  タイトルバー                             │
├──────┬──────────────────────────────────┤
│      │  URLバー                          │
│ サイド├──────────────────────────────────┤
│ バー  │                                  │
│      │       WebViewエリア               │
│ アイ  │     （QtWebEngine表示）           │
│ コン  │                                  │
│ 一覧  │                                  │
│      │                                  │
├──────┤                                  │
│  ＋  │                                  │
│ 設定  │                                  │
└──────┴──────────────────────────────────┘
```

### 6.2 カラーテーマ

| トークン | 値 | 用途 |
|---|---|---|
| ink-bg | #0a0a0f | 背景 |
| ink-surface | #12121a | サイドバー・モーダル背景 |
| ink-border | #1e1e2e | ボーダー |
| ink-muted | #2a2a3e | ホバー背景 |
| ink-accent | #c0392b | アクセント・ボタン |
| ink-gold | #d4a017 | ゴールドアクセント |
| ink-text | #e8e8f0 | メインテキスト |
| ink-subtext | #8888aa | サブテキスト |

---

## 7. フォルダ構成（予定）

```
ink-boss/
├── main.py                   ← Pythonエントリーポイント
├── requirements.txt          ← Python依存関係
├── package.json              ← フロントエンド依存関係
├── vite.config.ts
├── tailwind.config.js
├── README.md
│
├── public/
│   ├── icon.png              ← Ink Bossライオンアイコン
│   └── banner.png            ← GitHub README用バナー
│
├── src/                      ← Reactフロントエンド（旧ink-hub資産）
│   ├── main.tsx
│   ├── App.tsx
│   ├── styles.css
│   ├── components/
│   │   ├── Sidebar.tsx
│   │   ├── WebViewArea.tsx
│   │   ├── ServiceModal.tsx
│   │   ├── GroupContextMenu.tsx  ← 新規
│   │   └── SettingsModal.tsx
│   ├── store/
│   │   └── index.ts
│   └── types/
│       └── index.ts
│
└── backend/
    ├── webview_manager.py    ← QWebEngineProfile管理
    ├── session_manager.py    ← セッション永続化
    ├── llm/
    │   ├── ollama.py
    │   ├── claude.py
    │   └── gemini.py
    └── config.py             ← 設定JSON管理
```

---

## 8. 開発ロードマップ

### Phase 1（環境構築・基本動作）
- [ ] ink-bossフォルダ作成・依存関係整備
- [ ] pywebview + PySide6でメインウィンドウ表示
- [ ] Reactフロントエンドの読み込み確認
- [ ] Python ↔ JavaScript通信確認

### Phase 2（コア機能実装）
- [ ] サービス登録・WebView表示
- [ ] セッション分離（QWebEngineProfile）
- [ ] 左サイドバー・タブ切り替え
- [ ] グループ管理（作成・名前変更・削除）
- [ ] サービス移動・コピー・ドラッグ&ドロップ
- [ ] 設定のエクスポート/インポート

### Phase 3（LLM統合）
- [ ] Ollamaとの接続・翻訳パネル
- [ ] ページ要約機能
- [ ] Claude API / Gemini API対応
- [ ] バックエンド切り替えUI

### Phase 4（仕上げ・配布）
- [ ] ダーク/ライトテーマ
- [ ] トレイ常駐
- [ ] PyInstallerでビルド
- [ ] AppImage / debパッケージング
- [ ] GitHub Releasesで公開

---

## 9. ライセンス・配布方針

| 項目 | 内容 |
|---|---|
| ライセンス | MIT |
| pywebview / PySide6 | LGPL（動的リンクでMIT互換） |
| 配布場所 | GitHub Releases |
| パッケージ形式 | AppImage / .deb（Linux v2.0） |
| APIキー | ユーザー自身が用意・運営側は一切保持しない |

---

## 10. 変更履歴

| バージョン | 内容 |
|---|---|
| v1.0 | Tauri v2 + React/TSで開発開始・ビルド成功 |
| v1.1 | WebView真っ黒問題発覚・12AIセカンドオピニオン実施 |
| v2.0 | pywebview + QtWebEngineに移行・Gmail突破確認・Ink Bossに改名 |

---

*Ink Boss 仕様書 v2.0 - Ink Inc. / 黒井葉跡*
