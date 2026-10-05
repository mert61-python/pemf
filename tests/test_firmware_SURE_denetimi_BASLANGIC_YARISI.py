# Author: mertaygn, cglrgrkn
"""1-G YENİ BULGU — STM süre denetimi bobin BAŞLARKEN yanlışlıkla "süre doldu" deyip bobini DURDURMAZ.

Ölçüm aracı: ana döngü koşum takımı (`tests/firmware_dongu_aparat.py`; GERÇEK main.c + HAL 1.8.5, sanal zaman) ve salt-okur
sonda (etkin bobin maskesi `g_active`, her ms). Paketler backend'in GERÇEK kurucusundan (`HardwareController`: bobin 1-5
100 Hz %40 5 dk başlat / `stop_all_coils`).

ÖLÇÜLEN KUSUR (D1.106 koşum takımıyla bulundu): ana döngü `current_time`'ı tur BAŞINDA alır; aynı turda işlenen paket
bobini başlatınca TIM1 ISR'ı `g_start_ms[i] = HAL_GetTick()` yazar (TAZE). Arada SysTick ilerlediyse
`start_ms = current_time + 1` → işaretsiz `current_time - start_ms` = 4 294 967 295 ≥ hedef → bobin başlar başlamaz
DURDURULUR ve `STM_STOPPED: Sure(ler) doldu` basılır; sonraki keep-alive bobini yeniden başlatır (tedavi kesik kesik,
kayıt "süre doldu" der). Güvenli yön (durdurma) ama hekimin girdiği süreye sadakat yok.

SÖZLEŞME: süre denetimi yalnız gerçekten geçen süreyle durdurur — 30 başlatmanın (her biri farklı fazda) HİÇBİRİNDE bobin
durdurma paketinden önce kapanmaz; 5 dk'lık sürede STM_STOPPED basılmaz. ⚠️ TEZGÂH (Oturum 13): kartta doğrulanır.
⚠️ Yalnız Windows (VEH): başka platformda gerekçeli SKIP (Linux portu YOK).
"""

from __future__ import annotations

import random
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="ana döngü koşum takımı Windows VEH'e dayanır; Linux portu YOK (DUZELTME-D1G açık madde)",
)

N_BASLAT = 30
BAS_US = 2_500_000
ARA_US = 1_000_000
STOP_SONRA_US = 600_000
FAZ_US = 200_000


def _paketler() -> tuple[bytes, bytes]:
    from kayitci_donanim import gercek_hc, paket_coz

    with gercek_hc() as hc:
        for cid in range(1, 6):
            hc.update_coil(cid, 100, 40, 0, 5, start=True)
        hc.stop_all_coils()
        q = hc.core._hw_send_queue.paketler
        baslat, dur = q[4], q[-1]
    assert all(x > 0 for x in paket_coz(baslat)[0][:5]), "aparat: başlatma paketi bobin 1-5'i sürmüyor"
    assert not any(x > 0 for x in paket_coz(dur)[0]), "aparat: durdurma paketi sıfır değil"
    return baslat, dur


@pytest.fixture(scope="module")
def kosu(tmp_path_factory):
    import firmware_dongu_aparat as da

    dizin = tmp_path_factory.mktemp("sure")
    exe = da.derle(dizin)
    baslat, dur = _paketler()
    rnd = random.Random(1061)
    baslar = [BAS_US + k * ARA_US + rnd.randrange(FAZ_US) for k in range(N_BASLAT)]
    akis = []
    for t in baslar:
        akis += [(t, baslat), (t + STOP_SONRA_US, dur)]
    # CPU modeli: newlib-nano snprintf ~3 µs @168 MHz (ACK biçimleme ~30 çağrı ≈ 90 µs → TIM1 ISR'ı (20 µs) gölgeyi
    # aynı turda uygular — gerçek kartta olduğu gibi). Takımın varsayılanı 0'dır (CPU "anlık"): o hâlde yarış penceresi
    # yapay olarak dar kalır (1-G: aynı senaryoda 0/30).
    s = ["SURE_US %d" % (baslar[-1] + ARA_US), "ERISIM_NS 50", "GETTICK_NS 1000", "SNPRINTF_NS 3000"]
    s += [f"ACS {k} 2500" for k in (0, 3, 4, 10, 13)]
    s += ["I2C 1 MLX90614 5A", "I2C 2 MLX90393 18"]
    s += [f"PAKET {t} {p.hex()}" for t, p in akis]
    k = da.kos(exe, "\n".join(s) + "\n", dizin, "sure", sinir_sn=1500)
    k["baslar"] = baslar
    return k


def _araliklar(aktif: list) -> list:
    araliklar, ac = [], None
    for t_us, maske in aktif:
        if maske and ac is None:
            ac = t_us
        elif not maske and ac is not None:
            araliklar.append((ac, t_us))
            ac = None
    if ac is not None:
        araliklar.append((ac, 10**12))
    return araliklar


def test_KRITIK_SURE_30_baslatmanin_HICBIRINDE_bobin_DURDURMADAN_once_KAPANMAZ(kosu):
    araliklar = _araliklar(kosu["aktif"])
    acilan, erken = 0, []
    for t in kosu["baslar"]:
        a = next(((ac, kp) for ac, kp in araliklar if t <= ac < t + 50_000), None)
        if a is None:
            continue
        acilan += 1
        if a[1] < t + STOP_SONRA_US - 50_000:
            erken.append((t, a[1] - a[0]))
    assert acilan == N_BASLAT, f"aparat: {N_BASLAT} başlatmanın yalnız {acilan}'inde bobinler açıldı"
    assert erken == [], (
        f"{N_BASLAT} başlatmanın {len(erken)}'inde bobinler DURDURMA paketinden önce kapandı (süre 5 dk) — "
        f"(başlatma_us, açık_kalma_us): {erken[:4]}"
    )


def test_KRITIK_SURE_dolmadan_STM_STOPPED_basilmaz(kosu):
    durdu = [x for x in kosu["satirlar"] if "STM_STOPPED" in x[2]]
    assert durdu == [], f"5 dk'lık süre dolmadan {len(durdu)} 'STM_STOPPED: Sure(ler) doldu' satırı: {durdu[:2]}"
