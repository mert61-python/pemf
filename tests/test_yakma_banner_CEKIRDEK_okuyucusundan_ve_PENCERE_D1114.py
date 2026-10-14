# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.114 · B-4.6 — yakma sonrası kart kimliği portu BIRAKMADAN çekirdeğin KENDİ okuyucusundan; yakma PENCERESİ dürüst.

ÖLÇÜLEN KUSURLAR:
  * B-4.6: backend açılış yakmasında seri portu TUTAR (HWSender okuyucusu); `stm_yakma.banner_dogrula` ise portu KENDİSİ
    açmaya çalışıyordu → "erişim reddedildi" `except Exception: continue` ile YUTULUYOR, sonuç "STM_READY hiç görülmedi"
    (BANNER_TANINMADI) → UYUMSUZ firmware'de OTOMATİK GERİ DÖNÜŞ HİÇ tetiklenemiyordu; destek de yanlış yöne gidiyordu
    ("karta RESET atın"). `banner_dinle`'nin kendi notu "port meşgul ile hiçbir şey duyulmadı farklı arızalardır" diyor.
  * Orkestratör notu: port BIRAKILMAZ (E-stop'un STM yolu hiç ölmez); banner core'un okuyucusundan alınır. Yakma
    penceresi boyunca ACİL DURDUR 200 ve STOP GİDER ama teyit (`confirmed`/`stmStopped`) True DÖNMEZ — MCU yakılırken STOP
    baytı ST-Link VCP'ye YAZILIR, kart işlemez (port açık tutulduğu için "porta yazıldı" teyidi yalan olurdu).
  * Yakma penceresinde (yedek → yak → banner → gerekirse geri dönüş) bobin BAŞLATMA kabul edilmez — ön kontrolle yakma
    arasındaki denetle-sonra-yap aralığında başlatılan bobin, MCU resetiyle ANİDEN dururdu.

KAPI (sahte yakıcı `_kos`, gerçek seri port YOK; `PEMF_FW_AUTO_UPDATE=1` yalnız bu sahte zincirde):
  (1) CLI yolu: `banner_dinle` "erişim reddedildi" fırlatınca sonuç PORT_MESGUL — "hiç görülmedi"/BANNER_TANINMADI DEĞİL.
  (2) GERÇEK `backend_service._donanim_guncellemesi_safe` → `acilis_denetimi` → `yakma_akisi`; çekirdek GERÇEK
      `HeadlessCore` metotlarıyla (`_handle_stm_line`): sahte yakıcı `-w` sonrası kartın reset banner'ını çekirdeğin
      okuyucusuna verir. Yeni firmware UYUMSUZ (5-ch) → otomatik GERİ DÖNÜŞ yapılır; port yeniden AÇILMAZ (`banner_dinle`
      0 çağrı).
  (3) Pencere: yakma sürerken GERÇEK HardwareController'a bobin başlatma REDDEDİLİR (bobin sürülmez) ve GERÇEK
      `_emergency_stop_all` STOP'u donanıma VERİR (`stop_all_coils`) ama `confirmed`/`stmStopped` False döner.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import logging
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ILK_BANNER = "-> STM_READY: 2.3.0 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands..."
YENI_UYUMSUZ = "-> STM_READY: 2.4.0 (5-ch + HW_SYNC@PB1) Waiting for commands..."
ESKI_GERI = "-> STM_READY: 2.3.0 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands..."


# ──────────────────────────────────────────────────────────────────────────
# (1) CLI yolu — port meşgul ≠ hiç görülmedi
# ──────────────────────────────────────────────────────────────────────────
def test_KRITIK_CLI_port_ACILAMAZSA_PORT_MESGUL_hic_gorulmedi_DEGIL(monkeypatch, tmp_path):
    import serial

    sy = importlib.import_module("utils.stm_yakma")
    ikili = tmp_path / "pemf.bin"
    ikili.write_bytes(b"YENI" * 64)
    kos: list[list[str]] = []

    def _sahte_kos(cli, argumanlar, timeout=300.0):
        kos.append(list(argumanlar))
        if "-r" in argumanlar:
            Path(argumanlar[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(argumanlar[-1]).write_bytes(b"ESKI")
        return 0, ""

    def _mesgul(port, sure=12.0):
        raise serial.SerialException(
            f"could not open port '{port}': PermissionError(13, 'Erişim engellendi.', None, 5)"
        )

    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("sahte_cli.exe"))
    monkeypatch.setattr(sy, "_kos", _sahte_kos)
    # TD1-e: yakma sonrası geri okuma + yeniden başlatma BU kapının konusu değil (başarılı — gerçek çıktı uzayından); gerçek akış EN ALT katta: test_TD1_yakma_ve_kimlik_betigi_KANITLA (flash öykünmesi).
    monkeypatch.setattr(sy, "geri_oku", lambda _c, _i, _h: (True, "geri okuma: (aparat) bayt bayt AYNI"))
    monkeypatch.setattr(sy, "baslat", lambda _c: (True, ""))
    monkeypatch.setattr(sy, "port_adaylari", lambda istenen=None: ["COM10"])
    monkeypatch.setattr(sy, "banner_dinle", _mesgul)
    monkeypatch.setattr(sy, "kart_dogrula", _mesgul)  # TD1-e: CLI doğrulaması portu bu yoldan açar
    s = sy.yakma_akisi(ikili, guvenlik_kontrolu=lambda: (True, "test"), yedek_dizin=tmp_path / "y")
    assert s.kod != sy.BANNER_TANINMADI and "hiç görülmedi" not in s.ozet, (
        f"port açılamadı (backend tutuyor) ama sonuç '{s.ozet}' (kod {s.kod}) — 'hiç görülmedi' ile AYNI; destek yanlış yöne "
        "gider ve uyumsuz firmware'de geri dönüş tetiklenemez (B-4.6)"
    )
    assert s.kod == getattr(sy, "PORT_MESGUL", -1), s


# ──────────────────────────────────────────────────────────────────────────
# (2)+(3) Backend'in kendi yakması — çekirdek okuyucusu + pencere
# ──────────────────────────────────────────────────────────────────────────
def _cekirdek(bus):
    import headless_core as hcm
    from utils.simple_signal import SimpleSignal

    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = logging.getLogger("test-d1114")
    core.event_bus = bus
    core._stm_state_lock = threading.RLock()
    core.stm_is_connected = False
    core.stm_kimlik = None
    core.stm_uyumlu = None
    core.stm_uyumsuzluk_sebebi = ""
    core.stm_connected_signal = SimpleSignal()
    core.stm_connected_signal.connect(core._on_stm_connected_slot)
    return core


@pytest.fixture()
def zincir(monkeypatch, tmp_path):
    import backend_service as bs
    import event_bus as eb
    import serial
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import live_state as ls

    fm = importlib.import_module("servers.firmware_manager")
    importlib.reload(fm)
    sy = importlib.import_module("utils.stm_yakma")
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    yeni_bus = eb.EventBus()
    monkeypatch.setattr(eb, "_event_bus_instance", yeni_bus)
    core = _cekirdek(yeni_bus)
    core._handle_stm_line(ILK_BANNER)  # açılışta okunan kimlik (sürümü ayrıştırılabilir)
    monkeypatch.setattr(api.state, "core", core)
    monkeypatch.setitem(api._active_session, "is_active", False)

    ikili = tmp_path / "pemf_fw.bin"
    ikili.write_bytes(b"PEMF-FW-2.4.0" * 95)  # 1235 B — yeni ikili, uygulama alanından KÜÇÜK
    ozet = hashlib.sha256(ikili.read_bytes()).hexdigest()
    manifest = {
        "firmware": {
            "stm32": {"version": "2.4.0", "url": "https://github.com/mert61-python/pemf-update/x", "sha256": ozet}
        },
        "uyumluluk": [{"clientMin": "", "firmwareMin": "2.4.0"}],
    }
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: manifest)
    monkeypatch.setattr(fm.um, "get_current_version", lambda: "1.9.51")
    monkeypatch.setattr(fm.um, "get_status", lambda: {"previousStable": None})
    monkeypatch.setattr(fm, "firmware_indir", lambda url, sha: (ikili, ""))

    pencere_basladi, devam = threading.Event(), threading.Event()
    kos: list[str] = []

    def _banner_ver(satir):
        def _is():
            time.sleep(0.2)  # kart reset sonrası açılış
            core._handle_stm_line(satir)

        threading.Thread(target=_is, daemon=True).start()

    def _sahte_kos(cli, argumanlar, timeout=300.0):
        if "-r" in argumanlar:
            kos.append("yedek")
            Path(argumanlar[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(argumanlar[-1]).write_bytes(b"ESKI-FW-2.3.0")
        elif "-w" in argumanlar:
            hedef = Path(argumanlar[argumanlar.index("-w") + 1])
            if hedef.read_bytes() == ikili.read_bytes():
                kos.append("yak:yeni")
                pencere_basladi.set()
                devam.wait(15)
                # `-rst` sonrası banner yakıcı süreci BİTMEDEN gelebilir → SENKRON ver (işaret yakmadan ÖNCE alınmalı).
                core._handle_stm_line(YENI_UYUMSUZ)
            else:
                kos.append("yak:yedek")
                _banner_ver(ESKI_GERI)
        return 0, "sahte yakici"

    port_acma: list[str] = []

    def _port_mesgul(port, sure=12.0):
        port_acma.append(port)
        raise serial.SerialException(f"could not open port '{port}': PermissionError(13, 'Erişim engellendi.')")

    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("sahte_cli.exe"))
    monkeypatch.setattr(sy, "_kos", _sahte_kos)
    # TD1-e: yakma sonrası geri okuma + yeniden başlatma BU kapının konusu değil (başarılı — gerçek çıktı uzayından); gerçek akış EN ALT katta: test_TD1_yakma_ve_kimlik_betigi_KANITLA (flash öykünmesi).
    monkeypatch.setattr(sy, "geri_oku", lambda _c, _i, _h: (True, "geri okuma: (aparat) bayt bayt AYNI"))
    monkeypatch.setattr(sy, "baslat", lambda _c: (True, ""))
    monkeypatch.setattr(sy, "port_adaylari", lambda istenen=None: ["COM10"])
    monkeypatch.setattr(sy, "banner_dinle", _port_mesgul)
    monkeypatch.setattr(sy, "kart_dogrula", _port_mesgul)  # TD1-e: CLI doğrulaması portu bu yoldan açar
    monkeypatch.setattr(sy, "BANNER_SURESI", 5.0)

    def _http(self, fullurl, *a, **k):
        raise urllib.error.URLError(ConnectionRefusedError(10061, "kimse dinlemiyor (kapı taklidi)"))

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _http)
    monkeypatch.setenv("PEMF_FW_AUTO_UPDATE", "1")
    with ls._live_state_lock:
        eski_bobin = copy.deepcopy(ls._live_state["coils"])
        eski_tedavi = copy.deepcopy(ls._live_state["activeTreatment"])
        for c in ls._live_state["coils"].values():
            c["running"] = False
        ls._live_state["activeTreatment"]["isActive"] = False
    try:
        # GERÇEK HardwareController, kayıtçı kuyruk (`_KayitciCore`): STOP/START paketleri kaydedilir; çekirdek yazım izi
        # bildirmediği için E-stop `stmStopped` "kuyruğa verildi"ye dayanır — port açık tutulduğunda yakma penceresindeki
        # gerçek durumla aynı (STOP baytı VCP'ye yazılır ama kart işlemez).
        with gercek_hc(stm_cevrimici=True) as hc:
            monkeypatch.setattr(api.state, "hardware", hc)
            yield {
                "bs": bs,
                "fm": fm,
                "sy": sy,
                "api": api,
                "core": core,
                "hc": hc,
                "kos": kos,
                "port_acma": port_acma,
                "pencere_basladi": pencere_basladi,
                "devam": devam,
            }
    finally:
        devam.set()
        with ls._live_state_lock:
            ls._live_state["coils"].clear()
            ls._live_state["coils"].update(eski_bobin)
            ls._live_state["activeTreatment"].clear()
            ls._live_state["activeTreatment"].update(eski_tedavi)


def test_KRITIK_backend_yakmasi_banneri_CEKIRDEKTEN_alir_UYUMSUZDA_GERI_DONER_ve_PENCERE_durust(zincir):
    z = zincir
    sonuc: dict = {}
    # KARŞIT (aparat): pencere DIŞINDA başlatma ÇALIŞIR — pencere içindeki red mandal/gönderici gibi başka bir nedenden değil.
    assert z["hc"].update_coil(2, freq=100.0, duty=20.0, phase=0.0, duration=1, start=True) is True, (
        "aparat: pencere dışında bile bobin başlatılamıyor — kapı kör olurdu"
    )
    z["hc"].update_coil(2, freq=100.0, duty=0.0, phase=0.0, duration=0, start=False)
    assert not z["hc"].calisan_bobin_durumu(), "aparat: karşıt bobini durmadı"

    def _acilis():
        z["bs"]._donanim_guncellemesi_safe(z["core"], logging.getLogger("test-d1114-acilis"))

    t = threading.Thread(target=_acilis, daemon=True)
    t.start()
    assert z["pencere_basladi"].wait(15), (
        f"aparat: yakma penceresine ulaşılmadı (zincir: {z['kos']}, {z['fm'].durum()})"
    )

    # (3a) pencere sürerken bobin BAŞLATMA reddedilmeli; seans/AI Pro kapısı ("güncelleme sürüyor") da kapalı
    sonuc["baslat"] = z["hc"].update_coil(1, freq=100.0, duty=20.0, phase=0.0, duration=1, start=True)
    sonuc["calisan"] = dict(z["hc"].calisan_bobin_durumu())
    sonuc["guncelleme_suruyor"] = z["fm"].um.is_update_in_progress()
    # (3b) ACİL DURDUR: STOP donanıma VERİLİR, teyit True DÖNMEZ
    once = z["hc"].stop_all_cagri
    r = z["api"]._emergency_stop_all("d1114-pencere")
    sonuc["estop"] = {k: r.get(k) for k in ("status", "confirmed", "stmStopped")}
    sonuc["stop_verildi"] = z["hc"].stop_all_cagri - once
    z["devam"].set()
    t.join(30)
    assert not t.is_alive(), "açılış donanım güncellemesi bitmedi"
    d = z["fm"].durum()

    assert sonuc["baslat"] is False and not sonuc["calisan"], (
        f"firmware YAKILIRKEN bobin başlatma KABUL EDİLDİ ({sonuc}) — MCU resetinde bobin ANİDEN durur"
    )
    assert sonuc["guncelleme_suruyor"] is True, f"yakma penceresinde seans/AI Pro kapısı açık: {sonuc}"
    assert z["fm"].um.is_update_in_progress() is False, "yakma bittikten sonra 'güncelleme sürüyor' kapanmadı"
    assert sonuc["stop_verildi"] >= 1, f"pencerede ACİL DURDUR STOP'u donanıma VERİLMEDİ (Ö.4-Y8): {sonuc}"
    assert sonuc["estop"]["confirmed"] is False and sonuc["estop"]["stmStopped"] is False, (
        f"MCU yakılırken ACİL DURDUR 'teyitli' döndü: {sonuc['estop']} — STOP VCP'ye yazıldı ama kart işlemedi"
    )
    assert z["kos"] == ["yedek", "yak:yeni", "yak:yedek"], (
        f"UYUMSUZ yeni firmware'de OTOMATİK GERİ DÖNÜŞ yapılmadı: {z['kos']} · {d} — banner çekirdeğin okuyucusundan "
        "alınmalı (port backend'de açık; yeniden açmak 'erişim reddedildi' alır)"
    )
    assert z["port_acma"] == [], f"yakma sonrası port YENİDEN açılmaya çalışıldı (backend tutuyor): {z['port_acma']}"
    assert str(z["sy"].UYUMSUZ_GERI_DONULDU) in d["hata"], d


@pytest.mark.parametrize("yol", ["update_coil", "start_all_coils"])
def test_KRITIK_pencere_ERKEN_denetimden_SONRA_acilirsa_KILIT_ICI_kapi_reddeder(yol):
    """Belirlenimci yarış: başlatma, erken denetimi (`_stm_baslatma_engeli`) pencere KAPALIYKEN geçer; pencere tam o anda
    açılır (yakma ön kontrolü). Kilit-İÇİ kapı yine reddetmeli — yoksa bobin, ön kontrol "bobin yok" dedikten SONRA
    sürülür ve MCU resetinde ANİDEN durur. (Erken denetim tek başına bu aralığı KAPATMAZ.) İki başlatma yolu da
    (`update_coil`: tekil/seans/AI Pro · `start_all_coils`: AI (Auto)) kendi kilit-içi kapısını taşır."""
    from kayitci_donanim import gercek_hc
    from utils import firmware_yakma_penceresi as pencere

    with gercek_hc(stm_cevrimici=True) as hc:
        orj = hc._gonderici_baslatmaya_hazir

        def _araya_gir():
            pencere._acik.set()  # erken denetim GEÇİLDİ; yakma penceresi ŞİMDİ açılıyor
            return orj()

        hc._gonderici_baslatmaya_hazir = _araya_gir
        try:
            if yol == "update_coil":
                sonuc = hc.update_coil(3, freq=100.0, duty=20.0, phase=0.0, duration=1, start=True)
            else:
                sonuc = hc.start_all_coils(freq=100.0, duty=20.0, phase=0.0, duration=1)
            calisan = dict(hc.calisan_bobin_durumu())
        finally:
            pencere._acik.clear()
    assert sonuc is False and not calisan, (
        f"pencere erken denetimden sonra açıldı ama START YAZILDI ({calisan}) — kilit-içi kapı yok/eksik"
    )
