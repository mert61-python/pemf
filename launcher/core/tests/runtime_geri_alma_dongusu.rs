// Author: mertaygn, cglrgrkn
//! GERİ ALINAN RUNTIME GÜNCELLEMESİ SONSUZA DEK YENİDEN DENENMEZ (denetim 2026-08-23, C2).
//!
//! ÖLÇÜLEN DURUM: sağlık kapısı düşünce güncelleme geri alınıyor ama HİÇBİR deneme sayacı
//! tutulmuyordu — kodun kendi yorumu bunu kabul ediyor: "kayıtlar yazılmadığı için disk
//! 'bilinmiyor'da kalır; sonraki açılış yeniden dener".
//!
//! Yapısal doğrulamayı geçen ama backend'i başlatamayan bir yayında sonuç şu: HER client
//! açılışında backend öldürülür, ~1,19 GB deps yeniden açılır, `start_and_wait` 180 sn boşuna
//! beklenir, sonra geri alınır. Klinik her açılışta dakikalarca bloklanır ve çıkış yolu YALNIZ
//! yayıncının manifest'e `rollout: 0` yazmasıdır.
//!
//! Launcher'ın KENDİ self-update'inde bu koruma 2026-08-04'te eklenmişti
//! (`MAX_SELFUPDATE_ATTEMPTS`, `selfupdate_attempt.json`); runtime yolunda karşılığı yoktu.
//!
//! ⚠️ SÖZLEŞME — sayaç yalnız OTOMATİK kurulumu durdurur:
//!   · Bildirim ve kullanıcının elle "Onar" demesi ETKİLENMEZ (kullanıcı zorlayabilmeli).
//!   · YENİ bir hedef (farklı sha) yayınlanınca sayaç SIFIRLANIR — düzeltme yayını hemen gelsin.
//!   · Güncelleme BAŞARILI olunca kayıt silinir.

use pemf_launcher_core::install;

fn kok() -> tempfile::TempDir {
    tempfile::tempdir().unwrap()
}

const HEDEF: &str = "app:aaa111|deps:bbb222";
const BASKA_HEDEF: &str = "app:ccc333|deps:bbb222";

#[test]
fn KRITIK_ayni_bozuk_hedef_SINIRSIZ_denenmez() {
    let d = kok();
    let k = d.path();
    assert!(
        install::runtime_otomatik_izinli(k, HEDEF),
        "hic denenmemis hedef en basta engellenmis — guncelleme HIC uygulanamaz"
    );

    for _ in 0..install::MAX_RUNTIME_ATTEMPTS {
        install::record_runtime_attempt(k, HEDEF);
    }

    assert!(
        !install::runtime_otomatik_izinli(k, HEDEF),
        "geri alinan ayni surum sinirsiz yeniden kuruluyor — klinik HER acilista dakikalarca \
         bloklanir ve tek cikis yolu yayincinin rollout:0 yazmasi"
    );
}

#[test]
fn KRITIK_YENI_hedef_sayaci_SIFIRLAR() {
    let d = kok();
    let k = d.path();
    for _ in 0..install::MAX_RUNTIME_ATTEMPTS {
        install::record_runtime_attempt(k, HEDEF);
    }
    assert!(!install::runtime_otomatik_izinli(k, HEDEF), "onkosul: eski hedef bloklu olmali");

    assert!(
        install::runtime_otomatik_izinli(k, BASKA_HEDEF),
        "YENI yayin (farkli sha) eski hedefin sayacina takildi — DUZELTME yayini cihaza ulasamaz"
    );
}

#[test]
fn KRITIK_basarili_guncelleme_sayaci_TEMIZLER() {
    let d = kok();
    let k = d.path();
    install::record_runtime_attempt(k, HEDEF);
    install::clear_runtime_attempt(k);
    assert!(
        install::runtime_otomatik_izinli(k, HEDEF),
        "basarili kurulumdan sonra sayac temizlenmedi — sonraki gercek guncelleme engellenebilir"
    );
}

#[test]
fn KARSIT_KANIT_sinir_ALTINDA_hala_denenir() {
    let d = kok();
    let k = d.path();
    // Tek bir gecici arıza (ör. o anda calisan baska bir surec) guncellemeyi KALICI durdurmamali.
    install::record_runtime_attempt(k, HEDEF);
    assert!(
        install::runtime_otomatik_izinli(k, HEDEF),
        "TEK basarisizlik guncellemeyi kalici durdurdu — gecici ariza kalici karara donusturuldu"
    );
}

#[test]
fn KARSIT_KANIT_bozuk_kayit_guncellemeyi_ENGELLEMEZ() {
    // Fail-open: kayit okunamiyorsa guncelleme AKMAYA devam etmeli (bilinmiyor = engelleme).
    let d = kok();
    let k = d.path();
    std::fs::write(k.join("runtime_attempt.json"), b"{bozuk json").unwrap();
    assert!(
        install::runtime_otomatik_izinli(k, HEDEF),
        "bozuk sayac dosyasi guncellemeyi kilitledi — tek bir bozuk bayt cihazi eski surumde dondurur"
    );
}
