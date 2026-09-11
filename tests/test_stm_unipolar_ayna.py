# Author: mertaygn, cglrgrkn
"""STM UNIPOLAR AYNA PROJESİ KAPISI (2026-09-08, sahip isteği: "her bobin 1 PWM'li ayrı kopya").

İki CubeIDE projesi AYNI firmware'i iki sürüş kipiyle derler:
  firmware/stm32_pemf/           PEMF_SURUS_UNIPOLAR 0 → simetrik bipolar (IN_A + IN_B)
  firmware/stm32_pemf_unipolar/  PEMF_SURUS_UNIPOLAR 1 → tek-bacak düz sürüş (yalnız IN_A)

2026-08-19 dersi: ikinci bir main.c kopyası bir kez SESSİZCE AYRIŞTI (masaüstü 2 ay geride kaldı).
Bu yüzden "kopya" burada BAYT-BAYT AYNA'dır: Core/ altında yalnız `Inc/pemf_surus.h` farklı olabilir;
kanonik değişince `python scripts/stm_unipolar_senkronla.py` koşturulur. Bu kapı ayrışmayı, kipin
gerçekten dalga üretimine bağlı olduğunu ve iki projenin CubeIDE'de yan yana import edilebildiğini
(farklı proje adı) kilitler.
"""

from __future__ import annotations

import filecmp
import re
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
FW = KOK / "firmware"
KANONIK = FW / "stm32_pemf"
AYNA = FW / "stm32_pemf_unipolar"
ISTISNA = Path("Inc") / "pemf_surus.h"

pytestmark = pytest.mark.skipif(not AYNA.exists(), reason="unipolar ayna projesi yok")


def _kaynak() -> str:
    return (KANONIK / "Core" / "Src" / "main.c").read_text(encoding="utf-8", errors="replace")


def _yorumsuz(metin: str) -> str:
    metin = re.sub(r"/\*.*?\*/", " ", metin, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", metin)


def _kip_dali(kaynak: str, unipolar: bool) -> str:
    """`#if PEMF_SURUS_UNIPOLAR … #else … #endif` bloklarının istenen dalını birleştir."""
    parcalar = []
    for m in re.finditer(r"#if PEMF_SURUS_UNIPOLAR\n(.*?)(?:#else\n(.*?))?#endif", kaynak, re.DOTALL):
        parcalar.append(m.group(1) if unipolar else (m.group(2) or ""))
    return "\n".join(parcalar)


def test_KRITIK_Core_agaci_pemf_surus_haric_BAYT_BAYT_AYNI():
    farkli = []
    for p in (KANONIK / "Core").rglob("*"):
        if not p.is_file():
            continue
        g = p.relative_to(KANONIK / "Core")
        if g == ISTISNA:
            continue
        h = AYNA / "Core" / g
        if not h.exists() or not filecmp.cmp(p, h, shallow=False):
            farkli.append(str(g))
    for p in (AYNA / "Core").rglob("*"):
        if p.is_file() and not (KANONIK / "Core" / p.relative_to(AYNA / "Core")).exists():
            farkli.append("FAZLA: " + str(p.relative_to(AYNA / "Core")))
    assert not farkli, (
        f"unipolar ayna kanonikten AYRIŞTI: {farkli} — elle düzenlemeyin; "
        "`python scripts/stm_unipolar_senkronla.py` koşturun (tek kaynak = stm32_pemf/Core)"
    )


def test_KRITIK_surus_kipi_iki_projede_FARKLI_ve_dogru():
    """⚠️ 2026-09-11: kip artık BOBİN BAŞINA (`PEMF_BOBIN_UNIPOLAR_MASKESI`).

    Sahip donanım bilgisi: bobin 1-5 TAM KÖPRÜ (bipolar olabilir), bobin 6-7 TEK YÖNLÜ
    sürücü (yalnız unipolar). Tek bir `PEMF_SURUS_UNIPOLAR` bayrağı bunu İFADE EDEMEZ.
    İki proje artık MASKEYLE ayrışır; ayrıntı: tests/test_stm_bobin_basina_kip.py
    """
    k = (KANONIK / "Core" / ISTISNA).read_text(encoding="utf-8")
    a = (AYNA / "Core" / ISTISNA).read_text(encoding="utf-8")
    assert re.search(r"^#define PEMF_SURUS_UNIPOLAR 0$", k, re.M), "kanonik proje bipolar (0) olmalı"
    assert re.search(r"^#define PEMF_SURUS_UNIPOLAR 1$", a, re.M), "unipolar proje 1 olmalı"

    mk = re.search(r"^#define PEMF_BOBIN_UNIPOLAR_MASKESI 0x([0-9A-Fa-f]+)U", k, re.M)
    ma = re.search(r"^#define PEMF_BOBIN_UNIPOLAR_MASKESI 0x([0-9A-Fa-f]+)U", a, re.M)
    assert mk and ma, "iki projede de kip MASKESİ tanımlı olmalı"
    assert int(mk.group(1), 16) == 0x60, (
        f"saha projesi maskesi 0x{mk.group(1)} != 0x60 — bobin 6-7 TEK YÖNLÜ sürücüde, "
        "bipolar sürülemez; 1-5 tam köprüde ve dB/dt için bipolar sürülür"
    )
    assert int(ma.group(1), 16) == 0x7F, "karşılaştırma projesi HEPSİ-unipolar (0x7F) olmalı"

    # Yalnız bu iki #define satırı farklı olabilir (başlık yorumu iki değeri de anlatır).
    def _define_siz(m: str) -> list[str]:
        return [
            s
            for s in m.splitlines()
            if not s.startswith("#define PEMF_SURUS_UNIPOLAR ")
            and not s.startswith("#define PEMF_BOBIN_UNIPOLAR_MASKESI ")
        ]

    assert _define_siz(k) == _define_siz(a), "pemf_surus.h iki projede yalnız kip #define'larıyla farklı olmalı"


def test_KRITIK_main_c_kipi_okur_ve_DALGA_gercekten_degisir():
    """Metin değil DAVRANIŞ: unipolar dalda B durumu (0) hiç üretilmez, tavan tam-periyot.

    ⚠️ 2026-09-11: dallanma `#if PEMF_SURUS_UNIPOLAR` DEĞİL, çalışma-zamanı
    `if (g_unipolar[i])` oldu (bobin başına kip). Dalların İÇERİĞİ aynı kaldı;
    bu test onu ölçmeye devam eder, yalnız dalları ayıklama yolu değişti.
    """
    src = _kaynak()
    assert '#include "pemf_surus.h"' in src, "main.c pemf_surus.h'ı dahil etmiyor → kip etkisiz"
    tum = _yorumsuz(src)

    # Çalışma-zamanı kip dalları: if (g_unipolar[i]) { UNI } else { BIP }
    m = re.search(
        r"if \(g_unipolar\[i\]\) \{(?P<uni>.*?)\n    \} else \{(?P<bip>.*?)\n    \}",
        tum,
        re.S,
    )
    assert m, "çalışma-zamanı kip dallanması (`if (g_unipolar[i])`) bulunamadı → maske ETKİSİZ"
    uni, bip = m.group("uni"), m.group("bip")

    assert "state = (adj < duty) ? 1U : 3U;" in uni, "unipolar dal tek-bacak darbe üretmiyor"
    assert "yarim" not in uni, "unipolar dalda yarım-periyot (ikinci bacak) penceresi var — tek-bacak değil"
    assert re.search(r"\(PEMF_BOBIN_TERS_MASKESI >> i\) & 1U", tum) and "state ^= 1U;" in tum, (
        "polarite maskesi ISR'de uygulanmıyor (A↔B çevirme yok) — bobin 1/2 ters sargı düzeltilmez"
    )
    assert "(state < 2U)" in tum, "maske boşluk/IDLE durumlarını da çeviriyor (yalnız 0/1 çevrilmeli)"
    hdr_k = (KANONIK / "Core" / ISTISNA).read_text(encoding="utf-8")
    hdr_a = (AYNA / "Core" / ISTISNA).read_text(encoding="utf-8")
    for h in (hdr_k, hdr_a):
        assert re.search(r"^#define PEMF_BOBIN_TERS_MASKESI 0x00U$", h, re.M), (
            "polarite maskesi 0x00 DEGIL. SAHIP KARARI 2026-09-10: maske KULLANILMAYACAK — ters "
            "sargi bobin UCLARI CEVRILEREK donanimda cozuldu, darbe DAIMA IN_A'dan cikar "
            "(PC8 PC9 PD10 PC6 PA8) ve IN_B pinleri (PD12 PE10 PD11 PC7 PA9) FIZIKSEL OLARAK "
            "BAGLI DEGIL. Mono suruste maske biti dalgayi degil DARBENIN CIKTIGI PINI degistirir "
            "→ bagli olmayan bir pine darbe basmak o bobini SESSIZCE oldurur (ACK'te duty gorunur, "
            "`running` true, arayuz 'Aktif', ALAN SIFIR). 2026-09-08'de 0x03 idi ve tam bu ariza "
            "riskini tasiyordu. Degistirmek yeni bir SAHIP KARARI + IN_B kablolamasi gerektirir."
        )
    assert "state = 0U" in bip and "yarim + duty" in bip.replace("(", " ").replace(")", " "), "bipolar dal bozulmuş"

    # ⚠️ 2026-09-11: klempler artık kip dallarının İÇİNDE değil, bobin başına TERNARY.
    # İki klemp de `g_unipolar[i]` okumalı ve iki tavanı da taşımalı; ayrışırlarsa bipolar
    # bobin yarım-periyottan uzun duty alır → A/B pencereleri çakışır → SHOOT-THROUGH.
    klempler = re.findall(r"int32_t\s+max_d(?:_now)?\s*=\s*([^;]+);", tum, re.S)
    assert len(klempler) == 2, f"beklenen 2 duty klempi, bulunan {len(klempler)}"
    for kl in klempler:
        assert "g_unipolar[i]" in kl, f"duty klempi kip dizisini okumuyor: {kl.strip()[:70]!r}"
        assert "- 1" in kl, "unipolar tavanı (tam-periyot−1) klempte yok"
        assert "DDS_BIPOLAR_GAP_TICKS" in kl, "bipolar tavanı (yarım−boşluk) klempte yok"

    # STM_READY dizesi kipi MASKEDEN türetmeli (elle yazılan etiket karma kipte yalan söyler).
    assert "PEMF_BOBIN_UNIPOLAR_MASKESI == 0x00U" in tum and '"KARMA"' in tum, (
        "STM_READY dizesi kip maskesinden türetilmiyor → banner karma yapılandırmada YANLIŞ"
    )
    assert "UNIPOLAR tek-bacak" in tum and "SYM-BIPOLAR" in tum, "kip etiketleri kayboldu"


MASKE = 0x00  # pemf_surus.h PEMF_BOBIN_TERS_MASKESI — sahip kararı 2026-09-10: maske KULLANILMIYOR


def _unipolar_dalga(tpp: int, duty_t: int, faz_t: int, bobin_idx: int = 1) -> list[str]:
    """main.c unipolar dalının Python modeli: seçili TEK bacak=[0,duty), gerisi LOW.
    bobin_idx = ISR'deki i (0 tabanlı); maske biti set ise darbe B'de, değilse A'da."""
    darbe = "B" if (MASKE >> bobin_idx) & 1 else "A"
    out = []
    for t in range(tpp):
        adj = t - faz_t
        if adj < 0:
            adj += tpp
        out.append(darbe if adj < duty_t else "-")
    return out


def _bipolar_dalga(tpp: int, duty_t: int, gap: int, bobin_idx: int) -> list[str]:
    """main.c bipolar dalının modeli + polarite maskesi: A=[0,duty), B=[yarım,yarım+duty); maskeli
    bobinde A↔B yer değiştirir (ayna). Boşluklar LOW."""
    yarim = tpp // 2
    ters = bool((MASKE >> bobin_idx) & 1)
    out = []
    for adj in range(tpp):
        if adj < duty_t:
            s = "A"
        elif yarim <= adj < yarim + duty_t:
            s = "B"
        else:
            s = "-"
        if ters and s in ("A", "B"):
            s = "B" if s == "A" else "A"
        out.append(s)
    return out


def test_KRITIK_maske_SIFIR_hicbir_bobin_AYNALANMAZ():
    """SAHİP KARARI 2026-09-10: maske 0x00 → beş bobinin HEPSİ aynı bacağı kullanır.

    Bipolarda hiçbiri aynalanmaz (hepsi A ile başlar), unipolarda hepsi IN_A'dan darbelenir.
    ⚠️ Bu, 2026-09-08'deki 0x03'ün TERSİ: o gün ters sargı YAZILIMDA düzeltilmişti, şimdi
    bobin UÇLARI donanımda çevrildiği için yazılım düzeltmesi KALKTI.
    """
    assert MASKE == 0x00, f"maske {MASKE:#04x}; sahip kararı 0x00 (donanımda çevrildi)"
    tpp, duty = 500, 100
    for idx in range(5):
        d = _bipolar_dalga(tpp, duty, 0, bobin_idx=idx)
        assert d[0] == "A" and d[250] == "B", f"bobin{idx + 1} bipolar dalgası aynalanmış: maske sıfır değil gibi"
        assert d.count("A") == duty and d.count("B") == duty
        assert all(x in ("A", "B", "-") for x in d) and d.count("-") == tpp - 2 * duty


def test_unipolar_dalga_modeli_tek_bacak_ve_tam_periyot_doluluk():
    """Maske 0x00 → BEŞ bobinin hepsi IN_A'dan darbelenir (PC8 PC9 PD10 PC6 PA8).

    ⚠️ Bir bobinin B'ye kayması, darbeyi KABLOSU OLMAYAN pine taşır (IN_B'ler bağlı değil) →
    o bobin sessizce sürülmez. Bu yüzden burada "B hiç yok" iddiası beş bobin için de pinli.
    """
    tpp = 500
    for duty in (1, 250, 499):
        for idx in range(5):
            d = _unipolar_dalga(tpp, duty, 0, bobin_idx=idx)
            assert "B" not in d and d.count("A") == duty, (
                f"bobin{idx + 1} duty={duty}: darbe IN_A'da DEĞİL ({d.count('A')} A tick) — "
                "maske biti set edilmiş olabilir; o pinde KABLO YOK"
            )
    # faz kaydırması sarmalı
    d = _unipolar_dalga(tpp, 100, 450, bobin_idx=2)
    assert d[450] == "A" and d[49] == "A" and d[50] == "-"


def test_KARSIT_KANIT_model_maskeyi_GERCEKTEN_uyguluyor():
    """Öz-test: yukarıdaki iddialar maske sıfır OLDUĞU İÇİN mi geçiyor, yoksa model maskeyi hiç
    okumuyor mu? Modele elle 0x03 verilirse bobin 1-2 B'ye kaymalı — kaymıyorsa kapı SAHTE-YEŞİL.
    """
    global MASKE
    _yedek = MASKE
    try:
        MASKE = 0x03
        d1 = _unipolar_dalga(500, 100, 0, bobin_idx=0)
        d3 = _unipolar_dalga(500, 100, 0, bobin_idx=2)
        assert "A" not in d1 and d1.count("B") == 100, "model maske bitini OKUMUYOR → kapı sahte-yeşil"
        assert "B" not in d3, "maskesiz bobin de kaymış → model bit indeksini yanlış uyguluyor"
        b1 = _bipolar_dalga(500, 100, 0, bobin_idx=0)
        assert b1[0] == "B", "bipolar model maskeyi uygulamıyor"
    finally:
        MASKE = _yedek


def test_KRITIK_iki_proje_CubeIDE_de_yan_yana_import_edilebilir():
    """Aynı proje adı → Eclipse ikinciyi import ETMEZ. Ad ve tüm yol referansları ayrık olmalı."""
    ad = re.search(r"<name>([^<]+)</name>", (AYNA / ".project").read_text(encoding="utf-8")).group(1)
    assert ad == "PEMF_UNIPOLAR", f"unipolar proje adı {ad!r}"
    cproj = (AYNA / ".cproject").read_text(encoding="utf-8")
    assert "workspace_loc:/PEMF}" not in cproj and 'name="PEMF"/>' not in cproj, ".cproject hâlâ PEMF'i işaret ediyor"
    ioc = AYNA / "PEMF_UNIPOLAR.ioc"
    assert ioc.exists() and "ProjectManager.ProjectName=PEMF_UNIPOLAR" in ioc.read_text(encoding="utf-8")
    launch = AYNA / "PEMF_UNIPOLAR Debug.launch"
    assert launch.exists()
    lt = launch.read_text(encoding="utf-8")
    assert "PEMF_UNIPOLAR.elf" in lt
    # SAHA 2026-09-08 (LattePanda): launch bipolar'dan kopyalanmıştı, ST yükleme listesindeki
    # `fProjectName` "PEMF" kalmıştı → Debug önce `PEMF\Debug\PEMF_UNIPOLAR.elf: No such file`,
    # PEMF projesi silinince `projectPath is null` verdi. Proje adı geçen HER alan PEMF_UNIPOLAR olmalı.
    assert 'PROJECT_ATTR" value="PEMF_UNIPOLAR"' in lt, "launch PROJECT_ATTR PEMF_UNIPOLAR değil"
    assert "&quot;fProjectName&quot;:&quot;PEMF_UNIPOLAR&quot;" in lt, (
        "ST loadList fProjectName PEMF_UNIPOLAR değil → Debug 'projectPath is null' / elf bulunamaz"
    )
    assert "&quot;fProjectName&quot;:&quot;PEMF&quot;" not in lt, "loadList hâlâ bipolar PEMF projesini gösteriyor"
    assert '<listEntry value="/PEMF_UNIPOLAR"/>' in lt and '<listEntry value="/PEMF"/>' not in lt
    assert re.search(r"[\\/]PEMF[\\/]Debug[\\/]", lt) is None, "launch içinde PEMF\\Debug yolu kalmış (st-link log)"
    assert not (AYNA / "PEMF.ioc").exists() and not (AYNA / "PEMF Debug.launch").exists()


def test_KRITIK_unipolar_build_ciktisi_izlenmiyor():
    ch = subprocess.run(
        ["git", "ls-files", "--", "firmware/stm32_pemf_unipolar/Debug", "firmware/stm32_pemf_unipolar/Release"],
        cwd=KOK,
        capture_output=True,
        text=True,
    )
    assert not ch.stdout.strip(), f"unipolar Debug/Release çıktısı depoya sızmış:\n{ch.stdout}"
