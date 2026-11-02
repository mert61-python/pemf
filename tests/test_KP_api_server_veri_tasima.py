# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: cihaz TAŞIMA (yedek) hata yolları — `/api/data/export` (tedavi DB'si
yok → 500; zayıf parola `ExportError` → 400 + ürünün parola gerekçesi; tablo okuması patlarsa 500; round-trip doğrulaması
tutmazsa 500 ve günlükte tablo/sayılar; zamanlama (`ensure_future`) düşerse kilit BIRAKILIR, sonraki yedek alınır), `_disa_aktar`
(geri yükleme kilidi arada alındıysa 409), `/api/data/import` (tedavi DB'si yok → 500; zamanlama düşerse kilit bırakılır; cihaz
DIŞI istekte hızlı doluluk sorgusu geçici kilitle düşerse tam yol karar verir → 403 + "reddedildi" denetim izi, kayıt değişmez;
v1 yedeğinde hasta kartları `patients` anahtarından alınır), `_yedegi_masaustune_yaz` (geçici dosya taşınamazsa ÖZGÜN hata
yükselir, geçici dosya silinemese de; doğrulanamayan hedef silinemese de "DOĞRULANAMADI" hatası yükselir).

Sahte EN ALT katta: DB'ler GERÇEK (`veri_tasima_aparati`: tmp'de `TreatmentHistoryDB` + `PatientDatabase`); arızalar DB yöntemi /
bağlantı düzeyinde `sqlite3.OperationalError`, olay döngüsü zamanlaması (`asyncio.ensure_future` → `RuntimeError`), dosya sistemi
(`os.replace` / `Path.unlink` → `PermissionError`, `Path.read_bytes` bozuk bayt), masaüstü dizini (`seans_alan_kaydi.masaustu_dizini`
→ tmp), cihaz jetonu (`auth.check_token`).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import sqlite3
from pathlib import Path

import httpx
import pytest
import veri_tasima_aparati as vta

LAN = ("192.168.1.80", 52011)
CIHAZ = ("127.0.0.1", 50131)
JETON = "KP-CIHAZ-JETONU"


def _tr(anahtar, **k):
    from utils import ceviri

    return ceviri.t(anahtar, dil="tr", **k)


def _istek(app, yontem, yol, govde=None, client=CIHAZ, basliklar=None, hata_yukselt=True):
    async def _kos():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=client, raise_app_exceptions=hata_yukselt),
            base_url="http://cihaz",
            timeout=60,
        ) as c:
            return await c.request(yontem, yol, json=govde, headers=basliklar or {})

    return asyncio.run(_kos())


@pytest.fixture
def o(tmp_path, monkeypatch):
    from servers import api_server as a
    from servers import auth

    monkeypatch.setattr(auth, "check_token", lambda t: t == JETON)
    monkeypatch.setattr(a, "_RL_REMOTE_MAX", 0)
    tdb, hdb = vta.cihaz_kur(monkeypatch, tmp_path / "A")
    vta.uclari_bagla(monkeypatch, tdb, hdb)
    acik = [tdb, hdb]

    class _O:
        pass

    ns = _O()
    ns.a, ns.tdb, ns.hdb, ns.acik, ns.tmp = a, tdb, hdb, acik, tmp_path
    try:
        yield ns
    finally:
        for kilit in (a._VERI_TASIMA_KILIDI, a._DISA_AKTARMA_KILIDI):
            assert not kilit.locked(), "test sonunda veri taşıma kilidi TUTULU kaldı"
        vta.kapat(*acik)


class _AsyncioVekil:
    """Gerçek `asyncio` modülüne yönlendirir; yalnız `ensure_future` olay döngüsü kapanırkenki gibi düşer (eşyordamı kapatır)."""

    def __init__(self, gercek):
        self._gercek = gercek
        self.denenen = 0

    def __getattr__(self, ad):
        return getattr(self._gercek, ad)

    def ensure_future(self, coro, *a, **k):
        self.denenen += 1
        coro.close()
        raise RuntimeError("cannot schedule new futures after interpreter shutdown")


def _paket_b64(paket: dict) -> str:
    from utils.data_export import encrypt_bundle

    return base64.b64encode(encrypt_bundle(paket, vta.PAROLA)).decode("ascii")


# ── /api/data/export ───────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_DISA_AKTARMA_tedavi_DB_YOKSA_500_db_hazir_degil(o, monkeypatch):
    """Tedavi DB'si yok (`_get_treatment_db` None) → 500 `yedek.hata.dbHazirDegil`; dışa aktarma kilidi bırakılır."""
    monkeypatch.setattr(o.a, "_get_treatment_db", lambda: None)
    r = _istek(o.a.app, "POST", "/api/data/export", {"passphrase": vta.PAROLA})
    assert r.status_code == 500
    assert r.json()["detail"] == _tr("yedek.hata.dbHazirDegil")


def test_DISA_AKTARMA_zayif_parola_ExportError_400_urun_gerekcesi(o):
    """Parola politikayı geçmiyor ("abc") → `encrypt_bundle` ExportError → 400, detay ürünün kendi parola gerekçesi."""
    from utils.data_export import parola_gecerli_mi

    vta.doldur(o.tdb, o.hdb, ["Mia"], seans_basi=1)
    gecerli, sebep = parola_gecerli_mi("abc")
    assert gecerli is False and sebep
    r = _istek(o.a.app, "POST", "/api/data/export", {"passphrase": "abc"})
    assert r.status_code == 400
    assert r.json()["detail"] == sebep


def test_DISA_AKTARMA_tablo_okumasi_PATLARSA_500_genel_hata_gunlukte(o, monkeypatch, caplog):
    """`export_rows` OperationalError (bozuk DB) → 500 `yedek.hata.disaAktarBasarisiz`, günlükte "data export failed"."""

    def _bozuk():
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(o.tdb, "export_rows", _bozuk)
    caplog.set_level(logging.ERROR)
    r = _istek(o.a.app, "POST", "/api/data/export", {"passphrase": vta.PAROLA})
    assert r.status_code == 500
    assert r.json()["detail"] == _tr("yedek.hata.disaAktarBasarisiz")
    assert "data export failed" in [x.getMessage() for x in caplog.records]


def test_DISA_AKTARMA_round_trip_SAYISI_TUTMAZSA_500_ve_tablo_gunlukte(o, monkeypatch, caplog):
    """2 hasta × 2 seans; çözülen paket bir seans EKSİK döner (bozuk şifreli dosya) → 500 `yedek.hata.dogrulanamadi`, günlükte
    "round-trip doğrulaması BAŞARISIZ (treatment_sessions: 3 != 4)"; yanıtta paket YOK."""
    from utils import data_export as de

    vta.doldur(o.tdb, o.hdb, ["Mia", "Pamuk"], seans_basi=2)
    gercek = de.decrypt_bundle

    def _eksik_donen(blob, parola):
        p = gercek(blob, parola)
        p["treatment_sessions"] = list(p.get("treatment_sessions") or [])[:-1]
        return p

    monkeypatch.setattr(de, "decrypt_bundle", _eksik_donen)
    caplog.set_level(logging.ERROR)
    r = _istek(o.a.app, "POST", "/api/data/export", {"passphrase": vta.PAROLA})
    assert r.status_code == 500
    assert r.json() == {"detail": _tr("yedek.hata.dogrulanamadi")}
    assert "VERİ TAŞIMA: round-trip doğrulaması BAŞARISIZ (treatment_sessions: 3 != 4)" in [
        x.getMessage() for x in caplog.records
    ]


def test_DISA_AKTARMA_zamanlama_DUSERSE_kilit_BIRAKILIR_sonraki_yedek_200(o, monkeypatch):
    """`ensure_future` RuntimeError (olay döngüsü kapanıyor) → 500 ve `_DISA_AKTARMA_KILIDI` BIRAKILIR; zamanlama düzelince aynı
    cihazın sonraki dışa aktarması 409 "yedek alma sürüyor" ALMAZ, 200 döner."""
    vta.doldur(o.tdb, o.hdb, ["Mia"], seans_basi=1)
    vekil = _AsyncioVekil(asyncio)
    monkeypatch.setattr(o.a, "asyncio", vekil)
    r = _istek(o.a.app, "POST", "/api/data/export", {"passphrase": vta.PAROLA}, hata_yukselt=False)
    assert r.status_code == 500 and vekil.denenen == 1
    assert not o.a._DISA_AKTARMA_KILIDI.locked()
    monkeypatch.setattr(o.a, "asyncio", asyncio)
    r2 = _istek(o.a.app, "POST", "/api/data/export", {"passphrase": vta.PAROLA})
    assert r2.status_code == 200, r2.text[:200]
    assert r2.json()["counts"]["treatment_sessions"] == 1


def test_DISA_AKTARMA_govdesi_GERI_YUKLEME_kilidi_arada_alindiysa_409(o):
    """Uç kilidi denetleyip görevi zamanladıktan sonra geri yükleme kilidi alındı → `_disa_aktar` 409 `geriYuklemeSuruyor`
    (yarım içe aktarılmış durum yedek diye verilmez); tablolar okunmaz."""
    from fastapi import HTTPException
    from starlette.requests import Request

    okunan: list = []
    o.tdb.export_rows = lambda: okunan.append(1) or {}
    istek = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/data/export",
            "raw_path": b"/api/data/export",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [(b"host", b"127.0.0.1")],
            "client": CIHAZ,
            "server": ("127.0.0.1", 80),
            "app": o.a.app,
        }
    )
    assert o.a._VERI_TASIMA_KILIDI.acquire(blocking=False)
    try:
        with pytest.raises(HTTPException) as e:
            asyncio.run(o.a._disa_aktar(o.a.DataExportPayload(passphrase=vta.PAROLA), istek))
    finally:
        o.a._VERI_TASIMA_KILIDI.release()
    assert (e.value.status_code, e.value.detail) == (409, _tr("yedek.hata.geriYuklemeSuruyor"))
    assert okunan == []


# ── /api/data/import ───────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_ICE_AKTARMA_tedavi_DB_YOKSA_500_db_hazir_degil(o, monkeypatch):
    """Tedavi DB'si yok → 500 `yedek.hata.dbHazirDegil`; veri taşıma kilidi bırakılır."""
    vta.doldur(o.tdb, o.hdb, ["Mia"], seans_basi=1)
    paket = vta.disa_aktar(o.a.app, client=CIHAZ)
    monkeypatch.setattr(o.a, "_get_treatment_db", lambda: None)
    r = _istek(o.a.app, "POST", "/api/data/import", {"passphrase": vta.PAROLA, "blob_b64": paket["data_b64"]})
    assert r.status_code == 500
    assert r.json()["detail"] == _tr("yedek.hata.dbHazirDegil")


def test_ICE_AKTARMA_zamanlama_DUSERSE_veri_tasima_kilidi_BIRAKILIR(o, monkeypatch):
    """`ensure_future` RuntimeError → 500 ve `_VERI_TASIMA_KILIDI` bırakılır: ardından dışa aktarma 409 "geri yükleme sürüyor"
    ALMAZ (200)."""
    vta.doldur(o.tdb, o.hdb, ["Mia"], seans_basi=1)
    paket = vta.disa_aktar(o.a.app, client=CIHAZ)
    vekil = _AsyncioVekil(asyncio)
    monkeypatch.setattr(o.a, "asyncio", vekil)
    r = _istek(
        o.a.app,
        "POST",
        "/api/data/import",
        {"passphrase": vta.PAROLA, "blob_b64": paket["data_b64"]},
        hata_yukselt=False,
    )
    assert r.status_code == 500 and vekil.denenen == 1
    assert not o.a._VERI_TASIMA_KILIDI.locked()
    monkeypatch.setattr(o.a, "asyncio", asyncio)
    assert _istek(o.a.app, "POST", "/api/data/export", {"passphrase": vta.PAROLA}).status_code == 200


def test_ICE_AKTARMA_LAN_hizli_doluluk_KILITLE_duserse_TAM_yol_403_ve_red_izi(o, monkeypatch):
    """Hedef yalnız hasta kartı taşıyor (tedavi tabloları boş); LAN'dan jetonlu REPLACE_ALL; hızlı doluluk sorgusundaki hasta
    okuması bir kez "database is locked" → hızlı yol "boş" sayar, TAM yol hastayı görür → 403 `cihazDisiGeriYukleme`, denetim
    izine `data.import` / `reddedildi` / {"neden": "cihaz_disi"} yazılır; hedefin kayıt sayıları DEĞİŞMEZ."""
    import json

    vta.doldur(o.tdb, o.hdb, ["Mia", "Pamuk"], seans_basi=1)
    paket = vta.disa_aktar(o.a.app, client=CIHAZ)
    tb, hb = vta.cihaz_kur(monkeypatch, o.tmp / "B")
    o.acik += [tb, hb]
    vta.uclari_bagla(monkeypatch, tb, hb)
    hb.add_patient({"name": "Zeytin", "species": "Kedi", "owner": "z-sahibi"})
    once = vta.sayimlar(tb, hb)
    gercek = hb.get_all_patients
    cagri = {"n": 0}

    def _ilki_kilitli(*x, **k):
        cagri["n"] += 1
        if cagri["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return gercek(*x, **k)

    monkeypatch.setattr(hb, "get_all_patients", _ilki_kilitli)
    r = _istek(
        o.a.app,
        "POST",
        "/api/data/import",
        {"passphrase": vta.PAROLA, "blob_b64": paket["data_b64"], "confirm": "REPLACE_ALL"},
        client=LAN,
        basliklar={"X-API-Key": JETON},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == _tr("yedek.hata.cihazDisiGeriYukleme")
    assert cagri["n"] >= 2
    monkeypatch.setattr(hb, "get_all_patients", gercek)
    assert vta.sayimlar(tb, hb) == once
    iz = tb.denetim_oku(event_type="data.import")
    assert [(s["outcome"], s["scope"], s["item_count"], json.loads(s["detail"])) for s in iz] == [
        ("reddedildi", "replace_all", 0, {"neden": "cihaz_disi"})
    ]


def test_ICE_AKTARMA_v1_yedeginde_hasta_kartlari_PATIENTS_anahtarindan(o, monkeypatch):
    """v1 yedeği (`bundle_version` 1, `patient_db` YOK, hasta kartları `patients`ta) boş cihaza → 200, `counts.patient_db` = 2 ve
    kartlar paketteki kimlikleriyle hasta DB'sinde."""
    from utils.data_export import decrypt_bundle

    vta.doldur(o.tdb, o.hdb, ["Mia", "Pamuk"], seans_basi=0, analiz=False)
    kaynak = vta.disa_aktar(o.a.app, client=CIHAZ)
    v2 = decrypt_bundle(base64.b64decode(kaynak["data_b64"]), vta.PAROLA)
    kartlar = v2["patient_db"]
    assert len(kartlar) == 2
    v1 = {
        "bundle_version": 1,
        "created_at": v2["created_at"],
        "treatment_sessions": [],
        "ai_analyses": [],
        "patients": kartlar,
    }
    tb, hb = vta.cihaz_kur(monkeypatch, o.tmp / "C")
    o.acik += [tb, hb]
    vta.uclari_bagla(monkeypatch, tb, hb)
    r = _istek(o.a.app, "POST", "/api/data/import", {"passphrase": vta.PAROLA, "blob_b64": _paket_b64(v1)})
    assert r.status_code == 200, r.text[:300]
    assert r.json()["counts"]["patient_db"] == 2
    assert sorted(h["id"] for h in hb.get_all_patients()) == sorted(h["id"] for h in kartlar)


# ── _yedegi_masaustune_yaz ─────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def masaustu(tmp_path, monkeypatch):
    from servers import seans_alan_kaydi

    d = tmp_path / "masaustu"
    d.mkdir()
    monkeypatch.setattr(seans_alan_kaydi, "masaustu_dizini", lambda: (d, "kp-tmp"))
    return d


def test_YEDEK_YAZ_gecici_TASINAMAZ_ve_SILINEMEZSE_ozgun_hata_yukselir(masaustu, monkeypatch):
    """`os.replace` PermissionError (hedef kilitli) + geçici dosya da silinemiyor → ÖZGÜN PermissionError yükselir (silme hatası
    onu ezmez); hedef dosya OLUŞMAZ."""
    import os

    from servers import api_server as a

    gercek_replace, gercek_unlink = os.replace, Path.unlink

    def _replace(src, dst, *x, **k):
        if str(src).endswith(".yazim.tmp"):
            raise PermissionError(13, "Erişim engellendi (hedef kilitli)")
        return gercek_replace(src, dst, *x, **k)

    def _unlink(self, *x, **k):
        if self.name.endswith(".yazim.tmp"):
            raise PermissionError(13, "dosya kullanımda")
        return gercek_unlink(self, *x, **k)

    monkeypatch.setattr(os, "replace", _replace)
    monkeypatch.setattr(Path, "unlink", _unlink)
    with pytest.raises(PermissionError) as e:
        a._yedegi_masaustune_yaz(b"0123456789", "kp-yedek.pemfbak")
    assert "hedef kilitli" in str(e.value)
    assert not (masaustu / "kp-yedek.pemfbak").exists()
    assert (masaustu / "kp-yedek.pemfbak.yazim.tmp").exists()


def test_YEDEK_YAZ_DOGRULANAMAYAN_hedef_silinemese_de_RuntimeError(masaustu, monkeypatch):
    """Diskten geri okunan bayt EKSİK (9/10) + bozuk hedef silinemiyor → RuntimeError "… DOĞRULANAMADI (9 / 10 bayt)" (silme
    hatası yutulur; "doğrulandı" denmez)."""
    from servers import api_server as a

    gercek_oku, gercek_unlink = Path.read_bytes, Path.unlink

    def _oku(self):
        b = gercek_oku(self)
        return b[:-1] if self.name == "kp-yedek.pemfbak" else b

    def _unlink(self, *x, **k):
        if self.name == "kp-yedek.pemfbak":
            raise PermissionError(13, "virüs tarayıcısı dosyayı tutuyor")
        return gercek_unlink(self, *x, **k)

    monkeypatch.setattr(Path, "read_bytes", _oku)
    monkeypatch.setattr(Path, "unlink", _unlink)
    with pytest.raises(RuntimeError) as e:
        a._yedegi_masaustune_yaz(b"0123456789", "kp-yedek.pemfbak")
    assert str(e.value) == "yedek dosyası diske yazıldı ama DOĞRULANAMADI (9 / 10 bayt)"
