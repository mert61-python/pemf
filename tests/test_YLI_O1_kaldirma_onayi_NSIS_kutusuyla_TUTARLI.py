# -*- coding: utf-8 -*-
"""YLI-O.1 (YLI bağımsız inceleme, orkestratör) · launcher "Kaldır" onayı NSIS kaldırıcısının kutusuyla ÇELİŞMEZ.

Launcher'ın "Kaldır" düğmesi (`ui.uninBody` onayı → `uninstall` komutu) NSIS `uninstall.exe`'yi başlatır; kaldırıcı "Uygulama verilerini sil" /
"Delete the application data" kutusunu sunar ve kutu İŞARETSİZKEN (varsayılan) indirilen çalışma zamanını, modelleri ve önbelleği KORUR
(`hooks.nsi` POSTUNINSTALL, `PEMF_veriSilIsaretsiz`). Onay metni ise koşulsuz "İndirilen uygulama ve AI modelleri silinecek." / "The downloaded app
and AI models will be removed." diyordu (07-29 metni; 08-04 kutu düzeltmesinden beri çelişki) → kullanıcı iki ekranda iki ayrı şey okuyordu.

Kural: onayın ilk paragrafı silmeyi KUTUYA bağlar ve kutuyu kaldırıcının kendi iletisindeki adıyla anar (iki dilde); koşulsuz silme cümlesi yok.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
HOOKS = (KOK / "launcher/app/windows/hooks.nsi").read_text(encoding="utf-8")
#: NSIS dil kodu → launcher katalog dili
DILLER = {"tr": "1055", "en": "1033"}
KOSULSUZ = {"tr": re.compile(r"modelleri silinecek\b"), "en": re.compile(r"models will be removed\b")}


def _kutu_adi(kod: str) -> str:
    m = re.search(rf'^LangString PEMF_veriSilIsaretsiz {kod} "PEMF: \'([^\']+)\'', HOOKS, re.M)
    assert m, f"hooks.nsi PEMF_veriSilIsaretsiz {kod} bulunamadı"
    return m.group(1)


def _ilk_paragraf(dil: str) -> str:
    ui = json.loads((KOK / f"launcher/i18n/{dil}.json").read_text(encoding="utf-8"))["ui"]
    return ui["uninBody"].split("\n\n", 1)[0]


def test_FIKSTUR_kaldirici_kutu_ISARETSIZKEN_indirilenleri_KORUR():
    # Metnin dayandığı davranış: runtime / ai_models yalnız kutu işaretliyken (= 1) silinir (yorum satırları sayılmaz).
    kod = "\n".join(s for s in HOOKS.splitlines() if not s.lstrip().startswith(";"))
    dal = kod.index("${ElseIf} $DeleteAppDataCheckboxState = 1")
    assert kod.index('RMDir /r "$INSTDIR\\runtime"') > dal and kod.index('RMDir /r "$INSTDIR\\ai_models"') > dal
    assert "$(PEMF_veriSilIsaretsiz)" in kod[dal:]


@pytest.mark.parametrize("dil", sorted(DILLER))
def test_KRITIK_O1_kaldirma_onayi_silmeyi_KUTUYA_baglar_kutuyu_NSIS_adiyla_anar(dil):
    ilk = _ilk_paragraf(dil)
    kutu = _kutu_adi(DILLER[dil])
    assert f"'{kutu}'" in ilk, f"{dil}: onay kutuyu kaldırıcının adıyla ('{kutu}') anmıyor: {ilk!r}"
    assert not KOSULSUZ[dil].search(ilk), f"{dil}: onay hâlâ koşulsuz silme diyor: {ilk!r}"


def test_KRITIK_O1_uretilmis_katalog_YENI_metni_tasir():
    js = (KOK / "launcher/app/ui/i18n_katalog.js").read_text(encoding="utf-8")
    for dil in DILLER:
        assert json.dumps(_ilk_paragraf(dil), ensure_ascii=False)[1:-1] in js, (
            f"{dil}: i18n_katalog.js üretilmemiş (launcher_uret.py)"
        )
