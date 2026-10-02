# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.81 · 1-C bağımsız inceleme i1-F5 — başlatma UÇUŞTAYKEN verilen bobin STOP'u uçuştaki seans başlatmasını İPTAL eder.

ÖLÇÜLEN KUSUR (i1 3/3; burada 4 STOP biçimi × 3): `/api/session/start` DB yazımındayken (await) gelen bobin STOP'u —
bobin henüz sürülmediği için — no-op'tu; başlatma ardından bobinleri ENERJİLİYOR ve 200 "success" dönüyordu. Nesil
yalnız seans / acil durdurma / `stop_all_coils` durdurmalarında artıyordu, bobin-başı STOP'ta artmıyordu.
Arayüzde yol açık: başlatma sürerken ana "⏹ Durdur" `loading` ile kilitli, ama bobin kartının "⏹ Durdur"u
(`CoilParameterPanel`; yalnız kendi isteği sürerken kilitli) basılabilir. (i1'in "arayüzün Durdur'u" gerekçesi ana
düğme için geçersiz — o düğme başlatma sürerken basılamaz; bobin kartı yolu geçerli.)

DÜZELTME (`api_server._ucustaki_baslatmayi_gecersiz_kil`): başlatma uçuştayken (seans kuruldu, sürüş sonrası denetim
bitmedi) o seansın bobinlerinden birini kapsayan bobin STOP'u — tekil / batch / legacy `stop_coil`, 0 Hz "parkla" dahil
— nesli artırır. DB yazımı sırasındaysa başlatma bobin SÜRMEDEN iptal edilir (409; kendi satırı "İptal Edildi" —
donanım reddetmediği için "Donanım Reddetti" DEĞİL); sürüş sırasındaysa kalan bobinler `HardwareController`da kilit
altında reddedilir ve seans durdurulur. Başlatma bittikten sonra ve AI (Auto) / AI Pro seansında nesle DOKUNMAZ (bobin
STOP'u yalnız o bobini durdurur; AI Pro sürüş yetkisi tek bobin STOP'uyla kesilmez). Ö.4-Y8: STOP yine gönderilir.

KAPI: GERÇEK `HardwareController` (kayıtçı kuyruk, firmware aynası) + tmp DB; DB yazımı bir Event'te bekletilir.
  KRİTİK (DB penceresi) — 4 STOP biçimi × 3: STOP'tan SONRA sürüş paketi yok, çalışan bobin yok, yanıt 409, seans
  pasif, kendi DB satırı "cancelled".
  KRİTİK (sürüş penceresi) — bobin 1 kabul edildikten SONRA, bobin 2'den ÖNCE bobin 2 STOP'u (zorlanmış zamanlama):
  bobin 2 o STOP'tan sonra hiç sürülmez, sonunda çalışan bobin yok, yanıt 409.
  KARŞIT — (a) seansın kapsamadığı bobine STOP başlatmayı iptal ETMEZ; (b) başlatma bittikten sonra bobin STOP'u nesle
  DOKUNMAZ, yalnız o bobini durdurur, seans sürer; (c) AI Pro mühürlü seansta bobin STOP'u nesle DOKUNMAZ.
"""

from __future__ import annotations

import threading

import ai_pro_aparati as ap
import pytest

TEKRAR = 3
_BOBINLER = [1, 2]

# STOP biçimleri: bobin kartı (tekil), ana Durdur'un bobin STOP'u (batch), legacy uç, 0 Hz "parkla" (D1.53: STOP sayılır).
_STOPLAR = {
    "tekil": ("/api/coil/2/control", {"start": False, "freq": 0, "duty": 0, "phase": 0, "duration": 0}),
    "batch": ("/api/coil/batch", {"coil_ids": [1, 2], "start": False, "freq": 0, "duty": 0, "phase": 0, "duration": 0}),
    "legacy": ("/api/hardware/command", {"command": "stop_coil", "params": {"coil_id": 1}}),
    "sifir_hz": ("/api/coil/1/control", {"start": True, "freq": 0, "duty": 40, "phase": 0, "duration": 60}),
}


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    engel = {"ev": None, "girdi": threading.Event(), "sidler": []}
    orj = ns.db.start_session

    def _bloklu_start_session(*a, **k):
        ev = engel["ev"]
        if ev is not None:
            engel["ev"] = None  # yalnız uçuştaki başlatmanın çağrısı tutulur
            engel["girdi"].set()
            assert ev.wait(10), "aparat: DB engeli 10 sn'de kalkmadı"
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
    o.c.post("/api/session/stop")
    o.hc.stop_all_coils()
    ap.mandali_sifirla(o.c)


def _baslat(o):
    return o.c.post(
        "/api/session/start",
        json={"coil_ids": _BOBINLER, "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5, "mode": "Manuel"},
    )


def _arka_planda_baslat(o):
    kutu: dict = {}

    def _calis():
        try:
            kutu["yanit"] = _baslat(o)
        except Exception as e:  # pragma: no cover - aparat tanısı
            kutu["hata"] = e

    t = threading.Thread(target=_calis, name="test-baslatma", daemon=True)
    t.start()
    return t, kutu


def _stop(o, bicim):
    yol, govde = _STOPLAR[bicim]
    return o.c.post(yol, json=govde)


def _db_penceresinde(o, bicim) -> dict:
    """Başlatmayı DB yazımında tut, STOP'u ver, bırak → gözlem."""
    _temizle(o)
    o.engel["girdi"].clear()
    o.engel["sidler"].clear()
    ev = threading.Event()
    o.engel["ev"] = ev
    t, kutu = _arka_planda_baslat(o)
    assert o.engel["girdi"].wait(10), "aparat: başlatma DB yazımına ulaşmadı"
    r_stop = _stop(o, bicim)
    assert r_stop.status_code == 200, f"aparat: {bicim} STOP'u {r_stop.status_code} {r_stop.text[:200]}"
    sonra = ap.paket_sayisi(o)
    ev.set()
    t.join(15)
    assert not t.is_alive(), "aparat: başlatma bitmedi"
    r = kutu.get("yanit")
    with o.api._session_lock:
        aktif = bool(o.api._active_session.get("is_active"))
    sid = o.engel["sidler"][-1] if o.engel["sidler"] else None
    return {
        "yanit": getattr(r, "status_code", kutu.get("hata")),
        "govde": r.text[:160] if r is not None else None,
        "surus": ap.surus_paketleri(o, sonra)[:1],
        "calisan": ap.calisan(o),
        "seans_aktif": aktif,
        "db": (o.db.get_session_details(sid) or {}).get("session_status") if sid else None,
    }


@pytest.mark.parametrize("bicim", list(_STOPLAR))
def test_KRITIK_DB_yazimi_sirasinda_bobin_STOPu_baslatmayi_IPTAL_eder(o, bicim):
    gozlem = [_db_penceresinde(o, bicim) for _ in range(TEKRAR)]
    _temizle(o)
    for g in gozlem:
        assert not g["surus"] and not g["calisan"], (
            f"{bicim}: başlatma DB yazımındayken verilen bobin STOP'undan SONRA uçuştaki START bobinleri ENERJİLEDİ: {g}"
        )
        assert g["yanit"] == 409 and not g["seans_aktif"], f"{bicim}: başlatma reddedilmedi ya da seans açık kaldı: {g}"
        assert g["db"] == "cancelled", f"{bicim}: iptal edilen başlatmanın DB satırı 'İptal Edildi' değil: {g}"


def test_KRITIK_SURUS_sirasinda_bobin_STOPu_kalan_bobini_SURDURMEZ(o, monkeypatch):
    """Bobin 1 kabul edildikten SONRA, bobin 2 sürülmeden ÖNCE bobin 2 STOP'u (zorlanmış zamanlama): bobin 2 o STOP'tan
    sonra HİÇ sürülmez; başlatma reddedilir ve kabul edilmiş bobin 1 de durdurulur (STOP'lar yalnız artar)."""
    gercek = o.hc.update_coil
    durum: dict = {}

    def _kancali(bobin, *a, **k):
        sonuc = gercek(bobin, *a, **k)
        if k.get("start") and bobin == 1 and not durum.get("tetik"):
            durum["tetik"] = True
            th = threading.Thread(target=lambda: durum.update(stop=_stop(o, "tekil")), daemon=True)
            th.start()
            th.join(10)
            durum["sonra"] = ap.paket_sayisi(o)
        return sonuc

    monkeypatch.setattr(o.hc, "update_coil", _kancali)
    gozlem = []
    for _ in range(TEKRAR):
        _temizle(o)
        durum.clear()
        o.engel["ev"] = None
        r = _baslat(o)
        assert durum.get("tetik") and durum.get("stop") is not None, f"aparat: kanca tetiklenmedi {durum}"
        assert durum["stop"].status_code == 200, f"aparat: STOP {durum['stop'].status_code}"
        bobin2 = [d for d in ap.surus_paketleri(o, durum["sonra"]) if d[1] > 0]
        gozlem.append({"yanit": r.status_code, "bobin2_surus": bobin2[:1], "calisan": ap.calisan(o)})
    _temizle(o)
    for g in gozlem:
        assert not g["bobin2_surus"] and not g["calisan"] and g["yanit"] == 409, (
            f"sürüş sırasında verilen bobin 2 STOP'undan SONRA bobin 2 sürüldü ya da bobin enerjili kaldı: {g}"
        )


def test_KRITIK_Y8_iptal_mekanizmasi_HATA_verse_de_bobin_STOPu_GIDER(o):
    """Ö.4-Y8: uçuştaki-başlatma iptali (nesil artırımı) istisna atsa bile bobin STOP'u reddedilmez — tekil, batch ve
    legacy uçların üçü de STOP paketini kuyruğa verir ve 200 döner (iptalin hatası STOP isteğini 500'e çevirmez)."""
    from utils import estop_mandali

    def _bozuk():
        raise RuntimeError("test: nesil artırımı bozuk")

    for bicim in ("tekil", "batch", "legacy"):
        _temizle(o)
        o.engel["girdi"].clear()
        ev = threading.Event()
        o.engel["ev"] = ev
        t, kutu = _arka_planda_baslat(o)
        assert o.engel["girdi"].wait(10), "aparat: başlatma DB yazımına ulaşmadı"
        once = ap.paket_sayisi(o)
        orj = estop_mandali.nesil_artir
        estop_mandali.nesil_artir = _bozuk
        try:
            r = _stop(o, bicim)
            sonra = ap.paket_sayisi(o)
        finally:
            estop_mandali.nesil_artir = orj
            ev.set()  # STOP isteği istisna atsa da uçuştaki başlatma serbest bırakılır (aparat askıda kalmasın)
            t.join(15)
            _temizle(o)
        assert r.status_code == 200 and (r.json() or {}).get("status") == "success", (
            f"{bicim}: iptal mekanizmasının hatası bobin STOP isteğini bozdu: {r.status_code} {r.text[:200]}"
        )
        assert sonra > once, f"{bicim}: iptal mekanizmasının hatasıyla STOP paketi kuyruğa VERİLMEDİ"


def test_KARSIT_seansin_KAPSAMADIGI_bobine_STOP_baslatmayi_IPTAL_ETMEZ(o):
    _temizle(o)
    o.engel["girdi"].clear()
    ev = threading.Event()
    o.engel["ev"] = ev
    t, kutu = _arka_planda_baslat(o)
    assert o.engel["girdi"].wait(10), "aparat: başlatma DB yazımına ulaşmadı"
    r_stop = o.c.post("/api/coil/5/control", json={"start": False, "freq": 0, "duty": 0, "phase": 0, "duration": 0})
    assert r_stop.status_code == 200, r_stop.text[:200]
    ev.set()
    t.join(15)
    yanit = kutu["yanit"]
    calisan = ap.calisan(o)
    _temizle(o)
    assert yanit.status_code == 200 and yanit.json().get("status") == "success", yanit.text[:300]
    assert sorted(calisan) == _BOBINLER, f"kapsam dışı bobin STOP'u başlatmayı etkiledi: çalışan {calisan}"


def test_KARSIT_baslatma_BITTIKTEN_sonra_bobin_STOPu_nesle_DOKUNMAZ(o):
    from utils import estop_mandali

    _temizle(o)
    o.engel["ev"] = None
    r = _baslat(o)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:300]
    n0 = estop_mandali.nesil()
    assert _stop(o, "tekil").status_code == 200  # bobin 2
    n1 = estop_mandali.nesil()
    calisan = ap.calisan(o)
    with o.api._session_lock:
        aktif = bool(o.api._active_session.get("is_active"))
    _temizle(o)
    assert n1 == n0, f"çalışan seansta bobin STOP'u nesli artırdı ({n0}->{n1}) — seansın sürüş yetkisi kesilirdi"
    assert calisan == [1] and aktif, f"bobin STOP'u yalnız o bobini durdurmalı: çalışan {calisan}, seans aktif {aktif}"


def test_KARSIT_AI_Pro_seansinda_bobin_STOPu_nesle_DOKUNMAZ(o):
    from utils import estop_mandali

    _temizle(o)
    ap.muhurlu_seans_yaz(o.api, coil_ids=[1, 2])
    n0 = estop_mandali.nesil()
    assert _stop(o, "tekil").status_code == 200
    n1 = estop_mandali.nesil()
    _temizle(o)
    assert n1 == n0, f"AI Pro seansında tek bobin STOP'u nesli artırdı ({n0}->{n1}) — AI Pro sürüş yetkisi kesilirdi"
