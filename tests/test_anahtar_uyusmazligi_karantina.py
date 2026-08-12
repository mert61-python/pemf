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
    monkeypatch.setenv("APPDATA", str(tmp_path / "APPDATA"))
    monkeypatch.setattr(path_utils.platform, "system", lambda: "Windows")

    path_utils._kullanicidan_makineye_gocur(hedef)

    assert not (hedef / "pemf_treatment_history.db").exists(), (
        "ACILAMAYAN sifreli DB hedefe KOPYALANDI → cihaz her acilista kirilir ve karantina "
        "bile kurtarmaz (dosya tekrar tekrar kopyalanir)"
    )
    assert (eski / "pemf_treatment_history.db").exists(), "kaynak silinmis — veri kaybi"


def _sir_yaz(kok: Path, anahtar_degeri: str | None) -> Path:
    """Hedef/kaynak kökte `pemf_secrets.json` üret. `None` → sqlcipher_key ALANI YOK."""
    import json

    doc = {"_version": 1, "auto": {"device_id": "111", "pairing_code": "ABC"}}
    if anahtar_degeri is not None:
        doc["auto"]["sqlcipher_key"] = anahtar_degeri
    p = kok / "pemf_secrets.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_KRITIK_ANAHTAR_gocer_ama_CIHAZ_KIMLIGI_gocmez(tmp_path):
    """Şifreli tıbbi kaydın yeni kökte okunabilmesi için at-rest anahtarı taşınmalı —
    ama SADECE o. Cihaz kimliği kopyalanırsa iki kurulum aynı `device_id`yi paylaşır."""
    import json

    from utils import path_utils

    eski = tmp_path / "eski"
    hedef = tmp_path / "hedef"
    eski.mkdir()
    hedef.mkdir()
    _sir_yaz(eski, "ESKI-KOKUN-ANAHTARI")

    assert path_utils._sqlcipher_anahtarini_gocur(eski, hedef) is True

    yeni = json.loads((hedef / "pemf_secrets.json").read_text(encoding="utf-8"))
    assert yeni["auto"]["sqlcipher_key"] == "ESKI-KOKUN-ANAHTARI", "anahtar tasinmadi"
    assert "device_id" not in yeni["auto"], "CIHAZ KIMLIGI tasinmis → iki kurulum ayni device_id"
    assert "pairing_code" not in yeni["auto"], "eslestirme kodu tasinmis"


def test_KRITIK_hedefteki_anahtar_ASLA_EZILMEZ(tmp_path):
    """⚠️ Hedefin kendi verisi kendi anahtarıyla şifreli olabilir. Üzerine yazmak ÇALIŞAN bir
    kurulumu okunamaz hâle getirir — düzeltmeye çalıştığımız hatanın ta kendisi."""
    import json

    from utils import path_utils

    eski = tmp_path / "eski"
    hedef = tmp_path / "hedef"
    eski.mkdir()
    hedef.mkdir()
    _sir_yaz(eski, "GELEN")
    _sir_yaz(hedef, "HEDEFIN-KENDI-ANAHTARI")

    assert path_utils._sqlcipher_anahtarini_gocur(eski, hedef) is False

    kalan = json.loads((hedef / "pemf_secrets.json").read_text(encoding="utf-8"))
    assert kalan["auto"]["sqlcipher_key"] == "HEDEFIN-KENDI-ANAHTARI", (
        "hedefin anahtari EZILDI → calisan kurulumun verisi okunamaz hale gelir"
    )


def test_anahtar_YOKSA_sessizce_gecer(tmp_path):
    from utils import path_utils

    eski = tmp_path / "eski"
    hedef = tmp_path / "hedef"
    eski.mkdir()
    hedef.mkdir()
    assert path_utils._sqlcipher_anahtarini_gocur(eski, hedef) is False  # sır dosyası yok
    _sir_yaz(eski, None)  # dosya var ama alan yok
    assert path_utils._sqlcipher_anahtarini_gocur(eski, hedef) is False


def test_KRITIK_GOC_DUZ_METIN_DByi_KOPYALAR(tmp_path, monkeypatch):
    """Karşı-kanıt: göç TAMAMEN bozulmamalı. Düz-metin DB güvenle taşınır — hedefte şifreleme
    açıksa backend ilk açılışta onu kendi anahtarıyla şifreler. Bu test olmadan yukarıdaki
    test, göçü komple kapatarak da geçerdi ('vardiyalı klinikte boş klinik' regresyonu)."""
    from utils import path_utils

    eski = tmp_path / "APPDATA" / "PEMF_GUI"
    hedef = tmp_path / "ProgramData" / "PEMF_GUI"
    eski.mkdir(parents=True)
    hedef.mkdir(parents=True)

    # Düz-metin SQLite başlığı (şifreli DEĞİL).
    (eski / "pemf_treatment_history.db").write_bytes(b"SQLite format 3\x00" + b"veri" * 32)
    monkeypatch.setenv("APPDATA", str(tmp_path / "APPDATA"))
    monkeypatch.setattr(path_utils.platform, "system", lambda: "Windows")

    path_utils._kullanicidan_makineye_gocur(hedef)

    assert (hedef / "pemf_treatment_history.db").exists(), (
        "duz-metin DB tasinmadi → vardiyali klinikte 'bos klinik' regresyonu"
    )


def test_KRITIK_GOC_SONSUZ_OZYINELEME_yapmaz(tmp_path, monkeypatch):
    """⚠️⚠️ EN KRİTİK DEĞİŞMEZ — bu kusur SAHAYA YAYINLANDI (app 1.9.9 + 1.9.10).

    Göç `get_app_data_directory()` İÇİNDEN çağrılır. İlk yazımım oradan `get_sqlcipher_key()`
    çağırıyordu ve şu döngü kuruluyordu:

        get_app_data_directory → _kullanicidan_makineye_gocur → (kontrol)
          → get_sqlcipher_key → secrets_manager.get_secret → _load → _data_dir
          → get_app_data_directory → ...

    Backend AÇILIŞTA sonsuz özyinelemeye girip belleği tüketiyordu. Geliştirme makinesinde
    commit limitini doldurup Windows'u BSOD'a (0x10E) götürdü; klinikte cihazın hiç
    açılmaması demekti. Yığın izi `faulthandler` ile kanıtlandı.

    Bu test, göç yolunun sır/kripto katmanına GERİ DÖNMESİNİ engeller."""
    from utils import path_utils

    eski = tmp_path / "eski"
    hedef = tmp_path / "hedef"
    eski.mkdir()
    hedef.mkdir()
    kaynak = eski / "pemf_patients.db"
    kaynak.write_bytes(b"SQLite format 3\x00")

    import database.sqlcipher_util as su_mod
    import utils.secrets_manager as sm_mod

    def _patlat(*a, **k):
        raise AssertionError(
            "goc yolu sir/kripto katmanina dokundu → get_app_data_directory'ye geri doner "
            "ve SONSUZ OZYINELEME kurar (backend acilista olur)"
        )

    monkeypatch.setattr(su_mod, "get_sqlcipher_key", _patlat)
    monkeypatch.setattr(sm_mod, "get_secret", _patlat)

    # Hem düz-metin hem şifreli kolun tamamı sır katmanına dokunmadan yürümeli.
    assert path_utils._tasinabilir_mi(kaynak, eski, hedef) is True
    sifreli = eski / "pemf_treatment_history.db"
    sifreli.write_bytes(b"\x00\x01SIFRELI-BAYTLAR")
    assert path_utils._tasinabilir_mi(sifreli, eski, hedef) is False  # anahtar yok → taşıma
    assert path_utils._sqlcipher_anahtarini_gocur(eski, hedef) is False


def test_KRITIK_anahtar_gocunce_SIFRELI_DB_de_tasinir(tmp_path, monkeypatch):
    """Sahibin istediği asıl kazanım: anahtar taşındıktan sonra ŞİFRELİ tıbbi kayıt da
    yeni köke geçer — yani şifreli kurulumlarda "boş klinik" sorunu gerçekten çözülür."""
    from utils import path_utils

    eski = tmp_path / "APPDATA" / "PEMF_GUI"
    hedef = tmp_path / "ProgramData" / "PEMF_GUI"
    eski.mkdir(parents=True)
    hedef.mkdir(parents=True)
    _sir_yaz(eski, "MAKINE-ANAHTARI")
    (eski / "pemf_treatment_history.db").write_bytes(b"\x00\x01SIFRELI-SEANS-KAYDI")

    monkeypatch.setenv("APPDATA", str(tmp_path / "APPDATA"))
    monkeypatch.setattr(path_utils.platform, "system", lambda: "Windows")

    path_utils._kullanicidan_makineye_gocur(hedef)

    assert (hedef / "pemf_treatment_history.db").exists(), (
        "anahtar tasindigi halde sifreli tibbi kayit tasinmadi → 'bos klinik' devam eder"
    )
    assert path_utils._ham_sqlcipher_anahtari(hedef) == "MAKINE-ANAHTARI"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
