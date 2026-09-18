# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KAYNAK ŞİFRELEME — kripto ilkeleri (2026-08-06).

⚠️ NEDEN `utils/` ALTINDA: frozen EXE `utils` paketini bundle'lar, `build_tools`'u ETMEZ.
Çözücü sahada çalışacağı için ilkeler burada durmalı; `build_tools/source_crypto.py` yalnız
buradan yeniden dışa aktarır (build tarafı aynı kodu kullanır → şifreleme/çözme AYNI algoritma).

╔══════════════════════════════════════════════════════════════════════════════════════╗
║ ⚠️ DÜRÜSTLÜK — BU NE KORUR, NE KORUMAZ                                              ║
║ Şifre çözme anahtarı ÜRÜNÜN İÇİNDE gider (frozen EXE'ye gömülür). Bu katman:         ║
║   ✓ KORUR : klasörü kopyalayıp kaynağı doğrudan okumayı, kazara sızmayı              ║
║   ✗ KORUMAZ: tersine mühendislik yapan birini                                        ║
║ GERÇEK koruma `.py → .pyd` (Cython/Nuitka) native derlemedir.                        ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import base64
import hashlib
import os

ENC_SUFFIX = ".pyenc"
MAGIC = b"PEMFENC1"
_KDF_ROUNDS = 200_000
_SALT = b"pemf-vet-source-2026"


def derive_key(password: str) -> bytes:
    """Paroladan Fernet anahtarı türet. Sabit tuz KASITLI: build makinesi ile saha makinesi
    aynı parolayla aynı anahtarı üretmeli."""
    if not password:
        raise ValueError("Parola boş olamaz.")
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _SALT, _KDF_ROUNDS, dklen=32)
    return base64.urlsafe_b64encode(dk)


def _fernet(password: str):
    from cryptography.fernet import Fernet

    return Fernet(derive_key(password))


def encrypt_bytes(data: bytes, password: str) -> bytes:
    return MAGIC + _fernet(password).encrypt(data)


def decrypt_bytes(blob: bytes, password: str) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("Şifreli kaynak dosyası değil (imza uyuşmuyor).")
    return _fernet(password).decrypt(blob[len(MAGIC) :])


def read_password() -> str:
    """Parolayı çöz. SIRA: ortam değişkeni → gömülü parola modülü.

    Sahip parolayı `build_tools/_static_password.py` içine statik yazar; PyInstaller spec'i
    onu `pemf_source_key` adıyla frozen EXE'ye gömer (bkz. PEMF_Backend_onedir.spec).
    Parola yoksa boş döner → şifreleme uygulanmamış build demektir, yükleyici devre dışı kalır.
    """
    env = os.getenv("PEMF_SOURCE_KEY", "").strip()
    if env:
        return env
    # SIRA ÖNEMLİ: frozen EXE'de parola `_internal/_static_password.py` olarak durur (spec onu
    # kök seviyeye koyar) → `_static_password` ilk denenir. Kaynaktan çalışırken
    # `build_tools._static_password` bulunur. `pemf_source_key` ileride farklı bir paketleme
    # kullanılırsa diye korunur.
    for modul in ("_static_password", "build_tools._static_password", "pemf_source_key"):
        try:
            m = __import__(modul, fromlist=["SOURCE_PASSWORD"])
            pw = str(getattr(m, "SOURCE_PASSWORD", "") or "").strip()
            if pw:
                return pw
        except Exception:
            continue
    return ""
