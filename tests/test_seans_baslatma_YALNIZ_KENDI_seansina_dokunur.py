# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-C bağımsız inceleme i1-F3 / i2-F1 / i2-F7 — bayat bir başlatma YALNIZ KENDİ seansına dokunur.

ÖLÇÜLEN KUSUR (c5b3c04 sonrası, i2 3 koşu × 30/30 × 2 kol; i1 3/3): `/api/session/start` (R1) DB yazımını beklerken
operatör durdurur (seans durdurma ya da E-stop + Sıfırla) ve YENİ bir seans (R2) açar. R1 uyanınca sürüşü nesille
DOĞRU reddediliyordu ama await sonrasındaki hiçbir adım "hâlâ BENİM seansım mı" diye bakmıyordu: R2'nin
`db_session_id`sini kendi satırıyla EZİYOR, R2'nin açık koşu kaydını ve sensör/dakika tamponlarını SİLİYOR, ret
sonrasındaki geri alma (`_seansi_geri_al`) O AN AKTİF olan R2'yi pasife çekip "Sistem Hazır" yazıyordu — R2'nin
bobini keep-alive ile enerjiliyken (süre bekçisi göremez, ekran "hazır" der, R2'nin DB satırı yetim 'active').
i2-F7: R1'in DB yazımı sırasında E-stop gelirse R1 "cancelled" döner ama açtığı satır 'active' kalıyordu.
Aynı kimliksiz geri alma AI (Auto) landmark yolunda da vardı (`start_all_coils` reddinde).

KAPI: R1'in `db.start_session`ı bir `threading.Event`te tutulur (gerçekte: SQLCipher yazımı yavaş/disk meşgul);
GERÇEK `/api/session/start`, `/api/session/stop`, `_emergency_stop_all`, Sıfırla, `HardwareController` (kayıtçı
kuyruk, firmware aynası), tmp DB. Ölçüt: R2'nin oturumu/canlı durumu/DB kimliği/koşu kaydı + bobin paketi; 30 deneme.
KARŞIT: yarış yokken R2 aktif kalır ve bobini çalışır (ölçüt her şeyi kırmızı saymıyor).
"""

from __future__ import annotations

import threading

import ai_pro_aparati as ap
import pytest

DENEME = 30


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    engel = {"ev": None, "girdi": threading.Event(), "sidler": []}
    orj = ns.db.start_session

    def _bloklu_start_session(*a, **k):
        ev = engel["ev"]
        if ev is not None:
            engel["ev"] = None  # yalnız R1'in çağrısı tutulur
            engel["girdi"].set()
            assert ev.wait(10), "aparat: R1 DB engeli 10 sn'de kalkmadı"
        sid = orj(*a, **k)
        engel["sidler"].append(sid)
        return sid

    monkeypatch.setattr(ns.db, "start_session", _bloklu_start_session)
    ns.engel = engel
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _temizle(o):
    ap.mandali_sifirla(o.c)
    o.c.post("/api/session/stop")
    o.hc.stop_all_coils()
    ap.mandali_sifirla(o.c)


def _seans(o, bobin: int, duty: float, mod: str):
    return o.c.post(
        "/api/session/start",
        json={"coil_ids": [bobin], "frequency": 50, "duty": duty, "phase": 0, "duration_minutes": 5, "mode": mod},
    )


def _r1_arka_planda(o):
    kutu: dict = {}

    def _calis():
        try:
            kutu["yanit"] = _seans(o, 1, 10, "Manuel-R1")
        except Exception as e:  # pragma: no cover - aparat tanısı
            kutu["hata"] = e

    t = threading.Thread(target=_calis, name="test-R1", daemon=True)
    t.start()
    return t, kutu


def _tur(o, durdurma: str, bloklu: bool = True) -> dict:
    _temizle(o)
    o.engel["girdi"].clear()
    ev = threading.Event()
    if bloklu:
        o.engel["ev"] = ev
        t, kutu = _r1_arka_planda(o)
        assert o.engel["girdi"].wait(10), "aparat: R1 DB yazımına ulaşmadı"
    else:
        o.engel["ev"] = None
        t, kutu = _r1_arka_planda(o)
        t.join(15)
    if durdurma == "session_stop":
        r = o.c.post("/api/session/stop")
        assert r.status_code == 200, r.text[:200]
    else:
        o.api._emergency_stop_all("manual")
        ap.mandali_sifirla(o.c)
    r2 = _seans(o, 2, 20, "Manuel-R2")
    assert r2.status_code == 200 and r2.json().get("status") == "success", f"aparat: R2 açılmadı {r2.text[:300]}"
    with o.api._session_lock:
        s2_kimlik = o.api._active_session.get("session_id")
        s2_db = o.api._active_session.get("db_session_id")
    s2_kosu = o.api._active_coil_runs.get(2)
    sonra = ap.paket_sayisi(o)
    ev.set()
    t.join(15)
    assert not t.is_alive(), "aparat: R1 bitmedi"
    with o.api._session_lock:
        s = dict(o.api._active_session)
    with o.ls._live_state_lock:
        canli = dict(o.ls._live_state["activeTreatment"])
    from kayitci_donanim import paket_coz

    sonuc = {
        "r1": getattr(kutu.get("yanit"), "status_code", kutu.get("hata")),
        "bobin2_calisiyor": bool(o.hc.coils_state[2]["is_running"]),
        "s2_aktif": bool(s.get("is_active")) and s.get("session_id") == s2_kimlik,
        "s2_db_ezildi": s.get("db_session_id") != s2_db,
        "canli_aktif": bool(canli.get("isActive")),
        "canli_mod": canli.get("mode"),
        "r1_bobin1_surus": [
            tuple(paket_coz(p)[0]) for p in o.hc.core._hw_send_queue.paketler[sonra:] if paket_coz(p)[0][0] > 0
        ],
        "s2_kosu_silindi": s2_kosu is not None and o.api._active_coil_runs.get(2) != s2_kosu,
    }
    r_dur = o.c.post("/api/session/stop")  # operatörün sonraki Durdur'u R2'nin KENDİ satırını kapatmalı
    sonuc["s2_db_durum_durdurdan_sonra"] = (
        (o.db.get_session_details(s2_db) or {}).get("session_status") if s2_db else None
    )
    sonuc["durdur_mesaji"] = (r_dur.json() or {}).get("message", "")[:60]
    return sonuc


@pytest.mark.parametrize("durdurma", ["session_stop", "estop_sifirla"])
def test_KRITIK_bayat_seans_baslatma_YENI_seansa_DOKUNMAZ_N30(o, durdurma):
    say = dict(ihlal=0, db_ezildi=0, eski_surus=0, kosu_silindi=0, canli_ezildi=0, db_acik=0)
    ornek = None
    for _ in range(DENEME):
        s = _tur(o, durdurma)
        bu = {
            "ihlal": s["bobin2_calisiyor"] and not s["s2_aktif"],
            "db_ezildi": s["s2_db_ezildi"],
            "eski_surus": bool(s["r1_bobin1_surus"]),
            "kosu_silindi": s["s2_kosu_silindi"],
            "canli_ezildi": not (s["canli_aktif"] and s["canli_mod"] == "Manuel-R2"),
            "db_acik": s["s2_db_durum_durdurdan_sonra"] == "active",
        }
        for k, v in bu.items():
            say[k] += bool(v)
        if any(bu.values()) and ornek is None:
            ornek = s
    assert all(v == 0 for v in say.values()), (
        f"{durdurma}: {DENEME} denemede bayat R1 YENİ seansa (R2) dokundu: {say} — örnek {ornek}"
    )


def test_KRITIK_iptal_edilen_baslatmanin_DB_satiri_ACIK_kalmaz_N30(o):
    """i2-F7: R1'in DB yazımı sürerken E-stop → R1 "cancelled". R1'in açtığı satır 'active' KALMAMALI ("İptal Edildi")."""
    durumlar: list = []
    for _ in range(DENEME):
        _temizle(o)
        o.engel["girdi"].clear()
        o.engel["sidler"].clear()
        ev = threading.Event()
        o.engel["ev"] = ev
        t, kutu = _r1_arka_planda(o)
        assert o.engel["girdi"].wait(10), "aparat: R1 DB yazımına ulaşmadı"
        o.api._emergency_stop_all("manual")
        ev.set()
        t.join(15)
        assert kutu["yanit"].status_code == 200 and kutu["yanit"].json().get("status") == "cancelled", kutu
        sid1 = o.engel["sidler"][-1]
        durumlar.append((o.db.get_session_details(sid1) or {}).get("session_status"))
    assert durumlar.count("cancelled") == DENEME, (
        f"iptal edilen başlatmanın DB satırı durumları: { {d: durumlar.count(d) for d in set(durumlar)} } "
        "(hepsi 'cancelled' olmalı — 'active' hayalet seans kaydıdır)"
    )


def test_KARSIT_yaris_yokken_yeni_seans_AKTIF_kalir(o):
    for _ in range(5):
        s = _tur(o, "session_stop", bloklu=False)
        assert s["r1"] == 200, s
        assert s["bobin2_calisiyor"] and s["s2_aktif"] and s["canli_aktif"], s


# ── AI (Auto) landmark: donanım reddindeki geri alma YALNIZ kendi seansına ─────────────────────────────────────────
