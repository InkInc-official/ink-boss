; Ink Boss Windows インストーラー (Inno Setup 6)
; ビルド: powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_installer.ps1
; 先に packaging\windows\build_windows.ps1 で dist\ink-boss を作っておくこと。
; 相対パスは、このファイル（packaging\windows\）を基準に解決される。

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif

[Setup]
; AppId は更新・アンインストールの同一性判定に使うので、絶対に変更しないこと
AppId={{6E1B7C54-3A9D-4F6B-9C2E-1D4A8B0F5E73}
AppName=Ink Boss
AppVersion={#AppVersion}
AppPublisher=Ink Inc.
AppPublisherURL=https://github.com/InkInc-official/ink-boss
DefaultDirName={autopf}\Ink Boss
DefaultGroupName=Ink Boss
DisableProgramGroupPage=yes
; ユーザー単位インストール（管理者権限不要）。自動更新を無人・UACなしで行うため。
PrivilegesRequired=lowest
OutputDir=..\..\dist\installer
OutputBaseFilename=Ink-Boss-Setup-{#AppVersion}
SetupIconFile=..\..\public\icon.ico
UninstallDisplayIcon={app}\ink-boss.exe
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにアイコンを作成する"; GroupDescription: "追加のアイコン:"; Flags: unchecked

[Files]
Source: "..\..\dist\ink-boss\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Ink Boss"; Filename: "{app}\ink-boss.exe"
Name: "{group}\Ink Boss のアンインストール"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Ink Boss"; Filename: "{app}\ink-boss.exe"; Tasks: desktopicon

[Run]
; 通常インストール: 完了画面のチェックで起動
Filename: "{app}\ink-boss.exe"; Description: "Ink Boss を起動する"; Flags: nowait postinstall skipifsilent
; 自動更新（サイレント）: 更新後に自動で再起動
Filename: "{app}\ink-boss.exe"; Flags: nowait; Check: WizardSilent

[Code]
// インストール/アンインストール前に、動作中の Ink Boss を終了する。
// /T で子プロセス（同梱 electron.exe など）もまとめて終了する。
procedure KillRunningApp();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM ink-boss.exe', '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(800);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  KillRunningApp();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  KillRunningApp();
  Result := True;
end;
