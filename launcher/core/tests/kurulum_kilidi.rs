// Author: mertaygn, cglrgrkn
//! EŞZAMANLI CLIENT — kurulum kilidi.
//!
//! Client'ın tek-örnek koruması yok; kullanıcı simgeye iki kez tıklayabilir. İki client aynı
//! anda kurulum yaparsa aynı `runtime.new`e açar, birbirinin backend'ini `taskkill`ler (süren
//! seansı öldürür) ve takası yarış hâlinde yapar.
//!
//! Kilit, işletim sisteminin dosya kilidine dayanır: süreç ölürse Windows tutamağı kendi
//! kapatır → bayat kilit imkânsız. (PID + canlılık sorgusu, çöken kurulumdan sonra kliniği
//! kalıcı kilitli bırakırdı.)

use pemf_launcher_core::install;

#[test]
fn KRITIK_ayni_anda_IKINCI_kurulum_engellenir() {
    let d = tempfile::tempdir().unwrap();
    let birinci = install::kurulum_kilidi_al(d.path()).expect("ilk kilit alinmali");

    let ikinci = install::kurulum_kilidi_al(d.path());
    #[cfg(windows)]
    assert!(
        ikinci.is_err(),
        "iki client ayni anda kurulum yapabiliyor → runtime.new bozulur, digerinin backend'i \
         (muhtemelen SUREN SEANS) taskkill'lenir"
    );
    #[cfg(windows)]
    {
        let m = ikinci.unwrap_err();
        assert!(
            m.contains("Başka bir PEMF Vet Client"),
            "mesaj kullaniciya ne yapacagini soylemiyor: {m}"
        );
    }
    drop(birinci);
}

#[test]
fn KRITIK_kilit_BIRAKILINCA_yeniden_alinabilir() {
    // Kilit kalıcı olmamalı: kurulum bitince sonraki kurulum/onarım yapılabilmeli.
    let d = tempfile::tempdir().unwrap();
    {
        let _k = install::kurulum_kilidi_al(d.path()).unwrap();
    } // Drop
    assert!(
        install::kurulum_kilidi_al(d.path()).is_ok(),
        "kilit birakildiktan sonra alinamiyor → cihaz kalici kilitli kalir"
    );
}

#[test]
fn KRITIK_surec_CoKSE_bile_kilit_bayat_kalmaz() {
    // Tasarımın can alıcı noktası: kilit dosyası diskte KALSA bile yeniden alınabilmeli —
    // koruma dosyanın VARLIĞI değil, AÇIK TUTAMAK'tır.
    let d = tempfile::tempdir().unwrap();
    {
        let _k = install::kurulum_kilidi_al(d.path()).unwrap();
    }
    assert!(
        install::kurulum_kilidi_al(d.path()).is_ok(),
        "kilit DOSYASININ VARLIGI engel oldu → cokmeden sonra kurulum bir daha ASLA yapilamaz"
    );
}

#[test]
fn KRITIK_kilit_TUTULURKEN_kaldirma_yapilabilir() {
    // ⚠️ Bu kusur ilk yazımda VARDI: kilit dosyası kurulum kökünün İÇİNDEydi. `remove_install`
    // bütün kökü `remove_dir_all` ile siler ve Windows AÇIK tutamaklı dosyayı sildirmez →
    // kaldırma başarısız olur, kullanıcıya yarım silinmiş kurulum kalır. Kilit artık kökün
    // DIŞINDA (geçici dizin) durur.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path().join("kurulum");
    std::fs::create_dir_all(kok.join("runtime")).unwrap();
    std::fs::write(kok.join("runtime").join("x.bin"), b"veri").unwrap();

    let _kilit = install::kurulum_kilidi_al(&kok).expect("kilit alinmali");
    install::remove_install(&kok).expect("kilit TUTULURKEN kaldirma BASARISIZ → yarim silme");
    assert!(!kok.exists(), "kurulum koku silinemedi");
}

#[test]
fn farkli_kokler_birbirini_KILITLEMEZ() {
    // Taşınabilir/ikinci kurulum ayrı kök kullanır; biri diğerini bloklamamalı.
    let a = tempfile::tempdir().unwrap();
    let b = tempfile::tempdir().unwrap();
    let _ka = install::kurulum_kilidi_al(a.path()).unwrap();
    assert!(
        install::kurulum_kilidi_al(b.path()).is_ok(),
        "farkli kurulum kokleri ayni kilidi paylasiyor"
    );
}

#[test]
fn kilit_kurulum_kokunu_OLUSTURUR() {
    // İlk kurulumda kök henüz yoktur; kilit almak onu yaratmalı, yoksa ilk kurulum patlar.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path().join("henuz-yok");
    assert!(install::kurulum_kilidi_al(&kok).is_ok());
    assert!(kok.is_dir());
}
