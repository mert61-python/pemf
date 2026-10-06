# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""OTO-FİRMWARE YAKMA PENCERESİ — süreç içi bayrak (D1.114 · B-4.6).

Backend kendi açılış yakmasını (`servers/firmware_manager._firmware_uygula`) seri portu BIRAKMADAN yapar: kart kimliği
yakmadan sonra çekirdeğin KENDİ okuyucusundan alınır, ACİL DURDUR'un STM yolu hiç kopmaz. Pencere = ön kontrol → yedek →
yakma → banner → gerekirse geri dönüş. Pencere AÇIKKEN:

  * STM bobin BAŞLATMA reddedilir (`HardwareController` başlatma kapısı — durum kilidi ALTINDA, durum yazımıyla aynı kritik
    bölgede): ön kontrolle yakma arasındaki denetle-sonra-yap aralığında başlatılan bobin MCU resetiyle ANİDEN dururdu.
  * `update_manager.is_update_in_progress()` True → seans / AI Pro başlatma 409.
  * ⚠️ ACİL DURDUR KAPILANMAZ (Ö.4-Y8): STOP yine donanıma VERİLİR; yalnız TEYİDİ dürüstleşir — MCU yakılırken STOP baytı
    ST-Link VCP'ye YAZILIR ama kart işlemez, "porta yazıldı" teyit sayılamaz (`api_server._emergency_stop_all`).

Bu modül YALNIZ bayrak taşır (bağımlılığı yok) — `controllers` / `servers` katmanları birbirini içe aktarmadan okur.
"""

from __future__ import annotations

import contextlib
import threading

_acik = threading.Event()

#: Başlatma reddinin operatöre/günlüğe giden metni.
BASLATMA_ENGELI = (
    "STM32 firmware'i YAZILIYOR (donanım güncellemesi) — bitene kadar bobin başlatılamaz; ACİL DURDUR çalışır."
)


def acik_mi() -> bool:
    """Oto-firmware yakma penceresi şu an açık mı?"""
    return _acik.is_set()


def baslatma_engeli() -> str:
    """Pencere açıksa başlatmayı reddeden metin, değilse ""."""
    return BASLATMA_ENGELI if _acik.is_set() else ""


@contextlib.contextmanager
def ac():
    """Blok boyunca pencereyi açık tutar; her çıkışta (istisna dahil) kapatır."""
    _acik.set()
    try:
        yield
    finally:
        _acik.clear()
