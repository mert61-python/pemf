# Author: mertaygn, cglrgrkn
"""ANAHTAR UYUŞMAZLIĞI → CİHAZ TUĞLALAŞMAMALI (saha arızası 2026-08-11).

NE OLDU. Kullanıcı PEMF'i kaldırıp yeniden kurdu. Hasta/seans veritabanları KVKK gereği
korunur, ama `pemf_secrets.json` yeniden üretilince at-rest anahtarı değişti. SQLCipher
dosyayı çözemeyince `file is not a database` attı; `_init_database` bunu yukarı fırlattı ve
**backend çıkış kodu 1 ile öldü.** Cihaz bir daha hiç açılmadı.

KURAL. Anahtar GİTTİYSE veri zaten KALICI OKUNAMAZ; cihazı çalışmaz tutmak veriyi kurtarmaz,
yalnızca kliniği cihazsız bırakır. Dosya KENARA ALINIR (yeniden adlandırılır, **asla
silinmez**) ve temiz bir DB açılır.

⚠️ SINIR. Karantina YALNIZ "anahtar okunabildi ama uymuyor" hâlinde yapılır. Anahtar hiç
çözülemediyse (geçici DPAPI/keyring hatası) hata yukarı fırlamalı — aksi hâlde geçici bir
arıza KURTARILABİLİR hasta verisini yetim bırakır. Aşağıdaki testler bu sınırı da kilitler.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import sqlcipher_util as su  # noqa: E402

sqlcipher = su.import_sqlcipher()
pytestmark = pytest.mark.skipif(sqlcipher is None, reason="sqlcipher3 binding yok")


def _sifreli_db_yaz(yol: Path, anahtar: str, satir: str = "kayit") -> None:
    """Verilen anahtarla ŞİFRELİ, içinde veri olan gerçek bir SQLCipher DB üret."""
    c = sqlcipher.connect(str(yol))
    c.execute(f"PRAGMA key='{anahtar}'")
    c.execute("CREATE TABLE t (v TEXT)")
    c.execute("INSERT INTO t VALUES (?)", (satir,))
    c.commit()
    c.close()


def test_KRITIK_anahtar_uyusmazligi_TESPIT_edilir(tmp_path):
    """Yanlış anahtarla açış `anahtar_uyusmazligi_mi` ile tanınmalı. Bu ayrım olmadan
    karantina ya hiç çalışmaz ya da HER hatada dosyayı kenara alır."""
    db = tmp_path / "x.db"
    _sifreli_db_yaz(db, "dogru-anahtar")
    with pytest.raises(Exception) as ex:
        su.open_encrypted_conn(db, "yanlis-anahtar", sqlcipher)
    assert su.anahtar_uyusmazligi_mi(ex.value), f"uyusmazlik taninmadi: {ex.value}"


def test_KRITIK_basarisiz_acis_dosyayi_KILITLEMEZ(tmp_path):
    """Yanlış anahtarla açış bağlantıyı SIZDIRMAMALI.

    Windows'ta sızan SQLCipher tutamağı dosyayı kilitler ve karantina `shutil.move`'u
    PermissionError'a düşer → tuğlalaşma koruması tam ihtiyaç anında çalışmaz. (Bu kusur
    gerçekten vardı; yukarıdaki testin geçici dizini temizlenemeyince ortaya çıktı.)"""
    db = tmp_path / "kilit.db"
    _sifreli_db_yaz(db, "dogru")
    for _ in range(3):
        with pytest.raises(Exception):
            su.open_encrypted_conn(db, "yanlis", sqlcipher)
    assert su.karantinaya_al(db, zaman_damgasi="TEST") is not None, (
        "basarisiz acis dosyayi KILITLI birakti → karantina yapilamiyor"
    )


def test_karantina_dosyayi_SILMEZ_kenara_alir(tmp_path):
    """Karantina = yeniden adlandırma. Anahtar sonradan bulunursa geri dönülebilmeli."""
    db = tmp_path / "patients.db"
    _sifreli_db_yaz(db, "k1")
    onceki = db.read_bytes()
    (tmp_path / "patients.db-wal").write_bytes(b"wal")
    (tmp_path / "patients.db-shm").write_bytes(b"shm")

    tasinan = su.karantinaya_al(db, zaman_damgasi="TEST")

    assert tasinan is not None
    assert not db.exists(), "orijinal ad hala duruyor → yeni DB olusturulamaz"
    assert Path(tasinan).exists(), "karantina dosyasi YOK → VERI SILINMIS"
    assert Path(tasinan).read_bytes() == onceki, "icerik degismis"
    # WAL/SHM de taşınmalı: geride kalan -wal YENİ ve boş DB'ye uygulanmaya çalışılır → bozulma.
    assert not (tmp_path / "patients.db-wal").exists(), "-wal geride kaldi → yeni DB bozulabilir"
    assert not (tmp_path / "patients.db-shm").exists(), "-shm geride kaldi"


def test_karantina_dosya_YOKSA_None(tmp_path):
    assert su.karantinaya_al(tmp_path / "olmayan.db") is None


def _patient_db_ac(tmp_path, monkeypatch, anahtar: str):
    """PatientDatabase'i izole bir veri kökünde, verilen at-rest anahtarıyla aç."""
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PEMF_SQLCIPHER_KEY", anahtar)
    for mod in [m for m in list(sys.modules) if m.startswith("database.patient_database")]:
        del sys.modules[mod]
    import database.patient_database as pdb

    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: anahtar)
    return pdb


def test_KRITIK_ESKI_anahtarli_DB_backendi_OLDURMEZ(tmp_path, monkeypatch):
    """SAHA SENARYOSU: diskte eski anahtarla şifreli `patients.db` var, uygulama YENİ anahtarla
    açılıyor. Eskiden burada RuntimeError fırlıyor ve backend çıkış kodu 1 ile ölüyordu."""
    kok = tmp_path / "PEMF_GUI"
    kok.mkdir(parents=True)
    db = kok / "patients.db"
    _sifreli_db_yaz(db, "ESKI-ANAHTAR", "gizli-hasta")

    pdb = _patient_db_ac(tmp_path, monkeypatch, "YENI-ANAHTAR")
    ornek = pdb.PatientDatabase(str(db))  # patlamamalı

    assert ornek is not None
    kalanlar = [p.name for p in kok.iterdir() if p.name.startswith("patients.db.acilamadi-")]
    assert kalanlar, f"eski DB karantinaya ALINMAMIS: {[p.name for p in kok.iterdir()]}"
    assert db.exists(), "temiz DB olusturulmamis"
    # Yeni DB gerçekten YENİ anahtarla açılıyor mu (yani kullanılabilir mi)?
    c = su.open_encrypted_conn(db, "YENI-ANAHTAR", sqlcipher)
    c.close()


def test_KRITIK_karantina_ANAHTAR_YOKKEN_yapilmaz(tmp_path, monkeypatch):
    """Anahtar hiç çözülemediyse (geçici DPAPI/keyring arızası) dosya KENARA ALINMAMALI —
    aksi hâlde geçici bir hata KURTARILABİLİR hasta verisini yetim bırakır."""
    kok = tmp_path / "PEMF_GUI"
    kok.mkdir(parents=True)
    db = kok / "patients.db"
    _sifreli_db_yaz(db, "ESKI-ANAHTAR", "gizli-hasta")

    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    for mod in [m for m in list(sys.modules) if m.startswith("database.patient_database")]:
        del sys.modules[mod]
    import database.patient_database as pdb

    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")  # anahtar ÇÖZÜLEMEDİ

    with pytest.raises(Exception):
        pdb.PatientDatabase(str(db))

    assert db.exists(), "ANAHTARSIZ hatada DB kenara alinmis → kurtarilabilir veri yetim kaldi"
    assert not [p for p in kok.iterdir() if ".acilamadi-" in p.name], "beklenmedik karantina"


def test_KRITIK_TEDAVI_GECMISI_eski_anahtarda_backendi_OLDURMEZ(tmp_path, monkeypatch):
    """SAHADA GERÇEKTEN ÇARPILAN YOL BUYDU (2026-08-11 11:51 günlüğü).

    `treatment_history_db` hasta DB'sinden FARKLI bir hata tipiyle patlar: aday anahtarların
    hiçbiri açmayınca `_create_connection` `RuntimeError("PEMF_ENCRYPT_AT_REST=1 ama SQLCipher
    sağlanamadı...")` fırlatır — `sqlite3.Error` DEĞİL. Yalnız `_DB_ERROR` yakalansaydı bu
    düzeltme sahada HİÇ çalışmazdı; bu test tam olarak onu kilitler."""
    kok = tmp_path / "PEMF_GUI"
    kok.mkdir(parents=True)
    db = kok / "pemf_treatment_history.db"
    _sifreli_db_yaz(db, "ESKI-ANAHTAR", "eski-seans")

    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    for mod in [m for m in list(sys.modules) if m.startswith("database.treatment_history_db")]:
        del sys.modules[mod]
    import database.treatment_history_db as thdb

    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key", lambda self: "YENI-ANAHTAR", raising=False)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "", raising=False)

    ornek = thdb.TreatmentHistoryDB(kok)  # Path bekler; patlamamalı

    assert ornek is not None
    karantina = [p.name for p in kok.iterdir() if ".acilamadi-" in p.name]
    assert karantina, f"eski gecmis DB karantinaya ALINMAMIS: {[p.name for p in kok.iterdir()]}"
    assert db.exists(), "temiz gecmis DB olusturulmamis"


def test_KRITIK_GOC_acilamayan_sifreli_DByi_KOPYALAMAZ(tmp_path, monkeypatch):
    """SONSUZ TUĞLA DÖNGÜSÜ (saha arızası 2026-08-11).

    `_kullanicidan_makineye_gocur`, tıbbi kaydı `%APPDATA%\\PEMF_GUI`den makine-geneli köke
    kopyalar. Ama SQLCipher anahtarı `pemf_secrets.json`da durur ve o dosya (cihaz kimliği
    içerdiği için, haklı olarak) GÖÇMEZ. Hedefin kendi sır dosyası varsa anahtarlar farklıdır →
    kopyalanan DB KALICI OKUNAMAZ → backend açılışta ölür.

    En kötüsü: dosya kenara alınsa bile bir sonraki açılışta `varis.exists()` yine False olur ve
    AYNI bozuk dosya TEKRAR kopyalanır. Karantina hiçbir şey çözmez; cihaz bir daha hiç açılmaz.
    (Bu tam olarak sahada yaşandı ve elle kenara almak da yetmedi.)"""
    from utils import path_utils

    eski = tmp_path / "APPDATA" / "PEMF_GUI"
    hedef = tmp_path / "ProgramData" / "PEMF_GUI"
    eski.mkdir(parents=True)
    hedef.mkdir(parents=True)

    # Eski kökte BAŞKA bir anahtarla şifreli tedavi geçmişi.
    _sifreli_db_yaz(eski / "pemf_treatment_history.db", "ESKI-KOK-ANAHTARI", "eski-seans")
    # Hedef kökün anahtarı FARKLI.
    monkeypatch.setattr(path_utils, "get_sqlcipher_key", lambda *a, **k: "HEDEF-ANAHTARI", raising=False)
    import database.sqlcipher_util as su_mod

    monkeypatch.setattr(su_mod, "get_sqlcipher_key", lambda *a, **k: "HEDEF-ANAHTARI")
    monkeypatch.setenv("APPDATA", str(tmp_path / "APPDATA"))
    monkeypatch.setattr(path_utils.platform, "system", lambda: "Windows")

    path_utils._kullanicidan_makineye_gocur(hedef)

    assert not (hedef / "pemf_treatment_history.db").exists(), (
        "ACILAMAYAN sifreli DB hedefe KOPYALANDI → cihaz her acilista kirilir ve karantina "
        "bile kurtarmaz (dosya tekrar tekrar kopyalanir)"
    )
    assert (eski / "pemf_treatment_history.db").exists(), "kaynak silinmis — veri kaybi"


def test_KRITIK_GOC_hedefte_anahtar_HIC_YOKKEN_kopyalamaz(tmp_path, monkeypatch):
    """Hedef kökte at-rest anahtarı HİÇ çözülemiyorsa şifreli DB kopyalanmamalı — o dosya orada
    asla açılamaz ve yine sonsuz açılış-hatası döngüsü doğar. (Anahtarın 'yanlış' olması ile
    'hiç olmaması' AYNI sonucu verir; ikisi de engellenmeli.)"""
    from utils import path_utils

    eski = tmp_path / "APPDATA" / "PEMF_GUI"
    hedef = tmp_path / "ProgramData" / "PEMF_GUI"
    eski.mkdir(parents=True)
    hedef.mkdir(parents=True)

    _sifreli_db_yaz(eski / "pemf_treatment_history.db", "BIR-ANAHTAR", "seans")
    import database.sqlcipher_util as su_mod

    monkeypatch.setattr(su_mod, "get_sqlcipher_key", lambda *a, **k: "")  # hedefte anahtar YOK
    monkeypatch.setenv("APPDATA", str(tmp_path / "APPDATA"))
    monkeypatch.setattr(path_utils.platform, "system", lambda: "Windows")

    path_utils._kullanicidan_makineye_gocur(hedef)

    assert not (hedef / "pemf_treatment_history.db").exists(), (
        "hedefte anahtar YOKKEN sifreli DB kopyalandi → orada asla acilamaz, cihaz kirilir"
    )


def test_GOC_acilabilen_DByi_KOPYALAR(tmp_path, monkeypatch):
    """Karşı-kanıt: anahtar UYUYORSA göç çalışmaya devam etmeli. Bu olmadan yukarıdaki test,
    göçü tamamen bozarak da geçebilirdi (vardiyalı klinikte 'boş klinik' regresyonu)."""
    from utils import path_utils

    eski = tmp_path / "APPDATA" / "PEMF_GUI"
    hedef = tmp_path / "ProgramData" / "PEMF_GUI"
    eski.mkdir(parents=True)
    hedef.mkdir(parents=True)

    _sifreli_db_yaz(eski / "pemf_treatment_history.db", "ORTAK-ANAHTAR", "seans")
    import database.sqlcipher_util as su_mod

    monkeypatch.setattr(su_mod, "get_sqlcipher_key", lambda *a, **k: "ORTAK-ANAHTAR")
    monkeypatch.setenv("APPDATA", str(tmp_path / "APPDATA"))
    monkeypatch.setattr(path_utils.platform, "system", lambda: "Windows")

    path_utils._kullanicidan_makineye_gocur(hedef)

    assert (hedef / "pemf_treatment_history.db").exists(), (
        "anahtar UYUYOR ama goc yapilmadi → vardiyali klinikte 'bos klinik' regresyonu"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
