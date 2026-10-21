# -*- coding: utf-8 -*-
"""YH B7 — sitenin İngilizce ekran görüntüsü seti (`apps/web/public/screenshots/en/`) Türkçe setle AYNI biçimde: aynı adlar, 560 × 1116
JPEG (galeri `width={560} height={1116}` bildirir — oran bozulmasın), benzer sıkıştırma (Türkçe setin boyut aralığının yakınında; dev PNG ya
da bozuk dosya sitenin yükünü büyütmesin). Görseller yalıtılmış kum havuzunda UYDURMA demo verisiyle çekildi (YH B7; gerçek veri / yerel yol /
bildirim paneli YOK) — bu kapı biçimi ölçer, içeriği rapor kaydeder."""

from __future__ import annotations

import struct
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
TR = KOK / "apps" / "web" / "public" / "screenshots"
EN = TR / "en"


def _jpeg_boyut(yol: Path) -> tuple[int, int]:
    b = yol.read_bytes()
    assert b[:2] == b"\xff\xd8", f"{yol.name}: JPEG değil"
    i = 2
    while i < len(b):
        assert b[i] == 0xFF, f"{yol.name}: bozuk JPEG işaretçisi"
        isaret = b[i + 1]
        uzunluk = struct.unpack(">H", b[i + 2 : i + 4])[0]
        if isaret in (0xC0, 0xC1, 0xC2):
            yuk, gen = struct.unpack(">HH", b[i + 5 : i + 9])
            return gen, yuk
        i += 2 + uzunluk
    raise AssertionError(f"{yol.name}: SOF yok")


def test_ayni_adlar():
    tr = sorted(p.name for p in TR.glob("*.jpg"))
    assert len(tr) == 8
    assert sorted(p.name for p in EN.glob("*.jpg")) == tr
    assert not [p for p in EN.iterdir() if p.suffix.lower() != ".jpg"], "en/ altında JPEG dışı dosya"


def test_boyut_ve_sikistirma_turkce_setle_ayni_bicimde():
    tr_boyut = [p.stat().st_size for p in TR.glob("*.jpg")]
    alt, ust = min(tr_boyut) * 0.6, max(tr_boyut) * 1.6
    for p in sorted(EN.glob("*.jpg")):
        assert _jpeg_boyut(p) == (560, 1116), (p.name, _jpeg_boyut(p))
        assert alt <= p.stat().st_size <= ust, (p.name, p.stat().st_size, alt, ust)
    for p in sorted(TR.glob("*.jpg")):
        assert _jpeg_boyut(p) == (560, 1116), p.name
