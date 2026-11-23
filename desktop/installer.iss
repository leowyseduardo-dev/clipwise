#ifndef AppVersion
  #define AppVersion "1.3.0"
#endif

[Setup]
AppId={{8C1F6F6E-4B9A-4A3E-9A54-7D3A0D8A6C21}
AppName=Clipwise
AppVersion={#AppVersion}
AppVerName=Clipwise {#AppVersion}
AppPublisher=Clipwise
DefaultDirName={localappdata}\Programs\Clipwise
DefaultGroupName=Clipwise
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist\installer
OutputBaseFilename=Clipwise-Setup-{#AppVersion}
SetupIconFile=assets\Clipwise.ico
UninstallDisplayIcon={app}\Clipwise.exe
UninstallDisplayName=Clipwise
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
AppMutex=Local\Clipwise.Desktop.SingleInstance
VersionInfoCompany=Clipwise
VersionInfoDescription=Clipwise - editor automatico de clips verticales
VersionInfoProductName=Clipwise
VersionInfoProductVersion={#AppVersion}
VersionInfoVersion={#AppVersion}.0
SetupLogging=yes
AllowNoIcons=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: checkedonce

#ifndef BundleDir
  #define BundleDir "dist\Clipwise"
#endif

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#if FileExists(AddBackslash(SourcePath) + "vendor\MicrosoftEdgeWebView2Setup.exe")
Source: "vendor\MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
#endif

[Icons]
Name: "{autoprograms}\Clipwise"; Filename: "{app}\Clipwise.exe"
Name: "{autodesktop}\Clipwise"; Filename: "{app}\Clipwise.exe"; Tasks: desktopicon

[Run]
#if FileExists(AddBackslash(SourcePath) + "vendor\MicrosoftEdgeWebView2Setup.exe")
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Instalando Microsoft Edge WebView2..."; Flags: waituntilterminated; Check: not WebView2RuntimeInstalled
#endif
Filename: "{app}\Clipwise.exe"; Description: "Iniciar Clipwise"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function WebView2RuntimeInstalled: Boolean;
begin
  Result :=
    RegValueExists(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv') or
    RegValueExists(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv') or
    RegValueExists(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv');
end;
