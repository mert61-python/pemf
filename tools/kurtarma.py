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

    # Şifreli operatör hesapları yedeğini düz auth_users.db'ye çöz (--yaz'dan SONRA):
    python tools/kurtarma.py --hesap-yedegi pemf_auth_users_<tarih>.db --cikti <veri-dizini>\\auth_users.db

GERİ YÜKLEME SIRASI
    1) Yeni makineye PEMF'i kurun, servisi HENÜZ BAŞLATMAYIN.
       (Başlatırsanız yeni bir sqlcipher_key üretilir ve yedekler açılmaz.)
    2) Bu aracı --yaz ile çalıştırın.
    3) Yedek dizinindeki EN YENİ dosyaları veri dizinine kopyalayın:
         pemf_treatment_history_<tarih>.db  ->  pemf_treatment_history.db
         pemf_patients_<tarih>.db           ->  patients.db
       Operatör hesapları (D2.51 · A-32): pemf_auth_users_<tarih>.db şifreliyse --hesap-yedegi ile
       auth_users.db'ye çözün; şifresiz kurulumda auth_users.db adıyla kopyalayın. Ayarlar:
       pemf_config_<tarih>.json -> config.json, pemf_system_settings_<tarih>.json -> system_settings.json
       (SIRSIZ — MQTT kullanıcı/parola ve API anahtarını yeniden girin).
    4) Servisi başlatın.
"""

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── DEPO KÖKÜ + BACKEND YOLU ─────────────────────────────────────────────────
# ⚠️ Bu betik 2026-09-18 klasör taşımasından (F4: `apps/backend/`) beri ÖLÜYDÜ: `utils`
#    artık depo kökünde değil. Açılışta `ModuleNotFoundError: No module named 'utils'`.
#    Ölçüldü 2026-09-21; kapı: tests/test_betikler_ACILIYOR.py
# ⚠️ SABİT DERİNLİK YAZILMAZ — kök İŞARET DOSYASIYLA yukarı aranır.
def _depo_koku(bas: Path) -> Path:
    for aday in (bas, *bas.parents):
        if (aday / "pyproject.toml").is_file() and (aday / "apps" / "backend").is_dir():
            return aday
    raise RuntimeError("depo kökü bulunamadı (işaret: pyproject.toml + apps/backend)")


_KOK = _depo_koku(Path(__file__).resolve())
for _yol in (_KOK, _KOK / "apps" / "backend"):
    if str(_yol) not in sys.path:
        sys.path.insert(0, str(_yol))

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

    # ⚠️ 2-A inceleme A2-1.6: anahtarlar TEK yazımda (ya hepsi ya hiçbiri). Eskiden tek tek yazılıyordu; ikinci yazım
    # düşünce (AV / kilit) diskte yalnız `sqlcipher_key` kalıyor, araç ham istisnayla çıkıyor ve sonraki açılış eksik
    # `patient_fernet_key`i YENİDEN ÜRETİYORDU → kurtarılan hasta alanları çözülemiyordu (ölçüldü).
    try:
        sm.set_secrets(keys)
    except Exception as e:
        print(f"YAZILAMADI ({type(e).__name__}: {e}) — HICBIR anahtar yazilmadi, sir deposu DEGISMEDI.")
        print()
        print("  Servisi BASLATMAYIN: eksik anahtar yeniden URETILIR ve kurtarilan veri acilamaz.")
        print("  Sir dizinine erisimi (antivirus / izin) duzeltip AYNI komutu yeniden calistirin.")
        return 4
    for name in keys:
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
    print("Operator hesaplari (sifreli yedek):")
    print("    python tools/kurtarma.py --hesap-yedegi pemf_auth_users_<tarih>.db --cikti <veri-dizini>\\auth_users.db")
    return 0


def _hesap_yedegini_coz(yedek: Path, cikti: Path) -> int:
    """⚠️ D2.51 (A-32): makine dışı / yerel hesap yedeğini (`pemf_auth_users_<tarih>.db`) düz `auth_users.db`ye çevirir.

    Şifreli kurulumda yedek BİRİNCİL `sqlcipher_key` ile şifrelidir (zarf yalnız onu taşır — A-13); anahtar bu makineye `--yaz` ile
    yerleşmiş olmalıdır. Düz yedek doğrulanıp kopyalanır. Çıktı VARSA dokunulmaz (mevcut hesapları ezmez)."""
    import logging
    import shutil

    from database.yedek_dosyasi import basarisiz_yedegi_kaldir, sifreli_yedegi_duze_coz, yedek_acilir_mi

    if not yedek.is_file():
        print(f"HATA: hesap yedegi bulunamadi: {yedek}")
        return 2
    if cikti.exists():
        print(f"DURDURULDU: cikti zaten var → {cikti}")
        print("  Mevcut hesaplarin USTUNE YAZILMAZ. Baska bir cikti yolu verin ya da dosyayi bilerek kaldirin.")
        return 3
    with open(yedek, "rb") as f:
        duz = f.read(16) == b"SQLite format 3\x00"
    if duz:
        if not yedek_acilir_mi(str(yedek), tam=True):
            print(f"HATA: sifresiz hesap yedegi ACILMIYOR / bozuk: {yedek}")
            return 2
        # ⚠️ D2-2.3 (2-D incelemesi): doğrudan çıktıya kopya disk dolunca YARIM auth_users.db bırakıyor, OSError yakalanmadan
        # kaçıyor, yeniden denemede rc 3 ("çıktı zaten var") yarım dosyayı koruyordu. Şifreli dalla aynı sözleşme: geçici ad →
        # doğrulama → os.replace; düşerse geçici silinir, çıktı OLUŞMAZ.
        gecici = Path(f"{cikti}.yazim.tmp")
        try:
            shutil.copy2(yedek, gecici)
            if not yedek_acilir_mi(str(gecici), tam=True):
                raise RuntimeError(f"kopya dogrulanamadi: {gecici}")
            os.replace(gecici, cikti)
        except Exception as e:
            basarisiz_yedegi_kaldir(str(gecici), logging.getLogger("kurtarma"))
            print(f"HATA: sifresiz hesap yedegi KOPYALANAMADI ({type(e).__name__}: {e}) — cikti YAZILMADI.")
            print("  Disk alanini ve hedef klasorun yazilabilir oldugunu denetleyip ayni komutu yeniden calistirin.")
            return 4
        print(f"Sifresiz hesap yedegi kopyalandi ve dogrulandi: {cikti}")
        return 0
    from database.sqlcipher_util import import_sqlcipher
    from utils import secrets_manager as sm

    anahtar = ""
    try:
        anahtar = sm.get_secret("sqlcipher_key", generate=False) or ""
    except Exception as e:
        print(f"HATA: sqlcipher_key okunamadi ({type(e).__name__}: {e})")
    if not anahtar:
        print("HATA: bu makinede sqlcipher_key YOK — once anahtarlari zarftan yerlestirin:")
        print("    python tools/kurtarma.py --zarf <yedek>\\kurtarma-zarfi.enc --kod <KOD> --yaz")
        return 2
    try:
        sifreli_yedegi_duze_coz(str(yedek), str(cikti), import_sqlcipher(), anahtar, logging.getLogger("kurtarma"))
    except Exception as e:
        print(f"HATA: hesap yedegi COZULEMEDI ({type(e).__name__}: {e}) — cikti YAZILMADI.")
        print("  Yedek baska bir anahtarla (onceki kurulum) sifrelenmis olabilir; o kurulumun zarfi/kodu gerekir.")
        return 4
    print(f"Hesap yedegi cozuldu ve dogrulandi: {cikti}")
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
    ap.add_argument(
        "--hesap-yedegi",
        type=Path,
        help="Operator hesaplari yedegini (pemf_auth_users_<tarih>.db) duz auth_users.db'ye coz (--yaz'dan sonra)",
    )
    ap.add_argument("--cikti", type=Path, help="--hesap-yedegi icin cikti yolu (or. <veri-dizini>\\auth_users.db)")
    a = ap.parse_args(argv)

    if a.kodu_goster:
        return _show_local_code()

    if a.hesap_yedegi:
        if not a.cikti:
            ap.error("--hesap-yedegi icin --cikti gerekli")
        return _hesap_yedegini_coz(a.hesap_yedegi, a.cikti)

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
