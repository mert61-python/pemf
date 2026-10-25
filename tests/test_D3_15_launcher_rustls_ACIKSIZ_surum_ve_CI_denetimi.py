# Author: mertaygn, cglrgrkn
"""D3.15 (B-8.18) — launcher `Cargo.lock` `rustls` ≥ 0.23.45 (RUSTSEC-2026-0285) ve `cargo audit` HER PUSH'ta koşar.

ÖLÇÜLEN (2026-10-25): `cargo audit --no-fetch --deny warnings` (yerel tavsiye DB, audit.toml ile) HEAD kilidinde rc 1 — rustls 0.23.42
RUSTSEC-2026-0285. `cargo update -p rustls --precise 0.23.45` (istemdeki tek indirme istisnası, crates.io) → rustls 0.23.45 + zorunlu
geçişli rustls-webpki 0.103.16; denetim rc 0; cargo çekirdek 379 / 0, uygulama 50 / 0. Denetim yalnız `launcher-v*` etiketinde koşuyordu.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


def _surum(paket: str) -> tuple[int, ...]:
    kilit = (KOK / "launcher" / "Cargo.lock").read_text(encoding="utf-8")
    m = re.findall(rf'\[\[package\]\]\nname = "{re.escape(paket)}"\nversion = "([0-9.]+)"', kilit.replace("\r\n", "\n"))
    assert m, f"{paket} kilitte yok"
    return min(tuple(int(x) for x in v.split(".")) for v in m)


def test_KRITIK_D3_15_rustls_RUSTSEC_2026_0285_duzeltmesinin_ustunde():
    assert _surum("rustls") >= (0, 23, 45), f"rustls {_surum('rustls')} — RUSTSEC-2026-0285"
    assert _surum("rustls-webpki") >= (0, 103, 16)


def test_KRITIK_D3_15_cargo_audit_HER_PUSHta_ve_audit_toml_ile():
    yaml = pytest.importorskip("yaml", reason="pyyaml yok")
    d = yaml.safe_load((KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))
    adim = [a for a in d["jobs"]["launcher"]["steps"] if "cargo audit" in str(a.get("run") or "")]
    assert len(adim) == 1, "tests.yml launcher işinde cargo audit yok (yalnız etiketli yayında koşuyordu)"
    assert adim[0].get("working-directory") == "launcher", "audit.toml (launcher/.cargo) okunmaz"
    assert (
        "--deny warnings" in adim[0]["run"] and "|| true" not in adim[0]["run"] and not adim[0].get("continue-on-error")
    )
    toml = (KOK / "launcher" / ".cargo" / "audit.toml").read_text(encoding="utf-8")
    assert "RUSTSEC-2026-0285" not in toml, "gerçek açık yoksayma listesine eklenmiş"
