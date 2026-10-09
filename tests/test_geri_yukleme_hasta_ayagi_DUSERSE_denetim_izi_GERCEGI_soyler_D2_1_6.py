# -*- coding: utf-8 -*-
"""D2-1.6 (2-D incelemesi, A1) — REPLACE_ALL'da hasta ayağı (patients.db) tedavi commit'inden SONRA düşerse DENETİM İZİ "ok" der.

ÖLÇÜLEN KUSUR (HEAD a76ee0d, `servers/api_server.py::_ice_aktar`): tedavi DB'si yedektekiyle değiştirildikten sonra hasta kartlarının
eklenmesi düşerse (patients.db yazılamıyor) yanıt `200 status=success`, `uyari` yalnız Y12 metnini taşır; `data.import` denetim kaydı
`outcome='ok'` ve `detail`'de başarısız / zaten-var sayısı YOK [ÖLÇTÜM sonda: "hasta": 0, outcome ok]. Arayüz `counts.patient_db_basarisiz`
ile hata tostu gösteriyor — ama "hangi geri yükleme neyi değiştirdi" sorusunun TEK kalıcı cevabı olan iz (A-07: kritik olay süresiz) yarım
kalan geri yüklemeyi başarılı diye saklıyor; yanıtın insan-okur `uyari`'sı da susuyor.
DÜZELTME: iz `outcome='kismi'` + `hasta_basarisiz` / `hasta_zaten_vardi`; `uyari` aktarılamayan hasta sayısını söyler. Normal yol DEĞİŞMEZ.
SAHTE EN ALT KATTA: patients.db'de SQLite'ın kendi tetikleyicisi hasta eklemesini reddeder (G-Ç / kilit hatasının yerine). Uç, şifreleme,
paket, iz GERÇEK (httpx ASGITransport, cihazın kendisi = 127.0.0.1).
"""

from __future__ import annotations

import json

import pytest
from veri_tasima_aparati import PAROLA, cihaz_kur, disa_aktar, doldur, istekler, kapat, uclari_bagla


@pytest.fixture
def iki(tmp_path, monkeypatch):
    from servers import api_server as api

    ta, ha = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, ta, ha)
    doldur(ta, ha, ["Mia", "Pamuk"], seans_basi=2)
    paket = disa_aktar(api.app)
    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")
    uclari_bagla(monkeypatch, tb, hb)
    doldur(tb, hb, ["Zeytin"], seans_basi=1)
    try:
        yield api, paket, tb, hb
    finally:
        kapat(ta, ha, tb, hb)


def _ice_aktar(api, paket):
    govde = {"passphrase": PAROLA, "blob_b64": paket["data_b64"], "confirm": "REPLACE_ALL"}
    (r,) = istekler(api.app, [("POST", "/api/data/import", govde, None)])
    return r


def _iz(tb):
    with tb._get_connection() as c:
        return [
            (o, json.loads(d or "{}"))
            for o, d in c.execute(
                "SELECT outcome, detail FROM audit_events WHERE event_type='data.import' ORDER BY id"
            ).fetchall()
        ]


def test_KRITIK_hasta_ayagi_DUSERSE_denetim_izi_ve_uyari_GERCEGI_soyler(iki):
    api, paket, tb, hb = iki
    with hb._get_connection() as c:
        c.execute(
            "CREATE TRIGGER d216_hasta_dusur BEFORE INSERT ON patients BEGIN SELECT RAISE(ABORT, 'disk I/O error (aparat)'); END;"
        )
        c.commit()
    r = _ice_aktar(api, paket)
    g = r.json()
    assert r.status_code == 200 and g["counts"]["patient_db_basarisiz"] == 2, f"aparat: {r.status_code} {r.text[:300]}"
    iz = _iz(tb)
    assert iz, "aparat: data.import denetim kaydı yok"
    outcome, detail = iz[-1]
    assert outcome != "ok", (
        f"2 hasta kartı içe AKTARILAMADI ama denetim izi outcome='{outcome}' (detail={detail}) — yarım geri yükleme izde başarılı görünüyor"
    )
    assert detail.get("hasta_basarisiz") == 2, f"denetim izinde aktarılamayan hasta sayısı yok: {detail}"
    assert "aktarılamadı" in (g.get("uyari") or "").lower(), (
        f"yanıtın uyarısı aktarılamayan hastaları söylemiyor: {g.get('uyari')!r}"
    )


def test_KARSIT_normal_geri_yuklemede_iz_ok_ve_uyari_yalniz_Y12(iki):
    api, paket, tb, hb = iki
    r = _ice_aktar(api, paket)
    g = r.json()
    assert r.status_code == 200 and g["counts"]["patient_db_basarisiz"] == 0
    outcome, detail = _iz(tb)[-1]
    assert outcome == "ok", f"normal geri yükleme izde '{outcome}'"
    assert "aktarılamadı" not in (g.get("uyari") or "").lower()
    assert "Yedekte olmayan 1 hastanın kartı korundu" in (g.get("uyari") or ""), "Y12 uyarısı bozuldu"
