# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YS3 e · Y342 (sahip 27-11 "Evet, YS3'e ekle"): Seans Detayı / raporlardaki PDF ve CSV "İndir" düğmeleri (geçmiş raporu, hasta
raporu, seans / bobin CSV'si, AI PDF — hepsi `history_router._diske_kaydet`) Masaüstüne yazıyordu; Masaüstü OneDrive'a bağlıysa
hasta raporu BULUTA gidiyordu (DB şifreli + hasta bulut eşitlemesi KVKK için KAPALI — Y331'in aynı çelişkisi).

SÖZLEŞME (YS2 g `seans_csv_dizini` ile AYNI kural, ortak `_yerel_belge_dizini`): `%USERPROFILE%\\PEMF Vet\\Raporlar`; kullanıcı
klasörü de bulut eşitlemesindeyse `%LOCALAPPDATA%\\PEMF Vet\\Raporlar`; servis hesabında geçerli çalışma dizini. Arayüzde "📂 Raporlar
klasörü" (yalnız cihazın kendi ekranından açar; uzak istemci yolu alır; JSON olmayan basit POST 415). Telefon / tarayıcı indirmesi
(tarayıcının kendi indirme klasörü) DEĞİŞMEZ (`kaydet=1` yalnız cihaz ekranı — D3.05). Testler gerçek eve YAZMAZ (sahte ev).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


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


def _gercek_cozuculer(monkeypatch):
    """conftest yamasından ÖNCEKİ üretim çözücüleri (masaüstü + Raporlar) modüle geri konur."""
    import servers.seans_alan_kaydi as sak

    rapor = getattr(sak, "_orijinal_raporlar_dizini", None)
    assert rapor is not None, "üretimde Raporlar çözücüsü (raporlar_dizini) YOK — İndir hâlâ masaüstü çözücüsünden"
    monkeypatch.setattr(sak, "masaustu_dizini", sak._orijinal_masaustu_dizini)
    monkeypatch.setattr(sak, "raporlar_dizini", rapor)
    return rapor


def test_KRITIK_Y342_OneDrive_a_yonlendirilmis_masaustunde_INDIR_BULUTA_yazilmaz(ev, monkeypatch):
    import servers.seans_alan_kaydi as sak
    from servers.history_router import _diske_kaydet

    _gercek_cozuculer(monkeypatch)
    assert sak.masaustu_dizini()[0] == ev / "OneDrive" / "Desktop", "aparat: yönlendirilmiş masaüstü benzetimi tutmadı"
    g = _diske_kaydet(b"%PDF-1.4 hasta raporu", "PEMF_Rapor_3_seans.pdf")
    yol = Path(g["yol"])
    assert g["status"] == "success" and yol.is_file(), g
    assert "OneDrive" not in yol.parts, f"İndir dosyası BULUT eşitleme klasörüne yazıldı: {yol}"
    assert yol.parent == ev / "PEMF Vet" / "Raporlar", yol
    assert not any((ev / "OneDrive" / "Desktop").iterdir()), "masaüstüne (OneDrive) de dosya bırakıldı"


def test_KRITIK_Y342_kullanici_klasoru_BULUTTAYSA_yerel_uygulama_verisine(ev, monkeypatch):
    from servers.history_router import _diske_kaydet

    _gercek_cozuculer(monkeypatch)
    monkeypatch.setenv("OneDrive", str(ev))  # tüm kullanıcı klasörü eşitleniyor
    yol = Path(_diske_kaydet(b"a;b\n", "PEMF_Gecmis.csv")["yol"])
    assert yol.parent == ev / "AppData" / "Local" / "PEMF Vet" / "Raporlar", yol


def test_Y342_servis_hesabinda_kullanici_klasoru_YOK_calisma_dizini(tmp_path, monkeypatch):
    rapor = _gercek_cozuculer(monkeypatch)
    monkeypatch.setattr(os.path, "expanduser", lambda p: r"C:\Windows\System32\config\systemprofile")
    monkeypatch.chdir(tmp_path)
    dizin, gerekce = rapor()
    assert dizin == Path.cwd() and "servis" in gerekce


def test_KRITIK_Y342_seans_CSV_ile_AYNI_KURAL_ayri_klasor(ev, monkeypatch):
    """ "İki kez yazma": seans CSV'si (Y331) ve İndir (Y342) TEK kuraldan — bulut altındaki kullanıcı klasöründe ikisi de yerel
    uygulama verisine düşer, yalnız alt klasör ayrı."""
    import servers.seans_alan_kaydi as sak

    rapor = _gercek_cozuculer(monkeypatch)
    monkeypatch.setenv("OneDrive", str(ev))
    yerel = ev / "AppData" / "Local" / "PEMF Vet"
    assert sak._orijinal_seans_csv_dizini()[0] == yerel / "Seans CSV"
    assert rapor()[0] == yerel / "Raporlar"


def test_KRITIK_Y342_raporlar_cozucusu_TEST_SIRASINDA_yamalanmis_ve_masaustunden_AYRI():
    """`conftest._masaustunu_koru` Raporlar çözücüsünü de yönlendirir (süit gerçek eve yazmaz) — masaüstü sahtesinden AYRI dizine:
    aynı dizin olsaydı `_diske_kaydet`in masaüstüne geri dönüşü eski testlerde YEŞİL kalırdı."""
    import servers.seans_alan_kaydi as sak

    dizin, gerekce = sak.raporlar_dizini()
    assert gerekce == "test izolasyonu", f"Raporlar çözücüsü YAMALANMAMIŞ ({gerekce!r}) — süit gerçek eve yazabilir"
    assert Path(dizin) != Path(sak.masaustu_dizini()[0]), "Raporlar sahtesi masaüstü sahtesiyle AYNI dizin"


@pytest.fixture
def uc(monkeypatch, tmp_path):
    import servers.seans_alan_kaydi as sak
    from servers import api_server as api

    acilan = []
    hedef = tmp_path / "Raporlar"
    hedef.mkdir()
    monkeypatch.setattr(sak, "raporlar_dizini", lambda: (hedef, "test"))
    monkeypatch.setattr(os, "startfile", lambda p: acilan.append(p), raising=False)  # GERÇEK Gezgin AÇILMAZ
    return type("U", (), {"api": api, "acilan": acilan, "hedef": hedef})


def test_KRITIK_Y342_raporlar_klasorunu_ac_CIHAZ_EKRANINDAN_gezginde_acar(uc):
    c = TestClient(uc.api.app, client=("127.0.0.1", 53231))
    r = c.post("/api/history/raporlar_klasoru/ac", json={})
    assert r.status_code == 200, r.text[:200]
    assert r.json() == {"status": "success", "yol": str(uc.hedef)}
    assert uc.acilan == [str(uc.hedef)], "Raporlar yerine başka klasör açıldı"


def test_KARSIT_Y342_BASIT_POST_JSON_degilse_415_pencere_ACILMAZ(uc):
    c = TestClient(uc.api.app, client=("127.0.0.1", 53232))
    r = c.post("/api/history/raporlar_klasoru/ac", content=b"", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415 and "JSON" in r.json()["detail"] and uc.acilan == [], r.text[:200]


def test_KARSIT_Y342_LAN_istemcisi_sunucuda_PENCERE_ACTIRAMAZ_yalniz_yolu_alir(uc):
    c = TestClient(uc.api.app, client=("192.168.137.22", 53233))
    r = c.post("/api/history/raporlar_klasoru/ac", json={})
    assert r.status_code == 200 and r.json() == {"status": "uzak", "yol": str(uc.hedef)} and uc.acilan == [], r.text[
        :200
    ]


@pytest.mark.parametrize(
    ("dil", "parca"), [("tr", "Raporlar klasörü açılamadı"), ("en", "Could not open the Reports folder")]
)
def test_Y342_klasor_ACILAMAZSA_eylem_soyleyen_500(uc, monkeypatch, dil, parca):
    def _patla(p):
        raise OSError("gezgin yok")

    monkeypatch.setattr(os, "startfile", _patla, raising=False)
    c = TestClient(uc.api.app, client=("127.0.0.1", 53234))
    r = c.post("/api/history/raporlar_klasoru/ac", json={}, headers={"X-PEMF-Dil": dil})
    d = r.json()["detail"]
    assert r.status_code == 500 and parca in d and str(uc.hedef) in d, r.text[:300]
