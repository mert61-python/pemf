# -*- coding: utf-8 -*-
"""I18NI-A2.5 sondası (kalıcı kapı adayı): K-3 (`_yorumsuz`) ve K-5 (`yorumsuz_ts`) TS yorum soyucusu `re.sub(r"/\\*.*?\\*/", …, re.S)`
DİZGİ İÇİNDEKİ `/*`'ı (ör. `input.accept = 'image/*'`) yorum başlangıcı sayar ve bir SONRAKİ `*/`'a kadar KODU yutar. Ölçüldü (HEAD
e1c8c9c3): `AiHubScreen.tsx` 519–4421 arası 1024 kod satırı / 100 çeviri çağrısı bu iki kapıya GÖRÜNMEZ → oraya eklenen eksik anahtar
(K-3) ve üretimde `__bayrakTestiAyarla(true)` (K-5) mutantları SAĞ kaldı.
Koşum: bash $SP/aj.sh b pytest _inceleme/I18NI-A2.5/test_ts_yorum_soyucusu_dizgiyi_yorum_saymaz.py -q -rfE
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest


def _kok() -> Path:
    p = Path(__file__).resolve().parent
    while not (p / "i18n" / "kapsam.json").exists():
        p = p.parent
    return p


KOK = _kok()
for _p in (KOK, KOK / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import test_i18n_anahtar_K3 as k3  # noqa: E402
import test_i18n_kritik_K5 as k5  # noqa: E402

ORNEK = (
    "input.accept = 'image/*';\n"
    'const a = t("ai.ornek.anahtar");\n'
    "__bayrakTestiAyarla(true);\n"
    "const u = \"https://ornek.test/a\"; // satır yorumu t(\"yorum.icinde\")\n"
    "/* blok yorum t(\"blok.icinde\") */\n"
    "<Text>Wi-Fi'de bağlı değil</Text>\n"
    'const b = t("ai.sonraki.anahtar");\n'
)

SOYUCULAR = [
    pytest.param(lambda s: k3._yorumsuz(s, "x.tsx"), id="K3"),
    pytest.param(k5.yorumsuz_ts, id="K5"),
]


@pytest.mark.parametrize("soy", SOYUCULAR)
def test_dizgideki_yildizli_bolu_KODU_YUTMAZ(soy):
    kod = soy(ORNEK)
    assert 't("ai.ornek.anahtar")' in kod, "dizgideki '/*' sonrası çeviri çağrısı yutuldu"
    assert "__bayrakTestiAyarla(true)" in kod, "dizgideki '/*' sonrası bayrak kancası yutuldu"
    assert 't("ai.sonraki.anahtar")' in kod, "JSX kesme işareti / URL sonrası kod yutuldu"


@pytest.mark.parametrize("soy", SOYUCULAR)
def test_gercek_yorumlar_HALA_soyulur(soy):
    kod = soy(ORNEK)
    assert "yorum.icinde" not in kod and "blok.icinde" not in kod, "gerçek yorum soyulmadı"
    assert "https://ornek.test/a" in kod, "dizgideki URL yorum sanıldı"


CAGRI = re.compile(r"""(?:\b(?:t|kritikMetin)|\bi18n\.t)\(\s*["']([A-Za-z][\w]*(?:\.[\w]+)+)["']""")


def _kod_satiri_cagrilari(src: str) -> list[str]:
    """Kaba ama bağımsız: yorum satırı / blok yorum içi OLMAYAN satırlardaki çeviri çağrıları."""
    sonuc, blok = [], False
    for ln in src.split("\n"):
        st = ln.strip()
        if blok:
            if "*/" in st:
                blok = False
            continue
        if st.startswith(("//", "*")):
            continue
        if st.startswith(("/*", "{/*")):
            if "*/" not in st:
                blok = True
            continue
        kesik = re.split(r"(?<![:\"'])\s//", ln)[0]
        sonuc += CAGRI.findall(kesik)
    return sonuc


@pytest.mark.parametrize("soy", SOYUCULAR)
def test_AiHubScreen_kod_satirlarindaki_cagrilarin_HEPSI_kapiya_gorunur(soy):
    src = (KOK / "apps/ui/src/screens/AiHubScreen.tsx").read_text(encoding="utf-8")
    beklenen = _kod_satiri_cagrilari(src)
    gorunen = CAGRI.findall(soy(src))
    assert len(beklenen) > 500, len(beklenen)
    eksik = len(beklenen) - len(gorunen)
    assert eksik <= 0, f"AiHubScreen: {eksik} çeviri çağrısı yorum soyucusunda KAYBOLUYOR (kapıya görünmez)"
