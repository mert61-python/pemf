// Author: mertaygn, cglrgrkn
//! KESİNTİ SENARYOLARI — "kurulum/güncelleme esnasında kapanma".
//!
//! SAHİP İSTEĞİ (2026-08-11): "süreçler düzgün yönetilmiyor bence client tarafında güncelleme
//! olsun ya da kurulum. kurulum esnasında kapanma güncelleme esnasında kapanma kullanıcı
//! tarafından hepsi olabilir — bir kullanıcıymış gibi davran ve bugları bul."
//!
//! Burada süreç GERÇEKTEN öldürülmez; öldürülmüş olsaydı diskte ne kalırdı, o durum birebir
//! kurulur ve bir sonraki AÇILIŞIN toparlayıp toparlamadığı ölçülür. Kesintinin kendisi değil,
//! **kesintiden sonraki ilk açılış** önemlidir — kullanıcı orada ya çalışan bir cihaz bulur ya
//! da 1,4 GB'lık bir sıfırdan kurulum ekranı.

use std::fs;
use std::path::Path;

use pemf_launcher_core::{flow, install};

/// Yapısal olarak GEÇERLİ bir runtime ağacı kur (agac_yapisal_gecerli_mi'nin aradığı 3 şey).
fn runtime_kur(dir: &Path, imza: &str) {
    let kok = dir.join("PEMF_Backend");
    fs::create_dir_all(kok.join("_internal").join("frontend").join("dist")).unwrap();
    fs::write(kok.join(exe_adi()), imza).unwrap();
    fs::write(
        kok.join("_internal").join("frontend").join("dist").join("index.html"),
        imza,
    )
    .unwrap();
}

fn exe_adi() -> &'static str {
    pemf_launcher_core::platform::backend_exe_name()
}

fn imza_oku(dir: &Path) -> String {
    fs::read_to_string(dir.join("PEMF_Backend").join(exe_adi())).unwrap_or_default()
}

#[test]
fn KRITIK_takasin_ORTASINDA_kapanma_calisan_surumu_KAYBETMEZ() {
    // SENARYO: güncelleme sırasında kullanıcı pencereyi kapattı / elektrik gitti.
    // `runtime` → `runtime.old` yapıldı, `runtime.new` → `runtime` YAPILAMADI.
    // Diskte `runtime` YOK; çalışan sürüm `runtime.old`da.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    runtime_kur(&install::runtime_old_dir(kok), "CALISAN-ESKI");
    runtime_kur(&install::runtime_new_dir(kok), "DOGRULANMAMIS-YENI");
    assert!(!install::runtime_dir(kok).exists(), "senaryo kurulumu hatali");

    let kurtarildi = flow::yarim_takasi_kurtar(kok);

    assert!(kurtarildi, "yarim takas KURTARILMADI → client 'kurulu degil' der");
    assert!(
        install::backend_path(kok).exists(),
        "kurtarma sonrasi backend yolu yok → detect_environment yine 'kurulu degil' der"
    );
    // ⚠️ KANITLANMIŞ sürüm geri gelmeli; doğrulanmamış `runtime.new` sessizce canliya ALINMAMALI.
    assert_eq!(
        imza_oku(&install::runtime_dir(kok)),
        "CALISAN-ESKI",
        "dogrulanmamis yeni surum saglik kapisi ATLANARAK canliya alindi"
    );
}

#[test]
fn KRITIK_eski_YOKSA_yeni_ile_toparlar() {
    // İlk kurulumun takası yarıda kaldıysa `runtime.old` hiç oluşmamıştır. O hâlde tek seçenek
    // `runtime.new`dir — doğrulanmamış olması, kliniği runtime'sız bırakmaktan iyidir.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    runtime_kur(&install::runtime_new_dir(kok), "YENI");

    assert!(flow::yarim_takasi_kurtar(kok));
    assert_eq!(imza_oku(&install::runtime_dir(kok)), "YENI");
}

#[test]
fn KRITIK_BOZUK_yedek_canliya_ALINMAZ() {
    // `runtime.old` yarım/bozuksa (kopyalama sırasında kesinti) onu geri koymak, cihazı
    // "kurulu ama açılmıyor" durumuna sokar — kurulu-değil'den daha kötüdür, çünkü onarım
    // akışı tetiklenmez. Yapısal kapı bunu elemeli.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    let eski = install::runtime_old_dir(kok);
    fs::create_dir_all(eski.join("PEMF_Backend").join("_internal")).unwrap();
    fs::write(eski.join("PEMF_Backend").join(exe_adi()), "YARIM").unwrap();
    // index.html YOK → yapısal olarak GEÇERSİZ
    runtime_kur(&install::runtime_new_dir(kok), "SAGLAM-YENI");

    assert!(flow::yarim_takasi_kurtar(kok));
    assert_eq!(
        imza_oku(&install::runtime_dir(kok)),
        "SAGLAM-YENI",
        "bozuk yedek canliya alindi → cihaz 'kurulu ama acilmiyor' olur"
    );
}

#[test]
fn calisan_kurulum_VARKEN_hicbir_sey_yapmaz() {
    // Karşı-kanıt: kurtarma yalnız `runtime` YOKKEN devreye girmeli. Aksi hâlde her açılışta
    // sağlam kurulumun üzerine `runtime.old`/`runtime.new` taşınabilirdi.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    runtime_kur(&install::runtime_dir(kok), "CANLI");
    runtime_kur(&install::runtime_old_dir(kok), "ESKI");

    assert!(!flow::yarim_takasi_kurtar(kok), "gereksiz kurtarma calisti");
    assert_eq!(imza_oku(&install::runtime_dir(kok)), "CANLI", "canli kurulum EZILDI");
}

#[test]
fn KRITIK_YARIM_kurulum_HAZIR_gorunmez() {
    // SENARYO: ilk kurulum / profil değiştirme sırasında kapanma. `install_profiles` ATOMİK
    // DEĞİLDİR (canlı `runtime`ı silip yerine açar; `runtime.new` + takas yalnız GÜNCELLEMEDE).
    // Açma sırasında kesilirse exe yazılmış ama web arayüzü yarım kalmış olabilir.
    //
    // Eskiden `already_installed` YALNIZ exe'ye bakıyordu → client "Hazır!" der, kullanıcı
    // Başlat'a basar ve backend anlaşılmaz bir hatayla düşerdi.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    let rt = install::runtime_dir(kok);
    fs::create_dir_all(rt.join("PEMF_Backend").join("_internal")).unwrap();
    fs::write(rt.join("PEMF_Backend").join(exe_adi()), "YARIM").unwrap();
    // frontend/dist/index.html YOK → açma yarıda kalmış

    assert!(
        install::backend_path(kok).exists(),
        "senaryo kurulumu: exe VAR olmali (eski kontrolun yanildigi durum)"
    );
    assert!(
        !flow::kurulum_saglam_mi(kok),
        "yarim kurulum SAGLAM sayildi → client 'Hazir!' der, Baslat anlasilmaz hatayla duser"
    );
}

#[test]
fn TAM_kurulum_saglam_sayilir() {
    // Karşı-kanıt: kontrol fazla katı olursa çalışan kurulumlar "kurulu değil" görünür ve
    // kullanıcı gereksiz yere yeniden kurar.
    let d = tempfile::tempdir().unwrap();
    runtime_kur(&install::runtime_dir(d.path()), "TAM");
    assert!(flow::kurulum_saglam_mi(d.path()));
}

#[test]
fn hicbir_sey_YOKKEN_sessizce_gecer() {
    // Temiz makine (ilk kurulum öncesi): kurtarma çökmemeli, false dönmeli.
    let d = tempfile::tempdir().unwrap();
    assert!(!flow::yarim_takasi_kurtar(d.path()));
}
