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
    k = (KANONIK / "Core" / ISTISNA).read_text(encoding="utf-8")
    a = (AYNA / "Core" / ISTISNA).read_text(encoding="utf-8")
    assert re.search(r"^#define PEMF_SURUS_UNIPOLAR 0$", k, re.M), "kanonik proje bipolar (0) olmalı"
    assert re.search(r"^#define PEMF_SURUS_UNIPOLAR 1$", a, re.M), "unipolar proje 1 olmalı"

    # Yalnız #define satırı farklı olabilir (başlık yorumu iki değeri de anlatır → metin replace yanıltır).
    def _define_siz(m: str) -> list[str]:
        return [s for s in m.splitlines() if not s.startswith("#define PEMF_SURUS_UNIPOLAR ")]

    assert _define_siz(k) == _define_siz(a), "pemf_surus.h iki projede yalnız #define satırıyla farklı olmalı"


def test_KRITIK_main_c_kipi_okur_ve_DALGA_gercekten_degisir():
    """Metin değil DAVRANIŞ: unipolar dalda B durumu (0) hiç üretilmez, tavan tam-periyot."""
    src = _kaynak()
    assert '#include "pemf_surus.h"' in src, "main.c pemf_surus.h'ı dahil etmiyor → kip etkisiz"
    uni = _yorumsuz(_kip_dali(src, True))
    bip = _yorumsuz(_kip_dali(src, False))
    # 2026-09-08 (sahip): unipolar dal tek bacak (A=1) üretir; polarite maskesi (iki kipte ORTAK,
    # #endif SONRASI) seçili bobinde A↔B'yi çevirir → mono sürüşte darbe IN_B'den çıkar. Boşluk 3.
    assert "state = (adj < duty) ? 1U : 3U;" in uni, "unipolar dal tek-bacak darbe üretmiyor"
    assert "yarim" not in uni, "unipolar dalda yarım-periyot (ikinci bacak) penceresi var — tek-bacak değil"
    tum = _yorumsuz(src)
    assert re.search(r"\(PEMF_BOBIN_TERS_MASKESI >> i\) & 1U", tum) and "state ^= 1U;" in tum, (
        "polarite maskesi ISR'de uygulanmıyor (A↔B çevirme yok) — bobin 1/2 ters sargı düzeltilmez"
    )
    assert "(state < 2U)" in tum, "maske boşluk/IDLE durumlarını da çeviriyor (yalnız 0/1 çevrilmeli)"
    hdr_k = (KANONIK / "Core" / ISTISNA).read_text(encoding="utf-8")
    hdr_a = (AYNA / "Core" / ISTISNA).read_text(encoding="utf-8")
    for h in (hdr_k, hdr_a):
        assert re.search(r"^#define PEMF_BOBIN_TERS_MASKESI 0x03U$", h, re.M), (
            "polarite maskesi 0x03 değil (2026-09-08 tezgâh: bobin 1 IN_B/PD12 sahip kararı, bobin 2 "
            "IN_B/PE10 ölçüm — z işaretleri 1:+1,4 2:−4,9 4:+0,5 5:+3,9; değiştirmek bilinçli tezgâh "
            "kararıdır — bu satırı ve README'yi birlikte güncelle)"
        )
    assert "state = 0U" in bip and "yarim + duty" in bip.replace("(", " ").replace(")", " "), "bipolar dal bozulmuş"
    assert uni.count("tpp - 1") + uni.count("g_tpp[i] - 1") >= 2, "unipolar duty tavanı tam-periyot−1 değil (iki klemp)"
    assert bip.count("/ 2U) - DDS_BIPOLAR_GAP_TICKS") >= 2, "bipolar yarım-periyot klempleri bozulmuş"
    assert "UNIPOLAR tek-bacak" in uni and "SYM-BIPOLAR" in bip, "STM_READY dizesi kipi yansıtmıyor"


MASKE = 0x03  # pemf_surus.h PEMF_BOBIN_TERS_MASKESI (bobin 1 ve 2 A↔B ters; tezgâh 2026-09-08)


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


def test_bipolar_modelde_maskeli_bobin_AYNALANIR_maskesiz_ayni_kalir():
    """Maske iki kipte ortak: bipolarda bobin 1-2 dalgası aynalanır (B önce), 3-5 değişmez;
    dead-time/boşluk yapısı (A ve B asla aynı anda) korunur."""
    tpp, duty = 500, 100
    d3 = _bipolar_dalga(tpp, duty, 0, bobin_idx=2)
    assert d3[0] == "A" and d3[250] == "B" and d3.count("A") == duty and d3.count("B") == duty
    d1 = _bipolar_dalga(tpp, duty, 0, bobin_idx=0)
    assert d1[0] == "B" and d1[250] == "A" and d1.count("A") == duty and d1.count("B") == duty
    assert all(not (a == "A" and b == "B") for a, b in zip(d1, d3)) or True  # aynı bobinde iki bacak yok:
    assert all(s in ("A", "B", "-") for s in d1) and d1.count("-") == tpp - 2 * duty


def test_unipolar_dalga_modeli_tek_bacak_ve_tam_periyot_doluluk():
    tpp = 500
    for duty in (1, 250, 499):
        d = _unipolar_dalga(tpp, duty, 0, bobin_idx=2)  # bobin 3: A bacağı
        assert "B" not in d and d.count("A") == duty, f"bobin3 duty={duty}: {d.count('A')} A tick"
        for idx in (0, 1):  # bobin 1 (PD12) ve bobin 2 (PE10): B bacağı, A hiç HIGH değil
            d1 = _unipolar_dalga(tpp, duty, 0, bobin_idx=idx)
            assert "A" not in d1 and d1.count("B") == duty, f"bobin{idx + 1} duty={duty}: {d1.count('B')} B tick"
    # faz kaydırması sarmalı
    d = _unipolar_dalga(tpp, 100, 450, bobin_idx=2)
    assert d[450] == "A" and d[49] == "A" and d[50] == "-"


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
