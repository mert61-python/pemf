# Author: mertaygn, cglrgrkn
"""KLİNİK VERİ TAŞIMA — şifreli dışa/içe aktarma (2026-08-08).

NEDEN VAR: kayıtlar bilerek MAKİNEDE tutuluyor (bulut senkronu yok — kişisel veri yurt dışına
çıkmasın, kayıt kliniğin olsun; bkz. sahip kararı). Bunun tek gerçek dezavantajı **cihaz
değişimi**: klinik bilgisayarı yenileyince geçmiş taşınmaz. Çözüm bulut değil, kliniğin
KENDİ kontrolündeki şifreli bir dosya.

⚠️ TUZ RASTGELE — `utils/source_crypto` ile AYNI ŞEYİ YAPMAYIN.
Orada tuz SABİT ve bu kasıtlıdır (build makinesi ile saha makinesi aynı anahtarı türetmeli).
Burada parola KULLANICININ seçtiği bir paroladır: sabit tuz, önceden hesaplanmış tablolara ve
aynı parolayla üretilen dosyalar arasında ilişkilendirmeye açık olurdu. Tuz her dışa aktarımda
yeniden üretilir ve dosyanın başına yazılır.

DOSYA BİÇİMİ:
    b"PEMFDATA1"  (9 bayt sihirli imza)
  + salt          (16 bayt, rastgele)
  + Fernet jetonu (AES-128-CBC + HMAC-SHA256 — bütünlük DAHİL)
Açık metin = gzip(JSON). Yanlış parola/bozuk dosya → Fernet doğrulaması PATLAR (sessiz bozulma yok).
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
from typing import Any, Dict

MAGIC = b"PEMFDATA1"
SALT_LEN = 16
_KDF_ROUNDS = 200_000
# v2 (2026-08-09): paket artık tıbbi kaydın TAMAMINI taşır — bobin koşuları (uygulanan doz),
# sensör telemetrisi, seans olayları/parametreleri ve hasta satırları. v1 yalnız seans
# BAŞLIKLARINI + AI analizlerini taşıyordu; içe aktarma v1'i de okumaya devam eder.
BUNDLE_VERSION = 2


class ExportError(Exception):
    """Dışa/içe aktarma hatası (yanlış parola, bozuk dosya, uyumsuz sürüm)."""


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    dk = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, _KDF_ROUNDS, dklen=32)
    return base64.urlsafe_b64encode(dk)


#: Yedek parolası için ASGARİ uzunluk.
#
# ⚠️ DENETİM 2026-08-09 (Tier 1): eskiden yalnız "boş olmasın" kuralı vardı — tek karakterlik bir
# parola kabul ediliyordu. Bu dosya bir kliniğin TÜM hasta geçmişini taşır ve kopyası off-site'a
# gider; oradaki tek koruma paroladır. PBKDF2 200k turu, kısa bir parolayı kurtarmaz.
# Karakter-sınıfı kuralı (büyük/küçük/rakam) yerine UZUNLUK şart koşuluyor: kullanıcı-şifresinden
# farklı olarak bu bir PAROLA CÜMLESİDİR ve uzunluk, hatırlanabilirliği bozmadan entropi verir.
MIN_PAROLA = 12


def parola_gecerli_mi(passphrase: str) -> tuple:
    """(gecerli, sebep). Sunucu ve istemci AYNI kuralı uygulasın diye tek yerde."""
    p = (passphrase or "").strip()
    if not p:
        return False, "Parola boş olamaz — şifresiz tıbbi veri dosyası üretilmez."
    if len(p) < MIN_PAROLA:
        return False, (
            f"Parola en az {MIN_PAROLA} karakter olmalı. Bu dosya kliniğin tüm hasta "
            "geçmişini taşır ve tek koruması bu paroladır."
        )
    if len(set(p)) < 4:
        return False, "Parola çok basit (aynı karakterlerin tekrarı). Farklı karakterler kullanın."
    return True, ""


def encrypt_bundle(payload: Dict[str, Any], passphrase: str) -> bytes:
    """JSON paketini şifrele. Parola politikası `parola_gecerli_mi`de (sunucu tarafı zorunlu)."""
    ok, sebep = parola_gecerli_mi(passphrase)
    if not ok:
        raise ExportError(sebep)
    from cryptography.fernet import Fernet

    salt = os.urandom(SALT_LEN)
    duz = gzip.compress(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
    token = Fernet(_derive_key(passphrase, salt)).encrypt(duz)
    return MAGIC + salt + token


def decrypt_bundle(blob: bytes, passphrase: str) -> Dict[str, Any]:
    """Şifreli paketi çöz. Yanlış parola / kurcalanmış dosya → `ExportError`."""
    from cryptography.fernet import Fernet, InvalidToken

    if not blob.startswith(MAGIC):
        raise ExportError("Bu dosya bir PEMF Vet veri yedeği değil.")
    salt = blob[len(MAGIC) : len(MAGIC) + SALT_LEN]
    token = blob[len(MAGIC) + SALT_LEN :]
    if len(salt) != SALT_LEN or not token:
        raise ExportError("Dosya bozuk (eksik başlık).")
    try:
        duz = Fernet(_derive_key(passphrase, salt)).decrypt(token)
    except InvalidToken as e:
        # Yanlış parola ile kurcalanmış dosyayı AYIRMAYIZ: ikisi de "açılamadı"dır.
        raise ExportError("Parola yanlış ya da dosya bozulmuş.") from e
    try:
        payload = json.loads(gzip.decompress(duz).decode("utf-8"))
    except Exception as e:
        raise ExportError("Dosya içeriği okunamadı.") from e
    if not isinstance(payload, dict):
        raise ExportError("Dosya içeriği beklenen biçimde değil.")
    surum = int(payload.get("bundle_version") or 0)
    if surum > BUNDLE_VERSION:
        raise ExportError(f"Bu yedek daha yeni bir sürümle üretilmiş (v{surum}). Önce uygulamayı güncelleyin.")
    return payload
