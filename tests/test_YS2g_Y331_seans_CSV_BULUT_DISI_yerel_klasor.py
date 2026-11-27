# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YS2 g · Y331 (sahip 26-11; Y218 DEĞİŞTİ): seans alan CSV'si bugün ŞİFRESİZ, dosya adında HASTA ADIYLA Masaüstüne yazılıyordu;
Masaüstü OneDrive'a yönlendirilmişse (Windows Bilinen Klasör yönlendirmesi) dosya BULUTA gidiyordu — DB şifreli ve hasta bulut
eşitlemesi KVKK için KAPALIYKEN çelişki.

SÖZLEŞME: varsayılan klasör `%USERPROFILE%\\PEMF Vet\\Seans CSV` (yönlendirmeye girmez); kullanıcı klasörü de bulut eşitlemesindeyse
`%LOCALAPPDATA%\\PEMF Vet\\Seans CSV`; servis hesabında (systemprofile) geçerli çalışma dizini. Dosya adı seans NO + tarih (hasta adı
dosya adında YOK — içerikte üst bilgi olarak kalır; hocanın 10-30 "CSV adları şartnamedekiyle birebir" kararı makale `paper_inputs`
CSV'lerini bağlar). Arayüzden klasörü açan eylem: yalnız cihazın kendi ekranından (uzak istemci sunucuda pencere açtıramaz, yolu alır).
Eski Masaüstü CSV'lerine DOKUNULMAZ. Testler gerçek eve / Masaüstüne YAZMAZ (sahte ev, `conftest._masaustunu_koru`).
"""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_KP_api_server_seans_baslat import GOVDE, o  # noqa: F401 — gerçek /session/start aparatı


@pytest.fixture
def ev(tmp_path, monkeypatch):
    """Sahte kullanıcı evi: Masaüstü OneDrive'a YÖNLENDİRİLMİŞ (yerel Desktop yok; `OneDrive` ortam değişkeni)."""
    e = tmp_path / "Kullanici"
    (e / "OneDrive" / "Desktop").mkdir(parents=True)
    (e / "AppData" / "Local").mkdir(parents=True)
    for k in ("USERPROFILE", "HOME"):
        monkeypatch.setenv(k, str(e))
    monkeypatch.setenv("LOCALAPPDATA", str(e / "AppData" / "Local"))
    monkeypatch.setenv("OneDrive", str(e / "OneDrive"))
    for k in ("OneDriveConsumer", "OneDriveCommercial"):
        monkeypatch.delenv(k, raising=False)
    return e


def _gercek_cozucu():
    import servers.seans_alan_kaydi as sak

    cozucu = getattr(sak, "_orijinal_seans_csv_dizini", None)  # conftest yamasından ÖNCEKİ üretim çözücüsü
    assert cozucu is not None, "üretimde seans CSV çözücüsü (seans_csv_dizini) YOK — CSV hâlâ masaüstü çözücüsünden"
    return cozucu


def test_KRITIK_Y331_OneDrive_a_yonlendirilmis_masaustunde_CSV_BULUTA_yazilmaz(ev, monkeypatch):
    import servers.seans_alan_kaydi as sak

    eski_masaustu, _ = sak._orijinal_masaustu_dizini()
    assert eski_masaustu == ev / "OneDrive" / "Desktop", "aparat: yönlendirilmiş masaüstü benzetimi tutmadı"
    monkeypatch.setattr(sak, "seans_csv_dizini", _gercek_cozucu())
    k = sak.SeansAlanKaydi()
    try:
        yol = k.seans_basladi("SEANS-UUID-1", {"seans_no": 42, "patient_name": "Boncuk Yılmaz", "mode": "Manuel"})
    finally:
        k.seans_bitti("test")
    assert yol is not None and yol.is_file()
    assert "OneDrive" not in yol.parts, f"seans CSV'si BULUT eşitleme klasörüne yazıldı: {yol}"
    assert yol.parent == ev / "PEMF Vet" / "Seans CSV", yol
    assert yol.name.startswith("PEMF_alan_seans42_") and yol.suffix == ".csv", yol.name
    assert "Boncuk" not in yol.name, "dosya ADINDA hasta adı (Y331: seans no + tarih)"
    with io.open(yol, encoding="utf-8-sig", newline="") as f:
        duz = [",".join(s) for s in csv.reader(f)]
    assert any("Boncuk" in s for s in duz), (
        "hasta adı dosyanın İÇİNDEKİ üst bilgiden de silindi (yalnız ad değişmeliydi)"
    )


def test_KRITIK_Y331_kullanici_klasoru_BULUTTAYSA_yerel_uygulama_verisine(ev, monkeypatch):
    monkeypatch.setenv("OneDrive", str(ev))  # tüm kullanıcı klasörü eşitleniyor
    dizin, gerekce = _gercek_cozucu()()
    assert dizin == ev / "AppData" / "Local" / "PEMF Vet" / "Seans CSV" and dizin.is_dir(), (dizin, gerekce)


def test_Y331_OneDrive_adli_ust_klasor_de_BULUT_sayilir(tmp_path, monkeypatch):
    e = tmp_path / "OneDrive - Klinik" / "Kullanici"
    e.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(e))
    monkeypatch.setenv("HOME", str(e))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "yerel"))
    for k in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        monkeypatch.delenv(k, raising=False)
    dizin, _ = _gercek_cozucu()()
    assert dizin == tmp_path / "yerel" / "PEMF Vet" / "Seans CSV"


def test_Y331_servis_hesabinda_kullanici_klasoru_YOK_calisma_dizini(tmp_path, monkeypatch):
    monkeypatch.setattr(os.path, "expanduser", lambda p: r"C:\Windows\System32\config\systemprofile")
    monkeypatch.chdir(tmp_path)
    dizin, gerekce = _gercek_cozucu()()
    assert dizin == Path.cwd() and "servis" in gerekce


def test_KRITIK_Y331_seans_baslatma_DOSYA_ADINA_seans_NO_verir(o, monkeypatch):  # noqa: F811
    """Gerçek `/api/session/start`: kayda giden seans numarası = DB satırı (geçmişteki kimlik)."""
    gelen = []

    class _Kayit:
        def seans_basladi(self, seans_id, meta=None):
            gelen.append((seans_id, dict(meta or {})))
            return None

        def seans_bitti(self, *a, **k):
            return None

    monkeypatch.setattr(o.api, "_seans_alan", _Kayit())
    r = o.c.post("/api/session/start", json={**GOVDE, "patient_name": "Pamuk"})
    assert r.status_code == 200, r.text[:300]
    sid = o.api._active_session.get("db_session_id")
    assert sid and gelen and gelen[-1][1].get("seans_no") == sid, gelen


@pytest.fixture
def uc(monkeypatch, tmp_path):
    import servers.seans_alan_kaydi as sak
    from servers import api_server as api

    acilan = []
    hedef = tmp_path / "Seans CSV"
    hedef.mkdir()
    monkeypatch.setattr(sak, "seans_csv_dizini", lambda: (hedef, "test"))
    monkeypatch.setattr(os, "startfile", lambda p: acilan.append(p), raising=False)  # GERÇEK Gezgin AÇILMAZ
    return type("U", (), {"api": api, "acilan": acilan, "hedef": hedef})


def test_KRITIK_Y331_klasoru_ac_CIHAZ_EKRANINDAN_gezginde_acar(uc):
    c = TestClient(uc.api.app, client=("127.0.0.1", 53219))
    r = c.post("/api/history/seans_csv_klasoru/ac", json={})
    assert r.status_code == 200, r.text[:200]
    assert r.json() == {"status": "success", "yol": str(uc.hedef)}
    assert uc.acilan == [str(uc.hedef)]


def test_KARSIT_Y331_BASIT_POST_JSON_degilse_415_pencere_ACILMAZ(uc):
    """D5 · 1-C §9 #14 (Sıfırla emsali): ön-uçuşsuz basit POST (başka bir sayfa cihazın tarayıcısından) Gezgin açtıramaz."""
    c = TestClient(uc.api.app, client=("127.0.0.1", 53222))
    r = c.post("/api/history/seans_csv_klasoru/ac", content=b"", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415 and "JSON" in r.json()["detail"] and uc.acilan == [], r.text[:200]


def test_KARSIT_Y331_LAN_istemcisi_sunucuda_PENCERE_ACTIRAMAZ_yalniz_yolu_alir(uc):
    c = TestClient(uc.api.app, client=("192.168.137.21", 53220))
    r = c.post("/api/history/seans_csv_klasoru/ac", json={})
    assert r.status_code == 200, r.text[:200]
    assert r.json()["status"] == "uzak" and uc.acilan == []


@pytest.mark.parametrize(("dil", "parca"), [("tr", "elle açın"), ("en", "open it manually")])
def test_Y331_klasor_ACILAMAZSA_eylem_soyleyen_500(uc, monkeypatch, dil, parca):
    def _patla(p):
        raise OSError("gezgin yok")

    monkeypatch.setattr(os, "startfile", _patla, raising=False)
    c = TestClient(uc.api.app, client=("127.0.0.1", 53221))
    r = c.post("/api/history/seans_csv_klasoru/ac", json={}, headers={"X-PEMF-Dil": dil})
    assert r.status_code == 500 and parca in r.json()["detail"] and str(uc.hedef) in r.json()["detail"], r.text[:300]
