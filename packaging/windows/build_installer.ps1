# Ink Boss Windows インストーラーのビルド
# 使い方: powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_installer.ps1
# 前提: build_windows.ps1 で dist\ink-boss が作成済みであること / Inno Setup 6 がインストール済みであること

$ErrorActionPreference = "Stop"
# このスクリプトは packaging\windows\ にあるので、2つ上がリポジトリのルート
$Src = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location $Src

Write-Host "========================================"
Write-Host "  Ink Boss インストーラー作成"
Write-Host "========================================"

if (-not (Test-Path (Join-Path $Src "dist\ink-boss\ink-boss.exe"))) {
    Write-Host "dist\ink-boss\ink-boss.exe がありません。先に packaging\windows\build_windows.ps1 を実行してください"
    exit 1
}

$Candidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$Iscc = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) {
    Write-Host "Inno Setup 6 (ISCC.exe) が見つかりません。インストールしてください: https://jrsoftware.org/isdl.php"
    exit 1
}

$Version = (Get-Content (Join-Path $Src "VERSION") -Raw).Trim()
Write-Host "バージョン: $Version"
Write-Host "コンパイラ: $Iscc"
Write-Host ""
Write-Host "> コンパイル中（約860MBを圧縮するため数分かかります）..."

& $Iscc "/DAppVersion=$Version" (Join-Path $Src "packaging\windows\ink-boss.iss")
if ($LASTEXITCODE -ne 0) {
    Write-Host "インストーラーのコンパイルに失敗しました"
    exit 1
}

$Setup = Join-Path $Src "dist\installer\Ink-Boss-Setup-$Version.exe"
$SizeMB = [math]::Round((Get-Item $Setup).Length / 1MB)
Write-Host ""
Write-Host "========================================"
Write-Host "  完了: $Setup  (約 ${SizeMB} MB)"
Write-Host "========================================"
