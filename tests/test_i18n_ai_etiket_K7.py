# -*- coding: utf-8 -*-
"""K-7 · AI ETİKET EŞLİĞİ arayüz ↔ sunucu (T7) — sürüklenme kapısı.

Aynı model çıktısı (alan adı / sınıf kimliği / belirti) iki yerde metne çevrilir: arayüz `apps/ui/src/utils/aiDetail.ts`
(`DETAIL_LABELS`, `VALUE_LABELS`) + `screens/AiHubScreen.tsx` (`DISEASE_FEATURE_TR`) ve sunucu PDF'i `apps/backend/utils/ai_rapor_ogeleri.py`
(`ETIKETLER`, `DEGERLER`, `BELIRTILER`). ÖLÇÜLDÜ (I18N-0, taban `c1e098ef`): 164 ortak kimliğin 69'unda Türkçe BİLEREK farklı (ekran kısa,
PDF sade — 78099b44, sahip bildirimi 2026-10-18) ve bazı kimlikler yalnız bir tarafta. TR birebir kuralı bunları DONDURUR:
  * ortak kimlikte TR ve EN iki tarafta AYNI — ya da `i18n/ai-etiket-farklari.json` → `farkli` listesinde (gerekçeli);
  * yalnız bir tarafta olan kimlik o listenin `yalnizArayuz` / `yalnizSunucu` kümesinde;
  * yeni bir kimlik eklemek ya da ortak değeri bir tarafta değiştirmek → listeyi gerekçeyle güncellemeden geçemez.
Tablo değeri göç sonrası bir katalog anahtarıdır (`ai.etiket.x`) ya da göç öncesi Türkçe metnin kendisi; kapı ikisini de çözer.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
for p in (KOK, KOK / "apps" / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from scripts.i18n import ortak  # noqa: E402

FARK = json.loads((KOK / "i18n" / "ai-etiket-farklari.json").read_text(encoding="utf-8"))
CIFT = re.compile(r'(?:"([^"]+)"|([A-Za-z_][A-Za-z0-9_]*))\s*:\s*"((?:[^"\\]|\\.)*)"')
ANAHTAR = re.compile(r"^[a-z][A-Za-z0-9]*(\.[A-Za-z0-9_]+)+$")
UI_TABLO = {
    "etiket": ("apps/ui/src/utils/aiDetail.ts", "DETAIL_LABELS"),
    "deger": ("apps/ui/src/utils/aiDetail.ts", "VALUE_LABELS"),
    "belirti": ("apps/ui/src/screens/AiHubScreen.tsx", "DISEASE_FEATURE_TR"),
}
SV_TABLO = {"etiket": "ETIKETLER", "deger": "DEGERLER", "belirti": "BELIRTILER"}


def _coz(deger: str, yuzey: str, dil: str) -> str:
    if ANAHTAR.match(deger):
        return str(ortak.duzlestir(ortak.katalog_yukle(yuzey, dil)).get(deger, f"<katalogda yok: {deger}>"))
    return deger if dil == "tr" else ""  # göç öncesi: tablo TR metni taşır, EN henüz yok


def ui_tablosu(tur: str, dil: str) -> dict[str, str]:
    dosya, ad = UI_TABLO[tur]
    src = (KOK / dosya).read_text(encoding="utf-8")
    i = src.index(f"const {ad}")
    j = src.index("};", i)
    return {(a or b): _coz(c, "arayuz", dil) for a, b, c in CIFT.findall(src[i:j])}


def sunucu_tablosu(tur: str, dil: str) -> dict[str, str]:
    import importlib

    m = importlib.import_module("utils.ai_rapor_ogeleri")
    return {k: _coz(v, "sunucu", dil) for k, v in getattr(m, SV_TABLO[tur]).items()}


@pytest.mark.parametrize("tur", list(UI_TABLO))
def test_K7_ortak_kimlikler_ayni_ya_da_gerekceli_farkli(tur):
    ui, sv = ui_tablosu(tur, "tr"), sunucu_tablosu(tur, "tr")
    liste = FARK[tur]
    sorun = []
    for k in sorted(set(ui) & set(sv)):
        if ui[k] != sv[k] and k not in liste["farkli"]:
            sorun.append(f"{tur}:{k}: arayüz {ui[k]!r} ≠ sunucu {sv[k]!r} (listede yok)")
        if ui[k] == sv[k] and k in liste["farkli"]:
            sorun.append(f"{tur}:{k}: artık AYNI — farklar listesinden çıkarın")
    if set(ui) - set(sv) != set(liste["yalnizArayuz"]):
        sorun.append(
            f"{tur}: yalnız arayüzde olan kimlikler değişti: +{sorted(set(ui) - set(sv) - set(liste['yalnizArayuz']))} "
            f"-{sorted(set(liste['yalnizArayuz']) - (set(ui) - set(sv)))}"
        )
    if set(sv) - set(ui) != set(liste["yalnizSunucu"]):
        sorun.append(
            f"{tur}: yalnız sunucuda olan kimlikler değişti: +{sorted(set(sv) - set(ui) - set(liste['yalnizSunucu']))} "
            f"-{sorted(set(liste['yalnizSunucu']) - (set(sv) - set(ui)))}"
        )
    assert not sorun, "\n".join(sorun)


@pytest.mark.parametrize("tur", list(UI_TABLO))
def test_K7_ingilizce_ortak_kimliklerde_ayni(tur):
    """Göç sonrası: TR'si AYNI olan ortak kimliğin EN'i de iki tarafta aynı (biri çevrilmişse öteki de)."""
    ui_tr, sv_tr = ui_tablosu(tur, "tr"), sunucu_tablosu(tur, "tr")
    ui_en, sv_en = ui_tablosu(tur, "en"), sunucu_tablosu(tur, "en")
    sorun = [
        f"{tur}:{k}: EN arayüz {ui_en[k]!r} ≠ sunucu {sv_en[k]!r}"
        for k in sorted(set(ui_tr) & set(sv_tr))
        if ui_tr[k] == sv_tr[k] and ui_en[k] and sv_en[k] and ui_en[k] != sv_en[k]
    ]
    assert not sorun, "\n".join(sorun)


def test_K7_KARSIT_ayristirici_tablolari_OKUR():
    assert len(ui_tablosu("etiket", "tr")) >= 100 and len(sunucu_tablosu("etiket", "tr")) >= 60
    assert ui_tablosu("deger", "tr").get("no pain") and sunucu_tablosu("deger", "tr").get("no pain")
