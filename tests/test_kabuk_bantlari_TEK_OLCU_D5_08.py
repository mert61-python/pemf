# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.08 (B-6.14) — kabuk bantlarının "donanım çalışıyor" ölçüsü TEK KAYNAK (`useDonanimCalisiyor`); bant kümesi AppShell'den TÜRETİLİR.

ÖLÇÜLEN KUSUR: `RecoveryCodeBanner` yalnız `activeTreatment.isActive`e bakıyordu → seanssız sürülen bobin (AI Pro, bobin paneli,
başka istemci) varken yönetimsel bant hastanın üzerinde enerjili bobin varken çiziliyordu. Eski kapı (`test_surum_kaymasi_*`)
yalnız `SurumFarkiBanner`ı adıyla denetliyordu.
"""

from __future__ import annotations

import re
from pathlib import Path

_KOK = Path(__file__).resolve().parents[1]


def _kabuk_bantlari() -> dict[str, Path]:
    """AppShell'in ÇİZDİĞİ her `<XBanner />` / `<XBandi />` → bileşen dosyası (AppShell'in kendi import'undan çözülür; liste
    elle yazılmaz — yeni bant eklenince kapıya kendiliğinden girer)."""
    from c_soyucu import c_soy

    shell = c_soy((_KOK / "apps" / "ui" / "src" / "components" / "ui" / "AppShell.tsx").read_text(encoding="utf-8"))
    importlar = dict(re.findall(r'import\s*\{\s*(\w+)\s*\}\s*from\s*"@/([^"]+)"', shell))
    out = {}
    for ad in sorted(set(re.findall(r"<(\w+(?:Banner|Bandi))\b", shell))):
        assert ad in importlar, f"AppShell {ad} çiziyor ama import yolu çözülemedi"
        out[ad] = _KOK / "apps" / "ui" / "src" / (importlar[ad] + ".tsx")
    return out


def test_KRITIK_D5_08_kabuk_bantlari_donanim_olcusunu_TEK_KAYNAKTAN_alir():
    """D5.08 (B-6.14): donanım/seans durumuna göre susan her yönetimsel bant ölçüyü `useDonanimCalisiyor`dan alır; hiçbir bant kendi
    dar ölçüsünü (`activeTreatment` / `isActive` / `.running`) kurmaz. Susmayan bantlar (ACİL DURDUR mandalı, kayıt DB, STM uyumu)
    bu ölçüyü KULLANMAZ — güvenlik bandı donanım çalışırken gizlenmemeli (Ö.4-Y8)."""
    from c_soyucu import c_soy

    bantlar = _kabuk_bantlari()
    assert len(bantlar) >= 6, f"VAKUM: AppShell'de yalnız {sorted(bantlar)} bant bulundu"
    ihlal, olcu_kullanan = [], []
    for ad, yol in bantlar.items():
        assert yol.exists(), f"{ad} bileşen dosyası YOK: {yol}"
        kod = c_soy(yol.read_text(encoding="utf-8"))
        if re.search(r"\bactiveTreatment\b|\.isActive\b|\?\.running\b|\.running\b", kod):
            ihlal.append(f"{ad}: kendi dar ölçüsünü kuruyor (activeTreatment / isActive / running)")
        if "useDonanimCalisiyor(" in kod:
            olcu_kullanan.append(ad)
    assert not ihlal, "bant donanım ölçüsünü TEK KAYNAKTAN almıyor: " + "; ".join(ihlal)
    assert {"UpdateBanner", "MobileUpdateBanner", "RecoveryCodeBanner", "SurumFarkiBanner"} <= set(olcu_kullanan), (
        f"yönetimsel bant(lar) donanım çalışırken susmuyor: {sorted(set(bantlar) - set(olcu_kullanan))}"
    )
    assert "EstopMandalBandi" in bantlar and "EstopMandalBandi" not in olcu_kullanan, (
        "ACİL DURDUR mandal bandı donanım ölçüsüyle GİZLENİYOR olabilir — güvenlik bandı susmaz (Ö.4-Y8)"
    )
