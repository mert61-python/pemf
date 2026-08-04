//! Backend sürecini başlatma + hazır olmasını bekleme + tarayıcıyı açma.
//!
//! Sessiz başarısızlık YASAK: eski akışta backend açılmazsa kullanıcı boş bir
//! tarayıcı sekmesiyle kalıyordu. Burada `/api/health` 200 dönene kadar beklenir;
//! zaman aşımında süreç öldürülür ve stderr çağırana verilir.

use std::io;
use std::net::{Ipv4Addr, SocketAddrV4, TcpListener, TcpStream};
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

use crate::install;

#[derive(Debug, thiserror::Error)]
pub enum BackendError {
    #[error("backend çalıştırılabiliri bulunamadı: {0}")]
    NotFound(String),
    #[error("backend başlatılamadı: {0}")]
    Spawn(#[source] io::Error),
    #[error("backend {timeout_s} sn içinde hazır olmadı (port {port}). Son çıktı:\n{tail}")]
    Timeout { port: u16, timeout_s: u64, tail: String },
    #[error("backend başlarken sonlandı (çıkış kodu {code:?}). Son çıktı:\n{tail}")]
    Exited { code: Option<i32>, tail: String },
    #[error("boş port bulunamadı ({start}..{end})")]
    NoFreePort { start: u16, end: u16 },
}

/// Port GERÇEKTEN boş mu? — backend'in bağlanacağı adresle UYUMLU kontrol.
///
/// ⚠️ DENETİM 2026-08-04: eskiden yalnız `TcpListener::bind(127.0.0.1:port)` deneniyordu; oysa
/// backend `0.0.0.0`'a bağlanır (`backend_service.py --host` varsayılanı — mobil istemciler LAN'dan
/// erişsin diye). Windows'ta bu ikisi ÇAKIŞMAZ ve bu ampirik olarak doğrulandı:
///   biri `0.0.0.0:8000`'i DİNLERKEN → `bind(127.0.0.1:8000)` BAŞARILI, `bind(0.0.0.0:8000)` RED.
/// Yani orada yetim bir backend (ya da başka bir web servisi) varken launcher portu "boş" sanıp
/// 8000'i seçiyor, uvicorn `0.0.0.0:8000`'de WinError 10048 alıp ÖLÜYOR, `wait_for_health` ~180 sn
/// boşuna bekleyip genel bir hata gösteriyordu. Klinikte: cihaz açılmıyor, mesaj da yol göstermiyor.
/// (`kill_stray_backends` her zaman başaramaz — başka oturumun yükseltilmiş süreci kalabilir.)
///
/// Düzeltme neden `bind(0.0.0.0)` DEĞİL: launcher bugün hiçbir sokete bağlanmıyor; loopback dışı
/// bir `listen` Windows Güvenlik Duvarı'nda YENİ bir izin istemi doğurur (klinik kurulumunda
/// istenmeyen bir sürpriz). Bunun yerine ÖNCE bağlanma-yoklaması: `0.0.0.0`'a bağlı bir dinleyici
/// loopback üzerinden de bağlantı kabul eder → connect başarılıysa port MEŞGULDÜR.
///
/// Kalan boşluk (bilinçli): YALNIZCA belirli bir LAN IP'sine (ör. 192.168.1.5:8000) bağlı bir
/// dinleyici loopback'ten görünmez; o durumda uvicorn yine 10048 alır. Bu senaryo bu üründe
/// pratikte görülmedi ve yakalamak için loopback-dışı `listen` gerekirdi (güvenlik duvarı istemi).
fn port_is_free(port: u16) -> bool {
    let addr = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    // 1) Dinleyen biri var mı? (0.0.0.0'a bağlı dinleyiciyi de yakalar)
    if TcpStream::connect_timeout(&addr.into(), Duration::from_millis(150)).is_ok() {
        return false;
    }
    // 2) Bizim de bağlanabildiğimizi teyit et (TIME_WAIT vb. durumları eler).
    TcpListener::bind(addr).is_ok()
}

/// `start`'tan itibaren bağlanabilen ilk portu bulur.
/// Klinik makinesinde 8000 sıkça meşguldür (başka servis) → sabit port varsaymayız.
pub fn find_free_port(start: u16, tries: u16) -> Result<u16, BackendError> {
    for port in start..start.saturating_add(tries) {
        if port_is_free(port) {
            return Ok(port);
        }
    }
    Err(BackendError::NoFreePort {
        start,
        end: start.saturating_add(tries),
    })
}

/// Tek-seferlik sağlık nonce'u üret (DENETİM 2026-08-04, P2 #13).
///
/// Yeni bağımlılık eklemeden OS entropisi: `RandomState` her örneklemede işletim sisteminden
/// tohumlanır; buna süreç kimliği ve nanosaniye çözünürlüklü zaman karıştırılıp SHA-256'dan
/// geçirilir. Nonce'un tek gereksinimi, portu kapmaya çalışan YEREL bir sürecin onu ~180 sn'lik
/// başlatma penceresinde TAHMİN EDEMEMESİDİR (değer çocuk sürecin ortamındadır; aynı kullanıcı
/// zaten her şeyi yapabilir — korunan şey FARKLI kullanıcı/düşük-yetkili süreçtir).
pub fn generate_health_nonce() -> String {
    use sha2::{Digest, Sha256};
    use std::collections::hash_map::RandomState;
    use std::hash::{BuildHasher, Hasher};

    let mut h = Sha256::new();
    for i in 0..4u64 {
        let mut hh = RandomState::new().build_hasher();
        hh.write_u64(i.wrapping_mul(0x9E37_79B9_7F4A_7C15));
        h.update(hh.finish().to_le_bytes());
    }
    h.update(std::process::id().to_le_bytes());
    if let Ok(d) = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH) {
        h.update(d.as_nanos().to_le_bytes());
    }
    h.finalize().iter().fold(String::with_capacity(64), |mut s, b| {
        use std::fmt::Write;
        let _ = write!(s, "{b:02x}");
        s
    })
}

/// `/api/health` hazır olana kadar bekler.
///
/// `expected_nonce = Some(n)`: yanıt 200 OLMASI YETMEZ — gövdedeki `launcherNonce` alanı `n` ile
/// EŞLEŞMELİDİR. Bu, portu bizden önce kapmış bir sürecin "hazır" sanılmasını engeller
/// (bkz. `install::ENV_HEALTH_NONCE`). `None`: eski davranış (yalnız HTTP 200) — nonce'u
/// yansıtmayan ESKİ base.zip'ler için geriye uyum.
pub fn wait_for_health(port: u16, timeout: Duration, expected_nonce: Option<&str>) -> bool {
    let url = health_url(port);
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        let ok = ureq::get(&url)
            .timeout(Duration::from_secs(2))
            .call()
            .ok()
            .filter(|r| r.status() == 200)
            .map(|r| match expected_nonce {
                None => true, // eski backend: yalnız 200
                Some(want) => r
                    .into_string()
                    .ok()
                    .and_then(|b| serde_json::from_str::<serde_json::Value>(&b).ok())
                    .and_then(|v| {
                        v.get("launcherNonce")
                            .and_then(|n| n.as_str().map(str::to_owned))
                    })
                    .is_some_and(|got| got == want),
            })
            .unwrap_or(false);
        if ok {
            return true;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    false
}

pub fn health_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}/api/health")
}

/// `<install_root>/backend.port` içeriğini GÜVENLE oku. Rakam-dışı / aralık-dışı → `None`.
pub fn read_backend_port(install_root: &Path) -> Option<u16> {
    let txt = std::fs::read_to_string(install_root.join("backend.port")).ok()?;
    txt.trim().parse::<u16>().ok().filter(|p| *p > 0)
}

/// Bu portta GERÇEKTEN bir PEMF backend'i mi var? (`/api/health` gövdesinde `"service":"PEMF-Vet"`)
///
/// `wait_for_health` yalnız HTTP 200'e bakar; KENDİ başlattığımız süreci beklerken bu yeterlidir.
/// Ama BAŞKASININ başlattığı bir backend'i sahiplenmeden önce kimliğini doğrulamak gerekir —
/// aynı porta bağlanmış ilgisiz bir yerel servis de 200 dönebilir.
pub fn probe_pemf_backend(port: u16) -> bool {
    ureq::get(&health_url(port))
        .timeout(Duration::from_secs(2))
        .call()
        .ok()
        .filter(|r| r.status() == 200)
        .and_then(|r| r.into_string().ok())
        .and_then(|b| serde_json::from_str::<serde_json::Value>(&b).ok())
        .and_then(|v| v.get("service").and_then(|s| s.as_str().map(str::to_owned)))
        .is_some_and(|s| s == "PEMF-Vet")
}

/// Kurulu backend ZATEN çalışıyor mu? Çalışıyorsa portunu döndürür.
///
/// DENETİM 2026-08-04: launcher yalnız KENDİ `state.proc`'una bakıyordu. Sistemde çalışan bir
/// backend varken "Başlat" İKİNCİ bir süreç açıyordu (`find_free_port` meşgul 8000'i atlayıp 8001
/// veriyor; backend tarafında da tek-instance kilidi YOK). İki süreç aynı hasta DB'sine ve aynı
/// COM/MQTT kaynağına talip oluyor; seri port Windows'ta exclusive olduğundan ikincisi donanımı
/// SÜREMEZ ama UI'yı "boşta/temiz" gösterir → veteriner donanımı KONTROL ETMEYEN bir ekrana bakar.
/// Üstelik `backend.port` üzerine yazılıp ilk sürecin E-stop adresi kayboluyordu.
/// Artık: çalışan varsa İKİNCİSİNİ BAŞLATMA, mevcut olanı SAHİPLEN.
pub fn detect_running_backend(install_root: &Path) -> Option<u16> {
    // 1) Kayıtlı port — kim başlattıysa yazmıştır.
    if let Some(port) = read_backend_port(install_root) {
        if probe_pemf_backend(port) {
            return Some(port);
        }
    }
    // 2) Port dosyası silinmiş/bayat olabilir → varsayılan portu da yokla.
    if probe_pemf_backend(install::DEFAULT_PORT) {
        return Some(install::DEFAULT_PORT);
    }
    None
}

pub fn app_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}/")
}

/// Backend'i başlatır ve hazır olana kadar bekler. Hazır olmazsa süreci ÖLDÜRÜR.
pub fn start_and_wait(
    install_root: &Path,
    port: u16,
    timeout: Duration,
) -> Result<Child, BackendError> {
    let exe = install::backend_path(install_root);
    if !exe.exists() {
        return Err(BackendError::NotFound(exe.display().to_string()));
    }

    let mut cmd = Command::new(&exe);
    cmd.arg("--port").arg(port.to_string());
    // Çalışma dizini paketin kendi kökü olmalı: PyInstaller onedir yanındaki
    // _internal/ kaynaklarını göreli çözer.
    if let Some(dir) = exe.parent() {
        cmd.current_dir(dir);
    }
    // DENETİM 2026-08-04 (P2 #13): tek-seferlik nonce → yalnız GERÇEK backend onu yansıtabilir.
    // Kurulu backend nonce'u desteklemiyorsa (eski base.zip, `_internal/VERSION` yok) doğrulama
    // hoşgörülü moda düşer ve mevcut kurulumlar KIRILMAZ; yeni base.zip yayınlanınca
    // KENDİLİĞİNDEN katılaşır (bkz. install::backend_supports_health_nonce).
    let nonce = generate_health_nonce();
    let verify_nonce = install::backend_supports_health_nonce(install_root);
    for (k, v) in install::backend_env(install_root, port, &nonce) {
        cmd.env(k, v);
    }
    // ⚠️ DEADLOCK FIX: backend'in stdout/stderr'ini pipe'layıp DRENAJLAMAMAK (eski hal) tüm servisi
    // kilitliyordu. Backend logging'i HER satırı `sys.stdout`'a da yazar (StreamHandler); pipe okunmadığı
    // için ~saatlerce log sonrası buffer dolunca `stdout.flush()` SÜRESİZ BLOKE olur, Python logging
    // kilidini tutarak asılır → o kilidi bekleyen TÜM AI model yüklemeleri (`_get_or_load_model`) +
    // STM logları + telemetri DEADLOCK (py-spy: CloudSyncWorker `flush`'ta, asyncio_* `logger.info`'da).
    // Backend zaten her şeyi backend_service.log'a yazıyor → stdout/stderr'e İHTİYAÇ YOK. NUL'e yönlendir:
    // flush asla bloke olmaz. (Hazırlık HTTP `/api/health` ile algılanır; başlangıç-hatası teşhisi
    // read_tail → backend_service.log'a bakar.)
    cmd.stdout(Stdio::null()).stderr(Stdio::null());

    // Windows: launcher windowed (konsolsuz) olduğundan, KONSOL-altsistem backend exe'si spawn
    // edilince Windows ona YENİ KONSOL açar → kullanıcıya siyah cmd penceresi görünür. CREATE_NO_WINDOW
    // konsolu hiç açtırmaz (stdout/stderr NUL'e gittiği için ekstra pencere/pipe sorunu da olmaz).
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = cmd.spawn().map_err(BackendError::Spawn)?;

    if wait_for_health(port, timeout, verify_nonce.then_some(nonce.as_str())) {
        return Ok(child);
    }

    // Hazır olmadı: süreç kendi kendine mi öldü, yoksa asılı mı kaldı?
    let exited = child.try_wait().ok().flatten();
    let tail = read_tail(&mut child);
    let _ = child.kill();
    let _ = child.wait();

    Err(match exited {
        Some(status) => BackendError::Exited {
            code: status.code(),
            tail,
        },
        None => BackendError::Timeout {
            port,
            timeout_s: timeout.as_secs(),
            tail,
        },
    })
}

/// Başlangıç-hatası teşhisi. stdout/stderr NUL'e yönlendirildi (drenajsız pipe deadlock'luyordu) →
/// canlı çıktı yok; ayrıntı backend'in kendi günlüğünde. (stderr yine de doluysa son 20 satırı ekle.)
fn read_tail(child: &mut Child) -> String {
    use std::io::Read;
    let mut buf = String::new();
    if let Some(err) = child.stderr.as_mut() {
        let mut raw = Vec::new();
        let _ = err.take(64 * 1024).read_to_end(&mut raw);
        buf = String::from_utf8_lossy(&raw).into_owned();
    }
    let tail: String = {
        let lines: Vec<&str> = buf.lines().rev().take(20).collect();
        lines.into_iter().rev().collect::<Vec<_>>().join("\n")
    };
    let hint = "Ayrıntı için backend günlüğü: %APPDATA%\\PEMF_GUI\\logs\\backend_service.log";
    if tail.trim().is_empty() { hint.to_string() } else { format!("{tail}\n{hint}") }
}

/// Kapanmadan ÖNCE bobinleri güvene al (TIBBİ GÜVENLİK). Hard-kill (child.kill = TerminateProcess)
/// sinyal GÖNDERMEZ → backend'in graceful shutdown'ı (bobin STOP + kuyruk-flush) ÇALIŞMAZ ve
/// bobinler firmware süre-watchdog'u dolana kadar HASTANIN ÜZERİNDE açık kalabilir. Bu çağrı
/// E-stop endpoint'iyle TÜM transport'lardan (STM 1-5 + ESP 6-8) DONANIM STOP tetikler; STM STOP
/// async seri-kuyruğa konduğu için porta yazılsın diye kısa bekler. Best-effort: backend cevap
/// vermese/erişilemese bile çağıran süreci YİNE öldürür (bu adım güvenliği artırır, engellemez).
/// E-stop HTTP bütçesi. DENETİM 2026-08-04: eskiden 3 sn idi; backend AYNI ucu kendi kaynağında
/// "senkron MQTT publish yapar (~7sn worst-case)" diye belgeliyor (`servers/api_server.py`
/// `emergency_stop` yorumu) ve `_estop_one` bobin-başına iki senkron publish yapıyor. 3 sn dolunca
/// ureq isteği bırakıyordu, çağıran hemen `child.kill()` (TerminateProcess) çağırıyordu ve E-stop'u
/// yürüten `asyncio.to_thread` thread'i ORTASINDA ölüyordu. STM bobinleri 1-5 firmware'in 1500 ms
/// ölü-adam devresiyle kurtulur; **ESP bobinleri 6-8'in link-watchdog'u YOKTUR** → yalnızca broker'a
/// ulaşan STOP publish'iyle dururlar. Bu yüzden bütçe backend'in worst-case'inin üstüne çekildi.
const ESTOP_TIMEOUT_S: u64 = 10;
/// Yanıt döndükten SONRA STM STOP'un sender-thread'ce seri porta YAZILMASI için beklenen süre.
/// Backend'in kendi kuyruk-boşaltma deadline'ı 1.5 sn (`backend_service.py`), eski 1200 ms bunun
/// ALTINDAYDI → kuyruk boşalmadan süreç öldürülebiliyordu.
const ESTOP_FLUSH_MS: u64 = 1600;

pub fn safe_stop_coils(port: u16) {
    let url = format!("http://127.0.0.1:{port}/api/hardware/emergency_stop");
    // Backend `{"status":"success|partial|error","confirmed":bool,...}` döner ve "bir transport
    // doğrulanamadı" durumunu BİLEREK bildirir. Eski kod yanıtı `let _ =` ile tamamen atıyordu →
    // "STM durdu ama MQTT yayınlanamadı" sinyali görülmüyordu. Doğrulanmazsa BİR KEZ daha dene:
    // ESP publish'i geçici broker/ağ hatasında sıklıkla ikinci denemede geçer.
    for attempt in 0..2u8 {
        let confirmed = ureq::post(&url)
            .timeout(Duration::from_secs(ESTOP_TIMEOUT_S))
            .call()
            .ok()
            .and_then(|r| r.into_string().ok())
            .and_then(|b| serde_json::from_str::<serde_json::Value>(&b).ok())
            .and_then(|v| v.get("confirmed").and_then(|c| c.as_bool()))
            .unwrap_or(false);
        if confirmed {
            break;
        }
        if attempt == 0 {
            std::thread::sleep(Duration::from_millis(300));
        }
    }
    // Best-effort: doğrulanmasa bile çağıran süreci YİNE öldürür (bu adım güvenliği artırır,
    // engellemez). Doğrulanmadıysa kuyruğun yazılması için tam bütçeyi tanı.
    std::thread::sleep(Duration::from_millis(ESTOP_FLUSH_MS));
}

/// ARTAKALAN (orphan) backend süreçlerini sistem-genelinde durdur.
///
/// SORUN: backend `child.kill()` (Windows TerminateProcess) SİNYALSİZDİR ve ÇOCUK-AĞACINI
/// öldürmez → backend'in spawn ettiği `mosquitto.exe`/`cloudflared.exe` YETİM kalır ve
/// `runtime/.../mosquitto.exe`'yi KİLİTLER. Sonraki kurulum base'i re-extract ederken bu kilitli
/// dosyaya çarpar → "os error 32" (sharing violation). Bu yüzden yeniden-kurulumdan/onarımdan
/// ÖNCE bu üç bundled süreci (+ çocuk-ağaçları) zorla kapatırız. Klinik makinesinde bu isimli
/// süreçler bize aittir. TIBBİ GÜVENLİK: çağırandan ÖNCE safe_stop_coils POST edilmeli.
pub fn kill_stray_backends() {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        for image in ["PEMF_Backend.exe", "mosquitto.exe", "cloudflared.exe"] {
            let mut c = Command::new("taskkill");
            c.args(["/F", "/IM", image, "/T"]); // /T = süreç + çocuk-ağacı
            c.creation_flags(CREATE_NO_WINDOW); // siyah konsol açma
            let _ = c.stdout(Stdio::null()).stderr(Stdio::null()).status();
        }
    }
    #[cfg(not(windows))]
    {
        // DENETİM 2026-08-04: burada `pkill -f <ad>` vardı. `-f` TÜM KOMUT SATIRINDA arar →
        // `tail -f /var/log/mosquitto.log`, `less cloudflared.log`, hatta argümanında bu kelime
        // geçen editör/grep gibi TAMAMEN İLGİSİZ süreçler de öldürülüyordu. Windows kolu zaten
        // `/IM` ile YALNIZ imaj adına bakıyor; Unix kolu bundan çok daha genişti.
        // `-x` = süreç ADI TAM eşleşmeli (komut satırı değil) → Windows `/IM` ile aynı davranış.
        for name in ["PEMF_Backend", "mosquitto", "cloudflared"] {
            let _ = Command::new("pkill")
                .args(["-x", name])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }
    }
}

/// Varsayılan tarayıcıda aç. Başarısızlık ÖLÜMCÜL DEĞİL — çağıran URL'yi gösterebilir.
pub fn open_browser(url: &str) -> io::Result<()> {
    #[cfg(target_os = "macos")]
    let mut cmd = {
        let mut c = Command::new("open");
        c.arg(url);
        c
    };
    #[cfg(target_os = "windows")]
    let mut cmd = {
        // GÜVENLİK: `cmd /C start "" <url>` URL'yi KABUK'a verir → manifest-türevi (zehirli/MITM)
        // bir URL'deki cmd metakarakterleri (&, |, ^) ikinci komut zincirleyip RCE olur.
        // rundll32 FileProtocolHandler URL'yi TEK argüman olarak alır; hiçbir kabuk ayrıştırmaz.
        let mut c = Command::new("rundll32.exe");
        c.args(["url.dll,FileProtocolHandler", url]);
        c
    };
    #[cfg(all(unix, not(target_os = "macos")))]
    let mut cmd = {
        let mut c = Command::new("xdg-open");
        c.arg(url);
        c
    };
    cmd.stdout(Stdio::null()).stderr(Stdio::null()).spawn().map(|_| ())
}

#[cfg(test)]
mod tests {
    use std::io::Write;
    use std::net::TcpStream;

    use super::*;

    #[test]
    fn bos_port_bulunur() {
        let port = find_free_port(48000, 50).unwrap();
        assert!((48000..48050).contains(&port));
    }

    /// ⚠️ DENETİM 2026-08-04 — ASIL SENARYO: backend `0.0.0.0`'a bağlanır, launcher ise
    /// yalnız `127.0.0.1`'i yokluyordu. Windows'ta biri `0.0.0.0:P`'yi DİNLERKEN
    /// `bind(127.0.0.1:P)` BAŞARILI olur (ampirik olarak doğrulandı) → port "boş" sanılır,
    /// uvicorn `0.0.0.0:P`'de WinError 10048 alıp ölür, kullanıcı ~180 sn sonra genel hata görür.
    /// Yetim backend / başka bir web servisi tam olarak bu durumu yaratır.
    #[test]
    fn tum_arayuzlere_bagli_dinleyici_bos_sayilmaz() {
        let ln = TcpListener::bind((Ipv4Addr::UNSPECIFIED, 0)).unwrap();
        let port = ln.local_addr().unwrap().port();

        // Eski kod bu portu "boş" bulup dönerdi; artık MEŞGUL sayılmalı.
        assert!(!port_is_free(port), "0.0.0.0'a bagli dinleyici varken port BOS sayildi");
        assert_ne!(
            find_free_port(port, 1).ok(),
            Some(port),
            "find_free_port mesgul portu dondurdu — backend baslangicta 10048 alir"
        );
        drop(ln);
    }

    #[test]
    fn dolu_port_atlanir() {
        let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let busy = listener.local_addr().unwrap().port();
        let found = find_free_port(busy, 20).unwrap();
        assert_ne!(found, busy, "mesgul port bos sanildi");
    }

    #[test]
    fn url_yardimcilari_dogru_bicimde() {
        assert_eq!(health_url(8123), "http://127.0.0.1:8123/api/health");
        assert_eq!(app_url(8123), "http://127.0.0.1:8123/");
    }

    /// TIBBİ GÜVENLİK: safe_stop_coils, süreç öldürülmeden önce E-stop endpoint'ini POST etmeli.
    /// (Bu çağrı kalkarsa seans sürerken pencere kapanışında bobinler açık kalır.)
    #[test]
    fn safe_stop_coils_estop_endpointini_post_eder() {
        use std::io::Read;
        let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        let (tx, rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            // Boş yoklama bağlantılarını (bkz. `port_is_free`) atlayıp GERÇEK isteği bekle.
            for stream in listener.incoming() {
                let Ok(mut s) = stream else { continue };
                let mut buf = [0u8; 1024];
                let n = s.read(&mut buf).unwrap_or(0);
                if n == 0 {
                    continue;
                }
                // GERÇEK yanıt şekli (servers/api_server.py `emergency_stop`): `confirmed` alanı
                // "her iki transport da doğrulandı" demektir. safe_stop_coils bunu OKUR ve
                // doğrulanmadıysa bir kez daha dener → burada true dönerek tek denemede biter.
                let body = br#"{"status":"success","confirmed":true,"stmStopped":true}"#;
                let _ = write!(
                    s,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    body.len()
                );
                let _ = s.write_all(body);
                let _ = tx.send(String::from_utf8_lossy(&buf[..n]).into_owned());
                break;
            }
        });
        safe_stop_coils(port);
        let req = rx
            .recv_timeout(Duration::from_secs(5))
            .expect("safe_stop_coils E-stop endpoint'ini ÇAĞIRMADI");
        assert!(
            req.starts_with("POST /api/hardware/emergency_stop"),
            "yanlış istek gönderildi: {req}"
        );
    }

    /// TIBBİ GÜVENLİK: backend `confirmed:false` (ör. "STM durdu ama MQTT yayınlanamadı") derse
    /// E-stop TEK denemeyle bırakılmamalı — ESP bobinleri 6-8'in link-watchdog'u YOKTUR, tek
    /// durdurma yolu broker'a ulaşan STOP publish'idir.
    #[test]
    fn dogrulanmayan_estop_yeniden_denenir() {
        use std::io::Read;
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::sync::Arc;

        let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        let hits = Arc::new(AtomicUsize::new(0));
        let hits2 = hits.clone();
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(mut s) = stream else { continue };
                let mut buf = [0u8; 1024];
                let read = s.read(&mut buf).unwrap_or(0);
                // ⚠️ Yalnız GERÇEK istekleri say. `find_free_port`'un boşluk yoklaması (ve paralel
                // koşan komşu testler) bağlanıp hiçbir şey göndermeden kapatabilir; ham `accept`
                // sayılırsa bu test port-uzayı yarışına bağlı hale gelir (flaky).
                if read == 0 {
                    continue;
                }
                let n = hits2.fetch_add(1, Ordering::SeqCst);
                // 1. istek: partial/confirmed=false → yeniden denenmeli. 2. istek: confirmed=true.
                let body: &[u8] = if n == 0 {
                    br#"{"status":"partial","confirmed":false}"#
                } else {
                    br#"{"status":"success","confirmed":true}"#
                };
                let _ = write!(
                    s,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    body.len()
                );
                let _ = s.write_all(body);
            }
        });

        safe_stop_coils(port);
        assert_eq!(
            hits.load(Ordering::SeqCst),
            2,
            "confirmed=false yaniti YENIDEN DENENMEDI — ESP bobinleri durdurulmadan kalabilir"
        );
    }

    /// `backend.port` KULLANICI-YAZILABİLİR bir dizindedir → içeriği asla ham güvenilmez.
    #[test]
    fn backend_port_dosyasi_guvenle_okunur() {
        let tmp = tempfile::tempdir().unwrap();
        let p = tmp.path();
        assert_eq!(read_backend_port(p), None, "dosya yokken None olmali");

        std::fs::write(p.join("backend.port"), "8123\r\n").unwrap();
        assert_eq!(read_backend_port(p), Some(8123), "CR/LF kirpilmali");

        for bad in ["", "   ", "0", "abc", "8123; calc", "-1", "99999"] {
            std::fs::write(p.join("backend.port"), bad).unwrap();
            assert_eq!(read_backend_port(p), None, "gecersiz deger kabul edildi: {bad:?}");
        }
    }

    /// DENETİM 2026-08-04: çalışan bir backend'i SAHİPLENMEDEN (ikinci süreç başlatmayı
    /// engellemeden) önce KİMLİĞİ doğrulanmalı — aynı porta bağlanmış İLGİSİZ bir yerel servis
    /// de HTTP 200 döner. Yanlış sahiplenme, veterinere donanımı kontrol etmeyen bir UI gösterir.
    #[test]
    fn calisan_backend_yalniz_pemf_imzasiyla_sahiplenilir() {
        use std::io::Read;

        fn serve(body: &'static [u8]) -> u16 {
            let l = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
            let port = l.local_addr().unwrap().port();
            std::thread::spawn(move || {
                for stream in l.incoming() {
                    let Ok(mut s) = stream else { continue };
                    let mut buf = [0u8; 1024];
                    let _ = s.read(&mut buf);
                    let _ = write!(
                        s,
                        "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                        body.len()
                    );
                    let _ = s.write_all(body);
                }
            });
            port
        }

        let pemf = serve(br#"{"status":"online","service":"PEMF-Vet"}"#);
        let other = serve(br#"{"status":"online","service":"BaskaServis"}"#);

        let tmp = tempfile::tempdir().unwrap();
        // backend.port GERÇEK backend'i gösteriyor → tespit edilmeli (ikinci süreç açılmaz).
        std::fs::write(tmp.path().join("backend.port"), pemf.to_string()).unwrap();
        assert_eq!(detect_running_backend(tmp.path()), Some(pemf));

        // backend.port İLGİSİZ bir servisi gösteriyor → SAHİPLENİLMEMELİ.
        std::fs::write(tmp.path().join("backend.port"), other.to_string()).unwrap();
        assert_ne!(
            detect_running_backend(tmp.path()),
            Some(other),
            "PEMF olmayan bir servis backend sanildi"
        );
    }

    /// DENETİM 2026-08-04 (P2 #13): portu bizden önce kapan bir süreç HTTP 200 dönse bile
    /// "hazır" SAYILMAMALI — aksi halde kapanışta E-stop POST'u ONA gider ve gerçek bobinler
    /// hastanın üzerinde çalışmaya devam eder.
    #[test]
    fn health_nonce_uyusmazsa_hazir_demez() {
        use std::io::Read;

        fn serve(body: &'static str) -> u16 {
            let l = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
            let port = l.local_addr().unwrap().port();
            std::thread::spawn(move || {
                for stream in l.incoming() {
                    let Ok(mut s) = stream else { continue };
                    let mut buf = [0u8; 1024];
                    let _ = s.read(&mut buf);
                    let _ = write!(
                        s,
                        "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                        body.len(),
                        body
                    );
                }
            });
            port
        }

        // 1) GERÇEK backend: nonce'u yansıtıyor → hazır.
        let ok_port = serve(r#"{"status":"online","service":"PEMF-Vet","launcherNonce":"DOGRU"}"#);
        assert!(wait_for_health(ok_port, Duration::from_secs(5), Some("DOGRU")));

        // 2) PORT KAPAN SÜREÇ: 200 döner, PEMF gibi görünür ama nonce'u BİLEMEZ → hazır DEĞİL.
        let squat = serve(r#"{"status":"online","service":"PEMF-Vet"}"#);
        assert!(
            !wait_for_health(squat, Duration::from_secs(2), Some("DOGRU")),
            "nonce YOKKEN hazir dendi — port kapan surece E-stop gonderilir"
        );

        // 3) YANLIŞ nonce (tahmin denemesi) → hazır DEĞİL.
        let wrong = serve(r#"{"status":"online","service":"PEMF-Vet","launcherNonce":"YANLIS"}"#);
        assert!(!wait_for_health(wrong, Duration::from_secs(2), Some("DOGRU")));

        // 4) ESKİ backend (nonce desteklemiyor) + doğrulama KAPALI → geriye uyum korunur.
        assert!(wait_for_health(squat, Duration::from_secs(5), None));
    }

    /// Nonce tahmin edilebilir OLMAMALI: her çağrı farklı ve 256-bit hex.
    #[test]
    fn health_nonce_benzersiz_ve_yeterli_uzunlukta() {
        let a = generate_health_nonce();
        let b = generate_health_nonce();
        assert_eq!(a.len(), 64, "SHA-256 hex = 64 karakter");
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(a, b, "ardisik iki nonce AYNI cikti — entropi yok");
    }

    /// Sahte bir HTTP sunucusu 200 dönünce hazır kabul edilmeli.
    #[test]
    fn health_200_gorunce_hazir_der() {
        let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        // take(1) DEĞİL: ureq bağlantıyı erken kapatırsa/ilk deneme ıskalarsa sunucu ölür
        // ve test yük altında kırılgan olur. Sürekli dinle; thread testle birlikte biter.
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(mut s) = stream else { continue };
                let body = b"{\"status\":\"online\"}";
                let _ = write!(
                    s,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    body.len()
                );
                let _ = s.write_all(body);
            }
        });
        assert!(wait_for_health(port, Duration::from_secs(5), None));
    }

    /// Kimse dinlemiyorsa zaman aşımına düşmeli (sessizce "hazır" DEMEMELİ).
    ///
    /// DENETİM 2026-08-04 (test kararlılığı): bu test EFEMERAL bir portu serbest bırakıp
    /// "artık kimse dinlemiyor" VARSAYIYORDU. Aynı süreçteki diğer testler port 0 ile sunucu
    /// açtığı için işletim sistemi tam o portu ONLARA verebiliyor ve test SAHTE-KIRMIZI oluyordu
    /// (gerçek regresyon değil). Flaky bir test, gerçek bir kırılmayı gürültüde saklar → portun
    /// gerçekten boş olduğunu DOĞRULA, kapılmışsa başka bir port dene.
    #[test]
    fn dinleyen_yoksa_hazir_demez() {
        for _ in 0..8 {
            let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
            let port = listener.local_addr().unwrap().port();
            drop(listener); // port serbest bırakıldı
            if TcpStream::connect(("127.0.0.1", port)).is_ok() {
                continue; // yarış: başka bir test bu portu kapmış → yeni port dene
            }
            assert!(!wait_for_health(port, Duration::from_secs(2), None));
            return;
        }
        panic!("gercekten bos bir port bulunamadi (8 deneme)");
    }

    /// 200 DIŞI yanıt hazır sayılmamalı (404 veren başka bir servis olabilir).
    #[test]
    fn baska_servis_404_verirse_hazir_demez() {
        let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let mut s = stream.unwrap();
                let _ = write!(s, "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
            }
        });
        assert!(!wait_for_health(port, Duration::from_secs(2), None));
    }

    #[test]
    fn eksik_backend_net_hata_verir() {
        let tmp = tempfile::tempdir().unwrap();
        let err = start_and_wait(tmp.path(), 48999, Duration::from_secs(1)).unwrap_err();
        assert!(matches!(err, BackendError::NotFound(_)));
    }

    #[test]
    fn tcp_baglanti_kurulabiliyor_mu_testi_saglikli() {
        let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        assert!(TcpStream::connect(("127.0.0.1", port)).is_ok());
    }
}
