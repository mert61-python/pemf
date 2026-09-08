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
    # 2026-09-08 (sahip): bobin başına TEK bacak; hangisi olduğu PEMF_UNIPOLAR_B_BACAK_MASKESI ile
    # seçilir (bobin 1 → IN_B/PD12, diğerleri IN_A). Darbe durumu 0 (B) ya da 1 (A), boşluk 3;
    # aynı bobinde iki bacak birden ASLA (bipolar 'yarim' penceresi unipolar dalda yok).
    assert "state = (adj < duty) ? darbe_durumu : 3U;" in uni, "unipolar dal tek-bacak darbe üretmiyor"
    assert "PEMF_UNIPOLAR_B_BACAK_MASKESI >> i" in uni and "? 0U : 1U" in uni, "bacak seçimi maskeden okunmuyor"
    assert "yarim" not in uni, "unipolar dalda yarım-periyot (ikinci bacak) penceresi var — tek-bacak değil"
    hdr_k = (KANONIK / "Core" / ISTISNA).read_text(encoding="utf-8")
    hdr_a = (AYNA / "Core" / ISTISNA).read_text(encoding="utf-8")
    for h in (hdr_k, hdr_a):
        assert re.search(r"^#define PEMF_UNIPOLAR_B_BACAK_MASKESI 0x03U$", h, re.M), (
            "bacak maskesi 0x03 değil (2026-09-08: bobin 1 sahip kararıyla IN_B/PD12, bobin 2 tezgâh "
            "ölçümüyle IN_B/PE10 — z işaretleri 1:+1,4 2:−4,9 4:+0,5 5:+3,9; değiştirmek bilinçli "
            "tezgâh kararıdır — bu satırı ve README'yi birlikte güncelle)"
        )
    assert "state = 0U" in bip and "yarim + duty" in bip.replace("(", " ").replace(")", " "), "bipolar dal bozulmuş"
    assert uni.count("tpp - 1") + uni.count("g_tpp[i] - 1") >= 2, "unipolar duty tavanı tam-periyot−1 değil (iki klemp)"
    assert bip.count("/ 2U) - DDS_BIPOLAR_GAP_TICKS") >= 2, "bipolar yarım-periyot klempleri bozulmuş"
    assert "UNIPOLAR tek-bacak" in uni and "SYM-BIPOLAR" in bip, "STM_READY dizesi kipi yansıtmıyor"


MASKE = 0x03  # pemf_surus.h PEMF_UNIPOLAR_B_BACAK_MASKESI (bobin 1 ve 2 → IN_B; tezgâh 2026-09-08)


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
