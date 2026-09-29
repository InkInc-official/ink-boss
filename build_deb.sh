#!/bin/bash
# build_deb.sh - Ink Boss DEBパッケージビルドスクリプト
# 実行場所: ~/InkTools/ink-boss/
# 実行方法: bash build_deb.sh
#
# 構成（デュアルエンジン版）:
#   /usr/lib/ink-boss/          PyInstaller --onedir 出力一式 + electron-engine/
#   /usr/bin/ink-boss           上記への symlink
#   /usr/share/applications/    .desktop
#   /usr/share/icons/...        アイコン
#
# 旧版との違い:
#   - PyInstaller --onefile ではなく --onedir（ink-boss.spec参照。
#     起動毎の展開オーバーヘッドを避けるため）
#   - electron-engine（node_modules込み）はPyInstallerに通さず、
#     ビルド後の出力ディレクトリへ直接コピーする
#   - 配置先を /usr/share（本来arch非依存データ用）ではなく
#     /usr/lib（arch依存バイナリ・プライベートライブラリ用、FHS準拠）
#     にし、dpkgが管理してはいけない /usr/local ではなく /usr/bin に
#     symlinkを置く

set -e

APP_NAME="ink-boss"
VERSION="1.0.1"
ARCH="amd64"
BUILD_DIR="$HOME/build-deb"
PKG_DIR="$BUILD_DIR/${APP_NAME}_${VERSION}_${ARCH}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Ink Boss DEBパッケージビルド v${VERSION}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── ① 依存ツールの確認 ──────────────────────
echo ""
echo "▶ 依存ツールを確認中..."

if ! command -v pyinstaller &>/dev/null; then
    echo "  PyInstallerをインストール中..."
    pip install pyinstaller --break-system-packages
fi

if ! command -v dpkg-deb &>/dev/null; then
    echo "  dpkg-devをインストール中..."
    sudo apt install -y dpkg-dev
fi

if [ ! -d "$SRC_DIR/frontend/dist" ]; then
    echo "  ⚠️ frontend/dist が見つかりません。先に (cd frontend && npm run build) を実行してください"
    exit 1
fi

if [ ! -d "$SRC_DIR/electron-engine/node_modules" ]; then
    echo "  ⚠️ electron-engine/node_modules が見つかりません。先に (cd electron-engine && npm install) を実行してください"
    exit 1
fi

echo "  ✓ OK"

# ── ② PyInstallerでバイナリ生成（--onedir、spec経由） ──
echo ""
echo "▶ バイナリをビルド中（数分かかります）..."

cd "$SRC_DIR"
pyinstaller --noconfirm ink-boss.spec

if [ ! -d "dist/ink-boss" ]; then
    echo "  ⚠️ PyInstallerの出力（dist/ink-boss/）が見つかりません。ビルドに失敗した可能性があります"
    exit 1
fi

echo "  ✓ dist/ink-boss/ 生成完了"

# ── ③ DEBディレクトリ構造を作成 ─────────────
echo ""
echo "▶ DEBパッケージ構造を作成中..."

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$PKG_DIR/usr/lib/ink-boss"

# PyInstaller --onedir 出力一式（実行ファイル + _internal/、
# frontend/dist・frontend/public は ink-boss.spec の datas 経由で
# 既にこの中に含まれている）
cp -a "$SRC_DIR/dist/ink-boss/." "$PKG_DIR/usr/lib/ink-boss/"
echo "  ✓ PyInstaller onedir 出力を同梱"

# electron-engine 一式（node_modules込み）を実行ファイルと同じ階層へ
# 直接コピー（PyInstallerのdatasは経由しない。cp -a でシンボリック
# リンク・実行権限を保持する）。electron_bridge.py の ENGINE_DIR が
# frozen時に「実行ファイル自身のディレクトリ」を基準に解決するため、
# ここに置く必要がある。
cp -a "$SRC_DIR/electron-engine" "$PKG_DIR/usr/lib/ink-boss/electron-engine"
echo "  ✓ electron-engine を同梱"

# /usr/bin へのsymlink（dpkgが管理してはいけない /usr/local は使わない）
ln -sf /usr/lib/ink-boss/ink-boss "$PKG_DIR/usr/bin/ink-boss"

# アイコン
if [ -f "$SRC_DIR/frontend/public/icon.png" ]; then
    cp "$SRC_DIR/frontend/public/icon.png" \
       "$PKG_DIR/usr/share/icons/hicolor/256x256/apps/ink-boss.png"
fi

# ── ④ controlファイル作成 ───────────────────
# wmctrl・xdotool・x11-utils(xprop) は main.py/bridge.py/api.py/
# window.py が実行時に直接呼び出しており、無いとウィンドウ制御が
# 機能しない（Depends）。fcitx5-remote(bridge.py) はfcitx5未導入
# 環境ではibusにフォールバックする設計のためRecommendsに留める。
# fcitx5-frontend-gtk3 は Electron エンジンのサービスで fcitx5 の日本語入力を
# 使うためのGTKモジュール（無いとElectron側でIMEが接続されない）。
# ollamaはアプリ内の「インストール」ボタンで案内する完全な任意
# 機能のため、ここには含めない。
cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: ink-boss
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: libnss3, libatk-bridge2.0-0, libgtk-3-0, libxss1, libgbm1, wmctrl, xdotool, x11-utils
Recommends: fcitx5, fcitx5-frontend-gtk3
Maintainer: 黒井葉跡 <inkinc.official@gmail.com>
Description: Ink Boss - レシピレスのマルチサービス一元化デスクトップアプリ
 Ink Inc.が開発する、複数のWebサービスを1つのウィンドウにまとめる
 デスクトップアプリ。OSSとして公開。
 AI Creation, Human Care. The Future Drawn Together.
EOF

# ── ⑤ .desktopファイル作成 ──────────────────
cat > "$PKG_DIR/usr/share/applications/ink-boss.desktop" << EOF
[Desktop Entry]
Name=Ink Boss
Comment=Ink Inc. 配信特化PCワークスペース
Exec=/usr/bin/ink-boss
Icon=ink-boss
Terminal=false
Type=Application
Categories=Utility;Network;
StartupNotify=true
EOF

# ── ⑥ postinstスクリプト作成 ────────────────
cat > "$PKG_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/bash
update-desktop-database /usr/share/applications 2>/dev/null || true
gtk-update-icon-cache /usr/share/icons/hicolor 2>/dev/null || true
EOF
chmod 755 "$PKG_DIR/DEBIAN/postinst"

# ── ⑦ DEBパッケージをビルド ─────────────────
echo ""
echo "▶ DEBパッケージをビルド中..."

dpkg-deb --build "$PKG_DIR" "$BUILD_DIR/${APP_NAME}_${VERSION}_${ARCH}.deb"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ 完了！"
echo "  出力先: $BUILD_DIR/${APP_NAME}_${VERSION}_${ARCH}.deb"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "インストールするには:"
echo "  sudo dpkg -i $BUILD_DIR/${APP_NAME}_${VERSION}_${ARCH}.deb"
