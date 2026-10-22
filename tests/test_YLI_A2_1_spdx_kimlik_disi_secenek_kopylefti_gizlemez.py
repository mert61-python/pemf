# -*- coding: utf-8 -*-
"""YLI-A2.1 — npm kopyleft kapısı (YH D3 `spdx_kopyleft_mu`) lisans KİMLİĞİ olmayan bir `OR` seçeneğini "izin veren seçenek" sayıp
kopylefti GİZLER; lisansı belirsiz girdiler (`UNLICENSED`, `SEE LICENSE IN …`) "lisanssız girdi yok" denetiminden geçer.

ÖLÇÜLEN (A2, `_inceleme/olcum/spdx_dagilim.py`, HEAD 957ba225):
  `GPL-3.0 or later` → False · `GPL-3.0 OR later` → False · `(GPL-2.0 OR later)` → False · `AGPL-3.0 OR Commercial` → False
  (yaprak `kopyleft_mu` dördünde de True). Neden: ayrıştırıcı her belirteci büyük harfe çevirip bağlaç sayar (küçük `or` = `OR`) ve HER
  sözcüğü lisans kimliği kabul eder → `later` / `Commercial` kopyleft olmayan bir "seçenek" olur, `A OR B` "hepsi kopyleft değil" → temiz.
  `UNLICENSED` ve `SEE LICENSE IN LICENSE.md` → kopyleft False VE "doğrulanmadı" değil → kapı ikisinde de YEŞİL kalır.
Bugünkü dört kilitte (782 tekil girdi, 19 farklı dize) bu biçimlerden HİÇBİRİ yok → bugünkü envanter etkilenmez; kapı bu sınıfa KÖR.

Kapı (ürün düzelince yeşil): lisans kimliği olmayan seçenek kaçış sayılmaz (ifade ayrıştırılamaz → metnin tamamı → güvenli taraf);
bağlaçlar SPDX'teki gibi BÜYÜK harfle; belirsiz lisans (boş / doğrulanmadı / UNLICENSED / SEE LICENSE IN) ayrı yardımcıyla yakalanır.
Karşıt: bugünkü 19 dizenin kararı DEĞİŞMEZ (npm kopyleft kümesi boş kalır).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = next(p for p in Path(__file__).resolve().parents if (p / "versions.json").exists())


def _l():
    sys.path.insert(0, str(KOK / "scripts"))
    import lisans_envanteri_uret as l

    return l


@pytest.mark.parametrize(
    "ifade",
    [
        "GPL-3.0 or later",
        "GPL-3.0 OR later",
        "(GPL-2.0 OR later)",
        "AGPL-3.0 OR Commercial",
        "GPL-2.0 OR LicenseRef-Proprietary",
        "MIT AND (GPL-3.0 or later)",
    ],
)
def test_KRITIK_kimlik_olmayan_OR_secenegi_KOPYLEFTI_gizlemez(ifade):
    assert _l().spdx_kopyleft_mu(ifade) is True, (
        f"{ifade!r}: kimlik olmayan seçenek 'izin veren' sayıldı → kopyleft GİZLENDİ"
    )


@pytest.mark.parametrize(
    "ifade", ["UNLICENSED", "SEE LICENSE IN LICENSE.md", "see license in LICENSE", "", "⚠️ doğrulanmadı"]
)
def test_KRITIK_belirsiz_lisans_AYRICA_yakalanir(ifade):
    l = _l()
    assert hasattr(l, "lisans_belirsiz_mu"), (
        "üreticide belirsiz lisans yardımcısı yok — kapı yalnız 'doğrulanmadı' dizesine bakıyor"
    )
    assert l.lisans_belirsiz_mu(ifade) is True, (
        f"{ifade!r} belirsiz sayılmadı → 'lisanssız girdi yok' denetiminden geçer"
    )


@pytest.mark.parametrize(
    "ifade, beklenen",
    [
        ("(BSD-3-Clause OR GPL-2.0)", False),  # node-forge: gerçek seçim hakkı AYNEN
        ("(MIT OR CC0-1.0)", False),
        ("MIT AND OFL-1.1", False),
        ("(AFL-2.1 OR BSD-3-Clause)", False),
        ("LGPL-2.1 OR GPL-3.0", False),
        ("MIT OR Commercial", False),  # kopyleftsiz metin: güvenli taraf da temiz der
        ("GPL-2.0-only WITH Classpath-exception-2.0", True),
        ("MPL-2.0", False),
    ],
)
def test_KARSIT_gercek_SPDX_kararlari_DEGISMEZ(ifade, beklenen):
    assert _l().spdx_kopyleft_mu(ifade) is beklenen, ifade


def test_KARSIT_bugunku_npm_envanteri_ETKILENMEZ():
    l = _l()
    assert l.npm_kopyleft() == []
    if hasattr(l, "lisans_belirsiz_mu"):
        assert [(a, s, li) for a, s, li in l.npm_envanteri() if l.lisans_belirsiz_mu(li)] == []
    for a, s, li in l.npm_envanteri():
        assert l.lisans_belirsiz_mu(li) is False if hasattr(l, "lisans_belirsiz_mu") else True, (a, s, li)
