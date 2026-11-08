# -*- coding: utf-8 -*-
"""KP-3 C · backend'in son kapsanmayan kolları (tam süit @ c83b47e9: %99,88, 31 satır) — her test bir DAVRANIŞ iddiası. ⚠️ Ürün kodu
DEĞİŞMEDİ (yalnız test; şifreleme / veri yolu kolları yalnız ölçülür).

- Kurtarma kodu dosyası yerine KONAMAZSA asıl hata yükselir; geçici dosya silinemese de o hata ASIL hatayı GİZLEMEZ.
- Kurtarma zarfı bir hedefe yazılamazsa (geçici dosyası da silinemez) DİĞER hedefe yine yazılır; sonuç "yazıldı".
- Zarf mührü (parmak izi) yazılamazsa tur yine başarılı; bir SONRAKİ tur mührü (ve zarfı) yeniden yazar — kalıcı "güncel" sanılmaz.
- Doz değişikliği kaydında DB'ye HİÇ ulaşılamazsa sürüş yanıtı yine başarılı, ama "kayda yazıldı" DENMEZ.
- Kart sistematik DUTY reddindeyken ACİL DURDUR mandalı OKUNAMAZSA eylem metni yine üretilir ("Sıfırla" ipucu olmadan; çökme yok).
- Tedavi DB'si (SQLCipher): önbellekteki anahtar açmazsa ve bağlantı KAPATMA da patlarsa önbellek boşaltılıp tam çözümlemeyle
  yeniden denenir; kapatma hatası akışı bozmaz, "anahtar vardı ama açmadı" işareti kurulur (karantina kararının girdisi).
- Tedavi DB'si: WAL ayarlanamaz VE bağlantı kapatma da patlarsa yeni bağlantıyla DELETE kipinde açılır; bağlantı ayarı sırasında
  hata + kapatma hatası olursa ASIL hata yükselir.
SAHTE (en alt kat): dosya sistemi (`os.replace` / `Path.unlink` / `Path.write_text` — yalnız hedef yolda) · sır deposu
(`secrets_manager.get_secret`) · DB sürücüsü (sahte SQLCipher modülü / bağlantı) · mandal okuması. GERÇEK: modüller.
"""

from __future__ import annotations

import logging
import pathlib
import sqlite3
import time
from types import SimpleNamespace

import pytest
from utils import backup_recovery as br

# .gitleaks.toml izin listesindeki, ÖNCEDEN doğrulanmış SAHTE değerler (test_backup_recovery.py ile aynı)
_KEYS = {"sqlcipher_key": "s3cr3t-sqlcipher-anahtari-xyz", "patient_fernet_key": "p4t13nt-fernet-key"}


@pytest.fixture()
def izole_sirlar(tmp_path, monkeypatch):
    """Sır deposu tmp'de (test_backup_recovery.py ile aynı): GERÇEK pemf_secrets.json'a dokunulmaz."""
    from utils import secrets_manager as sm

    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sm, "_CACHE", None, raising=False)
    store = dict(_KEYS)

    def _get(key, default="", generate=True):
        if key in store:
            return store[key]
        if generate:
            store[key] = f"URETILDI-{key}"
            return store[key]
        return default

    monkeypatch.setattr(sm, "get_secret", _get)
    monkeypatch.setattr(sm, "set_secret", lambda k, v: store.__setitem__(k, v))
    return store


# ── Kurtarma kodu / zarfı ─────────────────────────────────────────────────────


def test_kod_dosyasi_yerine_konamazsa_asil_hata_yukselir_gecici_silinemese_de(tmp_path, monkeypatch):
    gercek_replace = br.os.replace
    gercek_unlink = pathlib.Path.unlink

    def _replace(src, dst, *a, **k):
        if pathlib.Path(dst).name == br.CODE_FILE_NAME:
            raise PermissionError(32, "KURTARMA-KODU.txt başka işlemce açık (aparat)")
        return gercek_replace(src, dst, *a, **k)

    def _unlink(self, *a, **k):
        if self.name.startswith(br.CODE_FILE_NAME) and self.name.endswith(".tmp"):
            raise PermissionError(5, "geçici dosya silinemedi (aparat)")
        return gercek_unlink(self, *a, **k)

    monkeypatch.setattr(br.os, "replace", _replace)
    monkeypatch.setattr(pathlib.Path, "unlink", _unlink)
    with pytest.raises(PermissionError, match="başka işlemce açık"):
        br.write_code_file(tmp_path, br.generate_recovery_code())
    assert not (tmp_path / br.CODE_FILE_NAME).exists()


def test_zarf_bir_hedefe_yazilamazsa_digerine_yine_yazilir(tmp_path, izole_sirlar, monkeypatch, caplog):
    app = tmp_path / "app"
    app.mkdir()
    kilitli, saglam = tmp_path / "usb", tmp_path / "yedek"
    gercek_replace = br.os.replace
    gercek_unlink = pathlib.Path.unlink

    def _replace(src, dst, *a, **k):
        if pathlib.Path(dst) == kilitli / br.ENVELOPE_NAME:
            raise PermissionError(5, "hedef salt okunur (aparat)")
        return gercek_replace(src, dst, *a, **k)

    def _unlink(self, *a, **k):
        if self.parent == kilitli and self.name.endswith(".tmp"):
            raise PermissionError(5, "geçici zarf silinemedi (aparat)")
        return gercek_unlink(self, *a, **k)

    monkeypatch.setattr(br.os, "replace", _replace)
    monkeypatch.setattr(pathlib.Path, "unlink", _unlink)
    with caplog.at_level(logging.WARNING, logger=br.logger.name):
        assert br.refresh_recovery_material(app, [kilitli, saglam]) is True
    kod = izole_sirlar["backup_recovery_code"]
    assert br.open_envelope(kod, (saglam / br.ENVELOPE_NAME).read_bytes()) == _KEYS
    assert not (kilitli / br.ENVELOPE_NAME).exists()
    assert any("kurtarma zarfi yazilamadi" in r.getMessage() and str(kilitli) in r.getMessage() for r in caplog.records)


def test_muhur_yazilamazsa_sonraki_tur_yeniden_yazar(tmp_path, izole_sirlar, monkeypatch):
    app = tmp_path / "app"
    app.mkdir()
    yedek = tmp_path / "yedek"
    gercek_write_text = pathlib.Path.write_text

    def _write_text(self, *a, **k):
        if self.name == br._FP_FILE_NAME:
            raise OSError(28, "disk dolu (aparat)")
        return gercek_write_text(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "write_text", _write_text)
    assert br.refresh_recovery_material(app, [yedek]) is True
    assert not (app / br._FP_FILE_NAME).exists(), "aparat: mühür yazılmış"
    monkeypatch.setattr(pathlib.Path, "write_text", gercek_write_text)
    zarf_once = (yedek / br.ENVELOPE_NAME).stat().st_mtime_ns
    time.sleep(0.02)
    assert br.refresh_recovery_material(app, [yedek]) is True
    assert (app / br._FP_FILE_NAME).read_text(encoding="utf-8").startswith(br._FP_MUHUR_ONEKI)
    assert (yedek / br.ENVELOPE_NAME).stat().st_mtime_ns != zarf_once, "mühürsüz tur 'güncel' sayıldı, zarf yenilenmedi"


# ── Doz değişikliği kaydı ─────────────────────────────────────────────────────


def test_parametre_degisikligi_DB_ulasilamazsa_surus_yaniti_basarili_kayda_yazildi_DENMEZ(
    tmp_path, monkeypatch, caplog
):
    from fastapi.testclient import TestClient
    from servers import api_server as api

    def _db_yok():
        raise RuntimeError("tedavi DB'si açılamadı (aparat)")

    monkeypatch.setattr(api, "_get_treatment_db", _db_yok)
    with api._session_lock:
        eski = dict(api._active_session)
        api._active_session.clear()
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "kp3",
                "db_session_id": 41,
                "mode": "Manuel",
                "duration_minutes": 5,
                "start_time": time.time(),
                "started_epoch": time.time(),
                "start_mono": time.monotonic(),
                "coil_ids": [1],
            }
        )
    try:
        c = TestClient(api.app, client=("127.0.0.1", 51234))
        with caplog.at_level(logging.ERROR):
            r = c.post("/api/session/parametre_guncelle", json={"frequency": 150})
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("status") == "success" and r.json().get("kayda_yazildi") is False, r.json()
        assert any("kayda yazilamadi" in rec.getMessage() for rec in caplog.records)
    finally:
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski)


# ── Kart DUTY reddi metni ──────────────────────────────────────────────────────

DUTY_NACK = "-> STM_NACK: RANGE coil=1 field=duty value_milli=800000 max_milli=500000 kip=bipolar"


def test_duty_reddi_metni_mandal_okunamazsa_yine_uretilir_sifirla_ipucusuz(monkeypatch):
    from servers import live_state as ls
    from utils import estop_mandali

    def _okunamaz():
        raise OSError("mandal dosyası okunamadı (aparat)")

    monkeypatch.setattr(estop_mandali, "mandalli_mi", _okunamaz)
    try:
        for _ in range(ls.STM_RED_ESIGI):
            ls.stm_komut_reddi_bildir(DUTY_NACK)
        metin = ls.stm_red_duty_metni("", dil="tr")
        assert metin and metin == ls.stm_duty_reddi_metni(DUTY_NACK, "", sifirla=False, dil="tr")
    finally:
        ls.stm_komut_kabulu_bildir()


# ── Tedavi DB'si bağlantı kapanışı ─────────────────────────────────────────────


class _KapanmayanBaglanti:
    """Sahte sürücü bağlantısı: `PRAGMA key` kabul, ilk okuma 'file is not a database' (yanlış anahtar), KAPATMA da patlar."""

    row_factory = None

    def __init__(self, kayit):
        self._k = kayit

    def execute(self, sql, *a):
        if sql.startswith("PRAGMA key"):
            return None
        raise sqlite3.DatabaseError("file is not a database")

    def close(self):
        self._k.append("close")
        raise OSError("kapatma da düştü (aparat)")


@pytest.fixture()
def tdb(tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(tmp_path / "gecmis")
    yield d
    try:
        d.close()
    except Exception:
        pass


def test_onbellek_anahtari_acmaz_ve_kapatma_patlarsa_tam_cozumlemeyle_yeniden_denenir(tdb, monkeypatch):
    kapatmalar: list = []
    surucu = SimpleNamespace(connect=lambda *a, **k: _KapanmayanBaglanti(kapatmalar), Row=sqlite3.Row)
    monkeypatch.setattr(tdb, "_import_sqlcipher", lambda: surucu)
    monkeypatch.setattr(tdb, "_get_sqlcipher_key", lambda: "birincil-anahtar")
    monkeypatch.setattr(tdb, "_get_sqlcipher_key_legacy", lambda: "")
    tdb._cipher_key_cache = "eski-onbellek-anahtari"
    assert tdb._connect_sqlcipher_if_configured() is None
    assert tdb._cipher_key_cache is None, "açmayan önbellek anahtarı bırakıldı"
    assert kapatmalar == ["close", "close"], "önbellek + birincil denemesinin bağlantısı kapatılmaya çalışılmadı"
    assert tdb._anahtar_vardi_ama_acmadi is True


class _WalsizBaglanti:
    def __init__(self, kayit, ayar_hatasi=None):
        self._k = kayit
        self._ayar_hatasi = ayar_hatasi

    def execute(self, sql, *a):
        if self._ayar_hatasi and sql.startswith("PRAGMA foreign_keys"):
            raise self._ayar_hatasi
        if sql.startswith("PRAGMA journal_mode"):
            raise sqlite3.OperationalError("database is locked")
        return SimpleNamespace(fetchone=lambda: ("delete",))

    def close(self):
        self._k.append("close")
        raise OSError("kapatma da düştü (aparat)")


def test_WAL_ayarlanamaz_ve_kapatma_patlarsa_yeni_baglanti_DELETE_kipinde(tdb, monkeypatch):
    kapatmalar: list = []
    gercek = tdb._connect_plain_sqlite
    sira = iter([_WalsizBaglanti(kapatmalar)])
    # Fikstürün kendi bağlantıları kapatılır: başka bir bağlantı dosyayı WAL'de açık tutarken DELETE'e geçiş sessizce YAPILMAZ
    # (ürün bunu zararsız sayıp mevcut kipte sürer — O-A2-2.b); burada yalnız yeni bağlantının kurulduğu ölçülür.
    tdb.close_connections()
    monkeypatch.setattr(tdb, "_connect_sqlcipher_if_configured", lambda: None)
    monkeypatch.setattr(tdb, "_connect_plain_sqlite", lambda: next(sira, None) or gercek())
    conn = tdb._create_connection()
    try:
        assert kapatmalar == ["close"]
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        conn.close()


def test_baglanti_ayarinda_hata_ve_kapatma_patlarsa_ASIL_hata_yukselir(tdb, monkeypatch):
    kapatmalar: list = []
    monkeypatch.setattr(tdb, "_connect_sqlcipher_if_configured", lambda: None)
    monkeypatch.setattr(
        tdb,
        "_connect_plain_sqlite",
        lambda: _WalsizBaglanti(kapatmalar, sqlite3.DatabaseError("file is not a database")),
    )
    with pytest.raises(sqlite3.DatabaseError, match="file is not a database"):
        tdb._create_connection()
    assert kapatmalar == ["close"]
