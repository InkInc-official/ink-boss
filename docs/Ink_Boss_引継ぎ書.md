# Ink Boss 開発引継ぎ書
## Ink Inc. 所長・黒井葉跡

> AI Creation, Human Care. The Future Drawn Together.

---

## 1. プロジェクト概要

| 項目 | 内容 |
|---|---|
| アプリ名 | Ink Boss |
| 種別 | デスクトップアプリ（Ubuntu Budgie） |
| コンセプト | Ferdiumライクなマルチサービス管理ブラウザ＋AI（Ink Aide）搭載 |
| 対象ユーザー | Ink Inc.所属ライバー（将来的にLite版配布予定） |
| 開発環境 | Ubuntu Budgie 24.04 / Mutter(Budgie) WM |

---

## 2. 技術スタック

| レイヤー | 技術 |
|---|---|
| バックエンド | Python 3.12 / pywebview 6.2.1 / PySide6 6.11.1 |
| フロントエンド | React + TypeScript + Vite v8.0.14 + TailwindCSS |
| ウィンドウ | pywebview（Qtバックエンド） + QWebEngineView |
| AI | Ollama（ローカル）/ Claude API / Gemini API |
| 設定保存 | `~/.config/ink-boss/config.json` |
| セッション保存 | `~/.config/ink-boss/sessions/{service_id}/` |

---

## 3. ファイル構成

```
~/InkTools/ink-boss/
├── main.py                          ← メイン（全機能統合）
└── frontend/src/components/
    ├── App.tsx
    ├── store/index.ts
    ├── types/index.ts
    └── components/
        ├── Sidebar.tsx              ← サイドバー（グループ・サービス管理）
        ├── WebViewArea.tsx          ← メインエリア（URLバー・Aideボタン）
        ├── InkAide.tsx              ← AIアシスタントパネル（新規）
        ├── ConfirmDialog.tsx
        ├── ContextMenu.tsx
        └── SettingsModal.tsx        ← 未使用（設定はPython側QDialog）
```

---

## 4. 起動コマンド

```bash
cd ~/InkTools/ink-boss
pkill -f vite; fuser -k 5173/tcp 5174/tcp 2>/dev/null; sleep 1
npm run dev --prefix frontend &
sleep 4
python3 main.py
```

---

## 5. 実装済み機能

### 5.1 基本機能
- サービス追加・削除・名前変更（右クリックメニュー）
- グループ追加・削除・名前変更・並び替え（ドラッグ）
- グループ折りたたみ
- サービスのグループ間移動・コピー
- 休止モード（指定時間後に自動休止）
- サービスごとにセッション保存（ログイン状態維持）
- ウィンドウリサイズ追従
- ドラッグ移動（URLバー部分）

### 5.2 設定（Python側QDialog）
- 一般タブ：休止モード時間設定
- AI/LLMタブ：
  - Ollamaインストールボタン
  - おすすめモデル5種のダウンロード・選択
  - Claude APIキー / Gemini APIキー入力
- データタブ：設定エクスポート・インポート

### 5.3 Ink Aide（AIアシスタント）
- URLバー右の「Aide」ボタンで開閉
- クイックボタン：要約・和訳・信ぴょう性チェック
- チャット入力欄
- バックエンド：Ollama / Claude API / Gemini API対応
- ページ内容取得：`get_page_text`でQWebEngineViewからJS経由で取得

### 5.4 UI
- タイトルバー：xprop+wmctrlで非表示（Mutter/Budgie対応）
- ボトムバー折りたたみ（▽/△）
- サービス未選択・全休止時はINK BOSSスタート画面表示

---

## 6. 重要な実装メモ

### ダイアログのフリーズ問題
- `dialog.exec()`はQueuedConnectionのSlot内で**使える**
- `js_eval`（pywebviewのevaluate_js）は`threading.Thread`で非同期化が必要
- `dialog.show()`はSlot終了後にダイアログが破棄されてボタンが効かなくなる
- **結論：`dialog.exec()` + `js_eval`を`threading.Thread`で呼ぶ**

### _aide_width（重要）
Ink Aideパネルを開く際、WebViewのサイズをパネル分縮小する必要がある。
以下の全箇所で`_aide_width`を使うこと：

```python
_aide_width = 0  # グローバル変数

def get_rect(window, aide_w=0):
    return SIDEBAR_W, URLBAR_H, window.width - SIDEBAR_W - aide_w, window.height - URLBAR_H

# set_aide_width：_aide_widthを更新してWebViewを縮小
# sync()：100msタイマーでもaide_w=_aide_widthを使う
# on_resized()：リサイズ時もaide_w=_aide_widthを使う
# show_service()：サービス切替時もaide_w=_aide_widthを使う
```

### showEmpty（WebViewArea.tsx）
```tsx
const showEmpty = !activeServiceId;  // !activeServiceではなく!activeServiceId
```

### js_eval
```python
def js_eval(js: str):
    import threading
    def _eval():
        try:
            if webview.windows:
                webview.windows[0].evaluate_js(js)
        except:
            pass
    threading.Thread(target=_eval, daemon=True).start()
```

---

## 7. 未解決の問題

| 問題 | 状況 | 備考 |
|---|---|---|
| タイトルバーが消えない | 未解決 | xpropは実行されているがMutterが反映しない。本番パッケージ化時に再対処 |
| 日本語入力できない | 未解決 | QWebEngineViewでIMEが効かない。`os.environ["QT_IM_MODULE"] = "fcitx5"`は設定済み |
| Aideがページ内容を読めない | 未確認 | `get_page_text`は実装済み。InkAide.tsxのAPI呼び出しで使っているか要確認 |

---

## 8. 次のチャットでやること

### 優先度高
- [ ] 日本語入力の修正（QWebEngineViewのIME対応）
- [ ] Ink AideがページのテキストをAIに渡せているか確認・修正
- [ ] `get_page_text`の動作確認（Ollamaで要約が実際に動くか）

### 優先度中
- [ ] タイトルバー非表示（パッケージ化時に対処）
- [ ] Lite版の設計（サービス登録数制限・ライセンスキー方式）
- [ ] DEBパッケージ・AppImage化

### 将来の拡張
- ライセンスキー認証（退所後使用不可）
- Ollamaモデルのダウンロード進捗表示改善
- Ink Memory連携

---

## 9. 環境情報

| 項目 | 値 |
|---|---|
| Python | 3.12 |
| pywebview | 6.2.1 |
| PySide6 | 6.11.1 |
| Node.js | v22.22.2 |
| Vite | v8.0.14 |
| WM | Mutter(Budgie) |
| Viteポート | 5174（5173が使用中のため） |
| SIDEBAR_W | 208 |
| URLBAR_H | 40 |

---

## 10. 次のチャットに渡すファイル

- `main.py`
- `WebViewArea.tsx`
- `InkAide.tsx`
- `Sidebar.tsx`

---

*AI Creation, Human Care. The Future Drawn Together.*
*Ink Inc. 所長・黒井葉跡*
