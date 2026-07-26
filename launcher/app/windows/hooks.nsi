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
  ; Launcher pencereyle birlikte backend child'ını öldürür; ama launcher çökmüş/zorla
  ; kapatılmışsa PEMF_Backend.exe orphan kalıp runtime/ dizininde dosya KİLİDİ tutar →
  ; recursive silme başarısız olur. Önce kilidi bırak. (Servis modunda NSSM yeniden
  ; başlatır; o senaryo Inno-backend uninstaller'ının alanı.)
  DetailPrint "PEMF: artık backend süreçleri durduruluyor…"
  nsExec::Exec 'taskkill /F /IM PEMF_Backend.exe /T'
  Sleep 800
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Tauri şablonu yalnız exe'yi + kısayolları siler; launcher'ın İNDİRDİĞİ payload
  ; ($INSTDIR altındaki runtime/ ~600MB + ai_models/ ~2GB + cache/) NON-recursive
  ; RMDir'den geri kalır → GB'larca yetim dizin. Recursive temizle.
  DetailPrint "PEMF: indirilen çalışma-zamanı ve modeller kaldırılıyor…"
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
  ; NOT: %APPDATA%\PEMF_GUI (hasta DB + SQLCipher/Fernet anahtarları) KASITLI KORUNUR.
  ; Servisler (PemfBackend/mosquitto), C:\Program Files\PEMF Backend, C:\ProgramData\*,
  ; PEMF-Hotspot görevi, firewall kuralları → ADMIN "PEMF Backend" uninstaller'ının işi.
!macroend
