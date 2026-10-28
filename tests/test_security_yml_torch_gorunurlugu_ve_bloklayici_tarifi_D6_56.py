# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.56 (B-10.212) — `security.yml` pip-audit adımının yorumu iş akışının GERÇEĞİNİ söyler.

Kusur (HEAD ebf1c3fe): yorum "shiplenen AI yığını (torch …) TARANSIN … bilinen-ertelenen dışındaki CVE'ler GÖRÜNÜR" ve
"bloklayıcı yapmak için … continue-on-error'ı kaldır" diyordu. Oysa `torch==2.1.2+cpu` / `torchvision==0.16.2+cpu` PyPI'da
yok → pip-audit onları ATLAR (torch CVE'leri bu adımda görünmez); her pip-audit satırı `|| true` ile biter → yalnız
continue-on-error'ı kaldırmak adımı bloklayıcı YAPMAZ.

D67 orkestratör kolu: ilk yamada bu yorumun kapısı yoktu (tarifi eski hâline döndüren mutant YAŞADI). CI koşturulmaz (A-43);
dosya metin olarak okunur.
"""

from __future__ import annotations

from pathlib import Path

YML = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "security.yml"


def _yorum_ve_komut() -> tuple[str, list[str]]:
    satirlar = YML.read_text(encoding="utf-8").splitlines()
    yorum = "\n".join(s for s in satirlar if s.lstrip().startswith("#"))
    komut = [s for s in satirlar if not s.lstrip().startswith("#")]
    return yorum, komut


def test_bloklayici_tarifi_HER_pip_audit_satirindaki_or_true_yu_anar():
    yorum, komut = _yorum_ve_komut()
    audit = [s for s in komut if "pip-audit " in s and "pip install" not in s]
    assert audit, "security.yml'de pip-audit komutu bulunamadı — kapı bayatladı"
    if any(s.rstrip().endswith("|| true") for s in audit):
        assert "`|| true`" in yorum, (
            "pip-audit satırları `|| true` ile bitiyor ama 'bloklayıcı yapmak' tarifi bunu anmıyor — yalnız "
            "continue-on-error'ı kaldırmak adımı bloklayıcı YAPMAZ (D6.56)"
        )


def test_torch_CVE_lerinin_bu_adimda_GORUNMEDIGINI_soyler():
    yorum, _ = _yorum_ve_komut()
    req = (YML.parents[2] / "requirements.txt").read_text(encoding="utf-8")
    if "+cpu" in req:
        assert "ATLAR" in yorum and "GÖRÜNMEZ" in yorum, (
            "requirements.txt torch'u +cpu yerel sürümüyle pinliyor (PyPI'da yok → pip-audit atlar) ama yorum torch "
            "CVE'lerinin bu adımda görünmediğini söylemiyor (D6.56)"
        )
