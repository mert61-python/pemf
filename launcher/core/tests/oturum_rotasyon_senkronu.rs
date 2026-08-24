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
    // ⚠️ Kullanıcı "Beni hatırla"yı SEÇMEDİYSE blob yoktur. Devir oturumunu diske yazmak,
    // kullanıcının AÇIKÇA istemediği kalıcılığı arkasından kurmak olurdu.
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
fn KRITIK_BASKA_KULLANICI_oturumu_ISLENMEZ() {
    // ⚠️ Devir oturumu farkli bir e-postaya aitse bu bir ROTASYON degil, BASKA bir giristir.
    // Sessizce diske yazmak, A kullanicisinin "beni hatirla" kaydini B ile degistirirdi.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    secret_store::save(kok, &oturum("A-JETON", 1000));
    let mut baskasi = oturum("B-JETON", 5000);
    baskasi.email = "baska@klinik.tr".into();

    assert!(!secret_store::rotasyonu_isle(kok, &baskasi), "baska kullanicinin oturumu islendi");
    assert_eq!(secret_store::load(kok).unwrap().refresh_token, "A-JETON");
}
