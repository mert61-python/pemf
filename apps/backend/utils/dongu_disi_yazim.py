# -*- coding: utf-8 -*-
"""Olay döngüsü iş parçacığından gelen KAYIT yazımlarını döngüyü dondurmadan yürütür (C2-4.1 · Ö.4-Y8).

NEDEN: async uçlar (AI değerlendirmesi/silme 428 red izi, seans başlatma `session_started`, bobin kontrolü koşu kaydı, dışa
aktarma / destek paketi izi …) tedavi DB'sine OLAY DÖNGÜSÜ iş parçacığında senkron yazıyordu. Tedavi DB'si başka bir yazıcı
tarafından kilitliyken her yazım `busy_timeout` (5 sn) kadar bekliyor → döngü donuyor, o sırada gelen ACİL DURDUR isteği
işlenemiyordu [ölçüldü — 2-C incelemesi: jetonsuz değerlendirme yükünde ACİL DURDUR 9,8 sn, STOP donanım kuyruğuna 4,4 sn;
seans içi bobin başlat/durdur yükünde STOP kuyruğa 9,8 sn]. B2B2-1 aynı sınıfı yalnız KİMLİK DB'si okumaları için kapatmıştı.

KURAL: döngü iş parçacığında çağrılırsa iş TEK işçili (FIFO — kayıt sırası korunur) ayrı bir yürütücüde koşar ve en çok
`BEKLEME_SN` beklenir: normal yükte yazım ms'de biter → davranış AYNI (yanıt yazımdan SONRA döner). DB meşgulse döngü en çok
`BEKLEME_SN` bekler, yazım KAYBOLMAZ — işçide tamamlanır (ya da DB katmanının kendi hata yolu ERROR yazar). Kuyrukta BİTMEMİŞ
kayıt varsa (DB meşgul) HİÇ beklenmez: tek tek sınırlı beklemeler eşzamanlı isteklerde TOPLANIYORDU (3 istemcide ACİL DURDUR 1,9 sn).
Döngü dışından (iş parçacığı havuzu, ACİL DURDUR iş parçacığı, senkron rotalar) çağrı DOĞRUDAN, eşzamanlı koşar (eski davranış).
Yeni `await` noktası EKLEMEZ (başlatma akışının atomikliği değişmez). Kapı:
tests/test_kayit_DB_KILITLIYKEN_dongu_yazimi_ACIL_DURDUR_BEKLEMEZ_C2_4_1.py
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import logging
import threading

BEKLEME_SN = 0.25  # B2B2-1'in katı kimlik okumasıyla aynı sınır
#: C2-2.5 / C2-1.3: durdurma yanıtının STOP'tan sonraki kayıt kapanışını en çok bekleyeceği süre (sn). Sağlıklı DB'de kapanış
#: ms'de biter (yanıt eskisi gibi kayıttan SONRA döner); kilitli tedavi DB'sinde ACİL DURDUR yanıtı 21,7 sn bekliyordu.
DURDURMA_KAYIT_BEKLEME_SN = 1.0

_logger = logging.getLogger(__name__)
_kilit = threading.Lock()
_yerel = threading.local()  # `iscide`: çağıran FIFO işçinin kendisi mi (kendini bekleyip kilitlenmesin)
_yurutucu: concurrent.futures.ThreadPoolExecutor | None = None
_sayac_kilidi = threading.Lock()
_bekleyen = 0  # kuyruğa girmiş, henüz BİTMEMİŞ iş sayısı (geri birikim)


def _isci() -> concurrent.futures.ThreadPoolExecutor:
    global _yurutucu
    with _kilit:
        if _yurutucu is None:
            _yurutucu = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="pemf-kayit-yazim")
        return _yurutucu


def _iscide_kos(baglam: contextvars.Context, fn, args, kwargs):
    global _bekleyen
    _yerel.iscide = True
    try:
        return baglam.run(fn, *args, **kwargs)
    finally:
        with _sayac_kilidi:  # sonuç bekleyene ULAŞMADAN önce düşülür (ardışık çağrı birikim görmez)
            _bekleyen -= 1


def _kuyrukta_bekle(fn, args, kwargs, bekleme_sn: float, ad: str):
    global _bekleyen
    yurutucu = _isci()
    with _sayac_kilidi:
        birikim = _bekleyen
        _bekleyen += 1
    try:
        gelecek = yurutucu.submit(_iscide_kos, contextvars.copy_context(), fn, args, kwargs)
    except BaseException:
        with _sayac_kilidi:
            _bekleyen -= 1
        raise
    # ⚠️ GERİ BİRİKİM (2-C incelemesi, C2-3.2 kapısının ölçümü): kuyrukta BİTMEMİŞ kayıt varsa DB meşgul demektir — beklemek
    # yalnız döngüyü / yanıtı geciktirir ve eşzamanlı isteklerde gecikmeler TOPLANIR (3 istemcide ACİL DURDUR 1,9 sn). O zaman
    # hiç beklenmez; sıra yine korunur (iş kuyrukta). Sağlıklı DB'de kuyruk boştur → davranış AYNI.
    try:
        return gelecek.result(timeout=0 if birikim else bekleme_sn)
    except concurrent.futures.TimeoutError:
        gelecek.add_done_callback(_gec_hata_gunlugu(ad))
        (_logger.debug if birikim else _logger.warning)(
            "%s: kayit veritabani mesgul — yazim arka planda SURUYOR (olay dongusu ve ACIL DURDUR beklemez)", ad
        )
        return None


def dongude_mi() -> bool:
    """Çağıran iş parçacığında ÇALIŞAN bir asyncio döngüsü var mı (async uç gövdesi)?"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _gec_hata_gunlugu(ad: str):
    def _bitti(gelecek: concurrent.futures.Future) -> None:
        if gelecek.cancelled():
            return
        hata = gelecek.exception()
        if hata is not None:
            _logger.error("%s: arka planda tamamlanan kayit yazimi HATA verdi: %r", ad, hata)

    return _bitti


def calistir(fn, *args, ad: str = "kayit", **kwargs):
    """`fn(*args, **kwargs)`: döngü dışında doğrudan; döngüde FIFO işçide, en çok `BEKLEME_SN` beklenerek.

    Döngüde süre dolarsa `None` döner (iş işçide SÜRER — kaybolmaz) ve uyarı yazılır. Süre içinde biten işin sonucu/istisnası
    aynen döner."""
    if not dongude_mi():
        return fn(*args, **kwargs)
    return _kuyrukta_bekle(fn, args, kwargs, BEKLEME_SN, ad)


def sirada_calistir(fn, *args, bekleme_sn: float = DURDURMA_KAYIT_BEKLEME_SN, ad: str = "kayit", **kwargs):
    """`fn(*args, **kwargs)`'u döngüde OLMASA da FIFO işçide koşar (önceden kuyruğa girmiş kayıtlardan SONRA) ve en çok
    `bekleme_sn` bekler (C2-2.5 · C2-1.3 · Ö.4-Y8).

    DURDURMA yollarının STOP'tan SONRAKİ kayıt kapanışı için (ACİL DURDUR, AI Pro durdurma): tedavi DB'si kilitliyken yanıt
    ve teyit kayıt yazımını beklemez (kayıt işçide tamamlanır); kuyruktaki koşu başlatma / seans izi kayıtlarından sonra
    koştuğu için kayıt sırası bozulmaz. İşçinin kendisinden ya da işçi açılamazken (kapanış) doğrudan koşar. Süre dolarsa
    `None`."""
    if getattr(_yerel, "iscide", False):
        return fn(*args, **kwargs)
    try:
        return _kuyrukta_bekle(fn, args, kwargs, bekleme_sn, ad)
    except RuntimeError:  # yürütücü kapatıldı / iş parçacığı açılamadı → eski (eşzamanlı) yol
        return fn(*args, **kwargs)


def bosalt(sure: float = 30.0) -> bool:
    """Bekleyen kayıt yazımları bitene dek bekler (testler / kapanış). Döngü iş parçacığından ÇAĞIRMAYIN."""
    with _kilit:
        y = _yurutucu
    if y is None:
        return True
    try:
        y.submit(lambda: None).result(timeout=sure)
        return True
    except concurrent.futures.TimeoutError:
        return False
