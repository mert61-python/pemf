# -*- coding: utf-8 -*-
"""2-F incelemesi §10 #4 (D5 · yardımcı E) — KVKK anonimleştirme kalıcı BEKLEYEN listesindeki hastanın kanonik KARTI SİLİNİRSE girdi
listeden DÜŞER (iz + uyarı); kartı duran hastanın girdisi KALIR; hasta DB'si okunamazken hiçbir girdi düşmez.

ÖLÇÜLEN KUSUR (HEAD 9c6d4505): `services.kvkk_anonimlestirme._bekleyenleri_isle` yalnız kanonik tarafı `anonymized=1` olan girdileri
işler. Kartı silinen hastada `pdb.get_patient` → None → girdi hiç işlenmez, hiç düşmez: tedavi DB'sinin `system_settings`
`kvkk_anonim_bekleyen` JSON'unda hastanın DÜZ ad / sahip / e-posta kopyası SÜRESİZ kalıyor, her gün yeniden okunuyor, günlükte tek satır
yok, `tedavi_bekleyen` sayısı şişik kalıyordu. İki yol:
  (A) kanonik adım oldu, tedavi adımı düştü (-1) → anonim kart sonra silindi;
  (B) kanonik adım düştü (aday hâlâ anonim değil) → aday kart silindi.

Düzeltme: tur başındaki bekleyen işleme girdilerin kartlarını KATI okumayla sınar (yalnız var olanlar; okuma hatası YÜKSELİR → bu turda
hiçbir girdi düşmez). Kartı OLMAYAN girdi düşer + WARNING + denetim izi `kvkk.bekleyen_silinen_hasta` (yalnız sayı; ad YOK; boş turda iz
yok). ⚠️ SON (Y204 · S-D5.10, sahip): girdi düşmeden ÖNCE tedavi adımı uygulanır (eskiden "tedavi geçmişine DOKUNULMAZ" — ad süresiz
kalıyordu); tedavi adımı düşerse girdi KALIR. Bu dosya girdinin düşmesini / kalmasını ölçer — A testinde tedavi tetikleyicisi artık YALNIZ
kartı DURAN hastanın ayna satırında (silinenin adımı uygulanabilsin); adımın kendisi `test_kvkk_SILINEN_kartin_tedavi_gecmisi_ANONIMLESIR_Y204.py`.

Kurulum EN ALT katta: tedavi / kanonik adımın düşmesi GERÇEK SQLite tetikleyicisiyle (`RAISE(ABORT)`), kart silmesi GERÇEK
`PatientDatabase.delete_patient`, okunamayan hasta DB'si GERÇEK "no such table". GERÇEK `services.kvkk_anonimlestirme.tur`.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta

import pytest

HEKIM = "dr.e4@klinik.vet"
IZ = "kvkk.bekleyen_silinen_hasta"


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database.patient_database import PatientDatabase
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    pdb = PatientDatabase(str(tmp_path / "patients.db"))
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield pdb, tdb
    finally:
        tdb.close_connections()


def _hasta(pdb, ad, gun=2200):
    pid = pdb.add_patient({"name": ad, "owner": f"Sahip {ad}", "owner_email": "e4@ornek.com"})
    with pdb._get_connection() as c:
        c.execute(
            "UPDATE patients SET last_treatment_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=gun)).isoformat(), pid),
        )
        c.commit()
    return pid


def _seans(tdb, ad, pid):
    """`api_server._persist_session_start` sırası: ayna hasta → seans → hasta bağı."""
    tpid = tdb.upsert_patient({"name": ad, "patient_uuid": pid, "owner_email": "e4@ornek.com"})
    sid = int(tdb.start_session(treatment_mode="Manuel", patient_name=ad, operator_name="Dr E4", operator_email=HEKIM))
    tdb.set_session_meta(sid, started_epoch=time.time(), patient_id=tpid)
    tdb.end_session(sid, patient_notes=f"{ad} sakin", duration_minutes=5)
    return sid


def _onay(tdb):
    from services import kvkk_anonimlestirme as kv

    tdb.anonim_onayi_yaz(gun=kv.ESIK_GUN, sayi=2, kim=HEKIM)


def _tetik(db, ad):
    """EN ALT kat: `patients` UPDATE'i GERÇEK SQLite hatasıyla düşer (disk dolu / kilit benzetimi)."""
    with db._get_connection() as c:
        c.execute(f"CREATE TRIGGER {ad} BEFORE UPDATE ON patients BEGIN SELECT RAISE(ABORT, 'E4 benzetim'); END")
        c.commit()


def _tetik_kaldir(db, ad):
    with db._get_connection() as c:
        c.execute(f"DROP TRIGGER {ad}")
        c.commit()


def _izler(tdb):
    return tdb.denetim_oku(50, IZ)


def _ham_liste(tdb) -> str:
    return json.dumps(tdb.anonim_bekleyen_oku(), ensure_ascii=False)


def _A_kur(pdb, tdb):
    """İki hasta onaylı turda kanonik olarak anonimleşir; tedavi adımı (GERÇEK tetikleyici) düşer → ikisi de listede."""
    from services import kvkk_anonimlestirme as kv

    p1, p2 = _hasta(pdb, "Pamuk Silinen-E4"), _hasta(pdb, "Boncuk Duran-E4")
    _seans(tdb, "Pamuk Silinen-E4", p1)
    _seans(tdb, "Boncuk Duran-E4", p2)
    _onay(tdb)
    _tetik(tdb, "e4_tedavi_dus")
    s = kv.tur(pdb, tdb)
    assert s["anonimlestirilen"] == 2, f"aparat: kanonik adım olmadı: {s}"
    assert pdb.get_patient(p1)["anonymized"] in (1, "1", True)
    # Ürün davranışı (B-3.34): kartı DURAN, tedavi adımı düşen hastaların girdisi KALIR (yeniden denenecek).
    assert {p1, p2} <= set(tdb.anonim_bekleyen_oku()) and s["tedavi_bekleyen"] == 2, (
        f"kartı DURAN, tedavi adımı düşen hastaların girdisi listeden düşürüldü — yeniden deneme kaybolur: {s}"
    )
    return p1, p2


def test_KRITIK_A_tedavi_adimi_dusen_hastanin_KARTI_SILINIRSE_girdisi_DUSER_iz_ve_uyari(o, caplog):
    """MUTASYON: silinen kart sınaması yok → KIRMIZI (girdi süresiz kalır); iz yok → KIRMIZI; yalnız ilk girdi sınanır → KIRMIZI."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    p1, p2 = _A_kur(pdb, tdb)
    # SON (Y204): silinen kartın girdisi ancak tedavi adımı uygulanınca düşer → tetikleyici YALNIZ kartı duran p2'nin ayna satırında kalır.
    _tetik_kaldir(tdb, "e4_tedavi_dus")
    with tdb._get_connection() as c:
        c.execute(
            "CREATE TRIGGER e4_tedavi_dus_p2 BEFORE UPDATE ON patients WHEN OLD.patient_uuid = ? "
            "BEGIN SELECT RAISE(ABORT, 'E4 benzetim'); END".replace("?", "'" + str(p2).replace("'", "''") + "'")
        )
        c.commit()
    assert pdb.delete_patient(p1) is True, "aparat: kart silinemedi"
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=kv.logger.name):
        s = kv.tur(pdb, tdb)
    bekleyen = tdb.anonim_bekleyen_oku()
    assert p1 not in bekleyen, (
        "kartı SİLİNEN hastanın girdisi kalıcı bekleyen listede SÜRESİZ kaldı (düz ad/sahip/e-posta kopyası tedavi DB'sinde)"
    )
    assert "Pamuk Silinen-E4" not in _ham_liste(tdb), "silinen hastanın adı bekleyen listenin ham JSON'unda kaldı"
    assert p2 in bekleyen, (
        "kartı DURAN (tedavi adımı düşen) hastanın girdisi de düşürüldü — tedavi adımı bir daha denenmez"
    )
    assert s["tedavi_bekleyen"] == 1, f"tur sonucu bekleyen sayısı şişik: {s}"
    izler = _izler(tdb)
    assert len(izler) == 1, f"silinen kart girdisinin düşmesi denetim izine yazılmadı (ya da birden çok kez): {izler}"
    assert int(izler[0]["item_count"]) == 1, f"iz sayısı yanlış: {izler[0]}"
    assert "Pamuk" not in json.dumps(izler[0], ensure_ascii=False, default=str), "denetim izi hasta adını taşıyor"
    # Aynı turda `_uzlastir` da WARNING yazar (p2'nin ayna adı) — uyarı silinen karta ait olmalı.
    assert any(
        r.name == kv.logger.name and r.levelno >= logging.WARNING and "silin" in r.getMessage() for r in caplog.records
    ), "silinen kart girdisi SESSİZ düştü — günlükte WARNING yok"
    # İkinci tur: düşecek yok → yeni iz yazılmaz (idempotens).
    kv.tur(pdb, tdb)
    assert len(_izler(tdb)) == 1, "boş turda yeniden 'silinen hasta' izi yazıldı"
    assert p2 in tdb.anonim_bekleyen_oku()


def test_KRITIK_B_kanonik_adimi_dusen_adayin_KARTI_SILINIRSE_girdisi_DUSER(o):
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    p1 = _hasta(pdb, "Zeytin Aday-E4")
    _seans(tdb, "Zeytin Aday-E4", p1)
    _onay(tdb)
    _tetik(pdb, "e4_kanonik_dus")
    s = kv.tur(pdb, tdb)
    assert s["anonimlestirilen"] == 0, f"aparat: kanonik adım düşmedi: {s}"
    assert p1 in tdb.anonim_bekleyen_oku(), "kartı DURAN adayın (kanonik adım düştü) girdisi listeden düşürüldü"
    _tetik_kaldir(pdb, "e4_kanonik_dus")
    assert pdb.delete_patient(p1) is True
    s = kv.tur(pdb, tdb)
    assert p1 not in tdb.anonim_bekleyen_oku(), (
        "kanonik adımı düşen adayın kartı silindi; girdisi listede SÜRESİZ kaldı"
    )
    assert s["tedavi_bekleyen"] == 0, f"tur sonucu bekleyen sayısı şişik: {s}"
    izler = _izler(tdb)
    assert [int(i["item_count"]) for i in izler] == [1], f"silinen kart izi yok / fazla / sayısı yanlış: {izler}"


def test_KARSIT_karti_DURAN_anonim_hastanin_girdisi_KALIR_ve_sonra_ISLENIR(o):
    """Kart silinmedikçe hiçbir girdi düşmez; tedavi adımı düzelince girdi işlenip düşer (B-3.34 sözleşmesi aynen). Silinen-kart izi YOK."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    p1, p2 = _A_kur(pdb, tdb)
    kv.tur(pdb, tdb)
    assert {p1, p2} <= set(tdb.anonim_bekleyen_oku()), "kartı DURAN hastaların girdisi düşürüldü"
    _tetik_kaldir(tdb, "e4_tedavi_dus")
    kv.tur(pdb, tdb)
    assert not tdb.anonim_bekleyen_oku(), "tedavi adımı düzeldiği hâlde girdiler işlenmedi"
    assert _izler(tdb) == [], "kart silinmediği hâlde 'silinen hasta' izi yazıldı"


def test_KARSIT_hasta_DB_okunamazken_HICBIR_girdi_DUSMEZ(o):
    """Varlık okunamıyorsa (GERÇEK 'no such table') girdi 'silinmiş' SAYILMAZ — liste aynen kalır, iz yok (fail-safe)."""
    from services import kvkk_anonimlestirme as kv

    pdb, tdb = o
    p1, p2 = _A_kur(pdb, tdb)
    with pdb._get_connection() as c:
        c.execute("ALTER TABLE patients RENAME TO patients_e4_gizli")
        c.commit()
    kv.tur(pdb, tdb)
    assert {p1, p2} <= set(tdb.anonim_bekleyen_oku()), "hasta DB'si okunamazken girdiler 'silinmiş' sayılıp düşürüldü"
    assert _izler(tdb) == [], "okuma hatasında 'silinen hasta' izi yazıldı"
