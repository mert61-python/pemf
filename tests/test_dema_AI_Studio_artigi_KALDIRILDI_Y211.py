# -*- coding: utf-8 -*-
"""Y211 · S-D67.8 (sahip, 2026-10-28) — DEMA simülatöründe Google AI Studio şablon artığı kaldırıldı (L1-7.7 devri).

Kesin kaldırılan: `vite.config.ts` `process.env.GEMINI_API_KEY` tanımı (+ yalnız onun için okunan `loadEnv`), AI Studio HMR anahtarı
(`DISABLE_HMR`), `.env.example` (Gemini anahtarı + AI Studio `APP_URL` şablonu) ve `.gitignore`daki istisnası. Simülatör Gemini'yi
çağırmaz (L1-7.7 kapısı kaynağı ölçer). `package.json`daki `@google/genai` kaydı o gün ÇEVRİMDIŞI kaldırılamadı (npm `--offline`
ENOTCACHED); YH-A2 (istem 50, 2026-11-16, ağ izinli) `npm uninstall @google/genai` ile package.json + kilitten kaldırdı — kapı artık kesin.
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


def test_KRITIK_genai_kaydi_package_json_ve_KILITTE_YOK_YH_A2():
    """YH-A2 (istem 50, 2026-11-16): kayıt ağ izinli oturumda `npm uninstall @google/genai` ile kaldırıldı (eskiden bu kapı
    "kayıt durdukça README kaldırma adımını söyler" diyordu). Kalıntı geri gelirse (elle ekleme / eski kilit) KIRMIZI: `package.json`
    bağımlılıklarında YOK; kilitte hiçbir paket girdisinde YOK (yalnız package.json'dan silinip kilit kalırsa `npm ci` uyuşmazlıkla
    DÜŞER); README artık kaydın "durduğunu" söylemez."""
    paket = json.loads((DEMA / "package.json").read_text(encoding="utf-8"))
    assert "@google/genai" not in {**paket.get("dependencies", {}), **paket.get("devDependencies", {})}, (
        "@google/genai kaydı package.json'da DURUYOR (simülatör Gemini'yi çağırmaz — ölü bağımlılık)"
    )
    kilit = json.loads((DEMA / "package-lock.json").read_text(encoding="utf-8"))
    assert "@google/genai" not in json.dumps(kilit), (
        "kilit dosyasında @google/genai DURUYOR — `npm ci` uyuşmazlıkla DÜŞER"
    )
    readme = (DEMA / "README.md").read_text(encoding="utf-8")
    assert not re.search(r"kaldırılamadığı için duruyor|ağ açık bir derleme oturumunda `npm uninstall", readme), (
        "README kaydın hâlâ durduğunu / yapılacak adımı söylüyor — bayat"
    )
