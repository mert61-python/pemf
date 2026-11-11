// Author: mertaygn, cglrgrkn
// KP-4 A1 (Y257 c, sahip 08.11): Tauri kabuğu — `kapsam_siniflari.json`'daki S sınıfı (test edilemez: pencere / WebView / Tauri
// çalışma zamanı / gerçek platform API'si / UAC / görünür süreç) üst düzey işlevler main.rs'ten DEĞİŞTİRİLMEDEN buraya taşındı.
// Bu dosya AYRI bir modül DEĞİLDİR: main.rs onu `include!` ile AYNI kök modüle katar (görünürlük, yol ve Tauri komut kaydı
// AYNEN). Tek fark kaynak dosya adıdır → cargo-llvm-cov bu dosyayı `--ignore-filename-regex` ile ölçümden GEREKÇELİ dışlar
// (CI `tests.yml` + yerel `kapsam_cargo.sh`). Sayan kapı `tests/test_KP3_main_rs_kapsam_siniflari.py`: S işlevleri YALNIZ bu
// dosyada, burada S olmayan işlev YOK, S sayısı SABİT, her S gerekçeli, güvenlik / güncelleme kararı S OLAMAZ.
// ⚠️ Buraya YENİ işlev ekleme: test edilebilen mantık main.rs / çekirdekte kalır; buraya yalnız ince kabuk girer (kapı sayar).

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
    // UI'ya donen adres; pencere URL'si `open_app_window` icinde kurulu profil listesiyle kurulur.
    _url: &str,
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
    open_app_window(app, port);
}

/// OTURUM DEVRİ (E-ÖZELLİĞİ ORTAK SÖZLEŞMESİ): client'ın Supabase oturumunu, backend ayağa
/// kalktıktan SONRA ama uygulama penceresi AÇILMADAN ÖNCE backend'e ver.
///
/// SIRA KRİTİK: pencere önce açılırsa uygulama kendi giriş ekranını çoktan çizmiş olur ve
/// kullanıcı İKİNCİ kez giriş yapar (sözleşme: "Çift giriş YOK").
/// `PEMF_REQUIRE_AUTH=1` verilmiş olsa da loopback istekleri backend'de muaftır
/// (`apps/backend/servers/auth.py::is_local_request`) → ek jeton gerekmez.
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

fn open_app_window(app: &tauri::AppHandle, port: u16) {
    // Kurulu profiller ACILIS ANINDA kayittan okunur (kaldirma/ekleme sonrasi taze).
    let installed = install::read_installed_profiles(&install::default_install_root(&home_dir()));
    let busted = uygulama_url(port, &installed);
    let url = &busted;

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
        // LN L9 · D2.E01 (WebView2 kolu) · İG-6.20: indirmeler AÇIK kararla (bkz. `indirme_karari`).
        .on_download(move |_webview, olay| indirme_olayi(olay, port))
        .build();
    if built.is_err() {
        // Pencere açılamazsa (nadir) → uygulamayı tarayıcıda göster; client yine açık kalır (fail-safe).
        let _ = backend::open_browser(url);
    }
}

/// `on_download` işleyicisi (`true` = WebView2 indirsin). `Finished` yalnız başarıyı günlüğe yazar — dosya ADI / yolu yazılmaz
/// (rapor / yedek adları hasta adı taşıyabilir).
fn indirme_olayi(olay: tauri::webview::DownloadEvent<'_>, port: u16) -> bool {
    match olay {
        tauri::webview::DownloadEvent::Requested { url, destination: _ } => match indirme_karari(url.as_str(), port) {
            IndirmeKarari::Izin => true,
            IndirmeKarari::TarayicidaAc => {
                let _ = backend::open_browser(url.as_str());
                false
            }
            IndirmeKarari::Reddet => {
                eprintln!("[indirme] reddedildi (sema {})", url.scheme());
                false
            }
        },
        tauri::webview::DownloadEvent::Finished { success, .. } => {
            eprintln!("[indirme] bitti: basari={success}");
            true
        }
        _ => true,
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

/// ⚠️ 2026-10-18 (sahip: "aynı sorunlu başka işlem de olabilir detaylı incele"): bu komut `async` DEĞİLDİ → pencere iş parçacığında
/// koşuyordu ve HER açılışta `yarim_takasi_kurtar` → `olu_sahne_agaclarini_temizle` yarım güncellemeden kalan `runtime.new` /
/// `runtime.bozuk` ağaçlarını (~1,2 GB, binlerce dosya) `remove_dir_all` ile siliyor, geri alma yolunda yeniden adlandırıyordu →
/// kesilen bir güncellemeden sonra açılış (pencere) saniyelerce donar. `firewall_durumu` ile AYNI desen.
#[tauri::command]
async fn detect_environment() -> Environment {
    tauri::async_runtime::spawn_blocking(detect_environment_blocking)
        .await
        // Görev çökerse kurtarmasız yerel özet (kurtarma bir sonraki açılışta yeniden denenir).
        .unwrap_or_else(|_| ortam_ozeti(&install::default_install_root(&home_dir())))
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
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.manifestGorevCoktu", &[("e", &e.to_string())]))?
}

/// I18N (Y161): arayüzün açılış dili + İngilizce bayrağı. Anlık iş (kilitli değişken okuma). Etkin dil açılışta `dil::baslat()` ile
/// kurulur: bayrak kapalıyken HER ZAMAN tr; açıkken uygulamanın seçimi (`arayuz_dili.json`) > Windows görüntüleme dili > tr.
#[tauri::command]
fn dil_bilgisi() -> serde_json::Value {
    serde_json::json!({ "dil": pemf_launcher_core::dil::etkin().kod(), "enAcik": pemf_launcher_core::dil::I18N_EN_ACIK })
}

/// I18N: arayüzdeki TR / EN düğmesi Rust iletilerinin dilini de ayarlar (bayrak kapalıyken tr kalır). Anlık iş. Dönüş: etkin dil.
#[tauri::command]
fn dil_ayarla(kod: String) -> String {
    use pemf_launcher_core::dil;
    match dil::Dil::coz(&kod) {
        Some(d) => dil::ayarla(d).kod().to_string(),
        None => dil::etkin().kod().to_string(),
    }
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
        return Err(pemf_launcher_core::dil::t_ile("rust.hata.indirmeAdresiIzinsiz", &[("url", &url.to_string())]));
    }
    // Derinlik-savunması: open_browser artık rundll32 kullansa da (kabuk yok), manifest-türevi
    // URL'yi asla riske atma — kabuk-metakarakteri, kontrol-karakteri veya boşluk içeren URL'yi
    // reddet. Meşru GitHub/Vercel indirme URL'lerinde bunlar bulunmaz.
    if url.len() > 2048 || url.chars().any(|c| c.is_control() || "&|^<>\"'`{} \t\r\n".contains(c)) {
        return Err(pemf_launcher_core::dil::t("rust.hata.indirmeAdresiGecersizKarakter"));
    }
    backend::open_browser(&url).map_err(|e| e.to_string())
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
    aktif_seans_kapisi_portla(root, install::DEFAULT_PORT)
}

/// Diskteki kurulum manifest'e göre bayat mı? (AĞA ÇIKMAZ — manifest UI'da zaten çekilmiştir.)
///
/// SAHİP KARARI 2026-08-08: kullanıcı "Onar"a basmasın; client açılışta kendi anlasın.
///
/// 2026-10-18: diske kayıt yazar / okur (`adopt_unknown_models`, `pending_updates`) ve açılışta + uygulama açıkken PERİYODİK
/// (`recheckUpdates`) çağrılır → pencere iş parçacığında koşmasın (yavaş disk / virüs taraması pencereyi dondururdu).
#[tauri::command]
async fn check_runtime_update(manifest_raw: String) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || check_runtime_update_blocking(manifest_raw))
        .await
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.guncellemeDenetimiGorevCoktu", &[("e", &e.to_string())]))?
}

/// GÜNCELLEME ONAYI (sahip Y253 / Y254, 2026-11-06 — SAHİP KARARI 2026-08-08'i değiştirir): onay penceresinin içeriği ve kararı
/// (`yok` / `sor` / `onayli` / `zorunlu`). TEK pencere: başlatıcı X → Y + uygulama A → B + bağımlılık + kurulu profil paketleri, inecek
/// toplam boyut, kısa sürüm notu. Karar çekirdekte (`guncelleme_onayi::ozet`, testli). AĞA ÇIKMAZ (manifest arayüzde çekildi); diske
/// yalnız `adopt_unknown_models` kaydı ve yaşını aşmış onay kaydının silinmesi → pencere iş parçacığında koşmaz.
#[tauri::command]
async fn guncelleme_ozeti(manifest_raw: String) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || guncelleme_ozeti_blocking(manifest_raw))
        .await
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.guncellemeDenetimiGorevCoktu", &[("e", &e.to_string())]))?
}

/// GÜNCELLEME ONAYI: taşınan onayla akış tamamlandı → kaydı sil (bir daha taşınmasın).
#[tauri::command]
async fn guncelleme_onayini_temizle() -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(|| guncelleme_onayi::temizle(&install::default_install_root(&home_dir())))
        .await
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.guncellemeGorevCoktu", &[("e", &e.to_string())]))
}

/// GÜNCELLEME ONAYI · GÜVENLİK DEĞİŞMEZİ: etkin seans (`/api/health` `sessionActive`), kart yazılımı yükleme ya da yanıtsız backend
/// varken yeniden başlatma YAPILMAZ. Onaylı / zorunlu akış kurulumdan ÖNCE bunu yoklar, engel kalkana dek bekler ve EKRANDA söyler.
/// Kapı `aktif_seans_kapisi` (TEK yer — `apply_runtime_update` / `apply_self_update` da onu kullanır; bu yoklama onların YERİNE değil,
/// ÖNÜNDE). Görev çökerse "engel VAR" (fail-safe: bilinmeyen durumda yeniden başlatma yok).
#[tauri::command]
async fn guncelleme_engeli() -> serde_json::Value {
    tauri::async_runtime::spawn_blocking(|| guncelleme_engeli_json(aktif_seans_kapisi(&install::default_install_root(&home_dir()))))
        .await
        .unwrap_or_else(|e| guncelleme_engeli_json(Err(e.to_string())))
}

/// GÜNCELLEME ONAYI: katman güncellemesinden sonra AÇIK uygulama penceresini önbellek kırıcılı URL'ye yönlendir (eski arayüz paketi
/// yeni backend'le kalmasın). Pencere yoksa `false` (açmayı `open_app_window` yapar).
fn uygulama_penceresini_yenile(app: &tauri::AppHandle, port: u16) -> bool {
    let Some(win) = app.get_webview_window("app") else { return false };
    let kurulu = install::read_installed_profiles(&install::default_install_root(&home_dir()));
    match uygulama_url(port, &kurulu).parse::<tauri::Url>() {
        Ok(u) => win.navigate(u).is_ok(),
        Err(_) => false,
    }
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
///
/// 2026-10-18: önbellekteki yarım indirme dosyalarını SİLER — pencere iş parçacığında koşmasın (bkz. `firewall_durumu`).
#[tauri::command]
async fn discard_pending(manifest_raw: Option<String>) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || discard_pending_blocking(manifest_raw))
        .await
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.temizlikGorevCoktu", &[("e", &e.to_string())]))?
}

/// UI açılışta sorar: bu süreç "güncelleniyor" bilgilendirme penceresi mi? (normal açılışta false)
#[tauri::command]
fn guncelleme_modu() -> bool {
    GUNCELLEME_MODU.load(std::sync::atomic::Ordering::Relaxed)
}

/// Bilgilendirme penceresini launcher exe'sinin %TEMP%'e alınmış FARKLI ADLI kopyasından başlat.
/// Neden kopya: NSIS'in "uygulama çalışıyor" denetimi `PEMFVetClient.exe` ADINA bakar ve sessiz
/// kurulumda onu öldürür; farklı adlı kopya ne öldürülür ne de kurulum exe'sinin kilidini tutar.
/// Başarısızlık güncellemeyi DURDURMAZ (eski davranışa düşer). Kopyayı batch siler.
/// 🔴 DENETİM 2026-09-06 (bulgu #6): eskiden `Option` döndürüyordu — kopyalama/başlatma hatası
/// `.ok()?` ile None'a çöküyor ve HİÇBİR yere yazılmıyordu; batch `:sil` bloğunu sessizce atlıyor,
/// relauncher günlüğü pencere var/yok BİREBİR aynı çıkıyordu. Gerçekçi tetik: %TEMP%'e kopyalanan
/// farklı adlı imzasız exe = Defender ASR / AppLocker hedefi → yönetilen makinede HER güncellemede.
/// Artık SEBEP döner; çağıran onu yardımcının günlüğüne yazar. Akış değişmez: hata güncellemeyi
/// DURDURMAZ (eski davranışa düşer).
#[cfg(windows)]
fn guncelleme_penceresini_ac(sfx: &str) -> Result<std::path::PathBuf, String> {
    let exe = std::env::current_exe().map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.exeYoluOkunamadi", &[("e", &e.to_string())]))?;
    let kopya = std::env::temp_dir().join(format!("PEMFVetClient-Guncelleme-{sfx}.exe"));
    let _ = std::fs::remove_file(&kopya);
    std::fs::copy(&exe, &kopya).map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.kopyalanamadi", &[("yol", &kopya.display().to_string()), ("e", &e.to_string())]))?;
    // Konsol-penceresi kapısı (core/tests/konsol_penceresi.rs): her spawn CREATE_NO_WINDOW taşır.
    // Kopya GUI alt-sisteminde (Tauri) olduğundan bayrak davranışı değiştirmez, kuralı korur.
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    std::process::Command::new(&kopya)
        .arg(GUNCELLEME_EKRANI_ARG)
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()
        .map_err(|e| {
            let (yol, e) = (kopya.display().to_string(), e.to_string());
            pemf_launcher_core::dil::t_ile("rust.hata.baslatilamadi", &[("yol", &yol), ("e", &e)])
        })?;
    Ok(kopya)
}

/// Yardımcı batch'i (güncelleme relauncher'ı / kaldırıcı) başlatan TEK yol.
///
/// 🔴 DENETİM 2026-09-06 (bulgu #2): `Command::new("cmd.exe").arg("/c").arg(&bat)` %TEMP% yolunda
/// `&` ya da `^` varsa batch'i HİÇ BAŞLATMIYORDU — ve %TEMP%'in tek değişkeni Windows kullanıcı
/// adıdır ("Vet & Co", "Ali^Veli" yerel hesap adında YASAK DEĞİL). cmd'nin /C tırnak-soyma kuralı
/// komut satırında özel karakter görünce dış tırnakları soyar, yol `&`'de bölünür → cmd rc=1,
/// spawn Ok döner, batch'in kendi günlüğü İLK satırı olduğu için log dosyası bile oluşmaz: o klinikte
/// güncelleme VE kaldırma kalıcı ölü, sıfır kanıt. ÖLÇÜLDÜ (6 dizin, üretim bayraklarıyla):
///     /c "<yol>"        → "Vet & Co" rc=1 iz=YOK · "Ali^Veli" rc=1 iz=YOK · diğer 4 tamam
///     /S /C ""<yol>""   → 6/6 tamam
/// `/S` cmd'yi "ilk ve son tırnağı soy" kuralına zorlar; iç tırnak çifti korunur, yol bölünmez.
/// Mevcut davranışsal kapı geliştiricinin düz %TEMP%'inde koşuyor ve spawn'ı satır içinde yeniden
/// yazıyordu → kör kalmıştı; artık kapı BU yardımcıyı metakarakterli dizinlerde çağırır.
///
/// Erken-ölüm kapısı: batch'in ilk işi en az ~1 sn uyur (`ping -n 2` / `ping -n 6`); 300 ms içinde
/// BAŞARISIZ çıkmışsa cmd komut satırını ayrıştıramamış demektir → sessiz kalma, Err döndür ki
/// çağıran (`apply_self_update`) işareti temizleyip kullanıcıya söylesin. Hızlı ve BAŞARILI çıkış
/// (kod 0) hata değildir.
#[cfg(windows)]
fn yardimci_batch_baslat(bat: &std::path::Path) -> Result<std::process::Child, String> {
    use std::os::windows::process::CommandExt;
    let yol = bat.to_str().ok_or_else(|| pemf_launcher_core::dil::t("rust.hata.yardimciBatchYoluUtf8"))?;
    if yol.contains('"') || yol.contains('\r') || yol.contains('\n') {
        return Err(pemf_launcher_core::dil::t("rust.hata.yardimciBatchYoluGuvensiz"));
    }
    // ⚠️ stdio NULL (2026-09-06): ayrık yardımcı ebeveynin tutamaçlarını DEVRALMAMALI. Launcher
    // GUI olduğundan üretimde zaten konsol yok; ama `cargo test`/CI altında test ikilisinin stdout'u
    // BORUDUR ve devralınan boru, batch zincirinden sağ kalan bir süreçte (ör. `start x.bat` → `cmd /K`)
    // EOF'u sonsuza dek erteler → testi çağıran süreç ASILIR (ölçüldü: iki yetim `cmd /K`, Python
    // `communicate()` bekliyordu). Null stdio ile yardımcının çocukları boruyu hiç görmez.
    let mut cocuk = std::process::Command::new("cmd.exe")
        .raw_arg(format!("/S /C \"\"{yol}\"\""))
        .creation_flags(YARDIMCI_BATCH_BAYRAKLARI)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.yardimciBaslatilamadi", &[("yol", &yol.to_string()), ("e", &e.to_string())]))?;
    std::thread::sleep(std::time::Duration::from_millis(300));
    if let Ok(Some(durum)) = cocuk.try_wait() {
        if !durum.success() {
            let _ = std::fs::remove_file(bat);
            let kod = durum.code().map(|k| k.to_string()).unwrap_or_else(|| pemf_launcher_core::dil::t("rust.hata.yok"));
            let yol = bat.display().to_string();
            return Err(pemf_launcher_core::dil::t_ile("rust.hata.yardimciHemenSonlandi", &[("kod", &kod), ("yol", &yol)]));
        }
    }
    Ok(cocuk)
}

#[cfg(windows)]
fn spawn_update_relauncher(installer: &std::path::Path, pencere: Option<&std::path::Path>) -> Result<(), String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let exe_s = exe.to_str().ok_or_else(|| pemf_launcher_core::dil::t("rust.hata.launcherYoluUtf8"))?;
    let inst_s = installer.to_str().ok_or_else(|| pemf_launcher_core::dil::t("rust.hata.setupYoluUtf8"))?;
    let pencere_s = match pencere {
        Some(p) => Some(p.to_str().ok_or_else(|| pemf_launcher_core::dil::t("rust.hata.pencereYoluUtf8"))?),
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

    // Tek yol: `yardimci_batch_baslat` (bulgu #2 — `/S /C ""…""` + erken-ölüm kapısı).
    yardimci_batch_baslat(&bat)?;
    Ok(())
}

/// Kayıtlı NSIS uninstaller'ı, launcher ÇIKTIKTAN sonra çalışacak şekilde DETACHED başlat (self-update
/// relauncher'la aynı desen). Launcher exe kilidi kalkınca uninstaller $INSTDIR'ı (launcher+runtime) siler.
#[cfg(windows)]
fn spawn_uninstaller_detached(uninstaller: &std::path::Path) -> Result<(), String> {
    let unins_s = uninstaller.to_str().ok_or_else(|| pemf_launcher_core::dil::t("rust.hata.kaldiriciYoluUtf8"))?;
    let script = build_uninstall_script(unins_s)?;
    let bat = std::env::temp_dir().join("pemf_uninstall.bat");
    std::fs::write(&bat, script).map_err(|e| e.to_string())?;

    // Tek yol: `yardimci_batch_baslat` (bulgu #2 — relauncher ile AYNI tuzak, aynı düzeltme).
    yardimci_batch_baslat(&bat)?;
    Ok(())
}

/// GÜVENLİK DUVARI DURUMU — mobil uygulama kliniğe bağlanabiliyor mu?
///
/// ⚠️ DENETİM 2026-08-09 (Tier 1): backend `0.0.0.0:8000`'i dinliyor ama launcher yolunda gelen
/// kurulumda inbound kural HİÇ oluşturulmuyordu (client kurulumu `currentUser` → NSIS
/// yükseltilmiş değil; kuralları yalnız ESKİ servis kurulumu ekliyor). Sonuç: yayınlanan mobil
/// APK klinik WiFi'sinde cihaza HİÇ bağlanamıyor ve sebebi hiçbir yerde yazmıyor.
///
/// ⚠️ SAHİP BİLDİRİMİ 2026-10-18 ("güncelleme kontrol ediliyor yazarken pencere bloklanıyor hareket ettiremiyorum"): bu komut
/// `async` DEĞİLDİ → Tauri senkron komutu OLAY DÖNGÜSÜ (pencere) iş parçacığında koşturur; gövde `powershell` başlatıp
/// `Get-NetFirewallApplicationFilter` ile TÜM kuralları tarıyor (bu makinede 713 kural: ölçüldü 2,2–2,4 sn, soğuk açılışta
/// daha uzun). Launcher açılışta (`refreshEnv` → `firewallKontrol(false)`) ve backend başlayınca bunu çağırıyordu → pencere
/// o süre sürüklenemiyor / tıklamalara yanıt vermiyordu. `fetch_profiles` ile AYNI desen: `async fn` + `spawn_blocking`.
#[tauri::command]
async fn firewall_durumu() -> serde_json::Value {
    // Görev çökerse boş nesne: arayüz uyarı göstermez (okunamayan durum ENGEL sayılmaz — firewall.rs fail-open notu).
    tauri::async_runtime::spawn_blocking(firewall_durumu_blocking).await.unwrap_or_else(|_| serde_json::json!({}))
}

fn firewall_durumu_blocking() -> serde_json::Value {
    use pemf_launcher_core::firewall::{api_portu, durum_icin, Durum};
    // ⚠️ backend exe YOLUNU ver: Windows'un KENDİ otomatik izni de sayılsın. Yol verilmezse
    // denetim yalnız bizim adlandırılmış kurallarımıza bakar ve Windows zaten izin vermiş
    // olsa bile "engelli" der → kullanıcı GEREKSİZ bir UAC istemine itilir (sahip bildirimi
    // 2026-08-11: "eskiden buna gerek olmadan buluyordu").
    // D5 I-1: port = çocuğun GERÇEK portu (`backend.port`; 8000 doluysa 8001+) — kural onu kapsamalı.
    let root = install::default_install_root(&home_dir());
    let exe = install::backend_path(&root);
    let d = durum_icin(Some(&exe), api_portu(&root));
    serde_json::json!({
        // AÇIKÇA engellenmiş (Block kuralı) — her zaman uyar, kalıcı engel.
        "engelli": d == Durum::Engelli,
        // Henüz kural yok — backend HİÇ dinlemediyse NORMAL. Arayüz bunu yalnız backend
        // çalıştıktan SONRA uyarıya çevirir (bkz. index.html::firewallKontrol).
        "kural_yok": d == Durum::KuralYok,
        "gereksiz": d == Durum::Gereksiz,
    })
}

/// PowerShell betiğini UAC ile YÜKSELTEREK çalıştırır (firewall / paylaşım / kaldırma temizliği admin ister). ⚠️ Base64 taşıma
/// KASITLI: betik kullanıcı-etkili yollar içerebilir; tırnak/kaçış katmanları arasında bozulmasın (bkz. firewall.rs enjeksiyon
/// notu). Konsol penceresi açılmaz. DEV-D5.b: kaldırma temizliği (`silme_betigi`) de bunu kullanır — kod günlüğe, sonuç yutulur.
/// D3 T-g: yükseltilmiş betiğin ÇIKIŞ KODUNU döndürür (`-PassThru`); UAC reddi / yükseltme
/// başlatılamadı → `paylasim::KOD_UAC_REDDEDILDI` (1223 = ERROR_CANCELLED). D5 J-3: güvenlik duvarı "İzin ver" yolu da bunu kullanır.
/// D5 J-3 tur 3: çıkış kodu boşsa → `KOD_YUKSELTILMIS_CIKIS_KODU_YOK` (fail-closed; davranışı gölge PowerShell'le ölçen kapı
/// `tests/test_launcher_izin_ver_sarmalayici_GOLGE_cikis_kodu_D5_J3.py`).
#[cfg(windows)]
fn ps_yukselterek_kos_kodlu(betik: &str) -> Result<i32, String> {
    let b64 = ps_b64(betik);
    let arg = format!(
        "try {{ $p = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden -ErrorAction Stop \
         -ArgumentList '-NoProfile','-NonInteractive','-EncodedCommand','{b64}' }} catch {{ exit {red} }}; \
         if ($null -eq $p -or $null -eq $p.ExitCode) {{ exit {bos} }}; exit $p.ExitCode",
        red = pemf_launcher_core::paylasim::KOD_UAC_REDDEDILDI,
        bos = KOD_YUKSELTILMIS_CIKIS_KODU_YOK,
    );
    let cikti = pemf_launcher_core::platform::gizli_komut("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &arg])
        .output()
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.yukseltmeBaslatilamadi", &[("e", &e.to_string())]))?;
    Ok(cikti.status.code().unwrap_or(pemf_launcher_core::paylasim::KOD_UAC_REDDEDILDI))
}

/// D3 T-g · Y182 (S-YLI.1): bu hesap makinedeki hasta verisine erişemiyor mu (başka hesabın) — arayüz paylaşım kartını gösterir.
/// Dosya sistemi + hesap araması → ayrı iş parçacığı. #22 (Y275): görev çökerse BELİRSİZ yanıtı (kart "paylaşım gerekli olabilir"
/// der) — eskiden boş nesne dönüyor ve kart hiç gösterilmiyordu.
#[tauri::command]
async fn paylasim_durumu() -> serde_json::Value {
    tauri::async_runtime::spawn_blocking(paylasim_durumu_blocking)
        .await
        .unwrap_or_else(|_| pemf_launcher_core::paylasim::belirsiz_yaniti())
}

fn paylasim_durumu_blocking() -> serde_json::Value {
    use pemf_launcher_core::paylasim::{arayuz_yaniti, durum_icin};
    arayuz_yaniti(durum_icin(|k| std::env::var(k).ok()))
}

/// D3 T-g · Y182: paylaşılan grubu TEK SEFERLİK yönetici adımıyla (UAC) kur — yalnız kullanıcının düğmeye basmasıyla.
/// Hesap kimliği YÜKSELTİLMEMİŞ bu süreçten okunur (yükseltilmiş süreç başka bir yönetici hesabıyla açılabilir).
#[tauri::command]
async fn paylasim_kur() -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(paylasim_kur_blocking)
        .await
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.paylasimGorevCoktu", &[("e", &e.to_string())]))?
}

fn paylasim_kur_blocking() -> Result<serde_json::Value, String> {
    #[cfg(not(windows))]
    { return Ok(serde_json::json!({ "status": "gereksiz" })); }
    #[cfg(windows)]
    {
        use pemf_launcher_core::dil::{t, t_ile};
        use pemf_launcher_core::paylasim::{hata_anahtari, kurma_betigi, surec_hesabi_sid, KOD_TAMAM};
        let sid = surec_hesabi_sid().ok_or_else(|| t("rust.hata.paylasimHesapOkunamadi"))?;
        let betik = kurma_betigi(&sid, &t("rust.paylasim.grupAciklamasi")).ok_or_else(|| t("rust.hata.paylasimHesapTuru"))?;
        match ps_yukselterek_kos_kodlu(&betik)? {
            KOD_TAMAM => Ok(serde_json::json!({ "status": "ok" })),
            kod => Err(t_ile(hata_anahtari(kod), &[("kod", &kod.to_string())])),
        }
    }
}

/// 2026-10-18: UAC istemi + yükseltilmiş PowerShell BEKLENİR — pencere iş parçacığında koşmasın (bkz. `firewall_durumu`).
#[tauri::command]
async fn firewall_kurali_ekle() -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(firewall_kurali_ekle_blocking)
        .await
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.guvenlikDuvariGorevCoktu", &[("e", &e.to_string())]))?
}

fn firewall_kurali_ekle_blocking() -> Result<serde_json::Value, String> {
    #[cfg(not(windows))]
    { return Ok(serde_json::json!({ "status": "gereksiz" })); }
    #[cfg(windows)]
    {
        use pemf_launcher_core::firewall::{api_portu, ekleme_betigi};
        let root = install::default_install_root(&home_dir());
        let exe = install::backend_path(&root);
        if !exe.exists() {
            return Err(pemf_launcher_core::dil::t("rust.hata.backendKurulDegil"));
        }
        // Ortak yardımcı (base64 + UAC) — paylaşım kurulumu da aynısını kullanır, kopya yok.
        // D5 I-1: kural İÇERİKLE + çocuğun GERÇEK portu (8000'e sabit değil).
        // D5 J-3: yükseltilmiş betiğin ÇIKIŞ KODU okunur. Eskiden `ps_yukselterek_kos` (`Start-Process -Wait`, `-PassThru` yok)
        // yalnız UAC reddini görüyordu: içerideki `New-NetFirewallRule` düşse de arayüz "tamam" deyip uyarıyı kapatıyordu.
        izin_ver_sonucu(ps_yukselterek_kos_kodlu(&ekleme_betigi(&exe, api_portu(&root))))
    }
}

/// OFF-SITE YEDEK HEDEFİ — durum (2026-08-09 denetimi, Tier 1).
///
/// ⚠️ Yedekler bugüne kadar hasta verisiyle AYNI DİSKE alınıyordu; disk arızasında ya da fidye
/// yazılımında veri VE yedek birlikte gidiyordu. Backend `PEMF_BACKUP_DIR` desteğini zaten
/// taşıyordu ama hiçbir yerde ayarlanmadığı için özellik sahada HİÇ çalışmadı.
///
/// 2026-10-18: yazılabilirlik denetimi yedek klasörüne DOSYA YAZAR — çıkarılmış USB / yanıt vermeyen ağ paylaşımında saniyelerce
/// asılabilir; açılışta pencere iş parçacığında koşmasın (bkz. `firewall_durumu`). Görev çökerse `null` → arayüz not göstermez.
#[tauri::command]
async fn yedek_hedefi_durumu() -> serde_json::Value {
    tauri::async_runtime::spawn_blocking(yedek_hedefi_durumu_blocking).await.unwrap_or(serde_json::Value::Null)
}

/// LN L7 · D2.33 / D2.76: kaldırma diyaloğunun gösterdiği KORUNAN hasta verisi konumu — launcher'ın backend'e verdiği kök
/// (`veri_koku.txt`); kayıt yoksa makine-geneli kök VARSA o, yoksa `%APPDATA%\PEMF_GUI`. Öteki aday da diskteyse `diger`
/// (eski sürümün / başka Windows hesabının kayıtları). Eskiden arayüz sabit `%APPDATA%\PEMF_GUI` diyordu — makine-geneli kökte
/// yanlış klasör. Dosya sistemi okur → ayrı iş parçacığı; görev çökerse `null` (arayüz yedek metni gösterir).
#[tauri::command]
async fn kaldirma_veri_konumu() -> serde_json::Value {
    tauri::async_runtime::spawn_blocking(kaldirma_veri_konumu_blocking).await.unwrap_or(serde_json::Value::Null)
}

/// Klasör seçtir ve doğrula. Tauri dialog eklentisi YOK (yeni bağımlılık istemiyoruz) →
/// Windows'un kendi klasör seçicisi PowerShell üzerinden açılır.
///
/// 2026-10-18: klasör seçici penceresi kapanana dek PowerShell BEKLENİR — launcher penceresi o süre donmasın (bkz. `firewall_durumu`).
#[tauri::command]
async fn yedek_hedefi_sec() -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(yedek_hedefi_sec_blocking)
        .await
        .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.klasorSeciciGorevCoktu", &[("e", &e.to_string())]))?
}

fn yedek_hedefi_sec_blocking() -> Result<serde_json::Value, String> {
    #[cfg(not(windows))]
    { return Err(pemf_launcher_core::dil::t("rust.hata.platformDesteklenmiyor")); }
    #[cfg(windows)]
    {
        // `OutputEncoding=UTF8` (bulgu #3, bitişik): Türkçe karakterli yol (ör. "D:\Yedek Çekmece")
        // varsayılan OEM kod sayfasında bozuluyor → sonraki "yazılamıyor" hatası yanlış teşhis.
        // Pencere AÇIKLAMASI kullanıcıya görünür → katalogdan (tek tırnak PowerShell'de iki tırnakla kaçışlanır).
        let betik = format!(
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; \
            Add-Type -AssemblyName System.Windows.Forms; \
            $d = New-Object System.Windows.Forms.FolderBrowserDialog; \
            $d.Description = '{}'; \
            if ($d.ShowDialog() -eq 'OK') {{ $d.SelectedPath }}",
            pemf_launcher_core::dil::t("rust.klasorSecici.aciklama").replace('\'', "''")
        );
        // Konsol penceresi AÇMADAN (bkz. platform::gizli_komut). Açılan klasör-seçici bir
        // WinForms diyaloğudur; onu başlatan kabuğun görünmesi gerekmez.
        let o = pemf_launcher_core::platform::gizli_komut("powershell")
            .args(["-NoProfile", "-STA", "-Command", betik.as_str()])
            .output()
            .map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.klasorSeciciAcilamadi", &[("e", &e.to_string())]))?;
        // Bulgu #3: çıkış kodu + stderr OKUNUR; boş stdout ancak PowerShell başarılıysa "iptal"dir.
        let yol = match klasor_secici_sonucu(o.status.success(), o.status.code(), &o.stdout, &o.stderr)? {
            Some(y) => y,
            None => return Ok(serde_json::json!({ "status": "iptal" })),
        };
        let root = install::default_install_root(&home_dir());
        // Veri kökü makine-geneli olabilir; kıyaslamayı GERÇEK hedefle yap.
        let veri = install::cozulmus_veri_dizini(|k| std::env::var(k).ok()).unwrap_or(root.clone());
        // LN L8 · S-E2I.4: hedef bir PEMF kökünün içinde olamaz (kaldırma / tam temizlik siler); `\\?\` / `\\localhost\C$`
        // biçimleri yerel yola çevrilerek denetlenir.
        let kokler = install::pemf_kokleri(|k| std::env::var(k).ok(), &home_dir(), &root);
        let bilgisayar = std::env::var("COMPUTERNAME").unwrap_or_default();
        install::yedek_hedefi_gecerli_mi(std::path::Path::new(&yol), &veri, &kokler, &bilgisayar)?;
        install::backup_dir_yaz(&root, &yol).map_err(|e| pemf_launcher_core::dil::t_ile("rust.hata.kaydedilemedi", &[("e", &e.to_string())]))?;
        Ok(serde_json::json!({ "status": "ok", "yol": yol }))
    }
}

fn main() {
    let ctx = tauri::generate_context!();
    // I18N: etkin dil (Rust iletileri + arayüzün açılış dili) — bayrak kapalıyken tr. Okuma hatası açılışı DURDURMAZ (tr'de kalır).
    pemf_launcher_core::dil::baslat();
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
            kaldirma_veri_konumu,
            firewall_kurali_ekle,
            paylasim_durumu,
            paylasim_kur,
            fetch_profiles,
            install_and_launch,
            start_installed,
            repair,
            remove_profiles,
            check_runtime_update,
            apply_runtime_update,
            prefetch_runtime_update,
            guncelleme_ozeti,
            guncelleme_onayini_kaydet,
            guncelleme_onayini_temizle,
            guncelleme_engeli,
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
            guncelleme_modu,
            dil_bilgisi,
            dil_ayarla
        ])
        .on_window_event(|window, event| {
            // Pencere kapanınca backend'i BIRAKMA: yetim süreç portu tutar ve sonraki açılışta
            // "port meşgul" hatası verir. AMA öldürmeden ÖNCE bobinleri GÜVENE AL (TIBBİ GÜVENLİK):
            // child.kill() sinyal göndermez → backend'in bobin-STOP graceful'ı çalışmaz, seans
            // sürerken pencere kapatılırsa bobinler hastanın üzerinde açık kalır. E-stop ile durdur.
            //
            // LN L3 · Y82 (sahip): ANA pencere kapanırken (süreç çıkacak) bu oturumun backend'i STM32 firmware'i YAKIYORSA kapanış
            // ERTELENİR: ana pencerede uyarı (TR / EN), yakma bitince pencere KENDİLİĞİNDEN kapanır (azami `YAKMA_BEKLEME_AZAMI`).
            // STOP / ACİL DURDUR bu kapıya BAĞLI DEĞİL — kapanışın STOP'u Destroyed'da her zaman kill'den ÖNCE gider (Ö.4-Y8); yakma
            // penceresinde backend bobin başlatmayı zaten reddeder. Yoklama yalnız TRACKED backend'de ve en çok 0,8 sn.
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    if let Some(state) = window.app_handle().try_state::<AppState>() {
                        let port = state.proc.lock().unwrap().as_ref().map(|(_, p)| *p);
                        let asama = state.kapanis_yakma_beklendi.load(Ordering::Acquire);
                        if let Some(port) = port {
                            if asama == KAPANIS_YAKMA_BEKLENIYOR {
                                api.prevent_close(); // bekleyici zaten çalışıyor — uyarı ekranda
                            } else if asama == KAPANIS_NORMAL
                                && backend::yakma_suruyor_mu(port, std::time::Duration::from_millis(800)) == Some(true)
                            {
                                api.prevent_close();
                                state.kapanis_yakma_beklendi.store(KAPANIS_YAKMA_BEKLENIYOR, Ordering::Release);
                                let _ = window.emit(OLAY_KAPANIS_YAKMA_BEKLENIYOR, ());
                                let asama_c = state.kapanis_yakma_beklendi.clone();
                                // KI G1: Destroyed işinin STOP sonrası beklemesi AYNI bütçeden (ikinci bir azami bekleme YOK).
                                let sinir = state.kapanis_yakma_siniri.clone();
                                let w = window.clone();
                                std::thread::spawn(move || {
                                    let _ = backend::yakmanin_bitmesini_bekle_sinirla(
                                        port,
                                        &sinir,
                                        backend::YAKMA_BEKLEME_AZAMI,
                                        std::time::Duration::from_secs(1),
                                    );
                                    asama_c.store(KAPANIS_YAKMA_BITTI, Ordering::Release);
                                    let _ = w.close();
                                });
                            }
                        }
                    }
                }
            }
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
                    if is_main {
                        // 2026-10-18 (sahip: "aynı sorunlu başka işlem de olabilir"): ana pencere kapanınca aşağıdaki bobin durdurma
                        // (E-stop + 1,6 sn kuyruk boşaltma + son oturum yakalama + kill ≈ 2–4 sn) BİLEREK pencere iş parçacığında
                        // beklenir (süreç çıkıyor, durdurma bitmeden dönülmez). O sürede açık kalan uygulama penceresi DONUK
                        // görünüyordu ("Yanıt vermiyor"). Önce GİZLE — durdurma AYNEN beklenir, pencere iş bitince kapatılır.
                        if let Some(appwin) = window.app_handle().get_webview_window("app") {
                            let _ = appwin.hide();
                        }
                    }
                    if let Some((mut child, port)) = state.proc.lock().unwrap().take() {
                        let root = install::default_install_root(&home_dir());
                        let bellek = state.session.clone(); // [S4] job'a taşınır (F5 belleği de tazeler)
                        let sinir = kapanis_yakma_siniri(&state, is_main); // KI G1: ana pencerede bekleyicinin bütçesi
                        // `mut`: closure `child`'ı taşır ve üzerinde kill/wait çağırır (FnMut değil,
                        // FnOnce; ama gövde &mut child istediği için binding mutable olmalı).
                        let mut job = move || {
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
                let _ = w.set_title(&pemf_launcher_core::dil::t("rust.pencere.guncelleniyor"));
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
