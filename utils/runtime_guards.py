# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""runtime_guards — ürün süreçlerinde çalışma-anı davranış kilitleri.

DENETİM 2026-08-28 #10. Sevk edilen backend, bir AI modeli her yüklendiğinde ultralytics'in
bağımlılık denetimine giriyor ve `onnxruntime`'ı EKSİK sanıp şunu deniyordu:

    "…\\PEMF_Backend.exe" -m pip install --no-cache-dir onnxruntime      → exit 2

Yani ürün, kendi EXE'sini bir alt-süreç olarak başlatıp kendine paket kurmaya çalışıyordu.
Ölçülen üç zarar: (1) destek mühendisini VAR OLMAYAN bir eksik bağımlılığa yönlendiren kırmızı
log, (2) model başına ~2,9 sn israf (soğuk 3,975 s → yasakla 1,069 s), (3) internete çıkabilen
bir klinikte ürünün kendi bağımlılıklarını habersiz değiştirme ihtimali.

Kök neden metadata tarafında (spec'te `onnxruntime`'ın .dist-info'su toplanmıyordu, düzeltildi)
ama BU KAPI METADATA DÜZELSE BİLE KALMALIDIR: paketlenmiş bir tıbbi cihaz yazılımı çalışma anında
kendi bağımlılıklarını DEĞİŞTİRMEMELİDİR. İki savunma bağımsız olmalı — biri sessizce gerilerse
diğeri ayakta kalsın.

⚠️ Bu modül ultralytics'ten ÖNCE çalışmalı: `AUTOINSTALL` bayrağı ultralytics'in kendi
`utils/__init__.py`'sinde IMPORT ANINDA okunur; sonradan set etmek etkisizdir.
"""

from __future__ import annotations

import os
import sys


def _frozen_mu() -> bool:
    return bool(getattr(sys, "frozen", False))


def pip_kurulumunu_yasakla() -> None:
    """Çalışma anında otomatik paket kurulumunu kapat (idempotent, hatasız).

    - `YOLO_AUTOINSTALL=false`: ultralytics'in pip alt-süreci açmasını engeller. HER ortamda
      uygulanır — geliştirme makinesinde de ürün kodu pip çalıştırmamalı.
    - `ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS=1`: YALNIZ frozen'da. Paketlenmiş üründe eksik
      bağımlılık zaten build zamanında yakalanmalıdır; çalışma anındaki kontrol hiçbir şeyi
      düzeltemez, yalnız model başına saniyeler yakar. Geliştirme ortamında kontrol AÇIK kalır
      ki gerçek bir eksik bağımlılık gizlenmesin.
    """
    os.environ["YOLO_AUTOINSTALL"] = "false"
    if _frozen_mu():
        os.environ["ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS"] = "1"


def kurulum_yasagi_etkin_mi() -> bool:
    """Kapının gerçekten kapalı olduğunu doğrular (kapı testi + /api/ai/hazirlik için)."""
    if os.environ.get("YOLO_AUTOINSTALL", "").lower() != "false":
        return False
    if _frozen_mu() and os.environ.get("ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS") != "1":
        return False
    return True
