# =============================================================================
# PEMF AYAK İZİ — makinede yaratılan HER ŞEYİN TEK KAYNAĞI (Faz 2 konsolidasyon).
# -----------------------------------------------------------------------------
# ÜÇ kaldırıcı (Tauri client-hook / Inno backend / eski GUI) + standalone tam-kaldırıcı
# BU tanımdan türer → yeni artefakt eklenince TEK yer güncellenir, drift biter.
#
# KVKK: Kvkk=$true olan yollar/kimlikler HASTA VERİSİDİR → yalnız -IncludePatientData
# ile silinir (VARSAYILAN KORU). Owner: hangi kurulum yarattı (client/backend/gui/shared).
#
# Bu dosya SADECE veri döndürür (yan etkisiz) → pemf_teardown.ps1 tüketir, test doğrular.
# =============================================================================

# Per-user artefaktlar TÜM profillerde olabilir; backend LocalSystem çalıştığından
# systemprofile'da da yazar. Var olan profil köklerini döndür.
function Get-PemfProfileRoots {
    # NOT: kökleri Test-Path'leME — systemprofile'a non-admin erişilemez (access-denied fırlatır)
    # ama her zaman vardır; C:\Users\* zaten Get-ChildItem'dan gelir. Var-olma kontrolü,
    # hedef başına Remove-PemfPaths içinde yapılır (orada zararsız Test-Path).
    $roots = @()
    try { $roots += (Get-ChildItem 'C:\Users' -Directory -ErrorAction SilentlyContinue).FullName } catch {}
    $roots += 'C:\Windows\System32\config\systemprofile'   # LocalSystem — her Windows'ta var
    @($roots | Where-Object { $_ } | Select-Object -Unique)
}

function Get-PemfFootprint {
    # Kind: 'Abs' = mutlak makine yolu | 'PerUser' = profil köküne göreli (tüm profillerde aranır)
    $paths = @(
        # ── Uygulama dizinleri (ikili dosyalar) — hasta-verisi DEĞİL ──
        @{ Kind = 'Abs';     Path = 'C:\Program Files\PEMF Backend';                Owner = 'backend'; Kvkk = $false }
        @{ Kind = 'Abs';     Path = 'C:\Program Files\PEMF';                        Owner = 'backend'; Kvkk = $false }
        @{ Kind = 'PerUser'; Path = 'AppData\Local\PEMF Vet Client';               Owner = 'client';  Kvkk = $false }
        @{ Kind = 'PerUser'; Path = 'AppData\Local\PEMFVetClient';                 Owner = 'client';  Kvkk = $false }  # eski isim
        # ── Uygulama verisi (non-patient) ──
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_GUI\ai_models';           Owner = 'shared';  Kvkk = $false }
        # ⚠️ DENETİM 2026-08-04 (P1): 'C:\ProgramData\PEMF_System' KÖKÜ Kvkk=$false olarak
        # listeleniyordu ve koşulsuz `Remove-Item -Recurse` ile siliniyordu. Oysa üretim profili
        # (deploy/device.env:58) `PEMF_DATA_DIR=C:\ProgramData\PEMF_System` veriyor ve
        # apps/backend/utils/path_utils.py bunu `<PEMF_DATA_DIR>\PEMF_GUI` yapıyor → hasta DB'si (patients.db),
        # tedavi geçmişi, `.sqlcipher_key` ve `pemf_secrets.json` TAM OLARAK o ağacın içindeydi.
        # Sonuç: "HASTA VERİSİ KORUNACAK" diyen varsayılan kaldırma, hasta verisini SİLİYORDU.
        # ÇÖZÜM: kökü ARTIK LİSTELEME; yalnız hasta-verisi OLMAYAN alt dizinleri say. Veri kökü
        # aşağıda KVKK bloğunda ayrıca korunuyor. (Üst dizin silinirse alt-koruma anlamsız olurdu.)
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_System\logs';             Owner = 'shared';  Kvkk = $false }
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_System\mosquitto';        Owner = 'shared';  Kvkk = $false }
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_System\hotspot.json';     Owner = 'shared';  Kvkk = $false }
        # staging profili (deploy/staging.env: PEMF_DATA_DIR=C:\ProgramData\PEMF_Staging) —
        # footprint'te HİÇ yoktu → kaldırma sonrası kalıntı kalıyordu (KVKK "sildim" raporu eksik).
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_Staging\logs';            Owner = 'shared';  Kvkk = $false }
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_Staging\mosquitto';       Owner = 'shared';  Kvkk = $false }
        @{ Kind = 'PerUser'; Path = 'AppData\Local\PEMF_System';                   Owner = 'shared';  Kvkk = $false }
        @{ Kind = 'PerUser'; Path = 'AppData\Local\PEMF_DigitalTwin_Installation'; Owner = 'gui';     Kvkk = $false }
        @{ Kind = 'PerUser'; Path = 'AppData\Local\PEMF_GUI_OneFile';              Owner = 'gui';     Kvkk = $false }
        # NOT: eski GUI %APPDATA%\Ultralytics'i de siliyordu — KASITEN ÇIKARILDI: üçüncü-parti
        # ML framework cache'i (PEMF-markası değil, re-download edilebilir), silmek kullanıcının
        # PEMF-dışı ML işini bozabilir. Konsolidasyonun bilinçli kararı = kapsamda değil.
        @{ Kind = 'PerUser'; Path = 'AppData\Roaming\com.pemfmedical.vetclient';   Owner = 'client';  Kvkk = $false }
        @{ Kind = 'PerUser'; Path = 'AppData\Local\com.pemfmedical.vetclient';     Owner = 'client';  Kvkk = $false }
        @{ Kind = 'PerUser'; Path = 'AppData\Roaming\com.vpemf.client';            Owner = 'client';  Kvkk = $false }
        @{ Kind = 'PerUser'; Path = 'AppData\Local\com.vpemf.client';              Owner = 'client';  Kvkk = $false }
        # ── HASTA VERİSİ (KVKK) — yalnız -IncludePatientData ile silinir ──
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_GUI';                     Owner = 'shared';  Kvkk = $true  }
        # device/server profilinin GERÇEK veri kökü (PEMF_DATA_DIR=C:\ProgramData\PEMF_System):
        # patients.db + treatment geçmişi + .sqlcipher_key + pemf_secrets.json BURADA.
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_System\PEMF_GUI';         Owner = 'shared';  Kvkk = $true  }
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_Staging\PEMF_GUI';        Owner = 'shared';  Kvkk = $true  }
        @{ Kind = 'PerUser'; Path = 'AppData\Roaming\PEMF_GUI';                    Owner = 'shared';  Kvkk = $true  }
        @{ Kind = 'PerUser'; Path = '.pemf_gui';                                   Owner = 'gui';     Kvkk = $true  }
        # ⚠️ DENETİM 2026-08-28 #02 — BULUT CİHAZ KİMLİĞİ (veri kökünün DIŞINDA, BİLEREK).
        # `device_registry_secret` artık burada tutuluyor: veri kökü yenilendiğinde sırrın
        # kaybolması, cihazın buluta KALICI olarak yazamamasına yol açıyordu (13 gün ölçüldü).
        # Sır kasıtlı olarak `PEMF_System\PEMF_GUI` dışında; ama bulut YAZMA YETKİSİ taşıdığı
        # için KVKK kapsamındadır: "cihazı kaldırdım" diyen klinikte yetki makinede KALMAMALI.
        # Bu satır o ödünleşimin karşılığıdır — kaldırılırsa yetki geride kalır.
        # (Sıradan kaldır-kur bu dosyaya DOKUNMAZ; yalnız -IncludePatientData siler.)
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_System\device_identity.json'; Owner = 'shared'; Kvkk = $true }
        # A-04 · D1.104 — YEREL MQTT BROKER KİMLİĞİ (`utils.mqtt_kimlik`; device_identity.json ile AYNI ödünleşim):
        # ESP'lere YAKILAN parolanın tek kaynağı. Sıradan kaldır-kur DOKUNMAZ (silinseydi yeniden kurulumda yeni parola
        # üretilir, yakılmış ESP'ler broker'a BAĞLANAMAZ — bobinin STOP yolu kopardı); KVKK silmesi götürür.
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_System\mqtt_kimlik.json';    Owner = 'shared'; Kvkk = $true }
        # D2.74: staging profili bulut kimliğini AYRI tutar (deploy/staging.env PEMF_DEVICE_IDENTITY_DIR=C:\ProgramData\PEMF_Staging).
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_Staging\device_identity.json'; Owner = 'shared'; Kvkk = $true }
        # ⚠️ Y85 (İG-9.88 · D2.E04): faturalanmamış AI tüketim defteri (`servers/jeton.py` → `<PEMF_DATA_DIR>\jeton_bekleyen.json`;
        # PEMF_DATA_DIR yoksa `~\.pemf`). Hasta verisi DEĞİL ama cihaz kimliği taşır → yalnız -IncludePatientData siler; sıradan
        # kaldır-kur KORUR (silinseydi çevrimdışı birikmiş tüketim hiç faturalanmazdı). Eskiden hiçbir kaldırma dokunmuyordu.
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_System\jeton_bekleyen.json';  Owner = 'shared'; Kvkk = $true }
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_Staging\jeton_bekleyen.json'; Owner = 'shared'; Kvkk = $true }
        @{ Kind = 'PerUser'; Path = '.pemf\jeton_bekleyen.json';                       Owner = 'shared'; Kvkk = $true }
        # 4B-1.4: defterin atomik yazım geçici dosyası (`.tmp`) ve bozuk defter karantinası (`.bozuk`) — AYNI veri, AYNI kural
        # (`servers/jeton.py` DEFTER_GECICI_EKI / DEFTER_KARANTINA_EKI).
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_System\jeton_bekleyen.json.tmp';    Owner = 'shared'; Kvkk = $true }
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_Staging\jeton_bekleyen.json.tmp';   Owner = 'shared'; Kvkk = $true }
        @{ Kind = 'PerUser'; Path = '.pemf\jeton_bekleyen.json.tmp';                         Owner = 'shared'; Kvkk = $true }
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_System\jeton_bekleyen.json.bozuk';  Owner = 'shared'; Kvkk = $true }
        @{ Kind = 'Abs';     Path = 'C:\ProgramData\PEMF_Staging\jeton_bekleyen.json.bozuk'; Owner = 'shared'; Kvkk = $true }
        @{ Kind = 'PerUser'; Path = '.pemf\jeton_bekleyen.json.bozuk';                       Owner = 'shared'; Kvkk = $true }
        # ⚠️ Y99 (O-A2-1.a · D2.E04): veri kökü yazılamayınca backend günlüğü geçici dizine düşer (`backend_service.py`
        # `tempfile.gettempdir()\PEMF_GUI\logs`); günlük hasta adı taşıyabilir → KVKK tam temizliği götürür. Kullanıcı süreci:
        # `%LOCALAPPDATA%\Temp`; LocalSystem servisi: `C:\Windows\Temp` (Windows 11 24H2+: `C:\Windows\SystemTemp`).
        @{ Kind = 'PerUser'; Path = 'AppData\Local\Temp\PEMF_GUI';                     Owner = 'shared'; Kvkk = $true }
        @{ Kind = 'Abs';     Path = 'C:\Windows\Temp\PEMF_GUI';                        Owner = 'shared'; Kvkk = $true }
        @{ Kind = 'Abs';     Path = 'C:\Windows\SystemTemp\PEMF_GUI';                  Owner = 'shared'; Kvkk = $true }
    )
    [pscustomobject]@{
        Paths       = $paths
        # D2.74: staging servisi AYRI addadır (setup_services.ps1 -Mode staging → PemfBackendStaging); tam temizlik onu da kaldırır.
        Services    = @('PemfBackend', 'PemfBackendStaging', 'mosquitto')
        Tasks       = @('PEMF-Hotspot')
        FirewallRx  = 'pemf|mosquitto|cloudflared'    # eski adlar (pemf_gui/PEMF_Service_Port_*/cloudflared) dahil
        EnvRx       = '^PEMF_'                          # HKLM Session Manager Environment (Makine kapsamı)
        Registry    = @(
            # ⚠️ İKİ ÜRETİCİ ADI DA TARANIR. Inno kurulumu `[Registry]`ye YAYINCI ADIYLA yazar
            # (SOFTWARE\<MyAppPublisher>\PEMF Backend). Ünvan 2026-08-11'de "PEMF Medical
            # Technologies" -> "İBİA Teknoloji Ltd. Şti." olarak düzeltildi; ESKİ ad LİSTEDE
            # KALMALI, yoksa o adla kurulmuş makinelerde kaldırma anahtarı geride kalır.
            @{ Path = 'HKLM:\SOFTWARE\İBİA Teknoloji Ltd. Şti.';  Owner = 'shared' }  # üretici (güncel)
            @{ Path = 'HKLM:\SOFTWARE\PEMF Medical Technologies'; Owner = 'shared' }  # üretici (ESKİ ad — silme)
            # Client (NSIS) üretici anahtarı: `Software\<MANUFACTURER>\<ürün>` → kurulum yolu.
            # ⚠️ 2026-08-11 öncesi `bundle.publisher` TANIMSIZDI; Tauri kimliğin ikinci parçasına
            # düşüp `pemfmedical` yazıyordu. Ünvan tanımlanınca yol DEĞİŞTİ; eski anahtar kaldırma
            # sırasında artık eşleşmez ve GERİDE KALIR — bu yüzden ikisi de taranır.
            @{ Path = 'HKCU:\Software\İBİA Teknoloji Ltd. Şti.';  Owner = 'client' }  # client üretici (güncel)
            @{ Path = 'HKCU:\Software\pemfmedical';               Owner = 'client' }  # client üretici (ESKİ — yetim)
            @{ Path = 'HKCU:\Software\vpemf';                     Owner = 'client' }  # eski client kalıntısı
        )
        # KVKK — Windows Credential Manager hedef adları. python-keyring'in Windows arka ucu hedefi
        # "<ad>@<servis>" biçiminde yazar (servis = 'PEMF_GUI'); ad listesi runtime'dan türetilir:
        #   apps/backend/utils/secrets_manager.py  _keyring_get("sqlcipher_key"|"patient_fernet_key"|"master_secret")
        #   keyring.set_password ile YAZANLAR: apps/backend/database/sqlcipher_util.py ("sqlcipher_key") +
        #   pemf_gui/config.py ("patient_fernet_key") — ikisi de aşağıdaki listede (denetim 2026-09-06)
        # ⚠️ DENETİM 2026-09-06: burada 'fernet_key@PEMF_GUI' yazıyordu; runtime ise 'patient_fernet_key'
        # kullanır → o kayıt HİÇ silinmiyor, teardown ise sonucu doğrulamadığından her koşuda sahte
        # "kimlik silindi" raporluyordu. Ad düzeltildi + 'master_secret' eklendi. ESKİ adlar ('PEMF_GUI',
        # 'api_token@PEMF_GUI', 'fernet_key@PEMF_GUI') eski kurulumlar için LİSTEDE KALIR — teardown
        # artık var-olmayanı "yoktu" diye raporlar, başarısızlık saymaz. tests/test_teardown_kimlik_dogrulama.py
        # bu listeyi runtime adlarıyla karşılaştırır.
        Credentials = @(
            'patient_fernet_key@PEMF_GUI', 'sqlcipher_key@PEMF_GUI', 'master_secret@PEMF_GUI',   # runtime (güncel)
            'fernet_key@PEMF_GUI', 'PEMF_GUI', 'api_token@PEMF_GUI'                              # ESKİ kurulum adları
        )
    }
}
