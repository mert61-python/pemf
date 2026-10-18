// Author: mertaygn, cglrgrkn
//! "BENİ HATIRLA" JETON ROTASYONUNDA BOZULMAZ (saha arızası 2026-08-24).
//!
//! ÖLÇÜLEN ZİNCİR: launcher oturumu DPAPI ile `auth_session.bin`e yazar VE aynı jetonları
//! uygulama penceresine devreder (`push_desktop_session`). Pencere `setSession` ile alır;
//! supabase-js `autoRefreshToken: true` ile çalışır — yayındaki masaüstü paketinde `autoRefreshToken:!0`
//! olarak DOĞRULANDI — ve arka planda yeniler. Supabase yenilemede refresh token'ı **DÖNDÜRÜR**:
//! yeni jeton tarayıcı deposunda kalır, launcher'ın diskteki kopyası BAYATLAR.
//!
//! Sonuç: bir sonraki launcher açılışında bayat jetonla yenileme denenir → GoTrue açıkça
//! reddeder → `AuthError::SessionRevoked` → `secret_store::clear()` → kayıtlı oturum SİLİNİR ve
//! kullanıcıdan yeniden e-posta+parola istenir. Güncelleme bunu güvenilir biçimde tetikler
//! (pencere açık kalıp jetonu döndürür, sonra zorunlu yeniden başlatma gelir).
//!
//! SÖZLEŞME: pencere döndürdüğü oturumu backend'e geri yazar; launcher onu okuyup diske işler.
//! Bu dosya launcher yarısının SAF karar mantığını kilitler (ağ gerektirmez).

use pemf_launcher_core::auth::Session;
use pemf_launcher_core::secret_store;

fn oturum(refresh: &str, exp: i64) -> Session {
    Session {
        access_token: "AT".into(),
        refresh_token: refresh.into(),
        email: "vet@klinik.tr".into(),
        expires_at: exp,
    }
}

#[test]
fn KRITIK_backend_DAHA_YENI_jeton_tutuyorsa_diske_islenir() {
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    // Diskte ESKİ (döndürülmüş, artık geçersiz) jeton:
    assert!(secret_store::save(kok, &oturum("ESKI-DONDURULDU", 1000)));

    // Pencere yeniledi ve backend'e YENİ oturumu geri yazdı:
    let backendteki = oturum("YENI-GECERLI", 5000);

    let islendi = secret_store::rotasyonu_isle(kok, &backendteki);

    assert!(islendi, "backend'teki YENI jeton diske ISLENMEDI — bir sonraki acilista bayat jetonla \
                      yenileme denenir, GoTrue reddeder ve 'Beni hatirla' SILINIR");
    let okunan = secret_store::load(kok).expect("blob okunamadi");
    assert_eq!(okunan.refresh_token, "YENI-GECERLI");
    assert_eq!(okunan.expires_at, 5000, "yeni son-kullanma da islenmeli");
}

#[test]
fn KARSIT_KANIT_ayni_jeton_tekrar_YAZILMAZ() {
    // Gereksiz DPAPI+disk yazımı (60 sn'de bir) diski yorar ve dosya zaman damgasını kirletir.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    secret_store::save(kok, &oturum("AYNI", 1000));
    assert!(!secret_store::rotasyonu_isle(kok, &oturum("AYNI", 1000)), "ayni jeton yeniden yazildi");
}

#[test]
fn KRITIK_KAYITLI_OTURUM_YOKKEN_yazilmaz() {
    // ⚠️ Kullanıcı "Beni hatırla"yı SEÇMEDİYSE blob da tercih işareti de yoktur. Devir oturumunu diske yazmak,
    // kullanıcının AÇIKÇA istemediği kalıcılığı arkasından kurmak olurdu (2026-10-18: RIZA kapısı aynen — işaret yok).
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    assert!(secret_store::load(kok).is_none(), "onkosul: blob olmamali");

    let islendi = secret_store::rotasyonu_isle(kok, &oturum("YENI", 5000));

    assert!(!islendi, "'Beni hatirla' KAPALIYKEN oturum diske yazildi — kullanicinin secmedigi \
                       kaliciligi arkasindan kurar");
    assert!(secret_store::load(kok).is_none(), "blob olusturuldu");
}

#[test]
fn KARSIT_KANIT_BOS_jeton_kaydi_BOZMAZ() {
    // Backend `{}` ya da eksik alan dönebilir; bos jetonu diske yazmak kayitli oturumu YOK EDERDI.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    secret_store::save(kok, &oturum("SAGLAM", 1000));
    assert!(!secret_store::rotasyonu_isle(kok, &oturum("", 5000)), "bos jeton islendi");
    assert_eq!(secret_store::load(kok).unwrap().refresh_token, "SAGLAM", "saglam kayit bozuldu");
}

#[test]
fn KRITIK_BASKA_HESAP_pencerenin_SON_hesabi_olarak_ISLENIR() {
    // ⚠️ SAHİP KARARI 2026-10-18 (auth_session.bin kaybı): launcher pencerenin SON hesabını hatırlar (çıkış + yeniden giriş,
    // CH1 hesap geçişi). Eskiden bu test tersini pinliyordu ("başka kullanıcı işlenmez") — pencerede başka hesapla giriş
    // launcher'a yansımıyor, launcher sunucuda silinmiş oturumla kalıp sonraki açılışta "Beni hatırla"yı sessizce siliyordu.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    secret_store::save(kok, &oturum("A-JETON", 5000));
    let mut baskasi = oturum("B-JETON", 1000); // daha ESKİ son-kullanma: [S4-yön] yalnız AYNI hesapta geçerli
    baskasi.email = "baska@klinik.tr".into();

    assert!(secret_store::rotasyonu_isle(kok, &baskasi), "pencerenin son hesabi launcher'a islenmedi");
    let okunan = secret_store::load(kok).unwrap();
    assert_eq!((okunan.refresh_token.as_str(), okunan.email.as_str()), ("B-JETON", "baska@klinik.tr"));
}

#[test]
fn KRITIK_pencere_cikisindan_sonra_TERCIH_isaretiyle_yeni_giris_hatirlanir() {
    // 10-13 olayının düzeltilmiş hâli: "Beni hatırla" ile giriş (işaret) → pencerede çıkış (kayıt silinir, işaret KALIR)
    // → pencerede yeni giriş → launcher onu hatırlar.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    secret_store::hatirla_tercihini_yaz(kok, true);
    secret_store::save(kok, &oturum("S-ESKI", 1000));
    secret_store::clear(kok); // pencerede çıkış
    assert!(secret_store::hatirla_isareti_path(kok).exists(), "cikis tercih isaretini de sildi");
    assert!(secret_store::rotasyonu_isle(kok, &oturum("YENI-GIRIS", 9000)), "cikistan sonraki yeni giris hatirlanmadi");
    assert_eq!(secret_store::load(kok).unwrap().refresh_token, "YENI-GIRIS");
}

#[test]
fn KARSIT_KANIT_isaretsiz_eski_kurulumda_kayit_TERCIH_sayilir() {
    // İşaret dosyası bu sürümde geldi: önceden "Beni hatırla" ile girmiş kullanıcının kaydı var ama işareti yok → ilk
    // rotasyonda işaret tamamlanır (sonraki pencere çıkışı tercihi kaybettirmesin).
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    secret_store::save(kok, &oturum("ESKI", 1000));
    assert!(!secret_store::hatirla_isareti_path(kok).exists(), "onkosul");
    secret_store::rotasyonu_isle(kok, &oturum("YENI", 5000));
    assert!(secret_store::hatirla_isareti_path(kok).exists(), "eski kurulumun tercihi tamamlanmadi");
    secret_store::hatirla_tercihini_yaz(kok, false);
    assert!(!secret_store::hatirla_isareti_path(kok).exists(), "isaretsiz giris tercihi silmedi");
}

#[test]
fn KRITIK_S4_AYNI_hesapta_daha_ESKI_jeton_diski_GERIYE_cekmez() {
    // [S4-yön] (saha 2026-09-03): bayat devir ekosu diskteki kayıttan daha ESKİ jeton getirebilir; yazmak diski geriye çeker ve
    // GoTrue reuse-detection aileyi iptal eder. SGI KARARLARI (2026-10-18) bu kapıyı yalnız AYNI hesapta bıraktı — davranış testi
    // yoktu (metin kapısı `false &&` önekini göremez; mutant tüm çekirdek testlerinden sağ çıkıyordu).
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    secret_store::save(kok, &oturum("YENI", 5000));
    let mut eko = oturum("ESKI-EKO", 1000);
    eko.email = "VET@klinik.tr".into(); // aynı hesap, farklı büyük/küçük harf
    assert!(!secret_store::rotasyonu_isle(kok, &eko), "ayni hesabin daha ESKI jetonu diske yazildi");
    assert_eq!(secret_store::load(kok).unwrap().refresh_token, "YENI");
}

#[test]
fn KARSIT_KANIT_S4_son_kullanma_BILINMIYORSA_kapi_devre_disi() {
    // Eski backend `expires_at` göndermez (0) → kapı devre dışı, döndürülmüş jeton yine işlenir.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    secret_store::save(kok, &oturum("ESKI", 5000));
    assert!(secret_store::rotasyonu_isle(kok, &oturum("YENI-BILINMEYEN", 0)), "son-kullanma bilinmeyen jeton islenmedi");
    assert_eq!(secret_store::load(kok).unwrap().refresh_token, "YENI-BILINMEYEN");
}
