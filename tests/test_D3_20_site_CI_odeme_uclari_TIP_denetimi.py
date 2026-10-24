# Author: mertaygn, cglrgrkn
"""D3.20 (B-7.10) — site CI'ı ödeme uçlarının (`apps/web/api` — Vercel işlevleri) tip denetimini de koşar ve YUTMAZ.

ÖLÇÜLEN KÖR KAPI (2026-10-25): `site.yml`'in tip adımı `npx tsc -b` yalnız `tsconfig.app` (include=src) + `tsconfig.node`'u derler; `api/`
dışarıda. `api/_lib/util.ts`'e `export const _m: number = "yedi"` mutantı: `tsc -b` rc 0, `tsc -p api --noEmit` rc 2. Ayrıca `tsc -p api`
HEAD'de KENDİSİ kırmızıydı (rc 2): `api/_lib/__tests__/jeton-yenileme.test.ts` `src/config` üzerinden tarayıcı kodunu (DOM, `src/i18n`)
çekiyordu → kapsam işlevlere daraltıldı (testler vitest'te koşar).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
yaml = pytest.importorskip("yaml", reason="pyyaml yok")


def _adimlar():
    d = yaml.safe_load((KOK / ".github" / "workflows" / "site.yml").read_text(encoding="utf-8"))
    for is_ in d["jobs"].values():
        yield from is_.get("steps") or []


def test_KRITIK_D3_20_site_CI_tsc_p_api_adimi_VAR_ve_YUTULMAZ():
    adim = [a for a in _adimlar() if "tsc -p api" in str(a.get("run") or "")]
    assert len(adim) == 1, "site.yml'de ödeme uçlarının tip denetimi (tsc -p api) yok"
    a = adim[0]
    assert str(a["run"]).strip() == "npx tsc -p api --noEmit", f"adım biçimi: {a['run']!r}"
    assert not a.get("continue-on-error"), "adım continue-on-error ile yutuluyor"
    assert "||" not in str(a["run"]) and "true" not in str(a["run"]), "adım kabukta yutuluyor"
    tip = [i for i, x in enumerate(_adimlar()) if str(x.get("run") or "").strip() == "npx tsc -b"]
    assert tip and list(_adimlar()).index(a) > tip[0], "api tip denetimi ana tip adımından önce / yerine"


def test_KRITIK_D3_20_api_tsconfig_ISLEVLERI_kapsar_testleri_disarida_birakir():
    ham = (KOK / "apps" / "web" / "api" / "tsconfig.json").read_text(encoding="utf-8")
    c = json.loads(ham)
    assert c.get("include") == ["**/*.ts"], c.get("include")
    assert c.get("exclude") == ["_lib/__tests__/**"], (
        "kapsam yalnız testleri dışarıda bırakmalı (işlevler denetimden düşmesin)"
    )
    assert c["compilerOptions"].get("strict") is True and c["compilerOptions"].get("noEmit") is True
    islevler = sorted(p.name for p in (KOK / "apps" / "web" / "api").glob("*.ts"))
    assert {"callback.ts", "checkout.ts", "webhook.ts", "cancel.ts", "tokens.ts"} <= set(islevler), islevler
