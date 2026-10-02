# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.55 · 1-C bağımsız inceleme i5-F-3 — ölü HWSender'ı canlandırmayı GEREKTİREN başlatma REDDEDİLİR.

ÖLÇÜLEN KUSUR (293ff1c, i5 30/30): boştayken ölen gönderici en olası durumda bir sonraki START ile canlandırılır
(`update_coil` → `_gonderici_canli()`). Canlandırılan çalışanın `connect_serial`'i kopuş olayı üretir → `on_disconnect`
HC'yi "durdu"ya çeker. START durumu bundan ÖNCE yazmışsa START "başarılı" döner (tekil uçta `success` + koşu kaydı),
HC "durdu", keep-alive susar — sahte başarılı START (eski tutamağın kapanışı 50 ms iken 30/30). F-1'in kuyruk ayıklaması
bayat RUN'ı atsa da START yine "başarılı" der.

SÖZLEŞME: gönderici ŞU AN ölüyse START / `start_all_coils` False döner ve durum YAZILMAZ; canlandırma yine denenir (sonraki
STOP'lar yazılsın — Ö.4-Y8: STOP yolları bu kapıdan geçmez). KAPI: GERÇEK HeadlessCore + HardwareController + olay zinciri
(i5 aparatı). 2 kapanış kolu × 30 deneme + start_all kolu + KARŞIT (canlı göndericide START sürer).
"""

from __future__ import annotations

import time

import pytest
from test_hwsender_CANLANDIRMA_bayat_RUN_yazmaz import _OLUM, _aparat, _bekle, _gondericiyi_oldur, _stop_mu

DENEME = 30


@_OLUM
@pytest.mark.parametrize("kapatma", [0.0, 0.05], ids=["dogal", "eski_tutamak_kapatma_50ms"])
def test_KRITIK_olu_gondericiyi_canlandiran_START_REDDEDILIR_durum_yazilmaz_N30(tmp_path, kapatma):
    ihlal = 0
    ornek = None
    for n in range(DENEME):
        with _aparat(tmp_path / f"t{n}", olay=True, gecikme=0.15, kapatma=kapatma) as (core, hc, d, api):
            _gondericiyi_oldur(core)  # boştayken ölüm: hiçbir bobin çalışmıyor
            n_acilis, once = len(d.acilan), len(d.yazilan)
            ok = hc.update_coil(1, 100.0, 30.0, 0.0, 1, start=True)
            canlandi = _bekle(lambda: len(d.acilan) > n_acilis and core.stm_is_connected, 3.0)
            _bekle(lambda: core._hw_send_queue.empty(), 2.0)
            time.sleep(0.1)
            durum = hc.coils_state[1]["is_running"]
            run = sum(1 for x in d.yazilan[once:] if not _stop_mu(x[2]))
            bu = ok is not False or durum or run or not canlandi
            ihlal += bool(bu)
            if bu and ornek is None:
                ornek = dict(start=ok, durum=durum, run=run, canlandi=canlandi)
    assert ihlal == 0, (
        f"kapatma={kapatma}: {DENEME} denemenin {ihlal}'inde canlandırma gerektiren START reddedilmedi: {ornek}"
    )


@_OLUM
def test_KRITIK_olu_gondericide_start_all_coils_REDDEDILIR_ve_canlandirma_DENENIR(tmp_path):
    for n in range(5):
        with _aparat(tmp_path / f"t{n}", olay=True, gecikme=0.15) as (core, hc, d, api):
            _gondericiyi_oldur(core)
            n_acilis, once = len(d.acilan), len(d.yazilan)
            ok = hc.start_all_coils(100.0, 30.0, 0.0, 1)
            assert ok is False, "ölü göndericide start_all_coils 'başarılı' döndü"
            assert _bekle(lambda: len(d.acilan) > n_acilis and core.stm_is_connected, 3.0), "canlandırma denenmedi"
            assert not any(hc.coils_state[c]["is_running"] for c in hc.coils_state), "durum yazıldı"
            assert not any(not _stop_mu(x[2]) for x in d.yazilan[once:]), "RUN porta gitti"


@_OLUM
def test_KARSIT_canli_gondericide_START_SURER(tmp_path):
    for n in range(5):
        with _aparat(tmp_path / f"t{n}", olay=True, gecikme=0.15) as (core, hc, d, api):
            once = len(d.yazilan)
            assert hc.update_coil(1, 100.0, 30.0, 0.0, 1, start=True) is True
            assert _bekle(lambda: any(not _stop_mu(x[2]) for x in d.yazilan[once:]), 3.0), "aparat: RUN yazılmadı"
            assert hc.coils_state[1]["is_running"]
