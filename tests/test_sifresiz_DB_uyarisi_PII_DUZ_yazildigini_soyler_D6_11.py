# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.11 (B-3.72) — düz-metin yolundaki açılış uyarısı ve yorumlar PII'nin maskelendiğini SÖYLEMEZ; adların düz yazıldığını söyler.

ÖLÇÜLEN (HEAD ebf1c3fe, 2026-10-28): `TreatmentHistoryDB._create_connection` şifresiz dala düşünce (PEMF_ENCRYPT_AT_REST≠1,
SQLCipher yok) günlüğe "B-1.3 KORUMASI: kisi-tanimlayici PII … '[SIFRELENMEMIS-DB]' ile MASKELENIR (sifresiz DB'ye gercek PII
yazilmaz)" yazıyordu. Oysa SAHİP KARARI (2026-07-28) maske VARSAYILAN KAPALI (`thdb_pii._redact_pii`: yalnız
`PEMF_MASK_HISTORY_PII=1` iken maske) → aynı açılışta ad, operatör adı ve notlar GERÇEK değerleriyle diske yazılıyordu. Uyarı yalnız
`_encryption_warned` bayrağına bağlı; maske ayarına bakan koşul YOK. Aynı bayat iddia yorumlarda da vardı (thdb_ai_gecmisi,
thdb_seans, treatment_history_db B-1.3 bloğu, test_pii_protection başlığı).

⚠️ Uyarı GÜNLÜĞE gider (`self.logger.warning`; kullanıcıya ileten günlük işleyicisi yok — i18n/KURALLAR §5: günlük iletileri Türkçe
kalır, kataloğa girmez). ⚠️ Maske varsayılan-açık YAPILMAZ (sahip kararı; "Geri EKLEME") — bu kapı yalnız METNİ davranışa bağlar.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
DB = KOK / "apps" / "backend" / "database"
UYARI_IMI = "AT-REST SIFRELEME KAPALI: tedavi gecmisi"


def _sifresiz_ac(monkeypatch, caplog, temp_app_data, maske: str | None):
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    if maske is None:
        monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)
    else:
        monkeypatch.setenv("PEMF_MASK_HISTORY_PII", maske)
    # Şifresiz dal: SQLCipher bağlantısı kurulamıyor (binding yok / anahtar yok) — dev / yanlış yapılandırma.
    monkeypatch.setattr(TreatmentHistoryDB, "_connect_sqlcipher_if_configured", lambda self: None)
    with caplog.at_level(logging.WARNING):
        db = TreatmentHistoryDB(temp_app_data)
    uyarilar = [r.getMessage() for r in caplog.records if UYARI_IMI in r.getMessage()]
    assert len(uyarilar) == 1, f"aparat: şifresiz tedavi DB'si açılış uyarısı tek kez bekleniyordu: {len(uyarilar)}"
    assert db.at_rest_encrypted is False, "aparat: şifresiz dala düşülmedi"
    return db, uyarilar[0]


def _diskteki_seans(db, sid):
    c = sqlite3.connect(str(db.db_path))
    try:
        return c.execute(
            "SELECT operator_name, patient_name, patient_notes FROM treatment_sessions WHERE id=?", (sid,)
        ).fetchone()
    finally:
        c.close()


def test_KRITIK_sifresiz_acilis_uyarisi_MASKELENIR_demez_adlarin_DUZ_yazildigini_soyler(
    temp_app_data, monkeypatch, caplog
):
    db, uyari = _sifresiz_ac(monkeypatch, caplog, temp_app_data, maske=None)
    # Davranış (sahip kararı): varsayılanda maske YOK — ad aynen döner ve diske aynen yazılır.
    assert db._redact_pii("Boncuk") == "Boncuk", "aparat: maske varsayılanda AÇIK çıktı (sahip kararı: KAPALI)"
    sid = db.start_session("Manuel", operator_name="Dr Mert", patient_name="Boncuk")
    db.end_session(sid, patient_notes="gizli not", duration_minutes=1)
    assert _diskteki_seans(db, sid) == ("Dr Mert", "Boncuk", "gizli not"), (
        "aparat: varsayılanda diske gerçek değer yazılmadı"
    )
    # Metin ↔ davranış.
    assert "MASKELENIR" not in uyari.upper(), (
        f"şifresiz uyarı PII'nin MASKELENDİĞİNİ söylüyor; adlar düz yazılıyor: {uyari!r}"
    )
    assert "gercek pii yazilmaz" not in uyari.lower(), f"şifresiz uyarı 'gerçek PII yazılmaz' diyor: {uyari!r}"
    assert "GERCEK degerleriyle DUZ yaziliyor" in uyari, f"şifresiz uyarı adların DÜZ yazıldığını söylemiyor: {uyari!r}"
    assert "PEMF_MASK_HISTORY_PII=1" in uyari, f"şifresiz uyarı opt-in maskenin yolunu söylemiyor: {uyari!r}"
    assert "PEMF_ENCRYPT_AT_REST=1" in uyari and "pemf_secrets.json" in uyari, (
        f"şifresiz uyarı doğru üretim çözümünü (şifreleme + anahtar yeri) söylemiyor: {uyari!r}"
    )


def test_opt_in_maskede_uyari_yine_DOGRU_ve_maske_CALISIR(temp_app_data, monkeypatch, caplog):
    db, uyari = _sifresiz_ac(monkeypatch, caplog, temp_app_data, maske="1")
    assert db._redact_pii("Boncuk") == db._PII_REDACTION, "opt-in maske (PEMF_MASK_HISTORY_PII=1) ÇALIŞMIYOR"
    sid = db.start_session("Manuel", operator_name="Dr Mert", patient_name="Boncuk")
    assert _diskteki_seans(db, sid)[1] == db._PII_REDACTION
    # Uyarı her iki durumu da doğru anlatır: =1 iken yazılan yer tutucuyu adıyla verir.
    assert f"'{db._PII_REDACTION}' yazilir" in uyari, (
        f"şifresiz uyarı opt-in maskenin yer tutucusunu söylemiyor: {uyari!r}"
    )
    assert "MASKELENIR" not in uyari.upper()


#: Yorumlarda / başlıklarda maskenin VARSAYILANDA açık olduğunu söyleyen (sahip kararından önceki) ifadeler.
YASAK_IFADELER = (
    "MASKELENIR (sifresiz DB'ye gercek PII yazilmaz)",
    "şifresiz DB'de düz-metin PII sızmaz",
    "gerçek PII'yi DÜZ-METİN yazmak yerine maskele",
    "şifresiz DB'ye gerçek PII yazma",
    "PII maskesi (şifresiz modda da uygula)",
    "at-rest şifreleme YOKken kişi-tanımlayıcı PII'yi maskele",
    "şifresiz DB'de gerçek PII yazılmaz",
)
TARANAN = (
    DB / "treatment_history_db.py",
    DB / "thdb_ai_gecmisi.py",
    DB / "thdb_seans.py",
    DB / "thdb_pii.py",
    KOK / "tests" / "test_pii_protection.py",
)


@pytest.mark.parametrize("yol", TARANAN, ids=lambda p: p.name)
def test_yorumlar_maskeyi_VARSAYILANDA_acik_diye_anlatmaz(yol):
    metin = yol.read_text(encoding="utf-8")
    bulunan = [i for i in YASAK_IFADELER if i in metin]
    # Tur 2 (çürütücü): birebir liste yeni yazılmış eş anlamlı iddiayı ("şifresiz modda PII maskelenir, gerçek ad yazılmaz")
    # kaçırıyordu → aynı satırda "şifresiz … maskelenir" ya da "gerçek PII / ad / kişi … yazılmaz / sızmaz" de yasak.
    # (KVKK saklama maskelemesi / opt-in anlatımı "şifresiz" ile birlikte "maskelenir" DEMEZ — bugün eşleşme yok.)
    bulunan += [
        f"{no}: {s.strip()[:120]}"
        for no, s in enumerate(metin.splitlines(), 1)
        if YASAK_DESEN.search(s) and not any(i in s for i in YASAK_IFADELER)
    ]
    assert not bulunan, f"{yol.name} maskeyi varsayılanda açık diye anlatıyor (sahip kararı: KAPALI): {bulunan}"


YASAK_DESEN = re.compile(
    r"(?:şifresiz|sifresiz)[^.\n]{0,40}maskelen(?:ir|iyor)\b"
    r"|(?:gerçek|gercek)\s+(?:PII|ad|adı|adlar|kişi|kisi)\w*[^.\n]{0,30}(?:yazılmaz|yazilmaz|sızmaz|sizmaz)",
    re.IGNORECASE,
)
