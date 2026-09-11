# -*- coding: utf-8 -*-
# Author: mertaygn
"""TEST YARDIMCISI — STM "bağlı" ön koşulu. ⚠️ Bu dosya pytest tarafından TOPLANMAZ.

(`test_` ön eki yok; `topoloji.py` / `capraz.py` ile aynı desen.)

===============================================================================
NEDEN VAR (2026-09-11)
===============================================================================
`HardwareController.update_coil` / `start_all_coils` artık **STM kopukken BAŞLATMAYI
REDDEDİYOR** (saha arızası: donanım bağlı değilken `/api/coil/1/control`
`{"status":"success"}` dönüyordu — `tests/test_stm_kopukken_baslatma_reddi.py`).

`servers.live_state._live_state["stm"]` varsayılanı **"warning"**dir; yani bobin
SÜRÜŞÜNÜ test eden her dosya kapıya çarpar. O testler bağlantıyı değil parametre/kuyruk
semantiğini ölçüyor → ön koşulu açıkça kurmaları gerekir.

⚠️ NEDEN `conftest.py`'de OTOMATİK (autouse) FIXTURE DEĞİL: tüm süiti sessizce "STM bağlı"
yapmak kapıyı GLOBAL OLARAK MASKELER. O zaman kapıyı tamamen silen bir regresyon yeşil
kalırdı. Ön koşul, ihtiyacı olan dosyada GÖRÜNÜR olmalı.
"""

from __future__ import annotations

import contextlib


@contextlib.contextmanager
def stm_bagli():
    """Blok boyunca STM'i "online" yapar; çıkışta ESKİ değeri geri koyar.

    Kullanım:
        with stm_bagli():
            hw.update_coil(1, 50.0, 25.0, 0.0, 10, start=True)
    """
    from servers import live_state as _ls

    with _ls._live_state_lock:
        eski = _ls._live_state["stm"]
        _ls._live_state["stm"] = "online"
    try:
        yield
    finally:
        # ⚠️ Geri koymak ŞART: sızdırılan "online" başka dosyaların kapı testlerini
        # sessizce yeşile boyar (bu depoda kayıtlı test-sızıntısı sınıfı).
        with _ls._live_state_lock:
            _ls._live_state["stm"] = eski
