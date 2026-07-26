﻿; ============================================================================
; PEMF Medical System â€” Inno Setup Kurulum Scripti
; ============================================================================
;
; KULLANIM:
;   1. Inno Setup'Ä± indir: https://jrsoftware.org/isinfo.php
;   2. PyInstaller ile Ã¶nce onedir build yap:
;      cd build_tools && .\build_onedir_exe.ps1
;   3. Bu scripti Inno Setup IDE'de aÃ§ ve "Build > Compile" yap.
;      VEYA komut satÄ±rÄ±ndan: iscc.exe PEMF_Setup.iss
;
; Ã‡IKTI: build_tools\Output\PEMFSetup_v{VERSION}.exe
; ============================================================================

#define MyAppName      "PEMF Medical System"
#define MyAppVersion   "1.4.0"
#define MyAppPublisher "PEMF Medical Technologies"
#define MyAppURL       "https://pemf-medical.com"
#define MyAppExeName   "PEMF_GUI.exe"
; OneDir build Ã§Ä±ktÄ±sÄ± - PyInstaller'Ä±n dist/PEMF_GUI/ klasÃ¶rÃ¼
; Bu script build_tools/ iÃ§inden Ã§alÄ±ÅŸtÄ±rÄ±ldÄ±ÄŸÄ± iÃ§in bir Ã¼st dizin proje kÃ¶kÃ¼dÃ¼r.
#define ProjectRoot    ".."
#define BuildOutput    "..\dist\PEMF_GUI"

[Setup]
; Uygulama kimliÄŸi â€” ASLA DEÄÄ°ÅTÄ°RMEYÄ°N (kaldÄ±rma iÃ§in kullanÄ±lÄ±r)
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Kurulum dizini â€” Program Files altÄ±nda
DefaultDirName={autopf}\PEMF Medical
DefaultGroupName={#MyAppName}

; Denetim MasasÄ±'nda gÃ¶rÃ¼nmesi iÃ§in
UninstallDisplayName={#MyAppName} v{#MyAppVersion}
UninstallDisplayIcon={app}\PEMF_GUI.exe

; Kurulum dosyasÄ± adÄ±
OutputDir=Output
OutputBaseFilename=PEMFSetup_v{#MyAppVersion}

; SÄ±kÄ±ÅŸtÄ±rma (LZMA en iyi sÄ±kÄ±ÅŸtÄ±rma oranÄ±)
Compression=lzma2/ultra64
SolidCompression=yes

; Admin yetkisi iste (sÃ¼rÃ¼cÃ¼ kurulumu iÃ§in ÅŸart)
PrivilegesRequired=admin

; Windows 7 SP1 ve Ã¼zeri (6.1sp1 Ã¶nerilen minimum)
MinVersion=6.1sp1

; 64-bit uygulama
ArchitecturesInstallIn64BitMode=x64compatible

; Kurulum sihirbazÄ± gÃ¶rsel ayarlarÄ±
WizardStyle=modern
WizardSizePercent=110

; Ä°kon
SetupIconFile={#ProjectRoot}\pemf_gui\resources\icons\pemf_heart_emf_icon.ico

; Kurulumdan Ã¶nce Ã§alÄ±ÅŸan kopyayÄ± kapat
CloseApplications=yes
CloseApplicationsFilter=PEMF_GUI.exe
RestartApplications=no

; Dil
ShowLanguageDialog=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[CustomMessages]
turkish.InstallingVC=Microsoft Visual C++ Redistributable kuruluyor...
turkish.InstallingSTM32=STM32 VCP SÃ¼rÃ¼cÃ¼sÃ¼ kuruluyor...
turkish.ConfiguringFirewall=Windows GÃ¼venlik DuvarÄ± ayarlanÄ±yor...
turkish.SetupComplete=Kurulum TamamlandÄ±
turkish.SetupCompleteDesc=PEMF Medical System baÅŸarÄ±yla kuruldu.%n%nMasaÃ¼stÃ¼ndeki kÄ±sayolu kullanarak uygulamayÄ± baÅŸlatabilirsiniz.

[Tasks]
Name: "desktopicon"; Description: "MasaÃ¼stÃ¼ne kÄ±sayol oluÅŸtur"; GroupDescription: "Ek KÄ±sayollar:"
Name: "startmenuicon"; Description: "BaÅŸlat MenÃ¼sÃ¼ne ekle"; GroupDescription: "Ek KÄ±sayollar:"

[Components]
Name: "main"; Description: "Ana Uygulama"; Types: full compact custom; Flags: fixed
Name: "ai"; Description: "AI Paketlerini Kur (Ã‡evrimdÄ±ÅŸÄ± KullanÄ±m Ä°Ã§in)"; Types: full custom

[Files]
; â”€â”€ Ana Uygulama (PyInstaller OnDir Ã§Ä±ktÄ±sÄ±) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
; TÃ¼m PEMF_GUI/ klasÃ¶rÃ¼nÃ¼ kopyala (EXE + _internal/ + tÃ¼m dosyalar)
Source: "{#BuildOutput}\*"; DestDir: "{app}"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs

; â”€â”€ Runtime config ve credential dosyalarÄ± (plug-and-play kurulum) â”€â”€â”€â”€â”€â”€â”€â”€â”€
; PyInstaller bundle iÃ§inde _internal/config olarak zaten bulunur; burada ayrÄ±ca
; {app}\config altÄ±nda gÃ¶rÃ¼nÃ¼r kopya bÄ±rakÄ±lÄ±r.
Source: "{#ProjectRoot}\config\*"; DestDir: "{app}\config"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ProjectRoot}\data\config.json"; DestDir: "{app}\data"; Components: main; Flags: ignoreversion skipifsourcedoesntexist

; â”€â”€ AI Paketleri (Opsiyonel Kurulum) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Source: "{#ProjectRoot}\release_assets\ai_models\*"; DestDir: "{commonappdata}\PEMF_GUI\ai_models"; Components: ai; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist

; â”€â”€ SÃ¼rÃ¼cÃ¼ Kurulum DosyalarÄ± (geÃ§ici, kurulumda Ã§alÄ±ÅŸtÄ±rÄ±lacak) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Source: "{#ProjectRoot}\lattekurulum\VC_redist.x64.exe"; DestDir: "{tmp}"; Components: main; Flags: deleteafterinstall skipifsourcedoesntexist
[Icons]
; MasaÃ¼stÃ¼ kÄ±sayolu
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\PEMF_GUI.exe"
; BaÅŸlat MenÃ¼sÃ¼
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\PEMF_GUI.exe"
Name: "{group}\{#MyAppName} KaldÄ±r"; Filename: "{uninstallexe}"

[Run]
; â”€â”€ 1. Microsoft Visual C++ Redistributable (sessiz kurulum) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Filename: "{tmp}\VC_redist.x64.exe"; \
  Parameters: "/install /quiet /norestart"; \
  StatusMsg: "{cm:InstallingVC}"; \
  Flags: waituntilterminated runhidden; \
  Check: VCRedistNeedsInstall and FileExists(ExpandConstant('{tmp}\VC_redist.x64.exe'))

; â”€â”€ 2. UygulamayÄ± baÅŸlat (kurulumdan sonra, opsiyonel) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Filename: "{app}\{#MyAppExeName}"; \
  Description: "PEMF Medical System'i Åimdi BaÅŸlat"; \
  WorkingDir: "{app}"; \
  Flags: nowait postinstall skipifsilent shellexec runasoriginaluser

[UninstallRun]
; KaldÄ±rma sÄ±rasÄ±nda Ã¶nce aÃ§Ä±k olan programlarÄ± kapat
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM {#MyAppExeName} /T"; Flags: runhidden; RunOnceId: "KillPEMFProcess"
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Get-CimInstance Win32_Process -Filter 'name = ''mosquitto.exe''' | Where-Object {{ $_.ExecutablePath -like '*\PEMF_GUI\mosquitto\*' -or $_.ExecutablePath -like '*\PEMF Medical\_internal\bin\mosquitto\*' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"""; \
  Flags: runhidden waituntilterminated; \
  RunOnceId: "KillBundledMosquittoProcess"

; GÃ¼venlik DuvarÄ± kurallarÄ±nÄ± sil
Filename: "netsh"; \
  Parameters: "advfirewall firewall delete rule name=""Mosquitto Broker"""; \
  Flags: runhidden waituntilterminated; \
  RunOnceId: "RemoveFirewallRuleMosquitto"

[UninstallDelete]
; UygulamanÄ±n kurulu olduÄŸu dizindeki Ã§alÄ±ÅŸÄ±rken Ã¼retilen dosyalarÄ± zorla sil
Type: filesandordirs; Name: "{app}"
; AI modelleri klasÃ¶rÃ¼nÃ¼ (varsa) tamamen sil
; [KVKK] ai_models = uygulama modelleri (hasta-verisi DEGIL). Tum PEMF_GUI'yi SILME -> hasta DB'si
; korunur. Tam hasta-verisi silme icin: scripts\pemf_uninstall_all.ps1 -PurgeData (birlesik teardown).
Type: filesandordirs; Name: "{commonappdata}\PEMF_GUI\ai_models"
; Bridge/service loglarÄ± ve Ã§alÄ±ÅŸma zamanÄ± kalÄ±ntÄ±larÄ±
Type: filesandordirs; Name: "{commonappdata}\PEMF_System"
; [KVKK] "{userappdata}\PEMF_GUI" (HASTA VERISI) KOSULSUZ SILME KALDIRILDI -> operator hasta DB'sini
; kaybetmesin. Tam silme kullanicinin ACIK onayiyla: pemf_uninstall_all.ps1 -PurgeData.
; NOT: Ultralytics (ucuncu-parti ML cache, PEMF-markasi degil) da KASITEN kaldirildi.
Type: filesandordirs; Name: "{localappdata}\PEMF_DigitalTwin_Installation"
Type: filesandordirs; Name: "{localappdata}\PEMF_System"
; [KVKK] "{%USERPROFILE}\.pemf_gui" (HASTA VERISI) KOSULSUZ SILME KALDIRILDI (bkz. yukari; -PurgeData ile silinir).
Type: files; Name: "{%TEMP}\PEMF_GUI_Update_Setup.exe"
; DiÄŸer Windows kullanÄ±cÄ± profillerindeki per-user kalÄ±ntÄ±lar Pascal Script ile ayrÄ±ca temizlenir.


[Registry]
; Windows GÃ¼venlik DuvarÄ± kuralÄ± kurulum sÄ±rasÄ±nda eklenir
; (Pascal kodu aracÄ±lÄ±ÄŸÄ±yla, aÅŸaÄŸÄ±da)

; Uygulama bilgileri Denetim MasasÄ± iÃ§in
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"

[Code]
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Pascal Script â€” Ã–zel Kurulum MantÄ±ÄŸÄ±
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// VC++ Redistributable kurulu mu diye kontrol et
function VCRedistNeedsInstall: Boolean;
var
  Installed: Cardinal;
begin
  // Visual C++ 2015-2022 x64 Redistributable iÃ§in registry kontrolÃ¼
  Result := not RegQueryDWordValue(
    HKLM,
    'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
    'Installed',
    Installed
  ) or (Installed = 0);
end;

procedure DeleteDirIfExists(Path: String);
begin
  if DirExists(Path) then
    DelTree(Path, True, True, True);
end;

procedure DeleteFileIfExists(Path: String);
begin
  if FileExists(Path) then
    DeleteFile(Path);
end;

function IsRealUserProfile(ProfileName: String): Boolean;
begin
  Result :=
    (ProfileName <> '') and
    (ProfileName <> '.') and
    (ProfileName <> '..') and
    (CompareText(ProfileName, 'All Users') <> 0) and
    (CompareText(ProfileName, 'Default') <> 0) and
    (CompareText(ProfileName, 'Default User') <> 0) and
    (CompareText(ProfileName, 'Public') <> 0);
end;

procedure DeletePerUserArtifacts;
var
  FindRec: TFindRec;
  UsersRoot: String;
  ProfilePath: String;
begin
  UsersRoot := ExpandConstant('{sd}') + '\Users';
  if not DirExists(UsersRoot) then
    exit;

  if FindFirst(UsersRoot + '\*', FindRec) then
  begin
    try
      repeat
        if ((FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0) and IsRealUserProfile(FindRec.Name) then
        begin
          ProfilePath := UsersRoot + '\' + FindRec.Name;
          DeleteDirIfExists(ProfilePath + '\AppData\Roaming\PEMF_GUI');
          DeleteDirIfExists(ProfilePath + '\AppData\Roaming\Ultralytics');
          DeleteDirIfExists(ProfilePath + '\AppData\Local\PEMF_DigitalTwin_Installation');
          DeleteDirIfExists(ProfilePath + '\AppData\Local\PEMF_System');
          DeleteDirIfExists(ProfilePath + '\.pemf_gui');
          DeleteFileIfExists(ProfilePath + '\AppData\Local\Temp\PEMF_GUI_Update_Setup.exe');
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

// Kurulum tamamlandÄ±ktan sonra GÃ¼venlik DuvarÄ± kuralÄ±nÄ± ekle
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  MosquittoPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Mosquitto gÃ¼venlik duvarÄ± kuralÄ±:
    // PyInstaller onedir build'de datas dosyalari {app}\_internal altÄ±nda yer alÄ±r.
    MosquittoPath := ExpandConstant('{app}') + '\_internal\bin\mosquitto\mosquitto.exe';
    
    if FileExists(MosquittoPath) then
    begin
      // Gelen kural
      Exec('netsh',
        'advfirewall firewall add rule name="Mosquitto Broker" dir=in action=allow program="' + MosquittoPath + '" enable=yes profile=any',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      
      // Giden kural
      Exec('netsh',
        'advfirewall firewall add rule name="Mosquitto Broker" dir=out action=allow program="' + MosquittoPath + '" enable=yes profile=any',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
    
    // PEMF_GUI.exe iÃ§in de kural ekle (serial port ve MQTT eriÅŸimi iÃ§in)
    Exec('netsh',
      'advfirewall firewall add rule name="PEMF Medical System" dir=in action=allow program="' + ExpandConstant('{app}') + '\PEMF_GUI.exe" enable=yes profile=any',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      
    Exec('netsh',
      'advfirewall firewall add rule name="PEMF Medical System" dir=out action=allow program="' + ExpandConstant('{app}') + '\PEMF_GUI.exe" enable=yes profile=any',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

// KaldÄ±rma sÄ±rasÄ±nda ek temizlik
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // PEMF_GUI.exe gÃ¼venlik duvarÄ± kurallarÄ±nÄ± sil
    Exec('netsh',
      'advfirewall firewall delete rule name="PEMF Medical System"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
  
  if CurUninstallStep = usPostUninstall then
  begin
    // AppData, LocalAppData, ProgramData ve log kalÄ±ntÄ±larÄ±nÄ± temizle.
    DeleteDirIfExists(ExpandConstant('{userappdata}') + '\PEMF_GUI');
    DeleteDirIfExists(ExpandConstant('{userappdata}') + '\Ultralytics');
    DeleteDirIfExists(ExpandConstant('{localappdata}') + '\PEMF_DigitalTwin_Installation');
    DeleteDirIfExists(ExpandConstant('{localappdata}') + '\PEMF_System');
    DeleteDirIfExists(ExpandConstant('{commonappdata}') + '\PEMF_GUI');
    DeleteDirIfExists(ExpandConstant('{commonappdata}') + '\PEMF_System');
    DeleteDirIfExists(ExpandConstant('{%USERPROFILE}') + '\.pemf_gui');
    DeleteFileIfExists(ExpandConstant('{%TEMP}') + '\PEMF_GUI_Update_Setup.exe');
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Mertacor\PEMF_GUI');
    DeletePerUserArtifacts;
  end;
end;

