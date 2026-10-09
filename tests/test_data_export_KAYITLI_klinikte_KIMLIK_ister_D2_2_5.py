# -*- coding: utf-8 -*-
"""D2-2.5 (2-D incelemesi A2 · Q6) — `/api/data/export` (kliniğin TAMAMI: hastalar, seanslar, bobin koşuları, sensör, AI — çağıranın
SEÇTİĞİ parolayla) kayıtlı operatörlü klinikte KİMLİK ister. [KARAR — önerilen seçenek, Y123 ile orkestratör uygular]

ÖLÇÜLEN TUTARSIZLIK [ÖLÇTÜM sonda k5 Q6]: S-D.1 (O-A3.7) kayıtlı operatörlü klinikte kimliksiz "Tümü" CSV'sini 428 yaptı (Y103'ün
dışa aktarma yüzü); ama AYNI klinikte jetonsuz bir LAN istemcisi `GET /api/auth/token` (A-01: LAN'a token verilir) → 200, ardından
`POST /api/data/export` + `X-API-Key` (operatör kimliği YOK) → 200 ve paket kendi seçtiği parolayla çözülünce 3 hasta / 3 seans / 3 AI
— başka hekimin 3 seansı dahil. Aynı token ile CSV "Tümü" 428. Tünelden token ile de 200. Yani S-D.1'in kapattığı sınıfın (kimliksiz
tek istekle tüm klinik dökümü) en geniş yüzü açık.

ÖNERİLEN (a): kayıtlı operatörlü klinikte jetonsuz istek 428 (`kimliksiz_detayi` — kimlik DB arızasında Y113 iletisi); kimlikli hekim
bugünkü gibi TÜM kliniği alır (rol modeli yok, A-28); operatörsüz klinik (Kural 2) DEĞİŞMEZ. Alternatifler: (b) yalnız cihaz DIŞI
(LAN/tünel) istek kimlik ister, cihazın kendi ekranı muaf; (c) bugünkü gibi (A-01 token = güven). Geri alma: yamanın revert'i.
"""

from __future__ import annotations

import base64

import pytest
from veri_tasima_aparati import PAROLA, cihaz_kur, doldur, istekler, kapat, uclari_bagla

AYSE = "dr.ayse.d225@klinik.invalid"
MEHMET = "dr.mehmet.d225@klinik.invalid"
LAN = ("192.168.1.95", 53395)


@pytest.fixture
def cihaz(tmp_path, monkeypatch):
    from servers import api_server as api
    from servers import auth, operator_tokens

    monkeypatch.setattr(auth, "check_token", lambda t: t == "CIHAZ-TOKEN")
    monkeypatch.setattr(auth, "get_api_token", lambda: "CIHAZ-TOKEN")
    tdb, hdb = cihaz_kur(monkeypatch, tmp_path / "B")
    uclari_bagla(monkeypatch, tdb, hdb)
    doldur(tdb, hdb, ["Zeytin", "Boncuk"], seans_basi=1, operator=MEHMET)
    doldur(tdb, hdb, ["Mia"], seans_basi=1, operator=AYSE)
    operator_tokens.temizle_hepsi()
    try:
        yield api.app
    finally:
        for op in istekler(api.app, [("GET", "/api/operators", None, None)])[0].json().get("data", []):
            istekler(api.app, [("POST", "/api/operators/remove", {"email": op["email"]}, None)])
        operator_tokens.temizle_hepsi()
        kapat(tdb, hdb)


def _kayit(app) -> str:
    r = istekler(
        app, [("POST", "/api/operators/enroll", {"email": AYSE, "display_name": "Dr. Ayşe", "pin": "123456"}, None)]
    )
    assert r[0].status_code == 200, r[0].text[:200]
    return istekler(app, [("POST", "/api/operators/verify", {"email": AYSE, "pin": "123456"}, None)])[0].json()[
        "operator_token"
    ]


def _lan_tokeni(app) -> str:
    (t,) = istekler(app, [("GET", "/api/auth/token", None, None)], client=LAN)
    assert t.status_code == 200, "aparat: A-01 LAN token akışı"
    return t.json()["token"]


@pytest.mark.parametrize("yer", ["LAN_token", "tunel_token", "cihazin_kendisi"])
def test_KRITIK_D2_2_5_kayitli_operatorlu_klinikte_KIMLIKSIZ_tum_klinik_paketi_VERILMEZ_428(cihaz, yer):
    _kayit(cihaz)
    token = _lan_tokeni(cihaz)
    bas, client = {
        "LAN_token": ({"X-API-Key": token}, LAN),
        "tunel_token": (
            {"X-API-Key": token, "cf-ray": "d225", "cf-connecting-ip": "203.0.113.9"},
            ("127.0.0.1", 53396),
        ),
        "cihazin_kendisi": ({}, ("127.0.0.1", 53397)),
    }[yer]
    (r,) = istekler(
        cihaz, [("POST", "/api/data/export", {"passphrase": "SALDIRGAN-parolasi-d225"}, bas)], client=client
    )
    g = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    hasta = 0
    if r.status_code == 200 and g.get("data_b64"):
        from utils.data_export import decrypt_bundle

        hasta = len(decrypt_bundle(base64.b64decode(g["data_b64"]), "SALDIRGAN-parolasi-d225").get("patient_db") or [])
    assert r.status_code == 428 and "data_b64" not in g, (
        f"kayıtlı operatörlü klinikte KİMLİKSİZ istek ({yer}) kliniğin tamamını aldı: {r.status_code}, paketteki hasta={hasta} "
        "(aynı istemciye CSV 'Tümü' 428 — S-D.1)"
    )
    assert "Operatör seçin" in g.get("detail", "")


def test_KARSIT_D2_2_5_KIMLIKLI_hekim_LANdan_tum_klinigi_alir_A01_A28(cihaz):
    jeton = _kayit(cihaz)
    token = _lan_tokeni(cihaz)
    (r,) = istekler(
        cihaz,
        [("POST", "/api/data/export", {"passphrase": PAROLA}, {"X-API-Key": token, "X-PEMF-Operator": jeton})],
        client=LAN,
    )
    assert r.status_code == 200, r.text[:300]
    from utils.data_export import decrypt_bundle

    paket = decrypt_bundle(base64.b64decode(r.json()["data_b64"]), PAROLA)
    assert len(paket["patient_db"]) == 3 and len(paket["treatment_sessions"]) == 3, (
        "rol modeli yok: kimlikli hekim TÜMÜNÜ alır"
    )


def test_KARSIT_D2_2_5_OPERATORSUZ_klinik_Kural2_bugunku_gibi(cihaz):
    token = _lan_tokeni(cihaz)
    (r,) = istekler(cihaz, [("POST", "/api/data/export", {"passphrase": PAROLA}, {"X-API-Key": token})], client=LAN)
    assert r.status_code == 200 and r.json().get("data_b64"), r.text[:300]
