//! manifest.json ayrıştırma — v1 (sahadaki) ve v2 (hedef) formatlarının İKİSİ de okunur.
//!
//! v1 (bugün yayında, `client-app-v1.8.0`): platform anahtarları ad-hoc —
//! `base` = Windows, `base_linux` = Linux, `base_mac` = macOS. Sahadaki v1.8.0
//! kurulumları bozulmasın diye desteklenmeye devam eder.
//!
//! v2 (hedef): `runtimes` altında AÇIK platform anahtarları + `models` altında profiller.
//! `"schema": 2` alanıyla ayırt edilir.

use std::collections::HashMap;

use serde::Deserialize;

use crate::platform;

#[derive(Debug, thiserror::Error)]
pub enum ManifestError {
    #[error("manifest JSON olarak ayrıştırılamadı: {0}")]
    Json(#[from] serde_json::Error),
    #[error("manifest'te '{0}' alanı yok")]
    MissingField(&'static str),
    #[error(
        "Bu platform ({platform}) için manifest'te paket YOK. \
         Mevcut anahtarlar: [{available}]. Yanlış platformun paketi KURULMAZ — \
         yayın sürecinde bu platformun base paketi eksik."
    )]
    UnsupportedPlatform { platform: String, available: String },
    #[error("'{profile}' profili manifest'te yok. Mevcut profiller: [{available}]")]
    UnknownProfile { profile: String, available: String },
    #[error("'{key}' kaydının sha256 değeri geçersiz (64 hex bekleniyor, gelen: {got:?})")]
    BadDigest { key: String, got: String },
}

/// İndirilecek tek bir paket (base runtime ya da profil model paketi).
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct Package {
    pub url: String,
    pub sha256: String,
    #[serde(default)]
    pub size: u64,
    #[serde(default = "default_kind")]
    pub kind: String,
}

fn default_kind() -> String {
    "zip".to_string()
}

/// Yayındaki EN SON launcher (client) sürümü + indirme sayfası. Launcher thin-bootstrapper
/// olduğu için kendini güncellemez; açılışta bu alanı kendi sürümüyle kıyaslayıp KULLANICIYA
/// "yeni sürüm var, indir" bildirir (opsiyonel — alan yoksa kontrol sessizce atlanır).
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct LauncherInfo {
    pub version: String,
    #[serde(default)]
    pub url: String,
    /// OTO-GÜNCELLEME: yeni launcher setup'ının DOĞRUDAN indirme URL'i (NSIS `PEMFVetClient-Setup.exe`).
    /// Varsa açılışta sessizce indirilip (host-pinli) SHA doğrulanıp kurulur; yoksa yalnız bildirim.
    #[serde(default)]
    pub installer_url: Option<String>,
    /// Setup exe'nin SHA256'sı — `installer_url` ile birlikte ZORUNLU (imzasız exe'yi çalıştırmadan önce
    /// bütünlük/orijinallik doğrulaması; manifest host-pinli kaynaktan geldiği için sha güven çıpasıdır).
    #[serde(default)]
    pub sha256: Option<String>,
    /// Setup exe boyutu (bayt) — opsiyonel, indirme ilerlemesi/ön-tahsis için.
    #[serde(default)]
    pub size: Option<u64>,
}

/// Formatı ne olursa olsun normalize edilmiş manifest.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Manifest {
    pub version: String,
    pub tag: Option<String>,
    /// platform anahtarı -> base runtime paketi
    pub runtimes: HashMap<String, Package>,
    /// profil adı -> model paketi
    pub models: HashMap<String, Package>,
    /// Yayındaki en son launcher sürümü (opsiyonel; açılışta self-update bildirimi için).
    pub launcher: Option<LauncherInfo>,
    /// Kaynak şema sürümü (1 veya 2) — teşhis/log için.
    pub schema: u8,
}

#[derive(Deserialize)]
struct RawV2 {
    version: String,
    #[serde(default)]
    tag: Option<String>,
    #[serde(default)]
    runtimes: HashMap<String, Package>,
    #[serde(default)]
    models: HashMap<String, Package>,
    #[serde(default)]
    launcher: Option<LauncherInfo>,
}

#[derive(Deserialize)]
struct RawV1 {
    version: String,
    #[serde(default)]
    tag: Option<String>,
    #[serde(default)]
    profiles: HashMap<String, Package>,
    #[serde(default)]
    base: Option<Package>,
    #[serde(default)]
    base_linux: Option<Package>,
    #[serde(default)]
    base_mac: Option<Package>,
    #[serde(default)]
    launcher: Option<LauncherInfo>,
}

impl Manifest {
    pub fn parse(raw: &str) -> Result<Self, ManifestError> {
        let probe: serde_json::Value = serde_json::from_str(raw)?;
        let schema = probe.get("schema").and_then(|v| v.as_u64()).unwrap_or(1);

        let manifest = if schema >= 2 {
            let v2: RawV2 = serde_json::from_str(raw)?;
            Manifest {
                version: v2.version,
                tag: v2.tag,
                runtimes: v2.runtimes,
                models: v2.models,
                launcher: v2.launcher,
                schema: 2,
            }
        } else {
            let v1: RawV1 = serde_json::from_str(raw)?;
            let mut runtimes = HashMap::new();
            // v1 ad-hoc anahtar -> v2 platform anahtarı eşlemesi.
            if let Some(p) = v1.base {
                runtimes.insert(platform::WIN_X64.to_string(), p);
            }
            if let Some(p) = v1.base_linux {
                runtimes.insert(platform::LINUX_X64.to_string(), p);
            }
            if let Some(p) = v1.base_mac {
                runtimes.insert(platform::MAC_ARM64.to_string(), p);
            }
            Manifest {
                version: v1.version,
                tag: v1.tag,
                runtimes,
                models: v1.profiles,
                launcher: v1.launcher,
                schema: 1,
            }
        };

        if manifest.version.is_empty() {
            return Err(ManifestError::MissingField("version"));
        }
        manifest.validate_digests()?;
        Ok(manifest)
    }

    /// Her kaydın sha256'sı 64 hex olmalı. Bozuk digest'i İNDİRMEDEN ÖNCE yakala —
    /// yoksa gigabaytlarca indirip sonunda doğrulama hatası alınır.
    fn validate_digests(&self) -> Result<(), ManifestError> {
        for (key, pkg) in self.runtimes.iter().chain(self.models.iter()) {
            if !is_hex64(&pkg.sha256) {
                return Err(ManifestError::BadDigest {
                    key: key.clone(),
                    got: pkg.sha256.clone(),
                });
            }
        }
        // DENETİM 2026-08-04: doğrulama YALNIZ runtimes+models üzerinde dönüyordu; `launcher.sha256`
        // kapsam DIŞINDAYDI — oysa o, açılışta KULLANICI ONAYI OLMADAN indirilip `/S` ile SESSİZCE
        // kurulan İMZASIZ setup.exe'nin tek güven çıpasıdır. Satır 61-62'deki yorum bu alanı
        // `installer_url` ile birlikte "ZORUNLU" ilan ediyor ama tip `Option<String>` ve parse
        // aşamasında hiçbir zorunluluk yoktu; tek kontrol çalışma zamanında (main.rs, boş-mu) idi.
        // Bozuk digest'i İNDİRMEDEN ÖNCE yakala — paketler için zaten uygulanan ilkenin aynısı.
        if let Some(l) = &self.launcher {
            if l.installer_url.as_deref().is_some_and(|u| !u.trim().is_empty()) {
                let got = l.sha256.clone().unwrap_or_default();
                if !is_hex64(&got) {
                    return Err(ManifestError::BadDigest { key: "launcher".into(), got });
                }
            }
        }
        Ok(())
    }

    /// Bu platformun base paketi. Eşleşme yoksa HATA — asla başka platformun paketine düşme.
    pub fn runtime_for_current_platform(&self) -> Result<&Package, ManifestError> {
        let key = platform::current();
        self.runtimes
            .get(key)
            .ok_or_else(|| ManifestError::UnsupportedPlatform {
                platform: key.to_string(),
                available: sorted_keys(&self.runtimes),
            })
    }

    pub fn model_package(&self, profile: &str) -> Result<&Package, ManifestError> {
        self.models
            .get(profile)
            .ok_or_else(|| ManifestError::UnknownProfile {
                profile: profile.to_string(),
                available: sorted_keys(&self.models),
            })
    }
}

/// 64 haneli, salt-hex bir SHA256 mi?
fn is_hex64(s: &str) -> bool {
    s.len() == 64 && s.chars().all(|c| c.is_ascii_hexdigit())
}

fn sorted_keys(map: &HashMap<String, Package>) -> String {
    let mut keys: Vec<&str> = map.keys().map(|s| s.as_str()).collect();
    keys.sort_unstable();
    keys.join(", ")
}

/// `candidate` sürümü `current`'tan YENİ mi? ("1.9.1" > "1.9.0"). X.Y.Z parçaları sayısal
/// kıyaslanır; eksik parça 0, ayrıştırılamayan parça 0 sayılır → asla panik atmaz (kötü
/// manifest yanlış-güncelleme tetikleyemez). Baştaki `v` yok sayılır. Eşitlikte `false`.
pub fn is_newer(candidate: &str, current: &str) -> bool {
    fn parts(v: &str) -> Vec<u64> {
        v.trim()
            .trim_start_matches('v')
            .split('.')
            .map(|p| {
                p.chars()
                    .take_while(|c| c.is_ascii_digit())
                    .collect::<String>()
                    .parse()
                    .unwrap_or(0)
            })
            .collect()
    }
    let (a, b) = (parts(candidate), parts(current));
    for i in 0..a.len().max(b.len()) {
        let (x, y) = (a.get(i).copied().unwrap_or(0), b.get(i).copied().unwrap_or(0));
        if x != y {
            return x > y;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    const D1: &str = "3f77eba1614dd794dfb36eda1c4275de917cc7a1f3c5bfa827860c2cd9014149";
    const D2: &str = "1b49fd93454c4ce558edde8cc345eb3e4aec673167033000e19dd42106aeaf53";

    fn v1_json(extra_base: &str) -> String {
        format!(
            r#"{{
                "version": "1.8.0",
                "tag": "client-app-v1.8.0",
                "profiles": {{ "vet": {{"url":"https://x/vet.zip","sha256":"{D1}","size":1,"kind":"zip"}} }},
                "base": {{"url":"https://x/base.zip","sha256":"{D2}","size":2,"kind":"zip"}}
                {extra_base}
            }}"#
        )
    }

    #[test]
    fn v1_ad_hoc_anahtarlari_platform_anahtarina_esler() {
        let raw = v1_json(&format!(
            r#", "base_linux": {{"url":"https://x/base-linux.zip","sha256":"{D1}","size":3,"kind":"zip"}}"#
        ));
        let m = Manifest::parse(&raw).unwrap();
        assert_eq!(m.schema, 1);
        assert!(m.runtimes.contains_key(platform::WIN_X64));
        assert!(m.runtimes.contains_key(platform::LINUX_X64));
        assert_eq!(m.models["vet"].url, "https://x/vet.zip");
    }

    #[test]
    fn v2_dogrudan_okunur() {
        let raw = format!(
            r#"{{
                "schema": 2, "version": "1.9.0",
                "runtimes": {{ "mac-arm64": {{"url":"https://x/base-mac.zip","sha256":"{D1}","size":1}} }},
                "models": {{ "vet": {{"url":"https://x/vet.zip","sha256":"{D2}","size":2}} }}
            }}"#
        );
        let m = Manifest::parse(&raw).unwrap();
        assert_eq!(m.schema, 2);
        assert_eq!(m.runtimes["mac-arm64"].kind, "zip", "kind varsayilani zip olmali");
    }

    /// EN KRİTİK DAVRANIŞ: platform paketi yoksa başka platformunkine DÜŞMEZ.
    #[test]
    fn eksik_platform_sessizce_baska_pakete_dusmez() {
        // Yalnız Windows base'i var; mac/linux'ta çalışırken hata beklenir.
        let raw = v1_json("");
        let m = Manifest::parse(&raw).unwrap();
        let res = m.runtime_for_current_platform();
        if platform::current() == platform::WIN_X64 {
            assert!(res.is_ok());
        } else {
            let err = res.unwrap_err();
            assert!(matches!(err, ManifestError::UnsupportedPlatform { .. }));
            // Hata mesajı hangi anahtarların mevcut olduğunu SÖYLEMELİ (teşhis edilebilirlik).
            assert!(err.to_string().contains(platform::WIN_X64));
        }
    }

    #[test]
    fn bozuk_sha256_indirmeden_once_yakalanir() {
        let raw = r#"{"version":"1.0","base":{"url":"https://x/b.zip","sha256":"kisa","size":1}}"#;
        let err = Manifest::parse(raw).unwrap_err();
        assert!(matches!(err, ManifestError::BadDigest { .. }));
    }

    #[test]
    fn bilinmeyen_profil_mevcutlari_listeler() {
        let m = Manifest::parse(&v1_json("")).unwrap();
        let err = m.model_package("research").unwrap_err();
        assert!(err.to_string().contains("vet"));
    }

    /// Sahadaki GERÇEK manifest ayrıştırılabiliyor mu? (geriye uyumun asıl testi)
    #[test]
    fn depodaki_gercek_manifest_ayristirilir() {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../pemf-app-packages/manifest.json");
        let Ok(raw) = std::fs::read_to_string(path) else {
            eprintln!("atlandi: {path} yok");
            return;
        };
        let m = Manifest::parse(&raw).expect("gercek manifest ayristirilamadi");
        assert_eq!(m.schema, 2);
        assert_eq!(m.version, "1.8.0");
        assert!(m.runtimes.contains_key(platform::WIN_X64), "base -> win-x64");
        assert!(m.runtimes.contains_key(platform::LINUX_X64), "base_linux -> linux-x64");
        // base_mac artık YAYINDA (2026-07-26 notarize'li) → mac-arm64 runtime bulunmalı.
        assert!(m.runtimes.contains_key(platform::MAC_ARM64), "base_mac yayinlandi -> mac-arm64");
        for p in ["home", "vet", "research"] {
            assert!(m.models.contains_key(p), "{p} profili eksik");
        }
        // Self-update alanı eklendi → gerçek manifest launcher sürümünü taşımalı (bildirimi besler).
        let l = m.launcher.clone().expect("gerçek manifest'te launcher alanı olmali");
        assert!(!l.version.is_empty(), "launcher sürümü bos olmamali");

        // ⚠️ DENETİM 2026-08-04 (#97/#99) REGRESYON KAPISI: kaynak-URL pinlemesi daraltıldı
        // (github.com yolu repo'ya sabit, joker sonek kaynak için geçersiz). YAYINDAKİ manifest'in
        // HER URL'si bu kontrolü GEÇMELİ — geçmezse sahadaki tüm indirmeler kırılır. Pin bir daha
        // sıkılaştırılırsa bu test önce KIRILIR, kullanıcı değil.
        for (key, pkg) in m.runtimes.iter().chain(m.models.iter()) {
            crate::net::validate_download_source(&pkg.url)
                .unwrap_or_else(|e| panic!("YAYINDAKI '{key}' url'i kaynak-pinlemesini GECMIYOR: {} → {e}", pkg.url));
        }
        if let Some(iu) = l.installer_url.as_deref().filter(|u| !u.is_empty()) {
            crate::net::validate_download_source(iu)
                .unwrap_or_else(|e| panic!("YAYINDAKI launcher installer_url pinlemeyi GECMIYOR: {iu} → {e}"));
        }
    }

    /// DENETİM 2026-08-04: `installer_url` VARSA `sha256` de ZORUNLU ve 64-hex olmalı —
    /// o exe imzasızdır, kullanıcı onayı olmadan `/S` ile sessizce kurulur ve TEK güven çıpası
    /// bu digest'tir. Bozuk/eksik digest 2.7 MB indirildikten SONRA değil, ayrıştırmada yakalanmalı.
    #[test]
    fn launcher_installer_sha256i_da_dogrulanir() {
        let mk = |launcher: &str| {
            format!(
                r#"{{ "schema":2, "version":"1.9.1",
                     "runtimes": {{ "win-x64": {{"url":"https://x/b.zip","sha256":"{D1}","size":1}} }},
                     "models": {{ "vet": {{"url":"https://x/v.zip","sha256":"{D2}","size":1}} }},
                     "launcher": {launcher} }}"#
            )
        };

        // installer_url VAR + sha256 YOK → REDDET
        let err = Manifest::parse(&mk(
            r#"{ "version":"1.9.3", "installer_url":"https://github.com/o/r/releases/download/v/S.exe" }"#,
        ))
        .unwrap_err();
        assert!(matches!(err, ManifestError::BadDigest { .. }), "eksik sha kabul edildi: {err:?}");

        // installer_url VAR + sha256 BOZUK (kısa) → REDDET
        let err = Manifest::parse(&mk(
            r#"{ "version":"1.9.3", "installer_url":"https://x/S.exe", "sha256":"kisa" }"#,
        ))
        .unwrap_err();
        assert!(matches!(err, ManifestError::BadDigest { .. }));

        // installer_url YOK (yalnız bildirim) → sha256 gerekmez, GEÇMELİ (geriye uyum)
        let m = Manifest::parse(&mk(r#"{ "version":"1.9.3", "url":"https://pemf-vet-web.vercel.app/" }"#))
            .expect("installer_url'siz launcher blogu kabul edilmeli");
        assert_eq!(m.launcher.unwrap().version, "1.9.3");

        // installer_url + geçerli sha256 → GEÇMELİ
        let m = Manifest::parse(&mk(&format!(
            r#"{{ "version":"1.9.3", "installer_url":"https://x/S.exe", "sha256":"{D1}", "size":1 }}"#
        )))
        .expect("gecerli digest reddedildi");
        assert!(m.launcher.unwrap().sha256.is_some());
    }

    #[test]
    fn surum_karsilastirma_dogru() {
        assert!(is_newer("1.9.1", "1.9.0"));
        assert!(is_newer("1.10.0", "1.9.9"), "10 > 9 SAYISAL olmali (leksik degil)");
        assert!(is_newer("2.0.0", "1.9.9"));
        assert!(!is_newer("1.9.0", "1.9.0"), "esit -> guncelleme YOK");
        assert!(!is_newer("1.9.0", "1.9.1"), "eski -> guncelleme YOK");
        assert!(is_newer("v1.9.1", "1.9.0"), "'v' on eki yok sayilmali");
        assert!(!is_newer("bozuk", "1.0.0"), "ayristirilamaz=0 -> yanlis-guncelleme YOK");
        assert!(is_newer("1.9.1", ""), "bos current = 0.0.0");
    }

    #[test]
    fn launcher_alani_opsiyonel_ve_ayristirilir() {
        // Alan YOKSA None (geriye uyum: launcher alanı olmayan eski manifest kırılmaz).
        let m = Manifest::parse(&v1_json("")).unwrap();
        assert!(m.launcher.is_none(), "launcher alanı yoksa None olmali");
        // Alan VARSA sürüm + url okunur.
        let raw = format!(
            r#"{{ "schema":2, "version":"1.9.1",
                 "runtimes": {{ "win-x64": {{"url":"https://x/b.zip","sha256":"{D1}","size":1}} }},
                 "models": {{ "vet": {{"url":"https://x/v.zip","sha256":"{D2}","size":1}} }},
                 "launcher": {{ "version":"1.9.1", "url":"https://pemf-vet-web.vercel.app/" }} }}"#
        );
        let m = Manifest::parse(&raw).unwrap();
        let l = m.launcher.expect("launcher alanı okunmali");
        assert_eq!(l.version, "1.9.1");
        assert!(l.url.contains("vercel.app"));
        // installer_url/sha256/size YOKSA None (geriye uyum: yalnız bildirim).
        assert!(l.installer_url.is_none() && l.sha256.is_none() && l.size.is_none());
    }

    /// OTO-GÜNCELLEME: launcher.installer_url + sha256 + size varsa ayrıştırılır (apply_self_update besler).
    #[test]
    fn launcher_installer_alanlari_ayristirilir() {
        let raw = format!(
            r#"{{ "schema":2, "version":"1.9.1",
                 "runtimes": {{ "win-x64": {{"url":"https://x/b.zip","sha256":"{D1}","size":1}} }},
                 "models": {{ "vet": {{"url":"https://x/v.zip","sha256":"{D2}","size":1}} }},
                 "launcher": {{ "version":"1.9.3", "url":"https://pemf-vet-web.vercel.app/",
                    "installer_url":"https://github.com/mert61-python/pemf-update/releases/download/launcher-v1.9.3/PEMFVetClient-Setup.exe",
                    "sha256":"{D1}", "size":2596084 }} }}"#
        );
        let m = Manifest::parse(&raw).unwrap();
        let l = m.launcher.expect("launcher alanı okunmali");
        assert_eq!(l.version, "1.9.3");
        assert_eq!(
            l.installer_url.as_deref(),
            Some("https://github.com/mert61-python/pemf-update/releases/download/launcher-v1.9.3/PEMFVetClient-Setup.exe")
        );
        assert!(l.sha256.is_some());
        assert_eq!(l.size, Some(2596084));
    }
}
