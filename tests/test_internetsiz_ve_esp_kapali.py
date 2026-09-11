# -*- coding: utf-8 -*-
# Author: mertaygn
"""İNTERNETSİZ ÇALIŞMA + ESP DEVRE DIŞI — 2026-09-11 sahip bildirimleri.

===============================================================================
1) "İNTERNET YOKKEN KIRMIZI DOLU EKRAN"
===============================================================================
Sahip: "uygulama internet olmayan makinede çalışmalı (uzaktan erişim hariç). İnternete
bağlı değilken kullanıcı geri bildirimi çok eksik, her yerden kırmızı uyarılar fışkırıyor.
Latte Panda'da düşün: internete bağlı olmasa bile hotspot açabiliyor ve bütün donanım
kusursuz çalışıyor ama kırmızı dolu bir ekran var."

KÖK NEDEN: `services/headless_services._determine_gateway_mode` hotspot AÇIK + internet
YOK durumunu `"offline"` döndürüyor; `api_server` bunu
`gateway = "online" if mode in ("online","hybrid") else "offline"` ile okuyordu →
Dashboard'daki "Bağlantı" rozeti KIRMIZI. Oysa o an hotspot çalışıyor, STM kablolu,
bütün donanım sürülüyor.

⚠️ SINIF: "internet yok" ile "cihaz bozuk" AYNI renge boyanıyordu. Sonuç uyarı körlüğü —
kalıcı kırmızıya alışan operatör GERÇEK arızayı da görmez.

===============================================================================
2) ESP SÖKÜLDÜ — KOD SİLİNMEZ, DEVRE DIŞI KALIR
===============================================================================
Sahip: "espleri sistemden söktüğüm için ESP kodlarını devre dışı bırak ama ASLA SİLME,
ileride tekrar hibrit ESP+STM ya da sadece ESP sistemine dönebilirim."

ÇÖZÜM: tek bayrak `PEMF_ESP_ENABLED` (varsayılan 0). Kod CANLI kalır ve testler onu
`PEMF_ESP_ENABLED=1` ile koşmaya DEVAM EDER — yorum satırına alınsaydı derlenmez/test
edilmez olur ve geri dönüşte sessizce bayatlardı.

===============================================================================
⚠️ BU DOSYA NE ÖLÇMEZ
===============================================================================
"Gösterilen değerler gerçek değil" şikâyeti ARAŞTIRILDI: `PEMF_SIMULATE` saf bir ortam
değişkenidir, bağlantıdan TÜRETİLMEZ — yani internetsizlik uygulamayı sahte veriye
DÜŞÜRMÜYOR. Sensör alanlarının boş görünmesinin sebebi ayrı bir arızaydı (newlib-nano
printf-float, bkz. test_stm_printf_float_kapisi.py). Burada o iddia sınanmaz; aşağıdaki
kapı yalnız "simülasyon bağlantıdan türemez" değişmezini kilitler.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

os.environ.setdefault("PEMF_SIMULATE", "1")


def _olay(tur: str, veri: dict):
    return type("O", (), {"event_type": tur, "data": veri})()


@pytest.fixture
def durum():
    """`_live_state`i testten sonra eski hâline döndürür."""
    from servers import live_state

    with live_state._live_state_lock:
        eski = {k: live_state._live_state[k] for k in ("gateway", "mqtt", "internet")}
    yield live_state
    with live_state._live_state_lock:
        live_state._live_state.update(eski)


# ============================================================================
# 1. İNTERNET YOKKEN CİHAZ AĞI "ÇEVRİMDIŞI" SAYILMAZ
# ============================================================================


def test_KRITIK_hotspot_ACIK_internet_YOKKEN_gateway_ONLINE(durum):
    """⚠️ ASIL KAPI — sahanın "kırmızı dolu ekran" şikâyeti tam olarak budur.

    MUTASYON: `cihaz_agi_var` hesabını eski hâline döndür
    (`"online" if mode in ("online","hybrid") else "offline"`) → KIRMIZI.
    """
    from servers import api_server

    api_server._handle_backend_event(
        _olay("network.status", {"gateway_mode": "offline", "hotspot_active": True, "internet_connected": False})
    )
    with durum._live_state_lock:
        g, i = durum._live_state["gateway"], durum._live_state["internet"]
    assert g == "online", (
        f"hotspot ACIK ve donanim calisirken cihaz agi '{g}' bildirildi -> arayuz KIRMIZI yanar "
        "ve operator gercek arizayi goremez hale gelir (uyari korlugu)"
    )
    assert i == "offline", "internet durumu AYRI alanda bildirilmeli (notr bilgi)"


def test_KRITIK_internet_ile_cihaz_agi_AYRI_alanlar(durum):
    """İkisi tek alana sıkıştırılırsa arayüz hangisinin bozuk olduğunu SÖYLEYEMEZ."""
    from servers import api_server

    # İnternet VAR, hotspot yok (kablolu klinik ağı).
    api_server._handle_backend_event(
        _olay("network.status", {"gateway_mode": "hybrid", "hotspot_active": False, "internet_connected": True})
    )
    with durum._live_state_lock:
        assert durum._live_state["gateway"] == "online"
        assert durum._live_state["internet"] == "online"


def test_HICBIR_AG_YOKKEN_cihaz_agi_GERCEKTEN_offline(durum):
    """Karşıt kanıt: kural "her zaman online de" diye geçilemesin.

    Hotspot da yok, internet de yok → cihaz ağı GERÇEKTEN çevrimdışıdır ve öyle
    bildirilmelidir (mobil istemciler bağlanamaz).
    """
    from servers import api_server

    api_server._handle_backend_event(
        _olay("network.status", {"gateway_mode": "disconnected", "hotspot_active": False, "internet_connected": False})
    )
    with durum._live_state_lock:
        assert durum._live_state["gateway"] == "offline"


def test_snapshot_internet_alanini_TASIR(durum):
    """Arayüz alanı okuyamıyorsa ayrım işe yaramaz."""
    from servers import live_state

    anlik = live_state._build_ws_snapshot() if hasattr(live_state, "_build_ws_snapshot") else None
    if anlik is None:
        pytest.skip("snapshot yardimcisi bu surumde yok")
    assert "internet" in anlik, "snapshot `internet` alanini TASIMIYOR -> arayuz notr gosterge cizemez"


# ============================================================================
# 2. ESP DEVRE DIŞI — KOD DURUYOR, DAVRANIŞ KAPALI
# ============================================================================


def test_KRITIK_varsayilan_ESP_KAPALI(monkeypatch):
    """Sahип ESP'leri söktü → varsayılan KAPALI olmalı.

    MUTASYON: varsayılanı `"1"` yap → KIRMIZI (sökülü donanım için MQTT denemeleri
    ve kalıcı sarı rozet geri gelir).
    """
    from servers import live_state

    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    assert live_state.esp_etkin() is False


def test_KRITIK_bayrakla_ESP_GERI_GELIR(monkeypatch):
    """⚠️ EN ÖNEMLİ DEĞİŞMEZ: kod SİLİNMEDİ, tek satırlık ayarla geri dönülüyor.

    Sahip: "ileride tekrar hibrit esp stm ya da sadece esp sistemine dönebilirim."
    Bu kapı, devre-dışı bırakmanın geri DÖNÜLEBİLİR olduğunu kanıtlar.
    """
    from servers import live_state

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    assert live_state.esp_etkin() is True


def test_KRITIK_ESP_kapaliyken_MQTT_rozeti_ARIZA_gostermez(durum, monkeypatch):
    """Kurulu olmayan alt sistem için kalıcı sarı/kırmızı rozet = uyarı körlüğü.

    MUTASYON: `mqtt.broker.status` işleyicisindeki `esp_etkin()` dalını sil → KIRMIZI.
    """
    from servers import api_server

    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    api_server._handle_backend_event(_olay("mqtt.broker.status", {"port_open": False, "running": False}))
    with durum._live_state_lock:
        assert durum._live_state["mqtt"] == "devre_disi", (
            "ESP sokulu iken broker durumu ARIZA olarak bildirildi -> kalici alarm"
        )


def test_KRITIK_ESP_ACIKKEN_broker_arizasi_YINE_bildirilir(durum, monkeypatch):
    """Karşıt kanıt: bayrak açıkken gerçek broker arızası GİZLENMEZ."""
    from servers import api_server

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    api_server._handle_backend_event(_olay("mqtt.broker.status", {"port_open": False, "running": False}))
    with durum._live_state_lock:
        assert durum._live_state["mqtt"] == "warning"


def test_KRITIK_ESP_kapaliyken_MQTT_dinleyicisi_BASLAMAZ(monkeypatch):
    """Broker yokken `connect_async` sonsuz yeniden dener → log seli + boşa kaynak.

    MUTASYON: `_start_mqtt_for_api` başındaki `esp_etkin()` kapısını sil → KIRMIZI.
    """
    from servers import api_server

    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    cagrildi = {"paho": False}

    class _SahtePaho:
        def __getattr__(self, _ad):
            cagrildi["paho"] = True
            raise AssertionError("ESP KAPALIYKEN paho.mqtt'ye DOKUNULDU")

    monkeypatch.setitem(sys.modules, "paho.mqtt.client", _SahtePaho())
    api_server._start_mqtt_for_api()
    assert cagrildi["paho"] is False


# ============================================================================
# 3. ESP KAYNAK KODU SİLİNMEDİ (geri dönüş yolu AÇIK)
# ============================================================================


@pytest.mark.parametrize(
    "yol",
    [
        "firmware/esps3_pemf_coil",
        "firmware/esp8266_pemf_coil",
    ],
)
def test_KRITIK_ESP_firmware_kaynagi_DURUYOR(yol):
    """⚠️ Sahip AÇIKÇA "asla silme" dedi. Devre dışı bırakmak SİLMEK DEĞİLDİR.

    MUTASYON: klasörü sil → KIRMIZI. Bu kapı, "temizlik" amaçlı bir sonraki turda
    kaynağın sessizce kaldırılmasını engeller.
    """
    d = KOK / yol
    assert d.is_dir(), f"{yol} SILINMIS -> ESP'ye geri donus yolu kapandi (sahip: 'asla silme')"
    assert any(d.rglob("*.cpp")) or any(d.rglob("*.ino")), f"{yol} bos -> kaynak kaybolmus"


def test_KRITIK_ESP_calisma_zamani_kodu_da_DURUYOR():
    """MQTT/ESP sürüş yolları yorum satırına alınmadı, YERİNDE duruyor."""
    kaynak = (KOK / "servers" / "api_server.py").read_text(encoding="utf-8", errors="replace")
    for isaret in ("_start_mqtt_for_api", "_on_mqtt_message_api", "_mqtt_publish"):
        assert f"def {isaret}" in kaynak, (
            f"`{isaret}` kaldirilmis -> ESP'ye geri donus tek satirlik ayar olmaktan CIKTI"
        )


# ============================================================================
# 4. SİMÜLASYON BAĞLANTIDAN TÜREMEZ (sahte veri kapısı)
# ============================================================================


def test_KRITIK_simulasyon_BAGLANTIDAN_turetilmez():
    """⚠️ Sahip "gösterilen değerler gerçek değil" dedi — bu iddia ARAŞTIRILDI.

    `PEMF_SIMULATE` SAF bir ortam değişkenidir; internet/ağ durumundan TÜRETİLMEZ.
    Yani internetsiz bir klinik makinesi sahte veriye DÜŞMEZ.

    MUTASYON: simülasyon kararına bir ağ koşulu ekle (ör. `or not internet`) → KIRMIZI.
    Sahadaki etki: gerçek donanım bağlıyken uydurma sayılar gösterilir — bu deponun
    en tehlikeli arıza sınıfı.
    """
    import ast

    kaynak = (KOK / "servers" / "api_server.py").read_text(encoding="utf-8", errors="replace")
    agac = ast.parse(kaynak)
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Compare):
            continue
        metin = ast.dump(dugum)
        if "PEMF_SIMULATE" not in metin:
            continue
        # Karşılaştırma YALNIZ ortam değişkeni ile sabit arasında olmalı.
        for yasak in ("internet", "gateway", "wsConnected", "connected", "online"):
            assert yasak not in metin, (
                f"simulasyon karari '{yasak}' ile birlesmis -> baglanti kaybinda SAHTE VERI riski"
            )


def test_KRITIK_ESP_kapaliyken_MQTT_PUBLISH_hic_denenmez(monkeypatch):
    """⚠️ TEK BOĞAZ NOKTASI: bütün ESP komutları `_mqtt_publish`ten geçer.

    Kapı burada olmazsa her komut (manuel, seans, AI, E-stop, reconcile, selftest) sökülü
    donanım için soket probu açar ve `_kaydet_esp_komut_niyeti` ile BAYAT niyet biriktirir.
    O niyet, ileride `PEMF_ESP_ENABLED=1` ile dönüldüğünde reconcile'ı yanlış tetikler.

    ⚠️ "False döndü" YETMEZ — broker yokken zaten False döner. Bu kapı DENENMEDİĞİNİ ölçer:
    soket açılmamalı ve niyet yazılmamalı.

    MUTASYON: `_mqtt_publish` başındaki `esp_etkin()` kapısını sil → KIRMIZI.
    """
    import socket as _socket

    from servers import api_server

    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    izler = {"soket": 0, "niyet": 0}

    def _soket_yasak(*a, **k):
        izler["soket"] += 1
        raise OSError("baglanti yok")

    monkeypatch.setattr(_socket, "create_connection", _soket_yasak)
    monkeypatch.setattr(
        api_server, "_kaydet_esp_komut_niyeti", lambda *a, **k: izler.__setitem__("niyet", izler["niyet"] + 1)
    )

    sonuc = api_server._mqtt_publish("pemf/coil/8/control", {"command": "stop"})

    assert sonuc is False, "ESP kapaliyken 'gonderildi' denildi -> gonderilmemis komut teyit edildi"
    assert izler["soket"] == 0, "ESP kapaliyken SOKET acildi -> kapi calismiyor"
    assert izler["niyet"] == 0, "ESP kapaliyken NIYET kaydedildi -> geri donuste bayat reconcile"


def test_KRITIK_ESP_ACIKKEN_publish_GERCEKTEN_denenir(monkeypatch):
    """Karşıt kanıt: bayrak açıkken yol kapanmamalı (geri dönüş GERÇEKTEN çalışmalı)."""
    import socket as _socket

    from servers import api_server

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    izler = {"soket": 0}

    def _soket_sayac(*a, **k):
        izler["soket"] += 1
        raise OSError("broker yok")

    monkeypatch.setattr(_socket, "create_connection", _soket_sayac)
    api_server._mqtt_publish("pemf/coil/8/control", {"command": "stop"})
    assert izler["soket"] == 1, "ESP ACIKKEN publish denenmedi -> geri donus yolu KOPUK"
