# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.09 (B-3.7 · B-3.16) — SQLCipher anahtarının YERİNİ söyleyen her metin GERÇEK yeri söyler.

Kusur: `utils.secrets_manager` başlığı DPAPI'li sırlar arasında `config_fernet_key` sayıyordu — öyle bir sır YOK
(`config.json`un şifreli alanları `patient_fernet_key` ile; 1.9.50'nin `.pemf_key`i düz dosyadır, yalnız ACL ile
korunur ve yalnız OKUNUR). Hasta / tedavi DB'sinin fail-closed iletileri ve RUNBOOK'un `atRestEncrypted=false` satırı
operatöre "`.sqlcipher_key`/keyring anahtarını doğrulayın" diyordu; anahtar ise D2.45'ten beri YALNIZ
`<veri kökü>\\pemf_secrets.json` → `auto.sqlcipher_key`dedir (DPAPI). Teknisyen olmayan dosyayı / boş kasayı arar,
gerçek sır dosyasına hiç bakmazdı.

Kapı (ölçüm → metin):
  (1) başlıkta adı geçen her sır GERÇEK `_REGISTRY`de var; "KRİTİK" listesi kayıttaki DPAPI'li sırların TAMAMI ve
      yalnızı;
  (2) taze kurulumda (izole veri kökü, null kasa — conftest) GERÇEK `get_sqlcipher_key` çağrılır: anahtar
      `pemf_secrets.json` → `auto.sqlcipher_key` (makineye bağlı şifreli) durur; kasaya yazım ve `.sqlcipher_key`
      dosyası 0;
  (3) iki DB'nin fail-closed iletisi GERÇEK kurucudan (binding yok + `PEMF_ENCRYPT_AT_REST=1`), şifresiz uyarısı
      günlükten alınır ve RUNBOOK satırı okunur: ölçülen dosya adını + `sqlcipher_key`i söyler, `.sqlcipher_key` /
      keyring demez.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
RUNBOOK = KOK / "docs" / "RUNBOOK.md"

#: Sahte EN ALT katta: binding paketleri içe aktarılamaz (paket eksik / bozuk) — ürün zinciri gerçek.
_BINDINGLER = ("sqlcipher3", "sqlcipher3.dbapi2", "pysqlcipher3", "pysqlcipher3.dbapi2")
#: Eski (yanlış) yer iddiaları — ileti / belge satırında GEÇMEZ.
_ESKI_YER = re.compile(r"keyring|(?<![A-Za-z_.])\.sqlcipher_key\b|config_fernet_key", re.IGNORECASE)


@pytest.fixture
def sm(monkeypatch):
    """İzole veri kökünde (conftest) temiz SecretsManager; ACL kilidi kaydedilmez, uygulanmaz."""
    from utils import file_acl
    from utils import secrets_manager as _sm

    monkeypatch.setattr(file_acl, "lock_down_file", lambda *a, **k: True)
    monkeypatch.setattr(file_acl, "lock_down_dir", lambda *a, **k: True, raising=False)
    monkeypatch.delenv("PEMF_SQLCIPHER_KEY", raising=False)
    _sm._cache = None
    yield _sm
    _sm._cache = None


@pytest.fixture
def kasa(monkeypatch):
    """Kimlik kasasına (python-keyring; conftest null arka uç) yazımları KAYDEDER — değer tutulmaz."""
    import keyring

    yazimlar: list[tuple[str, str]] = []
    gercek = keyring.set_password

    def _kaydet(servis, ad, deger):
        yazimlar.append((servis, ad))
        return gercek(servis, ad, deger)

    monkeypatch.setattr(keyring, "set_password", _kaydet)
    return yazimlar


@pytest.fixture
def olculen_yer(sm, kasa, temp_app_data, monkeypatch):
    """Taze kurulumda anahtarın GERÇEK yeri: (dosya adı, bölüm, anahtar adı) — ürün zincirinden ölçülür."""
    from database.sqlcipher_util import get_sqlcipher_key

    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    anahtar = get_sqlcipher_key(temp_app_data, None)
    assert anahtar, "aparat: şifreli kurulumda anahtar üretilmedi"
    sir = sm.secrets_path()
    assert sir.is_file(), f"aparat: sır dosyası yazılmadı: {sir}"
    belge = json.loads(sir.read_text(encoding="utf-8"))
    saklanan = belge.get("auto", {}).get("sqlcipher_key", "")
    assert saklanan, f"anahtar `{sir.name}` → auto.sqlcipher_key'de DEĞİL: bölümler={sorted(belge)}"
    assert saklanan != anahtar and saklanan.split(":", 1)[0] in ("DPAPI", "MKEY"), (
        "anahtar sır dosyasında makineye bağlı ŞİFRELİ durmuyor (DPAPI:/MKEY: öneki yok)"
    )
    assert sm._dec(saklanan) == anahtar, "aparat: saklanan değer dönen anahtara çözülmüyor"
    assert kasa == [], f"taze kurulumda kimlik kasasına yazıldı: {kasa}"
    for kok in {temp_app_data, sm._data_dir()}:
        dosyalar = list(Path(kok).rglob(".sqlcipher_key"))
        assert not dosyalar, f"taze kurulumda `.sqlcipher_key` dosyası yazıldı: {dosyalar}"
    return sir.name, "auto", "sqlcipher_key"


def _yer_dogru(metin: str, yer: tuple[str, str, str], nerede: str) -> None:
    dosya, _bolum, ad = yer
    assert dosya in metin and ad in metin, f"{nerede} anahtarın GERÇEK yerini söylemiyor ({dosya} → {ad}): {metin!r}"
    eski = _ESKI_YER.search(metin)
    assert eski is None, f"{nerede} eski / yanlış anahtar yerini söylüyor ({eski.group(0)!r}): {metin!r}"


# ── (1) başlık ↔ kayıt ────────────────────────────────────────────────────────
def test_secrets_manager_basligindaki_SIRLAR_kayitta_VAR_ve_DPAPI_listesi_TAM_D6_09():
    from utils import secrets_manager as sm

    baslik = sm.__doc__ or ""
    kayit = sm._REGISTRY
    # (a) sır adı biçimindeki her ad (dosya adı `.x_key` ve işlev çağrısı hariç) gerçek kayıtta olmalı.
    adlar = {
        m.group(0)
        for m in re.finditer(r"(?<![\w.\\/])[a-z][a-z0-9]*(?:_[a-z0-9]+)*_(?:key|code|token|pass)\b(?!\()", baslik)
    }
    assert adlar, "aparat: başlıkta sır adı bulunamadı"
    olmayan = sorted(adlar - set(kayit))
    assert not olmayan, f"secrets_manager başlığı kayıtta OLMAYAN sır adı sayıyor: {olmayan}"
    # (b) "KRİTİK kripto anahtarları (…)" listesi = kayıttaki DPAPI'li (dpapi=True) sırların tamamı.
    m = re.search(r"KRİTİK kripto anahtarları[^(]*\(([^)]*)\)", baslik)
    assert m, "aparat: başlıkta 'KRİTİK kripto anahtarları (…)' listesi yok"
    liste = {a.strip() for a in re.split(r"[,\s]+", m.group(1)) if a.strip()}
    olmayan = sorted(liste - set(kayit))
    assert not olmayan, f"KRİTİK listesinde kayıtta OLMAYAN sır: {olmayan}"
    dpapisiz = sorted(a for a in liste if not kayit[a][1])
    assert not dpapisiz, f"KRİTİK listesindeki sır kayıtta DPAPI'li DEĞİL: {dpapisiz}"
    eksik = sorted(a for a, (_b, dpapi, *_r) in kayit.items() if dpapi and a not in liste)
    assert not eksik, f"kayıtta DPAPI'li ama başlığın KRİTİK listesinde YOK: {eksik}"


# ── (2) + (3) ölçülen yer ↔ ileti / belge ─────────────────────────────────────
def test_KRITIK_taze_kurulumda_anahtar_pemf_secrets_jsonda_kasaya_ve_dosyaya_YAZILMAZ_D6_09(olculen_yer):
    assert olculen_yer == ("pemf_secrets.json", "auto", "sqlcipher_key")


def _bindingsiz(monkeypatch):
    for ad in _BINDINGLER:
        monkeypatch.setitem(sys.modules, ad, None)
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")


def test_KRITIK_hasta_DB_fail_closed_iletisi_GERCEK_yeri_soyler_D6_09(olculen_yer, temp_app_data, monkeypatch):
    from database.patient_database import PatientDatabase

    _bindingsiz(monkeypatch)
    with pytest.raises(RuntimeError) as hata:
        PatientDatabase(str(temp_app_data / "patients.db"))
    assert "patients.db" in str(hata.value), f"aparat: beklenen fail-closed iletisi değil: {hata.value}"
    _yer_dogru(str(hata.value), olculen_yer, "hasta DB'si fail-closed iletisi")


def test_KRITIK_tedavi_DB_fail_closed_iletisi_GERCEK_yeri_soyler_D6_09(olculen_yer, temp_app_data, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB

    _bindingsiz(monkeypatch)
    with pytest.raises(RuntimeError) as hata:
        TreatmentHistoryDB(temp_app_data / "tedavi")
    assert "tedavi DB" in str(hata.value), f"aparat: beklenen fail-closed iletisi değil: {hata.value}"
    _yer_dogru(str(hata.value), olculen_yer, "tedavi DB'si fail-closed iletisi")


def test_hasta_DB_SIFRESIZ_uyarisi_GERCEK_yeri_soyler_D6_09(olculen_yer, temp_app_data, monkeypatch, caplog):
    """Bayrak 0 + binding yok: hasta DB'si düz açılır ve günlüğe tek seferlik uyarı yazar — uyarı anahtarın yerini
    söyler."""
    from database.patient_database import PatientDatabase

    _bindingsiz(monkeypatch)
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "0")
    with caplog.at_level(logging.WARNING):
        PatientDatabase(str(temp_app_data / "patients.db"))
    uyarilar = [r.getMessage() for r in caplog.records if "AT-REST SIFRELEME KAPALI" in r.getMessage()]
    assert uyarilar, "aparat: şifresiz hasta DB'si uyarısı günlüğe yazılmadı"
    _yer_dogru(uyarilar[0], olculen_yer, "hasta DB'si şifresiz uyarısı")


def test_RUNBOOK_atRestEncrypted_satiri_GERCEK_yeri_soyler_D6_09(olculen_yer):
    satirlar = [s for s in RUNBOOK.read_text(encoding="utf-8").splitlines() if "atRestEncrypted=false" in s]
    assert len(satirlar) == 1, f"aparat: RUNBOOK'ta tek `atRestEncrypted=false` satırı bekleniyordu: {len(satirlar)}"
    _yer_dogru(satirlar[0], olculen_yer, "RUNBOOK `atRestEncrypted=false` satırı")


# ── D6.37 (B-11.6 · A-13) — RUNBOOK / database README: BİRİNCİL yer + makine dışı yedek için kurtarma zarfı ──────────
README_DB = KOK / "apps" / "backend" / "database" / "README.md"
#: Eski kaynaklar — satırda geçebilir ama YALNIZ "eski" diye anılan cümlede ve ölçülen yerden SONRA.
_ESKI_KAYNAK = re.compile(r"keyring|kimlik kasas|(?<![A-Za-z_.])\.sqlcipher_key\b", re.IGNORECASE)


def _birincil_yer_dogru(metin: str, yer: tuple[str, str, str], nerede: str) -> None:
    dosya, bolum, ad = yer
    assert dosya in metin and f"{bolum}.{ad}" in metin, (
        f"{nerede} anahtarın BİRİNCİL yerini ({dosya} → {bolum}.{ad}) söylemiyor: {metin!r}"
    )
    for m in _ESKI_KAYNAK.finditer(metin):
        assert metin.index(dosya) < m.start(), f"{nerede} eski kaynağı ({m.group(0)!r}) BİRİNCİL yerden önce anıyor"
        cumle = re.split(r"(?<=[.;—])\s", metin[: m.start()])[-1] + metin[m.start() : m.end() + 60]
        assert "eski" in cumle.casefold() or "eskİ" in cumle, (
            f"{nerede} eski kaynağı ({m.group(0)!r}) 'eski' demeden anıyor: …{cumle}…"
        )


def _makine_disi_zarf(metin: str, nerede: str) -> None:
    from utils.backup_recovery import ENVELOPE_NAME

    assert ENVELOPE_NAME in metin and "kurtarma kodu" in metin.casefold(), (
        f"{nerede} makine dışı yedeğin açılış yolunu (kurtarma kodu + {ENVELOPE_NAME}) göstermiyor"
    )
    assert "makineye bağlı" in metin, f"{nerede} anahtarın bu makineye bağlı (DPAPI) olduğunu söylemiyor"


def test_KRITIK_RUNBOOK_SQLCipher_anahtari_BIRINCIL_yer_ve_ZARF_D6_37(olculen_yer):
    satirlar = [s for s in RUNBOOK.read_text(encoding="utf-8").splitlines() if "**SQLCipher anahtarı**" in s]
    assert len(satirlar) == 1, f"aparat: RUNBOOK'ta tek '**SQLCipher anahtarı**' satırı bekleniyordu: {len(satirlar)}"
    _birincil_yer_dogru(satirlar[0], olculen_yer, "RUNBOOK 'SQLCipher anahtarı' satırı")
    _makine_disi_zarf(satirlar[0], "RUNBOOK 'SQLCipher anahtarı' satırı")


@pytest.mark.parametrize(
    "isaret", ["| `sqlcipher_util.py` |", "**Tüm-DB SQLCipher**"], ids=["sqlcipher_util_satiri", "sifreleme_modeli"]
)
def test_KRITIK_database_README_anahtar_satirlari_BIRINCIL_yeri_soyler_D6_37(olculen_yer, isaret):
    satirlar = [s for s in README_DB.read_text(encoding="utf-8").splitlines() if isaret in s]
    assert len(satirlar) == 1, f"aparat: database/README'de tek {isaret!r} satırı bekleniyordu: {len(satirlar)}"
    _birincil_yer_dogru(satirlar[0], olculen_yer, f"database/README {isaret!r} satırı")
    if "Tüm-DB" in isaret:
        _makine_disi_zarf(satirlar[0], "database/README şifreleme modeli satırı")
