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
# ⚠️ D2.75 (B-11.5): kurtarma komutunun TEK kaynağı. Sahada Python YOK; tek çalıştırılabilir launcher'ın kullanıcı-başına kurduğu
# `PEMF_Backend.exe`dir (`%LOCALAPPDATA%\PEMF Vet Client\runtime\PEMF_Backend\`); `--kurtarma` alt komutu `tools.kurtarma`yı koşturur
# (`backend_service._kurtarma_mi`; D2.35: donmuş EXE'de depo dışında açılır). Eskiden KURTARMA-KODU.txt, yedeklerin yanındaki
# OKU-KURTARMA.txt, aracın kendi uyarıları ve RUNBOOK `python tools/kurtarma.py` diyordu → anakartı ölen klinik "Python bulunamadı"
# alıp yedeklerin açılamadığını sanırdı. Biçim Komut İstemi (cmd.exe) içindir (`%LOCALAPPDATA%` orada açılır).
# Kapı: tests/test_kurtarma_yonergesi_SAHADA_CALISAN_komut_D275.py
KURTARMA_EXE = r'"%LOCALAPPDATA%\PEMF Vet Client\runtime\PEMF_Backend\PEMF_Backend.exe"'


def kurtarma_komutu(*argumanlar: str) -> str:
    """Sahada çalışan kurtarma komutu (cmd.exe): `"…\\PEMF_Backend.exe" --kurtarma <argümanlar>`."""
    return " ".join((KURTARMA_EXE, "--kurtarma", *argumanlar))


# Zarfın gereksiz yere her gün yeniden yazılmaması için yerel parmak izi.
_FP_FILE_NAME = ".recovery_fp"
# D2.60 (B-3.94): mühür `<önek><parmak izi>` YALNIZ zarf VE kod dosyası bu kod için yazıldıktan sonra vurulur. Öneksiz mühür eski
# sürümündür — o sürüm mührü kod dosyasından ÖNCE vuruyordu, yani dosya hiç yazılamamış olabilir (bkz. refresh_recovery_material).
_FP_MUHUR_ONEKI = "kod-yazildi:"
# E2-1.10: operatör "Kaydettim" dediğinde (`/api/system/recovery-ack`) veri kökünde bırakılan işaret — kod dosyası yoksa "operatör kodu
# dışarı alıp sildi" yalnız bu işaret varken varsayılır (onay kaydının asıl yeri tedavi DB'si; yedek turu DB'ye bağlanmaz).
ONAY_ISARETI_ADI = ".recovery_ack"


def kod_onay_izi(code: str) -> str:
    """Onaylanan KODUN 16 hex parmak izi (kod 150 bit → kaba kuvvetle açılamaz; kod saklanmaz). Onay ucu (`system_router`) ve yedek turu
    AYNI izi kullanır: işaret yalnız onaylanan koda geçerlidir — kod değişince eski onayın işareti yeni kodun onaysız silinmesini örtmez
    (2-E incelemesi E2-1.10)."""
    return hashlib.sha256(("kod:" + format_code(code)).encode("ascii")).hexdigest()[:16]


def _onay_isareti_bu_kod_icin_mi(app_data_dir: Path, code: str) -> bool:
    try:
        return (Path(app_data_dir) / ONAY_ISARETI_ADI).read_text(encoding="utf-8").strip() == kod_onay_izi(code)
    except Exception:
        return False


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


def kod_dosyasi_metni(code: str) -> str:
    """`KURTARMA-KODU.txt`in BEKLENEN içeriği (tek kaynak) — yazım ve "dosya güncel mi?" denetimi aynı metni kullanır."""
    return (
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
        "KURTARMA (yeni makinede, PEMF kurulduktan sonra, Komut Istemi / cmd penceresinde)\n"
        "  " + kurtarma_komutu("--zarf", "<yedek-dizini>\\" + ENVELOPE_NAME, "--kod", "<kod>", "--yaz") + "\n"
        "=============================================================\n"
    )


def kod_dosyasi_guncel_mi(app_data_dir: Path, code: str) -> bool:
    """`KURTARMA-KODU.txt` VAR ve tam olarak `code` için beklenen metni mi taşıyor? (okunamazsa False)."""
    try:
        return (Path(app_data_dir) / CODE_FILE_NAME).read_text(encoding="utf-8") == kod_dosyasi_metni(code)
    except Exception:
        return False


def write_code_file(app_data_dir: Path, code: str) -> Path | None:
    """Kurtarma kodunu yerel diske yaz (ACL kilitli) — operatör bir yerden okumalı.

    Bu dosya yedek dizinine KOPYALANMAZ; amacı operatörün kodu makine dışına
    taşıyabilmesi. Taşındıktan sonra silinebilir (zarf yine geçerli kalır).

    D2.13: ATOMİK (tmp + fsync + os.replace) — kod değişince dosya yeniden yazılır; yarım kalan bir yazım eski kodu
    bozup yeni kodu da yarım bırakmasın.
    """
    p = Path(app_data_dir) / CODE_FILE_NAME
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(kod_dosyasi_metni(code))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
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

    Returns: zarf yazıldıysa/yerindeyse True; kurtarılacak anahtar (sqlcipher_key / patient_fernet_key) yoksa ya da zarf hiçbir
    hedefe yazılamadıysa False.
    """
    app_data_dir = Path(app_data_dir)
    dests = [Path(d) for d in dest_dirs if d]
    if not dests:
        return False

    keys = _collect_keys()
    # ⚠️ D2.60 (B-3.64): eskiden `sqlcipher_key` yoksa ("at-rest kapalı") zarf HİÇ yazılmıyordu; oysa hasta alanları (ad, sahip, …)
    # `patient_fernet_key` ile şifreli — makine ölünce başka makinede okunamaz. Artık kurtarılacak HERHANGİ bir anahtar varsa zarf
    # yazılır; hiç yoksa (taze, şifresiz kurulum) atlanır. Karar 31 korunur: `_collect_keys` generate=False → sqlcipher_key
    # burada ÜRETİLMEZ (şifrelemeyi kazara açmaz). Kapı: tests/test_kurtarma_zarfi_FERNET_ve_kod_dosyasi_YENIDEN_denenir_D260.py
    if not keys:
        logger.debug("kurtarma zarfi atlandi: kurtarilacak anahtar yok (sqlcipher_key / patient_fernet_key)")
        return False

    code = get_or_create_code()
    fp = _fingerprint(code, keys)
    fp_file = app_data_dir / _FP_FILE_NAME
    try:
        muhur = fp_file.read_text(encoding="utf-8").strip()
    except Exception:
        muhur = ""
    unchanged = muhur in (fp, _FP_MUHUR_ONEKI + fp)
    # D2.60 (B-3.94): önekli mühür = bu kod + anahtarlar için kod dosyası YAZILDI. Öneksiz (eski sürüm) mühür dosya yazılamadan da
    # vurulmuş olabilir → zarf yeniden yazılmaz ama kod dosyasına bir kez daha bakılır (takılı kalmış kurulum kendiliğinden düzelir).
    kod_muhurlu = muhur == _FP_MUHUR_ONEKI + fp

    # ══════════════════════════════════════════════════════════════════════════════════════════
    # SAGLAMLIK "VAR MI?" ILE OLCULEMEZ (DENETIM 2026-08-17).
    #
    # Burada kapi `not (d / ENVELOPE_NAME).exists()` idi. `_fingerprint` yalniz `code` + `keys`'in
    # fonksiyonu (yedek icerigi ETKILEMEZ) ve anahtarlar sabit oldugu icin `unchanged` sonsuza dek
    # True. Dolayisiyla zarf bir kez BOZULURSA (yazim sirasinda guc kesintisi / kisa dosya) dosya
    # VAR oldugu icin `missing` bos kalir ve zarf BIR DAHA ASLA yeniden yazilmaz. Olculdu: bozuk
    # zarf 5 tur boyunca onarilmadi ve fonksiyon her turda True dondu.
    #
    # Sonuc: anakart/disk arizasindan sonra `open_envelope` "Zarf okunamadi (bozuk dosya?)" der ve
    # sifreli yedeklerin TEK off-machine anahtar escrow'u okunamaz (RUNBOOK: pemf_secrets.json
    # DPAPI ile makineye bagli, support_bundle zarfi bilerek disliyor). Asil sivri uc kaybin
    # kendisi degil SESSIZLIGI: `_copy_offsite` kararini yalniz `.exists()`'ten verip operatore
    # "KURTARMA KODU ile baska makinede geri yuklenebilir" diye YANLIS GUVENCE logluyordu.
    #
    # "Degismediyse yeniden yazma" davranisi KASITLI ve testle kilitli (test_backup_recovery:
    # "Operatorun dogruladigi zarf her gun degisip suphe uyandirmasin") → KORUNUR. Degisen tek sey:
    # "var mi?" yerine "GERCEKTEN ACILIYOR MU?" sorulmasi.
    # Kilit: tests/test_kurtarma_zarfi_saglamlik.py
    # ══════════════════════════════════════════════════════════════════════════════════════════
    def _zarf_saglam_mi(yol) -> bool:
        try:
            return bool(open_envelope(code, yol.read_bytes()))
        except Exception:
            return False

    missing = [d for d in dests if not _zarf_saglam_mi(d / ENVELOPE_NAME)]
    # ⚠️ D2.60 (B-3.94): erken dönüş yalnız kod dosyası bu kod için YAZILMIŞSA (önekli mühür). Eskiden mühür kod dosyasından ÖNCE
    # vuruluyordu; dosya bir kez yazılamayınca (disk dolu / AV / izin) sonraki her tur "değişmedi + zarf sağlam" deyip burada dönüyor,
    # operatör kodu HİÇ öğrenmiyordu (uyarı bandı da çıkmıyordu: kod dosyası yok). Önekli mühürle dosya şimdi yoksa operatör kodu
    # dışarı alıp silmiştir (dosyanın kendi metni "silebilirsiniz" der) → geri YAZILMAZ.
    # ⚠️ E2-1.10 (2-E incelemesi, S-E.1 kalan riski): "dışarı alıp sildi" yalnız operatör ONAY verdiyse varsayılır (onay ucu
    # `ONAY_ISARETI_ADI` bırakır). Onaysız yok olan dosya (kodu almadan silme / AV) bir kez daha yazılır → uyarı bandı geri gelir.
    if (
        unchanged
        and not missing
        and kod_muhurlu
        and ((app_data_dir / CODE_FILE_NAME).exists() or _onay_isareti_bu_kod_icin_mi(app_data_dir, code))
    ):
        return True
    if missing:
        logger.warning(
            "kurtarma zarfi eksik/BOZUK (%s) — yeniden yaziliyor.",
            ", ".join(str(d) for d in missing),
        )

    written = 0
    zarf_gerekli = bool(missing) or not unchanged
    blob = build_envelope(code, keys) if zarf_gerekli else b""
    for d in dests if zarf_gerekli else ():
        try:
            d.mkdir(parents=True, exist_ok=True)
            # ATOMIK YAZIM: tmp + fsync + os.replace. `write_bytes` yarim dosya birakabilir ve
            # yukaridaki kapi (eskiden `.exists()`) onu "saglam" sayardi. Ayni desen ve gerekcesi:
            # utils/secrets_manager._save ("yarim kalan bir sir dosyasi TUM kurulumu acilamaz kilar").
            # Surece-ozel tmp adi: yarida kalan bir tmp sonraki yazimlari kalici engellemesin.
            _tmp = d / f"{ENVELOPE_NAME}.{os.getpid()}.tmp"
            try:
                with open(_tmp, "wb") as _f:
                    _f.write(blob)
                    _f.flush()
                    os.fsync(_f.fileno())
                os.replace(_tmp, d / ENVELOPE_NAME)
            finally:
                try:
                    if _tmp.exists():
                        _tmp.unlink()
                except Exception:
                    pass
            written += 1
        except Exception:
            logger.warning("kurtarma zarfi yazilamadi: %s", d, exc_info=True)
    if zarf_gerekli and not written:
        return False

    # ⚠️ D2.13 (B-3.39): kod dosyası yalnız YOKSA yazılıyordu. Kod yeniden üretilince (sır dosyası sıfırlanıp `get_or_create_code`
    # yenisini üretince) zarf YENİ kodla yazılıyor, `KURTARMA-KODU.txt` (ve onu okuyan `/api/system/recovery-code`) ESKİ kodu
    # gösteriyordu → operatör zarfı AÇMAYAN kodu kasaya koyardı. Artık dosya zarfın koduyla güncel DEĞİLSE (yok / farklı kod /
    # bozuk) yeniden yazılır. Kapı: tests/test_kurtarma_kodu_DOSYASI_yeni_kodla_GUNCELLENIR_D213.py
    code_file = app_data_dir / CODE_FILE_NAME
    kod_guncel = kod_dosyasi_guncel_mi(app_data_dir, code)
    if not kod_guncel:
        _vardi = code_file.exists()
        # ⚠️ E2-1.9 (2-E incelemesi): dosya yalnız METİN ŞABLONU yüzünden de güncel olmayabilir (D2.75 metni değiştirdi; 1.9.50'den
        # yükseltme). "Kod değişti" yalnız dosyadaki kod bu kod DEĞİLSE denir — yoksa geçerli kasa kopyası "geçersiz" sanılır.
        try:
            _kod_ayni = _vardi and format_code(code) in code_file.read_text(encoding="utf-8")
        except Exception:
            _kod_ayni = False
        try:
            write_code_file(app_data_dir, code)
            kod_guncel = True
            logger.warning(
                "KURTARMA KODU %s: %s — bu kodu MAKINE DISINDA saklayin. Yedekleri "
                "baska bir makinede acmanin TEK yolu budur.",
                (
                    "dosya metni yenilendi (kod AYNI — kasadaki kod gecerli)"
                    if _kod_ayni
                    else "GUNCELLENDI (kod degisti; eski kod artik zarfi ACMAZ)"
                    if _vardi
                    else "yazildi"
                ),
                code_file,
            )
        except Exception:
            logger.warning(
                "kurtarma kodu dosyasi YAZILAMADI (%s) — bir sonraki yedek turunda yeniden denenecek; operator kodu henuz "
                "goremiyor.",
                code_file,
                exc_info=True,
            )

    # D2.60 (B-3.94): mühür YALNIZ zarf ve kod dosyası güncelken vurulur → yazılamayan kod dosyası sonraki turda yeniden denenir.
    if kod_guncel:
        try:
            fp_file.write_text(_FP_MUHUR_ONEKI + fp, encoding="utf-8")
        except Exception:
            logger.debug("kurtarma parmak izi yazilamadi", exc_info=True)

    if written:
        logger.info("Kurtarma zarfi guncellendi (%d dizin, %d anahtar)", written, len(keys))
    return True
