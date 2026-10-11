# Author: mertaygn, cglrgrkn
"""KABUK + PROFİL KİMLİĞİ (petri v2) — gerçek uygulama `ai_hub/cv_ortak/cabin_config.py`de.

AI-2 (2026-10-12): hocanın `petri_cv_v2/cabin_config.py` KOPYASI ALINMADI — tek farkı `multiwell:` bölümüydü ve o
bölüm `cv_ortak`a taşındı (plan §3.4, A2). Burada yalnız profilin kendine ait iki şey var: varsayılan YAML
(`cabin_config_v2.yaml` = saha kabin ölçüsü + hocanın `multiwell:` bölümü) ve MQTT profil kimliği.

⚠️ VARSAYILAN YAML BURADA KALMAK ZORUNDA: ortak modülün `Path(__file__).parent`ı `cv_ortak/`u gösterir ve orada YAML
YOKTUR; `load_cabin_config(None)` üretimde yükleyicilerden çağrılır (ai_router `_yukle_em_petri_cv`,
ai_service `predictors._load_em_petri`).

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
DEFAULT_CONFIG_YAML = _DIR / "cabin_config_v2.yaml"

#: Profil kimliği. ⚠️ Yayın anında `benzersiz_client_id()` süreç eki koyar —
#: sabit kimlik brokerda ikinci bağlantıyı düşürür.
VARSAYILAN_CLIENT_ID = "petri_cv_pipeline"


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
