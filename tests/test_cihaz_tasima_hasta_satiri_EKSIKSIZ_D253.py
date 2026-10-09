# -*- coding: utf-8 -*-
"""D2.53 (B-3.30 · B-3.31) — cihaz taşıma paketi hasta satırını EKSİKSİZ taşır.

ÖLÇÜLEN KUSURLAR (DENETIM-03, 2-D'de yeniden ölçüldü — gerçek dışa aktar ucu → gerçek içe aktar ucu, iki ayrı veri kökü):
  B-3.30 `PatientDatabase.add_patient` içe aktarmada `created_at = şimdi` yazıyor, `last_treatment_at` ve `anonymized`ı hiç almıyordu:
         KVKK'nın 5 yıllık inaktiflik saati içe aktarma anına SIFIRLANIYOR (6,7 yıl inaktif hasta yeni cihazda 5 yıl daha anonimleşmez),
         anonim hasta yeniden "anonim değil" sayılıyordu.
  B-3.31 Çözülemeyen (farklı / eski anahtarla şifrelenmiş) alan dışa aktarmada `'[okunamayan kayıt]'` YER TUTUCUSU olarak paketleniyor,
         yeni cihazda bu metin GERÇEK DEĞER diye şifreleniyordu: özgün şifreli değer KAYBOLUYOR, ekranda yer tutucu gerçek veri gibi duruyordu.
DÜZELTME: dışa aktarma çözülemeyen alanı `_sifreli_ham` altında ÖZGÜN değeriyle taşır; içe aktarma onu AYNEN yazar (arama dizinine
katmaz) ve `created_at` / `updated_at` / `last_treatment_at` / `anonymized`ı korur.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from veri_tasima_aparati import PAROLA, cihaz_kur, disa_aktar, istekler, kapat, uclari_bagla


def _ham(hdb, pid, alan):
    c = sqlite3.connect(str(hdb.db_file))
    try:
        return c.execute(f"SELECT {alan} FROM patients WHERE id = ?", (pid,)).fetchone()[0]
    finally:
        c.close()


def _ham_yaz(hdb, pid, **alanlar):
    hdb._reset_thread_conn()
    c = sqlite3.connect(str(hdb.db_file))
    try:
        for k, v in alanlar.items():
            c.execute(f"UPDATE patients SET {k} = ? WHERE id = ?", (v, pid))
        c.commit()
    finally:
        c.close()


def _tasi(tmp_path, monkeypatch, hazirla):
    from servers import api_server as api

    ta, ha = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, ta, ha)
    durum = hazirla(ta, ha)
    paket = disa_aktar(api.app)
    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")
    uclari_bagla(monkeypatch, tb, hb)
    (r,) = istekler(
        api.app, [("POST", "/api/data/import", {"passphrase": PAROLA, "blob_b64": paket["data_b64"]}, None)]
    )
    assert r.status_code == 200, r.text[:300]
    return (ta, ha, tb, hb), durum


def test_KRITIK_D253_inaktiflik_saati_ve_anonim_bayragi_TASINIR_KVKK_kumesi_AYNI(tmp_path, monkeypatch):
    eski = (datetime.now() - timedelta(days=int(6.7 * 365))).isoformat()
    yeni = (datetime.now() - timedelta(days=30)).isoformat()

    def hazirla(ta, ha):
        x = ha.add_patient({"name": "UzunInaktif", "species": "Kedi"})
        y = ha.add_patient({"name": "[ANONIM]", "species": "Kedi"})
        z = ha.add_patient({"name": "Yakin", "species": "Kopek"})
        _ham_yaz(ha, x, created_at=eski, updated_at=eski)
        _ham_yaz(ha, y, created_at=eski, updated_at=eski, anonymized=1, last_treatment_at=eski)
        _ham_yaz(ha, z, created_at=eski, last_treatment_at=yeni)
        return {"x": x, "y": y, "z": z}

    dbler, k = _tasi(tmp_path, monkeypatch, hazirla)
    ta, ha, tb, hb = dbler
    try:
        assert _ham(hb, k["x"], "created_at") == eski, (
            "kayıt tarihi içe aktarma anına SIFIRLANDI (KVKK inaktiflik saati)"
        )
        assert _ham(hb, k["z"], "last_treatment_at") == yeni, "son tedavi tarihi taşınmadı"
        assert int(_ham(hb, k["y"], "anonymized") or 0) == 1, "anonim hasta yeni cihazda 'anonim değil' oldu"
        kaynak = sorted(ha.anonymize_inactive_patients(1825))
        hedef = sorted(hb.anonymize_inactive_patients(1825))
        assert kaynak == [k["x"]], f"aparat: kaynakta beklenen inaktif küme yok: {kaynak}"
        assert hedef == kaynak, (
            f"KVKK 5 yıl anonimleştirme kümesi taşımadan sonra FARKLI: kaynak {kaynak} · hedef {hedef}"
        )
    finally:
        kapat(*dbler)


def test_KRITIK_D253_cozulemeyen_alan_YER_TUTUCU_olarak_degil_OZGUN_sifreli_degeriyle_tasinir(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    baska = "enc:" + Fernet(Fernet.generate_key()).encrypt("Ahmet Bey (eski anahtar)".encode()).decode()

    def hazirla(ta, ha):
        pid = ha.add_patient({"name": "Boncuk", "species": "Kedi", "owner": "gecici"})
        _ham_yaz(ha, pid, owner=baska)
        assert ha.get_patient(pid)["owner"] == "[okunamayan kayıt]", "aparat: alan kaynakta çözülemez olmalı"
        return {"pid": pid}

    dbler, k = _tasi(tmp_path, monkeypatch, hazirla)
    ta, ha, tb, hb = dbler
    try:
        ham_b = _ham(hb, k["pid"], "owner")
        assert ham_b == baska, (
            "çözülemeyen alanın ÖZGÜN şifreli değeri taşınmadı — yer tutucu metin yeni cihazda gerçek değer diye şifrelendi "
            f"(özgün değer KAYBOLDU): {str(ham_b)[:60]!r}"
        )
        h = hb.get_patient(k["pid"])
        assert h["owner"] == "[okunamayan kayıt]" and h["name"] == "Boncuk"
        assert hb.search_patients("okunamayan") == [], "yer tutucu metin arama dizinine girdi"
    finally:
        kapat(*dbler)


def test_KARSIT_D253_normal_hasta_alanlari_ve_arama_TASINIR(tmp_path, monkeypatch):
    def hazirla(ta, ha):
        return {"pid": ha.add_patient({"name": "Pamuk", "species": "Kedi", "owner": "Ayşe Hanım", "breed": "Tekir"})}

    dbler, k = _tasi(tmp_path, monkeypatch, hazirla)
    ta, ha, tb, hb = dbler
    try:
        h = hb.get_patient(k["pid"])
        assert (h["name"], h["owner"], h["breed"]) == ("Pamuk", "Ayşe Hanım", "Tekir")
        assert [p["id"] for p in hb.search_patients("pamuk")] == [k["pid"]]
        assert int(_ham(hb, k["pid"], "anonymized") or 0) == 0
    finally:
        kapat(*dbler)
