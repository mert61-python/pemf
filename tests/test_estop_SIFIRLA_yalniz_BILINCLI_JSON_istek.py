# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.81 · Y4 · 1-C bağımsız inceleme i3-F-6 — "Sıfırla" yalnız BİLİNÇLİ istekle: `Content-Type: application/json` +
`{"onay": true}`. Yetki modeli (A-01) değişmez: tünel/uzak kimliksiz 401; LAN ve yerel açık.

ÖLÇÜLEN KUSUR (i3): uç gövdesiz/JSON'suz POST'u kabul ediyor ve Origin'e bakmıyordu → LAN'daki ya da cihazdaki bir
tarayıcıda açılan HERHANGİ bir sayfa, operatör eylemi olmadan "basit" (ön-uçuşsuz) bir POST ile mandalı kaldırabiliyordu
(`Origin: http://kotu.example`, `Content-Type: text/plain`, gövdesiz → HTTP 200, mandal kalktı). START uçları JSON gövde
istediği için ön-uçuş + LAN CORS'tan geçer; Sıfırla geçmiyordu.
DÜZELTME: uç `application/json` içerik türü VE `{"onay": true}` ister. Tarayıcı çapraz kökenden JSON'u ön-uçuşsuz
gönderemez (ön-uçuş CORS'ta düşer); içerik türsüz "Blob" gövdesi de reddedilir. Aynı köken (tünel web arayüzü), mobil
(Origin yok) ve LAN arayüzü çalışır. (Origin listesi denetimi SEÇİLMEDİ: tünelden açılan web arayüzünün kendi kökeni LAN
listesinde değildir → meşru uzaktan Sıfırla'yı 403'e düşürürdü.) Denetim izi istemci adresini ve kökeni de yazar
(oturumsuz ekrandan yapılan sıfırlamada `operator` boştur — "kim" en azından NEREDEN ile izlenir).
Jeton yalnız bu teste özgü sahte dize (sır değil).
"""

from __future__ import annotations

import pytest

_SAHTE_TOKEN = "kapi-sahte-test-tokeni"
_ONAY = {"onay": True}


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    from servers import api_server as api
    from servers import auth

    monkeypatch.setenv("PEMF_REQUIRE_AUTH", "1")
    monkeypatch.setenv("PEMF_API_TOKEN", _SAHTE_TOKEN)
    for ad in ("_require", "_token", "_LOOPBACK_BIND", "_TRUSTED_PROXIES"):
        monkeypatch.setattr(auth, ad, None)
    monkeypatch.setattr(auth, "_warned", True)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 0)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api, "_estop_ack_watch", lambda *a, **k: None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    monkeypatch.setattr(api.state, "hardware", None)
    monkeypatch.setitem(api._active_session, "is_active", False)
    olaylar: list = []

    class _Db:
        def record_session_event(self, *a, **k):
            olaylar.append((a, k))

    monkeypatch.setattr(api, "_get_treatment_db", lambda: _Db())
    api.olaylar = olaylar
    yield api


def _dene(api, ip: str, **istek):
    from fastapi.testclient import TestClient
    from utils import estop_mandali as m

    m.mandalla("manual")
    assert m.mandalli_mi(), "aparat: mandal kurulmadı"
    c = TestClient(api.app, client=(ip, 50123))
    r = c.post("/api/hardware/estop_mandali/sifirla", **istek)
    kaldirildi = not m.mandalli_mi()
    es = c.post(
        "/api/hardware/emergency_stop",
        headers={k: v for k, v in istek.get("headers", {}).items() if k != "Content-Type"},
    )
    m.sifirla("test")
    return r, kaldirildi, es


_TUNEL = {"cf-connecting-ip": "203.0.113.7", "cf-ray": "x"}
# ad: (istemci_ip, istek, beklenen_kaldirildi)
_DURUMLAR = {
    "tunel_tokensiz_onayli": ("127.0.0.1", {"headers": _TUNEL, "json": _ONAY}, False),
    "tunel_tokenli_onayli": ("127.0.0.1", {"headers": {**_TUNEL, "X-API-Key": _SAHTE_TOKEN}, "json": _ONAY}, True),
    "lan_onayli": ("192.168.1.50", {"json": _ONAY}, True),
    "loopback_onayli": ("127.0.0.1", {"json": _ONAY}, True),
    # ── bilinçsiz / çapraz köken istekleri (KRİTİK) ──
    "lan_capraz_koken_basit_POST_text_plain": (
        "192.168.1.50",
        {"headers": {"Origin": "http://kotu.example", "Content-Type": "text/plain"}, "content": b'{"onay": true}'},
        False,
    ),
    "lan_icerik_turu_YOK_blob_govde": (
        "192.168.1.50",
        {"headers": {"Origin": "http://kotu.example"}, "content": b'{"onay": true}'},
        False,
    ),
    "lan_form_POST": ("192.168.1.50", {"headers": {"Origin": "http://kotu.example"}, "data": {"onay": "true"}}, False),
    "loopback_govdesiz": ("127.0.0.1", {}, False),
    "loopback_json_onaysiz": ("127.0.0.1", {"json": {}}, False),
    "loopback_json_onay_false": ("127.0.0.1", {"json": {"onay": False}}, False),
    "loopback_json_onay_metin": ("127.0.0.1", {"json": {"onay": "true"}}, False),
}


@pytest.mark.parametrize("durum", list(_DURUMLAR))
def test_KRITIK_sifirla_YALNIZ_bilincli_JSON_istekle_ve_A01_yetkisiyle(ortam, durum):
    ip, istek, beklenen = _DURUMLAR[durum]
    r, kaldirildi, es = _dene(ortam, ip, **istek)
    assert kaldirildi is beklenen, (
        f"{durum}: beklenen kaldirildi={beklenen}, ölçülen {kaldirildi} (HTTP {r.status_code})"
    )
    if not beklenen:
        assert r.status_code >= 400, f"{durum}: mandal kalkmadı ama HTTP {r.status_code} (başarı görünümü)"
    assert es.status_code == 200, f"{durum}: ACİL DURDUR {es.status_code} (Ö.4-Y8: hiçbir şeye kapılanmaz)"


def test_KRITIK_SIFIRLA_denetim_izi_ISTEMCI_ve_KOKENI_tasir(ortam):
    r, kaldirildi, _es = _dene(ortam, "192.168.1.50", json=_ONAY, headers={"Origin": "http://192.168.1.50:8000"})
    assert r.status_code == 200 and kaldirildi
    izler = [
        k.get("payload") or (a[2] if len(a) > 2 else None) for a, k in ortam.olaylar if "estop_mandali_sifirlandi" in a
    ]
    assert izler, f"aparat: denetim izi yazılmadı {ortam.olaylar}"
    iz = izler[-1]
    assert iz.get("istemci") == "192.168.1.50" and iz.get("koken") == "http://192.168.1.50:8000", (
        f"Sıfırla denetim izi istemci adresini/kökeni taşımıyor (oturumsuz ekranda 'kim' boş): {iz}"
    )
