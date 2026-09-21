# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KAYNAK ŞİFRELEME — build tarafı giriş noktası (2026-08-06).

İlkeler `apps/backend/utils/source_crypto.py`'de durur ÇÜNKÜ frozen EXE `utils`'i bundle'lar, `build_tools`'u
ETMEZ — çözücünün sahada çalışabilmesi için kod orada olmalı. Bu modül yalnız yeniden dışa
aktarır, böylece şifreleyen (build) ile çözen (saha) AYNI algoritmayı kullanır ve ikisi
birbirinden sürüklenemez.

⚠️ Bu katmanın NE koruyup NE korumadığı: bkz. apps/backend/utils/source_crypto.py başlığı.
"""

import sys
from pathlib import Path


# ── DEPO KÖKÜ + BACKEND YOLU ─────────────────────────────────────────────────
# ⚠️ Bu dosya 2026-09-18 klasör taşımasından (F4: `apps/backend/`) beri ÖLÜYDÜ —
#    `utils` artık depo kökünde değil, `apps/backend/` altında. Açılışta
#    `ModuleNotFoundError: No module named 'utils'` atıyordu. Ölçüldü 2026-09-21.
# ⚠️ SABİT DERİNLİK (`parents[1]`) YAZILMAZ: taşımada sessizce kayar ve bu depoda tam
#    o sınıf kod korumasını kırdı. Kök, İŞARET DOSYASIYLA yukarı aranır.
def _depo_koku(bas: Path) -> Path:
    for aday in (bas, *bas.parents):
        if (aday / "pyproject.toml").is_file() and (aday / "apps" / "backend").is_dir():
            return aday
    raise RuntimeError("depo kökü bulunamadı (işaret: pyproject.toml + apps/backend). Betik depo dışına mı taşındı?")


_KOK = _depo_koku(Path(__file__).resolve())
for _yol in (_KOK, _KOK / "apps" / "backend"):
    if str(_yol) not in sys.path:
        sys.path.insert(0, str(_yol))

from utils.source_crypto import (  # noqa: F401
    ENC_SUFFIX,
    MAGIC,
    decrypt_bytes,
    derive_key,
    encrypt_bytes,
    read_password,
)


def encrypt_file(src: str, dst: str, password: str) -> int:
    with open(src, "rb") as f:
        raw = f.read()
    blob = encrypt_bytes(raw, password)
    with open(dst, "wb") as f:
        f.write(blob)
    return len(blob)


def decrypt_file(src: str, dst: str, password: str) -> int:
    with open(src, "rb") as f:
        blob = f.read()
    raw = decrypt_bytes(blob, password)
    with open(dst, "wb") as f:
        f.write(raw)
    return len(raw)
