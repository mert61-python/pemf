# Author: mertaygn, cglrgrkn
"""TEST YARDIMCISI — `while True` arka plan döngüsünün gövdesini TAM BİR TUR koşturur. ⚠️ pytest TOPLAMAZ.

(`test_` ön eki yok; `topoloji.py` / `kayitci_donanim.py` deseni.)

Döngü AYRI bir iş parçacığında koşar; `time.sleep` (ve istenirse `time.time`) YALNIZ o iş parçacığında
değişir — diğer iş parçacıkları (çalışıyorsa gerçek `session-watchdog`) özgün işlevleri görür. Süreç
genelindeki sleep yaması uyuyan watchdog'u öldürüyordu (B-10.257, D1.41). İlk kullanım D1.36.
"""

from __future__ import annotations

import threading
import time as _time


class TurBitti(BaseException):
    """Döngü `sleep`e vardı → bir tur tamam. BaseException: döngünün `except Exception`'ı yutmasın."""


def bir_tur_kos(fonk, dakika_atla: bool = False, zaman_kaydir: float = 0.0, sure: float = 10.0):
    """`fonk`u ayrı iş parçacığında bir tur koştur → (uyku_sayisi, hatalar).

    `dakika_atla`: o iş parçacığında her `time.time()` çağrısı 61 sn ileri gider (sensör döngüsü dakika
    sınırına varsın). `zaman_kaydir`: o iş parçacığında `time.time()` sabit kaydırılır (duvar saati
    sıçraması; monotonic etkilenmez)."""
    orj_sleep, orj_time = _time.sleep, _time.time
    durum = {"ident": None, "uyku": 0, "zaman": 0}

    def _sleep(s):
        if threading.get_ident() == durum["ident"]:
            durum["uyku"] += 1
            raise TurBitti()
        return orj_sleep(s)

    def _zaman():
        if threading.get_ident() == durum["ident"]:
            if dakika_atla:
                durum["zaman"] += 1
                return orj_time() + 61.0 * (durum["zaman"] - 1)
            return orj_time() + zaman_kaydir
        return orj_time()

    hatalar: list[BaseException] = []

    def _kos():
        durum["ident"] = threading.get_ident()
        try:
            fonk()
        except TurBitti:
            pass
        except BaseException as e:  # noqa: BLE001 — çağıran iddia eder
            hatalar.append(e)

    _time.sleep, _time.time = _sleep, _zaman
    try:
        th = threading.Thread(target=_kos, daemon=True, name="tek-tur")
        th.start()
        th.join(sure)
    finally:
        _time.sleep, _time.time = orj_sleep, orj_time
    assert not th.is_alive(), f"{getattr(fonk, '__name__', fonk)} bir turda sleep'e varmadı ({sure} sn)"
    return durum["uyku"], hatalar
