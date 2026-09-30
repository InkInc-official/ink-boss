# -*- mode: python ; coding: utf-8 -*-
#
# --onedir 方式（--onefile は使わない）。
# 理由: --onefile は起動のたびに全データを一時ディレクトリへ展開する
# ため、electron-engine（node_modules込みで270MB超）のような巨大な
# データを持つこのアプリでは起動が大幅に遅くなる。--onedir はその
# 展開オーバーヘッドが無く、将来Windows版をPyInstallerでビルドする
# 際にも同じ考え方をそのまま使える。
#
# electron-engine/ はここ（datas）には含めない。PyInstallerの一時
# 展開・アーカイブ機構に270MB超のバイナリ一式（Electron本体・
# node_modules）を通すと余計なコピー/圧縮コストがかかる上、
# node_modules/.bin 内のシンボリックリンクの扱いも煩雑になるため、
# build_deb.sh 側で dist/ink-boss/（このspecの出力先）に対して
# 直接 cp -a するほうがシンプルで確実。electron_bridge.py の
# ENGINE_DIR は、frozen時は実行ファイル自身のディレクトリを基準に
# 解決するため、electron-engine/ を実行ファイルと同じ階層に
# 置きさえすれば dev/frozen どちらでも同じ相対構造で見つかる。

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # VERSION: updater.pyのCURRENT_VERSIONがbuild_deb.shのVERSIONと
    # 単一の情報源を共有するために同梱する（updater.pyのdocstring参照）。
    datas=[('frontend/dist', 'frontend/dist'), ('frontend/public', 'frontend/public'), ('VERSION', '.')],
    # platformdirs: 直接は使っていないが、PyInstallerのpkg_resources
    # 用ランタイムフック(pyi_rth_pkgres)がsetuptools同梱のpkg_resources
    # を初期化する際に必要とする。hiddenimportsに無いとバンドルされず、
    # 実機では「ImportError: The 'platformdirs' package is required」
    # で起動直後にクラッシュする（実機で再現・確認済み）。
    hiddenimports=['PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore', 'PySide6.QtWebChannel', 'webview', 'platformdirs'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ink-boss',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ink-boss',
)
