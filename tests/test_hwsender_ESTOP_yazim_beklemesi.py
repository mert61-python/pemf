# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.55 · 1-C bağımsız inceleme i3-F-5 + i5-F-4 — E-stop'un "STOP porta yazıldı mı" beklemesi yanıtı GECİKTİRMEZ.

ÖLÇÜLEN KUSUR (293ff1c, i3 3/3 + i5): `stmStopped` için bekleme 1,0 sn'ydi ve STOP yazılamadığında (kablo çıkık / ölü
gönderici) E-stop yanıtı ~1,0 sn gecikiyordu; istemcinin yedek zinciri sıralı (E-stop → E-stop → seans durdurma +
stop_all) olduğundan 3. adım ~2 sn'de başlıyordu (A-63: yedek gönderimler teyitten bağımsız ve her zaman koşar).
Üst sınır da kapısızdı: 1 → 6 sn mutantında ilgili 827 test yeşil kaldı, yanıt 6,0 sn (istemci köprü zaman aşımı 5 sn).

DÜZELTME: üst sınır 0,5 sn; STOP'un ŞU AN yazılamayacağı belliyse (gönderici ölü ya da açık seri bağlantı yok) hiç
beklenmez. KAPI (i5 aparatı: GERÇEK HeadlessCore + HC + `_emergency_stop_all`): iki kol — "kablo çıkık" erken çıkışı
(≤0,2 sn), "yazım takıldı" (gönderici canlı, bağlantı açık ama yazım bloklu → bekleme üst sınıra dek; ≤0,8 sn).
"""

from __future__ import annotations

import threading
import time

from test_hwsender_CANLANDIRMA_bayat_RUN_yazmaz import _aparat, _bekle, _surulen_bobin


def test_KRITIK_kablo_cikikken_ESTOP_yaniti_BEKLEMEZ(tmp_path):
    for n in range(3):
        with _aparat(tmp_path / f"k{n}") as (core, hc, d, api):
            _surulen_bobin(hc, d)
            d.acilis_mumkun = False
            d.port_var = False
            assert _bekle(lambda: not core.stm_is_connected and not any(c.is_open for c in d.acilan), 3.0)
            t0 = time.perf_counter()
            govde = api._emergency_stop_all("manual")
            sure = time.perf_counter() - t0
            assert govde["stmStopped"] is False
            assert sure <= 0.2, f"kablo çıkıkken E-stop yanıtı {sure:.3f} sn (yazılamayacak STOP için beklendi)"


def test_KRITIK_yazim_takilmisken_ESTOP_yaniti_UST_SINIRDA_kalir(tmp_path):
    for n in range(3):
        with _aparat(tmp_path / f"t{n}") as (core, hc, d, api):
            _surulen_bobin(hc, d)
            d.kapi = threading.Event()  # bir sonraki yazım (E-stop'un STOP'u) bloklanır: gönderici canlı, bağlantı açık
            try:
                t0 = time.perf_counter()
                govde = api._emergency_stop_all("manual")
                sure = time.perf_counter() - t0
            finally:
                d.kapi.set()
            assert govde["stmStopped"] is False, "yazılmamış STOP 'yazıldı' sayıldı"
            assert sure <= 0.8, f"yazım takılıyken E-stop yanıtı {sure:.3f} sn (üst sınır aşıldı)"
