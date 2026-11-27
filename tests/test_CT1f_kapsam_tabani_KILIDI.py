# -*- coding: utf-8 -*-
"""CT1 f / g (istem 66 · Y311 / Y325 / Y326): KAPSAM KİLİDİ — taban DEPODA (`tests/kapsam_tabani.json`) ve CI eşikleri ONDAN.

🔴 ÖLÇÜLEN (26-11, Y325): Y311 cırcırı yalnız DENETIM istemlerinde + hafızadaydı; CI eşikleri tabanın ALTINDAYDI (jest 99/98/93/99 ↔
taban 100/99,29/94,38/100 · cargo 95 ↔ 96,04 · site 99/99/96/99 ↔ 100/100/98,21/100) → yeni kod yüzdeyi sessizce eritebiliyordu.
Kapı: (a) taban dosyası geçerli (her paket, 0–100, ai_hub / kart yazılımı dışarıdakiler gerekçeli) · (b) pyproject `fail_under` = sunucu
tabanı · (c) jest / vitest eşikleri JSON'dan okunur (sabit sayı YOK) · (d) cargo `--fail-under-lines` = taban − ölçülmüş pay · (e) her
iş akışında fark kapsamı adımı + tam geçmiş · (f) `scripts/kapsam_tabani_kapisi.py`: taban altı → 1 (önce-KIRMIZI, gerçek coverage verisiyle),
%100 tabanda yuvarlama payı YOK · (g) CLAUDE.md "Test kapsamı — kalıcı kural" bölümü taban dosyasını işaret eder."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

try:
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover — 3.10 (depo kilidi)
    import tomli as _toml

KOK = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("kapsam_tabani_kapisi_ct1f", KOK / "scripts" / "kapsam_tabani_kapisi.py")
ktk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ktk)
TABAN = json.loads((KOK / "tests" / "kapsam_tabani.json").read_text(encoding="utf-8"))["paketler"]
WF = KOK / ".github" / "workflows"
_fk_spec = importlib.util.spec_from_file_location("fark_kapsami_ct1f_k", KOK / "scripts" / "fark_kapsami.py")
fk = importlib.util.module_from_spec(_fk_spec)
_fk_spec.loader.exec_module(fk)


def test_KRITIK_taban_dosyasi_GECERLI_her_paket_ve_DISARIDAKILER_gerekceli():
    assert set(TABAN) == {"sunucu", "istemci_jest", "site_vitest", "baslatici_cargo", "ai_hub", "kart_yazilimi"}
    for ad, p in TABAN.items():
        for alan in ("satir", "deyim", "dal", "islev"):
            if alan in p:
                assert 0.0 <= float(p[alan]) <= 100.0, (ad, alan)
    for ad in ("ai_hub", "kart_yazilimi"):
        assert TABAN[ad]["disarida"] and all(len(g) >= 20 for g in TABAN[ad]["disarida"].values()), ad


def test_KRITIK_pyproject_fail_under_SUNUCU_tabanina_esit_ai_hub_toplam_DISINDA():
    cov = _toml.loads((KOK / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["coverage"]
    assert float(cov["report"]["fail_under"]) == TABAN["sunucu"]["satir"]
    assert "ai_hub" in cov["run"]["source"] and "*/ai_hub/*" in cov["report"]["omit"]
    disari_py = [k for k in TABAN["ai_hub"]["disarida"] if k.endswith(".py")]
    assert all(any(o.endswith(k.split("ai_hub/", 1)[1]) for o in cov["run"]["omit"]) for k in disari_py), (
        "ai_hub dışarıdaki listesi ↔ run.omit tutarsız"
    )


@pytest.mark.parametrize(
    "yol,anahtar",
    [("apps/ui/jest.config.js", "istemci_jest"), ("apps/web/vite.config.ts", "site_vitest")],
)
def test_KRITIK_jest_vitest_esikleri_TABANDAN_sabit_sayi_YOK(yol, anahtar):
    t = (KOK / yol).read_text(encoding="utf-8")
    assert "tests/kapsam_tabani.json" in t and f"paketler.{anahtar}" in t, f"{yol} eşiği tabandan okumuyor"
    for alan, ad in (("lines", "satir"), ("statements", "deyim"), ("branches", "dal"), ("functions", "islev")):
        assert re.search(rf"{alan}:\s*KAPSAM_TABANI\.{ad}\b", t), f"{yol}: {alan} tabandan değil"
        assert not re.search(rf"{alan}:\s*\d", t), f"{yol}: {alan} SABİT sayı (taban altı eşik geri gelir)"


def test_KRITIK_cargo_esigi_TABAN_eksi_OLCULMUS_pay():
    c = TABAN["baslatici_cargo"]
    assert 0 < c["oynama_payi"] <= 0.5, "pay ölçülmüş küçük oynamadan büyük — taban fiilen düşürülür"
    assert round(c["satir"] - c["oynama_payi"], 2) == c["ci_esigi"]
    yml = (WF / "tests.yml").read_text(encoding="utf-8")
    m = re.findall(r"--fail-under-lines ([0-9.]+)", yml)
    assert m == [str(c["ci_esigi"])], (m, c["ci_esigi"])


def _adim(yml: str, ad: str) -> str:
    m = re.search(rf"- name: {re.escape(ad)}[^\n]*\n(?:\s{{8}}.*\n)+", yml)
    assert m, f"adım yok: {ad}"
    return m.group(0)


def test_KRITIK_her_is_akisinda_FARK_KAPSAMI_adimi_ve_TAM_gecmis():
    tests = (WF / "tests.yml").read_text(encoding="utf-8")
    a = _adim(tests, "Kapsam kilidi (taban + fark kapsamı)")
    assert "python scripts/kapsam_tabani_kapisi.py --json coverage.json" in a
    assert "python scripts/fark_kapsami.py --covjson coverage.json" in a
    assert tests.index("- name: Kritik-yol testleri") < tests.index("- name: Kapsam kilidi (taban + fark kapsamı)")
    assert "--lcov launcher/lcov.info:launcher" in _adim(tests, "Fark kapsamı kapısı (başlatıcı)")
    launcher = tests[tests.index("  launcher:\n") :]
    assert "fetch-depth: 0" in launcher[: launcher.index("dtolnay/rust-toolchain")]
    for dosya, lcov in (
        ("frontend.yml", "apps/ui/coverage/lcov.info:apps/ui"),
        ("site.yml", "apps/web/coverage/lcov.info:apps/web"),
    ):
        y = (WF / dosya).read_text(encoding="utf-8")
        assert f"python3 scripts/fark_kapsami.py --lcov {lcov}" in _adim(y, "Fark kapsamı kapısı"), dosya
        assert "fetch-depth: 0" in y[: y.index("actions/setup-node")], f"{dosya}: sığ klonda fark tabanı bulunmaz (kör)"
        assert y.index("--coverage") < y.index("- name: Fark kapsamı kapısı"), dosya
    assert "'lcov'" in (KOK / "apps" / "web" / "vite.config.ts").read_text(encoding="utf-8")


def test_KRITIK_karsilastir_TABAN_ALTI_kirmizi_yuz_tabanda_yuvarlama_PAYI_YOK():
    t = {"sunucu": {"satir": 100.0}, "ai_hub": {"satir": 61.37}}
    assert ktk.karsilastir({"sunucu": 100.0, "ai_hub": 61.37}, t) == []
    assert ktk.karsilastir({"sunucu": 100.0, "ai_hub": 61.374}, t) == []
    assert ktk.karsilastir({"sunucu": 99.996, "ai_hub": 70.0}, t)[0].startswith("sunucu:")
    s = ktk.karsilastir({"sunucu": 100.0, "ai_hub": 61.36}, t)
    assert len(s) == 1 and "ai_hub" in s[0] and "DÜŞÜRÜLMEZ" in s[0]


_OLCUM_BETIGI = """
import importlib, sys
import coverage
sys.path.insert(0, ".")
c = coverage.Coverage(data_file=".coverage", config_file="pyproject.toml")
c.start()
a = importlib.import_module("paket.a")
b = importlib.import_module("ai_hub.b")
a.f()
b.g(True)
if sys.argv[1] == "1":
    b.g(False)
c.stop()
c.save()
"""


def _kapsam_verisi(tmp_path: Path, kos_b: bool) -> Path:
    """Gerçek coverage verisi: `paket/a.py` (sunucu benzeri) + `ai_hub/b.py`; `kos_b` False → ai_hub'ın yarısı koşmaz.

    ⚠️ ALT SÜREÇTE (ölçüldü 27-11, CI eşi tam koşusu): süreç içinde ikinci bir `Coverage().start()` pytest-cov'un izleyici yığınını
    bozuyordu — xdist işçisi "Expected current collector …" iç hatasıyla düştü, `.coverage` birleşmedi (kapsam kapısı kör kaldı).
    pytest-cov'un alt süreç ortam değişkenleri silinir (alt süreç kendi ölçümünü kurmasın)."""
    import os
    import subprocess
    import sys

    (tmp_path / "paket").mkdir()
    (tmp_path / "ai_hub").mkdir()
    (tmp_path / "paket" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "ai_hub" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "paket" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "ai_hub" / "b.py").write_text(
        "def g(x):\n    if x:\n        return 1\n    return 2\n", encoding="utf-8"
    )
    ayar = tmp_path / "pyproject.toml"
    ayar.write_text(
        '[tool.coverage.run]\nsource = ["paket", "ai_hub"]\nrelative_files = true\n'
        '[tool.coverage.report]\nomit = ["*/ai_hub/*"]\n',
        encoding="utf-8",
    )
    (tmp_path / "olc.py").write_text(_OLCUM_BETIGI, encoding="utf-8")
    ortam = {k: v for k, v in os.environ.items() if not k.startswith(("COV_CORE_", "COVERAGE_"))}
    r = subprocess.run(
        [sys.executable, "olc.py", "1" if kos_b else "0"],
        cwd=tmp_path,
        env=ortam,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0 and (tmp_path / ".coverage").is_file(), r.stderr[-1500:]
    return ayar


def test_KRITIK_olc_GERCEK_veride_sunucu_ve_ai_hub_AYRI_taban_alti_KIRMIZI(tmp_path, monkeypatch):
    ayar = _kapsam_verisi(tmp_path, kos_b=False)
    monkeypatch.chdir(tmp_path)
    olcum = ktk.olc(tmp_path / ".coverage", tmp_path / "c.json", ayar)
    assert olcum["sunucu"] == 100.0, "ai_hub sunucu toplamına karıştı"
    assert 0 < olcum["ai_hub"] < 100.0
    dosyalar = {Path(k).as_posix() for k in json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))["files"]}
    assert {"ai_hub/__init__.py", "ai_hub/b.py", "paket/__init__.py", "paket/a.py"} <= dosyalar, (
        f"birleşik raporda yol TEK anlamlı değil / ai_hub yok: {dosyalar}"
    )
    taban = {"sunucu": {"satir": 100.0}, "ai_hub": {"satir": 100.0}}
    assert ktk.karsilastir(olcum, taban), "taban altı ai_hub YEŞİL geçti"


def test_main_kor_ve_kirmizi_ve_yesil(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ktk, "_konsol_utf8", lambda: None)
    assert ktk.main(["--veri", str(tmp_path / "yok")]) == 2
    (tmp_path / "bozuk").write_bytes(b"bozuk")
    assert ktk.main(["--veri", str(tmp_path / "bozuk")]) == 2
    monkeypatch.setattr(ktk, "olc", lambda v, x: {"sunucu": 100.0, "ai_hub": 50.0})
    t = tmp_path / "t.json"
    t.write_text(json.dumps({"paketler": {"sunucu": {"satir": 100}, "ai_hub": {"satir": 60}}}), encoding="utf-8")
    assert ktk.main(["--veri", str(tmp_path / "bozuk"), "--taban", str(t)]) == 1
    t.write_text(json.dumps({"paketler": {"sunucu": {"satir": 100}, "ai_hub": {"satir": 50}}}), encoding="utf-8")
    assert ktk.main(["--veri", str(tmp_path / "bozuk"), "--taban", str(t)]) == 0
    assert "tamam" in capsys.readouterr().out


def test_konsol_utf8():
    class _A:
        ayar = None

        def reconfigure(self, **k):
            self.ayar = k

    a = _A()
    ktk._konsol_utf8([a, object()])
    assert a.ayar == {"encoding": "utf-8", "errors": "replace"}


def test_KRITIK_CLAUDE_md_KALICI_kural_bolumu_tabani_isaret_eder():
    t = (KOK / "CLAUDE.md").read_text(encoding="utf-8")
    bas = t.index("## Test kapsamı — kalıcı kural")
    b = t[bas:]
    for ifade in (
        "Fark kapsamı %100",
        "Yeni dosya baştan %100",
        "tests/kapsam_tabani.json",
        "pragma: no cover",
        "DÜŞÜRÜLMEZ",
        "test silinmez",
        "tests/ci_atlanan_defteri.json",
    ):
        assert ifade in b, ifade
    assert 5 <= len(re.findall(r"^\d\. \*\*", b, re.M)) <= 7
