# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""PAKET SINIRLARI TANIMLI (2026-09-17).

OLCULEN ACIK. `pyproject.toml` 96 satir ve YALNIZ arac ayari tasiyordu: `[project]` yok,
`[build-system]` yok, `setup.py` yok. Depo kurulabilir bir Python dagitimi degildi; kok
dizinin kendisi import kokuydu.

Somut maliyetleri:
  · `controllers/`, `scripts/`, `build_tools/` paket gibi import ediliyor ama
    `__init__.py`'leri YOK — PEP 420 ortam-paketlerine bel baglanmis. Bir ad cakismasi
    ya da `sys.path` sirasi degisikligi sessizce yanlis modulu yukleyebilir.
  · IEC 62304 acisindan "yazilim ogesi" tanimlamak icin kurulabilir bir birim ve
    makine-okunur surum metadatasi yok.

⚠️ SURUM DORDUNCU KEZ YAZILMAZ. `[project] version = "1.9.50"` yazmak, surumu DORDUNCU
bir yere koymak olurdu: versions.json (tek kaynak) -> VERSION -> CHANGELOG -> pyproject.
Bu depo tam bu tuzaga README'de UC kez dustu (bkz. test_readme_surum_bayatlamaz.py).
Bu yuzden `dynamic = ["version"]` + `[tool.setuptools.dynamic] version = {file="VERSION"}`
kullanilir: pyproject VERSION'dan, VERSION da versions.json'dan turer.

⚠️ `tests/` BILEREK DISARIDA: oraya `__init__.py` koymak pytest'in kok-dizin tabanli
toplama davranisini degistirir. Denetim de onu istemiyordu.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# ⚠️ `tomllib` YALNIZ Python 3.11+. Bu depo 3.10'a KILITLI (CI matrisi de 3.10) — ilk
# yazimda `import tomllib` kullandim ve test TOPLAMA asamasinda coktu. `tomli` zaten
# kurulu (pytest onu kullaniyor); 3.11+ makinelerde de calissin diye ikisi de denenir.
try:  # pragma: no cover - surume bagli dal
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover
    import tomli as _toml

KOK = Path(__file__).resolve().parents[1]
_PYPROJECT = KOK / "pyproject.toml"
_VERSION = KOK / "VERSION"
_SURUMLER = KOK / "versions.json"

#: `__init__.py` tasimasi gereken, uretimde/araclarda paket gibi import edilen dizinler.
_PAKET_DIZINLERI = ("controllers", "scripts", "build_tools")

#: ⚠️ tests/ BILEREK YOK — pytest toplama davranisini bozar.
_ISTISNA = ("tests",)


def _tomi() -> dict:
    return _toml.loads(_PYPROJECT.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════════════════════════
# ASIL SOZLESME
# ═══════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("dizin", _PAKET_DIZINLERI)
def test_KRITIK_paket_dizininde_init_VAR(dizin: str):
    """⚠️ BU TEST DUZELTMEDEN ONCE KIRMIZIYDI (uc dizinde de `__init__.py` yoktu)."""
    p = KOK / dizin
    assert p.is_dir(), f"{dizin}/ agacta yok — kapi bayatlamis olabilir"
    assert (p / "__init__.py").exists(), (
        f"{dizin}/__init__.py YOK -> paket PEP 420 ortam-paketi olarak cozuluyor. "
        "Ad cakismasi ya da sys.path sirasi degisikliginde SESSIZCE yanlis modul yuklenebilir."
    )


def test_KRITIK_pyproject_PROJE_metadatasi_TASIR():
    """`[project]` + `[build-system]` olmadan depo kurulabilir bir birim degildir."""
    t = _tomi()
    assert "project" in t, "[project] blogu yok -> yazilim ogesi tanimlanamiyor (IEC 62304)"
    # ⚠️ "blok var mi" YETMEZ (mutasyonla olculdu): `build-backend` satirini silen mutasyon
    # kapiyi YESIL birakti, cunku `[build-system]` tablosu `requires` ile ayakta kaliyordu.
    # Backend'siz bir `[build-system]` setuptools'un ESKI yoluna duser — beyan yarim kalir.
    bs = t.get("build-system", {})
    assert bs.get("requires"), "[build-system] requires yok -> `pip install .` bagimliligi cozemez"
    assert bs.get("build-backend"), (
        "[build-system] build-backend YOK -> beyan yarim; kurulum eski/ongorulemez yola duser"
    )
    assert t["project"].get("name"), "[project] name bos"
    assert t["project"].get("description"), "[project] description bos -> metadata anlamsiz"


def test_KRITIK_surum_DORDUNCU_kez_YAZILMAZ():
    """⚠️ Surum sabiti pyproject'e YAZILMAZ; VERSION'dan TURETILIR.

    Elle yazilan her surum bayatlar — bu depo README'de UC kez yasadi.
    """
    t = _tomi()
    proje = t["project"]
    assert "version" not in proje, (
        f"[project] version SABIT yazilmis ({proje.get('version')!r}) -> bu, surumun DORDUNCU "
        "kopyasidir ve bayatlar. `dynamic = [\"version\"]` kullanin."
    )
    assert "version" in proje.get("dynamic", []), (
        "[project] dynamic listesinde 'version' yok -> surum nereden gelecek belirsiz"
    )
    dyn = t.get("tool", {}).get("setuptools", {}).get("dynamic", {})
    assert dyn.get("version", {}).get("file") == "VERSION", (
        "[tool.setuptools.dynamic] version dosyasi `VERSION` olmali -> tek kaynak zinciri: "
        "versions.json -> VERSION -> pyproject"
    )


def test_KRITIK_VERSION_versions_json_ile_UYUMLU():
    """Zincirin ilk halkasi: `VERSION` gercekten `versions.json`dan turemis olmali."""
    surum = _VERSION.read_text(encoding="utf-8").strip()
    beklenen = json.loads(_SURUMLER.read_text(encoding="utf-8"))["backend"]
    assert surum == beklenen, (
        f"VERSION={surum!r} ama versions.json backend={beklenen!r} -> zincir kopmus. "
        "`build_tools/sync_versions.ps1` calistirin."
    )
    assert re.fullmatch(r"\d+\.\d+\.\d+", surum), f"beklenmeyen surum bicimi: {surum!r}"


# ═══════════════════════════════════════════════════════════════════════════════════════
# KARSIT-KANITLAR
# ═══════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("dizin", _ISTISNA)
def test_KARSIT_KANIT_tests_dizinine_init_EKLENMEZ(dizin: str):
    """⚠️ Kural "her dizine __init__.py" ya kaymamali.

    `tests/__init__.py` pytest'in kok-dizin tabanli toplama davranisini degistirir ve
    335 test dosyasinin import yolunu bozabilir. Denetim de bunu istemiyordu.
    """
    assert not (KOK / dizin / "__init__.py").exists(), (
        f"{dizin}/__init__.py EKLENMIS -> pytest toplama davranisi degisir. "
        "Kural yalnizca URETIM/ARAC paketleri icindir."
    )


def test_KARSIT_KANIT_init_dosyalari_BOS_KABUK_degil():
    """`__init__.py` eklemek bir KARAR'dir; neden eklendigi dosyada yazili olmali.

    Bos bir dosya, sonraki kisiye "silinebilir mi?" sorusunu biraktirir ve silinince
    kapi kirmizi doner ama sebebi anlasilmaz.
    """
    for dizin in _PAKET_DIZINLERI:
        metin = (KOK / dizin / "__init__.py").read_text(encoding="utf-8").strip()
        assert len(metin) >= 40, (
            f"{dizin}/__init__.py bos/kisa -> neden var oldugu yazili degil. "
            "Paket sinirini ACIKLAYAN bir docstring yazin."
        )


def test_KARSIT_KANIT_mevcut_ARAC_ayarlari_KAYBOLMADI():
    """`[project]` eklerken dosyanin geri kalanini ezmek kolay bir hata olurdu.

    ruff/pytest/coverage/mypy ayarlari bu depoda CI kapilarini besliyor.
    """
    t = _tomi()
    for bolum in ("ruff", "pytest", "coverage", "mypy"):
        assert bolum in t.get("tool", {}), f"[tool.{bolum}] KAYBOLMUS -> CI kapisi sessizce gevser"
    assert t["tool"]["coverage"]["report"].get("fail_under"), "kapsam ratcheti (fail_under) kaybolmus"


def test_KARSIT_KANIT_setuptools_paketleri_ACIKCA_listeli():
    """Otomatik kesif duz-yerlesimde "Multiple top-level packages" ile PATLAR.

    Paketler acikca listelenmezse `pip install .` calismaz — yani `[build-system]`
    eklemek bir sey duzeltmemis, yalnizca yeni bir kirik yol acmis olurdu.
    """
    t = _tomi()
    paketler = t.get("tool", {}).get("setuptools", {}).get("packages")
    assert paketler, "[tool.setuptools] packages listesi yok -> otomatik kesif patlar"
    for zorunlu in ("servers", "services", "database", "utils", "controllers"):
        assert zorunlu in paketler, f"{zorunlu} paket listesinde yok -> kurulumda EKSIK giderdi"


def test_KARSIT_KANIT_ai_hub_paket_listesine_EKLENMEZ():
    """⚠️ `ai_hub` BILEREK disarida — "eksik" sanip eklemeyin.

    Uc gerekce, ucu de olculdu:
      1. 84 MB ve icinde 20 model agirligi var (`XGBoost.pkl` tek basina 50 MB).
      2. Kod korumasi karari geregi frozen EXE'de PYZ'den CIKARILIR
         (`PEMF_Backend_onedir.spec` -> `a.pure`dan silinir) ve diskteki `.pyd`/`.pyenc`
         olarak sevk edilir. Kurulabilir paket ilan etmek bu kararla CELISIR.
      3. Kurulum yolu zaten kullanilmiyor (`pip install -e .` depoda hic gecmiyor).

    Bu test, ileride birinin "listede eksik var" diye eklemesini bilincli bir karara
    donusturur.
    """
    t = _tomi()
    paketler = t["tool"]["setuptools"]["packages"]
    assert "ai_hub" not in paketler, (
        "ai_hub paket listesine eklenmis -> kod korumasi karariyla celisir "
        "(PYZ disinda .pyd olarak sevk edilir) ve 84 MB'lik bir dagitim birimi ilan eder"
    )


def test_KARSIT_KANIT_listelenen_her_paket_GERCEKTEN_var():
    """Liste bayatlarsa `pip install .` "package not found" ile duser."""
    t = _tomi()
    for ad in t["tool"]["setuptools"]["packages"]:
        p = KOK / ad
        assert p.is_dir(), f"paket listesinde `{ad}` var ama dizin YOK -> kurulum duser"
        assert (p / "__init__.py").exists(), (
            f"`{ad}` paket olarak listelenmis ama `__init__.py`si yok -> setuptools onu "
            "paket saymaz, sessizce EKSIK kurar"
        )
