# -*- coding: utf-8 -*-
"""Y132 (S-F2-1.6, sahip — D3 devri → D5): anonimleştirmede serbest metinden ad temizliği eşiği 3 harf KALIR; 2 harfli adlar metinden
SİLİNMEZ (sıradan kelimelerin — "Su", "Al" — klinik metinden geri dönüşsüz silinmesi önlenir). Bugünkü davranış; değişiklik YOK.

Ölçülen önce (k5, HEAD `5bc99be1`): eşiği 2'ye indiren mutant (`thdb_pii.py` `len(m) >= 2`) anonimleştirme kümesinde (23 dosya, 100 test)
YEŞİL kalıyordu — karar kapısızdı. Bu kapı iki yönü birlikte ölçer: 3+ harfli ad metinden `[ANONIM]`a döner (eşik yükselirse KIRMIZI), 2 harfli
ad metinde KALIR (eşik düşerse KIRMIZI). Eşik değeri testte PİNLİ (kaynaktan okunmaz).
"""

from __future__ import annotations

import pytest


@pytest.fixture
def tdb(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    db = TreatmentHistoryDB(tmp_path / "gecmis")
    try:
        yield db
    finally:
        db.close_connections()


def _ozet(db, aid):
    with db._get_connection() as c:
        return c.execute("SELECT result_summary FROM ai_analyses WHERE id = ?", (aid,)).fetchone()[0]


@pytest.mark.parametrize(
    "ad, metin, kalmali",
    [
        ("Su", "Su tüketimi artmış; kontrol önerilir.", True),  # 2 harf: sıradan kelime — SİLİNMEZ (Y132)
        ("Bal", "Bal kilo kaybı gösteriyor.", False),  # 3 harf: eşiğin kendisi — temizlenir
        ("Pamuk", "Pamuk için ikinci kontrol.", False),
    ],
)
def test_KRITIK_ad_temizligi_ESIGI_uc_harf(tdb, ad, metin, kalmali):
    u = f"y132-{ad.lower()}"
    aid = tdb.add_ai_analysis(mode="AI", module_id="m", patient_name=ad, result_summary=metin, patient_uuid=u)
    assert aid, "aparat: AI kaydı yazılamadı"
    assert tdb.anonymize_patients_by_uuid([u], kimlikler={u: {"metinler": [ad], "ad_ile_kimliksiz": False}}) >= 0
    sonra = _ozet(tdb, aid)
    if kalmali:
        assert sonra == metin, f"2 harfli ad ('{ad}') klinik metinden SİLİNDİ — Y132 eşiği 3 harf: {sonra!r}"
    else:
        assert ad not in sonra and "[ANONIM]" in sonra, f"{len(ad)} harfli ad metinde KALDI: {sonra!r}"
