// Author: mertaygn, cglrgrkn
//! GERİ ALMA YALAN SÖYLEMEZ (denetim 2026-08-23, C10).
//!
//! ÖLÇÜLEN DURUM: `update_installed`'ın yalnız-app dalı `GeriAlmaBilgisi { app_yedegi: true }`
//! değerini KOŞULSUZ set ediyordu. Oysa `app_katmanini_degistir` yedeği YALNIZ kök listesi
//! doluyken alır ve `install::read_app_roots` dosya yok/bozuksa BOŞ döner (kasıtlı: bilinmeyen
//! sınırla silmek, bayat dosya bırakmaktan tehlikelidir) — fonksiyon yine `Ok(())` döner.
//!
//! Sonuç: `_app_roots.json` kayıp/bozuk olan bir kurulumda (AV karantinası, yarım kalan önceki
//! açılım, disk hatası) app katmanı canlı ağacın ÜZERİNE YEDEKSİZ açılır; sağlık kapısı düşerse
//! `guncellemeyi_geri_al` yedek dizinini bulamaz, SESSİZCE hiçbir şey yapmaz ve `Ok(())` döner.
//! Kullanıcıya "eski sürüme dönüldü" denirken cihaz DOĞRULANMAMIŞ yeni sürümde kalır.
//!
//! ⚠️ Bu, tıbbi cihazda YANLIŞ GÜVENCE sınıfıdır — deponun 2026-08-20'de `let _ =` yutması için
//! kapattığı hatanın aynı türden ikinci örneği. Sözleşme: geri alma ya GERÇEKTEN geri alır ya da
//! alamadığını SÖYLER.

use std::fs;
use std::path::Path;

use pemf_launcher_core::{flow, install};

fn exe_adi() -> &'static str {
    pemf_launcher_core::platform::backend_exe_name()
}

fn runtime_kur(dir: &Path, imza: &str) {
    let kok = dir.join("PEMF_Backend");
    fs::create_dir_all(kok.join("_internal").join("frontend").join("dist")).unwrap();
    fs::write(kok.join(exe_adi()), imza).unwrap();
    fs::write(kok.join("_internal").join("frontend").join("dist").join("index.html"), imza).unwrap();
}

#[test]
fn KRITIK_yedeksiz_geri_alma_BASARILI_DEMEZ() {
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    runtime_kur(&install::runtime_dir(kok), "YENI-DOGRULANMAMIS");
    // `_app_yedek` YOK (yedek hiç alınamadı) ama bilgi "yedek var" diyor:
    let b = flow::GeriAlmaBilgisi {
        app_yedegi: true,
        ..Default::default()
    };

    let sonuc = flow::guncellemeyi_geri_al(kok, &b);

    assert!(
        sonuc.is_err(),
        "geri alma YEDEK YOKKEN 'basarili' dondu — kullaniciya 'eski surume donuldu' denirken \
         cihaz DOGRULANMAMIS yeni surumde kalir (yanlis guvence)"
    );
}

#[test]
fn KARSIT_KANIT_gercek_yedek_VARKEN_geri_alma_calisir() {
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    let rt = install::runtime_dir(kok);
    let yedek = install::app_backup_dir(kok);
    runtime_kur(&rt, "YENI-BOZUK");
    runtime_kur(&yedek, "ESKI-CALISAN");
    fs::write(
        yedek.join("PEMF_Backend").join("_app_roots.json"),
        format!(r#"{{"roots":["PEMF_Backend/{}"]}}"#, exe_adi()),
    )
    .unwrap();

    flow::guncellemeyi_geri_al(kok, &flow::GeriAlmaBilgisi { app_yedegi: true, ..Default::default() })
        .expect("gercek yedek varken geri alma basarisiz oldu");

    let imza = fs::read_to_string(rt.join("PEMF_Backend").join(exe_adi())).unwrap();
    assert_eq!(imza, "ESKI-CALISAN", "eski calisan surum geri konmadi");
}

#[test]
fn KARSIT_KANIT_yapilacak_is_YOKKEN_hata_verilmez() {
    // Hicbir sey yapilmadiysa (plan bostu) geri alma da sessizce basarili olmali —
    // kapi asiri genislemesin.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    runtime_kur(&install::runtime_dir(kok), "DOKUNULMADI");

    flow::guncellemeyi_geri_al(kok, &flow::GeriAlmaBilgisi::default())
        .expect("bos geri alma bilgisi hata uretti — kapi asiri genis");
}
