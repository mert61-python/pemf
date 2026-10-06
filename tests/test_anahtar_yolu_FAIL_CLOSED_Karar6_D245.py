# -*- coding: utf-8 -*-
"""D2.45 (B-3.5 · B-3.14 · B-3.51 · Karar 6 · Y9) — ANAHTAR YOLU FAIL-CLOSED.

Sır okunamaz ya da yazılamazsa eski yola düşülmez, YENİ ANAHTAR ÜRETİLMEZ, legacy adayla karantina kararı
verilmez; üretilen anahtar önbelleğe ancak diske yazıldıktan sonra girer; sebep loglanır. Fail-closed süreç
ÖLÜMÜ değildir: DB'si açılamayan backend DB'siz kısıtlı kipte açılır (Y9 — uçtan uca kol
`test_acilis_DB_acilamasa_ACIL_DURDUR_yasar.py` "sir_cozulemez").

ÖLÇÜLEN KUSURLAR (DENETIM-03):
  B-3.5  `get_secret` üretilen anahtarı `_save`'den ÖNCE önbellek dokümanına yazıyordu. İlk `_save` bir kez düşünce
         `get_sqlcipher_key` eski yolda İKİNCİ bir anahtar üretiyor, göç ise önbellekteki (diske hiç yazılmamış)
         anahtarla yapılıyordu → karantina → yeniden başlatmada 0 hasta.
  B-3.14 Tedavi DB'si `get_sqlcipher_key`'in bilerek yükselttiği RuntimeError'u yutup legacy adaya düşüyordu; legacy
         farklıysa kurtarılabilir geçmiş karantinaya gidiyor, yerine bayat anahtarla BOŞ DB kuruluyordu.
  B-3.51 Erişilemeyen sır dizininde `get_secret` PermissionError (RuntimeError değil) veriyor; `get_sqlcipher_key` eski
         yolda YENİ anahtar üretip keyring'e ve `.sqlcipher_key`e yazıyordu.

Sahte EN ALT katta: `os.replace` (sır dosyasının kalıcılaştırılması), `Path.exists` (kilitli sır dizini), makinenin
çözemediği sır blobu (DPAPI/MKEY); ürün zinciri (SecretsManager → get_sqlcipher_key → DB kurucuları) gerçek.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

import pytest
import sahte_sqlcipher

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

K_DOGRU = "D245-K1-dogru-anahtar"
K_BAYAT = "D245-K0-bayat-anahtar"


@pytest.fixture(params=sahte_sqlcipher.BAGLAYICILAR)
def baglayici(request, monkeypatch):
    return sahte_sqlcipher.baglayici_kur(request.param, monkeypatch)


@pytest.fixture
def sm(monkeypatch):
    """İzole veri kökünde (conftest `_gercek_kurulumu_koru`) temiz SecretsManager; ACL kilidi kaydedilir, uygulanmaz
    (eski kodun ürettiği anahtar dosyası tmp'de SYSTEM'e kilitlenip artık bırakmasın)."""
    from utils import file_acl
    from utils import secrets_manager as _sm

    monkeypatch.setattr(file_acl, "lock_down_file", lambda *a, **k: True)
    monkeypatch.delenv("PEMF_SQLCIPHER_KEY", raising=False)
    _sm._cache = None
    yield _sm
    _sm._cache = None


def _ozet(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _kalicilastirmayi_bir_kez_dusur(monkeypatch, sir: Path, kosul) -> dict:
    """Sır dosyasının `os.replace`'i, `kosul(yeni_dokuman)` doğru olan İLK yazımda bir kez PermissionError verir
    (sahada görülen: AV/ACL). Diğer her `os.replace` gerçek."""
    gercek = os.replace
    durum = {"dustu": 0}
    hedef = os.path.normcase(os.path.abspath(str(sir)))

    def _replace(src, dst, *a, **k):
        if durum["dustu"] == 0 and os.path.normcase(os.path.abspath(str(dst))) == hedef:
            if kosul(json.loads(Path(src).read_text(encoding="utf-8"))):
                durum["dustu"] += 1
                raise PermissionError(13, "Erisim engellendi (taklit: AV/ACL sir dosyasini tuttu)")
        return gercek(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", _replace)
    return durum


def _sqlcipher_anahtari_var(doc: dict) -> bool:
    return bool(str((doc.get("auto") or {}).get("sqlcipher_key") or "").strip())


def _cozulemeyen_sir_yaz(sm) -> str:
    """Bu makinenin ÇÖZEMEYECEĞİ, saklanmış bir sqlcipher_key (makine değişimi / Windows yeniden kurulumu)."""
    onek = sm._DPAPI_PREFIX if os.name == "nt" else sm._MKEY_PREFIX
    blob = onek + base64.b64encode(b"D245 baska makinenin blobu " * 4).decode("ascii")
    p = sm.secrets_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"_version": 1, "auto": {"sqlcipher_key": blob}, "operator": {}, "embedded": {}}),
        encoding="utf-8",
    )
    sm._cache = None
    return blob


def _sifreli_db_kur(mod, yol: Path, anahtar: str) -> None:
    """`kayit` tablosunda 1 satırlı ŞİFRELİ DB (gerçek sqlcipher3 ya da sahte bağlayıcı — göçün kullandığı yol)."""
    kaynak = yol.with_name(yol.name + ".kaynak")
    c = sqlite3.connect(str(kaynak))
    c.execute("CREATE TABLE kayit (ad TEXT)")
    c.execute("INSERT INTO kayit VALUES ('KurtarilabilirGecmis')")
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
    assert yol.read_bytes()[:16] != b"SQLite format 3\x00", "ön koşul: DB şifreli kurulmalı"


def _karantina(app: Path) -> list:
    return sorted(p.name for p in app.glob("*.acilamadi-*"))


def _baglantiyi_kapat(db) -> None:
    conn = getattr(getattr(db, "_local", None), "conn", None)
    if conn is not None:
        conn.close()
        db._local.conn = None


# ─────────────────────────── B-3.5 · SecretsManager: önce disk, sonra önbellek ───────────────────────────


def test_KRITIK_ilk_anahtar_DISKE_yazilamazsa_ONBELLEGE_girmez_yeniden_baslatmada_AYNI_anahtar(sm, monkeypatch):
    """MUTASYON: `get_secret`'te değeri `_save`'den ÖNCE önbellek dokümanına yazmak → KIRMIZI (süreçte kullanılan
    anahtar diskte YOK; yeniden başlatmada başka anahtar / boş)."""
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    durum = _kalicilastirmayi_bir_kez_dusur(monkeypatch, sm.secrets_path(), _sqlcipher_anahtari_var)

    with pytest.raises(OSError):
        sm.get_secret("sqlcipher_key", generate=True)
    assert durum["dustu"] == 1, "ön koşul: ilk kalıcılaştırma düşürülmeli"
    kullanilan = sm.get_secret("sqlcipher_key", generate=True)
    sm._cache = None  # yeniden başlatma
    diskteki = sm.get_secret("sqlcipher_key", generate=False)
    assert kullanilan and diskteki == kullanilan, (
        "süreçte kullanılan anahtar DİSKTE YOK — bununla şifrelenen DB yeniden başlatmada AÇILAMAZ (B-3.5)"
    )


def test_KRITIK_set_secret_DISKE_yazilamazsa_ONBELLEK_eski_degeri_KORUR(sm, monkeypatch):
    """`set_secret` aynı sınıf: yazım düştüyse süreç de, yeniden başlatma da ESKİ değeri görmeli."""
    monkeypatch.delenv("PEMF_TUNNEL_HOSTNAME", raising=False)
    sm.set_secret("tunnel_hostname", "eski.ornek")
    _kalicilastirmayi_bir_kez_dusur(
        monkeypatch, sm.secrets_path(), lambda d: (d.get("operator") or {}).get("tunnel_hostname") == "yeni.ornek"
    )
    with pytest.raises(OSError):
        sm.set_secret("tunnel_hostname", "yeni.ornek")
    assert sm.get_secret("tunnel_hostname") == "eski.ornek", "diske yazılamayan değer süreçte GEÇERLİ sayıldı"
    sm._cache = None
    assert sm.get_secret("tunnel_hostname") == "eski.ornek"


# ─────────────────────────── B-3.51 · get_sqlcipher_key: eski yol yok, yeni anahtar yok ───────────────────────────


def test_KRITIK_sir_dizini_OKUNAMAZSA_yeni_anahtar_URETILMEZ_sebep_LOGLANIR(sm, tmp_path, monkeypatch, caplog):
    """MUTASYON: `get_sqlcipher_key`'e `except Exception → eski yol` dalını geri koymak → KIRMIZI (yeni anahtar
    keyring'e ve `.sqlcipher_key`e yazılır)."""
    from database import sqlcipher_util as su

    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    sir = os.path.normcase(os.path.abspath(str(sm.secrets_path())))
    gercek_exists = Path.exists

    def _exists(self, *a, **k):
        if os.path.normcase(os.path.abspath(str(self))) == sir:
            raise PermissionError(13, "Erisim engellendi (taklit: veri koku baska Windows hesabina kilitli)", str(self))
        return gercek_exists(self, *a, **k)

    monkeypatch.setattr(Path, "exists", _exists)
    yazilan = []

    class _Kasa:
        def get_password(self, *a, **k):
            return None

        def set_password(self, *a, **k):
            yazilan.append(a[:2])

    monkeypatch.setattr(su, "keyring", _Kasa(), raising=False)
    app = tmp_path / "veri"
    app.mkdir()

    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError):
        su.get_sqlcipher_key(app, logging.getLogger("d245"))

    assert not (app / ".sqlcipher_key").exists(), "sır okunamazken YENİ anahtar dosyası yazıldı (Karar 6 ihlali)"
    assert yazilan == [], f"sır okunamazken YENİ anahtar kimlik kasasına yazıldı: {yazilan}"
    assert "Yeni SQLCipher anahtari uretildi" not in caplog.text
    assert re.search(r"OKUNAMADI", caplog.text) and "PermissionError" in caplog.text, (
        f"fail-closed sebebi günlükte YOK:\n{caplog.text[-1500:]}"
    )


# ─────────────────────────── B-3.14 · tedavi DB: yutma yok, legacy adayla karantina yok ───────────────────────────


@pytest.mark.parametrize("legacy", ["farkli", "dogru"])
def test_KRITIK_birincil_anahtar_COZULEMEZSE_tedavi_DB_legacy_yola_DUSMEZ_karantina_YOK(
    baglayici, sm, legacy, monkeypatch, caplog
):
    """Sır saklanmış ama bu makinede ÇÖZÜLEMİYOR (RuntimeError, brick koruması). Legacy kaynakta (.sqlcipher_key)
    `farkli` anahtar varken eskiden kurtarılabilir geçmiş KARANTİNAYA gidiyordu (ölçüldü, DENETIM-03 B-3.14).
    `dogru` kolu Karar 6'nın bilinçli sonucunu ölçer (plan "uyandırır"): sır çözülemiyorsa legacy anahtar DB'yi açsa
    bile ona düşülmez — DB açılmaz, dosya YERİNDE (backend DB'siz kısıtlı kipte açılır, Y9).
    MUTASYON: `_get_sqlcipher_key`'e `except Exception → legacy` dalını geri koymak → KIRMIZI."""
    from database import patient_database as pdb
    from database import treatment_history_db as thdb

    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    app = sm._data_dir()
    db = app / "pemf_treatment_history.db"
    _sifreli_db_kur(baglayici, db, K_DOGRU)
    (app / ".sqlcipher_key").write_text(K_BAYAT if legacy == "farkli" else K_DOGRU, encoding="utf-8")
    blob = _cozulemeyen_sir_yaz(sm)
    once = _ozet(db)

    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError):
        thdb.TreatmentHistoryDB(app)

    assert _karantina(app) == [], f"birincil anahtar OKUNAMAZKEN tedavi geçmişi karantinaya alındı: {_karantina(app)}"
    assert db.exists() and _ozet(db) == once, "tedavi DB'sine DOKUNULDU"
    assert "legacy yola dusuluyor" not in caplog.text, "birincil anahtar hatası yutulup legacy yola düşüldü"
    sir = json.loads(sm.secrets_path().read_text(encoding="utf-8"))
    assert sir["auto"]["sqlcipher_key"] == blob, "çözülemeyen sır EZİLDİ (yeni anahtar üretildi)"
    # İkiz: hasta DB'si aynı koşulda zaten duruyordu — karşılaştırma için.
    with pytest.raises(RuntimeError):
        pdb.PatientDatabase(str(app / "patients.db"))
    assert _karantina(app) == []


def test_KRITIK_birincil_BOSKEN_legacy_aday_tek_basina_KARANTINA_karari_VEREMEZ(baglayici, tmp_path, monkeypatch):
    """Karantina yalnız BİRİNCİL anahtarın gerçek uyuşmazlığında. Birincil boş, legacy aday da DB'yi açmıyorsa
    (D2.04 ile aynı ilke: anahtar YOKKEN şifreli DB karantinaya alınmaz) DB açılmaz ama dosya YERİNDE kalır.
    MUTASYON: uyuşmazlık kararını yeniden SON adayın hatasından vermek → KIRMIZI."""
    from database import treatment_history_db as thdb

    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "0")
    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    db = app / "pemf_treatment_history.db"
    _sifreli_db_kur(baglayici, db, K_DOGRU)
    once = _ozet(db)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key", lambda self: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: K_BAYAT)

    with pytest.raises(Exception):
        thdb.TreatmentHistoryDB(app)
    assert _karantina(app) == [], f"YALNIZ legacy adayın uyuşmazlığıyla karantina kararı verildi: {_karantina(app)}"
    assert _ozet(db) == once


def test_KARSIT_birincil_NORMAL_donerken_D3_legacy_kurtarmasi_SURER(sm, monkeypatch, caplog):
    """D-3 (anahtar ayrışması kurtarması) korunur: birincil anahtar HATASIZ döner ama DB'yi açmaz, legacy açar →
    tedavi DB'si legacy anahtarla açılır, veri okunur, karantina YOK."""
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    gercek = sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    app = sm._data_dir()
    db = app / "pemf_treatment_history.db"
    _sifreli_db_kur(gercek, db, K_DOGRU)
    (app / ".sqlcipher_key").write_text(K_DOGRU, encoding="utf-8")
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: K_BAYAT)

    with caplog.at_level(logging.WARNING):
        t = thdb.TreatmentHistoryDB(app)
    try:
        with t._get_connection() as c:
            assert c.execute("SELECT ad FROM kayit").fetchone()[0] == "KurtarilabilirGecmis"
    finally:
        t.close_connections()
    assert "LEGACY anahtarla acildi" in caplog.text
    assert _karantina(app) == []


# ─────────────────────────── B-3.5 · uçtan uca: gerçek hasta DB'si ───────────────────────────


def test_KRITIK_ilk_anahtar_DISKE_yazilamazsa_hasta_DB_DOKUNULMAZ_ikinci_acilista_2_hasta(sm, monkeypatch, caplog):
    """Plan kapısı (1): 2 hastalı düz-metin DB; şifreleme açılınca ilk `sqlcipher_key` kalıcılaştırması bir kez
    düşer. Eskiden: aynı süreçte iki anahtar → göç önbellekteki anahtarla, bağlantı eski-yol anahtarıyla →
    karantina → ikinci açılışta (ve yeniden başlatmada) 0 HASTA (ölçüldü). Şimdi: ilk açılış fail-closed (DB'ye
    dokunulmaz, yeni anahtar dosyası yok), ikinci açılış anahtarı DİSKE yazıp göçer → 2 hasta; yeniden başlatmada 2."""
    from database import patient_database as pdb

    sahte_sqlcipher.baglayici_kur("gercek", monkeypatch)
    app = sm._data_dir()
    yol = app / "patients.db"
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    h = pdb.PatientDatabase(str(yol))
    assert not h.at_rest_encrypted, "ön koşul: başlangıçta düz-metin kurulum"
    for ad in ("Boncuk", "Pamuk"):
        h.add_patient({"name": ad, "owner": "D245", "species": "Kedi"})
    _baglantiyi_kapat(h)
    del h

    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    sm._cache = None
    durum = _kalicilastirmayi_bir_kez_dusur(monkeypatch, sm.secrets_path(), _sqlcipher_anahtari_var)

    ilk = "acildi"
    with caplog.at_level(logging.WARNING):
        try:
            _baglantiyi_kapat(pdb.PatientDatabase(str(yol)))
        except RuntimeError:
            ilk = "fail-closed"
    assert durum["dustu"] == 1, "ön koşul: ilk anahtar kalıcılaştırması düşürülmeli"
    ilk_karantina = _karantina(app)
    ilk_anahtar_dosyasi = (app / ".sqlcipher_key").exists()

    ikinci = pdb.PatientDatabase(str(yol))
    ikinci_sayi = len(ikinci.get_all_patients())
    _baglantiyi_kapat(ikinci)
    del ikinci
    sm._cache = None  # yeniden başlatma
    ucuncu = pdb.PatientDatabase(str(yol))
    ucuncu_sayi = len(ucuncu.get_all_patients())
    _baglantiyi_kapat(ucuncu)

    assert ikinci_sayi == 2, f"ikinci açılışta {ikinci_sayi} hasta (2 beklenirdi) — B-3.5"
    assert ucuncu_sayi == 2, f"yeniden başlatmada {ucuncu_sayi} hasta — kullanılan anahtar diske yazılmamış"
    assert ilk == "fail-closed", "anahtar diske yazılamadığı halde ilk açılış BAŞKA bir anahtarla sürdü (eski yol)"
    assert ilk_karantina == [] and _karantina(app) == [], f"karantina: {ilk_karantina} / {_karantina(app)}"
    assert not ilk_anahtar_dosyasi, "eski yol YENİ anahtar dosyası (.sqlcipher_key) yazdı"
    assert "Yeni SQLCipher anahtari uretildi" not in caplog.text


# ─────────────────────────── B-3.51 · ölüm noktası: günlük dizini yazılamazsa ───────────────────────────


def test_KRITIK_gunluk_dizini_YAZILAMAZSA_backend_OLMEZ_sebep_YEDEK_gunlukte(tmp_path, monkeypatch, caplog):
    """Veri kökü başka bir Windows hesabına kilitliyse (ya da disk salt-okursa) `_configure_logging` günlük dizinini
    oluşturamıyor ve süreç crash handler KURULMADAN, hiçbir günlüğe yazmadan ölüyordu (DENETIM-03 B-3.51: ikinci
    hesabın backend'i hiç açılmıyor, sebep yok). Artık geçici dizine düşer, nedeni yazar, açılış sürer (DB açılamazsa
    DB'siz kısıtlı kip — Y9). Gerçek OS hatası: günlük dizininin yerinde bir DOSYA var.
    MUTASYON: yedeğe düşüşü kaldırmak → KIRMIZI (istisna kaçar); nedeni yazmamak → KIRMIZI."""
    import io
    import tempfile

    import backend_service as bs

    engel = tmp_path / "veri_koku_kilitli"
    engel.write_text("dizin yerine dosya", encoding="utf-8")
    yakalanan: dict = {}
    monkeypatch.setattr(logging, "basicConfig", lambda **k: yakalanan.update(k))
    monkeypatch.setenv("PEMF_LOG_DIR", str(engel / "logs"))
    monkeypatch.delenv("PEMF_LOG_JSON", raising=False)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "gecici"))

    with caplog.at_level(logging.ERROR):
        bs._configure_logging(tmp_path, "INFO")
    handlers = yakalanan.get("handlers") or []
    try:
        dosyalar = [Path(h.baseFilename) for h in handlers if hasattr(h, "baseFilename")]
        assert dosyalar and all(tmp_path / "gecici" in d.parents for d in dosyalar), (
            f"günlük yedek (geçici) dizine düşmedi: {dosyalar}"
        )
    finally:
        for h in handlers:
            h.close()
    assert re.search(r"GUNLUK DIZINI YAZILAMADI", caplog.text) and str(tmp_path / "gecici") in caplog.text, (
        f"günlük dizini neden yazılamadı ve yedek nerede — günlükte YOK:\n{caplog.text[-800:]}"
    )


# ─────────────────────────── sebep loglanır: Supabase kimlik çözümü ───────────────────────────


def test_KRITIK_supabase_kimligi_SIR_okunamazsa_sebep_LOGLANIR(monkeypatch, caplog):
    """`_resolve_supabase_credentials` SecretsManager hatasını SESSİZCE yutuyordu (ortam/varsayılana düşüş görünmez)."""
    import backend_service as bs
    from utils import secrets_manager as _sm

    def _okunamaz(*a, **k):
        raise PermissionError(13, "Erisim engellendi (taklit)")

    monkeypatch.setattr(_sm, "get_secret", _okunamaz)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    with caplog.at_level(logging.WARNING):
        url, anahtar = bs._resolve_supabase_credentials()
    assert url and anahtar, "yedek kimlik çözümü bozuldu"
    assert "PermissionError" in caplog.text and re.search(r"SecretsManager", caplog.text), (
        f"Supabase kimliği sırdan okunamadı ama sebep günlükte YOK:\n{caplog.text[-800:]}"
    )
