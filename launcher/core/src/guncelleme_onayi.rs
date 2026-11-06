// Author: mertaygn, cglrgrkn
//! GÜNCELLEME ONAYI — sahip Y253 / Y254 (2026-11-06).
//!
//! Sahip (Y253): "yeni sürüm kontrolünden sonra yeni güncelleme varsa yapılsın indirilsin mi diye kullanıcı onayı sorulmalı …
//! otomatik yapmamalı; kullanıcı onaylarsa süreç otomatik devam etmeli … bir sonraki açılışta kurulacak süreç yerine oto yeniden
//! başlasın uygulama". Bu, SAHİP KARARI 2026-08-08'i ("arka planda indir, bir sonraki açılışta kur") DEĞİŞTİRİR. O kararın
//! gerekçesi KORUNUR: soru açılışı BLOKLAMAZ — arayüz soruyu bloklamayan bir kartta sorar, "Başlat" açık kalır.
//!
//! Y254 cevapları: (a) HEPSİ TEK PENCEREDE (başlatıcı + uygulama / bağımlılık katmanları + profil paketleri; sürüm X → Y, paket
//! adları, inecek toplam boyut, kısa sürüm notu) · (b) "Şimdi değil" → bir SONRAKİ açılışta yeniden sorulur, uygulama açık
//! kaldıkça en çok GÜNDE BİR hatırlatılır (arayüz) · (c) ZORUNLU (manifest `min_supported_version` kurulu sürümden yeni) ONAYSIZ
//! iner, ekranda bildirilir, etkin seans bitince yeniden başlatır; normal güncelleme onaysız İNMEZ.
//!
//! Bu modül UI'dan bağımsız SAF karar + tek dosyalık kayıttır (headless test edilir):
//!  * [`karar`] — Yok / Sor / Onayli / Zorunlu;
//!  * [`ozet`] — onay penceresinin içeriği;
//!  * [`OnayKaydi`] — onay → başlatıcı kendini kurup YENİDEN başlarken katman kurulumunun SORMADAN sürmesi (tek akış, tek
//!    yeniden başlatma: önce katmanlar önbelleğe iner, sonra başlatıcı kurulur ve yeniden başlar, yeni başlatıcı önbellekteki
//!    katmanları onay sormadan kurar ve uygulamayı açar).
//! Etkin seans / yakma / yanıtsız backend kapısı (`aktif_seans_kapisi`) ve kurulum yolları (sağlık kapısı, geri alma, atomik takas,
//! döngü kırıcı, `buildId`) bu modülde DEĞİL — onlar AYNEN kalır; bu modül yalnız "sorulsun mu, ne sorulsun" kararını verir.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::flow::UpdatePlan;
use crate::manifest::Manifest;

/// Kurulum kökünde onay kaydının dosya adı.
pub const ONAY_DOSYASI: &str = "guncelleme_onayi.json";
/// Onay kaydının azami yaşı (sn). Daha eski kayıt TAŞINMAZ: kullanıcı haftalar önce verdiği onayla habersiz kurulum görmez.
pub const ONAY_AZAMI_YAS_S: u64 = 7 * 24 * 60 * 60;
/// Saat ileri / geri kaydıysa (kayıt "gelecekte") bu kadarına göz yumulur; ötesi geçersiz.
const SAAT_KAYMASI_TOLERANSI_S: u64 = 24 * 60 * 60;

/// Pencerede ne yapılacak.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Karar {
    /// Güncellenecek bir şey yok.
    Yok,
    /// Kullanıcıya sor (normal güncelleme) — onaysız İNDİRME YOK.
    Sor,
    /// Önceki açılışta onaylandı, başlatıcı yeniden başladı → katman kurulumu SORMADAN sürer.
    Onayli,
    /// Zorunlu güvenlik güncellemesi (`min_supported_version`) → SORMADAN iner, ekranda bildirilir.
    Zorunlu,
}

/// Saf karar tablosu.
///
/// * `baslatici_var` — başlatıcının kendi güncellemesi (yayındaki sürüm YENİ ve otomatik kuruluma izinli).
/// * `katman_var` — uygulama / bağımlılık katmanı ya da kurulu profil paketi bayat (döngü kırıcı durdurmadıysa).
/// * `zorunlu` — kurulu uygulama `min_supported_version`'ın altında.
/// * `katman_onayli` — bu başlatıcıya taşınmış, BU katman hedefi için verilmiş onay kaydı.
///
/// ⚠️ Taşınan onay yalnız KATMANI kapsar: araya yeni bir başlatıcı yayını girdiyse (`baslatici_var`) yeniden sorulur.
pub fn karar(baslatici_var: bool, katman_var: bool, zorunlu: bool, katman_onayli: bool) -> Karar {
    if !baslatici_var && !katman_var {
        return Karar::Yok;
    }
    if zorunlu {
        return Karar::Zorunlu;
    }
    if katman_onayli && katman_var && !baslatici_var {
        return Karar::Onayli;
    }
    Karar::Sor
}

/// Onay kaydı: `{launcherHedefi, katmanHedefi, zaman}`.
///
/// * `launcher_hedefi` — onaylanan başlatıcı sürümü (`None` = bu onayda başlatıcı güncellemesi yoktu);
/// * `katman_hedefi` — onaylanan katman hedefi (`UpdatePlan::hedef`; boş = bu onayda katman yoktu);
/// * `zaman` — onay anı (unix sn).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OnayKaydi {
    pub launcher_hedefi: Option<String>,
    pub katman_hedefi: String,
    pub zaman: u64,
}

fn kayit_yolu(install_root: &Path) -> PathBuf {
    install_root.join(ONAY_DOSYASI)
}

/// Kaydı ATOMİK yaz (geçici dosya + yeniden adlandırma): yarım yazılmış kayıt okunamaz → taşınmaz (soru yeniden sorulur).
pub fn kaydet(install_root: &Path, kayit: &OnayKaydi) -> std::io::Result<()> {
    std::fs::create_dir_all(install_root)?;
    let json = serde_json::to_string(kayit).map_err(std::io::Error::other)?;
    let gecici = install_root.join(format!("{ONAY_DOSYASI}.tmp"));
    std::fs::write(&gecici, json)?;
    std::fs::rename(&gecici, kayit_yolu(install_root))
}

/// Kaydı oku; yok / bozuk → `None` (bozuk kayıt "onay yok" sayılır — fail-safe: yeniden sorulur).
pub fn oku(install_root: &Path) -> Option<OnayKaydi> {
    let s = std::fs::read_to_string(kayit_yolu(install_root)).ok()?;
    serde_json::from_str(&s).ok()
}

/// Kaydı sil (yoksa sessiz).
pub fn temizle(install_root: &Path) {
    let _ = std::fs::remove_file(kayit_yolu(install_root));
}

/// Kayıt yaş sınırı içinde mi? (saat geri alınmışsa ya da kayıt "gelecekteyse" tolerans dışında geçersiz)
pub fn yas_gecerli(kayit: &OnayKaydi, simdi: u64) -> bool {
    kayit.zaman <= simdi.saturating_add(SAAT_KAYMASI_TOLERANSI_S) && simdi.saturating_sub(kayit.zaman) <= ONAY_AZAMI_YAS_S
}

/// Kayıt BU başlatıcıya taşındı mı? — onaylanan başlatıcı hedefine ULAŞILDI (ya da onayda başlatıcı yoktu) ve kayıt taze.
/// Hedefe ulaşılmadıysa (kurulum başarısız / henüz yeniden başlamadı) kayıt bu başlatıcı için GEÇERSİZDİR.
pub fn bu_baslaticiya_tasindi(kayit: &OnayKaydi, kendi_launcher: &str, simdi: u64) -> bool {
    yas_gecerli(kayit, simdi) && kayit.launcher_hedefi.as_deref().map_or(true, |h| h == kendi_launcher)
}

/// Taşınan kayıt BU katman hedefini kapsıyor mu? (boş hedef = onayda katman yoktu → kapsamaz; yayın değiştiyse kapsamaz)
pub fn katman_onayli(kayit: &OnayKaydi, kendi_launcher: &str, plan_hedefi: &str, simdi: u64) -> bool {
    bu_baslaticiya_tasindi(kayit, kendi_launcher, simdi) && !kayit.katman_hedefi.is_empty() && kayit.katman_hedefi == plan_hedefi
}

/// Onay penceresinin başlatıcı satırı.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BaslaticiOzeti {
    pub suanki: String,
    pub yeni: String,
    pub boyut: u64,
    pub installer_url: String,
    pub sha256: String,
    pub not_tr: Option<String>,
    pub not_en: Option<String>,
}

/// Onay penceresinin uygulama satırı.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UygulamaOzeti {
    pub suanki: String,
    pub yeni: String,
    pub not_tr: Option<String>,
    pub not_en: Option<String>,
}

/// Onay penceresinin tamamı (arayüz JSON'u; camelCase).
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Ozet {
    pub karar: Karar,
    pub baslatici: Option<BaslaticiOzeti>,
    pub uygulama: Option<UygulamaOzeti>,
    /// Bağımlılık katmanı (Python / torch …) da iniyor mu — boyutu büyük, kullanıcı bilmeli.
    pub bagimliliklar: bool,
    /// Yenilenecek KURULU profil paketleri (anahtar; arayüz adını çevirir).
    pub profiller: Vec<String>,
    /// İnecek toplam bayt (başlatıcı kurucusu + önbellekte olmayan katman / profil paketleri).
    pub toplam_bayt: u64,
    /// Katman / profil işi var mı (döngü kırıcı durdurduysa `false`, `katman_durduruldu` `true`).
    pub katman_gerekli: bool,
    /// Gereken katman / profil paketlerinin hepsi önbellekte mi (indirme adımı atlanır).
    pub katman_onbellekte: bool,
    /// Döngü kırıcı (C2) otomatik kurulumu durdurdu — arayüz bildirir, kurmaz.
    pub katman_durduruldu: bool,
    pub zorunlu: bool,
    /// Bu başlatıcıya taşınmış bir onay kaydı var (onaylı akışın sonunda uygulama kendiliğinden açılır).
    pub tasinan: bool,
}

/// Pencere içeriğini kur (SAF — ağa / diske çıkmaz; çağıran manifest'i, planı ve kaydı verir).
///
/// `launcher_otomatik` = başlatıcı güncellemesi otomatik kuruluma izinli mi (deneme sınırı + `rollout` dilimi;
/// `install::selfupdate_auto_allowed` / `install::rollout_dilimi`). İzinsizse başlatıcı satırı pencereye GİRMEZ
/// (arayüz eski "yeni sürüm yayınlandı" bildirimini gösterir).
pub fn ozet(
    manifest: &Manifest,
    plan: &UpdatePlan,
    kendi_launcher: &str,
    kurulu_surum: &str,
    launcher_otomatik: bool,
    kayit: Option<&OnayKaydi>,
    simdi: u64,
) -> Ozet {
    let baslatici = manifest
        .launcher_guncellemesi(kendi_launcher)
        .filter(|_| launcher_otomatik)
        .and_then(|l| {
            let url = l.installer_url.as_deref().map(str::trim).filter(|u| !u.is_empty())?;
            let sha = l.sha256.as_deref().map(str::trim).filter(|s| !s.is_empty())?;
            Some(BaslaticiOzeti {
                suanki: kendi_launcher.to_string(),
                yeni: l.version.clone(),
                boyut: l.size.unwrap_or(0),
                installer_url: url.to_string(),
                sha256: sha.to_string(),
                not_tr: l.notes.clone(),
                not_en: l.notes_en.clone(),
            })
        });
    let katman_gerekli = plan.needed() && !plan.otomatik_durduruldu;
    let uygulama = (katman_gerekli && (plan.app || plan.base)).then(|| UygulamaOzeti {
        suanki: kurulu_surum.to_string(),
        yeni: manifest.version.clone(),
        not_tr: manifest.notes.clone(),
        not_en: manifest.notes_en.clone(),
    });
    let tasinan = kayit.is_some_and(|k| bu_baslaticiya_tasindi(k, kendi_launcher, simdi));
    let onayli = kayit.is_some_and(|k| katman_onayli(k, kendi_launcher, &plan.hedef, simdi));
    let toplam_bayt =
        baslatici.as_ref().map_or(0, |b| b.boyut) + if katman_gerekli { plan.indirilecek } else { 0 };
    Ozet {
        karar: karar(baslatici.is_some(), katman_gerekli, plan.zorunlu, onayli),
        baslatici,
        uygulama,
        bagimliliklar: katman_gerekli && plan.deps,
        profiller: if katman_gerekli { plan.profiles.clone() } else { Vec::new() },
        toplam_bayt,
        katman_gerekli,
        katman_onbellekte: katman_gerekli && plan.cached,
        katman_durduruldu: plan.needed() && plan.otomatik_durduruldu,
        zorunlu: plan.zorunlu,
        tasinan,
    }
}

/// Onaylanan pencere için kaydı kur: başlatıcı hedefi + (katman işi varsa) BU planın hedefi.
pub fn onay_kaydi_kur(plan: &UpdatePlan, launcher_hedefi: Option<&str>, simdi: u64) -> OnayKaydi {
    let katman = plan.needed() && !plan.otomatik_durduruldu;
    OnayKaydi {
        launcher_hedefi: launcher_hedefi.map(str::to_string),
        katman_hedefi: if katman { plan.hedef.clone() } else { String::new() },
        zaman: simdi,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::install;
    use std::fs;

    const SHA_A: &str = "aa7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
    const SHA_B: &str = "bb7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
    const SHA_C: &str = "cc7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
    const SIMDI: u64 = 1_800_000_000;

    fn manifest_json(launcher: Option<(&str, bool)>, min: Option<&str>, notlu: bool) -> String {
        let plat = crate::platform::current();
        let l = match launcher {
            Some((v, kurucu)) => {
                let k = if kurucu {
                    format!(r#", "installer_url": "https://github.com/a/s.exe", "sha256": "{SHA_C}", "size": 2000"#)
                } else {
                    String::new()
                };
                let n = if notlu { r#", "notes": "başlatıcı notu", "notes_en": "launcher note""# } else { "" };
                format!(r#", "launcher": {{ "version": "{v}", "url": "https://github.com/a/s.exe"{k}{n} }}"#)
            }
            None => String::new(),
        };
        let m = min.map(|v| format!(r#", "min_supported_version": "{v}""#)).unwrap_or_default();
        let n = if notlu { r#", "notes": "uygulama notu", "notes_en": "app note""# } else { "" };
        format!(
            r#"{{ "schema": 2, "version": "1.9.60"{l}{m}{n},
                  "layers": {{ "{plat}": {{
                      "deps": {{ "url": "https://github.com/a/base-deps.zip", "sha256": "{SHA_A}", "size": 900 }},
                      "app":  {{ "url": "https://github.com/a/base-app.zip",  "sha256": "{SHA_B}", "size": 70 }} }} }},
                  "models": {{ "vet": {{ "url": "https://github.com/a/vet.zip", "sha256": "{SHA_C}", "size": 30 }} }} }}"#
        )
    }

    /// Kurulu cihaz: backend exe + VERSION + deps güncel (SHA_A), app eski, `vet` profili eski.
    fn sahte_kurulum(root: &Path, surum: &str) {
        let exe = install::backend_path(root);
        fs::create_dir_all(exe.parent().unwrap()).unwrap();
        fs::write(&exe, b"x").unwrap();
        let v = install::runtime_dir(root).join("PEMF_Backend").join("_internal");
        fs::create_dir_all(&v).unwrap();
        fs::write(v.join("VERSION"), surum).unwrap();
        install::record_layer_sha(root, "deps", SHA_A);
        install::record_layer_sha(root, "app", SHA_A);
    }

    fn plan_ve_ozet(root: &Path, m: &str, kendi: &str, otomatik: bool, kayit: Option<&OnayKaydi>) -> (UpdatePlan, Ozet) {
        let plan = crate::flow::pending_updates(m, root).unwrap();
        let man = Manifest::parse(m).unwrap();
        let oz = ozet(&man, &plan, kendi, &install::kurulu_surum(root), otomatik, kayit, SIMDI);
        (plan, oz)
    }

    // ── karar tablosu ────────────────────────────────────────────────────────────────────────────

    #[test]
    fn KRITIK_normal_guncelleme_SORULUR_onaysiz_yol_yok() {
        assert_eq!(karar(true, false, false, false), Karar::Sor, "yalnız başlatıcı");
        assert_eq!(karar(false, true, false, false), Karar::Sor, "yalnız katman");
        assert_eq!(karar(true, true, false, false), Karar::Sor, "ikisi birlikte TEK soru");
        assert_eq!(karar(false, false, false, false), Karar::Yok);
        assert_eq!(karar(false, false, true, true), Karar::Yok, "iş yokken zorunlu / onay bir şey indirmez");
    }

    #[test]
    fn KRITIK_zorunlu_SORMADAN_iner() {
        for (b, k) in [(true, false), (false, true), (true, true)] {
            assert_eq!(karar(b, k, true, false), Karar::Zorunlu, "b={b} k={k}");
            assert_eq!(karar(b, k, true, true), Karar::Zorunlu, "b={b} k={k} (onay kaydı zorunluyu değiştirmez)");
        }
    }

    #[test]
    fn KRITIK_tasinan_onay_yalniz_katmani_kapsar_yeni_baslatici_yeniden_sorulur() {
        assert_eq!(karar(false, true, false, true), Karar::Onayli, "başlatıcı yeniden başladı → katman SORMADAN sürer");
        assert_eq!(karar(true, true, false, true), Karar::Sor, "araya yeni başlatıcı yayını girdi → yeniden sor");
    }

    // ── onay kaydı ───────────────────────────────────────────────────────────────────────────────

    #[test]
    fn kayit_atomik_yazilir_okunur_silinir_bozuk_kayit_onay_SAYILMAZ() {
        let d = tempfile::tempdir().unwrap();
        assert_eq!(oku(d.path()), None);
        let k = OnayKaydi { launcher_hedefi: Some("1.9.55".into()), katman_hedefi: "app:x|deps:y".into(), zaman: SIMDI };
        kaydet(d.path(), &k).unwrap();
        assert_eq!(oku(d.path()), Some(k));
        assert!(!d.path().join(format!("{ONAY_DOSYASI}.tmp")).exists(), "geçici dosya kaldı");
        fs::write(d.path().join(ONAY_DOSYASI), "{bozuk").unwrap();
        assert_eq!(oku(d.path()), None, "bozuk kayıt onay sayıldı");
        temizle(d.path());
        assert!(!d.path().join(ONAY_DOSYASI).exists());
        temizle(d.path()); // yokken sessiz
    }

    #[test]
    fn KRITIK_kayit_yalniz_hedef_baslaticiya_ULASILINCA_tasinir() {
        let k = OnayKaydi { launcher_hedefi: Some("1.9.55".into()), katman_hedefi: "H".into(), zaman: SIMDI };
        assert!(!bu_baslaticiya_tasindi(&k, "1.9.54", SIMDI), "eski başlatıcı (kurulum olmadı) onayı taşıdı");
        assert!(bu_baslaticiya_tasindi(&k, "1.9.55", SIMDI));
        assert!(katman_onayli(&k, "1.9.55", "H", SIMDI));
        assert!(!katman_onayli(&k, "1.9.55", "BASKA", SIMDI), "yayın değişti — yeni katman hedefi onaysız kurulacaktı");
        let yalniz_baslatici = OnayKaydi { launcher_hedefi: Some("1.9.55".into()), katman_hedefi: String::new(), zaman: SIMDI };
        assert!(!katman_onayli(&yalniz_baslatici, "1.9.55", "", SIMDI), "boş katman hedefi katman onayı sayıldı");
        assert!(!katman_onayli(&yalniz_baslatici, "1.9.55", "H", SIMDI), "başlatıcı onayı katmanı kapsadı");
        let yalniz_katman = OnayKaydi { launcher_hedefi: None, katman_hedefi: "H".into(), zaman: SIMDI };
        assert!(katman_onayli(&yalniz_katman, "1.9.54", "H", SIMDI));
    }

    #[test]
    fn kayit_yasi_sinirli_saat_kaymasi_toleransli() {
        let k = |z| OnayKaydi { launcher_hedefi: None, katman_hedefi: "H".into(), zaman: z };
        assert!(yas_gecerli(&k(SIMDI - ONAY_AZAMI_YAS_S), SIMDI));
        assert!(!yas_gecerli(&k(SIMDI - ONAY_AZAMI_YAS_S - 1), SIMDI), "haftalar önceki onay taşındı");
        assert!(yas_gecerli(&k(SIMDI + SAAT_KAYMASI_TOLERANSI_S), SIMDI));
        assert!(!yas_gecerli(&k(SIMDI + SAAT_KAYMASI_TOLERANSI_S + 1), SIMDI), "gelecekteki kayıt geçerli sayıldı");
    }

    // ── özet (pencere içeriği) — gerçek `pending_updates` ile ────────────────────────────────────

    #[test]
    fn KRITIK_tek_pencere_baslatici_uygulama_profil_boyut_not() {
        let d = tempfile::tempdir().unwrap();
        sahte_kurulum(d.path(), "1.9.52");
        install::record_model_sha(d.path(), "vet", SHA_A);
        install::add_installed_profiles(d.path(), &["vet".to_string()]);
        let m = manifest_json(Some(("1.9.55", true)), None, true);
        let (plan, oz) = plan_ve_ozet(d.path(), &m, "1.9.54", true, None);
        assert!(plan.app && !plan.deps && plan.profiles == vec!["vet".to_string()], "ön koşul: {plan:?}");
        assert_eq!(oz.karar, Karar::Sor);
        let b = oz.baslatici.as_ref().expect("başlatıcı satırı yok");
        assert_eq!((b.suanki.as_str(), b.yeni.as_str(), b.boyut), ("1.9.54", "1.9.55", 2000));
        assert_eq!((b.not_tr.as_deref(), b.not_en.as_deref()), (Some("başlatıcı notu"), Some("launcher note")));
        let u = oz.uygulama.as_ref().expect("uygulama satırı yok");
        assert_eq!((u.suanki.as_str(), u.yeni.as_str()), ("1.9.52", "1.9.60"));
        assert_eq!((u.not_tr.as_deref(), u.not_en.as_deref()), (Some("uygulama notu"), Some("app note")));
        assert_eq!(oz.profiller, vec!["vet".to_string()]);
        assert!(!oz.bagimliliklar);
        // inecek: kurucu 2000 + app 70 + vet 30 (deps güncel → sayılmaz)
        assert_eq!(oz.toplam_bayt, 2100, "{oz:?}");
        let j = serde_json::to_value(&oz).unwrap();
        assert_eq!(j["karar"], "sor");
        assert_eq!(j["baslatici"]["installerUrl"], "https://github.com/a/s.exe");
        assert_eq!(j["toplamBayt"], 2100);
    }

    #[test]
    fn KRITIK_inecek_boyut_onbellektekini_saymaz() {
        let d = tempfile::tempdir().unwrap();
        sahte_kurulum(d.path(), "1.9.52");
        let m = manifest_json(None, None, false);
        let (_, oz) = plan_ve_ozet(d.path(), &m, "1.9.54", true, None);
        assert_eq!((oz.toplam_bayt, oz.katman_onbellekte), (70, false));
        let cache = install::cache_dir(d.path());
        fs::create_dir_all(&cache).unwrap();
        fs::write(cache.join("base-app.zip"), vec![0u8; 70]).unwrap();
        let (plan, oz) = plan_ve_ozet(d.path(), &m, "1.9.54", true, None);
        assert_eq!((oz.toplam_bayt, oz.katman_onbellekte, plan.indirilecek), (0, true, 0), "önbellekteki paket yeniden sayıldı");
        assert_eq!(oz.karar, Karar::Sor, "önbellekte olsa da onaysız KURULMAZ");
    }

    #[test]
    fn baslatici_otomatik_izinsiz_ya_da_kurucusuz_ise_pencereye_girmez() {
        let d = tempfile::tempdir().unwrap();
        sahte_kurulum(d.path(), "1.9.52");
        install::record_layer_sha(d.path(), "app", SHA_B); // katman güncel
        let (_, oz) = plan_ve_ozet(d.path(), &manifest_json(Some(("1.9.55", true)), None, false), "1.9.54", false, None);
        assert_eq!((oz.karar, oz.baslatici.is_none()), (Karar::Yok, true), "deneme sınırı / rollout izinsizken soruldu");
        let (_, oz) = plan_ve_ozet(d.path(), &manifest_json(Some(("1.9.55", false)), None, false), "1.9.54", true, None);
        assert_eq!((oz.karar, oz.baslatici.is_none()), (Karar::Yok, true), "kurucusuz (eski tip) bildirim pencereye girdi");
        let (_, oz) = plan_ve_ozet(d.path(), &manifest_json(Some(("1.9.54", true)), None, false), "1.9.54", true, None);
        assert_eq!(oz.karar, Karar::Yok, "aynı sürüm güncelleme sayıldı");
    }

    #[test]
    fn KRITIK_zorunlu_min_supported_onaysiz_karar() {
        let d = tempfile::tempdir().unwrap();
        sahte_kurulum(d.path(), "1.9.52");
        let (plan, oz) = plan_ve_ozet(d.path(), &manifest_json(None, Some("1.9.53"), false), "1.9.54", true, None);
        assert!(plan.zorunlu && oz.zorunlu);
        assert_eq!(oz.karar, Karar::Zorunlu);
        let (_, oz) = plan_ve_ozet(d.path(), &manifest_json(None, Some("1.9.52"), false), "1.9.54", true, None);
        assert_eq!(oz.karar, Karar::Sor, "asgari = kurulu → zorunlu DEĞİL, sorulur");
    }

    #[test]
    fn KRITIK_baslatici_ve_katman_birlikte_TEK_akis_tasinan_onayla_sorulmadan_kurulur() {
        let d = tempfile::tempdir().unwrap();
        sahte_kurulum(d.path(), "1.9.52");
        let m = manifest_json(Some(("1.9.55", true)), None, false);
        // Eski başlatıcı (1.9.54): ikisi birlikte TEK soru.
        let (plan, oz) = plan_ve_ozet(d.path(), &m, "1.9.54", true, None);
        assert_eq!(oz.karar, Karar::Sor);
        assert!(oz.baslatici.is_some() && oz.katman_gerekli);
        let k = onay_kaydi_kur(&plan, Some("1.9.55"), SIMDI);
        assert_eq!(k.katman_hedefi, plan.hedef);
        kaydet(d.path(), &k).unwrap();
        // Onaydan sonra eski başlatıcı yeniden bakarsa (yeniden başlamadan): kayıt ona TAŞINMAZ → yine "Sor" (sessiz kurulum yok).
        let (_, oz) = plan_ve_ozet(d.path(), &m, "1.9.54", true, oku(d.path()).as_ref());
        assert_eq!((oz.karar, oz.tasinan), (Karar::Sor, false));
        // Yeni başlatıcı (1.9.55) açıldı: katman SORMADAN kurulur, akış sonunda uygulama açılır (`tasinan`).
        let (_, oz) = plan_ve_ozet(d.path(), &m, "1.9.55", true, oku(d.path()).as_ref());
        assert_eq!((oz.karar, oz.tasinan, oz.baslatici.is_none()), (Karar::Onayli, true, true), "{oz:?}");
    }

    #[test]
    fn dongu_kirici_durdurduysa_katman_sorulmaz_bildirilir() {
        let d = tempfile::tempdir().unwrap();
        sahte_kurulum(d.path(), "1.9.52");
        let m = manifest_json(None, None, false);
        let plan = crate::flow::pending_updates(&m, d.path()).unwrap();
        for _ in 0..5 {
            install::record_runtime_attempt(d.path(), &plan.hedef);
        }
        let (plan, oz) = plan_ve_ozet(d.path(), &m, "1.9.54", true, None);
        assert!(plan.otomatik_durduruldu, "ön koşul: döngü kırıcı devrede");
        assert_eq!((oz.karar, oz.katman_gerekli, oz.katman_durduruldu, oz.toplam_bayt), (Karar::Yok, false, true, 0));
        let k = onay_kaydi_kur(&plan, None, SIMDI);
        assert!(k.katman_hedefi.is_empty(), "durdurulmuş katman onay kaydına girdi");
    }
}
