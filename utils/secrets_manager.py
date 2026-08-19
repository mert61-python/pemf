# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""
PEMF — TEK-DOSYA sır yönetimi (SecretsManager).

Tüm sırlar/token/anahtar/şifreler TEK dosyada toplanır:
    <app_data>/pemf_secrets.json   (genelde C:\\ProgramData\\PEMF_System\\PEMF_GUI\\pemf_secrets.json)

HİBRİT güvenlik:
  • operatör sırları (mqtt, tünel...) + api_token + pairing/device_id → DÜZ-METİN
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
import time
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


# DENETIM 2026-08-04 (P2): sir DIZINI sertlestirilmiyordu. ProgramData mirasi Users'a
# "yeni dosya olustur" + "yeni dosyalari oku" veriyor. Iki somut sonuc:
#   (a) _save() .tmp'yi yazip ACL'i BILEREK ancak os.replace'ten SONRA uyguluyor (sira ZORUNLU;
#       aksi halde yonetici-olmayan surec kendi .tmp'sinin DELETE hakkini kaybedip replace'i
#       dusuruyordu). Dizin kilitli DEGILSE .tmp, TUM duz-metin sirlarla birlikte kisa sure
#       Users-OKUNUR kaliyordu. Dizin kilitliyse .tmp DOGDUGU ANDA kisitlidir → pencere kapanir.
#   (b) _legacy_appdata_token() / sqlcipher legacy okuyucusu <data_dir>/api_token.txt ve
#       .sqlcipher_key'i KOSULSUZ migrate eder → Users-yazilabilir dizinde bu dosyalar ONCEDEN
#       YERLESTIRILEBILIRDI (bilinen-anahtar enjeksiyonu).
# icacls maliyetli → surec basina BIR KEZ.
_dir_hardened = False


def _ensure_dir_hardened(d: Path) -> None:
    global _dir_hardened
    if _dir_hardened:
        return
    # ⚠️ DENETİM 2026-08-04 (P3): bayrak DENEMEDEN ÖNCE True yapılıyordu → tek bir geçici
    # `icacls` hatası (dosya kilidi, AV, geçici izin sorunu) sertleştirmeyi SÜREÇ ÖMRÜ BOYUNCA
    # kapatıyordu; oysa asıl korunmak istenen `_save()` yolu her yazımda tekrar denenebilir.
    # Bayrak artık YALNIZ BAŞARIDA set edilir → sonraki yazımlar yeniden dener.
    try:
        from utils.file_acl import lock_down_dir

        if lock_down_dir(d, keep_current_user=True):
            _dir_hardened = True
        else:
            logger.warning(
                "SIR DIZINI ACL kilidi UYGULANAMADI (%s) — .tmp yazim penceresinde duz-metin "
                "sirlar yerel Users'a okunur kalabilir ve eski-kaynak dosyalari onceden "
                "yerlestirilebilir.",
                d,
            )
    except Exception:
        logger.warning("SIR DIZINI ACL kilidi hata verdi", exc_info=True)


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


# ───────────────────────── makine-bağlı anahtar (Linux/mac — DPAPI eşdeğeri) ─────────────────────────
# Windows'ta DPAPI (LOCAL_MACHINE) kritik anahtarları makineye bağlar. Linux/mac'te DPAPI YOK →
# eskiden _enc sessizce DÜZ-METİN'e düşüyordu (sqlcipher_key/patient_fernet_key düz saklanır → disk/
# yedek/imaj hırsızlığında şifreli DB + PII çözülür). Fix (#6): stabil makine-kimliğinden (/etc/
# machine-id, mac IOPlatformUUID) türetilmiş Fernet ile "MKEY:" öneki → başka makinede çözülemez.
_MKEY_PREFIX = "MKEY:"


def _machine_secret() -> bytes:
    """Makineye-bağlı stabil 32-byte gizli. Linux: /etc/machine-id (veya dbus). mac: IOPlatformUUID.
    Bulunamazsa RuntimeError → çağıran düz-metin fallback + uyarıya düşer."""
    import hashlib
    import platform as _pf

    ident = ""
    if _pf.system() == "Darwin":
        try:
            import re
            import subprocess

            out = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
            m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            if m:
                ident = m.group(1).strip()
        except Exception:
            ident = ""
    else:
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                v = Path(p).read_text(encoding="utf-8").strip()
                if v:
                    ident = v
                    break
            except Exception:
                continue
    if not ident:
        raise RuntimeError("makine kimliği bulunamadı (machine-id/IOPlatformUUID)")
    return hashlib.sha256(("PEMF-secrets-v1:" + ident).encode("utf-8")).digest()


def _machine_fernet():
    from cryptography.fernet import Fernet

    return Fernet(base64.urlsafe_b64encode(_machine_secret()))  # 32 bytes → geçerli Fernet anahtarı


def _is_windows() -> bool:
    return os.name == "nt"


def _enc(plain: str, critical: bool = False) -> str:
    """Düz-metin → makineye-bağlı şifreli. Windows: 'DPAPI:'. Linux/mac: 'MKEY:' (machine-id Fernet).
    critical=True (sqlcipher_key/patient_fernet_key gibi at-rest KRİTİK anahtarlar): şifreleme fail
    ederse düz-metin yazmak yerine RuntimeError (fail-CLOSED, Audit P2) — aksi halde DB anahtarı
    Users-okunur düz kalır → tüm PII. critical=False: eski davranış (uyarı + düz fallback)."""
    if _is_windows():
        try:
            return _DPAPI_PREFIX + base64.b64encode(_dpapi(plain.encode("utf-8"), True)).decode("ascii")
        except Exception as e:
            if critical:
                raise RuntimeError(
                    f"Kritik anahtar DPAPI ile sifrelenemedi → düz-metin YAZILMIYOR (fail-closed): {e}"
                ) from e
            logger.warning("DPAPI sifreleme yapilamadi, duz saklaniyor: %s", e)
            return plain
    try:
        return _MKEY_PREFIX + _machine_fernet().encrypt(plain.encode("utf-8")).decode("ascii")
    except Exception as e:
        if critical:
            raise RuntimeError(
                f"Kritik anahtar makine-bagli sifrelenemedi → düz-metin YAZILMIYOR (fail-closed): {e}"
            ) from e
        logger.warning("Makine-bagli sifreleme yapilamadi (machine-id yok?), duz saklaniyor: %s", e)
        return plain


def _dec(stored: str) -> str:
    if stored.startswith(_DPAPI_PREFIX):
        raw = base64.b64decode(stored[len(_DPAPI_PREFIX) :])
        return _dpapi(raw, False).decode("utf-8")
    if stored.startswith(_MKEY_PREFIX):
        return _machine_fernet().decrypt(stored[len(_MKEY_PREFIX) :].encode("ascii")).decode("utf-8")
    return stored  # düz-metin (eski/fallback)


def bu_makinede_cozulebilir_mi(stored: str) -> bool:
    """Saklanmış bir sır değeri BU makinede çözülebiliyor mu?

    ⚠️ NİÇİN VAR (2026-08-15): veri göçü, eski kökteki HAM `sqlcipher_key` değerini hedefe
    OLDUĞU GİBİ kopyalıyordu. Değer başka bir makine/kullanıcı bağlamında sarılmışsa hedefte
    "saklanmış ama ÇÖZÜLEMEYEN" bir sır oluşuyor; `get_secret` fail-closed `RuntimeError`
    atıyor ve **backend bir daha hiç açılmıyor**. Yani göç, çalışan bir kurulumu açılamaz hâle
    getirebiliyordu. Göç artık kopyalamadan ÖNCE burayı sorar.

    ⚠️ NEDEN BURADA, `path_utils`te DEĞİL: önek (`DPAPI:`/`MKEY:`) ve DPAPI bayrakları TEK
    KAYNAKTA kalsın. `path_utils` kendi ctypes kopyasını yazsaydı `MKEY:` (Linux/macOS yolu)
    kapsam dışı kalır ve aynı tuğla açık kalırdı.

    ⚠️ ÖZYİNELEME SINIRI: `_dec` yol/dosya katmanına DOKUNMAZ (`_data_dir` yalnız `_load`
    içinde çağrılır). `get_sqlcipher_key`/`get_app_data_directory` üzerinden geçen çağrı
    1.9.9/1.9.10'da açılışta sonsuz özyineleme + BSOD üretmişti; bu fonksiyon o yola GİRMEZ.
    `tests/test_goc_anahtar_kapisi.py` çağrı sayısını ölçerek kilitler.

    Düz-metin (bilinen önek yok) → `True`: makineye bağlı değildir, taşınması güvenlidir.
    """
    try:
        _dec(stored)
        return True
    except Exception:
        return False


# ───────────────────────── üreteçler ─────────────────────────
def _gen_urlsafe24() -> str:
    return _secrets.token_urlsafe(24)


def _gen_urlsafe32() -> str:
    return _secrets.token_urlsafe(32)


def _gen_fernet() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode("ascii")


def _gen_pairing() -> str:
    alpha = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 0,O,1,I,L hariç
    return "".join(_secrets.choice(alpha) for _ in range(6))


def _gen_admin_code() -> str:
    # Operatör şifre-sıfırlama yönetici kodu — okunaklı 8 karakter (0,O,1,I,L karışıklığı yok).
    alpha = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(_secrets.choice(alpha) for _ in range(8))


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


def _bundled_cloud(key: str) -> str:
    """PAKETE GÖMÜLÜ bulut-MQTT provizyonunu oku (E-stop bulut aynası — sahip kararı 2026-08-19).

    Konum: frozen'da `sys._MEIPASS/data/cloud_mqtt_provision.json` (PyInstaller datas);
    geliştirmede repo `data/` (git'e girmez). Test override: PEMF_CLOUD_PROVISION_PATH.
    Dosya yok/bozuk → "" (ayna sessizce devre dışı — asla exception sızdırmaz)."""
    try:
        import json as _json
        import sys as _sys

        yol = os.getenv("PEMF_CLOUD_PROVISION_PATH", "").strip()
        if yol:
            aday = Path(yol)
        elif getattr(_sys, "frozen", False):
            kok = getattr(_sys, "_MEIPASS", None) or str(Path(_sys.executable).parent / "_internal")
            aday = Path(kok) / "data" / "cloud_mqtt_provision.json"
        else:
            aday = Path(__file__).resolve().parent.parent / "data" / "cloud_mqtt_provision.json"
        if not aday.exists():
            return ""
        return str(_json.loads(aday.read_text(encoding="utf-8")).get(key) or "").strip()
    except Exception:
        return ""


# key -> (section, dpapi?, generator|None, legacy_reader|None)
_REGISTRY: dict[str, tuple] = {
    # AUTO (sistem üretir)
    "api_token": (
        "auto",
        False,
        _gen_urlsafe24,
        lambda: os.getenv("PEMF_API_TOKEN", "").strip() or _legacy_appdata_token(),
    ),
    "pairing_code": ("auto", False, _gen_pairing, lambda: _read_file(_data_dir() / "pairing_code.txt")),
    "admin_reset_code": (
        "auto",
        False,
        _gen_admin_code,  # operatör şifre-sıfırlama (login 'Şifremi unuttum' + Ayarlar)
        lambda: _read_file(_data_dir() / "admin_reset_code.txt"),
    ),
    "device_id": ("auto", False, _gen_device_id, lambda: _read_file(_data_dir() / "device_id.txt")),
    "sqlcipher_key": (
        "auto",
        True,
        _gen_urlsafe32,
        lambda: (
            _keyring_get("sqlcipher_key")
            or os.getenv("PEMF_SQLCIPHER_KEY", "").strip()
            or _read_file(_data_dir() / ".sqlcipher_key")
        ),
    ),
    "patient_fernet_key": (
        "auto",
        True,
        _gen_fernet,
        lambda: _keyring_get("patient_fernet_key") or _read_file(_config_dir() / ".pemf_key_v2"),
    ),
    # DENETIM (offsite-backup-no-key-escrow): yedeklerin yanina yazilan kurtarma zarfini acan
    # 150-bit kod. Zarf olmadan yedekler BASKA makinede acilamaz (sqlcipher_key DPAPI ile bu
    # makineye bagli). ÜRETİM utils/backup_recovery.get_or_create_code icinde — burada generator
    # YOK ki get_secret(generate=True) ile kazara yeni kod uretilip mevcut zarf ORPHAN kalmasin.
    "backup_recovery_code": ("auto", True, None, lambda: os.getenv("PEMF_BACKUP_RECOVERY_CODE", "").strip()),
    # Coverage-audit P1: bulut capability-token — Supabase RPC'lerinde device_id (gizli-değil) yerine
    # YETKİ anahtarı. dpapi=True (kritik). İlk publish'te TOFU ile bulut secret_hash'e mühürlenir; sonra
    # her RPC (upsert_device/upsert_patient/resolve_patients...) bunu p_secret olarak gönderir.
    "device_registry_secret": (
        "auto",
        True,
        _gen_urlsafe32,
        lambda: os.getenv("PEMF_DEVICE_REGISTRY_SECRET", "").strip(),
    ),
    "master_secret": (
        "operator",
        True,
        None,  # Audit P3: dpapi=True — KDF kökü; set_secret ile girilirse makineye-bağlı şifrele (sqlcipher/patient_fernet ile tutarlı). operatör/env; YOKSA credential_manager uyarı+dosya yolu (oto-üretme yok)
        lambda: os.getenv("PEMF_MASTER_SECRET", "").strip() or _keyring_get("master_secret"),
    ),
    # OPERATOR (operatör girer; üreteç YOK)
    "mqtt_user": ("operator", False, None, lambda: os.getenv("PEMF_MQTT_USER", "").strip()),
    "mqtt_pass": ("operator", False, None, lambda: os.getenv("PEMF_MQTT_PASS", "").strip()),
    "cloudflare_tunnel_token": ("operator", False, None, lambda: os.getenv("PEMF_CLOUDFLARE_TUNNEL_TOKEN", "").strip()),
    "tunnel_hostname": ("operator", False, None, lambda: os.getenv("PEMF_TUNNEL_HOSTNAME", "").strip()),
    # Plan A-2 (2026-08-19): E-STOP BULUT AYNASI kimlik bilgileri — buluta failover etmiş ESP'ye
    # acil durdurmayı ulaştırır (api_server._estop_cloud_mirror). Üreteç YOK (rastgele host/parola
    # anlamsız ve tehlikeli). Tanımsızsa ayna SESSİZCE devre dışı (get_secret default döner —
    # KeyError DEĞİL; adversaryal review F1). Parola dpapi=True.
    # Okuma zinciri: env (PEMF_MQTT_CLOUD_*) → PAKETE GÖMÜLÜ provizyon dosyası (sahip kararı
    # 2026-08-19 gece, "indir-kur yeterli olsun": data/cloud_mqtt_provision.json — git'e girmez,
    # build-time üretilir, bkz. build_tools/make_cloud_provision.py; ilk okumada buraya —
    # pemf_secrets.json'a — taşınır, parola DPAPI'lenir).
    "mqtt_cloud_host": (
        "operator",
        False,
        None,
        lambda: os.getenv("PEMF_MQTT_CLOUD_HOST", "").strip() or _bundled_cloud("mqtt_cloud_host"),
    ),
    "mqtt_cloud_port": (
        "operator",
        False,
        None,
        lambda: os.getenv("PEMF_MQTT_CLOUD_PORT", "").strip() or _bundled_cloud("mqtt_cloud_port"),
    ),
    "mqtt_cloud_user": (
        "operator",
        False,
        None,
        lambda: os.getenv("PEMF_MQTT_CLOUD_USER", "").strip() or _bundled_cloud("mqtt_cloud_user"),
    ),
    "mqtt_cloud_pass": (
        "operator",
        True,
        None,
        lambda: os.getenv("PEMF_MQTT_CLOUD_PASS", "").strip() or _bundled_cloud("mqtt_cloud_pass"),
    ),
    # EMBEDDED (build ile gelir)
    "supabase_url": (
        "embedded",
        False,
        None,
        lambda: os.getenv("SUPABASE_URL", "").strip() or "https://wmsxonunkphjeregpvuj.supabase.co",
    ),
    "supabase_anon_key": (
        "embedded",
        False,
        None,
        lambda: os.getenv("SUPABASE_KEY", "").strip() or "sb_publishable_D2SaRML_PIhRtr3kqlXxaw_1cS75GKT",
    ),
}


# ───────────────────────── dosya yükle/yaz ─────────────────────────
def _empty_doc() -> dict:
    doc = {
        "_comment": "PEMF tüm sırları. 'operator' bölümünü doldurun; 'auto' kendiliğinden dolar; "
        "kritik kripto anahtarları DPAPI ile makineye-bağlı şifreli. BU DOSYAYI YEDEKLEYİN.",
        "_version": _VERSION,
        "auto": {},
        "operator": {},
        "embedded": {},
    }
    for key, (section, *_rest) in _REGISTRY.items():
        doc[section].setdefault(key, "")
    return doc


def _load() -> dict:
    _ensure_dir_hardened(_data_dir())
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
            # KRITIK VERI-KORUMA (DENETIM P0): burada FAIL-OPEN vardi — parse hatasinda sessizce
            # BOS dokuman donuluyordu. Ardindan get_secret eksik anahtari (sqlcipher_key /
            # patient_fernet_key) yeniden URETIP _save() ile dosyanin UZERINE yaziyordu →
            # patients.db + pemf_treatment_history.db + TUM yedekler SONSUZA DEK cozulemez hale
            # geliyordu. get_secret'teki brick-korumasi yalnizca "saklanmis ama COZULEMIYOR"
            # halini kapsiyor; "dosya PARSE EDILEMIYOR" hali bu excepte dusup korumayi ATLIYORDU.
            # Artik FAIL-CLOSED: bozuk dosyayi ASLA ezme, kanit icin sakla, HATA yukselt.
            # (Cagiranlarin tamami try/except ile sarili → surec cokmez, eski yollara duser.)
            try:
                _ts = time.strftime("%Y%m%d_%H%M%S")
                _bad = p.with_name(p.name + f".corrupt.{_ts}")
                p.replace(_bad)
                logger.error("pemf_secrets.json BOZUK (%s) — %s olarak saklandi, YENI URETILMEDI.", e, _bad.name)
            except Exception:
                logger.error("pemf_secrets.json BOZUK (%s) ve yeniden adlandirilamadi — YENI URETILMEDI.", e)
            raise RuntimeError(
                "pemf_secrets.json okunamadi/bozuk. Mevcut sifreli hasta verisini korumak icin "
                "yeni anahtar URETILMEDI ve dosya EZILMEDI. Yedekten geri yukleyin "
                "(bozuk kopya .corrupt.<zaman> olarak saklandi)."
            ) from e
    else:
        # ══════════════════════════════════════════════════════════════════════════════════════
        # KARANTINA KANITI KAPISI (DENETIM 2026-08-17) — fail-closed YALNIZ ILK CAGRIYI kapsiyordu.
        #
        # Yukaridaki blok bozuk dosyayi `.corrupt.<zaman>` olarak KENARA ALIR ve hata yukseltir
        # (kasitli, testle kilitli). Ama dosya artik YOLDAN KALDIRILMIS oldugu icin BIR SONRAKI
        # `_load()` cagrisi `p.exists()` -> False gorup bu dala dusuyor, `_empty_doc()` donuyor ve
        # hata YOK. Ardindan `get_secret("sqlcipher_key")` YENI bir anahtar URETIP `_save()` ile
        # temiz bir dosya yaziyordu. Olculen zincir:
        #   ADIM1 get_sqlcipher_key -> RuntimeError (brick korumasi CALISTI)
        #         ...ama backend_service._initialize_database_safe 'except Exception' ile YUTAR
        #   ADIM2 _resolve_supabase_credentials sessizce gecti; dosya YENIDEN YAZILDI
        #   ADIM3 yeni anahtar uretildi -> ESKISIYLE AYNI DEGIL
        # Sonuc: patients.db + pemf_treatment_history.db karantinaya alinir, cihaz BOS gecmisle
        # acilir; `backup_recovery_code` da sifirlanir -> operatorun kasadaki kurtarma kodu
        # gecersiz olur, `_fingerprint` degistigi icin zarf yeniden yazilir ve `_copy_offsite`
        # OFF-SITE zarfi EZER. ~14 yedek turu sonra eski sifreli yedekler rotasyonla duser ->
        # TIBBI KAYIT KALICI OKUNAMAZ.
        #
        # NEDEN BELLEKTE BIR KILIT YETMEZ: backend sik yeniden baslar; yeni surecte dosya yine YOK
        # olur ve ayni yere dusulur. Bu yuzden kapi DISKTE kalan kanita bakar.
        #
        # TAZE KURULUM BOZULMAZ: dosya yok VE karantina kaniti yok -> eskisi gibi `_empty_doc()`.
        # OPERATORUN CIKIS YOLU ACIK: karantina dosyalarini kaldirmak ("durumu ele aldim") makineyi
        # normal calismaya dondurur — aksi halde cihazi KALICI acilamaz yapardik, yani duzeltmeye
        # calistigimiz seyden daha kotusunu uretirdik.
        #
        # Kilit: tests/test_bozuk_sir_dosyasi_kalici_fail_closed.py (karsit-kanit testleri dahil).
        # ══════════════════════════════════════════════════════════════════════════════════════
        _karantina = sorted(p.parent.glob(p.name + ".corrupt.*"))
        if _karantina:
            _adlar = ", ".join(q.name for q in _karantina[-3:])
            logger.error(
                "pemf_secrets.json YOK ama karantina kaniti VAR (%s) — YENI ANAHTAR URETILMEDI. "
                "Bu makine taze bir kurulum DEGIL; sirlari karantinaya alinmis bir kurulumdur.",
                _adlar,
            )
            raise RuntimeError(
                "pemf_secrets.json yok, ama yaninda karantinaya alinmis bozuk kopya(lar) var "
                f"({_adlar}). Mevcut sifreli hasta verisini korumak icin yeni anahtar URETILMEDI. "
                "Yapilacak: (1) pemf_secrets.json'i yedekten geri yukleyin — tercih edilen yol; "
                "ya da (2) sifreli verinin kalici kaybini KABUL ediyorsaniz karantina dosyalarini "
                "(*.corrupt.*) kaldirin; cihaz o zaman temiz anahtarlarla acilir."
            )
        doc = _empty_doc()
    _cache = doc
    return doc


def _save(doc: dict) -> None:
    p = secrets_path()
    # .tmp YAZILMADAN ONCE dizini kilitle → tmp kisitli ACL'i MIRAS alsin (bkz. _ensure_dir_hardened).
    _ensure_dir_hardened(p.parent)
    # DENETIM P3 (canli kanittan): tmp adi SABITTI. ACL-sirasi hatasindan (bkz. asagi) geride
    # kalan KILITLI bir .tmp, sonraki TUM sir yazimlarini PermissionError ile KALICI olarak
    # engelliyordu — kod duzeltilse bile makine bozuk kaliyordu (sahada gorulen durum:
    # pemf_secrets.json YOK, okunamayan pemf_secrets.json.tmp VAR). Surece-ozel benzersiz ad
    # kullan → bayat bir kalinti asla yolu tikayamaz. Ayrica eski kalintilari temizlemeyi dene.
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    try:
        for _stale in p.parent.glob(f"{p.name}*.tmp"):
            if _stale != tmp:
                try:
                    _stale.unlink()
                except Exception:
                    logger.warning("Bayat sir .tmp temizlenemedi (ACL?): %s", _stale)
    except Exception:
        pass
    with open(tmp, "w", encoding="utf-8") as _f:
        _f.write(json.dumps(doc, ensure_ascii=False, indent=2))
        # DENETIM P0 (dayaniklilik): fsync YOKTU → guc kesintisinde NTFS'te 0-baytlik/yarim dosya
        # kalabiliyordu; bir sonraki acilisda _load() onu "bozuk" gorup (eskiden) anahtarlari
        # yeniden uretiyordu. Once veriyi diske indir, sonra atomik replace yap.
        _f.flush()
        os.fsync(_f.fileno())
    # Audit P2: .tmp'yi de HEMEN kilitle — os.replace'e kadar miras-ACL ile Users-okunur pencere
    # olusuyordu (tmp düz-metin TÜM sirlari tutar).
    #
    # DENETIM P1 — SIRALAMA HATASI: ACL kilidi os.replace'ten ONCE uygulaniyordu. lock_down_file
    # erisimi SYSTEM+Administrators'a kisitladigi icin, surec YONETICI DEGILSE (Tauri launcher
    # "kullanici-basina kurulum, yonetici hakki GEREKTIRMEZ" ile calisir) kendi actigi .tmp
    # uzerindeki DELETE/WRITE hakkini KAYBEDIYOR → os.replace PermissionError firlatiyor →
    # sirlar HIC kalicilasmiyor ve geride okunamaz bir .tmp kaliyordu. (Sahada dogrulandi:
    # %APPDATA%\PEMF_GUI icinde pemf_secrets.json YOK ama pemf_secrets.json.tmp duruyordu.)
    # Cozum: ONCE atomik replace, SONRA hedefe ACL uygula. Basarisizlikta .tmp'yi temizle.
    try:
        os.replace(tmp, p)
    except Exception:
        try:
            tmp.unlink()  # yetim .tmp birakma (icinde duz-metin sirlar var)
        except Exception:
            pass
        raise
    # NTFS ACL kilidi (audit B-1.2): TÜM sırları taşıyan dosya yalnız SYSTEM + Administrators'a
    # açık olsun. os.chmod Windows'ta no-op'tur → düz-metin operatör-sırları Users'a açık kalırdı.
    try:
        from utils.file_acl import lock_down_file

        if not lock_down_file(p, keep_current_user=True):
            logger.warning(
                "SIR dosyası ACL kilidi UYGULANAMADI — tüm sırları taşıyan dosya yerel Users'a açık kalmış olabilir (icacls/OS?)."
            )
    except Exception:
        logger.warning("SIR dosyası ACL kilidi hata verdi", exc_info=True)


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
                # KRİTİK VERİ-KORUMA (brick koruması): sır DEPOLANMIŞ ama çözülemiyor (ör. DPAPI
                # makine/kullanıcı-profili değişti, master-key döndü). Burada YENİ üretip dosyayı EZERSEK
                # mevcut ciphertext'i (ör. patients.db SQLCipher anahtarı) KALICI kaybederiz → tüm şifreli
                # hasta verisi geri-DÖNÜLEMEZ brick olur. Bu yüzden fail-closed: ÜRETME/MİGRATE ETME/EZME,
                # HATA yükselt. Ciphertext dosyada korunur (DPAPI düzelince veya doğru makine/yedekle çözülür).
                logger.error(
                    "Sır çözülemedi (%s): %s — mevcut şifreli değer KORUNUYOR, üretilmiyor (brick koruması).", key, e
                )
                raise RuntimeError(
                    f"Depolanmış sır '{key}' çözülemedi (DPAPI/makine/profil değişmiş olabilir). "
                    f"Var olan şifreli veriyi korumak için yeni anahtar ÜRETİLMEDİ ve dosya EZİLMEDİ. "
                    f"Doğru makineyi kullanın veya pemf_secrets.json yedeğinden geri yükleyin."
                ) from e
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
        doc[section][key] = _enc(val, critical=True) if dpapi else val
        _save(doc)
        return val


def set_secret(key: str, value: str) -> None:
    """Operatör/sistem bir sırrı yazar (kritikse DPAPI ile saklanır)."""
    if key not in _REGISTRY:
        raise KeyError("Bilinmeyen sır anahtarı: %s" % key)
    section, dpapi, *_ = _REGISTRY[key]
    with _lock:
        doc = _load()
        doc[section][key] = _enc(value, critical=True) if (dpapi and value) else value
        _save(doc)
