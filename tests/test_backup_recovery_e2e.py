# Author: mertaygn, cglrgrkn
"""DENETİM (offsite-backup-no-key-escrow) — UÇTAN UCA FELAKET KURTARMA.

Kilitlenen senaryo, düzeltmenin var oluş sebebinin ta kendisi:

    LattePanda'nın diski/anakartı ölür → klinik yeni donanım alır → NAS'taki yedeği
    yükler → hasta geçmişi OKUNABİLİR Mİ?

Düzeltmeden ÖNCE cevap HAYIR'dı: yedek .db'ler SQLCipher ile şifreli, anahtar ise eski
makinede DPAPI CRYPTPROTECT_LOCAL_MACHINE ile sarılıydı. Bu test gerçek SQLCipher ile
tam turu koşar: yaz → yedekle → off-site kopyala → MAKİNEYİ YOK ET → yalnız (yedek
dizini + kurtarma kodu) ile geri oku.
"""

import shutil

import pytest

from utils import backup_recovery as br

sqlcipher = pytest.importorskip("sqlcipher3.dbapi2", reason="SQLCipher yoksa senaryo anlamsız")

_KEY = "test-sqlcipher-anahtari-0123456789abcdef"


class _SabitAnahtarDB:
    """TreatmentHistoryDB'yi sabit test anahtarıyla kur — makinenin GERÇEK sırlarına dokunma."""

    def __new__(cls, app_data_dir):
        from database.treatment_history_db import TreatmentHistoryDB

        class _DB(TreatmentHistoryDB):
            def _get_sqlcipher_key(self):
                return _KEY

            def _get_sqlcipher_key_legacy(self):
                return ""

        return _DB(app_data_dir)


@pytest.fixture()
def izole_sirlar(monkeypatch):
    """Sır deposu = bellek içi sözlük. Gerçek pemf_secrets.json'a DOKUNULMAZ."""
    from utils import secrets_manager as sm

    store = {"sqlcipher_key": _KEY, "patient_fernet_key": "test-fernet-anahtari"}
    monkeypatch.setattr(sm, "get_secret", lambda k, default="", generate=True: store.get(k, default))
    monkeypatch.setattr(sm, "set_secret", lambda k, v: store.__setitem__(k, v))
    return store


def _bakim_servisi(app_data_dir, db):
    """HeadlessDBMaintenance'ı singleton'a bulaşmadan kur (_run_backup'ın kullandığı alanlar)."""
    from services.headless_db_maintenance import HeadlessDBMaintenance

    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir = app_data_dir
    w.db = db
    w.patient_db = None
    w.backup_retention_keep = 14
    return w


def test_donanim_arizasindan_sonra_yedekler_yeni_makinede_ACILIR(tmp_path, izole_sirlar, monkeypatch):
    app = tmp_path / "PEMF_GUI"
    nas = tmp_path / "NAS_yedek"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(nas))

    # ── 1) Klinik cihazı: şifreli DB'ye hasta seansları yaz ───────────────────
    db = _SabitAnahtarDB(app)
    assert db.at_rest_encrypted, "test kurulumu: DB şifreli olmalı, yoksa senaryo anlamsız"
    for ad in ("Boncuk", "Karamel", "Zeytin"):
        db.start_session("Manuel", patient_name=ad)
    assert len(db.get_session_history(limit=10)) == 3

    # ── 2) Günlük yedek + off-site kopya (gerçek üretim yolu) ─────────────────
    _bakim_servisi(app, db)._run_backup()

    yedekler = sorted(nas.glob("pemf_treatment_history_*.db"))
    assert yedekler, "off-site yedek oluşmadı"
    zarf = nas / br.ENVELOPE_NAME
    assert zarf.exists(), "kurtarma zarfı off-site kopyaya GİRMEDİ → yedek yine açılamaz olurdu"

    # Operatörün kasaya koyduğu kod (cihazda KURTARMA-KODU.txt olarak da yazılı)
    kod = izole_sirlar["backup_recovery_code"]
    assert (app / br.CODE_FILE_NAME).exists()

    # ── 3) Kod NAS'a sızmamalı — sızsaydı zarfın koruması sıfır olurdu ────────
    kod_norm = br.normalize_code(kod).encode()
    for p in nas.rglob("*"):
        if p.is_file():
            assert kod_norm not in p.read_bytes(), f"kurtarma kodu off-site sızdı: {p.name}"

    # ── 4) DONANIM ÖLDÜ: makinedeki her şey yok (sırlar, DB, DPAPI) ──────────
    db.close_connections()
    shutil.rmtree(app)
    izole_sirlar.clear()
    assert not app.exists()

    # ── 5) Yeni makine: elde SADECE NAS dizini + operatörün kodu var ─────────
    anahtarlar = br.open_envelope(kod, zarf.read_bytes())
    assert anahtarlar["sqlcipher_key"] == _KEY

    conn = sqlcipher.connect(str(yedekler[-1]))
    try:
        conn.execute("PRAGMA key='{}'".format(anahtarlar["sqlcipher_key"].replace("'", "''")))
        adlar = {r[0] for r in conn.execute("SELECT patient_name FROM treatment_sessions ORDER BY id")}
    finally:
        conn.close()

    assert adlar == {"Boncuk", "Karamel", "Zeytin"}, "yedek yeni makinede okunamadı → felaket kurtarma HÂLÂ çalışmıyor"


def test_zarfsiz_yedek_yeni_makinede_ACILAMAZ(tmp_path, izole_sirlar, monkeypatch):
    """Kontrol grubu: düzeltmeden ÖNCEKİ durum. Zarf yoksa aynı yedek gerçekten
    açılamıyor — yani yukarıdaki testi geçiren şey zarf, tesadüf değil."""
    app = tmp_path / "PEMF_GUI"
    nas = tmp_path / "NAS_yedek"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(nas))

    db = _SabitAnahtarDB(app)
    db.start_session("Manuel", patient_name="Boncuk")
    _bakim_servisi(app, db)._run_backup()
    db.close_connections()

    yedek = sorted(nas.glob("pemf_treatment_history_*.db"))[-1]
    (nas / br.ENVELOPE_NAME).unlink()  # zarfı yok say = eski davranış
    shutil.rmtree(app)
    izole_sirlar.clear()

    conn = sqlcipher.connect(str(yedek))
    try:
        conn.execute("PRAGMA key='tahmin-edilen-yanlis-anahtar'")
        with pytest.raises(Exception):
            conn.execute("SELECT count(*) FROM treatment_sessions").fetchone()
    finally:
        conn.close()


def test_kurtarma_araci_anahtarlari_yeni_makineye_yazar(tmp_path, izole_sirlar, monkeypatch):
    """tools/kurtarma.py --yaz gerçekten çalışmalı; operatörün elindeki tek arayüz bu."""
    import tools.kurtarma as kurtarma

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    yedek = tmp_path / "backups"
    assert br.refresh_recovery_material(app, [yedek])
    kod = izole_sirlar["backup_recovery_code"]

    izole_sirlar.clear()  # yeni makine: sır deposu boş
    rc = kurtarma.main(["--zarf", str(yedek / br.ENVELOPE_NAME), "--kod", kod, "--yaz"])

    assert rc == 0
    assert izole_sirlar["sqlcipher_key"] == _KEY
    assert izole_sirlar["patient_fernet_key"] == "test-fernet-anahtari"


def test_kurtarma_araci_MEVCUT_anahtarin_uzerine_yazmaz(tmp_path, izole_sirlar):
    """Veri kaybı koruması: üzerine yazmak, o anahtarla şifrelenmiş mevcut hasta
    verisini KALICI olarak açılamaz yapardı."""
    import tools.kurtarma as kurtarma

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    yedek = tmp_path / "backups"
    br.refresh_recovery_material(app, [yedek])
    kod = izole_sirlar["backup_recovery_code"]

    izole_sirlar["sqlcipher_key"] = "BU-MAKINEDE-ZATEN-VAR"
    rc = kurtarma.main(["--zarf", str(yedek / br.ENVELOPE_NAME), "--kod", kod, "--yaz"])

    assert rc == 3, "mevcut anahtarın üzerine yazıldı → mevcut şifreli veri kaybı riski"
    assert izole_sirlar["sqlcipher_key"] == "BU-MAKINEDE-ZATEN-VAR"


def test_kurtarma_araci_yanlis_kodda_hicbir_sey_yazmaz(tmp_path, izole_sirlar):
    import tools.kurtarma as kurtarma

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    yedek = tmp_path / "backups"
    br.refresh_recovery_material(app, [yedek])
    izole_sirlar.clear()

    rc = kurtarma.main(["--zarf", str(yedek / br.ENVELOPE_NAME), "--kod", br.generate_recovery_code(), "--yaz"])
    assert rc == 2
    assert "sqlcipher_key" not in izole_sirlar
