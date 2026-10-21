# -*- coding: utf-8 -*-
"""I18NI-A2.1 KALICI KAPI (14-I18N-INCELEME): TÜRKÇE GERİLEMESİ — göç öncesi TR tabanının (`cikar.py --taban`, `c1e098ef`) HER metni bugün
ya kaynakta (muaf / genel / kod), ya dosyanın kullandığı bir anahtarın TR değerinde, ya gerekçeli `birlesikIstisna`'da karşılanır
(`katalog.py taban`). Göç sonunda dedektör kalıcı kapı DEĞİLDİ ve uçta 3 grupta 180 SAHTE kırmızı veriyordu (12 ara katman JSON gövdesi
`{"detail":"…"}` → `_json_detay(ceviri.t(…))`, 168 launcher `index.html`'in yayındaki EN sözlük metni); argümansız çağrı `[OK] (0 dosya)`
diyordu; `birlesikIstisna.sonra` doğrulanmıyordu (3 girdi ilgisiz anahtar gösteriyordu).
Taban depo DIŞINDA: `PEMF_I18N_TABAN` ya da `ortak.varsayilan_taban()` (`~/Desktop/DENETIM/I18N/…`; kullanıcı adı GÖMÜLMEZ); yoksa gerekçeyle
ATLANIR (CI'da koşmaz; göç / inceleme / yayın hazırlığı makinesinde koşar — kafesli koşucuda tabanı açıkça verin).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


def _kok() -> Path:
    p = Path(__file__).resolve().parent
    while not (p / "i18n" / "kapsam.json").exists():
        p = p.parent
    return p


KOK = _kok()
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import katalog, ortak  # noqa: E402

TABAN = ortak.varsayilan_taban()  # PEMF_I18N_TABAN > ~/Desktop/DENETIM/I18N/taban-tr-metinler.json
pytestmark = pytest.mark.skipif(not TABAN.is_file(), reason=f"TR tabanı yok ({TABAN}) — depo dışında")
DEFTER = json.loads((KOK / "i18n" / "kapsam.json").read_text(encoding="utf-8"))


def test_taban_TR_metinlerinin_HEPSI_karsilanir_butun_gruplar():
    dosyalar = sorted(DEFTER["dosyalar"])
    sorun = katalog.taban_karsilastir(KOK, dosyalar, TABAN)
    assert not sorun, f"{len(sorun)} taban TR metni karşılanmıyor (gerileme ya da dedektör gürültüsü):\n" + "\n".join(
        sorun[:15]
    )


def test_bos_cagri_YESIL_DEMEZ(capsys):
    assert katalog.main(["taban", "--taban", str(TABAN)]) != 0, (
        "dosya / grup verilmeyen `taban` çağrısı [OK] dememeli (0 dosya)"
    )


def test_birlesik_istisna_sonra_anahtarlari_VAR_ve_DOSYADA_kullanilir():
    sorun = []
    for f, k in DEFTER["dosyalar"].items():
        tr = ortak.duzlestir(ortak.katalog_yukle(k["yuzey"], "tr")) if k.get("birlesikIstisna") else {}
        kaynak = (KOK / f).read_text(encoding="utf-8") if k.get("birlesikIstisna") else ""
        for b in k.get("birlesikIstisna", []):
            for a in b.get("sonra", []):
                if not ortak.anahtar_kullanilabilir(a, tr):
                    sorun.append(f"{f}: '{b.get('once')}' → {a} katalogda YOK")
                elif a not in kaynak:
                    sorun.append(f"{f}: '{b.get('once')}' → {a} dosyada KULLANILMIYOR")
    assert not sorun, "birlesikIstisna gerekçesi doğrulanmıyor:\n" + "\n".join(sorun)
