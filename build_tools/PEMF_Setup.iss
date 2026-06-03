; ============================================================================
; PEMF Medical System — Inno Setup Kurulum Scripti
; ============================================================================
;
; KULLANIM:
;   1. Inno Setup'ı indir: https://jrsoftware.org/isinfo.php
;   2. PyInstaller ile önce onedir build yap:
;      cd build_tools && .\build_onedir_exe.ps1
;   3. Bu scripti Inno Setup IDE'de aç ve "Build > Compile" yap.
;      VEYA komut satırından: iscc.exe PEMF_Setup.iss
;
; ÇIKTI: build_tools\Output\PEMFSetup_v1.0.exe
; ============================================================================

#define MyAppName      "PEMF Medical System"
#define MyAppVersion   "1.1"
#define MyAppPublisher "PEMF Medical Technologies"
#define MyAppURL       "https://pemf-medical.com"
#define MyAppExeName   "PEMF_GUI.exe"
; OneDir build çıktısı - PyInstaller'ın dist/PEMF_GUI/ klasörü
; Bu script build_tools/ içinden çalıştırıldığı için bir üst dizin proje köküdür.
#define ProjectRoot    ".."
#define BuildOutput    "..\dist\PEMF_GUI"

[Setup]
; Uygulama kimliği — ASLA DEĞİŞTİRMEYİN (kaldırma için kullanılır)
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Kurulum dizini — Program Files altında
DefaultDirName={autopf}\PEMF Medical
DefaultGroupName={#MyAppName}

; Denetim Masası'nda görünmesi için
UninstallDisplayName={#MyAppName} v{#MyAppVersion}
UninstallDisplayIcon={app}\PEMF_GUI.exe

; Kurulum dosyası adı
OutputDir=Output
OutputBaseFilename=PEMFSetup_v{#MyAppVersion}

; Sıkıştırma (LZMA en iyi sıkıştırma oranı)
Compression=lzma2/ultra64
SolidCompression=yes

; Admin yetkisi iste (sürücü kurulumu için şart)
PrivilegesRequired=admin

; Windows 7 SP1 ve üzeri (6.1sp1 önerilen minimum)
MinVersion=6.1sp1

; 64-bit uygulama
ArchitecturesInstallIn64BitMode=x64compatible

; Kurulum sihirbazı görsel ayarları
WizardStyle=modern
WizardSizePercent=110

; İkon
SetupIconFile={#ProjectRoot}\pemf_gui\resources\icons\pemf_heart_emf_icon.ico

; Kurulumdan önce çalışan kopyayı kapat
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no

; Dil
ShowLanguageDialog=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[CustomMessages]
turkish.InstallingVC=Microsoft Visual C++ Redistributable kuruluyor...
turkish.InstallingSTM32=STM32 VCP Sürücüsü kuruluyor...
turkish.ConfiguringFirewall=Windows Güvenlik Duvarı ayarlanıyor...
turkish.SetupComplete=Kurulum Tamamlandı
turkish.SetupCompleteDesc=PEMF Medical System başarıyla kuruldu.%n%nMasaüstündeki kısayolu kullanarak uygulamayı başlatabilirsiniz.

[Tasks]
Name: "desktopicon"; Description: "Masaüstüne kısayol oluştur"; GroupDescription: "Ek Kısayollar:"
Name: "startmenuicon"; Description: "Başlat Menüsüne ekle"; GroupDescription: "Ek Kısayollar:"

[Components]
Name: "main"; Description: "Ana Uygulama"; Types: full compact custom; Flags: fixed
Name: "ai"; Description: "AI Paketlerini Kur (Çevrimdışı Kullanım İçin)"; Types: full custom

[Files]
; ── Ana Uygulama (PyInstaller OnDir çıktısı) ──────────────────────────────
; Tüm PEMF_GUI/ klasörünü kopyala (EXE + _internal/ + tüm dosyalar)
Source: "{#BuildOutput}\*"; DestDir: "{app}"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs

; ── AI Paketleri (Opsiyonel Kurulum) ──────────────────────────────────────
Source: "{#ProjectRoot}\release_assets\ai_models\*"; DestDir: "{commonappdata}\PEMF_GUI\ai_models"; Components: ai; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist

; ── Sürücü Kurulum Dosyaları (geçici, kurulumda çalıştırılacak) ───────────
Source: "{#ProjectRoot}\lattekurulum\VC_redist.x64.exe"; DestDir: "{tmp}"; Components: main; Flags: deleteafterinstall
[Icons]
; Masaüstü kısayolu
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\PEMF_GUI.exe"
; Başlat Menüsü
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\PEMF_GUI.exe"
Name: "{group}\{#MyAppName} Kaldır"; Filename: "{uninstallexe}"

[Run]
; ── 1. Microsoft Visual C++ Redistributable (sessiz kurulum) ──────────────
Filename: "{tmp}\VC_redist.x64.exe"; \
  Parameters: "/install /quiet /norestart"; \
  StatusMsg: "{cm:InstallingVC}"; \
  Flags: waituntilterminated runhidden; \
  Check: VCRedistNeedsInstall

; ── 2. Uygulamayı başlat (kurulumdan sonra, opsiyonel) ────────────────────
Filename: "{app}\{#MyAppExeName}"; \
  Description: "PEMF Medical System'i Şimdi Başlat"; \
  WorkingDir: "{app}"; \
  Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
; Kaldırma sırasında önce açık olan programları kapat
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM {#MyAppExeName} /T"; Flags: runhidden; RunOnceId: "KillPEMFProcess"
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM mosquitto.exe /T"; Flags: runhidden; RunOnceId: "KillMosquittoProcess"

; Güvenlik Duvarı kurallarını sil
Filename: "netsh"; \
  Parameters: "advfirewall firewall delete rule name=""Mosquitto Broker"""; \
  Flags: runhidden waituntilterminated; \
  RunOnceId: "RemoveFirewallRuleMosquitto"

[UninstallDelete]
; Uygulamanın kurulu olduğu dizindeki çalışırken üretilen dosyaları zorla sil
Type: filesandordirs; Name: "{app}"
; AI modelleri klasörünü (varsa) tamamen sil
Type: filesandordirs; Name: "{commonappdata}\PEMF_GUI"
; NOT: userappdata ve localappdata temizliği (per-user alanlar)
; PrivilegesRequired=admin ile çakışmamak için Pascal Script'te yapılır (CurUninstallStepChanged).


[Registry]
; Windows Güvenlik Duvarı kuralı kurulum sırasında eklenir
; (Pascal kodu aracılığıyla, aşağıda)

; Uygulama bilgileri Denetim Masası için
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"

[Code]
// ─────────────────────────────────────────────────────────────────────────
// Pascal Script — Özel Kurulum Mantığı
// ─────────────────────────────────────────────────────────────────────────

// VC++ Redistributable kurulu mu diye kontrol et
function VCRedistNeedsInstall: Boolean;
var
  Installed: Cardinal;
begin
  // Visual C++ 2015-2022 x64 Redistributable için registry kontrolü
  Result := not RegQueryDWordValue(
    HKLM,
    'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
    'Installed',
    Installed
  ) or (Installed = 0);
end;

// Kurulum tamamlandıktan sonra Güvenlik Duvarı kuralını ekle
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  MosquittoPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Mosquitto güvenlik duvarı kuralı:
    // PyInstaller onedir build'de datas dosyalari {app}\_internal altında yer alır.
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
    
    // PEMF_GUI.exe için de kural ekle (serial port ve MQTT erişimi için)
    Exec('netsh',
      'advfirewall firewall add rule name="PEMF Medical System" dir=in action=allow program="' + ExpandConstant('{app}') + '\PEMF_GUI.exe" enable=yes profile=any',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      
    Exec('netsh',
      'advfirewall firewall add rule name="PEMF Medical System" dir=out action=allow program="' + ExpandConstant('{app}') + '\PEMF_GUI.exe" enable=yes profile=any',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

// Kaldırma sırasında ek temizlik
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  AppDataPath: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    // PEMF_GUI.exe güvenlik duvarı kurallarını sil
    Exec('netsh',
      'advfirewall firewall delete rule name="PEMF Medical System"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
  
  if CurUninstallStep = usPostUninstall then
  begin
    // AppData klasörünü ve logları otomatik olarak sil
    AppDataPath := ExpandConstant('{userappdata}') + '\PEMF_GUI';
    if DirExists(AppDataPath) then
      DelTree(AppDataPath, True, True, True);

    // Ultralytics YOLO cache
    AppDataPath := ExpandConstant('{userappdata}') + '\Ultralytics';
    if DirExists(AppDataPath) then
      DelTree(AppDataPath, True, True, True);

    // Digital Twin kurulum dizini
    AppDataPath := ExpandConstant('{localappdata}') + '\PEMF_DigitalTwin_Installation';
    if DirExists(AppDataPath) then
      DelTree(AppDataPath, True, True, True);

    // Gizli .pemf_gui klasörü
    AppDataPath := ExpandConstant('{%USERPROFILE}') + '\.pemf_gui';
    if DirExists(AppDataPath) then
      DelTree(AppDataPath, True, True, True);
  end;
end;
