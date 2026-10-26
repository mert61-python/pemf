# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""pt_yolu — gradient-XAI PT ikizlerinin TEK yol çözücüsü (2026-08-26, cu128 smoke dersi).

ÖLÇÜLDÜ: ai_service imajı minimaldir — apps/backend/utils/model_downloader imaja KOPYALANMAZ
(Dockerfile.ai yalnız 3 kapı modülünü alır). XAI fonksiyonları PT'yi doğrudan
download_model_sync ile çözünce imajda 'No module named utils.model_downloader' ile
zarif düşüşe takılıyordu. Çözüm sırası:
  1) PEMF_AI_MODELS_DIR (ai_service /models mount'u) altında göreli yol,
  2) utils.model_downloader.download_model_sync (klinik tek-EXE / geliştirme —
     EXE bundle / ProgramData / release_assets YEREL araması),
  3) açık FileNotFoundError (sessiz yanlış-yol yok).
"""

from __future__ import annotations

import os
from pathlib import Path


def pt_coz(rel_yol: str) -> str:
    """'ai_hub/<modul>/<dosya>.pt' göreli yolunu ortama göre mutlak yola çöz.

    ⚠️ D3I-E.1 (D3.48 · Y18): çözücü VARSA önce o — `PEMF_AI_MODELS_DIR` onun 1. köküdür ve aday bütünlük süzgecinden geçer (özet
    tutmazsa `ModelButunlukHatasi`, başka köke DÜŞÜLMEZ; kesik kopyada sonraki kök). Eskiden aday VARSA özetlenmeden dönüyordu: launcher
    bu değişkeni her zaman verdiği için XAI ikizleri ve CPN (`weights_only=False`) başka sürüm / kurcalanmış dosyayla yükleniyordu."""
    try:
        from utils.model_downloader import download_model_sync
    except ImportError:
        download_model_sync = None  # imaj profili: utils yok — yalnız mount (eski davranış)
    if download_model_sync is not None:
        return str(download_model_sync(rel_yol))
    kok = os.environ.get("PEMF_AI_MODELS_DIR")
    if kok:
        aday = Path(kok) / rel_yol
        if aday.exists():
            return str(aday)
    raise FileNotFoundError(
        f"XAI PT ikizi bulunamadı: {rel_yol} — PEMF_AI_MODELS_DIR mount'unda yok ve "
        "model_downloader bu profilde mevcut değil."
    )
