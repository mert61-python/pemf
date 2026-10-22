# Author: mertaygn, cglrgrkn
"""TD1 · Y68 — firmware KİMLİK SORGUSU ve banner'da PROTOKOL REVİZYONU, GERÇEK firmware ile (ana makine döngü koşum takımı).

GERÇEK `main.c` + GERÇEK HAL 1.8.5 MSVC'de koşar (`tests/firmware_dongu_aparat.py`; USART3 bayt süresi BRR'den). Ölçülen:
  * banner sürümden SONRA `proto=<PEMF_PROTOKOL_REV> pkt=<BINARY_PKT_SIZE>` basar; backend ayrıştırıcısı paket boyunu
    `STM_PAKET_BOYU` ile AYNI okur (120 / 121 baytlık kartlar artık ayırt edilir — tezgâh 2026-10-14: iki imaj AYNI banner);
  * 0xA5 0x5A 'I' 'D' çerçevesine `-> STM_ID: <banner gövdesi>` döner (sürüm · kanal · kip · maske · proto · pkt);
  * sorgu PWM'i BAŞLATMAZ, NACK üretmez, READY pingini kesmez (yalnız kimlik satırı);
  * yarım sorgudan sonra gelen 0xAA (komut paketi) KAÇIRILMAZ — paket STM_OK alır.
TABAN (TD1 öncesi `main.c`, aynı RX makinesi = saha imajının RX makinesi): sorguya YANIT YOK ve NACK YOK → eski kartta
güvenli (backend yanıt yokluğunu "eski kart" sayıp paket kabul / red kanıtına düşer).
⚠️ TEZGÂH-2: gerçek UART'ta kimlik yanıtı ve banner.
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="ana döngü koşum takımı Windows VEH'e dayanır")

SORGU = "a55a4944"
T_SORGU_US = 2_500_000


def _sifir_paket() -> bytes:
    from utils.stm32_transport import build_stm32_zero_duty_packet

    return build_stm32_zero_duty_packet(100.0)


def _senaryo(sure_us: int, paketler: list[tuple[int, str]]) -> str:
    s = [f"SURE_US {sure_us}", "ERISIM_NS 50", "GETTICK_NS 1000"]
    s += [f"PAKET {t} {h}" for t, h in paketler]
    return "\n".join(s) + "\n"


@pytest.fixture(scope="module")
def kosum(tmp_path_factory):
    import firmware_dongu_aparat as da

    dizin = tmp_path_factory.mktemp("y68")
    exe = da.derle(dizin)
    yarim_sonra_paket = (T_SORGU_US + 600_000, "a5" + _sifir_paket().hex())  # 0xA5 sonra 0xAA55… → paket önceliği
    sonuclar = {
        "sorgu": da.kos(exe, _senaryo(5_000_000, [(T_SORGU_US, SORGU)]), dizin, "sorgu"),
        "yarim": da.kos(exe, _senaryo(4_000_000, [yarim_sonra_paket]), dizin, "yarim"),
    }
    return sonuclar


def _satirlar(k: dict, onek: str) -> list[tuple[int, str]]:
    return [(b, m.strip()) for b, _e, m in k["satirlar"] if onek in m]


def test_KRITIK_banner_PROTOKOL_ve_PAKET_BOYU_basar_backend_ayni_okur(kosum):
    from utils.stm32_kimlik import banner_ayristir, firmware_surumu, uyum_denetle
    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI, STM_PAKET_BOYU, STM_PROTOKOL_REV

    ready = _satirlar(kosum["sorgu"], "STM_READY")
    assert ready, "banner basılmadı"
    k = banner_ayristir(ready[0][1])
    assert k is not None and (k.protokol, k.paket_boyu) == (STM_PROTOKOL_REV, STM_PAKET_BOYU), ready[0][1]
    from test_firmware_SURUM_banner_ve_UYUM_VARLIGI_D1120 import KAYNAK_SURUM

    assert firmware_surumu(k.surum) == KAYNAK_SURUM, f"sürüm ilk sırada değil (O-1.3): {ready[0][1]!r}"
    assert uyum_denetle(k, STM_PAKET_BOBIN_SAYISI)[0] is True


def test_KRITIK_kimlik_sorgusu_STM_ID_ile_yanitlanir_govde_BANNERDAN(kosum):
    from utils.stm32_kimlik import kimlik_yaniti_ayristir
    from utils.stm32_transport import STM_PAKET_BOYU, STM_PROTOKOL_REV

    kimlik = _satirlar(kosum["sorgu"], "STM_ID")
    assert len(kimlik) == 1, f"kimlik yanıtı {len(kimlik)} kez: {kimlik}"
    t, satir = kimlik[0]
    assert T_SORGU_US <= t < T_SORGU_US + 50_000, f"yanıt {t - T_SORGU_US} µs sonra"
    k = kimlik_yaniti_ayristir(satir)
    assert k is not None and (k.protokol, k.paket_boyu, k.kanal, k.maske) == (STM_PROTOKOL_REV, STM_PAKET_BOYU, 7, 0x60)
    ready = _satirlar(kosum["sorgu"], "STM_READY")[0][1]
    govde = ready.split("STM_READY:", 1)[1].split(" Waiting", 1)[0]
    assert satir.split("STM_ID:", 1)[1] == govde, "kimlik gövdesi banner'dan TÜREMİYOR (iki kaynak)"


def test_KRITIK_sorgu_PWMi_baslatmaz_NACK_uretmez_READY_pingi_SURER(kosum):
    k = kosum["sorgu"]
    assert not _satirlar(k, "STM_NACK"), _satirlar(k, "STM_NACK")
    assert not _satirlar(k, "STM_OK"), "sorgu paket gibi işlendi"
    assert all(m == 0 for _t, m in k["aktif"]), f"sorgu bobin çıkışı açtı: {k['aktif']}"
    ping_sonra = [t for t, _s in _satirlar(k, "STM_READY") if t > T_SORGU_US]
    assert ping_sonra, "sorgudan sonra READY pingi kesildi (g_pwm_started değişti)"


def test_KARSIT_yarim_sorgudan_sonra_gelen_PAKET_kacirilmaz(kosum):
    k = kosum["yarim"]
    assert _satirlar(k, "STM_OK"), "0xA5'ten sonra gelen geçerli paket kaçırıldı (paket önceliği yok)"
    assert not _satirlar(k, "STM_ID") and not _satirlar(k, "STM_NACK")
