# -*- coding: utf-8 -*-
"""Y205 · S-D5.21 (sahip, 2026-10-28) — M-4 (`410e12ca`) profil okuyucusunu (`Read-PemfProfilEnv`) PS 5.1'de de UTF-8'e çevirdi; profil
elle "ANSI" kaydedilirse ASCII dışı değer artık iki sürümde de bozulur. `deploy/README.md` "profil UTF-8 kaydedilir" der — ve bu not
kodla aynı kalır: iki kurulum betiğinin okuyucusu UTF-8 okumayı bırakırsa not yanlışa düşer (kapı ikisini birlikte tutar).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("betik", ["setup_services.ps1", "install_backend_service.ps1"])
def test_profil_okuyucusu_UTF8_okur(betik):
    kod = (KOK / "scripts" / betik).read_text(encoding="utf-8")
    m = re.search(r"function Read-PemfProfilEnv\b.*?\n\}", kod, re.S)
    assert m, f"aparat: {betik} içinde Read-PemfProfilEnv bulunamadı"
    okuma = re.findall(r"Get-Content\b[^\n]*", m.group(0))
    assert okuma and all(re.search(r"-Encoding\s+UTF8\b", s, re.I) for s in okuma), (
        f"{betik}: profil okuyucusu UTF-8 okumuyor — deploy/README notunu yeniden ölç: {okuma}"
    )


def test_deploy_README_profil_UTF8_kaydedilir_notu_VAR():
    metin = (KOK / "deploy" / "README.md").read_text(encoding="utf-8")
    paragraflar = [p for p in re.split(r"\n\s*\n", metin) if "UTF-8" in p and "ANSI" in p and "Read-PemfProfilEnv" in p]
    assert paragraflar, (
        "deploy/README.md profilin UTF-8 kaydedilmesi gerektiğini (ANSI kaydı bozar) söylemiyor — S-D5.21"
    )
