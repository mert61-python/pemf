# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YH · A1 (istem 50 · Y289): bir sonraki yayının sürüm notu TASLAĞI — app 1.9.53 · launcher 1.9.55 · mobile 2.3.36.

Yayın hazırlığı (A) `versions.json`'a YAZMAZ (B6 kesinleştirir); notların taslağı `docs/surum_notlari.json`'da önceden durur ki
yayın günü notsuz / tek dilli / iddialı bir metin manifest'e girmesin. Bu kapı:
  · taslak sürümlerin İKİ dilde notu var; Türkçe not Türkçe, İngilizcede Türkçe harf yok, tıbbi iddia yok (YH-D1 ile aynı kural);
  · taslak sürüm `versions.json`'daki sürümden KÜÇÜK değil (taslak yayındaki notu ezemez; B6'da eşitlenir);
  · dosyadaki HER sürümün notu aynı kurallara uyar (eskiden yalnız `versions.json`'daki sürüm ölçülüyordu — taslak ölçüsüz kalırdı).
B6'dan sonra taslak = yayın sürümü olur; kapı eşitlikte de geçer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
NOTLAR = KOK / "docs" / "surum_notlari.json"
TASLAK = {"app": "1.9.53", "launcher": "1.9.56", "mobile": "2.3.36"}  # YS3c: başlatıcı 1.9.56 (yayınlanmadı)

_TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
_IDDIA_TR = re.compile(r"(?i)(iyileştir|şifa|tedavi eder|tedavi sağlar|ağrıyı (giderir|azaltır|keser)|etkili tedavi)")
_IDDIA_EN = re.compile(r"(?i)\b(cures?|heals?|healing|treats?|treating|therapeutic effect|pain relief|relieves?)\b")


def _notlar() -> dict:
    return json.loads(NOTLAR.read_text(encoding="utf-8"))


def _surum(s: str) -> tuple[int, ...]:
    return tuple(int(p) for p in s.split("."))


def _kural_ihlali(kanal: str, surum: str, kayit) -> list[str]:
    if not isinstance(kayit, dict):
        return [f"{kanal} {surum}: kayıt yok"]
    tr, en = str(kayit.get("notes") or ""), str(kayit.get("notes_en") or "")
    hatalar = []
    if not tr.strip() or not _TR_HARF.search(tr):
        hatalar.append(f"{kanal} {surum}: Türkçe not boş / Türkçe değil")
    if not en.strip() or _TR_HARF.search(en):
        hatalar.append(f"{kanal} {surum}: İngilizce not boş ya da Türkçe harf taşıyor")
    if _IDDIA_TR.search(tr) or _IDDIA_EN.search(en):
        hatalar.append(f"{kanal} {surum}: tıbbi iddia")
    return hatalar


@pytest.mark.parametrize("kanal", sorted(TASLAK))
def test_KRITIK_bir_sonraki_yayinin_TASLAK_notu_IKI_dilde_ve_iddiasiz(kanal):
    surum = TASLAK[kanal]
    assert _kural_ihlali(kanal, surum, _notlar().get(kanal, {}).get(surum)) == []


@pytest.mark.parametrize("kanal", sorted(TASLAK))
def test_taslak_surum_YAYINDAKINDEN_kucuk_degil(kanal):
    v = json.loads((KOK / "versions.json").read_text(encoding="utf-8"))
    yayindaki = {"app": v["backend"], "launcher": v["launcher"], "mobile": v["mobile"]["name"]}[kanal]
    assert _surum(TASLAK[kanal]) >= _surum(yayindaki), f"{kanal}: taslak {TASLAK[kanal]} < versions.json {yayindaki}"


def test_KRITIK_dosyadaki_HER_surum_notu_ayni_kurallara_uyar():
    hatalar = [
        h
        for kanal in ("app", "launcher", "mobile")
        for s, k in _notlar().get(kanal, {}).items()
        for h in _kural_ihlali(kanal, s, k)
    ]
    assert hatalar == []


def test_KARSIT_kural_olcucusu_ihlalleri_YAKALAR():
    assert _kural_ihlali("app", "9.9.9", None)
    assert _kural_ihlali("app", "9.9.9", {"notes": "Only English", "notes_en": "ok"})
    assert _kural_ihlali("app", "9.9.9", {"notes": "Türkçe", "notes_en": "Türkçe harf"})
    assert _kural_ihlali("app", "9.9.9", {"notes": "Ağrıyı giderir.", "notes_en": "fine"})
    assert _kural_ihlali("app", "9.9.9", {"notes": "Türkçe not", "notes_en": "It heals."})
    assert _kural_ihlali("app", "9.9.9", {"notes": "Türkçe not", "notes_en": "Plain note."}) == []
