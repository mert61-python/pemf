# Author: mertaygn, cglrgrkn
"""TD5 (tezgâh Oturum 13 · K4, K5, A4) — takılı olmayan (YÜZEN) ACS712 girişi "kalibre" SAYILMAZ, akım BASILMAZ; açılış raporu doğru.

ÖLÇÜLEN KUSUR (tezgâh, PSU KAPALI, yeni imaj): `STM_TELE: C=1,I=74.630` · `C=2,I=33.243` · `C=3,I=19.820,X=1` · `C=4,I=3.826,X=1`;
arayüzde 10–115 A, 46 "ölçüm aralığını AŞTI" bildirimi, "Anlık Güç" 6,3 W. Kök (`pemf_akim.c`): kalibrasyon yalnız 100 örneğin
ORTALAMASININ 0,5–3,2 V penceresine bakıyor → yüzen pin (geniş salınım, ortalama pencerede) "kalibre" sayılıp gürültü RMS'i amper
olarak basılıyor; açılış raporu `ok` bayrağını ilk `Poll`'dan ÖNCE okuduğu için HER ZAMAN "YOK/kalibre-EDILEMEDI" yazıyor.
DÜZENEK: GERÇEK firmware + HAL ana makine koşum takımında; ADC modeli: `ACS <kanal> <mV>` kararlı sensör (±2 LSB), `ACS_YUZEN
<kanal> <merkez> <genlik>` yüzen giriş (her dönüşüm merkez ± genlik), verilmeyen kanal 0 V. Bobin 1..5 = ADC IN0, IN3, IN4, IN10, IN13.
SÖZLEŞME: kararlı 2,5 V → "hazir" ve ~0 A; yüzen → "kalibre-EDILEMEDI" (neden: değişken) ve HİÇ `I=` satırı yok; 0 V → pencere dışı.
"""

from __future__ import annotations

import re
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="ana döngü koşum takımı Windows VEH'e dayanır")


@pytest.fixture(scope="module")
def kosum(tmp_path_factory):
    import firmware_dongu_aparat as da

    dizin = tmp_path_factory.mktemp("td5")
    exe = da.derle(dizin)
    s = [
        "SURE_US 2500000",
        "ERISIM_NS 50",
        "GETTICK_NS 1000",
        "ACS 0 2500",  # bobin 1: takılı sensör, 0 A (VCC/2)
        "ACS_YUZEN 3 1650 1500",  # bobin 2: yüzen giriş, ortalama pencerede (tezgâh C=2 I=33 A)
        # bobin 3 (IN4): hiçbir şey → 0 V (pencere dışı)
        "ACS_YUZEN 10 1200 900",  # bobin 4: yüzen, dar salınım ama yine geniş (0,3–2,1 V)
        "ACS 13 2480",  # bobin 5: takılı sensör
    ]
    return da.kos(exe, "\n".join(s) + "\n", dizin, "td5")


def _sens(k, bobin):
    return [m.strip() for _b, _e, m in k["satirlar"] if f"STM_SENS: C={bobin} ACS712=" in m]


def _akim(k, bobin):
    return [
        float(x.group(1)) for _b, _e, m in k["satirlar"] if (x := re.search(rf"STM_TELE: C={bobin},I=([0-9.]+)", m))
    ]


@pytest.mark.parametrize("bobin", [1, 5])
def test_KRITIK_takili_sensor_HAZIR_raporlanir_ve_sifir_akim(kosum, bobin):
    s = _sens(kosum, bobin)
    assert s and "ACS712=hazir" in s[0], f"açılış raporu kalibrasyonun sonucunu söylemiyor: {s}"
    i = _akim(kosum, bobin)
    assert i and max(i) < 0.15, f"bobin {bobin}: 0 A'de akım {i[:5]}"


@pytest.mark.parametrize("bobin", [2, 4])
def test_KRITIK_YUZEN_pin_kalibre_SAYILMAZ_ve_akim_BASILMAZ(kosum, bobin):
    i = _akim(kosum, bobin)
    assert not i, f"bobin {bobin}: takılı olmayan girişten akım basıldı (tezgâh 74 A sınıfı): {i[:5]}"
    s = _sens(kosum, bobin)
    assert s and "kalibre-EDILEMEDI" in s[0] and "degisken" in s[0], s


def test_KARSIT_sinyalsiz_kanal_PENCERE_disi(kosum):
    s = _sens(kosum, 3)
    assert s and "kalibre-EDILEMEDI" in s[0] and "pencere" in s[0], s
    assert not _akim(kosum, 3)
