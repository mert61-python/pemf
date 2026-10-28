# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.21 (B-8.10) — ESP32-S3 BLE provizyon başlıkları SÜRE / PIN iddiasını KODLA aynı söyler (ESP kodu SİLİNMEZ, Ö.4-Y7).

Kusur: `BLEProvisioning.h` senaryosu "120sn timeout: süre dolarsa BLE otomatik kapanır" diyordu; `BLEProvisioning.cpp::process()`
"Sınırsız Süre — 120sn timeout kaldırıldı" ve `SharedDefs.h` `BLE_ADV_TIMEOUT_SEC` HİÇBİR yerde tüketilmiyor. BLE yapılandırma yüzeyi
kimlik doğrulamasız olduğu için "süre dolunca kapanır" güvenlik iddiası operatörü yanıltır.

Ölçüm (derleyici YOK — xtensa yok): yorumları soyulmuş (dize-bilinçli `c_soyucu.c_soy`) S3 kaynağında sabitin `#define` DIŞI tüketim
sayısı 0 iken başlık yorumları süre sınırı iddia etmez ve tanım satırı "KULLANILMIYOR" diye işaretlidir. `Secrets.h` (A-41: sır dosyası,
skip-worktree) taranmaz ve DEĞİŞTİRİLMEZ.
"""

from __future__ import annotations

import re
from pathlib import Path

from c_soyucu import c_soy

KOK = Path(__file__).resolve().parent.parent
S3 = KOK / "firmware" / "esps3_pemf_coil"
SABIT = "BLE_ADV_TIMEOUT_SEC"


def _kaynaklar() -> dict[str, str]:
    return {
        p.name: p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(S3.iterdir())
        if p.suffix in (".h", ".cpp", ".ino") and p.name != "Secrets.h"
    }


def _tuketim(sabit: str) -> int:
    n = 0
    for metin in _kaynaklar().values():
        for satir in c_soy(metin).splitlines():
            if re.search(rf"\b{sabit}\b", satir) and not re.match(rf"\s*#\s*define\s+{sabit}\b", satir):
                n += 1
    return n


def test_KARSIT_D6_21_olcut_GERCEK_process_SURESIZ_ve_sabit_TUKETILMIYOR():
    """Aparat kendi kendine yeşil olmasın: process() süre denetimi yapmıyor ve sabitin tüketimi gerçekten 0."""
    cpp = c_soy((S3 / "BLEProvisioning.cpp").read_text(encoding="utf-8"))
    govde = cpp[cpp.index("void BLEProvisioning::process()") :]
    govde = govde[: govde.index("\n}\n") if "\n}\n" in govde else len(govde)]
    assert "stopAdvertising" not in govde and "_advertisingStartTime" not in govde, (
        "ölçüt değişti: process() süre denetimi yapıyor"
    )
    assert _tuketim(SABIT) == 0, "ölçüt değişti: BLE_ADV_TIMEOUT_SEC artık tüketiliyor — başlık yeniden ölçülmeli"


def test_KRITIK_BLE_baslik_yorumlari_SURE_SINIRI_iddia_etmez_D6_21():
    if _tuketim(SABIT):
        return  # süre sınırı gerçekten uygulanıyorsa iddia serbest (KARŞIT test bu durumu ayrıca yakalar)
    kotu = []
    for ad, metin in _kaynaklar().items():
        for no, satir in enumerate(metin.splitlines(), 1):
            yorum = satir.split("//", 1)[1] if "//" in satir else ""
            if re.search(r"(?i)kald[ıi]r", yorum):  # "120sn timeout kaldırıldı" — DOĞRU tarih notu, iddia değil
                continue
            if re.search(r"(?i)\d+\s*sn\s*timeout|süre dolarsa BLE otomatik kapan|timeout ile kapandı", yorum):
                kotu.append(f"{ad}:{no}: {satir.strip()}")
    assert not kotu, (
        "BLE süre sınırı uygulanmıyor (BLE_ADV_TIMEOUT_SEC tüketimi 0) ama yorum iddia ediyor:\n" + "\n".join(kotu)
    )


def test_KRITIK_tuketilmeyen_sabit_KULLANILMIYOR_diye_isaretli_D6_21():
    if _tuketim(SABIT):
        return
    tanim = [
        s
        for s in (S3 / "SharedDefs.h").read_text(encoding="utf-8").splitlines()
        if re.match(rf"\s*#\s*define\s+{SABIT}\b", s)
    ]
    assert len(tanim) == 1, f"{SABIT} tanımı bulunamadı / birden fazla (Ö.4-Y7: silinmez)"
    # tanımın HEMEN üstündeki bitişik `//` yorum bloğu (ya da satır sonu yorumu) işareti taşımalı
    ust = (S3 / "SharedDefs.h").read_text(encoding="utf-8").split(tanim[0])[0].splitlines()
    blok = []
    while ust and ust[-1].strip().startswith("//"):
        blok.insert(0, ust.pop())
    onceki = "\n".join(blok)
    assert "KULLANILMIYOR" in tanim[0] or "KULLANILMIYOR" in onceki, (
        f"{SABIT} hiçbir yerde tüketilmiyor ama tanımı 'KULLANILMIYOR' diye işaretli değil: {onceki!r} / {tanim[0]!r}"
    )
