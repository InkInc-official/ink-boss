# Ink Hub 仕様書 v1.1
## Ink Inc. 所長・黒井葉跡

---

## 1. プロダクト概要

| 項目 | 内容 |
|---|---|
| プロダクト名 | Ink Hub |
| 種別 | デスクトップアプリケーション（マルチサービス一元化ツール） |
| コンセプト | レシピ不要・URL登録だけで全サービスを一元管理する次世代ワークスペース |
| 開発元 | Ink Inc. / 黒井葉跡 |
| 対象ユーザー | 多数のWebサービスを一元管理したいユーザー・OSSコミュニティ |
| フレームワーク | Tauri v2（Rust + TypeScript + React） |
| 対応OS | Linux（v1.0）→ Windows・Mac（将来対応） |
| ライセンス | MIT |
| ステータス | v1.0 ビルド済み・動作確認済み |

---

## 2. 設計思想

### 2.1 レシピレス設計

既存の一元化アプリ（Ferdium・Rambox等）はサービスごとの「レシピ（定義ファイル）」を大量に抱える。
各サービスのUI変更のたびにレシピが壊れ、メンテナンスコストが開発者を圧迫し、プロジェクトの停滞・終了を招く。

Ink Hubはこの構造を根本から排除する。

```
従来の一元化アプリ
└── レシピ（サービス定義ファイル）を大量に抱える
    └── サービス変更 → レシピ破損 → メンテ負担 → 停滞・終了

Ink Hub
└── 全サービスをCustom WebViewとして扱う
    └── URLさえ生きていれば動き続ける
    └── メンテコストほぼゼロ
```

### 2.2 OSSとして成立する設計

- サービス固有のコードを一切含まない
- ライセンス問題が発生しない
- コードベースが小さく保たれ、フォークしやすい
- コントリビューターが「レシピ職人」ではなく「機能開発者」になれる

### 2.3 Ferdiumとの差別化

| 機能 | Ferdium | Ink Hub |
|---|---|---|
| レシピ | 必要 | **不要** |
| フレームワーク | Electron（重い） | **Tauri（軽量）** |
| LLM統合 | なし | **3択対応** |
| ページ要約・翻訳 | なし | **実装予定** |
| OSSの綺麗さ | レシピ依存で複雑 | **クリーン** |
| 同期 | 専用サーバーあり | JSON出力で代替 |

> 「Operaのariaを、すべてのサービスで。どのサービスでも、AIが読んでくれる。」

### 2.4 Inkシリーズにおける位置づけ

```
Ink Hub      → マルチサービス一元化デスクトップアプリ（本プロダクト）
Ink Memory   → マネジメント記録システム（Streamlit/Python）
Ink Canvas   → AI画像生成スタジオ（Web）
Ink Atelier  → ローカルAIイラスト生成（ComfyUI）
Ink Check    → ストレスチェックシステム（Notionフォーム）
Ink Triage   → メンタルケア記録システム（Memos/Docker）
```

### 2.5 AI統合の思想

APIキーはユーザー自身が用意する方式。
運営側（Ink Inc.）のキーは一切使用しない。
これによりOSSとして配布してもクリーンな状態を保つ。

---

## 3. 機能一覧

### 3.1 コア機能（v1.0実装済み）

| 機能 | 内容 |
|---|---|
| サービス登録 | URL・名前・アイコンを手動入力して登録 |
| WebView表示 | 登録したURLをWebViewで表示 |
| セッション分離 | 各サービスのCookie・ログイン状態を独立管理 |
| 左サイドバー | 登録サービスをアイコン+名前で縦に並べる（展開/折りたたみ対応） |
| タブ切り替え | サイドバークリックでサービスを切り替え |
| グループ管理 | サービスをグループ（ワークスペース）でまとめる |
| トレイ常駐 | 最小化時にシステムトレイに格納 |
| 設定のエクスポート/インポート | 登録サービス一覧をJSON形式で保存・復元 |

### 3.2 LLM統合機能（v1.0設定のみ・機能実装はv1.1予定）

LLMバックエンドは設定画面で以下の3択から選択する。

```
LLMバックエンド
├── Ollama（ローカル）← デフォルト・無料・完全オフライン
├── Claude API       ← 高精度・従量課金・ユーザー自前キー
└── Gemini API       ← 無料枠あり・取得容易・ユーザー自前キー
```

### 3.3 AI機能（v1.1実装予定・優先順）

| 優先度 | 機能 | 内容 |
|---|---|---|
| 高 | 翻訳パネル | 選択テキストを右クリック→「AIで翻訳」でサイドパネルに日本語表示 |
| 高 | ページ要約 | 表示中WebViewのテキストをLLMで3行要約 |
| 中 | コマンドパレット | Ctrl+Kで自然言語操作「Notionを開いて」等 |
| 中 | 通知サマリー | 全サービスの状態をAIが定期まとめ |
| 低 | Ink Memory連携 | マネジメントシステムとのデータ連携 |

### 3.4 将来機能（v2.0以降）

| 機能 | 優先度 | 内容 |
|---|---|---|
| Windows対応 | 高 | Tauriのクロスプラットフォームビルド |
| Mac対応 | 中 | 同上 |
| WebDAV/Nextcloud同期 | 中 | セルフホストサーバーとの設定同期 |
| ドラッグ&ドロップ並び替え | 中 | サービスの順番を直感的に変更 |
| 通知バッジ | 中 | サービスごとの未読数表示 |

---

## 4. UI設計

### 4.1 基本レイアウト

```
┌─────────────────────────────────────────┐
│  タイトルバー（ウィンドウ操作）               │
├──────┬──────────────────────────────────┤
│      │                                  │
│ サイド│                                  │
│ バー  │       WebViewエリア               │
│      │     （選択中のサービスを表示）        │
│ アイ  │                                  │
│ コン  │                                  │
│ 一覧  │                                  │
│      │                                  │
├──────┤                                  │
│  ＋  │                                  │
│ 追加  │                                  │
└──────┴──────────────────────────────────┘
```

### 4.2 サイドバー仕様

- 幅：60px（アイコンのみ） / 200px（アイコン+名前、展開時）
- クリックで展開/折りたたみ切り替え
- アイコン：ファビコン自動取得 or ユーザーが画像をアップロード
- グループはフォルダアイコンで折りたたみ可能
- 下部に「＋サービス追加」「⚙設定」ボタン常設

### 4.3 空状態（サービス未選択時）

- 中央にInk Hubアイコン（ライオン）を表示
- 「左のサイドバーからサービスを選択するか＋でサービスを追加してください」

### 4.4 カラーテーマ

| トークン | 値 | 用途 |
|---|---|---|
| ink-bg | #0a0a0f | 背景 |
| ink-surface | #12121a | サイドバー・モーダル背景 |
| ink-border | #1e1e2e | ボーダー |
| ink-muted | #2a2a3e | ホバー背景 |
| ink-accent | #c0392b | アクセント・ボタン |
| ink-gold | #d4a017 | ゴールドアクセント（将来） |
| ink-text | #e8e8f0 | メインテキスト |
| ink-subtext | #8888aa | サブテキスト |

### 4.5 フォント

| 用途 | フォント |
|---|---|
| 見出し・ロゴ | Bebas Neue |
| 本文・UI | DM Sans |
| コード・URL | JetBrains Mono |

---

## 5. 技術仕様

### 5.1 スタック

| レイヤー | 技術 |
|---|---|
| デスクトップシェル | Tauri v2 |
| バックエンド | Rust |
| フロントエンド | React + TypeScript + Vite |
| スタイリング | TailwindCSS v3 |
| 状態管理 | Zustand（persist対応） |
| WebView管理 | Tauri WebviewWindow |
| セッション管理 | partition:persist（サービスごとに独立） |
| 設定保存 | JSON（ローカルファイル） |
| LLM連携 | Ollama API / Anthropic API / Gemini API |

### 5.2 セッション分離の実装方針

各サービスに固有のpartition IDを割り当て、Cookie・キャッシュ・ローカルストレージを完全に分離する。

```
サービスA → partition: "persist:service_a"
サービスB → partition: "persist:service_b"
サービスC → partition: "persist:service_c"
```

これにより各サービスのログイン状態がアプリ再起動後も維持される。

### 5.3 設定ファイル形式

```json
{
  "version": "1.0",
  "theme": "dark",
  "llm": {
    "backend": "ollama",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3",
    "claude_api_key": "",
    "gemini_api_key": ""
  },
  "groups": [
    {
      "id": "group_001",
      "name": "SNS",
      "collapsed": false,
      "services": [
        {
          "id": "service_001",
          "name": "Discord",
          "url": "https://discord.com/app",
          "icon": "favicon",
          "muted": false
        }
      ]
    }
  ]
}
```

---

## 6. フォルダ構成

```
ink-hub/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── tailwind.config.js
├── postcss.config.js
├── README.md
│
├── public/
│   ├── icon.png                  ← 起動画面中央のライオンアイコン
│   └── banner.png                ← GitHub README用バナー画像
│
├── src/
│   ├── main.tsx                  ← Reactエントリーポイント
│   ├── App.tsx                   ← ルートコンポーネント
│   ├── styles.css                ← グローバルCSS・Inkブランドカラー
│   │
│   ├── components/
│   │   ├── Sidebar.tsx           ← 左サイドバー（展開/折りたたみ対応）
│   │   ├── WebViewArea.tsx       ← セッション分離済みWebViewエリア
│   │   ├── ServiceModal.tsx      ← サービス追加モーダル
│   │   └── SettingsModal.tsx     ← 設定モーダル（LLM・グループ・データ）
│   │
│   ├── store/
│   │   └── index.ts              ← Zustand状態管理・設定永続化
│   │
│   └── types/
│       └── index.ts              ← TypeScript型定義
│
└── src-tauri/
    ├── build.rs                  ← Tauriビルドスクリプト
    ├── Cargo.toml                ← Rust依存関係
    ├── tauri.conf.json           ← Tauri設定（ウィンドウ・バンドル等）
    │
    ├── icons/                    ← アプリアイコン各サイズ
    │   ├── 32x32.png
    │   ├── 128x128.png
    │   └── 128x128@2x.png
    │
    └── src/
        └── main.rs               ← Rustエントリーポイント
```

---

## 7. 開発ロードマップ

### Phase 1（完了）
- [x] Tauri + React + TypeScript環境構築
- [x] 基本ウィンドウ・左サイドバー表示
- [x] WebViewの表示・セッション分離
- [x] サービス登録UI
- [x] グループ管理
- [x] 設定のエクスポート/インポート
- [x] Linuxビルド・動作確認済み

### Phase 2（次期）
- [ ] AI翻訳パネル（選択テキスト→日本語）
- [ ] AIページ要約（3行サマリー）
- [ ] ドラッグ&ドロップ並び替え
- [ ] ファビコン自動取得の安定化
- [ ] トレイ常駐・スタートアップ登録

### Phase 3（将来）
- [ ] Ctrl+Kコマンドパレット
- [ ] 通知サマリー
- [ ] WebDAV/Nextcloud同期
- [ ] Windows・Macビルド対応

### Phase 4（長期）
- [ ] Ink Memory連携
- [ ] ワークスペース横断レポート生成
- [ ] GitHub Releasesでの公式配布

---

## 8. セットアップ手順

### 必要環境

- Node.js v18以上
- Rust（rustup経由でインストール）
- Linux（v1.0時点）

### 開発起動

```bash
git clone https://github.com/ink-inc/ink-hub.git
cd ink-hub
npm install
npm run tauri dev
```

### ビルド

```bash
npm run tauri build
# 成果物: src-tauri/target/release/bundle/deb/
```

### インストール（Linux）

```bash
sudo dpkg -i "src-tauri/target/release/bundle/deb/Ink Hub_1.0.0_amd64.deb"
```

### スタートアップ登録（任意）

```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/ink-hub.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=Ink Hub
Exec=ink-hub
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
```

---

## 9. ライセンス・配布方針

| 項目 | 内容 |
|---|---|
| ライセンス | MIT |
| 配布場所 | GitHub Releases |
| パッケージ形式 | .deb（Linux v1.0） |
| コントリビューション | Issue・PRを受け付ける |
| APIキー | ユーザー自身が用意・運営側は一切保持しない |

---

*Ink Hub 仕様書 v1.1 - Ink Inc. / 黒井葉跡*
