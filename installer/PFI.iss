; Inno Setup script for Personal Finance Intelligence.
; Built by scripts\build.ps1:  ISCC /DAppVersion=x /DSourceDir=dist\PFI /DOutputDir=dist PFI.iss

#ifndef AppVersion
  #define AppVersion "0.3.1"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\PFI"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
AppId={{3AD51315-839A-4B92-A567-7DCF6605A5C1}
AppName=Personal Finance Intelligence
AppVersion={#AppVersion}
AppVerName=Personal Finance Intelligence {#AppVersion}
AppPublisher=Ibrahim
DefaultDirName={autopf}\Personal Finance Intelligence
DefaultGroupName=Personal Finance Intelligence
DisableProgramGroupPage=yes
; Per-user install by default (no administrator prompt); user may choose all users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir={#OutputDir}
OutputBaseFilename=PFI-Setup-{#AppVersion}
SetupIconFile={#SourceDir}\pfi.ico
UninstallDisplayIcon={app}\PFI.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Personal Finance Intelligence"; Filename: "{app}\PFI.exe"
Name: "{autodesktop}\Personal Finance Intelligence"; Filename: "{app}\PFI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PFI.exe"; Description: "{cm:LaunchProgram,Personal Finance Intelligence}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Your financial data in %LOCALAPPDATA%\PersonalFinanceIntelligence is kept.
Type: filesandordirs; Name: "{app}\backend\__pycache__"

[Messages]
FinishedLabel=Setup has finished installing [name]. Your data is stored in %LOCALAPPDATA%\PersonalFinanceIntelligence and is kept if you uninstall.
