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
    assert "state = (adj < duty) ? 1U : 3U;" in uni, "unipolar dal yalnız A darbesi üretmiyor"
    assert "state = 0U" not in uni, "unipolar dalda B durumu (0) üretiliyor — IN_B sürülür, tek-bacak değil"
    assert "state = 0U" in bip and "yarim + duty" in bip.replace("(", " ").replace(")", " "), "bipolar dal bozulmuş"
    assert uni.count("tpp - 1") + uni.count("g_tpp[i] - 1") >= 2, "unipolar duty tavanı tam-periyot−1 değil (iki klemp)"
    assert bip.count("/ 2U) - DDS_BIPOLAR_GAP_TICKS") >= 2, "bipolar yarım-periyot klempleri bozulmuş"
    assert "UNIPOLAR tek-bacak" in uni and "SYM-BIPOLAR" in bip, "STM_READY dizesi kipi yansıtmıyor"


def _unipolar_dalga(tpp: int, duty_t: int, faz_t: int) -> list[str]:
    """main.c unipolar dalının Python modeli: yalnız A=[0,duty), gerisi LOW."""
    out = []
    for t in range(tpp):
        adj = t - faz_t
        if adj < 0:
            adj += tpp
        out.append("A" if adj < duty_t else "-")
    return out


def test_unipolar_dalga_modeli_B_asla_HIGH_degil_ve_tam_periyot_doluluk():
    tpp = 500
    for duty in (1, 250, 499):
        d = _unipolar_dalga(tpp, duty, 0)
        assert "B" not in d and d.count("A") == duty, f"duty={duty}: {d.count('A')} A tick"
    # faz kaydırması sarmalı
    d = _unipolar_dalga(tpp, 100, 450)
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
    assert launch.exists() and "PEMF_UNIPOLAR.elf" in launch.read_text(encoding="utf-8")
    assert not (AYNA / "PEMF.ioc").exists() and not (AYNA / "PEMF Debug.launch").exists()


def test_KRITIK_unipolar_build_ciktisi_izlenmiyor():
    ch = subprocess.run(
        ["git", "ls-files", "--", "firmware/stm32_pemf_unipolar/Debug", "firmware/stm32_pemf_unipolar/Release"],
        cwd=KOK,
        capture_output=True,
        text=True,
    )
    assert not ch.stdout.strip(), f"unipolar Debug/Release çıktısı depoya sızmış:\n{ch.stdout}"
