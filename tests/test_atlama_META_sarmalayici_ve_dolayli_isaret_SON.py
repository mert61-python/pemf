"""SON-A1.57 (22 · A1b) — D5 META kapısı (`test_atlama_ZORUNLU_kipte_DUSER_D5.tara`) dolaylı ham atlama biçimlerini de görmeli.

C135 TUR 3b'nin bağımsız çürütmesinde talimattaki biçimler (değişkene atanmış `skipif`, `unittest.skipIf`, `importorskip` takma adı, koşullu
`pytestmark` listesi) YAKALANDI; şu dört biçim GÖRÜLMÜYORDU (sentetik kaynak — yalnız AST, kod KOŞMAZ):
  * koşulsuz atlayan yerel sarmalayıcı `def _atla(n): pytest.skip(n)` eser koşuluyla çağrılınca,
  * aynı sarmalayıcı `lambda`,
  * `functools.partial(pytest.mark.skipif, <eser koşulu>)`,
  * `pytest.mark.skipif(**{"condition": <eser koşulu>, …})`.
Hepsi ZORUNLU kipte de atlar (yayın öncesi süit eser eksik makinede YEŞİL biter). KARŞIT: ZORUNLU'ya bağlı sarmalayıcı (`if capraz.ZORUNLU:
pytest.fail(...)` sonra skip — depodaki `_pwsh_gerekli` / `_derleyici` / `gitleaks_ikili.gerekli` biçimi) ve eser DIŞI koşulla çağrı ham DEĞİL.
"""

from __future__ import annotations

import pytest
from test_atlama_ZORUNLU_kipte_DUSER_D5 import tara

_BAS = "import shutil, os, functools\nimport pytest\nimport capraz\nfrom pathlib import Path\nP = Path('x')\n"

_HAM = {
    "sarmalayici_def": _BAS
    + "def _atla(n):\n    pytest.skip(n)\ndef test_a():\n    if not P.exists():\n        _atla('eser yok')\n",
    "sarmalayici_lambda": _BAS
    + "_atla = lambda n: pytest.skip(n)\ndef test_a():\n    if not P.exists():\n        _atla('eser yok')\n",
    "partial_skipif": _BAS
    + "_yok = functools.partial(pytest.mark.skipif, not P.exists())\n@_yok(reason='eser yok')\ndef test_a():\n    pass\n",
    "skipif_kwargs_sozluk": _BAS
    + "@pytest.mark.skipif(**{'condition': not P.exists(), 'reason': 'eser yok'})\ndef test_a():\n    pass\n",
}
_BAGLI = {
    "KARSIT_zorunluya_bagli_sarmalayici": _BAS
    + "def _gerekli():\n    if capraz.ZORUNLU:\n        pytest.fail('zorunlu')\n    pytest.skip('yok')\ndef test_a():\n    if not P.exists():\n        _gerekli()\n",
    "KARSIT_eser_disi_kosulla_sarmalayici": _BAS
    + "def _atla(n):\n    pytest.skip(n)\ndef test_a():\n    if os.name != 'nt':\n        _atla('yalniz Windows')\n",
    "KARSIT_partial_eser_disi": _BAS
    + "_yok = functools.partial(pytest.mark.skipif, os.name != 'nt')\n@_yok(reason='platform')\ndef test_a():\n    pass\n",
}


@pytest.mark.parametrize("bicim", list(_HAM))
def test_KRITIK_META_dolayli_HAM_atlamayi_GORUR(bicim):
    assert tara(_HAM[bicim], f"tests/sentetik_{bicim}.py"), (
        f"META kapısı '{bicim}' biçimindeki eser yokluğuna bağlı HAM atlamayı GÖRMEDİ — ZORUNLU kipte de atlar"
    )


@pytest.mark.parametrize("bicim", list(_BAGLI))
def test_KARSIT_META_bagli_ve_eser_disi_dolayliyi_SAYMAZ(bicim):
    assert not tara(_BAGLI[bicim], f"tests/sentetik_{bicim}.py"), f"KARŞIT '{bicim}' HAM sayıldı (sahte kırmızı)"
