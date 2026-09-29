# -*- coding: utf-8 -*-
# Author: mertaygn
"""HASTA VERİSİ ANAHTARI — MAKİNE-DIŞI EMANET (escrow) ve doğrulama.

⚠️ NEDEN VAR — ÖLÇÜLMÜŞ RİSK (2026-09-13)
=========================================
Sahadaki makinede hasta veritabanları GERÇEKTEN şifreli (ölçüldü: `patients.db` ve
`pemf_treatment_history.db` başlıkları `SQLite format 3` DEĞİL). Bu iyi. Ama o şifreyi açan
anahtar tek bir yerde duruyor:

    C:\\ProgramData\\PEMF_System\\PEMF_GUI\\pemf_secrets.json  →  auto.sqlcipher_key
    biçim: "DPAPI:..."  →  **Windows DPAPI, MAKİNEYE BAĞLI**

⚠️ Taşınabilir sır yedeği (`~/pemf-sirlar.pemfsec`) bu anahtarı **TAŞIMIYOR** — ölçüldü, içinde
7 kalem var ve hepsi derleme-zamanı sırrı (ESP Secrets.h, Android keystore, cloud provision).

**SONUÇ:** disk/OS/profil kaybında DPAPI blob'u çözülemez → **hasta verisi KALICI OKUNAMAZ.**
Yedekten dönmek de kurtarmaz: şifreli `.db` dosyasını yedeklemek, anahtarı olmadan işe yaramaz.

⚠️ NEDEN `pemf-sirlar.pemfsec`E EKLENMEDİ: o arşiv **PAROLASIZ** (sahip kararı 2026-08-19, düz
base64). Hasta verisinin anahtarını parolasız bir dosyaya koymak, şifrelemenin kendisini
anlamsız kılardı. Bu yüzden AYRI ve BİLİNÇLİ bir adım: nereye konacağına sahip karar verir.

KULLANIM
--------
    # Emanet dosyasi uret (hedefi SIZ verirsiniz; varsayilan YOK)
    python scripts/hasta_anahtari_emanet.py --disa-aktar "D:/kasa/pemf-hasta-anahtari.txt"

    # Elinizdeki emanet HALA gecerli mi (anahtar degismis olabilir)
    python scripts/hasta_anahtari_emanet.py --dogrula "D:/kasa/pemf-hasta-anahtari.txt"

    # Yalniz parmak izini goster (anahtari YAZDIRMAZ) — kayit/karsilastirma icin
    python scripts/hasta_anahtari_emanet.py --parmak-izi

⚠️ EMANET DOSYASI DÜZ METİNDİR. Şifreli bir kasaya (parola yöneticisi, kasadaki USB, kurumsal
key-vault) koyun. Bilgisayarın kendi diskinde bırakmak riski KALDIRMAZ — amaç makine-dışı kopya.

⚠️ ACL: NTFS/ReFS'te emanet ÖNCE boş oluşturulup kilitlenir (SYSTEM + Administrators + betiği
çalıştıran hesap; yerel Users grubu OKUYAMAZ), içerik SONRA yazılır. Kilit tutmazsa düz-metin
emanet YAZILMAZ (çıkış 2). FAT/exFAT USB'de ACL yoktur: yazılır, uyarı basılır.

⚠️ `PEMF_DATA_DIR` tanımlıysa her üç komut da ürünün `get_app_data_directory()`sini çağırır; o,
kullanıcı kökündeki (%APPDATA%\\PEMF_GUI) sır ve veritabanlarını makine köküne VAR OLANI EZMEDEN
kopyalayabilir (`_kullanicidan_makineye_gocur`). `--parmak-izi` bu yüzden salt-okur DEĞİLDİR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


# ── DEPO KÖKÜ + BACKEND YOLU (D0Ö.19/20 · B-10.57, B-9.25) ──────────────────
# ⚠️ F4 (`apps/backend/`, 2026-09-18) taşımasından beri `utils` depo kökünde DEĞİL; yalnız kök
#    eklendiği için `_sirlari_oku` ilk çağrıda `ModuleNotFoundError` veriyordu (önsöz sağlam
#    görünüyordu) → emanet oluşturulamıyor/doğrulanamıyordu. Kök SABİT DERİNLİKLE (`parents[1]`)
#    değil İŞARET DOSYASIYLA aranır (scripts/stm_firmware_kimligi.py deseni).
#    Kapı: tests/test_betikler_ACILIYOR.py::test_KRITIK_fonksiyon_ici_ilk_taraf_importlari_COZULUYOR
def _depo_koku(bas: Path) -> Path:
    for aday in (bas, *bas.parents):
        if (aday / "pyproject.toml").is_file() and (aday / "apps" / "backend").is_dir():
            return aday
    raise RuntimeError("depo kökü bulunamadı (işaret: pyproject.toml + apps/backend). Betik depo dışına mı taşındı?")


KOK = _depo_koku(Path(__file__).resolve())
for _yol in (KOK, KOK / "apps" / "backend"):
    if str(_yol) not in sys.path:
        sys.path.insert(0, str(_yol))

#: Emanete alınacak alanlar. İkisi de kaybolursa veri okunamaz.
ALANLAR = (
    ("auto.sqlcipher_key", "whole-DB SQLCipher anahtari (patients.db + pemf_treatment_history.db)"),
    ("auto.patient_fernet_key", "alan-duzeyi hasta sifrelemesi (Fernet)"),
)


def _veri_koku_adaylari() -> list[Path]:
    """Sır dosyasının bulunabileceği kökler — ÖNCELİK SIRASIYLA.

    ⚠️ BU LİSTE ŞART: launcher backend'i `PEMF_DATA_DIR=%PROGRAMDATA%\\PEMF_System` ile
    başlatır (`launcher/core/src/install.rs::machine_data_dir`), yani SAHADAKİ gerçek sırlar
    `%PROGRAMDATA%\\PEMF_System\\PEMF_GUI` altındadır. Bu değişken olmadan
    `get_app_data_directory()` `%APPDATA%\\PEMF_GUI`ye düşer ve orada `auto.sqlcipher_key`
    **BOŞTUR** → araç "anahtar yok" der ve emanet SESSİZCE eksik çıkar.

    Ölçüldü (2026-09-13): tam olarak bu oldu — ilk koşuda yalnız `patient_fernet_key` göründü.
    """
    import os

    adaylar: list[Path] = []
    pd = os.environ.get("PROGRAMDATA", "").strip()
    if pd:
        adaylar.append(Path(pd) / "PEMF_System" / "PEMF_GUI")
    # ⚠️ D0Ö.20 (B-9.25): import hatası YUTULMAZ. Eskiden `except Exception: pass` idi — yol
    # bozukken (F4'ten beri tam böyle) PEMF_DATA_DIR kökü aday listesinden SESSİZCE düşüyor ve
    # araç YANLIŞ kökün anahtarını okuyup emanete koyabiliyordu.
    try:
        from utils.path_utils import get_app_data_directory
    except ImportError as e:
        raise SystemExit(
            f"HATA: utils.path_utils yuklenemedi ({e}) — PEMF_DATA_DIR koku bulunamaz ve YANLIS kokun "
            "anahtari okunabilir. Betigi depodan (scripts/) calistirin; depo/kurulum bozuk olabilir."
        ) from e
    try:
        adaylar.append(Path(get_app_data_directory()))
    except OSError as e:
        # D0Ö.20 ek: PEMF_DATA_DIR kökünde mkdir/göç izin hatası ham traceback değil, EYLEM söyler.
        raise SystemExit(
            f"HATA: veri koku belirlenemedi ({e}) — PEMF_DATA_DIR kokune erisilemiyor olabilir. "
            "Yonetici olarak calistirin ya da PEMF_DATA_DIR degerini denetleyin."
        ) from e
    ap = os.environ.get("APPDATA", "").strip()
    if ap:
        adaylar.append(Path(ap) / "PEMF_GUI")

    # Tekille (sıra korunur)
    gorulen: set[str] = set()
    benzersiz: list[Path] = []
    for a in adaylar:
        k = str(a).lower()
        if k not in gorulen:
            gorulen.add(k)
            benzersiz.append(a)
    return benzersiz


def _veri_koku() -> Path:
    """SQLCipher anahtarını GERÇEKTEN taşıyan kökü seç; yoksa ilk var olanı döndür."""
    ilk_var: Path | None = None
    for kok in _veri_koku_adaylari():
        yol = kok / "pemf_secrets.json"
        if not yol.is_file():
            continue
        if ilk_var is None:
            ilk_var = kok
        try:
            ham = json.loads(yol.read_text(encoding="utf-8"))
            if (ham.get("auto") or {}).get("sqlcipher_key"):
                return kok
        except Exception:
            continue
    if ilk_var is not None:
        return ilk_var
    raise SystemExit(
        "HATA: hicbir kokte pemf_secrets.json bulunamadi. Arananlar:\n  "
        + "\n  ".join(str(k) for k in _veri_koku_adaylari())
    )


def _sirlari_oku() -> dict[str, str]:
    """Canlı sır dosyasından ilgili alanları ÇÖZÜLMÜŞ olarak döndür."""
    from utils import secrets_manager as sm

    yol = _veri_koku() / "pemf_secrets.json"
    if not yol.is_file():
        raise SystemExit(f"HATA: sir dosyasi yok -> {yol}")
    ham = json.loads(yol.read_text(encoding="utf-8"))

    cozulmus: dict[str, str] = {}
    for alan, _aciklama in ALANLAR:
        grup, ad = alan.split(".", 1)
        depolanan = (ham.get(grup) or {}).get(ad) or ""
        if not depolanan:
            continue
        if not sm.bu_makinede_cozulebilir_mi(depolanan):
            raise SystemExit(
                f"HATA: {alan} BU MAKINEDE COZULEMIYOR.\n"
                "  DPAPI blob'u baska bir makine/hesap tarafindan yazilmis olabilir.\n"
                "  Bu, emanetin ZATEN gec kalindigi anlamina gelir — veriyi acabilen makinede kosturun."
            )
        cozulmus[alan] = sm._dec(depolanan)
    if not cozulmus:
        raise SystemExit(
            "HATA: hicbir anahtar bulunamadi. Sifreleme hic acilmamis olabilir\n"
            "  (kontrol: /api/health -> atRestEncrypted)."
        )
    return cozulmus


def _parmak(deger: str) -> str:
    """Anahtarın kendisini AÇMADAN kimliğini gösteren kısa özet."""
    return hashlib.sha256(deger.encode("utf-8")).hexdigest()[:16]


#: ACL destekleyen dosya sistemleri — burada kilit tutmazsa düz-metin emanet YAZILMAZ.
_ACL_DESTEKLI = {"NTFS", "REFS"}


def _dosya_sistemi(yol: Path) -> str | None:
    """`yol`un bulunduğu birimin dosya sistemi ("NTFS", "exFAT", "FAT32"…); Windows dışı/bilinmiyorsa None."""
    if sys.platform != "win32":
        return None
    import ctypes

    k32 = ctypes.windll.kernel32
    birim = ctypes.create_unicode_buffer(261)
    ad = ctypes.create_unicode_buffer(261)
    if not k32.GetVolumePathNameW(str(yol), birim, len(birim)):
        return None
    if not k32.GetVolumeInformationW(birim.value, None, 0, None, None, None, ad, len(ad)):
        return None
    return ad.value or None


def parmak_izi() -> int:
    kok = _veri_koku()
    print(f"  veri koku: {kok}")
    cozulmus = _sirlari_oku()
    for alan, aciklama in ALANLAR:
        deger = cozulmus.get(alan)
        durum = f"parmak={_parmak(deger)}" if deger else "YOK"
        print(f"  {alan:28s} {durum}  ({aciklama})")
    return 0


def disa_aktar(hedef: Path) -> int:
    # ⚠️ DEPOYA YAZMAYI REDDET: depo PUBLIC ve bu dosya DUZ METIN anahtar tasir.
    try:
        hedef.resolve().relative_to(KOK.resolve())
        print(
            f"HATA: hedef DEPO ICINDE -> {hedef}\n"
            "  Depo public; duz-metin hasta anahtari oraya YAZILAMAZ.\n"
            "  Kasadaki bir USB / parola yoneticisi / key-vault yolu verin."
        )
        return 2
    except ValueError:
        pass  # depo dışında — istenen budur

    # ⚠️ D0Ö.20 (B-9.25, İG-9.16): ACL modülü YAZMADAN ÖNCE yüklenir ve hatası YUTULMAZ. Eskiden
    # yazımdan SONRA `try/except: pass` içindeydi: modül yüklenemezse (F4'ten beri tam böyle)
    # düz-metin hasta anahtarı UYARISIZ ve ACL kilidi OLMADAN diske düşüyordu.
    try:
        from utils.file_acl import lock_down_file
    except ImportError as e:
        raise SystemExit(
            f"HATA: utils.file_acl yuklenemedi ({e}) — duz-metin emanet ACL kilidi olmadan YAZILMADI. "
            "Betigi depodan (scripts/) calistirin; depo/kurulum bozuk olabilir."
        ) from e

    cozulmus = _sirlari_oku()
    satirlar = [
        "# PEMF Vet — HASTA VERISI ANAHTARI (EMANET)",
        "# ⚠️ BU DOSYA DUZ METINDIR. Sifreli bir kasada saklayin.",
        "# ⚠️ KAYBOLURSA: sifreli hasta veritabanlari KALICI OLARAK OKUNAMAZ.",
        "#",
        "# Geri yukleme: bu degerleri hedef makinede",
        "#   <VERI_KOKU>/pemf_secrets.json  ->  auto.<alan>  alanlarina yazin",
        "#   (duz metin yazilir; backend ilk aciliste DPAPI ile yeniden sarar)",
        "# VERI_KOKU: C:\\ProgramData\\PEMF_System\\PEMF_GUI  (launcher PEMF_DATA_DIR ile verir)",
        "",
    ]
    for alan, aciklama in ALANLAR:
        deger = cozulmus.get(alan)
        if not deger:
            satirlar.append(f"# {alan} = (bu makinede yok)")
            continue
        satirlar.append(f"# {aciklama}")
        satirlar.append(f"# parmak izi: {_parmak(deger)}")
        satirlar.append(f"{alan} = {deger}")
        satirlar.append("")

    hedef.parent.mkdir(parents=True, exist_ok=True)
    yeni = not hedef.exists()
    try:
        hedef.touch()
    except PermissionError as e:
        raise SystemExit(
            f"HATA: hedefe yazilamiyor ({e.strerror}: {hedef}) — onceki bir surumun yalniz-yonetici kilidi "
            "olabilir. Yonetici olarak calistirin ya da baska bir hedef verin."
        ) from e
    # ⚠️ D0Ö.20 ek (tur 4): ÖNCE boş dosya kilitlenir, SONRA içerik yazılır — arada düz-metin anahtar
    # miras ACL'siyle (Users okur) durmaz. `keep_current_user=True`: yalnız SYSTEM + Administrators
    # kilidi UAC'li/standart hesabı KENDİ emanetinden dışarı atıyordu (`--dogrula` PermissionError —
    # ÖLÇÜLDÜ; file_acl: "DENETİM P3 — sahada yaşandı"). Yerel Users grubu yine OKUYAMAZ.
    # `lock_down_file` hata ATMAZ, False döner (best-effort) — dönüş OKUNUR.
    kilit_notu = ""
    if lock_down_file(hedef, keep_current_user=True):
        kilit_notu = "ACL: yalniz SYSTEM, Administrators ve bu hesap okuyabilir (yerel Users grubu okuyamaz)."
    else:
        fs = _dosya_sistemi(hedef)
        if (fs or "").upper() in _ACL_DESTEKLI:
            if yeni:
                hedef.unlink(missing_ok=True)
            print(
                f"HATA: ACL kilidi UYGULANAMADI ({hedef}, {fs}) — duz-metin emanet YAZILMADI: bu birim ACL "
                "destekliyor ve kilitsiz dosya bu makinedeki baska hesaplarca okunabilirdi. Yonetici olarak "
                "calistirin ya da sifreli kasa / USB hedefi verin.",
                file=sys.stderr,
            )
            return 2
        print(
            f"UYARI: ACL kilidi UYGULANAMADI ({hedef}, {fs or 'dosya sistemi bilinmiyor'}) — dosya bu makinedeki "
            "baska hesaplarca okunabilir (FAT/exFAT USB'de ACL yoktur). Yalniz sizin erisebildiginiz bir yerde "
            "(sifreli kasa / fiziksel olarak korunan USB) tutun.",
            file=sys.stderr,
        )
    hedef.write_text("\n".join(satirlar) + "\n", encoding="utf-8")

    print(f"emanet yazildi: {hedef}")
    if kilit_notu:
        print(f"  {kilit_notu}")
    for alan, _a in ALANLAR:
        if cozulmus.get(alan):
            print(f"  {alan:28s} parmak={_parmak(cozulmus[alan])}")
    print(
        "\n⚠️ SIMDI: bu dosyayi bu bilgisayarin DISINA tasiyin (kasadaki USB / parola yoneticisi).\n"
        "   Ayni diskte durursa risk KALKMAZ — amac makine-disi kopya."
    )
    return 0


def dogrula(emanet: Path) -> int:
    if not emanet.is_file():
        print(f"HATA: emanet dosyasi yok -> {emanet}")
        return 2
    kayitli: dict[str, str] = {}
    try:
        metin = emanet.read_text(encoding="utf-8")
    except PermissionError as e:
        raise SystemExit(
            f"HATA: emanet okunamiyor ({e.strerror}: {emanet}) — dosya yalniz yoneticilere kilitli olabilir "
            "(eski surum). Yonetici olarak calistirin."
        ) from e
    for satir in metin.splitlines():
        s = satir.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        kayitli[k.strip()] = v.strip()

    canli = _sirlari_oku()
    sorun = 0
    for alan, _a in ALANLAR:
        c, e = canli.get(alan), kayitli.get(alan)
        if c and not e:
            print(f"  ⚠️ {alan}: CANLIDA VAR, emanette YOK -> emanet EKSIK")
            sorun += 1
        elif c and e and c != e:
            print(f"  ⚠️ {alan}: emanet ESKI (parmak {_parmak(e)} != canli {_parmak(c)})")
            sorun += 1
        elif c and e:
            print(f"  ✓ {alan}: guncel (parmak {_parmak(c)})")

    if sorun:
        print("\nSONUC: EMANET GECERSIZ — bu dosyayla veri KURTARILAMAZ. Yeniden disa aktarin.")
        return 1
    print("\nSONUC: EMANET GUNCEL.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--disa-aktar", metavar="HEDEF", help="emanet dosyasi uret (depo disi bir yol)")
    g.add_argument("--dogrula", metavar="DOSYA", help="elindeki emanet hala gecerli mi")
    g.add_argument("--parmak-izi", action="store_true", help="yalniz parmak izi goster (anahtari YAZDIRMAZ)")
    a = ap.parse_args()
    if a.parmak_izi:
        return parmak_izi()
    if a.disa_aktar:
        return disa_aktar(Path(a.disa_aktar))
    return dogrula(Path(a.dogrula))


if __name__ == "__main__":
    sys.exit(main())
