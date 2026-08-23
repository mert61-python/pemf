// Author: mertaygn, cglrgrkn
//! SAĞLIK KAPISI GEÇTİ AMA CİHAZ SEANS AÇAMIYOR (denetim 2026-08-23, C5).
//!
//! ÖLÇÜLEN DURUM: `wait_for_health` = HTTP 200 + `launcherNonce`. Backend AYNI yanıtta `dbReady`
//! alanını da yayınlıyor ve `/api/session/start` tam o alana bakıp 503 döndürüyor
//! (`api_server::_kayit_db_hazir`). Yani DB tarafını bozan bir yayında: backend açılır, 200 döner,
//! launcher "sağlıklı" der, sha kaydedilir ve **`runtime.old` SİLİNİR**. Klinik hiçbir seans
//! başlatamaz ve OTOMATİK geri dönüş yolu artık yoktur; tek çare kullanıcının "Onar"a basmasıdır.
//!
//! ⚠️ ÇÖZÜM `wait_for_health`E KAPI EKLEMEK DEĞİLDİR. Backend'in kendi yorumu bunu açıkça
//! reddediyor: "Sağlığın kendisini DÜŞÜRMEZ: backend ayakta ve acil durdurma yolu çalışıyor."
//! DB bozukken bile E-stop çalışmalıdır; sağlığı düşürmek onu da düşürürdü.
//!
//! DOĞRU YER: güncellemeyi ONAYLAMADAN hemen önce TEK SEFERLİK gövde okuması. Cihaz ayakta ama
//! seans açamıyorsa o yayın BAŞARISIZDIR — geri alınmalı.
//!
//! ⚠️ BİLİNMİYORSA GERİ ALMA YOK: eski backend'ler `dbReady` alanını yansıtmaz. Alan yoksa /
//! yanıt okunamıyorsa `None` döner ve güncelleme normal onaylanır — bilinmeyeni "bozuk" saymak,
//! sahadaki eski sürümleri güncellenemez yapardı (nonce'taki geriye-uyum kuralının aynısı).

use pemf_launcher_core::backend;

#[test]
fn KRITIK_dbReady_FALSE_ise_yayin_basarisiz_sayilir() {
    let govde = r#"{"status":"ok","version":"1.9.20","dbReady":false,"launcherNonce":"abc"}"#;
    assert_eq!(
        backend::db_hazir_govdeden(govde),
        Some(false),
        "dbReady=false okunamadi — DB'yi bozan yayin 'saglikli' sayilip onaylanir, runtime.old \
         SILINIR ve klinik hicbir seans acamaz (geri donus yolu yok olur)"
    );
}

#[test]
fn KARSIT_KANIT_dbReady_TRUE_normal_onaylanir() {
    let govde = r#"{"status":"ok","dbReady":true}"#;
    assert_eq!(backend::db_hazir_govdeden(govde), Some(true));
}

#[test]
fn KARSIT_KANIT_alan_YOKSA_bilinmiyor_doner() {
    // Eski backend: alani hic yansitmaz. "Bozuk" saymak sahadaki eski surumleri kilitlerdi.
    let govde = r#"{"status":"ok","version":"1.9.10"}"#;
    assert_eq!(
        backend::db_hazir_govdeden(govde),
        None,
        "alan yokken 'bozuk' varsayildi — eski backend'e guncelleme HIC uygulanamaz"
    );
}

#[test]
fn KARSIT_KANIT_bozuk_govde_bilinmiyor_doner() {
    assert_eq!(backend::db_hazir_govdeden("bu json degil"), None);
    assert_eq!(backend::db_hazir_govdeden(""), None);
    // Beklenmedik tip de "bilinmiyor" olmali, "false" DEGIL.
    assert_eq!(backend::db_hazir_govdeden(r#"{"dbReady":"evet"}"#), None);
}
