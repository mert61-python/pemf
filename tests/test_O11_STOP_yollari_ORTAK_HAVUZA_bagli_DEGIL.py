# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""O-1.1 (1-F inceleme §22 #1 · Ö.4-Y8) — STOP yolları olay döngüsünün ORTAK iş parçacığı havuzlarına BAĞLI DEĞİL.

ÖLÇÜLEN KUSUR (1-G önce-kırmızı, `f65402b`): ACİL DURDUR ucu `_emergency_stop_all`'ı `await asyncio.to_thread(...)` ile
olay döngüsünün ORTAK varsayılan havuzunda (`min(32, cpu+4)` işçi) koşturuyordu. Havuzu asılı G/Ç ile tüketen her
`to_thread` (asılı diskte DB yazımları — 1-F incelemesinde 60 sn bekleyen denetim izi yazımı ölçüldü) ACİL DURDUR'u
SIRAYA sokuyordu: STOP porta GİTMİYOR, yanıt dönmüyordu; istemci vazgeçince sıradaki iş İPTAL edilip STOP HİÇ
gitmiyordu. Aynı bağımlılık seans durdurmada (`_stop_session_coils` / `_seanssiz_durdur`), mandallıyken 0 Hz
isteğinde, AI Pro `/frame` hedef-kaybı STOP'unda, ESP bobin STOP yayınında (tekil + toplu) ve eski `stop_all_coils`
yanıtında vardı. AI Pro durdurma ucu `/api/ai/pro/stop` ise iki kez bekliyordu: yönlendiricinin `jeton_gate`
bağımlılığında (serbest uç kararı bile `to_thread`'de) ve eşzamanlı (`def`) uç olarak anyio'nun ORTAK iş parçacığı
sınırlayıcısında (40).

SÖZLEŞME: iki ortak havuz da (asyncio varsayılan yürütücüsü + anyio varsayılan sınırlayıcısı) asılı işlerle DOLUYKEN
her STOP yolu < 1 sn'de STOP'u PORTA yazar (ESP yolunda yayını yapar) ve yanıtını döner — ≥ 30 deneme. Ölçüt HTTP
kodu değil PORTA YAZILAN BAYTLAR (firmware aynasıyla çözülür): GERÇEK `HeadlessCore` (yalnız DB açılışları sahte;
HWSender GERÇEK) + GERÇEK `HardwareController` + GERÇEK uçlar; TEK olay döngüsü (httpx ASGITransport + asyncio.run —
TestClient her istekte yeni döngü açar, ortak havuzu ölçemez). Sahte olan: tek erişimli seri taşıma (porta yazılan her
paket zaman damgalı kaydedilir), `_mqtt_publish` (kayıtçı), bildirim/WS yayını ve bulut aynası.
Ek kol: AI Pro durdurma STOP'u, kamerayı bırakan önizleme `join`'inden (6 sn'ye dek) ÖNCE porta gider.
"""

from __future__ import annotations

import asyncio
import socket as _gercek_socket
import threading
import time
import types

import pytest

DENEME = 30
SINIR_S = 1.0  # sözleşme: STOP porta ve yanıt < 1 sn
BEKLEME_S = SINIR_S + 1.0  # aparat: yanıtı en çok bu kadar bekle (kırmızıda deneme süresi)


def _bekle(kosul, sure=5.0):
    son = time.monotonic() + sure
    while time.monotonic() < son and not kosul():
        time.sleep(0.01)
    return kosul()


def _stop_mu(paket: bytes) -> bool:
    """Firmware aynasıyla çözülen paketin TÜM bobin duty'leri 0 mı (NACK'lenecek paket → AssertionError)."""
    from kayitci_donanim import paket_coz

    return all(x == 0.0 for x in paket_coz(paket)[0])


@pytest.fixture
def aparat(monkeypatch, tmp_path):
    import headless_core as hcm
    from controllers.hardware_controller import HardwareController
    from servers import ai_router as air
    from servers import api_server as api
    from servers import live_state as _ls
    from utils import estop_mandali

    d = types.SimpleNamespace(acilan=[], yazilan=[], yayin=[], bildirim=[])

    class _Conn:
        def __init__(self, ad: str):
            self.ad = ad
            self.port = "COM_TEST"
            self.is_open = True

        def readline(self):
            time.sleep(0.02)
            return b""

        def write(self, b):
            d.yazilan.append((time.perf_counter(), bytes(b)))

        def close(self):
            self.is_open = False

    class _Tasima:
        def __init__(self, *a, **k):
            pass

        def open_and_handshake(self, stop_event=None, on_line=None):
            if any(c.is_open for c in d.acilan):
                return None  # TEK ERİŞİM: önceki tutamak kapanmadan port açılamaz (Windows COM gibi)
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
    monkeypatch.setattr(hcm, "_PORT_CHECK_S", 0.05)
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
    bus = types.SimpleNamespace(publish=lambda *_a, **_k: None)
    core = hcm.HeadlessCore(tmp_path / "veri", start_headless_services=False, event_bus=bus)
    with _ls._live_state_lock:
        eski_stm = _ls._live_state["stm"]
        _ls._live_state["stm"] = "online"
    hc = HardwareController(core)
    hc._keep_alive_stop.set()  # paketler yalnız test edilen çağrılardan gelsin
    hc._keep_alive_thread.join(timeout=2)

    def _yayin(topic, payload):
        d.yayin.append((time.perf_counter(), topic, dict(payload)))
        return True

    monkeypatch.setattr(api.state, "hardware", hc)
    monkeypatch.setattr(api.state, "core", core)
    monkeypatch.setattr(api, "_mqtt_publish", _yayin)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api, "_estop_ack_watch", lambda *a, **k: None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(_ls, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info", *a, **k: d.bildirim.append((t, m)))
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 0)
    for ad in ("_ai_loop_active", "_ai_owner_client", "_ai_hedef_modeli", "_ai_hazirlik_active", "_ai_hazirlik_thread"):
        monkeypatch.setattr(air, ad, getattr(air, ad))
    with api._session_lock:
        eski_seans = dict(api._active_session)
        api._active_session.clear()
    o = types.SimpleNamespace(api=api, air=air, mandal=estop_mandali, core=core, hc=hc, d=d)
    try:
        assert _bekle(lambda: bool(d.acilan) and core.stm_is_connected), f"aparat: STM baglanmadi {d}"
        yield o
    finally:
        core._hw_sender_stop.set()
        core._hw_sender_thread.join(timeout=3)
        for c in d.acilan:
            c.close()
        hc.stop()
        with _ls._live_state_lock:
            _ls._live_state["stm"] = eski_stm
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski_seans)
        estop_mandali.sifirla("test")


# ── Senaryolar: (hazırlık, istek, beklenen yanıt kodu, ölçüt) ─────────────────────────────────────────────────────────


def _bobin1_sur(o) -> None:
    """STOP'tan ÖNCE bobin 1 GERÇEKTEN sürülür ve porta duty>0 paket yazılır (telde gerçek sürüş)."""
    o.mandal.sifirla("test")
    t = time.perf_counter()
    assert o.hc.update_coil(1, 100.0, 30.0, 0.0, 1, start=True) is True, "aparat: bobin 1 surulemedi"
    assert _bekle(lambda: any(ts >= t and not _stop_mu(b) for ts, b in list(o.d.yazilan)), 3.0), (
        "aparat: surus paketi porta yazilmadi"
    )


def _aktif_seans(o, deneme: int) -> None:
    with o.api._session_lock:
        o.api._active_session.clear()
        o.api._active_session.update(
            {
                "is_active": True,
                "session_id": f"o11-{deneme}",
                "coil_ids": [1, 2],
                "db_session_id": None,
                "started_epoch": time.time(),
                "start_mono": time.monotonic(),
                "mode": "Manuel",
            }
        )


def _seanssiz(o, deneme: int) -> None:
    with o.api._session_lock:
        o.api._active_session.clear()


def _mandalli(o, deneme: int) -> None:
    _seanssiz(o, deneme)
    o.mandal.mandalla("test-o11")


async def _frame_kayip(o, c):
    await o.air._frame_kayip_stopu("test-o11", 3)
    return types.SimpleNamespace(status_code=200)


YOLLAR = {
    "acil_durdur": dict(
        hazirla=_seanssiz, istek=lambda o, c: c.post("/api/hardware/emergency_stop"), kod={200}, olcut="stm"
    ),
    "seans_durdur_AKTIF": dict(
        hazirla=_aktif_seans, istek=lambda o, c: c.post("/api/session/stop"), kod={200}, olcut="stm"
    ),
    "seans_durdur_SEANSSIZ": dict(
        hazirla=_seanssiz, istek=lambda o, c: c.post("/api/session/stop"), kod={200}, olcut="stm"
    ),
    "eski_komut_stop_all": dict(
        hazirla=_seanssiz,
        istek=lambda o, c: c.post("/api/hardware/command", json={"command": "stop_all_coils", "params": {}}),
        kod={200},
        olcut="stm",
    ),
    "ai_pro_stop": dict(hazirla=_seanssiz, istek=lambda o, c: c.post("/api/ai/pro/stop"), kod={200}, olcut="stm"),
    "sifir_hz_MANDALLI": dict(
        hazirla=_mandalli,
        istek=lambda o, c: c.post("/api/session/start", json={"frequency": 0, "coil_ids": [1, 2]}),
        kod={503},
        olcut="stm",
    ),
    "frame_hedef_kaybi_STOP": dict(hazirla=_seanssiz, istek=_frame_kayip, kod={200}, olcut="stm"),
    "esp_bobin_STOP": dict(
        hazirla=_seanssiz,
        istek=lambda o, c: c.post("/api/coil/8/control", json={"start": False}),
        kod={200},
        olcut="esp",
    ),
    "esp_toplu_STOP": dict(
        hazirla=_seanssiz,
        istek=lambda o, c: c.post("/api/coil/batch", json={"coil_ids": [8], "start": False}),
        kod={200},
        olcut="esp",
    ),
}


def _ilk_stop_stm(o, t0: float):
    for ts, b in list(o.d.yazilan):
        if ts >= t0 and _stop_mu(b):
            return ts
    return None


def _ilk_stop_esp(o, t0: float):
    for ts, topic, payload in list(o.d.yayin):
        if ts >= t0 and topic == "pemf/coil/8/control" and payload.get("command") == "stop":
            return ts
    return None


async def _havuzlari_doldur():
    """İki ORTAK havuzu asılı işlerle doldurur (asılı disk / DB benzeri). @return (olay, isler, dolu_mu).
    Aparat kanıtı: iki havuzda da kısa bir iş 0,3 sn'de BAŞLAMAZ."""
    import anyio.to_thread

    loop = asyncio.get_running_loop()
    await asyncio.to_thread(lambda: None)  # varsayılan yürütücü kurulsun
    n_asyncio = int(loop._default_executor._max_workers)
    n_anyio = int(anyio.to_thread.current_default_thread_limiter().total_tokens)
    olay = threading.Event()
    isler = [asyncio.ensure_future(asyncio.to_thread(olay.wait, 60)) for _ in range(n_asyncio + 2)]
    isler += [asyncio.ensure_future(anyio.to_thread.run_sync(olay.wait, 60)) for _ in range(n_anyio + 2)]
    await asyncio.sleep(0.05)
    dolu = []
    for deneme in (lambda: asyncio.to_thread(lambda: None), lambda: anyio.to_thread.run_sync(lambda: None)):
        try:
            await asyncio.wait_for(deneme(), 0.3)
            dolu.append(False)
        except asyncio.TimeoutError:
            dolu.append(True)
    return olay, isler, all(dolu)


def _bir_deneme(o, ad: str, deneme: int, havuz_dolu: bool):
    """Tek deneme (kendi olay döngüsü): hazırlık → [havuzlar dolu] → istek → STOP'un porta yazıldığı an."""
    import httpx

    y = YOLLAR[ad]
    if y["olcut"] == "stm":
        _bobin1_sur(o)
    y["hazirla"](o, deneme)

    async def _kos():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=o.api.app), base_url="http://cihaz") as c:
            olay, isler, dolu = (None, [], True)
            if havuz_dolu:
                olay, isler, dolu = await _havuzlari_doldur()
            try:
                assert dolu, "aparat: ortak havuzlar DOLMADI (olcum anlamsiz)"
                t0 = time.perf_counter()
                kod, yanit_s = None, None
                try:
                    r = await asyncio.wait_for(y["istek"](o, c), timeout=BEKLEME_S)
                    kod, yanit_s = r.status_code, time.perf_counter() - t0
                except asyncio.TimeoutError:
                    pass
                bul = _ilk_stop_stm if y["olcut"] == "stm" else _ilk_stop_esp
                while time.perf_counter() < t0 + SINIR_S and bul(o, t0) is None:
                    await asyncio.sleep(0.01)
                ts = bul(o, t0)
                return kod, yanit_s, (None if ts is None else ts - t0)
            finally:
                if olay is not None:
                    olay.set()
                await asyncio.gather(*isler, return_exceptions=True)

    return asyncio.run(_kos())


def _olc(o, ad: str, n: int, havuz_dolu: bool):
    y = YOLLAR[ad]
    sonuclar = [_bir_deneme(o, ad, i, havuz_dolu) for i in range(n)]
    kotu = [
        s
        for s in sonuclar
        if s[0] not in y["kod"] or s[1] is None or s[1] >= SINIR_S or s[2] is None or s[2] >= SINIR_S
    ]
    _sure = [round(s[2], 3) if s[2] is not None else None for s in sonuclar]
    print(f"O11_ORAN yol={ad} havuz_dolu={havuz_dolu} kirmizi={len(kotu)}/{n} stop_s={_sure[:6]} ornek_kotu={kotu[:3]}")
    return kotu


@pytest.mark.parametrize("ad", list(YOLLAR))
def test_KRITIK_ortak_havuzlar_DOLUYKEN_STOP_1_sn_icinde_PORTA_gider(aparat, ad):
    kotu = _olc(aparat, ad, DENEME, havuz_dolu=True)
    assert not kotu, (
        f"{ad}: iki ortak iş parçacığı havuzu asılı işlerle doluyken {len(kotu)}/{DENEME} denemede STOP {SINIR_S} sn "
        f"içinde PORTA gitmedi ya da yanıt dönmedi — STOP yolu ortak havuza bağlı (Ö.4-Y8). "
        f"(kod, yanit_s, stop_s) örnek: {kotu[:3]}"
    )


@pytest.mark.parametrize("ad", list(YOLLAR))
def test_KARSIT_havuzlar_BOSKEN_aparat_STOPu_olcer(aparat, ad):
    """Aparat kanıtı: havuzlar boşken aynı ölçüm her yolda STOP'u < 1 sn'de porta yazılmış görür (kırmızı yalnız
    havuz bağımlılığından gelir, aparattan değil)."""
    kotu = _olc(aparat, ad, 3, havuz_dolu=False)
    assert not kotu, f"{ad}: havuz boşken bile ölçüt tutmadı (aparat?): {kotu}"


@pytest.mark.parametrize("ad", ["acil_durdur", "seans_durdur_AKTIF"])
def test_KRITIK_istek_IPTAL_edilse_de_STOP_porta_gider(aparat, monkeypatch, ad):
    """İstemci vazgeçince (zaman aşımı / bağlantı kopması — Starlette `BaseHTTPMiddleware` uç görevini iptal edebilir)
    bekleyen iptal edilir. `to_thread`'de iş henüz BAŞLAMADIYSA yürütücü onu ATLAR → STOP HİÇ gitmez (havuz doluyken
    pencere sınırsız). Sözleşme: bekleyen vazgeçse de durdurma işi YİNE koşar. Pencere zorlanır: yeni iş parçacıkları
    50 ms geç başlar, istek 10 ms'de iptal edilir."""
    import httpx

    class _GecBaslayan(threading.Thread):
        def run(self):
            time.sleep(0.05)
            super().run()

    o = aparat
    y = YOLLAR[ad]
    kotu = []
    for i in range(DENEME):
        _bobin1_sur(o)
        y["hazirla"](o, i)
        monkeypatch.setattr(threading, "Thread", _GecBaslayan)

        async def _kos():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=o.api.app), base_url="http://cihaz") as c:
                t0 = time.perf_counter()
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(y["istek"](o, c), timeout=0.01)
                while time.perf_counter() < t0 + 1.5 and _ilk_stop_stm(o, t0) is None:
                    await asyncio.sleep(0.01)
                ts = _ilk_stop_stm(o, t0)
                return None if ts is None else ts - t0

        try:
            stop_s = asyncio.run(_kos())
        finally:
            monkeypatch.setattr(threading, "Thread", _GecBaslayan.__mro__[1])
        if stop_s is None:
            kotu.append(i)
    print(f"O11_ORAN yol={ad}_IPTAL kirmizi={len(kotu)}/{DENEME}")
    assert not kotu, (
        f"{ad}: istek iptal edilince {len(kotu)}/{DENEME} denemede STOP porta HİÇ gitmedi — bekleyen vazgeçince durdurma "
        "işi de düşüyor (Ö.4-Y8)"
    )


class _AsiliOnizleme:
    """Kamerayı bırakmak için `join` bekleten önizleme iş parçacığı (lokalizasyon ortası; `join_timeout_s` 6 sn)."""

    def __init__(self):
        self.olay = threading.Event()
        self.join_ani = None

    def is_alive(self):
        return not self.olay.is_set()

    def join(self, timeout=None):
        self.join_ani = time.perf_counter()
        self.olay.wait(timeout)


def test_KRITIK_ai_pro_stop_STOPu_ONIZLEME_beklemesinden_ONCE_porta_gider(aparat):
    """`stop_ai_pro` STOP'tan ÖNCE `_ai_hazirlik_durdur_ic()`'i çağırıyordu: önizleme o an lokalizasyondaysa kamera
    bırakılana dek `join(timeout=6)` — STOP 6 sn'ye dek gecikir (mobil `/frame` seansı `_ai_loop_active` kurmaz,
    önizleme açık kalabilir). Sözleşme: STOP < 1 sn'de porta; önizleme durdurma SONRA beklenir."""
    import httpx

    o = aparat
    kotu = []
    for i in range(DENEME):
        _bobin1_sur(o)
        _seanssiz(o, i)
        oniz = _AsiliOnizleme()
        o.air._ai_hazirlik_thread = oniz
        o.air._ai_hazirlik_active = True

        async def _kos():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=o.api.app), base_url="http://cihaz") as c:
                t0 = time.perf_counter()
                gorev = asyncio.ensure_future(c.post("/api/ai/pro/stop"))
                try:
                    while time.perf_counter() < t0 + SINIR_S and _ilk_stop_stm(o, t0) is None:
                        await asyncio.sleep(0.01)
                    ts = _ilk_stop_stm(o, t0)
                    # Önizleme durdurma yolu GERÇEKTEN koşsun: yük altında STOP + teyit beklemesi 1 sn'yi aşabilir
                    # (1-G kapsam koşusu: olay 1 sn'de koşulsuz bırakılınca sahte iş parçacığı "ölü" göründü, `join`
                    # hiç çağrılmadı — aparat kırmızısı). Olay `join` çağrılana dek (≤ 10 sn) tutulur.
                    son = time.perf_counter() + 10.0
                    while oniz.join_ani is None and time.perf_counter() < son:
                        await asyncio.sleep(0.01)
                finally:
                    oniz.olay.set()
                r = await asyncio.wait_for(gorev, timeout=10)
                return r.status_code, (None if ts is None else ts - t0), oniz.join_ani is not None

        kod, stop_s, join_oldu = asyncio.run(_kos())
        assert join_oldu, "aparat: önizleme join'i çağrılmadı (önizleme durdurma yolu koşmadı)"
        if kod != 200 or stop_s is None or stop_s >= SINIR_S:
            kotu.append((kod, stop_s))
    print(f"O11_ORAN yol=ai_pro_stop_ONIZLEME kirmizi={len(kotu)}/{DENEME} ornek={kotu[:3]}")
    assert not kotu, (
        f"AI Pro durdurma: önizleme kamerayı bırakırken (join) {len(kotu)}/{DENEME} denemede STOP {SINIR_S} sn içinde "
        f"PORTA gitmedi — STOP önizleme beklemesinin ARKASINDA (Ö.4-Y8). Örnek: {kotu[:3]}"
    )
