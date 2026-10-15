# Third-Party Notices / 第三者ソフトウェアについて

Ink Boss（MIT License）は、次のソフトウェアを利用・同梱しています。
各ソフトウェアのライセンス全文は、配布パッケージ内の各ライブラリのフォルダ、または下記の配布元で確認できます。

Ink Boss (MIT License) uses and bundles the software listed below.
Full license texts are included in the distributed packages and are available from each project.

## 主な同梱ソフトウェア / Main bundled software

| ソフトウェア | 用途 | ライセンス |
|---|---|---|
| [Qt for Python (PySide6)](https://doc.qt.io/qtforpython-6/) / Qt 6 / QtWebEngine | デスクトップ画面・Qtエンジン | LGPL-3.0 |
| [Electron](https://www.electronjs.org/) | Electronエンジン | MIT |
| [Chromium](https://www.chromium.org/) | Electron・QtWebEngine に含まれる | BSD-3-Clause ほか（下記参照） |
| [pywebview](https://pywebview.flowrl.com/) | ウィンドウとフロントエンドの橋渡し | BSD-3-Clause |
| [QtPy](https://github.com/spyder-ide/qtpy) | Qt バインディングの抽象化 | MIT |
| [React](https://react.dev/) ほか、`frontend/package.json` の依存 | フロントエンド | 主に MIT |
| [Pillow](https://python-pillow.org/) | 画像処理 | HPND |
| [PyInstaller](https://pyinstaller.org/)（Windows版のビルド） | 実行ファイルの作成 | GPL-2.0 + bootloader exception |
| [Inno Setup](https://jrsoftware.org/isinfo.php)（Windows版のビルド） | インストーラーの作成 | Inno Setup License |

実際に同梱される Python パッケージの一覧とライセンスは、`requirements.txt` と、各パッケージのメタデータを参照してください。

## Qt（LGPL-3.0）について / About Qt (LGPL-3.0)

- Ink Boss は Qt を**動的リンク**で利用しています。Windows版・Linux版のどちらも、Qt のライブラリ（DLL / 共有ライブラリ）は、配布物の中に独立したファイルとして含まれています（Windows版: インストール先の `_internal` フォルダ内）。
- 利用者は、LGPL-3.0 に従い、これらの Qt ライブラリを、互換性のある別のビルドに差し替えられます。
- Qt のソースコードは <https://download.qt.io/> から、PySide6 は <https://pypi.org/project/PySide6/> から入手できます。
- LGPL-3.0 の全文: <https://www.gnu.org/licenses/lgpl-3.0.html>

## Electron と Chromium

- Electron は MIT License です。
- Electron と Chromium が利用する各種ライブラリのライセンス一覧は、Electron に同梱されている `LICENSE` と `LICENSES.chromium.html`（Windows版: インストール先の `electron-engine\node_modules\electron\dist\`）に含まれています。

## PyInstaller（Windows版）

PyInstaller は GPL-2.0 ですが、生成される実行ファイルについては、bootloader exception により、Ink Boss 自体のライセンスは影響を受けません。
<https://pyinstaller.org/en/stable/license.html>

---

このファイルに誤りや不足があれば、Issue でお知らせください。
If you find any error or omission in this file, please open an issue.
