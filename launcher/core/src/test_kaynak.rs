// Author: mertaygn, cglrgrkn
//! KP-4 (istem 42 · Y257 a / b): yalnız TEST — kaynak çapası yardımcıları. Davranış koruyan yeniden düzenlemeden ÖNCE yazılan
//! SABİTLEYEN kapılar güvenlik sırasını yorum-soyulmuş kaynakta ölçer; çapa, adından bağımsız olarak çapaların HEPSİNİ taşıyan
//! TEK işlev gövdesine bakar (işlev bölünüp `_ile` gövdesine taşındığında da aynı kapı geçerli kalır).

/// `//` yorumlarını dize-bilinçli soyar (URL'deki `//` dizenin içindedir, korunur); satır sonları `\n`.
pub(crate) fn yorumsuz(src: &str) -> String {
    let mut cikti = String::with_capacity(src.len());
    for satir in src.replace("\r\n", "\n").lines() {
        let mut dizede = false;
        let mut kacis = false;
        let mut kes = satir.len();
        let b = satir.as_bytes();
        for i in 0..b.len() {
            let c = b[i];
            if dizede {
                if kacis {
                    kacis = false;
                } else if c == b'\\' {
                    kacis = true;
                } else if c == b'"' {
                    dizede = false;
                }
            } else if c == b'"' && !(i > 0 && b[i - 1] == b'\'') {
                dizede = true;
            } else if c == b'/' && i + 1 < b.len() && b[i + 1] == b'/' {
                kes = i;
                break;
            }
        }
        cikti.push_str(&satir[..kes]);
        cikti.push('\n');
    }
    cikti
}

/// Üretim kısmındaki (ilk `#[cfg(test)]`'ten önce) üst düzey işlevlerden çapaların HEPSİNİ taşıyan TEK gövde (yoksa / birden
/// çoksa panik) ve çapaların o gövdedeki konumları.
pub(crate) fn sirali_govde(kaynak: &str, capalar: &[&str]) -> Vec<usize> {
    let uretim = &kaynak[..kaynak.find("#[cfg(test)]").expect("test modülü yok")];
    let mut govdeler = Vec::new();
    let mut ofset = 0;
    for satir in uretim.split_inclusive('\n') {
        let t = satir.strip_prefix("pub(crate) ").or_else(|| satir.strip_prefix("pub ")).unwrap_or(satir);
        if t.starts_with("fn ") {
            let son = uretim[ofset..].find("\n}\n").map(|k| ofset + k).unwrap_or(uretim.len());
            govdeler.push(&uretim[ofset..son]);
        }
        ofset += satir.len();
    }
    assert!(govdeler.len() >= 10, "VAKUM: kaynakta yalnız {} işlev bulundu", govdeler.len());
    let tutan: Vec<&&str> = govdeler.iter().filter(|g| capalar.iter().all(|c| g.contains(c))).collect();
    assert_eq!(tutan.len(), 1, "çapaların hepsini taşıyan TEK işlev bekleniyordu ({} bulundu): {capalar:?}", tutan.len());
    let g = tutan[0];
    capalar.iter().map(|c| g.find(c).unwrap()).collect()
}

/// Çapalar verilen SIRADA mı? Bozuksa hangi ikilinin yer değiştirdiğini söyler.
pub(crate) fn sira_dogru(kaynak: &str, capalar: &[&str], baglam: &str) {
    let sira = sirali_govde(kaynak, capalar);
    for (k, w) in sira.windows(2).enumerate() {
        assert!(w[0] < w[1], "{baglam}: `{}` `{}`'den ÖNCE olmalı", capalar[k], capalar[k + 1]);
    }
}

#[test]
fn yorumsuz_dizedeki_cift_egik_cizgiyi_KORUR_yorumu_SOYAR() {
    let s = yorumsuz("let u = \"https://x/y\"; // yorum\n// tam satır\nlet c = '\"'; // c\n");
    assert_eq!(s, "let u = \"https://x/y\"; \n\nlet c = '\"'; \n");
}

#[test]
#[should_panic(expected = "TEK işlev")]
fn sirali_govde_capasiz_kaynakta_PANIKLER() {
    let kaynak = (0..12).map(|i| format!("fn f{i}() {{\n}}\n")).collect::<String>() + "#[cfg(test)]\n";
    sirali_govde(&kaynak, &["yok_boyle_capa"]);
}

#[test]
#[should_panic(expected = "ÖNCE olmalı")]
fn sira_dogru_YER_DEGISTIRMEYI_yakalar() {
    let mut kaynak = (0..12).map(|i| format!("fn f{i}() {{\n}}\n")).collect::<String>();
    kaynak.push_str("pub(crate) fn g() {\n    b();\n    a();\n}\n#[cfg(test)]\n");
    sira_dogru(&kaynak, &["a();", "b();"], "deneme");
}
