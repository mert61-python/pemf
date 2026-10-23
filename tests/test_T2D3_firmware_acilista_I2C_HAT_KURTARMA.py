# -*- coding: utf-8 -*-
"""T2D-3 (Tezgâh-2 #4) — MLX90393 yazılım reset'inden sonra KAYBOLMAZ: açılışta I2C hat kurtarması; protokol / paket AYNI, sürüm bir artar.

ÖLÇÜLEN KUSUR (Tezgâh-2, 2026-10-23, DDS v2.4): `STM32_Programmer_CLI -c port=SWD -rst` sonrası açılış raporu `I2C2 … (SENSOR YOK)`,
`B=` satırı yok — 3 / 3 reset'te; USB güç döngüsü kurtardı. Yazılım reset'i yalnız MCU'yu sıfırlar; MLX güç almaya devam eder ve
reset bir I2C işleminin ortasına denk gelince SDA'yı LOW tutar. `i2c_hat_kurtar` (9 SCL darbesi + elle STOP + SWRST) vardı ama
YALNIZ çalışırken art arda 5 hatadan sonra koşuyordu; açılış yoklaması (`cihaz_var` / `mag_adres_bul`) takılı hatta sensörü bulamıyordu.
SÖZLEŞME: `PEMF_Sensor_Init` her hatta pinler kurulduktan SONRA, adres yoklamasından ÖNCE bir kez `i2c_hat_kurtar` koşar; kurtarma
GPIO kipine geçmeden önce çıkış mandalını HIGH yazar (geçişte sahte START yok). Protokol revizyonu 3 ve paket 121 bayt AYNI; banner
sürümü v2.4'ten büyük (main.c = simülatör = README: tests/test_YH_D7_firmware_surum_dizesi_Y80.py).
Kart davranışı (gerçek reset ×3 → sensör bulunur) TEZGÂHTA ölçülür; burada kaynak + gerçek çapraz derleme (rapor T2D).
"""

from __future__ import annotations

import re
from pathlib import Path

from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
SENSOR_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "pemf_sensor.c"
MAIN_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"


def _govde(kod: str, imza: str) -> str:
    i = kod.find(imza)
    assert i >= 0, f"{imza} yok"
    j = kod.find("{", i)
    derinlik, k = 0, j
    while True:
        if kod[k] == "{":
            derinlik += 1
        elif kod[k] == "}":
            derinlik -= 1
            if derinlik == 0:
                return kod[j : k + 1]
        k += 1


def test_KRITIK_acilista_HAT_KURTARMA_pin_kurulumundan_SONRA_yoklamadan_ONCE():
    g = _govde(c_soy(SENSOR_C.read_text(encoding="utf-8")), "void PEMF_Sensor_Init(void)")
    son_kurulum = g.rfind("hat_donanim_kur(")
    kurtarma = g.find("i2c_hat_kurtar(")
    ilk_yoklama = min(i for i in (g.find("cihaz_var("), g.find("mag_adres_bul(")) if i >= 0)
    assert kurtarma >= 0, (
        "açılışta I2C hat kurtarması YOK — yazılım reset'inden sonra MLX SDA'yı tutar, sensör bulunmaz"
    )
    assert son_kurulum < kurtarma < ilk_yoklama, (
        "hat kurtarma pin kurulumundan SONRA ve adres yoklamasından ÖNCE olmalı"
    )
    dongu = g[g.rfind("for", 0, kurtarma) : kurtarma]
    assert "PEMF_SENSOR_BOBIN_SAYISI" in dongu, "kurtarma her hatta (I2C1 + I2C2) koşmalı"


def test_KRITIK_kurtarma_GPIO_kipinden_ONCE_mandali_HIGH_yazar():
    g = _govde(c_soy(SENSOR_C.read_text(encoding="utf-8")), "static void i2c_hat_kurtar(SensorHat_t *h)")
    yuksek = re.search(r"BSRR\s*=\s*\(uint32_t\)\(h->scl_pin\s*\|\s*h->sda_pin\)", g)
    gpio = g.find("i2c_pin_gpio(h, true)")
    assert yuksek and yuksek.start() < gpio, "GPIO kipine geçerken ODR=0 iki hattı birlikte düşürür (sahte START)"
    assert re.search(r"for\s*\([^)]*<\s*9U", g) and "I2C_CR1_SWRST" in g


def test_KRITIK_protokol_ve_paket_AYNI_surum_ARTTI():
    import sys

    sys.path.insert(0, str(KOK))
    from utils.stm32_transport import STM_PAKET_BOYU

    import tools.stm32_simulator as sim

    assert STM_PAKET_BOYU == 121 and sim.PKT_SIZE == 121 and sim.PROTOKOL_REV == 3, "protokol / paket DEĞİŞMEMELİ"
    m = re.search(r'"-> STM_READY: DDS v(\d+)\.(\d+) ', c_soy(MAIN_C.read_text(encoding="utf-8")))
    assert m and (int(m.group(1)), int(m.group(2))) > (2, 4), (
        "T2D-3: firmware değişti → banner sürümü v2.4'ten BÜYÜK olmalı"
    )
