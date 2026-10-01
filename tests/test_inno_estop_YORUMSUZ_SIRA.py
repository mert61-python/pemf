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


# Inno'da süreç başlatan TÜM yerleşik biçimler (1-B inceleme i5: yalnız `Exec(` aranıyordu).
_OLDURUCU = re.compile(
    r"\b(Exec|ExecAsOriginalUser|ShellExec|ShellExecAsOriginalUser|ExecAndCaptureOutput|ExecAndLogOutput)\s*\(", re.I
)
# E-stop'un kendisi (port dosyasından POST'u powershell `Exec`'iyle gönderir) — öldürücü SAYILMAZ.
_ESTOP_YORDAMLARI = {"pemfbobinleriguveneal", "pemfestopportagonder", "pemfestopdosyadan"}
# Dal gövdesinde E-stop'tan ÖNCE izin verilen deyimler: boş, çağrısız atama, düz `Log('…')`.
_IZINLI_ONCUL = re.compile(r"(?:[A-Za-z_]\w*\s*:=\s*[^()]*|Log\s*\(\s*'(?:[^']|'')*'\s*\))", re.S)
# Kurulum/kaldırma dalından ÖNCE koşan olay işleyicileri (sihirbaz akışı, ön-hazırlık).
_ERKEN_ISLEYICILER = (
    "InitializeSetup",
    "InitializeUninstall",
    "InitializeWizard",
    "InitializeUninstallProgressForm",
    "PrepareToInstall",
    "NextButtonClick",
    "CurPageChanged",
    "ShouldSkipPage",
)
# Hedef daldan SONRA gelen adımların dalları (oradaki süreç başlatma E-stop'tan sonradır).
_SONRAKI_ADIMLAR = {
    "CurStepChanged": ("CurStep", ("ssPostInstall", "ssDone")),
    "CurUninstallStepChanged": ("CurUninstallStep", ("usPostUninstall", "usDone")),
}


def _dizesiz(kod: str) -> str:
    """Pascal '…' dizelerinin İÇİNİ boşlukla değiştirir (çağrı adı araması dizeye takılmasın)."""
    return re.sub(r"'(?:[^'\n]|'')*'", lambda m: "'" + " " * (len(m.group(0)) - 2) + "'", kod)


def yordamlar(kod: str) -> dict[str, tuple[int, int]]:
    """`[Code]`'daki her procedure/function için küçük-harf ad → (gövde başı, gövde sonu)."""
    sonuc = {}
    kod = _dizesiz(kod)  # dizedeki `try`/`end` (ör. powershell `-Command "try { … }"`) blok sayılmasın
    for b in re.finditer(r"^\s*(?:procedure|function)\s+([A-Za-z_]\w*)", kod, re.M | re.I):
        ilk = re.compile(r"\bbegin\b", re.I).search(kod, b.end())
        if not ilk:
            continue
        derinlik = 1
        for t in _TOKEN.finditer(kod, ilk.end()):
            derinlik += 1 if _ACAN.fullmatch(t.group(1)) else -1
            if derinlik == 0:
                sonuc[b.group(1).lower()] = (ilk.end(), t.start())
                break
    return sonuc


def olduren_yordamlar(kod: str) -> set[str]:
    """Doğrudan ya da GEÇİŞLİ olarak süreç başlatan (Exec*/ShellExec*) yordamlar; E-stop yordamları hariç."""
    yor = yordamlar(kod)
    govdeler = {ad: _dizesiz(kod[b:s]) for ad, (b, s) in yor.items()}
    olduren = {ad for ad, g in govdeler.items() if ad not in _ESTOP_YORDAMLARI and _OLDURUCU.search(g)}
    degisti = True
    while degisti:
        degisti = False
        for ad, g in govdeler.items():
            if ad in olduren or ad in _ESTOP_YORDAMLARI:
                continue
            if any(re.search(rf"\b{o}\b", g, re.I) for o in olduren):
                olduren.add(ad)
                degisti = True
    return olduren


def _oldurur_mu(metin: str, olduren: set[str]) -> str | None:
    m = _OLDURUCU.search(metin)
    if m:
        return m.group(0)
    for o in sorted(olduren):
        if re.search(rf"\b{o}\b", metin, re.I):
            return o
    return None


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
    # (a) E-stop'tan ÖNCE dalda yalnız izinli deyimler: başka HER çağrı (yardımcı yordam dahil) bir öldürme yolu olabilir.
    for deyim in _dizesiz(onu).split(";"):
        d = deyim.strip()
        assert not d or _IZINLI_ONCUL.fullmatch(d), (
            f"{yordam}/{kosul}: E-stop'tan ÖNCE izinsiz deyim {d[:60]!r} — yalnız atama/Log; çağrılar E-stop'tan SONRA"
        )
    olduren = olduren_yordamlar(kod)
    exec_ = _OLDURUCU.search(_dizesiz(govde))
    assert exec_ is None or c.start() < exec_.start(), (
        f"{yordam}/{kosul}: E-stop dalın ilk {exec_.group(0)!r}'inden SONRA — backend önce öldürülür, bobinler enerjili kalabilir"
    )
    # (b) Aynı yordamda hedef dalın DIŞINDA (önce koşan kod / önceki adımların dalları) süreç başlatma yok;
    #     yalnız SONRAKİ adımların (ssPostInstall/usPostUninstall/…) dalları muaf.
    yor = yordamlar(kod)
    ybas, yson = yor[yordam.lower()]
    degisken, sonrakiler = _SONRAKI_ADIMLAR[yordam]
    muaf = [(bas, son)]
    for adim in sonrakiler:
        if re.search(rf"\b{degisken}\s*=\s*{adim}\b", kod[ybas:yson]):
            muaf.append(dal_govdesi(kod, yordam, rf"{degisken}\s*=\s*{adim}"))
    disari = "".join(" " if any(mb <= i < ms for mb, ms in muaf) else ch for i, ch in enumerate(kod[ybas:yson], ybas))
    bulgu = _oldurur_mu(_dizesiz(disari), olduren)
    assert bulgu is None, f"{yordam}: hedef dalın ({kosul}) DIŞINDA süreç başlatma/öldürme yolu {bulgu!r}"
    # (c) Erken olay işleyicileri (kurulum/kaldırma dalından ÖNCE koşar): süreç başlatma ya da öldüren yardımcı YOK.
    for isleyici in _ERKEN_ISLEYICILER:
        if isleyici.lower() in yor:
            ib, is_ = yor[isleyici.lower()]
            bulgu = _oldurur_mu(_dizesiz(kod[ib:is_]), olduren)
            assert bulgu is None, f"{isleyici}: E-stop'tan ÖNCE koşan işleyicide süreç başlatma/öldürme yolu {bulgu!r}"


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
# 1-B inceleme i5: yalnız dalın ilk `Exec(`'i ölçülüyordu — yardımcı yordam, Exec ailesinin diğer üyeleri,
# hedef dal DIŞINDAKİ kod ve erken olay işleyicileri görünmüyordu.
_KILL = "  Exec('taskkill.exe', '/F /IM PEMF_Backend.exe', '', SW_HIDE, ewWaitUntilTerminated, RC);\n"
_UNINST_YORDAM = "procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);"
_YARDIMCI = "procedure PemfBackendiKapat();\nvar\n  RC: Integer;\nbegin\n" + _KILL + "end;\n\n"
_INIT_SETUP = "function InitializeSetup: Boolean;\nbegin\n  Result := True;\n"
_MUTANTLAR += [
    (
        "kaldirma_YARDIMCI_yordam_ONCE",  # i5 inno_yardimci_kill
        1,
        [
            (_UNINST_YORDAM, _YARDIMCI + _UNINST_YORDAM),
            (_UNINST, "    PemfBackendiKapat();\n" + _UNINST),
        ],
    ),
    (
        "kaldirma_ExecAsOriginalUser_ONCE",
        1,
        [
            (
                _UNINST,
                "    ExecAsOriginalUser('taskkill.exe', '/F /IM PEMF_Backend.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);\n"
                + _UNINST,
            )
        ],
    ),
    (
        "kaldirma_ShellExec_ONCE",
        1,
        [
            (
                _UNINST,
                "    ShellExec('', 'taskkill.exe', '/F /IM PEMF_Backend.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);\n"
                + _UNINST,
            )
        ],
    ),
    (
        "kaldirma_DAL_DISINDA_once",
        1,
        [
            (
                "begin\n  if CurUninstallStep = usUninstall then",
                "begin\n  Exec('taskkill.exe', '/F /IM PEMF_Backend.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);\n"
                "  if CurUninstallStep = usUninstall then",
            )
        ],
    ),
    (
        "kaldirma_usAppMutexCheck_dalinda",
        1,
        [
            (
                "begin\n  if CurUninstallStep = usUninstall then",
                "begin\n  if CurUninstallStep = usAppMutexCheck then\n  begin\n    PemfBackendiKapat();\n  end;\n"
                "  if CurUninstallStep = usUninstall then",
            ),
            (_UNINST_YORDAM, _YARDIMCI + _UNINST_YORDAM),
        ],
    ),
    (
        "kaldirma_InitializeUninstall_kill",
        1,
        [
            (
                _UNINST_YORDAM,
                "function InitializeUninstall(): Boolean;\nvar\n  RC: Integer;\nbegin\n"
                + _KILL
                + "  Result := True;\nend;\n\n"
                + _UNINST_YORDAM,
            )
        ],
    ),
    (
        "kurulum_InitializeSetup_GECISLI_yardimci",
        0,
        [(_UNINST_YORDAM, _YARDIMCI + _UNINST_YORDAM), (_INIT_SETUP, _INIT_SETUP + "  PemfBackendiKapat();\n")],
    ),
]


def test_cozumleyici_canli_yordamlari_ve_estop_istisnasini_gorur(iss):
    kod = pascal_soy(code_bolumu(iss))
    yor = yordamlar(kod)
    for ad in ("curstepchanged", "curuninstallstepchanged", "initializesetup", "pemfbobinleriguveneal"):
        assert ad in yor, f"yordam çözümleyici {ad!r} gövdesini bulamadı (çapa çürüdü)"
    # E-stop'un POST'u powershell Exec'iyle gider → istisna listesi OLMADAN öldürücü sayılırdı; listede olmalı.
    assert _OLDURUCU.search(_dizesiz(kod[slice(*yor["pemfestopportagonder"])])), (
        "E-stop yordamında Exec yok (çapa çürüdü)"
    )
    assert not (olduren_yordamlar(kod) & _ESTOP_YORDAMLARI)


def test_KARSIT_sonraki_adim_dalinda_Exec_YESIL(iss):
    """ssPostInstall dalındaki süreç başlatma E-stop'tan SONRADIR → kapı yanlış kırmızı vermemeli."""
    src = iss.replace("\r\n", "\n")
    capa = "  else if CurStep = ssPostInstall then\n  begin\n"
    assert src.count(capa) == 1, "karşıt çapası çürüdü"
    src = src.replace(
        capa, capa + "    Exec('sc.exe', 'start PemfBackend', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);\n"
    )
    estop_sira_denetle(src, *_DALLAR[0])


@pytest.mark.parametrize(("ad", "dal", "degisiklik"), _MUTANTLAR, ids=[m[0] for m in _MUTANTLAR])
def test_KRITIK_denetleyici_mutantta_KIRMIZI(iss, ad, dal, degisiklik):
    src = iss.replace("\r\n", "\n")
    for eski, yeni in degisiklik:
        assert src.count(eski) == 1, f"mutant çapası {src.count(eski)} kez: {eski[:60]!r}"
        src = src.replace(eski, yeni)
    yordam, kosul = _DALLAR[dal]
    with pytest.raises(AssertionError):
        estop_sira_denetle(src, yordam, kosul)
