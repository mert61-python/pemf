# -*- coding: utf-8 -*-
"""AII-1.6 (AI incelemesi, A1) — C9'un yapısal `sys.path` kapısı yalnız `sys.path.insert/append` metnini görüyor (KÖR KAPI, düşük).

ÖLÇÜLDÜ (`amut.sh` C9-a…d, `petri_cv_v2/pipeline.py`): `sys.path.extend([...])`, `sys.path[0:0] = [...]`, `site.addsitedir(...)`,
`importlib.util.spec_from_file_location` biçimlerinin HİÇBİRİNİ regex görmüyor. Sınıfı ikiye bölen biçimler (dilim / addsitedir /
dosyadan yükleme + üst düzey `inference_em_petri` içe aktarımı) davranış denetimi `pp.PetriPredictor is paket.PetriPredictor` ile
YİNE KIRMIZI — ama yalnız yol EKLEYEN biçim (`extend`, içe aktarım paket yolundan kalır) her iki denetimde YEŞİL: süreç geneli
`sys.path`'e `ai_hub/inference_em_petri` girer → `inference_em_petri` adı başka tüketiciler için üst düzey modül olur (aynı sınıf
iki modül — `tests/golden/yukleyici.py` notunun sınıfı). v1 emekli olduğundan (C6) ai_hub'da sys.path'e dokunan HİÇBİR modül yok →
kural tüm ai_hub için AST'den, biçimden bağımsız ölçülebilir.
"""

from __future__ import annotations

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def _ihlaller(p: Path) -> list[str]:
    agac = ast.parse(p.read_text(encoding="utf-8"))
    # Dosyadan modül yükleme yalnız CV profillerinde yasak: `inference_em_*` CLI geri düşüşü (`em_girdi`, paket yolda değilken) meşru.
    cv_profili = any(d in p.parts for d in ("petri_cv_v2", "phantom_cv_v3", "cv_ortak"))
    # `import sys as _s` takma adı da sys sayılır (ilk sürümde `sys` adına bakılıyordu: `_s.path.extend` mutantı YEŞİL kaldı)
    sys_adlari = {"sys"} | {
        a.asname or a.name for n in ast.walk(agac) if isinstance(n, ast.Import) for a in n.names if a.name == "sys"
    }
    out = []
    for n in ast.walk(agac):
        # sys.path'e her türlü erişim: .insert/.append/.extend, [i:j] = …, += …, doğrudan atama
        if (
            isinstance(n, ast.Attribute)
            and n.attr == "path"
            and isinstance(n.value, ast.Name)
            and n.value.id in sys_adlari
        ):
            out.append(f"{p.relative_to(KOK).as_posix()}:{n.lineno} sys.path")
        if isinstance(n, ast.ImportFrom) and n.module == "sys" and any(a.name == "path" for a in n.names):
            out.append(f"{p.relative_to(KOK).as_posix()}:{n.lineno} from sys import path")
        if isinstance(n, ast.Attribute) and (
            n.attr == "addsitedir" or (n.attr == "spec_from_file_location" and cv_profili)
        ):
            out.append(f"{p.relative_to(KOK).as_posix()}:{n.lineno} {n.attr}")
    return out


def test_KRITIK_ai_hub_modulleri_sys_path_e_DOKUNMAZ_ve_dosyadan_modul_YUKLEMEZ():
    dosyalar = [p for p in sorted((KOK / "ai_hub").rglob("*.py")) if "__pycache__" not in p.parts]
    assert len(dosyalar) >= 80, f"tarama dar ({len(dosyalar)})"
    ihlal = [i for p in dosyalar for i in _ihlaller(p)]
    assert not ihlal, (
        "ai_hub modülü sys.path'e dokunuyor / dosyadan modül yüklüyor (paket içe aktarımı kullanın):\n  "
        + "\n  ".join(ihlal)
    )
