#define MyAppName "SecOne"
#define MyAppVersion "1.0.0-rc1"
#define MyAppPublisher "SecOne Contributors"
#define MyAppExeName "SecOne.exe"

[Setup]
AppId={{8E2B7E1C-5C4A-4B1E-9F61-2D3A4C5B6D70}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\SecOne
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=SecOne-{#MyAppVersion}-setup
SetupIconFile=..\assets\secone.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
AllowNoIcons=yes

[Languages]
#if FileExists(AddBackslash(CompilerPath) + "Languages\ChineseSimplified.isl")
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\SecOne\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\models"; Flags: uninsneveruninstall
Name: "{app}\runtime"; Flags: uninsneveruninstall
Name: "{app}\data"; Flags: uninsneveruninstall
Name: "{app}\workspace"; Flags: uninsneveruninstall
Name: "{app}\output"; Flags: uninsneveruninstall
Name: "{app}\logs"; Flags: uninsneveruninstall

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not WizardSilent then
    begin
      if not FileExists(ExpandConstant('{app}\models\XuanmuSec-v2-Q6_K.gguf')) and
         not FileExists(ExpandConstant('{app}\runtime\llama-server.exe')) then
        MsgBox('SecOne 已安装。本地 AI 引擎需要单独下载的模型包（GGUF 与 llama.cpp 运行时）。' + #13#10 +
               '请把模型包解压到安装目录，或在“设置”页指定现有模型与运行时路径。' + #13#10 +
               '未配置模型时，文件处理、静态分析与规则扫描仍可使用。',
               mbInformation, MB_OK);
    end;
  end;
end;
