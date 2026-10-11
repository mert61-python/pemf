# -*- coding: utf-8 -*-
"""4B-3.1 (A3 inceleme) — `_modul_yukleme_bicimi` belgesi D4.13'ten sonra BAYAT: `EncryptedLoader` artık `__file__` ATAR.

D4.13 (`d504fef3`) `EncryptedFinder`'ı `spec_from_file_location`'a çevirdi → şifreli modülün `__file__`'ı diskteki `.pyenc`.
`servers/ai_router._modul_yukleme_bicimi`'nin belgesi hâlâ "`EncryptedLoader` ise (`utils/encrypted_import.py:88` —
`spec_from_loader` + `get_filename` yok) `__file__` ATAMAZ. İkisi de ölçüldü" diyor → ölçülmüş diye sunulan yanlış öncül
(uzantıya bakmama kuralının gerekçesinin yarısı). Kapı DAVRANIŞI (gerçek şifreleyici + gerçek install) ölçer ve belgenin o
davranışla çelişmediğini ister.
"""

from __future__ import annotations

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
AI_ROUTER = KOK / "apps" / "backend" / "servers" / "ai_router.py"


def _belge() -> str:
    agac = ast.parse(AI_ROUTER.read_text(encoding="utf-8"))
    for d in agac.body:
        if isinstance(d, ast.FunctionDef) and d.name == "_modul_yukleme_bicimi":
            return ast.get_docstring(d) or ""
    raise AssertionError("_modul_yukleme_bicimi ai_router.py'de bulunamadı")


def test_KRITIK_belge_EncryptedLoader_davranisiyla_celismez(tmp_path):
    import test_sifreli_modul_DOSYA_YOLUNU_bilir_D413 as d413

    paket = d413._sifreli_dist(tmp_path)
    s = d413._ice_aktar(tmp_path, paket)
    assert "hata" not in s, s.get("hata")
    # GERÇEK davranış (D4.13 sonrası): EncryptedLoader `__file__`'ı diskteki .pyenc'e bağlar.
    assert s["has_location"] is True and s["file"].endswith(".pyenc"), s
    belge = _belge()
    i = belge.find("EncryptedLoader")
    assert i >= 0, "belge EncryptedLoader'ı artık anmıyor — kapıyı güncelle"
    parca = belge[i : i + 220]
    assert "ATAMAZ" not in parca and "spec_from_loader" not in parca, (
        "_modul_yukleme_bicimi belgesi EncryptedLoader'ın __file__ ATAMADIĞINI 'ölçüldü' diye söylüyor; D4.13'ten beri "
        f"atıyor (has_location True, __file__ = {Path(s['file']).name}). Bayat öncül: {parca!r}"
    )
