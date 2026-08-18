# Author: mertaygn, cglrgrkn
"""LINT MUAFİYETLERİ İKİ YERDE AYRIŞMAMALI — "yerelde geçti, CI'da kırmızı" sınıfı.

NE OLDU (2026-08-18, ölçüldü): `training_archive/` ruff'tan muaf tutulacaktı. Muafiyet YALNIZ
`.pre-commit-config.yaml`'a yazıldı. Sonuç: `git commit` yerelde SORUNSUZ geçti (pre-commit
kendi exclude'unu uyguladı), ama CI `ruff check --output-format=github .` komutunu koşuyor ve o
**`pyproject.toml`**'u okuyor → `lint` işi 10 hatayla kırmızı döndü (ca280ea, b850c08).

Bu sınıfın zararı gecikmeli: geliştirici yerelde yeşil görüp push eder, kırmızı e-posta 2 dakika
sonra gelir ve "CI yine bozuk" yorgunluğu üretir. Asıl kural basit — **muafiyetin TEK KAYNAĞI
`pyproject.toml`'dur**; pre-commit'in ruff hook'u `--force-exclude` ile zaten ona uyar.
Bu kapı, pre-commit'te olup pyproject'te olmayan bir muafiyet kalmasını engeller.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
PYPROJECT = KOK / "pyproject.toml"
PRECOMMIT = KOK / ".pre-commit-config.yaml"


def _pyproject_muafiyetleri() -> set[str]:
    """`[tool.ruff]` altındaki `extend-exclude` / `exclude` dizilerini oku.

    ⚠️ `tomllib` KULLANILMIYOR: 3.11+ gerektiriyor, hem yerel embedded Python hem CI **3.10**.
    `tomli` de `requirements-test.txt`te yok → CI'da atlanır ve kapı tam ihtiyaç duyulan yerde
    ölü kalırdı. Onun yerine dizinin gövdesi hedefli okunuyor; yorum satırları önce atılıyor
    ki içlerindeki tırnak/kesme işaretleri yol sanılmasın.
    """
    metin = PYPROJECT.read_text(encoding="utf-8")
    yollar: set[str] = set()
    for anahtar in ("extend-exclude", "exclude"):
        m = re.search(rf"^\s*{anahtar}\s*=\s*\[(.*?)\]", metin, re.S | re.M)
        if not m:
            continue
        govde = "\n".join(s.split("#", 1)[0] for s in m.group(1).splitlines())
        yollar.update(re.findall(r'"([^"]+)"', govde))
    return {y.strip("/^$").lstrip("./") for y in yollar}


def _precommit_ruff_muafiyetleri() -> set[str]:
    """`.pre-commit-config.yaml`'daki ruff/ruff-format hook'larının `exclude:` regex'leri.

    YAML ayrıştırıcı bağımlılığı eklememek için hedefli okuma: ruff hook bloğu içindeki
    `exclude: '<regex>'` satırlarından yol adlarını çıkarır (`^(a|b)/` → {a, b}).
    """
    metin = PRECOMMIT.read_text(encoding="utf-8")
    # ruff deposunun bloğu: `- repo: ...ruff-pre-commit` ile başlar, sonraki `- repo:`e kadar.
    blok = re.search(r"-\s*repo:.*?ruff-pre-commit.*?(?=\n\s*-\s*repo:|\Z)", metin, re.S)
    if not blok:
        pytest.skip("pre-commit'te ruff hook'u yok")
    yollar: set[str] = set()
    for kalip in re.findall(r"^\s*exclude:\s*['\"](.+?)['\"]\s*$", blok.group(0), re.M):
        ham = kalip.strip("^$")
        ic = re.fullmatch(r"\((.+)\)/?", ham.rstrip("/"))
        parcalar = ic.group(1).split("|") if ic else [ham.rstrip("/")]
        yollar.update(p.strip("/") for p in parcalar if p.strip("/"))
    return yollar


def test_KRITIK_precommit_ruff_muafiyeti_pyprojectte_de_VAR():
    """pre-commit'te muaf ama pyproject'te değil → CI kırmızı, yerel yeşil."""
    eksik = sorted(_precommit_ruff_muafiyetleri() - _pyproject_muafiyetleri())
    assert not eksik, (
        f"Bu yollar .pre-commit-config.yaml'da ruff'tan muaf ama pyproject.toml'da DEĞİL: {eksik}. "
        "CI `ruff check .` komutunu pyproject ile koşar → yerelde geçen commit CI'da KIRMIZI döner "
        "(2026-08-18'de tam bu oldu). Muafiyeti önce pyproject.toml `[tool.ruff] extend-exclude`'a "
        "yazın."
    )


def test_KARSIT_KANIT_kapi_bos_gecmiyor():
    """İki tarafın da gerçekten okunabildiğini kanıtla — boş küme karşılaştırması işe yaramaz."""
    pp = _pyproject_muafiyetleri()
    pc = _precommit_ruff_muafiyetleri()
    assert len(pp) > 5, f"pyproject muafiyetleri okunamadı ({pp}) — kapı boş dönüyor"
    assert pc, "pre-commit ruff muafiyetleri okunamadı — kapı boş dönüyor"
    assert "training_archive" in pp, (
        "training_archive pyproject'te muaf değil — donmuş arşiv lint'lenirse CI kırmızı döner"
    )
    assert "training_archive" in pc, "training_archive pre-commit'te muaf değil"
