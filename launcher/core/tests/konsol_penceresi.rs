// Author: mertaygn, cglrgrkn
//! SİYAH KONSOL PENCERESİ REGRESYON KAPISI.
//!
//! SAHA ŞİKÂYETİ (2026-08-11): "client güncellemesi için uygulamayı kapatıp geri açtığımda
//! 2 kez siyah konsol penceresi çıktı."
//!
//! Launcher pencereli (konsolsuz) çalışır. Konsol-altsistem bir program (powershell, icacls,
//! taskkill, cmd…) böyle bir süreçten başlatılınca Windows ona YENİ BİR KONSOL açar. Backend
//! spawn'ında `CREATE_NO_WINDOW` vardı ama yardımcı komutlarda unutulmuştu:
//! güvenlik-duvarı denetimi (açılışta) + kurulum dizinine ACL (güncellemede) = tam 2 pencere.
//!
//! Bu dosya kaynağı DENETLER: Windows'ta süreç başlatan her yer `platform::gizli_komut`
//! kullanmalı. Tek tek düzeltmek yetmez — bir sonraki yardımcı komut yine unutulur.

use std::path::{Path, PathBuf};

/// Denetlenecek kaynak dosyalar (launcher core + app).
fn kaynaklar() -> Vec<PathBuf> {
    let kok = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().to_path_buf();
    let mut v = Vec::new();
    for alt in ["core/src", "app/src"] {
        let d = kok.join(alt);
        if let Ok(girdiler) = std::fs::read_dir(&d) {
            for e in girdiler.flatten() {
                let p = e.path();
                if p.extension().and_then(|x| x.to_str()) == Some("rs") {
                    v.push(p);
                }
            }
        }
    }
    assert!(!v.is_empty(), "kaynak dosya bulunamadi");
    v
}

/// `#[cfg(test)]` bloğundan SONRAKİ satırları at — test kodu kullanıcıya pencere göstermez.
fn uretim_kodu(icerik: &str) -> String {
    match icerik.find("#[cfg(test)]") {
        Some(i) => icerik[..i].to_string(),
        None => icerik.to_string(),
    }
}

/// Yalnız Windows-dışı platformlarda çalışan komutlar — Windows konsolu açamazlar.
const WINDOWS_DISI: [&str; 3] = ["pkill", "\"open\"", "xdg-open"];

/// `creation_flags(<TEK_BUYUK_HARFLI_SABIT>)` ise sabitin adını döndür.
///
/// Yalnızca TEK bir tanımlayıcı kabul edilir: `creation_flags(A | 0x8)` gibi karma ifadeler
/// buraya düşmez, onları yukarıdaki AÇIK bayrak denetimi zaten değerlendirir.
fn bayrak_sabiti(pencere: &str) -> Option<String> {
    let i = pencere.find("creation_flags(")? + "creation_flags(".len();
    let kalan = &pencere[i..];
    let j = kalan.find(')')?;
    let arg = kalan[..j].trim();
    let gecerli = !arg.is_empty()
        && arg.chars().all(|c| c.is_ascii_uppercase() || c.is_ascii_digit() || c == '_')
        && arg.chars().next().is_some_and(|c| c.is_ascii_uppercase() || c == '_');
    gecerli.then(|| arg.to_string())
}

/// Sabitin TANIMI CREATE_NO_WINDOW taşıyor mu? (dolaylılık kapıyı atlatmasın)
fn sabit_no_window(sabitler: &std::collections::HashMap<String, String>, ad: &str) -> bool {
    sabitler
        .get(ad)
        .is_some_and(|govde| govde.contains("CREATE_NO_WINDOW") || govde.contains("0x0800_0000"))
}

/// Taranan kaynaklardaki `const AD: u32 = <gövde>;` tanımlarını topla.
fn sabitleri_topla(dosyalar: &[PathBuf]) -> std::collections::HashMap<String, String> {
    let mut m = std::collections::HashMap::new();
    for d in dosyalar {
        let Ok(icerik) = std::fs::read_to_string(d) else { continue };
        for satir in icerik.lines() {
            let s = satir.trim();
            let Some(kalan) = s.strip_prefix("const ") else { continue };
            let Some((ad, govde)) = kalan.split_once('=') else { continue };
            let ad = ad.split(':').next().unwrap_or("").trim();
            if !ad.is_empty() {
                m.insert(ad.to_string(), govde.to_string());
            }
        }
    }
    m
}

#[test]
fn KRITIK_konsol_acabilecek_spawn_KALMADI() {
    // KURAL: Windows'ta süreç başlatan her yer YA `platform::gizli_komut` kullanmalı YA DA
    // aynı blokta `creation_flags(... CREATE_NO_WINDOW ...)` vermeli. (İkincisi, DETACHED_PROCESS
    // gibi EK bayrak gereken yerler için meşrudur — `creation_flags` değeri EZER, OR'lamaz.)
    let mut ihlaller = Vec::new();
    let sabitler = sabitleri_topla(&kaynaklar());
    for dosya in kaynaklar() {
        // `gizli_komut` tanımının KENDİSİ çıplak Command::new kullanır — tek meşru istisna.
        if dosya.file_name().and_then(|x| x.to_str()) == Some("platform.rs") {
            continue;
        }
        let ham = std::fs::read_to_string(&dosya).unwrap();
        let kod = uretim_kodu(&ham);
        let satirlar: Vec<&str> = kod.lines().collect();
        for (i, satir) in satirlar.iter().enumerate() {
            let s = satir.trim();
            if s.starts_with("//") || !s.contains("Command::new") {
                continue;
            }
            if WINDOWS_DISI.iter().any(|p| s.contains(p)) {
                continue;
            }
            // Aynı blokta (sonraki ~10 satır) bayrak açıkça veriliyor mu?
            let pencere = satirlar[i..(i + 10).min(satirlar.len())].join("\n");
            let acik_bayrak = pencere.contains("creation_flags")
                && (pencere.contains("CREATE_NO_WINDOW") || pencere.contains("0x0800_0000"));
            // …ya da ADLANDIRILMIŞ bir sabitle: `creation_flags(YARDIMCI_BATCH_BAYRAKLARI)`.
            // ⚠️ Dolaylılık BEDAVA DEĞİL: sabitin KENDİ tanımı bayrağı taşımalı. Aksi hâlde
            // `creation_flags(BOS)` yazarak kapı sessizce atlanabilirdi. (Aynı gerekçeyle
            // `gizli_komut` için de ayrı bir test bayrağı pinliyor.)
            let sabitle = bayrak_sabiti(&pencere).is_some_and(|ad| sabit_no_window(&sabitler, &ad));
            if acik_bayrak || sabitle {
                continue;
            }
            ihlaller.push(format!(
                "{}:{} -> {}",
                dosya.file_name().unwrap().to_string_lossy(),
                i + 1,
                s
            ));
        }
    }
    assert!(
        ihlaller.is_empty(),
        "Bu spawn'lar kullanici karsisinda SIYAH KONSOL acabilir. \
         `platform::gizli_komut` kullanin (ya da CREATE_NO_WINDOW iceren creation_flags verin).\n  {}",
        ihlaller.join("\n  ")
    );
}

#[test]
fn KRITIK_gizli_komut_CREATE_NO_WINDOW_uygular() {
    // Bayrağın kendisi kaybolursa yardımcı sessizce ETKİSİZ kalır ve yukarıdaki denetim
    // "hepsi gizli_komut kullaniyor" diye YEŞİL yanmaya devam eder — yanlış güvence.
    let p = Path::new(env!("CARGO_MANIFEST_DIR")).join("src").join("platform.rs");
    let s = std::fs::read_to_string(p).unwrap();
    assert!(
        s.contains("0x0800_0000") || s.contains("0x08000000"),
        "gizli_komut CREATE_NO_WINDOW bayragini kaybetmis"
    );
    assert!(s.contains("creation_flags"), "creation_flags cagrisi yok");
}

#[test]
fn gizli_komut_CALISIR_ve_ciktiyi_dondurur() {
    // Yardımcı yalnız pencereyi gizlemekle kalmayıp komutu gerçekten çalıştırmalı.
    let prog = if cfg!(windows) { "cmd" } else { "sh" };
    let args: &[&str] = if cfg!(windows) { &["/C", "echo pemf"] } else { &["-c", "echo pemf"] };
    let o = pemf_launcher_core::platform::gizli_komut(prog).args(args).output().unwrap();
    assert!(o.status.success(), "gizli_komut komutu calistiramadi");
    assert!(String::from_utf8_lossy(&o.stdout).contains("pemf"));
}
