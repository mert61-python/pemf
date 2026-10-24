# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""H-2.2 (1-H bağımsız incelemesi) — D1.114: yakma ön kontrolü (seans / bobin) YAKMA PENCERESİ AÇIKKEN yapılır; ön
kontrolden HEMEN SONRA gelen bir bobin başlatması yakmayla ÇAKIŞAMAZ.

KÖR KAPI (ölçüldü, inceleme `kayit/h22eski_mutasyon.txt`): `_firmware_uygula`'da süreç içi ön kontrol pencere AÇILMADAN
yapılıp sonucu `yakma_akisi`'ya hazır verilince (denetle-sonra-yap aralığı geri açılır) firmware zincirinin 9 kapı dosyası
(D1.108/111, D1.112, D1.113, D1.114, D1.115, D1.120, D1.121, `test_firmware_manager`, H-2.1) 88/88 YEŞİL kaldı. D1.114'ün
kilit-içi kapısı yalnız PENCERE AÇIKKEN reddeder; ön kontrol "bobin yok" dedikten SONRA ve pencere açılmadan ÖNCE gelen
START kabul edilir → bobin sürülürken yedek + yakma başlar, MCU resetinde bobin ANİDEN durur (güvenlik değişmezi 1-2).

KAPI: GERÇEK `firmware_manager._firmware_uygula` → GERÇEK `yakma_akisi`; GERÇEK `HardwareController` (`kayitci_donanim.
gercek_hc`). Ön kontrol (GERÇEK `_surec_ici_guvenlik_kontrolu`) "güvenli" dedikten hemen SONRA, aynı iş parçacığında
belirlenimci olarak bobin 1 başlatılır (operatörün o anda bastığı START). Sonra: START REDDEDİLMİŞ ve yakıcının `-r`/`-w`
çağrılarında çalışan bobin YOK. Karşıt: pencere dışında aynı START kabul edilir (aparat başlatmayı gerçekten yapabiliyor).
Gerçek seri port / yakıcı YOK.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
from pathlib import Path

import pytest
from stlink_sahte import listeli  # T-b: sahte yakıcı `-l st-link` prob listesini de verir

BANNER = "-> STM_READY: DDS v2.4 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands..."


@pytest.fixture()
def zincir(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import live_state as ls

    fm = importlib.import_module("servers.firmware_manager")
    sy = importlib.import_module("utils.stm_yakma")
    monkeypatch.setattr(ls, "_ws_broadcast_sync", lambda m: None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    ikili = tmp_path / "indir" / "pemf_fw.bin"
    ikili.parent.mkdir()
    ikili.write_bytes(b"PEMF-FW-2.4" * 97)
    girdi = {"version": "2.4", "sha256": hashlib.sha256(ikili.read_bytes()).hexdigest(), "url": "x"}
    monkeypatch.setattr(fm, "firmware_indir", lambda url, sha: (ikili, ""))
    monkeypatch.setattr(fm, "_yedek_dizini", lambda: tmp_path / "firmware_yedek")
    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("sahte_yakici.exe"))
    monkeypatch.setattr(sy, "banner_dogrula", lambda *a, **k: (True, "uyumlu", BANNER))
    monkeypatch.setattr(sy.time, "sleep", lambda _s: None)
    monkeypatch.setitem(api._active_session, "is_active", False)
    with ls._live_state_lock:
        eski_bobin = copy.deepcopy(ls._live_state["coils"])
        eski_tedavi = copy.deepcopy(ls._live_state["activeTreatment"])
        for c in ls._live_state["coils"].values():
            c["running"] = False
        ls._live_state["activeTreatment"]["isActive"] = False
    try:
        with gercek_hc(stm_cevrimici=True) as hc:
            monkeypatch.setattr(api.state, "hardware", hc)
            yield {"fm": fm, "sy": sy, "hc": hc, "girdi": girdi, "mp": monkeypatch}
    finally:
        with ls._live_state_lock:
            ls._live_state["coils"].clear()
            ls._live_state["coils"].update(eski_bobin)
            ls._live_state["activeTreatment"].clear()
            ls._live_state["activeTreatment"].update(eski_tedavi)


def _baslat(hc):
    return hc.update_coil(1, freq=100.0, duty=20.0, phase=0.0, duration=1, start=True)


def test_KRITIK_H22_on_kontrolden_HEMEN_SONRA_gelen_START_yakmayla_CAKISAMAZ(zincir):
    from utils import surum_uyumu as su

    z = zincir
    hc = z["hc"]
    gorulen: dict = {"start": None, "kos": []}
    orj = z["fm"]._surec_ici_guvenlik_kontrolu

    def _kontrol_sonra_start():
        sonuc = orj()
        if gorulen["start"] is None:
            gorulen["kontrol"] = sonuc
            gorulen["start"] = _baslat(hc)  # ön kontrol "güvenli" dedi; operatör TAM ŞİMDİ başlatıyor
        return sonuc

    def _sahte_kos(cli, argumanlar, timeout=300.0):
        gorulen["kos"].append((argumanlar[2], sorted(hc.calisan_bobin_durumu())))
        if "-r" in argumanlar:
            Path(argumanlar[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(argumanlar[-1]).write_bytes(b"ESKI-FW")
        return 0, ""

    z["mp"].setattr(z["fm"], "_surec_ici_guvenlik_kontrolu", _kontrol_sonra_start)
    z["mp"].setattr(z["sy"], "_kos", listeli(_sahte_kos))
    z["fm"]._firmware_uygula(z["girdi"], su.Plan(su.FIRMWARE_GUNCELLE, "2.4", "test"))
    assert gorulen.get("kontrol", (None,))[0] is True, f"aparat: ön kontrol güvenli demedi {gorulen}"
    assert gorulen["start"] is False, (
        "ön kontrolden SONRA, yakmadan ÖNCE gelen START KABUL EDİLDİ — ön kontrol pencere açılmadan yapılmış "
        f"(denetle-sonra-yap aralığı): {gorulen}"
    )
    calisirken = [(adim, bobinler) for adim, bobinler in gorulen["kos"] if bobinler]
    assert gorulen["kos"] and not calisirken, f"yakıcı BOBİN SÜRÜLÜRKEN çağrıldı: {calisirken}"


def test_KARSIT_H22_pencere_DISINDA_ayni_START_kabul_edilir(zincir):
    assert _baslat(zincir["hc"]) is True, "aparat: pencere dışında başlatma yapılamıyor (kapı kör olur)"
    assert 1 in zincir["hc"].calisan_bobin_durumu()
