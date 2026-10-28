# -*- coding: utf-8 -*-
"""Y209 (S-D5.4) — kimliksiz (eski istemci, APK 2.3.34) gözlem notunun AD eşleşmesi belirsizse not BUGÜNKÜ GİBİ en son bitmiş seansa
kaydedilir, AMA kayıt (`session_events`) ve ekran (bildirim + yanıttaki `uyari`) bunu söyler (TR + EN).

ÖLÇÜLEN (D5 DEV-D1§7.D2d · O-10.2): seanslar hastaya bağlı değilken (`patient_id` NULL — eski istemci yalnız ad gönderir) aynı adlı
birden çok bitmiş seans C2-2.1'in "farklı hasta kimliği" ölçütüne takılmıyor, not SESSİZCE en sonuncuya gidiyordu; kimse farkında değildi.
SAHİP KARARI Y209: davranış değişmez (not kaydedilir — eski istemcinin not yolu kırılmaz), yalnız uyarı. C2-2.1'in iki AYRI hasta
kimliğinde 409'u AYNEN kalır (o test dosyası ölçer). İz / olay hasta ADINI taşımaz.

GERÇEK: uçlar (TestClient), kayıtçı donanım, geçici DB (`ai_pro_aparati.kur`), canlı bildirim kaydı.
"""

from __future__ import annotations

import json
import time

import ai_pro_aparati as ap
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
            ns.c.post("/api/session/stop")
    finally:
        ns.geri()


def _seans(o, ad="Tarcin Y209", yas_s=600):
    r = o.c.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "intensity": 0,
            "duration_minutes": 20,
            "coil_ids": [1],
            "patient_name": ad,
        },
    )
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:300]
    sid = r.json()["session"]["db_session_id"]
    assert o.c.post("/api/session/stop").status_code == 200
    with o.db._get_connection() as c:
        c.execute("UPDATE treatment_sessions SET started_epoch = ? WHERE id = ?", (time.time() - yas_s, sid))
        c.commit()
    return sid


def _bellegi_sil(o):
    with o.api._session_lock:
        o.api._active_session.clear()


def _eski_not(o, ad="Tarcin Y209", metin="Y209 gozlem", dil=None):
    h = {"X-PEMF-Dil": dil} if dil else {}
    return o.c.post(
        "/api/session/notes",
        json={
            "notes": metin,
            "patient_name": ad,
            "mode": "Manuel",
            "frequency": 100,
            "intensity": 0,
            "duration_minutes": 20,
        },
        headers=h,
    )


def _not(o, sid):
    with o.db._get_connection() as c:
        return c.execute("SELECT COALESCE(patient_notes, '') FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[
            0
        ]


def _olaylar(o, sid):
    with o.db._get_connection() as c:
        return [
            (r[0], json.loads(r[1]))
            for r in c.execute(
                "SELECT severity, payload FROM session_events WHERE session_id = ? AND event_type = 'not_ad_eslesmesi_belirsiz'",
                (sid,),
            ).fetchall()
        ]


def test_KRITIK_ayni_adli_iki_KIMLIKSIZ_seans_not_EN_SONA_kaydedilir_ama_KAYIT_ve_EKRAN_uyarir(o):
    from utils import ceviri

    eski = _seans(o, yas_s=3600)
    yeni = _seans(o, yas_s=600)
    _bellegi_sil(o)  # hasta (ad) dalı: yeniden başlatma sonrası / başka istemci
    o.bildirim.clear()
    r = _eski_not(o)
    assert r.status_code == 200 and _not(o, yeni) == "Y209 gozlem" and _not(o, eski) == "", (
        f"Y209 'davranış bugünkü gibi': not en son seansa kaydedilmeliydi — {r.status_code} {r.text[:200]}"
    )
    assert r.json().get("uyari"), f"yanıt belirsiz eşleşmeyi SÖYLEMİYOR (ekran uyarısı yok): {r.json()}"
    ol = _olaylar(o, yeni)
    assert ol, "belirsiz eşleşme KAYDA (session_events) geçmedi"
    beklenen = ceviri.t("seans.uyari.notAdEslesmesiBelirsiz", dil="tr", aday=2)
    assert r.json()["uyari"] == beklenen, r.json()
    assert len(ol) == 1 and ol[0][0] == "warning" and ol[0][1].get("aday") == 2, f"belirsiz eşleşme KAYDA geçmedi: {ol}"
    assert "Tarcin" not in json.dumps(ol, ensure_ascii=False), "olay yükü hasta adını taşıyor"
    mesajlar = [m for m, _t in o.bildirim]
    assert any(m == ceviri.t("bildirim.notAdEslesmesiBelirsiz", dil="tr", aday=2) for m in mesajlar), (
        f"masaüstü ekranında (bildirim) uyarı yok: {mesajlar}"
    )


def test_uyari_X_PEMF_Dil_en_INGILIZCE(o):
    from utils import ceviri

    _seans(o, yas_s=3600)
    _seans(o, yas_s=600)
    _bellegi_sil(o)
    r = _eski_not(o, dil="en")
    assert r.status_code == 200 and r.json().get("uyari"), f"İngilizce istekte uyarı yok: {r.text[:200]}"
    assert r.json()["uyari"] == ceviri.t("seans.uyari.notAdEslesmesiBelirsiz", dil="en", aday=2)
    assert r.json()["uyari"] != ceviri.t("seans.uyari.notAdEslesmesiBelirsiz", dil="tr", aday=2)


def test_KARSIT_TEK_seans_ve_KIMLIKLI_istek_UYARISIZ(o):
    tek = _seans(o, ad="Mavis Y209", yas_s=600)
    _bellegi_sil(o)
    o.bildirim.clear()
    r = _eski_not(o, ad="Mavis Y209")
    assert r.status_code == 200 and "uyari" not in r.json() and _olaylar(o, tek) == [], r.text[:200]
    r2 = o.c.post(
        "/api/session/notes",
        json={
            "notes": "kimlikli",
            "patient_name": "Mavis Y209",
            "session_id": tek,
            "mode": "Manuel",
            "frequency": 100,
            "intensity": 0,
            "duration_minutes": 20,
        },
    )
    assert r2.status_code == 200 and "uyari" not in r2.json(), r2.text[:200]
    assert not any("Mavis" in m or "eşleş" in m for m, _t in o.bildirim), o.bildirim
