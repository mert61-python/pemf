# -*- coding: utf-8 -*-
"""O-A2.3 (2-B incelemesi, düşük) — silme / dışa-içe aktarma izinde kimlik işlemden SONRA istekten yeniden çözülmez.

C2-3.3 kimliği istek başına BİR KEZ çözüp ASGI `scope`'ta tutar (`servers.auth._jeton_kimligi`); bu, kimlik işlemden ÖNCE çözülmüşse
korur. Silme uçları kapıda (`sahiplik_kapisi` / tekil AI silme) ve DOLU cihaz geri yüklemesi kimliği işlemden önce çözüyor (kapı:
`test_silme_ve_not_BASARI_IZI_kilit_yarisinda_YETKILENDIREN_hekim_C2_3_3.py`). ÖLÇÜLEN KALINTI: BOŞ cihaza ilk içe aktarma kimliği
hiç çözmeden işleme giriyor, başarı izi sonda İLK KEZ çözüyordu → işlem sürerken aynı hekimin "Kilitle"si izi SAHİPSİZ bırakıyordu
(içe aktarılan kliniğin geçmişinin tek kanıtı). Dışa aktarma kayıtlı operatörlü klinikte kimliği kapıda çözer (KARŞIT).
GERÇEK: iki cihaz (gerçek DB'ler), gerçek `/api/data/export` paketi, gerçek `/api/data/import`, operatör kaydı/jetonu; "Kilitle" =
`operator_tokens.iptal` (POST /api/operators/lock'un yaptığı) içe aktarma işleminin İÇİNDE.
"""

from __future__ import annotations

import pytest
from veri_tasima_aparati import PAROLA, cihaz_kur, disa_aktar, doldur, istekler, kapat, uclari_bagla

AYSE = "dr.ayse@klinik.com"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from servers import api_server as api
    from servers import auth, operator_tokens

    monkeypatch.setattr(auth, "check_token", lambda t: t == "CIHAZ-TOKEN")
    ta, ha = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, ta, ha)
    doldur(ta, ha, ["Mia"], seans_basi=1)
    paket = disa_aktar(api.app)
    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")  # BOŞ hedef
    uclari_bagla(monkeypatch, tb, hb)
    operator_tokens.temizle_hepsi()
    try:
        yield type("O", (), {"api": api, "paket": paket, "tb": tb, "hb": hb})
    finally:
        for op in istekler(api.app, [("GET", "/api/operators", None, None)])[0].json().get("data", []):
            istekler(api.app, [("POST", "/api/operators/remove", {"email": op["email"]}, None)])
        operator_tokens.temizle_hepsi()
        kapat(ta, ha, tb, hb)


def _jeton(o) -> str:
    r1, r2 = istekler(
        o.api.app,
        [
            ("POST", "/api/operators/enroll", {"email": AYSE, "display_name": "Ayse", "pin": "123456"}, None),
            ("POST", "/api/operators/verify", {"email": AYSE, "pin": "123456"}, None),
        ],
    )
    assert r1.status_code == 200, r1.text[:200]
    return r2.json()["operator_token"]


def _islem_icinde_kilitle(monkeypatch, db, ad, jeton):
    from servers import operator_tokens

    orj = getattr(db, ad)

    def _sar(*a, **k):
        operator_tokens.iptal(jeton)  # işlem sürerken "Kilitle"
        return orj(*a, **k)

    monkeypatch.setattr(db, ad, _sar)


def test_KRITIK_OA23_bos_cihaza_ice_aktarma_SURERKEN_Kilitle_iz_YETKILENDIREN_hekimin_adina(o, monkeypatch):
    """MUTASYON: içe aktarma başında kimlik çözümü kaldırılır → KIRMIZI (iz sahipsiz)."""
    j = _jeton(o)
    _islem_icinde_kilitle(monkeypatch, o.tb, "import_rows", j)
    (r,) = istekler(
        o.api.app,
        [("POST", "/api/data/import", {"passphrase": PAROLA, "blob_b64": o.paket["data_b64"]}, {"X-PEMF-Operator": j})],
    )
    assert r.status_code == 200, r.text[:300]
    izler = [x for x in o.tb.denetim_oku(20, "data.import") if x.get("outcome") not in ("reddedildi",)]
    assert izler, "aparat: içe aktarma izi yok"
    assert izler[0]["operator_email"] == AYSE, (
        f"içe aktarma sürerken 'Kilitle' → başarı izi SAHİPSİZ ({izler[0]['operator_email']!r}) — kimlik işlemden SONRA çözülüyor (O-A2.3)"
    )


def test_KARSIT_istekten_ONCE_iptal_edilmis_jetonla_iz_SAHIPSIZ(o):
    """Araç kör değil: istekten ÖNCE iptal edilmiş jeton yine boş çözülür (iz kimliği gerçekten jetondan gelir)."""
    from servers import operator_tokens

    j = _jeton(o)
    operator_tokens.iptal(j)
    (r,) = istekler(
        o.api.app,
        [("POST", "/api/data/import", {"passphrase": PAROLA, "blob_b64": o.paket["data_b64"]}, {"X-PEMF-Operator": j})],
    )
    assert r.status_code == 200, r.text[:300]
    izler = [x for x in o.tb.denetim_oku(20, "data.import") if x.get("outcome") not in ("reddedildi",)]
    assert izler and not izler[0]["operator_email"], izler[:1]


def test_KARSIT_disa_aktarma_kayitli_klinikte_kimligi_KAPIDA_cozer(o, monkeypatch):
    j = _jeton(o)
    _islem_icinde_kilitle(monkeypatch, o.tb, "export_rows", j)
    (r,) = istekler(o.api.app, [("POST", "/api/data/export", {"passphrase": PAROLA}, {"X-PEMF-Operator": j})])
    assert r.status_code == 200, r.text[:300]
    izler = o.tb.denetim_oku(20, "data.export")
    assert izler and izler[0]["operator_email"] == AYSE, izler[:1]
