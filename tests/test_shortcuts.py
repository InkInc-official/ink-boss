import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import types
# PySide6 が無い環境でもロジックだけ試せるようにスタブを入れる
try:
    import PySide6  # noqa
except Exception:
    for name in ("PySide6", "PySide6.QtCore", "PySide6.QtWidgets", "PySide6.QtGui"):
        sys.modules[name] = types.ModuleType(name)
    qc = sys.modules["PySide6.QtCore"]
    qc.QObject = object
    class _Q:  # ダミー
        pass
    qc.QEvent = _Q; qc.QTimer = _Q; qc.Qt = _Q
    qc.Signal = lambda *a, **k: None
    qc.Slot = lambda *a, **k: (lambda f: f)
    sys.modules["PySide6.QtWidgets"].QApplication = _Q
    sys.modules["PySide6.QtGui"].QKeySequence = _Q
    sys.modules["PySide6.QtGui"].QShortcut = _Q

import shortcuts as S


def make():
    log = []
    timers = []
    e = S.ShortcutEngine(
        dispatch=lambda a, arg: log.append((a, arg)),
        chord_changed=lambda act, text: log.append(("chord", act, text)),
        start_timer=lambda ms: timers.append(ms),
        stop_timer=lambda: timers.append("stop"),
    )
    return e, log, timers


def test_alt_digit_goto():
    e, log, _ = make()
    assert e.handle("Digit0", "a") and log == [("workspace-goto", 0)]
    assert e.handle("Digit7", "a") and log[-1] == ("workspace-goto", 7)
    assert not e.handle("Digit7", "")          # 修飾なしは通す
    assert not e.handle("Digit7", "ca")        # Ctrl+Alt+数字はOS用に触らない


def test_fixed_actions():
    e, log, _ = make()
    assert e.handle("KeyB", "ca") and log[-1] == ("sidebar-toggle", None)
    assert e.handle("Comma", "ca") and log[-1] == ("settings", None)
    assert e.handle("KeyE", "ca") and log[-1] == ("groups-toggle", None)
    assert e.handle("KeyK", "ca") and log[-1] == ("quick-switch", None)
    assert e.handle("KeyZ", "ca") and log[-1] == ("stop-all", None)
    assert e.handle("KeyH", "ca") and log[-1] == ("hibernate-current", None)
    assert not e.handle("KeyA", "ca")          # 未実装は通す
    assert not e.handle("KeyB", "c")


def test_chord_commit_enter():
    e, log, timers = make()
    assert e.handle("KeyN", "a") and e.chord_active
    assert e.handle("Digit1", "") and e.handle("Digit2", "")
    assert e.handle("Enter", "")
    assert log[-1] == ("workspace-goto", 12) and not e.chord_active
    assert ("chord", True, "12") in log and log[-2] == ("chord", False, "")


def test_chord_numpad_and_many_digits():
    e, log, _ = make()
    e.handle("KeyN", "a")
    for c in ("Numpad1", "Digit0", "Digit0"):
        assert e.handle(c, "")
    e.handle("Enter", "")
    assert log[-1] == ("workspace-goto", 100)


def test_chord_timeout_commits_or_cancels():
    e, log, _ = make()
    e.handle("KeyN", "a"); e.handle("Digit3", ""); e.on_timeout()
    assert log[-1] == ("workspace-goto", 3) and not e.chord_active
    e.handle("KeyN", "a"); e.on_timeout()      # 数字なしで時間切れ → 取消
    assert log[-1] == ("chord", False, "") and not e.chord_active


def test_chord_escape_backspace_and_other_key():
    e, log, _ = make()
    e.handle("KeyN", "a"); e.handle("Digit4", ""); assert e.handle("Escape", "")
    assert not e.chord_active and ("workspace-goto", 4) not in log
    e.handle("KeyN", "a"); e.handle("Digit4", ""); e.handle("Digit5", ""); e.handle("Backspace", "")
    e.handle("Enter", "")
    assert log[-1] == ("workspace-goto", 4)
    e.handle("KeyN", "a")
    assert not e.handle("KeyX", "")            # 他のキーは取消して通す
    assert not e.chord_active


def test_chord_alt_held():
    e, log, _ = make()
    e.handle("KeyN", "a"); assert e.handle("Digit2", "a"); e.handle("Enter", "")
    assert log[-1] == ("workspace-goto", 2)


def test_empty_enter_cancels():
    e, log, _ = make()
    e.handle("KeyN", "a"); assert e.handle("Enter", "")
    assert not e.chord_active and not any(x[0] == "workspace-goto" for x in log)


if __name__ == "__main__":
    n = 0
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); n += 1; print("ok", k)
    print(n, "passed")
