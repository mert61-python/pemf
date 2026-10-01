# Author: mertaygn, cglrgrkn
"""SONSUZ DÖNGÜ HATA BİLDİRİMİ — bildirimin kendisi döngüyü ÖLDÜREMEZ.

⚠️ NEDEN VAR (2026-09-19'da ölçüldü). Backend'in altı daemon döngüsünün **altısı da**
aynı şekle sahipti:

    while True:
        try:
            ...
        except Exception:
            logging.exception("...")     # <-- BU fırlatırsa `while`dan ÇIKILIR
        time.sleep(N)

`logging` NE ZAMAN fırlatır — ÖLÇÜLEN model (DENETİM-01 B-1.36, DENETİM-04 B-4.17 öncülü D0;
D1.17'de düzeltildi — eski metin "kilitli log → PermissionError, disk dolu → OSError" diyordu):
ürünün yapılandırmasında (stdlib `RotatingFileHandler`, `backend_service._configure_logging`)
kilitli dosyada devir hatası, dolu disk, kapalı handler ve `sys.stderr = None` FIRLATMAZ —
`Handler.emit` hatayı `handleError`'a verir, o da `sys.stderr`'e yazıp yutar. Ölçülen tek
fırlatma: `sys.stderr` KAPALI bir akış nesnesiyken `handleError`'ın kendi yazımı (`ValueError:
I/O operation on closed file`); standart dışı bir handler/filtre de fırlatabilir. Tetik NADİR —
ama olursa thread **sessizce ölür ve bir daha dönmez**, hiçbir yere de yazılmaz.

**En ağır sonucu `session-watchdog`ta:** o döngü seans süresi dolunca bobinlere DONANIM
düzeyinde STOP üretir. Kendi belgesi diyor ki *"firmware keep-alive süreyi her sn
tazelediğinden tek başına auto-stop OLMAZ"*. Yani thread ölürse seans planlanan süreyi
**aşar** ve kimse haberdar olmaz — hasta bu sırada PEMF maruziyetinde kalır.

⚠️ NASIL FARK EDİLDİ: conftest daemon sızıntısını ölçerken tam süit koşumlarından
**birinde** `esp-telemetry-watchdog` süit sonunda yoktu; ikinci koşumda vardı ve izole
ölçümde 72 sn boyunca canlı kaldı. Tekrar üretilemedi — ama tarama kodda bu yolun
**altı yerde** var olduğunu gösterdi. "Tekrar üretemedim" ≠ "yok".

⚠️ BU MODÜL "hatayı yutan" bir modül DEĞİL. İki ayrı kanal dener ve hangisinin çalıştığı
ölçülebilir: önce `logger`, o düşerse ham `sys.__stderr__`. İkisi de düşerse sessiz kalır
— çünkü alternatif, güvenlik bekçisini öldürmektir. Kapı: `tests/test_dongu_hata_bildirimi_OLDURMEZ.py`
her iki dalı da KOŞTURUR (bu depoda "except dalına hiç uğranmıyor" arızası yaşandı).
"""

from __future__ import annotations

import logging
import sys
import traceback

__all__ = ["dongu_hatasini_bildir"]


def dongu_hatasini_bildir(
    mesaj: str,
    *args,
    logger: logging.Logger | None = None,
    seviye: int = logging.ERROR,
    exc_info: bool = True,
) -> str:
    """Sonsuz döngünün yakaladığı hatayı bildirir ve **HİÇBİR KOŞULDA fırlatmaz**.

    `except Exception:` bloğunun İÇİNDEN çağrılmalıdır — geçerli istisnayı kendisi okur.

    `*args` logging'in `%` biçim argümanlarıdır (biçimleme logging'e bırakılır — çağrı yerindeki
    `logger.warning("... %s", e)` AYNEN taşınır). `exc_info=False`: logger kaydı yığın izi
    TAŞIMAZ (eski çağrı da taşımıyorsa günlük içeriği değişmesin — D1.18). Son çare (stderr)
    kanalı yığın izini her durumda basar: oraya düşüldüyse günlük zaten çalışmıyordur.

    Dönüş: hangi kanalın çalıştığı — ``"logger"`` · ``"stderr"`` · ``"sessiz"``.
    Dönüş değeri test edilebilirlik içindir; çağıran okumak zorunda değildir.
    """
    # ⚠️ İstisnayı EN BAŞTA yakala: aşağıdaki `except` blokları `sys.exc_info()`yu
    # geçici olarak DEĞİŞTİRİR; son çare dalında orijinali kaybetmemek için kopyala.
    bilgi = sys.exc_info()

    try:
        (logger or logging.getLogger(__name__)).log(seviye, mesaj, *args, exc_info=bilgi if exc_info else False)
        return "logger"
    except Exception:
        pass

    # Son çare: logging zincirini TAMAMEN atla. `sys.__stderr__` yorumlayıcının
    # orijinal akışıdır — test/capture katmanları `sys.stderr`i değiştirir, bunu değil.
    try:
        akis = sys.__stderr__
        if akis is not None:
            try:
                metin = mesaj % args if args else mesaj
            except Exception:
                metin = f"{mesaj} {args!r}"
            print(f"[DONGU HATASI] {metin}  (logging BASARISIZ)", file=akis)
            if bilgi[0] is not None:
                traceback.print_exception(bilgi[0], bilgi[1], bilgi[2], file=akis)
            akis.flush()
            return "stderr"
    except Exception:
        pass

    return "sessiz"
