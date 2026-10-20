// Author: mertaygn, cglrgrkn
//! Backend sürecini başlatma + hazır olmasını bekleme + tarayıcıyı açma.
//!
//! Sessiz başarısızlık YASAK: eski akışta backend açılmazsa kullanıcı boş bir
//! tarayıcı sekmesiyle kalıyordu. Burada `/api/health` 200 dönene kadar beklenir;
//! zaman aşımında süreç öldürülür ve stderr çağırana verilir.

use std::collections::BTreeMap;
use std::io;
use std::net::{Ipv4Addr, SocketAddrV4, TcpListener, TcpStream};
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

use crate::install;

#[derive(Debug, thiserror::Error)]
pub enum BackendError {
    #[error("{}", crate::dil::t_ile("rust.backend.bulunamadi", &[("yol", &(.0).to_string())]))]
    NotFound(String),
    #[error("{}", crate::dil::t_ile("rust.backend.baslatilamadi", &[("hata", &(.0).to_string())]))]
    Spawn(#[source] io::Error),
    #[error("{}", crate::dil::t_ile("rust.backend.hazirOlmadi", &[("timeout_s", &(.timeout_s).to_string()), ("port", &(.port).to_string()), ("tail", &(.tail).to_string())]))]
    Timeout { port: u16, timeout_s: u64, tail: String },
    #[error("{}", crate::dil::t_ile("rust.backend.sonlandi", &[("code", &format!("{:?}", .code)), ("tail", &(.tail).to_string())]))]
    Exited { code: Option<i32>, tail: String },
    #[error("{}", crate::dil::t_ile("rust.backend.portYok", &[("start", &(.start).to_string()), ("end", &(.end).to_string())]))]
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

/// `/api/health` gövdesinden "tıbbi kayıt DB'si hazır mı" — `None` = BİLİNMİYOR.
///
/// ⚠️ DENETİM 2026-08-23 (C5). `wait_for_health` yalnız HTTP 200 + nonce ölçer; backend AYNI
/// yanıtta `dbReady` alanını da yayınlar ve `/api/session/start` tam ona bakıp 503 döner
/// (`api_server::_kayit_db_hazir`). DB tarafını bozan bir yayında cihaz "sağlıklı" görünür,
/// güncelleme ONAYLANIR ve `runtime.old` SİLİNİR → klinik hiçbir seans açamaz ve otomatik geri
/// dönüş yolu kalmaz.
///
/// ⚠️ BU ALAN `wait_for_health`E KAPI OLARAK EKLENMEZ. Backend'in kendi gerekçesi bunu açıkça
/// reddediyor: "Sağlığın kendisini DÜŞÜRMEZ: backend ayakta ve acil durdurma yolu çalışıyor."
/// DB bozukken bile E-stop çalışmalıdır. Bu yüzden ölçüm ayrı bir fonksiyondadır ve YALNIZ
/// güncellemeyi onaylama kararında kullanılır.
///
/// `None` (alan yok / gövde bozuk / beklenmedik tip) → çağıran güncellemeyi normal onaylar:
/// eski backend'ler bu alanı yansıtmaz ve bilinmeyeni "bozuk" saymak onları güncellenemez yapardı
/// (nonce'taki geriye-uyum kuralının aynısı).
pub fn db_hazir_govdeden(govde: &str) -> Option<bool> {
    serde_json::from_str::<serde_json::Value>(govde)
        .ok()?
        .get("dbReady")?
        .as_bool()
}

/// Çalışan backend'e TEK istek atıp `dbReady` durumunu okur. Ulaşılamazsa `None` (bilinmiyor).
pub fn db_hazir_mi(port: u16) -> Option<bool> {
    ureq::get(&health_url(port))
        .timeout(Duration::from_secs(3))
        .call()
        .ok()
        .filter(|r| r.status() == 200)
        .and_then(|r| r.into_string().ok())
        .and_then(|b| db_hazir_govdeden(&b))
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

/// Bu portta AKTİF BİR TEDAVİ SEANSI sürüyor mu? (`/api/health` → `sessionActive`)
///
/// ⚠️ DENETİM 2026-08-04: launcher açılışta manifest'e bakıp yeni sürümü SESSİZCE indirip `/S`
/// ile kurar. NSIS yükseltme kancası `taskkill /F /IM PEMF_Backend.exe` çalıştırır → HASTA
/// ÜZERİNDE SÜREN seans yarıda kesilir. (E-stop kancası bobinleri güvene alır, yani hasta
/// güvenliği korunur; ama tedavi yarım kalır ve veteriner sebebini göremez.) Launcher artık
/// güncellemeden ÖNCE burayı okur.
///
/// GERİYE UYUM — bu ayrım kritiktir: alan YOKSA (`sessionActive` döndürmeyen ESKİ base.zip)
/// `false` döneriz. "Bilinmiyor = aktif" deseydik eski backend'i olan HER kurulum kendini
/// bir daha ASLA güncelleyemezdi (kilitlenme). Yalnız AÇIKÇA `true` güncellemeyi erteler;
/// backend tarafı okuma hatasında zaten fail-safe olarak `true` yayınlıyor.
pub fn session_active(port: u16) -> Option<bool> {
    // ⚠️ P1 (denetim 2026-08-04): eskiden `bool` dönüyordu ve ULAŞILAMAYAN/ZAMAN AŞIMINA UĞRAYAN
    // sağlık yanıtı da `false` ("seans yok") sayılıyordu. Ölçüldü: yük altındaki (yanıt yazmayan)
    // bir backend'de `session_active = false (2003 ms)`. Çağıran o an backend'in CANLI olduğunu
    // zaten kanıtlamış oluyor → "bilinmiyor"u "seans yok" saymak, süren tedaviyi kesen sessiz
    // güncellemeye izin verirdi. Backend tarafı bilinçli olarak TERS yönde fail-safe
    // (system_router.py: `except Exception: _session_active = True`); istemci de öyle olmalı.
    //
    // `None` = BİLİNMİYOR (ulaşılamadı / bozuk yanıt). Alan YOKSA `Some(false)` döner —
    // bu, `sessionActive` yayınlamayan ESKİ base.zip'lerin kendini bir daha asla
    // güncelleyememesini önleyen bilinçli geriye-uyum kararıdır (bkz. test).
    //
    // Zaman aşımı 2 sn değil: bu çağrı YIKICI bir işlemi (sessiz `/S` kurulum) kapıyor ve
    // klinik makinesinde backend AI çıkarımı yaparken /api/health saniyeler sürebilir.
    let r = ureq::get(&health_url(port))
        .timeout(Duration::from_secs(SESSION_PROBE_TIMEOUT_S))
        .call()
        .ok()?;
    if r.status() != 200 {
        return None;
    }
    let v: serde_json::Value = serde_json::from_str(&r.into_string().ok()?).ok()?;
    match v.get("sessionActive") {
        // Alan var ve bool → net cevap.
        Some(x) if x.is_boolean() => x.as_bool(),
        // Alan YOK / null → eski backend. Geriye uyum: engelleme.
        Some(x) if x.is_null() => Some(false),
        None => Some(false),
        // Beklenmedik tip → güvenilmez, BİLİNMİYOR say.
        Some(_) => None,
    }
}

/// Seans yoklaması için zaman aşımı — yıkıcı bir işlemi kapıdığı için cömert.
const SESSION_PROBE_TIMEOUT_S: u64 = 10;

/// Backend KESİN olarak yok mu? (TCP bağlantısı reddedildi ⇒ o portta dinleyen YOK)
///
/// ⚠️ DENETİM 2026-08-04 (P1 — BU DÜZELTMENİN KENDİ AÇIĞI): `clear_port_if_stopped`
/// `probe_pemf_backend`'in `false`'ına bakıyordu; oysa o `false` İKİ AYRI ŞEYİ birleştiriyor:
///   • "orada kimse yok"            (kesin ölü)
///   • "dinleyici var ama 2 sn'de cevap vermedi" (BİLİNMİYOR — yük altındaki backend)
/// Ölçüldü: TCP kabul eden ama yanıt yazmayan bir dinleyicide `probe_pemf_backend = false
/// (2002 ms)`. Yani `taskkill` başarısız olmuş, backend HÂLÂ AYAKTA ve bobinler enerjiliyken
/// launcher `backend.port`'u siliyordu → NSIS uninstaller / onarım yolu E-stop adresini
/// bulamıyor → E-stop'suz `taskkill /F` → link-watchdog'u OLMAYAN ESP bobinleri 6-8 HASTANIN
/// ÜZERİNDE ENERJİLİ kalıyor. Düzeltmenin önlemeyi vaat ettiği sonucun ta kendisi.
///
/// Artık silme kararı YALNIZ "kesin ölü"ye dayanır. Yanılma maliyeti asimetriktir: ölü bir
/// adres dosyasının kalması ZARARSIZ (bir sonraki başlatma üzerine yazar), canlı bir adresin
/// silinmesi HASTA GÜVENLİĞİ sorunudur.
pub fn backend_is_definitely_gone(port: u16) -> bool {
    let addr = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    TcpStream::connect_timeout(&addr.into(), Duration::from_millis(400)).is_err()
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

// ── Masaüstü oturum devri (E-ÖZELLİĞİ ORTAK SÖZLEŞMESİ) ─────────────────────────────────────
//
// Client Supabase ile giriş yapar, oturumu backend'e DEVREDER, uygulama onu alıp kendi login
// ekranını ATLAR. Çift giriş YOK.
//   POST   /api/auth/desktop-session   {access_token, refresh_token, email, expires_at}
//   DELETE /api/auth/desktop-session   → oturumu temizle (çıkış)
// Oturum backend'de YALNIZ BELLEKTE tutulur; kalıcılık client tarafındadır (secret_store).

/// Oturum devri ucu (yalnız loopback).
pub fn desktop_session_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}/api/auth/desktop-session")
}

/// Oturum devri için tek bütçe: backend yereldir, yavaşsa bile açılışı bekletmemeli.
const SESSION_PUSH_TIMEOUT_S: u64 = 5;

/// F5 (denetim 2026-08-24): kapanış-öncesi SON pull bütçesi. Teardown yolunda backend meşgulse
/// (örn. AI yükü) kapanışı 5 sn bekletmemeli — bu YALNIZ son-yakalamaya özgü KISA bütçe, 60 sn
/// rotasyon döngüsünün `SESSION_PUSH_TIMEOUT_S`=5'ini DEĞİŞTİRMEZ.
pub const PULL_TEARDOWN_TIMEOUT_S: u64 = 2;

/// Hedef GERÇEKTEN loopback mi? (saf → birim-testlenebilir)
///
/// ⚠️ SÖZLEŞME: oturum jetonları YALNIZ 127.0.0.1/::1'e gönderilir. Bu kontrol savunma
/// derinliğidir: bugün URL'yi port'tan biz üretiyoruz, ama bir gün "uzak backend" alanı
/// eklenirse jetonlar sessizce tünelden/LAN'dan çıkardı.
pub fn is_loopback_http_url(url: &str) -> bool {
    let Some(rest) = url.strip_prefix("http://") else {
        // https://127.0.0.1 de meşru sayılır (yerel TLS kurulumu) — başka şema ASLA.
        let Some(rest) = url.strip_prefix("https://") else { return false };
        return authority_is_loopback(rest);
    };
    authority_is_loopback(rest)
}

fn authority_is_loopback(rest: &str) -> bool {
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    // userinfo ("127.0.0.1@evil.example") ayrıştırıcılar arasında farklı yorumlanır → REDDET.
    if authority.is_empty() || authority.contains('@') {
        return false;
    }
    // IPv6 köşeli-parantez biçimi: [::1]:8000
    let host = if let Some(k) = authority.strip_prefix('[') {
        match k.split_once(']') {
            Some((h, _)) => h.to_string(),
            None => return false,
        }
    } else {
        authority.split(':').next().unwrap_or("").to_string()
    };
    let h = host.to_ascii_lowercase();
    // "localhost" BİLEREK YOK: hosts dosyasıyla başka bir adrese yönlendirilebilir; jeton
    // gönderdiğimiz adres ad çözümlemesine bağlı OLMAMALI.
    h == "127.0.0.1" || h == "::1"
}

/// Oturumu verilen URL'ye devret. Loopback DIŞI hedefte istek HİÇ gönderilmez.
///
/// GERİYE UYUM: backend 404/405/501 dönerse (ucu henüz taşımayan base.zip) SESSİZCE başarı
/// sayılır — aksi halde iki hat aynı anda yayınlanmadığında client açılmaz hale gelirdi.
/// Uygulama o durumda kendi giriş ekranını gösterir; kimse kilitlenmez.
pub fn push_desktop_session_to(url: &str, session: &crate::auth::Session) -> Result<(), String> {
    if !is_loopback_http_url(url) {
        return Err(crate::dil::t("rust.backend.oturumYalnizYerel"));
    }
    let body = serde_json::to_string(session).map_err(|_| crate::dil::t("rust.backend.oturumSerilestirilemedi"))?;
    match ureq::post(url)
        .timeout(Duration::from_secs(SESSION_PUSH_TIMEOUT_S))
        .set("Content-Type", "application/json")
        .send_string(&body)
    {
        Ok(_) => Ok(()),
        Err(ureq::Error::Status(404 | 405 | 501, _)) => Ok(()),
        // ⚠️ Hata metnine ASLA gövde koyma: gövde jetonların ta kendisiydi.
        Err(ureq::Error::Status(s, _)) => Err(crate::dil::t_ile("rust.backend.oturumKabulEdilmedi", &[("s", &(s).to_string())])),
        Err(_) => Err(crate::dil::t("rust.backend.oturumDevredilemedi")),
    }
}

/// Backend'in BELLEĞİNDEKİ devir oturumunu OKU (uygulama penceresi jetonu döndürmüş olabilir).
///
/// 🔴 Rotasyon senkronu (saha arızası 2026-08-24): pencere `autoRefreshToken` ile jetonu yeniler,
/// Supabase onu DÖNDÜRÜR ve pencere yeni oturumu buraya geri yazar. Launcher bunu okuyup diske
/// işlemezse kendi kopyası bayatlar ve "Beni hatırla" bir sonraki açılışta SİLİNİR.
///
/// Boş gövde / eksik alan / ulaşılamama → `None` (sessiz; senkron bir kolaylıktır).
pub fn pull_desktop_session(port: u16) -> Option<crate::auth::Session> {
    pull_desktop_session_kisa(port, SESSION_PUSH_TIMEOUT_S)
}

/// [F5] `pull_desktop_session`'ın timeout-parametrized varyantı. Teardown son-yakalaması KISA
/// bütçeyle (`PULL_TEARDOWN_TIMEOUT_S`) çağırır; 60 sn döngüsü 5 sn ile çağırmaya devam eder.
/// Loopback sözleşmesi + boş-oturum (`{}`) → `None` semantiği DEĞİŞMEZ (aynı gövde).
pub fn pull_desktop_session_kisa(port: u16, timeout_s: u64) -> Option<crate::auth::Session> {
    match devir_cek_kisa(port, timeout_s) {
        DevirCekme::Oturum(s) => Some(s),
        DevirCekme::Cikis | DevirCekme::Yok => None,
    }
}

/// Devir çekmenin sonucu. ⚠️ 2026-10-18 (auth_session.bin kaybı, sahip kararı): pencerede "Çıkış Yap" artık AYRI bir
/// durumdur — backend çıkıştan sonra `{"cikis": true}` döner; launcher kendi "Beni hatırla" kaydını HEMEN siler.
/// Eskiden çıkış da `{}` (oturum yok) görünüyor, launcher sunucuda silinmiş oturumun jetonunu diskte tutuyordu.
#[derive(Debug, Clone)]
pub enum DevirCekme {
    /// Backend'te devredilmiş (ya da pencerenin geri yazdığı) oturum var.
    Oturum(crate::auth::Session),
    /// Pencerede çıkış yapıldı (yeni devir gelene kadar).
    Cikis,
    /// Oturum yok / ulaşılamadı / gövde bozuk (backend yeniden başladıysa da bu — çıkış SAYILMAZ).
    Yok,
}

/// `pull_desktop_session_kisa`nın üç durumlu hâli (loopback sözleşmesi aynı).
pub fn devir_cek_kisa(port: u16, timeout_s: u64) -> DevirCekme {
    let url = desktop_session_url(port);
    if !is_loopback_http_url(&url) {
        return DevirCekme::Yok;
    }
    let govde = ureq::get(&url)
        .timeout(Duration::from_secs(timeout_s))
        .call()
        .ok()
        .filter(|r| r.status() == 200)
        .and_then(|r| r.into_string().ok());
    govde.map(|g| devir_govdesini_coz(&g)).unwrap_or(DevirCekme::Yok)
}

/// `devir_cek_kisa` + 60 sn döngüsünün bütçesi.
pub fn devir_cek(port: u16) -> DevirCekme {
    devir_cek_kisa(port, SESSION_PUSH_TIMEOUT_S)
}

/// Devir ucunun gövdesini çöz (saf → birim-testlenebilir). Jeton varsa `Oturum` (çıkış işareti yok sayılır),
/// yalnız `{"cikis": true}` ise `Cikis`, aksi hâlde `Yok`.
pub fn devir_govdesini_coz(govde: &str) -> DevirCekme {
    let Ok(v) = serde_json::from_str::<serde_json::Value>(govde) else {
        return DevirCekme::Yok;
    };
    let al = |k: &str| v.get(k).and_then(|x| x.as_str()).unwrap_or("").to_string();
    let refresh = al("refresh_token");
    let access = al("access_token");
    if refresh.is_empty() || access.is_empty() {
        // oturum yok ({}) → senkronlanacak bir şey de yok; çıkış işareti varsa launcher kaydını temizler
        return if v.get("cikis").and_then(|x| x.as_bool()) == Some(true) { DevirCekme::Cikis } else { DevirCekme::Yok };
    }
    DevirCekme::Oturum(crate::auth::Session {
        access_token: access,
        refresh_token: refresh,
        email: al("email"),
        // Backend `expires_at`i sayı ya da metin tutabilir (auth_router elle zorluyor).
        expires_at: v
            .get("expires_at")
            .and_then(|x| x.as_i64().or_else(|| x.as_str().and_then(|t| t.parse().ok())))
            .unwrap_or(0),
    })
}

/// Oturumu çalışan backend'e devret (best-effort — çağıran hatayı yutabilir).
pub fn push_desktop_session(port: u16, session: &crate::auth::Session) -> Result<(), String> {
    push_desktop_session_to(&desktop_session_url(port), session)
}

/// Oturum devri için GÜVENİLİR hedef portu seç.
///
/// ⚠️ DENETİM 2026-08-06 (JETON SIZINTISI): `auth_login`/`auth_logout` hedefi `backend.port`
/// dosyasından HAM okuyordu. O dosya bilinçli olarak "kesin ölü" teyidi olmadan SİLİNMEZ
/// (bobinlerin E-stop adresidir — bkz. `clear_port_if_stopped`), yani backend çöktükten ya da
/// makine kapandıktan sonra diskte KALIR. Bu aralıkta 127.0.0.1:<port>'u BAŞKA bir yerel süreç
/// dinliyorsa launcher, Supabase access+refresh jetonlarını ONA POST ederdi (Windows'ta loopback
/// portunu her kullanıcı süreci bağlayabilir). "Başlat" yolu (`start_installed`) mevcut bir
/// backend'i sahiplenmeden ÖNCE `/api/health` imzasını ZATEN doğruluyordu; jeton yolu ondan
/// zayıf olamaz.
///
/// `tracked` = BU launcher'ın başlattığı süreç; kimliği başlatırken health-nonce ile
/// kanıtlanmıştır → yeniden yoklanmaz (yük altındaki backend'de yanlış-negatif üretip
/// "çift giriş"e düşmeyelim).
pub fn session_target_port(tracked: Option<u16>, install_root: &Path) -> Option<u16> {
    if tracked.is_some() {
        return tracked;
    }
    detect_running_backend(install_root)
}

/// Backend'deki oturumu temizle ("Çıkış yap"). Best-effort ve sessiz.
pub fn clear_desktop_session(port: u16) {
    let url = desktop_session_url(port);
    if !is_loopback_http_url(&url) {
        return;
    }
    let _ = ureq::delete(&url)
        .timeout(Duration::from_secs(SESSION_PUSH_TIMEOUT_S))
        .call();
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

    // Konsol penceresi AÇMADAN (bkz. platform::gizli_komut) — backend KONSOL-altsistem bir
    // exe'dir; pencereli launcher'dan başlatılınca Windows ona yeni konsol açardı.
    let mut cmd = crate::platform::gizli_komut(&exe);
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
    // Aynı harita hem çocuğa verilir HEM DE `read_tail`e — günlük yolu çocuğun gördüğü
    // `PEMF_DATA_DIR`/`PEMF_LOG_DIR` ile çözülsün (bkz. read_tail'deki arıza notu).
    let cocuk_env = install::backend_env(install_root, port, &nonce);
    for (k, v) in &cocuk_env {
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

    // (Konsol gizleme yukarıda `platform::gizli_komut` ile uygulanır — bayrak burada TEKRAR
    // verilmez; `creation_flags` değeri EZER, yani ikinci bir çağrı ilkini sessizce iptal ederdi.)

    let mut child = cmd.spawn().map_err(BackendError::Spawn)?;

    if wait_for_health(port, timeout, verify_nonce.then_some(nonce.as_str())) {
        return Ok(child);
    }

    // Hazır olmadı: süreç kendi kendine mi öldü, yoksa asılı mı kaldı?
    let exited = child.try_wait().ok().flatten();
    let tail = read_tail(&mut child, &cocuk_env);
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

/// Başlangıç-hatası teşhisi.
///
/// ⚠️ DENETİM 2026-08-04: bu fonksiyon `child.stderr`'i okuyordu — ama stderr `Stdio::null()`'a
/// yönlendirilmiş durumda (drenajsız pipe TÜM servisi deadlock'luyordu; bkz. üstteki not), yani
/// `child.stderr` HER ZAMAN `None` olur. Kod hiç çalışmayan bir dal taşıyordu ve kullanıcı backend
/// her başlatılamadığında SADECE "günlüğe bak" cümlesini görüyordu — hatanın kendisini değil.
/// Klinikte bu, cihazın neden açılmadığını kimsenin söyleyemediği bir durum demek. Artık
/// backend'in GERÇEK günlüğünün son satırları hataya konur (port çakışması, eksik model, bozuk
/// yapılandırma doğrudan görünür).
fn read_tail(_child: &mut Child, backend_env: &BTreeMap<String, String>) -> String {
    let home = std::env::var_os(if cfg!(target_os = "windows") { "USERPROFILE" } else { "HOME" })
        .or_else(|| {
            std::env::var_os(if cfg!(target_os = "windows") { "HOME" } else { "USERPROFILE" })
        })
        .map(std::path::PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    // ⚠️ ARIZA (2026-08-11): günlük yolu launcher'ın KENDİ ortamından çözülüyordu. Ama
    // `PEMF_DATA_DIR` yalnız ÇOCUK sürece verilir (backend_env) — launcher'ın kendi ortamında
    // YOKTUR. Sonuç: backend `C:\ProgramData\PEMF_System\...\logs`a yazarken launcher
    // `%APPDATA%\PEMF_GUI\logs`u okuyordu ve kullanıcıya GÜNLER ÖNCESİNE ait bayat bir günlük
    // gösteriliyordu. Sahada bir kurulum bu yüzden teşhis edilemedi: gerçek sebep (at-rest
    // anahtarı DB'yi açmıyor) doğru dosyaya YAZILMIŞTI ama kimse o dosyaya bakmıyordu.
    // Çözüm: çocuğa verilen ortamı ÖNCE sor, sonra sürecin kendi ortamına düş.
    let log = install::backend_log_path_with(
        |k| backend_env.get(k).cloned().or_else(|| std::env::var(k).ok()),
        &home,
    );
    read_log_tail(&log, 20)
}

/// Günlük dosyasının SON `n` satırı + yol ipucu. Dosya yoksa/boşsa yalnız ipucu döner.
/// Tamamını okumaz: sondan en fazla 64 KB alır (günlük 10 MB'a kadar büyüyebiliyor).
fn read_log_tail(path: &Path, n: usize) -> String {
    use std::io::{Read, Seek, SeekFrom};
    const WINDOW: u64 = 64 * 1024;
    let mut buf = String::new();
    if let Ok(mut f) = std::fs::File::open(path) {
        let len = f.metadata().map(|m| m.len()).unwrap_or(0);
        let start = len.saturating_sub(WINDOW);
        if f.seek(SeekFrom::Start(start)).is_ok() {
            let mut raw = Vec::new();
            let _ = f.take(WINDOW).read_to_end(&mut raw);
            buf = String::from_utf8_lossy(&raw).into_owned();
            // Pencerenin ortasından başladıysak ilk (yarım) satırı at.
            if start > 0 {
                if let Some(i) = buf.find('\n') {
                    buf = buf[i + 1..].to_string();
                }
            }
        }
    }
    let tail: String = {
        let lines: Vec<&str> = buf.lines().rev().take(n).collect();
        lines.into_iter().rev().collect::<Vec<_>>().join("
")
    };
    // ⚠️ DENETİM 2026-08-04 (P3): günlüğün TAZE olup olmadığı hiç kontrol edilmiyordu. Dosya
    // append-mode'dur; backend loglama YAPILANDIRILMADAN ÖNCE çökerse (ör. AV bir .dll'i
    // karantinaya aldı → PyInstaller önyükleyicisi Python'u hiç çalıştıramadı) tek satır bile
    // yazılmaz ve kullanıcıya ÖNCEKİ BAŞARILI koşunun satırları "Son çıktı" diye gösterilirdi —
    // teşhisi iyileştirmek yerine aktif olarak YANILTIR ("startup complete" yazıyor ama açılmıyor).
    let yas = std::fs::metadata(path)
        .and_then(|m| m.modified())
        .ok()
        .and_then(|t| std::time::SystemTime::now().duration_since(t).ok());
    let bayat = yas.map(|d| d > Duration::from_secs(120)).unwrap_or(false);
    let hint = match yas {
        Some(d) if bayat => crate::dil::t_ile("rust.backend.gunlukBayat", &[("dk", &(d.as_secs() / 60).to_string()), ("yol", &(path.display()).to_string())]),
        _ => crate::dil::t_ile("rust.backend.gunlukIpucu", &[("yol", &(path.display()).to_string())]),
    };
    if tail.trim().is_empty() { hint } else { format!("{tail}
{hint}") }
}


/// Kapanmadan ÖNCE bobinleri güvene al (TIBBİ GÜVENLİK). Hard-kill (child.kill = TerminateProcess)
/// sinyal GÖNDERMEZ → backend'in graceful shutdown'ı (bobin STOP + kuyruk-flush) ÇALIŞMAZ ve
/// bobinler firmware süre-watchdog'u dolana kadar HASTANIN ÜZERİNDE açık kalabilir. Bu çağrı
/// E-stop endpoint'iyle TÜM transport'lardan (STM 1-5 + ESP 6-8) DONANIM STOP tetikler; STM STOP
/// async seri-kuyruğa konduğu için porta yazılsın diye kısa bekler. Best-effort: backend cevap
/// vermese/erişilemese bile çağıran süreci YİNE öldürür (bu adım güvenliği artırır, engellemez).
/// E-stop HTTP bütçesi. DENETİM 2026-08-04: eskiden 3 sn idi; backend AYNI ucu kendi kaynağında
/// "senkron MQTT publish yapar (~7sn worst-case)" diye belgeliyor (`apps/backend/servers/api_server.py`
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

/// Launcher'ın kapanış durdurma ucu (backend `kapanis_durdur`). SAHİP BİLDİRİMİ 2026-10-18 ("uygulama ilk açılışta niye bu
/// uyarıyı veriyor daha yeni açtık … sürekli çıkmasın"): her pencere kapanışı operatörün ACİL DURDUR ucunu çağırıyordu → mandal
/// DİSKE yazılıyor, her açılışta "önceki oturumda ACİL DURDUR — sıfırlanmadı" bandı çıkıyordu. Bu uç STOP'ları AYNEN gönderir;
/// mandalı diske yalnız kapanış anında bobin çalışıyor / seans sürüyorsa yazar.
const KAPANIS_DURDUR_YOLU: &str = "/api/hardware/kapanis_durdur";
const ESTOP_YOLU: &str = "/api/hardware/emergency_stop";
/// Yanıtsız kapanış denemesi bundan KISA sürdüyse (bağlantı reddi) ACİL DURDUR ucu yine denenir; uzun sürdüyse (asılı backend,
/// zaman aşımı) denenmez — pencere kapanışındaki donma katlanmaz (aşağıdaki DENETİM 2026-08-04 notu).
const HIZLI_HATA_ESIGI: Duration = Duration::from_secs(2);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum DurdurDenemesi {
    /// Sözleşme yanıtı, `confirmed: true`.
    Dogrulandi,
    /// Sözleşme yanıtı, `confirmed: false` ("STM durdu ama MQTT yayınlanamadı") — bir kez daha denenir.
    Dogrulanmadi,
    /// HTTP hata durumu (eski backend: 404 / 405; reddedilen istek: 403 / 415 / 400) ya da 200 ama sözleşme yanıtı değil
    /// (ör. statik sayfa) — uç bu backend'de YOK sayılır.
    UcYok,
    /// Yanıt gelmedi (bağlantı reddi / zaman aşımı).
    Yanitsiz,
}

fn durdur_iste(url: &str, onay_govdesi: bool) -> DurdurDenemesi {
    let istek = ureq::post(url).timeout(Duration::from_secs(ESTOP_TIMEOUT_S));
    let sonuc = if onay_govdesi {
        istek.set("Content-Type", "application/json").send_string(r#"{"onay":true}"#)
    } else {
        istek.call()
    };
    match sonuc {
        Ok(r) => match r
            .into_string()
            .ok()
            .and_then(|b| serde_json::from_str::<serde_json::Value>(&b).ok())
            .and_then(|v| v.get("confirmed").and_then(|c| c.as_bool()))
        {
            Some(true) => DurdurDenemesi::Dogrulandi,
            Some(false) => DurdurDenemesi::Dogrulanmadi,
            None => DurdurDenemesi::UcYok,
        },
        Err(ureq::Error::Status(..)) => DurdurDenemesi::UcYok,
        Err(_) => DurdurDenemesi::Yanitsiz,
    }
}

/// Bobinleri durdur (backend öldürülmeden ÖNCE). Önce kapanış ucu; bu backend'de yoksa ya da reddederse (eski runtime / beklenmeyen
/// yanıt) ya da bağlantı HIZLA reddedildiyse operatörün ACİL DURDUR ucu — bobin durdurma hiçbir yolda AZALMAZ (Ö.4-Y8).
pub fn safe_stop_coils(port: u16) {
    let kapanis = format!("http://127.0.0.1:{port}{KAPANIS_DURDUR_YOLU}");
    let t0 = Instant::now();
    let estop_gerekli = match durdur_iste(&kapanis, true) {
        DurdurDenemesi::Dogrulandi => false,
        DurdurDenemesi::Dogrulanmadi => {
            std::thread::sleep(Duration::from_millis(300));
            let _ = durdur_iste(&kapanis, true);
            false
        }
        DurdurDenemesi::UcYok => true,
        DurdurDenemesi::Yanitsiz => t0.elapsed() < HIZLI_HATA_ESIGI,
    };
    if estop_gerekli {
        estop_ucuyla_durdur(port);
    }
    // Best-effort: doğrulanmasa bile çağıran süreci YİNE öldürür (bu adım güvenliği artırır,
    // engellemez). Doğrulanmadıysa kuyruğun yazılması için tam bütçeyi tanı.
    std::thread::sleep(Duration::from_millis(ESTOP_FLUSH_MS));
}

/// Eski yol (ve kapanış ucu yoksa yedek): operatörün ACİL DURDUR ucu — mandalı diske yazar.
fn estop_ucuyla_durdur(port: u16) {
    let url = format!("http://127.0.0.1:{port}{ESTOP_YOLU}");
    // Backend `{"status":"success|partial|error","confirmed":bool,...}` döner ve "bir transport
    // doğrulanamadı" durumunu BİLEREK bildirir. Eski kod yanıtı `let _ =` ile tamamen atıyordu →
    // "STM durdu ama MQTT yayınlanamadı" sinyali görülmüyordu. Doğrulanmazsa BİR KEZ daha dene:
    // ESP publish'i geçici broker/ağ hatasında sıklıkla ikinci denemede geçer.
    // ⚠️ DENETİM 2026-08-04 (P2 — BU DÜZELTMENİN YAN ETKİSİ): bütçeyi 3 sn'den 10 sn'ye çıkarıp
    // ikinci denemeyi eklediğimde EN KÖTÜ blokaj 4,2 sn'den ~21,9 sn'ye çıktı (ölçüldü). Bu çağrı
    // pencere kapanışında Tauri OLAY DÖNGÜSÜ thread'inden yapılıyor → istemci o süre boyunca
    // DONUYOR, Windows "Yanıt vermiyor" diyor ve kullanıcı Görev Yöneticisi'nden launcher'ı
    // sonlandırırsa `child.kill()` + `kill_stray_backends()` HİÇ çalışmıyor → yetim backend seri
    // portu ve `runtime/` dosyalarını tutmaya devam ediyor (sonraki kurulumda "os error 32").
    //
    // Çözüm bütçeyi kısmak DEĞİL (backend `emergency_stop`'u ~7 sn worst-case MQTT publish diye
    // belgeliyor; kısaltmak ESP bobinlerini yayınlanmadan bırakır). Çözüm: İKİNCİ denemeyi
    // yalnızca backend GERÇEKTEN YANIT VERDİĞİNDE ama `confirmed:false` dediğinde yap. O durumda
    // ikinci istek hızlı döner ve anlamlıdır ("STM durdu, MQTT yayınlanamadı" → tekrar dene).
    // Yanıt HİÇ gelmediyse (timeout) ikinci 10 sn beklemek hiçbir şey kazandırmaz, yalnız donmayı
    // ikiye katlar. Yeni en kötü durum: ~11,6 sn (10 + flush), yanıtlı-doğrulanmamışta ~12 sn.
    // Yanıt YOKSA (ulaşılamadı/timeout) ya da sözleşme yanıtı değilse tekrar denemenin faydası yok — donmayı katlamaz.
    for attempt in 0..2u8 {
        match durdur_iste(&url, false) {
            DurdurDenemesi::Dogrulanmadi if attempt == 0 => std::thread::sleep(Duration::from_millis(300)),
            _ => break,
        }
    }
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
        let mut c = crate::platform::gizli_komut("rundll32.exe");
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

    /// `/api/health` gövdesini taklit eden tek-atışlık sunucu (testler için).
    fn saglik_sunucusu(body: &'static str) -> u16 {
        use std::io::Read;
        let ln = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = ln.local_addr().unwrap().port();
        std::thread::spawn(move || {
            for stream in ln.incoming() {
                let Ok(mut s) = stream else { continue };
                let mut buf = [0u8; 1024];
                if s.read(&mut buf).unwrap_or(0) == 0 {
                    continue; // boş yoklama bağlantısı (bkz. port_is_free)
                }
                let _ = write!(
                    s,
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                    body.len(),
                    body
                );
                break;
            }
        });
        port
    }

    /// Tedavi sürerken launcher SESSİZ oto-güncelleme yapmamalı (NSIS yükseltmesi backend'i
    /// `taskkill` ile öldürür → hasta üzerindeki seans yarıda kesilir).
    #[test]
    fn aktif_seans_bildirildiginde_true_doner() {
        let p = saglik_sunucusu(r#"{"service":"PEMF-Vet","sessionActive":true}"#);
        assert_eq!(session_active(p), Some(true), "aktif seans goz ardi edildi — guncelleme tedaviyi keser");
    }

    /// ⚠️ GERİYE UYUM KİLİDİ: `sessionActive` ALANI OLMAYAN eski backend'de `false` dönmeli.
    /// "Bilinmiyor = aktif" deseydik eski base.zip'i olan her kurulum kendini bir daha ASLA
    /// güncelleyemezdi (kalıcı kilitlenme).
    #[test]
    fn alan_yoksa_guncelleme_engellenmez() {
        let p = saglik_sunucusu(r#"{"service":"PEMF-Vet","status":"online"}"#);
        assert!(
            session_active(p) == Some(false),
            "eski backend guncellemeyi KALICI engelliyor — self-update bir daha calismaz"
        );
    }

    #[test]
    fn seans_yokken_false_doner() {
        let p = saglik_sunucusu(r#"{"service":"PEMF-Vet","sessionActive":false}"#);
        assert_eq!(session_active(p), Some(false));
    }

    /// SAHA ARIZASI 2026-08-11 — TEŞHİS EDİLEMEZ BAŞLATMA HATASI.
    ///
    /// Backend `PEMF_DATA_DIR` ile makine-geneli köke (`C:\ProgramData\PEMF_System`) yazar; bu
    /// değişkeni ÇOCUĞA yalnız launcher verir, launcher'ın KENDİ ortamında yoktur. `read_tail`
    /// yolu kendi ortamından çözdüğü için `%APPDATA%\PEMF_GUI\logs`a bakıyordu → kullanıcıya
    /// GÜNLER ÖNCESİNE ait bayat günlük gösterildi; gerçek sebep doğru dosyaya yazılmıştı ama
    /// kimse oraya bakmıyordu. Günlük yolu, çocuğun GÖRDÜĞÜ ortamla çözülmeli.
    #[test]
    fn KRITIK_gunluk_yolu_COCUGUN_ortamiyla_cozulur() {
        let cocuk = tempfile::tempdir().unwrap();
        let launcher_ev = tempfile::tempdir().unwrap();

        // Çocuğa verilen kök: backend GERÇEKTEN buraya yazar.
        let mut env = BTreeMap::new();
        env.insert(
            install::ENV_DATA_DIR.to_string(),
            cocuk.path().to_string_lossy().into_owned(),
        );

        let dogru = install::backend_log_path_with(
            |k| env.get(k).cloned().or_else(|| std::env::var(k).ok()),
            launcher_ev.path(),
        );
        // Launcher'ın kendi ortamı (PEMF_DATA_DIR YOK) ile çözülen — eski, YANLIŞ yol.
        let yanlis = install::backend_log_path_with(|_| None, launcher_ev.path());

        assert!(
            dogru.starts_with(cocuk.path()),
            "gunluk yolu cocugun PEMF_DATA_DIR'ini ONURLANDIRMIYOR: {dogru:?}"
        );
        assert_ne!(
            dogru, yanlis,
            "cocuk-ortami ile launcher-ortami AYNI yolu verdi → arıza yeniden uretilemiyor, \
             test gercegi olcmuyor"
        );
    }

    /// DENETİM 2026-08-04: `read_tail` `child.stderr`'i okuyordu ama stderr `Stdio::null()`
    /// olduğu için o dal HİÇ çalışmıyordu → backend açılmadığında kullanıcı yalnız "günlüğe bak"
    /// görüyor, hatanın kendisini göremiyordu. Artık gerçek günlüğün sonu hataya konuyor.
    #[test]
    fn gunluk_sonu_hataya_ekleniyor() {
        let d = tempfile::tempdir().unwrap();
        let log = d.path().join("backend_service.log");

        // Dosya yoksa: yalnız yol ipucu (çökmemeli).
        let yok = read_log_tail(&log, 20);
        assert!(yok.contains("backend_service.log"), "yol ipucu yok: {yok}");

        // Gerçek bir başlatma hatası senaryosu.
        let mut icerik = String::new();
        for i in 0..500 {
            icerik.push_str(&format!("2026-08-04 10:00:{i:02} INFO [x] dolgu satiri {i}
"));
        }
        icerik.push_str("2026-08-04 10:01:00 ERROR [uvicorn] [Errno 10048] port 8000 kullanimda
");
        std::fs::write(&log, &icerik).unwrap();

        let t = read_log_tail(&log, 20);
        assert!(
            t.contains("10048") && t.contains("port 8000 kullanimda"),
            "GERCEK hata satiri teshise girmedi: {t}"
        );
        assert!(t.contains("backend_service.log"), "yol ipucu kayboldu");
        // Yalnız son n satır — tüm dosya değil.
        assert!(!t.contains("dolgu satiri 0
"), "tum dosya kopyalanmis");
        assert!(t.lines().count() <= 22, "beklenenden fazla satir: {}", t.lines().count());
    }

    /// Günlük 10 MB'a kadar büyüyebiliyor; teşhis için tamamı OKUNMAMALI (sondan 64 KB pencere).
    #[test]
    fn cok_buyuk_gunluk_tamamen_okunmaz() {
        let d = tempfile::tempdir().unwrap();
        let log = d.path().join("backend_service.log");
        let mut big = String::with_capacity(3 * 1024 * 1024);
        big.push_str("ILK-SATIR-BULUNMAMALI
");
        while big.len() < 3 * 1024 * 1024 {
            big.push_str("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
");
        }
        big.push_str("SON-SATIR-GORUNMELI
");
        std::fs::write(&log, &big).unwrap();

        let t = read_log_tail(&log, 5);
        assert!(t.contains("SON-SATIR-GORUNMELI"), "son satir alinmadi");
        assert!(!t.contains("ILK-SATIR-BULUNMAMALI"), "3 MB'lik gunlugun tamami okunmus");
    }

    /// ⚠️ P1 (denetim 2026-08-04) — "BİLİNMİYOR"u "ÖLÜ" saymak HASTA GÜVENLİĞİ sorunuydu.
    ///
    /// Yük altındaki backend (TCP kabul ediyor ama yanıt yazmıyor) `probe_pemf_backend`'de
    /// `false (2002 ms)` dönüyordu → `clear_port_if_stopped` E-stop adresini siliyordu →
    /// kaldırıcı bobinleri E-stop'suz öldürüyordu. Artık silme kararı YALNIZ "TCP reddedildi".
    #[test]
    fn asili_backend_kesin_olu_sayilmaz() {
        let ln = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = ln.local_addr().unwrap().port();
        // Kabul et ama hiç yanıt yazma (GIL/AI yükü altındaki backend).
        std::thread::spawn(move || {
            let _tut: Vec<_> = ln.incoming().take(4).filter_map(|c| c.ok()).collect();
            std::thread::sleep(Duration::from_secs(20));
        });

        assert!(
            !backend_is_definitely_gone(port),
            "ASILI backend 'kesin olu' sayildi — E-stop adresi silinir, bobinler enerjili oldurulur"
        );
        assert_eq!(
            session_active(port),
            None,
            "ULASILAMAYAN backend 'seans yok' sayildi — sessiz guncelleme tedaviyi keser"
        );
    }

    /// Gerçekten kapalı bir port KESİN ölü sayılmalı (aksi halde ölü adresler birikir).
    #[test]
    fn dinleyici_yoksa_kesin_olu() {
        let ln = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = ln.local_addr().unwrap().port();
        drop(ln);
        // Portun gerçekten boşaldığını teyit et (efemer port yarışına karşı).
        for _ in 0..20 {
            if TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, port)).is_ok() {
                break;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        assert!(backend_is_definitely_gone(port), "kapali port kesin-olu sayilmadi");
    }

    /// ⚠️ P2 (denetim 2026-08-04): E-stop bütçesini 10 sn'ye çıkarıp ikinci deneme eklemek,
    /// YANIT VERMEYEN backend'de blokajı ~21,9 sn'ye çıkarmıştı. Bu çağrı pencere kapanışında
    /// olay-döngüsü thread'inden yapılıyor → istemci donuyor, kullanıcı Görev Yöneticisi'yle
    /// öldürürse yetim backend seri portu tutuyor. Yanıt gelmiyorsa TEKRAR DENENMEMELİ.
    #[test]
    fn yanitsiz_estop_ikinci_kez_denenmez() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::sync::Arc;
        let ln = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = ln.local_addr().unwrap().port();
        let sayac = Arc::new(AtomicUsize::new(0));
        let s2 = sayac.clone();
        std::thread::spawn(move || {
            // Kabul et, isteği oku, ama ASLA yanıt yazma (asılı backend).
            let mut tut = Vec::new();
            for c in ln.incoming() {
                let Ok(mut c) = c else { continue };
                use std::io::Read;
                let mut buf = [0u8; 512];
                if c.read(&mut buf).unwrap_or(0) > 0 {
                    s2.fetch_add(1, Ordering::SeqCst);
                }
                tut.push(c);
            }
        });

        let t = Instant::now();
        safe_stop_coils(port);
        let sure = t.elapsed();

        assert_eq!(
            sayac.load(Ordering::SeqCst),
            1,
            "yanitsiz backend'e IKINCI istek gonderildi — UI donmasi ikiye katlanir"
        );
        assert!(
            sure < Duration::from_secs(ESTOP_TIMEOUT_S + 5),
            "safe_stop_coils cok uzun blokladi: {sure:?}"
        );
    }

    /// P3: gunluk BAYAT ise (backend loglama yapilandirilmadan cokmus) kullaniciya ONCEKI
    /// kosunun satirlari "Son cikti" diye gosteriliyordu — teshis yaniltiyordu.
    #[test]
    fn bayat_gunluk_acikca_isaretlenir() {
        let d = tempfile::tempdir().unwrap();
        let log = d.path().join("backend_service.log");
        std::fs::write(&log, b"2026-08-03 10:00:00 INFO [uvicorn] Application startup complete.
").unwrap();

        // Taze dosya → uyari YOK.
        let taze = read_log_tail(&log, 5);
        assert!(!taze.contains("OLMAYABILIR") && !taze.contains("OLMAYABİLİR"), "taze gunluge bayat uyarisi kondu");

        // mtime'i 1 saat geriye al → BAYAT.
        let eski = std::time::SystemTime::now() - Duration::from_secs(3600);
        let f = std::fs::File::options().write(true).open(&log).unwrap();
        f.set_modified(eski).unwrap();
        drop(f);

        let t = read_log_tail(&log, 5);
        assert!(
            t.contains("OLMAYABİLİR") || t.contains("ONCESINE") || t.contains("ÖNCESİNE"),
            "BAYAT gunluk isaretlenmedi — kullanici onceki kosunun 'startup complete' satirini              bu kosuya ait sanir: {t}"
        );
    }

    #[test]
    fn dolu_port_atlanir() {
        let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let busy = listener.local_addr().unwrap().port();
        let found = find_free_port(busy, 20).unwrap();
        assert_ne!(found, busy, "mesgul port bos sanildi");
    }

    /// 2026-10-18 (auth_session.bin kaybı): pencerede çıkış backend'te `{"cikis": true}` bırakır; launcher bunu `Yok`tan
    /// AYIRMALI (backend yeniden başladıysa `{}` = çıkış DEĞİL). Jeton varsa işaret yok sayılır.
    #[test]
    fn devir_govdesi_cikis_isaretini_oturum_yokundan_AYIRIR() {
        assert!(matches!(devir_govdesini_coz(r#"{"cikis": true}"#), DevirCekme::Cikis));
        assert!(matches!(devir_govdesini_coz("{}"), DevirCekme::Yok));
        assert!(matches!(devir_govdesini_coz(r#"{"cikis": false}"#), DevirCekme::Yok));
        assert!(matches!(devir_govdesini_coz(r#"{"cikis": "true"}"#), DevirCekme::Yok), "yalniz JSON true");
        assert!(matches!(devir_govdesini_coz("bozuk"), DevirCekme::Yok));
        match devir_govdesini_coz(r#"{"access_token":"A","refresh_token":"R","email":"e@k.tr","expires_at":"42","cikis":true}"#) {
            DevirCekme::Oturum(s) => assert_eq!((s.refresh_token.as_str(), s.expires_at), ("R", 42)),
            d => panic!("jetonlu govde oturum sayilmadi: {d:?}"),
        }
        assert!(matches!(devir_govdesini_coz(r#"{"access_token":"A","cikis":true}"#), DevirCekme::Cikis), "eksik jeton = oturum yok");
    }

    #[test]
    fn url_yardimcilari_dogru_bicimde() {
        assert_eq!(health_url(8123), "http://127.0.0.1:8123/api/health");
        assert_eq!(app_url(8123), "http://127.0.0.1:8123/");
        assert_eq!(
            desktop_session_url(8123),
            "http://127.0.0.1:8123/api/auth/desktop-session"
        );
    }

    /// ⚠️ SÖZLEŞME GÜVENLİĞİ: oturum jetonları YALNIZ loopback'e gider.
    #[test]
    fn oturum_hedefi_yalniz_loopback_kabul_eder() {
        for u in [
            "http://127.0.0.1:8000/api/auth/desktop-session",
            "http://127.0.0.1/api/auth/desktop-session",
            "http://[::1]:8000/api/auth/desktop-session",
            "https://127.0.0.1:8443/api/auth/desktop-session",
        ] {
            assert!(is_loopback_http_url(u), "mesru loopback hedefi reddedildi: {u}");
        }
        for u in [
            // LAN / tünel / uzak → jeton ASLA çıkmamalı
            "http://192.168.1.5:8000/api/auth/desktop-session",
            "https://klinik.example.com/api/auth/desktop-session",
            "http://127.0.0.1@evil.example/api/auth/desktop-session",
            "http://evil.example/127.0.0.1/api/auth/desktop-session",
            // hosts dosyasıyla yönlendirilebilir → ad çözümlemesine bağlı adres KABUL EDİLMEZ
            "http://localhost:8000/api/auth/desktop-session",
            "http://127.0.0.1.evil.example/x",
            "file:///c:/x",
            "",
        ] {
            assert!(!is_loopback_http_url(u), "LOOPBACK DISI hedef kabul edildi (jeton sizar): {u}");
        }
    }

    /// Loopback dışı hedefe istek GÖNDERİLMEMELİ — sahte sunucu hiçbir bağlantı görmemeli.
    #[test]
    fn loopback_disi_hedefe_oturum_gonderilmez() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::sync::Arc;

        // Gerçekte loopback OLMAYAN bir adres taklidi: dinleyiciyi 127.0.0.1'de açıyoruz ama
        // URL'de "localhost" kullanıyoruz → politika onu REDDETMELİ (ad çözümlemesine bağlı).
        let l = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = l.local_addr().unwrap().port();
        let sayac = Arc::new(AtomicUsize::new(0));
        let s2 = sayac.clone();
        std::thread::spawn(move || {
            for c in l.incoming() {
                if c.is_ok() {
                    s2.fetch_add(1, Ordering::SeqCst);
                }
            }
        });

        let s = crate::auth::Session {
            access_token: "GIZLI".into(),
            refresh_token: "GIZLI2".into(),
            email: "vet@klinik.com".into(),
            expires_at: 0,
        };
        let r = push_desktop_session_to(&format!("http://localhost:{port}/api/auth/desktop-session"), &s);
        assert!(r.is_err(), "loopback disi hedef kabul edildi");
        std::thread::sleep(Duration::from_millis(200));
        assert_eq!(
            sayac.load(Ordering::SeqCst),
            0,
            "JETON GONDERILDI — sozlesme ihlali (yalniz 127.0.0.1)"
        );
    }

    /// ⚠️ JETON SIZINTISI (denetim 2026-08-06): BAYAT `backend.port`, kimliği doğrulanmamış bir
    /// yerel dinleyiciyi oturum hedefi YAPAMAZ. Dosya "kesin ölü" teyidi olmadan silinmediği için
    /// backend çöktükten sonra diskte kalır; o portu kapan başka bir süreç Supabase jetonlarını
    /// alırdı. Kendi başlattığımız süreç ise yoklanMAdan kabul edilir (yük altındaki backend'de
    /// yanlış-negatif → gereksiz "çift giriş" olmasın).
    #[test]
    fn bayat_port_dosyasi_jeton_hedefi_olamaz() {
        use std::io::Read;
        let l = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let yabanci = l.local_addr().unwrap().port();
        // PEMF OLMAYAN ama HTTP 200 dönen bir yerel servis taklidi.
        std::thread::spawn(move || {
            for stream in l.incoming() {
                let Ok(mut s) = stream else { continue };
                let mut buf = [0u8; 1024];
                let _ = s.read(&mut buf);
                let govde = br#"{"status":"online","service":"BaskaServis"}"#;
                let _ = write!(
                    s,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    govde.len()
                );
                let _ = s.write_all(govde);
            }
        });

        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("backend.port"), yabanci.to_string()).unwrap();
        assert_ne!(
            session_target_port(None, d.path()),
            Some(yabanci),
            "PEMF OLMAYAN yerel servise jeton devredilirdi"
        );
        // Kendi sürecimiz: ağ yoklaması YAPILMADAN kabul (aynı yabancı port bile olsa — burada
        // kimliği health-nonce ile zaten kanıtlanmıştır).
        assert_eq!(session_target_port(Some(yabanci), d.path()), Some(yabanci));
    }

    /// Oturum devri sözleşmedeki gövdeyi POST etmeli; backend ucu YOKSA (404/405) SESSİZCE
    /// başarı sayılmalı — eski base.zip'li kurulumlar açılmaz hale gelmesin.
    #[test]
    fn oturum_devri_sozlesme_govdesini_gonderir() {
        use std::io::Read;
        let l = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = l.local_addr().unwrap().port();
        let (tx, rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let mut ilk = true;
            for stream in l.incoming() {
                let Ok(mut s) = stream else { continue };
                // ⚠️ ureq başlıkları ve gövdeyi AYRI yazabiliyor → tek `read` yalnız başlıkları
                // görür ve test yanlışlıkla "gövde yok" der. Kısa okuma-zaman aşımıyla, gövdenin
                // sonunu ('}') görene kadar biriktir.
                let _ = s.set_read_timeout(Some(Duration::from_millis(500)));
                let mut ham = Vec::new();
                let mut buf = [0u8; 4096];
                loop {
                    match s.read(&mut buf) {
                        Ok(0) | Err(_) => break,
                        Ok(n) => {
                            ham.extend_from_slice(&buf[..n]);
                            if ham.ends_with(b"}") || ham.len() > 8192 {
                                break;
                            }
                        }
                    }
                }
                if ham.is_empty() {
                    continue;
                }
                let _ = tx.send(String::from_utf8_lossy(&ham).into_owned());
                // 1. istek: 200 (yeni backend), 2. istek: 404 (ucu taşımayan eski base.zip).
                let kod = if ilk { "200 OK" } else { "404 Not Found" };
                ilk = false;
                let _ = write!(s, "HTTP/1.1 {kod}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
            }
        });

        let s = crate::auth::Session {
            access_token: "AAA".into(),
            refresh_token: "RRR".into(),
            email: "vet@klinik.com".into(),
            expires_at: 1_900_000_000,
        };
        assert!(push_desktop_session(port, &s).is_ok());
        let req = rx.recv_timeout(Duration::from_secs(5)).expect("oturum POST edilmedi");
        assert!(req.starts_with("POST /api/auth/desktop-session"), "yanlis istek: {req}");
        for alan in ["access_token", "refresh_token", "email", "expires_at", "AAA", "RRR"] {
            assert!(req.contains(alan), "sozlesme alani govdede yok: {alan}");
        }

        // GERİYE UYUM: 404 → sessizce başarı.
        assert!(
            push_desktop_session(port, &s).is_ok(),
            "ucu tasimayan backend'de client HATA verdi — eski kurulumlar acilmaz olur"
        );
    }

    /// [F5] `pull_desktop_session_kisa` geçerli oturumu döndürür VE yanıt YAZMAYAN backend'de
    /// verilen KISA bütçe kadar (≈1 sn) bekler — 5 sn DEĞİL → kapanış son-yakalaması teardown'ı
    /// bloklamaz. (`timeout_s` parametresi hardcode `SESSION_PUSH_TIMEOUT_S`e sabitlenirse stall
    /// dalı ~5 sn'ye çıkar → assert kırmızı: mutasyon kapısı.)
    #[test]
    fn pull_teardown_kisa_timeout_gecerli_oturum_ve_STALL_da_hizli_None() {
        use std::io::{Read, Write};
        // (1) Geçerli oturum sunan backend → Some(doğru jeton)
        let l = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = l.local_addr().unwrap().port();
        std::thread::spawn(move || {
            for stream in l.incoming() {
                let Ok(mut s) = stream else { continue };
                let _ = s.set_read_timeout(Some(Duration::from_millis(300)));
                let mut buf = [0u8; 2048];
                let _ = s.read(&mut buf);
                let body = r#"{"access_token":"AT","refresh_token":"RRR","email":"vet@klinik.tr","expires_at":5000}"#;
                let _ = write!(
                    s,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                    body.len(),
                    body
                );
            }
        });
        let sess =
            pull_desktop_session_kisa(port, PULL_TEARDOWN_TIMEOUT_S).expect("gecerli oturum None dondu");
        assert_eq!(sess.refresh_token, "RRR");
        assert_eq!(sess.expires_at, 5000);

        // (2) STALL: accept eder ama HİÇ yanıt yazmaz → kısa bütçeyle None + HIZLI dön (5 sn değil).
        let stall = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let sport = stall.local_addr().unwrap().port();
        std::thread::spawn(move || {
            for stream in stall.incoming() {
                let Ok(s) = stream else { continue };
                std::thread::sleep(Duration::from_secs(30)); // tut, hiç yazma
                drop(s);
            }
        });
        let t0 = std::time::Instant::now();
        let r = pull_desktop_session_kisa(sport, 1);
        let dt = t0.elapsed();
        assert!(r.is_none(), "yanit yazmayan backend Some dondu");
        assert!(
            dt < Duration::from_secs(3),
            "kisa timeout'a uyulmadi ({dt:?} >= 3s) — teardown son-yakalamasi 5 sn bloklanir"
        );
    }

    /// Sahte backend: her GERÇEK bağlantıya sıradaki yanıt (`None` = isteği okuyup YANITSIZ kapat → hızlı bağlantı hatası).
    /// Gelen istek metinleri kanala yazılır.
    fn sahte_backend(yanitlar: Vec<Option<(u16, &'static str)>>) -> (u16, std::sync::mpsc::Receiver<String>) {
        use std::io::Read;
        let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        let (tx, rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let mut sira = yanitlar.into_iter();
            for stream in listener.incoming() {
                let Ok(mut s) = stream else { continue };
                // Başlık + `Content-Length` kadar gövde (ureq ikisini ayrı yazabilir).
                let mut al: Vec<u8> = Vec::new();
                let mut buf = [0u8; 2048];
                loop {
                    let n = s.read(&mut buf).unwrap_or(0);
                    if n == 0 {
                        break;
                    }
                    al.extend_from_slice(&buf[..n]);
                    let metin = String::from_utf8_lossy(&al).to_string();
                    if let Some(son) = metin.find("\r\n\r\n") {
                        let uzunluk = metin[..son]
                            .lines()
                            .find_map(|l| l.to_ascii_lowercase().strip_prefix("content-length:").map(|v| v.trim().to_string()))
                            .and_then(|v| v.parse::<usize>().ok())
                            .unwrap_or(0);
                        if al.len() >= son + 4 + uzunluk {
                            break;
                        }
                    }
                }
                if al.is_empty() {
                    continue; // boş yoklama bağlantısı
                }
                let _ = tx.send(String::from_utf8_lossy(&al).into_owned());
                match sira.next() {
                    Some(Some((kod, govde))) => {
                        let _ = write!(
                            s,
                            "HTTP/1.1 {kod} X\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{govde}",
                            govde.len()
                        );
                    }
                    Some(None) => drop(s),
                    None => break,
                }
            }
        });
        (port, rx)
    }

    fn istekler(rx: &std::sync::mpsc::Receiver<String>) -> Vec<String> {
        let mut v = Vec::new();
        while let Ok(r) = rx.recv_timeout(Duration::from_millis(300)) {
            v.push(r);
        }
        v
    }

    /// 2026-10-18 (sahip: "uygulama ilk açılışta niye bu uyarıyı veriyor … sürekli çıkmasın"): kapanış durdurması operatörün
    /// ACİL DURDUR ucunu DEĞİL kapanış ucunu, bilinçli JSON onayıyla çağırır; uç doğruladıysa ACİL DURDUR ucu ÇAĞRILMAZ (mandal
    /// diske yazılmaz → sonraki açılışta "önceki oturumda ACİL DURDUR" bandı çıkmaz).
    #[test]
    fn KRITIK_kapanis_durdurmasi_KAPANIS_ucunu_onayla_cagirir_ACIL_DURDUR_ucunu_cagirmaz() {
        let (port, rx) = sahte_backend(vec![Some((200, r#"{"status":"success","confirmed":true,"mandalKalici":false}"#))]);
        safe_stop_coils(port);
        let v = istekler(&rx);
        assert_eq!(v.len(), 1, "fazladan istek: {v:?}");
        assert!(v[0].starts_with("POST /api/hardware/kapanis_durdur "), "yanlış uç: {}", v[0]);
        let kucuk = v[0].to_ascii_lowercase();
        assert!(kucuk.contains("content-type: application/json"), "JSON içerik türü yok: {}", v[0]);
        assert!(v[0].contains(r#"{"onay":true}"#), "onay gövdesi yok: {}", v[0]);
    }

    /// TIBBİ GÜVENLİK: kapanış ucu bu backend'de YOKSA (eski runtime: StaticFiles bilinmeyen POST'a 405) ya da sözleşme dışı 200
    /// dönerse bobin durdurma ATLANMAZ — operatörün ACİL DURDUR ucuna düşülür.
    #[test]
    fn KRITIK_eski_backend_ya_da_sozlesme_disi_yanitta_ACIL_DURDUR_ucuna_duser() {
        for ilk in [(405u16, r#"{"detail":"Method Not Allowed"}"#), (200u16, "<!doctype html><html></html>")] {
            let (port, rx) = sahte_backend(vec![Some(ilk), Some((200, r#"{"status":"success","confirmed":true}"#))]);
            safe_stop_coils(port);
            let v = istekler(&rx);
            assert_eq!(v.len(), 2, "{ilk:?}: istekler {v:?}");
            assert!(v[0].starts_with("POST /api/hardware/kapanis_durdur "), "{}", v[0]);
            assert!(v[1].starts_with("POST /api/hardware/emergency_stop "), "{ilk:?}: ACİL DURDUR'a DÜŞMEDİ: {}", v[1]);
        }
    }

    /// TIBBİ GÜVENLİK: bağlantı HIZLA koparsa (yanıtsız) ACİL DURDUR ucu yine denenir.
    #[test]
    fn KRITIK_kapanis_ucunda_hizli_baglanti_hatasi_ACIL_DURDUR_ucuna_duser() {
        let (port, rx) = sahte_backend(vec![None, Some((200, r#"{"status":"success","confirmed":true}"#))]);
        safe_stop_coils(port);
        let v = istekler(&rx);
        assert_eq!(v.len(), 2, "istekler {v:?}");
        assert!(v[1].starts_with("POST /api/hardware/emergency_stop "), "ACİL DURDUR'a DÜŞMEDİ: {}", v[1]);
    }

    /// TIBBİ GÜVENLİK: safe_stop_coils, süreç öldürülmeden önce bir durdurma ucunu POST etmeli (kapanış ucu yoksa ACİL DURDUR).
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
                // GERÇEK yanıt şekli (apps/backend/servers/api_server.py `emergency_stop`): `confirmed` alanı
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
            .expect("safe_stop_coils durdurma ucunu ÇAĞIRMADI");
        // 2026-10-18: ilk istek kapanış ucudur (bu sahte backend her isteğe `confirmed:true` döner → tek istek).
        assert!(
            req.starts_with("POST /api/hardware/kapanis_durdur"),
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
