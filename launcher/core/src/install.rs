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
    let mut env = BTreeMap::new();
    env.insert(
        ENV_MODELS_DIR.to_string(),
        models_dir(install_root).to_string_lossy().into_owned(),
    );
    env.insert(ENV_API_PORT.to_string(), port.to_string());
    // Güvenli varsayılan (bkz. ENV_REQUIRE_AUTH): uzak/tünel erişimi token ister; LAN muaf kalır.
    env.insert(ENV_REQUIRE_AUTH.to_string(), "1".to_string());
    if !health_nonce.is_empty() {
        env.insert(ENV_HEALTH_NONCE.to_string(), health_nonce.to_string());
    }
    env
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
pub fn clear_partials(install_root: &Path) {
    let cache = cache_dir(install_root);
    if let Ok(entries) = std::fs::read_dir(&cache) {
        for e in entries.flatten() {
            if e.path().extension().is_some_and(|x| x == "part") {
                let _ = std::fs::remove_file(e.path());
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
