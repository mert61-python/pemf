// PEMF Vet Client (launcher) — PROFESYONEL indirme (Steam-tarzı): kaldığı yerden devam (HTTP Range),
// durdur/devam/iptal, bağlantı kopunca otomatik yeniden-bağlan + install-layout kurulum.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicBool, Ordering},
    thread,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter};
#[cfg(windows)]
use std::os::windows::process::CommandExt;

// Konsol penceresi açmadan çalıştır (sessiz kurulum — hiçbir PowerShell/cmd penceresi görünmez).
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
#[cfg(not(windows))]
const CREATE_NO_WINDOW: u32 = 0;

// macOS/Linux: Windows'a özel `.creation_flags()` metodu yok. Paylaşılan kod (powershell çağrıları)
// çapraz-platform DERLENSİN diye no-op shim. (Bu kurulum akışı zaten yalnız Windows'ta çalışır;
// Mac derlemesi için yalnızca derlenebilirlik gerekir.)
#[cfg(not(windows))]
trait CreationFlagsExt {
    fn creation_flags(&mut self, flags: u32) -> &mut Self;
}
#[cfg(not(windows))]
impl CreationFlagsExt for std::process::Command {
    fn creation_flags(&mut self, _flags: u32) -> &mut Self {
        self
    }
}

// Masaüstü kısayolu için PEMF (kalp) uygulama ikonu — binary'ye gömülü, kuruluma bağımsız.
const APP_ICON: &[u8] = include_bytes!("../icons/pemf_app.ico");

// Tek indirme aynı anda çalışır → global durum bayrakları (durdur/iptal).
static PAUSED: AtomicBool = AtomicBool::new(false);
static CANCELLED: AtomicBool = AtomicBool::new(false);
// Aynı anda TEK kurulum (re-entrancy kilidi): çift start_install çağrısı aynı .part/finalize.ps1
// dosyalarına yazıp bozmasın + iki UAC istemi çıkmasın.
static INSTALLING: AtomicBool = AtomicBool::new(false);

#[derive(Clone, Serialize)]
struct Progress {
    percent: u32,
    label: String,
    /// downloading | retrying | paused | installing | done | error | cancelled
    state: String,
    done: bool,
    error: Option<String>,
    #[serde(rename = "downloadedMb")]
    downloaded_mb: u64,
    #[serde(rename = "totalMb")]
    total_mb: u64,
    #[serde(rename = "speedMbps")]
    speed_mbps: f64,
}

/// İlerleme güncellemesi (çekirdek → emitter). Progress'e dönüştürülür.
struct Upd {
    pct: u32,
    label: String,
    state: String,
    downloaded: u64,
    total: u64,
    speed: f64,
}

enum Dl {
    Done,
    Cancelled,
}

#[derive(Deserialize)]
struct Manifest {
    #[allow(dead_code)]
    #[serde(default)]
    version: String,
    base: Component,
    #[serde(default)]
    profiles: std::collections::HashMap<String, Component>,
}

#[derive(Deserialize)]
struct Component {
    url: String,
    #[serde(default)]
    sha256: String,
    #[serde(default)]
    size: u64,
    #[allow(dead_code)]
    #[serde(default)]
    kind: String,
}

fn data_dir() -> PathBuf {
    let base = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".into());
    PathBuf::from(base).join("PEMFVetClient")
}
fn marker() -> PathBuf {
    data_dir().join("installed.json")
}
fn install_dir() -> String {
    std::env::var("PEMF_INSTALL_DIR").unwrap_or_else(|_| r"C:\Program Files\PEMF Backend".into())
}
fn models_parent() -> String {
    std::env::var("PEMF_MODELS_PARENT").unwrap_or_else(|_| r"C:\ProgramData\PEMF_GUI".into())
}

/// install_dir'in YIKICI işlem (rename-swap / recursive-delete) için GÜVENLİ olduğunu doğrular:
/// mutlak + en az 2 seviye derin + sürücü-kökü/sistem-dizini değil. Yanlış/kötücül PEMF_INSTALL_DIR
/// (boş, `C:\`, `C:\Windows\System32`) ile admin-yetkili felaket-silmeyi önler.
fn validate_install_dir(inst: &str) -> Result<(), String> {
    // PS meta-karakterleri (çift-tırnaklı bağlamda tehlikeli): $ → değişken, ` → escape, " → tırnak-kır.
    // Varsayılan yollarda yok; yalnız kötücül/yanlış PEMF_INSTALL_DIR'de olabilir → reddet (L1).
    if inst.contains('$') || inst.contains('`') || inst.contains('"') {
        return Err(format!("Kurulum yolu güvensiz karakter içeriyor ($ ` \"): {inst}"));
    }
    let p = Path::new(inst);
    if !p.is_absolute() {
        return Err(format!("Kurulum yolu geçersiz (mutlak değil): {inst}"));
    }
    let depth = p
        .components()
        .filter(|c| matches!(c, std::path::Component::Normal(_)))
        .count();
    if depth < 2 {
        return Err(format!("Kurulum yolu çok sığ (sürücü-kökü riski): {inst}"));
    }
    let low = inst.to_lowercase().replace('/', "\\");
    let trimmed = low.trim_end_matches('\\');
    if trimmed.len() <= 2 {
        return Err(format!("Kurulum yolu sürücü kökü: {inst}"));
    }
    let sysroot = std::env::var("SystemRoot").unwrap_or_else(|_| r"C:\Windows".into());
    let sysroot = sysroot.to_lowercase().replace('/', "\\");
    let sysroot = sysroot.trim_end_matches('\\');
    if trimmed == sysroot || trimmed.starts_with(&format!("{sysroot}\\")) {
        return Err(format!("Kurulum yolu sistem dizini içinde: {inst}"));
    }
    Ok(())
}

fn save_installed(profiles: &[String]) -> std::io::Result<()> {
    fs::create_dir_all(data_dir())?;
    let data = serde_json::to_string(profiles).unwrap_or_else(|_| "[]".into());
    // ATOMİK yaz: temp'e yaz → rename (Windows'ta MOVEFILE_REPLACE_EXISTING). Yarıda kesilse bile
    // truncated/bozuk marker bırakmaz (aksi halde bozuk marker → gereksiz tam-yeniden-kurulum riski).
    let tmp = data_dir().join("installed.json.tmp");
    fs::write(&tmp, &data)?;
    fs::rename(&tmp, marker())
}

/// PowerShell TEK-tırnak string kaçışı ('→''). Yol/kullanıcı-adı apostrof içerse (ör. "O'Brien")
/// tek-tırnaklı PS literali kırılmasın diye elevated betiklerde kullanılır.
fn psq(s: &str) -> String {
    s.replace('\'', "''")
}

/// Backend exe'si diskte var mı (kurulum en azından başlamış mı).
fn backend_exe_present() -> bool {
    Path::new(&install_dir()).join("PEMF_Backend.exe").exists()
}

/// Backend GERÇEKTEN ayakta + arayüz sunuyor mu? (localhost:8000 → 200). Kısa timeout + birkaç deneme.
/// "exe var ama arayüz yok" = bozuk/yarım kurulum → çağıran taraf tam onarım tetikler
/// (siyah-ekran / 404 durumunun sessizce 'başarılı' sanılmasını önler).
fn backend_healthy() -> bool {
    let client = match reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };
    for _ in 0..3 {
        if let Ok(r) = client.get("http://127.0.0.1:8000/").send() {
            if r.status().is_success() {
                return true;
            }
        }
        thread::sleep(Duration::from_millis(600));
    }
    false
}

/// PemfBackend Windows servisi KAYITLI mı? (anında, zamanlama-bağımsız SCM sorgusu). Bu, "tam kurulmuş
/// ama yavaş-açılan" (servis VAR → YIKMA) ile "yarım kurulum" (servis YOK → tam onar) ayrımını yapar —
/// böylece marker kayıp + yavaş backend, sağlık-probu zamanlamasına takılıp yıkıcı tam-kuruluma düşmez.
fn backend_service_exists() -> bool {
    Command::new("sc")
        .args(["query", "PemfBackend"])
        .creation_flags(CREATE_NO_WINDOW)
        .output()
        .map(|o| o.status.success()) // sc query: servis varsa exit 0, yoksa 1060
        .unwrap_or(false)
}

/// "Başlat" öncesi backend'in GERÇEKTEN hazır olmasını sağlar: hazır değilse (kurulu) servisi
/// başlatmayı dener + arayüz (localhost:8000) yanıt verene dek sınırlı süre bekler. true = hazır.
/// Reboot sonrası frozen-EXE soğuk-başlangıç + Defender taramasına tolerans → app açılınca çerçevesiz
/// "Bu sayfaya ulaşılamıyor" ekranını önler (marker var ≠ servis O AN ayakta).
fn wait_backend_ready(max: Duration) -> bool {
    if backend_healthy() {
        return true;
    }
    // Servis kayıtlıysa ama durmuşsa başlatmayı dene (DACL izin vermezse / kurulu değilse zararsız).
    if backend_service_exists() {
        let _ = Command::new("sc")
            .args(["start", "PemfBackend"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }
    let deadline = Instant::now() + max;
    while Instant::now() < deadline {
        thread::sleep(Duration::from_millis(800));
        if backend_healthy() {
            return true;
        }
    }
    false
}

fn fetch_manifest(url: &str) -> Result<Manifest, String> {
    // Timeout ŞART: yavaş/yarı-açık manifest host'unda kurulum thread'i sonsuz asılı kalmasın
    // (manifest küçük → tüm-istek timeout uygun; convenience get() timeout'suzdu).
    let client = reqwest::blocking::Client::builder()
        .connect_timeout(Duration::from_secs(15))
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|e| e.to_string())?;
    let txt = client
        .get(url)
        .send()
        .and_then(|r| r.error_for_status())
        .map_err(|e| format!("manifest indirilemedi: {e}"))?
        .text()
        .map_err(|e| e.to_string())?;
    serde_json::from_str(&txt).map_err(|e| format!("manifest çözümlenemedi: {e}"))
}

fn pct(done: u64, total: u64) -> u32 {
    (((done as f64) / (total.max(1) as f64)) * 100.0).min(99.0) as u32
}

/// Tamamlanmış .part dosyasının sha256'sı (tek geçiş — resume sonrası bütünlük).
fn hash_file(p: &Path) -> Result<String, String> {
    let mut f = fs::File::open(p).map_err(|e| e.to_string())?;
    let mut h = Sha256::new();
    let mut buf = [0u8; 65536];
    loop {
        let n = f.read(&mut buf).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        h.update(&buf[..n]);
    }
    Ok(format!("{:x}", h.finalize()))
}

/// Duraklatıldıysa bekle (bağlantı kapalı; devam edilince Range ile sürer). İptal gelirse Cancelled.
fn wait_if_paused(
    progress: &dyn Fn(Upd),
    label: &str,
    downloaded: u64,
    total: u64,
) -> Option<Dl> {
    if !PAUSED.load(Ordering::Relaxed) {
        return None;
    }
    while PAUSED.load(Ordering::Relaxed) {
        if CANCELLED.load(Ordering::Relaxed) {
            return Some(Dl::Cancelled);
        }
        progress(Upd {
            pct: pct(downloaded, total),
            label: label.into(),
            state: "paused".into(),
            downloaded,
            total,
            speed: 0.0,
        });
        thread::sleep(Duration::from_millis(300));
    }
    None
}

/// Bir bileşeni RESUMABLE indirir: `.part`e yazar (Range ile kaldığı yerden), bağlantı kopunca
/// otomatik yeniden dener (ilerleme oldukça sayaç sıfırlanır), durdur/iptal duyarlı, sha256 doğrular,
/// sonra `.part → final` yeniden adlandırır. Çıkarmaz.
#[allow(clippy::too_many_arguments)]
fn download_to(
    comp: &Component,
    part: &Path,
    finalp: &Path,
    base_done: u64,
    total: u64,
    label: &str,
    progress: &dyn Fn(Upd),
) -> Result<Dl, String> {
    // Resume: bu bileşen zaten TAM + DOĞRU inmiş mi? sha256 varsa İÇERİĞİ doğrula (yalnız-boyut kabulü,
    // aynı-boyutlu bozuk/zehirli cache'i finalize'a taşır → tar patlar → hata sonrası cache kalır →
    // tekrar-dene/Onar aynı bozuğu kabul = ONARILAMAZ). Kendini-iyileştiren cache: bozuksa sil+baştan.
    if finalp.exists() {
        let ok = if !comp.sha256.is_empty() {
            // en güçlü sinyal: içerik hash'i (boyuttan bağımsız)
            hash_file(finalp)
                .map(|h| h.eq_ignore_ascii_case(&comp.sha256))
                .unwrap_or(false)
        } else {
            // sha256 yok → yalnız BİLİNEN (sıfırdan farklı) boyut eşleşmesine güven; size==0 = güvenme
            let sz = fs::metadata(finalp).map(|m| m.len()).unwrap_or(0);
            comp.size != 0 && sz == comp.size
        };
        if ok {
            return Ok(Dl::Done);
        }
        let _ = fs::remove_file(finalp); // eksik/bozuk/doğrulanamaz → sil, baştan indir
    }
    // Not: reqwest 0.12 blocking'de per-read timeout yok. Bağlantı kopması okuma-hatası üretir
    // (net_err) → otomatik Range-resume. connect_timeout yeniden-bağlanma denemelerini sınırlar.
    // TCP keepalive: yarı-açık/ölü bağlantıyı (veri de FIN de gelmeyen "stall" — WiFi kopması,
    // NAT/captive-portal zaman-aşımı, router reset) OS-seviyesinde tespit et → bloklanan read()
    // hata döner → yukarıdaki Range-resume devreye girer (aksi halde read() saatlerce bloklardı).
    let client = reqwest::blocking::Client::builder()
        .connect_timeout(Duration::from_secs(30))
        .tcp_keepalive(Duration::from_secs(30))
        .tcp_keepalive_interval(Duration::from_secs(10))
        .tcp_keepalive_retries(3)
        .build()
        .map_err(|e| e.to_string())?;
    let max_retries: u32 = 12;
    let mut attempt: u32 = 0;
    let mut buf = [0u8; 65536];

    loop {
        if CANCELLED.load(Ordering::Relaxed) {
            return Ok(Dl::Cancelled);
        }
        if let Some(d) = wait_if_paused(progress, label, base_done, total) {
            return Ok(d);
        }
        let already = fs::metadata(part).map(|m| m.len()).unwrap_or(0);

        let mut rb = client.get(&comp.url);
        if already > 0 {
            rb = rb.header(reqwest::header::RANGE, format!("bytes={already}-"));
        }
        let resp = match rb.send().and_then(|r| r.error_for_status()) {
            Ok(r) => r,
            Err(e) => {
                attempt += 1;
                if attempt > max_retries {
                    return Err(format!("İndirme başarısız ({label}): {e}"));
                }
                progress(Upd {
                    pct: pct(base_done + already, total),
                    label: label.into(),
                    state: "retrying".into(),
                    downloaded: base_done + already,
                    total,
                    speed: 0.0,
                });
                for _ in 0..(attempt.min(8) + 1) {
                    if CANCELLED.load(Ordering::Relaxed) {
                        return Ok(Dl::Cancelled);
                    }
                    if let Some(d) = wait_if_paused(progress, label, base_done + already, total) {
                        return Ok(d);
                    }
                    thread::sleep(Duration::from_millis(700));
                }
                continue;
            }
        };

        let resumed = already > 0 && resp.status() == reqwest::StatusCode::PARTIAL_CONTENT;
        let mut file = if resumed {
            fs::OpenOptions::new()
                .append(true)
                .open(part)
                .map_err(|e| e.to_string())?
        } else {
            fs::File::create(part).map_err(|e| e.to_string())? // 200 (Range yok) / ilk → baştan
        };
        let start_got = if resumed { already } else { 0 };
        let mut got = start_got;
        let mut resp = resp;
        let mut t = Instant::now();
        let mut t_bytes = got;
        let mut net_err = false;
        let mut paused = false;

        loop {
            if CANCELLED.load(Ordering::Relaxed) {
                let _ = file.flush();
                return Ok(Dl::Cancelled);
            }
            if PAUSED.load(Ordering::Relaxed) {
                paused = true;
                break;
            }
            let n = match resp.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => n,
                Err(_) => {
                    net_err = true;
                    break;
                }
            };
            if file.write_all(&buf[..n]).is_err() {
                return Err(format!("Disk yazma hatası ({label})"));
            }
            got += n as u64;
            let el = t.elapsed().as_secs_f64();
            if el >= 0.4 {
                let speed = (got - t_bytes) as f64 / el / 1_000_000.0;
                t = Instant::now();
                t_bytes = got;
                progress(Upd {
                    pct: pct(base_done + got, total),
                    label: label.into(),
                    state: "downloading".into(),
                    downloaded: base_done + got,
                    total,
                    speed,
                });
            }
        }
        let _ = file.flush();

        if paused {
            if let Some(d) = wait_if_paused(progress, label, base_done + got, total) {
                return Ok(d); // iptal
            }
            continue; // devam → Range ile sürdür (bekleme hata değil, sayaç artmaz)
        }

        if net_err || (comp.size > 0 && got < comp.size) {
            if got > start_got {
                attempt = 0; // ilerleme oldu → yeniden-bağlan sayacı sıfırla (Steam gibi)
            } else {
                attempt += 1;
            }
            if attempt > max_retries {
                return Err(format!("Bağlantı tekrar kurulamadı ({label})"));
            }
            progress(Upd {
                pct: pct(base_done + got, total),
                label: label.into(),
                state: "retrying".into(),
                downloaded: base_done + got,
                total,
                speed: 0.0,
            });
            for _ in 0..(attempt.max(1).min(8) + 1) {
                if CANCELLED.load(Ordering::Relaxed) {
                    return Ok(Dl::Cancelled);
                }
                if let Some(d) = wait_if_paused(progress, label, base_done + got, total) {
                    return Ok(d);
                }
                thread::sleep(Duration::from_millis(700));
            }
            continue;
        }

        // Tamamlandı → bütünlük
        if !comp.sha256.is_empty() {
            let actual = hash_file(part)?;
            if !actual.eq_ignore_ascii_case(&comp.sha256) {
                let _ = fs::remove_file(part); // bozuk → baştan
                attempt += 1;
                if attempt > max_retries {
                    return Err(format!("Bütünlük doğrulaması başarısız ({label})"));
                }
                continue;
            }
        }
        fs::rename(part, finalp).map_err(|e| e.to_string())?;
        return Ok(Dl::Done);
    }
}

/// Kullanıcı-yazılabilir dizindeki bir PS betiğini elevated (RunAs) çalıştıran outer komut — ÖNCE
/// sha256 hash-kapısı: betik RunAs ile okunmadan önce (TOCTOU) değiştirilirse admin-yetkiyle
/// çalışmaz. Beklenen hash disk yerine tamper-edilemez process-argümanına gömülür (çift psq: inner
/// PS komutu bir kez, dış Start-Process argümanı bir kez → RunAs tarafında doğru çözülür).
fn elevated_hashgated_outer(ps_path: &Path) -> Result<String, String> {
    let bytes = fs::read(ps_path).map_err(|e| e.to_string())?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    let hash = format!("{:x}", hasher.finalize()).to_uppercase();
    let p = psq(&ps_path.display().to_string());
    let inner = format!(
        "$h=(Get-FileHash -Algorithm SHA256 -LiteralPath '{p}').Hash; if ($h -ne '{hash}') {{ exit 7 }}; & '{p}'"
    );
    Ok(format!(
        "Start-Process powershell -Verb RunAs -WindowStyle Hidden -Wait -ArgumentList '-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-Command','{}'",
        psq(&inner)
    ))
}

/// İndirilen paketleri GERÇEK konumlara kurar (elevated): base→Program Files,
/// modeller→ProgramData\PEMF_GUI, sonra setup_services.ps1 (NSSM). tar ile çıkarır.
// is_full=true → TAM kurulum (temiz sil + base + modeller + servis). false → ARTIMLI: yalnız yeni
// profil modellerini ekle, backend'e/base'e DOKUNMA. is_full çağıran tarafından `!backend_installed`
// ile AÇIKÇA verilir — downloads'ta stale base.zip'e GÜVENİLMEZ (yanlış wipe'ı önler).
fn finalize_install(profiles: &[String], is_full: bool) -> Result<(), String> {
    let inst = install_dir();
    validate_install_dir(&inst)?; // yıkıcı rename-swap öncesi yol güvenliği (env-override footgun'u)
    let models = models_parent();
    if models.contains('$') || models.contains('`') || models.contains('"') {
        return Err("Model dizini güvensiz karakter içeriyor.".into()); // L1: çift-tırnaklı PS bağlamı
    }
    let dl = data_dir().join("downloads");
    let result = data_dir().join("finalize.result");
    let ps_path = data_dir().join("finalize.ps1");
    let _ = fs::remove_file(&result);

    let base_zip = dl.join("base.zip");

    // tarx: YALNIZ zip mevcutsa çıkar (Test-Path guard) → indirilmemiş/eksik zip finalize'ı çökertmez
    // (eskiden base yoksa 'tar cikarma hatasi' + dizin zaten silinmiş = kurulum bozuk kalıyordu).
    let tarx = |zip: String, dir: &str| {
        format!(
            "if (Test-Path \"{zip}\") {{\r\n\
             $to = & \"$env:windir\\System32\\tar.exe\" -xf \"{zip}\" -C \"{dir}\" 2>&1\r\n\
             if ($LASTEXITCODE -ne 0) {{ throw \"tar cikarma hatasi (kod $LASTEXITCODE): $to\" }}\r\n\
             }}\r\n"
        )
    };
    // extracts = YALNIZ profil modelleri (ProgramData'ya, ekleme — yıkım yok). base ayrı STAGING ile.
    let mut extracts = String::new();
    for p in profiles {
        extracts.push_str(&tarx(dl.join(format!("{p}.zip")).display().to_string(), &models));
    }

    // TAM kurulumda base'i STAGING'e çıkar → BAŞARILIYSA eski inst'i sil + taşı. Böylece geçerli-ama-
    // yarıda-çıkarılan base (disk-dolu / AV-kilidi / güç-kesintisi) çalışan backend'i YIKMAZ: staging
    // patlarsa eski inst'e DOKUNULMAMIŞ olur (fail-safe). Artımlıda base_stage boş = backend'e dokunma.
    let base_stage = if is_full {
        format!(
            "$stage = \"{inst}._stage\"\r\n\
             $old = \"{inst}._old\"\r\n\
             Remove-Item \"$stage\" -Recurse -Force -ErrorAction SilentlyContinue\r\n\
             Remove-Item \"$old\" -Recurse -Force -ErrorAction SilentlyContinue\r\n\
             if (Test-Path \"$old\") {{ throw \"onceki kurulum ._old klasoru temizlenemedi (kilitli olabilir); backend'i durdurup tekrar deneyin\" }}\r\n\
             New-Item -ItemType Directory -Force -Path \"$stage\" | Out-Null\r\n\
             if (Test-Path \"{base}\") {{\r\n\
             $to = & \"$env:windir\\System32\\tar.exe\" -xf \"{base}\" -C \"$stage\" 2>&1\r\n\
             if ($LASTEXITCODE -ne 0) {{ Remove-Item \"$stage\" -Recurse -Force -ErrorAction SilentlyContinue; throw \"base cikarma hatasi (kod $LASTEXITCODE): $to\" }}\r\n\
             }} else {{ Remove-Item \"$stage\" -Recurse -Force -ErrorAction SilentlyContinue; throw \"base paketi bulunamadi\" }}\r\n\
             # ATOMİK-BENZERİ TAKAS: eski inst'i SİLME → yeniden adlandır (._old). Kilitli exe olsa\r\n\
             # bile ayni-birim rename metadata islemidir (silme değil) → calisir. Wipe+move'da (eski\r\n\
             # yol) kilitli dosya wipe'i yarim birakip move'u throw ettirir + eski surum yok olurdu.\r\n\
             if (Test-Path \"{inst}\") {{ Move-Item -LiteralPath \"{inst}\" -Destination \"$old\" -Force -ErrorAction Stop }}\r\n\
             try {{ Move-Item -LiteralPath \"$stage\" -Destination \"{inst}\" -Force -ErrorAction Stop }}\r\n\
             catch {{ if (Test-Path \"$old\") {{ Move-Item -LiteralPath \"$old\" -Destination \"{inst}\" -Force -ErrorAction SilentlyContinue }}; throw \"kurulum takasi basarisiz (eski surum geri yuklendi): $_\" }}\r\n\
             Remove-Item \"$old\" -Recurse -Force -ErrorAction SilentlyContinue\r\n",
            inst = inst,
            base = base_zip.display()
        )
    } else {
        String::new()
    };
    // TAM kurulum: servisi (yeniden) yapılandır. ARTIMLI: yalnız backend'i yeniden başlat
    // (yeni profil modelleri yüklensin; servis config'ine / install dosyalarına dokunma).
    let skip_svc = std::env::var("PEMF_SKIP_SERVICE").is_ok();
    let svc = if skip_svc {
        String::new() // test modu: servise dokunma
    } else if is_full {
        format!(
            "& \"{inst}\\setup_services.ps1\" -AppDir \"{inst}\" -Mode device\r\n\
             if ($LASTEXITCODE -ne 0) {{ throw \"servis kurulumu hatasi (kod $LASTEXITCODE)\" }}\r\n"
        )
    } else {
        // ARTIMLI: servis YOKSA kur (self-heal — yarım kurulumdan kalmış olabilir), VARSA başlat.
        // Böylece 'servis yok → Start-Service sessiz no-op → yanlış başarı' tuzağı kapanır.
        format!(
            "if (-not (Get-Service PemfBackend -ErrorAction SilentlyContinue)) {{\r\n\
             & \"{inst}\\setup_services.ps1\" -AppDir \"{inst}\" -Mode device\r\n\
             if ($LASTEXITCODE -ne 0) {{ throw \"servis kurulumu hatasi (kod $LASTEXITCODE)\" }}\r\n\
             }} else {{\r\n\
             Start-Service PemfBackend -ErrorAction SilentlyContinue\r\n\
             }}\r\n"
        )
    };

    // Kurulum sonrası GERÇEK doğrulama: backend arayüzü (localhost:8000) 200 veriyor mu? Vermiyorsa
    // 'throw' → sonuç ERR olur → UI 'Hata' gösterir (durdurulmuş/bozuk backend'i 'Tamamlandı'
    // sanmaz). Bu, tam da yaşanan siyah-ekran/404 sınıfını yakalar.
    let verify = if skip_svc {
        String::new()
    } else {
        // 120 deneme × ~1sn → frozen EXE soğuk-başlangıç + Defender taramasına GENİŞ tolerans (yavaş
        // ama çalışan kurulumda yanlış ERR → yıkıcı 'Onar'a itmesin, L4). Normalde ~10sn'de 200.
        "$ok=$false\r\n\
         for($i=0; $i -lt 120; $i++) {\r\n\
         try { $r=Invoke-WebRequest 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -eq 200) { $ok=$true; break } } catch {}\r\n\
         Start-Sleep -Seconds 1\r\n\
         }\r\n\
         if (-not $ok) { throw 'backend arayuzu dogrulanamadi (localhost:8000 yanit vermiyor)' }\r\n"
            .to_string()
    };

    // Add/Remove kaydı YALNIZ tam kurulumda (artımlıda zaten kayıtlı → dokunma).
    let client_exe = std::env::current_exe()
        .map(|p| p.display().to_string())
        .unwrap_or_default();
    let reg = if is_full {
        format!(
            "$rk='HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\PEMFVetApp'\r\n\
             New-Item -Path $rk -Force | Out-Null\r\n\
             $appver = (Get-Item '{inst}\\PEMF_Backend.exe' -ErrorAction SilentlyContinue).VersionInfo.ProductVersion\r\n\
             if (-not $appver) {{ $appver = '1.8.0' }}\r\n\
             Set-ItemProperty $rk DisplayName 'PEMF Vet'\r\n\
             Set-ItemProperty $rk DisplayVersion $appver\r\n\
             Set-ItemProperty $rk Publisher 'V-PEMF Technologies'\r\n\
             Set-ItemProperty $rk DisplayIcon '{inst}\\PEMF_Backend.exe'\r\n\
             Set-ItemProperty $rk InstallLocation '{inst}'\r\n\
             Set-ItemProperty $rk UninstallString '\"{client_exe}\" --uninstall-app'\r\n\
             Set-ItemProperty $rk NoModify 1 -Type DWord\r\n\
             Set-ItemProperty $rk NoRepair 1 -Type DWord\r\n",
            // TEK-tırnaklı PS literalleri → apostrof-içeren yol (client_exe kullanıcı-profilinde) tüm
            // finalize betiğini PARSE-hatasıyla kırmasın diye psq (inst çift-tırnaklı kullanımlarda ayrı).
            inst = psq(&inst),
            client_exe = psq(&client_exe)
        )
    } else {
        String::new()
    };

    let script = format!(
        "$ErrorActionPreference='Stop'\r\n\
         try {{\r\n\
         New-Item -ItemType Directory -Force -Path \"{inst}\" | Out-Null\r\n\
         New-Item -ItemType Directory -Force -Path \"{models}\" | Out-Null\r\n\
         Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | Where-Object {{ $_.PathName -like '*PEMF Backend*' }} | ForEach-Object {{ Stop-Service -Name $_.Name -Force -ErrorAction SilentlyContinue }}\r\n\
         Get-Service PemfBackend -ErrorAction SilentlyContinue | Stop-Service -Force -ErrorAction SilentlyContinue\r\n\
         Start-Sleep -Milliseconds 1000\r\n\
         Get-Process -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -like '*PEMF Backend*' }} | Stop-Process -Force -ErrorAction SilentlyContinue\r\n\
         Start-Sleep -Seconds 2\r\n\
         {base_stage}\
         {extracts}{svc}{reg}{verify}\
         Set-Content -Path \"{result}\" -Value 'OK'\r\n\
         }} catch {{ Get-Service PemfBackend -ErrorAction SilentlyContinue | Start-Service -ErrorAction SilentlyContinue; Set-Content -Path \"{result}\" -Value ('ERR: ' + $_.Exception.Message); exit 1 }}\r\n",
        inst = inst,
        models = models,
        base_stage = base_stage,
        extracts = extracts,
        svc = svc,
        reg = reg,
        verify = verify,
        result = result.display()
    );
    fs::write(&ps_path, script).map_err(|e| e.to_string())?;

    let status = if std::env::var("PEMF_NO_ELEVATE").is_ok() {
        Command::new("powershell")
            .creation_flags(CREATE_NO_WINDOW)
            .args(["-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File"])
            .arg(&ps_path)
            .status()
    } else {
        // Tek UAC istemi (gerekli izin) → ardından her şey GİZLİ pencerede sessiz çalışır.
        let outer = elevated_hashgated_outer(&ps_path)?;
        Command::new("powershell")
            .creation_flags(CREATE_NO_WINDOW)
            .args(["-NoProfile", "-WindowStyle", "Hidden", "-Command", &outer])
            .status()
    }
    .map_err(|e| e.to_string())?;

    match fs::read_to_string(&result) {
        Ok(s) if s.trim() == "OK" => Ok(()),
        Ok(s) => Err(s.trim().to_string()),
        Err(_) => Err(format!(
            "Kurulum tamamlanamadı (yönetici izni reddedilmiş olabilir). Kod={:?}",
            status.code()
        )),
    }
}

/// Uygulama kaldırma betiği (elevated): servis durdur/sil + dosyalar + modeller + Add/Remove kaydı.
fn app_removal_script(inst: &str, models: &str) -> String {
    format!(
        "$ErrorActionPreference='SilentlyContinue'\r\n\
         Stop-Service PemfBackend -Force\r\n\
         Start-Sleep -Milliseconds 900\r\n\
         sc.exe delete PemfBackend | Out-Null\r\n\
         Remove-Item \"{inst}\" -Recurse -Force\r\n\
         Remove-Item \"{models}\\ai_models\" -Recurse -Force\r\n\
         Remove-Item 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\PEMFVetApp' -Recurse -Force\r\n"
    )
}

/// Uygulamayı kaldır: elevated betik (servis/dosya/kayıt) + per-user temizlik (marker/kısayol).
fn do_uninstall_app() -> Result<(), String> {
    let inst = install_dir();
    validate_install_dir(&inst)?; // recursive-delete öncesi yol güvenliği
    let models = models_parent();
    fs::create_dir_all(data_dir()).ok();
    let ps_path = data_dir().join("uninstall_app.ps1");
    fs::write(&ps_path, app_removal_script(&inst, &models)).map_err(|e| e.to_string())?;
    let status = if std::env::var("PEMF_NO_ELEVATE").is_ok() {
        Command::new("powershell")
            .creation_flags(CREATE_NO_WINDOW)
            .args(["-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File"])
            .arg(&ps_path)
            .status()
    } else {
        // Tek UAC istemi (gerekli izin) → ardından her şey GİZLİ pencerede sessiz çalışır.
        let outer = elevated_hashgated_outer(&ps_path)?;
        Command::new("powershell")
            .creation_flags(CREATE_NO_WINDOW)
            .args(["-NoProfile", "-WindowStyle", "Hidden", "-Command", &outer])
            .status()
    };
    match status {
        Ok(s) if s.success() => {
            // Elevated kaldırma BAŞARILI → per-user temizlik (marker/kısayol). Aksi halde marker KALIR:
            // UAC reddedilirse servis/dosyalar silinmemiştir; is_installed() yalan söylemesin (yarım-
            // kaldırma sonrası taze-kurulum akışı gösterip çalışan backend'i gizlemesin).
            let _ = fs::remove_file(marker());
            if let Ok(up) = std::env::var("USERPROFILE") {
                let desk = PathBuf::from(up).join("Desktop");
                // create_shortcuts artık .lnk üretiyor (eski .url yerine) + NSIS "PEMF Vet Client.lnk"
                // koyar → ÜÇÜNÜ de temizle (kaldırma sonrası ölü kısayol kalmasın).
                let _ = fs::remove_file(desk.join("PEMF Vet.url"));
                let _ = fs::remove_file(desk.join("PEMF Vet.lnk"));
                let _ = fs::remove_file(desk.join("PEMF Vet Client.lnk"));
            }
            Ok(())
        }
        _ => Err("Kaldırma tamamlanamadı (yönetici izni gerekli olabilir).".into()),
    }
}

#[tauri::command]
fn uninstall_app() -> Result<(), String> {
    do_uninstall_app()
}

/// Çekirdek: manifest → (gerekliyse base) + seçili profilleri RESUMABLE indir → elevated finalize.
/// force_full=true → "Onar/Yeniden Kur": exe/sağlık ne olursa olsun TAM yeniden kurulum.
fn run_install_core(
    profiles: &[String],
    manifest_url: &str,
    force_full: bool,
    progress: &dyn Fn(Upd),
) -> Result<Dl, String> {
    progress(Upd {
        pct: 0,
        label: "Sürüm bilgisi alınıyor…".into(),
        state: "downloading".into(),
        downloaded: 0,
        total: 0,
        speed: 0.0,
    });
    let manifest = fetch_manifest(manifest_url)?;

    let dl = data_dir().join("downloads");
    fs::create_dir_all(&dl).map_err(|e| e.to_string())?;

    let exe_present = backend_exe_present();
    let already: Vec<String> = fs::read_to_string(marker())
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default();

    // TAM (yıkıcı) kurulum YALNIZCA:
    //  - force_full (kullanıcı 'Onar' dedi), VEYA
    //  - exe hiç yok (taze makine), VEYA
    //  - marker boş/yok VE PemfBackend servisi YOK → önceki kurulum gerçekten yarım kaldı (base çıkmış
    //    ama setup_services patlamış = exe var / marker yok / servis yok) → tam onarım gerek.
    // Servis-varlığı KASITEN sağlık-probu yerine kullanılır: kurulu-ama-yavaş-açılan backend'in servisi
    // VARDIR → yıkılmaz (sağlık-probunun ~10s zamanlaması, kurulu backend'i yanlışlıkla 'ölü' sanamaz).
    let need_full =
        force_full || !exe_present || (already.is_empty() && !backend_service_exists());

    // İndirilecekler (comps) + marker'a yazılacak GERÇEKTEN kurulu profiller (resolved).
    // Manifest'te olmayan seçili profil ATLANIR → yalancı 'kurulu' işaretlenmesi önlenir.
    let mut comps: Vec<(String, &Component, String)> = Vec::new();
    if need_full {
        comps.push(("base.zip".into(), &manifest.base, "Uygulama".into()));
    }
    let mut resolved: Vec<String> = Vec::new();
    let mut missing: Vec<String> = Vec::new();
    for p in profiles {
        // Zaten kurulu profil → modelleri ProgramData'da mevcut, YENİDEN İNDİRME (tam onarımda bile:
        // onarım backend'i/base'i tazeler, modeller korunur → ~1.3GB base, 3.5GB değil). Kurulu say.
        if already.contains(p) {
            if !resolved.contains(p) {
                resolved.push(p.clone());
            }
            continue;
        }
        if let Some(c) = manifest.profiles.get(p) {
            let name = match p.as_str() {
                "home" => "Ev Sahibi",
                "vet" => "Veteriner",
                "research" => "Araştırma",
                _ => p,
            };
            comps.push((format!("{p}.zip"), c, format!("{name} modelleri")));
            if !resolved.contains(p) {
                resolved.push(p.clone());
            }
        } else {
            // Seçili ama ne kurulu ne manifest'te → indirilemez. SESSİZ 'kurulu' işaretleme YOK.
            missing.push(p.clone());
        }
    }

    // Manifest'te bulunmayan seçili profil varsa YÜKSEK SESLE hata ver (yanlış 'Tamamlandı' + hayali
    // AI yeteneği yerine). Tıbbi cihazda 'kurulu ama modelleri yok' sessiz güvencesi kabul edilemez.
    if !missing.is_empty() {
        return Err(format!(
            "Seçilen profil(ler) sunucu paket listesinde yok: {}. Lütfen bu profili çıkarıp tekrar deneyin veya daha sonra deneyin.",
            missing.join(", ")
        ));
    }

    // Marker = already ∪ resolved — TAM kurulumda BİLE: wipe yalnız Program Files'ı siler, ProgramData
    // modelleri KALIR → önceden kurulu profiller diskte durur, marker'dan DÜŞÜRÜLMEZ (aksi=gereksiz GB'ler).
    let final_set: Vec<String> = {
        let mut s = already.clone();
        for p in &resolved {
            if !s.contains(p) {
                s.push(p.clone());
            }
        }
        s
    };

    // İndirilecek yeni bileşen yok (tüm seçilenler zaten kurulu). Marker'ı güncelle; sonra arayüz
    // GERÇEKTEN çalışıyor mu bak — çalışmıyorsa YIKMADAN 'Onar' öner (yanlış 'Tamamlandı' verme).
    // (Yalnız burada probe: normal artımlı eklemede gereksiz sağlık-probu yapılmaz.)
    if comps.is_empty() {
        save_installed(&final_set).map_err(|e| e.to_string())?;
        if backend_healthy() {
            return Ok(Dl::Done);
        }
        return Err(
            "Uygulama kurulu görünüyor ancak arayüz (localhost:8000) yanıt vermiyor. 'Onar' ile yeniden kurabilir ya da bilgisayarı yeniden başlatabilirsiniz."
                .into(),
        );
    }

    let total: u64 = comps.iter().map(|(_, c, _)| c.size).sum::<u64>().max(1);
    let mut base_done: u64 = 0;
    for (fname, comp, label) in &comps {
        let finalp = dl.join(fname);
        let part = dl.join(format!("{fname}.part"));
        match download_to(comp, &part, &finalp, base_done, total, &format!("{label} indiriliyor"), progress)? {
            Dl::Done => base_done += comp.size,
            Dl::Cancelled => return Ok(Dl::Cancelled),
        }
    }

    progress(Upd {
        pct: 99,
        label: "Kuruluyor (yönetici izni gerekebilir)…".into(),
        state: "installing".into(),
        downloaded: total,
        total,
        speed: 0.0,
    });
    // resolved = zip'i indirilmiş/kurulu profiller (finalize Test-Path ile indirilmemişleri atlar).
    finalize_install(&resolved, need_full)?;
    let _ = fs::remove_dir_all(&dl);
    save_installed(&final_set).map_err(|e| e.to_string())?;
    Ok(Dl::Done)
}

/// start_install re-entrancy kilidini (INSTALLING) thread çıkışında (panik dahil) serbest bırakır.
struct InstallGuard;
impl Drop for InstallGuard {
    fn drop(&mut self) {
        INSTALLING.store(false, Ordering::SeqCst);
    }
}

#[tauri::command]
fn start_install(app: AppHandle, profiles: Vec<String>, manifest: String, force_full: Option<bool>) {
    // Re-entrancy koruması: zaten bir kurulum sürüyorsa yok say (çift-emit/çift-thread aynı
    // .part/finalize.ps1/finalize.result'a yazıp bozmasın; iki UAC istemi çıkmasın).
    if INSTALLING
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
        return;
    }
    // Yeni/başlat/devam → bayrakları sıfırla (tek thread; race yok).
    PAUSED.store(false, Ordering::Relaxed);
    CANCELLED.store(false, Ordering::Relaxed);
    let force = force_full.unwrap_or(false); // true = Onar/Yeniden Kur (tam kurulum zorla)
    thread::spawn(move || {
        // Çıkışta (normal/hata/panik) INSTALLING'i serbest bırak → sonraki kurulum başlayabilsin.
        let _install_guard = InstallGuard;
        let url = std::env::var("PEMF_MANIFEST_URL").unwrap_or(manifest);
        let app_p = app.clone();
        let emit = move |u: Upd| {
            let _ = app_p.emit(
                "install://progress",
                Progress {
                    percent: u.pct.min(100),
                    label: u.label,
                    state: u.state,
                    done: false,
                    error: None,
                    downloaded_mb: u.downloaded / 1_048_576,
                    total_mb: u.total / 1_048_576,
                    speed_mbps: (u.speed * 10.0).round() / 10.0,
                },
            );
        };
        let send = |percent: u32, label: &str, state: &str, done: bool, error: Option<String>| {
            let _ = app.emit(
                "install://progress",
                Progress {
                    percent,
                    label: label.into(),
                    state: state.into(),
                    done,
                    error,
                    downloaded_mb: 0,
                    total_mb: 0,
                    speed_mbps: 0.0,
                },
            );
        };
        match run_install_core(&profiles, &url, force, &emit) {
            Ok(Dl::Done) => send(100, "Tamamlandı", "done", true, None),
            Ok(Dl::Cancelled) => {
                let _ = fs::remove_dir_all(data_dir().join("downloads")); // iptalde ilerlemeyi temizle
                send(0, "İptal edildi", "cancelled", true, None);
            }
            Err(e) => send(0, "Hata", "error", true, Some(e)),
        }
    });
}

#[tauri::command]
fn pause_install() {
    PAUSED.store(true, Ordering::Relaxed);
}

#[tauri::command]
fn resume_install() {
    PAUSED.store(false, Ordering::Relaxed);
}

#[tauri::command]
fn cancel_install() {
    CANCELLED.store(true, Ordering::Relaxed);
    PAUSED.store(false, Ordering::Relaxed); // duraklamışsa uyandır → iptali görsün
}

#[tauri::command]
fn launch_app(url: String) -> Result<(), String> {
    Command::new("cmd")
        .creation_flags(CREATE_NO_WINDOW)
        .args(["/C", "start", "", &url])
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// Microsoft Edge (msedge.exe) tam yolu — Windows'ta her zaman kurulu. `--app` chromeless penceresi için.
fn edge_path() -> Option<String> {
    let mut candidates = vec![
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe".to_string(),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe".to_string(),
    ];
    // Per-user kurulum da dene (LTSC/debloat makinelerde makine-geneli yol olmayabilir → aksi halde
    // chromeless pencere yerine varsayılan tarayıcı sekmesine düşerdi).
    if let Ok(la) = std::env::var("LOCALAPPDATA") {
        candidates.push(format!(r"{la}\Microsoft\Edge\Application\msedge.exe"));
    }
    candidates.into_iter().find(|p| Path::new(p).exists())
}

/// Uygulamayı KENDİ chromeless penceresinde açar (Edge `--app`: URL çubuğu/sekme YOK → app gibi). Gerçek
/// tarayıcı motoru → yerel backend'e (loopback) erişebilir + kamera native izin akışıyla çalışır.
/// Edge yoksa yedek: varsayılan tarayıcıda sekme.
fn launch_app_window(url: &str) {
    if let Some(edge) = edge_path() {
        if Command::new(&edge)
            .creation_flags(CREATE_NO_WINDOW)
            .arg(format!("--app={url}"))
            .spawn()
            .is_ok()
        {
            return;
        }
    }
    // Yedek: varsayılan tarayıcı (sekme).
    let _ = Command::new("cmd")
        .creation_flags(CREATE_NO_WINDOW)
        .args(["/C", "start", "", url])
        .spawn();
}

/// "Başlat" → uygulamayı chromeless app penceresinde aç. ÖNCE backend'in hazır olmasını bekle
/// (reboot sonrası servis geç açılırsa app boş/hata sayfası yerine hazır arayüze açılsın). Süre
/// dolarsa "backend-not-ready" Err → frontend kullanıcıya "servis hazır değil" mesajı gösterir.
/// async + spawn_blocking: 90sn'ye kadar bekleme UI'yi DONDURMASIN (check_client_update ile aynı desen).
#[tauri::command]
async fn open_app(url: String) -> Result<(), String> {
    let ready = tauri::async_runtime::spawn_blocking(|| wait_backend_ready(Duration::from_secs(90)))
        .await
        .unwrap_or(false);
    if ready {
        launch_app_window(&url);
        Ok(())
    } else {
        Err("backend-not-ready".into())
    }
}

// ---- Client SELF-UPDATE (launcher'ın kendini güncellemesi) ----
// client-latest.json: { "version": "1.3.1", "sha256": "<setup.exe sha256>", "notes": "...", "url": "<https setup.exe>" }
#[derive(Deserialize)]
struct ClientUpdate {
    version: String,
    #[serde(default)]
    sha256: String,
    #[serde(default)]
    notes: String,
    url: String,
}
#[derive(Serialize)]
struct ClientUpdateOut {
    version: String,
    sha256: String,
    notes: String,
    url: String,
}

/// Sürüm parçaları: baştaki 'v' + ön-sürüm/build son-eki ('-','+' vb.) atılır, her parçanın baştaki
/// rakam dizisi alınır. Parçalanamayan (rakamsız) parça → None (güvenilmez → güncelleme yok).
fn ver_parts(s: &str) -> Option<Vec<u32>> {
    let s = s.trim().trim_start_matches(['v', 'V']);
    let mut out = Vec::new();
    for part in s.split('.') {
        let digits: String = part.trim().chars().take_while(|c| c.is_ascii_digit()).collect();
        if digits.is_empty() {
            return None;
        }
        out.push(digits.parse().unwrap_or(0));
    }
    if out.is_empty() {
        return None;
    }
    Some(out)
}

/// a > b (semver benzeri). Herhangi bir sürüm parçalanamıyorsa false (yanlış-güncelleme/downgrade önlenir).
fn ver_gt(a: &str, b: &str) -> bool {
    let (pa, pb) = match (ver_parts(a), ver_parts(b)) {
        (Some(x), Some(y)) => (x, y),
        _ => return false,
    };
    for i in 0..pa.len().max(pb.len()) {
        let x = *pa.get(i).unwrap_or(&0);
        let y = *pb.get(i).unwrap_or(&0);
        if x != y {
            return x > y;
        }
    }
    false
}

fn check_update_blocking(current: &str, url: &str) -> Option<ClientUpdateOut> {
    if !url.starts_with("https://") {
        return None; // yalnız https manifest
    }
    let client = reqwest::blocking::Client::builder()
        .connect_timeout(Duration::from_secs(4))
        .timeout(Duration::from_secs(6)) // açılışı ~6sn'den fazla bekletme (ulaşılamayan host)
        .build()
        .ok()?;
    let txt = client.get(url).send().ok()?.error_for_status().ok()?.text().ok()?;
    let info: ClientUpdate = serde_json::from_str(&txt).ok()?;
    // https-only url + DOLU sha256 + daha yeni sürüm → aksi halde güncelleme yok.
    if info.url.starts_with("https://") && !info.sha256.trim().is_empty() && ver_gt(&info.version, current) {
        Some(ClientUpdateOut { version: info.version, sha256: info.sha256, notes: info.notes, url: info.url })
    } else {
        None
    }
}

/// Açılışta çağrılır: yeni client sürümü var mı? Varsa {version,sha256,notes,url} döner (yoksa null).
#[tauri::command]
async fn check_client_update(current: String, url: String) -> Option<ClientUpdateOut> {
    tauri::async_runtime::spawn_blocking(move || check_update_blocking(&current, &url))
        .await
        .ok()
        .flatten()
}

/// Yeni setup.exe'yi indirir + sha256 DOĞRULAR (manifestteki değerle) → ayrık yardımcı: on-disk hash'i
/// TEKRAR doğrular (TOCTOU penceresini kapatır) → yükleyiciyi sessiz+elevated çalıştırır → SADECE kurulum
/// BAŞARILIYSA (exit 0) client'ı yeniden açar. UAC reddi/başarısızlık → yeniden-açma YOK (kopya pencere/
/// döngü olmaz). https-only + sha256-zorunlu. Kurulu profiller/modeller ProgramData'da → dokunulmaz.
#[tauri::command]
async fn run_client_update(url: String, sha256: String) -> Result<(), String> {
    let client_exe = std::env::current_exe()
        .map(|p| p.display().to_string())
        .unwrap_or_default();
    tauri::async_runtime::spawn_blocking(move || {
        let pid = std::process::id(); // eski client'ı relaunch öncesi kapat (çift-pencere önle, L2)
        if !url.starts_with("https://") {
            return Err("Güncelleme adresi güvenli değil (https gerekli).".into());
        }
        let want = sha256.trim().to_string();
        if want.is_empty() {
            return Err("Güncelleme bütünlük değeri (sha256) eksik.".into());
        }
        // Dosya adına hash son-eki (izole) → paralel/eski artıkla karışmaz.
        let short: String = want.chars().take(16).collect();
        let tmp = std::env::temp_dir().join(format!("PEMFVetClient-Update-{short}.exe"));
        let helper = std::env::temp_dir().join(format!("pemf-client-update-{short}.ps1"));
        // Heartbeat: yardımcı durumu ('elevating'/'done'/'declined'/'failed') buraya yazar; client polling
        // ile okur → yavaş-ama-başarılı kurulumu ('elevating') erken un-stick etmez (watchdog yarışı yok).
        let status = std::env::temp_dir().join("pemf-client-update.status");
        let _ = fs::remove_file(&status); // stale durumu temizle (önceki denemeden kalmasın)
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(600))
            .build()
            .map_err(|e| e.to_string())?;
        let bytes = client
            .get(&url)
            .send()
            .map_err(|e| e.to_string())?
            .error_for_status()
            .map_err(|e| e.to_string())?
            .bytes()
            .map_err(|e| e.to_string())?;
        if bytes.len() < 200_000 {
            return Err("Güncelleme dosyası eksik indirildi.".into());
        }
        // BÜTÜNLÜK: indirilen baytların sha256'sı manifest ile eşleşmeli (imzasız ama hash-korumalı OTA).
        let actual = {
            let mut h = Sha256::new();
            h.update(&bytes);
            format!("{:x}", h.finalize())
        };
        if !actual.eq_ignore_ascii_case(&want) {
            return Err("Güncelleme bütünlük doğrulaması başarısız (sha256 uyuşmadı).".into());
        }
        fs::write(&tmp, &bytes).map_err(|e| e.to_string())?;

        // Yardımcı: on-disk dosyayı TEKRAR hash'le (TOCTOU) → eşleşirse sessiz kur (tek UAC) → SADECE
        // başarılı kurulumda (exit 0) client'ı yeniden aç. Reddedilirse/başarısızsa yeniden-açma YOK.
        let ps = format!(
            "$ErrorActionPreference='SilentlyContinue'\r\n\
             $st='{status}'\r\n\
             Set-Content -LiteralPath $st -Value 'elevating' -Force\r\n\
             Start-Sleep -Milliseconds 900\r\n\
             $h = (Get-FileHash -Algorithm SHA256 -LiteralPath '{setup}').Hash\r\n\
             if ($h -ne '{hash}') {{ Set-Content -LiteralPath $st -Value 'failed' -Force; Remove-Item '{setup}' -Force; exit 1 }}\r\n\
             $ok = $false\r\n\
             try {{ $p = Start-Process -FilePath '{setup}' -ArgumentList '/S' -Verb RunAs -Wait -PassThru -ErrorAction Stop; $ok = ($p.ExitCode -eq 0) }} catch {{ $ok = $false }}\r\n\
             if ($ok) {{ Set-Content -LiteralPath $st -Value 'done' -Force }} else {{ Set-Content -LiteralPath $st -Value 'declined' -Force }}\r\n\
             Start-Sleep -Milliseconds 1200\r\n\
             if ($ok) {{ Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 400; if (Test-Path '{cexe}') {{ Start-Process -FilePath '{cexe}' }} }}\r\n\
             Remove-Item '{setup}' -Force -ErrorAction SilentlyContinue\r\n",
            status = psq(&status.display().to_string()),
            setup = psq(&tmp.display().to_string()),
            hash = psq(&want.to_uppercase()),
            cexe = psq(&client_exe),
            pid = pid
        );
        fs::write(&helper, ps).map_err(|e| e.to_string())?;

        // Ayrık başlat: helper powershell'dir; installer yalnız client exe'sini kapatır, helper yaşar.
        Command::new("powershell")
            .creation_flags(CREATE_NO_WINDOW)
            .args(["-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File"])
            .arg(&helper)
            .spawn()
            .map_err(|e| e.to_string())?;
        Ok::<(), String>(())
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Self-update yardımcısının durumu: ''(yok) / elevating / done / declined / failed.
/// Client 'updating' ekranında bunu polling ile okur → 'elevating'de bekler (yavaş kurulum), aksi
/// halde normale döner (watchdog zaman-yarışı yerine gerçek duruma bakar).
#[tauri::command]
fn client_update_status() -> String {
    let p = std::env::temp_dir().join("pemf-client-update.status");
    fs::read_to_string(&p).map(|s| s.trim().to_string()).unwrap_or_default()
}

#[tauri::command]
fn create_shortcuts(url: String) -> Result<(), String> {
    let desktop =
        PathBuf::from(std::env::var("USERPROFILE").map_err(|e| e.to_string())?).join("Desktop");
    fs::create_dir_all(&desktop).ok();

    // PEMF (kalp) ikonunu kalıcı bir yola yaz — kısayol ikonu bunu gösterir.
    fs::create_dir_all(data_dir()).ok();
    let ico = data_dir().join("pemf_app.ico");
    let _ = fs::write(&ico, APP_ICON);

    // Kısayol artık TARAYICI açan .url değil → client'i `--open-app` ile başlatan .lnk. Böylece uygulama
    // KENDİ native penceresinde açılır (Chrome sekmesi değil). WScript.Shell ile .lnk oluşturulur.
    let client_exe = std::env::current_exe().map(|p| p.display().to_string()).unwrap_or_default();
    let wd = std::path::Path::new(&client_exe)
        .parent()
        .map(|p| p.display().to_string())
        .unwrap_or_default();
    let lnk = desktop.join("PEMF Vet.lnk");
    let ps_path = data_dir().join("mk_shortcut.ps1");
    let ps = format!(
        "$ws = New-Object -ComObject WScript.Shell\r\n\
         $s = $ws.CreateShortcut('{lnk}')\r\n\
         $s.TargetPath = '{exe}'\r\n\
         $s.Arguments = '--open-app \"{url}\"'\r\n\
         $s.IconLocation = '{ico}'\r\n\
         $s.WorkingDirectory = '{wd}'\r\n\
         $s.Description = 'PEMF Vet'\r\n\
         $s.Save()\r\n",
        lnk = psq(&lnk.display().to_string()),
        exe = psq(&client_exe),
        url = psq(&url),
        ico = psq(&ico.display().to_string()),
        wd = psq(&wd),
    );
    fs::write(&ps_path, ps).map_err(|e| e.to_string())?;
    let _ = Command::new("powershell")
        .creation_flags(CREATE_NO_WINDOW)
        .args(["-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File"])
        .arg(&ps_path)
        .status();

    // Eski tarayıcı-kısayollarını temizle → kullanıcı tek, doğru (native-açan) kısayol görsün.
    let _ = fs::remove_file(desktop.join("PEMF Vet.url"));
    let _ = fs::remove_file(desktop.join("PEMF Vet Client.lnk"));
    // Kısayol GERÇEKTEN oluştu mu? Oluşmadıysa Err → frontend "kısayol eklendi" demesin (COM/PS hatası
    // eskiden sessizce yutuluyordu → kullanıcı ikon göremeyip sebebini bilemiyordu).
    if lnk.exists() {
        Ok(())
    } else {
        Err("Masaüstü kısayolu oluşturulamadı.".into())
    }
}

#[tauri::command]
fn is_installed() -> bool {
    marker().exists()
}

#[tauri::command]
fn installed_profiles() -> Vec<String> {
    fs::read_to_string(marker())
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

// ============================================================================
//  macOS/Linux DALI — Windows kurulum akışı (native frozen backend) Mac/Linux'ta
//  çalışmaz; onlar PEMF'i DOCKER ile koşar. Bu komutlar Docker'ı yönetir
//  (durum/başlat/durdur/paket-bul). Frontend os=="macos" || "linux" iken çağırır.
//  Platform-özel açış (open/xdg-open) open_native() ile soyutlandı (cfg).
// ============================================================================

/// İşletim sistemi ("macos" | "windows" | "linux") — frontend dallanması için.
#[tauri::command]
fn get_os() -> String {
    std::env::consts::OS.to_string()
}

/// Docker durumu: "not_installed" (komut yok) | "not_running" (daemon kapalı) | "running".
#[tauri::command]
fn mac_docker_status() -> String {
    match Command::new("docker").arg("info").output() {
        Ok(o) if o.status.success() => "running".to_string(),
        Ok(_) => "not_running".to_string(),
        Err(_) => "not_installed".to_string(),
    }
}

/// PEMF Docker paketini (docker-compose.dist.yml içeren klasör) yaygın konumlarda bul.
fn mac_find_pkg() -> Option<PathBuf> {
    let home = std::env::var("HOME").ok()?;
    for c in [
        "Downloads/PEMF-Mac-Paket",
        "Downloads/PEMF-Linux-Paket",
        "Desktop/PEMF-Mac-Paket",
        "Desktop/PEMF-Linux-Paket",
        "PEMF-Mac-Paket",
        "PEMF-Linux-Paket",
        "Downloads/PEMF-Docker",
    ] {
        let p = Path::new(&home).join(c);
        if p.join("docker-compose.dist.yml").exists() {
            return Some(p);
        }
    }
    None
}

/// Paket klasörü yolu ("" = bulunamadı).
#[tauri::command]
fn mac_package_dir() -> String {
    mac_find_pkg()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_default()
}

/// Tarayıcıda URL aç — platforma göre (macOS: open, Linux: xdg-open). Windows'ta çağrılmaz.
fn open_native(url: &str) {
    #[cfg(target_os = "macos")]
    {
        let _ = Command::new("open").arg(url).spawn();
    }
    #[cfg(target_os = "linux")]
    {
        let _ = Command::new("xdg-open").arg(url).spawn();
    }
    #[cfg(not(any(target_os = "macos", target_os = "linux")))]
    {
        let _ = url;
    }
}

/// Docker'ı başlat: macOS → Docker Desktop uygulaması; Linux → docker servisi (izin yoksa kullanıcı elle).
#[tauri::command]
fn mac_open_docker() -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        Command::new("open").args(["-a", "Docker"]).output().map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "linux")]
    {
        let _ = Command::new("systemctl").args(["--user", "start", "docker-desktop"]).output();
        let _ = Command::new("systemctl").args(["start", "docker"]).output();
    }
    Ok(())
}

/// Stack'i başlat: (ilk sefer) imajları yükle → docker compose up -d → tarayıcı aç.
#[tauri::command]
fn mac_start() -> Result<String, String> {
    let dir = mac_find_pkg()
        .ok_or_else(|| "PEMF paketi bulunamadı (Downloads/PEMF-Mac-Paket).".to_string())?;

    // İmajlar yüklü değilse pemf-images.tar.gz'den yükle (ilk sefer ~1-2 dk).
    let have_img = Command::new("docker")
        .args(["image", "inspect", "pemf-backend:latest"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);
    let tar = dir.join("pemf-images.tar.gz");
    if !have_img && tar.exists() {
        let load = Command::new("docker")
            .arg("load")
            .arg("-i")
            .arg(&tar)
            .current_dir(&dir)
            .output()
            .map_err(|e| e.to_string())?;
        if !load.status.success() {
            return Err(format!(
                "İmaj yükleme başarısız: {}",
                String::from_utf8_lossy(&load.stderr).trim()
            ));
        }
    }

    let up = Command::new("docker")
        .args(["compose", "-f", "docker-compose.dist.yml", "up", "-d"])
        .current_dir(&dir)
        .output()
        .map_err(|e| e.to_string())?;
    if !up.status.success() {
        return Err(String::from_utf8_lossy(&up.stderr).trim().to_string());
    }

    open_native("http://localhost:8080");
    Ok("started".to_string())
}

/// Stack'i durdur (docker compose down).
#[tauri::command]
fn mac_stop() -> Result<(), String> {
    let dir = mac_find_pkg().ok_or_else(|| "PEMF paketi bulunamadı.".to_string())?;
    Command::new("docker")
        .args(["compose", "-f", "docker-compose.dist.yml", "down"])
        .current_dir(&dir)
        .output()
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// Stack (compose) ayakta mı? docker ps'te 8080 portu var mı? Frontend gerçek çalışıyor-durumunu
/// böyle alır (yerel state yerine → pencere yeniden açılınca da doğru, L23). macOS-only (Windows'ta çağrılmaz).
#[tauri::command]
fn mac_running() -> bool {
    Command::new("docker")
        .args(["ps", "--format", "{{.Ports}}"])
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).contains(":8080"))
        .unwrap_or(false)
}

/// Headless E2E: PEMF_SELFTEST=1 (+ PEMF_SELFTEST_PROFILES=home,vet). GUI açmaz.
fn selftest() {
    let url = std::env::var("PEMF_MANIFEST_URL").unwrap_or_default();
    let profiles: Vec<String> = std::env::var("PEMF_SELFTEST_PROFILES")
        .unwrap_or_else(|_| "home,vet,research".into())
        .split(',')
        .filter(|s| !s.is_empty())
        .map(|s| s.trim().to_string())
        .collect();
    let pf = |u: Upd| println!("[{:3}%] {} ({}) {:.1} MB/s", u.pct, u.label, u.state, u.speed);
    match run_install_core(&profiles, &url, false, &pf) {
        Ok(Dl::Done) => println!("SELFTEST OK"),
        Ok(_) => println!("SELFTEST DURDU (pause/cancel)"),
        Err(e) => {
            eprintln!("SELFTEST FAIL: {e}");
            std::process::exit(1);
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    if std::env::var("PEMF_SELFTEST").is_ok() {
        selftest();
        return;
    }
    // Denetim Masası "Kaldır" → client'ı --uninstall-app ile çağırır (GUI açmadan kaldırır).
    if std::env::args().any(|a| a == "--uninstall-app") {
        let _ = do_uninstall_app();
        return;
    }
    // Masaüstü kısayolu "--open-app <url>" → launcher GUI'sini AÇMA, doğrudan uygulamayı chromeless app
    // penceresinde (Edge --app) aç + çık. URL yoksa 127.0.0.1:8000'e düş.
    {
        let args: Vec<String> = std::env::args().collect();
        if let Some(pos) = args.iter().position(|a| a == "--open-app") {
            let url = args
                .get(pos + 1)
                .cloned()
                .unwrap_or_else(|| "http://127.0.0.1:8000".to_string());
            // Backend hazır olana dek bekle (reboot sonrası servis geç açılırsa çerçevesiz hata
            // ekranını önle). Kısayol yolunda GUI yok → süre dolsa bile yine de aç.
            let _ = wait_backend_ready(Duration::from_secs(90));
            launch_app_window(&url);
            return;
        }
    }
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            start_install,
            pause_install,
            resume_install,
            cancel_install,
            uninstall_app,
            launch_app,
            open_app,
            create_shortcuts,
            is_installed,
            installed_profiles,
            get_os,
            check_client_update,
            run_client_update,
            client_update_status,
            mac_docker_status,
            mac_package_dir,
            mac_open_docker,
            mac_start,
            mac_stop,
            mac_running
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
