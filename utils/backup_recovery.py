# Author: mertaygn, cglrgrkn
"""Yedek kurtarma zarfı — makineden BAĞIMSIZ felaket kurtarma.

DENETİM (offsite-backup-no-key-escrow) çözümü.

SORUN
-----
Yedeklenen `.db` dosyaları SQLCipher ile şifreli; anahtar `pemf_secrets.json` içinde
DPAPI `CRYPTPROTECT_LOCAL_MACHINE` ile sarılı, yani MAKİNEYE bağlı. Sonuç: anakart/disk
arızasında ya da Windows yeniden kurulduğunda — off-site yedek dahil — HİÇBİR yedek
açılamaz. Yedek sistemi yalnız mantıksal bozulmaya karşı koruyordu, fiziksel kayba karşı
hiç korumuyordu.

ÇÖZÜM (sahip kararı: D şıkkı — sistem üretimi kurtarma kodu)
-----------------------------------------------------------
Operatörün SEÇTİĞİ bir parola kullanılmaz; bu, zayıf bir parolanın tüm hasta verisini
koruyan en zayıf halka olması demekti. Onun yerine sistem 150 bitlik bir kurtarma kodu
üretir, operatör bunu bir kez kasaya/parola yöneticisine koyar. Anahtarlar bu koddan
scrypt ile türetilen bir anahtarla şifrelenip yedeklerin YANINA `kurtarma-zarfi.enc`
olarak yazılır.

Neden güvenli: kod 150 bit entropili ve SİSTEM üretimi → kaba kuvvet imkânsız, "1234"
riski yok. Zarf tek başına işe yaramaz, kod tek başına işe yaramaz.

NE YAPILMAZ
-----------
  * Kurtarma kodu yedek dizinine ASLA yazılmaz (zarf + kod aynı yerde = koruma yok).
  * `sqlcipher_key` ÜRETİLMEZ (generate=False): şifreleme kapalıyken yanlışlıkla
    anahtar üretip at-rest şifrelemeyi açmak, mevcut düz-metin DB'yi kilitlerdi.
"""

import base64
import hashlib
import json
import logging
import os
import secrets as _secrets
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Yedeklerin yanına yazılan şifreli zarf (off-site'a da kopyalanır).
ENVELOPE_NAME = "kurtarma-zarfi.enc"
# Kurtarma kodunun operatöre gösterildiği yerel dosya — YEDEK DİZİNİNE KOPYALANMAZ.
CODE_FILE_NAME = "KURTARMA-KODU.txt"
# Zarfın gereksiz yere her gün yeniden yazılmaması için yerel parmak izi.
_FP_FILE_NAME = ".recovery_fp"

# Yedekleri OKUYABİLMEK için gereken asgari anahtar kümesi. Fazlasını koymuyoruz:
# zarf ele geçerse açığa çıkacak yüzey kadar küçük olsun.
RECOVERY_SECRET_KEYS = ("sqlcipher_key", "patient_fernet_key")

# base32 alfabesi: 0/1/8/9 yok → elle yazımda rakam-harf karışıklığı azalır.
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_CODE_CHARS = 30  # 30 × 5 bit = 150 bit
_GROUP = 5
# Elle girişte sık yapılan okuma hataları (alfabede olmayan rakamlar → benzer harf).
_CONFUSABLE = {"0": "O", "1": "I", "8": "B"}

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1  # ~16 MB, ~100 ms
_ENVELOPE_VERSION = 1


# ── Kod üretimi / normalleştirme ─────────────────────────────────────────────


def generate_recovery_code() -> str:
    """150 bitlik kurtarma kodu: XXXXX-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX."""
    raw = "".join(_secrets.choice(_ALPHABET) for _ in range(_CODE_CHARS))
    return "-".join(raw[i : i + _GROUP] for i in range(0, _CODE_CHARS, _GROUP))


def normalize_code(code: str) -> str:
    """Tire/boşluk/küçük harf toleransı + sık okuma hatalarını düzelt.

    Türetme HER ZAMAN normalleştirilmiş kod üzerinden yapılır → operatörün kodu
    nasıl yazdığı (tireli/tiresiz/küçük harf) sonucu değiştirmez.
    """
    out = []
    for ch in (code or "").upper():
        ch = _CONFUSABLE.get(ch, ch)
        if ch in _ALPHABET:
            out.append(ch)
    return "".join(out)


def format_code(code: str) -> str:
    """Normalleştirilmiş kodu okunabilir gruplara böl."""
    n = normalize_code(code)
    return "-".join(n[i : i + _GROUP] for i in range(0, len(n), _GROUP))


# ── Zarf ─────────────────────────────────────────────────────────────────────


def _derive(
    code: str, salt: bytes, n: int = _SCRYPT_N, r: int = _SCRYPT_R, p: int = _SCRYPT_P, dklen: int = 32
) -> bytes:
    """Kurtarma kodundan Fernet anahtarı türet (scrypt).

    Yazma ve OKUMA yolları bu TEK fonksiyonu kullanır. Ayrı ayrı scrypt çağırsalardı
    biri değişip diğeri değişmediğinde zarflar sessizce açılamaz hale gelirdi —
    ve bu, ancak gerçek bir felaket kurtarmada fark edilirdi.
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("Kurtarma kodu bos")
    dk = hashlib.scrypt(norm.encode("ascii"), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=64 * 1024 * 1024)
    return base64.urlsafe_b64encode(dk)


def build_envelope(code: str, keys: dict) -> bytes:
    """Anahtar sözlüğünü koddan türetilen anahtarla şifreleyip zarf baytları üret."""
    from cryptography.fernet import Fernet

    if not keys:
        raise ValueError("Zarfa konacak anahtar yok")
    salt = os.urandom(16)
    payload = json.dumps({"keys": keys}, ensure_ascii=False).encode("utf-8")
    token = Fernet(_derive(code, salt)).encrypt(payload)
    doc = {
        "urun": "PEMF",
        "tur": "kurtarma-zarfi",
        "v": _ENVELOPE_VERSION,
        "kdf": {"ad": "scrypt", "n": _SCRYPT_N, "r": _SCRYPT_R, "p": _SCRYPT_P, "dklen": 32},
        "salt": base64.b64encode(salt).decode("ascii"),
        "ct": token.decode("ascii"),
        "olusturma": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "not": (
            "Bu dosya PEMF veritabani anahtarlarini KURTARMA KODU ile sifreli tutar. "
            "Kod olmadan acilamaz. Kodu bu dizinde SAKLAMAYIN."
        ),
    }
    return json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")


def open_envelope(code: str, blob: bytes) -> dict:
    """Zarfı çöz → {anahtar_adi: deger}. Yanlış kod → ValueError."""
    from cryptography.fernet import Fernet, InvalidToken

    try:
        doc = json.loads(blob.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Zarf okunamadi (bozuk dosya?): {e}") from e
    if doc.get("tur") != "kurtarma-zarfi":
        raise ValueError("Bu bir PEMF kurtarma zarfi degil")
    if int(doc.get("v", 0)) != _ENVELOPE_VERSION:
        raise ValueError(f"Desteklenmeyen zarf surumu: {doc.get('v')}")
    kdf = doc.get("kdf") or {}
    salt = base64.b64decode(doc["salt"])
    # KDF parametreleri ZARFTAN okunur → ileride parametreler sertleşse bile eski zarflar
    # açılmaya devam eder (bir sürüm yükseltmesi eski yedekleri kurtarılamaz yapamaz).
    fkey = _derive(
        code,
        salt,
        n=int(kdf.get("n", _SCRYPT_N)),
        r=int(kdf.get("r", _SCRYPT_R)),
        p=int(kdf.get("p", _SCRYPT_P)),
        dklen=int(kdf.get("dklen", 32)),
    )
    try:
        plain = Fernet(fkey).decrypt(doc["ct"].encode("ascii"))
    except InvalidToken as e:
        raise ValueError("Kurtarma kodu YANLIS (zarf acilamadi)") from e
    return json.loads(plain.decode("utf-8"))["keys"]


# ── Yerel kurtarma malzemesi (kod + zarf) ────────────────────────────────────


def get_or_create_code() -> str:
    """Bu kurulumun kurtarma kodunu döndür; yoksa üretip sırlara yazar."""
    from utils import secrets_manager as sm

    code = sm.get_secret("backup_recovery_code", generate=False)
    if not code:
        code = generate_recovery_code()
        sm.set_secret("backup_recovery_code", code)
        logger.warning(
            "Yedek kurtarma kodu URETILDI. Operator bunu makine DISINDA saklamali "
            "(kasa / parola yoneticisi) — aksi halde donanim arizasinda yedekler acilamaz."
        )
    return code


def _collect_keys() -> dict:
    """Zarfa girecek anahtarları topla. ÜRETME YOK (generate=False)."""
    from utils import secrets_manager as sm

    out = {}
    for name in RECOVERY_SECRET_KEYS:
        try:
            val = sm.get_secret(name, generate=False)
        except Exception:
            logger.debug("kurtarma: %s okunamadi", name, exc_info=True)
            continue
        if val:
            out[name] = val
    return out


def write_code_file(app_data_dir: Path, code: str) -> Path | None:
    """Kurtarma kodunu yerel diske yaz (ACL kilitli) — operatör bir yerden okumalı.

    Bu dosya yedek dizinine KOPYALANMAZ; amacı operatörün kodu makine dışına
    taşıyabilmesi. Taşındıktan sonra silinebilir (zarf yine geçerli kalır).
    """
    p = Path(app_data_dir) / CODE_FILE_NAME
    text = (
        "PEMF — YEDEK KURTARMA KODU\n"
        "=============================================================\n\n"
        f"    {format_code(code)}\n\n"
        "BU KODU MAKINE DISINDA SAKLAYIN (kasa / parola yoneticisi / kagit).\n\n"
        "NE ISE YARAR\n"
        "  Yedek dizinindeki  " + ENVELOPE_NAME + "  dosyasini bu kod acar.\n"
        "  Zarfin icinde veritabani sifre-cozme anahtarlari vardir.\n"
        "  Boylece anakart/disk arizasindan sonra BASKA bir makinede\n"
        "  yedekler geri yuklenebilir.\n\n"
        "UYARI\n"
        "  * Bu dosyayi yedek dizinine KOPYALAMAYIN. Kod ve zarf ayni yerde\n"
        "    durursa koruma ortadan kalkar.\n"
        "  * Kod kaybolursa yedekler bu makine disinda ACILAMAZ.\n"
        "  * Kodu disari aldiktan sonra bu dosyayi silebilirsiniz.\n\n"
        "KURTARMA\n"
        "  tools/kurtarma.py --zarf <yedek-dizini>/" + ENVELOPE_NAME + " --kod <kod> --yaz\n"
        "=============================================================\n"
    )
    p.write_text(text, encoding="utf-8")
    try:
        from utils.file_acl import lock_down_file

        lock_down_file(p, keep_current_user=True)
    except Exception:
        logger.debug("kurtarma kodu dosyasi ACL kilitlenemedi", exc_info=True)
    return p


def _fingerprint(code: str, keys: dict) -> str:
    """Zarf içeriğinin parmak izi — YEREL kalır, zarfa yazılmaz (sızıntı yüzeyi açmaz)."""
    h = hashlib.sha256()
    h.update(normalize_code(code).encode("ascii"))
    for k in sorted(keys):
        h.update(b"\x00" + k.encode("utf-8") + b"\x00" + keys[k].encode("utf-8"))
    return h.hexdigest()


def refresh_recovery_material(app_data_dir, dest_dirs) -> bool:
    """Kurtarma kodunu garanti et ve zarfı verilen dizinlere yaz.

    Anahtarlar değişmediyse (parmak izi aynı) ve zarf zaten yerindeyse yeniden
    yazmaz → operatörün doğruladığı dosya gün gün değişip şüphe uyandırmasın.

    Returns: zarf yazıldıysa/yerindeyse True; at-rest şifreleme yoksa False.
    """
    app_data_dir = Path(app_data_dir)
    dests = [Path(d) for d in dest_dirs if d]
    if not dests:
        return False

    keys = _collect_keys()
    if "sqlcipher_key" not in keys:
        # Şifreleme kapalı → yedekler zaten düz-metin, kurtarma zarfı ANLAMSIZ
        # (ve sqlcipher_key'i burada ÜRETMEK şifrelemeyi yanlışlıkla açardı).
        logger.debug("kurtarma zarfi atlandi: sqlcipher_key yok (at-rest sifreleme kapali)")
        return False

    code = get_or_create_code()
    fp = _fingerprint(code, keys)
    fp_file = app_data_dir / _FP_FILE_NAME
    try:
        unchanged = fp_file.read_text(encoding="utf-8").strip() == fp
    except Exception:
        unchanged = False

    missing = [d for d in dests if not (d / ENVELOPE_NAME).exists()]
    if unchanged and not missing:
        return True

    blob = build_envelope(code, keys)
    written = 0
    for d in dests:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / ENVELOPE_NAME).write_bytes(blob)
            written += 1
        except Exception:
            logger.warning("kurtarma zarfi yazilamadi: %s", d, exc_info=True)
    if not written:
        return False

    try:
        fp_file.write_text(fp, encoding="utf-8")
    except Exception:
        logger.debug("kurtarma parmak izi yazilamadi", exc_info=True)

    code_file = app_data_dir / CODE_FILE_NAME
    if not code_file.exists():
        try:
            write_code_file(app_data_dir, code)
            logger.warning(
                "KURTARMA KODU yazildi: %s — bu kodu MAKINE DISINDA saklayin. Yedekleri "
                "baska bir makinede acmanin TEK yolu budur.",
                code_file,
            )
        except Exception:
            logger.warning("kurtarma kodu dosyasi yazilamadi", exc_info=True)

    logger.info("Kurtarma zarfi guncellendi (%d dizin, %d anahtar)", written, len(keys))
    return True
