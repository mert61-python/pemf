# -*- coding: utf-8 -*-
"""A3 · D2-3.1 — D2.66'nın İLK yarısı: hasta DB'si okunamazken GERÇEK `GET /api/patients` "hasta yok" (200 success, data=[], total=0)
diyor mu? Plan (DENETIM-14 D2.66 "Neden") bunu kusur sayıyordu: "DB hatası operatöre 'hasta yok' (success, total=0) görünüyor";
2-D yalnız günlük + taşıma uçlarını düzeltti (patient_router.py'ye dokunmadı).

Arıza EN ALT katta, gerçek biçimiyle (2-D'nin kendi yöntemi): hasta DB dosyasının SQLite başlığı bozulur → "file is not a database".
Zincir: gerçek PatientDatabase → gerçek /api/patients ucu (patient_router) → yanıt. Arayüz (PatientScreen.tsx:74-81, :437-439) 200 +
`status: success` + boş dizi alınca "Henüz hasta kaydı yok." gösterir; 5xx alınca "Hastalar yüklenemedi" + "Tekrar Dene".

Bu dosya ÖNCE-KIRMIZI kapıdır (depodaki yeri: tests/test_hasta_LISTESI_okunamazken_BOS_demez_D266b.py). Pozitif kontrol: sağlıklı DB'de
uç hastaları GÖRÜR (okuyucu kaydı görebiliyor) — sonra yokluk iddiası ölçülür.
"""

from __future__ import annotations

import pytest
from veri_tasima_aparati import cihaz_kur, istekler, kapat


def _bozuk(hdb) -> None:
    hdb._reset_thread_conn()
    with open(hdb.db_file, "r+b") as f:
        f.write(b"BOZUK-BASLIK-A3-D266" * 6)


@pytest.fixture()
def cihaz(tmp_path, monkeypatch):
    from servers import patient_router as pr

    tdb, hdb = cihaz_kur(monkeypatch, tmp_path / "A")
    monkeypatch.setattr(pr, "get_patient_database", lambda *a, **k: hdb)
    try:
        yield tdb, hdb
    finally:
        kapat(tdb, hdb)


def test_KARSIT_A3_saglikli_DB_liste_hastalari_GOSTERIR(cihaz):
    from servers import api_server as api

    tdb, hdb = cihaz
    hdb.add_patient({"name": "Mia", "species": "Kedi"})
    hdb.add_patient({"name": "Pamuk", "species": "Kopek"})
    (r,) = istekler(api.app, [("GET", "/api/patients", None, None)])
    assert r.status_code == 200, r.text[:300]
    g = r.json()
    assert g["status"] == "success" and len(g["data"]) == 2 and g["total"] == 2, g


def test_KRITIK_A3_hasta_DB_okunamazken_liste_HASTA_YOK_demez(cihaz):
    """Masada hasta varken (DB'de 2 kayıt) okunamayan defter 'success + 0 hasta' DÖNMEMELİ — arayüz bunu 'Henüz hasta kaydı yok.'
    diye gösterir; operatör aynı hayvana yeni kart açar (geçici arızada → çift hasta)."""
    from servers import api_server as api

    tdb, hdb = cihaz
    hdb.add_patient({"name": "Mia", "species": "Kedi"})
    hdb.add_patient({"name": "Pamuk", "species": "Kopek"})
    _bozuk(hdb)
    (r,) = istekler(api.app, [("GET", "/api/patients", None, None)])
    govde = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    assert not (r.status_code == 200 and govde.get("status") == "success" and govde.get("data") == []), (
        f"hasta DB'si okunamazken liste 'başarılı ve BOŞ' döndü (arayüz: 'Henüz hasta kaydı yok.'): {r.status_code} {r.text[:200]}"
    )
    assert r.status_code >= 500, f"okunamayan defter 5xx değil: {r.status_code} {r.text[:200]}"
    assert "okunamad" in str(govde.get("detail", "")).lower(), f"gerekçe arızayı söylemiyor: {r.text[:300]}"
