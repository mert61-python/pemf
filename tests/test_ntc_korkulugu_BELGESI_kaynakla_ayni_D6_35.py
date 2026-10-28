# -*- coding: utf-8 -*-
"""D6.35 (B-11.2 · B-11.10 EK · A-47) — "NTC bayrağı 1 olursa derleme DURUR" belge iddiası KAYNAKLA aynı; "bayrağı 1 yap" önerisi YOK.

ÖLÇÜLEN DURUM (HEAD ebf1c3fe, 2026-10-28):
  · İddia BUGÜN DOĞRU (D5.06'dan beri): `PEMF_NTC_TERMAL_ENABLED` tek tanımı iki çeviri biriminin ortak başlığında
    (`Core/Inc/pemf_akim.h`), `pemf_akim.c` onu `#include "pemf_akim.h"` ile `#error` korkuluğundan ÖNCE görür. Önişlemciyle ölçüldü
    (`arm-none-eabi-gcc -E -DPEMF_NTC_TERMAL_ENABLED=1 … pemf_akim.c` → `#error`, rc=1; varsayılanda iki birim de `0` görür).
    D5.06'ya kadar tanım yalnız `main.c`'deydi ve aynı belge cümleleri YANLIŞTI (B-8.14) — belge o tarihçeyi anar.
  · `docs/acik-isler-2026-09-12.md` B1 satırı "⚠️ AÇIK P0" ve §7 "NTC bağlanır bağlanmaz bayrağı 1 yap"; `firmware/README.md` HG-1 notu
    "fiziksel bağlandıktan sonra 1 yapın" diyordu — A-47 (sahip kapalı kararı): NTC termal kesme YOK. Öneri tarihçeye alınır (üstü çizili).

İKİ KOL:
  1. DERLEYİCİSİZ (CI'da HER ZAMAN koşar — orkestratör notu D6.35): `#include` grafiği + tek tanım yeri + korkuluk sırası yorumsuz
     kaynakta (`c_soyucu.c_soy`) ölçülür. Korkuluk ölüyse belge "derleme durur" diyemez → KIRMIZI.
     (Gerçek önişlemci kolu ayrı kapıdadır: `tests/test_ntc_acs712_korkulugu_ONISLEMDE_D5_06.py`, ZORUNLU kipte derleyicisiz FAIL.)
  2. BELGE: dört belge korkuluğu ve A-47'yi anar; "bayrağı 1 yap" önerisi YALNIZ üstü çizili (`~~…~~`) tarihçede kalabilir.

⚠️ A-47: termal kesme EKLENMEZ — bu kapı yalnız anlatımın kaynakla aynı kalmasını ölçer.
"""

from __future__ import annotations

import re
from pathlib import Path

from c_soyucu import c_soy
from utils.path_utils import kaynak_kokunu_bul

KOK = Path(kaynak_kokunu_bul(__file__))
STM = KOK / "firmware" / "stm32_pemf" / "Core"
AKIM_C = STM / "Src" / "pemf_akim.c"
AKIM_H = STM / "Inc" / "pemf_akim.h"
MAIN_C = STM / "Src" / "main.c"

DONANIM = KOK / "docs" / "DONANIM-UYUM-ANALIZI-2026-08-19.md"
PIN = KOK / "docs" / "stm32-pin-haritasi.md"
ACIK = KOK / "docs" / "acik-isler-2026-09-12.md"
FW_README = KOK / "firmware" / "README.md"

_TANIM = re.compile(r"^[ \t]*#define[ \t]+PEMF_NTC_TERMAL_ENABLED\b", re.M)
_INC = re.compile(r'^[ \t]*#include[ \t]+"pemf_akim\.h"', re.M)
_KORKULUK = re.compile(
    r"^[ \t]*#if[ \t]+defined\(PEMF_NTC_TERMAL_ENABLED\)[ \t]*&&[ \t]*\(PEMF_NTC_TERMAL_ENABLED[ \t]*!=[ \t]*0\)[ \t]*\n[ \t]*#error",
    re.M,
)
#: "bayrağı 1 yap" önerisinin bilinen biçimleri (üstü çizili tarihçe dışında YASAK).
_ONERI = (
    re.compile(r"bayrağı 1 yap", re.I),
    re.compile(r"bağlandıktan sonra 1 yapın", re.I),
    re.compile(r"NTC bağlanır bağlanmaz", re.I),
)


def _oku(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _cizilisiz(md: str) -> str:
    """`~~…~~` (satır aşabilir) üstü çizili tarihçeyi çıkarır."""
    return re.sub(r"~~.*?~~", " ", md, flags=re.S)


def test_KRITIK_korkuluk_CANLI_derleyicisiz_include_grafigi():
    akim_c, akim_h, main_c = (c_soy(_oku(p)) for p in (AKIM_C, AKIM_H, MAIN_C))
    yerler = [
        ad for ad, s in (("pemf_akim.h", akim_h), ("pemf_akim.c", akim_c), ("main.c", main_c)) if _TANIM.search(s)
    ]
    assert yerler == ["pemf_akim.h"], (
        f"PEMF_NTC_TERMAL_ENABLED tek tanımı ortak başlıkta (pemf_akim.h) olmalı, bulunan: {yerler} — pemf_akim.c korkuluğu ölü "
        "(B-8.14); belge 'derleme durur' DİYEMEZ"
    )
    assert re.search(r"#define[ \t]+PEMF_NTC_TERMAL_ENABLED[ \t]+0\b", akim_h), (
        "varsayılan 0 olmalı (A-47: bayrak 1 yapılmaz)"
    )
    inc = _INC.search(akim_c)
    kork = _KORKULUK.search(akim_c)
    assert inc and kork, "pemf_akim.c: #include \"pemf_akim.h\" ve #error korkuluğu ikisi de yorumsuz kaynakta olmalı"
    assert inc.start() < kork.start(), "pemf_akim.c: başlık korkuluktan SONRA içeriliyor — korkuluk makroyu görmez"
    assert _INC.search(main_c), "main.c ortak başlığı içermeli (iki birim aynı tanımı görsün)"


def test_belgeler_korkulugu_ve_A47yi_anar():
    for p, gerekli in (
        (DONANIM, ("pemf_akim.h", "D5.06", "A-47")),
        (PIN, ("pemf_akim.h", "D5.06", "A-47")),
        (FW_README, ("pemf_akim.h", "D5.06", "A-47", "#error")),
        (ACIK, ("pemf_akim.h", "A-47")),
    ):
        m = _oku(p)
        for g in gerekli:
            assert g in m, f"{p.name}: '{g}' anılmalı (NTC korkuluğu / A-47 anlatımı)"


def test_bayragi_1_yap_onerisi_YALNIZ_cizili_tarihcede():
    for p in (ACIK, FW_README, DONANIM, PIN):
        m = _cizilisiz(_oku(p))
        bulunan = [r.pattern for r in _ONERI if r.search(m)]
        assert not bulunan, (
            f"{p.name}: 'NTC bayrağını 1 yap' önerisi canlı ({bulunan}) — A-47: termal kesme YOK, tarihçeye alın (~~…~~)"
        )


def test_acik_isler_B1_ACIK_P0_degil_YAPILMAYACAK():
    satir = [s for s in _oku(ACIK).splitlines() if re.match(r"\|\s*(~~)?B1(~~)?\s*\|", s)]
    assert len(satir) == 1, f"acik-isler B1 satırı tek olmalı ({len(satir)})"
    s = _cizilisiz(satir[0])
    assert "AÇIK P0" not in s, "acik-isler B1: A-47 kapalı karar — 'AÇIK P0' değil"
    assert "YAPILMAYACAK" in s and "A-47" in s
