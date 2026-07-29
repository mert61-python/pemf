// Windows'ta arka planda konsol penceresi açılmasın.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! PEMF Vet Client — Tauri kabuğu.
//!
//! Tüm iş mantığı `pemf-launcher-core`'da; burası yalnız pencere, komutlar ve
//! ilerleme olaylarıdır. Böylece kurulum akışı UI olmadan test edilebilir kalır
//! (bkz. core/tests/real_artifacts.rs).

use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::{Arc, Mutex};

use pemf_launcher_core::{backend, flow, install, net, platform, verify};
use tauri::{Emitter, Manager};

/// İndirme akış-kontrolü bayrağı (AppState.control): frontend pause/cancel komutları bunu set eder,
/// indirme döngüsü her yığında okur.
const CTL_RUN: u8 = 0;
const CTL_PAUSE: u8 = 1;
const CTL_CANCEL: u8 = 2;

/// Kurulum sonucu (spawn_blocking → komut). Ready backend'i taşır; Paused/Cancelled durum döner.
enum InstallOutcome {
    Ready(std::process::Child, String, u16),
    Paused,
    Cancelled,
}

/// Manifest'in yayınlandığı yer (`pemf-app-packages/publish.ps1` ile aynı repo/tag).
const MANIFEST_URL: &str = "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/manifest.json";

/// Backend süreci + portu — pencere kapanınca ÖNCE E-stop, sonra kill için tutulur.
/// #141: child + port TEK mutex altında → 'port biliniyorsa E-stop, child varsa kill' kararı
/// ATOMİK; port her zaman child ile birlikte set edilir ('child var ama port yok' imkânsız).
struct AppState {
    proc: Mutex<Option<(std::process::Child, u16)>>,
    /// Son ilerleme snapshot'ı — frontend `get_progress` ile POLL eder. Neden event değil:
    /// Tauri `emit` spawn_blocking thread'inden webview `listen`'e güvenilir ULAŞMIYOR (indirme
    /// boyunca UI donuk kaldı); invoke/polling kesin çalışıyor.
    progress: Arc<Mutex<Option<serde_json::Value>>>,
    /// İndirme akış-kontrolü: CTL_RUN/PAUSE/CANCEL. pause/cancel komutları set eder.
    control: Arc<AtomicU8>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            proc: Mutex::new(None),
            progress: Arc::new(Mutex::new(None)),
            control: Arc::new(AtomicU8::new(CTL_RUN)),
        }
    }
}

#[derive(serde::Serialize)]
struct Environment {
    platform: String,
    install_root: String,
    already_installed: bool,
    /// Kurulu profiller (UI çip'leri: "Ev Sahibi"/"Veteriner"/"Araştırma").
    installed_profiles: Vec<String>,
    /// Yarım kalan kurulumun profilleri (varsa) — açılışta "devam et?" gösterilir.
    pending_profiles: Vec<String>,
}

/// Çalışan backend'i TIBBİ-GÜVENLİ durdur: ÖNCE bobinleri E-stop'la, SONRA süreci öldür.
/// Yeniden-kurulum / onarım / kaldırma öncesi çağrılır (port çakışması + kilitli exe + enerjili
/// bobin riskini keser). state.proc bu oturumda başlatılan backend'i tutar.
fn stop_tracked_backend(state: &tauri::State<'_, AppState>, root: &std::path::Path) {
    // 1) Bu oturumun tracked backend'i: E-stop (TIBBİ GÜVENLİK) + kill.
    let had_tracked = if let Some((mut child, port)) = state.proc.lock().unwrap().take() {
        backend::safe_stop_coils(port);
        let _ = child.kill();
        let _ = child.wait();
        true
    } else {
        false
    };
    // 2) ORPHAN süreçler (önceki kurulum/instance): yeniden-kurulumda `mosquitto.exe`/backend
    //    runtime/ dosyalarını KİLİTLER → extract "os error 32". Bu yüzden sistem-genelinde durdur.
    //    Tracked yoksa önce backend.port'tan E-stop (bobinleri güvene al), sonra zorla kapat.
    if !had_tracked {
        if let Ok(txt) = std::fs::read_to_string(root.join("backend.port")) {
            if let Ok(port) = txt.trim().parse::<u16>() {
                backend::safe_stop_coils(port);
            }
        }
    }
    backend::kill_stray_backends();
    // taskkill sonrası OS'un dosya kilitlerini bırakması için kısa bekle (extract'tan ÖNCE).
    std::thread::sleep(std::time::Duration::from_millis(800));
    let _ = std::fs::remove_file(root.join("backend.port"));
}

/// İlerleme raporlayıcı: son snapshot'ı paylaşılan `store`'a yazar (frontend POLL eder). İndirme
/// olayları ~80ms'e throttle'lı (net.rs 256KB-başı çağırır → her seferinde JSON+kilit gereksiz);
/// faz-değişimi (manifest/verify/extract/start/ready) + her indirmenin SON parçası HER ZAMAN yazılır.
/// (emit de yapılır — bazı ortamlarda çalışır, zararsız — ama UI polling'e dayanır.)
fn progress_reporter(
    app: tauri::AppHandle,
    store: std::sync::Arc<Mutex<Option<serde_json::Value>>>,
) -> impl FnMut(flow::Progress) {
    let mut last = std::time::Instant::now();
    let mut any = false;
    move |p: flow::Progress| {
        if let flow::Progress::Downloading { done, total, .. } = &p {
            let final_chunk = *total > 0 && *done >= *total;
            if any && !final_chunk && last.elapsed() < std::time::Duration::from_millis(80) {
                return;
            }
        }
        any = true;
        last = std::time::Instant::now();
        if let Ok(v) = serde_json::to_value(&p) {
            *store.lock().unwrap() = Some(v);
        }
        let _ = app.emit("install://progress", &p);
    }
}

/// Backend başladıktan sonra: child+port'u ATOMİK sakla, port'u diske yaz (uninstaller E-stop
/// okuyabilsin), tarayıcıyı aç. install/start/repair'in ortak son adımı.
fn on_backend_ready(
    app: &tauri::AppHandle,
    state: &tauri::State<'_, AppState>,
    child: std::process::Child,
    url: &str,
    port: u16,
) {
    *state.proc.lock().unwrap() = Some((child, port));
    let _ = std::fs::write(
        install::default_install_root(&home_dir()).join("backend.port"),
        port.to_string(),
    );
    // Chrome/harici tarayıcı YERİNE: uygulamayı CLIENT PENCERESİNE göm (WebView2 içinde localhost).
    show_app_in_window(app, url);
}

/// Ana pencerenin webview'ını (localhost) uygulamaya yönlendir + pencereyi büyüt. Host-başlatımlı
/// navigasyon (adres-çubuğu gibi) → launcher CSP'si engellemez. Pencere kapanınca on_window_event
/// Destroyed → backend GÜVENLE durur (E-stop + kill). navigate imkânsızsa tarayıcıya düş (fail-safe).
fn show_app_in_window(app: &tauri::AppHandle, url: &str) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.maximize();
        // WebView2 CACHE-BUST: kalıcı user-data-folder aynı origin'de (127.0.0.1:8000) ESKİ index.html'i
        // cache'ler → önceki bir kurulumun eski bundle'ı yüklenip (ör. giriş Supabase'e ulaşamaz, "hatalı")
        // Chrome'da sorun yokken WebView2'de kalır. Zaman-damgalı query her açılışta TAZE index.html
        // çektirir; onun referans ettiği hash'li JS zaten yeni dosya adıyla taze gelir.
        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0);
        let sep = if url.contains('?') { '&' } else { '?' };
        let busted = format!("{url}{sep}_={ts}");
        match busted.parse::<tauri::Url>() {
            Ok(u) => {
                let _ = win.navigate(u);
            }
            Err(_) => {
                let _ = backend::open_browser(url);
            }
        }
    } else {
        let _ = backend::open_browser(url);
    }
}

fn home_dir() -> std::path::PathBuf {
    // std::env::home_dir() eski Rust'larda Windows'ta yanlış davrandığı için
    // ortam değişkenlerinden çözüyoruz.
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(std::path::PathBuf::from)
        // #146: HOME/USERPROFILE yoksa CWD-relative "." (fail-open) YERİNE mutlak temp dizini —
        // kurulumu çalışma-dizinine (öngörülemez/yazılabilir) yazma riskini keser.
        .unwrap_or_else(std::env::temp_dir)
}

#[tauri::command]
fn detect_environment() -> Environment {
    let root = install::default_install_root(&home_dir());
    Environment {
        platform: platform::current().to_string(),
        already_installed: install::backend_path(&root).exists(),
        installed_profiles: install::read_installed_profiles(&root),
        pending_profiles: install::read_pending(&root),
        install_root: root.to_string_lossy().into_owned(),
    }
}

/// Manifest'i indir ve profil listesini döndür.
#[tauri::command]
fn fetch_profiles() -> Result<serde_json::Value, String> {
    // Host pinlemesi manifest'in KENDİSİ için de geçerli: zehirli bir manifest zaten her şeyin
    // girdisidir. fetch_string_pinned: https-only + connect/read timeout (asılı-uç askıya almasın)
    // + redirect-sonrası host yeniden-doğrulama + into_string ~10MB metin-DoS sınırı.
    let raw = net::fetch_string_pinned(MANIFEST_URL)
        .map_err(|e| format!("Manifest indirilemedi: {e}"))?;

    let manifest =
        pemf_launcher_core::Manifest::parse(&raw).map_err(|e| e.to_string())?;

    // Bu platformun paketi yayınlanmamışsa KULLANICIYA ŞİMDİ söyle — 2 GB
    // indirdikten sonra değil.
    let supported = manifest.runtime_for_current_platform().is_ok();
    let mut profiles: Vec<&str> = manifest.models.keys().map(|s| s.as_str()).collect();
    profiles.sort_unstable();

    // OTO-GÜNCELLEME: launcher thin-bootstrapper. Manifest'teki en son launcher sürümü kendi
    // sürümümüzden yeniyse UI açılışta SESSİZCE güncellemeyi uygular (`installer_url` varsa →
    // `apply_self_update`); yalnız sürüm/url varsa (eski manifest) UI "yeni sürüm var" bildirir.
    // İnternet yoksa fetch_profiles zaten hata verir → kontrol hiç çalışmaz (sessiz atlama).
    let current_launcher = env!("CARGO_PKG_VERSION");
    let update = manifest.launcher.as_ref().and_then(|l| {
        pemf_launcher_core::is_newer(&l.version, current_launcher).then(|| {
            serde_json::json!({
                "version": l.version,
                "url": l.url,
                "installer_url": l.installer_url,
                "sha256": l.sha256,
                "size": l.size,
            })
        })
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
    // #138: ham "https://github.com/" YERİNE ürün-repo önekine daralt → zehirli manifest keyfi bir
    // GitHub repo'suna (SHA'sız indirme) yönlendiremez.
    const ALLOWED: [&str; 2] = [
        "https://pemf-vet-web.vercel.app/",
        "https://github.com/mert61-python/pemf-update/",
    ];
    if !ALLOWED.iter().any(|p| url.starts_with(p)) {
        return Err(format!("İzin verilmeyen indirme adresi: {url}"));
    }
    // Derinlik-savunması: open_browser artık rundll32 kullansa da (kabuk yok), manifest-türevi
    // URL'yi asla riske atma — kabuk-metakarakteri, kontrol-karakteri veya boşluk içeren URL'yi
    // reddet. Meşru GitHub/Vercel indirme URL'lerinde bunlar bulunmaz.
    if url.len() > 2048 || url.chars().any(|c| c.is_control() || "&|^<>\"'`{} \t\r\n".contains(c)) {
        return Err("Geçersiz karakter içeren indirme adresi reddedildi".to_string());
    }
    backend::open_browser(&url).map_err(|e| e.to_string())
}

/// SEÇİLEN PROFİLLERİ kur ve başlat. İlerleme `install://progress` olayıyla akar.
/// `profiles`: bir veya birden çok profil ("home"/"vet"/"research") — çoklu seçim desteklenir.
#[tauri::command]
async fn install_and_launch(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    manifest_raw: String,
    profiles: Vec<String>,
) -> Result<serde_json::Value, String> {
    let root = install::default_install_root(&home_dir());
    // Yeniden-kurulum: çalışan backend varsa ÖNCE güvenle durdur (exe kilidi + port çakışması).
    stop_tracked_backend(&state, &root);
    // Açılışta "devam et?" için seçimi kaydet (internet kesilir/laptop kapanırsa .part + bu dosya kalır).
    install::write_pending(&root, &profiles);
    *state.progress.lock().unwrap() = None;
    state.control.store(CTL_RUN, Ordering::Relaxed);

    // Ağır iş: bloklayan çağrılar UI thread'ini dondurmasın.
    let app2 = app.clone();
    let root2 = root.clone();
    let store = state.progress.clone();
    let ctrl = state.control.clone();
    let result: Result<InstallOutcome, String> = tauri::async_runtime::spawn_blocking(move || {
        let mut on = progress_reporter(app2, store);
        let control = || match ctrl.load(Ordering::Relaxed) {
            CTL_PAUSE => net::Control::Pause,
            CTL_CANCEL => net::Control::Cancel,
            _ => net::Control::Continue,
        };
        match flow::install_profiles(&manifest_raw, &profiles, &root2, &mut on, &control) {
            Ok(()) => {}
            Err(flow::FlowError::Net(net::NetError::Paused)) => return Ok(InstallOutcome::Paused),
            Err(flow::FlowError::Net(net::NetError::Cancelled)) => return Ok(InstallOutcome::Cancelled),
            Err(e) => return Err(e.to_string()),
        }
        flow::start_backend(&root2, &mut on)
            .map(|(c, u, p)| InstallOutcome::Ready(c, u, p))
            .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| format!("kurulum görevi çöktü: {e}"))?;

    match result {
        Ok(InstallOutcome::Ready(child, url, port)) => {
            on_backend_ready(&app, &state, child, &url, port);
            install::clear_pending(&root); // kurulum bitti → yarım-kalma kaydını temizle
            Ok(serde_json::json!({ "status": "ready", "url": url }))
        }
        // Duraklatıldı: .part + pending KORUNUR → "Devam Et" ile Range'den sürer.
        Ok(InstallOutcome::Paused) => Ok(serde_json::json!({ "status": "paused" })),
        // İptal: yarım .part + pending SİLİNİR → seçim ekranına dön.
        Ok(InstallOutcome::Cancelled) => {
            install::clear_pending(&root);
            install::clear_partials(&root);
            Ok(serde_json::json!({ "status": "cancelled" }))
        }
        Err(e) => Err(e),
    }
}

/// Başlat: KURULU uygulamanın backend'ini başlat (indirme YOK). Zaten çalışıyorsa tarayıcıyı
/// yeniden açar. "Hazır!" ekranındaki büyük Başlat düğmesi bunu çağırır.
#[tauri::command]
async fn start_installed(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
) -> Result<String, String> {
    let root = install::default_install_root(&home_dir());
    if !install::backend_path(&root).exists() {
        return Err("Uygulama kurulu değil — önce profil seçip kurun.".to_string());
    }
    // Zaten bu oturumda çalışıyorsa: yeni süreç başlatma, uygulamayı pencerede tekrar göster.
    let running_port = state.proc.lock().unwrap().as_ref().map(|(_, p)| *p);
    if let Some(port) = running_port {
        let url = backend::app_url(port);
        show_app_in_window(&app, &url);
        return Ok(url);
    }

    *state.progress.lock().unwrap() = None;
    let app2 = app.clone();
    let root2 = root.clone();
    let store = state.progress.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        let mut on = progress_reporter(app2, store);
        flow::start_backend(&root2, &mut on).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| format!("başlatma görevi çöktü: {e}"))?;

    match result {
        Ok((child, url, port)) => {
            on_backend_ready(&app, &state, child, &url, port);
            Ok(url)
        }
        Err(e) => Err(e),
    }
}

/// Onar: kurulu profilleri (+base) yeniden doğrula/çıkar (bozuk/eksik dosyaları onarır), sonra
/// backend'i başlat. İlerleme `install://progress` ile akar.
#[tauri::command]
async fn repair(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    manifest_raw: String,
) -> Result<serde_json::Value, String> {
    let root = install::default_install_root(&home_dir());
    stop_tracked_backend(&state, &root);
    *state.progress.lock().unwrap() = None;
    state.control.store(CTL_RUN, Ordering::Relaxed);

    let app2 = app.clone();
    let root2 = root.clone();
    let store = state.progress.clone();
    let ctrl = state.control.clone();
    let result: Result<InstallOutcome, String> = tauri::async_runtime::spawn_blocking(move || {
        let mut on = progress_reporter(app2, store);
        let control = || match ctrl.load(Ordering::Relaxed) {
            CTL_PAUSE => net::Control::Pause,
            CTL_CANCEL => net::Control::Cancel,
            _ => net::Control::Continue,
        };
        match flow::repair(&manifest_raw, &root2, &mut on, &control) {
            Ok(()) => {}
            Err(flow::FlowError::Net(net::NetError::Paused)) => return Ok(InstallOutcome::Paused),
            Err(flow::FlowError::Net(net::NetError::Cancelled)) => return Ok(InstallOutcome::Cancelled),
            Err(e) => return Err(e.to_string()),
        }
        flow::start_backend(&root2, &mut on)
            .map(|(c, u, p)| InstallOutcome::Ready(c, u, p))
            .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| format!("onarım görevi çöktü: {e}"))?;

    match result {
        Ok(InstallOutcome::Ready(child, url, port)) => {
            on_backend_ready(&app, &state, child, &url, port);
            Ok(serde_json::json!({ "status": "ready", "url": url }))
        }
        Ok(InstallOutcome::Paused) => Ok(serde_json::json!({ "status": "paused" })),
        Ok(InstallOutcome::Cancelled) => Ok(serde_json::json!({ "status": "cancelled" })),
        Err(e) => Err(e),
    }
}

/// Uygulamayı kaldır: KURULU uygulamayı (runtime + ai_models + cache + profil kaydı) sil, seçim
/// ekranına dön. TIBBİ-GÜVENLİ: önce bobin E-stop + backend kill. Hasta verisi (PEMF_GUI, %APPDATA%)
/// AYRI dizinde → SİLİNMEZ. Launcher'ın kendisi kalır (kullanıcı istediğinde yeniden kurabilir).
#[tauri::command]
fn uninstall(state: tauri::State<'_, AppState>) -> Result<(), String> {
    let root = install::default_install_root(&home_dir());
    stop_tracked_backend(&state, &root);
    install::remove_install(&root).map_err(|e| {
        format!("Kaldırma başarısız (uygulama çalışıyor olabilir): {e}")
    })
}

/// Son ilerleme snapshot'ını döndür (frontend kurulum/onarım sırasında ~150ms'de bir POLL eder).
/// null = henüz ilerleme yok veya temizlendi. Snapshot = `flow::Progress` JSON'u ({step, what, done, total} vb.).
#[tauri::command]
fn get_progress(state: tauri::State<'_, AppState>) -> Option<serde_json::Value> {
    state.progress.lock().unwrap().clone()
}

/// İndirmeyi DURAKLAT — indirme döngüsü `.part`'ı koruyup durur; kurulum komutu {status:"paused"}
/// döner. "Devam Et" = aynı profillerle install_and_launch'ı yeniden çağır (Range ile sürer).
#[tauri::command]
fn pause_install(state: tauri::State<'_, AppState>) {
    state.control.store(CTL_PAUSE, Ordering::Relaxed);
}

/// İndirmeyi/kurulumu İPTAL — `.part` + pending SİLİNİR; kurulum komutu {status:"cancelled"} döner.
#[tauri::command]
fn cancel_install(state: tauri::State<'_, AppState>) {
    state.control.store(CTL_CANCEL, Ordering::Relaxed);
}

/// Açılıştaki "yarım kalan kurulum" bildirimini AT: pending kaydı + `.part` dosyalarını sil
/// (çalışan kurulum yokken kullanıcı "devam etme, iptal" derse).
#[tauri::command]
fn discard_pending() -> Result<(), String> {
    let root = install::default_install_root(&home_dir());
    install::clear_pending(&root);
    install::clear_partials(&root);
    Ok(())
}

/// OTO-GÜNCELLEME uygula: yeni launcher setup'ını indir (host-pinli) + SHA256 doğrula + SESSİZCE
/// kur + yeniden başlat. Açılışta `fetch_profiles` `update.installer_url` döndürünce UI çağırır.
/// İlerleme `get_progress` ile POLL edilir. Başarılıysa uygulamadan ÇIKAR (detached helper setup'ı
/// çalıştırıp yeni launcher'ı başlatır); BAŞARISIZSA Err → UI normal boot'a düşer (güncelleme
/// kullanıcıyı ASLA bloklamaz — internet kesik/indirme bozuksa uygulama yine açılır).
#[tauri::command]
async fn apply_self_update(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    url: String,
    sha256: String,
    size: u64,
) -> Result<(), String> {
    #[cfg(not(windows))]
    {
        let _ = (&app, &state, &url, &sha256, size);
        Err("Bu platformda oto-güncelleme desteklenmiyor".to_string())
    }
    #[cfg(windows)]
    {
        // GÜVENLİK: imzasız setup exe çalıştırılacak → SHA256 ZORUNLU (manifest host-pinli kaynaktan
        // geldiği için sha güven çıpasıdır). url host-pinlemesi download_to_file içinde uygulanır.
        if sha256.trim().is_empty() {
            return Err("Güncelleme SHA256 yok — güvenlik gereği atlandı".to_string());
        }
        *state.progress.lock().unwrap() = None;
        state.control.store(CTL_RUN, Ordering::Relaxed);

        let dest = std::env::temp_dir().join("PEMFVetClient-Update.exe");
        let (u, sha, dest2) = (url.clone(), sha256.clone(), dest.clone());
        let store = state.progress.clone();
        let app2 = app.clone();
        let ctrl = state.control.clone();
        tauri::async_runtime::spawn_blocking(move || -> Result<(), String> {
            let mut on = progress_reporter(app2, store);
            let control = || match ctrl.load(Ordering::Relaxed) {
                CTL_CANCEL => net::Control::Cancel,
                CTL_PAUSE => net::Control::Pause,
                _ => net::Control::Continue,
            };
            {
                let mut dl = |done, total| {
                    on(flow::Progress::Downloading { what: "Güncelleme".to_string(), done, total });
                };
                net::download_to_file(&u, &dest2, size, &mut dl, &control)
                    .map_err(|e| e.to_string())?;
            }
            on(flow::Progress::Verifying { what: "Güncelleme".to_string() });
            verify::verify_file(&dest2, &sha).map_err(|e| {
                // Bozuk/sahte setup'ı ASLA çalıştırma → sil.
                let _ = std::fs::remove_file(&dest2);
                format!("Güncelleme doğrulanamadı: {e}")
            })?;
            Ok(())
        })
        .await
        .map_err(|e| format!("güncelleme görevi çöktü: {e}"))??;

        // İndirildi + SHA doğrulandı → sessiz kur + yeniden başlat helper'ını DETACHED başlat, sonra çık.
        spawn_update_relauncher(&dest)?;
        app.exit(0);
        Ok(())
    }
}

/// Sessiz kurulum + yeniden başlatma helper'ı (Windows). Bu launcher ÇIKTIKTAN sonra bağımsız
/// çalışsın diye DETACHED bir batch başlatır: kısa bekle (launcher çıksın, exe kilidi bıraksın) →
/// setup'ı `/S` sessiz kur (NSIS eski sürümü kaldırıp yenisini kurar) → yeni launcher'ı başlat →
/// kendini sil. Tauri NSIS `currentUser` kurulumu (AppData\Local) olduğundan UAC prompt'u YOK.
/// Yeniden-başlatma batch'inin İÇERİĞİNİ üret (saf → birim-test edilebilir). Batch-enjeksiyonu
/// savunması: yollar tırnak / yeni-satır içeremez (meşru Windows yollarında bulunmaz). `ping` =
/// taşınabilir uyku (timeout.exe redirected-stdin'de çalışmaz): ~3sn bekle → sessiz kur → ~2sn → başlat.
#[cfg(windows)]
fn build_relaunch_script(installer: &str, exe: &str) -> Result<String, String> {
    for p in [installer, exe] {
        if p.contains('"') || p.contains('\r') || p.contains('\n') {
            return Err("Güncelleme yolu güvensiz karakter içeriyor".to_string());
        }
    }
    Ok(format!(
        "@echo off\r\n\
         ping -n 4 127.0.0.1 >nul\r\n\
         \"{inst}\" /S\r\n\
         ping -n 3 127.0.0.1 >nul\r\n\
         start \"\" \"{exe}\"\r\n\
         del \"%~f0\"\r\n",
        inst = installer,
        exe = exe,
    ))
}

#[cfg(windows)]
fn spawn_update_relauncher(installer: &std::path::Path) -> Result<(), String> {
    use std::os::windows::process::CommandExt;
    const DETACHED_PROCESS: u32 = 0x0000_0008;
    const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;

    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let exe_s = exe.to_str().ok_or("launcher yolu UTF-8 değil")?;
    let inst_s = installer.to_str().ok_or("setup yolu UTF-8 değil")?;
    let script = build_relaunch_script(inst_s, exe_s)?;
    let bat = std::env::temp_dir().join("pemf_selfupdate.bat");
    std::fs::write(&bat, script).map_err(|e| e.to_string())?;

    std::process::Command::new("cmd.exe")
        .arg("/c")
        .arg(&bat)
        .creation_flags(DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW)
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            detect_environment,
            fetch_profiles,
            install_and_launch,
            start_installed,
            repair,
            uninstall,
            get_progress,
            pause_install,
            cancel_install,
            discard_pending,
            open_url,
            apply_self_update
        ])
        .on_window_event(|window, event| {
            // Pencere kapanınca backend'i BIRAKMA: yetim süreç portu tutar ve sonraki açılışta
            // "port meşgul" hatası verir. AMA öldürmeden ÖNCE bobinleri GÜVENE AL (TIBBİ GÜVENLİK):
            // child.kill() sinyal göndermez → backend'in bobin-STOP graceful'ı çalışmaz, seans
            // sürerken pencere kapatılırsa bobinler hastanın üzerinde açık kalır. E-stop ile durdur.
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<AppState>() {
                    // #141: child+port tek kilitten atomik alınır → E-stop(port) HER ZAMAN kill'den önce.
                    if let Some((mut child, port)) = state.proc.lock().unwrap().take() {
                        backend::safe_stop_coils(port);
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                    // child.kill() ÇOCUK-AĞACINI öldürmez → spawn edilen mosquitto/cloudflared YETİM
                    // kalır ve runtime/ dosyalarını kilitler (sonraki kurulum "os error 32"). Ağacı temizle.
                    backend::kill_stray_backends();
                    // Temiz kapanış: bobinler durduruldu + backend öldürüldü → port dosyasını
                    // sil ki sonraki bir uninstall ölü bir porta E-stop POST'lamasın. (Çökme
                    // yolunda bu handler ÇALIŞMAZ → dosya kalır ve uninstaller E-stop'lar.)
                    let root = install::default_install_root(&home_dir());
                    let _ = std::fs::remove_file(root.join("backend.port"));
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("Tauri uygulaması başlatılamadı");
}

#[cfg(test)]
mod tests {
    use super::*;

    /// GÜVENLİK: open_url kabuk-metakarakteri / izinsiz-host / kontrol-karakteri içeren
    /// (manifest-türevi zehirli) URL'leri open_browser'a ULAŞTIRMADAN reddetmeli.
    #[test]
    fn open_url_kotucul_url_reddeder() {
        // İZİNLİ öneki (daraltılmış repo) GEÇİP metakarakter dalına takılan URL'ler → reddet.
        // (Böylece main.rs:100 prefix'i DEĞİL, metakarakter/kontrol reddi de test edilir.)
        assert!(open_url("https://github.com/mert61-python/pemf-update/x&\\\\evil\\evil.exe".into()).is_err());
        assert!(open_url("https://github.com/mert61-python/pemf-update/a|calc".into()).is_err());
        assert!(open_url("https://github.com/mert61-python/pemf-update/a b".into()).is_err());
        // izin verilmeyen repo (daraltılmış önek dışı) → prefix'te reddet
        assert!(open_url("https://github.com/x&\\\\evil\\share\\evil.exe".into()).is_err());
        assert!(open_url("https://github.com/a|calc".into()).is_err());
        assert!(open_url("https://github.com/a^b".into()).is_err());
        // izinsiz şema/host
        assert!(open_url("http://evil.com/".into()).is_err());
        assert!(open_url("https://github.com.evil/x".into()).is_err());
        // boşluk / kontrol karakteri
        assert!(open_url("https://github.com/a b".into()).is_err());
        assert!(open_url("https://github.com/a\nb".into()).is_err());
    }

    /// OTO-GÜNCELLEME: yeniden-başlatma batch'i yolları DOĞRU gömer + enjeksiyon (tırnak/newline) REDDEDER.
    #[cfg(windows)]
    #[test]
    fn relaunch_script_gomer_ve_enjeksiyon_reddeder() {
        let s = build_relaunch_script(
            r"C:\Temp\PEMFVetClient-Update.exe",
            r"C:\Users\x\AppData\Local\PEMF Vet Client\PEMF Vet Client.exe",
        )
        .unwrap();
        // Sessiz kurulum (/S) + doğru setup yolu.
        assert!(s.contains("\"C:\\Temp\\PEMFVetClient-Update.exe\" /S"));
        // Yeni launcher'ı başlat (boşluklu yol tırnaklı).
        assert!(s.contains("start \"\" \"C:\\Users\\x\\AppData\\Local\\PEMF Vet Client\\PEMF Vet Client.exe\""));
        // Kendini sil.
        assert!(s.contains("del \"%~f0\""));
        // Batch-enjeksiyonu: tırnak veya yeni-satır içeren yol → REDDET.
        assert!(build_relaunch_script("C:\\a\".exe", "C:\\b.exe").is_err());
        assert!(build_relaunch_script("C:\\a.exe", "C:\\b\n.exe").is_err());
        assert!(build_relaunch_script("C:\\a\r.exe", "C:\\b.exe").is_err());
    }
}
