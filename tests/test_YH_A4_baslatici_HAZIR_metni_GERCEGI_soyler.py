# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YH · A4 (istem 50 · Tezgâh-2 listesi 4): başlatıcının kurulum bitince yazdığı durum satırı GERÇEĞİ söyler.

ÖLÇÜLEN (tezgâh 13 Kasım 2026): durum satırı "hazır — tarayıcıda açıldı" (EN "ready — opened in browser") diyordu; oysa başlatıcı
dış tarayıcı AÇMAZ — backend hazır olunca uygulamayı KENDİ penceresinde açar (`kabuk.rs::on_backend_ready` → `open_app_window`,
Tauri web görünümü). Kullanıcı ekranda tarayıcı arıyordu (hafıza "Düğme etiketi gerçeği söylesin"). YALNIZ metin değişti; başlatıcı
kabukları (KP-6 alanı) DEĞİŞMEDİ.
Kapı GERÇEĞE bağlı: metin "uygulama penceresi" der VE kaynakta hazır olunca açılan şey `open_app_window`dır (başlatıcı ileride dış
tarayıcı açmaya dönerse metinle birlikte bu kapı da kırmızı olur). Üretilmiş katalog (`i18n_katalog.js`) eşitliği K-6 kapısında.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def _ready(dil: str) -> str:
    return json.loads((KOK / "launcher" / "i18n" / f"{dil}.json").read_text(encoding="utf-8"))["ui"]["ready"]


def _hazir_govdesi() -> str:
    kaynak = (KOK / "launcher" / "app" / "src" / "kabuk.rs").read_text(encoding="utf-8")
    i = kaynak.index("fn on_backend_ready(")
    j = kaynak.index("\nfn ", i + 1)
    return "\n".join(s for s in kaynak[i:j].splitlines() if not s.lstrip().startswith("//"))


def test_KRITIK_hazir_olunca_acilan_UYGULAMA_PENCERESI_dis_tarayici_DEGIL():
    govde = _hazir_govdesi()
    assert "open_app_window(" in govde, (
        "aparat: hazır olunca uygulama penceresi açılmıyor mu? (kaynak değişti — metni yeniden ölç)"
    )
    assert not re.search(r"\bopen::that|opener|open_url|ShellExt|start\s+http", govde), (
        "hazır olunca DIŞ tarayıcı açılıyor"
    )


def test_KRITIK_durum_satiri_tarayici_DEMEZ_uygulama_penceresi_der():
    tr, en = _ready("tr"), _ready("en")
    assert "tarayıcı" not in tr.lower() and "uygulama penceresi" in tr, tr
    assert "browser" not in en.lower() and "app window" in en.lower(), en
