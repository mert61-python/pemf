# -*- coding: utf-8 -*-
"""D6.40 (B-11.11) — doğrulama belgelerindeki yorumlayıcı yolu depodaki GERÇEK yorumlayıcıdır.

ÖLÇÜLEN DURUM (HEAD ebf1c3fe, 2026-10-28):
  · `docs/VERIFICATION.md:71` wheel denetimini `myenv\\Scripts\\python -c "import sqlcipher3"` ile anlatıyordu;
    `:99` testleri `py -3.10 -m pytest guii/tests` ile. Kök `README.md` ("Build Python'ı = gömülü") gömülü `python.exe`'nin
    TEK build yorumlayıcısı olduğunu, `myenv` ve sistem Python'ının KALDIRILDIĞINI söyler → iki komut temiz makinede çalışmaz
    (ya yok ya da başka bir Python'ın site-packages'ını ölçer — yanlış "wheel var/yok" sonucu).

İzinli biçim KÖK README'den okunur (sabit kopya değil): README "gömülü / python.exe / myenv … kaldırıldı" demeyi bırakırsa kapı
kırmızı olur ve bu kapı bilinçli güncellenir. `docs/RUNBOOK.md` (hat A belgesi) YALNIZ OKUNUR.
"""

from __future__ import annotations

import re
from pathlib import Path

from utils.path_utils import kaynak_kokunu_bul

KOK = Path(kaynak_kokunu_bul(__file__))
BELGELER = ("docs/VERIFICATION.md", "docs/RUNBOOK.md")
YASAK = (
    re.compile(r"myenv[\\/]+Scripts[\\/]+python", re.I),
    re.compile(r"(?<![\w-])py\s+-3(\.\d+)?\b"),
)
GOMULU = r"..\python.exe"


def _oku(yol: str) -> str:
    return (KOK / yol).read_text(encoding="utf-8")


def _cizgisiz(md: str) -> str:
    return re.sub(r"~~.*?~~", " ", md, flags=re.S)


def test_izinli_bicim_KOK_READMEden():
    s = [x for x in _oku("README.md").splitlines() if "Build Python'ı = gömülü" in x]
    assert len(s) == 1, "kök README'de 'Build Python'ı = gömülü' satırı tek olmalı (izinli biçimin kaynağı)"
    assert "python.exe" in s[0] and "myenv" in s[0] and "kaldırıldı" in s[0], (
        "kök README artık gömülü python.exe'yi tek build yorumlayıcısı diye anlatmıyor — bu kapıyı bilinçli güncelleyin"
    )


def test_dogrulama_belgeleri_KALDIRILMIS_yorumlayiciyi_KULLANMAZ():
    ihlal = []
    for yol in BELGELER:
        for no, satir in enumerate(_cizgisiz(_oku(yol)).splitlines(), 1):
            for r in YASAK:
                if r.search(satir):
                    ihlal.append(f"{yol}:{no} {satir.strip()[:120]}")
    assert not ihlal, "kaldırılmış yorumlayıcı (myenv / py -3.x) — gömülü `..\\python.exe` kullanın:\n  " + "\n  ".join(
        ihlal
    )


def test_VERIFICATION_gomulu_yorumlayici_ve_SEVK_AGACI_komutu():
    m = _cizgisiz(_oku("docs/VERIFICATION.md"))
    assert f'{GOMULU} -c "import sqlcipher3"' in m, "VERIFICATION wheel denetimi gömülü yorumlayıcıyla yazılmalı"
    assert f"{GOMULU} -m pytest tests" in m, "VERIFICATION test komutu gömülü yorumlayıcıyla, depo kökünden yazılmalı"
    assert re.search(r"Get-ChildItem[^\n]*_internal[^\n]*sqlcipher3", m), (
        "VERIFICATION sevk ağacını okuyan komutu vermeli"
    )
