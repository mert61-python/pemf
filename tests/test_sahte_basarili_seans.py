# -*- coding: utf-8 -*-
# Author: mertaygn
"""SAHTE "BAŞARILI" SEANS — donanım komutu reddederken seans başlıyormuş gibi görünmesi.

===============================================================================
SAHİP BİLDİRİMİ (2026-09-12)
===============================================================================
"firmware sürüm uyumsuzluğundan dolayı bobinler komut almicak bildirimi gelmesine ve
gerçekten bobinlere komut gitmemesine rağmen seans başlatınca gerçekten başlıyormuş gibi
her şey sorunsuz devam ediyor."

===============================================================================
ÖLÇÜLEN İKİ KÖK NEDEN
===============================================================================
1) `hardware.stm.nack` dalı YALNIZCA bildirim basıp `return` ediyordu. Oysa `watchdog_timeout`
   dalı aynı sınıftan bir olayda ("donanım komuta uymuyor") seansı DURDURUYOR. CRC reddinde
   seans aktif kalıyor, sayaç işliyor, geçmişe "Tamamlandı" yazılıyordu.

2) DAHA GENEL OLANI: `/api/session/start` içindeki `_start_stm_coils()`, `update_coil`'in
   dönüş değerini HİÇ OKUMUYORDU. `update_coil` reddi False ile bildirir (kart kopuk /
   firmware uyuşmaz / parametre geçersiz) — hiçbir bobin sürülmese bile seans "başladı"
   sayılıyor ve coil-run satırları TAM SÜREYLE yazılıyordu.
   ⚠️ Tekil bobin yolu bunu 2026-08-20'de zaten düzeltmişti; SEANS yolu dışarıda kalmıştı
   ("kısmi düzeltme, düzeltilmemiş demektir").

===============================================================================
NEDEN BU EN AĞIR ARIZA SINIFI
===============================================================================
Tıbbi kayıt, hiç uygulanmamış bir tedaviyi uygulanmış olarak BELGELİYORDU. Operatör
hastanın doz aldığını sanıyor; geçmiş, PDF ve KPI bunu doğruluyor. Hatanın hiçbir izi yok.
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

_PF = KOK / "apps" / "ui" / "src"


@pytest.fixture
def istemci():
    from fastapi.testclient import TestClient
    from servers import api_server

    with TestClient(api_server.app) as c:
        yield c


@pytest.fixture(autouse=True)
def temiz_red_durumu():
    """Her test TEMİZ başlasın: red sayacı süreç-genelidir, testler arası sızar."""
    from servers import live_state

    live_state.stm_komut_kabulu_bildir()
    yield
    live_state.stm_komut_kabulu_bildir()


@pytest.fixture
def seans_kapat(istemci):
    """Test bir seans açtıysa kapat (sonraki teste 'Zaten aktif seans var' sızmasın)."""
    yield
    try:
        istemci.post("/api/session/stop")
    except Exception:
        pass


@pytest.fixture
def izole_db(tmp_path, monkeypatch):
    """Seans/koşu satırlarının yazıldığı tedavi-DB'sini izole eder.

    ⚠️ GEREKLİ: koşu kaydının açılıp açılmadığını `_active_coil_runs` sözlüğünden ölçmek
    YETMEZ — mutasyonla ölçüldü (2026-09-12): geri alma yolu o sözlüğü zaten temizlediği
    için kapı YEŞİL kalıyordu. Asıl zarar DB'ye SATIR YAZILMASIDIR (geçmiş/PDF/KPI onu
    gerçek doz sanar), dolayısıyla kapı DB satırını saymalı.
    """
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server, coil_run_tracker

    kok = tmp_path / "izole_gecmis"
    kok.mkdir(parents=True, exist_ok=True)
    db = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(coil_run_tracker, "_treatment_db_getter", lambda: db)
    return db


class SahteDonanim:
    """`update_coil` çağrılarını kaydeden, KABUL/RED davranışı ayarlanabilir sahte kontrolcü."""

    def __init__(self, kabul: bool):
        self.kabul = kabul
        self.cagrilar: list = []

    def update_coil(self, coil_id, freq, duty, phase, duration, start=True, duration_seconds=None):
        self.cagrilar.append((coil_id, start))
        return self.kabul

    def stop_all_coils(self):
        return True

    def get_all_coils_state(self):
        return {}


def _seans_baslat(istemci, bobinler=(1, 2)):
    return istemci.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 100,
            "duty": 50,
            "phase": 0,
            "intensity": 0.0,
            "duration_minutes": 20,
            "coil_ids": list(bobinler),
            "patient_name": "Mia",
        },
    )


# ============================================================================
# 1. ⚠️ ASIL KAPI — HİÇBİR BOBİN KABUL ETMEZSE SEANS BAŞLAMAZ
# ============================================================================


def test_KRITIK_hicbir_bobin_kabul_etmezse_seans_BASLAMAZ(istemci, monkeypatch, seans_kapat):
    """MUTASYON: `if stm_coils and not _stm_kabul and not esp_coils:` kapısını sil → KIRMIZI
    (200 "started" döner; sahibin bildirdiği arızanın ta kendisi).
    """
    from servers import api_server

    sahte = SahteDonanim(kabul=False)
    monkeypatch.setattr(api_server.state, "hardware", sahte)

    y = _seans_baslat(istemci)
    assert y.status_code == 503, f"RED beklenirken {y.status_code}: {y.text[:300]}"
    assert sahte.cagrilar, "onkosul: update_coil hic cagrilmadi -> kapi yanlis yeri olcuyor"
    # ⚠️ Mesaj EYLEM söylemeli: "hata" demek operatöre ne yapacağını söylemez.
    assert "firmware" in y.text.lower(), f"mesaj EYLEM soylemiyor: {y.text[:300]}"


def test_KRITIK_reddedilen_seans_AKTIF_KALMAZ(istemci, monkeypatch, seans_kapat):
    """⚠️ Geri alma yapılmazsa seans `is_active=True` kalır: sayaç işler, süre-watchdog
    20 dakika sonra onu "tamamlandı" diye mühürler ve ikinci bir seans "Zaten aktif seans
    var" ile reddedilir. Arıza, ilk denemeden SONRA da yaşamaya devam ederdi.

    MUTASYON: `_seansi_geri_al(...)` çağrısını sil → KIRMIZI.
    """
    from servers import api_server

    monkeypatch.setattr(api_server.state, "hardware", SahteDonanim(kabul=False))
    _seans_baslat(istemci)
    durum = istemci.get("/api/session/status")
    if durum.status_code == 200:
        g = durum.json()
        aktif = g.get("is_active", g.get("isActive", g.get("active")))
        assert not aktif, f"reddedilen seans AKTIF kaldi: {g}"
    with api_server._session_lock:
        assert not api_server._active_session.get("is_active"), "_active_session AKTIF kaldi"


def test_KRITIK_reddedilen_bobin_icin_DB_kosu_satiri_YAZILMAZ(istemci, monkeypatch, seans_kapat, izole_db):
    """⚠️ Reddedilen bobin için `_begin_coil_run` açmak, hiç uygulanmamış bir dozu tıbbi
    kayda YAZMAK demektir — geçmiş/PDF/KPI o dozu gerçekmiş gibi raporlar.

    ⚠️ KAPI DB SATIRINI SAYAR, bellek sözlüğünü DEĞİL: `_active_coil_runs`i ölçen ilk
    sürüm mutasyonda YEŞİL kaldı, çünkü geri alma yolu o sözlüğü zaten temizliyor. Kalıcı
    zarar diskteki satırdır.

    MUTASYON: `_start_stm_coils` içinde `_begin_coil_run`i `if kabul` dalının DIŞINA al
    → KIRMIZI (reddedilen bobinler için satır yazılır).
    """
    from servers import api_server

    monkeypatch.setattr(api_server.state, "hardware", SahteDonanim(kabul=False))
    _seans_baslat(istemci)
    seanslar = izole_db.get_session_history(limit=50)
    assert seanslar, "onkosul: seans satiri hic olusmadi -> kapi yanlis yeri olcuyor"
    toplam = sum(len(izole_db.get_session_coil_runs(s["id"])) for s in seanslar)
    assert toplam == 0, f"reddedilen bobinler icin {toplam} KOSU SATIRI yazildi (uygulanmamis doz kaydi)"


def test_KRITIK_reddedilen_seans_DBde_TAMAMLANDI_degil(istemci, monkeypatch, seans_kapat, izole_db):
    """⚠️ ARIZANIN KALICILAŞTIĞI YER: hiç başlamamış seans `'completed'` yazılırsa,
    uygulanmamış bir tedavi geçmişte/PDF'te/KPI'de UYGULANMIŞ olarak belgelenir.

    MUTASYON: `_finalize_session_db`teki `donanim-reddi` dalını sil → KIRMIZI ("completed").
    """
    from database.treatment_history_db import SEANS_DURUMU_DONANIM_REDDI
    from servers import api_server

    monkeypatch.setattr(api_server.state, "hardware", SahteDonanim(kabul=False))
    _seans_baslat(istemci)
    seanslar = izole_db.get_session_history(limit=50)
    assert seanslar, "onkosul: seans satiri hic olusmadi"
    durumlar = {(s.get("session_status") or "") for s in seanslar}
    assert "completed" not in durumlar, (
        f"hic baslamamis seans TAMAMLANDI yazildi: {durumlar} -> uygulanmamis tedavi belgelendi"
    )
    assert SEANS_DURUMU_DONANIM_REDDI in durumlar, f"durum {durumlar}, beklenen {SEANS_DURUMU_DONANIM_REDDI}"


def test_KABUL_edilen_bobinle_seans_NORMAL_baslar(istemci, monkeypatch, seans_kapat):
    """⚠️ KARŞIT KANIT: kapı, sağlam donanımda seansı ENGELLEMEMELİ. Aşırı-kapılama,
    düzelttiğimiz arızanın tersi ama aynı ölçüde zararlıdır (tedavi hiç yapılamaz).
    """
    from servers import api_server

    monkeypatch.setattr(api_server.state, "hardware", SahteDonanim(kabul=True))
    y = _seans_baslat(istemci)
    assert y.status_code == 200, f"saglam donanimda seans REDDEDILDI: {y.status_code} {y.text[:300]}"


# ============================================================================
# 2. CRC / FIRMWARE UYUŞMAZLIĞI — SİSTEMATİK RED KARARI
# ============================================================================


def test_KRITIK_sistematik_red_seans_baslatmayi_ENGELLER(istemci, monkeypatch, seans_kapat):
    """Kart komutları reddediyorken seans HİÇ denenmemeli — operatöre reflash söylenmeli.

    MUTASYON: `/session/start`taki `live_state.stm_komutlari_reddediyor()` kapısını sil →
    KIRMIZI (sahte donanım "kabul" dediği için seans 200 döner).
    """
    from servers import api_server, live_state

    monkeypatch.setattr(api_server.state, "hardware", SahteDonanim(kabul=True))
    for _ in range(live_state.STM_RED_ESIGI):
        live_state.stm_komut_reddi_bildir("STM_NACK: CRC")
    assert live_state.stm_komutlari_reddediyor(), "onkosul: sistematik red kurulamadi"

    y = _seans_baslat(istemci)
    assert y.status_code == 409, f"RED beklenirken {y.status_code}: {y.text[:300]}"
    assert "firmware" in y.text.lower()


def test_KRITIK_TEK_nack_seansi_engellemez(istemci, monkeypatch, seans_kapat):
    """⚠️ KARŞIT KANIT: tek bir NACK hat gürültüsü olabilir ve zaten yeniden gönderilir.
    Onu "sistematik red" saymak, sağlam bir kartta tedaviyi bloke ederdi.

    MUTASYON: `STM_RED_ESIGI`yi 1 yap → KIRMIZI.
    """
    from servers import api_server, live_state

    monkeypatch.setattr(api_server.state, "hardware", SahteDonanim(kabul=True))
    live_state.stm_komut_reddi_bildir("STM_NACK: CRC")
    assert not live_state.stm_komutlari_reddediyor(), "TEK nack sistematik red sayildi"
    assert _seans_baslat(istemci).status_code == 200


def test_KRITIK_KABUL_gelince_red_karari_SIFIRLANIR():
    """⚠️ Sıfırlama olmazsa eski bir gürültü NACK'i sayacı sonsuza dek yukarıda tutar ve
    sağlam kartta seans başlatmak KALICI olarak engellenir.

    MUTASYON: `hardware.stm.coil_update` dalındaki `stm_komut_kabulu_bildir()` çağrısını
    sil → KIRMIZI.
    """
    from servers import api_server, live_state

    for _ in range(live_state.STM_RED_ESIGI):
        live_state.stm_komut_reddi_bildir("STM_NACK: CRC")
    assert live_state.stm_komutlari_reddediyor()

    class _Olay:
        event_type = "hardware.stm.coil_update"
        data = {"coil_id": 1, "duty": 0.0, "freq": 0.0, "phase": 0.0, "duration_min": 0, "running": False}

    api_server._handle_backend_event(_Olay())
    assert not live_state.stm_komutlari_reddediyor(), "KABUL geldi ama red karari SIFIRLANMADI"


def test_KRITIK_red_karari_BAYATLAR():
    """⚠️ Kalıcı kilitlenme olmasın: yeni bilgi gelmezse karar geçerliliğini yitirir."""
    import time as _t

    from servers import live_state

    for _ in range(live_state.STM_RED_ESIGI):
        live_state.stm_komut_reddi_bildir("STM_NACK: CRC")
    assert live_state.stm_komutlari_reddediyor()
    gercek = _t.monotonic
    try:
        _t.monotonic = lambda: gercek() + live_state.STM_RED_GECERLILIK_S + 1.0
        assert not live_state.stm_komutlari_reddediyor(), "red karari BAYATLAMIYOR (kalici kilit)"
    finally:
        _t.monotonic = gercek


# ============================================================================
# 3. TIBBİ KAYIT DÜRÜSTLÜĞÜ — "Tamamlandı" YAZILMAZ
# ============================================================================


def test_KRITIK_reddedilen_seans_gecmise_TAMAMLANDI_yazilmaz():
    """⚠️ ARIZANIN KALICILAŞTIĞI YER BURASI: hiç başlamamış seans `'completed'` yazılınca,
    uygulanmamış bir tedavi geçmişte/PDF'te/KPI'de UYGULANMIŞ olarak belgelenir.

    MUTASYON: `_finalize_session_db`teki `donanim-reddi` dalını sil → KIRMIZI ("completed").
    """
    from database.treatment_history_db import SEANS_DURUMU_DONANIM_REDDI
    from servers import api_server

    assert SEANS_DURUMU_DONANIM_REDDI != "completed"
    src = (KOK / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8")
    assert 'elif _sebep.startswith("donanim-reddi"):' in src, "donanim-reddi dali kayboldu"
    assert hasattr(api_server, "_seansi_geri_al"), "geri alma yardimcisi kayboldu"


def test_KRITIK_donanim_reddi_durumu_TURKCE_gosterilir():
    """Yeni durum kodu iki etiket haritasında da olmalı; yoksa operatör ham
    "Hardware_rejected" görür (sahibin ilk şikâyetiyle aynı sınıf)."""
    from database.treatment_history_db import SEANS_DURUMU_DONANIM_REDDI
    from utils.seans_durum import durum_etiketi

    assert durum_etiketi(SEANS_DURUMU_DONANIM_REDDI) == "Donanım Reddetti"


def test_KRITIK_NACK_dali_aktif_seansi_DURDURUR():
    """⚠️ Seans BAŞLADIKTAN SONRA firmware reddetmeye başlarsa da kayıt yalan olmamalı.
    `watchdog_timeout` dalı bunu zaten doğru yapıyordu; NACK dalı yalnız bildirim basıyordu.

    MUTASYON: `_stm_red_aktif_seansi_durdur(_ham)` çağrısını sil → KIRMIZI.
    """
    src = (KOK / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8")
    i_nack = src.index('if event.event_type in {"hardware.stm.error", "hardware.stm.nack"}:')
    govde = src[i_nack : i_nack + 2000]
    assert "_stm_red_aktif_seansi_durdur(" in govde, (
        "NACK dali aktif seansi DURDURMUYOR -> sahte 'tamamlandi' geri geldi"
    )
    assert "live_state.stm_komut_reddi_bildir(" in govde, "NACK dali red sayacini artirmiyor"
    # ⚠️ SAYAÇ, BİLDİRİM BASTIRMASINDAN ÖNCE ARTMALI: sonra artsaydı susturma körlüğe dönerdi.
    assert govde.index("stm_komut_reddi_bildir(") < govde.index("_stm_nack_bastir("), (
        "red sayaci bildirim bastirmasindan SONRA artiyor -> sistematik red hic olusmaz"
    )


# ============================================================================
# 4. ⚠️ HAYALET BOBİN 8 / ESP — "7 bobinli sistem" (sahip, 2026-09-12)
# ============================================================================
#
# "seans detayında donanım eps kalmış ve bobin 8 de görünüyor ama aslında çalışmıyor,
#  7 bobinli sistem bunu da düzelt."
#
# ÖLÇÜLEN KÖK NEDEN: `_mqtt_publish` ESP kapalıyken hiç yayınlamıyor (doğru), ama seans
# yolundaki ESP döngüsü `_begin_coil_run`ı KOŞULSUZ çağırıyordu → bobin 8 için geçmişe
# "46 sn · 100 Hz · ESP" satırı yazılıyordu, o donanım ORTADA YOKKEN. Bobin kimliği
# verilmeyen seans `list(range(1, 9))`e düştüğü için bu VARSAYILAN yoldu.


def test_KRITIK_ESP_kapaliyken_bobin8_KOSU_SATIRI_yazilmaz(istemci, monkeypatch, seans_kapat, izole_db):
    """MUTASYON: `if esp_coils and not live_state.esp_etkin():` kapısını sil → KIRMIZI
    (bobin 8 için hayalet satır yazılır).
    """
    from servers import api_server, live_state

    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    assert not live_state.esp_etkin(), "onkosul: ESP kapali olmali"
    monkeypatch.setattr(api_server.state, "hardware", SahteDonanim(kabul=True))

    # ⚠️ BOBİN LİSTESİ VERİLMEDEN: arızanın gerçekleştiği VARSAYILAN yol (1..8'e düşer).
    y = istemci.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 100,
            "duty": 50,
            "phase": 0,
            "intensity": 0.0,
            "duration_minutes": 20,
            "patient_name": "Mia",
        },
    )
    assert y.status_code == 200, y.text
    istemci.post("/api/session/stop")

    seanslar = izole_db.get_session_history(limit=50)
    assert seanslar, "onkosul: seans satiri olusmadi"
    tum_kosular = [r for s in seanslar for r in izole_db.get_session_coil_runs(s["id"])]
    assert tum_kosular, "onkosul: hic kosu satiri yok -> kapi yanlis yeri olcuyor"
    hayalet = [r for r in tum_kosular if (r.get("hw_type") or "").lower() == "esp" or r.get("coil_id") == 8]
    assert not hayalet, (
        f"ESP kapaliyken HAYALET kosu satiri yazildi: {[(r.get('coil_id'), r.get('hw_type')) for r in hayalet]}"
    )


def test_KRITIK_ESP_ACIKKEN_eski_davranis_KORUNUR(monkeypatch):
    """⚠️ ESP KODU SİLİNMEDİ, YALNIZ KAPILANDI (sahip kararı 2026-09-11: "ilerde tekrar hibrit
    esp+stm'e dönebilirim"). Bayrak açılınca bobin 8 yine seans kapsamında OLMALI.

    MUTASYON: kapıyı `if esp_coils:` yap (bayrağı yok say) → KIRMIZI.
    """
    from servers import live_state

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    assert live_state.esp_etkin(), "bayrak acikken ESP etkin olmali"
    src = (KOK / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8")
    assert "if esp_coils and not live_state.esp_etkin():" in src, (
        "ESP kapisi bayraktan BAGIMSIZ hale gelmis -> geri donus tek satirlik olmaktan cikar"
    )


def test_KRITIK_arayuz_sokulu_ESP_satirini_ETIKETLER():
    """⚠️ ESKİ KAYITLAR SİLİNMEZ/GİZLENMEZ (tıbbi kayıt), ama "ESP" diye gösterilirse operatör
    onu HÂLÂ VAR OLAN bir donanım sanar. Etiket, kaydı korurken gerçeği de söyler.

    MUTASYON: `hwLabel`daki "ESP (sökülü)" değerini "ESP"ye geri çevir → KIRMIZI.
    """
    from c_soyucu import c_soy

    src = c_soy((_PF / "components" / "domain" / "SessionDetailModal.tsx").read_text(encoding="utf-8"))
    assert '"ESP (sökülü)"' in src, "sokulu ESP satiri hala sanki mevcut donanimmis gibi gosteriliyor"
    assert "seans-sokulu-uyarisi" in src, "eski ESP satiri tasiyan seansta aciklama uyarisi YOK"
