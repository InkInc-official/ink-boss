# Ink Boss 開発引継ぎ書 v3
## Ink Inc. 所長・黒井葉跡

> AI Creation, Human Care. The Future Drawn Together.

---

## 0. プロジェクトの裏コンセプト（最重要）

Ink BossはInk Inc.所属ライバーへの**無料配布ツール**として設計されている。

### 事務所運営の哲学
Ink Inc.は「飴と鞭」の鞭（違約金・縛り）を使わない事務所。
ライバーが「辞めたくない」「辞める理由がない」と感じる環境づくりが目標。

### Ink Bossが果たす役割
- 所属ライバーに**無料で配布**し、配信に特化したPCワークスペースを提供
- 辞めると**このツールが使えなくなる**というソフトなデメリットを生む
- 配信とPCはセットのため、配信環境ごと提供することで「辞める理由がない」状態を作る
- これが事務所コンセプト「Human Care」の具体的実装

### 配布プラン（予定）
| プラン | サービス登録数 | 対象 |
|---|---|---|
| 一般公開版（Lite） | 最大3〜5件 | 非所属・一般ユーザー |
| 所属ライバー版（Full） | 無制限 | Ink Inc.所属ライバー |

### 配布形式（予定）
- Linux: DEBパッケージ・AppImage
- Windows: EXEパッケージ
- → **誰の環境でも動く**ことが前提

---

## 1. 起動コマンド

```bash
cd ~/InkTools/ink-boss
pkill -f vite; fuser -k 5173/tcp 5174/tcp 2>/dev/null; sleep 1
npm run dev --prefix frontend &
sleep 4
python3 main.py
```

---

## 2. 技術スタック

| レイヤー | 技術 |
|---|---|
| バックエンド | Python 3.12 / pywebview 6.2.1 / PySide6 6.11.1 |
| フロントエンド | React + TypeScript + Vite v8.0.14 + TailwindCSS |
| AI | Ollama（ローカル）/ Claude API / Gemini API |
| 設定保存 | `~/.config/ink-boss/config.json` |
| Viteポート | 5174（5173が使用中のため） |
| リポジトリ | https://github.com/InkInc-official/ink-boss（Private） |

---

## 3. ファイル構成

```
~/InkTools/ink-boss/
├── main.py
└── frontend/src/components/
    ├── Sidebar.tsx
    ├── WebViewArea.tsx
    ├── InkAide.tsx
    ├── ConfirmDialog.tsx
    └── ContextMenu.tsx
```

---

## 4. 重要な実装メモ

### _aide_width（必須）
Aideパネルを開く時にWebViewを縮小する。以下全箇所で使うこと。

```python
_aide_width = 0  # グローバル変数

def get_rect(window, aide_w=0):
    return SIDEBAR_W, URLBAR_H, window.width - SIDEBAR_W - aide_w, window.height - URLBAR_H
```

チェックコマンド：
```bash
grep -n "_aide_width\|get_rect" ~/InkTools/ink-boss/main.py
# 正常：5箇所以上ヒット
# get_rect(w)が1箇所でもあればNG → get_rect(w, _aide_width)に直す
```

### showEmpty（WebViewArea.tsx）
```tsx
const showEmpty = !activeServiceId;  // !activeServiceや|| isHibernatedはNG
```

### ダブルクリックでsetActiveService（Sidebar.tsx）
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

### setIntervalを使わない
JS側のsetIntervalでsync_geometryを呼ぶコードは削除済み。
on_resizedで対応しているため不要。

### init_views_signalの使い方
`on_shown`はpywebviewスレッドから呼ばれるため、QTimer.singleShotが使えない。
サービス初期化は`bridge.init_views_signal.emit()`でQtメインスレッドに委譲する。

```python
# ViewBridgeにinit_views_signalを定義
init_views_signal = Signal()
# on_shown内
bridge.init_views_signal.emit()
```

### show_serviceのwake→show遅延
wakeとshowを連続emitすると真っ黒になる。300ms遅延を入れること。

```python
if sid in bridge.hibernated:
    bridge.wake_view_signal.emit(sid, bridge.urls.get(sid, "about:blank"))
    x, y, ww, h = get_rect(w, _aide_width)
    QTimer.singleShot(300, lambda: bridge.show_view_signal.emit(sid, x, y, ww, h))
```

---

## 5. タイトルバー非表示（解決済み）

`on_shown`内の`hide_titlebar()`が`xprop`で`_MOTIF_WM_HINTS`を書き換えて実現。
Ubuntu BudgieのMutterが受け付けたため安定動作中。
同時に`_win_id`グローバル変数にウィンドウIDをキャッシュしている。

```python
_win_id = None  # グローバル変数（hide_titlebar内でキャッシュ）
```

---

## 6. ウィンドウドラッグ移動（解決済み）

TopBarの`onMouseDown`で`drag_start`、`mouseup`で`drag_end`を呼ぶ。
Python側でスレッドがxdotoolでマウス座標を追跡してwmctrlで移動する。
WebViewのZ順に依存しないOS座標追跡方式。

**注意：** `drag_start`内でウィンドウIDは`_win_id`キャッシュを使う（起動時に1回のみ取得）。

---

## 7. 日本語入力（解決済み）

### 原因の連鎖
1. `QT_IM_MODULE=fcitx` → QWebEngineView（Chromium）には効かない
2. XIMプロトコル → ChromiumはXIMを使わない
3. `xdotool windowfocus` → 効かない（Mutterがフォーカス管理しない）
4. `wmctrl -ia` → X11フォーカスは取れるが不十分
5. **`QT_IM_MODULE=ibus` + fcitx5のibusフロントエンド経由** → 解決！

### 結論
ChromiumベースのQWebEngineViewは**ibusプロトコル**でIMEと通信する。
fcitx5はibusフロントエンドを内蔵しているため、ibusとして接続させれば動く。

### 実装（_setup_ime関数）
```python
# fcitx5が動いている場合もibusプロトコル経由で接続
os.environ["QT_IM_MODULE"]  = "ibus"
os.environ["XMODIFIERS"]    = "@im=ibus"
os.environ["GTK_IM_MODULE"] = "ibus"
```

### 配布時の注意
- Windows・macOS・ibus環境: 何もしなくて動く
- fcitx5環境: 初回のみ以下を実行してログアウト→ログイン
  ```bash
  im-config -n fcitx5
  ```
- PySide6はfcitx5プラグインを内包していないため自動リンクで対応済み

### PySide6のプラグイン自動リンク
起動時に`_setup_ime()`がシステムのfcitx5プラグインをPySide6ディレクトリに自動リンク。
```
~/.local/lib/python3.12/site-packages/PySide6/Qt/plugins/platforminputcontexts/
  libfcitx5platforminputcontextplugin.so  ← 自動リンク
```

---

## 8. 背景透過防止（解決済み）

`_MOTIF_WM_HINTS`でタイトルバーを消した後、背景が透過する問題。
2箇所から対処：

```python
# 1. create_window
background_color="#080810"

# 2. on_shown内
palette.setColor(QPalette.ColorRole.Window, QColor("#080810"))
main_win.setPalette(palette)
main_win.setAutoFillBackground(True)
```

---

## 9. 設定画面（Python側QDialog）

### 一般タブ
- 休止モード（無効/5分/10分/15分/30分/1時間）
- **ナレッジ（自己紹介）** → 200文字以内、感想ボタン使用時にシステムプロンプトに追加

### AI/LLMタブ
- Ollamaインストールボタン
- おすすめモデル5種：
  - gemma2:9b（高品質・Google）
  - qwen2.5:3b（軽量・多言語・推奨）
  - qwen2.5:7b（バランス型）
  - llama3.2:latest（Meta汎用）
  - mistral:7b（高品質・フランス製）
- モデル選択時に他のボタンを「選択」に戻す（`model_buttons`辞書で管理）
- Claude APIキー / Gemini APIキー入力
- 保存時「✓ 保存しました」表示

### データタブ
- 設定エクスポート・インポート

---

## 10. Ink Aide（解決済み）

### 機能
- URLバー右の「Aide」ボタンで開閉（幅320px）
- `set_aide_width`でWebViewを縮小
- 起動時にOllama/Claude/Gemini接続確認→「✓ Aide OK」緑表示
- クリアボタンでloading状態もリセット

### クイックボタン3つ
1. **要約** → 「このページの内容を日本語で簡潔に要約してください。」
2. **ポイント** → 「このページの重要なポイントを日本語で箇条書きにしてください。」
3. **感想** → `__KNOWLEDGE__` + 「このページの内容について、私の立場から見た活用方法や感想を日本語で教えてください。」

### __KNOWLEDGE__置換（解決済み）
吹き出し表示用に`displayPrompt`、AI送信用に`resolvedPrompt`を分離。

```tsx
// 吹き出し表示：__KNOWLEDGE__を除去
const displayPrompt = prompt.replace("__KNOWLEDGE__", "").trim();
setMessages(prev => [...prev, { role: "user", content: displayPrompt }]);

// AI送信：ナレッジ内容に置換
const resolvedPrompt = prompt.includes("__KNOWLEDGE__")
  ? prompt.replace("__KNOWLEDGE__", knowledge ? `私は${knowledge}。\n\n` : "")
  : prompt;
const fullPrompt = pageText
  ? `ページ内容：\n${pageText.slice(0, 3000)}\n\n${resolvedPrompt}`
  : resolvedPrompt;
```

---

## 11. 未解決の問題

| 問題 | 状況 | 備考 |
|---|---|---|
| Google検索結果のサイトが開かない | 未解決 | 原因不明 |
| 日本語入力（IME入力欄） | 未解決 | WebView内のinput要素でのpreedit表示未確認 |
| タイトルバーが消えない | 解決済み | Mutter+xpropで安定 |
| 設定コンポーネント化 | 未着手 | main.pyが肥大化している |

---

## 12. 次のチャットでやること

### 優先度高
- [ ] Google検索結果のサイトが開かない問題の調査
- [ ] 日本語入力のpreedit（変換候補）表示確認

### 優先度中
- [ ] 設定コンポーネント化（main.pyが肥大化）
- [ ] Lite版のサービス登録数制限実装

### 将来の拡張
- ライセンスキー認証（所属ライバー判定）
- DEBパッケージ・AppImage化・EXEパッケージ
- 自動アップデート機能

---

## 13. 次のチャットに渡すファイル

- `main.py`
- `WebViewArea.tsx`
- `InkAide.tsx`
- `Sidebar.tsx`

GitHubからも取得可能：
```bash
git clone https://github.com/InkInc-official/ink-boss.git
```

---

*AI Creation, Human Care. The Future Drawn Together.*
*Ink Inc. 所長・黒井葉跡*
