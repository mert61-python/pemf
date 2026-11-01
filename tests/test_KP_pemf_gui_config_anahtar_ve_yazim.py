# -*- coding: utf-8 -*-
"""KP-1 · `pemf_gui/config.py` · sözleşmeler: config.json JSON NESNESİ olmalı · erişim reddi onarılamazsa hata çağırana yükselir (varsayılanlar
klinik ayarlarını ezmesin) · atomik yazımda takas düşerse dosya ÖNCEKİ baytlarla kalır, geçici dosya silinemese de ASIL hata yükselir,
ACL kilidi düşse de yazım tamamlanır · veri kökü yoksa `~/.pemf_gui` · eski `~/.pemf_gui` dosyaları kanonik dizine İLERİ taşınır (var olan
EZİLMEZ, eski SİLİNMEZ, kopya kilitlenir; kilit / kopya hatası açılışı durdurmaz) · birincil alan anahtarı alınamazsa / boşsa fail-closed
(yeni anahtar ÜRETİLMEZ) · eski anahtar çözücüsü bozuk `.pemf_key` / MAC hatasında atlar · şifreleme boş değeri olduğu gibi döner, base64
olmayan değer çözülmeden döner · düz-metin sır göçü şifreleme / kayıt düşerse açılışı durdurmaz.

Gerçek veri kökü / kasa YOK: dizinler `tmp_path`; dosya açma (`pemf_gui.config.open`), `os.replace` / `os.remove`, ACL (`utils.file_acl`) ve
anahtar kaynağı (`utils.secrets_manager.get_secret`) EN ALT katta sahte.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest
import utils.file_acl as fa
import utils.secrets_manager as sm

import pemf_gui.config as cfg


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    kilit: list = []
    monkeypatch.setattr(fa, "lock_down_file", lambda p, **k: kilit.append(Path(p)) or True)
    monkeypatch.setattr(
        sm,
        "get_secret",
        lambda ad, *a, **k: "uR0pZ1f2x7L3c7p0bS3oE5qJ8m4vN6tY9aK2hW1dG0s=" if ad == "patient_fernet_key" else "",
    )
    monkeypatch.setenv("HOME", str(tmp_path / "ev"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "ev"))
    return kilit


def test_config_json_NESNE_degilse_reddedilir(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON nesnesi degil"):
        cfg.config_json_oku(p)


def test_KRITIK_erisim_reddi_ONARILAMAZSA_hata_cagirana_yukselir(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    p.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        cfg, "open", lambda *a, **k: (_ for _ in ()).throw(PermissionError("Erişim engellendi")), raising=False
    )
    monkeypatch.setattr(fa, "lock_down_file", lambda *a, **k: (_ for _ in ()).throw(OSError("icacls yok")))
    with pytest.raises(PermissionError):
        cfg.config_json_oku(p)
    monkeypatch.setattr(fa, "lock_down_file", lambda *a, **k: False)  # başka hesabın dosyası → onarılamaz
    with pytest.raises(PermissionError):
        cfg.config_json_oku(p)


def test_KRITIK_atomik_takas_DUSERSE_onceki_baytlar_KALIR_gecici_silinemese_de_ASIL_hata(ortam, tmp_path, monkeypatch):
    p = tmp_path / "pemf" / "config.json"
    cfg.config_json_yaz(str(p), {"mqtt": {"broker": "klinik.local"}})
    once = p.read_bytes()
    with monkeypatch.context() as m:
        m.setattr(os, "replace", lambda a, b: (_ for _ in ()).throw(PermissionError("AV kilidi")))
        m.setattr(os, "remove", lambda yol: (_ for _ in ()).throw(PermissionError("silinemedi")))
        with pytest.raises(PermissionError, match="AV kilidi"):
            cfg.config_json_yaz(str(p), {"mqtt": {"broker": "YANLIS"}})
    assert p.read_bytes() == once, "takas düştü ama config.json değişti"


def test_ACL_kilidi_PATLASA_da_yazim_tamamlanir(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(fa, "lock_down_file", lambda *a, **k: (_ for _ in ()).throw(OSError("icacls yok")))
    p = tmp_path / "config.json"
    with caplog.at_level(logging.DEBUG, logger=cfg.logger.name):
        cfg.config_json_yaz(str(p), {"a": 1})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1}
    assert any("ACL kilidi uygulanamadi" in r.getMessage() for r in caplog.records)


def test_veri_koku_YOKSA_ev_altinda_pemf_gui(ortam, monkeypatch, tmp_path):
    monkeypatch.delenv("PEMF_DATA_DIR", raising=False)
    m = cfg.ConfigManager()
    assert Path(m.config_dir) == tmp_path / "ev" / ".pemf_gui" and Path(m.config_file).name == "config.json"


def test_KRITIK_eski_dizin_ILERI_tasinir_var_olan_EZILMEZ_eski_SILINMEZ_kopya_KILITLENIR(ortam, monkeypatch, tmp_path):
    eski = tmp_path / "ev" / ".pemf_gui"
    eski.mkdir(parents=True)
    (eski / "config.json").write_text(json.dumps({"mqtt": {"broker": "eski.local"}}), encoding="utf-8")
    (eski / ".pemf_key_v2").write_text("ESKI-ANAHTAR", encoding="utf-8")
    yeni = tmp_path / "pd" / "PEMF_GUI"
    yeni.mkdir(parents=True)
    (yeni / ".pemf_key_v2").write_text("YENI-ANAHTAR", encoding="utf-8")
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "pd"))
    m = cfg.ConfigManager()
    assert json.loads((yeni / "config.json").read_text(encoding="utf-8"))["mqtt"]["broker"] == "eski.local"
    assert (yeni / ".pemf_key_v2").read_text(encoding="utf-8") == "YENI-ANAHTAR", "kanonik dizindeki anahtar EZİLDİ"
    assert (eski / "config.json").exists() and (eski / ".pemf_key_v2").exists(), "eski dosya silindi (veri kaybı)"
    assert yeni / "config.json" in ortam, "taşınan düz-metin config kilitlenmedi"
    assert Path(m.config_dir) == yeni


def test_tasima_kilidi_ya_da_kopyasi_DUSERSE_acilis_SURER(ortam, monkeypatch, tmp_path, caplog):
    eski = tmp_path / "ev" / ".pemf_gui"
    eski.mkdir(parents=True)
    (eski / ".pemf_key").write_bytes(b"x")
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "pd"))
    monkeypatch.setattr(fa, "lock_down_file", lambda *a, **k: (_ for _ in ()).throw(OSError("icacls yok")))
    cfg.ConfigManager()
    assert (tmp_path / "pd" / "PEMF_GUI" / ".pemf_key").exists(), "kilit düşünce kopya geri alındı / yapılmadı"
    import shutil

    (eski / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(shutil, "copy2", lambda *a, **k: (_ for _ in ()).throw(OSError("disk dolu")))
    with caplog.at_level(logging.WARNING, logger=cfg.logger.name):
        cfg.ConfigManager()
    assert any("ileri-tasima atlandi" in r.getMessage() for r in caplog.records)


def test_KRITIK_birincil_anahtar_ALINAMAZSA_ya_da_BOSSA_fail_closed_yeni_anahtar_URETILMEZ(
    ortam, monkeypatch, tmp_path, caplog
):
    m = cfg.ConfigManager(str(tmp_path / "c" / "config.json"))
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: "")
    with pytest.raises(RuntimeError, match="bos dondu"):
        m._anahtar_hazirla()
    assert m._cipher is None
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: (_ for _ in ()).throw(OSError("sır dizinine erişim yok")))
    monkeypatch.delattr(sm, "tekrar_kisitli_hata")  # yardımcı yoksa da tam ileti günlüğe düşer
    with caplog.at_level(logging.ERROR, logger=cfg.logger.name):
        with pytest.raises(RuntimeError, match="yeni anahtar URETILMEDI"):
            m._anahtar_hazirla()
    assert any("patient_fernet_key SecretsManager'dan OKUNAMADI" in r.getMessage() for r in caplog.records)
    with pytest.raises(RuntimeError):
        m._encrypt_value("gizli-parola")  # şifrelenemeyen sır düz-metne DÜŞMEZ


def test_eski_cozucu_bozuk_pemf_key_ve_MAC_hatasinda_ATLAR(ortam, monkeypatch, tmp_path):
    d = tmp_path / "c"
    (d / ".pemf_key").mkdir(parents=True)  # dosya yerine DİZİN → okunamaz
    m = cfg.ConfigManager(str(d / "config.json"))
    assert m._legacy_cipher is not None, "MAC-türevli eski anahtar kurulmadı (eski hasta alanları okunamaz)"
    import uuid

    monkeypatch.setattr(uuid, "getnode", lambda: (_ for _ in ()).throw(OSError("NIC yok")))
    assert m._get_legacy_cipher() is None


def test_bos_deger_sifrelenmez_base64_olmayan_deger_COZULMEDEN_doner(ortam, tmp_path):
    m = cfg.ConfigManager(str(tmp_path / "c" / "config.json"))
    assert m._encrypt_value("") == ""
    assert m._decrypt_value("abc") == "abc" and m._decrypt_value("") == ""  # bozuk dolgu / boş → çözülmeden döner
    m.set("mqtt.pass", "parola-1", save=False)
    assert m.config["mqtt"]["pass"].startswith("enc:") and m.get("mqtt.pass") == "parola-1"
    m.config["mqtt"]["user"] = "duz-kullanici"  # şifreli olmayan (eski) değer olduğu gibi döner
    assert m.get("mqtt.user") == "duz-kullanici"


def test_duz_metin_sir_gocu_sifreleme_ya_da_kayit_DUSERSE_acilis_SURER(ortam, monkeypatch, tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "config.json").write_text(json.dumps({"mqtt": {"pass": "duz-parola"}}), encoding="utf-8")
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("anahtar çözülemez")))
    m = cfg.ConfigManager(str(d / "config.json"))  # şifreleme düşer → değer DOKUNULMADAN kalır, istisna yok
    assert m.config["mqtt"]["pass"] == "duz-parola"
    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: "uR0pZ1f2x7L3c7p0bS3oE5qJ8m4vN6tY9aK2hW1dG0s=")
    gercek_yaz = cfg.config_json_yaz
    monkeypatch.setattr(cfg, "config_json_yaz", lambda *a, **k: (_ for _ in ()).throw(OSError("disk dolu")))
    m2 = cfg.ConfigManager(str(d / "config.json"))  # şifrelendi ama kayıt düştü → açılış SÜRER
    assert m2.config["mqtt"]["pass"].startswith("enc:")
    assert json.loads((d / "config.json").read_text(encoding="utf-8"))["mqtt"]["pass"] == "duz-parola"
    monkeypatch.setattr(cfg, "config_json_yaz", gercek_yaz)
    cfg.ConfigManager(str(d / "config.json"))  # kayıt çalışınca düz-metin sır DİSKTE şifreli olur
    diskte = json.loads((d / "config.json").read_text(encoding="utf-8"))["mqtt"]["pass"]
    assert diskte.startswith("enc:") and "duz-parola" not in diskte, "düz-metin MQTT parolası diskte kaldı"
