# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KP-3 B1 / B4 (istem 38 + 41 C · Y242) + KP-4 A1 (istem 42 · Y257 c): başlatıcı uygulama kapsam sınıfları — SAYAN kapı.

`launcher/app/kapsam_siniflari.json`: main.rs + kabuk.rs'in HER üst düzey işlevi tam bir sınıfta — T (test edilebilir) · Y (yeniden
düzenleme gerekir) · S (sınırda: pencere / Tauri çalışma zamanı / gerçek platform API'si — test edilemez) · K (kapsanıyor). Kural (Y242):
test yazılabilen satıra S YASAK; her S "neden" + "neden T / Y değil" taşır; S listesi SAYILIR (yeni S sessizce eklenemez).

KP-4 A1 (Y257 c, sahip 08.11): `#[coverage(off)]` rustc 1.98.1'de kararlı değil (E0658) → S işlevleri main.rs'ten DEĞİŞTİRİLMEDEN
`launcher/app/src/kabuk.rs`'e taşındı; main.rs onu `include!` ile AYNI modüle katar (görünürlük / yol / `generate_handler!` aynı) ve
CI'ın kapsam adımı (`tests.yml`, cargo llvm-cov `--ignore-filename-regex`) YALNIZ bu dosyayı ölçümden dışlar. Bu kapı dışlamanın
dürüst kalmasını kilitler: S işlevleri YALNIZ kabuk.rs'te, kabuk.rs'te S olmayan işlev YOK, S sayısı SABİT, güvenlik / güncelleme yolu
S OLAMAZ, kabuk.rs'te test / alt modül / iç içe `include!` YOK, dışlama deseni başka hiçbir kaynak dosyayı yakalamaz.
"""

import json
import re
from pathlib import Path

_KOK = Path(__file__).resolve().parent.parent
_MAIN = _KOK / "launcher" / "app" / "src" / "main.rs"
_KABUK = _KOK / "launcher" / "app" / "src" / "kabuk.rs"
_SINIF = _KOK / "launcher" / "app" / "kapsam_siniflari.json"
_CI = _KOK / ".github" / "workflows" / "tests.yml"
# KP-3 B4 ölçümü (d45d9cf2): 44 S işlevi. Değişiklik BİLİNÇLİ olmalı — sayı burada ve JSON'da birlikte değişir.
# KP-5 B2 (sahip kararı 2a, 11-11): A2c'nin 8 ince kök / Tauri kabuğu (`*_blocking` ×7 + `guncelleme_onayini_kaydet`) S → 52.
# KP-6 D2 (madde 6): `oturum_rotasyon_senkronu_baslat` ince kök / aralık kabuğu S (gövdesi `_ile` K) → 53.
# KP-6 D3: `prefetch_runtime_update` Tauri komut kabuğu S (gövdesi `prefetch_runtime_update_ile` K; güvenlik listesinde GÖVDE) → 54.
# KP-6 D4: `install_and_launch` / `start_installed` / `repair` / `remove_profiles` Tauri komut kabukları S (gövdeleri `_ile` K) → 58.
# KP-6 D5: `uninstall` Tauri komut kabuğu S (gövdesi `uninstall_ile` K) → 59.
# KP-6 D6: `apply_runtime_update` Tauri komut kabuğu S (gövdesi `apply_runtime_update_ile` K; güvenlik listesinde GÖVDE) → 60.
# KP-6 D7: `apply_self_update` Tauri komut kabuğu S (gövdesi `apply_self_update_ile` K; güvenlik listesinde GÖVDE) → 61.
BEKLENEN_S = 61
_FN = re.compile(r"^(?:pub(?:\([^)]*\))? )?(?:async )?fn (\w+)")


def _satirlar(yol: Path) -> list[str]:
    return yol.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")


def _ust_duzey(yol: Path) -> list[str]:
    satirlar = _satirlar(yol)
    son = next((i for i, s in enumerate(satirlar) if s.startswith("#[cfg(test)]")), len(satirlar))
    return [m.group(1) for s in satirlar[:son] if (m := _FN.match(s))]


def _veri() -> dict:
    return json.loads(_SINIF.read_text(encoding="utf-8"))


def _kod(yol: Path) -> str:
    """Satır yorumları soyulmuş kaynak (`//` ile başlayan satırlar ve satır sonu yorumları) — yorumdaki söz sayılmaz."""
    return "\n".join(s.split("//", 1)[0] if not s.lstrip().startswith("//") else "" for s in _satirlar(yol))


def test_KRITIK_main_rs_HER_ust_duzey_islev_TAM_BIR_sinifta():
    main, kabuk = _ust_duzey(_MAIN), _ust_duzey(_KABUK)
    islevler = main + kabuk
    assert len(islevler) >= 90, f"VAKUM: main.rs + kabuk.rs'te yalnız {len(islevler)} üst düzey işlev bulundu"
    assert len(islevler) == len(set(islevler)), (
        "aynı adlı iki üst düzey işlev (cfg kolları ya da iki dosyada birden?) — ayrıştırıcı / sınıf belirsiz"
    )
    sinif = _veri()["islevler"]
    eksik = sorted(set(islevler) - set(sinif))
    fazla = sorted(set(sinif) - set(islevler))
    assert not eksik, f"main.rs / kabuk.rs'e SINIFSIZ işlev eklendi (T / Y / S / K seçin, S ise gerekçe): {eksik}"
    assert not fazla, f"sınıf listesinde main.rs / kabuk.rs'te OLMAYAN işlev (silindi / adı değişti): {fazla}"
    assert {v["sinif"] for v in sinif.values()} <= {"T", "Y", "S", "K"}


def test_KRITIK_S_ve_Y_GEREKCELI_S_sayisi_SAYILIR():
    v = _veri()
    s = {a: x for a, x in v["islevler"].items() if x["sinif"] == "S"}
    assert len(s) == v["s_sayisi"] == BEKLENEN_S, (
        f"S sayısı değişti: JSON {len(s)} / s_sayisi {v['s_sayisi']} / kapı {BEKLENEN_S} — yeni S BİLİNÇLİ eklenir (Y242)"
    )
    gerekcesiz = [
        a
        for a, x in s.items()
        if len(x.get("neden", "").strip()) < 15 or len(x.get("neden_T_Y_degil", "").strip()) < 15
    ]
    assert not gerekcesiz, f"gerekçesiz S: {gerekcesiz}"
    y_gerekcesiz = [
        a for a, x in v["islevler"].items() if x["sinif"] in ("Y", "T") and len(x.get("neden", "").strip()) < 10
    ]
    assert not y_gerekcesiz, f"gerekçesiz Y / T: {y_gerekcesiz}"


def test_S_listesi_GUVENLIK_yollarini_ICERMEZ():
    """Kapanış / ACİL DURDUR / güncelleme güvenlik yolları S (test edilemez) diye kapatılamaz — Y (davranış koruyan ayrım, sahip onayıyla)."""
    sinif = _veri()["islevler"]
    for ad in (
        "stop_backend_for_teardown",
        "stop_tracked_backend",
        "yakma_bitene_kadar_bekle",
        "firmware_uyumsuz_geri_al",
        "apply_runtime_update_ile",  # KP-6 D6: güncelleme kararının GÖVDESİ (komut ince S kabuğu)
        "apply_self_update_ile",  # KP-6 D7: güncelleme kararının GÖVDESİ (komut ince S kabuğu)
        "prefetch_runtime_update_ile",  # KP-6 D3: güncelleme kararının GÖVDESİ (komut ince S kabuğu)
        # KP-5 B2: güncelleme kararının GÖVDELERİ (ince kabukları S — yalnız gerçek kök / saat bağlar, karar içermez)
        "guncelleme_ozeti_ile",
        "onay_kaydet_ile",
        "check_runtime_update_ile",
        "aktif_seans_kapisi_portla",
    ):
        assert sinif[ad]["sinif"] != "S", f"{ad} güvenlik / güncelleme yolu — S olamaz"


def test_KRITIK_KP4_A1_S_YALNIZ_kabuk_rs_te_ve_kabukta_S_DISI_islev_YOK():
    """Y257 c: kapsamdan dışlanan dosyada YALNIZ S kabuğu durur — test edilebilen işlev oraya saklanamaz, S main.rs'te kalamaz."""
    sinif = _veri()["islevler"]
    s = {a for a, x in sinif.items() if x["sinif"] == "S"}
    kabuk = _ust_duzey(_KABUK)
    assert kabuk, "VAKUM: kabuk.rs'te üst düzey işlev bulunamadı"
    assert not (set(kabuk) - s), f"kabuk.rs'te S OLMAYAN işlev (ölçümden kaçırılıyor): {sorted(set(kabuk) - s)}"
    assert not (s - set(kabuk)), f"S işlevi kabuk.rs DIŞINDA (main.rs'e geri döndü?): {sorted(s - set(kabuk))}"
    assert not (set(_ust_duzey(_MAIN)) & s), "main.rs'te S işlevi var"


def test_KRITIK_KP4_A1_kabuk_AYNI_modulde_TEK_include_test_ve_alt_modul_YOK():
    main_kod = _kod(_MAIN)
    test_bas = main_kod.index("#[cfg(test)]")
    uretim = main_kod[:test_bas]
    assert len(re.findall(r'(?m)^include!\("kabuk\.rs"\);\s*$', uretim)) == 1, (
        "main.rs kabuk.rs'i TEK kez, kök düzeyde katmalı"
    )
    assert main_kod.count('include!("kabuk.rs")') == 1, "kabuk.rs testlerde / ikinci kez katılıyor"
    assert not re.search(r"(?m)^\s*(pub(\([^)]*\))?\s+)?mod\s+kabuk\b", main_kod), (
        "kabuk ayrı modül yapılmış (görünürlük değişir)"
    )
    kabuk_kod = _kod(_KABUK)
    for yasak, neden in (
        ("#[cfg(test)]", "dışlanan dosyada test modülü (ölçümden kaçar)"),
        ("#[test]", "dışlanan dosyada test"),
        ("include!(", "dışlanan dosyadan iç içe katma"),
    ):
        assert yasak not in kabuk_kod, f"kabuk.rs: {neden}"
    assert not re.search(r"(?m)^\s*(pub(\([^)]*\))?\s+)?mod\s+\w+", kabuk_kod), "kabuk.rs'te alt modül"


def _ci_desen() -> str:
    satir = [s for s in _satirlar(_CI) if "cargo llvm-cov" in s and "--ignore-filename-regex" in s]
    assert len(satir) == 1, f"tests.yml'de TEK cargo llvm-cov kapsam adımı bekleniyor: {len(satir)}"
    m = re.search(r'--ignore-filename-regex "([^"]+)"', satir[0])
    assert m, satir[0]
    return m.group(1)


def test_KRITIK_KP4_A1_CI_kapsam_dislamasi_YALNIZ_kabuk_rs_ve_entegrasyon_testleri():
    """CI dışlama deseni kabuk.rs'i ve `tests/` entegrasyon testlerini yakalar; başka HİÇBİR kaynak dosyayı (main.rs, çekirdek) yakalamaz."""
    desen = re.compile(_ci_desen())
    kaynaklar = sorted((_KOK / "launcher").glob("*/src/**/*.rs"))
    assert len(kaynaklar) >= 15, f"VAKUM: {len(kaynaklar)} kaynak dosya"
    for yol in kaynaklar:
        for bicim in (str(yol), yol.as_posix(), "D:\\a\\pemf\\pemf\\" + str(yol.relative_to(_KOK)).replace("/", "\\")):
            yakalandi = bool(desen.search(bicim))
            assert yakalandi == (yol == _KABUK), (
                f"dışlama deseni {'yakalıyor' if yakalandi else 'yakalamıyor'}: {bicim}"
            )
    for test_yolu in ("D:\\a\\pemf\\pemf\\launcher\\core\\tests\\real_artifacts.rs", "/a/launcher/core/tests/x.rs"):
        assert desen.search(test_yolu), f"entegrasyon testi dışlanmıyor: {test_yolu}"
