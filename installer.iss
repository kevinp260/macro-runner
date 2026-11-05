#define MyAppName     "MacroRunner"
#define MyAppVersion  "2.0.0"
#define MyAppId       "8F6B8A3D-5D6E-4E62-9C0D-0D0FBF9A8F22"  ; keep this GUID stable

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename={#MyAppName}-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=macro_runner_icon.ico

; Let Setup close locking apps via Windows Restart Manager
CloseApplications=yes
; Optional: limit/expand what files are checked (default: *.exe,*.dll,*.chm)
; CloseApplicationsFilter=*.exe,*.dll,*.chm
RestartApplications=no

; Optional: have your app create this mutex; Setup/Uninstall will detect it
AppMutex=Global\MacroRunnerMutex

UsePreviousAppDir=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\MacroRunner.exe

[Files]
Source: "dist\MacroRunner.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MacroRunner"; Filename: "{app}\MacroRunner.exe"
Name: "{commondesktop}\MacroRunner"; Filename: "{app}\MacroRunner.exe"
