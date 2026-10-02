# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.55 · 1-C bağımsız inceleme i5 kör kapıları — yazım izi ve canlandırmanın pinlenmemiş sözleşmeleri.

i5-F-6: STOP tanımı (`headless_core._tum_duty_sifir_mi`) paketin BÜTÜN bobinlerine bakmalı. Yalnız ilk 5 duty'ye bakan
mutantta bobin 6 RUN'ı "STOP yazıldı" sayılıyordu (E-stop teyidi yalanı; D1.72'de aynı işlev STOP muafiyetini de
belirler) ve D1.55 + D1.72 kapıları dahil ilgili 827 test YEŞİL kalıyordu.
KAPI: i5 aparatı (GERÇEK HeadlessCore + HC); bobin 6 ve 7 yalnız sürülürken yazılan RUN STOP SAYILMAZ, ardından gelen
`stop_all_coils` STOP'u SAYILIR.
i5-F-7: kapanışta gönderici canlandırılmaz, COM portu yeniden açılmaz.
"""

from __future__ import annotations

import time

from test_hwsender_CANLANDIRMA_bayat_RUN_yazmaz import _OLUM, _aparat, _bekle, _calisan_gondericiler, _duty, _stop_mu


def test_KRITIK_i5F6_yazim_izi_bobin_6_ve_7_RUN_STOP_SAYILMAZ(tmp_path):
    import headless_core as hcm

    with _aparat(tmp_path / "m3") as (core, hc, d, api):
        for bobin in (6, 7):
            isaret = core.hw_yazim_isareti()
            once = len(d.yazilan)
            assert hc.update_coil(bobin, 100.0, 30.0, 0.0, 1, start=True) is True
            assert _bekle(lambda: len(d.yazilan) > once, 3.0)
            pkt = d.yazilan[-1][2]
            duty = _duty(pkt)
            assert duty[bobin - 1] > 0 and not _stop_mu(pkt), f"aparat: bobin {bobin} RUN değil {duty}"
            assert hcm._tum_duty_sifir_mi(pkt) is False, f"bobin {bobin} RUN paketi STOP sayıldı {duty}"
            assert core.hw_stop_yazildi_bekle(isaret, 0.3) is False, f"bobin {bobin} RUN yazıldı, 'STOP yazıldı' dendi"
            isaret2 = core.hw_yazim_isareti()
            assert hc.stop_all_coils() is True
            assert core.hw_stop_yazildi_bekle(isaret2, 3.0) is True


@_OLUM
def test_KRITIK_i5F7_kapanista_gonderici_CANLANDIRILMAZ_port_ACILMAZ(tmp_path):
    """i5-F-7: kapanışta (`_hw_sender_stop` kurulu) gelen bir STOP/E-stop HWSender'ı yeniden BAŞLATMAZ ve COM portunu
    yeniden AÇMAZ (denetim silinince port yeniden açılıyor, 2 sn tutuluyor — yeni örneğin ilk açılışı "port meşgul";
    D1.55 kapısı 9/9 ve ilgili 827 test yeşil kalıyordu). STOP kuyruğa yine girer (Y8) ama "porta yazıldı" denmez."""
    with _aparat(tmp_path / "m4") as (core, hc, d, api):
        t = core._hw_sender_thread
        core._hw_sender_stop.set()
        t.join(3)
        assert not t.is_alive()
        n = len(d.acilan)
        ok = hc.stop_all_coils()
        time.sleep(0.3)
        assert not _calisan_gondericiler(core), "kapanışta HWSender yeniden başlatıldı"
        assert len(d.acilan) == n, f"kapanışta seri port YENİDEN AÇILDI ({n}->{len(d.acilan)})"
        assert ok is False
