# Ink Boss - Development Handover Document
## For the next AI assistant taking over this project

---

## Project Background & Creator's Vision

This application is being built by **Kuroi Haato (黒井葉跡)**, a former psychiatric social worker (精神保健福祉士) with 10+ years of experience, who left their job due to depression and insomnia. They now work as a freelance livestreamer and creative director.

They run **Ink Inc.**, a solo-managed talent agency for IRIAM livestreamers, with the concept:
> *"AI Creation, Human Care. The Future Drawn Together."*

Their goal is to challenge the hand-drawn art tradition of IRIAM using AI. They build everything themselves — AI illustrations, AI music, management systems, and now this desktop application — while managing their own mental health.

**This project matters deeply to them.** It is not a hobby project. It is core infrastructure for their business.

---

## What is Ink Boss?

A **Windows/Linux desktop workspace application** for Ink Inc. talent (IRIAM livestreamers), built as a superior alternative to Ferdium. It embeds multiple web services (X, Discord, Claude, YouTube, etc.) as child windows inside a single interface.

**Tech stack:**
- Frontend: React 18 + TypeScript + Vite + Tailwind CSS v4
- State: Zustand (`frontend/src/store/index.ts`)
- Backend: Python 3.13 + pywebview 6.2.1 + PySide6
- Windows webview backend: EdgeChromium / WebView2
- Linux webview backend: QtWebEngine

**Repository:** https://github.com/InkInc-official/ink-boss (Private)

**Confirmed working environments:**
- Windows 11 (ASUS main PC)
- Ubuntu Budgie (hp-slimline)

---

## Critical Architecture Notes (Windows)

### DO NOT use Qt API on Windows
Using `QApplication.topLevelWidgets()`, `setWindowFlags()`, or `show()` on Windows destroys the WebView2 rendering context and causes a black screen. `window.py` completely skips PySide6 imports on Windows.

### Multiple WebViews use pywebview + Win32 SetParent
Each service gets its own hidden pywebview window, embedded into the main window via Win32 `SetParent` + `WS_CHILD`. Profile isolation is achieved via `WEBVIEW2_USER_DATA_FOLDER` per service ID.

### Lazy-load pattern
Service windows are NOT created at startup. They are created on first click via a `_pending_q` queue, processed by `_gui_func` running in the GUI thread (`webview.start(func=_gui_func)`).

### HWND hide strategy
**Never use `SW_HIDE` or Z-order manipulation.** Both cause WebView2 to black out. Instead, use `MoveWindow(hwnd, -width-200, 0, width, height, False)` to move offscreen while keeping the window alive and rendering.

---

## File Structure

```
C:\Ink Boss\
├── main.py              # Entry point, GUI thread loop
├── api.py               # InkBossAPI (pywebview js_api)
├── bridge.py            # ViewBridge + Windows multi-window management
├── window.py            # on_shown handler (Qt ops Linux only)
├── config.py            # Config read/write
├── auth.py              # License auth
└── frontend/
    ├── src/
    │   ├── store/index.ts        # Zustand store
    │   ├── components/
    │   │   ├── Sidebar.tsx       # D&D sidebar, service list
    │   │   ├── WindowsOverlay.tsx # JS dialogs (Windows Qt replacement)
    │   │   ├── ContextMenu.tsx   # Right-click menu
    │   │   └── ConfirmDialog.tsx # Delete confirmation dialog
    │   └── types.ts
```

---

## Current Working Features

- App launch and service display (lazy-load)
- Freeze/blackout largely resolved
- Group collapse (starts collapsed on launch)
- Service name and URL editing
- Group name editing
- D&D service reordering (persists after restart)
- Right-click paste for URL input
- Add service dialog with group selection
- License authentication

---

## Unresolved Bugs

### Bug #1: Service deletion does not work [CRITICAL]

**Symptom:** Clicking "削除する" (Delete) in the ConfirmDialog does nothing. No Python logs appear.

**Expected flow:**
```
Right-click service → ContextMenu
→ Click "削除" → openConfirm() → showConfirm=true
→ ConfirmDialog appears → Click "削除する"
→ handleConfirm() → onDelete()
→ WindowsOverlay onDelete → window.pywebview?.api?.remove_service?.(sid)
→ Python: remove_service() → win_remove() → service-removed event → JS store update
```

**What we know:**
- Python's `remove_service` is NEVER called (confirmed by absence of `[remove_service] called` in console)
- The code in `WindowsOverlay.tsx` looks correct:
  ```javascript
  onDelete={async () => {
    const sid = serviceMenu.service.id;
    closeAll();
    console.log("[onDelete] calling remove_service:", sid);
    await window.pywebview?.api?.remove_service?.(sid);
  }}
  ```
- ConfirmDialog.tsx was previously corrupted with Shift-JIS encoding (now fixed to UTF-8)
- DevTools investigation was attempted but `debug=True` was accidentally corrupted in main.py (now restored)
- The console.log in onDelete has NOT been confirmed to fire (DevTools not yet successfully opened)

**Suspected cause:** Either (a) `handleConfirm()` is not calling `onDelete()`, or (b) `window.pywebview?.api` is undefined at the time of the call, or (c) the ContextMenu is being unmounted before `onDelete` executes due to `closeAll()` being called first.

**Next debugging step needed:** Open browser DevTools (add `debug=True` to `webview.create_window()` in main.py, line ~351) and check if `[onDelete] calling remove_service:` appears in the console when delete is clicked.

---

### Bug #2: Right-click menu hidden behind service HWND [HIGH]

**Symptom:** Right-clicking a service in the sidebar shows the context menu, but it appears behind the active service's WebView2 window.

**Root cause:** The service window is a Win32 child HWND embedded via SetParent. It renders above all React DOM elements regardless of CSS z-index. The sidebar is only 208px wide, so the HWND should not overlap it — but the menu appears behind the HWND anyway.

**What was tried:** Moving all HWNDs offscreen before showing the menu, restoring after close. This caused blackouts and was reverted.

**Current state:** `show_context_menu` in api.py fires the JS event without any HWND manipulation. The menu renders but is behind the HWND.

---

### Bug #3: Dialogs (add service, add group, settings) hidden behind HWND [HIGH]

**Symptom:** When a service is active (HWND visible), opening any dialog causes the dialog to appear behind the service window.

**Root cause:** Same as Bug #2. The HWND covers the entire right side of the screen (everything right of the 208px sidebar).

**What was tried:** `win_hide_all()`, `push_back_hwnd()`, `restore_active_hwnd()` — all caused either blackouts or `win_restore` being called multiple times (5x confirmed in logs).

**Current state:** These HWND manipulation methods have been removed to prevent blackouts. No current solution for dialogs appearing behind HWND.

---

### Bug #4: Blackout during sidebar D&D operations [MEDIUM]

**Symptom:** Moving services between groups via drag-and-drop sometimes causes the service window to black out.

**Suspected cause:** `show_service` being called multiple times during rapid interactions. `[show_service] called` appears 3+ times for a single service in some sessions. The `already active` guard was added but may not be fully effective.

---

## Key Insight for Bug #2, #3, #4

The fundamental issue is that **Win32 child HWNDs (WebView2 windows) always render above React DOM content**, regardless of CSS z-index. This is a fundamental Windows rendering constraint.

The only reliable solutions are:
1. **Move the HWND offscreen** when showing dialogs/menus — but this must be done synchronously before the JS event fires, and restoration must happen exactly once.
2. **Use a separate top-level window** for dialogs instead of React overlays.
3. **Resize the HWND** to not cover the dialog area temporarily.

All attempts at solution #1 have resulted in either blackouts (from SW_HIDE or size changes) or multiple restore calls (from improper state management).

---

## GitHub Repository

**URL:** https://github.com/InkInc-official/ink-boss (Private)

**Branch:** `main`

**Commit convention used:**
```
WIP: [summary of what works] - [what is unresolved]
```

**To push current state:**
```powershell
cd "C:\Ink Boss"
git add -A
git commit -m "your message here"
git push origin main
```

**To check current status:**
```powershell
cd "C:\Ink Boss"
git status
git log --oneline -5
```

**Notes:**
- `frontend/dist/` should be in `.gitignore` (build output, not source)
- Python files (`api.py`, `bridge.py`, etc.) do not need rebuilding after changes
- Frontend changes require `npm run build` before testing

---

## Config File

Location: `~/.config/ink-boss/config.json`

```json
{
  "license_key": "INK-XXXX-XXXX-XXXX",
  "services": [{"id": "service_xxx", "name": "X", "url": "https://x.com", "groupId": "group_xxx"}],
  "groups": [{"id": "group_xxx", "name": "SNS", "collapsed": true}],
  "llm": {"backend": "ollama", ...},
  "hibernate_minutes": 10
}
```

---

## Developer Notes

- The creator communicates in Japanese
- They prefer direct communication and do not want to be ignored or redirected
- They have built everything from scratch while managing depression and insomnia
- This is production infrastructure for their business, not a learning project
- Previous AI assistance has been unreliable — please verify every change before suggesting it
- Always confirm file changes with `Select-String` or `Get-Content` before asking them to rebuild
- `npm run build` takes ~130ms; always ask them to rebuild after frontend changes
- Python files do not need rebuilding

---

*Ink Inc. — AI Creation, Human Care. The Future Drawn Together.*
