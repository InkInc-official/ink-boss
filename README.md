# 🦁 Ink Boss

> All your services. One place. No compromises.

**Ink Inc.** が開発する、レシピレスのマルチサービス一元化デスクトップアプリ。

[![license](https://img.shields.io/badge/license-MIT-green)](#license)
[![platform](https://img.shields.io/badge/platform-Linux-blue)](#)
[![built with](https://img.shields.io/badge/built%20with-PySide6%20%2B%20Electron-41cd52)](#)

> AI Creation, Human Care. The Future Drawn Together. — Ink Inc.

---

## なぜ作ったか

Ferdium・Rambox・Station のような「マルチサービス統合アプリ」は数多く存在しますが、
単一のブラウザエンジンだけでは、サービスごとに異なるログイン方式の要件を
すべて満たせません。実地検証で以下の制約が判明しています。

- **Googleアカウントでのログイン**は、Googleが2021年以降「組み込みブラウザ
  (embedded browser)」からのOAuthを公式ポリシーとして拒否しており、
  Electron（Chromium同梱）ベースのアプリでは構造的にブロックされる。
- 一方で **Discordのようなメール/パスワード認証**は、QtWebEngine側の
  終了タイミングによってはセッション情報（LocalStorage）がディスクに
  書き切られず、ログイン状態が失われることがある。Electronベースの
  セッション管理の方が安定するケースがある。

そこでInk Bossは、**サービスごとにQtWebEngineとElectronのどちらのエンジンを
使うか選べる「デュアルエンジン方式」**を採用しています。片方の弱点をもう
片方で補う構成です。

---

## デュアルエンジン方式

| エンジン | 得意なケース | 実装 |
|---|---|---|
| **Qt**（QtWebEngine） | Google OAuthを要するサービス（Gmail, Claude等） | PySide6のQWebEngineViewをアプリ内に直接埋め込み |
| **Electron** | メール/パスワード認証で長期セッションを維持したいサービス（Discord等） | 常駐のElectronヘルパープロセスをHTTP経由で操作し、ウィンドウをInk Boss本体に追従させる |

- サービス追加時、URLからGoogle系ドメインを検出すると自動でQtを提案し、
  それ以外はElectronをデフォルト提案します（手動で切り替えも可能）。
- サービスごとに独立したプロファイル（Cookie・LocalStorage）を持ち、
  アカウント間のセッションは完全に分離されます。

---

## コンセプト

既存の一元化アプリは、サービスごとの「レシピ」を大量に抱え、メンテナンスコストで停滞・終了を繰り返してきました。Ink Bossはこの構造を根本から排除します。

**URLを登録するだけ。** レシピは不要です。

- **レシピレス設計** — URLを追加するだけで、あらゆるWebサービスをサイドバーに固定できる
- **エンジン選択式** — サービスごとにQt / Electronを選び、認証方式に応じた最適なエンジンで動かせる
- **セッション分離** — サービスごとに独立したプロファイルを割り当て、Cookie・ログイン状態を完全に分離
- **遅延ロード / ハイバネート** — 未使用サービスは休止し、メモリを節約
- **ローカルファースト** — ログイン情報・閲覧データは外部に送信されません

---

## 技術スタック

| レイヤー | 技術 |
|---|---|
| デスクトップシェル | PySide6（Qt for Python）+ [pywebview](https://pywebview.flowrl.com/)（`gui="qt"`） |
| フロントエンド | React + TypeScript + Vite（`frontend/`） |
| レンダリングエンジン（Qt側） | QtWebEngine（Chromiumベース） |
| レンダリングエンジン（Electron側） | 常駐Electronヘルパー（`electron-engine/`）をHTTP APIで制御 |
| Python ↔ フロント連携 | pywebview の `js_api`（[api.py](api.py)） |
| Python ↔ Electron連携 | ローカルHTTP（[electron_bridge.py](electron_bridge.py)） |

---

## セットアップ

### 必要なもの

- Python 3.12+
- PySide6（QtWebEngine含む）
- Node.js（Electronヘルパー用）

```bash
pip install -r requirements.txt
cd electron-engine && npm install && cd ..
```

フロントエンドをビルドする場合（`frontend/dist` があればそちらを優先して配信します）:

```bash
npm install --prefix frontend
npm run build --prefix frontend
```

### 起動

```bash
python3 main.py
```

開発中でフロントエンドをVite dev serverで動かす場合:

```bash
npm run dev --prefix frontend &
python3 main.py
```

設定・セッションは以下に保存されます。

- `~/.config/ink-boss/config.json`
- `~/.config/ink-boss/sessions/`（Qtエンジンのプロファイル）
- `~/.config/ink-boss/electron-userdata/`（Electronエンジンのプロファイル）

---

## ロードマップ

- [ ] 1サービス内での複数タブ機能
- [ ] サービスのフォルダ分け（ドラッグ&ドロップでの並べ替え）
- [ ] Windows / macOS対応
- [ ] Aide（サイドパネルAIアシスタント）の正式統合
- [ ] 配布パッケージ（.deb / AppImage）の自動ビルド

---

## Contributing

Issue・Pull Request、歓迎します。特に以下の分野での貢献を歓迎しています。

- Windows / macOS対応
- サービスごとのバッジ通知（未読数表示）
- UI/UXの改善

---

## ライセンス

MIT License — © 2026 黒井葉跡 / Ink Inc.

---

## Ink Inc.について

**AI Creation, Human Care. The Future Drawn Together.**

AIによる創造と人によるケアを両立するIRIAMライバー事務所です。「無料でもここまでできる」を体現するために、内製ツールを積極的にOSSとして公開しています。

- Web: https://inkinc-hp.vercel.app/
- X: https://x.com/InkInc_Info
- GitHub: https://github.com/InkInc-official

### 関連プロジェクト

- [Ink Timodal](https://github.com/InkInc-official/ink-timodal) — ADHDクリエイターのための完全ローカル自己観察ツール
- [Ink Calendar Lite](https://github.com/BlackHeart0731/ink-calendar-lite) — サーバー不要のイベント予定共有ツール
