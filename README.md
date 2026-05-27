# 🦁 Ink Hub

> All your services. One place.

**Ink Inc.** が開発するレシピレスのマルチサービス一元化デスクトップアプリ。

---

## コンセプト

既存の一元化アプリ（Ferdium・Rambox等）はサービスごとの「レシピ」を大量に抱え、メンテナンスコストで停滞・終了を繰り返してきた。

Ink Hubはこの構造を根本から排除する。**URLを登録するだけ**。それだけで全サービスが動く。

---

## 特徴

- **レシピレス設計** — URL登録のみ。サービス固有コードなし
- **セッション分離** — 各サービスのログイン状態を完全独立管理
- **LLM統合（3択）** — Ollama / Claude API / Gemini API
- **完全OSS** — MITライセンス・ライセンス問題ゼロ
- **軽量** — Tauri採用でElectronより大幅に軽い

---

## セットアップ

### 必要なもの

- [Node.js](https://nodejs.org/) v18以上
- [Rust](https://rustup.rs/)
- Linux（v1.0）

### インストール

```bash
git clone https://github.com/ink-inc/ink-hub.git
cd ink-hub
npm install
npm run tauri dev
```

### ビルド

```bash
npm run tauri build
```

---

## LLM設定

設定画面（⚙）からバックエンドを選択：

| バックエンド | 特徴 |
|---|---|
| Ollama（デフォルト） | ローカル・無料・完全オフライン |
| Claude API | 高精度・従量課金・要APIキー |
| Gemini API | 無料枠あり・取得容易・要APIキー |

APIキーはユーザー自身が用意します。Ink Inc.は一切保持しません。

---

## ライセンス

MIT © Ink Inc. / 黒井葉跡
