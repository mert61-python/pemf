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
    #[error("{}", crate::dil::t_ile("rust.acma.dosyaSistemi", &[("hata", &(.0).to_string())]))]
    Io(#[from] std::io::Error),
    /// DENETİM 2026-08-04: onarım, hangi profillerin kurulu olduğunu bilmeden model paketlerini
    /// SESSİZCE atlayıp "Hazır" diyordu. Artık kullanıcıya ne yapacağını söyleyen açık hata.
    #[error("{}", crate::dil::t("rust.kurulum.kayitOkunamadi"))]
    ProfileRecordUnreadable,
    /// Profil kaldirma reddi (denetim 2026-09-06). Metin NE olduğunu ve NE yapilacagini soyler;
    /// UI dogrudan gosterir. Hicbir dosya silinmeden once uretilir (bkz. `remove_profiles`).
    #[error("{0}")]
    ProfilKaldirma(String),
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
    // LN L10 · D4.15: TEK KAYNAK — kural (Io / Transport / Dns / 5xx · 408 · 429 geçici; PolicyLimit / LocalIo / güvenlik reddi /
    // kullanıcı kararı kalıcı) `net::gecici_hata_mi`'de; manifest çekimi (`denemeli_cek`) aynı kuralı kullanır.
    net::gecici_hata_mi(e)
}

/// C2 (denetim 2026-08-24): `update_installed` hatası DENEME sayacına (geri-alma döngü kırıcısı)
/// yazılmalı mı?
///
/// DETERMİNİSTİK hatalar (kilitli model / AV karantinası / eksik-exe / bozuk manifest / güvenlik
/// reddi) HER açılışta tekrarlanır — sağlık kapısı geri alması sayaç yazıyordu ama `update_installed`
/// İÇİNDEKİ açılım/profil/yapısal hataları YAZMIYORDU → o sınıf döngü kırıcısına (`otomatik_durduruldu`)
/// HİÇ takılmadan her açılışta backend'i öldürüp deps açıp geri alıyordu. Bu sınıfı `true` işaretler.
///
/// ⚠️ Kullanıcı iptali/duraklatması (Cancel/Pause) ve GEÇİCİ ağ hataları (yeniden denenir) `false`:
/// kör sayım iki kullanıcı iptalini döngü-kırıcıya saydırır ya da geçici bir ağ hatası düzeltme
/// yayınını kalıcı bloklardı. (`apply_runtime_update` Cancel/Pause'u zaten önce ayırır; burada
/// savunma-derinliği + saf-fonksiyon tamlığı.)
pub fn hata_deterministik_mi(e: &FlowError) -> bool {
    match e {
        FlowError::Net(net::NetError::Paused | net::NetError::Cancelled) => false,
        FlowError::Extract(extract::ExtractError::Cancelled) => false,
        // Geçici ağ/IO → yeniden denenir, deneme sayma.
        FlowError::Net(ne) => !is_retriable(ne),
        // Extract(non-Cancel) / Manifest / Verify / Backend / Io / ProfileRecordUnreadable →
        // deterministik başarısızlık, say.
        _ => true,
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

/// Bekleyen güncelleme planının `.part` yolları = İPTAL temizliğinin KORUMA listesi.
///
/// `prefetch_updates` TAM OLARAK bu paketleri indirir, dolayısıyla bu liste "o an inen dosyalar"a
/// eşittir. Manifest/plan okunamazsa BOŞ döner (fail-safe: hiçbir şey korunmaz DEĞİL — çağıran
/// manifest yokken temizliği hiç yapmaz).
pub fn plan_part_paths(manifest_raw: &str, install_root: &Path) -> Vec<PathBuf> {
    let (Ok(plan), Ok(manifest)) = (
        pending_updates(manifest_raw, install_root),
        Manifest::parse(manifest_raw),
    ) else {
        return Vec::new();
    };
    let cache = install::cache_dir(install_root);
    plan_paketleri(&manifest, &plan)
        .into_iter()
        .map(|(p, etiket)| net::part_path(&cache_path_for(p, &cache, &etiket), &p.sha256))
        .collect()
}

/// İndirilen paketin SHA doğrulaması + uyuşmazlıkta TEK SEFERLİK temiz yeniden indirme.
///
/// ⚠️ SAHA ŞİKÂYETİ 2026-08-11: kullanıcı güncellemede "SHA256 UYUŞMADI — dosya bozuk ya da değiştirilmiş" gördü; oysa hem
/// yayındaki paket hem sonradan inen kopya DOĞRUYDU (ikisi de manifest sha'sıyla birebir). Bozulma İNDİRME sırasında oluşan
/// geçici bir durumdu — ama 6-denemeli retry YALNIZ ağ hatalarını kapsıyor; "indi ama sha tutmadı" hâli kullanıcıya hemen hata
/// olarak çıkıyordu. ÇÖZÜM: sha uyuşmazlığında SIFIRDAN bir kez daha indir; ikinci kez de tutmazsa hata gerçektir ve yukarı
/// çıkar — güvenlik doğrulaması ZAYIFLATILMAZ, yalnız bir kez telafi edilir. Kullanıcı duraklattı/iptal ettiyse telafi YOK.
///
/// D5.20 (B-10.90): karar ve akış eskiden `ensure_package`in içindeydi ve yalnız METİN çapasıyla kapılıydı (`if false && …`
/// mutantı 3+13+62 testte YEŞİL). Ağ katmanı (HTTPS + host pini) test edilemediği için yeniden indirme ENJEKTE edilir;
/// birim testleri bu fonksiyonu gerçek dosya + gerçek `verify` ile koşturur.
fn dogrula_ya_da_bir_kez_temiz_indir(
    dest: &Path,
    sha256: &str,
    label: &str,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
    temiz_yeniden_indir: &mut dyn FnMut(&mut dyn FnMut(Progress)) -> Result<(), FlowError>,
) -> Result<(), FlowError> {
    on(Progress::Verifying { what: label.to_string() });
    if let Err(e) = verify::verify_file(dest, sha256) {
        // Bozuk dosyayı BIRAKMA: kalırsa sonraki kurulum onu "önbellek" sanıp aynı hataya tekrar düşer.
        let _ = fs::remove_file(dest);
        if temiz_yeniden_indirilebilir(control) {
            on(Progress::Reconnecting { what: label.to_string(), attempt: 1, max: 1 });
            temiz_yeniden_indir(on)?;
            on(Progress::Verifying { what: label.to_string() });
            if let Err(e2) = verify::verify_file(dest, sha256) {
                let _ = fs::remove_file(dest);
                return Err(e2.into());
            }
            return Ok(());
        }
        return Err(e.into());
    }
    Ok(())
}

pub fn ensure_package(
    pkg: &crate::Package,
    cache: &Path,
    label: &str,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<PathBuf, FlowError> {
    let uyu = |ms: u64| std::thread::sleep(std::time::Duration::from_millis(ms));
    ensure_package_ile(pkg, cache, label, on, control, &net::download_to_file, &uyu)
}

/// Paket indirici — `net::download_to_file` ile AYNI imza (url, hedef, beklenen boyut, beklenen sha, ilerleme, denetim).
pub(crate) type Indirici<'a> =
    dyn Fn(&str, &Path, u64, &str, net::ProgressFn<'_>, &dyn Fn() -> net::Control) -> Result<u64, net::NetError> + 'a;

/// `ensure_package`'ın gövdesi — indirici ve denemeler arası bekleme ENJEKTE (KP-4 A2; üretimde `net::download_to_file` +
/// `thread::sleep`). Önbellek doğrulaması, 6 deneme, geçici-hata ayrımı, Duraklat / İptal yanıtı ve tek temiz yeniden indirme AYNEN.
pub(crate) fn ensure_package_ile(
    pkg: &crate::Package,
    cache: &Path,
    label: &str,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
    indir: &Indirici<'_>,
    uyu: &dyn Fn(u64),
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
            indir(&pkg.url, &dest, pkg.size, &pkg.sha256, &mut cb, control)
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
                    uyu(200);
                    waited += 200;
                }
            }
        }
    }

    // Telafi kolunun TEMİZ yeniden indirmesi: `.part` SİLİNİR (Range ile devam DEĞİL, tam yeniden indirme).
    let mut temiz_yeniden_indir = |on: &mut dyn FnMut(Progress)| -> Result<(), FlowError> {
        let _ = fs::remove_file(net::part_path(&dest, &pkg.sha256));
        let mut cb = |done, total| {
            on(Progress::Downloading { what: label.to_string(), done, total });
        };
        indir(&pkg.url, &dest, pkg.size, &pkg.sha256, &mut cb, control)?;
        Ok(())
    };
    dogrula_ya_da_bir_kez_temiz_indir(&dest, &pkg.sha256, label, on, control, &mut temiz_yeniden_indir)?;
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
/// DİSK KAPISI + ÖLÜ ÖNBELLEK TEMİZLİĞİ — indirmeye başlamadan ÖNCE.
///
/// 2026-08-09 denetimi bunu ÖLÇEREK ekledi (LattePanda eMMC: ~4,8 GB kalıcı önbellek birikiyor,
/// kurulum 1,2 GB indirdikten SONRA `os error 112` ile ölüyor; klinik 20 dk bekleyip anlaşılmaz
/// bir hata alıyor). AMA kapı yalnız `install_profiles`e kondu — yani KULLANICININ İZLEDİĞİ ilk
/// kurulum yoluna. GÖZETİMSİZ koşan oto-güncelleme (`update_installed`) ve arka plan indirme
/// (`prefetch_updates`) korumasız kaldı (denetim 2026-08-16, Bulgu 2). Burada tek kaynağa alındı.
///
/// `kurulum_da_yapilacak`:
///   • `true`  — indirilen zip AÇILACAK da → yer 2× (zip + ağaç) + zaten önbellektekilerin açılımı.
///   • `false` — yalnız ÖN-İNDİRME (prefetch): sadece zip'in yeri gerekir, açma yok.
///
/// Sıra ÖNEMLİ: önce ölü önbelleği temizle (yer aç), SONRA karar ver — aksi hâlde eski
/// sürümlerin kalıntısı yüzünden gereksiz yere "yer yok" derdik.
/// [Onar/önbellek çelişkisi — sahip onayı 2026-08-20] Bu cihazla İLGİLİ güncel-manifest paket
/// adları: platformun katmanları (deps+app) ya da base runtime'ı + KURULU profillerin modelleri.
/// Ölü-önbellek temizliği bunları da korur. Üretim URL'leri paket başına SABİTTİR (assetler aynı
/// etikete --clobber ile yüklenir) → bu adlar eski ve yeni sürümün AYNI önbellek adıdır; temizlik
/// böylece yalnız GERÇEKTEN ölü (manifestten düşmüş / yeniden adlanmış) girdileri siler. Eski
/// koruma listesi yalnız o işlemin paket kümesiydi: app-only bir oto-güncelleme geçerli deps.zip'i
/// "ölü" diye siliyor, "Onar" 20+ dk indirmeye dönüyor ve UI'ın "indirilenler önbellekten gelir,
/// yeniden İNMEZ" vaadi (ProfileRecordUnreadable metni dahil) boşa çıkıyordu. eMMC disk-kazanım
/// özelliği DURUYOR — yalnız canlı paketler kapsam dışına çıktı.
pub(crate) fn cihazin_guncel_paket_adlari(
    manifest: &Manifest,
    install_root: &Path,
    cache: &Path,
) -> Vec<String> {
    let mut paketler: Vec<(&crate::Package, String)> = Vec::new();
    if let Some(l) = manifest.layers_for_current_platform() {
        paketler.push((&l.deps, "deps".to_string()));
        paketler.push((&l.app, "app".to_string()));
    } else if let Ok(p) = manifest.runtime_for_current_platform() {
        paketler.push((p, "base".to_string()));
    }
    for ad in install::read_installed_profiles(install_root) {
        if let Ok(ciftler) = profil_paketleri(manifest, &ad) {
            paketler.extend(ciftler);
        }
    }
    paketler
        .into_iter()
        .filter_map(|(pkg, etiket)| {
            cache_path_for(pkg, cache, &etiket)
                .file_name()
                .and_then(|s| s.to_str())
                .map(String::from)
        })
        .collect()
}

pub(crate) fn disk_kapisi(
    gerekli: &[(&crate::Package, String)],
    install_root: &Path,
    cache: &Path,
    on: &mut dyn FnMut(Progress),
    kurulum_da_yapilacak: bool,
    ayrica_koru: &[String],
) -> Result<(), FlowError> {
    let mut korunacak: Vec<String> = gerekli
        .iter()
        .filter_map(|(pkg, etiket)| {
            cache_path_for(pkg, cache, etiket)
                .file_name()
                .and_then(|s| s.to_str())
                .map(|s| s.to_string())
        })
        .collect();
    // [Onar/önbellek çelişkisi]: cihazın güncel paketleri de korunur — bkz. cihazin_guncel_paket_adlari.
    korunacak.extend(ayrica_koru.iter().cloned());
    let silinen = crate::disk::olu_onbellek_temizle(cache, &korunacak);
    if silinen > 0 {
        on(Progress::Extracting {
            what: crate::dil::t_ile("rust.kurulum.eskiPaketlerTemizlendi", &[("boyut", &(crate::disk::insan_okur(silinen)).to_string())]),
        });
    }

    let (mut inecek, mut acilacak) = (Vec::new(), Vec::new());
    for (pkg, etiket) in gerekli {
        if paket_onbellekte_hazir(pkg, cache, etiket) {
            if kurulum_da_yapilacak {
                acilacak.push(pkg.size);
            }
        } else {
            inecek.push(pkg.size);
        }
    }
    let gereken = if kurulum_da_yapilacak {
        crate::disk::gereken_alan(&inecek, &acilacak)
    } else {
        // Yalnız indirme: zip kadar yer + aynı emniyet payı.
        crate::disk::gereken_alan(&[], &inecek)
    };
    if let Err((gerek, bos)) = crate::disk::yeterli_alan_var_mi(install_root, gereken) {
        return Err(FlowError::Io(std::io::Error::other(crate::dil::t_ile("rust.kurulum.yetersizDisk", &[("gerek", &(crate::disk::insan_okur(gerek)).to_string()), ("bos", &(crate::disk::insan_okur(bos)).to_string())]))));
    }
    Ok(())
}

/// Bir güncelleme planının dokunacağı TÜM paketleri topla (disk kapısı için).
/// FAZ 4.5 (coklu-model-zip): profilin TUM zip'leri (ana + parcalar) BENZERSIZ
/// onbellek etiketiyle. Parca etiketi "<profil>-p2", "-p3"... — URL adi guvensizse
/// `cache_path_for` etikete duser; ana ile ayni etikete dusup birbirini EZMESIN.
fn profil_paketleri<'a>(
    manifest: &'a Manifest,
    ad: &str,
) -> Result<Vec<(&'a crate::Package, String)>, crate::manifest::ManifestError> {
    let pkgs = manifest.model_packages(ad)?;
    Ok(pkgs
        .into_iter()
        .enumerate()
        .map(|(i, p)| (p, if i == 0 { ad.to_string() } else { format!("{ad}-p{}", i + 1) }))
        .collect())
}

/// FAZ 4.5: `installed_packages.models` kaydindaki BIRLESIK kimlik. TEK parcada ana
/// sha'nin KENDISI — eski kayitlarla birebir, yukseltmede sahte "bayat" uretmez.
/// Cok parcada sha'lar '+' ile birlesir (kayit yalniz ESITLIK kiyasinda kullanilir).
fn birlesik_model_sha(pkgs: &[&crate::Package]) -> String {
    if pkgs.len() == 1 {
        pkgs[0].sha256.clone()
    } else {
        pkgs.iter().map(|p| p.sha256.as_str()).collect::<Vec<_>>().join("+")
    }
}

fn plan_paketleri<'a>(
    manifest: &'a Manifest,
    plan: &UpdatePlan,
) -> Vec<(&'a crate::Package, String)> {
    let mut v: Vec<(&crate::Package, String)> = Vec::new();
    if let Some(l) = manifest.layers_for_current_platform() {
        if plan.deps {
            v.push((&l.deps, "deps".to_string()));
        }
        if plan.app {
            v.push((&l.app, "app".to_string()));
        }
    } else if plan.base {
        if let Ok(p) = manifest.runtime_for_current_platform() {
            v.push((p, "base".to_string()));
        }
    }
    for ad in &plan.profiles {
        if let Ok(ciftler) = profil_paketleri(manifest, ad) {
            v.extend(ciftler);
        }
    }
    v
}

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
    // FAZ 4.5: profil = ana zip + opsiyonel parçalar (etiketli) — hepsi birlikte doğrulanır.
    let model_pkgs: Vec<(&String, Vec<(&crate::Package, String)>)> = profiles
        .iter()
        .map(|p| profil_paketleri(&manifest, p).map(|ciftler| (p, ciftler)))
        .collect::<Result<_, _>>()?;

    // Yükseltme: eski boşluksuz "PEMFVetClient" kurulumu varsa yeni isme taşı (2 GB yeniden inmesin).
    install::migrate_legacy_install_root(install_root);

    let cache = install::cache_dir(install_root);

    // DISK ALANI ON KONTROLU (2026-08-09 denetimi, Tier 1)
    // Mantik `disk_kapisi`ya CIKARILDI (denetim 2026-08-16, Bulgu 2): ayni koruma gozetimsiz
    // kosan `update_installed` ve `prefetch_updates` yollarinda da gerekliydi ve orada YOKTU.
    // Olculmus gerekce icin `disk_kapisi` basligina bak. Tek kaynak -> biri duzeltilip
    // digeri unutulamaz.
    {
        let mut gerekli: Vec<(&crate::Package, String)> = Vec::new();
        if let Some(l) = manifest.layers_for_current_platform() {
            gerekli.push((&l.deps, "deps".to_string()));
            gerekli.push((&l.app, "app".to_string()));
        }
        if let Some(pp) = runtime_pkg {
            gerekli.push((pp, "base".to_string()));
        }
        for (_ad, ciftler) in &model_pkgs {
            for (pkg, etiket) in ciftler {
                gerekli.push((pkg, etiket.clone()));
            }
        }
        let koru = cihazin_guncel_paket_adlari(&manifest, install_root, &cache);
        disk_kapisi(&gerekli, install_root, &cache, on, true, &koru)?;
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
        // İlk kurulumda yedek YOKTUR (disk boş) — dönüş bilinçli olarak yok sayılır.
        let _ = app_katmanini_degistir(&app_zip, install_root, &mut extract_budget, on, control)?;
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
        on(Progress::Extracting { what: crate::dil::t("rust.kurulum.eskiSurumTemizleniyor") });
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
    for (name, ciftler) in &model_pkgs {
        // FAZ 4.5: yarım-ağaç penceresi küçük kalsın diye TÜM parçalar önce İNER,
        // açılım sonra parça sırasıyla yapılır (ana zip önce — bugünkü davranış).
        let mut zipler: Vec<std::path::PathBuf> = Vec::with_capacity(ciftler.len());
        for (pkg, etiket) in ciftler {
            zipler.push(ensure_package(pkg, &cache, etiket, on, control)?);
        }
        on(Progress::Extracting { what: (*name).clone() });
        let pkgs: Vec<&crate::Package> = ciftler.iter().map(|(p, _)| *p).collect();
        // SHA kaydı açılımdan ÖNCE geçersiz kılınır, gerçek sha YALNIZ tüm açılım başarılıysa yazılır (bkz. profil_modelini_ac).
        // `is_profile = true`: profil paketi doğrulanmış `runtime/` ağacını ve launcher durum dosyalarını EZEMEZ
        // (bkz. extract::PROFILE_FORBIDDEN_TOP, #104).
        // Bu profil TAM indi + açıldı → HEMEN "kurulu" işaretle (mevcutlarla birleşir). ÖNEMLİ: işaretlemeyi döngü SONUNA
        // bırakma. Çoklu-profil kurulumunda kullanıcı sonraki profili İPTAL ederse (ör. Ev Sahibi bitti, Veteriner yarıda
        // iptal), erken-return burayı atlar → tamamlanan profil KAYBOLURDU.
        profil_modelini_ac(
            install_root,
            name.as_str(),
            &zipler,
            &birlesik_model_sha(&pkgs),
            &mut |model_zip| {
                extract::extract_zip_cancellable(model_zip, install_root, &mut extract_budget, true, &|| {
                    control() == net::Control::Cancel
                })?;
                Ok(())
            },
            &mut || install::add_installed_profiles(install_root, std::slice::from_ref(*name)),
        )?;
    }
    // Denetim Masası boyutunu GERÇEK kullanımla güncelle: NSIS onu kurulum anında hesaplar ve
    // o an dizinde yalnız launcher vardır (~11 MB); runtime + profil modelleri SONRA iner.
    // (bkz. install::boyut_kaydini_guncelle)
    install::boyut_kaydini_guncelle(install_root);
    Ok(())
}

// ─────────────────────────── PROFIL KALDIRMA (denetim 2026-09-06) ──────────────────────────────
//
// "Profilleri degistir" ekraninda kullanici kurulu bir profili (or. Veteriner) birakabilir.
// Kaldirma, KURULUM sirasinda ne acildiysa ONU siler — kaynak, onbellekteki profil zip'lerinin
// merkezi dizinidir (ai_models/ altina acilan dosyalarin tam listesi). Iki profil ayni dosyayi
// tasiyabilir (ortak ONNX/PT); kalan profillerin dosyalari KORUNUR. Bu yuzden kalan profillerin
// zip'leri de okunabilir olmali; degilse ortak kume hesaplanamaz ve islem REDDEDILIR (yanlis
// silme, yeniden indirmeden daha pahali: kullanici sebebini goremez, AI analizi anlasilmaz bir
// hatayla duser).
//
// GUVENLIK: zip'ten okunan yol yalniz `ai_models/` altinda, `..`/mutlak/ters-egik-cizgi/surucu
// icermeyen bir yol olabilir. Tek bir kotu girdi TUM islemi durdurur — hicbir dosya silinmez.
// Hasta verisi (%APPDATA%\PEMF_GUI, ProgramData\PEMF_System) bu fonksiyonun ERISIM ALANININ
// DISINDADIR: yalniz `install_root/ai_models/**` ve `install_root/cache/<profil zip'leri>`.

/// `remove_profiles` sonucu — Tauri komutu bunu JSON'a cevirir.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct RemoveReport {
    /// Kaldirilan profiller (istek sirasi).
    pub removed: Vec<String>,
    /// Islem SONRASI kurulu kalan profiller (`installed_profiles.json`'dan yeniden okunur).
    pub installed: Vec<String>,
    /// Diskten bosaltilan bayt (model dosyalari + onbellek zip'leri).
    pub freed_bytes: u64,
    /// Kaldirilan profil(ler)in dosyalarindan, kalan profil(ler) de kullandigi icin KORUNAN sayi.
    pub kept_shared: usize,
}

/// Zip girdi adini `ai_models/...` altinda GUVENLI bir goreli yola normalize et.
///
/// `Ok(None)` → dizin girdisi (sonu `/`), atlanir. `Err(sebep)` → guvensiz; cagiran TUM islemi
/// reddeder. Kurallar: ters-egik-cizgi, surucu (`:`), NUL, bos parca (mutlak yol / `//`), `..`,
/// sonu nokta/bosluk ile biten parca yasak; `.` parcalari atilir; ilk parca TAM OLARAK `ai_models` olmali (buyuk/kucuk harf
/// varyanti dahil baska hicbir kok kabul edilmez — `runtime/x` gibi girdiler zaten kurulumda
/// acilmaz, bkz. extract::PROFILE_FORBIDDEN_TOP).
fn model_yolunu_normalize_et(ad: &str) -> Result<Option<String>, String> {
    if ad.contains('\\') || ad.contains(':') || ad.contains('\0') {
        return Err(crate::dil::t_ile("rust.kurulum.yolGuvensizKarakter", &[("ad", &format!("{:?}", ad))]));
    }
    let dizin_girdisi = ad.ends_with('/');
    let mut parcalar: Vec<&str> = Vec::new();
    for (i, seg) in ad.split('/').enumerate() {
        if seg.is_empty() {
            // Sondaki bos parca dizin girdisidir; bastaki bos parca MUTLAK yoldur.
            if i == 0 || !dizin_girdisi || parcalar.is_empty() {
                return Err(crate::dil::t_ile("rust.kurulum.yolMutlak", &[("ad", &format!("{:?}", ad))]));
            }
            continue;
        }
        if seg == "." {
            continue;
        }
        if seg == ".." {
            return Err(crate::dil::t_ile("rust.kurulum.yolUstDizin", &[("ad", &format!("{:?}", ad))]));
        }
        // Sondaki nokta/bosluk (sahip incelemesi 2026-09-06): Windows yol normalizasyonu bunlari
        // DUSURUR ("em_kedi." → "em_kedi"), KEEP kiyasi ise dusurmez → kalan profilin dosyasi
        // "ortak degil" sanilip silinebilirdi. Muhafazakar: boyle parca tasiyan paket kaldirilamaz.
        let kirp = seg.trim_end_matches(['.', ' ']);
        if kirp.len() != seg.len() {
            return Err(crate::dil::t_ile("rust.kurulum.yolSonuNokta", &[("ad", &format!("{:?}", ad))]));
        }
        parcalar.push(seg);
    }
    if parcalar.first().copied() != Some("ai_models") {
        return Err(crate::dil::t_ile("rust.kurulum.yolAiModelsDisi", &[("ad", &format!("{:?}", ad))]));
    }
    if dizin_girdisi || parcalar.len() == 1 {
        return Ok(None);
    }
    Ok(Some(parcalar.join("/")))
}

/// KEEP/DELETE kiyasi icin anahtar — buyuk/kucuk harf duyarsiz. Windows/macOS dosya sistemleri
/// harf duyarsizdir; farkli yazimla ayni dosyayi "ortak degil" sayip silmek yerine MUHAFAZAKAR
/// davranilir (Linux'ta fazladan koruma zararsizdir).
fn yol_anahtari(yol: &str) -> String {
    yol.to_ascii_lowercase()
}

/// Bir profilin onbellekteki zip'lerini (ana + parcalar) listele: `(etiket, yol)`.
fn profil_onbellek_zipleri(
    manifest: &Manifest,
    cache: &Path,
    ad: &str,
) -> Result<Vec<(String, PathBuf)>, FlowError> {
    let ciftler = profil_paketleri(manifest, ad).map_err(|_| {
        FlowError::ProfilKaldirma(crate::dil::t_ile("rust.kurulum.profilManifestteYok", &[("ad", &(ad).to_string())]))
    })?;
    Ok(ciftler
        .into_iter()
        .map(|(pkg, etiket)| {
            let yol = cache_path_for(pkg, cache, &etiket);
            (etiket, yol)
        })
        .collect())
}

/// Zip merkezi dizininden `ai_models/...` dosya yollarini oku (normalize edilmis). Icerik
/// ACILMAZ — yalniz girdi adlari (1 GB'lik zip'te bile milisaniyeler).
fn zip_dosya_listesi(zip_yolu: &Path, profil: &str) -> Result<Vec<String>, FlowError> {
    let f = fs::File::open(zip_yolu).map_err(|e| {
        FlowError::ProfilKaldirma(crate::dil::t_ile("rust.kurulum.onbellekOkunamadi", &[("profil", &(profil).to_string()), ("dosya", &(zip_yolu.file_name().and_then(|s| s.to_str()).unwrap_or("paket")).to_string()), ("hata", &(e).to_string())]))
    })?;
    let bozuk = |e: zip::result::ZipError| {
        FlowError::ProfilKaldirma(crate::dil::t_ile("rust.kurulum.onbellekBozuk", &[("profil", &(profil).to_string()), ("dosya", &(zip_yolu.file_name().and_then(|s| s.to_str()).unwrap_or("paket")).to_string()), ("hata", &(e).to_string())]))
    };
    let arsiv = zip::ZipArchive::new(f).map_err(bozuk)?;
    // YS3 (zip 9): girdi adları tembel çözülür (`ZipResult<Cow<str>>`) — çözülemeyen ad da "önbellek bozuk" (2.x açılışta çözerdi).
    let adlar: Vec<_> = arsiv.file_names().collect::<Result<_, _>>().map_err(bozuk)?;
    let mut v = Vec::with_capacity(adlar.len());
    for ad in &adlar {
        match model_yolunu_normalize_et(ad) {
            Ok(Some(yol)) => v.push(yol),
            Ok(None) => {}
            // NOT (inceleme 2026-09-06): kurulum (extract) ters-egik-cizgili adlari ve ai_models
            // disindaki yasak-listede olmayan kok girdilerini (or. README.txt) ACABILIR; kaldirma
            // ise MUHAFAZAKAR olarak TUMUNU reddeder (yanlis silme > yeniden kurulum maliyeti).
            // Boyle bir profil kurulabilir ama buradan kaldirilamaz → kullaniciya acik yol: paket
            // bozuksa Onar, degilse uygulamayi kaldirip yalniz istenen profillerle yeniden kur.
            Err(sebep) => {
                return Err(FlowError::ProfilKaldirma(crate::dil::t_ile("rust.kurulum.paketGuvensiz", &[("profil", &(profil).to_string()), ("sebep", &(sebep).to_string())])))
            }
        }
    }
    Ok(v)
}

/// Silme asamasindaki dosya sistemi hatasini EYLEME DONUK metne cevir (inceleme 2026-09-06).
///
/// Ham `Io` ("Access is denied (os error 5)") ne yapilacagini soylemiyordu. Kayit (adim 4)
/// henuz degismedigi icin profil "kurulu" gorunur ve 'Kurulumu onar' eksigi onbellekten
/// tamamlar; kullanici bunu bilmeli. Tipik sebep: antivirus taramasi ya da acik kalan bir
/// uygulama dosyayi kilitlemistir (os error 5/32).
fn silme_hatasi(yol: &str, e: &std::io::Error) -> FlowError {
    FlowError::ProfilKaldirma(crate::dil::t_ile("rust.kurulum.silinemedi", &[("yol", &(yol).to_string()), ("hata", &(e).to_string())]))
}

/// Kurulu profil(ler)i KALDIR: model dosyalari (ortaklar haric) + onbellek zip'leri + kayitlar.
///
/// Sira (yarim kalma guvenligi): 1) TUM listeler okunur ve dogrulanir — burada hata = hicbir
/// sey silinmedi. 2) Dosyalar silinir, bos dizinler budanir. 3) Onbellek zip'leri silinir.
/// 4) Kayitlar guncellenir. 2-3 yarida kalirsa kayit DEGISMEZ → profil hala "kurulu" gorunur ve
/// "Kurulumu onar" eksik dosyalari onbellekten/agdan tamamlar (sessiz yarim-profil YOK).
///
/// Cagiran backend'i ONCE durdurmus olmali (bobinler E-stop'lu; model dosyalari kilitli degil).
///
/// `_on` (inceleme 2026-09-06): HICBIR `Progress` olayi URETILMEZ. `Progress` varyantlarinin hepsi
/// KURULUM adimidir (UI "extracting"i "Kuruluyor…/Installing…" basligiyla gosterir); kaldirma
/// sirasinda o basligi ve `<profil> kaldırılıyor installing` gibi karisik metni gostermek yaniltici
/// olurdu. Baslatici arayuzu "Kaldırılıyor…" ekranini kendisi yonetir. Parametre, `install_profiles`
/// ile ayni cagri sekli korunsun diye duruyor.
pub fn remove_profiles(
    install_root: &Path,
    manifest: &Manifest,
    profiles: &[String],
    _on: &mut dyn FnMut(Progress),
) -> Result<RemoveReport, FlowError> {
    if profiles.is_empty() {
        return Err(FlowError::ProfilKaldirma(
            crate::dil::t("rust.kurulum.profilSecilmedi"),
        ));
    }
    let kurulu = install::read_installed_profiles(install_root);
    for p in profiles {
        if !kurulu.iter().any(|k| k == p) {
            return Err(FlowError::ProfilKaldirma(crate::dil::t_ile("rust.kurulum.profilKurulDegil", &[("profil", &(p).to_string())])));
        }
    }
    let kalan: Vec<String> = kurulu
        .iter()
        .filter(|k| !profiles.iter().any(|p| p == *k))
        .cloned()
        .collect();
    if kalan.is_empty() {
        return Err(FlowError::ProfilKaldirma(
            crate::dil::t("rust.kurulum.enAzBirProfil"),
        ));
    }

    let cache = install::cache_dir(install_root);
    let models = install::models_dir(install_root);

    // 1a) KALAN profillerin dosya kumesi (KEEP). Zip eksikse REDDET: ortak dosya bilinemez.
    let mut keep: std::collections::HashSet<String> = std::collections::HashSet::new();
    for q in &kalan {
        for (_etiket, zip_yolu) in profil_onbellek_zipleri(manifest, &cache, q)? {
            if !zip_yolu.is_file() {
                return Err(FlowError::ProfilKaldirma(crate::dil::t_ile("rust.kurulum.kalanOnbellekYok", &[("profil", &(q).to_string()), ("dosya", &(zip_yolu.file_name().and_then(|s| s.to_str()).unwrap_or("paket")).to_string())])));
            }
            for yol in zip_dosya_listesi(&zip_yolu, q)? {
                keep.insert(yol_anahtari(&yol));
            }
        }
    }

    // 1b) Kaldirilacak profillerin dosya + zip listeleri.
    let mut silinecek: Vec<String> = Vec::new();
    let mut zipler: Vec<PathBuf> = Vec::new();
    let mut kept_shared = 0usize;
    let mut gorulen: std::collections::HashSet<String> = std::collections::HashSet::new();
    for p in profiles {
        for (_etiket, zip_yolu) in profil_onbellek_zipleri(manifest, &cache, p)? {
            if !zip_yolu.is_file() {
                return Err(FlowError::ProfilKaldirma(crate::dil::t_ile("rust.kurulum.onbellekYok", &[("profil", &(p).to_string()), ("dosya", &(zip_yolu.file_name().and_then(|s| s.to_str()).unwrap_or("paket")).to_string())])));
            }
            for yol in zip_dosya_listesi(&zip_yolu, p)? {
                let anahtar = yol_anahtari(&yol);
                if !gorulen.insert(anahtar.clone()) {
                    continue; // ayni profil icinde tekrar (parca ustune yazma)
                }
                // KEEP CIKARMA: kalan bir profil de tasiyorsa DOKUNMA (ortak model).
                if keep.contains(&anahtar) {
                    kept_shared += 1;
                } else {
                    silinecek.push(yol);
                }
            }
            zipler.push(zip_yolu);
        }
    }

    // 2) Dosyalari sil. Her hedef kurulum kokunun `ai_models/` altinda gercekten cozumlenmeli
    //    (junction/symlink ile disari cikan yol → REDDET; extract ile ayni kapi).
    let mut freed: u64 = 0;
    let mut ebeveynler: std::collections::BTreeSet<PathBuf> = std::collections::BTreeSet::new();
    for yol in &silinecek {
        let hedef = install_root.join(yol);
        let meta = match fs::symlink_metadata(&hedef) {
            Ok(m) => m,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue, // zaten yok
            Err(e) => return Err(silme_hatasi(yol, &e)),
        };
        if !extract::is_within(&models, hedef.parent().unwrap_or(&models)) {
            return Err(FlowError::ProfilKaldirma(crate::dil::t_ile("rust.kurulum.silmeKokDisi", &[("yol", &(yol).to_string())])));
        }
        if meta.is_dir() {
            continue; // zip'te dosya, diskte dizin: dokunma (budama asamasi bossa alir)
        }
        fs::remove_file(&hedef).map_err(|e| silme_hatasi(yol, &e))?;
        freed = freed.saturating_add(meta.len());
        if let Some(e) = hedef.parent() {
            ebeveynler.insert(e.to_path_buf());
        }
    }
    // Bos kalan dizinleri buda: derinden yukari, `ai_models/`in KENDISI haric.
    let mut adaylar: Vec<PathBuf> = ebeveynler.into_iter().collect();
    adaylar.sort_by_key(|p| std::cmp::Reverse(p.components().count()));
    for mut d in adaylar {
        while d.starts_with(&models) && d != models {
            let bos = fs::read_dir(&d).map(|mut it| it.next().is_none()).unwrap_or(false);
            if !bos || fs::remove_dir(&d).is_err() {
                break;
            }
            match d.parent() {
                Some(e) => d = e.to_path_buf(),
                None => break,
            }
        }
    }

    // 3) Onbellek zip'leri (+ varsa yarim `.part` kalintisi degil — o kurulum alanidir).
    for z in &zipler {
        let etiket = z.file_name().and_then(|s| s.to_str()).unwrap_or("paket");
        match fs::metadata(z) {
            Ok(m) => {
                fs::remove_file(z).map_err(|e| silme_hatasi(etiket, &e))?;
                freed = freed.saturating_add(m.len());
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(e) => return Err(silme_hatasi(etiket, &e)),
        }
    }

    // 4) Kayitlar — en son (yukaridaki adimlar yarim kalirsa profil "kurulu" kalir → Onar toparlar).
    for p in profiles {
        install::remove_installed_profile(install_root, p);
        install::remove_model_record(install_root, p);
    }
    install::boyut_kaydini_guncelle(install_root);

    Ok(RemoveReport {
        removed: profiles.to_vec(),
        installed: install::read_installed_profiles(install_root),
        freed_bytes: freed,
        kept_shared,
    })
}

/// Uygulama penceresinin URL'si: backend adresi + kurulu profiller (`?profiles=home,vet`).
///
/// Uygulama (pf) `?profiles=` parametresini okuyup kalici olarak saklar (`installedModes()`);
/// boylece profil kaldirildiginda arayuz o profili artik sunmaz. Bos listede parametre YOK
/// (eski davranis). Adlar yalniz `[A-Za-z0-9_-]` olabilir — kayit dosyasindan gelen bozuk bir
/// ad URL'yi kirmasin diye elenir (kodlama yerine eleme: profil adlari bizim manifestimizden).
pub fn uygulama_url(port: u16, installed: &[String]) -> String {
    let taban = crate::backend::app_url(port);
    let adlar: Vec<&str> = installed
        .iter()
        .map(|s| s.as_str())
        .filter(|s| {
            !s.is_empty() && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
        })
        .collect();
    if adlar.is_empty() {
        taban
    } else {
        let sep = if taban.contains('?') { '&' } else { '?' };
        format!("{taban}{sep}profiles={}", adlar.join(","))
    }
}

/// WebView2 onbellek-kirici parametresi (`_=<ms>`) — mevcut sorgu parametreleri KORUNUR.
pub fn onbellek_kirici(url: &str, ts_ms: u128) -> String {
    let sep = if url.contains('?') { '&' } else { '?' };
    format!("{url}{sep}_={ts_ms}")
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
        on(Progress::Extracting { what: crate::dil::t("rust.kurulum.eskiSurumTemizleniyor") });
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
/// Döner: **yedek GERÇEKTEN alındı mı**.
///
/// ⚠️ DENETİM 2026-08-23 (C10): eskiden `Result<(), _>` dönüyordu ve çağıran `app_yedegi`yi
/// KOŞULSUZ `true` yapıyordu. Oysa yedek yalnız kök listesi doluyken alınır; `read_app_roots`
/// dosya yok/bozuksa BOŞ döner (kasıtlı — bilinmeyen sınırla silmek tehlikelidir) ve fonksiyon
/// yine `Ok` dönerdi. Kayıt gerçeği yansıtmayınca geri alma "başarılı" diyerek hiçbir şey
/// yapmıyordu. Artık gerçek dönülür; çağıran yalan bir söz veremez.
fn app_katmanini_degistir(
    zip: &Path,
    install_root: &Path,
    butce: &mut u64,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<bool, FlowError> {
    let rt = install::runtime_dir(install_root);
    let yedek = install::app_backup_dir(install_root);
    let roots = install::read_app_roots(install_root);
    let _ = fs::remove_dir_all(&yedek);
    if !roots.is_empty() {
        // ⚠️ SİLMEK DEĞİL TAŞIMAK: geri alma buna dayanır. Silseydik, yeni app açılımı yarıda
        // kalınca (iptal/disk/G-Ç) ne eski ne yeni app kalırdı → kurulum ölür ve 1,2 GB'lık deps
        // sağlam olduğu hâlde her şey baştan inmek zorunda kalırdı. Taşıma aynı birimde metadata
        // işlemidir (~anlık), 1,2 GB kopyalamaya gerek yok.
        on(Progress::Extracting { what: crate::dil::t("rust.kurulum.eskiAppYedekleniyor") });
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
    let yedek_alindi = !roots.is_empty() && yedek.is_dir();
    on(Progress::Extracting { what: "app".into() });
    if let Err(e) = extract::extract_zip_cancellable(zip, &rt, butce, false, &|| {
        control() == net::Control::Cancel
    }) {
        // Açılım başarısız → eski app'i HEMEN geri koy (kurulum çalışır kalsın).
        // Yedek alınamadıysa geri konacak bir şey de yok; hata zaten yukarı taşınıyor.
        if yedek_alindi {
            let b = GeriAlmaBilgisi { app_yedegi: true, ..Default::default() };
            // 2. tur [3.1] deseni (denetim 2026-08-24, C4): geri almanın SONUCU YUTULMAZ. Eski hâli
            // `let _ =` idi — geri koyma düşerse (kilitli dosya / AV / zehirli artık) çağırana YALNIZ
            // açılım hatası/iptal gidiyordu: UI "iptal edildi" derken cihaz DOĞRULANMAMIŞ/yarım app
            // ağacıyla kalıyordu. İptal bile olsa geri alma düştüyse sonuç NÖTR DEĞİLDİR → açık,
            // yükseltilmiş hata dön (dış yol `profilleri_yenile` ile SİMETRİK; main.rs bunu kırmızı
            // hata gösterir, "cancelled" maskesi takılmaz). Kilit: C4_app_ic_yol_geri_alma_DUSERSE...
            if let Err(g) = guncellemeyi_geri_al(install_root, &b) {
                return Err(FlowError::Io(std::io::Error::new(
                    std::io::ErrorKind::Other,
                    crate::dil::t_ile("rust.kurulum.appGeriAlinamadi", &[("geri", &(g).to_string()), ("adim", &(e).to_string())]),
                )));
            }
        }
        return Err(e.into());
    }
    Ok(yedek_alindi)
}

/// Bir güncellemenin GERİ ALINABİLİR durumu. `update_installed` döner; çağıran sağlık kapısından
/// sonra ya `guncellemeyi_onayla` ya da `guncellemeyi_geri_al` çağırmak ZORUNDADIR.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct GeriAlmaBilgisi {
    /// deps yenilendi → tam ağaç takası yapıldı (`runtime.old` bekliyor).
    pub tam_takas: bool,
    /// yalnız app yenilendi → eski app dosyaları `_app_yedek`te bekliyor **ve geri konabilir**.
    ///
    /// ⚠️ C10: bu alan "app değişti" DEĞİL "geri alınabilir bir yedek VAR" demektir. İkisi eskiden
    /// karıştırılıyordu: yedek alınamasa bile `true` yazılıyor ve geri alma hiçbir şey yapmadan
    /// "başarılı" dönüyordu. "App değişti mi" sorusu `app_degisti` alanındadır.
    pub app_yedegi: bool,
    /// App katmanı GERÇEKTEN değiştirildi mi (yedek alınabilmiş olsun ya da olmasın).
    ///
    /// `bir_sey_yapildi()` bunu kullanır: yedeksiz de olsa disk DEĞİŞMİŞTİR ve sağlık kapısı
    /// koşmalıdır. Yalnız `app_yedegi`ye bakmak, yedeksiz güncellemeyi "hiçbir şey yapılmadı"
    /// sayıp doğrulanmamış sürümü sessizce onaylardı.
    pub app_degisti: bool,
    /// Onaylanınca kaydedilecek sha'lar (sağlık kapısı geçmeden kayıt yazılmaz).
    pub deps_sha: String,
    pub app_sha: String,
    pub base_sha: String,
}

impl GeriAlmaBilgisi {
    pub fn bir_sey_yapildi(&self) -> bool {
        // ⚠️ C10: `app_degisti` de sayılır. Yalnız `app_yedegi`ye bakmak, yedek alınamayan bir
        // app güncellemesini "hiçbir şey yapılmadı" sayardı → sağlık kapısı hiç koşmaz ve
        // doğrulanmamış sürüm sessizce onaylanırdı.
        self.tam_takas || self.app_yedegi || self.app_degisti
    }

    /// Onaylanınca kurulu sayılacak paket kimliği — `install::backend_env_with` ile AYNI kural: katmanlıda
    /// `app`, katmansızda `base`. Boşsa `None` (kimlik kayıttan okunur). Sağlık kapısındaki backend'e geçer
    /// (`start_backend_kimlikli`), yoksa güncellemeden sonraki ilk oturum eski `buildId`i raporlar.
    pub fn paket_kimligi(&self) -> Option<&str> {
        [self.app_sha.as_str(), self.base_sha.as_str()].into_iter().find(|s| !s.is_empty())
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
/// Kesinti/geri-almadan kalan SAHNELEME ağaçlarını sil (denetim 2026-08-23, C9).
///
/// ⚠️ `runtime.old`'a ASLA DOKUNMAZ: o, sağlık kapısını geçmiş, çalıştığı KANITLANMIŞ sürümdür —
/// yani geri dönüş yolunun kendisi. Burada silinenler yalnız doğrulanmamış sahne (`runtime.new`)
/// ve teşhis kopyasıdır (`runtime.bozuk`); ikisi de bir sonraki güncellemede zaten silinecekti,
/// sorun o silmenin disk kapısından SONRA gelmesiydi.
fn olu_sahne_agaclarini_temizle(install_root: &Path) {
    let _ = fs::remove_dir_all(install::runtime_new_dir(install_root));
    let _ = fs::remove_dir_all(install_root.join("runtime.bozuk"));
}

/// Döner: kurtarma yapıldıysa `true`.
pub fn yarim_takasi_kurtar(install_root: &Path) -> bool {
    let rt = install::runtime_dir(install_root);
    if rt.exists() {
        // ⚠️ `runtime` VAR — ama bu "her şey yolunda" demek DEĞİL (denetim 2026-08-23):
        //
        // (C11) APP KATMANI takası app köklerini canlı ağaçtan `_app_yedek`e TAŞIYIP yeni app'i
        // açıyor; arada kesinti olursa `runtime/` yerinde kalır ama İÇİ EKSİKTİR. Eski erken-dönüş
        // bu hâli hiç görmüyordu: cihaz "kurulu değil" görünüyor, sağlam yedek yetim kalıyor ve
        // kullanıcı ~1,46 GB deps'i yeniden indirmek zorunda kalıyordu — oysa çalışan sürüm
        // diskte, bir `rename` uzaklıkta duruyor.
        if !agac_yapisal_gecerli_mi(&rt) {
            let yedek = install::app_backup_dir(install_root);
            if yedek.is_dir() {
                let b = GeriAlmaBilgisi { app_yedegi: true, ..Default::default() };
                if guncellemeyi_geri_al(install_root, &b).is_ok() && agac_yapisal_gecerli_mi(&rt) {
                    olu_sahne_agaclarini_temizle(install_root);
                    return true;
                }
            }
        }
        // (C9) Sağlam kurulumda kurtarma YAPILMAZ (sözleşme korunur) — ama kesintiden kalan ölü
        // sahne ağaçları burada toplanır. Aksi hâlde `update_installed` sırası yüzünden
        // (önce `disk_kapisi`, sonra `temizle_ve_ac`) yetim `runtime.new` kapının istediği alanı
        // işgal eder ve güncelleme KALICI olarak "Yetersiz disk alanı" ile reddedilebilir:
        // artığı silecek olan şey güncellemenin kendisidir.
        olu_sahne_agaclarini_temizle(install_root);
        return false;
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
            if let Err(hata) = fs::rename(&eski, &rt) {
                // 2. tur denetimi [3.1] alt-durumu (2026-08-20): eski→rt DÜŞTÜ (kilitli dosya /
                // AV taraması runtime.old içinde tutamaç tutuyor) ve canlı ağaç az önce
                // runtime.bozuk'a alındı → kurulum o oturum boyunca HİÇ runtime dizinsiz kalırdı
                // (cihaz açılamaz; yarim_takasi_kurtar ancak SONRAKİ açılışta ve koşullu).
                // Doğrulanmamış-yeni'yi geri koy: çalışan-bilinmeyen > hiç yok. Hata çağırana
                // AYNEN çıkar; çağıran (aşağıdaki yükseltme) operatörü açıkça uyarır.
                if !rt.exists() && bozuk.is_dir() {
                    let _ = fs::rename(&bozuk, &rt);
                }
                return Err(hata.into());
            }
            let _ = fs::remove_dir_all(&bozuk);
        }
    } else if b.app_yedegi {
        let yedek = install::app_backup_dir(install_root);
        // ⚠️ DENETİM 2026-08-23 (C10): YEDEK YOKSA SESSİZCE BAŞARILI DÖNMEZ.
        // `app_yedegi: true` eskiden koşulsuz set ediliyordu; `app_katmanini_degistir` ise yedeği
        // yalnız kök listesi doluyken alır (`read_app_roots` dosya yok/bozuksa BOŞ döner — kasıtlı).
        // Bu ikisi ayrışınca geri alma hiçbir şey yapmadan `Ok(())` dönüyordu ve kullanıcıya
        // "eski sürüme dönüldü" deniyordu — oysa cihaz DOĞRULANMAMIŞ yeni sürümde kalıyordu.
        // Artık kayıt de düzeltildi (yedek gerçekten alındıysa `true`), ama bu kapı ikinci kemer:
        // yedek dizini yoksa çağıran GERÇEĞİ öğrenir ve operatöre söyleyebilir.
        if !yedek.is_dir() {
            return Err(FlowError::Io(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                crate::dil::t("rust.kurulum.appYedegiYok"),
            )));
        }
        {
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
    /// GERİ ÇAĞIRMA: kurulu sürüm `min_supported_version`'ın altında → güncelleme ZORUNLU.
    ///
    /// Bu bayrak `rollout`u ezer (bkz. `pending_updates`) ve UI'ya AYRICA bildirilir: geri
    /// çağırma bir bobin-güvenliği düzeltmesi taşıyabilir ve cihaz güncellenene kadar kullanıcı
    /// bunu BİLMELİ. Sessizce beklemek, geri çağırmanın amacını boşa çıkarır.
    pub zorunlu: bool,
    /// Gereken TÜM paketler zaten önbellekte mi?
    ///
    /// SAHİP KARARI 2026-08-08: güncelleme açılışta kimseyi bekletmemeli. `true` ise kurulum
    /// ANINDA yapılabilir (yalnız açma); `false` ise paketler ARKA PLANDA indirilir ve kurulum
    /// bir SONRAKİ açılışa bırakılır — hayvanı masada bekleyen veteriner 45 dk indirmeye takılmaz.
    pub cached: bool,
    /// Bu hedef daha önce kurulup SAĞLIK KAPISINDAN geçemedi ve deneme sınırı doldu (C2).
    ///
    /// `needed()` bundan ETKİLENMEZ: güncelleme hâlâ "gerekli"dir ve kullanıcıya bildirilir —
    /// yalnız SESSİZ/otomatik kurulum durur. Elle "Onar" yolu açık kalır. Yeni bir sürüm
    /// yayınlanınca (farklı sha → farklı hedef kimliği) sayaç sıfırlanır ve bayrak kendiliğinden
    /// düşer, yani düzeltme yayını hemen uygulanır.
    pub otomatik_durduruldu: bool,
    /// Bu güncellemenin HEDEF KİMLİĞİ — deneme sayacının anahtarı (C2).
    ///
    /// ⚠️ Sürüm NUMARASI değil paket SHA'ları: aynı sürüm numarası altında farklı ikili
    /// yayınlanabilir (`--clobber`) ve numaraya bağlanan bir sayaç düzeltme yayınını da bloklardı.
    /// Sha değişince kimlik değişir → sayaç kendiliğinden sıfırlanır.
    pub hedef: String,
    /// GÜNCELLEME ONAYI (Y253 / Y254, 2026-11-06): onay penceresinin "inecek toplam boyut"u — `bytes`ın önbellekte HENÜZ
    /// OLMAYAN paketlere düşen kısmı (yarım kalmış / önceden inmiş paket yeniden sayılmaz).
    pub indirilecek: u64,
}

impl UpdatePlan {
    pub fn needed(&self) -> bool {
        self.base || self.deps || self.app || !self.profiles.is_empty()
    }
}

/// Geri alma anında çağrılır: bu hedefin deneme sayacını artırır (C2).
///
/// Ayrı bir yardımcı olmasının sebebi, `install::record_runtime_attempt`ın hedef kimliğini
/// çağıranın hesaplamasını gerektirmesi — kimlik `pending_updates` ile AYNI kaynaktan gelmeli,
/// yoksa sayaç hiçbir zaman eşleşmez ve koruma sessizce ölür.
pub fn geri_almayi_kaydet(install_root: &Path, manifest_raw: &str) {
    if let Ok(plan) = pending_updates(manifest_raw, install_root) {
        if !plan.hedef.is_empty() {
            install::record_runtime_attempt(install_root, &plan.hedef);
        }
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
        plan.zorunlu = zorunlu;
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
        let Ok(pkgs) = manifest.model_packages(&name) else { continue };
        let hedef = birlesik_model_sha(&pkgs);
        // ⚠️ MODELLERDE KURAL BASE'DEN FARKLI: KAYIT YOKSA "bayat" DEMİYORUZ.
        // Base'de bilinmeyeni bayat saymak 1,3 GB'a mal olur ve backend gerçekten değişmiştir.
        // Modellerde aynı kuralı uygulamak, kaydı olmayan her eski kurulumda ÜÇ profili birden
        // (~2,2 GB) boşuna indirtirdi — oysa model paketleri base'den çok daha seyrek değişir ve
        // kullanıcı onları zaten AYNI manifestten kurmuştu. Bu yüzden kaydı olmayan profilin
        // sha'sı manifestten BENİMSENİR (`adopt_unknown_models`); benimsendikten SONRA yapılan
        // her model değişikliği normal biçimde yakalanır. Tam yeniden doğrulama isteyen
        // kullanıcının yolu hâlâ "Onar"dır.
        let Some(mevcut) = kurulu.models.get(&name) else { continue };
        if !mevcut.eq_ignore_ascii_case(&hedef) {
            plan.bytes += pkgs.iter().map(|p| p.size).sum::<u64>();
            plan.profiles.push(name);
        }
    }

    // Gereken paketler zaten indirilmiş mi? (arka plan indirmesi bir önceki açılışta bitmiş olabilir)
    let cache = install::cache_dir(install_root);
    let mut hepsi = true;
    if let Some(l) = manifest.layers_for_current_platform() {
        if plan.deps && !paket_onbellekte_hazir(&l.deps, &cache, "deps") { hepsi = false; plan.indirilecek += l.deps.size; }
        if plan.app && !paket_onbellekte_hazir(&l.app, &cache, "app") { hepsi = false; plan.indirilecek += l.app.size; }
    } else if plan.base {
        if let Ok(p) = manifest.runtime_for_current_platform() {
            if !paket_onbellekte_hazir(p, &cache, "base") { hepsi = false; plan.indirilecek += p.size; }
        }
    }
    for name in &plan.profiles {
        if let Ok(ciftler) = profil_paketleri(&manifest, name) {
            for (pkg, etiket) in ciftler {
                if !paket_onbellekte_hazir(pkg, &cache, &etiket) { hepsi = false; plan.indirilecek += pkg.size; }
            }
        }
    }
    plan.cached = hepsi;

    // ⚠️ DENETİM 2026-08-23 (C2): GERİ ALMA DÖNGÜSÜ KIRICI. Bu hedef daha önce kurulup sağlık
    // kapısından geçemediyse (ve sınır dolduysa) OTOMATİK kurulum durur. Aksi hâlde bozuk bir
    // yayın her açılışta backend'i öldürüp ~1,19 GB açıp 180 sn bekletip geri alınıyordu ve tek
    // çıkış yolu yayıncının `rollout: 0` yazmasıydı.
    //
    // ⚠️ NE DURMAZ: bildirim, geri çağırma uyarısı ve kullanıcının elle "Onar" demesi. Bayrak
    // yalnız `otomatik_durduruldu` olarak taşınır; `needed()` DEĞİŞMEZ — bunu `needed()`e
    // bağlamak arızayı görünmez kılardı, oysa kullanıcı cihazının eski sürümde takılı kaldığını
    // BİLMELİ (`selfupdate_auto_allowed` ile birebir aynı sözleşme).
    plan.hedef = if let Some(l) = manifest.layers_for_current_platform() {
        format!("app:{}|deps:{}", l.app.sha256, l.deps.sha256)
    } else if let Ok(p) = manifest.runtime_for_current_platform() {
        format!("base:{}", p.sha256)
    } else {
        String::new()
    };
    // Kimlik çıkarılamadıysa (bilinmeyen platform) kapı UYGULANMAZ — bilinmeyeni engellemek,
    // güncellemeyi hiç alamayan bir cihaz üretirdi.
    plan.otomatik_durduruldu =
        plan.needed() && !plan.hedef.is_empty() && !install::runtime_otomatik_izinli(install_root, &plan.hedef);

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
    // Bulgu 2 (denetim 2026-08-16): ARKA PLAN indirmesi korumasızdı — 1,5 GB'ı gözetimsiz
    // indirip diski doldurabiliyordu ve hata kullanıcıya HİÇ görünmüyordu. Yalnız indirme
    // yapıldığı için `kurulum_da_yapilacak = false` (zip kadar yer yeter, açma yok).
    let koru = cihazin_guncel_paket_adlari(&manifest, install_root, &cache);
    disk_kapisi(&plan_paketleri(&manifest, &plan), install_root, &cache, on, false, &koru)?;
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
        for (pkg, etiket) in profil_paketleri(&manifest, name)? {
            ensure_package(pkg, &cache, &etiket, on, control)?;
        }
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
        let Ok(pkgs) = manifest.model_packages(&name) else { continue };
        // FAZ 4.5 (dusman-dogrulama bulgusu): benimseme parcalarin DISKTE var olup
        // olmadigini dogrulayamaz. Parcali profilde BIRLESIK kimligi benimsemek,
        // kaydi kaybolmus ama parcalari HIC inmemis cihazi sonsuza dek "guncel"
        // sayardi (sessiz eksik-model — adopt'un onledigi sinifin parca surumu).
        // MUHAFAZAKAR benimseme: yalniz ANA sha yazilir; parcali manifestte hedef
        // (birlesik) != kayit (ana) oldugu icin profil plana girer ve parcalar
        // indirilir. Bedeli: kayit kaybi + parcalar aslinda kuruluysa ~1,8 GB
        // gereksiz yenileme — nadir ve guvenli yon (tam dogrulama yolu zaten Onar).
        install::record_model_sha(install_root, &name, &pkgs[0].sha256);
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
    // Bulgu 2 (denetim 2026-08-16): OTO-GÜNCELLEME yolunda disk kapısı YOKTU — kapı yalnız
    // kullanıcının izlediği ilk kuruluma konmuştu. Burası gözetimsiz koşar; alan yetmezse
    // güncelleme sessizce başarısız olur ve ölü önbellek hiç geri kazanılmaz.
    // Burada AÇMA da yapılacak → 2× yer + zaten önbellektekilerin açılımı hesaplanır.
    let koru = cihazin_guncel_paket_adlari(&manifest, install_root, &cache);
    disk_kapisi(&plan_paketleri(&manifest, &plan), install_root, &cache, on, true, &koru)?;
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
                    crate::dil::t("rust.kurulum.yeniKurulumEksik"),
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
            // ⚠️ C10: `app_yedegi` GERÇEĞİ yansıtır (koşulsuz `true` DEĞİL). `_app_roots.json`
            // kayıp/bozuksa yedek alınamaz; o durumda geri alma sözü VERİLMEZ.
            let yedek_alindi = app_katmanini_degistir(&az, install_root, &mut extract_budget, on, control)?;
            if !agac_yapisal_gecerli_mi(&install::runtime_dir(install_root)) {
                let b = GeriAlmaBilgisi { app_yedegi: yedek_alindi, ..Default::default() };
                let geri_hata = guncellemeyi_geri_al(install_root, &b).err();
                return Err(FlowError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    match geri_hata {
                        // Geri alma da yapılamadıysa operatöre BUNU söyle: cihaz doğrulanmamış
                        // sürümde kaldı ve "Onar" gerekiyor. Sessizce "dönüldü" demek yalandır.
                        Some(_) => crate::dil::t("rust.kurulum.katmanEksikGeriAlinamadi"),
                        None => crate::dil::t("rust.kurulum.katmanEksikDonuldu"),
                    },
                )));
            }
            geri = GeriAlmaBilgisi {
                app_yedegi: yedek_alindi,
                app_degisti: true,
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
                crate::dil::t("rust.kurulum.yeniKurulumEksik"),
            )));
        }
        atomik_takas(install_root)?;
        geri = GeriAlmaBilgisi {
            tam_takas: true,
            base_sha: runtime_pkg.sha256.clone(),
            ..Default::default()
        };
    }

    // ⚠️ TAKAS ZATEN YAPILDI (yukarıda). `GeriAlmaBilgisi` sözleşmesi uyarınca bu noktadan `?` ile
    // ÇIKMAK YASAK: çağıran (`launcher/app/src/main.rs`, İptal/Err kolları) `geri`yi HİÇ görmez →
    //   1. doğrulanmamış sürüm sağlık kapısı (`start_backend`) KOŞMADAN canlıda kalır; UI
    //      `s-ready` der, kullanıcı "Başlat"a basar,
    //   2. `runtime.old` bir SONRAKİ turda `atomik_takas` tarafından TÜKETİLİR (ilk iş olarak
    //      `remove_dir_all` ediyor) → son-bilinen-çalışan sürüm yok olur.
    // Tetikleyici: kurulu cihaz + `plan.cached` + planda HEM katman HEM en az bir profil + profil
    // adımında iptal/IO hatası (kilitli model dosyası, AV karantinası). Tasarım "indirmeler
    // takastan önce biter" varsayıyordu; aynı turda PROFİL paketi olabileceği hesaplanmamıştı.
    // ⚠️ KAYIT YAZILMAZ — `installed_packages.json`ın "bilinmiyor"da kalması KASITLI fail-safe
    // (bkz. BUILD.md ve `upgrade_drill.rs::geri_alinan_guncelleme_KAYIT_birakmaz`). Eksik olan
    // şey kayıt değil, `guncellemeyi_geri_al` ÇAĞRISIydı.
    if let Err(e) = profilleri_yenile(&manifest, &plan, install_root, &cache, &mut extract_budget, on, control) {
        if geri.bir_sey_yapildi() {
            // 2. tur denetimi [3.1] (2026-08-20): geri almanın SONUCU artık YUTULMAZ. Eski hâli
            // `let _ =` idi — geri alma düşerse (kilitli dosya/AV/zehirli artık) çağırana yalnız
            // profil hatası/iptal gidiyordu: UI "iptal edildi" derken cihaz DOĞRULANMAMIŞ yeni
            // sürümde kalıyor ve runtime.old bir SONRAKİ turda atomik_takas tarafından tüketilip
            // son-bilinen-çalışan yok oluyordu. İptal bile olsa geri alma düştüyse sonuç nötr
            // DEĞİLDİR → açık, yükseltilmiş hata dön (main.rs bunu kırmızı hata olarak gösterir;
            // "cancelled" maskesi takılmaz). Kilit: upgrade_drill.rs TATBİKAT 5.
            if let Err(g) = guncellemeyi_geri_al(install_root, &geri) {
                return Err(FlowError::Io(std::io::Error::new(
                    std::io::ErrorKind::Other,
                    crate::dil::t_ile("rust.kurulum.guncellemeGeriAlinamadi", &[("geri", &(g).to_string()), ("adim", &(e).to_string())]),
                )));
            }
        }
        return Err(e);
    }
    Ok(geri)
}

/// Bir profilin model zip'lerini AÇ — iki model döngüsünün (`install_profiles`, `profilleri_yenile`) TEK sıra kuralı.
///
/// ⚠️ DENETİM 2026-08-23 (C12): SHA KAYDI AÇILIMDAN ÖNCE GEÇERSİZ KILINIR. `repair()` doğrudan `install_profiles`e düşer ve
/// onarım senaryosunda kayıt ZATEN doğru sha'yı taşır. Açılım yarıda kesilirse (elektrik / iptal / bozuk zip) diskte YARIM bir
/// model ağacı kalır ama kayıt manifest sha'sıyla EŞLEŞMEYE devam eder → `pending_updates` o profili "güncel" sayar ve bir daha
/// ASLA yenilemez; AI analizi anlaşılmaz bir hatayla düşer. Gerçek sha YALNIZ tüm parçalar açıldıktan sonra yazılır.
/// D5.52 (B-10.144): kural eskiden iki döngüde kopya duruyor ve yalnız METİNLE kapılıydı (`if false { … }` mutantı YEŞİL); artık
/// tek yerde ve açılım ENJEKTE edildiği için birim testleri gerçek `installed_packages.json` ile davranışı ölçer.
fn profil_modelini_ac(
    install_root: &Path,
    name: &str,
    zipler: &[PathBuf],
    gercek_sha: &str,
    ac: &mut dyn FnMut(&Path) -> Result<(), FlowError>,
    acildi: &mut dyn FnMut(),
) -> Result<(), FlowError> {
    install::record_model_sha(install_root, name, "");
    for model_zip in zipler {
        ac(model_zip)?;
    }
    acildi();
    install::record_model_sha(install_root, name, gercek_sha);
    Ok(())
}

/// Profil (model) paketlerini yenile.
///
/// ⚠️ AYRI FONKSİYON OLMASI KASITLI: `?` ile erken çıkışın çağıran taraftaki GERİ ALMA'yı
/// atlamasını yapısal olarak engeller (çağırana `Result` döner, o da geri alır).
#[allow(clippy::too_many_arguments)]
fn profilleri_yenile(
    manifest: &Manifest,
    plan: &UpdatePlan,
    install_root: &Path,
    cache: &Path,
    butce: &mut u64,
    on: &mut dyn FnMut(Progress),
    control: &dyn Fn() -> net::Control,
) -> Result<(), FlowError> {
    for name in &plan.profiles {
        let ciftler = profil_paketleri(manifest, name)?;
        // FAZ 4.5: tum parcalar ONCE iner, acilim sonra sirayla (install_profiles ile ayni).
        let mut zipler: Vec<std::path::PathBuf> = Vec::with_capacity(ciftler.len());
        for (pkg, etiket) in &ciftler {
            zipler.push(ensure_package(pkg, cache, etiket, on, control)?);
        }
        on(Progress::Extracting { what: name.clone() });
        let pkgs: Vec<&crate::Package> = ciftler.iter().map(|(p, _)| *p).collect();
        profil_modelini_ac(
            install_root,
            name,
            &zipler,
            &birlesik_model_sha(&pkgs),
            &mut |model_zip| {
                extract::extract_zip_cancellable(model_zip, install_root, butce, true, &|| {
                    control() == net::Control::Cancel
                })?;
                Ok(())
            },
            &mut || {},
        )?;
    }
    Ok(())
}

/// HOTSPOT KEEP-ALIVE GÖREVİ GEREKLİ Mİ? — kurulu profillerden karar.
///
/// ⚠️ SAHADA ÖLÇÜLDÜ (2026-09-10): `PEMF-Hotspot` görevini YALNIZ Inno/servis kurulumu
/// (`setup_services.ps1 -Mode device`) kuruyordu; launcher ile kurulan makineler HİÇ almıyordu.
/// Sonuç: hotspot bir kez elle açılsa bile ağ değişiminde ya da yeniden başlatmada düşüyor ve
/// onu geri getirecek kimse olmuyor → ESP bobinleri (6-8) broker'a bağlanamıyor.
///
/// ⚠️ NEDEN PROFİL KAPISI, "her makinede" DEĞİL: AP'yi koşulsuz açmak sahada iki kez arıza
/// üretti (kendi hotspot'umuz aynı-WiFi keşfini bozuyordu — bkz. mDNS kesintisi bulgusu).
/// Terapi `vet`/`research` profillerinde yapılır; `home` (ev sahibi) analiz-only olduğu için
/// bobin sürmez → o makinede AP'ye gerek YOK.
///
/// ⚠️ NEDEN STM ALGISI DEĞİL: "STM bağlanınca aç" önerisi ELENDİ — yalnız ESP kullanan
/// (STM'siz) kurulumlarda hiç tetiklenmez ve tavuk-yumurta olur: ESP bağlanmak için hotspot
/// ister, hotspot ise donanım görülmesini beklerdi. Profil sinyali ağdan bağımsızdır.
pub(crate) fn hotspot_gorevi_gerekli(profiller: &[String]) -> bool {
    profiller.iter().any(|p| p == "vet" || p == "research")
}

/// Görevi kurulu profillere göre eşitle (kur ya da kaldır). Sahiplenilmez: başarısız olsa bile
/// uygulama açılışını ENGELLEMEZ — eksik hotspot ESP'leri etkiler, uygulamanın kendisini değil.
#[cfg(windows)]
pub(crate) fn hotspot_gorevini_esitle(install_root: &Path) {
    let gunluk = std::env::var_os("LOCALAPPDATA")
        .filter(|v| !v.is_empty())
        .map(|d| PathBuf::from(d).join("PEMF_System").join("hotspot.log"));
    hotspot_gorevini_esitle_ile(install_root, gunluk.as_deref(), |c| c.spawn().map(|_| ()));
}

/// `hotspot_gorevini_esitle`in test edilebilir hâli — başlatıcı ve günlük yolu ENJEKTE (D5.16 · B-10.75).
///
/// ⚠️ D5.16: başlatma sonucu eskiden `let _ = c.spawn();` ile ATILIYORDU — `powershell` başlatılamazsa (ilke, AppLocker,
/// bozuk System32) görev hiç kurulmuyor, ESP bobinleri (6-8) hotspot'a bağlanamıyor ve hiçbir yerde iz kalmıyordu. Artık
/// başlatma hatası betiğin KENDİ günlüğüne (`%LOCALAPPDATA%\PEMF_System\hotspot.log`) yazılır; açılışı yine ENGELLEMEZ.
#[cfg(windows)]
pub(crate) fn hotspot_gorevini_esitle_ile(
    install_root: &Path,
    gunluk: Option<&Path>,
    baslat: impl FnOnce(&mut std::process::Command) -> std::io::Result<()>,
) {
    let betik = install::runtime_dir(install_root)
        .join("PEMF_Backend")
        .join("install_hotspot_task.ps1");
    if !betik.exists() {
        return; // eski paket (betik henüz yayınlanmamış) → sessizce geç
    }
    let gerekli = hotspot_gorevi_gerekli(&install::read_installed_profiles(install_root));
    // ⚠️ `powershell` (5.1) ŞART, `pwsh` DEĞİL: Mobile Hotspot WinRT API'si PowerShell 7'de
    // YOK → "Operation is not supported on this platform (0x80131539)", netsh yedeği de
    // yönetici ister ve sessizce düşer. 2026-09-10'da tam bu yüzden yanlış teşhis kondu.
    let mut c = crate::platform::gizli_komut("powershell");
    c.args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File"])
        .arg(&betik);
    if !gerekli {
        c.arg("-Kaldir"); // profil kaldırıldıysa görev de temizlenir
    }
    if let Err(e) = baslat(&mut c) {
        if let Some(yol) = gunluk {
            hotspot_gunlugune_ekle(yol, &format!("[launcher] hotspot_gorevi_baslatilamadi: {e}"));
        }
    }
}

/// Best-effort tek satır ekleme (dizin yoksa açılır). Yazılamazsa sessiz: açılış bu yüzden durmaz.
#[cfg(windows)]
fn hotspot_gunlugune_ekle(yol: &Path, satir: &str) {
    use std::io::Write as _;
    if let Some(d) = yol.parent() {
        let _ = fs::create_dir_all(d);
    }
    if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(yol) {
        let _ = writeln!(f, "{satir}");
    }
}

#[cfg(not(windows))]
pub(crate) fn hotspot_gorevini_esitle(_install_root: &Path) {}

/// Backend DURDURULDUKTAN sonra PEMF-Gateway kapatılmalı mı — backend'in AÇTIĞI durumla AYNI kural (sahip 2026-11-04).
///
/// Backend hotspot'u `PEMF_HOTSPOT` "0" / "false" / "False" değilse açar (`backend_service._start_hotspot_safe`); başlatıcı
/// o değişkeni operatörün ortamından AYNEN, yoksa yalnız terapisiz kurulumda "0" geçirir (`install::backend_env_with` · Y234).
/// Backend'in açmadığı hotspot (ev sahibi kurulumu / operatör kapattı) kullanıcınındır → KAPATILMAZ.
#[cfg_attr(not(windows), allow(dead_code))]
pub(crate) fn hotspot_kapatma_gerekli_ile<F>(getenv: F, profiller: &[String]) -> bool
where
    F: Fn(&str) -> Option<String>,
{
    match getenv(install::ENV_HOTSPOT).filter(|v| !v.trim().is_empty()) {
        Some(v) => !matches!(v.trim(), "0" | "false" | "False"),
        None => !install::hotspot_kapatilmali(profiller),
    }
}

/// PEMF-Gateway hotspot'unu kapat — başlatıcı KENDİ başlattığı backend'i durdurduktan SONRA çağırır (sahip 2026-11-04:
/// "backend kapatılırken mobil etkin noktanın da kapanması lazım"). Eskiden kapatan yol YOKTU ve `PEMF-Hotspot` görevi
/// hotspot'u her 3 dk yeniden açıyordu; görev artık `-BekciKipi` ile yalnız backend çalışırken açık tutar.
/// Sahiplenilmez ve BEKLENMEZ: betik (`start_hotspot.ps1 -Kapat`) ayrı süreçte koşar, kapanışı geciktirmez; başlatılamazsa
/// hotspot günlüğüne yazılır. Betik ayrıca hiçbir PEMF backend'i kalmadığını ve SSID'nin PEMF'inki olduğunu kendisi denetler.
#[cfg(windows)]
pub fn hotspot_kapat(install_root: &Path) {
    let gunluk = std::env::var_os("LOCALAPPDATA")
        .filter(|v| !v.is_empty())
        .map(|d| PathBuf::from(d).join("PEMF_System").join("hotspot.log"));
    hotspot_kapat_ile(install_root, |k| std::env::var(k).ok(), gunluk.as_deref(), |c| c.spawn().map(|_| ()));
}

/// `hotspot_kapat`ın test edilebilir hâli — ortam, günlük yolu ve başlatıcı ENJEKTE (`hotspot_gorevini_esitle_ile` deseni).
#[cfg(windows)]
pub(crate) fn hotspot_kapat_ile<F>(
    install_root: &Path,
    getenv: F,
    gunluk: Option<&Path>,
    baslat: impl FnOnce(&mut std::process::Command) -> std::io::Result<()>,
) where
    F: Fn(&str) -> Option<String>,
{
    let betik = install::runtime_dir(install_root)
        .join("PEMF_Backend")
        .join("start_hotspot.ps1");
    if !betik.exists() {
        return; // kaldırılmış / eski paket → sessizce geç
    }
    if !hotspot_kapatma_gerekli_ile(getenv, &install::read_installed_profiles(install_root)) {
        return;
    }
    // `powershell` (5.1) ŞART — Mobile Hotspot WinRT API'si pwsh'ta YOK (bkz. `hotspot_gorevini_esitle_ile`).
    let mut c = crate::platform::gizli_komut("powershell");
    c.args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File"])
        .arg(&betik)
        .arg("-Kapat");
    if let Err(e) = baslat(&mut c) {
        if let Some(yol) = gunluk {
            hotspot_gunlugune_ekle(yol, &format!("[launcher] hotspot_kapatilamadi: {e}"));
        }
    }
}

#[cfg(not(windows))]
pub fn hotspot_kapat(_install_root: &Path) {}

/// Kurulu backend'i başlat (İNDİRME YOK). Hem ilk kurulum sonrası hem "Başlat" bunu kullanır.
pub fn start_backend(
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
) -> Result<(std::process::Child, String, u16), FlowError> {
    start_backend_kimlikli(install_root, on, None)
}

/// `start_backend` + paket kimliği: güncelleme sağlık kapısı `GeriAlmaBilgisi::paket_kimligi()`ni verir
/// (kayıt henüz eski — bkz. `install::paket_kimligini_uygula`). `None` = kayıttaki kimlik.
pub fn start_backend_kimlikli(
    install_root: &Path,
    on: &mut dyn FnMut(Progress),
    paket_kimligi: Option<&str>,
) -> Result<(std::process::Child, String, u16), FlowError> {
    let port = crate::backend::find_free_port(install::DEFAULT_PORT, 50)?;
    on(Progress::StartingBackend { port });
    let child = crate::backend::start_and_wait_kimlikli(
        install_root,
        port,
        std::time::Duration::from_secs(180),
        paket_kimligi,
    )?;
    let url = crate::backend::app_url(port);
    // Hotspot keep-alive görevini her açılışta eşitle: idempotent, penceresiz ve
    // sahiplenilmez. Her açılışta koşması KASITLI — görev elle silinmiş ya da profil
    // değişmişse kendini onarır. Backend hazır olduktan SONRA, açılışı geciktirmesin diye.
    hotspot_gorevini_esitle(install_root);
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
                what: crate::dil::t_ile("rust.kurulum.eskiKurulumAlgilandi", &[("adet", &(v.len()).to_string())]),
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

    /// D5.52 (b) · C12: açılım (parçalardan biri) DÜŞERSE profilin model sha kaydı BOŞ kalır (onarımdaki eski doğru sha
    /// "güncel" diye kalmaz) ve profil "kurulu" İŞARETLENMEZ. Açılım enjekte — gerçek `installed_packages.json`.
    fn model_acilimi_kos(dusen_parca: Option<usize>) -> (bool, Option<String>, bool, usize) {
        let d = tempfile::tempdir().unwrap();
        install::record_model_sha(d.path(), "vet", "ESKI_DOGRU_SHA");
        let zipler = vec![d.path().join("vet.zip"), d.path().join("vet-2.zip")];
        let mut acilan = 0usize;
        let mut isaretlendi = false;
        let r = profil_modelini_ac(
            d.path(),
            "vet",
            &zipler,
            "YENI_SHA",
            &mut |_z| {
                acilan += 1;
                if Some(acilan) == dusen_parca {
                    Err(FlowError::from(std::io::Error::other("sahte açılım hatası")))
                } else {
                    Ok(())
                }
            },
            &mut || isaretlendi = true,
        );
        let sha = install::read_installed_packages(d.path()).models.get("vet").cloned();
        (r.is_ok(), sha, isaretlendi, acilan)
    }

    #[test]
    fn D5_52_model_acilimi_DUSERSE_sha_kaydi_BOS_kalir_ve_kurulu_ISARETLENMEZ() {
        for dusen in [1usize, 2] {
            let (ok, sha, isaret, _) = model_acilimi_kos(Some(dusen));
            assert!(!ok, "{dusen}. parçanın açılımı düştü ama profil açılımı BAŞARILI döndü");
            assert_eq!(
                sha.as_deref(),
                Some(""),
                "{dusen}. parça açılamadı ama kayıt BOŞ değil ({sha:?}) — yarım model 'güncel' sayılır, bir daha yenilenmez (C12)"
            );
            assert!(!isaret, "yarım açılan profil 'kurulu' işaretlendi");
        }
    }

    #[test]
    fn D5_52_tum_parcalar_acilinca_GERCEK_sha_yazilir_ve_isaretlenir() {
        let (ok, sha, isaret, acilan) = model_acilimi_kos(None);
        assert!(ok && isaret && acilan == 2, "başarılı açılım: ok={ok} isaret={isaret} acilan={acilan}");
        assert_eq!(sha.as_deref(), Some("yeni_sha"), "gerçek sha (küçük harf) yazılmadı");
    }

    fn pkg(url: &str, sha: &str) -> crate::Package {
        crate::Package {
            url: url.to_string(),
            sha256: sha.to_string(),
            size: 0,
            kind: "zip".into(),
        }
    }

    const ABC_SHA: &str = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

    /// D5.20 (B-10.90): `dogrula_ya_da_bir_kez_temiz_indir`i gerçek dosya + gerçek `verify` ile koşturur; yeniden indirme
    /// enjekte (ağ YOK). (sonuç, yeniden-indirme çağrı sayısı, dosya hâlâ var mı, içerik).
    fn telafi_kos(ilk: &[u8], ikinci: &[u8], kontrol: net::Control) -> (bool, u32, bool, Vec<u8>) {
        let d = tempfile::tempdir().unwrap();
        let dest = d.path().join("paket.zip");
        fs::write(&dest, ilk).unwrap();
        let mut cagri = 0u32;
        let mut on = |_p: Progress| {};
        let kontrol_fn = move || kontrol;
        let sonuc = dogrula_ya_da_bir_kez_temiz_indir(
            &dest,
            ABC_SHA,
            "paket",
            &mut on,
            &kontrol_fn,
            &mut |_on: &mut dyn FnMut(Progress)| {
                cagri += 1;
                fs::write(&dest, ikinci).map_err(FlowError::from)
            },
        );
        let var = dest.exists();
        let icerik = fs::read(&dest).unwrap_or_default();
        (sonuc.is_ok(), cagri, var, icerik)
    }

    #[test]
    fn D5_20_sha_uyusmazliginda_BIR_KEZ_temiz_yeniden_indirir_ve_dogrular() {
        let (ok, cagri, var, icerik) = telafi_kos(b"BOZUK", b"abc", net::Control::Continue);
        assert_eq!(cagri, 1, "sha uyuşmazlığında temiz yeniden indirme YAPILMADI (ya da birden çok kez yapıldı)");
        assert!(ok && var && icerik == b"abc", "telafi sonrası doğru dosya kabul edilmedi: ok={ok} var={var}");
    }

    #[test]
    fn D5_20_ikinci_indirme_de_bozuksa_HATA_ve_dosya_SILINIR() {
        let (ok, cagri, var, _) = telafi_kos(b"BOZUK", b"HALA-BOZUK", net::Control::Continue);
        assert_eq!(cagri, 1, "telafi TEK seferlik olmalı");
        assert!(!ok, "ikinci indirme de sha'yı tutmadığı hâlde KABUL edildi — telafi sha kontrolünü ZAYIFLATIR");
        assert!(!var, "bozuk dosya diskte bırakıldı → sonraki kurulum onu önbellek sanar");
    }

    #[test]
    fn D5_20_duraklat_ya_da_iptalde_telafi_YAPILMAZ() {
        for k in [net::Control::Pause, net::Control::Cancel] {
            let (ok, cagri, var, _) = telafi_kos(b"BOZUK", b"abc", k);
            assert!(!ok && cagri == 0 && !var, "{k:?}: kullanıcı durdurmuşken yeniden indirildi ya da bozuk dosya kaldı");
        }
    }

    #[test]
    fn D5_20_sha_tutuyorsa_yeniden_indirme_YOK() {
        let (ok, cagri, var, _) = telafi_kos(b"abc", b"BASKA", net::Control::Continue);
        assert!(ok && cagri == 0 && var, "doğru dosya varken gereksiz yeniden indirme");
    }

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

    /// YAYIN 2026-11-03 (`buildId` bulgusu): sağlık kapısına geçen kimlik `install::backend_env_with` ile AYNI kural —
    /// katmanlıda `app`, katmansızda `base`; ikisi de boşsa `None` (kimlik kayıttan okunur).
    #[test]
    fn paket_kimligi_katmanlida_APP_katmansizda_BASE_bossa_YOK() {
        let (a, b) = ("a".repeat(64), "b".repeat(64));
        let katmanli = GeriAlmaBilgisi { tam_takas: true, deps_sha: "c".repeat(64), app_sha: a.clone(), ..Default::default() };
        assert_eq!(katmanli.paket_kimligi(), Some(a.as_str()), "deps ya da boş kimlik seçildi");
        let ikisi = GeriAlmaBilgisi { app_sha: a.clone(), base_sha: b.clone(), ..Default::default() };
        assert_eq!(ikisi.paket_kimligi(), Some(a.as_str()), "app varken base seçildi");
        let tek_parca = GeriAlmaBilgisi { base_sha: b.clone(), ..Default::default() };
        assert_eq!(tek_parca.paket_kimligi(), Some(b.as_str()));
        assert_eq!(GeriAlmaBilgisi { app_yedegi: true, ..Default::default() }.paket_kimligi(), None);
    }

    /// DENETİM 2026-08-04: 4xx KALICIDIR — yeniden denemek kullanıcıyı ~22 sn boşuna bekletiyordu.
    /// Güvenlik reddi ve kullanıcı iptali de ASLA yeniden denenmemeli.
    /// C10 — `_app_roots.json` YOKSA yedek alinamaz ve bu DURUM BILDIRILMELI.
    ///
    /// Kok neden buydu: fonksiyon `Ok(())` donuyordu ve cagiran `app_yedegi: true` yaziyordu.
    /// Kayit gercegi yansitmayinca `guncellemeyi_geri_al` hicbir sey yapmadan "basarili" donuyor,
    /// kullaniciya "eski surume donuldu" deniyor ama cihaz DOGRULANMAMIS surumde kaliyordu.
    /// (Mutasyon turunda `Ok(true)` sabitine donmek HIC yakalanmadi — bu test o bosluk icin.)
    #[test]
    fn C10_kok_listesi_YOKKEN_yedek_alinmadigi_RAPOR_EDILIR() {
        use std::io::Write as _;

        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        let rt = install::runtime_dir(root);
        let kok = rt.join("PEMF_Backend");
        fs::create_dir_all(kok.join("_internal").join("frontend").join("dist")).unwrap();
        fs::write(kok.join(crate::platform::backend_exe_name()), b"ESKI-EXE").unwrap();
        fs::write(kok.join("_internal").join("frontend").join("dist").join("index.html"), b"ESKI-WEB").unwrap();
        // ⚠️ `_app_roots.json` BILEREK YOK (AV karantinasi / yarim onceki acilim / disk hatasi).

        let zip_yolu = root.join("app.zip");
        {
            let f = fs::File::create(&zip_yolu).unwrap();
            let mut z = zip::ZipWriter::new(f);
            let o: zip::write::SimpleFileOptions =
                zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Stored);
            for (ad, icerik) in [
                ("PEMF_Backend/PEMF_Backend.exe", &b"YENI-EXE"[..]),
                ("PEMF_Backend/_internal/frontend/dist/index.html", &b"YENI-WEB"[..]),
            ] {
                z.start_file(ad, o).unwrap();
                z.write_all(icerik).unwrap();
            }
            z.finish().unwrap();
        }

        let mut butce = 0u64;
        let mut on = |_: Progress| {};
        let yedek_alindi =
            app_katmanini_degistir(&zip_yolu, root, &mut butce, &mut on, &|| net::Control::Continue).unwrap();

        assert!(
            !yedek_alindi,
            "kok listesi YOKKEN 'yedek alindi' RAPOR EDILDI — cagiran geri alma sozu verir,              geri alma hicbir sey yapmaz ve kullaniciya 'eski surume donuldu' denir (yanlis guvence)"
        );
        assert!(
            !install::app_backup_dir(root).is_dir(),
            "onkosul: yedek dizini olusmamali (kok listesi bos)"
        );
    }

    /// C2 (denetim 2026-08-24): `hata_deterministik_mi` — hangi update_installed hatası deneme
    /// sayacına yazılır. Deterministik (kilitli model/AV/eksik-exe/güvenlik reddi) → SAY;
    /// kullanıcı iptali/duraklatma + GEÇİCİ ağ hataları → SAYMA.
    #[test]
    fn hata_deterministik_mi_dogru_siniflar() {
        use crate::net::NetError;
        // Kullanıcı kararı → DENEME DEĞİL.
        assert!(!hata_deterministik_mi(&FlowError::Net(NetError::Paused)));
        assert!(!hata_deterministik_mi(&FlowError::Net(NetError::Cancelled)));
        assert!(!hata_deterministik_mi(&FlowError::Extract(extract::ExtractError::Cancelled)));
        // GEÇİCİ ağ → yeniden denenir, DENEME DEĞİL (aksi halde tek ağ hatası düzeltme yayınını bloklardı).
        assert!(!hata_deterministik_mi(&FlowError::Net(NetError::HttpStatus {
            status: 503,
            url: "https://x/y.zip".into()
        })));
        assert!(!hata_deterministik_mi(&FlowError::Net(NetError::Transport("koptu".into()))));
        assert!(!hata_deterministik_mi(&FlowError::Net(NetError::Io(std::io::Error::new(
            std::io::ErrorKind::TimedOut,
            "t"
        )))));
        // DETERMİNİSTİK → SAY (döngü kırıcı devreye girmeli).
        assert!(hata_deterministik_mi(&FlowError::Io(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "yeni kurulum eksik (exe/web bulunamadı)"
        )))); // app yapısal-geçersiz
        assert!(hata_deterministik_mi(&FlowError::Net(NetError::LocalIo("kilitli model".into())))); // C8: AV/kilit
        assert!(hata_deterministik_mi(&FlowError::Net(NetError::PolicyLimit("boyut".into()))));
        assert!(hata_deterministik_mi(&FlowError::Net(NetError::HttpStatus {
            status: 404,
            url: "https://x/y.zip".into()
        }))); // kalıcı 4xx
        assert!(hata_deterministik_mi(&FlowError::Extract(extract::ExtractError::PathEscape("x".into()))));
        assert!(hata_deterministik_mi(&FlowError::ProfileRecordUnreadable));
    }

    /// C4 (denetim 2026-08-24): app-katmanı İÇ YOLUNDA geri alma DÜŞERSE hata YUTULMAZ.
    ///
    /// `app_katmanini_degistir` açılım hatasında eski app'i HEMEN geri koyar (kurulum çalışır
    /// kalsın); geri koyma da düşerse (kilitli dosya / AV) eski hâli `let _ =` ile hatayı YUTUYORDU
    /// → çağırana yalnız açılım hatası/iptal gidiyordu: UI "iptal edildi" derken cihaz
    /// DOĞRULANMAMIŞ/YARIM app ağacıyla kalıyordu. Dış yol (`profilleri_yenile`, 2. tur [3.1])
    /// bu simetriyi zaten kuruyor; bu test iç yolu ona hizalar. Kilit desen: upgrade_drill TATBİKAT 5.
    ///
    /// Geri almayı DETERMİNİSTİK düşürme: yedekteki bir dosyayı AÇIK tut (Windows, içinde açık
    /// handle olan dizinin taşınmasını reddeder → `rename(yedek→rt)` Err) + açılımı iptal et.
    #[test]
    #[cfg(windows)]
    #[allow(non_snake_case)]
    fn C4_app_ic_yol_geri_alma_DUSERSE_hata_yutulmaz() {
        use std::io::Write as _;
        use std::sync::atomic::{AtomicBool, Ordering};
        use std::sync::{Arc, Mutex};

        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        let rt = install::runtime_dir(root);
        let kok = rt.join("PEMF_Backend");
        fs::create_dir_all(kok.join("_internal").join("frontend").join("dist")).unwrap();
        fs::write(kok.join(crate::platform::backend_exe_name()), b"ESKI-EXE").unwrap();
        fs::write(kok.join("_internal").join("frontend").join("dist").join("index.html"), b"ESKI-WEB").unwrap();
        // Yedek ALINABİLSİN diye kök listesi VAR (dizin-kök: içinde açık handle geri-almayı düşürür).
        fs::write(
            install::app_roots_path(root),
            br#"{"roots":["PEMF_Backend/_internal/frontend/dist"]}"#,
        )
        .unwrap();

        // Geçerli app zip — açılım İPTALLE düşecek (içerik önemsiz).
        let zip_yolu = root.join("app.zip");
        {
            let f = fs::File::create(&zip_yolu).unwrap();
            let mut z = zip::ZipWriter::new(f);
            let o: zip::write::SimpleFileOptions =
                zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Stored);
            z.start_file("PEMF_Backend/_internal/frontend/dist/index.html", o).unwrap();
            z.write_all(b"YENI-WEB").unwrap();
            z.finish().unwrap();
        }

        // "app" açılımı BAŞLARKEN (yedek alma bitmiş olur): yedekteki dosyayı AÇIK tut + iptal et.
        let iptal = Arc::new(AtomicBool::new(false));
        let tutamac: Arc<Mutex<Option<fs::File>>> = Arc::new(Mutex::new(None));
        let iptal_c = iptal.clone();
        let tutamac_c = tutamac.clone();
        let yedek_dist_idx = install::app_backup_dir(root)
            .join("PEMF_Backend")
            .join("_internal")
            .join("frontend")
            .join("dist")
            .join("index.html");
        let mut on = move |p: Progress| {
            if let Progress::Extracting { what } = &p {
                if what == "app" {
                    let f = fs::File::open(&yedek_dist_idx)
                        .expect("yedek dosyasi bekleniyordu (yedek alma dalina girilmedi mi?)");
                    *tutamac_c.lock().unwrap() = Some(f);
                    iptal_c.store(true, Ordering::SeqCst);
                }
            }
        };
        let control = || {
            if iptal.load(Ordering::SeqCst) {
                net::Control::Cancel
            } else {
                net::Control::Continue
            }
        };

        let mut butce = 0u64;
        let sonuc = app_katmanini_degistir(&zip_yolu, root, &mut butce, &mut on, &control);
        let hata = format!("{}", sonuc.err().expect("iptal + geri-alma-dusmesi basarili dondu"));
        assert!(
            hata.contains("GERI ALINAMADI"),
            "app ic yolunda geri alma DUSTU ama hata YUTULDU — cagiran 'iptal edildi' sanir, cihaz \
             dogrulanmamis/yarim app agaciyla kalir (bulgu C4; dis yol [3.1] ile simetri). Donen hata: {hata}"
        );
        drop(tutamac.lock().unwrap().take());
    }

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
        // YLI-A2.5 (D4.15 tek kaynak): DNS indirmede de GEÇİCİ — flow'da ayrı (DNS'siz) bir kopya geri gelirse burada düşer.
        assert!(is_retriable(&net::NetError::Dns("resolve dns name".into())), "DNS indirmede KALICI sayildi (08-29 sinifi)");
        for e in [net::NetError::Dns("x".into()), st(503), st(404), net::NetError::LocalIo("x".into()), net::NetError::Paused] {
            assert_eq!(is_retriable(&e), net::gecici_hata_mi(&e), "flow ile net kurali ayristi: {e:?}");
        }
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
        // ⚠️ DENETİM 2026-08-23 (C8): YEREL dosya hatası da deterministiktir. En kötü hâli
        // TAMAMLANMIŞ indirmenin `rename`inde düşmesiydi (AV / os error 32): 6 deneme boyunca
        // her seferinde tam `.part` silinip 1,19 GB sıfırdan iniyordu.
        assert!(
            !is_retriable(&net::NetError::LocalIo("dosya taşınamadı".into())),
            "yerel dosya hatasi GECICI sayildi — tek bir rename hatasi ~7 GB bosuna trafik uretir"
        );
        // KARŞI-KANIT: `Io` hâlâ GEÇİCİ olmalı — o kol gerçek AĞ okuma hatalarını taşıyor
        // (`reader.read(...)?`). İkisini birden kalıcı yapmak, kopan bağlantıda yeniden denemeyi
        // öldürür ve kararsız hatta kurulumu imkânsızlaştırırdı.
        assert!(
            is_retriable(&net::NetError::Io(std::io::Error::new(
                std::io::ErrorKind::ConnectionReset,
                "baglanti sifirlandi"
            ))),
            "ag okuma hatasi KALICI sayildi — kararsiz hatta yeniden deneme olur"
        );
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
        // ⚠️ DENETIM 2026-08-28 #06: bu fixture ESKIDEN `ai_models/home/` + `ai_models/vet/`
        // diye ELLE uyduruluyordu — URETIMDE HIC OLUSMAYAN bir duzen. Gercek profil zip'leri
        // `ai_models/ai_hub/<modul>/...` acar (make_model_zip.py; yayindaki vet.zip merkezi
        // dizininde dogrulandi). Uydurma duzen yuzunden bu kapi, "Onar" fiilen bozukken
        // YESIL kaliyordu: gercek kurulumda cikarim ["ai_hub"] donuyor ve repair()
        // UnknownProfile{profile:"ai_hub"} ile indirme baslamadan dusuyordu.
        let hub = install::models_dir(root).join("ai_hub");
        for modul in ["cat_disease", "cat_thermal", "em_petri"] {
            std::fs::create_dir_all(hub.join(modul)).unwrap();
            std::fs::write(hub.join(modul).join("m.onnx"), b"x").unwrap();
        }
        assert!(matches!(
            install::read_installed_profiles_detailed(root),
            install::ProfileRecord::Missing
        ));

        let bulunan = install::infer_profiles_from_disk(root);
        assert_eq!(
            bulunan,
            vec!["home".to_string(), "research".to_string(), "vet".to_string()],
            "GERCEK sevk duzeninden profiller cikarilamadi — eski kurulumlarda Onar calismaz"
        );
    }

    /// Geriye uyum: dogrudan `ai_models/<profil>/` duzeni de kabul edilmeli (elle kurulum).
    #[test]
    fn duz_profil_dizini_duzeni_de_desteklenir() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        for prof in ["home", "vet"] {
            std::fs::create_dir_all(install::models_dir(root).join(prof)).unwrap();
            std::fs::write(install::models_dir(root).join(prof).join("m.onnx"), b"x").unwrap();
        }
        assert_eq!(
            install::infer_profiles_from_disk(root),
            vec!["home".to_string(), "vet".to_string()]
        );
    }

    /// ⚠️ Manifest'te KARSILIGI OLMAYAN bir dizin adi profil sanilmamali.
    /// Eskiden "ai_hub" tam da boyle sizip repair()'i UnknownProfile ile dusuruyordu.
    #[test]
    fn bilinmeyen_dizin_adi_profil_sayilmaz() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        for ad in ["ai_hub", "gecici", "yedek"] {
            std::fs::create_dir_all(install::models_dir(root).join(ad)).unwrap();
        }
        // ai_hub bos (modul yok) → hicbir profil cikmamali; digerleri de profil DEGIL.
        assert!(
            install::infer_profiles_from_disk(root).is_empty(),
            "bilinmeyen dizin adlari profil sanildi — repair() UnknownProfile ile duser"
        );
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

    /// Kurulu bir cihaz kur (guncelleme testlerinin ortak on kosulu).
    fn kurulu_cihaz(root: &Path, base_sha: &str) {
        let rt = install::runtime_dir(root);
        std::fs::create_dir_all(rt.join("PEMF_Backend")).unwrap();
        std::fs::write(install::backend_path(root), b"exe").unwrap();
        install::record_base_sha(root, base_sha);
    }

    /// 🔴 DENETIM 2026-08-16 (Bulgu 2): OTO-GUNCELLEME yolunda disk kapisi YOKTU.
    ///
    /// 2026-08-09 denetimi kapiyi OLCEREK ekledi ama yalniz `install_profiles`e (kullanicinin
    /// IZLEDIGI ilk kurulum). `update_installed` GOZETIMSIZ kosar: alan yetmezse guncelleme
    /// sessizce basarisiz olur, olu onbellek de hic geri kazanilmaz.
    #[test]
    fn guncellemede_yetersiz_disk_INDIRMEDEN_once_durdurur() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        kurulu_cihaz(root, &"b".repeat(64));

        let sha = "a".repeat(64);
        let man = format!(
            concat!(r#"{{"schema":2,"version":"9.9.9","runtimes":{{"{plat}":"#,
                    r#"{{"url":"https://example.invalid/base.zip","sha256":"{sha}","#,
                    r#""size":9000000000000,"kind":"zip"}}}},"models":{{}}}}"#),
            plat = crate::platform::current(), sha = sha);

        let mut olaylar: Vec<String> = Vec::new();
        let mut on = |p: Progress| {
            if let Progress::Downloading { .. } = p { olaylar.push("indirme".into()); }
        };
        let r = update_installed(&man, root, &mut on, &|| net::Control::Continue);

        let e = r.expect_err("imkansiz boyutta guncelleme 'basarili' dondu");
        let mesaj = e.to_string();
        assert!(mesaj.contains("disk") || mesaj.contains("Disk"),
            "hata disk alanini soylemiyor: {mesaj}");
        assert!(olaylar.is_empty(),
            "kontrol INDIRMEDEN SONRA yapilmis — guncelleme bosuna GB indirirdi");
    }

    /// 🔴 ARKA PLAN indirmesi de korumasizdi: gozetimsiz 1,5 GB indirip diski doldurabiliyordu
    /// ve hata kullaniciya HIC gorunmuyordu (`.catch` sessiz).
    #[test]
    fn on_indirmede_yetersiz_disk_INDIRMEDEN_once_durdurur() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        kurulu_cihaz(root, &"b".repeat(64));

        let sha = "a".repeat(64);
        let man = format!(
            concat!(r#"{{"schema":2,"version":"9.9.9","runtimes":{{"{plat}":"#,
                    r#"{{"url":"https://example.invalid/base.zip","sha256":"{sha}","#,
                    r#""size":9000000000000,"kind":"zip"}}}},"models":{{}}}}"#),
            plat = crate::platform::current(), sha = sha);

        let mut olaylar: Vec<String> = Vec::new();
        let mut on = |p: Progress| {
            if let Progress::Downloading { .. } = p { olaylar.push("indirme".into()); }
        };
        let r = prefetch_updates(&man, root, &mut on, &|| net::Control::Continue);

        // ⚠️ Yalnız `is_err()` YETMEZ: kapi kaldirilsa bile `ensure_package` erisilemez host'a
        // gidip HATA doner — test ikisini ayirt edemez (mutasyon turu 2026-08-16 bunu gosterdi).
        // Hatanin DISK hatasi oldugunu dogrula.
        let e = r.expect_err("imkansiz boyutta on-indirme 'basarili' dondu");
        let mesaj = e.to_string();
        assert!(mesaj.contains("disk") || mesaj.contains("Disk"),
            "on-indirme disk kapisina TAKILMADI (ag hatasina dustu): {mesaj}");
        assert!(olaylar.is_empty(), "on-indirme kontrolden ONCE aga cikti");
    }

    /// ON-INDIRME yalniz ZIP'i indirir (acma YOK) -> 2x yer istemek YANLIS olurdu.
    ///
    /// Kurulum yolu 2x ister (zip + acilmis agac); on-indirme 1x. Ikisi ayni hesabi kullanirsa
    /// prefetch gereksiz yere "yer yok" der ve arka plan indirmesi HIC calismaz.
    ///
    /// ⚠️ Bu test iki kez duzeltildi (mutasyon turu 2026-08-16):
    ///   1) once GERCEK diski olcup bol-yerli makinede erken donuyordu -> hicbir sey kanitlamiyordu;
    ///   2) sonra `gereken_alan`i DOGRUDAN cagiriyordu -> `disk_kapisi`nin hangi bicimi kullandigini
    ///      hic sinamiyordu (cagri yeri bozulsa test yine yesil kalirdi).
    /// Artik `disk_kapisi`nin KENDISI cagriliyor ve boyut, olculen bos alandan turetiliyor:
    /// 1x sigar, 2x sigmaz. Disk durumundan bagimsiz olarak ayrimi zorlar.
    #[test]
    fn on_indirme_kurulumdan_DAHA_AZ_yer_ister() {
        let d = tempfile::tempdir().unwrap();
        let cache = d.path().join("cache");
        std::fs::create_dir_all(&cache).unwrap();
        let Some(bos) = crate::disk::bos_alan(d.path()) else {
            return; // olculemiyorsa kapi zaten DAIMA Ok doner; ayrim sinanamaz
        };
        // bos/2: 1x + %10 pay  ~ %55 -> SIGAR | 2x + %10 pay ~ %110 -> SIGMAZ
        let pkg = crate::Package {
            url: "https://example.invalid/x.zip".into(),
            sha256: "a".repeat(64),
            size: bos / 2,
            kind: "zip".into(),
        };
        let gerekli = vec![(&pkg, "base".to_string())];
        let mut on = |_: Progress| {};

        assert!(
            disk_kapisi(&gerekli, d.path(), &cache, &mut on, false, &[]).is_ok(),
            "on-indirme (1x) sigmasi gerekirken reddedildi -> arka plan indirmesi hic calismaz"
        );
        assert!(
            disk_kapisi(&gerekli, d.path(), &cache, &mut on, true, &[]).is_err(),
            "kurulum (2x) sigmamasi gerekirken kabul edildi -> acilirken disk dolar"
        );
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

    /// 🔴 [Onar/önbellek çelişkisi — sahip onayı 2026-08-20]: temizlik yalnız O İŞLEMİN paket
    /// kümesini koruyordu; KURULU ama bu işlemde seçilmemiş profilin geçerli zip'i "ölü" sayılıp
    /// siliniyordu → "Onar" 20+ dk indirmeye dönüyor, UI'ın "indirilenler önbellekten gelir,
    /// yeniden İNMEZ" vaadi (ProfileRecordUnreadable metni dahil) boşa çıkıyordu.
    #[test]
    fn KRITIK_onar_celiskisi_kurulu_profil_paketi_onbellekte_KORUNUR() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        let cache = install::cache_dir(root);
        std::fs::create_dir_all(&cache).unwrap();
        // Kurulu profil kaydı: "vet" kurulu — ama bu işlem yalnız base kuruyor (selected=[]).
        std::fs::write(root.join("installed_profiles.json"), r#"["vet"]"#).unwrap();
        // vet.zip önbellekte GEÇERLİ duruyor (adı güncel manifestin model URL'sinden).
        let vet = cache.join("vet.zip");
        std::fs::write(&vet, vec![1u8; 128]).unwrap();
        // Manifestten DÜŞMÜŞ gerçek ölü girdi — özellik korunuyor mu (karşıt-kanıt)?
        let olu = cache.join("ESKI-SURUM-base.zip");
        std::fs::write(&olu, vec![0u8; 4096]).unwrap();

        let man = format!(
            concat!(r#"{{"schema":2,"version":"9.9.9","runtimes":{{"{plat}":"#,
                    r#"{{"url":"https://example.invalid/base.zip","sha256":"{sha}","#,
                    r#""size":9000000000000,"kind":"zip"}}}},"models":{{"vet":"#,
                    r#"{{"url":"https://example.invalid/vet.zip","sha256":"{sha}","#,
                    r#""size":1,"kind":"zip"}}}}}}"#),
            plat = crate::platform::current(), sha = "a".repeat(64));

        let mut on = |_: Progress| {};
        // İmkânsız boyut → akış disk kapısında durur; temizlik ondan ÖNCE koşmuştur.
        let _ = install_profiles(&man, &[], root, &mut on, &|| net::Control::Continue);

        assert!(vet.exists(),
            "KURULU profilin (vet) geçerli zip'i 'ölü önbellek' diye SİLİNDİ → Onar yeniden indirir, \
             'önbellekten gelir' vaadi yalan olur (Onar/önbellek çelişkisi)");
        assert!(!olu.exists(),
            "gerçekten ölü girdi SİLİNMEDİ → eMMC disk-kazanım özelliği bozuldu (aşırı-düzeltme)");
    }

    /// 🔴 Aynı çelişkinin OTO-GÜNCELLEME yüzü: app-only bir plan, sha'sı GÜNCEL deps.zip'i
    /// (planın dışında diye) siliyordu — bir sonraki deps güncellemesi/Onar yeniden indirir.
    #[test]
    fn KRITIK_onar_celiskisi_guncel_katman_paketi_guncellemede_KORUNUR() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        kurulu_cihaz(root, &"b".repeat(64));
        let cache = install::cache_dir(root);
        std::fs::create_dir_all(&cache).unwrap();

        let deps_sha = "c".repeat(64);
        let app_sha = "d".repeat(64);
        // Kurulu kayıt: deps GÜNCEL (sha eşit), app BAYAT → plan yalnız app'i içerir.
        std::fs::write(
            install::installed_packages_path(root),
            format!(r#"{{"base":"","deps":"{deps_sha}","app":"ESKI","models":{{}}}}"#),
        )
        .unwrap();
        let deps = cache.join("deps.zip");
        std::fs::write(&deps, vec![2u8; 64]).unwrap();

        let man = format!(
            concat!(r#"{{"schema":2,"version":"9.9.9","runtimes":{{}},"layers":{{"{plat}":"#,
                    r#"{{"deps":{{"url":"https://example.invalid/deps.zip","sha256":"{d_sha}","size":1,"kind":"zip"}},"#,
                    r#""app":{{"url":"https://example.invalid/app.zip","sha256":"{a_sha}","size":1,"kind":"zip"}}}}}},"#,
                    r#""models":{{}}}}"#),
            plat = crate::platform::current(), d_sha = deps_sha, a_sha = app_sha);

        let mut on = |_: Progress| {};
        // İndirme pinlenmemiş host'ta düşer — temizlik ondan ÖNCE koşmuştur.
        let _ = update_installed(&man, root, &mut on, &|| net::Control::Continue);

        assert!(deps.exists(),
            "sha'sı GÜNCEL deps.zip app-only güncellemede 'ölü' diye SİLİNDİ → Onar/sonraki tur \
             1+ GB'ı yeniden indirir (Onar/önbellek çelişkisi, oto-güncelleme yüzü)");
    }

    /// 17. parti (adversaryal test-gaming bulgusu): üç disk_kapisi çağrı yerinden yalnız ikisi
    /// pinliydi — prefetch_updates'teki `&koru` sessizce `&[]`e döndürülebiliyordu (gözetimsiz
    /// arka plan yolunda kurulu-güncel deps.zip'in silinmesi: düzeltilen sınıfın kendisi).
    #[test]
    fn KRITIK_onar_celiskisi_on_indirme_yolunda_da_KORUR() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        kurulu_cihaz(root, &"b".repeat(64));
        let cache = install::cache_dir(root);
        std::fs::create_dir_all(&cache).unwrap();

        let deps_sha = "c".repeat(64);
        let app_sha = "d".repeat(64);
        std::fs::write(
            install::installed_packages_path(root),
            format!(r#"{{"base":"","deps":"{deps_sha}","app":"ESKI","models":{{}}}}"#),
        )
        .unwrap();
        let deps = cache.join("deps.zip");
        std::fs::write(&deps, vec![2u8; 64]).unwrap();

        let man = format!(
            concat!(r#"{{"schema":2,"version":"9.9.9","runtimes":{{}},"layers":{{"{plat}":"#,
                    r#"{{"deps":{{"url":"https://example.invalid/deps.zip","sha256":"{d_sha}","size":1,"kind":"zip"}},"#,
                    r#""app":{{"url":"https://example.invalid/app.zip","sha256":"{a_sha}","size":1,"kind":"zip"}}}}}},"#,
                    r#""models":{{}}}}"#),
            plat = crate::platform::current(), d_sha = deps_sha, a_sha = app_sha);

        let mut on = |_: Progress| {};
        let _ = prefetch_updates(&man, root, &mut on, &|| net::Control::Continue);

        assert!(deps.exists(),
            "ON-INDIRME yolunda sha'sı GÜNCEL deps.zip 'ölü' diye SİLİNDİ — gözetimsiz arka plan \
             turu önbelleği boşaltır (Onar/önbellek çelişkisinin prefetch yüzü)");
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

    /// LN L12 (17'nin yerleştirmesi buna dayanır): yayındaki manifest kopyası (app 1.9.50 · deps 1.9.41 · `min_supported_version`
    /// YOK) ile kurulu kayıt (`installed_packages.json`) AYNI sha'ları taşırken APP katmanı yeniden İNMEZ — ağaçtaki `VERSION` yeni
    /// bir derlemeyi (1.9.51) gösterse bile: karar yalnız kayıt ↔ manifest SHA'sı, ağaç yalnız yapısal denetlenir
    /// (`kurulum_saglam_mi`), `VERSION` yalnız geri çağırma (`min_supported_version`) içindir. KARŞIT: kayıttaki app sha'sı yayındakinden
    /// farklıysa (yerleştiren kaydı yeni derlemenin sha'sıyla yazarsa) launcher yayındaki app'i indirip yerleştirileni EZER.
    #[test]
    fn KRITIK_L12_kurulu_kayit_1_9_50_iken_APP_katmani_YENIDEN_INMEZ() {
        let yol = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../pemf-app-packages/manifest.json");
        let raw = fs::read_to_string(&yol).unwrap_or_else(|e| panic!("yayındaki manifest kopyası okunamadı {}: {e}", yol.display()));
        let m = Manifest::parse(&raw).unwrap();
        let Some(l) = m.layers_for_current_platform() else {
            assert!(!cfg!(windows), "yayındaki kopyada bu platformun (win-x64) katmanı yok");
            return;
        };
        assert!(m.min_supported_version.is_none(), "yayında geri çağırma VAR — bu test ve 17'nin varsayımı yeniden ölçülmeli");
        let dir = tempfile::tempdir().unwrap();
        sahte_kurulum(dir.path());
        let surum = install::runtime_dir(dir.path()).join("PEMF_Backend").join("_internal").join("VERSION");
        fs::create_dir_all(surum.parent().unwrap()).unwrap();
        fs::write(&surum, "1.9.51\n").unwrap();
        install::record_layer_sha(dir.path(), "deps", &l.deps.sha256);
        install::record_layer_sha(dir.path(), "app", &l.app.sha256);
        let plan = pending_updates(&raw, dir.path()).unwrap();
        assert!(!plan.needed() && !plan.app && !plan.deps && !plan.zorunlu, "yayındaki app yeniden indirilecekti: {plan:?}");
        // KARŞIT: kayıt yeni derlemenin sha'sını taşırsa yayındaki app katmanı iner (yerleştirilen ezilir).
        install::record_layer_sha(dir.path(), "app", SHA_B);
        let plan = pending_updates(&raw, dir.path()).unwrap();
        assert!(plan.app && !plan.deps, "kayıt farkı görülmedi: {plan:?}");
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
            let o: zip::write::SimpleFileOptions =
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
        let yedek_alindi =
            app_katmanini_degistir(&zip_yolu, root, &mut butce, &mut on, &|| net::Control::Continue).unwrap();
        assert!(yedek_alindi, "kok listesi DOLUYKEN yedek alinmadi — geri alma yolu olur");
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
        // ⚠️ 2026-09-11 DUZELTME — AYNI KOR NOKTA **BESINCI** YERDE.
        // Burada "tek parca 'runtimes' girdisi DURMALI" yaziyordu. Monolit (`base.zip`) 1.9.48'de
        // sahip karariyla KALICI olarak yayindan cikarildi (yayin 1,55 GB -> 210 MB) ve manifest
        // artik yalniz `layers` tasiyor. Iddia, kurulabilirligi TEK-PARCA KOPYAYLA olcuyordu →
        // dogru bir yayinda kirmizi oldu. Ayni kok daha once DORT yerde bulundu: launcher
        // `platform_supported`, `make_manifest`in "hicbir base paketi yok" kapisi,
        // `test_manifest_consistency` sayaci ve `make_manifest`in tazelik kapisi.
        //
        // DOGRU IDDIA: bu platformda KURULABILIR bir sey olmali — `runtimes` YA DA `layers`.
        // Ikisi de yoksa client "paket yok" deyip durur; o hala bir ariza ve burada KIRMIZI.
        // ⚠️ Not: `base.zip` yokken client <=1.9.12 kurulum yapamaz — bu BILINEN ve KABUL EDILEN
        // bir sonuctur (launcher >=1.9.51 katmanlari da sayar), test edilecek bir hata degil.
        assert!(
            m.runtime_for_current_platform().is_ok() || m.layers_for_current_platform().is_some(),
            "bu platformda NE tek-parca NE katman var — hicbir client kurulum yapamaz"
        );
        // Self-update imzasi: installer_url varsa sha256 ZORUNLU (parse zaten dogrular, burada
        // manifest'in gercekten o alani tasidigini kilitliyoruz).
        let lc = m.launcher.as_ref().expect("launcher bolumu yok");
        assert!(lc.installer_url.is_some(), "installer_url yok — oto-guncelleme calismaz");
    }

    // ── HOTSPOT GÖREVİ PROFİL KAPISI (2026-09-10) ────────────────────────────────────────
    // Bu kapı iki ayrı sahada-görülmüş arızanın arasında duruyor:
    //   (a) görev HİÇ kurulmazsa  → hotspot düşünce geri gelmez, ESP bobinleri bağlanamaz;
    //   (b) HER makinede kurulursa → gereksiz AP açılır, aynı-WiFi keşfini bozar (mDNS bulgusu).
    // Bu yüzden hem "açılmalı" hem "açılmamalı" yönü ayrı ayrı pinlenir.
    fn p(v: &[&str]) -> Vec<String> {
        v.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    #[allow(non_snake_case)]
    fn KRITIK_terapi_profilinde_hotspot_gorevi_GEREKLI() {
        // vet ve research bobin sürer → AP şart (ESP 6-8 buraya bağlanır).
        assert!(hotspot_gorevi_gerekli(&p(&["vet"])), "vet: gorev gerekli olmali");
        assert!(hotspot_gorevi_gerekli(&p(&["research"])), "research: gorev gerekli olmali");
        assert!(hotspot_gorevi_gerekli(&p(&["home", "vet"])), "home+vet: vet belirleyici olmali");
    }

    #[test]
    #[allow(non_snake_case)]
    fn KRITIK_yalniz_ev_sahibi_profilinde_hotspot_gorevi_GEREKMEZ() {
        // ⚠️ Ev sahibi profili ANALİZ-ONLY (otonom terapi yok) → bobin sürmez, AP'ye gerek yok.
        // Bu iddia TRUE'ya dönerse her ev-sahibi kurulumunda gereksiz bir Wi-Fi AP açılır.
        assert!(!hotspot_gorevi_gerekli(&p(&["home"])), "yalniz home: AP acilmamali");
        assert!(!hotspot_gorevi_gerekli(&[]), "profilsiz kurulum: AP acilmamali");
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

    // ── FAZ 4.5: birlesik kimlik + benzersiz onbellek etiketi ───────────────
    #[test]
    fn faz45_birlesik_sha_tek_parcada_ana_shanin_kendisi() {
        // Eski installed_packages kayitlariyla BIREBIR kalmali — yoksa yukseltmede
        // her profil sahte-bayat olur ve GB'lar bosuna iner.
        let a = pkg("https://x/research.zip", ABC_SHA);
        assert_eq!(birlesik_model_sha(&[&a]), ABC_SHA);
        let b = pkg("https://x/research-2.zip", "f".repeat(64).as_str());
        let birlesik = birlesik_model_sha(&[&a, &b]);
        assert!(birlesik.contains('+') && birlesik.starts_with(ABC_SHA));
    }

    #[test]
    fn faz45_profil_paketleri_etiketleri_benzersiz() {
        // cache_path_for guvensiz-URL fallback'i ETIKETE duser; iki parca ayni
        // etikete duserse onbellekte birbirini EZER (kesif tuzagi #3).
        let manifest = Manifest::parse(&format!(
            r#"{{"schema":2,"version":"1",
                 "models": {{"research": {{"url":"https://x/a.zip","sha256":"{h}","size":1}} }},
                 "model_parts": {{"research": [ {{"url":"https://x/b.zip","sha256":"{h}","size":1}} ] }} }}"#,
            h = ABC_SHA
        ))
        .unwrap();
        let ciftler = profil_paketleri(&manifest, "research").unwrap();
        assert_eq!(ciftler.len(), 2);
        assert_eq!(ciftler[0].1, "research");
        assert_eq!(ciftler[1].1, "research-p2");
        assert_ne!(ciftler[0].1, ciftler[1].1);
    }

    #[test]
    #[allow(non_snake_case)]
    fn faz45_adopt_parcali_profilde_MUHAFAZAKAR_ana_sha_benimser() {
        // Kayit kaybi senaryosu: parcalarin diskte oldugu DOGRULANAMAZ ->
        // birlesik kimlik benimsenirse eksik parcalar sonsuza dek gizli kalirdi.
        // Kaynak-duzeyi kilit: adopt govdesi birlesik degil pkgs[0] yazmali.
        let src = include_str!("flow.rs");
        let i = src.find("pub fn adopt_unknown_models").expect("adopt bulunmali");
        // SABIT-UZUNLUK PENCERESI KULLANMA (CI'da olculdu): Windows runner CRLF
        // checkout eder, ayni bayt penceresi daha az satir kapsar ve assert
        // penceresinin DISINDA kalir (yerel LF'te yesil, CI'da kirmizi).
        // Fonksiyon-sonu cipasi bayt-bicimden bagimsizdir.
        let j = src[i..].find("
pub fn ").map(|k| i + k).unwrap_or(src.len());
        let govde = &src[i..j];
        assert!(govde.contains("pkgs[0].sha256"), "adopt ana-sha benimsemiyor");
        assert!(
            !govde.contains("birlesik_model_sha"),
            "adopt birlesik kimlik benimsiyor — sessiz eksik-model penceresi"
        );
    }

    /// D5.16 (B-10.75): görev betiği Windows PowerShell 5.1 (`powershell`, `pwsh` DEĞİL) ile çağrılır ve başlatma HATASI
    /// günlüğe yazılır (eskiden `let _ = c.spawn();` ile atılıyordu). Gerçek süreç BAŞLATILMAZ — başlatıcı enjekte.
    #[cfg(windows)]
    #[test]
    fn hotspot_gorevi_PS51_ile_cagrilir_ve_baslatma_HATASI_gunluge_yazilir() {
        let d = tempfile::tempdir().unwrap();
        let kok = d.path().join("kok");
        let betik = install::runtime_dir(&kok).join("PEMF_Backend").join("install_hotspot_task.ps1");
        fs::create_dir_all(betik.parent().unwrap()).unwrap();
        fs::write(&betik, "# sahte betik (calistirilmaz)").unwrap();
        let gunluk = d.path().join("LocalAppData").join("PEMF_System").join("hotspot.log");
        let mut goruldu: Option<(std::ffi::OsString, Vec<std::ffi::OsString>)> = None;
        hotspot_gorevini_esitle_ile(&kok, Some(&gunluk), |c| {
            goruldu = Some((c.get_program().to_owned(), c.get_args().map(|a| a.to_owned()).collect()));
            Err(std::io::Error::new(std::io::ErrorKind::NotFound, "sahte-baslatici: powershell yok"))
        });
        let (program, args) = goruldu.expect("görev betiği hiç başlatılmak istenmedi");
        assert_eq!(program, std::ffi::OsString::from("powershell"), "görev pwsh/başka yorumlayıcıyla çağrılıyor — WinRT hotspot API'si yalnız 5.1'de");
        let i = args.iter().position(|a| a == "-File").expect("-File yok");
        assert_eq!(args.get(i + 1).map(std::path::PathBuf::from), Some(betik.clone()), "-File görev betiğini göstermiyor");
        assert!(args.iter().any(|a| a == "-Kaldir"), "profil kurulu değilken görev KALDIRILMALI (-Kaldir)");
        let metin = fs::read_to_string(&gunluk).expect("başlatma hatası günlüğe YAZILMADI (D5.16)");
        assert!(metin.contains("sahte-baslatici: powershell yok"), "günlük satırı hatayı taşımıyor: {metin:?}");
    }

    /// Karşıt: betik paketlenmemişse (eski paket) başlatıcı ÇAĞRILMAZ ve günlük AÇILMAZ.
    #[cfg(windows)]
    #[test]
    fn hotspot_betigi_yoksa_baslatici_CAGRILMAZ() {
        let d = tempfile::tempdir().unwrap();
        let gunluk = d.path().join("hotspot.log");
        let mut cagrildi = false;
        hotspot_gorevini_esitle_ile(&d.path().join("kok"), Some(&gunluk), |_| {
            cagrildi = true;
            Ok(())
        });
        assert!(!cagrildi && !gunluk.exists());
    }

    /// Sahip 2026-11-04: kapatma kuralı backend'in AÇMA kuralıyla AYNI — `PEMF_HOTSPOT` "0" / "false" / "False" (boşluklu da)
    /// = backend açmadı → kapatma; başka değer = kapat; değişken yoksa yalnız terapisiz (`home`) kurulumda kapatma (kayıt yok /
    /// boş = backend varsayılanı açar → kapat).
    #[test]
    fn hotspot_kapatma_kurali_backendin_ACMA_kuraliyla_AYNI() {
        let vet = vec!["vet".to_string()];
        let ev = vec!["home".to_string()];
        let ortam = |v: Option<&'static str>| move |k: &str| if k == install::ENV_HOTSPOT { v.map(str::to_string) } else { None };
        for v in ["0", "false", "False", " 0 "] {
            assert!(!hotspot_kapatma_gerekli_ile(ortam(Some(v)), &vet), "PEMF_HOTSPOT={v:?} — backend açmadı, kapatılmamalı");
        }
        assert!(hotspot_kapatma_gerekli_ile(ortam(Some("1")), &ev), "operatör açtıysa ev kurulumunda da kapatılır");
        assert!(hotspot_kapatma_gerekli_ile(ortam(Some("   ")), &vet), "boş değer = tanımsız");
        assert!(hotspot_kapatma_gerekli_ile(ortam(None), &vet));
        assert!(hotspot_kapatma_gerekli_ile(ortam(None), &["research".to_string(), "home".to_string()]));
        assert!(!hotspot_kapatma_gerekli_ile(ortam(None), &ev), "ev sahibi kurulumunda backend açmaz → kullanıcının hotspot'u");
        assert!(hotspot_kapatma_gerekli_ile(ortam(None), &[]), "kayıt yok / boş = backend varsayılanı açar → kapat");
    }

    /// Sahip 2026-11-04: kapatma `start_hotspot.ps1 -Kapat`ı Windows PowerShell 5.1 ile GİZLİ çağırır; başlatma hatası günlüğe
    /// yazılır; betik yoksa / ev sahibi kurulumunda başlatıcı ÇAĞRILMAZ. Gerçek süreç BAŞLATILMAZ — başlatıcı enjekte.
    #[cfg(windows)]
    #[test]
    fn hotspot_kapat_PS51_ile_Kapat_kipini_cagirir_yoksa_ya_da_ev_kurulumunda_CAGIRMAZ() {
        let d = tempfile::tempdir().unwrap();
        let kok = d.path().join("kok");
        let betik = install::runtime_dir(&kok).join("PEMF_Backend").join("start_hotspot.ps1");
        let gunluk = d.path().join("LocalAppData").join("PEMF_System").join("hotspot.log");
        let ortam_yok = |_: &str| None::<String>;
        let mut cagrildi = false;
        hotspot_kapat_ile(&kok, ortam_yok, Some(&gunluk), |_| {
            cagrildi = true;
            Ok(())
        });
        assert!(!cagrildi && !gunluk.exists(), "betik yokken başlatıcı çağrıldı");
        fs::create_dir_all(betik.parent().unwrap()).unwrap();
        fs::write(&betik, "# sahte betik (calistirilmaz)").unwrap();
        fs::write(install::installed_profiles_path(&kok), r#"["home"]"#).unwrap();
        hotspot_kapat_ile(&kok, ortam_yok, Some(&gunluk), |_| {
            cagrildi = true;
            Ok(())
        });
        assert!(!cagrildi, "ev sahibi kurulumunda (backend hotspot açmaz) kapatma çağrıldı");
        fs::write(install::installed_profiles_path(&kok), r#"["vet"]"#).unwrap();
        let mut goruldu: Option<(std::ffi::OsString, Vec<std::ffi::OsString>)> = None;
        hotspot_kapat_ile(&kok, ortam_yok, Some(&gunluk), |c| {
            goruldu = Some((c.get_program().to_owned(), c.get_args().map(|a| a.to_owned()).collect()));
            Err(std::io::Error::new(std::io::ErrorKind::NotFound, "sahte-baslatici: powershell yok"))
        });
        let (program, args) = goruldu.expect("kapatma betiği hiç başlatılmak istenmedi");
        assert_eq!(program, std::ffi::OsString::from("powershell"), "kapatma pwsh / başka yorumlayıcıyla — WinRT yalnız 5.1'de");
        let i = args.iter().position(|a| a == "-File").expect("-File yok");
        assert_eq!(args.get(i + 1).map(std::path::PathBuf::from), Some(betik.clone()), "-File start_hotspot.ps1'i göstermiyor");
        assert_eq!(args.get(i + 2).map(|a| a.to_owned()), Some("-Kapat".into()), "betik -Kapat kipinde çağrılmıyor (AÇARDI)");
        assert!(args.windows(2).any(|w| w[0] == "-WindowStyle" && w[1] == "Hidden"), "kapatma gizli değil");
        let metin = fs::read_to_string(&gunluk).expect("başlatma hatası günlüğe YAZILMADI");
        assert!(metin.contains("hotspot_kapatilamadi") && metin.contains("sahte-baslatici: powershell yok"), "{metin:?}");
    }
}

// ==== KP2-C TESTLERI BASLANGIC (yalniz test; urun satirlari kaymaz) ====
/// KP-2 · launcher/core/src/flow.rs · sözleşmeler: önbellekten (AĞSIZ) katmansız kurulum + parçalı profil · yarım base açılımı
/// silinir · onarımın kayıt / disk kolları · ön-indirme kuruluma dokunmaz · katmansız / katmanlı güncelleme + atomik takas +
/// geri alma · yarım takas kurtarma kolları · deneme sayacı · profil kaldırma kenar kolları.
/// AĞ YOK: paket URL'leri pinlenmemiş `example.invalid` — önbellek ıskalarsa indirme host pininde reddedilir (gerçek ağa çıkılmaz).
#[allow(non_snake_case)]
#[cfg(test)]
mod kp2_testleri {
    use super::*;
    use sha2::{Digest, Sha256};
    use std::io::Write as _;

    const WEB: &str = "PEMF_Backend/_internal/frontend/dist/index.html";

    fn sha_hex(b: &[u8]) -> String {
        let mut h = Sha256::new();
        h.update(b);
        format!("{:x}", h.finalize())
    }

    /// Bellekte zip üret; sonu `/` olan ad DİZİN girdisidir.
    fn zip_bayt(girdiler: &[(&str, &[u8])]) -> Vec<u8> {
        let mut z = zip::ZipWriter::new(std::io::Cursor::new(Vec::new()));
        let o: zip::write::SimpleFileOptions =
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Stored);
        for (ad, icerik) in girdiler {
            if ad.ends_with('/') {
                z.add_directory(*ad, o).unwrap();
            } else {
                z.start_file(*ad, o).unwrap();
                z.write_all(icerik).unwrap();
            }
        }
        z.finish().unwrap().into_inner()
    }

    fn exe_zipte() -> String {
        format!("PEMF_Backend/{}", crate::platform::backend_exe_name())
    }

    fn base_zip(exe: &[u8]) -> Vec<u8> {
        zip_bayt(&[(&exe_zipte(), exe), (WEB, b"YENI-WEB")])
    }

    struct Pk {
        url: String,
        sha: String,
        boyut: u64,
    }

    impl Pk {
        fn json(&self) -> String {
            format!(r#"{{"url":"{}","sha256":"{}","size":{},"kind":"zip"}}"#, self.url, self.sha, self.boyut)
        }
    }

    /// Paketi önbelleğe koy (dosya adı = URL'nin son parçası). `boyut_yaz=false` → manifest boyutu 0 (önbellek "hazır" SAYILMAZ
    /// ama `ensure_package` sha'yı doğrulayıp yine önbellekten verir).
    fn onbellege(root: &Path, ad: &str, bayt: &[u8], boyut_yaz: bool) -> Pk {
        let c = install::cache_dir(root);
        fs::create_dir_all(&c).unwrap();
        fs::write(c.join(ad), bayt).unwrap();
        Pk { url: format!("https://example.invalid/{ad}"), sha: sha_hex(bayt), boyut: if boyut_yaz { bayt.len() as u64 } else { 0 } }
    }

    fn man(base: Option<&Pk>, katman: Option<(&Pk, &Pk)>, modeller: &[(&str, &Pk)], parcalar: &[(&str, Vec<&Pk>)]) -> String {
        let plat = crate::platform::current();
        let mut s = String::from(r#"{"schema":2,"version":"9.9.9""#);
        if let Some(b) = base {
            s += &format!(r#","runtimes":{{"{plat}":{}}}"#, b.json());
        }
        if let Some((d, a)) = katman {
            s += &format!(r#","layers":{{"{plat}":{{"deps":{},"app":{}}}}}"#, d.json(), a.json());
        }
        let m: Vec<String> = modeller.iter().map(|(n, p)| format!(r#""{n}":{}"#, p.json())).collect();
        let pr: Vec<String> = parcalar
            .iter()
            .map(|(n, v)| format!(r#""{n}":[{}]"#, v.iter().map(|p| p.json()).collect::<Vec<_>>().join(",")))
            .collect();
        s += &format!(r#","models":{{{}}},"model_parts":{{{}}}}}"#, m.join(","), pr.join(","));
        s
    }

    /// Yapısal olarak SAĞLAM kurulu cihaz (exe + `_internal/frontend/dist/index.html`).
    fn kurulu(root: &Path, exe: &[u8]) {
        let k = install::runtime_dir(root).join("PEMF_Backend");
        fs::create_dir_all(k.join("_internal").join("frontend").join("dist")).unwrap();
        fs::write(install::backend_path(root), exe).unwrap();
        fs::write(k.join("_internal").join("frontend").join("dist").join("index.html"), b"ESKI-WEB").unwrap();
    }

    fn devam() -> net::Control {
        net::Control::Continue
    }

    fn exe_icerigi(rt: &Path) -> Vec<u8> {
        fs::read(rt.join("PEMF_Backend").join(crate::platform::backend_exe_name())).unwrap()
    }

    /// Katmansız manifest + paketler önbellekte → kurulum AĞA ÇIKMADAN: eski runtime artığı silinir, base açılır ve sha'sı
    /// kaydedilir; parçalı profilin TÜM zip'leri açılır, birleşik sha yazılır, profil "kurulu" işaretlenir.
    #[test]
    fn kp2_katmansiz_kurulum_onbellekten_eski_artigi_siler_base_ve_parcali_profili_acar_kaydeder() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        let artik = install::runtime_dir(&root).join("ESKI_SURUM.dll");
        fs::create_dir_all(artik.parent().unwrap()).unwrap();
        fs::write(&artik, b"bayat").unwrap();
        let base = onbellege(&root, "base.zip", &base_zip(b"YENI-EXE"), true);
        let vet = onbellege(&root, "vet.zip", &zip_bayt(&[("ai_models/ai_hub/em_kedi/a.onnx", b"A")]), true);
        let vet2 = onbellege(&root, "vet-2.zip", &zip_bayt(&[("ai_models/ai_hub/em_kedi/b.onnx", b"BB")]), true);
        let m = man(Some(&base), None, &[("vet", &vet)], &[("vet", vec![&vet2])]);

        let mut olaylar = Vec::new();
        install_profiles(&m, &["vet".to_string()], &root, &mut |p| olaylar.push(p), &devam).unwrap();

        assert_eq!(fs::read(install::backend_path(&root)).unwrap(), b"YENI-EXE");
        assert!(!artik.exists(), "eski sürümün artığı yeni kurulumda yaşıyor (iki sürümün birleşimi)");
        let kayit = install::read_installed_packages(&root);
        assert_eq!(kayit.base, base.sha, "base açıldı ama kimliği kaydedilmedi");
        assert_eq!(kayit.models.get("vet"), Some(&format!("{}+{}", vet.sha, vet2.sha)), "parçalı profilin birleşik kimliği");
        assert_eq!(install::read_installed_profiles(&root), vec!["vet".to_string()]);
        assert_eq!(fs::read(root.join("ai_models/ai_hub/em_kedi/b.onnx")).unwrap(), b"BB", "ikinci parça açılmadı");
        assert_eq!(
            olaylar,
            vec![
                Progress::ManifestFetched { version: "9.9.9".into(), schema: 2 },
                Progress::Cached { what: "base".into() },
                Progress::Extracting { what: crate::dil::t("rust.kurulum.eskiSurumTemizleniyor") },
                Progress::Extracting { what: "base".into() },
                Progress::Cached { what: "vet".into() },
                Progress::Cached { what: "vet-p2".into() },
                Progress::Extracting { what: "vet".into() },
            ]
        );
    }

    /// Base açılımı YARIDA düşerse (exe yazıldıktan sonra hostile girdi) `runtime/` SİLİNİR ve base sha YAZILMAZ —
    /// yarım ağaç "kurulu" görünmez.
    #[test]
    fn kp2_katmansiz_base_acilimi_YARIDA_duserse_runtime_SILINIR_sha_YAZILMAZ() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        let base = onbellege(&root, "base.zip", &zip_bayt(&[(&exe_zipte(), b"EXE"), ("PEMF_Backend/CON.txt", b"aygit")]), true);
        let m = man(Some(&base), None, &[], &[]);
        let r = install_profiles(&m, &[], &root, &mut |_| {}, &devam);
        assert!(matches!(r, Err(FlowError::Extract(extract::ExtractError::PathEscape(_)))), "{r:?}");
        assert!(!install::runtime_dir(&root).exists(), "yarım açılan base ağacı (exe yazılmış) diskte kaldı");
        assert_eq!(install::read_installed_packages(&root).base, "", "yarım açılım 'kurulu' kaydedildi");
    }

    /// Onar + kayıt OKUNUR (`["vet"]`) → kayıttaki profil önbellekten yeniden açılır (silinmiş model dosyası geri gelir).
    #[test]
    fn kp2_onar_KAYITLI_profili_onbellekten_yeniden_acar() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        fs::create_dir_all(&root).unwrap();
        fs::write(install::installed_profiles_path(&root), r#"["vet"]"#).unwrap();
        let base = onbellege(&root, "base.zip", &base_zip(b"EXE"), true);
        let vet = onbellege(&root, "vet.zip", &zip_bayt(&[("ai_models/ai_hub/em_kedi/a.onnx", b"MODEL")]), true);
        let m = man(Some(&base), None, &[("vet", &vet)], &[]);
        let mut olaylar = Vec::new();
        repair(&m, &root, &mut |p| olaylar.push(p), &devam).unwrap();
        assert_eq!(fs::read(root.join("ai_models/ai_hub/em_kedi/a.onnx")).unwrap(), b"MODEL");
        assert_eq!(install::read_installed_packages(&root).models.get("vet"), Some(&vet.sha));
        assert!(olaylar.contains(&Progress::Extracting { what: "vet".into() }), "kayıttaki profil onarılmadı: {olaylar:?}");
    }

    /// Onar + kayıt YOK ama diskte `ai_models/ai_hub/em_kedi` VAR → profil diskten çıkarılır (vet), kullanıcıya "eski kurulum
    /// algılandı (1)" bildirilir ve profil kurulup kaydedilir.
    #[test]
    fn kp2_onar_kayit_YOKKEN_diskteki_modulden_profili_cikarir_ve_BILDIRIR() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        fs::create_dir_all(root.join("ai_models/ai_hub/em_kedi")).unwrap();
        let base = onbellege(&root, "base.zip", &base_zip(b"EXE"), true);
        let vet = onbellege(&root, "vet.zip", &zip_bayt(&[("ai_models/ai_hub/em_kedi/a.onnx", b"M")]), true);
        let m = man(Some(&base), None, &[("vet", &vet)], &[]);
        let mut olaylar = Vec::new();
        repair(&m, &root, &mut |p| olaylar.push(p), &devam).unwrap();
        assert_eq!(
            olaylar.first(),
            Some(&Progress::Extracting { what: crate::dil::t_ile("rust.kurulum.eskiKurulumAlgilandi", &[("adet", "1")]) })
        );
        assert_eq!(install::read_installed_profiles(&root), vec!["vet".to_string()]);
    }

    /// Ön-indirme: plan bayat + paket boyutu manifestte YOK (önbellek "hazır" sayılmaz) → paketler önbellekten SHA ile doğrulanır
    /// (Cached), ama KURULUMA dokunulmaz: exe, kayıtlar, runtime.new değişmez.
    #[test]
    fn kp2_on_indirme_boyutsuz_paketleri_dogrular_kuruluma_DOKUNMAZ() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"ESKI-EXE");
        install::record_base_sha(&root, &"b".repeat(64));
        install::add_installed_profiles(&root, &["vet".to_string()]);
        install::record_model_sha(&root, "vet", &"c".repeat(64));
        let base = onbellege(&root, "base.zip", &base_zip(b"YENI-EXE"), false);
        let vet = onbellege(&root, "vet.zip", &zip_bayt(&[("ai_models/ai_hub/em_kedi/a.onnx", b"M")]), false);
        let m = man(Some(&base), None, &[("vet", &vet)], &[]);
        let plan = pending_updates(&m, &root).unwrap();
        assert!(plan.base && plan.profiles == vec!["vet".to_string()] && !plan.cached, "ön koşul: {plan:?}");

        let mut olaylar = Vec::new();
        prefetch_updates(&m, &root, &mut |p| olaylar.push(p), &devam).unwrap();
        assert_eq!(olaylar, vec![Progress::Cached { what: "base".into() }, Progress::Cached { what: "vet".into() }]);
        assert_eq!(fs::read(install::backend_path(&root)).unwrap(), b"ESKI-EXE", "ön-indirme kurulumu değiştirdi");
        assert_eq!(install::read_installed_packages(&root).base, "b".repeat(64));
        assert!(!install::runtime_new_dir(&root).exists() && !root.join("ai_models").exists());
    }

    /// Ön-indirme: (a) kurulum GÜNCEL → (b) bayat ama paketler önbellekte HAZIR → hiçbir olay yok (doğrulama / indirme yapılmaz).
    #[test]
    fn kp2_on_indirme_guncelse_ya_da_paketler_HAZIRSA_hicbir_sey_yapmaz() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"EXE");
        let base = onbellege(&root, "base.zip", &base_zip(b"YENI"), true);
        let m = man(Some(&base), None, &[], &[]);
        install::record_base_sha(&root, &base.sha);
        let mut olaylar = Vec::new();
        prefetch_updates(&m, &root, &mut |p| olaylar.push(p), &devam).unwrap();
        install::record_base_sha(&root, &"b".repeat(64));
        assert!(pending_updates(&m, &root).unwrap().cached, "ön koşul: paket önbellekte hazır");
        prefetch_updates(&m, &root, &mut |p| olaylar.push(p), &devam).unwrap();
        assert!(olaylar.is_empty(), "gereksiz ön-indirme: {olaylar:?}");
    }

    /// Katmanlı manifest + katmanlar güncel + yalnız profil bayat (boyutsuz) → ön-indirme YALNIZ profili ister.
    #[test]
    fn kp2_katmanli_on_indirme_yalniz_BAYAT_profili_ister() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"EXE");
        let deps = onbellege(&root, "deps.zip", &zip_bayt(&[("PEMF_Backend/_internal/torch.dll", b"T")]), true);
        let app = onbellege(&root, "app.zip", &base_zip(b"APP"), true);
        install::record_layer_sha(&root, "deps", &deps.sha);
        install::record_layer_sha(&root, "app", &app.sha);
        install::add_installed_profiles(&root, &["vet".to_string()]);
        install::record_model_sha(&root, "vet", &"c".repeat(64));
        let vet = onbellege(&root, "vet.zip", &zip_bayt(&[("ai_models/ai_hub/em_kedi/a.onnx", b"M")]), false);
        let m = man(None, Some((&deps, &app)), &[("vet", &vet)], &[]);
        let mut olaylar = Vec::new();
        prefetch_updates(&m, &root, &mut |p| olaylar.push(p), &devam).unwrap();
        assert_eq!(olaylar, vec![Progress::Cached { what: "vet".into() }]);
    }

    /// Güncelleme gerekmiyorsa `update_installed` hiçbir olay üretmeden BOŞ geri-alma bilgisi döner (sağlık kapısı koşmaz).
    #[test]
    fn kp2_guncelleme_GEREKMIYORSA_bos_geri_alma_bilgisi_doner() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"EXE");
        let base = onbellege(&root, "base.zip", &base_zip(b"EXE"), true);
        install::record_base_sha(&root, &base.sha);
        let m = man(Some(&base), None, &[], &[]);
        let mut olaylar = Vec::new();
        let g = update_installed(&m, &root, &mut |p| olaylar.push(p), &devam).unwrap();
        assert_eq!(g, GeriAlmaBilgisi::default());
        assert!(!g.bir_sey_yapildi() && olaylar.is_empty(), "{olaylar:?}");
    }

    /// Katmansız güncelleme: yeni ağaç `runtime.new`'de (yarım sahne artığı temizlenerek) kurulur, ATOMİK takas edilir
    /// (eski sürüm `runtime.old`'da; önceki artık silinir); kayıt sağlık kapısından ÖNCE yazılmaz, onayda yazılır.
    #[test]
    fn kp2_katmansiz_guncelleme_ayri_agacta_kurar_atomik_takas_eder_onayda_sha_yazar() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"ESKI-EXE");
        install::record_base_sha(&root, &"b".repeat(64));
        fs::create_dir_all(install::runtime_old_dir(&root).join("ARTIK")).unwrap();
        fs::create_dir_all(install::runtime_new_dir(&root).join("YARIM")).unwrap();
        let base = onbellege(&root, "base.zip", &base_zip(b"YENI-EXE"), true);
        let m = man(Some(&base), None, &[], &[]);
        let mut olaylar = Vec::new();
        let g = update_installed(&m, &root, &mut |p| olaylar.push(p), &devam).unwrap();

        assert_eq!(g, GeriAlmaBilgisi { tam_takas: true, base_sha: base.sha.clone(), ..Default::default() });
        assert_eq!(exe_icerigi(&install::runtime_dir(&root)), b"YENI-EXE");
        assert_eq!(exe_icerigi(&install::runtime_old_dir(&root)), b"ESKI-EXE", "geri dönüş yolu (runtime.old) yok");
        assert!(!install::runtime_old_dir(&root).join("ARTIK").exists(), "önceki takasın artığı silinmedi");
        assert!(!install::runtime_dir(&root).join("YARIM").exists(), "yarım sahne artığı yeni sürüme karıştı");
        assert!(olaylar.contains(&Progress::Extracting { what: crate::dil::t("rust.kurulum.eskiSurumTemizleniyor") }));
        assert_eq!(install::read_installed_packages(&root).base, "b".repeat(64), "kayıt sağlık kapısından ÖNCE yazıldı");

        guncellemeyi_onayla(&root, &g);
        assert_eq!(install::read_installed_packages(&root).base, base.sha, "onayda base sha yazılmadı");
        assert!(!install::runtime_old_dir(&root).exists());
    }

    /// Katmansız güncellemede yeni ağaç YAPISAL eksikse (web arayüzü yok) → InvalidData + `yeniKurulumEksik`; sahne silinir,
    /// çalışan kurulum DOKUNULMADAN kalır (takas yapılmaz).
    #[test]
    fn kp2_katmansiz_guncellemede_YAPISAL_eksik_agac_reddedilir_calisan_kurulum_kalir() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"ESKI-EXE");
        install::record_base_sha(&root, &"b".repeat(64));
        let base = onbellege(&root, "base.zip", &zip_bayt(&[(&exe_zipte(), b"YENI")]), true);
        let m = man(Some(&base), None, &[], &[]);
        let e = update_installed(&m, &root, &mut |_| {}, &devam).unwrap_err();
        let beklenen = crate::dil::t("rust.kurulum.yeniKurulumEksik");
        assert!(
            matches!(&e, FlowError::Io(io) if io.kind() == std::io::ErrorKind::InvalidData && io.to_string() == beklenen),
            "{e:?}"
        );
        assert_eq!(exe_icerigi(&install::runtime_dir(&root)), b"ESKI-EXE");
        assert!(!install::runtime_new_dir(&root).exists() && !install::runtime_old_dir(&root).exists());
    }

    /// Katmanlı (deps+app) güncellemede APP açılımı düşerse → `runtime.new` silinir, çalışan kurulum ve kayıtlar aynen kalır.
    #[test]
    fn kp2_katmanli_guncellemede_app_acilimi_duserse_YENI_agac_silinir_calisan_kalir() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"ESKI-EXE");
        install::record_layer_sha(&root, "deps", &"d".repeat(64));
        install::record_layer_sha(&root, "app", &"e".repeat(64));
        let deps = onbellege(&root, "deps.zip", &zip_bayt(&[("PEMF_Backend/_internal/torch.dll", b"T")]), true);
        let app = onbellege(&root, "app.zip", &zip_bayt(&[(&exe_zipte(), b"YENI"), ("PEMF_Backend/CON.txt", b"x")]), true);
        let m = man(None, Some((&deps, &app)), &[], &[]);
        let e = update_installed(&m, &root, &mut |_| {}, &devam).unwrap_err();
        assert!(matches!(e, FlowError::Extract(extract::ExtractError::PathEscape(_))), "{e:?}");
        assert!(!install::runtime_new_dir(&root).exists(), "yarım yeni ağaç kaldı");
        assert_eq!(exe_icerigi(&install::runtime_dir(&root)), b"ESKI-EXE");
        assert_eq!(install::read_installed_packages(&root).deps, "d".repeat(64));
    }

    /// Katmanlı manifest + katmanlar güncel + yalnız profil bayat → katmanlara dokunulmaz (geri-alma bilgisi BOŞ),
    /// profil yenilenir ve gerçek sha yazılır.
    #[test]
    fn kp2_katmanli_yalniz_profil_bayatsa_katmanlara_DOKUNMAZ_profili_yeniler() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"EXE");
        let deps = onbellege(&root, "deps.zip", &zip_bayt(&[("PEMF_Backend/_internal/torch.dll", b"T")]), true);
        let app = onbellege(&root, "app.zip", &base_zip(b"APP"), true);
        install::record_layer_sha(&root, "deps", &deps.sha);
        install::record_layer_sha(&root, "app", &app.sha);
        install::add_installed_profiles(&root, &["vet".to_string()]);
        install::record_model_sha(&root, "vet", &"c".repeat(64));
        let vet = onbellege(&root, "vet.zip", &zip_bayt(&[("ai_models/ai_hub/em_kedi/a.onnx", b"YENI-MODEL")]), true);
        let m = man(None, Some((&deps, &app)), &[("vet", &vet)], &[]);
        let mut olaylar = Vec::new();
        let g = update_installed(&m, &root, &mut |p| olaylar.push(p), &devam).unwrap();
        assert_eq!(g, GeriAlmaBilgisi::default(), "katmanlara dokunulmadığı hâlde geri-alma sözü verildi");
        assert_eq!(install::read_installed_packages(&root).models.get("vet"), Some(&vet.sha));
        assert_eq!(fs::read(root.join("ai_models/ai_hub/em_kedi/a.onnx")).unwrap(), b"YENI-MODEL");
        assert_eq!(exe_icerigi(&install::runtime_dir(&root)), b"EXE");
        assert_eq!(
            olaylar,
            vec![
                Progress::ManifestFetched { version: "9.9.9".into(), schema: 2 },
                Progress::Cached { what: "vet".into() },
                Progress::Extracting { what: "vet".into() },
            ]
        );
    }

    /// Takas YAPILDIKTAN sonra profil yenilemesi düşerse → eski runtime GERİ konur (runtime.old / runtime.bozuk kalmaz) ve
    /// özgün açılım hatası döner; profilin sha kaydı boş kalır (yarım model "güncel" sayılmaz).
    #[test]
    fn kp2_profil_yenilemesi_TAKASTAN_SONRA_duserse_eski_runtime_GERI_konur_ozgun_hata_doner() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"ESKI-EXE");
        install::record_base_sha(&root, &"b".repeat(64));
        install::add_installed_profiles(&root, &["vet".to_string()]);
        install::record_model_sha(&root, "vet", &"c".repeat(64));
        let base = onbellege(&root, "base.zip", &base_zip(b"YENI-EXE"), true);
        let vet = onbellege(&root, "vet.zip", b"ZIP-DEGIL", true);
        let m = man(Some(&base), None, &[("vet", &vet)], &[]);
        let e = update_installed(&m, &root, &mut |_| {}, &devam).unwrap_err();
        assert!(matches!(e, FlowError::Extract(extract::ExtractError::Zip(_))), "özgün hata yerine: {e:?}");
        assert_eq!(exe_icerigi(&install::runtime_dir(&root)), b"ESKI-EXE", "doğrulanmamış sürüm canlıda kaldı");
        assert!(!install::runtime_old_dir(&root).exists() && !root.join("runtime.bozuk").exists());
        assert_eq!(install::read_installed_packages(&root).models.get("vet"), Some(&String::new()));
    }

    /// App katmanı açılımı düşer: (a) kök listesi VAR → eski app yedekten GERİ konur, yedek silinir, açılım hatası döner;
    /// (b) kök listesi YOK → yedek alınmamıştır, hiçbir şey taşınmaz, açılım hatası döner.
    #[test]
    fn kp2_app_katmani_acilimi_duserse_yedekliyse_GERI_koyar_yedeksizse_dokunmaz() {
        for kok_listesi in [true, false] {
            let d = tempfile::tempdir().unwrap();
            let root = d.path().join("kok");
            kurulu(&root, b"ESKI-EXE");
            if kok_listesi {
                fs::write(install::app_roots_path(&root), br#"{"roots":["PEMF_Backend/_internal/frontend/dist"]}"#).unwrap();
            }
            let zip_yolu = d.path().join("app.zip");
            fs::write(&zip_yolu, b"ZIP-DEGIL").unwrap();
            let mut butce = 0u64;
            let r = app_katmanini_degistir(&zip_yolu, &root, &mut butce, &mut |_| {}, &devam);
            assert!(matches!(r, Err(FlowError::Extract(extract::ExtractError::Zip(_)))), "{kok_listesi}: {r:?}");
            let web = install::runtime_dir(&root).join(WEB);
            assert_eq!(fs::read(&web).unwrap(), b"ESKI-WEB", "{kok_listesi}: eski app geri konmadı");
            assert!(!install::app_backup_dir(&root).exists(), "{kok_listesi}: yedek dizini kaldı");
        }
    }

    /// Atomik takas: (a) yeni ağaç YOKSA eski sürüm GERİ konur ve hata döner; (b) canlı runtime YOKSA yeni ağaç doğrudan yerleşir.
    #[test]
    fn kp2_atomik_takas_yeni_agac_yoksa_eskiyi_GERI_koyar_runtime_yoksa_dogrudan_yerlesir() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"ESKI-EXE");
        let r = atomik_takas(&root);
        assert!(matches!(&r, Err(FlowError::Io(io)) if io.kind() == std::io::ErrorKind::NotFound), "{r:?}");
        assert_eq!(exe_icerigi(&install::runtime_dir(&root)), b"ESKI-EXE", "takas düşünce ortada runtime kalmadı");
        assert!(!install::runtime_old_dir(&root).exists());

        let root2 = d.path().join("kok2");
        let yeni = install::runtime_new_dir(&root2).join("PEMF_Backend");
        fs::create_dir_all(&yeni).unwrap();
        fs::write(yeni.join(crate::platform::backend_exe_name()), b"YENI").unwrap();
        atomik_takas(&root2).unwrap();
        assert_eq!(exe_icerigi(&install::runtime_dir(&root2)), b"YENI");
        assert!(!install::runtime_old_dir(&root2).exists() && !install::runtime_new_dir(&root2).exists());
    }

    /// Yarım takas kurtarma: runtime VAR ama yapısal bozuk + (a) yedek YOK → false; (b) yedek var ama kök listesi yok (geri
    /// konacak bir şey yok) → false. İki durumda da ölü sahne (`runtime.new`) temizlenir, canlı runtime silinmez.
    #[test]
    fn kp2_yarim_takas_bozuk_runtime_kurtarilamazsa_false_ve_olu_sahne_temizlenir() {
        for yedek_var in [false, true] {
            let d = tempfile::tempdir().unwrap();
            let root = d.path().join("kok");
            fs::create_dir_all(install::runtime_dir(&root).join("PEMF_Backend")).unwrap();
            fs::write(install::backend_path(&root), b"EXE").unwrap();
            fs::create_dir_all(install::runtime_new_dir(&root).join("x")).unwrap();
            if yedek_var {
                fs::create_dir_all(install::app_backup_dir(&root).join("PEMF_Backend")).unwrap();
            }
            assert!(!yarim_takasi_kurtar(&root), "{yedek_var}: kurtarılamayan kurulum 'kurtarıldı' dendi");
            assert!(!install::runtime_new_dir(&root).exists(), "{yedek_var}: ölü sahne kaldı");
            assert_eq!(fs::read(install::backend_path(&root)).unwrap(), b"EXE");
        }
    }

    /// Tam takas geri alması + `runtime.old` YOK → hiçbir şeye dokunmadan Ok (canlı ağaç olduğu gibi kalır).
    #[test]
    fn kp2_tam_takas_geri_almasi_eski_surum_yoksa_DOKUNMADAN_ok() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"EXE");
        guncellemeyi_geri_al(&root, &GeriAlmaBilgisi { tam_takas: true, ..Default::default() }).unwrap();
        assert_eq!(exe_icerigi(&install::runtime_dir(&root)), b"EXE");
        assert!(!root.join("runtime.bozuk").exists());
    }

    /// Geri alma kaydı: kurulu cihazda her çağrı hedefin ("base:<sha>") sayacını ARTIRIR → sınırda otomatik kurulum durur;
    /// kurulu olmayan kökte hedef yoktur → sayaç YAZILMAZ.
    #[test]
    fn kp2_geri_alma_kaydi_hedef_sayacini_artirir_kurulu_degilse_yazmaz() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"EXE");
        install::record_base_sha(&root, &"b".repeat(64));
        let sha = "f".repeat(64);
        let m = man(Some(&Pk { url: "https://example.invalid/base.zip".into(), sha: sha.clone(), boyut: 5 }), None, &[], &[]);
        geri_almayi_kaydet(&root, &m);
        geri_almayi_kaydet(&root, &m);
        let hedef = format!("base:{sha}");
        assert_eq!(install::read_runtime_attempt(&root), Some((hedef.clone(), 2)));
        assert!(pending_updates(&m, &root).unwrap().otomatik_durduruldu, "deneme sınırı dolduğu hâlde otomatik kurulum sürüyor");

        let bos = d.path().join("bos");
        geri_almayi_kaydet(&bos, &m);
        assert_eq!(install::read_runtime_attempt(&bos), None);
    }

    /// Benimseme: kurulu değilse hiçbir kayıt yazılmaz (`installed_packages.json` oluşmaz).
    #[test]
    fn kp2_benimseme_kurulu_DEGILSE_kayit_yazmaz() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        fs::create_dir_all(&root).unwrap();
        fs::write(install::installed_profiles_path(&root), r#"["vet"]"#).unwrap();
        let m = man(None, None, &[("vet", &Pk { url: "https://example.invalid/vet.zip".into(), sha: "a".repeat(64), boyut: 1 })], &[]);
        adopt_unknown_models(&m, &root).unwrap();
        assert!(!install::installed_packages_path(&root).exists());
    }

    /// Plan: bayat base + bayat profil önbellekte HAZIR, güncel profil plana GİRMEZ → cached=true, bayt toplamı yalnız bayatlar,
    /// hedef kimliği "base:<sha>".
    #[test]
    fn kp2_plan_guncel_profili_dislar_hazir_onbellegi_cached_sayar() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        kurulu(&root, b"EXE");
        install::record_base_sha(&root, &"b".repeat(64));
        install::add_installed_profiles(&root, &["home".to_string(), "vet".to_string()]);
        let home = Pk { url: "https://example.invalid/home.zip".into(), sha: "a".repeat(64), boyut: 7 };
        install::record_model_sha(&root, "home", &home.sha);
        install::record_model_sha(&root, "vet", &"c".repeat(64));
        let base = onbellege(&root, "base.zip", &base_zip(b"YENI"), true);
        let vet = onbellege(&root, "vet.zip", &zip_bayt(&[("ai_models/ai_hub/em_kedi/a.onnx", b"M")]), true);
        let m = man(Some(&base), None, &[("home", &home), ("vet", &vet)], &[]);
        let p = pending_updates(&m, &root).unwrap();
        assert!(p.base && p.cached, "{p:?}");
        assert_eq!(p.profiles, vec!["vet".to_string()], "güncel profil (home) plana girdi");
        assert_eq!(p.bytes, base.boyut + vet.boyut);
        assert_eq!(p.hedef, format!("base:{}", base.sha));
    }

    /// Plan paketleri: katmansız manifest + base BAYAT DEĞİL → base listeye GİRMEZ, yalnız planlı profilin paketleri döner.
    #[test]
    fn kp2_plan_paketleri_base_bayat_degilse_yalniz_profil_paketleri() {
        let pk = |ad: &str| Pk { url: format!("https://example.invalid/{ad}"), sha: "a".repeat(64), boyut: 1 };
        let m = Manifest::parse(&man(Some(&pk("base.zip")), None, &[("vet", &pk("vet.zip"))], &[])).unwrap();
        let plan = UpdatePlan { profiles: vec!["vet".to_string()], ..Default::default() };
        let etiketler: Vec<String> = plan_paketleri(&m, &plan).into_iter().map(|(_, e)| e).collect();
        assert_eq!(etiketler, vec!["vet".to_string()]);
    }

    /// Profil kaldırma: boş liste → profilSecilmedi; kalan profil manifestte YOK → profilManifestteYok (hiçbir dosya silinmez).
    #[test]
    fn kp2_profil_kaldirma_bos_liste_ve_kalan_profil_manifestte_yoksa_REDDEDER() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        let vet = onbellege(&root, "vet.zip", &zip_bayt(&[("ai_models/ai_hub/em_kedi/a.onnx", b"A")]), true);
        let m = Manifest::parse(&man(None, None, &[("vet", &vet)], &[])).unwrap();
        install::add_installed_profiles(&root, &["home".to_string(), "vet".to_string()]);
        let e = remove_profiles(&root, &m, &[], &mut |_| {}).unwrap_err();
        assert!(matches!(&e, FlowError::ProfilKaldirma(s) if *s == crate::dil::t("rust.kurulum.profilSecilmedi")), "{e:?}");
        let e = remove_profiles(&root, &m, &["vet".to_string()], &mut |_| {}).unwrap_err();
        let beklenen = crate::dil::t_ile("rust.kurulum.profilManifestteYok", &[("ad", "home")]);
        assert!(matches!(&e, FlowError::ProfilKaldirma(s) if *s == beklenen), "{e:?}");
        assert!(install::cache_dir(&root).join("vet.zip").exists());
    }

    /// Profil kaldırma kenarları: dizin girdileri (`ai_models/`, `…/`) ve `./` parçaları normalize edilir; parça aynı zip'i
    /// tekrar listeler (tekrar sayılmaz); diskte olmayan dosya atlanır; zip'te dosya ama diskte DİZİN olan girdiye dokunulmaz;
    /// kalan profilin ortak dosyası KORUNUR; önbellek zip'i silinir (aynı yol ikinci kez "zaten yok" sayılır); kayıtlar güncellenir.
    #[test]
    fn kp2_profil_kaldirma_kenar_girdileri_dogru_isler_ortaklari_korur_rapor_dogru() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path().join("kok");
        let home = onbellege(&root, "home.zip", &zip_bayt(&[("ai_models/ai_hub/ortak/s.onnx", b"S")]), true);
        let vet_bayt = zip_bayt(&[
            ("ai_models/", b""),
            ("ai_models/ai_hub/", b""),
            ("ai_models/./ai_hub/em_kedi/a.onnx", b"AAA"),
            ("ai_models/ai_hub/ortak/s.onnx", b"S"),
            ("ai_models/ai_hub/em_kedi/yok.onnx", b"Y"),
            ("ai_models/ai_hub/em_kedi/klasor", b"K"),
        ]);
        let vet = onbellege(&root, "vet.zip", &vet_bayt, true);
        let m = Manifest::parse(&man(None, None, &[("home", &home), ("vet", &vet)], &[("vet", vec![&vet])])).unwrap();
        let mk = install::models_dir(&root).join("ai_hub");
        fs::create_dir_all(mk.join("em_kedi").join("klasor")).unwrap();
        fs::create_dir_all(mk.join("ortak")).unwrap();
        fs::write(mk.join("em_kedi").join("a.onnx"), b"AAA").unwrap();
        fs::write(mk.join("ortak").join("s.onnx"), b"S").unwrap();
        install::add_installed_profiles(&root, &["home".to_string(), "vet".to_string()]);
        install::record_model_sha(&root, "vet", &vet.sha);

        let r = remove_profiles(&root, &m, &["vet".to_string()], &mut |_| {}).unwrap();
        assert_eq!(
            r,
            RemoveReport {
                removed: vec!["vet".to_string()],
                installed: vec!["home".to_string()],
                freed_bytes: 3 + vet_bayt.len() as u64,
                kept_shared: 1,
            }
        );
        assert!(!mk.join("em_kedi").join("a.onnx").exists());
        assert!(mk.join("ortak").join("s.onnx").exists(), "kalan profilin ortak dosyası silindi");
        assert!(mk.join("em_kedi").join("klasor").is_dir(), "diskteki dizine dokunuldu");
        assert!(!install::cache_dir(&root).join("vet.zip").exists() && install::cache_dir(&root).join("home.zip").exists());
        assert_eq!(install::read_installed_packages(&root).models.get("vet"), None);
    }

    /// Zip listesi okunamazsa (dosya yok) → ProfilKaldirma `onbellekOkunamadi` (profil + dosya adı + işletim sistemi hatası).
    #[test]
    fn kp2_zip_listesi_dosya_yoksa_eyleme_donuk_hata() {
        let d = tempfile::tempdir().unwrap();
        let yol = d.path().join("yok.zip");
        let os = fs::File::open(&yol).unwrap_err().to_string();
        let e = zip_dosya_listesi(&yol, "vet").unwrap_err();
        let beklenen = crate::dil::t_ile("rust.kurulum.onbellekOkunamadi", &[("profil", "vet"), ("dosya", "yok.zip"), ("hata", &os)]);
        assert!(matches!(&e, FlowError::ProfilKaldirma(s) if *s == beklenen), "{e:?}");
    }

    // ── KP-4 A2 (Y257 a) SABİTLEYEN kapı — `ensure_package` yeniden deneme / telafi SIRASI (yeniden düzenlemeden ÖNCE yazıldı) ─
    // İndiricinin enjeksiyonu yalnız G/Ç'yi ayırır: önbellek doğrulaması, 6 deneme, yalnız GEÇİCİ hatada yeniden deneme, artan
    // bekleme boyunca Duraklat / İptal'e anında yanıt, sha uyuşmazlığında `.part` SİLİNEREK tek temiz yeniden indirme AYNEN kalmalı.
    #[test]
    fn KRITIK_KP4_A2_SABIT_ensure_package_yeniden_deneme_SIRASI() {
        let kaynak = crate::test_kaynak::yorumsuz(include_str!("flow.rs"));
        crate::test_kaynak::sira_dogru(
            &kaynak,
            &[
                "let dest = cache_path_for(pkg, cache, label);",
                "if dest.exists() && verify::verify_file(&dest, &pkg.sha256).is_ok() {",
                "const MAX_ATTEMPTS: u32 = 6;",
                "(&pkg.url, &dest, pkg.size, &pkg.sha256, &mut cb, control)",
                "let retriable = is_retriable(&e);",
                "if !retriable || attempt >= MAX_ATTEMPTS {",
                "Progress::Reconnecting { what: label.to_string(), attempt, max: MAX_ATTEMPTS }",
                "let wait_ms = (attempt.min(5) as u64) * 1500;",
                "net::Control::Cancel => return Err(net::NetError::Cancelled.into()),",
                "net::Control::Pause => return Err(net::NetError::Paused.into()),",
                "waited += 200;",
                "let _ = fs::remove_file(net::part_path(&dest, &pkg.sha256));",
                "dogrula_ya_da_bir_kez_temiz_indir(&dest, &pkg.sha256, label, on, control, &mut temiz_yeniden_indir)?;",
            ],
            "ensure_package sırası bozuk",
        );
    }

    // ── KP-4 A2 (Y257 a): `ensure_package_ile` DAVRANIŞI — sahte indirici + sahte bekleme (ağ / gerçek uyku YOK) ─────────────
    use std::cell::{Cell, RefCell};

    const ENS_URL: &str = "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/base.zip";

    struct EnsDurum {
        cagri: Cell<u32>,
        bekleme: RefCell<Vec<u64>>,
        olaylar: RefCell<Vec<String>>,
    }
    impl EnsDurum {
        fn yeni() -> Self {
            EnsDurum { cagri: Cell::new(0), bekleme: RefCell::new(vec![]), olaylar: RefCell::new(vec![]) }
        }
    }
    fn ens_paket(govde: &[u8]) -> crate::Package {
        crate::Package { url: ENS_URL.into(), sha256: sha_hex(govde), size: govde.len() as u64, kind: "zip".into() }
    }
    fn olay_adi(p: &Progress) -> String {
        match p {
            Progress::Downloading { done, total, .. } => format!("indir {done}/{total}"),
            Progress::Reconnecting { attempt, max, .. } => format!("yeniden {attempt}/{max}"),
            diger => format!("{diger:?}").split([' ', '{']).next().unwrap_or_default().to_lowercase(),
        }
    }

    /// `davranis(cagri_no, hedef)` her indirme çağrısında ne olacağını söyler (dosyayı yazar ya da hata döner).
    fn ens_kos(
        pkg: &crate::Package,
        cache: &Path,
        durum: &EnsDurum,
        kontrol: &dyn Fn() -> net::Control,
        davranis: &dyn Fn(u32, &Path) -> Result<u64, net::NetError>,
    ) -> Result<PathBuf, FlowError> {
        let indir = |url: &str, dest: &Path, boyut: u64, sha: &str, ilerle: net::ProgressFn<'_>, _k: &dyn Fn() -> net::Control| {
            assert_eq!((url, boyut, sha), (pkg.url.as_str(), pkg.size, pkg.sha256.as_str()), "indiriciye yanlış paket");
            durum.cagri.set(durum.cagri.get() + 1);
            ilerle(1, boyut);
            davranis(durum.cagri.get(), dest)
        };
        let uyu = |ms: u64| durum.bekleme.borrow_mut().push(ms);
        let mut on = |p: Progress| durum.olaylar.borrow_mut().push(olay_adi(&p));
        ensure_package_ile(pkg, cache, "base", &mut on, kontrol, &indir, &uyu)
    }
    fn surdur() -> net::Control {
        net::Control::Continue
    }
    fn kopma() -> net::NetError {
        net::NetError::Transport("connection reset".into())
    }

    #[test]
    fn KRITIK_KP4_A2_ensure_GECICI_hatada_KALDIGI_YERDEN_yeniden_dener_artan_bekleme() {
        let d = tempfile::tempdir().unwrap();
        let govde = b"BASE-ZIP".to_vec();
        let pkg = ens_paket(&govde);
        let durum = EnsDurum::yeni();
        let r = ens_kos(&pkg, d.path(), &durum, &surdur, &|n, dest| {
            if n < 3 {
                Err(kopma())
            } else {
                std::fs::write(dest, &govde).unwrap();
                Ok(govde.len() as u64)
            }
        });
        let yol = r.unwrap();
        assert_eq!(std::fs::read(&yol).unwrap(), govde);
        assert_eq!(durum.cagri.get(), 3);
        // 1. bekleme 1500 ms (200'lük dilimlerle 8 kez), 2. bekleme 3000 ms (15 kez) — her dilimde Duraklat / İptal yoklanır
        assert_eq!(durum.bekleme.borrow().len(), 8 + 15, "artan bekleme (1,5 sn → 3 sn) değişti");
        assert!(durum.bekleme.borrow().iter().all(|ms| *ms == 200));
        let o = durum.olaylar.borrow();
        assert!(o.contains(&"yeniden 1/6".to_string()) && o.contains(&"yeniden 2/6".to_string()), "{o:?}");
        assert_eq!(o.last().map(String::as_str), Some("verifying"));
    }

    #[test]
    fn KRITIK_KP4_A2_ensure_ALTI_denemeden_sonra_ve_KALICI_hatada_hemen_vazgecer() {
        let d = tempfile::tempdir().unwrap();
        let pkg = ens_paket(b"x");
        let durum = EnsDurum::yeni();
        let r = ens_kos(&pkg, d.path(), &durum, &surdur, &|_, _| Err(kopma()));
        assert!(matches!(r, Err(FlowError::Net(net::NetError::Transport(_)))), "{r:?}");
        assert_eq!(durum.cagri.get(), 6, "geçici hatada deneme sayısı 6 değil");
        let durum = EnsDurum::yeni();
        let r = ens_kos(&pkg, d.path(), &durum, &surdur, &|_, _| Err(net::NetError::HttpStatus { status: 404, url: ENS_URL.into() }));
        assert!(matches!(r, Err(FlowError::Net(net::NetError::HttpStatus { status: 404, .. }))));
        assert_eq!(durum.cagri.get(), 1, "kalıcı (404) hata yeniden denendi");
        assert!(durum.bekleme.borrow().is_empty());
    }

    #[test]
    fn KRITIK_KP4_A2_ensure_bekleme_SIRASINDA_duraklat_ve_iptal_HEMEN_doner() {
        let d = tempfile::tempdir().unwrap();
        let pkg = ens_paket(b"x");
        for (istenen, beklenen_duraklat) in [(net::Control::Pause, true), (net::Control::Cancel, false)] {
            let durum = EnsDurum::yeni();
            let yoklama = Cell::new(0);
            let kontrol = || {
                yoklama.set(yoklama.get() + 1);
                if yoklama.get() > 2 { istenen } else { net::Control::Continue }
            };
            let r = ens_kos(&pkg, d.path(), &durum, &kontrol, &|_, _| Err(kopma()));
            if beklenen_duraklat {
                assert!(matches!(r, Err(FlowError::Net(net::NetError::Paused))), "{r:?}");
            } else {
                assert!(matches!(r, Err(FlowError::Net(net::NetError::Cancelled))), "{r:?}");
            }
            assert_eq!(durum.cagri.get(), 1, "bekleme sırasında gelen karara rağmen yeniden indirildi");
            assert_eq!(durum.bekleme.borrow().len(), 2, "karar ilk yoklamada uygulanmadı (asılı kalma)");
        }
    }

    #[test]
    fn KRITIK_KP4_A2_ensure_sha_UYUSMAZSA_part_SILINIP_TEK_temiz_indirme() {
        let d = tempfile::tempdir().unwrap();
        let govde = b"DOGRU-ICERIK".to_vec();
        let pkg = ens_paket(&govde);
        let durum = EnsDurum::yeni();
        let part = net::part_path(&cache_path_for(&pkg, d.path(), "base"), &pkg.sha256);
        let r = ens_kos(&pkg, d.path(), &durum, &surdur, &|n, dest| {
            if n == 1 {
                std::fs::write(dest, b"BOZUK").unwrap();
                std::fs::write(&part, b"bozuk-devam").unwrap(); // yarım baytlar Range ile yeniden eklenmesin
            } else {
                assert!(!part.exists(), "temiz yeniden indirmeden önce .part SİLİNMEDİ (yine bozuk baytlara eklenir)");
                std::fs::write(dest, &govde).unwrap();
            }
            Ok(0)
        });
        assert_eq!(std::fs::read(r.unwrap()).unwrap(), govde);
        assert_eq!(durum.cagri.get(), 2, "sha uyuşmazlığında TEK telafi bekleniyordu");
        // ikinci kez de tutmazsa hata gerçektir: yukarı çıkar, bozuk dosya bırakılmaz
        let d2 = tempfile::tempdir().unwrap();
        let durum = EnsDurum::yeni();
        let r = ens_kos(&pkg, d2.path(), &durum, &surdur, &|_, dest| {
            std::fs::write(dest, b"HEP-BOZUK").unwrap();
            Ok(0)
        });
        assert!(r.is_err() && durum.cagri.get() == 2);
        assert!(!cache_path_for(&pkg, d2.path(), "base").exists(), "bozuk dosya önbellekte kaldı");
    }

    #[test]
    fn KRITIK_KP4_A2_ensure_ONBELLEKTE_dogrulanan_paket_INDIRILMEZ() {
        let d = tempfile::tempdir().unwrap();
        let govde = b"ONBELLEK".to_vec();
        let pkg = ens_paket(&govde);
        std::fs::write(cache_path_for(&pkg, d.path(), "base"), &govde).unwrap();
        let durum = EnsDurum::yeni();
        let r = ens_kos(&pkg, d.path(), &durum, &surdur, &|_, _| Ok(0));
        assert!(r.is_ok());
        assert_eq!(durum.cagri.get(), 0, "önbellekteki doğru paket yeniden indirildi");
        assert_eq!(*durum.olaylar.borrow(), vec!["cached".to_string()]);
    }

    /// Üretim sarmalayıcısı gerçek indiriciyi bağlar: pinli olmayan paket URL'si ağa ÇIKMADAN reddedilir (kalıcı → tek deneme).
    #[test]
    fn KRITIK_KP4_A2_ensure_uretim_sarmalayicisi_pinsiz_URLde_aga_CIKMAZ() {
        let d = tempfile::tempdir().unwrap();
        let pkg = crate::Package { url: "https://evil.example.com/base.zip".into(), sha256: "0".repeat(64), size: 1, kind: "zip".into() };
        let r = ensure_package(&pkg, d.path(), "base", &mut |_| {}, &|| net::Control::Continue);
        assert!(matches!(r, Err(FlowError::Net(net::NetError::HostNotAllowed(_)))), "{r:?}");
    }
}
