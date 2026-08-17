//! GERÇEK-PAKET YÜKSELTME + GERİ ALMA TATBİKATI (2026-08-09 denetimi, Tier 3).
//!
//! ARIZA: atomik kurulum ve sağlık-kapılı geri alma yolu YALNIZ 70/900 BAYTLIK sentetik zip'lerle
//! test edilmişti. O boyutta sınanan bir yol, gerçek paketin ürettiği durumları hiç görmez:
//!   • yüzlerce dosyalı iç içe ağaç (`PEMF_Backend/_internal/...`),
//!   • yeni sürümde KALDIRILAN dosyalar (eski `.pyd`, eski web bundle parçaları),
//!   • app katmanının sınır dosyası (`_app_roots.json`) ve ona dayanan geri alma,
//!   • deps yenilendiğinde tam ağaç takası (`runtime` → `runtime.old`).
//! Yani "geri alma çalışıyor" güvencesi ölçülmemişti.
//!
//! BU TATBİKAT: gerçekçi ŞEKİLDE (yüzlerce dosya, MB mertebesi, doğru ağaç düzeni) v1 kurar,
//! v2'ye yükseltir, sağlık kapısı DÜŞMÜŞ gibi geri alır ve **v1'in dosya dosya aynı** döndüğünü
//! doğrular. Ağ yok: paketler önbelleğe doğru adla+sha ile yerleştirilir (`ensure_package`
//! önbellekteki doğru-sha dosyayı indirmeden kullanır).
//!
//! ⚠️ Gerçek 1,19 GB'lık `base-deps.zip` bilinçli olarak kullanılmaz: CI'da dakikalar sürer ve
//! kırılganlaşır. Kritik olan BOYUT değil ŞEKİL'dir — ağaç düzeni, dosya sayısı, kaldırılan
//! dosyalar ve sınır dosyası. Boyuta bağlı yol (indirme/Range/yeniden deneme) `net` testlerinde.

use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use pemf_launcher_core::{flow, install, platform};

// ── yardımcılar ─────────────────────────────────────────────────────────────

fn sha_hex(bayt: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    let mut h = Sha256::new();
    h.update(bayt);
    format!("{:x}", h.finalize())
}

/// Girdi haritasından zip üret (deterministik sıra).
fn zip_uret(girdiler: &BTreeMap<String, Vec<u8>>) -> Vec<u8> {
    let mut tampon = std::io::Cursor::new(Vec::new());
    {
        let mut z = zip::ZipWriter::new(&mut tampon);
        let ayar: zip::write::FileOptions<'_, ()> =
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (ad, veri) in girdiler {
            z.start_file(ad.clone(), ayar).unwrap();
            z.write_all(veri).unwrap();
        }
        z.finish().unwrap();
    }
    tampon.into_inner()
}

/// ⚠️ ÜRETİMDEKİ app-katmanı SINIRI — `build_tools/make_base_zip.py::APP_ROOTS` ile AYNI olmalı.
/// Tatbikat uydurma bir sınırla koşarsa gerçeği değil kendi kurgusunu doğrular (ilk yazımda tam
/// bu oldu: exe sınırın dışında bırakılmıştı ve testler yanlış sonuç verdi).
const APP_ROOTS: &[&str] = &[
    "PEMF_Backend/PEMF_Backend.exe",
    "PEMF_Backend/_internal/ai_hub",
    "PEMF_Backend/_internal/frontend",
    "PEMF_Backend/_internal/VERSION",
    "PEMF_Backend/_app_roots.json",
];

fn app_roots_json() -> Vec<u8> {
    let liste: Vec<String> = APP_ROOTS
        .iter()
        .map(|r| {
            // exe adı platforma göre değişir; sınır dosyası diskteki gerçek adı taşımalı.
            if *r == "PEMF_Backend/PEMF_Backend.exe" {
                format!("PEMF_Backend/{}", platform::backend_exe_name())
            } else {
                r.to_string()
            }
        })
        .collect();
    format!(r#"{{"roots":{}}}"#, serde_json::to_string(&liste).unwrap()).into_bytes()
}

/// deps katmanı: ağır, seyrek değişen ağaç (yüzlerce dosya).
fn deps_agaci(surum: &str) -> BTreeMap<String, Vec<u8>> {
    let mut m = BTreeMap::new();
    for i in 0..300 {
        m.insert(
            format!("PEMF_Backend/_internal/paket{}/modul{}.pyd", i % 12, i),
            format!("deps {surum} modul {i} {}", "x".repeat(2048)).into_bytes(),
        );
    }
    m.insert(
        "PEMF_Backend/_internal/torch/lib/torch_cpu.dll".into(),
        format!("ağır ikili {surum} {}", "y".repeat(64 * 1024)).into_bytes(),
    );
    m
}

/// app katmanı: her sürümde değişen ince katman + SINIR dosyası.
///
/// `fazla` = yalnız bu sürümde bulunan dosyalar (bir sonraki sürümde KALDIRILMIŞ olacak) —
/// `_app_roots.json` sınırı olmadan bunlar diskte yaşamaya devam ederdi.
fn app_agaci(surum: &str, fazla: usize, exe_var: bool) -> BTreeMap<String, Vec<u8>> {
    let mut m = BTreeMap::new();
    if exe_var {
        m.insert(
            format!("PEMF_Backend/{}", platform::backend_exe_name()),
            format!("EXE {surum}").into_bytes(),
        );
    }
    m.insert("PEMF_Backend/_app_roots.json".into(), app_roots_json());
    m.insert(
        "PEMF_Backend/_internal/VERSION".into(),
        surum.as_bytes().to_vec(),
    );
    m.insert(
        "PEMF_Backend/_internal/frontend/dist/index.html".into(),
        format!("<html>{surum}</html>").into_bytes(),
    );
    for i in 0..60 {
        m.insert(
            format!("PEMF_Backend/_internal/ai_hub/model{}.onnx", i),
            format!("app {surum} model {i} {}", "z".repeat(1024)).into_bytes(),
        );
    }
    for i in 0..fazla {
        m.insert(
            format!("PEMF_Backend/_internal/frontend/dist/eski_parca_{}.js", i),
            format!("yalniz {surum} {}", "q".repeat(512)).into_bytes(),
        );
    }
    m
}

struct Paket {
    bayt: Vec<u8>,
    sha: String,
    url: String,
}

impl Paket {
    fn yeni(bayt: Vec<u8>, ad: &str) -> Self {
        let sha = sha_hex(&bayt);
        Self { sha, url: format!("https://github.com/o/r/releases/download/v/{ad}"), bayt }
    }
    fn json(&self) -> String {
        format!(
            r#"{{ "url": "{}", "sha256": "{}", "size": {} }}"#,
            self.url,
            self.sha,
            self.bayt.len()
        )
    }
    /// Paketi önbelleğe doğru adla koy → `ensure_package` ağa ÇIKMAZ.
    fn onbellege_koy(&self, install_root: &Path, etiket: &str) {
        let cache = install::cache_dir(install_root);
        fs::create_dir_all(&cache).unwrap();
        let pkg = pemf_launcher_core::Package {
            url: self.url.clone(),
            sha256: self.sha.clone(),
            size: self.bayt.len() as u64,
            kind: "zip".into(),
        };
        fs::write(flow::cache_path_for(&pkg, &cache, etiket), &self.bayt).unwrap();
    }
}

fn manifest(deps: &Paket, app: &Paket) -> String {
    format!(
        r#"{{ "schema": 2, "version": "9.9.9",
              "layers": {{ "{}": {{ "deps": {}, "app": {} }} }},
              "models": {{}} }}"#,
        platform::current(),
        deps.json(),
        app.json()
    )
}

/// Ağacın dosya→sha haritası (karşılaştırma için).
///
/// ⚠️ `_app_yedek` HARİÇ: geri alma yedeği `runtime/` İÇİNDE tutulur (bilinçli — aynı birimde
/// rename metadata işlemidir, 1,2 GB kopyalamaya gerek kalmaz). Yedeği saymak "yükseltme
/// yapıldı mı?" sorusunu yanıltır: taşınan eski dosyalar hâlâ ağaçta görünür. Bu, tatbikatın
/// ilk sürümünde yanlış bir "bayat dosya sızıntısı" alarmı üretti.
fn agac_parmak_izi(kok: &Path) -> BTreeMap<String, String> {
    fn gez(kok: &Path, p: &Path, out: &mut BTreeMap<String, String>) {
        for g in fs::read_dir(p).unwrap().flatten() {
            let yol = g.path();
            if yol.file_name().is_some_and(|n| n == "_app_yedek") {
                continue;
            }
            if yol.is_dir() {
                gez(kok, &yol, out);
            } else {
                let bagil = yol.strip_prefix(kok).unwrap().to_string_lossy().replace('\\', "/");
                out.insert(bagil, sha_hex(&fs::read(&yol).unwrap()));
            }
        }
    }
    let mut m = BTreeMap::new();
    if kok.is_dir() {
        gez(kok, kok, &mut m);
    }
    m
}

fn sessiz() -> impl FnMut(flow::Progress) {
    |_p| {}
}

fn devam() -> impl Fn() -> pemf_launcher_core::net::Control {
    || pemf_launcher_core::net::Control::Continue
}

/// v1'i kur (KURULUM akışı — `update_installed` yalnız KURULU cihazda çalışır: `pending_updates`
/// backend exe yoksa "güncelleme yok" der ve bu bilinçlidir; ilk kurulum ayrı yoldur).
fn v1_kur(kok: &Path) -> (Paket, Paket) {
    let deps1 = Paket::yeni(zip_uret(&deps_agaci("v1")), "base-deps.zip");
    let app1 = Paket::yeni(zip_uret(&app_agaci("v1", 8, true)), "base-app.zip");
    deps1.onbellege_koy(kok, "deps");
    app1.onbellege_koy(kok, "app");

    let m = manifest(&deps1, &app1);
    flow::install_profiles(&m, &[], kok, &mut sessiz(), &devam()).unwrap();
    assert!(
        install::backend_path(kok).exists(),
        "v1 kurulmadi (backend exe yok)"
    );
    (deps1, app1)
}

// ═══════════════════════════════════════════════════════════════════════════
// TATBİKAT 1 — app katmanı yükseltmesi, sağlık kapısı DÜŞTÜ → geri alma
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn KRITIK_app_yukseltmesi_geri_alininca_v1_BIREBIR_doner() {
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    let (deps1, _app1) = v1_kur(kok);

    let rt = install::runtime_dir(kok);
    let v1_izi = agac_parmak_izi(&rt);
    assert!(v1_izi.len() > 350, "gercekci agac kurulmadi: {} dosya", v1_izi.len());

    // v2: app değişti, deps AYNI. `fazla=0` → v1'in 8 ekstra dosyası KALDIRILMIŞ olacak.
    let app2 = Paket::yeni(zip_uret(&app_agaci("v2", 0, true)), "base-app.zip");
    app2.onbellege_koy(kok, "app");
    let m2 = manifest(&deps1, &app2);

    let geri = flow::update_installed(&m2, kok, &mut sessiz(), &devam()).unwrap();
    assert!(geri.app_yedegi && !geri.tam_takas, "app-yolu beklenirken: {geri:?}");

    // Yükseltme gerçekten oldu mu? (v1'in kaldırılan dosyaları gitmiş olmalı)
    let v2_izi = agac_parmak_izi(&rt);
    assert!(
        !v2_izi.keys().any(|k| k.contains("eski_parca_")),
        "yeni surumde KALDIRILAN dosyalar diskte kaldi — bayat dosya sizintisi"
    );
    assert_ne!(v1_izi, v2_izi, "yukseltme hicbir sey degistirmedi");

    // SAĞLIK KAPISI DÜŞTÜ → geri al.
    flow::guncellemeyi_geri_al(kok, &geri).unwrap();

    let geri_izi = agac_parmak_izi(&rt);
    assert_eq!(
        geri_izi, v1_izi,
        "geri alma v1'i BIREBIR getirmedi — fark: {:?}",
        geri_izi
            .iter()
            .filter(|(k, v)| v1_izi.get(*k) != Some(*v))
            .map(|(k, _)| k.clone())
            .collect::<Vec<_>>()
    );
    // Yedek diskte kalırsa app katmanı iki kez yer kaplar ve bir sonraki güncellemede
    // "eski sürüm" olarak yanlış sınır okunabilir.
    assert!(
        !install::app_backup_dir(kok).exists(),
        "geri almadan sonra `_app_yedek` diskte kaldi"
    );
}

#[test]
fn geri_alinan_guncelleme_KAYIT_birakmaz() {
    // Kayıt yazılırsa bir sonraki açılış bozuk sürümü "kurulu" sanar ve tekrar denemez.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    let (deps1, app1) = v1_kur(kok);

    let app2 = Paket::yeni(zip_uret(&app_agaci("v2", 0, true)), "base-app.zip");
    app2.onbellege_koy(kok, "app");
    let geri = flow::update_installed(&manifest(&deps1, &app2), kok, &mut sessiz(), &devam()).unwrap();
    flow::guncellemeyi_geri_al(kok, &geri).unwrap();

    assert_eq!(
        install::read_installed_packages(kok).app,
        app1.sha,
        "geri alinmasina ragmen YENI app sha'si kayitli — sonraki acilis bozuk surumu 'guncel' sanar"
    );
}

// ═══════════════════════════════════════════════════════════════════════════
// TATBİKAT 2 — deps yenilendi (TAM AĞAÇ TAKASI), sağlık düştü → geri alma
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn KRITIK_tam_takas_geri_alininca_v1_BIREBIR_doner() {
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    v1_kur(kok);

    let rt = install::runtime_dir(kok);
    let v1_izi = agac_parmak_izi(&rt);

    let deps2 = Paket::yeni(zip_uret(&deps_agaci("v2")), "base-deps.zip");
    let app2 = Paket::yeni(zip_uret(&app_agaci("v2", 0, true)), "base-app.zip");
    deps2.onbellege_koy(kok, "deps");
    app2.onbellege_koy(kok, "app");

    let geri = flow::update_installed(&manifest(&deps2, &app2), kok, &mut sessiz(), &devam()).unwrap();
    assert!(geri.tam_takas, "deps degistiginde TAM TAKAS beklenir: {geri:?}");
    assert!(install::runtime_old_dir(kok).is_dir(), "eski agac saklanmamis — geri donus yolu yok");
    assert_ne!(agac_parmak_izi(&rt), v1_izi);

    flow::guncellemeyi_geri_al(kok, &geri).unwrap();
    assert_eq!(agac_parmak_izi(&rt), v1_izi, "tam takas geri alinamadi");
}

#[test]
fn onaylanan_guncelleme_yedekleri_TEMIZLER() {
    // Yedekler kalırsa 1,2 GB'lık ağaç iki kez yer kaplar (LattePanda eMMC'de kurulum ölür).
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    v1_kur(kok);

    let deps2 = Paket::yeni(zip_uret(&deps_agaci("v2")), "base-deps.zip");
    let app2 = Paket::yeni(zip_uret(&app_agaci("v2", 0, true)), "base-app.zip");
    deps2.onbellege_koy(kok, "deps");
    app2.onbellege_koy(kok, "app");
    let geri = flow::update_installed(&manifest(&deps2, &app2), kok, &mut sessiz(), &devam()).unwrap();
    assert!(install::runtime_old_dir(kok).is_dir());

    flow::guncellemeyi_onayla(kok, &geri);
    assert!(!install::runtime_old_dir(kok).exists(), "onaydan sonra eski agac silinmedi");
    assert!(!install::app_backup_dir(kok).exists(), "onaydan sonra app yedegi silinmedi");
    assert_eq!(install::read_installed_packages(kok).deps, deps2.sha);
    assert_eq!(install::read_installed_packages(kok).app, app2.sha);
}

// ═══════════════════════════════════════════════════════════════════════════
// TATBİKAT 3 — KASTEN BOZUK katman: yapısal kapı tutuyor mu?
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn KRITIK_bozuk_app_katmani_kurulumu_BOZMAZ() {
    // Yeni app paketinde backend exe YOK (yayıncı hatası / yarım paket). Yapısal kapı bunu
    // yakalamalı ve eski sürüm ÇALIŞIR kalmalı — cihaz "exe'siz kurulum" ile ölmemeli.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    let (deps1, app1) = v1_kur(kok);
    let rt = install::runtime_dir(kok);
    let v1_izi = agac_parmak_izi(&rt);

    let bozuk = Paket::yeni(zip_uret(&app_agaci("v2-BOZUK", 0, false)), "base-app.zip");
    bozuk.onbellege_koy(kok, "app");

    let sonuc = flow::update_installed(&manifest(&deps1, &bozuk), kok, &mut sessiz(), &devam());
    assert!(sonuc.is_err(), "exe'siz paket KABUL EDILDI — cihaz calismaz hale gelirdi");

    assert!(
        rt.join("PEMF_Backend").join(platform::backend_exe_name()).is_file(),
        "bozuk guncelleme sonrasi backend exe YOK — kurulum oldu"
    );
    assert_eq!(agac_parmak_izi(&rt), v1_izi, "bozuk guncelleme v1'i bozdu");
    assert_eq!(install::read_installed_packages(kok).app, app1.sha, "bozuk paketin sha'si kaydedildi");
}

#[test]
fn KRITIK_bozuk_deps_katmani_CALISAN_kuruluma_DOKUNMAZ() {
    // Tam takas yolunda yeni ağaç `runtime.new`de kurulur; bozuksa takas HİÇ yapılmamalı.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    let (_deps1, _app1) = v1_kur(kok);
    let rt = install::runtime_dir(kok);
    let v1_izi = agac_parmak_izi(&rt);

    let deps2 = Paket::yeni(zip_uret(&deps_agaci("v2")), "base-deps.zip");
    let bozuk_app = Paket::yeni(zip_uret(&app_agaci("v2", 0, false)), "base-app.zip");
    deps2.onbellege_koy(kok, "deps");
    bozuk_app.onbellege_koy(kok, "app");

    let sonuc = flow::update_installed(&manifest(&deps2, &bozuk_app), kok, &mut sessiz(), &devam());
    assert!(sonuc.is_err(), "exe'siz yeni agac takas edildi");
    assert_eq!(agac_parmak_izi(&rt), v1_izi, "takas yapilmadi deniyor ama agac degismis");
    assert!(!install::runtime_new_dir(kok).exists(), "yarim `runtime.new` birakildi (disk sizintisi)");
}

// ═══════════════════════════════════════════════════════════════════════════
// TATBİKAT 4 — tatbikatın kendisi anlamlı mı?
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn tatbikat_GERCEKCI_olcekte_kosuyor() {
    // ⚠️ Bu testin var oluş sebebi: denetimin bulduğu arıza "yol yalnız 70/900 BAYTLIK zip'lerle
    // sınanmıştı" idi. Biri paketleri küçültürse tatbikat sessizce eski hâline döner.
    // Ölçüt SIKIŞTIRILMIŞ boyut DEĞİL (içerik tekrarlı olduğu için 60 KB'a iniyor); anlamlı olan
    // AÇILMIŞ hacim ve dosya sayısıdır — ağaç düzenini zorlayan şey odur.
    let deps = deps_agaci("v1");
    let app = app_agaci("v1", 8, true);
    let acik: usize = deps.values().chain(app.values()).map(|v| v.len()).sum();
    assert!(acik > 700_000, "acilmis hacim gercekci degil: {acik} bayt");
    assert!(deps.len() + app.len() > 350, "dosya sayisi az: {}", deps.len() + app.len());
    assert!(deps.keys().filter(|k| k.contains("/_internal/")).count() > 250, "agac duz kalmis");
}

/// ⚠️ TATBİKATIN GERÇEKLE BAĞI. Sınır listesi ürünle ayrışırsa tatbikat kendi kurgusunu doğrular.
/// (İlk yazımda tam bu oldu: exe sınırın dışında bırakılmıştı ve iki test yanlış sonuç verdi.)
#[test]
fn tatbikat_sinirlari_URETIMLE_ayni() {
    let py = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../build_tools/make_base_zip.py");
    let Ok(src) = fs::read_to_string(&py) else {
        eprintln!("make_base_zip.py yok — atlaniyor");
        return;
    };
    // ⚠️ Yalnız APP_ROOTS BLOĞUNA bak: dosyanın herhangi bir yerinde geçen bir dize (yorum,
    // doğrulama listesi) kapıyı geçirirdi. İlk yazımda `|| src.contains("APP_ROOTS_FILE")`
    // koşulu vardı ve o koşul HER ZAMAN doğruydu → kapı boş güvence veriyordu (mutasyon
    // turunda yakalandı: VERSION listeden çıkarıldığında test yine yeşil kaldı).
    let blok = src
        .split_once("APP_ROOTS = [")
        .expect("make_base_zip.py icinde APP_ROOTS bulunamadi")
        .1
        .split_once(']')
        .expect("APP_ROOTS listesi kapanmamis")
        .0;
    for r in APP_ROOTS {
        let bulundu = if *r == "PEMF_Backend/_app_roots.json" {
            // Bu girdi sabit ADIYLA listelenir; sabitin tanımını ayrıca doğrula.
            blok.contains("APP_ROOTS_FILE")
                && src.contains(&format!("APP_ROOTS_FILE = '{r}'"))
        } else {
            blok.contains(&format!("'{r}'"))
        };
        assert!(bulundu, "uretim APP_ROOTS'unda yok: {r} (blok: {blok})");
    }
}

/// SÜRÜM DOSYASI APP KATMANINDA OLMALI — bu tatbikatın bulduğu gerçek kusur.
///
/// `_internal/VERSION` app kökleri arasında DEĞİLDİ → deps'e düşüyordu. Sıradan bir yayın yalnız
/// app katmanını yeniler (~71 MB); dolayısıyla sürüm dosyası aylarca TAZELENMEZDİ. Launcher'ın
/// `kurulu_surum()`u tam bu dosyayı okur ve GERİ ÇAĞIRMA (`min_supported_version`) ona bakar →
/// düzeltilmiş bir cihaz "destek dışı" sanılıp zorla güncellenebilir, ya da tersi.
#[test]
fn KRITIK_surum_dosyasi_APP_katmaninda_ve_app_guncellemesinde_TAZELENIR() {
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    let (deps1, _app1) = v1_kur(kok);
    assert_eq!(install::kurulu_surum(kok), "v1");

    // Yalnız app değişiyor (sıradan yayın senaryosu) — deps AYNI.
    let app2 = Paket::yeni(zip_uret(&app_agaci("v2", 0, true)), "base-app.zip");
    app2.onbellege_koy(kok, "app");
    let geri = flow::update_installed(&manifest(&deps1, &app2), kok, &mut sessiz(), &devam()).unwrap();
    assert!(geri.app_yedegi && !geri.tam_takas, "app-yolu beklenirken: {geri:?}");

    assert_eq!(
        install::kurulu_surum(kok),
        "v2",
        "app guncellemesi surum dosyasini TAZELEMEDI — geri cagirma yanlis surume bakar"
    );

    // Geri alınırsa sürüm de v1'e dönmeli (aksi hâlde cihaz kendini yanlış tanıtır).
    flow::guncellemeyi_geri_al(kok, &geri).unwrap();
    assert_eq!(install::kurulu_surum(kok), "v1", "geri alma surumu geri getirmedi");
}

#[test]
fn onbellek_yolu_AGA_CIKMADAN_calisiyor() {
    // Tatbikat ağa çıkarsa CI'da kırılgan olur ve "geri alma testi" bir ağ testine dönüşür.
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    let (deps1, app1) = v1_kur(kok);
    let cache = install::cache_dir(kok);
    for (p, etiket) in [(&deps1, "deps"), (&app1, "app")] {
        let pkg = pemf_launcher_core::Package {
            url: p.url.clone(),
            sha256: p.sha.clone(),
            size: p.bayt.len() as u64,
            kind: "zip".into(),
        };
        assert!(
            flow::paket_onbellekte_hazir(&pkg, &cache, etiket),
            "{etiket} onbellekte degil — test ag'a cikmis olabilir"
        );
    }
}

/// Yardımcı: derleyici uyarısını sustur (PathBuf yalnız imzalarda kullanılıyor).
#[allow(dead_code)]
fn _tip_kullanimi(_p: PathBuf) {}


// ───────────────────────────────────────────────────────────────────────────
// TATBİKAT 4 — takastan SONRA profil adımında İPTAL → geri alma ÇAĞRILMALI
// (denetim 2026-08-17, bulgu 19). Bu dal HİÇBİR testte koşmuyordu: yukarıdaki
// `manifest()` `"models": {}` kullanıyor, yani plana profil HİÇ girmiyordu.
// ───────────────────────────────────────────────────────────────────────────

/// `manifest()`in profil TAŞIYAN sürümü.
///
/// ⚠️ Mevcut `manifest()`in `"models": {}` olması bu bulgunun KÖR NOKTASIYDI: profil adımı
/// planda hiç yer almadığı için takas-sonrası erken çıkış dalı hiçbir tatbikatta yürütülmedi.
fn manifest_modelli(deps: &Paket, app: &Paket, profil: (&str, &Paket)) -> String {
    format!(
        r#"{{ "schema": 2, "version": "9.9.9",
              "layers": {{ "{}": {{ "deps": {}, "app": {} }} }},
              "models": {{ "{}": {} }} }}"#,
        platform::current(),
        deps.json(),
        app.json(),
        profil.0,
        profil.1.json()
    )
}

#[test]
#[allow(non_snake_case)]
fn KRITIK_profil_adiminda_IPTAL_v1e_GERI_DONER() {
    let d = tempfile::tempdir().unwrap();
    let kok = d.path();
    v1_kur(kok);
    let v1_izi = agac_parmak_izi(&install::runtime_dir(kok));

    // v2 katmanları + bir profil paketi.
    let deps2 = Paket::yeni(zip_uret(&deps_agaci("v2")), "base-deps.zip");
    let app2 = Paket::yeni(zip_uret(&app_agaci("v2", 8, true)), "base-app.zip");
    let mut model = std::collections::BTreeMap::new();
    model.insert(
        "ai_models/ai_hub/em_kedi/x.onnx".to_string(),
        b"ONNX-v2".to_vec(),
    );
    let vet = Paket::yeni(zip_uret(&model), "vet.zip");
    deps2.onbellege_koy(kok, "deps");
    app2.onbellege_koy(kok, "app");
    vet.onbellege_koy(kok, "vet");

    // Profilin PLANA girmesi için iki ön koşul: kurulu olmalı VE bir sha kaydı olmalı.
    install::add_installed_profiles(kok, &["vet".to_string()]);
    install::record_model_sha(kok, "vet", &"0".repeat(64));

    let m2 = manifest_modelli(&deps2, &app2, ("vet", &vet));

    // ⚠️ ÖN KOŞUL KAPISI: plan boşsa test hiçbir şeyi ölçmemiş olur (yanlış-yeşil).
    let plan = flow::pending_updates(&m2, kok).unwrap();
    assert!(plan.deps && plan.app, "katman guncellemesi planlanmadi: {plan:?}");
    assert_eq!(plan.profiles, vec!["vet".to_string()], "profil plana girmedi: {plan:?}");

    // İptali TAM profil adımında tetikle + o anda canlı ağacın sürümünü OKU.
    let iptal = std::sync::atomic::AtomicBool::new(false);
    let gorulen = std::sync::Mutex::new(None::<String>);
    let mut on = |p: flow::Progress| {
        if let flow::Progress::Extracting { what } = &p {
            if what == "vet" {
                // ⚠️ YANLIŞ-YEŞİL KAPISI: testin GERÇEKTEN takas sonrası dala girdiğini kanıtlar.
                // Disk kapısı / ensure_package / app extract'ında düşen bir koşuda bu None kalır.
                let v = install::runtime_dir(kok)
                    .join("PEMF_Backend/_internal/VERSION");
                *gorulen.lock().unwrap() = fs::read_to_string(v).ok();
                iptal.store(true, std::sync::atomic::Ordering::SeqCst);
            }
        }
    };
    let control = || {
        if iptal.load(std::sync::atomic::Ordering::SeqCst) {
            pemf_launcher_core::net::Control::Cancel
        } else {
            pemf_launcher_core::net::Control::Continue
        }
    };

    let sonuc = flow::update_installed(&m2, kok, &mut on, &control);

    assert!(sonuc.is_err(), "iptal edilmis guncelleme BASARILI dondu: {sonuc:?}");
    assert_eq!(
        gorulen.lock().unwrap().as_deref().map(str::trim),
        Some("v2"),
        "profil adimina TAKAS SONRASI girilmedi → test yanlis dali olcuyor"
    );

    assert_eq!(
        agac_parmak_izi(&install::runtime_dir(kok)),
        v1_izi,
        "profil adiminda iptal sonrasi canli agac v1'e DONMEDI → dogrulanmamis surum saglik kapisi \
         ATLANARAK canlida kaldi (start_backend hic kosmadi) ve runtime.old bir sonraki turda \
         atomik_takas tarafindan TUKETILIR"
    );
    assert!(
        !install::runtime_old_dir(kok).exists(),
        "runtime.old temizlenmedi (~1,5 GB diskte kaldi)"
    );

    // ⚠️ KASITLI FAIL-SAFE: geri alınan güncelleme KAYIT BIRAKMAZ.
    assert_ne!(
        install::read_installed_packages(kok).deps,
        deps2.sha,
        "geri alinan guncelleme kayit YAZDI (kasitli fail-safe bozuldu)"
    );
}
