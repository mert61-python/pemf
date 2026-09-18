# Author: mertaygn, cglrgrkn
"""Windows NTFS ACL kilidi — sır/anahtar dosyalarını yalnız SYSTEM + Administrators okusun.

SORUN: `os.chmod(path, 0o600)` Windows'ta NTFS ACL kurmaz (POSIX modu neredeyse no-op'tur).
Bu yüzden düz-metin anahtar/sır dosyaları (`.sqlcipher_key`, `pemf_secrets.json`, `.pemf_key_v2`,
`api_token.txt`) üst klasörün ACL'sini MİRAS alır ve genellikle yerel `Users` grubu tarafından
OKUNABİLİR kalır → at-rest şifreleme anahtarı makinedeki her kullanıcıya açık (audit B-1.2).

ÇÖZÜM: `icacls` ile inheritance'ı kaldır ve yalnız SYSTEM + Administrators'a tam erişim ver.
Servis LocalSystem (SYSTEM) olarak koştuğundan anahtarı okumaya devam eder; operatör (Administrator)
yedek/kurtarma için okuyabilir; normal kullanıcı/kötücül-process OKUYAMAZ.

Yerelleştirme: grup ADLARI Türkçe Windows'ta değişir ("Administrators" → "Yöneticiler"), bu yüzden
İSİM değil **well-known SID** kullanılır:  S-1-5-18 = LocalSystem,  S-1-5-32-544 = Administrators.

Best-effort: uygulanamazsa (izin/eski Windows) uyarı loglanır, çağıran akış DURMAZ.
"""

import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

# icacls SID sözdizimi: "*S-1-5-18". F = Full control.
_SYSTEM_SID = "*S-1-5-18"  # NT AUTHORITY\SYSTEM (servis LocalSystem)
_ADMINS_SID = "*S-1-5-32-544"  # BUILTIN\Administrators (operatör yedek/kurtarma)
# DENETİM 2026-08-04: `/inheritance:r` YALNIZ MİRAS ALINAN ACE'leri kaldırır; hedefte AÇIK
# (explicit) bir Users / Authenticated-Users ACE'i varsa OLDUĞU GİBİ KALIR ve `/grant:r` de
# yalnız adı geçen SID'leri değiştirir → dosya/dizin 'kilitlendi' sanılırken Users ERİŞMEYE
# DEVAM EDER. (Davranış testiyle yakalandı.) Bu yüzden ikisi AÇIKÇA kaldırılır.
_USERS_SID = "*S-1-5-32-545"  # BUILTIN\Users
_AUTHUSERS_SID = "*S-1-5-11"  # NT AUTHORITY\Authenticated Users


def lock_down_dir(path, keep_current_user: bool = True) -> bool:
    """`path` DİZİNİNİ kilitle; içinde OLUŞACAK dosyalar kısıtlı ACL'i MİRAS alsın.

    DENETİM 2026-08-04 (P2): sır dizini (`<PEMF_DATA_DIR>\\PEMF_GUI`, üretimde
    `C:\\ProgramData\\PEMF_System\\PEMF_GUI`) sertleştirilmiyordu. ProgramData mirası
    `BUILTIN\\Users:(OI)(CI)(RX)` + `(CI)(WD,AD)` verir → yerel kullanıcılar oraya
    DOSYA OLUŞTURABİLİR ve yeni dosyaları OKUYABİLİR. İki somut sonuç:

    1) `secrets_manager._save()` önce `pemf_secrets.json.<pid>.tmp` yazar ve ACL'i BİLEREK
       yalnız `os.replace`'ten SONRA hedefe uygular (sıra ZORUNLU: .tmp önce kilitlenirse
       yönetici-olmayan süreç kendi dosyası üzerindeki DELETE hakkını kaybedip replace'i
       düşürüyordu — sahada yaşandı). Dolayısıyla .tmp, TÜM düz-metin sırlarla birlikte
       miras-ACL'iyle kısa süre Users-OKUNUR kalıyordu. DİZİN kilitliyse .tmp doğduğu anda
       kısıtlıdır → pencere kapanır ve replace de bozulmaz.
    2) `_legacy_appdata_token()` / sqlcipher legacy okuyucusu `<data_dir>/api_token.txt` ve
       `.sqlcipher_key`'i KOŞULSUZ migrate eder. Dizin Users-yazılabilir olduğu için bu dosyalar
       saldırgan tarafından ÖNCEDEN YERLEŞTİRİLEBİLİRDİ (bilinen anahtar enjeksiyonu).

    `keep_current_user=True` (varsayılan): yönetici-olmayan süreç kendi dizinini kullanmaya
    devam etsin. Yerel `Users` grubu her hâlükârda ERİŞEMEZ; korunan budur.
    Best-effort: uygulanamazsa uyarı loglanır, çağıran akış DURMAZ.
    """
    p = str(path)
    if not os.path.isdir(p):
        return False
    if sys.platform != "win32":
        try:
            os.chmod(p, 0o700)
            return True
        except Exception:
            return False
    try:
        # (OI)(CI) = içindeki dosya/dizinlere MİRAS geçsin — asıl amaç budur.
        _args = [
            "icacls",
            p,
            "/inheritance:r",
            # Miras DEGIL, ACIK ACE olarak duran Users/Authenticated-Users grant'larini da kaldir.
            "/remove:g",
            _USERS_SID,
            "/remove:g",
            _AUTHUSERS_SID,
            "/grant:r",
            f"{_SYSTEM_SID}:(OI)(CI)F",
            "/grant:r",
            f"{_ADMINS_SID}:(OI)(CI)F",
        ]
        if keep_current_user:
            import getpass

            _args += ["/grant:r", f"{getpass.getuser()}:(OI)(CI)F"]
        subprocess.run(
            _args,
            check=True,
            capture_output=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception as e:
        logger.warning("Dizin ACL kilidi uygulanamadı (%s): %s", p, e)
        return False


def lock_down_file(path, keep_current_user: bool = False) -> bool:
    """`path` dosyasını yalnız SYSTEM + Administrators erişebilecek şekilde kilitle.

    keep_current_user=True → SYSTEM + Administrators'a EK OLARAK süreci çalıştıran hesaba da
    tam erişim verilir. Bu, SÜREKLİ açılıp yazılan dosyalar (ör. auth_users.db) için ZORUNLUDUR:
    aksi halde yönetici OLMAYAN bir süreç (Tauri launcher kullanıcı-başına kurulum) kendi
    dosyasından dışarı atılır ve o özellik tamamen kırılır (DENETİM P3 — sahada yaşandı).
    Yerel `Users` grubu her iki modda da ERİŞEMEZ; korunan şey budur.

    True = ACL uygulandı. Dosya yoksa / hata olursa False (best-effort — çağıran DURMAZ).
    Windows dışında POSIX 0o600'e düşer.
    """
    p = str(path)
    if not os.path.exists(p):
        return False
    if sys.platform != "win32":
        try:
            os.chmod(p, 0o600)
            return True
        except Exception:
            return False
    try:
        _args = [
            "icacls",
            p,
            "/inheritance:r",  # miras alınan (Users dahil) tüm ACE'leri kaldır
            # ...ama ACIK ACE'ler mirasla gitmez → onlari da adiyla kaldir (bkz. SID notu).
            "/remove:g",
            _USERS_SID,
            "/remove:g",
            _AUTHUSERS_SID,
            "/grant:r",
            f"{_SYSTEM_SID}:F",
            "/grant:r",
            f"{_ADMINS_SID}:F",
        ]
        if keep_current_user:
            import getpass

            _args += ["/grant:r", f"{getpass.getuser()}:F"]
        subprocess.run(
            _args,
            check=True,
            capture_output=True,
            timeout=10,  # E-3: wedge'lenen handle başlangıçta bloklamasın (tek timeout'suz subprocess'ti)
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception as e:
        logger.warning("Dosya ACL kilidi uygulanamadı (%s): %s", p, e)
        return False
