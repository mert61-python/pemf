# -*- coding: utf-8 -*-
"""KP-1 · `utils/production_config_manager.py` (PCM) · sözleşmeler: süreç TEKİLİ ikinci kez kurulmaz (eşzamanlı kurulumda da config yeniden
yüklenmez) · gömülü varsayılan → paket (donmuş `_MEIPASS`) config ya da şablon → kullanıcı config'i sırası; bozuk paket / şablon dosyası
açılışı durdurmaz · şablon kullanıcı config'ine YALNIZ eksik anahtarı ekler · şablon tamamlama / kayıt düşerse açılış sürer · kayıt hatası
günlüklenir · noktalı yol olmayan ara düğümü kurar, skaler içine inen okuma varsayılanı döner · hassas değer şifrelenemezse düz-metin
DÜRÜSTÇE yazılır ('enc:' öneki YOK) · çözme: sahibin zinciri → eski PCM `.pemf_key` (yalnız okunur) → çözülemezse ham değer + hata.

Gerçek veri kökü / kasa YOK: veri dizini PEMF_DATA_DIR = tmp; config.json'un sahibi (`pemf_gui.config`) test dizinine bağlı TAZE gerçek
örnek; alan anahtarı (`utils.secrets_manager.get_secret`) ve ACL (`utils.file_acl`) EN ALT katta sahte; PCM tekili her testte sıfırlanır.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
from pathlib import Path

import pytest
import utils.file_acl as fa
import utils.secrets_manager as sm
from cryptography.fernet import Fernet
from utils import production_config_manager as pcm

ANAHTAR = Fernet.generate_key().decode()


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    veri = tmp_path / "PEMF_GUI"
    veri.mkdir()
    monkeypatch.setattr(fa, "lock_down_file", lambda *a, **k: True)
    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: ANAHTAR if ad == "patient_fernet_key" else "")
    from pemf_gui import config as sahip_modulu

    sahip = sahip_modulu.ConfigManager(config_file=str(veri / "config.json"))
    monkeypatch.setattr(sahip_modulu, "config", sahip)
    monkeypatch.setattr(pcm.ProductionConfigManager, "_instance", None)
    monkeypatch.setattr(pcm, "_global_config", None)
    return veri


def _yeni():
    pcm.ProductionConfigManager._instance = None
    pcm._global_config = None
    return pcm.get_production_config()


def test_veri_dizini_ortak_cozucuden_gelir_tekil_IKINCI_kez_kurulmaz(ortam, monkeypatch):
    m = _yeni()
    assert m._get_app_data_dir() == ortam, "PCM sahibinden farklı veri dizinine bakıyor (split-brain)"
    m.set("serial.port", "COM42", save=False)
    yuklendi: list = []
    monkeypatch.setattr(pcm.ProductionConfigManager, "_load_config", lambda self: yuklendi.append(1))
    assert pcm.ProductionConfigManager() is m and yuklendi == [] and m.get("serial.port") == "COM42", (
        "tekil yeniden yüklendi"
    )


def test_eszamanli_kurulumda_kilit_beklerken_tamamlanan_kurulum_YENIDEN_yuklenmez(ortam, monkeypatch):
    m = _yeni()
    m._initialized = False  # ikinci iş parçacığı bayrağı henüz görmeden kilide girmiş gibi

    class _BeklerkenTamamlanan:
        def __enter__(self):
            m._initialized = True  # bekleme sırasında ilk iş parçacığı kurulumu bitirdi
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pcm.ProductionConfigManager, "_cfg_lock", _BeklerkenTamamlanan())
    yuklendi: list = []
    monkeypatch.setattr(pcm.ProductionConfigManager, "_load_config", lambda self: yuklendi.append(1))
    pcm.ProductionConfigManager.__init__(m)
    assert yuklendi == [], "kilit içi ikinci denetim yok → config iki kez yüklendi / şifreleyici ezildi"


def test_donmus_pakette_config_MEIPASS_ten_okunur_bozuk_paket_config_acilisi_durdurmaz(
    ortam, monkeypatch, tmp_path, caplog
):
    paket = tmp_path / "_internal"
    (paket / "config").mkdir(parents=True)
    (paket / "config" / "config.json").write_text(json.dumps({"serial": {"baudrate": 57600}}), encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(paket), raising=False)
    assert _yeni().get("serial.baudrate") == 57600, "donmuş paketteki config okunmadı"
    (ortam / "config.json").unlink()
    (paket / "config" / "config.json").write_text("{bozuk", encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger=pcm.logger.name):
        m = _yeni()
    assert m.get("serial.baudrate") == pcm._DEFAULT_CONFIG["serial"]["baudrate"]
    assert any("Failed to load bundled config" in r.getMessage() for r in caplog.records)


def test_sablon_kullanici_configine_YALNIZ_eksik_anahtari_ekler(ortam, tmp_path):
    (ortam / "config.json").write_text(json.dumps({"serial": {"port": "COM9"}}), encoding="utf-8")
    sablon = tmp_path / "sablon.json"
    sablon.write_text(
        json.dumps({"serial": {"port": "COM1", "yeni_alan": 7}, "yeni_bolum": {"a": 1}}), encoding="utf-8"
    )
    m = _yeni()
    m._upgrade_user_config_with_template(sablon)
    assert m.get("serial.port") == "COM9", "şablon kullanıcı değerini EZDİ"
    assert m.get("serial.yeni_alan") == 7 and m.get("yeni_bolum.a") == 1
    m._upgrade_user_config_with_template(None)  # şablon yok → dokunmaz
    (tmp_path / "bozuk.json").write_text("{", encoding="utf-8")
    m._upgrade_user_config_with_template(tmp_path / "bozuk.json")  # okunamaz → dokunmaz
    assert m.get("serial.port") == "COM9"


def test_sablon_tamamlama_ya_da_kayit_DUSERSE_acilis_SURER(ortam, monkeypatch):
    monkeypatch.setattr(
        pcm.ProductionConfigManager,
        "_upgrade_user_config_with_template",
        lambda self, t: (_ for _ in ()).throw(OSError("şablon kilitli")),
    )
    _yeni()  # kullanıcı config'i YOK → ilk config oluşturulur (şablon hatası yutulur)
    assert (ortam / "config.json").exists()
    m2 = _yeni()  # kullanıcı config'i VAR → tamamlama düşse de yüklenir
    assert m2._user_config_unreadable is None


def test_kayit_HATASI_gunluklenir_ve_CAGIRANA_yukselir(ortam, monkeypatch, caplog):
    m = _yeni()
    from pemf_gui import config as sahip_modulu

    monkeypatch.setattr(sahip_modulu, "config_json_yaz", lambda *a, **k: (_ for _ in ()).throw(OSError("disk dolu")))
    with caplog.at_level(logging.ERROR, logger=pcm.logger.name):
        with pytest.raises(OSError, match="disk dolu"):  # ayar ucu başarısızlığı ÖĞRENMELİ (sessiz "success" yok)
            m.set("serial.port", "COM77")
    assert any("Failed to save user config" in r.getMessage() for r in caplog.records)


def test_ara_dugum_kurulur_skaler_icine_inen_okuma_VARSAYILAN_doner(ortam):
    m = _yeni()
    m.set("yeni.alt.anahtar", 5, save=False)
    assert m.get("yeni.alt.anahtar") == 5
    assert m.get("serial.baudrate.ic", "yok") == "yok"


def test_KRITIK_sifrelenemeyen_hassas_deger_DUZ_yazilir_enc_oneki_YOK(ortam, monkeypatch, caplog):
    m = _yeni()
    assert m._encrypt_value("") == ""
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: (_ for _ in ()).throw(OSError("sır dizinine erişim yok")))
    from pemf_gui import config as sahip_modulu

    monkeypatch.setattr(sahip_modulu, "config", sahip_modulu.ConfigManager(config_file=str(ortam / "baska.json")))
    with caplog.at_level(logging.WARNING, logger=pcm.logger.name):
        m.set("mqtt.pass", "parola-x", save=False)
    assert m._config["mqtt"]["pass"] == "parola-x", "şifrelenemeyen değere sahte 'enc:' öneki eklendi"
    assert any("SIFRELENEMEDI" in r.getMessage() for r in caplog.records)


def test_KRITIK_cozme_SAHIP_sonra_ESKI_PCM_anahtari_cozulemezse_HAM_deger(ortam, monkeypatch, caplog):
    m = _yeni()
    assert m._decrypt_value("") == ""
    assert m._eski_pcm_anahtari() is None  # .pemf_key yok
    (ortam / ".pemf_key").write_bytes(b"gecersiz-anahtar")
    assert m._eski_pcm_anahtari() is None  # geçersiz → None (istisna yok)
    eski = Fernet.generate_key()
    (ortam / ".pemf_key").write_bytes(eski)
    eski_sifreli = base64.urlsafe_b64encode(Fernet(eski).encrypt(b"1.9.50-parola")).decode()
    assert m._decrypt_value(eski_sifreli) == "1.9.50-parola", "1.9.50 PCM'inin yazdığı değer okunamıyor"
    from pemf_gui import config as sahip_modulu

    monkeypatch.setattr(sahip_modulu, "get_config", lambda: (_ for _ in ()).throw(RuntimeError("sahip kurulamadı")))
    assert m._decrypt_value(eski_sifreli) == "1.9.50-parola", "sahip düşünce eski anahtara geçilmedi"
    with caplog.at_level(logging.ERROR, logger=pcm.logger.name):
        assert m._decrypt_value("Y296dWxlbWV6") == "Y296dWxlbWV6"
    assert any("Decryption failed" in r.getMessage() for r in caplog.records)
    assert Path(ortam / ".pemf_key").read_bytes() == eski, "PCM eski .pemf_key'e YAZDI"
