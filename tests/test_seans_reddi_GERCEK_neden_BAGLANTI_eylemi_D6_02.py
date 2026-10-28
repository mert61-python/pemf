# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.02 · S-1.7 — kopuk STM'de seans başlatma reddi "kartın yazılımı uyumsuz (FW-PAKET)" DEMEZ; USB / bağlantı eylemini söyler.

ÖLÇÜLEN KUSUR (HEAD ebf1c3fe): `/api/session/start` hiçbir STM bobini kabul etmediğinde 503'ü HER ZAMAN
`komutKabulEdilmedi` + `stm_red_mesaji()` ("Cihaz kartı komutları reddediyor — kartın yazılımı bu uygulama sürümüyle uyumsuz …
Teknik desteği arayın (kod: FW-PAKET)") ile kuruyordu. Oysa en sık sebep KABLONUN TAKILI OLMAMASIDIR: `update_coil` kopuk kartta
`donanim.hata.stmBagliDegil` ("USB (ST-Link) kablosunu takın") sebebini BİLİYOR ama üç farklı sebebe (kopuk / gönderici ölü /
parametre) aynı çıplak `False` dönüyordu → veteriner sağlam kart için teknik destek arıyordu.

Düzeltme: `HardwareController.son_baslatma_reddi()` — son START reddinin operatör metni (iş parçacığı-yerel; dönüş tipi `bool`
KALIR); seans ucu bu sebebi 503'e taşır. Sebep bildirmeyen donanım nesnesinde STM kopuksa bağlantı eylemi söylenir.
İKİ KOL AYRI: firmware KESİN uyumsuzken 409 metni (FW-PAKET) KORUNUR. Ölçüt metin BAYT BAYT (TR) + EN karşılığı (`X-PEMF-Dil`).
"""

from __future__ import annotations

import contextlib
import threading
import types

import pytest

#: TR / EN beklenen metinler TESTTE PİNLİ (katalogdan okunmaz — katalog değeri değişirse kapı kırmızı olur).
_SABLON_TR = "Hiçbir bobin komutu kabul etmedi; seans BAŞLATILMADI. "
_SABLON_EN = "No coil accepted the command; the session was NOT STARTED. "
_BAGLI_DEGIL_TR = "STM32 bağlı değil. USB (ST-Link) kablosunu takın; bağlantı gelince komutu yeniden verin."
_BAGLI_DEGIL_EN = (
    "The STM32 is not connected. Plug in the USB (ST-Link) cable; give the command again once it is connected."
)
_GONDERICI_TR = (
    "Cihaz kartına komut gönderilemiyor — bobin başlatılmadı. USB kablosunu denetleyip birkaç saniye sonra komutu "
    "yeniden verin; sürerse uygulamayı kapatıp yeniden açın."
)
_GONDERICI_EN = (
    "Commands cannot be sent to the device board — the coil was not started. Check the USB cable and give the command "
    "again in a few seconds; if it persists, close and reopen the app."
)
_FW_409_TR = (
    "Seans BAŞLATILMADI: Cihaz kartı komutları reddediyor — kartın yazılımı bu uygulama sürümüyle uyumsuz; bobinler "
    "çalışmaz. Teknik desteği arayın (kod: FW-PAKET)."
)
_FIRMWARE_IZLERI = ("FW-PAKET", "yazılımı", "firmware", "Firmware", "CubeIDE", "programlay")


@contextlib.contextmanager
def _stm_durumu(deger: str):
    from servers import live_state as _ls

    with _ls._live_state_lock:
        eski = _ls._live_state["stm"]
        _ls._live_state["stm"] = deger
    try:
        yield
    finally:
        with _ls._live_state_lock:
            _ls._live_state["stm"] = eski


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from servers import api_server as api
    from servers import coil_run_tracker as crt
    from servers import live_state

    kok = tmp_path / "gecmis"
    kok.mkdir()
    db = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: db)
    monkeypatch.setattr(api, "_kayit_db_hazir", lambda: (True, ""))
    monkeypatch.setattr(api, "_push_notification", lambda m, t="info": None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 0)
    monkeypatch.setattr(api.state, "core", types.SimpleNamespace(stm_uyumlu=None), raising=False)
    live_state.stm_komut_kabulu_bildir()
    with api._session_lock:
        eski_seans = dict(api._active_session)
        api._active_session["is_active"] = False
    try:
        with TestClient(api.app) as c:
            yield types.SimpleNamespace(api=api, c=c, db=db)
    finally:
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski_seans)
        live_state.stm_komut_kabulu_bildir()


def _baslat(c, dil: str | None = None):
    basliklar = {"X-PEMF-Dil": dil} if dil else {}
    return c.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 100,
            "duty": 50,
            "phase": 0,
            "intensity": 0.0,
            "duration_minutes": 20,
            "coil_ids": [1, 2],
            "patient_name": "D602",
        },
        headers=basliklar,
    )


def _detay(y) -> str:
    return str(y.json().get("detail", ""))


# ── 1. kopuk STM: GERÇEK HardwareController → 503 bağlantı eylemi (TR + EN) ────────────────────────────────────────────
@pytest.mark.parametrize(
    "dil, beklenen",
    [(None, _SABLON_TR + _BAGLI_DEGIL_TR), ("en", _SABLON_EN + _BAGLI_DEGIL_EN)],
)
def test_KRITIK_kopuk_STM_seans_reddi_USB_baglanti_eylemini_soyler(ortam, monkeypatch, dil, beklenen):
    from kayitci_donanim import gercek_hc

    with gercek_hc(stm_cevrimici=False) as hc, _stm_durumu("warning"):
        monkeypatch.setattr(ortam.api.state, "hardware", hc)
        y = _baslat(ortam.c, dil)
        assert y.status_code == 503, f"kopuk STM'de seans {y.status_code}: {y.text[:300]}"
        assert not [i for i, s in hc.coils_state.items() if s["is_running"]], "kopuk kartta bobin sürüldü"
    d = _detay(y)
    izler = [s for s in _FIRMWARE_IZLERI if s in d]
    assert not izler, f"kopuk STM reddi firmware / yazılım uyumsuzluğu söylüyor ({izler}): {d!r}"
    assert d == beklenen, f"503 metni bağlantı (USB) eylemini söylemiyor:\n  gelen   {d!r}\n  beklenen {beklenen!r}"


# ── 2. gönderici ölü (STM bağlı görünür): sebep yine donanımdan taşınır ─────────────────────────────────────────────────
@pytest.mark.parametrize(
    "dil, beklenen",
    [(None, _SABLON_TR + _GONDERICI_TR), ("en", _SABLON_EN + _GONDERICI_EN)],
)
def test_gonderici_olu_seans_reddi_KENDI_sebebini_tasir(ortam, monkeypatch, dil, beklenen):
    from kayitci_donanim import gercek_hc

    with gercek_hc(stm_cevrimici=True) as hc, _stm_durumu("online"):
        hc.core.hw_gonderici_canli = lambda: False
        hc.core.hw_gondericiyi_canlandir = lambda: False
        monkeypatch.setattr(ortam.api.state, "hardware", hc)
        y = _baslat(ortam.c, dil)
    assert y.status_code == 503, f"gönderici ölüyken seans {y.status_code}: {y.text[:300]}"
    d = _detay(y)
    assert "FW-PAKET" not in d, f"gönderici ölü reddi firmware uyumsuzluğu söylüyor: {d!r}"
    assert d == beklenen, f"503 metni donanımın red sebebini taşımıyor:\n  gelen   {d!r}\n  beklenen {beklenen!r}"


# ── 3. sebep bildirmeyen donanım nesnesi + kopuk STM → yine bağlantı eylemi (FW-PAKET değil) ──────────────────────────
class _SebepsizRed:
    def __init__(self):
        self.cagrilar: list = []

    def update_coil(self, coil_id, freq, duty, phase, duration, start=True, duration_seconds=None):
        self.cagrilar.append(coil_id)
        return False

    def stop_all_coils(self):
        return True

    def get_all_coils_state(self):
        return {}


def test_sebepsiz_red_kopuk_STMde_baglanti_eylemi(ortam, monkeypatch):
    sahte = _SebepsizRed()
    monkeypatch.setattr(ortam.api.state, "hardware", sahte)
    with _stm_durumu("warning"):
        y = _baslat(ortam.c)
    assert y.status_code == 503 and sahte.cagrilar, f"ön koşul: {y.status_code} {sahte.cagrilar}"
    assert _detay(y) == _SABLON_TR + _BAGLI_DEGIL_TR, f"sebepsiz red + kopuk STM: {_detay(y)!r}"


# ── 4. İKİ KOL AYRI: firmware KESİN uyumsuzken 409 metni (FW-PAKET) KORUNUR ─────────────────────────────────────────────
def test_firmware_UYUMSUZ_kolu_409_FW_PAKET_metnini_KORUR(ortam, monkeypatch):
    from kayitci_donanim import gercek_hc

    with gercek_hc(stm_cevrimici=True) as hc, _stm_durumu("online"):
        monkeypatch.setattr(ortam.api.state, "hardware", hc)
        monkeypatch.setattr(
            ortam.api.state,
            "core",
            types.SimpleNamespace(stm_uyumlu=False, stm_uyumsuzluk_sebebi="5 != 7"),
            raising=False,
        )
        y = _baslat(ortam.c)
    assert y.status_code == 409, f"uyumsuz firmware'de seans {y.status_code}: {y.text[:300]}"
    assert _detay(y) == _FW_409_TR, f"firmware uyumsuz kolunun 409 metni değişti: {_detay(y)!r}"


# ── 5. HardwareController sözleşmesi: dönüş bool KALIR, sebep iş parçacığı-yerel ──────────────────────────────────────
def test_update_coil_red_sebebini_TASIR_donus_bool_kalir_is_parcacigi_yerel():
    from kayitci_donanim import gercek_hc

    with gercek_hc(stm_cevrimici=False) as hc:
        with _stm_durumu("warning"):
            assert hc.update_coil(1, 50.0, 25.0, 0.0, 10, start=True) is False
            assert hc.son_baslatma_reddi() == _BAGLI_DEGIL_TR, f"kopuk red sebebi: {hc.son_baslatma_reddi()!r}"
            baska: list = []
            t = threading.Thread(target=lambda: baska.append(hc.son_baslatma_reddi()))
            t.start()
            t.join(5)
            assert baska == [""], f"red sebebi başka iş parçacığına sızdı: {baska!r}"
        with _stm_durumu("online"):
            # parametre reddi (üçüncü sebep) de kendi metnini taşır — durum DEĞİŞMEZ
            assert hc.update_coil(1, 50.0, "x", 0.0, 10, start=True) is False
            assert hc.son_baslatma_reddi().startswith("Sürüş parametresi donanım paketine çevrilemiyor ("), (
                f"parametre red sebebi: {hc.son_baslatma_reddi()!r}"
            )
            assert not hc.coils_state[1]["is_running"]
            # AYNI denetleyici, AYNI iş parçacığı: kabul edilen START önceki reddin sebebini SİLER (bayat sebep 503'e gitmez).
            assert hc.update_coil(1, 50.0, 25.0, 0.0, 10, start=True) is True
            assert hc.son_baslatma_reddi() == "", f"KABUL edilen START sonrası bayat sebep: {hc.son_baslatma_reddi()!r}"
            hc.stop_all_coils()


def test_yeni_metin_TR_bayt_bayt_ve_EN_katalogda():
    from utils import ceviri

    assert ceviri.t("donanim.hata.gondericiCalismiyor", dil="tr") == _GONDERICI_TR
    assert ceviri.t("donanim.hata.gondericiCalismiyor", dil="en") == _GONDERICI_EN


# ── TUR 2 kolları (çürütücü, hat D) ─────────────────────────────────────────────────────────────────────────────────────
#: `stm_red_mesaji()` TR metni — sebep bildirmeyen donanım + STM BAĞLI kolunun (üçüncü sıra) beklenen nedeni (testte pinli).
_KART_REDDI_TR = (
    "Cihaz kartı komutları reddediyor — kartın yazılımı bu uygulama sürümüyle uyumsuz; bobinler çalışmaz. Teknik desteği "
    "arayın (kod: FW-PAKET)."
)


def test_sebepsiz_red_kopuk_STMde_baglanti_eylemi_EN(ortam, monkeypatch):
    """Tur 2 kolu: sebep bildirmeyen donanım + kopuk STM kolu da İSTEK DİLİNDE (`X-PEMF-Dil: en`) — TR'ye sabitlenmiş
    `stmBagliDegil` İngilizce ekranda Türkçe eylem gösterirdi."""
    sahte = _SebepsizRed()
    monkeypatch.setattr(ortam.api.state, "hardware", sahte)
    with _stm_durumu("warning"):
        y = _baslat(ortam.c, "en")
    assert y.status_code == 503 and sahte.cagrilar, f"ön koşul: {y.status_code} {sahte.cagrilar}"
    assert _detay(y) == _SABLON_EN + _BAGLI_DEGIL_EN, f"sebepsiz red + kopuk STM (en): {_detay(y)!r}"


def test_sebepsiz_red_BAGLI_STMde_baglanti_eylemi_SOYLENMEZ(ortam, monkeypatch):
    """Tur 2 kolu (karşıt): STM BAĞLIYKEN sebep bildirmeyen red "STM32 bağlı değil / kabloyu takın" DEMEZ (yanlış eylem);
    üçüncü sıra — eski kart-reddi metni — kalır. Ön-denetimi (`stm_surus_hazir`) atlayan sıralama burada yakalanır."""
    sahte = _SebepsizRed()
    monkeypatch.setattr(ortam.api.state, "hardware", sahte)
    with _stm_durumu("online"):
        y = _baslat(ortam.c)
    assert y.status_code == 503 and sahte.cagrilar, f"ön koşul: {y.status_code} {sahte.cagrilar}"
    d = _detay(y)
    assert "bağlı değil" not in d and "USB (ST-Link)" not in d, (
        f"STM BAĞLIYKEN 'bağlı değil / kabloyu takın' deniyor: {d!r}"
    )
    assert d == _SABLON_TR + _KART_REDDI_TR, f"bağlı STM + sebepsiz red nedeni değişti: {d!r}"


def test_kilit_alti_engel_de_SEBEBINI_tasir():
    """Tur 2 kolu: kilit ALTINDAKİ ikinci START engeli (E-stop mandalı / BAYAT sürüş nesli / gözlem / yakma penceresi) da red
    sebebini taşır — çıplak `False` dönerse seans ucu (STM bağlı) "kartın yazılımı uyumsuz (FW-PAKET)" der. Bayat nesil
    küresel mandalı KURMADAN aynı satırı koşturur (mandal durumu değişmez)."""
    from kayitci_donanim import gercek_hc
    from utils import estop_mandali

    with gercek_hc(stm_cevrimici=True) as hc, _stm_durumu("online"):
        mandal_once = estop_mandali.mandalli_mi()
        bayat = estop_mandali.nesil() - 1
        assert hc.update_coil(1, 50.0, 25.0, 0.0, 10, start=True, nesil=bayat) is False
        sebep = hc.son_baslatma_reddi()
        assert sebep, "kilit altındaki engel (bayat nesil) red SEBEBİ bildirmiyor (çıplak False)"
        assert sebep == estop_mandali.nesil_mesaji(), f"bayat nesil red sebebi: {sebep!r}"
        assert "FW-PAKET" not in sebep
        assert not hc.coils_state[1]["is_running"], "bayat nesilli START bobini sürdü"
        assert estop_mandali.mandalli_mi() == mandal_once, "kapı küresel mandal durumunu değiştirdi"
        hc.stop_all_coils()
