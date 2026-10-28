# -*- coding: utf-8 -*-
"""Y211 · S-D67.8 (sahip, 2026-10-28) — DEMA simülatöründe Google AI Studio şablon artığı kaldırıldı (L1-7.7 devri).

Kesin kaldırılan: `vite.config.ts` `process.env.GEMINI_API_KEY` tanımı (+ yalnız onun için okunan `loadEnv`), AI Studio HMR anahtarı
(`DISABLE_HMR`), `.env.example` (Gemini anahtarı + AI Studio `APP_URL` şablonu) ve `.gitignore`daki istisnası. Simülatör Gemini'yi
çağırmaz (L1-7.7 kapısı kaynağı ölçer). `package.json`daki `@google/genai` kaydı ÇEVRİMDIŞI kaldırılamadı (npm `--offline` ENOTCACHED —
kilit dosyası yeniden çözülmeli; ORTAK §1 indirme yasağı): kayıt durdukça README bunu ve yapılacak adımı SÖYLER (sessiz kalıntı olmaz).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
DEMA = KOK / "dema-terapi-simülatörü"


def test_KRITIK_vite_yapilandirmasinda_Gemini_ve_AI_Studio_artigi_YOK():
    kod = (DEMA / "vite.config.ts").read_text(encoding="utf-8")
    kod = "\n".join(s for s in kod.splitlines() if not s.lstrip().startswith("//"))
    for yasak in ("GEMINI_API_KEY", "DISABLE_HMR", "loadEnv"):
        assert yasak not in kod, f"vite.config.ts hâlâ AI Studio artığı taşıyor: {yasak}"
    assert "plugins: [react(), tailwindcss()]" in kod, "aparat: vite yapılandırması tanınmadı"


def test_KRITIK_env_example_sablonu_ve_gitignore_istisnasi_YOK():
    assert not (DEMA / ".env.example").exists(), (
        ".env.example (Gemini anahtarı / AI Studio APP_URL şablonu) hâlâ duruyor"
    )
    assert "!.env.example" not in (DEMA / ".gitignore").read_text(encoding="utf-8")


def test_KRITIK_genai_kaydi_durdukca_README_kaldirma_adimini_SOYLER():
    paket = json.loads((DEMA / "package.json").read_text(encoding="utf-8"))
    kayitli = "@google/genai" in {**paket.get("dependencies", {}), **paket.get("devDependencies", {})}
    readme = (DEMA / "README.md").read_text(encoding="utf-8")
    if kayitli:
        assert re.search(r"npm uninstall @google/genai", readme), (
            "@google/genai kaydı duruyor ama README kaldırma adımını söylemiyor (sessiz kalıntı)"
        )
    else:
        assert "@google/genai" not in json.dumps(
            json.loads((DEMA / "package-lock.json").read_text(encoding="utf-8"))
        ), "package.json'dan kalktı ama kilit dosyasında duruyor — `npm ci` uyuşmazlıkla DÜŞER"
