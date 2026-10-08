# -*- coding: utf-8 -*-
"""C2-4.1 (2-C incelemesi, orkestratör) — TEDAVİ DB'si kilitliyken olay döngüsündeki kayıt yazımları ACİL DURDUR'u BEKLETMEZ.

ÖLÇÜLEN KUSUR (B2B2-1'in tedavi DB'si ikizi; 2-B2 §6 #7 açık sorusu): async uçlar tedavi DB'sine OLAY DÖNGÜSÜ iş parçacığında
senkron yazıyordu — `audit_log.yaz` (kayıtlı operatörlü cihazda jetonsuz değerlendirme / AI silme 428 red izi, enroll, dışa
aktarma, destek paketi …), `start_session`'ın `session_started` olayı, bobin kontrol uçlarının koşu kaydı
(`coil_run_tracker._begin_coil_run` / `_finish_coil_run`). Tedavi DB'si başka bir yazıcı tarafından kilitliyken (WAL: okumalar
sürer, yazımlar `busy_timeout` 5 sn bekler) döngü donuyor, o sırada gelen ACİL DURDUR işlenemiyordu [ÖLÇTÜM, paylaşılan döngü]:
jetonsuz değerlendirme yükünde ACİL DURDUR yanıtı 9,8 sn, STOP donanım kuyruğuna 4,4 sn; seans içi bobin başlat/durdur yükünde
STOP kuyruğa 9,9 sn. Ö.4-Y8: ACİL DURDUR hiçbir şeye kapılanmaz — gecikme de kapılanmadır. Ayrıca kilitte bu kayıtlar (red izi,
bobin koşu kaydı) `busy_timeout` sonunda DÜŞÜYORDU (iz ve doz kaydı kaybı).

DÜZELTME: `utils.dongu_disi_yazim.calistir` — döngüde tek işçili FIFO yürütücü, en çok 0,25 sn beklenir (normal yükte yanıt
yazımdan SONRA döner; DB meşgulse kayıt işçide tamamlanır); damgalar çağrı anında alınır.

GERÇEK: `TreatmentHistoryDB` (aparat tmp), kayıtlı operatör (gerçek enroll/jeton), GERÇEK `HardwareController` (kayıtçı kuyruk),
tek PAYLAŞILAN olay döngüsü (anyio portal — üretimdeki uvicorn gibi), ikinci bağlantıyla GERÇEK yazma kilidi. Ölçüt: STOP'un
donanım kuyruğuna ulaşma anı (`stop_all_coils` ilk çağrısı) ve ACİL DURDUR yanıtı.
KAPSAM DIŞI (ayrı açık madde C2-4.2): seans sürerken ACİL DURDUR yanıtı STOP'tan SONRAKİ seans kaydı yazımlarını bekler —
o yanıt süresi burada ölçülmez; STOP'un kuyruğa gidişi ölçülür.
"""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

LAN = ("192.168.1.85", 52135)
YEREL = ("127.0.0.1", 52134)
AYSE = "dr.ayse@klinik.com"
SINIR_SN = 2.0  # önce: STOP kuyruğa 4,4–9,9 sn, yanıt 9,8 sn; düzeltmeyle ≤ 0,35 sn


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens

    o = apa.kur(monkeypatch, tmp_path)
    o.secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.yerel = TestClient(o.api.app, client=YEREL, backend_options=o.secenek)
    operator_tokens.temizle_hepsi()
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            r = o.yerel.post("/api/operators/enroll", json={"email": AYSE, "display_name": "A", "pin": "123456"})
            assert r.status_code == 200, r.text[:200]
            o.jeton = r.json()["operator_token"]
            o.aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
            o.stop_ani = []
            _orj = hc.stop_all_coils

            def _damgali():
                o.stop_ani.append(time.monotonic())
                return _orj()

            hc.stop_all_coils = _damgali
            yield o
    finally:
        from utils import dongu_disi_yazim

        assert dongu_disi_yazim.bosalt(30), "aparat: bekleyen kayıt yazımları 30 sn'de bitmedi"
        operator_tokens.temizle_hepsi()
        for op in (o.yerel.get("/api/operators").json() or {}).get("data", []) or []:
            o.yerel.post("/api/operators/remove", json={"email": op["email"]})
        with o.api._session_lock:
            o.api._active_session["is_active"] = False
        o.geri()


def _kilitle(yol):
    """GERÇEK yazma kilidi (başka bir yazıcı): WAL'da okumalar sürer, yazımlar bekler."""
    kc = sqlite3.connect(str(yol), isolation_level=None, timeout=10)
    kc.execute("BEGIN EXCLUSIVE")
    kc.execute("UPDATE ai_analyses SET id = id")
    t = sqlite3.connect(str(yol), isolation_level=None, timeout=0.1)
    try:
        with pytest.raises(sqlite3.OperationalError):
            t.execute("BEGIN IMMEDIATE")  # araç kanıtı: kilit gerçekten tutuluyor
    finally:
        t.close()
    return kc


def _birak(kc):
    kc.execute("ROLLBACK")
    kc.close()


def _red_izi_sayisi(o):
    return len(
        [e for e in o.db.denetim_oku(1000) if e.get("event_type") == "ai.review" and e.get("outcome") == "reddedildi"]
    )


def _seans_ac(o):
    r = o.yerel.post(
        "/api/session/start",
        json={"patient_name": "Boncuk", "mode": "Manuel", "duration_minutes": 5},
        headers={"X-PEMF-Operator": o.jeton},
    )
    assert r.status_code == 200, r.text[:300]


def _yuk_istegi(o, aday, c, sira):
    if aday == "degerlendirme_JETONSUZ_428":
        return c.post("/api/ai/log/review", json={"analysis_id": o.aid, "status": "rejected", "note": "n"})
    if aday == "ai_sil_JETONSUZ_428":
        return c.post("/api/ai/log/delete", json={"id": o.aid})
    if aday == "seans_baslat_jetonlu":
        try:
            return c.post(
                "/api/session/start",
                json={"patient_name": "Boncuk", "mode": "Manuel", "duration_minutes": 5},
                headers={"X-PEMF-Operator": o.jeton},
            )
        finally:
            with o.api._session_lock:
                o.api._active_session["is_active"] = False
    if aday == "bobin_seansta":
        return c.post("/api/coil/1/control", json={"freq": 50, "duty": 25, "start": sira % 2 == 0})
    raise AssertionError(aday)


@pytest.mark.parametrize(
    "aday,istemci,yanit_olc",
    [
        ("degerlendirme_JETONSUZ_428", LAN, True),
        ("ai_sil_JETONSUZ_428", YEREL, True),
        ("seans_baslat_jetonlu", LAN, False),
        ("bobin_seansta", LAN, False),
    ],
)
def test_KRITIK_tedavi_DB_KILITLIYKEN_dongu_yazimi_ACIL_DURDUR_ve_STOP_BEKLETMEZ(o, aday, istemci, yanit_olc):
    from anyio.from_thread import start_blocking_portal

    if aday == "bobin_seansta":
        _seans_ac(o)  # koşu kaydı yalnız aktif seansta yazılır
    kc = _kilitle(o.db.db_path)
    try:
        with start_blocking_portal(backend="asyncio", backend_options=o.secenek) as portal:
            c = TestClient(o.api.app, client=istemci)
            c.portal = portal
            ce = TestClient(o.api.app, client=LAN)
            ce.portal = portal
            dur = threading.Event()
            yuk: list = []

            def _yuk():
                sira = 0
                while not dur.is_set():
                    t = time.monotonic()
                    r = _yuk_istegi(o, aday, c, sira)
                    yuk.append((r.status_code, round(time.monotonic() - t, 2)))
                    sira += 1
                    time.sleep(0.1)  # gerçekçi hız

            th = threading.Thread(target=_yuk, daemon=True)
            th.start()
            time.sleep(1.0)
            kutu: dict = {}

            def _estop():
                t = time.monotonic()
                kutu["r"] = ce.post("/api/hardware/emergency_stop")
                kutu["sn"] = time.monotonic() - t

            o.stop_ani.clear()
            t0 = time.monotonic()
            te = threading.Thread(target=_estop, daemon=True)
            te.start()
            while not o.stop_ani and time.monotonic() - t0 < 15:
                time.sleep(0.01)
            kuyruk_sn = (o.stop_ani[0] - t0) if o.stop_ani else None
            if yanit_olc:
                te.join(15)
            dur.set()
            _birak(kc)
            kc = None
            te.join(90)
            th.join(90)
    finally:
        if kc is not None:
            _birak(kc)
    print(
        f"\nC2-4.1 {aday}: STOP kuyruğa {kuyruk_sn} sn · ACİL DURDUR yanıtı {kutu.get('sn')} sn · yük {yuk[:6]} (n={len(yuk)})"
    )
    assert yuk, "aparat: kilit sürerken hiç yük isteği gitmedi"
    assert kuyruk_sn is not None and kuyruk_sn < SINIR_SN, (
        f"tedavi DB'si kilitliyken ACİL DURDUR'un STOP'u donanım kuyruğuna {kuyruk_sn} sn'de gitti — olay döngüsü kayıt "
        f"yazımında donuk ({aday})"
    )
    assert kutu["r"].status_code == 200, kutu["r"].text[:200]
    if yanit_olc:
        assert kutu["sn"] < SINIR_SN, (
            f"tedavi DB'si kilitliyken ACİL DURDUR yanıtı {kutu['sn']:.1f} sn bekledi ({aday})"
        )


def test_KARSIT_kilitsiz_RED_IZI_yanittan_ONCE_yazilir_yaris_yok(o):
    """Normal yolda davranış AYNI: 428'in red izi yanıt dönmeden önce DB'de (okuyucu hemen görür; 20 kez)."""
    c = TestClient(o.api.app, client=LAN, backend_options=o.secenek)
    for i in range(20):
        r = c.post("/api/ai/log/review", json={"analysis_id": o.aid, "status": "rejected", "note": "n"})
        assert r.status_code == 428, r.text[:200]
        assert _red_izi_sayisi(o) == i + 1, f"{i + 1}. red izi yanıttan sonra DB'de YOK (yarış)"


def test_KARSIT_kilitte_ertelenen_RED_IZI_KAYBOLMAZ(o):
    """Kilit sürerken atılan jetonsuz değerlendirmelerin red izleri kilit kalkınca TAMAMI yazılır (eskiden busy_timeout'ta düşüyordu)."""
    from utils import dongu_disi_yazim

    c = TestClient(o.api.app, client=LAN, backend_options=o.secenek)
    once = _red_izi_sayisi(o)
    kc = _kilitle(o.db.db_path)
    try:
        kodlar = [
            c.post("/api/ai/log/review", json={"analysis_id": o.aid, "status": "rejected", "note": "n"}).status_code
            for _ in range(3)
        ]
    finally:
        _birak(kc)
    assert kodlar == [428, 428, 428], kodlar
    assert dongu_disi_yazim.bosalt(30)
    assert _red_izi_sayisi(o) - once == 3, (
        f"kilitte atılan red izlerinden {3 - (_red_izi_sayisi(o) - once)} tanesi KAYBOLDU"
    )


def test_KARSIT_kilitte_BOBIN_KOSU_kaydi_KAYBOLMAZ_sira_ve_SURE_dogru(o):
    """Kilit sürerken başlatılıp durdurulan bobinin koşu kaydı kilit kalkınca yazılır; bitiş damgası ÇAĞRI anından (kuyruk
    beklemesi doz süresine eklenmez — D2.40); başlatma ve bitirme sırası korunur (açık koşu kalmaz)."""
    from utils import dongu_disi_yazim

    _seans_ac(o)

    def _kosular():
        with o.db._get_connection() as conn:
            return [
                (float(r[0]), (None if r[1] is None else float(r[1])))
                for r in conn.execute(
                    "SELECT started_epoch, ended_epoch FROM session_coil_runs WHERE coil_id = 2 ORDER BY id"
                ).fetchall()
            ]

    once = _kosular()  # seans başlatma bobinin kendi koşusunu açmış olabilir
    c = TestClient(o.api.app, client=LAN, backend_options=o.secenek)
    kc = _kilitle(o.db.db_path)
    try:
        r1 = c.post("/api/coil/2/control", json={"freq": 50, "duty": 25, "start": True})
        time.sleep(0.6)
        r2 = c.post("/api/coil/2/control", json={"freq": 50, "duty": 25, "start": False})
        time.sleep(1.5)  # kilit sürüyor: işçi bekliyor
    finally:
        _birak(kc)
    assert (r1.status_code, r2.status_code) == (200, 200), (r1.text[:200], r2.text[:200])
    assert dongu_disi_yazim.bosalt(30)
    sonra = _kosular()
    assert len(sonra) == len(once) + 1, f"kilitte bobin koşu kaydı yazılmadı ya da çoğaldı: önce {once} → sonra {sonra}"
    assert all(bit is not None for _b, bit in sonra), (
        f"koşu AÇIK kaldı (bitirme başlatmadan önce koştu / kayboldu): {sonra}"
    )
    bas, bit = sonra[-1]
    sure = bit - bas
    assert 0.4 <= sure < 1.5, (
        f"koşu süresi {sure:.2f} sn — çağrılar arası ~0,6 sn olmalıydı (kuyruk beklemesi süreye karıştı mı?)"
    )


def test_KRITIK_C2_2_5_durdurma_kapanisi_KUYRUKTAKI_kayitlardan_SONRA_kosar_ve_beklemez():
    """C2-2.5 / C2-1.3 birleşimi (orkestratör): durdurma yollarının STOP-sonrası kayıt kapanışı (`sirada_calistir`) kayıt
    kuyruğuna önceden girmiş yazımlardan (döngüde ertelenmiş koşu BAŞLATMA kaydı) SONRA koşar ve çağıranı en çok
    `bekleme_sn` bekletir. Ayrı iş parçacığında koşsaydı açık koşuları başlatma kaydı işlenmeden okuyabilir, koşu kilit
    kalkınca açılıp AÇIK kalırdı (kayıt 'sürülüyor' der, bobin durmuş)."""
    import asyncio

    from utils import dongu_disi_yazim

    sira: list = []
    engel = threading.Event()

    def _baslatma():
        engel.wait(10)  # kilitli DB'de bekleyen yazım
        sira.append("baslatma")

    async def _dongude():
        return dongu_disi_yazim.calistir(_baslatma, ad="sinama")

    assert asyncio.run(_dongude()) is None, "aparat: döngüdeki yazım kuyruğa ertelenmedi"
    t0 = time.monotonic()
    sonuc = dongu_disi_yazim.sirada_calistir(lambda: sira.append("kapanis"), bekleme_sn=0.2, ad="sinama")
    gecen = time.monotonic() - t0
    engel.set()
    assert dongu_disi_yazim.bosalt(10)
    assert sonuc is None and gecen < 1.0, f"durdurma kapanışı çağıranı {gecen:.2f} sn bekletti (sınır 0,2 sn)"
    assert sira == ["baslatma", "kapanis"], f"kapanış kuyruktaki kayıttan ÖNCE koştu: {sira}"


def test_KARSIT_C2_2_5_kilitte_baslatilan_bobinin_kosusu_ACIL_DURDURDA_KAPANIR(o):
    """Kilit sürerken başlatılan bobin, ardından ACİL DURDUR: yanıt beklemez; kilit kalkınca hiçbir koşu AÇIK kalmaz ve
    seans ACİL DURDURMA mührüyle kapanır (kayıt kaybolmaz)."""
    from utils import dongu_disi_yazim

    _seans_ac(o)
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    c = TestClient(o.api.app, client=LAN, backend_options=o.secenek)
    kc = _kilitle(o.db.db_path)
    try:
        r1 = c.post("/api/coil/3/control", json={"freq": 50, "duty": 25, "start": True})
        t0 = time.monotonic()
        r2 = c.post("/api/hardware/emergency_stop")
        sn = time.monotonic() - t0
        time.sleep(0.5)
    finally:
        _birak(kc)
    assert (r1.status_code, r2.status_code) == (200, 200), (r1.text[:200], r2.text[:200])
    assert sn < SINIR_SN, f"tedavi DB kilitliyken ACİL DURDUR yanıtı {sn:.1f} sn (kayıt kapanışını bekledi)"
    assert dongu_disi_yazim.bosalt(30)
    with o.db._get_connection() as conn:
        acik = conn.execute(
            "SELECT coil_id FROM session_coil_runs WHERE session_id = ? AND ended_epoch IS NULL", (sid,)
        ).fetchall()
        durum = conn.execute("SELECT session_status FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]
    assert not acik, f"ACİL DURDUR'dan sonra koşu AÇIK kaldı (bobinler {[r[0] for r in acik]})"
    assert durum == "EMERGENCY_STOPPED", durum
    with o.api._active_coil_runs_lock:
        assert not o.api._active_coil_runs, f"bellekte açık koşu kaldı: {dict(o.api._active_coil_runs)}"


def test_KRITIK_ESZAMANLI_bes_istemci_kilitte_ACIL_DURDUR_gecikmeleri_TOPLANMAZ(o):
    """Geri birikim kuralı (C2-3.2 kapısının ölçümü): kilitte beş istemci aynı anda jetonsuz değerlendirme gönderirken
    ACİL DURDUR yanıtı 1 sn'yi aşmaz — kuyrukta bitmemiş kayıt varken döngü HİÇ beklemez. Kural olmasa her istek 0,25 sn
    bekler, gecikmeler istemci sayısıyla TOPLANIR ve ACİL DURDUR kapanışı da kuyrukta 1 sn bekler (3 istemcide 1,9 sn)."""
    from anyio.from_thread import start_blocking_portal

    kc = _kilitle(o.db.db_path)
    try:
        with start_blocking_portal(backend="asyncio", backend_options=o.secenek) as portal:
            ce = TestClient(o.api.app, client=LAN)
            ce.portal = portal
            dur = threading.Event()
            yuk: list = []

            def _yuk():
                c = TestClient(o.api.app, client=LAN)
                c.portal = portal
                while not dur.is_set():
                    yuk.append(_yuk_istegi(o, "degerlendirme_JETONSUZ_428", c, 0).status_code)

            ipler = [threading.Thread(target=_yuk, daemon=True) for _ in range(5)]
            for t in ipler:
                t.start()
            time.sleep(1.0)
            sureler = []
            for _ in range(3):
                t = time.monotonic()
                r = ce.post("/api/hardware/emergency_stop")
                sureler.append((round(time.monotonic() - t, 2), r.status_code))
                time.sleep(0.3)
            dur.set()
            _birak(kc)
            kc = None
            for t in ipler:
                t.join(90)
    finally:
        if kc is not None:
            _birak(kc)
    print(f"\nC2-4.1 eşzamanlı 5 istemci: ACİL DURDUR {sureler} · yük n={len(yuk)} kodlar {sorted(set(yuk))}")
    assert yuk and set(yuk) == {428}, f"aparat: yük istekleri beklenen 428'i dönmedi: {sorted(set(yuk))}"
    assert all(k == 200 for _, k in sureler), sureler
    en_kotu = max(s for s, _ in sureler)
    assert en_kotu < 1.0, f"kilitte 5 eşzamanlı istemciyle ACİL DURDUR {en_kotu:.2f} sn — kayıt beklemeleri TOPLANIYOR"
