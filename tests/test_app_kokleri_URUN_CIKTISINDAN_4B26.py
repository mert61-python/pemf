# -*- coding: utf-8 -*-
"""4B-2.6 (4-B incelemesi A2) — D4.29 kök kapısı APP_ROOTS'u yalnız ÜST-DÜZEY `=` atamasından okuyor.

Ölçüldü (`_inceleme/kayit/k2_mutasyon.txt`): `make_base_zip.py`'ye tanımdan sonra `APP_ROOTS.remove('…/deploy')` ya da
`APP_ROOTS += ['…/yeni_kok']` eklenince D4.29 + D4.32 kümesi (59 dosya) **596 passed** — kök gerçekte düştüğü/eklendiği hâlde
kapı eski listeyi görür (D4.29'un korumak istediği "deploy deps'e kayar" kusurunun ta kendisi, başka sözdizimiyle).
Doğru ölçü ürünün KENDİ çıktısıdır: launcher'ın okuduğu `_app_roots.json` (base-app.zip içinde). Bu kapı betiği sahte dist ile
GERÇEKTEN koşturur, işaret dosyasını okur; AST değerlendirmesiyle AYNI olmalı ve Rust tatbikatıyla iki yönlü karşılaştırılır.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "tests"))

import test_app_koku_RUST_PYTHON_ve_model_parts_kaybi_D429 as d429  # noqa: E402


def _isaret_kokleri(tmp: Path) -> set[str]:
    d = tmp / "dist" / "PEMF_Backend"
    for alt in ("ai_hub", "frontend/dist", "bin/mosquitto", "torch", "ai_models/ai_hub/inference_cat_organ/models"):
        (d / "_internal" / alt).mkdir(parents=True, exist_ok=True)
    (d / "PEMF_Backend.exe").write_bytes(b"EXE")
    (d / "_internal" / "ai_hub" / "model.pyd").write_bytes(b"PYD")
    (d / "_internal" / "frontend" / "dist" / "index.html").write_text("<html>", encoding="utf-8")
    (d / "_internal" / "bin" / "mosquitto" / "mosquitto.exe").write_bytes(b"MOSQ")
    (d / "_internal" / "torch" / "lib.dll").write_bytes(b"TORCH")
    (d / "_internal" / "ai_models" / "ai_hub" / "inference_cat_organ" / "models" / "r.onnx").write_bytes(b"ORGAN")
    cikti = tmp / "cikti"
    cikti.mkdir()
    r = subprocess.run(
        [sys.executable, str(d429.MAKE_BASE_ZIP), str(d)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PEMF_PKG_OUT": str(cikti)},
        timeout=300,
    )
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-800:]
    with zipfile.ZipFile(cikti / "base-app.zip") as z:
        return set(json.loads(z.read("PEMF_Backend/_app_roots.json"))["roots"])


def test_KRITIK_urunun_isaret_dosyasi_AST_okumasiyla_AYNI_ve_RUST_ile_iki_yonlu(tmp_path):
    isaret = _isaret_kokleri(tmp_path)
    ast_kokleri = d429._python_app_roots(d429.MAKE_BASE_ZIP.read_text(encoding="utf-8"))
    assert isaret == ast_kokleri, (
        "make_base_zip'in URETTIGI _app_roots.json, kapinin AST'den okudugu APP_ROOTS'tan FARKLI (ust-duzey atama disinda "
        f"degisiklik: +=, append, remove, kosullu): yalniz isarette {sorted(isaret - ast_kokleri)}, "
        f"yalniz AST'de {sorted(ast_kokleri - isaret)}"
    )
    rs = d429._rust_app_roots(d429.UPGRADE_DRILL.read_text(encoding="utf-8"))
    assert rs <= isaret and isaret - rs == d429.RUST_TATBIKATINDA_HENUZ_YOK, (
        f"uretim isareti ile Rust tatbikati kaydi: fark={sorted(isaret - rs)}, rust-fazla={sorted(rs - isaret)}"
    )
