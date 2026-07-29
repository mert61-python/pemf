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
  ClearErrors
  FileOpen $0 "$INSTDIR\backend.port" r
  IfErrors pemf_estop_done
  FileRead $0 $1
  FileClose $0
  StrCmp $1 "" pemf_estop_done
  DetailPrint "PEMF: aktif tedavi güvenliği — bobinlere E-stop gönderiliyor (port $1)…"
  nsExec::Exec 'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod -Uri http://127.0.0.1:$1/api/hardware/emergency_stop -Method POST -TimeoutSec 3 | Out-Null } catch {}"'
  Pop $0  ; nsExec::Exec dönüş-kodunu yığından AT — aksi halde aşağıdaki Pop $1/$0 orijinal
          ; kayıtlar yerine bu dönüşü yükler ve bir kayıt yığında sızardı (yığın dengesi).
  ; STM STOP'un async seri-kuyruktan porta yazılması için bekle (backend flush deadline'ı ~1.5s).
  Sleep 1500
  pemf_estop_done:
  ; --- Ardından backend sürecini durdur (orphan runtime/ dosya kilidini bırak) ---
  ; (Servis modunda NSSM yeniden başlatır; o senaryo Inno-backend uninstaller'ının alanı.)
  ; taskkill'i kayıt-geri-yüklemeden ÖNCE yap; her iki yolda (atla/ilerle) yığın burada [$1o,$0o].
  DetailPrint "PEMF: artık backend süreçleri durduruluyor…"
  nsExec::Exec 'taskkill /F /IM PEMF_Backend.exe /T'
  Pop $0  ; taskkill nsExec dönüş-kodunu da AT
  Sleep 800
  Pop $1  ; orijinal $1 geri yüklenir
  Pop $0  ; orijinal $0 geri yüklenir
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; --- İndirilen payload'u (runtime ~600MB + ai_models ~2GB + cache = profiller + uygulama çekirdeği)
  ;     NE ZAMAN sileriz? Tauri'nin KENDİ kaldırması payload'a DOKUNMAZ (Section Uninstall yalnız
  ;     launcher exe'sini siler; `RMDir "$INSTDIR"` ÖZYİNELEMESİZ = doluysa no-op). Payload'ı silen
  ;     TEK yer BU hook. Üç durum:
  ;   1) YÜKSELTME (Tauri eski uninstaller'ı SESSİZ /S koşturur)   → KORU (3GB tekrar inmesin; SHA-cache anında geçer).
  ;   2) İnteraktif + 'Uygulama verisini sil' İŞARETLİ            → TAM temizlik.
  ;   3) İnteraktif + İŞARETSİZ (checkbox VARSAYILANI)             → KORU. (#bug-fix: eskiden checkbox'a
  ;      BAKILMADAN interaktif her kaldırmada silinirdi → kullanıcı kutuyu işaretlemese bile profiller
  ;      gidiyor, yeniden kurulumda ~2.6GB TEKRAR iniyordu. Artık işaretsiz = indirilen her şey KORUNUR
  ;      → silip yeniden kurunca profiller anında hazır, tekrar İNMEZ.)
  ; $DeleteAppDataCheckboxState: Tauri'nin un.ConfirmLeave'de okuduğu kutu durumu (1=işaretli); bu hook
  ; Section Uninstall sonunda (checkbox-silmesinden SONRA) çalışır → değer geçerlidir.
  ${If} ${Silent}
    DetailPrint "PEMF: yükseltme — indirilen modeller ve önbellek korunuyor (tekrar inmez)."
  ${ElseIf} $DeleteAppDataCheckboxState = 1
    DetailPrint "PEMF: 'uygulama verisini sil' işaretli — indirilen çalışma-zamanı ve modeller kaldırılıyor…"
    RMDir /r "$INSTDIR\runtime"
    RMDir /r "$INSTDIR\ai_models"
    RMDir /r "$INSTDIR\cache"
    RMDir /r "$INSTDIR"
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
  ; NOT: %APPDATA%\PEMF_GUI (hasta DB + SQLCipher/Fernet anahtarları) HER YOLDA KORUNUR (KVKK).
  ; Servisler (PemfBackend/mosquitto), C:\Program Files\PEMF Backend, C:\ProgramData\*,
  ; PEMF-Hotspot görevi, firewall kuralları → ADMIN "PEMF Backend" uninstaller'ının işi.
!macroend
