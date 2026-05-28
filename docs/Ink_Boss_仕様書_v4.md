# Ink Boss 仕様書 v4.0
## Ink Inc. 所長・黒井葉跡

> AI Creation, Human Care. The Future Drawn Together.

---

## 0. プロジェクトの裏コンセプト（最重要）

Ink Boss は Ink Inc. 所属ライバーへの**無料配布ツール**として設計されている。

### 事務所運営の哲学

Ink Inc. は「飴と鞭」の鞭（違約金・縛り）を使わない事務所。
ライバーが「辞めたくない」「辞める理由がない」と感じる環境づくりが目標。

### Ink Boss が果たす役割

- 所属ライバーに**無料で配布**し、配信に特化した PC ワークスペースを提供
- 辞めると**このツールが使えなくなる**というソフトなデメリットを生む
- 配信と PC はセットのため、配信環境ごと提供することで「辞める理由がない」状態を作る
- これが事務所コンセプト「Human Care」の具体的実装

### 配布プラン

| プラン | サービス登録数 | グループ機能 | Ink Aide | 対象 |
|---|---|---|---|---|
| Lite版 | 最大3件 | なし（誘導あり） | なし（誘導あり） | 一般ユーザー |
| Full版 | 無制限 | あり | あり | Ink Inc. 所属ライバー |

### 配布方針

- **両版ともプライベート配布**（ソースコード非公開）
- Lite版・Full版ともに GitHub Private リポジトリで管理
- 将来的に DEBパッケージ・AppImage（Linux）・EXEパッケージ（Windows）でバイナリ配布予定

---

## 1. 技術スタック

| レイヤー | 技術 |
|---|---|
| バックエンド | Python 3.12 / pywebview 6.2.1 / PySide6 6.11.1 |
| フロントエンド | React + TypeScript + Vite v8.0.14 + TailwindCSS |
| AI（Full版のみ） | Ollama（ローカル）/ Claude API / Gemini API |
| 設定保存（Full版） | `~/.config/ink-boss/config.json` |
| 設定保存（Lite版） | `~/.config/ink-boss-lite/config.json` |
| Vite ポート | 5174 |
| Full版リポジトリ | https://github.com/InkInc-official/ink-boss（Private） |
| Lite版リポジトリ | https://github.com/InkInc-official/ink-boss-lite（Private） |

---

## 2. ファイル構成

### Full版 (`~/InkTools/ink-boss/`)

```
ink-boss/
├── main.py              # エントリーポイント（100行）
├── ime.py               # IME自動検出・プラグインリンク
├── config.py            # 定数・load_config・save_config・スタイル定数
├── bridge.py            # ViewBridge（シグナル・WebView管理）
├── api.py               # InkBossAPI（JS↔Python橋渡し）
├── window.py            # find_container・on_shown・on_resized
├── qt_worker.py         # 旧アーキテクチャ残骸（削除しない・マルチプロセス化時の参考）
└── dialogs/
    ├── __init__.py
    ├── settings.py      # 設定ダイアログ（一般・AI/LLM・データ）
    ├── add_service.py   # サービス追加ダイアログ
    ├── add_group.py     # グループ追加ダイアログ
    └── context_menu.py  # コンテキストメニュー（サービス・グループ）
└── frontend/src/components/
    ├── Sidebar.tsx
    ├── WebViewArea.tsx
    ├── InkAide.tsx
    ├── ConfirmDialog.tsx
    └── ContextMenu.tsx
```

### Lite版 (`~/InkTools/ink-boss-lite/`)

```
ink-boss-lite/
├── main.py              # Full版と同一
├── ime.py               # Full版と同一
├── config.py            # LITE_MODE=True / LITE_LIMIT=3 / LITE_URL を追加
├── bridge.py            # グループ操作→誘導ダイアログに差し替え
├── api.py               # Full版と同一
├── window.py            # Full版と同一
└── dialogs/
    ├── __init__.py
    ├── settings.py      # ナレッジ・AI/LLMに注意書きバナーを追加
    ├── add_service.py   # 3件上限チェック追加
    ├── add_group.py     # Full版と同一（bridge側で誘導するため実質未使用）
    ├── context_menu.py  # Full版と同一
    └── upgrade_dialog.py # Ink Inc. 所属誘導ダイアログ（Lite版専用）
└── frontend/src/components/
    ├── Sidebar.tsx      # グループボタン→誘導モーダル / Liteバッジ表示
    ├── WebViewArea.tsx  # Aideボタン→誘導モーダル / Liteバッジ表示
    ├── ConfirmDialog.tsx
    └── ContextMenu.tsx
```

---

## 3. 起動コマンド

### Full版

```bash
cd ~/InkTools/ink-boss
pkill -f vite; fuser -k 5173/tcp 5174/tcp 2>/dev/null; sleep 1
npm run dev --prefix frontend &
sleep 4
python3 main.py
```

### Lite版

```bash
cd ~/InkTools/ink-boss-lite
pkill -f vite; fuser -k 5173/tcp 5174/tcp 2>/dev/null; sleep 1
npm run dev --prefix frontend &
sleep 4
python3 main.py
```

---

## 4. 実装済み機能

### 4.1 共通機能（Full版・Lite版）

| 機能 | 詳細 |
|---|---|
| WebView管理 | サービスごとに独立した QWebEngineView を生成・管理 |
| サービス追加 | 名前・URL を入力して登録（Enterキー対応） |
| サービス休止 | 非アクティブ時に about:blank でメモリ解放 |
| サービス復帰 | ダブルクリックで復帰（300ms遅延でチラつき防止） |
| サービス削除 | コンテキストメニューから削除 |
| サービス名変更 | コンテキストメニューから変更 |
| ドラッグ移動 | タイトルバードラッグでウィンドウ移動（xdotool + wmctrl） |
| タイトルバー非表示 | xprop で `_MOTIF_WM_HINTS` を書き換え（Mutter対応） |
| 背景透過防止 | QPalette で `#080810` を明示セット |
| 日本語IME | fcitx5/ibus を自動検出・ibusプロトコル経由で接続 |
| リサイズ対応 | on_resized イベントで WebView ジオメトリを追従 |
| Google検索対応 | `_CustomPage` で全ナビゲーション許可・リダイレクトURL対応 |
| 新規タブ対応 | `target="_blank"` を同 View で開く |
| 設定画面 | 休止モード・ナレッジ・AI/LLM・データ（エクスポート・インポート） |
| Favicon表示 | Google Favicon API でサービスアイコンを取得・グレースケール表示 |
| ページテキストキャッシュ | ページ読み込み後に innerText をキャッシュ（Ink Aide 用） |

### 4.2 Full版専用機能

| 機能 | 詳細 |
|---|---|
| グループ機能 | サービスをグループ分けして整理・折りたたみ対応 |
| グループ並び替え | ドラッグ＆ドロップでグループ順序を変更 |
| サービス移動・コピー | コンテキストメニューからグループ間移動・コピー |
| Ink Aide | AIチャットパネル（要約・ポイント・感想の3クイックボタン） |
| Ink Aide バックエンド | Ollama / Claude API / Gemini API を設定で切り替え |
| ナレッジ機能 | 自己紹介テキストを Ink Aide の感想ボタンに反映 |
| Ollamaモデル管理 | おすすめ5モデルをワンクリックでダウンロード・選択 |

### 4.3 Lite版専用機能

| 機能 | 詳細 |
|---|---|
| サービス登録上限 | 3件を超えると Ink Inc. 所属誘導ダイアログを表示 |
| グループ誘導 | グループボタン押下時に所属誘導モーダルを表示 |
| Aide誘導 | Aide ボタン押下時に所属誘導モーダルを表示 |
| 特典バッジ | グループ・Aide ボタンに「✦」バッジを表示 |
| 設定注意書き | ナレッジ・AI/LLM 設定に Lite版注意書きバナーを表示 |
| 誘導URL | https://inkinc-hp.vercel.app/ |

---

## 5. 重要な実装メモ

### _aide_width（必須）

Aide パネルを開く時に WebView を縮小する。

```python
_aide_width = 0  # グローバル変数

def get_rect(window, aide_w=0):
    return SIDEBAR_W, URLBAR_H, window.width - SIDEBAR_W - aide_w, window.height - URLBAR_H
```

チェックコマンド：
```bash
grep -n "_aide_width\|get_rect" ~/InkTools/ink-boss/main.py
# 正常：5箇所以上ヒット
```

### showEmpty（WebViewArea.tsx）

```tsx
const showEmpty = !activeServiceId;  // !activeServiceや|| isHibernatedはNG
```

### ダブルクリックで setActiveService（Sidebar.tsx）

```tsx
// 休止中ダブルクリック時：service-wokeイベントを受け取ってからsetActiveService
const onWoke = (e: CustomEvent) => {
  if (e.detail === service.id) {
    setActiveService(service.id);
    window.removeEventListener("service-woke", onWoke as EventListener);
  }
};
window.addEventListener("service-woke", onWoke as EventListener);
await window.pywebview?.api?.show_service(service.id);
```

### show_service の wake→show 遅延

```python
if sid in bridge.hibernated:
    bridge.wake_view_signal.emit(sid, bridge.urls.get(sid, "about:blank"))
    x, y, ww, h = get_rect(w, _aide_width)
    QTimer.singleShot(300, lambda: bridge.show_view_signal.emit(sid, x, y, ww, h))
```

### Google検索リンク対応（_CustomPage）

```python
class _CustomPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        return True  # 全ナビゲーション許可

    def _on_new_window(self, request):
        self.setUrl(request.requestedUrl())  # target="_blank"を同Viewで開く
```

### サービス追加ダイアログ（finished シグナル方式）

```python
accepted = {"svc": None}

def on_accept():
    ...
    accepted["svc"] = svc
    dialog.accept()

def on_finished():
    svc = accepted["svc"]
    if svc is None: return
    QTimer.singleShot(100, lambda: create_view_fn(svc["id"], svc["url"]))
    QTimer.singleShot(200, lambda: js_eval_fn(...))

dialog.finished.connect(on_finished)
```

### Enterキー対応

```python
name_input.returnPressed.connect(on_accept)
url_input.returnPressed.connect(on_accept)
```

### 日本語入力（IME）

ChromiumベースのQWebEngineViewは ibusプロトコルでIMEと通信する。
fcitx5 はibusフロントエンドを内蔵しているため、ibusとして接続すれば動く。

```python
os.environ["QT_IM_MODULE"]  = "ibus"
os.environ["XMODIFIERS"]    = "@im=ibus"
os.environ["GTK_IM_MODULE"] = "ibus"
```

### init_views_signal の使い方

`on_shown` は pywebview スレッドから呼ばれるため QTimer.singleShot が使えない。
サービス初期化は `bridge.init_views_signal.emit()` で Qt メインスレッドに委譲する。

---

## 6. 設定画面仕様

### 一般タブ

| 項目 | 詳細 |
|---|---|
| 休止モード | 無効 / 5分 / 10分 / 15分 / 30分 / 1時間 |
| ナレッジ | AIへの自己紹介（200文字以内）。Ink Aide 感想ボタン使用時に活用 |

※ Lite版：ナレッジに「Ink Aide は所属特典のため Lite版では使用できません」バナーを表示

### AI/LLM タブ（Full版）

| 項目 | 詳細 |
|---|---|
| Ollama インストール | ワンクリックインストール |
| おすすめモデル5種 | gemma2:9b / qwen2.5:3b / qwen2.5:7b / llama3.2 / mistral:7b |
| Claude API キー | sk-ant-... |
| Gemini API キー | AIza... |

※ Lite版：タブ冒頭に「AI/LLM 設定は Ink Aide 専用・所属特典のため使用できません」バナーを表示

### データタブ

| 項目 | 詳細 |
|---|---|
| 設定エクスポート | JSON ファイルとして保存 |
| 設定インポート | JSON ファイルから読み込み |

---

## 7. Ink Aide 仕様（Full版のみ）

### 機能

- URL バー右の「Aide」ボタンで開閉（幅 320px）
- `set_aide_width` で WebView を縮小
- 起動時に Ollama / Claude / Gemini 接続確認 → 「✓ Aide OK」緑表示
- クリアボタンで loading 状態もリセット

### クイックボタン3つ

| ボタン | プロンプト |
|---|---|
| 要約 | このページの内容を日本語で簡潔に要約してください。 |
| ポイント | このページの重要なポイントを日本語で箇条書きにしてください。 |
| 感想 | `__KNOWLEDGE__` + このページの内容について、私の立場から見た活用方法や感想を日本語で教えてください。 |

### `__KNOWLEDGE__` 置換

```tsx
// 吹き出し表示：__KNOWLEDGE__を除去
const displayPrompt = prompt.replace("__KNOWLEDGE__", "").trim();

// AI送信：ナレッジ内容に置換
const resolvedPrompt = prompt.includes("__KNOWLEDGE__")
  ? prompt.replace("__KNOWLEDGE__", knowledge ? `私は${knowledge}。\n\n` : "")
  : prompt;
```

---

## 8. 解決済み問題

| 問題 | 解決方法 |
|---|---|
| Google検索結果のリンクに飛べない | `_CustomPage.acceptNavigationRequest` で全ナビゲーションを許可 |
| target="_blank" が動かない | `newWindowRequested` を同 View で開くよう実装 |
| サービス追加が保存されない | `dialog.finished` シグナル方式に変更・QTimer遅延で競合回避 |
| Enterキーで追加できない | `returnPressed` を `on_accept` に接続 |
| 日本語入力できない | fcitx5 を ibus プロトコル経由で接続 |
| タイトルバーが消えない | xprop で `_MOTIF_WM_HINTS` を書き換え（Mutter対応） |
| 背景が透過する | QPalette で Window ロールに `#080810` を明示セット |
| WebView チラつき | wake→show に 300ms 遅延を追加 |

---

## 9. 未着手タスク

### 優先度高
- [ ] Lite版の動作完全確認
- [ ] Full版・Lite版のバイナリパッケージ化（DEB / AppImage / EXE）

### 優先度中
- [ ] ライセンスキー認証（所属ライバー判定）
- [ ] 自動アップデート機能

### 将来の拡張
- [ ] テーマ機能（CSS変数化が前提・v3.0以降で検討）
- [ ] マルチプロセス化（qt_worker.py を参考に復活）
- [ ] Lite版の Windows 対応確認

---

## 10. Git コミット履歴

| コミット | 内容 |
|---|---|
| `05d4a29` | feat: initial commit - IME, drag, titlebar, knowledge fixes |
| `2f7fd67` | refactor: main.pyをコンポーネント化（1411行→100行） |
| `bf75081` | fix: Google検索リンク無反応・サービス追加不具合を修正 |

---

## 11. 次のチャットに渡すファイル

- `main.py`
- `bridge.py`
- `api.py`
- `window.py`
- `config.py`
- `dialogs/add_service.py`
- `dialogs/add_group.py`
- `Ink_Boss_仕様書_v4.md`

GitHub からも取得可能：
```bash
# Full版
git clone https://github.com/InkInc-official/ink-boss.git

# Lite版
git clone https://github.com/InkInc-official/ink-boss-lite.git
```

---

*AI Creation, Human Care. The Future Drawn Together.*
*Ink Inc. 所長・黒井葉跡*
