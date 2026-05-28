# Ink Aide コンテンツ表示問題 手続き書
## Ink Inc. 所長・黒井葉跡

---

## 問題の概要

Aideボタンを押すと右側に黒いパネルは表示されるが、
中のコンテンツ（クイックボタン・チャット欄・ヘッダー）が見えない。

---

## 原因

**2つの原因が重なっている。**

### 原因①：`showEmpty`が`true`になっている

`WebViewArea.tsx`の`showEmpty`が`!activeService`になっていると、
サービスが休止状態のままだと`activeService`がundefinedになり、
InkAideを含まない方のreturnが返される。

```tsx
// ❌ ダメ
const showEmpty = !activeService;
const showEmpty = !activeService || isHibernated;

// ✅ 正しい
const showEmpty = !activeServiceId;
```

### 原因②：`_aide_width`がmain.pyの全箇所で使われていない

`set_aide_width`は呼ばれてWebViewを縮小するが、
`sync()`タイマー（100ms）や`on_resized()`が`_aide_width`を無視して
元のサイズに戻し続けるため、InkAideパネルがWebViewに押しつぶされる。

---

## 確認手順

### ステップ1：`showEmpty`の確認

```bash
grep -n "showEmpty" ~/InkTools/ink-boss/frontend/src/components/WebViewArea.tsx
```

`!activeService`や`!activeService || isHibernated`になっていたら原因①。

### ステップ2：`_aide_width`の確認

```bash
grep -n "_aide_width\|get_rect" ~/InkTools/ink-boss/main.py
```

**正常な状態（5箇所以上あること）：**

```
○○○: _aide_width = 0                          ← グローバル変数
○○○: def get_rect(window, aide_w=0):           ← 引数あり
○○○: x, y, ww, h = get_rect(w, _aide_width)   ← show_service
○○○: x, y, ww, h = get_rect(w, _aide_width)   ← sync_geometry
○○○: x, y, w, h = get_rect(window, _aide_width) ← sync()タイマー
○○○: x, y, w, h = get_rect(window, _aide_width) ← on_resized()
```

`get_rect(w)`や`get_rect(window)`が1箇所でもあれば原因②。

### ステップ3：`set_aide_width`の確認

```bash
grep -n "def set_aide_width" ~/InkTools/ink-boss/main.py
```

**出力がなければ**`set_aide_width`自体が消えている。

---

## 修正手順

### 修正①：`showEmpty`を直す

```bash
python3 - << 'PYEOF'
with open('/home/hp/InkTools/ink-boss/frontend/src/components/WebViewArea.tsx', 'r') as f:
    content = f.read()

content = content.replace('  const showEmpty = !activeService;', '  const showEmpty = !activeServiceId;')
content = content.replace('  const showEmpty = !activeService || isHibernated;', '  const showEmpty = !activeServiceId;')

with open('/home/hp/InkTools/ink-boss/frontend/src/components/WebViewArea.tsx', 'w') as f:
    f.write(content)
print("完了")
PYEOF
```

### 修正②：`_aide_width`を全箇所に追加する

```bash
python3 - << 'PYEOF'
with open('/home/hp/InkTools/ink-boss/main.py', 'r') as f:
    lines = f.readlines()

# get_rect(w)を全てget_rect(w, _aide_width)に変える
fixed = 0
for i, line in enumerate(lines):
    if 'get_rect(w)' in line:
        lines[i] = line.replace('get_rect(w)', 'get_rect(w, _aide_width)')
        fixed += 1
    if 'get_rect(window)' in line and 'def get_rect' not in line:
        lines[i] = line.replace('get_rect(window)', 'get_rect(window, _aide_width)')
        fixed += 1

with open('/home/hp/InkTools/ink-boss/main.py', 'w') as f:
    f.writelines(lines)
print(f"完了: {fixed}箇所修正")
PYEOF
```

### 修正③：`set_aide_width`が消えている場合

```bash
python3 - << 'PYEOF'
with open('/home/hp/InkTools/ink-boss/main.py', 'r') as f:
    content = f.read()

if 'def set_aide_width' not in content:
    content = content.replace(
        '    def drag_window(self): pass\n',
        '''    def drag_window(self): pass

    def set_aide_width(self, width):
        global _aide_width
        _aide_width = int(width)
        w = webview.windows[0] if webview.windows else None
        if not w or not bridge.active_id: return
        x, y, ww, h = get_rect(w, _aide_width)
        bridge.show_view_signal.emit(bridge.active_id, x, y, ww, h)

    def get_page_text(self, service_id):
        if service_id not in bridge.views:
            return ""
        view = bridge.views[service_id]
        result = []
        import threading
        loop = threading.Event()
        def cb(text):
            result.append(text or "")
            loop.set()
        view.page().runJavaScript("document.body.innerText", cb)
        loop.wait(timeout=3.0)
        return result[0] if result else ""

'''
    )
    print("set_aide_width追加完了")
else:
    print("set_aide_width既に存在")

with open('/home/hp/InkTools/ink-boss/main.py', 'w') as f:
    f.write(content)
PYEOF
```

### 修正④：`_aide_width`グローバル変数が消えている場合

```bash
python3 - << 'PYEOF'
with open('/home/hp/InkTools/ink-boss/main.py', 'r') as f:
    content = f.read()

if '_aide_width = 0' not in content:
    content = content.replace(
        'config = load_config()\nbridge = ViewBridge(qt_app, config)',
        'config = load_config()\nbridge = ViewBridge(qt_app, config)\n_aide_width = 0'
    )
    print("_aide_width追加完了")
else:
    print("_aide_width既に存在")

if 'def get_rect(window, aide_w=0)' not in content:
    content = content.replace(
        'def get_rect(window):\n    return SIDEBAR_W, URLBAR_H, window.width - SIDEBAR_W, window.height - URLBAR_H',
        'def get_rect(window, aide_w=0):\n    return SIDEBAR_W, URLBAR_H, window.width - SIDEBAR_W - aide_w, window.height - URLBAR_H'
    )
    print("get_rect修正完了")
else:
    print("get_rect既に修正済み")

with open('/home/hp/InkTools/ink-boss/main.py', 'w') as f:
    f.write(content)
PYEOF
```

---

## 修正後の確認

```bash
# _aide_widthが5箇所以上あることを確認
grep -c "_aide_width" ~/InkTools/ink-boss/main.py

# showEmptyがactiveServiceIdになっていることを確認
grep "showEmpty" ~/InkTools/ink-boss/frontend/src/components/WebViewArea.tsx

# 再起動
pkill -f vite 2>/dev/null
fuser -k 5173/tcp 5174/tcp 2>/dev/null
sleep 1
npm run dev --prefix frontend &
sleep 4
python3 main.py
```

サービスをクリック → Aideボタンを押す → パネルにコンテンツが表示されればOK。

---

## まとめ

| チェック項目 | 確認コマンド | 正常な値 |
|---|---|---|
| showEmpty | `grep showEmpty WebViewArea.tsx` | `!activeServiceId` |
| _aide_width箇所数 | `grep -c "_aide_width" main.py` | 5以上 |
| set_aide_width存在 | `grep -n "def set_aide_width" main.py` | 1行ヒット |
| get_rect引数 | `grep "def get_rect" main.py` | `aide_w=0`あり |

---

*AI Creation, Human Care. The Future Drawn Together.*
*Ink Inc. 所長・黒井葉跡*
