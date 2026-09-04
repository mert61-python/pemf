// Author: mertaygn, cglrgrkn
// Windows'ta arka planda konsol penceresi açılmasın.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! PEMF Vet Client — Tauri kabuğu.
//!
//! Tüm iş mantığı `pemf-launcher-core`'da; burası yalnız pencere, komutlar ve
//! ilerleme olaylarıdır. Böylece kurulum akışı UI olmadan test edilebilir kalır
//! (bkz. core/tests/real_artifacts.rs).

use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::{Arc, Mutex};

use pemf_launcher_core::{auth, backend, extract, flow, install, net, platform, secret_store, verify};
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
    /// ARKA PLAN ön-indirmenin ilerlemesi — `progress`ten AYRI tutulur (2026-08-16, sahip
    /// isteği: "yüzdelik real-time bar"). Neden ayrı: `progress`i kurulum ekranı yokluyor;
    /// sessiz ön-indirme oraya yazsaydı bir kurulum/onarım sürerken iki akış birbirine
    /// karışır ve ekran ele geçirilirdi — oysa ön-indirmenin tek amacı kullanıcıyı
    /// BEKLETMEMEK. Ayrı kanal: aynı anda ikisi de akabilir, UI ikisini ayrı çizer.
    prefetch: Arc<Mutex<Option<serde_json::Value>>>,
    /// İndirme akış-kontrolü: CTL_RUN/PAUSE/CANCEL. pause/cancel komutları set eder.
    control: Arc<AtomicU8>,
    /// "app" penceresi kapanınca ARKA PLANDA çalışan backend-kapatma işi (E-stop + kill).
    /// Client ("main") kapanmadan ÖNCE `join` edilir → süreç, bobin durdurma uçarken ÇIKMAZ.
    teardown: Mutex<Option<std::thread::JoinHandle<()>>>,
    /// Doğrulanmış Supabase oturumu — YALNIZ BELLEKTE. Kalıcılık ("Beni hatırla") ayrı ve
    /// işletim sistemi korumalı (`secret_store`). ⚠️ Bu alan `progress` snapshot'ına ASLA
    /// yazılmaz: o snapshot `get_progress` ile webview'e akar ve jetonlar UI'ya sızardı.
    session: Arc<Mutex<Option<auth::Session>>>,
    /// Oturum-rotasyon senkron thread'i çalışıyor mu (C3/L7 çift-thread guard'ı). Senkron BİR
    /// backend için tek thread; sahiplenme dalı her Başlat'ta koşabildiğinden guard olmadan thread
    /// biriktirirdi. Thread bittiğinde (backend öldü / 5 ardışık başarısız yoklama) serbest bırakılır.
    rotasyon_senkronu_aktif: Arc<AtomicBool>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            proc: Mutex::new(None),
            progress: Arc::new(Mutex::new(None)),
            prefetch: Arc::new(Mutex::new(None)),
            control: Arc::new(AtomicU8::new(CTL_RUN)),
            teardown: Mutex::new(None),
            session: Arc::new(Mutex::new(None)),
            rotasyon_senkronu_aktif: Arc::new(AtomicBool::new(false)),
        }
    }
}

#[derive(serde::Serialize)]
struct Environment {
    platform: String,
    install_root: String,
    already_installed: bool,
    /// Çalışan launcher sürümü. DENETİM 2026-08-06: UI bunu yalnız `fetch_profiles`'tan
    /// (yani MANİFEST'ten) alıyordu → internetsizken başlık "v—" kalıyor, "Hakkında" boş
    /// görünüyordu. Sürüm YEREL bir bilgidir; ağa bağlamak yanlıştı.
    launcher_version: String,
    /// Kurulu profiller (UI çip'leri: "Ev Sahibi"/"Veteriner"/"Araştırma").
    installed_profiles: Vec<String>,
    /// Yarım kalan kurulumun profilleri (varsa) — açılışta "devam et?" gösterilir.
    pending_profiles: Vec<String>,
}

/// Çalışan backend'i TIBBİ-GÜVENLİ durdur: ÖNCE bobinleri E-stop'la, SONRA süreci öldür.
/// Yeniden-kurulum / onarım / kaldırma öncesi çağrılır (port çakışması + kilitli exe + enerjili
/// bobin riskini keser). state.proc bu oturumda başlatılan backend'i tutar.
fn stop_tracked_backend(state: &tauri::State<'_, AppState>, root: &std::path::Path) {
    let tracked = state.proc.lock().unwrap().take();
    stop_backend_for_teardown(tracked, root, state.session.clone());
}

/// `stop_tracked_backend`'in kilitten BAĞIMSIZ gövdesi.
///
/// DENETİM 2026-08-06: `uninstall` bu işi `spawn_blocking`'e taşıyabilsin diye ayrıldı —
/// `tauri::State` thread'e taşınamaz, ama `(Child, port)` çifti taşınabilir. Sıra (E-stop →
/// kill → stray temizliği → port dosyası) DEĞİŞMEDİ.
fn stop_backend_for_teardown(
    tracked: Option<(std::process::Child, u16)>,
    root: &std::path::Path,
    bellek: Arc<Mutex<Option<auth::Session>>>, // [S4] F5 yakalama belleği de tazeler (thread'e taşınabilir Arc)
) {
    // 1) Bu oturumun tracked backend'i: E-stop (TIBBİ GÜVENLİK) + [F5] son-yakalama + kill.
    let had_tracked = if let Some((mut child, port)) = tracked {
        backend::safe_stop_coils(port);
        son_oturumu_yakala(port, root, &bellek); // [F5] E-stop SONRASI / kill ÖNCESİ: son jetonu diske işle
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
    clear_port_if_stopped(root, None);
}

/// [F5] (denetim 2026-08-24): kapanış-ÖNCESİ SON oturum yakalama. Teardown yolunda E-stop
/// gönderildi ama backend HENÜZ öldürülMEDİ → 60 sn rotasyon döngüsünün kaçırdığı son (≤60 sn)
/// döndürülmüş jetonu diske işlemek için SON şans. Aksi halde tüketilmiş refresh jeton diskte kalır
/// → sonraki açılışta SessionRevoked → "Beni hatırla" parola yeniden ister.
///
/// ⚠️ TIBBİ GÜVENLİK: bu çağrı `safe_stop_coils`'ten SONRA / `child.kill()`'den ÖNCE gelir —
/// bobinler DAİMA önce güvene alınır (pemf-device-safety-shutdown değişmezi); yakalama E-stop'u
/// ASLA geciktirmez. KISA timeout (`PULL_TEARDOWN_TIMEOUT_S`): backend meşgulse kapanışı bekletme.
/// best-effort: `None` → yazma yok (bugünküyle aynı). `rotasyonu_isle` YENİDEN kullanılır → 3 yazma
/// kapısı (kayıt-yok / boş-jeton / başka-eposta) OTOMATİK korunur (save() DOĞRUDAN çağrılmaz).
/// ⚠️ Yalnız BU oturumun TRACKED backend'inde çağrılır; orphan/backend.port dalında ASLA —
/// başka sürecin portundan jeton okumak loopback-jeton-zehirlenmesi savunmasını deler.
fn son_oturumu_yakala(port: u16, root: &std::path::Path, bellek: &Mutex<Option<auth::Session>>) {
    if let Some(s) = backend::pull_desktop_session_kisa(port, backend::PULL_TEARDOWN_TIMEOUT_S) {
        let _ = secret_store::rotasyonu_isle(root, &s);
        bellek_rotasyonu_uygula(bellek, &s); // [S4] bellek de taze kalsın (yeniden devir bayat itmesin)
    }
}

/// [S4] (saha arızası 2026-09-03, ÖLÇÜLDÜ): rotasyonla gelen oturum yalnız DİSKE yazılıyor, bellekteki
/// `AppState.session` HİÇ güncellenmiyordu. `hand_off_session` belleği ittiği için bir sonraki devirde
/// (runtime güncellemesi backend'i yeniden başlatınca / orphan sahiplenmede / ikinci Başlat'ta) backend'e
/// BAYAT jeton gidiyor, pencere onunla yenilemeye kalkıyor ve GoTrue reuse-detection TÜM AİLEYİ iptal
/// ediyordu → sonraki açılışta SessionRevoked → "Beni hatırla" parola istiyordu (bugün 17:07'den beri
/// açık launcher, 20:3x app 1.9.39 güncellemesi, 20:38 yeniden giriş). Bellek kuralı diskten AYRI:
/// "Beni hatırla" kapalı olsa da bellek taze kalmalı. Aynı e-posta + dolu + DEĞİŞMİŞ refresh → uygula;
/// bellekte oturum yoksa (giriş yapılmamış) devralma YOK (uydurma/otomatik giriş olmasın).
fn bellek_rotasyonu_gerekli(mevcut: Option<&auth::Session>, yeni: &auth::Session) -> bool {
    if yeni.refresh_token.trim().is_empty() {
        return false;
    }
    match mevcut {
        None => false,
        // [S4-yön] daha ESKİ jeton (bayat devir ekosu) belleği GERİYE çekemez; expires_at bilinmiyorsa (0) kabul.
        Some(m) => {
            m.email.eq_ignore_ascii_case(&yeni.email)
                && m.refresh_token != yeni.refresh_token
                && !(m.expires_at > 0 && yeni.expires_at > 0 && yeni.expires_at < m.expires_at)
        }
    }
}

fn bellek_rotasyonu_uygula(bellek: &Mutex<Option<auth::Session>>, yeni: &auth::Session) -> bool {
    let mut g = bellek.lock().unwrap();
    if bellek_rotasyonu_gerekli(g.as_ref(), yeni) {
        *g = Some(yeni.clone());
        true
    } else {
        false
    }
}

/// `backend.port`'u YALNIZ backend gerçekten sustuysa sil.
///
/// ⚠️ DENETİM 2026-08-04 — TIBBİ GÜVENLİK: bu dosya çalışan backend'in E-STOP ADRESİDİR; NSIS
/// uninstaller ve onarım yolu bobinleri durdurmak için SADECE ondan okur. Önceden silme KOŞULSUZDU:
/// `child.kill()` ya da `taskkill` BAŞARISIZ olsa bile (erişim reddi, süreç askıda, yükseltilmiş
/// başka oturumun süreci) dosya gidiyordu. Sonuç: backend hâlâ ayakta ve ESP bobinleri 6-8 enerjili
/// iken adres kayboluyor — o bobinlerin firmware'de link-watchdog'u YOKTUR, tek durdurma yolu
/// broker'a ulaşan STOP publish'idir. Artık portu yokluyoruz: hâlâ yanıt veriyorsa dosya KORUNUR.
fn clear_port_if_stopped(root: &std::path::Path, port: Option<u16>) {
    // ⚠️ P1 (denetim 2026-08-04): burada `probe_pemf_backend` kullanılıyordu; onun `false`'ı
    // "kimse yok" ile "yük altında, 2 sn'de cevap vermedi"yi AYNI kovaya koyuyor. Ölçüldü:
    // yanıt yazmayan canlı bir dinleyicide `false (2002 ms)`. Yani taskkill başarısız olmuş,
    // backend hâlâ ayakta ve bobinler enerjiliyken E-stop adresini SİLİYORDUK.
    // Artık silme YALNIZ "kesin ölü" (TCP reddedildi) durumunda. Yanılma maliyeti asimetrik:
    // ölü adres kalması zararsız, canlı adresin silinmesi hasta güvenliği sorunudur.
    let Some(p) = port.or_else(|| backend::read_backend_port(root)) else {
        // Port hiç bilinmiyorsa silinecek anlamlı bir adres de yok; dosyayı temizle.
        let _ = std::fs::remove_file(root.join("backend.port"));
        return;
    };
    if !backend::backend_is_definitely_gone(p) {
        return; // AYAKTA ya da BİLİNMİYOR → E-stop adresi KORUNUR.
    }
    let _ = std::fs::remove_file(root.join("backend.port"));
}

/// İlerleme raporlayıcı: son snapshot'ı paylaşılan `store`'a yazar (frontend POLL eder). İndirme
/// olayları ~80ms'e throttle'lı (net.rs 256KB-başı çağırır → her seferinde JSON+kilit gereksiz);
/// faz-değişimi (manifest/verify/extract/start/ready) + her indirmenin SON parçası HER ZAMAN yazılır.
/// (emit de yapılır — bazı ortamlarda çalışır, zararsız — ama UI polling'e dayanır.)
/// İlerleme snapshot'larını paylaşılan bir store'a yazan THROTTLE'lı yazıcı.
///
/// `progress_reporter` (kurulum) ve `prefetch_runtime_update` (arka plan) AYNI mantığı
/// kullanır; buraya çıkarıldı çünkü iki kural da sessizce bozulabiliyordu ve ikisi de
/// kullanıcıya doğrudan yansıyor:
///   • throttle YOKSA: indirme 256 KB başına olay üretir → her seferinde JSON+kilit israfı.
///   • SON PARÇA istisnası yoksa: son olay throttle'a takılır ve bar %99'da ASILI kalır.
/// (Mutasyon turu 2026-08-16: kaynak-regex testleri bu iki kuralı ayırt EDEMİYORDU; artık
/// `reporter_testleri` davranışsal olarak kilitliyor.)
fn snapshot_yazici(
    store: std::sync::Arc<Mutex<Option<serde_json::Value>>>,
    throttle_ms: u64,
) -> impl FnMut(flow::Progress) {
    let mut last = std::time::Instant::now();
    let mut any = false;
    move |p: flow::Progress| {
        if let flow::Progress::Downloading { done, total, .. } = &p {
            let son_parca = *total > 0 && *done >= *total;
            if any && !son_parca && last.elapsed() < std::time::Duration::from_millis(throttle_ms) {
                return;
            }
        }
        any = true;
        last = std::time::Instant::now();
        if let Ok(v) = serde_json::to_value(&p) {
            *store.lock().unwrap() = Some(v);
        }
    }
}

fn progress_reporter(
    app: tauri::AppHandle,
    store: std::sync::Arc<Mutex<Option<serde_json::Value>>>,
) -> impl FnMut(flow::Progress) {
    // Throttle + son-parça kuralı ORTAK yazıcıda (tek kaynak) — ön-indirme ile ayrışmasın.
    // Buradaki tek fark `emit`: bazı ortamlarda çalışır, zararsız; UI polling'e dayanır.
    let mut yaz = snapshot_yazici(store, 80);
    move |p: flow::Progress| {
        yaz(p.clone());
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
    // 🔴 OTURUM ROTASYON SENKRONU (saha arızası 2026-08-24) — "Beni hatırla" bozuluyordu.
    // Uygulama penceresi supabase-js ile jetonu arka planda yeniler ve Supabase refresh token'ı
    // DÖNDÜRÜR. Döndürülen jeton yalnız pencerenin deposunda kalıyordu; buradaki DPAPI kopyası
    // bayatlıyor, bir sonraki açılışta bayat jetonla yenileme deneniyor, GoTrue reddediyor ve
    // kayıtlı oturum SİLİNİYORDU. Pencere artık yeni oturumu backend'e geri yazıyor; burada
    // periyodik olarak okuyup diske işliyoruz.
    //
    // ⚠️ Yazma kararı `secret_store::rotasyonu_isle`de (kayıtlı oturum yoksa / boş jeton /
    // başka e-posta → YAZMAZ). Burada yalnız OKUMA ve tetikleme var.
    // ⚠️ Backend ölünce görev kendiliğinden biter (okuma başarısız → sayaç → çık); sızıntı yok.
    oturum_rotasyon_senkronu_baslat(state.rotasyon_senkronu_aktif.clone(), port, state.session.clone());

    // Uygulamayı AYRI pencerede aç → client/profil penceresi ("main") AÇIK KALIR.
    open_app_window(app, url);
}

/// Senkron thread BİR KEZ başlar (C3/L7 çift-thread guard'ı). Bayrak `false→true` geçebiliyorsa
/// başlatılmalı (bu çağrı thread'i açar); başka thread zaten aktifse (`true`) atlanır. Saf ve
/// yan-etkisiz → doğrudan test edilebilir.
fn senkron_baslamali(aktif: &AtomicBool) -> bool {
    aktif
        .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Rotasyon-senkron döngüsünün ardışık-başarısızlık sayacı kararı (F4, denetim 2026-08-24).
///
/// `pull_desktop_session` `None` döndüğünde `kesin_olu` = `backend_is_definitely_gone(port)`
/// (TCP REDDEDİLDİ = süreç yok). Kesin-ölüyse sayaç artar ve eşikte thread çıkar; aksi halde
/// (backend CANLI ama meşgul / oturum boş `{}` — loopback 5 sn'de yanıt vermeyebilir, TCP yine de
/// KABUL edilir) sayaç SIFIRLANIR ve thread YAŞAR. "meşgul ≠ ölü": uzun AI çıkarım yükünde
/// (backend.rs session_active timeout'u tam bu yüzden 10 sn) meşgul-timeout'u "ölü" saymak thread'i
/// öldürür ve o oturumun sonraki rotasyonlarını kaçırırdı → "Beni hatırla" aralıklı geri gelirdi.
fn rotasyon_ardisik(kesin_olu: bool, ardisik: u32, esik: u32) -> (u32, bool) {
    if kesin_olu {
        let yeni = ardisik.saturating_add(1);
        (yeni, yeni >= esik)
    } else {
        (0, false)
    }
}

/// Backend'teki devir oturumunu periyodik okuyup DÖNDÜRÜLEN jetonu diske işler.
///
/// Aralık 60 sn: Supabase erişim jetonu ~1 saat yaşar, yani rotasyon seyrektir; 60 sn hem
/// "kapatmadan önce yakala" için fazlasıyla sık hem de loopback'te maliyetsizdir.
fn oturum_rotasyon_senkronu_baslat(aktif: Arc<AtomicBool>, port: u16, bellek: Arc<Mutex<Option<auth::Session>>>) {
    // ÇİFT-THREAD GUARD (C3/L7, denetim 2026-08-24): sahiplenme dalı (`start_installed` →
    // `detect_running_backend`) her Başlat'ta koşabilir ve `state.proc`a KOYMAZ; guard olmadan her
    // çağrı yeni bir thread biriktirirdi. Bir thread aktifken yenisi açılmaz.
    if !senkron_baslamali(&aktif) {
        return;
    }
    std::thread::spawn(move || {
        let root = install::default_install_root(&home_dir());
        let mut ardisik_hata = 0u32;
        loop {
            std::thread::sleep(std::time::Duration::from_secs(60));
            match backend::pull_desktop_session(port) {
                Some(s) => {
                    ardisik_hata = 0;
                    let _ = secret_store::rotasyonu_isle(&root, &s);
                    bellek_rotasyonu_uygula(&bellek, &s); // [S4] bellek de taze kalsın
                }
                None => {
                    // F4 (denetim 2026-08-24): None'ı sınıfla — backend KESİN ÖLÜ mü (TCP reddedildi)
                    // yoksa CANLI ama meşgul/oturum-boş mu? Yalnız kesin-ölüde say; meşgul-timeout
                    // (uzun AI yükü) thread'i öldürmemeli (bkz. rotasyon_ardisik).
                    let kesin_olu = backend::backend_is_definitely_gone(port);
                    let (yeni, cik) = rotasyon_ardisik(kesin_olu, ardisik_hata, 5);
                    ardisik_hata = yeni;
                    if cik {
                        break;
                    }
                }
            }
        }
        // Thread bitti → bayrağı serbest bırak: sonraki backend (farklı port) için yeniden
        // başlatılabilsin. Aksi halde guard bir daha hiç açılmaz ve rotasyon kalıcı dururdu.
        aktif.store(false, Ordering::Release);
    });
}

/// OTURUM DEVRİ (E-ÖZELLİĞİ ORTAK SÖZLEŞMESİ): client'ın Supabase oturumunu, backend ayağa
/// kalktıktan SONRA ama uygulama penceresi AÇILMADAN ÖNCE backend'e ver.
///
/// SIRA KRİTİK: pencere önce açılırsa uygulama kendi giriş ekranını çoktan çizmiş olur ve
/// kullanıcı İKİNCİ kez giriş yapar (sözleşme: "Çift giriş YOK").
/// `PEMF_REQUIRE_AUTH=1` verilmiş olsa da loopback istekleri backend'de muaftır
/// (`servers/auth.py::is_local_request`) → ek jeton gerekmez.
/// Best-effort: backend ucu yoksa (eski base.zip → 404/405) SESSİZCE geçilir; uygulama o
/// durumda kendi giriş ekranını gösterir, hiçbir şey kilitlenmez.
async fn hand_off_session(state: &tauri::State<'_, AppState>, port: u16) {
    let sess = state.session.lock().unwrap().clone();
    let Some(s) = sess else { return };
    // Bloklayan HTTP → ASLA olay-döngüsü thread'inde değil.
    let _ = tauri::async_runtime::spawn_blocking(move || {
        let _ = backend::push_desktop_session(port, &s);
    })
    .await;
}

/// Uygulamayı AYRI bir pencerede aç — client/profil penceresi ("main") AÇIK KALIR (kullanıcı isteği:
/// Başlat'a basınca client kapanmasın, uygulama ikinci pencerede açılsın). Zaten açık bir "app"
/// penceresi varsa onu tazele + öne getir (ikinci Başlat yeni pencere YIĞMASIN). WebView2 cache-bust
/// korunur. Her pencere kapanınca on_window_event Destroyed → backend GÜVENLE durur (E-stop + kill);
/// "main" açık kaldığı için "app" kapanınca kullanıcı client'a döner. Oluşturma imkânsızsa tarayıcıya düş.
fn open_app_window(app: &tauri::AppHandle, url: &str) {
    // WebView2 CACHE-BUST: kalıcı user-data-folder aynı origin'de (127.0.0.1:8000) ESKİ index.html'i
    // cache'ler → eski bundle yüklenip "hata" verir (Chrome'da yok, WebView2'de kalır). Zaman-damgalı
    // query her açılışta TAZE index.html çektirir; referans ettiği hash'li JS zaten yeni adla taze gelir.
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    let sep = if url.contains('?') { '&' } else { '?' };
    let busted = format!("{url}{sep}_={ts}");

    // Zaten açık bir uygulama penceresi varsa → SADECE öne getir. YENİDEN YÜKLEME.
    //
    // Eskiden burada koşulsuz `navigate(busted)` vardı: kullanıcı uygulamayı açıkken client'taki
    // "Başlat"a bastığında (client hâlâ "Başlat" gösterdiği için buna sık gerek duyuluyor) çalışan
    // uygulama BAŞTAN yükleniyordu → seçili profil, açık ekran ve form girdileri gidiyor, kullanıcı
    // profil seçimine geri düşüyordu. Cache-bust'ın amacı GÜNCELLEME sonrası bayat index.html'i
    // aşmaktır; ZATEN AÇIK olan pencere güncel bundle'ı çoktan yüklemiştir → tekrar bust anlamsız.
    if let Some(win) = app.get_webview_window("app") {
        let _ = win.unminimize();
        let _ = win.set_focus();
        return;
    }

    // Yeni "app" penceresi oluştur (client "main" DOKUNULMADAN açık kalır). Harici URL = localhost backend;
    // host-başlatımlı yükleme → launcher CSP'si engellemez (main-window navigate ile aynı yol).
    let parsed = match busted.parse::<tauri::Url>() {
        Ok(u) => u,
        Err(_) => {
            let _ = backend::open_browser(url);
            return;
        }
    };
    // [matris-9] Pencere maximize açılır ama kullanıcı "geri yükle" derse eski varsayılan boyut
    // 860 px'e düşüyor ve arayüz kabuğu (900 px eşiği) TELEFON düzenine geçiyordu. Asgari boyut
    // masaüstü kırılma noktasını hedefler; ekranı aşmaz (bkz. uygulama_pencere_boyutu).
    let ((uw, uh), (umw, umh)) = app
        .primary_monitor()
        .ok()
        .flatten()
        .map(|m| {
            let l = m.size().to_logical::<f64>(m.scale_factor());
            uygulama_pencere_boyutu(l.width, l.height)
        })
        .unwrap_or(((1280.0, 860.0), (900.0, 520.0)));
    let built = tauri::WebviewWindowBuilder::new(app, "app", tauri::WebviewUrl::External(parsed))
        .title("PEMF Vet")
        .inner_size(uw, uh)
        .min_inner_size(umw, umh)
        .maximized(true)
        .build();
    if built.is_err() {
        // Pencere açılamazsa (nadir) → uygulamayı tarayıcıda göster; client yine açık kalır (fail-safe).
        let _ = backend::open_browser(url);
    }
}

/// Ev dizini için ortam-değişkeni ÖNCELİK sırası (saf → test edilebilir; env yarışı yok).
fn home_var_order(windows: bool) -> (&'static str, &'static str) {
    if windows {
        ("USERPROFILE", "HOME")
    } else {
        ("HOME", "USERPROFILE")
    }
}

fn home_dir() -> std::path::PathBuf {
    // std::env::home_dir() eski Rust'larda Windows'ta yanlış davrandığı için
    // ortam değişkenlerinden çözüyoruz.
    // ⚠️ DENETİM 2026-08-04: sıra platforma göre. Windows'ta `HOME` İŞLETİM SİSTEMİNİN değil,
    // Git-Bash/MSYS/Cygwin/conda gibi araçların kurduğu bir değişkendir ve sıklıkla POSIX-tarzı
    // (`/c/Users/merta`) ya da başka bir dizin olur. NSIS kurulumu ise $LOCALAPPDATA'yı GERÇEK
    // profilden türetir. `HOME` öne alınınca launcher kurulum kökünü BAŞKA bir yerde arar →
    // "kurulu değil" sanıp ~1,3 GB'ı yeniden indirir ve çalışan backend'in `backend.port`'unu
    // bulamaz (E-stop yedeği kör kalır). Windows'un kanonik değişkeni USERPROFILE'dır.
    let (first, second) = home_var_order(cfg!(target_os = "windows"));
    // DENETİM 2026-08-04 (P3): `filter` `or_else`'ten SONRA uygulanıyordu → ilk değişken
    // TANIMLI-AMA-BOŞ ise (`set USERPROFILE=` ya da servis bağlamı) `var_os` `Some("")` döner,
    // `or_else` HİÇ çalışmaz ve boş değer filtrelenip doğrudan `temp_dir()`e düşülürdü. Yani
    // ikinci değişkene geçiş imkânsızdı. Filtreyi HER değişkene ayrı uygula.
    let al = |k: &str| std::env::var_os(k).filter(|v| !v.is_empty());
    al(first)
        .or_else(|| al(second))
        .map(std::path::PathBuf::from)
        // #146: HOME/USERPROFILE yoksa CWD-relative "." (fail-open) YERİNE mutlak temp dizini —
        // kurulumu çalışma-dizinine (öngörülemez/yazılabilir) yazma riskini keser.
        .unwrap_or_else(std::env::temp_dir)
}

#[tauri::command]
fn detect_environment() -> Environment {
    let root = install::default_install_root(&home_dir());
    // ⚠️ HER ŞEYDEN ÖNCE: yarım kalan çalışma-zamanı takasını kurtar. Güncellemenin iki `rename`i
    // arasında kapanma olduysa `runtime` diskte YOKTUR ve aşağıdaki `already_installed` kontrolü
    // "kurulu değil" der — kullanıcı, çalışan bir kurulumu olduğu hâlde sıfırdan kurulum ekranı
    // görür. (bkz. flow::yarim_takasi_kurtar)
    if pemf_launcher_core::flow::yarim_takasi_kurtar(&root) {
        eprintln!("[kurtarma] yarim kalan calisma-zamani takasi onarildi");
    }
    Environment {
        platform: platform::current().to_string(),
        launcher_version: env!("CARGO_PKG_VERSION").to_string(),
        // ⚠️ YALNIZ exe'ye BAKMA (bkz. flow::kurulum_saglam_mi): `install_profiles` atomik
        // değildir; açma sırasında kapanma olursa exe yazılmış ama `_internal/frontend` yarım
        // kalmış olabilir → client "Hazır!" der, Başlat anlaşılmaz hatayla düşer.
        already_installed: pemf_launcher_core::flow::kurulum_saglam_mi(&root),
        installed_profiles: install::read_installed_profiles(&root),
        pending_profiles: install::read_pending(&root),
        install_root: root.to_string_lossy().into_owned(),
    }
}

/// Manifest'i indir ve profil listesini döndür.
///
/// ⚠️ DENETİM 2026-08-06 (P0 — OFFLINE BOOT KİLİDİ): bu komut `async fn` DEĞİLDİ. `tauri-macros`
/// varsayılan yürütme bağlamı `Blocking`'dir (yalnız `async fn` onu `Async`'e çevirir), yani gövde
/// IPC/olay-döngüsü thread'inde SATIR İÇİ koşuyordu → manifest inene kadar TÜM client donuyordu
/// ("yanıt vermiyor"). İnternetsiz klinikte bu, "Ortam algılanıyor…" ekranında SONSUZ takılma
/// demekti. Düzeltme deseni install_and_launch ile AYNI: `async fn` + `spawn_blocking`
/// (`#[tauri::command(async)]` DEĞİL — o, bloklayan ureq çağrısını tokio worker'ına taşırdı).
#[tauri::command]
async fn fetch_profiles() -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(fetch_profiles_blocking)
        .await
        .map_err(|e| format!("manifest görevi çöktü: {e}"))?
}

fn fetch_profiles_blocking() -> Result<serde_json::Value, String> {
    // Host pinlemesi manifest'in KENDİSİ için de geçerli: zehirli bir manifest zaten her şeyin
    // girdisidir. fetch_string_pinned_budgeted: https-only + KISA connect/read timeout + KÜRESEL
    // deadline + duvar saati tavanı (DNS'e deadline uygulanamıyor) + redirect-sonrası host
    // yeniden-doğrulama + into_string ~10MB metin-DoS sınırı.
    let raw = net::fetch_string_pinned_budgeted(MANIFEST_URL)
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
    // DENETİM 2026-08-04 (P2 — sonsuz döngü): kayıtlı deneme hedefine ULAŞTIYSAK güncelleme
    // gerçekten uygulanmış → sayacı temizle. Ulaşamadıysak sayaç durur ve N denemeden sonra
    // OTOMATİK kurulum kapanır (bildirim kalır, kullanıcı elle indirebilir).
    let su_root = install::default_install_root(&home_dir());
    if let Some((tried, _)) = install::read_selfupdate_attempt(&su_root) {
        if tried == current_launcher {
            install::clear_selfupdate_attempt(&su_root);
        }
    }
    let update = manifest.launcher.as_ref().and_then(|l| {
        pemf_launcher_core::is_newer(&l.version, current_launcher).then(|| {
            serde_json::json!({
                "version": l.version,
                "url": l.url,
                "installer_url": l.installer_url,
                "sha256": l.sha256,
                "size": l.size,
                // `false` ise UI SESSİZ kurulumu ATLAR (döngü kırıcı) ama bildirimi gösterir.
                //
                // ⚠️ 2026-08-09 (Tier 1): `rollout` KAPISI EKLENDİ. Runtime katmanlarında bu fren
                // vardı ama güncellemeyi YÖNETEN bileşenin kendisinde yoktu: bozuk bir launcher
                // yayını bir sonraki açılışta sahadaki HER cihaza gidiyordu ve — runtime'ın
                // aksine — geri çekmenin yolu kalmıyordu (yeni launcher artık eskisini
                // çalıştırmıyor). Manifest'te `launcher.rollout: 0` yazmak yayını ANINDA durdurur.
                // Bildirim yine görünür; yalnız SESSİZ kurulum beklemeye alınır.
                "auto": install::selfupdate_auto_allowed(&su_root, &l.version)
                    && install::rollout_dilimi(&su_root) < l.rollout,
                "rollout_bekliyor": install::rollout_dilimi(&su_root) >= l.rollout,
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
    // ⚠️ EŞZAMANLI CLIENT KAPISI — `stop_tracked_backend`ten ÖNCE. İkinci bir client penceresi
    // açıksa ve kurulum yapıyorsa, buradan devam etmek onun `runtime.new`ini ezer VE aşağıdaki
    // durdurma onun backend'ini (muhtemelen SÜREN SEANSI) öldürür. Kilit alınamıyorsa hiçbir
    // şeye dokunmadan dönülür. (bkz. install::kurulum_kilidi_al)
    let _kilit = install::kurulum_kilidi_al(&root)?;
    // Yeniden-kurulum: çalışan backend varsa ÖNCE güvenle durdur (exe kilidi + port çakışması).
    stop_tracked_backend(&state, &root);
    // ⚠️ SIRA ÖNEMLİ (denetim 2026-08-04): migrasyon `write_pending`'DEN ÖNCE olmalı.
    // `migrate_legacy_install_root` ilk satırında `if install_root.exists() { return; }` der;
    // `write_pending` ise `create_dir_all(install_root)` yapar. Migrasyon şimdiye kadar yalnız
    // `flow::install_profiles` içinden (spawn_blocking'in İÇİNDE, yani buradan SONRA) çağrıldığı
    // için kök ARTIK VAR oluyordu ve migrasyon HER ZAMAN erken dönüyordu → eski boşluksuz
    // `PEMFVetClient` kurulumundan yükseltenler ~2.6 GB payload'u HER SEFERİNDE yeniden indiriyordu.
    // (flow.rs'teki çağrı idempotent olduğu için orada KALIYOR — kütüphane yolu da korunsun.)
    install::migrate_legacy_install_root(&root);
    // Açılışta "devam et?" için seçimi kaydet (internet kesilir/laptop kapanırsa .part + bu dosya kalır).
    install::write_pending(&root, &profiles);
    *state.progress.lock().unwrap() = None;
    state.control.store(CTL_RUN, Ordering::Relaxed);

    // Ağır iş: bloklayan çağrılar UI thread'ini dondurmasın.
    let app2 = app.clone();
    let root2 = root.clone();
    let store = state.progress.clone();
    let ctrl = state.control.clone();
    // [5.10] İptal dalı, arka plan ön-indirmesinin .part'ını koruyabilsin diye (aşağıda).
    let manifest_raw_iptal = manifest_raw.clone();
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
            // #109: açma da iptal edilebilir. Bu bir HATA değil kullanıcı kararıdır — aynı
            // "cancelled" durumuna düşmeli, yoksa UI kırmızı bir arıza mesajı gösterir.
            Err(flow::FlowError::Extract(extract::ExtractError::Cancelled)) => {
                return Ok(InstallOutcome::Cancelled)
            }
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
            // Oturumu pencere AÇILMADAN ÖNCE devret (bkz. hand_off_session).
            hand_off_session(&state, port).await;
            on_backend_ready(&app, &state, child, &url, port);
            install::clear_pending(&root); // kurulum bitti → yarım-kalma kaydını temizle
            Ok(serde_json::json!({ "status": "ready", "url": url }))
        }
        // Duraklatıldı: .part + pending KORUNUR → "Devam Et" ile Range'den sürer.
        Ok(InstallOutcome::Paused) => Ok(serde_json::json!({ "status": "paused" })),
        // İptal: yarım .part + pending SİLİNİR → seçim ekranına dön.
        Ok(InstallOutcome::Cancelled) => {
            install::clear_pending(&root);
            // [5.10] (sahip onayı 2026-08-20): eski `&[]` yorumu "yabancı .part sorunu
            // discard_pending yolundaydı" diyordu — EŞZAMANLILIKTA yanlış: ön-indirme kilidi
            // yalnız yoklayıp BIRAKIR ve kilitsiz indirir; kurulumdan ÖNCE başlamış bir arka
            // plan ön-indirmesi bu iptal sırasında hâlâ yazıyor olabilir. `&[]` onun ≤1,4 GB
            // .part'ını da siliyordu (FILE_SHARE_DELETE silmeyi kabul eder, sonraki rename
            // düşer) — discard_pending'in 2026-08-17'de kapattığı sınıfın aynısı. Aynı koruma:
            // güncel PLANIN .part'ları korunur; bu iptalin kendi aktif .part'ını net.rs zaten
            // siler, kurulu-olmayan cihazda plan boş → tümü silinir (ilk-kurulum sözleşmesi).
            install::clear_partials(&root, &flow::plan_part_paths(&manifest_raw_iptal, &root));
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
        // İDEMPOTENT: kullanıcı arada "Çıkış yap"/"Giriş yap" yapmış olabilir → oturumu tazele.
        hand_off_session(&state, port).await;
        let url = backend::app_url(port);
        open_app_window(&app, &url);
        return Ok(url);
    }

    // DENETİM 2026-08-04: BAŞKA bir launcher instance'ı (ya da çökmüş bir önceki oturum) backend'i
    // çalıştırıyor olabilir. Eskiden yalnız KENDİ state.proc'umuza bakılıyordu → İKİNCİ bir backend
    // başlatılıyor, seri portu alamadığı için donanımı süremiyor ama UI'da "boşta" görünüyordu.
    // Çalışan varsa yenisini BAŞLATMA, mevcut olanı SAHİPLEN (state.proc'a KOYMA: onu biz
    // başlatmadık, dolayısıyla pencere kapanışında ÖLDÜRME hakkımız da yok).
    if let Some(port) = backend::detect_running_backend(&root) {
        // SAHİPLENİLEN backend'e de oturumu devret (idempotent) — o süreci biz başlatmadık ama
        // kullanıcı BU client'tan giriş yaptı; uygulama yine kendi login'ini atlamalı.
        // [S4] Sahiplenilen backend BİZDEN TAZE bir oturum tutuyor olabilir (pencere döndürmüş, biz
        // kapalıyken / başka açılışta). Önce ÇEK; tazeyse belleğe+diske al; ANCAK ondan sonra devret —
        // aksi hâlde bayat jeton backend'e itilir, pencere onunla yeniler, GoTrue aileyi iptal eder.
        {
            let bellek = state.session.clone();
            let root_c = root.clone();
            let _ = tauri::async_runtime::spawn_blocking(move || {
                if let Some(s) = backend::pull_desktop_session_kisa(port, backend::PULL_TEARDOWN_TIMEOUT_S) {
                    if bellek_rotasyonu_uygula(&bellek, &s) {
                        let _ = secret_store::rotasyonu_isle(&root_c, &s);
                    }
                }
            })
            .await;
        }
        hand_off_session(&state, port).await;
        // 🔴 C3 (denetim 2026-08-24): sahiplenilen backend'in ROTASYON SENKRONU da başlamalı.
        // `on_backend_ready` burada ÇAĞRILAMAZ (child yok — süreci biz başlatmadık, `state.proc`a
        // koymuyoruz, öldürme hakkımız yok) ve senkron thread yalnız orada başlatılıyordu → pencere
        // jetonu döndürüp backend'e push eder, launcher pull ETMEZ, diskteki kopya bayatlar ve
        // sonraki açılışta SessionRevoked → "Beni hatırla" SİLİNİR (saha arızasının açık kalan kolu).
        // Guard (senkron_baslamali) çift-Başlat'ta thread biriktirmeyi önler.
        oturum_rotasyon_senkronu_baslat(state.rotasyon_senkronu_aktif.clone(), port, state.session.clone());
        let url = backend::app_url(port);
        open_app_window(&app, &url);
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
            hand_off_session(&state, port).await;
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
    // ⚠️ EŞZAMANLI CLIENT KAPISI (bkz. install_and_launch'taki not): onarım da backend'i öldürüp
    // dosyaları değiştirir; ikinci bir pencere kurulum yaparken buna girmek ikisini de bozar.
    let _kilit = install::kurulum_kilidi_al(&root)?;
    // ⚠️ DENETİM 2026-08-09 (ENGEL) — ONAR'IN AKTİF SEANS KAPISI YOKTU (hiçbir platformda).
    // `repair` de tıpkı `apply_runtime_update` gibi backend'i öldürüp dosyalarını değiştirir; yani
    // hastanın üzerinde süren bir tedaviyi kesebilirdi. Üstelik "Onar" düğmesi kullanıcıya her
    // zaman görünür ve masumca görünür.
    //
    // KATILIK FARKI (bilinçli): `apply_runtime_update` OTOMATİK çalışır ve `None` (backend yanıt
    // vermiyor) durumunda da erteler — kullanıcı bir şey istememiştir, ertelemek bedavadır.
    // `repair` ise kullanıcının BOZUK bir kuruluma karşı kasıtlı eylemidir; `None`'da da bloklamak,
    // tam da onarıma ihtiyaç duyulan anda (backend asılı) kullanıcıyı kalıcı olarak kilitlerdi.
    // Bu yüzden burada YALNIZ KESİN bilgiyle (`Some(true)`) durulur. Hasta güvenliği yine korunur:
    // `stop_tracked_backend` her iki yolda da kill'den ÖNCE `safe_stop_coils` gönderir.
    if let Some(p) = backend::detect_running_backend(&root) {
        if backend::session_active(p) == Some(true) {
            return Err("Şu anda bir seans sürüyor — onarım seans bittikten sonra yapılabilir."
                .to_string());
        }
    }
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
            // #109: açma da iptal edilebilir. Bu bir HATA değil kullanıcı kararıdır — aynı
            // "cancelled" durumuna düşmeli, yoksa UI kırmızı bir arıza mesajı gösterir.
            Err(flow::FlowError::Extract(extract::ExtractError::Cancelled)) => {
                return Ok(InstallOutcome::Cancelled)
            }
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
            hand_off_session(&state, port).await;
            on_backend_ready(&app, &state, child, &url, port);
            Ok(serde_json::json!({ "status": "ready", "url": url }))
        }
        Ok(InstallOutcome::Paused) => Ok(serde_json::json!({ "status": "paused" })),
        Ok(InstallOutcome::Cancelled) => Ok(serde_json::json!({ "status": "cancelled" })),
        Err(e) => Err(e),
    }
}

/// TIBBİ GÜVENLİK KAPISI — hastanın üzerinde seans sürüyorsa dosya değiştiren hiçbir iş yapılmaz.
///
/// `apply_self_update` ve `apply_runtime_update` AYNI kapıyı kullanır: ikisi de sonunda backend'i
/// öldürüp dosyalarını değiştirir. `None` (backend yanıt vermiyor) = BİLİNMİYOR ve BİLİNMİYOR
/// "seans yok" DEMEK DEĞİLDİR — ertelemek, süren bir seansı kesmekten her zaman ucuzdur.
///
/// ⚠️ DENETİM 2026-08-09 (ENGEL) — `#[cfg(windows)]` KALDIRILDI.
/// Kapı Windows'a kilitliydi, ama `apply_runtime_update` (base/deps/app katmanları) macOS ve
/// Linux'ta da çalışır ve orada da backend'i öldürüp dosyalarını değiştirir. Sonuç: aynı sürüm,
/// aynı akış, aynı tıbbi risk — ama koruma yalnız bir platformda DERLENİYORDU. Hasta güvenliği
/// kapısı işletim sistemine göre değişemez. (Launcher'ın KENDİ NSIS güncellemesi Windows'a özgü
/// kalır; o akışın tamamı zaten `#[cfg(windows)]` bloğunun içindedir.)
fn aktif_seans_kapisi(root: &std::path::Path) -> Result<(), String> {
    let Some(p) = backend::detect_running_backend(root) else { return Ok(()) };
    match backend::session_active(p) {
        Some(false) => Ok(()),
        Some(true) => Err(
            "Şu anda bir seans sürüyor — güncelleme seans bittikten sonra yapılacak.".to_string(),
        ),
        None => Err(
            "Backend yanıt vermiyor, seans sürüyor olabilir — güncelleme ertelendi.".to_string(),
        ),
    }
}

/// `UpdatePlan`'ı UI'nın beklediği JSON şekline çevirir (camelCase anahtarlar UI sözleşmesi).
///
/// ⚠️ AYRI FONKSİYON çünkü `check_runtime_update` dosya-sistemine bağlı (birim testte zor);
/// bu saf dönüşüm ise plan → JSON kablolamasını doğrudan test edilebilir kılar. `flow.rs`'te
/// PLAN üzerinde hesaplanan her bayrak burada UI'ya TAŞINMALI, yoksa hesap ölü kalır (C2:
/// `otomatik_durduruldu` flow'da hesaplanıp bu köprüde unutulmuştu → döngü kırıcı üretimde ölüydü).
fn plan_to_json(plan: &flow::UpdatePlan) -> serde_json::Value {
    serde_json::json!({
        "needed": plan.needed(),
        "base": plan.base,
        "deps": plan.deps,
        "app": plan.app,
        "profiles": plan.profiles,
        "bytes": plan.bytes,
        // true → paketler hazır, kurulum saniyeler sürer (açılışta yapılabilir).
        // false → önce ARKA PLANDA inecek, kurulum SONRAKİ açılışta.
        "cached": plan.cached,
        "rolloutPending": plan.rollout_bekliyor,
        // GERİ ÇAĞIRMA: kurulu sürüm asgarinin altında → rollout ezildi, güncelleme zorunlu.
        // UI bunu AYRICA gösterir; sessizce beklemek geri çağırmanın amacını boşa çıkarır.
        "recall": plan.zorunlu,
        // C2 GERİ-ALMA DÖNGÜ KIRICI (denetim 2026-08-24): bu hedef 2 kez sağlık kapısından
        // geçemedi → deneme sınırı doldu. UI (`index.html`) bu bayrağı okuyup otomatik kurulumu
        // DURDURUR (`plan.otomatik_durduruldu` → rtBlocked). ⚠️ flow.rs bayrağı hesaplıyordu ama bu
        // köprü onu HİÇ taşımıyordu → bozuk yayın her açılışta yeniden kurulup geri alınıyordu.
        "otomatik_durduruldu": plan.otomatik_durduruldu,
    })
}

/// Diskteki kurulum manifest'e göre bayat mı? (AĞA ÇIKMAZ — manifest UI'da zaten çekilmiştir.)
///
/// SAHİP KARARI 2026-08-08: kullanıcı "Onar"a basmasın; client açılışta kendi anlasın.
#[tauri::command]
fn check_runtime_update(manifest_raw: String) -> Result<serde_json::Value, String> {
    let root = install::default_install_root(&home_dir());
    // Kaydı olmayan ESKİ kurulumlarda profil sha'larını önce benimse — yoksa üç profil birden
    // (~2,2 GB) boşuna iner. Base bilerek kapsam dışı: o gerçekten değişmiştir.
    let _ = flow::adopt_unknown_models(&manifest_raw, &root);
    let plan = flow::pending_updates(&manifest_raw, &root).map_err(|e| e.to_string())?;
    Ok(plan_to_json(&plan))
}

/// ARKA PLAN İNDİRME — paketleri önbelleğe çeker, kuruluma DOKUNMAZ, UI'ı BLOKLAMAZ.
///
/// SAHİP KARARI 2026-08-08: "güncelleme açılışta kimseyi bekletmesin". Kullanıcı uygulamayı
/// normal kullanırken paketler iner; kurulum bir sonraki açılışta, paketler hazırken yapılır.
#[tauri::command]
async fn prefetch_runtime_update(
    state: tauri::State<'_, AppState>,
    manifest_raw: String,
) -> Result<serde_json::Value, String> {
    let root = install::default_install_root(&home_dir());
    // ⚠️ DENETİM 2026-08-16 (Bulgu 3) — DENE-VE-VAZGEÇ, tam kilit DEĞİL.
    // Ön-indirme 45 dakika sürebilir; kilidi o süre boyunca TUTSAYDI kullanıcı "Onar"/profil
    // kurulumu yapamaz ve "başka pencere güncelleme yapıyor" hatası alırdı — oysa bu akışın
    // TEK amacı kullanıcıyı bekletmemek. Bu yüzden kilit yalnız YOKLANIR: bir kurulum/onarım
    // sürüyorsa ön-indirme bu turu ATLAR (isteğe bağlıdır, sonra tekrar denenir). Kilit
    // hemen bırakılır; indirme onsuz sürer.
    // Kalan risk BİLİNÇLİ: ön-indirme başladıktan SONRA kurulum başlarsa ikisi aynı önbellek
    // `.part` dosyasına yazabilir. Bu AĞACI bozmaz (ön-indirme kuruluma hiç dokunmaz) ve
    // `ensure_package` sha doğruladığı için bozuk indirme kabul edilmez, yalnız tekrarlanır.
    match install::kurulum_kilidi_al(&root) {
        Ok(k) => drop(k),
        Err(_) => {
            return Ok(serde_json::json!({
                "status": "skipped",
                "reason": "kurulum/onarım sürüyor — ön-indirme ertelendi"
            }))
        }
    }
    // İlerleme AYRI kanala yazılır (`prefetch`), kurulum ekranını ele geçirmez — ama artık
    // sessiz de değil: kullanıcı "arka planda iniyor" notunun yanında yüzdeyi görür.
    // ⚠️ `tauri::State` Send değil → Arc'ı spawn_blocking'e taşımadan ÖNCE klonla (install
    // yolundaki desenin aynısı).
    let store = state.prefetch.clone();
    *store.lock().unwrap() = None;
    let store_is = store.clone();
    // ⚠️ SAHA BİLDİRİMİ 2026-08-28: burada `&|| net::Control::Continue` SABİT veriliyordu.
    // Sonuç: 1,4 GB'lık arka plan indirmesi başladıktan sonra kullanıcının DURDURMA YOLU YOKTU —
    // ekranda yalnız ilerleme çubuğu vardı, düğme yoktu. Oysa `net::Control` (Pause/Cancel) ve
    // `pause_install`/`cancel_install` komutları ZATEN mevcuttu ve kurulum yolunda çalışıyordu;
    // bağlanmamış olan tek yer arka plan indirmesiydi. Ölçülen sınıf: yetenek var, kablo yok.
    // ⚠️ Bayrağı SIFIRLAMIYORUZ (`store(CTL_RUN)` YOK): kurulum yolları turun başında sıfırlar,
    // ama ön-indirme kullanıcının önceki "duraklat" kararını EZMEMELİ. Duraklatılmışken tur
    // açılırsa ilk yığında durur ve `.part` korunur.
    let ctl = state.control.clone();
    let sonuc = tauri::async_runtime::spawn_blocking(move || {
        // Kurulum yolundakiyle AYNI yazıcı (throttle + son-parça istisnası) — tek kaynak.
        let mut on = snapshot_yazici(store_is, 150);
        flow::prefetch_updates(&manifest_raw, &root, &mut on, &|| match ctl.load(Ordering::Relaxed)
        {
            CTL_PAUSE => net::Control::Pause,
            CTL_CANCEL => net::Control::Cancel,
            _ => net::Control::Continue,
        })
        // ⚠️ Durum kodu HATA TİPİNDEN çıkarılır, mesaj METNİNDEN değil: metne bakan bir
        // ayrım, hata cümlesi bir gün düzenlendiğinde SESSİZCE bozulur ve kullanıcının
        // "duraklat"ı yeniden "indirme tamamlanamadı" diye görünmeye başlar.
        .map_err(|e| {
            let kod = match &e {
                flow::FlowError::Net(net::NetError::Paused) => "paused",
                flow::FlowError::Net(net::NetError::Cancelled) => "cancelled",
                _ => "failed",
            };
            (kod, e.to_string())
        })
    })
    .await
    .map_err(|e| format!("arka plan indirme çöktü: {e}"))?;
    // Bittiğinde kanalı KAPAT: UI bunu "indirme tamamlandı" olarak okur ve yoklamayı durdurur.
    // Aksi halde son snapshot ekranda donmuş bir yüzde olarak kalırdı.
    *store.lock().unwrap() = None;
    match sonuc {
        Ok(()) => Ok(serde_json::json!({ "status": "prefetched" })),
        // ⚠️ KULLANICI KARARI ≠ HATA (saha bildirimi 2026-08-28). "Duraklat"/"İptal"e basan
        // kullanıcıya "indirme tamamlanamadı" demek yanlış geri bildirimdir: arıza sanır ve
        // `.part` korunmuşken (Pause) sanki kaybolmuş gibi okunur. UI ikisini ayrı gösterir.
        Err((kod, sebep)) => Ok(match kod {
            "paused" => serde_json::json!({ "status": "paused" }),
            "cancelled" => serde_json::json!({ "status": "cancelled" }),
            // Ağ hatası sessizce yutulur: bu isteğe bağlı bir ön-indirmedir.
            _ => serde_json::json!({ "status": "failed", "reason": sebep }),
        }),
    }
}

/// Bayat paketleri yenile (backend'i durdurur, günceller, BAŞLATMAZ — UI "Hazır"a döner).
///
/// Akış `repair` ile aynı iskelettir; farkı yalnız DEĞİŞENİ indirmesi ve öncesinde aktif-seans
/// kapısından geçmesidir. Duraklat/İptal aynı `state.control` üzerinden çalışır → 1,3 GB'lık bir
/// indirme kullanıcıyı açılışta hapsedemez.
#[tauri::command]
async fn apply_runtime_update(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    manifest_raw: String,
) -> Result<serde_json::Value, String> {
    let root = install::default_install_root(&home_dir());
    // ⚠️ DENETİM 2026-08-16 (Bulgu 3): KURULUM KİLİDİ YOKTU.
    // `install_and_launch`, `repair` ve `uninstall` bu kilidi alıyordu; AYNI runtime ağacını
    // değiştiren OTO-GÜNCELLEME almıyordu. Tek-instance koruması da yok → ikinci bir client
    // penceresi ya da kullanıcının "Onar"a basması ile iki akış `runtime.new`'e birlikte yazıp
    // takas edebiliyordu. Kilit ELDE EDİLEMEZSE güncelleme yapılmaz: sonraki açılışta tekrar
    // denenir (paketler önbellekte, maliyeti yok).
    let _kilit = install::kurulum_kilidi_al(&root)?;
    // ⚠️ 2026-08-09: `#[cfg(windows)]` kaldırıldı — bu akış mac/Linux'ta da backend'i öldürür.
    aktif_seans_kapisi(&root)?;

    // Kapıdan geçtik → backend'i GÜVENLE durdur (E-stop → kill; stop_tracked_backend bunu yapar).
    stop_tracked_backend(&state, &root);
    *state.progress.lock().unwrap() = None;
    state.control.store(CTL_RUN, Ordering::Relaxed);

    let app2 = app.clone();
    let root2 = root.clone();
    let store = state.progress.clone();
    let ctrl = state.control.clone();
    // Güncelleme + SAĞLIK KAPISI tek blokta: yeni sürüm takas edilir, backend başlatılır
    // (`start_and_wait` zaten `/api/health` bekler → başlaması sağlığın KANITIdır). Başlayamazsa
    // eski sürüme DÖNÜLÜR. Böylece bozuk bir yayın kliniği çalışmaz hâlde bırakamaz.
    let bellek2 = state.session.clone(); // [S4] geri-alma dalındaki teardown için (closure'a taşınır)
    let sonuc: Result<GuncellemeSonucu, String> = tauri::async_runtime::spawn_blocking(move || {
        let mut on = progress_reporter(app2, store);
        let control = || match ctrl.load(Ordering::Relaxed) {
            CTL_PAUSE => net::Control::Pause,
            CTL_CANCEL => net::Control::Cancel,
            _ => net::Control::Continue,
        };
        let geri = match flow::update_installed(&manifest_raw, &root2, &mut on, &control) {
            Ok(g) => g,
            // Duraklat/İptal kullanıcı kararıdır, arıza değil → UI kırmızı hata göstermesin.
            Err(flow::FlowError::Net(net::NetError::Paused)) => return Ok(GuncellemeSonucu::Duraklatildi),
            Err(flow::FlowError::Net(net::NetError::Cancelled)) => return Ok(GuncellemeSonucu::Iptal),
            Err(flow::FlowError::Extract(extract::ExtractError::Cancelled)) => {
                return Ok(GuncellemeSonucu::Iptal)
            }
            Err(e) => {
                // 🔴 C2 (denetim 2026-08-24): sağlık kapısı geri alması (aşağıda) deneme sayacını
                // artırıyordu ama `update_installed` İÇİNDEKİ DETERMİNİSTİK hatalar (kilitli model /
                // AV karantinası / eksik-exe / bozuk manifest) sayılmıyordu → o sınıf döngü
                // kırıcısına (`otomatik_durduruldu`) HİÇ takılmadan her açılışta backend'i öldürüp
                // ~1,19 GB açıp geri alıyordu. Cancel/Pause/Extract-Cancel yukarıda ayrıldı; GEÇİCİ
                // ağ hataları `hata_deterministik_mi`de dışlanır (yeniden denenir, bloklama yok).
                if flow::hata_deterministik_mi(&e) {
                    flow::geri_almayi_kaydet(&root2, &manifest_raw);
                }
                return Err(e.to_string());
            }
        };
        if !geri.bir_sey_yapildi() {
            return Ok(GuncellemeSonucu::DegisiklikYok);
        }
        match flow::start_backend(&root2, &mut on) {
            Ok((child, url, port)) => {
                // ⚠️ DENETİM 2026-08-23 (C5): "AYAKTA" ≠ "KULLANILABİLİR".
                // `wait_for_health` HTTP 200 + nonce ölçer; backend AYNI yanıtta `dbReady` alanını
                // da yayınlar ve `/api/session/start` tam ona bakıp 503 döner. DB tarafını bozan
                // bir yayında cihaz "sağlıklı" görünür, güncelleme ONAYLANIR ve `runtime.old`
                // SİLİNİR → klinik hiçbir seans açamaz ve otomatik geri dönüş yolu kalmaz.
                //
                // ⚠️ Bu kontrol `wait_for_health`E EKLENMEZ (backend'in belgeli kararı): DB
                // bozukken bile ACİL DURDURMA çalışmalıdır; sağlığı düşürmek onu da düşürürdü.
                // Bu yüzden ölçüm burada, YALNIZ onaylama kararında yapılır.
                //
                // ⚠️ Yalnız `Some(false)` geri alır. `None` = BİLİNMİYOR (eski backend alanı
                // yansıtmaz) → normal onaylanır; bilinmeyeni "bozuk" saymak sahadaki eski
                // sürümleri güncellenemez yapardı.
                if backend::db_hazir_mi(port) == Some(false) {
                    // ⚠️ TIBBİ GÜVENLİK: yeni sürümü durdururken de sıra E-stop → kill.
                    // `stop_backend_for_teardown` bu değişmezi tek yerde tutuyor; burada
                    // `child.kill()` çağırmak bobinleri enerjili bırakabilirdi.
                    stop_backend_for_teardown(Some((child, port)), &root2, bellek2.clone());
                    flow::geri_almayi_kaydet(&root2, &manifest_raw);
                    let geri_hata =
                        flow::guncellemeyi_geri_al(&root2, &geri).err().map(|x| x.to_string());
                    return Ok(GuncellemeSonucu::GeriAlindi {
                        sebep: "yeni sürüm açıldı ama tıbbi kayıt veritabanı hazır değil — \
                                cihaz hiçbir seans başlatamazdı; eski sürüme dönüldü"
                            .to_string(),
                        geri_alma_hatasi: geri_hata,
                    });
                }
                flow::guncellemeyi_onayla(&root2, &geri);
                // C2: gerçekten çalıştı → döngü-kırıcı sayacı sıfırla (bir sonraki gerçek
                // güncelleme eski başarısızlıkların kalıntısına takılmasın).
                install::clear_runtime_attempt(&root2);
                Ok(GuncellemeSonucu::Hazir(child, url, port))
            }
            Err(e) => {
                // SAĞLIK KAPISI DÜŞTÜ → eski sürüme dön.
                // ⚠️ DENETİM 2026-08-23 (C2): eskiden burada HİÇBİR iz bırakılmıyordu ("disk
                // bilinmiyorda kalır, sonraki açılış yeniden dener") → bozuk bir yayın her
                // açılışta aynı pahalı döngüyü tekrarlıyordu. Artık deneme sayılıyor; sınır
                // dolunca yalnız OTOMATİK kurulum durur, bildirim ve elle "Onar" açık kalır.
                flow::geri_almayi_kaydet(&root2, &manifest_raw);
                let geri_hata = flow::guncellemeyi_geri_al(&root2, &geri).err().map(|x| x.to_string());
                Ok(GuncellemeSonucu::GeriAlindi {
                    sebep: e.to_string(),
                    geri_alma_hatasi: geri_hata,
                })
            }
        }
    })
    .await
    .map_err(|e| format!("güncelleme görevi çöktü: {e}"))?;

    match sonuc? {
        GuncellemeSonucu::Hazir(child, url, port) => {
            hand_off_session(&state, port).await;
            on_backend_ready(&app, &state, child, &url, port);
            Ok(serde_json::json!({ "status": "ready", "url": url }))
        }
        GuncellemeSonucu::DegisiklikYok => Ok(serde_json::json!({ "status": "noop" })),
        GuncellemeSonucu::Duraklatildi => Ok(serde_json::json!({ "status": "paused" })),
        GuncellemeSonucu::Iptal => Ok(serde_json::json!({ "status": "cancelled" })),
        GuncellemeSonucu::GeriAlindi { sebep, geri_alma_hatasi } => Ok(serde_json::json!({
            "status": "rolled_back",
            "reason": sebep,
            "rollback_error": geri_alma_hatasi,
        })),
    }
}

/// `apply_runtime_update`'in iç sonucu — `Child` Serialize edilemediği için ayrı tip.
enum GuncellemeSonucu {
    Hazir(std::process::Child, String, u16),
    DegisiklikYok,
    Duraklatildi,
    Iptal,
    /// Yeni sürüm AÇILAMADI → eskiye dönüldü. `geri_alma_hatasi` doluysa disk elle onarım ister.
    GeriAlindi {
        sebep: String,
        geri_alma_hatasi: Option<String>,
    },
}

/// Uygulamayı kaldır — Windows'ta kayıtlı NSIS uninstaller'ı (`uninstall.exe`) başlatır.
///
/// NEDEN süreç-içi silme DEĞİL: `install_root` (%LOCALAPPDATA%\PEMF Vet Client) ÇALIŞAN launcher
/// exe'sini (`PEMFVetClient.exe`) + `uninstall.exe`'yi İÇERİR → `remove_dir_all` çalışan kendi
/// exe'sini silemez → **os error 5 (erişim engellendi)**. Windows-doğru yol: Denetim Masası'ndakiyle
/// AYNI kayıtlı uninstaller'ı ayrı süreç başlat + launcher'dan çık. NSIS uninstaller kendini $TEMP'e
/// kopyalar (böylece $INSTDIR'ı silebilir), launcher+runtime+ai_models'i kaldırır, 'uygulama verisini
/// sil' checkbox'ını sunar (işaretsiz = indirilenleri koru → yeniden kurulum hızlı) ve PREUNINSTALL
/// hook'unda bobinlere E-stop atar (windows/hooks.nsi). Hasta DB'si (%APPDATA%\PEMF_GUI) KVKK: KORUNUR.
///
/// TIBBİ GÜVENLİK: uninstaller'ı başlatmadan önce burada da E-stop + backend/child (mosquitto/
/// cloudflared) kill yapılır — hook zaten yapar, bu ekstra kemer + runtime dosya-kilidini bırakır.
/// ⚠️ DENETİM 2026-08-06 (P0 — UI DONMASI): bu komut da SENKRON'du ve gövdesi `stop_tracked_backend`
/// içinde `safe_stop_coils` (worst-case ~11,6 sn) + 800 ms uyku + `taskkill` çalıştırıyordu; hepsi
/// IPC/olay-döngüsü thread'inde. Kullanıcı "Kaldır"a bastığında client on saniye "yanıt vermiyor"
/// oluyordu. İş `spawn_blocking`'e alındı.
/// 🔴 KIRMIZI ÇİZGİ (TIBBİ GÜVENLİK): E-stop → kill sırası AYNEN korunur ve `app.exit(0)` iş
/// BİTMEDEN çağrılmaz — aksi halde süreç, bobin durdurma uçarken çıkar (ESP bobinleri 6-8'in
/// link-watchdog'u YOKTUR).
#[tauri::command]
async fn uninstall(app: tauri::AppHandle, state: tauri::State<'_, AppState>) -> Result<(), String> {
    let root = install::default_install_root(&home_dir());
    // ⚠️ EŞZAMANLI CLIENT KAPISI: diğer pencere kurulum yaparken kaldırmaya başlamak, yarı
    // kurulmuş bir ağacı silmeye çalışmak demektir (dosya kilitleri + yarım kalan artıklar).
    let _kilit = install::kurulum_kilidi_al(&root)?;
    // Süreç + port'u kilitten ATOMİK al (state.proc `Send` değil → spawn_blocking'e taşınamaz;
    // durdurma işini burada kendi thread'imizde yapıp SONUCU bekliyoruz).
    let tracked = state.proc.lock().unwrap().take();
    let root2 = root.clone();
    let bellek2 = state.session.clone(); // [S4]
    tauri::async_runtime::spawn_blocking(move || {
        stop_backend_for_teardown(tracked, &root2, bellek2);
    })
    .await
    .map_err(|e| format!("kaldırma hazırlığı çöktü: {e}"))?;

    #[cfg(windows)]
    {
        // ⚠️ GÜVENLİK DUVARI TEMİZLİĞİ (kaldırma denetimi 2026-08-29). Kural EKLENİYOR ama
        // SİLEN KOD HİÇ YOKTU: kaldırmadan sonra `PEMF Backend API` + `PEMF UDP Discovery`
        // kuralları makinede kalıyor ve artık var olmayan bir exe'yi işaret ediyordu. NSIS
        // kancasının kendi notu bunu "ayrı ADMIN uninstaller'ın işi" sayıyor — ama backend'i
        // CLIENT kuruyor; o ayrı admin kurulumu hiç yapılmamış makinelerde kurallar hiçbir
        // kaldırıcıya ait değildi (bu makinede ölçüldü: 3 yetim kural).
        //
        // ⚠️ BURADA yapılır, NSIS kancasında DEĞİL: kanca currentUser bağlamında koşar ve
        // yükseltemez; client ise UAC isteyebilir.
        // ⚠️ HATA YUTULUR: kullanıcı UAC'yi reddederse kaldırma NORMAL devam eder — yetim bir
        // firewall kuralı, kaldırmayı düşürmeyi haklı çıkarmaz. Tam temizlik için
        // `scripts/pemf_teardown.ps1` zaten var.
        if let Err(e) = ps_yukselterek_kos(&pemf_launcher_core::firewall::silme_betigi()) {
            eprintln!("[uninstall] güvenlik duvarı kuralları temizlenemedi (yok sayıldı): {e}");
        }

        // uninstall.exe launcher exe'sinin YANINDADIR (NSIS ikisini de $INSTDIR'a koyar). current_exe
        // üzerinden bul → özel kurulum dizinlerinde de doğru (sabit yol varsaymaz).
        let uninstaller = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.join("uninstall.exe")))
            .filter(|p| p.exists())
            .ok_or_else(|| {
                "Kaldırıcı (uninstall.exe) bulunamadı. Windows 'Ayarlar → Uygulamalar'dan kaldırabilirsiniz."
                    .to_string()
            })?;
        spawn_uninstaller_detached(&uninstaller)?;
        app.exit(0); // launcher ÇIKMALI ki uninstaller çalışan PEMFVetClient.exe'yi silebilsin
        Ok(())
    }
    #[cfg(not(windows))]
    {
        let _ = app; // mac/linux: platform paket-kaldırıcısı ayrı → indirilen payload'u temizle
        install::remove_install(&root)
            .map_err(|e| format!("Kaldırma başarısız (uygulama çalışıyor olabilir): {e}"))
    }
}

// ══════════════════════════════════════════════════════════════════════════════════════════
//  CLIENT GİRİŞİ (Supabase) + "Beni hatırla"
// ══════════════════════════════════════════════════════════════════════════════════════════

/// UI'ya dönen giriş durumu. ⚠️ JETON İÇERMEZ — UI'da gösterilmez, loglanmaz.
#[derive(serde::Serialize)]
struct AuthStatus {
    logged_in: bool,
    email: String,
    /// "fresh" = jeton sunucudan tazelendi · "cached" = kayıtlı oturumla çevrimdışı devam
    /// · "none" = giriş gerekli.
    source: &'static str,
    /// Sunucuya ulaşılamadı (UI "çevrimdışı" rozetini bununla gösterir).
    offline: bool,
    /// Bu platformda "Beni hatırla" mümkün mü (Windows=DPAPI; diğerleri: kalıcı depo YOK).
    persist_available: bool,
}

impl AuthStatus {
    fn cikis_yapildi(offline: bool) -> Self {
        Self {
            logged_in: false,
            email: String::new(),
            source: "none",
            offline,
            persist_available: secret_store::available(),
        }
    }
    fn giris_yapildi(email: &str, source: &'static str, offline: bool) -> Self {
        Self {
            logged_in: true,
            email: email.to_string(),
            source,
            offline,
            persist_available: secret_store::available(),
        }
    }
}

/// Açılışta çağrılır: bellekte ya da "Beni hatırla" deposunda geçerli bir oturum var mı?
///
/// ⚠️ OFFLINE KARARI (bilinçli, riskler bölümünde tartışıldı): kayıtlı bir oturum varsa ve
/// sunucuya ULAŞILAMIYORSA, jetonun süresi DOLMUŞ olsa bile kullanıcı GİRİŞ YAPMIŞ sayılır.
/// Gerekçe: bu bir YEREL cihaz + YEREL backend'dir; kimlik doğrulama internete bağlı hale
/// getirilirse internetsiz bir klinikte tedavi cihazı açılamaz — az önce (A) maddesinde
/// düzelttiğimiz kilidin aynısını kimlik katmanında geri getirmiş oluruz. Jetonun tazeliği
/// bulut senkronizasyonu için önemlidir, cihazın çalışması için değil.
#[tauri::command]
async fn auth_status(state: tauri::State<'_, AppState>) -> Result<AuthStatus, String> {
    // 1) Bu süreçte zaten giriş yapılmışsa (bellek) — ağa hiç çıkma.
    let bellek = state.session.lock().unwrap().clone();
    if let Some(s) = bellek {
        return Ok(AuthStatus::giris_yapildi(&s.email, "fresh", false));
    }

    // 2) "Beni hatırla" blob'u (işletim sistemi korumalı). Ağ YOK — yerel okuma.
    let root = install::default_install_root(&home_dir());
    let root2 = root.clone();
    let kayitli = tauri::async_runtime::spawn_blocking(move || secret_store::load(&root2))
        .await
        .map_err(|e| format!("oturum okuma görevi çöktü: {e}"))?;
    let Some(kayitli) = kayitli else {
        return Ok(AuthStatus::cikis_yapildi(false));
    };

    // 3) Jeton hâlâ tazeyse ağa çıkmaya gerek yok (açılış hızlı kalsın).
    if !kayitli.needs_refresh(auth::now_unix()) {
        *state.session.lock().unwrap() = Some(kayitli.clone());
        return Ok(AuthStatus::giris_yapildi(&kayitli.email, "cached", false));
    }

    // 4) Sessiz yenileme (duvar saati bütçeli → açılışı bloklamaz).
    let eposta = kayitli.email.clone();
    let rt = kayitli.refresh_token.clone();
    let sonuc = tauri::async_runtime::spawn_blocking(move || auth::refresh_budgeted(&rt, &eposta))
        .await
        .map_err(|e| format!("oturum yenileme görevi çöktü: {e}"))?;

    match (oturum_karari(&sonuc), sonuc) {
        (OturumKarari::Yenilendi, Ok(yeni)) => {
            let root3 = root.clone();
            let y2 = yeni.clone();
            // Yenilenen refresh_token'ı SAKLA (Supabase rotasyon yapar; eskisi geçersizleşir).
            let _ = tauri::async_runtime::spawn_blocking(move || secret_store::save(&root3, &y2)).await;
            let email = yeni.email.clone();
            *state.session.lock().unwrap() = Some(yeni);
            Ok(AuthStatus::giris_yapildi(&email, "fresh", false))
        }
        (OturumKarari::Sil, _) => {
            let root4 = root.clone();
            let _ = tauri::async_runtime::spawn_blocking(move || secret_store::clear(&root4)).await;
            Ok(AuthStatus::cikis_yapildi(false))
        }
        // ÇEVRİMDIŞI / geçici sunucu hatası → kayıtlı oturumla devam (yukarıdaki OFFLINE KARARI).
        _ => {
            let email = kayitli.email.clone();
            *state.session.lock().unwrap() = Some(kayitli);
            Ok(AuthStatus::giris_yapildi(&email, "cached", true))
        }
    }
}

/// Sessiz yenileme sonucundan çıkan KARAR (saf → birim-testlenebilir).
///
/// ⚠️ Bu ayrım hasta erişilebilirliğinin kilit noktası: "sunucuya ULAŞAMADIM" ile "sunucuya
/// ULAŞTIM ve HAYIR dedi" AYNI KOVAYA konulamaz. Birincisinde kullanıcıyı kilitlemek, internetsiz
/// bir klinikte tedavi cihazını kullanılamaz hale getirir; ikincisinde ise jeton gerçekten
/// iptal edilmiştir (parola değişti / oturum kapatıldı) ve kaydı tutmak güvenlik açığıdır.
#[derive(Debug, PartialEq, Eq)]
enum OturumKarari {
    /// Yenilendi → yeni oturumu SAKLA ve kullan.
    Yenilendi,
    /// Ulaşılamadı / geçici hata → KAYITLI oturumla ÇEVRİMDIŞI devam.
    CevrimdisiDevam,
    /// Sunucu jetonu AÇIKÇA reddetti → kaydı SİL, giriş ekranına dön.
    Sil,
}

fn oturum_karari(sonuc: &Result<auth::Session, auth::AuthError>) -> OturumKarari {
    match sonuc {
        Ok(_) => OturumKarari::Yenilendi,
        Err(auth::AuthError::SessionRevoked) => OturumKarari::Sil,
        Err(_) => OturumKarari::CevrimdisiDevam,
    }
}

/// E-posta + parola ile giriş. `remember` → oturum işletim sistemi korumalı depoya yazılır.
///
/// GÜVENLİK: parola YALNIZ burada geçer; hiçbir yere yazılmaz, hata metinlerine konmaz.
#[tauri::command]
async fn auth_login(
    state: tauri::State<'_, AppState>,
    email: String,
    password: String,
    remember: bool,
) -> Result<AuthStatus, String> {
    let (e, p) = (email.trim().to_string(), password);
    let sonuc = tauri::async_runtime::spawn_blocking(move || auth::login_budgeted(&e, &p))
        .await
        .map_err(|err| format!("giriş görevi çöktü: {err}"))?;
    // `AuthError`'ın Display'i zaten TÜRKÇE ve HTTP gövdesini yansıtmaz (bkz. core/auth.rs).
    let session = sonuc.map_err(|err| err.to_string())?;

    let root = install::default_install_root(&home_dir());
    let s2 = session.clone();
    let hatirla = remember && secret_store::available();
    let _ = tauri::async_runtime::spawn_blocking(move || {
        if hatirla {
            secret_store::save(&root, &s2);
        } else {
            // "Beni hatırla" İŞARETSİZ → oturum SÜREÇ-ÖMÜRLÜ. Önceki bir kaydı da temizle,
            // yoksa kullanıcı kutucuğu kaldırdığında eski jeton diskte kalırdı.
            secret_store::clear(&root);
        }
    })
    .await;

    let email_out = session.email.clone();
    *state.session.lock().unwrap() = Some(session);

    // Backend ZATEN çalışıyorsa (kullanıcı önce Başlat'a bastıysa) oturumu HEMEN devret —
    // uygulama bir sonraki yüklemede kendi login'ini atlar.
    if let Some(port) = calisan_backend_portu(&state).await {
        hand_off_session(&state, port).await;
    }
    Ok(AuthStatus::giris_yapildi(&email_out, "fresh", false))
}

/// Çıkış: backend'deki devredilmiş oturumu sil + yerel kaydı sil + Supabase'e bildir.
///
/// Sıra önemli: ÖNCE yerel/backend temizliği (kesin çalışır), SONRA ağ bildirimi (best-effort).
/// Böylece internet yokken de çıkış GERÇEKTEN olur.
#[tauri::command]
async fn auth_logout(state: tauri::State<'_, AppState>) -> Result<AuthStatus, String> {
    let session = state.session.lock().unwrap().take();
    let port = calisan_backend_portu(&state).await;
    let root = install::default_install_root(&home_dir());

    let _ = tauri::async_runtime::spawn_blocking(move || {
        if let Some(p) = port {
            backend::clear_desktop_session(p);
        }
        secret_store::clear(&root);
        if let Some(s) = session {
            let _ = auth::logout(&s.access_token); // best-effort, çevrimdışıysa sessizce geçer
        }
    })
    .await
    .map_err(|e| format!("çıkış görevi çöktü: {e}"))?;

    Ok(AuthStatus::cikis_yapildi(false))
}

/// Oturumun devredileceği backend portu.
///
/// ⚠️ DENETİM 2026-08-06 (JETON SIZINTISI — bu denetimde düzeltildi): burada `read_backend_port`
/// HAM okunuyordu. `backend.port` bilinçli olarak "kesin ölü" teyidi olmadan silinmez (bobinlerin
/// E-stop adresi), yani çökme/kapanma sonrası diskte bayat kalır; o portu kapan HERHANGİ bir yerel
/// süreç `auth_login` sırasında Supabase access+refresh jetonlarını alırdı. Artık diskten gelen
/// port `/api/health` imzasıyla doğrulanıyor (`backend::session_target_port`); kendi başlattığımız
/// süreç yoklanmadan kabul edilir.
///
/// `async`: doğrulama BLOKLAYAN HTTP → olay-döngüsü thread'inde çalışmamalı (bu oturumdaki P0
/// donma hatasının aynısı). Kendi sürecimiz varsa ağa hiç çıkılmaz.
async fn calisan_backend_portu(state: &tauri::State<'_, AppState>) -> Option<u16> {
    let tracked = state.proc.lock().unwrap().as_ref().map(|(_, p)| *p);
    let root = install::default_install_root(&home_dir());
    tauri::async_runtime::spawn_blocking(move || backend::session_target_port(tracked, &root))
        .await
        .ok()
        .flatten()
}

/// Son ilerleme snapshot'ını döndür (frontend kurulum/onarım sırasında ~150ms'de bir POLL eder).
/// null = henüz ilerleme yok veya temizlendi. Snapshot = `flow::Progress` JSON'u ({step, what, done, total} vb.).
/// Uygulama penceresi şu an AÇIK mı? Client, "Başlat" mı yoksa "Uygulamaya dön" mü göstereceğine
/// buna bakarak karar verir.
///
/// Neden komut + odak-yoklaması, neden `emit` DEĞİL: bu projede Tauri `emit`'in webview
/// `listen`'ine güvenilir ulaşmadığı zaten belgeli (bkz. AppState.progress — ilerleme olayları
/// bu yüzden POLL'a çevrilmişti). Kullanıcı uygulama penceresini kapatınca odak zaten client'a
/// döner; o anda tek bir yoklama yapmak hem ucuz hem kesin.
#[tauri::command]
fn app_window_open(app: tauri::AppHandle) -> bool {
    app.get_webview_window("app").is_some()
}

#[tauri::command]
fn get_progress(state: tauri::State<'_, AppState>) -> Option<serde_json::Value> {
    state.progress.lock().unwrap().clone()
}

/// ARKA PLAN ön-indirmenin son ilerleme snapshot'ı. `None` = indirme yok ya da BİTTİ.
/// UI bunu yoklar; kurulum ekranını AÇMAZ, yalnız bilgi notundaki yüzdeyi/barı günceller.
#[tauri::command]
fn get_prefetch_progress(state: tauri::State<'_, AppState>) -> Option<serde_json::Value> {
    state.prefetch.lock().unwrap().clone()
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

/// Duraklatılmış indirmeyi SÜRDÜR (saha bildirimi 2026-08-28).
///
/// ⚠️ `pause_install` vardı ama karşılığı YOKTU: kurulum yolları turun başında bayrağı zaten
/// `CTL_RUN`a çektiği için orada eksikliği görünmüyordu. Arka plan indirmesi ise bayrağı
/// BİLEREK sıfırlamaz (kullanıcının "duraklat" kararı bir sonraki turda ezilmesin diye) —
/// dolayısıyla açık bir "devam et" komutu olmadan duraklatılmış indirme SÜREKLİ duraklı kalırdı.
/// `.part` korunmuş olduğu için indirme Range ile kaldığı yerden sürer, baştan inmez.
#[tauri::command]
fn resume_install(state: tauri::State<'_, AppState>) {
    state.control.store(CTL_RUN, Ordering::Relaxed);
}

/// Açılıştaki "yarım kalan kurulum" bildirimini AT: pending kaydı + `.part` dosyalarını sil
/// (çalışan kurulum yokken kullanıcı "devam etme, iptal" derse).
///
/// ⚠️ DENETİM 2026-08-17: burası cache'teki TÜM `*.part`ları siliyordu ve bu soru ekrana tam olarak
/// arka plan ön-indirmesi BAŞLADIKTAN SONRA çıkıyor (ölçülen sıra: `check_runtime_update` →
/// `prefetch_runtime_update` → `discard_pending`). "İptal et" diyen kullanıcı, farkında olmadan
/// o an inen ≤1,4 GB'lık güncellemeyi çöpe atıyordu. Artık GÜNCEL PLANIN `.part`ları korunuyor.
/// ⚠️ Manifest YOKSA hiç silme yapılmaz: hangi `.part`ın aktif indirmeye ait olduğu bilinemez ve
/// yer kazanmak, süren bir güncellemeyi çöpe atmaktan daha az önemlidir (fail-safe).
#[tauri::command]
fn discard_pending(manifest_raw: Option<String>) -> Result<(), String> {
    let root = install::default_install_root(&home_dir());
    install::clear_pending(&root);
    if let Some(m) = manifest_raw {
        install::clear_partials(&root, &flow::plan_part_paths(&m, &root));
    }
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
    // Hedef sürüm — SONSUZ DÖNGÜ koruması için kaydedilir (bkz. install::record_selfupdate_attempt).
    version: String,
) -> Result<(), String> {
    #[cfg(not(windows))]
    {
        let _ = (&app, &state, &url, &sha256, size, &version);
        Err("Bu platformda oto-güncelleme desteklenmiyor".to_string())
    }
    #[cfg(windows)]
    {
        // GÜVENLİK: imzasız setup exe çalıştırılacak → SHA256 ZORUNLU (manifest host-pinli kaynaktan
        // geldiği için sha güven çıpasıdır). url host-pinlemesi download_to_file içinde uygulanır.
        if sha256.trim().is_empty() {
            return Err("Güncelleme SHA256 yok — güvenlik gereği atlandı".to_string());
        }
        // ⚠️ DENETİM 2026-08-04: AKTİF TEDAVİ SIRASINDA GÜNCELLEME YOK.
        // Bu akış açılışta SESSİZ çalışır ve sonunda `/S` kurulum yapar; NSIS yükseltme kancası
        // `taskkill /F /IM PEMF_Backend.exe` ile backend'i öldürür. Backend'i launcher'dan bağımsız
        // sahiplenebildiğimiz için (bkz. detect_running_backend) launcher yeniden açıldığında
        // HASTA ÜZERİNDE SÜREN bir seans olabilir; güncelleme onu yarıda keserdi. Bobinler
        // uninstaller kancasının E-stop'uyla güvene alınır — yani hasta güvenliği korunur — ama
        // tedavi yarım kalır ve veteriner sebebini göremez. Seans bitince güncelleme yapılır.
        // P1: `None` = BİLİNMİYOR. Seans durumunu öğrenemiyorsak seansı kesme riskini ALMAYIZ →
        // ertele. Kapı `aktif_seans_kapisi`'nda TEK yerde; `apply_runtime_update` de onu kullanır.
        let kurulum_koku = install::default_install_root(&home_dir());
        // ⚠️ DENETİM 2026-08-23 (C6): KURULUM KİLİDİ BURADA DA ALINIR.
        // 2026-08-16'da (Bulgu 3) kilit `apply_runtime_update`e eklenmişti; `install_and_launch`,
        // `repair` ve `uninstall` da alıyor — ağacı değiştiren akışlar arasında kilitsiz kalan
        // TEK akış self-update'ti. Oysa bu akış da en sonunda NSIS'i `/S` ile çalıştırıyor ve
        // kurulum kancası `taskkill /F /IM PEMF_Backend.exe /T` yapıyor: ikinci bir pencere o
        // sırada kurulum/onarım/runtime-güncellemesi yapıyorsa ONUN backend'i ölür, sağlık kapısı
        // düşer ve SAĞLAM bir güncelleme boşuna geri alınır (ya da ağaç yarım kalır).
        // ⚠️ `let _ =` DEĞİL `let _kilit =`: `let _` bağlaması değeri ANINDA düşürür, koruma olmaz.
        // Kilit elde edilemezse güncelleme yapılmaz — sonraki açılışta yeniden denenir
        // (installer önbellekte, maliyeti yok). Bu, `apply_runtime_update` ile aynı sözleşmedir.
        let _kilit = install::kurulum_kilidi_al(&kurulum_koku)?;
        aktif_seans_kapisi(&kurulum_koku)?;
        *state.progress.lock().unwrap() = None;
        state.control.store(CTL_RUN, Ordering::Relaxed);

        // ⚠️ DENETİM 2026-08-04: hedef SABİT bir addı (`PEMFVetClient-Update.exe`) ve batch onu
        // ~3 sn SONRA `/S` ile SESSİZCE kuruyor. Sabit + tahmin edilebilir ad iki soruna yol açar:
        //   (a) önceki bir denemeden kalan BAYAT exe aynı yolda durur (SHA doğrulaması onu yakalar
        //       ama kullanıcı sebebi anlaşılmayan bir "doğrulanamadı" hatası görür);
        //   (b) yol önceden bilindiği için dosya indirilmeden ÖNCE oraya bir şey konabilir.
        // Adı beklenen SHA'ya bağlıyoruz: farklı içerik = farklı dosya, bayat dosya zararsız,
        // yol da önceden tahmin edilemez. (Temp Windows'ta kullanıcıya özeldir; bu, aynı
        // kullanıcı olarak koşan bir saldırganı DEĞİL, kaza ve önden-yerleştirmeyi keser.)
        // Yalnız hex karakterleri al: manifest'ten gelen değer beklenmedik biçimdeyse bayt-indeksli
        // dilimleme UTF-8 sınırını bölüp PANİKLEYEBİLİRDİ (launcher'da panik = pencere kapanır).
        let sfx: String = sha256
            .trim()
            .chars()
            .filter(|c| c.is_ascii_hexdigit())
            .take(16)
            .map(|c| c.to_ascii_lowercase())
            .collect();
        let sfx = if sfx.is_empty() { "x".to_string() } else { sfx };
        let dest = std::env::temp_dir().join(format!("PEMFVetClient-Update-{sfx}.exe"));
        // Eski sürümlerin bıraktığı sabit-adlı artığı temizle (disk + karışıklık).
        let _ = std::fs::remove_file(std::env::temp_dir().join("PEMFVetClient-Update.exe"));
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
                net::download_to_file(&u, &dest2, size, &sha, &mut dl, &control)
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

        // DENETİM 2026-08-04: denemeyi installer'ı BAŞLATMADAN ÖNCE kaydet. Kurulum "başarılı"
        // olup sürüm DEĞİŞMEZSE (manifest sürümü ile paketin gerçek sürümü ayrışmışsa) bir sonraki
        // açılışta sayaç dolar ve OTOMATİK kurulum durur → sonsuz indir-kur-yeniden başlat
        // döngüsü kırılır. Sürüm gerçekten yükselirse fetch_profiles kaydı temizler.
        // ⚠️ DENETİM 2026-08-04 (P2 — KAPININ TOCTOU'SU): aktif-seans kontrolü İNDİRMEDEN ÖNCE
        // bir kez yapılıyordu. İndirme klinik hattında dakikalar sürer (ve kullanıcı
        // DURAKLATABİLİR → pencere sınırsız uzar). O sırada veteriner tedaviyi başlatırsa,
        // indirme bitince NSIS `taskkill /F /IM PEMF_Backend.exe` ile SÜREN SEANSI keserdi —
        // kapının engellemek için var olduğu sonucun aynısı. Yıkıcı adımdan HEMEN ÖNCE tekrar bak.
        {
            let root = install::default_install_root(&home_dir());
            if let Some(p) = backend::detect_running_backend(&root) {
                match backend::session_active(p) {
                    Some(true) => {
                        return Err(
                            "Seans başladı — güncelleme kuruldu değil, ertelendi. İndirilen dosya saklandı."
                                .to_string(),
                        )
                    }
                    None => {
                        return Err(
                            "Backend yanıt vermiyor, seans sürüyor olabilir — kurulum ertelendi."
                                .to_string(),
                        )
                    }
                    Some(false) => {}
                }
            }
        }
        install::record_selfupdate_attempt(&install::default_install_root(&home_dir()), &version);
        // 🔴 [F5-SELFUPDATE] (saha bildirimi 2026-09-03): "güncelleme sonrası kapatıp açınca hesaptan
        // çıkmış oluyor, e-posta+şifre yeniden isteniyor". Kök neden: bu yol `app.exit(0)` ile çıkar;
        // teardown'daki [F5] "kapanış-ÖNCESİ son oturum yakalama" YALNIZ `WindowEvent::Destroyed`
        // kancasında ve `stop_backend_for_teardown`da vardı — `app.exit()` açık pencerelere Destroyed'ı
        // güvenilir teslim etmez (ve etse bile süreç çıkışıyla yarışır). Uygulama PENCERESİ (supabase-js)
        // oturumu tazeledikçe refresh jetonunu DÖNDÜRÜR (tek-kullanımlık) ve backend posta kutusuna
        // yazar; rotasyon-senkron thread'i 60 sn'de bir çektiği için diskteki kopya son rotasyonun
        // gerisinde kalabilir. (NSIS `/S` sessiz kurulumda kancalar KOŞMAZ — backend yetim kalır; yeni
        // launcher onu sahiplenir ya da runtime güncellemesi kill_stray ile öldürür.) Bu yol tek başına
        // en fazla 1 nesil kaybettirir (GoTrue 1 nesil geriyi tolere eder) → İKİNCİL kemer. ASIL neden
        // pencerenin kalıcı localStorage kopyası (app 1.9.40, pf/src/services/supabaseAuth.ts).
        // Çözüm: relauncher'dan ÖNCE, teardown ile AYNI yardımcıyla son oturumu diske işle.
        // ⚠️ YALNIZ bu oturumun TRACKED backend'i (`state.proc`): child ALINMAZ (kill burada değil, NSIS'te);
        // `detect_running_backend`/`backend.port` (orphan) ASLA — başka sürecin jetonunu okumak
        // zehirlenmedir (bkz. f5_kapanis_sirasi_* parite testi). Kilit: f5_selfupdate_son_yakalama_var.
        {
            let tracked_port = state.proc.lock().unwrap().as_ref().map(|(_, p)| *p);
            if let Some(port) = tracked_port {
                son_oturumu_yakala(port, &install::default_install_root(&home_dir()), &state.session); // [F5] relauncher ÖNCE
            }
        }
        // İndirildi + SHA doğrulandı → sessiz kur + yeniden başlat helper'ını DETACHED başlat, sonra çık.
        // [GÜNCELLEME EKRANI] (saha bildirimi 2026-09-04): çıkıştan yeni sürüm açılana kadar ekran
        // BOŞTU (Defender'ın 265 MB setup taraması + NSIS + sabit beklemeler) → kullanıcı exe'ye
        // yeniden tıklıyordu. Sıra: işaret → bilgilendirme penceresi → batch → çık. Pencere
        // açılamazsa güncelleme YİNE sürer (eski davranış); batch başlatılamazsa işaret silinir.
        let kok = install::default_install_root(&home_dir());
        install::guncelleme_isareti_yaz(&kok, env!("CARGO_PKG_VERSION"), &version);
        let pencere = guncelleme_penceresini_ac(&sfx);
        if let Err(e) = spawn_update_relauncher(&dest, pencere.as_deref()) {
            install::guncelleme_isaretini_temizle(&kok);
            return Err(e);
        }
        app.exit(0);
        Ok(())
    }
}

/// [GÜNCELLEME EKRANI] Bilgilendirme penceresi kipi (bkz. `guncelleme_ekranini_calistir`).
const GUNCELLEME_EKRANI_ARG: &str = "--guncelleme-ekrani";
/// Boşlukta yeniden tıklanan ESKİ exe'nin sessizce çıkacağı azami işaret yaşı (sn). Kurulum bu
/// süreyi aşarsa (başarısız/asılı) uygulama yine açılabilmeli → kilit kendiliğinden çözülür.
const GUNCELLEME_KILIT_AZAMI_S: u64 = 120;
/// Bilgilendirme penceresinin kendini kapatacağı azami süre (sn) — işaret silinmese bile.
const GUNCELLEME_EKRANI_AZAMI_S: u64 = 180;
static GUNCELLEME_MODU: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

/// UI açılışta sorar: bu süreç "güncelleniyor" bilgilendirme penceresi mi? (normal açılışta false)
#[tauri::command]
fn guncelleme_modu() -> bool {
    GUNCELLEME_MODU.load(std::sync::atomic::Ordering::Relaxed)
}

/// Bilgilendirme penceresini launcher exe'sinin %TEMP%'e alınmış FARKLI ADLI kopyasından başlat.
/// Neden kopya: NSIS'in "uygulama çalışıyor" denetimi `PEMFVetClient.exe` ADINA bakar ve sessiz
/// kurulumda onu öldürür; farklı adlı kopya ne öldürülür ne de kurulum exe'sinin kilidini tutar.
/// Başarısızlık güncellemeyi DURDURMAZ (eski davranışa düşer). Kopyayı batch siler.
#[cfg(windows)]
fn guncelleme_penceresini_ac(sfx: &str) -> Option<std::path::PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let kopya = std::env::temp_dir().join(format!("PEMFVetClient-Guncelleme-{sfx}.exe"));
    let _ = std::fs::remove_file(&kopya);
    std::fs::copy(&exe, &kopya).ok()?;
    // Konsol-penceresi kapısı (core/tests/konsol_penceresi.rs): her spawn CREATE_NO_WINDOW taşır.
    // Kopya GUI alt-sisteminde (Tauri) olduğundan bayrak davranışı değiştirmez, kuralı korur.
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    std::process::Command::new(&kopya)
        .arg(GUNCELLEME_EKRANI_ARG)
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()
        .ok()?;
    Some(kopya)
}

/// Sessiz kurulum + yeniden başlatma helper'ı (Windows). Bu launcher ÇIKTIKTAN sonra bağımsız
/// çalışsın diye DETACHED bir batch başlatır: kısa bekle (launcher çıksın, exe kilidi bıraksın) →
/// setup'ı `/S` sessiz kur (NSIS eski sürümü kaldırıp yenisini kurar) → yeni launcher'ı başlat →
/// kendini sil. Tauri NSIS `currentUser` kurulumu (AppData\Local) olduğundan UAC prompt'u YOK.
/// Yeniden-başlatma batch'inin İÇERİĞİNİ üret (saf → birim-test edilebilir). Batch-enjeksiyonu
/// savunması: yollar tırnak / yeni-satır içeremez (meşru Windows yollarında bulunmaz). `ping` =
/// taşınabilir uyku (timeout.exe redirected-stdin'de çalışmaz): ~3sn bekle → sessiz kur → ~2sn → başlat.
#[cfg(windows)]
fn build_relaunch_script(installer: &str, exe: &str, eski_pid: u32, pencere: Option<&str>) -> Result<String, String> {
    for p in [Some(installer), Some(exe), pencere].into_iter().flatten() {
        if p.contains('"') || p.contains('\r') || p.contains('\n') {
            return Err("Güncelleme yolu güvensiz karakter içeriyor".to_string());
        }
    }
    let exe_adi = std::path::Path::new(exe)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("PEMFVetClient.exe");
    // Araçları TAM YOLLA çağır: PATH'te Git'in `find`i öne çıkabiliyor (geliştirici makinesi).
    const TL: &str = "%SystemRoot%\\System32\\tasklist.exe";
    const FD: &str = "%SystemRoot%\\System32\\find.exe";
    let mut s = String::from("@echo off\r\n");
    // 1) Launcher'ın çıkmasını PID ile bekle (sabit 3 sn yerine ~1 sn adımlarla; en çok ~30 sn).
    s.push_str("set /a n=0\r\n:bekle\r\n");
    s.push_str(&format!("{TL} /FI \"PID eq {eski_pid}\" 2>nul | {FD} \" {eski_pid} \" >nul\r\n"));
    s.push_str("if errorlevel 1 goto kur\r\nset /a n+=1\r\nif %n% GEQ 30 goto kur\r\n");
    s.push_str("ping -n 2 127.0.0.1 >nul\r\ngoto bekle\r\n:kur\r\n");
    // 2) Sessiz kurulum (NSIS eski dosyaların üstüne yazar; `/S`te kancalar koşmaz).
    s.push_str(&format!("\"{installer}\" /S\r\nping -n 2 127.0.0.1 >nul\r\n"));
    // 3) Kullanıcı bu arada yeni exe'yi KENDİSİ açtıysa ikinci pencere AÇMA. `/FO CSV` ŞART:
    //    tablo çıktısı görüntü adını 25 karakterde KIRPAR (ölçüldü: uzun ad hiç eşleşmedi → ikinci
    //    pencere açıldı); CSV kırpmaz. `/NH` başlığı atar.
    s.push_str(&format!("{TL} /FI \"IMAGENAME eq {exe_adi}\" /NH /FO CSV 2>nul | {FD} /I \"{exe_adi}\" >nul\r\n"));
    s.push_str(&format!("if errorlevel 1 start \"\" \"{exe}\"\r\n"));
    // 4) Bilgilendirme penceresinin kopyasını (kendini kapatınca) sil — en çok ~40 sn dene.
    if let Some(pk) = pencere {
        s.push_str("set /a k=0\r\n:sil\r\n");
        s.push_str(&format!("del \"{pk}\" >nul 2>&1\r\nif not exist \"{pk}\" goto son\r\n"));
        s.push_str("set /a k+=1\r\nif %k% GEQ 40 goto son\r\nping -n 2 127.0.0.1 >nul\r\ngoto sil\r\n:son\r\n");
    }
    s.push_str("del \"%~f0\"\r\n");
    Ok(s)
}

#[cfg(windows)]
fn spawn_update_relauncher(installer: &std::path::Path, pencere: Option<&std::path::Path>) -> Result<(), String> {
    use std::os::windows::process::CommandExt;
    const DETACHED_PROCESS: u32 = 0x0000_0008;
    const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;

    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let exe_s = exe.to_str().ok_or("launcher yolu UTF-8 değil")?;
    let inst_s = installer.to_str().ok_or("setup yolu UTF-8 değil")?;
    let pencere_s = match pencere {
        Some(p) => Some(p.to_str().ok_or("pencere yolu UTF-8 değil")?),
        None => None,
    };
    let script = build_relaunch_script(inst_s, exe_s, std::process::id(), pencere_s)?;
    // Batch adı da kuruluma özel: sabit ad, iki eşzamanlı denemede birbirini ezerdi ve
    // yol önceden bilinirdi. Kurulum exe'sinin adından türetiliyor (o da SHA'ya bağlı).
    let stem = installer
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("pemf_selfupdate");
    let bat = std::env::temp_dir().join(format!("{stem}.bat"));
    std::fs::write(&bat, script).map_err(|e| e.to_string())?;

    std::process::Command::new("cmd.exe")
        .arg("/c")
        .arg(&bat)
        .creation_flags(DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW)
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// Kaldırma batch'inin İÇERİĞİNİ üret (saf → birim-test edilebilir). Batch-enjeksiyon savunması:
/// yol tırnak/yeni-satır içeremez (meşru Windows yollarında bulunmaz). `ping` = taşınabilir uyku
/// (`timeout.exe` redirected-stdin'de çalışmaz): ~5sn bekle (launcher çıksın, `PEMFVetClient.exe`
/// kilidi kalksın) → uninstaller'ı İNTERAKTİF başlat (kullanıcı 'uygulama verisini sil' checkbox'ını
/// görsün; `/S` YOK) → batch kendini sil.
#[cfg(windows)]
fn build_uninstall_script(uninstaller: &str) -> Result<String, String> {
    if uninstaller.contains('"') || uninstaller.contains('\r') || uninstaller.contains('\n') {
        return Err("Kaldırıcı yolu güvensiz karakter içeriyor".to_string());
    }
    Ok(format!(
        "@echo off\r\n\
         ping -n 6 127.0.0.1 >nul\r\n\
         start \"\" \"{unins}\"\r\n\
         del \"%~f0\"\r\n",
        unins = uninstaller,
    ))
}

/// Kayıtlı NSIS uninstaller'ı, launcher ÇIKTIKTAN sonra çalışacak şekilde DETACHED başlat (self-update
/// relauncher'la aynı desen). Launcher exe kilidi kalkınca uninstaller $INSTDIR'ı (launcher+runtime) siler.
#[cfg(windows)]
fn spawn_uninstaller_detached(uninstaller: &std::path::Path) -> Result<(), String> {
    use std::os::windows::process::CommandExt;
    const DETACHED_PROCESS: u32 = 0x0000_0008;
    const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;

    let unins_s = uninstaller.to_str().ok_or("kaldırıcı yolu UTF-8 değil")?;
    let script = build_uninstall_script(unins_s)?;
    let bat = std::env::temp_dir().join("pemf_uninstall.bat");
    std::fs::write(&bat, script).map_err(|e| e.to_string())?;

    std::process::Command::new("cmd.exe")
        .arg("/c")
        .arg(&bat)
        .creation_flags(DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW)
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// GÜVENLİK DUVARI DURUMU — mobil uygulama kliniğe bağlanabiliyor mu?
///
/// ⚠️ DENETİM 2026-08-09 (Tier 1): backend `0.0.0.0:8000`'i dinliyor ama launcher yolunda gelen
/// kurulumda inbound kural HİÇ oluşturulmuyordu (client kurulumu `currentUser` → NSIS
/// yükseltilmiş değil; kuralları yalnız ESKİ servis kurulumu ekliyor). Sonuç: yayınlanan mobil
/// APK klinik WiFi'sinde cihaza HİÇ bağlanamıyor ve sebebi hiçbir yerde yazmıyor.
#[tauri::command]
fn firewall_durumu() -> serde_json::Value {
    use pemf_launcher_core::firewall::{durum_icin, Durum};
    // ⚠️ backend exe YOLUNU ver: Windows'un KENDİ otomatik izni de sayılsın. Yol verilmezse
    // denetim yalnız bizim adlandırılmış kurallarımıza bakar ve Windows zaten izin vermiş
    // olsa bile "engelli" der → kullanıcı GEREKSİZ bir UAC istemine itilir (sahip bildirimi
    // 2026-08-11: "eskiden buna gerek olmadan buluyordu").
    let exe = install::backend_path(&install::default_install_root(&home_dir()));
    let d = durum_icin(Some(&exe));
    serde_json::json!({
        // AÇIKÇA engellenmiş (Block kuralı) — her zaman uyar, kalıcı engel.
        "engelli": d == Durum::Engelli,
        // Henüz kural yok — backend HİÇ dinlemediyse NORMAL. Arayüz bunu yalnız backend
        // çalıştıktan SONRA uyarıya çevirir (bkz. index.html::firewallKontrol).
        "kural_yok": d == Durum::KuralYok,
        "gereksiz": d == Durum::Gereksiz,
    })
}

/// Kuralları YÜKSELTİLMİŞ olarak ekle (UAC istemi çıkar). Kullanıcı reddederse hata döner.
///
/// Launcher bilerek yükseltilmemiş çalışır (sessiz oto-güncelleme UAC'siz olsun diye) → kural
/// ekleme ancak kullanıcının AÇIK onayıyla, tek seferlik bir yükseltmeyle yapılabilir.

/// PowerShell betiğini UAC ile YÜKSELTEREK çalıştır (firewall kuralları admin ister).
///
/// ⚠️ Base64 taşıma KASITLI: betik kullanıcı-etkili yollar içerebilir; tırnak/kaçış katmanları
/// arasında bozulmasın (bkz. firewall.rs enjeksiyon notu). Konsol penceresi açılmaz.
#[cfg(windows)]
fn ps_yukselterek_kos(betik: &str) -> Result<(), String> {
    let b64 = {
        const T: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        let g: Vec<u8> = betik.encode_utf16().flat_map(|u| u.to_le_bytes()).collect();
        let mut o = String::new();
        for c in g.chunks(3) {
            let b = [c[0], *c.get(1).unwrap_or(&0), *c.get(2).unwrap_or(&0)];
            let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
            for i in 0..4 {
                if i <= c.len() {
                    o.push(T[((n >> (18 - 6 * i)) & 63) as usize] as char);
                } else { o.push('='); }
            }
        }
        o
    };
    let arg = format!(
        "Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden              -ArgumentList '-NoProfile','-NonInteractive','-EncodedCommand','{b64}'");
    let cikti = pemf_launcher_core::platform::gizli_komut("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &arg])
        .output()
        .map_err(|e| format!("Yükseltme başlatılamadı: {e}"))?;
    if !cikti.status.success() {
        return Err("Yönetici izni verilmedi.".to_string());
    }
    Ok(())
}

#[tauri::command]
fn firewall_kurali_ekle() -> Result<serde_json::Value, String> {
    #[cfg(not(windows))]
    { return Ok(serde_json::json!({ "status": "gereksiz" })); }
    #[cfg(windows)]
    {
        use pemf_launcher_core::firewall::ekleme_betigi;
        let exe = install::backend_path(&install::default_install_root(&home_dir()));
        if !exe.exists() {
            return Err("Backend henüz kurulu değil — önce kurulumu tamamlayın.".to_string());
        }
        // Ortak yardımcı (base64 + UAC) — silme yolu da aynısını kullanır, kopya yok.
        ps_yukselterek_kos(&ekleme_betigi(&exe))
            .map_err(|_| "Yönetici izni verilmedi — güvenlik duvarı kuralı eklenemedi.".to_string())?;
        Ok(serde_json::json!({ "status": "ok" }))
    }
}

/// OFF-SITE YEDEK HEDEFİ — durum (2026-08-09 denetimi, Tier 1).
///
/// ⚠️ Yedekler bugüne kadar hasta verisiyle AYNI DİSKE alınıyordu; disk arızasında ya da fidye
/// yazılımında veri VE yedek birlikte gidiyordu. Backend `PEMF_BACKUP_DIR` desteğini zaten
/// taşıyordu ama hiçbir yerde ayarlanmadığı için özellik sahada HİÇ çalışmadı.
#[tauri::command]
fn yedek_hedefi_durumu() -> serde_json::Value {
    let root = install::default_install_root(&home_dir());
    let secili = install::backup_dir_oku(&root);
    let erisilebilir = secili.as_deref().map(install::dizin_yazilabilir_mi).unwrap_or(false);
    serde_json::json!({
        "yol": secili.map(|p| p.to_string_lossy().into_owned()),
        "erisilebilir": erisilebilir,
    })
}

/// Klasör seçtir ve doğrula. Tauri dialog eklentisi YOK (yeni bağımlılık istemiyoruz) →
/// Windows'un kendi klasör seçicisi PowerShell üzerinden açılır.
#[tauri::command]
fn yedek_hedefi_sec() -> Result<serde_json::Value, String> {
    #[cfg(not(windows))]
    { return Err("Bu platformda desteklenmiyor".to_string()); }
    #[cfg(windows)]
    {
        let betik = "Add-Type -AssemblyName System.Windows.Forms; \
            $d = New-Object System.Windows.Forms.FolderBrowserDialog; \
            $d.Description = 'Yedeklerin kopyalanacagi harici disk / ag paylasimi'; \
            if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }";
        // Konsol penceresi AÇMADAN (bkz. platform::gizli_komut). Açılan klasör-seçici bir
        // WinForms diyaloğudur; onu başlatan kabuğun görünmesi gerekmez.
        let o = pemf_launcher_core::platform::gizli_komut("powershell")
            .args(["-NoProfile", "-STA", "-Command", betik])
            .output()
            .map_err(|e| format!("Klasör seçici açılamadı: {e}"))?;
        let yol = String::from_utf8_lossy(&o.stdout).trim().to_string();
        if yol.is_empty() {
            return Ok(serde_json::json!({ "status": "iptal" }));
        }
        let root = install::default_install_root(&home_dir());
        // Veri kökü makine-geneli olabilir; kıyaslamayı GERÇEK hedefle yap.
        let veri = install::cozulmus_veri_dizini(|k| std::env::var(k).ok()).unwrap_or(root.clone());
        install::yedek_hedefi_gecerli_mi(std::path::Path::new(&yol), &veri)?;
        install::backup_dir_yaz(&root, &yol).map_err(|e| format!("Kaydedilemedi: {e}"))?;
        Ok(serde_json::json!({ "status": "ok", "yol": yol }))
    }
}

/// [L adım 3 / launcher-2] PENCERE BOYUTUNU MONİTÖR ÇALIŞMA ALANINA SIĞDIR.
///
/// ÖLÇÜLEN DURUM: `tauri.conf` sabit 880×600 pencere ve 700×540 asgari boyut veriyordu.
/// 1366×768 ekranda %150 DPI ile mantıksal çalışma alanı 911×480'e düşüyor: pencere ekrandan
/// TAŞIYOR, asgari yükseklik 540 > 480 olduğu için kullanıcı KÜÇÜLTEMİYOR da. Alt kısımdaki
/// "Kur ve Başlat" düğmesi ekran dışında kalıyordu.
///
/// Dönüş: ((pencere_w, pencere_h), (asgari_w, asgari_h)) — hepsi MANTIKSAL px.
/// Kural: çalışma alanından 40 px pay bırak, 880×600'ü aşma, 640×400'ün altına inme.
fn ana_pencere_boyutu(wa_w: f64, wa_h: f64) -> ((f64, f64), (f64, f64)) {
    const PAY: f64 = 40.0;
    const TAVAN_W: f64 = 880.0;
    const TAVAN_H: f64 = 600.0;
    const TABAN_W: f64 = 640.0;
    const TABAN_H: f64 = 400.0;
    const MIN_W: f64 = 700.0;
    const MIN_H: f64 = 460.0;
    let w = (wa_w - PAY).min(TAVAN_W).max(TABAN_W);
    let h = (wa_h - PAY).min(TAVAN_H).max(TABAN_H);
    // Asgari boyut pencereden BÜYÜK olamaz: aksi hâlde kullanıcı pencereyi küçültemez ve
    // içerik ekran dışında kalır (tam da denetimde ölçülen durum).
    let min_w = MIN_W.min(w);
    let min_h = MIN_H.min(h);
    ((w, h), (min_w, min_h))
}

/// Kurulu uygulama ("app") penceresi: masaüstü kırılma noktasını (≥900 px) koruyacak kadar geniş
/// olsun ama ekranı da aşmasın. `matris-9`: geri-yükle sonrası pencere 860 px'e düşünce kabuk
/// telefon düzenine geçiyordu.
fn uygulama_pencere_boyutu(wa_w: f64, wa_h: f64) -> ((f64, f64), (f64, f64)) {
    const PAY: f64 = 40.0;
    let w = (wa_w - PAY).min(1280.0).max(700.0);
    let h = (wa_h - PAY).min(860.0).max(460.0);
    // Kabuk 900 px'te sidebar'a geçer; asgari genişlik bunu HEDEFLER ama ekranı aşmaz.
    let min_w = 900.0_f64.min(w);
    let min_h = 520.0_f64.min(h);
    ((w, h), (min_w, min_h))
}

fn main() {
    let ctx = tauri::generate_context!();
    // [GÜNCELLEME EKRANI] bilgilendirme penceresi kipi: normal açılışın hiçbiri koşmaz.
    if std::env::args().any(|a| a == GUNCELLEME_EKRANI_ARG) {
        guncelleme_ekranini_calistir(ctx);
        return;
    }
    // Güncelleme boşluğunda yeniden tıklanan ESKİ exe: sessizce çık (pencere zaten ekranda).
    // Yeni sürüm ya da bayat işaret → işaret temizlenir (pencere kapanır), normal açılış.
    if install::guncelleme_bosluguna_dusen_eski_exe_mi(
        &install::default_install_root(&home_dir()),
        env!("CARGO_PKG_VERSION"),
        GUNCELLEME_KILIT_AZAMI_S,
    ) {
        return;
    }
    tauri::Builder::default()
        .manage(AppState::default())
        // [L adım 3-4] Pencere boyutu monitör çalışma alanına göre kırpılır ve ANCAK ondan sonra
        // gösterilir (tauri.conf `visible:false`). Aksi hâlde pencere önce 880×600 çizilip sonra
        // zıplıyordu. ⚠️ Gecikmeli iş parçacığı kalıbı BİLİNÇLİ: setup içinde doğrudan yapılan
        // boyut çağrıları pencere yaratılırken uygulanan config tarafından EZİLİYOR (güncelleme
        // ekranında ölçüldü, main.rs'teki gunc kipi aynı kalıbı kullanıyor).
        // ⚠️ show() JS'e DEĞİL bu koşulsuz zamanlayıcıya bağlı: JS ayrıştırılamazsa (2026-08-29
        // arızası) JS'e bağlı bir show() görünmez donmuş uygulama üretirdi.
        .setup(|app| {
            if let Some(w) = app.get_webview_window("main") {
                let w2 = w.clone();
                std::thread::spawn(move || {
                    std::thread::sleep(std::time::Duration::from_millis(250));
                    if let Ok(Some(mon)) = w2.current_monitor() {
                        let olcek = mon.scale_factor();
                        let boyut = mon.size().to_logical::<f64>(olcek);
                        let ((pw, ph), (mw, mh)) = ana_pencere_boyutu(boyut.width, boyut.height);
                        let _ = w2.set_min_size(Some(tauri::LogicalSize::new(mw, mh)));
                        let _ = w2.set_size(tauri::LogicalSize::new(pw, ph));
                        let _ = w2.center();
                    }
                    let _ = w2.show();
                });
            }
            Ok(())
        })

        .invoke_handler(tauri::generate_handler![
            detect_environment,
            firewall_durumu,
            yedek_hedefi_durumu,
            yedek_hedefi_sec,
            firewall_kurali_ekle,
            fetch_profiles,
            install_and_launch,
            start_installed,
            repair,
            check_runtime_update,
            apply_runtime_update,
            prefetch_runtime_update,
            uninstall,
            get_progress,
            get_prefetch_progress,
            app_window_open,
            pause_install,
            cancel_install,
            resume_install,
            discard_pending,
            open_url,
            apply_self_update,
            auth_status,
            auth_login,
            auth_logout,
            guncelleme_modu
        ])
        .on_window_event(|window, event| {
            // Pencere kapanınca backend'i BIRAKMA: yetim süreç portu tutar ve sonraki açılışta
            // "port meşgul" hatası verir. AMA öldürmeden ÖNCE bobinleri GÜVENE AL (TIBBİ GÜVENLİK):
            // child.kill() sinyal göndermez → backend'in bobin-STOP graceful'ı çalışmaz, seans
            // sürerken pencere kapatılırsa bobinler hastanın üzerinde açık kalır. E-stop ile durdur.
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<AppState>() {
                    // ⚠️ SAHİPLİK KURALI (denetim 2026-08-04): yalnız BU instance'ın BAŞLATTIĞI
                    // backend durdurulur. Eskiden `kill_stray_backends()` (sistem-genelinde
                    // `taskkill /F /IM PEMF_Backend.exe /T`) ve `backend.port` silme KOŞULSUZ
                    // çalışıyordu. Tek-instance koruması olmadığı için ikinci bir client penceresi
                    // kapandığında, AKTİF TEDAVİ süren ve BAŞKASININ başlattığı backend
                    // E-STOP'SUZ öldürülüyordu — STM bobinleri 1-5'i firmware'in 1500 ms ölü-adam
                    // devresi kurtarır ama ESP bobinleri 6-8'in link-watchdog'u YOKTUR ve tek
                    // durdurma yolu broker'a ulaşan STOP publish'idir (o da backend'le birlikte ölür).
                    // #141: child+port tek kilitten atomik alınır → E-stop(port) HER ZAMAN kill'den önce.
                    // ⚠️ UI DONMASI (kullanıcı bildirimi 2026-08-06): bu blok Tauri OLAY DÖNGÜSÜ
                    // thread'inde çalışıyordu. `safe_stop_coils` bloklayan bir HTTP çağrısıdır
                    // (backend yanıt verse bile gidiş-dönüş + kill + wait + kill_stray ~1-2 sn) →
                    // uygulama penceresi kapatılınca CLIENT 1-2 sn boyunca tıklamalara yanıt
                    // vermiyordu. Worst-case ~11,6 sn (yorumda belgeli).
                    //
                    // ÇÖZÜM: işi thread'e al AMA hasta güvenliğini bozma:
                    //   • "app" kapandı → "main" (client) AÇIK kalır, süreç yaşar → arka planda
                    //     yap, UI akıcı kalsın.
                    //   • "main" kapandı → SÜREÇ ÇIKIYOR → BLOKLA (yoksa bobin durdurma yarıda
                    //     kalabilir). Ayrıca aşağıda, uçuşta bir arka-plan işi varsa `join` edilir.
                    let is_main = window.label() == "main";
                    if let Some((mut child, port)) = state.proc.lock().unwrap().take() {
                        let root = install::default_install_root(&home_dir());
                        let bellek = state.session.clone(); // [S4] job'a taşınır (F5 belleği de tazeler)
                        // `mut`: closure `child`'ı taşır ve üzerinde kill/wait çağırır (FnMut değil,
                        // FnOnce; ama gövde &mut child istediği için binding mutable olmalı).
                        let mut job = move || {
                            backend::safe_stop_coils(port);
                            son_oturumu_yakala(port, &root, &bellek); // [F5] E-stop SONRASI / kill ÖNCESİ
                            let _ = child.kill();
                            let _ = child.wait();
                            // child.kill() ÇOCUK-AĞACINI öldürmez → BİZİM spawn ettiğimiz
                            // mosquitto/cloudflared YETİM kalır ve runtime/ dosyalarını kilitler
                            // (sonraki kurulum "os error 32"). Yalnız SAHİBİYSEK ağacı temizle.
                            backend::kill_stray_backends();
                            // Temiz kapanış: bobinler durduruldu + backend öldürüldü → port dosyasını
                            // sil ki sonraki bir uninstall ölü bir porta E-stop POST'lamasın. (Çökme
                            // yolunda bu handler ÇALIŞMAZ → dosya kalır ve uninstaller E-stop'lar.)
                            clear_port_if_stopped(&root, Some(port));
                        };
                        if is_main {
                            job(); // süreç çıkıyor → bobin durdurma BİTMEDEN dönme
                        } else {
                            *state.teardown.lock().unwrap() = Some(std::thread::spawn(job));
                        }
                    }
                    // Client kapanıyorsa, "app" kapanışından kalan arka-plan işini BEKLE: süreç
                    // E-stop uçarken çıkarsa bobinler enerjili kalabilir (ESP 6-8'in watchdog'u yok).
                    if is_main {
                        if let Some(h) = state.teardown.lock().unwrap().take() {
                            let _ = h.join();
                        }
                    }
                    // SAHİBİ DEĞİLSEK: hiçbir şey öldürme ve `backend.port`'a DOKUNMA — o dosya
                    // çalışan backend'in E-stop adresidir; silersek NSIS uninstaller'ının ve
                    // onarım yolunun E-stop yedeği KÖR kalır (bobinler enerjili öldürülür).
                }
                // Client/profil penceresi ("main") kapandı → uygulama penceresini de kapat ki süreç
                // ÇIKSIN (yoksa "app" penceresi ölü-backend'le açık kalır, süreç kapanmaz). "app"
                // penceresi kapanınca ise "main" açık kaldığından süreç yaşar → kullanıcı client'a
                // döner (backend yukarıda GÜVENLE durduruldu). Böylece Başlat client'ı KAPATMAZ.
                if window.label() == "main" {
                    if let Some(appwin) = window.app_handle().get_webview_window("app") {
                        let _ = appwin.close();
                    }
                }
            }
        })
        .run(ctx)
        .expect("Tauri uygulaması başlatılamadı");
}

/// `--guncelleme-ekrani`: self-update boşluğunu dolduran KÜÇÜK bilgilendirme penceresi.
/// Backend'e, oturuma, kuruluma DOKUNMAZ; yalnız metin + hareketli bar. Kapanma: işaret dosyası
/// silinince (yeni sürüm açıldı) ya da bayatlayınca / azami süre dolunca.
fn guncelleme_ekranini_calistir(ctx: tauri::Context<tauri::Wry>) {
    use tauri::Manager as _;
    GUNCELLEME_MODU.store(true, std::sync::atomic::Ordering::Relaxed);
    let root = install::default_install_root(&home_dir());
    let sonuc = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![guncelleme_modu])
        .setup(move |app| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.set_title("PEMF Vet — güncelleniyor");
                let _ = w.set_always_on_top(true);
                // Boyut/konum: pencere yaratılırken uygulanan config (880×600, minWidth 700, center)
                // bu çağrıları `setup` içinde EZİYORDU (ölçüldü: pencere 880×600 kaldı, ekran
                // kenarına düştü). Kısa gecikmeyle, olay döngüsü yerleştikten sonra uygula.
                let w2 = w.clone();
                std::thread::spawn(move || {
                    std::thread::sleep(std::time::Duration::from_millis(250));
                    let _ = w2.set_min_size(None::<tauri::Size>);
                    let _ = w2.set_resizable(false);
                    let _ = w2.set_size(tauri::LogicalSize::new(640.0, 400.0));
                    let _ = w2.center();
                });
            }
            let h = app.handle().clone();
            std::thread::spawn(move || {
                let baslangic = std::time::Instant::now();
                loop {
                    std::thread::sleep(std::time::Duration::from_millis(400));
                    if !install::guncelleme_isareti_taze(&root, GUNCELLEME_EKRANI_AZAMI_S) {
                        break;
                    }
                    if baslangic.elapsed().as_secs() > GUNCELLEME_EKRANI_AZAMI_S {
                        break;
                    }
                }
                h.exit(0);
            });
            Ok(())
        })
        .run(ctx);
    if let Err(e) = sonuc {
        eprintln!("güncelleme penceresi açılamadı: {e}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// C2 (denetim 2026-08-24): `check_runtime_update`'in UI'ya döndürdüğü JSON, flow'un
    /// hesapladığı `otomatik_durduruldu` bayrağını TAŞIMALI. Bayrak `flow.rs`'te hesaplanıyor
    /// (`test_KRITIK_3`) ve UI okuyor (`test_KRITIK_4`) ama ARADAKİ komut köprüsü onu hiç
    /// serileştirmiyordu → döngü kırıcı üretimde ölüydü (bozuk yayın her açılışta yeniden kurulur).
    /// Bu test o köprüyü DAVRANIŞSAL olarak kilitler (isim değil, üretilen değer ölçülür).
    #[test]
    fn plan_to_json_otomatik_durduruldu_tasir() {
        let durduruldu = flow::UpdatePlan { otomatik_durduruldu: true, ..Default::default() };
        let j = plan_to_json(&durduruldu);
        assert_eq!(
            j.get("otomatik_durduruldu").and_then(|v| v.as_bool()),
            Some(true),
            "komut çıktısı otomatik_durduruldu=true'yu UI'ya taşımıyor — C2 döngü kırıcı ölü"
        );
        // KARŞIT-KANIT: false plan da açıkça false taşımalı (alanın sabit true'ya çakılmaması).
        let devam = flow::UpdatePlan { otomatik_durduruldu: false, ..Default::default() };
        assert_eq!(
            plan_to_json(&devam).get("otomatik_durduruldu").and_then(|v| v.as_bool()),
            Some(false),
            "otomatik_durduruldu koşulsuz true — normal güncelleme de bloklanır"
        );
    }

    /// F4 (denetim 2026-08-24): rotasyon döngüsü "meşgul (canlı, timeout)" ile "kesin ölü (TCP
    /// reddedildi)"yi ayırmalı. Meşgul → sayaç SIFIRLANIR, thread ASLA çıkmaz (sonraki rotasyonu
    /// yakalar); kesin-ölü → sayaç artar, eşikte çıkar. Meşgul-yoklamayı "ölü" saymak thread'i
    /// öldürür ve o oturumun rotasyonlarını kaçırırdı ("Beni hatırla" aralıklı geri gelir).
    #[test]
    fn rotasyon_ardisik_mesgulu_oldurmez() {
        // MEŞGUL/canlı-boş (kesin_olu=false): sayaç SIFIRLANIR, ASLA çıkmaz.
        assert_eq!(rotasyon_ardisik(false, 4, 5), (0, false));
        assert_eq!(rotasyon_ardisik(false, 0, 5), (0, false));
        // KESİN-ÖLÜ: 0'dan 5 kez → tam 5.'de çık, 4.'de değil.
        let mut a = 0u32;
        for i in 1..=5 {
            let (yeni, cik) = rotasyon_ardisik(true, a, 5);
            a = yeni;
            assert_eq!(cik, i == 5, "kesin-ölü {i}. yoklamada çık={cik}");
        }
        // Araya giren CANLI yoklama sayacı sıfırlar → çık gecikir (meşgul-boot arasında ölmez).
        let (a1, _) = rotasyon_ardisik(true, 0, 5); // 1
        let (a2, _) = rotasyon_ardisik(true, a1, 5); // 2
        let (a3, c3) = rotasyon_ardisik(false, a2, 5); // canlı → 0
        assert_eq!((a3, c3), (0, false));
        let (_, c4) = rotasyon_ardisik(true, a3, 5); // 1
        assert!(!c4, "sıfırlama sonrası tek kesin-ölü çıkmamalı");
    }

    /// Rust yorum-soyucu (satır + blok + string-bilinçli) — yapısal kapılar doc-comment'lerdeki
    /// token'lardan (safe_stop_coils / son_oturumu_yakala / kill) etkilenmesin.
    fn f5_yorumlari_soy(src: &str) -> String {
        let mut out = String::with_capacity(src.len());
        let mut ch = src.chars().peekable();
        #[derive(PartialEq)]
        enum S {
            Kod,
            Satir,
            Blok,
            Str,
        }
        let mut s = S::Kod;
        while let Some(c) = ch.next() {
            match s {
                S::Satir => {
                    if c == '\n' {
                        s = S::Kod;
                        out.push('\n');
                    }
                }
                S::Blok => {
                    if c == '*' && ch.peek() == Some(&'/') {
                        ch.next();
                        s = S::Kod;
                    }
                }
                S::Str => {
                    out.push(c);
                    if c == '\\' {
                        if let Some(n) = ch.next() {
                            out.push(n);
                        }
                    } else if c == '"' {
                        s = S::Kod;
                    }
                }
                S::Kod => {
                    if c == '/' && ch.peek() == Some(&'/') {
                        ch.next();
                        s = S::Satir;
                    } else if c == '/' && ch.peek() == Some(&'*') {
                        ch.next();
                        s = S::Blok;
                    } else {
                        if c == '"' {
                            s = S::Str;
                        }
                        out.push(c);
                    }
                }
            }
        }
        out
    }

    /// [F5] (denetim 2026-08-24): KAPANIŞ SIRASI değişmezi. Her teardown gövdesinde `safe_stop_coils`
    /// (E-stop, TIBBİ GÜVENLİK) hem son-yakalamadan hem kill'den ÖNCE; son-yakalama kill'den ÖNCE
    /// (backend hâlâ ayaktayken oturum okunur). Orphan/backend.port dalı son-yakalama İÇERMEMELİ
    /// (başka sürecin portundan jeton okumak = loopback-jeton-zehirlenmesi). Yorum-soyulmuş ölçülür.
    #[test]
    fn f5_kapanis_sirasi_estop_ONCE_yakalama_kill_ONCE_orphan_HARIC() {
        let soy = f5_yorumlari_soy(include_str!("main.rs"));

        // stop_backend_for_teardown gövdesi: imza → sonraki üst-seviye `\nfn `.
        let i = soy.find("fn stop_backend_for_teardown").expect("teardown fn yok");
        let son = soy[i..].find("\nfn ").map(|j| i + j).unwrap_or(soy.len());
        let govde = &soy[i..son];
        let estop = govde.find("safe_stop_coils(").expect("teardown E-stop yok");
        let yakala = govde.find("son_oturumu_yakala(").expect("teardown son-yakalama YOK (F5)");
        let kill = govde.find(".kill()").expect("teardown kill yok");
        assert!(estop < yakala, "E-stop son-yakalamadan SONRA — bobin güvenliği geciker (TIBBİ)");
        assert!(yakala < kill, "son-yakalama kill'den SONRA — backend ölmüş, oturum okunamaz (F5)");

        // Orphan (!had_tracked) dalı son-yakalama İÇERMEMELİ.
        let o = govde.find("if !had_tracked").expect("orphan dalı yok");
        let orphan_son = govde[o..].find('}').map(|j| o + j).unwrap_or(govde.len());
        let orphan = &govde[o..orphan_son];
        assert!(
            !orphan.contains("son_oturumu_yakala("),
            "orphan/backend.port dalında son-yakalama var — başka sürecin jetonunu okur (zehirlenme)"
        );

        // Destroyed job closure: E-stop → son-yakalama → kill sırası.
        let d = soy.find("let mut job = move ||").expect("Destroyed job closure yok");
        let jg = &soy[d..(d + 600).min(soy.len())];
        let de = jg.find("safe_stop_coils(").expect("job E-stop yok");
        let dy = jg.find("son_oturumu_yakala(").expect("job son-yakalama YOK (F5)");
        let dk = jg.find(".kill()").expect("job kill yok");
        assert!(de < dy && dy < dk, "Destroyed job sırası bozuk (E-stop→yakala→kill)");
    }

    /// [F5-SELFUPDATE] (saha bildirimi 2026-09-03): self-update yolu `app.exit(0)` ile çıkar; F5
    /// son-yakalama yalnız Destroyed kancası + teardown'da vardı → güncelleme sonrası açılışta
    /// bayat refresh jetonu → SessionRevoked → "Beni hatırla" parola istiyordu. Değişmez:
    /// `apply_self_update` gövdesinde `son_oturumu_yakala(` VAR, `spawn_update_relauncher(`den
    /// ve `app.exit(`ten ÖNCE gelir; port kaynağı TRACKED `state.proc`tur (orphan
    /// `detect_running_backend` DEĞİL — başka sürecin jetonunu okumak zehirlenmedir).
    /// MUTASYON: yakalama silinirse / relauncher'dan sonraya alınırsa / port orphan'dan alınırsa KIRMIZI.
    #[test]
    fn f5_selfupdate_son_yakalama_var() {
        let soy = f5_yorumlari_soy(include_str!("main.rs"));
        let i = soy.find("fn apply_self_update").expect("apply_self_update yok");
        let son = soy[i..].find("\nfn ").map(|j| i + j).unwrap_or(soy.len());
        let govde = &soy[i..son];
        let yakala = govde.find("son_oturumu_yakala(").expect("self-update son-yakalama YOK (F5-SELFUPDATE)");
        let relauncher = govde.find("spawn_update_relauncher(").expect("self-update relauncher yok");
        let cikis = govde.find("app.exit(").expect("self-update app.exit yok");
        assert!(yakala < relauncher, "son-yakalama relauncher'dan SONRA — NSIS backend'i öldürür, jeton okunamaz");
        assert!(relauncher < cikis, "relauncher app.exit'ten SONRA — sıra bozuk");
        // Port kaynağı: yakalamadan önceki EN YAKIN kaynak tracked `state.proc` olmalı (orphan değil).
        let onceki = &govde[..yakala];
        let tracked = onceki.rfind("state.proc.lock()").expect("yakalama portu tracked state.proc'tan alınmıyor");
        let orphan = onceki.rfind("detect_running_backend(").unwrap_or(0);
        assert!(tracked > orphan, "yakalama portu orphan detect_running_backend'den geliyor — zehirlenme (F5)");
    }

    /// [S4] Bellek rotasyon kuralı: aynı e-posta + dolu + DEĞİŞMİŞ refresh → uygula; boş refresh,
    /// başka e-posta, aynı jeton, giriş yok → uygulama. MUTASYON: kural gevşetilirse kırmızı.
    #[test]
    fn s4_bellek_rotasyonu_kurali() {
        let s = |email: &str, rt: &str| auth::Session { access_token: "a".into(), refresh_token: rt.into(), email: email.into(), expires_at: 0 };
        let m = s("vet@k.tr", "r1");
        assert!(bellek_rotasyonu_gerekli(Some(&m), &s("vet@k.tr", "r2")), "değişmiş jeton uygulanmalı");
        assert!(bellek_rotasyonu_gerekli(Some(&m), &s("VET@K.TR", "r2")), "e-posta büyük/küçük duyarsız");
        assert!(!bellek_rotasyonu_gerekli(Some(&m), &s("vet@k.tr", "r1")), "aynı jeton → boşuna yazma");
        assert!(!bellek_rotasyonu_gerekli(Some(&m), &s("vet@k.tr", "  ")), "boş refresh → uygulama");
        assert!(!bellek_rotasyonu_gerekli(Some(&m), &s("baska@k.tr", "r2")), "başka kullanıcı → uygulama");
        assert!(!bellek_rotasyonu_gerekli(None, &s("vet@k.tr", "r2")), "giriş yokken devralma YOK");
        let se = |rt: &str, exp: i64| auth::Session { access_token: "a".into(), refresh_token: rt.into(), email: "vet@k.tr".into(), expires_at: exp };
        assert!(bellek_rotasyonu_gerekli(Some(&se("r1", 100)), &se("r2", 200)), "daha YENİ jeton uygulanmalı");
        assert!(!bellek_rotasyonu_gerekli(Some(&se("r1", 200)), &se("r2", 100)), "daha ESKİ jeton (bayat devir ekosu) uygulanMAMALI [S4-yön]");
        assert!(bellek_rotasyonu_gerekli(Some(&se("r1", 0)), &se("r2", 100)), "mevcut expires_at bilinmiyorsa (0) kabul");
        let bellek = Mutex::new(Some(m.clone()));
        assert!(bellek_rotasyonu_uygula(&bellek, &s("vet@k.tr", "r2")));
        assert_eq!(bellek.lock().unwrap().as_ref().unwrap().refresh_token, "r2");
        assert!(!bellek_rotasyonu_uygula(&bellek, &s("vet@k.tr", "r2")), "ikinci kez aynı → false");
    }

    /// [S4] Parite: rotasyon senkron thread'i ve F5 yakalama BELLEĞİ de güncellemeli; orphan
    /// sahiplenme devirden ÖNCE çekmeli. MUTASYON: herhangi biri kaldırılırsa kırmızı.
    #[test]
    fn s4_rotasyon_bellegi_de_tazeler_ve_sahiplenme_once_ceker() {
        let soy = f5_yorumlari_soy(include_str!("main.rs"));
        let i = soy.find("fn oturum_rotasyon_senkronu_baslat").expect("rotasyon fn yok");
        let son = soy[i..].find("\nfn ").map(|j| i + j).unwrap_or(soy.len());
        assert!(soy[i..son].contains("bellek_rotasyonu_uygula("), "rotasyon thread'i belleği tazelemiyor (S4)");
        let y = soy.find("fn son_oturumu_yakala").expect("F5 fn yok");
        let yson = soy[y..].find("\nfn ").map(|j| y + j).unwrap_or(soy.len());
        assert!(soy[y..yson].contains("bellek_rotasyonu_uygula("), "F5 yakalama belleği tazelemiyor (S4)");
        let o = soy.find("if let Some(port) = backend::detect_running_backend(&root) {").expect("orphan sahiplenme yok");
        let oson = soy[o..].find("open_app_window(").map(|j| o + j).unwrap_or(soy.len());
        let blok = &soy[o..oson];
        let cek = blok.find("pull_desktop_session_kisa(").expect("sahiplenmede ÖNCE çekme yok (S4)");
        let devir = blok.find("hand_off_session(").expect("sahiplenmede devir yok");
        assert!(cek < devir, "sahiplenme devirden SONRA çekiyor — bayat itme (S4)");
    }

    /// C3/L7 (denetim 2026-08-24): rotasyon-senkron çift-thread guard'ı. İlk çağrı thread'i
    /// AÇMALI (true), aktifken ikinci çağrı ATLANMALI (false); thread bitip bayrağı serbest
    /// bıraktıktan sonra yeniden AÇILABİLMELİ (sonraki backend). Sahiplenme dalı her Başlat'ta
    /// koştuğundan bu guard olmadan thread biriktirilirdi.
    #[test]
    fn senkron_baslamali_cift_thread_onler() {
        let aktif = AtomicBool::new(false);
        assert!(senkron_baslamali(&aktif), "ilk çağrı thread'i açmalı");
        assert!(!senkron_baslamali(&aktif), "aktif thread varken ikinci çağrı atlanmalı (çift-thread yok)");
        assert!(!senkron_baslamali(&aktif), "hâlâ aktif → yine atlanmalı");
        // Thread bitişini taklit et: bayrağı serbest bırak → sonraki backend için yeniden açılabilmeli.
        aktif.store(false, Ordering::Release);
        assert!(senkron_baslamali(&aktif), "thread bittikten sonra yeni backend için yeniden açılmalı");
    }

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
            4242,
            Some(r"C:\Temp\PEMFVetClient-Guncelleme-ab.exe"),
        )
        .unwrap();
        // Sessiz kurulum (/S) + doğru setup yolu.
        assert!(s.contains("\"C:\\Temp\\PEMFVetClient-Update.exe\" /S"));
        // [GÜNCELLEME EKRANI] sabit 3 sn yerine PID bekleme; ikinci pencere açmama; kopyayı silme.
        assert!(s.contains("PID eq 4242"), "launcher çıkışı PID ile beklenmeli");
        assert!(s.contains("if %n% GEQ 30 goto kur"), "PID beklemesi sınırlı olmalı");
        assert!(s.contains("IMAGENAME eq PEMF Vet Client.exe\" /NH /FO CSV"), "çalışıyorsa yeniden başlatma; CSV = ad kırpılmaz");
        assert!(s.contains("if errorlevel 1 start \"\" \""), "start yalnız çalışmıyorsa");
        assert!(s.contains("del \"C:\\Temp\\PEMFVetClient-Guncelleme-ab.exe\""), "pencere kopyası silinmeli");
        assert!(s.contains("System32\\tasklist.exe") && s.contains("System32\\find.exe"), "araçlar tam yolla");
        assert!(!s.contains("ping -n 4 127.0.0.1"), "eski sabit 3 sn bekleme kalkmalı");
        // Pencere yoksa (kopya açılamadı) batch yine geçerli; sil-döngüsü yok.
        let s2 = build_relaunch_script("C:\\a.exe", "C:\\b.exe", 7, None).unwrap();
        assert!(s2.contains("\"C:\\a.exe\" /S") && !s2.contains(":sil"));
        assert!(build_relaunch_script("C:\\a.exe", "C:\\b.exe", 1, Some("C:\\c\".exe")).is_err());
        // Yeni launcher'ı başlat (boşluklu yol tırnaklı).
        assert!(s.contains("start \"\" \"C:\\Users\\x\\AppData\\Local\\PEMF Vet Client\\PEMF Vet Client.exe\""));
        // Kendini sil.
        assert!(s.contains("del \"%~f0\""));
        // Batch-enjeksiyonu: tırnak veya yeni-satır içeren yol → REDDET.
        assert!(build_relaunch_script("C:\\a\".exe", "C:\\b.exe", 1, None).is_err());
        assert!(build_relaunch_script("C:\\a.exe", "C:\\b\n.exe", 1, None).is_err());
        assert!(build_relaunch_script("C:\\a\r.exe", "C:\\b.exe", 1, None).is_err());
    }

    /// [GÜNCELLEME EKRANI] kaynak-paritesi: self-update kuyruğunda işaret → pencere → batch → çık
    /// sırası ve açılış bekçisinin Builder'dan ÖNCE koşması (pencere açılmadan sessiz çıkış).
    #[test]
    fn guncelleme_ekrani_sirasi_ve_acilis_bekcisi() {
        let soy = f5_yorumlari_soy(include_str!("main.rs"));
        let i = soy.find("fn apply_self_update").expect("apply_self_update yok");
        let g = &soy[i..];
        let a = g.find("guncelleme_isareti_yaz(").expect("işaret yazılmıyor");
        let b = g.find("guncelleme_penceresini_ac(").expect("pencere açılmıyor");
        let c = g.find("spawn_update_relauncher(&dest").expect("relauncher yok");
        let d = g.find("app.exit(0)").expect("exit yok");
        assert!(a < b && b < c && c < d, "sıra: işaret → pencere → batch → çık olmalı");
        let m = soy.find("fn main()").expect("main yok");
        let mm = &soy[m..];
        let kip = mm.find("GUNCELLEME_EKRANI_ARG").expect("pencere kipi yok");
        let bekci = mm.find("guncelleme_bosluguna_dusen_eski_exe_mi(").expect("açılış bekçisi yok");
        let builder = mm.find("tauri::Builder::default()").expect("builder yok");
        assert!(kip < bekci && bekci < builder, "kip ve bekçi Builder'dan ÖNCE koşmalı");
    }

    /// [GÜNCELLEME EKRANI] Elle uçtan-uca doğrulama kancası (CI'da KOŞMAZ — `--ignored`):
    /// ortam değişkenlerinden gelen parametrelerle üretilen batch'i `%TEMP%\pemf_relaunch_dump.bat`e
    /// yazar; test yürütücüsü onu gerçek cmd.exe'de sahte kurulumla çalıştırıp PID-bekleme,
    /// start-koruması ve kopya-silme davranışını ölçer.
    #[cfg(windows)]
    #[test]
    #[ignore]
    fn relaunch_script_dump_ignored() {
        let al = |k: &str| std::env::var(k).unwrap_or_default();
        let (inst, exe, pid, splash) = (al("PEMF_TEST_INSTALLER"), al("PEMF_TEST_EXE"), al("PEMF_TEST_PID"), al("PEMF_TEST_SPLASH"));
        let pid: u32 = pid.parse().unwrap_or(0);
        let s = build_relaunch_script(&inst, &exe, pid, if splash.is_empty() { None } else { Some(&splash) }).unwrap();
        std::fs::write(std::env::temp_dir().join("pemf_relaunch_dump.bat"), s).unwrap();
    }

    /// KALDIRMA: uninstaller batch'i yolu gömer + İNTERAKTİF başlatır (/S YOK) + enjeksiyon REDDEDER.
    #[cfg(windows)]
    #[test]
    fn uninstall_script_gomer_ve_enjeksiyon_reddeder() {
        let path = r"C:\Users\x\AppData\Local\PEMF Vet Client\uninstall.exe";
        let s = build_uninstall_script(path).unwrap();
        assert!(s.contains(path)); // uninstaller yolu tam gömülü
        assert!(s.contains("start \"\" \"")); // ayrı süreç başlat
        assert!(!s.contains("/S")); // SİLENT değil → kullanıcı 'veri sil' checkbox'ını görür
        assert!(s.contains("ping -n 6 127.0.0.1 >nul")); // launcher çıksın diye bekle (exe kilidi)
        assert!(s.contains("del \"%~f0\"")); // batch kendini sil
        // Batch-enjeksiyonu: tırnak / yeni-satır içeren yol → REDDET.
        assert!(build_uninstall_script("C:\\a\".exe").is_err());
        assert!(build_uninstall_script("C:\\a\n.exe").is_err());
        assert!(build_uninstall_script("C:\\a\r.exe").is_err());
    }

    /// ⚠️ OFFLINE-FALLBACK KARAR MANTIĞI (denetim 2026-08-06).
    ///
    /// "Ulaşamadım" ile "ulaştım, HAYIR dedi" AYNI davranışa düşerse iki yönlü hata olur:
    ///   • hepsini "sil" saymak → internetsiz klinikte cihaz KİLİTLENİR (tedavi yapılamaz),
    ///   • hepsini "devam" saymak → iptal edilmiş jeton süresiz kabul edilir (güvenlik).
    #[test]
    fn cevrimdisi_ile_iptal_edilmis_oturum_ayrilir() {
        let s = auth::Session {
            access_token: "a".into(),
            refresh_token: "r".into(),
            email: "vet@klinik.com".into(),
            expires_at: 0,
        };
        assert_eq!(oturum_karari(&Ok(s)), OturumKarari::Yenilendi);

        // Ağ yok → KAYITLI oturumla devam (hasta erişilebilirliği).
        assert_eq!(
            oturum_karari(&Err(auth::AuthError::Offline)),
            OturumKarari::CevrimdisiDevam,
            "internet yokken kullanici kilitlendi — internetsiz klinikte cihaz acilmaz"
        );
        // Geçici sunucu hatası da kilitlememeli.
        assert_eq!(oturum_karari(&Err(auth::AuthError::Server(503))), OturumKarari::CevrimdisiDevam);
        assert_eq!(oturum_karari(&Err(auth::AuthError::Malformed)), OturumKarari::CevrimdisiDevam);

        // Sunucu jetonu AÇIKÇA reddetti → kayıt SİLİNMELİ.
        assert_eq!(
            oturum_karari(&Err(auth::AuthError::SessionRevoked)),
            OturumKarari::Sil,
            "iptal edilmis jeton diskte birakildi — oturum devralinabilir"
        );
    }

    /// ⚠️ SÖZLEŞME: UI'ya dönen durum nesnesi JETON İÇERMEZ. (Birisi `AuthStatus`'a oturumu
    /// eklerse jetonlar webview'e ve oradan hata metinlerine/loglara sızardı.)
    #[test]
    fn auth_status_jeton_tasimaz() {
        let st = AuthStatus::giris_yapildi("vet@klinik.com", "fresh", false);
        let j = serde_json::to_string(&st).unwrap();
        for yasak in ["access_token", "refresh_token", "password", "token"] {
            assert!(!j.contains(yasak), "AuthStatus jeton alani tasiyor ({yasak}): {j}");
        }
        assert!(j.contains("vet@klinik.com") && j.contains("logged_in"));

        let bos = AuthStatus::cikis_yapildi(true);
        let j = serde_json::to_string(&bos).unwrap();
        assert!(j.contains("\"logged_in\":false") && j.contains("\"offline\":true"));
    }

    /// DENETİM 2026-08-04: Windows'ta `HOME` öncelikliydi. Git-Bash/MSYS/conda bu değişkeni
    /// kurar (sık sık `/c/Users/...` POSIX biçiminde); NSIS ise $LOCALAPPDATA'yı GERÇEK
    /// profilden türetir. Sıra yanlışsa launcher kurulumu BAŞKA yerde arar → "kurulu değil"
    /// deyip ~1,3 GB yeniden indirir ve çalışan backend'in `backend.port`'unu bulamaz.
    #[test]
    fn ev_dizini_degisken_sirasi_platforma_uygun() {
        assert_eq!(home_var_order(true), ("USERPROFILE", "HOME"), "Windows'ta USERPROFILE once olmali");
        assert_eq!(home_var_order(false), ("HOME", "USERPROFILE"), "unix'te HOME once olmali");
    }

    /// `backend.port` çalışan backend'in E-STOP adresidir. PEMF backend YOKSA (ölü ya da
    /// yabancı bir dinleyici) dosya temizlenmeli — ölü adres birikmesin.
    #[test]
    fn olu_veya_yabanci_port_dosyasi_temizlenir() {
        let d = std::env::temp_dir().join(format!("pemf_port_test_{}", std::process::id()));
        std::fs::create_dir_all(&d).unwrap();
        let f = d.join("backend.port");

        std::fs::write(&f, "65000").unwrap();
        clear_port_if_stopped(&d, Some(65000));
        assert!(!f.exists(), "olu/yabanci port icin dosya korunmus (olu adres birikir)");

        std::fs::write(&f, "bozuk").unwrap();
        clear_port_if_stopped(&d, None);
        assert!(!f.exists(), "gecersiz port dosyasi temizlenmedi");

        let _ = std::fs::remove_dir_all(&d);
    }

    /// ⚠️ ASIL GÜVENLİK DALI — backend HÂLÂ AYAKTAYKEN `backend.port` KORUNMALI.
    ///
    /// Bu dosya çalışan backend'in tek E-STOP adresidir; NSIS uninstaller ve onarım yolu
    /// bobinleri durdurmak için SADECE onu okur. `child.kill()`/`taskkill` başarısız olur da
    /// dosya yine silinirse, kaldırma E-stop'suz `taskkill /F` çalıştırır ve ESP bobinleri 6-8
    /// HASTANIN ÜZERİNDE ENERJİLİ kalır (o bobinlerin firmware link-watchdog'u YOKTUR).
    /// Sahte bir PEMF backend'i (`/api/health` → `"service":"PEMF-Vet"`) ayağa kaldırıp
    /// dosyanın DOKUNULMADAN kaldığını doğruluyoruz.
    #[test]
    fn backend_ayaktayken_estop_adresi_korunur() {
        use std::io::{Read, Write};
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ln.local_addr().unwrap().port();
        let h = std::thread::spawn(move || {
            // Tek istek yeterli (probe bir kez yoklar).
            if let Ok((mut c, _)) = ln.accept() {
                let mut buf = [0u8; 1024];
                let _ = c.read(&mut buf);
                let body = br#"{"service":"PEMF-Vet","status":"ok"}"#;
                let _ = c.write_all(
                    format!(
                        "HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: {}
Connection: close

",
                        body.len()
                    )
                    .as_bytes(),
                );
                let _ = c.write_all(body);
                let _ = c.flush();
            }
        });

        let d = std::env::temp_dir().join(format!("pemf_port_live_{}", std::process::id()));
        std::fs::create_dir_all(&d).unwrap();
        let f = d.join("backend.port");
        std::fs::write(&f, port.to_string()).unwrap();

        clear_port_if_stopped(&d, Some(port));
        assert!(
            f.exists(),
            "backend AYAKTA iken E-stop adresi SILINDI — kaldirma bobinleri enerjili oldurur"
        );

        let _ = h.join();
        let _ = std::fs::remove_dir_all(&d);
    }

    // ═════════════════════════════════════════════════════════════════════════════════════
    // AKTİF SEANS KAPISI (2026-08-09 denetimi, ENGEL — HASTA GÜVENLİĞİ)
    //
    // İKİ ARIZA:
    //  (1) `aktif_seans_kapisi` `#[cfg(windows)]` idi. `apply_runtime_update` macOS ve Linux'ta da
    //      çalışır ve orada da backend'i öldürüp dosyalarını değiştirir → aynı sürüm, aynı akış,
    //      aynı tıbbi risk, ama koruma yalnız bir platformda DERLENİYORDU.
    //  (2) `repair` ("Onar" düğmesi) hiçbir platformda kapıdan geçmiyordu; kullanıcıya her zaman
    //      görünen bu düğme, hastanın üzerinde süren tedaviyi kesebiliyordu.
    // ═════════════════════════════════════════════════════════════════════════════════════

    /// `/api/health`'e verilen gövdeyi döndüren sahte backend. (port, thread) verir.
    ///
    /// ⚠️ Dönen thread'e ASLA `join()` YAPMAYIN: `accept()` istenen sayıda bağlantı gelene kadar
    /// bloklar, kapı ise yalnız 1-2 istek atar → `join()` test takımını SONSUZA DEK asar
    /// (bu, testleri ilk yazarken gerçekten yaşandı: `cargo test` hiç bitmedi). `drop(h)` ile
    /// bırakın; süreç sonunda ölür.
    fn sahte_backend(govde: &'static str, istek_sayisi: usize) -> (u16, std::thread::JoinHandle<()>) {
        use std::io::{Read, Write};
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ln.local_addr().unwrap().port();
        let h = std::thread::spawn(move || {
            for _ in 0..istek_sayisi {
                match ln.accept() {
                    Ok((mut c, _)) => {
                        let mut buf = [0u8; 2048];
                        let _ = c.read(&mut buf);
                        let _ = c.write_all(
                            format!(
                                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                                govde.len()
                            )
                            .as_bytes(),
                        );
                        let _ = c.write_all(govde.as_bytes());
                        let _ = c.flush();
                    }
                    Err(_) => break,
                }
            }
        });
        (port, h)
    }

    fn gecici_kok(ad: &str, port: u16) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("pemf_kapi_{}_{}_{}", ad, std::process::id(), port));
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(d.join("backend.port"), port.to_string()).unwrap();
        d
    }

    /// ⚠️ Bu test `#[cfg(windows)]` TAŞIMAZ — kapının HER platformda derlendiğinin kanıtı budur.
    /// Fonksiyon yeniden Windows'a özel işaretlenirse mac/Linux derlemesi bu testte KIRILIR.
    #[test]
    fn seans_suruyorsa_guncelleme_ertelenir() {
        let (port, h) = sahte_backend(
            r#"{"service":"PEMF-Vet","status":"ok","sessionActive":true}"#, 4);
        let d = gecici_kok("aktif", port);

        let r = aktif_seans_kapisi(&d);
        assert!(r.is_err(), "seans surerken guncelleme gecti — tedavi yarida kesilir");
        assert!(r.unwrap_err().contains("seans"), "mesaj sebebi soylemiyor");

        drop(h);
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn seans_yoksa_guncelleme_gecer() {
        let (port, h) = sahte_backend(
            r#"{"service":"PEMF-Vet","status":"ok","sessionActive":false}"#, 4);
        let d = gecici_kok("bos", port);

        assert!(aktif_seans_kapisi(&d).is_ok(), "seans yokken guncelleme engellendi");

        drop(h);
        let _ = std::fs::remove_dir_all(&d);
    }

    /// BİLİNMİYOR ≠ "seans yok". Otomatik güncelleme kullanıcı istemeden çalışır; ertelemek bedava,
    /// süren bir tedaviyi kesmek değil.
    ///
    /// ⚠️ Bu testin kurulumu bilinçlidir. Backend'in TAMAMEN yanıtsız olduğu durum bu kapıya HİÇ
    /// ULAŞMAZ: `detect_running_backend` böyle bir portu zaten tanımaz (probe düşer) ve kapı
    /// "backend yok" diyerek geçer. Gerçek "BİLİNMİYOR" yolu şudur: backend probe'a sağlıklı
    /// cevap verir (yani AYAKTADIR), ama seans durumu okunabilir bir değer olarak gelmez.
    /// Sağlıklı-ama-okunamaz durumu deterministik modellemek için `sessionActive` alanını bool
    /// DIŞI bir tiple döndürüyoruz (zaman aşımı beklemek testi 12 sn yavaşlatırdı).
    #[test]
    fn seans_durumu_okunamazsa_guncelleme_ertelenir() {
        use std::io::{Read, Write};
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ln.local_addr().unwrap().port();
        let h = std::thread::spawn(move || {
            // 1. istek: probe → geçerli PEMF-Vet yanıtı (backend AYAKTA).
            // Sonraki istekler: sessionActive bool DEĞİL → "BİLİNMİYOR".
            let mut ilk = true;
            for _ in 0..4 {
                let Ok((mut c, _)) = ln.accept() else { break };
                let mut buf = [0u8; 2048];
                let _ = c.read(&mut buf);
                let govde = if ilk {
                    r#"{"service":"PEMF-Vet","status":"ok"}"#
                } else {
                    r#"{"service":"PEMF-Vet","status":"ok","sessionActive":"belki"}"#
                };
                ilk = false;
                let _ = c.write_all(
                    format!(
                        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                        govde.len()
                    )
                    .as_bytes(),
                );
                let _ = c.write_all(govde.as_bytes());
                let _ = c.flush();
            }
        });
        let d = gecici_kok("okunamaz", port);

        let r = aktif_seans_kapisi(&d);
        assert!(
            r.is_err(),
            "BILINMIYOR 'seans yok' sayildi — sessiz guncelleme suren tedaviyi keser"
        );

        drop(h);
        let _ = std::fs::remove_dir_all(&d);
    }

    // ── ARKA PLAN İNDİRME İLERLEMESİ (2026-08-16, sahip isteği: yüzdelik real-time bar) ──
    // Bu iki kural kaynak-regex testiyle AYIRT EDİLEMİYORDU (mutasyon turu gösterdi); burada
    // davranışsal olarak kilitleniyor. İkisi de doğrudan kullanıcıya yansır.

    fn ilerleme(done: u64, total: u64) -> flow::Progress {
        flow::Progress::Downloading { what: "app".into(), done, total }
    }

    fn okunan(store: &Arc<Mutex<Option<serde_json::Value>>>) -> Option<(u64, u64)> {
        store.lock().unwrap().as_ref().map(|v| {
            (v["done"].as_u64().unwrap_or(0), v["total"].as_u64().unwrap_or(0))
        })
    }

    /// 🔴 SON PARÇA HER ZAMAN yazılmalı — yoksa bar %99'da ASILI kalır ve kullanıcı
    /// indirmenin bittiğini göremez.
    #[test]
    fn son_parca_throttle_a_TAKILMAZ() {
        let store: Arc<Mutex<Option<serde_json::Value>>> = Arc::new(Mutex::new(None));
        // Throttle'ı çok uzun tut: son parça dışındaki her şey elenmeli.
        let mut yaz = snapshot_yazici(store.clone(), 60_000);

        yaz(ilerleme(10, 100)); // ilk olay her zaman yazılır
        assert_eq!(okunan(&store), Some((10, 100)));

        yaz(ilerleme(50, 100)); // throttle → YAZILMAMALI
        assert_eq!(okunan(&store), Some((10, 100)), "throttle calismiyor");

        yaz(ilerleme(100, 100)); // SON PARÇA → throttle'a RAĞMEN yazılmalı
        assert_eq!(
            okunan(&store),
            Some((100, 100)),
            "son parca throttle'a takildi -> bar %99'da asili kalir"
        );
    }

    /// İlerleme gerçekten store'a AKMALI (yazıcı sessizce hiçbir şey yapmamalı).
    #[test]
    fn ilerleme_store_a_gercekten_yazilir() {
        let store: Arc<Mutex<Option<serde_json::Value>>> = Arc::new(Mutex::new(None));
        let mut yaz = snapshot_yazici(store.clone(), 0);
        assert!(store.lock().unwrap().is_none(), "baslangicta bos olmali");

        yaz(flow::Progress::Verifying { what: "deps".into() });
        let v = store.lock().unwrap().clone().expect("faz olayi yazilmadi");
        assert_eq!(v["step"], "verifying");
        assert_eq!(v["what"], "deps");

        yaz(ilerleme(7, 9));
        assert_eq!(okunan(&store), Some((7, 9)), "indirme olayi yazilmadi");
    }

    /// `total = 0` (Content-Length yok): son-parça kuralı yanlışlıkla tetiklenmemeli,
    /// ama olaylar yine de akmalı — UI orada belirsiz bar gösterir.
    #[test]
    fn toplam_bilinmiyorken_de_akar() {
        let store: Arc<Mutex<Option<serde_json::Value>>> = Arc::new(Mutex::new(None));
        let mut yaz = snapshot_yazici(store.clone(), 0);
        yaz(ilerleme(0, 0));
        assert_eq!(okunan(&store), Some((0, 0)));
        yaz(ilerleme(4096, 0));
        assert_eq!(okunan(&store), Some((4096, 0)));
    }

    /// Backend hiç çalışmıyorsa kapı engel OLMAMALI (ilk kurulum / temiz makine).
    #[test]
    fn backend_yoksa_kapi_engellemez() {
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ln.local_addr().unwrap().port();
        drop(ln);
        let d = gecici_kok("yok", port);

        assert!(aktif_seans_kapisi(&d).is_ok(), "backend yokken guncelleme engellendi");

        let _ = std::fs::remove_dir_all(&d);
    }
    /// [L adım 3 / launcher-2] Pencere boyutu monitör çalışma alanına sığmalı.
    /// ÖLÇÜLEN: 1366×768 @%150 → mantıksal 911×480. Sabit 880×600 pencere + 700×540 asgari
    /// boyut ile pencere ekrandan taşıyor ve KÜÇÜLTÜLEMİYORDU (asgari 540 > 480).
    #[test]
    fn ana_pencere_calisma_alanina_sigar() {
        // 1366×768 @%150 maximize
        let ((w, h), (mw, mh)) = ana_pencere_boyutu(911.0, 480.0);
        assert!(h <= 480.0, "pencere yüksekliği çalışma alanını aşıyor: {h}");
        assert!(mh <= h, "asgari yükseklik pencereden büyük → küçültülemez: {mh} > {h}");
        assert_eq!((w, h), (871.0, 440.0));
        assert_eq!((mw, mh), (700.0, 440.0));

        // 1366×768 @%125 → 1093×576
        let ((w2, h2), (_, mh2)) = ana_pencere_boyutu(1093.0, 576.0);
        assert_eq!((w2, h2), (880.0, 536.0));
        assert_eq!(mh2, 460.0);

        // Geniş ekran: tavan aşılmaz.
        let ((w3, h3), _) = ana_pencere_boyutu(2560.0, 1440.0);
        assert_eq!((w3, h3), (880.0, 600.0));

        // Çok küçük sanal ekran: taban altına inilmez.
        let ((w4, h4), (mw4, mh4)) = ana_pencere_boyutu(500.0, 300.0);
        assert_eq!((w4, h4), (640.0, 400.0));
        assert!(mw4 <= w4 && mh4 <= h4);
    }

    /// [matris-9] Kurulu uygulama penceresi masaüstü kırılma noktasını (900 px) hedefler.
    #[test]
    fn uygulama_penceresi_masaustu_kirilma_noktasini_korur() {
        let ((w, _), (mw, _)) = uygulama_pencere_boyutu(1920.0, 1080.0);
        assert!(w >= 900.0);
        assert_eq!(mw, 900.0, "asgari genişlik kabuğu telefon düzenine düşürmemeli");

        // Dar ekranda asgari genişlik pencereyi AŞMAZ (aksi hâlde küçültülemez).
        let ((w2, _), (mw2, _)) = uygulama_pencere_boyutu(800.0, 600.0);
        assert!(mw2 <= w2);
    }

}
