// Windows'ta arka planda konsol penceresi açılmasın.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! PEMF Vet Client — Tauri kabuğu.
//!
//! Tüm iş mantığı `pemf-launcher-core`'da; burası yalnız pencere, komutlar ve
//! ilerleme olaylarıdır. Böylece kurulum akışı UI olmadan test edilebilir kalır
//! (bkz. core/tests/real_artifacts.rs).

use std::sync::Mutex;

use pemf_launcher_core::{backend, flow, install, net, platform};
use tauri::{Emitter, Manager};

/// Manifest'in yayınlandığı yer (`pemf-app-packages/publish.ps1` ile aynı repo/tag).
const MANIFEST_URL: &str = "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/manifest.json";

/// Backend süreci — pencere kapanınca öldürmek için tutulur.
#[derive(Default)]
struct AppState {
    child: Mutex<Option<std::process::Child>>,
    /// Backend portu — pencere kapanışında bobinleri E-stop ile güvene almak için (safe_stop_coils).
    port: Mutex<Option<u16>>,
}

#[derive(serde::Serialize)]
struct Environment {
    platform: String,
    install_root: String,
    already_installed: bool,
}

fn home_dir() -> std::path::PathBuf {
    // std::env::home_dir() eski Rust'larda Windows'ta yanlış davrandığı için
    // ortam değişkenlerinden çözüyoruz.
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| std::path::PathBuf::from("."))
}

#[tauri::command]
fn detect_environment() -> Environment {
    let root = install::default_install_root(&home_dir());
    Environment {
        platform: platform::current().to_string(),
        already_installed: install::backend_path(&root).exists(),
        install_root: root.to_string_lossy().into_owned(),
    }
}

/// Manifest'i indir ve profil listesini döndür.
#[tauri::command]
fn fetch_profiles() -> Result<serde_json::Value, String> {
    // Host pinlemesi manifest'in KENDİSİ için de geçerli: zehirli bir manifest
    // zaten her şeyin girdisidir.
    net::validate_url(MANIFEST_URL).map_err(|e| e.to_string())?;
    let raw = ureq::get(MANIFEST_URL)
        .call()
        .map_err(|e| format!("Manifest indirilemedi: {e}"))?
        .into_string()
        .map_err(|e| format!("Manifest okunamadı: {e}"))?;

    let manifest =
        pemf_launcher_core::Manifest::parse(&raw).map_err(|e| e.to_string())?;

    // Bu platformun paketi yayınlanmamışsa KULLANICIYA ŞİMDİ söyle — 2 GB
    // indirdikten sonra değil.
    let supported = manifest.runtime_for_current_platform().is_ok();
    let mut profiles: Vec<&str> = manifest.models.keys().map(|s| s.as_str()).collect();
    profiles.sort_unstable();

    // Self-update BİLDİRİMİ: launcher thin-bootstrapper (kendini güncellemez). Manifest'teki
    // en son launcher sürümü kendi sürümümüzden yeniyse UI "yeni sürüm var, indir" gösterir.
    // (Mevcut kurulumlara ancak launcher'da bu kontrol VARSA ulaşır → bu sürümden itibaren.)
    let current_launcher = env!("CARGO_PKG_VERSION");
    let update = manifest.launcher.as_ref().and_then(|l| {
        pemf_launcher_core::is_newer(&l.version, current_launcher)
            .then(|| serde_json::json!({ "version": l.version, "url": l.url }))
    });

    Ok(serde_json::json!({
        "version": manifest.version,
        "schema": manifest.schema,
        "profiles": profiles,
        "platform_supported": supported,
        "platform": platform::current(),
        "current_launcher": current_launcher,
        "update": update,
        "raw": raw,
    }))
}

/// Güncelleme indirme sayfasını varsayılan tarayıcıda aç. Manifest host-pinli kaynaktan gelir;
/// yine de savunma: yalnız https + bilinen indirme host'ları (poisoned-manifest keyfi/zararlı
/// URL açamasın). Sondaki "/" şart → "github.com.evil" ve userinfo (github.com@evil) hileleri geçmez.
#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    const ALLOWED: [&str; 2] = ["https://pemf-vet-web.vercel.app/", "https://github.com/"];
    if !ALLOWED.iter().any(|p| url.starts_with(p)) {
        return Err(format!("İzin verilmeyen indirme adresi: {url}"));
    }
    backend::open_browser(&url).map_err(|e| e.to_string())
}

/// Kur ve başlat. İlerleme `install://progress` olayıyla akar.
#[tauri::command]
async fn install_and_launch(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    manifest_raw: String,
    profile: String,
) -> Result<String, String> {
    let root = install::default_install_root(&home_dir());

    // Ağır iş: bloklayan çağrılar UI thread'ini dondurmasın.
    let app2 = app.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        let mut on = |p: flow::Progress| {
            let _ = app2.emit("install://progress", &p);
        };
        flow::install_and_launch(&manifest_raw, &profile, &root, &mut on)
    })
    .await
    .map_err(|e| format!("kurulum görevi çöktü: {e}"))?;

    match result {
        Ok((child, url, port)) => {
            *state.child.lock().unwrap() = Some(child);
            *state.port.lock().unwrap() = Some(port);
            let _ = backend::open_browser(&url);
            Ok(url)
        }
        Err(e) => Err(e.to_string()),
    }
}

fn main() {
    tauri::Builder::default()
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            detect_environment,
            fetch_profiles,
            install_and_launch,
            open_url
        ])
        .on_window_event(|window, event| {
            // Pencere kapanınca backend'i BIRAKMA: yetim süreç portu tutar ve sonraki açılışta
            // "port meşgul" hatası verir. AMA öldürmeden ÖNCE bobinleri GÜVENE AL (TIBBİ GÜVENLİK):
            // child.kill() sinyal göndermez → backend'in bobin-STOP graceful'ı çalışmaz, seans
            // sürerken pencere kapatılırsa bobinler hastanın üzerinde açık kalır. E-stop ile durdur.
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<AppState>() {
                    if let Some(port) = *state.port.lock().unwrap() {
                        backend::safe_stop_coils(port);
                    }
                    if let Some(mut child) = state.child.lock().unwrap().take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("Tauri uygulaması başlatılamadı");
}
