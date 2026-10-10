# -*- coding: utf-8 -*-
"""S-F.3 [ÖNERİLEN UYGULANDI] — AI geçmişi toplu silmesinin (ve ertelenmiş KVKK VACUUM'unun) ardından silinen metin DOSYADA kalmaz.

ÖLÇÜLEN KUSUR (2-F, Y121 sırasında): `clear_ai_analyses` "VACUUM ŞART — VACUUM tüm dosyayı yeniden yazdığı için silinen kişisel veri
gerçekten gider" diyor; WAL kipinde VACUUM yeni sayfaları WAL'a yazar, ESKİ sayfalar denetim noktasına kadar ana dosyada KALIR → "Tümünü
sil" sonrası 3 kaydın 3'ünün metni dosyada okunabiliyordu (ölçüldü, `kayit/aivac_sonda.txt`). Aynısı D1.58'in ertelenmiş VACUUM'unda.
Düzeltme: VACUUM'dan sonra D2.29'un silme sonrası denetim noktası (TRUNCATE). Y13 (güvenli silme) ilkesi.
GERÇEK: TreatmentHistoryDB (sentetik, tmp, şifresiz — bekçi null keyring), gerçek silme işlevleri; ölçüm ham `.db` + `-wal` baytlarında.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _kalan(db, belirtecler) -> int:
    p = Path(db.db_path)
    b = b"".join(f.read_bytes() for f in (p, p.with_name(p.name + "-wal")) if f.exists())
    return sum(1 for t in belirtecler if t.encode() in b)


@pytest.fixture
def db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    d = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield d
    finally:
        d.close_connections()


def _kayitlar(db, onek):
    belirtecler = [f"{onek}{i}" for i in range(3)]
    for t in belirtecler:
        assert db.add_ai_analysis(mode="vet", module_id="m", result_summary=f"bulgu {t} " + "x" * 300)
    assert _kalan(db, belirtecler) == 3, "aparat KÖR: belirteçler silmeden önce dosyada yok"
    return belirtecler


def test_KRITIK_SF3_tumunu_sil_VACUUM_sonrasi_metin_DOSYADA_kalmaz(db):
    """MUTASYON: VACUUM sonrası denetim noktası yok → KIRMIZI."""
    b = _kayitlar(db, "SF3TOPLU")
    assert db.clear_ai_analyses(None) == 3
    assert _kalan(db, b) == 0, (
        "AI geçmişi 'Tümünü sil' + VACUUM sonrası silinen metin dosyada KALDI (WAL eski sayfaları)"
    )


def test_KRITIK_SF3_ertelenmis_VACUUM_sonrasi_metin_DOSYADA_kalmaz(db):
    """Seans sürerken silme VACUUM'u erteler (D1.58); seans sonrası/bakımda koşan ertelenmiş VACUUM da kalıntı bırakmaz."""
    b = _kayitlar(db, "SF3ERTELE")
    assert db.clear_ai_analyses(None, vacuum_ertele=True) == 3
    assert db.vacuum_bekliyor_mu() is True
    assert db.bekleyen_vacuum_calistir() is True
    assert _kalan(db, b) == 0, "ertelenmiş KVKK VACUUM'undan sonra silinen metin dosyada KALDI"


def test_KARSIT_kalan_kayit_DOSYADA_durur(db):
    """Aşırı silme yok: yalnız bir hekimin kayıtları silinince ötekinin metni dosyada kalır."""
    db.add_ai_analysis(mode="vet", module_id="m", result_summary="SF3KALAN " + "x" * 300, operator_email="b@k.com")
    sil = db.add_ai_analysis(mode="vet", module_id="m", result_summary="SF3SIL " + "x" * 300, operator_email="a@k.com")
    assert sil and db.clear_ai_analyses("a@k.com") == 1
    assert _kalan(db, ["SF3KALAN"]) == 1 and _kalan(db, ["SF3SIL"]) == 0
