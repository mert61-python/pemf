# -*- coding: utf-8 -*-
"""4B-2.11 (4-B incelemesi A2) — D4.17'nin boş-toplama kapısı yalnız `services` ile ölçülüyor.

Ölçüldü (`_inceleme/kayit/k3_mutasyon.txt`): spec'te `_BIRINCI_TARAF_PAKETLER`'den `ai` ve `ai_hub` çıkarılınca (bu iki paket hoşgörülü
üçüncü-taraf dalına düşer: boş toplama SESSİZ) spec / hookspath / collect_submodules anan 18 dosya **154 passed** — yedi paketin
ikisinde fail-closed kaybı görünmüyor. Kapı her birinci-taraf paket için ayrı ölçer (D4.17/18 testinin KENDİ sürücüsü, GERÇEK toplama).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tests"))

import test_spec_BIRINCI_TARAF_paketleri_TOPLANIR_D417_D418 as d417  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="spec yalnız Windows derlemesinde koşar")


@pytest.mark.parametrize("paket", d417.BIRINCI_TARAF)
def test_KRITIK_HER_birinci_taraf_paket_BOS_toplanirsa_derleme_DURUR(tmp_path, paket):
    p, _ = d417._kos(tmp_path, bos_donsun=paket)
    assert p.returncode != 0, f"{paket} 0 modul dondugu halde spec BASARIYLA bitti (sessiz dusus):\n{p.stdout[-800:]}"
    assert f"'{paket}'" in (p.stdout + p.stderr), (p.stdout + p.stderr)[-800:]
