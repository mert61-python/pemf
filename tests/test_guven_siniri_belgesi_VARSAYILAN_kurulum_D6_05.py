# -*- coding: utf-8 -*-
"""D6.05 (B-2.22) — güven sınırı belgeleri VARSAYILAN kurulumun gerçeğini anlatsın.

🔴 ÖLÇÜLEN DURUM (HEAD ebf1c3fe, 2026-10-28):
  · `apps/backend/servers/README.md` `patient_router.py` satırı "(hasta-auth guard)" diyordu — `_enforce_patient_auth`
    yalnız `PEMF_REQUIRE_PATIENT_AUTH=1` iken çalışır, varsayılan `"0"` (`patient_router.py:23`): LAN'dan hasta CRUD token'sız.
    Okuyan, hasta uçlarının korunduğunu sanıyordu. Kliniğin TAMAMINI silme ise yalnız cihazın kendisinden (A-03).
  · `docs/ARCHITECTURE.md` "LAN (güvenli) — auth-muaf" diyordu — ayrıcalıklı sınıf (`servers/auth.is_privileged_request`:
    dışa/içe aktarma, AI log silme, operatör kaydı) LAN'da da loopback ya da token ister; A-01 LAN'ı "güvenilir" sayar ve
    risk kaydı yazar.
  · ARCHITECTURE hasta/seans satırı "at-rest şifreli + PII maskeleme" diyordu — maskeleme varsayılan KAPALI
    (`thdb_pii.py` `PEMF_MASK_HISTORY_PII` varsayılanı `"0"`, opt-in — sahip kararı; geri EKLENMEZ: varsayılan-açık YAPILMAZ).

Kapı varsayılanları ÜRÜN KAYNAĞINDAN okur VE testte PİNLER: varsayılan değişirse belge de güncellenmeli (kırmızı).
"""

from __future__ import annotations

import re
from pathlib import Path

from utils.path_utils import kaynak_kokunu_bul

KOK = Path(kaynak_kokunu_bul(__file__))
SRV_README = KOK / "apps" / "backend" / "servers" / "README.md"
ARCH = KOK / "docs" / "ARCHITECTURE.md"
PATIENT_ROUTER = KOK / "apps" / "backend" / "servers" / "patient_router.py"
THDB_PII = KOK / "apps" / "backend" / "database" / "thdb_pii.py"
AUTH = KOK / "apps" / "backend" / "servers" / "auth.py"


def _oku(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _varsayilan(kaynak: Path, bayrak: str) -> str:
    bulunan = set(re.findall(r'os\.getenv\(\s*"' + re.escape(bayrak) + r'"\s*,\s*"([^"]*)"\s*\)', _oku(kaynak)))
    assert len(bulunan) == 1, f"{kaynak.name}: {bayrak} varsayılanı tek olmalı, bulunan {bulunan}"
    return bulunan.pop()


def _tek_satir(metin: str, anahtar: str) -> str:
    s = [x for x in metin.splitlines() if anahtar in x]
    assert len(s) == 1, f"'{anahtar}' satırı tam 1 kez olmalı, {len(s)}"
    return s[0]


def test_varsayilanlar_PINLI():
    assert _varsayilan(PATIENT_ROUTER, "PEMF_REQUIRE_PATIENT_AUTH") == "0", (
        "hasta-auth varsayılanı değişti — servers/README ve ARCHITECTURE güncellenmeli"
    )
    assert _varsayilan(THDB_PII, "PEMF_MASK_HISTORY_PII") == "0", (
        "PII maskesi varsayılanı değişti — ARCHITECTURE güncellenmeli (sahip kararı: varsayılan KAPALI)"
    )
    a = _oku(AUTH)
    assert "def is_privileged_request" in a and "def cihazin_kendisinden_mi" in a


def test_servers_readme_hasta_auth_VARSAYILAN_KAPALI_der():
    s = _tek_satir(_oku(SRV_README), "| `patient_router.py` |")
    assert "(hasta-auth guard)" not in s, (
        "servers/README: 'hasta-auth guard' varsayılan kurulumda YOK (PEMF_REQUIRE_PATIENT_AUTH=0)"
    )
    for b in ("PEMF_REQUIRE_PATIENT_AUTH=1", "VARSAYILAN KAPALI", "A-01", "A-03", "cihazin_kendisinden_mi"):
        assert b in s, f"servers/README patient_router satırı '{b}' içermeli"


def test_architecture_LAN_siniri_AYRICALIKLI_sinifi_anar():
    s = _tek_satir(_oku(ARCH), "1. **LAN")
    assert "LAN (güvenli)" not in s, "ARCHITECTURE: LAN 'güvenli' değil, 'güvenilir sayılır' (A-01) — risk kaydıyla"
    for b in ("A-01", "is_privileged_request", "A-03", "delete_all", "/api/auth/token"):
        assert b in s, f"ARCHITECTURE LAN satırı '{b}' içermeli"


def test_architecture_PII_maskesi_OPT_IN_der():
    s = _tek_satir(_oku(ARCH), "| Hasta/seans |")
    assert not re.search(r"\+ PII maskeleme\s*\|", s), (
        "ARCHITECTURE: PII maskeleme varsayılan KAPALI — koşulsuz anılmaz"
    )
    for b in ("PEMF_MASK_HISTORY_PII=1", "opt-in", "VARSAYILAN KAPALI", "A-09"):
        assert b in s, f"ARCHITECTURE hasta/seans satırı '{b}' içermeli"
