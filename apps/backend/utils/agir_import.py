# -*- coding: utf-8 -*-
"""Ağır (torch tabanlı) modül import'larını TEK boğumdan geçirir — A9.

ÖLÇÜLEN ARIZA (2026-09-20, docs/ARIZA-LISTESI.md A9)
    Aynı kod, aynı girdi, iki E2E koşumu: birincisinde 8 AI ucu 200, ikincisinde HEPSİ 500.
    Tek koşumda 38 kez, tam yığın izi:
        File ".../torch/__init__.py", line 465, in <module>
            for name in dir(_C)
        NameError: name '_C' is not defined
    ⚠️ İLK TEŞHİS YANLIŞTI, İZCİYLE ÖLÇÜLDÜ. "İki istek birbiriyle yarışıyor" sanılmıştı;
    eşzamanlı `import torch` tek başına TEKRARLAMADI (3 thread, temiz yorumlayıcı → 0 hata).
    `sys.meta_path` izcisi gerçek tarafları gösterdi:
        1.500 sn  ai-warmup    ai_hub.inference_cat_sound      (backend_service.py)
        1.547 sn  MainThread   torch                            (lifespan/ısıtma)
    `_start_ai_warmup_safe()` bu daemon'ı uvicorn'dan ÖNCE başlatıyor; ses modülü de
    `import torch` yapıyor. İki taraf aynı anda kurarken biri yarım modülü
    `sys.modules`'tan siliyor → `_bootstrap.py:699  sys.modules.pop(spec.name)` →
    `KeyError: 'sympy.assumptions.cnf'` (modül adı koşumdan koşuma DEĞİŞİYOR — yarış imzası).
    torch yarım kalınca süreç boyunca HER `import torch` `NameError: _C` verir; tek zehirli
    import tüm AI'yı öldürür. Etkilenen: kidney_ct · landmark · segmentation · reticulocytes ·
    cat_organ · em_petri · scratch (KLİNİK modüller dahil). Bobin sürüşü etkilenmez — hasta
    güvenliği riski yok; kayıp, tanı erişilebilirliğidir. Tekrar deneyince genelde çalıştığı
    için "bazen oluyor" diye geçiştirilmeye açıktır; bu yüzden kapıyla sabitlendi.

TASARIM — iki parça, ikisi de gerekli:
    · `torch_isit()`  : `backend_service.main()` içinde, ISITMA THREAD'LERİNDEN ÖNCE,
      SENKRON bir kez (ölçüm 1,92 sn). `lifespan`de de çağrılır — idempotenttir, oradaki
      çağrı geç kalan yolları (doğrudan api_server ile açılış) korur. ⚠️ YALNIZ lifespan'de
      olması YETMEZ: `ai-warmup` uvicorn'dan önce başlar, ölçülen arıza tam buydu.
    · `agir_import()` : süreç-geneli tek kilit. Isıtma thread'i, derin hazırlık probu ve
      model yükleyici AYNI kilidi kullanır.

⚠️ RLock, Lock DEĞİL: ağır modüller birbirini import eder (ai_hub.X → ai_hub.Y). Düz Lock
   aynı iş parçacığında kendini kilitlerdi.
⚠️ ZAMAN AŞIMLI: kilit alınamazsa import KİLİTSİZ yapılır ve UYARI basılır. Klinik cihazda
   donmak 500'den kötüdür — bu yol, A9 öncesi davranışa dönüştür, kilitlenme değil.
"""

from __future__ import annotations

import importlib
import logging
import threading
from types import ModuleType

__all__ = ["agir_import", "torch_isit", "kilit_durumu"]

logger = logging.getLogger(__name__)

# Süreç-geneli TEK kilit. Ağır import'ların hepsi buradan geçer.
_KILIT = threading.RLock()

# Kilit için üst sınır. torch ölçümü 1,92 sn; en ağır ai_hub modülü ısıtmayla birlikte
# ~35 sn sürebiliyor (scratch, 872 MB). 120 sn "asla normalde dolmaz" payıdır.
_KILIT_BEKLEME_SN = 120.0

_isitildi = False
_isitma_kilidi = threading.Lock()


def agir_import(yol: str) -> ModuleType:
    """`yol` modülünü süreç-geneli kilit altında import et.

    Zaten `sys.modules`'daysa importlib onu döndürür; kilit yalnız İLK kurulumu serileştirir.
    """
    alindi = _KILIT.acquire(timeout=_KILIT_BEKLEME_SN)
    if not alindi:
        # A9 öncesi davranış: kilitsiz import. Donmaktansa yarış riskini al, ama SESSİZ olma.
        logger.warning(
            "agir_import: kilit %.0f sn içinde alınamadı (%s) — KİLİTSİZ import ediliyor; "
            "eşzamanlı import yarışı (A9) yeniden mümkün",
            _KILIT_BEKLEME_SN,
            yol,
        )
        return importlib.import_module(yol)
    try:
        return importlib.import_module(yol)
    finally:
        _KILIT.release()


def torch_isit() -> bool:
    """`torch`u bir kez, SENKRON, kilit altında kur. True = bu çağrıda kuruldu/kurulu.

    Dönüş False YALNIZCA torch gerçekten import edilemiyorsa (AI'sız kurulum) olur —
    bu bir hata değildir, servis AI'sız çalışmaya devam eder.
    """
    global _isitildi
    with _isitma_kilidi:
        if _isitildi:
            return True
        try:
            agir_import("torch")
            _isitildi = True
            logger.info("torch ısıtıldı (A9: eşzamanlı yarı-import yarışı kapatıldı).")
            return True
        except Exception as e:
            # AI kurulu değilse burası NORMALDİR; servis AI'sız ayakta kalır.
            # ⚠️ Ama TEŞHİS KÖRLÜĞÜ yaratmasın: ilk torch import'u düşerse torch
            # `sys.modules`'da YARIM kalır ve süreç boyunca HER AI ucu 500 verir
            # (A9'da ölçüldü: tek koşumda 38 kez). Tam zincir olmadan bu, "AI kurulu
            # değil" sanılır. exc_info ŞART.
            logger.warning(
                "torch ısıtılamadı (%s: %s) — AI uçları bu süreç boyunca 500 verebilir",
                type(e).__name__,
                e,
                exc_info=True,
            )
            return False


def kilit_durumu() -> dict:
    """Tanılama — testler ve destek paketi için. Sır/DEĞER taşımaz."""
    return {"isitildi": _isitildi, "bekleme_sn": _KILIT_BEKLEME_SN}
