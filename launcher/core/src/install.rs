// Author: mertaygn, cglrgrkn
//! Kurulum düzeni + backend'e verilecek ortam değişkenleri.
//!
//! GERİYE UYUM: buradaki yollar `apps/backend/utils/path_utils.py::get_app_data_directory()`
//! ile BİREBİR aynı olmak zorunda. Backend hasta DB'sini, SQLCipher anahtarını ve
//! sırlarını oraya yazar; launcher farklı bir dizin uydurursa yükseltilen kurulum
//! kendi verisini bulamaz.
//!
//! Python tarafı (kanonik):
//!   PEMF_DATA_DIR set  -> <PEMF_DATA_DIR>/PEMF_GUI
//!   Windows            -> %APPDATA%/PEMF_GUI        (yoksa ~/AppData/Roaming/PEMF_GUI)
//!   macOS              -> ~/Library/Application Support/PEMF_GUI
//!   diğer (Linux)      -> ~/.local/share/PEMF_GUI

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// Backend'in modelleri aradığı köklerden #1 (`PEMF_AI_MODELS_DIR`).
///
/// Neden env ile veriyoruz: `apps/backend/utils/model_downloader.py::_candidate_model_roots()`
/// sıralaması → 1) `$PEMF_AI_MODELS_DIR`  2) `%PROGRAMDATA%\PEMF_GUI\ai_models`
/// 3) app_data/.ai_models  4) proje-yanı  5) bundle. Kök #2 YALNIZ Windows'ta var
/// (`PROGRAMDATA` yoksa atlanır) → macOS/Linux'ta hiç devreye girmez. Kök #1 üç
/// platformda da aynı çalışır ve en yüksek önceliklidir.
pub const ENV_MODELS_DIR: &str = "PEMF_AI_MODELS_DIR";
pub const ENV_LOG_DIR: &str = "PEMF_LOG_DIR";

pub const ENV_DATA_DIR: &str = "PEMF_DATA_DIR";
pub const ENV_API_PORT: &str = "PEMF_API_PORT";
/// DENETİM P0: launcher backend'i yalnız model-kökü + port ile başlatıyordu. Backend `.env`
/// dosyalarını OTOMATİK YÜKLEMEZ (`load_dotenv` yok) — `deploy/device.env`'deki sıkılaştırma
/// yalnız NSSM servis kaydında uygulanır. Launcher exe'yi doğrudan spawn ettiği için
/// `PEMF_REQUIRE_AUTH` tanımsız kalıyor ve `apps/backend/servers/auth.py` varsayılanı "0" → uzak/tünel
/// erişiminde bile kimlik doğrulaması KAPALI oluyordu. LAN/localhost istekleri
/// `is_local_request` ile zaten muaf olduğundan bunu açmak yerel arayüzü ETKİLEMEZ.
pub const ENV_REQUIRE_AUTH: &str = "PEMF_REQUIRE_AUTH";
/// DENETİM 2026-08-04 (P2 #13): tek-seferlik sağlık nonce'u. `find_free_port` portu bind edip
/// HEMEN bırakır; frozen backend'in onu gerçekten bind etmesi onlarca saniye sürer. O pencerede
/// loopback'e bağlanabilen HERHANGİ bir yerel süreç portu kapabilir ve `wait_for_health` yalnız
/// HTTP 200'e baktığı için launcher onu "hazır" sanardı → kapanışta E-stop POST'u SALDIRGANIN
/// dinleyicisine gider, gerçek bobinler hastanın üzerinde çalışmaya devam ederdi.
/// Backend bu değeri `/api/health` yanıtında YALNIZ loopback'e yansıtır (bkz. system_router).
pub const ENV_HEALTH_NONCE: &str = "PEMF_HEALTH_NONCE";

/// AT-REST ŞİFRELEME (SQLCipher) — hasta verisi diske ŞİFRELİ yazılsın.
///
/// ⚠️ 2026-08-08 DENETİM BULGUSU: bu değişken `backend_env()`'de YOKTU. Servis kurulumu
/// (`scripts/setup_services.ps1`) onu geçiriyordu ama LAUNCHER yolu — yani siteden indirip kuran
/// HER klinik — geçirmiyordu. Ölçüldü (frozen backend, izole veri dizini):
///     bayraksız → `atRestEncrypted=False`   |   `PEMF_ENCRYPT_AT_REST=1` → `atRestEncrypted=True`
/// Yani sahadaki klinikler hasta verisini DÜZ METİN yazıyordu. PII maskeleme de sahip kararıyla
/// varsayılan kapalı olduğundan gerçek hasta adları diskteydi. Üstelik site üç yerde
/// "klinik verisi cihazda şifreli (SQLCipher)" diye BEYAN ediyor (config.ts + Legal.tsx).
///
/// GÜVENLİ Mİ: evet, ÖLÇÜLDÜ. sqlcipher3 frozen EXE'ye bundle'lı ve çalışıyor; mevcut DÜZ-METİN
/// veritabanı açılışta otomatik göçüyor (`_migrate_to_encrypted_if_needed`) ve veri KORUNUYOR
/// (gerçek artefaktla uçtan uca doğrulandı: bayraksız yazılan kayıt, bayrak açılınca okunabildi).
///
/// ⚠️ Backend bu bayrak açıkken SQLCipher'ı sağlayamazsa BİLEREK hard-fail eder (düz-metin PII
/// yazmaktansa DB'yi açmaz). Bu yüzden bayrağı kaldırmak "güvenli tarafa düşmek" DEĞİLDİR —
/// sessizce şifresiz çalışmaya döner. KALDIRMAYIN.
pub const ENV_ENCRYPT_AT_REST: &str = "PEMF_ENCRYPT_AT_REST";

/// UZAKTAN ERİŞİM (Cloudflare tüneli) — farklı ağdan bağlanma.
///
/// ⚠️ 2026-08-12 SAHA BULGUSU — `ENV_ENCRYPT_AT_REST` ile AYNI SINIF HATA. Bu değişken
/// `backend_env()`'de YOKTU. Servis kurulumu (`deploy/device.env` → `PEMF_ENABLE_TUNNEL=1`)
/// onu geçiriyordu ama LAUNCHER yolu — yani siteden indirip kuran HER klinik — geçirmiyordu.
/// Backend'de varsayılan KAPALI (`backend_service::_maybe_start_tunnel`), dolayısıyla:
///   • tünel hiç başlamıyor → cihazın `tunnel_url`i boş,
///   • cihaz buluta yine de kaydoluyor (`cloudRegistry: ok`, `pairingCode` dolu),
///   • mobil, adresi olmayan kaydı eleyip **"kod/kimlikle eşleşen cihaz bulunamadı"** diyor.
/// Kullanıcı doğru kodu defalarca giriyor ve sebebi anlayamıyordu (ölçüldü: `/api/health` →
/// `pairingCode: MVPDDN`, `cloudRegistry: ok`, `tunnelUrl: None`).
///
/// Oysa mobil arayüz bunu AÇIKÇA vaat ediyor: "Farklı ağ → bir kez eşleştikten sonra cihazın
/// buluttaki güncel adresinden otomatik bağlanır." Vaat ile davranış ayrışmıştı.
///
/// GÜVENLİ Mİ: tünel cihazı internete açar, evet — ama backend tüneli açarken
/// `_force_auth_for_tunnel` ile `PEMF_REQUIRE_AUTH=1`i ZORLA etkinleştirir (fail-closed);
/// kimliksiz donanım/hasta erişimi mümkün değildir. `cloudflared` pakete zaten bundle'lı.
///
/// ÇIKIŞ KAPISI: ortamda bu değişken ZATEN tanımlıysa ona dokunulmaz — internete açılmaması
/// gereken bir kurulum `PEMF_ENABLE_TUNNEL=0` ile kapatabilir, kod değişikliği gerekmez.
pub const ENV_ENABLE_TUNNEL: &str = "PEMF_ENABLE_TUNNEL";

/// STM32 PORT OTO-ALGILAMASI — bobin 1-5'in seri bağlantısı.
///
/// ⚠️ 2026-08-17 DENETİM BULGUSU — `ENV_ENCRYPT_AT_REST` ve `ENV_ENABLE_TUNNEL` ile AYNI SINIFIN
/// ÜÇÜNCÜ ÖRNEĞİ. Bu değişken `backend_env()`'de YOKTU. Servis kurulumu (`deploy/device.env`) onu
/// `auto` olarak AÇIKÇA veriyor — hem de yanındaki uyarıyla: *"boş bırakılırsa kod oto-algılama
/// YAPMAZ → sabit COM10'a düşer (yanlış port riski)"*. Ama LAUNCHER yolu — yani siteden indirip
/// kuran HER klinik, BUILD.md'nin "ANA dağıtım" dediği yol — geçirmiyordu.
///
/// Sonuç zinciri (`apps/backend/utils/stm32_transport.py`): değişken boşsa `configured = FIXED_STM32_PORT`
/// (= `COM10`) ve oto-algılama YALNIZ `auto` ile açılır. ST-Link VCP'nin COM numarası Windows'un
/// USB numaralandırmasına göre değişir (COM3/COM4/COM5…), dolayısıyla klinik PC'sinde COM10
/// olmadığında backend sonsuza dek COM10'u dener (`_mark_bad` + 3 sn cooldown) →
/// **bobin 1-5 hiç bağlanmaz.** ESP bobinleri 6-8 MQTT'den çalışmaya devam ettiği için cihaz
/// "çalışıyor gibi görünür" — 1.9.28'de aynı sınıf için kaydedilen "yarısı çalışan cihaz" tablosu.
/// Bu ayar ne arayüzde ne launcher'da açığa çıkarılmıştır (`apps/backend/servers/settings_router.py` yalnız
/// MQTT alanlarını yönetir), yani operatörün yapabileceği bir şey yoktur.
///
/// GÜVENLİ Mİ: evet. `auto`, ST-Link'e ÖZGÜ USB PID setiyle (V1/V2/V2-1/V3) eşleşir ve LattePanda
/// gibi kartlardaki onboard STM CDC'yi ELER (`_autodetect_stlink`); bulamazsa eski davranışa,
/// yani `COM10`a düşer. Dolayısıyla COM10'un doğru olduğu makinelerde davranış DEĞİŞMEZ.
///
/// ÇIKIŞ KAPISI: ortamda bu değişken ZATEN tanımlıysa ona DOKUNULMAZ — sahada portu sabitlemek
/// gereken kurulum `PEMF_STM_PORT=COM7` ile ezebilir (kod değişikliği gerekmez). `socket://`
/// (STM simülatörü) yolu da böyle korunur.
///
/// Kilit: `device_env_anahtarlari_launcherda_KARSILIGINI_BULUR` — o kapı bu sınıfın DÖRDÜNCÜSÜNÜ
/// engellemek için yazıldı (`backend_env_kumesi_bilincli_kalir` yalnız EKLEME tespit eder, EKSİKLİK
/// tespit etmez; bu bulgu tam o kör noktada yaşadı).
pub const ENV_STM_PORT: &str = "PEMF_STM_PORT";

/// ARAŞTIRMA AI PRO SÜRÜŞ BAYRAĞI (2026-09-09) — bu sınıfın ALTINCI örneği olmasın.
///
/// `deploy/device.env` bu anahtarı 2026-09-09'da (`71c0676`, "FAZ 1e") tanımladı ama launcher
/// backend'e GEÇİRMİYORDU. Sonucu sessiz ve yanıltıcıydı: tezgâh doğrulaması bitince operatör
/// `PEMF_ARASTIRMA_AIPRO=1` yazıp servisi yeniden başlatır, launcher'ın başlattığı backend'de
/// HİÇBİR ŞEY değişmez ve "açtım" sanır. (Yön fail-safe — sürüş kapalı kalır — ama operatörün
/// gördüğü durum ile gerçek durum ayrışır.)
///
/// Backend semantiği (`apps/backend/servers/ai_router.py::_arastirma_aipro_acik`): yok/boş = KAPALI; yalnız
/// `1|true|yes|on` açar. Bu yüzden varsayılanımız `"0"` — davranışı DEĞİŞTİRMEZ, sadece
/// operatörün değerinin backend'e ULAŞMASINI sağlar.
///
/// ⚠️ Kapalıyken kedi DIŞI modellerle (fantom/petri) öneri+seans 409 döner: bobinler tezgâhta
/// doğrulanmamış koordinatla SÜRÜLMEZ. Varsayılanı `"1"` yapmayın.
///
/// ÇIKIŞ KAPISI: ortamda tanımlıysa DOKUNULMAZ (`PEMF_ARASTIRMA_AIPRO=1` ile açılır).
/// Kilit: `device_env_anahtarlari_launcherda_KARSILIGINI_BULUR`.
pub const ENV_ARASTIRMA_AIPRO: &str = "PEMF_ARASTIRMA_AIPRO";

/// KEDİ AI PRO KAPALI DÖNGÜ SÜRÜŞÜ (LN L8 · S-AIK.6 açık #1 · Y142) — yalnız TAŞIYICI: `deploy/device.env` → launcher → backend.
/// Backend semantiği (`apps/backend/servers/ai_router.py::_kedi_aipro_surus_acik`): yok / boş = KAPALI; yalnız `1|true|yes|on`
/// açar. Varsayılanımız `"0"` — davranış DEĞİŞMEZ (Y142: tezgâhta F6 doğrulanıp sahip onaylayana dek KAPALI); taşıyıcı yokken
/// operatör açsa bile launcher'ın başlattığı backend'e ULAŞMAZDI (ARAŞTIRMA bayrağının aynı kaçış sınıfı). Varsayılanı `"1"`
/// YAPMAYIN. Ortamda tanımlıysa DOKUNULMAZ. Kilit: `device_env_anahtarlari_launcherda_KARSILIGINI_BULUR`.
pub const ENV_KEDI_AIPRO_SURUS: &str = "PEMF_KEDI_AIPRO_SURUS";

/// FANTOM AI PRO KAPALI DÖNGÜ SÜRÜŞÜ (D3 T-f · Y195, GÜVENLİK) — yalnız TAŞIYICI: `deploy/device.env` → launcher → backend. Eskiden fantom
/// sürüşü petri ile ORTAK `PEMF_ARASTIRMA_AIPRO` bayrağına bağlıydı; fantom hattı boş kabinde de tümör bulup "sürülebilir" dediği için
/// AYRI bayrak. Backend semantiği (`ai_router.py::_arastirma_aipro_fantom_acik`): yok / boş = KAPALI; yalnız `1|true|yes|on` açar.
/// Varsayılanımız `"0"` — davranış DEĞİŞMEZ (kapalı); taşıyıcı olmadan operatör açsa bile backend'e ULAŞMAZDI. Varsayılanı `"1"` YAPMAYIN.
/// Ortamda tanımlıysa DOKUNULMAZ. Kilit: `device_env_anahtarlari_launcherda_KARSILIGINI_BULUR`.
pub const ENV_ARASTIRMA_AIPRO_FANTOM: &str = "PEMF_ARASTIRMA_AIPRO_FANTOM";

/// SAKLAMA SÜRELERİ (LN L8 · S-F2-3.2 (a) · A-33 · D2.44): backend'in tek silicisi (`services/headless_db_maintenance`) bu adları
/// okur. Launcher ORTAMDA TANIMLI olanları backend'e AYNEN geçirir; VARSAYILAN YAZMAZ (backend varsayılanları tek kaynak: sensör 90 ·
/// doz 3650 · seans olayı 365 · giden kutusu 30 · PII 365 gün). Boş / geçersiz değer backend'de o adımı KAPATIR ve uyarı yazar
/// (S-F2-1.5) — launcher bu anlamı DEĞİŞTİRMEZ. Eski ad `PEMF_SENSOR_RETAIN_DAYS` da geçer (backend yalnız yeni ad yokken uygular).
pub const ENV_SAKLAMA: [&str; 6] = [
    "PEMF_RETAIN_SENSOR_DAYS",
    "PEMF_RETAIN_DOSE_DAYS",
    "PEMF_RETAIN_EVENT_DAYS",
    "PEMF_RETAIN_OUTBOX_DAYS",
    "PEMF_RETAIN_PII_DAYS",
    "PEMF_SENSOR_RETAIN_DAYS",
];

/// DNS-REBINDING KORUMASI (eksik-taramasi P2, 2026-08-22) — bu sinifin BESINCI ornegi olmasin:
/// `PEMF_ALLOWED_HOSTS` altyapisi backend'de 2026-08-04'ten beri vardi ama launcher gecirmedigi
/// icin siteden kurulan HICBIR klinikte aktif degildi (ENABLE_TUNNEL/STM_PORT/DATA_DIR ile
/// birebir ayni kacis yolu). "auto": IP-literal/localhost/*.local/makine-adi/tunel alanlari
/// serbest, YABANCI alan adlari 400 (rebinding vektoru). Ortamda tanimliysa DOKUNULMAZ
/// (cikis kapisi: `PEMF_ALLOWED_HOSTS=*` korumayi kapatir, `auto,klinik.sirket.com` ek ad verir).
pub const ENV_ALLOWED_HOSTS: &str = "PEMF_ALLOWED_HOSTS";

/// JETON (TOKEN) KAPISI — bu sinifin **YEDINCI** ornegi (2026-09-13).
///
/// `apps/backend/servers/jeton.py` tamamen yazili ve `ai_router`a bagli, ama kapi `PEMF_JETON_ENFORCED`
/// bayragina bakiyor ve launcher o bayragi **HIC gecirmiyordu**. Sonuc: bayrak makinede
/// tanimlansa bile launcher'dan acilan backend onu GORMUYOR → jeton hicbir zaman dusmuyor.
/// ENCRYPT_AT_REST / ENABLE_TUNNEL / STM_PORT / ALLOWED_HOSTS / DATA_DIR ile **birebir ayni**
/// kacis yolu: "backend'de altyapi var, launcher gecirmiyor".
///
/// ⚠️ VARSAYILAN `"0"` — SATIS ACILMADI. Bunu `"1"` YAPMAYIN: acilirsa her AI analizi bakiye
/// ister ve bakiyesi olmayan klinikte analiz DURUR. Kapali iken `jeton.izin()` tam no-op.
///
/// ⚠️ SEANS / ACIL DURDUR / SENSOR IZLEME HICBIR KOSULDA KAPILANMAZ — bu yollar jeton kapisina hic
/// gelmez: `servers/jeton.py::_islem_turu` ai_router disindaki her yolu ve `_SERBEST_AI_UCLARI`ni
/// serbest sayar (D4.11; kapi tests/test_jeton_kapisi_TUM_ROTALARDA_guvenlik_uclari_SERBEST_D411.py);
/// bayragin acilmasi onu DEGISTIRMEZ.
///
/// CIKIS KAPISI: ortamda tanimliysa DOKUNULMAZ → `PEMF_JETON_ENFORCED=1` ile test edilebilir.
pub const ENV_JETON_ENFORCED: &str = "PEMF_JETON_ENFORCED";

/// DUZ-METIN YEDEK (.plain.bak) EMANETI — bu sinifin **SEKIZINCI** ornegi (2026-09-15).
///
/// Goc sirasinda olusan `.plain.bak`, TUM hasta/tedavi PII'sinin duz-metin tam kopyasidir ve
/// SQLCipher'i tamamen baypas eder. Varsayilan GUVENLI-SIL; `=1` ACL-kilitli emanet saklar
/// (ACL uygulanamazsa yine siler — fail-closed).
///
/// ⚠️ NEDEN ACIKCA GECIRILIYOR — "miras alinir" GEREKCESI YETERSIZ. Olculdu:
/// `backend.rs` haritayi `cmd.env(k, v)` ile uygular ve `env_clear()` YOKTUR, yani
/// launcher'in DOGURDUGU backend ortami zaten miras alir. Ama:
///   · SERVIS (NSSM) kurulumu ortami `deploy/device.env`ten yazar, miras ALMAZ;
///   · miras, launcher SURECININ kendi ortamina baglidir — bayrak launcher ACILDIKTAN sonra
///     tanimlanirsa gorunmez (ortam surec baslangicinda dondurulur).
/// Bu depo ayni "gecirilmiyor" sinifina YEDI kez dustu; ortulu bir mekanizmaya guvenmek
/// sekizincisini davet ederdi.
///
/// ⚠️ VARSAYILAN `"0"` = guvenli-sil. `"1"` YAPMAYIN: her klinikte TUM PII'nin duz-metin tam
/// kopyasi diskte kalir (ACL yalniz yerel kullaniciya karsi korur; disk calinmasina/
/// imajlanmasina karsi HICBIR sey yapmaz ve at-rest sifrelemenin tehdit modeli tam odur).
/// Sahip karari 2026-08-08.
///
/// CIKIS KAPISI: ortamda tanimliysa DOKUNULMAZ.
/// Kapi: tests/test_duz_metin_yedek_bayragi_tek_ad.py + bu dosyadaki
/// `device_env_anahtarlari_launcherda_KARSILIGINI_BULUR`.
pub const ENV_KEEP_PLAIN_BACKUP: &str = "PEMF_KEEP_PLAIN_BACKUP";

/// HOTSPOT PROFİL KAPISI (Y234 · S-BE.3, 2026-11-01). Backend açılışta PEMF-Gateway hotspot'unu kurulu profile BAKMADAN
/// açıyordu (`backend_service._start_hotspot_safe`); profil kapısı yalnız keep-alive görevindeydi (`flow::hotspot_gorevi_gerekli`).
/// Yalnız "Evcil Hayvan Sahibi" (`home`) kurulu makine bobin sürmez → AP gereksiz (aynı-WiFi keşfini bozar — bkz. flow'daki not).
///
/// ⚠️ `"0"` YALNIZ profil kaydı DOLU ve hiçbiri terapi profili değilse verilir. Kayıt yok / bozuk / boşsa DEĞİŞKEN VERİLMEZ
/// (backend varsayılanı = bugünkü davranış): klinikte telefon PEMF-Gateway'e bağlanır, okunamayan bir kayıt yüzünden AP'yi
/// kapatmak telefonu cihazdan koparırdı.
///
/// CIKIS KAPISI: ortamda tanimliysa DOKUNULMAZ (değer AYNEN geçirilir — bkz. ENV_KEEP_PLAIN_BACKUP'taki "miras" notu).
pub const ENV_HOTSPOT: &str = "PEMF_HOTSPOT";

/// Y234: backend'e `PEMF_HOTSPOT=0` geçilmeli mi — profil kaydı DOLU ve hiçbiri terapi profili değil (saf → birim-testlenebilir).
pub fn hotspot_kapatilmali(profiller: &[String]) -> bool {
    !profiller.is_empty() && !crate::flow::hotspot_gorevi_gerekli(profiller)
}

/// TIBBİ VERİ KÖKÜ — MAKİNE GENELİ (2026-08-09 denetimi, Tier 1).
///
/// ⚠️ ARIZA: launcher `PEMF_DATA_DIR` VERMİYORDU → backend `%APPDATA%\PEMF_GUI`e düşüyordu,
/// yani hasta/seans/AI verisi WINDOWS KULLANICISINA ÖZELdi. Vardiyalı bir klinikte ikinci
/// hesapla açan veteriner "BOŞ KLİNİK" görüyor: hasta listesi yok, geçmiş yok, AI kaydı yok.
/// Kullanıcı açısından bu VERİ KAYBINDAN ayırt edilemez. (Kurulum kökü de kullanıcı-başına
/// olduğundan ikinci hesap ayrıca 1,3 GB'ı yeniden indiriyor — bu ayrı bir mesele.)
///
/// Servis-tabanlı (Inno) dağıtım bunu ZATEN doğru yapıyordu: `device.env`/`server.env`
/// `PEMF_DATA_DIR=C:\ProgramData\PEMF_System` veriyor. Launcher yolu geride kalmıştı; AYNI
/// yolu kullanıyoruz ki iki dağıtım aynı veriyi görsün.
/// (Sabit `ENV_DATA_DIR` yukarıda tanımlı.)
///
/// Makine-geneli veri kökü adayı (Windows: `%PROGRAMDATA%\PEMF_System`).
pub fn machine_data_dir<F>(getenv: F) -> Option<PathBuf>
where
    F: Fn(&str) -> Option<String>,
{
    if !cfg!(target_os = "windows") {
        // Windows dışında makine-geneli yazılabilir bir yol yönetici ister; kullanıcı-başına
        // kal (bugünkü davranış). Bu platformlarda çoklu-hesap klinik senaryosu da yok.
        return None;
    }
    let pd = getenv("PROGRAMDATA").filter(|v| !v.is_empty())?;
    Some(PathBuf::from(pd).join("PEMF_System"))
}

/// Dizin GERÇEKTEN yazılabilir mi? (yarat + sonda dosyası yaz + sil)
///
/// ⚠️ Bu kontrol ŞART. `C:\ProgramData` altında bir klasörü A kullanıcısı yaratırsa varsayılan
/// ACL'de B kullanıcısı YAZAMAZ. Yazamayan bir yolu `PEMF_DATA_DIR` olarak vermek, backend'in
/// tıbbi kayıt DB'sini açamamasına ve (2026-08-09 kapısı gereği) SEANS BAŞLATAMAMASINA yol
/// açardı — yani bu düzeltme, düzeltmeye çalıştığı şeyden daha ağır bir arıza üretirdi.
pub fn dizin_yazilabilir_mi(dir: &Path) -> bool {
    if std::fs::create_dir_all(dir).is_err() {
        return false;
    }
    // ⚠️ SONDA ADI BENZERSİZ OLMALI. Sabit adla iki eşzamanlı yoklama aynı dosyayı paylaşır:
    // biri yazarken diğeri siler → yanlış "yazılamıyor" sonucu. Bu, `PEMF_DATA_DIR`in sessizce
    // verilmemesine ve kliniğin ikinci kullanıcıda yine "boş klinik" görmesine yol açardı.
    // (Testlerin paralel koşusunda GERÇEKTEN yaşandı; üretimde de iki süreç aynı anda yoklayabilir.)
    use std::sync::atomic::{AtomicU64, Ordering};
    static SAYAC: AtomicU64 = AtomicU64::new(0);
    let sonda = dir.join(format!(
        ".pemf_yazma_denemesi_{}_{}",
        std::process::id(),
        SAYAC.fetch_add(1, Ordering::Relaxed)
    ));
    let ok = std::fs::write(&sonda, b"x").is_ok();
    let _ = std::fs::remove_file(&sonda);
    ok
}

/// Y96 (sahip, LN L8): çok hesaplı kurulumda veri kökünü kullanan hesapların üye olduğu PAYLAŞILAN YEREL grubun SID'i. Kurulum /
/// yönetici ortama yazar; launcher veri kökünü bu grubun ACL'iyle kurar ve backend'e geçirir (`apps/backend/utils/file_acl.py`
/// kilitleri `/inheritance:r` ile kalıtımı kaldırdığı için grubu orada da açıkça verir — o yarı 2-E'de yapıldı).
pub const ENV_DATA_GROUP_SID: &str = "PEMF_DATA_GROUP_SID";

/// `S-1-5-21-<a>-<b>-<c>-<RID>` (bilgisayar / etki alanı tarafından OLUŞTURULMUŞ hesap biçimi) — backend `_OZEL_GRUP_SID_RE` ile AYNI.
/// Users (S-1-5-32-545), Authenticated Users (S-1-5-11), Everyone (S-1-1-0), Interactive (S-1-5-4) bu biçimde DEĞİL → reddedilir.
pub fn ozel_grup_sid_bicimi_mi(sid: &str) -> bool {
    let p: Vec<&str> = sid.split('-').collect();
    p.len() == 8
        && p[..4] == ["S", "1", "5", "21"]
        && p[4..].iter().all(|x| !x.is_empty() && x.len() <= 10 && x.bytes().all(|b| b.is_ascii_digit()))
}

/// LookupAccountSid sonucu YEREL GRUP mu: tür `SidTypeAlias` (4) VE etki alanı = bu bilgisayarın adı (saf — testli).
pub fn yerel_grup_karari(tur: i32, alan: &str, bilgisayar: &str) -> bool {
    tur == 4 && !alan.is_empty() && alan.eq_ignore_ascii_case(bilgisayar)
}

/// `sid` bu makinede çözülen bir YEREL GRUP mu? (backend `_bu_makinenin_yerel_grubu_mu` ikizi) Hata / çözülemez → `false`.
#[cfg(windows)]
fn bu_makinenin_yerel_grubu_mu(sid: &str) -> bool {
    hesap_turu_alani_bilgisayar(sid).is_some_and(|(tur, alan, bilgisayar)| yerel_grup_karari(tur, &alan, &bilgisayar))
}

/// LookupAccountSidW: `(SID_NAME_USE, etki alanı, bu bilgisayarın adı)`; çözülemez → `None`.
#[cfg(windows)]
fn hesap_turu_alani_bilgisayar(sid: &str) -> Option<(i32, String, String)> {
    use windows_sys::Win32::Foundation::LocalFree;
    use windows_sys::Win32::Security::Authorization::ConvertStringSidToSidW;
    use windows_sys::Win32::Security::LookupAccountSidW;
    use windows_sys::Win32::System::WindowsProgramming::GetComputerNameW;
    let genis: Vec<u16> = sid.encode_utf16().chain(std::iter::once(0)).collect();
    // SAFETY: tamponlar boyutlarıyla verilir; ConvertStringSidToSidW'nin ayırdığı SID LocalFree ile bırakılır.
    unsafe {
        let mut bilgisayar = [0u16; 64];
        let mut bboy = bilgisayar.len() as u32;
        if GetComputerNameW(bilgisayar.as_mut_ptr(), &mut bboy) == 0 {
            return None;
        }
        let mut psid: windows_sys::Win32::Security::PSID = std::ptr::null_mut();
        if ConvertStringSidToSidW(genis.as_ptr(), &mut psid) == 0 || psid.is_null() {
            return None;
        }
        let (mut ad, mut alan) = ([0u16; 256], [0u16; 256]);
        let (mut aboy, mut alboy) = (ad.len() as u32, alan.len() as u32);
        let mut tur: i32 = 0;
        let ok = LookupAccountSidW(
            std::ptr::null(),
            psid,
            ad.as_mut_ptr(),
            &mut aboy,
            alan.as_mut_ptr(),
            &mut alboy,
            &mut tur,
        ) != 0;
        LocalFree(psid as _);
        ok.then(|| {
            (
                tur,
                String::from_utf16_lossy(&alan[..alboy as usize]),
                String::from_utf16_lossy(&bilgisayar[..bboy as usize]),
            )
        })
    }
}

#[cfg(not(windows))]
fn bu_makinenin_yerel_grubu_mu(_sid: &str) -> bool {
    false
}

/// Y182 (D3 T-g): yerel hesap / grup ADINDAN SID (LookupAccountNameW — salt-okur). Bulunamaz → `None`.
#[cfg(windows)]
pub fn grup_adindan_sid(ad: &str) -> Option<String> {
    use windows_sys::Win32::Foundation::LocalFree;
    use windows_sys::Win32::Security::Authorization::ConvertSidToStringSidW;
    use windows_sys::Win32::Security::LookupAccountNameW;
    let genis: Vec<u16> = ad.encode_utf16().chain(std::iter::once(0)).collect();
    // SAFETY: tamponlar boyutlarıyla verilir (SID en çok 68 bayt); ConvertSidToStringSidW'nin ayırdığı dize LocalFree ile bırakılır.
    unsafe {
        let mut sid = [0u64; 16];
        let mut sboy = std::mem::size_of_val(&sid) as u32;
        let mut alan = [0u16; 256];
        let mut alboy = alan.len() as u32;
        let mut tur: i32 = 0;
        if LookupAccountNameW(
            std::ptr::null(),
            genis.as_ptr(),
            sid.as_mut_ptr().cast(),
            &mut sboy,
            alan.as_mut_ptr(),
            &mut alboy,
            &mut tur,
        ) == 0
        {
            return None;
        }
        let mut dize: windows_sys::core::PWSTR = std::ptr::null_mut();
        if ConvertSidToStringSidW(sid.as_mut_ptr().cast(), &mut dize) == 0 || dize.is_null() {
            return None;
        }
        let mut n = 0usize;
        while *dize.add(n) != 0 {
            n += 1;
        }
        let s = String::from_utf16_lossy(std::slice::from_raw_parts(dize, n));
        LocalFree(dize as _);
        Some(s)
    }
}

#[cfg(not(windows))]
pub fn grup_adindan_sid(_ad: &str) -> Option<String> {
    None
}

/// Y96: geçerli paylaşılan grup — `PEMF_DATA_GROUP_SID` biçimi tutar VE bu makinenin yerel grubu. Değilse `None` (Users / etki alanı
/// grubu / kullanıcı hesabı / silinmiş grup REDDEDİLİR — backend ile aynı kural; çözülemeyen SID icacls'ı da düşürürdü).
/// Y182 (D3 T-g): değişken YOKSA launcher'ın tek seferlik yönetici adımıyla kurduğu grup ADIYLA bulunur (`paylasim::GRUP_ADI`;
/// yerel grubu yalnız yönetici kurabilir). Değişken VARSA yalnız o geçerlidir — geçersizse sessiz yedek YOK.
pub fn paylasilan_grup_sid<F>(getenv: F) -> Option<String>
where
    F: Fn(&str) -> Option<String>,
{
    paylasilan_grup_sid_karari(getenv, || grup_adindan_sid(crate::paylasim::GRUP_ADI), bu_makinenin_yerel_grubu_mu)
}

/// `paylasilan_grup_sid`'in saf kararı (testli): ad araması ve yerel-grup denetimi dışarıdan verilir.
pub fn paylasilan_grup_sid_karari<F, A, Y>(getenv: F, adindan: A, yerel_grup_mu: Y) -> Option<String>
where
    F: Fn(&str) -> Option<String>,
    A: FnOnce() -> Option<String>,
    Y: Fn(&str) -> bool,
{
    let s = match getenv(ENV_DATA_GROUP_SID).map(|v| v.trim().to_string()).filter(|v| !v.is_empty()) {
        Some(s) => s,
        None => adindan()?,
    };
    (ozel_grup_sid_bicimi_mi(&s) && yerel_grup_mu(&s)).then_some(s)
}

/// Yeni yaratılan makine-geneli veri köküne verilecek ACL (saf — testli). Y96 (sahip): yalnız PAYLAŞILAN YEREL grup `Değiştir`
/// alır; yerel `Users` (S-1-5-32-545) DIŞARIDA — eskiden bu makinedeki HER hesap hasta veri köküne yazabiliyordu. Grup yoksa
/// (tek hesaplı kurulum) ek hak VERİLMEZ: klasörü yaratan hesap sahip olarak (CREATOR OWNER) tam denetimdedir.
pub fn veri_koku_acl_argumanlari(grup: Option<&str>) -> Option<Vec<String>> {
    grup.map(|g| ["/grant".to_string(), format!("*{g}:(OI)(CI)M"), "/T".into(), "/C".into(), "/Q".into()].to_vec())
}

/// Y202 (S-D3I.4, sahip): yeni makine kökünde grup hakkının TEK hedefi — hasta veri dizini `<kök>\PEMF_GUI` (T-g
/// `paylasim::kurma_betigi` ile aynı hedef, D3I-A2.9). Kökün kendisi ve kardeşleri (mosquitto, logs, kimlik dosyaları) gruba AÇILMAZ;
/// eskiden grup `M /T` kökün TAMAMINA veriliyordu.
pub fn veri_koku_acl_hedefi(kok: &Path) -> PathBuf {
    kok.join("PEMF_GUI")
}

/// Y202: dosya sistemi girdisi bir BAĞ mı — Windows'ta HER yeniden ayrıştırma noktası (sembolik bağ, bağlantı noktası / junction ve
/// öbürleri; T-g `ReparsePoint` ile aynı), başka platformda sembolik bağ.
fn bag_ozniteligi_mi(m: &std::fs::Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        m.file_attributes() & windows_sys::Win32::Storage::FileSystem::FILE_ATTRIBUTE_REPARSE_POINT != 0
    }
    #[cfg(not(windows))]
    {
        m.file_type().is_symlink()
    }
}

/// Y202: dosyanın birden çok adı (sabit bağ) var mı; okunamazsa VAR sayılır (hak yazılmaz).
#[cfg(windows)]
fn birden_cok_adli_mi(yol: &Path) -> bool {
    use std::os::windows::fs::OpenOptionsExt;
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Storage::FileSystem::{
        GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION, FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OPEN_REPARSE_POINT,
    };
    // FILE_READ_ATTRIBUTES yeter; bağı İZLEMEDEN açılır.
    let Ok(f) = std::fs::OpenOptions::new()
        .access_mode(0x80)
        .custom_flags(FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)
        .open(yol)
    else {
        return true;
    };
    // SAFETY: tutamaç `f` yaşadıkça geçerli; yapı tam boyutuyla verilir.
    let mut bi: BY_HANDLE_FILE_INFORMATION = unsafe { std::mem::zeroed() };
    if unsafe { GetFileInformationByHandle(f.as_raw_handle() as _, &mut bi) } == 0 {
        return true;
    }
    bi.nNumberOfLinks > 1
}

#[cfg(not(windows))]
fn birden_cok_adli_mi(yol: &Path) -> bool {
    use std::os::unix::fs::MetadataExt;
    std::fs::symlink_metadata(yol).map(|m| m.nlink() > 1).unwrap_or(true)
}

/// Y202: ağaçta (kendisi dahil) bağ var mı — T-g `paylasim::kurma_betigi` bağ denetiminin (`ReparsePoint` / `LinkType`) karşılığı:
/// `icacls /T` bağın HEDEFİNE (ör. hesabın başka bir klasörüne) grup hakkı yazardı. ProgramData mirası (`Users: (CI)` yaratma) başka
/// bir yerel hesaba yeni klasörün İÇİNE bağ koydurabilir. Okunamayan girdi de bağ SAYILIR (hak yazılmaz).
fn agacta_bag_var(dir: &Path) -> bool {
    let mut yigin = vec![dir.to_path_buf()];
    while let Some(p) = yigin.pop() {
        let Ok(m) = std::fs::symlink_metadata(&p) else { return true };
        if bag_ozniteligi_mi(&m) {
            return true;
        }
        if !m.is_dir() {
            if birden_cok_adli_mi(&p) {
                return true;
            }
            continue;
        }
        let Ok(girdiler) = std::fs::read_dir(&p) else { return true };
        for e in girdiler {
            match e {
                Ok(e) => yigin.push(e.path()),
                Err(_) => return true,
            }
        }
    }
    false
}

/// Y96 · Y202: yeni makine kökü için `icacls` argümanlarının TAMAMI (hedef dahil — testli). Hedef `veri_koku_acl_hedefi` (`PEMF_GUI`);
/// `/T` yalnız onun ağacına. Grup yoksa, kökün kendisi bağsa ya da hedef ağacında bağ varsa `None` (hak VERİLMEZ).
pub fn veri_koku_acl_komutu(kok: &Path, grup: Option<&str>) -> Option<Vec<std::ffi::OsString>> {
    let arg = veri_koku_acl_argumanlari(grup)?;
    let hedef = veri_koku_acl_hedefi(kok);
    let kok_bag = std::fs::symlink_metadata(kok).map(|m| bag_ozniteligi_mi(&m)).unwrap_or(true);
    if kok_bag || agacta_bag_var(&hedef) {
        return None;
    }
    Some(std::iter::once(hedef.into_os_string()).chain(arg.into_iter().map(Into::into)).collect())
}

/// `acl_ver`'in gövdesi; komut koşucusu ENJEKTE (testler gerçek `icacls` ÇALIŞTIRMAZ). Grup yoksa HİÇBİR şey yapılmaz (tek hesaplı
/// kurulum — bugünkü gibi, `PEMF_GUI`'yi backend kurar); grup varsa hak yazılabilsin diye `PEMF_GUI` yaratılır (zaten varsa bağ
/// denetimi karar verir).
#[cfg_attr(not(windows), allow(dead_code))]
fn acl_ver_ile<K: FnOnce(Vec<std::ffi::OsString>)>(kok: &Path, grup: Option<&str>, kos: K) {
    if grup.is_none() {
        return;
    }
    let _ = std::fs::create_dir(veri_koku_acl_hedefi(kok));
    if let Some(arg) = veri_koku_acl_komutu(kok, grup) {
        kos(arg);
    }
}

/// Yeni yaratılan makine-geneli kökte paylaşılan gruba hak ver (`veri_koku_acl_komutu` — Y202: yalnız `<kök>\PEMF_GUI`).
///
/// Klasörü YARATAN kullanıcı sahibidir ve sahip, yönetici olmasa da DACL'i değiştirebilir →
/// UAC gerekmez. ⚠️ YLI-A3.1 (ÖLÇÜLDÜ, 2026-10-22): grup verilmese de `C:\ProgramData` mirası (`Users: Write (CI)`) ikinci Windows
/// hesabına köke dosya yazdırır → `dizin_yazilabilir_mi(kök)` onu AYIRT ETMEZ; o hesap makine kökünü alır ama backend asıl veri dizinini
/// (`<kök>\PEMF_GUI`) `file_acl.lock_down_dir` ile ilk hesaba kilitlediği için hasta verisine ERİŞEMEZ (DB açılmaz — görünür arıza,
/// sessiz "boş klinik" değil). Çok hesaplı klinikte paylaşılan grup ZORUNLU (Y96); ikinci hesap için sahip kararı Y182 (S-YLI.1):
/// launcher erişimsizliği görür ve tek seferlik yönetici adımıyla grubu kurar (`paylasim.rs`).
/// Başarısız olursa sessizce geçilir: `dizin_yazilabilir_mi` kapısı zaten koruyor.
#[cfg(windows)]
fn acl_ver(dir: &Path, grup: Option<&str>) {
    // Konsol penceresi AÇMADAN (bkz. platform::gizli_komut): kurulum/güncelleme akışında koşar;
    // çıplak `Command` kullanıcıya siyah pencere gösteriyordu.
    acl_ver_ile(dir, grup, |arg| {
        let _ = crate::platform::gizli_komut("icacls").args(arg).output();
    });
}

#[cfg(not(windows))]
fn acl_ver(_dir: &Path, _grup: Option<&str>) {}

/// Backend'e verilecek veri kökü: makine-geneli YAZILABİLİRSE onu, değilse `None`
/// (kullanıcı-başına eski davranışa düş — kurulumu kırmaktansa bugünkü hâlde kal).
pub fn cozulmus_veri_dizini<F>(getenv: F) -> Option<PathBuf>
where
    F: Fn(&str) -> Option<String>,
{
    let dir = machine_data_dir(&getenv)?;
    let yeni = !dir.exists();
    if !dizin_yazilabilir_mi(&dir) {
        return None;
    }
    if yeni {
        acl_ver(&dir, paylasilan_grup_sid(&getenv).as_deref());
        // ACL sonrası tekrar doğrula — icacls başarısızsa yol yine de kullanılabilir olmalı.
        if !dizin_yazilabilir_mi(&dir) {
            return None;
        }
    }
    Some(dir)
}

// ══════════════════════════════════════════════════════════════════════════════════════════
// OFF-SITE YEDEK HEDEFİ (2026-08-09 denetimi, Tier 1)
//
// ARIZA: yedekler `<veri-dizini>/backups` altına, yani HASTA VERİSİYLE AYNI DİSKE alınıyordu.
// Disk/anakart arızasında ya da fidye yazılımında veri VE yedek birlikte gider — yedek sistemi
// yalnız mantıksal bozulmaya karşı koruyordu, fiziksel kayba karşı HİÇ.
//
// Backend `PEMF_BACKUP_DIR` desteğini ZATEN taşıyordu (`_copy_offsite`) ama hiçbir yerde
// ayarlanmıyordu → özellik sahada hiç çalışmadı. Launcher artık operatörün seçtiği hedefi
// saklıyor ve backend'e geçiriyor.
//
// ⚠️ AYNI BİRİM KABUL EDİLMEZ: hedefi C: üzerinde seçmek, düzeltmenin amacını tamamen ortadan
// kaldırır ve operatöre yanlış güvence verir. Kontrol `yedek_hedefi_gecerli_mi`de.
// ══════════════════════════════════════════════════════════════════════════════════════════

/// Backend'e verilen off-site yedek hedefi (bkz. apps/backend/services/headless_db_maintenance._copy_offsite).
pub const ENV_BACKUP_DIR: &str = "PEMF_BACKUP_DIR";

/// Operatörün seçtiği hedefin saklandığı dosya.
pub fn backup_dir_kaydi(install_root: &Path) -> PathBuf {
    install_root.join("backup_dir.txt")
}

/// Kayıtlı hedefi oku (yoksa/boşsa None).
pub fn backup_dir_oku(install_root: &Path) -> Option<PathBuf> {
    let s = std::fs::read_to_string(backup_dir_kaydi(install_root)).ok()?;
    let t = s.trim();
    (!t.is_empty()).then(|| PathBuf::from(t))
}

/// Hedefi kaydet ("" → kaydı sil).
pub fn backup_dir_yaz(install_root: &Path, dir: &str) -> std::io::Result<()> {
    let yol = backup_dir_kaydi(install_root);
    if dir.trim().is_empty() {
        let _ = std::fs::remove_file(&yol);
        return Ok(());
    }
    std::fs::create_dir_all(install_root)?;
    std::fs::write(yol, dir.trim())
}

/// İki yol AYNI birimde mi? (Windows: sürücü harfi; diğer: bilinemez → `None`)
pub fn ayni_birim(a: &Path, b: &Path) -> Option<bool> {
    if !cfg!(target_os = "windows") {
        return None;
    }
    let harf = |p: &Path| -> Option<char> {
        p.to_string_lossy().chars().next().map(|c| c.to_ascii_uppercase())
    };
    Some(harf(a)? == harf(b)?)
}

/// YLI-A3 (S-E2I.4): UNC ana bilgisayar adı BU makine mi — `localhost` / bilgisayar adı (sondaki nokta yok sayılır), 127.0.0.0/8
/// (`127.0.0.2` dahil) ve Windows çözümleyicisinin kabul ettiği `127.1` / `127.0.1` kısaltmaları, `::1` / `[::1]` (saf).
fn yerel_host_mu(host: &str, bilgisayar: &str) -> bool {
    let h = host.trim_end_matches('.').trim_start_matches('[').trim_end_matches(']');
    if h.eq_ignore_ascii_case("localhost") || (!bilgisayar.is_empty() && h.eq_ignore_ascii_case(bilgisayar)) {
        return true;
    }
    if let Ok(ip) = h.parse::<std::net::IpAddr>() {
        return ip.is_loopback();
    }
    let p: Vec<&str> = h.split('.').collect();
    (2..=3).contains(&p.len()) && p[0] == "127" && p.iter().all(|x| !x.is_empty() && x.bytes().all(|b| b.is_ascii_digit()))
}

/// LN L8 · S-E2I.4: yolun YEREL karşılığı (saf). `\\?\C:\x` / `\\.\C:\x` → `C:\x`; `\\?\UNC\<h>\C$\x` ve `\\<h>\C$\x` (h = localhost ·
/// 127.0.0.1 · ::1 · bu bilgisayarın adı) → `C:\x`; başka biçim (gerçek ağ paylaşımı) aynen. Eskiden `ayni_birim` yalnız İLK
/// karaktere baktığı için `\\?\C:\…` ve `\\localhost\C$\…` "başka sürücü" sayılıyor, hasta verisiyle AYNI diske yedek kabul ediliyordu.
pub fn yerel_yol(yol: &str, bilgisayar: &str) -> String {
    let s = yol.replace('/', "\\");
    let unc = |r: &str| -> Option<String> {
        let mut p = r.splitn(3, '\\');
        let (host, pay, kalan) = (p.next()?, p.next()?, p.next().unwrap_or(""));
        let yerel = yerel_host_mu(host, bilgisayar);
        let harf = pay.strip_suffix('$').filter(|h| h.len() == 1 && h.chars().all(|c| c.is_ascii_alphabetic()))?;
        yerel.then(|| format!("{}:\\{kalan}", harf.to_ascii_uppercase()))
    };
    if let Some(r) = s.strip_prefix("\\\\?\\UNC\\") {
        return unc(r).unwrap_or(s);
    }
    if let Some(r) = s.strip_prefix("\\\\?\\").or_else(|| s.strip_prefix("\\\\.\\")) {
        return r.to_string();
    }
    if let Some(r) = s.strip_prefix("\\\\") {
        return unc(r).unwrap_or(s);
    }
    s
}

/// LN L8 · S-E2I.4: kaldırma / KVKK tam temizliğinin sildiği PEMF kökleri — yedek hedefi bunların İÇİNDE olamaz (yedek de silinirdi;
/// silme kapsamı DEĞİŞMEDİ, kural hedef seçiminde). Kurulum kökü · makine kökü `%PROGRAMDATA%\PEMF_System` · kullanıcı veri kökü
/// `%APPDATA%\PEMF_GUI` · `%LOCALAPPDATA%\PEMF_System` · eski paylaşılan `%PROGRAMDATA%\PEMF_GUI` (`scripts/pemf_footprint.ps1`).
pub fn pemf_kokleri<F>(getenv: F, home: &Path, install_root: &Path) -> Vec<PathBuf>
where
    F: Fn(&str) -> Option<String>,
{
    let mut v = vec![install_root.to_path_buf(), app_data_dir_with(&getenv, home)];
    if let Some(pd) = getenv("PROGRAMDATA").filter(|s| !s.is_empty()) {
        v.push(PathBuf::from(&pd).join("PEMF_System"));
        v.push(PathBuf::from(&pd).join("PEMF_GUI"));
    }
    if let Some(la) = getenv("LOCALAPPDATA").filter(|s| !s.is_empty()) {
        v.push(PathBuf::from(la).join("PEMF_System"));
    }
    v
}

/// YLI-A3 (S-E2I.4): VAR OLAN yolun gerçek biçimi (junction / sembolik bağ / 8.3 kısa ad / `subst` çözülmüş — `canonicalize`); yoksa
/// olduğu gibi. Kök kuralı metinle karşılaştırdığı için PEMF köküne bağlanan bir junction'ı göremiyordu.
fn gercek_yol(p: &Path) -> String {
    std::fs::canonicalize(p).map(|c| c.to_string_lossy().into_owned()).unwrap_or_else(|_| p.to_string_lossy().into_owned())
}

/// YLI-A3 (S-E2I.4): iki VAR OLAN dizin aynı birimde mi — birim seri numarasıyla (bu makinenin normal ağ paylaşımı `\\<pc>\Yedek`,
/// eşlenmiş sürücü, `subst` dahil; ağ paylaşımında sunucunun birimi okunur). Biri açılamazsa `None` (karar sürücü harfinde kalır).
#[cfg(windows)]
pub fn ayni_birim_seri(a: &Path, b: &Path) -> Option<bool> {
    fn seri(p: &Path) -> Option<u32> {
        use std::os::windows::fs::OpenOptionsExt;
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::Storage::FileSystem::{GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION, FILE_FLAG_BACKUP_SEMANTICS};
        // FILE_READ_ATTRIBUTES yeter; dizin tutamacı için BACKUP_SEMANTICS.
        let f = std::fs::OpenOptions::new().access_mode(0x80).custom_flags(FILE_FLAG_BACKUP_SEMANTICS).open(p).ok()?;
        // SAFETY: tutamaç `f` yaşadıkça geçerli; yapı tam boyutuyla verilir.
        let mut bi: BY_HANDLE_FILE_INFORMATION = unsafe { std::mem::zeroed() };
        (unsafe { GetFileInformationByHandle(f.as_raw_handle() as _, &mut bi) } != 0).then_some(bi.dwVolumeSerialNumber)
    }
    Some(seri(a)? == seri(b)?)
}

#[cfg(not(windows))]
pub fn ayni_birim_seri(_a: &Path, _b: &Path) -> Option<bool> {
    None
}

/// Seçilen hedef off-site yedek için uygun mu? `Ok(())` ya da kullanıcıya gösterilecek sebep. Yollar önce YEREL karşılığına
/// çevrilir (`yerel_yol` — `\\?\` / `\\localhost\C$` atlatması); hedef bir PEMF kökünün içinde ya da kökün kendisiyse RED
/// (S-E2I.4; yazılabilirlik sondası o klasöre dosya yazmadan ÖNCE).
pub fn yedek_hedefi_gecerli_mi(hedef: &Path, veri_dizini: &Path, pemf_kokleri: &[PathBuf], bilgisayar: &str) -> Result<(), String> {
    let h = yerel_yol(&gercek_yol(hedef), bilgisayar);
    let ic_mi = |k: &Path| {
        let k = yerel_yol(&gercek_yol(k), bilgisayar);
        let k = k.trim_end_matches('\\');
        h.trim_end_matches('\\').eq_ignore_ascii_case(k) || crate::backend::kok_altinda_mi(&h, Path::new(k))
    };
    if pemf_kokleri.iter().chain(std::iter::once(&veri_dizini.to_path_buf())).any(|k| ic_mi(k)) {
        return Err(crate::dil::t("rust.yedek.pemfKokuAltinda"));
    }
    if !dizin_yazilabilir_mi(hedef) {
        return Err(crate::dil::t("rust.yedek.yazilamiyor"));
    }
    let v = yerel_yol(&gercek_yol(veri_dizini), bilgisayar);
    if ayni_birim(Path::new(&h), Path::new(&v)) == Some(true) || ayni_birim_seri(hedef, veri_dizini) == Some(true) {
        return Err(crate::dil::t("rust.yedek.ayniSurucu"));
    }
    Ok(())
}

/// FİLO ENVANTERİ (2026-08-09 denetimi, Tier 2) — geri çağırma yapılabilsin diye.
///
/// ⚠️ Bir bobin-güvenliği hatası bulunduğunda "hangi klinik hangi sürümde?" sorusunun cevabı
/// YOKTU. Cihaz kaydı 60 sn'de bir heartbeat gönderiyor ama içinde SÜRÜM BİLGİSİ hiç yok;
/// `rollout: 0` yalnız YENİ kurulumları durdurur, sahadaki mevcut cihazlara dokunmaz.
/// Backend bu değişkenleri bulut kaydına yazar (bkz. apps/backend/servers/sync_worker.py).
pub const ENV_LAUNCHER_VERSION: &str = "PEMF_LAUNCHER_VERSION";
/// Kurulu app katmanının sha'sı — hangi build'in sahada olduğunu KESİN belirler.
pub const ENV_BASE_SHA: &str = "PEMF_BASE_SHA";

/// Varsayılan backend portu (`backend_service.py` ile aynı).
pub const DEFAULT_PORT: u16 = 8000;

/// Profil paketleri `ai_models/...` önekiyle açıldığı için model kökü budur.
/// (Doğrulandı: vet.zip → `ai_models/ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx`)
pub fn models_dir(install_root: &Path) -> PathBuf {
    install_root.join("ai_models")
}

/// Base runtime paketinin açıldığı yer (`PEMF_Backend/` bu dizinin altına açılır).
pub fn runtime_dir(install_root: &Path) -> PathBuf {
    install_root.join("runtime")
}

// ── ATOMİK KURULUM DİZİNLERİ (2026-08-08) ─────────────────────────────────────────────────────
// Eskiden güncelleme `runtime/`'ı SİLİP yerine açıyordu: açma yarıda kalırsa (elektrik, disk
// dolu, iptal) klinikte HİÇ runtime kalmıyordu ve 1,2 GB baştan inmesi gerekiyordu. Ayrıca yeni
// sürüm açılıyor ama ÇALIŞMIYORSA geri dönüş yolu yoktu.
// Yeni akış: `runtime.new`'e kur → takas → backend'i başlat (sağlık kapısı) → başarılıysa
// `runtime.old` sil, başarısızsa geri al.

// ── KURULUM KİLİDİ (eşzamanlı client) ────────────────────────────────────────────────────────
//
// ⚠️ ARIZA (2026-08-11, "kurulum/güncelleme esnasında kapanma" incelemesi): client'ın TEK-ÖRNEK
// koruması YOK. Kullanıcı simgeye iki kez tıklarsa (ya da biri açıkken kısayoldan tekrar açarsa)
// İKİ client aynı anda çalışır ve ikisi de:
//   * AYNI `runtime.new` dizinine paket açar → birbirinin dosyalarını ezer, ağaç bozulur;
//   * kurulum öncesi `taskkill /IM PEMF_Backend.exe` çalıştırır → DİĞERİNİN backend'ini,
//     yani muhtemelen SÜREN BİR SEANSI öldürür (bobinler E-stop ile güvenle durur ama seans gider);
//   * takası aynı anda yapar → `runtime`/`runtime.old` yarış hâlinde.
//
// ÇÖZÜM: işletim sisteminin DOSYA KİLİDİ. Kilit dosyası süreç boyunca AÇIK tutulur ve
// paylaşımsız (`share_mode(0)`) açılır; ikinci süreç açamaz. Süreç ölürse Windows tutamağı
// KENDİ kapatır → **bayat kilit imkânsız**. (PID yazıp canlılık sorgulamak, çöken kurulumdan
// sonra kliniği kalıcı kilitli bırakırdı.)

/// Tutulduğu sürece başka bir client kurulum/onarım/kaldırma yapamaz. `Drop` ile bırakılır.
#[derive(Debug)]
pub struct KurulumKilidi {
    _dosya: std::fs::File,
}

/// Kilit dosyasının yolu — kurulum kökünün **DIŞINDA**, geçici dizinde.
///
/// ⚠️ KÖKÜN İÇİNDE OLAMAZ. `remove_install` bütün kökü `remove_dir_all` ile siler; Windows
/// AÇIK tutamağı olan bir dosyayı silmeye izin vermez → kaldırma başarısız olur ve kullanıcıya
/// yarım silinmiş bir kurulum kalır. (İlk yazımda kilit kökün içindeydi; bu kusur kaldırma
/// akışı gözden geçirilirken yakalandı.)
///
/// Ad, kurulum kökünden TÜRETİLİR: farklı kökler (ör. taşınabilir kurulum) birbirini kilitlemez.
fn kilit_yolu(install_root: &Path) -> PathBuf {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325; // FNV-1a
    for b in install_root.to_string_lossy().to_lowercase().bytes() {
        h ^= b as u64;
        h = h.wrapping_mul(0x1000_0000_01b3);
    }
    std::env::temp_dir().join(format!("pemf-kurulum-{h:016x}.lock"))
}

/// Kurulum kilidini AL. Başkası tutuyorsa `Err(mesaj)` — çağıran kullanıcıya göstermeli.
pub fn kurulum_kilidi_al(install_root: &Path) -> Result<KurulumKilidi, String> {
    let _ = std::fs::create_dir_all(install_root);
    let yol = kilit_yolu(install_root);
    let mut secenek = std::fs::OpenOptions::new();
    secenek.create(true).write(true).truncate(false);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        secenek.share_mode(0); // hiç paylaşma → ikinci açış "sharing violation"
    }
    match secenek.open(&yol) {
        Ok(f) => Ok(KurulumKilidi { _dosya: f }),
        Err(e) => Err(crate::dil::t_ile("rust.kurulum.baskaPencere", &[("hata", &(e).to_string())])),
    }
}

// ── DENETİM MASASI BOYUTU ────────────────────────────────────────────────────────────────────
//
// ⚠️ ARIZA (2026-08-11, sahip bildirimi): "Denetim Masası'nda uygulamanın boyutu hep 11 MB
// görünüyor, profil kurulumlarından sonra bile."
//
// SEBEP: NSIS `EstimatedSize`i KURULUM ANINDA `$INSTDIR`den hesaplar. O anda dizinde yalnız
// launcher vardır (~11 MB); çalışma zamanı (~2 GB) ve profil modelleri (0,3-1,6 GB) SONRADAN
// client tarafından indirilir. Kayıt bir daha hiç güncellenmez → kullanıcı diskte yer ararken
// gigabaytlık bir uygulamayı 11 MB sanır ve yanlış karar verir.
//
// ÇÖZÜM: kurulum/onarım/güncelleme bitince gerçek boyutu yaz. Kayıt per-user kurulumda
// HKCU'dadır → YÖNETİCİ GEREKMEZ.

/// Kaldırma kaydının yolu (NSIS `UNINSTKEY` ile AYNI: ürün ADIna göre).
const KALDIRMA_ANAHTARI: &str = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PEMF Vet Client";

/// Kurulum kökünün diskte kapladığı toplam boyut (bayt).
///
/// Önbellek de DAHİLDİR: indirilen paketler gerçekten yer kaplar ve kaldırma onları da siler,
/// yani "bu uygulamayı kaldırırsam ne kadar yer açılır" sorusunun doğru cevabı budur.
pub fn kurulum_boyutu(install_root: &Path) -> u64 {
    fn yur(d: &Path, toplam: &mut u64, derinlik: u32) {
        if derinlik > 24 {
            return; // savunma: döngüsel junction'da sonsuza gitme
        }
        let Ok(girdiler) = std::fs::read_dir(d) else { return };
        for e in girdiler.flatten() {
            let Ok(t) = e.file_type() else { continue };
            if t.is_symlink() {
                continue; // junction/symlink İZLEME — başka bir birimi saymayalım
            }
            if t.is_dir() {
                yur(&e.path(), toplam, derinlik + 1);
            } else if let Ok(m) = e.metadata() {
                *toplam = toplam.saturating_add(m.len());
            }
        }
    }
    let mut t = 0u64;
    yur(install_root, &mut t, 0);
    t
}

/// Denetim Masası'ndaki boyutu GERÇEK kullanımla güncelle. Best-effort: başarısızlık sessizdir
/// (kozmetik bir alandır; kurulumu düşürmemeli).
///
/// Döner: kayıt yazmaya GİRİŞİLDİ mi. (Yazmanın kendisi best-effort'tur; dönüş değeri
/// "boş kökte dokunulmadı" değişmezini TEST EDİLEBİLİR kılmak için var — dönüş olmadan
/// test yalnız çökmediğini görebiliyordu, bu da yanlış güvenceydi.)
/// D5.41 (YLI-A3.7): kayda yazılacak değer (KB, u32 sınırında); boş / okunamayan kök → `None` (saf — testli).
pub fn boyut_kaydi_degeri(install_root: &Path) -> Option<u64> {
    let kb = kurulum_boyutu(install_root) / 1024;
    (kb > 0).then(|| kb.min(u64::from(u32::MAX)))
}

#[cfg(windows)]
pub fn boyut_kaydini_guncelle(install_root: &Path) -> bool {
    let Some(kb) = boyut_kaydi_degeri(install_root) else {
        return false; // kök boş/okunamadı → yanlış "0 MB" yazmaktansa dokunma
    };
    // D5.41 (YLI-A3.7): HKCU `…\Uninstall\PEMF Vet Client` GERÇEK kurulum kökünü anlatır (`InstallLocation`). Başka bir kökün
    // (test / geçici dizin) boyutu oraya yazılmaz — `cargo test` sahte `reg.exe`siz koşunca geliştiricinin / kliniğin GERÇEK kaydını
    // eziyordu (13 çağrı / koşu). Ev dizini launcher'ın `home_dir()` kuralıyla (Windows: USERPROFILE önce; BOŞ değer atlanır).
    let al = |k: &str| std::env::var_os(k).filter(|v| !v.is_empty());
    let ev = al("USERPROFILE").or_else(|| al("HOME")).map(PathBuf::from);
    if ev.map(|h| default_install_root(&h)).as_deref() != Some(install_root) {
        return false;
    }
    // `reg.exe` kullanılır: yeni bağımlılık yok. Kayıt per-user kurulumda HKCU'dadır; makine
    // geneli kurulum (HKLM) yönetici ister ve sessizce başarısız olur — kabul.
    let _ = crate::platform::gizli_komut("reg")
        .args([
            "add",
            &format!(r"HKCU\{KALDIRMA_ANAHTARI}"),
            "/v",
            "EstimatedSize",
            "/t",
            "REG_DWORD",
            "/d",
            &kb.to_string(),
            "/f",
        ])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status();
    true
}

#[cfg(not(windows))]
pub fn boyut_kaydini_guncelle(_install_root: &Path) -> bool {
    false
}

/// Yeni sürümün hazırlandığı yer (takas edilene kadar çalışan kuruluma DOKUNULMAZ).
pub fn runtime_new_dir(install_root: &Path) -> PathBuf {
    install_root.join("runtime.new")
}

/// Takas sonrası eski sürüm burada bekler — sağlık kapısı geçilince silinir, geçilmezse geri konur.
pub fn runtime_old_dir(install_root: &Path) -> PathBuf {
    install_root.join("runtime.old")
}

/// Yalnız APP katmanı güncellenirken eski app dosyalarının taşındığı yer.
///
/// NEDEN tam kopya değil: app katmanı ~71 MB / 155 dosya; taşıma (rename) aynı birimde metadata
/// işlemidir, 1,2 GB'lık ağacı kopyalamak ise dakikalar sürerdi. Başarısızlıkta buradan geri alınır.
pub fn app_backup_dir(install_root: &Path) -> PathBuf {
    runtime_dir(install_root).join("_app_yedek")
}

/// Backend çalıştırılabilirinin tam yolu.
pub fn backend_path(install_root: &Path) -> PathBuf {
    runtime_dir(install_root)
        .join("PEMF_Backend")
        .join(crate::platform::backend_exe_name())
}

/// `get_app_data_directory()` (Python) karşılığı. `env` çözümlemesi enjekte edilir
/// ki testler gerçek ortam değişkenlerine dokunmadan koşabilsin.
pub fn app_data_dir_with<F>(getenv: F, home: &Path) -> PathBuf
where
    F: Fn(&str) -> Option<String>,
{
    if let Some(override_dir) = getenv(ENV_DATA_DIR).filter(|v| !v.trim().is_empty()) {
        return PathBuf::from(override_dir.trim()).join("PEMF_GUI");
    }
    if cfg!(target_os = "windows") {
        let base = getenv("APPDATA")
            .filter(|v| !v.is_empty())
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join("AppData").join("Roaming"));
        base.join("PEMF_GUI")
    } else if cfg!(target_os = "macos") {
        home.join("Library").join("Application Support").join("PEMF_GUI")
    } else {
        home.join(".local").join("share").join("PEMF_GUI")
    }
}

/// LN L7 · D2.33 / D2.67 / D2.76 / D2.77: launcher'ın backend'e verdiği GERÇEK hasta veri kökü kurulum köküne yazılır → kaldırma
/// diyaloğu (launcher) ve NSIS KVKK iletisi tahmin değil, çalışma anındaki seçimi gösterir (makine-geneli kök yazılabilirse
/// `%PROGRAMDATA%\PEMF_System\PEMF_GUI`, değilse düşüş `%APPDATA%\PEMF_GUI`). Eskiden ikisi de sabit `%APPDATA%\PEMF_GUI` diyordu
/// (NSIS'te `all` bağlamında `C:\ProgramData\PEMF_GUI` — hiçbiri doğru değil). Kaldırmada silinir (hooks POSTUNINSTALL); profil
/// paketi ezemez (`extract.rs::PROFILE_FORBIDDEN_TOP`).
pub fn veri_koku_yolu(install_root: &Path) -> PathBuf {
    install_root.join("veri_koku.txt")
}

/// Veri kökünü kaydet: UTF-16LE, BOM'suz, satır sonu YOK (NSIS `FileReadUTF16LE` Türkçe kullanıcı adlı yolu da bozmadan okur;
/// ANSI `FileRead` cp1254 dışı karakteri bozardı). Atomik (geçici dosya + yeniden adlandırma).
pub fn veri_kokunu_kaydet(install_root: &Path, kok: &Path) -> std::io::Result<()> {
    let baytlar: Vec<u8> = kok.to_string_lossy().encode_utf16().flat_map(|c| c.to_le_bytes()).collect();
    let hedef = veri_koku_yolu(install_root);
    let gecici = hedef.with_extension("txt.yeni");
    std::fs::write(&gecici, baytlar)?;
    std::fs::rename(&gecici, &hedef).inspect_err(|_| {
        let _ = std::fs::remove_file(&gecici); // artık kalmasın: özyinelemesiz `RMDir "$INSTDIR"` dolu dizinde başarısız olur
    })
}

/// `veri_kokunu_kaydet`'in okuyucusu; dosya yok / bozuk / boş → `None`.
pub fn veri_kokunu_oku(install_root: &Path) -> Option<PathBuf> {
    let ham = std::fs::read(veri_koku_yolu(install_root)).ok()?;
    if ham.len() % 2 != 0 {
        return None;
    }
    let birim: Vec<u16> = ham.chunks_exact(2).map(|c| u16::from_le_bytes([c[0], c[1]])).collect();
    let s = String::from_utf16(&birim).ok()?;
    let s = s.trim().trim_start_matches('\u{feff}');
    (!s.is_empty()).then(|| PathBuf::from(s))
}

/// Kaldırma diyaloğunun göstereceği hasta veri konumu: `(birincil, diğer adaylar)`. Birincil = launcher'ın backend'e verdiği kök
/// (`veri_koku.txt`); dosya yoksa (backend bu sürümle hiç başlatılmadı) makine-geneli kök VARSA o, yoksa `%APPDATA%\PEMF_GUI`.
/// Diğer = öteki aday diskte VARSA (eski sürümün / başka Windows hesabının kayıtları — iki konumda da DB bulunan makine ölçüldü).
/// YAN ETKİSİZ: dizin yaratmaz, sonda yazmaz (yalnız `exists`). `getenv` / `home` enjekte edilir.
pub fn kaldirma_veri_konumu_with<F>(install_root: &Path, getenv: F, home: &Path) -> (PathBuf, Vec<PathBuf>)
where
    F: Fn(&str) -> Option<String>,
{
    let makine = machine_data_dir(&getenv).map(|d| d.join("PEMF_GUI"));
    let kullanici = app_data_dir_with(&getenv, home);
    let birincil = veri_kokunu_oku(install_root)
        .or_else(|| makine.clone().filter(|d| d.is_dir()))
        .unwrap_or_else(|| kullanici.clone());
    let ayni = |a: &Path, b: &Path| a.to_string_lossy().to_lowercase() == b.to_string_lossy().to_lowercase();
    let diger = [makine, Some(kullanici)]
        .into_iter()
        .flatten()
        .filter(|d| d.is_dir() && !ayni(d, &birincil))
        .collect();
    (birincil, diger)
}

/// Backend'in günlük dosyası — `backend_service.py:80` ile AYNI kural:
/// `PEMF_LOG_DIR` varsa o, yoksa `<app_data>/logs`.
///
/// DENETİM 2026-08-04: başlatma hatası teşhisinde kullanılır (bkz. `backend::read_tail`).
/// `getenv` enjekte edilir → testler gerçek ortam değişkenlerine dokunmaz.
pub fn backend_log_path_with<F>(getenv: F, home: &Path) -> PathBuf
where
    F: Fn(&str) -> Option<String> + Copy,
{
    if let Some(d) = getenv(ENV_LOG_DIR).filter(|v| !v.trim().is_empty()) {
        return PathBuf::from(d.trim()).join("backend_service.log");
    }
    app_data_dir_with(getenv, home).join("logs").join("backend_service.log")
}

/// Backend süreci için ortam değişkenleri. `health_nonce` boşsa değişken hiç verilmez.
pub fn backend_env(install_root: &Path, port: u16, health_nonce: &str) -> BTreeMap<String, String> {
    backend_env_with(|k| std::env::var(k).ok(), install_root, port, health_nonce)
}

/// `backend_env`in test edilebilir hâli — ortam okuması ENJEKTE edilir.
///
/// ⚠️ Neden: tünel tercihi süreç-geneli `PEMF_ENABLE_TUNNEL`den okunuyor. Testler PARALEL
/// koşar; biri `set_var` yapınca diğeri onu görüyor ve yanlış-kırmızı veriyordu (ilk yazımda
/// tam olarak bu oldu). Enjeksiyonla test global duruma HİÇ dokunmaz — depoda
/// `backend_log_path_with`/`app_data_dir_with` ile aynı desen.
pub fn backend_env_with<F>(
    getenv: F,
    install_root: &Path,
    port: u16,
    health_nonce: &str,
) -> BTreeMap<String, String>
where
    F: Fn(&str) -> Option<String> + Copy,
{
    let mut env = BTreeMap::new();
    env.insert(
        ENV_MODELS_DIR.to_string(),
        models_dir(install_root).to_string_lossy().into_owned(),
    );
    env.insert(ENV_API_PORT.to_string(), port.to_string());
    // Güvenli varsayılan (bkz. ENV_REQUIRE_AUTH): uzak/tünel erişimi token ister; LAN muaf kalır.
    env.insert(ENV_REQUIRE_AUTH.to_string(), "1".to_string());
    // KVKK (bkz. ENV_ENCRYPT_AT_REST): hasta verisi diske ŞİFRELİ yazılır. Bu satır olmadan
    // launcher ile kurulan klinikler düz-metin yazıyordu.
    env.insert(ENV_ENCRYPT_AT_REST.to_string(), "1".to_string());
    // UZAKTAN ERİŞİM (bkz. ENV_ENABLE_TUNNEL): bu satır olmadan launcher ile kuran hiçbir klinik
    // farklı ağdan bağlanamıyordu — arayüz bunu vaat ettiği hâlde. Ortamda zaten tanımlıysa
    // DOKUNMA (çıkış kapısı: `PEMF_ENABLE_TUNNEL=0` ile kapatılabilir).
    env.insert(
        ENV_ENABLE_TUNNEL.to_string(),
        getenv(ENV_ENABLE_TUNNEL)
            .filter(|v| !v.trim().is_empty())
            .unwrap_or_else(|| "1".to_string()),
    );
    // STM32 PORT OTO-ALGILAMASI (bkz. ENV_STM_PORT): bu satır olmadan launcher ile kuran her
    // klinikte backend sabit COM10'u deniyor ve ST-Link başka bir COM'daysa bobin 1-5 HİÇ
    // bağlanmıyordu (ESP 6-8 çalıştığı için cihaz "yarı çalışıyor" görünüyordu).
    // Ortamda zaten tanımlıysa DOKUNMA (çıkış kapısı: `PEMF_STM_PORT=COM7` ya da `socket://…`).
    env.insert(
        ENV_STM_PORT.to_string(),
        getenv(ENV_STM_PORT)
            .filter(|v| !v.trim().is_empty())
            .unwrap_or_else(|| "auto".to_string()),
    );
    // ARAŞTIRMA AI PRO SÜRÜŞÜ (bkz. ENV_ARASTIRMA_AIPRO): bu satır olmadan operatörün açtığı
    // bayrak launcher yolundaki backend'e HİÇ ulaşmıyordu. Varsayılan "0" = backend'in zaten
    // uyguladığı fail-safe (kedi dışı modellerle sürüş KAPALI). Ortamda tanımlıysa DOKUNMA.
    env.insert(
        ENV_ARASTIRMA_AIPRO.to_string(),
        getenv(ENV_ARASTIRMA_AIPRO)
            .filter(|v| !v.trim().is_empty())
            .unwrap_or_else(|| "0".to_string()),
    );
    // KEDİ AI PRO SÜRÜŞÜ (bkz. ENV_KEDI_AIPRO_SURUS · Y142): yalnız taşıyıcı; varsayılan "0" = KAPALI. Ortamda tanımlıysa DOKUNMA.
    env.insert(
        ENV_KEDI_AIPRO_SURUS.to_string(),
        getenv(ENV_KEDI_AIPRO_SURUS)
            .filter(|v| !v.trim().is_empty())
            .unwrap_or_else(|| "0".to_string()),
    );
    // FANTOM AI PRO SÜRÜŞÜ (bkz. ENV_ARASTIRMA_AIPRO_FANTOM · D3 T-f): yalnız taşıyıcı; varsayılan "0" = KAPALI. Ortamda tanımlıysa DOKUNMA.
    env.insert(
        ENV_ARASTIRMA_AIPRO_FANTOM.to_string(),
        getenv(ENV_ARASTIRMA_AIPRO_FANTOM)
            .filter(|v| !v.trim().is_empty())
            .unwrap_or_else(|| "0".to_string()),
    );
    // SAKLAMA SÜRELERİ (bkz. ENV_SAKLAMA · S-F2-3.2 a): yalnız TANIMLI olanlar, değer AYNEN (boş da — backend'in kapatma anlamı).
    for ad in ENV_SAKLAMA {
        if let Some(v) = getenv(ad) {
            env.insert(ad.to_string(), v);
        }
    }
    // DNS-REBINDING KORUMASI (bkz. ENV_ALLOWED_HOSTS): bu satir olmadan launcher ile kuran
    // hicbir klinikte Host korumasi calismiyordu. Ortamda tanimliysa DOKUNMA.
    env.insert(
        ENV_ALLOWED_HOSTS.to_string(),
        getenv(ENV_ALLOWED_HOSTS)
            .filter(|v| !v.trim().is_empty())
            .unwrap_or_else(|| "auto".to_string()),
    );
    // JETON KAPISI (bkz. ENV_JETON_ENFORCED): backend'de modul hazir ama launcher bayragi
    // gecirmiyordu -> makinede tanimlansa bile gorunmuyordu. Varsayilan "0" = bugunku canli
    // davranis (satis acilmadi, tam no-op). Ortamda tanimliysa DOKUNMA.
    env.insert(
        ENV_JETON_ENFORCED.to_string(),
        getenv(ENV_JETON_ENFORCED)
            .filter(|v| !v.trim().is_empty())
            .unwrap_or_else(|| "0".to_string()),
    );
    // DÜZ-METİN YEDEK EMANETİ (bkz. ENV_KEEP_PLAIN_BACKUP): `.plain.bak` TÜM PII'nin düz-metin
    // tam kopyasıdır. Varsayılan "0" = güvenli-sil (bugünkü canlı davranış). KOŞULSUZ eklenir;
    // ortamdaki değer KORUNUR → operatör emaneti açıkça açabilir. "Nasılsa miras alınır"
    // gerekçesine güvenilmedi: servis (NSSM) yolu mirası ALMAZ ve miras launcher sürecinin
    // başlangıç ortamına bağlıdır.
    env.insert(
        ENV_KEEP_PLAIN_BACKUP.to_string(),
        getenv(ENV_KEEP_PLAIN_BACKUP)
            .filter(|v| !v.trim().is_empty())
            .unwrap_or_else(|| "0".to_string()),
    );
    // HOTSPOT PROFİL KAPISI (bkz. ENV_HOTSPOT · Y234): ortamdaki değer AYNEN; yoksa yalnız terapisiz kurulumda "0".
    if let Some(v) = getenv(ENV_HOTSPOT).filter(|v| !v.trim().is_empty()) {
        env.insert(ENV_HOTSPOT.to_string(), v);
    } else if hotspot_kapatilmali(&read_installed_profiles(install_root)) {
        env.insert(ENV_HOTSPOT.to_string(), "0".to_string());
    }
    // TIBBİ VERİ KÖKÜ (bkz. ENV_DATA_DIR): makine-geneli yazılabilirse oraya. Bu satır olmadan
    // backend %APPDATA%'ya düşüyor ve ikinci Windows hesabı "boş klinik" görüyordu.
    if let Some(d) = cozulmus_veri_dizini(getenv) {
        env.insert(ENV_DATA_DIR.to_string(), d.to_string_lossy().into_owned());
    }
    // PAYLAŞILAN YEREL GRUP (bkz. ENV_DATA_GROUP_SID · Y96): yalnız GEÇERLİYSE (biçim + bu makinenin yerel grubu) — backend'in
    // `file_acl` kilitleri grubu açıkça verir; geçersiz değer geçirilmez (backend de reddeder).
    if let Some(g) = paylasilan_grup_sid(getenv) {
        env.insert(ENV_DATA_GROUP_SID.to_string(), g);
    }
    // OFF-SITE YEDEK (bkz. ENV_BACKUP_DIR): operatör bir hedef seçtiyse geçir. Hedef o an
    // erişilemiyorsa (USB çıkarılmış) DEĞİŞKEN VERİLMEZ — backend'in her turda hataya düşüp
    // günlüğü doldurmasındansa yedek sessizce yerelde kalsın; UI eksikliği zaten bildiriyor.
    if let Some(b) = backup_dir_oku(install_root) {
        if dizin_yazilabilir_mi(&b) {
            env.insert(ENV_BACKUP_DIR.to_string(), b.to_string_lossy().into_owned());
        }
    }
    // FİLO ENVANTERİ (bkz. ENV_LAUNCHER_VERSION): backend bunları bulut cihaz kaydına yazar →
    // geri çağırma gerektiğinde hangi kliniğin hangi sürümde olduğu BİLİNİR.
    env.insert(ENV_LAUNCHER_VERSION.to_string(), env!("CARGO_PKG_VERSION").to_string());
    let paketler = read_installed_packages(install_root);
    // Katmanlı kurulumda `app` bizim kodumuzdur (her sürümde değişir); katmansızda `base`.
    let sha = if paketler.app.is_empty() { paketler.base } else { paketler.app };
    if !sha.is_empty() {
        env.insert(ENV_BASE_SHA.to_string(), sha);
    }
    if !health_nonce.is_empty() {
        env.insert(ENV_HEALTH_NONCE.to_string(), health_nonce.to_string());
    }
    env
}

/// Güncelleme SAĞLIK KAPISINDA başlatılan backend'in paket kimliği (`ENV_BASE_SHA`).
///
/// ⚠️ YAYIN 2026-11-03 bulgusu: kayıt (`installed_packages.json`) sağlık kapısı GEÇTİKTEN SONRA yazılır
/// (`flow::guncellemeyi_onayla`), ama kapıda başlatılan süreç onaydan sonra da ÇALIŞMAYA DEVAM EDER →
/// `backend_env` kimliği eski kayıttan okuyordu ve güncellemeden sonraki ilk oturum `/api/health`te
/// ESKİ `buildId`i raporluyordu (destek / bulut envanteri cihazı yanlış paketle görür). Kapıdaki
/// başlatma, onaylanacak kimliği buradan geçirir; `None` / boş = kayıttaki değer AYNEN kalır.
pub fn paket_kimligini_uygula(
    mut env: BTreeMap<String, String>,
    paket_kimligi: Option<&str>,
) -> BTreeMap<String, String> {
    if let Some(k) = paket_kimligi.map(str::trim).filter(|k| !k.is_empty()) {
        env.insert(ENV_BASE_SHA.to_string(), k.to_string());
    }
    env
}

/// Kurulu backend'in sürümü (`runtime/PEMF_Backend/_internal/VERSION`).
///
/// GERİ ÇAĞIRMA için gerekli (bkz. `Manifest::min_supported_version`): "bu cihaz destek dışı
/// bir sürümde mi?" sorusunun cevabı. Dosya yoksa (çok eski base.zip) `"0.0.0"` döner — yani
/// ESKİ sayılır ve zorunlu güncellemeye girer. Bu bilinçli bir fail-safe: sürümünü söyleyemeyen
/// bir kurulum, geri çağırma kapsamının DIŞINDA kalmamalıdır.
pub fn kurulu_surum(install_root: &Path) -> String {
    std::fs::read_to_string(
        runtime_dir(install_root)
            .join("PEMF_Backend")
            .join("_internal")
            .join("VERSION"),
    )
    .ok()
    .map(|s| s.trim().to_string())
    .filter(|s| !s.is_empty())
    .unwrap_or_else(|| "0.0.0".to_string())
}

/// Kurulu backend `PEMF_HEALTH_NONCE`'u yansıtabiliyor mu?
///
/// Nonce desteği ile `VERSION` dosyasının PyInstaller bundle'ına eklenmesi AYNI sürümde geldi
/// (bkz. `build_tools/PEMF_Backend_onedir.spec`). Dolayısıyla `_internal/VERSION` varlığı,
/// "bu backend nonce'u yansıtır" için güvenilir ve SÜRÜM AYRIŞTIRMAYA gerek bırakmayan bir
/// göstergedir. Sahadaki ESKİ base.zip'lerde dosya YOKTUR → launcher hoşgörülü moda düşer ve
/// kurulumu kırmaz. Yeni base.zip yayınlandığı anda doğrulama KENDİLİĞİNDEN katılaşır.
pub fn backend_supports_health_nonce(install_root: &Path) -> bool {
    runtime_dir(install_root)
        .join("PEMF_Backend")
        .join("_internal")
        .join("VERSION")
        .exists()
}

/// Uygulamanın (base + modeller) kurulacağı kök.
///
/// Kullanıcı-başına kurulum: yönetici hakkı GEREKTİRMEZ. Klinik makinelerinde
/// operatör çoğu zaman yönetici değildir; Program Files'a yazmaya çalışmak
/// kurulumu ilk adımda düşürür.
pub fn default_install_root(home: &Path) -> PathBuf {
    if cfg!(target_os = "windows") {
        home.join("AppData").join("Local").join("PEMF Vet Client")
    } else if cfg!(target_os = "macos") {
        home.join("Library").join("Application Support").join("PEMF Vet Client")
    } else {
        home.join(".local").join("share").join("PEMF Vet Client")
    }
}

/// İndirilen paketlerin önbelleği (yeniden kurulumda tekrar indirme yok).
pub fn cache_dir(install_root: &Path) -> PathBuf {
    install_root.join("cache")
}

/// Yükseltme migrasyonu: eski sürüm kurulum kökünü boşluksuz `PEMFVetClient` olarak
/// oluşturuyordu; productName `PEMF Vet Client` olunca yeni kök değişti. Eski dizin varsa
/// ve yeni yoksa yeniden adlandır → indirilen ~2 GB payload (runtime + ai_models) tekrar
/// inmez. Best-effort: eski dizin kilitliyse (backend çalışıyorsa) sessizce atlanır ve akış
/// normal temiz-indirmeye düşer. Hasta DB'si ayrı dizinde (`PEMF_GUI`) → bundan etkilenmez.
pub fn migrate_legacy_install_root(install_root: &Path) {
    // ⚠️ DENETİM 2026-08-04 (P2): koşul `install_root.exists()` idi ve bu migrasyonu TAMAMEN
    // ÖLDÜRÜYORDU. `install_root`, NSIS `$INSTDIR`'ın TA KENDİSİDİR (ampirik olarak doğrulandı:
    // `PEMFVetClient.exe` + `uninstall.exe` `runtime/` ile AYNI dizinde) ve launcher hiç
    // çalışmadan ÖNCE, kurulum anında oluşturulur → erken-return HER ZAMAN tetikleniyordu.
    // Bu denetimde eklenen `record_selfupdate_attempt` da `create_dir_all(install_root)` yaparak
    // durumu ayrıca pekiştiriyordu. Sonuç: yükseltmede ~2,6 GB payload YENİDEN İNDİRİLİYORDU.
    // Doğru ölçüt dizinin VARLIĞI değil, YÜKÜN varlığıdır.
    if runtime_dir(install_root).exists() || has_model_data(install_root) {
        return; // yeni kökte zaten payload var → taşınacak bir şey yok
    }
    let Some(parent) = install_root.parent() else {
        return;
    };
    let legacy = parent.join("PEMFVetClient");
    if !legacy.is_dir() {
        return;
    }
    // Eski kökte de payload yoksa uğraşma (boş/artık dizin).
    if !(runtime_dir(&legacy).exists() || has_model_data(&legacy)) {
        return;
    }

    // En ucuz yol: hedef hiç yoksa dizini komple yeniden adlandır.
    if !install_root.exists() && std::fs::rename(&legacy, install_root).is_ok() {
        return;
    }
    // Hedef VAR (NSIS oluşturdu) → `rename` başarısız olur; İÇERİĞİ taşı.
    // Yeni kurulumun kendi dosyalarını (exe, uninstall.exe) ASLA EZME.
    let _ = std::fs::create_dir_all(install_root);
    if let Ok(rd) = std::fs::read_dir(&legacy) {
        for e in rd.flatten() {
            let hedef = install_root.join(e.file_name());
            if hedef.exists() {
                continue;
            }
            let _ = std::fs::rename(e.path(), &hedef);
        }
    }
}

/// Windows'ta eski kurulumun modelleri `%PROGRAMDATA%\PEMF_GUI\ai_models` altında
/// olabilir. Doluysa profil paketini YENİDEN İNDİRME (2 GB'a kadar boşa trafik).
/// Yükseltme yolunda kullanılır; diğer platformlarda her zaman `None`.
pub fn legacy_windows_models_dir<F>(getenv: F) -> Option<PathBuf>
where
    F: Fn(&str) -> Option<String>,
{
    if !cfg!(target_os = "windows") {
        return None;
    }
    let pd = getenv("PROGRAMDATA").filter(|v| !v.is_empty())?;
    let dir = PathBuf::from(pd).join("PEMF_GUI").join("ai_models");
    dir.is_dir().then_some(dir)
}

/// Kurulu profillerin kaydı (`Ev Sahibi`/`Veteriner`/`Araştırma` — UI çip'leri + Onar bunu okur).
/// install_root içinde tutulur → kaldırınca birlikte gider (durum sıfırlanır).
pub fn installed_profiles_path(install_root: &Path) -> PathBuf {
    install_root.join("installed_profiles.json")
}

/// Kurulu profilleri oku (JSON dizi). Dosya yok/bozuksa boş liste (fail-safe).
pub fn read_installed_profiles(install_root: &Path) -> Vec<String> {
    std::fs::read_to_string(installed_profiles_path(install_root))
        .ok()
        .and_then(|s| serde_json::from_str::<Vec<String>>(&s).ok())
        .unwrap_or_default()
}

// ─────────────────────────── KURULU PAKET KAYDI (runtime oto-güncelleme) ───────────────────────
//
// SAHİP KARARI 2026-08-08: "Onar'a basmadan, client'ı kapatıp açınca backend dâhil TÜM
// güncellemeler gelmeli; siteye deploy etmem yetmeli." Bunun için launcher'ın "DİSKTEKİ paket
// hangi sürüm?" sorusuna cevap verebilmesi gerekir — eskiden bu bilgi HİÇ tutulmuyordu
// (`installed_profiles.json` yalnız profil ADLARINI biliyordu), bu yüzden manifest ile
// karşılaştırma yapılamıyor ve güncelleme kullanıcının "Onar" demesine bağlı kalıyordu.
//
// Kayıt install_root içinde durur → "Uygulamayı kaldır" ile birlikte gider (durum sıfırlanır).

/// Kurulu paketlerin sha256 kaydı (base + her profil modeli).
pub fn installed_packages_path(install_root: &Path) -> PathBuf {
    install_root.join("installed_packages.json")
}

/// Diskteki paketlerin kimliği. Boş alan = BİLİNMİYOR (kayıt öncesi kurulum).
#[derive(Debug, Default, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct InstalledPackages {
    /// Tek parça base.zip kimliği (eski yol / katmansız manifest).
    #[serde(default)]
    pub base: String,
    /// Katmanlı kurulumda bağımlılık katmanı (2026-08-08).
    #[serde(default)]
    pub deps: String,
    /// Katmanlı kurulumda uygulama katmanı (bizim kod) — her sürümde değişir.
    #[serde(default)]
    pub app: String,
    #[serde(default)]
    pub models: BTreeMap<String, String>,
}

/// KURULUM KİMLİĞİ — kademeli yayın diliminin KARARLI kaynağı.
///
/// İlk çağrıda üretilip diske yazılır, sonra hep aynı kalır. Rastgele bir sayı her açılışta
/// yeniden üretilseydi cihaz dilimler arasında zıplar ve "önce %10'a aç, izle" diye bir şey
/// mümkün olmazdı (her açılışta farklı cihazlar girip çıkardı).
pub fn kurulum_kimligi(install_root: &Path) -> String {
    let p = install_root.join("install_id.txt");
    if let Ok(s) = std::fs::read_to_string(&p) {
        let s = s.trim().to_string();
        if !s.is_empty() {
            return s;
        }
    }
    // Kriptografik olması gerekmiyor: amaç kimlik değil, dengeli dağılım.
    let t = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let id = format!("{t:032x}");
    let _ = std::fs::create_dir_all(install_root);
    let _ = std::fs::write(&p, &id);
    id
}

/// Cihazın kademeli yayın dilimi (0-99). Kurulum kimliğinden türetilir → kararlı.
pub fn rollout_dilimi(install_root: &Path) -> u8 {
    let id = kurulum_kimligi(install_root);
    // FNV-1a: küçük, bağımlılıksız, bu amaç için yeterince dengeli.
    let mut h: u64 = 0xcbf29ce484222325;
    for b in id.as_bytes() {
        h ^= *b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    (h % 100) as u8
}

pub fn record_layer_sha(install_root: &Path, katman: &str, sha: &str) {
    let mut p = read_installed_packages(install_root);
    match katman {
        "deps" => p.deps = sha.to_ascii_lowercase(),
        "app" => p.app = sha.to_ascii_lowercase(),
        _ => return,
    }
    write_installed_packages(install_root, &p);
}

/// APP KATMANININ SINIRI — app paketi kendi köklerini `_app_roots.json` içinde taşır.
///
/// NEDEN dosyadan okunuyor (launcher'a gömülü sabit liste DEĞİL): app güncellenirken ESKİ sürümün
/// dosyaları silinmeli, yoksa yeni sürümde KALDIRILAN dosyalar (eski `.pyd`, eski web bundle
/// parçaları) diskte yaşar — PyInstaller ağacında bayat bir uzantı, sürüm numarasına bakan hiçbir
/// teşhisle görünmeyen tanımsız davranış üretir. Sınır pakette taşınırsa, ileride sınır değişse
/// bile launcher'ı elle güncellemek gerekmez.
pub fn app_roots_path(install_root: &Path) -> PathBuf {
    runtime_dir(install_root).join("PEMF_Backend").join("_app_roots.json")
}

/// Diskteki app katmanının kökleri. Dosya yoksa/bozuksa BOŞ döner — çağıran o zaman silme yapmaz
/// (üzerine-yazma moduna düşer): bilinmeyen bir sınırla dosya silmek, bayat dosya bırakmaktan
/// çok daha tehlikelidir.
pub fn read_app_roots(install_root: &Path) -> Vec<String> {
    #[derive(serde::Deserialize)]
    struct R {
        #[serde(default)]
        roots: Vec<String>,
    }
    std::fs::read_to_string(app_roots_path(install_root))
        .ok()
        .and_then(|s| serde_json::from_str::<R>(&s).ok())
        .map(|r| r.roots)
        .unwrap_or_default()
        .into_iter()
        // Yol-kaçışı olan bir kök `runtime/` DIŞINDA silme yapabilirdi; paket bizim ürettiğimiz
        // olsa da bu dosya diskten okunuyor → kaçış içeren girdileri AT.
        .filter(|r| !r.contains("..") && !r.starts_with('/') && !r.contains(':') && !r.contains('\\'))
        .collect()
}

/// Kurulu paket kaydını oku. Dosya yok/bozuksa BOŞ döner — bu "bilinmiyor" demektir,
/// "güncel" değil (bkz. `flow::pending_updates`: bilinmeyen base = güncellenmeli).
pub fn read_installed_packages(install_root: &Path) -> InstalledPackages {
    std::fs::read_to_string(installed_packages_path(install_root))
        .ok()
        .and_then(|s| serde_json::from_str::<InstalledPackages>(&s).ok())
        .unwrap_or_default()
}

fn write_installed_packages(install_root: &Path, p: &InstalledPackages) {
    if let Ok(json) = serde_json::to_string_pretty(p) {
        let _ = std::fs::write(installed_packages_path(install_root), json);
    }
}

/// base.zip başarıyla AÇILDIKTAN sonra çağrılır.
///
/// ⚠️ SIRA ÖNEMLİ: kaydı yalnız açma bittikten sonra yaz. Önce yazılırsa, yarıda kesilen bir
/// açılım "bu sürüm kurulu" diye işaretlenir ve bir daha ASLA onarılmaz.
pub fn record_base_sha(install_root: &Path, sha: &str) {
    let mut p = read_installed_packages(install_root);
    p.base = sha.to_ascii_lowercase();
    write_installed_packages(install_root, &p);
}

/// Profil model paketi açıldıktan sonra çağrılır (aynı sıra kuralı).
pub fn record_model_sha(install_root: &Path, profile: &str, sha: &str) {
    let mut p = read_installed_packages(install_root);
    p.models.insert(profile.to_string(), sha.to_ascii_lowercase());
    write_installed_packages(install_root, &p);
}

/// Aynı hedef sürüm için izin verilen OTOMATİK self-update denemesi sayısı.
pub const MAX_SELFUPDATE_ATTEMPTS: u32 = 2;

fn selfupdate_state_path(install_root: &Path) -> PathBuf {
    install_root.join("selfupdate_attempt.json")
}

/// Son denenen self-update hedefi ve deneme sayısı: `(sürüm, sayı)`.
///
/// DENETİM 2026-08-04 (P2 — SONSUZ DÖNGÜ): karar YALNIZ `manifest.launcher.version` vs
/// `CARGO_PKG_VERSION` kıyasına dayanıyordu; hangi hedefin DENENDİĞİ/BAŞARISIZ olduğu hiçbir
/// yerde tutulmuyordu. Manifest "1.9.9" derken `installer_url` gerçekte 1.9.8'i gösterirse
/// (klasik `--clobber`/yanlış-asset yayın hatası) kurulum "başarılı" olur ama SÜRÜM DEĞİŞMEZ →
/// bir sonraki açılışta aynı karar yeniden verilir → indir-kur-yeniden başlat DÖNGÜSÜ.
/// Üstelik UI o ekranda Duraklat/İptal'i GİZLEDİĞİ için kullanıcı döngüyü kıramıyordu.
pub fn read_selfupdate_attempt(install_root: &Path) -> Option<(String, u32)> {
    let s = std::fs::read_to_string(selfupdate_state_path(install_root)).ok()?;
    let v: serde_json::Value = serde_json::from_str(&s).ok()?;
    let ver = v.get("version")?.as_str()?.to_string();
    let n = v.get("count").and_then(|c| c.as_u64()).unwrap_or(0) as u32;
    Some((ver, n))
}

/// Bu hedef için deneme sayacını artır (aynı sürümse +1, farklı sürümse 1'den başlar).
pub fn record_selfupdate_attempt(install_root: &Path, version: &str) {
    let n = match read_selfupdate_attempt(install_root) {
        Some((v, c)) if v == version => c.saturating_add(1),
        _ => 1,
    };
    // P2: burada `create_dir_all` yapmak, migrasyonun eski "kök varsa erken-return" korumasını
    // tetikleyip eski ağacın taşınmasını engelliyordu. Migrasyon artık yük-temelli olduğu için
    // sıra kritik değil, yine de önce göç denenir (idempotent, ucuz).
    migrate_legacy_install_root(install_root);
    let _ = std::fs::create_dir_all(install_root);
    if let Ok(json) = serde_json::to_string(&serde_json::json!({ "version": version, "count": n })) {
        let _ = std::fs::write(selfupdate_state_path(install_root), json);
    }
}

/// Güncelleme GERÇEKTEN uygulandığında (çalışan sürüm hedefe ulaştı) sayacı sıfırla.
pub fn clear_selfupdate_attempt(install_root: &Path) {
    let _ = std::fs::remove_file(selfupdate_state_path(install_root));
}

/// Bu hedef sürüm için OTOMATİK (sessiz) güncelleme hâlâ denenmeli mi?
/// Sınır aşıldıysa `false` → bildirim kalır ama sessiz kurulum DURUR (döngü kırılır).
pub fn selfupdate_auto_allowed(install_root: &Path, target_version: &str) -> bool {
    match read_selfupdate_attempt(install_root) {
        Some((v, c)) if v == target_version => c < MAX_SELFUPDATE_ATTEMPTS,
        _ => true,
    }
}

// ── SELF-UPDATE "GÜNCELLEME SÜRÜYOR" İŞARETİ (saha bildirimi 2026-09-04) ──────────────────────
//
// Launcher self-update'te `app.exit(0)` ile çıkar; kurulum bitip yeni sürüm açılana kadar ekranda
// HİÇBİR ŞEY yoktu (Defender'ın 265 MB setup taraması + NSIS + sabit beklemeler = yavaş makinede
// 10-30 sn). Kullanıcı bu boşlukta exe'ye yeniden tıklıyor → ESKİ exe açılıp NSIS'in dosya
// kilidine çarpıyordu. Bu işaret dosyası iki şeye yarar:
//   (1) `--guncelleme-ekrani` ile açılan bilgilendirme penceresi, işaret silinince (yeni sürüm
//       açıldı) ya da işaret bayatlayınca kendini kapatır;
//   (2) boşlukta yeniden tıklanan ESKİ exe işareti görüp SESSİZCE çıkar (ekranda zaten
//       "güncelleniyor" penceresi var). Yeni sürüm açılınca işaret temizlenir.
// ⚠️ Kilit KENDİLİĞİNDEN çözülür: işaret `azami_yas_s`'den yaşlıysa (kurulum başarısız/asılı)
// eski exe yine açılır — kullanıcı asla kalıcı olarak dışarıda kalmaz.
pub const GUNCELLEME_ISARETI_DOSYASI: &str = "selfupdate_inprogress.json";

fn guncelleme_isareti_yolu(install_root: &Path) -> PathBuf {
    install_root.join(GUNCELLEME_ISARETI_DOSYASI)
}

fn unix_simdi() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// İşareti yaz: `{from, to, started_unix}`. Yazılamazsa sessizce geç (güncelleme yine sürer).
pub fn guncelleme_isareti_yaz(install_root: &Path, from: &str, to: &str) {
    let _ = std::fs::create_dir_all(install_root);
    if let Ok(json) = serde_json::to_string(&serde_json::json!({
        "from": from, "to": to, "started_unix": unix_simdi()
    })) {
        let _ = std::fs::write(guncelleme_isareti_yolu(install_root), json);
    }
}

/// İşareti oku: `(from, to, yaş_saniye)`. Yoksa/bozuksa `None`. Saat geriye alınmışsa yaş 0.
pub fn guncelleme_isareti_oku(install_root: &Path) -> Option<(String, String, u64)> {
    let s = std::fs::read_to_string(guncelleme_isareti_yolu(install_root)).ok()?;
    let v: serde_json::Value = serde_json::from_str(&s).ok()?;
    let from = v.get("from")?.as_str()?.to_string();
    let to = v.get("to")?.as_str()?.to_string();
    let basladi = v.get("started_unix").and_then(|x| x.as_u64()).unwrap_or(0);
    Some((from, to, unix_simdi().saturating_sub(basladi)))
}

/// İşaret var ve `azami_yas_s`'den genç mi?
pub fn guncelleme_isareti_taze(install_root: &Path, azami_yas_s: u64) -> bool {
    matches!(guncelleme_isareti_oku(install_root), Some((_, _, yas)) if yas <= azami_yas_s)
}

pub fn guncelleme_isaretini_temizle(install_root: &Path) {
    let _ = std::fs::remove_file(guncelleme_isareti_yolu(install_root));
}

/// Açılıştaki karar: bu süreç, güncelleme boşluğunda yeniden tıklanan ESKİ exe mi?
/// `true` → sessizce çık (bilgilendirme penceresi zaten ekranda; işaret KALIR, pencere ona bakıyor).
/// Diğer her durumda işaret temizlenir (yeni sürüm açıldı / işaret bayat / hedef == kaynak) →
/// normal açılış. `from == to` (yanlış yapılandırılmış manifest) ASLA kilitlemez.
pub fn guncelleme_bosluguna_dusen_eski_exe_mi(install_root: &Path, calisan_surum: &str, azami_yas_s: u64) -> bool {
    match guncelleme_isareti_oku(install_root) {
        Some((from, to, yas)) if yas <= azami_yas_s && from != to && calisan_surum == from => true,
        Some(_) => {
            guncelleme_isaretini_temizle(install_root);
            false
        }
        None => false,
    }
}

// ── RUNTIME GÜNCELLEMESİ: geri alma döngüsü kırıcı (denetim 2026-08-23, C2) ──────────────────
//
// ⚠️ SORUN: sağlık kapısı düşünce güncelleme geri alınıyordu ama HİÇBİR deneme sayacı
// tutulmuyordu — kodun kendi yorumu bunu kabul ediyordu ("kayıtlar yazılmadığı için disk
// 'bilinmiyor'da kalır; sonraki açılış yeniden dener"). Yapısal doğrulamayı geçen ama backend'i
// başlatamayan bir yayında bu, HER açılışta: backend öldür → ~1,19 GB deps aç → 180 sn boşuna
// bekle → geri al demekti. Klinik her açılışta dakikalarca bloklanıyor ve tek çıkış yolu
// yayıncının manifest'e `rollout: 0` yazması oluyordu.
//
// Launcher'ın KENDİ self-update'inde bu koruma 2026-08-04'te eklendi (`MAX_SELFUPDATE_ATTEMPTS`);
// runtime yolunda karşılığı yoktu. Desen birebir aynı, hedef kimliği farklı: sürüm numarası değil
// paket sha'ları (aynı sürüm numarası altında farklı ikili yayınlanabilir).

/// Aynı hedef için izin verilen OTOMATİK runtime kurulumu denemesi.
///
/// 2: ilk düşüş geçici olabilir (o anda çalışan başka bir süreç, anlık disk/AV olayı); ikincisi
/// artık kalıcı bir arıza sayılır. Sınır aşılınca YALNIZ otomatik kurulum durur — bildirim ve
/// kullanıcının elle "Onar" demesi ETKİLENMEZ.
pub const MAX_RUNTIME_ATTEMPTS: u32 = 2;

fn runtime_attempt_path(install_root: &Path) -> PathBuf {
    install_root.join("runtime_attempt.json")
}

/// Son denenen runtime hedefi ve deneme sayısı: `(hedef, sayı)`.
///
/// ⚠️ FAIL-OPEN: dosya yok/bozuksa `None` → güncelleme akmaya devam eder. Tek bir bozuk bayt
/// cihazı eski sürümde dondurmamalı; bu sayaç bir kolaylıktır, bir kapı değil.
pub fn read_runtime_attempt(install_root: &Path) -> Option<(String, u32)> {
    let s = std::fs::read_to_string(runtime_attempt_path(install_root)).ok()?;
    let v: serde_json::Value = serde_json::from_str(&s).ok()?;
    let hedef = v.get("hedef")?.as_str()?.to_string();
    let n = v.get("count").and_then(|c| c.as_u64()).unwrap_or(0) as u32;
    Some((hedef, n))
}

/// Bu hedef için sayacı artır (aynı hedefse +1, FARKLI hedefse 1'den başlar).
///
/// Geri alma anında çağrılır. Farklı hedefte sıfırlanması kritik: düzeltme yayını (yeni sha)
/// eski hedefin sayacına takılıp cihaza ulaşamazsa koruma, korumaya çalıştığı şeyi bozar.
pub fn record_runtime_attempt(install_root: &Path, hedef: &str) {
    let n = match read_runtime_attempt(install_root) {
        Some((h, c)) if h == hedef => c.saturating_add(1),
        _ => 1,
    };
    let _ = std::fs::create_dir_all(install_root);
    if let Ok(json) = serde_json::to_string(&serde_json::json!({ "hedef": hedef, "count": n })) {
        let _ = std::fs::write(runtime_attempt_path(install_root), json);
    }
}

/// Güncelleme GERÇEKTEN başarılı olduğunda sayacı sıfırla.
pub fn clear_runtime_attempt(install_root: &Path) {
    let _ = std::fs::remove_file(runtime_attempt_path(install_root));
}

/// Bu hedef için OTOMATİK (sessiz) runtime kurulumu hâlâ denenmeli mi?
pub fn runtime_otomatik_izinli(install_root: &Path, hedef: &str) -> bool {
    match read_runtime_attempt(install_root) {
        Some((h, c)) if h == hedef => c < MAX_RUNTIME_ATTEMPTS,
        _ => true,
    }
}

/// `installed_profiles.json` kaydının DURUMU.
///
/// DENETİM 2026-08-04 (P2): `read_installed_profiles` FAIL-SAFE tasarlanmıştı — dosya yoksa VEYA
/// JSON bozuksa `.unwrap_or_default()` ile BOŞ liste dönüyordu. `repair()` onarılacak paket
/// listesini TAMAMEN bundan aldığı için boş listeyle çağrılıyor, YALNIZ base indirilip açılıyor,
/// HİÇBİR model paketi doğrulanmıyor/onarılmıyordu — ve fonksiyon `Ok(())` dönüp UI "Hazır"
/// diyordu. Oysa bu dosya tam da onarımı gerektiren senaryolarda (yarım kalan kurulum, disk
/// hatası, kısmi silme) bozulur; üstelik profil zip'lerinin açıldığı `install_root`'un
/// İÇİNDEDİR, yani bir profil arşivi tarafından da ezilebilir.
/// "Modeller onarılmadı" durumu artık SESSİZ KALMIYOR — çağıran ayırt edebiliyor.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProfileRecord {
    /// Kayıt okundu. Boş olabilir — gerçekten yalnız base kurulu demektir.
    Ok(Vec<String>),
    /// Kayıt dosyası YOK.
    Missing,
    /// Dosya var ama JSON olarak ayrıştırılamıyor.
    Corrupt,
}

/// Kayıt dosyası YOKKEN kurulu profilleri DİSKTEN çıkar (`ai_models/<profil>/`).
///
/// ⚠️ DENETİM 2026-08-04 (P3): `repair()` `Missing` ile `Corrupt`'ı AYNI kovaya koyuyordu ve
/// diskte model verisi varsa ikisinde de HATA veriyordu. Ama `installed_profiles.json` bu
/// projeye 2026-07-29'da eklendi — ONDAN ÖNCE yapılmış TÜM meşru kurulumlarda kayıt `Missing`
/// olur ve model verisi de vardır. Sonuç: o kullanıcılarda "Onar" düğmesi tamamen çalışmaz hale
/// gelmişti. Kayıt yoksa profiller diskten güvenle çıkarılabilir; `Corrupt` (dosya var ama
/// bozuk) ise gerçekten belirsizdir ve hata vermek doğrudur.
/// `ai_models/ai_hub/<modül>` → PROFİL ADI ters eşlemesi.
///
/// ⚠️ DENETİM 2026-08-28 (bulgu #06 — ÖLÇÜLDÜ): profil zip'leri `ai_models/ai_hub/<modül>/...`
/// düzeniyle açılır (`build_tools/make_model_zip.py::dosyalari_topla` her girdiyi
/// `f"ai_models/{rel}"` yazar ve `rel` DAİMA `ai_hub/` ile başlar). Yayındaki `vet.zip`
/// merkezî dizininde birebir doğrulandı: `ai_models/vet/` diye bir girdi YOKTUR.
/// Yani `ai_models` altında tek bir dizin oluşur: `ai_hub`. Eski çıkarım o adı PROFİL sanıyor,
/// `repair()` de `UnknownProfile { profile: "ai_hub" }` ile İNDİRME BAŞLAMADAN düşüyordu:
/// kullanıcı "eski kurulum algılandı (1 profil)" ardından "'ai_hub' profili manifest'te yok"
/// görüyordu. 2026-08-04 P3 düzeltmesinin kapısı, fixture'ı `ai_models/home/` diye ELLE
/// uydurduğu için (üretimde hiç oluşmayan düzen) hata canlıyken yeşil kalıyordu.
///
/// ⚠️ SAĞDAKİ ADLAR MANİFEST ANAHTARIDIR (`models.home` / `models.vet` / `models.research`).
/// `research-2.zip` ayrı bir profil DEĞİL, `model_parts` parçasıdır → "research"e eşlenir.
///
/// Sürüklenme kapısı: `tests/test_profil_modul_haritasi.py` (kaynak = make_model_zip.py).
pub const PROFIL_MODULLERI: [(&str, &str); 18] = [
    ("cat_disease", "home"),
    ("cat_landmark", "home"),
    ("cat_segmentation", "home"),
    ("inference_cat_sound", "home"),
    ("cat_thermal", "vet"),
    ("em_kedi", "vet"),
    ("em_kedi_legacy", "vet"),
    ("em_petri", "research"),
    ("em_phantom", "research"),
    ("feline_reticulocytes", "research"),
    ("inference_em_fantom", "research"),
    ("inference_em_petri", "research"),
    ("inference_human_kidney_ct", "research"),
    // D4.27 (B-9.9): RNA açıklamasının PT ikizi araştırma paketinde (make_model_zip PROFILLER["research"]).
    ("inference_human_kidney_rna", "research"),
    ("inference_paper_dilek_hoca", "research"),
    ("inference_petri_dish", "research"),
    ("inference_renal_histopath_kmc", "research"),
    ("petri_dish", "research"),
];

/// Bir dizin adını profil adına çevir. `ai_hub` altındaki modül adları eşlemeden çözülür;
/// doğrudan profil adı olan dizinler (eski/elle kurulumlar) OLDUĞU GİBİ kabul edilir.
fn dizin_adini_profile_cevir(ad: &str) -> Option<String> {
    if matches!(ad, "home" | "vet" | "research") {
        return Some(ad.to_string());
    }
    PROFIL_MODULLERI
        .iter()
        .find(|(modul, _)| *modul == ad)
        .map(|(_, profil)| (*profil).to_string())
}

pub fn infer_profiles_from_disk(install_root: &Path) -> Vec<String> {
    let models = models_dir(install_root);

    // Gerçek sevk düzeni: `ai_models/ai_hub/<modül>/...`. Varsa modül adlarından profil çıkar.
    let ai_hub = models.join("ai_hub");
    let mut v: Vec<String> = if ai_hub.is_dir() {
        std::fs::read_dir(&ai_hub)
            .map(|rd| {
                rd.flatten()
                    .filter(|e| e.file_type().map(|t| t.is_dir()).unwrap_or(false))
                    .filter_map(|e| e.file_name().to_str().and_then(dizin_adini_profile_cevir))
                    .collect()
            })
            .unwrap_or_default()
    } else {
        Vec::new()
    };

    // Geriye uyum: doğrudan `ai_models/<profil>/` düzeni de kabul edilir (elle kurulum /
    // gelecekte düzen değişirse). Bilinmeyen adlar SESSİZCE ATILIR — eskiden buradan
    // manifest'te olmayan bir "profil" sızıp repair()'i düşürüyordu.
    if let Ok(rd) = std::fs::read_dir(&models) {
        for e in rd.flatten() {
            if !e.file_type().map(|t| t.is_dir()).unwrap_or(false) {
                continue;
            }
            if let Some(ad) = e.file_name().to_str() {
                if ad == "ai_hub" {
                    continue;
                }
                if let Some(p) = dizin_adini_profile_cevir(ad) {
                    v.push(p);
                }
            }
        }
    }

    v.sort();
    v.dedup();
    v
}

pub fn read_installed_profiles_detailed(install_root: &Path) -> ProfileRecord {
    match std::fs::read_to_string(installed_profiles_path(install_root)) {
        Err(_) => ProfileRecord::Missing,
        Ok(s) => match serde_json::from_str::<Vec<String>>(&s) {
            Ok(v) => ProfileRecord::Ok(v),
            Err(_) => ProfileRecord::Corrupt,
        },
    }
}

/// Diskte GERÇEKTEN model verisi var mı? Kayıt kayıp/bozukken "aslında profil kurulu muydu?"
/// sorusunun tek güvenilir cevabı budur.
pub fn has_model_data(install_root: &Path) -> bool {
    std::fs::read_dir(models_dir(install_root))
        .map(|mut d| d.next().is_some())
        .unwrap_or(false)
}

/// Yeni kurulan profilleri mevcut kayda EKLE (birleştir, tekilleştir, sırala). Best-effort.
pub fn add_installed_profiles(install_root: &Path, profiles: &[String]) {
    let mut set = read_installed_profiles(install_root);
    for p in profiles {
        if !set.iter().any(|x| x == p) {
            set.push(p.clone());
        }
    }
    set.sort();
    set.dedup();
    if let Ok(json) = serde_json::to_string(&set) {
        let _ = std::fs::write(installed_profiles_path(install_root), json);
    }
}

/// Kaldirilan profili kayittan DUSUR (denetim 2026-09-06, profil kaldirma).
///
/// `add_installed_profiles` ile AYNI bicim (sirali, tekil, kompakt JSON) — iki yol ayrisirsa
/// UI cipleri ile Onar farkli listeler gorur. Profil kayitta yoksa dosya yine de normalize
/// edilerek yazilir (idempotent). Best-effort: yazma hatasi yutulur, cagiran `read_installed_profiles`
/// ile sonucu dogrular.
pub fn remove_installed_profile(install_root: &Path, profile: &str) {
    let mut set = read_installed_profiles(install_root);
    set.retain(|x| x != profile);
    set.sort();
    set.dedup();
    if let Ok(json) = serde_json::to_string(&set) {
        let _ = std::fs::write(installed_profiles_path(install_root), json);
    }
}

/// Kaldirilan profilin `installed_packages.models` girdisini sil (denetim 2026-09-06).
///
/// Diger alanlar (`base`/`deps`/`app` ve kalan modeller) `write_installed_packages` ile AYNI
/// serilestirmeden gecer → dosya bayt-uyumlu kalir; `pending_updates` kalan profilleri eskisi gibi
/// kiyaslar. Girdi zaten yoksa dosyaya DOKUNULMAZ (gereksiz yazma yok).
pub fn remove_model_record(install_root: &Path, profile: &str) {
    let mut p = read_installed_packages(install_root);
    if p.models.remove(profile).is_some() {
        write_installed_packages(install_root, &p);
    }
}

/// Devam-eden kurulum kaydı: kurulum BAŞLARKEN seçilen profiller yazılır, BİTİNCE/İPTAL'de silinir.
/// Açılışta bu dosya varsa "kurulum yarım kaldı — devam et?" gösterilir (internet kesildi/laptop
/// kapandı → `.part` cache'te durur, Range ile kaldığı yerden sürer).
pub fn pending_path(install_root: &Path) -> PathBuf {
    install_root.join("pending_install.json")
}

pub fn write_pending(install_root: &Path, profiles: &[String]) {
    let _ = std::fs::create_dir_all(install_root);
    if let Ok(json) = serde_json::to_string(profiles) {
        let _ = std::fs::write(pending_path(install_root), json);
    }
}

pub fn read_pending(install_root: &Path) -> Vec<String> {
    std::fs::read_to_string(pending_path(install_root))
        .ok()
        .and_then(|s| serde_json::from_str::<Vec<String>>(&s).ok())
        .unwrap_or_default()
}

pub fn clear_pending(install_root: &Path) {
    let _ = std::fs::remove_file(pending_path(install_root));
}

/// Cache'teki yarım `.part` dosyalarını sil (İPTAL'de çağrılır → disk boşalt).
///
/// ⚠️ `koru`: silinMEYECEK `.part` dosyaları (DENETİM 2026-08-17). Cache PAYLAŞIMLIDIR — arka
/// plandaki ön-indirme AYNI dizine yazar. Sahipliği okumadan hepsini silmek, o an inen ≤1,4 GB'lık
/// güncellemeyi çöpe atıyordu ve kurtarılamıyordu (`disk::olu_onbellek_temizle` `.part`a dokunmaz;
/// Windows'ta `FILE_SHARE_DELETE` ile açıldığı için silme BAŞARILI olur, sonraki `rename` düşer).
/// Ölçülen sıra: `check_runtime_update` → `prefetch_runtime_update` → `discard_pending`, yani
/// "Kurulum yarım kaldı" sorusu ön-indirme BAŞLADIKTAN HEMEN SONRA çıkıyor.
/// Kural: "GÜNCEL PLANIN ihtiyaç duyduğu `.part` silinmez; gerisi silinir." Bu, sahipliği tahmin
/// etmeden doğru ayrımı yapar — ön-indirme tam olarak plan paketlerini indirir ve kurulu OLMAYAN
/// cihazda plan boştur, yani yarım kalan İLK kurulumun temizliği (asıl gerekçe) aynen korunur.
pub fn clear_partials(install_root: &Path, koru: &[std::path::PathBuf]) {
    let cache = cache_dir(install_root);
    if let Ok(entries) = std::fs::read_dir(&cache) {
        for e in entries.flatten() {
            let yol = e.path();
            // Yol biçimi farklarına (ayırıcı, UNC, kısa-ad) düşmemek için DOSYA ADI karşılaştırılır.
            if yol.extension().is_some_and(|x| x == "part")
                && !koru.iter().any(|k| k.file_name() == yol.file_name())
            {
                let _ = std::fs::remove_file(yol);
            }
        }
    }
}

/// Kurulu uygulamayı (runtime + ai_models + cache + kayıtlar) SİL. Hasta verisi AYRI dizinde
/// (`PEMF_GUI`, %APPDATA%) → buradan ETKİLENMEZ (KVKK/tıbbi: hasta DB'si kazara silinmez).
/// Not: backend çalışıyorsa exe kilitli olur → çağırandan ÖNCE süreç öldürülmeli (main.rs yapar).
pub fn remove_install(install_root: &Path) -> std::io::Result<()> {
    if install_root.exists() {
        std::fs::remove_dir_all(install_root)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// YLI-A3.k (L8d · S-E2I.4) ÖNCE-KIRMIZI: PEMF köküne bağlanan bir JUNCTION yedek hedefi olarak seçilirse yedek PEMF kökünün
    /// İÇİNE yazılır (kaldırma / tam temizlik onu da siler). Kural metin karşılaştırması yaptığı için junction'ı görmez. Veri dizini
    /// başka bir "sürücü" (Q:) verilir ki yalnız PEMF-kök kuralı ölçülsün. Her şey geçici dizinde.
    #[cfg(windows)]
    #[test]
    fn KRITIK_A3_yedek_hedefi_PEMF_kokune_BAGLANTI_ile_atlatilamaz() {
        let d = tempfile::tempdir().unwrap();
        let kok = d.path().join("PEMF_System");
        std::fs::create_dir_all(&kok).unwrap();
        let bag = d.path().join("baglanti");
        let c = std::process::Command::new("cmd").args(["/d", "/c", "mklink", "/J"]).arg(&bag).arg(&kok).output().unwrap();
        assert!(c.status.success() && bag.is_dir(), "junction kurulamadı: {c:?}");
        let r = yedek_hedefi_gecerli_mi(&bag, Path::new(r"Q:\veri\PEMF_GUI"), &[kok.clone()], "");
        let ic: Vec<_> = std::fs::read_dir(&kok).unwrap().flatten().map(|e| e.file_name()).collect();
        let _ = std::fs::remove_dir(&bag);
        eprintln!("A3OLC|L8d|junction|{r:?}|kok_icerigi={ic:?}");
        assert!(r.is_err(), "PEMF köküne bağlanan junction yedek hedefi KABUL edildi — yedek PEMF kökünün içine yazılır");
    }

    /// YLI-A3.k (L8d · S-E2I.4) ÖNCE-KIRMIZI (saf, ağa çıkmaz): bu makinenin yönetici paylaşımına giden başka yazımlar (127.0.0.0/8'in
    /// başka adresi, `127.1` kısaltması, sondaki noktalı `localhost.`) hasta verisiyle AYNI diski "başka sürücü" gösterir.
    #[test]
    fn KRITIK_A3_yedek_hedefi_YEREL_takma_adlarla_ayni_diski_atlatamaz() {
        if !cfg!(target_os = "windows") {
            return;
        }
        let veri = Path::new(r"C:\ProgramData\PEMF_System\PEMF_GUI");
        let mut kacan = Vec::new();
        for h in [r"\\127.0.0.2\C$\yedek", r"\\127.1\C$\yedek", r"\\localhost.\C$\yedek", r"\\KLINIK-PC.\C$\yedek"] {
            let y = yerel_yol(h, "KLINIK-PC");
            let ayni = ayni_birim(Path::new(&y), veri);
            eprintln!("A3OLC|L8d|takma|{h}|{y}|{ayni:?}");
            if ayni != Some(true) {
                kacan.push(h);
            }
        }
        assert!(kacan.is_empty(), "aynı diskteki yönetici paylaşımı 'başka sürücü' sayıldı: {kacan:?}");
    }

    /// LN L11 · S-I18N.13: testler GERÇEK ortamı OKUMAZ — eskiden `backend_env(...)` / `cozulmus_veri_dizini(std::env)` gerçek
    /// `PROGRAMDATA`'yı okuyup `C:\ProgramData\PEMF_System`'de dizin açıyor, sonda dosyası yazıyor, ilk seferde `icacls` koşuyordu
    /// (araç setinin sahte `PROGRAMDATA`'sı olmadan koşulamıyordu). Artık her test kendi geçici `PROGRAMDATA`'sıyla; başka değişken YOK.
    fn sahte_pd() -> (tempfile::TempDir, String) {
        let d = tempfile::tempdir().unwrap();
        let s = d.path().to_string_lossy().into_owned();
        (d, s)
    }

    fn yalniz_pd(pd: &str) -> impl Fn(&str) -> Option<String> + Copy + '_ {
        move |k| (k == "PROGRAMDATA").then(|| pd.to_string())
    }

    /// LN L11 · S-I18N.13 kapısı: bu test modülü GERÇEK süreç ortamını okuyan çağrı İÇERMEZ — ne ortamı kendisi okuyan
    /// `backend_env(…)` ne de `std::env::var…` (ortam HEP enjekte: `env_from` / `yalniz_pd`). Desenler `concat!` ile bölünür ki
    /// kapı kendi metnini yakalamasın; yorum satırları sayılmaz.
    #[test]
    fn KRITIK_L11_testler_gercek_ortami_OKUMAZ() {
        let src = include_str!("install.rs");
        let modul = &src[src.find(concat!("mod ", "tests {")).expect("test modülü yok")..];
        // YLI-A3.5: önek BAĞIMSIZ (`use std::env; env::var(…)` da gerçek ortamı okur).
        let desenler = [concat!("backend_env", "("), concat!("env::", "var("), concat!("env::", "var_os("), concat!("env::", "vars(")];
        let ihlal: Vec<&str> = modul
            .lines()
            .filter(|s| !s.trim_start().starts_with("//"))
            .filter(|s| desenler.iter().any(|d| s.contains(d)))
            .collect();
        assert!(ihlal.is_empty(), "test gerçek ortamı okuyor (gerçek ProgramData'ya yazar): {ihlal:#?}");
        // YLI-A3.5: kök yaratan install çağrısını GERÇEK ortamla yapan bir backend.rs testi de aynı sonuca varır (bu kapı yalnız
        // install.rs'yi tarıyordu; `PD_TUZAK=1` ölçümünde mutant tuzakta `PEMF_System` açtı).
        let bsrc = include_str!("backend.rs");
        let bmod = &bsrc[bsrc.find(concat!("mod ", "tests {")).expect("backend test modülü yok")..];
        let kok_yaratan = [concat!("cozulmus_veri_", "dizini("), concat!("backend_env", "("), concat!("backend_env", "_with(")];
        let bihlal: Vec<&str> = bmod
            .lines()
            .filter(|s| !s.trim_start().starts_with("//"))
            .filter(|s| kok_yaratan.iter().any(|d| s.contains(d)) && s.contains(concat!("env::", "var")))
            .collect();
        assert!(bihlal.is_empty(), "backend.rs testi kök yaratan çağrıyı GERÇEK ortamla yapıyor: {bihlal:#?}");
    }

    fn env_from<'a>(pairs: &'a [(&'a str, &'a str)]) -> impl Fn(&str) -> Option<String> + 'a {
        move |k| {
            pairs
                .iter()
                .find(|(kk, _)| *kk == k)
                .map(|(_, v)| (*v).to_string())
        }
    }

    /// LN L7 · D2.76: launcher'ın backend'e verdiği veri kökü kaydedilir ve geri okunur (Türkçe kullanıcı adlı yol bozulmadan —
    /// UTF-16LE); dosya yoksa / bozuksa `None`; geçici dosya artık bırakmaz.
    #[test]
    fn KRITIK_L7_veri_koku_KAYDEDILIR_ve_TURKCE_yol_bozulmadan_okunur() {
        let d = tempfile::tempdir().unwrap();
        assert_eq!(veri_kokunu_oku(d.path()), None);
        let kok = PathBuf::from(r"C:\Users\Çağlar Gürkan\AppData\Roaming\PEMF_GUI");
        veri_kokunu_kaydet(d.path(), &kok).unwrap();
        assert_eq!(veri_kokunu_oku(d.path()), Some(kok.clone()));
        let ham = std::fs::read(veri_koku_yolu(d.path())).unwrap();
        assert_eq!(&ham[..4], &[b'C', 0, b':', 0], "UTF-16LE BOM'suz değil (NSIS FileReadUTF16LE)");
        let girdiler: Vec<_> = std::fs::read_dir(d.path()).unwrap().map(|e| e.unwrap().file_name()).collect();
        assert_eq!(girdiler.len(), 1, "geçici dosya kaldı: {girdiler:?}");
        std::fs::write(veri_koku_yolu(d.path()), [0x41u8]).unwrap();
        assert_eq!(veri_kokunu_oku(d.path()), None, "tek baytlı bozuk dosya kök sayıldı");
    }

    /// LN L7 · D2.33 / D2.76: kaldırma diyaloğunun konumu — kayıtlı kök önce; kayıt yoksa makine-geneli kök VARSA o, yoksa
    /// `%APPDATA%\PEMF_GUI`; öteki aday diskte VARSA "diğer". Yan etkisiz (dizin yaratmaz). Sahte PROGRAMDATA / APPDATA.
    #[test]
    fn KRITIK_L7_kaldirma_veri_konumu_GERCEK_koku_ve_DIGER_adayi_soyler() {
        let ev = tempfile::tempdir().unwrap();
        let pd = ev.path().join("ProgramData");
        let ad = ev.path().join("AppData").join("Roaming");
        let kur = ev.path().join("kurulum");
        std::fs::create_dir_all(&kur).unwrap();
        let (pd_s, ad_s) = (pd.to_string_lossy().into_owned(), ad.to_string_lossy().into_owned());
        let env = [("PROGRAMDATA", pd_s.as_str()), ("APPDATA", ad_s.as_str())];
        let makine = pd.join("PEMF_System").join("PEMF_GUI");
        let kullanici = ad.join("PEMF_GUI");
        if cfg!(target_os = "windows") {
            // hiçbiri yok, kayıt yok → %APPDATA% (düşüş konumu); YAN ETKİSİZ
            assert_eq!(kaldirma_veri_konumu_with(&kur, env_from(&env), ev.path()), (kullanici.clone(), vec![]));
            assert!(!pd.exists(), "konum sorgusu ProgramData'da dizin yarattı");
            // makine kökü var → o; kullanıcı kökü de varsa "diğer"
            std::fs::create_dir_all(&makine).unwrap();
            assert_eq!(kaldirma_veri_konumu_with(&kur, env_from(&env), ev.path()), (makine.clone(), vec![]));
            std::fs::create_dir_all(&kullanici).unwrap();
            assert_eq!(kaldirma_veri_konumu_with(&kur, env_from(&env), ev.path()), (makine.clone(), vec![kullanici.clone()]));
            // kayıt (launcher makine köküne YAZAMADI → düşüş) birincildir
            veri_kokunu_kaydet(&kur, &kullanici).unwrap();
            assert_eq!(kaldirma_veri_konumu_with(&kur, env_from(&env), ev.path()), (kullanici.clone(), vec![makine.clone()]));
        }
    }

    #[test]
    fn model_koku_profil_zip_duzeniyle_esler() {
        // vet.zip icerigi: ai_models/ai_hub/em_kedi/X.onnx
        // find_installed_model("ai_hub/em_kedi/X.onnx") -> <kok>/ai_hub/em_kedi/X.onnx
        let root = Path::new("/opt/pemf");
        let models = models_dir(root);
        assert_eq!(models, Path::new("/opt/pemf/ai_models"));
        assert_eq!(
            models.join("ai_hub/em_kedi/X.onnx"),
            Path::new("/opt/pemf/ai_models/ai_hub/em_kedi/X.onnx")
        );
    }

    #[test]
    fn data_dir_override_her_platformda_oncelikli() {
        let got = app_data_dir_with(env_from(&[(ENV_DATA_DIR, "/srv/pemfdata")]), Path::new("/home/u"));
        assert_eq!(got, Path::new("/srv/pemfdata/PEMF_GUI"));
    }

    #[test]
    fn bos_override_yok_sayilir() {
        let got = app_data_dir_with(env_from(&[(ENV_DATA_DIR, "   ")]), Path::new("/home/u"));
        assert_ne!(got, Path::new("   /PEMF_GUI"));
        assert!(got.ends_with("PEMF_GUI"));
    }

    /// path_utils.py ile aynı dizini vermeli — yoksa yükseltmede veri "kaybolur".
    #[test]
    fn platform_kanonik_dizini_python_ile_ayni() {
        let home = Path::new("/home/u");
        let got = app_data_dir_with(env_from(&[]), home);
        if cfg!(target_os = "macos") {
            assert_eq!(got, home.join("Library/Application Support/PEMF_GUI"));
        } else if cfg!(target_os = "windows") {
            assert!(got.ends_with("PEMF_GUI"));
        } else {
            assert_eq!(got, home.join(".local/share/PEMF_GUI"));
        }
    }


    // ═════════════════════════════════════════════════════════════════════════════════════
    // MAKİNE-GENELİ VERİ KÖKÜ (2026-08-09 denetimi, Tier 1)
    //
    // ARIZA: launcher `PEMF_DATA_DIR` VERMİYORDU → backend `%APPDATA%\PEMF_GUI`e düşüyor, yani
    // hasta/seans/AI verisi WINDOWS KULLANICISINA ÖZEL oluyordu. Vardiyalı klinikte ikinci
    // hesapla açan veteriner "BOŞ KLİNİK" görüyor — kullanıcı açısından VERİ KAYBINDAN ayırt
    // edilemez. Servis-tabanlı dağıtım bunu zaten doğru yapıyordu (device.env).
    // ═════════════════════════════════════════════════════════════════════════════════════

    #[test]
    fn makine_veri_dizini_ProgramData_altinda() {
        let got = machine_data_dir(env_from(&[("PROGRAMDATA", r"C:\ProgramData")]));
        if cfg!(target_os = "windows") {
            assert_eq!(got.unwrap(), PathBuf::from(r"C:\ProgramData").join("PEMF_System"));
        } else {
            assert!(got.is_none(), "windows disinda makine-geneli kok kullanilmamali");
        }
    }

    #[test]
    fn PROGRAMDATA_yoksa_None() {
        assert!(machine_data_dir(env_from(&[])).is_none());
    }

    #[test]
    fn yazilabilirlik_gercekten_olculur() {
        let d = tempfile::tempdir().unwrap();
        assert!(dizin_yazilabilir_mi(&d.path().join("yeni")), "yazilabilir dizin reddedildi");
        // Sonda dosyası ARDINDA BIRAKILMAMALI (klinik klasöründe çöp).
        // Sonda adı benzersizdir (eşzamanlılık) → dizinde HİÇ kalıntı kalmamalı.
        let kalinti: Vec<_> = std::fs::read_dir(d.path().join("yeni")).unwrap().flatten().collect();
        assert!(kalinti.is_empty(), "sonda dosyasi ardinda birakildi: {kalinti:?}");
    }

    /// ⚠️ EN KRİTİK KAPI: yazılamayan bir yolu `PEMF_DATA_DIR` olarak vermek, backend'in tıbbi
    /// kayıt DB'sini açamamasına ve (2026-08-09 kapısı gereği) SEANS BAŞLATAMAMASINA yol açar —
    /// yani bu düzeltme, düzelttiği şeyden ağır bir arıza üretirdi.
    #[test]
    fn yazilamayan_yol_icin_None_doner() {
        // Var olmayan bir sürücü/geçersiz kök → create_dir_all da write da başarısız.
        let gecersiz = if cfg!(target_os = "windows") { r"\?\Q:\yok" } else { "/proc/olmaz/pemf" };
        assert!(!dizin_yazilabilir_mi(Path::new(gecersiz)));
        assert!(cozulmus_veri_dizini(env_from(&[("PROGRAMDATA", gecersiz)])).is_none(),
            "yazilamayan yol PEMF_DATA_DIR olarak verildi — backend DB'yi acamaz, seans BASLAMAZ");
    }

    #[test]
    fn backend_env_veri_kokunu_TASIR() {
        let (_pd, pds) = sahte_pd();
        let env = backend_env_with(yalniz_pd(&pds), Path::new("/opt/pemf"), 8000, "");
        if cfg!(target_os = "windows") {
            // (Sahte) ProgramData yazılabilir → değişken verilmiş OLMALI ve TAM o kök olmalı.
            assert!(env.contains_key(ENV_DATA_DIR),
                "PEMF_DATA_DIR verilmedi — ikinci Windows hesabi BOS KLINIK gorur");
            assert_eq!(Path::new(&env[ENV_DATA_DIR]), Path::new(&pds).join("PEMF_System"));
        }
    }


    // ═════════════════════════════════════════════════════════════════════════════════════
    // OFF-SITE YEDEK HEDEFİ (2026-08-09 denetimi, Tier 1)
    //
    // ARIZA: yedekler hasta verisiyle AYNI DİSKE alınıyordu → disk arızası/fidye yazılımında
    // veri VE yedek birlikte gidiyordu. Backend `PEMF_BACKUP_DIR` desteğini zaten taşıyordu
    // ama hiçbir yerde ayarlanmadığı için özellik sahada HİÇ çalışmadı.
    // ═════════════════════════════════════════════════════════════════════════════════════

    #[test]
    fn yedek_hedefi_kaydedilir_ve_okunur() {
        let d = tempfile::tempdir().unwrap();
        assert!(backup_dir_oku(d.path()).is_none(), "hedef yokken Some dondu");
        backup_dir_yaz(d.path(), r"E:\PEMF_Yedek").unwrap();
        assert_eq!(backup_dir_oku(d.path()).unwrap(), PathBuf::from(r"E:\PEMF_Yedek"));
        backup_dir_yaz(d.path(), "").unwrap();
        assert!(backup_dir_oku(d.path()).is_none(), "bos deger kaydi silmedi");
    }

    /// ⚠️ EN ÖNEMLİ KURAL: hedef veriyle aynı sürücüdeyse düzeltmenin AMACI ortadan kalkar ve
    /// operatör "off-site yedeğim var" sanır. Yanlış güvence, korumasızlıktan tehlikelidir.
    #[test]
    fn KRITIK_ayni_surucu_REDDEDILIR() {
        if !cfg!(target_os = "windows") { return; }
        let (d, h) = (tempfile::tempdir().unwrap(), tempfile::tempdir().unwrap());
        let veri = d.path();
        let r = yedek_hedefi_gecerli_mi(h.path(), veri, &[], "");
        assert!(r.is_err(), "ayni surucudeki hedef kabul edildi");
        assert!(r.unwrap_err().contains("AYNI"), "sebep kullaniciya anlasilir degil");
    }

    /// LN L8 · S-E2I.4: yolun yerel karşılığı — `\\?\` / `\\.\` önekleri ve bu makinenin yönetici paylaşımı (`\\localhost\C$`,
    /// `\\127.0.0.1\c$`, `\\<bilgisayar>\C$`, `\\?\UNC\…`) sürücü yoluna; gerçek başka makine / normal paylaşım AYNEN.
    #[test]
    fn KRITIK_L8_SE2I4_yerel_yol_ATLATMA_bicimlerini_cozer() {
        for (girdi, beklenen) in [
            (r"\\?\C:\Yedek", r"C:\Yedek"),
            (r"\\.\D:\Yedek", r"D:\Yedek"),
            (r"\\localhost\C$\ProgramData\PEMF_System\y", r"C:\ProgramData\PEMF_System\y"),
            (r"\\127.0.0.1\c$\y", r"C:\y"),
            (r"\\KLINIK-PC\C$\y", r"C:\y"),
            (r"\\?\UNC\localhost\C$\y", r"C:\y"),
            (r"//localhost/C$/y", r"C:\y"),
            (r"\\NAS\yedek\pemf", r"\\NAS\yedek\pemf"),
            (r"\\localhost\paylasim\y", r"\\localhost\paylasim\y"),
            (r"\\BASKA-PC\C$\y", r"\\BASKA-PC\C$\y"),
            (r"E:\Yedek", r"E:\Yedek"),
        ] {
            assert_eq!(yerel_yol(girdi, "klinik-pc"), beklenen, "{girdi}");
        }
    }

    /// LN L8 · S-E2I.4: yedek hedefi bir PEMF kökünün İÇİNDEYSE (kaldırma / tam temizlik onu da siler) RED — `\\?\` ve
    /// `\\localhost\C$` biçimleri de; ve `\\?\` önekli AYNI sürücü hedefi artık "başka sürücü" sayılmaz. Red, hedefe yazmadan ÖNCE.
    #[test]
    fn KRITIK_L8_SE2I4_yedek_hedefi_PEMF_KOKU_altinda_olamaz() {
        if !cfg!(target_os = "windows") {
            return;
        }
        // SAHTE kökler (geçici dizin): mutantlı kod red'i atlasa bile yazılabilirlik sondası GERÇEK ProgramData'ya gitmez
        // (ölçülen tuzak — ilk sürüm literal C:\ProgramData yolları kullanıyordu, iki mutant orada boş dizin yarattı; geri alındı).
        let d = tempfile::tempdir().unwrap();
        let pemf = d.path().join("ProgramData").join("PEMF_System");
        let kur = d.path().join("Local").join("PEMF Vet Client");
        let veri = d.path().join("veri").join("PEMF_GUI");
        let kokler = [pemf.clone(), kur.clone()];
        let mesaj = crate::dil::t("rust.yedek.pemfKokuAltinda");
        let ps = pemf.to_string_lossy().into_owned();
        let mut hedefler = vec![
            pemf.join("yedek_hic_yok"),
            pemf.clone(),
            PathBuf::from(format!(r"\\?\{}", pemf.join("yedek_hic_yok").display())),
            PathBuf::from(ps.to_uppercase()).join("y"),
            kur.join("backups"),
            veri.join("backups"),
        ];
        if let Some(r) = ps.strip_prefix("C:\\") {
            hedefler.push(PathBuf::from(format!(r"\\localhost\C$\{r}\y")));
        }
        for hedef in &hedefler {
            assert_eq!(yedek_hedefi_gecerli_mi(hedef, &veri, &kokler, "KLINIK-PC"), Err(mesaj.clone()), "{hedef:?}");
        }
        assert!(!pemf.exists() && !kur.exists() && !veri.exists(), "reddedilen hedefe dizin yaratıldı — red yazmadan ÖNCE değil");
        // `\\?\` önekli AYNI sürücü: eskiden ilk karakter '\' → "başka sürücü" sayılıp kabul ediliyordu.
        let (v, h) = (tempfile::tempdir().unwrap(), tempfile::tempdir().unwrap());
        let onekli = PathBuf::from(format!(r"\\?\{}", h.path().display()));
        assert_eq!(
            yedek_hedefi_gecerli_mi(&onekli, v.path(), &[], ""),
            Err(crate::dil::t("rust.yedek.ayniSurucu")),
            "önekli aynı sürücü hedefi kabul edildi"
        );
        let kok_disi = pemf_kokleri(
            |k| match k {
                "PROGRAMDATA" => Some(r"C:\ProgramData".to_string()),
                "APPDATA" => Some(r"C:\Users\vet\AppData\Roaming".to_string()),
                "LOCALAPPDATA" => Some(r"C:\Users\vet\AppData\Local".to_string()),
                _ => None,
            },
            Path::new(r"C:\Users\vet"),
            Path::new(r"C:\Users\vet\AppData\Local\PEMF Vet Client"),
        );
        for k in [r"C:\ProgramData\PEMF_System", r"C:\ProgramData\PEMF_GUI", r"C:\Users\vet\AppData\Roaming\PEMF_GUI", r"C:\Users\vet\AppData\Local\PEMF_System"] {
            assert!(kok_disi.contains(&PathBuf::from(k)), "PEMF kökü listede yok: {k} / {kok_disi:?}");
        }
    }

    #[test]
    fn yazilamayan_hedef_REDDEDILIR() {
        let gecersiz = if cfg!(target_os = "windows") { r"\?\Q:\yok" } else { "/proc/olmaz" };
        assert!(yedek_hedefi_gecerli_mi(Path::new(gecersiz), Path::new("/tmp"), &[], "").is_err());
    }

    #[test]
    fn ayni_birim_surucu_harfine_bakar() {
        if !cfg!(target_os = "windows") {
            assert_eq!(ayni_birim(Path::new("/a"), Path::new("/b")), None);
            return;
        }
        assert_eq!(ayni_birim(Path::new(r"C:\x"), Path::new(r"c:\y")), Some(true));
        assert_eq!(ayni_birim(Path::new(r"C:\x"), Path::new(r"E:\y")), Some(false));
    }

    #[test]
    fn backend_env_yedek_hedefini_TASIR() {
        let d = tempfile::tempdir().unwrap();
        let hedef = d.path().join("yedek");
        std::fs::create_dir_all(&hedef).unwrap();
        backup_dir_yaz(d.path(), &hedef.to_string_lossy()).unwrap();
        let (_pd, pds) = sahte_pd();
        let env = backend_env_with(yalniz_pd(&pds), d.path(), 8000, "");
        assert_eq!(Path::new(&env[ENV_BACKUP_DIR]), hedef,
            "yedek hedefi backend'e gecirilmedi — off-site kopya HIC alinmaz");
    }

    /// USB çıkarılmışsa değişken VERİLMEZ: backend her turda hataya düşüp günlüğü doldurmasın.
    #[test]
    fn erisilemez_hedef_backend_enve_GIRMEZ() {
        let d = tempfile::tempdir().unwrap();
        backup_dir_yaz(d.path(), r"\?\Q:\cikarilmis-usb").unwrap();
        let (_pd, pds) = sahte_pd();
        let env = backend_env_with(yalniz_pd(&pds), d.path(), 8000, "");
        assert!(!env.contains_key(ENV_BACKUP_DIR), "erisilemez hedef env'e girdi");
    }

    #[test]
    fn backend_env_model_kokunu_ve_portu_verir() {
        let (_pd, pds) = sahte_pd();
        let env = backend_env_with(yalniz_pd(&pds), Path::new("/opt/pemf"), 8123, "");
        // Platform-agnostik: Windows '\' vs POSIX '/' — Path karşılaştır (string değil).
        assert_eq!(Path::new(&env[ENV_MODELS_DIR]), Path::new("/opt/pemf").join("ai_models"));
        assert_eq!(env[ENV_API_PORT], "8123");
    }

    /// DENETİM P0 regresyonu: launcher backend'i kimlik doğrulaması KAPALI başlatmamalı.
    /// Backend `.env` dosyalarını okumaz; bu env verilmezse `apps/backend/servers/auth.py` varsayılanı "0"dır
    /// ve uzak/tünel erişimi kimliksiz açılır. LAN/localhost `is_local_request` ile muaf olduğu
    /// için bu bayrak yerel arayüzü bozmaz.
    #[test]
    fn backend_env_auth_zorunlulugunu_acik_verir() {
        let (_pd, pds) = sahte_pd();
        let env = backend_env_with(yalniz_pd(&pds), Path::new("/opt/pemf"), 8123, "");
        assert_eq!(env[ENV_REQUIRE_AUTH], "1");
    }

    /// ⚠️ KVKK SÖZLEŞMESİ (2026-08-08 denetim bulgusu) — BU TESTİ SİLMEYİN.
    ///
    /// `PEMF_ENCRYPT_AT_REST` bu haritada YOKTU. Servis kurulumu (`setup_services.ps1`) onu
    /// geçiriyordu, launcher geçirmiyordu → siteden indirip kuran HER klinik hasta verisini
    /// DÜZ METİN yazıyordu. Ölçüldü: bayraksız `atRestEncrypted=False`, bayrakla `True`.
    /// Site ise üç yerde "cihazda şifreli (SQLCipher)" diye beyan ediyor.
    ///
    /// Bu ayar bir daha SESSİZCE kaybolmasın: eksikliği testi düşürür.
    #[test]
    fn backend_env_at_rest_sifrelemeyi_ZORUNLU_kilar() {
        let (_pd, pds) = sahte_pd();
        let env = backend_env_with(yalniz_pd(&pds), Path::new("/opt/pemf"), 8123, "");
        assert_eq!(
            env.get(ENV_ENCRYPT_AT_REST).map(String::as_str),
            Some("1"),
            "at-rest şifreleme kapalı → hasta PII'si diske DÜZ METİN yazılır (KVKK) ve \
             sitedeki 'cihazda şifreli' beyanı yanlış olur"
        );
    }

    #[test]
    fn backend_env_UZAKTAN_ERISIMI_acar() {
        // ⚠️ SAHA BULGUSU 2026-08-12: bu satır olmadan tünel hiç başlamıyor, cihazın
        // `tunnel_url`i boş kalıyor ve mobil "kod/kimlikle eşleşen cihaz bulunamadı" diyor —
        // kod DOĞRU olduğu hâlde. Arayüz farklı-ağdan bağlanmayı açıkça vaat ediyor.
        // Güvenlik: backend tüneli açarken PEMF_REQUIRE_AUTH'u ZORLA açar (fail-closed).
        let env = backend_env_with(|_| None, Path::new("/opt/pemf"), 8123, "");
        assert_eq!(
            env.get(ENV_ENABLE_TUNNEL).map(String::as_str),
            Some("1"),
            "uzaktan erişim kapalı → farklı ağdan bağlanma ÇALIŞMAZ ve mobil kullanıcıya              yanlışlıkla 'kod hatalı' dedirtir"
        );
    }

    /// Y234 · S-BE.3: backend açılışta PEMF-Gateway'i profilden BAĞIMSIZ açıyordu → yalnız terapisiz (`home`) kurulumda `PEMF_HOTSPOT=0`.
    #[test]
    fn KRITIK_Y234_yalniz_ev_profilinde_backend_HOTSPOT_kapali_baslar() {
        let (_pd, pds) = sahte_pd();
        let d = tempfile::tempdir().unwrap();
        std::fs::write(installed_profiles_path(d.path()), r#"["home"]"#).unwrap();
        let env = backend_env_with(yalniz_pd(&pds), d.path(), 8000, "");
        assert_eq!(
            env.get(ENV_HOTSPOT).map(String::as_str),
            Some("0"),
            "yalniz Ev Sahibi kurulu makinede backend PEMF-Gateway hotspot'unu ACMAMALI"
        );
    }

    /// Y234: terapi profili varsa ya da profil kaydı okunamıyorsa değişken VERİLMEZ (backend varsayılanı = bugünkü davranış) —
    /// klinikte telefon PEMF-Gateway'e bağlanır; okunamayan kayıt yüzünden AP kapanırsa telefon cihazdan kopar.
    #[test]
    fn KRITIK_Y234_terapi_profilinde_ya_da_kayit_okunamazsa_HOTSPOT_degiskeni_VERILMEZ() {
        let (_pd, pds) = sahte_pd();
        let haller: [(Option<&str>, &str); 6] = [
            (Some(r#"["vet"]"#), "vet"),
            (Some(r#"["research"]"#), "research"),
            (Some(r#"["home","vet"]"#), "home+vet"),
            (Some("[]"), "bos kayit"),
            (Some("{bozuk-json"), "bozuk kayit"),
            (None, "kayit yok"),
        ];
        for (icerik, ad) in haller {
            let d = tempfile::tempdir().unwrap();
            if let Some(i) = icerik {
                std::fs::write(installed_profiles_path(d.path()), i).unwrap();
            }
            let env = backend_env_with(yalniz_pd(&pds), d.path(), 8000, "");
            assert!(
                !env.contains_key(ENV_HOTSPOT),
                "{ad}: PEMF_HOTSPOT={:?} verildi — klinikte telefon PEMF-Gateway'e baglanamaz",
                env.get(ENV_HOTSPOT)
            );
        }
    }

    /// Y234 çıkış kapısı: operatörün tanımladığı değer AYNEN geçer (yalnız-home kurulumda da "1" ezilmez).
    #[test]
    fn Y234_ortamdaki_HOTSPOT_degeri_AYNEN_gecer() {
        let (_pd, pds) = sahte_pd();
        let pdr: &str = &pds;
        let getenv = move |k: &str| match k {
            "PROGRAMDATA" => Some(pdr.to_string()),
            ENV_HOTSPOT => Some("1".to_string()),
            _ => None,
        };
        let d = tempfile::tempdir().unwrap();
        std::fs::write(installed_profiles_path(d.path()), r#"["home"]"#).unwrap();
        let env = backend_env_with(getenv, d.path(), 8000, "");
        assert_eq!(
            env.get(ENV_HOTSPOT).map(String::as_str),
            Some("1"),
            "operatorun PEMF_HOTSPOT degeri EZILDI"
        );
    }

    #[test]
    fn backend_env_STM_PORT_OTO_ALGILAMAYI_acar() {
        // ⚠️ DENETİM 2026-08-17: bu satır olmadan backend sabit `COM10`a düşüyordu
        // (`apps/backend/utils/stm32_transport.py`: oto-algılama YALNIZ `auto` ile açılır). ST-Link'in COM
        // numarası Windows USB numaralandırmasına göre değişir → klinikte COM10 değilse
        // **bobin 1-5 hiç bağlanmıyordu**, ESP 6-8 çalıştığı için cihaz "yarı çalışıyor" görünüyordu.
        let env = backend_env_with(|_| None, Path::new("/opt/pemf"), 8123, "");
        assert_eq!(
            env.get(ENV_STM_PORT).map(String::as_str),
            Some("auto"),
            "STM portu oto-algılaması kapalı → ST-Link COM10 değilse bobin 1-5 HİÇ bağlanmaz \
             (cihaz yarı çalışır ve sebebi arayüzde yazmaz)"
        );
    }

    #[test]
    fn backend_env_REBIND_KORUMASINI_ACAR() {
        // Varsayilan "auto" — koruma launcher kurulumlarinda fiilen devrede.
        let env = backend_env_with(|_| None, Path::new("/opt/pemf"), 8123, "n");
        assert_eq!(env.get(ENV_ALLOWED_HOSTS).map(String::as_str), Some("auto"));
    }

    #[test]
    fn backend_env_ORTAMDAKI_ALLOWED_HOSTS_tercihine_dokunmaz() {
        // Cikis kapisi: operator "*" ile kapatabilir ya da ek ad verebilir.
        let env = backend_env_with(
            |k| (k == ENV_ALLOWED_HOSTS).then(|| "auto,klinik.sirket.com".to_string()),
            Path::new("/opt/pemf"),
            8123,
            "n",
        );
        assert_eq!(
            env.get(ENV_ALLOWED_HOSTS).map(String::as_str),
            Some("auto,klinik.sirket.com")
        );
    }

    #[test]
    fn backend_env_ORTAMDAKI_STM_PORT_tercihine_dokunmaz() {
        // Çıkış kapısı: sahada portu sabitlemek gerekebilir (`PEMF_STM_PORT=COM7`) ya da STM
        // simülatörü kullanılabilir (`socket://127.0.0.1:5100`). Ortam ENJEKTE edilir.
        let env = backend_env_with(
            |k| (k == ENV_STM_PORT).then(|| "COM7".to_string()),
            Path::new("/opt/pemf"),
            8123,
            "",
        );
        assert_eq!(
            env.get(ENV_STM_PORT).map(String::as_str),
            Some("COM7"),
            "operatörün sabitlediği port EZİLDİ — çıkış kapısı çalışmıyor"
        );
    }

    #[test]
    fn backend_env_ORTAMDAKI_tunel_tercihine_dokunmaz() {
        // Çıkış kapısı: internete açılmaması gereken kurulum `PEMF_ENABLE_TUNNEL=0` diyebilmeli.
        // Ortam ENJEKTE edilir → global duruma dokunulmaz, paralel testler birbirini ezmez.
        let env = backend_env_with(
            |k| (k == ENV_ENABLE_TUNNEL).then(|| "0".to_string()),
            Path::new("/opt/pemf"),
            8123,
            "",
        );
        assert_eq!(
            env.get(ENV_ENABLE_TUNNEL).map(String::as_str),
            Some("0"),
            "operatörün açık tercihi EZİLDİ — kapatma yolu kalmadı"
        );
    }

    /// Backend'e giden değişken kümesi BİLİNÇLİ olmalı: yeni bir değişken sessizce eklenirse
    /// (ya da biri düşerse) bu test düşer ve karar gözden geçirilir.
    #[test]
    fn backend_env_kumesi_bilincli_kalir() {
        let (_pd, pds) = sahte_pd();
        let env = backend_env_with(yalniz_pd(&pds), Path::new("/opt/pemf"), 8123, "nonce123");
        let mut anahtarlar: Vec<&str> = env.keys().map(String::as_str).collect();
        anahtarlar.sort();
        // ⚠️ `ENV_DATA_DIR` KOŞULLUDUR: yalnız makine-geneli kök YAZILABİLİRSE eklenir (Windows'ta
        // ProgramData; başka platformda ya da yazılamıyorsa hiç eklenmez — bkz. cozulmus_veri_dizini).
        // Bu yüzden beklenen küme çalışma ortamına göre değişir; koşulu AÇIKÇA modelliyoruz ki
        // "bilinçli küme" kapısı hem Windows'ta hem CI'nın Linux koşusunda anlamlı kalsın.
        let mut beklenen = vec![
            ENV_MODELS_DIR,
            ENV_API_PORT,
            ENV_ENCRYPT_AT_REST,
            // UZAKTAN ERİŞİM (2026-08-12): launcher bunu geçirmediği için siteden kuran hiçbir
            // klinik farklı ağdan bağlanamıyordu; arayüz bunu vaat ediyordu. KOŞULSUZ eklenir.
            ENV_ENABLE_TUNNEL,
            ENV_HEALTH_NONCE,
            ENV_REQUIRE_AUTH,
            // FİLO ENVANTERİ (2026-08-09, Tier 2): backend bunları bulut cihaz kaydına yazar.
            // Bir bobin-güvenliği hatası bulunduğunda "hangi klinik hangi sürümde?" sorusunun
            // cevabı yoktu; `rollout: 0` yalnız YENİ kurulumları durdurur. KOŞULSUZ eklenir.
            ENV_LAUNCHER_VERSION,
            // STM32 PORT OTO-ALGILAMASI (2026-08-17 denetimi): bu satır olmadan launcher ile kuran
            // her klinikte backend sabit COM10'u deniyor ve ST-Link başka COM'daysa bobin 1-5 HİÇ
            // bağlanmıyordu. KOŞULSUZ eklenir; ortamdaki değer korunur (bkz. ENV_STM_PORT).
            ENV_STM_PORT,
            // DNS-REBINDING KORUMASI (2026-08-22): bu satır olmadan Host koruması launcher
            // kurulumlarında ÖLÜydü. KOŞULSUZ eklenir; ortamdaki değer korunur.
            ENV_ALLOWED_HOSTS,
            // ARAŞTIRMA AI PRO SÜRÜŞÜ (2026-09-09): device.env bayrağı tanımlıyordu ama launcher
            // geçirmiyordu → operatör tezgâh sonrası "açtım" sanıp açamıyordu. KOŞULSUZ eklenir;
            // varsayılan "0" backend'in fail-safe'iyle AYNI, ortamdaki değer korunur.
            ENV_ARASTIRMA_AIPRO,
            // JETON KAPISI (2026-09-13): `apps/backend/servers/jeton.py` hazırdı ve `ai_router`a bağlıydı ama
            // launcher bayrağı geçirmiyordu → makinede `PEMF_JETON_ENFORCED=1` yazılsa bile
            // launcher'dan açılan backend görmüyordu (jeton HİÇ düşmüyordu). KOŞULSUZ eklenir;
            // varsayılan "0" = bugünkü canlı davranış (satış açılmadı, modül tam no-op),
            // ortamdaki değer korunur.
            ENV_JETON_ENFORCED,
            // DÜZ-METİN YEDEK EMANETİ (2026-09-15): `deploy/device.env` bayrağı taşıyor ama
            // launcher geçirmiyordu → `device_env_anahtarlari_launcherda_KARSILIGINI_BULUR`
            // KIRMIZI döndü (CI koşusu 35002368710). Bu, "backend'de altyapı var, launcher
            // geçirmiyor" sınıfının SEKİZİNCİ örneğiydi. KOŞULSUZ eklenir; varsayılan "0" =
            // güvenli-sil (bugünkü canlı davranış), ortamdaki değer korunur.
            ENV_KEEP_PLAIN_BACKUP,
            // KEDİ AI PRO SÜRÜŞÜ TAŞIYICISI (LN L8 · S-AIK.6 · Y142): KOŞULSUZ; varsayılan "0" = KAPALI, ortamdaki değer korunur.
            ENV_KEDI_AIPRO_SURUS,
            // FANTOM AI PRO SÜRÜŞÜ TAŞIYICISI (D3 T-f · Y195): KOŞULSUZ; varsayılan "0" = KAPALI, ortamdaki değer korunur.
            ENV_ARASTIRMA_AIPRO_FANTOM,
        ];
        // SAKLAMA SÜRELERİ (LN L8 · S-F2-3.2 a): yalnız ortamda TANIMLIYSA geçer (varsayılan yazılmaz) — koşullu.
        // (LN L11: ortam sahte — saklama adları tanımsız, eklenmez.)
        // `ENV_BASE_SHA` yalnız KURULU bir paket varsa eklenir (ilk açılışta kurulum yok).
        if !read_installed_packages(Path::new("/opt/pemf")).app.is_empty()
            || !read_installed_packages(Path::new("/opt/pemf")).base.is_empty()
        {
            beklenen.push(ENV_BASE_SHA);
        }
        if cozulmus_veri_dizini(yalniz_pd(&pds)).is_some() {
            beklenen.push(ENV_DATA_DIR);
        }
        // Y96 (LN L8): paylaşılan yerel grup — sahte ortamda tanımsız (L11), eklenmez.
        assert_eq!(
            anahtarlar,
            beklenen
            .into_iter()
            .collect::<std::collections::BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>(),
            "backend'e giden ortam değişkeni kümesi değişti — bilinçli mi?"
        );
    }

    /// YAYIN 2026-11-03 (`buildId` bulgusu): sağlık kapısının verdiği kimlik kayıttakinin ÜZERİNE yazılır, başka anahtara
    /// dokunmaz; yok / boş / yalnız boşluk = kayıttaki AYNEN; kayıt yokken (ilk kurulum) kimlik EKLENİR.
    #[test]
    fn paket_kimligini_uygula_KAPI_kimligi_kaydi_ezer_bos_ezmez() {
        let mut env = BTreeMap::new();
        env.insert(ENV_BASE_SHA.to_string(), "cb33f48382a2".to_string());
        env.insert(ENV_API_PORT.to_string(), "8000".to_string());
        let yeni = paket_kimligini_uygula(env.clone(), Some("d8b0fea4bfaf"));
        assert_eq!(yeni.get(ENV_BASE_SHA).map(String::as_str), Some("d8b0fea4bfaf"), "kapı kimliği uygulanmadı");
        assert_eq!(yeni.get(ENV_API_PORT).map(String::as_str), Some("8000"), "başka anahtar değişti");
        assert_eq!(yeni.len(), env.len());
        for k in [None, Some(""), Some("   ")] {
            assert_eq!(paket_kimligini_uygula(env.clone(), k), env, "{k:?} kaydı ezdi");
        }
        let ilk = paket_kimligini_uygula(BTreeMap::new(), Some(" abc "));
        assert_eq!(ilk.get(ENV_BASE_SHA).map(String::as_str), Some("abc"));
    }

    /// LN L8 · Y96 (sahip): veri kökünün ACL'i yalnız PAYLAŞILAN YEREL gruba `Değiştir` verir; yerel `Users` (S-1-5-32-545) HİÇBİR
    /// yolda verilmez (eskiden bu makinedeki her hesap hasta veri köküne yazabiliyordu); grup yoksa ek hak YOK (yaratan hesap sahip).
    #[test]
    fn KRITIK_L8_Y96_veri_koku_ACL_yalniz_PAYLASILAN_GRUBA_Users_DISARIDA() {
        assert_eq!(veri_koku_acl_argumanlari(None), None, "grup yokken ek hak verildi");
        let g = "S-1-5-21-111-222-333-1005";
        let a = veri_koku_acl_argumanlari(Some(g)).expect("grup ACL'i yok");
        assert!(a.iter().any(|x| x == "*S-1-5-21-111-222-333-1005:(OI)(CI)M"), "{a:?}");
        assert!(!a.iter().any(|x| x.contains("S-1-5-32-545")), "Users ACL'de: {a:?}");
        // Y202a: karar `veri_koku_acl_komutu`nda (davranış kapıları aşağıda); Windows `acl_ver` YALNIZ onun argümanlarını koşar —
        // kendi yolunu (`.arg(dir)` = kök) eklemez.
        let src = include_str!("install.rs").replace("\r\n", "\n");
        let acl = &src[src.find("fn acl_ver(dir: &Path, grup: Option<&str>)").expect("acl_ver yok")..];
        let acl = &acl[..acl.find("\n#[cfg(not(windows))]").unwrap()];
        assert!(
            acl.contains("acl_ver_ile(dir, grup, |arg|") && acl.contains(".args(arg)") && !acl.contains(".arg(") && !acl.contains("S-1-5-32-545"),
            "acl_ver kararı veri_koku_acl_komutu'ndan almıyor ya da icacls'a kendi yolunu ekliyor"
        );
        // Tur 2 kolu (D67 çürütme, mutant n1): satır yorumları SOYULUR — çağrının metni yalnız bir yorumda kalıp kök `icacls`'a başka
        // biçimde (`.args([dir…])`) eklenirse de yakalanır: kodda `dir` yalnız imzada + `acl_ver_ile` çağrısında, tek komut çağrısı.
        let kod: String = acl.lines().map(|l| l.split("//").next().unwrap_or("")).collect::<Vec<_>>().join("\n");
        assert!(kod.contains("acl_ver_ile(dir, grup, |arg|"), "acl_ver_ile çağrısı yalnız yorumda: {kod}");
        assert_eq!(kod.matches("dir").count(), 2, "acl_ver kök yolunu (dir) acl_ver_ile dışında kullanıyor: {kod}");
        assert_eq!(kod.matches("gizli_komut(").count(), 1, "acl_ver birden çok komut koşuyor: {kod}");
        let komut = &src[src.find("pub fn veri_koku_acl_komutu(").expect("veri_koku_acl_komutu yok")..];
        let komut = &komut[..komut.find("fn acl_ver_ile").expect("acl_ver_ile yok")];
        assert!(komut.contains("veri_koku_acl_argumanlari(grup)?"), "komut ACE'i saf fonksiyondan almıyor");
    }

    /// Y202 (S-D3I.4, sahip) ÖNCE-KIRMIZI: yeni makine kökünde paylaşılan grubun hakkı YALNIZ `<kök>\PEMF_GUI` ağacına (`/T` yalnız
    /// ona; T-g `kurma_betigi` ile aynı hedef); kökün kendisi ve kardeşleri (mosquitto, logs, kimlik dosyaları) gruba AÇILMAZ — eskiden
    /// `icacls <kök> … /T`. Gerçek `icacls` ÇALIŞMAZ: enjekte koşucu argümanları kaydeder; her şey geçici dizinde.
    #[test]
    fn KRITIK_Y202a_grup_hakki_YALNIZ_PEMF_GUI_agacina_kok_DISARIDA() {
        let d = tempfile::tempdir().unwrap();
        let kok = d.path().join("PEMF_System");
        std::fs::create_dir_all(kok.join("mosquitto")).unwrap();
        let gui = kok.join("PEMF_GUI");
        let mut kayit: Vec<Vec<std::ffi::OsString>> = Vec::new();
        acl_ver_ile(&kok, Some("S-1-5-21-111-222-333-1005"), |a| kayit.push(a));
        assert_eq!(kayit.len(), 1, "grup varken icacls çağrılmadı: {kayit:?}");
        let a: Vec<String> = kayit[0].iter().map(|x| x.to_string_lossy().into_owned()).collect();
        assert_eq!(Path::new(&kayit[0][0]), gui.as_path(), "icacls hedefi PEMF_GUI değil (kök / kardeşler gruba açılır): {a:?}");
        assert_eq!(
            &a[1..],
            &["/grant", "*S-1-5-21-111-222-333-1005:(OI)(CI)M", "/T", "/C", "/Q"],
            "icacls'a PEMF_GUI dışında yol ya da beklenmeyen argüman gitti: {a:?}"
        );
        assert!(gui.is_dir(), "PEMF_GUI yaratılmadı — hakkın yazılacağı dizin yok");
        assert_eq!(veri_koku_acl_komutu(&kok, Some("S-1-5-21-111-222-333-1005")), Some(kayit[0].clone()), "ikinci tur farklı komut");
    }

    /// Y202: grup YOKKEN (tek hesaplı kurulum) bugünkü gibi — ne `icacls` ne `PEMF_GUI` (onu backend kurar).
    #[test]
    fn Y202a_grup_YOKKEN_komut_yok_PEMF_GUI_yaratilmaz() {
        let d = tempfile::tempdir().unwrap();
        let kok = d.path().join("PEMF_System");
        std::fs::create_dir_all(&kok).unwrap();
        let mut n = 0;
        acl_ver_ile(&kok, None, |_| n += 1);
        assert_eq!(n, 0, "grup yokken icacls çağrıldı");
        assert!(!kok.join("PEMF_GUI").exists(), "grup yokken PEMF_GUI yaratıldı — tek hesaplı kurulumun davranışı değişti");
        assert_eq!(veri_koku_acl_komutu(&kok, None), None, "grup yokken komut üretildi");
    }

    /// Tur 2 kolu (D67 çürütme, mutant n2): hedef ağacında OKUNAMAYAN girdi bağ SAYILIR (hak yazılmaz) — gerçek ACL değiştirilemediğinden
    /// okunamazlık, kök varken var olmayan `PEMF_GUI` ile ölçülür; kök yokken de komut yok.
    #[test]
    fn Y202a_hedef_OKUNAMAZSA_komut_yok_okunamayan_girdi_BAG_sayilir() {
        let d = tempfile::tempdir().unwrap();
        let kok = d.path().join("PEMF_System");
        std::fs::create_dir_all(kok.join("mosquitto")).unwrap();
        let g = Some("S-1-5-21-111-222-333-1005");
        assert_eq!(veri_koku_acl_komutu(&kok, g), None, "PEMF_GUI okunamıyorken komut üretildi — okunamayan girdi bağ sayılmalı");
        assert_eq!(veri_koku_acl_komutu(&d.path().join("yok"), g), None, "kök yokken komut üretildi");
    }

    /// Y202 (T-g bağ denetimi deseni) ÖNCE-KIRMIZI: hedef ağacında BAĞ varsa — `PEMF_GUI`'nin kendisi bağlantı noktası, içinde bağlantı
    /// noktası, içinde sabit bağlı dosya ya da kökün kendisi bağlantı noktası — hak YAZILMAZ (`icacls /T` bağın HEDEFİNE, hesabın başka
    /// bir klasörüne grup hakkı yazardı). KARŞIT: içinde sıradan klasör / dosya varken hak yazılır. Bağlantı noktası `mklink /J`
    /// (yönetici gerektirmez); her şey geçici dizinde, gerçek `icacls` ÇALIŞMAZ.
    #[cfg(windows)]
    #[test]
    fn KRITIK_Y202a_hedef_agacinda_BAG_varsa_hak_YAZILMAZ() {
        fn junction(bag: &Path, hedef: &Path) {
            let c = std::process::Command::new("cmd").args(["/d", "/c", "mklink", "/J"]).arg(bag).arg(hedef).output().unwrap();
            assert!(c.status.success() && bag.is_dir(), "junction kurulamadı: {c:?}");
        }
        let d = tempfile::tempdir().unwrap();
        let dis = d.path().join("hesabin_baska_klasoru");
        std::fs::create_dir_all(&dis).unwrap();
        std::fs::write(dis.join("ozel.txt"), b"x").unwrap();
        let kok = |ad: &str| {
            let k = d.path().join(ad);
            std::fs::create_dir_all(k.join("PEMF_GUI").join("alt")).unwrap();
            k
        };
        let k1 = d.path().join("gui_bag");
        std::fs::create_dir_all(&k1).unwrap();
        junction(&k1.join("PEMF_GUI"), &dis);
        let k2 = kok("icte_bag");
        junction(&k2.join("PEMF_GUI").join("alt").join("bag"), &dis);
        let k3 = kok("sabit_bag");
        std::fs::hard_link(dis.join("ozel.txt"), k3.join("PEMF_GUI").join("ozel.txt")).unwrap();
        let gercek = kok("gercek_kok");
        let k4 = d.path().join("kok_bag");
        junction(&k4, &gercek);
        let k5 = kok("karsit");
        std::fs::write(k5.join("PEMF_GUI").join("alt").join("dosya.txt"), b"x").unwrap();
        let mut sonuc = Vec::new();
        for (ad, k) in [("PEMF_GUI bağ", &k1), ("içte bağ", &k2), ("sabit bağ", &k3), ("kök bağ", &k4), ("KARŞIT sıradan", &k5)] {
            let mut n = 0;
            acl_ver_ile(k, Some("S-1-5-21-111-222-333-1005"), |_| n += 1);
            sonuc.push((ad, n));
        }
        for b in [k1.join("PEMF_GUI"), k2.join("PEMF_GUI").join("alt").join("bag"), k4.clone()] {
            let _ = std::fs::remove_dir(&b);
        }
        assert!(dis.join("ozel.txt").exists(), "aparat dış klasörü bozdu");
        assert_eq!(
            sonuc,
            [("PEMF_GUI bağ", 0), ("içte bağ", 0), ("sabit bağ", 0), ("kök bağ", 0), ("KARŞIT sıradan", 1)],
            "bağ varken hak yazıldı ya da sıradan ağaçta yazılmadı"
        );
    }

    /// LN L8 · Y96: grup SID'i biçim + bu makinenin YEREL grubu olmalı (backend `file_acl` ile aynı kural): Users / Authenticated Users
    /// / Everyone / Interactive biçim dışı; LookupAccountSid türü SidTypeAlias (4) ve etki alanı = bu bilgisayar değilse (kullanıcı
    /// hesabı, etki alanı grubu, makine "None" grubu) reddedilir; çözülemeyen (silinmiş) SID reddedilir; geçersiz grup backend'e GİTMEZ.
    #[test]
    fn KRITIK_L8_Y96_grup_SID_bicim_ve_YEREL_grup_kurali() {
        for (sid, ok) in [
            ("S-1-5-21-111-222-333-1005", true),
            ("S-1-5-32-545", false),
            ("S-1-5-11", false),
            ("S-1-1-0", false),
            ("S-1-5-4", false),
            ("S-1-5-21-111-222-333", false),
            ("S-1-5-21-111-222-333-1005-7", false),
            ("S-1-5-21-111-22x-333-1005", false),
            (" S-1-5-21-1-2-3-4", false),
        ] {
            assert_eq!(ozel_grup_sid_bicimi_mi(sid), ok, "{sid}");
        }
        assert!(yerel_grup_karari(4, "KLINIK-PC", "klinik-pc"));
        assert!(!yerel_grup_karari(1, "KLINIK-PC", "KLINIK-PC"), "kullanıcı hesabı grup sayıldı");
        assert!(!yerel_grup_karari(2, "KLINIK-PC", "KLINIK-PC"), "SidTypeGroup (makine 'None') yerel grup sayıldı");
        assert!(!yerel_grup_karari(4, "SIRKET", "KLINIK-PC"), "etki alanı grubu yerel sayıldı");
        assert!(!yerel_grup_karari(4, "", ""));
        assert_eq!(paylasilan_grup_sid(|_| None), None);
        assert_eq!(paylasilan_grup_sid(|k| (k == ENV_DATA_GROUP_SID).then(|| "S-1-5-32-545".to_string())), None);
        // Biçim tutar ama bu makinede YOK (RID 4294967295 kullanılmaz) → çözülemez → reddedilir (gerçek LookupAccountSid yolu).
        let yok = |k: &str| (k == ENV_DATA_GROUP_SID).then(|| "S-1-5-21-1-2-3-4294967295".to_string());
        assert_eq!(paylasilan_grup_sid(yok), None);
        assert!(!backend_env_with(yok, Path::new("/opt/pemf"), 8123, "").contains_key(ENV_DATA_GROUP_SID), "geçersiz grup backend'e geçti");
        // GERÇEK LookupAccountSid yolu çalışıyor: yerleşik Users (BUILTIN) bir YEREL GRUP türüdür ama etki alanı bu bilgisayar
        // DEĞİL → reddedilir ("false" bir başarısızlık değil, kararın kendisi).
        #[cfg(windows)]
        {
            let (tur, alan, bilgisayar) = hesap_turu_alani_bilgisayar("S-1-5-32-545").expect("Users SID çözülemedi — Lookup yolu bozuk");
            assert_eq!(tur, 4, "Users SidTypeAlias değil: {tur}");
            assert!(!alan.is_empty() && !alan.eq_ignore_ascii_case(&bilgisayar), "{alan} / {bilgisayar}");
            assert!(!bu_makinenin_yerel_grubu_mu("S-1-5-32-545"));
            assert_eq!(hesap_turu_alani_bilgisayar("S-1-5-21-1-2-3-4294967295"), None);
        }
    }

    /// D3 T-g (Y182) ÖNCE-KIRMIZI: `PEMF_DATA_GROUP_SID` YOKKEN launcher'ın kurduğu grup ADIYLA bulunur (aynı biçim + yerel grup
    /// kuralıyla); değişken VARSA yalnız o geçerlidir — geçersiz değerde ad aramasına SESSİZCE düşülmez.
    #[test]
    fn KRITIK_T_g_paylasilan_grup_ortam_YOKKEN_ADIYLA_bulunur() {
        let gecerli = "S-1-5-21-10-20-30-1009";
        let yok = |_: &str| None::<String>;
        assert_eq!(paylasilan_grup_sid_karari(yok, || Some(gecerli.to_string()), |_| true), Some(gecerli.to_string()));
        assert_eq!(paylasilan_grup_sid_karari(yok, || Some(gecerli.to_string()), |_| false), None, "yerel grup değil");
        assert_eq!(paylasilan_grup_sid_karari(yok, || Some("S-1-5-32-545".into()), |_| true), None, "Users ad aramasıyla geçti");
        assert_eq!(paylasilan_grup_sid_karari(yok, || None, |_| true), None);
        let bos = |k: &str| (k == ENV_DATA_GROUP_SID).then(|| "  ".to_string());
        assert_eq!(paylasilan_grup_sid_karari(bos, || Some(gecerli.to_string()), |_| true), Some(gecerli.to_string()));
        let aranan = std::cell::Cell::new(false);
        let kotu = |k: &str| (k == ENV_DATA_GROUP_SID).then(|| "S-1-5-32-545".to_string());
        let ara = || {
            aranan.set(true);
            Some(gecerli.to_string())
        };
        assert_eq!(paylasilan_grup_sid_karari(kotu, ara, |_| true), None);
        assert!(!aranan.get(), "geçersiz değişkende ad aramasına sessizce düşüldü");
        let acik = |k: &str| (k == ENV_DATA_GROUP_SID).then(|| " S-1-5-21-1-2-3-1100 ".to_string());
        assert_eq!(paylasilan_grup_sid_karari(acik, || Some(gecerli.to_string()), |_| true), Some("S-1-5-21-1-2-3-1100".to_string()));
    }

    /// LN L8 · S-AIK.6 (Y142 taşıyıcısı) + S-F2-3.2 (a): kedi sürüş bayrağı KOŞULSUZ geçer, varsayılan "0" (KAPALI), ortamdaki
    /// değer korunur; saklama adları YALNIZ tanımlıysa ve değeri AYNEN (boş da — backend'in "adım kapalı" anlamı) geçer, tanımsızken
    /// launcher varsayılan YAZMAZ (backend varsayılanları tek kaynak).
    #[test]
    fn KRITIK_L8_kedi_bayragi_TASINIR_saklama_adlari_YALNIZ_tanimliysa_aynen_gecer() {
        let bos = backend_env_with(|_| None, Path::new("/opt/pemf"), 8123, "");
        assert_eq!(bos[ENV_KEDI_AIPRO_SURUS], "0", "kedi sürüşü varsayılanı KAPALI değil (Y142)");
        assert!(ENV_SAKLAMA.iter().all(|a| !bos.contains_key(*a)), "tanımsız saklama adına launcher varsayılan yazdı");
        let ortam = [
            ("PEMF_KEDI_AIPRO_SURUS", "1"),
            ("PEMF_RETAIN_SENSOR_DAYS", "30"),
            ("PEMF_RETAIN_PII_DAYS", ""),
            ("PEMF_SENSOR_RETAIN_DAYS", "45"),
        ];
        let dolu = backend_env_with(
            |k| ortam.iter().find(|(a, _)| *a == k).map(|(_, v)| v.to_string()),
            Path::new("/opt/pemf"),
            8123,
            "",
        );
        assert_eq!(dolu[ENV_KEDI_AIPRO_SURUS], "1", "operatörün açtığı bayrak backend'e ulaşmıyor");
        assert_eq!(dolu["PEMF_RETAIN_SENSOR_DAYS"], "30");
        assert_eq!(dolu["PEMF_RETAIN_PII_DAYS"], "", "boş değer (backend: adım kapalı) değiştirildi");
        assert_eq!(dolu["PEMF_SENSOR_RETAIN_DAYS"], "45", "eski ad geçmiyor");
        assert!(!dolu.contains_key("PEMF_RETAIN_DOSE_DAYS"));
        assert_eq!(ENV_SAKLAMA.len(), 6);
    }

    /// ⚠️ EKSİKLİK KAPISI (denetim 2026-08-17) — yukarıdaki testin YAPAMADIĞI şey.
    ///
    /// `backend_env_kumesi_bilincli_kalir` kümeyi kilitler ama **DEĞİŞİKLİK** tespiti yapar: bir
    /// değişken *eklenirse* kırılır, *eksikse* sessiz kalır. Bu sınıf ÜÇ KEZ yaşandı ve üçünde de
    /// arıza yalnız SAHADA görüldü:
    ///   * `ENV_ENCRYPT_AT_REST` (2026-08-08) → klinikler hasta verisini DÜZ METİN yazıyordu,
    ///   * `ENV_ENABLE_TUNNEL`   (2026-08-12) → hiçbir klinik farklı ağdan bağlanamıyordu,
    ///   * `ENV_STM_PORT`        (2026-08-17) → ST-Link COM10 değilse **bobin 1-5 hiç bağlanmıyordu**
    ///     (ESP 6-8 MQTT'den çalıştığı için cihaz "yarı çalışıyor" görünüyordu).
    ///
    /// Ortak kök neden: `deploy/device.env` bir davranışı ayarlıyor, backend `.env` dosyalarını
    /// OTOMATİK YÜKLEMEZ (`load_dotenv` yok → `apps/backend/servers/api_server.py`'nin kendi notu), launcher da
    /// o değişkeni geçirmiyor. Servis yolu doğru, launcher yolu geride kalıyor.
    ///
    /// KAPI: `deploy/device.env`'deki HER etkin anahtar ya launcher tarafından GEÇİRİLMELİ ya da
    /// aşağıda GEREKÇESİYLE muaf tutulmalı. Yeni bir anahtar eklendiğinde bu test kırılır ve karar
    /// vermek ZORUNLU olur — "unutmak" artık sessiz bir seçenek değil.
    #[test]
    fn device_env_anahtarlari_launcherda_KARSILIGINI_BULUR() {
        let env_dosyasi = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .join("deploy")
            .join("device.env");
        let icerik = std::fs::read_to_string(&env_dosyasi)
            .unwrap_or_else(|e| panic!("deploy/device.env okunamadi ({:?}): {e}", env_dosyasi));

        // Etkin (yorumlanmamış) anahtarlar.
        let anahtarlar: Vec<String> = icerik
            .lines()
            .map(str::trim)
            .filter(|s| !s.is_empty() && !s.starts_with('#') && s.contains('='))
            .map(|s| s.split('=').next().unwrap().trim().to_string())
            .collect();
        assert!(
            anahtarlar.len() >= 10,
            "device.env ayristirilamadi (yalniz {} anahtar) — kapi anlamsiz kalir",
            anahtarlar.len()
        );

        let (_pd, pds) = sahte_pd();
        let env = backend_env_with(yalniz_pd(&pds), Path::new("/opt/pemf"), 8123, "nonce123");

        // ── MUAF: backend VARSAYILANI device.env ile AYNI sonucu veriyor ya da launcher yolunda
        //    kavram olarak karşılığı yok. Her satırın gerekçesi ZORUNLU.
        let muaf: &[(&str, &str)] = &[
            ("PEMF_HEADLESS", "frozen build ZATEN headless; GUI kaynagi silindi (pemf_gui olu)"),
            ("PEMF_API_HOST", "backend varsayilani 0.0.0.0 (backend_service.py) → launcher ETKILENMEZ"),
            (
                "PEMF_CORS_ORIGINS",
                "DENETIM P0 sonrasi backend varsayilani loopback+RFC1918+*.local ile SINIRLI \
                 (api_server.py) — cozum tam olarak 'launcher gecirmiyor' oldugu icin VARSAYILANI \
                 degistirmekti; ayrica test_security_hardening kilitliyor",
            ),
            ("PEMF_RATELIMIT_REMOTE_PER_MIN", "backend varsayilani 600 = device.env degeri"),
            (
                "PEMF_CLOUD_PATIENT_SYNC",
                "backend varsayilani '0' (KAPALI) = device.env degeri; \
                 test_kvkk_transfer_claims varsayilani kaynak duzeyinde kilitliyor",
            ),
            ("PEMF_DEVICE_NAME", "klinige ozgu etiket; launcher yolunda karsiligi yok (bulut kaydi ayri)"),
            (
                "PEMF_LOG_DIR",
                "backend gunluk yolunu PEMF_DATA_DIR'den turetir; launcher'in read_tail'i de AYNI \
                 ortamla cozer (2026-08-11 'yanlis gunluk' arizasinin duzeltmesi)",
            ),
        ];

        // ── KOŞULLU: gerçekten geçirilir ama ortama bağlı (Windows / operatör seçimi). CI'nin
        //    Linux koşusunda haritada bulunmazlar; yokluğu bir eksiklik DEĞİLDİR.
        let kosullu = [ENV_DATA_DIR, ENV_BACKUP_DIR];

        let mut eksik: Vec<String> = Vec::new();
        for a in &anahtarlar {
            if env.contains_key(a) {
                continue;
            }
            if muaf.iter().any(|(k, _)| k == a) {
                continue;
            }
            if kosullu.contains(&a.as_str()) {
                continue;
            }
            eksik.push(a.clone());
        }

        assert!(
            eksik.is_empty(),
            "deploy/device.env bu anahtarlari ayarliyor ama launcher backend'e GECIRMIYOR ve \
             muafiyet listesinde de yoklar: {eksik:?}\n\
             Bu, sahada UC KEZ yasanan hata sinifinin ta kendisi (bkz. testin docstring'i). \
             Ya `backend_env_with`e ekleyin ya da yukaridaki `muaf` listesine GEREKCESIYLE yazin."
        );
    }

    /// ⚠️ P2 (denetim 2026-08-04): migrasyon `install_root.exists()` ile erken donuyordu, ama
    /// `install_root` NSIS `$INSTDIR`'in TA KENDISI ve kurulum aninda olusturuluyor →
    /// migrasyon HIC calismiyordu ve yukseltmede ~2,6 GB payload YENIDEN INDIRILIYORDU.
    /// GERCEK senaryo: yeni kok VAR (icinde exe/uninstaller) ama PAYLOAD YOK.
    #[test]
    fn nsis_koku_varken_de_eski_payload_tasinir() {
        let d = tempfile::tempdir().unwrap();
        let parent = d.path();
        let yeni = parent.join("PEMF Vet Client");
        let eski = parent.join("PEMFVetClient");

        // NSIS'in yaptigi: kok + kendi dosyalari (payload YOK).
        std::fs::create_dir_all(&yeni).unwrap();
        std::fs::write(yeni.join("PEMFVetClient.exe"), b"yeni-exe").unwrap();
        std::fs::write(yeni.join("uninstall.exe"), b"unins").unwrap();

        // Eski kurulum: GERCEK payload.
        std::fs::create_dir_all(runtime_dir(&eski).join("PEMF_Backend")).unwrap();
        std::fs::write(runtime_dir(&eski).join("PEMF_Backend").join("x.dll"), b"payload").unwrap();
        std::fs::create_dir_all(models_dir(&eski).join("vet")).unwrap();
        std::fs::write(models_dir(&eski).join("vet").join("m.onnx"), b"model").unwrap();

        migrate_legacy_install_root(&yeni);

        assert!(runtime_dir(&yeni).join("PEMF_Backend").join("x.dll").exists(),
            "payload TASINMADI — kullanici ~2,6 GB'i yeniden indirir");
        assert!(has_model_data(&yeni), "ai_models tasinmadi");
        // Yeni kurulumun KENDI dosyalari EZILMEMELI.
        assert_eq!(std::fs::read(yeni.join("PEMFVetClient.exe")).unwrap(), b"yeni-exe",
            "yeni launcher exe'si eski dosyayla EZILDI");
    }

    /// Yeni kokte ZATEN payload varsa migrasyon calismamali (eskiyi uzerine yazmasin).
    #[test]
    fn yeni_kokte_payload_varsa_goc_yapilmaz() {
        let d = tempfile::tempdir().unwrap();
        let yeni = d.path().join("PEMF Vet Client");
        let eski = d.path().join("PEMFVetClient");
        std::fs::create_dir_all(runtime_dir(&yeni)).unwrap();
        std::fs::write(runtime_dir(&yeni).join("guncel.txt"), b"yeni").unwrap();
        std::fs::create_dir_all(runtime_dir(&eski)).unwrap();
        std::fs::write(runtime_dir(&eski).join("bayat.txt"), b"eski").unwrap();

        migrate_legacy_install_root(&yeni);

        assert!(runtime_dir(&yeni).join("guncel.txt").exists());
        assert!(!runtime_dir(&yeni).join("bayat.txt").exists(), "eski agac uzerine tasinmis");
        assert!(eski.exists(), "eski dizin gereksiz yere tuketilmis");
    }

    #[test]
    fn legacy_programdata_yalniz_windowsta() {
        let got = legacy_windows_models_dir(env_from(&[("PROGRAMDATA", "/c/ProgramData")]));
        if cfg!(target_os = "windows") {
            // Dizin gerçekten yoksa None döner; burada sadece platform dalını doğruluyoruz.
            assert!(got.is_none() || got.unwrap().ends_with("ai_models"));
        } else {
            assert!(got.is_none(), "windows disi platformda ProgramData kullanilmamali");
        }
    }

    /// DENETİM 2026-08-04 regresyonu: migrasyon YALNIZ kök yokken çalışır (erken-return).
    /// Bu yüzden ÇAĞRI SIRASI kritiktir: `write_pending` (create_dir_all yapar) migrasyondan
    /// ÖNCE koşarsa migrasyon SESSİZCE ölür ve eski `PEMFVetClient` kurulumundan yükseltenler
    /// ~2.6 GB payload'u (runtime + ai_models) HER yükseltmede yeniden indirir.
    #[test]
    fn legacy_kok_tasinir_ama_kok_varsa_no_op() {
        let dir = tempfile::tempdir().unwrap();
        let parent = dir.path();
        let legacy = parent.join("PEMFVetClient");
        let target = parent.join("PEMF Vet Client");
        std::fs::create_dir_all(legacy.join("runtime")).unwrap();
        std::fs::write(legacy.join("runtime").join("marker.txt"), b"payload").unwrap();

        // 1) Kök YOK → taşınır, payload korunur (yeniden indirme YOK).
        migrate_legacy_install_root(&target);
        assert!(
            target.join("runtime").join("marker.txt").exists(),
            "legacy payload tasinmadi — yukseltmede 2.6 GB yeniden inecek"
        );
        assert!(!legacy.exists(), "eski dizin yerinde kalmis");

        // 2) Hedefte ARTIK PAYLOAD VAR (1. adımda taşındı) → no-op.
        //    DENETİM 2026-08-04: ölçüt eskiden "kök dizini var mı" idi; bu, NSIS kökü her zaman
        //    oluşturduğu için migrasyonu tamamen öldürüyordu. Artık ölçüt YÜKÜN varlığı.
        std::fs::create_dir_all(legacy.join("runtime")).unwrap();
        std::fs::write(legacy.join("runtime").join("yeni.txt"), b"z").unwrap();
        migrate_legacy_install_root(&target); // target ARTIK var
        assert!(
            legacy.join("runtime").join("yeni.txt").exists(),
            "kok varken tasima YAPILMAMALI (erken-return bekleniyor)"
        );
    }

    /// DENETİM 2026-08-04 (P2 — SONSUZ DÖNGÜ): aynı hedef sürüm N kez denenip sürüm DEĞİŞMEZSE
    /// (manifest sürümü ↔ paketin gerçek sürümü ayrışması) otomatik kurulum DURMALI. Aksi halde
    /// launcher her açılışta indir-kur-yeniden başlat döngüsüne girer.
    #[test]
    fn selfupdate_ayni_surumu_sonsuz_denemez() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        assert!(selfupdate_auto_allowed(root, "1.9.9"), "hic denenmemisken izinli olmali");

        record_selfupdate_attempt(root, "1.9.9");
        assert_eq!(read_selfupdate_attempt(root), Some(("1.9.9".into(), 1)));
        assert!(selfupdate_auto_allowed(root, "1.9.9"), "1. denemeden sonra hala izinli");

        record_selfupdate_attempt(root, "1.9.9");
        assert_eq!(read_selfupdate_attempt(root), Some(("1.9.9".into(), 2)));
        assert!(
            !selfupdate_auto_allowed(root, "1.9.9"),
            "sinir dolunca OTOMATIK kurulum DURMALI (dongu kirilmali)"
        );

        // FARKLI bir hedef sürüm sayacı sıfırdan başlatır — yeni yayın yine denenebilmeli.
        assert!(selfupdate_auto_allowed(root, "2.0.0"));
        record_selfupdate_attempt(root, "2.0.0");
        assert_eq!(read_selfupdate_attempt(root), Some(("2.0.0".into(), 1)));

        // Güncelleme GERÇEKTEN uygulandıysa (çalışan sürüm hedefe ulaştı) kayıt temizlenir.
        clear_selfupdate_attempt(root);
        assert_eq!(read_selfupdate_attempt(root), None);
        assert!(selfupdate_auto_allowed(root, "2.0.0"));
    }

    /// DENETİM 2026-08-04: kayıt YOK / BOZUK / okundu birbirinden ayırt edilebilmeli — eski
    /// `read_installed_profiles` üçünü de "boş liste"ye indirgiyordu ve onarım sessizce
    /// model paketlerini atlayıp "Hazır" diyordu.
    #[test]
    fn profil_kaydi_durumu_ayirt_edilir() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();

        assert_eq!(read_installed_profiles_detailed(root), ProfileRecord::Missing);

        std::fs::write(installed_profiles_path(root), "{bozuk-json").unwrap();
        assert_eq!(read_installed_profiles_detailed(root), ProfileRecord::Corrupt);

        std::fs::write(installed_profiles_path(root), r#"["vet","research"]"#).unwrap();
        assert_eq!(
            read_installed_profiles_detailed(root),
            ProfileRecord::Ok(vec!["vet".into(), "research".into()])
        );

        // Boş liste GEÇERLİ bir kayıttır (gerçekten yalnız base kurulu) — Corrupt değil.
        std::fs::write(installed_profiles_path(root), "[]").unwrap();
        assert_eq!(read_installed_profiles_detailed(root), ProfileRecord::Ok(vec![]));
    }

    /// Kayıt kayıp/bozukken "aslında profil kurulu muydu?" sorusunun tek güvenilir cevabı disktir.
    #[test]
    fn model_verisi_varligi_dogru_tespit_edilir() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        assert!(!has_model_data(root), "ai_models yokken var denmemeli");

        std::fs::create_dir_all(models_dir(root)).unwrap();
        assert!(!has_model_data(root), "BOŞ ai_models dizini 'model var' sayılmamalı");

        std::fs::create_dir_all(models_dir(root).join("ai_hub")).unwrap();
        assert!(has_model_data(root));
    }

    #[test]
    fn backend_yolu_platforma_gore_uzanti_alir() {
        let p = backend_path(Path::new("/opt/pemf"));
        if cfg!(target_os = "windows") {
            assert!(p.ends_with("PEMF_Backend.exe"));
        } else {
            assert!(p.ends_with("PEMF_Backend"));
        }
        assert!(p.starts_with("/opt/pemf/runtime"));
    }
}


#[cfg(test)]
mod guncelleme_isareti_testleri {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static SAYAC: AtomicUsize = AtomicUsize::new(0);

    fn tmp() -> PathBuf {
        let d = std::env::temp_dir().join(format!(
            "pemf_gisaret_{}_{}",
            std::process::id(),
            SAYAC.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = std::fs::remove_dir_all(&d);
        d
    }

    #[test]
    fn yaz_oku_taze_temizle() {
        let d = tmp();
        assert!(guncelleme_isareti_oku(&d).is_none());
        assert!(!guncelleme_isareti_taze(&d, 120));
        guncelleme_isareti_yaz(&d, "1.9.44", "1.9.45");
        let (f, t, yas) = guncelleme_isareti_oku(&d).expect("işaret okunamadı");
        assert_eq!((f.as_str(), t.as_str()), ("1.9.44", "1.9.45"));
        assert!(yas <= 5, "yaş {yas}");
        assert!(guncelleme_isareti_taze(&d, 120));
        guncelleme_isaretini_temizle(&d);
        assert!(!guncelleme_isareti_taze(&d, 120));
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn eski_exe_karari() {
        let d = tmp();
        guncelleme_isareti_yaz(&d, "1.9.44", "1.9.45");
        // ESKİ exe (from), taze işaret → sessiz çıkış; işaret KALIR (pencere ona bakıyor).
        assert!(guncelleme_bosluguna_dusen_eski_exe_mi(&d, "1.9.44", 120));
        assert!(guncelleme_isareti_oku(&d).is_some(), "eski exe işareti silmemeli");
        // YENİ exe (to) → normal açılış + işaret temizlenir → pencere kapanır.
        assert!(!guncelleme_bosluguna_dusen_eski_exe_mi(&d, "1.9.45", 120));
        assert!(guncelleme_isareti_oku(&d).is_none(), "yeni exe işareti temizlemeli");
        // BAYAT işaret: eski exe bile olsa çıkmaz (kurulum başarısızsa uygulama yine açılmalı).
        let json = serde_json::json!({"from": "1.9.44", "to": "1.9.45", "started_unix": 1}).to_string();
        std::fs::write(d.join(GUNCELLEME_ISARETI_DOSYASI), json).unwrap();
        assert!(!guncelleme_bosluguna_dusen_eski_exe_mi(&d, "1.9.44", 120));
        assert!(guncelleme_isareti_oku(&d).is_none(), "bayat işaret temizlenmeli");
        // from == to (manifest yanlış) → ASLA kilitleme.
        guncelleme_isareti_yaz(&d, "1.9.45", "1.9.45");
        assert!(!guncelleme_bosluguna_dusen_eski_exe_mi(&d, "1.9.45", 120));
        // Bozuk JSON → işaret yok sayılır.
        std::fs::write(d.join(GUNCELLEME_ISARETI_DOSYASI), "{bozuk").unwrap();
        assert!(!guncelleme_bosluguna_dusen_eski_exe_mi(&d, "1.9.44", 120));
        let _ = std::fs::remove_dir_all(&d);
    }

    // ═══ KP-3 C · yarım kurulum kaydı, sağlık nonce desteği göstergesi, günlük yolu ═══
    /// Yarım kurulum kaydı: yazılan profiller AYNEN okunur ("kurulum yarım kaldı — devam et?"); silinince boş; bozuk / yok → boş.
    #[test]
    fn kp3_yarim_kurulum_kaydi_yaz_oku_sil_bozuk_bos() {
        let d = tempfile::tempdir().unwrap();
        let kok = d.path().join("kurulum");
        assert!(read_pending(&kok).is_empty());
        write_pending(&kok, &["vet".to_string(), "research".to_string()]);
        assert_eq!(pending_path(&kok), kok.join("pending_install.json"));
        assert_eq!(read_pending(&kok), vec!["vet".to_string(), "research".to_string()]);
        clear_pending(&kok);
        assert!(!pending_path(&kok).exists());
        assert!(read_pending(&kok).is_empty());
        std::fs::write(pending_path(&kok), "{bozuk").unwrap();
        assert!(read_pending(&kok).is_empty(), "bozuk kayıt profil listesi sayıldı");
    }

    /// `_internal/VERSION` varlığı = backend sağlık nonce'unu yansıtır (eski base.zip'te yok → hoşgörülü kip).
    #[test]
    fn kp3_saglik_nonce_destegi_version_dosyasindan_okunur() {
        let d = tempfile::tempdir().unwrap();
        assert!(!backend_supports_health_nonce(d.path()));
        let v = runtime_dir(d.path()).join("PEMF_Backend").join("_internal");
        std::fs::create_dir_all(&v).unwrap();
        assert!(!backend_supports_health_nonce(d.path()), "VERSION yokken destek var sayıldı");
        std::fs::write(v.join("VERSION"), "1.9.52").unwrap();
        assert!(backend_supports_health_nonce(d.path()));
    }

    /// Günlük yolu: `PEMF_LOG_DIR` (boşluk kırpılır) varsa o; boş / yoksa `<uygulama verisi>/logs`.
    #[test]
    fn kp3_backend_gunluk_yolu_ortam_dizini_once() {
        let ev = Path::new("/ev");
        let dizin = |k: &str| (k == ENV_LOG_DIR).then(|| "  /kayit/dizin  ".to_string());
        assert_eq!(backend_log_path_with(dizin, ev), PathBuf::from("/kayit/dizin").join("backend_service.log"));
        let bos = |k: &str| (k == ENV_LOG_DIR).then(|| "   ".to_string());
        assert_eq!(backend_log_path_with(bos, ev), app_data_dir_with(bos, ev).join("logs").join("backend_service.log"));
    }

    // ═══ KP-3 C (2. tur) · backend ortamı: kurulu paket kimliği (filo envanteri);  sarmalayıcısı L11 gereği test edilmez ═══
    /// Kurulu paket kimliği backend'e geçer (bulut cihaz kaydı "hangi klinik hangi sürümde"): katmanlıda `app` (bizim kodumuz),
    /// katmansızda `base`; kayıt yoksa değişken HİÇ verilmez (boş dize "bilinen sürüm" sanılmasın).
    #[test]
    fn kp3_backend_ortamina_kurulu_paket_kimligi_gecer_katmanli_app_oncelikli() {
        let d = tempfile::tempdir().unwrap();
        let yok = |_: &str| -> Option<String> { None };
        assert!(!backend_env_with(yok, d.path(), 8000, "").contains_key(ENV_BASE_SHA));
        std::fs::write(installed_packages_path(d.path()), r#"{"base":"b-sha"}"#).unwrap();
        assert_eq!(backend_env_with(yok, d.path(), 8000, "").get(ENV_BASE_SHA).map(String::as_str), Some("b-sha"));
        std::fs::write(installed_packages_path(d.path()), r#"{"base":"b-sha","app":"a-sha"}"#).unwrap();
        assert_eq!(backend_env_with(yok, d.path(), 8000, "").get(ENV_BASE_SHA).map(String::as_str), Some("a-sha"));
    }
}
