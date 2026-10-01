# Author: mertaygn, cglrgrkn
"""D1.43 · B-10.43 — Inno kurulum/kaldırma E-stop kapısı Pascal yorumlarını SOYAR ve sırayı ölçer.

ÖLÇÜLEN KÖRLÜK (`test_inno_kurulum_bobin_guvenligi.py`):
  * kurulum (`ssInstall`) kolu yalnız `//` ile BAŞLAYAN satırları atıyordu → `{ PemfBobinleriGuveneAl(); }`
    ya da `(* … *)` Pascal blok yorumu "kod" sayılıyordu; `if False then PemfBobinleriGuveneAl();` de;
  * kaldırma (`usUninstall`) kolu yorum soymuyordu → `// PemfBobinleriGuveneAl();` YEŞİL; çağrının
    `setup_services.ps1` `Exec`'inin ARKASINA taşınması (backend önce sinyalsiz öldürülür) ölçülmüyordu.
Üçü de ISCC ile derlenir; değişmez kategori 1: backend sinyalsiz öldürülmeden önce bobinler güvene alınmalı.

Bu kapı `.iss` dosyasının yalnız `[Code]` bölümünü (Pascal) DİZE-BİLİNÇLİ soyar — `[Files]` gibi
bölümlerde `{app}` bir Inno SABİTİDİR, yorum değil. Dalın gövdesi `begin`/`end` eşlemesiyle bulunur;
çağrı dalın ÜST DÜZEYİNDE (alt blokta değil), KOŞULSUZ (önünde `then`/`else`/`do` yok) ve dalın
ilk `Exec(`'inden ÖNCE olmalı. Inno betiği DERLENMEZ, KOŞTURULMAZ (görev kuralı).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ISS = Path(__file__).resolve().parents[1] / "build_tools" / "PEMF_Backend_Setup.iss"
CAGRI = re.compile(r"\bPemfBobinleriGuveneAl\s*\(\s*\)\s*;")


def pascal_soy(src: str) -> str:
    """Pascal yorumlarını (`//…`, `{…}`, `(*…*)`) uzunluğu koruyarak boşlukla değiştirir; '…' dizeleri korur."""
    out, i, n = [], 0, len(src)

    def bos(c):
        return "\n" if c == "\n" else " "

    while i < n:
        c = src[i]
        if c == "'":  # Pascal dizesi; '' kaçış
            j = i + 1
            while j < n:
                if src[j] == "'" and j + 1 < n and src[j + 1] == "'":
                    j += 2
                    continue
                if src[j] == "'" or src[j] == "\n":
                    break
                j += 1
            out.append(src[i : j + 1])
            i = j + 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
            continue
        for ac, kapa in (("{", "}"), ("(*", "*)")):
            if src.startswith(ac, i):
                j = src.find(kapa, i + len(ac))
                j = n if j < 0 else j + len(kapa)
                out.append("".join(bos(x) for x in src[i:j]))
                i = j
                break
        else:
            out.append(c)
            i += 1
    sonuc = "".join(out)
    assert len(sonuc) == len(src)
    return sonuc


def code_bolumu(iss: str) -> str:
    m = re.search(r"^\[Code\]\s*$", iss, re.M)
    assert m, ".iss'te [Code] bölümü yok"
    son = re.search(r"^\[[A-Za-z]+\]\s*$", iss[m.end() :], re.M)
    return iss[m.end() : m.end() + son.start()] if son else iss[m.end() :]


_ACAN = re.compile(r"\b(begin|try|case)\b", re.I)
_TOKEN = re.compile(r"\b(begin|try|case|end)\b", re.I)


def dal_govdesi(kod: str, yordam: str, kosul: str) -> tuple[int, int]:
    """`procedure <yordam>` içindeki `if <kosul> then begin … end` dalının (gövde başı, gövde sonu) dizinleri."""
    p = re.search(rf"\bprocedure\s+{yordam}\b", kod)
    assert p, f"procedure {yordam} (yorum dışı) yok"
    d = re.compile(rf"\bif\s+{kosul}\s+then\s+begin\b", re.I).search(kod, p.end())
    assert d, f"{yordam}: `if {kosul} then begin` (yorum dışı) yok"
    derinlik, bas = 1, d.end()
    for t in _TOKEN.finditer(kod, bas):
        derinlik += 1 if _ACAN.fullmatch(t.group(1)) else -1
        if derinlik == 0:
            return bas, t.start()
    raise AssertionError(f"{yordam}: dal kapanmıyor")


def estop_sira_denetle(iss: str, yordam: str, kosul: str) -> None:
    kod = pascal_soy(code_bolumu(iss))
    bas, son = dal_govdesi(kod, yordam, kosul)
    govde = kod[bas:son]
    cagrilar = list(CAGRI.finditer(govde))
    assert cagrilar, f"{yordam}/{kosul}: PemfBobinleriGuveneAl() YORUM DIŞINDA yok — backend sinyalsiz öldürülür"
    c = cagrilar[0]
    onu = govde[: c.start()]
    derinlik = sum(1 if _ACAN.fullmatch(t.group(1)) else -1 for t in _TOKEN.finditer(onu))
    assert derinlik == 0, f"{yordam}/{kosul}: E-stop çağrısı alt blokta (derinlik {derinlik}) — koşullu olabilir"
    onceki = re.findall(r"[A-Za-z_]+|[;]", onu)
    assert not onceki or onceki[-1] == ";" or onceki[-1].lower() == "begin" or onu.strip() == "", (
        f"{yordam}/{kosul}: E-stop çağrısı KOŞULLU (önünde {onceki[-1]!r})"
    )
    exec_ = re.search(r"\bExec\s*\(", govde)
    assert exec_ is None or c.start() < exec_.start(), (
        f"{yordam}/{kosul}: E-stop dalın ilk Exec'inden SONRA — backend önce öldürülür, bobinler enerjili kalabilir"
    )


@pytest.fixture(scope="module")
def iss() -> str:
    return ISS.read_text(encoding="utf-8")


_DALLAR = [
    ("CurStepChanged", r"CurStep\s*=\s*ssInstall"),
    ("CurUninstallStepChanged", r"CurUninstallStep\s*=\s*usUninstall"),
]


@pytest.mark.parametrize(("yordam", "kosul"), _DALLAR, ids=["kurulum_ssInstall", "kaldirma_usUninstall"])
def test_KRITIK_ESTOP_yorum_disinda_KOSULSUZ_ve_Execten_ONCE(iss, yordam, kosul):
    estop_sira_denetle(iss, yordam, kosul)


# ── öz-denetim: soyucu ve sıra denetleyicisi kör değil ──────────────────────


def test_soyucu_UC_yorum_bicimini_soyar_dizeyi_ve_Inno_sabitini_korur():
    soy = pascal_soy("A; // X();\nB; { Y(); } C; (* Z(); *) D := 'a//b{c}''d';")
    assert "X(" not in soy and "Y(" not in soy and "Z(" not in soy
    assert "'a//b{c}''d'" in soy
    # [Code] dışındaki `{app}` Inno sabiti soyucuya hiç verilmez (yalnız [Code] bölümü soyulur).
    assert "{app}" not in code_bolumu("[Files]\nSource: \"{app}\"\n[Code]\nprocedure P; begin end;\n")


_UNINST = "    PemfBobinleriGuveneAl();\n\n    Purge := False;"
_INST = "    PemfBobinleriGuveneAl();\n\n    // [Files] kopyalamadan"
_EXEC_UNINST = "    Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);\n"
_MUTANTLAR = [
    ("kaldirma_SATIR_yorumu", 1, [(_UNINST, "    // PemfBobinleriGuveneAl();\n\n    Purge := False;")]),
    (
        "kaldirma_Execten_SONRA",
        1,
        [(_UNINST, "    Purge := False;"), (_EXEC_UNINST, _EXEC_UNINST + "    PemfBobinleriGuveneAl();\n")],
    ),
    ("kaldirma_IF_FALSE", 1, [(_UNINST, "    if False then PemfBobinleriGuveneAl();\n\n    Purge := False;")]),
    ("kurulum_SUSLU_yorum", 0, [(_INST, _INST.replace("PemfBobinleriGuveneAl();", "{ PemfBobinleriGuveneAl(); }"))]),
    ("kurulum_PAREN_yorum", 0, [(_INST, _INST.replace("PemfBobinleriGuveneAl();", "(* PemfBobinleriGuveneAl(); *)"))]),
    (
        "kurulum_IF_ALT_BLOK",
        0,
        [
            (
                _INST,
                _INST.replace(
                    "PemfBobinleriGuveneAl();", "if False then\n    begin\n      PemfBobinleriGuveneAl();\n    end;"
                ),
            )
        ],
    ),
]


@pytest.mark.parametrize(("ad", "dal", "degisiklik"), _MUTANTLAR, ids=[m[0] for m in _MUTANTLAR])
def test_KRITIK_denetleyici_mutantta_KIRMIZI(iss, ad, dal, degisiklik):
    src = iss.replace("\r\n", "\n")
    for eski, yeni in degisiklik:
        assert src.count(eski) == 1, f"mutant çapası {src.count(eski)} kez: {eski[:60]!r}"
        src = src.replace(eski, yeni)
    yordam, kosul = _DALLAR[dal]
    with pytest.raises(AssertionError):
        estop_sira_denetle(src, yordam, kosul)
