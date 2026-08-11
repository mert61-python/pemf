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

#[test]
fn KRITIK_konsol_acabilecek_spawn_KALMADI() {
    // KURAL: Windows'ta süreç başlatan her yer YA `platform::gizli_komut` kullanmalı YA DA
    // aynı blokta `creation_flags(... CREATE_NO_WINDOW ...)` vermeli. (İkincisi, DETACHED_PROCESS
    // gibi EK bayrak gereken yerler için meşrudur — `creation_flags` değeri EZER, OR'lamaz.)
    let mut ihlaller = Vec::new();
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
            let bayrakli = pencere.contains("creation_flags")
                && (pencere.contains("CREATE_NO_WINDOW") || pencere.contains("0x0800_0000"));
            if bayrakli {
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
