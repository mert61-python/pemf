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
#define MyAppVersion   "1.8.0"
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
; UX: 3.5GB tek imzasiz exe'yi Windows Defender, exe calismadan ONCE tam tarar -> ~20sn siyah ekran
; ("acilmiyor mu?" suphesi). DiskSpanning = kucuk launcher exe (~birkac MB) + ayri .bin veri dosyalari ->
; kucuk exe aninda taranir, Inno sihirbazi 1-2sn'de acilir. exe + .bin AYNI klasorde birlikte dagitilir.
DiskSpanning=yes
DiskSliceSize=2100000000
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
; Hotspot baslatici (PEMF-Gateway WiFi â€” ESP bobinleri icin; logon-task + kurulumda bir kez calisir)
Source: "{#ProjectRoot}\scripts\start_hotspot.ps1"; DestDir: "{app}"; Flags: ignoreversion
; BIRLESIK TEARDOWN (Faz 2): setup_services.ps1 -Uninstall bunlara delege eder; pemf_uninstall_all.ps1
; standalone tam-kaldirici (destek/sifirlama + KVKK "tum veriyi sildim" raporu). UCU ayni {app}'te.
Source: "{#ProjectRoot}\scripts\pemf_footprint.ps1";     DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\scripts\pemf_teardown.ps1";      DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\scripts\pemf_uninstall_all.ps1"; DestDir: "{app}"; Flags: ignoreversion
; AI MODELLERI (OFFLINE, ~640MB): YOLO/XGBoost/segmentation/thermal vb. -> ProgramData. Servis (LocalSystem)
; bunlari find_installed_model ile candidate-root #1'de (C:\ProgramData\PEMF_GUI\ai_models) bulur -> HF token
; ve internet GEREKMEZ. (Eskiden model HF'den indiriliyordu; LocalSystem kullanici-env token'ini goremedigi
; icin indirme 401 -> TUM AI endpoint'leri 500 veriyordu. Bundle bunu kokten cozer; offline klinik calisir.)
Source: "{#ProjectRoot}\release_assets\ai_models\*"; DestDir: "{commonappdata}\PEMF_GUI\ai_models"; Flags: ignoreversion recursesubdirs createallsubdirs
; VC++ Redistributable (gecici; torch/onnx/opencv MSVC runtime gerektirir)
; skipifsourcedoesntexist KALDIRILDI â€” redist yoksa ISCC compile FAIL etsin (sessiz-eksik installer Ã¼retilmesin;
; aksi halde taze klinikte VCRUNTIME140.dll eksik â†’ torch/onnx/cv2 yÃ¼klÃ¼ EXE aÃ§Ä±lmaz, sessiz baÅŸarÄ±sÄ±zlÄ±k).
Source: "{#ProjectRoot}\lattekurulum\VC_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[INI]
; Web arayuzu icin gercek internet kisayolu (.url) olustur
Filename: "{app}\PEMF Web UI.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:8000"
; MASAUSTU kisayolu: React web arayuzunu (localhost:8000) tarayicida acar; ikon = backend EXE (kalp ikonu)
Filename: "{commondesktop}\PEMF Web Arayuzu.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:8000"
Filename: "{commondesktop}\PEMF Web Arayuzu.url"; Section: "InternetShortcut"; Key: "IconFile"; String: "{app}\PEMF_Backend.exe"
Filename: "{commondesktop}\PEMF Web Arayuzu.url"; Section: "InternetShortcut"; Key: "IconIndex"; String: "0"

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

; NOT: Servis/hotspot/firewall kaldirma [UninstallRun]'dan [Code]'a (CurUninstallStepChanged)
; tasindi -> operatore "hasta verilerini de sil?" ONAYI sorulup yanita gore
; setup_services.ps1'e kosullu -PurgeData gecilebilsin ([UninstallRun] parametreleri
; statiktir; kosullu bayrak orada mumkun degil). KVKK: varsayilan KORU.

[UninstallDelete]
Type: files; Name: "{commondesktop}\PEMF Web Arayuzu.url"
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{commonappdata}\PEMF_System"
Type: filesandordirs; Name: "{commonappdata}\PEMF_GUI\ai_models"

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

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    // [Files] kopyalamadan ONCE calisan backend'i durdur/kill -> kilitli-EXE kopyalama hatasini onler (re-install).
    Exec('taskkill.exe', '/F /IM PEMF_Backend.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('sc.exe', 'stop PemfBackend', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end
  else if CurStep = ssPostInstall then
  begin
    // setup_services.ps1 YALNIZ gercek dogrulamada (/api/health 200) ".install_verified" yazar.
    // Yoksa: servis kurulumu/baslatma BASARISIZ -> teknik-olmayan kurulumcuya GORUNUR hata (sessiz-basariyi kapat).
    if not FileExists(ExpandConstant('{app}\.install_verified')) then
      MsgBox('KURULUM TAMAMLANAMADI: PEMF backend baslatilamadi veya /api/health dogrulanamadi.' + #13#10 +
             'Cihaz su an CALISMIYOR.' + #13#10#13#10 +
             'Log: C:\ProgramData\PEMF_System\logs\backend_service_stderr.log' + #13#10 +
             'Olasi neden: VC++ runtime eksik, port 8000 dolu, veya bozuk kurulum. Logu kontrol edin / destek ile gorusun.',
             mbError, MB_OK);
  end;
end;

// Kaldirmada servisleri/hotspot/firewall/env/registry'yi kaldir. ONCE operatore sor:
// hasta verisi + sifreleme anahtarlari da silinsin mi? KVKK geregi VARSAYILAN = KORU
// (yalnizca ACIK onayla sil). usUninstall, {app} silinMEDEN once calisir -> setup_services.ps1 hazir.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  Params: String;
  Purge: Boolean;
begin
  if CurUninstallStep = usUninstall then
  begin
    Purge := False;
    // Sessiz kaldirmada SORMA -> veri KORUNUR (sessiz akis hasta verisini onaysiz silmesin).
    if not UninstallSilent then
      Purge := MsgBox(
        'Hasta verilerini ve sifreleme anahtarlarini da KALICI olarak silmek istiyor musunuz?' + #13#10#13#10 +
        'HAYIR (onerilen): Servisler/hotspot/firewall kaldirilir, HASTA VERISI KORUNUR' + #13#10 +
        '(yeniden kurulumda erisilebilir kalir).' + #13#10#13#10 +
        'EVET: Tum hasta veritabani + sifreleme anahtarlari GERI DONULEMEZ sekilde silinir (KVKK tam temizlik).',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;

    Params := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\setup_services.ps1') +
              '" -AppDir "' + ExpandConstant('{app}') + '" -Uninstall';
    if Purge then
      Params := Params + ' -PurgeData';

    // Best-effort: teardown hatasi kaldirmayi bloklamasin (script kendisi de ErrorAction=Continue).
    Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;























