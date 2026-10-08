# -*- coding: utf-8 -*-
"""C2-2.6 (2-C inceleme A2) — KÖR KAPI: O-B.1 meta kapısı (`test_c_soy_PYTHON_kaynagina_UYGULANMAZ_OB1.ihlaller`) yeni bir
`c_soy` → Python çağıranının ÇOĞU biçimini kaçırıyor; koruma EN ALT katta, `c_soy`'un kendisinde olmalı.

ÖLÇÜLEN (HEAD 1cd770c, `_inceleme/kayit/sonda_k8a.txt`, aracın KENDİSİ): bilinen doğrudan biçim ve `modul.c_soy(...)` bulunuyor;
şu altı biçim KAÇIYOR — `from c_soyucu import c_soy as sok` · fonksiyon içi yerel yol değişkeni · `rglob('*.py')` döngüsü ·
`getattr(c_soyucu, 'c_soy')` · başka modüldeki yardımcı (test dosyasında `c_soy` metni yok → hiç taranmaz) · yardımcıya anahtar
argümanla `.py`. 2-C'nin ölçtüğü gerçek zarar (ai_router.py'nin 2190 satırının boşalması → "yalnız BİR kez atanır" kapısı sahte
yeşil) bu biçimlerden herhangi biriyle geri gelir ve meta kapı yeşil kalır.
DÜZELTME (en alt kat): `c_soy` girdisi Python modülü olarak ayrışıyor VE üst düzeyde `def`/`class`/`import` taşıyorsa
`ValueError` — çağıran hangi biçimde gelirse gelsin. C/C++/TS/TSX kaynakları Python olarak ayrışmaz (ölçüldü: c_soy kullanan
47 dosyanın tamamı yeşil).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
if not (_KOK / "apps").is_dir():
    _KOK = Path(__file__).resolve().parents[2]
if str(_KOK / "tests") not in sys.path:
    sys.path.insert(0, str(_KOK / "tests"))

from c_soyucu import c_soy  # noqa: E402
from c_soyucu import c_soy as sok  # noqa: E402

AI_ROUTER = _KOK / "apps" / "backend" / "servers" / "ai_router.py"


def test_KRITIK_c_soy_GERCEK_python_kaynagini_REDDEDER():
    with pytest.raises(ValueError, match="Python"):
        c_soy(AI_ROUTER.read_text(encoding="utf-8"))


def test_KRITIK_meta_kapinin_kacirdigi_TAKMA_AD_ve_YEREL_degisken_bicimleri_de_REDDEDILIR():
    def _yerel():
        p = _KOK / "apps" / "backend" / "backend_service.py"
        return c_soy(p.read_text(encoding="utf-8"))

    with pytest.raises(ValueError):
        sok(AI_ROUTER.read_text(encoding="utf-8"))
    with pytest.raises(ValueError):
        _yerel()


def test_KARSIT_C_ve_TSX_kaynagi_ile_ifade_parcasi_AYNEN_soyulur():
    c_kaynak = next((_KOK / "firmware").rglob("*.c"), None) if (_KOK / "firmware").is_dir() else None
    tsx = _KOK / "apps" / "ui" / "src" / "components" / "domain" / "ObservationNotesModal.tsx"
    for f in [x for x in (c_kaynak, tsx) if x is not None]:
        metin = f.read_text(encoding="utf-8", errors="replace")
        assert len(c_soy(metin)) == len(metin), f.name
    ifade = "a = 1 // yorum\n"  # Python'da da ayrışan C ifadesi: üst düzey def/import yok → reddedilmez
    sonuc = c_soy(ifade)
    assert len(sonuc) == len(ifade) and "yorum" not in sonuc and sonuc.startswith("a = 1")
