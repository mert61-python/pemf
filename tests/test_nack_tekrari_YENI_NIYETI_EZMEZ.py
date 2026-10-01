# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.72 · B-1.17 — STM_NACK yeniden oynatması daha YENİ bir niyeti (STOP dahil) EZMEZ; kalıcı NACK'te SINIRLI.

ÖLÇÜLEN KUSUR (plan v-A06): NACK gelince okuyucu iş parçacığı porta son yazılan paketi kuyruğa KENDİSİ
koyuyordu. Gönderici meşgulken araya STOP girdiyse sıra [STOP, eski RUN] oluyor → bobin acil durdurmadan
SONRA eski duty ile yeniden enerjileniyordu (son paket RUN; bir sonraki keep-alive'a dek ~0,48 sn). NACK STOP'tan
ÖNCE gelip ikisi birlikte beklerse de eski RUN, STOP'tan sonra (kuyruğa verildikten sonra) porta yazılıyordu.
Kalıcı NACK'te tekrar SINIRSIZDI (1,5 sn'de 96 yazım). Mevcut yaş sınırı (0,75 sn) keep-alive turundan (0,5 sn)
geniş olduğu için bunu kapatmıyordu.

Kapı GERÇEK `HeadlessCore` (HWSender + okuyucu + GERÇEK `_handle_stm_line` + GERÇEK `retry_last_payload`) ve
GERÇEK `HardwareController.stop_all_coils` ile koşar. Sahte olan: seri taşıma (porta yazılan her paket zaman damgalı
kaydedilir; firmware satırları bir kuyruktan okunur; "gönderici meşgul" bir yazımın Event'te TUTULMASIYLA kurulur —
zamanlamaya bırakılmaz), DB açılışları, `socket`, olay veriyolu. Paketler firmware aynasıyla çözülür.

Ö.4-Y8: STOP'un yeniden gönderimi AZALTILMAZ — karşıt kol kalıcı NACK'te STOP'un sınırsız tekrarını pinler.
"""

from __future__ import annotations

import queue
import socket as _gercek_socket
import threading
import time
import types

import pytest

NACK = b"-> STM_NACK: CRC hatasi\n"


def _bekle(kosul, sure=5.0):
    son = time.monotonic() + sure
    while time.monotonic() < son and not kosul():
        time.sleep(0.005)
    return kosul()


def _stop_mu(paket: bytes) -> bool:
    from kayitci_donanim import paket_coz

    return all(x == 0.0 for x in paket_coz(paket)[0])


@pytest.fixture
def aparat(monkeypatch, tmp_path):
    import headless_core as hcm
    from controllers.hardware_controller import HardwareController
    from servers import live_state as _ls

    d = types.SimpleNamespace(
        acilan=[],
        yazilan=[],
        satirlar=queue.Queue(),
        surekli_nack=False,
        tut=False,
        tutuluyor=threading.Event(),
        birak=threading.Event(),
    )

    class _Conn:
        def __init__(self, ad: str):
            self.ad = ad
            self.port = "COM_TEST"
            self.is_open = True

        def readline(self):
            try:
                return d.satirlar.get(timeout=0.02)
            except queue.Empty:
                return b""

        def write(self, b):
            d.yazilan.append((time.perf_counter(), bytes(b)))
            if d.surekli_nack:
                d.satirlar.put(NACK)
            if d.tut:  # gönderici bu yazımda MEŞGUL kalır (Event'le — zamanlama değil)
                d.tut = False
                d.tutuluyor.set()
                d.birak.wait(10)

        def close(self):
            self.is_open = False

    class _Tasima:
        def __init__(self, *a, **k):
            pass

        def open_and_handshake(self, stop_event=None, on_line=None):
            if any(c.is_open for c in d.acilan):
                return None
            c = _Conn(f"C{len(d.acilan)}")
            d.acilan.append(c)
            return types.SimpleNamespace(serial=c)

        def close_serial(self, c):
            c.close()

        def port_hala_var(self, _port):
            return True

    def _soket_yok(*_a, **_k):
        raise OSError("test: UDP soketi kurulmaz")

    monkeypatch.setattr(hcm, "Stm32SerialTransport", _Tasima)
    monkeypatch.setattr(
        hcm,
        "socket",
        types.SimpleNamespace(
            socket=_soket_yok,
            AF_INET=_gercek_socket.AF_INET,
            SOCK_DGRAM=_gercek_socket.SOCK_DGRAM,
            SOL_SOCKET=_gercek_socket.SOL_SOCKET,
            SO_BROADCAST=_gercek_socket.SO_BROADCAST,
        ),
    )
    monkeypatch.setattr(hcm, "get_patient_database", lambda *_a, **_k: object())
    monkeypatch.setattr(hcm, "get_session_manager", lambda *_a, **_k: object())
    core = hcm.HeadlessCore(
        tmp_path / "veri", start_headless_services=False, event_bus=types.SimpleNamespace(publish=lambda *a, **k: None)
    )
    with _ls._live_state_lock:
        eski_stm = _ls._live_state["stm"]
        _ls._live_state["stm"] = "online"
    hc = HardwareController(core)
    hc._keep_alive_stop.set()  # paketler yalnız test edilen çağrılardan gelsin
    hc._keep_alive_thread.join(timeout=2)
    try:
        assert _bekle(lambda: d.acilan and core.stm_is_connected), f"aparat: STM baglanmadi {d}"
        yield core, hc, d
    finally:
        d.surekli_nack = False
        d.birak.set()
        core._hw_sender_stop.set()
        core._hw_sender_thread.join(timeout=3)
        for c in d.acilan:
            c.close()
        hc.stop()
        with _ls._live_state_lock:
            _ls._live_state["stm"] = eski_stm


@pytest.mark.parametrize("sira", ["STOP_sonra_NACK", "NACK_sonra_STOP"])
def test_KRITIK_NACK_tekrari_STOPtan_SONRA_eski_RUNi_porta_YAZMAZ(aparat, sira):
    """Gönderici RUN'ı yazarken MEŞGUL; bu sırada STOP kuyruğa verilir ve RUN için NACK gelir (iki sırada da).
    İddia: `stop_all_coils` döndükten SONRA porta duty>0 paket YAZILMAZ ve son yazılan paket STOP'tur."""
    core, hc, d = aparat
    d.tut = True
    assert hc.update_coil(1, 100.0, 30.0, 0.0, 1, start=True) is True
    assert d.tutuluyor.wait(3), "aparat: gonderici RUN yaziminda tutulmadi"
    assert not _stop_mu(d.yazilan[-1][1]), "aparat: tutulan yazim RUN degil"
    if sira == "STOP_sonra_NACK":
        assert hc.stop_all_coils() is True
        t_stop = time.perf_counter()
        d.satirlar.put(NACK)
        assert _bekle(lambda: core._hw_send_queue.qsize() == 2, 3.0), (
            f"aparat: NACK islenmedi (kuyruk {core._hw_send_queue.qsize()})"
        )
    else:
        d.satirlar.put(NACK)
        assert _bekle(lambda: core._hw_send_queue.qsize() == 1, 3.0), (
            f"aparat: NACK islenmedi (kuyruk {core._hw_send_queue.qsize()})"
        )
        assert hc.stop_all_coils() is True
        t_stop = time.perf_counter()
        assert core._hw_send_queue.qsize() == 2, "aparat: STOP kuyruga girmedi"
    d.birak.set()
    assert _bekle(lambda: core._hw_send_queue.empty(), 3.0), "aparat: kuyruk bosalmadi"
    time.sleep(0.3)
    sonrasi = [b for ts, b in d.yazilan if ts > t_stop]
    assert sonrasi, "aparat: STOP'tan sonra hic yazim yok (STOP porta gitmedi)"
    run_sonrasi = [b for b in sonrasi if not _stop_mu(b)]
    assert not run_sonrasi, (
        f"{sira}: STOP kuyruga verildikten SONRA porta {len(run_sonrasi)} duty>0 paket YAZILDI — NACK tekrari "
        "eski RUN'i STOP'un ARDINDAN yeniden enerjiledi (E-stop sonrasi yeniden enerjileme)"
    )
    assert _stop_mu(sonrasi[-1]), "porta yazilan SON paket STOP degil"


def test_KARSIT_yeni_niyet_YOKKEN_NACKlenen_RUN_bir_kez_YENIDEN_yazilir(aparat):
    """Kapı "hiç oynatma"ya dönüşmesin: araya niyet girmediyse NACK'lenen RUN yeniden yazılır."""
    core, hc, d = aparat
    yazim_once = len(d.yazilan)
    assert hc.update_coil(1, 100.0, 30.0, 0.0, 1, start=True) is True
    assert _bekle(lambda: len(d.yazilan) == yazim_once + 1, 3.0), "aparat: RUN yazilmadi"
    d.satirlar.put(NACK)
    assert _bekle(lambda: len(d.yazilan) == yazim_once + 2, 3.0), "NACK'lenen RUN yeniden YAZILMADI (telafi yok)"
    assert d.yazilan[-1][1] == d.yazilan[-2][1], "yeniden yazilan paket NACK'lenen paket degil"


def test_KRITIK_kalici_NACKte_RUN_tekrari_SINIRLI(aparat):
    """Kart her pakete NACK dönüyor (kalıcı red). Eskiden her NACK yeni bir tekrar → sınırsız döngü.
    Ölçüt (plan): 1 sn içinde yeniden oynatma yazımı ≤ 2 (ilk yazım + en çok 2 tekrar)."""
    core, hc, d = aparat
    d.surekli_nack = True
    yazim_once = len(d.yazilan)
    assert hc.update_coil(1, 100.0, 30.0, 0.0, 1, start=True) is True
    time.sleep(1.0)
    run = [b for _, b in d.yazilan[yazim_once:] if not _stop_mu(b)]
    d.surekli_nack = False
    assert 1 <= len(run) <= 3, f"kalici NACK'te 1 sn'de {len(run)} RUN yazimi — tekrar SINIRSIZ (ilk + en cok 2)"


def test_KARSIT_kalici_NACKte_STOP_tekrari_AZALMAZ(aparat):
    """Ö.4-Y8: STOP'un yeniden gönderimi azaltılmaz — RUN'a konan sınır STOP'a UYGULANMAZ."""
    import headless_core as hcm

    core, hc, d = aparat
    d.surekli_nack = True
    yazim_once = len(d.yazilan)
    assert hc.stop_all_coils() is True
    time.sleep(0.5)
    stop = [b for _, b in d.yazilan[yazim_once:] if _stop_mu(b)]
    d.surekli_nack = False
    # Asgari PİNLİ (4): sınır sabiti mutasyonla düşürülürse kapının ölçütü de düşmesin.
    asgari = max(4, 1 + getattr(hcm, "_NACK_RUN_TEKRAR_SINIRI", 0) + 2)
    assert len(stop) >= asgari, (
        f"kalici NACK'te STOP yalniz {len(stop)} kez yazildi (>= {asgari} beklenir) — STOP tekrari AZALTILDI (Y8)"
    )


def test_KARSIT_NACKlenen_STOP_araya_YENI_NIYET_girse_de_YENIDEN_yazilir(aparat):
    """Ö.4-Y8: "daha yeni niyet" kuralı YALNIZ eski RUN içindir. Kart STOP'u reddettiyse STOP — araya yeni bir
    komut girse de — yeniden yazılır (durdurma kazanır; keep-alive güncel durumu sonra yeniden kurar)."""
    core, hc, d = aparat
    d.tut = True
    assert hc.stop_all_coils() is True
    assert d.tutuluyor.wait(3), "aparat: gonderici STOP yaziminda tutulmadi"
    assert _stop_mu(d.yazilan[-1][1]), "aparat: tutulan yazim STOP degil"
    assert hc.update_coil(1, 100.0, 30.0, 0.0, 1, start=True) is True  # yeni niyet kuyrukta
    d.satirlar.put(NACK)  # kart STOP'u reddetti
    assert _bekle(lambda: core._hw_send_queue.qsize() == 2, 3.0), "aparat: NACK islenmedi"
    d.birak.set()
    assert _bekle(lambda: core._hw_send_queue.empty(), 3.0), "aparat: kuyruk bosalmadi"
    time.sleep(0.3)
    stoplar = [b for _, b in d.yazilan if _stop_mu(b)]
    assert len(stoplar) >= 2, f"NACK'lenen STOP yeniden YAZILMADI ({len(stoplar)} STOP) — STOP tekrari azaldi (Y8)"
    assert _stop_mu(d.yazilan[-1][1]), "reddedilen STOP'un tekrari yeni komutun ARDINDAN yazilmadi"
