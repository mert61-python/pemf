// Author: mertaygn, cglrgrkn
//! DENETİM MASASI BOYUTU — gerçeği yansıtmalı.
//!
//! SAHİP BİLDİRİMİ (2026-08-11): "Denetim Masası'nda uygulamanın boyutu hep 11 MB görünüyor,
//! profil kurulumlarından sonra bile."
//!
//! SEBEP: NSIS `EstimatedSize`i KURULUM ANINDA hesaplar; o an dizinde yalnız launcher vardır
//! (~11 MB). Çalışma zamanı (~2 GB) ve profil modelleri (0,3-1,6 GB) SONRADAN indirilir ve
//! kayıt bir daha güncellenmez. Kullanıcı diskte yer ararken gigabaytlık bir uygulamayı 11 MB
//! sanar — yanlış karar verdiren bir sayı.

use std::fs;
use std::path::Path;

use pemf_launcher_core::install;

fn dosya(p: &Path, boyut: usize) {
    fs::create_dir_all(p.parent().unwrap()).unwrap();
    fs::write(p, vec![7u8; boyut]).unwrap();
}

#[test]
fn KRITIK_boyut_INDIRILEN_paketleri_de_sayar() {
    // Kurulum sonrası ağaç: launcher (küçük) + runtime + profil modelleri (büyük).
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    dosya(&kok.join("PEMFVetClient.exe"), 2_000);
    let launcher_only = install::kurulum_boyutu(kok);

    dosya(&kok.join("runtime").join("PEMF_Backend").join("PEMF_Backend.exe"), 50_000);
    dosya(&kok.join("ai_models").join("home").join("model.onnx"), 200_000);

    let tam = install::kurulum_boyutu(kok);
    assert!(
        tam > launcher_only * 10,
        "boyut indirilen paketleri saymiyor → Denetim Masasi'nda '11 MB'da takili kalir \
         (launcher={launcher_only} tam={tam})"
    );
    assert_eq!(tam, 252_000, "toplam beklenenden farkli");
}

#[test]
fn KRITIK_onbellek_de_SAYILIR() {
    // Önbellekteki zip'ler gerçekten yer kaplar ve kaldırma onları da siler. "Bu uygulamayı
    // kaldırırsam ne kadar yer açılır" sorusunun doğru cevabı onları İÇERİR.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    dosya(&kok.join("runtime").join("x.bin"), 1_000);
    let onbelleksiz = install::kurulum_boyutu(kok);
    dosya(&kok.join("cache").join("base-deps.zip"), 9_000);
    assert_eq!(install::kurulum_boyutu(kok), onbelleksiz + 9_000, "onbellek sayilmiyor");
}

#[test]
fn bos_kok_SIFIR_doner() {
    let d = tempfile::tempdir().unwrap();
    assert_eq!(install::kurulum_boyutu(d.path()), 0);
}

#[test]
fn olmayan_kok_COKMEZ() {
    assert_eq!(install::kurulum_boyutu(Path::new(r"C:\olmayan-dizin-xyz")), 0);
}

#[test]
fn KRITIK_bos_kokte_kayit_GUNCELLENMEZ() {
    // "0 MB" yazmak, eski 11 MB'ı bırakmaktan DAHA KÖTÜ olurdu: kullanıcı "hiç yer kaplamıyor"
    // sanır. Boyut okunamıyorsa mevcut değere DOKUNULMAZ.
    //
    // ⚠️ Bu testin ilk hâli yalnız "çökmedi"yi ölçüyordu ve mutasyonu (boş kökte de yaz)
    // YAKALAMIYORDU — yanlış güvence. Fonksiyon artık yazmaya girişip girişmediğini döndürüyor.
    let d = tempfile::tempdir().unwrap();
    assert!(
        !install::boyut_kaydini_guncelle(d.path()),
        "bos kokte kayit YAZILDI → Denetim Masasi '0 MB' gosterir"
    );
}

#[test]
fn KRITIK_dolu_kokte_kayit_YAZILIR() {
    // Karşı-kanıt: fonksiyon her koşulda `false` dönerse yukarıdaki test yeşil kalır ama
    // boyut hiç güncellenmez — asıl şikâyet ("hep 11 MB") devam ederdi.
    let d = tempfile::tempdir().unwrap();
    dosya(&d.path().join("runtime").join("x.bin"), 5_000_000);
    assert!(
        install::boyut_kaydini_guncelle(d.path()),
        "dolu kokte kayit yazilmadi → boyut '11 MB'da takili kalir"
    );
}

#[test]
fn KRITIK_symlink_IZLENMEZ() {
    // Kurulum kökünde junction olabilir (model kökü paylaşımı). İzlenirse başka bir birimdeki
    // gigabaytlar sayılır ve boyut YANLIŞ ŞİŞER — 11 MB kadar yanıltıcı olurdu.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path().join("kurulum");
    let disari = d.path().join("disari");
    fs::create_dir_all(&kok).unwrap();
    fs::create_dir_all(&disari).unwrap();
    dosya(&disari.join("buyuk.bin"), 100_000);
    dosya(&kok.join("kucuk.bin"), 1_000);

    // Junction kurulamıyorsa (izin yok) testi atla — ölçemediğimizi iddia etmeyelim.
    #[cfg(windows)]
    {
        let ok = pemf_launcher_core::platform::gizli_komut("cmd")
            .args(["/C", "mklink", "/J"])
            .arg(kok.join("link"))
            .arg(&disari)
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false);
        if !ok {
            eprintln!("atlandi: junction olusturulamadi");
            return;
        }
    }
    #[cfg(not(windows))]
    {
        let _ = std::os::unix::fs::symlink(&disari, kok.join("link"));
    }

    assert_eq!(
        install::kurulum_boyutu(&kok),
        1_000,
        "symlink/junction IZLENDI → baska birimdeki veriler sayildi, boyut yanlis sisti"
    );
}
