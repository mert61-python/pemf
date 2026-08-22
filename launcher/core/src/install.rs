// Author: mertaygn, cglrgrkn
//! Kurulum düzeni + backend'e verilecek ortam değişkenleri.
//!
//! GERİYE UYUM: buradaki yollar `utils/path_utils.py::get_app_data_directory()`
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
/// Neden env ile veriyoruz: `utils/model_downloader.py::_candidate_model_roots()`
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
/// `PEMF_REQUIRE_AUTH` tanımsız kalıyor ve `servers/auth.py` varsayılanı "0" → uzak/tünel
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
/// Sonuç zinciri (`utils/stm32_transport.py`): değişken boşsa `configured = FIXED_STM32_PORT`
/// (= `COM10`) ve oto-algılama YALNIZ `auto` ile açılır. ST-Link VCP'nin COM numarası Windows'un
/// USB numaralandırmasına göre değişir (COM3/COM4/COM5…), dolayısıyla klinik PC'sinde COM10
/// olmadığında backend sonsuza dek COM10'u dener (`_mark_bad` + 3 sn cooldown) →
/// **bobin 1-5 hiç bağlanmaz.** ESP bobinleri 6-8 MQTT'den çalışmaya devam ettiği için cihaz
/// "çalışıyor gibi görünür" — 1.9.28'de aynı sınıf için kaydedilen "yarısı çalışan cihaz" tablosu.
/// Bu ayar ne arayüzde ne launcher'da açığa çıkarılmıştır (`servers/settings_router.py` yalnız
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

/// DNS-REBINDING KORUMASI (eksik-taramasi P2, 2026-08-22) — bu sinifin BESINCI ornegi olmasin:
/// `PEMF_ALLOWED_HOSTS` altyapisi backend'de 2026-08-04'ten beri vardi ama launcher gecirmedigi
/// icin siteden kurulan HICBIR klinikte aktif degildi (ENABLE_TUNNEL/STM_PORT/DATA_DIR ile
/// birebir ayni kacis yolu). "auto": IP-literal/localhost/*.local/makine-adi/tunel alanlari
/// serbest, YABANCI alan adlari 400 (rebinding vektoru). Ortamda tanimliysa DOKUNULMAZ
/// (cikis kapisi: `PEMF_ALLOWED_HOSTS=*` korumayi kapatir, `auto,klinik.sirket.com` ek ad verir).
pub const ENV_ALLOWED_HOSTS: &str = "PEMF_ALLOWED_HOSTS";

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

/// Yeni yaratılan makine-geneli klasöre "Kullanıcılar: Değiştir" ACL'i ver.
///
/// Klasörü YARATAN kullanıcı sahibidir ve sahip, yönetici olmasa da DACL'i değiştirebilir →
/// UAC gerekmez. Bu olmadan ikinci Windows hesabı klasörü okuyabilir ama YAZAMAZ.
/// Başarısız olursa sessizce geçilir: `dizin_yazilabilir_mi` kapısı zaten koruyor.
#[cfg(windows)]
fn acl_ver(dir: &Path) {
    // Konsol penceresi AÇMADAN (bkz. platform::gizli_komut): kurulum/güncelleme akışında koşar;
    // çıplak `Command` kullanıcıya siyah pencere gösteriyordu.
    let _ = crate::platform::gizli_komut("icacls")
        .arg(dir)
        .args(["/grant", "*S-1-5-32-545:(OI)(CI)M", "/T", "/C", "/Q"])
        .output();
}

#[cfg(not(windows))]
fn acl_ver(_dir: &Path) {}

/// Backend'e verilecek veri kökü: makine-geneli YAZILABİLİRSE onu, değilse `None`
/// (kullanıcı-başına eski davranışa düş — kurulumu kırmaktansa bugünkü hâlde kal).
pub fn cozulmus_veri_dizini<F>(getenv: F) -> Option<PathBuf>
where
    F: Fn(&str) -> Option<String>,
{
    let dir = machine_data_dir(getenv)?;
    let yeni = !dir.exists();
    if !dizin_yazilabilir_mi(&dir) {
        return None;
    }
    if yeni {
        acl_ver(&dir);
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

/// Backend'e verilen off-site yedek hedefi (bkz. services/headless_db_maintenance._copy_offsite).
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

/// Seçilen hedef off-site yedek için uygun mu? `Ok(())` ya da kullanıcıya gösterilecek sebep.
pub fn yedek_hedefi_gecerli_mi(hedef: &Path, veri_dizini: &Path) -> Result<(), String> {
    if !dizin_yazilabilir_mi(hedef) {
        return Err("Bu klasöre yazılamıyor. Sürücü takılı ve yazılabilir olmalı.".to_string());
    }
    if ayni_birim(hedef, veri_dizini) == Some(true) {
        return Err("Yedek hedefi hasta verisiyle AYNI sürücüde. Disk arızasında ikisi de \
                    kaybolur — harici bir disk ya da ağ paylaşımı seçin."
            .to_string());
    }
    Ok(())
}

/// FİLO ENVANTERİ (2026-08-09 denetimi, Tier 2) — geri çağırma yapılabilsin diye.
///
/// ⚠️ Bir bobin-güvenliği hatası bulunduğunda "hangi klinik hangi sürümde?" sorusunun cevabı
/// YOKTU. Cihaz kaydı 60 sn'de bir heartbeat gönderiyor ama içinde SÜRÜM BİLGİSİ hiç yok;
/// `rollout: 0` yalnız YENİ kurulumları durdurur, sahadaki mevcut cihazlara dokunmaz.
/// Backend bu değişkenleri bulut kaydına yazar (bkz. servers/sync_worker.py).
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
        Err(e) => Err(format!(
            "Başka bir PEMF Vet Client penceresi kurulum/güncelleme yapıyor. \
             Onun bitmesini bekleyin ya da diğer pencereyi kapatın. ({e})"
        )),
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
#[cfg(windows)]
pub fn boyut_kaydini_guncelle(install_root: &Path) -> bool {
    let kb = kurulum_boyutu(install_root) / 1024;
    if kb == 0 {
        return false; // kök boş/okunamadı → yanlış "0 MB" yazmaktansa dokunma
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
            &kb.min(u64::from(u32::MAX)).to_string(),
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
    // DNS-REBINDING KORUMASI (bkz. ENV_ALLOWED_HOSTS): bu satir olmadan launcher ile kuran
    // hicbir klinikte Host korumasi calismiyordu. Ortamda tanimliysa DOKUNMA.
    env.insert(
        ENV_ALLOWED_HOSTS.to_string(),
        getenv(ENV_ALLOWED_HOSTS)
            .filter(|v| !v.trim().is_empty())
            .unwrap_or_else(|| "auto".to_string()),
    );
    // TIBBİ VERİ KÖKÜ (bkz. ENV_DATA_DIR): makine-geneli yazılabilirse oraya. Bu satır olmadan
    // backend %APPDATA%'ya düşüyor ve ikinci Windows hesabı "boş klinik" görüyordu.
    if let Some(d) = cozulmus_veri_dizini(getenv) {
        env.insert(ENV_DATA_DIR.to_string(), d.to_string_lossy().into_owned());
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
pub fn infer_profiles_from_disk(install_root: &Path) -> Vec<String> {
    let mut v: Vec<String> = std::fs::read_dir(models_dir(install_root))
        .map(|rd| {
            rd.flatten()
                .filter(|e| e.file_type().map(|t| t.is_dir()).unwrap_or(false))
                .filter_map(|e| e.file_name().to_str().map(str::to_owned))
                .collect()
        })
        .unwrap_or_default();
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

    fn env_from<'a>(pairs: &'a [(&'a str, &'a str)]) -> impl Fn(&str) -> Option<String> + 'a {
        move |k| {
            pairs
                .iter()
                .find(|(kk, _)| *kk == k)
                .map(|(_, v)| (*v).to_string())
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
        let env = backend_env(Path::new("/opt/pemf"), 8000, "");
        if cfg!(target_os = "windows") && std::env::var("PROGRAMDATA").is_ok() {
            // Gerçek makinede ProgramData yazılabilir → değişken verilmiş OLMALI.
            assert!(env.contains_key(ENV_DATA_DIR),
                "PEMF_DATA_DIR verilmedi — ikinci Windows hesabi BOS KLINIK gorur");
            assert!(env[ENV_DATA_DIR].contains("PEMF_System"));
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
        let d = tempfile::tempdir().unwrap();
        let veri = d.path();
        let r = yedek_hedefi_gecerli_mi(veri, veri);
        assert!(r.is_err(), "ayni surucudeki hedef kabul edildi");
        assert!(r.unwrap_err().contains("AYNI"), "sebep kullaniciya anlasilir degil");
    }

    #[test]
    fn yazilamayan_hedef_REDDEDILIR() {
        let gecersiz = if cfg!(target_os = "windows") { r"\?\Q:\yok" } else { "/proc/olmaz" };
        assert!(yedek_hedefi_gecerli_mi(Path::new(gecersiz), Path::new("/tmp")).is_err());
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
        let env = backend_env(d.path(), 8000, "");
        assert_eq!(Path::new(&env[ENV_BACKUP_DIR]), hedef,
            "yedek hedefi backend'e gecirilmedi — off-site kopya HIC alinmaz");
    }

    /// USB çıkarılmışsa değişken VERİLMEZ: backend her turda hataya düşüp günlüğü doldurmasın.
    #[test]
    fn erisilemez_hedef_backend_enve_GIRMEZ() {
        let d = tempfile::tempdir().unwrap();
        backup_dir_yaz(d.path(), r"\?\Q:\cikarilmis-usb").unwrap();
        let env = backend_env(d.path(), 8000, "");
        assert!(!env.contains_key(ENV_BACKUP_DIR), "erisilemez hedef env'e girdi");
    }

    #[test]
    fn backend_env_model_kokunu_ve_portu_verir() {
        let env = backend_env(Path::new("/opt/pemf"), 8123, "");
        // Platform-agnostik: Windows '\' vs POSIX '/' — Path karşılaştır (string değil).
        assert_eq!(Path::new(&env[ENV_MODELS_DIR]), Path::new("/opt/pemf").join("ai_models"));
        assert_eq!(env[ENV_API_PORT], "8123");
    }

    /// DENETİM P0 regresyonu: launcher backend'i kimlik doğrulaması KAPALI başlatmamalı.
    /// Backend `.env` dosyalarını okumaz; bu env verilmezse `servers/auth.py` varsayılanı "0"dır
    /// ve uzak/tünel erişimi kimliksiz açılır. LAN/localhost `is_local_request` ile muaf olduğu
    /// için bu bayrak yerel arayüzü bozmaz.
    #[test]
    fn backend_env_auth_zorunlulugunu_acik_verir() {
        let env = backend_env(Path::new("/opt/pemf"), 8123, "");
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
        let env = backend_env(Path::new("/opt/pemf"), 8123, "");
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

    #[test]
    fn backend_env_STM_PORT_OTO_ALGILAMAYI_acar() {
        // ⚠️ DENETİM 2026-08-17: bu satır olmadan backend sabit `COM10`a düşüyordu
        // (`utils/stm32_transport.py`: oto-algılama YALNIZ `auto` ile açılır). ST-Link'in COM
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
        let env = backend_env(Path::new("/opt/pemf"), 8123, "nonce123");
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
        ];
        // `ENV_BASE_SHA` yalnız KURULU bir paket varsa eklenir (ilk açılışta kurulum yok).
        if !read_installed_packages(Path::new("/opt/pemf")).app.is_empty()
            || !read_installed_packages(Path::new("/opt/pemf")).base.is_empty()
        {
            beklenen.push(ENV_BASE_SHA);
        }
        if cozulmus_veri_dizini(|k| std::env::var(k).ok()).is_some() {
            beklenen.push(ENV_DATA_DIR);
        }
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
    /// OTOMATİK YÜKLEMEZ (`load_dotenv` yok → `servers/api_server.py`'nin kendi notu), launcher da
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

        let env = backend_env(Path::new("/opt/pemf"), 8123, "nonce123");

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
