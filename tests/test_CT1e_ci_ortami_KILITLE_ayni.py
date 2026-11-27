# -*- coding: utf-8 -*-
"""CT1 e (istem 66): CI ortamı = DERLEME KİLİDİ (`build_tools/myenv-requirements.txt`) — kilitten sonra kurulan hiçbir şey kilitteki
sürümü değiştiremez.

🔴 ÖLÇÜLEN (27-11, CI eşi = tests.yml adımlarının birebiri, `DENETIM\\araclar\\ci-esi\\kur.sh`): "gitleaks ikilisi" adımındaki kısıtsız
`pip install "pre-commit>=4.0,<5.0"` kilitteki packaging 26.2 → 26.4 ve typing-extensions 4.15.0 → 4.16.0 YÜKSELTİYORDU — 12 bin test
ürünün sevk ettiğinden farklı sürümlerle koşuyordu (CI-STANDART #2 "ürün ortamında test"). Düzeltme: kilit KISIT (`-c`) olarak verilir.

Kapı: (a) backend işindeki her `pip install` ya kilidin kendisi, ya sabit tek sürüm, ya pip yükseltmesi, ya da `-c <kilit>` taşır ·
(b) `requirements-test.txt` kilitle ORTAK paketlerde AYNI sürümü sabitler (ikinci adım kilidi değiştiremez) · (c) torch CPU dizini
(CUDA tekerleği CI'da gereksiz, kilit `+cpu`) · (d) pip / npm / model paketi önbellekleri dosya özetiyle anahtarlı."""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
KILIT = KOK / "build_tools" / "myenv-requirements.txt"


def _backend_isi() -> str:
    yml = (KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    bas = yml.index("  backend:\n")
    return yml[bas : yml.index("\n  sir-taramasi:", bas)]


def _sabitler(yol: Path) -> dict[str, str]:
    d = {}
    for s in yol.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==([^\s;#]+)", s.strip())
        if m:
            d[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = m.group(2)
    return d


def _kurulum_satirlari(is_: str) -> list[str]:
    return [s.strip() for s in is_.splitlines() if re.search(r"\bpip install\b", s) and not s.strip().startswith("#")]


def _kilitli_mi(satir: str) -> bool:
    return (
        "-r build_tools/myenv-requirements.txt" in satir
        or "-r requirements-test.txt" in satir
        or "-c build_tools/myenv-requirements.txt" in satir
        or re.search(r"pip install --upgrade pip\s*$", satir) is not None
        or re.search(r"pip install (--only-binary \S+ )?[A-Za-z0-9_.\-]+==[\w.+]+\s*$", satir) is not None
    )


def test_KRITIK_backend_isindeki_HER_pip_kurulumu_KILITLI():
    satirlar = _kurulum_satirlari(_backend_isi())
    assert len(satirlar) >= 4, satirlar
    kilitsiz = [s for s in satirlar if not _kilitli_mi(s)]
    assert not kilitsiz, f"kilitten sonra KISITSIZ kurulum (kilitteki sürümü değiştirebilir): {kilitsiz}"


def test_KARSIT_kisitsiz_pre_commit_kurulumu_YAKALANIR():
    assert not _kilitli_mi('pip install "pre-commit>=4.0,<5.0"')
    assert not _kilitli_mi("pip install requests")
    assert _kilitli_mi('pip install "pre-commit>=4.0,<5.0" -c build_tools/myenv-requirements.txt')
    assert _kilitli_mi("pip install --only-binary sqlcipher3 sqlcipher3==0.6.2")


def test_KRITIK_test_gereksinimleri_kilitle_ORTAK_paketlerde_AYNI_surum():
    kilit, test = _sabitler(KILIT), _sabitler(KOK / "requirements-test.txt")
    fark = {k: (v, kilit[k]) for k, v in test.items() if k in kilit and kilit[k] != v}
    assert not fark, f"requirements-test.txt kilitteki sürümü DEĞİŞTİRİR (test ↔ kilit): {fark}"


def test_KRITIK_torch_CPU_tekerlegi_ve_onbellekler():
    is_ = _backend_isi()
    assert "--extra-index-url https://download.pytorch.org/whl/cpu" in is_
    assert _sabitler(KILIT)["torch"].endswith("+cpu")
    assert re.search(r"cache: pip", is_) and re.search(r"cache: npm", is_)
    assert "key: pemf-ci-modelleri-${{ hashFiles('scripts/ci_modelleri_listesi.json') }}" in is_
