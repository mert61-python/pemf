# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""JEST TEST ZAMAN ASIMI — varsayilan 5 sn SOGUK CI'da yetmiyor (2026-09-15).

OLCULEN ARIZA (kosu 34998091761). `frontend-ci` kirmizi dondu:

    AiProPanelArastirma.test.tsx:109
    thrown: "Exceeded timeout of 5000 ms for a test."

AYNI test bu makinede 273 ms suruyor (jest --json ile olculdu; dosyanin 16 testi TOPLAM
795 ms). 18 katlik fark runner'in yavasligiyla aciklanamaz. Iki olculen sebep:

  1. `.github/workflows/frontend.yml` npm'i onbellege aliyor (`cache: npm`) ama JEST
     TRANSFORM onbellegini almiyor -> her CI kosusu expo/react-native agacini SOGUKTAN
     babel'den geciriyor.
  2. expo'nun `fetch` global'i TEMBEL bir getter (expo/src/winter/installGlobal.ts:44).
     Ilk dokunus expo-modules-core -> ExpoFetchModule -> fetch zincirini require ediyor;
     CI log'unda bu zincir aynen goruldu.

Yani sure test MANTIGINDA degil, ILK DOKUNUSTAKI transform'da harcaniyor. Faturayi o an
hangi test kosuyorsa o oder -> "suclu" test kosudan kosuya DEGISIR. Bu yuzden tek bir
teste `timeout` parametresi eklemek arizayi cozmez, yalnizca baska bir teste tasir.

⚠️ NEDEN "kararsiz test" DEYIP GECILMEDI: hata bir IDDIA hatasi degil ZAMAN ASIMI idi,
yerel sure olculdu ve CI log'unda mekanizma goruldu. Bkz. bellek: yarim-goc arizasinda
"kararsiz test" varsayimi bir VERI KAYBINI aylarca gizlemisti.

BU KAPI: yapilandirmanin `testTimeout` tasidigini ve degerin makul bir ARALIKTA kaldigini
olcer. Ust sinir da vardir: zaman asimini surekli yukseltmek, GERCEK bir sonsuz beklemeyi
(fake-timer ile asilan promise) gorunmez kilar.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_JEST_CONFIG = _KOK / "apps" / "ui" / "jest.config.js"

#: Alt sinir — soguk transform penceresini kapatacak kadar. 5000 (jest varsayilani) CI'da
#: OLCULEREK yetersiz bulundu.
_EN_AZ_MS = 15_000
#: Ust sinir — bunun uzerine cikmak "bir yerde sonsuz bekleme var" demektir ve zaman asimini
#: yukseltmek onu GIZLER. Gercek is 795 ms olculdugune gore 30 sn zaten 37 kat paydir.
_EN_COK_MS = 30_000


def _kod() -> str:
    """jest.config.js'in YORUMSUZ hâli.

    ⚠️ ZORUNLU. Bu dosyanin BASLIK YORUMU "jest-expo preset (RN transform)" cumlesini
    iceriyor; ham metinde `"preset" in metin` araman, anahtar SILINSE BILE True doner.
    Mutasyonla olculdu (2026-09-15): `preset:` satiri silindi, kapi YESIL kaldi.
    Bu deponun tekrar eden hata sinifi — "yorum kapiyi kandirdi".
    """
    metin = _JEST_CONFIG.read_text(encoding="utf-8")
    return "\n".join(re.sub(r"//.*$", "", s) for s in metin.splitlines())


def _testtimeout_degeri() -> int | None:
    m = re.search(r"\btestTimeout\s*:\s*([0-9_]+)", _kod())
    return int(m.group(1).replace("_", "")) if m else None


def test_KRITIK_jest_testTimeout_TANIMLI():
    """Tanimli degilse jest 5000 ms'e duser — CI'da olculen arizanin ta kendisi."""
    assert _JEST_CONFIG.exists(), f"jest yapilandirmasi yok: {_JEST_CONFIG}"
    deger = _testtimeout_degeri()
    assert deger is not None, (
        "apps/ui/jest.config.js icinde `testTimeout` YOK -> jest varsayilan 5000 ms kullanir. "
        "2026-09-15'te (kosu 34998091761) tam bu deger yuzunden frontend-ci kirmizi dondu: "
        "sure test mantiginda degil, SOGUK CI'daki ilk babel transform'unda harcaniyor."
    )


def test_KRITIK_testTimeout_soguk_CI_icin_YETERLI():
    deger = _testtimeout_degeri()
    assert deger is not None, "once test_KRITIK_jest_testTimeout_TANIMLI'ya bakin"
    assert deger >= _EN_AZ_MS, (
        f"testTimeout={deger} ms — soguk CI transform penceresi icin DAR. "
        f"En az {_EN_AZ_MS} ms olmali (olculen gercek is: 16 test / 795 ms)."
    )


def test_KARSIT_KANIT_testTimeout_SINIRSIZ_DEGIL():
    """⚠️ ASIRI-GENISLEME KAPISI.

    "Kirmizi mi? zaman asimini buyut" refleksi, fake-timer ile asilan bir promise'i
    (yani GERCEK bir sonsuz beklemeyi) gorunmez kilar — test 5 sn yerine 10 dakika
    bekler ve CI dakikasi yakar. Tavan, arizayi hala yakalanabilir tutar.
    """
    deger = _testtimeout_degeri()
    assert deger is not None, "once test_KRITIK_jest_testTimeout_TANIMLI'ya bakin"
    assert deger <= _EN_COK_MS, (
        f"testTimeout={deger} ms — COK BUYUK. Bu noktada zaman asimi bir kapi degil, "
        f"bir orttur: sonsuz bekleyen bir test de 'gecerli' gorunur. "
        f"Tavan {_EN_COK_MS} ms. Daha fazlasi gerekiyorsa once NEDEN yavasladigini olcun."
    )


@pytest.mark.parametrize("anahtar", ["preset", "setupFilesAfterEnv", "moduleNameMapper", "transformIgnorePatterns"])
def test_KARSIT_KANIT_yapilandirma_BOSALTILMADI(anahtar):
    """Asiri-genisleme korumasi: yukaridaki iki test, yapilandirmayi SADELESTIREREK de
    yesil yapilabilirdi (preset/transform kurallarini silip yalniz `testTimeout` birakmak).
    O hâlde RN transform'u bozulur ve testler ya hic kosmaz ya da yanlis modulu yukler.

    ⚠️ Capa YORUMSUZ koda pinli (`_kod()`), ham metne DEGIL — bkz. oradaki aciklama.
    """
    assert re.search(rf"^\s*{anahtar}\s*:", _kod(), re.M), (
        f"apps/ui/jest.config.js icinden `{anahtar}` anahtari KAYBOLMUS — o olmadan jest-expo "
        f"transform zinciri kurulmaz ve `testTimeout` tek basina hicbir sey ifade etmez"
    )
