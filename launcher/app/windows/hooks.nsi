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
  nsExec::Exec /TIMEOUT=20000 'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod -Uri http://127.0.0.1:$2/api/hardware/emergency_stop -Method POST -TimeoutSec 10 | Out-Null } catch {}"'
  Pop $0  ; nsExec::Exec dönüş-kodunu yığından AT — aksi halde aşağıdaki Pop'lar orijinal
          ; kayıtlar yerine bu dönüşü yükler ve bir kayıt yığında sızardı (yığın dengesi).
  ; STM STOP'un async seri-kuyruktan porta yazılması için bekle (backend flush deadline'ı 1.5s).
  Sleep 1800
  pemf_estop_done:
  ; --- Ardından backend sürecini durdur (orphan runtime/ dosya kilidini bırak) ---
  ; (Servis modunda NSSM yeniden başlatır; o senaryo Inno-backend uninstaller'ının alanı.)
  ; taskkill'i kayıt-geri-yüklemeden ÖNCE yap; her iki yolda (atla/ilerle) yığın burada [$2o,$1o,$0o].
  DetailPrint "PEMF: artık backend süreçleri durduruluyor…"
  nsExec::Exec /TIMEOUT=30000 'taskkill /F /IM PEMF_Backend.exe /T'
  Pop $0  ; taskkill nsExec dönüş-kodunu da AT
  Sleep 800
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
    Delete "$INSTDIR\backend.port"
    ; DENETİM 2026-08-06: "Beni hatırla" oturumu (DPAPI ile şifreli Supabase access+refresh
    ; jetonu) bu denetimde eklendi ve listeye ALINMAMIŞTI. İki sonucu vardı: (1) özyinelemesiz
    ; `RMDir "$INSTDIR"` dolu dizinde başarısız olup kurulum kökünü artıkla geride bırakıyordu
    ; (yukarıdaki 2026-08-04 notunun aynısı), (2) `core/src/secret_store.rs` modül başlığındaki
    ; "blob install_root içinde tutulur → uygulama kaldırılınca oturum da gider" güvencesi
    ; GERÇEK DEĞİLDİ: kullanıcı uygulamayı kaldırsa da jetonu diskte kalıyordu.
    Delete "$INSTDIR\auth_session.bin"
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
