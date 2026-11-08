; What's Playing - Inno Setup script (needs Inno Setup 6.3 or later).
; Wraps the PyInstaller folder build (dist\WhatsPlaying\) into one Setup.exe.
; Normally run via build-installer.bat, which passes /DMyAppVersion=x.y.z.

#ifndef MyAppVersion
  #define MyAppVersion "1.1.0"
#endif
#define MyAppName "What's Playing"
#define MyAppExe "WhatsPlaying.exe"

[Setup]
; AppId identifies this app for upgrades/uninstall. Never change it between releases.
AppId={{A0FB7890-C22B-4142-967D-D8E743EBCFE6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
; Per-user install: no admin prompt, and the folder stays writable. The app saves
; .env, recognitions.csv and logs next to the .exe, so it must NOT live in Program Files.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\WhatsPlaying
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer
OutputBaseFilename=WhatsPlaying-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=TERMS.txt
UninstallDisplayIcon={app}\{#MyAppExe}
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "dist\WhatsPlaying\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch {#MyAppName}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove disposable files only. .env (your API key), recognitions.csv and its backups
; are deliberately kept, so uninstalling or upgrading never destroys your history.
Type: files; Name: "{app}\last_clip.wav"
Type: files; Name: "{app}\retry_clip.wav"
Type: files; Name: "{app}\whatsplaying.log"

[Code]
{ The app's native window needs the Microsoft Edge WebView2 Runtime. Windows 11 and most
  up-to-date Windows 10 PCs have it. Detection follows Microsoft's documented registry check. }
function ReadPv(Root: Integer; const SubKey: String): String;
var
  Value: String;
begin
  if RegQueryStringValue(Root, SubKey, 'pv', Value) then
    Result := Value
  else
    Result := '';
end;

function WebView2Installed(): Boolean;
var
  Guid, Pv: String;
begin
  Guid := '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Pv := ReadPv(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + Guid);
  if (Pv = '') or (Pv = '0.0.0.0') then
    Pv := ReadPv(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + Guid);
  Result := (Pv <> '') and (Pv <> '0.0.0.0');
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not WebView2Installed() then
    Result := MsgBox('The Microsoft Edge WebView2 Runtime was not found on this PC. ' +
      'What''s Playing needs it to open its window.' + #13#10#13#10 +
      'You can install it free from:' + #13#10 +
      'https://developer.microsoft.com/microsoft-edge/webview2' + #13#10#13#10 +
      'Continue installing What''s Playing anyway?',
      mbConfirmation, MB_YESNO) = IDYES;
end;
