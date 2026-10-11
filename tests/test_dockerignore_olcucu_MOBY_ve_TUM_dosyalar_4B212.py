# -*- coding: utf-8 -*-
"""4B-2.12 (4-B incelemesi A2) — D4.20'nin `.dockerignore` ölçücüsü (`_dislanir_mi`) moby'den ayrışıyor ve TEK örnek dosyaya bakıyor.

(1) `_dislanir_mi` `fnmatch` kullanır: `*` ve `?` `/`'yi de geçer, `**/` → `*` indirgenir. Docker belgesinin kendi örnekleri:
    `*/temp*` YALNIZ bir alt düzeyi dışlar (`a/b/temp` DIŞLANMAZ), `temp?` tek karakter, `*.md` yalnız kökte. Ölçücü ilkini yanlış
    "dışlanır" sayar (ölçüldü) → bir ignore deseni Docker'da dışlamadığı hâlde kapı YEŞİL.
(2) Kapı alt bağlamdan yalnız `apps/ui/package.json`'a bakar: `apps/ui/` satırı `apps/ui/package.json`'a daraltılırsa (geri kalan arayüz
    kaynağı backend/AI imajına girer) D4.20 + COPY + taşınmış-dizin kapıları YEŞİL (ölçüldü, `kayit/4212_*`).
Bu kapı ölçücüyü Docker belgesi örnekleriyle kalibre eder ve alt bağlamın TÜM takipli dosyalarını sınar.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tests"))

import test_docker_DOCKERFILE_ve_IGNORE_yollari_GUNCEL_D420 as d420  # noqa: E402
from test_betikler_ACILIYOR import _compose_contextleri, _takipli  # noqa: E402

#: Docker belgesi (.dockerignore) örnekleri + moby patternmatcher anlamı: (yol, desenler, dışlanır mı)
_KALIBRE = [
    ("a/temp/x", ["*/temp*"], True),
    ("a/b/temp", ["*/temp*"], False),
    ("a/b/temp", ["*/*/temp*"], True),
    ("temp1", ["temp?"], True),
    ("tempab", ["temp?"], False),
    ("x/y/z.md", ["**/*.md"], True),
    ("README.md", ["*.md", "!README.md"], False),
    ("docs/a.md", ["*.md"], False),
    ("apps/ui/src/App.tsx", ["apps/ui/"], True),
    ("apps/ui/src/App.tsx", ["apps/ui", "!apps/ui/src/App.tsx"], False),
    ("xnode_modules/a", ["**/node_modules"], False),
    ("a/node_modules/b", ["**/node_modules"], True),
]


@pytest.mark.parametrize("yol,desenler,beklenen", _KALIBRE)
def test_olcucu_DOCKER_belgesi_ornekleriyle_KALIBRE(yol, desenler, beklenen):
    assert d420._dislanir_mi(yol, desenler) is beklenen, (
        f"_dislanir_mi({yol!r}, {desenler}) Docker'dan AYRISTI (beklenen {beklenen})"
    )


def test_KRITIK_alt_baglamin_TUM_takipli_dosyalari_DISLANIR():
    ctx = _compose_contextleri()
    baglamlar = set(ctx.values())
    sizan, bakilan = [], 0
    for df, taban in ctx.items():
        ignore = Path(df + ".dockerignore")
        if not ignore.is_file():
            ignore = taban / ".dockerignore"
        desenler = d420._desenler(ignore) if ignore.is_file() else []
        for alt in baglamlar:
            if alt == taban or taban not in alt.parents:
                continue
            rel = alt.relative_to(taban).as_posix()
            dosyalar = [f for f in _takipli([f"{rel}/**"]) if f.startswith(rel + "/")]
            assert len(dosyalar) >= 20, f"VAKUM: {rel} altinda {len(dosyalar)} takipli dosya"
            bakilan += len(dosyalar)
            girenler = [f for f in dosyalar if not d420._dislanir_mi(f, desenler)]
            if girenler:
                sizan.append(f"{Path(df).name} ({ignore.name}) → {len(girenler)} dosya, ör. {girenler[:3]}")
    assert bakilan >= 40, f"VAKUM: {bakilan}"
    assert not sizan, f"arayuz kaynagi backend/AI imajina GIRIYOR: {sizan}"
