; ============================================================================
; PEMF Medical Backend (HEADLESS) - Inno Setup Kurulum Scripti
; ============================================================================
; GUI YOK. Backend EXE'sini kurar + Mosquitto ve Backend'i Windows SERVISI yapar.
; (PEMF_Setup.iss'in headless karsiligi; o GUI baslatir, bu servis kurar.)
;
; KULLANIM:
;   1. Headless EXE build et:  cd guii  &&  .\scripts\build_backend_exe.ps1
;      Build ciktisi C:\PEMF_BUILD\dist\PEMF_Backend olusur. Bu installer
;      "..\dist\PEMF_Backend" (yani guii\dist\PEMF_Backend) bekler:
;        -> Ya BuildOutput define'ini kendi cikti yolunuza gore degistirin,
;        -> Ya da C:\PEMF_BUILD\dist\PEMF_Backend'i guii\dist\PEMF_Backend'e kopyalayin.
;   2. iscc.exe PEMF_Backend_Setup.iss     (veya Inno Setup IDE: Build > Compile)
; CIKTI: build_tools\Output\PEMFBackendSetup_v{VERSION}.exe
; ============================================================================

#define MyAppName      "PEMF Medical Backend"
#define MyAppVersion   "1.4.0"
#define MyAppPublisher "PEMF Medical Technologies"
#define MyAppURL       "https://pemf-medical.com"
#define ProjectRoot    ".."
; BuildOutput ve ModeName komut satirindan /D ile override edilebilir:
;   ISCC "/DBuildOutput=C:\PEMF_BUILD\dist\PEMF_Backend" PEMF_Backend_Setup.iss            (device)
;   ISCC "/DBuildOutput=C:\PEMF_BUILD\dist\PEMF_Backend" "/DModeName=server" ...           (server)
#ifndef BuildOutput
  #define BuildOutput  "..\dist\PEMF_Backend"
#endif
#ifndef ModeName
  #define ModeName     "device"
#endif

[Setup]
; GUI installer'dan FARKLI AppId -> yan yana kurulabilir, cakismaz.
AppId={{B7A1C2D3-E4F5-4061-8273-A1B2C3D4E5F6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion} ({#ModeName})
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\PEMF Backend
DefaultGroupName={#MyAppName}
UninstallDisplayName={#MyAppName} v{#MyAppVersion}
OutputDir=Output
OutputBaseFilename=PEMFBackendSetup_{#ModeName}_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=admin
MinVersion=6.1sp1
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
SetupIconFile={#ProjectRoot}\pemf_gui\resources\icons\pemf_heart_emf_icon.ico
ShowLanguageDialog=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[CustomMessages]
turkish.InstallingVC=Microsoft Visual C++ Redistributable kuruluyor...
turkish.InstallingServices=PEMF arka plan servisleri (Mosquitto + Backend) kuruluyor...

[Files]
; Headless backend (PyInstaller onedir): EXE + _internal (frontend, mosquitto, ML stack, ...)
Source: "{#BuildOutput}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Servis kurulum scripti (installer bunu calistirir)
Source: "{#ProjectRoot}\scripts\setup_services.ps1"; DestDir: "{app}"; Flags: ignoreversion
; VC++ Redistributable (gecici; torch/onnx/opencv MSVC runtime gerektirir)
Source: "{#ProjectRoot}\lattekurulum\VC_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall skipifsourcedoesntexist

[INI]
; Web arayuzu icin gercek internet kisayolu (.url) olustur
Filename: "{app}\PEMF Web UI.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:8000"

[Icons]
; GUI yok; Baslat Menusu kisayolu web arayuzunu (tarayicida) acar.
Name: "{group}\PEMF Backend - Web Arayuzu"; Filename: "{app}\PEMF Web UI.url"
Name: "{group}\PEMF Backend Kaldir"; Filename: "{uninstallexe}"

[Run]
; 1. VC++ Redistributable (gerekirse, sessiz)
Filename: "{tmp}\VC_redist.x64.exe"; Parameters: "/install /quiet /norestart"; \
  StatusMsg: "{cm:InstallingVC}"; Flags: waituntilterminated runhidden; \
  Check: VCRedistNeedsInstall and FileExists(ExpandConstant('{tmp}\VC_redist.x64.exe'))
; 2. Mosquitto + Backend servislerini kur ve baslat
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup_services.ps1"" -AppDir ""{app}"" -Mode {#ModeName}"; \
  StatusMsg: "{cm:InstallingServices}"; Flags: waituntilterminated runhidden
; 3. Web arayuzunu ac (opsiyonel, sessiz kurulumda atlanir)
Filename: "http://localhost:8000"; Description: "Web arayuzunu simdi ac"; \
  Flags: postinstall shellexec skipifsilent nowait

[UninstallRun]
; Kaldirmadan ONCE servisleri durdur + sil (dosyalar silinmeden once)
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup_services.ps1"" -AppDir ""{app}"" -Uninstall"; \
  Flags: runhidden waituntilterminated; RunOnceId: "RemovePemfServices"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{commonappdata}\PEMF_System"

[Registry]
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\PEMF Backend"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\PEMF Backend"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"

[Code]
// VC++ 2015-2022 x64 Redistributable kurulu mu?
function VCRedistNeedsInstall: Boolean;
var
  Installed: Cardinal;
begin
  Result := not RegQueryDWordValue(
    HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed
  ) or (Installed = 0);
end;
