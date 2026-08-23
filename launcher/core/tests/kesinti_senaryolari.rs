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

// ─────────────────────────────────────────────────────────────────────────────────────────
// DENETİM 2026-08-23 — kurtarmanın GÖRMEDİĞİ iki kesinti (C9, C11)
// ─────────────────────────────────────────────────────────────────────────────────────────

/// C9 — Kesintiden kalan `runtime.new`, DİSK KAPISININ istediği alanı işgal ediyor.
///
/// `update_installed` sırası: önce `disk_kapisi`, SONRA `temizle_ve_ac` (o da `runtime.new`i
/// siler). Kapı `?` ile erken döndüğü için o silme HİÇ çalışmaz. `yarim_takasi_kurtar` ise
/// `runtime` sağlam olduğu için ilk satırda `false` döner ve ölü ağaca DOKUNMAZ; ölü-önbellek
/// temizliği yalnız `cache/` içine bakar. Sonuç: ~1,19 GB'lık yetim ağaç diskte kalır ve
/// güncelleme "Yetersiz disk alanı" ile KALICI olarak reddedilebilir — artığı silecek olan şey
/// güncellemenin kendisidir.
#[test]
fn KRITIK_kesintiden_kalan_runtime_new_ACILISTA_temizlenir() {
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    runtime_kur(&install::runtime_dir(kok), "CALISAN");
    runtime_kur(&install::runtime_new_dir(kok), "YARIM-KALAN");
    fs::create_dir_all(kok.join("runtime.bozuk").join("PEMF_Backend")).unwrap();

    let kurtarildi = flow::yarim_takasi_kurtar(kok);

    assert!(!kurtarildi, "calisan kurulum VARKEN kurtarma yapilmamali (mevcut sozlesme)");
    assert_eq!(imza_oku(&install::runtime_dir(kok)), "CALISAN", "calisan surum bozuldu");
    assert!(
        !install::runtime_new_dir(kok).exists(),
        "kesintiden kalan runtime.new diskte BIRAKILDI — bir sonraki guncelleme disk kapisinda \
         kalici olarak reddedilebilir (artigi silecek olan sey guncellemenin kendisi)"
    );
    assert!(
        !kok.join("runtime.bozuk").exists(),
        "runtime.bozuk teshis kopyasi diskte birakildi (geri donus yolu DEGIL)"
    );
}

/// KARŞI-KANIT (C9): temizlik `runtime.old`a ASLA dokunmaz — o son bilinen ÇALIŞAN sürümdür.
#[test]
fn KARSIT_KANIT_runtime_old_temizlikte_KORUNUR() {
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    runtime_kur(&install::runtime_dir(kok), "CALISAN");
    runtime_kur(&install::runtime_old_dir(kok), "GERI-DONUS-YOLU");

    flow::yarim_takasi_kurtar(kok);

    assert_eq!(
        imza_oku(&install::runtime_old_dir(kok)),
        "GERI-DONUS-YOLU",
        "runtime.old SILINDI — saglik kapisi duserse geri donulecek surum yok olur"
    );
}

/// C11 — APP KATMANI takasının ortasında kapanma kurtarılmıyor.
///
/// `app_katmanini_degistir` app köklerini (exe + `_internal/frontend`) canlı ağaçtan `_app_yedek`e
/// TAŞIR, sonra yeni app'i açar. Arada kesinti olursa `runtime/` YERİNDE kalır ama içi eksiktir →
/// `yarim_takasi_kurtar` `rt.exists()` yüzünden hemen `false` döner ve sağlam yedek YETİM kalır.
/// Kullanıcı "kurulu değil" ekranı görür ve ~1,46 GB deps'i yeniden indirmek zorunda kalır.
#[test]
fn KRITIK_APP_katmani_takasinin_ortasinda_kapanma_KURTARILIR() {
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    let rt = install::runtime_dir(kok);
    let yedek = install::app_backup_dir(kok);

    // Kesinti anı: app kökleri yedeğe TAŞINDI, yeni app HENÜZ açılmadı.
    //  · runtime/ var ama YAPISAL OLARAK GEÇERSİZ (exe + frontend yok, deps yerinde)
    //  · _app_yedek/ sağlam app'i ve sınır dosyasını taşıyor
    fs::create_dir_all(rt.join("PEMF_Backend").join("_internal").join("ai_hub")).unwrap();
    runtime_kur(&yedek, "CALISAN-APP");
    fs::write(
        yedek.join("PEMF_Backend").join("_app_roots.json"),
        format!(
            r#"{{"roots":["PEMF_Backend/{}","PEMF_Backend/_internal/frontend"]}}"#,
            exe_adi()
        ),
    )
    .unwrap();
    // Yapisal gecerlilik = exe + frontend/dist/index.html varligi (flow::agac_yapisal_gecerli_mi
    // ozel bir yardimci; test onu cagirmak icin gorunurlugunu DEGISTIRMEZ, ayni sarti olcer).
    assert!(!rt.join("PEMF_Backend").join(exe_adi()).exists(), "senaryo kurulumu hatali: exe var");

    let kurtarildi = flow::yarim_takasi_kurtar(kok);

    assert!(
        kurtarildi,
        "app katmani takasinin ortasinda kesilen kurulum KURTARILMADI — cihaz 'kurulu degil' \
         gorunur ve saglam _app_yedek yetim kalir (~1,46 GB yeniden indirme)"
    );
    assert!(rt.join("PEMF_Backend").join(exe_adi()).exists(), "kurtarma sonrasi exe yok");
    assert!(
        rt.join("PEMF_Backend").join("_internal").join("frontend").join("dist").join("index.html").exists(),
        "kurtarma sonrasi frontend yok"
    );
    assert_eq!(imza_oku(&rt), "CALISAN-APP", "eski calisan app geri konmadi");
    assert!(!yedek.exists(), "kurtarma sonrasi _app_yedek temizlenmedi");
}

/// KARŞI-KANIT (C11): SAĞLAM bir kuruluma dokunulmaz — kurtarma aşırı genişlemesin.
#[test]
fn KARSIT_KANIT_saglam_kurulum_APP_kurtarmasindan_ETKILENMEZ() {
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    runtime_kur(&install::runtime_dir(kok), "SAGLAM");
    // Eski bir yedek artığı dursa bile sağlam ağaç geri alınmamalı:
    runtime_kur(&install::app_backup_dir(kok), "ESKI-YEDEK");

    let kurtarildi = flow::yarim_takasi_kurtar(kok);

    assert!(!kurtarildi, "saglam kurulumda kurtarma calisti — calisan surum eskiye DONDURULDU");
    assert_eq!(imza_oku(&install::runtime_dir(kok)), "SAGLAM", "saglam agac degistirildi");
}
