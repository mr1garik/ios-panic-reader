; Установщик iOS Panic Reader для Windows (Inno Setup 6).
; Сборка: ISCC /DAppVersion=0.4.2 installer\iOSPanicReader.iss  (exe должен лежать в dist\)
; Ставится для текущего пользователя без прав администратора — так автообновление
; может само заменять программу. Данные пользователя (Документы\iOSPanicReader) не трогаются.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F0B5D3E-2A4C-4F8B-9C1D-7E3A5B2C9D41}
AppName=iOS Panic Reader
AppVersion={#AppVersion}
AppVerName=iOS Panic Reader {#AppVersion}
AppPublisher=mr1garik
AppPublisherURL=https://github.com/mr1garik/ios-panic-reader
AppSupportURL=https://github.com/mr1garik/ios-panic-reader/issues
AppUpdatesURL=https://github.com/mr1garik/ios-panic-reader/releases
DefaultDirName={localappdata}\Programs\iOS Panic Reader
DefaultGroupName=iOS Panic Reader
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=iOSPanicReader-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\iOSPanicReader.exe
UninstallDisplayName=iOS Panic Reader
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "uk"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\iOSPanicReader.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\iOS Panic Reader"; Filename: "{app}\iOSPanicReader.exe"
Name: "{autodesktop}\iOS Panic Reader"; Filename: "{app}\iOSPanicReader.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\iOSPanicReader.exe"; Description: "{cm:LaunchProgram,iOS Panic Reader}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; только то, что лежит рядом с программой; данные в Документах остаются
Type: files; Name: "{app}\*.new.exe"
