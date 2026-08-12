# Author: mertaygn, cglrgrkn
"""KARDEŞ KAYNAK OKUMA — bu deponun DIŞINDAKİ dosyalara çapa atan testler için (2026-08-12).

Bazı testler kasten depo sınırını aşar: mobil uygulama (`pf/`), pazarlama sitesi
(`pemf-vet-web/` — KENDİ git deposu, kendi Vercel projesi) ve derleme çıktıları
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

import os
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent

#: Yayın makinesinde `1` yapılırsa kardeş kaynak eksikliği ATLAMA değil BAŞARISIZLIK sayılır.
ZORUNLU = os.environ.get("PEMF_CAPRAZ_KAYNAK_ZORUNLU") == "1"


def kaynak_yolu(gorece: str) -> Path:
    """guii köküne göre kardeş kaynak yolu (varlık kontrolü YAPMAZ)."""
    return KOK / gorece


def var_mi(gorece: str) -> bool:
    return kaynak_yolu(gorece).exists()


def atla_yoksa(gorece: str) -> None:
    """Kardeş kaynak yoksa testi atlar (zorunlu kipte düşürür). Okumadan kontrol için."""
    if var_mi(gorece):
        return
    sebep = f"kardeş kaynak yok: {gorece} — bu depoda izlenmez (.gitignore); ayrı depo/derleme çıktısı"
    if ZORUNLU:
        pytest.fail(f"PEMF_CAPRAZ_KAYNAK_ZORUNLU=1 ama {sebep}")
    pytest.skip(sebep)


def oku(gorece: str) -> str:
    """Kardeş kaynağı metin olarak okur; yoksa testi atlar (zorunlu kipte düşürür)."""
    atla_yoksa(gorece)
    return kaynak_yolu(gorece).read_text(encoding="utf-8")
