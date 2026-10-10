# -*- coding: utf-8 -*-
"""D2.39 (B-1.12) — "sensör kaydı HER ZAMAN açık" vaadi STM telemetrisiyle de gerçekleşir.

ÖLÇÜLEN KUSUR: sürekli CSV kaydedicinin (`servers/sensor_kaydedici`) TEK çağıranı MQTT (ESP) işleyicisiydi ve o yol `PEMF_ESP_ENABLED`
arkasında. Varsayılan saha yapılandırmasında (ESP kapalı) bobin 6-7'nin sıcaklık / alan ve bobin 1-5'in akım telemetrisi (`STM_TELE` →
`hardware.stm.telemetry`) diske HİÇ yazılmıyor, hata da üretmiyordu (sahip kararı: "kayıt her zaman açık" — Y31).
Düzeltme: STM telemetri işleyicisi aynı kaydediciyi çağırır (yalnız GELEN alanlar — ölçülmeyen alan boş kalır, 0.0 yazılmaz — Y6);
STM'nin işaretli eksen uçları (bipolar / faz kazancının tek taşıyıcısı) ve doygunluk bayrakları CSV'ye yeni sütunlar olarak eklenir; aynı
gün eski başlıkla açılmış dosyaya yeni sütunlu satır yazılmaz (yeni dosya). Kaydedici hatası canlı durumu ASLA bozmaz.
⚠️ `PEMF_SENSOR_LOG_DIR` klonun TEMP'inde (masaüstü ya da cwd DEĞİL); MQTT dinleyicisi ESP kapalıyken kapalı kalır (dokunulmadı).
"""

from __future__ import annotations

import csv
from datetime import datetime

import pytest


class _Olay:
    def __init__(self, govde: dict, tip: str = "hardware.stm.telemetry"):
        self.event_type = tip
        self.data = govde


@pytest.fixture
def kur(tmp_path, monkeypatch):
    from servers import api_server as api
    from servers import sensor_kaydedici as sk

    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    monkeypatch.delenv("PEMF_SENSOR_LOG", raising=False)
    dizin = tmp_path / "sensor_log"
    monkeypatch.setenv("PEMF_SENSOR_LOG_DIR", str(dizin))
    monkeypatch.setattr(sk, "_kaydedici", None)  # süreç tekili bu dizinle yeniden kurulsun
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    try:
        yield api, sk, dizin
    finally:
        if sk._kaydedici is not None:
            sk._kaydedici.kapat()


def _satirlar(sk, dizin, ad=None) -> list:
    sk.kaydedici().flush()
    yol = dizin / (ad or f"sensor_{datetime.now():%Y-%m-%d}.csv")
    if not yol.exists():
        return []
    with open(yol, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def test_KRITIK_STM_telemetrisi_ESP_KAPALIYKEN_CSV_ye_yazilir(kur):
    """Plan kapısı: ESP kapalı (bayrak tanımsız), gerçek olay yolu → günlük CSV'de bobin satırı.
    MUTASYON: STM işleyicisindeki kaydet çağrısı silinir → KIRMIZI."""
    api, sk, dizin = kur
    api._handle_backend_event(_Olay({"coil_id": 6, "object_temp": 41.7, "ambient_temp": 26.3, "magnetic_field": 1.842}))
    satirlar = _satirlar(sk, dizin)
    assert len(satirlar) == 2, f"STM telemetrisi sensör kaydına yazılmadı (satırlar: {satirlar})"
    k = dict(zip(satirlar[0], satirlar[1]))
    assert (k["bobin"], k["temp_object"], k["temp_ambient"], k["magnetic_field"]) == ("6", "41.7", "26.3", "1.842"), k


def test_KRITIK_OLCULMEYEN_alan_BOS_yazilir_sifir_DEGIL(kur):
    """Y6: bobin 1 yalnız akım ölçer → sıcaklık/alan sütunu BOŞ (0.0 "ölçüldü" sanılır)."""
    api, sk, dizin = kur
    api._handle_backend_event(_Olay({"coil_id": 1, "current": 2.5}))
    k = dict(zip(*_satirlar(sk, dizin)[:2]))
    assert (k["bobin"], k["current"], k["temp_object"], k["magnetic_field"]) == ("1", "2.5", "", ""), k


def test_KRITIK_eksen_uclari_ve_doygunluk_KAYDA_girer(kur):
    """STM'nin işaretli eksen uçları (bipolar / faz kazancının tek taşıyıcısı) ve doygunluk bayrakları kayıtta.
    MUTASYON: eksen ucu eşlemesi silinir → KIRMIZI."""
    api, sk, dizin = kur
    api._handle_backend_event(
        _Olay(
            {
                "coil_id": 7,
                "magnetic_field": 3.1,
                "mag_x_min": -2.9,
                "mag_x_max": 3.1,
                "mag_z_min": -0.4,
                "mag_z_max": 0.5,
                "magnetic_saturated": True,
            }
        )
    )
    k = dict(zip(*_satirlar(sk, dizin)[:2]))
    assert (k["mag_x_min"], k["mag_x_max"], k["mag_z_min"], k["mag_z_max"]) == ("-2.9", "3.1", "-0.4", "0.5"), k
    assert k["mag_y_min"] == "" and k["magnetic_saturated"] == "1", k


def test_KRITIK_ayni_gun_ESKI_basliklı_dosyaya_yeni_sutunlu_satir_YAZILMAZ(kur):
    """Güncelleme günü: o gün eski sürümle açılmış (eski başlıklı) dosya varsa yeni satırlar AYRI dosyaya — sütunlar kaymaz.
    MUTASYON: başlık denetimi silinir → eski dosyaya yeni sütunlu satır eklenir → KIRMIZI."""
    api, sk, dizin = kur
    dizin.mkdir(parents=True)
    eski_ad = f"sensor_{datetime.now():%Y-%m-%d}.csv"
    eski_baslik = ",".join(sk.SUTUNLAR[:24])
    (dizin / eski_ad).write_text(eski_baslik + "\n" + ",".join(["x"] * 24) + "\n", encoding="utf-8")
    api._handle_backend_event(_Olay({"coil_id": 6, "object_temp": 40.0}))
    assert (dizin / eski_ad).read_text(encoding="utf-8").count("\n") == 2, "eski başlıklı dosyaya satır eklendi"
    yeni = _satirlar(sk, dizin, f"sensor_{datetime.now():%Y-%m-%d}_2.csv")
    assert yeni and yeni[0] == list(sk.SUTUNLAR) and dict(zip(yeni[0], yeni[1]))["temp_object"] == "40.0", yeni


def test_KRITIK_kaydedici_HATA_atsa_da_canli_durum_GUNCELLENIR(kur, monkeypatch):
    """Ö.4-Y8 ruhu: telemetri kaydı bir kolaylıktır; kaydedici fırlatırsa olay işleyicisi düşmez, canlı durum yazılır."""
    api, sk, _ = kur

    def _patla(*a, **k):
        raise OSError("disk dolu")

    monkeypatch.setattr(api._sensor_kaydedici, "kaydet", _patla)
    api._handle_backend_event(_Olay({"coil_id": 6, "object_temp": 39.9}))
    with api._live_state_lock:
        assert api._live_state["coils"][5]["objectTemp"] == 39.9


def test_KARSIT_PEMF_SENSOR_LOG_0_iken_dosya_YAZILMAZ(kur, monkeypatch):
    api, sk, dizin = kur
    monkeypatch.setenv("PEMF_SENSOR_LOG", "0")
    api._handle_backend_event(_Olay({"coil_id": 6, "object_temp": 41.7}))
    assert _satirlar(sk, dizin) == []
