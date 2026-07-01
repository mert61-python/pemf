# -*- coding: utf-8 -*-
"""
PEMF — TEK-DOSYA sır yönetimi (SecretsManager).

Tüm sırlar/token/anahtar/şifreler TEK dosyada toplanır:
    <app_data>/pemf_secrets.json   (genelde C:\\ProgramData\\PEMF_System\\PEMF_GUI\\pemf_secrets.json)

HİBRİT güvenlik:
  • operatör sırları (mqtt, tünel, gmail...) + api_token + pairing/device_id → DÜZ-METİN
    (operatör dosyayı açıp okuyabilir/girebilir; NTFS ACL ile korunur).
  • KRİTİK kripto anahtarları (sqlcipher_key, patient_fernet_key, config_fernet_key,
    master_secret) → dosya İÇİNDE makineye-bağlı **DPAPI** ile şifreli ("DPAPI:<b64>").
    Dosya başka makineye kopyalansa açılmaz + düz-metinde görünmez (KVKK).

LAZY MİGRASYON (veri kaybı YOK): bir anahtar dosyada yoksa, ilk get() çağrısında ESKİ
kaynaktan (env → keyring → eski dosya) okunur ve dosyaya yazılır. Mevcut şifreli DB'leri
açan sqlcipher/fernet anahtarları AYNEN taşınır; yalnız hiçbir eski kaynak yoksa YENİ üretilir.

Kullanım:
    from utils.secrets_manager import get_secret, set_secret
    token = get_secret("api_token")
    set_secret("mqtt_pass", "...")
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets as _secrets
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_FILENAME = "pemf_secrets.json"
_VERSION = 1
_DPAPI_PREFIX = "DPAPI:"
_lock = threading.RLock()
_cache: dict | None = None


# ───────────────────────── yol ─────────────────────────
def _data_dir() -> Path:
    """app_data dizini (PEMF_DATA_DIR'e saygı duyar → ProgramData)."""
    try:
        from utils.path_utils import get_app_data_directory
        return get_app_data_directory()
    except Exception:
        override = os.getenv("PEMF_DATA_DIR", "").strip()
        if override:
            d = Path(override) / "PEMF_GUI"
        else:
            d = Path(os.getenv("APPDATA") or (Path.home() / ".config")) / "PEMF_GUI"
        d.mkdir(parents=True, exist_ok=True)
        return d


def secrets_path() -> Path:
    return _data_dir() / _FILENAME


# ───────────────────────── DPAPI (makine kapsamı) ─────────────────────────
def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    flags = 0x4  # CRYPTPROTECT_LOCAL_MACHINE
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, None, None, None, flags, ctypes.byref(blob_out))
    if not ok:
        raise OSError("DPAPI %s başarısız" % ("protect" if protect else "unprotect"))
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _enc(plain: str) -> str:
    """Düz-metin → 'DPAPI:<b64>' (makineye bağlı). DPAPI yoksa düz döner (uyarı)."""
    try:
        return _DPAPI_PREFIX + base64.b64encode(_dpapi(plain.encode("utf-8"), True)).decode("ascii")
    except Exception as e:
        logger.warning("DPAPI şifreleme yapılamadı, düz saklanıyor: %s", e)
        return plain


def _dec(stored: str) -> str:
    if not stored.startswith(_DPAPI_PREFIX):
        return stored  # düz-metin (eski/fallback)
    raw = base64.b64decode(stored[len(_DPAPI_PREFIX):])
    return _dpapi(raw, False).decode("utf-8")


# ───────────────────────── üreteçler ─────────────────────────
def _gen_urlsafe24() -> str: return _secrets.token_urlsafe(24)
def _gen_urlsafe32() -> str: return _secrets.token_urlsafe(32)


def _gen_fernet() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode("ascii")


def _gen_pairing() -> str:
    alpha = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 0,O,1,I,L hariç
    return "".join(_secrets.choice(alpha) for _ in range(6))


def _gen_device_id() -> str:
    import uuid
    return str(uuid.getnode())


# ───────────────────────── eski-kaynak okuyucular (lazy migration) ─────────────────────────
def _read_file(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""
    except Exception:
        return ""


def _keyring_get(name: str) -> str:
    try:
        import keyring
        return (keyring.get_password("PEMF_GUI", name) or "").strip()
    except Exception:
        return ""


def _legacy_appdata_token() -> str:
    # auth.py eski yolları: PEMF_DATA_DIR (ProgramData) VE %APPDATA% (LocalSystem'de systemprofile).
    # Mevcut token'ı koru → ikisini de dene.
    paths = [_data_dir() / "api_token.txt"]
    appdata = os.getenv("APPDATA")
    if appdata:
        paths.append(Path(appdata) / "PEMF_GUI" / "api_token.txt")
    for p in paths:
        v = _read_file(p)
        if v:
            return v
    return ""


def _config_dir() -> Path:
    # pemf_gui.config Fernet anahtar dosyası (.pemf_key_v2) genelde app_data ile aynı kökte.
    return _data_dir()


# key -> (section, dpapi?, generator|None, legacy_reader|None)
_REGISTRY: dict[str, tuple] = {
    # AUTO (sistem üretir)
    "api_token":          ("auto", False, _gen_urlsafe24,
                           lambda: os.getenv("PEMF_API_TOKEN", "").strip() or _legacy_appdata_token()),
    "pairing_code":       ("auto", False, _gen_pairing,
                           lambda: _read_file(_data_dir() / "pairing_code.txt")),
    "device_id":          ("auto", False, _gen_device_id,
                           lambda: _read_file(_data_dir() / "device_id.txt")),
    "sqlcipher_key":      ("auto", True, _gen_urlsafe32,
                           lambda: _keyring_get("sqlcipher_key") or os.getenv("PEMF_SQLCIPHER_KEY", "").strip()
                                   or _read_file(_data_dir() / ".sqlcipher_key")),
    "patient_fernet_key": ("auto", True, _gen_fernet,
                           lambda: _keyring_get("patient_fernet_key") or _read_file(_config_dir() / ".pemf_key_v2")),
    "master_secret":      ("operator", False, None,  # operatör/env; YOKSA credential_manager uyarı+dosya yolu (oto-üretme yok)
                           lambda: os.getenv("PEMF_MASTER_SECRET", "").strip() or _keyring_get("master_secret")),
    # OPERATOR (operatör girer; üreteç YOK)
    "mqtt_user":               ("operator", False, None, lambda: os.getenv("PEMF_MQTT_USER", "").strip()),
    "mqtt_pass":               ("operator", False, None, lambda: os.getenv("PEMF_MQTT_PASS", "").strip()),
    "cloudflare_tunnel_token": ("operator", False, None, lambda: os.getenv("PEMF_CLOUDFLARE_TUNNEL_TOKEN", "").strip()),
    "tunnel_hostname":         ("operator", False, None, lambda: os.getenv("PEMF_TUNNEL_HOSTNAME", "").strip()),
    "gmail_app_password":      ("operator", False, None, lambda: os.getenv("PEMF_GMAIL_APP_PASSWORD", "").strip()),
    "huggingface_token":       ("operator", False, None, lambda: os.getenv("HF_TOKEN", "").strip()),
    # EMBEDDED (build ile gelir)
    "supabase_url":      ("embedded", False, None,
                          lambda: os.getenv("SUPABASE_URL", "").strip() or "https://wmsxonunkphjeregpvuj.supabase.co"),
    "supabase_anon_key": ("embedded", False, None,
                          lambda: os.getenv("SUPABASE_KEY", "").strip() or "sb_publishable_D2SaRML_PIhRtr3kqlXxaw_1cS75GKT"),
}


# ───────────────────────── dosya yükle/yaz ─────────────────────────
def _empty_doc() -> dict:
    doc = {"_comment": "PEMF tüm sırları. 'operator' bölümünü doldurun; 'auto' kendiliğinden dolar; "
                       "kritik kripto anahtarları DPAPI ile makineye-bağlı şifreli. BU DOSYAYI YEDEKLEYİN.",
           "_version": _VERSION, "auto": {}, "operator": {}, "embedded": {}}
    for key, (section, *_rest) in _REGISTRY.items():
        doc[section].setdefault(key, "")
    return doc


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    p = secrets_path()
    if p.exists():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            for s in ("auto", "operator", "embedded"):
                doc.setdefault(s, {})
        except Exception as e:
            logger.error("pemf_secrets.json okunamadı (%s) — yeni oluşturuluyor.", e)
            doc = _empty_doc()
    else:
        doc = _empty_doc()
    _cache = doc
    return doc


def _save(doc: dict) -> None:
    p = secrets_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass


# ───────────────────────── genel API ─────────────────────────
def get_secret(key: str, default: str = "", generate: bool = True) -> str:
    """Sırrı TEK dosyadan döndür. Yoksa: eski-kaynaktan MİGRATE (her zaman) → (generate=True ise) ÜRET → default.
    generate=False: mevcut/migrate anahtarı döndür ama YOKSA üretme (örn sqlcipher: PEMF_ENCRYPT_AT_REST
    kapalıyken yeni anahtar üretip sifrelemeyi YANLIŞLIKLA açma). Kritik anahtarlar DPAPI ile saklanır/çözülür."""
    if key not in _REGISTRY:
        raise KeyError("Bilinmeyen sır anahtarı: %s" % key)
    section, dpapi, generator, legacy = _REGISTRY[key]
    with _lock:
        doc = _load()
        raw = (doc.get(section, {}).get(key) or "").strip()
        if raw:
            try:
                return _dec(raw)
            except Exception as e:
                logger.error("Sır çözülemedi (%s): %s", key, e)
                # düşmeden migrate/gen denenir
        # 1) eski kaynaktan MİGRATE (her zaman — mevcut DB anahtarı korunur)
        val = ""
        if legacy:
            try:
                val = (legacy() or "").strip()
            except Exception:
                val = ""
        if val:
            logger.info("Sır migrate edildi (eski kaynak → tek dosya): %s", key)
        # 2) yoksa ÜRET (yalnız generate=True + generator var)
        elif generator is not None and generate:
            val = generator()
            logger.info("Sır üretildi (tek dosya): %s", key)
        if not val:
            return default
        # dosyaya yaz (kritikse DPAPI)
        doc[section][key] = _enc(val) if dpapi else val
        _save(doc)
        return val


def set_secret(key: str, value: str) -> None:
    """Operatör/sistem bir sırrı yazar (kritikse DPAPI ile saklanır)."""
    if key not in _REGISTRY:
        raise KeyError("Bilinmeyen sır anahtarı: %s" % key)
    section, dpapi, *_ = _REGISTRY[key]
    with _lock:
        doc = _load()
        doc[section][key] = _enc(value) if (dpapi and value) else value
        _save(doc)


def ensure_file() -> Path:
    """İlk kurulumda dosyayı (boş şablon) oluşturur; auto sırları üretir/migrate eder."""
    with _lock:
        p = secrets_path()
        if not p.exists():
            _save(_empty_doc())
        # auto bölümünü doldur (token + kripto anahtarları üret/migrate)
        encrypt = os.getenv("PEMF_ENCRYPT_AT_REST", "0") == "1"
        for key, (section, *_rest) in _REGISTRY.items():
            if section == "auto":
                # sqlcipher_key YALNIZ at-rest şifreleme açıkken üretilir (mevcutsa yine migrate edilir)
                get_secret(key, generate=(encrypt if key == "sqlcipher_key" else True))
        return p
