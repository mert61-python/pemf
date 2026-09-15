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
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

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
    try:
        from utils.path_utils import get_app_data_directory

        adaylar.append(Path(get_app_data_directory()))
    except Exception:
        pass
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
    hedef.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    try:
        from utils.file_acl import lock_down_file

        lock_down_file(hedef)
    except Exception:
        pass

    print(f"emanet yazildi: {hedef}")
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
    for satir in emanet.read_text(encoding="utf-8").splitlines():
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
