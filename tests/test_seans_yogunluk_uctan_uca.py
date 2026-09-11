# -*- coding: utf-8 -*-
# Author: mertaygn
"""UÇTAN UCA: STM telemetrisi → bobin 6 kartı → seans yoğunluğu → masaüstü CSV.

SAHİP KARARI 2026-09-11 (tek cümlede üç iş):
  "1 tane manyetik bağlı olduğu için bobin 6 ya koy mT değeri sensörden arayüzdeki bobin 6
   kısmına gelsin ... ordaki yoğunluk değeri stm e bağlı olan SENSÖRDEN GELSİN VE AYNI
   ZAMANDA CSV YE KAYDEDİP MASAÜSTÜNE KOYSUN. SEANS ÖZELİNDE OLCAK BU."

⚠️ NEDEN AYRI BİR UÇTAN UCA DOSYASI: parçaların hepsi kendi kapısıyla yeşil olabilir ve
zincir yine de KOPUK olabilir — telemetri işleyicisi `_seans_alan.olcum(...)`u hiç çağırmazsa
CSV boş kalır, `update_measured_intensity` hiç çağrılmazsa kart reçeteyi göstermeye devam
eder. Bu deponun tekrarlayan arıza sınıfı: "her modül doğru, zincir kopuk".

Tasarım: `_event_loop` None → `_ws_broadcast_sync` yakalanır; CSV tmp_path'e yönlendirilir.
"""

import io
import os

os.environ.pop("PEMF_SIMULATE", None)

import csv

import pytest


class _Olay:
    def __init__(self, govde: dict, tip: str = "hardware.stm.telemetry"):
        self.event_type = tip
        self.data = govde


@pytest.fixture()
def kur(monkeypatch, tmp_path):
    from servers import api_server as api
    from servers.seans_alan_kaydi import SeansAlanKaydi

    yayinlar: list[dict] = []
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: yayinlar.append(m))
    monkeypatch.setattr(api.live_state, "_ws_broadcast_sync", lambda m: yayinlar.append(m))
    bildirimler: list[tuple] = []
    monkeypatch.setattr(api, "_push_notification", lambda m, s="info": bildirimler.append((m, s)))

    # Masaüstü yerine tmp_path'e yazan TAZE kaydedici (süreç geneli örneği kirletme).
    monkeypatch.setattr("servers.seans_alan_kaydi.masaustu_dizini", lambda: (tmp_path, "test"))
    kayit = SeansAlanKaydi()
    monkeypatch.setattr(api, "_seans_alan", kayit)

    with api._live_state_lock:
        api._live_state["coils"][5].update({"magneticMt": 0.0, "measuredFields": []})
        api._live_state["activeTreatment"].update(
            {"isActive": False, "measuredIntensityMt": None, "measuredIntensityCoil": None}
        )
    api._coil_olculen_alanlar.pop(5, None)
    api._coil_last_telemetry.pop(5, None)
    api._mag_doygun_son.pop(5, None)

    yield api, kayit, yayinlar, bildirimler, tmp_path

    kayit.seans_bitti("test bitti")
    with api._live_state_lock:
        api._live_state["activeTreatment"].update(
            {"isActive": False, "measuredIntensityMt": None, "measuredIntensityCoil": None}
        )


def _son(yayinlar, tip):
    for m in reversed(yayinlar):
        if m.get("type") == tip:
            return m
    return None


def test_KRITIK_zincir_TAM_telemetri_karta_ve_CSVye_ulasir(kur):
    """Tek bir telemetri olayı üç yere birden ulaşmalı: bobin 6 kartı, seans çipi, CSV.

    MUTASYON: telemetri işleyicisindeki `_seans_alan.olcum(...)` çağrısını sil → KIRMIZI
    (CSV boş kalır). `update_measured_intensity(...)` çağrısını sil → KIRMIZI (kart reçetede
    kalır). İkisi ayrı ayrı zinciri koparır ve hiçbir birim testi bunu görmez.
    """
    api, kayit, yayinlar, _bildirimler, tmp_path = kur

    # 1) Seans başlar → CSV açılır
    yol = kayit.seans_basladi("SEANS-E2E", {"patient_name": "Test", "intensity": 2.0})
    assert yol is not None and yol.exists()
    api.live_state.update_live_session_state(is_active=True, mode="Manuel", freq=10, intensity=2.0, duration_sec=600)

    # 2) STM'den saniyelik TEPE gelir (bobin 6 — tek manyetik sensör oraya eşlenik)
    api._handle_backend_event(_Olay({"coil_id": 6, "magnetic_field": 3.412, "magnetic_samples": 407}))

    # 3a) Bobin 6 kartı
    with api._live_state_lock:
        c = dict(api._live_state["coils"][5])
    assert c["magneticMt"] == pytest.approx(3.412), "bobin 6 karti alani ALMADI"
    assert "magneticMt" in c["measuredFields"], "alan OLCULDU olarak isaretlenmedi"
    sd = _son(yayinlar, "sensor_data")
    assert sd is not None and sd["coilId"] == 6

    # 3b) Aktif seans çipi — SENSÖRDEN gelen değer, reçete DOKUNULMADAN
    with api._live_state_lock:
        at = dict(api._live_state["activeTreatment"])
    assert at["measuredIntensityMt"] == pytest.approx(3.412), "seans yogunlugu SENSORDEN gelmedi"
    assert at["measuredIntensityCoil"] == 6
    assert at["intensityMt"] == pytest.approx(2.0), "olcum RECETE alaninin uzerine yazildi"

    # 3c) CSV — satır ANINDA diskte (çöküşte kaybolmamalı)
    with io.open(yol, encoding="utf-8-sig", newline="") as f:
        satirlar = list(csv.reader(f))
    veri = [s for s in satirlar if s and s[0] and not s[0].startswith("#") and s[0] != "zaman"]
    assert len(veri) == 1, f"CSV'ye olcum YAZILMADI: {satirlar}"
    assert veri[0][2] == "6" and veri[0][3] == "3.412" and veri[0][4] == "407"


def test_KRITIK_seans_yogunlugu_SEANS_TEPESI_son_saniye_DEGIL(kur):
    """Kartta seans boyu TEPE gösterilir; darbe fazına göre inip çıkan son saniye değil."""
    api, kayit, _y, _b, _t = kur
    kayit.seans_basladi("SEANS-TEPE", {})
    api.live_state.update_live_session_state(is_active=True, mode="Manuel", freq=10, intensity=1.0, duration_sec=600)
    for v in (2.0, 9.6, 1.1):
        api._handle_backend_event(_Olay({"coil_id": 6, "magnetic_field": v, "magnetic_samples": 400}))
    with api._live_state_lock:
        at = dict(api._live_state["activeTreatment"])
    assert at["measuredIntensityMt"] == pytest.approx(9.6), (
        f"kartta {at['measuredIntensityMt']} — seans TEPESI degil, son saniye gosteriliyor"
    )


def test_KRITIK_manyetik_DOYGUNLUK_operatore_SOYLENIR_ve_bir_kez(kur):
    """Sensör aralığı aşıldıysa değer güvenilmezdir ve doz kaydına öyle giriyor.

    ⚠️ Yalnız 0→1 geçişinde bildirilir: saniyede bir bildirim basmak alarm yorgunluğu
    üretir ve gerçek olayları boğar (akım doygunluğunda alınmış aynı karar).

    MUTASYON: `_mag_doygun_son` geçiş kontrolünü kaldır → ikinci olayda da bildirim çıkar
    → KIRMIZI.
    """
    api, kayit, _y, bildirimler, _t = kur
    kayit.seans_basladi("SEANS-DOY", {})
    api.live_state.update_live_session_state(is_active=True, mode="Manuel", freq=10, intensity=1.0, duration_sec=600)
    olay = {"coil_id": 6, "magnetic_field": 24.5, "magnetic_samples": 400, "magnetic_saturated": True}
    api._handle_backend_event(_Olay(dict(olay)))
    api._handle_backend_event(_Olay(dict(olay)))
    doygunluk_bildirimleri = [m for m, _s in bildirimler if "manyetik" in m.lower()]
    assert len(doygunluk_bildirimleri) == 1, (
        f"doygunluk bildirimi {len(doygunluk_bildirimleri)} kez basildi (1 bekleniyordu) -> alarm yorgunlugu"
    )
    assert "GÜVENİLMEZ" in doygunluk_bildirimleri[0]


def test_KRITIK_akim_bobinleri_seans_yogunlugunu_KIRLETMEZ(kur):
    """Bobin 1-5 yalnız akım gönderir; o satır seans yoğunluğuna DOKUNMAMALI.

    ⚠️ NEDEN: `magnetic_field` anahtarı yoksa ölçüm YOKTUR. Akım satırını da "ölçüm geldi"
    sayıp `update_measured_intensity(zirve)` çağırmak, sensör hiç yokken kartta bir sayı
    (ya da 0.0) belirmesine yol açardı.

    MUTASYON: `float(data["magnetic_field"])` → `float(data.get("magnetic_field", 0.0))`
    (ve kapıyı `if True:` yap) → KIRMIZI. Bu deponun tekrarlayan arıza sınıfı: ölçülmeyen
    alanın 0.0 varsayılanı aşağı akışta "ölçüldü" olarak kaydediliyor.

    ⚠️ SADECE kapıyı `if True:` yapmak KIRMIZI ETMEZ — `data["magnetic_field"]` KeyError
    atar ve blok geniş `except`e düşer. Yani bu satırdaki gerçek koruma anahtar kontrolü
    DEĞİL, "eksik alanı varsayılanla okumama" kuralıdır; mutasyon onu hedeflemeli.
    """
    api, kayit, _y, _b, tmp_path = kur
    kayit.seans_basladi("SEANS-AKIM", {})
    api.live_state.update_live_session_state(is_active=True, mode="Manuel", freq=10, intensity=1.0, duration_sec=600)
    api._handle_backend_event(_Olay({"coil_id": 3, "current": 2.14}))
    with api._live_state_lock:
        at = dict(api._live_state["activeTreatment"])
    assert at["measuredIntensityMt"] is None, "akim satiri seans yogunlugunu yazdi"
    assert kayit.durum()["satir"] == 0, "akim satiri alan CSV'sine yazildi"
