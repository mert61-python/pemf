# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.105 orkestratör notu (C2b) — Y8 bekçisi olan jest kolu, BACKEND teyit sözleşmesi değişince de KOŞAR.

ÖLÇÜLEN KÖR NOKTA: istemcinin "yedek acil durdurma adımları teyitten bağımsız" bekçisi (`emergencyStop.A63.yedekKosulsuz`,
`emergencyStop.test.ts`) yalnız `frontend.yml`'de koşar ve o iş akışının yol filtresi `apps/ui/**` idi. Backend'de
`confirmed` / teyit alanını değiştiren bir commit (`api_server.py`: `_emergency_stop_all`, `_esp_yanit_durumu`;
`live_state.py`: WS sözleşmesi) jest'i TETİKLEMİYORDU — Y8 bekçisi tam da riskli değişikliğe kördü.

Kapı DEĞER kapısıdır: push VE pull_request yol filtrelerinin ikisi de bu dosyaları içermeli. (CI bu oturumda koşmaz —
A-43, itme yok; doğrulama yayın öncesi.)
"""

from __future__ import annotations

import re
from pathlib import Path

_YML = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "frontend.yml"
_GEREKLI = ("apps/backend/servers/api_server.py", "apps/backend/servers/live_state.py")


def _yol_filtreleri() -> dict:
    metin = _YML.read_text(encoding="utf-8")
    sonuc, olay = {}, None
    for satir in metin.splitlines():
        m = re.match(r"^  (push|pull_request):\s*$", satir)
        if m:
            olay = m.group(1)
            continue
        if re.match(r"^\S", satir):
            olay = None
        m = re.match(r"^\s+paths:\s*\[(.*)\]\s*$", satir)
        if m and olay:
            sonuc[olay] = [y.strip().strip('"').strip("'") for y in m.group(1).split(",") if y.strip()]
    return sonuc


def test_KRITIK_frontend_yml_yol_filtresi_backend_teyit_dosyalarinda_jest_KOSTURUR():
    filtre = _yol_filtreleri()
    assert set(filtre) == {"push", "pull_request"}, f"aparat: yol filtreleri okunamadi: {filtre}"
    for olay, yollar in filtre.items():
        assert "apps/ui/**" in yollar, f"aparat: {olay} filtresi beklenen bicimde degil: {yollar}"
        eksik = [g for g in _GEREKLI if g not in yollar]
        assert not eksik, f"{olay}: backend teyit sozlesmesi degisince Y8 jest bekcisi KOSMAZ — eksik {eksik}"
