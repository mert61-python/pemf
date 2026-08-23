// Author: mertaygn, cglrgrkn
//! ZIP açma — zip-slip korumalı.
//!
//! Paketler uzaktan iner; arşiv girdisinin adı `../../` içerirse naif bir açıcı
//! kurulum kökünün DIŞINA yazar (zip-slip). Bu, uzaktan kod çalıştırmaya kadar
//! gidebilen klasik bir zafiyettir. Burada her girdinin hedefi kökün altında
//! kalmak ZORUNDA; değilse açma durur.

use std::fs;
use std::io::{self, Read};
use std::path::{Component, Path, PathBuf};

#[derive(Debug, thiserror::Error)]
pub enum ExtractError {
    #[error("dosya sistemi hatası: {0}")]
    Io(#[from] io::Error),
    #[error("zip okunamadı: {0}")]
    Zip(#[from] zip::result::ZipError),
    #[error("GÜVENLİK: arşiv girdisi kurulum dizininin dışına yazmaya çalıştı: {0:?}")]
    PathEscape(String),
    #[error("GÜVENLİK: arşiv kaynak-limitini aştı (zip-bomb?): {0}")]
    ResourceLimit(String),
    /// Kullanıcı açma sırasında İPTAL etti. Yarım açılmış `runtime/` bir sonraki kurulumda
    /// zaten silinir (bkz. `flow::install_profiles`), durum dosyaları güncellenmez.
    #[error("açma iptal edildi")]
    Cancelled,
}

/// Açılan toplam-boyut bütçesi (disk-doldurma/zip-bomb DoS). base~600MB + ai_models~2GB →
/// 8 GB güvenli üst-sınır; meşru paket bunu aşmaz. Girdi-sayısı ve symlink-hedef de sınırlı.
const MAX_TOTAL_UNCOMPRESSED: u64 = 8 * 1024 * 1024 * 1024;
const MAX_ENTRIES: usize = 300_000;
const MAX_SYMLINK_LEN: u64 = 4096;

/// Profil (model) zip'inin EZMESİ YASAK olan üst-düzey girdiler.
///
/// DENETİM 2026-08-04 (#104): profil paketleri `install_root`'a açılır ve yorum onların
/// `ai_models/` önekiyle geldiğini VARSAYAR — ama kod bunu DOĞRULAMAZ. Bir profil zip'indeki
/// `runtime/PEMF_Backend/PEMF_Backend.exe` girdisi zip-slip korumasını tamamen MEŞRU geçer
/// (kök altındadır) ve base.zip'in SHA256 ile DOĞRULANMIŞ backend ikilisini sessizce EZER;
/// açıldıktan sonra o ağacı yeniden doğrulayan hiçbir mekanizma yoktur. `installed_profiles.json`
/// ve `backend.port` da aynı şekilde ezilebilir (E-stop adresi!).
/// Katı bir `ai_models/` ÖNEK ZORUNLULUĞU meşru bir paketi kırabileceğinden, hedefli yasak-liste.
///
/// ⚠️ DENETİM 2026-08-23 (C1): LİSTE ÜÇÜNCÜ KEZ ESKİMİŞTİ. 2026-08-08/09'da eklenen üç durum
/// dosyası ve üç sahneleme dizini hiç işlenmemişti. En ağırı `installed_packages.json`:
/// `pending_updates` "bayat mı güncel mi" kararını TAM ondan okur, yani kök seviyeye manifest
/// sha'larını içeren bir kopya koyan profil zip'i cihazı sonsuza dek "güncel" gösterir —
/// **`min_supported_version` GERİ ÇAĞIRMASI dahil** hiçbir runtime yaması bir daha uygulanmaz
/// (`zorunlu` bayrağı yalnız rollout erken-dönüşünü ezer, sha kıyasını DEĞİL). Bobin-güvenliği
/// düzeltmesi taşıyan bir yayın o cihaza hiç ulaşmaz ve kullanıcıya hiçbir belirti yansımaz.
/// `runtime.old` ise geri dönüş yoludur: ezilirse sağlık kapısı düştüğünde dönülecek sürüm kalmaz.
///
/// Listenin bir daha eskimemesi `tests/test_profil_paketi_kok_dosyalari.py` ile sağlanır: kapı
/// adları değil KAYNAĞI ölçer — `install_root.join("...")` ile üretilen her kök girdisi ya bu
/// listede olmalı ya da açıkça meşru sayılmalı (tek istisna `ai_models`, profillerin hedefi).
const PROFILE_FORBIDDEN_TOP: [&str; 14] = [
    "runtime",
    // Sahneleme/geri-dönüş kardeşleri: `runtime` korunup bunların açıkta kalması korumayı
    // anlamsız kılıyordu — özellikle `runtime.old`, sağlık kapısı düştüğünde dönülecek sürüm.
    "runtime.new",
    "runtime.old",
    "runtime.bozuk",
    // Güncelleme kararının TEK kaynağı (bkz. yukarıdaki not) ve kademeli-yayın dilimi kimliği.
    "installed_packages.json",
    "install_id.txt",
    // Geri alma döngüsü kırıcının sayacı (C2). Ezilirse iki yönde de zarar: sıfırlanırsa döngü
    // geri gelir, şişirilirse GERÇEK bir güncelleme kalıcı olarak bloklanır.
    "runtime_attempt.json",
    // Off-site yedek hedefi — değiştirilirse yedekler başka bir yere yazılır.
    "backup_dir.txt",
    "cache",
    "installed_profiles.json",
    "pending_install.json",
    "backend.port",
    // DENETİM 2026-08-04 (P2): bu denetimde EKLENEN durum dosyası listeye alınmamıştı. Profil
    // zip'i kök seviyeye `selfupdate_attempt.json` koyup `{"version":"<bir sonraki launcher>",
    // "count":99}` yazarsa `selfupdate_auto_allowed` false döner ve launcher'ın SESSİZ
    // oto-güncellemesi o sürüm için KALICI durur (güvenlik yamaları da gelmez).
    "selfupdate_attempt.json",
    // DENETİM 2026-08-06 (P3): "Beni hatırla" oturum blob'u (secret_store.rs) da kurulum KÖKÜNDE
    // duruyor. Zehirli bir manifest'in gösterdiği profil zip'i kök seviyeye `auth_session.bin`
    // koyarsa kullanıcının kayıtlı oturumunu EZER: DPAPI çözümü başarısız olur, `load` None döner
    // ve kullanıcı hiçbir açıklama olmadan giriş ekranına düşer (çevrimdışı klinikte parolayı
    // hatırlamıyorsa kurulu cihaz açılamaz). Jeton ÇALINAMAZ (blob dışarı gitmez), ama bu bir
    // hizmet-engelidir; küme hooks.nsi'deki silme listesiyle EŞ tutulur.
    "auth_session.bin",
];

/// `archive` içeriğini `dest` altına açar. Girdi yolları `dest` dışına çıkamaz.
/// Açılan dosya sayısını döndürür. (Bütçe bu çağrıya özeldir — çok-paketli kurulumda
/// `extract_zip_budgeted` kullanın.)
pub fn extract_zip(archive: &Path, dest: &Path) -> Result<usize, ExtractError> {
    let mut used = 0u64;
    extract_zip_budgeted(archive, dest, &mut used, false)
}

/// Açılım bütçesini ÇAĞRILAR ARASINDA paylaşan sürüm.
///
/// DENETİM 2026-08-04 (#110): `total_bytes` her `extract_zip` çağrısında SIFIRLANIYORDU; oysa
/// `flow::install_profiles` base + 3 profil için 4 AYRI çağrı yapar → belgelenen 8 GB tavanı
/// pratikte 32 GB'dı (sabitin kendi gerekçesi ise "base ~600MB + ai_models ~2GB" diyerek
/// KURULUM BÜTÜNÜ üzerinden akıl yürütüyor). `used` artık çağıran tarafından taşınır.
/// `is_profile = true` → `PROFILE_FORBIDDEN_TOP` uygulanır (bkz. #104).
pub fn extract_zip_budgeted(
    archive: &Path,
    dest: &Path,
    used: &mut u64,
    is_profile: bool,
) -> Result<usize, ExtractError> {
    extract_zip_cancellable(archive, dest, used, is_profile, &|| false)
}

/// İPTAL EDİLEBİLİR açma.
///
/// ⚠️ DENETİM 2026-08-04 (#109): açma tamamen bloklayıcıydı. `ai_models` paketi ~2 GB ve yavaş
/// bir klinik diskinde dakikalar sürebiliyor; bu süre boyunca UI'daki İptal düğmesi ÖLÜYDÜ
/// (`control` yalnız indirmede okunuyordu). Kullanıcı yanlış profili seçtiğini fark etse bile
/// işlemi durduramıyor, pencereyi kapatmak da yarım bir ağaç bırakıyordu. `cancel` her GİRDİDE
/// yoklanır → en fazla bir dosya gecikmeyle durur.
///
/// Yarım kalan ağaç KASITLI olarak geri alınmaz: `flow::install_profiles` base açmadan önce
/// `runtime/`'ı zaten siler ve `installed_profiles.json` güncellenmediği için kurulum "yapılmış"
/// sayılmaz. Geri-alma eklemek, iptal anında ~2 GB silme işlemi demek olurdu.
pub fn extract_zip_cancellable(
    archive: &Path,
    dest: &Path,
    used: &mut u64,
    is_profile: bool,
    cancel: &dyn Fn() -> bool,
) -> Result<usize, ExtractError> {
    let file = fs::File::open(archive)?;
    let mut zip = zip::ZipArchive::new(file)?;
    fs::create_dir_all(dest)?;

    if zip.len() > MAX_ENTRIES {
        return Err(ExtractError::ResourceLimit(format!("çok fazla girdi: {}", zip.len())));
    }

    let mut written = 0usize;
    // #102: yazmadan once hedef dizinin GERCEK konumunu dogrularken ayni dizin icin
    // canonicalize'i tekrarlamamak icin son dogrulanan ebeveyn (girdiler gruplu gelir).
    let mut last_checked_parent: Option<std::path::PathBuf> = None;
    for i in 0..zip.len() {
        if cancel() {
            return Err(ExtractError::Cancelled);
        }
        let mut entry = zip.by_index(i)?;
        // `enclosed_name()` zip-slip'e karşı ilk savunma (mutlak yol / `..` reddeder),
        // ama kendi kontrolümüzü de yapıyoruz: tek savunma hattına güvenme.
        let raw_name = entry.name().to_string();
        let rel = match entry.enclosed_name() {
            Some(p) => p.to_path_buf(),
            None => return Err(ExtractError::PathEscape(raw_name)),
        };
        if !is_safe_relative(&rel) {
            return Err(ExtractError::PathEscape(raw_name));
        }
        // #104: profil paketi, DOĞRULANMIŞ runtime/ ağacını veya launcher durum dosyalarını EZEMEZ.
        if is_profile {
            if let Some(Component::Normal(top)) = rel.components().find(|c| matches!(c, Component::Normal(_))) {
                if let Some(t) = top.to_str() {
                    // ⚠️ DENETİM 2026-08-04 (P1 — BU KORUMANIN KENDİ AÇIĞI): karşılaştırma TAM
                    // EŞLEŞMEYDİ. Windows (NTFS) ve macOS (APFS/HFS+) dosya adlarında HARF
                    // DUYARSIZDIR: `RUNTIME/PEMF_Backend/...` içeren bir profil zip'i bu kontrolü
                    // geçer ama diske TAM OLARAK `runtime/` ağacının üstüne yazar — yani SHA'sı
                    // doğrulanmış backend ikilisi profil paketiyle DEĞİŞTİRİLEBİLİRDİ.
                    // Windows ayrıca ad sonundaki NOKTA ve BOŞLUKLARI atar (`runtime.` → `runtime`),
                    // bu da ikinci bir atlatma yazımıdır. Normalize edip karşılaştırıyoruz.
                    let norm = t.trim_end_matches(['.', ' ']).to_ascii_lowercase();
                    if PROFILE_FORBIDDEN_TOP.iter().any(|f| f.eq_ignore_ascii_case(&norm)) {
                        return Err(ExtractError::PathEscape(format!(
                            "{raw_name} (profil paketi '{t}' altına yazamaz — doğrulanmış runtime/durum dosyası)"
                        )));
                    }
                }
            }
        }

        let out = dest.join(&rel);

        // ⚠️ DENETİM 2026-08-04 (P2 — BU KORUMANIN KENDİ AÇIĞI): aşağıdaki #102 kontrolü
        // ESKİDEN yalnız DÜZ-DOSYA dalındaydı. Dizin girdileri (`is_dir` → `continue`) ve
        // symlink girdileri (`is_symlink` → `continue`) kontrolden ÖNCE dönüyordu, yani
        // korumayı TAMAMEN atlıyorlardı. Somut: kurulum kökünde bir junction varken
        // (`mklink /J` — Windows'ta yönetici gerektirmez) arşivdeki tek bir DİZİN girdisi
        // `link/kacak/` → `create_dir_all` junction'ı İZLER, kökün DIŞINDA dizin oluşur ve
        // fonksiyon hata bile vermez. Kontrol artık girdi tipine bakmadan, HER dal için ve
        // `create_dir_all`'DAN ÖNCE yapılır.
        let hedef_dizin: &Path = if entry.is_dir() {
            out.as_path()
        } else {
            out.parent().unwrap_or(dest)
        };
        if last_checked_parent.as_deref() != Some(hedef_dizin) {
            if !is_within(dest, hedef_dizin) {
                return Err(ExtractError::PathEscape(format!(
                    "{raw_name} (hedef dizin symlink/junction üzerinden kurulum kökünün DIŞINA çözümlendi)"
                )));
            }
            last_checked_parent = Some(hedef_dizin.to_path_buf());
        }
        fs::create_dir_all(hedef_dizin)?;

        if entry.is_dir() {
            continue;
        }

        // SEMBOLİK LİNKLER: macOS base paketinde 96 adet var (ör. `_internal/Python` →
        // `Python.framework/Versions/3.10/Python`). Düz dosya olarak yazılırlarsa içerik
        // hedef yolun METNİ olur ve dlopen "slice is not valid mach-o file" ile ÇÖKER —
        // backend hiç açılmaz. (Bu hata gerçek pakette uçtan uca testle yakalandı.)
        if is_symlink(&entry) {
            // Symlink hedefini SINIRLI oku (aksi halde dev bir girdi read_to_string ile OOM'a
            // sürükleyebilir); gerçek hedefler PATH_MAX (<4KiB) altındadır.
            let mut target = String::new();
            (&mut entry).take(MAX_SYMLINK_LEN).read_to_string(&mut target)?;
            // #110: symlink gövdeleri bütçeye HİÇ sayılmıyordu → MAX_ENTRIES(300k) ×
            // MAX_SYMLINK_LEN(4KiB) ≈ 1.2 GB bütçe-dışı yazım mümkündü.
            *used = used.saturating_add(target.len() as u64);
            if *used > MAX_TOTAL_UNCOMPRESSED {
                return Err(ExtractError::ResourceLimit(
                    "açılım boyut bütçesi aşıldı (symlink)".to_string(),
                ));
            }
            create_symlink(&target, &out, dest, &raw_name)?;
            // Yeni bir symlink, SONRAKİ yolların çözümlenmesini değiştirebilir → önbelleği düşür.
            last_checked_parent = None;
            written += 1;
            continue;
        }
        let mut target = fs::File::create(&out)?;
        // Toplam açılım bütçesi: yalan-başlıklı zip-bomb'a karşı GERÇEK yazılan byte'ı sınırla
        // (kalan bütçe + 1 alıp aşımı yakala). Meşru paket 8GB'ı aşmaz.
        let remaining = MAX_TOTAL_UNCOMPRESSED.saturating_sub(*used);
        let n = io::copy(&mut (&mut entry).take(remaining + 1), &mut target)?;
        *used = used.saturating_add(n);
        if *used > MAX_TOTAL_UNCOMPRESSED {
            drop(target);
            let _ = fs::remove_file(&out);
            return Err(ExtractError::ResourceLimit(
                "açılım boyut bütçesi aşıldı".to_string(),
            ));
        }
        written += 1;

        // Çalıştırma bitini KORU: PEMF_Backend ve yanındaki ikili/kütüphaneler Unix'te +x
        // olmadan başlatılamaz. Ama setuid/setgid/sticky (0o7000) MASKELE — arşiv keyfi bir
        // dosyaya setuid-root veremesin (yerel yetki-yükseltme yüzeyi).
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            if let Some(mode) = entry.unix_mode() {
                // DENETİM 2026-08-04 (#105): eski maske `mode & 0o777` yalnız setuid/setgid/
                // sticky'yi (0o7000) düşürüyordu; GRUP ve DİĞER kullanıcıların YAZMA bitleri
                // (0o022) AYNEN korunuyordu. umask 000 ile üretilmiş bir build makinesinde
                // 0o777 işaretli girdiler herkes-yazılabilir olarak açılır → `PEMF_Backend`
                // ikilisi ve `_internal/*.so` başka bir yerel kullanıcı tarafından DEĞİŞTİRİLİR
                // (bir sonraki çalıştırmada bobin kontrolü devralınır). Çalıştırma biti KORUNUR
                // (backend +x olmadan başlamaz), yalnız grup/diğer YAZMA kaldırılır.
                let safe_mode = (mode & 0o777) & !0o022;
                fs::set_permissions(&out, fs::Permissions::from_mode(safe_mode))?;
            }
        }
    }
    Ok(written)
}

/// Yol yalnız normal bileşenlerden oluşmalı: kök, önek (Windows `C:`), `..` YASAK.
///
/// DENETİM 2026-08-04 (iki düzeltme):
///
/// 1. **`./` YANLIŞ-POZİTİFİ**: Rust `Path::components()` yolun BAŞINDAKİ `.` bileşenini
///    sadeleştirmez, `Component::CurDir` olarak döndürür. `./PEMF_Backend/x` gibi TAMAMEN MEŞRU
///    bir arşiv girdisi (birçok zip aracı bu öneki üretir) "GÜVENLİK: kurulum dizininin dışına
///    yazmaya çalıştı" hatasıyla TÜM kurulumu ilk girdide düşürüyordu. `CurDir` zararsızdır —
///    yolu ileri taşımaz; artık kabul edilir. `..` (`ParentDir`) hâlâ REDDEDİLİR.
///
/// 2. **NTFS ALTERNATE DATA STREAM**: Windows'ta `a.txt:gizli` adı TEK bir `Component::Normal`
///    olarak görünür (sürücü öneki tek harf gerektirdiği için `Prefix` sayılmaz) ve eski kontrolü
///    GEÇİYORDU. `File::create(dest/a.txt:gizli)` `dest/a.txt` dosyasının ALTERNATİF VERİ
///    AKIŞINA yazar: içerik dizin listelemesinde ve boyut hesabında GÖRÜNMEZ, SHA doğrulaması
///    ana akışı okur → arşive gizli yük saklanabilir. Kurulum kökünden ÇIKIŞ yok ama bütünlük
///    ve gizlenebilirlik sorunudur; meşru bir paket ADS içermez → reddet.
fn is_safe_relative(p: &Path) -> bool {
    p.components().all(|c| match c {
        Component::CurDir => true, // `./` zararsız (bkz. not 1)
        Component::Normal(seg) => !segment_is_hostile(seg),
        _ => false, // RootDir / Prefix / ParentDir
    })
}

/// Tek bir yol parçası düşmanca mı? (NTFS ADS ayıracı + Windows rezerve aygıt adları)
fn segment_is_hostile(seg: &std::ffi::OsStr) -> bool {
    let Some(s) = seg.to_str() else {
        return false; // UTF-8 olmayan ad: ayrıca kısıtlamıyoruz (kök altında kalır)
    };
    if s.contains(':') {
        return true; // `dosya:akış` → NTFS ADS
    }
    // `NUL`, `CON`, `COM1`… → `File::create` AYGITA açar, içerik SESSİZCE yutulur ve
    // `written` sayacı yine artar (kurulum "başarılı" görünür, dosya hiç oluşmaz).
    let stem = s.split('.').next().unwrap_or("").to_ascii_uppercase();
    const RESERVED: [&str; 22] = [
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7",
        "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    ];
    RESERVED.contains(&stem.as_str())
}

/// ZIP girdisi sembolik link mi? (unix mode'da S_IFLNK)
fn is_symlink(entry: &zip::read::ZipFile<'_>) -> bool {
    const S_IFMT: u32 = 0o170000;
    const S_IFLNK: u32 = 0o120000;
    entry.unix_mode().is_some_and(|m| m & S_IFMT == S_IFLNK)
}

/// Sembolik linki oluşturur — hedefi kurulum kökünün DIŞINA çıkamaz.
///
/// Symlink'ler zip-slip'in ikinci yüzüdür: `link -> ../../../etc/x` girdisi kendisi
/// kök altında dursa bile, sonradan o link ÜZERİNDEN dışarı yazılabilir. Bu yüzden
/// mutlak hedefler ve kökten çıkan göreli hedefler REDDEDİLİR.
fn create_symlink(
    target: &str,
    link_path: &Path,
    root: &Path,
    raw_name: &str,
) -> Result<(), ExtractError> {
    let target_path = Path::new(target);
    if target_path.is_absolute() {
        return Err(ExtractError::PathEscape(format!(
            "{raw_name} -> {target} (mutlak hedef)"
        )));
    }
    // Linkin bulunduğu dizine göre normalize et; `..` fazlaysa kökten çıkar.
    let base = link_path.parent().unwrap_or(root);
    if !stays_within(root, base, target_path) {
        return Err(ExtractError::PathEscape(format!(
            "{raw_name} -> {target} (kurulum dizini disina cikiyor)"
        )));
    }
    if let Some(parent) = link_path.parent() {
        fs::create_dir_all(parent)?;
    }
    // Yeniden kurulumda kalıntı olabilir.
    let _ = fs::remove_file(link_path);

    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(target_path, link_path)?;
        Ok(())
    }
    // Windows'ta symlink ayrıcalık ister ve Windows base paketinde symlink YOKTUR;
    // sessizce düz dosya yazmaktansa açıkça reddet.
    #[cfg(not(unix))]
    {
        Err(ExtractError::PathEscape(format!(
            "{raw_name}: bu platformda sembolik link desteklenmiyor"
        )))
    }
}

/// `base/target` sadeleştirildiğinde hâlâ `root` altında mı? (dosya sistemine dokunmaz)
fn stays_within(root: &Path, base: &Path, target: &Path) -> bool {
    let mut stack: Vec<Component> = base.components().collect();
    for comp in target.components() {
        match comp {
            Component::ParentDir => {
                if stack.pop().is_none() {
                    return false;
                }
            }
            Component::CurDir => {}
            other => stack.push(other),
        }
    }
    let resolved: PathBuf = stack.iter().collect();
    resolved.starts_with(root)
}

/// Hedefin gerçekten kökün altında kaldığını sembolik link çözümünden SONRA doğrular.
///
/// DENETİM 2026-08-04: bu fonksiyon `canonicalize` başarısız olduğunda `true` (= "kök altında")
/// dönüyordu — bir GÜVENLİK YÜKLEMİ için FAIL-OPEN varsayılan. Dosya yoksa, izin yoksa, Windows'ta
/// kilitliyse veya yol çok uzunsa "güvenli" deniyordu. Artık FAIL-CLOSED.
///
/// Aday HENÜZ YOKSA (yazmadan önce kontrol) en yakın VAR OLAN atası çözümlenir: "buraya yazsam
/// kökün altında kalır mıydım?" sorusunun doğru cevabı budur. Hiçbir ata çözümlenemezse `false`.
pub fn is_within(root: &Path, candidate: &Path) -> bool {
    let Ok(root) = root.canonicalize() else {
        return false; // kök çözümlenemiyorsa hiçbir şey doğrulanamaz → reddet
    };
    let mut probe = candidate;
    loop {
        if let Ok(cand) = probe.canonicalize() {
            return cand.starts_with(&root);
        }
        match probe.parent() {
            Some(p) if p != probe => probe = p,
            _ => return false, // var olan ata bulunamadı → reddet
        }
    }
}


#[cfg(test)]
mod tests {
    use std::io::Write;

    use super::*;

    fn build_zip(entries: &[(&str, &[u8])]) -> (tempfile::TempDir, PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("a.zip");
        let f = fs::File::create(&path).unwrap();
        let mut w = zip::ZipWriter::new(f);
        let opts: zip::write::FileOptions<()> =
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (name, data) in entries {
            w.start_file(*name, opts).unwrap();
            w.write_all(data).unwrap();
        }
        w.finish().unwrap();
        (dir, path)
    }

    #[test]
    fn normal_arsiv_acilir() {
        let (_d, zip_path) = build_zip(&[
            ("PEMF_Backend/PEMF_Backend", b"ELF" as &[u8]),
            ("PEMF_Backend/_internal/x.dat", b"data"),
        ]);
        let out = tempfile::tempdir().unwrap();
        let n = extract_zip(&zip_path, out.path()).unwrap();
        assert_eq!(n, 2);
        assert!(out.path().join("PEMF_Backend/PEMF_Backend").exists());
        assert!(out.path().join("PEMF_Backend/_internal/x.dat").exists());
    }

    /// #109: ~2 GB'lık `ai_models` açılırken UI'daki İptal ÖLÜYDÜ (`control` yalnız indirmede
    /// okunuyordu). Kullanıcı yanlış profili seçtiğini fark etse bile dakikalarca bekliyordu.
    #[test]
    fn acma_iptal_edilebilir() {
        let (_d, zip_path) = build_zip_many(50);
        let out = tempfile::tempdir().unwrap();
        let mut used = 0u64;

        // 5. girdiden sonra iptal et.
        let seen = std::cell::Cell::new(0usize);
        let err = extract_zip_cancellable(&zip_path, out.path(), &mut used, false, &|| {
            seen.set(seen.get() + 1);
            seen.get() > 5
        })
        .unwrap_err();
        assert!(matches!(err, ExtractError::Cancelled), "iptal edilmedi: {err}");
        assert!(seen.get() <= 7, "iptal cok gec fark edildi: {} girdi", seen.get());

        // İptal ETMEYEN çağrı hâlâ tam açmalı (regresyon: cancel her zaman true dönmesin).
        let out2 = tempfile::tempdir().unwrap();
        let mut used2 = 0u64;
        assert_eq!(
            extract_zip_cancellable(&zip_path, out2.path(), &mut used2, false, &|| false).unwrap(),
            50
        );
    }

    /// N adet küçük dosya içeren zip (iptal/bütçe testleri için).
    fn build_zip_many(n: usize) -> (tempfile::TempDir, PathBuf) {
        let d = tempfile::tempdir().unwrap();
        let path = d.path().join("many.zip");
        let f = fs::File::create(&path).unwrap();
        let mut w = zip::ZipWriter::new(f);
        let opts: zip::write::FileOptions<'_, ()> =
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Stored);
        for i in 0..n {
            w.start_file(format!("dir/f{i}.bin"), opts).unwrap();
            std::io::Write::write_all(&mut w, b"x").unwrap();
        }
        w.finish().unwrap();
        (d, path)
    }

    /// ⚠️ P1 (denetim 2026-08-04): #104 korumasi TAM-ESLESME yapiyordu. Windows (NTFS) ve
    /// macOS (APFS) HARF DUYARSIZ oldugu icin `RUNTIME/...` kontrolu gecer ama diske
    /// `runtime/` agacinin UZERINE yazardi — SHA'si dogrulanmis backend ikilisi profil
    /// paketiyle DEGISTIRILEBILIRDI. Windows ayrica sondaki nokta/boslugu atar.
    #[test]
    fn profil_paketi_harf_varyantiyla_runtimei_ezemez() {
        for ad in [
            "RUNTIME/PEMF_Backend/x.dll",
            "Runtime/PEMF_Backend/x.dll",
            "runtime./PEMF_Backend/x.dll",
            "RUNTIME /PEMF_Backend/x.dll",
            "CACHE/base.zip",
            "Installed_Profiles.json",
            "BACKEND.PORT",
        ] {
            let (_d, zip_path) = build_zip_named(ad);
            let out = tempfile::tempdir().unwrap();
            let mut used = 0u64;
            let r = extract_zip_budgeted(&zip_path, out.path(), &mut used, true);
            assert!(
                r.is_err(),
                "profil paketi '{ad}' ile korumayi ATLATTI — dogrulanmis runtime/durum dosyasi ezilir"
            );
        }

        // Mesru profil icerigi etkilenmemeli.
        let (_d, ok_zip) = build_zip_named("ai_models/vet/model.onnx");
        let out = tempfile::tempdir().unwrap();
        let mut used = 0u64;
        assert_eq!(extract_zip_budgeted(&ok_zip, out.path(), &mut used, true).unwrap(), 1);
    }

    /// Tek dosyali zip uretici (ad testleri icin).
    fn build_zip_named(name: &str) -> (tempfile::TempDir, PathBuf) {
        let d = tempfile::tempdir().unwrap();
        let path = d.path().join("t.zip");
        let f = fs::File::create(&path).unwrap();
        let mut w = zip::ZipWriter::new(f);
        let opts: zip::write::FileOptions<'_, ()> =
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Stored);
        w.start_file(name, opts).unwrap();
        std::io::Write::write_all(&mut w, b"x").unwrap();
        w.finish().unwrap();
        (d, path)
    }

    #[test]
    fn zip_slip_reddedilir() {
        let (_d, zip_path) = build_zip(&[("../kotucul.txt", b"pwned" as &[u8])]);
        let out = tempfile::tempdir().unwrap();
        let err = extract_zip(&zip_path, out.path()).unwrap_err();
        assert!(matches!(err, ExtractError::PathEscape(_)));
        // Kurulum kökünün ÜSTÜNE hiçbir şey yazılmamış olmalı.
        assert!(!out.path().parent().unwrap().join("kotucul.txt").exists());
    }

    #[test]
    fn derin_zip_slip_de_reddedilir() {
        let (_d, zip_path) = build_zip(&[("a/b/../../../../etc/pemf_test", b"x" as &[u8])]);
        let out = tempfile::tempdir().unwrap();
        assert!(matches!(
            extract_zip(&zip_path, out.path()).unwrap_err(),
            ExtractError::PathEscape(_)
        ));
    }

    #[test]
    fn is_safe_relative_dogru_ayirir() {
        assert!(is_safe_relative(Path::new("a/b/c.txt")));
        assert!(!is_safe_relative(Path::new("../a")));
        assert!(!is_safe_relative(Path::new("/mutlak/yol")));
    }

    /// DENETİM 2026-08-04: `./` önekli MEŞRU arşiv tüm kurulumu düşürüyordu (yanlış-pozitif).
    #[test]
    fn nokta_egik_onekli_mesru_yol_kabul_edilir() {
        assert!(is_safe_relative(Path::new("./PEMF_Backend/x.dat")));
        assert!(is_safe_relative(Path::new("./a/./b")));
        // Ama `..` HÂLÂ reddedilmeli.
        assert!(!is_safe_relative(Path::new("./../disari")));
    }

    /// DENETİM 2026-08-04: `a.txt:akis` Windows'ta TEK Normal bileşendir ve eski kontrolü
    /// GEÇİYORDU → arşiv, dizin listelemesinde GÖRÜNMEYEN bir alternatif veri akışına yazabilirdi.
    #[test]
    fn ntfs_ads_ve_rezerve_aygit_adlari_reddedilir() {
        assert!(!is_safe_relative(Path::new("a.txt:gizli")));
        assert!(!is_safe_relative(Path::new("PEMF_Backend/x.exe:payload")));
        // Rezerve aygıt adları: File::create AYGITA açar, içerik sessizce yutulur.
        for bad in ["NUL", "CON", "com1", "LPT9", "nul.txt", "PEMF_Backend/CON"] {
            assert!(!is_safe_relative(Path::new(bad)), "rezerve ad kabul edildi: {bad}");
        }
        // Benzeyen ama MEŞRU adlar reddedilmemeli.
        for ok in ["console.js", "CONFIG", "com.dat", "nullable.py", "LPT10"] {
            assert!(is_safe_relative(Path::new(ok)), "mesru ad reddedildi: {ok}");
        }
    }

    #[cfg(unix)]
    fn build_zip_with_symlink(link: &str, target: &str) -> (tempfile::TempDir, PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("s.zip");
        let f = fs::File::create(&path).unwrap();
        let mut w = zip::ZipWriter::new(f);
        // add_symlink GERÇEK symlink girdisi yazar (S_IFLNK). `unix_permissions(0o120777)`
        // yetmez — o yalnız izin bitlerini taşır, dosya TİPİNİ değil.
        let opts: zip::write::SimpleFileOptions = zip::write::FileOptions::default();
        w.add_symlink(link, target, opts).unwrap();
        w.finish().unwrap();
        (dir, path)
    }

    /// GERÇEK PAKET DAVRANIŞI: `_internal/Python` bir symlink. Düz dosya olarak
    /// yazılırsa dlopen "slice is not valid mach-o file" der ve backend HİÇ açılmaz.
    #[cfg(unix)]
    #[test]
    fn sembolik_link_link_olarak_acilir() {
        let (_d, zip_path) =
            build_zip_with_symlink("PEMF_Backend/_internal/Python", "Python.framework/Versions/3.10/Python");
        let out = tempfile::tempdir().unwrap();
        extract_zip(&zip_path, out.path()).unwrap();

        let link = out.path().join("PEMF_Backend/_internal/Python");
        let meta = fs::symlink_metadata(&link).unwrap();
        assert!(meta.file_type().is_symlink(), "duz dosya olarak yazilmis — backend acilmaz");
        assert_eq!(
            fs::read_link(&link).unwrap(),
            Path::new("Python.framework/Versions/3.10/Python")
        );
    }

    /// Symlink zip-slip'in ikinci yüzü: link kök altında ama HEDEFİ dışarıda.
    #[cfg(unix)]
    #[test]
    fn disari_cikan_symlink_reddedilir() {
        let (_d, zip_path) = build_zip_with_symlink("a/b/link", "../../../../etc/passwd");
        let out = tempfile::tempdir().unwrap();
        assert!(matches!(
            extract_zip(&zip_path, out.path()).unwrap_err(),
            ExtractError::PathEscape(_)
        ));
    }

    #[cfg(unix)]
    #[test]
    fn mutlak_hedefli_symlink_reddedilir() {
        let (_d, zip_path) = build_zip_with_symlink("link", "/etc/passwd");
        let out = tempfile::tempdir().unwrap();
        assert!(matches!(
            extract_zip(&zip_path, out.path()).unwrap_err(),
            ExtractError::PathEscape(_)
        ));
    }

    /// Kök içinde kalan `..` kullanımı MEŞRUDUR (ör. framework içi göreli linkler).
    #[cfg(unix)]
    #[test]
    fn kok_icinde_kalan_gorelilik_kabul_edilir() {
        let (_d, zip_path) = build_zip_with_symlink("a/b/link", "../c/real.dylib");
        let out = tempfile::tempdir().unwrap();
        extract_zip(&zip_path, out.path()).unwrap();
        assert!(fs::symlink_metadata(out.path().join("a/b/link")).unwrap().file_type().is_symlink());
    }

    /// DENETİM 2026-08-04: `is_within` bir GÜVENLİK yüklemidir → çözümlenemeyen yol "güvenli"
    /// sayılmamalı (eski hâli `true` dönüyordu = FAIL-OPEN).
    #[test]
    fn is_within_fail_closed_ve_var_olmayan_yolu_dogru_degerlendirir() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();

        // 1) Kök altındaki VAR OLAN dosya → true
        let inside = root.join("a");
        fs::create_dir_all(&inside).unwrap();
        let f = inside.join("x.bin");
        fs::write(&f, b"x").unwrap();
        assert!(is_within(root, &f));

        // 2) Kök altında HENÜZ YOK olan yol → en yakın var olan ata (a/) çözümlenir → true
        assert!(is_within(root, &inside.join("daha").join("olmayan.bin")));

        // 3) Kökün DIŞINDAKİ var olan yol → false
        let outside = dir.path().parent().unwrap().to_path_buf();
        assert!(!is_within(root, &outside));

        // 4) Kök çözümlenemiyorsa (yok) → FAIL-CLOSED, true DEĞİL
        let yok = root.join("hic-olmayan-kok");
        assert!(!is_within(&yok, &yok.join("x")), "kok cozumlenemedi ama 'guvenli' dendi (fail-open)");
    }

    /// ⚠️ DENETİM 2026-08-04 (#102): İKİ symlink tek tek "kök altında" görünür ama ZİNCİRLENİNCE
    /// kökün DIŞINA çıkar (`a -> "."`, `b -> "a/.."` → `<kök>/b` = kökün EBEVEYNİ). Ardından
    /// sıradan bir girdi o link ÜZERİNDEN dışarı yazar. `stays_within` salt sözdizimsel olduğu
    /// için bunu GÖREMİYORDU; artık yazmadan önce hedef dizin GERÇEKTEN çözümleniyor.
    #[cfg(unix)]
    #[test]
    fn zincirleme_symlink_ile_disari_yazma_reddedilir() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("chain.zip");
        let f = fs::File::create(&path).unwrap();
        let mut w = zip::ZipWriter::new(f);
        let opts: zip::write::SimpleFileOptions = zip::write::FileOptions::default();
        // 1) a -> "."          (kök altında görünür)
        w.add_symlink("a", ".", opts).unwrap();
        // 2) b -> "a/.."       (sadeleştirilince kök; ama GERÇEKTE kökün EBEVEYNİ)
        w.add_symlink("b", "a/..", opts).unwrap();
        // 3) b/ustunden DIŞARI yazma denemesi
        w.start_file("b/kacak.txt", zip::write::FileOptions::<()>::default()).unwrap();
        w.write_all(b"pwned").unwrap();
        w.finish().unwrap();

        let out = tempfile::tempdir().unwrap();
        let err = extract_zip(&path, out.path()).unwrap_err();
        assert!(
            matches!(err, ExtractError::PathEscape(_)),
            "zincirleme symlink ile kok DISINA yazma ENGELLENMEDI: {err:?}"
        );
        // Kökün ebeveynine hiçbir şey sızmamış olmalı.
        assert!(!out.path().parent().unwrap().join("kacak.txt").exists());
    }

    /// Windows karşılığı (#102): zip-symlink'ler burada zaten reddedilir, ama hedef dizin
    /// BAŞKA bir yolla (junction/reparse-point — `mklink /J`, yönetici GEREKTİRMEZ) kurulum
    /// kökünün dışına yönlendirilmiş olabilir. Aynı koruma bunu da yakalamalı.
    #[cfg(windows)]
    #[test]
    fn junction_uzerinden_disari_yazma_reddedilir() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("kurulum");
        let disari = dir.path().join("disari");
        fs::create_dir_all(&root).unwrap();
        fs::create_dir_all(&disari).unwrap();

        // <kök>/link  ->  <tmp>/disari   (kurulum kökünün DIŞI)
        let st = std::process::Command::new("cmd")
            .args(["/C", "mklink", "/J"])
            .arg(root.join("link"))
            .arg(&disari)
            .output();
        let ok = st.map(|o| o.status.success()).unwrap_or(false);
        if !ok {
            eprintln!("atlandi: junction olusturulamadi (mklink yok/izin yok)");
            return;
        }

        let path = dir.path().join("j.zip");
        let f = fs::File::create(&path).unwrap();
        let mut w = zip::ZipWriter::new(f);
        w.start_file("link/kacak.txt", zip::write::FileOptions::<()>::default()).unwrap();
        w.write_all(b"pwned").unwrap();
        w.finish().unwrap();

        let err = extract_zip(&path, &root).unwrap_err();
        assert!(
            matches!(err, ExtractError::PathEscape(_)),
            "junction uzerinden kok DISINA yazma ENGELLENMEDI: {err:?}"
        );
        assert!(!disari.join("kacak.txt").exists(), "dosya kok disina yazilmis");
    }

    /// ⚠️ P2 (denetim 2026-08-04): #102 kontrolü YALNIZ düz-dosya dalındaydı. DİZİN girdisi
    /// (`is_dir` → `continue`) kontrolden ÖNCE dönüyordu → junction izlenip kurulum kökünün
    /// DIŞINDA dizin oluşuyor ve fonksiyon HATA BİLE VERMİYORDU (`Ok(0)`).
    #[cfg(windows)]
    #[test]
    fn junction_uzerinden_dizin_olusturma_da_reddedilir() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("kurulum");
        let disari = dir.path().join("disari");
        fs::create_dir_all(&root).unwrap();
        fs::create_dir_all(&disari).unwrap();

        let st = std::process::Command::new("cmd")
            .args(["/C", "mklink", "/J"])
            .arg(root.join("link"))
            .arg(&disari)
            .output();
        if !st.map(|o| o.status.success()).unwrap_or(false) {
            eprintln!("atlandi: junction olusturulamadi");
            return;
        }

        // Arşivde YALNIZCA bir DİZİN girdisi var — hiç dosya yok.
        let path = dir.path().join("d.zip");
        let f = fs::File::create(&path).unwrap();
        let mut w = zip::ZipWriter::new(f);
        w.add_directory("link/kacak_dizin/", zip::write::FileOptions::<()>::default())
            .unwrap();
        w.finish().unwrap();

        let err = extract_zip(&path, &root).unwrap_err();
        assert!(
            matches!(err, ExtractError::PathEscape(_)),
            "DIZIN girdisi junction uzerinden kok DISINA cikti: {err:?}"
        );
        assert!(
            !disari.join("kacak_dizin").exists(),
            "dizin kurulum kokunun DISINDA olusturulmus"
        );
    }

    /// #104: profil (model) paketi `install_root`'a açılır → DOĞRULANMIŞ `runtime/` ağacını ya da
    /// launcher durum dosyalarını EZEBİLİYORDU. `backend.port` ezilirse E-stop adresi de kaybolur.
    #[test]
    fn profil_paketi_runtime_ve_durum_dosyalarini_ezemez() {
        for kotu in [
            "runtime/PEMF_Backend/PEMF_Backend.exe",
            "installed_profiles.json",
            "backend.port",
            "cache/base.zip",
            "pending_install.json",
            "selfupdate_attempt.json",
            // DENETİM 2026-08-06: "Beni hatırla" oturumu da kurulum kökünde → profil paketi
            // kullanıcının kayıtlı oturumunu EZEMEZ (aksi halde sessiz "çıkış yaptırma").
            "auth_session.bin",
        ] {
            let (_d, zip_path) = build_zip(&[(kotu, b"sahte" as &[u8])]);
            let out = tempfile::tempdir().unwrap();
            let mut used = 0u64;
            let err = extract_zip_budgeted(&zip_path, out.path(), &mut used, true).unwrap_err();
            assert!(
                matches!(err, ExtractError::PathEscape(_)),
                "profil paketi '{kotu}' yazabildi: {err:?}"
            );
        }

        // MEŞRU profil içeriği (`ai_models/...`) ve BASE paketi (is_profile=false) etkilenmemeli.
        let (_d, ok_zip) = build_zip(&[("ai_models/ai_hub/em_kedi/m.onnx", b"x" as &[u8])]);
        let out = tempfile::tempdir().unwrap();
        let mut used = 0u64;
        assert_eq!(extract_zip_budgeted(&ok_zip, out.path(), &mut used, true).unwrap(), 1);

        let (_d2, base_zip) = build_zip(&[("runtime/PEMF_Backend/x", b"y" as &[u8])]);
        let out2 = tempfile::tempdir().unwrap();
        let mut used2 = 0u64;
        assert_eq!(
            extract_zip_budgeted(&base_zip, out2.path(), &mut used2, false).unwrap(),
            1,
            "base paketi runtime/ altina yazabilmeli"
        );
    }

    /// #110: açılım bütçesi her çağrıda SIFIRLANIYORDU → base + 3 profil için belgelenen 8 GB
    /// tavanı pratikte 32 GB'dı. Artık çağıran tarafından TAŞINIR.
    #[test]
    fn acilim_butcesi_cagrilar_arasinda_tasinir() {
        let (_d, z) = build_zip(&[("a.bin", b"0123456789" as &[u8])]);
        let mut used = 0u64;
        let out1 = tempfile::tempdir().unwrap();
        extract_zip_budgeted(&z, out1.path(), &mut used, false).unwrap();
        let after_first = used;
        assert_eq!(after_first, 10, "yazilan bayt butceye islenmedi");

        let out2 = tempfile::tempdir().unwrap();
        extract_zip_budgeted(&z, out2.path(), &mut used, false).unwrap();
        assert_eq!(used, 20, "ikinci cagri butceyi SIFIRLADI (paylasim yok)");

        // Eski `extract_zip` sarmalayicisi hala calisir (cagri-basi butce).
        let out3 = tempfile::tempdir().unwrap();
        assert_eq!(extract_zip(&z, out3.path()).unwrap(), 1);
    }

    #[test]
    fn stays_within_dogru_hesaplar() {
        let root = Path::new("/opt/app");
        assert!(stays_within(root, Path::new("/opt/app/a/b"), Path::new("../c")));
        assert!(stays_within(root, Path::new("/opt/app"), Path::new("x/y")));
        assert!(!stays_within(root, Path::new("/opt/app/a"), Path::new("../../escape")));
    }

    #[cfg(unix)]
    #[test]
    fn calistirma_biti_korunur() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("x.zip");
        let f = fs::File::create(&path).unwrap();
        let mut w = zip::ZipWriter::new(f);
        let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .unix_permissions(0o755);
        w.start_file("PEMF_Backend", opts).unwrap();
        w.write_all(b"#!/bin/sh\n").unwrap();
        w.finish().unwrap();

        let out = tempfile::tempdir().unwrap();
        extract_zip(&path, out.path()).unwrap();
        use std::os::unix::fs::PermissionsExt;
        let mode = fs::metadata(out.path().join("PEMF_Backend")).unwrap().permissions().mode();
        assert_eq!(mode & 0o111, 0o111, "calistirma biti kaybolmus — backend baslatilamaz");
    }
}
