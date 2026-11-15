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
    /// LN L3 · Y82: ana pencere kapanışının yakma aşaması — `KAPANIS_NORMAL` · `KAPANIS_YAKMA_BEKLENIYOR` (kapanış ertelendi,
    /// bekleyici çalışıyor) · `KAPANIS_YAKMA_BITTI` (bekleme bitti → sonraki kapanış isteği ertelenmeden geçer).
    kapanis_yakma_beklendi: Arc<AtomicU8>,
    /// KI G1: ana pencere kapanışının yakma bütçesi — `CloseRequested` bekleyicisi ile `Destroyed` işinin STOP sonrası beklemesi AYNI son
    /// anı paylaşır (ilk beklemede sabitlenir; toplam ≤ `YAKMA_BEKLEME_AZAMI`). Yalnız ANA pencere (süreç çıkıyor) kullanır.
    kapanis_yakma_siniri: backend::YakmaBeklemeSiniri,
}

const KAPANIS_NORMAL: u8 = 0;
const KAPANIS_YAKMA_BEKLENIYOR: u8 = 1;
const KAPANIS_YAKMA_BITTI: u8 = 2;
/// LN L3: ana pencere arayüzüne "yakma bitince kapanacak" uyarısı (`index.html` dinler → `kapanisYakmaBekleniyor`).
const OLAY_KAPANIS_YAKMA_BEKLENIYOR: &str = "pemf://kapanis-yakma-bekleniyor";

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
            kapanis_yakma_beklendi: Arc::new(AtomicU8::new(KAPANIS_NORMAL)),
            kapanis_yakma_siniri: backend::YakmaBeklemeSiniri::default(),
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
use pemf_launcher_core::guncelleme_onayi;

fn stop_tracked_backend(state: &tauri::State<'_, AppState>, root: &std::path::Path) {
    let tracked = state.proc.lock().unwrap().take();
    stop_backend_for_teardown(tracked, root, state.session.clone());
}

/// `stop_tracked_backend`'in kilitten BAĞIMSIZ gövdesi.
///
/// DENETİM 2026-08-06: `uninstall` bu işi `spawn_blocking`'e taşıyabilsin diye ayrıldı —
/// `tauri::State` thread'e taşınamaz, ama `(Child, port)` çifti taşınabilir. Sıra (E-stop →
/// kill → stray temizliği → port dosyası) DEĞİŞMEDİ.
///
/// KP-5 B1: orphan dalının varsayılan portu ENJEKTE (`varsayilan_port`; testte 8000'e istek YOK) — üretim girişi aşağıdaki
/// `stop_backend_for_teardown` (`install::DEFAULT_PORT`). Gövde başka hiçbir yerde DEĞİŞMEDİ.
fn stop_backend_for_teardown_portla(
    tracked: Option<(std::process::Child, u16)>,
    root: &std::path::Path,
    bellek: Arc<Mutex<Option<auth::Session>>>, // [S4] F5 yakalama belleği de tazeler (thread'e taşınabilir Arc)
    varsayilan_port: u16,
) {
    // KI G1: tracked + orphan yakma beklemeleri TEK bütçe (toplam ≤ YAKMA_BEKLEME_AZAMI).
    let sinir = backend::YakmaBeklemeSiniri::default();
    // 1) Bu oturumun tracked backend'i: E-stop (TIBBİ GÜVENLİK) + [F5] son-yakalama + kill.
    let had_tracked = if let Some((mut child, port)) = tracked {
        backend::safe_stop_coils(port);
        yakma_bitene_kadar_bekle(port, &sinir); // LN L3 · Y82: STOP SONRASI / kill ÖNCESİ — yakıcı yarıda kesilmesin
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
    //    LN L6 · İG-8.27: port dosyası YOK / bayatken varsayılan portta çalışan (kimliği doğrulanmış) backend de STOP alır —
    //    `kill_stray_backends` onu ADLA öldürür; eskiden STOP'suzdu.
    if !had_tracked {
        for port in backend::orphan_durdurma_hedefleri(root, varsayilan_port) {
            backend::safe_stop_coils(port);
            yakma_bitene_kadar_bekle(port, &sinir); // LN L3 · Y82
        }
    }
    backend::kill_stray_backends(root); // LN L5: mosquitto yalnız bu kökten (Y71)
    // taskkill sonrası OS'un dosya kilitlerini bırakması için kısa bekle (extract'tan ÖNCE).
    std::thread::sleep(std::time::Duration::from_millis(800));
    clear_port_if_stopped(root, None);
}

/// Üretim girişi (çağıranlar AYNI): `stop_backend_for_teardown_portla` + gerçek varsayılan port.
fn stop_backend_for_teardown(
    tracked: Option<(std::process::Child, u16)>,
    root: &std::path::Path,
    bellek: Arc<Mutex<Option<auth::Session>>>,
) {
    stop_backend_for_teardown_portla(tracked, root, bellek, install::DEFAULT_PORT)
}

/// KP-5 B1 (sahip kararı 1): pencere kapanışının (`WindowEvent::Destroyed`) söküm işi — gövde `kabuk.rs`'teki kapanıştan BAYT AYNI
/// taşındı (değişken adları aynı: sahip olunan `root` / `bellek` / `sinir`); kabukta yalnız iş parçacığı / Tauri olayı kalır. Sıra
/// DAVRANIŞLA sınanır (`KRITIK_KP5_B1_pencere_kapanis_isi_…`): STOP → yakma beklemesi → son oturum → kill → artakalan → port dosyası
/// → hotspot. YALNIZ bu başlatıcının başlattığı (izlenen) backend için çağrılır (sahiplik kuralı kabukta AYNEN).
fn pencere_kapanis_isi(
    mut child: std::process::Child,
    port: u16,
    root: std::path::PathBuf,
    bellek: Arc<Mutex<Option<auth::Session>>>,
    sinir: backend::YakmaBeklemeSiniri,
) {
    backend::safe_stop_coils(port);
    yakma_bitene_kadar_bekle(port, &sinir); // LN L3 · Y82: STOP SONRASI / kill ÖNCESİ
    son_oturumu_yakala(port, &root, &bellek); // [F5] E-stop SONRASI / kill ÖNCESİ
    let _ = child.kill();
    let _ = child.wait();
    // child.kill() ÇOCUK-AĞACINI öldürmez → BİZİM spawn ettiğimiz
    // mosquitto/cloudflared YETİM kalır ve runtime/ dosyalarını kilitler
    // (sonraki kurulum "os error 32"). Yalnız SAHİBİYSEK ağacı temizle.
    backend::kill_stray_backends(&root); // LN L5: mosquitto yalnız bu kökten (Y71)
    // Temiz kapanış: bobinler durduruldu + backend öldürüldü → port dosyasını
    // sil ki sonraki bir uninstall ölü bir porta E-stop POST'lamasın. (Çökme
    // yolunda bu handler ÇALIŞMAZ → dosya kalır ve uninstaller E-stop'lar.)
    clear_port_if_stopped(&root, Some(port));
    // Sahip 2026-11-04: backend kapandı → PEMF-Gateway hotspot'u da kapanır (eskiden açık kalıyor, görev
    // her 3 dk geri açıyordu). Yalnız BİZİM backend'imizi durdurduysak; bobin STOP'u ve kill'den SONRA,
    // beklemeden (ayrı süreç). Benimsenen / başkasının backend'inde bu blok koşmaz → hotspot'a dokunulmaz.
    flow::hotspot_kapat(&root);
}

/// LN L3 · Y82 (sahip): STOP gönderildikten SONRA, süreç öldürülmeden ÖNCE — backend STM32 firmware'i YAKIYORSA bitmesini bekle
/// (`STM32_Programmer_CLI` yarıda kesilirse kart yarım yazılmış uygulama alanıyla kalır). STOP bu beklemeye BAĞLI DEĞİL (önce gider —
/// Ö.4-Y8); azami süre dolarsa yine öldürülür ama yakıcı backend'in AĞACINDA öldürülmez (`backend::ARTAKALAN_SURECLER`).
/// KI G1: bekleme `sinir` bütçesinden — aynı kapanıştaki önceki bekleme(ler) azamiyi tükettiyse yeniden BEKLENMEZ.
fn yakma_bitene_kadar_bekle(port: u16, sinir: &backend::YakmaBeklemeSiniri) {
    match backend::yakmanin_bitmesini_bekle_sinirla(port, sinir, backend::YAKMA_BEKLEME_AZAMI, std::time::Duration::from_secs(1)) {
        backend::YakmaBeklemesi::Yoktu | backend::YakmaBeklemesi::Bilinmiyor => {}
        backend::YakmaBeklemesi::Bitti => eprintln!("[kapanis] STM32 firmware yakmasi bitti — backend simdi durduruluyor"),
        backend::YakmaBeklemesi::ZamanAsimi => {
            eprintln!("[kapanis] STM32 firmware yakmasi azami surede bitmedi — backend durduruluyor (yakici agacta degil, olmez)")
        }
    }
}

/// KI G1: pencere `Destroyed` işinin yakma bütçesi. ANA pencere (süreç çıkıyor) `CloseRequested` bekleyicisinin bütçesini PAYLAŞIR → STOP
/// sonrası bekleme yalnız kalan süre kadar (toplam ≤ `YAKMA_BEKLEME_AZAMI`); "app" penceresinin işi (süreç yaşar, backend yeniden
/// başlatılabilir) kendi taze bütçesiyle.
fn kapanis_yakma_siniri(state: &AppState, is_main: bool) -> backend::YakmaBeklemeSiniri {
    if is_main {
        state.kapanis_yakma_siniri.clone()
    } else {
        backend::YakmaBeklemeSiniri::default()
    }
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
    match backend::devir_cek_kisa(port, backend::PULL_TEARDOWN_TIMEOUT_S) {
        backend::DevirCekme::Oturum(s) => {
            let _ = secret_store::rotasyonu_isle(root, &s);
            bellek_rotasyonu_uygula(bellek, &s); // [S4] bellek de taze kalsın (yeniden devir bayat itmesin)
        }
        backend::DevirCekme::Cikis => {
            pencere_cikisini_uygula(root, bellek);
        }
        backend::DevirCekme::Yok => {}
    }
}

/// Pencerede "Çıkış Yap" (backend `{"cikis": true}`) → launcher'ın "Beni hatırla" kaydı ve bellekteki oturumu HEMEN
/// temizlenir (sahip kararı 2026-10-18; auth_session.bin kaybı — eskiden ölü jeton diskte kalıp sonraki açılışta sessizce
/// siliniyordu). Kullanıcının "Beni hatırla" TERCİHİ korunur (pencerede sonraki giriş yeniden hatırlansın). 60 sn döngüsü
/// her turda aynı işareti görür → yalnız gerçekten bir şey temizlendiyse günlüğe yazar. Dönüş: temizlendi mi.
fn pencere_cikisini_uygula(root: &std::path::Path, bellek: &Mutex<Option<auth::Session>>) -> bool {
    secret_store::hatirla_isaretini_tamamla(root);
    let diskte = secret_store::blob_path(root).exists();
    let bellekte = bellek.lock().unwrap().take().is_some();
    if !diskte && !bellekte {
        return false;
    }
    secret_store::clear(root);
    secret_store::oturum_gunlugune_yaz(root, "pencerede cikis yapildi -> 'Beni hatirla' kaydi ve launcher oturumu temizlendi");
    true
}

/// [S4] (saha arızası 2026-09-03, ÖLÇÜLDÜ): rotasyonla gelen oturum yalnız DİSKE yazılıyor, bellekteki
/// `AppState.session` HİÇ güncellenmiyordu. `hand_off_session` belleği ittiği için bir sonraki devirde
/// (runtime güncellemesi backend'i yeniden başlatınca / orphan sahiplenmede / ikinci Başlat'ta) backend'e
/// BAYAT jeton gidiyor, pencere onunla yenilemeye kalkıyor ve GoTrue reuse-detection TÜM AİLEYİ iptal
/// ediyordu → sonraki açılışta SessionRevoked → "Beni hatırla" parola istiyordu (bugün 17:07'den beri
/// açık launcher, 20:3x app 1.9.39 güncellemesi, 20:38 yeniden giriş). Bellek kuralı diskten AYRI:
/// "Beni hatırla" kapalı olsa da bellek taze kalmalı. Dolu + DEĞİŞMİŞ refresh → uygula.
/// ⚠️ SAHİP KARARI 2026-10-18 (auth_session.bin kaybı): launcher pencerenin SON hesabını izler — başka hesap da, bellek
/// boşken (launcher'da giriş yok / pencerede çıkış yapıldı) pencerede yapılan giriş de uygulanır. Eskiden ikisi de reddediliyor,
/// pencerede yeniden girilen oturum launcher'a hiç geçmiyordu. Kaynak yalnız sıkı-loopback devir ucu (A-03).
fn bellek_rotasyonu_gerekli(mevcut: Option<&auth::Session>, yeni: &auth::Session) -> bool {
    if yeni.refresh_token.trim().is_empty() {
        return false;
    }
    match mevcut {
        None => true,
        // [S4-yön] AYNI hesabın daha ESKİ jetonu (bayat devir ekosu) belleği GERİYE çekemez; expires_at bilinmiyorsa (0) kabul.
        Some(m) => {
            m.refresh_token != yeni.refresh_token
                && !(m.email.eq_ignore_ascii_case(&yeni.email)
                    && m.expires_at > 0
                    && yeni.expires_at > 0
                    && yeni.expires_at < m.expires_at)
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
            match backend::devir_cek(port) {
                backend::DevirCekme::Oturum(s) => {
                    ardisik_hata = 0;
                    let _ = secret_store::rotasyonu_isle(&root, &s);
                    bellek_rotasyonu_uygula(&bellek, &s); // [S4] bellek de taze kalsın
                }
                // 2026-10-18 (sahip kararı): pencerede "Çıkış Yap" → launcher kaydı + belleği HEMEN temizlenir.
                backend::DevirCekme::Cikis => {
                    ardisik_hata = 0;
                    pencere_cikisini_uygula(&root, &bellek);
                }
                backend::DevirCekme::Yok => {
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

/// Uygulamayı AYRI bir pencerede aç — client/profil penceresi ("main") AÇIK KALIR (kullanıcı isteği:
/// Başlat'a basınca client kapanmasın, uygulama ikinci pencerede açılsın). Zaten açık bir "app"
/// penceresi varsa onu tazele + öne getir (ikinci Başlat yeni pencere YIĞMASIN). WebView2 cache-bust
/// korunur. Her pencere kapanınca on_window_event Destroyed → backend GÜVENLE durur (E-stop + kill);
/// "main" açık kaldığı için "app" kapanınca kullanıcı client'a döner. Oluşturma imkânsızsa tarayıcıya düş.
/// Uygulama penceresinin TAM URL'si (denetim 2026-09-06, profil kaldirma).
///
/// `?profiles=home,vet` → uygulama (pf `installedModes()`) yalniz KURULU profilleri sunar;
/// kaldirilan profil arayuzden de duser. Ardindan WebView2 onbellek-kiricisi (`_=<ms>`):
/// kalıcı user-data-folder aynı origin'de (127.0.0.1:8000) ESKİ index.html'i cache'ler → eski
/// bundle yüklenip "hata" verir (Chrome'da yok, WebView2'de kalır). Zaman-damgalı query her
/// açılışta TAZE index.html çektirir; referans ettiği hash'li JS zaten yeni adla taze gelir.
/// Saf parcalar core'da (`flow::uygulama_url` / `flow::onbellek_kirici`) → testte olculur.
fn uygulama_url(port: u16, installed: &[String]) -> String {
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    flow::onbellek_kirici(&flow::uygulama_url(port, installed), ts)
}

/// LN L9 · D2.E01 (WebView2 kolu) · İG-6.20: uygulama penceresindeki indirmenin kararı (saf — testli). Eskiden `on_download`
/// kayıtlı DEĞİLDİ → indirme WebView2'nin varsayılanına kalıyordu (saha notu 09-11 `dosyaIndir.ts`: "sessizce ölüyordu"; wry kaynağı:
/// işleyici yoksa `DownloadStarting`'e abone olunmaz). Artık açık karar:
///   * uygulamanın KENDİ kökeni (`http://127.0.0.1:<port>` / `localhost` / `[::1]`), o kökenin `blob:` adresi ve `data:` → İZİN
///     (WebView2'nin önerdiği hedef: kullanıcının İndirilenler klasörü);
///   * başka bir http(s) adresi → uygulama penceresinde İNDİRİLMEZ, varsayılan tarayıcıda açılır (kullanıcı indirmeyi orada görür);
///   * başka köken `blob:`'u ve diğer şemalar (`file:` …) → RED.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum IndirmeKarari {
    Izin,
    TarayicidaAc,
    Reddet,
}

fn yerel_koken_mi(u: &tauri::Url, port: u16) -> bool {
    u.scheme() == "http" && matches!(u.host_str(), Some("127.0.0.1" | "localhost" | "[::1]")) && u.port_or_known_default() == Some(port)
}

fn indirme_karari(url: &str, port: u16) -> IndirmeKarari {
    let Ok(u) = url.parse::<tauri::Url>() else { return IndirmeKarari::Reddet };
    match u.scheme() {
        "data" => IndirmeKarari::Izin,
        // `blob:http://127.0.0.1:8000/<uuid>` — iç adres yolda; yalnız uygulamanın kendi kökeni.
        "blob" => match u.path().parse::<tauri::Url>() {
            Ok(ic) if yerel_koken_mi(&ic, port) => IndirmeKarari::Izin,
            _ => IndirmeKarari::Reddet,
        },
        "http" | "https" if yerel_koken_mi(&u, port) => IndirmeKarari::Izin,
        "http" | "https" => IndirmeKarari::TarayicidaAc,
        _ => IndirmeKarari::Reddet,
    }
}

/// KP-5 B3: `on_download` olayının kabuktan bağımsız özeti (Tauri `DownloadEvent` `non_exhaustive` — bilinmeyen tür kabukta `true`).
enum IndirmeOlayi<'a> {
    Istek(&'a tauri::Url),
    Bitti(bool),
}

/// `on_download` kararı (`true` = WebView2 indirsin) — KP-5 B3 (sahip kararı 2b): `indirme_olayi`ndan ayrıldı, davranış AYNI; dış
/// adresi açan `ac` ENJEKTE (kabuk: gerçek tarayıcı). `Bitti` yalnız başarıyı günlüğe yazar — dosya ADI / yolu yazılmaz (rapor /
/// yedek adları hasta adı taşıyabilir).
fn indirme_olayi_karari(olay: IndirmeOlayi<'_>, port: u16, ac: impl FnOnce(&str)) -> bool {
    match olay {
        IndirmeOlayi::Istek(url) => match indirme_karari(url.as_str(), port) {
            IndirmeKarari::Izin => true,
            IndirmeKarari::TarayicidaAc => {
                ac(url.as_str());
                false
            }
            IndirmeKarari::Reddet => {
                eprintln!("[indirme] reddedildi (sema {})", url.scheme());
                false
            }
        },
        IndirmeOlayi::Bitti(success) => {
            eprintln!("[indirme] bitti: basari={success}");
            true
        }
    }
}

/// Güncelleme indirme sayfası adresinin denetimi (`open_url` tarayıcıda açmadan ÖNCE) — KP-5 B3 (sahip kararı 2b): kabuktan ayrıldı,
/// davranış AYNI. Manifest host-pinli kaynaktan gelir; yine de savunma: yalnız https + bilinen indirme host'ları (poisoned-manifest
/// keyfi/zararlı URL açamasın). Sondaki "/" şart → "github.com.evil" ve userinfo (github.com@evil) hileleri geçmez.
fn indirme_adresi_denetle(url: &str) -> Result<(), String> {
    // #138: ham "https://github.com/" YERİNE ürün-repo önekine daralt → zehirli manifest keyfi bir
    // GitHub repo'suna (SHA'sız indirme) yönlendiremez.
    const ALLOWED: [&str; 2] = [
        "https://pemf-vet-web.vercel.app/",
        "https://github.com/mert61-python/pemf-update/",
    ];
    if !ALLOWED.iter().any(|p| url.starts_with(p)) {
        return Err(pemf_launcher_core::dil::t_ile("rust.hata.indirmeAdresiIzinsiz", &[("url", &url.to_string())]));
    }
    // Derinlik-savunması: open_browser artık rundll32 kullansa da (kabuk yok), manifest-türevi
    // URL'yi asla riske atma — kabuk-metakarakteri, kontrol-karakteri veya boşluk içeren URL'yi
    // reddet. Meşru GitHub/Vercel indirme URL'lerinde bunlar bulunmaz.
    if url.len() > 2048 || url.chars().any(|c| c.is_control() || "&|^<>\"'`{} \t\r\n".contains(c)) {
        return Err(pemf_launcher_core::dil::t("rust.hata.indirmeAdresiGecersizKarakter"));
    }
    Ok(())
}

/// KP-5 B3 (sahip kararı 2b): yardımcı batch YOLUNUN denetimi — `yardimci_batch_baslat`tan ayrıldı, davranış AYNI. Yol UTF-8
/// olmalı; `"` / CR / LF `cmd /S /C ""<yol>""` alıntısını bozar → reddedilir.
#[cfg(windows)]
fn yardimci_batch_yolu(bat: &std::path::Path) -> Result<&str, String> {
    let yol = bat.to_str().ok_or_else(|| pemf_launcher_core::dil::t("rust.hata.yardimciBatchYoluUtf8"))?;
    if yol.contains('"') || yol.contains('\r') || yol.contains('\n') {
        return Err(pemf_launcher_core::dil::t("rust.hata.yardimciBatchYoluGuvensiz"));
    }
    Ok(yol)
}

/// KP-5 B3: erken ölen (300 ms içinde rc≠0) yardımcı batch'in iletisi — çıkış kodu yoksa "yok" — `yardimci_batch_baslat`tan ayrıldı.
#[cfg(windows)]
fn yardimci_hemen_sonlandi_iletisi(kod: Option<i32>, bat: &std::path::Path) -> String {
    let kod = kod.map(|k| k.to_string()).unwrap_or_else(|| pemf_launcher_core::dil::t("rust.hata.yok"));
    let yol = bat.display().to_string();
    pemf_launcher_core::dil::t_ile("rust.hata.yardimciHemenSonlandi", &[("kod", &kod), ("yol", &yol)])
}

/// Ev dizini için ortam-değişkeni ÖNCELİK sırası (saf → test edilebilir; env yarışı yok).
fn home_var_order(windows: bool) -> (&'static str, &'static str) {
    if windows {
        ("USERPROFILE", "HOME")
    } else {
        ("HOME", "USERPROFILE")
    }
}

/// KP-4 A2c (Y257 a): `detect_environment_blocking`'in gövdesi — kök ENJEKTE (testte sahte kök; gerçek kurulum / gerçek ortam okunmaz).
fn ortam_algila(root: &std::path::Path) -> Environment {
    // ⚠️ HER ŞEYDEN ÖNCE: yarım kalan çalışma-zamanı takasını kurtar. Güncellemenin iki `rename`i
    // arasında kapanma olduysa `runtime` diskte YOKTUR ve aşağıdaki `already_installed` kontrolü
    // "kurulu değil" der — kullanıcı, çalışan bir kurulumu olduğu hâlde sıfırdan kurulum ekranı
    // görür. (bkz. flow::yarim_takasi_kurtar)
    if pemf_launcher_core::flow::yarim_takasi_kurtar(root) {
        eprintln!("[kurtarma] yarim kalan calisma-zamani takasi onarildi");
    }
    ortam_ozeti(root)
}

fn ortam_ozeti(root: &std::path::Path) -> Environment {
    let root = root.to_path_buf();
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

/// KP-4 A2c (Y257 a): `fetch_profiles_blocking`'in gövdesi — manifest ÇEKİCİSİ ve kök (`su_root`) ENJEKTE (ağ / gerçek kök YOK).
fn profilleri_getir(
    cek: impl FnOnce() -> Result<String, net::NetError>,
    su_root: &std::path::Path,
) -> Result<serde_json::Value, String> {
    let raw = cek()
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.manifestIndirilemedi", &[("e", &e.to_string())]))?;

    let manifest =
        pemf_launcher_core::Manifest::parse(&raw).map_err(|e| e.to_string())?;

    // Bu platformun paketi yayınlanmamışsa KULLANICIYA ŞİMDİ söyle — 2 GB
    // indirdikten sonra değil.
    //
    // ⚠️ 2026-09-10: burada `runtime_for_current_platform().is_ok()` yazıyordu — yalnız
    // tek-parça `runtimes`e bakıyordu. `base.zip` manifestten çıkarılınca (layers doluyken)
    // sahadaki HER istemci "paket yayınlanmadı" deyip kilitlendi. Karar core'a taşındı ve
    // orada testlerle pinlendi (`Manifest::platform_desteklenir`); burada satır içi mantık
    // BIRAKMAYIN — bu dosyada test yok, o yüzden kapı sessizce kırılabiliyordu.
    let supported = manifest.platform_desteklenir();
    let mut profiles: Vec<&str> = manifest.models.keys().map(|s| s.as_str()).collect();
    profiles.sort_unstable();

    // OTO-GÜNCELLEME: launcher thin-bootstrapper. Manifest'teki en son launcher sürümü kendi sürümümüzden yeniyse UI onu onay
    // penceresine koyar (`guncelleme_ozeti`; GÜNCELLEME ONAYI Y253 / Y254 — 2026-11-06'ya dek SESSİZCE kuruluyordu); kullanıcı
    // onaylarsa (ya da güncelleme ZORUNLUYSA) `apply_self_update` indirir, kurar ve yeniden başlatır. Yalnız sürüm/url varsa
    // (eski manifest) UI "yeni sürüm var" bildirir. İnternet yoksa fetch_profiles zaten hata verir → kontrol hiç çalışmaz.
    let current_launcher = env!("CARGO_PKG_VERSION");
    // DENETİM 2026-08-04 (P2 — sonsuz döngü): kayıtlı deneme hedefine ULAŞTIYSAK güncelleme
    // gerçekten uygulanmış → sayacı temizle. Ulaşamadıysak sayaç durur ve N denemeden sonra
    // OTOMATİK kurulum kapanır (bildirim kalır, kullanıcı elle indirebilir).
    if let Some((tried, _)) = install::read_selfupdate_attempt(su_root) {
        if tried == current_launcher {
            install::clear_selfupdate_attempt(&su_root);
        }
    }
    // LN L12: karar çekirdekte TEK yerde (`Manifest::launcher_guncellemesi` — yalnız yayındaki sürüm YENİYSE; eşit / eski → yok).
    let update = manifest.launcher_guncellemesi(current_launcher).map(|l| {
        serde_json::json!({
            "version": l.version,
            "url": l.url,
            "installer_url": l.installer_url,
            "sha256": l.sha256,
            "size": l.size,
            // `false` ise UI onay penceresine KOYMAZ (döngü kırıcı) ama bildirimi gösterir.
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
    .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.kurulumGorevCoktu", &[("e", &e.to_string())]))?;

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
        return Err(pemf_launcher_core::dil::t("rust.hata.uygulamaKuruluDegil"));
    }
    // Zaten bu oturumda çalışıyorsa: yeni süreç başlatma, uygulamayı pencerede tekrar göster.
    let running_port = state.proc.lock().unwrap().as_ref().map(|(_, p)| *p);
    if let Some(port) = running_port {
        // İDEMPOTENT: kullanıcı arada "Çıkış yap"/"Giriş yap" yapmış olabilir → oturumu tazele.
        hand_off_session(&state, port).await;
        open_app_window(&app, port);
        return Ok(backend::app_url(port));
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
                match backend::devir_cek_kisa(port, backend::PULL_TEARDOWN_TIMEOUT_S) {
                    backend::DevirCekme::Oturum(s) => {
                        if bellek_rotasyonu_uygula(&bellek, &s) {
                            let _ = secret_store::rotasyonu_isle(&root_c, &s);
                        }
                    }
                    // 2026-10-18: sahiplenilen backend'te pencere çıkış yapmış → launcher da çıkışa geçer (devir YAPILMAZ).
                    backend::DevirCekme::Cikis => {
                        pencere_cikisini_uygula(&root_c, &bellek);
                    }
                    backend::DevirCekme::Yok => {}
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
        open_app_window(&app, port);
        return Ok(backend::app_url(port));
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
    .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.baslatmaGorevCoktu", &[("e", &e.to_string())]))?;

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
            return Err(pemf_launcher_core::dil::t("rust.hata.onarimSeansSuruyor"));
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
    .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.onarimGorevCoktu", &[("e", &e.to_string())]))?;

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

/// Profil kaldir (denetim 2026-09-06): "Profilleri degistir" ekraninda birakilan profil(ler)in
/// model dosyalari (kalan profillerle ORTAK olanlar haric) + onbellek zip'leri + kayitlari silinir.
/// Backend BASLATILMAZ — UI ardindan ya ekleme kurulumuna gecer ya da hazir ekranina doner.
///
/// Sira `repair` ile AYNI: kilit → aktif seans kapisi → E-stop + kill (`stop_tracked_backend`) →
/// acik "app" penceresini kapat → `spawn_blocking`. Model dosyalari acik bir backend tarafindan
/// kilitli olabilir; ve bobinler asla E-stop'suz kalmaz.
///
/// ILERLEME (inceleme 2026-09-06): `state.progress` None BIRAKILIR ve cekirdege no-op callback
/// gecilir. `Progress` varyantlari kurulum adimlaridir; UI "extracting"i "Kuruluyor…/Installing…"
/// diye basar ve 150 ms'lik yoklama T2'nin "Kaldırılıyor…" basligini ezerdi. UI o ekrani kendi
/// yonetir.
///
/// PENCERE (inceleme 2026-09-06): acik "app" penceresi KAPATILIR. Aksi halde SPA eski
/// `?profiles=home,vet` URL'si + localStorage kopyasiyla acik kalir, sonraki Baslat mevcut
/// pencereyi yalniz one getirir (navigate YOK) → kaldirilan profil arayuzde secilebilir kalir ve
/// modeller diskte olmadigi icin AI analizi anlasilmaz hatayla duser. Kapatma `stop_tracked_backend`
/// SONRASINDA: `state.proc` orada atomik alinip E-stop → yakala → kill TAMAMLANIR; Destroyed
/// kancasi `proc`u None bulur ve hicbir sey yapmaz (iki yolun ayni backend'i yarista E-stop'suz
/// oldurmesi imkansiz).
#[tauri::command]
async fn remove_profiles(
    state: tauri::State<'_, AppState>,
    app: tauri::AppHandle,
    manifest_raw: String,
    profiles: Vec<String>,
) -> Result<serde_json::Value, String> {
    let root = install::default_install_root(&home_dir());
    let _kilit = install::kurulum_kilidi_al(&root)?;
    if let Some(p) = backend::detect_running_backend(&root) {
        if backend::session_active(p) == Some(true) {
            return Err(
                pemf_launcher_core::dil::t("rust.hata.profilKaldirmaSeansSuruyor"),
            );
        }
    }
    stop_tracked_backend(&state, &root);
    *state.progress.lock().unwrap() = None;
    if let Some(w) = app.get_webview_window("app") {
        let _ = w.close();
    }

    let root2 = root.clone();
    let rapor = tauri::async_runtime::spawn_blocking(move || -> Result<flow::RemoveReport, String> {
        let manifest = pemf_launcher_core::Manifest::parse(&manifest_raw).map_err(|e| e.to_string())?;
        flow::remove_profiles(&root2, &manifest, &profiles, &mut |_| {}).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.profilKaldirmaGorevCoktu", &[("e", &e.to_string())]))??;

    Ok(serde_json::json!({
        "status": "ok",
        "removed": rapor.removed,
        "installed": rapor.installed,
        "freed_bytes": rapor.freed_bytes,
        "kept_shared": rapor.kept_shared,
    }))
}

/// `aktif_seans_kapisi`'nın gövdesi; varsayılan port testte enjekte edilir (8000'e istek YOK). LN L6 · İG-8.21: yük altında 2 sn'lik
/// kimlik yoklamasına yanıt vermeyen ama TCP kabul eden backend "yok" SAYILMAZ (`guncelleme_kapisi_backendi`) → seans sorulur.
fn aktif_seans_kapisi_portla(root: &std::path::Path, varsayilan_port: u16) -> Result<(), String> {
    let Some(p) = backend::guncelleme_kapisi_backendi(root, varsayilan_port) else { return Ok(()) };
    match backend::session_active(p) {
        Some(false) => {}
        Some(true) => return Err(
            pemf_launcher_core::dil::t("rust.hata.guncellemeSeansSuruyor"),
        ),
        None => return Err(
            pemf_launcher_core::dil::t("rust.hata.guncellemeBackendYanitsiz"),
        ),
    }
    // LN L3 · Y82: backend STM32 firmware'i YAKIYORSA güncelleme ERTELENİR — self-update'in NSIS kancası backend'i öldürür, runtime
    // güncellemesi de söker; yakma yarıda kalırdı. Bilinmiyorsa (yanıt yok) seans kuralıyla aynı: ertele.
    match backend::yakma_suruyor_mu(p, std::time::Duration::from_secs(3)) {
        Some(false) => Ok(()),
        Some(true) => Err(pemf_launcher_core::dil::t("rust.hata.guncellemeYakmaSuruyor")),
        None => Err(pemf_launcher_core::dil::t("rust.hata.guncellemeBackendYanitsiz")),
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
        // true → paketler hazır, kurulum saniyeler sürer.
        // false → önce ARKA PLANDA inecek (YALNIZ onaydan / zorunlu güncellemeden sonra — GÜNCELLEME ONAYI Y253 / Y254),
        // indirme bitince kurulum seans kapısından geçip KENDİLİĞİNDEN sürer (2026-11-06'ya dek: SONRAKİ açılışta).
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

/// KP-4 A2c (Y257 a): `check_runtime_update_blocking`'in gövdesi — kök ENJEKTE (testte sahte kök; gerçek kurulum / gerçek ortam okunmaz).
fn check_runtime_update_ile(root: &std::path::Path, manifest_raw: String) -> Result<serde_json::Value, String> {
    // Kaydı olmayan ESKİ kurulumlarda profil sha'larını önce benimse — yoksa üç profil birden
    // (~2,2 GB) boşuna iner. Base bilerek kapsam dışı: o gerçekten değişmiştir.
    let _ = flow::adopt_unknown_models(&manifest_raw, &root);
    let plan = flow::pending_updates(&manifest_raw, &root).map_err(|e| e.to_string())?;
    Ok(plan_to_json(&plan))
}

fn unix_simdi_s() -> u64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

/// KP-4 A2c (Y257 a): `guncelleme_ozeti_blocking`'in gövdesi — kök ve ŞİMDİ (unix sn) ENJEKTE (onay yaşı sahte saatle sınanır).
fn guncelleme_ozeti_ile(root: &std::path::Path, manifest_raw: String, simdi: u64) -> Result<serde_json::Value, String> {
    let manifest = pemf_launcher_core::Manifest::parse(&manifest_raw).map_err(|e| e.to_string())?;
    // `check_runtime_update` ile AYNI sıra: kaydı olmayan eski kurulumda profil sha'ları önce benimsenir (yoksa ~2,2 GB boşuna sorulur).
    let _ = flow::adopt_unknown_models(&manifest_raw, &root);
    let plan = flow::pending_updates(&manifest_raw, &root).map_err(|e| e.to_string())?;
    let kendi = env!("CARGO_PKG_VERSION");
    // `fetch_profiles`in `auto` bayrağıyla AYNI ölçüt (deneme sınırı + kademeli yayın dilimi).
    let launcher_otomatik = manifest.launcher_guncellemesi(kendi).is_some_and(|l| {
        install::selfupdate_auto_allowed(&root, &l.version) && install::rollout_dilimi(&root) < l.rollout
    });
    let kayit = guncelleme_onayi::oku(&root);
    if kayit.as_ref().is_some_and(|k| !guncelleme_onayi::yas_gecerli(k, simdi)) {
        guncelleme_onayi::temizle(&root); // haftalar önceki onay habersiz kurulum doğurmaz
    }
    let oz = guncelleme_onayi::ozet(
        &manifest,
        &plan,
        kendi,
        &install::kurulu_surum(&root),
        launcher_otomatik,
        kayit.as_ref().filter(|k| guncelleme_onayi::yas_gecerli(k, simdi)),
        simdi,
    );
    serde_json::to_value(oz).map_err(|e| e.to_string())
}

/// KP-4 A2c (Y257 a): `guncelleme_onayini_kaydet`in gövdesi — kök ve ŞİMDİ ENJEKTE.
fn onay_kaydet_ile(root: &std::path::Path, manifest_raw: &str, launcher_hedefi: Option<&str>, simdi: u64) -> Result<(), String> {
    let plan = flow::pending_updates(manifest_raw, root).map_err(|e| e.to_string())?;
    let kayit = guncelleme_onayi::onay_kaydi_kur(&plan, launcher_hedefi, simdi);
    guncelleme_onayi::kaydet(root, &kayit)
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.onayKaydiYazilamadi", &[("e", &e.to_string())]))
}

/// `guncelleme_engeli` sonucunun JSON'u (saf — testli).
fn guncelleme_engeli_json(kapi: Result<(), String>) -> serde_json::Value {
    match kapi {
        Ok(()) => serde_json::json!({ "engel": false }),
        Err(mesaj) => serde_json::json!({ "engel": true, "mesaj": mesaj }),
    }
}

/// ARKA PLAN İNDİRME — paketleri önbelleğe çeker, kuruluma DOKUNMAZ, UI'ı BLOKLAMAZ.
///
/// SAHİP KARARI 2026-08-08: "güncelleme açılışta kimseyi bekletmesin" — gerekçe KORUNUR: kullanıcı uygulamayı normal
/// kullanırken paketler iner. GÜNCELLEME ONAYI (Y253 / Y254, 2026-11-06) bu kararı DEĞİŞTİRDİ: UI bu komutu YALNIZ kullanıcı
/// onayından (ya da zorunlu güncellemeden) SONRA çağırır ve indirme bitince kurulum "bir sonraki açılışı" BEKLEMEZ —
/// seans kapısından (`guncelleme_engeli`) geçip `apply_runtime_update` ile sürer, uygulama kendiliğinden yeniden açılır.
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
    .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.arkaPlanIndirmeCoktu", &[("e", &e.to_string())]))?;
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
        // Bu süreç onaydan SONRA da çalışmaya devam eder → kimliği eski kayıttan değil, onaylanacak paketten
        // (YAYIN 2026-11-03: güncellemeden sonraki ilk oturum `/api/health`te eski `buildId`i raporluyordu).
        match flow::start_backend_kimlikli(&root2, &mut on, geri.paket_kimligi()) {
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
                        kod: None,
                    });
                }
                // ⚠️ LN L2 · Y16 + Y81 (D1.119, docs/LAUNCHER_SPEC.md): backend `firmwareGuncelleme.istemciGeriAlinmali` JSON `true`
                // (kesin uyumsuz + STM bağlı + ileri gidilemiyor) → client ÖNCEKİ çalışan sürüme sağlık kapılı GERİ ALINIR. Yalnız o
                // zaman: `uyum == null`, "hedef sürümü bildirmedi", alanın yokluğu (eski backend) ve bütçe içinde kararın gelmemesi
                // geri alma sebebi DEĞİL. Karar BURADA beklenir: `runtime.old` / `_app_yedek` yalnız onaydan ÖNCE durur ve backend
                // açılış kararını STM el sıkışmasından SONRA verir (D1.121).
                if backend::firmware_kararini_bekle(port, backend::FIRMWARE_KARAR_BUTCESI, FIRMWARE_KARAR_YOKLAMA)
                    == backend::FirmwareKarari::GeriAl
                {
                    return Ok(firmware_uyumsuz_geri_al(child, port, &root2, &manifest_raw, &geri, bellek2.clone()));
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
                    kod: None,
                })
            }
        }
    })
    .await
    .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.guncellemeGorevCoktu", &[("e", &e.to_string())]))?;

    match sonuc? {
        GuncellemeSonucu::Hazir(child, url, port) => {
            hand_off_session(&state, port).await;
            // GÜNCELLEME ONAYI (Y253 "oto yeniden başlasın uygulama"): açık uygulama penceresi YENİ arayüzü yükler; açık değilse
            // `on_backend_ready` → `open_app_window` açar. Kurulum "bir sonraki açılışı" beklemez.
            uygulama_penceresini_yenile(&app, port);
            on_backend_ready(&app, &state, child, &url, port);
            Ok(serde_json::json!({ "status": "ready", "url": url }))
        }
        GuncellemeSonucu::DegisiklikYok => Ok(serde_json::json!({ "status": "noop" })),
        GuncellemeSonucu::Duraklatildi => Ok(serde_json::json!({ "status": "paused" })),
        GuncellemeSonucu::Iptal => Ok(serde_json::json!({ "status": "cancelled" })),
        GuncellemeSonucu::GeriAlindi { sebep, geri_alma_hatasi, kod } => Ok(serde_json::json!({
            "status": "rolled_back",
            "reason": sebep,
            "rollback_error": geri_alma_hatasi,
            // LN L2: arayüz nedene göre doğru notu seçer (`firmware_uyumsuz` → "açılamadı" DEMEZ).
            "kod": kod,
        })),
    }
}

/// LN L2: firmware kararı yoklama aralığı (bütçe `backend::FIRMWARE_KARAR_BUTCESI`).
const FIRMWARE_KARAR_YOKLAMA: std::time::Duration = std::time::Duration::from_secs(1);
/// LN L2: `rolled_back` yanıtındaki neden kodu — arayüz `rtRollbackFirmware` notunu gösterir.
const KOD_FIRMWARE_UYUMSUZ: &str = "firmware_uyumsuz";

/// LN L2 · Y16 + Y81: yeni sürüm açıldı ama backend "client geri alınmalı" dedi (kart yazılımı uyumsuz, ileri gidilemiyor).
/// Sıra dbReady dalıyla AYNI: ⚠️ E-stop → kill (`stop_backend_for_teardown`) → deneme sayacı (döngü kırıcı: aynı hedef 2 kez geri
/// alınınca otomatik kurulum durur) → eski sürüme dön. Kendi fonksiyonunda: o dalın satırları Python kapılarının TEK geçmesi gereken
/// çapalarıdır (`tests/launcher_onay_karari.py`).
fn firmware_uyumsuz_geri_al(
    child: std::process::Child,
    port: u16,
    root: &std::path::Path,
    manifest_raw: &str,
    geri: &flow::GeriAlmaBilgisi,
    bellek: Arc<Mutex<Option<auth::Session>>>,
) -> GuncellemeSonucu {
    stop_backend_for_teardown(Some((child, port)), root, bellek);
    flow::geri_almayi_kaydet(root, manifest_raw);
    let geri_alma_hatasi = flow::guncellemeyi_geri_al(root, geri).err().map(|x| x.to_string());
    GuncellemeSonucu::GeriAlindi {
        sebep: pemf_launcher_core::dil::t("rust.hata.guncellemeFirmwareUyumsuz"),
        geri_alma_hatasi,
        kod: Some(KOD_FIRMWARE_UYUMSUZ),
    }
}

/// `apply_runtime_update`'in iç sonucu — `Child` Serialize edilemediği için ayrı tip.
enum GuncellemeSonucu {
    Hazir(std::process::Child, String, u16),
    DegisiklikYok,
    Duraklatildi,
    Iptal,
    /// Yeni sürüm AÇILAMADI ya da kullanılamaz (dbReady false · kart yazılımı uyumsuz) → eskiye dönüldü. `geri_alma_hatasi` doluysa
    /// disk elle onarım ister. `kod`: arayüzün notu seçtiği neden (yalnız `firmware_uyumsuz`; diğerleri `None` = genel not).
    GeriAlindi {
        sebep: String,
        geri_alma_hatasi: Option<String>,
        kod: Option<&'static str>,
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
/// hook'unda bobinlere E-stop atar (windows/hooks.nsi). Hasta DB'si (launcher'ın verdiği kök — `veri_koku.txt`; %PROGRAMDATA%\PEMF_System\PEMF_GUI ya da
/// %APPDATA%\PEMF_GUI) KVKK: KORUNUR.
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
    .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.kaldirmaHazirligiCoktu", &[("e", &e.to_string())]))?;

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
        // DEV-D5.b: temizliğin ÇIKIŞ KODU da günlüğe yazılır (kodlu sarmalayıcı; eskiden yalnız UAC reddi görülüyordu).
        // Sonuç yine YUTULUR — kaldırma her durumda sürer.
        // SON-A1.53: yalnız BU launcher'ın exe'sinin (aynı kök) adlı kuralları + yetim kurallar silinir — servis kurulumunun aynı
        // adlı kuralı (başka program) KALIR (D5 I-1 değişmezi; eskiden adla hepsi siliniyordu → servis LAN'ı sessizce kapanırdı).
        let fw_temizlik = ps_yukselterek_kos_kodlu(&pemf_launcher_core::firewall::silme_betigi(&install::backend_path(&root)));
        if let Ok(kod) = &fw_temizlik {
            eprintln!("[uninstall] güvenlik duvarı temizliği çıkış kodu {kod}{} (0 = tamam) — kaldırma sürer", if *kod == pemf_launcher_core::paylasim::KOD_UAC_REDDEDILDI { format!(": {}", pemf_launcher_core::dil::t("rust.hata.yoneticiIzniVerilmedi")) } else { String::new() });
        }
        if let Err(e) = fw_temizlik {
            eprintln!("[uninstall] güvenlik duvarı kuralları temizlenemedi (yok sayıldı): {e}");
        }

        // uninstall.exe launcher exe'sinin YANINDADIR (NSIS ikisini de $INSTDIR'a koyar). current_exe
        // üzerinden bul → özel kurulum dizinlerinde de doğru (sabit yol varsaymaz).
        let uninstaller = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.join("uninstall.exe")))
            .filter(|p| p.exists())
            .ok_or_else(|| {
                pemf_launcher_core::dil::t("rust.hata.kaldiriciYok")
            })?;
        spawn_uninstaller_detached(&uninstaller)?;
        app.exit(0); // launcher ÇIKMALI ki uninstaller çalışan PEMFVetClient.exe'yi silebilsin
        Ok(())
    }
    #[cfg(not(windows))]
    {
        let _ = app; // mac/linux: platform paket-kaldırıcısı ayrı → indirilen payload'u temizle
        install::remove_install(&root)
            .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.kaldirmaBasarisiz", &[("e", &e.to_string())]))
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
    // KP-5 B4: kararlar `oturum_ilk_durum` / `oturum_yenileme_sonucu`nda (kök, bellek, saat ve yenileyici ENJEKTE — testli); burada yalnız
    // gerçek kök + iki `spawn_blocking` evresi (okuma · yenileme; iletileri AYNEN).
    let root = install::default_install_root(&home_dir());
    let (bellek, root2) = (state.session.clone(), root.clone());
    let ilk = tauri::async_runtime::spawn_blocking(move || oturum_ilk_durum(&bellek, &root2, auth::now_unix()))
        .await
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.oturumOkumaGorevCoktu", &[("e", &e.to_string())]))?;
    let kayitli = match ilk {
        OturumIlkDurum::Sonuc(durum) => return Ok(durum),
        OturumIlkDurum::Yenile(kayitli) => kayitli,
    };
    let bellek = state.session.clone();
    tauri::async_runtime::spawn_blocking(move || {
        oturum_yenileme_sonucu(&bellek, &root, kayitli, |rt, eposta| (auth::refresh_budgeted(rt, eposta), auth::son_yenileme_reddi()))
    })
    .await
    .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.oturumYenilemeGorevCoktu", &[("e", &e.to_string())]))
}

/// `auth_status`un ilk evresinin sonucu: ya karar verildi (bellek / kayıt yok / taze kayıt) ya da kayıtlı oturum sessiz yenilenmeli.
enum OturumIlkDurum {
    Sonuc(AuthStatus),
    Yenile(auth::Session),
}

/// KP-5 B4 (A2 deseni): `auth_status` 1)–3) — bellek, "Beni hatırla" kaydı (işletim sistemi korumalı, yerel okuma — ağ YOK), tazelik.
/// Kök / bellek / ŞİMDİ ENJEKTE (testte geçici kök). Sıra AYNEN: bellekte oturum → "fresh" · kayıt yok → çıkış · kayıt taze → belleğe
/// al, "cached" · bayat → yenilemeye.
fn oturum_ilk_durum(bellek: &Mutex<Option<auth::Session>>, root: &std::path::Path, simdi: i64) -> OturumIlkDurum {
    // 1) Bu süreçte zaten giriş yapılmışsa (bellek) — ağa hiç çıkma.
    if let Some(s) = bellek.lock().unwrap().clone() {
        return OturumIlkDurum::Sonuc(AuthStatus::giris_yapildi(&s.email, "fresh", false));
    }
    // 2) "Beni hatırla" blob'u (işletim sistemi korumalı). Ağ YOK — yerel okuma.
    let Some(kayitli) = secret_store::load(root) else {
        return OturumIlkDurum::Sonuc(AuthStatus::cikis_yapildi(false));
    };
    // 3) Jeton hâlâ tazeyse ağa çıkmaya gerek yok (açılış hızlı kalsın).
    if !kayitli.needs_refresh(simdi) {
        *bellek.lock().unwrap() = Some(kayitli.clone());
        return OturumIlkDurum::Sonuc(AuthStatus::giris_yapildi(&kayitli.email, "cached", false));
    }
    OturumIlkDurum::Yenile(kayitli)
}

/// KP-5 B4 (A2 deseni): `auth_status` 4) — sessiz yenileme (duvar saati bütçeli; `yenile` ENJEKTE → testte sahte) ve `oturum_karari`
/// (Yenilendi → yeni refresh_token SAKLA + belleğe · Sil → nedeni günlüğe + kaydı sil · çevrimdışı / geçici → nedeni günlüğe, kayıtlı
/// oturumla devam — yukarıdaki OFFLINE KARARI). Yan etkiler AYNEN.
fn oturum_yenileme_sonucu(
    bellek: &Mutex<Option<auth::Session>>,
    root: &std::path::Path,
    kayitli: auth::Session,
    yenile: impl FnOnce(&str, &str) -> (Result<auth::Session, auth::AuthError>, Option<String>),
) -> AuthStatus {
    let (sonuc, red) = yenile(&kayitli.refresh_token, &kayitli.email);
    match (oturum_karari(&sonuc), sonuc) {
        (OturumKarari::Yenilendi, Ok(yeni)) => {
            // Yenilenen refresh_token'ı SAKLA (Supabase rotasyon yapar; eskisi geçersizleşir).
            let _ = secret_store::save(root, &yeni);
            let email = yeni.email.clone();
            *bellek.lock().unwrap() = Some(yeni);
            AuthStatus::giris_yapildi(&email, "fresh", false)
        }
        (OturumKarari::Sil, _) => {
            // 🔴 SAHA (2026-10-17): silme NEDENİ günlüğe (yalnız HTTP durumu + GoTrue kodu; jeton / e-posta YOK).
            if let Some(o) = oturum_gunlugu_olayi(&OturumKarari::Sil, red.as_deref()) {
                secret_store::oturum_gunlugune_yaz(root, &o);
            }
            secret_store::clear(root);
            AuthStatus::cikis_yapildi(false)
        }
        // ÇEVRİMDIŞI / geçici sunucu hatası → kayıtlı oturumla devam (yukarıdaki OFFLINE KARARI).
        _ => {
            if let Some(o) = oturum_gunlugu_olayi(&OturumKarari::CevrimdisiDevam, red.as_deref()) {
                secret_store::oturum_gunlugune_yaz(root, &o);
            }
            let email = kayitli.email.clone();
            *bellek.lock().unwrap() = Some(kayitli);
            AuthStatus::giris_yapildi(&email, "cached", true)
        }
    }
}

/// KP-5 B4 (A2 deseni): `auth_login` sonrası "Beni hatırla" kaydı — kök ENJEKTE (testte geçici kök). 2026-10-18: kutunun kararı AYRICA
/// tercih işaretine yazılır — pencerede çıkış kaydı siler ama bu kararı silmez, pencerede yapılan sonraki giriş yeniden hatırlanır
/// (secret_store::rotasyonu_isle rıza kapısı). "Beni hatırla" İŞARETSİZ → oturum SÜREÇ-ÖMÜRLÜ; önceki bir kayıt da temizlenir (yoksa
/// kullanıcı kutucuğu kaldırdığında eski jeton diskte kalırdı).
fn giris_kaydini_isle(root: &std::path::Path, oturum: &auth::Session, hatirla: bool) {
    secret_store::hatirla_tercihini_yaz(root, hatirla);
    if hatirla {
        secret_store::save(root, oturum);
    } else {
        secret_store::clear(root);
    }
}

/// KP-5 B4 (A2 deseni): `auth_logout` gövdesi — sıra AYNEN: ÖNCE yerel / backend temizliği (kesin çalışır: backend devir oturumu →
/// "Beni hatırla" kaydı), SONRA ağ bildirimi (best-effort; çevrimdışıysa sessizce geçer). Backend temizleyici ve ağ bildirimi ENJEKTE.
fn cikis_isle(
    root: &std::path::Path,
    port: Option<u16>,
    oturum: Option<auth::Session>,
    backend_temizle: impl FnOnce(u16),
    aga_bildir: impl FnOnce(&str),
) {
    if let Some(p) = port {
        backend_temizle(p);
    }
    secret_store::clear(root);
    if let Some(s) = oturum {
        aga_bildir(&s.access_token);
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

/// Açılış yenilemesinin oturum tanı günlüğü satırı (saf → birim-testlenebilir). `red`: `auth::son_yenileme_reddi()`
/// (yalnız HTTP durumu + GoTrue kodu). Silmede HER ZAMAN satır; korumada yalnız sunucu yanıt verdiyse (ağ yoksa günlük
/// boşuna büyümesin); yenilendiyse satır yok.
fn oturum_gunlugu_olayi(karar: &OturumKarari, red: Option<&str>) -> Option<String> {
    match karar {
        OturumKarari::Sil => Some(format!(
            "acilis yenilemesi REDDEDILDI ({}) -> 'Beni hatirla' kaydi SILINDI, giris ekrani",
            red.unwrap_or("kayitli refresh jetonu bos")
        )),
        OturumKarari::CevrimdisiDevam => {
            red.map(|r| format!("acilis yenilemesi basarisiz ({r}) -> kayit KORUNDU, cevrimdisi devam"))
        }
        OturumKarari::Yenilendi => None,
    }
}

fn oturum_karari(sonuc: &Result<auth::Session, auth::AuthError>) -> OturumKarari {
    match sonuc {
        Ok(_) => OturumKarari::Yenilendi,
        Err(auth::AuthError::SessionRevoked) => OturumKarari::Sil,
        Err(_) => OturumKarari::CevrimdisiDevam,
    }
}

/// Y211 · S-D67.15: giriş hatası arayüze `{kod, mesaj}` olarak gider — `doLogin`'in DAVRANIŞI makine-okur koda (`AuthError::kod`),
/// ekran metni `mesaj`a bakar (metin dil / üslup için değişebilir; eskiden "parola hatalı" metni sözleşmeydi).
#[derive(serde::Serialize)]
struct GirisHatasi {
    kod: &'static str,
    mesaj: String,
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
) -> Result<AuthStatus, GirisHatasi> {
    let (e, p) = (email.trim().to_string(), password);
    let sonuc = tauri::async_runtime::spawn_blocking(move || auth::login_budgeted(&e, &p)).await.map_err(|err| GirisHatasi {
        kod: "gorev_coktu",
        mesaj: pemf_launcher_core::dil::t_ile("rust.hata.girisGorevCoktu", &[("err", &err.to_string())]),
    })?;
    // `AuthError`'ın Display'i zaten TÜRKÇE ve HTTP gövdesini yansıtmaz (bkz. core/auth.rs).
    let session = sonuc.map_err(|err| GirisHatasi { kod: err.kod(), mesaj: err.to_string() })?;

    let root = install::default_install_root(&home_dir());
    let s2 = session.clone();
    let hatirla = remember && secret_store::available();
    let _ = tauri::async_runtime::spawn_blocking(move || giris_kaydini_isle(&root, &s2, hatirla)).await; // KP-5 B4: gövde testli

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
        // KP-5 B4: sıra `cikis_isle`de (testli); ağ çıkışı best-effort, çevrimdışıysa sessizce geçer.
        cikis_isle(&root, port, session, backend::clear_desktop_session, |jeton| {
            let _ = auth::logout(jeton);
        })
    })
    .await
    .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.cikisGorevCoktu", &[("e", &e.to_string())]))?;

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

/// KP-4 A2c (Y257 a): `discard_pending_blocking`'in gövdesi — kök ENJEKTE (testte sahte kök; gerçek kurulum / gerçek ortam okunmaz).
fn discard_pending_ile(root: &std::path::Path, manifest_raw: Option<String>) -> Result<(), String> {
    install::clear_pending(&root);
    if let Some(m) = manifest_raw {
        install::clear_partials(&root, &flow::plan_part_paths(&m, &root));
    }
    Ok(())
}

/// OTO-GÜNCELLEME uygula: yeni launcher setup'ını indir (host-pinli) + SHA256 doğrula + sessiz (`/S`)
/// kur + yeniden başlat. GÜNCELLEME ONAYI (Y253 / Y254, 2026-11-06): UI bunu YALNIZ kullanıcı onayından (ya da zorunlu
/// güncellemeden) ve seans kapısı (`guncelleme_engeli`) açıldıktan SONRA çağırır — 2026-11-06'ya dek açılışta SORMADAN çağrılıyordu.
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
        Err(pemf_launcher_core::dil::t("rust.hata.otoGuncellemeDesteklenmiyor"))
    }
    #[cfg(windows)]
    {
        // GÜVENLİK: imzasız setup exe çalıştırılacak → SHA256 ZORUNLU (manifest host-pinli kaynaktan
        // geldiği için sha güven çıpasıdır). url host-pinlemesi download_to_file içinde uygulanır.
        if sha256.trim().is_empty() {
            return Err(pemf_launcher_core::dil::t("rust.hata.guncellemeSha256Yok"));
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
            // GÜNCELLEME ONAYI: onaylı akış etkin seans bitene dek bekleyip YENİDEN dener — doğrulanmış kurucu (adı sha'ya bağlı)
            // zaten duruyorsa yeniden İNMEZ; bozuk / yarım dosya doğrulamadan geçemez → normal indirme.
            if verify::verify_file(&dest2, &sha).is_err() {
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
                pemf_launcher_core::dil::t_ile("rust.hata.guncellemeDogrulanamadi", &[("e", &e.to_string())])
            })?;
            Ok(())
        })
        .await
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.guncellemeGorevCoktu", &[("e", &e.to_string())]))??;

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
                            pemf_launcher_core::dil::t("rust.hata.seansBasladiGuncellemeErtelendi"),
                        )
                    }
                    None => {
                        return Err(
                            pemf_launcher_core::dil::t("rust.hata.kurulumBackendYanitsiz"),
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
        let pencere_sonuc = guncelleme_penceresini_ac(&sfx);
        // Bulgu #6: pencere sonucunu yardımcının GÜNLÜĞÜNE yaz (aynı dosya; batch `>>` ile ekler).
        // Dosya adı `build_relaunch_script`in %TEMP%\pemf_selfupdate_<pid>.log'uyla AYNI olmalı.
        let _ = std::fs::write(
            std::env::temp_dir().join(format!("pemf_selfupdate_{}.log", std::process::id())),
            pencere_gunluk_satiri(&pencere_sonuc),
        );
        let pencere = pencere_sonuc.ok(); // akış değişmez: pencere hatası güncellemeyi DURDURMAZ
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

/// Pencere sonucunun relauncher günlüğüne yazılacak satırı — saf, tablo-testli (bulgu #6).
#[cfg_attr(not(windows), allow(dead_code))]
fn pencere_gunluk_satiri(sonuc: &Result<std::path::PathBuf, String>) -> String {
    match sonuc {
        Ok(p) => format!("[rust] pencere=1 {}\r\n", p.display()),
        Err(e) => format!("[rust] pencere=0 {e}\r\n"),
    }
}

/// Sessiz kurulum + yeniden başlatma helper'ı (Windows). Bu launcher ÇIKTIKTAN sonra bağımsız
/// çalışsın diye DETACHED bir batch başlatır: kısa bekle (launcher çıksın, exe kilidi bıraksın) →
/// setup'ı `/S` sessiz kur (NSIS eski sürümü kaldırıp yenisini kurar) → yeni launcher'ı başlat →
/// kendini sil. Tauri NSIS `currentUser` kurulumu (AppData\Local) olduğundan UAC prompt'u YOK.
/// Yeniden-başlatma batch'inin İÇERİĞİNİ üret (saf → birim-test edilebilir). Batch-enjeksiyonu
/// savunması: yollar tırnak / yeni-satır içeremez (meşru Windows yollarında bulunmaz). `ping` =
/// taşınabilir uyku (timeout.exe redirected-stdin'de çalışmaz): ~3sn bekle → sessiz kur → ~2sn → başlat.
/// 🔴 SAHA ARIZASI 2026-09-05 — YARDIMCI BATCH'İN SÜREÇ BAYRAKLARI.
///
/// `DETACHED_PROCESS` verilen `cmd.exe` KONSOLSUZ başlar ve **ilk BORU (`|`) satırında ÖLÜR**.
/// 1.9.45'te bekleme döngüsüne `tasklist … | find …` eklendi; o satır batch'in İLK çalışan
/// satırıydı → yardımcı hiç kurulum yapmadan ölüyordu. Görünen belirti dört katlıydı ve hiçbiri
/// sebebi göstermiyordu: kurulum olmuyor, uygulama geri açılmıyor, bilgilendirme penceresi
/// 180 sn ekranda kalıyor, `.bat` kendini silmiyor (sonuna hiç varmıyor).
///
/// ÖLÇÜM (varsayım değil): aynı batch dört bayrak kombinasyonuyla koşuldu —
///   DETACHED|GRUP|NO_WINDOW → yalnız "BASLADI" yazıldı, boruda öldü
///   DETACHED|GRUP           → yalnız "BASLADI" yazıldı, boruda öldü
///   GRUP|NO_WINDOW          → SONA KADAR koştu
///   bayraksız               → SONA KADAR koştu
///
/// `CREATE_NO_WINDOW` konsol-altsistem sürece GİZLİ bir konsol verir: boru çalışır, kullanıcı
/// hiçbir şey görmez (siyah-konsol kapısı korunur). Süreç bağımsızlığı `DETACHED_PROCESS`e
/// BAĞLI DEĞİLDİR — Windows'ta ebeveynin çıkması çocuğu öldürmez; Ctrl+C/konsol sinyallerinden
/// ayrışma `CREATE_NEW_PROCESS_GROUP` ile zaten sağlanır.
#[cfg(windows)]
const YARDIMCI_BATCH_BAYRAKLARI: u32 = 0x0000_0200 /* CREATE_NEW_PROCESS_GROUP */ | 0x0800_0000 /* CREATE_NO_WINDOW */;

#[cfg(windows)]
fn build_relaunch_script(installer: &str, exe: &str, eski_pid: u32, pencere: Option<&str>) -> Result<String, String> {
    for p in [Some(installer), Some(exe), pencere].into_iter().flatten() {
        if p.contains('"') || p.contains('\r') || p.contains('\n') {
            return Err(pemf_launcher_core::dil::t("rust.hata.guncellemeYoluGuvensiz"));
        }
    }
    let exe_adi = std::path::Path::new(exe)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("PEMFVetClient.exe");
    // Araçları TAM YOLLA çağır: PATH'te Git'in `find`i öne çıkabiliyor (geliştirici makinesi).
    const TL: &str = "%SystemRoot%\\System32\\tasklist.exe";
    const FS: &str = "%SystemRoot%\\System32\\findstr.exe";
    // ⚠️ BORU YASAK (yukarıdaki saha arızası). `tasklist` çıktısı GEÇİCİ DOSYAYA yönlendirilir,
    // `findstr` o dosyayı okur. Yönlendirme konsolsuz `cmd`de de çalışır; boru çalışmaz.
    // Kapı: `betik_BORU_icermez` + `yardimci_batch_uretimdeki_bayraklarla_SONA_KADAR_kosar`.
    let t = format!("%TEMP%\\pemf_upd_{eski_pid}.txt");
    let g = format!("%TEMP%\\pemf_selfupdate_{eski_pid}.log");
    let mut s = String::from("@echo off\r\n");
    s.push_str(&format!("set \"T={t}\"\r\nset \"G={g}\"\r\n"));
    // Günlük: bu yardımcı sessizce ölürse sahada tek kanıt budur (arıza tam da bu yüzden
    // teşhis edilemiyordu — hiçbir yere hiçbir şey yazılmıyordu).
    // `>>` (EKLE) — Rust tarafı aynı dosyaya pencere sonucunu ÖNCE yazar (bulgu #6); `>` onu ezerdi.
    s.push_str("echo [%DATE% %TIME%] yardimci basladi >> \"%G%\"\r\n");
    // 1) Launcher'ın çıkmasını PID ile bekle (~1 sn adımlarla; en çok ~30 sn).
    s.push_str("set /a n=0\r\n:bekle\r\n");
    s.push_str(&format!("{TL} /FI \"PID eq {eski_pid}\" /NH > \"%T%\" 2>nul\r\n"));
    s.push_str(&format!("{FS} /C:\" {eski_pid} \" \"%T%\" >nul 2>&1\r\n"));
    s.push_str("if errorlevel 1 goto kur\r\nset /a n+=1\r\nif %n% GEQ 30 goto kur\r\n");
    s.push_str("ping -n 2 127.0.0.1 >nul\r\ngoto bekle\r\n:kur\r\n");
    s.push_str("echo [%TIME%] kurulum baslatiliyor (bekleme turu %n%) >> \"%G%\"\r\n");
    // 2) Sessiz kurulum (NSIS eski dosyaların üstüne yazar; `/S`te kancalar koşmaz).
    s.push_str(&format!("\"{installer}\" /S\r\n"));
    s.push_str("echo [%TIME%] kurulum bitti errorlevel=%ERRORLEVEL% >> \"%G%\"\r\n");
    s.push_str("ping -n 2 127.0.0.1 >nul\r\n");
    // 3) Kullanıcı bu arada yeni exe'yi KENDİSİ açtıysa ikinci pencere AÇMA. `/FO CSV` ŞART:
    //    tablo çıktısı görüntü adını 25 karakterde KIRPAR (ölçüldü: uzun ad hiç eşleşmedi → ikinci
    //    pencere açıldı); CSV kırpmaz. `/NH` başlığı atar.
    s.push_str(&format!("{TL} /FI \"IMAGENAME eq {exe_adi}\" /NH /FO CSV > \"%T%\" 2>nul\r\n"));
    s.push_str(&format!("{FS} /I /C:\"{exe_adi}\" \"%T%\" >nul 2>&1\r\n"));
    // ⚠️ `if errorlevel` ile onu ÜRETEN komut arasına HİÇBİR satır girmez (echo dahil): araya
    // giren komut ERRORLEVEL'i sıfırlayabilir ve uygulama bir daha ASLA başlatılmaz. Günlük
    // satırı bu yüzden if'ten SONRA. Parantezli if/else de kullanılmaz — `%TIME%` gibi özel
    // karakterli değerlerle blok ayrıştırması kırılgandır.
    s.push_str(&format!("if errorlevel 1 start \"\" \"{exe}\"\r\n"));
    s.push_str("echo [%TIME%] baslatma adimi gecildi >> \"%G%\"\r\n");
    s.push_str("del \"%T%\" >nul 2>&1\r\n");
    // 4) Bilgilendirme penceresinin kopyasını (kendini kapatınca) sil — en çok ~40 sn dene.
    if let Some(pk) = pencere {
        s.push_str("set /a k=0\r\n:sil\r\n");
        s.push_str(&format!("del \"{pk}\" >nul 2>&1\r\nif not exist \"{pk}\" goto son\r\n"));
        s.push_str("set /a k+=1\r\nif %k% GEQ 40 goto son\r\nping -n 2 127.0.0.1 >nul\r\ngoto sil\r\n:son\r\n");
    }
    s.push_str("echo [%TIME%] yardimci bitti >> \"%G%\"\r\n");
    s.push_str("del \"%~f0\"\r\n");
    Ok(s)
}

/// Kaldırma batch'inin İÇERİĞİNİ üret (saf → birim-test edilebilir). Batch-enjeksiyon savunması:
/// yol tırnak/yeni-satır içeremez (meşru Windows yollarında bulunmaz). `ping` = taşınabilir uyku
/// (`timeout.exe` redirected-stdin'de çalışmaz): ~5sn bekle (launcher çıksın, `PEMFVetClient.exe`
/// kilidi kalksın) → uninstaller'ı İNTERAKTİF başlat (kullanıcı 'uygulama verisini sil' checkbox'ını
/// görsün; `/S` YOK) → batch kendini sil.
#[cfg(windows)]
fn build_uninstall_script(uninstaller: &str) -> Result<String, String> {
    if uninstaller.contains('"') || uninstaller.contains('\r') || uninstaller.contains('\n') {
        return Err(pemf_launcher_core::dil::t("rust.hata.kaldiriciYoluGuvensiz"));
    }
    Ok(format!(
        "@echo off\r\n\
         ping -n 6 127.0.0.1 >nul\r\n\
         start \"\" \"{unins}\"\r\n\
         del \"%~f0\"\r\n",
        unins = uninstaller,
    ))
}

/// `-EncodedCommand` taşıması: UTF-16LE + base64 (ortak; kaçış katmanlarında bozulmaz).
#[cfg(windows)]
fn ps_b64(betik: &str) -> String {
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
}

/// D5 J-3 tur 3 · ÜRÜN KARARI [ÖNERİLEN UYGULANDI]: yükseltilmiş sürecin nesnesi ya da çıkış kodu OKUNAMAZSA (`$p` /
/// `$p.ExitCode` boş) sarmalayıcı SIFIR DIŞI çıkar (fail-closed). Eskiden `exit $p.ExitCode` → `exit $null` = 0 → "İzin ver"
/// arayüzü "tamam" deyip uyarıyı kapatıyordu (paylaşım kurulumu da "kuruldu" sayıyordu). 1 = PowerShell'in yakalanmamış hata
/// koduyla AYNI genel hata: güvenlik duvarında MEVCUT "kural eklenemedi (kod 1)", paylaşımda MEVCUT `paylasimBasarisiz` iletisi
/// (özel kodlar 3 / 4 / 5 / 1223 ile ÇAKIŞMAZ; yeni kullanıcı metni YOK).
#[cfg_attr(not(windows), allow(dead_code))]
const KOD_YUKSELTILMIS_CIKIS_KODU_YOK: i32 = 1;

/// D5 J-3 (tur 2): "İzin ver" yükseltilmiş betiğinin SONUCU → arayüz yanıtı (SAF eşleme; davranışı app crate testinde ölçülür).
/// `Err` (PowerShell / yükseltme başlatılamadı) ve UAC reddi (1223) → MEVCUT ileti (`guvenlikDuvariIzinYok`); 0 → "tamam";
/// sıfır dışı başka her kod → kodu taşıyan hata (`firewall::ekleme_hata_anahtari`) — arayüz uyarıyı KAPATMAZ.
#[cfg_attr(not(windows), allow(dead_code))]
fn izin_ver_sonucu(kod: Result<i32, String>) -> Result<serde_json::Value, String> {
    let kod = kod.map_err(|_| pemf_launcher_core::dil::t("rust.hata.guvenlikDuvariIzinYok"))?;
    match pemf_launcher_core::firewall::ekleme_hata_anahtari(kod) {
        None => Ok(serde_json::json!({ "status": "ok" })),
        Some(anahtar) => Err(pemf_launcher_core::dil::t_ile(anahtar, &[("kod", &kod.to_string())])),
    }
}

/// KP-4 A2c (Y257 a): `kaldirma_veri_konumu_blocking`'in gövdesi — ev dizini ve ortam okuyucusu ENJEKTE (gerçek ortam okunmaz).
fn kaldirma_veri_konumu_ile(ev: &std::path::Path, getenv: impl Fn(&str) -> Option<String>) -> serde_json::Value {
    let (konum, diger) = install::kaldirma_veri_konumu_with(&install::default_install_root(ev), getenv, ev);
    serde_json::json!({
        "konum": konum.to_string_lossy(),
        "diger": diger.iter().map(|d| d.to_string_lossy().into_owned()).collect::<Vec<_>>(),
    })
}

/// KP-4 A2c (Y257 a): `yedek_hedefi_durumu_blocking`'in gövdesi — kök ENJEKTE (testte sahte kök; gerçek kurulum / gerçek ortam okunmaz).
fn yedek_hedefi_durumu_ile(root: &std::path::Path) -> serde_json::Value {
    let secili = install::backup_dir_oku(&root);
    let erisilebilir = secili.as_deref().map(install::dizin_yazilabilir_mi).unwrap_or(false);
    serde_json::json!({
        "yol": secili.map(|p| p.to_string_lossy().into_owned()),
        "erisilebilir": erisilebilir,
    })
}

/// Klasör seçicinin (PowerShell + WinForms) çıktısını yorumla — SAF, tablo-testli.
///
/// 🔴 DENETİM 2026-09-06 (bulgu #3): boş stdout KOŞULSUZ "iptal" sayılıyordu; `o.status` hiç
/// okunmuyor, `o.stderr` düşüyordu. Oysa PowerShell'in KENDİSİ düşmüş olabilir: CLM/WDAC altında
/// `Add-Type` yasak, WinForms yüklenemez, PS çöker → stdout boş, stderr dolu, çıkış ≠ 0. Bu,
/// operatörün "İptal"inden AYIRT EDİLEMEZDİ; UI yalnız düğmeyi geri açıyor, launcher'da günlük yok
/// (Tier-1 özellik sessiz ölüyor). Kardeş spawn'lar (`ps_yukselterek_kos_kodlu`, firewall) status'u okur;
/// bu bir boşluktu, konvansiyon değil. Kural: çıkış başarısız YA DA (stdout boş VE stderr dolu) →
/// hata; boş stdout + başarı → iptal; dolu stdout → yol.
#[cfg_attr(not(windows), allow(dead_code))]
fn klasor_secici_sonucu(basarili: bool, kod: Option<i32>, stdout: &[u8], stderr: &[u8]) -> Result<Option<String>, String> {
    let yol = String::from_utf8_lossy(stdout).trim().to_string();
    let hata = String::from_utf8_lossy(stderr).trim().to_string();
    if !basarili || (yol.is_empty() && !hata.is_empty()) {
        let kod = kod.map(|k| k.to_string()).unwrap_or_else(|| pemf_launcher_core::dil::t("rust.hata.yok"));
        let ayrinti = if hata.is_empty() { pemf_launcher_core::dil::t("rust.hata.ayrintiYok") } else { hata };
        return Err(pemf_launcher_core::dil::t_ile("rust.hata.klasorSecici", &[("kod", &kod), ("ayrinti", &ayrinti)]));
    }
    Ok(if yol.is_empty() { None } else { Some(yol) })
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

// KP-4 A1 (Y257 c): S sınıfı Tauri kabuğu (pencere / WebView / Tauri çalışma zamanı / gerçek platform) AYRI DOSYADA ama AYNI
// modülde — `include!` görünürlüğü / yolları / komut kaydını değiştirmez; kapsam ölçümü kabuk.rs'i dosya adıyla dışlar.
include!("kabuk.rs");

#[cfg(test)]
mod tests {
    use super::*;

    /// LN L12: açılış bildirimi (ve onun beslediği sessiz kurulum) launcher güncelleme kararını çekirdeğin TEK fonksiyonundan
    /// alır (`Manifest::launcher_guncellemesi` — adlı birim testi orada: yayında 1.9.51 iken 1.9.52 kendini GERİ indirmez).
    /// Satır içi bir sürüm kıyası geri gelirse (ters argüman sırası dahil) çekirdek testi onu görmez — bu kapı görür.
    #[test]
    fn KRITIK_L12_acilis_bildirimi_cekirdegin_TEK_kararini_kullanir() {
        // SON-A3.53 (22-SON): yorum SOYULUR — çağrı metni yalnız yorumda kalıp satır içi `!=` kıyası gelince kapı yeşil kalıyordu
        // (mutant ölçüldü: 1.9.52 yayındaki 1.9.51'i "yeni" sayar → kendini geri indirir). Dize içine taşınan çağrı metnine karşı
        // `manifest.launcher` ALANINA doğrudan erişim de yasak (yalnız `manifest.launcher_guncellemesi(` yöntemi serbest).
        let src = f5_yorumlari_soy(include_str!("main.rs"));
        // KP-4 A2c: kararın gövdesi `profilleri_getir`de (kök / çekici enjekte); kabuk `fetch_profiles_blocking` yalnız bağlar.
        let ks = kabuk_soy(); // KP-5 B2: ince kabuk kabuk.rs'te (S); karar main.rs `profilleri_getir`de
        let kabuk = &ks[ks.find(concat!("fn fetch_profiles_", "blocking(")).expect("fetch_profiles_blocking yok")..];
        let kabuk = &kabuk[..kabuk.find("\n\u{7d}").expect("kabuk sonu yok")];
        assert!(kabuk.contains("profilleri_getir(") && !kabuk.contains("launcher_guncellemesi"), "kabuk karar içeriyor / gövdeye bağlanmıyor");
        let g = &src[src.find(concat!("fn profilleri_", "getir(")).expect("profilleri_getir yok")..];
        let g = &g[..g.find("\n\u{7d}").expect("gövde sonu yok")];
        assert!(g.contains("manifest.launcher_guncellemesi(current_launcher)"), "açılış bildirimi çekirdeğin kararını kullanmıyor");
        assert!(!g.contains(concat!("is_", "newer(")), "açılış bildiriminde satır içi sürüm kıyası var");
        let alan = concat!("manifest.", "launcher");
        let dogrudan: Vec<usize> = g.match_indices(alan).map(|(i, _)| i).filter(|&i| !g[i + alan.len()..].starts_with('_')).collect();
        assert!(dogrudan.is_empty(), "açılış bildirimi `manifest.launcher` alanını doğrudan okuyor (çekirdek kararını atlayan satır içi kıyas yolu)");
    }

    /// SAHİP BİLDİRİMİ 2026-10-18: "güncelleme kontrol ediliyor yazarken pencere bloklanıyor hareket ettiremiyorum".
    /// Tauri SENKRON komutları pencere (olay döngüsü) iş parçacığında koşar; PowerShell / ağ / yavaş disk bekleyen bir senkron
    /// komut pencereyi dondurur (ölçüldü: `firewall_durumu`'nun PowerShell sorgusu 2,2–2,4 sn, açılışta ve backend başlayınca).
    /// Kural: bu tür bekleyen bir çağrı taşıyan HİÇBİR `#[tauri::command]` senkron olamaz; adı bilinen komutlar `async` +
    /// `spawn_blocking` olmalı (gövdeleri `*_blocking`).
    #[test]
    fn KRITIK_bekleyen_is_yapan_komut_PENCERE_is_parcaciginda_kosmaz() {
        let soy_main = f5_yorumlari_soy(include_str!("main.rs")).replace("\r\n", "\n"); // çalışma kopyası CRLF olabilir
        let soy = kabuk_soy(); // KP-4 A1: komut kabukları kabuk.rs'te; main.rs'teki komutlar da AYRICA taranır
        // 2026-10-18 genişletme (sahip: "aynı sorunlu başka işlem de olabilir detaylı incele"): disk işleri de (ağaç silme / takas
        // kurtarma / kayıt yazma / yarım indirme silme) — `detect_environment`, `check_runtime_update`, `discard_pending` senkrondu.
        // YLI-A3.6: backend'e HTTP isteği atan / bekleyen yardımcılar ve uyku da (LN L3 / L6 / L2 yeni bekleyen çağrıları) — ANLIK
        // listedeki bir komuta eklenirlerse de pencere donar. `open_browser` (beklemeden süreç başlatır) bilinçli olarak YOK.
        const BEKLEYEN: [&str; 30] = [
            "gizli_komut(", "durum_icin(", "ps_yukselterek_kos(", "dizin_yazilabilir_mi", "ureq::", "fetch_string",
            "yarim_takasi_kurtar(", "adopt_unknown_models(", "pending_updates(", "clear_partials(", "clear_pending(",
            "remove_dir_all", "fs::remove_file", "fs::rename", "fs::write",
            "safe_stop_coils(", "yakma_suruyor_mu(", "yakmanin_bitmesini_bekle(", "yakmanin_bitmesini_bekle_sinirla(", // KI G1
            "yakma_bitene_kadar_bekle(", "firmware_kararini_bekle(",
            "session_active(", "probe_pemf_backend(", "detect_running_backend(", "guncelleme_kapisi_backendi(", "db_hazir_mi(",
            "stop_tracked_backend(", "stop_backend_for_teardown(", "thread::sleep", "fs::read",
        ];
        // Senkron kalmasına İZİN verilen komutlar: yalnız ANLIK iş (atomik bayrak, kısa kilitli kopya, pencere yoklaması,
        // beklemeden süreç başlatma). Listede olmayan YENİ senkron komut → kırmızı: pencere iş parçacığında koşar, gözden geçir.
        const ANLIK: [&str; 10] = [
            "app_window_open", "get_progress", "get_prefetch_progress", "pause_install", "cancel_install", "resume_install",
            "guncelleme_modu", "open_url", "dil_bilgisi", "dil_ayarla",
        ];
        let mut ihlal = Vec::new();
        for parca in soy.split("#[tauri::command]").skip(1).chain(soy_main.split("#[tauri::command]").skip(1)) {
            let govde = &parca[..parca.find("\n}\n").unwrap_or(parca.len())];
            let bas = govde.trim_start();
            if bas.starts_with("fn ") {
                let ad = bas[3..].split('(').next().unwrap_or("?").to_string();
                if let Some(m) = BEKLEYEN.iter().find(|m| govde.contains(**m)) {
                    ihlal.push(format!("{ad} ({m})"));
                } else if !ANLIK.contains(&ad.as_str()) {
                    ihlal.push(format!("{ad} (anlık iş listesinde değil)"));
                }
            }
        }
        assert!(ihlal.is_empty(), "pencere iş parçacığında bekleyen senkron komut(lar): {ihlal:?}");
        for ad in [
            "fetch_profiles", "firewall_durumu", "firewall_kurali_ekle", "yedek_hedefi_durumu", "yedek_hedefi_sec",
            "detect_environment", "check_runtime_update", "discard_pending", "kaldirma_veri_konumu",
            "paylasim_durumu", "paylasim_kur",
        ] {
            let bas = soy.find(&format!("async fn {ad}(")).unwrap_or_else(|| panic!("{ad} async DEĞİL"));
            let govde = &soy[bas..bas + soy[bas..].find("\n}\n").expect("gövde sonu")];
            assert!(govde.contains("spawn_blocking"), "{ad}: bekleyen gövde ayrı iş parçacığına alınmıyor");
        }
    }

    /// D3 T-g · Y182 ÖNCE-KIRMIZI: ikinci Windows hesabı için paylaşım komutları KAYITLI; kurma adımı yükseltilmiş betiğin ÇIKIŞ
    /// KODUNU okur (yutulan hata "kuruldu" sayılmaz), hesap kimliğini YÜKSELTİLMEMİŞ süreçten alır ve betiği çekirdekten üretir
    /// (yol / kaçış kararı tek yerde). Arayüz paylaşım kartını güvenlik duvarı uyarısından ÖNCE gösterir ve onu ezdirmez.
    #[test]
    fn KRITIK_T_g_ikinci_hesap_PAYLASIM_komutlari_ve_arayuz_karti() {
        let soy = kabuk_soy(); // KP-4 A1: çapa S kabuğunda (kabuk.rs)
        // Aranan iki dize BÖLÜNÜR: düz yazılsalar ayna kapısı (`generate_handler` bloğu) ve K-2'nin test bölgesi ayraç sayacı yanılır.
        const SON: &str = "\n\u{7d}\n"; // satır başında kapanan gövde
        let el = &soy[soy.find(concat!("tauri::generate_handler", "![")).expect("generate_handler yok")..];
        let el = &el[..el.find("])").expect("liste sonu")];
        assert!(el.contains("paylasim_durumu,") && el.contains("paylasim_kur,"), "paylaşım komutları kayıtlı değil");
        let kur = &soy[soy.find("fn paylasim_kur_blocking(").expect("kurma gövdesi yok")..];
        let kur = &kur[..kur.find(SON).expect("gövde sonu")];
        for parca in ["surec_hesabi_sid()", "kurma_betigi(&sid,", "ps_yukselterek_kos_kodlu(&betik)", "KOD_TAMAM =>", "hata_anahtari(kod)"] {
            assert!(kur.contains(parca), "kurma adımında {parca} yok");
        }
        let kodlu = &soy[soy.find("fn ps_yukselterek_kos_kodlu(").expect("kodlu yükseltme yok")..];
        let kodlu = &kodlu[..kodlu.find(SON).expect("gövde sonu")];
        assert!(kodlu.contains("-PassThru") && kodlu.contains("exit $p.ExitCode") && kodlu.contains("KOD_UAC_REDDEDILDI"), "{kodlu}");
        let html = include_str!("../ui/index.html").replace("\r\n", "\n");
        assert!(html.contains("invoke(\"paylasim_durumu\")") && html.contains("invoke(\"paylasim_kur\")"));
        for k in ["paylasimGerekli", "paylasimKvkk", "paylasimOturumYenile", "paylasimKur", "paylasimKuruldu"] {
            assert!(html.contains(&format!("t().{k}")), "arayüz {k} metnini göstermiyor");
        }
        let env = &html[html.find("async function refreshEnv()").expect("refreshEnv yok")..];
        let env = &env[..env.find("return env;").expect("refreshEnv sonu")];
        let p = env.find("paylasimKontrol()").expect("açılışta paylaşım denetlenmiyor");
        assert!(p < env.find("firewallKontrol(false)").expect("güvenlik duvarı denetimi yok"), "paylaşım kartı güvenlik duvarından SONRA");
        let fw = &html[html.find("async function firewallKontrol(").expect("firewallKontrol yok")..];
        assert!(fw[..fw.find("invoke(\"firewall_durumu\")").unwrap()].contains("paylasimNotu"), "güvenlik duvarı paylaşım kartını ezer");
    }

    /// D5 J-3 (tur 2 · çürütücü n10 / n2): "İzin ver" sonucunun DAVRANIŞI — saf `izin_ver_sonucu` (`firewall_kurali_ekle_blocking`
    /// yalnız onu çağırır; çekirdeğin `KRITIK_J3_main_rs_…` kapısı yorumlar soyulmuş gövdede bunu doğrular). Kodlar burada SABİT;
    /// beklenen ileti TR ya da EN katalog metni (etkin dil başka testte değişebilir), kod iletide.
    #[test]
    fn KRITIK_J3_izin_ver_sonucu_KOD_davranisi_UAC_reddi_mevcut_metin() {
        use pemf_launcher_core::dil::{katalog, Dil};
        let metinler = |anahtar: &str, kod: Option<i32>| -> Vec<String> {
            [Dil::Tr, Dil::En]
                .into_iter()
                .map(|d| {
                    let m = katalog(d).get(anahtar).unwrap_or_else(|| panic!("{anahtar} katalogda yok")).clone();
                    match kod {
                        Some(k) => m.replace("\u{7b}\u{7b}kod\u{7d}\u{7d}", &k.to_string()),
                        None => m,
                    }
                })
                .collect()
        };
        assert_eq!(izin_ver_sonucu(Ok(0)), Ok(serde_json::json!({ "status": "ok" })), "başarı (0) 'tamam' dönmüyor");
        for (kod, anahtar) in [
            (2, "rust.hata.guvenlikDuvariKuralEklenemedi"),
            (4242, "rust.hata.guvenlikDuvariKuralEklenemedi"),
            (1, "rust.hata.guvenlikDuvariKuralEklenemedi"),
            (-1, "rust.hata.guvenlikDuvariKuralEklenemedi"),
            (3, "rust.hata.guvenlikDuvariBozukKuralSilinemedi"),
        ] {
            let e = izin_ver_sonucu(Ok(kod))
                .expect_err(&format!("sıfır dışı çıkış {kod} 'tamam' sayıldı → arayüz uyarıyı kapatır, LAN erişimi YOK"));
            assert!(metinler(anahtar, Some(kod)).contains(&e), "kod {kod}: ileti {anahtar} değil ya da kodu taşımıyor: {e}");
        }
        let uac = metinler("rust.hata.guvenlikDuvariIzinYok", None);
        let e = izin_ver_sonucu(Ok(1223)).expect_err("UAC reddi (1223) 'tamam' sayıldı");
        assert!(uac.contains(&e), "UAC reddinin MEVCUT iletisi değişti: {e}");
        let e = izin_ver_sonucu(Err("powershell başlatılamadı".to_string())).expect_err("yükseltme başlatılamadı ama 'tamam'");
        assert!(uac.contains(&e), "yükseltme başlatılamayınca MEVCUT ileti dönmüyor: {e}");
    }

    /// `ac` konumundaki açılış ayracının kapanışından SONRAKİ konum (tırnak içindeki ayraçlar sayılmaz).
    fn j3_blok_sonu(s: &str, ac: usize) -> usize {
        let mut derinlik = 0i32;
        let mut tirnak: Option<char> = None;
        let mut onceki = ' ';
        for (i, c) in s[ac..].char_indices() {
            match tirnak {
                Some(q) => {
                    if c == q && onceki != '\\' {
                        tirnak = None;
                    }
                }
                None => match c {
                    '"' | '\'' | '`' => tirnak = Some(c),
                    '\u{7b}' => derinlik += 1,
                    '\u{7d}' => {
                        derinlik -= 1;
                        if derinlik == 0 {
                            return ac + i + c.len_utf8();
                        }
                    }
                    _ => {}
                },
            }
            onceki = if onceki == '\\' { ' ' } else { c };
        }
        panic!("ayraç kapanmıyor");
    }

    /// JS parçasından `//` ve `/* … */` yorumlarını atar (dizge içi korunur).
    fn j3_js_yorumsuz(s: &str) -> String {
        let k: Vec<char> = s.chars().collect();
        let mut o = String::new();
        let mut i = 0;
        let mut tirnak: Option<char> = None;
        while i < k.len() {
            let c = k[i];
            if let Some(q) = tirnak {
                o.push(c);
                if c == '\\' && i + 1 < k.len() {
                    o.push(k[i + 1]);
                    i += 1;
                } else if c == q {
                    tirnak = None;
                }
                i += 1;
            } else if c == '/' && k.get(i + 1) == Some(&'/') {
                while i < k.len() && k[i] != '\n' {
                    i += 1;
                }
            } else if c == '/' && k.get(i + 1) == Some(&'*') {
                i += 2;
                while i < k.len() && !(k[i] == '*' && k.get(i + 1) == Some(&'/')) {
                    i += 1;
                }
                i += 2;
            } else {
                if c == '"' || c == '\'' || c == '`' {
                    tirnak = Some(c);
                }
                o.push(c);
                i += 1;
            }
        }
        o
    }

    /// D5 J-3 (tur 2 · çürütücü n3): Rust `Err`ini kullanıcıya gösteren SON halka — "İzin ver" `onclick` işleyicisinde `catch` hatayı
    /// (`String(e)`) yazar, düğmeyi yeniden açar ve uyarıyı KAPATMAZ; `clearNotice()` YALNIZ başarıda (`invoke`dan SONRA) ve işleyicide
    /// TEK. JS yorumları soyulur (yorumda kalan satır sayılmaz). D3 T-g'nin `include_str!("../ui/index.html")` deseni.
    #[test]
    fn KRITIK_J3_arayuz_izin_ver_HATAYI_gosterir_uyariyi_KAPATMAZ() {
        let html = include_str!("../ui/index.html").replace("\r\n", "\n");
        let cagri = html.find("invoke(\"firewall_kurali_ekle\")").expect("arayüz 'İzin ver' komutunu hiç çağırmıyor");
        let bas = html[..cagri].rfind(".onclick").expect("'İzin ver' düğmesinin onclick işleyicisi yok");
        let ac = bas + html[bas..].find('\u{7b}').expect("işleyici gövdesi yok");
        let isleyici = j3_js_yorumsuz(&html[ac..j3_blok_sonu(&html, ac)]);
        let ct = isleyici.find("catch").expect("'İzin ver' işleyicisinde catch YOK — komut hatası kullanıcıya gösterilmez");
        let tr = isleyici[..ct].find("try").expect("'İzin ver' işleyicisinde try yok");
        let dene = &isleyici[tr..ct];
        // SON-A1.52 (22 · A1b, yaşayan j3_m3b): `await invoke("firewall_kurali_ekle").then(null, () => null); clearNotice();` (Rust Err'i
        // YUTAR, uyarı kapanır — engel sürerken kullanıcı "tamam" sanır) metin aramasından GEÇİYORDU. try gövdesi İZİN LİSTESİYLE.
        let dene_yalin: String = dene.split_whitespace().collect();
        assert_eq!(
            dene_yalin, "try{awaitinvoke(\"firewall_kurali_ekle\");clearNotice();}",
            "'İzin ver' try gövdesi komutun hatasını yutabilecek biçimde değişti (.then / .catch / ek deyim / sıra): {dene}"
        );
        let i_inv = dene.find("await invoke(\"firewall_kurali_ekle\")").expect("komut try içinde beklenmiyor (yalnız yorumda?)");
        let i_kapa = dene.find("clearNotice()").expect("başarıda uyarı kapanmıyor");
        assert!(i_inv < i_kapa, "uyarı komutun SONUCUNDAN önce kapanıyor (hata da 'tamam' görünür)");
        let cac = ct + isleyici[ct..].find('\u{7b}').expect("catch gövdesi yok");
        let yakala = &isleyici[cac..j3_blok_sonu(&isleyici, cac)];
        assert!(
            yakala.contains(".textContent = String(e)"),
            "'İzin ver' hatası (Rust Err: kural kurulamadı / UAC reddi) kullanıcıya GÖSTERİLMİYOR: {yakala}"
        );
        assert!(yakala.contains("disabled = false"), "hata sonrası 'İzin ver' düğmesi yeniden açılmıyor: {yakala}");
        assert!(!yakala.contains("clearNotice("), "hata dalında uyarı KAPATILIYOR — engel sürerken kullanıcı 'tamam' sanır: {yakala}");
        assert_eq!(isleyici.matches("clearNotice(").count(), 1, "uyarıyı kapatan ikinci bir yol (finally / catch) var: {isleyici}");
        // TUR 3 (çürütücü 2 j2): `clearNotice(` ADI aranıyordu — `box.hidden = true` (aynı görünür etki) YEŞİLDİ. Artık catch gövdesi
        // İZİN LİSTESİYLE: yalnız `<öğe>.textContent = String(e)` (öğe = bu işlevde `document.createElement` ile kurulan metin öğesi,
        // uyarı kutusunun kendisi DEĞİL) ve `<düğme>.disabled = false` (düğme = bu onclick'in sahibi); başka HİÇBİR deyim yok.
        let catch_bas = &isleyici[ct..cac];
        assert!(catch_bas.contains("(e)"), "catch hatayı `e` adıyla bağlamıyor (String(e) başka şeyi gösterir): {catch_bas}");
        for yasak in ["hidden", "box.", "$(\"notice\")", "textContent = \"\"", "clearNotice", "innerHTML", "remove("] {
            assert!(!yakala.contains(yasak), "'İzin ver' hata dalı uyarıyı gizliyor / boşaltıyor (`{yasak}`): {yakala}");
        }
        let dugme: String = html[..bas]
            .chars()
            .rev()
            .take_while(|c| c.is_alphanumeric() || *c == '_' || *c == '$')
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect();
        assert!(!dugme.is_empty(), "onclick'in sahibi düğme adı okunamadı");
        let govde = yakala.trim().trim_start_matches('\u{7b}').trim_end_matches('\u{7d}');
        let (mut metin_ogesi, mut acildi) = (None::<String>, false);
        for d in govde.split(';').map(|s| s.split_whitespace().collect::<Vec<_>>().join(" ")).filter(|s| !s.is_empty()) {
            if let Some(h) = d.strip_suffix(".textContent = String(e)") {
                if metin_ogesi.is_none() && !h.is_empty() && h.chars().all(|c| c.is_alphanumeric() || c == '_' || c == '$') {
                    metin_ogesi = Some(h.to_string());
                    continue;
                }
            }
            if d == format!("{dugme}.disabled = false") && !acildi {
                acildi = true;
                continue;
            }
            panic!("'İzin ver' catch gövdesinde İZİN LİSTESİ DIŞI deyim: `{d}` (yalnız hata metni + düğmeyi açma) — {yakala}");
        }
        assert!(acildi, "hata sonrası onclick'in sahibi `{dugme}` yeniden açılmıyor: {yakala}");
        let h = metin_ogesi.expect("hata metni yazılmıyor");
        assert_ne!(h, dugme, "hata metni düğmenin ÜSTÜNE yazılıyor (uyarı metni kaybolur): {yakala}");
        let kutu = html[..bas].rfind("$(\"notice\")").expect("uyarı kutusu bu işlevde kurulmuyor");
        let tanim = html[..bas].rfind(&format!("const {h} = document.createElement(")).unwrap_or(0);
        assert!(
            tanim > kutu,
            "hata metni uyarı kutusunun İÇİNE kurulan metin öğesine yazılmıyor (`{h}` bu uyarıda createElement ile kurulmadı): {yakala}"
        );
    }

    /// Rust dizge sabitinin İÇERİĞİ → değer: `\`+satır sonu+girinti birleşir, `{{` / `}}` (format!) tek ayraca iner.
    fn j3_rust_dizge_coz(s: &str) -> String {
        let mut o = String::new();
        let mut it = s.chars().peekable();
        while let Some(c) = it.next() {
            if c == '\\' && it.peek() == Some(&'\n') {
                while matches!(it.peek(), Some(n) if n.is_whitespace()) {
                    it.next();
                }
            } else {
                o.push(c);
            }
        }
        o.replace("\u{7b}\u{7b}", "\u{7b}").replace("\u{7d}\u{7d}", "\u{7d}")
    }

    /// PowerShell komutundan `<# … #>` ve `# …` yorumlarını atar (bu komutta dizge içinde `#` yok).
    fn j3_ps_yorumsuz(s: &str) -> String {
        let mut o = s.to_string();
        while let Some(a) = o.find("<#") {
            let b = o[a..].find("#>").map(|b| a + b + 2).unwrap_or(o.len());
            o.replace_range(a..b, " ");
        }
        o.lines().map(|l| l.split('#').next().unwrap_or("")).collect::<Vec<_>>().join("\n")
    }

    /// D5 J-3 (tur 2 · çürütücü n1): kodlu yükseltme sarmalayıcısı iç sürecin ÇIKIŞ KODUNU aktarır — PowerShell yorumları soyulmuş
    /// komutta `-PassThru`, SON deyim `exit $p.ExitCode` ve başka `exit` yalnız UAC-reddi `catch`ında; Rust tarafı sürecin kodunu okur.
    /// (D3 T-g kapısı `exit $p.ExitCode`i HAM metinde arıyordu: `exit 0 <# exit $p.ExitCode #>` YEŞİLDİ — kod hiç aktarılmaz, arayüz
    /// her durumda "tamam".) Komut KOŞULMAZ — gerçek UAC / `Start-Process -Verb RunAs` YOK.
    #[test]
    fn KRITIK_J3_kodlu_sarmalayici_CIKIS_KODUNU_aktarir_PS_yorumsuz() {
        let soy = kabuk_soy(); // KP-4 A1: çapa S kabuğunda (kabuk.rs)
        let kodlu = &soy[soy.find("fn ps_yukselterek_kos_kodlu(").expect("kodlu yükseltme yok")..];
        let kodlu = &kodlu[..kodlu.find("\n\u{7d}\n").expect("gövde sonu")];
        let f = kodlu.find("format!(").expect("sarmalayıcı komutu format! ile kurulmuyor");
        let a = f + kodlu[f..].find('"').expect("komut dizgesi yok") + 1;
        let b = a + kodlu[a..].find('"').expect("komut dizgesi sonu yok");
        let ps = j3_ps_yorumsuz(&j3_rust_dizge_coz(&kodlu[a..b]));
        let ps = ps.split_whitespace().collect::<Vec<_>>().join(" ");
        assert!(ps.contains("-Verb RunAs -Wait -PassThru"), "yükseltilmiş süreç beklenmiyor / nesnesi alınmıyor: {ps}");
        assert!(
            ps.trim_end().trim_end_matches(';').trim_end().ends_with("exit $p.ExitCode"),
            "sarmalayıcının SON deyimi iç sürecin çıkış kodu değil (yorum soyulmuş): {ps}"
        );
        // TUR 3 (çürütücü 2 j3): `-ErrorAction Stop` `try` içindeki `Start-Process` çağrısında — UAC iptali SONLANDIRMAYAN hata
        // olursa `catch`e düşmez, `$p` boş kalır (gölge ölçümü: `-ErrorAction Stop` yokken çıkış 0 = "tamam").
        let dene = &ps[ps.find("try {").expect("sarmalayıcıda try yok")..ps.find("} catch {").expect("sarmalayıcıda catch yok")];
        assert!(
            dene.contains("Start-Process") && dene.contains("-ErrorAction Stop"),
            "UAC iptali (sonlandırmayan hata) catch'e DÜŞMEZ — `Start-Process … -ErrorAction Stop` try içinde değil: {dene}"
        );
        // TUR 3 ÜRÜN KARARI: çıkış kodu BOŞSA sıfır dışı (fail-closed) — koruma SON deyimden önce, değeri genel hata.
        let koruma = "if ($null -eq $p -or $null -eq $p.ExitCode) \u{7b} exit \u{7b}bos\u{7d} \u{7d}";
        let k = ps.find(koruma).unwrap_or_else(|| {
            panic!("çıkış kodu BOŞSA (`$p` / `$p.ExitCode` $null) sarmalayıcı sıfır dışı çıkmıyor — `exit $null` = 0 → 'tamam': {ps}")
        });
        assert!(k < ps.rfind("exit $p.ExitCode").expect("son exit yok"), "boş-kod koruması SON deyimden sonra (ulaşılmaz): {ps}");
        assert!(kodlu.contains("bos = KOD_YUKSELTILMIS_CIKIS_KODU_YOK"), "boş-kod koruması sabit dışı bir değerle çıkıyor");
        assert!(
            ![0, 3, 4, 5, pemf_launcher_core::paylasim::KOD_UAC_REDDEDILDI].contains(&KOD_YUKSELTILMIS_CIKIS_KODU_YOK),
            "boş-kod değeri {KOD_YUKSELTILMIS_CIKIS_KODU_YOK} başarı ya da ÖZEL bir sonuçla (UAC reddi / bozuk kural / paylaşım) karışıyor"
        );
        assert_eq!(
            ps.matches("exit ").count(),
            3,
            "UAC-reddi catch'i ve boş-kod koruması dışında ikinci bir sabit `exit` var (kod aktarılmaz): {ps}"
        );
        assert!(kodlu.contains("status.code()"), "Rust tarafı yükseltme sarmalayıcısının çıkış kodunu okumuyor");
    }

    /// 2026-10-18: ana pencere kapanınca bobin durdurma BİLEREK beklenir (süreç çıkıyor) — ama açık uygulama penceresi o 2–4 sn
    /// DONUK görünmesin: gizleme, bekleyen işten (`job()`) ÖNCE gelmeli; durdurma yine BEKLENİR (arka plana atılmaz).
    #[test]
    fn KRITIK_ana_pencere_kapanisinda_uygulama_penceresi_bekleyen_durdurmadan_ONCE_gizlenir() {
        let soy = kabuk_soy(); // KP-4 A1: çapa S kabuğunda (kabuk.rs)
        let bas = soy.find(".on_window_event(").expect("pencere olay işleyicisi yok");
        let blok = &soy[bas..bas + soy[bas..].find(".run(ctx)").expect("olay işleyicisi sonu")];
        let gizle = blok.find("appwin.hide()").expect("ana pencere kapanışında uygulama penceresi GİZLENMİYOR");
        let bekle = blok.find("job();").expect("ana pencere kapanışında bobin durdurma artık BEKLENMİYOR");
        assert!(gizle < bekle, "uygulama penceresi bobin durdurma bekleyişinden SONRA gizleniyor (o sürede donuk görünür)");
    }

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

    /// YAYIN 2026-11-03 ÖNCE-KIRMIZI (`buildId` bulgusu): güncelleme SAĞLIK KAPISINDA başlatılan backend onaydan sonra da
    /// çalışmaya devam eder → paket kimliğini eski kayıttan değil, onaylanacak paketten (`geri.paket_kimligi()`) almalı;
    /// yoksa güncellemeden sonraki ilk oturum `/api/health`te eski `buildId`i raporlar (bu makinede 03.11'de ölçüldü).
    #[test]
    fn KRITIK_saglik_kapisi_backendi_ONAYLANACAK_paket_kimligiyle_baslar() {
        let soy = f5_yorumlari_soy(include_str!("main.rs")).replace("\r\n", "\n");
        let kapi = &soy[soy.find("flow::update_installed(&manifest_raw, &root2").expect("güncelleme yolu yok")..];
        let kapi = &kapi[..kapi.find("flow::guncellemeyi_onayla(&root2, &geri)").expect("onay yok")];
        assert!(
            kapi.contains("flow::start_backend_kimlikli(&root2, &mut on, geri.paket_kimligi())"),
            "sağlık kapısı backend'i onaylanacak kimlik olmadan başlatıyor"
        );
        assert!(!kapi.contains("flow::start_backend(&root2"), "sağlık kapısında kimliksiz start_backend kaldı");
    }

    /// Sahip 2026-11-04 ÖNCE-KIRMIZI: PEMF kapatılınca PEMF-Gateway hotspot'u da kapanır. Kapatma YALNIZ bu başlatıcının
    /// durdurduğu backend'in kapanış işinde (benimsenen backend'e dokunulmaz) ve bobin STOP'u + kill + port temizliğinden SONRA
    /// (Ö.4-Y8 sırası bozulmaz); üretim kodunda başka yerde çağrılmaz.
    #[test]
    fn KRITIK_kapanis_isi_backendden_SONRA_hotspotu_kapatir() {
        let soy = kabuk_soy(); // KP-4 A1: çapa S kabuğunda (kabuk.rs)
        let main_soy = f5_yorumlari_soy(include_str!("main.rs")).replace("\r\n", "\n");
        let main_uretim = &main_soy[..main_soy.find("#[cfg(test)]").expect("test modülü yok")];
        let uretim = &soy[..];
        let cagri = "flow::hotspot_kapat(&root);";
        // KP-5 B1: kapanış işinin gövdesi main.rs `pencere_kapanis_isi`te (kabuk yalnız çağırır).
        assert_eq!(main_uretim.matches(cagri).count(), 1, "hotspot kapatma üretimde tam bir kez olmalı");
        assert_eq!(uretim.matches(cagri).count(), 0, "hotspot kapatma kabukta da var (iki kez)");
        let is = &main_uretim[main_uretim.find("fn pencere_kapanis_isi(").expect("kapanış işi yok")..];
        let is = &is[..is.find("\n}").expect("kapanış işi sonu yok")];
        let sira: Vec<usize> = ["backend::safe_stop_coils(port);", "let _ = child.kill();", "clear_port_if_stopped(&root, Some(port));", cagri]
            .iter()
            .map(|p| is.find(p).unwrap_or_else(|| panic!("kapanış işinde {p} yok")))
            .collect();
        assert!(sira.windows(2).all(|w| w[0] < w[1]), "sıra bozuk (STOP → kill → port → hotspot olmalı): {sira:?}");
    }

    /// KP-4 A1 (Y257 c): S sınıfı Tauri kabuğu `kabuk.rs`'te (main.rs onu `include!` ile AYNI modüle katar). Taşınan işlevlere
    /// çapalı kaynak kapıları bu metni okur — main.rs'te ARAMAZLAR (S'nin yeri sayan kapıyla da kilitli).
    fn kabuk_soy() -> String {
        f5_yorumlari_soy(include_str!("kabuk.rs")).replace("\r\n", "\n")
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
        let i = soy.find("fn stop_backend_for_teardown_portla(").expect("teardown fn yok"); // KP-5 B1: gövde `_portla`da
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
        // KP-5 B1: Destroyed işinin gövdesi main.rs `pencere_kapanis_isi` (kabuk yalnız çağırır — davranış testi KRITIK_KP5_B1_pencere_…).
        assert!(kabuk_soy().contains("let job = move || pencere_kapanis_isi(child, port, root, bellek, sinir);"), "Destroyed işi gövdeye bağlı değil");
        let d = soy.find("fn pencere_kapanis_isi(").expect("Destroyed job gövdesi yok");
        let jg = &soy[d..(d + 900).min(soy.len())];
        let de = jg.find("safe_stop_coils(").expect("job E-stop yok");
        let dy = jg.find("son_oturumu_yakala(").expect("job son-yakalama YOK (F5)");
        let dk = jg.find(".kill()").expect("job kill yok");
        assert!(de < dy && dy < dk, "Destroyed job sırası bozuk (E-stop→yakala→kill)");
    }

    /// LN L9 · D2.E01 (WebView2 kolu) · İG-6.20: uygulama penceresinin indirme kararı — kendi kökeni / onun `blob:`'u / `data:` İZİN,
    /// başka http(s) tarayıcıda, başka köken `blob:`'u ve diğer şemalar RED.
    #[test]
    fn KRITIK_L9_indirme_karari_KENDI_KOKEN_izin_DIS_tarayici_DIGER_red() {
        use IndirmeKarari::*;
        for (u, k) in [
            ("blob:http://127.0.0.1:8123/5f1c-aa", Izin),
            ("blob:http://localhost:8123/x", Izin),
            ("data:application/octet-stream;base64,QUJD", Izin),
            ("http://127.0.0.1:8123/api/data/export", Izin),
            ("blob:http://127.0.0.1:9999/x", Reddet),
            ("blob:https://kotu.example/x", Reddet),
            ("https://pemf-vet-web.vercel.app/belge.pdf", TarayicidaAc),
            ("http://127.0.0.1:9999/x", TarayicidaAc),
            ("https://127.0.0.1:8123/x", TarayicidaAc),
            ("file:///C:/Windows/win.ini", Reddet),
            ("bozuk adres", Reddet),
        ] {
            assert_eq!(indirme_karari(u, 8123), k, "{u}");
        }
    }

    /// LN L9: olay işleyicisi — izinli istek `true` (WebView2 indirir), reddedilen `false`, bitiş `true`; dış adres kolu tarayıcı
    /// AÇTIĞI için burada çağrılmaz (yapısal ölçülür); uygulama penceresi kurucusu işleyiciyi KAYDEDER (eskiden `on_download` yoktu).
    #[test]
    fn KRITIK_L9_indirme_olayi_ve_PENCERE_kaydi() {
        let mut hedef = std::path::PathBuf::from(r"C:\Users\x\Downloads\a.pemfbak");
        let izinli = tauri::webview::DownloadEvent::Requested { url: "blob:http://127.0.0.1:8123/u".parse().unwrap(), destination: &mut hedef };
        assert!(indirme_olayi(izinli, 8123), "uygulamanın kendi blob indirmesi reddedildi");
        let red = tauri::webview::DownloadEvent::Requested { url: "file:///C:/x".parse().unwrap(), destination: &mut hedef };
        assert!(!indirme_olayi(red, 8123), "file: indirmesine izin verildi");
        let bitti = tauri::webview::DownloadEvent::Finished { url: "blob:http://127.0.0.1:8123/u".parse().unwrap(), path: None, success: false };
        assert!(indirme_olayi(bitti, 8123));
        let soy = kabuk_soy(); // KP-4 A1: çapa S kabuğunda (kabuk.rs)
        let ow = &soy[soy.find("fn open_app_window(").expect("open_app_window yok")..];
        let ow = &ow[..ow.find("\nfn ").expect("sonraki fn yok")];
        assert!(ow.contains(".on_download(move |_webview, olay| indirme_olayi(olay, port))"), "pencere indirme işleyicisini kaydetmiyor");
        // KP-5 B3: kabuk kararı `indirme_olayi_karari`na bırakır ve dış adres için GERÇEK tarayıcıyı bağlar; karar aşağıda DAVRANIŞLA.
        let io = &soy[soy.find("fn indirme_olayi(").expect("indirme_olayi yok")..];
        let io = &io[..io.find("\n}").expect("indirme_olayi sonu yok")];
        assert!(
            io.contains("indirme_olayi_karari(ozet, port, |u| {") && io.contains("backend::open_browser(u);"),
            "dış adres tarayıcıda açılmıyor (kabuk kararı / tarayıcıyı bağlamıyor)"
        );
    }

    /// KP-5 B3 (sahip kararı 2b): `on_download` KARARI davranışla — dış http(s) adresi `ac` ile TARAYICIDA açılır ve WebView2 İNDİRMEZ;
    /// kendi kökeni indirilir, reddedilen ve izinli adres tarayıcıya GİTMEZ; bitiş `true`.
    #[test]
    fn KRITIK_KP5_B3_indirme_olayi_karari_DIS_adres_TARAYICIDA_acilir_digerleri_acilmaz() {
        let acilan = std::cell::RefCell::new(Vec::<String>::new());
        let kaydet = |u: &str| acilan.borrow_mut().push(u.to_string());
        let dis: tauri::Url = "https://pemf-vet-web.vercel.app/belge.pdf".parse().unwrap();
        assert!(!indirme_olayi_karari(IndirmeOlayi::Istek(&dis), 8123, kaydet), "dış adres WebView2'de indirildi");
        assert_eq!(*acilan.borrow(), vec!["https://pemf-vet-web.vercel.app/belge.pdf".to_string()], "dış adres tarayıcıda açılmadı");
        let kendi: tauri::Url = "blob:http://127.0.0.1:8123/u".parse().unwrap();
        let red: tauri::Url = "file:///C:/x".parse().unwrap();
        assert!(indirme_olayi_karari(IndirmeOlayi::Istek(&kendi), 8123, |u: &str| acilan.borrow_mut().push(u.to_string())));
        assert!(!indirme_olayi_karari(IndirmeOlayi::Istek(&red), 8123, |u: &str| acilan.borrow_mut().push(u.to_string())));
        assert!(indirme_olayi_karari(IndirmeOlayi::Bitti(false), 8123, |u: &str| acilan.borrow_mut().push(u.to_string())));
        assert_eq!(acilan.borrow().len(), 1, "izinli / reddedilen / bitiş tarayıcı açtı");
    }

    /// LN L6 · İG-8.27: orphan söküm dalı STOP hedeflerini `orphan_durdurma_hedefleri`'nden (port dosyası + varsayılan porttaki
    /// kimlikli backend) alır, her hedefe STOP kill'den ÖNCE; eski tek-dosya okuması (dosya yokken STOP'suz kill) kalmadı.
    #[test]
    fn KRITIK_L6_IG827_orphan_dali_varsayilan_porttaki_backendi_de_DURDURUR() {
        let soy = f5_yorumlari_soy(include_str!("main.rs")).replace("\r\n", "\n");
        let i = soy.find("fn stop_backend_for_teardown_portla(").expect("teardown fn yok"); // KP-5 B1: gövde `_portla`da
        let g = &soy[i..];
        let o = g.find("if !had_tracked").expect("orphan dalı yok");
        let ob = &g[o..g.find("backend::kill_stray_backends(root)").expect("kill_stray yok")];
        let dongu = ob
            .find("for port in backend::orphan_durdurma_hedefleri(root, varsayilan_port) {")
            .expect("orphan dalı varsayılan porttaki backend'i hedeflemiyor (İG-8.27)");
        assert!(ob[dongu..].find("backend::safe_stop_coils(port);").is_some(), "hedeflere STOP yok");
        assert!(!ob.contains("read_to_string(root.join(\"backend.port\"))"), "eski tek-dosya okuması duruyor");
        // KP-5 B1: üretim girişi gerçek varsayılan portu verir (davranış: KRITIK_KP5_B1_orphan_…).
        assert!(soy.contains("    stop_backend_for_teardown_portla(tracked, root, bellek, install::DEFAULT_PORT)\n}"), "üretim girişi DEFAULT_PORT vermiyor");
    }

    /// LN L3 · Y82 (sahip): kapanışta sıra STOP → yakmanın bitmesini BEKLE → son oturum yakalama → kill (tracked teardown, orphan dalı
    /// ve pencere Destroyed işi). STOP beklemeye BAĞLI değil: bekleme her yerde `safe_stop_coils`'tan SONRA. Yorum-soyulmuş ölçülür.
    #[test]
    fn KRITIK_L3_kapanis_STOP_sonra_YAKMA_BEKLENIR_sonra_kill() {
        let soy = f5_yorumlari_soy(include_str!("main.rs")).replace("\r\n", "\n");
        let i = soy.find("fn stop_backend_for_teardown_portla(").expect("teardown fn yok"); // KP-5 B1: gövde `_portla`da
        let son = soy[i..].find("\nfn ").map(|j| i + j).unwrap_or(soy.len());
        let g = &soy[i..son];
        let estop = g.find("safe_stop_coils(").expect("teardown E-stop yok");
        let bekle = g.find("yakma_bitene_kadar_bekle(").expect("teardown yakma beklemesi YOK (Y82)");
        let yakala = g.find("son_oturumu_yakala(").expect("son yakalama yok");
        let kill = g.find(".kill()").expect("kill yok");
        assert!(estop < bekle && bekle < yakala && yakala < kill, "teardown sırası STOP → bekle → yakala → kill değil");
        let o = g.find("if !had_tracked").expect("orphan dalı yok");
        let ob = &g[o..g.find("backend::kill_stray_backends(root)").expect("kill_stray yok")];
        let (oe, obk) = (ob.find("safe_stop_coils(").expect("orphan STOP yok"), ob.find("yakma_bitene_kadar_bekle(").expect("orphan bekleme yok"));
        assert!(oe < obk, "orphan dalında bekleme STOP'tan ÖNCE");
        // KP-5 B1: Destroyed işinin gövdesi main.rs `pencere_kapanis_isi` (kabuk yalnız çağırır).
        let d = soy.find("fn pencere_kapanis_isi(").expect("Destroyed job gövdesi yok");
        let jg = &soy[d..(d + 1000).min(soy.len())];
        let (je, jb, jy, jk) = (
            jg.find("safe_stop_coils(").expect("job STOP yok"),
            jg.find("yakma_bitene_kadar_bekle(").expect("job yakma beklemesi YOK (Y82)"),
            jg.find("son_oturumu_yakala(").expect("job yakalama yok"),
            jg.find(".kill()").expect("job kill yok"),
        );
        assert!(je < jb && jb < jy && jy < jk, "Destroyed job sırası STOP → bekle → yakala → kill değil");
    }

    /// LN L3 · Y82: ANA pencere kapanırken (süreç çıkacak) tracked backend yakıyorsa kapanış ertelenir, kullanıcı uyarılır, bekleme
    /// bitince pencere kendisi kapanır. Arayüz olayı dinler ve iki dilli notu gösterir.
    #[test]
    fn KRITIK_L3_ana_pencere_kapanisi_yakmada_ERTELENIR_ve_UYARIR() {
        let soy = kabuk_soy(); // KP-4 A1: çapa S kabuğunda (kabuk.rs)
        let bas = soy.find(".on_window_event(").expect("pencere olay işleyicisi yok");
        let blok = &soy[bas..bas + soy[bas..].find("if let tauri::WindowEvent::Destroyed = event").expect("Destroyed kolu yok")];
        let kr = blok.find("tauri::WindowEvent::CloseRequested { api, .. }").expect("kapanış isteği işlenmiyor (Y82 uyarısı yok)");
        // Sıralı arama: her parça bir öncekinden SONRA aranır (ilk `prevent_close` "bekleyici zaten çalışıyor" kolundadır).
        let mut i = kr;
        for (parca, neden) in [
            ("window.label() == \"main\"", "yalnız ana pencere değil"),
            ("backend::yakma_suruyor_mu(port", "yakma yoklaması yok"),
            ("api.prevent_close()", "yakma görülünce kapanış ertelenmiyor"),
            ("window.emit(OLAY_KAPANIS_YAKMA_BEKLENIYOR", "arayüz uyarılmıyor"),
            ("std::thread::spawn(", "bekleme pencere iş parçacığında (donma)"),
            ("backend::yakmanin_bitmesini_bekle_sinirla(", "bekleyici yok"), // KI G1: paylaşılan bütçeyle
            ("w.close()", "bekleme sonrası kapanmıyor"),
        ] {
            i += blok[i..].find(parca).unwrap_or_else(|| panic!("kapanış ertelemesi: {neden} ({parca})"));
        }
        let html = include_str!("../ui/index.html");
        assert!(
            html.contains(r#"listen("pemf://kapanis-yakma-bekleniyor", () => notice(t().kapanisYakmaBekleniyor))"#),
            "arayüz yakma uyarısını dinlemiyor / göstermiyor"
        );
        assert_eq!(OLAY_KAPANIS_YAKMA_BEKLENIYOR, "pemf://kapanis-yakma-bekleniyor");
    }

    /// KI G1 (22 A3a G1): yakma sürerken ANA pencere kapanışında İKİ ayrı azami bekleme vardı — `CloseRequested` bekleyicisi
    /// (`YAKMA_BEKLEME_AZAMI`, sonra `w.close()`) ve ardından `Destroyed` işinin STOP sonrası beklemesi (yine azami) → yakma takılırsa
    /// toplam ~1200 sn. Artık ikisi AYNI bütçeyi (`AppState::kapanis_yakma_siniri`, ilk beklemede sabitlenen son an) paylaşır; teardown'da
    /// (onarım / kaldırma) tracked + orphan beklemeleri de TEK bütçe. STOP sırası DEĞİŞMEZ (bekleme her yerde STOP'tan sonra — L3 kapısı).
    /// Yorum-soyulmuş kaynakta ölçülür (pencere olayları Tauri çalışma zamanı ister); bütçenin kendisi çekirdekte sahte saatle.
    #[test]
    fn KRITIK_KI_G1_kapanis_yakma_beklemesi_TEK_BUTCE_kaynak() {
        let soy = f5_yorumlari_soy(include_str!("main.rs")).replace("\r\n", "\n");
        let govde = |imza: &str| -> String {
            let i = soy.find(imza).unwrap_or_else(|| panic!("{imza} yok"));
            let son = soy[i..].find("\nfn ").map(|j| i + j).unwrap_or(soy.len());
            soy[i..son].to_string()
        };
        // (a) kapanış bekleyicisi AppState bütçesiyle ve SINIRLI bekler
        let kabuk = kabuk_soy(); // KP-4 A1: pencere olayları `main` içinde (kabuk.rs); yardımcılar main.rs'te
        let bas = kabuk.find(".on_window_event(").expect("pencere olay işleyicisi yok");
        let dst = bas + kabuk[bas..].find("if let tauri::WindowEvent::Destroyed = event").expect("Destroyed kolu yok");
        let kr: String = kabuk[bas..dst].chars().filter(|c| !c.is_whitespace()).collect(); // çağrı çok satırlı olabilir
        let mut i = 0;
        for (parca, neden) in [
            ("state.kapanis_yakma_siniri.clone()", "bekleyici AppState bütçesini almıyor"),
            ("std::thread::spawn(", "bekleyici iş parçacığı yok"),
            ("backend::yakmanin_bitmesini_bekle_sinirla(port,&sinir,", "bekleyici paylaşılan bütçeyle beklemiyor"),
        ] {
            i += kr[i..].find(parca).unwrap_or_else(|| panic!("KI G1 bekleyici: {neden} ({parca})"));
        }
        assert!(!kr.contains("backend::yakmanin_bitmesini_bekle("), "bekleyicide kendi azamisiyle (bütçesiz) bekleme kaldı");
        // (b) Destroyed işi: ana pencerede AYNI bütçe, bekleme STOP'tan sonra
        let ds = &kabuk[dst..];
        let job = ds.find("let job = move || pencere_kapanis_isi(").expect("Destroyed job yok"); // KP-5 B1
        assert!(
            ds[..job].contains("let sinir = kapanis_yakma_siniri(&state, is_main);"),
            "Destroyed işi bekleyicinin bütçesini almıyor (ikinci azami bekleme)"
        );
        let pk = soy.find("fn pencere_kapanis_isi(").expect("Destroyed job gövdesi yok"); // KP-5 B1: gövde main.rs'te
        let jg = &soy[pk..];
        let (st, bk) = (
            jg.find("backend::safe_stop_coils(port);").expect("job STOP yok"),
            jg.find("yakma_bitene_kadar_bekle(port, &sinir);").expect("job paylaşılan bütçeyle beklemiyor"),
        );
        assert!(st < bk, "job'da bekleme STOP'tan ÖNCE");
        // (c) bekleme yardımcısı bütçeyi kullanır; (d) teardown TEK bütçe
        let yb = govde("fn yakma_bitene_kadar_bekle(port: u16, sinir: &backend::YakmaBeklemeSiniri)");
        assert!(yb.contains("backend::yakmanin_bitmesini_bekle_sinirla(port, sinir,") && !yb.contains("backend::yakmanin_bitmesini_bekle("));
        let td = govde("fn stop_backend_for_teardown_portla("); // KP-5 B1
        assert_eq!(td.matches("backend::YakmaBeklemeSiniri::default()").count(), 1, "teardown'da tek bütçe değil");
        assert!(td.find("backend::YakmaBeklemeSiniri::default()") < td.find("let had_tracked"));
        assert_eq!(td.matches("yakma_bitene_kadar_bekle(").count(), td.matches("yakma_bitene_kadar_bekle(port, &sinir)").count());
        assert_eq!(td.matches("yakma_bitene_kadar_bekle(port, &sinir)").count(), 2, "tracked + orphan iki bekleme bekleniyor");
    }

    /// KI G1 · davranış (sahte anlar): bekleyici (`CloseRequested`) AppState bütçesini t0'da sabitler; ANA pencerenin `Destroyed` işi
    /// AYNI son anı görür (azamiden sonra kalan 0 — ikinci bekleme yok); "app" penceresinin işi kendi taze bütçesiyle (süreç yaşar).
    #[test]
    fn KRITIK_KI_G1_ana_pencere_isi_bekleyiciyle_AYNI_butce_app_penceresi_kendi_butcesi() {
        let st = AppState::default();
        let azami = backend::YAKMA_BEKLEME_AZAMI;
        let t0 = std::time::Instant::now();
        assert_eq!(st.kapanis_yakma_siniri.clone().son_an(t0, azami), t0 + azami, "bekleyici bütçeyi sabitlemedi");
        let ana = kapanis_yakma_siniri(&st, true);
        let t_destroyed = t0 + azami + std::time::Duration::from_secs(3);
        assert_eq!(ana.son_an(t_destroyed, azami), t0 + azami, "ana pencere işi YENİ bütçe açtı — ikinci azami bekleme");
        let app = kapanis_yakma_siniri(&st, false);
        assert_eq!(app.son_an(t_destroyed, azami), t_destroyed + azami, "app penceresi işi ana pencerenin bütçesini tüketti");
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
        // SAHİP KARARI 2026-10-18 (auth_session.bin kaybı): launcher pencerenin SON hesabını izler — eskiden bu iki satır
        // tersini pinliyordu (başka hesap / bellek boşken devralma YOK) ve pencerede yeniden giriş launcher'a geçmiyordu.
        assert!(bellek_rotasyonu_gerekli(Some(&m), &s("baska@k.tr", "r2")), "pencerenin son hesabı uygulanmalı");
        assert!(bellek_rotasyonu_gerekli(None, &s("vet@k.tr", "r2")), "bellek boşken pencere girişi uygulanmalı");
        let eski_baska = auth::Session { access_token: "a".into(), refresh_token: "b1".into(), email: "b@k.tr".into(), expires_at: 50 };
        let m_exp = auth::Session { expires_at: 100, ..m.clone() };
        assert!(bellek_rotasyonu_gerekli(Some(&m_exp), &eski_baska), "[S4-yön] yalnız AYNI hesapta — başka hesap engellenmez");
        let se = |rt: &str, exp: i64| auth::Session { access_token: "a".into(), refresh_token: rt.into(), email: "vet@k.tr".into(), expires_at: exp };
        assert!(bellek_rotasyonu_gerekli(Some(&se("r1", 100)), &se("r2", 200)), "daha YENİ jeton uygulanmalı");
        assert!(!bellek_rotasyonu_gerekli(Some(&se("r1", 200)), &se("r2", 100)), "daha ESKİ jeton (bayat devir ekosu) uygulanMAMALI [S4-yön]");
        assert!(bellek_rotasyonu_gerekli(Some(&se("r1", 0)), &se("r2", 100)), "mevcut expires_at bilinmiyorsa (0) kabul");
        let bellek = Mutex::new(Some(m.clone()));
        assert!(bellek_rotasyonu_uygula(&bellek, &s("vet@k.tr", "r2")));
        assert_eq!(bellek.lock().unwrap().as_ref().unwrap().refresh_token, "r2");
        assert!(!bellek_rotasyonu_uygula(&bellek, &s("vet@k.tr", "r2")), "ikinci kez aynı → false");
    }

    /// 2026-10-18 (sahip kararı, auth_session.bin kaybı): pencerede "Çıkış Yap" → launcher kaydı + belleği temizlenir,
    /// "Beni hatırla" TERCİHİ korunur; zaten temizse ikinci kez yazmaz (60 sn döngüsü günlüğü şişirmesin).
    #[test]
    fn pencere_cikisi_launcher_kaydini_ve_bellegini_temizler_tercihi_korur() {
        let d = std::env::temp_dir().join(format!("pemf_cikis_testi_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        let kok = d.as_path();
        let s = auth::Session { access_token: "a".into(), refresh_token: "r".into(), email: "v@k.tr".into(), expires_at: 0 };
        secret_store::save(kok, &s); // işaretsiz eski kurulum
        let bellek = Mutex::new(Some(s));
        assert!(pencere_cikisini_uygula(kok, &bellek), "pencere cikisi uygulanmadi");
        assert!(secret_store::load(kok).is_none(), "launcher kaydi silinmedi");
        assert!(bellek.lock().unwrap().is_none(), "launcher bellegi temizlenmedi");
        assert!(secret_store::hatirla_isareti_path(kok).exists(), "'Beni hatirla' tercihi kayboldu");
        let gunluk = std::fs::read_to_string(secret_store::oturum_gunlugu_path(kok)).unwrap();
        assert!(gunluk.contains("pencerede cikis"), "{gunluk}");
        assert!(!pencere_cikisini_uygula(kok, &bellek), "temizken yine yazdi (gunluk sisirir)");
        assert_eq!(std::fs::read_to_string(secret_store::oturum_gunlugu_path(kok)).unwrap().lines().count(), 1);
        let _ = std::fs::remove_dir_all(&d);
    }

    /// Çıkış işareti üç çekme yolunda da ele alınır (60 sn döngüsü, kapanış son-yakalaması, sahiplenme). MUTASYON: biri
    /// `Cikis` kolunu kaybederse kırmızı.
    #[test]
    fn cikis_isareti_uc_cekme_yolunda_da_uygulanir() {
        let soy = f5_yorumlari_soy(include_str!("main.rs"));
        for (bas, ad) in [
            ("fn oturum_rotasyon_senkronu_baslat", "60 sn döngüsü"),
            ("fn son_oturumu_yakala", "kapanış son-yakalaması"),
            ("if let Some(port) = backend::detect_running_backend(&root) {", "sahiplenme"),
        ] {
            let i = soy.find(bas).unwrap_or_else(|| panic!("{ad} yok"));
            let son = soy[i + 1..].find("\nfn ").map(|j| i + 1 + j).unwrap_or(soy.len());
            let b = &soy[i..son];
            assert!(
                b.contains("DevirCekme::Cikis") && b.contains("pencere_cikisini_uygula("),
                "{ad}: pencere cikisi ele alinmiyor"
            );
        }
    }

    /// 2026-10-18: giriş ekranındaki "Beni hatırla" kararı tercih işaretine yazılır (pencere çıkışından sonra sonraki girişin
    /// hatırlanıp hatırlanmayacağını bu belirler). MUTASYON: `auth_login` işareti yazmazsa kırmızı.
    #[test]
    fn giris_beni_hatirla_kararini_tercih_isaretine_yazar() {
        let soy = f5_yorumlari_soy(include_str!("main.rs"));
        let i = soy.find("async fn auth_login(").expect("auth_login yok");
        let son = soy[i + 1..].find("\nasync fn ").map(|j| i + 1 + j).unwrap_or(soy.len());
        // KP-5 B4: yazım `giris_kaydini_isle`de (davranış testi: KRITIK_KP5_B4_giris_kaydi_…); auth_login ona bağlanır.
        assert!(soy[i..son].contains("giris_kaydini_isle(&root, &s2, hatirla)"), "giris tercihi isarete yazilmiyor (auth_login baglanmiyor)");
        let g = &soy[soy.find("fn giris_kaydini_isle(").expect("giris_kaydini_isle yok")..];
        assert!(g[..g.find("\n}").unwrap()].contains("secret_store::hatirla_tercihini_yaz(root, hatirla)"), "giris tercihi isarete yazilmiyor");
    }

    /// Y211 · S-D67.15: `auth_login` hatası arayüze `{kod, mesaj}` gider ve kod `AuthError::kod`dan gelir — `doLogin`'in kimlik hatasında
    /// şifre alanını temizlemesi / çevrimdışı çıkış yolu bu koda bakar (auth.rs `KRITIK_Y211_doLogin_KODA_bakar_METNE_bakmaz`). Kod
    /// sabitlenir ya da metin gönderilirse (eski `err.to_string()` sözleşmesi) arayüz davranışı sessizce kaybolur. Yorumlar soyulur.
    #[test]
    fn KRITIK_Y211_auth_login_hatasi_KOD_ve_MESAJ_tasir() {
        let soy = f5_yorumlari_soy(include_str!("main.rs"));
        let i = soy.find("async fn auth_login(").expect("auth_login yok");
        let son = soy[i + 1..].find("\nasync fn ").map(|j| i + 1 + j).unwrap_or(soy.len());
        let g: String = soy[i..son].chars().filter(|c| !c.is_whitespace()).collect();
        assert!(g.contains("->Result<AuthStatus,GirisHatasi>"), "auth_login hata tipi kodlu degil");
        assert!(g.contains("GirisHatasi{kod:err.kod(),mesaj:err.to_string()}"), "AuthError kodu arayuze gitmiyor");
        assert!(!g.contains(".map_err(|err|err.to_string())"), "kodsuz (yalniz metin) hata donuyor");
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
        // 2026-10-18: çekme `devir_cek_kisa` (üç durumlu: oturum / ÇIKIŞ / yok); sözleşme aynı — devirden ÖNCE çek.
        let cek = blok.find("devir_cek_kisa(").expect("sahiplenmede ÖNCE çekme yok (S4)");
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
        // KP-5 B3: karar `indirme_adresi_denetle`de (kabuk yalnız tarayıcıyı açar) — izinli iki önek GEÇER (tarayıcı açılmadan ölçülür).
        assert!(indirme_adresi_denetle("https://pemf-vet-web.vercel.app/indir").is_ok());
        assert!(indirme_adresi_denetle("https://github.com/mert61-python/pemf-update/releases/download/x/PEMFVetClient-Setup.exe").is_ok());
        assert!(indirme_adresi_denetle(&format!("https://pemf-vet-web.vercel.app/{}", "a".repeat(2100))).is_err(), "2048 sınırı yok");
        assert!(indirme_adresi_denetle("https://pemf-vet-web.vercel.app/a\tb").is_err(), "sekme geçti");
        let k = kabuk_soy();
        let ou = &k[k.find("fn open_url(").expect("open_url yok")..];
        let ou = &ou[..ou.find("\n}").expect("open_url sonu yok")];
        let (d, a) = (ou.find("indirme_adresi_denetle(&url)?;").expect("open_url denetlemeden açıyor"), ou.find("backend::open_browser(&url)").expect("tarayıcı yok"));
        assert!(d < a, "open_url tarayıcıyı denetimden ÖNCE açıyor");
        // İZİNLİ öneki (daraltılmış repo) GEÇİP metakarakter dalına takılan URL'ler → reddet.
        // (Böylece main.rs:100 prefix'i DEĞİL, metakarakter/kontrol reddi de test edilir.)
        assert!(indirme_adresi_denetle("https://github.com/mert61-python/pemf-update/x&\\\\evil\\evil.exe").is_err());
        assert!(indirme_adresi_denetle("https://github.com/mert61-python/pemf-update/a|calc").is_err());
        assert!(indirme_adresi_denetle("https://github.com/mert61-python/pemf-update/a b").is_err());
        // izin verilmeyen repo (daraltılmış önek dışı) → prefix'te reddet
        assert!(indirme_adresi_denetle("https://github.com/x&\\\\evil\\share\\evil.exe").is_err());
        assert!(indirme_adresi_denetle("https://github.com/a|calc").is_err());
        assert!(indirme_adresi_denetle("https://github.com/a^b").is_err());
        // izinsiz şema/host
        assert!(indirme_adresi_denetle("http://evil.com/").is_err());
        assert!(indirme_adresi_denetle("https://github.com.evil/x").is_err());
        // boşluk / kontrol karakteri
        assert!(indirme_adresi_denetle("https://github.com/a b").is_err());
        assert!(indirme_adresi_denetle("https://github.com/a\nb").is_err());
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
        assert!(s.contains("System32\\tasklist.exe") && s.contains("System32\\findstr.exe"), "araçlar tam yolla");
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

    /// 🔴 SAHA ARIZASI 2026-09-05 — YARDIMCI BATCH HİÇ KOŞMUYORDU (yapısal kapı).
    ///
    /// `DETACHED_PROCESS`li `cmd.exe` konsolsuzdur ve İLK BORU satırında ölür. 1.9.45'te bekleme
    /// döngüsüne `tasklist … | find …` eklenince batch'in ilk çalışan satırı bir boru oldu →
    /// kurulum hiç koşmadı. Metin ölçen mevcut test bunu YAKALAYAMADI (doğru araç adlarını
    /// içeriyordu, sadece çalışmıyordu). Borular geri gelirse burası kırmızı yanar.
    #[cfg(windows)]
    #[test]
    fn betik_BORU_icermez() {
        let s = build_relaunch_script(r"C:\a.exe", r"C:\b.exe", 4242, Some(r"C:\c.exe")).unwrap();
        assert!(
            !s.contains('|'),
            "yeniden-başlatma batch'i BORU içeriyor — konsolsuz cmd ilk boruda ölür, kurulum hiç koşmaz:\n{s}"
        );
        let u = build_uninstall_script(r"C:\u.exe").unwrap();
        assert!(!u.contains('|'), "kaldırma batch'i BORU içeriyor (aynı tuzak)");
    }

    /// Kök neden kapısı: yardımcı batch'in bayrakları `DETACHED_PROCESS` TAŞIMAMALI, ama
    /// `CREATE_NO_WINDOW` taşımalı (siyah-konsol kapısı + boru çalışsın).
    #[cfg(windows)]
    #[test]
    fn yardimci_bayraklari_DETACHED_tasimaz() {
        const DETACHED_PROCESS: u32 = 0x0000_0008;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        assert_eq!(
            YARDIMCI_BATCH_BAYRAKLARI & DETACHED_PROCESS,
            0,
            "DETACHED_PROCESS geri gelmiş: cmd konsolsuz kalır ve batch boruda ölür"
        );
        assert_ne!(
            YARDIMCI_BATCH_BAYRAKLARI & CREATE_NO_WINDOW,
            0,
            "CREATE_NO_WINDOW düşmüş: kullanıcıya siyah konsol penceresi görünür"
        );
    }

    /// 🔴 DAVRANIŞSAL KAPI: üretilen batch, ÜRETİMDEKİ bayraklarla başlatıldığında SONA KADAR
    /// koşuyor mu? Metin denetimi bu arızayı kaçırdı; burada batch GERÇEKTEN çalıştırılır.
    ///
    /// Kurulum yerine işaret bırakan bir .bat konur; "yeni exe" de öyle. Sonda üç şey ölçülür:
    /// kurulum adımı koştu, uygulama başlatıldı, batch kendini sildi (yani sona vardı).
    #[cfg(windows)]
    #[test]
    fn yardimci_batch_uretimdeki_bayraklarla_SONA_KADAR_kosar() {
        let tmp = std::env::temp_dir();
        let pid: u32 = 999_123; // var olmayan PID → bekleme döngüsü hemen geçer
        let uyg_iz = tmp.join("pemf_kapi_uygulama.txt");
        let pencere = tmp.join("pemf_kapi_pencere.tmp");
        // ⚠️ SAHTE KURULUM GERÇEK BİR .exe OLMALI. Batch içinden `.bat` çağırmak `call`sız
        // kontrolü DEVREDER ve GERİ DÖNMEZ — ilk denemede tam bu oldu ve bu kapı yakaladı.
        // Üretimde kurulum daima .exe'dir; burada dönüş yapan zararsız bir sistem exe'si kullanılır
        // ("/S" onun için geçersiz argüman → hemen çıkar). Adımın koştuğu GÜNLÜKTEN doğrulanır.
        let sahte_kur = std::path::PathBuf::from(r"C:\Windows\System32\findstr.exe");
        // ⚠️ 2026-10-18 (sahip oyundayken bu test GÖRÜNÜR bir `cmd /K` penceresi açıp odağı çaldı — "KOMUT İSTEMLERİNİ SESSİZ
        // ARKA PLANDA AÇ"): batch'teki `start "" "<uyg>"` bir `.bat` için YENİ ve GÖRÜNÜR konsol açar; test dosyayı erken silince
        // pencere "The batch file cannot be found." ile açık kalıyordu. Üretimde hedef PENCERELİ `PEMFVetClient.exe`'dir (konsol yok).
        // Sahte uygulama artık penceresiz Windows Script Host betiği: `.vbs` → wscript (GUI alt sistemi), `start` onu ShellExecute ile
        // KONSOLSUZ açar; `On Error Resume Next` → hata olsa bile diyalog (odak çalan) çıkmaz.
        let sahte_uyg = tmp.join("pemf_kapi_uyg.vbs");
        let betik = tmp.join("pemf_kapi_relaunch.bat");
        let gunluk = tmp.join(format!("pemf_selfupdate_{pid}.log"));
        for p in [&uyg_iz, &gunluk] {
            let _ = std::fs::remove_file(p);
        }
        // Bulgu #6: Rust tarafı aynı günlüğe pencere sonucunu ÖNCE yazar; batch `>>` ile eklemeli.
        // `>`'a dönülürse bu satır kaybolur → aşağıdaki assert kırmızı yanar.
        std::fs::write(&gunluk, pencere_gunluk_satiri(&Err("kapi-onsatir".to_string()))).unwrap();
        // (Eski `.bat` sahtesinde sağ kalan `cmd /K` devraldığı stdout borusunu tutup cargo'yu ASIYORDU — `.vbs` konsol ve boru
        // devralmaz.)
        std::fs::write(
            &sahte_uyg,
            format!(
                "On Error Resume Next\r\nSet f = CreateObject(\"Scripting.FileSystemObject\").CreateTextFile(\"{}\", True)\r\n\
                 f.WriteLine \"acildi\"\r\nf.Close\r\n",
                uyg_iz.display()
            ),
        )
        .unwrap();
        std::fs::write(&pencere, b"x").unwrap();

        let s = build_relaunch_script(
            sahte_kur.to_str().unwrap(),
            sahte_uyg.to_str().unwrap(),
            pid,
            pencere.to_str(),
        )
        .unwrap();
        std::fs::write(&betik, s).unwrap();

        // ÜRETİM yardımcısıyla başlat (satır içi yeniden yazım DEĞİL — bulgu #2: inline spawn kapıyı
        // kör bırakıyordu; yardımcı değişirse test onu ölçmüyordu).
        yardimci_batch_baslat(&betik).expect("yardımcı başlatılamadı");

        let mut bitti = false;
        for _ in 0..120 {
            std::thread::sleep(std::time::Duration::from_millis(500));
            if !betik.exists() {
                bitti = true;
                break;
            }
        }
        // ⚠️ `start` ASENKRONDUR: batch bittiğinde başlatılan süreç henüz yazmamış olabilir.
        // (İlk sürümde burada yarış vardı ve test yanlış-kırmızı yandı.)
        for _ in 0..40 {
            if uyg_iz.exists() {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(250));
        }
        // ⚠️ Batch günlüğü `%DATE%` yazar: Türkçe OEM kod sayfasında gün adı UTF-8 DEĞİLDİR (Çarşamba → "Çar"). `read_to_string` o gün Err
        // döner → boş günlük → bu kapı YANLIŞ-KIRMIZI yanardı (2026-10-21 Çarşamba ölçüldü). Bayt oku, kayıplı çevir.
        let g = String::from_utf8_lossy(&std::fs::read(&gunluk).unwrap_or_default()).into_owned();
        assert!(
            g.contains("kurulum bitti errorlevel="),
            "KURULUM ADIMI HİÇ KOŞMADI/DÖNMEDİ — batch erken öldü (1.9.45 arızası). Günlük:\n{g}"
        );
        assert!(uyg_iz.exists(), "uygulama yeniden başlatılmadı. Günlük:\n{g}");
        assert!(bitti, "batch kendini silmedi (sona varamadı). Günlük:\n{g}");
        assert!(g.contains("yardimci bitti"), "günlük eksik — saha teşhisi yine kör kalır:\n{g}");
        assert!(
            g.contains("[rust] pencere=0 kapi-onsatir"),
            "batch, Rust'ın yazdığı pencere satırını EZDİ (`>>` yerine `>`): pencere teşhisi kaybolur:\n{g}"
        );
        assert!(!pencere.exists(), "bilgilendirme penceresinin kopyası silinmedi");
        for p in [&uyg_iz, &sahte_uyg, &pencere, &gunluk] {
            let _ = std::fs::remove_file(p);
        }
    }

    /// 🔴 DENETİM 2026-09-06 (bulgu #2) — DAVRANIŞSAL: yardımcı batch, %TEMP%'te ÖZEL KARAKTER
    /// olan dizinlerde de koşuyor mu? `cmd /c "<yol>"` biçimi "Vet & Co" ve "Ali^Veli"de batch'i
    /// hiç başlatmıyordu (ölçüldü: rc=1, iz yok, sıfır kanıt). ÜRETİM yardımcısı çağrılır; satır
    /// içi spawn yazmak kapıyı kör bırakır.
    #[cfg(windows)]
    #[test]
    fn yardimci_batch_metakarakterli_TEMP_yolunda_da_kosar() {
        let kok = std::env::temp_dir().join("pemf_kapi_meta");
        let _ = std::fs::remove_dir_all(&kok);
        let mut hatalar = Vec::new();
        for ad in ["duz bosluk", "Vet & Co", "Ali^Veli", "Ahmet (Klinik)", "a@b!c"] {
            let d = kok.join(ad);
            std::fs::create_dir_all(&d).unwrap();
            let iz = d.join("iz.txt");
            let bat = d.join("t.bat");
            // Yardımcının erken-ölüm kapısı 300 ms bakar; batch ≥1 sn yaşasın (ping-uyku, üretimdeki gibi).
            std::fs::write(
                &bat,
                format!("@echo off\r\nping -n 2 127.0.0.1 >nul\r\necho kostu > \"{}\"\r\n", iz.display()),
            )
            .unwrap();
            match yardimci_batch_baslat(&bat) {
                Err(e) => hatalar.push(format!("{ad}: yardımcı Err döndü: {e}")),
                Ok(mut cocuk) => {
                    let _ = cocuk.wait();
                    std::thread::sleep(std::time::Duration::from_millis(200));
                    if !iz.exists() {
                        hatalar.push(format!("{ad}: batch KOŞMADI (iz dosyası yok) — cmd yolu böldü"));
                    }
                }
            }
        }
        let _ = std::fs::remove_dir_all(&kok);
        assert!(hatalar.is_empty(), "yardımcı batch şu dizinlerde çalışmıyor:\n  {}", hatalar.join("\n  "));
    }

    /// Bulgu #2 — erken-ölüm kapısı: cmd komut satırını ayrıştıramayıp hemen rc≠0 ile çıkarsa
    /// yardımcı SESSİZ kalmaz, Err döndürür (çağıran işareti temizler + kullanıcıya söyler).
    /// Var olmayan .bat → cmd hemen "The system cannot find..." + rc=1.
    #[cfg(windows)]
    #[test]
    fn yardimci_batch_hemen_olurse_HATA_doner() {
        let yok = std::env::temp_dir().join("pemf_kapi_yok_bu_dosya_12345.bat");
        let _ = std::fs::remove_file(&yok);
        let r = yardimci_batch_baslat(&yok);
        assert!(r.is_err(), "var olmayan batch için Ok döndü — erken ölüm sessiz kaldı");
        let m = r.err().unwrap();
        assert!(m.contains("hemen sonlandı") && m.contains("çıkış kodu"), "hata mesajı sebebi söylemiyor: {m}");
    }

    /// KP-5 B3 (sahip kararı 2b): yardımcı batch yolu denetimi ve erken-ölüm iletisi saf — `"` / CR / LF / UTF-8 olmayan yol reddedilir,
    /// düz yol AYNEN döner; ileti kodu (yoksa "yok") ve yolu söyler. Kabuk ikisini de kullanır (yapısal).
    #[cfg(windows)]
    #[test]
    fn KRITIK_KP5_B3_yardimci_batch_yolu_ve_erken_olum_iletisi() {
        use std::os::windows::ffi::OsStringExt;
        let duz = std::path::Path::new(r"C:\Users\x\Temp\Vet & Co\t.bat");
        assert_eq!(yardimci_batch_yolu(duz).unwrap(), r"C:\Users\x\Temp\Vet & Co\t.bat");
        let guvensiz = pemf_launcher_core::dil::t("rust.hata.yardimciBatchYoluGuvensiz");
        for kotu in ["C:\\a\"b.bat", "C:\\a\rb.bat", "C:\\a\nb.bat"] {
            assert_eq!(yardimci_batch_yolu(std::path::Path::new(kotu)).unwrap_err(), guvensiz, "{kotu:?} kabul edildi");
        }
        let utf8_degil = std::path::PathBuf::from(std::ffi::OsString::from_wide(&[0x43, 0x3a, 0x5c, 0xD800]));
        assert_eq!(yardimci_batch_yolu(&utf8_degil).unwrap_err(), pemf_launcher_core::dil::t("rust.hata.yardimciBatchYoluUtf8"));
        let i1 = yardimci_hemen_sonlandi_iletisi(Some(1), duz);
        assert!(i1.contains("hemen sonlandı") && i1.contains("çıkış kodu") && i1.contains('1') && i1.contains("t.bat"), "{i1}");
        let i2 = yardimci_hemen_sonlandi_iletisi(None, duz);
        assert!(i2.contains(&pemf_launcher_core::dil::t("rust.hata.yok")), "{i2}");
        let k = kabuk_soy();
        let yb = &k[k.find("fn yardimci_batch_baslat(").expect("yardimci_batch_baslat yok")..];
        let yb = &yb[..yb.find("\n}").expect("sonu yok")];
        assert!(yb.contains("yardimci_batch_yolu(bat)?") && yb.contains("yardimci_hemen_sonlandi_iletisi(durum.code(), bat)"), "kabuk saf yardımcıları kullanmıyor");
    }

    /// Bulgu #2 — kaynak-parite: iki spawn noktası da ORTAK yardımcıyı kullanmalı; `.arg("/c")`
    /// geri gelirse tırnak-soyma tuzağı geri gelir.
    #[cfg(windows)]
    #[test]
    fn spawn_yollari_ortak_yardimciyi_kullanir() {
        // KP-5 B3 (kör çapa): iki işlev KP-4 A1'de kabuk.rs'e taşındı; main.rs'te aramak bu testin KENDİ dizgesini buluyordu (boşuna yeşil).
        let kaynak = kabuk_soy();
        for fn_adi in ["fn spawn_update_relauncher(", "fn spawn_uninstaller_detached("] {
            let i = kaynak.find(fn_adi).unwrap_or_else(|| panic!("{fn_adi} yok"));
            let govde = &kaynak[i..i + 1400];
            assert!(govde.contains("yardimci_batch_baslat("), "{fn_adi} ortak yardımcıyı çağırmıyor");
            assert!(!govde.contains(".arg(\"/c\")"), "{fn_adi} yeniden `.arg(\"/c\")` kullanıyor — tırnak-soyma tuzağı geri geldi");
        }
    }

    /// 🔴 DENETİM 2026-09-06 (bulgu #3): klasör seçicinin boş çıktısı ancak PowerShell BAŞARILIYSA
    /// "iptal"dir; PS düştüyse (CLM/WDAC, Add-Type yasak) operatörün İptal'inden ayırt edilmeli.
    #[test]
    fn klasor_secici_sonucu_tablosu() {
        // (başarılı, kod, stdout, stderr) → beklenen
        assert_eq!(klasor_secici_sonucu(true, Some(0), b"", b""), Ok(None), "temiz iptal korunmalı");
        assert_eq!(
            klasor_secici_sonucu(true, Some(0), b"D:\\Yedek\r\n", b""),
            Ok(Some("D:\\Yedek".to_string())),
            "yol trim'lenmeli"
        );
        let clm = klasor_secici_sonucu(
            false,
            Some(1),
            b"",
            b"Add-Type: Cannot invoke method. Method invocation is supported only on core types in this language mode. ConstrainedLanguage",
        );
        let m = clm.expect_err("PowerShell düştü ama Ok döndü — İptal'den ayırt edilemez");
        assert!(m.contains("çıkış kodu 1") && m.contains("ConstrainedLanguage"), "hata sebebi taşımıyor: {m}");
        assert!(m.contains("BT yöneticinize"), "hata ne yapılacağını söylemiyor: {m}");
        // başarı kodu ama stdout boş + stderr dolu → yine hata (gerçek iptalde stderr boştur)
        assert!(klasor_secici_sonucu(true, Some(0), b"", b"WinForms yuklenemedi").is_err());
        // kod bilinmiyorsa (sinyalle öldü) mesaj "yok" der, panik etmez
        assert!(klasor_secici_sonucu(false, None, b"", b"").expect_err("başarısız").contains("çıkış kodu yok"));
    }

    /// Bulgu #6: pencere sonucu günlük satırı — iki dal da yazılır, sebep taşınır.
    #[test]
    fn pencere_gunluk_satiri_iki_dal() {
        let ok = pencere_gunluk_satiri(&Ok(std::path::PathBuf::from(r"C:\T\x.exe")));
        assert!(ok.starts_with("[rust] pencere=1 ") && ok.contains("x.exe") && ok.ends_with("\r\n"));
        let err = pencere_gunluk_satiri(&Err("kopyalanamadı (C:\\T): erişim engellendi".to_string()));
        assert!(err.starts_with("[rust] pencere=0 ") && err.contains("erişim engellendi"), "{err}");
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
        // 401 "Invalid API key" gibi iptal OLMAYAN red artık `Server(401)` → kayıt korunur (auth::yenileme_hatasi).
        assert_eq!(oturum_karari(&Err(auth::AuthError::Server(401))), OturumKarari::CevrimdisiDevam);
    }

    /// 🔴 SAHA (2026-10-17): "Beni hatırla" kaydı sessizce silindi, nedeni hiçbir yerde yoktu. Silmede HER ZAMAN,
    /// korumada sunucu yanıt verdiyse günlüğe satır; satır yalnız durum + kod taşır.
    #[test]
    fn acilis_yenilemesi_silme_ve_koruma_NEDENI_gunluge() {
        let s = oturum_gunlugu_olayi(&OturumKarari::Sil, Some("HTTP 400 refresh_token_not_found")).unwrap();
        assert!(s.contains("SILINDI") && s.contains("HTTP 400 refresh_token_not_found"), "{s}");
        assert!(oturum_gunlugu_olayi(&OturumKarari::Sil, None).unwrap().contains("SILINDI"), "neden yokken satir yazilmadi");
        let k = oturum_gunlugu_olayi(&OturumKarari::CevrimdisiDevam, Some("HTTP 401")).unwrap();
        assert!(k.contains("KORUNDU") && k.contains("HTTP 401"), "{k}");
        assert_eq!(oturum_gunlugu_olayi(&OturumKarari::CevrimdisiDevam, None), None, "ag yokken gunluk sisiyor");
        assert_eq!(oturum_gunlugu_olayi(&OturumKarari::Yenilendi, Some("x")), None);
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

    /// Dinleyeni OLMAYAN loopback port — kapı testlerinde VARSAYILAN port yerine enjekte edilir (8000'e istek YOK).
    fn kapali_port() -> u16 {
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let p = ln.local_addr().unwrap().port();
        drop(ln);
        p
    }

    /// `sahte_backend`'in YÜK ALTINDAKİ backend'i: her isteği okur, `gecikme` bekler, sonra yanıtlar (sırayla). Yoklama (2 sn)
    /// düşer, cömert bütçeli istek (`session_active`, 10 sn) yanıtı alır. ⚠️ `join()` YAPMAYIN (bkz. `sahte_backend`).
    fn sahte_yavas_backend(govde: &'static str, gecikme: std::time::Duration, istek_sayisi: usize) -> (u16, std::thread::JoinHandle<()>) {
        use std::io::{Read, Write};
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ln.local_addr().unwrap().port();
        let h = std::thread::spawn(move || {
            for _ in 0..istek_sayisi {
                let Ok((mut c, _)) = ln.accept() else { break };
                let mut buf = [0u8; 2048];
                let _ = c.read(&mut buf);
                std::thread::sleep(gecikme);
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
        (port, h)
    }

    /// LN L6 · İG-8.21 (ÖLÇÜLDÜ — ayrı süreç GERÇEK backend, süreç içi Python yükünde sağlık > 2 sn): 2 sn'lik kimlik yoklamasına
    /// yanıt vermeyen ama TCP kabul eden backend "yok" SAYILMAZ — seans cömert bütçeyle sorulur, seans sürüyorsa güncelleme
    /// ERTELENİR. Önce: yoklama düşer → kapı "backend yok" der → sessiz güncelleme süren tedaviyi keserdi.
    #[test]
    fn KRITIK_L6_yuk_altinda_YANITSIZ_backend_YOK_sayilmaz_seans_sorulur() {
        let (port, h) = sahte_yavas_backend(
            r#"{"service":"PEMF-Vet","status":"ok","sessionActive":true}"#,
            std::time::Duration::from_millis(2600),
            3,
        );
        let d = gecici_kok("yavas", port);
        let r = aktif_seans_kapisi_portla(&d, kapali_port());
        assert_eq!(
            r,
            Err(pemf_launcher_core::dil::t("rust.hata.guncellemeSeansSuruyor")),
            "yük altındaki backend 'yok' sayıldı — güncelleme süren seansı keser"
        );
        drop(h);
        let _ = std::fs::remove_dir_all(&d);
    }

    /// LN L6 KARŞIT: `backend.port` KESİN ölü porta işaret ediyor ve varsayılan port da boş → kapı GEÇER (ilk kurulum / kapalı
    /// backend güncellemeyi kilitlemez) ve hızlıdır (10 sn'lik seans bütçesi beklenmez).
    #[test]
    fn KRITIK_L6_kesin_olu_backend_GECER_hizli() {
        let d = gecici_kok("olu", kapali_port());
        let t0 = std::time::Instant::now();
        assert!(aktif_seans_kapisi_portla(&d, kapali_port()).is_ok(), "kesin ölü backend güncellemeyi engelledi");
        // Windows'ta kapalı loopback porta bağlanma ~2 sn'de düşer (RST sonrası SYN yeniden denemesi; ÖLÇÜLDÜ ~4,5 sn = iki yoklama,
        // HEAD'le aynı). Sınır: 10 sn'lik seans bütçesi BEKLENMEZ.
        assert!(t0.elapsed() < std::time::Duration::from_secs(8), "ölü backend'de kapı seans bütçesini bekledi: {:?}", t0.elapsed());
        let _ = std::fs::remove_dir_all(&d);
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

        let r = aktif_seans_kapisi_portla(&d, kapali_port());
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

        assert!(aktif_seans_kapisi_portla(&d, kapali_port()).is_ok(), "seans yokken guncelleme engellendi");

        drop(h);
        let _ = std::fs::remove_dir_all(&d);
    }

    /// BİLİNMİYOR ≠ "seans yok". Otomatik güncelleme kullanıcı istemeden çalışır; ertelemek bedava,
    /// süren bir tedaviyi kesmek değil.
    ///
    /// ⚠️ Bu testin kurulumu bilinçlidir: backend probe'a sağlıklı cevap verir (yani AYAKTADIR), ama
    /// seans durumu okunabilir bir değer olarak gelmez. (Eskiden TAMAMEN yanıtsız backend bu kapıya
    /// hiç ulaşmıyordu — probe düşer, kapı "backend yok" der geçerdi; LN L6 · İG-8.21 ile kapandı,
    /// bkz. `KRITIK_L6_…`.)
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

        let r = aktif_seans_kapisi_portla(&d, kapali_port());
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

    /// LN L3 · Y82: backend STM32 firmware'i YAKARKEN otomatik güncelleme (self-update / runtime) ERTELENİR — self-update'in NSIS
    /// kancası ve runtime güncellemesi backend'i öldürür, yakma yarıda kalırdı. KARŞIT: yakma yoksa geçer.
    #[test]
    fn KRITIK_L3_yakma_surerken_guncelleme_ERTELENIR() {
        let (port, h) = sahte_backend(r#"{"service":"PEMF-Vet","sessionActive":false,"firmwareGuncelleme":{"yakiliyor":true}}"#, 4);
        let d = gecici_kok("yakma", port);
        let r = aktif_seans_kapisi_portla(&d, kapali_port());
        assert_eq!(r, Err(pemf_launcher_core::dil::t("rust.hata.guncellemeYakmaSuruyor")), "yakma sürerken güncelleme ertelenmedi");
        drop(h);
        let _ = std::fs::remove_dir_all(&d);
        let (port2, h2) = sahte_backend(r#"{"service":"PEMF-Vet","sessionActive":false,"firmwareGuncelleme":{"yakiliyor":false}}"#, 4);
        let d2 = gecici_kok("yakmayok", port2);
        assert!(aktif_seans_kapisi_portla(&d2, kapali_port()).is_ok(), "yakma yokken güncelleme engellendi");
        drop(h2);
        let _ = std::fs::remove_dir_all(&d2);
    }

    /// Backend hiç çalışmıyorsa kapı engel OLMAMALI (ilk kurulum / temiz makine).
    #[test]
    fn backend_yoksa_kapi_engellemez() {
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ln.local_addr().unwrap().port();
        drop(ln);
        let d = gecici_kok("yok", port);

        assert!(aktif_seans_kapisi_portla(&d, kapali_port()).is_ok(), "backend yokken guncelleme engellendi");

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

    /// Profil kaldırma komutu (inceleme 2026-09-06): (1) açık "app" penceresi KAPATILIR — aksi
    /// hâlde SPA eski `?profiles=` listesiyle açık kalır ve kaldırılan profil seçilebilir kalır;
    /// (2) kapatma `stop_tracked_backend`ten SONRA gelir — `state.proc` orada atomik alınıp E-stop →
    /// kill tamamlanır, Destroyed kancası boş bulur (yarış yok); (3) ilerleme YAYINLANMAZ —
    /// `progress_reporter` "extracting"i "Kuruluyor…" diye bastırır, kaldırma sırasında yanıltıcı.
    #[test]
    fn profil_kaldirma_komutu_pencereyi_stop_SONRASI_kapatir_ilerleme_yayinlamaz() {
        let soy = f5_yorumlari_soy(include_str!("main.rs"));
        let i = soy.find("async fn remove_profiles(").expect("remove_profiles komutu yok");
        let son = soy[i..].find("\nfn ").map(|j| i + j).unwrap_or(soy.len());
        let govde = &soy[i..son];
        let stop = govde.find("stop_tracked_backend(").expect("remove_profiles E-stop+kill (stop_tracked_backend) çağırmıyor");
        let pencere = govde
            .find("get_webview_window(\"app\")")
            .expect("remove_profiles açık \"app\" penceresini kapatmıyor — kaldırılan profil arayüzde seçilebilir kalır");
        let kapat = govde[pencere..].find(".close()").expect("\"app\" penceresi bulunuyor ama close() yok");
        assert!(kapat < 200, "get_webview_window(\"app\") ile close() arası kopuk");
        let spawn = govde.find("spawn_blocking(").expect("remove_profiles spawn_blocking yok");
        assert!(stop < pencere, "pencere kapatma stop_tracked_backend'ten ÖNCE — Destroyed kancası ile yarış (E-stop sırası)");
        assert!(pencere < spawn, "pencere kapatma dosya silme başladıktan SONRA — eski profil listesi açık kalır");
        assert!(
            !govde.contains("progress_reporter("),
            "remove_profiles ilerleme yayınlıyor — UI bunu 'Kuruluyor…/Installing…' diye gösterir (yanıltıcı)"
        );
    }

    /// GK (istem 41 A) · GÜNCELLEME ONAYI Y253 / Y254: seans engeli yoklamasının sözleşmesi — kapı açıksa `engel: false`; kapı reddederse
    /// (etkin seans / kart yazılımı yükleme / yanıtsız backend / görev çöktü) `engel: true` + kapının seçili dildeki iletisi (arayüz
    /// bekler ve EKRANDA söyler). Engeli `false`a çeviren bir değişiklik etkin seansta yeniden başlatmanın yolunu açar.
    #[test]
    fn KRITIK_GK_seans_engeli_JSON_kapi_reddinde_ENGEL_VAR() {
        let acik = guncelleme_engeli_json(Ok(()));
        assert_eq!(acik["engel"], serde_json::json!(false), "{acik}");
        let red = guncelleme_engeli_json(Err("SEANS-SURUYOR".to_string()));
        assert_eq!(red["engel"], serde_json::json!(true), "kapı reddi engel sayılmadı: {red}");
        assert_eq!(red["mesaj"], serde_json::json!("SEANS-SURUYOR"), "kapının iletisi arayüze taşınmıyor: {red}");
        let soy = kabuk_soy(); // KP-4 A1: çapa S kabuğunda (kabuk.rs)
        let g = &soy[soy.find(concat!("async fn guncelleme_", "engeli(")).expect("komut yok")..];
        let g = &g[..g.find("\n}\n").expect("gövde sonu")];
        assert!(g.contains("aktif_seans_kapisi(") && g.contains("guncelleme_engeli_json(Err("), "engel TEK kapıdan / fail-safe değil: {g}");
    }

    /// GK · Y253 "oto yeniden başlasın uygulama": katman güncellemesi HAZIR olunca açık uygulama penceresi yeni arayüzü yükler — oturum
    /// devrinden SONRA, `on_backend_ready`den ÖNCE. Kurucu önbelleği: doğrulanmış kurucu varsa yeniden inmez, yoksa (doğrulama
    /// düşerse) İNER — ve her durumda kurulumdan önce yeniden doğrulanır.
    #[test]
    fn KRITIK_GK_hazir_kolu_pencereyi_YENILER_kurucu_onbellegi_dogrulamaya_bagli() {
        let soy = f5_yorumlari_soy(include_str!("main.rs")).replace("\r\n", "\n");
        let k = &soy[soy.find(concat!("GuncellemeSonucu::Hazir(child, url, port) =", "> {")).expect("hazır kolu yok")..];
        let k = &k[..k.find("\n        }").expect("kol sonu")];
        let devir = k.find("hand_off_session(").expect("oturum devri yok");
        let yenile = k.find("uygulama_penceresini_yenile(&app, port)").expect("hazır kolunda pencere yenileme yok");
        let hazir = k.find("on_backend_ready(").expect("on_backend_ready yok");
        assert!(devir < yenile && yenile < hazir, "sıra: oturum devri → pencere yenile → on_backend_ready olmalı");
        let s = &soy[soy.find(concat!("async fn apply_", "self_update(")).expect("apply_self_update yok")..];
        let kosul = s.find("if verify::verify_file(&dest2, &sha).is_err() {").expect("kurucu önbellek koşulu yok");
        let indir = s.find("net::download_to_file(&u, &dest2").expect("indirme yok");
        let dogrula = s.find("on(flow::Progress::Verifying").expect("indirme sonrası doğrulama yok");
        assert!(kosul < indir && indir < dogrula, "kurucu yalnız doğrulama DÜŞERSE inmeli ve her durumda yeniden doğrulanmalı");
    }

    // ==== KP-3 B2 (istem 38 / 41 C): main.rs "T" sınıfı işlevlerin testleri — dosya sonuna (üstteki satırlar KAYMAZ) ====

    /// KP-3 B2 · `ps_b64`: PowerShell `-EncodedCommand` UTF-16LE + base64 kodlaması — Python `base64.b64encode(s.encode("utf-16-le"))` ile
    /// birebir (1 / 2 / 3 karakterlik dolgu kolları + Türkçe / BMP dışı olmayan çok baytlı karakter). Yanlış kodlama yükseltilmiş betiği
    /// sessizce bozar (UAC penceresi açılır ama komut çalışmaz).
    #[test]
    fn kp3_b2_ps_b64_UTF16LE_base64_python_ile_BIREBIR() {
        for (girdi, beklenen) in [
            ("a", "YQA="),
            ("ab", "YQBiAA=="),
            ("abc", "YQBiAGMA"),
            ("Get-Date", "RwBlAHQALQBEAGEAdABlAA=="),
            ("şİ€", "XwEwAawg"),
            // alfabenin son iki karakteri (`+` = 62, `/` = 63) — ilk turda hiçbir vektör üretmiyordu, alfabe mutantı YAŞADI
            ("ûÿ", "+wD/AA=="),
            ("ÿû", "/wD7AA=="),
            ("", ""),
        ] {
            assert_eq!(ps_b64(girdi), beklenen, "girdi {girdi:?}");
        }
    }

    /// KP-3 B2 · `uygulama_url`: çekirdeğin profil URL'si + önbellek kırıcı (`_=<ms>`) — WebView2 eski index.html'i önbellekten
    /// yüklemesin. Kırıcı GERÇEK zaman damgası taşır (iki çağrı arası azalmaz) ve kurulu profiller URL'ye girer.
    #[test]
    fn kp3_b2_uygulama_url_profil_listesi_ve_ZAMAN_DAMGALI_onbellek_kirici() {
        let kurulu = vec!["vet".to_string(), "home".to_string()];
        let taban = flow::uygulama_url(8123, &kurulu);
        let once = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_millis();
        let u = uygulama_url(8123, &kurulu);
        let sonra = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_millis();
        assert!(u.starts_with(&taban), "çekirdek URL'si korunmadı: {u} / {taban}");
        assert!(u.contains("8123") && u.contains("vet") && u.contains("home"), "{u}");
        let ts: u128 = u.rsplit("_=").next().and_then(|x| x.parse().ok()).unwrap_or_else(|| panic!("önbellek kırıcı yok: {u}"));
        assert!(once <= ts && ts <= sonra, "kırıcı gerçek zaman değil: {ts} ∉ [{once}, {sonra}]");
    }

    /// KP-3 B2 · `unix_simdi_s`: saniye cinsinden duvar saati (onay kaydının yaşı buna göre ölçülür — milisaniye ya da 0 dönerse
    /// 7 günlük sınır anlamsızlaşır).
    #[test]
    fn kp3_b2_unix_simdi_s_SANIYE_ve_GERCEK_zaman() {
        let a = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
        let s = unix_simdi_s();
        let b = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
        assert!(a <= s && s <= b, "{s} ∉ [{a}, {b}] (saniye değil ya da sabit)");
    }

    /// KP-3 B2 · `ortam_ozeti`: arayüzün açılış ekranı kararı (kurulu mu / profiller / yarım kurulum) KÖKTEN okunur — sahte kökle,
    /// gerçek kuruluma dokunmadan. Kurulu olmayan kökte "kurulu" DENMEZ (yoksa Başlat anlaşılmaz hatayla düşer).
    #[test]
    fn kp3_b2_ortam_ozeti_KOKTEN_okur_kurulu_degilse_kurulu_DEMEZ() {
        // app crate'inde `tempfile` yok (yeni bağımlılık EKLENMEZ) → süreç + zaman damgalı geçici dizin; KP-4: `Drop` ile silinir
        // (eskiden yalnız doğrulamalar geçerse siliniyordu — düşen koşu TEMP'te `kp3_ortam_ozeti_*` bırakıyordu).
        let gecici = GeciciKok::yeni("kp3_ortam_ozeti");
        let kok = gecici.0.clone();
        std::fs::create_dir_all(&kok).unwrap();
        let e = ortam_ozeti(&kok);
        assert!(!e.already_installed, "boş kök kurulu sayıldı");
        assert!(e.installed_profiles.is_empty() && e.pending_profiles.is_empty());
        assert_eq!(e.install_root, kok.to_string_lossy());
        assert_eq!(e.launcher_version, env!("CARGO_PKG_VERSION"));
        assert_eq!(e.platform, platform::current());
        install::add_installed_profiles(&kok, &["vet".to_string()]);
        let e2 = ortam_ozeti(&kok);
        assert_eq!(e2.installed_profiles, vec!["vet".to_string()], "kurulu profil kaydı okunmadı");
        assert!(!e2.already_installed, "yalnız profil kaydı varken (exe / frontend yok) kurulu sayıldı");
    }

    /// KP-4 (KP4-LISTESI ilk iş): testlerin geçici kökü — `Drop`'ta silinir (doğrulama düşse / panik olsa da TEMP'te kalmaz).
    struct GeciciKok(std::path::PathBuf);
    impl GeciciKok {
        fn yeni(onek: &str) -> Self {
            let ns = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
            GeciciKok(std::env::temp_dir().join(format!("{onek}_{}_{ns}", std::process::id())))
        }
    }
    impl Drop for GeciciKok {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn KRITIK_KP4_gecici_kok_PANIKTE_de_silinir() {
        let yol = std::sync::Mutex::new(None);
        let sonuc = std::panic::catch_unwind(|| {
            let g = GeciciKok::yeni("kp4_drop_sinama");
            std::fs::create_dir_all(g.0.join("alt")).unwrap();
            std::fs::write(g.0.join("alt").join("x.txt"), b"x").unwrap();
            *yol.lock().unwrap() = Some(g.0.clone());
            panic!("doğrulama düştü (kasıtlı)");
        });
        assert!(sonuc.is_err(), "kasıtlı panik yakalanmadı");
        let yol = yol.lock().unwrap().clone().expect("geçici kök kurulmadı");
        assert!(!yol.exists(), "panikte geçici kök TEMP'te kaldı: {}", yol.display());
    }

    // ═══ KP-4 A2c (Y257 a) · kök-enjeksiyonlu gövdeler — SAHTE kök (GeciciKok), ağ / gerçek kurulum / gerçek ortam YOK ═══
    const A2C_SHA: &str = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789";
    const A2C_KAYNAK: &str = "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0";

    fn a2c_manifest(launcher_surumu: &str, rollout: u32) -> String {
        let plat = platform::current();
        format!(
            r#"{{"schema":2,"version":"1.9.60",
                "runtimes":{{"{plat}":{{"url":"{A2C_KAYNAK}/base.zip","sha256":"{A2C_SHA}","size":5}}}},
                "models":{{"vet":{{"url":"{A2C_KAYNAK}/vet.zip","sha256":"{A2C_SHA}","size":3}},
                           "home":{{"url":"{A2C_KAYNAK}/home.zip","sha256":"{A2C_SHA}","size":2}}}},
                "launcher":{{"version":"{launcher_surumu}","installer_url":"{A2C_KAYNAK}/PEMFVetClient-setup.exe",
                             "sha256":"{A2C_SHA}","size":10,"rollout":{rollout}}}}}"#
        )
    }

    fn kurulu_agac(kok: &std::path::Path, ad: &str) {
        let b = kok.join(ad).join("PEMF_Backend");
        std::fs::create_dir_all(b.join("_internal").join("frontend").join("dist")).unwrap();
        std::fs::write(b.join(platform::backend_exe_name()), b"exe").unwrap();
        std::fs::write(b.join("_internal").join("frontend").join("dist").join("index.html"), b"<html>").unwrap();
    }

    #[test]
    fn KRITIK_KP4_A2c_ortam_algila_YARIM_TAKASI_kurtarir_sonra_KURULU_der() {
        let g = GeciciKok::yeni("kp4_a2c_ortam");
        std::fs::create_dir_all(&g.0).unwrap();
        let e = ortam_algila(&g.0);
        assert!(!e.already_installed && e.installed_profiles.is_empty(), "boş kök kurulu sayıldı");
        // Güncellemenin iki rename'i arasında kesinti: `runtime` yok, sağlam `runtime.old` var → kurtarılır, KURULU görünür.
        kurulu_agac(&g.0, "runtime.old");
        let e = ortam_algila(&g.0);
        assert!(e.already_installed, "yarım takas kurtarılmadı → çalışan kurulum 'kurulu değil' göründü");
        assert!(install::runtime_dir(&g.0).is_dir() && !install::runtime_old_dir(&g.0).exists());
    }

    #[test]
    fn KRITIK_KP4_A2c_profiller_MANIFESTTEN_platform_ve_baslatici_guncellemesi_rollout_kapili() {
        let g = GeciciKok::yeni("kp4_a2c_profil");
        std::fs::create_dir_all(&g.0).unwrap();
        let ham = a2c_manifest("99.0.0", 100);
        let j = profilleri_getir(|| Ok(ham.clone()), &g.0).unwrap();
        assert_eq!(j["profiles"], serde_json::json!(["home", "vet"]), "profiller sıralı listelenmedi");
        assert_eq!(j["platform_supported"], serde_json::json!(true));
        assert_eq!(j["current_launcher"], serde_json::json!(env!("CARGO_PKG_VERSION")));
        assert_eq!(j["raw"], serde_json::json!(ham), "manifest metni arayüze taşınmadı");
        assert_eq!(j["update"]["version"], serde_json::json!("99.0.0"));
        assert_eq!(j["update"]["auto"], serde_json::json!(true), "rollout %100 + deneme yokken otomatik değil");
        assert_eq!(j["update"]["rollout_bekliyor"], serde_json::json!(false));
        // rollout 0 → yayın DURDURULDU: bildirim kalır, sessiz kurulum yok
        let j = profilleri_getir(|| Ok(a2c_manifest("99.0.0", 0)), &g.0).unwrap();
        assert_eq!((j["update"]["auto"].clone(), j["update"]["rollout_bekliyor"].clone()), (serde_json::json!(false), serde_json::json!(true)));
        // deneme sınırı dolmuş hedef otomatik kurulmaz
        for _ in 0..10 {
            install::record_selfupdate_attempt(&g.0, "99.0.0");
        }
        let j = profilleri_getir(|| Ok(a2c_manifest("99.0.0", 100)), &g.0).unwrap();
        assert_eq!(j["update"]["auto"], serde_json::json!(false), "deneme sınırı dolu hedef yine otomatik");
        // kendi sürümüne ULAŞILMIŞ deneme kaydı temizlenir; eşit sürümde güncelleme YOK
        install::record_selfupdate_attempt(&g.0, env!("CARGO_PKG_VERSION"));
        let j = profilleri_getir(|| Ok(a2c_manifest(env!("CARGO_PKG_VERSION"), 100)), &g.0).unwrap();
        assert!(j["update"].is_null(), "eşit sürüm güncelleme sayıldı");
        assert_eq!(install::read_selfupdate_attempt(&g.0), None, "ulaşılan hedefin deneme kaydı temizlenmedi");
    }

    #[test]
    fn KRITIK_KP4_A2c_profiller_cekim_ve_bozuk_manifest_HATASI_arayuze_doner() {
        let g = GeciciKok::yeni("kp4_a2c_profil_hata");
        let e = profilleri_getir(|| Err(net::NetError::Dns("dns".into())), &g.0).unwrap_err();
        assert!(!e.is_empty());
        assert!(profilleri_getir(|| Ok("{bozuk".to_string()), &g.0).is_err(), "bozuk manifest kabul edildi");
        assert!(!g.0.exists(), "hata yolunda köke yazıldı");
    }

    #[test]
    fn KRITIK_KP4_A2c_guncelleme_plani_ve_ozeti_KOKTEN_bozuk_manifest_HATA() {
        let g = GeciciKok::yeni("kp4_a2c_plan");
        std::fs::create_dir_all(&g.0).unwrap();
        let ham = a2c_manifest("99.0.0", 100);
        let plan = check_runtime_update_ile(&g.0, ham.clone()).unwrap();
        for k in ["needed", "cached", "recall", "otomatik_durduruldu"] {
            assert!(plan.get(k).is_some(), "plan JSON'unda {k} yok: {plan}");
        }
        assert!(check_runtime_update_ile(&g.0, "{bozuk".into()).is_err());
        let oz = guncelleme_ozeti_ile(&g.0, ham.clone(), 1_000).unwrap();
        assert!(oz.get("karar").is_some() && oz.get("zorunlu").is_some(), "özet JSON'u eksik: {oz}");
        assert!(guncelleme_ozeti_ile(&g.0, "{bozuk".into(), 1_000).is_err());
    }

    #[test]
    fn KRITIK_KP4_A2c_onay_kaydi_SIMDI_ile_yazilir_BAYAT_onay_ozette_TEMIZLENIR() {
        let g = GeciciKok::yeni("kp4_a2c_onay");
        std::fs::create_dir_all(&g.0).unwrap();
        let ham = a2c_manifest("99.0.0", 100);
        onay_kaydet_ile(&g.0, &ham, Some("99.0.0"), 5_000).unwrap();
        let k = guncelleme_onayi::oku(&g.0).expect("onay kaydı yazılmadı");
        assert_eq!((k.launcher_hedefi.as_deref(), k.zaman), (Some("99.0.0"), 5_000));
        // Haftalar sonra özet: yaşı geçmiş onay habersiz kuruluma dönüşmez — kayıt SİLİNİR
        let _ = guncelleme_ozeti_ile(&g.0, ham.clone(), 5_000 + 365 * 24 * 3600).unwrap();
        assert!(guncelleme_onayi::oku(&g.0).is_none(), "bayat onay kaydı temizlenmedi");
        // Taze onay korunur
        onay_kaydet_ile(&g.0, &ham, None, 9_000).unwrap();
        let _ = guncelleme_ozeti_ile(&g.0, ham.clone(), 9_001).unwrap();
        assert!(guncelleme_onayi::oku(&g.0).is_some(), "taze onay silindi");
        assert!(onay_kaydet_ile(&g.0, "{bozuk", None, 1).is_err());
        // Kök yazılamaz (dosya) → hata arayüze döner
        let dosya = g.0.join("kok_dosya");
        std::fs::write(&dosya, b"x").unwrap();
        assert!(onay_kaydet_ile(&dosya, &ham, None, 1).is_err(), "yazılamayan onay başarılı sayıldı");
    }

    /// Yarım kurulumu bırak: kayıt HER iki kolda silinir. Manifest YOKSA yarım indirmelere dokunulmaz; manifest varsa GÜNCEL planın
    /// `.part`'ları korunur, plan DIŞINDAKİ (bayat) yarım indirmeler silinir (`install::clear_partials` koruma listesi).
    #[test]
    fn KRITIK_KP4_A2c_yarim_kurulum_IPTALI_kaydi_siler_bayat_yarim_indirmeyi_TEMIZLER() {
        let g = GeciciKok::yeni("kp4_a2c_iptal");
        std::fs::create_dir_all(&g.0).unwrap();
        let bayat = install::cache_dir(&g.0).join("eski.dddddddddddd.part");
        std::fs::create_dir_all(bayat.parent().unwrap()).unwrap();
        std::fs::write(&bayat, b"bayat").unwrap();
        install::write_pending(&g.0, &["vet".to_string()]);
        discard_pending_ile(&g.0, None).unwrap();
        assert!(install::read_pending(&g.0).is_empty(), "yarım kurulum kaydı silinmedi");
        assert!(bayat.exists(), "manifestsiz iptalde yarım indirme silindi");
        install::write_pending(&g.0, &["vet".to_string()]);
        discard_pending_ile(&g.0, Some(a2c_manifest("99.0.0", 100))).unwrap();
        assert!(install::read_pending(&g.0).is_empty(), "manifestli iptalde kayıt silinmedi");
        assert!(!bayat.exists(), "plan dışı (bayat) yarım indirme silinmedi");
    }

    #[test]
    fn KRITIK_KP4_A2c_kaldirma_veri_konumu_ENJEKTE_ortamdan_yedek_hedefi_KAYITTAN() {
        let ev = GeciciKok::yeni("kp4_a2c_ev");
        std::fs::create_dir_all(&ev.0).unwrap();
        let j = kaldirma_veri_konumu_ile(&ev.0, |_| None);
        let konum = j["konum"].as_str().unwrap().to_string();
        assert!(konum.starts_with(&*ev.0.to_string_lossy()) && konum.ends_with("PEMF_GUI"), "{konum}");
        assert!(j["diger"].as_array().unwrap().is_empty());
        let veri = ev.0.join("veri");
        std::fs::create_dir_all(&veri).unwrap();
        let kok = install::default_install_root(&ev.0);
        std::fs::create_dir_all(&kok).unwrap();
        assert_eq!(yedek_hedefi_durumu_ile(&kok), serde_json::json!({ "yol": null, "erisilebilir": false }));
        install::backup_dir_yaz(&kok, &veri.to_string_lossy()).unwrap();
        let y = yedek_hedefi_durumu_ile(&kok);
        assert_eq!((y["yol"].as_str(), y["erisilebilir"].as_bool()), (Some(&*veri.to_string_lossy()), Some(true)));
        let dosya = ev.0.join("hedef_aslinda_dosya");
        std::fs::write(&dosya, b"x").unwrap();
        install::backup_dir_yaz(&kok, &dosya.to_string_lossy()).unwrap();
        assert_eq!(yedek_hedefi_durumu_ile(&kok)["erisilebilir"], serde_json::json!(false), "yazılamayan hedef erişilebilir sayıldı");
    }

    // ═════════════════════════════════════════════════════════════════════════════════════
    // KP-5 B1 (sahip kararı 1, 11-11): güvenlik yolu metin çapaları (F5 / L3 / L6 / KI G1) ÖNCE aynı sıra iddiasını taşıyan DAVRANIŞ
    // testine çevrilir — eski çapa + bu test birlikte yeşil; enjeksiyon SONRA. GERÇEK `stop_backend_for_teardown`: sahte HTTP backend
    // (rastgele port; sözleşme yanıtları) + sahte SÜREÇ (bu test ikilisinin uyuyan kopyası). `kill_stray_backends` çekirdeğin
    // `test-kancasi` özelliğinde gerçek `taskkill` ÇALIŞTIRMAZ (çağrı + an kaydedilir) → sahibin kurulu backend'ine dokunulmaz.
    // ═════════════════════════════════════════════════════════════════════════════════════

    /// Sahte süreç: ortam işareti varsa uzun uyur (yoksa anında döner — normal koşuda iz bırakmaz). `#[ignore]`: yalnız çocuk koşar.
    #[test]
    #[ignore]
    fn kp5_b1_sahte_surec_uyur() {
        if std::env::var_os("PEMF_KP5_SAHTE_SUREC").is_some() {
            std::thread::sleep(std::time::Duration::from_secs(120));
        }
    }

    /// KP-5 B1 davranış testlerini sıraya sokar (gözlemci çekirdekte süreç geneli).
    static KP5_B1_KILIT: std::sync::Mutex<()> = std::sync::Mutex::new(());

    #[cfg(windows)]
    fn kp5_cocuk_canli_mi(ad: &str, pid: u32) -> bool {
        backend::surec_yollari(ad).iter().any(|(p, _)| *p == pid)
    }

    type Kp5Kayit = Arc<Mutex<Vec<(String, String, std::time::Instant, bool)>>>;

    /// Sahte backend: çocuk süreç CANLIYKEN istekleri yanıtlar ve (yöntem, yol, an, çocuk canlı mı) kaydeder; çocuk ölünce dinleyiciyi
    /// KAPATIR (gerçek ölü backend gibi: bağlantı reddi → port dosyası temizlenebilir).
    #[cfg(windows)]
    fn kp5_sahte_backend(ln: std::net::TcpListener, ad: String, pid: u32, kayit: Kp5Kayit) -> std::thread::JoinHandle<()> {
        kp5_sahte_backend_ile(ln, move || kp5_cocuk_canli_mi(&ad, pid), kayit)
    }

    /// `kp5_sahte_backend`in gövdesi — "backend canlı mı" yüklemi ENJEKTE (izlenen: çocuk süreç · orphan: test bayrağı).
    fn kp5_sahte_backend_ile(
        ln: std::net::TcpListener,
        canli_mi: impl Fn() -> bool + Send + 'static,
        kayit: Kp5Kayit,
    ) -> std::thread::JoinHandle<()> {
        use std::io::{Read, Write};
        ln.set_nonblocking(true).unwrap();
        std::thread::spawn(move || {
            let bitis = std::time::Instant::now() + std::time::Duration::from_secs(60);
            while std::time::Instant::now() < bitis && canli_mi() {
                let Ok((mut c, _)) = ln.accept() else {
                    std::thread::sleep(std::time::Duration::from_millis(5));
                    continue;
                };
                let _ = c.set_nonblocking(false);
                let _ = c.set_read_timeout(Some(std::time::Duration::from_secs(2)));
                let mut buf = vec![0u8; 8192];
                let n = c.read(&mut buf).unwrap_or(0);
                if n == 0 {
                    continue; // yalnız TCP yoklaması (`backend_is_definitely_gone`) — istek değil, kaydedilmez
                }
                let istek = String::from_utf8_lossy(&buf[..n]).to_string();
                let mut ilk = istek.lines().next().unwrap_or("").split_whitespace();
                let (yontem, yol) = (ilk.next().unwrap_or("").to_string(), ilk.next().unwrap_or("").to_string());
                let canli = canli_mi();
                kayit.lock().unwrap().push((yontem, yol.clone(), std::time::Instant::now(), canli));
                let (kod, govde) = match yol.as_str() {
                    "/api/hardware/kapanis_durdur" => {
                        ("200 OK", r#"{"status":"success","confirmed":true,"stmStopped":true,"mqttResults":[]}"#)
                    }
                    "/api/health" => ("200 OK", r#"{"service":"PEMF-Vet","status":"ok"}"#),
                    "/api/auth/desktop-session" => ("200 OK", "{}"),
                    _ => ("404 Not Found", "{}"),
                };
                let yanit = format!(
                    "HTTP/1.1 {kod}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{govde}",
                    govde.len()
                );
                let _ = c.write_all(yanit.as_bytes());
                let _ = c.flush();
            }
            drop(ln); // çocuk öldü → "ölü backend" (bağlantı reddi)
        })
    }

    /// KRİTİK (F5 + L3 + KI G1 davranışla): izlenen backend'in sökümünde sıra STOP (kapanış ucu) → yakma yoklaması → son oturum
    /// çekimi — üçü de süreç CANLIYKEN — → süreç öldürülür → artakalan temizliği SÜREÇ ÖLDÜKTEN SONRA → ölü backend'in port dosyası
    /// silinir. Eski metin çapaları DEĞİŞMEDEN yeşil (`f5_kapanis_sirasi_…`, `KRITIK_L3_…`, `KRITIK_KI_G1_…`).
    #[cfg(windows)]
    #[test]
    fn KRITIK_KP5_B1_teardown_SIRASI_DAVRANIS_stop_yakma_yakala_SUREC_CANLIYKEN_sonra_kill_sonra_artakalan() {
        let _k = KP5_B1_KILIT.lock().unwrap_or_else(|e| e.into_inner());
        let exe = std::env::current_exe().unwrap();
        let ad = exe.file_name().unwrap().to_string_lossy().to_string();
        let mut komut = std::process::Command::new(&exe);
        komut
            .args(["tests::kp5_b1_sahte_surec_uyur", "--exact", "--ignored", "--test-threads=1", "-q"])
            .env("PEMF_KP5_SAHTE_SUREC", "1")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null());
        {
            use std::os::windows::process::CommandExt;
            komut.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
        }
        let cocuk = komut.spawn().expect("sahte süreç başlamadı");
        let pid = cocuk.id();
        assert!(kp5_cocuk_canli_mi(&ad, pid), "sahte süreç görünmüyor");
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ln.local_addr().unwrap().port();
        let kayit: Kp5Kayit = Arc::new(Mutex::new(Vec::new()));
        let sunucu = kp5_sahte_backend(ln, ad.clone(), pid, kayit.clone());
        let kok = std::env::temp_dir().join(format!("pemf_kp5_b1_{}_{port}", std::process::id()));
        std::fs::create_dir_all(&kok).unwrap();
        std::fs::write(kok.join("backend.port"), port.to_string()).unwrap();
        let artakalan_aninda_canli = Arc::new(Mutex::new(None::<bool>));
        let (ad_g, a_g, kok_g) = (ad.clone(), artakalan_aninda_canli.clone(), kok.clone());
        backend::test_kancasi::gozlemci_kur(Some(Box::new(move |k: &std::path::Path| {
            if k == kok_g {
                *a_g.lock().unwrap() = Some(kp5_cocuk_canli_mi(&ad_g, pid));
            }
        })));
        let t0 = std::time::Instant::now();
        stop_backend_for_teardown(Some((cocuk, port)), &kok, Arc::new(Mutex::new(None)));
        let sure = t0.elapsed();
        backend::test_kancasi::gozlemci_kur(None);
        // Sahte süreç 120 sn uyur: söküm onu ÖLDÜRMEK yerine kendiliğinden çıkmasını beklerse (kill yok) bu sınır aşılır.
        assert!(sure < std::time::Duration::from_secs(30), "süreç öldürülmedi — söküm {sure:?} bekledi");
        let _ = sunucu.join();
        let k = kayit.lock().unwrap().clone();
        let yollar: Vec<(&str, &str)> = k.iter().map(|(y, p, _, _)| (y.as_str(), p.as_str())).collect();
        // 1) STOP ÖNCE (kapanış ucu, onaylı), sonra yakma yoklaması, sonra son oturum çekimi — başka istek YOK.
        assert_eq!(
            yollar,
            vec![("POST", "/api/hardware/kapanis_durdur"), ("GET", "/api/health"), ("GET", "/api/auth/desktop-session")],
            "söküm istek sırası STOP → yakma yoklaması → son oturum çekimi değil"
        );
        // 2) Üçü de süreç CANLIYKEN (kill bunlardan SONRA).
        assert!(k.iter().all(|(_, _, _, canli)| *canli), "bir istek süreç ÖLDÜKTEN sonra geldi (kill erken): {k:?}");
        // 3) Süreç öldürüldü; artakalan temizliği TAM BİR kez, bu kökle, süreç ÖLDÜKTEN sonra ve son istekten SONRA.
        assert!(!kp5_cocuk_canli_mi(&ad, pid), "izlenen backend öldürülmedi");
        let ak = backend::test_kancasi::cagrilar(&kok);
        assert_eq!(ak.len(), 1, "artakalan temizliği çağrı sayısı");
        assert_eq!(*artakalan_aninda_canli.lock().unwrap(), Some(false), "artakalan temizliği süreç CANLIYKEN (kill'den önce) çağrıldı");
        assert!(ak[0] > k.last().unwrap().2 && ak[0] > t0, "artakalan temizliği son istekten ÖNCE");
        // 4) Ölü backend'in E-stop adresi (port dosyası) temizlendi.
        assert!(!kok.join("backend.port").exists(), "ölü backend'in port dosyası kaldı");
        let _ = std::fs::remove_dir_all(&kok);
    }

    /// KP-5 B1b ortak düzenek: bu test ikilisinin uyuyan kopyasını (sahte süreç) başlatır → (çocuk, pid, ikili adı).
    #[cfg(windows)]
    fn kp5_sahte_surec() -> (std::process::Child, u32, String) {
        use std::os::windows::process::CommandExt;
        let exe = std::env::current_exe().unwrap();
        let ad = exe.file_name().unwrap().to_string_lossy().to_string();
        let cocuk = std::process::Command::new(&exe)
            .args(["tests::kp5_b1_sahte_surec_uyur", "--exact", "--ignored", "--test-threads=1", "-q"])
            .env("PEMF_KP5_SAHTE_SUREC", "1")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
            .spawn()
            .expect("sahte süreç başlamadı");
        let pid = cocuk.id();
        assert!(kp5_cocuk_canli_mi(&ad, pid), "sahte süreç görünmüyor");
        (cocuk, pid, ad)
    }

    fn kp5_yollar(k: &Kp5Kayit) -> Vec<(String, String)> {
        k.lock().unwrap().iter().map(|(y, p, _, _)| (y.clone(), p.clone())).collect()
    }

    fn kp5_cift(y: &str, p: &str) -> (String, String) {
        (y.to_string(), p.to_string())
    }

    /// KRİTİK (KP-5 B1b · F5 + L3 + KI G1 + hotspot sırası DAVRANIŞLA): pencere kapanışının (Destroyed) işi — kabuktan BAYT AYNI taşınan
    /// `pencere_kapanis_isi` — STOP → yakma yoklaması → son oturum çekimi (süreç CANLIYKEN) → kill → artakalan (süreç ÖLDÜKTEN sonra) →
    /// ölü backend'in port dosyası silinir. Hotspot kapatma kurulu betik yokken (geçici kök) hiçbir şey yapmaz (sahibin ağına dokunulmaz).
    #[cfg(windows)]
    #[test]
    fn KRITIK_KP5_B1_pencere_kapanis_isi_SIRASI_DAVRANIS_stop_yakma_yakala_SUREC_CANLIYKEN_sonra_kill_sonra_artakalan() {
        let _k = KP5_B1_KILIT.lock().unwrap_or_else(|e| e.into_inner());
        let (cocuk, pid, ad) = kp5_sahte_surec();
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ln.local_addr().unwrap().port();
        let kayit: Kp5Kayit = Arc::new(Mutex::new(Vec::new()));
        // Süreç ölünce soketi AYNI ANDA kapanır: dinleyici `kapat` ile de kapanır ve artakalan gözlemcisi (kill'den SONRA, port
        // yoklamasından ÖNCE) onu kapatıp bekler — "çocuk öldü mü" yoklamasıyla yarış YOK (beklemesiz port yoklaması belirlenimci).
        let kapat = Arc::new(AtomicBool::new(false));
        let (ad_s, kapat_s) = (ad.clone(), kapat.clone());
        let sunucu = Arc::new(Mutex::new(Some(kp5_sahte_backend_ile(
            ln,
            move || !kapat_s.load(Ordering::SeqCst) && kp5_cocuk_canli_mi(&ad_s, pid),
            kayit.clone(),
        ))));
        let kok = std::env::temp_dir().join(format!("pemf_kp5_b1p_{}_{port}", std::process::id()));
        std::fs::create_dir_all(&kok).unwrap();
        std::fs::write(kok.join("backend.port"), port.to_string()).unwrap();
        let aninda = Arc::new(Mutex::new(None::<bool>));
        let (ad_g, a_g, kok_g, kapat_g, sunucu_g) = (ad.clone(), aninda.clone(), kok.clone(), kapat.clone(), sunucu.clone());
        backend::test_kancasi::gozlemci_kur(Some(Box::new(move |k: &std::path::Path| {
            if k == kok_g {
                *a_g.lock().unwrap() = Some(kp5_cocuk_canli_mi(&ad_g, pid));
                kapat_g.store(true, Ordering::SeqCst);
                if let Some(h) = sunucu_g.lock().unwrap().take() {
                    let _ = h.join();
                }
            }
        })));
        let t0 = std::time::Instant::now();
        pencere_kapanis_isi(cocuk, port, kok.clone(), Arc::new(Mutex::new(None)), backend::YakmaBeklemeSiniri::default());
        let sure = t0.elapsed();
        backend::test_kancasi::gozlemci_kur(None);
        kapat.store(true, Ordering::SeqCst);
        if let Some(h) = sunucu.lock().unwrap().take() {
            let _ = h.join();
        }
        assert!(sure < std::time::Duration::from_secs(30), "süreç öldürülmedi — iş {sure:?} bekledi");
        assert_eq!(
            kp5_yollar(&kayit),
            vec![
                kp5_cift("POST", "/api/hardware/kapanis_durdur"),
                kp5_cift("GET", "/api/health"),
                kp5_cift("GET", "/api/auth/desktop-session")
            ],
            "kapanış işi istek sırası STOP → yakma yoklaması → son oturum çekimi değil"
        );
        let k = kayit.lock().unwrap().clone();
        assert!(k.iter().all(|(_, _, _, c)| *c), "bir istek süreç ÖLDÜKTEN sonra geldi (kill erken): {k:?}");
        assert!(!kp5_cocuk_canli_mi(&ad, pid), "izlenen backend öldürülmedi");
        let ak = backend::test_kancasi::cagrilar(&kok);
        assert_eq!(ak.len(), 1, "artakalan temizliği çağrı sayısı");
        assert_eq!(*aninda.lock().unwrap(), Some(false), "artakalan temizliği süreç CANLIYKEN çağrıldı");
        assert!(ak[0] > k.last().unwrap().2, "artakalan temizliği son istekten ÖNCE");
        assert!(!kok.join("backend.port").exists(), "ölü backend'in port dosyası kaldı");
        let _ = std::fs::remove_dir_all(&kok);
    }

    /// KRİTİK (KP-5 B1b · L6 / İG-8.27 + F5 "orphan HARİÇ" DAVRANIŞLA): izlenen backend YOKKEN `backend.port`taki (başka sürecin)
    /// backend STOP alır ve yakması beklenir — son oturum ÇEKİLMEZ (başka sürecin jetonu: zehirlenme); artakalan temizliği STOP'tan
    /// SONRA; backend hâlâ CANLI → E-stop adresi (port dosyası) KORUNUR. Varsayılan port dinleyicisiz (kesin ölü → hedef değil).
    #[cfg(windows)]
    #[test]
    fn KRITIK_KP5_B1_orphan_STOP_alir_son_oturum_CEKILMEZ_canli_backendin_port_dosyasi_KORUNUR() {
        let _k = KP5_B1_KILIT.lock().unwrap_or_else(|e| e.into_inner());
        let canli = Arc::new(AtomicBool::new(true));
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ln.local_addr().unwrap().port();
        let kayit: Kp5Kayit = Arc::new(Mutex::new(Vec::new()));
        let c = canli.clone();
        let sunucu = kp5_sahte_backend_ile(ln, move || c.load(Ordering::SeqCst), kayit.clone());
        let bos = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let olu_port = bos.local_addr().unwrap().port();
        drop(bos); // dinleyicisiz → kesin ölü
        let kok = std::env::temp_dir().join(format!("pemf_kp5_b1o_{}_{port}", std::process::id()));
        std::fs::create_dir_all(&kok).unwrap();
        std::fs::write(kok.join("backend.port"), port.to_string()).unwrap();
        stop_backend_for_teardown_portla(None, &kok, Arc::new(Mutex::new(None)), olu_port);
        let son_istek = kayit.lock().unwrap().last().map(|x| x.2);
        canli.store(false, Ordering::SeqCst);
        let _ = sunucu.join();
        assert_eq!(
            kp5_yollar(&kayit),
            vec![kp5_cift("POST", "/api/hardware/kapanis_durdur"), kp5_cift("GET", "/api/health")],
            "orphan söküm sırası STOP → yakma yoklaması değil (ya da son oturum ÇEKİLDİ — başka sürecin jetonu)"
        );
        let ak = backend::test_kancasi::cagrilar(&kok);
        assert_eq!(ak.len(), 1, "artakalan temizliği çağrı sayısı");
        assert!(Some(ak[0]) > son_istek, "artakalan temizliği STOP'tan ÖNCE");
        assert!(kok.join("backend.port").exists(), "CANLI backend'in E-stop adresi silindi");
        let _ = std::fs::remove_dir_all(&kok);
    }

    /// KRİTİK (KP-5 B1b · L6 / İG-8.27 DAVRANIŞLA): port dosyası YOKKEN varsayılan portta kimliği PEMF olan backend de STOP alır (eskiden
    /// STOP'suz ADLA öldürülüyordu) — kimlik yoklaması → STOP → yakma yoklaması; son oturum ÇEKİLMEZ; artakalan temizliği SONRA.
    #[cfg(windows)]
    #[test]
    fn KRITIK_KP5_B1_orphan_VARSAYILAN_porttaki_PEMF_backendi_de_STOP_alir() {
        let _k = KP5_B1_KILIT.lock().unwrap_or_else(|e| e.into_inner());
        let canli = Arc::new(AtomicBool::new(true));
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let varsayilan = ln.local_addr().unwrap().port();
        let kayit: Kp5Kayit = Arc::new(Mutex::new(Vec::new()));
        let c = canli.clone();
        let sunucu = kp5_sahte_backend_ile(ln, move || c.load(Ordering::SeqCst), kayit.clone());
        let kok = std::env::temp_dir().join(format!("pemf_kp5_b1v_{}_{varsayilan}", std::process::id()));
        std::fs::create_dir_all(&kok).unwrap();
        stop_backend_for_teardown_portla(None, &kok, Arc::new(Mutex::new(None)), varsayilan);
        let son_istek = kayit.lock().unwrap().last().map(|x| x.2);
        canli.store(false, Ordering::SeqCst);
        let _ = sunucu.join();
        assert_eq!(
            kp5_yollar(&kayit),
            vec![kp5_cift("GET", "/api/health"), kp5_cift("POST", "/api/hardware/kapanis_durdur"), kp5_cift("GET", "/api/health")],
            "varsayılan porttaki PEMF backend'i: kimlik → STOP → yakma yoklaması değil"
        );
        let ak = backend::test_kancasi::cagrilar(&kok);
        assert_eq!(ak.len(), 1, "artakalan temizliği çağrı sayısı");
        assert!(Some(ak[0]) > son_istek, "artakalan temizliği STOP'tan ÖNCE");
        let _ = std::fs::remove_dir_all(&kok);
    }

    // ═════════════════════════════════════════════════════════════════════════════════════
    // KP-5 B4 (A2 deseni): auth komutlarının gövdeleri — geçici kök (gerçek DPAPI kaydı, gerçek kurulum kökü DEĞİL) + sahte
    // yenileyici / backend temizleyici / ağ bildirimi. Gerçek ağ YOK, gerçek kimlik kasası YOK.
    // ═════════════════════════════════════════════════════════════════════════════════════

    fn kp5_b4_kok(ad: &str) -> std::path::PathBuf {
        let k = std::env::temp_dir().join(format!("pemf_kp5_b4_{ad}_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&k);
        std::fs::create_dir_all(&k).unwrap();
        k
    }

    fn kp5_b4_oturum(rt: &str, exp: i64) -> auth::Session {
        auth::Session { access_token: format!("a-{rt}"), refresh_token: rt.into(), email: "vet@klinik.tr".into(), expires_at: exp }
    }

    fn kp5_b4_durum(d: &AuthStatus) -> (bool, String, &'static str, bool) {
        (d.logged_in, d.email.clone(), d.source, d.offline)
    }

    /// KRİTİK (KP-5 B4): açılış oturum durumu 1)–3) — bellekte oturum → "fresh" (kayda bakılmaz) · kayıt yok → çıkış · taze kayıt →
    /// belleğe alınır, "cached" · bayat kayıt → sessiz yenilemeye (kayıt AYNEN döner).
    #[cfg(windows)]
    #[test]
    fn KRITIK_KP5_B4_oturum_ilk_durum_bellek_KAYITSIZ_TAZE_BAYAT() {
        let kok = kp5_b4_kok("ilk");
        let bellek = Mutex::new(Some(kp5_b4_oturum("bellek", 0)));
        match oturum_ilk_durum(&bellek, &kok, 1_000) {
            OturumIlkDurum::Sonuc(d) => assert_eq!(kp5_b4_durum(&d), (true, "vet@klinik.tr".into(), "fresh", false)),
            OturumIlkDurum::Yenile(_) => panic!("bellekte oturum varken yenilemeye gidildi"),
        }
        let bellek = Mutex::new(None);
        match oturum_ilk_durum(&bellek, &kok, 1_000) {
            OturumIlkDurum::Sonuc(d) => assert_eq!(kp5_b4_durum(&d), (false, String::new(), "none", false), "kayıt yokken giriş sayıldı"),
            OturumIlkDurum::Yenile(_) => panic!("kayıt yokken yenilemeye gidildi"),
        }
        assert!(secret_store::save(&kok, &kp5_b4_oturum("taze", 0)), "geçici köke kayıt yazılamadı");
        match oturum_ilk_durum(&bellek, &kok, 1_000) {
            OturumIlkDurum::Sonuc(d) => assert_eq!(kp5_b4_durum(&d), (true, "vet@klinik.tr".into(), "cached", false)),
            OturumIlkDurum::Yenile(_) => panic!("taze kayıt yenilemeye gitti"),
        }
        assert_eq!(bellek.lock().unwrap().as_ref().map(|s| s.refresh_token.clone()), Some("taze".into()), "taze kayıt belleğe alınmadı");
        let bellek = Mutex::new(None);
        assert!(secret_store::save(&kok, &kp5_b4_oturum("bayat", 500)));
        match oturum_ilk_durum(&bellek, &kok, 1_000) {
            OturumIlkDurum::Yenile(k) => assert_eq!(k.refresh_token, "bayat"),
            OturumIlkDurum::Sonuc(_) => panic!("bayat kayıt yenilenmeden kullanıldı"),
        }
        assert!(bellek.lock().unwrap().is_none(), "bayat kayıt yenilenmeden belleğe alındı");
        let _ = std::fs::remove_dir_all(&kok);
    }

    /// KRİTİK (KP-5 B4 · OFFLINE KARARI): sessiz yenileme sonucu — yenilendi → yeni refresh_token SAKLANIR + belleğe ("fresh") ·
    /// REDDEDİLDİ (oturum iptal) → nedeni günlüğe, kayıt SİLİNİR, çıkış · ulaşılamadı → nedeni günlüğe, kayıt KORUNUR, kayıtlı oturumla
    /// çevrimdışı devam ("cached", offline). Yenileyiciye kayıtlı refresh_token + e-posta gider.
    #[cfg(windows)]
    #[test]
    fn KRITIK_KP5_B4_oturum_yenileme_YENILENDI_SIL_CEVRIMDISI() {
        let kok = kp5_b4_kok("yenile");
        // (a) yenilendi
        assert!(secret_store::save(&kok, &kp5_b4_oturum("eski", 500)));
        let bellek = Mutex::new(None);
        let mut gelen = None;
        let d = oturum_yenileme_sonucu(&bellek, &kok, kp5_b4_oturum("eski", 500), |rt, e| {
            gelen = Some((rt.to_string(), e.to_string()));
            (Ok(kp5_b4_oturum("yeni", 9_999_999)), None)
        });
        assert_eq!(gelen, Some(("eski".into(), "vet@klinik.tr".into())));
        assert_eq!(kp5_b4_durum(&d), (true, "vet@klinik.tr".into(), "fresh", false));
        assert_eq!(secret_store::load(&kok).map(|s| s.refresh_token), Some("yeni".into()), "yenilenen jeton SAKLANMADI");
        assert_eq!(bellek.lock().unwrap().as_ref().map(|s| s.refresh_token.clone()), Some("yeni".into()));
        // (b) reddedildi → sil
        let bellek = Mutex::new(None);
        let d = oturum_yenileme_sonucu(&bellek, &kok, kp5_b4_oturum("yeni", 500), |_, _| {
            (Err(auth::AuthError::SessionRevoked), Some("HTTP 400 refresh_token_not_found".into()))
        });
        assert_eq!(kp5_b4_durum(&d), (false, String::new(), "none", false));
        assert!(secret_store::load(&kok).is_none(), "iptal edilen oturumun kaydı SİLİNMEDİ (güvenlik)");
        assert!(bellek.lock().unwrap().is_none());
        let g = std::fs::read_to_string(secret_store::oturum_gunlugu_path(&kok)).unwrap_or_default();
        assert!(g.contains("REDDEDILDI (HTTP 400 refresh_token_not_found)") && g.contains("SILINDI"), "silme nedeni günlükte yok: {g}");
        // (c) ulaşılamadı → çevrimdışı devam, kayıt korunur
        assert!(secret_store::save(&kok, &kp5_b4_oturum("kayitli", 500)));
        let bellek = Mutex::new(None);
        let d = oturum_yenileme_sonucu(&bellek, &kok, kp5_b4_oturum("kayitli", 500), |_, _| {
            (Err(auth::AuthError::Offline), Some("HTTP 503".into()))
        });
        assert_eq!(kp5_b4_durum(&d), (true, "vet@klinik.tr".into(), "cached", true), "ulaşılamayınca cihaz kilitlendi (OFFLINE KARARI)");
        assert_eq!(secret_store::load(&kok).map(|s| s.refresh_token), Some("kayitli".into()), "çevrimdışıyken kayıt silindi");
        assert_eq!(bellek.lock().unwrap().as_ref().map(|s| s.refresh_token.clone()), Some("kayitli".into()));
        let g = std::fs::read_to_string(secret_store::oturum_gunlugu_path(&kok)).unwrap_or_default();
        assert!(g.contains("basarisiz (HTTP 503) -> kayit KORUNDU"), "çevrimdışı nedeni günlükte yok: {g}");
        let _ = std::fs::remove_dir_all(&kok);
    }

    /// KRİTİK (KP-5 B4): giriş sonrası kayıt — "Beni hatırla" İŞARETLİ → tercih + DPAPI kaydı; İŞARETSİZ → tercih "hayır" ve ÖNCEKİ kayıt
    /// SİLİNİR (kutucuk kaldırılınca eski jeton diskte kalmaz).
    #[cfg(windows)]
    #[test]
    fn KRITIK_KP5_B4_giris_kaydi_HATIRLA_kaydeder_HATIRLAMA_onceki_kaydi_SILER() {
        let kok = kp5_b4_kok("giris");
        giris_kaydini_isle(&kok, &kp5_b4_oturum("g1", 0), true);
        assert_eq!(secret_store::load(&kok).map(|s| s.refresh_token), Some("g1".into()), "hatırla işaretliyken kaydedilmedi");
        assert!(secret_store::hatirla_isareti_path(&kok).exists(), "tercih işareti yazılmadı");
        let isaret_evet = std::fs::read(secret_store::hatirla_isareti_path(&kok)).unwrap();
        giris_kaydini_isle(&kok, &kp5_b4_oturum("g2", 0), false);
        assert!(secret_store::load(&kok).is_none(), "hatırla işaretsizken ÖNCEKİ kayıt silinmedi");
        let isaret_hayir = std::fs::read(secret_store::hatirla_isareti_path(&kok)).unwrap_or_default();
        assert_ne!(isaret_evet, isaret_hayir, "işaretsiz giriş tercihi değiştirmedi");
        let _ = std::fs::remove_dir_all(&kok);
    }

    /// KRİTİK (KP-5 B4): çıkış sırası — ÖNCE backend devir oturumu + "Beni hatırla" kaydı (kesin), SONRA ağ bildirimi (best-effort);
    /// backend yoksa backend temizliği çağrılmaz, bellekte oturum yoksa ağa çıkılmaz. Ağ bildirimi geldiğinde kayıt ZATEN silinmiş.
    #[cfg(windows)]
    #[test]
    fn KRITIK_KP5_B4_cikis_ONCE_yerel_temizlik_SONRA_ag() {
        let kok = kp5_b4_kok("cikis");
        assert!(secret_store::save(&kok, &kp5_b4_oturum("c1", 0)));
        let sira = std::cell::RefCell::new(Vec::<String>::new());
        let kok_g = kok.clone();
        cikis_isle(
            &kok,
            Some(8123),
            Some(kp5_b4_oturum("c1", 0)),
            |p| sira.borrow_mut().push(format!("backend {p} kayit={}", secret_store::load(&kok_g).is_some())),
            |j| sira.borrow_mut().push(format!("ag {j} kayit={}", secret_store::load(&kok_g).is_some())),
        );
        assert_eq!(*sira.borrow(), vec!["backend 8123 kayit=true".to_string(), "ag a-c1 kayit=false".to_string()]);
        assert!(secret_store::load(&kok).is_none());
        sira.borrow_mut().clear();
        cikis_isle(&kok, None, None, |p| sira.borrow_mut().push(format!("backend {p}")), |j| sira.borrow_mut().push(format!("ag {j}")));
        assert!(sira.borrow().is_empty(), "backend / oturum yokken çağrı yapıldı: {:?}", sira.borrow());
        let _ = std::fs::remove_dir_all(&kok);
    }

    // ═════════════════════════════════════════════════════════════════════════════════════
    // KP-5 B4b: güvenlik yolu yardımcılarının kalan KOLLARI davranışla — `son_oturumu_yakala` (oturum / çıkış) ve
    // `yakma_bitene_kadar_bekle` (yakma BİTTİ / azami bütçe DOLDU). Sahte HTTP backend (rastgele port; yol başına sıralı yanıt).
    // ═════════════════════════════════════════════════════════════════════════════════════

    /// Sıralı yanıt veren sahte backend: `yanitla(yol, o yola kaçıncı istek)` → gövde (200). `kapat` ile durur; gelen yollar kaydedilir.
    fn kp5_yanitlayan(
        yanitla: impl Fn(&str, usize) -> String + Send + 'static,
    ) -> (u16, Arc<AtomicBool>, Arc<Mutex<Vec<String>>>, std::thread::JoinHandle<()>) {
        use std::io::{Read, Write};
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ln.local_addr().unwrap().port();
        ln.set_nonblocking(true).unwrap();
        let (kapat, yollar) = (Arc::new(AtomicBool::new(false)), Arc::new(Mutex::new(Vec::<String>::new())));
        let (k, y) = (kapat.clone(), yollar.clone());
        let h = std::thread::spawn(move || {
            let bitis = std::time::Instant::now() + std::time::Duration::from_secs(60);
            while !k.load(Ordering::SeqCst) && std::time::Instant::now() < bitis {
                let Ok((mut c, _)) = ln.accept() else {
                    std::thread::sleep(std::time::Duration::from_millis(5));
                    continue;
                };
                let _ = c.set_nonblocking(false);
                let _ = c.set_read_timeout(Some(std::time::Duration::from_secs(2)));
                let mut buf = vec![0u8; 8192];
                let n = c.read(&mut buf).unwrap_or(0);
                if n == 0 {
                    continue;
                }
                let istek = String::from_utf8_lossy(&buf[..n]).to_string();
                let yol = istek.lines().next().unwrap_or("").split_whitespace().nth(1).unwrap_or("").to_string();
                let kac = {
                    let mut g = y.lock().unwrap();
                    g.push(yol.clone());
                    g.iter().filter(|x| **x == yol).count() - 1
                };
                let govde = yanitla(&yol, kac);
                let _ = c.write_all(
                    format!("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{govde}", govde.len())
                        .as_bytes(),
                );
                let _ = c.flush();
            }
        });
        (port, kapat, yollar, h)
    }

    /// KRİTİK (KP-5 B4b · F5): söküm öncesi son oturum çekimi — backend döndürülmüş oturumu verirse "Beni hatırla" kaydı ve bellek
    /// TAZELENİR (sonraki açılışta bayat jeton → SessionRevoked olmaz); pencerede çıkış yapılmışsa ({"cikis": true}) kayıt ve bellek SİLİNİR.
    #[cfg(windows)]
    #[test]
    fn KRITIK_KP5_B4b_son_oturum_yakalama_OTURUM_tazeler_CIKIS_temizler() {
        let kok = kp5_b4_kok("yakala");
        assert!(secret_store::save(&kok, &kp5_b4_oturum("r1", 0)));
        let bellek = Mutex::new(Some(kp5_b4_oturum("r1", 0)));
        let (port, kapat, yollar, h) = kp5_yanitlayan(|yol, _| {
            if yol == "/api/auth/desktop-session" {
                r#"{"access_token":"a-r2","refresh_token":"r2","email":"vet@klinik.tr","expires_at":0}"#.to_string()
            } else {
                "{}".to_string()
            }
        });
        son_oturumu_yakala(port, &kok, &bellek);
        assert_eq!(secret_store::load(&kok).map(|s| s.refresh_token), Some("r2".into()), "döndürülmüş jeton diske işlenmedi");
        assert_eq!(bellek.lock().unwrap().as_ref().map(|s| s.refresh_token.clone()), Some("r2".into()), "bellek tazelenmedi");
        kapat.store(true, Ordering::SeqCst);
        let _ = h.join();
        assert_eq!(*yollar.lock().unwrap(), vec!["/api/auth/desktop-session".to_string()]);
        let (port, kapat, _y, h) = kp5_yanitlayan(|_, _| r#"{"cikis":true}"#.to_string());
        son_oturumu_yakala(port, &kok, &bellek);
        kapat.store(true, Ordering::SeqCst);
        let _ = h.join();
        assert!(secret_store::load(&kok).is_none(), "pencere çıkışından sonra 'Beni hatırla' kaydı kaldı");
        assert!(bellek.lock().unwrap().is_none(), "pencere çıkışından sonra bellekte oturum kaldı");
        let _ = std::fs::remove_dir_all(&kok);
    }

    /// KRİTİK (KP-5 B4b · L3 / Y82): söküm STOP'tan sonra yakmayı bekler — yakma sürerken yoklar, BİTİNCE döner (en az bir aralık
    /// bekledi); bütçe zaten dolmuşsa (aynı kapanışın önceki beklemesi tüketti — KI G1) yakma sürse de BEKLEMEDEN döner (tek yoklama).
    #[test]
    fn KRITIK_KP5_B4b_yakma_beklemesi_BITTI_ve_BUTCE_DOLDU() {
        let yakiyor = |sure: bool| format!(r#"{{"service":"PEMF-Vet","firmwareGuncelleme":{{"yakiliyor":{sure}}}}}"#);
        let (port, kapat, yollar, h) = kp5_yanitlayan(move |_, kac| yakiyor(kac == 0));
        let t0 = std::time::Instant::now();
        yakma_bitene_kadar_bekle(port, &backend::YakmaBeklemeSiniri::default());
        let sure = t0.elapsed();
        kapat.store(true, Ordering::SeqCst);
        let _ = h.join();
        assert_eq!(yollar.lock().unwrap().len(), 2, "yakma sürerken yeniden yoklanmadı");
        assert!(sure >= std::time::Duration::from_millis(900), "yakma sürerken BEKLEMEDİ ({sure:?})");
        let (port, kapat, yollar, h) = kp5_yanitlayan(move |_, _| r#"{"firmwareGuncelleme":{"yakiliyor":true}}"#.to_string());
        let sinir = backend::YakmaBeklemeSiniri::default();
        let _ = sinir.son_an(std::time::Instant::now(), std::time::Duration::ZERO); // bütçe önceki beklemede tükendi
        let t0 = std::time::Instant::now();
        yakma_bitene_kadar_bekle(port, &sinir);
        let sure = t0.elapsed();
        kapat.store(true, Ordering::SeqCst);
        let _ = h.join();
        assert_eq!(yollar.lock().unwrap().len(), 1, "bütçe dolmuşken yeniden yoklandı");
        assert!(sure < std::time::Duration::from_millis(900), "bütçe dolmuşken BEKLEDİ ({sure:?}) — kapanış ikinci azamiyi bekler");
    }

    // ═════════════════════════════════════════════════════════════════════════════════════
    // KP-6 D (madde 6) · `firmware_uyumsuz_geri_al` (LN L2 · Y16 + Y81) — Tauri'siz düz işlev: yeniden düzenleme GEREKMEDİ, GERÇEK
    // işlev KP-5 B1 aparatıyla (sahte süreç + sahte backend + çekirdeğin `test-kancasi` artakalan gözlemcisi) davranışla sabitlenir.
    // ═════════════════════════════════════════════════════════════════════════════════════

    /// KRİTİK (L2 · Y16 + Y81): kart yazılımı uyumsuz → sıra ⚠️ E-stop (STOP) → yakma yoklaması → son oturum çekimi (süreç CANLIYKEN)
    /// → kill → artakalan (süreç ÖLDÜKTEN sonra) → ANCAK SONRA deneme sayacı + eski sürüme dönüş (artakalan anında `runtime.old` henüz
    /// yerinde, sayaç yazılmamış) → `GeriAlindi { kod: firmware_uyumsuz }` + eylem söyleyen neden; eski sürüm geri gelir, bozuk yeni silinir.
    #[cfg(windows)]
    #[test]
    fn KRITIK_KP6_D_firmware_uyumsuz_geri_al_SIRA_estop_kill_SONRA_sayac_ve_ESKI_surume_donus() {
        let _k = KP5_B1_KILIT.lock().unwrap_or_else(|e| e.into_inner());
        let (cocuk, pid, ad) = kp5_sahte_surec();
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ln.local_addr().unwrap().port();
        let kayit: Kp5Kayit = Arc::new(Mutex::new(Vec::new()));
        let sunucu = kp5_sahte_backend(ln, ad.clone(), pid, kayit.clone());
        let kok = std::env::temp_dir().join(format!("pemf_kp6_d_fw_{}_{port}", std::process::id()));
        let _ = std::fs::remove_dir_all(&kok);
        let exe_yolu = |k: &std::path::Path| k.join("PEMF_Backend").join(pemf_launcher_core::platform::backend_exe_name());
        let yeni = install::runtime_dir(&kok);
        let eski = install::runtime_old_dir(&kok);
        for (dizin, icerik) in [(&yeni, b"YENI-SURUM".as_slice()), (&eski, b"ESKI-SURUM".as_slice())] {
            std::fs::create_dir_all(exe_yolu(dizin).parent().unwrap()).unwrap();
            std::fs::write(exe_yolu(dizin), icerik).unwrap();
        }
        install::record_base_sha(&kok, &"b".repeat(64));
        let plat = pemf_launcher_core::platform::current();
        let sha = "f".repeat(64);
        let manifest = format!(
            r#"{{"schema":2,"version":"9.9.9","runtimes":{{"{plat}":{{"url":"https://example.invalid/base.zip","sha256":"{sha}","size":5,"kind":"zip"}}}},"models":{{}},"model_parts":{{}}}}"#
        );
        std::fs::write(kok.join("backend.port"), port.to_string()).unwrap();
        let artakalan_ani: Arc<Mutex<Option<(bool, bool, bool)>>> = Arc::new(Mutex::new(None));
        let (ad_g, a_g, kok_g) = (ad.clone(), artakalan_ani.clone(), kok.clone());
        backend::test_kancasi::gozlemci_kur(Some(Box::new(move |k: &std::path::Path| {
            if k == kok_g {
                let eski_yerinde = install::runtime_old_dir(&kok_g).is_dir();
                let sayac_yok = install::read_runtime_attempt(&kok_g).is_none();
                *a_g.lock().unwrap() = Some((kp5_cocuk_canli_mi(&ad_g, pid), eski_yerinde, sayac_yok));
            }
        })));
        let geri = flow::GeriAlmaBilgisi { tam_takas: true, ..Default::default() };
        let t0 = std::time::Instant::now();
        let sonuc = firmware_uyumsuz_geri_al(cocuk, port, &kok, &manifest, &geri, Arc::new(Mutex::new(None)));
        let sure = t0.elapsed();
        backend::test_kancasi::gozlemci_kur(None);
        assert!(sure < std::time::Duration::from_secs(30), "süreç öldürülmedi — geri alma {sure:?} bekledi");
        let _ = sunucu.join();
        // 1) E-stop ÖNCE: STOP → yakma yoklaması → son oturum çekimi, üçü de süreç CANLIYKEN; başka istek YOK.
        assert_eq!(
            kp5_yollar(&kayit),
            vec![
                kp5_cift("POST", "/api/hardware/kapanis_durdur"),
                kp5_cift("GET", "/api/health"),
                kp5_cift("GET", "/api/auth/desktop-session")
            ],
            "geri almada istek sırası E-stop → yakma → son oturum değil"
        );
        assert!(kayit.lock().unwrap().iter().all(|(_, _, _, c)| *c), "bir istek süreç ÖLDÜKTEN sonra geldi (kill E-stop'tan önce)");
        // 2) Kill + artakalan: süreç öldü; artakalan anında süreç ölü, eski sürüm HENÜZ geri konmamış, sayaç HENÜZ yazılmamış.
        assert!(!kp5_cocuk_canli_mi(&ad, pid), "yeni sürümün backend'i öldürülmedi");
        assert_eq!(
            *artakalan_ani.lock().unwrap(),
            Some((false, true, true)),
            "(süreç canlı, runtime.old yerinde, sayaç yok) artakalan anında beklenen değil — geri alma / sayaç kill'den ÖNCE"
        );
        // 3) Döngü kırıcı sayaç bu hedef için 1 (aynı hedef 2 kez geri alınınca otomatik kurulum durur).
        assert_eq!(install::read_runtime_attempt(&kok), Some((format!("base:{sha}"), 1)), "geri alma deneme sayacı");
        // 4) Eski sürüm geri geldi, bozuk yeni kenara alınıp silindi; port dosyası (ölü backend) temizlendi.
        assert_eq!(std::fs::read(exe_yolu(&yeni)).unwrap(), b"ESKI-SURUM", "eski sürüme dönülmedi");
        assert!(!eski.exists() && !kok.join("runtime.bozuk").exists(), "geri alma artığı kaldı");
        assert!(!kok.join("backend.port").exists(), "ölü backend'in port dosyası kaldı");
        // 5) Sonuç: GeriAlindi + arayüz notu kodu + eylem söyleyen neden; geri alma hatası YOK.
        match sonuc {
            GuncellemeSonucu::GeriAlindi { sebep, geri_alma_hatasi, kod } => {
                assert_eq!(sebep, pemf_launcher_core::dil::t("rust.hata.guncellemeFirmwareUyumsuz"));
                assert!(!sebep.is_empty() && sebep != "rust.hata.guncellemeFirmwareUyumsuz", "neden metni katalogdan çözülmedi");
                assert_eq!(geri_alma_hatasi, None);
                assert_eq!(kod, Some(KOD_FIRMWARE_UYUMSUZ));
                assert_eq!(KOD_FIRMWARE_UYUMSUZ, "firmware_uyumsuz", "arayüz sözleşmesi (rtRollbackFirmware) kodu");
            }
            _ => panic!("firmware uyumsuzluğu GeriAlindi dönmedi"),
        }
        let _ = std::fs::remove_dir_all(&kok);
    }

    /// KARŞIT (L2): eski sürüm yoksa (runtime.old yok, app yedeği de yok) geri alma hatası SÖYLENİR (sessiz "dönüldü" YOK) ama E-stop →
    /// kill yine yapılır ve sayaç yine yazılır (döngü kırıcı çalışır).
    #[cfg(windows)]
    #[test]
    fn KP6_D_firmware_uyumsuz_geri_al_YEDEK_YOKSA_hata_SOYLENIR_estop_ve_sayac_YINE() {
        let _k = KP5_B1_KILIT.lock().unwrap_or_else(|e| e.into_inner());
        let (cocuk, pid, ad) = kp5_sahte_surec();
        let ln = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ln.local_addr().unwrap().port();
        let kayit: Kp5Kayit = Arc::new(Mutex::new(Vec::new()));
        let sunucu = kp5_sahte_backend(ln, ad.clone(), pid, kayit.clone());
        let kok = std::env::temp_dir().join(format!("pemf_kp6_d_fw_yok_{}_{port}", std::process::id()));
        let _ = std::fs::remove_dir_all(&kok);
        let exe = install::backend_path(&kok);
        std::fs::create_dir_all(exe.parent().unwrap()).unwrap();
        std::fs::write(&exe, b"YENI-SURUM").unwrap();
        install::record_base_sha(&kok, &"b".repeat(64));
        let plat = pemf_launcher_core::platform::current();
        let sha = "e".repeat(64);
        let manifest = format!(
            r#"{{"schema":2,"version":"9.9.9","runtimes":{{"{plat}":{{"url":"https://example.invalid/base.zip","sha256":"{sha}","size":5,"kind":"zip"}}}},"models":{{}},"model_parts":{{}}}}"#
        );
        let geri = flow::GeriAlmaBilgisi { app_yedegi: true, app_degisti: true, ..Default::default() };
        let sonuc = firmware_uyumsuz_geri_al(cocuk, port, &kok, &manifest, &geri, Arc::new(Mutex::new(None)));
        let _ = sunucu.join();
        assert_eq!(kp5_yollar(&kayit).first(), Some(&kp5_cift("POST", "/api/hardware/kapanis_durdur")), "E-stop yapılmadı");
        assert!(!kp5_cocuk_canli_mi(&ad, pid), "backend öldürülmedi");
        assert_eq!(install::read_runtime_attempt(&kok), Some((format!("base:{sha}"), 1)), "yedek yokken sayaç yazılmadı");
        match sonuc {
            GuncellemeSonucu::GeriAlindi { geri_alma_hatasi, kod, .. } => {
                let h = geri_alma_hatasi.expect("yedek yokken geri alma hatası SÖYLENMEDİ (sessiz 'eski sürüme dönüldü')");
                assert!(h.contains(&pemf_launcher_core::dil::t("rust.kurulum.appYedegiYok")), "{h}");
                assert_eq!(kod, Some(KOD_FIRMWARE_UYUMSUZ));
            }
            _ => panic!("GeriAlindi dönmedi"),
        }
        assert_eq!(std::fs::read(&exe).unwrap(), b"YENI-SURUM", "yedek yokken canlı ağaca dokunuldu");
        let _ = std::fs::remove_dir_all(&kok);
    }
}
