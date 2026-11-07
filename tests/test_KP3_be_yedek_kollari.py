# -*- coding: utf-8 -*-
"""KP-3 C · yedek dosyası (`database/yedek_dosyasi.py`) + kurtarma zarfı (`utils/backup_recovery.py`) kapsanmayan kolları — her test
bir DAVRANIŞ iddiası (ürün kodu DEĞİŞMEDİ):

- Başarısız yedek artığı silinemezse (açık tutamaç) uyarı yazılır, istisna yükselmez.
- `yedek_acilir_mi`: boş dosya / olmayan yol / tablosuz DB → AÇILMAZ; bağlantı kapanışı patlasa da karar döner.
- `yedek_yaz`: hedef DELETE kipine alınamazsa yedek yine yazılır (uyarıyla); yedekleme hatasında hedef kapanamasa da ASIL hata yükselir
  ve geçici dosya kaldırılır.
- Şifreli hesap yedeği / çözümü doğrulanamazsa istisna + çıktı OLUŞMAZ; çözüm hedefi varsa üzerine yazılmaz.
- Ayar yedeği: listedeki `enc:` değerleri ayıklanır (yol `alan[i]`); geçersiz JSON yedeği geçersiz; geri okunan ayar yazılanla eşit
  değilse yedek oluşmaz ve geçici dosya kaldırılır.
- Kurtarma: boş kod / boş anahtar sözlüğü / desteklenmeyen zarf sürümü → ValueError; kod dosyası ACL kilitlenemese de yazılır; hedef
  dizin yoksa malzeme yenilenmez.

Sahte EN ALT katta: SQLite bağlantı sınıfı (alt sınıf), bağlayıcı modül, ACL yardımcısı, doğrulayıcı; dosyalar gerçek (tmp).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3

import pytest
from database import sqlcipher_util as su
from database import yedek_dosyasi as yd
from utils import backup_recovery as br

LOG = logging.getLogger("kp3.yedek")


def _tablolu_db(yol) -> sqlite3.Connection:
    c = sqlite3.connect(str(yol))
    c.execute("CREATE TABLE t (x INTEGER)")
    c.execute("INSERT INTO t VALUES (1)")
    c.commit()
    return c


def test_acik_tutamacli_artik_silinemezse_uyari_yukselmez(tmp_path, caplog):
    artik = tmp_path / "yedek.db.tmp"
    artik.write_bytes(b"x")
    with open(artik, "rb"), caplog.at_level(logging.WARNING, logger="kp3.yedek"):
        yd.basarisiz_yedegi_kaldir(str(artik), LOG)
    assert artik.exists()
    assert any("kaldirilamadi" in r.getMessage() for r in caplog.records)


def test_yedek_acilir_mi_bos_yok_tablosuz_ve_kapanis_hatasi(tmp_path):
    bos = tmp_path / "bos.db"
    bos.write_bytes(b"")
    assert yd.yedek_acilir_mi(bos) is False
    assert yd.yedek_acilir_mi(tmp_path / "yok.db") is False
    tablosuz = tmp_path / "tablosuz.db"
    c = sqlite3.connect(str(tablosuz))
    c.execute("PRAGMA user_version=1")
    c.commit()
    c.close()
    assert tablosuz.stat().st_size > 0 and yd.yedek_acilir_mi(tablosuz) is False

    class _Imlec:
        def fetchone(self):
            return (3,)

    class _KapanmayanBaglanti:
        def execute(self, sql):
            return _Imlec()

        def close(self):
            raise sqlite3.ProgrammingError("kapanış hatası")

    sifreli = tmp_path / "sifreli.db"
    sifreli.write_bytes(b"\x8f" * 64)
    baglayici = type("B", (), {"connect": staticmethod(lambda yol: _KapanmayanBaglanti())})
    assert yd.yedek_acilir_mi(sifreli, baglayici, "anahtar") is True


class _WalKalan(sqlite3.Connection):
    def execute(self, sql, *a):
        if sql.strip().upper().startswith("PRAGMA JOURNAL_MODE"):
            return super().execute("SELECT 'wal'")
        return super().execute(sql, *a)


def test_yedek_delete_kipine_alinamazsa_yine_yazilir(tmp_path, caplog):
    kaynak = _tablolu_db(tmp_path / "kaynak.db")
    hedef = tmp_path / "yedek.db"
    baglayici = type("B", (), {"connect": staticmethod(lambda yol: sqlite3.connect(yol, factory=_WalKalan))})
    with caplog.at_level(logging.WARNING, logger="kp3.yedek"):
        yd.yedek_yaz(kaynak, str(hedef), baglayici, "", LOG)
    kaynak.close()
    assert yd.yedek_acilir_mi(hedef, tam=True) is True
    assert any("DELETE kipine alinamadi" in r.getMessage() for r in caplog.records)


class _KapanmayanHedef(sqlite3.Connection):
    def close(self):
        super().close()
        raise sqlite3.ProgrammingError("hedef kapanamadı")


def test_yedekleme_hatasinda_asil_hata_yukselir_gecici_kaldirilir(tmp_path):
    class _BozukKaynak:
        def backup(self, *a, **k):
            raise sqlite3.OperationalError("kaynak kilitli")

    hedef = tmp_path / "yedek.db"
    baglayici = type("B", (), {"connect": staticmethod(lambda yol: sqlite3.connect(yol, factory=_KapanmayanHedef))})
    with pytest.raises(sqlite3.OperationalError, match="kaynak kilitli"):
        yd.yedek_yaz(_BozukKaynak(), str(hedef), baglayici, "", LOG)
    assert not hedef.exists() and not os.path.exists(yd.gecici_yol(str(hedef)))
    yd._kapat(None, sqlite3.connect(":memory:", factory=_KapanmayanHedef))  # kapanış hatası yutulur


@pytest.mark.skipif(su.import_sqlcipher() is None, reason="sqlcipher3 binding yok")
def test_sifreli_hesap_yedegi_ve_cozumu_dogrulanamazsa_cikti_olusmaz(tmp_path, monkeypatch):
    sc = su.import_sqlcipher()
    kaynak = tmp_path / "auth.db"
    _tablolu_db(kaynak).close()
    gercek = yd.yedek_acilir_mi
    monkeypatch.setattr(yd, "yedek_acilir_mi", lambda *a, **k: False)
    with pytest.raises(RuntimeError, match="DOGRULANAMADI"):
        yd.duz_dbyi_yedekle(str(kaynak), str(tmp_path / "auth.yedek"), sc, "anahtar-1", LOG)
    assert not (tmp_path / "auth.yedek").exists()
    monkeypatch.setattr(yd, "yedek_acilir_mi", gercek)
    yd.duz_dbyi_yedekle(str(kaynak), str(tmp_path / "auth.yedek"), sc, "anahtar-1", LOG)
    monkeypatch.setattr(yd, "yedek_acilir_mi", lambda *a, **k: False)
    with pytest.raises(RuntimeError, match="cozulen hesap yedegi"):
        yd.sifreli_yedegi_duze_coz(str(tmp_path / "auth.yedek"), str(tmp_path / "geri.db"), sc, "anahtar-1", LOG)
    assert not (tmp_path / "geri.db").exists()
    (tmp_path / "var.db").write_bytes(b"dokunma")
    with pytest.raises(FileExistsError):
        yd.sifreli_yedegi_duze_coz(str(tmp_path / "auth.yedek"), str(tmp_path / "var.db"), sc, "anahtar-1", LOG)
    assert (tmp_path / "var.db").read_bytes() == b"dokunma"


def test_ayar_yedegi_liste_sifreleri_bozuk_json_ve_esit_olmayan_geri_okuma(tmp_path):
    temiz, ayiklanan = yd.sirsiz_ayarlar({"sunucular": ["acik", "enc:gizli", {"ad": "x"}]})
    assert temiz == {"sunucular": ["acik", {"ad": "x"}]} and ayiklanan == ["sunucular[1]"]
    bozuk = tmp_path / "ayar.json"
    bozuk.write_text("{bozuk", encoding="utf-8")
    assert yd.json_yedegi_gecerli_mi(bozuk) is False
    hedef = tmp_path / "ayar.yedek.json"
    with pytest.raises(RuntimeError, match="esit degil"):
        yd.json_yedegi_yaz({"demet": (1, 2)}, str(hedef), LOG)
    assert not hedef.exists() and not os.path.exists(yd.gecici_yol(str(hedef)))


def test_kurtarma_bos_kod_bos_anahtar_ve_surum(tmp_path):
    with pytest.raises(ValueError, match="Kurtarma kodu bos"):
        br._derive(" - ", b"\0" * 16)
    with pytest.raises(ValueError, match="anahtar yok"):
        br.build_envelope(br.generate_recovery_code(), {})
    zarf = json.dumps({"tur": "kurtarma-zarfi", "v": 99, "salt": base64.b64encode(b"\0" * 16).decode()}).encode()
    with pytest.raises(ValueError, match="Desteklenmeyen zarf surumu: 99"):
        br.open_envelope(br.generate_recovery_code(), zarf)
    assert br.refresh_recovery_material(tmp_path, ["", None]) is False


def test_kod_dosyasi_acl_kilitlenemese_de_yazilir(tmp_path, monkeypatch, caplog):
    from utils import file_acl

    def _patla(*a, **k):
        raise OSError("icacls yok")

    monkeypatch.setattr(file_acl, "lock_down_file", _patla)
    kod = br.generate_recovery_code()
    with caplog.at_level(logging.DEBUG, logger=br.logger.name):
        yol = br.write_code_file(tmp_path, kod)
    assert yol.exists() and br.format_code(kod) in yol.read_text(encoding="utf-8")
    assert any("ACL kilitlenemedi" in r.getMessage() for r in caplog.records)
