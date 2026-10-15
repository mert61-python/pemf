# Author: mertaygn, cglrgrkn
"""CH4 · Y154 aparatı — akım sensörü AÇIK kapıları.

Y154 (sahip, 2026-10-15): akım sensörü (ACS712) varsayılan olarak TÜMDEN KAPALI (`apps/backend/utils/akim_olcumu.py`,
`PEMF_AKIM_OLCUMU`). Sensör ileride takılıp doğrulanırsa açılabilsin diye TD5 / D2.39 / D1.67 / ESP akım yolları KALDIRILMADI; o yolları
koruyan kapılar bu aparatla bayrak AÇIKKEN koşar. Kapalı sözleşmenin kapısı: `tests/test_CH4_akim_sensoru_TUMDEN_KAPALI_Y154.py`.

Kullanım (test modülünde): `from akim_olcumu_aparati import akim_olcumu_acik  # noqa: F401` — autouse, modülün her testinde etkin.
⚠️ `monkeypatch` İSTEMEZ: ortam elle kaydedilip geri yüklenir (hafıza: conftest-autouse-fiksturu-monkeypatch-istemez — yıkım sırası
nöbet fikstürlerini etkilemesin; testin kendi `monkeypatch`i bu aparattan SONRA kurulur ve önce geri alınır).
"""

from __future__ import annotations

import os

import pytest

_DEGISKEN = "PEMF_AKIM_OLCUMU"


@pytest.fixture(autouse=True)
def akim_olcumu_acik():
    once = os.environ.get(_DEGISKEN)
    os.environ[_DEGISKEN] = "1"
    try:
        yield
    finally:
        if once is None:
            os.environ.pop(_DEGISKEN, None)
        else:
            os.environ[_DEGISKEN] = once
