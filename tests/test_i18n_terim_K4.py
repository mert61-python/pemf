# -*- coding: utf-8 -*-
"""K-4 · TERİM SÖZLÜĞÜ (T12) — `i18n/terimler.json`: TR değerinde zorunlu terim geçiyorsa EN değerinde karşılığı geçer; yasak İngilizce
(`treatment` / `therapy` / `token`) yalnız TR'de karşılığı (tedavi / terapi / token) varsa. Bütün yüzeylerin bütün katalogları.

Neden kapı: "Seans" İngilizcede "treatment / therapy" olursa ürün tıbbi tedavi iddiasında bulunur (sahip kararı 2026-08-08'in tersi);
"Jeton" "token" olursa oturum belirteciyle karışır; ACİL DURDUR'un İngilizcesi sözlükten saparsa güvenlik metni tutarsızlaşır.
İstisna yalnız `terimler.json` → `istisnalar` (anahtar + terim + gerekçe).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import ortak  # noqa: E402

SOZLUK = json.loads((KOK / "i18n" / "terimler.json").read_text(encoding="utf-8"))


def tr_katla(s: str) -> str:
    return str(s).replace("İ", "i").replace("I", "ı").lower()


def ihlaller(tr: dict, en: dict, yuzey: str, sozluk: dict) -> list[str]:
    istisna = {(x["yuzey"], x["anahtar"], x["terim"]) for x in sozluk.get("istisnalar", [])}
    sorun = []
    for k, trv in tr.items():
        env = en.get(k)
        if not isinstance(trv, str) or not isinstance(env, str):
            continue
        tk, ek = tr_katla(trv), env.lower()
        for t in sozluk["terimler"]:
            if re.search(t["tr"], tk) and not re.search(t["en"], ek) and (yuzey, k, t["tr"]) not in istisna:
                sorun.append(f"{yuzey}:{k}: TR '{t['tr']}' içeriyor, EN '{t['en']}' içermiyor → {env!r}")
        for y in sozluk["yasakEn"]:
            if re.search(y["en"], ek) and not re.search(y["yasakIstisnaTr"], tk) and (yuzey, k, y["en"]) not in istisna:
                sorun.append(f"{yuzey}:{k}: EN yasak terim '{y['en']}' (TR'de karşılığı yok) → {env!r}")
    return sorun


@pytest.mark.parametrize("yuzey", list(ortak.KATALOGLAR))
def test_K4_terim_sozlugu(yuzey):
    tr = ortak.duzlestir(ortak.katalog_yukle(yuzey, "tr"))
    en = ortak.duzlestir(ortak.katalog_yukle(yuzey, "en"))
    sorun = ihlaller(tr, en, yuzey, SOZLUK)
    assert not sorun, "\n".join(sorun)


def test_K4_KARSIT_kapi_terim_sapmasini_YAKALAR():
    tr = {"a": "Seansı başlat", "b": "Jeton bakiyesi", "c": "ACİL DURDUR", "d": "Hukuki: tedavisinin yerine geçmez"}
    en = {"a": "Start treatment", "b": "Token balance", "c": "STOP", "d": "does not replace treatment"}
    s = "\n".join(ihlaller(tr, en, "arayuz", SOZLUK))
    assert "arayuz:a" in s and "treatment" in s, "Seans → treatment yakalanmadı"
    assert "arayuz:b" in s, "Jeton → Token yakalanmadı"
    assert "arayuz:c" in s, "ACİL DURDUR → STOP (emergency stop değil) yakalanmadı"
    assert "arayuz:d" not in s, "hukuki 'tedavi' → 'treatment' istisnası tanınmadı"


def test_K4_hastalik_cekimleri_hasta_terimi_DEGIL_ama_hasta_hala_zorunlu():
    # "Hastalığı / hastalığın / hastalığa" (ğ yumuşaması) hastalık demektir, hasta (hayvan) DEĞİL; gerçek "hasta" hâlâ "patient" ister
    tr = {
        "a": "Böbrek Hastalığı",
        "b": "Hastalığın şiddeti",
        "c": "Hastalığa işaret",
        "d": "Hasta seçin",
        "e": "Hastalar",
        "f": "Klinik / hastane adı",
        "g": "Hastanede takip",
    }
    en = {
        "a": "Kidney Disease",
        "b": "Severity of the disease",
        "c": "Points to the disease",
        "d": "Select a patient",
        "e": "Patients",
        "f": "Clinic / animal hospital name",
        "g": "Follow-up at the hospital",
    }
    # "hastane" (hospital) hasta (patient) terimi DEĞİL; yine de "hasta" bulunduğu cümle "patient" ister (kotu aşağıda)
    assert not ihlaller(tr, en, "arayuz", SOZLUK)
    kotu = {"d": "Select an animal", "e": "Animals"}
    s = "\n".join(ihlaller({k: tr[k] for k in kotu}, kotu, "arayuz", SOZLUK))
    assert "arayuz:d" in s and "arayuz:e" in s, "gerçek 'hasta' → patient zorunluluğu kaybolmuş"
