# -*- coding: utf-8 -*-
"""K-5 · GÜVENLİK METİNLERİ (T11) + BAYRAK (T4).

  * `i18n/kritik-anahtarlar.json`'daki HER anahtar kendi yüzeyinin kataloğunda iki dilde DOLU; ACİL DURDUR düğme metninin İngilizcesi
    "EMERGENCY STOP" içerir.
  * Arayüzün çeviriden BAĞIMSIZ yedeği (`apps/ui/src/i18n/kritik.ts::KRITIK_YEDEK`) kataloğun AYNISI (iki dil, birebir) ve listedeki her
    arayüz anahtarını içerir — katalog bozuk / anahtar eksik / i18n başlatılamamış olsa da ACİL DURDUR etiketi boş kalmaz (Ö.4-Y8).
  * `GlobalEmergencyStop` kritik deseni kullanır (`kritikMetin` + `useKritikDil`), react-i18next'e (Suspense / hazır-değil) BAĞLANMAZ.
  * Bayrak tek kaynakta (`i18n/bayrak.json`) ve her yüzey onunla AYNI (`scripts/i18n/bayrak.py --denetle`); test kancası
    `__bayrakTestiAyarla` üretim kodundan ÇAĞRILMAZ.
  * Kapsam defterinde `tamam` olan dosyada listenin `bekleyen` her kritik metni ya listedeki bir anahtarın TR değeridir, ya gerekçeli muaftır
    (`kapsam.muaf_mi`), ya da `birlesikIstisna`'da (şablon / birleştirme tam cümle anahtarlarına bölündü) — parti kritik metni listeye
    eklemeden taşıyamaz.
Davranış tarafı (bozuk katalogda düğme görünür ve çalışır) jest'te: `apps/ui/src/components/ui/__tests__/GlobalEmergencyStop.I18N0.kritik.test.tsx`.
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

from scripts.i18n import bayrak, kapsam, ortak  # noqa: E402

LISTE = json.loads((KOK / "i18n" / "kritik-anahtarlar.json").read_text(encoding="utf-8"))
KRITIK_TS = KOK / "apps" / "ui" / "src" / "i18n" / "kritik.ts"


def yorumsuz_ts(src: str) -> str:
    """Blok yorumlar (çok satırlı) ve satır yorumları soyulur. ⚠️ `//.*` re.S ile koşarsa DOSYA SONUNA kadar yutar (ölçüldü: kapı boş
    metinle karşılaştırıyordu) — iki ayrı geçiş. Dizgi içindeki `//` (URL) için satır yorumu yalnız tırnak / iki nokta sonrası değilse."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)(^|[^:\"'])//.*$", r"\1", src)


def bekleyen_ihlalleri(liste: dict, defter: dict) -> list[str]:
    tr_degerleri: dict[str, set[str]] = {}
    for k in liste["anahtarlar"]:
        duz = ortak.duzlestir(ortak.katalog_yukle(k["yuzey"], "tr"))
        tr_degerleri.setdefault(k["yuzey"], set()).update(
            duz[x] for x in (k["anahtar"], k["anahtar"] + "_one", k["anahtar"] + "_other") if x in duz
        )
    sorun = []
    for b in liste["bekleyen"]:
        kayit = defter["dosyalar"].get(b["dosya"], {})
        if kayit.get("durum") != "tamam":
            continue
        yuzey = kayit.get("yuzey", "")
        birlesik = {x.get("once") for x in kayit.get("birlesikIstisna", [])}
        if b["ham"] in tr_degerleri.get(yuzey, set()) or b["metin"] in tr_degerleri.get(yuzey, set()):
            continue
        if b["metin"] in birlesik or kapsam.muaf_mi(defter, b["dosya"], b["metin"]):
            continue
        sorun.append(f"{b['dosya']}:{b['satir']} kritik metin listede değil: {b['metin']!r}")
    return sorun


def test_K5_tamam_dosyada_bekleyen_kritik_metin_listede():
    sorun = bekleyen_ihlalleri(LISTE, kapsam.defter_oku(KOK))
    assert not sorun, "kritik metin taşındı ama i18n/kritik-anahtarlar.json'a eklenmedi:\n" + "\n".join(sorun)


def test_K5_KARSIT_bekleyen_denetimi_listesiz_tasimayi_YAKALAR():
    defter = kapsam.defter_oku(KOK)
    sahte = {**LISTE, "anahtarlar": []}
    sorun = bekleyen_ihlalleri(sahte, defter)
    assert any("GlobalEmergencyStop.tsx" in s and "Acil durdurma gönderiliyor" in s for s in sorun), sorun


def yedek_tablosu() -> dict[str, dict[str, str]]:
    """kritik.ts → {"tr": {anahtar: metin}, "en": {...}} (JSON uyumlu dizgi değişmezleri; çok satırlı değer desteklenir)."""
    metin = KRITIK_TS.read_text(encoding="utf-8")
    bas = metin.index("export const KRITIK_YEDEK")
    son = metin.index("} as const;", bas)
    govde = metin[bas:son]
    i_tr, i_en = govde.index("\n  tr: {"), govde.index("\n  en: {")
    cift = re.compile(r'"([\w.]+)":\s*"((?:[^"\\]|\\.)*)"')
    return {
        "tr": {k: json.loads(f'"{v}"') for k, v in cift.findall(govde[i_tr:i_en])},
        "en": {k: json.loads(f'"{v}"') for k, v in cift.findall(govde[i_en:])},
    }


def test_K5_liste_bos_degil_ve_her_kayit_tam():
    assert LISTE["anahtarlar"], "kritik liste boş"
    for k in LISTE["anahtarlar"]:
        assert {"yuzey", "anahtar", "aciklama"} <= set(k), k
        assert k["yuzey"] in ortak.KATALOGLAR, k


@pytest.mark.parametrize("dil", ortak.DILLER)
def test_K5_her_kritik_anahtar_iki_dilde_dolu(dil):
    eksik = []
    for k in LISTE["anahtarlar"]:
        duz = ortak.duzlestir(ortak.katalog_yukle(k["yuzey"], dil))
        if not ortak.anahtar_kullanilabilir(k["anahtar"], duz):
            eksik.append(f"{k['yuzey']}:{k['anahtar']}")
            continue
        degerler = [duz[x] for x in (k["anahtar"], k["anahtar"] + "_one", k["anahtar"] + "_other") if x in duz]
        if not all(str(v).strip() for v in degerler):
            eksik.append(f"{k['yuzey']}:{k['anahtar']} (boş)")
    assert not eksik, f"{dil} kataloğunda eksik / boş kritik anahtar: {eksik}"


def test_K5_ACIL_DURDUR_ingilizcesi_EMERGENCY_STOP():
    en = ortak.duzlestir(ortak.katalog_yukle("arayuz", "en"))
    assert "EMERGENCY STOP" in en["guvenlik.acilDurdur.dugme"]
    tr = ortak.duzlestir(ortak.katalog_yukle("arayuz", "tr"))
    assert "ACİL DURDUR" in tr["guvenlik.acilDurdur.dugme"]


def test_K5_arayuz_yedegi_katalogun_AYNISI_ve_listeyi_kapsar():
    yedek = yedek_tablosu()
    for dil in ortak.DILLER:
        duz = ortak.duzlestir(ortak.katalog_yukle("arayuz", dil))
        for k, v in yedek[dil].items():
            assert duz.get(k) == v, f"KRITIK_YEDEK[{dil}][{k}] katalogdan FARKLI: {v!r} ≠ {duz.get(k)!r}"
    yedek_kokleri = {re.sub(r"_(one|other)$", "", k) for k in yedek["tr"]}
    for k in LISTE["anahtarlar"]:
        if k["yuzey"] == "arayuz" and k["anahtar"].startswith("guvenlik.acilDurdur."):
            assert k["anahtar"] in yedek_kokleri, f"ACİL DURDUR kritik anahtarı yedekte YOK: {k['anahtar']}"


def test_K5_ACIL_DURDUR_dugmesi_kritik_deseni_kullanir_react_i18nexte_baglanmaz():
    src = (KOK / "apps/ui/src/components/ui/GlobalEmergencyStop.tsx").read_text(encoding="utf-8")
    kod = yorumsuz_ts(src)
    assert "kritikMetin(" in kod and "useKritikDil(" in kod
    assert "useTranslation" not in kod and "react-i18next" not in kod, (
        "ACİL DURDUR react-i18next'e bağlanmamalı (Suspense / hazır-değil)"
    )
    assert "Suspense" not in kod


def test_K5_bayrak_tek_kaynakta_ve_yuzeyler_ayni():
    sorun = bayrak.denetle(KOK)
    assert not sorun, "\n".join(sorun)


def test_K5_test_kancasi_uretim_kodunda_cagrilmaz():
    ihlal = []
    for y in ("arayuz", "site", "dema"):
        for f in ortak.yuzey_dosyalari(y, KOK):
            metin = yorumsuz_ts((KOK / f).read_text(encoding="utf-8"))
            for m in re.finditer(r"__bayrakTestiAyarla\s*\(", metin):
                onceki = metin[: m.start()]
                if not re.search(r"export function\s*$", onceki[-40:]):
                    ihlal.append(f)
    assert not ihlal, f"bayrak test kancası üretim kodunda çağrılıyor: {sorted(set(ihlal))}"


def test_K5_KARSIT_yedek_ayristirici_KOR_DEGIL():
    yedek = yedek_tablosu()
    assert yedek["tr"].get("guvenlik.acilDurdur.dugme") == "🚨 ACİL DURDUR"
    assert yedek["en"].get("guvenlik.acilDurdur.dugme") == "🚨 EMERGENCY STOP"
    assert len(yedek["tr"]) == len(yedek["en"]) >= 10
