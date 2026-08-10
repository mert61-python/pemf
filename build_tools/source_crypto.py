# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KAYNAK ŞİFRELEME — build tarafı giriş noktası (2026-08-06).

İlkeler `utils/source_crypto.py`'de durur ÇÜNKÜ frozen EXE `utils`'i bundle'lar, `build_tools`'u
ETMEZ — çözücünün sahada çalışabilmesi için kod orada olmalı. Bu modül yalnız yeniden dışa
aktarır, böylece şifreleyen (build) ile çözen (saha) AYNI algoritmayı kullanır ve ikisi
birbirinden sürüklenemez.

⚠️ Bu katmanın NE koruyup NE korumadığı: bkz. utils/source_crypto.py başlığı.
"""

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
