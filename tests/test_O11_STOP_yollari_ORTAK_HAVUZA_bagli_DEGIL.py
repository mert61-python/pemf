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

SÖZLEŞME: iki ortak havuz da (asyncio varsayılan yürütücüsü + anyio varsayılan sınırlayıcısı) asılı işlerle KİLİTLİYKEN
her STOP yolu STOP'u PORTA yazar (ESP yolunda yayını yapar) ve yanıtını döner — 30 deneme. KESİN ölçüt (SA, 2026-10-31):
havuz kilidi STOP porta ULAŞIP yanıt döndükten SONRA açılır (cömert güvenlik süresi `GUVENLIK_S`); STOP ya da yanıt
ortak havuza bağlıysa kilit açılmadan ASLA gelmez → her koşuda kırmızı; bağlı değilse makine yükünden bağımsız yeşil.
Eski ölçüt "her denemede < 1 sn" yükü ölçüyordu (MH2 tam süiti `cbbbe023`: makine APK derlerken 30 denemenin 1'inde
1,10 sn — tek başına 3 × yeşil). 1 sn BÜTÇESİ ayrı kolda (`test_BUTCE_…`, gerekçesi orada). Ölçüt HTTP
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
SINIR_S = 1.0  # sözleşme bütçesi: STOP porta ve yanıt < 1 sn (bütçe kolu, ortanca)
BEKLEME_S = SINIR_S + 1.0  # bütçe kolu: yanıtı en çok bu kadar bekle (kırmızıda deneme süresi)
GUVENLIK_S = 30.0  # kesin kol: havuz kilidinin en uzun süresi (tipik STOP ~0,01 sn; yalnız havuza bağlı STOP'ta dolar)
BUTCE_DENEME = 11  # bütçe kolu: ortanca için tek sayı


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
    İşler `olay` açılana dek BİTMEZ (kilit; güvenlik süresinden uzun bekler). Aparat kanıtı: iki havuzda da kısa bir iş
    0,3 sn'de BAŞLAMAZ — işçilerin hepsi kilitte, sonraki iş kuyrukta (yükten bağımsız)."""
    import anyio.to_thread

    loop = asyncio.get_running_loop()
    await asyncio.to_thread(lambda: None)  # varsayılan yürütücü kurulsun
    n_asyncio = int(loop._default_executor._max_workers)
    n_anyio = int(anyio.to_thread.current_default_thread_limiter().total_tokens)
    olay = threading.Event()
    kilit_s = GUVENLIK_S + 30.0
    isler = [asyncio.ensure_future(asyncio.to_thread(olay.wait, kilit_s)) for _ in range(n_asyncio + 2)]
    isler += [asyncio.ensure_future(anyio.to_thread.run_sync(olay.wait, kilit_s)) for _ in range(n_anyio + 2)]
    await asyncio.sleep(0.05)
    dolu = []
    for deneme in (lambda: asyncio.to_thread(lambda: None), lambda: anyio.to_thread.run_sync(lambda: None)):
        try:
            await asyncio.wait_for(deneme(), 0.3)
            dolu.append(False)
        except asyncio.TimeoutError:
            dolu.append(True)
    return olay, isler, all(dolu)


def _bir_deneme(o, ad: str, deneme: int, havuz_dolu: bool, kilit_en_cok_s: float = GUVENLIK_S):
    """Tek deneme (kendi olay döngüsü): hazırlık → [havuzlar kilitli] → istek → STOP'un porta yazıldığı an + yanıt.
    Havuz kilidi STOP porta ULAŞIP yanıt döndükten SONRA açılır (en çok `kilit_en_cok_s`): ortak havuza bağlı STOP / yanıt
    kilit açılmadan GELMEZ. İstek bu süre içinde iptal EDİLMEZ (iptal STOP'u düşürebilir — yükte sahte kırmızı).
    @return (kod, yanit_s, stop_s) — kilit süresinde gelmeyen None."""
    import httpx

    y = YOLLAR[ad]
    if y["olcut"] == "stm":
        _bobin1_sur(o)
    y["hazirla"](o, deneme)
    bul = _ilk_stop_stm if y["olcut"] == "stm" else _ilk_stop_esp

    async def _kos():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=o.api.app), base_url="http://cihaz") as c:

            async def _iste():
                r = await y["istek"](o, c)
                return r.status_code, time.perf_counter()

            olay, isler, dolu = (None, [], True)
            if havuz_dolu:
                olay, isler, dolu = await _havuzlari_doldur()
            gorev = None
            try:
                assert dolu, "aparat: ortak havuzlar DOLMADI (olcum anlamsiz)"
                t0 = time.perf_counter()
                gorev = asyncio.ensure_future(_iste())
                son = t0 + kilit_en_cok_s
                while time.perf_counter() < son and (bul(o, t0) is None or not gorev.done()):
                    await asyncio.sleep(0.01)
                ts = bul(o, t0)
                kod, yanit_s = None, None
                if gorev.done() and not gorev.cancelled() and gorev.exception() is None:
                    kod, t_yanit = gorev.result()
                    yanit_s = t_yanit - t0
                return kod, yanit_s, (None if ts is None else ts - t0)
            finally:
                if olay is not None:
                    olay.set()  # kilit YALNIZ burada açılır: STOP + yanıt geldikten (ya da süre dolduktan) SONRA
                if gorev is not None and not gorev.done():
                    await asyncio.wait([gorev], timeout=10)
                    gorev.cancel()
                await asyncio.gather(*isler, return_exceptions=True)
                if gorev is not None:
                    await asyncio.gather(gorev, return_exceptions=True)

    return asyncio.run(_kos())


def _olc(o, ad: str, n: int, havuz_dolu: bool):
    """KESİN ölçüt: STOP porta ulaştı VE yanıt beklenen kodla döndü (kilit süresi içinde). İlk kötü denemede durur:
    havuza bağlı STOP her denemede gelmez, tekrar yalnız güvenlik süresi kadar bekletir."""
    y = YOLLAR[ad]
    sonuclar, kotu = [], []
    for i in range(n):
        s = _bir_deneme(o, ad, i, havuz_dolu)
        sonuclar.append(s)
        if s[0] not in y["kod"] or s[1] is None or s[2] is None:
            kotu.append(s)
            break
    _sure = [round(s[2], 3) if s[2] is not None else None for s in sonuclar]
    _en = max((s[2] for s in sonuclar if s[2] is not None), default=None)
    print(
        f"O11_ORAN yol={ad} havuz_dolu={havuz_dolu} kirmizi={len(kotu)}/{len(sonuclar)} stop_s={_sure[:6]} "
        f"en_uzun_stop_s={None if _en is None else round(_en, 3)} ornek_kotu={kotu[:3]}"
    )
    return kotu


@pytest.mark.parametrize("ad", list(YOLLAR))
def test_KRITIK_ortak_havuzlar_KILITLIYKEN_STOP_PORTA_gider_yanit_doner(aparat, ad):
    kotu = _olc(aparat, ad, DENEME, havuz_dolu=True)
    assert not kotu, (
        f"{ad}: iki ortak iş parçacığı havuzu asılı işlerle KİLİTLİYKEN STOP {GUVENLIK_S:.0f} sn içinde PORTA gitmedi ya da "
        f"yanıt dönmedi (kilit yalnız STOP + yanıttan SONRA açılır) — STOP yolu ortak havuza bağlı (Ö.4-Y8). "
        f"(kod, yanit_s, stop_s) örnek: {kotu[:3]}"
    )


@pytest.mark.parametrize("ad", list(YOLLAR))
def test_KARSIT_havuzlar_BOSKEN_aparat_STOPu_olcer(aparat, ad):
    """Aparat kanıtı: havuzlar boşken aynı kesin ölçüm her yolda STOP'u porta yazılmış ve yanıtı dönmüş görür (kırmızı
    yalnız havuz bağımlılığından gelir, aparattan değil)."""
    kotu = _olc(aparat, ad, 3, havuz_dolu=False)
    assert not kotu, f"{ad}: havuz boşken bile ölçüt tutmadı (aparat?): {kotu}"


@pytest.mark.parametrize("ad", list(YOLLAR))
def test_BUTCE_ortak_havuzlar_DOLUYKEN_STOP_ORTANCA_1_sn_icinde(aparat, ad):
    """1 sn BÜTÇESİ — ayrı kol. GEREKÇE: kesin kol STOP'un ortak havuza BAĞLI OLMADIĞINI kanıtlar ama havuzdan bağımsız
    olup YAPISAL olarak yavaş bir STOP'u (ör. porta yazmadan önce teyit / uyku bekleyen, yanıtı geciktiren) göremez;
    sözleşme sayısı 1 sn. Ölçüt ORTANCA (11 deneme, havuzlar dolu, deneme başına en çok `BEKLEME_S`): yapısal gecikme
    her denemede olur → ortanca yakalar; tek bir zamanlayıcı takılması (MH2: makine APK derlerken 30'da 1, 1,10 sn)
    makine yükünü ölçer, Ö.4-Y8'i değil → ortancayı oynatmaz."""
    y = YOLLAR[ad]
    yari = BUTCE_DENEME // 2
    sonuclar = []
    for i in range(BUTCE_DENEME):
        sonuclar.append(_bir_deneme(aparat, ad, i, havuz_dolu=True, kilit_en_cok_s=BEKLEME_S))
        asan = [
            s for s in sonuclar if s[0] not in y["kod"] or s[1] is None or s[2] is None or max(s[1], s[2]) >= SINIR_S
        ]
        if len(asan) > yari:
            break  # ortanca artık bütçeyi aşar
    sonsuz = float("inf")
    stop = sorted(s[2] if s[2] is not None else sonsuz for s in sonuclar)
    yanit = sorted(s[1] if s[1] is not None and s[0] in y["kod"] else sonsuz for s in sonuclar)
    stop_orta, yanit_orta = stop[len(stop) // 2], yanit[len(yanit) // 2]
    print(f"O11_BUTCE yol={ad} n={len(sonuclar)} stop_ortanca_s={stop_orta:.3f} yanit_ortanca_s={yanit_orta:.3f}")
    assert len(sonuclar) == BUTCE_DENEME and stop_orta < SINIR_S and yanit_orta < SINIR_S, (
        f"{ad}: ortak havuzlar doluyken STOP / yanıt ORTANCASI {SINIR_S} sn bütçesini aştı — STOP yapısal olarak yavaş "
        f"(Ö.4-Y8 sözleşmesi < 1 sn). ortanca stop_s={stop_orta:.3f} yanit_s={yanit_orta:.3f}; (kod, yanit_s, stop_s): "
        f"{sonuclar}"
    )


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


@pytest.mark.parametrize("ikinci", ["acil_durdur", "seans_durdur_SEANSSIZ"])
def test_KRITIK_ASILI_bir_STOP_isi_SONRAKI_STOPu_bekletmez(aparat, monkeypatch, ikinci):
    """1-G inceleme G-1.2: durdurma işleri birbirini BEKLEMEZ. Bir STOP işi STOP'u gönderdikten sonra asılı kalabilir
    (ACİL DURDUR'un seans kaydı kapanışı asılı diskte; `_emergency_stop_all` DB'yi STOP'tan SONRA yazar). Yardımcı her
    işe KENDİ iş parçacığını açtığı için sonraki STOP sıra beklemez. "Ayrılmış tek-işlik yürütücü" (1-F inceleme
    önerisi) ya da işleri serileştiren bir kilit bunu bozar: yukarıdaki kollar onlarda YEŞİL kaldı (ölçüldü — ortak
    havuzlar dolu ama ayrılmış yürütücü boş), sonraki STOP 10/10 porta GİTMEDİ."""
    import httpx

    o = aparat
    asili, girdi = threading.Event(), threading.Event()

    class _AsiliDB:
        def record_session_event(self, *a, **k):
            girdi.set()
            asili.wait(30)

    monkeypatch.setattr(o.api, "_get_treatment_db", lambda: _AsiliDB())
    monkeypatch.setattr(o.api, "_finalize_session_db", lambda *a, **k: asili.wait(30))
    sonuc = []
    try:
        for i in range(10):
            asili.clear()
            girdi.clear()
            _bobin1_sur(o)
            with o.api._session_lock:
                o.api._active_session.clear()
                o.api._active_session.update(
                    {
                        "is_active": True,
                        "session_id": f"g12-{i}",
                        "coil_ids": [1, 2],
                        "db_session_id": 4242,
                        "started_epoch": time.time(),
                        "start_mono": time.monotonic(),
                        "mode": "Manuel",
                    }
                )

            async def _kos():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=o.api.app), base_url="http://cihaz"
                ) as c:
                    t0 = time.perf_counter()
                    ilk = asyncio.ensure_future(c.post("/api/hardware/emergency_stop"))
                    while time.perf_counter() < t0 + 3 and not girdi.is_set():
                        await asyncio.sleep(0.01)
                    assert girdi.is_set(), "aparat: ilk ACİL DURDUR seans kaydı kapanışına (asılı) girmedi"
                    assert _ilk_stop_stm(o, t0) is not None, "aparat: ilk ACİL DURDUR'un STOP'u porta gitmedi"
                    _bobin1_sur(o)  # ikinci STOP'tan önce telde yine gerçek sürüş
                    with o.api._session_lock:
                        o.api._active_session.clear()
                    t1 = time.perf_counter()
                    yol = "/api/hardware/emergency_stop" if ikinci == "acil_durdur" else "/api/session/stop"
                    ikinci_g = asyncio.ensure_future(c.post(yol))
                    try:
                        while time.perf_counter() < t1 + SINIR_S and _ilk_stop_stm(o, t1) is None:
                            await asyncio.sleep(0.01)
                        ts = _ilk_stop_stm(o, t1)
                    finally:
                        asili.set()
                        await asyncio.wait_for(asyncio.gather(ilk, ikinci_g, return_exceptions=True), 15)
                    return None if ts is None else round(ts - t1, 3)

            sonuc.append(asyncio.run(_kos()))
    finally:
        asili.set()
    print(f"O11_ORAN yol={ikinci}_ASILI_ONCEKI_IS sonuc={sonuc}")
    kotu = [s for s in sonuc if s is None or s >= SINIR_S]
    assert not kotu, (
        f"{ikinci}: önceki bir STOP işi (ACİL DURDUR'un DB kapanışı) asılıyken {len(kotu)}/10 denemede sonraki STOP "
        f"{SINIR_S} sn içinde PORTA gitmedi — durdurma işleri birbirini bekliyor (Ö.4-Y8). Süreler: {sonuc}"
    )
