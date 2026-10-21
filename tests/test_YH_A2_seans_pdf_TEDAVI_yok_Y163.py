# -*- coding: utf-8 -*-
"""YH A2 · Y163 (S-I18N.6, sahip 2026-10-20): seans / hasta PDF'inde kalan "TEDAVİ" sözcükleri "SEANS" olur; İngilizcesi "session"
(treatment / therapy iddiası YOK — terim sözlüğü). Hukuki sorumluluk cümlesindeki "tedavi" DEĞİŞMEZ (2026-08-08 kararının istisnası:
"teşhis ve tedavi" hekimin tıbbi tedavisi — `ai.rapor.kesinTani`).

Kapı iki katlı: (1) PDF üretecinin kullandığı `pdf.*` anahtarları — TR'de "tedavi" yok + "seans" var, EN'de treatment / therapy yok +
"session" var; anahtar ADLARI değişmedi (geri uyum: üreteç aynı anahtarları çağırır); (2) hukuki cümle BAYT BAYT aynı.
Gerçek PDF üretimi (PyMuPDF metni) `test_sunucu_pdf_yedek_durum_istek_dilinde_P1.py` / `test_i18n_pilot_sunucu.py`'de.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KAT = KOK / "apps" / "backend" / "i18n"
URETEC = KOK / "apps" / "backend" / "utils" / "pdf_report_generator.py"

#: Y163 anahtarları → (TR, EN) beklenen değer. Anahtar adları göç öncesinden (`…Tedavi…`) — DEĞİŞTİRİLMEZ.
Y163 = {
    "pdf.baslik.varsayilan": ("PEMF SEANS RAPORU", "PEMF SESSION REPORT"),
    "pdf.bilgi.seansGecmisiRaporu": ("Seans Geçmişi Raporu", "Session History Report"),
    "pdf.hasta.ilkTedavi": ("İlk Seans:", "First Session:"),
    "pdf.hasta.ilkTedaviTarihi": ("İlk Seans Tarihi", "First Session Date"),
    "pdf.hasta.sonTedaviTarihi": ("Son Seans Tarihi", "Last Session Date"),
    "pdf.hasta.tedaviGecmisi": ("SEANS GEÇMİŞİ", "SESSION HISTORY"),
    "pdf.seans.tedaviModu": ("Seans Modu", "Session Mode"),
    "pdf.seans.tedaviSeanslari": ("SEANSLAR", "SESSIONS"),
    "pdf.seans.toplamTedaviSuresi": ("Toplam Seans Süresi", "Total Session Duration"),
}
ALT_BILGI = "pdf.altBilgi.varsayilan"
HUKUKI = ("ai.rapor.kesinTani", "Kesin tanı ve tedavi kararını veteriner hekim verir.")
TEDAVI = re.compile(r"tedavi|TEDAV[İI]|Tedavi")
TREATMENT = re.compile(r"(?i)treatment|therapy|therapeutic")
#: Terim sözlüğünün gerekçeli istisnası (`i18n/terimler.json` → istisnalar): PEMF açılımı ürün adıdır, "tedavi" iddiası değil.
PEMF_ACILIMI = "Pulsed Electromagnetic Field Therapy"


def _duz(o, onek=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _duz(v, f"{onek}.{k}" if onek else k)
    else:
        yield onek, o


def _kat(dil: str) -> dict:
    return dict(_duz(json.loads((KAT / f"{dil}.json").read_text(encoding="utf-8"))))


def test_Y163_anahtarlari_TR_SEANS_EN_session():
    tr, en = _kat("tr"), _kat("en")
    yanlis = [(k, tr.get(k), en.get(k)) for k, (t, e) in Y163.items() if (tr.get(k), en.get(k)) != (t, e)]
    assert not yanlis, yanlis


def test_alt_bilgi_TEDAVI_yok_SEANS_var_EN_session():
    tr, en = _kat("tr")[ALT_BILGI], _kat("en")[ALT_BILGI]
    assert not TEDAVI.search(tr), tr
    assert "seans cihazı" in tr and "Veteriner PEMF Seans Sistemi v1.0" in tr, tr
    assert "{{tarih}}" in tr and "{{tarih}}" in en
    assert not TREATMENT.search(en) and "Session System" in en, en


def test_PDF_ureteci_bu_anahtarlari_KULLANIYOR_ve_pdf_ad_alaninda_TEDAVI_kalmadi():
    kaynak = URETEC.read_text(encoding="utf-8")
    eksik = [k for k in [*Y163, ALT_BILGI] if f'ceviri.t("{k}"' not in kaynak]
    assert not eksik, f"üreteç anahtarı çağırmıyor (ad değişti mi?): {eksik}"
    tr, en = _kat("tr"), _kat("en")
    kalan_tr = {k: v for k, v in tr.items() if k.startswith("pdf.") and TEDAVI.search(str(v))}
    kalan_en = {
        k: v for k, v in en.items() if k.startswith("pdf.") and TREATMENT.search(str(v).replace(PEMF_ACILIMI, ""))
    }
    assert not kalan_tr, kalan_tr
    assert not kalan_en, kalan_en


def test_HUKUKI_cumle_DEGISMEZ():
    """2026-08-08 + Y163 istisnası: "Kesin tanı ve tedavi kararını veteriner hekim verir." hekimin TIBBİ tedavisidir — "seans" OLMAZ."""
    anahtar, cumle = HUKUKI
    assert cumle in _kat("tr")[anahtar]
    assert "treatment decision" in _kat("en")[anahtar]
