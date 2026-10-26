# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3I-A2.2 (Y93 · A-08) — AT-REST GÖÇÜ KESİNTİSİNDEN KALAN DÜZ `<db>.plain.bak` SONRAKİ AÇILIŞTA ŞİFRELENİR (SİLİNMEZ).

ÖLÇÜLEN KUSUR (önceden var; Y93 `032d2b8e` bu sınıfı kapatmak için geldi ama kökü taramıyordu): göç `.enc.tmp → db`yi yerleştirip
`.plain.bak`ı (göç öncesi DÜZ DB — TÜM hasta PII'si) güvenli silmeden ÖNCE kesilirse (güç / süreç öldürme) `.plain.bak` DÜZ kalır; sonraki
açılışlarda DB zaten şifreli → göç dalı koşmaz, Y93 arka plan taraması yalnız `migration_backups/` + `backups/`a bakar → düz PII süresiz.

SÖZLEŞME: Y93 taraması veri kökündeki tam `<db>.plain.bak`ı da aynı şifreleyiciyle (Y95: eski düz bloklar sıfırlanır) AYNI adla şifreler —
YALNIZ canlı `<db>` yerinde ve at-rest anahtarıyla AÇILIYORSA ve emanet istenmiyorsa; yarım göçün (`db` YOK) `.plain.bak`ına dokunmaz
(`_yarim_goc_toparla` geri koyar). Silme YOK (A-08). Kesinti GERÇEK göç kodunda (`goc_sonrasi_yedek_politikasi` öncesi) kurulur; yalnız
anahtar çözümü sabitlenir. D3I-A2.6 ile ÇAPRAZ SIRA kolları bu dosyada (iki düzeltme birlikte).
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

import pytest

_ANAHTAR = "d3i-a2-2-test-anahtari"
_KEYQ = "'" + _ANAHTAR + "'"
_LOG = logging.getLogger("d3i_a2_2")


class _Kesinti(BaseException):
    """Süreç ölümü: `except Exception` sarmalları YAKALAMAZ."""


@pytest.fixture
def su(monkeypatch):
    from database import sqlcipher_util as _su

    if _su.import_sqlcipher() is None:
        pytest.fail("sqlcipher3 bağlayıcısı yok (A-46: sessizce atlanmaz)")
    monkeypatch.delenv("PEMF_KEEP_PLAIN_BACKUP", raising=False)
    monkeypatch.delenv("PEMF_KEEP_PLAIN_BAK", raising=False)
    monkeypatch.setattr(_su, "get_sqlcipher_key", lambda *a, **k: _ANAHTAR)
    yield _su
    _su.yedek_sifrelemesini_bekle(60)


def _duz(yol: Path, deger: str) -> None:
    c = sqlite3.connect(str(yol))
    c.execute("CREATE TABLE kayit (ad TEXT)")
    c.execute("INSERT INTO kayit VALUES (?)", (deger,))
    c.commit()
    c.close()


def _oku(su, yol: Path) -> str:
    c = su.import_sqlcipher().connect(str(yol))
    try:
        c.execute(f"PRAGMA key={_KEYQ}")
        return c.execute("SELECT ad FROM kayit").fetchone()[0]
    finally:
        c.close()


def _kesik_goc(su, monkeypatch, kok: Path, deger: str = "KesintiHastasi", ad: str = "patients.db") -> tuple[Path, Path]:
    """GERÇEK göç: `db → .plain.bak`, `.enc.tmp → db` YAPILDI; `.plain.bak`ın güvenli silinmesinden ÖNCE süreç öldü."""
    db = kok / ad
    _duz(db, deger)
    gercek = su.goc_sonrasi_yedek_politikasi

    def _ol(*a, **k):
        raise _Kesinti()

    monkeypatch.setattr(su, "goc_sonrasi_yedek_politikasi", _ol)
    with pytest.raises(_Kesinti):
        su.migrate_to_encrypted_if_needed(str(db), kok, _LOG)
    monkeypatch.setattr(su, "goc_sonrasi_yedek_politikasi", gercek)
    bak = kok / (ad + ".plain.bak")
    assert su.duz_metin_sqlite_mi(bak) and db.exists() and not su.duz_metin_sqlite_mi(db), "kesinti kurulamadı"
    return db, bak


def test_KRITIK_D3I_A2_2_kesintiden_kalan_DUZ_plain_bak_sonraki_acilista_SIFRELENIR_SILINMEZ(su, monkeypatch, tmp_path):
    """MUTASYON: kök taraması yok → KIRMIZI ("hâlâ DÜZ")."""
    db, bak = _kesik_goc(su, monkeypatch, tmp_path)
    su.migrate_to_encrypted_if_needed(str(db), tmp_path, _LOG)  # sonraki açılış: "zaten şifreli" → Y93 arka plan
    assert su.yedek_sifrelemesini_bekle(60)
    assert bak.exists(), "kesintiden kalan yedek SİLİNDİ (A-08: silme yok)"
    assert not su.duz_metin_sqlite_mi(bak), "kesintiden kalan .plain.bak (TÜM PII) açılıştan sonra hâlâ DÜZ-METİN"
    assert _oku(su, bak) == "KesintiHastasi", "şifrelenen yedekte veri KAYBOLDU"
    assert _oku(su, db) == "KesintiHastasi", "canlı DB bozuldu"
    assert not list(tmp_path.glob("*.duz.sil")) and not list(tmp_path.glob("*.plain.bak.enc.tmp")), (
        "Y95 / geçici artık kaldı"
    )
    # Çapraz sıra (D3I-A2.6): canlı DB VARKEN toparlama ŞİFRELİ `.plain.bak`a dokunmaz (onu düz sanıp canlının yerine koymaz).
    assert su._yarim_goc_toparla(str(db), _LOG) is False and _oku(su, db) == "KesintiHastasi" and bak.exists()


def test_KARSIT_D3I_A2_2_emanet_isteniyorsa_plain_bak_DOKUNULMAZ(su, monkeypatch, tmp_path):
    db, bak = _kesik_goc(su, monkeypatch, tmp_path)
    once = bak.read_bytes()
    monkeypatch.setenv("PEMF_KEEP_PLAIN_BACKUP", "1")
    su.migrate_to_encrypted_if_needed(str(db), tmp_path, _LOG)
    assert su.yedek_sifrelemesini_bekle(60)
    assert bak.read_bytes() == once, "operatörün istediği düz emanet kopyası değiştirildi"


def test_KARSIT_D3I_A2_2_canli_DB_anahtarla_ACILMIYORSA_plain_bak_DOKUNULMAZ(su, monkeypatch, tmp_path):
    """Canlı DB doğrulanmış şifreli değilse (başka anahtar / bozuk) göç bitmiş sayılmaz — `.plain.bak` tek sağlam kopya olabilir.
    MUTASYON: canlı DB doğrulaması yok → KIRMIZI."""
    db, bak = _kesik_goc(su, monkeypatch, tmp_path)
    db.write_bytes(b"BOZUK-YA-DA-BASKA-ANAHTAR" * 64)
    once = bak.read_bytes()
    su.duz_metin_yedekleri_sifrele(tmp_path, _KEYQ, su.import_sqlcipher(), _LOG)
    assert bak.read_bytes() == once, "canlı DB doğrulanmadan .plain.bak şifrelendi"


def test_KARSIT_D3I_A2_2_yarim_gocte_plain_bak_SIFRELENMEZ_toparlanir(su, tmp_path):
    """`db` YOKKEN (yarım göç) `.plain.bak` şifrelenmez — toparlama onu DÜZ olarak geri koyar, göç yeniden dener ve biter."""
    _duz(tmp_path / "patients.db.plain.bak", "YarimGoc")
    once = (tmp_path / "patients.db.plain.bak").read_bytes()
    su.duz_metin_yedekleri_sifrele(tmp_path, _KEYQ, su.import_sqlcipher(), _LOG)
    assert (tmp_path / "patients.db.plain.bak").read_bytes() == once, (
        "yarım göçün tek kopyası şifrelendi (toparlama onu DÜZ bekler)"
    )
    su.migrate_to_encrypted_if_needed(str(tmp_path / "patients.db"), tmp_path, _LOG)
    assert su.yedek_sifrelemesini_bekle(60)
    assert _oku(su, tmp_path / "patients.db") == "YarimGoc", "yarım göç toparlanıp şifrelenmedi"


def test_KRITIK_D3I_A2_2_kokte_yarim_kalan_Y95_ikinci_adi_toparlanir(su, monkeypatch, tmp_path):
    """Kök şifrelemesi Y95 sıfırlamasında kesilirse kalan `<db>.plain.bak.duz.sil` (eski DÜZ içerik) sonraki taramada sıfırlanıp silinir."""
    db, bak = _kesik_goc(su, monkeypatch, tmp_path)
    gercek = su._duz_icerigi_sifirla_ve_sil

    def _ol(*a, **k):
        raise _Kesinti()

    monkeypatch.setattr(su, "_duz_icerigi_sifirla_ve_sil", _ol)
    with pytest.raises(_Kesinti):
        su.duz_metin_yedekleri_sifrele(tmp_path, _KEYQ, su.import_sqlcipher(), _LOG)
    monkeypatch.setattr(su, "_duz_icerigi_sifirla_ve_sil", gercek)
    sil = tmp_path / "patients.db.plain.bak.duz.sil"
    assert sil.exists() and su.duz_metin_sqlite_mi(sil), "Y95 kesintisi kurulamadı"
    su.duz_metin_yedekleri_sifrele(tmp_path, _KEYQ, su.import_sqlcipher(), _LOG)
    assert not sil.exists(), "kökte yarım kalan Y95 düz içeriği (TÜM PII) kaldı"
    assert _oku(su, bak) == "KesintiHastasi"


def test_D3I_A2_2_sifrelenmis_kok_plain_bak_IKINCI_taramada_DOKUNULMAZ_yanlis_HATA_yok(
    su, monkeypatch, tmp_path, caplog
):
    """D3I orkestratör: şifrelenmiş kök `.plain.bak` sonraki açılışların taramasında yeniden işlenmez — dosya aynen, `sifrelenemedi`
    boş, ERROR günlüğü YOK. Düz-metin denetimi atlanırsa şifreleyici şifreli dosyayı düz sanıp düşer ve her açılışta "DÜZ-METİN ama
    SAĞLAM bırakıldı" diye YANLIŞ hata yazılır (operatör yanıltılır). MUTASYON: düz-metin denetimi yok → KIRMIZI (ilk turda YAŞADI)."""
    db, bak = _kesik_goc(su, monkeypatch, tmp_path)
    ilk = su.duz_metin_yedekleri_sifrele(tmp_path, _KEYQ, su.import_sqlcipher(), _LOG)
    assert [Path(p).name for p in ilk["sifrelendi"]] == [bak.name] and not su.duz_metin_sqlite_mi(bak), ilk
    once = bak.read_bytes()
    caplog.clear()
    with caplog.at_level(logging.ERROR):
        ikinci = su.duz_metin_yedekleri_sifrele(tmp_path, _KEYQ, su.import_sqlcipher(), _LOG)
    assert bak.read_bytes() == once, "şifreli yedek ikinci taramada değişti"
    assert ikinci == {"sifrelendi": [], "sifrelenemedi": []}, ikinci
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], [r.getMessage() for r in caplog.records]
    assert _oku(su, bak) == "KesintiHastasi"


# ─────────────────────────── ÇAPRAZ SIRA: D3I-A2.2 × D3I-A2.6 (iki düzeltme birlikte) ───────────────────────────


@pytest.fixture
def kokler(tmp_path, monkeypatch):
    from utils import path_utils as pu

    if sys.platform != "win32":
        pytest.skip("eski kök göçü yalnız Windows'ta koşar")
    eski_appdata = tmp_path / "kullanici" / "AppData" / "Roaming"
    eski = eski_appdata / "PEMF_GUI"
    eski.mkdir(parents=True)
    hedef = tmp_path / "ProgramData" / "PEMF_System" / "PEMF_GUI"
    hedef.mkdir(parents=True)
    _duz(eski / "patients.db", "BayatEskiKok")
    monkeypatch.setenv("APPDATA", str(eski_appdata))
    monkeypatch.setattr(pu, "_GOC_YAPILDI", set())
    monkeypatch.setattr(pu, "_GOC_ENGELI", {}, raising=False)
    return pu, eski, hedef


def _duz_artik(su, kok: Path) -> list:
    return [p.name for p in kok.glob("patients.db.plain.bak*") if su.duz_metin_sqlite_mi(p)]


def test_CAPRAZ_A22_sonra_A26_sifrelenmis_plain_bak_varken_db_KAYBOLURSA_eski_kok_getirilmez_toparlanan_ACILIR(
    su, monkeypatch, kokler
):
    """Sıra: kesinti → (A2.2) `.plain.bak` şifrelendi → karantina `db → .acilamadi-*` ile yeni DB arasında kesinti → açılış:
    (A2.6) eski kökün BAYAT kopyası GELMEZ; toparlama ŞİFRELİ `.plain.bak`ı geri koyar ve at-rest anahtarıyla AÇILIR (düz sanılıp
    bozulmaz); düz-metin artık KALMAZ."""
    pu, eski, hedef = kokler
    db, bak = _kesik_goc(su, monkeypatch, hedef)
    su.migrate_to_encrypted_if_needed(str(db), hedef, _LOG)
    assert su.yedek_sifrelemesini_bekle(60) and not su.duz_metin_sqlite_mi(bak)
    db.rename(hedef / "patients.db.acilamadi-20261026_120000")
    once = (eski / "patients.db").read_bytes()

    pu._kullanicidan_makineye_gocur(hedef)
    assert not db.exists(), "hedefte artık varken eski kökün BAYAT DB'si getirildi"
    assert su._yarim_goc_toparla(str(db), _LOG) is True
    su.migrate_to_encrypted_if_needed(str(db), hedef, _LOG)
    assert su.yedek_sifrelemesini_bekle(60)
    assert _oku(su, db) == "KesintiHastasi", "toparlanan (şifreli) kopya anahtarla açılmadı"
    assert _duz_artik(su, hedef) == [], "düz-metin .plain.bak artığı kaldı"
    assert (eski / "patients.db").read_bytes() == once, "eski kök değişti"


def test_CAPRAZ_A26_sonra_A22_yarim_gocte_eski_kok_getirilmez_goc_biter_DUZ_ARTIK_kalmaz(su, kokler):
    """Sıra: yarım göç (`db` YOK + DÜZ `.plain.bak` GÜNCEL) → açılış: (A2.6) eski kök getirilmez → toparlama + göç tamamlanır →
    (A2.2) Y93 taraması yarım göçün kopyasına dokunmamıştı; göç sonrası politika onu güvenli siler → düz artık YOK, veri GÜNCEL."""
    pu, eski, hedef = kokler
    _duz(hedef / "patients.db.plain.bak", "GuncelHasta")
    once = (eski / "patients.db").read_bytes()

    pu._kullanicidan_makineye_gocur(hedef)
    assert not (hedef / "patients.db").exists(), "yarım göçte eski kökün BAYAT DB'si getirildi"
    su.migrate_to_encrypted_if_needed(str(hedef / "patients.db"), hedef, _LOG)
    assert su.yedek_sifrelemesini_bekle(60)
    assert _oku(su, hedef / "patients.db") == "GuncelHasta"
    assert _duz_artik(su, hedef) == [], "düz-metin .plain.bak artığı kaldı"
    assert (eski / "patients.db").read_bytes() == once, "eski kök değişti"
