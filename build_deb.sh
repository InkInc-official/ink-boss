#!/bin/bash
# build_deb.sh - Ink Boss DEBパッケージビルドスクリプト
# 実行場所: ~/InkTools/ink-boss/
# 実行方法: bash build_deb.sh

set -e

APP_NAME="ink-boss"
VERSION="1.0.0"
ARCH="amd64"
BUILD_DIR="$HOME/build-deb"
PKG_DIR="$BUILD_DIR/${APP_NAME}_${VERSION}_${ARCH}"

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

echo "  ✓ OK"

# ── ② PyInstallerでバイナリ生成 ─────────────
echo ""
echo "▶ バイナリをビルド中（数分かかります）..."

cd ~/InkTools/ink-boss

pyinstaller \
    --onefile \
    --noconsole \
    --name ink-boss \
    --exclude-module PyQt5 \
    --add-data "frontend/dist:frontend/dist" \
    --add-data "frontend/public:frontend/public" \
    --hidden-import "PySide6.QtWebEngineWidgets" \
    --hidden-import "PySide6.QtWebEngineCore" \
    --hidden-import "PySide6.QtWebChannel" \
    --hidden-import "webview" \
    main.py

echo "  ✓ dist/ink-boss 生成完了"

# ── ③ DEBディレクトリ構造を作成 ─────────────
echo ""
echo "▶ DEBパッケージ構造を作成中..."

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/local/bin"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$PKG_DIR/usr/share/ink-boss"
mkdir -p "$PKG_DIR/usr/share/ink-boss/frontend/dist"

# frontend/distをコピー（ビルド済みUIファイル）
if [ -d ~/InkTools/ink-boss/frontend/dist ]; then
    cp -r ~/InkTools/ink-boss/frontend/dist/. "$PKG_DIR/usr/share/ink-boss/frontend/dist/"
    echo "  ✓ frontend/dist を同梱"
else
    echo "  ⚠️ frontend/dist が見つかりません。先に npm run build を実行してください"
    exit 1
fi

# バイナリをusr/share/ink-bossに配置してlnでusr/local/binに繋ぐ
cp ~/InkTools/ink-boss/dist/ink-boss "$PKG_DIR/usr/share/ink-boss/ink-boss"
chmod +x "$PKG_DIR/usr/share/ink-boss/ink-boss"
ln -sf /usr/share/ink-boss/ink-boss "$PKG_DIR/usr/local/bin/ink-boss"

# アイコンをコピー（あれば）
if [ -f ~/InkTools/ink-boss/frontend/public/icon.png ]; then
    cp ~/InkTools/ink-boss/frontend/public/icon.png \
       "$PKG_DIR/usr/share/icons/hicolor/256x256/apps/ink-boss.png"
fi

# ── ④ controlファイル作成 ───────────────────
cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: ink-boss
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: libnss3, libatk-bridge2.0-0, libgtk-3-0, libxss1, libgbm1
Maintainer: 黒井葉跡 <inkinc.official@gmail.com>
Description: Ink Boss - Ink Inc. 配信特化PCワークスペース
 Ink Inc.所属ライバー向けの配信特化PCワークスペースツール。
 AI Creation, Human Care. The Future Drawn Together.
EOF

# ── ⑤ .desktopファイル作成 ──────────────────
cat > "$PKG_DIR/usr/share/applications/ink-boss.desktop" << EOF
[Desktop Entry]
Name=Ink Boss
Comment=Ink Inc. 配信特化PCワークスペース
Exec=ink-boss
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
