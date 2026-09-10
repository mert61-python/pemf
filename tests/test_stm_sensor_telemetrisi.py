# -*- coding: utf-8 -*-
# Author: mertaygn
"""BOBİN 6-7 SENSÖR TELEMETRİSİ (`STM_TELE`) — ESP'den STM'e taşınan ölçüm yolu.

FAZ 3 (2026-09-10). Bobin 6-7 ESP8266'dan STM32'ye taşınıyor; sensörler de STM'e bağlanıyor.
STM'in seri protokolünde sıcaklık/alan alanı **yoktu** (`api_server.py` bunu açıkça yazıyor:
"STM bobinlerinde (1-5) sicaklik/akim/alan telemetrisi YOKTUR"), bu yüzden yeni bir satır
sözleşmesi eklendi:

    -> STM_TELE: C=6,T=34.20,A=27.10,B=1.842

⚠️ **NEDEN BU KAPI GÜVENLİK KAPISI:** sahip kararıyla bobin 6-7'de **cihaz-taraflı termal
kesme YOK**. Kalan tek otomatik katman arayüzdeki 48 °C istemci interlock'u
(`pf/src/components/domain/CoilParameterPanel.tsx:21,143`) ve o interlock `objectTemp`in
arayüze **ULAŞMASINA** bağlı. Bu zincir kopunca hiçbir hata görünmez: kart sıcaklığı okur,
kimse duymaz, bobin ısınmaya devam eder. Zincirin her halkası burada ölçülüyor.

⚠️ **İKİNCİ İDDİA — ÖLÇÜLMEYEN ALAN GÖNDERİLMEZ:** akım sensörü (ACS712) taşınmıyor
(sahip kararı 3) ve sıcaklık/alan da arızada gelmez. Eksik alanı `0.0` ile doldurmak, aşağı
akışta "ölçüldü" olarak kaydedilir — geçmişte tam bu desen hasta sahibine giden PDF'e
"0.0 °C ölçüldü" yazdırmıştı. Bu yüzden eksik alanın **anahtarı bile konmaz**.

BU KAPI DAVRANIŞ ÖLÇER: gerçek `_parse_stm_tele` gerçek satırlarla sürülür, gerçek
`_handle_backend_event` gerçek bir olayla sürülür ve `_live_state` + WS kuyruğu + telemetri
damgası okunur.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.pop("PEMF_SIMULATE", None)

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))


# ── 1. Firmware → satır → olay gövdesi ───────────────────────────────────────


@pytest.fixture()
def ayristir():
    import headless_core as hc

    class _Sahte:
        _TELE_DESENI = hc.HeadlessCore._TELE_DESENI

    return lambda s: hc.HeadlessCore.__dict__["_parse_stm_tele"](_Sahte(), s)


def test_KRITIK_tam_satir_UC_alani_da_tasir(ayristir):
    g = ayristir("-> STM_TELE: C=6,T=34.20,A=27.10,B=1.842")
    assert g == {
        "coil_id": 6,
        "object_temp": 34.20,
        "ambient_temp": 27.10,
        "magnetic_field": 1.842,
    }, g


def test_KRITIK_EKSIK_alan_ANAHTARI_HIC_KONMAZ(ayristir):
    """Ölçülmeyen alan `0.0` DEĞİL, `None` DEĞİL — anahtar HİÇ YOK.

    MUTASYON: ayrıştırıcıda eksik alanı `govde[alan] = 0.0` yap → KIRMIZI.
    Sahadaki etki: DB'ye "0.0 °C ölçüldü" yazılır, PDF'te hasta sahibine beyan edilir.
    """
    g = ayristir("-> STM_TELE: C=7,B=0.512")
    assert g == {"coil_id": 7, "magnetic_field": 0.512}, g
    assert "object_temp" not in g and "ambient_temp" not in g


def test_KRITIK_akim_alani_SOZLESMEDE_VAR(ayristir):
    """⚠️ KAPI BİLİNÇLİ OLARAK TERSİNE ÇEVRİLDİ (2026-09-10, aynı gün ikinci karar).

    Önceki hâli `test_akim_alani_SOZLESMEDE_YOK` idi ve "ACS712 taşınmıyor (sahip kararı 3)
    → satırda akım alanı OLMAMALI" diyordu. Sahip kararını değiştirdi: bobin 1-5'e ACS712-30A
    bağlanacak ve STM'de 5 ADC kanalı açıldı (`pemf_akim.c`). Kapı, kararla birlikte çevrildi
    — eski iddia sessizce silinmedi, burada kayıtlı.

    ⚠️ Bobin 6-7'de ACS712 YOK: onların satırında `I=` HİÇ olmaz. Yani "akım alanı var"
    iddiası bobine göre değişir; ayrıştırıcı bunu ALANIN VARLIĞINDAN öğrenir, bobin
    numarasına göre TAHMİN ETMEZ.
    """
    g = ayristir("-> STM_TELE: C=1,I=0.350")
    assert g == {"coil_id": 1, "current": 0.350}, g
    # Karışık satır da desteklenir (ileride bir bobinde hepsi olabilir)
    h = ayristir("-> STM_TELE: C=6,T=30.00,A=25.00,B=1.000,I=0.350")
    assert h == {
        "coil_id": 6,
        "object_temp": 30.0,
        "ambient_temp": 25.0,
        "magnetic_field": 1.0,
        "current": 0.350,
    }, h


def test_KRITIK_ADC_DOYGUNLUGU_isaretli_gelir(ayristir):
    """`X=1` = ADC tavanına dayandı (bölücüsüz ~12 A üstü) → değer GÜVENİLMEZ.

    ⚠️ NEDEN ÖNEMLİ: ACS712-30A 0 A'da 2,50 V verir ve 66 mV/A ile 3,30 V'a **+12,1 A**'da
    dayanır. STM32'nin ADC'si orada kırpar; kırpılmış sayı sessizce doz kaydına girerse
    "12 A ölçüldü" der ama gerçek akım 25 A olabilir. İşaret yutulmamalı.

    MUTASYON: ayrıştırıcıdan `X` grubunu sil → KIRMIZI.
    """
    g = ayristir("-> STM_TELE: C=3,I=12.100,X=1")
    assert g["current"] == 12.1 and g.get("current_saturated") is True, g
    t = ayristir("-> STM_TELE: C=3,I=2.000")
    assert "current_saturated" not in t, t


def test_yalniz_X_tasiyan_satir_OLCUM_SAYILMAZ(ayristir):
    """`X` tek başına bir ölçüm değildir → satır reddedilir (sahte damga atılmasın)."""
    assert ayristir("-> STM_TELE: C=3,X=1") is None


@pytest.mark.parametrize(
    "satir",
    [
        "-> STM_TELE: C=6",  # yalniz kimlik → tasinacak olcum yok
        "-> STM_TELE: C=99,T=1.0",  # gecersiz bobin
        "-> STM_OK: D=0,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=1,1,1,1,1,1,1 T=0,0,0,0,0,0,0",
        "-> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak + HW_SYNC@PB1)",
        "",
    ],
)
def test_alakasiz_ve_bos_satirlar_REDDEDILIR(ayristir, satir):
    assert ayristir(satir) is None, satir


def test_negatif_sicaklik_KABUL_EDILIR(ayristir):
    """MLX90614 −40 °C'ye kadar okur; eksi işaret yutulursa soğuk bobin sıcak görünür."""
    g = ayristir("-> STM_TELE: C=6,T=-12.50,A=-3.25")
    assert g["object_temp"] == -12.5 and g["ambient_temp"] == -3.25, g


# ── 2. Olay → live_state + WS + telemetri damgası ────────────────────────────


@pytest.fixture()
def kur(monkeypatch):
    from servers import api_server as api

    yayinlar: list[dict] = []
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: yayinlar.append(m))
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    with api._live_state_lock:
        for i in (5, 6):
            api._live_state["coils"][i]["objectTemp"] = 0.0
            api._live_state["coils"][i]["ambientTemp"] = 0.0
            api._live_state["coils"][i]["magneticMt"] = 0.0
    api._coil_last_telemetry.pop(5, None)
    api._coil_last_telemetry.pop(6, None)
    return api, yayinlar


class _Olay:
    def __init__(self, govde: dict, tip: str = "hardware.stm.telemetry"):
        self.event_type = tip
        self.data = govde


def _tip(yayinlar, tip, coil_id):
    for m in yayinlar:
        if m.get("type") == tip and m.get("coilId") == coil_id:
            return m
    return None


def test_KRITIK_olay_live_state_e_YAZAR_ve_YAYINLAR(kur):
    """Zincirin son halkası: olay → `_live_state` → `coil_status` + `sensor_data`.

    MUTASYON: `_ws_broadcast_sync` çağrılarını sil → KIRMIZI. Sahadaki etki: sıcaklık
    sunucuda durur, arayüze HİÇ gitmez → 48 °C istemci interlock'u ASLA tetiklenmez ve
    bobin 6-7 tamamen korumasız kalır (cihaz-taraflı kesme sahip kararıyla yok).
    """
    api, yayinlar = kur
    api._handle_backend_event(_Olay({"coil_id": 6, "object_temp": 41.7, "ambient_temp": 26.3, "magnetic_field": 1.842}))

    with api._live_state_lock:
        c = dict(api._live_state["coils"][5])
    assert c["objectTemp"] == 41.7 and c["ambientTemp"] == 26.3 and c["magneticMt"] == 1.842, c

    cs = _tip(yayinlar, "coil_status", 6)
    assert cs is not None, f"coil_status yayini GITMEDI: {[y.get('type') for y in yayinlar]}"
    assert cs["data"]["objectTemp"] == 41.7

    sd = _tip(yayinlar, "sensor_data", 6)
    assert sd is not None, "sensor_data yayini GITMEDI → grafik/kaydedici beslenmez"
    assert sd["data"]["objectTemp"] == 41.7 and sd["data"]["magneticMt"] == 1.842
    # ⚠️ 2026-09-10 (ikinci karar): `currentA` ARTIK sözleşmede — bobin 1-5'te ACS712 var.
    # Bu bobin (6) akım göndermediği için değer 0.0 KALIR ama `measuredFields` onu
    # ölçülmüş SAYMAZ → arayüz kısa çizgi gösterir, DB satır yazmaz.
    assert "currentA" in sd["data"], "sensor_data akim alanini tasimiyor"
    assert "currentA" not in (sd["data"].get("measuredFields") or []), (
        "bobin 6 akim OLCMUYOR ama measuredFields onu olculmus sayiyor → DB'ye 0.0 A yazilir"
    )


def test_KRITIK_telemetri_DAMGASI_atilir_yoksa_DB_satiri_URETILMEZ(kur):
    """`_coil_last_telemetry` damgası olmadan dakika-ortalaması bobini ATLAR.

    MUTASYON: `_coil_last_telemetry[_t_idx] = ...` satırını sil → KIRMIZI.
    Sahadaki etki: sıcaklık arayüzde görünür ama geçmiş/PDF/KPI'de HİÇ yer almaz —
    yani ölçüm var sanılır, kayıt yoktur.
    """
    api, _ = kur
    api._handle_backend_event(_Olay({"coil_id": 7, "object_temp": 33.1}))
    assert api._coil_last_telemetry.get(6) is not None, (
        "telemetri damgasi atilmadi → api_server'daki dakika-ortalamasi kapisi bu bobin icin "
        "HIC DB satiri uretmez (olcum sessizce kaybolur)"
    )


def test_EKSIK_alan_live_state_te_UZERINE_YAZMAZ(kur):
    """Alan gelmediyse mevcut değere DOKUNULMAZ — 0.0 ile ezilmez."""
    api, _ = kur
    with api._live_state_lock:
        api._live_state["coils"][5]["objectTemp"] = 39.9
    api._handle_backend_event(_Olay({"coil_id": 6, "magnetic_field": 2.5}))
    with api._live_state_lock:
        c = dict(api._live_state["coils"][5])
    assert c["objectTemp"] == 39.9, f"eksik alan 0.0 ile EZILDI: {c}"
    assert c["magneticMt"] == 2.5


def test_olcum_TASIMAYAN_olay_damga_ATMAZ(kur):
    """Yalnız `coil_id` taşıyan olay ölçüm değildir → damga atılmamalı, yayın gitmemeli."""
    api, yayinlar = kur
    api._handle_backend_event(_Olay({"coil_id": 6}))
    assert api._coil_last_telemetry.get(5) is None, "olcumsuz olay damga atti"
    assert _tip(yayinlar, "coil_status", 6) is None


def test_gecersiz_bobin_kimligi_state_i_BOZMAZ(kur):
    api, yayinlar = kur
    for govde in ({"coil_id": 0, "object_temp": 1.0}, {"coil_id": 42, "object_temp": 1.0}, {"coil_id": "x"}):
        api._handle_backend_event(_Olay(govde))
    assert yayinlar == [], f"gecersiz kimlik yayin uretti: {yayinlar}"


def test_KARSIT_KANIT_kapi_gercekten_olcuyor(kur):
    """Öz-test: yayın yakalayıcı ve filtre gerçekten ayırt ediyor mu?"""
    _api, yayinlar = kur
    assert _tip(yayinlar, "coil_status", 6) is None, "kurulum yayin uretmemeliydi"
    yayinlar.append({"type": "sensor_data", "coilId": 6, "data": {}})
    assert _tip(yayinlar, "coil_status", 6) is None, "filtre ALAKASIZ tipi coil_status sandi"
    assert _tip(yayinlar, "sensor_data", 6) is not None
    yayinlar.append({"type": "coil_status", "coilId": 7, "data": {}})
    assert _tip(yayinlar, "coil_status", 6) is None, "filtre YANLIS bobini esledi"


# ── 3. ALAN BAZINDA ÖLÇÜM KAYDI — sahte 0.0 satırı üretilmesin ───────────────


def test_KRITIK_measuredFields_YALNIZ_GELEN_alanlari_isaretler(kur):
    """Bobin 1-5 yalnız AKIM ölçer → `measuredFields` sıcaklık/alanı SAYMAMALI.

    ⚠️ NEDEN BU KAPI: bobin bazında "telemetri geldi mi" damgası 2026-09-10'da YETERSİZ
    kaldı. Bobin 1-5'e ACS712 eklendi ve o bobinler artık telemetri gönderiyor; damga
    atılınca dakika-ortalaması döngüsü `objectTemp`/`magneticMt` alanlarını da biriktirmeye
    başlar ve başlangıç değeri 0.0 olduğu için DB'ye **"0.0 °C ölçüldü, sample_count=30"**
    yazar — hasta sahibine giden PDF'te uygulanmamış bir ölçüm beyan edilir.

    MUTASYON: handler'da `_t_kume.add(_hedef)` satırını sil → KIRMIZI.
    """
    api, _ = kur
    api._coil_olculen_alanlar.pop(0, None)
    api._handle_backend_event(_Olay({"coil_id": 1, "current": 0.412}))

    with api._live_state_lock:
        c = dict(api._live_state["coils"][0])
    assert c["currentA"] == 0.412
    assert c["measuredFields"] == ["currentA"], (
        f"measuredFields {c['measuredFields']!r} — bobin 1'de SICAKLIK/ALAN sensoru YOK, "
        "onlari olculmus saymak DB'ye '0.0 °C olculdu' yazdirir"
    )


def test_KRITIK_dakika_akumulatoru_OLCULMEYEN_alani_BIRIKTIRMEZ(kur, monkeypatch):
    """Akümülatör yalnız `measuredFields`teki alanları toplamalı.

    ⚠️ Bu, yukarıdaki iddianın DB ayağı: `_live_state` doğru olsa bile akümülatör
    `if temp is not None` ile 0.0'ı gerçek ölçüm sayarsa satır yine yazılır.
    MUTASYON: akümülatörde `and "objectTemp" in _olculen` koşulunu sil → KIRMIZI.
    """
    api, _ = kur
    api._coil_olculen_alanlar.pop(0, None)
    api._handle_backend_event(_Olay({"coil_id": 1, "current": 0.5}))

    # Akümülatörün TEK turunu elle koştur (sonsuz döngüyü çalıştırmadan).
    with api._minute_acc_lock:
        api._minute_acc.pop(1, None)
    with api._live_state_lock:
        api._live_state["coils"][0]["running"] = True
    with api._session_lock:
        api._active_session["is_active"] = True
    try:
        _Dur = type("_Dur", (Exception,), {})
        monkeypatch.setattr(api.time, "sleep", lambda _s: (_ for _ in ()).throw(_Dur()))
        with pytest.raises(_Dur):
            api._sensor_persistence_loop()
    finally:
        with api._session_lock:
            api._active_session["is_active"] = False
        with api._live_state_lock:
            api._live_state["coils"][0]["running"] = False

    with api._minute_acc_lock:
        acc = dict(api._minute_acc.get(1) or {})
    assert acc, "akumulator bobin 1 icin hic tur islemedi (test kurgusu bozuk)"
    assert acc["i_n"] > 0, "AKIM biriktirilmedi — gercek olcum kayboluyor"
    assert acc["t_n"] == 0, (
        f"SICAKLIK biriktirildi (t_n={acc['t_n']}) ama bobin 1'de sensor YOK → "
        "DB'ye '0.0 °C olculdu' satiri yazilir (PDF'te uygulanmamis olcum beyani)"
    )
    assert acc["b_n"] == 0, f"ALAN biriktirildi (b_n={acc['b_n']}) ama bobin 1'de sensor YOK"


def test_KRITIK_ADC_doygunlugu_operatore_bildirilir_ve_TEKRARLAMAZ(kur, monkeypatch):
    """`X=1` → uyarı çıkmalı; ama her saniye DEĞİL (alarm yorgunluğu).

    ⚠️ Doygun akım doz kaydına giriyor: operatör "12 A" görürken gerçek 25 A olabilir.
    Sessiz kalmak kabul edilemez. Ama 1 Hz'de bildirim basmak da gerçek olayları boğar →
    yalnız 0→1 GEÇİŞİNDE bildir.
    MUTASYON: geçiş kontrolünü (`if _t_doygun != ...`) kaldır → ikinci assert KIRMIZI.
    """
    api, _ = kur
    bildirimler: list = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": bildirimler.append((msg, sev)))
    api._akim_doygun_son.pop(2, None)

    api._handle_backend_event(_Olay({"coil_id": 3, "current": 12.1, "current_saturated": True}))
    assert any("aral" in m.lower() for m, _ in bildirimler), (
        f"ADC doygunlugu operatore BILDIRILMEDI: {bildirimler!r} — kirpilmis akim sessizce doz kaydina girer"
    )
    ilk = len(bildirimler)
    api._handle_backend_event(_Olay({"coil_id": 3, "current": 12.1, "current_saturated": True}))
    assert len(bildirimler) == ilk, (
        f"doygunluk SURERKEN her turda bildirim basiliyor ({len(bildirimler)} > {ilk}) — "
        "alarm yorgunlugu, gercek olaylar bogulur"
    )
    # Normale dönüş yeni bir episode açmalı (bir daha doygunlukta yine uyarılsın).
    api._handle_backend_event(_Olay({"coil_id": 3, "current": 2.0}))
    api._handle_backend_event(_Olay({"coil_id": 3, "current": 12.1, "current_saturated": True}))
    assert len(bildirimler) > ilk, "normale dondukten sonraki YENI doygunluk bildirilmedi"
