# 🦁 Ink Boss

> All your services. One place. No compromises.

[日本語](#ink-boss) | [English](#ink-boss-english)

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



## Ink Boss (English)

> All your services. One place. No compromises.

A recipe-less, multi-service desktop app developed by **Ink Inc.**

[![license](https://img.shields.io/badge/license-MIT-green)](#license)
[![platform](https://img.shields.io/badge/platform-Linux-blue)](#)
[![built with](https://img.shields.io/badge/built%20with-PySide6%20%2B%20Electron-41cd52)](#)

> AI Creation, Human Care. The Future Drawn Together. — Ink Inc.

---

### Why we built this

Multi-service "everything in one app" tools like Ferdium, Rambox, and Station already exist, but a single browser engine can't satisfy every service's login requirements. In practice we ran into these constraints:

- **Google account sign-in**: since 2021, Google's official policy blocks OAuth from "embedded browsers," which structurally blocks Electron (bundled Chromium) apps.
- **Email/password auth (e.g. Discord)**: depending on when QtWebEngine shuts down, session data (LocalStorage) can fail to flush to disk, losing the login state. Electron's session handling is more reliable for these cases.

So Ink Boss uses a **dual-engine design**: you choose QtWebEngine or Electron per service, and each engine covers the other's weak spot.

---

### Dual-engine design

| Engine | Best for | Implementation |
|---|---|---|
| **Qt** (QtWebEngine) | Services requiring Google OAuth (Gmail, Claude, etc.) | PySide6's QWebEngineView embedded directly in the app |
| **Electron** | Services with email/password auth that need long-lived sessions (Discord, etc.) | A persistent Electron helper process controlled over HTTP, with its window tracking the main Ink Boss window |

- When you add a service, Ink Boss auto-suggests Qt for Google-domain URLs and Electron for everything else (you can switch manually).
- Each service gets an isolated profile (cookies, LocalStorage) — sessions never leak between accounts.

---

### Concept

Existing "everything in one app" tools accumulate a "recipe" per service and eventually stall or shut down under that maintenance burden. Ink Boss removes that structure entirely.

**Just register a URL. No recipes needed.**

- **Recipe-less** — pin any web service to the sidebar just by adding its URL
- **Per-service engine choice** — pick Qt or Electron per service to match its auth method
- **Session isolation** — each service gets its own profile; cookies and login state never mix
- **Lazy loading / hibernation** — unused services sleep to save memory
- **Local-first** — login info and browsing data are never sent anywhere external

---

### Tech stack

| Layer | Technology |
|---|---|
| Desktop shell | PySide6 (Qt for Python) + [pywebview](https://pywebview.flowrl.com/) (`gui="qt"`) |
| Frontend | React + TypeScript + Vite (`frontend/`) |
| Rendering engine (Qt side) | QtWebEngine (Chromium-based) |
| Rendering engine (Electron side) | Persistent Electron helper (`electron-engine/`) controlled via HTTP API |
| Python ↔ Frontend | pywebview's `js_api` ([api.py](api.py)) |
| Python ↔ Electron | Local HTTP ([electron_bridge.py](electron_bridge.py)) |

---

### Setup

**Requirements**

- Python 3.12+
- PySide6 (with QtWebEngine)
- Node.js (for the Electron helper)

```bash
pip install -r requirements.txt
cd electron-engine && npm install && cd ..
```

If you want to build the frontend yourself (if `frontend/dist` exists, it's served in preference to a dev server):

```bash
npm install --prefix frontend
npm run build --prefix frontend
```

**Run**

```bash
python3 main.py
```

To run the frontend against the Vite dev server during development:

```bash
npm run dev --prefix frontend &
python3 main.py
```

Config and sessions are stored at:

- `~/.config/ink-boss/config.json`
- `~/.config/ink-boss/sessions/` (Qt engine profiles)
- `~/.config/ink-boss/electron-userdata/` (Electron engine profiles)

---

### Roadmap

- [ ] Multiple tabs within a single service
- [ ] Folder grouping for services (drag & drop reordering)
- [ ] Windows / macOS support
- [ ] Official integration of Aide (the sidebar AI assistant)
- [ ] Automated build of distribution packages (.deb / AppImage)

---

### Contributing

Issues and pull requests are welcome. We'd especially love help with:

- Windows / macOS support
- Per-service unread/badge notifications
- UI/UX improvements

---

### License

MIT License — © 2026 Kuroi Hatsuto / Ink Inc.

---

### About Ink Inc.

**AI Creation, Human Care. The Future Drawn Together.**

An IRIAM talent agency that combines AI-driven creation with human care. We actively open-source our in-house tools to show what's possible even on a shoestring budget.

- Web: https://inkinc-hp.vercel.app/
- X: https://x.com/InkInc_Info
- GitHub: https://github.com/InkInc-official

**Related projects**

- [Ink Timodal](https://github.com/InkInc-official/ink-timodal) — a fully local self-observation tool for ADHD creators
- [Ink Calendar Lite](https://github.com/BlackHeart0731/ink-calendar-lite) — a serverless event-schedule sharing tool