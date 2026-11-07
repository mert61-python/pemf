//! ÇOK DİLLİLİK (I18N · Y157–Y161) — launcher kataloğu, etkin dil ve dil seçimi.
//!
//! * Katalog `launcher/i18n/{tr,en}.json` (i18next JSON v4 — arayüz / sunucu / site ile AYNI biçim, AYNI kapılar K-1…K-7) İKİLİYE
//!   GÖMÜLÜR (`include_str!`): ağdan / diskten okuma yok, donmuş pakette eksik dosya riski yok (K-6).
//! * Arayüz (index.html) aynı kataloğun `ui.*` alt ağacını `i18n_katalog.js`'ten (katalogdan ÜRETİLİR — `scripts/i18n/katalog.py
//!   launcher-js`; K-6 eşliği denetler) eşzamanlı okur; Rust iletileri `t()` ile.
//! * Etkin dil: bayrak (`I18N_EN_ACIK`) KAPALIYKEN HER ZAMAN tr. Açıkken: uygulamanın seçimi (`<veri kökü>/PEMF_GUI/arayuz_dili.json` —
//!   masaüstü arayüz dil seçince backend yazar) → yoksa Windows görüntüleme dili (`tr*` → tr, diğer → en) → yoksa tr.
//! * Eksik anahtar: test derlemesinde PANİK (sessiz geçmez); üründe Türkçe değere, o da yoksa anahtara düşer (boş ileti yok).

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{OnceLock, RwLock};

/// İNGİLİZCE BAYRAĞI (Y158) — TEK KAYNAK depo kökü `i18n/bayrak.json`; bu sabit `scripts/i18n/bayrak.py` ile yazılır, K-5 eşliği
/// denetler. ⚠️ ELLE DEĞİŞTİRME — yalnız inceleme oturumu açar.
pub const I18N_EN_ACIK: bool = true;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Dil {
    Tr,
    En,
}

impl Dil {
    pub fn kod(self) -> &'static str {
        match self {
            Dil::Tr => "tr",
            Dil::En => "en",
        }
    }
    pub fn coz(kod: &str) -> Option<Dil> {
        match kod.trim().to_ascii_lowercase().as_str() {
            "tr" => Some(Dil::Tr),
            "en" => Some(Dil::En),
            _ => None,
        }
    }
}

const TR_JSON: &str = include_str!("../../i18n/tr.json");
const EN_JSON: &str = include_str!("../../i18n/en.json");

static KATALOGLAR: OnceLock<(HashMap<String, String>, HashMap<String, String>)> = OnceLock::new();
static ETKIN: RwLock<Dil> = RwLock::new(Dil::Tr);

fn duzlestir(onek: &str, v: &serde_json::Value, cikti: &mut HashMap<String, String>) {
    if let Some(o) = v.as_object() {
        for (k, alt) in o {
            let tam = if onek.is_empty() { k.clone() } else { format!("{onek}.{k}") };
            duzlestir(&tam, alt, cikti);
        }
    } else if let Some(s) = v.as_str() {
        cikti.insert(onek.to_string(), s.to_string());
    }
}

fn katalog_ayristir(ham: &str) -> HashMap<String, String> {
    let mut m = HashMap::new();
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(ham) {
        duzlestir("", &v, &mut m);
    }
    m
}

fn kataloglar() -> &'static (HashMap<String, String>, HashMap<String, String>) {
    KATALOGLAR.get_or_init(|| (katalog_ayristir(TR_JSON), katalog_ayristir(EN_JSON)))
}

/// Etkin dil.
pub fn etkin() -> Dil {
    ETKIN.read().map(|d| *d).unwrap_or(Dil::Tr)
}

/// Etkin dili ayarla — bayrak kapalıyken her zaman tr kalır.
pub fn ayarla(d: Dil) -> Dil {
    let son = if I18N_EN_ACIK { d } else { Dil::Tr };
    if let Ok(mut w) = ETKIN.write() {
        *w = son;
    }
    son
}

/// Yerel ayar kodu → dil: `tr`, `tr-TR`, `tr_TR` → tr; boş → tr; diğer her şey → en.
pub fn dile_indirge(kod: &str) -> Dil {
    let s = kod.trim().to_ascii_lowercase().replace('_', "-");
    if s.is_empty() || s == "tr" || s.starts_with("tr-") {
        Dil::Tr
    } else {
        Dil::En
    }
}

/// Uygulamanın (masaüstü arayüz) dil seçimini taşıyan dosya adayları — makine-geneli veri kökü önce, sonra kullanıcı kökü.
pub fn uygulama_dili_dosyalari<F>(getenv: F) -> Vec<PathBuf>
where
    F: Fn(&str) -> Option<String>,
{
    let mut v = Vec::new();
    if let Some(m) = crate::install::machine_data_dir(&getenv) {
        v.push(m.join("PEMF_GUI").join("arayuz_dili.json"));
    }
    if let Some(a) = getenv("APPDATA").filter(|s| !s.is_empty()) {
        v.push(PathBuf::from(a).join("PEMF_GUI").join("arayuz_dili.json"));
    }
    v
}

/// Uygulamanın kayıtlı seçimi (dosya yok / bozuk → None).
pub fn uygulama_secimi(dosyalar: &[PathBuf]) -> Option<Dil> {
    for f in dosyalar {
        if let Ok(ham) = std::fs::read_to_string(f) {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(&ham) {
                if let Some(d) = v.get("dil").and_then(|x| x.as_str()).and_then(Dil::coz) {
                    return Some(d);
                }
            }
        }
    }
    None
}

/// Windows görüntüleme dili (GetUserDefaultUILanguage → birincil dil kimliği; 0x1F = Türkçe). Windows dışı / okunamaz → None.
#[cfg(windows)]
pub fn windows_arayuz_dili() -> Option<Dil> {
    // SAFETY: parametresiz, yan etkisiz Win32 sorgusu.
    let langid = unsafe { windows_sys::Win32::Globalization::GetUserDefaultUILanguage() };
    if langid == 0 {
        return None;
    }
    Some(if (langid & 0x3ff) == 0x1f { Dil::Tr } else { Dil::En })
}

#[cfg(not(windows))]
pub fn windows_arayuz_dili() -> Option<Dil> {
    std::env::var("LANG").ok().map(|l| dile_indirge(&l))
}

/// Açılış dili: bayrak kapalı → tr; açık → uygulamanın seçimi > işletim sistemi dili > tr.
pub fn baslangic_dili(en_acik: bool, uygulama: Option<Dil>, isletim_sistemi: Option<Dil>) -> Dil {
    if !en_acik {
        return Dil::Tr;
    }
    uygulama.or(isletim_sistemi).unwrap_or(Dil::Tr)
}

/// Açılışta bir kez: etkin dili kur.
pub fn baslat() -> Dil {
    let uyg = uygulama_secimi(&uygulama_dili_dosyalari(|k| std::env::var(k).ok()));
    let d = baslangic_dili(I18N_EN_ACIK, uyg, windows_arayuz_dili());
    ayarla(d)
}

fn bul(anahtar: &str, d: Dil) -> Option<&'static str> {
    let (tr, en) = kataloglar();
    let birincil = if d == Dil::En { en } else { tr };
    birincil.get(anahtar).or_else(|| tr.get(anahtar)).map(|s| s.as_str())
}

/// Anahtar → metin (etkin dilde). Eksik: testte panik; üründe anahtar.
pub fn t(anahtar: &str) -> String {
    t_ile(anahtar, &[])
}

/// Anahtar → metin, `{{ad}}` yer tutucuları `p`'den.
pub fn t_ile(anahtar: &str, p: &[(&str, &str)]) -> String {
    let Some(m) = bul(anahtar, etkin()) else {
        if cfg!(test) {
            panic!("dil: katalogda olmayan anahtar {anahtar:?}");
        }
        return anahtar.to_string();
    };
    let mut s = m.to_string();
    for (ad, deger) in p {
        s = s.replace(&format!("{{{{{ad}}}}}"), deger);
    }
    s
}

/// Kataloğun ham hâli (arayüz ve testler için).
pub fn katalog(d: Dil) -> &'static HashMap<String, String> {
    let (tr, en) = kataloglar();
    if d == Dil::En {
        en
    } else {
        tr
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn yerel_kod_tr_ile_baslarsa_tr_degilse_en() {
        assert_eq!(dile_indirge("tr"), Dil::Tr);
        assert_eq!(dile_indirge("tr-TR"), Dil::Tr);
        assert_eq!(dile_indirge("TR_tr"), Dil::Tr);
        assert_eq!(dile_indirge(""), Dil::Tr);
        assert_eq!(dile_indirge("en-US"), Dil::En);
        assert_eq!(dile_indirge("de-DE"), Dil::En);
    }

    #[test]
    fn bayrak_kapaliyken_her_zaman_tr_acikken_uygulama_secimi_once() {
        assert_eq!(baslangic_dili(false, Some(Dil::En), Some(Dil::En)), Dil::Tr);
        assert_eq!(baslangic_dili(true, Some(Dil::En), Some(Dil::Tr)), Dil::En);
        assert_eq!(baslangic_dili(true, None, Some(Dil::En)), Dil::En);
        assert_eq!(baslangic_dili(true, None, None), Dil::Tr);
    }

    #[test]
    fn uygulama_secimi_dosyadan_okunur_bozuk_dosya_yok_sayilir() {
        let d = tempfile::tempdir().unwrap();
        let bozuk = d.path().join("a.json");
        let iyi = d.path().join("b.json");
        std::fs::write(&bozuk, "{bozuk").unwrap();
        std::fs::write(&iyi, r#"{"dil":"en"}"#).unwrap();
        assert_eq!(uygulama_secimi(&[bozuk.clone(), iyi.clone()]), Some(Dil::En));
        assert_eq!(uygulama_secimi(&[bozuk]), None);
        assert_eq!(uygulama_secimi(&[d.path().join("yok.json")]), None);
    }

    #[test]
    fn uygulama_dili_dosyalari_makine_koku_once_sonra_kullanici() {
        let v = uygulama_dili_dosyalari(|k| match k {
            "PROGRAMDATA" => Some(r"C:\PD".into()),
            "APPDATA" => Some(r"C:\U\AppData\Roaming".into()),
            _ => None,
        });
        let son = v.last().unwrap().to_string_lossy().replace('\\', "/");
        assert!(son.ends_with("AppData/Roaming/PEMF_GUI/arayuz_dili.json"), "{son}");
        if cfg!(windows) {
            assert_eq!(v.len(), 2);
            assert!(v[0].to_string_lossy().replace('\\', "/").ends_with("PD/PEMF_System/PEMF_GUI/arayuz_dili.json"));
        }
    }

    #[test]
    fn katalog_gomulu_ve_iki_dilde_ayni_anahtarlar() {
        let (tr, en) = kataloglar();
        assert!(!tr.is_empty(), "tr kataloğu boş / ayrıştırılamadı");
        let mut a: Vec<_> = tr.keys().collect();
        let mut b: Vec<_> = en.keys().collect();
        a.sort();
        b.sort();
        assert_eq!(a, b, "tr / en anahtar kümesi farklı");
    }

    #[test]
    fn t_yer_tutucu_doldurur_eksik_anahtar_testte_panik() {
        // nsis.* katalogda var; bayrak kapalıyken etkin dil tr
        // D6.67: ekranda ürün adı "PEMF Vet" (METIN-KILAVUZU §1) — iki dilde de değer, anahtar adı değil
        assert!(t("nsis.temizlikTamam").starts_with("PEMF Vet "));
        let r = std::panic::catch_unwind(|| t("olmayan.anahtar"));
        assert!(r.is_err(), "eksik anahtar testte panik etmeli (sessizce anahtar basmamalı)");
    }

    #[test]
    fn bayrak_kapaliyken_ayarla_en_tr_kalir() {
        if !I18N_EN_ACIK {
            assert_eq!(ayarla(Dil::En), Dil::Tr);
            assert_eq!(etkin(), Dil::Tr);
        }
    }

    // ═══ KP-3 C · dil kodu gidiş-dönüş, etkin dil kurulumu, Windows arayüz dili sorgusu ═══
    #[test]
    fn kp3_kod_coz_gidis_donus_ve_etkin_dil_tr_kurulur() {
        assert_eq!(Dil::Tr.kod(), "tr");
        assert_eq!(Dil::En.kod(), "en");
        for d in [Dil::Tr, Dil::En] {
            assert_eq!(Dil::coz(d.kod()), Some(d));
        }
        assert_eq!(Dil::coz(" EN "), Some(Dil::En));
        assert_eq!(Dil::coz("de"), None);
        // Küresel etkin dil YALNIZ Tr'ye kurulur: aynı süreçteki diğer testler Türkçe metin bekler (En'e çekmek yarış doğurur).
        assert_eq!(ayarla(Dil::Tr), Dil::Tr);
        assert_eq!(etkin(), Dil::Tr);
    }

    /// GetUserDefaultUILanguage yan etkisiz bir sorgudur ve dil kimliği 0 dönmez → her Windows'ta bir dil (tr / en) çıkar.
    #[cfg(windows)]
    #[test]
    fn kp3_windows_arayuz_dili_bir_dil_doner() {
        assert!(windows_arayuz_dili().is_some());
    }
}
