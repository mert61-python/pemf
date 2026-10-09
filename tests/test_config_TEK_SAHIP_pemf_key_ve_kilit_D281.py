# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.81 (B-3.40 · B-3.41) — A-29: `config.json`un TEK sahibi `pemf_gui` ConfigManager; ProductionConfigManager (PCM, `/api/settings`)
ona BAĞLANIR (sahibin anahtarı, sahibin TEK okuyucu / atomik yazıcı / kilidi), yazım atomik.

B-3.40: PCM ortak veri dizinine (`<PEMF_DATA_DIR>\\PEMF_GUI`) `.pemf_key` YOKSA rastgele anahtar YAZIYORDU. Sahibin eski-anahtar
zinciri o dosya varsa YALNIZ onu, yoksa MAC-türevli anahtarı deniyordu → PCM'in ilk açılışından sonra MAC-türevli anahtarla şifrelenmiş
ESKİ hasta alanları (ad / sahip) "[okunamayan kayıt]" görünür (veri durur, geri alınabilir).
B-3.41: PCM kaydettiği `config.json`u `lock_down_file(…)` (varsayılan: yalnız SYSTEM + Administrators) ile kilitliyordu → yükseltilmemiş
(launcher) backend ikinci açılıştan itibaren KENDİ config dosyasını okuyamaz; `POST /api/settings` "success" der ama disk değişmez.
Ayrıca iki yönetici aynı alanı AYRI anahtarlarla şifreliyordu: sahibin `patient_fernet_key` ile yazdığı `mqtt.pass` PCM'den şifreli
metin olarak dönüyordu.

Arıza GERÇEK biçimiyle: MAC-türevli anahtarla şifreli gerçek alan + GERÇEK `ProductionConfigManager()` + yeni `ConfigManager`;
yükseltilmemiş süreçte (Administrators yalnız "deny only") GERÇEK `lock_down_file` + GERÇEK `/api/settings` ucu; okunamayan dosya
gerçek bozuk baytlarla. `finally`de `icacls /reset /T` (kalan kilit tmp temizliğini engellemesin).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import uuid

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

SIR = "SAHTE-MQTT-D281-bir"
SIR2 = "SAHTE-MQTT-D281-iki"


def _mac_ile_sifrele(metin: str) -> str:
    """Eski sürümlerin MAC-türevli anahtarıyla (sha256(uuid.getnode())) yazılmış alan — `_encrypt_value` biçimi (b64(Fernet))."""
    anahtar = base64.urlsafe_b64encode(hashlib.sha256(str(uuid.getnode()).encode()).digest())
    return base64.urlsafe_b64encode(Fernet(anahtar).encrypt(metin.encode())).decode()


def _sifirla(yol) -> None:
    if os.name == "nt":
        subprocess.run(["icacls", str(yol), "/reset", "/T", "/C"], capture_output=True, timeout=60)


def _okunur_mu(yol) -> bool:
    try:
        open(yol, "rb").close()
        return True
    except PermissionError:
        return False


def _dacl_sidleri(yol) -> set[str]:
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", f"(Get-Acl -LiteralPath '{yol}').Sddl"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0 and "D:" in r.stdout, f"aparat: SDDL okunamadı: {r.stdout}{r.stderr}"
    dacl = r.stdout.split("D:", 1)[1].split("S:", 1)[0]
    return {m.group(1) for m in re.finditer(r"\(A;[^;()]*;[^;()]*;[^;()]*;[^;()]*;([^;()]+)\)", dacl)}


@pytest.fixture()
def veri(tmp_path):
    """Ortak veri dizini (`<PEMF_DATA_DIR>\\PEMF_GUI` modeli): PCM'in app-data dizini = sahibin config dizini."""
    d = tmp_path / "PEMF_GUI"
    d.mkdir()
    yield d
    _sifirla(d)


@pytest.fixture()
def pcm_uret(veri, monkeypatch):
    from utils import production_config_manager as pcm

    monkeypatch.setattr(pcm.ProductionConfigManager, "_get_app_data_dir", lambda self: veri)
    monkeypatch.setattr(pcm, "_global_config", None)

    def _uret():
        pcm.ProductionConfigManager._instance = None
        pcm._global_config = None
        return pcm.get_production_config()

    monkeypatch.setattr(pcm.ProductionConfigManager, "_instance", None)
    return _uret


@pytest.fixture()
def sahip_uret(veri, monkeypatch):
    """Sahip = süreç-geneli `pemf_gui.config.config` (PCM onu `get_config()` ile kullanır — üründe TEK örnek). Her çağrı test veri
    dizinine bağlı YENİ sahibi kurar ve TEKİL olarak yerleştirir. Ayrı örnek kurmak, önceki bir testin tekilde önbelleğe aldığı
    şifreleyiciyle ayrışıyordu (kapanış tam süitinde ölçüldü: PCM, sahibin şifrelediği `mqtt.pass`i çözemedi — tek başına yeşil)."""
    from pemf_gui import config as sahip_modulu

    def _uret():
        m = sahip_modulu.ConfigManager(config_file=str(veri / "config.json"))
        monkeypatch.setattr(sahip_modulu, "config", m)
        return m

    return _uret


@pytest.fixture()
def acl_kaydedici(monkeypatch):
    """ACL bu kolların konusu değil (B-3.41 kolları GERÇEK kilitle ayrıca ölçülür): kilit kaydedilir, uygulanmaz."""
    import utils.file_acl as fa

    monkeypatch.setattr(fa, "lock_down_file", lambda *a, **k: True)


@pytest.fixture()
def istemci(veri, monkeypatch, pcm_uret):
    from servers import api_server, settings_router

    monkeypatch.setattr(settings_router, "_settings_file", veri / "system_settings.json")
    return TestClient(api_server.app, client=("127.0.0.1", 51234))


@pytest.fixture()
def yukseltilmemis(tmp_path):
    """Aparat: bu süreç YÜKSELTİLMEMİŞ olmalı — yalnız SYSTEM + Administrators kilidi onu GERÇEKTEN dışarıda bırakmalı."""
    if os.name != "nt":
        pytest.skip("NTFS ACL yalnız Windows")
    from utils.file_acl import lock_down_file

    sonda = tmp_path / "sonda.txt"
    sonda.write_text("x", encoding="utf-8")
    try:
        assert lock_down_file(sonda) is True, "aparat: sonda kilitlenemedi"
        if _okunur_mu(sonda):
            pytest.skip("süreç YÜKSELTİLMİŞ (Administrators etkin) — yükseltilmemiş backend kolu bu ortamda ölçülemez")
    finally:
        _sifirla(sonda)


# ── B-3.40: PCM `.pemf_key` ÜRETMEZ; eski MAC-türevli alanlar okunur ─────────────────────────────────────────────────────


def test_KRITIK_PCM_pemf_key_URETMEZ_MAC_turevli_ESKI_alan_OKUNUR_D281(veri, pcm_uret, sahip_uret, acl_kaydedici):
    alan = _mac_ile_sifrele("Pamuk")
    pcm_uret()  # GERÇEK PCM örneği (cihazın /api/settings ile ilk açılışı)
    assert not (veri / ".pemf_key").exists(), "PCM ortak veri dizinine RASTGELE .pemf_key YAZDI"
    assert sahip_uret()._decrypt_value(alan) == "Pamuk", "MAC-türevli eski hasta alanı PCM'den sonra ÇÖZÜLEMİYOR"


def test_KRITIK_1950_PCMin_biraktigi_pemf_key_VARKEN_de_MAC_turevli_alan_OKUNUR_D281(veri, sahip_uret, acl_kaydedici):
    """Sahada 1.9.50'nin PCM'i `.pemf_key`i ZATEN yazmış olabilir: güncellemeden sonra eski alanlar yeniden okunmalı ve o dosyayla
    yazılmış eski değerler (PCM'in `mqtt.pass`i) de okunmaya devam etmeli."""
    rastgele = Fernet.generate_key()
    (veri / ".pemf_key").write_bytes(rastgele)
    eski_pcm_degeri = base64.urlsafe_b64encode(Fernet(rastgele).encrypt(SIR.encode())).decode()
    sahip = sahip_uret()
    assert sahip._decrypt_value(_mac_ile_sifrele("Pamuk")) == "Pamuk", (
        ".pemf_key varken MAC-türevli eski hasta alanı ÇÖZÜLEMİYOR ('[okunamayan kayıt]')"
    )
    assert sahip._decrypt_value(eski_pcm_degeri) == SIR, "eski PCM'in .pemf_key ile yazdığı değer artık okunmuyor"


# ── A-29: tek anahtar — sahip ve PCM birbirinin yazdığını okur ────────────────────────────────────────────────────────────


def test_KRITIK_sahibin_sifreledigi_mqtt_pass_PCMden_COZULUR_ve_tersi_D281(pcm_uret, sahip_uret, acl_kaydedici):
    sahip_uret().set("mqtt.pass", SIR)  # sahibin anahtarıyla (ör. açılıştaki düz-metin sır göçü)
    m = pcm_uret()
    assert m.get("mqtt.pass") == SIR, "PCM sahibin şifrelediği mqtt.pass'i ÇÖZEMEDİ (şifreli metin döndü)"
    m.set("mqtt.pass", SIR2)
    assert sahip_uret().get("mqtt.pass") == SIR2, "sahip PCM'in şifrelediği mqtt.pass'i ÇÖZEMEDİ"


# ── B-3.41: yükseltilmemiş backend KENDİ config dosyasını okur; POST diske yansır ──────────────────────────────────────────


def test_KRITIK_yukseltilmemis_surec_KENDI_config_dosyasini_OKUR_POST_diske_yansir_D281(
    veri, pcm_uret, istemci, yukseltilmemis
):
    pcm_uret().set("mqtt.broker_url", "192.168.10.5")  # GERÇEK lock_down_file
    assert _okunur_mu(veri / "config.json"), (
        "kaydeden süreç KENDİ config.json'unu okuyamıyor (yalnız SYSTEM + Administrators)"
    )
    assert pcm_uret().get("mqtt.broker_url") == "192.168.10.5", "yeni PCM örneği (ikinci açılış) ayarı OKUYAMADI"

    r = istemci.post("/api/settings/", json={"mqtt_broker": "10.0.0.7"})
    assert r.status_code == 200, r.text
    disk = json.loads((veri / "config.json").read_text(encoding="utf-8"))
    assert disk["mqtt"]["broker_url"] == "10.0.0.7", "POST /api/settings 'success' dedi ama disk DEĞİŞMEDİ"
    sidler = _dacl_sidleri(veri / "config.json")
    assert not ({"BU", "AU", "S-1-5-32-545", "S-1-5-11"} & sidler), (
        f"Users / Authenticated Users config'e açık: {sidler}"
    )


def test_KRITIK_1950in_KILITLEDIGI_kendi_config_dosyasi_guncellemede_ACILIR_Users_DISARIDA_D281(
    veri, pcm_uret, yukseltilmemis
):
    """1.9.50 yükseltilmemiş backend'in kendi dosyasını yalnız SYSTEM + Administrators'a kilitlediği hâl (sahibi bu hesap):
    güncellemeden sonraki ilk okuma kilidi süreç hesabı korunarak onarmalı; Users yine dışarıda."""
    from utils.file_acl import lock_down_file

    hedef = veri / "config.json"
    hedef.write_text(json.dumps({"mqtt": {"broker_url": "192.168.50.5", "broker_port": 1883}}), encoding="utf-8")
    assert lock_down_file(hedef) is True, "aparat: 1.9.50 kilidi kurulamadı"
    assert not _okunur_mu(hedef), "aparat: kilit okumayı engellemiyor"
    assert pcm_uret().get("mqtt.broker_url") == "192.168.50.5", (
        "1.9.50'nin kilitlediği KENDİ config dosyası güncellemeden sonra hâlâ OKUNAMIYOR (ayarlar varsayılana döndü)"
    )
    sidler = _dacl_sidleri(hedef)
    assert not ({"BU", "AU", "S-1-5-32-545", "S-1-5-11"} & sidler), f"onarım Users'ı içeri aldı: {sidler}"


# ── okunamayan config: kayıt reddi SESSİZ değil ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_okunamayan_config_POST_503_EYLEM_soyler_disk_ve_ayarlar_DEGISMEZ_D281(veri, istemci, acl_kaydedici):
    hedef = veri / "config.json"
    hedef.write_bytes(b'{"mqtt": {"broker_url": "192.168.1.9", BOZUK')
    once = hedef.read_bytes()
    r = istemci.post("/api/settings/", json={"mqtt_broker": "10.0.0.8", "clinic_name": "Klinik D281"})
    assert r.status_code == 503, f"okunamayan config'e kayıt REDDEDİLDİ ama uç {r.status_code} dedi: {r.text[:200]}"
    assert "KAYDEDILMEDI" in r.text and "Yapilacak" in r.text, f"ret eylem söylemiyor: {r.text[:300]}"
    assert hedef.read_bytes() == once, "okunamayan config.json EZİLDİ"
    assert not (veri / "system_settings.json").exists(), "kısmi kayıt: config reddedildi ama klinik adı yazıldı"


def test_KARSIT_okunamayan_configde_MQTT_degismiyorsa_klinik_adi_KAYDEDILIR_D281(veri, istemci, acl_kaydedici):
    """Karşıt: MQTT alanı değişmeyen POST (yalnız klinik adı) reddedilmez — config okunamıyor diye HER kayıt düşmesin."""
    hedef = veri / "config.json"
    hedef.write_bytes(b"{BOZUK")
    once = hedef.read_bytes()
    r = istemci.post("/api/settings/", json={"clinic_name": "Klinik D281"})
    assert r.status_code == 200, r.text
    assert json.loads((veri / "system_settings.json").read_text(encoding="utf-8"))["clinic_name"] == "Klinik D281"
    assert hedef.read_bytes() == once


# ── sahibin yazımı: fail-closed + atomik ─────────────────────────────────────────────────────────────────────────────────


def test_KRITIK_sahip_okunamayan_configi_VARSAYILANLARLA_EZMEZ_D281(veri, sahip_uret, acl_kaydedici):
    hedef = veri / "config.json"
    hedef.write_bytes(b'{"serial": {"port": "COM7"}, BOZUK')
    once = hedef.read_bytes()
    sahip = sahip_uret()
    with pytest.raises(Exception) as hata:
        sahip.set("serial.port", "COM9")
    assert type(hata.value).__name__ == "ConfigKaydiReddedildi", repr(hata.value)
    assert hedef.read_bytes() == once, "sahip okunamayan config.json'u VARSAYILANLARLA EZDİ"


def test_KRITIK_sahibin_yazimi_YARIDA_duserse_config_ESKI_baytlarla_kalir_D281(
    veri, sahip_uret, acl_kaydedici, monkeypatch
):
    sahip = sahip_uret()
    sahip.set("serial.port", "COM7")
    hedef = veri / "config.json"
    once = hedef.read_bytes()

    def _yarim(obj, fp, *a, **k):
        metin = json.dumps(obj, *a, **k)
        fp.write(metin[: len(metin) // 2])
        fp.flush()
        raise OSError(28, "No space left on device (sahte: disk YARIDA doldu)")

    gercek_dump = json.dump
    monkeypatch.setattr(json, "dump", _yarim)
    with pytest.raises(OSError):
        sahip.set("serial.port", "COM9")
    monkeypatch.setattr(json, "dump", gercek_dump)
    assert hedef.read_bytes() == once, "sahibin yarıda kalan yazımı config.json'u BOZDU"
