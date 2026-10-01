# Author: mertaygn, cglrgrkn
"""D1.41 · B-10.243 · B-10.257 — `conftest._seans_ve_watchdog_nobeti`nin denetim işlevi KÖR DEĞİL (Ö.6).

Nöbet teardown'da çalıştığı için kendi kırmızısı bir testin içinden iddia edilemez; bu dosya nöbetin SAF
denetim işlevini (`seans_watchdog_nobet_sorunlari`) sahte bir api nesnesiyle sınar: sızan seans raporlanır
VE kapatılır; arka plan iş parçacıkları başlamışken watchdog yoksa ölüm YALNIZ BİR KEZ raporlanır; canlı
watchdog ve temiz seans yanlış alarm üretmez.
"""

from __future__ import annotations

import threading
import types

import conftest
import pytest
from conftest import seans_watchdog_nobet_sorunlari


@pytest.fixture
def bayrak_sifir():
    eski = conftest._WATCHDOG_OLUMU_BILDIRILDI["evet"]
    conftest._WATCHDOG_OLUMU_BILDIRILDI["evet"] = False
    yield
    conftest._WATCHDOG_OLUMU_BILDIRILDI["evet"] = eski


def _api(aktif: bool, bg: bool):
    return types.SimpleNamespace(
        _session_lock=threading.Lock(),
        _active_session={"is_active": aktif, "session_id": "nobet-testi"} if aktif else {},
        _bg_threads_started=bg,
    )


def test_ARAC_sizan_aktif_seans_RAPORLANIR_ve_KAPATILIR(bayrak_sifir):
    api = _api(aktif=True, bg=False)
    sorun = seans_watchdog_nobet_sorunlari(api, [])
    assert len(sorun) == 1 and "SIZDI" in sorun[0]
    assert api._active_session["is_active"] is False, "nöbet sızıntıyı kapatmadı (sonraki teste taşınır)"


def test_ARAC_olu_watchdog_YALNIZ_BIR_KEZ_raporlanir(bayrak_sifir):
    api = _api(aktif=False, bg=True)
    ilk = seans_watchdog_nobet_sorunlari(api, [])
    ikinci = seans_watchdog_nobet_sorunlari(api, [])
    assert len(ilk) == 1 and "ÖLDÜ" in ilk[0]
    assert ikinci == [], "ölüm her testte yeniden raporlanıyor (zincirleme kırmızı — suçlu test görünmez)"


def test_ARAC_temiz_durum_ve_CANLI_watchdog_alarm_URETMEZ(bayrak_sifir):
    canli = types.SimpleNamespace(name="session-watchdog", is_alive=lambda: True)
    assert seans_watchdog_nobet_sorunlari(_api(aktif=False, bg=True), [canli]) == []
    assert seans_watchdog_nobet_sorunlari(_api(aktif=False, bg=False), []) == []
