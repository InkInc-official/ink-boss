"""
bridge.py - ViewBridge
Ink Boss / Ink Inc.

QWebEngineViewの生成・表示・休止・復帰・削除を管理する。
JS↔Pythonのシグナル橋渡しもここで行う。
"""

import json
import re
import threading
import time
import traceback
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineSettings, QWebEngineNewWindowRequest,
    QWebEngineScript, QWebEngineUrlRequestInterceptor
)
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QRect, Qt, QUrl

from config import SESSIONS_DIR, save_config
from dialogs.settings     import show_settings_dialog
from dialogs.add_service  import show_add_service_dialog
from dialogs.add_group    import show_add_group_dialog
from dialogs.context_menu import show_service_context_menu, show_group_context_menu
from sysenv import get_clean_subprocess_env

Q = Qt.ConnectionType.QueuedConnection

# グローバル参照（window.pyで初期化後セット）
_win_id: str | None = None

# UA偽装に使うChromeバージョン番号のフォールバック値。
# 実行時検出（_detect_chrome_version）が失敗した場合のみ使われる。
_UA_CHROME_VERSION_FALLBACK = "140.0.0.0"
_spoofed_chrome_version: str | None = None  # フルバージョン文字列。プロセス内で一度だけ検出してキャッシュ
_spoofed_user_agent: str | None = None


def _detect_chrome_version() -> str:
    """実際にQtWebEngineが内部で使っているChromiumのフルバージョン
    文字列（例: "140.0.0.0"）を実行時に検出する。

    以前はChromeバージョン番号をハードコードしていたが、実際に
    QtWebEngineが内部で使っているChromiumのバージョンとの間に乖離が
    生じ（例: 実際は140系なのにUAは124と自己申告）、Google等の高度な
    ボット検知に「UAと実挙動が食い違う偽装ブラウザ」と判定される原因
    になっていたことが判明した（実機で確認済み）。
    そのため、UA上書きなしのデフォルトQWebEngineProfileが返す本物の
    UA文字列からバージョン番号を実行時に抽出する。取得に失敗した場合
    のみフォールバック値を使う。結果はプロセス内でキャッシュする
    （バージョンは実行中に変わらない）。UA文字列本体だけでなく、
    Sec-CH-UA系ヘッダーやnavigator.userAgentData.brandsもこの同じ
    バージョンを使って組み立て、すべての自己申告を一致させる。
    """
    global _spoofed_chrome_version
    if _spoofed_chrome_version is not None:
        return _spoofed_chrome_version

    version = _UA_CHROME_VERSION_FALLBACK
    detected_from = "fallback（検出失敗）"
    try:
        default_ua = QWebEngineProfile.defaultProfile().httpUserAgent()
        m = re.search(r"Chrome/([\d.]+)", default_ua)
        if m:
            version = m.group(1)
            detected_from = f"実行時検出（元UA: {default_ua}）"
    except Exception as e:
        print(f"[bridge] Chromeバージョン検出失敗: {e}", flush=True)

    _spoofed_chrome_version = version
    print(f"[bridge] UA用Chromeバージョン: {version} ({detected_from})", flush=True)
    return version


def _spoofed_major_version() -> str:
    """メジャーバージョンのみ（例: "140"）。Sec-CH-UAやuserAgentData.brands
    はメジャーバージョンだけを使うのが実際のChromeの挙動に合う。"""
    return _detect_chrome_version().split(".")[0]


def _build_spoofed_user_agent() -> str:
    """「独立した本物のブラウザ」に見せるためのUser-Agent文字列を組み立てる。"""
    global _spoofed_user_agent
    if _spoofed_user_agent is not None:
        return _spoofed_user_agent

    version = _detect_chrome_version()
    _spoofed_user_agent = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{version} Safari/537.36"
    )
    print(f"[bridge] 設定するUA文字列: {_spoofed_user_agent}", flush=True)
    return _spoofed_user_agent


class _StealthRequestInterceptor(QWebEngineUrlRequestInterceptor):
    """QtWebEngineが内部生成するSec-CH-UA系ヘッダーは、setHttpUserAgent()
    では書き換えられず「Chromium」であることを正直に自己申告してしまう
    （navigator.userAgent側の「Chrome」偽装と矛盾し、Googleのボット
    検知シグナルになっていたことを実機で確認済み）。実際に送信される
    直前でこれらのヘッダーを書き換え、UA文字列と整合させる。"""

    def __init__(self, major_version: str, parent=None):
        super().__init__(parent)
        self._sec_ch_ua = (
            f'"Not)A;Brand";v="99", "Google Chrome";v="{major_version}", '
            f'"Chromium";v="{major_version}"'
        ).encode()

    def interceptRequest(self, info):
        info.setHttpHeader(b"Sec-CH-UA", self._sec_ch_ua)
        info.setHttpHeader(b"Sec-CH-UA-Mobile", b"?0")
        info.setHttpHeader(b"Sec-CH-UA-Platform", b'"Linux"')


_stealth_interceptor: "_StealthRequestInterceptor | None" = None


def _get_stealth_interceptor(qt_app) -> "_StealthRequestInterceptor":
    """全プロファイル共通の単一インスタンス（ヘッダー内容は全サービス
    共通のため）。Cで保持される生ポインタが早期GCされないよう、
    qt_appを親に持たせてPython参照も保つ。"""
    global _stealth_interceptor
    if _stealth_interceptor is None:
        _stealth_interceptor = _StealthRequestInterceptor(_spoofed_major_version(), qt_app)
    return _stealth_interceptor


def _build_stealth_script(major_version: str) -> str:
    """navigator.userAgentData.brands / window.chrome / navigator.plugins /
    navigator.mimeTypes を、独立した本物のGoogle Chromeに近い内容に
    書き換える注入スクリプト。DocumentCreation時にMainWorldで実行する
    （ページ自身のスクリプトから見える必要があるため）。
    各項目は個別にtry/catchし、1つが失敗しても他に影響しないようにする。
    """
    return f"""
(() => {{
  const MAJOR = "{major_version}";

  // 1. navigator.userAgentData.brands をSec-CH-UAヘッダーと一致させる。
  //    navigator.userAgentData は毎回アクセスごとに新しいオブジェクトを
  //    生成する（同一インスタンスではない）ため、一度取得したインスタンス
  //    のプロパティを上書きしても次のアクセスでは反映されない（実機で
  //    確認済み）。そのため Navigator.prototype の userAgentData ゲッター
  //    自体を上書きし、本物のゲッターが返す新しいインスタンスを毎回
  //    その場でパッチしてから返すようにする。
  try {{
    const proto = Object.getPrototypeOf(navigator);
    const origDesc = Object.getOwnPropertyDescriptor(proto, 'userAgentData');
    if (origDesc && origDesc.get) {{
      const origGetter = origDesc.get;
      const brands = [
        {{ brand: "Not)A;Brand", version: "99" }},
        {{ brand: "Google Chrome", version: MAJOR }},
        {{ brand: "Chromium", version: MAJOR }}
      ];
      Object.defineProperty(proto, 'userAgentData', {{
        get() {{
          const real = origGetter.call(this);
          if (!real) return real;
          try {{
            Object.defineProperty(real, 'brands', {{
              get: () => brands.map(b => ({{ ...b }})),
              configurable: true
            }});
            const origGHEV = real.getHighEntropyValues ? real.getHighEntropyValues.bind(real) : null;
            real.getHighEntropyValues = async (hints) => {{
              const base = origGHEV ? await origGHEV(hints) : {{}};
              return {{
                ...base,
                brands: brands.map(b => ({{ ...b }})),
                fullVersionList: brands.map(b => ({{ brand: b.brand, version: `${{MAJOR}}.0.0.0` }})),
                uaFullVersion: `${{MAJOR}}.0.0.0`
              }};
            }};
            // toJSON はネイティブ実装だとbrandsパッチを素通りして未パッチの
            // 内部値を漏らす（実機で確認済み）ため、同じ内容で上書きする。
            real.toJSON = () => ({{
              brands: brands.map(b => ({{ ...b }})),
              mobile: real.mobile,
              platform: real.platform
            }});
          }} catch (_) {{}}
          return real;
        }},
        configurable: true
      }});
    }}
  }} catch (_) {{}}

  // 2. window.chrome の充実化（存在すること自体が重要な最低限のプロパティ）
  try {{
    window.chrome = window.chrome || {{}};
    if (!window.chrome.runtime) {{
      window.chrome.runtime = {{
        connect: function () {{}},
        sendMessage: function () {{}},
        id: undefined
      }};
    }}
    if (!window.chrome.loadTimes) window.chrome.loadTimes = function () {{ return {{}}; }};
    if (!window.chrome.csi) window.chrome.csi = function () {{ return {{}}; }};
    if (!window.chrome.app) window.chrome.app = {{ isInstalled: false }};
  }} catch (_) {{}}

  // 3. navigator.plugins / navigator.mimeTypes の充実化
  //    非ヘッドレスの本物Chromeがデフォルトで持つPDFビューア系エントリを模す。
  //    本物のPluginArray/Plugin等はホストオブジェクトであり、
  //    (a) 内部スロットを要求するネイティブメソッド（refresh()等）を
  //        素のオブジェクトに対して呼ぶと "Illegal invocation" で例外、
  //    (b) インデックスや各プロパティは列挙不可（for-in/JSON.stringifyに
  //        出てこない）ため、プレーンオブジェクトのまま代入すると
  //        列挙可能になってしまい、plugin⇔mimeType の相互参照で
  //        JSON.stringify等が循環構造エラーを投げる
  //    ことを実機で確認した（実際にSpellAIログイン後の白画面の原因に
  //    なっていた）。そのため全ての合成プロパティを非列挙にし、
  //    refresh()等も自前のno-opで上書きして本物のふるまいに近づける。
  try {{
    const hide = (obj, key, value) => Object.defineProperty(obj, key, {{
      value, enumerable: false, configurable: true, writable: true
    }});

    const pluginDefs = [
      [ "PDF Viewer", "internal-pdf-viewer" ],
      [ "Chrome PDF Viewer", "internal-pdf-viewer" ],
      [ "Chromium PDF Viewer", "internal-pdf-viewer" ],
      [ "Microsoft Edge PDF Viewer", "internal-pdf-viewer" ],
      [ "WebKit built-in PDF", "internal-pdf-viewer" ]
    ];
    const description = "Portable Document Format";

    const fakeMimeTypesList = [];
    const fakePluginsList = pluginDefs.map(([ name, filename ]) => {{
      const plugin = Object.setPrototypeOf({{}}, Plugin.prototype);
      const mime = Object.setPrototypeOf({{}}, MimeType.prototype);
      hide(plugin, 'name', name);
      hide(plugin, 'filename', filename);
      hide(plugin, 'description', description);
      hide(plugin, 'length', 1);
      hide(mime, 'type', "application/pdf");
      hide(mime, 'suffixes', "pdf");
      hide(mime, 'description', description);
      hide(mime, 'enabledPlugin', plugin);
      hide(plugin, '0', mime);
      hide(plugin, 'item', i => (i === 0 ? mime : null));
      hide(plugin, 'namedItem', n => (n === "application/pdf" ? mime : null));
      hide(plugin, 'toString', () => "[object Plugin]");
      hide(mime, 'toString', () => "[object MimeType]");
      fakeMimeTypesList.push(mime);
      return plugin;
    }});

    const makeArrayLike = (list, proto, typeName) => {{
      const arr = Object.setPrototypeOf({{}}, proto);
      list.forEach((item, i) => hide(arr, i, item));
      hide(arr, 'length', list.length);
      hide(arr, 'item', i => list[i] || null);
      hide(arr, 'namedItem', name => list.find(x => x.name === name || x.type === name) || null);
      hide(arr, 'refresh', () => {{}}); // 本物も現行仕様ではno-op。素のオブジェクトでネイティブ実装を呼ぶと例外になるため上書きする
      hide(arr, Symbol.iterator, function* () {{ yield* list; }});
      hide(arr, 'toString', () => `[object ${{typeName}}]`);
      return arr;
    }};

    const fakePlugins = makeArrayLike(fakePluginsList, PluginArray.prototype, 'PluginArray');
    const fakeMimeTypes = makeArrayLike(fakeMimeTypesList, MimeTypeArray.prototype, 'MimeTypeArray');

    Object.defineProperty(navigator, 'plugins', {{ get: () => fakePlugins, configurable: true }});
    Object.defineProperty(navigator, 'mimeTypes', {{ get: () => fakeMimeTypes, configurable: true }});
  }} catch (_) {{}}
}})();
"""

# Ink Bossの表示エリアに対してページが等倍(100%)だと大きく表示され、
# はみ出したり見づらくなったりするサイトがあったため、デフォルトで
# 少し縮小して表示する。サービスごとに config.json の
# services[].zoomFactor で上書き可能
#（例: {"zoomFactor": 1.0} と設定すればそのサービスだけ等倍に戻せる）。
# 画面リサイズに応じた再計算は行わない固定値（要件どおりシンプルに）。
DEFAULT_ZOOM_FACTOR = 0.9


def _get_zoom_factor(config: dict, sid: str) -> float:
    svc = next((s for s in config.get("services", []) if s["id"] == sid), None)
    zf = (svc or {}).get("zoomFactor")
    if isinstance(zf, (int, float)) and zf > 0:
        return float(zf)
    return DEFAULT_ZOOM_FACTOR


def set_win_id(wid: str) -> None:
    global _win_id
    _win_id = wid


def get_win_id() -> str | None:
    return _win_id


def find_own_window_id(title_substr: str) -> str | None:
    """`wmctrl -lp`の出力から、タイトルにtitle_substrを含み、かつ
    実際に自プロセス(os.getpid())が所有するウィンドウのIDを返す。

    以前はタイトルの部分一致だけ（`wmctrl -l`でtitle_substrを含む
    最初の行を無条件採用）で判定しており、次の2パターンで無関係な
    ウィンドウを「自分のウィンドウ」として誤って掴んでしまう実害の
    あるバグがあった（いずれも実機で確認済み）:
      1. Ink Bossを複数インスタンス同時起動した場合、後から起動した
         方が先に起動していた別インスタンスのウィンドウを誤って掴む
      2. 無関係な外部アプリ（例: 実Ecosiaブラウザ等）のウィンドウ
         タイトルに、たまたまtitle_substrと同じ文字列が含まれていた
         場合（例: ブラウザでInk Boss関連のページを開いている等）に、
         そのアプリのウィンドウを誤って掴んでしまう。一度これが
         起きると、以降そのウィンドウIDを使う全ての操作（IME用の
         フォーカス強制、タイトルバードラッグでの移動）が、Ink Boss
         自身ではなく無関係な外部アプリの方に対して実行され続ける
         （実機で、コンテンツ領域に実Ecosiaブラウザが透けて見え、
         ドラッグすると実Ecosiaブラウザが動く、という形で確認済み）。

    自プロセス自身はサンドボックスされていないため_NET_WM_PIDは
    常に正しいホスト側PIDを報告する（_get_own_window_ids/
    main.pyの説明と同じ前提）。タイトル一致に加えてPID一致も
    要求することで、上記どちらのケースも確実に排除できる。"""
    import os
    import subprocess
    from sysenv import get_clean_subprocess_env

    try:
        result = subprocess.run(
            ["wmctrl", "-lp"], capture_output=True, text=True,
            env=get_clean_subprocess_env(), timeout=2.0,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    my_pid = os.getpid()
    for line in result.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 3:
            continue
        try:
            win_pid = int(parts[2])
        except ValueError:
            continue
        if win_pid == my_pid and title_substr in line:
            return parts[0]
    return None


class _CustomPage(QWebEnginePage):
    """
    Googleなどのリダイレクト型リンクを正しく処理するカスタムPage。

    デフォルトのQWebEnginePageは NavigationTypeLink を外部URLへ
    遷移しようとするとブロックすることがある。
    acceptNavigationRequest を常時Trueにして全ナビゲーションを許可する。

    新規ウィンドウ要求（target="_blank"、window.open()等）は、以前は
    「同じページ内で開く」実装だったが、これだとGoogle OAuthの
    ポップアップ認証フローが壊れることが実機で判明した:
    実際に別ウィンドウ（別WebContents）が作られないため
    window.opener関係がChromiumレベルで確立されず、認証完了後に
    ポップアップ側が window.close() で自分を閉じようとしても
    「Scripts may close only the windows that were opened by them」
    エラーで拒否され、親ページへの通知も行われず、ユーザーは
    本来表示されるはずのない認証中継ページに取り残されて白画面に
    なる（Cookie自体は正常に保存されるため、認証自体は成立している）。
    そのため popup_owner（ViewBridge）経由で実際に子ウィンドウを
    作成し、QWebEngineNewWindowRequest.openIn() で正式に紐付ける。
    """
    def __init__(self, profile, parent=None, popup_owner=None):
        super().__init__(profile, parent)
        self._popup_owner = popup_owner
        self.newWindowRequested.connect(self._on_new_window)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        # すべてのナビゲーションを許可
        return True

    def _on_new_window(self, request: QWebEngineNewWindowRequest):
        if self._popup_owner is not None:
            self._popup_owner.open_popup_window(self, request)
        else:
            # popup_owner未設定時のフォールバック（従来挙動）
            self.setUrl(request.requestedUrl())


class _CustomView(QWebEngineView):
    """ページ内右クリックメニューに「Ink Bossに追加」を追加するための
    QWebEngineViewサブクラス。標準のブラウザメニュー（戻る/進む/
    再読み込み等）は page().createStandardContextMenu() でそのまま
    維持しつつ、末尾に独自項目を追加する。既存の『サイドバーの+
    ボタンから追加』と同じダイアログ（show_add_service_dialog）を、
    現在表示中ページのURLを初期値にして開く。"""
    def __init__(self, bridge_ref, parent=None):
        super().__init__(parent)
        self._bridge_ref = bridge_ref

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        add_action = menu.addAction("Ink Bossに追加")
        current_url = self.url().toString()
        add_action.triggered.connect(
            lambda checked=False, u=current_url: self._bridge_ref.open_add_service_with_url(u)
        )
        menu.popup(event.globalPos())


class ViewBridge(QObject):
    # ─── シグナル定義 ───
    create_view_signal      = Signal(str, str)
    show_view_signal        = Signal(str, int, int, int, int)
    hide_all_signal         = Signal()
    remove_view_signal      = Signal(str)
    reload_view_signal      = Signal(str)
    hibernate_view_signal   = Signal(str)
    wake_view_signal        = Signal(str, str)
    wake_and_show_signal    = Signal(str, str, int, int, int, int)
    context_menu_signal     = Signal(str, str, int, int, bool, str)
    add_dialog_signal       = Signal(str)
    settings_signal         = Signal()
    add_group_dialog_signal = Signal()
    group_menu_signal       = Signal(str, str, int, int)
    add_group_signal        = Signal(str)
    del_group_signal        = Signal(str)
    init_views_signal       = Signal()   # サービス初期化用（on_shownから呼ぶ）
    # アプリ終了（JS スレッドからでも QueuedConnection で Qt メインスレッドへ）
    app_shutdown_signal     = Signal()
    # Electron側ページ内右クリック「Ink Bossに追加」用。electron_bridgeの
    # バックグラウンドスレッド（stdout読み取り）から呼ばれるため、
    # ダイアログ表示をQtメインスレッドへ安全に渡すのに使う。
    electron_add_service_signal = Signal(str)

    def __init__(self, qt_app, config: dict):
        super().__init__()
        self.qt_app          = qt_app
        self.config          = config
        self.views:           dict = {}
        self.profiles:        dict = {}
        self.urls:            dict = {}
        self.hibernated:      set  = set()
        # 現在音声を出力中のQtサービス（自動休止の除外判定用。recentlyAudibleChangedで更新）
        self.audible:         set  = set()
        self.active_id:       str | None = None
        self.container               = None
        self._active_menu            = None
        self._pending_js             = None
        self.page_text_cache: dict   = {}
        self._active_menu_holder     = [None]
        self._shutdown_handler       = None  # callable set by main/api
        self._popups:         list  = []  # OAuthポップアップ等の子ウィンドウ（GC防止のため参照を保持）

        # シグナル接続
        self.create_view_signal.connect(self._create_view, Q)
        self.show_view_signal.connect(self._show_view, Q)
        self.hide_all_signal.connect(self._hide_all, Q)
        self.remove_view_signal.connect(self._remove_view, Q)
        self.reload_view_signal.connect(self._reload_view, Q)
        self.hibernate_view_signal.connect(self._hibernate_view, Q)
        self.wake_view_signal.connect(self._wake_view, Q)
        self.wake_and_show_signal.connect(self._wake_and_show, Q)
        self.context_menu_signal.connect(self._show_context_menu, Q)
        self.add_dialog_signal.connect(self._show_add_dialog, Q)
        self.settings_signal.connect(self._show_settings, Q)
        self.add_group_dialog_signal.connect(self._show_add_group_dialog, Q)
        self.group_menu_signal.connect(self._show_group_menu, Q)
        self.add_group_signal.connect(self._add_group, Q)
        self.del_group_signal.connect(self._del_group, Q)
        self.init_views_signal.connect(self._init_views, Q)
        self.app_shutdown_signal.connect(self._on_app_shutdown, Q)
        self.electron_add_service_signal.connect(self.open_add_service_with_url, Q)

    def set_shutdown_handler(self, fn) -> None:
        """終了処理コールバック（Qt メインスレッドで実行される）。"""
        self._shutdown_handler = fn

    @Slot()
    def _on_app_shutdown(self):
        print("[Close] app_shutdown_signal on Qt main thread", flush=True)
        fn = self._shutdown_handler
        if fn is None:
            print("[Close] no shutdown handler registered", flush=True)
            return
        try:
            fn()
        except Exception as e:
            print(f"[Close] shutdown handler error: {e}", flush=True)
            import os
            os._exit(1)

    # ────────────────────────────────────
    # 初期化
    # ────────────────────────────────────
    @Slot()
    def _init_views(self):
        """Qt エンジンのサービスのみ起動時作成。electron は helper 側 lazy。"""
        services = self.config.get("services", [])
        print(f"[_init_views] services={len(services)}", flush=True)
        for svc in services:
            eng = (svc.get("engine") or "qt").lower()
            if eng in ("electron", "e"):
                print(f"[_init_views] skip qt (electron): {svc['id']}", flush=True)
                continue
            print(f"[_init_views] emit create_view: {svc['id']}", flush=True)
            self.create_view_signal.emit(svc["id"], svc["url"])

    def set_container(self, widget):
        self.container = widget

    # ────────────────────────────────────
    # WebView 操作
    # ────────────────────────────────────
    @Slot(str, str)
    def _create_view(self, sid: str, url: str):
        if sid in self.views:
            return
        self.urls[sid] = url
        profile = QWebEngineProfile(sid, self.qt_app)
        profile.setPersistentStoragePath(str(SESSIONS_DIR / sid))
        profile.setHttpUserAgent(_build_spoofed_user_agent())
        profile.setUrlRequestInterceptor(_get_stealth_interceptor(self.qt_app))
        stealth_script = QWebEngineScript()
        stealth_script.setName(f"inkboss-stealth-{sid}")
        stealth_script.setSourceCode(_build_stealth_script(_spoofed_major_version()))
        stealth_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        stealth_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        stealth_script.setRunsOnSubFrames(True)
        profile.scripts().insert(stealth_script)
        page = _CustomPage(profile, self.qt_app, popup_owner=self)
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        page.recentlyAudibleChanged.connect(
            lambda audible, s=sid: self.audible.add(s) if audible else self.audible.discard(s)
        )
        view = _CustomView(self, self.container)
        view.setPage(page)
        view.setZoomFactor(_get_zoom_factor(self.config, sid))
        view.setUrl(QUrl("about:blank"))
        self.hibernated.add(sid)
        view.hide()
        self.profiles[sid] = profile
        self.views[sid] = view

        def _push_text(text, s=sid):
            if text and len(text.strip()) > 10:
                self.page_text_cache[s] = text
                payload = json.dumps({"sid": s, "text": text[:4000]})
                js_eval(
                    f"window.dispatchEvent(new CustomEvent('page-text-ready',{{detail:{payload}}}))"
                )

        def on_load_finished(ok, s=sid):
            if not ok:
                return
            v = self.views.get(s)
            if v is None:
                return
            if v.url().toString() in ("about:blank", "", "about:blank#blocked"):
                return
            print(f"[cache:load] {s}", flush=True)
            v.page().runJavaScript("document.body.innerText", _push_text)

        view.loadFinished.connect(on_load_finished)

        def on_url_changed(url_obj, s=sid):
            url_str = url_obj.toString()
            if url_str in ("about:blank", "", "about:blank#blocked"):
                return
            # 休止復帰（wake）時、self.urls[sid] を使って再ナビゲートするため
            # ここで常に最新のURLへ更新しておく。更新しないと、登録時の
            # URL（例: ログイン前のURL）に休止復帰のたびに戻されてしまい、
            # ページ内遷移・ログイン後の遷移先が失われる不具合があった
            # （実機で確認済み）。
            self.urls[s] = url_str

            def delayed():
                v = self.views.get(s)
                if v:
                    v.page().runJavaScript("document.body.innerText", _push_text)
            QTimer.singleShot(1500, delayed)

        view.urlChanged.connect(on_url_changed)

    def open_popup_window(self, opener_page, request) -> None:
        """window.open()/target="_blank"等の新規ウィンドウ要求を、実際に
        別ウィンドウとして開く（Google OAuthポップアップ認証を正しく
        動かすために必要 — 詳細は _CustomPage のdocstring参照）。
        親と同じQWebEngineProfileを使うことでCookieを共有し、
        request.openIn() でChromiumレベルのwindow.opener関係を
        正式に確立する。同じプロファイルを使うため、stealthスクリプト
        （プロファイル単位で登録済み）もこのポップアップに自動的に
        適用される。"""
        print(f"[popup] new window requested: url={request.requestedUrl().toString()} "
              f"dest={request.destination()}", flush=True)
        profile = opener_page.profile()
        popup_page = _CustomPage(profile, self.qt_app, popup_owner=self)
        popup_view = QWebEngineView()
        popup_view.setPage(popup_page)
        popup_view.setWindowTitle("Sign in")
        popup_page.titleChanged.connect(popup_view.setWindowTitle)

        geo = request.requestedGeometry()
        if geo.width() > 0 and geo.height() > 0:
            popup_view.resize(geo.width(), geo.height())
        else:
            popup_view.resize(500, 650)

        self._popups.append(popup_view)
        # OSの閉じるボタン・JSのwindow.close()どちらで閉じられても
        # destroyedで一元的に後始末する（WA_DeleteOnCloseでclose()が
        # 実際の破棄につながるようにする）。
        popup_view.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        def _on_close_requested():
            print("[popup] windowCloseRequested (window.close() from JS)", flush=True)
            popup_view.close()

        def _on_destroyed():
            print("[popup] destroyed, cleaning up", flush=True)
            if popup_view in self._popups:
                self._popups.remove(popup_view)

        popup_page.windowCloseRequested.connect(_on_close_requested)
        popup_view.destroyed.connect(_on_destroyed)

        request.openIn(popup_page)
        popup_view.show()
        popup_view.raise_()
        popup_view.activateWindow()
        print(f"[popup] opened as separate window ({popup_view.width()}x{popup_view.height()})", flush=True)

    @Slot(str, str)
    def _wake_view(self, sid: str, url: str):
        if sid in self.views:
            self.views[sid].setUrl(QUrl(url))
            self.hibernated.discard(sid)
            js_eval(f"window.dispatchEvent(new CustomEvent('service-woke',{{detail:'{sid}'}}))")

    @Slot(str, str, int, int, int, int)
    def _wake_and_show(self, sid: str, url: str, x: int, y: int, w: int, h: int):
        """休止復帰＋表示。300msの表示ディレイはここ（Qtメインスレッド上で
        QueuedConnection経由で実行される）でスケジュールする。
        api.py側（pywebviewのjs_api呼び出しスレッド＝Qtイベントループを
        持たないスレッド）でQTimer.singleShotを直接使うと、タイマーが
        実質的に発火しないままになる不具合があったため、ここに移した。"""
        print(f"[TIMING2] {time.time():.3f} _wake_and_show({sid}) start", flush=True)
        self._wake_view(sid, url)
        QTimer.singleShot(300, lambda: self.show_view_signal.emit(sid, x, y, w, h))
        print(f"[TIMING2] {time.time():.3f} _wake_and_show({sid}) scheduled show_view_signal in 300ms", flush=True)

    @Slot(str, int, int, int, int)
    def _show_view(self, sid: str, x: int, y: int, w: int, h: int):
        print(f"[TIMING2] {time.time():.3f} _show_view({sid}) SLOT ENTER x={x} y={y} w={w} h={h}", flush=True)
        for s, v in self.views.items():
            if s != sid:
                if v.isVisible():
                    print(f"[TIMING2] {time.time():.3f} _show_view({sid}): hiding OTHER visible view {s}", flush=True)
                v.hide()
        if sid not in self.views:
            print(f"[TIMING2] {time.time():.3f} _show_view({sid}): sid not in self.views — return", flush=True)
            return
        view = self.views[sid]
        print(f"_show_view: x={x} y={y} w={w} h={h}", flush=True)
        view.setGeometry(QRect(x, y, w, h))
        view.show()
        view.raise_()
        print(f"[TIMING2] {time.time():.3f} _show_view({sid}): view.show()+raise_() done, isVisible={view.isVisible()}", flush=True)
        view.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        for child in view.findChildren(type(view)):
            child.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        # IME有効化：X11フォーカスをメインウィンドウに移す
        wid = get_win_id()
        if wid:
            import subprocess
            def _force_focus(wid_hex):
                import time as _t
                clean_env = get_clean_subprocess_env()
                _t.sleep(0.2)
                subprocess.run(["wmctrl", "-ia", wid_hex], check=False, capture_output=True, env=clean_env)
                _t.sleep(0.1)
                subprocess.run(["fcitx5-remote", "-o"], check=False, capture_output=True, env=clean_env)
                print(f"[TIMING2] {time.time():.3f} _show_view({sid}): _force_focus thread done (wmctrl+fcitx5-remote)", flush=True)
            threading.Thread(target=_force_focus, args=(wid,), daemon=True).start()
        self.active_id = sid
        print(f"[TIMING2] {time.time():.3f} _show_view({sid}) SLOT EXIT, active_id={self.active_id}", flush=True)

    @Slot()
    def _hide_all(self):
        print(f"[TIMING2] {time.time():.3f} _hide_all() CALLED — stack:", flush=True)
        traceback.print_stack()
        for v in self.views.values():
            v.hide()
        self.active_id = None

    @Slot(str)
    def _remove_view(self, sid: str):
        """安全に破棄。二重呼び出し・deleteLater 後アクセスを許容。"""
        try:
            view = self.views.pop(sid, None)
            if view is not None:
                try:
                    view.hide()
                except Exception:
                    pass
                try:
                    view.setParent(None)
                except Exception:
                    pass
                try:
                    view.deleteLater()
                except Exception:
                    pass
            prof = self.profiles.pop(sid, None)
            if prof is not None:
                try:
                    # 明示破棄はしない（Qt 所有）。参照だけ外す
                    pass
                except Exception:
                    pass
            self.urls.pop(sid, None)
            self.hibernated.discard(sid)
            self.page_text_cache.pop(sid, None)
            if self.active_id == sid:
                self.active_id = None
        except Exception as e:
            print(f"[bridge] _remove_view({sid}) error: {e}", flush=True)

    @Slot(str)
    def _reload_view(self, sid: str):
        if sid in self.views and sid not in self.hibernated:
            self.views[sid].reload()

    @Slot(str)
    def _hibernate_view(self, sid: str):
        print(f"[TIMING2] {time.time():.3f} _hibernate_view({sid}) CALLED — stack:", flush=True)
        traceback.print_stack()
        from PySide6.QtCore import QUrl
        if sid in self.views and sid not in self.hibernated:
            self.views[sid].setUrl(QUrl("about:blank"))
            self.hibernated.add(sid)
            if self.active_id == sid:
                self.views[sid].hide()
                self.active_id = None

    def update_geometry(self, sid: str, x: int, y: int, w: int, h: int):
        if sid in self.views and sid == self.active_id:
            self.show_view_signal.emit(sid, x, y, w, h)

    # ────────────────────────────────────
    # ダイアログ・メニュー
    # ────────────────────────────────────
    @Slot(str, str, int, int, bool, str)
    def _show_context_menu(self, sid, name, x, y, is_hib, groups_json):
        def _destroy_any(s: str) -> None:
            # Qt / Electron どちらでも安全に破棄（存在しない側は no-op）
            try:
                self._remove_view(s)
            except Exception as e:
                print(f"[bridge] qt remove {s}: {e}", flush=True)
            el = getattr(self, "electron", None)
            if el is not None and el.is_available():
                try:
                    el.remove(s)
                except Exception as e:
                    print(f"[bridge] electron remove {s}: {e}", flush=True)

        def _hibernate_any(s: str) -> None:
            svc = next((x for x in self.config.get("services", []) if x["id"] == s), None)
            eng = ((svc or {}).get("engine") or "qt").lower()
            if eng in ("electron", "e"):
                el = getattr(self, "electron", None)
                if el is not None and el.is_available():
                    el.hibernate(s)
                if self.active_id == s:
                    self.active_id = None
            else:
                self._hibernate_view(s)

        def _wake_any(s: str) -> None:
            svc = next((x for x in self.config.get("services", []) if x["id"] == s), None)
            # self.urls[s] はページ内遷移のたびに on_url_changed で更新される
            # 「最後にいたURL」。show_service（通常のサイドバー切替）と同じ
            # 優先順位にし、休止復帰のたびに登録時URLへ戻ってしまう不具合を
            # ここでも防ぐ（Electronエンジンではself.urlsに該当エントリが
            # ないため、その場合は従来通りconfig登録URLにフォールバックする）。
            url = self.urls.get(s) or (svc or {}).get("url") or "about:blank"
            eng = ((svc or {}).get("engine") or "qt").lower()
            if eng in ("electron", "e"):
                el = getattr(self, "electron", None)
                if el is not None and el.is_available():
                    el.wake(s, url)
                js_eval(
                    f"window.dispatchEvent(new CustomEvent('service-woke',{{detail:'{s}'}}))"
                )
            else:
                self._wake_view(s, url)

        def _navigate_any(s: str, new_url: str) -> None:
            # URL変更。プロファイル/partitionはsid単位のままなので、
            # 遷移するだけでCookie/LocalStorageは維持される
            # （view/BrowserWindowの再作成は行わない）。
            svc = next((x for x in self.config.get("services", []) if x["id"] == s), None)
            eng = ((svc or {}).get("engine") or "qt").lower()
            if eng in ("electron", "e"):
                el = getattr(self, "electron", None)
                if el is not None and el.is_available():
                    el.wake(s, new_url)
            else:
                self._wake_view(s, new_url)

        def _reload_any(s: str) -> None:
            # Qt / Electron どちらでも、現在のページをそのままリロードする
            # （休止中は_reload_view/el.reloadとも何もしない設計のため、
            # 呼び出し前にcontext_menu.py側でメニュー項目自体を非活性にしている）
            svc = next((x for x in self.config.get("services", []) if x["id"] == s), None)
            eng = ((svc or {}).get("engine") or "qt").lower()
            if eng in ("electron", "e"):
                el = getattr(self, "electron", None)
                if el is not None and el.is_available():
                    try:
                        el.reload(s)
                    except Exception as e:
                        print(f"[bridge] electron reload {s}: {e}", flush=True)
            else:
                self._reload_view(s)

        show_service_context_menu(
            sid=sid, name=name, x=x, y=y,
            is_hib=is_hib, groups_json=groups_json,
            config=self.config, js_eval_fn=js_eval,
            wake_view_fn=_wake_any,
            hibernate_view_fn=_hibernate_any,
            create_view_fn=self._create_view,
            remove_view_fn=_destroy_any,
            navigate_view_fn=_navigate_any,
            reload_view_fn=_reload_any,
            active_menu_holder=self._active_menu_holder,
            dialog_wrapper=self._show_dialog_with_electron_hidden,
        )

    def _hide_electron_for_dialog(self):
        """ダイアログ表示中、ElectronウィンドウがalwaysOnTopのせいで
        ネイティブダイアログの上に被って操作不能になる問題への対策。
        Electronが現在表示中なら一旦hide_all()し、「元のサービスを再表示
        する関数」を返す（表示中でなければ何もしない関数を返す）。
        再表示はダミー座標（main.pyのapplicationStateChanged復帰時と同じ
        パターン）で行うため、位置は維持され再ナビゲートも発生しない。
        ダイアログ中に削除/エンジン切替/別サービスへの切替があった場合は、
        /show が未存在sidを新規作成したり別サービスに重なったりするため
        復元しない。"""
        electron = getattr(self, "electron", None)
        was_shown = bool(electron and electron.is_shown)
        prev_sid = electron.active_sid if was_shown else None
        if was_shown:
            electron.hide_all()

        def restore() -> None:
            if not (was_shown and prev_sid):
                return
            svc = next((s for s in self.config.get("services", []) if s["id"] == prev_sid), None)
            still_electron = svc is not None and (svc.get("engine") or "qt").lower() in ("electron", "e")
            still_current = self.active_id in (prev_sid, None)
            if still_electron and still_current and not electron.is_shown:
                electron.show(prev_sid, "", 0, 0, 0, 0)

        return restore

    def _show_dialog_with_electron_hidden(self, dialog_fn) -> None:
        """モーダル（exec()でブロックする）ダイアログ用。閉じたら復元する。"""
        restore = self._hide_electron_for_dialog()
        try:
            dialog_fn()
        finally:
            restore()

    @Slot(str)
    def _show_add_dialog(self, group_id_str: str):
        self._show_dialog_with_electron_hidden(lambda: show_add_service_dialog(
            config=self.config,
            js_eval_fn=js_eval,
            create_view_fn=self._create_view,
            group_id=group_id_str,
        ))

    def open_add_service_with_url(self, url: str) -> None:
        """ページ内右クリック「Ink Bossに追加」から呼ばれる。既存の
        『サイドバーの+ボタンから追加』と同じダイアログを、URLだけ
        現在のページのもので初期値にして開く（名前は未入力のまま）。
        Qt側は _CustomView.contextMenuEvent からQtメインスレッド上で
        直接呼ばれる。Electron側は electron_add_service_signal 経由
        （バックグラウンドスレッド→QueuedConnectionでこのメソッドへ）。"""
        self._show_dialog_with_electron_hidden(lambda: show_add_service_dialog(
            config=self.config,
            js_eval_fn=js_eval,
            create_view_fn=self._create_view,
            initial_url=url,
        ))

    @Slot()
    def _show_settings(self):
        # 設定ダイアログは非モーダル（.show()で即return）なので、
        # ブロッキング用ヘルパーではなくfinishedシグナルで復元する
        restore = self._hide_electron_for_dialog()
        dialog = show_settings_dialog(config=self.config, js_eval_fn=js_eval)
        if dialog is None:
            restore()
        else:
            dialog.finished.connect(lambda _=None: restore())

    @Slot()
    def _show_add_group_dialog(self):
        self._show_dialog_with_electron_hidden(
            lambda: show_add_group_dialog(config=self.config, js_eval_fn=js_eval))

    @Slot(str, str, int, int)
    def _show_group_menu(self, gid, name, x, y):
        show_group_context_menu(
            gid=gid, name=name, x=x, y=y,
            config=self.config, js_eval_fn=js_eval,
            active_menu_holder=self._active_menu_holder,
            dialog_wrapper=self._show_dialog_with_electron_hidden,
        )

    @Slot(str)
    def _add_group(self, name: str):
        import uuid
        g = {"id": f"group_{uuid.uuid4().hex[:8]}", "name": name, "collapsed": False}
        self.config["groups"].append(g)
        save_config(self.config)
        threading.Thread(
            target=lambda: js_eval(
                f"window.dispatchEvent(new CustomEvent('group-added',{{detail:{json.dumps(g)}}}));"
            ),
            daemon=True,
        ).start()

    @Slot(str)
    def _del_group(self, gid: str):
        self.config["groups"] = [x for x in self.config["groups"] if x["id"] != gid]
        for s in self.config["services"]:
            if s.get("groupId") == gid:
                s["groupId"] = None
        save_config(self.config)
        threading.Thread(
            target=lambda: js_eval(
                f"window.dispatchEvent(new CustomEvent('group-removed',{{detail:'{gid}'}}));"
            ),
            daemon=True,
        ).start()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# JS評価ユーティリティ（モジュールレベル）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def js_eval(js: str) -> None:
    """pywebviewウィンドウにJSを非同期評価させる。"""
    import webview
    def _eval():
        try:
            if webview.windows:
                webview.windows[0].evaluate_js(js)
        except Exception:
            pass
    threading.Thread(target=_eval, daemon=True).start()
