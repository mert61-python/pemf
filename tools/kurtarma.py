# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""PEMF felaket kurtarma aracı — yedekleri BAŞKA bir makinede açılabilir kılar.

NE ZAMAN KULLANILIR
    Klinik cihazının anakartı/diski öldü ya da Windows yeniden kuruldu. Elinizde
    yalnız yedek dizini (.db dosyaları + kurtarma-zarfi.enc) ve operatörün sakladığı
    KURTARMA KODU var.

NEDEN GEREKLİ
    Yedek .db dosyaları SQLCipher ile şifreli; anahtar eski makinede DPAPI
    (CRYPTPROTECT_LOCAL_MACHINE) ile sarılıydı → o makine olmadan çözülemez.
    Kurtarma zarfı anahtarların koda-bağlı bir kopyasını taşır.

KULLANIM
    # Sadece göster (hiçbir şey yazmaz):
    python tools/kurtarma.py --zarf E:\\PEMF_Yedek\\kurtarma-zarfi.enc --kod ABCDE-FGHIJ-...

    # Anahtarları BU makinenin sır deposuna yaz (yeni kurulum için):
    python tools/kurtarma.py --zarf ... --kod ... --yaz

    # Bu makinedeki kurtarma kodunu göster (cihaz hâlâ çalışıyorken):
    python tools/kurtarma.py --kodu-goster

GERİ YÜKLEME SIRASI
    1) Yeni makineye PEMF'i kurun, servisi HENÜZ BAŞLATMAYIN.
       (Başlatırsanız yeni bir sqlcipher_key üretilir ve yedekler açılmaz.)
    2) Bu aracı --yaz ile çalıştırın.
    3) Yedek dizinindeki EN YENİ dosyaları veri dizinine kopyalayın:
         pemf_treatment_history_<tarih>.db  ->  pemf_treatment_history.db
         pemf_patients_<tarih>.db           ->  patients.db
    4) Servisi başlatın.
"""

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.backup_recovery import (  # noqa: E402
    CODE_FILE_NAME,
    ENVELOPE_NAME,
    format_code,
    open_envelope,
)


def _show_local_code() -> int:
    from utils import secrets_manager as sm

    try:
        code = sm.get_secret("backup_recovery_code", generate=False)
    except Exception as e:
        print(f"HATA: kurtarma kodu okunamadi: {e}")
        return 2
    if not code:
        print("Bu kurulumda henuz kurtarma kodu URETILMEMIS.")
        print("Ilk yedek alindiginda uretilir (varsayilan: gunde bir).")
        return 1
    print()
    print("  KURTARMA KODU:  " + format_code(code))
    print()
    print("  Bu kodu MAKINE DISINDA saklayin (kasa / parola yoneticisi).")
    print("  Yedekleri baska bir makinede acmanin TEK yolu budur.")
    print()
    return 0


def _restore(zarf: Path, kod: str, yaz: bool) -> int:
    if not zarf.exists():
        print(f"HATA: zarf bulunamadi: {zarf}")
        return 2
    try:
        keys = open_envelope(kod, zarf.read_bytes())
    except ValueError as e:
        print(f"HATA: {e}")
        return 2

    print()
    print(f"Zarf ACILDI: {zarf}  ({len(keys)} anahtar)")
    print()
    for name, val in sorted(keys.items()):
        # Ekrana tam deger yazmak omuz-surfing riskidir; --yaz kullanilmadiysa
        # operatorun dogru zarfi actigini gorebilmesi icin YALNIZ ozet gosterilir.
        print(f"  {name:24s} : {val[:4]}...{val[-4:]}  ({len(val)} karakter)")
    print()

    if not yaz:
        print("Anahtarlar YAZILMADI (--yaz verilmedi).")
        print("Yeni kuruluma yerlestirmek icin ayni komutu --yaz ile calistirin.")
        return 0

    from utils import secrets_manager as sm

    mevcut = []
    for name in keys:
        try:
            if sm.get_secret(name, generate=False):
                mevcut.append(name)
        except Exception:
            # Cozulemeyen (baska makinenin DPAPI'siyle sarilmis) deger de "mevcut" sayilir:
            # ustune yazmak, o degerle sifrelenmis veriyi kalici kaybettirebilir.
            mevcut.append(name)
    if mevcut and os.environ.get("PEMF_KURTARMA_USTUNE_YAZ") != "1":
        print("DURDURULDU: bu makinede zaten anahtar var → " + ", ".join(mevcut))
        print()
        print("  Ustune yazmak, MEVCUT sifreli veriyi kalici olarak acilamaz hale getirebilir.")
        print("  NOT: anahtar pemf_secrets.json'da olmasa bile ESKI kaynaklardan (Windows keyring,")
        print("       .sqlcipher_key, config\\.pemf_key_v2) geliyor olabilir — bunlar da sayilir.")
        print("  Bu makine TAZE bir kurulumsa (hic hasta verisi YOK) su sekilde zorlayin:")
        print("      set PEMF_KURTARMA_USTUNE_YAZ=1   &&   python tools/kurtarma.py ... --yaz")
        return 3

    for name, val in keys.items():
        sm.set_secret(name, val)
        print(f"  yazildi: {name}")
    print()
    print("Anahtarlar bu makinenin sir deposuna yazildi.")
    print("Simdi yedek .db dosyalarini veri dizinine kopyalayip servisi baslatin:")
    print("    pemf_treatment_history_<tarih>.db  ->  pemf_treatment_history.db")
    # ⚠️ HEDEF AD `patients.db` (2026-08-15 duzeltmesi). Burada `pemf_patients.db` yaziyordu;
    # uygulama O ADI HIC ACMAZ → yonergeyi izleyen klinik hasta kayitlarini "geri yukledigini"
    # sanip bos bir hasta listesiyle calisirdi. YEDEK dosya on-eki (`pemf_patients_<tarih>.db`)
    # DEGISMEDI — onu `headless_db_maintenance` uretir ve rotasyona sokar.
    print("    pemf_patients_<tarih>.db           ->  patients.db")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="PEMF yedek kurtarma araci",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Zarf dosyasi yedek dizininde '{ENVELOPE_NAME}', kod ise kurulum "
        f"makinesindeki '{CODE_FILE_NAME}' dosyasindadir.",
    )
    ap.add_argument("--zarf", type=Path, help=f"Kurtarma zarfi yolu ({ENVELOPE_NAME})")
    ap.add_argument("--kod", help="Kurtarma kodu (tire/bosluk/kucuk harf farketmez)")
    ap.add_argument("--yaz", action="store_true", help="Anahtarlari BU makinenin sir deposuna yaz (yeni kurulum)")
    ap.add_argument(
        "--kodu-goster", action="store_true", help="Bu makinedeki kurtarma kodunu goster (cihaz calisirken)"
    )
    a = ap.parse_args(argv)

    if a.kodu_goster:
        return _show_local_code()

    if not a.zarf:
        ap.error("--zarf gerekli (ya da --kodu-goster kullanin)")

    kod = a.kod
    if not kod:
        try:
            import getpass

            kod = getpass.getpass("Kurtarma kodu: ")
        except Exception:
            ap.error("--kod gerekli")
    return _restore(a.zarf, kod, a.yaz)


if __name__ == "__main__":
    sys.exit(main())
