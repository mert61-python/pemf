# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MLX90393 SIFIR OFSETİ ÇIKARIMI — sahip kararı (12 Kasım 2026, ODK tezgâhı): "bobinler kapalıyken ölçülen eksen ofseti çıkarılsın"; FIRMWARE DEĞİŞMEZ.

ÖLÇÜLDÜ (ODK 0. adım, `DENETIM\\ODAK.md` "ÖLÇÜM"): sensörün kendi sıfır kayması ~0,34 mT (sensör ekseninde Y +0,18, Z −0,28 — sensörle birlikte
döner, dış alan değil). Firmware `B=` (son 1 sn'nin tepe |B|'si) bu ofseti İÇERİR: bobinler kapalıyken ~0,38 mT gösterir, düşük dozda değeri
%30–40 fazla okur (ör. bütün bobinler faz 0: B satırı 1,04, ofsetsiz 0,75 mT).

YÖNTEM: kartın `STM_OK` yankısında BÜTÜN duty 0 iken ve son sıfır OLMAYAN duty yankısından ≥ `BOSTA_BEKLEME_S` sonra gelen MLX pencerelerinin
eksen merkezi ((min + maks) / 2) → son `PENCERE_SAYISI` pencerenin medyanı = ofset (sensör ofseti + o konumdaki Dünya alanı; ikisi de bobin dozu
değildir). En az `EN_AZ_PENCERE` boşta pencere görülmeden ofset UYGULANMAZ (ham `B=` aynen kalır). Uygulanınca: |B| = eksen başına
max(|maks − o|, |min − o|) vektör normu (bipolar / tek yönlü salınımın tepesi; eksen tepeleri farklı anlarda ise üst sınır), ham değer
`magnetic_field_ham` olarak korunur, `magnetic_ofset_duzeltildi` işareti konur. Doygun (`S=1`) pencere ofsete KATILMAZ.
"""

from __future__ import annotations

import re
import statistics
import threading
import time
from collections import deque

EKSENLER = (("mag_x_min", "mag_x_max"), ("mag_y_min", "mag_y_max"), ("mag_z_min", "mag_z_max"))
#: Son sürüşten sonra bobin akımı söner + MLX penceresi (1 sn) sürüş anını içermesin.
BOSTA_BEKLEME_S = 2.0
PENCERE_SAYISI = 15
EN_AZ_PENCERE = 3
_DUTY = re.compile(r"STM_OK:\s*D=(?P<d>[-0-9,]+)")


class MlxOfset:
    """Bir MLX hattının (bugün tek: bobin 6 kanalı) boşta ölçülen eksen ofseti ve sürüşte ofsetsiz |B|. İş parçacığı güvenli."""

    def __init__(self, saat=time.monotonic):
        self._saat = saat
        self._kilit = threading.Lock()
        self._merkezler: deque = deque(maxlen=PENCERE_SAYISI)
        self._bosta = False
        self._son_aktif: float | None = None
        self.ofset: list | None = None

    def duty_yankisi(self, satir: str) -> None:
        """`-> STM_OK: D=0,0,… P=…` → kart boşta mı (bütün duty 0) ve son sürüşün anı."""
        m = _DUTY.search(satir)
        if m is None:
            return
        try:
            d = [int(v) for v in m.group("d").split(",") if v]
        except ValueError:
            return
        if not d:
            return
        simdi = self._saat()
        with self._kilit:
            if any(v != 0 for v in d):
                self._bosta = False
                self._son_aktif = simdi
            else:
                self._bosta = True

    def pencere(self, govde: dict) -> None:
        """Telemetri gövdesini YERİNDE düzeltir (yalnız alan + üç eksenin uçları varsa)."""
        if "magnetic_field" not in govde or any(a not in govde or b not in govde for a, b in EKSENLER):
            return
        merkez = [(govde[a] + govde[b]) / 2.0 for a, b in EKSENLER]
        simdi = self._saat()
        with self._kilit:
            bosta = self._bosta and (self._son_aktif is None or simdi - self._son_aktif >= BOSTA_BEKLEME_S)
            if bosta and not govde.get("magnetic_saturated"):
                self._merkezler.append(merkez)
                if len(self._merkezler) >= EN_AZ_PENCERE:
                    self.ofset = [statistics.median(m[i] for m in self._merkezler) for i in range(3)]
            o = self.ofset
        if o is None:
            return
        sapma = [max(abs(govde[b] - o[i]), abs(govde[a] - o[i])) for i, (a, b) in enumerate(EKSENLER)]
        govde["magnetic_field_ham"] = govde["magnetic_field"]
        govde["magnetic_field"] = round(sum(s * s for s in sapma) ** 0.5, 4)
        govde["magnetic_ofset_duzeltildi"] = True
