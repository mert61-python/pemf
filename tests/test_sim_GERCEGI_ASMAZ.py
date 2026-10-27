# -*- coding: utf-8 -*-
"""SİMÜLATÖR GERÇEĞİ AŞMASIN — `PEMF_SIMULATE=1` ürünü fazla iyimser göstermesin.

SAHİP BİLDİRİMİ (2026-09-20): "stm bağlı gibi ama o da bayat çünkü bobini 7 tane STM'e
koyduk, ESP çıkardık."

ÖLÇÜLEN ÜÇ BAYATLIK — üçü de simülasyonu üründen İYİ gösteriyordu:
  1. `for idx in range(8)` ELLE yazılmıştı. Topoloji tek kaynak `live_state`
     (`STM_COIL_IDS`/`ESP_COIL_IDS`); 2026-09-10'da bobin 6-7 ESP'den STM'e taşındı ve
     bu döngü onu HİÇ görmedi. Aynı kural iki yerde → sessiz ayrışma.
  2. 🔴 HER bobine `objectTemp` uyduruyordu. STM protokolünde sıcaklık alanı YOK
     (`tools/stm32_simulator.py` 121 baytlık pakette yok) ve backend'de `objectTemp`
     YALNIZ MQTT yükünden gelir. Sim, sıcaklık bildiremeyen bobinleri bildiriyor gibi
     gösterince arayüzün "bu bobinde sıcaklık ölçümü yok — otomatik termal durdurma
     uygulanmaz" uyarısı SİMÜLASYONDA KAYBOLUYORDU: var olmayan bir koruma yeşil görünürdü.
  3. `mqtt`/`gateway` KOŞULSUZ "online" idi; ESP kapalıyken MQTT yoktur.

⚠️ BU KAPI SAYI SABİTLEMEZ. "8 bobin" ya da "7 bobin" yazmak, düzelttiğimiz bayatlığın
   ta kendisidir. İddia: sim döngüsü kapsamını `live_state`'TEN TÜRETİR.
"""

from __future__ import annotations

import ast
import os
import time
from pathlib import Path

import pytest
from utils.path_utils import kaynak_kokunu_bul

KOK = kaynak_kokunu_bul(__file__)
API = KOK / "apps" / "backend" / "servers" / "api_server.py"
PANEL = KOK / "apps" / "ui" / "src" / "components" / "domain" / "CoilParameterPanel.tsx"


def _sim_fonksiyonu() -> ast.FunctionDef:
    agac = ast.parse(API.read_text(encoding="utf-8"))
    for d in ast.walk(agac):
        if isinstance(d, ast.FunctionDef) and d.name == "_hardware_simulation_loop":
            return d
    raise AssertionError("_hardware_simulation_loop bulunamadı — sim yolu silinmiş olabilir")


# ──────────────────────────────────────────────────────────────────────────
# 1) KAPSAM — sayı elle yazılmasın, live_state'ten türesin
# ──────────────────────────────────────────────────────────────────────────


def test_sim_kapsami_ELLE_YAZILMAZ():
    """`range(8)` gibi sabit kapsam YASAK — topoloji değişince sessizce bayatlar."""
    fn = _sim_fonksiyonu()
    sabitler = []
    for d in ast.walk(fn):
        if (
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Name)
            and d.func.id == "range"
            # ⚠️ MUTASYON N1 BUNU KACIRDI: yalniz `range(8)` araniyordu, `range(1, 9)`
            # iki argumanli oldugu icin gorunmuyordu. Artik TUM argumanlari sabit olan
            # her `range(...)` yasak — kapsam kaynaktan TUREMELI.
            and d.args
            and all(isinstance(a, ast.Constant) and isinstance(a.value, int) for a in d.args)
        ):
            sabitler.append((d.lineno, tuple(a.value for a in d.args)))
    assert not sabitler, (
        f"sim döngüsünde SABİT kapsam: {sabitler}. Bobin sayısı `live_state.STM_COIL_IDS` / "
        "`ESP_COIL_IDS`'ten türetilmeli — 2026-09-10 taşımasını tam bu yüzden kaçırdı."
    )


def test_sim_kapsami_LIVE_STATETEN_TURER():
    """Kapsam iki kümeden de beslenmeli; biri düşerse bobin sessizce kaybolur.

    ⚠️ MUTASYON N2 BUNU KACIRDI: dize araması yapıyordum ve `STM_COIL_IDS` bu testin
    KENDİ docstring'inde geçtiği için kapı yeşil kaldı. Bu depoda "yorum kapıyı kandırdı"
    sınıfının yeni vakası. Artık AST'de GERÇEK nitelik erişimi aranıyor.
    """
    fn = _sim_fonksiyonu()
    erisimler = {
        d.attr
        for d in ast.walk(fn)
        if isinstance(d, ast.Attribute) and isinstance(d.value, ast.Name) and d.value.id == "live_state"
    }
    for ad in ("STM_COIL_IDS", "ESP_COIL_IDS"):
        assert ad in erisimler, (
            f"sim döngüsü kodunda `live_state.{ad}` erişimi YOK (bulunan: {sorted(erisimler)}) — "
            "kapsam tek kaynaktan türemiyor, taşımada sessizce bayatlar."
        )


# ──────────────────────────────────────────────────────────────────────────
# 2) SICAKLIK — ölçemeyen bobin ölçüyormuş gibi görünmesin  🔴
# ──────────────────────────────────────────────────────────────────────────


def test_sicaklik_KOSULSUZ_URETILMEZ():
    """`objectTemp` ataması koşulsuzsa var olmayan termal koruma yeşil görünür."""
    kaynak = ast.get_source_segment(API.read_text(encoding="utf-8"), _sim_fonksiyonu()) or ""
    assert "sicaklik_olculur" in kaynak, (
        "sim, sıcaklığı KOŞULSUZ üretiyor. STM bobinleri gerçekte sıcaklık bildirmez; "
        "sim bildirirse arayüzdeki 'termal durdurma uygulanmaz' uyarısı KAYBOLUR."
    )
    fn = _sim_fonksiyonu()
    kosulsuz = []
    for d in ast.walk(fn):
        if not isinstance(d, ast.Assign):
            continue
        for h in d.targets:
            if (
                isinstance(h, ast.Subscript)
                and isinstance(h.slice, ast.Constant)
                and h.slice.value in ("objectTemp", "ambientTemp")
                and not isinstance(d.value, ast.IfExp)
            ):
                kosulsuz.append((d.lineno, h.slice.value))
    assert not kosulsuz, f"koşulsuz sıcaklık ataması: {kosulsuz}. Ölçebilen bobin dışında `None` olmalı."


# ──────────────────────────────────────────────────────────────────────────
# 3) MQTT/GATEWAY — kurulu olmayan alt sistem "online" demesin
# ──────────────────────────────────────────────────────────────────────────


def test_mqtt_kosulsuz_ONLINE_DEMEZ():
    """`mqtt`/`gateway` ataması KOŞULLU olmalı (ESP kapalıyken 'online' diyemez).

    ⚠️ MUTASYON N4 BUNU KACIRDI ve sebebi tamamen bendeydi: haystack'ten boşlukları
    siliyor ama aradığım dizede boşluk bırakıyordum → hiçbir zaman eşleşmezdi. Vakum
    testi olmuş. Artık AST: atamanın değeri koşullu ifade (IfExp) olmak ZORUNDA.
    """
    fn = _sim_fonksiyonu()
    kosulsuz = []
    for d in ast.walk(fn):
        if not isinstance(d, ast.Assign):
            continue
        for h in d.targets:
            if (
                isinstance(h, ast.Subscript)
                and isinstance(h.slice, ast.Constant)
                and h.slice.value in ("mqtt", "gateway")
                and not isinstance(d.value, ast.IfExp)
            ):
                kosulsuz.append((d.lineno, h.slice.value))
    assert not kosulsuz, (
        f"koşulsuz durum ataması: {kosulsuz}. ESP kapalıyken MQTT yoktur; kurulu olmayan "
        "alt sistemi 'online' göstermek simülasyonu üründen iyi yapar."
    )
    cagrilar = {d.func.attr for d in ast.walk(fn) if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)}
    assert "esp_etkin" in cagrilar, (
        "sim, durumu `live_state.esp_etkin()` ÇAĞRISINA bağlamıyor (docstring'de geçmesi sayılmaz)."
    )


# ──────────────────────────────────────────────────────────────────────────
# 4) BELGE — arayüz yorumunda SAYI sabitlenmesin (bayatlığın kaynağı)
# ──────────────────────────────────────────────────────────────────────────


def test_ui_yorumu_SAYI_SABITLEMEZ():
    """Panel yorumunda '8 bobinin 5'i' gibi sabit sayı, taşımada BAYATLAR."""
    s = PANEL.read_text(encoding="utf-8")
    assert "8 bobinin 5'i" not in s, (
        "arayüz yorumu hâlâ '8 bobinin 5'i' diyor — bobin 6-7 2026-09-10'da STM'e taşındı, "
        "gerçek 8'in 7'si. Sayı yerine `live_state.STM_COIL_IDS` anılmalı."
    )
    assert "STM_COIL_IDS" in s, "yorum tek kaynağı (live_state.STM_COIL_IDS) anmıyor."


# ──────────────────────────────────────────────────────────────────────────
# 5) DAVRANIŞ — sim GERÇEKTEN böyle yayın yapıyor mu
# ──────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────
# İZOLASYON — bu kapı PAYLAŞILAN durumu mutasyona uğratıyor
# ──────────────────────────────────────────────────────────────────────────
#
# 🔴 ÖLÇÜLEN SIZINTI (2026-09-20, tam süit): ilk yazımda `importlib.reload(live_state)`
#    kullanıyordum. Reload modülü KÜRESEL olarak yeniden kurar; `_live_state` sözlüğüne
#    referans tutan öteki modüller eski nesnede kalır ve ayrışır. Sonuç: tam süitte
#    `test_stm_surus_kipi_ucu::test_KRITIK_yetenek_tavani_CANLI_DURUMDAN_okunur_SABIT_DEGIL`
#    KIRMIZI oldu — ürün hatası DEĞİL, BU TESTİN sızıntısıydı (tek başına yeşildi).
#    Ayrıca sim döngüsü `_live_state["coils"]`i yazar; sonraki testler onu okur.
# ÇÖZÜM: reload YOK (esp_etkin doğrudan yamalanır) + `_live_state` anlık görüntüsü
#    alınıp KOŞULSUZ geri yüklenir.


@pytest.fixture()
def izole_sim(monkeypatch):
    """(api, live_state) — esp KAPALI, paylaşılan durum sonradan GERİ YÜKLENİR."""
    import copy

    from servers import api_server as api
    from servers import live_state

    monkeypatch.setattr(live_state, "esp_etkin", lambda: False)
    monkeypatch.setattr(api.live_state, "esp_etkin", lambda: False, raising=False)
    with api._live_state_lock:
        yedek = copy.deepcopy(api._live_state)
    try:
        yield api, live_state
    finally:
        with api._live_state_lock:
            api._live_state.clear()
            api._live_state.update(yedek)


def _tek_tur(api, monkeypatch, yayin_kancasi=None) -> list[dict]:
    """Sim döngüsünü BİR TUR koştur, yayınları döndür.

    ⚠️ D1.41 (B-10.257): `time.sleep` eskiden SÜREÇ GENELİNDE `KeyboardInterrupt` fırlatan bir lambdaya
    yamanıyordu — yama penceresinde uyumaya giren HER iş parçacığı (çalışıyorsa gerçek `session-watchdog`:
    süre dolunca bobini durduran TEK yazılım mekanizması) KeyboardInterrupt ile ÖLÜYOR, sonraki testler
    watchdog'suz koşuyordu. Artık yalnız BU iş parçacığının uykusu turu bitirir; diğerleri gerçek uykuyu görür.
    Kapı: `test_KRITIK_tek_tur_yamasi_BASKA_is_parcacigini_OLDURMEZ`."""
    import threading
    import time as _gercek_time

    ana = threading.current_thread()
    gercek_uyku = _gercek_time.sleep

    def _uyku(sn):
        if threading.current_thread() is ana:
            raise KeyboardInterrupt
        return gercek_uyku(sn)

    yayinlar: list[dict] = []

    def _yayin(m):
        yayinlar.append(m)
        if yayin_kancasi:
            yayin_kancasi()

    monkeypatch.setattr(api, "_ws_broadcast_sync", _yayin)
    monkeypatch.setattr(_gercek_time, "sleep", _uyku)
    try:
        api._hardware_simulation_loop()
    except KeyboardInterrupt:
        pass
    finally:
        monkeypatch.setattr(_gercek_time, "sleep", gercek_uyku)
    return yayinlar


def test_KRITIK_tek_tur_yamasi_BASKA_is_parcacigini_OLDURMEZ(izole_sim, monkeypatch):
    """D1.41: yama penceresinde UYUYAN başka bir iş parçacığı (watchdog yerine geçen döngü) YAŞAMALI.

    Senkron: tur, ilk yayında, nöbetçi iş parçacığı yama altında en az iki uyku tamamlayana (ya da ölene)
    kadar bekletilir — eski süreç geneli yamada nöbetçi ilk uykuda KeyboardInterrupt ile ölür (ölçüldü)."""
    import threading
    import time as _t

    api, _ls = izole_sim
    durum = {"tur": 0, "dur": False}

    def _nobetci():
        while not durum["dur"]:
            _t.sleep(0.005)
            durum["tur"] += 1

    th = threading.Thread(target=_nobetci, daemon=True, name="d141-nobetci")
    th.start()
    while durum["tur"] < 1:  # nöbetçi ÇALIŞIYOR (yama öncesi)
        _t.perf_counter()

    def _kanca():
        hedef = durum["tur"] + 2
        bitis = _t.perf_counter() + 2.0
        while durum["tur"] < hedef and th.is_alive() and _t.perf_counter() < bitis:
            pass

    try:
        yayinlar = _tek_tur(api, monkeypatch, yayin_kancasi=_kanca)
        assert yayinlar, "aparat: sim turu hiç yayın yapmadı (kanca koşmadı)"
        assert th.is_alive(), "sim tek-tur yaması BAŞKA bir iş parçacığını öldürdü (süreç geneli sleep yaması)"
    finally:
        durum["dur"] = True
        th.join(timeout=2)


def test_DAVRANIS_sim_STM_bobinine_sicaklik_VERMEZ(izole_sim, monkeypatch):
    """Sim bir tur: STM bobinlerinde objectTemp None olmalı, kapsam topolojiye EŞİT.

    ⚠️ Yapısal iddialar doğruyken bile davranış yanlış olabilir — çıpa gerçek çıktıya pinli.
    """
    api, live_state = izole_sim
    yayinlar = _tek_tur(api, monkeypatch)

    coil_yayinlari = [m for m in yayinlar if m.get("type") == "coil_status"]
    assert coil_yayinlari, "sim hiç bobin durumu yayınlamadı — döngü koşmadı (VAKUM)"

    stm = set(live_state.STM_COIL_IDS)
    esp = set(live_state.ESP_COIL_IDS)
    for m in coil_yayinlari:
        cid = m.get("coilId")
        temp = (m.get("data") or {}).get("objectTemp")
        if cid in stm:
            assert temp is None, (
                f"bobin {cid} STM'de ama sim {temp}°C uydurdu — gerçekte STM protokolünde "
                "sıcaklık alanı YOK; bu, var olmayan termal korumayı yeşil gösterir."
            )
    yayinlanan = {m.get("coilId") for m in coil_yayinlari}
    assert yayinlanan == (stm | esp), (
        f"sim {sorted(yayinlanan)} yayınladı, topoloji {sorted(stm | esp)} — kapsam AYRIŞTI."
    )
    # ⚠️ D5.58 (B-10.177): yalnız `coil_status` ölçülüyordu — `sensor_data` yayını (Sensör ekranı / grafik / dakika ortalaması
    # bunu dinler) kendi sözlüğünü kurar; orada STM bobinine 24.0 °C uydurulsa bu kapı YEŞİLDİ (ölçüldü). İki yayın da ölçülür.
    sensor_yayinlari = [m for m in yayinlar if m.get("type") == "sensor_data"]
    assert {m.get("coilId") for m in sensor_yayinlari} == (stm | esp), (
        "sim sensor_data yayınlamadı / kapsam AYRIŞTI (VAKUM)"
    )
    for m in sensor_yayinlari:
        cid = m.get("coilId")
        if cid in stm:
            d = m.get("data") or {}
            assert d.get("objectTemp") is None and d.get("ambientTemp") is None, (
                f"bobin {cid} STM'de ama sim sensor_data yayınında sıcaklık uydurdu: {d}"
            )


def _cok_tur(api, monkeypatch, saat_adimlari=(0.0, 1800.0, 36000.0)) -> list[list[dict]]:
    """Sim döngüsünü `len(saat_adimlari)` TUR koştur; tur k, döngü başlangıcından `saat_adimlari[k]` sn SONRA koşar.

    Sahte saat ve tur sonu YALNIZ bu iş parçacığında (`_tek_tur` / D1.41 ilkesi): öteki iş parçacıkları gerçek `time.time`
    ve gerçek uykuyu görür. Uyku gerçekten beklenmez — saat ileri atlar (ikinci / sonraki turlar "zaman geçmiş" dalı)."""
    import threading
    import time as _gercek_time

    ana = threading.current_thread()
    gercek_uyku = _gercek_time.sleep
    gercek_saat = _gercek_time.time
    adimlar = list(saat_adimlari)
    kayma = {"sn": 0.0}
    turlar: list[list[dict]] = [[]]

    def _saat():
        return gercek_saat() + (kayma["sn"] if threading.current_thread() is ana else 0.0)

    def _uyku(sn):
        if threading.current_thread() is not ana:
            return gercek_uyku(sn)
        if len(turlar) >= len(adimlar):
            raise KeyboardInterrupt
        kayma["sn"] = adimlar[len(turlar)]
        turlar.append([])

    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: turlar[-1].append(m))
    monkeypatch.setattr(_gercek_time, "sleep", _uyku)
    monkeypatch.setattr(_gercek_time, "time", _saat)
    try:
        api._hardware_simulation_loop()
    except KeyboardInterrupt:
        pass
    finally:
        monkeypatch.setattr(_gercek_time, "sleep", gercek_uyku)
        monkeypatch.setattr(_gercek_time, "time", gercek_saat)
    return turlar


@pytest.mark.parametrize("esp_acik", [False, True], ids=["esp_kapali", "esp_acik"])
@pytest.mark.parametrize("seans", [False, True], ids=["bosta", "seans_tum_bobinler"])
def test_KRITIK_DAVRANIS_sim_STM_sicaklik_VERMEZ_seans_x_ESP_x_TUR_D5_58(izole_sim, monkeypatch, seans, esp_acik):
    """D5.58 TUR 2 (çürütme b1 / b2 / b3): yukarıdaki kapı TEK tur, SEANSSIZ, ESP KAPALI koşuyordu — yalnız boşta dalı ölçülüyordu.
    Ölçüldü (hepsi YEŞİLDİ): çalışan bobin dalında STM'e sıcaklık (`if running`; e2e kontrolleri tam da SEANS sırasında koşar) ·
    ESP açıkken HER bobine sıcaklık (`(cid in _esp) or esp_acik`) · ilk turda None, sonraki turlarda 24 °C (`or el > 0.25`).
    Artık {boşta, tüm bobinlerde aktif seans} × {ESP kapalı, açık} × 3 tur (t = 0 sn, 30 dk, 10 sa): her turda `coil_status` VE
    `sensor_data` yayınında STM bobinlerinin `objectTemp` / `ambientTemp` None. Öncüller (vakum karşıtı): her tur topolojinin
    tamamını yayınlar; seansta STM bobinleri `running`; ESP açıkken ESP bobini sıcaklık BİLDİRİR (ölçen yol gerçekten koştu)."""
    api, live_state = izole_sim
    monkeypatch.setattr(live_state, "esp_etkin", lambda: esp_acik)
    monkeypatch.setattr(api.live_state, "esp_etkin", lambda: esp_acik, raising=False)
    stm = set(live_state.STM_COIL_IDS)
    esp = set(live_state.ESP_COIL_IDS)
    assert stm, "öncül: topolojide STM bobini yok (VAKUM)"
    oturum = {"is_active": True, "frequency": 40.0, "duty": 30.0, "coil_ids": sorted(stm | esp)} if seans else {}
    # Paylaşılan seans sözlüğüne DOKUNULMAZ (D1.41 nöbeti): yalnız modül bağlaması bu tur için değişir, finally'de geri gelir.
    gercek_oturum = api._active_session
    api._active_session = oturum
    try:
        turlar = _cok_tur(api, monkeypatch)
    finally:
        api._active_session = gercek_oturum
    assert len(turlar) == 3, f"aparat: sim {len(turlar)} tur koştu (3 bekleniyordu)"
    for no, yayinlar in enumerate(turlar, start=1):
        for tur in ("coil_status", "sensor_data"):
            kume = {m.get("coilId") for m in yayinlar if m.get("type") == tur}
            assert kume == (stm | esp), (
                f"tur {no}: sim {tur} kapsamı {sorted(kume)} ≠ topoloji {sorted(stm | esp)} (VAKUM)"
            )
        for m in yayinlar:
            if m.get("type") not in ("coil_status", "sensor_data"):
                continue
            cid, d = m.get("coilId"), (m.get("data") or {})
            if cid in stm:
                assert d.get("objectTemp") is None and d.get("ambientTemp") is None, (
                    f"tur {no} ({'seans' if seans else 'boşta'}, ESP {'açık' if esp_acik else 'kapalı'}): bobin {cid} STM'de ama "
                    f"sim {m.get('type')} yayınında sıcaklık uydurdu: objectTemp={d.get('objectTemp')!r} "
                    f"ambientTemp={d.get('ambientTemp')!r} — STM protokolünde sıcaklık alanı YOK"
                )
                if seans and m.get("type") == "coil_status":
                    assert d.get("running") is True, (
                        f"öncül: seans aktifken STM bobini {cid} çalışmıyor (çalışan dal ölçülmedi)"
                    )
            elif cid in esp and esp_acik:
                assert d.get("objectTemp") is not None, (
                    f"öncül: ESP açıkken ESP bobini {cid} sıcaklık bildirmedi ({m.get('type')}) — ölçen yol koşmadı"
                )


def test_DAVRANIS_esp_kapaliyken_mqtt_online_DEMEZ(izole_sim, monkeypatch):
    api, live_state = izole_sim
    assert live_state.esp_etkin() is False, "öncül geçersiz — esp_etkin yamalanmamış"
    yayinlar = _tek_tur(api, monkeypatch)

    kapi = [m for m in yayinlar if m.get("type") == "gateway_status"]
    assert kapi, "gateway durumu hiç yayınlanmadı (VAKUM)"
    for m in kapi:
        assert (m.get("data") or {}).get("mqtt") != "online", (
            "ESP kapalıyken sim MQTT'yi 'online' ilan etti — kurulu olmayan alt sistem çalışıyor gösteriliyor."
        )


def test_zaman_damgasi_ARACIN_KENDISI(tmp_path):
    """Vakum karşıtı: kaynak dosyalar gerçekten okunabiliyor mu (kapı boşa koşmasın)."""
    assert API.is_file() and PANEL.is_file()
    assert os.path.getsize(API) > 10_000
    assert time.time() > 0
