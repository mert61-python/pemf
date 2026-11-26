# -*- coding: utf-8 -*-
"""YS1d · Y320 (4) — frontend-ci ESLint'i (audit B-10.1) zincir kapılarında KOŞMUYORDU (jest + tsc yeşildi) → 48 HATA birikti, 25-11 dalga-2
CI'ı `frontend-ci` kırmızı (42 `array-type`, 4 `import/no-duplicates`, 2 `react-hooks/immutability` — AiProPanel / ControlScreen).

KAPI: (1) pre-commit yerel kancası `eslint-arayuz-hata` commit'te DEĞİŞEN `apps/ui/(src|app)` dosyalarında ESLint'i YALNIZ HATA düzeyinde
koşar (`--quiet`: ESLint 9'da uyarı kuralları hiç koşmaz — 1 479 uyarı CI'da bilgi amaçlı), düz yapılandırma `apps/ui` altında olduğu için
oradan koşar ve yol önekini atar, hatayı YUTMAZ; (2) CI lint adımı ESLint hatasında BLOKLAR (`npm run lint` = `eslint src app`, yutma yok).
Kancanın davranışı (hata → kırmızı) oturumda mutantla ölçüldü (YAYIN-SONRASI.md YS1d); bu dosya tanımı kilitler.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parents[1]


def _kanca() -> dict:
    d = yaml.safe_load((KOK / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    kancalar = [h for r in d["repos"] for h in r["hooks"] if h.get("id") == "eslint-arayuz-hata"]
    assert len(kancalar) == 1, f"pre-commit'te TEK `eslint-arayuz-hata` kancası bekleniyordu, bulunan {len(kancalar)}"
    return kancalar[0]


def test_KRITIK_precommit_eslint_kancasi_HATA_duzeyinde_degisen_arayuz_dosyalarini_kosar():
    h = _kanca()
    assert h.get("language") == "system", h
    assert h.get("pass_filenames", True) is True, (
        "kanca değişen dosyaları almıyor (pass_filenames: false) — tüm ağaç ya da hiç"
    )
    e = str(h["entry"])
    assert "cd apps/ui" in e and "node node_modules/eslint/bin/eslint.js" in e, (
        f"ESLint apps/ui yapılandırmasıyla koşmuyor: {e}"
    )
    assert re.search(r"(^|\s)--quiet(\s|$)", e), (
        f"`--quiet` yok — uyarılar da kancayı yavaşlatır / gürültü (yalnız HATA düzeyi): {e}"
    )
    assert '"${@#apps/ui/}"' in e, f"dosya yolları apps/ui'ye göre çevrilmiyor (ESLint yapılandırması bulunamaz): {e}"
    assert not re.search(r"\|\|\s*(true|:|exit\s+0|echo)|;\s*(true|exit\s+0)\s*'", e), (
        f"kanca ESLint hatasını YUTUYOR: {e}"
    )
    assert "--max-warnings" not in e and "--fix" not in e, f"kanca uyarı eşiği / otomatik düzeltme taşımamalı: {e}"
    desen = re.compile(str(h["files"]))
    for yol in (
        "apps/ui/src/screens/ControlScreen.tsx",
        "apps/ui/src/utils/kontrolHafizasi.ts",
        "apps/ui/src/screens/__tests__/KP8-KpiDashboard-dallari.test.tsx",
        "apps/ui/app/_layout.tsx",
        "apps/ui/src/eski.js",
    ):
        assert desen.search(yol), f"kanca {yol} değişince KOŞMUYOR"
    for yol in (
        "apps/web/src/App.tsx",
        "apps/ui/eslint.config.js",
        "apps/ui/node_modules/x/y.ts",
        "apps/backend/servers/api_server.py",
    ):
        assert not desen.search(yol), f"kanca kapsam dışı {yol} için koşuyor"


def test_KRITIK_CI_lint_adimi_ESLint_hatasinda_BLOKLAR():
    is_ = yaml.safe_load((KOK / ".github" / "workflows" / "frontend.yml").read_text(encoding="utf-8"))["jobs"]["test"]
    lint = [a for a in is_["steps"] if str(a.get("run", "")).strip() == "npm run lint"]
    assert len(lint) == 1, "frontend-ci'da `npm run lint` adımı yok"
    assert not lint[0].get("continue-on-error"), "ESLint adımı continue-on-error — hata BLOKLAMAZ"
    betik = json.loads((KOK / "apps" / "ui" / "package.json").read_text(encoding="utf-8"))["scripts"]["lint"]
    assert re.fullmatch(r"eslint src app --max-warnings=\d+", betik), (
        f"lint betiği beklenmedik (yutma / kapsam): {betik!r}"
    )
