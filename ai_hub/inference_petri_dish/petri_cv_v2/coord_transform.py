# Author: mertaygn, cglrgrkn
"""KABUK — gerçek uygulama `ai_hub/cv_ortak/coord_transform.py`de (A2, 2026-09-19).

Bu dosya 2026-09-19'a kadar 326 satırlık bir **kopyaydı**; diğer profildekiyle
MD5 birebir aynıydı. `coord_transform` = bobin/hedef geometrisi — bir taraftaki
düzeltme diğerinde kalmazdı. Tek uygulamaya toplandı.

⚠️ Bu dosya SİLİNMEDİ çünkü import yolu sözleşmedir: `pipeline.py` `from
.coord_transform import ...` yazıyor ve `ai_service/predictors.py` ile
`apps/backend/servers/ai_router.py` profil paketinden içe aktarıyor.

Kapı: `tests/test_cv_ortak_tek_uygulama.py`
"""

from __future__ import annotations

from ...cv_ortak.coord_transform import *  # noqa: F401,F403
