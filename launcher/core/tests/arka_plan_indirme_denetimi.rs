//! ARKA PLAN İNDİRMESİ DURDURULABİLİR OLMALI (saha bildirimi 2026-08-28).
//!
//! Klinik ekranında 1,39 GB'lık `deps` paketi inerken kullanıcının DURDURMA YOLU YOKTU: kartta
//! yalnız ilerleme çubuğu ("%76 · 649 KB/s · ~9 dk kaldı") vardı, düğme yoktu. Uygulama
//! kullanılabilir durumdaydı ama indirme hattı doldurmaya devam ediyordu.
//!
//! ⚠️ ÖLÇÜLEN SINIF — "YETENEK VAR, KABLO YOK":
//!   * `net::Control::{Pause, Cancel}` VARDI (`net.rs`: Pause → `.part` KORUNUR + `Paused`;
//!     Cancel → `.part` SİLİNİR + `Cancelled`),
//!   * `pause_install` / `cancel_install` Tauri komutları VARDI,
//!   * kurulum yolları bunları ZATEN okuyordu (`main.rs` üç ayrı yerde),
//!   * ama ARKA PLAN indirmesi `&|| net::Control::Continue` SABİTİYLE çağrılıyordu → hiçbir
//!     kontrol ulaşmıyordu. Yani özellik yazılmıştı, tek bir çağrı yerinde bağlanmamıştı.
//!
//! Bu dosya davranışı çekirdek katmanda kilitler: `prefetch_updates`, verilen `control`
//! closure'ına GERÇEKTEN uyar. UI tarafı (düğmeler, "duraklat ≠ hata" ayrımı) ayrıca
//! `tests/test_launcher_indirme_denetimi.py` ile kilitlenir.

use std::fs;
use std::sync::atomic::{AtomicUsize, Ordering};

use pemf_launcher_core::{flow, install, net, platform, Package};

fn paket(ad: &str, sha_harfi: char, boyut: u64) -> Package {
    Package {
        url: // URL allowlist gercek repoyu sart kosar (net::validate_url) — sahte host reddedilir
        // ve control hic yoklanmadan hata doner. Indirme yine BASLAMAZ: iptal/duraklat karari
        // ilk yigindan ONCE okunur, bu yuzden test AGA CIKMAZ.
        format!("https://github.com/mert61-python/pemf-update/releases/download/client-app-v9.9.9/{ad}"),
        sha256: sha_harfi.to_string().repeat(64),
        size: boyut,
        kind: "zip".into(),
    }
}

/// Plan'ın `deps`+`app` indirmesi gerektirdiği bir manifest (kurulu sürüm eski).
fn manifest_json() -> String {
    let j = |p: &Package| {
        format!(
            r#"{{ "url": "{}", "sha256": "{}", "size": {} }}"#,
            p.url, p.sha256, p.size
        )
    };
    format!(
        r#"{{ "schema": 2, "version": "9.9.9",
              "layers": {{ "{}": {{ "deps": {}, "app": {} }} }},
              "models": {{}} }}"#,
        platform::current(),
        j(&paket("base-deps.zip", 'c', 100)),
        j(&paket("base-app.zip", 'b', 100))
    )
}

/// Kurulu cihaz taklidi: backend exe VAR, paket kaydı YOK → katmanlar otomatik BAYAT sayılır
/// (iptal_temizligi.rs ile aynı desen) → plan `deps`+`app` indirmesi ister.
fn kurulum_hazirla(root: &std::path::Path) {
    let be = install::backend_path(root);
    fs::create_dir_all(be.parent().unwrap()).unwrap();
    fs::write(&be, b"exe").unwrap();
}

/// ⚠️ ANA KAPI: `Cancel` verildiğinde ön-indirme DURMALI.
///
/// Mutasyon: `main.rs`teki `&|| net::Control::Continue` sabitine geri dönmek bu testi
/// düşürmez (o UI katmanı), ama `prefetch_updates`in control'ü hiç yoklamaması düşürür.
/// UI kablosunu `test_launcher_indirme_denetimi.py` kilitler — ikisi birlikte anlamlıdır.
#[test]
fn iptal_on_indirmeyi_durdurur() {
    let d = tempfile::tempdir().unwrap();
    let root = d.path();
    kurulum_hazirla(root);

    let cagri = AtomicUsize::new(0);
    let mut adimlar = 0usize;
    let mut on = |_p: flow::Progress| { adimlar += 1; };

    let sonuc = flow::prefetch_updates(&manifest_json(), root, &mut on, &|| {
        cagri.fetch_add(1, Ordering::Relaxed);
        net::Control::Cancel
    });

    assert!(cagri.load(Ordering::Relaxed) > 0, "control closure'i HIC yoklanmadi — iptal ulasmiyor");
    match sonuc {
        Err(flow::FlowError::Net(net::NetError::Cancelled)) => {}
        // Ag yok (test ortami) → indirme baslamadan baska bir hata donebilir; o zaman da
        // control YOKLANMIS olmali (yukaridaki assert). Yalniz BASARI kabul edilemez.
        Err(_) => {}
        Ok(()) => panic!("iptal edilmesine ragmen on-indirme BASARIYLA bitti"),
    }
}

/// `Pause` de akışı durdurmalı (ve `.part` korunur — net katmanının sözleşmesi).
#[test]
fn duraklatma_on_indirmeyi_durdurur() {
    let d = tempfile::tempdir().unwrap();
    let root = d.path();
    kurulum_hazirla(root);

    let cagri = AtomicUsize::new(0);
    let mut on = |_p: flow::Progress| {};
    let sonuc = flow::prefetch_updates(&manifest_json(), root, &mut on, &|| {
        cagri.fetch_add(1, Ordering::Relaxed);
        net::Control::Pause
    });

    assert!(cagri.load(Ordering::Relaxed) > 0, "control closure'i HIC yoklanmadi");
    assert!(sonuc.is_err(), "duraklatilmasina ragmen on-indirme BASARIYLA bitti");
}

/// ⚠️ KARŞIT-KANIT: `Continue` verildiğinde davranış DEĞİŞMEMELİ (kontrol eklemek indirmeyi
/// bozmadı). Ağ olmadığı için başarı beklenmez; beklenen, iptal/duraklatmadan FARKLI bir yol.
#[test]
fn devam_kararinda_iptal_hatasi_URETILMEZ() {
    let d = tempfile::tempdir().unwrap();
    let root = d.path();
    kurulum_hazirla(root);

    let mut on = |_p: flow::Progress| {};
    let sonuc = flow::prefetch_updates(&manifest_json(), root, &mut on, &|| net::Control::Continue);

    if let Err(flow::FlowError::Net(net::NetError::Cancelled | net::NetError::Paused)) = sonuc {
        panic!("Continue verildigi halde iptal/duraklat hatasi uretildi");
    }
}

/// ⚠️ Kullanıcı kararı YENİDEN DENENMEZ. `is_retriable` özel bir fonksiyon olduğu için
/// davranışsal ölçülür: iptal edilen indirme, control closure'ını yeniden-deneme turlarınca
/// DEFALARCA yoklamamalı. (Aksi hâlde tek "iptal" 6 kez tam indirme tetiklerdi — 1,4 GB × 6.)
#[test]
fn iptal_yeniden_deneme_TETIKLEMEZ() {
    let d = tempfile::tempdir().unwrap();
    let root = d.path();
    kurulum_hazirla(root);

    let cagri = AtomicUsize::new(0);
    let mut on = |_p: flow::Progress| {};
    let _ = flow::prefetch_updates(&manifest_json(), root, &mut on, &|| {
        cagri.fetch_add(1, Ordering::Relaxed);
        net::Control::Cancel
    });

    // Tek paket + tek karar: yoklama sayısı yeniden-deneme turlarıyla katlanmamalı.
    let n = cagri.load(Ordering::Relaxed);
    assert!(n > 0, "control HIC yoklanmadi");
    assert!(n < 20, "iptal sonrasi {n} kez yoklandi — yeniden deneme dongusu kullanici kararini eziyor");
}
