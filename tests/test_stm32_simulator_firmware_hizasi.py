# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.13 (B-10.267 · B-10.268) KAPISI — simülatör SEVK EDİLEN firmware'in ACK ve banner'ını basar.

ARIZA (DENETIM-10):
  B-10.267 — simülatörün ACK'i yalnız 5 bobin basıyordu ve `K=` (etkin sürüş kipi) alanı YOKTU.
    Firmware `NUM_COILS` (7) alan + ` K=<etkin maske>` basar (`main.c` ACK döngüsü). Simülatörle
    koşan ürün bobin 6-7 için `coil_update` almaz (onaysız/bayat görünür) ve kip göstergesi
    beslenmez → İG-5.3 / İG-6.1 ölçümleri simülatörle yapılırsa YANLIŞ hüküm çıkar.
  B-10.268 — banner "SYM-BIPOLAR" diyordu; firmware'in derlenen yetenek maskesi
    `PEMF_BOBIN_UNIPOLAR_MASKESI` (`pemf_surus.h`) 0x60 → firmware "KARMA uni=0x60" basar.

KAPI: ürünün GERÇEK paketi (`HardwareController`) simülatöre verilir, dönen ACK ürünün GERÇEK
ayrıştırıcısıyla (`HeadlessCore._parse_stm_ok`) çözülür: NUM_COILS kadar güncelleme ve her birinde
`unipolar` anahtarı; değer firmware kuralı `etkin = yetenek | istek`. Her bobine FARKLI
frekans/duty/faz/süre verilir ve ACK'in her alanı firmware ACK formülüyle (`main.c` ACK döngüsü)
bobin bobin karşılaştırılır → indis kayması görünür. Banner ürünün
`stm32_kimlik.banner_ayristir`'ı ile çözülür; kanal/kip/maske `pemf_surus.h`'ye eşit.
MUTASYON: `_send_ack`'te alan sayısını/indisi bozmak (M3) ya da banner'a "SYM-BIPOLAR" geri yazmak → KIRMIZI.
"""

from __future__ import annotations

import queue
import re
import socket
import struct
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sim = pytest.importorskip("tools.stm32_simulator", reason="simulator yok")
KOK = Path(__file__).resolve().parents[1]
BASLIK = KOK / "firmware" / "stm32_pemf" / "Core" / "Inc" / "pemf_surus.h"


def _firmware_yetenek_maskesi() -> int:
    m = re.search(r"#define\s+PEMF_BOBIN_UNIPOLAR_MASKESI\s+(0x[0-9A-Fa-f]+|\d+)U?", BASLIK.read_text(encoding="utf-8"))
    assert m, "pemf_surus.h'de PEMF_BOBIN_UNIPOLAR_MASKESI bulunamadı (çıpa kaymış)"
    return int(m.group(1), 0)


def _firmware_kip(maske: int, n: int) -> str:
    """`main.c` banner üçlüsünün AYNISI: 0 → SYM-BIPOLAR, hepsi → UNIPOLAR tek-bacak, aksi → KARMA."""
    if maske == 0:
        return "SYM-BIPOLAR"
    if maske == (1 << n) - 1:
        return "UNIPOLAR tek-bacak"
    return "KARMA"


def _firmware_ack_duty(duty: float) -> int:
    """`main.c` ACK: `(long)(parsed.coil[i].duty * 100.0f)` — float32 çarpım, sıfıra doğru kırpma."""
    return int(struct.unpack("<f", struct.pack("<f", duty * 100.0))[0])


#: bobin → (frekans Hz, duty %, faz °, süre dk). HEPSİ FARKLI: `_send_ack`'te bir indis kayarsa
#: (ör. `phase[0]`) başka bobinin değeri görünür. Duty'ler float32/double kırpmasında AYNI sonucu
#: veren değerlerden seçildi (bu testin konusu alan sayısı/indis; yuvarlama ayrı ölçülür).
_DEGERLER = {
    1: (100.0, 5.0, 0.0, 1),
    2: (110.0, 10.0, 30.0, 2),
    3: (120.0, 15.0, 60.0, 3),
    4: (130.0, 20.0, 90.0, 4),
    5: (140.0, 25.0, 120.0, 5),
    6: (150.0, 30.0, 150.0, 6),
    7: (160.0, 18.0, 180.0, 7),
}
#: Sürüş kipi İSTEĞİ: bobin 2 unipolar (yetenek bipolar → istek etkili olmalı) + bit 7 (8. bobin YOK;
#: firmware yalnız `NUM_COILS` biti sayar → ACK'te görünmemeli).
_ISTEK = 0x82


class _SahteCore:
    def __init__(self):
        self._hw_send_queue = queue.Queue(maxsize=100)


@pytest.fixture
def hw():
    from controllers.hardware_controller import HardwareController
    from servers import live_state as _ls

    with _ls._live_state_lock:
        _eski = _ls._live_state["stm"]
        _ls._live_state["stm"] = "online"
    c = HardwareController(_SahteCore())
    c._keep_alive_stop.set()
    c._keep_alive_thread.join(timeout=2)
    try:
        yield c
    finally:
        c.stop()
        with _ls._live_state_lock:
            _ls._live_state["stm"] = _eski


def _satirlar(sok: socket.socket, onek: str, adet: int, sure: float) -> list[str]:
    tampon, bulunan = b"", []
    bitis = time.monotonic() + sure
    while time.monotonic() < bitis and len(bulunan) < adet:
        sok.settimeout(max(0.05, bitis - time.monotonic()))
        try:
            parca = sok.recv(4096)
        except socket.timeout:
            break
        if not parca:
            break
        tampon += parca
        *tam, tampon = tampon.split(b"\n")
        bulunan += [s.decode("utf-8", "replace").strip() for s in tam if s.decode("utf-8", "replace").startswith(onek)]
    return bulunan


def _sim_bagla(monkeypatch):
    monkeypatch.setattr(sim, "READY_DELAY_S", 0.0)
    monkeypatch.setattr(sim.Stm32SimClient, "_watchdog_worker", lambda self: None)
    monkeypatch.setattr(sim.Stm32SimClient, "_duration_worker", lambda self: None)
    istemci, karsi = socket.socketpair()
    threading.Thread(target=sim.Stm32SimClient(karsi, ("socketpair", 0)).run, name="d0o13-sim", daemon=True).start()
    return istemci, karsi


def test_KRITIK_simulator_ACK_NUM_COILS_alan_ve_etkin_KIP_basar(hw, monkeypatch):
    from headless_core import HeadlessCore

    n = sim.NUM_COILS
    assert len(_DEGERLER) == n, "kapı her bobine değer vermeli"
    yetenek = _firmware_yetenek_maskesi()
    istemci, karsi = _sim_bagla(monkeypatch)
    try:
        hw.surus_kipi_ayarla(_ISTEK)
        for bobin, (frekans, duty_yuzde, faz, sure_dk) in _DEGERLER.items():
            assert hw.update_coil(bobin, frekans, duty_yuzde, faz, sure_dk)
        paket = None
        while not hw.core._hw_send_queue.empty():
            paket = bytes(hw.core._hw_send_queue.get_nowait()[0])
        cozum, sebep = sim.decode_packet(paket)
        assert cozum is not None, f"ürün paketi reddedildi: {sebep}"
        duty, faz, frek, sure, _ref_ms, istek = cozum
        assert istek == _ISTEK, f"ürün kip isteğini pakete koymadı ({istek:#04x}) — kapı anlamsız"
        istemci.sendall(paket)
        ack = _satirlar(istemci, "-> STM_OK:", 1, 3.0)
        assert ack, "simülatör ACK dönmedi (D0Ö.12 önkoşulu)"
        guncellemeler = HeadlessCore._parse_stm_ok(SimpleNamespace(STM_COIL_COUNT=HeadlessCore.STM_COIL_COUNT), ack[0])
        assert len(guncellemeler) == n, f"ACK {len(guncellemeler)} bobin bildirdi, firmware {n} basar: {ack[0]!r}"
        eksik_kip = [g["coil_id"] for g in guncellemeler if "unipolar" not in g]
        assert not eksik_kip, f"ACK'te K= (etkin kip) alanı YOK → bobin {eksik_kip} için kip bildirilmiyor: {ack[0]!r}"
        # Alan alan, bobin bobin: firmware'in bu pakete basacağı ACK (main.c ACK döngüsü).
        beklenen_alan = {i + 1: (_firmware_ack_duty(duty[i]), int(faz[i]), int(frek[i]), sure[i]) for i in range(n)}
        gelen_alan = {
            g["coil_id"]: (int(g["duty"]), int(g["phase"]), int(g["freq"]), g["duration_min"]) for g in guncellemeler
        }
        assert gelen_alan == beklenen_alan, f"ACK alanları firmware'in basacağıyla uyuşmuyor: {ack[0]!r}"
        # Firmware `K=` ETKİN maskeyi yalnız NUM_COILS bit üzerinden basar: etkin = yetenek | istek.
        etkin = (yetenek | istek) & ((1 << n) - 1)
        k = re.search(r"[,\s]K=(\d+)", ack[0])
        assert k and int(k.group(1)) == etkin, f"K= firmware'in etkin maskesi ({etkin}) değil: {ack[0]!r}"
        beklenen = {g["coil_id"]: bool((etkin >> (g["coil_id"] - 1)) & 1) for g in guncellemeler}
        assert {g["coil_id"]: g["unipolar"] for g in guncellemeler} == beklenen, (
            f"etkin kip firmware kuralı (yetenek|istek = {etkin:#04x}) ile uyuşmuyor: {ack[0]!r}"
        )
    finally:
        istemci.close()
        karsi.close()


def test_KRITIK_simulator_banner_FIRMWARE_maskesinden_turer(monkeypatch):
    from utils.stm32_kimlik import banner_ayristir

    yetenek = _firmware_yetenek_maskesi()
    istemci, karsi = _sim_bagla(monkeypatch)
    try:
        banner = _satirlar(istemci, "-> STM_READY:", 1, 3.0)
        assert banner, "simülatör banner basmadı"
        kimlik = banner_ayristir(banner[0])
        assert kimlik is not None, f"ürün banner'ı ayrıştıramadı: {banner[0]!r}"
        assert kimlik.kanal == sim.NUM_COILS, banner[0]
        assert kimlik.maske == yetenek, f"banner maskesi {kimlik.maske} != firmware {yetenek:#04x}: {banner[0]!r}"
        assert kimlik.kip == _firmware_kip(yetenek, sim.NUM_COILS), f"banner kipi firmware'den türemiyor: {banner[0]!r}"
    finally:
        istemci.close()
        karsi.close()
