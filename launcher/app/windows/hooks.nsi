; =============================================================================
; PEMF Vet Client — NSIS kaldırma kancaları (endüstri-standardı tam temizlik).
; -----------------------------------------------------------------------------
; Tauri v2 iki kanca sağlar:
;   NSIS_HOOK_PREUNINSTALL  — dosyalar/registry/kısayollar SİLİNMEDEN ÖNCE
;   NSIS_HOOK_POSTUNINSTALL — SİLİNDİKTEN SONRA
; Bu client KULLANICI-BAŞINA (currentUser) kurulum → yalnız KENDİ indirdiği payload'u
; ve client-verisini temizler. Servisler / ProgramData / hotspot / firewall, ayrı ADMIN
; kurulumu olan "PEMF Backend" (Inno) uninstaller'ının işidir. HASTA DB'si (%APPDATA%\
; PEMF_GUI) KVKK gereği client-kaldırmada KASITLI SİLİNMEZ.
; =============================================================================

!macro NSIS_HOOK_PREUNINSTALL
  ; --- HASTA GÜVENLİĞİ: backend'i ÖLDÜRMEDEN ÖNCE bobinlere E-stop gönder ---
  ; Launcher pencereyle birlikte düzgün kapandıysa bobinler zaten durduruldu. AMA launcher
  ; ÇÖKTÜ/zorla kapatıldıysa (ya da Tauri upgrade eski uninstaller'ı sessiz koşturursa)
  ; PEMF_Backend.exe orphan + bobinler HÂLÂ HASTANIN ÜZERİNDE ENERJİLİ olabilir. `taskkill /F`
  ; sinyalsizdir → backend'in graceful bobin-STOP'u ÇALIŞMAZ, bobinler firmware watchdog'una
  ; kalır. Bu yüzden önce donanım E-stop'unu POST'la. Portu launcher $INSTDIR\backend.port'a
  ; yazar (install_and_launch); uninstaller ayrı süreç olduğundan portu ANCAK bu dosyadan bilir.
  Push $0
  Push $1
  Push $2
  Push $3  ; DENETİM 2026-09-06: E-stop sonuç-günlüğü için dosya tutamacı (aşağıda)
  ClearErrors
  FileOpen $0 "$INSTDIR\backend.port" r
  IfErrors pemf_estop_fallback
  FileRead $0 $1
  FileClose $0
  Goto pemf_estop_haveport
  pemf_estop_fallback:
  ; DENETİM 2026-08-04: "$INSTDIR == veri kökü" bugün DOĞRU ama TESADÜFİDİR ve hiçbir yerde
  ; zorlanmıyor. Tauri NSIS varsayılanı installMode=currentUser → $INSTDIR = $LOCALAPPDATA\
  ; PEMF Vet Client; launcher da backend.port'u install::default_install_root() ile TAM AYNI
  ; yere yazıyor (doğrulandı: PEMFVetClient.exe ile runtime/ yan yana). Biri "kurulum Program
  ; Files'a gitsin" deyip installMode=perMachine yaparsa bu eşitlik SESSİZCE bozulur: dosya
  ; açılamaz, E-stop atlanır, hemen ardından taskkill /F koşar → bobinler HASTANIN ÜZERİNDE
  ; ENERJİLİ kalır (ESP bobinleri 6-8'in firmware watchdog'u YOK). Kaldırıcı sessizce "başarılı"
  ; görünür. Bu yüzden kanonik veri köküne AÇIK bir yedek yol: hasta güvenliği tek bir
  ; yapılandırma varsayımına bağlı kalmasın.
  ; ⚠️ DENETİM 2026-08-04 (P2 — BU YEDEK YOLUN KENDİ HATASI): Tauri'nin uninstaller'ı
  ; `un.onInit` içinde `SetShellVarContext all` çağırır; O BAĞLAMDA `$LOCALAPPDATA`
  ; `C:\ProgramData`ya çözümlenir. Yani yedek yol, TAM DA yazıldığı senaryoda
  ; (installMode=perMachine) YANLIŞ dizine bakar ve E-stop yine atlanırdı —
  ; bobinler enerjili öldürülürdü. Okuma süresince bağlamı KULLANICIYA çevir, hemen
  ; sonra geri al (kaldırıcının geri kalanı makine bağlamına güvenir).
  SetShellVarContext current
  ClearErrors
  FileOpen $0 "$LOCALAPPDATA\PEMF Vet Client\backend.port" r
  SetShellVarContext all
  IfErrors pemf_estop_done
  FileRead $0 $1
  FileClose $0
  DetailPrint "PEMF: backend.port $INSTDIR'de yok — veri kökünden okundu."
  pemf_estop_haveport:
  StrCmp $1 "" pemf_estop_done
  ; DENETİM 2026-08-04: $1 HAM satırdı ve doğrudan PowerShell -Command dizesine gömülüyordu.
  ; İki ayrı sorun: (a) backend.port kullanıcı-yazılabilir bir dizindedir (%LOCALAPPDATA%),
  ; içine `"` + `;` sokan biri keyfi komut çalıştırabilirdi; (b) FileRead satır-sonunu (CR/LF)
  ; de getirir → URL bozulur, PowerShell hatası try/catch'e düşer, E-stop SESSİZCE başarısız
  ; olur ama taskkill YİNE çalışır → bobinler enerjili kalır.
  ; IntOp, baştaki rakamları alıp gerisini atar; komutta ARTIK $1 değil SANİTİZE $2 kullanılır.
  IntOp $2 $1 + 0
  ${If} $2 < 1
  ${OrIf} $2 > 65535
    DetailPrint "PEMF: backend.port geçersiz ('$1') — E-stop atlandı."
    Goto pemf_estop_done
  ${EndIf}
  DetailPrint "PEMF: aktif seans güvenliği — bobinlere E-stop gönderiliyor (port $2)…"
  ; -TimeoutSec 10: backend bu ucu "senkron MQTT publish ~7sn worst-case" diye belgeliyor;
  ; 3 sn ESP bobinleri (6-8) yayınlanmadan dolabiliyordu. /TIMEOUT: powershell.exe'nin kendisi
  ; (AV taraması / bozuk PSModulePath) asılırsa kaldırma SÜRESİZ donmasın.
  ; ⚠️ DENETİM 2026-09-06 (iki bağımsız gözden geçirici): burası `nsExec::Exec` + `Pop $0` (dönüş
  ; ATILIYOR) + PowerShell'de `| Out-Null ... catch {}` idi. HER başarısızlık türü — powershell
  ; engelli ("error"), 20 sn aşımı ("timeout"), bayat port → bağlantı reddi, backend >10 sn asılı,
  ; backend yanıt verdi ama `confirmed=false` (STM ya da ESP yolu DOĞRULANAMADI) — ya catch {}'e
  ; düşüyor ya da yığından atılıyordu. Kaldırıcı BAŞARILI E-stop ile BİREBİR AYNI görünüyor,
  ; "gönderiliyor…" basıp taskkill /F'e geçiyordu; log da yazmıyordu. Launcher çökmüş + backend
  ; yetimken bu, sert kill'den önceki TEK bobin-durdurma noktasıdır (hasta güvenliği).
  ; Artık: ExecToStack ile dönüş kodu + çıktı ALINIR; PowerShell tek-satırı RAPORLAR
  ;   çıkış 0 → "OK status=<status> confirmed=True"   (backend /api/hardware/emergency_stop yanıtı:
  ;   çıkış 2 → "OK status=<status> confirmed=False"   {status, confirmed, stmStopped, mqttResults…})
  ;   çıkış 1 → "FAIL=<istisna mesajı>"                (bağlantı yok / zaman aşımı / HTTP hatası)
  ; `confirmed -ne $true`: alan yoksa da DOĞRULANMADI sayılır (backend'in kendi fail-closed kuralı).
  ; Tırnak kullanılmaz (NSIS `'` sınırlayıcısı + -Command `"` sınırlayıcısıyla çakışmasın); Write-Host
  ; -NoNewline: tek satır, satır-sonu yok → günlük satırı bozulmaz. /OEM: powershell boruya OEM
  ; (cp857) yazar, Türkçe istisna mesajı DetailPrint'te okunur kalsın.
  ; Kaldırma HİÇBİR koşulda engellenmez/durdurulmaz — amaç görünürlük + kalıcı iz + elle kontrol uyarısı.
  ; ⚠️ GÖZDEN GEÇİRME 2026-09-06: PowerShell'in HER `$`'ı `$$` ile KAÇIRILIR (yalnız NSIS port kaydı `$2`
  ; çıplak kalır). makensis `'...'` içindeki `$(...)`'ı LangString sanıp (uyarı 6040) çalışma zamanında
  ; BOŞ dizgeye çözüyordu → derlenmiş kaldırıcı fiilen "OK status= confirmed= t=" / "FAIL=" gönderiyordu
  ; (gerçek derleme + koşturmayla ölçüldü). Çıkış kodları etkilenmiyordu ama günlük/uyarı teşhis
  ; değerini yitiriyordu. test_kanca_gercekten_nsis_ile_derlenir artık 6040/6000 uyarısında KIRMIZI.
  nsExec::ExecToStack /OEM /TIMEOUT=20000 'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "try { $$r = Invoke-RestMethod -Uri http://127.0.0.1:$2/api/hardware/emergency_stop -Method POST -TimeoutSec 10; Write-Host -NoNewline OK status=$$($$r.status) confirmed=$$($$r.confirmed) t=$$(Get-Date -Format s); if ($$r.confirmed -ne $$true) { exit 2 }; exit 0 } catch { Write-Host -NoNewline FAIL=$$($$_.Exception.Message) t=$$(Get-Date -Format s); exit 1 }"'
  Pop $0  ; nsExec dönüş: süreç çıkış kodu YA DA "error" (başlatılamadı) / "timeout" (20 sn aşıldı)
  Pop $1  ; yakalanan çıktı (OK …/FAIL=…); $1'in ham port satırı $2'ye sanitize edildi, artık gerekmez.
          ; İki Pop ŞART: ExecToStack yığına İKİ öğe iter; biri kalsa aşağıdaki kayıt geri-yüklemesi kayar.
  ${If} $0 == "0"
    DetailPrint "PEMF: bobin E-stop DOĞRULANDI — $1"
  ${Else}
    DetailPrint "PEMF: bobin E-stop DOĞRULANAMADI (nsExec=$0 $1) — bobinleri ELLE kontrol edin; iz: %APPDATA%\PEMF_GUI\logs\uninstall_estop.log"
  ${EndIf}
  ; Kaldırıcının kendi günlüğü yoktur; kaldırmadan SONRA da okunabilen tek satırlık iz bırak.
  ; %APPDATA%\PEMF_GUI = KVKK gereği client-kaldırmanın ASLA silmediği veri kökü (bkz. dosya başlığı +
  ; POSTUNINSTALL), logs\ = backend'in de yazdığı günlük dizini (install.rs::backend_log_path_with).
  ; $APPDATA burada `all` bağlamında ProgramData'ya çözümlenir → yukarıdaki port-okumasıyla AYNI
  ; bağlam dansı: okuma/yazma süresince `current`, hemen ardından `all` (kaldırıcının geri kalanı
  ; makine bağlamına güvenir). Dizin yok / yazma izni yok → IfErrors ile ATLANIR, kaldırma sürer.
  SetShellVarContext current
  ClearErrors
  CreateDirectory "$APPDATA\PEMF_GUI\logs"
  ClearErrors
  FileOpen $3 "$APPDATA\PEMF_GUI\logs\uninstall_estop.log" a
  IfErrors pemf_estop_log_atla
  FileSeek $3 0 END
  FileWrite $3 "port=$2 nsExec=$0 $1$\r$\n"
  FileClose $3
  pemf_estop_log_atla:
  SetShellVarContext all
  ; Etkileşimli kaldırmada kullanıcıya SÖYLE (yalnız DetailPrint sessizce kayar gider). ${Silent}
  ; (self-update /S) ve $UpdateMode (Tauri yükseltmesi eski kaldırıcıyı /UPDATE ile koşturur) dışarıda:
  ; oralarda MessageBox akışı KİLİTLER. Bu bir uyarıdır, kaldırma yine devam eder (Abort YOK).
  ; Kayıt yolu LİTERAL %APPDATA%: bu noktada bağlam yine `all` → $APPDATA ProgramData'ya çözümlenir,
  ; kullanıcıya YANLIŞ yol gösterirdi (gözden geçirme 2026-09-06).
  ${If} $0 != "0"
    ${IfNot} ${Silent}
    ${AndIf} $UpdateMode <> 1
      MessageBox MB_OK|MB_ICONEXCLAMATION "PEMF: bobin acil-durdurma DOĞRULANAMADI ($0).$\r$\n$\r$\nBobinleri ELLE kontrol edin (cihaz üzerindeki göstergeler / fiziksel kapatma).$\r$\n$\r$\nAyrıntı: $1$\r$\nKayıt: %APPDATA%\PEMF_GUI\logs\uninstall_estop.log"
    ${EndIf}
  ${EndIf}
  ; STM STOP'un async seri-kuyruktan porta yazılması için bekle (backend flush deadline'ı 1.5s).
  Sleep 1800
  pemf_estop_done:
  ; --- Ardından backend sürecini durdur (orphan runtime/ dosya kilidini bırak) ---
  ; (Servis modunda NSSM yeniden başlatır; o senaryo Inno-backend uninstaller'ının alanı.)
  ; taskkill'i kayıt-geri-yüklemeden ÖNCE yap; her iki yolda (atla/ilerle) yığın burada [$3o,$2o,$1o,$0o].
  DetailPrint "PEMF: artık backend süreçleri durduruluyor…"
  nsExec::Exec /TIMEOUT=30000 'taskkill /F /IM PEMF_Backend.exe /T'
  Pop $0  ; taskkill nsExec dönüş-kodunu da AT
  ; ⚠️ DENETİM 2026-08-15 (kur→kaldır→yeniden-kur BOZULMASI): burada YALNIZ PEMF_Backend.exe
  ; öldürülüyordu. `/T` süreç-AĞACINI öldürür, yani backend HÂLÂ AYAKTAYSA çocukları olan
  ; mosquitto/cloudflared de gider. Ama backend daha ÖNCE çöktüyse/zorla kapatıldıysa (ya da
  ; launcher'ın `child.kill()`i — TerminateProcess ÇOCUK-AĞACINI öldürmez) mosquitto YETİM kalır:
  ; ebeveyn PID'i ölüdür → HİÇBİR ağaçta değildir → bu satır onu BULAMAZ. Üç sonucu vardı:
  ;   1) `runtime\...\mosquitto.exe` dosya-KİLİTLİ → POSTUNINSTALL'daki `RMDir /r "$INSTDIR\runtime"`
  ;      SESSİZCE başarısız (NSIS RMDir hata vermez) → kurulum kökü artıkla geride kalır,
  ;   2) yeniden kurulumda base re-extract o kilitli dosyaya çarpar → "os error 32",
  ;   3) yetim broker 1883'ü TUTAR → yeni backend kendi broker'ını bağlayamaz → MQTT ölü →
  ;      **ESP bobinleri 6-8 ULAŞILAMAZ** (STM 1-5 seri porttan çalışmaya devam eder, yani arıza
  ;      "yarı çalışan cihaz" gibi görünür ve teşhisi zordur).
  ; Launcher içi "Kaldır" düğmesi bu üçlüyü zaten `kill_stray_backends()` ile temizliyordu
  ; (core/src/backend.rs) — AMA kullanıcı Ayarlar ▸ Uygulamalar'dan kaldırdığında launcher HİÇ
  ; çalışmaz, yalnız bu kanca koşar. İki yol AYNI olmalı; isim listesi orayla birebir aynı tutulur.
  ; SIRA ÖNEMLİ: backend ÖNCE ölmeli — MosquittoSupervisor._monitor_loop (services/
  ; headless_services.py) broker'ı ölü görürse YENİDEN BAŞLATIR; önce mosquitto'yu öldürmek
  ; supervisor'ın onu geri getirmesine yarar. Backend zaten yukarıda öldürüldü.
  nsExec::Exec /TIMEOUT=30000 'taskkill /F /IM mosquitto.exe /T'
  Pop $0
  nsExec::Exec /TIMEOUT=30000 'taskkill /F /IM cloudflared.exe /T'
  Pop $0
  Sleep 800
  Pop $3  ; orijinal $3 geri yüklenir
  Pop $2  ; orijinal $2 geri yüklenir
  Pop $1  ; orijinal $1 geri yüklenir
  Pop $0  ; orijinal $0 geri yüklenir
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; --- İndirilen payload'u (runtime ~600MB + ai_models ~2GB + cache = profiller + uygulama çekirdeği)
  ;     NE ZAMAN sileriz? Tauri'nin KENDİ kaldırması payload'a DOKUNMAZ (Section Uninstall yalnız
  ;     launcher exe'sini siler; `RMDir "$INSTDIR"` ÖZYİNELEMESİZ = doluysa no-op). Payload'ı silen
  ;     TEK yer BU hook. Üç durum:
  ;   1) YÜKSELTME (Tauri eski uninstaller'ı `/UPDATE` ile koşturur; /S EKLEMEZ — bkz. aşağıdaki
  ;      DENETİM notu) → KORU (3GB tekrar inmesin; SHA-cache anında geçer).
  ;   2) İnteraktif + 'Uygulama verisini sil' İŞARETLİ            → TAM temizlik.
  ;   3) İnteraktif + İŞARETSİZ (checkbox VARSAYILANI)             → KORU. (#bug-fix: eskiden checkbox'a
  ;      BAKILMADAN interaktif her kaldırmada silinirdi → kullanıcı kutuyu işaretlemese bile profiller
  ;      gidiyor, yeniden kurulumda ~2.6GB TEKRAR iniyordu. Artık işaretsiz = indirilen her şey KORUNUR
  ;      → silip yeniden kurunca profiller anında hazır, tekrar İNMEZ.)
  ; $DeleteAppDataCheckboxState: Tauri'nin un.ConfirmLeave'de okuduğu kutu durumu (1=işaretli); bu hook
  ; Section Uninstall sonunda (checkbox-silmesinden SONRA) çalışır → değer geçerlidir.
  ; ⚠️ DENETİM 2026-08-04: yükseltme tespiti ${Silent} ile yapılıyordu ve bu YANLIŞTI.
  ; Üretilen installer.nsi:352 eski uninstaller'ı `"...uninstall.exe" /UPDATE _?=<dir>` ile çağırır —
  ; `/S` EKLEMEZ → yükseltmede ${Silent} FALSE'tur. Onay sayfası da yalnız PASSIVE modda atlanır
  ; (installer.nsi:458 un.SkipIfPassive), yani interaktif yükseltmede 'Uygulama verisini sil' kutusu
  ; kullanıcıya GÖSTERİLİR. Kutu işaretliyse bu blok ~3 GB runtime+model'i YÜKSELTME sırasında
  ; siliyordu (tam da kaçınmak istediği şey). Tauri kendi app-data silmesini zaten
  ; `$DeleteAppDataCheckboxState = 1 ${AndIf} $UpdateMode <> 1` ile koruyor (installer.nsi:821-822);
  ; aynı değişkeni burada da kullan. ($UpdateMode installer.nsi:69'da global, :741'de bu
  ; Section'dan ÖNCE ayrıştırılıyor → hook çalışırken DOLUDUR.)
  ${If} ${Silent}
  ${OrIf} $UpdateMode = 1
    DetailPrint "PEMF: yükseltme — indirilen modeller ve önbellek korunuyor (tekrar inmez)."
  ${ElseIf} $DeleteAppDataCheckboxState = 1
    DetailPrint "PEMF: 'uygulama verisini sil' işaretli — indirilen çalışma-zamanı ve modeller kaldırılıyor…"
    RMDir /r "$INSTDIR\runtime"
    RMDir /r "$INSTDIR\ai_models"
    RMDir /r "$INSTDIR\cache"
    ; DENETİM: burada `RMDir /r "$INSTDIR"` vardı. Tauri şablonu (installer.nsi:771) BİLEREK
    ; ÖZYİNELEMESİZ `RMDir "$INSTDIR"` kullanır — $INSTDIR kullanıcının seçtiği herhangi bir dizin
    ; olabilir (MUI_PAGE_DIRECTORY gösteriliyor, installer.nsi:384) ve /r o dizindeki PEMF-dışı
    ; her şeyi de yok eder. Kendi bıraktığımız dosyaları TEK TEK silip özyinelemesiz RMDir yap:
    ; dizin bize aitse boşalıp gider, kullanıcının başka dosyası varsa DOKUNULMAZ.
    ; DENETİM 2026-08-04 (P3): liste EKSİKTİ. `selfupdate_attempt.json` (bu denetimde eklendi)
    ; ve `installed_profiles.json.bak` (atomik yazımın yedeği — kurulu makinede diskte GÖRÜLDÜ)
    ; atlanıyordu → özyinelemesiz `RMDir "$INSTDIR"` boş olmayan dizinde BAŞARISIZ olur ve
    ; kurulum dizini artıkla birlikte geride kalır. Yeni bir durum dosyası eklenirse BURAYA da
    ; eklenmeli (aynı küme: extract.rs::PROFILE_FORBIDDEN_TOP).
    Delete "$INSTDIR\installed_profiles.json"
    Delete "$INSTDIR\installed_profiles.json.bak"
    Delete "$INSTDIR\pending_install.json"
    Delete "$INSTDIR\selfupdate_attempt.json"
    Delete "$INSTDIR\selfupdate_inprogress.json"
    Delete "$INSTDIR\backend.port"
    ; DENETİM 2026-08-06: "Beni hatırla" oturumu (DPAPI ile şifreli Supabase access+refresh
    ; jetonu) bu denetimde eklendi ve listeye ALINMAMIŞTI. İki sonucu vardı: (1) özyinelemesiz
    ; `RMDir "$INSTDIR"` dolu dizinde başarısız olup kurulum kökünü artıkla geride bırakıyordu
    ; (yukarıdaki 2026-08-04 notunun aynısı), (2) `core/src/secret_store.rs` modül başlığındaki
    ; "blob install_root içinde tutulur → uygulama kaldırılınca oturum da gider" güvencesi
    ; GERÇEK DEĞİLDİ: kullanıcı uygulamayı kaldırsa da jetonu diskte kalıyordu.
    Delete "$INSTDIR\auth_session.bin"
    ; DENETİM 2026-08-23 (C14): liste ÜÇÜNCÜ kez geride kalmıştı. 2026-08-08/09'da eklenen üç kök
    ; durum dosyası buraya işlenmemişti; aynı yorumun (yukarıda) koyduğu kural fiilen bozuktu.
    ; `installed_packages.json` = kurulu paket kaydı, `install_id.txt` = kademeli-yayın dilimi
    ; (kaldır-yeniden kur sonrası cihaz aynı dilimde sıkışıyordu), `backup_dir.txt` = yedek hedefi.
    Delete "$INSTDIR\installed_packages.json"
    Delete "$INSTDIR\install_id.txt"
    Delete "$INSTDIR\backup_dir.txt"
    Delete "$INSTDIR\runtime_attempt.json"
    ; ⚠️ SAHNELEME DİZİNLERİ: yalnız `runtime` siliniyordu. Kesintiye uğramış bir güncellemeden
    ; kalan bu kardeşler (her biri ≤1,19 GB) HİÇBİR yolla silinmiyordu → kaldırma "başarılı"
    ; görünürken diskte gigabaytlar kalıyordu.
    RMDir /r "$INSTDIR\runtime.new"
    RMDir /r "$INSTDIR\runtime.old"
    RMDir /r "$INSTDIR\runtime.bozuk"
    RMDir "$INSTDIR"
    ; Yükseltme-öncesi eski boşluksuz kurulum kökü (rename migrasyonu atlanmışsa) kalıntısı.
    RMDir /r "$LOCALAPPDATA\PEMFVetClient"
    ; Tauri/WebView2 app-verisi (mevcut kimlik + eski "vpemf" kimlik kalıntısı).
    RMDir /r "$APPDATA\com.pemfmedical.vetclient"
    RMDir /r "$LOCALAPPDATA\com.pemfmedical.vetclient"
    RMDir /r "$APPDATA\com.vpemf.client"
    RMDir /r "$LOCALAPPDATA\com.vpemf.client"
    ; Eski client registry ayarları (bugün com.pemfmedical; eski sürüm "vpemf" bırakırdı).
    DeleteRegKey HKCU "Software\vpemf"
    ; ⚠️ KALDIRMA DENETİMİ 2026-08-29: per-user `PEMF_System` kalıntısı hiçbir yerde
    ; silinmiyordu. Ayak izi tanımı (`pemf_footprint.ps1`) onu `Kvkk=$false` işaretliyor —
    ; yani TIBBİ VERİ DEĞİL, silinmesi gerekiyordu; ama aşağıdaki not "ProgramData/hotspot
    ; ADMIN uninstaller'ın işi" derken bu PER-USER dizini de kapsıyor sanılmıştı. Ölçüldü:
    ; kaldırmadan sonra `hotspot.log` geride kaldı. Buradaki yol kullanıcı-kapsamlıdır ve
    ; admin GEREKTİRMEZ → kancanın işi. (ProgramData tarafı gerçekten admin uninstaller'da.)
    RMDir /r "$LOCALAPPDATA\PEMF_System"
    DetailPrint "PEMF Vet Client temizliği tamamlandı."
  ${Else}
    DetailPrint "PEMF: 'uygulama verisini sil' işaretsiz — indirilen profiller/modeller KORUNUYOR (yeniden kurulumda tekrar inmez). Tamamen silmek için kaldırırken kutuyu işaretleyin."
  ${EndIf}
  ; ── KVKK AÇIKLIĞI (2026-08-08) ────────────────────────────────────────────────────────────
  ; "Uygulama verisini sil" kutusu tıbbi veriyi SİLMEZ (yalnız indirilen runtime/model/önbellek).
  ; Kutuyu işaretleyen kullanıcı makul olarak "verilerim gitti" diye anlar → YANLIŞ GÜVENCE.
  ; Denetim Masası'ndan kaldıranlar client'ın açıklayıcı diyaloğunu GÖRMEZ; burada söylemek
  ; tek şansımız. Log'a her zaman yazılır; etkileşimli kaldırmada ayrıca gösterilir.
  ; ⚠️ ${Silent} kontrolü ŞART: self-update `/S` ile kurar; orada MessageBox kurulumu KİLİTLERDİ.
  DetailPrint "PEMF: Hasta kayıtları, seans geçmişi ve AI analiz geçmişi KORUNDU (tıbbi kayıt) — %APPDATA%\PEMF_GUI"
  ${IfNot} ${Silent}
  ${AndIf} $UpdateMode <> 1
    MessageBox MB_OK|MB_ICONINFORMATION "PEMF Vet kaldırıldı.$\r$\n$\r$\nHASTA KAYITLARI, SEANS GEÇMİŞİ ve AI ANALİZ GEÇMİŞİ SİLİNMEDİ.$\r$\nTıbbi kayıt oldukları için kaldırma sırasında korunurlar.$\r$\n$\r$\nKonum:$\r$\n$APPDATA\PEMF_GUI$\r$\n$\r$\nKalıcı silmek isterseniz bu klasörü elle silin ya da yeniden kurup uygulama içinden silin (Hastalar → 'Tümünü Sil', AI Geçmişi → 'Geçmişi Sil')."
  ${EndIf}
  ; NOT: %APPDATA%\PEMF_GUI (hasta DB + SQLCipher/Fernet anahtarları) HER YOLDA KORUNUR (KVKK).
  ; Servisler (PemfBackend/mosquitto), C:\Program Files\PEMF Backend, C:\ProgramData\*,
  ; PEMF-Hotspot görevi, firewall kuralları → ADMIN "PEMF Backend" uninstaller'ının işi.
!macroend
