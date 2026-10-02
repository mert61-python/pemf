# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.55 · 1-C bağımsız inceleme i5-F-2 — E-stop'un `stmStopped` teyidi KENDİ STOP paketine bağlıdır.

ÖLÇÜLEN KUSUR (293ff1c, i5 iki koşumda 30/30; karşıt 0/30): `hw_stop_yazildi_bekle(isaret)` "işaretten SONRA porta
HERHANGİ bir tüm-duty-0 paket yazıldı mı"ya bakıyordu. Gönderici bir yazımda gecikirken kuyrukta [STOP_x (ör. operatör
durdurması), RUN_y (hemen ardından START)] bekliyorsa ve E-stop gelirse: STOP_x işaretten sonra yazılıp SAYILIYOR, RUN_y
yazılıyor, E-stop'un KENDİ STOP'u porta YAZILAMIYOR (yazım hatası / o an kablo) → `stmStopped=True` iken porta son giden
paket RUN. ESP açıkken ya da A-63/D1.105 teyidi STM'e bağlanınca bu, ekranda "teyitli E-stop" yalanı olur.

DÜZELTME: HC her kuyruk öğesine artan sıra verir (`_SiraliPaket`), E-stop `stop_all_coils`'tan hemen sonra kendi STOP'unun
sırasını alır; çekirdek yazılan STOP'ların en yüksek sırasını tutar ve teyit "sırası ≥ E-stop STOP'u olan bir STOP
yazıldı" demektir (FIFO). KAPI: i5 aparatı (GERÇEK HeadlessCore + HC + `_emergency_stop_all`), zamanlama Event ile
zorlanır, 30 deneme; KARŞIT: önceki STOP yokken aynı hata → `stmStopped=False`.
"""

from __future__ import annotations

import threading

import pytest
from test_hwsender_CANLANDIRMA_bayat_RUN_yazmaz import (
    _aparat,
    _bekle,
    _durdurma_zamanini_kaydet,
    _duty,
    _stop_mu,
    _surulen_bobin,
)

DENEME = 30


@pytest.mark.parametrize("onceki_stop", [True, False], ids=["onceki_STOP_var", "KARSIT_onceki_STOP_yok"])
def test_KRITIK_estop_teyidi_ONCEKI_STOPu_saymaz_son_paket_RUN_iken_stmStopped_YALAN_DEGIL_N30(tmp_path, onceki_stop):
    kayit, ihlal = [], 0
    for n in range(DENEME):
        with _aparat(tmp_path / f"t{n}") as (core, hc, d, api):
            _surulen_bobin(hc, d, coil_id=2)
            d.kapi = threading.Event()
            assert hc.update_coil(2, 100.0, 40.0, 0.0, 1, start=True) is True  # RUN_a: gonderici yazarken TUTULUR
            assert d.kapida.wait(3), "aparat: gonderici yazimda tutulamadi"
            if onceki_stop:
                assert hc.stop_all_coils() is True  # STOP_x (tum duty 0): kuyrukta bekler
            assert hc.update_coil(1, 100.0, 30.0, 0.0, 1, start=True) is True  # RUN_y: kuyrukta bekler
            beklenen = 4 if onceki_stop else 3  # RUN_a, [STOP_x], RUN_y, E-stop STOP'u
            sayac = {"n": 0}

            def _kanca(conn, b, _s=sayac, _k=beklenen):
                _s["n"] += 1
                if _s["n"] == _k:
                    raise OSError(5, "aparat: WriteFile basarisiz (E-stop STOP'u yazilirken hat koptu)")

            d.acilis_mumkun = False
            d.kanca = _kanca
            _durdurma_zamanini_kaydet(hc, d)
            sonuc: dict = {}
            th = threading.Thread(target=lambda: sonuc.update(api._emergency_stop_all("manual")), daemon=True)
            th.start()
            assert _bekle(lambda: bool(d.durdur_bitti), 3.0), "E-stop STOP'u kuyruga girmedi"
            d.kapi.set()
            th.join(10)
            assert not th.is_alive()
            _bekle(lambda: sayac["n"] >= beklenen, 2.0)
            son = d.yazilan[-1][2]
            son_run = not _stop_mu(son)
            if sonuc.get("stmStopped") is True and son_run:
                ihlal += 1
            kayit.append(
                f"deneme={n:02d} yazim_sirasi={[('RUN' if not _stop_mu(b) else 'STOP') for _, _, b in d.yazilan]} "
                f"E-stop_STOP_yazim_denemesi_patladi={sayac['n'] >= beklenen} stmStopped={sonuc.get('stmStopped')} "
                f"porta_SON_yazilan={'RUN duty=' + str(_duty(son)) if son_run else 'STOP'}"
            )
    kayit.append(
        f"ORAN: stmStopped=True iken porta SON yazilan paket RUN (E-stop STOP'u HIC yazilmadi) = {ihlal}/{DENEME}"
    )
    assert ihlal == 0, f"stmStopped=True ama porta son yazilan RUN: {ihlal}/{DENEME}"
