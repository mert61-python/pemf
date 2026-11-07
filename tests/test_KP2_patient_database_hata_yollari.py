# -*- coding: utf-8 -*-
"""KP-2 · apps/backend/database/patient_database.py · sözleşmeler: bağlantı kapatma / geri alma hatası yutulur ve bozuk bağlantı
yeniden kullanılmaz · anahtarsız şifreli dosyada eylem söyleyen ileti, karantina taşınamazsa açılış durur (dosya yerinde) ·
ertelenmiş VACUUM yine düşerse işaret KALIR · denetim noktası hatasında kalıcı işaret · kilit alınamazsa silme yok · boş girdi
erken dönüşleri · içe aktarmada geçersiz tarih varsayılana düşer · şifre çözme katmanı hata verirse yer tutucu / düz metin ·
tekil (`get_patient_database`) yedek kökü ve arka plan yeniden açması · `pemf_gui` doğrudan alınamazsa depo kökü sys.path'e girer.

Sahte EN ALT katta: `sqlite3.connect` (yalnız bu testin DB yolu için), bağlantı sarmalayıcısı (gerçek bağlantıya delege; yalnız
seçilen ifade gerçek SQLite hata biçimiyle düşer), kasa (`utils.secrets_manager.get_secret` — yalnız `sqlcipher_key`, ötekiler
gerçek), `shutil.move` (Windows kilidi: PermissionError), `time.sleep` (bekleme yok), kilit nesnesi. Dosya sistemi yalnız tmp_path.
"""

from __future__ import annotations

import builtins
import importlib.util
import logging
import os
import shutil
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from database import patient_database as pdb
from database import sqlcipher_util as su

YER_TUTUCU = "[okunamayan kayıt]"


# ---------------------------------------------------------------- yardımcılar


def _kasa_anahtari(monkeypatch, anahtar: str) -> None:
    """Kasa EN ALT katta: `get_secret('sqlcipher_key')` → verilen anahtar; başka sırlar gerçek kasaya (test oturumunun izole kökü)."""
    import utils.secrets_manager as sm

    gercek = sm.get_secret

    def _get_secret(ad, *a, **k):
        if ad == "sqlcipher_key":
            return anahtar
        return gercek(ad, *a, **k)

    monkeypatch.setattr(sm, "get_secret", _get_secret)


@pytest.fixture
def duz_db(tmp_path, monkeypatch):
    """At-rest anahtarı YOK (düz SQLite) — bağlantı `sqlite3.connect` ile açılır."""
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    _kasa_anahtari(monkeypatch, "")
    d = pdb.PatientDatabase(str(tmp_path / "patients.db"))
    assert d.at_rest_encrypted is False
    yield d
    d._reset_thread_conn()


class _Sarmal:
    """Gerçek bağlantıyı sarar; `dusur(sql)` True dönen ifade verilen istisnayla düşer. `close`/`rollback` istenirse düşer
    (gerçek bağlantı ÖNCE kapatılır — tutamak sızmaz)."""

    def __init__(self, gercek, dusur=None, hata=None, kapat_duser=False, geri_al_duser=False):
        d = self.__dict__
        d["_c"] = gercek
        d["_dusur"] = dusur or (lambda sql: False)
        d["_hata"] = hata or sqlite3.OperationalError("disk I/O error")
        d["_kapat_duser"] = kapat_duser
        d["_geri_al_duser"] = geri_al_duser
        d["kapat"] = 0
        d["geri_al"] = 0
        d["ifadeler"] = []

    def _denetle(self, sql):
        self.__dict__["ifadeler"].append(str(sql).strip())
        if self._dusur(str(sql).strip().upper()):
            raise self._hata

    def execute(self, sql, *a, **k):
        self._denetle(sql)
        return self._c.execute(sql, *a, **k)

    def cursor(self):
        gercek = self._c.cursor()
        dis = self

        class _Imlec:
            def execute(self, sql, *a, **k):
                dis._denetle(sql)
                return gercek.execute(sql, *a, **k)

            def __getattr__(self, ad):
                return getattr(gercek, ad)

        return _Imlec()

    def rollback(self):
        self.__dict__["geri_al"] += 1
        if self._geri_al_duser:
            raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
        return self._c.rollback()

    def close(self):
        self.__dict__["kapat"] += 1
        self._c.close()
        if self._kapat_duser:
            raise sqlite3.OperationalError("unable to close due to unfinalized statements or unfinished backups")

    def __getattr__(self, ad):
        return getattr(self._c, ad)

    def __setattr__(self, ad, deger):
        setattr(self._c, ad, deger)


def _gercek_baglanti(d):
    with d._get_connection() as c:
        return c


def _hasta(d, ad="Karabas", sahip="Ayse") -> str:
    return d.add_patient({"name": ad, "owner": sahip, "species": "kopek"})


def _ham_satir(yol, sql, *param):
    c = sqlite3.connect(str(yol))
    try:
        return c.execute(sql, param).fetchone()
    finally:
        c.close()


# ---------------------------------------------------------------- bağlantı yaşam döngüsü


def test_PRAGMA_hatasi_ve_kapatma_hatasi_birlikte_PRAGMA_hatasi_YUKSELIR(tmp_path, monkeypatch):
    """PRAGMA 'file is not a database' + close() da düşüyor → kapatma DENENİR, kapatma hatası yutulur; açılış PRAGMA hatasıyla durur."""
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    _kasa_anahtari(monkeypatch, "")
    yol = tmp_path / "patients.db"
    gercek_connect = sqlite3.connect
    sarmallar = []

    def _connect(hedef, *a, **k):
        c = gercek_connect(hedef, *a, **k)
        if Path(str(hedef)) == yol:
            s = _Sarmal(
                c,
                dusur=lambda sql: sql.startswith("PRAGMA JOURNAL_MODE"),
                hata=sqlite3.DatabaseError("file is not a database"),
                kapat_duser=True,
            )
            sarmallar.append(s)
            return s
        return c

    monkeypatch.setattr(sqlite3, "connect", _connect)
    with pytest.raises(RuntimeError, match="Database initialization failed: file is not a database"):
        pdb.PatientDatabase(str(yol))
    assert sarmallar and all(s.kapat == 1 for s in sarmallar), "PRAGMA hatasında bağlantı kapatılmalıydı"


def test_islem_hatasinda_geri_alma_ve_kapatma_duserse_bozuk_baglanti_UNUTULUR(duz_db, caplog):
    """Okuma DB hatası + rollback ve close da düşüyor → sonuç None, iş parçacığı bağlantısı None; SONRAKİ çağrı TAZE bağlantıyla okur."""
    pid = _hasta(duz_db)
    gercek = _gercek_baglanti(duz_db)
    bozuk = _Sarmal(
        gercek, dusur=lambda sql: sql.startswith("SELECT * FROM PATIENTS"), geri_al_duser=True, kapat_duser=True
    )
    duz_db._local.conn = bozuk
    with caplog.at_level(logging.WARNING, logger="PatientDatabase"):
        assert duz_db.get_patient(pid) is None
    assert bozuk.geri_al == 1 and bozuk.kapat == 1
    assert duz_db._local.conn is None, "geri alınamayan bağlantı yeniden kullanılmamalı"
    assert "hasta okuma" in caplog.text
    tekrar = duz_db.get_patient(pid)
    assert tekrar is not None and tekrar["name"] == "Karabas"
    assert duz_db._local.conn is not None and duz_db._local.conn is not bozuk


def test_isci_is_parcaciginda_kapatma_hatasi_YUTULUR_sonuc_doner(duz_db, monkeypatch):
    """Ana olmayan iş parçacığında açılan bağlantının close()'u düşerse → işlem sonucu yine döner, o parçacığın bağlantısı None."""
    _hasta(duz_db, "Tekir")
    _hasta(duz_db, "Pamuk")
    gercek_connect = sqlite3.connect
    sarmallar = []

    def _connect(hedef, *a, **k):
        c = gercek_connect(hedef, *a, **k)
        if Path(str(hedef)) == Path(duz_db.db_file):
            s = _Sarmal(c, kapat_duser=True)
            sarmallar.append(s)
            return s
        return c

    monkeypatch.setattr(sqlite3, "connect", _connect)
    sonuc = {}

    def _is():
        sonuc["sayi"] = duz_db.get_patient_count()
        sonuc["kalan"] = getattr(duz_db._local, "conn", "YOK")

    t = threading.Thread(target=_is)
    t.start()
    t.join(5)
    assert not t.is_alive()
    assert sonuc == {"sayi": 2, "kalan": None}
    assert len(sarmallar) == 1 and sarmallar[0].kapat == 1


def test_reset_thread_conn_kapatma_hatasini_YUTAR_ve_baglantiyi_UNUTUR(duz_db):
    """Karantina öncesi bağlantı bırakma: close() düşse de istisna yok, bağlantı None (sonraki çağrı yenisini açar)."""
    gercek = _gercek_baglanti(duz_db)
    s = _Sarmal(gercek, kapat_duser=True)
    duz_db._local.conn = s
    duz_db._reset_thread_conn()
    assert s.kapat == 1
    assert duz_db._local.conn is None
    assert duz_db.get_patient_count() == 0


# ---------------------------------------------------------------- açılış: anahtarsız şifreli dosya · karantina düşerse


def test_anahtar_YOKKEN_sifreli_gorunen_dosya_EYLEM_iletisi_ve_dokunulmaz(tmp_path, monkeypatch, caplog):
    """Anahtar yok + SQLite başlığı olmayan dosya → 'SIFRELI gorunuyor … SILMEYIN' hatası, RuntimeError, dosya bayt bayt AYNI, karantina YOK."""
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    _kasa_anahtari(monkeypatch, "")
    yol = tmp_path / "patients.db"
    icerik = bytes(range(256)) * 32
    yol.write_bytes(icerik)
    with caplog.at_level(logging.ERROR, logger="PatientDatabase"):
        with pytest.raises(RuntimeError, match="Database initialization failed"):
            pdb.PatientDatabase(str(yol))
    assert "SIFRELI gorunuyor" in caplog.text and "SILMEYIN" in caplog.text and "patients.db" in caplog.text
    assert yol.read_bytes() == icerik
    assert not [p for p in tmp_path.iterdir() if ".acilamadi-" in p.name]


@pytest.mark.skipif(su.import_sqlcipher() is None, reason="sqlcipher3 binding yok")
def test_anahtar_uyusmazliginda_karantina_TASINAMAZSA_acilis_durur_dosya_YERINDE(tmp_path, monkeypatch):
    """Şifreli DB eski anahtarla, kasada yeni anahtar; dosya kilitli (her taşıma PermissionError) → RuntimeError 'karantinaya ALINAMADI',
    özgün dosya bayt bayt AYNI, `.acilamadi-*` kopyası YOK."""
    sc = su.import_sqlcipher()
    yol = tmp_path / "patients.db"
    c = sc.connect(str(yol))
    c.execute("PRAGMA key='ESKI-ANAHTAR'")
    c.execute("CREATE TABLE t (v TEXT)")
    c.execute("INSERT INTO t VALUES ('gizli-hasta')")
    c.commit()
    c.close()
    once = yol.read_bytes()

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    _kasa_anahtari(monkeypatch, "YENI-ANAHTAR")
    denemeler = []

    def _move(src, dst, *a, **k):
        denemeler.append((src, dst))
        raise PermissionError(13, "Dosya baska bir islem tarafindan kullaniliyor", src)

    monkeypatch.setattr(shutil, "move", _move)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="karantinaya ALINAMADI"):
        pdb.PatientDatabase(str(yol))
    assert denemeler, "karantina taşıması denenmeliydi"
    assert all(str(s) == str(yol) for s, _ in denemeler)
    assert yol.read_bytes() == once
    assert not [p for p in tmp_path.iterdir() if ".acilamadi-" in p.name]


@pytest.mark.skipif(su.import_sqlcipher() is None, reason="sqlcipher3 binding yok")
def test_karantina_SONRASI_temiz_DB_acilamazsa_RuntimeError_ve_karantina_dosyasi_DURUR(tmp_path, monkeypatch):
    """Anahtar uyuşmazlığı → dosya `.acilamadi-*` olarak kenara alındı; yerine kurulacak TEMİZ DB sürücüde açılamıyor ('unable to open
    database file') → RuntimeError '(karantina sonrasi)'; kenara alınan dosya özgün baytlarıyla DURUR (silinmez)."""
    sc = su.import_sqlcipher()
    yol = tmp_path / "patients.db"
    c = sc.connect(str(yol))
    c.execute("PRAGMA key='ESKI-ANAHTAR'")
    c.execute("CREATE TABLE t (v TEXT)")
    c.execute("INSERT INTO t VALUES ('gizli-hasta')")
    c.commit()
    c.close()
    once = yol.read_bytes()

    class _Surucu:
        """SQLCipher sürücüsü (EN ALT kat): yalnız YOK olan patients.db'ye (karantina sonrası temiz DB) bağlantı düşer."""

        def connect(self, hedef, *a, **k):
            if Path(str(hedef)) == yol and not yol.exists():
                raise sc.OperationalError("unable to open database file")
            return sc.connect(hedef, *a, **k)

        def __getattr__(self, ad):
            return getattr(sc, ad)

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    _kasa_anahtari(monkeypatch, "YENI-ANAHTAR")
    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: _Surucu())
    with pytest.raises(RuntimeError, match=r"karantina sonrasi\): unable to open database file"):
        pdb.PatientDatabase(str(yol))
    kenarda = [p for p in tmp_path.iterdir() if p.name.startswith("patients.db.acilamadi-")]
    assert len(kenarda) == 1 and kenarda[0].read_bytes() == once
    assert not yol.exists()


def test_arama_parmak_izi_OKUNAMAZSA_dizin_bir_kez_yeniden_kurulur_arama_CALISIR(tmp_path, monkeypatch, caplog):
    """`.patient_search_keyfp` okunamıyor (yerinde dizin var) → parmak izi 'YOK' sayılır, dolu dizin yeniden kurulur, açılış sürer ve
    hasta aranınca bulunur; yazılamayan parmak izi uyarıyla geçer."""
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    _kasa_anahtari(monkeypatch, "")
    yol = tmp_path / "patients.db"
    ilk = pdb.PatientDatabase(str(yol))
    pid = ilk.add_patient({"name": "İhsan", "owner": "Veli"})
    ilk._reset_thread_conn()
    fp = tmp_path / ".patient_search_keyfp"
    fp.unlink()
    fp.mkdir()
    with caplog.at_level(logging.WARNING, logger="PatientDatabase"):
        ikinci = pdb.PatientDatabase(str(yol))
    try:
        assert "parmak izi YOK" in caplog.text
        assert "parmak izi yazilamadi" in caplog.text
        assert [h["id"] for h in ikinci.search_patients("ihsan")] == [pid]
    finally:
        ikinci._reset_thread_conn()


# ---------------------------------------------------------------- VACUUM / denetim noktası


def test_ertelenmis_VACUUM_yine_duserse_False_ve_isaret_KALIR(duz_db, caplog):
    """'VACUUM bekliyor' işareti varken VACUUM 'database or disk is full' ile düşer → False, işaret hâlâ bekliyor."""
    assert duz_db._vacuum_isaretini_yaz("1") is True
    gercek = _gercek_baglanti(duz_db)
    duz_db._local.conn = _Sarmal(
        gercek, dusur=lambda sql: sql.startswith("VACUUM"), hata=sqlite3.OperationalError("database or disk is full")
    )
    try:
        with caplog.at_level(logging.WARNING, logger="PatientDatabase"):
            assert duz_db.bekleyen_vacuum_calistir() is False
        assert "yine yapilamadi" in caplog.text
    finally:
        duz_db._local.conn = gercek
    assert duz_db.vacuum_bekliyor_mu() is True


def test_silme_sonrasi_denetim_noktasi_HATA_verirse_silme_DOGRU_isaret_KONUR(duz_db, caplog):
    """Silme commit edildi ama wal_checkpoint 'database table is locked' ile düştü → delete True, hasta yok, kalıcı VACUUM işareti '1'."""
    pid = _hasta(duz_db)
    assert duz_db.vacuum_bekliyor_mu() is False
    gercek = _gercek_baglanti(duz_db)
    duz_db._local.conn = _Sarmal(
        gercek,
        dusur=lambda sql: sql.startswith("PRAGMA WAL_CHECKPOINT"),
        hata=sqlite3.OperationalError("database table is locked"),
    )
    try:
        with caplog.at_level(logging.WARNING, logger="PatientDatabase"):
            assert duz_db.delete_patient(pid) is True
        assert "hasta silme: silme sonrasi denetim noktasi yapilamadi" in caplog.text
    finally:
        duz_db._local.conn = gercek
    assert duz_db.get_patient(pid) is None
    assert duz_db.vacuum_bekliyor_mu() is True


# ---------------------------------------------------------------- kilit alınamazsa


class _AlinamayanKilit:
    def __init__(self):
        self.istenen = []

    def acquire(self, blocking=True, timeout=-1):
        self.istenen.append(timeout)
        return False

    def release(self):
        raise AssertionError("alinmamis kilit birakildi")


def test_tekil_silme_kilit_10_sn_alinamazsa_False_hasta_DURUR(duz_db, monkeypatch):
    pid = _hasta(duz_db)
    kilit, gercek = _AlinamayanKilit(), duz_db.lock
    duz_db.lock = kilit
    try:
        assert duz_db.delete_patient(pid) is False
    finally:
        duz_db.lock = gercek
    assert kilit.istenen == [10.0]
    assert duz_db.get_patient(pid)["name"] == "Karabas"


def test_toplu_silme_kilit_alinamazsa_0_hastalar_DURUR(duz_db, monkeypatch):
    a, b = _hasta(duz_db, "A"), _hasta(duz_db, "B")
    kilit, gercek = _AlinamayanKilit(), duz_db.lock
    duz_db.lock = kilit
    try:
        assert duz_db.delete_patients_bulk([a, b]) == 0
    finally:
        duz_db.lock = gercek
    assert kilit.istenen == [10.0]
    assert duz_db.get_patient_count() == 2


# ---------------------------------------------------------------- boş / olmayan girdi


def test_olmayan_hastayi_tekil_silme_False_digerleri_DURUR(duz_db):
    pid = _hasta(duz_db)
    assert duz_db.delete_patient(str(uuid.uuid4())) is False
    assert duz_db.get_patient(pid) is not None


def test_toplu_silme_bos_ya_da_yalniz_bosluk_kimlik_0(duz_db):
    _hasta(duz_db)
    assert duz_db.delete_patients_bulk([]) == 0
    assert duz_db.delete_patients_bulk([None, "", "   "]) == 0
    assert duz_db.get_patient_count() == 1


def test_operator_sahipleri_bos_kimlik_listesi_bos_sozluk_DB_ye_GITMEZ(duz_db):
    gercek = _gercek_baglanti(duz_db)
    s = _Sarmal(gercek)
    duz_db._local.conn = s
    try:
        assert duz_db.operator_sahipleri([]) == {}
        assert duz_db.operator_sahipleri([None, "  "]) == {}
    finally:
        duz_db._local.conn = gercek
    assert s.ifadeler == []


def test_touch_last_treatment_bos_kimlik_DB_ye_GITMEZ(duz_db):
    gercek = _gercek_baglanti(duz_db)
    s = _Sarmal(gercek)
    duz_db._local.conn = s
    try:
        assert duz_db.touch_last_treatment("") is None
        assert duz_db.touch_last_treatment(None) is None
    finally:
        duz_db._local.conn = gercek
    assert s.ifadeler == []


def test_anonimlestirilecekler_sure_SIFIR_ya_da_negatif_bos_liste(duz_db):
    """Süre ≤ 0 → aday YOK (eskiden 0 → 1 gün olsaydı tüm eski hastalar aday olurdu)."""
    pid = _hasta(duz_db)
    with duz_db._get_connection() as c:
        c.execute(
            "UPDATE patients SET created_at=? WHERE id=?", ((datetime.now() - timedelta(days=4000)).isoformat(), pid)
        )
        c.commit()
    assert [h["id"] for h in duz_db.anonimlestirilecek_hastalar(1)] == [pid]  # karşıt-kanıt: süre pozitifken aday
    assert duz_db.anonimlestirilecek_hastalar(0) == []
    assert duz_db.anonimlestirilecek_hastalar(-5) == []


def test_bos_arama_terimi_TUM_hastalari_doner(duz_db):
    a, b = _hasta(duz_db, "A"), _hasta(duz_db, "B")
    assert {h["id"] for h in duz_db.search_patients("   ")} == {a, b}
    assert {h["id"] for h in duz_db.search_patients(None)} == {a, b}


def test_yalniz_offset_ile_listeleme_ILK_kayitlari_atlar(duz_db):
    kimlikler = []
    for i in range(3):
        pid = _hasta(duz_db, f"H{i}")
        with duz_db._get_connection() as c:
            c.execute("UPDATE patients SET created_at=? WHERE id=?", (f"2026-01-0{i + 1}T10:00:00", pid))
            c.commit()
        kimlikler.append(pid)
    # created_at DESC: H2, H1, H0 → offset 1 → H1, H0
    assert [h["id"] for h in duz_db.get_all_patients(offset=1)] == [kimlikler[1], kimlikler[0]]


def test_guncellemede_yalniz_operator_epostasi_ya_da_bilinmeyen_alan_False_degismez(duz_db):
    pid = d_id = duz_db.add_patient({"name": "Boncuk", "operator_email": "vet@klinik.test"})
    once = _ham_satir(duz_db.db_file, "SELECT operator_email, updated_at FROM patients WHERE id=?", d_id)
    assert duz_db.update_patient(pid, {"operator_email": "baska@klinik.test", "bilinmeyen": "x"}) is False
    assert _ham_satir(duz_db.db_file, "SELECT operator_email, updated_at FROM patients WHERE id=?", d_id) == once
    assert duz_db.get_patient(pid)["operator_email"] == "vet@klinik.test"


def test_hasta_sayimi_DB_hatasinda_0_ve_SESSIZ_DEGIL(duz_db, caplog):
    _hasta(duz_db)
    gercek = _gercek_baglanti(duz_db)
    duz_db._local.conn = _Sarmal(gercek, dusur=lambda sql: sql.startswith("SELECT COUNT(*)"))
    try:
        with caplog.at_level(logging.WARNING, logger="PatientDatabase"):
            assert duz_db.get_patient_count() == 0
    finally:
        duz_db._local.conn = gercek
    assert "hasta sayimi basarisiz" in caplog.text
    assert duz_db.get_patient_count() == 1


def test_satiri_olmayan_hastanin_arama_dizini_TEMIZLENIR(duz_db):
    """Dizin tazelemesi: hasta satırı yoksa o kimliğin yetim dizin satırları silinir (silinmiş hasta aramada görünmez)."""
    yetim = str(uuid.uuid4())
    with duz_db._get_connection() as c:
        c.execute("PRAGMA foreign_keys=OFF")
        c.execute(
            "INSERT INTO patient_search_index (patient_id, field_name, token_hmac) VALUES (?,?,?)",
            (yetim, "name", "abc"),
        )
        c.commit()
        cur = c.cursor()
        duz_db._refresh_search_index_for_patient(cur, yetim)
        c.commit()
        kalan = c.execute("SELECT COUNT(*) FROM patient_search_index WHERE patient_id=?", (yetim,)).fetchone()[0]
        c.execute("PRAGMA foreign_keys=ON")
    assert kalan == 0


# ---------------------------------------------------------------- alan şifreleme sınırları


def test_None_alan_BOS_yazilir_None_metni_sifrelenmez(duz_db):
    pid = duz_db.add_patient({"name": "Zeytin", "owner": None, "breed": None})
    ham = _ham_satir(duz_db.db_file, "SELECT owner, breed, name FROM patients WHERE id=?", pid)
    assert ham[0] == "" and ham[1] == ""
    assert ham[2].startswith("enc:")
    h = duz_db.get_patient(pid)
    assert h["owner"] == "" and h["breed"] == "" and h["name"] == "Zeytin"


def test_eski_satirda_NULL_alan_BOS_dize_doner(duz_db):
    pid = str(uuid.uuid4())
    with duz_db._get_connection() as c:
        c.execute(
            "INSERT INTO patients (id, name, owner, owner_email, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (pid, "EskiAd", None, None, "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
        )
        c.commit()
    h = duz_db.get_patient(pid)
    assert h["owner"] == "" and h["owner_email"] == "" and h["vet_contact"] == ""
    assert h["name"] == "EskiAd"


def test_enc_onekli_alanda_cozme_katmani_HATA_verirse_YER_TUTUCU(duz_db, monkeypatch):
    """Şifre çözme katmanı istisna atarsa ham şifreli metin KULLANICIYA gitmez → '[okunamayan kayıt]'."""
    pid = _hasta(duz_db, "Minnos")

    def _patlar(*a, **k):
        raise ValueError("Fernet anahtari bozuk")

    monkeypatch.setattr(duz_db.config_manager, "_decrypt_value", _patlar)
    h = duz_db.get_patient(pid)
    assert h["name"] == YER_TUTUCU and h["owner"] == YER_TUTUCU


def test_oneksiz_eski_alanda_cozme_katmani_HATA_verirse_duz_metin_AYNEN(duz_db, monkeypatch):
    """Öneksiz (eski) alan: çözme katmanı istisna atarsa düz-metin değer olduğu gibi; Fernet gövdesi gibi görünen değer yer tutucu."""
    pid = str(uuid.uuid4())
    fernet_gibi = "Z0FBQUFBQm1fYWJjZGVmZ2hpams="  # base64("gAAAAABm_abcdefghijk")
    with duz_db._get_connection() as c:
        c.execute(
            "INSERT INTO patients (id, name, owner, created_at, updated_at) VALUES (?,?,?,?,?)",
            (pid, "Duz Ad", fernet_gibi, "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
        )
        c.commit()

    def _patlar(*a, **k):
        raise ValueError("cozme katmani")

    monkeypatch.setattr(duz_db.config_manager, "_decrypt_value", _patlar)
    h = duz_db.get_patient(pid)
    assert h["name"] == "Duz Ad"
    assert h["owner"] == YER_TUTUCU


def test_ice_aktarmada_GECERSIZ_tarih_varsayilana_duser_gecerli_tarih_KORUNUR(duz_db, caplog):
    pid = str(uuid.uuid4())
    once = datetime.now()
    with caplog.at_level(logging.WARNING, logger="PatientDatabase"):
        duz_db.add_patient(
            {
                "name": "Tasinan",
                "created_at": "31/12/2024",
                "updated_at": "2025-03-04T05:06:07",
                "last_treatment_at": "dun",
            },
            patient_id=pid,
        )
    satir = _ham_satir(duz_db.db_file, "SELECT created_at, updated_at, last_treatment_at FROM patients WHERE id=?", pid)
    olusturma = datetime.fromisoformat(satir[0])
    assert once - timedelta(seconds=5) <= olusturma <= datetime.now() + timedelta(seconds=5)
    assert satir[1] == "2025-03-04T05:06:07"
    assert satir[2] is None
    assert "gecersiz created_at" in caplog.text and "gecersiz last_treatment_at" in caplog.text


# ---------------------------------------------------------------- tekil / arka plan yeniden açması


@pytest.fixture
def tekil_temiz(monkeypatch):
    monkeypatch.setattr(pdb, "_patient_db", None)
    monkeypatch.setattr(pdb, "_acilis_kilidi", {})
    acilan = []
    yield acilan
    for d in acilan:
        d._reset_thread_conn()


def test_veri_koku_cozulemezse_EV_altinda_pemf_gui_kullanilir(tmp_path, monkeypatch, tekil_temiz):
    import utils.path_utils as pu

    def _patlar():
        raise PermissionError(13, "Erisim engellendi")

    monkeypatch.setattr(pu, "get_app_data_directory", _patlar)
    ev = tmp_path / "ev"
    (ev / ".pemf_gui").mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(ev))
    monkeypatch.setenv("HOME", str(ev))
    _kasa_anahtari(monkeypatch, "")
    d = pdb.get_patient_database()
    tekil_temiz.append(d)
    assert Path(d.db_file) == ev / ".pemf_gui" / "patients.db"
    assert (ev / ".pemf_gui" / "patients.db").exists()
    assert pdb.get_patient_database() is d


def test_yeniden_ac_tekil_ZATEN_varsa_onu_doner_kilidi_kaldirir(tmp_path, monkeypatch, tekil_temiz, duz_db):
    monkeypatch.setattr(pdb, "_patient_db", duz_db)
    pdb.acilis_hatasini_kilitle(tmp_path, RuntimeError("x"))
    assert pdb._acilis_kilidi
    assert pdb.acilista_acilamayani_yeniden_ac(tmp_path) is duz_db
    assert pdb._acilis_kilidi == {}


def test_acilista_ACILAMAYAN_DB_arka_planda_acilir_istek_yolu_KILIDI_kalkar(tmp_path, monkeypatch, tekil_temiz):
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    _kasa_anahtari(monkeypatch, "")
    kok = tmp_path / "PEMF_GUI"
    kok.mkdir()
    pdb.acilis_hatasini_kilitle(kok, RuntimeError("anahtar okunamadi"))
    with pytest.raises(RuntimeError, match=r"ACILAMADI \(RuntimeError\)"):
        pdb.get_patient_database(kok)
    d = pdb.acilista_acilamayani_yeniden_ac(kok)
    tekil_temiz.append(d)
    assert Path(d.db_file) == kok / "patients.db"
    assert pdb._acilis_kilidi == {}
    assert pdb.get_patient_database(kok) is d


# ---------------------------------------------------------------- içe aktarma yedek yolu (modül düzeyi)


def test_pemf_gui_dogrudan_ALINAMAZSA_depo_koku_sys_path_basina_eklenir(monkeypatch):
    """Doğrudan betik koşusu (Spyder %runfile): ilk `from pemf_gui.config import get_config` ModuleNotFoundError → depo kökü
    (`kaynak_kokunu_bul`) sys.path'in BAŞINA eklenir ve get_config yine `pemf_gui.config`ten gelir. Kopya modül ayrı adla yüklenir
    (sys.modules'a girmez)."""
    from utils.path_utils import kaynak_kokunu_bul

    import pemf_gui.config as pgc

    kok = str(kaynak_kokunu_bul(pdb.__file__))
    gercek_import = builtins.__import__
    sayac = {"pemf_gui.config": 0}

    def _import(ad, globals=None, locals=None, fromlist=(), level=0):
        if ad == "pemf_gui.config" and level == 0:
            sayac[ad] += 1
            if sayac[ad] == 1:
                raise ModuleNotFoundError("No module named 'pemf_gui'", name="pemf_gui")
        return gercek_import(ad, globals, locals, fromlist, level)

    def _ayni(p):
        try:
            return os.path.normcase(os.path.abspath(p)) == os.path.normcase(os.path.abspath(kok))
        except Exception:
            return False

    monkeypatch.setattr(sys, "path", [p for p in sys.path if not _ayni(p)])
    monkeypatch.setattr(builtins, "__import__", _import)
    spec = importlib.util.spec_from_file_location("kp2_patient_database_kopya", pdb.__file__)
    kopya = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kopya)
    yol_basi = sys.path[0]
    monkeypatch.undo()
    assert "kp2_patient_database_kopya" not in sys.modules
    assert sayac["pemf_gui.config"] == 2
    assert _ayni(yol_basi), f"depo kökü sys.path başına eklenmedi: {yol_basi!r}"
    assert kopya.get_config is pgc.get_config


def test_veri_koku_cozulemez_ve_EV_pemf_gui_YOKSA_dizin_kurulur_DB_acilir(tmp_path, monkeypatch, tekil_temiz):
    """`get_app_data_directory` düştü, yedek kök `~/.pemf_gui` henüz YOK (temiz makine) → dizin kurulur, DB açılır.
    KP-3 A1 · sahip Y245 (03.11): H-1 düzeltildi — KP-2'de `xfail(strict=True)` belge testiydi (4033cafe: mkdir yok → RuntimeError
    'unable to open database file'); artık normal sözleşme testi. Kapsam YALNIZ "kök çözülemedi → yedek kök" yolu; Y200 göç kuralı
    (göç bir dosyayı atlarsa boş DB kurulmaz) `utils/path_utils` göçünde AYNEN. Dizin yalnız sahte EV altında kurulur."""
    import utils.path_utils as pu

    def _patlar():
        raise PermissionError(13, "Erisim engellendi")

    monkeypatch.setattr(pu, "get_app_data_directory", _patlar)
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("USERPROFILE", str(ev))
    monkeypatch.setenv("HOME", str(ev))
    _kasa_anahtari(monkeypatch, "")
    # A-46 atlama kapısı (conftest) xfail raporunun İZİNİ de "atlama nedeni" diye tarar; ürünün şema kurulumu izinde
    # şifreleme sürücüsünün adını geçirdiği için bu belge-xfail süiti çıkış 1 yapıyordu (KP-2 kapanış, 03.11 ölçüldü).
    # Düşüş burada yakalanır ve YALNIZ iletiyle, istisna zinciri olmadan bildirilir — sözleşme aynı.
    try:
        d = pdb.get_patient_database()
    except RuntimeError as e:
        hata = str(e)
    else:
        hata = None
        tekil_temiz.append(d)
    assert hata is None, f"hasta DB açılmadı: {hata}"
    assert (ev / ".pemf_gui" / "patients.db").exists()


def test_KP3_A1_yedek_kok_KURULAMAZSA_eski_davranis_RuntimeError_izin_hatasi_SIZMAZ(tmp_path, monkeypatch, tekil_temiz):
    """KP-3 A1 (Y245): yedek kök `~/.pemf_gui` kurulamazsa (izin / salt-okunur ev) davranış ESKİSİ GİBİ — DB açılışı `RuntimeError` ile düşer
    (çağıranlar bunu bekler: backend DB'siz kısıtlı kip, ACİL DURDUR etkilenmez); `mkdir`in `PermissionError`ı dışarı SIZMAZ ve dizin YOK."""
    import utils.path_utils as pu

    def _patlar():
        raise PermissionError(13, "Erisim engellendi")

    monkeypatch.setattr(pu, "get_app_data_directory", _patlar)
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("USERPROFILE", str(ev))
    monkeypatch.setenv("HOME", str(ev))
    _kasa_anahtari(monkeypatch, "")
    gercek_mkdir = Path.mkdir

    def _mkdir_red(self, *a, **k):
        if self.name == ".pemf_gui":
            raise PermissionError(13, "Erisim engellendi")
        return gercek_mkdir(self, *a, **k)

    monkeypatch.setattr(Path, "mkdir", _mkdir_red)
    try:
        d = pdb.get_patient_database()
    except RuntimeError as e:
        hata = str(e)
    else:
        hata = None
        tekil_temiz.append(d)
    assert hata is not None, "yedek kök kurulamadığı hâlde DB açıldı"
    assert not (ev / ".pemf_gui").exists()
