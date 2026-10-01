# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.14 · B-2.17 — BOZUK sayısal bayrak backend içe aktarımını (dolayısıyla ACİL DURDUR ucunu) ÖLDÜRMEZ.

ÖLÇÜLEN (DENETİM-02, 02-2): `jeton.py` / `entitlement.py` sayısal bayrakları modül düzeyinde
korumasız `int(os.getenv(...))` / `float(...)` ile okuyordu. Tek bir yazım hatası (`elli`, `4,5`)
`ai_router` içe aktarımında `ValueError` atar; `api_server` `ai_router`'ı modül düzeyinde içe
aktardığı için backend HİÇ açılmaz → E-stop ucu YOK (7/7 bayrak ölçüldü). Ö.4-Y8 ruhu: E-stop'un
VAR OLMASI bir ticari ayarın ayrıştırılmasına bağlı olamaz.

⚠️ Aynı sınıftan 8. bayrak bu maddede ölçülerek eklendi: `ai_client._TIMEOUT`
(`PEMF_AI_SERVICE_TIMEOUT`) — `ai_router` onu da modül düzeyinde içe aktarıyor.

Her bayrak AYRI ALT SÜREÇTE (conftest yolları ve önbellekli modüller YOK): gerçek
`import servers.api_server` → `POST /api/hardware/emergency_stop` (sahte donanım, ağ yok) → 200,
STOP çağrıldı, bayrak VARSAYILANA düştü. Ortam izin listesidir (`tests/betik_alt_sureci.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam

KOK = Path(__file__).resolve().parents[1]

#: (bayrak, bozuk değer, modül, öznitelik, beklenen varsayılan)
BAYRAKLAR = [
    ("PEMF_JETON_OFFLINE_TAVAN", "elli", "servers.jeton", "OFFLINE_TAVAN", 50),
    ("PEMF_JETON_BORC_TAVANI", "yuz", "servers.jeton", "BORC_TAVANI", 300),
    ("PEMF_JETON_TIMEOUT", "dort", "servers.jeton", "_SUPABASE_TIMEOUT", 4.0),
    ("PEMF_AI_QUEUE_CONCURRENCY", "bir", "servers.entitlement", "AI_QUEUE_CONCURRENCY", 1),
    ("PEMF_AI_QUEUE_MAX_WAIT", "otuz", "servers.entitlement", "AI_QUEUE_MAX_WAIT", 30.0),
    ("PEMF_ENTITLEMENT_CACHE_TTL", "altmis", "servers.entitlement", "_CACHE_TTL", 60.0),
    ("PEMF_ENTITLEMENT_TIMEOUT", "4,5", "servers.entitlement", "_SUPABASE_TIMEOUT", 4.0),
    ("PEMF_AI_SERVICE_TIMEOUT", "yuzseksen", "servers.ai_client", "_TIMEOUT", 180.0),
]

_ALT_SUREC = r"""
import importlib, json, sys
sys.path[:0] = [{kok!r}, {backend!r}]
import servers.api_server as api
from fastapi.testclient import TestClient

class _HW:
    stop = 0
    def stop_all_coils(self):
        _HW.stop += 1
        return True

api.state.hardware = _HW()
api._mqtt_publish = lambda topic, payload: False
api._push_notification = lambda *a, **k: None
r = TestClient(api.app, client=("127.0.0.1", 50001)).post("/api/hardware/emergency_stop")
deger = getattr(importlib.import_module({modul!r}), {oznitelik!r})
print("SONUC " + json.dumps({{"durum": r.status_code, "stop": _HW.stop, "deger": deger}}))
"""


def _kos(tmp_path, bayrak: str, deger: str | None, modul: str, oznitelik: str):
    env = yalitik_ortam(tmp_path)
    env.update(
        {
            "PEMF_DATA_DIR": str(tmp_path / "veri"),
            "PEMF_DEVICE_IDENTITY_DIR": str(tmp_path / "kimlik"),
            "PEMF_CLOUD_PROVISION_PATH": str(tmp_path / "yok" / "provizyon.json"),
            "PEMF_ESP_ENABLED": "0",
            "PEMF_FW_AUTO_UPDATE": "0",
            "PEMF_HOTSPOT": "0",
            "PEMF_AI_WARMUP": "0",
        }
    )
    if deger is not None:
        env[bayrak] = deger
    kod = _ALT_SUREC.format(kok=str(KOK), backend=str(KOK / "apps" / "backend"), modul=modul, oznitelik=oznitelik)
    (tmp_path / "alt.py").write_text(kod, encoding="utf-8")
    return kostur([str(tmp_path / "alt.py")], cwd=tmp_path, env=env, sure=240)


def _sonuc(cikti: str) -> dict | None:
    for satir in cikti.splitlines():
        if satir.startswith("SONUC "):
            return json.loads(satir[len("SONUC ") :])
    return None


@pytest.mark.parametrize(
    ("bayrak", "bozuk", "modul", "oznitelik", "varsayilan"), BAYRAKLAR, ids=[b[0] for b in BAYRAKLAR]
)
def test_KRITIK_bozuk_bayrak_backendi_OLDURMEZ_ACIL_DURDUR_calisir(
    tmp_path, bayrak, bozuk, modul, oznitelik, varsayilan
):
    p = _kos(tmp_path, bayrak, bozuk, modul, oznitelik)
    s = _sonuc(p.stdout)
    assert p.returncode == 0 and s is not None, (
        f"{bayrak}={bozuk!r}: backend İÇE AKTARILAMADI (rc={p.returncode}) — ACİL DURDUR ucu YOK. "
        f"stderr sonu: {p.stderr[-600:]}"
    )
    assert s["durum"] == 200 and s["stop"] >= 1, f"{bayrak}={bozuk!r}: acil durdurma {s}"
    assert s["deger"] == pytest.approx(varsayilan), f"{bayrak}={bozuk!r}: değer {s['deger']} (varsayılan {varsayilan})"
    assert bayrak in p.stderr, f"{bayrak}: bozuk değer SESSİZCE yutuldu — uyarı günlüğü yok"


def test_KARSIT_gecerli_bayrak_DEGERI_kullanilir(tmp_path):
    """Varsayılana düşüş "her şeyi yok say" biçiminde bozulmasın: geçerli değer AYNEN okunur."""
    s = _sonuc(_kos(tmp_path, "PEMF_JETON_OFFLINE_TAVAN", "7", "servers.jeton", "OFFLINE_TAVAN").stdout)
    assert s and s["deger"] == 7 and s["durum"] == 200, s
