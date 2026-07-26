#define MyAppName "Voice AI Studio Arabic"
#define MyAppVersion "2.2.0"
#define MyAppPublisher "Agfsgsy"
#define MyAppExeName "VoiceAIStudio.exe"

[Setup]
AppId={{74A2FE78-3A6E-4B8A-A79D-4AE17D6EA2C9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Voice AI Studio Arabic
DefaultGroupName=Voice AI Studio Arabic
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist_installer
OutputBaseFilename=VoiceAIStudioArabic-Setup-2.2.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[Tasks]
Name: "desktopicon"; Description: "إنشاء اختصار على سطح المكتب"; GroupDescription: "اختصارات إضافية:"; Flags: unchecked

[Files]
Source: "..\dist\VoiceAIStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Voice AI Studio Arabic"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Voice AI Studio Arabic"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "تشغيل Voice AI Studio Arabic"; Flags: nowait postinstall skipifsilent
