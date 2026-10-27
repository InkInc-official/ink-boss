"""
shortcuts.py - Ink Boss のキーボードショートカット
Ink Boss / Ink Inc.

【キー割り当て】（Webサービス側と衝突しにくい Alt / Ctrl+Alt 系のみ）
    Alt+0〜9            ワークスペースへ移動（0 = すべて、1〜 = プルダウンの番号）
    Alt+N → 数字 → Enter  10番以降へ移動（数字は何桁でも可。Enter か約1秒待つと確定、Escで取消）
    Ctrl+Alt+B          サイドバーの開閉
    Ctrl+Alt+,          設定を開く
    Ctrl+Alt+E          グループの全部開閉（トグル）
    Ctrl+Alt+K          クイック切替
    Ctrl+Alt+Z / H      全て休止 / 開いているサービスを休止
    （予定）Ctrl+Alt+A Aide

【作り】
- ShortcutEngine: Qt にも Electron にも依存しない純粋なロジック（tests/test_shortcuts.py で検証）
- ShortcutController: Qt の全キー入力を見張って Engine に渡す（Qt側）。
  Electron側のキーは main.js が stdout に出し、electron_bridge 経由で同じ Engine に入る。
- キーは (code, flags) に正規化する。
    code : "Digit5" / "KeyN" / "Comma" / "Enter" / "Escape" / "Backspace"
    flags: "c"=Ctrl "a"=Alt "s"=Shift "m"=Meta を c,a,s,m の順に並べた文字列（修飾なしは ""）

注意: Electron側は main.js 内に「転送するキーの一覧」を持つ（isShortcutCandidate）。
ここの割り当てを変えたら main.js も揃えること。
"""

import json

from PySide6.QtCore import QObject, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut

# 実装済みの機能だけを「消費」する（未実装のキーはそのままページへ渡す）
ACTIONS = {
    ("KeyB", "ca"): "sidebar-toggle",
    ("Comma", "ca"): "settings",
    ("KeyE", "ca"): "groups-toggle",
    # 以下は後の手順で実装:
    ("KeyK", "ca"): "quick-switch",
    ("KeyZ", "ca"): "stop-all",
    ("KeyH", "ca"): "hibernate-current",
    # ("KeyA", "ca"): "aide-toggle",
}

# 設定画面「ショートカット」タブに表示する一覧: (キー, 動作, 説明)
# 機能を追加したら、ここにも1行足すこと（ACTIONS と揃える）。
SHORTCUT_LIST = [
    ("Alt + 0", "「すべて」へ移動", "ワークスペースの「すべて」を開きます。"),
    ("Alt + 1〜9", "ワークスペースへ移動", "ワークスペースのプルダウンに出ている番号の画面を開きます。"),
    ("Alt + N → 番号 → Enter", "10番以降へ移動", "Alt+N を押したあと、番号を続けて入力します（桁数の上限なし）。"
     "Enter か約1秒待つと確定、Esc で取消。"),
    ("Ctrl + Alt + B", "サイドバーの開閉", "サイドバーを広げる／たたむ。"),
    ("Ctrl + Alt + E", "グループの全部開閉", "いま開いているワークスペースのグループを切り替えます。1つでも開いていれば全部たたみ、全部たたまれていれば全部開きます。"),
    ("Ctrl + Alt + K", "クイック切替", "検索窓を開き、サービス名・ワークスペース名で絞り込んで移動します。↑↓で選択、Enterで移動、Escで閉じる。"),
    ("Ctrl + Alt + Z", "全て休止", "いま開いているサービス以外を、すべて休止します。"),
    ("Ctrl + Alt + H", "開いているサービスを休止", "いま開いているサービスだけを休止します（Hibernate）。"),
    ("Ctrl + Alt + ,", "設定を開く", "この設定画面を開きます。"),
]

CHORD_START_IDLE_MS = 3000   # Alt+N のあと、最初の数字を待つ時間
CHORD_DIGIT_IDLE_MS = 1000   # 数字のあと、次の数字を待つ時間（過ぎたら確定）


def _digit_of(code: str):
    """Digit5 / Numpad5 → "5"。数字でなければ None。"""
    if len(code) > 1 and code[-1].isdigit() and code[:-1] in ("Digit", "Numpad"):
        return code[-1]
    return None


class ShortcutEngine:
    """キー1つを受け取り、「消費したか」を返す。副作用は引数のコールバックで行う。

    dispatch(action, arg)        : 機能の実行（"workspace-goto" / "sidebar-toggle" / "settings" ...）
    chord_changed(active, text)  : Alt+N 入力中の表示用（active=False で消す）
    start_timer(ms) / stop_timer(): 単発タイマー。時間切れで on_timeout() を呼ぶこと。
    """

    def __init__(self, dispatch, chord_changed, start_timer, stop_timer):
        self._dispatch = dispatch
        self._chord_changed = chord_changed
        self._start_timer = start_timer
        self._stop_timer = stop_timer
        self.chord_active = False
        self.buf = ""

    # ── 入口 ──
    def handle(self, code: str, flags: str) -> bool:
        if self.chord_active:
            return self._handle_chord(code, flags)
        return self._handle_idle(code, flags)

    def on_timeout(self) -> None:
        if not self.chord_active:
            return
        if self.buf:
            self._commit()
        else:
            self._cancel()

    # ── 通常時 ──
    def _handle_idle(self, code: str, flags: str) -> bool:
        if flags == "a":
            d = _digit_of(code)
            if d is not None:
                self._dispatch("workspace-goto", int(d))
                return True
            if code == "KeyN":
                self._chord_start()
                return True
            return False
        action = ACTIONS.get((code, flags))
        if action:
            self._dispatch(action, None)
            return True
        return False

    # ── Alt+N のあとの番号入力 ──
    def _chord_start(self) -> None:
        self.chord_active = True
        self.buf = ""
        self._chord_changed(True, "")
        self._start_timer(CHORD_START_IDLE_MS)

    def _handle_chord(self, code: str, flags: str) -> bool:
        if flags in ("", "a"):   # Alt を押したまま続けて数字でもよい
            d = _digit_of(code)
            if d is not None:
                self.buf += d
                self._chord_changed(True, self.buf)
                self._start_timer(CHORD_DIGIT_IDLE_MS)
                return True
            if code in ("Enter", "NumpadEnter"):
                if self.buf:
                    self._commit()
                else:
                    self._cancel()
                return True
            if code == "Escape":
                self._cancel()
                return True
            if code == "Backspace":
                self.buf = self.buf[:-1]
                self._chord_changed(True, self.buf)
                self._start_timer(CHORD_START_IDLE_MS if not self.buf else CHORD_DIGIT_IDLE_MS)
                return True
        # それ以外のキーは入力を取り消し、キー自体はそのまま通す
        self._cancel()
        return False

    def _commit(self) -> None:
        n = int(self.buf) if self.buf else None
        self._end()
        if n is not None:
            self._dispatch("workspace-goto", n)

    def _cancel(self) -> None:
        self._end()

    def _end(self) -> None:
        self._stop_timer()
        self.chord_active = False
        self.buf = ""
        self._chord_changed(False, "")


# ── Qt 側 ─────────────────────────────────────────────────
# 注意: QApplication 全体に Python の eventFilter を付ける方式は、Linux で
# メインループ中にセグフォを起こした（日本語入力との干渉も懸念）ため使わない。
# 代わりに Qt 標準の QShortcut（アプリ全体で有効）を使う。

class ShortcutController(QObject):
    # Electron の読み取りスレッドから呼ばれるため、Signal でQtメインスレッドへ渡す
    electron_key_signal = Signal(str, str)

    def __init__(self, qt_app, js_eval_fn, open_settings_fn, on_chord_changed=None):
        super().__init__(qt_app)
        self._js = js_eval_fn
        self._open_settings = open_settings_fn
        self._on_chord_changed = on_chord_changed  # (active: bool) → Electronへ通知する用
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self.engine = ShortcutEngine(
            dispatch=self._dispatch,
            chord_changed=self._chord_changed,
            start_timer=lambda ms: self._timer.start(ms),
            stop_timer=self._timer.stop,
        )
        self._timer.timeout.connect(self.engine.on_timeout)
        self.electron_key_signal.connect(self._on_electron_key)
        self.extra_actions = {}   # action名 → Python側で実行する関数（main.py で登録）
        self._fixed = []   # 常時有効
        self._chord = []   # Alt+N 入力中だけ有効
        self._attached = False

    def attach_when_ready(self, get_window, interval_ms: int = 500) -> None:
        """メインウィンドウができたら QShortcut を取り付ける（できるまで繰り返す）。"""
        def _try():
            try:
                w = get_window()
                if w is not None and not self._attached:
                    self._attach(w.window())
                    return
            except Exception as e:
                print(f"[shortcuts] attach: {e}", flush=True)
            QTimer.singleShot(interval_ms, _try)
        QTimer.singleShot(interval_ms, _try)

    def _mk(self, win, seq: str, code: str, flags: str, bucket: list, enabled=True):
        sc = QShortcut(QKeySequence(seq), win)
        sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc.setAutoRepeat(False)
        sc.activated.connect(lambda c=code, f=flags: self._on_qt_key(c, f))
        sc.setEnabled(enabled)
        bucket.append(sc)

    def _attach(self, win) -> None:
        self._attached = True
        for d in range(10):
            self._mk(win, f"Alt+{d}", f"Digit{d}", "a", self._fixed)
        self._mk(win, "Alt+N", "KeyN", "a", self._fixed)
        self._mk(win, "Ctrl+Alt+B", "KeyB", "ca", self._fixed)
        self._mk(win, "Ctrl+Alt+,", "Comma", "ca", self._fixed)
        self._mk(win, "Ctrl+Alt+K", "KeyK", "ca", self._fixed)
        self._mk(win, "Ctrl+Alt+Z", "KeyZ", "ca", self._fixed)
        self._mk(win, "Ctrl+Alt+H", "KeyH", "ca", self._fixed)
        self._mk(win, "Ctrl+Alt+E", "KeyE", "ca", self._fixed)
        # 番号入力中だけ有効にする（普段の入力を邪魔しない）
        for d in range(10):
            self._mk(win, str(d), f"Digit{d}", "", self._chord, enabled=False)
        for seq, code in (("Return", "Enter"), ("Enter", "Enter"), ("Esc", "Escape"), ("Backspace", "Backspace")):
            self._mk(win, seq, code, "", self._chord, enabled=False)
        print("[shortcuts] attached", flush=True)

    def _on_qt_key(self, code: str, flags: str) -> None:
        try:
            self.engine.handle(code, flags)
        except Exception as e:
            print(f"[shortcuts] {e}", flush=True)

    # ── Electron のキー入力（main.js → stdout → ここ）──
    @Slot(str, str)
    def _on_electron_key(self, code: str, flags: str) -> None:
        try:
            self.engine.handle(code, "" if flags == "-" else flags)
        except Exception as e:
            print(f"[shortcuts] {e}", flush=True)

    # ── 実行 ──
    def _dispatch(self, action: str, arg) -> None:
        if action == "settings":
            self._open_settings()
            return
        fn = self.extra_actions.get(action)
        if fn:
            fn()
            return
        detail = json.dumps({"action": action, "arg": arg})
        self._js(f"window.dispatchEvent(new CustomEvent('ink-shortcut',{{detail:{detail}}}));")

    def _chord_changed(self, active: bool, text: str) -> None:
        for sc in self._chord:
            sc.setEnabled(active)
        detail = json.dumps({"active": active, "text": text})
        self._js(f"window.dispatchEvent(new CustomEvent('ink-chord',{{detail:{detail}}}));")
        if self._on_chord_changed:
            try:
                self._on_chord_changed(active)
            except Exception:
                pass
