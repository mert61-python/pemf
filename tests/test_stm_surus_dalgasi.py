# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""STM SÜRÜŞ DALGASI + POLARİTE MASKESİ — tek proje kapısı.

===============================================================================
⚠️ BU DOSYA `test_stm_unipolar_ayna.py`NİN YERİNİ ALDI (2026-09-11)
===============================================================================
Eski dosya İKİ CubeIDE projesini (`stm32_pemf` = bipolar, `stm32_pemf_unipolar` = unipolar)
bayt-bayt ayna olarak kilitliyordu. O kurgunun sebebi, sürüş kipinin derleme-zamanı TEK
bir bayrakla (`PEMF_SURUS_UNIPOLAR`) seçilmesiydi.

Sahibin donanımı o kurguyu geçersiz kıldı:
    bobin 1-5 : TAM KÖPRÜ sürücü  → bipolar sürülebilir
    bobin 6-7 : TEK YÖNLÜ sürücü  → YALNIZ unipolar (sağ/sol duvar)
"5 bipolar + 2 unipolar" tek bayrakla İFADE EDİLEMEZ. Kip bobin başına maskeye taşındı
(`PEMF_BOBIN_UNIPOLAR_MASKESI`) → ikinci proje, ayna kapısı ve senkron betiği KALDIRILDI.

Bu dosya eski kapının **hâlâ geçerli** iddialarını korur:
  · polarite maskesi (`PEMF_BOBIN_TERS_MASKESI`) 0x00 ve ISR'de doğru uygulanıyor
  · iki kipin dalga modeli + modelin maskeyi GERÇEKTEN okuduğunun karşıt-kanıtı
  · derleme çıktısı depoya sızmıyor
Kip seçiminin kendi kapısı ayrıdır: `tests/test_stm_bobin_basina_kip.py`.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
PROJE = KOK / "firmware" / "stm32_pemf"
MAIN = PROJE / "Core" / "Src" / "main.c"
SURUS = PROJE / "Core" / "Inc" / "pemf_surus.h"

pytestmark = pytest.mark.skipif(not MAIN.exists(), reason="firmware kaynagi yok")

#: `pemf_surus.h` PEMF_BOBIN_TERS_MASKESI — sahip kararı 2026-09-10: KULLANILMIYOR.
MASKE = 0x00


def _yorumsuz(metin: str) -> str:
    metin = re.sub(r"/\*.*?\*/", " ", metin, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", metin)


def _kaynak() -> str:
    return MAIN.read_text(encoding="utf-8", errors="replace")


# ============================================================================
# 1. TEK PROJE — ayna gerçekten kalktı mı
# ============================================================================


def test_KRITIK_AYNA_projesi_ve_senkron_betigi_KALKTI():
    """⚠️ Ayna geri gelirse iki kaynak yeniden ayrışabilir (2026-08-19'da bir kez oldu).

    Kip artık bobin başına maskeyle seçildiği için ikinci projenin sebebi YOK.
    """
    assert not (KOK / "firmware" / "stm32_pemf_unipolar").exists(), (
        "stm32_pemf_unipolar GERI GELMIS -> tek kaynak bozuldu; kip artik maskeyle secilir"
    )
    assert not (KOK / "scripts" / "stm_unipolar_senkronla.py").exists(), "ayna senkron betigi geri gelmis"
    firmalar = sorted(p.name for p in (KOK / "firmware").iterdir() if p.is_dir())
    assert firmalar == ["esp8266_pemf_coil", "esps3_pemf_coil", "stm32_pemf"], (
        f"firmware/ icerigi {firmalar} — beklenen: TEK stm klasoru + iki ESP kodu ayri"
    )


def test_KRITIK_OLU_bayrak_PEMF_SURUS_UNIPOLAR_kalmadi():
    """Ölü bir sabit "kip buradan seçiliyor" yanılgısı üretir.

    MUTASYON: `#define PEMF_SURUS_UNIPOLAR 0` satırını geri ekle → KIRMIZI.
    """
    hdr = SURUS.read_text(encoding="utf-8", errors="replace")
    assert not re.search(r"^#define\s+PEMF_SURUS_UNIPOLAR\s", hdr, re.M), (
        "olu bayrak geri gelmis -> kip maskeden mi bayraktan mi belirsizlesir"
    )
    tum = _yorumsuz(_kaynak())
    assert "#if PEMF_SURUS_UNIPOLAR" not in tum, "surus yolunda derleme-zamani dal geri gelmis"


# ============================================================================
# 2. POLARİTE MASKESİ — sahip kararı 0x00
# ============================================================================


def test_KRITIK_polarite_maskesi_SIFIR_ve_ISRde_dogru_uygulaniyor():
    hdr = SURUS.read_text(encoding="utf-8", errors="replace")
    assert re.search(r"^#define PEMF_BOBIN_TERS_MASKESI 0x00U$", hdr, re.M), (
        "polarite maskesi 0x00 DEGIL. SAHIP KARARI 2026-09-10: ters sargi bobin UCLARI "
        "CEVRILEREK DONANIMDA cozuldu, yazilimda cevirmeye GEREK YOK. "
        "⚠️ Maske TEK-BACAK bobinlerde (6-7) TEHLIKELI: mono suruste bit, dalgayi degil "
        "DARBENIN CIKTIGI PINI degistirir; o bobinlerde IN_B kablosu YOKTUR -> bobin "
        "SESSIZCE olur (ACK'te duty gorunur, `running` true, arayuz 'Aktif', ALAN SIFIR). "
        "2026-09-08'de 0x03 idi ve tam bu riski tasiyordu. Degistirmek SAHIP KARARI ister."
    )
    tum = _yorumsuz(_kaynak())
    assert re.search(r"\(PEMF_BOBIN_TERS_MASKESI >> i\) & 1U", tum) and "state ^= 1U;" in tum, (
        "polarite maskesi ISR'de uygulanmiyor (A<->B cevirme yok)"
    )
    assert "(state < 2U)" in tum, "maske bosluk/IDLE durumlarini da ceviriyor (yalniz 0/1 cevrilmeli)"


# ============================================================================
# 3. DALGA MODELİ + KARŞIT KANIT
# ============================================================================


def _unipolar_dalga(tpp: int, duty_t: int, faz_t: int, bobin_idx: int = 1) -> list[str]:
    """Tek-bacak dalga modeli: seçili bacak=[0,duty), gerisi LOW."""
    darbe = "B" if (MASKE >> bobin_idx) & 1 else "A"
    out = []
    for t in range(tpp):
        adj = t - faz_t
        if adj < 0:
            adj += tpp
        out.append(darbe if adj < duty_t else "-")
    return out


def _bipolar_dalga(tpp: int, duty_t: int, bobin_idx: int) -> list[str]:
    """Bipolar model: A=[0,duty), B=[yarım,yarım+duty); maskeli bobinde A↔B yer değiştirir."""
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
    """Maske 0x00 → hiçbir bobin aynalanmaz; hepsi aynı bacakla başlar."""
    assert MASKE == 0x00, f"maske {MASKE:#04x}; sahip karari 0x00 (donanimda cevrildi)"
    tpp, duty = 500, 100
    for idx in range(7):
        d = _bipolar_dalga(tpp, duty, bobin_idx=idx)
        assert d[0] == "A" and d[250] == "B", f"bobin{idx + 1} bipolar dalgasi aynalanmis"
        assert d.count("A") == duty and d.count("B") == duty
        assert d.count("-") == tpp - 2 * duty


def test_unipolar_dalga_TEK_BACAK_ve_faz_sarmali():
    """Tek-bacak kipte B bacağı HİÇ sürülmez (bobin 6-7'de o pinin kablosu YOK)."""
    tpp = 500
    for duty in (1, 250, 499):
        for idx in range(7):
            d = _unipolar_dalga(tpp, duty, 0, bobin_idx=idx)
            assert "B" not in d and d.count("A") == duty, (
                f"bobin{idx + 1} duty={duty}: darbe IN_A'da DEGIL ({d.count('A')} A tick)"
            )
    d = _unipolar_dalga(tpp, 100, 450, bobin_idx=2)
    assert d[450] == "A" and d[49] == "A" and d[50] == "-", "faz kaydirmasi sarmiyor"


def test_KARSIT_KANIT_model_maskeyi_GERCEKTEN_uyguluyor():
    """⚠️ Öz-test: yukarıdakiler maske sıfır OLDUĞU İÇİN mi geçiyor, yoksa model maskeyi hiç
    okumuyor mu? 0x03 verilince bobin 1-2 B'ye kaymalı — kaymıyorsa kapı SAHTE-YEŞİL."""
    global MASKE
    _yedek = MASKE
    try:
        MASKE = 0x03
        d1 = _unipolar_dalga(500, 100, 0, bobin_idx=0)
        d3 = _unipolar_dalga(500, 100, 0, bobin_idx=2)
        assert "A" not in d1 and d1.count("B") == 100, "model maske bitini OKUMUYOR -> kapi sahte-yesil"
        assert "B" not in d3, "maskesiz bobin de kaymis -> model bit indeksini yanlis uyguluyor"
        assert _bipolar_dalga(500, 100, bobin_idx=0)[0] == "B", "bipolar model maskeyi uygulamiyor"
    finally:
        MASKE = _yedek


# ============================================================================
# 4. DERLEME ÇIKTISI DEPOYA SIZMASIN
# ============================================================================


def test_KRITIK_build_ciktisi_izlenmiyor():
    """⚠️ Depoya sızan bir `.elf`, CubeIDE tarafından yeniden derlenmeden FLASHLANABILIR.

    Sahada bir gün kaybettirdi: masaüstü kopyasındaki 8 Eylül tarihli 5 bobinlik
    `PEMF_UNIPOLAR.elf` yakıldı → her pakete `STM_NACK: CRC`, hiçbir bobin çalışmadı.
    """
    ch = subprocess.run(
        ["git", "ls-files", "--", "firmware/stm32_pemf/Debug", "firmware/stm32_pemf/Release"],
        cwd=KOK,
        capture_output=True,
        text=True,
    )
    assert not ch.stdout.strip(), f"Debug/Release ciktisi depoya sizmis:\n{ch.stdout}"
