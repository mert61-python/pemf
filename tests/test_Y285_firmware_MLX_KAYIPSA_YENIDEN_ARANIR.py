# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y285 (sahip 13 Kasım 2026: "MLX'in I2C hattı reconnect algoritmasını düzgünce eklersin, kopsa bile bağlanır; birkaç denemeden sonra
bağlanmazsa kullanıcıya uyarı gider") — FIRMWARE KISMI (kullanıcı uyarısı: `test_Y285_backend_MLX_BEKCISI_*`).

ÖLÇÜLEN KUSUR (tezgâh 13-11, iki kez): kart reset'lenmeden yalnız `STM_OK` geliyor, `STM_TELE B=` YOK; reset'le düzeliyordu. Kök
(`pemf_sensor.c`): MLX90393 adresi YALNIZ açılışta yoklanıyordu (`mag_adres_bul`); bulunamazsa `mag_adres = 0` ve bir daha HİÇ aranmıyordu.
SÖZLEŞME (DDS v2.6): adresi 0 olan hatta 2 sn'de bir (her 3. denemede önce hat kurtarması) yeniden yoklama; bulununca ayar bloklamadan
zamanlanır, GERİ OKUNUP doğrulanınca ölçüm başlar (doğru ölçek); tutmazsa RT'siz yeniden denenir. Bulunduktan sonra UZUN kopan sensör de
geri gelir. Adres NACK'inde (AF) ADDR beklemesi hemen biter (yoklama ana döngüyü bekletmez).
DÜZENEK: GERÇEK firmware + HAL ana makine koşum takımında (`firmware_dongu_aparat`); `MLX_GUC_KESINTISI <hat> <başlangıç_us> <süre_us>`:
o süre boyunca sensör adresi NACK'ler (kablo çıkık), ardından kayıtlar açılış varsayılanına döner (yeniden güç aldı).
"""

from __future__ import annotations

import re
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="ana döngü koşum takımı Windows VEH'e dayanır")

GERCEK_MT = (30.0**2 + 40.0**2) ** 0.5 / 1000.0  # 0,050 mT


def _senaryo(*ek: str, sure_us: int = 7_000_000) -> str:
    s = [f"SURE_US {sure_us}", "ERISIM_NS 50", "GETTICK_NS 1000", "I2C 2 MLX90393 18", "ALAN_UT 2 30.0 0.0 -40.0", *ek]
    return "\n".join(s) + "\n"


@pytest.fixture(scope="module")
def kosum(tmp_path_factory):
    import firmware_dongu_aparat as da

    dizin = tmp_path_factory.mktemp("y285")
    exe = da.derle(dizin)
    return {
        # açılışta sensör YOK (kablo çıkık 0–1,5 sn), sonra takılır
        "acilista_yok": da.kos(
            exe, _senaryo("MLX_RT_MESGUL 2 5000", "MLX_GUC_KESINTISI 2 0 1500000"), dizin, "acilista_yok"
        ),
        # çalışırken 3 sn kopma (1,5 → 4,5 sn)
        "uzun_kopma": da.kos(
            exe,
            _senaryo("MLX_RT_MESGUL 2 5000", "MLX_GUC_KESINTISI 2 1500000 3000000", sure_us=9_000_000),
            dizin,
            "uzun_kopma",
        ),
        # açılışta yok + YAVAŞ reset (RT sonrası 25 ms meşgul; ayar beklemesi 10 ms) — RT'siz yeniden deneme gerekir
        "acilista_yok_yavas": da.kos(
            exe, _senaryo("MLX_RT_MESGUL 2 25000", "MLX_GUC_KESINTISI 2 0 1500000"), dizin, "acilista_yok_yavas"
        ),
        # ayar HİÇ tutmaz (WR kayda geçmez): fail-closed kalır, ama 2 sn'de bir yeni RT'yle yeniden dener (eskiden 10 pencere)
        "ayar_tutmaz": da.kos(
            exe, _senaryo("MLX_RT_MESGUL 2 5000", "MLX_YAZMA_YOK 2", sure_us=5_000_000), dizin, "ayar_tutmaz"
        ),
    }


def _b(k: dict) -> list[tuple[int, float]]:
    """(satır başlangıcı µs, B mT) — `STM_TELE: C=6` satırları."""
    out = []
    for bas, _e, m in k["satirlar"]:
        if "STM_TELE: C=6" in m and (g := re.search(r"[,\s]B=([0-9.]+)", m)):
            out.append((bas, float(g.group(1))))
    return out


def test_KRITIK_acilista_BULUNAMAYAN_sensor_TAKILINCA_bulunur_ve_OLCEK_DOGRU(kosum):
    k = kosum["acilista_yok"]
    b = _b(k)
    assert b, "açılışta bulunamayan sensör sonradan takılınca HİÇ bulunmadı (eski firmware davranışı)"
    ilk = b[0][0]
    assert 1_500_000 < ilk <= 5_000_000, (
        f"ilk B satırı {ilk} µs — beklenen: takıldıktan (1,5 sn) sonra ≤ 2 yoklama aralığı + pencere"
    )
    assert all(abs(v - GERCEK_MT) <= 0.1 * GERCEK_MT for _t, v in b[1:]), [
        v for _t, v in b
    ]  # ayar geri okundu → ölçek doğru
    sens = [m for _b0, _e, m in k["satirlar"] if "STM_SENS" in m and "I2C2" in m]
    assert sens and "alan=0x00" in sens[0], f"açılış raporu sensörü YOK demeliydi: {sens[:1]}"


def test_KRITIK_calisirken_UZUN_kopan_sensor_GERI_GELIR(kosum):
    b = _b(kosum["uzun_kopma"])
    once = [t for t, _v in b if t < 1_500_000]
    sonra = [(t, v) for t, v in b if t > 4_500_000]
    assert once, "kopmadan önce ölçüm yoktu"
    assert sonra and sonra[0][0] <= 7_500_000, f"kopma bittikten sonra ölçüm geri gelmedi / geç geldi: {sonra[:2]}"
    assert all(abs(v - GERCEK_MT) <= 0.1 * GERCEK_MT for _t, v in sonra[1:]), [v for _t, v in sonra]
    kopukken = [t for t, _v in b if 2_600_000 <= t <= 4_500_000]
    assert not kopukken, f"sensör çıkıkken B basıldı (bayat değer): {kopukken[:3]}"


def test_KRITIK_YAVAS_reset_eden_sensor_RT_TEKRARLANMADAN_yeniden_denenir(kosum):
    """RT sonrası 25 ms meşgul sensör: ayar 10 ms sonra denenir, tutmazsa RT'siz `MLX90393_AYAR_DENEME` kez daha (her RT meşgul pencereyi
    YENİDEN başlatır — her denemede RT olsaydı ayar hiç tutmazdı; eski 10 sn'lik aralık da ölçümü 10 sn geciktirirdi)."""
    b = _b(kosum["acilista_yok_yavas"])
    assert b and b[0][0] <= 5_000_000, (
        f"yavaş reset eden sensör sonradan takılınca ölçüm başlamadı / geç başladı: {b[:2]}"
    )
    assert all(abs(v - GERCEK_MT) <= 0.1 * GERCEK_MT for _t, v in b[1:]), [v for _t, v in b]


def test_KRITIK_ayar_TUTMAYAN_sensor_B_basmaz_ama_2_snde_bir_YENIDEN_dener(kosum):
    k = kosum["ayar_tutmaz"]
    assert not _b(k), "doğrulanamayan ayarla alan basıldı (fail-closed bozuldu)"
    mlx = [s for s in k["ham"] if s.startswith("MLX hat=2")]
    rt = int(re.search(r"rt=(\d+)", mlx[0]).group(1))
    assert rt >= 3, (
        f"5 sn'de {rt} RT — açılış 1 + 2 sn'de bir yeniden deneme bekleniyordu (eskiden 10 pencerede bir): {mlx}"
    )


def test_KRITIK_sensorsuz_hatta_NACK_yoklamasi_BUTCEYI_tuketmez(kosum):
    """I2C1 (sahada sensörsüz) açılışta 6, sonra 2 sn'de bir 5 adres yoklar. ADDR beklemesi AF'yi (NACK) görmeden bütçe sonuna dek
    dönseydi her yoklama 40 000 SR1 okuması (~2 ms, ana döngü bekler) → 7 sn'de ~840 000; AF'de hemen çıkınca bir adres baytı (~1 800)."""
    k = kosum["acilista_yok"]
    say = {m.group(1): int(m.group(2)) for s in k["ham"] if (m := re.match(r"SAYAC 0x([0-9A-F]{8}) (\d+)", s))}
    assert say, "koşum takımı erişim sayaçlarını basmadı"
    assert say.get("40005414", 0) < 200_000, (
        f"I2C1 SR1 {say.get('40005414')} kez okundu — NACK'te ADDR bütçe sonuna dek bekleniyor"
    )


def test_YAPISAL_yeniden_yoklamada_TAKILI_HAT_KURTARMASI_yoklamadan_ONCE():
    """Takılı SDA (yazılım reset'i / kablo oynarken işlem ortasında kalan köle — T2D-3) adres yoklamasını hep NACK'letir; kurtarma (9 SCL +
    STOP + SWRST) olmadan yeniden yoklama sensörü hiç bulamaz. Koşum takımı takılı hattı modellemez (T2D-3 ile aynı: kart davranışı
    tezgâhta ölçülür) → yapı: Y285 dalında `MAG_YENIDEN_KURTARMA_HER` kapılı `i2c_hat_kurtar`, `mag_adres_bul`dan ÖNCE."""
    from pathlib import Path

    from c_soyucu import c_soy

    kok = Path(__file__).resolve().parents[1]
    s = c_soy((kok / "firmware" / "stm32_pemf" / "Core" / "Src" / "pemf_sensor.c").read_text(encoding="utf-8"))
    g = s[s.index("static bool hat_ilerlet(") :]
    dal = g[g.index("case S_BOSTA:") : g.index("mag_ayar_zamanla(h);")]
    kurtarma, yoklama = dal.find("i2c_hat_kurtar(h)"), dal.find("mag_adres_bul(h)")
    assert 0 <= kurtarma < yoklama, "yeniden yoklama dalında takılı hat kurtarması YOK (ya da yoklamadan sonra)"
    assert re.search(r"%\s*MAG_YENIDEN_KURTARMA_HER\)\s*==\s*0U\)\s*\{\s*i2c_hat_kurtar\(h\)", dal), (
        "kurtarma seyrek kapıyla değil"
    )


def test_YAPISAL_firmware_surumu_v2_6_ve_yeniden_yoklama_ARALIGI():
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    s = (kok / "firmware" / "stm32_pemf" / "Core" / "Src" / "pemf_sensor.c").read_text(encoding="utf-8")
    m = (kok / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c").read_text(encoding="utf-8")
    assert re.search(r"#define MAG_YENIDEN_YOKLAMA_MS 2000U", s) and "DDS v2.6" in m
