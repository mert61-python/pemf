# -*- coding: utf-8 -*-
# Author: mertaygn
"""İŞARETLİ EKSEN UÇLARI (−B / +B) — sürüş kipi ve faz kazancının TEK ölçülebilir yolu.

===============================================================================
NEDEN VAR (sahip amacı 2026-09-11: **maksimum dB/dt**)
===============================================================================
`alan_mt` / `magnetic_field` bir **BÜYÜKLÜKTÜR**: |B| = sqrt(x²+y²+z²). İşareti yoktur.

    unipolar   0 → +B :  tepe |B| = B      tepeden-tepeye = B
    bipolar   −B → +B :  tepe |B| = **B**  tepeden-tepeye = **2B**

Yani tepe |B| iki kipte **AYNI** okunur. Sahip bipolara geçtiğinde kazancı mevcut
CSV'den **GÖREMEZDİ** — ölçüm sessizce "değişmedi" derdi. Faz deneyinde durum daha da
kötü: dik eksenleri 180° kaydırınca alan büyüklükte değil DOĞRULTUDA değişir, |B| tepesi
**DÜŞER** ve iyileşme kayıp gibi görünür.

Sahip isteği (birebir): *"masaüstüne kaydederken de - +b diye kaydetsin"*.

===============================================================================
KAPININ ÖLÇTÜĞÜ
===============================================================================
1. Firmware altı ucu da basar (XN/XP/YN/YP/ZN/ZP) ve backend hepsini ayrıştırır.
2. CSV'de hem işaretli uçlar hem türetilmiş tepeden-tepeye sütunları vardır.
3. ⚠️ Uç YOKSA sütun **BOŞ** kalır — 0.0 yazılmaz (bu deponun tekrarlayan
   "ölçülmeyeni 0.0 kaydet" arızası).
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
MAIN = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
SENSOR_H = KOK / "firmware" / "stm32_pemf" / "Core" / "Inc" / "pemf_sensor.h"
SENSOR_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "pemf_sensor.c"

from headless_core import HeadlessCore  # noqa: E402
from servers.seans_alan_kaydi import CSV_BASLIKLARI, SeansAlanKaydi  # noqa: E402

UCLAR = ("mag_x_min", "mag_x_max", "mag_y_min", "mag_y_max", "mag_z_min", "mag_z_max")


def _ayristir(satir: str) -> dict:
    return HeadlessCore._parse_stm_tele(HeadlessCore.__new__(HeadlessCore), satir)


# ============================================================================
# 1. AYRIŞTIRMA
# ============================================================================


def test_KRITIK_alti_uc_da_ayristirilir():
    """MUTASYON: desenden `ZN`/`ZP` grubunu sil → KIRMIZI."""
    g = _ayristir("-> STM_TELE: C=6,B=1.842,N=412,XN=-1.203,XP=1.198,YN=-0.050,YP=0.062,ZN=-2.011,ZP=2.004")
    assert g is not None
    for k in UCLAR:
        assert k in g, f"{k} ayristirilmadi -> surus kipi/faz kazanci OLCULEMEZ"
    assert g["mag_x_min"] == pytest.approx(-1.203)
    assert g["mag_z_max"] == pytest.approx(2.004)


def test_KRITIK_NEGATIF_degerler_korunur():
    """⚠️ İşaret KAYBOLURSA bipolar ile unipolar ayırt EDİLEMEZ — kapının bütün amacı bu."""
    g = _ayristir("-> STM_TELE: C=6,B=2.0,XN=-1.900,XP=1.950,ZN=-0.010,ZP=2.000")
    assert g["mag_x_min"] < 0, "negatif uc POZITIFE dondu -> bipolar tespiti imkansiz"
    # bipolar imzasi: min ~ -max (DC ofset ~0)
    assert abs((g["mag_x_max"] + g["mag_x_min"]) / 2) < 0.1, "bipolar imzasi (DC~0) bozuldu"
    # unipolar imzasi: min ~ 0 (tek yonlu)
    assert abs(g["mag_z_min"]) < 0.1, "unipolar imzasi (min~0) bozuldu"


def test_KRITIK_UCLAR_YOKSA_anahtar_HIC_KONMAZ():
    """Eski firmware bu alanları basmaz → aşağı akış "ölçülmedi" ile "0.0"ı ayırabilmeli."""
    g = _ayristir("-> STM_TELE: C=6,T=30.0,B=1.5")
    for k in UCLAR:
        assert k not in g, f"{k} olculmediği halde anahtar KONDU -> 0.0 'olculdu' sayilir"


# ============================================================================
# 2. CSV
# ============================================================================


def test_KRITIK_CSV_isaretli_uclari_ve_tepeden_tepeyeyi_TASIR():
    for k in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max", "pp_x", "pp_y", "pp_z"):
        assert k in CSV_BASLIKLARI, f"CSV sutunu '{k}' YOK"


def test_KRITIK_CSV_satiri_UCLARI_ve_TURETILMIS_pp_yi_yazar(tmp_path, monkeypatch):
    """MUTASYON: `olcum`daki `uclar` bloğunu sil → KIRMIZI."""
    monkeypatch.setattr("servers.seans_alan_kaydi.masaustu_dizini", lambda: (tmp_path, "test"))
    k = SeansAlanKaydi()
    yol = k.seans_basladi("S1", {})
    assert yol is not None
    k.olcum(
        6,
        2.0,
        400,
        False,
        uclar={
            "mag_x_min": -1.2,
            "mag_x_max": 1.3,
            "mag_y_min": -0.1,
            "mag_y_max": 0.1,
            "mag_z_min": -2.0,
            "mag_z_max": 2.1,
        },
    )
    k.seans_bitti("test")

    with io.open(yol, encoding="utf-8-sig", newline="") as f:
        satirlar = list(csv.reader(f))
    bas = next(s for s in satirlar if s and s[0] == "zaman")
    veri = satirlar[satirlar.index(bas) + 1]
    d = dict(zip(bas, veri))

    assert float(d["x_min"]) == pytest.approx(-1.2), "x_min yazilmadi"
    assert float(d["z_max"]) == pytest.approx(2.1), "z_max yazilmadi"
    assert float(d["pp_x"]) == pytest.approx(2.5), f"pp_x TURETILMEDI (x_max-x_min): {d['pp_x']}"
    assert float(d["pp_z"]) == pytest.approx(4.1), "pp_z TURETILMEDI"


def test_KRITIK_UC_YOKSA_sutun_BOS_kalir_SIFIR_DEGIL(tmp_path, monkeypatch):
    """⚠️ 0.0 yazmak "olctuk, sifir cikti" demektir — bu deponun tekrarlayan arizasi."""
    monkeypatch.setattr("servers.seans_alan_kaydi.masaustu_dizini", lambda: (tmp_path, "test"))
    k = SeansAlanKaydi()
    yol = k.seans_basladi("S2", {})
    k.olcum(6, 2.0, 400, False)  # uclar YOK (eski firmware)
    k.seans_bitti("test")

    with io.open(yol, encoding="utf-8-sig", newline="") as f:
        satirlar = list(csv.reader(f))
    bas = next(s for s in satirlar if s and s[0] == "zaman")
    d = dict(zip(bas, satirlar[satirlar.index(bas) + 1]))
    for k2 in ("x_min", "x_max", "pp_x", "pp_z"):
        assert d[k2] == "", f"uc YOKKEN '{k2}' = {d[k2]!r} yazildi (bos olmaliydi)"


# ============================================================================
# 3. FIRMWARE
# ============================================================================


@pytest.mark.skipif(not MAIN.exists(), reason="firmware kaynagi yok")
def test_KRITIK_firmware_ALTI_UCU_da_basar():
    kod = io.open(MAIN, encoding="utf-8", errors="replace").read()
    m = re.search(r'",B=%\.3f,N=%u([^"]*)"', kod)
    assert m, "telemetri bicim dizesi bulunamadi"
    for alan in ("XN=", "XP=", "YN=", "YP=", "ZN=", "ZP="):
        assert alan in m.group(1), f"firmware {alan} basmiyor"


@pytest.mark.skipif(not SENSOR_C.exists(), reason="firmware kaynagi yok")
def test_KRITIK_ILK_ornek_uclari_ORNEGE_kurar_SIFIRA_DEGIL():
    """⚠️ Uçları 0.0'dan başlatmak, alan hiç 0'ı geçmiyorsa (tek yönlü sürüş + DC ofset)
    SAHTE bir salınım uydurur ve tepeden-tepeyeyi olduğundan BÜYÜK gösterir.

    MUTASYON: `if (h->zirve_ornek == 0U)` dalını sil → KIRMIZI.
    """
    kod = io.open(SENSOR_C, encoding="utf-8", errors="replace").read()
    assert re.search(r"if \(h->zirve_ornek == 0U\) \{\s*\n\s*h->uc_x_min = h->uc_x_max = xm;", kod), (
        "ilk ornekte uclar ORNEGE kurulmuyor -> sahte salinim uydurulur"
    )


@pytest.mark.skipif(not SENSOR_H.exists(), reason="firmware kaynagi yok")
def test_KRITIK_veri_yapisi_alti_ucu_TASIR():
    kod = io.open(SENSOR_H, encoding="utf-8", errors="replace").read()
    for alan in ("uc_x_min", "uc_x_max", "uc_y_min", "uc_y_max", "uc_z_min", "uc_z_max"):
        assert alan in kod, f"PEMF_SensorVerisi_t '{alan}' tasimiyor"
