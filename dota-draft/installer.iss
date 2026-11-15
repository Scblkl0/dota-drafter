#define AppName "Dota Draft Helper"
#define AppVersion "1.1.0"
#define AppExe "DotaDraftHelper.exe"

[Setup]
AppId={{5BDED5DD-01C9-4993-836D-F916382696FF}
AppName={#AppName}
AppVersion={#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={autopf}\DotaDraftHelper
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=DotaDraftHelper-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\DotaDraftHelper\*"; DestDir: "{app}"; Excludes: "debug\*"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\debug"
