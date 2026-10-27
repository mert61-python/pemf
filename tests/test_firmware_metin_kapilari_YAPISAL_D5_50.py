# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.50 (B-10.143 · .149 · .160 · .163) — STM / S3 firmware METİN kapıları yorum-soyulmuş YAPI kapılarına çevrildi.

Eski kapılar ham metinde alt-dize arıyordu; şu mutantlar 48 testte YEŞİL kalıyordu (ölçüldü, `_inceleme/D5.50`):
  (a1) STM tepe: `if (mt > h->zirve_mt) { }` + koşulsuz `h->zirve_mt = mt;` — "max" aslında "son örnek" olur, darbe kapalıyken biten
       pencere ~0 "yoğunluk" gösterir;
  (a2) ilk örnekte y / z uçları kurulmaz — sahte salınım (tepeden-tepeye büyük);
  (a3) S3 `if (false && !_i2cHazir) return;` — açılış yarışı (bus'a erken dokunma);
  (b)  PB1 sync darbesi `g_sync_pulse_countdown = 0U;` — darbe 100 µs yerine hiç inmez (kalıcı HIGH);
  (c)  `coil_gpio[NUM_COILS]` 7. girdi silinir — C sıfırla doldurur (portA = NULL, ISR NULL'a yazar) — `DIZI_TANIMI` artık yapı tiplerini de
       görür (`test_stm_bobin_sayisi_tek_kaynak.py`), burada coil_gpio'nun ölçüldüğü ayrıca pinlenir.
(d) printf-float nm kapısı (`scripts/firmware_derle.py`) ZATEN KAPALI (5d299048 / D1.29: `not in` → `in`, nm dalı `if False and`, nm yoksa
    geçer — üçü de mevcut kapılarda KIRMIZI); kaynakta `g_printf_float_zorla` KALIR, derleme betiğine `-u _printf_float` EKLENMEZ.
Yorum soyucu: `tests/c_soyucu.py::c_soy` (dizge-farkında).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
SENSOR_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "pemf_sensor.c"
MAIN_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
S3_CPP = KOK / "firmware" / "esps3_pemf_coil" / "SensorManager.cpp"

pytestmark = pytest.mark.skipif(
    not (SENSOR_C.exists() and MAIN_C.exists() and S3_CPP.exists()), reason="firmware kaynagi yok"
)


def _kod(p: Path) -> str:
    return c_soy(p.read_text(encoding="utf-8", errors="replace"))


def _blok(kod: str, ac: int) -> str:
    """`kod[ac] == "{"` olan bloğun İÇİ (dengeli süslü parantez)."""
    assert kod[ac] == "{", "aparat: blok başı '{' değil"
    derinlik = 0
    for j in range(ac, len(kod)):
        if kod[j] == "{":
            derinlik += 1
        elif kod[j] == "}":
            derinlik -= 1
            if derinlik == 0:
                return kod[ac + 1 : j]
    raise AssertionError("blok kapanmadi")


def _if_govdesi(kod: str, kosul_re: str) -> tuple[int, int, str]:
    m = re.search(r"\bif\s*\(\s*" + kosul_re + r"\s*\)\s*\{", kod)
    assert m, f"`if ({kosul_re})` bloğu yok"
    govde = _blok(kod, m.end() - 1)
    return m.start(), m.end() + len(govde) + 1, govde


def _mag_oku(kod: str) -> str:
    m = re.search(r"\bcase\s+S_MAG_OKU\s*:\s*\{", kod)
    assert m, "S_MAG_OKU durumu yok — kapı bayat"
    return _blok(kod, m.end() - 1)


def test_KRITIK_a1_STM_tepe_YALNIZ_karsilastirma_govdesinde_atanir():
    g = _mag_oku(_kod(SENSOR_C))
    bas, son, ic = _if_govdesi(g, r"mt\s*>\s*h->zirve_mt")
    assert re.search(r"\bh->zirve_mt\s*=\s*mt\s*;", ic), (
        "tepe karşılaştırmasının GÖVDESİNDE `h->zirve_mt = mt;` yok — 'max' güncellenmiyor (D5.50)"
    )
    disarida = g[:bas] + g[son:]
    assert not re.search(r"\bh->zirve_mt\s*=", disarida), (
        "S_MAG_OKU'da tepe karşılaştırma DIŞINDA koşulsuz `h->zirve_mt = …` var — raporlanan 'tepe' SON örnek olur (D5.50)"
    )


def test_KRITIK_a2_ilk_ornekte_UC_EKSENIN_de_uclari_ORNEGE_kurulur():
    g = _mag_oku(_kod(SENSOR_C))
    _b, _s, ic = _if_govdesi(g, r"h->zirve_ornek\s*==\s*0U?")
    for eksen in ("x", "y", "z"):
        assert re.search(rf"\bh->uc_{eksen}_min\s*=\s*h->uc_{eksen}_max\s*=\s*{eksen}m\s*;", ic), (
            f"ilk geçerli örnekte {eksen} ucu ÖRNEĞE kurulmuyor — 0.0'dan başlar, sahte salınım uydurulur (D5.50)"
        )


def test_KRITIK_a3_S3_pollMagnetic_kurulum_hazir_degilse_DONER():
    kod = _kod(S3_CPP)
    m = re.search(r"void\s+SensorManager::pollMagnetic\s*\(\s*\)\s*\{", kod)
    assert m, "pollMagnetic yok — kapı bayat"
    govde = _blok(kod, m.end() - 1)
    giris = govde.split("const unsigned long simdi", 1)[0]
    assert re.search(r"\bif\s*\(\s*!\s*_i2cHazir\s*\)\s*\{?\s*return\s*;", giris), (
        "pollMagnetic girişinde ÇALIŞAN `if (!_i2cHazir) return;` kapısı yok — kurulum sürerken bus'a dokunur (açılış yarışı) (D5.50)"
    )


def test_KRITIK_b_PB1_sync_darbesi_DDS_SYNC_PULSE_TICKS_ile_kurulur():
    kod = _kod(MAIN_C)
    m = re.search(r"#define\s+DDS_SYNC_PULSE_TICKS\s+(\d+)U?\b", kod)
    assert m and int(m.group(1)) > 0, "DDS_SYNC_PULSE_TICKS tanımı yok ya da 0"
    yuksel = [x.start() for x in re.finditer(r"GPIOB->BSRR\s*=\s*\(uint32_t\)\s*GPIO_PIN_1\s*;", kod)]
    assert yuksel, "PB1 HIGH yazımı (sync darbesi başlangıcı) bulunamadı — kapı bayat"
    for i in yuksel:
        sonraki = re.search(r"\bg_sync_pulse_countdown\s*=\s*([^;]+);", kod[i : i + 400])
        assert sonraki and sonraki.group(1).strip() == "DDS_SYNC_PULSE_TICKS", (
            f"PB1 HIGH yapıldıktan sonra sayaç {sonraki.group(1).strip() if sonraki else 'YOK'} ile kuruluyor — "
            "darbe 100 µs'de inmez, PB1 kalıcı HIGH (D5.50)"
        )


def test_KRITIK_c_coil_gpio_pin_haritasi_NUM_COILS_eleman_ve_DIZI_kapisinda():
    import test_stm_bobin_sayisi_tek_kaynak as bobin

    kod = bobin.yorumsuz(MAIN_C.read_text(encoding="utf-8", errors="replace"))
    adlar = [m.group(2) for m in bobin.DIZI_TANIMI.finditer(kod)]
    assert "coil_gpio" in adlar, (
        "bobin pin haritası (coil_gpio) [NUM_COILS] dizi kapısının DIŞINDA — eksik girdi NULL port olur (D5.50)"
    )
    assert not [
        k for k in bobin.ihlaller(MAIN_C.read_text(encoding="utf-8", errors="replace")) if k[0] == "coil_gpio"
    ], "coil_gpio NUM_COILS'ten az girdi taşıyor — eksik bobinin portu NULL (ISR NULL'a yazar) (D5.50)"
