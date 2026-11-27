# -*- coding: utf-8 -*-
"""CT2 e (istem 66 · Y326 katman 8) — TEDARİK ZİNCİRİ: her `uses:` tam SHA (yorumda sürüm) · Dependabot (github-actions + npm + cargo
+ pip; haftalık, toplu) · pip-audit / npm audit BLOKLAYICI + gerekçeli liste (cargo audit deseni) · CodeQL (Python + JS/TS) haftalık.

Önce-KIRMIZI: SHA'sız `uses:` (etiket / dal) ekleyen sahte iş akışı → kapı kırmızı; listede olmayan npm tavsiyesi → kırmızı.
Politika (launcher/.cargo/audit.toml ile TUTARLI): `uygulanamaz` bölümüne GERÇEK açık girmez; 28-11'de var olan gerçek açıklar
`bilinen_borc` cırcırında ([SAHİBE] yükseltme kararı; Y3 onnx / torch sabit) — yalnız küçülür.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

KOK = Path(__file__).resolve().parents[1]
W = KOK / ".github" / "workflows"
_spec = importlib.util.spec_from_file_location("ci_audit_ct2e", KOK / "scripts" / "ci_audit.py")
au = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(au)

_USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)(.*)$", re.M)
_SABIT = re.compile(r"^[\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40}$")


def sabitsiz(metin: str) -> list[str]:
    """SHA'ya sabitlenmemiş ya da sürüm yorumu olmayan `uses:` satırları (yerel `./` iş akışları hariç)."""
    sorun = []
    for m in _USES.finditer(metin):
        ref, kalan = m.group(1), m.group(2)
        if ref.startswith("./"):
            continue
        if not _SABIT.match(ref):
            sorun.append(f"{ref} (tam SHA değil)")
        elif not re.match(r"\s+#\s*\S+", kalan):
            sorun.append(f"{ref} (sürüm yorumu yok)")
    return sorun


def test_KRITIK_her_uses_TAM_SHA_ve_surum_yorumlu():
    dosyalar = sorted(W.glob("*.yml"))
    assert len(dosyalar) >= 9, [p.name for p in dosyalar]
    sorun = {p.name: s for p in dosyalar if (s := sabitsiz(p.read_text(encoding="utf-8")))}
    assert not sorun, f"SHA'sız / yorumsuz eylem: {sorun}"


@pytest.mark.parametrize(
    "satir",
    [
        "      - uses: actions/checkout@v4\n",
        "      - uses: dtolnay/rust-toolchain@stable\n",
        "      - uses: actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830\n",
        "        uses: github/codeql-action/init@v3  # v3\n",
    ],
)
def test_KARSIT_sahte_SHAsiz_uses_KIRMIZI(satir):
    assert sabitsiz("steps:\n" + satir), satir


def test_KARSIT_yerel_cagri_ve_dogru_sabit_GECER():
    assert not sabitsiz("    uses: ./.github/workflows/tests.yml\n      - uses: a/b@" + "0" * 40 + "  # v1.2.3\n")


def _dependabot() -> list[dict]:
    return yaml.safe_load((KOK / ".github" / "dependabot.yml").read_text(encoding="utf-8"))["updates"]


def test_KRITIK_dependabot_DORT_ekosistem_haftalik_TOPLU():
    u = _dependabot()
    assert {"github-actions", "npm", "cargo", "pip"} <= {x["package-ecosystem"] for x in u}
    for x in u:
        assert x["schedule"]["interval"] == "weekly", x
        gruplar = x.get("groups") or {}
        assert any(g.get("applies-to") == "version-updates" and g.get("patterns") == ["*"] for g in gruplar.values()), (
            f"{x['package-ecosystem']}:{x['directory']} sürüm güncellemeleri TOPLU değil"
        )
    assert "/docker" not in {x["directory"] for x in u}, "Y344-2: Docker emekli — /docker girdisi kalmamalı"


def _guvenlik() -> dict:
    return yaml.safe_load((W / "security.yml").read_text(encoding="utf-8"))["jobs"]


def test_KRITIK_pip_audit_BLOKLAYICI_surum_kilitten_liste_gerekceli():
    adimlar = _guvenlik()["pip-audit"]["steps"]
    metin = "\n".join(str(a.get("run", "")) for a in adimlar)
    assert not any(a.get("continue-on-error") for a in adimlar) and "|| true" not in metin, "pip-audit hâlâ bloklamıyor"
    assert "grep -i '^pip_audit==' build_tools/myenv-requirements.txt" in metin, "pip-audit sürümü kilitten değil"
    for kaynak in ("build_tools/myenv-requirements.txt", "requirements-test.txt"):
        assert re.search(
            rf"pip-audit -r {re.escape(kaynak)} --no-deps --disable-pip .*\$\(python scripts/ci_audit\.py pip-yoksay\)",
            metin,
        ), kaynak
    kilit = (KOK / "build_tools" / "myenv-requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^pip_audit==\d", kilit, re.M)


def test_KRITIK_npm_audit_BLOKLAYICI_uc_agac():
    run = "\n".join(str(a.get("run", "")) for a in _guvenlik()["npm-audit"]["steps"])
    assert "set -euo pipefail" in run and "scripts/ci_audit.py npm" in run
    for d in ("apps/ui", "apps/web", "dema-terapi-simülatörü"):
        assert d in run, d


def test_KRITIK_liste_POLITIKASI_cargo_ile_tutarli():
    borc = au.borc_oku()
    assert "ASLA" in borc["aciklama"] and "CIRCIR" in borc["aciklama"]
    for k in borc["pip"]["uygulanamaz"]:
        assert k.get("gerekce") and k.get("kimlik"), k
    for k in borc["pip"]["bilinen_borc"]:
        assert k["gerekce"] and k["karar"] and k["kimlikler"] and k["surum"], k
    onnx = next(k for k in borc["pip"]["bilinen_borc"] if k["paket"] == "onnx")
    assert "Y3" in onnx["karar"], "onnx Y3 (sahip kararı) olarak işaretli değil"
    assert set(borc["npm"]) == {"apps/ui", "apps/web", "dema-terapi-simülatörü"}
    toml = (KOK / "launcher" / ".cargo" / "audit.toml").read_text(encoding="utf-8")
    assert "ASLA" in toml, "cargo audit politikası değişti — liste politikası yeniden tutarlı kılınmalı"


def test_pip_yoksay_argumanlari():
    kim = au.pip_kimlikleri(au.borc_oku())
    assert kim and all(re.fullmatch(r"[A-Z]+-[\w-]+", k) for k in kim), kim[:5]


def _npm_audit(*tavsiyeler: tuple[str, str]) -> dict:
    v = {}
    for paket, ghsa in tavsiyeler:
        v.setdefault(paket, {"via": []})["via"].append({"source": 1, "url": f"https://github.com/advisories/{ghsa}"})
    v["dolayli"] = {"via": ["baska-paket"]}
    return {"vulnerabilities": v}


def test_KRITIK_npm_LISTEDE_OLMAYAN_tavsiye_KIRMIZI(tmp_path):
    borc = {"npm": {"apps/ui": [{"paket": "a", "tavsiye": "GHSA-aaaa-bbbb-cccc"}]}, "pip": {}}
    yeni, kapanan = au.npm_karsilastir("apps/ui", _npm_audit(("a", "GHSA-aaaa-bbbb-cccc")), borc)
    assert not yeni and not kapanan
    yeni, _ = au.npm_karsilastir(
        "apps/ui", _npm_audit(("a", "GHSA-aaaa-bbbb-cccc"), ("b", "GHSA-dddd-eeee-ffff")), borc
    )
    assert yeni == ["b GHSA-dddd-eeee-ffff"]
    _, kapanan = au.npm_karsilastir("apps/ui", _npm_audit(), borc)
    assert kapanan == ["a GHSA-aaaa-bbbb-cccc"], "kapanan borç bildirilmiyor (cırcır küçülmez)"
    j = tmp_path / "a.json"
    j.write_text(json.dumps(_npm_audit(("z", "GHSA-zzzz-zzzz-zzzz"))), encoding="utf-8")
    b = tmp_path / "b.json"
    b.write_text(json.dumps(borc), encoding="utf-8")
    assert au.main(["--borc", str(b), "npm", "apps/ui", str(j)]) == 1
    j.write_text("{}", encoding="utf-8")
    assert au.main(["--borc", str(b), "npm", "apps/ui", str(j)]) == 2, "boş / bozuk audit çıktısı KÖR geçti"


def test_borc_uret_gerekceyi_KORUR(tmp_path):
    pipj = tmp_path / "sevk.json"
    pipj.write_text(
        json.dumps({"dependencies": [{"name": "onnx", "version": "1.15.0", "vulns": [{"id": "PYSEC-1"}]}]}),
        encoding="utf-8",
    )
    eski = {"pip": {"uygulanamaz": [], "bilinen_borc": [{"paket": "onnx", "gerekce": "G", "karar": "Y3"}]}, "npm": {}}
    yeni = au.borc_uret([pipj], {}, eski)
    assert yeni["pip"]["bilinen_borc"] == [
        {
            "paket": "onnx",
            "surum": "1.15.0",
            "kimlikler": ["PYSEC-1"],
            "kaynak": ["sevk"],
            "gerekce": "G",
            "karar": "Y3",
        }
    ]


def test_KRITIK_codeql_HAFTALIK_python_ve_js_ts():
    d = yaml.safe_load((W / "codeql.yml").read_text(encoding="utf-8"))
    tetik = d.get("on", d.get(True))
    assert tetik["schedule"][0]["cron"].split()[-1] != "*", "CodeQL haftalık değil"
    is_ = d["jobs"]["analyze"]
    assert set(is_["strategy"]["matrix"]["dil"]) == {"python", "javascript-typescript"}
    assert is_["permissions"]["security-events"] == "write" and d["permissions"] == {"contents": "read"}
