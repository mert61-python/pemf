# -*- coding: utf-8 -*-
"""D2.46 (B-3.10 · B-3.48 · B-3.53 · Y9) — KARANTİNA YALNIZ "şifreli bağlantı + okunmuş anahtar + gerçek uyuşmazlık".

ÖLÇÜLEN KUSURLAR (DENETIM-03):
  B-3.10 Tedavi DB'sinde WAL ayarı OperationalError verince bağlantı KOŞULSUZ düz `sqlite3`e düşüyordu: doğru anahtarla
         açılmış şifreli geçmiş "file is not a database" ile uyuşmazlık sayılıp KARANTİNAYA gidiyor; ilk kurulumda
         şema ve PII DÜZ-METİN yazılıyor, `at_rest_encrypted` True kalıyordu.
  B-3.48 Hasta DB'si: anahtar var ama sqlcipher3 binding YOK (bayrak ≠ 1) → düz bağlantı şifreli dosyayı açamıyor →
         karar `self._cipher_key`e bakıyordu → sağlam şifreli `patients.db` KARANTİNAYA, yerine DÜZ-METİN DB.
  B-3.53 `karantinaya_al`: ana dosya taşındıktan sonra `-wal`/`-shm` taşıması düşerse ana dosya karantinada kalıyor,
         `-wal` yerinde yetim kalıyor, dönüş yalnız None; sonraki açılış ana dosyayı YOK görüp BOŞ DB kuruyordu.
Sahte EN ALT katta: WAL pragmasında tek seferlik OperationalError (bağlantı vekili), `import_sqlcipher` → None,
`shutil.move` (yalnız `-wal`/geri taşıma); ürün zinciri gerçek. Uçtan uca (Y9) kol: D1.37 aparatı "binding_yok".
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import sys
from pathlib import Path

import pytest
import sahte_sqlcipher

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

K = "D246-dogru-anahtar"
_SQLITE_BASLIK = b"SQLite format 3\x00"


@pytest.fixture(params=sahte_sqlcipher.BAGLAYICILAR)
def baglayici(request, monkeypatch):
    return sahte_sqlcipher.baglayici_kur(request.param, monkeypatch)


def _ozet(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _karantina(app: Path) -> list:
    return sorted(p.name for p in app.glob("*.acilamadi-*"))


def _sifreli_db_kur(mod, yol: Path, anahtar: str) -> None:
    kaynak = yol.with_name(yol.name + ".kaynak")
    c = sqlite3.connect(str(kaynak))
    c.execute("CREATE TABLE kayit (ad TEXT)")
    c.execute("INSERT INTO kayit VALUES ('SaglamSifreliHasta')")
    c.commit()
    c.close()
    k = mod.connect(str(kaynak))
    try:
        hedef = str(yol).replace("'", "''")
        k.execute(f"ATTACH DATABASE '{hedef}' AS enc KEY '{anahtar}'")
        k.execute("SELECT sqlcipher_export('enc')")
        k.execute("DETACH DATABASE enc")
    finally:
        k.close()
    kaynak.unlink()
    assert yol.read_bytes()[:16] != _SQLITE_BASLIK, "ön koşul: DB şifreli kurulmalı"


def _tedavi_anahtarli(monkeypatch):
    """Gerçek sqlcipher3 + birincil anahtar K (SecretsManager yerine; legacy boş)."""
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: K)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    return thdb


def _wal_bir_kez_dusur(monkeypatch, thdb, yeniden_acilmaz: bool = False) -> dict:
    """İLK SQLCipher bağlantısında `PRAGMA journal_mode` bir kez OperationalError verir (WAL kilidi / -shm yazılamaz).
    `yeniden_acilmaz`: WAL düşüşünden SONRAKİ SQLCipher açılışları None döner (anahtar o arada açmaz oldu)."""
    gercek = thdb.TreatmentHistoryDB._connect_sqlcipher_if_configured
    durum = {"dustu": 0, "yeniden": 0}

    class _Vekil:
        def __init__(self, c):
            object.__setattr__(self, "_c", c)

        def execute(self, sql, *a, **k):
            if durum["dustu"] == 0 and str(sql).strip().upper().startswith("PRAGMA JOURNAL_MODE"):
                durum["dustu"] += 1
                raise sqlite3.OperationalError("database is locked (taklit: WAL ayarlanamadi)")
            return self._c.execute(sql, *a, **k)

        def __getattr__(self, ad):
            return getattr(self._c, ad)

        def __setattr__(self, ad, deger):
            setattr(self._c, ad, deger)

    def _sarmal(self):
        if durum["dustu"] and yeniden_acilmaz:
            durum["yeniden"] += 1
            return None
        c = gercek(self)
        return _Vekil(c) if (c is not None and durum["dustu"] == 0) else c

    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_connect_sqlcipher_if_configured", _sarmal)
    return durum


# ─────────────────────────── B-3.10 · WAL hatasında düz bağlantıya düşüş yok ───────────────────────────


def test_KRITIK_WAL_ayarlanamazsa_SIFRELI_tedavi_DB_duz_baglantiya_DUSMEZ_karantina_YOK(tmp_path, monkeypatch):
    """MUTASYON: WAL düşüşünde koşulsuz `_connect_plain_sqlite`i geri koymak → KIRMIZI (doğru anahtarlı geçmiş
    karantinaya gider)."""
    thdb = _tedavi_anahtarli(monkeypatch)
    app = tmp_path / "PEMF_GUI"
    db = thdb.TreatmentHistoryDB(app)
    db.end_session(db.start_session("WalOncesiSeans"))
    db.close_connections()
    del db
    yol = app / "pemf_treatment_history.db"
    assert yol.read_bytes()[:16] != _SQLITE_BASLIK, "ön koşul: şifreli kurulum"

    durum = _wal_bir_kez_dusur(monkeypatch, thdb)
    t = thdb.TreatmentHistoryDB(app)
    try:
        assert durum["dustu"] == 1, "ön koşul: WAL pragması düşürülmeli"
        assert t.at_rest_encrypted is True
        assert len(t.get_session_history(limit=10)) == 1, "WAL düşüşünden sonra geçmiş OKUNAMIYOR"
    finally:
        t.close_connections()
    assert _karantina(app) == [], f"DOĞRU anahtarla açılmış geçmiş KARANTİNAYA alındı: {_karantina(app)}"
    assert yol.read_bytes()[:16] != _SQLITE_BASLIK


def test_KRITIK_ilk_kurulumda_WAL_ayarlanamazsa_DB_DUZ_METIN_kurulmaz(tmp_path, monkeypatch):
    """İlk kurulumda (dosya yok) WAL düşünce şema ve PII düz-metin yazılıyordu, `at_rest_encrypted` True kalıyordu."""
    thdb = _tedavi_anahtarli(monkeypatch)
    app = tmp_path / "PEMF_GUI"
    durum = _wal_bir_kez_dusur(monkeypatch, thdb)
    t = thdb.TreatmentHistoryDB(app)
    try:
        assert durum["dustu"] == 1, "ön koşul: WAL pragması düşürülmeli"
        t.end_session(t.start_session("IlkKurulum", patient_name="Boncuk-D246"))
        enc = t.at_rest_encrypted
    finally:
        t.close_connections()
    bas = (app / "pemf_treatment_history.db").read_bytes()
    assert bas[:16] != _SQLITE_BASLIK, "ilk kurulumda WAL düşünce tedavi DB'si DÜZ-METİN kuruldu"
    assert b"Boncuk-D246" not in bas, "hasta adı diskte DÜZ-METİN"
    assert enc is True


def test_KRITIK_WAL_sonrasi_sifreli_baglanti_ACILAMAZSA_fail_closed_DUZ_METIN_yok(tmp_path, monkeypatch):
    """WAL düştükten sonra şifreli bağlantı YENİDEN açılamazsa (anahtar o arada açmaz oldu) düz-metne düşülmez:
    kurucu hata verir, diskte düz-metin DB oluşmaz. MUTASYON: o dalda `_connect_plain_sqlite`e düşmek → KIRMIZI."""
    thdb = _tedavi_anahtarli(monkeypatch)
    app = tmp_path / "PEMF_GUI"
    durum = _wal_bir_kez_dusur(monkeypatch, thdb, yeniden_acilmaz=True)
    with pytest.raises(RuntimeError):
        thdb.TreatmentHistoryDB(app)
    assert durum["dustu"] == 1 and durum["yeniden"] >= 1, f"ön koşul: {durum}"
    yol = app / "pemf_treatment_history.db"
    assert not (yol.exists() and yol.read_bytes()[:16] == _SQLITE_BASLIK), (
        "şifreli bağlantı yeniden açılamayınca DÜZ-METİN DB kuruldu"
    )
    assert _karantina(app) == []


def test_KARSIT_sifresiz_kurulumda_WAL_dususu_DELETE_kipine_gecer(tmp_path, monkeypatch):
    """Şifreleme KAPALI kurulumda eski davranış korunur: WAL ayarlanamazsa düz bağlantı DELETE kipiyle sürer."""
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    gercek = thdb.TreatmentHistoryDB._connect_plain_sqlite
    durum = {"dustu": 0}

    class _Vekil:
        def __init__(self, c):
            object.__setattr__(self, "_c", c)

        def execute(self, sql, *a, **k):
            if durum["dustu"] == 0 and str(sql).strip().upper().startswith("PRAGMA JOURNAL_MODE"):
                durum["dustu"] += 1
                raise sqlite3.OperationalError("database is locked (taklit)")
            return self._c.execute(sql, *a, **k)

        def __getattr__(self, ad):
            return getattr(self._c, ad)

        def __setattr__(self, ad, deger):
            setattr(self._c, ad, deger)

    def _sarmal(self):
        c = gercek(self)
        return _Vekil(c) if durum["dustu"] == 0 else c

    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_connect_plain_sqlite", _sarmal)
    app = tmp_path / "PEMF_GUI"
    t = thdb.TreatmentHistoryDB(app)
    try:
        assert durum["dustu"] == 1
        t.end_session(t.start_session("Sifresiz"))
        with t._get_connection() as c:
            assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"
    finally:
        t.close_connections()
    assert _karantina(app) == []


# ─────────────────────────── B-3.48 · binding yokken karantina yok ───────────────────────────


def test_KRITIK_binding_YOKKEN_sifreli_hasta_DB_KARANTINAYA_alinmaz_fail_closed(baglayici, tmp_path, monkeypatch):
    """Anahtar var, sqlcipher3 binding YOK, bayrak 0: düz bağlantı şifreli dosyayı açamaz — bu UYUŞMAZLIK değildir.
    MUTASYON: karar koşulunu yeniden `self._cipher_key`e döndürmek → KIRMIZI."""
    from database import patient_database as pdb

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    yol = app / "patients.db"
    _sifreli_db_kur(baglayici, yol, K)
    once = _ozet(yol)
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "0")
    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: K)

    with pytest.raises(RuntimeError):
        pdb.PatientDatabase(str(yol))
    assert _karantina(app) == [], f"binding YOKKEN şifreli hasta DB'si karantinaya alındı: {_karantina(app)}"
    assert _ozet(yol) == once, "şifreli hasta DB'sine DOKUNULDU (yerine düz-metin DB kuruldu?)"


# ─────────────────────────── B-3.53 · kısmi karantina geri alınır ───────────────────────────


def _wal_ile_kur(baglayici, app: Path) -> Path:
    yol = app / "pemf_treatment_history.db"
    _sifreli_db_kur(baglayici, yol, K)
    (app / "pemf_treatment_history.db-wal").write_bytes(b"WAL-CERCEVELERI " * 64)
    return yol


def _tasima_dusur(monkeypatch, dusen, kopya_birakir) -> None:
    """Kilitli dosya: Windows'ta `shutil.move`un yeniden adlandırması düşer, `copy2` geri dönüşü hedefe KOPYA yazar,
    kaynağın silinmesi düşer (SQLite tutamağı FILE_SHARE_DELETE vermez) — hedefte yarım/tam kopya kalır."""
    import shutil
    import time

    gercek = shutil.move
    kopya = shutil.copy2

    def _move(src, dst, *a, **k):
        if dusen(str(src), str(dst)):
            if kopya_birakir(str(src), str(dst)):
                kopya(src, dst)
            raise PermissionError(32, "Dosya baska bir islem tarafindan kullaniliyor (taklit)")
        return gercek(src, dst, *a, **k)

    monkeypatch.setattr(shutil, "move", _move)
    monkeypatch.setattr(time, "sleep", lambda s: None)  # 24 x 0,25 sn bütçeyi testte bekletme


def test_KRITIK_kismi_karantina_GERI_ALINIR_ana_dosya_YERINDE(baglayici, tmp_path, monkeypatch, caplog):
    """Ana dosya karantinaya taşındıktan sonra `-wal` taşınamazsa ana dosya GERİ konur (WAL'i ondan ayırmak sonraki
    açılışta BOŞ DB kurdururdu). `-wal`in yarım kopyası SİLİNMEZ, adıyla loglanır (özgünü yerinde).
    MUTASYON: geri alma dalını silmek → KIRMIZI."""
    from database import sqlcipher_util as su

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    yol = _wal_ile_kur(baglayici, app)
    wal = app / "pemf_treatment_history.db-wal"
    once = (_ozet(yol), _ozet(wal))
    _tasima_dusur(monkeypatch, lambda s, d: s.endswith("-wal"), lambda s, d: True)

    with caplog.at_level(logging.WARNING):
        assert su.karantinaya_al(yol, logging.getLogger("d246")) is None
    assert yol.exists() and _ozet(yol) == once[0], "kısmi karantinadan sonra ana DB YERİNDE DEĞİL"
    assert _ozet(wal) == once[1], "özgün -wal değişti"
    kalan = _karantina(app)
    assert all(ad.startswith("pemf_treatment_history.db-wal.") for ad in kalan), (
        f"ana DB karantinada kaldı (geri alınmadı): {kalan}"
    )
    assert "GERI ALINDI" in caplog.text, f"kısmi karantinanın geri alındığı günlükte YOK:\n{caplog.text[-800:]}"
    for ad in kalan:
        assert _ozet(app / ad) == once[1] and ad in caplog.text, f"yarım kopya {ad} adıyla loglanmadı"


def test_KRITIK_kismi_karantina_geri_ALINAMAZSA_kurtarma_yonergesi_LOGLANIR(baglayici, tmp_path, monkeypatch, caplog):
    """Geri taşıma da düşerse operatöre hangi dosyanın nerede olduğu ve ne yapılacağı söylenir."""
    from database import sqlcipher_util as su

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    yol = _wal_ile_kur(baglayici, app)
    _tasima_dusur(monkeypatch, lambda s, d: s.endswith("-wal") or d == str(yol), lambda s, d: s.endswith("-wal"))

    with caplog.at_level(logging.WARNING):
        assert su.karantinaya_al(yol, logging.getLogger("d246")) is None
    ana = [ad for ad in _karantina(app) if ad.startswith("pemf_treatment_history.db.")]
    assert ana, "kurgu: ana dosya karantinada kalmalıydı (geri taşıma düşürüldü)"
    assert "ELLE KURTARMA" in caplog.text and ana[0] in caplog.text and str(yol) in caplog.text, (
        f"kurtarma yönergesi (karantina adı + özgün yol) günlükte YOK:\n{caplog.text[-1200:]}"
    )


def test_KARSIT_tum_dosyalar_tasinirsa_karantina_ESKISI_GIBI(baglayici, tmp_path, monkeypatch):
    from database import sqlcipher_util as su

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    yol = _wal_ile_kur(baglayici, app)
    hedef = su.karantinaya_al(yol, logging.getLogger("d246"))
    assert hedef and Path(hedef).exists() and not yol.exists()
    assert len(_karantina(app)) == 2, _karantina(app)  # ana + -wal
