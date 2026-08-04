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
        # utils/path_utils.py bunu `<PEMF_DATA_DIR>\PEMF_GUI` yapıyor → hasta DB'si (patients.db),
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
    )
    [pscustomobject]@{
        Paths       = $paths
        Services    = @('PemfBackend', 'mosquitto')
        Tasks       = @('PEMF-Hotspot')
        FirewallRx  = 'pemf|mosquitto|cloudflared'    # eski adlar (pemf_gui/PEMF_Service_Port_*/cloudflared) dahil
        EnvRx       = '^PEMF_'                          # HKLM Session Manager Environment (Makine kapsamı)
        Registry    = @(
            @{ Path = 'HKLM:\SOFTWARE\PEMF Medical Technologies'; Owner = 'shared' }  # üretici (backend+gui)
            @{ Path = 'HKCU:\Software\vpemf';                     Owner = 'client' }  # eski client kalıntısı
        )
        Credentials = @('fernet_key@PEMF_GUI', 'sqlcipher_key@PEMF_GUI', 'PEMF_GUI', 'api_token@PEMF_GUI')  # KVKK
    }
}
