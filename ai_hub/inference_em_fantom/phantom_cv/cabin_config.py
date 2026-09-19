# Author: mertaygn, cglrgrkn
"""KABUK + PROFİL KİMLİĞİ — gerçek uygulama `ai_hub/cv_ortak/cabin_config.py`de.

2026-09-19'a kadar bu dosya 367 satırdı ve diğer profildekiyle **366 satırı aynıydı**;
tek fark `mqtt_client_id` varsayılanıydı. Gövde ortak pakete taşındı, burada yalnız
profilin kendine ait olan iki şey kaldı.

⚠️ VARSAYILAN YAML BURADA KALMAK ZORUNDA. İki profilin `cabin_config_example.yaml`ı
FARKLI (192 vs 206 satır). Ortak modül taşındığı için oradaki
`Path(__file__).parent` artık `cv_ortak/`u gösterir ve orada örnek YAML YOKTUR.
`load_cabin_config(None)` ÜRETİMDE dört yerden çağrılıyor:
    apps/backend/servers/ai_router.py:985,1009 · ai_service/predictors.py:104,115
Bu kabuk olmasaydı dördü de `FileNotFoundError` ile düşerdi.

Kapı: `tests/test_cv_ortak_tek_uygulama.py`
"""

from __future__ import annotations

import os
from pathlib import Path

from ...cv_ortak.cabin_config import *  # noqa: F401,F403
from ...cv_ortak.cabin_config import CabinConfig
from ...cv_ortak.cabin_config import load_cabin_config as _ortak_yukle

_DIR = Path(__file__).parent.resolve()

#: ⚠️ PROFİL-BAŞINA FARKLI — ortak pakete taşınamaz.
DEFAULT_CONFIG_YAML = _DIR / "cabin_config_example.yaml"

#: Profil kimliği. ⚠️ Yayın anında `benzersiz_client_id()` süreç eki koyar —
#: sabit kimlik brokerda ikinci bağlantıyı düşürür.
VARSAYILAN_CLIENT_ID = "phantom_cv_pipeline"


def load_cabin_config(
    yaml_path: str | os.PathLike | None = None,
    *,
    varsayilan_yaml: str | os.PathLike | None = None,
    varsayilan_client_id: str = VARSAYILAN_CLIENT_ID,
) -> CabinConfig:
    """Ortak yükleyiciyi BU PROFİLİN varsayılanlarıyla çağırır."""
    return _ortak_yukle(
        yaml_path,
        varsayilan_yaml=varsayilan_yaml or DEFAULT_CONFIG_YAML,
        varsayilan_client_id=varsayilan_client_id,
    )
