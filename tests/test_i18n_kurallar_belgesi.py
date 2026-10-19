# -*- coding: utf-8 -*-
"""I18N · KALICI KURAL BELGELERİ (T17) — kökte `CLAUDE.md` (her oturumun ilk okuduğu) iki dil kuralını söyler ve ayrıntıya
(`i18n/KURALLAR.md`) bağlanır; `KURALLAR.md` var olan HER i18n kapı dosyasını anar ve var olmayan dosyaya atıf yapmaz (belge kapılarla
sürüklenmesin: yeni kapı eklenince kılavuza da girer)."""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent


def test_CLAUDE_md_iki_dil_kuralini_soyler_ve_KURALLARa_baglanir():
    claude = (KOK / "CLAUDE.md").read_text(encoding="utf-8")
    assert "tr` + `en` BİRLİKTE" in claude, "yeni anahtarın iki dilde BİRLİKTE ekleneceği kural yok"
    assert "BAYT BAYT" in claude and "kritik-anahtarlar.json" in claude and "terimler.json" in claude
    assert "i18n/KURALLAR.md" in claude and (KOK / "i18n" / "KURALLAR.md").is_file()


def test_KURALLAR_her_i18n_kapisini_anar_olmayana_atif_yapmaz():
    kurallar = (KOK / "i18n" / "KURALLAR.md").read_text(encoding="utf-8")
    # YALNIZ §9 "Kapılar" bölümü — başka bölümdeki geçen ad sayılsaydı §9'dan düşen kapı fark edilmezdi (ölçüldü: mutant sağ kaldı).
    bolum = kurallar[kurallar.index("## 9. Kapılar") : kurallar.index("## 10.")]
    anilan = set(re.findall(r"\btest_i18n_[A-Za-z0-9_]+\.py\b", bolum))
    var = {p.name for p in (KOK / "tests").glob("test_i18n_*.py")}
    assert not (anilan - var), f"KURALLAR.md olmayan kapıya atıf yapıyor: {sorted(anilan - var)}"
    eksik = var - anilan - {"test_i18n_kurallar_belgesi.py"}
    assert not eksik, f"KURALLAR.md §9 bu kapıları anmıyor: {sorted(eksik)}"
