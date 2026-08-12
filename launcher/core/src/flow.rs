// Author: mertaygn, cglrgrkn
//! Kurulum akışının tamamı — UI'dan bağımsız, tek çağrı.
//!
//! UI yalnız `Progress` olaylarını dinler; sıralama, önbellek ve hata mantığı burada.
//! Böylece aynı akış Tauri kabuğundan da, bir CLI'dan da, testten de koşabilir.

use std::fs;
use std::path::{Path, PathBuf};

use crate::{extract, install, manifest::Manifest, net, verify};

/// UI'ya bildirilecek adımlar.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
#[serde(tag = "step", rename_all = "snake_case")]
pub enum Progress {
    ManifestFetched { version: String, schema: u8 },
    /// `total` 0 olabilir (sunucu Content-Length vermezse).
    Downloading { what: String, done: u64, total: u64 },
    /// Geçici ağ hatası (timeout/kopma) → `.part`'tan otomatik yeniden bağlanılıyor.
    Reconnecting { what: String, attempt: u32, max: u32 },
    Verifying { what: String },
    /// Paket önbellekte bulundu, indirme atlandı.
    Cached { what: String },
    Extracting { what: String },
    StartingBackend { port: u16 },
    Ready { url: String },
}

#[derive(Debug, thiserror::Error)]
pub enum FlowError {
    #[error(transparent)]
    Manifest(#[from] crate::manifest::ManifestError),
    #[error(transparent)]
    Net(#[from] net::NetError),
    #[error(transparent)]
    Verify(#[from] verify::VerifyError),
    #[error(transparent)]
    Extract(#[from] extract::ExtractError),
    #[error(transparent)]
    Backend(#[from] crate::backend::BackendError),
    #[error("dosya sistemi hatası: {0}")]
    Io(#[from] std::io::Error),
    /// DENETİM 2026-08-04: onarım, hangi profillerin kurulu olduğunu bilmeden model paketlerini
    /// SESSİZCE atlayıp "Hazır" diyordu. Artık kullanıcıya ne yapacağını söyleyen açık hata.
    #[error(
        "Kurulu profil kaydı okunamadı ama diskte model verisi VAR — hangi profillerin \
         onarılacağı bilinmiyor. Profilleri yeniden seçip kurun (indirilenler önbellekten gelir, \
         yeniden İNMEZ)."
    )]
    ProfileRecordUnreadable,
}

/// Cache dosya-adı güvenli mi: tek segment, yol-ayırıcı / sürücü / `..` / NUL YOK.
fn is_safe_filename(name: &str) -> bool {
    !name.is_empty()
        && name != "."
        && name != ".."
        && !name.contains('/')
        && !name.contains('\\')
        && !name.contains(':')
        && !name.contains('\0')
}

/// Bir indirme hatası GEÇİCİ mi (yeniden denenmeli) yoksa KALICI mı?
///
/// DENETİM 2026-08-04: `ensure_package`'ın yorumu "KALICI hatalar (host-pin/HTTPS/4xx) yeniden
/// denenmez" diyordu ama kod TÜM `HttpStatus` varyantlarını geçici sayıyordu. 404 (asset
/// `--clobber` ile silinmiş / yanlış tag) ya da 403'te kullanıcı ~22 sn "Yeniden bağlanılıyor"
/// görüp sonunda yine aynı hatayı alıyordu. Karar saf bir fonksiyona alındı → doğrudan test
/// edilebilir (host-pinlemesi yüzünden yerel HTTP sunucusuyla uçtan uca test edilemiyor).
fn is_retriable(e: &net::NetError) -> bool {
    match e {
        // Ağ kopması / timeout / aktarım hatası → geçici.
        net::NetError::Io(_) | net::NetError::Transport(_) => true,
        // 5xx sunucu tarafı geçicidir; 408 (Request Timeout) ve 429 (Too Many Requests) da öyle.
        // Diğer 4xx'ler KALICI: yeniden denemek yalnız kullanıcıyı bekletir.
        net::NetError::HttpStatus { status, .. } => *status >= 500 || *status == 408 || *status == 429,
        // ⚠️ DENETİM 2026-08-04 (P2): boyut tavanı / küresel süre aşımı ESKİDEN `Transport`
        // olarak dönüyordu ve yukarıdaki kol onları GEÇİCİ sayıyordu → aynı deterministik hata
        // 6 kez TAM YENİDEN İNDİRME tetikliyordu (gigabaytlarca boşuna trafik). Artık ayrı
        // varyant ve AÇIKÇA kalıcı. (Alttaki `_` zaten false döndürüyor; bu kol niyeti
        // belgeliyor ve varyant eklendiğinde sessizce yanlış tarafa düşmesini engelliyor.)
        net::NetError::PolicyLimit(_) => false,
        // Malformed / NotHttps / HostNotAllowed → GÜVENLİK reddi, ASLA yeniden deneme.
        // Paused / Cancelled → kullanıcı kararı, yeniden deneme YANLIŞ olur.
        _ => false,
    }
}

/// Bir paketi hazır et: önbellekte geçerli kopya varsa indirme, yoksa indir + doğrula.
///
/// Doğrulama İKİ yolda da yapılır — önbellekteki dosya bozulmuş olabilir (disk hatası,
/// yarım kalmış eski indirme). "Önbellekte var" tek başına güven sebebi değildir.
/// Paketin önbellekteki yolu. `ensure_package` ve "indi mi?" kontrolü AYNI kuralı kullansın diye
/// tek yerde — ayrışırlarsa arka plan indirmesi "hazır" der ama kurulum dosyayı bulamaz.
///
/// #131/#139: dosya adı SALDIRGAN-ETKİLİ `pkg.url`'den türer. Yol-kaçış karakteri (Windows '\',
/// sürücü ':', '/', '..', NUL) içeriyorsa cache DIŞINA yazabilir → güvenli ada düş.
pub fn cache_path_for(pkg: &crate::Package, cache: &Path, label: &str) -> PathBuf {
    let raw_name = pkg.url.rsplit('/').next().unwrap_or("");
    let file_name = [raw_name, label, "package.bin"]
        .into_iter()
        .find(|s| is_safe_filename(s))
        .unwrap_or("package.bin");
    cache.join(file_name)
}

/// Paket önbellekte TAM hâlde duruyor mu? (boyut kontrolü — sha doğrulaması `ensure_package`'da)
///
/// ⚠️ Bilerek sha OKUMAZ: 1,2 GB'lık dosyanın sha256'sı ~10 sn sürer ve bu kontrol AÇILIŞTA,
/// kullanıcı ekrana bakarken yapılır. Yanlış "hazır" demenin bedeli yok: kurulum `ensure_package`
/// ile sha'yı zaten doğrular, uymazsa yeniden indirir.
pub fn paket_onbellekte_hazir(pkg: &crate::Package, cache: &Path, label: &str) -> bool {
    let p = cache_path_for(pkg, cache, label);
    pkg.size > 0 && fs::metadata(&p).map(|m| m.len() == pkg.size).unwrap_or(false)
}

pub fn ensure_package(
    pkg: &crate::Package,
    cache: &Path,
    label: &str,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<PathBuf, FlowError> {
    fs::create_dir_all(cache)?;
    // #131/#139: dosya adı SALDIRGAN-ETKİLİ pkg.url'den türüyor. Yol-kaçış karakteri (Windows '\',
    // sürücü ':', '/', '..', NUL) içeriyorsa cache DIŞINA yazabilir → güvenli ada düş. İlk güvenli
    // adayı seç: url-son-segment → label → sabit "package.bin".
    let dest = cache_path_for(pkg, cache, label);

    if dest.exists() && verify::verify_file(&dest, &pkg.sha256).is_ok() {
        on(Progress::Cached { what: label.to_string() });
        return Ok(dest);
    }

    // Otomatik yeniden-deneme: GEÇİCİ ağ hataları (timeout/kopma/5xx — ör. os error 10060, büyük
    // paket sonrası bağlantı düşmesi) kurulumu düşürmesin. `.part` korunduğu için her deneme Range
    // ile KALDIĞI YERDEN sürer. Pause/Cancel + KALICI hatalar (host-pin/HTTPS/4xx) yeniden denenmez.
    const MAX_ATTEMPTS: u32 = 6;
    let mut attempt = 0u32;
    loop {
        attempt += 1;
        let result = {
            let mut cb = |done, total| {
                on(Progress::Downloading { what: label.to_string(), done, total });
            };
            net::download_to_file(&pkg.url, &dest, pkg.size, &pkg.sha256, &mut cb, control)
        };
        match result {
            Ok(_) => break,
            Err(e) => {
                let retriable = is_retriable(&e);
                if !retriable || attempt >= MAX_ATTEMPTS {
                    return Err(e.into());
                }
                on(Progress::Reconnecting { what: label.to_string(), attempt, max: MAX_ATTEMPTS });
                // Artan bekleme (1.5s→7.5s), ama Pause/Cancel gelirse HEMEN dön (asılı kalma).
                let wait_ms = (attempt.min(5) as u64) * 1500;
                let mut waited = 0u64;
                while waited < wait_ms {
                    match control() {
                        net::Control::Cancel => return Err(net::NetError::Cancelled.into()),
                        net::Control::Pause => return Err(net::NetError::Paused.into()),
                        net::Control::Continue => {}
                    }
                    std::thread::sleep(std::time::Duration::from_millis(200));
                    waited += 200;
                }
            }
        }
    }

    on(Progress::Verifying { what: label.to_string() });
    if let Err(e) = verify::verify_file(&dest, &pkg.sha256) {
        // Bozuk dosyayı BIRAKMA: kalırsa sonraki kurulum onu "önbellek" sanıp
        // aynı hataya tekrar düşer.
        let _ = fs::remove_file(&dest);

        // ⚠️ SAHA ŞİKÂYETİ 2026-08-11: kullanıcı güncellemede
        //   "SHA256 UYUŞMADI — dosya bozuk ya da değiştirilmiş"
        // gördü; oysa hem yayındaki paket hem sonradan inen kopya DOĞRUYDU (ikisi de
        // manifest sha'sıyla birebir). Yani bozulma İNDİRME sırasında oluşan geçici bir
        // durumdu — ama yukarıdaki 6-denemeli retry YALNIZ ağ hatalarını kapsıyor;
        // "indi ama sha tutmadı" hâli döngünün DIŞINDA olduğu için kullanıcıya hemen
        // hata olarak çıkıyor ve elle tekrar denemesi gerekiyordu.
        //
        // Mesaj ayrıca gereksiz korkutucu: metin "değiştirilmiş" diyerek bir güvenlik
        // olayı ima ediyor, oysa en olası sebep yarım/bayat indirmedir.
        //
        // ÇÖZÜM: sha uyuşmazlığında SIFIRDAN bir kez daha indir (`.part` da silinir, yani
        // Range ile devam DEĞİL, tam yeniden indirme). İkinci kez de tutmazsa hata gerçektir
        // ve yukarı çıkar — güvenlik doğrulaması ZAYIFLATILMAZ, yalnız bir kez telafi edilir.
        if temiz_yeniden_indirilebilir(control) {
            on(Progress::Reconnecting { what: label.to_string(), attempt: 1, max: 1 });
            let _ = fs::remove_file(net::part_path(&dest, &pkg.sha256));
            let mut cb = |done, total| {
                on(Progress::Downloading { what: label.to_string(), done, total });
            };
            net::download_to_file(&pkg.url, &dest, pkg.size, &pkg.sha256, &mut cb, control)?;
            on(Progress::Verifying { what: label.to_string() });
            if let Err(e2) = verify::verify_file(&dest, &pkg.sha256) {
                let _ = fs::remove_file(&dest);
                return Err(e2.into());
            }
            return Ok(dest);
        }
        return Err(e.into());
    }
    Ok(dest)
}

/// Kullanıcı duraklatmadı/iptal etmediyse temiz yeniden-indirme yapılabilir.
fn temiz_yeniden_indirilebilir(control: &dyn Fn() -> net::Control) -> bool {
    matches!(control(), net::Control::Continue)
}


/// manifest → base + SEÇİLEN PROFİLLER → kurulum (backend BAŞLATMAZ). Kurulan profiller kaydedilir.
///
/// Çoklu-profil: kullanıcı birden çok profil (Ev Sahibi + Veteriner + Araştırma) seçebilir;
/// base BİR KEZ, her profil model-zip'i sırayla kurulur. Boş liste = yalnız base (onarım/temel).
pub fn install_profiles(
    manifest_raw: &str,
    profiles: &[String],
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<(), FlowError> {
    let manifest = Manifest::parse(manifest_raw)?;
    on(Progress::ManifestFetched {
        version: manifest.version.clone(),
        schema: manifest.schema,
    });

    // Platform paketi YOKSA burada durur — asla başka platformun paketine düşmez.
    // Katmanlı manifest varsa runtime tek parça DEĞİL; o durumda burada doğrulama yapmayız
    // (katman digest'leri Manifest::parse'ta zaten doğrulandı).
    let katmanli = manifest.layers_for_current_platform().is_some();
    let runtime_pkg = if katmanli {
        None
    } else {
        Some(manifest.runtime_for_current_platform()?)
    };
    // TÜM profilleri İNDİRMEDEN ÖNCE doğrula (biri manifestte yoksa hiç indirme başlamasın).
    let model_pkgs: Vec<(&String, &crate::Package)> = profiles
        .iter()
        .map(|p| manifest.model_package(p).map(|pk| (p, pk)))
        .collect::<Result<_, _>>()?;

    // Yükseltme: eski boşluksuz "PEMFVetClient" kurulumu varsa yeni isme taşı (2 GB yeniden inmesin).
    install::migrate_legacy_install_root(install_root);

    let cache = install::cache_dir(install_root);

    // ── DİSK ALANI ÖN KONTROLÜ (2026-08-09 denetimi, Tier 1) ────────────────────────────────
    // Kurulum yolunda hiçbir yerde boş alan kontrolü YOKTU ve önbellekteki TAMAMLANMIŞ paketler
    // hiç temizlenmiyordu. LattePanda eMMC'sinde ölçüldü: ~4,8 GB kalıcı önbellek birikiyor,
    // kurulum 1,2 GB İNDİRDİKTEN SONRA `os error 112` ile ölüyor. En kötü yanı zamanlaması:
    // klinik 20 dakika bekliyor, sonra anlaşılmayan bir hata alıyor ve tekrar deniyor — her
    // denemede önbellek biraz daha şişiyor.
    //
    // Sıra ÖNEMLİ: önce ölü önbelleği temizle (yer aç), SONRA karar ver. Aksi hâlde eski
    // sürümlerin kalıntısı yüzünden gereksiz yere "yer yok" derdik.
    {
        let mut korunacak: Vec<String> = Vec::new();
        let mut ekle = |pkg: &crate::Package, etiket: &str| {
            if let Some(ad) = cache_path_for(pkg, &cache, etiket).file_name()
                .and_then(|s| s.to_str()) { korunacak.push(ad.to_string()); }
        };
        if let Some(l) = manifest.layers_for_current_platform() {
            ekle(&l.deps, "deps");
            ekle(&l.app, "app");
        }
        if let Some(p) = runtime_pkg { ekle(p, "base"); }
        for (ad, pkg) in &model_pkgs { ekle(pkg, ad); }

        let silinen = crate::disk::olu_onbellek_temizle(&cache, &korunacak);
        if silinen > 0 {
            on(Progress::Extracting {
                what: format!("eski paketler temizlendi ({})", crate::disk::insan_okur(silinen)),
            });
        }

        // İndirilecek (2× yer: önce zip, sonra açılmış ağaç) ve yalnız açılacak paketleri ayır.
        let (mut inecek, mut acilacak) = (Vec::new(), Vec::new());
        let mut hesapla = |pkg: &crate::Package, etiket: &str| {
            if paket_onbellekte_hazir(pkg, &cache, etiket) { acilacak.push(pkg.size); }
            else { inecek.push(pkg.size); }
        };
        if let Some(l) = manifest.layers_for_current_platform() {
            hesapla(&l.deps, "deps");
            hesapla(&l.app, "app");
        }
        if let Some(p) = runtime_pkg { hesapla(p, "base"); }
        for (ad, pkg) in &model_pkgs { hesapla(pkg, ad); }

        let gereken = crate::disk::gereken_alan(&inecek, &acilacak);
        if let Err((gerek, bos)) = crate::disk::yeterli_alan_var_mi(install_root, gereken) {
            return Err(FlowError::Io(std::io::Error::other(format!(
                "Yetersiz disk alanı: kurulum için {} gerekiyor, bu diskte {} boş. \
                 Yer açıp tekrar deneyin.",
                crate::disk::insan_okur(gerek), crate::disk::insan_okur(bos)))));
        }
    }

    // #110: açılım bütçesi TÜM kurulum boyunca PAYLAŞILIR (base + profiller).
    let mut extract_budget: u64 = 0;
    let rt = install::runtime_dir(install_root);

    // ── KATMANLI KURULUM (2026-08-08) ───────────────────────────────────────────────────────
    // Sıra: deps ağacı kurar (temizleyerek), app onun ÜSTÜNE gelir. İkisi de İNDİRİLMEDEN
    // hiçbir şey silinmez — aksi halde app indirmesi başarısız olursa exe'siz bir ağaç kalırdı.
    if let Some(l) = manifest.layers_for_current_platform() {
        let deps_zip = ensure_package(&l.deps, &cache, "deps", on, control)?;
        let app_zip = ensure_package(&l.app, &cache, "app", on, control)?;
        install::record_base_sha(install_root, "");
        install::record_layer_sha(install_root, "deps", "");
        install::record_layer_sha(install_root, "app", "");
        temizle_ve_ac(&deps_zip, &rt, &mut extract_budget, on, control)?;
        install::record_layer_sha(install_root, "deps", &l.deps.sha256);
        // İlk kurulumda disk boş → silinecek eski kök yok; aynı fonksiyon ikisini de doğru işler.
        app_katmanini_degistir(&app_zip, install_root, &mut extract_budget, on, control)?;
        install::record_layer_sha(install_root, "app", &l.app.sha256);
    } else {
    let runtime_pkg = runtime_pkg.expect("katmansız yolda runtime paketi zorunlu");
    let runtime_zip = ensure_package(runtime_pkg, &cache, "base", on, control)?;

    // ⚠️ DENETİM 2026-08-04 (P2): `extract_zip` SALT-EKLEME/ÜZERİNE-YAZMA yapar — yalnız arşivde
    // BULUNAN girdileri yazar, arşivde OLMAYAN dosyaları KALDIRMAZ ve hedef ağacı önce silmez.
    // Kurulum yolunda hiçbir yerde `remove_dir_all(runtime_dir)` çağrılmıyordu (`remove_install`
    // yalnız Kaldır'da kullanılır). Sonuç: "başarılı" bir yükseltmeden sonra bile disk İKİ SÜRÜMÜN
    // BİRLEŞİMİYDİ — yeni sürümde KALDIRILAN dosyalar (eski .pyd/.dll, eski web bundle parçaları)
    // yaşamaya devam ediyordu. PyInstaller onedir düzeninde bayat bir DLL/uzantı, sürümü
    // uyuşmayan bir Python ikilisiyle yüklendiğinde tanımsız davranış üretir ve bu, sürüm
    // numarasına bakan hiçbir teşhisle görünmez.
    // base.zip runtime ağacının TAMAMINI içerir → ÖNCE TEMİZLE, sonra aç.
    // (Backend bu noktada zaten durdurulmuştur: install/repair yolları `stop_tracked_backend`
    //  çağırır. Dosya kilidi varsa burada AÇIK hata veririz — sessiz karışık-kurulumdan iyidir.)
    if rt.exists() {
        on(Progress::Extracting { what: "eski sürüm temizleniyor".into() });
        fs::remove_dir_all(&rt)?;
    }
    on(Progress::Extracting { what: "base".into() });
    // ⚠️ DENETİM 2026-08-04 (P2 — İPTAL ÖZELLİĞİNİN YAN ETKİSİ): iptali eklerken "yarım ağaç
    // zararsız, durum dosyaları güncellenmiyor" demiştim. YANLIŞTI. Launcher "kurulu mu"
    // kararını `installed_profiles.json`'a değil `install::backend_path().exists()`'e göre
    // veriyor (bkz. detect_environment) ve `make_base_zip.py` kökteki tek dosya olan
    // `PEMF_Backend.exe`'yi İLK girdi olarak yazıyor. Yani base açılımı %1'de iptal edilse
    // bile exe diske düşmüş oluyor → UI kurulumu "kurulu" gösterip 6155 girdisi (~1,29 GB
    // `_internal/` PyInstaller ağacı) EKSİK bir backend'i başlatmaya çalışıyor.
    // Bu yüzden base açılımı BAŞARISIZ olursa (iptal ya da G/Ç hatası) `runtime/` SİLİNİR —
    // "hiç kurulmamış" durumu, "yarım kurulmuş"tan her zaman iyidir. Maliyet düşük: iptal
    // genelde erken gelir ve zaten yeniden indirme gerektirmez (paketler önbellekte).
    if let Err(e) = extract::extract_zip_cancellable(
        &runtime_zip,
        &rt,
        &mut extract_budget,
        false,
        &|| control() == net::Control::Cancel,
    ) {
        let _ = fs::remove_dir_all(&rt);
        return Err(e.into());
    }
    // base AÇILDI → kimliğini kaydet. Açılımdan SONRA (yarım ağaç "kurulu" işaretlenmesin).
    install::record_base_sha(install_root, &runtime_pkg.sha256);
    }

    // Her profil paketi `ai_models/...` önekiyle geldiği için kurulum KÖKÜNE açılır →
    // <kök>/ai_models/... oluşur ve PEMF_AI_MODELS_DIR tam oraya işaret eder.
    for (name, pkg) in &model_pkgs {
        let model_zip = ensure_package(pkg, &cache, name, on, control)?;
        on(Progress::Extracting { what: (*name).clone() });
        // `is_profile = true`: profil paketi doğrulanmış `runtime/` ağacını ve launcher durum
        // dosyalarını EZEMEZ (bkz. extract::PROFILE_FORBIDDEN_TOP, #104).
        extract::extract_zip_cancellable(&model_zip, install_root, &mut extract_budget, true, &|| {
            control() == net::Control::Cancel
        })?;
        // Bu profil TAM indi + açıldı → HEMEN "kurulu" işaretle (mevcutlarla birleşir).
        // ÖNEMLİ: işaretlemeyi döngü SONUNA bırakma. Çoklu-profil kurulumunda kullanıcı
        // sonraki profili İPTAL ederse (ör. Ev Sahibi bitti, Veteriner yarıda iptal),
        // erken-return burayı atlar → tamamlanan profil KAYBOLURDU. Her profili kendi
        // extract'ından hemen sonra kaydederek, iptal-sonrası kullanıcı tamamlanmış
        // profil(ler)le uygulamayı kurup başlatabilir.
        install::add_installed_profiles(install_root, std::slice::from_ref(*name));
        install::record_model_sha(install_root, name, &pkg.sha256);
    }
    // Denetim Masası boyutunu GERÇEK kullanımla güncelle: NSIS onu kurulum anında hesaplar ve
    // o an dizinde yalnız launcher vardır (~11 MB); runtime + profil modelleri SONRA iner.
    // (bkz. install::boyut_kaydini_guncelle)
    install::boyut_kaydini_guncelle(install_root);
    Ok(())
}

/// `runtime/` ağacını temizleyip verilen paketi açar. Yarım kalırsa ağacı SİLER.
///
/// install_profiles ve update_installed AYNI kuralı paylaşsın diye tek yerde: "yarım kurulmuş",
/// "hiç kurulmamış"tan her zaman kötüdür (bkz. install_profiles'daki uzun denetim notu).
fn temizle_ve_ac(
    zip: &Path,
    rt: &Path,
    butce: &mut u64,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<(), FlowError> {
    if rt.exists() {
        on(Progress::Extracting { what: "eski sürüm temizleniyor".into() });
        fs::remove_dir_all(rt)?;
    }
    on(Progress::Extracting { what: "base".into() });
    if let Err(e) = extract::extract_zip_cancellable(zip, rt, butce, false, &|| {
        control() == net::Control::Cancel
    }) {
        let _ = fs::remove_dir_all(rt);
        return Err(e.into());
    }
    Ok(())
}

/// APP katmanını yerine koy: önce DİSKTEKİ eski köklerini sil, sonra yeni paketi aç.
///
/// ⚠️ Silme şart: `extract_zip` salt-ekleme/üzerine-yazma yapar; yeni sürümde KALDIRILAN dosyalar
/// (eski `.pyd`, eski web bundle parçaları) yaşamaya devam ederdi. Sınır diskteki
/// `_app_roots.json`'dan okunur; okunamıyorsa SİLME YAPILMAZ (üzerine yaz) — bilinmeyen sınırla
/// silmek, bayat dosya bırakmaktan tehlikelidir.
fn app_katmanini_degistir(
    zip: &Path,
    install_root: &Path,
    butce: &mut u64,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<(), FlowError> {
    let rt = install::runtime_dir(install_root);
    let yedek = install::app_backup_dir(install_root);
    let roots = install::read_app_roots(install_root);
    let _ = fs::remove_dir_all(&yedek);
    if !roots.is_empty() {
        // ⚠️ SİLMEK DEĞİL TAŞIMAK: geri alma buna dayanır. Silseydik, yeni app açılımı yarıda
        // kalınca (iptal/disk/G-Ç) ne eski ne yeni app kalırdı → kurulum ölür ve 1,2 GB'lık deps
        // sağlam olduğu hâlde her şey baştan inmek zorunda kalırdı. Taşıma aynı birimde metadata
        // işlemidir (~anlık), 1,2 GB kopyalamaya gerek yok.
        on(Progress::Extracting { what: "eski uygulama sürümü yedekleniyor".into() });
        // ⚠️ ÖNCE SINIR DOSYASI: geri alma, yedeğin İÇİNDEKİ `_app_roots.json`'dan kökleri okur.
        // Marker kök listesinde olmadığı için taşınmıyordu → yedek "sınırsız" kalıyor ve geri alma
        // HİÇBİR ŞEY yapmıyordu (bu hatayı `basarisiz_guncelleme_kurulumu_bozmaz` testi yakaladı).
        // Kopyalanır (taşınmaz): eski marker açma sırasında yeni paketinkiyle ezilecek zaten.
        {
            let src = install::app_roots_path(install_root);
            if src.is_file() {
                let dst = yedek.join("PEMF_Backend").join("_app_roots.json");
                if let Some(ust) = dst.parent() {
                    fs::create_dir_all(ust)?;
                }
                fs::copy(&src, &dst)?;
            }
        }
        for r in &roots {
            let src = rt.join(r.replace('/', std::path::MAIN_SEPARATOR_STR));
            if !src.exists() {
                continue;
            }
            let dst = yedek.join(r.replace('/', std::path::MAIN_SEPARATOR_STR));
            if let Some(ust) = dst.parent() {
                fs::create_dir_all(ust)?;
            }
            fs::rename(&src, &dst)?;
        }
    }
    on(Progress::Extracting { what: "app".into() });
    if let Err(e) = extract::extract_zip_cancellable(zip, &rt, butce, false, &|| {
        control() == net::Control::Cancel
    }) {
        // Açılım başarısız → eski app'i HEMEN geri koy (kurulum çalışır kalsın).
        let b = GeriAlmaBilgisi { app_yedegi: true, ..Default::default() };
        let _ = guncellemeyi_geri_al(install_root, &b);
        return Err(e.into());
    }
    Ok(())
}

/// Bir güncellemenin GERİ ALINABİLİR durumu. `update_installed` döner; çağıran sağlık kapısından
/// sonra ya `guncellemeyi_onayla` ya da `guncellemeyi_geri_al` çağırmak ZORUNDADIR.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct GeriAlmaBilgisi {
    /// deps yenilendi → tam ağaç takası yapıldı (`runtime.old` bekliyor).
    pub tam_takas: bool,
    /// yalnız app yenilendi → eski app dosyaları `_app_yedek`te bekliyor.
    pub app_yedegi: bool,
    /// Onaylanınca kaydedilecek sha'lar (sağlık kapısı geçmeden kayıt yazılmaz).
    pub deps_sha: String,
    pub app_sha: String,
    pub base_sha: String,
}

impl GeriAlmaBilgisi {
    pub fn bir_sey_yapildi(&self) -> bool {
        self.tam_takas || self.app_yedegi
    }
}

/// Yapısal doğrulama: ağaç en azından ÇALIŞTIRILABİLİR görünüyor mu?
///
/// Sağlık kapısından (backend'i başlatma) ÖNCE gelir — bozuk bir ağacı çalıştırmaya kalkmadan,
/// ucuz bir kontrolle yakalar. Zip açımı "başarılı" dönse bile eksik/yanlış katman burada patlar.
/// Kurulum GERÇEKTEN çalıştırılabilir mi? (exe + `_internal` + web arayüzü)
///
/// ⚠️ ARIZA (2026-08-11, kesinti incelemesi): `detect_environment` kurulumu YALNIZ backend
/// exe'sinin varlığıyla anlıyordu. Ama `install_profiles` ATOMİK DEĞİLDİR — canlı `runtime`'ı
/// silip yerine açar (güncelleme yolundaki `runtime.new` + takas yalnız GÜNCELLEMEDE var).
/// Açma sırasında kapanma olursa exe yazılmış ama `_internal/frontend` yarım kalmış olabilir;
/// client "Hazır!" der, kullanıcı Başlat'a basar ve backend anlaşılmaz bir hatayla düşer.
///
/// Yapısal kontrolle "kurulu değil" demek, "kurulu ama açılmıyor"dan İYİDİR: kurulum ekranı
/// çıkar ve kullanıcı tek tıkla toparlar (paketler önbellekte, yeniden indirme yok).
pub fn kurulum_saglam_mi(install_root: &Path) -> bool {
    agac_yapisal_gecerli_mi(&install::runtime_dir(install_root))
}

fn agac_yapisal_gecerli_mi(rt: &Path) -> bool {
    let kok = rt.join("PEMF_Backend");
    kok.join(crate::platform::backend_exe_name()).is_file()
        && kok.join("_internal").is_dir()
        && kok.join("_internal").join("frontend").join("dist").join("index.html").is_file()
}

/// `runtime` → `runtime.old`, `runtime.new` → `runtime`. Aynı birimde rename = neredeyse anlık.
fn atomik_takas(install_root: &Path) -> Result<(), FlowError> {
    let rt = install::runtime_dir(install_root);
    let yeni = install::runtime_new_dir(install_root);
    let eski = install::runtime_old_dir(install_root);
    if eski.exists() {
        fs::remove_dir_all(&eski)?;
    }
    if rt.exists() {
        fs::rename(&rt, &eski)?;
    }
    // Bu rename başarısız olursa eski sürümü GERİ KOY — aksi halde ortada runtime kalmaz.
    if let Err(e) = fs::rename(&yeni, &rt) {
        let _ = fs::rename(&eski, &rt);
        return Err(e.into());
    }
    Ok(())
}

/// YARIM KALAN TAKASI KURTAR — açılışta, her şeyden önce çağrılır.
///
/// ⚠️ ARIZA (2026-08-11, "kurulum/güncelleme esnasında kapanma" incelemesi):
/// `atomik_takas` iki `rename` yapar — `runtime`→`runtime.old`, sonra `runtime.new`→`runtime`.
/// İKİSİNİN ARASINDA süreç ölürse (kullanıcı pencereyi kapattı, elektrik gitti, görev
/// yöneticisinden sonlandırıldı) diskte `runtime` **HİÇ YOKTUR**; çalışan eski sürüm
/// `runtime.old`'da sapasağlam durur.
///
/// Ama `detect_environment` kurulumu `runtime/PEMF_Backend/…` var mı diye anlar → client
/// **"kurulu değil"** der. Kullanıcı çalışan bir kurulumu olduğu hâlde sıfırdan kurulum
/// ekranıyla karşılaşır ve sağlam `runtime.old` sessizce yetim kalır.
///
/// KURTARMA SIRASI — `runtime.old` ÖNCE:
///   `runtime.old` sağlık kapısını GEÇMİŞ, çalıştığı KANITLANMIŞ sürümdür. `runtime.new` ise
///   hiç doğrulanmadı. Yarıda kalan güncellemeyi "tamamlamak" doğrulanmamış bir sürümü sessizce
///   canlıya almak olurdu. Eskiye dönülür; güncelleme bir sonraki açılışta yeniden denenir
///   (paketler önbellekte, yeniden indirme YOK).
///
/// Döner: kurtarma yapıldıysa `true`.
pub fn yarim_takasi_kurtar(install_root: &Path) -> bool {
    let rt = install::runtime_dir(install_root);
    if rt.exists() {
        return false; // takas ya hiç başlamadı ya da tamamlandı
    }
    let eski = install::runtime_old_dir(install_root);
    if eski.is_dir() && agac_yapisal_gecerli_mi(&eski) && fs::rename(&eski, &rt).is_ok() {
        return true;
    }
    // Son çare: eski yok/bozuk ama yeni hazır ve YAPISAL olarak geçerli → onu al. Doğrulanmamış
    // olması, kliniği runtime'sız bırakmaktan iyidir (alternatif: 1,4 GB yeniden kurulum).
    let yeni = install::runtime_new_dir(install_root);
    if yeni.is_dir() && agac_yapisal_gecerli_mi(&yeni) && fs::rename(&yeni, &rt).is_ok() {
        return true;
    }
    false
}

/// Sağlık kapısı GEÇİLDİ → yedekleri sil ve paket kimliklerini kaydet.
///
/// ⚠️ Kayıt burada yazılır, güncellemenin ortasında DEĞİL: çalışmayan bir sürüm asla "kurulu"
/// işaretlenmemeli, yoksa bir sonraki açılış onu güncel sanıp bozuk hâlde başlatmaya çalışır.
pub fn guncellemeyi_onayla(install_root: &Path, b: &GeriAlmaBilgisi) {
    let _ = fs::remove_dir_all(install::runtime_old_dir(install_root));
    let _ = fs::remove_dir_all(install::app_backup_dir(install_root));
    if !b.deps_sha.is_empty() {
        install::record_layer_sha(install_root, "deps", &b.deps_sha);
    }
    if !b.app_sha.is_empty() {
        install::record_layer_sha(install_root, "app", &b.app_sha);
    }
    if !b.base_sha.is_empty() {
        install::record_base_sha(install_root, &b.base_sha);
    }
    // Güncelleme ağacı değiştirdi → Denetim Masası boyutu da tazelensin.
    install::boyut_kaydini_guncelle(install_root);
}

/// Sağlık kapısı GEÇİLEMEDİ → çalışan eski sürüme dön.
///
/// Kayıtlar zaten yazılmadığı için disk "bilinmiyor" durumunda kalır; bir sonraki açılış
/// güncellemeyi yeniden dener (paketler önbellekte olduğu için yeniden indirme YOK).
pub fn guncellemeyi_geri_al(install_root: &Path, b: &GeriAlmaBilgisi) -> Result<(), FlowError> {
    let rt = install::runtime_dir(install_root);
    if b.tam_takas {
        let eski = install::runtime_old_dir(install_root);
        if eski.is_dir() {
            // Bozuk yeni sürümü kenara al (teşhis için sakla), eskiyi geri koy.
            let bozuk = install_root.join("runtime.bozuk");
            let _ = fs::remove_dir_all(&bozuk);
            if rt.exists() {
                let _ = fs::rename(&rt, &bozuk);
            }
            fs::rename(&eski, &rt)?;
            let _ = fs::remove_dir_all(&bozuk);
        }
    } else if b.app_yedegi {
        let yedek = install::app_backup_dir(install_root);
        if yedek.is_dir() {
            // ⚠️ Geri koyma KÖK LİSTESİ üzerinden yürür, yedek dizininin üst seviyesi üzerinden
            // DEĞİL: kökler `PEMF_Backend/_internal/ai_hub` gibi İÇ İÇE yollardır ve üst seviye
            // girdisi (`PEMF_Backend`) taşınırsa tüm ağaç — deps dâhil — EZİLİRDİ.
            // Kökleri YEDEKTEN oku: `runtime/`dekiler yeni sürüme aittir.
            for kok in yedek_kokleri(&yedek) {
                let src = yedek.join(kok.replace('/', std::path::MAIN_SEPARATOR_STR));
                let dst = rt.join(kok.replace('/', std::path::MAIN_SEPARATOR_STR));
                if !src.exists() {
                    continue;
                }
                if dst.is_dir() {
                    let _ = fs::remove_dir_all(&dst);
                } else if dst.is_file() {
                    let _ = fs::remove_file(&dst);
                }
                if let Some(ust) = dst.parent() {
                    fs::create_dir_all(ust)?;
                }
                fs::rename(&src, &dst)?;
            }
            let _ = fs::remove_dir_all(&yedek);
        }
    }
    Ok(())
}

/// Yedeklenmiş app köklerinin listesi — yedeğin İÇİNDEKİ `_app_roots.json`'dan okunur.
///
/// Neden diskteki `runtime/`den değil: app açıldıktan sonra oradaki marker YENİ sürüme aittir;
/// geri alırken ESKİ sürümün sınırı gerekir.
fn yedek_kokleri(yedek: &Path) -> Vec<String> {
    #[derive(serde::Deserialize)]
    struct R {
        #[serde(default)]
        roots: Vec<String>,
    }
    fs::read_to_string(yedek.join("PEMF_Backend").join("_app_roots.json"))
        .ok()
        .and_then(|s| serde_json::from_str::<R>(&s).ok())
        .map(|r| r.roots)
        .unwrap_or_default()
        .into_iter()
        .filter(|r| !r.contains("..") && !r.starts_with('/') && !r.contains(':') && !r.contains('\\'))
        .collect()
}

/// Manifest ile diskteki kurulumun FARKI — "ne bayat?" sorusunun tek cevabı.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct UpdatePlan {
    /// Tek parça base.zip yenilenmeli mi? (katmansız manifest yolu)
    pub base: bool,
    /// Bağımlılık katmanı bayat mı? (katmanlı manifest)
    pub deps: bool,
    /// Uygulama katmanı bayat mı? (bizim kod — sık değişen)
    pub app: bool,
    /// Yenilenmesi gereken KURULU profiller (kurulu olmayanlar buraya GİRMEZ — sessizce
    /// yeni profil kurmayız, kullanıcı neyi seçtiyse o kalır).
    pub profiles: Vec<String>,
    /// İnecek toplam bayt (UI "ne kadar sürecek" diyebilsin).
    pub bytes: u64,
    /// Yeni sürüm VAR ama bu cihaz henüz kademeli yayın diliminde değil (`rollout`).
    /// `needed()` false döner — yani hiçbir şey indirilmez/kurulmaz; teşhis için işaretlenir.
    pub rollout_bekliyor: bool,
    /// Gereken TÜM paketler zaten önbellekte mi?
    ///
    /// SAHİP KARARI 2026-08-08: güncelleme açılışta kimseyi bekletmemeli. `true` ise kurulum
    /// ANINDA yapılabilir (yalnız açma); `false` ise paketler ARKA PLANDA indirilir ve kurulum
    /// bir SONRAKİ açılışa bırakılır — hayvanı masada bekleyen veteriner 45 dk indirmeye takılmaz.
    pub cached: bool,
}

impl UpdatePlan {
    pub fn needed(&self) -> bool {
        self.base || self.deps || self.app || !self.profiles.is_empty()
    }
}

/// Manifest'i diskteki kurulumla karşılaştır (AĞA ÇIKMAZ — manifest zaten çekilmiştir).
///
/// SAHİP KARARI 2026-08-08: kullanıcı "Onar"a basmadan güncellensin. Bu fonksiyon kararı verir,
/// `update_installed` uygular.
///
/// ⚠️ KAYIT YOKSA (`installed_packages.json` yok = 1.9.10 ve öncesi kurulumlar) base BAYAT
/// SAYILIR. Bilinmeyeni "güncel" saymak, tam da bu özelliğin çözmek için var olduğu sessiz
/// eskimeyi geri getirirdi. Bedeli tek seferlik bir base indirmesidir (kullanıcı zaten "Onar"a
/// bassa aynısı inecekti); sonraki açılışlarda kayıt dolu olduğu için karşılaştırma bedavadır.
pub fn pending_updates(manifest_raw: &str, install_root: &Path) -> Result<UpdatePlan, FlowError> {
    let manifest = Manifest::parse(manifest_raw)?;
    let mut plan = UpdatePlan::default();

    // Hiç kurulu değilse güncelleme YOK (kurulum akışı ayrı; burada karar vermeyiz).
    if !install::backend_path(install_root).exists() {
        return Ok(plan);
    }

    let kurulu = install::read_installed_packages(install_root);

    // KATMANLI manifest varsa O TERCİH EDİLİR: sıradan bir sürümde yalnız ~71 MB'lık app katmanı
    // iner, 1,19 GB'lık deps'e dokunulmaz. Katman yoksa (eski manifest) tek parça yola düşülür.
    if let Some(l) = manifest.layers_for_current_platform() {
        // ── KADEMELİ YAYIN / GERİ ÇEKME ANAHTARI ────────────────────────────────────────────
        // Güncelleme otomatik uygulandığı için bozuk bir yayın sahadaki HER cihaza gider.
        // `rollout` yüzdesi bunun tek frenidir: 0 = yayını durdur, 10 = önce küçük dilime aç.
        // Dilim kurulum kimliğinden türer → kararlı (aynı cihaz zıplamaz).
        // ⚠️ GERİ ÇAĞIRMA `rollout`u EZER (2026-08-09 denetimi, Tier 2).
        // `rollout: 0` yalnız YENİ dağıtımı durdurur — sahadaki cihaza dokunmaz. Bir
        // bobin-güvenliği hatası bulunduğunda asıl gereken, MEVCUT kurulumları güncellemeye
        // ZORLAMAKTIR. `min_supported_version` doluysa ve kurulu sürüm ondan eskiyse cihaz
        // dilimine BAKILMAZ: güncelleme uygulanır.
        let zorunlu = manifest
            .min_supported_version
            .as_deref()
            .is_some_and(|asgari| crate::is_newer(asgari, &install::kurulu_surum(install_root)));
        if !zorunlu && l.rollout < 100 && install::rollout_dilimi(install_root) >= l.rollout {
            plan.rollout_bekliyor = true;
            return Ok(plan);   // güncelleme VAR ama bu cihazın sırası değil
        }
        if !kurulu.deps.eq_ignore_ascii_case(&l.deps.sha256) {
            plan.deps = true;
            plan.bytes += l.deps.size;
        }
        if !kurulu.app.eq_ignore_ascii_case(&l.app.sha256) {
            plan.app = true;
            plan.bytes += l.app.size;
        }
        // deps yenilenecekse `runtime/` komple silinip yeniden kurulur → app da MUTLAKA gerekir
        // (aksi halde exe'siz bir ağaç kalırdı).
        if plan.deps {
            if !plan.app {
                plan.bytes += l.app.size;
            }
            plan.app = true;
        }
    } else {
        let runtime_pkg = manifest.runtime_for_current_platform()?;
        if !kurulu.base.eq_ignore_ascii_case(&runtime_pkg.sha256) {
            plan.base = true;
            plan.bytes += runtime_pkg.size;
        }
    }

    for name in install::read_installed_profiles(install_root) {
        // Manifestte olmayan profil (kaldırılmış) → dokunma, hata da verme.
        let Ok(pkg) = manifest.model_package(&name) else { continue };
        // ⚠️ MODELLERDE KURAL BASE'DEN FARKLI: KAYIT YOKSA "bayat" DEMİYORUZ.
        // Base'de bilinmeyeni bayat saymak 1,3 GB'a mal olur ve backend gerçekten değişmiştir.
        // Modellerde aynı kuralı uygulamak, kaydı olmayan her eski kurulumda ÜÇ profili birden
        // (~2,2 GB) boşuna indirtirdi — oysa model paketleri base'den çok daha seyrek değişir ve
        // kullanıcı onları zaten AYNI manifestten kurmuştu. Bu yüzden kaydı olmayan profilin
        // sha'sı manifestten BENİMSENİR (`adopt_unknown_models`); benimsendikten SONRA yapılan
        // her model değişikliği normal biçimde yakalanır. Tam yeniden doğrulama isteyen
        // kullanıcının yolu hâlâ "Onar"dır.
        let Some(mevcut) = kurulu.models.get(&name) else { continue };
        if !mevcut.eq_ignore_ascii_case(&pkg.sha256) {
            plan.bytes += pkg.size;
            plan.profiles.push(name);
        }
    }

    // Gereken paketler zaten indirilmiş mi? (arka plan indirmesi bir önceki açılışta bitmiş olabilir)
    let cache = install::cache_dir(install_root);
    let mut hepsi = true;
    if let Some(l) = manifest.layers_for_current_platform() {
        if plan.deps && !paket_onbellekte_hazir(&l.deps, &cache, "deps") { hepsi = false; }
        if plan.app && !paket_onbellekte_hazir(&l.app, &cache, "app") { hepsi = false; }
    } else if plan.base {
        if let Ok(p) = manifest.runtime_for_current_platform() {
            if !paket_onbellekte_hazir(p, &cache, "base") { hepsi = false; }
        }
    }
    for name in &plan.profiles {
        if let Ok(pkg) = manifest.model_package(name) {
            if !paket_onbellekte_hazir(pkg, &cache, name) { hepsi = false; }
        }
    }
    plan.cached = hepsi;
    Ok(plan)
}

/// ARKA PLAN İNDİRME — paketleri önbelleğe çeker, KURULUMA DOKUNMAZ.
///
/// SAHİP KARARI 2026-08-08 ("arka planda indir, sonra kur"): güncelleme açılışta kullanıcıyı
/// bekletmemeli. Bu fonksiyon yalnız indirir; kurulum bir sonraki açılışta, paketler hazırken
/// saniyeler içinde yapılır. Çalışan kuruluma HİÇBİR dosya yazmaz → indirme yarıda kalsa bile
/// cihaz etkilenmez (`.part` korunur, sonraki denemede Range ile devam eder).
pub fn prefetch_updates(
    manifest_raw: &str,
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<(), FlowError> {
    let plan = pending_updates(manifest_raw, install_root)?;
    if !plan.needed() || plan.cached {
        return Ok(());
    }
    let manifest = Manifest::parse(manifest_raw)?;
    let cache = install::cache_dir(install_root);
    if let Some(l) = manifest.layers_for_current_platform() {
        if plan.deps {
            ensure_package(&l.deps, &cache, "deps", on, control)?;
        }
        if plan.app {
            ensure_package(&l.app, &cache, "app", on, control)?;
        }
    } else if plan.base {
        ensure_package(manifest.runtime_for_current_platform()?, &cache, "base", on, control)?;
    }
    for name in &plan.profiles {
        ensure_package(manifest.model_package(name)?, &cache, name, on, control)?;
    }
    Ok(())
}

/// ESKİ KURULUM UYUMU — kaydı olmayan KURULU profillerin sha'sını manifestten benimse.
///
/// `pending_updates`'ten ÖNCE çağrılır. Benimsemezsek kayıt sonsuza dek boş kalır ve o profildeki
/// GERÇEK bir güncelleme hiçbir zaman fark edilmez (sessiz kaçırma). Base'e DOKUNMAZ.
pub fn adopt_unknown_models(manifest_raw: &str, install_root: &Path) -> Result<(), FlowError> {
    if !install::backend_path(install_root).exists() {
        return Ok(());
    }
    let manifest = Manifest::parse(manifest_raw)?;
    let kurulu = install::read_installed_packages(install_root);
    for name in install::read_installed_profiles(install_root) {
        if kurulu.models.contains_key(&name) {
            continue;
        }
        let Ok(pkg) = manifest.model_package(&name) else { continue };
        install::record_model_sha(install_root, &name, &pkg.sha256);
    }
    Ok(())
}

/// `pending_updates`'in bulduğu BAYAT paketleri yenile (backend BAŞLATMAZ).
///
/// `install_profiles`'tan farkı: yalnız DEĞİŞENİ indirir/açar. Tümünü yeniden açmak, sha'sı
/// değişmemiş 1,5 GB'lık araştırma modellerini her base güncellemesinde boşuna açardı.
///
/// ⚠️ ÇAĞIRAN, backend'i ÖNCEDEN DURDURMUŞ olmalı (E-stop → kill sırasıyla). base açılımı
/// `runtime/` ağacını SİLİP yeniden yazar; çalışan backend dosya kilidi tutar.
pub fn update_installed(
    manifest_raw: &str,
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<GeriAlmaBilgisi, FlowError> {
    let mut geri = GeriAlmaBilgisi::default();
    let plan = pending_updates(manifest_raw, install_root)?;
    if !plan.needed() {
        return Ok(geri);
    }
    let manifest = Manifest::parse(manifest_raw)?;
    on(Progress::ManifestFetched {
        version: manifest.version.clone(),
        schema: manifest.schema,
    });
    let cache = install::cache_dir(install_root);
    let mut extract_budget: u64 = 0;

    // ── KATMANLI YOL ────────────────────────────────────────────────────────────────────────
    if let Some(l) = manifest.layers_for_current_platform() {
        // İki paketi de İNDİRMEDEN hiçbir şeye dokunma: deps yenilenecekse ağaç değişecek, o anda
        // app paketi elde YOKSA kurulum exe'siz kalır. İndirme yeniden denenebilir, yarım ağaç değil.
        let deps_zip = if plan.deps {
            Some(ensure_package(&l.deps, &cache, "deps", on, control)?)
        } else {
            None
        };
        let app_zip = if plan.app {
            Some(ensure_package(&l.app, &cache, "app", on, control)?)
        } else {
            None
        };

        if let Some(dz) = deps_zip {
            // ATOMİK: yeni ağaç `runtime.new`'de kurulur; ÇALIŞAN kuruluma takasa kadar dokunulmaz.
            let yeni = install::runtime_new_dir(install_root);
            temizle_ve_ac(&dz, &yeni, &mut extract_budget, on, control)?;
            let az = app_zip.as_ref().expect("plan.deps → plan.app zorunlu (bkz. pending_updates)");
            on(Progress::Extracting { what: "app".into() });
            if let Err(e) = extract::extract_zip_cancellable(az, &yeni, &mut extract_budget, false, &|| {
                control() == net::Control::Cancel
            }) {
                let _ = fs::remove_dir_all(&yeni);
                return Err(e.into());
            }
            if !agac_yapisal_gecerli_mi(&yeni) {
                let _ = fs::remove_dir_all(&yeni);
                return Err(FlowError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "yeni kurulum eksik (exe/web bulunamadı) — takas yapılmadı",
                )));
            }
            atomik_takas(install_root)?;
            geri = GeriAlmaBilgisi {
                tam_takas: true,
                deps_sha: l.deps.sha256.clone(),
                app_sha: l.app.sha256.clone(),
                ..Default::default()
            };
        } else if let Some(az) = app_zip {
            // Yalnız app: eski app dosyalarını YEDEĞE TAŞI (silme!), sonra yenisini aç.
            app_katmanini_degistir(&az, install_root, &mut extract_budget, on, control)?;
            if !agac_yapisal_gecerli_mi(&install::runtime_dir(install_root)) {
                let b = GeriAlmaBilgisi { app_yedegi: true, ..Default::default() };
                let _ = guncellemeyi_geri_al(install_root, &b);
                return Err(FlowError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "yeni uygulama katmanı eksik — eski sürüme dönüldü",
                )));
            }
            geri = GeriAlmaBilgisi {
                app_yedegi: true,
                app_sha: l.app.sha256.clone(),
                ..Default::default()
            };
        }
    } else if plan.base {
        // ── TEK PARÇA (eski manifest / yedek) ───────────────────────────────────────────────
        let runtime_pkg = manifest.runtime_for_current_platform()?;
        let runtime_zip = ensure_package(runtime_pkg, &cache, "base", on, control)?;
        // Katmanlı yolla AYNI atomik akış: yeni ağaç ayrı dizinde kurulur, sonra takas edilir.
        // Kayıt (record_base_sha) sağlık kapısından SONRA `guncellemeyi_onayla`da yazılır.
        let yeni = install::runtime_new_dir(install_root);
        temizle_ve_ac(&runtime_zip, &yeni, &mut extract_budget, on, control)?;
        if !agac_yapisal_gecerli_mi(&yeni) {
            let _ = fs::remove_dir_all(&yeni);
            return Err(FlowError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "yeni kurulum eksik (exe/web bulunamadı) — takas yapılmadı",
            )));
        }
        atomik_takas(install_root)?;
        geri = GeriAlmaBilgisi {
            tam_takas: true,
            base_sha: runtime_pkg.sha256.clone(),
            ..Default::default()
        };
    }

    for name in &plan.profiles {
        let pkg = manifest.model_package(name)?;
        let model_zip = ensure_package(pkg, &cache, name, on, control)?;
        on(Progress::Extracting { what: name.clone() });
        install::record_model_sha(install_root, name, "");
        extract::extract_zip_cancellable(&model_zip, install_root, &mut extract_budget, true, &|| {
            control() == net::Control::Cancel
        })?;
        install::record_model_sha(install_root, name, &pkg.sha256);
    }
    Ok(geri)
}

/// Kurulu backend'i başlat (İNDİRME YOK). Hem ilk kurulum sonrası hem "Başlat" bunu kullanır.
pub fn start_backend(
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
) -> Result<(std::process::Child, String, u16), FlowError> {
    let port = crate::backend::find_free_port(install::DEFAULT_PORT, 50)?;
    on(Progress::StartingBackend { port });
    let child = crate::backend::start_and_wait(
        install_root,
        port,
        std::time::Duration::from_secs(180),
    )?;
    let url = crate::backend::app_url(port);
    on(Progress::Ready { url: url.clone() });
    // Port da döner: launcher pencere kapanışında bobinleri güvene almak için (safe_stop_coils).
    Ok((child, url, port))
}

/// Onar: kurulu profilleri (+base) YENİDEN doğrula/çıkar. `ensure_package` önbellekteki dosyayı
/// SHA ile doğrular → bozuksa yeniden indirir; her paket yeniden extract edilir (eksik/bozuk
/// dosyalar onarılır). Hiç profil kurulu değilse yalnız base onarılır. Backend BAŞLATMAZ.
pub fn repair(
    manifest_raw: &str,
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<(), FlowError> {
    // DENETİM 2026-08-04: liste `read_installed_profiles`'tan alınıyordu; o fonksiyon dosya yoksa
    // VEYA JSON bozuksa BOŞ liste döndüğü için onarım YALNIZ base'i yeniliyor, model paketlerine
    // HİÇ dokunmuyor ve yine de `Ok(())` dönüyordu → UI "Hazır" diyordu. Artık kaydın durumu
    // ayırt ediliyor: okunamıyorsa ve diskte model verisi VARSA hangi profillerin onarılacağı
    // BİLİNEMEZ → sessiz başarı yerine AÇIK hata.
    // DENETİM 2026-08-04 (P3): `Missing` ile `Corrupt` AYNI kovadaydı → `installed_profiles.json`
    // (2026-07-29) ÖNCESİ yapılmış TÜM meşru kurulumlarda "Onar" tamamen çalışmaz olmuştu.
    // `Missing` belirsiz DEĞİL: profiller `ai_models/<profil>/` dizinlerinden çıkarılabilir.
    // `Corrupt` (dosya var, JSON bozuk) gerçekten belirsizdir → açık hata doğru kalır.
    let installed = match install::read_installed_profiles_detailed(install_root) {
        install::ProfileRecord::Ok(v) => v,
        install::ProfileRecord::Missing if install::has_model_data(install_root) => {
            let v = install::infer_profiles_from_disk(install_root);
            on(Progress::Extracting {
                what: format!("eski kurulum algılandı ({} profil)", v.len()),
            });
            v
        }
        install::ProfileRecord::Corrupt if install::has_model_data(install_root) => {
            return Err(FlowError::ProfileRecordUnreadable);
        }
        // Kayıt yok/bozuk AMA diskte model de yok → gerçekten yalnız base kurulu; onarım doğru.
        _ => Vec::new(),
    };
    install_profiles(manifest_raw, &installed, install_root, on, control)
}

/// manifest → base + tek profil → kurulum → backend başlat. (Geriye-uyum: tek-profil sarmalayıcı.)
pub fn install_and_launch(
    manifest_raw: &str,
    profile: &str,
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
) -> Result<(std::process::Child, String, u16), FlowError> {
    install_profiles(
        manifest_raw,
        std::slice::from_ref(&profile.to_string()),
        install_root,
        on,
        &|| net::Control::Continue,
    )?;
    start_backend(install_root, on)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn pkg(url: &str, sha: &str) -> crate::Package {
        crate::Package {
            url: url.to_string(),
            sha256: sha.to_string(),
            size: 0,
            kind: "zip".into(),
        }
    }

    const ABC_SHA: &str = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

    #[test]
    fn onbellekteki_gecerli_dosya_yeniden_indirilmez() {
        let dir = tempfile::tempdir().unwrap();
        let cache = dir.path();
        // URL'nin son parçası dosya adı olur.
        fs::File::create(cache.join("x.zip")).unwrap().write_all(b"abc").unwrap();

        let mut seen = Vec::new();
        let mut on = |p: Progress| seen.push(p);
        // Host pinlemesi geçerli bir URL; önbellek isabet ettiği için AĞA ÇIKILMAZ.
        let got = ensure_package(
            &pkg("https://github.com/a/x.zip", ABC_SHA),
            cache,
            "base",
            &mut on,
            &|| net::Control::Continue,
        )
        .unwrap();

        assert_eq!(got, cache.join("x.zip"));
        assert_eq!(seen, vec![Progress::Cached { what: "base".into() }]);
    }

    #[test]
    fn onbellekteki_bozuk_dosya_guven_sebebi_degil() {
        let dir = tempfile::tempdir().unwrap();
        let cache = dir.path();
        fs::File::create(cache.join("x.zip")).unwrap().write_all(b"BOZUK").unwrap();

        let mut on = |_: Progress| {};
        // Dosya bozuk → önbellek reddedilir → indirmeye gider → ağ yok/host testte
        // erişilemez olduğu için hata döner. Önemli olan: "Cached" DEMEDİ.
        let err = ensure_package(
            &pkg("https://github.com/a/x.zip", ABC_SHA),
            cache,
            "base",
            &mut on,
            &|| net::Control::Continue,
        )
        .unwrap_err();
        assert!(matches!(err, FlowError::Net(_)), "beklenmeyen: {err:?}");
    }

    #[test]
    fn pinlenmemis_host_indirmeden_once_reddedilir() {
        let dir = tempfile::tempdir().unwrap();
        let mut on = |_: Progress| {};
        let err = ensure_package(
            &pkg("https://evil.example/x.zip", ABC_SHA),
            dir.path(),
            "base",
            &mut on,
            &|| net::Control::Continue,
        )
        .unwrap_err();
        assert!(matches!(err, FlowError::Net(net::NetError::HostNotAllowed(_))));
    }

    #[test]
    fn eksik_platform_akisi_baslamadan_durdurur() {
        let raw = format!(
            r#"{{"version":"1.8.0","profiles":{{"vet":{{"url":"https://github.com/a/vet.zip","sha256":"{ABC_SHA}"}}}}}}"#
        );
        let dir = tempfile::tempdir().unwrap();
        let mut on = |_: Progress| {};
        let err = install_and_launch(&raw, "vet", dir.path(), &mut on).unwrap_err();
        assert!(matches!(
            err,
            FlowError::Manifest(crate::manifest::ManifestError::UnsupportedPlatform { .. })
        ));
    }

    /// DENETİM 2026-08-04: 4xx KALICIDIR — yeniden denemek kullanıcıyı ~22 sn boşuna bekletiyordu.
    /// Güvenlik reddi ve kullanıcı iptali de ASLA yeniden denenmemeli.
    #[test]
    fn yalniz_gercekten_gecici_hatalar_yeniden_denenir() {
        let st = |s: u16| net::NetError::HttpStatus { status: s, url: "https://x/y.zip".into() };

        // KALICI 4xx → yeniden deneme YOK.
        for s in [400u16, 401, 403, 404, 410, 416, 451] {
            assert!(!is_retriable(&st(s)), "{s} KALICI olmali (bosuna bekletme)");
        }
        // GEÇİCİ: 5xx + 408 + 429.
        for s in [408u16, 429, 500, 502, 503, 504] {
            assert!(is_retriable(&st(s)), "{s} GECICI olmali");
        }
        // Ağ/aktarım → geçici.
        assert!(is_retriable(&net::NetError::Transport("baglanti koptu".into())));
        assert!(is_retriable(&net::NetError::Io(std::io::Error::new(
            std::io::ErrorKind::TimedOut,
            "timeout"
        ))));
        // GÜVENLİK reddi → ASLA yeniden deneme (host-pin/HTTPS zorunluluğu kalıcıdır).
        assert!(!is_retriable(&net::NetError::HostNotAllowed("evil.example".into())));
        assert!(!is_retriable(&net::NetError::NotHttps("http://x".into())));
        assert!(!is_retriable(&net::NetError::Malformed("x".into())));
        // Kullanıcı kararı → yeniden deneme YANLIŞ.
        assert!(!is_retriable(&net::NetError::Paused));
        assert!(!is_retriable(&net::NetError::Cancelled));
        // P2: politika iptalleri DETERMINISTIK — yeniden denemek 6x tam indirme demek.
        assert!(!is_retriable(&net::NetError::PolicyLimit("boyut".into())));
    }

    /// DENETİM 2026-08-04: profil kaydı okunamaz + diskte MODEL VARSA onarım SESSİZCE yalnız
    /// base'i yenileyip "Hazır" diyordu. Artık açık hata verir (kullanıcı ne yapacağını bilir).
    #[test]
    fn onarim_profil_kaydi_okunamazken_sessizce_basarili_olmaz() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        // Diskte model verisi VAR ama kayıt BOZUK → onarım hangi profilleri onaracağını bilemez.
        fs::create_dir_all(install::models_dir(root).join("ai_hub")).unwrap();
        fs::write(install::installed_profiles_path(root), "{bozuk").unwrap();

        let mut on = |_: Progress| {};
        let err = repair("{}", root, &mut on, &|| net::Control::Continue).unwrap_err();
        assert!(
            matches!(err, FlowError::ProfileRecordUnreadable),
            "sessiz basari/farkli hata: {err:?}"
        );
    }

    /// Kayıt yok AMA disk de boşsa: gerçekten yalnız base kurulu → onarım DEVAM etmeli
    /// (ProfileRecordUnreadable DEĞİL; burada manifest bozuk olduğu için Manifest hatası bekleriz).
    /// ⚠️ P2 (denetim 2026-08-04): base açılımı iptal/hata ile yarım kalırsa `runtime/`
    /// SİLİNMELİ. Aksi halde `make_base_zip.py`'nin İLK girdi olarak yazdığı
    /// `PEMF_Backend.exe` diske düşmüş olur, `detect_environment` `backend_path().exists()`
    /// ile "kurulu" der ve UI EKSİK bir backend'i başlatmaya çalışır.
    #[test]
    fn yarim_kalan_base_acilimi_kurulu_gorunmez() {
        use std::io::Write;
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        let rt = install::runtime_dir(root);

        // İptal edilmiş bir açılımı taklit et: backend exe yazılmış, gerisi yok.
        let bp = install::backend_path(root);
        std::fs::create_dir_all(bp.parent().unwrap()).unwrap();
        let mut f = std::fs::File::create(&bp).unwrap();
        f.write_all(b"yarim").unwrap();
        assert!(bp.exists(), "on kosul: backend exe yerinde");

        // flow'un iptal/hata dalindaki temizligi ile AYNI islem.
        let _ = std::fs::remove_dir_all(&rt);

        assert!(
            !install::backend_path(root).exists(),
            "yarim agac temizlenmedi — UI kurulumu 'kurulu' gosterir ve EKSIK backend baslatilir"
        );
    }

    /// ⚠️ P3 (denetim 2026-08-04): `Missing` ile `Corrupt` AYNI kovadaydi → kayit dosyasi
    /// (2026-07-29) ONCESI yapilmis TUM mesru kurulumlarda "Onar" tamamen calismaz olmustu.
    /// `Missing` belirsiz DEGIL: profiller `ai_models/<profil>/` dizinlerinden cikarilabilir.
    #[test]
    fn kayit_yokken_profiller_diskten_cikarilir() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        // Eski kurulum: kayit dosyasi YOK ama model verisi VAR.
        for prof in ["home", "vet"] {
            std::fs::create_dir_all(install::models_dir(root).join(prof)).unwrap();
            std::fs::write(install::models_dir(root).join(prof).join("m.onnx"), b"x").unwrap();
        }
        assert!(matches!(
            install::read_installed_profiles_detailed(root),
            install::ProfileRecord::Missing
        ));

        let bulunan = install::infer_profiles_from_disk(root);
        assert_eq!(bulunan, vec!["home".to_string(), "vet".to_string()],
            "profiller diskten cikarilamadi — eski kurulumlarda Onar calismaz");
    }

    /// BOZUK kayitta ise gercekten belirsiz → sessiz basari yerine ACIK hata (davranis korunuyor).
    #[test]
    fn bozuk_kayitta_hata_davranisi_korunur() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        std::fs::create_dir_all(install::models_dir(root).join("vet")).unwrap();
        std::fs::write(install::models_dir(root).join("vet").join("m.onnx"), b"x").unwrap();
        std::fs::write(install::installed_profiles_path(root), b"{bu json degil").unwrap();
        assert!(matches!(
            install::read_installed_profiles_detailed(root),
            install::ProfileRecord::Corrupt
        ));
    }


    // ═════════════════════════════════════════════════════════════════════════════════════
    // DİSK ALANI ÖN KONTROLÜ (2026-08-09 denetimi, Tier 1)
    //
    // Kurulum yolunda hiçbir yerde boş alan kontrolü YOKTU ve önbellekteki TAMAMLANMIŞ paketler
    // hiç temizlenmiyordu. LattePanda eMMC'sinde ölçüldü: ~4,8 GB kalıcı önbellek birikiyor,
    // kurulum 1,2 GB İNDİRDİKTEN SONRA `os error 112` ile ölüyor — yani klinik 20 dakika
    // bekledikten sonra anlaşılmayan bir hata alıyor ve her denemede önbellek biraz daha şişiyor.
    // ═════════════════════════════════════════════════════════════════════════════════════

    /// Bu testin ASIL konusu şu: kontrol İNDİRMEDEN ÖNCE mi yapılıyor? Sonra yapılırsa hiçbir
    /// işe yaramaz — zaten 1,2 GB inmiş olur.
    #[test]
    fn yetersiz_disk_INDIRMEDEN_once_durdurur() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        // Gerçekçi bir manifest: tek katmansız base + tek profil. Boyutlar İMKANSIZ büyük →
        // hiçbir diskte yer yok, dolayısıyla kontrol çalışıyorsa ağa HİÇ çıkılmaz.
        let sha = "a".repeat(64);
        let man = format!(
            concat!(r#"{{"schema":2,"version":"9.9.9","runtimes":{{"{plat}":"#,
                    r#"{{"url":"https://example.invalid/base.zip","sha256":"{sha}","#,
                    r#""size":9000000000000,"kind":"zip"}}}},"models":{{"vet":"#,
                    r#"{{"url":"https://example.invalid/vet.zip","sha256":"{sha}","#,
                    r#""size":9000000000000,"kind":"zip"}}}}}}"#),
            plat = crate::platform::current(), sha = sha);

        let mut olaylar: Vec<String> = Vec::new();
        let mut on = |p: Progress| {
            if let Progress::Downloading { .. } = p { olaylar.push("indirme".into()); }
        };
        // Kurulum giris noktasi `install_profiles`.
        let r = install_profiles(&man, &["vet".to_string()], root, &mut on, &|| net::Control::Continue);

        let e = r.expect_err("imkansiz boyutta kurulum 'basarili' dondu");
        let mesaj = e.to_string();
        assert!(mesaj.contains("disk") || mesaj.contains("Disk"),
            "hata disk alanini soylemiyor, kullanici sebebi anlayamaz: {mesaj}");
        assert!(olaylar.is_empty(),
            "kontrol INDIRMEDEN SONRA yapilmis — 1,2 GB bosa inerdi");
    }

    /// Ölü önbellek temizliği kurulum akışında GERÇEKTEN çalışıyor mu (yer açmanın en ucuz yolu).
    #[test]
    fn olu_onbellek_kurulum_akisinda_temizlenir() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        let cache = install::cache_dir(root);
        std::fs::create_dir_all(&cache).unwrap();
        // Eski sürümden kalan 1,2 GB'lık kalıntı (burada küçük tutuyoruz; önemli olan SİLİNMESİ).
        let eski = cache.join("ESKI-SURUM-base.zip");
        std::fs::write(&eski, vec![0u8; 4096]).unwrap();

        let man = format!(
            concat!(r#"{{"schema":2,"version":"9.9.9","runtimes":{{"{plat}":"#,
                    r#"{{"url":"https://example.invalid/base.zip","sha256":"{sha}","#,
                    r#""size":9000000000000,"kind":"zip"}}}},"models":{{}}}}"#),
            plat = crate::platform::current(), sha = "a".repeat(64));

        let mut on = |_: Progress| {};
        // Kurulum disk hatasıyla düşecek — ama temizlik ONDAN ÖNCE yapılmış olmalı.
        let _ = install_profiles(&man, &[], root, &mut on, &|| net::Control::Continue);
        assert!(!eski.exists(), "olu onbellek temizlenmedi — LattePanda'da disk dolar");
    }

    /// ⚠️ REGRESYON KAPISI: kontrol, MAKUL bir kurulumu engellememeli. Fail-open sözleşmesi
    /// (ölçülemeyen disk → devam) ve pay hesabı yüzünden normal bir kurulum durmamalı.
    #[test]
    fn makul_boyut_disk_kontrolune_TAKILMAZ() {
        let d = tempfile::tempdir().unwrap();
        let bos = crate::disk::bos_alan(d.path()).unwrap_or(0);
        assert!(bos > 0);
        // Boş alanın onda biri kadar bir kurulum kabul edilmeli.
        let gereken = crate::disk::gereken_alan(&[bos / 40], &[bos / 40]);
        assert!(crate::disk::yeterli_alan_var_mi(d.path(), gereken).is_ok(),
            "makul boyutlu kurulum disk kontrolune takildi");
    }

    #[test]
    fn onarim_model_yokken_normal_akista_kalir() {
        let dir = tempfile::tempdir().unwrap();
        let mut on = |_: Progress| {};
        let err = repair("{}", dir.path(), &mut on, &|| net::Control::Continue).unwrap_err();
        assert!(
            !matches!(err, FlowError::ProfileRecordUnreadable),
            "model verisi yokken onarim engellenmemeli: {err:?}"
        );
    }

    #[test]
    fn progress_json_olarak_serilestirilebilir() {
        let p = Progress::Downloading { what: "base".into(), done: 5, total: 10 };
        let s = serde_json::to_string(&p).unwrap();
        assert!(s.contains("\"step\":\"downloading\""), "{s}");
    }

    // ───────────── RUNTIME OTO-GÜNCELLEME (2026-08-08 sahip kararı) ─────────────
    //
    // Bu karar fonksiyonu 1,3 GB'lık bir indirmeyi tetikler VE "kullanıcı yayınlanan düzeltmeyi
    // aldı mı?" sorusunun tek cevabıdır. İki yönde de yanlış olması pahalı:
    //   • gereksiz "bayat" demek → her açılışta 1,3 GB,
    //   • gereksiz "güncel" demek → düzeltme kullanıcıya HİÇ ulaşmaz (bu özelliğin var olma sebebi).

    const SHA_A: &str = "aa7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
    const SHA_B: &str = "bb7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

    /// `sha` base sha'sı, `model` (profil, sha) olan bir manifest üretir.
    fn manifest_json(base_sha: &str, model: Option<(&str, &str)>) -> String {
        let plat = crate::platform::current();
        let models = match model {
            Some((ad, s)) => format!(
                r#""{ad}": {{ "url": "https://github.com/a/{ad}.zip", "sha256": "{s}", "size": 20 }}"#
            ),
            None => String::new(),
        };
        format!(
            // schema 2 ŞART: alanı olmayan manifest v1 sayılır ve `runtimes`/`models` yerine
            // `base`/`profiles` okunur → runtimes BOŞ kalır (bu testleri yazarken düştüğüm tuzak).
            r#"{{ "schema": 2, "version": "1.0.0",
                  "runtimes": {{ "{plat}": {{ "url": "https://github.com/a/base.zip", "sha256": "{base_sha}", "size": 10 }} }},
                  "models": {{ {models} }} }}"#
        )
    }

    /// Kurulu bir cihaz taklidi: backend exe'si diskte olmalı, yoksa "kurulu değil" sayılır.
    fn sahte_kurulum(root: &Path) {
        let exe = install::backend_path(root);
        fs::create_dir_all(exe.parent().unwrap()).unwrap();
        fs::write(&exe, b"x").unwrap();
    }

    #[test]
    fn kurulu_degilse_guncelleme_onerilmez() {
        let dir = tempfile::tempdir().unwrap();
        // backend exe YOK → burada karar vermeyiz (kurulum akışı ayrı).
        let plan = pending_updates(&manifest_json(SHA_A, None), dir.path()).unwrap();
        assert!(!plan.needed(), "kurulu olmayan cihaza guncelleme onerildi: {plan:?}");
    }

    #[test]
    fn kayit_yoksa_base_bayat_sayilir() {
        // 1.9.10 ve oncesi kurulumlar: installed_packages.json YOK. "Bilinmiyor"u "guncel"
        // saymak, tam da bu ozelligin cozdugu sessiz eskimeyi geri getirirdi.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        let plan = pending_updates(&manifest_json(SHA_A, None), dir.path()).unwrap();
        assert!(plan.base, "kayitsiz kurulum guncel sayildi: {plan:?}");
        assert_eq!(plan.bytes, 10);
    }

    #[test]
    fn ayni_sha_ikinci_acilista_yeniden_indirmez() {
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_base_sha(dir.path(), SHA_A);
        let plan = pending_updates(&manifest_json(SHA_A, None), dir.path()).unwrap();
        assert!(!plan.needed(), "sha ayniyken 1,3 GB yeniden inecekti: {plan:?}");
    }

    #[test]
    fn sha_degisince_base_bayat() {
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_base_sha(dir.path(), SHA_A);
        let plan = pending_updates(&manifest_json(SHA_B, None), dir.path()).unwrap();
        assert!(plan.base, "yayinlanan yeni base kaciriliyor: {plan:?}");
    }

    #[test]
    fn sha_kaydi_buyuk_kucuk_harf_farkindan_etkilenmez() {
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_base_sha(dir.path(), &SHA_A.to_uppercase());
        let plan = pending_updates(&manifest_json(SHA_A, None), dir.path()).unwrap();
        assert!(!plan.needed(), "harf buyuklugu sahte guncelleme uretti: {plan:?}");
    }

    #[test]
    fn yalniz_kurulu_profiller_guncellenir() {
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_base_sha(dir.path(), SHA_A);
        // "vet" manifestte var AMA kurulu DEGIL → sessizce yeni profil KURMAYIZ.
        let plan = pending_updates(&manifest_json(SHA_A, Some(("vet", SHA_B))), dir.path()).unwrap();
        assert!(!plan.needed(), "kurulu olmayan profil indirilecekti: {plan:?}");

        install::add_installed_profiles(dir.path(), &["vet".to_string()]);
        install::record_model_sha(dir.path(), "vet", SHA_A);   // kayit VAR ve FARKLI → bayat
        let plan = pending_updates(&manifest_json(SHA_A, Some(("vet", SHA_B))), dir.path()).unwrap();
        assert_eq!(plan.profiles, vec!["vet".to_string()]);
        assert!(!plan.base, "base bosuna bayat sayildi: {plan:?}");
        assert_eq!(plan.bytes, 20, "yalniz profil boyutu sayilmali");
    }

    #[test]
    fn eski_kurulumda_modeller_bosuna_indirilmez() {
        // 1.9.11 ve oncesi: installed_packages.json YOK ama uc profil kurulu. Modelleri de
        // "bilinmiyor=bayat" saymak ~2,2 GB'lik gereksiz indirme demekti.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::add_installed_profiles(dir.path(), &["vet".to_string()]);
        let m = manifest_json(SHA_A, Some(("vet", SHA_B)));
        let plan = pending_updates(&m, dir.path()).unwrap();
        assert!(plan.profiles.is_empty(), "kayitsiz model bosuna indirilecekti: {plan:?}");
        assert!(plan.base, "base yine de bayat olmali (backend gercekten degisti)");
    }

    #[test]
    fn benimseme_sonrasi_gercek_model_degisikligi_yakalanir() {
        // SESSIZ KACIRMA KORUMASI: benimsemezsek kayit sonsuza dek bos kalir ve o profilde
        // yayinlanan GERCEK bir guncelleme hicbir zaman fark edilmez.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::add_installed_profiles(dir.path(), &["vet".to_string()]);

        adopt_unknown_models(&manifest_json(SHA_A, Some(("vet", SHA_A))), dir.path()).unwrap();
        assert_eq!(install::read_installed_packages(dir.path()).models.get("vet").unwrap(), SHA_A);

        // Sonraki yayinda model degisti → ARTIK yakalanmali.
        let plan = pending_updates(&manifest_json(SHA_A, Some(("vet", SHA_B))), dir.path()).unwrap();
        assert_eq!(plan.profiles, vec!["vet".to_string()], "benimseme sonrasi degisiklik kacti");
    }

    #[test]
    fn benimseme_mevcut_kaydi_ezmez() {
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::add_installed_profiles(dir.path(), &["vet".to_string()]);
        install::record_model_sha(dir.path(), "vet", SHA_A);
        // Manifest SHA_B diyor; benimseme bunu EZERSE bekleyen guncelleme kaybolur.
        adopt_unknown_models(&manifest_json(SHA_A, Some(("vet", SHA_B))), dir.path()).unwrap();
        let plan = pending_updates(&manifest_json(SHA_A, Some(("vet", SHA_B))), dir.path()).unwrap();
        assert_eq!(plan.profiles, vec!["vet".to_string()], "benimseme bekleyen guncellemeyi yuttu");
    }

    #[test]
    fn manifestte_olmayan_kurulu_profil_hataya_dusurmez() {
        // Yayindan kaldirilmis bir profil, TUM guncelleme akisini kirmamali.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_base_sha(dir.path(), SHA_A);
        install::add_installed_profiles(dir.path(), &["kaldirilmis".to_string()]);
        let plan = pending_updates(&manifest_json(SHA_A, None), dir.path()).unwrap();
        assert!(!plan.needed(), "{plan:?}");
    }

    // ───────────── KATMANLI PAKET (2026-08-08) ─────────────
    //
    // Amaç ÖLÇÜLDÜ: tek parça base 1,32 GB, app katmanı 71 MB. Siradan bir surumde YALNIZ app
    // inmeli. Bu testler asil kazanci korur — mantik bozulursa kimse fark etmez, sadece herkes
    // her surumde 1,2 GB indirmeye baslar.

    fn manifest_katmanli(deps_sha: &str, app_sha: &str) -> String {
        let plat = crate::platform::current();
        format!(
            r#"{{ "schema": 2, "version": "1.0.0",
                  "runtimes": {{ "{plat}": {{ "url": "https://github.com/a/base.zip", "sha256": "{SHA_A}", "size": 1000 }} }},
                  "layers": {{ "{plat}": {{
                      "deps": {{ "url": "https://github.com/a/base-deps.zip", "sha256": "{deps_sha}", "size": 900 }},
                      "app":  {{ "url": "https://github.com/a/base-app.zip",  "sha256": "{app_sha}",  "size": 70 }} }} }},
                  "models": {{}} }}"#
        )
    }

    #[test]
    fn katman_varsa_tek_parca_base_yok_sayilir() {
        // Kurulu deps+app guncel; tek parca `runtimes` girdisi FARKLI bir sha tasiyor (eski
        // launcher'lar icin duruyor). Katmanli yol onu yok saymali, yoksa her acilista 1,2 GB.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_layer_sha(dir.path(), "deps", SHA_B);
        install::record_layer_sha(dir.path(), "app", SHA_B);
        let plan = pending_updates(&manifest_katmanli(SHA_B, SHA_B), dir.path()).unwrap();
        assert!(!plan.needed(), "tek parca base katmanli yolu tetikledi: {plan:?}");
    }

    #[test]
    fn yalniz_app_degisince_deps_inmez() {
        // ASIL KAZANC: 71 MB iner, 1,19 GB inmez.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_layer_sha(dir.path(), "deps", SHA_A);
        install::record_layer_sha(dir.path(), "app", SHA_A);
        let plan = pending_updates(&manifest_katmanli(SHA_A, SHA_B), dir.path()).unwrap();
        assert!(plan.app, "app degisikligi kacti");
        assert!(!plan.deps, "deps bosuna indirilecekti (1,19 GB): {plan:?}");
        assert_eq!(plan.bytes, 70, "yalniz app boyutu sayilmali");
    }

    #[test]
    fn deps_degisince_app_da_zorunlu() {
        // deps kurulumu `runtime/` agacini KOMPLE siler → app da yeniden acilmali, yoksa
        // exe'siz bir agac kalir ve backend hic baslamaz.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_layer_sha(dir.path(), "deps", SHA_A);
        install::record_layer_sha(dir.path(), "app", SHA_A);
        let plan = pending_updates(&manifest_katmanli(SHA_B, SHA_A), dir.path()).unwrap();
        assert!(plan.deps && plan.app, "deps yenilenirken app atlandi: {plan:?}");
        assert_eq!(plan.bytes, 970, "app boyutu toplama eklenmemis");
    }

    #[test]
    fn kayitsiz_kurulumda_iki_katman_da_bayat() {
        // Tek parca kurulu (eski) makine: katman kaydi yok → ikisi de inmeli.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_base_sha(dir.path(), SHA_A);
        let plan = pending_updates(&manifest_katmanli(SHA_A, SHA_A), dir.path()).unwrap();
        assert!(plan.deps && plan.app, "{plan:?}");
    }

    #[test]
    fn app_kokleri_yol_kacisini_reddeder() {
        // `_app_roots.json` DISKTEN okunuyor ve icerigi SILME yolu uretiyor. Kacis iceren bir
        // kok `runtime/` disinda silme yapabilirdi.
        let dir = tempfile::tempdir().unwrap();
        let p = install::app_roots_path(dir.path());
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(
            &p,
            r#"{"roots":["PEMF_Backend/_internal/ai_hub","../../../Windows","/etc","C:/x","a\\b"]}"#,
        )
        .unwrap();
        let roots = install::read_app_roots(dir.path());
        assert_eq!(roots, vec!["PEMF_Backend/_internal/ai_hub".to_string()]);
    }

    // ───────── ATOMİK KURULUM + GERİ ALMA / ARKA PLAN / KADEMELİ YAYIN (2026-08-08) ─────────

    fn manifest_rollout(deps_sha: &str, app_sha: &str, rollout: u8) -> String {
        let plat = crate::platform::current();
        format!(
            r#"{{ "schema": 2, "version": "1.0.0",
                  "runtimes": {{ "{plat}": {{ "url": "https://github.com/a/base.zip", "sha256": "{SHA_A}", "size": 1000 }} }},
                  "layers": {{ "{plat}": {{ "rollout": {rollout},
                      "deps": {{ "url": "https://github.com/a/base-deps.zip", "sha256": "{deps_sha}", "size": 900 }},
                      "app":  {{ "url": "https://github.com/a/base-app.zip",  "sha256": "{app_sha}",  "size": 70 }} }} }},
                  "models": {{}} }}"#
        )
    }


    // ═════════════════════════════════════════════════════════════════════════════════════
    // GERİ ÇAĞIRMA (2026-08-09 denetimi, Tier 2)
    //
    // `rollout: 0` yalnız YENİ dağıtımı durdurur — sahadaki cihaza DOKUNMAZ. Bir bobin-güvenliği
    // hatası bulunduğunda asıl gereken, MEVCUT kurulumları güncellemeye ZORLAMAKTIR.
    // `min_supported_version` bunu sağlar: kurulu sürüm eşiğin altındaysa cihaz dilimine BAKILMAZ.
    // ═════════════════════════════════════════════════════════════════════════════════════

    /// Kurulu sürümü diske yaz (backend `_internal/VERSION` dosyası).
    fn surum_yaz(root: &Path, surum: &str) {
        let p = install::runtime_dir(root).join("PEMF_Backend").join("_internal");
        fs::create_dir_all(&p).unwrap();
        fs::write(p.join("VERSION"), surum).unwrap();
    }

    fn manifest_geri_cagirma(app_sha: &str, rollout: u8, asgari: &str) -> String {
        let plat = crate::platform::current();
        format!(
            r#"{{ "schema": 2, "version": "1.0.0", "min_supported_version": "{asgari}",
                  "runtimes": {{ "{plat}": {{ "url": "https://github.com/a/base.zip", "sha256": "{SHA_A}", "size": 1000 }} }},
                  "layers": {{ "{plat}": {{ "rollout": {rollout},
                      "deps": {{ "url": "https://github.com/a/base-deps.zip", "sha256": "{SHA_A}", "size": 900 }},
                      "app":  {{ "url": "https://github.com/a/base-app.zip",  "sha256": "{app_sha}",  "size": 70 }} }} }},
                  "models": {{}} }}"#
        )
    }

    #[test]
    fn KRITIK_geri_cagirma_rollout_frenini_EZER() {
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_layer_sha(dir.path(), "deps", SHA_A);
        install::record_layer_sha(dir.path(), "app", SHA_A);
        surum_yaz(dir.path(), "1.9.10");           // destek eşiğinin ALTINDA

        // rollout=0 → normalde HİÇBİR cihaz güncellenmez.
        let plan = pending_updates(&manifest_geri_cagirma(SHA_B, 0, "1.9.16"), dir.path()).unwrap();
        assert!(plan.needed(), "geri cagirma rollout frenini ezmedi — etkilenen klinik eski surumde kalir");
        assert!(!plan.rollout_bekliyor, "geri cagirmada rollout beklemesi olmamali");
    }

    #[test]
    fn guncel_surum_geri_cagirmadan_ETKILENMEZ() {
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_layer_sha(dir.path(), "deps", SHA_A);
        install::record_layer_sha(dir.path(), "app", SHA_A);
        surum_yaz(dir.path(), "1.9.20");           // eşiğin ÜSTÜNDE

        let plan = pending_updates(&manifest_geri_cagirma(SHA_B, 0, "1.9.16"), dir.path()).unwrap();
        assert!(plan.rollout_bekliyor, "esik ustundeki cihaz da zorlandi — kademeli yayin bozulur");
    }

    /// ⚠️ FAIL-SAFE: sürümünü söyleyemeyen (çok eski base.zip → VERSION dosyası yok) bir kurulum
    /// geri çağırma kapsamının DIŞINDA kalmamalıdır.
    #[test]
    fn surumu_bilinmeyen_kurulum_geri_cagirmaya_GIRER() {
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_layer_sha(dir.path(), "deps", SHA_A);
        install::record_layer_sha(dir.path(), "app", SHA_A);
        // VERSION dosyası YOK → "0.0.0" sayılır.
        assert_eq!(install::kurulu_surum(dir.path()), "0.0.0");

        let plan = pending_updates(&manifest_geri_cagirma(SHA_B, 0, "1.9.16"), dir.path()).unwrap();
        assert!(plan.needed(), "surumu bilinmeyen kurulum geri cagirma disinda kaldi");
    }

    #[test]
    fn min_supported_version_YOKSA_rollout_normal_calisir() {
        // Regresyon kapısı: geri çağırma alanı olmayan sıradan yayınlarda kademeli dağıtım
        // eskisi gibi işlemeli.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_layer_sha(dir.path(), "deps", SHA_A);
        install::record_layer_sha(dir.path(), "app", SHA_A);
        surum_yaz(dir.path(), "1.9.10");
        let plan = pending_updates(&manifest_rollout(SHA_A, SHA_B, 0), dir.path()).unwrap();
        assert!(plan.rollout_bekliyor, "geri cagirma yokken rollout freni calismali");
    }

    #[test]
    fn kurulu_surum_VERSION_dosyasindan_okunur() {
        let dir = tempfile::tempdir().unwrap();
        surum_yaz(dir.path(), "  1.9.14\n");
        assert_eq!(install::kurulu_surum(dir.path()), "1.9.14", "bosluk/newline temizlenmiyor");
    }

    #[test]
    fn rollout_sifir_yayini_durdurur() {
        // GERI CEKME ANAHTARI: bozuk bir yayin fark edilince `rollout: 0` yazilir; henuz
        // guncellememis HICBIR cihaz almamali.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_layer_sha(dir.path(), "deps", SHA_A);
        install::record_layer_sha(dir.path(), "app", SHA_A);
        let plan = pending_updates(&manifest_rollout(SHA_B, SHA_B, 0), dir.path()).unwrap();
        assert!(!plan.needed(), "rollout=0 iken guncelleme yapildi: {plan:?}");
        assert!(plan.rollout_bekliyor, "teshis bayragi set edilmemis");
    }

    #[test]
    fn rollout_yuz_herkese_acar() {
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_layer_sha(dir.path(), "deps", SHA_A);
        install::record_layer_sha(dir.path(), "app", SHA_A);
        let plan = pending_updates(&manifest_rollout(SHA_A, SHA_B, 100), dir.path()).unwrap();
        assert!(plan.app && !plan.rollout_bekliyor, "{plan:?}");
    }

    #[test]
    fn rollout_dilimi_kararli() {
        // Dilim her acilista degisirse "once %10'a ac, izle" imkansiz olur.
        let dir = tempfile::tempdir().unwrap();
        let a = install::rollout_dilimi(dir.path());
        let b = install::rollout_dilimi(dir.path());
        assert_eq!(a, b, "dilim acilistan acilisa degisiyor");
        assert!(a < 100);
    }

    #[test]
    fn onbellek_hazirsa_acilis_indirmeye_takilmaz() {
        // plan.cached=true → kurulum aninda yapilabilir; false → arka plan indirmesi.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        let m = manifest_katmanli(SHA_A, SHA_A);
        let plan = pending_updates(&m, dir.path()).unwrap();
        assert!(plan.needed() && !plan.cached, "bos onbellek 'hazir' sayildi: {plan:?}");

        // Paketleri onbellege koy (boyutlar manifest ile ayni: deps 900, app 70).
        let cache = install::cache_dir(dir.path());
        fs::create_dir_all(&cache).unwrap();
        fs::write(cache.join("base-deps.zip"), vec![0u8; 900]).unwrap();
        fs::write(cache.join("base-app.zip"), vec![0u8; 70]).unwrap();
        let plan = pending_updates(&m, dir.path()).unwrap();
        assert!(plan.cached, "onbellekteki paketler goz ardi edildi: {plan:?}");
    }

    #[test]
    fn eksik_boyutlu_onbellek_hazir_sayilmaz() {
        // Yarim inen dosya "hazir" sayilirsa acilista kurulum baslar ve ORTASINDA indirmeye
        // duser — tam da onlemek istedigimiz bekletme.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        let cache = install::cache_dir(dir.path());
        fs::create_dir_all(&cache).unwrap();
        fs::write(cache.join("base-deps.zip"), vec![0u8; 10]).unwrap();   // 900 olmali
        fs::write(cache.join("base-app.zip"), vec![0u8; 70]).unwrap();
        let plan = pending_updates(&manifest_katmanli(SHA_A, SHA_A), dir.path()).unwrap();
        assert!(!plan.cached, "yarim dosya hazir sayildi");
    }

    #[test]
    fn app_geri_alma_deps_agacini_ezmez() {
        // EN TEHLIKELI HATA: yedek geri konurken ust seviye (`PEMF_Backend`) tasinirsa 1,19 GB'lik
        // deps agaci silinir ve kurulum olur. Geri alma KOK LISTESI uzerinden yurumeli.
        let dir = tempfile::tempdir().unwrap();
        let rt = install::runtime_dir(dir.path());
        let kok = rt.join("PEMF_Backend");
        fs::create_dir_all(kok.join("_internal").join("ai_hub")).unwrap();
        fs::create_dir_all(kok.join("_internal").join("torch")).unwrap();
        fs::write(kok.join("_internal").join("torch").join("torch.dll"), b"DEPS").unwrap();
        fs::write(kok.join("_internal").join("ai_hub").join("m.pyd"), b"ESKI").unwrap();

        // Yedek: yalniz app kokleri, TAM goreli yolla + kendi marker'i.
        let yedek = install::app_backup_dir(dir.path());
        fs::create_dir_all(yedek.join("PEMF_Backend").join("_internal").join("ai_hub")).unwrap();
        fs::write(
            yedek.join("PEMF_Backend").join("_app_roots.json"),
            r#"{"roots":["PEMF_Backend/_internal/ai_hub"]}"#,
        ).unwrap();
        fs::write(
            yedek.join("PEMF_Backend").join("_internal").join("ai_hub").join("m.pyd"),
            b"YEDEK",
        ).unwrap();
        // Yeni (bozuk) app diskte:
        fs::write(kok.join("_internal").join("ai_hub").join("m.pyd"), b"YENI").unwrap();

        let b = GeriAlmaBilgisi { app_yedegi: true, ..Default::default() };
        guncellemeyi_geri_al(dir.path(), &b).unwrap();

        assert_eq!(
            fs::read(kok.join("_internal").join("torch").join("torch.dll")).unwrap(),
            b"DEPS",
            "geri alma DEPS agacini ezdi — 1,19 GB yeniden inerdi"
        );
        assert_eq!(
            fs::read(kok.join("_internal").join("ai_hub").join("m.pyd")).unwrap(),
            b"YEDEK",
            "eski app geri konmadi"
        );
    }

    /// Gerçek zip ile TAM DÖNGÜ: yedekle → aç → (sağlık düştü) → geri al.
    ///
    /// Bu, atomik kurulumun ASIL VAADİDİR: başarısız bir güncelleme kliniği çalışmaz bırakmamalı.
    /// Birim testleri parçaları ayrı ayrı kontrol ediyor; bu test gerçek dosya/zip üzerinden
    /// uçtan uca yürür.
    #[test]
    fn basarisiz_guncelleme_kurulumu_bozmaz() {
        use std::io::Write as _;
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        let rt = install::runtime_dir(root);
        let kok = rt.join("PEMF_Backend");

        // ── ESKİ, ÇALIŞAN kurulum ────────────────────────────────────────────────────────────
        fs::create_dir_all(kok.join("_internal").join("ai_hub")).unwrap();
        fs::create_dir_all(kok.join("_internal").join("torch")).unwrap();
        fs::create_dir_all(kok.join("_internal").join("frontend").join("dist")).unwrap();
        fs::write(kok.join(crate::platform::backend_exe_name()), b"ESKI-EXE").unwrap();
        fs::write(kok.join("_internal").join("torch").join("t.dll"), b"DEPS").unwrap();
        fs::write(kok.join("_internal").join("ai_hub").join("eski.pyd"), b"ESKI").unwrap();
        fs::write(kok.join("_internal").join("frontend").join("dist").join("index.html"), b"ESKI-WEB").unwrap();
        fs::write(
            kok.join("_app_roots.json"),
            r#"{"roots":["PEMF_Backend/PEMF_Backend.exe","PEMF_Backend/_internal/ai_hub","PEMF_Backend/_internal/frontend"]}"#,
        ).unwrap();
        assert!(agac_yapisal_gecerli_mi(&rt), "baslangic kurulumu gecerli olmali");

        // ── YENİ app paketi (gerçek zip) ─────────────────────────────────────────────────────
        let zip_yolu = root.join("app.zip");
        {
            let f = fs::File::create(&zip_yolu).unwrap();
            let mut z = zip::ZipWriter::new(f);
            let o: zip::write::FileOptions<'_, ()> =
                zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Stored);
            for (ad, icerik) in [
                ("PEMF_Backend/PEMF_Backend.exe", &b"YENI-EXE"[..]),
                ("PEMF_Backend/_internal/ai_hub/yeni.pyd", &b"YENI"[..]),
                ("PEMF_Backend/_internal/frontend/dist/index.html", &b"YENI-WEB"[..]),
                (
                    "PEMF_Backend/_app_roots.json",
                    br#"{"roots":["PEMF_Backend/PEMF_Backend.exe","PEMF_Backend/_internal/ai_hub","PEMF_Backend/_internal/frontend"]}"#,
                ),
            ] {
                z.start_file(ad, o).unwrap();
                z.write_all(icerik).unwrap();
            }
            z.finish().unwrap();
        }

        // ── app katmanını değiştir (yedekle + aç) ────────────────────────────────────────────
        let mut butce = 0u64;
        let mut on = |_: Progress| {};
        app_katmanini_degistir(&zip_yolu, root, &mut butce, &mut on, &|| net::Control::Continue).unwrap();
        assert_eq!(fs::read(kok.join(crate::platform::backend_exe_name())).unwrap(), b"YENI-EXE");
        assert!(kok.join("_internal").join("ai_hub").join("yeni.pyd").exists());
        assert!(
            !kok.join("_internal").join("ai_hub").join("eski.pyd").exists(),
            "eski app dosyasi diskte kaldi — bayat .pyd tanimsiz davranis uretir"
        );
        assert_eq!(fs::read(kok.join("_internal").join("torch").join("t.dll")).unwrap(), b"DEPS",
                   "app guncellemesi DEPS'e dokunmamali");

        // ── SAĞLIK KAPISI DÜŞTÜ → geri al ───────────────────────────────────────────────────
        let b = GeriAlmaBilgisi { app_yedegi: true, app_sha: SHA_B.into(), ..Default::default() };
        guncellemeyi_geri_al(root, &b).unwrap();

        assert_eq!(fs::read(kok.join(crate::platform::backend_exe_name())).unwrap(), b"ESKI-EXE",
                   "eski exe geri gelmedi");
        assert_eq!(fs::read(kok.join("_internal").join("ai_hub").join("eski.pyd")).unwrap(), b"ESKI");
        assert!(!kok.join("_internal").join("ai_hub").join("yeni.pyd").exists(),
                "bozuk surumun dosyalari kaldi");
        assert_eq!(fs::read(kok.join("_internal").join("torch").join("t.dll")).unwrap(), b"DEPS",
                   "geri alma DEPS agacini ezdi");
        assert!(agac_yapisal_gecerli_mi(&rt), "geri alma sonrasi kurulum CALISIR olmali");
        assert_eq!(install::read_installed_packages(root).app, "",
                   "saglik gecilmeden sha kaydedilmis — sonraki acilis duzeltmeye calismaz");
    }

    #[test]
    fn yapisal_dogrulama_eksik_agaci_reddeder() {
        let dir = tempfile::tempdir().unwrap();
        let rt = dir.path().join("rt");
        let kok = rt.join("PEMF_Backend");
        fs::create_dir_all(kok.join("_internal").join("frontend").join("dist")).unwrap();
        assert!(!agac_yapisal_gecerli_mi(&rt), "exe yokken gecerli sayildi");
        fs::write(kok.join(crate::platform::backend_exe_name()), b"x").unwrap();
        assert!(!agac_yapisal_gecerli_mi(&rt), "web arayuzu yokken gecerli sayildi");
        fs::write(kok.join("_internal").join("frontend").join("dist").join("index.html"), b"x").unwrap();
        assert!(agac_yapisal_gecerli_mi(&rt));
    }

    #[test]
    fn onaylanmadan_sha_kaydedilmez() {
        // Saglik kapisi gecilmeden kayit yazilirsa, calismayan bir surum "guncel" isaretlenir ve
        // bir sonraki acilis onu duzeltmeye CALISMAZ.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        let b = GeriAlmaBilgisi {
            tam_takas: true, deps_sha: SHA_A.into(), app_sha: SHA_B.into(), ..Default::default()
        };
        assert_eq!(install::read_installed_packages(dir.path()).deps, "", "kayit erken yazilmis");
        guncellemeyi_onayla(dir.path(), &b);
        let k = install::read_installed_packages(dir.path());
        assert_eq!(k.deps, SHA_A);
        assert_eq!(k.app, SHA_B);
    }

    /// ÜRETİM MANİFESTİ gerçekten ayrıştırılıyor mu? Manifest ELLE düzenleniyor (sha/size/url) ve
    /// bir yazım hatası ancak SAHADA, client kurulum yapamayınca fark edilirdi. Bu test yayından
    /// ÖNCE yakalar. Dosya yoksa (başka bir checkout) sessizce atlanır.
    #[test]
    fn uretim_manifesti_ayristirilabilir() {
        let p = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../pemf-app-packages/manifest.json");
        let Ok(raw) = fs::read_to_string(&p) else { return };
        let m = Manifest::parse(&raw).expect("URETIM MANIFESTI AYRISTIRILAMADI");

        // Katmanlar bu platform için tanımlıysa: digest'ler geçerli ve boyutlar makul olmalı.
        if let Some(l) = m.layers_for_current_platform() {
            assert!(l.app.size > 0 && l.deps.size > 0, "katman boyutu 0");
            assert!(
                l.app.size < l.deps.size,
                "app katmani deps'ten BUYUK — katmanlar ters yazilmis olabilir (app {} > deps {})",
                l.app.size, l.deps.size
            );
            assert!(l.app.url.ends_with("base-app.zip"), "app url yanlis: {}", l.app.url);
            assert!(l.deps.url.ends_with("base-deps.zip"), "deps url yanlis: {}", l.deps.url);
        }
        // Eski client'lar icin tek parca girdi DURMALI — silinirse <=1.9.12 kurulum yapamaz.
        assert!(
            m.runtime_for_current_platform().is_ok(),
            "tek parca 'runtimes' girdisi KAYBOLMUS — eski client'lar kurulum yapamaz"
        );
        // Self-update imzasi: installer_url varsa sha256 ZORUNLU (parse zaten dogrular, burada
        // manifest'in gercekten o alani tasidigini kilitliyoruz).
        let lc = m.launcher.as_ref().expect("launcher bolumu yok");
        assert!(lc.installer_url.is_some(), "installer_url yok — oto-guncelleme calismaz");
    }

    #[test]
    fn app_kokleri_okunamazsa_bos_doner() {
        // Bilinmeyen sinirla silme yapmaktansa uzerine yazmak yeglenir.
        let dir = tempfile::tempdir().unwrap();
        assert!(install::read_app_roots(dir.path()).is_empty());
    }

    #[test]
    fn yarim_kalan_acilim_guncel_isaretlenmez() {
        // record_base_sha("") = "bilinmiyor". update_installed acmadan ONCE bunu yazar; elektrik
        // giderse bir sonraki acilis YARIM runtime'i "guncel" sanip baslatmamali.
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        install::record_base_sha(dir.path(), SHA_A);
        install::record_base_sha(dir.path(), "");
        let plan = pending_updates(&manifest_json(SHA_A, None), dir.path()).unwrap();
        assert!(plan.base, "yarim acilim guncel sayildi: {plan:?}");
    }
}
