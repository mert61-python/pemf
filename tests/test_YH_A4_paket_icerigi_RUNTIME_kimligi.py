# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YH · A4 (istem 50 · Tezgâh-2 listesi 5): `/api/health` çalışan RUNTIME'ın içeriğini söyler.

ÖLÇÜLEN KUSUR (T2Y tezgâhı, 13 Kasım 2026): `buildId` launcher'ın KAYDINDAN gelir (`installed_packages.json` → `PEMF_BASE_SHA`).
ODK'nın yerel deneme kurulumu runtime'ı kayıt dışı değiştirdi; `/api/health` yine yayındaki `13d967121f94`ü söyledi — "hangi paket
çalışıyor" sorusuna YANLIŞ cevap. `buildId`in kendisi sözleşmedir ([5.5]: manifest app-katmanı sha'sı = CHANGELOG etiketi; destek
eşleştirmesi) ve zip kendi sha'sını taşıyamaz → kayıttan bağımsız kimlik ayrı alanda: `make_base_zip` app katmanının İÇERİK özetini
(sıralı yol + içerik sha'sı) katmanın kendi sınır dosyasına (`PEMF_Backend/_app_roots.json` → `icerik`; launcher yalnız `roots`u okur)
yazar; backend onu `paketIcerigi` olarak verir (ilk 12 hane). Yerel kurulumda `paketIcerigi` ≠ yayındaki paketin içeriği → görünür.

Ölçüm: GERÇEK `make_base_zip` sahte dist ile alt süreçte (`PEMF_PKG_OUT` tmp; yayın dizinine dokunmaz) · GERÇEK `get_paket_icerigi`
donmuş-EXE benzetimiyle (`sys.frozen`, `sys.executable` tmp) · GERÇEK `/api/health` (TestClient).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
MAKE_BASE_ZIP = KOK / "build_tools" / "make_base_zip.py"


def _dist(tmp: Path, exe: bytes = b"EXE", torch: bytes = b"TORCH") -> Path:
    d = tmp / "dist" / "PEMF_Backend"
    for alt in ("ai_hub", "frontend/dist", "bin/mosquitto", "torch", "ai_models/ai_hub/inference_cat_organ/models"):
        (d / "_internal" / alt).mkdir(parents=True, exist_ok=True)
    (d / "_internal" / "ai_models" / "ai_hub" / "inference_cat_organ" / "models" / "r.onnx").write_bytes(b"ORGAN")
    (d / "PEMF_Backend.exe").write_bytes(exe)
    (d / "_internal" / "VERSION").write_text("1.9.53", encoding="utf-8")
    (d / "_internal" / "ai_hub" / "model.pyd").write_bytes(b"PYD")
    (d / "_internal" / "frontend" / "dist" / "index.html").write_text("<html>", encoding="utf-8")
    (d / "_internal" / "bin" / "mosquitto" / "mosquitto.exe").write_bytes(b"MOSQ")
    (d / "_internal" / "torch" / "lib.dll").write_bytes(torch)
    return d


def _paketle(tmp: Path, ad: str, **dist) -> tuple[dict, dict]:
    d = _dist(tmp / ad, **dist)
    cikti = tmp / ad / "cikti"
    cikti.mkdir()
    r = subprocess.run(
        [sys.executable, str(MAKE_BASE_ZIP), str(d)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PEMF_PKG_OUT": str(cikti)},
        timeout=300,
    )
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-800:]
    with zipfile.ZipFile(cikti / "base-app.zip") as z:
        isaret = json.loads(z.read("PEMF_Backend/_app_roots.json"))
    seti = json.loads((cikti / "base-katman-seti.json").read_text(encoding="utf-8"))
    return isaret, seti


def test_KRITIK_app_katmani_ICERIK_kimligini_TASIR_belirlenimci_ve_yalniz_APP_icerigine_bagli(tmp_path):
    a, seti_a = _paketle(tmp_path, "a")
    b, _ = _paketle(tmp_path, "b")  # aynı içerik, ayrı koşu
    c, _ = _paketle(tmp_path, "c", exe=b"EXE-2")  # app katmanı değişti
    d, _ = _paketle(tmp_path, "d", torch=b"TORCH-2")  # yalnız deps değişti
    ic = a.get("icerik")
    assert isinstance(ic, str) and len(ic) == 64 and all(h in "0123456789abcdef" for h in ic), a
    assert a["roots"] and isinstance(a["roots"], list), "aparat: sınır listesi aynen"
    assert b["icerik"] == ic, "aynı içerik farklı kimlik verdi (belirlenimci değil)"
    assert c["icerik"] != ic, "app katmanı değişti ama içerik kimliği AYNI kaldı"
    assert d["icerik"] == ic, "yalnız deps değişti ama app içerik kimliği değişti"
    assert seti_a["app"].get("icerik") == ic, (
        "base-katman-seti.json app içerik kimliğini taşımıyor (yerel kurulum doğrulaması)"
    )


def _donmus(monkeypatch, tmp: Path, isaret) -> None:
    from utils import path_utils

    exe_dizini = tmp / "runtime" / "PEMF_Backend"
    exe_dizini.mkdir(parents=True)
    if isaret is not None:
        (exe_dizini / "_app_roots.json").write_text(
            isaret if isinstance(isaret, str) else json.dumps(isaret), encoding="utf-8"
        )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dizini / "PEMF_Backend.exe"))
    monkeypatch.setattr(path_utils, "_PAKET_ICERIGI", None)


def test_KRITIK_donmus_runtime_kendi_icerik_kimligini_okur(monkeypatch, tmp_path):
    from utils import path_utils

    _donmus(monkeypatch, tmp_path, {"roots": ["PEMF_Backend/PEMF_Backend.exe"], "icerik": "AB" * 32})
    assert path_utils.get_paket_icerigi() == "abababababab"


@pytest.mark.parametrize(
    "isaret",
    [None, "{bozuk", {"roots": []}, {"roots": [], "icerik": "kisa"}, {"roots": [], "icerik": "zz" * 32}],
    ids=["dosya-yok", "bozuk-json", "alan-yok", "kisa", "hex-degil"],
)
def test_KRITIK_kimlik_UYDURULMAZ(monkeypatch, tmp_path, isaret):
    from utils import path_utils

    _donmus(monkeypatch, tmp_path, isaret)
    assert path_utils.get_paket_icerigi() == ""


def test_kaynak_agacindan_kosuda_BOS(monkeypatch):
    from utils import path_utils

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(path_utils, "_PAKET_ICERIGI", None)
    assert path_utils.get_paket_icerigi() == ""


def test_KRITIK_health_paketIcerigi_SOYLER_buildId_KAYITTAN_aynen(monkeypatch, tmp_path):
    """`buildId` sözleşmesi ([5.5]) DEĞİŞMEZ: kayıttaki (launcher) app sha'sı; `paketIcerigi` çalışan dosyaların kimliği."""
    from fastapi.testclient import TestClient
    from servers import api_server as api
    from utils import path_utils

    monkeypatch.setattr(api, "_BUILD_ID", "13d967121f94")
    monkeypatch.setattr(path_utils, "_PAKET_ICERIGI", "0123456789ab")
    c = TestClient(api.app, client=("127.0.0.1", 51234))  # test_version_visibility deseni (lifespan YOK)
    j = c.get("/api/health").json()
    assert j["buildId"] == "13d967121f94"
    assert j["paketIcerigi"] == "0123456789ab"
    monkeypatch.setattr(path_utils, "_PAKET_ICERIGI", "")
    assert c.get("/api/health").json()["paketIcerigi"] is None, "kimlik yokken boş dize değil None (uydurma YOK)"
