// Author: mertaygn, cglrgrkn
//! Supabase Auth (REST) — Client giriş ekranının ağ katmanı.
//!
//! NEDEN RUST'TA, NEDEN WEBVIEW'DEN DEĞİL: launcher penceresinin CSP'si `default-src 'self'`
//! (bkz. `app/tauri.conf.json`) ve `connect-src` hiç tanımlı değil → UI'dan Supabase'e `fetch`
//! İMKÂNSIZ. Ayrıca capability listesi boş olduğundan olay dinleme de yok; UI yalnız `invoke`
//! kullanabiliyor. Bu yüzden giriş bir `#[tauri::command]` üzerinden buradan yapılır.
//!
//! ⚠️ NEDEN AYRI AJAN + AYRI PİN: `net::ALLOWED_HOSTS` listesi `servers/update_manager.py::
//! _ALLOWED_UPDATE_HOSTS` ile BİREBİR eş tutuluyor ve o liste "imzasız setup.exe indirilebilecek
//! yerler" anlamına geliyor. Supabase'i oraya eklemek, zehirli bir manifest'in Supabase Storage'dan
//! paket indirtmesine kapı açardı. Auth kendi host pinini kendi uygular ve indirme yoluna DOKUNMAZ.
//!
//! GÜVENLİK: `Session`'ın `Debug`'ı ELLE yazılmıştır ve token alanlarını `***` gösterir —
//! yanlışlıkla loglanamaz (sözleşme: "token'lar ne INFO ne DEBUG loglanmaz").

use std::time::Duration;

/// Supabase proje referansı — DERLEME ZAMANI sabiti.
///
/// ⚠️ Bu değer manifest'ten/ağdan GELMEZ. Gelseydi, ele geçmiş bir manifest giriş ekranını
/// saldırganın Supabase projesine yönlendirip veteriner e-posta+parolasını toplayabilirdi
/// (kimlik avı). Mobil/web istemcilerle aynı proje: `frontend/src/services/supabaseAuth.ts`.
pub const PROJECT_REF: &str = "wmsxonunkphjeregpvuj";

/// Publishable ("anon") anahtar — GİZLİ DEĞİLDİR: web ve mobil istemcilerin bundle'ında da
/// düz metindir ve tek başına hiçbir veriye erişim vermez (yetki RLS ile sunucu tarafında).
pub const ANON_KEY: &str = "sb_publishable_D2SaRML_PIhRtr3kqlXxaw_1cS75GKT";

/// Giriş isteği bütçeleri — indirme yolundan (15/60 sn) çok daha kısa: bunlar küçük JSON
/// istekleridir ve kullanıcı giriş düğmesine basmış BEKLİYOR.
const CONNECT_TIMEOUT_S: u64 = 6;
const READ_TIMEOUT_S: u64 = 10;
const TOTAL_TIMEOUT_S: u64 = 10;
/// Duvar saati tavanı (DNS'e deadline uygulanamıyor — bkz. `net::with_wall_budget`).
///
/// ⚠️ Bu değer AÇILIŞ yolunu da bağlıyor: kayıtlı jetonun süresi dolmuşsa client, sessiz
/// yenileme için EN FAZLA bu kadar bekler ve sonra "çevrimdışı, kayıtlı oturumla devam" der.
/// Uzun tutmak, az önce düzeltilen açılış kilidini kimlik katmanında geri getirirdi.
pub const WALL_BUDGET_S: u64 = 12;

/// Beklenen Supabase host'u.
pub fn expected_host() -> String {
    format!("{PROJECT_REF}.supabase.co")
}

/// Auth REST kökü.
pub fn auth_base() -> String {
    format!("https://{}/auth/v1", expected_host())
}

#[derive(Debug, thiserror::Error)]
pub enum AuthError {
    /// Host/şema/yol pini tutmadı — istek HİÇ gönderilmedi.
    #[error("Giriş sunucusu adresi doğrulanamadı — işlem iptal edildi (güvenlik)")]
    UrlPin,
    #[error("İnternet bağlantısı yok — çevrimdışı devam edebilirsiniz")]
    Offline,
    #[error("E-posta veya parola hatalı")]
    BadCredentials,
    /// ⚠️ 2026-08-10: BOŞ girdi eskiden `BadCredentials` dönüyordu — yani arayüzde bir hata
    /// (alan okunamadı, otomatik doldurma state'i kaçtı, yanlış id) kullanıcıya "parolanız
    /// yanlış" diye görünüyordu ve HİÇBİR yerde ayırt edilemiyordu. İki durum farklı: biri
    /// kullanıcının, diğeri bizim hatamız. Ayrı tutulunca saha kaydında da ayrışır.
    #[error("E-posta ve parola boş bırakılamaz")]
    MissingInput,
    #[error("E-posta adresiniz doğrulanmamış — gelen kutunuzu kontrol edin")]
    EmailNotConfirmed,
    #[error("Çok fazla deneme yapıldı — birkaç dakika sonra tekrar deneyin")]
    RateLimited,
    /// Kayıtlı oturum sunucu tarafında geçersiz (parola değişti / oturum kapatıldı).
    #[error("Kayıtlı oturum geçersiz — lütfen tekrar giriş yapın")]
    SessionRevoked,
    /// ⚠️ HTTP gövdesi KASITLI olarak yansıtılmıyor: yanıtta e-posta/token parçaları olabilir
    /// ve UI hata metnini ekrana basıyor (index.html `fail`).
    #[error("Giriş sunucusu hata verdi (HTTP {0})")]
    Server(u16),
    #[error("Giriş yanıtı okunamadı")]
    Malformed,
}

/// Doğrulanmış oturum. Backend'e devredilen alanlar E-ÖZELLİĞİ SÖZLEŞMESİYLE birebir aynı:
/// `{access_token, refresh_token, email, expires_at}`.
#[derive(Clone, serde::Serialize, serde::Deserialize)]
pub struct Session {
    pub access_token: String,
    pub refresh_token: String,
    pub email: String,
    /// Unix saniye (Supabase `expires_at`). 0 = bilinmiyor.
    #[serde(default)]
    pub expires_at: i64,
}

/// ⚠️ ELLE yazıldı: türetilmiş `Debug` token'ları düz metin basardı ve bir `{:?}` / `unwrap` /
/// panik mesajı onları günlüğe düşürürdü. Sözleşme bunu açıkça yasaklıyor.
impl std::fmt::Debug for Session {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Session")
            .field("email", &self.email)
            .field("access_token", &"***")
            .field("refresh_token", &"***")
            .field("expires_at", &self.expires_at)
            .finish()
    }
}

/// Şu anki Unix saniye.
pub fn now_unix() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

impl Session {
    /// Erişim jetonu (yakında) doluyor mu? 120 sn emniyet payı — saat kaymasına toleranslı.
    pub fn needs_refresh(&self, now: i64) -> bool {
        self.expires_at > 0 && self.expires_at - 120 <= now
    }
}

/// Supabase URL pini — istek gönderilmeden ÖNCE çalışır.
///
/// Kurallar: yalnız `https://<PROJECT_REF>.supabase.co` (port YOK, userinfo YOK) ve yol
/// `/auth/v1/` ile başlamalı. Nokta-segmenti / yüzde-kodlu ayraç reddedilir: ureq isteği
/// göndermeden önce yolu RFC 3986 `remove_dot_segments` ile normalize eder, yani ham metin
/// üzerinde `starts_with` yapan bir pin atlatılabilir (aynı hata `net.rs`'te P0 olarak düzeltildi).
pub fn validate_supabase_url(url: &str) -> Result<(), AuthError> {
    let rest = url.strip_prefix("https://").ok_or(AuthError::UrlPin)?;
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    if authority.is_empty() || authority.contains('@') {
        return Err(AuthError::UrlPin);
    }
    // Port bile kabul edilmiyor: meşru Supabase URL'lerinde yok, "github.com:80@evil" sınıfı
    // karışıklıkları kökten keser.
    if !authority.eq_ignore_ascii_case(&expected_host()) {
        return Err(AuthError::UrlPin);
    }
    let path = &rest[authority.len()..];
    let low = path.to_ascii_lowercase();
    if low.contains("%2e") || low.contains("%2f") || low.contains("%5c") || path.contains('\\') {
        return Err(AuthError::UrlPin);
    }
    if path.split(['?', '#']).next().unwrap_or("").split('/').skip(1).any(|s| s == "." || s == ".." || s.is_empty())
    {
        return Err(AuthError::UrlPin);
    }
    if !path.starts_with("/auth/v1/") {
        return Err(AuthError::UrlPin);
    }
    Ok(())
}

fn agent() -> ureq::Agent {
    ureq::AgentBuilder::new()
        .timeout_connect(Duration::from_secs(CONNECT_TIMEOUT_S))
        .timeout_read(Duration::from_secs(READ_TIMEOUT_S))
        .timeout(Duration::from_secs(TOTAL_TIMEOUT_S))
        .https_only(true)
        .build()
}

/// HTTP durum + gövdesinden KULLANICIYA GÖSTERİLECEK hatayı türet (saf → birim-testlenebilir).
///
/// Gövde yalnız SINIFLANDIRMA için okunur, mesaja ASLA konmaz.
pub fn classify_error(status: u16, body: &str) -> AuthError {
    let v: Option<serde_json::Value> = serde_json::from_str(body).ok();
    let al = |k: &str| -> String {
        v.as_ref()
            .and_then(|v| v.get(k))
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_ascii_lowercase()
    };
    let kod = {
        let a = al("error_code");
        if a.is_empty() { al("error") } else { a }
    };
    let msg = {
        let a = al("msg");
        if a.is_empty() { al("error_description") } else { a }
    };

    if kod.contains("email_not_confirmed") || msg.contains("email not confirmed") {
        return AuthError::EmailNotConfirmed;
    }
    if status == 429 || kod.contains("rate_limit") || msg.contains("rate limit") {
        return AuthError::RateLimited;
    }
    // `invalid_grant` hem "parola yanlış" hem "refresh token geçersiz" için gelir; ayrımı
    // çağıran yapar (login → BadCredentials, refresh → SessionRevoked).
    if status == 400 || status == 401 || status == 403 {
        return AuthError::BadCredentials;
    }
    AuthError::Server(status)
}

/// Auth ucuna JSON POST. `bearer`: kullanıcının access_token'ı (logout için); yoksa anon anahtar.
fn post_json(
    url: &str,
    body: &str,
    bearer: Option<&str>,
) -> Result<serde_json::Value, AuthError> {
    validate_supabase_url(url)?;
    let req = agent()
        .post(url)
        .set("apikey", ANON_KEY)
        .set("Authorization", &format!("Bearer {}", bearer.unwrap_or(ANON_KEY)))
        .set("Content-Type", "application/json");
    // ureq'in `json` özelliği bu projede KAPALI (Cargo.lock'ta serde_json ureq bağımlılığı yok)
    // → gövde elle serileştirilip `send_string` ile gönderilir.
    match req.send_string(body) {
        Ok(r) => {
            // 204 (logout) gövdesizdir → boş nesne dön.
            let txt = r.into_string().unwrap_or_default();
            if txt.trim().is_empty() {
                return Ok(serde_json::Value::Object(Default::default()));
            }
            serde_json::from_str(&txt).map_err(|_| AuthError::Malformed)
        }
        Err(ureq::Error::Status(status, r)) => {
            let txt = r.into_string().unwrap_or_default();
            Err(classify_error(status, &txt))
        }
        // Bağlantı kurulamadı/koptu → ÇEVRİMDIŞI. (Ayrıntı mesaja konmaz: ureq hata metni URL
        // ve bazen başlık parçaları içerir.)
        Err(_) => Err(AuthError::Offline),
    }
}

/// Supabase yanıtından `Session` üret. `fallback_email`: yanıt `user.email` vermezse kullanılır.
fn session_from_json(v: &serde_json::Value, fallback_email: &str) -> Result<Session, AuthError> {
    let s = |k: &str| v.get(k).and_then(|x| x.as_str()).unwrap_or("").to_string();
    let access = s("access_token");
    let refresh = s("refresh_token");
    if access.is_empty() || refresh.is_empty() {
        return Err(AuthError::Malformed);
    }
    let email = v
        .get("user")
        .and_then(|u| u.get("email"))
        .and_then(|e| e.as_str())
        .map(str::to_owned)
        .filter(|e| !e.is_empty())
        .unwrap_or_else(|| fallback_email.to_string());
    let expires_at = v
        .get("expires_at")
        .and_then(|x| x.as_i64())
        .or_else(|| v.get("expires_in").and_then(|x| x.as_i64()).map(|s| now_unix() + s))
        .unwrap_or(0);
    Ok(Session { access_token: access, refresh_token: refresh, email, expires_at })
}

/// Bloklayan bir auth çağrısını DUVAR SAATİNE bağla.
///
/// Neden gerekli: ureq DNS çözümlemesine deadline uygulayamıyor (bkz. `net::with_wall_budget`).
/// Zaman aşımı burada ÇEVRİMDIŞI'ya eşlenir — kullanıcı açısından doğru olan budur: sunucuya
/// ulaşılamadı. İş thread'i arkada kendi zaman aşımıyla biter.
fn with_budget<T, F>(f: F) -> Result<T, AuthError>
where
    F: FnOnce() -> Result<T, AuthError> + Send + 'static,
    T: Send + 'static,
{
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let _ = tx.send(f());
    });
    rx.recv_timeout(Duration::from_secs(WALL_BUDGET_S))
        .unwrap_or(Err(AuthError::Offline))
}

/// `login` + duvar saati bütçesi (UI'nın çağırması gereken sürüm).
pub fn login_budgeted(email: &str, password: &str) -> Result<Session, AuthError> {
    let (e, p) = (email.to_string(), password.to_string());
    with_budget(move || login(&e, &p))
}

/// `refresh` + duvar saati bütçesi — AÇILIŞ yolunda çalışır, bloklamamalı.
pub fn refresh_budgeted(refresh_token: &str, bilinen_eposta: &str) -> Result<Session, AuthError> {
    let (r, e) = (refresh_token.to_string(), bilinen_eposta.to_string());
    with_budget(move || refresh(&r, &e))
}

/// E-posta + parola ile giriş (`grant_type=password`).
pub fn login(email: &str, password: &str) -> Result<Session, AuthError> {
    let email = email.trim();
    if email.is_empty() || password.is_empty() {
        return Err(AuthError::MissingInput);
    }
    let url = format!("{}/token?grant_type=password", auth_base());
    let body = serde_json::json!({ "email": email, "password": password }).to_string();
    let v = post_json(&url, &body, None)?;
    session_from_json(&v, email)
}

/// Kayıtlı `refresh_token` ile SESSİZ yenileme ("beni hatırla" açılış yolu).
pub fn refresh(refresh_token: &str, bilinen_eposta: &str) -> Result<Session, AuthError> {
    if refresh_token.trim().is_empty() {
        return Err(AuthError::SessionRevoked);
    }
    let url = format!("{}/token?grant_type=refresh_token", auth_base());
    let body = serde_json::json!({ "refresh_token": refresh_token }).to_string();
    match post_json(&url, &body, None) {
        Ok(v) => session_from_json(&v, bilinen_eposta),
        // Yenileme yolunda "geçersiz kimlik" = jeton iptal edilmiş demektir (kullanıcı parola
        // girmedi ki hatalı olsun). Çağıranın kaydı silebilmesi için AYRI hata.
        Err(AuthError::BadCredentials) => Err(AuthError::SessionRevoked),
        Err(e) => Err(e),
    }
}

/// Sunucu tarafında oturumu kapat. BEST-EFFORT: ağ yoksa yerel temizlik yine yapılır
/// (çağıran hatayı yutabilir) — kullanıcı çevrimdışıyken "çıkış yapamıyorum" durumuna düşmemeli.
///
/// ⚠️ KAPSAM `local` (denetim 2026-08-18): GoTrue `/logout` çağrısında kapsam VERİLMEZSE
/// varsayılan `global`dir ve kullanıcının TÜM refresh token'larını iptal eder. Üç istemci de AYNI
/// Supabase projesini kullanıyor (masaüstü burası, mobil `pf/src/services/supabaseAuth.ts`, web
/// `pemf-vet-web/src/lib/supabase.ts`), dolayısıyla klinikte "Çıkış"a basmak veteriner hekimin
/// TELEFONUNDAKİ oturumu da düşürüyordu — ve tersi. Yerel çıkış yeterli: bu cihazın jetonu zaten
/// `secret_store`dan siliniyor. (Cihaz devri/kaldırma gibi "her yerden at" senaryosu AYRI bir
/// akıştır; oraya karışmaz.)
pub const LOGOUT_SCOPE: &str = "local";

/// `logout`un GERÇEKTEN çağırdığı URL. AYRI fonksiyon çünkü test edilebilir olması gerekiyor:
/// URL'i testte yeniden kurmak TOTOLOJİK bir kapı olurdu (kapsamı `logout` gövdesinden silen bir
/// mutasyon sessizce geçerdi — ölçüldü).
fn logout_url() -> String {
    format!("{}/logout?scope={}", auth_base(), LOGOUT_SCOPE)
}

pub fn logout(access_token: &str) -> Result<(), AuthError> {
    if access_token.trim().is_empty() {
        return Ok(());
    }
    post_json(&logout_url(), "{}", Some(access_token)).map(|_| ())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// ÇIKIŞ KAPSAMI: `/logout` kapsamsız çağrılırsa GoTrue varsayılanı `global`dir ve aynı
    /// hesabın MOBİL + WEB oturumlarını da iptal eder (üçü aynı Supabase projesi). Klinikteki
    /// çıkış, hekimin telefonunu düşürmemeli.
    #[test]
    fn cikis_yalniz_bu_cihazi_kapatir() {
        // ⚠️ `logout_url()` ÇAĞRILIR — URL testte yeniden KURULMAZ. Yeniden kurmak, kapsamı
        // `logout` gövdesinden silen mutasyonu kaçıran totolojik bir kapı olurdu.
        let url = logout_url();
        assert!(url.contains("scope=local"), "cikis kapsami 'local' degil -> mobil/web oturumu duser: {url}");
        // KARŞIT-KANIT: yol hâlâ /logout olmalı (kapsamı daraltmak, çıkışı kaldırmak değildir).
        assert!(url.contains("/logout?"), "logout yolu bozuldu: {url}");
        assert!(url.starts_with(&auth_base()), "logout baska bir host'a gidiyor: {url}");
    }

    // ═══════════════════════════════════════════════════════════════════════════════════════
    // BOŞ GİRDİ ≠ YANLIŞ PAROLA (2026-08-10 saha hatası)
    //
    // Kullanıcı doğru parolayı yazdı, "E-posta veya parola hatalı" aldı; parola alanını silip
    // AYNI şeyi tekrar yazınca giriş yaptı. Yani ilk istekte gönderilen parola, yazdığı şey
    // değildi. Bu ihtimali kovalarken görüldü ki BOŞ girdi de aynı mesajı üretiyordu — yani
    // arayüz tarafındaki bir hata (alan okunamadı / otomatik doldurma state'i kaçtı) tam olarak
    // "parolanız yanlış" gibi görünüyor ve HİÇBİR kayıtta ayırt edilemiyordu.
    // ═══════════════════════════════════════════════════════════════════════════════════════

    #[test]
    fn KRITIK_bos_girdi_YANLIS_PAROLA_gibi_raporlanmaz() {
        for (e, p) in [("", "sifre"), ("a@b.com", ""), ("", ""), ("   ", "sifre")] {
            match login(e, p) {
                Err(AuthError::MissingInput) => {}
                other => panic!(
                    "bos girdi ({e:?},{p:?}) icin MissingInput bekleniyordu, gelen: {other:?} — \
                     arayuz hatasi kullaniciya 'parolaniz yanlis' diye gorunur"
                ),
            }
        }
    }

    #[test]
    fn bos_girdi_ag_a_CIKMAZ() {
        // Doğrulama isteği HİÇ gönderilmemeli: aksi hâlde boş parolayla Supabase'in oran
        // sınırlayıcısı tüketilir ve gerçek deneme "çok fazla deneme" ile reddedilir.
        // (Ağ yoksa bile hızlı dönmesi bunun kanıtı: `Offline` değil `MissingInput` geliyor.)
        assert!(matches!(login("a@b.com", ""), Err(AuthError::MissingInput)));
    }

    #[test]
    fn bos_girdi_mesaji_yanlis_parola_mesajindan_FARKLI() {
        let bos = AuthError::MissingInput.to_string();
        let yanlis = AuthError::BadCredentials.to_string();
        assert_ne!(bos, yanlis, "iki durum ayni metni veriyorsa ayirmanin anlami yok");
        // UI `doLogin` yalnız "parola hatalı" gördüğünde alanı temizler; boş-girdi mesajı o
        // dizeyi İÇERMEMELİ, yoksa kullanıcının yazdığı e-posta da boşuna silinir.
        assert!(!bos.contains("parola hatalı"), "bos-girdi mesaji UI temizleme kosuluna takiliyor");
    }

    #[test]
    fn gercek_kimlik_hatasi_HALA_BadCredentials() {
        // Regresyon: ayrım yaparken sunucunun 400/401/403'ü yanlışlıkla MissingInput'a kaymamalı.
        for s in [400u16, 401, 403] {
            assert!(matches!(classify_error(s, "{}"), AuthError::BadCredentials), "HTTP {s}");
        }
    }

    /// GÜVENLİK: Supabase pini yalnız DERLEME-ZAMANI proje referansını kabul etmeli.
    /// Kaçırılırsa: kimlik avı — veteriner e-posta+parolası saldırgana gider.
    #[test]
    fn supabase_url_pini_yalniz_kendi_projesini_kabul_eder() {
        // Gerçek uçlar GEÇMELİ.
        for u in [
            "https://wmsxonunkphjeregpvuj.supabase.co/auth/v1/token?grant_type=password",
            "https://wmsxonunkphjeregpvuj.supabase.co/auth/v1/token?grant_type=refresh_token",
            "https://wmsxonunkphjeregpvuj.supabase.co/auth/v1/logout",
        ] {
            assert!(validate_supabase_url(u).is_ok(), "gercek uc reddedildi: {u}");
        }
        // BAŞKA proje / host / şema / userinfo / benzer-isim / port / traversal → REDDET.
        for u in [
            "https://saldirgan.supabase.co/auth/v1/token?grant_type=password",
            "https://wmsxonunkphjeregpvuj.supabase.co.evil.example/auth/v1/token",
            "https://evil.example/auth/v1/token",
            "http://wmsxonunkphjeregpvuj.supabase.co/auth/v1/token",
            "https://evil.example@wmsxonunkphjeregpvuj.supabase.co/auth/v1/token",
            "https://wmsxonunkphjeregpvuj.supabase.co@evil.example/auth/v1/token",
            "https://wmsxonunkphjeregpvuj.supabase.co:8443/auth/v1/token",
            "https://wmsxonunkphjeregpvuj.supabase.co/auth/v1/../../evil",
            "https://wmsxonunkphjeregpvuj.supabase.co/auth/v1/%2e%2e/evil",
            "https://wmsxonunkphjeregpvuj.supabase.co/rest/v1/patients",
            "",
        ] {
            assert!(
                matches!(validate_supabase_url(u), Err(AuthError::UrlPin)),
                "PIN ATLATILDI (kimlik avi riski): {u}"
            );
        }
    }

    /// Ağ hiç kurulmadan da pin uygulanmalı — istek GÖNDERİLMEMELİ.
    #[test]
    fn pin_disi_urlye_istek_gonderilmez() {
        let t = std::time::Instant::now();
        let r = post_json("https://evil.example/auth/v1/token", "{}", None);
        assert!(matches!(r, Err(AuthError::UrlPin)));
        assert!(t.elapsed() < Duration::from_secs(2), "pin disi URL icin ag beklendi");
    }

    /// ⚠️ SÖZLEŞME: "token'lar ASLA loglanmaz". Türetilmiş `Debug` bunu ihlal ederdi.
    #[test]
    fn session_debug_ciktisinda_token_gecmez() {
        let s = Session {
            access_token: "eyJHASSAS-ACCESS".into(),
            refresh_token: "GIZLI-REFRESH".into(),
            email: "vet@ornek.com".into(),
            expires_at: 1_800_000_000,
        };
        let d = format!("{s:?}");
        assert!(!d.contains("eyJHASSAS-ACCESS"), "access_token Debug'a sizdi: {d}");
        assert!(!d.contains("GIZLI-REFRESH"), "refresh_token Debug'a sizdi: {d}");
        assert!(d.contains("***"));
        assert!(d.contains("vet@ornek.com"), "e-posta gorunmeli (kullanici kimligi, sir degil)");
    }

    /// Hata sınıflandırması kullanıcıya DOĞRU Türkçe mesajı vermeli ve HTTP gövdesini
    /// YANSITMAMALI (gövdede e-posta/jeton parçası olabilir; UI hatayı ekrana basıyor).
    #[test]
    fn hata_siniflandirmasi_govdeyi_yansitmaz() {
        let e = classify_error(400, r#"{"error":"invalid_grant","error_description":"Invalid login credentials"}"#);
        assert!(matches!(e, AuthError::BadCredentials));

        let e = classify_error(400, r#"{"code":400,"error_code":"email_not_confirmed","msg":"Email not confirmed"}"#);
        assert!(matches!(e, AuthError::EmailNotConfirmed));

        let e = classify_error(429, r#"{"error_code":"over_request_rate_limit","msg":"..."}"#);
        assert!(matches!(e, AuthError::RateLimited));

        let e = classify_error(503, "gateway down");
        assert!(matches!(e, AuthError::Server(503)));

        // Gövdedeki hassas metin mesaja SIZMAMALI.
        let e = classify_error(400, r#"{"error":"invalid_grant","error_description":"user vet@klinik.com token eyJABC"}"#);
        let m = e.to_string();
        assert!(!m.contains("vet@klinik.com") && !m.contains("eyJABC"), "govde mesaja sizdi: {m}");
    }

    /// Yanıt ayrıştırma: `expires_at` yoksa `expires_in`'den türetilmeli, eksik jeton = Malformed.
    #[test]
    fn oturum_yanitindan_dogru_ayristirilir() {
        let v: serde_json::Value = serde_json::from_str(
            r#"{"access_token":"A","refresh_token":"R","expires_in":3600,"user":{"email":"a@b.com"}}"#,
        )
        .unwrap();
        let s = session_from_json(&v, "yedek@b.com").unwrap();
        assert_eq!(s.email, "a@b.com");
        assert!(s.expires_at > now_unix() + 3000, "expires_in'den expires_at turetilmedi");

        // user.email yoksa girilen e-posta kullanılır.
        let v: serde_json::Value =
            serde_json::from_str(r#"{"access_token":"A","refresh_token":"R","expires_at":123}"#).unwrap();
        assert_eq!(session_from_json(&v, "yedek@b.com").unwrap().email, "yedek@b.com");

        // Jeton eksik → Malformed (yarım oturumu ASLA geçerli sayma).
        let v: serde_json::Value = serde_json::from_str(r#"{"access_token":"A"}"#).unwrap();
        assert!(matches!(session_from_json(&v, "x"), Err(AuthError::Malformed)));
    }

    /// ⚠️ UI SÖZLEŞMESİ: `index.html::doLogin` çevrimdışı dalını BU MESAJIN İÇERİĞİNE bakarak
    /// ayırt ediyor ("Çevrimdışı başlat" çıkış yolunu o dal açıyor). Metin yeniden yazılırsa
    /// internetsiz klinikte kurulu cihazın açılma yolu SESSİZCE kaybolurdu → burada kilitli.
    #[test]
    fn cevrimdisi_mesaji_ui_sozlesmesini_korur() {
        assert!(
            AuthError::Offline.to_string().contains("İnternet bağlantısı yok"),
            "UI'nin aradigi metin degisti — 'Cevrimdisi baslat' cikis yolu kaybolur: {}",
            AuthError::Offline
        );
    }

    /// ⚠️ UI SÖZLEŞMESİ #2 (2026-08-10 saha hatası): `index.html::doLogin` kimlik hatasında
    /// parola alanını temizleyip odaklamak için BU MESAJIN İÇERİĞİNE ("parola hatalı") bakıyor.
    /// Mesaj yeniden yazılırsa temizleme sessizce kaybolur ve hata yeniden ortaya çıkar:
    /// kullanıcı görünmeyen bir kalıntının üstüne yazmaya devam eder.
    #[test]
    fn KRITIK_kimlik_hatasi_mesaji_UI_temizleme_sozlesmesini_korur() {
        let m = AuthError::BadCredentials.to_string();
        assert!(
            m.contains("parola hatalı"),
            "UI'nin aradigi metin degisti — hatali giriste parola alani TEMIZLENMEZ olur: {m}"
        );
    }

    /// UI dosyası gerçekten bu davranışları taşıyor mu? (kaynak-metin kapısı — düzeltme
    /// silinirse burada patlar; UI'nin kendi test koşucusu yok.)
    #[test]
    fn ui_giris_ekrani_duzeltmeleri_YERINDE() {
        let p = concat!(env!("CARGO_MANIFEST_DIR"), "/../app/ui/index.html");
        let s = std::fs::read_to_string(p).expect("index.html okunamadi");
        for (parca, neden) in [
            // ⚠️ ID'yi ATTRIBUTE olarak ara. İlk yazımda yalnız `"btn-pw-toggle"` dizesi
            // aranıyordu; JS tarafındaki `$("btn-pw-toggle")` çağrısı bunu tek başına
            // karşılıyordu → HTML'den düğme SİLİNSE bile kapı yeşil kalıyordu (mutasyon
            // turunda ölçüldü). Düğmenin GERÇEKTEN var olduğunu id niteliği kanıtlar.
            (r#"id="btn-pw-toggle""#, "parola goster/gizle DUGMESI yok — maskeli alanda hata gorunmez kalir"),
            ("function parolaUyarisi", "gorunmez karakter/bosluk uyarisi fonksiyonu YOK"),
            ("loginPwSpace:", "bosluk uyari metni (sozlukte) YOK"),
            ("loginPwInvisible:", "gorunmez-karakter uyari metni (sozlukte) YOK"),
        ] {
            assert!(s.contains(parca), "{neden} ({parca})");
        }
        // Düğmenin bir İŞİ de olmalı: tıklanınca alanın tipini değiştirmeli.
        assert!(
            s.contains(r#"$("btn-pw-toggle").onclick"#) && s.contains(r#"$("login-pass").type"#),
            "goster/gizle dugmesi var ama parola alaninin tipini DEGISTIRMIYOR (olu dugme)"
        );
    }

    /// PROFİLLER BAĞIMSIZ SEÇİLİR (2026-08-10 sahip kararı).
    ///
    /// Eskiden `vet: ["home"]` idi → "Veteriner" seçilince "Ev Sahibi" ZORLA ekleniyordu ve
    /// yalnız Veteriner + Araştırma kurmak isteyen kullanıcı bunu yapamıyor, gereksiz 503 MB
    /// indiriyordu. Zorunluluk kaldırıldı; işlevsel bağ (AI Pro organ lokalizasyonu home'daki
    /// `inference_cat_organ` modellerini kullanır — uzak zip dizininden doğrulandı) ENGELLEMEYEN
    /// bir bilgi notuna dönüştü.
    #[test]
    fn KRITIK_profiller_BAGIMSIZ_secilebilir() {
        let p = concat!(env!("CARGO_MANIFEST_DIR"), "/../app/ui/index.html");
        let s = std::fs::read_to_string(p).expect("index.html okunamadi");

        let sat = s
            .lines()
            .find(|l| l.contains("const PROFILE_DEPS"))
            .expect("PROFILE_DEPS bulunamadi");
        // Hiçbir profilin ZORUNLU bağımlılığı olmamalı: `{ home: [], vet: [], research: [] }`
        assert!(
            !sat.contains("[\""),
            "bir profil ZORUNLU bagimlilik tasiyor -> kullanici istemedigi profili kurmaya zorlanir: {sat}"
        );
        // ✅ 2026-08-10: İŞLEVSEL bağ da KALKTI. `vet → home` bağı, AI Pro'nun organ
        // lokalizasyonunu çalıştıran `inference_cat_organ` modellerinin `home.zip` içinde
        // olmasından geliyordu; o ortak model ÇEKİRDEĞE alındı (make_base_zip::CORE_MODELS).
        // Artık profiller arasında HİÇBİR bağ yok — ne zorunlu ne işlevsel.
        let soft = s
            .lines()
            .find(|l| l.contains("const PROFILE_SOFT_DEPS"))
            .expect("PROFILE_SOFT_DEPS bulunamadi");
        assert!(
            !soft.contains(":"),
            "profiller arasi ISLEVSEL bag geri gelmis: {soft} — ortak model cekirdege alinmali, \
             kullanici istemedigi profili kurmaya ZORLANMAMALI"
        );
        // Mekanizma DURMALI: ileride yeni bir ortak model çıkarsa zorlamak yerine BİLGİ verilir.
        assert!(
            s.contains("function depNotice"),
            "bilgi-notu mekanizmasi silinmis — sonraki ortak bagimlilik SESSIZCE bozar"
        );
        // `installed` bir DİZİdir; `.has()` TypeError atar (yazarken yakalandı).
        assert!(
            !s.contains("installed.has("),
            "`installed` DIZI — `.has()` calisma aninda TypeError atar"
        );
        // Hatalı girişte alan TEMİZLENMELİ.
        //
        // ⚠️ İlk yazımda dosyadaki İLK `} catch (e) {` aranıyordu — o BAŞKA bir fonksiyonun
        // catch'i çıktı ve test yanlış sebeple kırıldı. Kaynak-metin iddiası neyi incelediğini
        // kesin bilmeli: `doLogin`in GÖVDESİNE sabitle, sonra onun catch'ine bak.
        let bas = s.find("async function doLogin()").expect("doLogin bulunamadi");
        let govde = &s[bas..];
        let son = govde.find("\n      }\n").map(|i| bas + i).unwrap_or(s.len());
        let dologin = &s[bas..son];
        let catch_ = dologin.find("} catch (e) {").expect("doLogin icinde catch yok");
        let hata_dali = &dologin[catch_..];
        assert!(
            hata_dali.contains(r#"$("login-pass").value = """#),
            "hatali giriste parola alani TEMIZLENMIYOR — kullanici gorunmeyen kalintinin ustune yazar"
        );
        assert!(
            hata_dali.contains("parolaUyarisi("),
            "hata dalinda gorunmez-karakter uyarisi cagrilmiyor"
        );
    }

    #[test]
    fn yenileme_esigi_emniyet_payiyla_calisir() {
        let now = 1_000_000i64;
        let mk = |exp| Session {
            access_token: "a".into(),
            refresh_token: "r".into(),
            email: "e".into(),
            expires_at: exp,
        };
        assert!(mk(now - 10).needs_refresh(now), "SURESI DOLMUS jeton yenilenmiyor");
        assert!(mk(now + 60).needs_refresh(now), "60 sn kalmis jeton yenilenmiyor (emniyet payi)");
        assert!(!mk(now + 3600).needs_refresh(now), "taze jeton bosuna yenileniyor");
        // expires_at bilinmiyorsa (0) yenilemeye ZORLAMA — çevrimdışı kullanıcıyı kilitler.
        assert!(!mk(0).needs_refresh(now));
    }
}
