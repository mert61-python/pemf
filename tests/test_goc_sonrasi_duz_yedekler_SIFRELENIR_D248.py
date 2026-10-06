# -*- coding: utf-8 -*-
"""D2.48 (B-3.29 · A-08) — DÜZ-METİN→SQLCIPHER GÖÇÜ, doğrulanmış başarıdan sonra düz dönemden kalan
`migration_backups/*.db` ve `backups/*.db` kopyalarını AYNI anahtarla ŞİFRELER (silmez).

ÖLÇÜLEN KUSUR (DENETIM-03 B-3.29): düz dönemde şema göçü öncesi alınan `pre_migration_v<N>_*.db` yedeği ve günlük
bakımın `backups/pemf_*.db` kopyaları düz-metin; at-rest göçü yalnız canlı DB'yi şifreliyordu → hasta adları diskte
düz kalıyordu (at-rest'i açan B-3.44/B-3.45 düz kurulumları göçe soktuğunda uyanır).
Sahip ilkesi (A-08 ile uyumlu): kopyalar SİLİNMEZ — şifrelenir (aynı ad, aynı içerik, şifreli).
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

K = "D248-at-rest-anahtar"
_SQLITE_BASLIK = b"SQLite format 3\x00"


@pytest.fixture(params=sahte_sqlcipher.BAGLAYICILAR)
def baglayici(request, monkeypatch):
    return sahte_sqlcipher.baglayici_kur(request.param, monkeypatch)


def _duz_db(yol: Path, ad: str) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(yol))
    c.execute("CREATE TABLE kayit (ad TEXT)")
    c.execute("INSERT INTO kayit VALUES (?)", (ad,))
    c.commit()
    c.close()


def _anahtarla_acilir(mod, yol: Path, anahtar: str) -> bool:
    c = mod.connect(str(yol))
    try:
        c.execute(f"PRAGMA key='{anahtar}'")
        return c.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] > 0
    except Exception:
        return False
    finally:
        c.close()


def _gocu_kur(app: Path, monkeypatch) -> Path:
    from database import sqlcipher_util as su

    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: K)
    monkeypatch.delenv("PEMF_KEEP_PLAIN_BACKUP", raising=False)
    db = app / "pemf_treatment_history.db"
    _duz_db(db, "CanliHasta-D248")
    return db


def test_KRITIK_goc_sonrasi_DUZ_yedekler_SIFRELENIR_silinmez(baglayici, tmp_path, monkeypatch, caplog):
    """MUTASYON: göç sonrası düz yedekleri şifreleme adımını kaldırmak → KIRMIZI."""
    from database import sqlcipher_util as su

    app = tmp_path / "PEMF_GUI"
    db = _gocu_kur(app, monkeypatch)
    yedekler = [
        app / "migration_backups" / "pre_migration_v2_20261001_000000.db",
        app / "backups" / "pemf_treatment_history_20261001_000000.db",
        app / "backups" / "pemf_patients_20261001_000000.db",
    ]
    for i, y in enumerate(yedekler):
        _duz_db(y, f"YedekHasta{i}-D248")
        os.utime(y, (1_700_000_000 + i, 1_700_000_000 + i))  # eski yedek zamanı (rotasyon mtime'a bakar)
    ilgisiz = app / "backups" / "notlar.json"
    ilgisiz.write_text('{"ilgisiz": true}', encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("d248"))
    assert db.read_bytes()[:16] != _SQLITE_BASLIK, "ön koşul: canlı DB göçmeli"
    # Sahte bağlayıcı içeriği gerçekten şifrelemez (yalnız başlık — anahtar denetimini taklit eder, gizliliği değil):
    # hasta adı baytı ölçütü yalnız GERÇEK kolda anlamlı.
    gercek_kol = baglayici is not sahte_sqlcipher
    for i, y in enumerate(yedekler):
        assert y.exists(), f"{y.name} SİLİNDİ (şifrelenmeliydi)"
        bas = y.read_bytes()
        assert bas[:16] != _SQLITE_BASLIK, f"{y.name} hâlâ DÜZ-METİN"
        if gercek_kol:
            assert f"YedekHasta{i}-D248".encode() not in bas, f"{y.name}: hasta adı diskte düz"
        assert _anahtarla_acilir(baglayici, y, K), f"{y.name} at-rest anahtarıyla AÇILMIYOR (veri kaybı)"
        assert y.name in caplog.text, f"{y.name} şifrelendiği günlükte adıyla yok"
        assert int(y.stat().st_mtime) == 1_700_000_000 + i, (
            f"{y.name}: değişiklik zamanı KORUNMADI — rotasyon şifrelenen eski yedeği 'en yeni' sanar"
        )
    assert ilgisiz.read_text(encoding="utf-8") == '{"ilgisiz": true}', "DB olmayan dosyaya dokunuldu"
    assert not list(app.rglob("*.enc.tmp")), "geçici şifreli kopya artığı kaldı"


def test_KRITIK_bir_yedek_SIFRELENEMEZSE_dokunulmaz_neden_LOGLANIR(baglayici, tmp_path, monkeypatch, caplog):
    """Bir kopyanın yerine konması düşerse (dosya kilitli) o kopya DÜZ ama SAĞLAM kalır, adıyla loglanır; diğerleri
    yine şifrelenir; geçici dosya kalmaz."""
    from database import sqlcipher_util as su

    app = tmp_path / "PEMF_GUI"
    db = _gocu_kur(app, monkeypatch)
    kilitli = app / "backups" / "pemf_patients_20261001_000000.db"
    digeri = app / "backups" / "pemf_treatment_history_20261001_000000.db"
    _duz_db(kilitli, "KilitliYedek-D248")
    _duz_db(digeri, "DigerYedek-D248")
    once = kilitli.read_bytes()
    gercek_replace = os.replace

    def _replace(src, dst, *a, **k):
        if os.path.normcase(str(dst)) == os.path.normcase(str(kilitli)):
            raise PermissionError(32, "Dosya baska bir islem tarafindan kullaniliyor (taklit)")
        return gercek_replace(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", _replace)
    with caplog.at_level(logging.WARNING):
        su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("d248"))
    assert kilitli.read_bytes() == once, "şifrelenemeyen yedek BOZULDU"
    assert kilitli.name in caplog.text and "SIFRELENEMEDI" in caplog.text, (
        f"şifrelenemeyen yedek adıyla loglanmadı:\n{caplog.text[-1000:]}"
    )
    assert digeri.read_bytes()[:16] != _SQLITE_BASLIK, "diğer yedek şifrelenmedi"
    assert not list(app.rglob("*.enc.tmp")), "geçici şifreli kopya artığı kaldı"


def test_KARSIT_goc_IPTAL_olursa_yedeklere_DOKUNULMAZ(baglayici, tmp_path, monkeypatch):
    """Göç doğrulanmış başarıyla bitmezse (kilit) yedekler ŞİFRELENMEZ — canlı DB düzken yedeği şifrelemek, geri
    dönüş kopyasını anahtara bağlar."""
    from database import sqlcipher_util as su

    app = tmp_path / "PEMF_GUI"
    db = _gocu_kur(app, monkeypatch)
    y = app / "migration_backups" / "pre_migration_v2_20261001_000000.db"
    _duz_db(y, "IptalYedek-D248")
    once = y.read_bytes()
    okuyucu = sqlite3.connect(str(db))
    okuyucu.execute("SELECT * FROM kayit").fetchall()
    try:
        su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("d248"))
    finally:
        okuyucu.close()
    assert db.read_bytes()[:16] == _SQLITE_BASLIK, "ön koşul: göç iptal olmalı"
    assert y.read_bytes() == once, "göç İPTAL olduğu halde yedek değiştirildi"


def test_KRITIK_dogrulanamayan_sifreli_kopya_YERINE_KONMAZ_yedek_KAYBOLMAZ(tmp_path, monkeypatch, caplog):
    """Şifreli kopya doğrulanamazsa (eksik/boş dışa aktarım) özgün yedek YERİNDE ve SAĞLAM kalır. Sahte bağlayıcıda
    yedeğin dışa aktarımı GEÇERLİ ama BOŞ şemalı şifreli dosya üretecek biçimde bozulur (canlı DB'ninki sağlam).
    MUTASYON: şema karşılaştırmalı doğrulamayı kaldırmak → KIRMIZI (yedek boş kopyayla değişir = VERİ KAYBI)."""
    import sqlite3 as _sq

    from database import sqlcipher_util as su

    sahte_sqlcipher.baglayici_kur("sahte", monkeypatch)
    app = tmp_path / "PEMF_GUI"
    db = _gocu_kur(app, monkeypatch)
    y = app / "backups" / "pemf_patients_20261001_000000.db"
    _duz_db(y, "DogrulamaYedek-D248")
    once = y.read_bytes()
    gercek_aktar = sahte_sqlcipher.Baglanti._disa_aktar

    def _bos_aktar(self):
        hedef, anahtar = self._ekli
        if not os.path.basename(hedef).startswith("pemf_patients_"):
            return gercek_aktar(self)
        bos = hedef + ".bos"
        c = _sq.connect(bos)
        c.execute("CREATE TABLE gecici (a)")
        c.execute("DROP TABLE gecici")  # geçerli sayfa, SIFIR tablo
        c.commit()
        c.close()
        veri = open(bos, "rb").read()
        os.remove(bos)
        with open(hedef, "wb") as f:
            f.write(sahte_sqlcipher._baslik(anahtar) + veri[len(_SQLITE_BASLIK) :])

    monkeypatch.setattr(sahte_sqlcipher.Baglanti, "_disa_aktar", _bos_aktar)
    with caplog.at_level(logging.WARNING):
        su.migrate_to_encrypted_if_needed(db, app, logging.getLogger("d248"))
    assert db.read_bytes()[:16] != _SQLITE_BASLIK, "ön koşul: canlı DB göçmeli"
    assert y.read_bytes() == once, "doğrulanamayan (boş) şifreli kopya yedeğin YERİNE KONDU — veri kaybı"
    assert "SIFRELENEMEDI" in caplog.text and y.name in caplog.text
    assert not list(app.rglob("*.enc.tmp"))


def test_KRITIK_plan_kapisi_duz_donem_on_yedegi_gocten_sonra_HASTA_ADI_tasimaz(tmp_path, monkeypatch):
    """Plan kapısı (gerçek TreatmentHistoryDB, gerçek sqlcipher3): düz dönemde şema sürümü 2 iken açılış göç öncesi
    yedek üretir (hasta adı DÜZ içerir — ön koşul); bayrak + anahtarla ikinci açılış gerçek at-rest göçünü koşar.
    Sonra `migration_backups/` ve `backups/` altında hasta adı baytı OLMAMALI; yedekler yerinde ve anahtarla açılır."""
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    gercek = sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
    app = tmp_path / "PEMF_GUI"
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    db = thdb.TreatmentHistoryDB(app)
    assert db.at_rest_encrypted is False
    db.end_session(db.start_session("Manuel", patient_name="DuzDonemHasta-D248"))
    db._set_system_setting("db_schema_version", "2", "test: duz donemde goc on-yedegi uretilsin")
    db.close_connections()
    del db
    db = thdb.TreatmentHistoryDB(app)  # düz dönem: göç öncesi yedek alınır
    db.close_connections()
    del db
    on_yedek = list((app / "migration_backups").glob("pre_migration_v2_*.db"))
    assert on_yedek and b"DuzDonemHasta-D248" in on_yedek[0].read_bytes(), "ön koşul: düz ön-yedek hasta adı taşımalı"
    (app / "backups").mkdir(exist_ok=True)
    gunluk = app / "backups" / "pemf_treatment_history_20261001_000000.db"
    gunluk.write_bytes(on_yedek[0].read_bytes())  # düz dönemin günlük yedeği

    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: K)
    db = thdb.TreatmentHistoryDB(app)
    try:
        assert db.at_rest_encrypted is True
        assert [s.get("patient_name") for s in db.get_session_history(limit=5)] == ["DuzDonemHasta-D248"]
    finally:
        db.close_connections()
    dosyalar = [p for alt in ("migration_backups", "backups") for p in sorted((app / alt).glob("*.db"))]
    duz_pii = [f"{p.parent.name}/{p.name}" for p in dosyalar if b"DuzDonemHasta-D248" in p.read_bytes()]
    assert duz_pii == [], f"göçten sonra hasta adı diskte DÜZ: {duz_pii}"
    acilmayan = [f"{p.parent.name}/{p.name}" for p in dosyalar if not _anahtarla_acilir(gercek, p, K)]
    assert acilmayan == [], f"at-rest anahtarıyla açılmayan yedek (düz kaldı ya da bozuldu): {acilmayan}"
    assert on_yedek[0].exists() and gunluk.exists(), "düz dönem yedeği SİLİNDİ (şifrelenmeliydi)"
