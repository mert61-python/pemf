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


def _tek_tur(api, monkeypatch) -> list[dict]:
    """Sim döngüsünü BİR TUR koştur, yayınları döndür."""
    import time as _gercek_time

    yayinlar: list[dict] = []
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: yayinlar.append(m))
    monkeypatch.setattr(_gercek_time, "sleep", lambda _s: (_ for _ in ()).throw(KeyboardInterrupt))
    try:
        api._hardware_simulation_loop()
    except KeyboardInterrupt:
        pass
    return yayinlar


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
