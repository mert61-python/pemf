// Author: mertaygn, cglrgrkn
//! PROFIL KALDIRMA KAPISI (denetim 2026-09-06).
//!
//! "Profilleri degistir" ekraninda birakilan profil diskten kaldirilir. Bu dosya `flow::remove_profiles`in
//! DAVRANISINI gercek dosya sistemi + gercek zip'lerle olcer:
//!   (a) ortak dosya KORUNUR, yalniz-A dosyalari silinir, bos dizin budanir, kayitlar guncellenir,
//!   (b) son profil kaldirilamaz,
//!   (c) profilin kendi zip'i yoksa → eyleme donuk hata, hicbir sey silinmez,
//!   (d) KALAN profilin zip'i yoksa → red (ortak kume hesaplanamaz), hicbir sey silinmez,
//!   (e) `..` / `runtime/x` / mutlak yol iceren zip → red, hicbir sey silinmez,
//!   (f) `model_parts` (A-2.zip) dosyalari da silinir,
//!   (g) uygulama URL'si kurulu profilleri tasir, onbellek-kirici korunur,
//!   (h) bozuk (zip olmayan) onbellek dosyasi — kaldirilanin ya da KALANIN — red, hicbir sey silinmez,
//!   (i) hicbir `Progress` olayi uretilmez (UI "Kaldırılıyor…" ekranini kendisi yonetir),
//!   (j) silme ortasinda dosya sistemi hatasi → eyleme donuk metin, kayit DEGISMEZ (Onar toparlar).
//!
//! Hasta verisi koklerine (PEMF_GUI / PEMF_System) HIC dokunulmaz: testler yalniz tempdir'de kosar.

use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use pemf_launcher_core::{flow, install, platform, Manifest};

const SHA_A: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const SHA_A2: &str = "a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2";
const SHA_B: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const SHA_BASE: &str = "0000000000000000000000000000000000000000000000000000000000000000";

const ORTAK: &str = "ai_models/ai_hub/shared/common.onnx";
const YALNIZ_A: &str = "ai_models/ai_hub/a/only_a.onnx";
const A_PARCA: &str = "ai_models/ai_hub/a/deep/part2.pt";
const YALNIZ_B: &str = "ai_models/ai_hub/b/only_b.onnx";

fn zip_uret(girdiler: &[(&str, &[u8])]) -> Vec<u8> {
    let mut tampon = std::io::Cursor::new(Vec::new());
    {
        let mut z = zip::ZipWriter::new(&mut tampon);
        let ayar: zip::write::FileOptions<'_, ()> =
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (ad, veri) in girdiler {
            z.start_file(*ad, ayar).unwrap();
            z.write_all(veri).unwrap();
        }
        z.finish().unwrap();
    }
    tampon.into_inner()
}

fn manifest_raw() -> String {
    let plat = platform::current();
    format!(
        r#"{{ "schema": 2, "version": "1.0.0",
              "runtimes": {{ "{plat}": {{ "url": "https://github.com/x/base.zip", "sha256": "{SHA_BASE}", "size": 10 }} }},
              "models": {{
                 "a": {{ "url": "https://github.com/x/a.zip", "sha256": "{SHA_A}", "size": 10 }},
                 "b": {{ "url": "https://github.com/x/b.zip", "sha256": "{SHA_B}", "size": 10 }}
              }},
              "model_parts": {{ "a": [ {{ "url": "https://github.com/x/a-2.zip", "sha256": "{SHA_A2}", "size": 10 }} ] }} }}"#
    )
}

/// Kurulu bir cihaz: a (ana + parca) ve b kurulu, ortak dosya ikisinde de var.
struct Cihaz {
    _dir: tempfile::TempDir,
    root: PathBuf,
    manifest: Manifest,
}

impl Cihaz {
    fn zip_yolu(&self, profil: &str, parca: usize) -> PathBuf {
        let pkgs = self.manifest.model_packages(profil).unwrap();
        let etiket = if parca == 0 { profil.to_string() } else { format!("{profil}-p{}", parca + 1) };
        flow::cache_path_for(pkgs[parca], &install::cache_dir(&self.root), &etiket)
    }
    fn var(&self, rel: &str) -> bool {
        self.root.join(rel).exists()
    }
    fn kaldir(&self, profiller: &[&str]) -> Result<flow::RemoveReport, flow::FlowError> {
        let p: Vec<String> = profiller.iter().map(|s| s.to_string()).collect();
        flow::remove_profiles(&self.root, &self.manifest, &p, &mut |_| {})
    }
}

/// `a_ekstra`: a.zip'e eklenecek ek girdi (guvensiz-yol senaryolari icin).
fn cihaz_kur(a_ekstra: Option<(&str, &[u8])>) -> Cihaz {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().join("PEMF Vet Client");
    let manifest = Manifest::parse(&manifest_raw()).unwrap();
    let cache = install::cache_dir(&root);
    fs::create_dir_all(&cache).unwrap();

    let mut a_girdiler: Vec<(&str, &[u8])> = vec![(YALNIZ_A, b"only-a-bytes!"), (ORTAK, b"shared-model-bytes")];
    if let Some(e) = a_ekstra {
        a_girdiler.push(e);
    }
    let a2_girdiler: Vec<(&str, &[u8])> = vec![(A_PARCA, b"part-two-bytes")];
    let b_girdiler: Vec<(&str, &[u8])> = vec![(YALNIZ_B, b"only-b"), (ORTAK, b"shared-model-bytes")];

    let c = Cihaz { _dir: dir, root: root.clone(), manifest };
    fs::write(c.zip_yolu("a", 0), zip_uret(&a_girdiler)).unwrap();
    fs::write(c.zip_yolu("a", 1), zip_uret(&a2_girdiler)).unwrap();
    fs::write(c.zip_yolu("b", 0), zip_uret(&b_girdiler)).unwrap();

    // Kurulumun acmis olacagi dosyalar (yalniz mesru ai_models/ girdileri diske yazilir).
    for (ad, veri) in a_girdiler.iter().chain(a2_girdiler.iter()).chain(b_girdiler.iter()) {
        if !ad.starts_with("ai_models/") {
            continue;
        }
        let p = root.join(ad);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(&p, veri).unwrap();
    }
    // Runtime agaci + kayitlar (gercek kurulumla ayni yardimcilar).
    let exe = install::backend_path(&root);
    fs::create_dir_all(exe.parent().unwrap()).unwrap();
    fs::write(&exe, b"exe").unwrap();
    install::record_base_sha(&root, SHA_BASE);
    install::record_model_sha(&root, "a", &format!("{SHA_A}+{SHA_A2}"));
    install::record_model_sha(&root, "b", SHA_B);
    install::add_installed_profiles(&root, &["a".to_string(), "b".to_string()]);
    c
}

/// Diskteki TUM dosyalarin (kok altinda) goreli yol → icerik haritasi: "hicbir sey silinmedi" kaniti.
fn agac(root: &Path) -> BTreeMap<String, Vec<u8>> {
    fn yuru(kok: &Path, d: &Path, m: &mut BTreeMap<String, Vec<u8>>) {
        for e in fs::read_dir(d).unwrap().flatten() {
            let p = e.path();
            if p.is_dir() {
                yuru(kok, &p, m);
            } else {
                let rel = p.strip_prefix(kok).unwrap().to_string_lossy().replace('\\', "/");
                m.insert(rel, fs::read(&p).unwrap());
            }
        }
    }
    let mut m = BTreeMap::new();
    yuru(root, root, &mut m);
    m
}

// ── (a) ortak dosya korunur, yalniz-A silinir, dizin budanir, kayitlar guncellenir ─────────────

#[test]
#[allow(non_snake_case)]
fn a_kaldirilinca_yalniz_a_dosyalari_silinir_ORTAK_korunur_kayitlar_guncellenir() {
    let c = cihaz_kur(None);
    let paket_kaydi_once = fs::read_to_string(install::installed_packages_path(&c.root)).unwrap();
    let a_zip_boyut = fs::metadata(c.zip_yolu("a", 0)).unwrap().len();
    let a2_zip_boyut = fs::metadata(c.zip_yolu("a", 1)).unwrap().len();

    let rapor = c.kaldir(&["a"]).expect("a kaldirilabilmeli");

    // Dosyalar
    assert!(!c.var(YALNIZ_A), "yalniz-A dosyasi silinmeliydi");
    assert!(!c.var(A_PARCA), "A parcasinin dosyasi silinmeliydi");
    assert!(c.var(ORTAK), "ORTAK dosya b tarafindan kullaniliyor — SILINMEMELIYDI (KEEP cikarma yok mu?)");
    assert!(c.var(YALNIZ_B), "b'nin dosyasina dokunulmamali");
    assert!(c.var("runtime"), "runtime agacina dokunulmamali");
    // Bos dizin budama
    assert!(!c.var("ai_models/ai_hub/a"), "bosalan ai_models/ai_hub/a dizini budanmaliydi");
    assert!(c.var("ai_models/ai_hub/shared"), "ortak dizin kalmali");
    assert!(c.var("ai_models"), "ai_models kokunun kendisi asla silinmez");
    // Onbellek
    assert!(!c.zip_yolu("a", 0).exists(), "cache/a.zip silinmeliydi");
    assert!(!c.zip_yolu("a", 1).exists(), "cache/a-2.zip (parca) silinmeliydi");
    assert!(c.zip_yolu("b", 0).exists(), "cache/b.zip kalmali");
    // Kayitlar
    assert_eq!(install::read_installed_profiles(&c.root), vec!["b".to_string()]);
    let paketler = install::read_installed_packages(&c.root);
    assert_eq!(paketler.models.get("b").map(String::as_str), Some(SHA_B), "b kaydi bozulmamali");
    assert!(!paketler.models.contains_key("a"), "a kaydi dusmeli");
    assert_eq!(paketler.base, SHA_BASE);
    // installed_packages.json: yalniz "a" satiri dusmus, gerisi BAYT-AYNI.
    let beklenen = paket_kaydi_once.replace(&format!("    \"a\": \"{SHA_A}+{SHA_A2}\",\n"), "");
    assert_ne!(beklenen, paket_kaydi_once, "test kurgusu: 'a' satiri bulunmali");
    let paket_kaydi_sonra = fs::read_to_string(install::installed_packages_path(&c.root)).unwrap();
    assert_eq!(paket_kaydi_sonra, beklenen, "installed_packages.json diger anahtarlar bayt-aynı kalmali");
    // Rapor
    assert_eq!(rapor.removed, vec!["a".to_string()]);
    assert_eq!(rapor.installed, vec!["b".to_string()]);
    assert_eq!(rapor.kept_shared, 1, "ortak dosya sayisi 1 olmali");
    let beklenen_bayt = b"only-a-bytes!".len() as u64 + b"part-two-bytes".len() as u64 + a_zip_boyut + a2_zip_boyut;
    assert_eq!(rapor.freed_bytes, beklenen_bayt, "bosaltilan bayt = silinen model dosyalari + zip'ler");
}

// ── (b) son profil kaldirilamaz ────────────────────────────────────────────────────────────────

#[test]
fn son_profil_kaldirilamaz_hicbir_sey_silinmez() {
    let c = cihaz_kur(None);
    let once = agac(&c.root);
    let hata = c.kaldir(&["a", "b"]).expect_err("son profil kaldirilamamali");
    let m = hata.to_string();
    assert!(m.contains("En az bir profil"), "hata metni: {m}");
    assert_eq!(agac(&c.root), once, "hicbir dosya degismemeli");
}

// ── (c) profilin kendi zip'i yok → eyleme donuk hata, hicbir sey silinmez ─────────────────────

#[test]
fn kendi_zipi_yoksa_onar_onerilir_hicbir_sey_silinmez() {
    let c = cihaz_kur(None);
    fs::remove_file(c.zip_yolu("a", 0)).unwrap();
    let once = agac(&c.root);
    let hata = c.kaldir(&["a"]).expect_err("zip yokken kaldirma reddedilmeli");
    let m = hata.to_string();
    assert!(m.contains("a.zip") && m.contains("onar"), "hata ne olduğunu ve ne yapilacagini soylemeli: {m}");
    assert_eq!(agac(&c.root), once, "hicbir dosya degismemeli");
    assert_eq!(install::read_installed_profiles(&c.root), vec!["a".to_string(), "b".to_string()]);
}

// ── (d) KALAN profilin zip'i yok → red ────────────────────────────────────────────────────────

#[test]
fn kalan_profilin_zipi_yoksa_ortak_kume_hesaplanamaz_red() {
    let c = cihaz_kur(None);
    fs::remove_file(c.zip_yolu("b", 0)).unwrap();
    let once = agac(&c.root);
    let hata = c.kaldir(&["a"]).expect_err("kalan profilin zip'i yokken kaldirma reddedilmeli");
    let m = hata.to_string();
    assert!(m.contains("b.zip") && m.contains("onar"), "hata kalan profilin zip'ini ve cozumu soylemeli: {m}");
    assert_eq!(agac(&c.root), once, "hicbir dosya degismemeli");
    assert!(c.zip_yolu("a", 0).exists(), "a.zip silinmemeli");
}

// ── (e) guvensiz yollar → red, hicbir sey silinmez ─────────────────────────────────────────────

fn guvensiz_girdi_reddedilir(girdi: &str) {
    let c = cihaz_kur(Some((girdi, b"x")));
    let once = agac(&c.root);
    let hata = match c.kaldir(&["a"]) {
        Err(e) => e.to_string(),
        Ok(r) => panic!("{girdi:?} iceren paket REDDEDILMELIYDI, kaldirma basarili oldu: {r:?}"),
    };
    assert!(hata.contains("güvensiz") || hata.contains("GÜVENLİK"), "hata metni: {hata}");
    assert!(hata.contains("silinmedi"), "kullaniciya hicbir seyin silinmedigi soylenmeli: {hata}");
    assert_eq!(agac(&c.root), once, "{girdi:?}: hicbir dosya degismemeli");
    assert!(c.var(YALNIZ_A), "{girdi:?}: yalniz-A dosyasi bile silinmemeli (tum islem red)");
}

#[test]
fn ust_dizin_kacisi_reddedilir() {
    guvensiz_girdi_reddedilir("../x");
    guvensiz_girdi_reddedilir("ai_models/../runtime/x");
}

#[test]
fn ai_models_disi_kok_reddedilir() {
    guvensiz_girdi_reddedilir("runtime/x");
    guvensiz_girdi_reddedilir("installed_profiles.json");
}

#[test]
fn mutlak_ve_ters_egik_yollar_reddedilir() {
    guvensiz_girdi_reddedilir("/abs/x");
    guvensiz_girdi_reddedilir("ai_models\\..\\runtime\\x");
    guvensiz_girdi_reddedilir("C:/ai_models/x");
}

/// Windows "ai_hub." parcasini "ai_hub" diye cozumler; KEEP kiyasi cozumlemez → kalan profilin
/// dosyasi "ortak degil" sanilip silinebilirdi (sahip incelemesi 2026-09-06). Boyle parca → tum islem red.
#[test]
fn sonu_nokta_veya_bosluk_ile_biten_parca_reddedilir() {
    guvensiz_girdi_reddedilir("ai_models/ai_hub./x.onnx");
    guvensiz_girdi_reddedilir("ai_models/ai_hub/x.onnx ");
    guvensiz_girdi_reddedilir("ai_models/ai_hub/x.onnx.");
}

// ── (f) model_parts dosyalari da silinir ──────────────────────────────────────────────────────

#[test]
fn model_parts_parca_dosyalari_ve_zipi_de_kaldirilir() {
    let c = cihaz_kur(None);
    assert!(c.var(A_PARCA) && c.zip_yolu("a", 1).exists(), "test kurgusu");
    c.kaldir(&["a"]).unwrap();
    assert!(!c.var(A_PARCA), "a-2.zip'ten acilan dosya silinmeliydi");
    assert!(!c.var("ai_models/ai_hub/a/deep"), "parcanin bos dizini budanmaliydi");
    assert!(!c.zip_yolu("a", 1).exists(), "cache/a-2.zip silinmeliydi");
    assert!(c.var(ORTAK) && c.var(YALNIZ_B));
}

/// Kurulu olmayan bir profil istenirse: acik hata, dokunma.
#[test]
fn kurulu_olmayan_profil_istegi_reddedilir() {
    let c = cihaz_kur(None);
    let once = agac(&c.root);
    let hata = c.kaldir(&["research"]).expect_err("kurulu olmayan profil reddedilmeli");
    assert!(hata.to_string().contains("research"), "{hata}");
    assert_eq!(agac(&c.root), once);
}

// ── (h) bozuk onbellek zip'i → red, hicbir sey silinmez ───────────────────────────────────────

/// `ZipArchive::new` hatasi TUM silmelerden ONCE uretilmeli: 'bozuk' + 'onar' metni, agac ayni.
fn bozuk_zip_reddedilir(bozulan_profil: &str, kaldirilan: &str) {
    let c = cihaz_kur(None);
    fs::write(c.zip_yolu(bozulan_profil, 0), b"\x00\x01bu bir zip degil\xff\xfe").unwrap();
    let once = agac(&c.root);
    let hata = match c.kaldir(&[kaldirilan]) {
        Err(e) => e.to_string(),
        Ok(r) => panic!("{bozulan_profil}.zip bozukken kaldirma REDDEDILMELIYDI: {r:?}"),
    };
    assert!(
        hata.contains("bozuk") && hata.contains("onar") && hata.contains(&format!("{bozulan_profil}.zip")),
        "hata hangi paketin bozuk oldugunu ve cozumu (Onar) soylemeli: {hata}"
    );
    assert_eq!(agac(&c.root), once, "bozuk zip: hicbir dosya degismemeli (bozuk bayt dahil)");
    assert_eq!(install::read_installed_profiles(&c.root), vec!["a".to_string(), "b".to_string()]);
}

#[test]
fn kaldirilan_profilin_zipi_bozuksa_red_hicbir_sey_silinmez() {
    bozuk_zip_reddedilir("a", "a");
}

#[test]
fn kalan_profilin_zipi_bozuksa_ortak_kume_hesaplanamaz_red() {
    bozuk_zip_reddedilir("b", "a");
}

// ── (i) ilerleme olayi YOK ────────────────────────────────────────────────────────────────────

/// Inceleme 2026-09-06: `Progress::Extracting { "a kaldırılıyor" }` UI'da "Kuruluyor…/Installing…"
/// basligiyla ve EN'de Turkce artikla gorunuyordu. Kaldirma hicbir Progress uretmez.
#[test]
fn kaldirma_hicbir_progress_olayi_uretmez() {
    let c = cihaz_kur(None);
    let mut olaylar: Vec<flow::Progress> = Vec::new();
    let p = vec!["a".to_string()];
    flow::remove_profiles(&c.root, &c.manifest, &p, &mut |e| olaylar.push(e)).unwrap();
    assert!(
        olaylar.is_empty(),
        "kaldirma Progress yayinlamamali (UI bunu kurulum adimi sanir): {olaylar:?}"
    );
    assert!(!c.var(YALNIZ_A), "kaldirma yine de gerceklesmeli");
}

// ── (j) silme ortasinda dosya sistemi hatasi → eyleme donuk metin, kayit degismez ─────────────

/// Windows'ta FILE_SHARE_DELETE'siz acik bir tanitici `remove_file`i "başka bir işlem tarafından
/// kullanılıyor (os error 32)" ile reddeder — antivirus taramasi / acik uygulama kilidinin
/// BIREBIR taklidi. (Unix'te acik tanitici silmeyi engellemez; bu senaryo orada olculemez.
/// Salt-okunur bayragi da olcum icin yetersiz: guncel std, Windows'ta onu temizleyip siler.)
#[cfg(windows)]
#[test]
fn silme_hatasi_eyleme_donuk_metin_verir_ve_kayit_degismez() {
    use std::os::windows::fs::OpenOptionsExt;
    let c = cihaz_kur(None);
    let kilitli = c.root.join(YALNIZ_A);
    // FILE_SHARE_READ (1) yalniz: silme paylasimi YOK → remove_file os error 32.
    let tanitici = fs::OpenOptions::new().read(true).share_mode(1).open(&kilitli).unwrap();

    let sonuc = c.kaldir(&["a"]);
    drop(tanitici); // temizlik once: panic durumunda tempdir silinebilsin
    let hata = match sonuc {
        Err(e) => e.to_string(),
        Ok(r) => panic!("kilitli dosya varken kaldirma basarili olmamali: {r:?}"),
    };

    assert!(
        hata.contains("silinemedi") && hata.contains("onar") && hata.contains("kayd"),
        "hata: NE oldu (silinemedi) + NE yapilmali (Onar) + kaydin degismedigi: {hata}"
    );
    assert!(!hata.starts_with("dosya sistemi hatası"), "ham Io hatasi yukari cikmamali: {hata}");
    assert!(c.var(YALNIZ_A), "kilitli dosya yerinde");
    assert!(c.var(ORTAK) && c.var(YALNIZ_B));
    assert!(c.zip_yolu("a", 0).exists() && c.zip_yolu("a", 1).exists(), "kayit/zip adimina gecilmemeli");
    assert_eq!(
        install::read_installed_profiles(&c.root),
        vec!["a".to_string(), "b".to_string()],
        "kayit DEGISMEMELI — profil 'kurulu' kalir, Onar eksikleri tamamlar"
    );
    assert!(install::read_installed_packages(&c.root).models.contains_key("a"));
}

// ── (g) uygulama URL'si ───────────────────────────────────────────────────────────────────────

#[test]
fn uygulama_url_kurulu_profilleri_tasir_ve_onbellek_kirici_korunur() {
    let u = flow::uygulama_url(8000, &["home".to_string(), "vet".to_string()]);
    assert_eq!(u, "http://127.0.0.1:8000/?profiles=home,vet");
    let busted = flow::onbellek_kirici(&u, 42);
    assert!(busted.contains("profiles=home,vet"), "{busted}");
    assert!(busted.ends_with("&_=42"), "onbellek-kirici '&' ile eklenmeli (ikinci parametre): {busted}");
    let parsed = url_sorgu(&busted);
    assert_eq!(parsed.get("profiles").map(String::as_str), Some("home,vet"));
    assert_eq!(parsed.get("_").map(String::as_str), Some("42"));
}

#[test]
fn uygulama_url_bos_listede_profiles_parametresi_yok() {
    let u = flow::uygulama_url(8001, &[]);
    assert_eq!(u, "http://127.0.0.1:8001/");
    let busted = flow::onbellek_kirici(&u, 7);
    assert_eq!(busted, "http://127.0.0.1:8001/?_=7");
    assert!(!busted.contains("profiles"));
}

#[test]
fn uygulama_url_bozuk_profil_adini_eler() {
    // Kayit dosyasindan gelen sacma bir ad URL'yi kirmasin.
    let u = flow::uygulama_url(8000, &["home".to_string(), "ve t&x=1".to_string()]);
    assert_eq!(u, "http://127.0.0.1:8000/?profiles=home");
}

fn url_sorgu(u: &str) -> BTreeMap<String, String> {
    u.split_once('?')
        .map(|(_, q)| {
            q.split('&')
                .filter_map(|kv| kv.split_once('=').map(|(k, v)| (k.to_string(), v.to_string())))
                .collect()
        })
        .unwrap_or_default()
}
