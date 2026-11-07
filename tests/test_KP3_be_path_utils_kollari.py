# -*- coding: utf-8 -*-
"""KP-3 C · `utils/path_utils.py` kapsanmayan kolları (veri kökü / eski kök göçü / cihaz kimliği / eşleştirme kodu / sürüm) — her test bir
DAVRANIŞ iddiası. ⚠️ Ürün kodu (VERİ GÖÇÜ) DEĞİŞMEDİ; gerçek ProgramData / APPDATA / ev dizini AÇILMAZ — hepsi tmp'ye yönlendirilir.

- Anahtar göçü: eski kökteki sır dosyası bozuksa göç YAPILMAZ (uyarı, False — hedef ezilmez); ham anahtar okuyucu bozuk dosyada "".
- Farklı kopya bildirimi: kopyalar karşılaştırılamazsa (G/Ç hatası) FARKLI sayılır ve günlüğe yazılır (sessiz geçilmez).
- DB göçü: DB yerleşmeyince önceden kopyalanmış WAL geri alınamasa da göç engeli kaydedilir, uyarı yazılır, istisna yükselmez.
- Eski kök göçü: Windows dışında / APPDATA yokken hiçbir şey yapmaz; içeride beklenmedik hata açılışı DÜŞÜRMEZ.
- Veri kökü: macOS / Linux kökleri; sürücü türü Windows dışında ya da API hatasında "bilinmiyor" (0); sürücü harfi olmayan göreli yol ağ
  paylaşımı SAYILMAZ.
- Cihaz kimliği / eşleştirme kodu: dosya yazılamasa da (salt-okunur / dizin) çalışma zamanı değeri döner; sıfırlama isteğinde eski kod
  silinemese de yeni kod üretilir.
- Sürüm: VERSION dosyası yoksa `frontend_version.json`dan okunur.
"""

from __future__ import annotations

import json
import logging
import types
import uuid

import pytest
from utils import path_utils as pu

LOG = pu.__name__


def test_bozuk_sir_dosyasinda_anahtar_gocu_yapilmaz(tmp_path, caplog):
    eski, hedef = tmp_path / "eski", tmp_path / "hedef"
    eski.mkdir()
    hedef.mkdir()
    (eski / pu._SIR_DOSYASI).write_text("{bozuk", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger=LOG):
        assert pu._sqlcipher_anahtarini_gocur(eski, hedef) is False
    assert not (hedef / pu._SIR_DOSYASI).exists(), "bozuk kaynaktan hedefe sır dosyası yazıldı"
    assert any("at-rest anahtarı taşınamadı (sqlcipher_key)" in r.getMessage() for r in caplog.records)
    assert pu._ham_sqlcipher_anahtari(eski) == ""


def test_karsilastirilamayan_kopya_farkli_sayilir(monkeypatch, tmp_path, caplog):
    eski, hedef = tmp_path / "eski", tmp_path / "hedef"
    for k in (eski, hedef):
        k.mkdir()
        (k / "patients.db").write_bytes(b"x" * 10)

    def _okunamaz(yol):
        raise PermissionError(13, "kilitli", str(yol))

    monkeypatch.setattr(pu, "_sha256_dosya", _okunamaz)
    with caplog.at_level(logging.WARNING, logger=LOG):
        pu._farkli_kopyayi_bildir(eski, hedef, ["patients.db"])
    assert any("FARKLI kopya var (patients.db)" in r.getMessage() for r in caplog.records)


def test_db_yerlesmeyince_wal_geri_alinamasa_da_engel_kaydedilir(monkeypatch, tmp_path, caplog):
    eski, hedef = tmp_path / "eski", tmp_path / "hedef"
    eski.mkdir()
    hedef.mkdir()
    (eski / "ayarlar.db").write_bytes(b"db")
    (eski / "ayarlar.db-wal").write_bytes(b"wal")
    monkeypatch.setattr(pu, "_GOC_ENGELI", {})
    monkeypatch.setattr(pu, "_kopyala_dogrula", lambda k, v: None if k.name.endswith("-wal") else "SHA-256 tutmadı")
    with caplog.at_level(logging.WARNING, logger=LOG):
        assert pu._dosyalari_gocur(eski, hedef, ["ayarlar.db"]) == ["ayarlar.db"]
    mesajlar = [r.getMessage() for r in caplog.records]
    assert any("kopyalanan WAL geri alınamadı" in m for m in mesajlar)
    assert any("VERİ GÖÇÜ DOĞRULANAMADI: ayarlar.db (SHA-256 tutmadı)" in m for m in mesajlar)
    assert list(pu._GOC_ENGELI.values()) == ["SHA-256 tutmadı"]


def test_eski_kok_gocu_windows_disi_appdatasiz_ve_hata_kollari(monkeypatch, tmp_path):
    monkeypatch.setattr(pu, "_GOC_YAPILDI", set())
    monkeypatch.setattr(pu, "platform", types.SimpleNamespace(system=lambda: "Linux"))
    pu._kullanicidan_makineye_gocur(tmp_path / "hedef")
    assert pu._GOC_YAPILDI == set(), "Windows dışında göç denendi"
    monkeypatch.setattr(pu, "platform", types.SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setenv("APPDATA", "")
    (tmp_path / "cwd" / "PEMF_GUI").mkdir(parents=True)
    monkeypatch.chdir(tmp_path / "cwd")  # APPDATA boşken ÇALIŞMA DİZİNİNDEKİ `PEMF_GUI` eski kök sayılmamalı
    denenen: list = []
    monkeypatch.setattr(pu, "_sqlcipher_anahtarini_gocur", lambda *a, **k: denenen.append(a) or False)
    pu._kullanicidan_makineye_gocur(tmp_path / "hedef")
    assert len(pu._GOC_YAPILDI) == 1 and denenen == [], "APPDATA yokken çalışma dizininden göç denendi"
    (tmp_path / "roaming" / "PEMF_GUI").mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))

    def _patla(*a, **k):
        raise RuntimeError("sır dosyası kilitli")

    monkeypatch.setattr(pu, "_sqlcipher_anahtarini_gocur", _patla)
    pu._kullanicidan_makineye_gocur(tmp_path / "hedef2")  # fırlatmaz: göç bir kolaylık
    assert len(pu._GOC_YAPILDI) == 2


@pytest.mark.parametrize(
    "sistem,beklenen", [("Darwin", ("Library", "Application Support")), ("Linux", (".local", "share"))]
)
def test_veri_koku_macos_ve_linux(monkeypatch, tmp_path, sistem, beklenen):
    monkeypatch.setenv("PEMF_DATA_DIR", "x")
    monkeypatch.delenv("PEMF_DATA_DIR")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(pu, "platform", types.SimpleNamespace(system=lambda: sistem))
    d = pu.get_app_data_directory()
    assert d == tmp_path.joinpath(*beklenen, "PEMF_GUI") and d.is_dir()


def test_surucu_turu_bilinmiyor_ve_goreli_yol(monkeypatch):
    import ctypes

    monkeypatch.setattr(pu, "sys", types.SimpleNamespace(platform="linux"))
    assert pu._surucu_turu("Z:\\") == 0
    monkeypatch.undo()

    def _patla(*a, **k):
        raise OSError("kernel32 yüklenemedi")

    monkeypatch.setattr(ctypes, "WinDLL", _patla)
    assert pu._surucu_turu("Z:\\") == 0
    assert pu.veri_koku_ag_paylasiminda_mi("goreli/veri") is False


def test_kimlik_ve_eslestirme_kodu_yazilamasa_da_doner(monkeypatch, tmp_path):
    (tmp_path / "device_id.txt").mkdir()
    (tmp_path / "pairing_code.txt").mkdir()
    monkeypatch.setattr(pu, "get_app_data_directory", lambda: tmp_path)
    assert pu.get_unique_device_id() == str(uuid.getnode())
    monkeypatch.setenv("PEMF_RESET_PAIRING_CODE", "1")
    kod = pu.get_pairing_code()
    assert len(kod) == pu._PAIRING_CODE_LENGTH and all(c in pu._PAIRING_CODE_ALPHABET for c in kod)
    assert (tmp_path / "pairing_code.txt").is_dir()


def test_surum_version_yoksa_frontend_surumunden(monkeypatch, tmp_path):
    (tmp_path / "kok").mkdir()
    (tmp_path / "kok" / "frontend_version.json").write_text(json.dumps({"version": " 1.9.54 "}), encoding="utf-8")
    monkeypatch.setattr(pu, "_APP_VERSION", None)
    monkeypatch.setattr(pu, "packaged_resource_path", lambda *p: tmp_path / "paket" / p[-1])
    monkeypatch.setattr(pu, "kaynak_kokunu_bul", lambda dosya: tmp_path / "kok")
    assert pu.get_app_version() == "1.9.54"
