# -*- coding: utf-8 -*-
"""D2.47 (B-3.15 · A-08) — GÖÇTE KALAN DÜZ-METİN KOPYA: kilitte kopya YAZILMAZ; kalanı adıyla LOGLANIR ve KORUMAYA alınır;
günlük "PII riski kapatıldı" diye yalan SÖYLEMEZ.

ÖLÇÜLEN KUSUR (DENETIM-03 B-3.15): göçün `db → .plain.bak` taşıması `shutil.move` ile yapılıyordu. Canlı DB'de KALICI
bir okuyucu (yedekleyici, ikinci süreç, açık bağlantı) varken Windows'ta yeniden adlandırma düşer; `shutil.move`
`copy2` geri dönüşüyle `.plain.bak`a TÜM düz-metin PII'nin KOPYASINI yazar, kaynağı silemez, göç iptal olur. Sonraki
başarılı göç o kopyayı `.plain.bak.<zaman>` olarak kenara alır (silinmez — doğru) ama korumaz, adını anmaz ve yeni
yedeği güvenli-silince "at-rest PII riski kapatıldı" der: diskte korumasız tam düz-metin kopya durur.

SAHİP KARARI A-08: göçte kalan `.plain.bak` düz-metin kopyası LOGLANIR ve korumaya alınır (SİLİNMEZ); canlı düz-metin
DB karantinaya ALINMAZ.

Kilit GERÇEK bağlantıyla kurulur (sahte `shutil.move` değil). Bağlayıcı sahte + gerçek (göç alt kümesi).
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from pathlib import Path

import pytest
import sahte_sqlcipher

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

K = "D247-at-rest-anahtar"
PII = "HastaAdi-D247-Boncuk"
_SQLITE_BASLIK = b"SQLite format 3\x00"


@pytest.fixture(params=sahte_sqlcipher.BAGLAYICILAR)
def baglayici(request, monkeypatch):
    return sahte_sqlcipher.baglayici_kur(request.param, monkeypatch)


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    """Düz-metin DB + at-rest anahtarı; ACL kilidi kaydedilir (keep_current_user görülsün). Sürecin hesabını KORUYAN
    kilit GERÇEK uygulanır; hesabı DIŞARIDA bırakan kilit (emanet) tmp'de silinemez artık bırakacağı için yalnız
    kaydedilir (başarılı sayılır)."""
    from database import sqlcipher_util as su
    from utils import file_acl

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    db = app / "patients.db"
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE kayit (ad TEXT)")
    c.execute("INSERT INTO kayit VALUES (?)", (PII,))
    c.commit()
    c.close()
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: K)
    monkeypatch.delenv("PEMF_KEEP_PLAIN_BACKUP", raising=False)
    monkeypatch.delenv("PEMF_KEEP_PLAIN_BAK", raising=False)
    kilitler = []
    gercek = file_acl.lock_down_file

    def _kayitli(yol, *a, **k):
        tut = bool(k.get("keep_current_user", a[0] if a else False))
        sonuc = gercek(yol, *a, **k) if tut else True
        kilitler.append((os.path.normcase(str(yol)), tut, sonuc))
        return sonuc

    monkeypatch.setattr(file_acl, "lock_down_file", _kayitli)
    return app, db, kilitler


def _duz_metin_kopyalar(app: Path) -> list:
    out = []
    for p in sorted(app.glob("*.plain.bak*")):
        with open(p, "rb") as f:
            if f.read(16) == _SQLITE_BASLIK:
                out.append(p.name)
    return out


def test_KRITIK_kalici_okuyucu_KILIDINDE_goc_duz_metin_KOPYA_yazmadan_DURUR(baglayici, ortam, caplog):
    """A-08(b): canlı DB'de gerçek okuyucu bağlantısı açıkken göç iptal olur ama `.plain.bak`a KOPYA bırakmaz; canlı DB
    yerinde ve düz-metin (karantina yok). MUTASYON: göç taşımasında `copy2` geri dönüşünü geri açmak → KIRMIZI."""
    from database import sqlcipher_util as su

    app, db, _ = ortam
    okuyucu = sqlite3.connect(str(db))
    okuyucu.execute("SELECT * FROM kayit").fetchall()  # tutamak AÇIK (FILE_SHARE_DELETE yok → ad değiştirme düşer)
    try:
        with caplog.at_level(logging.WARNING):
            su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("d247"))
    finally:
        okuyucu.close()
    assert db.read_bytes()[:16] == _SQLITE_BASLIK, "ön koşul: kilitte göç iptal olmalı (canlı DB düz-metin yerinde)"
    assert _duz_metin_kopyalar(app) == [], (
        f"kilitte göç DÜZ-METİN KOPYA bıraktı (copy2 geri dönüşü): {_duz_metin_kopyalar(app)}"
    )
    assert not list(app.glob("*.acilamadi-*")), "canlı düz-metin DB karantinaya alındı (A-08 ihlali)"


def test_KRITIK_kalan_duz_metin_kopya_ADIYLA_loglanir_KORUMAYA_alinir_kapatildi_DENMEZ(baglayici, ortam, caplog):
    """A-08(a): önceki bir sürümün kilitli göçünden kalmış tam düz-metin `.plain.bak` diskte. Başarılı göç onu silmez
    (kenara alır), ama ADIYLA loglar, ACL ile KORUR ve "PII riski kapatıldı" DEMEZ.
    MUTASYON: kalan kopyaları korumayı/loglamayı kaldırmak ya da "kapatıldı"yı koşulsuz yazmak → KIRMIZI."""
    from database import sqlcipher_util as su

    app, db, kilitler = ortam
    (app / "patients.db.plain.bak").write_bytes(db.read_bytes())  # eski sürümün copy2 artığı (tam düz-metin)
    # Daha ÖNCEKİ bir turda kenara alınmış kopya: bu turda `_yedegi_kenara_al` onu anmaz — adını YALNIZ kalan-kopya
    # koruması söyleyebilir (katman ayrı gözlensin).
    (app / "patients.db.plain.bak.20250101_000000").write_bytes(db.read_bytes())
    with caplog.at_level(logging.WARNING):
        su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("d247"))
    assert db.read_bytes()[:16] != _SQLITE_BASLIK, "ön koşul: göç tamamlanmalı"
    kalan = _duz_metin_kopyalar(app)
    assert kalan and all(ad.startswith("patients.db.plain.bak.") for ad in kalan), (
        f"ön koşul / SİLME YOK: önceki düz-metin kopya kenara alınmış olarak durmalı: {kalan}"
    )
    for ad in kalan:
        assert ad in caplog.text, f"kalan düz-metin kopya {ad} ADIYLA loglanmadı"
        hedef = os.path.normcase(str(app / ad))
        assert any(y == hedef and tut and sonuc for y, tut, sonuc in kilitler), (
            f"kalan düz-metin kopya {ad} KORUMAYA alınmadı (ACL, sürecin hesabı korunarak): {kilitler}"
        )
    assert "kapatıldı" not in caplog.text, (
        "diskte korumalı ama DÜZ-METİN kopya dururken günlük 'PII riski kapatıldı' dedi"
    )


def test_KRITIK_emanet_kipinde_ONCEKI_kopya_da_ADIYLA_loglanir_KORUNUR(baglayici, ortam, caplog, monkeypatch):
    """Emanet kipinde (PEMF_KEEP_PLAIN_BACKUP=1) bu turun yedeği bilinçli saklanır; ÖNCEKİ turlardan kalan düz-metin
    kopya da SİLİNMEZ, adıyla loglanır ve korunur. Bu kipte özet satırı yoktur — adı YALNIZ kalan-kopya koruması söyler.
    MUTASYON: kalan kopyanın tek tek loglanmasını kaldırmak → KIRMIZI (varsayılan kipte özet satırı maskelerdi)."""
    from database import sqlcipher_util as su

    app, db, kilitler = ortam
    monkeypatch.setenv("PEMF_KEEP_PLAIN_BACKUP", "1")
    ad = "patients.db.plain.bak.20250101_000000"
    (app / ad).write_bytes(db.read_bytes())
    with caplog.at_level(logging.WARNING):
        su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("d247"))
    assert db.read_bytes()[:16] != _SQLITE_BASLIK, "ön koşul: göç tamamlanmalı"
    assert (app / ad).exists(), "önceki düz-metin kopya SİLİNDİ (A-08: silinmez)"
    assert ad in caplog.text, f"emanet kipinde önceki düz-metin kopya {ad} ADIYLA loglanmadı"
    hedef = os.path.normcase(str(app / ad))
    assert any(y == hedef and tut and sonuc for y, tut, sonuc in kilitler), (
        f"emanet kipinde önceki düz-metin kopya KORUMAYA alınmadı: {kilitler}"
    )


def test_KARSIT_kalan_kopya_YOKSA_kapatildi_DOGRU_soylenir(baglayici, ortam, caplog):
    from database import sqlcipher_util as su

    app, db, _ = ortam
    with caplog.at_level(logging.WARNING):
        su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("d247"))
    assert db.read_bytes()[:16] != _SQLITE_BASLIK
    assert _duz_metin_kopyalar(app) == []
    assert "kapatıldı" in caplog.text, "kopya kalmadığında doğru sonuç söylenmeli"


def test_KRITIK_plan_kapisi_kilitli_goc_sonra_basarili_goc_DISKTE_duz_metin_KOPYA_kalmaz(baglayici, ortam, caplog):
    """Plan kapısı: kalıcı okuyucu altında göç düşer, okuyucu kapanır, ikinci göç GERÇEK `migrate_to_encrypted_if_needed`
    ile başarılı olur. Eskiden 'SQLite format 3' başlıklı `*.plain.bak*` kalıyor ve günlük 'kapatıldı' diyordu."""
    from database import sqlcipher_util as su

    app, db, _ = ortam
    okuyucu = sqlite3.connect(str(db))
    okuyucu.execute("SELECT * FROM kayit").fetchall()
    try:
        su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("d247"))
    finally:
        okuyucu.close()
    with caplog.at_level(logging.WARNING):
        su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("d247"))
    assert db.read_bytes()[:16] != _SQLITE_BASLIK, "ikinci göç tamamlanmalıydı"
    kalan = _duz_metin_kopyalar(app)
    assert not kalan or "kapatıldı" not in caplog.text, f"düz-metin kopya {kalan} dururken 'kapatıldı' dendi"
    assert kalan == [], f"diskte DÜZ-METİN kopya kaldı: {kalan}"


def test_KRITIK_acilista_KENARA_alinmis_duz_metin_kopyalar_da_KORUNUR(tmp_path, monkeypatch):
    """Açılış ACL sertleştirmesi yalnız `*.plain.bak`ı kilitliyordu; kenara alınmış `*.plain.bak.<zaman>` kopyaları
    (aynı tam düz-metin PII) korumasız kalıyordu. MUTASYON: deseni yeniden `*.plain.bak` yapmak → KIRMIZI."""
    import backend_service as bs
    from utils import file_acl

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    kenar = app / "patients.db.plain.bak.20261007_010101"
    kenar.write_bytes(_SQLITE_BASLIK + b"duz-metin")
    kilitler = []
    monkeypatch.setattr(file_acl, "lock_down_file", lambda yol, *a, **k: kilitler.append((Path(yol), k)) or True)
    bs._harden_secret_file_acls(app, logging.getLogger("d247"))
    kenar_kilidi = [k for y, k in kilitler if y == kenar]
    assert kenar_kilidi, f"kenara alınmış düz-metin kopya açılışta KORUMAYA alınmadı: {[str(y) for y, _ in kilitler]}"
    assert kenar_kilidi[0].get("keep_current_user") is True, (
        "düz-metin yedek sürecin hesabı DIŞARIDA bırakılarak kilitlendi (toparlama kendi yedeğini açamaz)"
    )
