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
pub const ENV_DATA_DIR: &str = "PEMF_DATA_DIR";
pub const ENV_API_PORT: &str = "PEMF_API_PORT";

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

/// Backend süreci için ortam değişkenleri.
pub fn backend_env(install_root: &Path, port: u16) -> BTreeMap<String, String> {
    let mut env = BTreeMap::new();
    env.insert(
        ENV_MODELS_DIR.to_string(),
        models_dir(install_root).to_string_lossy().into_owned(),
    );
    env.insert(ENV_API_PORT.to_string(), port.to_string());
    env
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
    if install_root.exists() {
        return;
    }
    if let Some(parent) = install_root.parent() {
        let legacy = parent.join("PEMFVetClient");
        if legacy.is_dir() {
            let _ = std::fs::rename(&legacy, install_root);
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
        let env = backend_env(Path::new("/opt/pemf"), 8123);
        // Platform-agnostik: Windows '\' vs POSIX '/' — Path karşılaştır (string değil).
        assert_eq!(Path::new(&env[ENV_MODELS_DIR]), Path::new("/opt/pemf").join("ai_models"));
        assert_eq!(env[ENV_API_PORT], "8123");
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
