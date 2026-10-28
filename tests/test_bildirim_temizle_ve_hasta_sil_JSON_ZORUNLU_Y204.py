# -*- coding: utf-8 -*-
"""Y204 (S-D5.8) — `/api/notifications/clear` ve `/api/patients/{id}/delete` YALNIZ `application/json` isteği yürütür (Sıfırla emsali).

ÖLÇÜLEN DURUM (D5 C62 basit-POST envanteri, `c1aaba61`): iki uç da basit (ön-uçuşsuz) POST'u — gövdesiz, `text/plain`, form,
multipart — YÜRÜTÜYORDU: LAN'da ya da cihazda açılan herhangi bir sayfa çapraz kökenden güvenlik bildirimlerini (mandal yazılamadı, ACİL
DURDUR uyarısı) silebiliyor; operatörsüz klinikte kimliği bilen sayfa hasta silebiliyordu. Tarayıcı çapraz kökenden `application/json`
gövdesini ÖN-UÇUŞSUZ gönderemez (ön-uçuş CORS'ta düşer) → içerik türü şartı bu yolu kapatır. SAHİP KARARI Y204: "application/json değilse
415" (Sıfırla emsali). Arayüz ve yayındaki APK 2.3.34 iki uca da `apiPost(…, {})` ile JSON gönderir (kaynaktan ölçüldü) — uyumlu.
ACİL DURDUR basit POST'la YÜRÜMEYE DEVAM EDER (Ö.4-Y8; bu kapı onu da ölçer).

GERÇEK: uçlar (TestClient — LAN), hasta DB'si (geçici), canlı bildirim listesi; ölçüt yan etki (satır sayısı / liste) + yanıt kodu.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

_KOTU = {"Origin": "http://kotu.example"}


def _basit_istekler(c, yol, ek=None):
    """Tarayıcının çapraz kökenden ÖN-UÇUŞSUZ gönderebildiği biçimler (ad → yanıt)."""
    h = {**_KOTU, **(ek or {})}
    return {
        "govdesiz": c.post(yol, headers=h),
        "text_plain_bos": c.post(yol, headers={**h, "Content-Type": "text/plain"}, content=b""),
        "text_plain_json_gibi": c.post(yol, headers={**h, "Content-Type": "text/plain"}, content=b"{}"),
        "icerik_tursuz_blob": c.post(yol, headers=h, content=b"{}"),
        "form": c.post(yol, headers=h, data={"x": "1"}),
        "multipart": c.post(
            yol, headers=h, data={"x": "1"}, files={"f": ("f.bin", b"veri", "application/octet-stream")}
        ),
    }


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import operator_tokens, patient_router

    hdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: hdb)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: tdb)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    yerel = TestClient(api.app, client=("127.0.0.1", 53234))
    lan = TestClient(api.app, client=("192.168.1.96", 53235))
    for op in yerel.get("/api/operators").json().get("data", []):
        yerel.post("/api/operators/remove", json={"email": op["email"]})
    operator_tokens.temizle_hepsi()
    with api._live_state_lock:
        eski = list(api._live_state["notifications"])
    try:
        yield type("O", (), {"api": api, "hdb": hdb, "tdb": tdb, "lan": lan})
    finally:
        with api._live_state_lock:
            api._live_state["notifications"][:] = eski
        operator_tokens.temizle_hepsi()
        tdb.close_connections()


def _say(o):
    with o.hdb._get_connection() as c:
        return c.execute("SELECT COUNT(*) FROM patients").fetchone()[0]


def _bildirim_ekle(o):
    with o.api._live_state_lock:
        o.api._live_state["notifications"][:] = [{"message": "kapi-sahte-guvenlik-bildirimi", "type": "error"}]


def _bildirimler(o):
    with o.api._live_state_lock:
        return list(o.api._live_state["notifications"])


def test_KRITIK_hasta_silme_basit_POSTla_YURUMEZ_415_hasta_DURUR(o):
    from utils import ceviri

    pid = o.hdb.add_patient({"name": "Kalan", "species": "Kedi", "operator_email": ""})
    yanitlar = _basit_istekler(o.lan, f"/api/patients/{pid}/delete")
    kodlar = {ad: r.status_code for ad, r in yanitlar.items()}
    assert set(kodlar.values()) == {415}, f"basit (ön-uçuşsuz) POST hasta silme ucunu YÜRÜTTÜ / 415 değil: {kodlar}"
    assert _say(o) == 1, "basit POST hastayı SİLDİ (Y204 / S-D5.8)"
    beklenen = ceviri.t("hasta.hata.silmeJson", dil="tr")
    assert yanitlar["text_plain_json_gibi"].json().get("detail") == beklenen and "JSON" in beklenen, yanitlar[
        "govdesiz"
    ].text[:200]


def test_KRITIK_bildirim_temizleme_basit_POSTla_YURUMEZ_415_bildirimler_DURUR(o):
    from utils import ceviri

    kodlar, kalan = {}, {}
    for ad, r in _basit_istekler(o.lan, "/api/notifications/clear").items():
        kodlar[ad] = r.status_code
    _bildirim_ekle(o)
    for ad in ("govdesiz", "text_plain_json_gibi", "form", "multipart"):
        r = _basit_istekler(o.lan, "/api/notifications/clear")[ad]
        kalan[ad] = len(_bildirimler(o))
        assert r.status_code == 415, f"{ad}: {r.status_code} {r.text[:150]}"
    assert set(kodlar.values()) == {415}, (
        f"basit (ön-uçuşsuz) POST bildirim temizleme ucunu YÜRÜTTÜ / 415 değil: {kodlar}"
    )
    assert set(kalan.values()) == {1}, f"basit POST güvenlik bildirimlerini SİLDİ (Y204 / S-D5.8): {kalan}"
    r = o.lan.post("/api/notifications/clear", headers={**_KOTU, "Content-Type": "text/plain"}, content=b"{}")
    beklenen = ceviri.t("sistem.hata.bildirimTemizleJson", dil="tr")
    assert r.json().get("detail") == beklenen and "JSON" in beklenen, r.text[:200]


def test_ileti_X_PEMF_Dil_en_INGILIZCE_basliksiz_TURKCE(o):
    from utils import ceviri

    pid = o.hdb.add_patient({"name": "Dil", "species": "Kedi", "operator_email": ""})
    tr = o.lan.post(f"/api/patients/{pid}/delete", headers={"Content-Type": "text/plain"}, content=b"{}").json()[
        "detail"
    ]
    en = o.lan.post(
        f"/api/patients/{pid}/delete", headers={"Content-Type": "text/plain", "X-PEMF-Dil": "en"}, content=b"{}"
    ).json()["detail"]
    assert (
        tr == ceviri.t("hasta.hata.silmeJson", dil="tr")
        and en == ceviri.t("hasta.hata.silmeJson", dil="en")
        and tr != en
    )
    tr2 = o.lan.post("/api/notifications/clear", headers={"Content-Type": "text/plain"}, content=b"{}").json()["detail"]
    en2 = o.lan.post(
        "/api/notifications/clear", headers={"Content-Type": "text/plain", "X-PEMF-Dil": "en"}, content=b"{}"
    ).json()["detail"]
    assert tr2 == ceviri.t("sistem.hata.bildirimTemizleJson", dil="tr")
    assert en2 == ceviri.t("sistem.hata.bildirimTemizleJson", dil="en") and tr2 != en2
    assert _say(o) == 1


@pytest.mark.parametrize("icerik_turu", ["application/json", "application/json; charset=utf-8", "Application/JSON"])
def test_KARSIT_JSON_istek_YURUR_arayuz_ve_APK_2_3_34_bicimi(o, icerik_turu):
    """Arayüz / APK `apiPost(yol, {})` → `Content-Type: application/json` + `{}` gövde: iki uç da yürür."""
    p1 = o.hdb.add_patient({"name": "Silinecek", "species": "Kedi", "operator_email": ""})
    o.hdb.add_patient({"name": "Kalan", "species": "Kedi", "operator_email": ""})
    r = o.lan.post(f"/api/patients/{p1}/delete", headers={"Content-Type": icerik_turu}, content=b"{}")
    assert r.status_code == 200 and r.json()["status"] == "success" and _say(o) == 1, r.text[:200]
    _bildirim_ekle(o)
    r2 = o.lan.post("/api/notifications/clear", headers={"Content-Type": icerik_turu}, content=b"{}")
    assert r2.status_code == 200 and _bildirimler(o) == [], r2.text[:200]


def test_KARSIT_DELETE_yontemi_ve_ACIL_DURDUR_basit_POST_DEGISMEDI(o):
    """`DELETE /api/patients/{id}` ön-uçuş ister (basit yöntem değil) — dokunulmadı; ACİL DURDUR basit POST'la YÜRÜR (Ö.4-Y8)."""
    pid = o.hdb.add_patient({"name": "Del", "species": "Kedi", "operator_email": ""})
    assert o.lan.delete(f"/api/patients/{pid}").status_code == 200 and _say(o) == 0
    r = o.lan.post("/api/hardware/emergency_stop", headers={**_KOTU, "Content-Type": "text/plain"}, content=b"")
    assert r.status_code == 200, r.text[:200]
