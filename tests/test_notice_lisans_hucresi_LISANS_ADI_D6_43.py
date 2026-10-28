# -*- coding: utf-8 -*-
"""D6.43 (B-11.15 · B-11.17 · Ö.4-Y4) — NOTICE lisans hücresi bir LİSANS ADIDIR; AGPL karar notunun modül sayısı koddan ölçülür.

ÖLÇÜLEN DURUM (HEAD ebf1c3fe, 2026-10-28 — guii `pemf-app-packages/base-deps.zip` YALNIZ OKUNARAK, 100 METADATA):
  · `THIRD_PARTY_LICENSES.md` Python tablosunda 7 hücre lisans adı değildi: cycler "Copyright (c) 2015, matplotlib project",
    kiwisolver "=========================", matplotlib "License agreement for …", numpy / scipy "Copyright (c) …",
    python-dateutil "Dual License", scikit-image "Files: *". İki kök neden (`scripts/lisans_envanteri_uret.py` `metadata_lisansi`):
    (1) `License:` alanının İLK SATIRI sınıflandırıcıdan ÖNCE geliyordu; (2) başlık yalnız ilk 80 satırda taranıyordu — lisans
    METNİNİ `License:` alanına koyan paketlerin sınıflandırıcısı 82.–981. satırdadır (numpy 981). Aynı `[:80]` sınırı
    `kopyleft_metadata_mu`'da da vardı: uzun lisans metninin ardındaki GPL sınıflandırıcısı kopyleft kapısına GÖRÜNMEZDİ.
  · pi-heif: `License: BSD-3-Clause` + `Classifier: … GNU Lesser General Public License v3 (LGPLv3)` — hücre yalnız BSD diyordu.
  · `docs/AGPL-KARARI.md` "üretim yolundaki iki modül", "Üç model hâlâ .pt", "diğer 24 — hepsi izin verici" — ölçüm: ultralytics'i
    içe aktaran ai_hub modülü 7 (AST), METADATA 100, LGPL taşıyanlar var (pi-heif, soxr, zeroconf).

⚠️ Ö.4-Y4: AI model AĞIRLIK lisans envanteri YAPILMAZ — bu kapı yalnız Python bağımlılık NOTICE'ını ve karar notunun iç tutarlılığını
ölçer. Lisans adı imzası BU TESTTE pinlidir (üreticiden okunmaz).
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from utils.path_utils import kaynak_kokunu_bul

KOK = Path(kaynak_kokunu_bul(__file__))
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

#: Bilinen lisans adı / SPDX imzası — testte PİNLİ.
LISANS_ADI = re.compile(
    r"\b(MIT|BSD|Apache|MPL|Mozilla|ISC|EPL|EDL|Eclipse|L?GPL|AGPL|Affero|General Public License|PSF|"
    r"Python Software Foundation|HPND|Historical Permission|Unlicense|Public Domain|CC0|Zlib)",
    re.I,
)


def _lisans_adi(hucre: str) -> bool:
    h = hucre.strip()
    return bool(h) and not h.lower().startswith(("copyright", "license agreement")) and bool(LISANS_ADI.search(h))


def _meta(ad: str, surum: str, lisans_satirlari: list[str], siniflar: list[str], uzun: int = 0) -> str:
    """Gerçek METADATA biçimi: `License:` çok satırlı lisans METNİ olabilir (devam satırları girintili), sınıflandırıcılar ARDINDAN."""
    satirlar = ["Metadata-Version: 2.1", f"Name: {ad}", f"Version: {surum}"]
    satirlar += [f"License: {lisans_satirlari[0]}"] + [f"        {s}" for s in lisans_satirlari[1:]]
    if uzun:
        # gerçek METADATA'da lisans metnindeki boş satır BOŞLUKLU devam satırıdır ("        ") — başlık SONU değildir
        satirlar += ["        "]
    satirlar += ["        Redistribution and use in source and binary forms, with or without modification ..."] * uzun
    satirlar += [f"Classifier: License :: OSI Approved :: {s}" for s in siniflar]
    return "\n".join(satirlar) + "\n\nREADME govdesi — License: MIT (govde SAYILMAZ)\n"


#: (dist-info adı, METADATA) — base-deps.zip'te ÖLÇÜLEN yapının kopyası (sınıflandırıcı satır konumları dahil).
FIKSTUR = {
    "cycler-0.12.1": _meta("cycler", "0.12.1", ["Copyright (c) 2015, matplotlib project"], ["BSD License"], uzun=30),
    "kiwisolver-1.5.0": _meta("kiwisolver", "1.5.0", ["========================="], ["BSD License"], uzun=80),
    "matplotlib-3.10.9": _meta(
        "matplotlib",
        "3.10.9",
        ["License agreement for matplotlib versions 1.3.0 and later"],
        ["Python Software Foundation License"],
        uzun=800,
    ),
    "numpy-1.26.4": _meta("numpy", "1.26.4", ["Copyright (c) 2005-2023, NumPy Developers."], ["BSD License"], uzun=970),
    "python_dateutil-2.9.0.post0": _meta(
        "python-dateutil", "2.9.0.post0", ["Dual License"], ["BSD License", "Apache Software License"]
    ),
    "scikit_image-0.25.2": _meta("scikit-image", "0.25.2", ["Files: *"], ["BSD License"], uzun=150),
    "scipy-1.15.3": _meta(
        "scipy",
        "1.15.3",
        ["Copyright (c) 2001-2002 Enthought, Inc. 2003-2024, SciPy Developers."],
        ["BSD License"],
        uzun=910,
    ),
    "pi_heif-1.4.0": _meta("pi-heif", "1.4.0", ["BSD-3-Clause"], ["GNU Lesser General Public License v3 (LGPLv3)"]),
}


def _sahte_paket(tmp_path: Path, fikstur: dict[str, str]) -> Path:
    z = tmp_path / "base-deps.zip"
    with zipfile.ZipFile(z, "w") as f:
        for ad, meta in fikstur.items():
            f.writestr(f"PEMF_Backend/_internal/{ad}.dist-info/METADATA", meta)
    return z


def test_KRITIK_uretec_lisans_hucresini_LISANS_ADI_uretir(tmp_path):
    from scripts import lisans_envanteri_uret as uretec

    tablo = uretec.paket_lisanslari(_sahte_paket(tmp_path, FIKSTUR))
    assert len(tablo) == len(FIKSTUR), f"aparat: sahte paketten {len(tablo)} METADATA okundu"
    kotu = {ad: lis for ad, (_s, lis) in tablo.items() if not _lisans_adi(lis)}
    assert not kotu, f"NOTICE hücresi lisans ADI değil (lisans metninin ilk satırı): {kotu}"
    assert "LGPL" in tablo["pi-heif"][1].upper(), (
        f"pi-heif LGPLv3 sınıflandırıcısı hücreye yansımıyor: {tablo['pi-heif'][1]!r}"
    )
    d = tablo["python-dateutil"][1]
    assert "BSD" in d and "Apache" in d, f"python-dateutil çift lisansı (BSD + Apache) hücrede değil: {d!r}"


def test_KRITIK_kopyleft_kapisi_UZUN_lisans_metninin_ARDINI_gorur():
    from scripts import lisans_envanteri_uret as uretec

    meta = _meta("gizli", "1.0", ["Copyright (c) 2024 Ornek"], ["GNU General Public License v3 (GPLv3)"], uzun=120)
    assert uretec.kopyleft_metadata_mu(meta), (
        "uzun lisans metninin ardındaki GPL sınıflandırıcısı kopyleft kapısına GÖRÜNMÜYOR"
    )
    govde = (
        _meta("temiz", "1.0", ["MIT"], ["MIT License"])
        + "Classifier: License :: OSI Approved :: GNU General Public License\n"
    )
    assert not uretec.kopyleft_metadata_mu(govde), "README GÖVDESİ başlık sayıldı (karşıt kanıt)"


def test_KRITIK_THIRD_PARTY_python_tablosu_hucreleri_LISANS_ADI():
    metin = (KOK / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    bas = metin.index("## Dağıtılan pakette tespit edilen bileşenler")
    son = metin.index("### Arayüz, site, DEMA ve launcher (npm)")
    satirlar = [s for s in metin[bas:son].splitlines() if re.match(r"^\|\s*`", s)]
    assert len(satirlar) >= 100, f"aparat: Python tablosunda {len(satirlar)} satır"
    kotu = [s for s in satirlar if not (_lisans_adi(s.split("|")[3]) or "doğrulanmadı" in s.split("|")[3])]
    assert not kotu, "THIRD_PARTY_LICENSES lisans hücresi lisans ADI değil:\n  " + "\n  ".join(kotu)
    pi = [s for s in satirlar if s.startswith("| `pi-heif`")]
    assert pi and "LGPL" in pi[0], f"pi-heif satırı LGPLv3 sınıflandırıcısını göstermiyor: {pi}"


def _ultralytics_modulleri() -> set[str]:
    dosyalar = subprocess.run(
        ["git", "-C", str(KOK), "ls-files", "-z", "ai_hub"], capture_output=True, check=True
    ).stdout
    out: set[str] = set()
    for rel in dosyalar.decode("utf-8").split("\0"):
        if not rel.endswith(".py"):
            continue
        try:
            agac = ast.parse((KOK / rel).read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for d in ast.walk(agac):
            adlar = []
            if isinstance(d, ast.Import):
                adlar = [a.name for a in d.names]
            elif isinstance(d, ast.ImportFrom) and d.module:
                adlar = [d.module]
            if any(a == "ultralytics" or a.startswith("ultralytics.") for a in adlar):
                out.add(rel.split("/")[1])
    return out


def test_KRITIK_AGPL_karari_modul_sayisi_KODLA_ayni():
    metin = re.sub(r"~~.*?~~", " ", (KOK / "docs" / "AGPL-KARARI.md").read_text(encoding="utf-8"), flags=re.S)
    moduller = _ultralytics_modulleri()
    assert moduller, "aparat: ultralytics içe aktaran ai_hub modülü bulunamadı"
    beyan = re.findall(r"ultralytics'i içe aktaran `ai_hub` modülü:\s*\*\*(\d+)\*\*", metin)
    assert beyan, "AGPL-KARARI ölçülen modül sayısını ('ultralytics'i içe aktaran `ai_hub` modülü: **N**') yazmalı"
    assert {int(b) for b in beyan} == {len(moduller)}, (
        f"AGPL-KARARI modül sayısı {beyan} ≠ AST {len(moduller)} ({sorted(moduller)})"
    )
    for ad in moduller:
        assert f"`{ad}" in metin, f"AGPL-KARARI ultralytics modülü `{ad}`'i anmalı"
    assert not re.search(r"hepsi izin verici", metin), (
        "AGPL-KARARI 'hepsi izin verici' diyor — LGPL (pi-heif, soxr, zeroconf) var"
    )
    acik = re.sub(r"~~.*?~~", " ", (KOK / "docs" / "acik-isler-2026-09-12.md").read_text(encoding="utf-8"), flags=re.S)
    a1 = [s for s in acik.splitlines() if s.startswith("| A1 |")]
    assert len(a1) == 1 and not re.search(r"\*\*iki\*\* modül", a1[0]), f"acik-isler A1 bayat modül sayısı: {a1}"
