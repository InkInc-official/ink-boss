# Ink Hub セカンドオピニオン（技術 × 思想 × 実装性）

---

## 🎯 結論（最重要ポイント）
Ink Hub の要件（Googleログイン突破・セッション分離・OSS・軽量・Electron不使用）をすべて満たす最適解は、  
**現時点では *PySide6 + QtWebEngine* が唯一の現実解。**

Tauri v2 は軽量で美しいが、  
**WebView 廃止 + WebKitGTK の制約 + Googleログイン不可**  
という三重苦により、Ink Hub の思想と要件を満たせない。

---

## 1. Tauri v2 で WebView を正しく動かす方法はあるか
結論：**WebviewWindow 以外に方法は存在しない。**

Tauri v2 の仕様変更により：

- `<webview>` タグ → 完全廃止  
- React 内に埋め込む WebView → 技術的に不可能  
- Ubuntu 24.04 の WebKitGTK → 埋め込みブラウザ扱いで真っ黒  

つまり Ink Hub の UI（左サイドバー + 中央にサービス表示）と  
**Tauri v2 の構造は根本的に相性が悪い。**

---

## 2. Ubuntu 24.04 で Googleログインを突破できる最適解

Google は「埋め込みブラウザ」を検出してログインを拒否する。

| フレームワーク | Googleログイン | 理由 |
|---|---|---|
| Tauri v2 | ❌ | WebKitGTK は埋め込み扱い |
| Wails | ❌ | 同上 |
| CEF | ◎ | Chromium そのもの |
| Chromium ラッパー | ◎ | 本物のブラウザ |
| **PySide6 + QtWebEngine** | **◎** | Chromium ベースで通る |

**Chromium 系以外は Googleログインを突破できない。**  
その中で OSS・軽量・実装容易なのが QtWebEngine。

---

## 3. PySide6 + QtWebEngine vs Tauri WebviewWindow

### パフォーマンス
- **Tauri**：最軽量（WebKitGTK）  
- **QtWebEngine**：Chromiumなので重いが Electron より軽い  

### 実装難易度
**Tauri WebviewWindow**
- 各サービスを別ウィンドウで管理  
- React と連携が複雑  
- セッション分離は自前実装  
- UI が Ink Hub の思想と乖離  

**PySide6 + QtWebEngine**
- **QWebEngineProfile で 1行でセッション分離**  
- Googleログインが素通り  
- Python なので Ink Memory と統合しやすい  
- OSS としてクリーン  

### 結論
**Tauri は軽いが Ink Hub の要件を満たせない。  
QtWebEngine は重いが要件をすべて満たす。**

---

## 4. 他に見落としている選択肢

### Neutralino.js
- 軽いが WebKitGTK → Googleログイン不可

### Ultralight
- 超軽量だが Googleログイン不可  
- OSS ではない

### Flutter WebView
- Linux 版は WebKitGTK → Googleログイン不可

### CEF Python
- Chromium そのもの  
- ただし重い・C++ の知識が必要  
- QtWebEngine の方が扱いやすい

---

## 5. セッション分離 + Googleログインを両立する最もシンプルな方法

QtWebEngine の **QWebEngineProfile** が圧倒的に最強。

```python
profile = QWebEngineProfile("service_123")
view = QWebEngineView()
view.setPage(QWebEnginePage(profile, view))
これだけで：

Cookie 分離

LocalStorage 分離

IndexedDB 分離

Googleログイン通過

サービスごとの独立セッション

Tauri ではこのレベルの分離は Rust + JS で自前実装が必要。

6. Ink Hub の思想に最も合う構造
Ink Hub の哲学：

レシピレス

軽量

OSS

構造美

AI統合

セッション分離

Googleログイン突破

これらを満たす構造は以下。

コード
UI：PySide6（Qt Widgets or QML）
WebView：QtWebEngine（Chromium）
セッション：QWebEngineProfile
AI：Python（Ollama/Claude/Gemini）
設定：JSON
Ink Memory と同じ Python 生態系で統一できるため、
Ink Inc. 全体の思想とも一致する。

7. 最終提案（思想 × 技術 × 実装性の統合）
Ink Hub は「Tauri で軽量を追う」段階を卒業し、
「QtWebEngine で確実に動く構造美」を採用すべき。

軽量さは重要だが、
Googleログイン・セッション分離・OSS・マルチサービス  
という要件は Chromium 系でしか成立しない。

そして Chromium 系の中で最も美しいのが QtWebEngine。

8. 次のステップ（推奨アクション）
PySide6 で最小 WebView プロトタイプを作る

QtWebEngine でセッション分離の実験をする

Ink Hub の新アーキテクチャ設計をまとめる