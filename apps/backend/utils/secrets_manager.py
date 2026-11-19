# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""
PEMF — TEK-DOSYA sır yönetimi (SecretsManager).

Tüm sırlar/token/anahtar/şifreler TEK dosyada toplanır:
    <app_data>/pemf_secrets.json   (genelde C:\\ProgramData\\PEMF_System\\PEMF_GUI\\pemf_secrets.json)

HİBRİT güvenlik:
  • operatör sırları (mqtt, tünel...) + api_token + pairing/device_id → DÜZ-METİN
    (operatör dosyayı açıp okuyabilir/girebilir; NTFS ACL ile korunur).
  • KRİTİK kripto anahtarları (sqlcipher_key, patient_fernet_key, backup_recovery_code,
    device_registry_secret, master_secret, mqtt_cloud_pass) → dosya İÇİNDE makineye-bağlı **DPAPI**
    (CRYPTPROTECT_LOCAL_MACHINE; Linux/mac'te "MKEY:") ile şifreli ("DPAPI:<b64>"). Dosya başka makineye
    kopyalansa açılmaz + düz-metinde görünmez (KVKK); makine dışı kurtarma = kurtarma zarfı (`utils.backup_recovery`).
  • `config.json`un şifreli alanları için AYRI bir sır YOK: anahtar `patient_fernet_key`dir (`pemf_gui.config`).
    1.9.50 ve öncesinin `.pemf_key`i bu dosyada DEĞİLDİR — veri kökünde DÜZ dosyadır, yalnız eski değerleri çözmek
    için OKUNUR (üretilmez) ve yalnız NTFS ACL ile korunur (`backend_service._harden_secret_file_acls`).
    ⚠️ D6.09 (B-3.7): bu liste eskiden kayıtta OLMAYAN bir "config" Fernet anahtarı sayıyordu. Kapı:
    tests/test_sqlcipher_anahtar_YERI_belge_ve_ileti_D6_09.py (liste = kayıttaki DPAPI'li sırlar).

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
import copy
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
# ⚠️ D2.80 (B-3.52): başarısız sertleştirme GERİ ÇEKİLİR. Bayrak yalnız başarıda kurulduğu için (P3, aşağıda) sertleştirme
# düşerken — LocalSystem'de D-3.1, kilitli dizin, AV — eskiden HER `get_secret` (önbellek denetiminden ÖNCE) ve her `_save` küresel
# `_lock` altında `icacls` (10 sn zaman aşımı) koşturuyordu. Artık başarısız denemeden sonra bu süre dolmadan yeniden denenmez;
# süre dolunca bir sonraki okuma/yazım yeniden dener (kalıcı kapatma YOK). Kapı: tests/test_sir_dosyasi_ERISIM_reddi_BOZUK_sayilmaz_D280.py
_SERTLESTIRME_GERI_CEKILME_SN = 60.0
_sertlestirme_sonraki = 0.0  # time.monotonic(); bu andan ÖNCE yeniden denenmez


def _ensure_dir_hardened(d: Path) -> None:
    global _dir_hardened, _sertlestirme_sonraki
    if _dir_hardened:
        return
    simdi = time.monotonic()
    if simdi < _sertlestirme_sonraki:
        return
    # ⚠️ DENETİM 2026-08-04 (P3): bayrak DENEMEDEN ÖNCE True yapılıyordu → tek bir geçici
    # `icacls` hatası (dosya kilidi, AV, geçici izin sorunu) sertleştirmeyi SÜREÇ ÖMRÜ BOYUNCA
    # kapatıyordu; oysa asıl korunmak istenen `_save()` yolu her yazımda tekrar denenebilir.
    # Bayrak artık YALNIZ BAŞARIDA set edilir → sonraki yazımlar (geri çekilme süresi dolunca) yeniden dener.
    try:
        from utils.file_acl import lock_down_dir

        if lock_down_dir(d, keep_current_user=True):
            _dir_hardened = True
        else:
            _sertlestirme_sonraki = simdi + _SERTLESTIRME_GERI_CEKILME_SN
            logger.warning(
                "SIR DIZINI ACL kilidi UYGULANAMADI (%s) — .tmp yazim penceresinde duz-metin "
                "sirlar yerel Users'a okunur kalabilir ve eski-kaynak dosyalari onceden "
                "yerlestirilebilir. %d sn sonra yeniden denenecek.",
                d,
                int(_SERTLESTIRME_GERI_CEKILME_SN),
            )
    except Exception:
        _sertlestirme_sonraki = simdi + _SERTLESTIRME_GERI_CEKILME_SN
        logger.warning("SIR DIZINI ACL kilidi hata verdi", exc_info=True)


# ⚠️ D2.80 (B-3.13 · O-2A.3 / O-A2-1.c): sır dosyasına ERİŞİLEMİYOR (izin / G-Ç) ≠ dosya BOZUK. Eskiden `_load` her okuma
# istisnasını "BOZUK" sayıp dosyayı `.corrupt.<zaman>` adına taşımayı deniyordu: yükseltilmemiş süreçte DACL süreci dışarıda
# bırakınca SAĞLAM dosya yeniden adlandırılıyor (üst dizin silmeye izin veriyorsa — ölçüldü, gerçek ACL) ve sonraki her açılış
# "karantina kanıtı var" ile KALICI kapalı kalıyordu; adlandırma tutmasa bile ileti "bozuk kopya saklandı, yedekten geri
# yükleyin" diyordu (ikisi de yanlış). Artık erişim hatasında dosyaya DOKUNULMAZ ve hata doğru eylemi söyler.
# ⚠️ Tür BİLEREK `PermissionError`/`OSError` kalır, `RuntimeError` DEĞİL: çağıranlar (`sqlcipher_util.get_sqlcipher_key`,
# `pemf_gui.config._get_or_create_key`) `RuntimeError`'ı "sır VAR ama ÇÖZÜLEMEZ (brick)", diğerini "OKUNAMADI/YAZILAMADI" diye
# sınıflar ve ikisinde de yeni anahtar üretmez (fail-closed, Karar 6). Erişim reddini `RuntimeError` yapmak günlüğe yanlış
# neden yazdırıyordu (ölçüldü: ikinci hesap kapısı A14 ve A12 bunu yakaladı).
# O-A2-1.b: ikinci hesap kipinde bu hata her `get_secret` çağrısında (Y43 yeniden denemeleri + çağıranlar) yükselir ve
# günlük 5 sn'de onlarca aynı satırla doluyordu (ölçüldü). `tekrar_kisitli_hata`: satır ilk kez ERROR basılır, AYNI anahtar +
# AYNI neden süre içinde tekrarlanınca BASILMAZ (sayılır), süre dolunca ya da neden değişince basılan satır sayıyı söyler.
_ERISIM_GUNLUK_ARALIK_SN = 60.0
_tekrar_gunluk: dict = {}


def tekrar_kisitli_hata(gunlukcu, anahtar: str, neden: str, ileti: str, *args) -> bool:
    """`ileti % args`i ERROR olarak basar — aynı `anahtar` ve aynı `neden` son basımdan bu yana `_ERISIM_GUNLUK_ARALIK_SN` sn
    dolmadan tekrarlanıyorsa basmaz, sayar. Basıldıysa True. Davranışı DEĞİŞTİRMEZ (yalnız günlük); çağıran hatayı yine yükseltir."""
    simdi = time.monotonic()
    with _lock:
        k = _tekrar_gunluk.get(anahtar)
        if k and k["neden"] == neden and simdi - k["zaman"] < _ERISIM_GUNLUK_ARALIK_SN:
            k["bastirilan"] += 1
            return False
        onceki = k["bastirilan"] if k else 0
        onceki_neden = k["neden"] if k else None
        _tekrar_gunluk[anahtar] = {"neden": neden, "zaman": simdi, "bastirilan": 0}
    if onceki and onceki_neden == neden:
        ileti = ileti + " [onceki %d sn icinde ayni nedenle %d kez daha]"
        args = (*args, int(_ERISIM_GUNLUK_ARALIK_SN), onceki)
    elif onceki:
        # ⚠️ E2-1.7 (2-E incelemesi): bastırılan sayı ESKİ nedene aittir — yeni nedenin satırına "aynı nedenle" diye yazılmaz.
        ileti = ileti + " [NEDEN DEGISTI: onceki neden (%s) bastirilmis %d kez daha tekrarlanmisti]"
        args = (*args, onceki_neden, onceki)
    gunlukcu.error(ileti, *args)
    return True


def _erisim_hatasi(p: Path, e: OSError) -> OSError:
    neden = f"{type(e).__name__}: {e}"
    reddedildi = isinstance(e, PermissionError)
    tekrar_kisitli_hata(
        logger,
        "pemf_secrets.json",
        neden,
        "pemf_secrets.json OKUNAMADI (%s) — dosya BOZUK SAYILMADI, yerinde birakildi, YENI ANAHTAR URETILMEDI.",
        neden,
    )
    tur = "erişim reddedildi" if reddedildi else "G/Ç hatası"
    ileti = (
        f"pemf_secrets.json OKUNAMADI — {tur} ({type(e).__name__}). Dosya BOZUK DEĞİL, yerinde bırakıldı; yeni anahtar "
        f"ÜRETİLMEDİ. Yapılacak: uygulamayı bu veri klasörünü kuran Windows hesabıyla açın ya da yöneticiye "
        f"'{p.parent}' klasörünün ve '{p.name}' dosyasının izinlerini düzelttirin (SYSTEM, Administrators ve uygulamayı "
        f"çalıştıran hesap tam erişim)."
    )
    return (PermissionError if reddedildi else OSError)(e.errno, ileti)


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
#: Linux makine kimliği kaynakları (sırayla; ilk DOLU olan kullanılır). D4.12 (B-3.49): `python:slim` Docker imajında ikisi de
#: YOKTU → kritik anahtar fail-closed RuntimeError, backend import'ta ölüyordu. İmaj artık `/etc/machine-id`'yi kalıcı adlı
#: birimdeki `/var/lib/dbus/machine-id`'ye bağlar; `docker/backend-entrypoint.sh` onu ilk açılışta üretir.
MAKINE_KIMLIGI_YOLLARI = ("/etc/machine-id", "/var/lib/dbus/machine-id")


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
        for p in MAKINE_KIMLIGI_YOLLARI:
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
    # TA T5 (çoklu klinik P2): yeni eşleştirme kodu 8 karakter — `path_utils._PAIRING_CODE_LENGTH` ile AYNI (kapı:
    # tests/test_TA_T5_cihaz_kodu_8_karakter.py); kayıtlı 6'lık kod okunmaya devam eder (`pairing_code.txt`).
    return "".join(_secrets.choice(alpha) for _ in range(8))


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


# ───────────────────── BULUT CİHAZ KİMLİĞİ — VERİ KÖKÜNDEN BAĞIMSIZ DEPO ─────────────────────
# ⚠️ DENETİM 2026-08-28 #02 — KÖK NEDEN: KALICILIK ASİMETRİSİ.
#   * `device_id` NIC MAC'inden türetilir (`path_utils.get_unique_device_id` → `uuid.getnode()`),
#     yani veri kökü silinse de YENİDEN AYNI değeri üretir — kalıcıdır.
#   * `device_registry_secret` ise rastgele üretilir ve YALNIZ veri kökündeki `pemf_secrets.json`
#     içinde yaşar — veri kökü yenilenince KAYBOLUR ve yenisi doğar.
# Buluttaki TOFU mührü `(device_id, secret_hash)` çiftine bağlı olduğundan sonuç deterministik:
# veri kökü yenilenince birincil anahtar AYNI kalır, sır DEĞİŞİR → KALICI `secret_mismatch`.
# Ölçülen saha sonucu: cihaz 13 gün boyunca buluta yazamadı; uzaktan bağlanan "cihaz bulunamadı"
# gördü (cihaz açık, internete bağlıydı).
#
# ÇÖZÜM (sahip kararı 2026-08-28): sır veri kökünün DIŞINDA, makine kapsamlı bir dosyada tutulur.
# Böylece veri kökü yenilense de sır device_id ile birlikte sabit kalır → uyuşmazlık HİÇ OLUŞMAZ.
#
# ⚠️ KVKK ÖDÜNLEŞİMİ VE KARŞILIĞI: sır artık hasta-verisi silme kapsamının dışında bir yerde.
# Bu bilinçli; karşılığı `scripts/pemf_footprint.ps1`e `Kvkk = $true` kalemi olarak eklendi →
# sıradan kaldır-kur sırrı KORUR (arıza olmaz), KVKK silmesi sırrı da GÖTÜRÜR (doğru davranış).
#
# ⚠️ DPAPI kapsamı LOCAL_MACHINE (`_dpapi`, flag 0x4): LocalSystem servisi de masaüstü kullanıcısı
# da aynı blob'u çözebilir. Disk imajı/klonlama sırrı taşır — bu, seçilen yolun bilinen bedeli.
_KIMLIK_DOSYASI = "device_identity.json"


def _cihaz_kimlik_deposu() -> Path:
    """Bulut cihaz sırrının VERİ KÖKÜNDEN BAĞIMSIZ kalıcı deposu.

    Windows: `%ProgramData%\\PEMF_System\\device_identity.json` — `PEMF_System\\PEMF_GUI` (veri
    kökü) silinse de ayakta kalır; `PEMF_System` KÖKÜ teardown'da KVKK-dışı sayılır (ölçüldü:
    `pemf_footprint.ps1:35` kök `Kvkk=$false`, yalnız alt dizinler işaretli).
    Linux/mac: `/var/lib/pemf` yazılabilirse orası, değilse `~/.pemf`.
    Test/özel kurulum: `PEMF_DEVICE_IDENTITY_DIR` ile yönlendirilebilir.
    """
    override = os.getenv("PEMF_DEVICE_IDENTITY_DIR", "").strip()
    if override:
        d = Path(override)
    elif os.name == "nt":
        d = Path(os.getenv("PROGRAMDATA") or r"C:\ProgramData") / "PEMF_System"
    else:  # pragma: no cover — PLATFORM: Linux / macOS makine deposu dalı (/var/lib/pemf → ~/.pemf)
        d = Path("/var/lib/pemf")
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / ".yazma_denemesi").touch()
            (d / ".yazma_denemesi").unlink()
        except Exception:
            d = Path.home() / ".pemf"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _kimlik_deposu_oku() -> str:
    """Makine deposundaki bulut sırrını döndür (yoksa boş). ASLA istisna fırlatmaz."""
    try:
        p = _cihaz_kimlik_deposu() / _KIMLIK_DOSYASI
        if not p.is_file():
            return ""
        ham = (json.loads(p.read_text(encoding="utf-8")) or {}).get("device_registry_secret", "")
        if not ham:
            return ""
        return _dec(str(ham)).strip()
    except Exception as e:
        # Çözülemiyorsa (başka makine / bozuk dosya) SESSİZ düşme YOK: kararın izi kalsın.
        logger.warning("Cihaz kimlik deposu okunamadı (%s) — veri kökündeki sır kullanılacak.", e)
        return ""


def _kimlik_deposu_yaz(deger: str) -> None:
    """Sırrı makine deposuna yaz (DPAPI/makine-anahtarı ile). Başarısızlık AKIŞI KESMEZ."""
    try:
        p = _cihaz_kimlik_deposu() / _KIMLIK_DOSYASI
        gecici = p.with_suffix(".tmp")
        gecici.write_text(
            json.dumps({"device_registry_secret": _enc(deger, critical=True)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(gecici, p)
        # ⚠️ `_ensure_dir_hardened(p.parent)` BİLEREK ÇAĞRILMIYOR — iki sebeple:
        #   (1) O fonksiyon SÜREÇ-GENELİ `_dir_hardened` bayrağını kullanır; burada başarıyla
        #       koşarsa ASIL SIR DİZİNİNİN (veri kökü) sertleştirmesi bir daha denenmez.
        #   (2) Kilitlenecek dizin `ProgramData\PEMF_System` KÖKÜ olurdu; orada `logs`,
        #       `mosquitto`, `hotspot.json` gibi başka bileşenlerin yazdığı yollar var
        #       (`pemf_footprint.ps1:43-45`) — ACL kısıtı onları bozabilir.
        # İçerik zaten DPAPI/LOCAL_MACHINE ile şifreli: dosyayı okuyan başka bir makine çözemez.
        logger.info("Bulut cihaz sırrı makine deposuna yazıldı (veri kökünden bağımsız): %s", p)
    except Exception as e:
        logger.warning("Cihaz kimlik deposuna yazılamadı (%s) — sır yalnız veri kökünde kalır.", e)


def _bulut_sirri_oku() -> str:
    """`device_registry_secret` için eski-kaynak okuyucusu: MAKİNE DEPOSU → env.

    `get_secret` bu değeri bulursa veri kökündeki dosyaya migrate eder; yani veri kökü
    yenilendiğinde sır AYNI kalır ve TOFU mührü bozulmaz.
    ⚠️ Y204 (S-D5.7): depo ÖNCE — kaldır-kur sonrası (veri kökü boş, depo dolu) env kurulu bulut kimliğini EZMEZ; env yalnız depo
    da boşken (hiç kurulmamış cihaz, Y14 ilk taşıma) kaynak olur."""
    return (_kimlik_deposu_oku() or os.getenv("PEMF_DEVICE_REGISTRY_SECRET", "").strip()).strip()


def _bulut_sirri_uret() -> str:
    """Yeni bulut sırrı üret VE makine deposuna yaz.

    ⚠️ Yazma şart: yalnız veri köküne yazılırsa bir sonraki kök yenilemesinde yine kaybolur ve
    bulgu geri gelir (bu fonksiyonun tek varlık sebebi budur)."""
    yeni = _gen_urlsafe32()
    _kimlik_deposu_yaz(yeni)
    return yeni


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
            from utils.path_utils import kaynak_kokunu_bul

            aday = kaynak_kokunu_bul(__file__) / "data" / "cloud_mqtt_provision.json"
        if not aday.exists():
            return ""
        return str(_json.loads(aday.read_text(encoding="utf-8")).get(key) or "").strip()
    except Exception:
        return ""


# ⚠️ D3.38 (B-3.103) · A-14 (sahip, önerilen): bu anahtarların kaynağı PAKETİN / ORTAMIN kendisidir (bulut-MQTT provizyonu, gömülü
# Supabase adresi / yayınlanabilir anahtarı). Eskiden değer yalnız dosyada YOKKEN taşınıyordu → yeni sürüm (rotasyon dahil) sahaya
# hiç ulaşmıyor, jeton / hak denetimi ve E-stop bulut aynası eski değerde kalıyordu. Artık her okumada kaynak (env → paket) DOLUYSA
# o döner ve dosyadakinden farklıysa dosya güncellenir; kaynak BOŞSA (provizyon yok) dosyadaki değer korunur.
_GOMULU_USTUN = frozenset(
    {"mqtt_cloud_host", "mqtt_cloud_port", "mqtt_cloud_user", "mqtt_cloud_pass", "supabase_url", "supabase_anon_key"}
)

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
    # ⚠️ DENETİM 2026-08-28 #02: üreteç ve eski-kaynak okuyucusu MAKİNE DEPOSUNA bağlandı
    # (bkz. `_cihaz_kimlik_deposu` üstündeki uzun not). Veri kökü yenilendiğinde sır artık
    # kaybolmuyor → TOFU mührü bozulmuyor → kalıcı `secret_mismatch` OLUŞMUYOR.
    "device_registry_secret": (
        "auto",
        True,
        _bulut_sirri_uret,
        _bulut_sirri_oku,
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
    global _cache
    if _cache is not None:
        return _cache
    # D2.80 (B-3.52): sertleştirme önbellek denetiminden SONRA — önbellek doluyken hiç denenmez (bkz. _ensure_dir_hardened).
    _ensure_dir_hardened(_data_dir())
    p = secrets_path()
    try:
        _var = p.exists()  # dizin listelenemiyorsa (ikinci hesap) `exists()` de WinError 5 yükseltir
    except OSError as e:
        raise _erisim_hatasi(p, e) from e
    if _var:
        try:
            _ham = p.read_bytes()
        except OSError as e:
            # D2.80: izin / G-Ç hatası — dosya BOZUK DEĞİL: yeniden adlandırma YOK, önbellek dolmaz (bkz. _erisim_hatasi).
            raise _erisim_hatasi(p, e) from e
        try:
            # ⚠️ E2-1.5 (2-E incelemesi): emanet geri yükleme yönergesi bu dosyayı ELLE düzenletir; PowerShell 5.1 / eski Notepad
            # BOM'lu UTF-8 ya da UTF-16 yazar. GEÇERLİ dosya "bozuk" sayılıp karantinaya gidiyordu. BOM'a göre çöz (yazım yine UTF-8).
            _metin = _ham.decode("utf-16") if _ham[:2] in (b"\xff\xfe", b"\xfe\xff") else _ham.decode("utf-8-sig")
            doc = json.loads(_metin)
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
            _saklandi = None
            try:
                _ts = time.strftime("%Y%m%d_%H%M%S")
                _bad = p.with_name(p.name + f".corrupt.{_ts}")
                p.replace(_bad)
                _saklandi = _bad.name
                logger.error("pemf_secrets.json BOZUK (%s) — %s olarak saklandi, YENI URETILMEDI.", e, _bad.name)
            except Exception:
                logger.error("pemf_secrets.json BOZUK (%s) ve yeniden adlandirilamadi — YENI URETILMEDI.", e)
            # D2.80: ileti GERÇEĞİ söyler — kenara alma tutmadıysa "kopya saklandı" DENMEZ (dosya yerinde durur).
            raise RuntimeError(
                "pemf_secrets.json okunamadi/bozuk. Mevcut sifreli hasta verisini korumak icin "
                "yeni anahtar URETILMEDI ve dosya EZILMEDI. Yedekten geri yukleyin "
                + (
                    f"(bozuk kopya {_saklandi} olarak saklandi)."
                    if _saklandi
                    else "(bozuk dosya YERINDE birakildi — kenara alinamadi)."
                )
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


def _diske_yaz_sonra_onbellege(doc: dict, section: str, key: str, stored: str) -> None:
    """⚠️ D2.45 (B-3.5 · Karar 6): değer ÖNCE diske, `_save` BAŞARILIYSA önbelleğe.

    Eskiden değer önbellek dokümanına (`_load()`un döndürdüğü `_cache`in KENDİSİ) `_save`'den ÖNCE yazılıyordu: `_save`
    bir kez düşerse (AV / ACL / disk — `os.replace` PermissionError'ı sahada görüldü) üretilen anahtar yalnız BELLEKTE
    kalıyor, aynı süreçteki sonraki çağrılar onu döndürüyordu → hasta DB'si diske hiç yazılmamış bir anahtarla
    şifreleniyor, yeniden başlatmada anahtar YOK → kalıcı 0 hasta (ölçüldü). Artık KOPYA doküman kaydedilir; `_save`
    düşerse önbellek DEĞİŞMEZ ve hata çağırana yükselir (anahtar yolu fail-closed).
    Kapı: tests/test_anahtar_yolu_FAIL_CLOSED_Karar6_D245.py."""
    global _cache
    yeni = copy.deepcopy(doc)
    yeni.setdefault(section, {})[key] = stored
    _save(yeni)
    _cache = yeni


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
        # ⚠️ D1.16 (B-3.104): dosya ELLE doldurulabiliyor — tırnaksız `"mqtt_cloud_port": 8883` JSON
        # SAYIDIR; eskiden `.strip()` AttributeError atıyor, E-stop bulut aynası her seferinde düşüyordu.
        # `or ""` önce: eksik/boş değer ('None'/'0' METNİ değil) eskisi gibi boş sayılır (`_bundled_cloud` deseni).
        raw = str(doc.get(section, {}).get(key) or "").strip()
        if key in _GOMULU_USTUN and legacy:
            try:
                _kaynak = (legacy() or "").strip()
            except Exception:
                _kaynak = ""
            if _kaynak:
                try:
                    _dosyadaki = _dec(raw) if raw else ""
                except Exception:
                    _dosyadaki = None  # çözülemeyen eski değer — kaynak otoritedir
                if _dosyadaki != _kaynak:
                    _diske_yaz_sonra_onbellege(doc, section, key, _enc(_kaynak, critical=True) if dpapi else _kaynak)
                    logger.info("A-14: paket / ortam değeri dosyadakinin yerine yazıldı: %s", key)
                return _kaynak
        if raw:
            try:
                _cozulen = _dec(raw)
                # ⚠️ D3.09 (B-3.43): emanetten / elle geri yüklenen KRİTİK anahtar dosyaya DÜZ yazılır (VAULT-ANAHTAR-EMANETI.md
                # Adım 4: "DPAPI: öneki OLMADAN — backend ilk açılışta kendi sarar"); ama `_dec` öneksiz değeri sarmadan döndürüyordu
                # → hasta DB anahtarı süresiz düz-metin kalıyordu. İlk okumada makineye bağlı sarılır (ÖNCE disk, sonra önbellek).
                # Sarma düşerse (DPAPI yok / disk kilitli) eskisi gibi düz değerle sürülür — açılış KIRILMAZ, uyarı günlüğe.
                if dpapi and _cozulen and not raw.startswith((_DPAPI_PREFIX, _MKEY_PREFIX)):
                    try:
                        _diske_yaz_sonra_onbellege(doc, section, key, _enc(_cozulen, critical=True))
                        logger.info("Kritik sır düz-metin bulundu, makineye bağlı yeniden sarıldı: %s", key)
                    except Exception:
                        logger.warning(
                            "Kritik sır '%s' düz-metin — yeniden sarılamadı (düz değerle sürülüyor)", key, exc_info=True
                        )
                # ⚠️ DENETİM 2026-08-28 #02 — GERİYE DÖNÜK KURTARMA. Kalıcı çözüm yalnız YENİ
                # kurulumları korusaydı sahadaki cihazlar açıkta kalırdı: onlarda sır zaten veri
                # kökünde DOLU olduğu için aşağıdaki migrate/üret yoluna hiç girilmez ve makine
                # deposuna hiç yazılmazdı → ilk kaldır-kur döngüsünde sır yine kaybolur, TOFU
                # mührü yine bozulurdu. Bu satır mevcut sırrı bir kereliğine depoya taşır.
                if key == "device_registry_secret" and _cozulen:
                    _makinedeki = _kimlik_deposu_oku()
                    if not _makinedeki:
                        _kimlik_deposu_yaz(_cozulen)
                    elif _makinedeki != _cozulen:
                        # ⚠️ AYRIŞMA — MAKİNE DEPOSU OTORİTEDİR (saha bulgusu 2026-08-29).
                        #
                        # ÖLÇÜLEN ARIZA: bu makinede iki kaynak FARKLI sır taşıyordu ve `raw`
                        # dolu olduğu için VERİ KÖKÜNDEKİ kazanıyordu. Veri kökü kaldırmada
                        # SİLİNİYOR, makine deposu KALIYOR → aynı cihaz, kaldır-kur'dan önce ve
                        # sonra buluta BAŞKA BAŞKA sır gönderiyor. Bulut ilk sırla TOFU'ya
                        # mühürlendiği için ikinci gönderim kalıcı `secret_mismatch` alıyor ve
                        # uzaktan erişim bir daha AÇILMIYOR (269 kez ölçüldü, 26→29 Ağustos).
                        #
                        # #02'nin taşıması yalnız "depo BOŞSA" çalışıyordu; depo başka bir yolla
                        # (üretimle) dolduysa ayrışma kalıcılaşıyordu. Kalıcı olan kaynağı
                        # otorite yapmak, kaldır-kur'un sırrı değiştirmesini kökten bitirir.
                        logger.warning(
                            "device_registry_secret AYRIŞMASI: veri kökü ile makine deposu farklı — "
                            "makine deposu kullanılıyor (kaldır-kur'da korunan kaynak odur)."
                        )
                        return _makinedeki
                return _cozulen
            except Exception as e:
                # KRİTİK VERİ-KORUMA (brick koruması): sır DEPOLANMIŞ ama çözülemiyor (ör. DPAPI
                # makine/kullanıcı-profili değişti, master-key döndü). Burada YENİ üretip dosyayı EZERSEK
                # mevcut ciphertext'i (ör. patients.db SQLCipher anahtarı) KALICI kaybederiz → tüm şifreli
                # hasta verisi geri-DÖNÜLEMEZ brick olur. Bu yüzden fail-closed: ÜRETME/MİGRATE ETME/EZME,
                # HATA yükselt. Ciphertext dosyada korunur (DPAPI düzelince veya doğru makine/yedekle çözülür).
                logger.error(
                    "Sır çözülemedi (%s): %s — mevcut şifreli değer KORUNUYOR, üretilmiyor (brick koruması).", key, e
                )
                # ⚠️ 4B-1.6: Linux/Docker'da "makine" = kimlik dosyası (D4.12: compose `pemf_kimlik` birimi). `pemf_secrets.json`
                # veri biriminde ve AYNI kimlikle sarılı — onu geri yüklemek ÇÖZMEZ; doğru yol kimlik birimini geri yüklemektir.
                # (macOS IOPlatformUUID kullanır — machine-id ipucu orada yanlış olurdu.)
                import platform as _pf

                _linux_ipucu = (
                    ""
                    if _is_windows() or _pf.system() == "Darwin"
                    else (
                        f" Linux/Docker: makine kimliği {', '.join(MAKINE_KIMLIGI_YOLLARI)} — kimlik birimini (compose: "
                        "pemf_kimlik) veri birimiyle BİRLİKTE geri yükleyin."
                    )
                )
                raise RuntimeError(
                    f"Depolanmış sır '{key}' çözülemedi (DPAPI/makine/profil değişmiş olabilir). "
                    f"Var olan şifreli veriyi korumak için yeni anahtar ÜRETİLMEDİ ve dosya EZİLMEDİ. "
                    f"Doğru makineyi kullanın veya pemf_secrets.json yedeğinden geri yükleyin.{_linux_ipucu}"
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
        # dosyaya yaz (kritikse DPAPI) — ÖNCE disk, sonra önbellek (D2.45)
        _diske_yaz_sonra_onbellege(doc, section, key, _enc(val, critical=True) if dpapi else val)
        return val


def set_secret(key: str, value: str) -> None:
    """Operatör/sistem bir sırrı yazar (kritikse DPAPI ile saklanır)."""
    if key not in _REGISTRY:
        raise KeyError("Bilinmeyen sır anahtarı: %s" % key)
    section, dpapi, *_ = _REGISTRY[key]
    with _lock:
        doc = _load()
        _diske_yaz_sonra_onbellege(doc, section, key, _enc(value, critical=True) if (dpapi and value) else value)


def set_secrets(degerler: dict) -> None:
    """Birden çok sırrı TEK disk yazımında kaydeder — ya HEPSİ diske yazılır ya HİÇBİRİ (önbellek de değişmez).

    ⚠️ 2-A inceleme A2-1.6 (D2.45 · Karar 6): felaket kurtarma `--yaz` zarftaki iki anahtarı TEK TEK `set_secret` ile
    yazıyordu; ikinci yazım düşünce (AV / kilit) diskte yalnız `sqlcipher_key` kalıyor, sonraki açılış eksik
    `patient_fernet_key`i YENİDEN ÜRETİYORDU → kurtarılan hasta alanları çözülemiyordu (ölçüldü).
    Kapı: tests/test_alan_anahtari_ICE_AKTARMADA_alinmaz_A21.py::test_KRITIK_A16_…"""
    global _cache
    for key in degerler:
        if key not in _REGISTRY:
            raise KeyError("Bilinmeyen sır anahtarı: %s" % key)
    with _lock:
        yeni = copy.deepcopy(_load())
        for key, value in degerler.items():
            section, dpapi, *_ = _REGISTRY[key]
            yeni.setdefault(section, {})[key] = _enc(value, critical=True) if (dpapi and value) else value
        _save(yeni)
        _cache = yeni
