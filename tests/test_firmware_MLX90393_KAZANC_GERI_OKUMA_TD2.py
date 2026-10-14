# Author: mertaygn, cglrgrkn
"""TD2 (tezgâh Oturum 13 · K6) — MLX90393 kazanç / çözünürlük ayarı GERİ OKUNARAK doğrulanır; doğrulanamazsa `B=` BASILMAZ.

ÖLÇÜLEN KUSUR (tezgâh 2026-10-14, gerçek kart): Dünya alanı sınamasında çip yukarı / 180° yarı fark |0,169| mT (beklenen ≈ 0,04)
→ ölçek ≈ 4–5× BÜYÜK; bobin |pp| 13,3 mT (gerçekte ≈ 2,7–3,3). Kök (`pemf_sensor.c::mag_yapilandir`): RT (reset) komutundan
HEMEN sonra CONF1 okunup GAIN_SEL = 0 yazılıyordu; okuma başarısızsa yazma ATLANIYOR, yazma sonucu `(void)` ile atılıyor, GERİ
OKUMA YOK. Sensör varsayılanı GAIN_SEL = 7 (0,150 / 0,242 µT/LSB) → firmware 0,751 / 1,210 ile çevirince TAM 5× büyük, sessiz.

DÜZENEK: GERÇEK firmware + HAL ana makine koşum takımında; MLX90393 modeli GERÇEKÇİ kipte (`ALAN_UT`: alan µT, ham değer
CONF1 GAIN_SEL'e göre; açılış / RT varsayılanı GAIN_SEL 7; `MLX_RT_MESGUL`: RT sonrası cihaz kısa süre adres NACK'ler —
reset sürüyor; `MLX_YAZMA_YOK`: WR kayda geçmez). Alan (30, 0, −40) µT → |B| = 0,050 mT (Dünya alanı mertebesi).
SÖZLEŞME: reset sonrası bekle → yaz → GERİ OKU → tutmazsa yeniden dene; ölçülen |B| doğru ölçekte (±%10); `STM_SENS` satırı kazanç /
çözünürlük / ayar durumunu söyler; her `B=` satırı doğrulama işaretini (`GS=`/`RS=`) taşır; ayar doğrulanamazsa `B=` HİÇ basılmaz
(fail-closed — backend / arayüz "doğrulanamadı" der). Sensör kablosu ÇIKIP TAKILIRSA (`MLX_GUC_KESINTISI`: kayıtlar açılış
varsayılanına döner, adres değişmez) ayar yeniden geri okunur — eski firmware burada da sessizce 5×'e dönerdi.
⚠️ TEZGÂH-2: gerçek sensörde Dünya alanı yarı farkı ≈ 0,04 mT.
"""

from __future__ import annotations

import re
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="ana döngü koşum takımı Windows VEH'e dayanır")

GERCEK_MT = (30.0**2 + 40.0**2) ** 0.5 / 1000.0  # 0,050 mT


def _senaryo(*ek: str) -> str:
    s = ["SURE_US 4500000", "ERISIM_NS 50", "GETTICK_NS 1000", "I2C 2 MLX90393 18", "ALAN_UT 2 30.0 0.0 -40.0", *ek]
    return "\n".join(s) + "\n"


@pytest.fixture(scope="module")
def kosum(tmp_path_factory):
    import firmware_dongu_aparat as da

    dizin = tmp_path_factory.mktemp("td2")
    exe = da.derle(dizin)
    return {
        "mesgul": da.kos(exe, _senaryo("MLX_RT_MESGUL 2 5000"), dizin, "mesgul"),
        "yazma_yok": da.kos(exe, _senaryo("MLX_RT_MESGUL 2 5000", "MLX_YAZMA_YOK 2"), dizin, "yazma_yok"),
        # Kesinti PENCERE ORTASINDA (pencereler ~1,0 / 2,0 / 3,0 s'de kapanır): pencere başı denetimine yaslanılamaz.
        "kesinti": da.kos(
            exe, _senaryo("MLX_RT_MESGUL 2 5000", "MLX_GUC_KESINTISI 2 2400000 100000"), dizin, "kesinti"
        ),
        "uzun_mesgul": da.kos(exe, _senaryo("MLX_RT_MESGUL 2 25000"), dizin, "uzun_mesgul"),
    }


def _satirlar(k: dict, onek: str) -> list[str]:
    return [m.strip() for _b, _e, m in k["satirlar"] if onek in m]


def _b_degerleri(k: dict) -> list[float]:
    return [float(m.group(1)) for s in _satirlar(k, "STM_TELE: C=6") if (m := re.search(r"[,\s]B=([0-9.]+)", s))]


def test_KRITIK_reset_sonrasi_MESGUL_cihazda_bile_OLCEK_DOGRU(kosum):
    b = _b_degerleri(kosum["mesgul"])
    assert b, f"alan satırı yok: {_satirlar(kosum['mesgul'], 'STM_')[:8]}"
    oran = b[-1] / GERCEK_MT
    assert 0.9 <= oran <= 1.1, (
        f"ölçek {oran:.2f}× (B={b[-1]} mT, gerçek {GERCEK_MT:.3f}) — kazanç ayarı uygulanmadı (tezgâh ~5×)"
    )


def test_KRITIK_ayar_GERI_OKUNUR_ve_STM_SENS_soyler(kosum):
    mlx = [s for s in kosum["mesgul"]["ham"] if s.startswith("MLX hat=2")]
    assert mlx, "koşum takımı MLX sayaçlarını basmadı"
    m = re.search(r"wr=(\d+) rr=(\d+) rt=(\d+) conf1=0x([0-9A-F]+)", mlx[0])
    wr, rr = int(m.group(1)), int(m.group(2))
    assert (int(m.group(4), 16) >> 4) & 7 == 0, f"CONF1 GAIN_SEL 0 değil: {mlx[0]}"
    assert rr >= wr + 2, f"yazımdan sonra GERİ OKUMA yok (wr={wr}, rr={rr})"
    sens = [s for s in _satirlar(kosum["mesgul"], "STM_SENS: C=6 I2C2")]
    assert sens and "kazanc=0" in sens[0] and "ayar=DOGRULANDI" in sens[0], sens


def test_KRITIK_her_B_satiri_DOGRULAMA_isaretini_tasir(kosum):
    tele = [s for s in _satirlar(kosum["mesgul"], "STM_TELE: C=6") if "B=" in s]
    assert tele and all(re.search(r",GS=0,RS=0\b", s) for s in tele), tele[:3]


def test_KRITIK_sensor_kablosu_CIKIP_TAKILINCA_olcek_SESSIZCE_BOZULMAZ(kosum):
    """2,4 s'de kablo çıkar, 0,1 s sonra takılır → MLX kayıtları GAIN_SEL 7'ye döner, adres AYNI. Kesintiden SONRAKİ her `B=`
    doğru ölçekte olmalı (eski davranış: ayar bir daha denetlenmez → kalan seans boyunca ~5×) ve alan geri gelmeli."""
    k = kosum["kesinti"]
    sonra = [
        (b, float(m.group(1)))
        for b, _e, s in k["satirlar"]
        if "STM_TELE: C=6" in s and b > 2_000_000 and (m := re.search(r"[,\s]B=([0-9.]+)", s))
    ]
    assert sonra, f"kesintiden sonra alan GERİ GELMEDİ: {[s for _b, _e, s in k['satirlar'] if 'C=6' in s][-4:]}"
    kotu = [(b, v) for b, v in sonra if not 0.9 <= v / GERCEK_MT <= 1.1]
    assert not kotu, f"kesinti sonrası yanlış ölçek (gerçek {GERCEK_MT:.3f} mT): {kotu[:4]}"
    mlx = [s for s in k["ham"] if s.startswith("MLX hat=2")]
    assert (int(re.search(r"conf1=0x([0-9A-F]+)", mlx[0]).group(1), 16) >> 4) & 7 == 0, mlx


def test_KRITIK_yavas_reset_25ms_ACILISTA_dogrulanir(kosum):
    """Reset (RT) sonrası cihaz 25 ms meşgul: firmware her denemeden önce BEKLEMELİ (art arda denemeler meşgul pencerede
    tükenir → açılışta doğrulanamaz, alan ~10 s yok)."""
    k = kosum["uzun_mesgul"]
    sens = _satirlar(k, "STM_SENS: C=6 I2C2")
    assert sens and "ayar=DOGRULANDI" in sens[0], sens
    b = _b_degerleri(k)
    assert b and 0.9 <= b[0] / GERCEK_MT <= 1.1, b


def test_KRITIK_ayar_TUTMAZSA_B_BASILMAZ_ve_STM_SENS_DOGRULANAMADI(kosum):
    k = kosum["yazma_yok"]
    assert not _b_degerleri(k), f"doğrulanamayan ayarla alan basıldı: {_satirlar(k, 'STM_TELE: C=6')[:3]}"
    sens = _satirlar(k, "STM_SENS: C=6 I2C2")
    assert sens and "ayar=DOGRULANAMADI" in sens[0], sens
    assert not _satirlar(k, "STM_MAGCHK"), "doğrulanmamış alanla MAGCHK yorumu basıldı"
    mlx = [s for s in k["ham"] if s.startswith("MLX hat=2")]
    assert int(re.search(r"wr=(\d+)", mlx[0]).group(1)) >= 2, f"yeniden deneme yok: {mlx}"
