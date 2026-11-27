# Author: mertaygn, cglrgrkn
"""KARDEŞ KAYNAK OKUMA — bu deponun DIŞINDAKİ dosyalara çapa atan testler için (2026-08-12).

Bazı testler kasten depo sınırını aşar: mobil uygulama (`apps/ui/`), pazarlama sitesi
(`apps/web/` — KENDİ git deposu, kendi Vercel projesi) ve derleme çıktıları
(`release_assets/ai_models`, `*/dist`). Bu yollar `.gitignore` ile BİLEREK dışlanmıştır;
`git ls-files` hepsinde **0 dosya** döner.

ARIZA: CI'ın temiz checkout'unda o dosyalar YOKTUR, dolayısıyla bu testler
`FileNotFoundError` ile düşüyordu — ölçtükleri değişmez bozulduğu için DEĞİL, ölçecek şey
bulunmadığı için. `critical-path-tests` hattının 16 çalışmasının 16'sında da kırmızı kalma
sebeplerinden biri buydu (2026-08-12 teşhisi).

KURAL, bu depoda `test_ai_golden_values.py` ile zaten yerleşik olan desenle AYNI:
yoksa **ATLA** — ama `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1` ayarlıysa atlamak **YASAK**, test düşer.
Yayın makinesi bu değişkeni ayarlayarak "sessizce atlandı" durumunu imkânsız kılar.

Neden atlama? Var olmayan bir dosya yüzünden kırmızı yanan hat, gerçek bir regresyonu
haber veremez hâle gelir — herkes kırmızıyı görmezden gelmeye alışır. Atlama dürüsttür
(çalışmadığını SÖYLER); zorunlu kip de bu dürüstlüğün yayında kaçamağa dönüşmesini engeller.
"""

import importlib
import os
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent

#: Yayın makinesinde `1` yapılırsa kardeş kaynak eksikliği ATLAMA değil BAŞARISIZLIK sayılır.
ZORUNLU = os.environ.get("PEMF_CAPRAZ_KAYNAK_ZORUNLU") == "1"
#: CT1 c (istem 66 · Y324): Y30 (`scripts/yayin_oncesi_suit.ps1`) `1` yapar. CI de ZORUNLU koşar (model paketi tam — eser yoksa
#: KIRMIZI); yalnız yayın makinesinde bulunan eser (`yalniz_yayin=True`: kurucu EXE, APK, base-deps.zip, TR tabanı …) CI'da GEREKÇELİ
#: atlar (`tests/ci_atlanan_defteri.json`, sınıf Y), yayın makinesinde ZORUNLU kuralı aynen işler (atlamaz, düşer).
YAYIN_MAKINESI = os.environ.get("PEMF_YAYIN_MAKINESI") == "1"
Y_ONEKI = "[Y — yalnız yayın makinesi]"


def kaynak_yolu(gorece: str) -> Path:
    """guii köküne göre kardeş kaynak yolu (varlık kontrolü YAPMAZ)."""
    return KOK / gorece


def var_mi(gorece: str) -> bool:
    return kaynak_yolu(gorece).exists()


def atla_yoksa(gorece: str, *, izlenen: bool = False, yalniz_yayin: bool = False) -> None:
    """Kardeş kaynak yoksa testi atlar (zorunlu kipte düşürür). Okumadan kontrol için.

    `izlenen=True` (D4.04, 2026-10-10): yol bu depoda İZLENEN bir ağaçtadır (`firmware/`, `apps/ui/`). Yalnız
    backend paketinde yokluğu beklenir; tam depoda yokluk bir klasör taşıması/silinmesidir — düz `skipif`
    bunu ZORUNLU=1'de de sessizce atlıyordu. Atlama nedeni bunu söyler.
    """
    if var_mi(gorece):
        return
    if izlenen:
        sebep = f"izlenen kaynak yok: {gorece} — depoda İZLENİR; tam depoda yokluğu klasör taşıması/silinmesidir (yalnız backend paketinde beklenir)"
    else:
        sebep = f"kardeş kaynak yok: {gorece} — bu depoda izlenmez (.gitignore); ayrı depo/derleme çıktısı"
    atla(sebep, yalniz_yayin=yalniz_yayin)


def oku(gorece: str) -> str:
    """Kardeş kaynağı metin olarak okur; yoksa testi atlar (zorunlu kipte düşürür)."""
    atla_yoksa(gorece)
    return kaynak_yolu(gorece).read_text(encoding="utf-8")


def atla(sebep: str, *, yalniz_yayin: bool = False) -> None:
    """Yol DIŞI eser yokluğu (çözümlenen ağırlık, araç ikilisi …): atla — ZORUNLU kipte DÜŞ (D5-F, 2026-10-27).

    Depo köküne göre bir yolun yokluğunda `atla_yoksa` tercih edilir (izlenen / kardeş ayrımını o yapar). Bu ikiz, varlığı
    bir yol değil bir ÇÖZÜMLEME sonucu olan eserler içindir (ör. ürünün model köklerinden bulunan ağırlık). Düz
    `pytest.skip` ZORUNLU=1'de de atlıyordu; meta kapı (`test_atlama_ZORUNLU_kipte_DUSER_D5.py`) onu yasaklar.

    Modül düzeyinde de çağrılabilir (`importorskip` gibi): varsayılan kipte modülü atlar, ZORUNLU kipte toplama HATASI (kırmızı).
    `yalniz_yayin=True` (CT1 c): eser YALNIZ yayın makinesinde bulunur → yayın makinesi DIŞINDA (CI) ZORUNLU'da da gerekçeli atlar;
    test / modül `yalniz_yayin_makinesi` işaretini taşımalı (Y30'da atlarsa `yayin_makinesi_kapisi` kırmızı yapar).
    """
    if yalniz_yayin and not YAYIN_MAKINESI:
        pytest.skip(f"{Y_ONEKI} {sebep}", allow_module_level=True)
    if ZORUNLU:
        pytest.fail(f"PEMF_CAPRAZ_KAYNAK_ZORUNLU=1 ama {sebep}")
    pytest.skip(sebep, allow_module_level=True)


#: Depo içi üst düzey paketler (`tests/golden/eser.py` `_DEPO_PAKETLERI` ile AYNI ilke): bunlardan birinin eksikliği "isteğe
#: bağlı paket yok" DEĞİL, ürün / taşıma hatasıdır — atlamaya gizlenmez.
_DEPO_PAKETLERI = frozenset(
    {"ai_hub", "utils", "servers", "database", "services", "controllers", "golden", "ai", "capraz"}
)


def paket_yoksa_atla(ad: str, *, sebep: str = ""):
    """`pytest.importorskip`in ZORUNLU'ya bağlı ikizi: paket YOKSA atla (zorunlu kipte DÜŞ), varsa modülü döndür.

    Varsayılan kipte `importorskip` ile AYNI sonuç (CI davranışı değişmez): paketin kendisi ya da içe aktarırken istediği 3. taraf
    bağımlılık yoksa ATLAR. Tek fark (ve ZORUNLU dışındaki tek sıkılaştırma): eksik modül DEPO paketindense (`servers.…`,
    `ai_hub.…`) bu bir ürün / taşıma hatasıdır — atlamaya GİZLENMEZ, `ImportError` olduğu gibi yükselir. Atlama nedeni paket adını
    taşır (`sqlcipher3` → A-46 yerel kapısı da görür).
    """
    try:
        return importlib.import_module(ad)
    except ImportError as e:
        eksik = getattr(e, "name", None) or ""
        if eksik.split(".")[0] in _DEPO_PAKETLERI:
            raise
        atla(
            f"isteğe bağlı paket yok: {ad}"
            + (f" ({eksik})" if eksik and eksik != ad else "")
            + (f" — {sebep}" if sebep else "")
        )
