# -*- coding: utf-8 -*-
"""KP-1 · `utils/secrets_manager.py` · sözleşmeler: KRİTİK anahtar şifrelenemezse düz-metin diske ASLA yazılmaz (fail-closed), kritik
olmayan düz saklanır · makineye bağlı sarma Linux machine-id / macOS IOPlatformUUID ile ve kimlik yoksa fail-closed · veri kökü çözücüsü
düşerse PEMF_DATA_DIR → APPDATA · dizin ACL kilidi düşerse geri çekilme süresi boyunca yeniden denenmez · bozuk dosya kenara alınamazsa
ileti GERÇEĞİ söyler · atomik yazım düşerse yetim .tmp kalmaz ve önbellek değişmez · paket / ortam kaynağı (A-14) okunamazsa dosya
otoritedir, dosyadaki değer çözülemiyorsa kaynak yazılır · eski kaynak okuyucuları (keyring, dosya) patlarsa boş sayılır · üreteçlerin
biçimi · bilinmeyen anahtar KeyError (hiçbir şey yazılmaz).

Gerçek kasa / keyring / cmdkey / gerçek veri kökü YOK: veri kökü ve makine deposu `tmp_path`; DPAPI sınırı (`_dpapi`), ACL (`utils.file_acl`),
süreç (`subprocess.run`) ve platform (`platform.system`) EN ALT katta sahte. Modül süreç geneli durumu (önbellek, ACL bayrağı) geri konur.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import utils.file_acl as fa
import utils.secrets_manager as sm


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    veri = tmp_path / "veri"
    (veri / "PEMF_GUI").mkdir(parents=True)
    monkeypatch.setenv("PEMF_DATA_DIR", str(veri))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine"))
    for ad in (
        "PEMF_API_TOKEN",
        "PEMF_MASTER_SECRET",
        "PEMF_MQTT_CLOUD_HOST",
        "PEMF_MQTT_CLOUD_PASS",
        "PEMF_CLOUD_PROVISION_PATH",
        "PEMF_SQLCIPHER_KEY",
        "PEMF_DEVICE_REGISTRY_SECRET",
    ):
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.setattr(sm, "_cache", None)
    monkeypatch.setattr(sm, "_dir_hardened", True)  # dizin ACL'i yalnız ilgili testte
    monkeypatch.setattr(sm, "_sertlestirme_sonraki", 0.0)
    kilit: list = []
    monkeypatch.setattr(fa, "lock_down_file", lambda p, **k: kilit.append(Path(p)) or True)
    monkeypatch.setattr(fa, "lock_down_dir", lambda p, **k: True)
    return SimpleNamespace(veri=sm._data_dir(), kilit=kilit, tmp=tmp_path)


def _dosya():
    p = sm.secrets_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _dpapi_dusur(monkeypatch):
    monkeypatch.setattr(sm, "_is_windows", lambda: True)
    monkeypatch.setattr(sm, "_dpapi", lambda veri, koru: (_ for _ in ()).throw(OSError("CryptProtectData 0x8009000B")))


# ───────────────────────── şifreleme sınırları ─────────────────────────


def test_KRITIK_DPAPI_dusunce_kritik_anahtar_DUZ_YAZILMAZ_kritik_olmayan_duz_saklanir(ortam, monkeypatch, caplog):
    """DPAPI hatası → kritik (sqlcipher_key) RuntimeError, dosyada anahtar YOK; kritik olmayan değer düz döner + uyarı."""
    _dpapi_dusur(monkeypatch)
    with pytest.raises(RuntimeError, match="fail-closed"):
        sm._enc("gizli", critical=True)
    with caplog.at_level(logging.WARNING, logger=sm.logger.name):
        assert sm._enc("gizli", critical=False) == "gizli"
    assert any("DPAPI sifreleme yapilamadi" in r.getMessage() for r in caplog.records)
    with pytest.raises(RuntimeError):
        sm.get_secret("sqlcipher_key")
    d = _dosya()
    assert not (d or {}).get("auto", {}).get("sqlcipher_key"), "kritik hasta DB anahtarı düz-metin diske yazıldı"
    assert not (sm._cache or {}).get("auto", {}).get("sqlcipher_key"), "yazılamayan anahtar önbellekte kaldı"


def test_KRITIK_Linux_makine_kimligiyle_sarar_BASKA_makinede_cozulmez_kimlik_YOKSA_fail_closed(
    ortam, monkeypatch, caplog, tmp_path
):
    monkeypatch.setattr(sm, "_is_windows", lambda: False)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    kimlik = tmp_path / "machine-id"
    kimlik.write_text("a1b2c3\n", encoding="utf-8")
    monkeypatch.setattr(sm, "MAKINE_KIMLIGI_YOLLARI", (str(tmp_path / "yok"), str(kimlik)))
    s = sm._enc("hasta-anahtari", critical=True)
    assert s.startswith(sm._MKEY_PREFIX) and "hasta-anahtari" not in s
    assert sm._dec(s) == "hasta-anahtari"
    kimlik.write_text("baska-makine\n", encoding="utf-8")
    with pytest.raises(Exception):
        sm._dec(s)  # başka makinenin kimliğiyle ÇÖZÜLMEZ
    monkeypatch.setattr(sm, "MAKINE_KIMLIGI_YOLLARI", (str(tmp_path / "yok"),))
    with pytest.raises(RuntimeError, match="makine-bagli"):
        sm._enc("x", critical=True)
    with caplog.at_level(logging.WARNING, logger=sm.logger.name):
        assert sm._enc("x", critical=False) == "x"
    assert any("Makine-bagli sifreleme yapilamadi" in r.getMessage() for r in caplog.records)


def test_macOS_kimligi_ioreg_IOPlatformUUID_dan_alinir_ioreg_YOKSA_kimlik_bulunamadi(ortam, monkeypatch):
    import hashlib

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    cagri: list = []

    def _ioreg(argv, **k):
        cagri.append(argv)
        return SimpleNamespace(stdout='+-o J316sAP\n    | "IOPlatformUUID" = "UUID-1234-ABCD"\n')

    monkeypatch.setattr(subprocess, "run", _ioreg)
    assert sm._machine_secret() == hashlib.sha256(b"PEMF-secrets-v1:UUID-1234-ABCD").digest()
    assert cagri and cagri[0][0] == "ioreg"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("ioreg")))
    with pytest.raises(RuntimeError, match="makine kimliği bulunamadı"):
        sm._machine_secret()


# ───────────────────────── veri kökü · ACL ─────────────────────────


def test_veri_koku_cozucusu_DUSERSE_PEMF_DATA_DIR_sonra_APPDATA(ortam, monkeypatch, tmp_path):
    import utils.path_utils as pu

    monkeypatch.setattr(pu, "get_app_data_directory", lambda: (_ for _ in ()).throw(RuntimeError("kök çözülemedi")))
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "pd"))
    assert sm._data_dir() == tmp_path / "pd" / "PEMF_GUI" and (tmp_path / "pd" / "PEMF_GUI").is_dir()
    monkeypatch.delenv("PEMF_DATA_DIR")
    monkeypatch.setenv("APPDATA", str(tmp_path / "ad"))
    assert sm._data_dir() == tmp_path / "ad" / "PEMF_GUI" and (tmp_path / "ad" / "PEMF_GUI").is_dir()


def test_dizin_ACL_kilidi_PATLARSA_geri_cekilme_suresince_YENIDEN_denenmez(ortam, monkeypatch, caplog):
    """D2.80: icacls her get_secret'te (küresel kilit altında) yeniden koşmasın; süre dolunca yeniden dener, başarıda bayrak kurulur."""
    monkeypatch.setattr(sm, "_dir_hardened", False)
    saat = {"t": 1000.0}
    monkeypatch.setattr(sm, "time", SimpleNamespace(monotonic=lambda: saat["t"], strftime=lambda *a: "20261101_000000"))
    cagri: list = []

    def _patla(d, **k):
        cagri.append(d)
        raise PermissionError("icacls erişim reddedildi")

    monkeypatch.setattr(fa, "lock_down_dir", _patla)
    with caplog.at_level(logging.WARNING, logger=sm.logger.name):
        sm._ensure_dir_hardened(ortam.veri)
    kayit = next(r for r in caplog.records if "SIR DIZINI ACL kilidi hata verdi" in r.getMessage())
    assert kayit.exc_info and sm._dir_hardened is False and len(cagri) == 1
    saat["t"] += sm._SERTLESTIRME_GERI_CEKILME_SN - 1
    sm._ensure_dir_hardened(ortam.veri)
    assert len(cagri) == 1, "geri çekilme süresi dolmadan icacls yeniden koştu"
    saat["t"] += 2
    monkeypatch.setattr(fa, "lock_down_dir", lambda d, **k: cagri.append(d) or True)
    sm._ensure_dir_hardened(ortam.veri)
    assert len(cagri) == 2 and sm._dir_hardened is True


def test_sir_dosyasi_ACL_kilidi_PATLARSA_yazim_SURER_uyari_zincirli(ortam, monkeypatch, caplog):
    monkeypatch.setattr(fa, "lock_down_file", lambda p, **k: (_ for _ in ()).throw(OSError("icacls yok")))
    with caplog.at_level(logging.WARNING, logger=sm.logger.name):
        sm.set_secret("mqtt_user", "operator1")
    assert _dosya()["operator"]["mqtt_user"] == "operator1"
    kayit = next(r for r in caplog.records if "SIR dosyası ACL kilidi hata verdi" in r.getMessage())
    assert kayit.exc_info


# ───────────────────────── bozuk dosya · atomik yazım ─────────────────────────


def test_KRITIK_bozuk_dosya_KENARA_ALINAMAZSA_yerinde_kalir_ileti_GERCEGI_soyler(ortam, monkeypatch):
    p = sm.secrets_path()
    p.write_text("{bozuk json", encoding="utf-8")
    gercek_replace = Path.replace

    def _kenara_alinamaz(self, hedef):
        if self == p:
            raise PermissionError("dosya kilitli (AV)")
        return gercek_replace(self, hedef)

    monkeypatch.setattr(Path, "replace", _kenara_alinamaz)
    with pytest.raises(RuntimeError) as hata:
        sm.get_secret("sqlcipher_key")
    assert "YERINDE birakildi" in str(hata.value) and "saklandi)" not in str(hata.value), (
        "ileti olmayan bir kopyadan söz ediyor"
    )
    assert p.read_text(encoding="utf-8") == "{bozuk json", "bozuk (şifreli veriyi taşıyan) dosya EZİLDİ"
    assert not list(p.parent.glob("pemf_secrets.json.corrupt.*"))


def test_bayat_tmp_temizlenemezse_UYARIR_yazim_yine_tamamlanir(ortam, monkeypatch, caplog):
    p = sm.secrets_path()
    bayat = p.with_name(f"{p.name}.99999.tmp")
    bayat.write_text("{}", encoding="utf-8")
    gercek_unlink = Path.unlink

    def _bayat_silinmez(self, *a, **k):
        if self == bayat:
            raise PermissionError("ACL")
        return gercek_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", _bayat_silinmez)
    with caplog.at_level(logging.WARNING, logger=sm.logger.name):
        sm.set_secret("tunnel_hostname", "cihaz.ornek")
    assert _dosya()["operator"]["tunnel_hostname"] == "cihaz.ornek"
    assert any("Bayat sir .tmp temizlenemedi" in r.getMessage() for r in caplog.records)
    gercek_glob = Path.glob
    monkeypatch.setattr(
        Path,
        "glob",
        lambda self, desen: (
            (_ for _ in ()).throw(OSError("dizin listelenemiyor"))
            if desen.endswith(".tmp")
            else gercek_glob(self, desen)
        ),
    )
    sm.set_secret("tunnel_hostname", "ikinci.ornek")  # bayat .tmp taraması düşse de yazım TAMAMLANIR
    assert _dosya()["operator"]["tunnel_hostname"] == "ikinci.ornek"


def test_KRITIK_atomik_yer_degistirme_DUSERSE_istisna_yukselir_onbellek_DEGISMEZ(ortam, monkeypatch):
    """D2.45: yazılamayan değer bellekte kalıp hasta DB'sini diske hiç yazılmamış anahtarla şifrelemesin."""
    sm.set_secret("mqtt_user", "eski")
    monkeypatch.setattr(os, "replace", lambda a, b: (_ for _ in ()).throw(PermissionError("AV kilidi")))
    with pytest.raises(PermissionError):
        sm.set_secret("mqtt_user", "yeni")
    assert sm.get_secret("mqtt_user") == "eski" and _dosya()["operator"]["mqtt_user"] == "eski"
    assert not list(sm.secrets_path().parent.glob("*.tmp")), "düz-metin sırlı yetim .tmp kaldı"
    gercek_unlink = Path.unlink
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda self, *a, **k: (
            (_ for _ in ()).throw(PermissionError("x")) if self.suffix == ".tmp" else gercek_unlink(self, *a, **k)
        ),
    )
    with pytest.raises(PermissionError, match="AV kilidi"):  # .tmp de silinemese ASIL hata yükselir
        sm.set_secret("mqtt_user", "yeni2")


# ───────────────────────── A-14 kaynak üstünlüğü · yeniden sarma ─────────────────────────


def test_paket_kaynagi_OKUNAMAZSA_dosyadaki_deger_korunur(ortam, monkeypatch):
    sm.set_secret("mqtt_cloud_host", "dosyadaki.host")
    bolum, dpapi, uretec, _ = sm._REGISTRY["mqtt_cloud_host"]
    monkeypatch.setitem(
        sm._REGISTRY,
        "mqtt_cloud_host",
        (bolum, dpapi, uretec, lambda: (_ for _ in ()).throw(OSError("paket okunamadı"))),
    )
    assert sm.get_secret("mqtt_cloud_host") == "dosyadaki.host"


def test_KRITIK_dosyadaki_deger_COZULEMIYORSA_paket_kaynagi_yazilir(ortam, monkeypatch):
    """Gömülü-üstün anahtar (E-stop bulut aynası parolası): dosyadaki eski değer çözülemiyor → kaynak otorite, dosyaya sarılı yazılır."""
    monkeypatch.setattr(sm, "_is_windows", lambda: True)
    monkeypatch.setattr(sm, "_dpapi", lambda veri, koru: veri[::-1])  # deterministik sahte DPAPI (sar = ters çevir)
    sm.secrets_path().write_text(
        json.dumps({"operator": {"mqtt_cloud_pass": "DPAPI:@@@bozuk-base64@@@"}}), encoding="utf-8"
    )
    monkeypatch.setenv("PEMF_MQTT_CLOUD_PASS", "yeni-parola")
    assert sm.get_secret("mqtt_cloud_pass") == "yeni-parola"
    saklanan = _dosya()["operator"]["mqtt_cloud_pass"]
    assert saklanan.startswith("DPAPI:") and sm._dec(saklanan) == "yeni-parola", "kaynak değeri sarılı yazılmadı"


def test_duz_kritik_anahtar_YENIDEN_SARILAMAZSA_duz_degerle_surer_acilis_kirilmaz(ortam, monkeypatch, caplog):
    sm.secrets_path().write_text(
        json.dumps({"auto": {"sqlcipher_key": "elle-geri-yuklenen-anahtar"}}), encoding="utf-8"
    )
    _dpapi_dusur(monkeypatch)
    with caplog.at_level(logging.WARNING, logger=sm.logger.name):
        assert sm.get_secret("sqlcipher_key") == "elle-geri-yuklenen-anahtar"
    assert any("yeniden sarılamadı" in r.getMessage() for r in caplog.records)
    assert _dosya()["auto"]["sqlcipher_key"] == "elle-geri-yuklenen-anahtar", "sarılamayan anahtar dosyada değiştirildi"


# ───────────────────────── eski kaynaklar · üreteçler · paket provizyonu ─────────────────────────


def test_eski_kaynak_okuyuculari_PATLARSA_bos_sayilir(ortam, monkeypatch):
    import keyring

    monkeypatch.setattr(keyring, "get_password", lambda *a: (_ for _ in ()).throw(RuntimeError("kasa arka ucu yok")))
    assert sm._keyring_get("master_secret") == ""
    assert sm.get_secret("master_secret", default="YOK") == "YOK"
    (ortam.veri / "pairing_code.txt").mkdir()  # dosya yerine DİZİN → okuma düşer
    assert sm._read_file(ortam.veri / "pairing_code.txt") == ""


def test_api_token_eski_APPDATA_konumundan_TASINIR(ortam, monkeypatch, tmp_path):
    (tmp_path / "appdata" / "PEMF_GUI").mkdir(parents=True)
    (tmp_path / "appdata" / "PEMF_GUI" / "api_token.txt").write_text("eski-token-123\n", encoding="utf-8")
    assert sm.get_secret("api_token") == "eski-token-123", "mevcut token korunmadı (eşleşmiş istemciler kopar)"
    assert _dosya()["auto"]["api_token"] == "eski-token-123"


def test_uretec_bicimleri_eslesme_6_yonetici_8_karisik_harf_YOK_cihaz_kimligi_MACten(ortam, monkeypatch):
    import uuid

    izinli = set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")
    kod = sm.get_secret("pairing_code")
    assert len(kod) == 6 and set(kod) <= izinli and sm.get_secret("pairing_code") == kod
    yk = sm.get_secret("admin_reset_code")
    assert len(yk) == 8 and set(yk) <= izinli and not set(yk) & set("0O1IL")
    monkeypatch.setattr(uuid, "getnode", lambda: 0x1A2B3C4D5E6F)
    assert sm.get_secret("device_id") == str(0x1A2B3C4D5E6F)


def test_makine_deposu_SARILI_yazar_AYNI_sirri_okur_bos_deger_yok_sayilir(ortam, monkeypatch):
    monkeypatch.setattr(sm, "_is_windows", lambda: True)
    monkeypatch.setattr(sm, "_dpapi", lambda veri, koru: veri[::-1])  # deterministik sahte DPAPI
    sm._kimlik_deposu_yaz("bulut-sirri-xyz")
    ham = json.loads((sm._cihaz_kimlik_deposu() / sm._KIMLIK_DOSYASI).read_text(encoding="utf-8"))[
        "device_registry_secret"
    ]
    assert ham.startswith("DPAPI:") and "bulut-sirri-xyz" not in ham, "makine deposunda sır düz-metin"
    assert sm._kimlik_deposu_oku() == "bulut-sirri-xyz"
    (sm._cihaz_kimlik_deposu() / sm._KIMLIK_DOSYASI).write_text(
        json.dumps({"device_registry_secret": ""}), encoding="utf-8"
    )
    assert sm._kimlik_deposu_oku() == ""


def test_eski_kaynak_okuyucusu_PATLARSA_yeni_deger_uretilir_acilis_kirilmaz(ortam, monkeypatch):
    bolum, dpapi, uretec, _ = sm._REGISTRY["pairing_code"]
    monkeypatch.setitem(
        sm._REGISTRY,
        "pairing_code",
        (bolum, dpapi, uretec, lambda: (_ for _ in ()).throw(OSError("eski dosya kilitli"))),
    )
    kod = sm.get_secret("pairing_code")
    assert len(kod) == 6 and _dosya()["auto"]["pairing_code"] == kod


def test_donmus_pakette_provizyon_MEIPASS_altindan_okunur_bozuksa_bos(ortam, monkeypatch, tmp_path):
    kok = tmp_path / "_internal"
    (kok / "data").mkdir(parents=True)
    (kok / "data" / "cloud_mqtt_provision.json").write_text(
        json.dumps({"mqtt_cloud_host": " paket.host "}), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(kok), raising=False)
    assert sm._bundled_cloud("mqtt_cloud_host") == "paket.host"
    (kok / "data" / "cloud_mqtt_provision.json").write_text("{bozuk", encoding="utf-8")
    assert sm._bundled_cloud("mqtt_cloud_host") == "", "bozuk provizyon istisna sızdırdı (E-stop bulut aynası düşer)"


def test_bilinmeyen_anahtar_KeyError_ve_toplu_yazimda_HICBIRI_yazilmaz(ortam):
    with pytest.raises(KeyError):
        sm.get_secret("yok_boyle")
    with pytest.raises(KeyError):
        sm.set_secret("yok_boyle", "x")
    with pytest.raises(KeyError):
        sm.set_secrets({"mqtt_user": "u", "yok_boyle": "x"})
    d = _dosya()
    assert d is None or "mqtt_user" not in d.get("operator", {}), "toplu yazımda geçerli anahtar tek başına yazıldı"
