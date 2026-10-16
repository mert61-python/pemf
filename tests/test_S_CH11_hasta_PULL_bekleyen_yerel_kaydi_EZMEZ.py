# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""S-CH.11 (CH2 sırasında bulundu) — hasta PULL'u PUSH BEKLEYEN yerel kaydı (ör. ANONİMLEŞTİRME) buluttaki eski kopyayla EZMEZ.

ÖLÇÜLEN KUSUR (taban `4240d3be`, latent — `PEMF_CLOUD_PATIENT_SYNC` varsayılan KAPALI): `_sync_patients` PULL'u
`ON CONFLICT(id) DO UPDATE SET name=excluded.name, … owner=excluded.owner, …, sync_status=1` yazıyordu — KOŞULSUZ. Anonimleştirme
(`anonymize_inactive_patients`) adı / sahibi `[ANONIM]` yapıp `sync_status=0` koyar ve "PUSH yayar" varsayar (Audit P2). Ama PUSH o turda
DÜŞERSE (ağ kesintisi, bulut reddi) aynı turdaki PULL buluttaki ESKİ şifreli adı / sahibi geri yazıyor, `sync_status`u 1'e çekiyordu:
hasta `anonymized=1` görünürken adı GERİ GELİYOR ve anonimleştirme buluta HİÇ gitmiyordu (KVKK — "geri dönüşsüz" söz verilen işlem tersine
dönüyordu). Seans yolunda aynı sınıf D2.65 ile kapalıydı; hasta yolunda değildi.
SÖZLEŞME: yerelde PUSH bekleyen (sync_status=0) hasta satırı PULL'da DEĞİŞMEZ ve bayrağı 0 KALIR (sonraki turda gönderilir). KARŞIT: senkron
(1) satır buluttaki değişikliği normal alır.
⚠️ MUTASYON: PULL'daki "bekleyen yerel satır" koşulu silinirse KRİTİK test KIRMIZI.
"""

from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "apps" / "backend"))


class _Sonuc:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _Bulut:
    """upsert_patient / resolve_patients taklidi (CANLIYA İSTEK YOK). `ag_yok=True` iken upsert düşer, resolve çalışır."""

    def __init__(self):
        self.hastalar: dict = {}
        self.ag_yok = False

    def rpc(self, ad, params=None):
        if ad == "upsert_patient":
            if self.ag_yok:
                raise RuntimeError("ag yok")
            yuk = dict(params["p_patient"])
            self.hastalar.setdefault(str(yuk["id"]), {}).update(yuk)
            return _Sonuc([])
        if ad == "resolve_patients":
            return _Sonuc([dict(h) for h in self.hastalar.values()])
        return _Sonuc([])


def _kur(temp_app_data, monkeypatch):
    from database.patient_database import PatientDatabase
    from servers.sync_worker import CloudSyncWorker

    monkeypatch.setenv("PEMF_CLOUD_PATIENT_SYNC", "1")
    hdb = PatientDatabase(str(temp_app_data / "patients.db"))
    w = CloudSyncWorker("", "")
    w.client = _Bulut()
    w.patient_sync_enabled = True
    w.device_id = "sch11-cihaz"
    return hdb, w


def _oku(hdb, pid):
    with hdb._get_connection() as c:
        r = c.execute("SELECT name, owner, anonymized, sync_status FROM patients WHERE id=?", (pid,)).fetchone()
    return {"ad": hdb._decrypt_field(r[0]), "sahip": hdb._decrypt_field(r[1]), "anonim": r[2], "sync": r[3]}


def test_KRITIK_PUSH_dusen_ANONIMLESTIRME_ayni_turdaki_PULL_ile_GERI_ALINAMAZ(temp_app_data, monkeypatch):
    hdb, w = _kur(temp_app_data, monkeypatch)
    pid = hdb.add_patient({"name": "Pamuk", "species": "kedi", "owner": "Ayse Yilmaz"})
    w._sync_patients(hdb)  # bulutta şifreli "Pamuk" / "Ayse Yilmaz"
    assert _oku(hdb, pid)["sync"] == 1
    with hdb._get_connection() as c:  # 2 yıldır gelmeyen hasta (süre 0 bilinçli olarak hiçbir şey yapmaz — F2-1.8)
        c.execute("UPDATE patients SET created_at='2024-01-01T00:00:00' WHERE id=?", (pid,))
        c.commit()
    assert hdb.anonymize_inactive_patients(inactive_days=365, yalniz=[pid]) == [pid], "önkoşul: anonimleştirme koşmadı"
    w.client.ag_yok = True
    w._sync_patients(hdb)  # PUSH düşer → PULL buluttaki eski kopyayı getirir
    s = _oku(hdb, pid)
    assert s["ad"] == "[ANONIM]" and s["sahip"] == "[ANONIM]", (
        f"ANONİMLEŞTİRME GERİ ALINDI: {s['ad']!r} / {s['sahip']!r}"
    )
    assert s["anonim"] == 1 and s["sync"] == 0, f"bekleyen anonimleştirmenin PUSH bayrağı silindi: {s}"
    w.client.ag_yok = False
    w._sync_patients(hdb)  # ağ geri geldi → anonimleştirme buluta gider
    assert _oku(hdb, pid)["sync"] == 1
    assert hdb._decrypt_field(w.client.hastalar[pid]["name"]) == "[ANONIM]", "anonimleştirme buluta yayılmadı"


def test_KARSIT_senkron_satir_buluttaki_degisikligi_ALIR(temp_app_data, monkeypatch):
    hdb, w = _kur(temp_app_data, monkeypatch)
    pid = hdb.add_patient({"name": "Boncuk", "species": "kopek", "owner": "Ali"})
    w._sync_patients(hdb)
    w.client.hastalar[pid]["breed"] = "golden"  # bulutta değişti (yerel senkron = 1)
    w._sync_patients(hdb)
    with hdb._get_connection() as c:
        irk, sync = c.execute("SELECT breed, sync_status FROM patients WHERE id=?", (pid,)).fetchone()
    assert (irk, sync) == ("golden", 1), "senkron satır buluttaki değişikliği almadı (koruma fazla geniş)"
