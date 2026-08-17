//! "KURULUM YARIM KALDI → İPTAL ET" YABANCI `.part` DOSYALARINI SİLİYORDU (denetim 2026-08-17).
//!
//! `discard_pending` → `install::clear_partials` cache'teki **TÜM** `*.part` dosyalarını siliyordu.
//! Ölçülen açılış sırası:
//!
//!     app_window_open → … → check_runtime_update → prefetch_runtime_update → discard_pending
//!
//! Yani "Kurulum yarım kaldı, devam edilsin mi?" sorusu arka plan ön-indirmesi **BAŞLADIKTAN HEMEN
//! SONRA** ekrana geliyor. "İptal et" diyen kullanıcı, farkında olmadan o an inen ≤1,4 GB'lık
//! güncellemeyi çöpe atıyordu; sonraki turda sıfırdan iniyordu. (Windows'ta Rust std dosyayı
//! `FILE_SHARE_DELETE` ile açtığı için silme BAŞARILI olur, sonraki `rename` düşer.)
//! `disk::olu_onbellek_temizle` `.part`lara dokunmadığı için başka bir kurtarma yolu da yok.
//!
//! ⚠️ `main.rs`in kendi yorumu yalnız "aynı `.part`a İKİ YAZICI" riskini bilinçli kabul ediyor;
//! YABANCI bir `.part`ın silinmesi hiçbir yerde belgelenmemişti.
//!
//! DÜZELTME KURALI: *"GÜNCEL PLANIN ihtiyaç duyduğu `.part` silinmez; gerisi silinir."* Bu kural
//! sahipliği tahmin etmeden doğru ayrımı yapar, çünkü `prefetch_updates` TAM OLARAK plan
//! paketlerini indirir ve kurulu OLMAYAN cihazda plan boştur → yarım kalan İLK kurulumun
//! temizliği (`clear_partials`ın ASIL GEREKÇESİ) aynen korunur. 2. test bunu kilitler.

use std::fs;
use std::path::PathBuf;

use pemf_launcher_core::{flow, install, net, platform, Package};

fn paket(ad: &str, sha_harfi: char, boyut: u64) -> Package {
    Package {
        url: format!("https://github.com/o/r/releases/download/v/{ad}"),
        sha256: sha_harfi.to_string().repeat(64),
        size: boyut,
        kind: "zip".into(),
    }
}

fn manifest(deps: &Package, app: &Package) -> String {
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
        j(deps),
        j(app)
    )
}

/// Kurulu cihaz taklidi: backend exe VAR, paket kaydı YOK → katmanlar otomatik BAYAT sayılır.
fn kurulu_cihaz(kok: &std::path::Path) {
    let exe = install::backend_path(kok);
    fs::create_dir_all(exe.parent().unwrap()).unwrap();
    fs::write(&exe, b"exe").unwrap();
}

fn part_yolu(kok: &std::path::Path, pkg: &Package, etiket: &str) -> PathBuf {
    // ⚠️ AD ELLE YAZILMAZ: `net::part_path` tek kaynaktır (sha12'li adlandırma orada tanımlı ve
    // `bozuk_indirme_telafi.rs` onu kilitliyor). Elle yazmak testi bayat bir ada bağlardı.
    let cache = install::cache_dir(kok);
    net::part_path(&flow::cache_path_for(pkg, &cache, etiket), &pkg.sha256)
}

#[test]
#[allow(non_snake_case)]
fn KRITIK_aktif_on_indirmenin_parti_KORUNUR() {
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    kurulu_cihaz(kok);

    let deps = paket("base-deps.zip", 'a', 900);
    let app = paket("base-app.zip", 'b', 70);
    let man = manifest(&deps, &app);

    // ⚠️ ÖN KOŞUL KAPISI: plan boşsa koruma listesi de boş olur ve test yanlış-yeşile döner.
    let plan = flow::pending_updates(&man, kok).unwrap();
    assert!(plan.deps && plan.app, "katman guncellemesi planlanmadi: {plan:?}");

    let cache = install::cache_dir(kok);
    fs::create_dir_all(&cache).unwrap();

    let aktif = part_yolu(kok, &deps, "deps");
    fs::write(&aktif, b"1.4 GB'in yarisi").unwrap();

    // Plan DIŞI (ölü) `.part`: sha12'si plandakinden FARKLI.
    let olu = cache.join("base-deps.cccccccccccc.part");
    fs::write(&olu, b"eski yarim indirme").unwrap();

    // Çağrıdan ÖNCE: `read_dir` boş dizinde sessizce döner → dosyalar gerçekten var olmalı.
    assert!(aktif.exists() && olu.exists(), "on-kosul: iki .part da diskte olmali");

    install::clear_partials(kok, &flow::plan_part_paths(&man, kok));

    assert!(
        aktif.exists(),
        "AKTIF on-indirmenin .part'i SILINDI → o an inen <=1,4 GB'lik guncelleme cope gitti \
         (sonraki turda sifirdan iner)"
    );
    assert!(
        !olu.exists(),
        "olu .part temizlenmedi → clear_partials'in ASIL GEREKCESI (yarim kurulumu temizle) bozuldu"
    );
}

#[test]
#[allow(non_snake_case)]
fn kurulu_OLMAYAN_cihazda_TUM_partlar_SILINIR() {
    // ⚠️ ASIL GEREKÇENİN REGRESYON KİLİDİ: yarım kalan İLK kurulumun temizliği DEĞİŞMEMELİ.
    // Kurulu olmayan cihazda `pending_updates` boş plan döner → koruma listesi boş → hepsi silinir.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    // backend exe YOK (kurulu değil)

    let deps = paket("base-deps.zip", 'a', 900);
    let app = paket("base-app.zip", 'b', 70);
    let man = manifest(&deps, &app);

    let cache = install::cache_dir(kok);
    fs::create_dir_all(&cache).unwrap();
    let p1 = cache.join("base-deps.aaaaaaaaaaaa.part");
    let p2 = cache.join("base-app.bbbbbbbbbbbb.part");
    fs::write(&p1, b"x").unwrap();
    fs::write(&p2, b"y").unwrap();

    install::clear_partials(kok, &flow::plan_part_paths(&man, kok));

    assert!(!p1.exists() && !p2.exists(), "kurulu OLMAYAN cihazda .part'lar temizlenmedi");
}

#[test]
#[allow(non_snake_case)]
fn manifest_bozuksa_KORUMA_LISTESI_BOS_doner() {
    // Fail-safe: manifest çözülemezse liste boş olur. Çağıran (`discard_pending`) manifest YOKKEN
    // temizliği HİÇ yapmaz; bozuk manifest hâlinde de en kötü sonuç bugünkü davranıştır.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    kurulu_cihaz(kok);

    assert!(flow::plan_part_paths("{bu-json-degil", kok).is_empty());
    assert!(flow::plan_part_paths("", kok).is_empty());
}
