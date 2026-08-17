# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""OKUNAMAYAN `config.json` VARSAYILANLARLA SESSİZCE EZİLİYORDU (denetim 2026-08-17).

`ProductionConfigManager`, kullanıcı config'i diskte VAR ama YÜKLENEMEZSE (izin reddi, bozuk JSON,
disk hatası) yalnızca bir hata logluyor ve **varsayılanlarla devam ediyordu**. Bellekteki config
artık yalnız bundled+template varsayılanlarıdır; sonraki İLK `save()` o varsayılanları diske yazıp
kullanıcının override'larını SESSİZCE siliyordu.

GERÇEK SENARYO: `backend_service` `config.json`u SYSTEM+Admin ACL'ine kilitliyor. Süreç sonradan
yetkisiz bir kullanıcıyla koşarsa (servis hesabı değişimi, elle çalıştırma) okuma düşer ve ilk
kayıt klinik ayarlarını siler → `mqtt.broker_url` `localhost`a döner → **ESP bobinleri (6-8)
broker'ı bulamaz**, tedavi başlatılamaz.

⚠️ BU BULGU KAZA ESERİ ÖLÇÜLDÜ: denetim sırasında pytest DIŞINDA çalıştırılan bir tanı komutu bu
makinenin gerçek `%APPDATA%\\PEMF_GUI\\config.json` dosyasını tam olarak bu yolla ezdi — "okuyamıyorum"
hatası "yazamıyorum" anlamına GELMİYOR: dosya ACL'li olsa da DİZİN yazılabilir olduğu için
`tmp + os.replace` başarılı oluyor.

⚠️ Bu, bozuk `pemf_secrets.json` bulgusunun (sessizce YENİ SQLCipher anahtarı üretme) AYNI SINIFI
ve çözümü de aynı: FAIL-CLOSED + operatöre iki açık çıkış yolu.
"""

import json
import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest


@pytest.fixture()
def yonetici(tmp_path, monkeypatch):
    """Yeni bir `ProductionConfigManager` örneği; app-data tmp'ye yönlendirilmiş.

    ⚠️ Singleton `get_production_config()` KULLANILMAZ: o, süreç ömrü boyunca tek örnek tutar ve
    başka bir testin/tanı komutunun bıraktığı durumu taşır."""
    from utils import production_config_manager as pcm

    monkeypatch.setattr(pcm.ProductionConfigManager, "_get_app_data_dir", lambda self: tmp_path)

    # ⚠️ Şifreleme kurulumu devre dışı: `.pemf_key` üretip onu ACL ile kilitliyor ve sonraki
    # testler tmp dizinini temizleyemiyor (PermissionError). Bu testin konusu ŞİFRELEME DEĞİL,
    # okunamayan config'in EZİLMEMESİ.
    monkeypatch.setattr(pcm.ProductionConfigManager, "_setup_encryption", lambda self: None)

    # ⚠️ ACL sertleştirmesi de devre dışı: `_save_user_config` yazdığı dosyayı SYSTEM+Admin'e
    # kilitliyor ve test onu GERİ OKUYAMIYOR. (Bu kilit, gerçek kazanın da sebebiydi: dosya
    # okunamaz ama DİZİN yazılabilir kaldığı için `os.replace` başarılı oluyor.)
    import utils.file_acl as _acl

    monkeypatch.setattr(_acl, "lock_down_file", lambda *a, **k: None)

    # ⚠️ SINGLETON SIFIRLANIR: sınıf `__new__` ile tek örnek paylaşıyor. Sıfırlanmazsa bu test,
    # süitin daha önce (gerçek app-data diziniyle) kurduğu örneği miras alır ve tmp'deki dosyayı
    # hiç yüklemez — izole koşuda YEŞİL, tam süitte KIRMIZI olurdu (ölçüldü).
    monkeypatch.setattr(pcm.ProductionConfigManager, "_instance", None)
    return pcm


def _yonetici_uret(pcm):
    """Taze örnek (fixture `_instance`i sıfırladığı için `__new__` yeni nesne üretir)."""
    y = pcm.ProductionConfigManager()
    assert y._get_app_data_dir().name.startswith("test_"), f"app-data tmp'ye yonlendirilmedi: {y._get_app_data_dir()}"
    return y


def test_KRITIK_okunamayan_config_VARSAYILANLARLA_EZILMEZ(yonetici, tmp_path):
    """Bozuk/okunamayan `config.json` diskte AYNEN kalmalı."""
    hedef = tmp_path / "config.json"
    hedef.write_text("{BU GECERLI JSON DEGIL", encoding="utf-8")
    once = hedef.read_bytes()

    y = _yonetici_uret(yonetici)

    # Yükleme düştüğü için bellekteki config VARSAYILANLARDIR — kaydetmek dosyayı yok ederdi.
    y.set("mqtt.broker_url", "localhost", save=False)
    y.save()

    assert hedef.read_bytes() == once, (
        "okunamayan config.json VARSAYILANLARLA EZILDI -> klinik override'lari (MQTT broker/port) "
        "sessizce yok oldu; ESP bobinleri (6-8) broker'i bulamaz"
    )


def test_KARSIT_KANIT_okunabilir_config_NORMAL_kaydedilir(yonetici, tmp_path):
    """Yama "hiç kaydetme"ye dönüşmemeli — sağlam dosyada yazma çalışmaya devam etmeli."""
    hedef = tmp_path / "config.json"
    hedef.write_text(json.dumps({"mqtt": {"broker_url": "192.168.137.1", "broker_port": 1883}}), encoding="utf-8")

    y = _yonetici_uret(yonetici)
    assert y.get("mqtt.broker_url") == "192.168.137.1", "saglam config YUKLENMEDI"

    y.set("mqtt.broker_url", "10.0.0.9", save=False)
    y.save()

    assert json.loads(hedef.read_text(encoding="utf-8"))["mqtt"]["broker_url"] == "10.0.0.9", (
        "saglam config'e yazma BOZULDU"
    )


def test_KARSIT_KANIT_config_YOKSA_olusturulur(yonetici, tmp_path):
    """İlk kurulum yolu bozulmamalı: dosya HİÇ yoksa oluşturulmaya devam etmeli."""
    hedef = tmp_path / "config.json"
    assert not hedef.exists()

    y = _yonetici_uret(yonetici)
    y.set("mqtt.broker_url", "10.0.0.5", save=False)
    y.save()

    assert hedef.exists(), "ilk kurulumda config.json OLUSTURULMADI"
    assert json.loads(hedef.read_text(encoding="utf-8"))["mqtt"]["broker_url"] == "10.0.0.5"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
