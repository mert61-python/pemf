//! Backend sürecini başlatma + hazır olmasını bekleme + tarayıcıyı açma.
//!
//! Sessiz başarısızlık YASAK: eski akışta backend açılmazsa kullanıcı boş bir
//! tarayıcı sekmesiyle kalıyordu. Burada `/api/health` 200 dönene kadar beklenir;
//! zaman aşımında süreç öldürülür ve stderr çağırana verilir.

use std::io;
use std::net::{Ipv4Addr, SocketAddrV4, TcpListener};
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

/// `start`'tan itibaren bağlanabilen ilk portu bulur.
/// Klinik makinesinde 8000 sıkça meşguldür (başka servis) → sabit port varsaymayız.
pub fn find_free_port(start: u16, tries: u16) -> Result<u16, BackendError> {
    for port in start..start.saturating_add(tries) {
        let addr = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
        if TcpListener::bind(addr).is_ok() {
            return Ok(port);
        }
    }
    Err(BackendError::NoFreePort {
        start,
        end: start.saturating_add(tries),
    })
}

/// `/api/health` 200 dönene kadar bekler.
pub fn wait_for_health(port: u16, timeout: Duration) -> bool {
    let url = health_url(port);
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        let ok = ureq::get(&url)
            .timeout(Duration::from_secs(2))
            .call()
            .map(|r| r.status() == 200)
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
    for (k, v) in install::backend_env(install_root, port) {
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

    if wait_for_health(port, timeout) {
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
pub fn safe_stop_coils(port: u16) {
    let url = format!("http://127.0.0.1:{port}/api/hardware/emergency_stop");
    let _ = ureq::post(&url)
        .timeout(Duration::from_secs(3))
        .call();
    // STM STOP sender-thread'ce seri porta yazılana kadar bekle (backend flush deadline'ı ~1.5s).
    std::thread::sleep(Duration::from_millis(1200));
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
        for pat in ["PEMF_Backend", "mosquitto", "cloudflared"] {
            let _ = Command::new("pkill")
                .args(["-f", pat])
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
            if let Ok((mut s, _)) = listener.accept() {
                let mut buf = [0u8; 1024];
                let n = s.read(&mut buf).unwrap_or(0);
                let body = b"{\"status\":\"success\"}";
                let _ = write!(
                    s,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    body.len()
                );
                let _ = s.write_all(body);
                let _ = tx.send(String::from_utf8_lossy(&buf[..n]).into_owned());
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
        assert!(wait_for_health(port, Duration::from_secs(5)));
    }

    /// Kimse dinlemiyorsa zaman aşımına düşmeli (sessizce "hazır" DEMEMELİ).
    #[test]
    fn dinleyen_yoksa_hazir_demez() {
        let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener); // port serbest, kimse dinlemiyor
        assert!(!wait_for_health(port, Duration::from_secs(2)));
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
        assert!(!wait_for_health(port, Duration::from_secs(2)));
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
