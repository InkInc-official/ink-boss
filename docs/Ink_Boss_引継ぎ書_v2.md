# Ink Boss 開発引継ぎ書 v2
## Ink Inc. 所長・黒井葉跡

> AI Creation, Human Care. The Future Drawn Together.

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
// 休止中ダブルクリック時
if (hibernatedIds.has(service.id)) {
  await window.pywebview?.api?.show_service(service.id);
  setActiveService(service.id);  // ← これが必須
  return;
}
```

### setIntervalを使わない
JS側のsetIntervalでsync_geometryを呼ぶコードは削除済み。
on_resizedで対応しているため不要。

---

## 5. 設定画面（Python側QDialog）

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

## 6. Ink Aide

### 機能
- URLバー右の「Aide」ボタンで開閉（幅320px）
- `set_aide_width`でWebViewを縮小
- 起動時にOllama接続確認→「✓ Aide OK」緑表示
- クリアボタンでloading状態もリセット

### クイックボタン3つ
1. **要約** → 「このページの内容を日本語で簡潔に要約してください。」
2. **ポイント** → 「このページの重要なポイントを日本語で箇条書きにしてください。」
3. **感想** → ナレッジ+「このページの内容について、私の立場から見た活用方法や感想を日本語で教えてください。」

### ナレッジ置換（未解決）
感想プロンプトに`__KNOWLEDGE__`プレースホルダーを使い、
送信時にconfig.knowledgeで置換する実装が入っているが、
**チャット吹き出しに`__KNOWLEDGE__`が表示されたままになっている**。

原因：`resolvedPrompt`の置換処理がInkAide.tsxの71行目に入っているが効いていない。

修正すべきコード（InkAide.tsx 71行目付近）：
```tsx
const resolvedPrompt = prompt.includes("__KNOWLEDGE__")
  ? prompt.replace("__KNOWLEDGE__", knowledge ? `私は${knowledge}。\n\n` : "")
  : prompt;
const fullPrompt = pageText
  ? `ページ内容：\n${pageText.slice(0, 2000)}\n\n${resolvedPrompt}`
  : resolvedPrompt;
```

---

## 7. 未解決の問題

| 問題 | 状況 | 備考 |
|---|---|---|
| __KNOWLEDGE__が消えない | 未解決 | resolvedPromptの置換が効いていない |
| タイトルバーが消えない | 保留 | Mutter(Budgie)+Qtの制限。パッケージ化時に対処 |
| 日本語入力できない | 未解決 | QWebEngineViewでIMEが効かない |
| URLバーのドラッグ移動 | 未解決 | WebViewのraise_()でTopBarのマウスイベントが届かない |
| Google検索結果のサイトが開かない | 未解決 | 不明 |


---

## 8. 次のチャットでやること

### 優先度高
- [ ] `__KNOWLEDGE__`置換問題の修正（InkAide.tsxを丸ごと書き直すのが確実）
- [ ] 日本語入力の修正

### 優先度中
- [ ] 設定コンポーネント化（main.pyが肥大化）
- [ ] タイトルバー非表示（パッケージ化時）

### 将来の拡張
- Lite版（サービス登録数制限・ライセンスキー認証）
- DEBパッケージ・AppImage化・EXEパッケージ

---

## 9. 次のチャットに渡すファイル

- `main.py`
- `WebViewArea.tsx`
- `InkAide.tsx`
- `Sidebar.tsx`

---

*AI Creation, Human Care. The Future Drawn Together.*
*Ink Inc. 所長・黒井葉跡*
