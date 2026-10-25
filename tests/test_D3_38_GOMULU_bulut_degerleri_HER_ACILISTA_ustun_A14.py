# Author: mertaygn, cglrgrkn
"""D3.38 (B-3.103) · A-14 — pakete gömülü / ortam bulut değerleri HER AÇILIŞTA `pemf_secrets.json`'daki ilk kopyanın üstündedir.

ÖLÇÜLEN (HEAD): `get_secret('mqtt_cloud_host')` gömülü provizyonu yalnız dosyada YOKKEN taşıyordu; provizyon değişince (rotasyon /
yeni sürüm) dosyadaki ESKİ değer dönmeye devam ediyordu — aynısı gömülü Supabase adresi / anahtarı için. SÖZLEŞME (A-14): kaynak
(env → paket) doluysa o döner ve dosya güncellenir; kaynak boşsa dosyadaki değer korunur; parola makineye bağlı sarılı yazılır.
İzole geçici kök + geçici provizyon dosyası; gerçek kasa / veri kökü AÇILMAZ; sır değeri basılmaz.
"""

from __future__ import annotations

import json
import secrets

import pytest


@pytest.fixture
def sm(monkeypatch, tmp_path):
    import utils.secrets_manager as s

    monkeypatch.setattr(s, "_data_dir", lambda: tmp_path)
    monkeypatch.setattr(s, "_cache", None)
    prov = tmp_path / "cloud_mqtt_provision.json"
    monkeypatch.setenv("PEMF_CLOUD_PROVISION_PATH", str(prov))
    for k in ("PEMF_MQTT_CLOUD_HOST", "PEMF_MQTT_CLOUD_PASS", "SUPABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    yield s, prov
    s._cache = None


def test_KRITIK_D3_38_provizyon_DEGISINCE_yeni_deger_doner_dosya_guncellenir(sm):
    s, prov = sm
    prov.write_text(json.dumps({"mqtt_cloud_host": "eski.hivemq.cloud"}), encoding="utf-8")
    assert s.get_secret("mqtt_cloud_host") == "eski.hivemq.cloud"
    prov.write_text(json.dumps({"mqtt_cloud_host": "yeni.hivemq.cloud"}), encoding="utf-8")
    s._cache = None
    assert s.get_secret("mqtt_cloud_host") == "yeni.hivemq.cloud", (
        "rotasyon sahaya ulaşmadı (dosyadaki eski değer döndü)"
    )
    assert (
        json.loads(s.secrets_path().read_text(encoding="utf-8"))["operator"]["mqtt_cloud_host"] == "yeni.hivemq.cloud"
    )


def test_KRITIK_D3_38_parola_rotasyonu_SARILI_yazilir(sm):
    s, prov = sm
    eski, yeni = secrets.token_hex(8), secrets.token_hex(8)
    prov.write_text(json.dumps({"mqtt_cloud_pass": eski}), encoding="utf-8")
    assert s.get_secret("mqtt_cloud_pass") == eski
    prov.write_text(json.dumps({"mqtt_cloud_pass": yeni}), encoding="utf-8")
    s._cache = None
    assert s.get_secret("mqtt_cloud_pass") == yeni
    metin = s.secrets_path().read_text(encoding="utf-8")
    assert yeni not in metin and eski not in metin, "parola dosyada düz"


def test_KRITIK_D3_38_gomulu_supabase_adresi_dosyadaki_ESKININ_ustunde(sm, monkeypatch):
    s, _ = sm
    s.secrets_path().write_text(
        json.dumps({"embedded": {"supabase_url": "https://eski-proje.supabase.co"}}), encoding="utf-8"
    )
    s._cache = None
    monkeypatch.setenv("SUPABASE_URL", "https://yeni-proje.supabase.co")  # yeni sürümün değeri
    assert s.get_secret("supabase_url") == "https://yeni-proje.supabase.co"


def test_KARSIT_D3_38_kaynak_BOSKEN_dosyadaki_deger_korunur(sm):
    s, prov = sm
    s.secrets_path().write_text(json.dumps({"operator": {"mqtt_cloud_host": "elle.girilen.host"}}), encoding="utf-8")
    s._cache = None
    assert not prov.exists()
    assert s.get_secret("mqtt_cloud_host") == "elle.girilen.host"
