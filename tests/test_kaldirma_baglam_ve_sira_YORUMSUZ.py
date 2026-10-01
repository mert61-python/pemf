# Author: mertaygn, cglrgrkn
"""D1.46 · B-10.27 + D1.47 · B-10.130 · B-10.133 — kaldırma yolu kapıları BAĞLAMA ve YORUMSUZ koda bağlı.

D1.46 (NSIS bağlamı): `launcher/app/windows/hooks.nsi` POSTUNINSTALL'daki `RMDir /r "$LOCALAPPDATA\\PEMF_System"`
yalnız `SetShellVarContext current` bağlamında kullanıcı dizinine çözülür; `all` bağlamında
`C:\\ProgramData\\PEMF_System`'e (device_identity.json; PEMF_DATA_DIR=ProgramData kurulumunda hasta/tedavi DB'si)
çözülür ve ÖZYİNELEMELİ silinir. Ölçülen bağlam akışı:
  * PREUNINSTALL kancası her yolda `SetShellVarContext all` ile biter (port/günlük okuması için
    `current`'a geçip hemen geri döner) → POSTUNINSTALL'a `all` bağlamı taşınır;
  * Tauri'nin `Section Uninstall`ı (üretilen `installer.nsi`, izlenmeyen derleme çıktısı; 2026-09-10 sürümünde
    okundu) YALNIZ `$DeleteAppDataCheckboxState = 1 ${AndIf} $UpdateMode <> 1` dalında, kancayı çağırmadan hemen
    önce `SetShellVarContext current` yapar.
Bugünkü silme o dalın içinde → DOĞRU. Satır dalın dışına taşınsa (M1) ya da `SetShellVarContext all` +
`$APPDATA\\PEMF_System` eklense (M3) mevcut 6 dosya YEŞİL kalıyordu. Bu kapı dosyayı SIRAYLA okuyup bağlamı
izler; `$LOCALAPPDATA`/`$APPDATA` altı `PEMF_System`/`PEMF_GUI` silmesi `all` bağlamında → KIRMIZI.

D1.47 (yorum ve sıra):
  (a) `scripts/setup_services.ps1 -Uninstall`: graceful `nssm stop` ve servis-durdu bekleme döngüsü
      force-kill (`Stop-AppProcs` ÇAĞRISI) öncesinde — "bobin HER kill'den önce durur" kararının kaldırma kolu;
      eski kapı yalnız bir YORUM dizesine bakıyordu.
  (b) NSIS yorumu `;` VE `#` ile başlar — yalnız `;` tanıyan ayıklayıcı `# Exec…` satırını kod sayar.
  (c) per-user `PEMF_System` silmesi YORUM DIŞINDA aranır.
Betikler DERLENMEZ, KOŞTURULMAZ (görev kuralı); kapılar metin/sıra ayrıştırıcısıdır.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
HOOKS = KOK / "launcher" / "app" / "windows" / "hooks.nsi"
SETUP = KOK / "scripts" / "setup_services.ps1"

# ── NSIS ────────────────────────────────────────────────────────────────────


def nsis_satirlari(metin: str) -> list[str]:
    """Yorum dışı NSIS satırları: `;`/`#` satır yorumu ve `/* … */` blok yorumu atılır (dize içi korunur)."""
    metin = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), metin, flags=re.S)
    out = []
    for s in metin.replace("\r\n", "\n").split("\n"):
        kod, tirnak = [], None
        for ch in s:
            if tirnak:
                kod.append(ch)
                if ch == tirnak:
                    tirnak = None
                continue
            if ch in "\"'`":
                tirnak = ch
            elif ch in ";#":
                break
            kod.append(ch)
        out.append("".join(kod).strip())
    return out


def makro_govdesi(satirlar: list[str], ad: str) -> list[str]:
    bas = next((i for i, s in enumerate(satirlar) if re.match(rf"!macro\s+{ad}\b", s)), None)
    assert bas is not None, f"!macro {ad} (yorum dışı) yok"
    son = next(i for i in range(bas + 1, len(satirlar)) if satirlar[i].startswith("!macroend"))
    return satirlar[bas + 1 : son]


_SIL = re.compile(r"^(RMDir|Delete)\b.*\$(LOCALAPPDATA|APPDATA)\\(PEMF_System|PEMF_GUI)\b", re.I)
_KUTU_DALI = re.compile(r"^\$\{(If|ElseIf)\}\s+\$DeleteAppDataCheckboxState\s*=\s*1\s*$", re.I)


def baglam_ihlalleri(metin: str) -> list[str]:
    """`all` bağlamında ProgramData'ya çözülecek PEMF_System/PEMF_GUI silmeleri."""
    satirlar = nsis_satirlari(metin)
    baglam = "current"  # Tauri un.onInit (installMode=currentUser) — PREUNINSTALL'ın kendi seçimleri izlenir
    for s in makro_govdesi(satirlar, "NSIS_HOOK_PREUNINSTALL"):
        m = re.match(r"SetShellVarContext\s+(all|current)\b", s, re.I)
        if m:
            baglam = m.group(1).lower()
    ihlal = []
    yigin: list[str] = []  # POSTUNINSTALL ${If} dal bağlamları
    for no, s in enumerate(makro_govdesi(satirlar, "NSIS_HOOK_POSTUNINSTALL")):
        m = re.match(r"SetShellVarContext\s+(all|current)\b", s, re.I)
        if m:
            baglam = m.group(1).lower()
            if yigin:
                yigin[-1] = baglam
            continue
        if re.match(r"^\$\{If(Not)?\}", s):
            yigin.append("current" if _KUTU_DALI.match(s) else baglam)
            continue
        if re.match(r"^\$\{(ElseIf|Else)\}", s):
            if yigin:
                yigin[-1] = "current" if _KUTU_DALI.match(s) else baglam
            continue
        if re.match(r"^\$\{EndIf\}", s):
            if yigin:
                yigin.pop()
            continue
        etkin = yigin[-1] if yigin else baglam
        if _SIL.match(s) and etkin == "all":
            ihlal.append(f"POSTUNINSTALL+{no}: {s}  [bağlam all → C:\\ProgramData]")
    return ihlal


@pytest.fixture(scope="module")
def hooks() -> str:
    return HOOKS.read_text(encoding="utf-8", errors="replace")


def test_KRITIK_D146_POSTUNINSTALL_silmeleri_ProgramData_ya_COZULMEZ(hooks):
    assert baglam_ihlalleri(hooks) == []


def test_KRITIK_D147c_per_user_PEMF_System_silmesi_YORUM_DISINDA(hooks):
    kod = makro_govdesi(nsis_satirlari(hooks), "NSIS_HOOK_POSTUNINSTALL")
    assert any(re.match(r'RMDir\s+/r\s+"\$LOCALAPPDATA\\PEMF_System"', s) for s in kod), (
        r"%LOCALAPPDATA%\PEMF_System silmesi yorum dışında yok — hotspot.log gibi artıklar kalır"
    )


def test_ARAC_nsis_ayiklayici_iki_yorum_bicimini_ve_bloku_tanir():
    satirlar = nsis_satirlari('A\n; B\n# C\n  D ; yorum\n/* E\nF */ G\nH "x;#y"\n')
    assert satirlar[:4] == ["A", "", "", "D"] and "E" not in "".join(satirlar) and "F" not in "".join(satirlar)
    assert 'H "x;#y"' in satirlar


_SATIR = '    RMDir /r "$LOCALAPPDATA\\PEMF_System"\n'
_MUTANTLAR = {
    "M1_satir_dalin_DISINA": lambda m: m.replace(_SATIR, "", 1).replace(
        "  ${EndIf}\n  ; ── KVKK AÇIKLIĞI",
        "  ${EndIf}\n" + _SATIR.strip().join(["  ", "\n"]) + "  ; ── KVKK AÇIKLIĞI",
        1,
    ),
    "M3_all_ve_APPDATA": lambda m: m.replace(
        _SATIR, _SATIR + '    SetShellVarContext all\n    RMDir /r "$APPDATA\\PEMF_System"\n', 1
    ),
    "silme_YORUMA_alindi_noktali_virgul": lambda m: m.replace(_SATIR, "    ; " + _SATIR.lstrip(), 1),
    "silme_YORUMA_alindi_diyez": lambda m: m.replace(_SATIR, "    # " + _SATIR.lstrip(), 1),
}


@pytest.mark.parametrize("ad", list(_MUTANTLAR))
def test_KRITIK_denetleyiciler_mutantta_KIRMIZI(hooks, ad):
    kaynak = hooks.replace("\r\n", "\n")
    assert kaynak.count(_SATIR) == 1
    mutant = _MUTANTLAR[ad](kaynak)
    assert mutant != kaynak, f"{ad}: çapa uymadı"
    baglam = baglam_ihlalleri(mutant)
    kod = makro_govdesi(nsis_satirlari(mutant), "NSIS_HOOK_POSTUNINSTALL")
    var = any(re.match(r'RMDir\s+/r\s+"\$LOCALAPPDATA\\PEMF_System"', s) for s in kod)
    assert baglam or not var, f"{ad}: iki denetleyici de YEŞİL kaldı"


# ── setup_services.ps1 -Uninstall (D1.47a) ─────────────────────────────────


def ps_soy(src: str) -> str:
    """PowerShell `#…` ve `<#…#>` yorumlarını (dize-bilinçli; '…' / "…" + backtick) uzunluğu koruyarak siler."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("<#", i):
            j = src.find("#>", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join("\n" if x == "\n" else " " for x in src[i:j]))
            i = j
            continue
        if c == "#":
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
            continue
        if c in "'\"":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if (c == '"' and src[j] == "`") else 1
            out.append(src[i : j + 1])
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def ps_blok(kod: str, bas_deseni: str) -> str:
    m = re.search(bas_deseni, kod)
    assert m, f"{bas_deseni!r} (yorum dışı) yok"
    ac = kod.index("{", m.start())
    derinlik = 0
    for k in range(ac, len(kod)):
        derinlik += {"{": 1, "}": -1}.get(kod[k], 0)
        if derinlik == 0:
            return kod[ac + 1 : k]
    raise AssertionError("blok kapanmıyor")


def _servis_bekleme_dongusu(blok: str):
    """`for ( … Get-Service -Name $ServiceBackend … ) { Start-Sleep …` — başlık iç içe parantezli olduğundan
    parantez EŞLENEREK bulunur (`[^)]*` ilk `)`de durur; ilk yazımda tam bu yüzden yanlış KIRMIZI verdi)."""
    for m in re.finditer(r"\bfor\s*\(", blok):
        derinlik, k = 0, m.end() - 1
        while k < len(blok):
            derinlik += {"(": 1, ")": -1}.get(blok[k], 0)
            if derinlik == 0:
                break
            k += 1
        baslik, sonrasi = blok[m.end() : k], blok[k + 1 :]
        if re.search(r"Get-Service\s+-Name\s+\$ServiceBackend", baslik) and re.match(r"\s*\{\s*Start-Sleep", sonrasi):
            return m
    return None


def kaldirma_sirasi_denetle(src: str) -> None:
    blok = ps_blok(ps_soy(src), r"if\s*\(\s*\$Uninstall\s*\)\s*\{")
    tanim = re.search(r"function\s+Stop-AppProcs\s*\{", blok)
    if tanim:  # tanımın gövdesi çağrı sayılmaz
        g = ps_blok(blok[tanim.start() :], r"function\s+Stop-AppProcs\s*\{")
        blok = (
            blok[: tanim.start()]
            + " " * (len(g) + (tanim.end() - tanim.start()) + 1)
            + blok[tanim.end() + len(g) + 1 :]
        )
    stop = re.search(r"&\s*\$NssmExe\s+stop\s+\$ServiceBackend", blok)
    bekle = _servis_bekleme_dongusu(blok)
    kill = re.search(r"(?<![\w-])Stop-AppProcs(?![\w-])", blok)
    assert stop, "-Uninstall'da graceful `nssm stop` (yorum dışı) YOK — backend Ctrl+C ile bobinleri durduramaz"
    assert bekle, "-Uninstall'da servis-durdu BEKLEME döngüsü (yorum dışı) YOK"
    assert kill, "-Uninstall'da Stop-AppProcs çağrısı yok — yapı değişmiş"
    assert stop.start() < bekle.start() < kill.start(), (
        "force-kill (Stop-AppProcs) graceful nssm stop + bekleme TAMAMLANMADAN — bobin STOP'u atlanabilir"
    )


def test_KRITIK_D147a_kaldirma_graceful_STOP_ve_BEKLEME_force_killden_ONCE():
    kaldirma_sirasi_denetle(SETUP.read_text(encoding="utf-8", errors="replace"))


_PS_KILL_DONGU = "        Stop-AppProcs\n        Start-Sleep -Milliseconds 500\n    }\n"
_PS_STOP = "    if (Test-Path $NssmExe) { & $NssmExe stop $ServiceBackend *>$null }\n"


@pytest.mark.parametrize(
    "ad",
    ["kill_ONE_ALINDI", "nssm_stop_YORUMDA", "bekleme_YORUMDA"],
)
def test_KRITIK_D147a_denetleyici_mutantta_KIRMIZI(ad):
    src = SETUP.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    assert src.count(_PS_STOP) == 1
    if ad == "kill_ONE_ALINDI":
        src = src.replace(_PS_STOP, "    Stop-AppProcs\n" + _PS_STOP, 1)
    elif ad == "nssm_stop_YORUMDA":
        src = src.replace(_PS_STOP, "    # " + _PS_STOP.lstrip(), 1)
    else:
        i = src.index("    for ($i = 0; $i -lt 40")
        src = src[:i] + "    # " + src[i + 4 :]
    with pytest.raises(AssertionError):
        kaldirma_sirasi_denetle(src)
