# -*- coding: utf-8 -*-
# Author: mertaygn
"""SÜRÜŞ KİPİ UCU (`POST /api/coil/surus_kipi`) — DAVRANIŞSAL kapı.

===============================================================================
NEDEN VAR
===============================================================================
2026-09-11'de bipolar/unipolar kipi ÇALIŞMA ZAMANINDA seçilebilir oldu (arayüzde
düğme). Zincir uzun: arayüz → HTTP → `HardwareController` maskesi → 121 baytlık
paket → firmware `etkin = yetenek || istek` → ACK `K=` → canlı durum → arayüz.

Bu zincirde SESSİZ YANLIŞ İKİ yerden çıkar ve ikisi de hastaya yanlış doz verir:

1. **Yetenek tavanı delinirse.** Bobin 6-7 (yan duvarlar) sürücülerinde ikinci
   yarım köprü FİZİKSEL OLARAK YOK. Arayüz onlara "bipolar" diyebiliyorsa
   operatör ±B salınımı sanır, gerçekte 0…+B tek yönlü sürülür — ölçülen dozla
   kayda geçen doz AYRIŞIR.

2. **Bit↔bobin eşlemesi kayarsa.** Maske bit `i` → bobin `i+1`. Bir kaymada
   YANLIŞ BOBİN kip değiştirir; hiçbir hata mesajı çıkmaz, yalnız alan profili
   sessizce değişir.

Bu dosya ikisini de ÖLÇER. Sabit karşılaştırması değil: gerçek uçtan geçer,
gerçek maskeyi kurar, gerçek `hardware_controller` alanına bakar.
"""

from __future__ import annotations

import os
import queue

import pytest

os.environ.setdefault("PEMF_SIMULATE", "1")

from controllers.hardware_controller import HardwareController  # noqa: E402
from servers import live_state  # noqa: E402


class _FakeCore:
    def __init__(self):
        self._hw_send_queue = queue.Queue(maxsize=100)


@pytest.fixture
def hw():
    c = HardwareController(_FakeCore())
    c._keep_alive_stop.set()
    c._keep_alive_thread.join(timeout=2)
    yield c
    c.stop()


@pytest.fixture
def istemci(hw):
    """Gerçek FastAPI uygulaması, `state.hardware` sahte-çekirdekli kontrolcüye bağlı."""
    from fastapi.testclient import TestClient
    from servers import api_server

    eski = api_server.state.hardware
    api_server.state.hardware = hw
    try:
        with TestClient(api_server.app) as c:
            yield c
    finally:
        api_server.state.hardware = eski


# ============================================================================
# 1. YETENEK TAVANI — DELİNEMEZ
# ============================================================================


def test_KRITIK_bobin_6_7_ye_BIPOLAR_istemek_ETKIN_kipi_DEGISTIRMEZ(istemci):
    """⚠️ ASIL KAPI. MUTASYON: uçtaki `etkin = uygulanan | yetenek` → `etkin = uygulanan`
    yap → KIRMIZI.

    Sahadaki etki: arayüz bobin 6-7 için "BİP" gösterir, donanım unipolar sürer.
    Operatör ±B salınımı sandığı bir dozu kayda geçirir.
    """
    y = istemci.post("/api/coil/surus_kipi", json={"unipolar": [False] * 7})
    assert y.status_code == 200, y.text
    g = y.json()

    assert g["istek"] == [False] * 7, "istek KIRLETILDI — kullanicinin yazdigi ne ise o donmeli"
    # Bobin 6-7 → indeks 5-6.
    assert g["etkin"][5] is True and g["etkin"][6] is True, (
        f"bobin 6-7 ETKIN kipi {g['etkin'][5:]} — donanim yetenegi YOKKEN bipolar bildirildi"
    )
    assert g["etkin"][:5] == [False] * 5, "bobin 1-5 bipolar istendi ama etkin kip unipolar cikti"
    assert g["maske"] == 0x60, f"etkin maske {g['maske']:#04x} != 0x60 (bit5|bit6 = bobin 6,7)"


def test_KRITIK_yetenek_tavani_CANLI_DURUMDAN_okunur_SABIT_DEGIL(istemci, monkeypatch):
    """Tavan `bipolarYetenek` alanından gelmeli, uca gömülü bir `id >= 6` kuralından değil.

    MUTASYON: uçtaki `_live_state[...]["bipolarYetenek"]` okumasını `idx >= 5` sabitiyle
    değiştir → KIRMIZI (bu test yeteneği bobin 3'e taşır).

    Sahadaki etki: sürücü kartı değişip bobin 6-7 bipolar olabilir hâle geldiğinde
    (ya da başka bir bobin tek-yönlüye düştüğünde) arayüz GERÇEĞİ göstermez.
    """
    with live_state._live_state_lock:
        eski = [live_state._live_state["coils"][i].get("bipolarYetenek") for i in range(7)]
        # Yeteneği TERSİNE çevir: yalnız bobin 3 tek-yönlü olsun.
        for i in range(7):
            live_state._live_state["coils"][i]["bipolarYetenek"] = i != 2
    try:
        g = istemci.post("/api/coil/surus_kipi", json={"unipolar": [False] * 7}).json()
        assert g["etkin"][2] is True, "yetenegi olmayan bobin 3 bipolar bildirildi"
        assert g["etkin"][5] is False and g["etkin"][6] is False, (
            "bobin 6-7 yetenegi ACILDI ama uc hala SABIT kurala gore unipolar bildiriyor"
        )
    finally:
        with live_state._live_state_lock:
            for i in range(7):
                live_state._live_state["coils"][i]["bipolarYetenek"] = eski[i]


# ============================================================================
# 2. BİT ↔ BOBİN EŞLEMESİ
# ============================================================================


def test_KRITIK_maske_biti_DOGRU_bobine_dusuyor(istemci, hw):
    """Her bobin TEK BAŞINA işaretlenir ve kontrolcüdeki maskede o bit aranır.

    Hepsini birden işaretlemek kaymayı GÖRMEZ — bu testin ayırt ediciliği tam olarak
    tek-tek gitmesinden gelir.

    MUTASYON: uçtaki `maske |= 1 << i` → `1 << (i + 1)` → KIRMIZI.
    """
    for bobin in range(1, 8):
        dizi = [False] * 7
        dizi[bobin - 1] = True
        istemci.post("/api/coil/surus_kipi", json={"unipolar": dizi})
        istek_maskesi = hw._unipolar_maskesi
        assert istek_maskesi == (1 << (bobin - 1)), (
            f"bobin {bobin} isaretlendi, kontrolcu maskesi {istek_maskesi:#04x} "
            f"!= {1 << (bobin - 1):#04x} -> bit<->bobin eslemesi KAYMIS"
        )


def test_KRITIK_paketteki_kip_alani_ISTEK_maskesini_tasiyor(hw):
    """Maske gerçekten 121 baytlık pakete giriyor mu — uçtan sonraki HALKA.

    MUTASYON: `_send_stm_manual_update` içindeki `_kip`i `0` sabitine çevir → KIRMIZI.
    """
    import struct

    from utils.stm32_transport import STM_PAKET_BOYU, STM_PAKET_FMT

    hw.surus_kipi_ayarla(0x2A)
    while True:
        try:
            hw.core._hw_send_queue.get_nowait()
        except queue.Empty:
            break
    hw._send_stm_manual_update()
    pkt = hw.core._hw_send_queue.get_nowait()[0]
    assert len(pkt) == STM_PAKET_BOYU, f"paket {len(pkt)} bayt != {STM_PAKET_BOYU}"
    alanlar = struct.unpack(STM_PAKET_FMT, pkt[:-4])
    assert alanlar[-1] == 0x2A, f"pakete giden kip {alanlar[-1]:#04x} != 0x2a"


# ============================================================================
# 3. GİRDİ DOĞRULAMA
# ============================================================================


@pytest.mark.parametrize("uzunluk", [0, 5, 6, 8])
def test_YANLIS_uzunlukta_dizi_REDDEDILIR(istemci, uzunluk):
    """Kısa dizi sessizce sıfır-dolgu edilirse eksik bobinler kipini KAYBEDER.

    MUTASYON: uzunluk kontrolünü sil → KIRMIZI (5 elemanlı dizi 200 döner).
    """
    y = istemci.post("/api/coil/surus_kipi", json={"unipolar": [False] * uzunluk})
    assert y.status_code == 400, f"{uzunluk} elemanli dizi KABUL EDILDI (HTTP {y.status_code})"


def test_kontrolcu_YOKKEN_503(istemci):
    """Donanım kontrolcüsü yokken "başarılı" dönmek, 2026-09-11 saha arızasının ta kendisi."""
    from servers import api_server

    eski = api_server.state.hardware
    api_server.state.hardware = None
    try:
        y = istemci.post("/api/coil/surus_kipi", json={"unipolar": [False] * 7})
        assert y.status_code == 503, f"kontrolcu YOKKEN HTTP {y.status_code} dondu"
    finally:
        api_server.state.hardware = eski


# ============================================================================
# 4. CANLI DURUM — "BİLDİRMEDİ" ile "BİPOLAR" AYRI ŞEYLER
# ============================================================================


def test_KRITIK_firmware_bildirmediyse_alan_NONE_kalir():
    """⚠️ `coil_update` olayında `unipolar` anahtarı YOKSA alana DOKUNULMAMALI.

    `False` yazmak "bipolar DOĞRULANDI" demektir — oysa eski firmware `K=` alanını hiç
    göndermez. Arayüz o durumda kısa çizgi göstermeli, "BİP" değil.

    MUTASYON: api_server'daki `if "unipolar" in data:` kapısını kaldırıp
    `data.get("unipolar", False)` yap → KIRMIZI.
    """
    from servers import api_server

    with live_state._live_state_lock:
        eski = live_state._live_state["coils"][0].get("unipolar")
        live_state._live_state["coils"][0]["unipolar"] = None
    try:

        class _Olay:
            event_type = "hardware.stm.coil_update"
            data = {"coil_id": 1, "duty": 25.0, "freq": 50.0, "duration_min": 5, "running": True}

        api_server._handle_backend_event(_Olay())
        with live_state._live_state_lock:
            deger = live_state._live_state["coils"][0]["unipolar"]
        assert deger is None, f"firmware BILDIRMEDI ama alana {deger!r} yazildi -> uydurma kip"
    finally:
        with live_state._live_state_lock:
            live_state._live_state["coils"][0]["unipolar"] = eski


def test_KRITIK_ACK_bildirdiginde_alan_YAZILIR():
    """Karşıt kanıt: kapıyı "hiç yazma" diye geçmek mümkün olmasın."""
    from servers import api_server

    with live_state._live_state_lock:
        eski = live_state._live_state["coils"][5].get("unipolar")
        live_state._live_state["coils"][5]["unipolar"] = None
    try:

        class _Olay:
            event_type = "hardware.stm.coil_update"
            data = {"coil_id": 6, "duty": 25.0, "freq": 50.0, "duration_min": 5, "running": True, "unipolar": True}

        api_server._handle_backend_event(_Olay())
        with live_state._live_state_lock:
            deger = live_state._live_state["coils"][5]["unipolar"]
        assert deger is True, f"ACK unipolar=True bildirdi, canli durumda {deger!r}"
    finally:
        with live_state._live_state_lock:
            live_state._live_state["coils"][5]["unipolar"] = eski


# ============================================================================
# 5. UÇTAN UCA — firmware ACK satırından arayüz alanına
# ============================================================================


class _SahteCekirdek:
    """`_parse_stm_ok` yalnız `STM_COIL_COUNT` okur — tam bir HeadlessCore kurmaya gerek yok."""

    STM_COIL_COUNT = 7


def _ack_satiri(kip_maskesi: int | None) -> str:
    """Firmware'in GERÇEKTEN bastığı ACK biçimi (main.c `ack_etiket` + ` K=`).

    ⚠️ Elle kurgulanmış bir sözlük değil, KABLODAN GELEN METİN. Ayrıştırıcı ile firmware
    arasındaki biçim ayrışması ancak böyle yakalanır.
    """
    n = 7
    d = ",".join("25" for _ in range(n))
    p = ",".join("0" for _ in range(n))
    f = ",".join("50" for _ in range(n))
    t = ",".join("10" for _ in range(n))
    satir = f"-> STM_OK: D={d} P={p} F={f} T={t}"
    if kip_maskesi is not None:
        satir += f" K={kip_maskesi}"
    return satir


@pytest.mark.parametrize("maske,beklenen", [(0x60, [False] * 5 + [True, True]), (0x7F, [True] * 7)])
def test_KRITIK_ACK_satirindan_CANLI_DURUMA_uctan_uca(maske, beklenen):
    """⚠️ TAM ZİNCİR: UART metni → `_parse_stm_ok` → olay → `live_state` → arayüz alanı.

    Halkaların her biri ayrı ayrı test edilmişti; arada BİÇİM ayrışması olsa (ör. firmware
    `K=` yerine `KIP=` bassa, ya da ayrıştırıcı boşluk beklerken firmware virgül koysa)
    hepsi yeşil kalır ve arayüz kipi HİÇ göstermezdi.

    MUTASYON: `_parse_stm_ok`taki `K=` desenini `KIP=` yap → KIRMIZI.
    """
    import headless_core
    from servers import api_server

    with live_state._live_state_lock:
        eski = [live_state._live_state["coils"][i].get("unipolar") for i in range(7)]
        for i in range(7):
            live_state._live_state["coils"][i]["unipolar"] = None
    try:
        guncellemeler = headless_core.HeadlessCore._parse_stm_ok(_SahteCekirdek(), _ack_satiri(maske))
        assert len(guncellemeler) == 7, f"ACK satirindan {len(guncellemeler)} bobin cozuldu (7 bekleniyordu)"
        for g in guncellemeler:
            api_server._handle_backend_event(type("O", (), {"event_type": "hardware.stm.coil_update", "data": g})())
        with live_state._live_state_lock:
            gercek = [live_state._live_state["coils"][i]["unipolar"] for i in range(7)]
        assert gercek == beklenen, f"maske {maske:#04x} -> canli durum {gercek}, beklenen {beklenen}"
    finally:
        with live_state._live_state_lock:
            for i in range(7):
                live_state._live_state["coils"][i]["unipolar"] = eski[i]


def test_KRITIK_ESKI_firmware_ACKinde_kip_alani_YOK_sayilir():
    """`K=` basmayan bir kart, canlı durumu KİRLETMEMELİ (kısa çizgi kalmalı)."""
    import headless_core

    guncellemeler = headless_core.HeadlessCore._parse_stm_ok(_SahteCekirdek(), _ack_satiri(None))
    assert guncellemeler, "eski ACK satiri hic cozulemedi -> geriye uyumluluk KIRILDI"
    assert all("unipolar" not in g for g in guncellemeler), (
        "eski firmware `K=` basmiyor ama guncellemeye 'unipolar' anahtari KONDU -> uydurma kip"
    )


def test_KRITIK_STM_kopunca_ETKIN_kip_UNUTULUR():
    """Kart gidince "kartın uyguladığı kip" artık DOĞRULANMIŞ değildir.

    Eski değeri tutmak, yeniden bağlanan — belki yeniden programlanmış, belki başka —
    bir kart için doğrulanmamış bir kipi doğrulanmış gibi göstermek olur.

    MUTASYON: `_sync_stm_coils_locked` içindeki `coil["unipolar"] = None` satırını sil
    → KIRMIZI.
    """
    with live_state._live_state_lock:
        eski_stm = live_state._live_state["stm"]
        eski = [live_state._live_state["coils"][i].get("unipolar") for i in range(7)]
        for i in range(7):
            live_state._live_state["coils"][i]["unipolar"] = True
    try:
        live_state.update_live_stm_status(False)
        with live_state._live_state_lock:
            kalan = [live_state._live_state["coils"][i]["unipolar"] for i in range(7)]
        assert kalan == [None] * 7, f"STM koptu ama etkin kip TUTULDU: {kalan}"
    finally:
        with live_state._live_state_lock:
            live_state._live_state["stm"] = eski_stm
            for i in range(7):
                live_state._live_state["coils"][i]["unipolar"] = eski[i]


# ============================================================================
# 6. İKİ KAYNAK YOK — arayüzün "yetenek"i firmware maskesiyle AYNI olmalı
# ============================================================================


def test_KRITIK_bipolarYetenek_FIRMWARE_maskesiyle_AYNI():
    """⚠️ Yetenek İKİ yerde yazılı: firmware `PEMF_BOBIN_UNIPOLAR_MASKESI` ve backend
    `bipolarYetenek`. Ayrışırlarsa arayüz basılabilir ama uygulanmayan bir düğme gösterir
    (ya da uygulanabilir bir düğmeyi gizler) — ikisi de operatöre yalan söyler.

    Bu depoda tekrar eden sınıf: "sihirli sayı ikinci bir yere kopyalanmış". Kapı, ikisini
    ayrı ayrı doğru sanıp BİRLİKTE yanlış olmalarını engeller.

    MUTASYON: firmware maskesini `0x00` ya da `0x70` yap → KIRMIZI.
    """
    import re
    from pathlib import Path as _P

    surus_h = _P(__file__).resolve().parents[1] / "firmware" / "stm32_pemf" / "Core" / "Inc" / "pemf_surus.h"
    if not surus_h.exists():
        pytest.skip("firmware kaynagi yok")
    m = re.search(
        r"#define\s+PEMF_BOBIN_UNIPOLAR_MASKESI\s+0x([0-9A-Fa-f]+)U?",
        surus_h.read_text(encoding="utf-8", errors="replace"),
    )
    assert m, "PEMF_BOBIN_UNIPOLAR_MASKESI bulunamadi"
    maske = int(m.group(1), 16)

    with live_state._live_state_lock:
        backend = [bool(live_state._live_state["coils"][i].get("bipolarYetenek")) for i in range(7)]
    firmware = [not bool((maske >> i) & 1) for i in range(7)]
    assert backend == firmware, (
        f"yetenek AYRISTI -> backend {backend}, firmware maskesi 0x{maske:02X} {firmware}. "
        "Arayuz uygulanmayan bir dugme gosterir (ya da uygulanabilir olani gizler)."
    )
