# packaging/windows/build_windows.ps1 - Ink Boss Windows版ビルドスクリプト
# 実行場所: 仮想環境(.venv)を有効にした PowerShell（どのフォルダからでも可。リポジトリのルートを自動で見つける）
# 実行方法: powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_windows.ps1
#
# やること:
#   1. 前提の確認（frontend\dist、electron-engine\node_modules、VERSION）
#   2. PyInstaller で dist\ink-boss\ を生成（ink-boss.spec、--onedir）
#   3. electron-engine を dist\ink-boss\electron-engine へコピー
#      （PyInstallerを通さない。electron_bridge.py が実行ファイルと同じ階層を見る）
#
# 出力: dist\ink-boss\ink-boss.exe（続けて build_installer.ps1 がこのフォルダをインストーラーにまとめる）

$ErrorActionPreference = "Stop"
# このスクリプトは packaging\windows\ にあるので、2つ上がリポジトリのルート
$Src = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location $Src

$Version = (Get-Content (Join-Path $Src "VERSION") -Raw).Trim()
Write-Host "========================================"
Write-Host "  Ink Boss Windows版ビルド v$Version"
Write-Host "========================================"

# ── 1. 前提の確認 ──
Write-Host ""
Write-Host "> 前提を確認中..."

if (-not (Test-Path (Join-Path $Src "frontend\dist"))) {
    Write-Host "  frontend\dist が見つかりません。先に次を実行してください:"
    Write-Host "    cd frontend; npm run build; cd .."
    exit 1
}
if (-not (Test-Path (Join-Path $Src "electron-engine\node_modules"))) {
    Write-Host "  electron-engine\node_modules が見つかりません。先に次を実行してください:"
    Write-Host "    cd electron-engine; npm install; cd .."
    exit 1
}
if (-not (Test-Path (Join-Path $Src "public\icon.ico"))) {
    Write-Host "  public\icon.ico が見つかりません"
    exit 1
}

python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  PyInstaller が見つかりません。先に次を実行してください:"
    Write-Host "    pip install pyinstaller"
    exit 1
}
Write-Host "  OK"

# ── 2. PyInstaller（--onedir、spec経由）──
Write-Host ""
Write-Host "> バイナリをビルド中（数分かかります）..."

python -m PyInstaller --noconfirm --clean ink-boss.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host "  PyInstaller が失敗しました"
    exit 1
}

$Out = Join-Path $Src "dist\ink-boss"
if (-not (Test-Path (Join-Path $Out "ink-boss.exe"))) {
    Write-Host "  dist\ink-boss\ink-boss.exe が見つかりません。ビルドに失敗した可能性があります"
    exit 1
}
Write-Host "  dist\ink-boss\ 生成完了"

# ── 3. electron-engine を同梱 ──
Write-Host ""
Write-Host "> electron-engine を同梱中..."

$Dest = Join-Path $Out "electron-engine"
if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }

# robocopy: 終了コード 0-7 は成功、8以上が失敗
robocopy (Join-Path $Src "electron-engine") $Dest /E /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Host "  electron-engine のコピーに失敗しました (robocopy=$LASTEXITCODE)"
    exit 1
}

if (-not (Test-Path (Join-Path $Dest "node_modules\electron\dist\electron.exe"))) {
    Write-Host "  electron.exe が同梱先に見つかりません"
    exit 1
}
Write-Host "  electron-engine を同梱"

$SizeMB = [math]::Round(((Get-ChildItem $Out -Recurse -File | Measure-Object Length -Sum).Sum) / 1MB)
Write-Host ""
Write-Host "========================================"
Write-Host "  完了  出力先: $Out  (約 ${SizeMB} MB)"
Write-Host "========================================"
Write-Host ""
Write-Host "動作確認: $Out\ink-boss.exe を起動してください"
