# Author: mertaygn, cglrgrkn
"""LN L7 · D2.33 · D2.67 · D2.76 · D2.77 — kaldırma: hasta verisinin GERÇEK konumu + Tauri bağlamı.

Ölçülen (HEAD, LN başı):
  * Launcher kaldırma diyaloğu (`ui.uninBody`) sabit "%APPDATA%\\PEMF_GUI" diyordu; launcher makine-geneli kök yazılabilirse
    backend'e `PEMF_DATA_DIR=%PROGRAMDATA%\\PEMF_System` verir (`install.rs::cozulmus_veri_dizini`) → hasta DB'si
    `%PROGRAMDATA%\\PEMF_System\\PEMF_GUI`'de — diyalog YANLIŞ klasörü gösteriyordu.
  * NSIS KVKK iletisi (`nsis.kaldirildiKutu`) `$APPDATA\\PEMF_GUI` diyordu ve kanca `SetShellVarContext all` ile bittiği için
    `C:\\ProgramData\\PEMF_GUI`'ye çözülüyordu — iki gerçek kökten hiçbiri.
  * Tauri `un.onInit` → `SetContext` (currentUser → `current`); kanca PREUNINSTALL'ı `all`'da bitiriyordu → hemen ardından
    şablonun kısayol silmesi (`$SMPROGRAMS`, `$DESKTOP`) TÜM-KULLANICILAR dizinine bakıyor, kullanıcının kısayolları KALIYORDU.

Kapı: üretilmiş şablonun kaldırma akışı (`tests/golden/tauri_nsis_kaldirma_akisi.nsi`, birebir alıntı) + kancanın GERÇEK
makroları sırayla, YOLA DUYARLI bağlam izleyicisiyle yürütülür. Betik DERLENMEZ / KOŞTURULMAZ (kanca derlemesi ayrı kapıda:
`test_kaldirma_yetim_surec_temizligi.py::test_kanca_gercekten_nsis_ile_derlenir`).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
HOOKS = KOK / "launcher" / "app" / "windows" / "hooks.nsi"
SABLON = KOK / "tests" / "golden" / "tauri_nsis_kaldirma_akisi.nsi"
INDEX = KOK / "launcher" / "app" / "ui" / "index.html"


def _yorumsuz(metin: str) -> list[str]:
    """Yorum dışı NSIS satırları (`;` / `#` satır yorumu, `/* … */` blok; tırnak içi korunur), kırpılmış."""
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


def _makrolar(satirlar: list[str]) -> dict[str, list[str]]:
    m: dict[str, list[str]] = {}
    ad = None
    for s in satirlar:
        b = re.match(r"!macro\s+(\w+)", s)
        if b and ad is None:
            ad, m[b.group(1)] = b.group(1), []
            continue
        if s.startswith("!macroend") and ad is not None:
            ad = None
            continue
        if ad is not None:
            m[ad].append(s)
    return m


def _bolum(satirlar: list[str], bas: str, son: str) -> list[str]:
    i = next(i for i, s in enumerate(satirlar) if s.startswith(bas))
    j = next(j for j in range(i + 1, len(satirlar)) if satirlar[j].startswith(son))
    return satirlar[i + 1 : j]


def _derleme_zamani(satirlar: list[str], tanimlar: dict[str, str], makrolar: dict[str, list[str]]) -> list[str]:
    """`!if "${X}" == "v"` / `!else if` / `!else` / `!endif` ve `!ifmacrodef` / `!ifdef` çöz; `!insertmacro` genişlet."""
    out: list[str] = []
    yigin: list[list[bool]] = []  # [bu_dal_etkin, daha_once_bir_dal_secildi]

    def etkin() -> bool:
        return all(c[0] for c in yigin)

    def kosul(s: str) -> bool:
        m = re.match(r'"\$\{(\w+)\}"\s*==\s*"([^"]*)"', s)
        if m:
            return tanimlar.get(m.group(1)) == m.group(2)
        raise AssertionError(f"çözülemeyen derleme koşulu: {s}")

    for s in satirlar:
        if s.startswith("!ifmacrodef"):
            v = s.split()[1] in makrolar
            yigin.append([v, v])
        elif s.startswith("!ifdef"):
            v = s.split()[1] in tanimlar
            yigin.append([v, v])
        elif s.startswith("!if "):
            v = kosul(s[4:].strip())
            yigin.append([v, v])
        elif s.startswith("!else if"):
            c = yigin[-1]
            v = (not c[1]) and kosul(s[len("!else if") :].strip())
            c[0], c[1] = v, c[1] or v
        elif s.startswith("!else"):
            c = yigin[-1]
            c[0], c[1] = not c[1], True
        elif s.startswith("!endif"):
            yigin.pop()
        elif not etkin():
            continue
        elif s.startswith("!insertmacro"):
            ad = s.split()[1]
            if ad in makrolar:
                out.append(f"; <makro {ad}>")
                out += _derleme_zamani(makrolar[ad], tanimlar, makrolar)
                out.append(f"; </makro {ad}>")
        elif s:
            out.append(s)
    assert not yigin, "kapanmayan derleme koşulu"
    return out


def _akis() -> tuple[list[str], dict[str, str]]:
    """un.onInit + Section Uninstall — kanca makroları GERÇEK hooks.nsi'den, şablon makroları fikstürden genişletilmiş."""
    sablon = _yorumsuz(SABLON.read_text(encoding="utf-8"))
    kanca = _yorumsuz(HOOKS.read_text(encoding="utf-8"))
    tanimlar = dict(re.findall(r'^!define\s+(\w+)\s+"([^"]*)"', "\n".join(sablon), re.M))
    makrolar = {**_makrolar(sablon), **_makrolar(kanca)}
    satirlar = _bolum(sablon, "Function un.onInit", "FunctionEnd") + _bolum(sablon, "Section Uninstall", "SectionEnd")
    return _derleme_zamani(satirlar, tanimlar, makrolar), tanimlar


_KISAYOL = re.compile(r"^(Delete|RMDir)\b.*\$(SMPROGRAMS|DESKTOP)\b", re.I)
_KULLANICI_SIL = re.compile(r"^(Delete|RMDir)\b.*\$(APPDATA|LOCALAPPDATA)\b", re.I)


def baglam_ihlalleri(akis: list[str], beklenen: str) -> list[str]:
    """Yola duyarlı izleyici: dal sonlarından biri `all` ise birleşim `all` (tutucu). Kullanım noktaları: kısayol silmesi,
    kullanıcı dizini silmesi, `$APPDATA`'dan kök çözümü ve PREUNINSTALL çıkışı — hepsi `beklenen` bağlamda olmalı."""
    ihlal = []
    baglam = None  # un.onInit'ten ÖNCE bilinmez
    yigin: list[dict] = []
    for no, s in enumerate(akis):
        m = re.match(r"SetShellVarContext\s+(all|current)\b", s, re.I)
        if m:
            baglam = m.group(1).lower()
            continue
        if re.match(r"^\$\{(If|IfNot|Unless)\}", s):
            yigin.append({"giris": baglam, "sonlar": [], "else": False})
            continue
        if re.match(r"^\$\{(ElseIf|Else)\}", s):
            c = yigin[-1]
            c["sonlar"].append(baglam)
            c["else"] = c["else"] or s.startswith("${Else}")
            baglam = c["giris"]
            continue
        if s.startswith("${EndIf}"):
            c = yigin.pop()
            yollar = c["sonlar"] + [baglam] + ([] if c["else"] else [c["giris"]])
            baglam = "all" if "all" in yollar else (None if None in yollar else "current")
            continue
        if s == "; </makro NSIS_HOOK_PREUNINSTALL>" and baglam != beklenen:
            ihlal.append(
                f"PREUNINSTALL çıkışı bağlam {baglam} (beklenen {beklenen}) — şablonun kısayol silmesi yanlış dizine bakar"
            )
        if (_KISAYOL.match(s) or _KULLANICI_SIL.match(s)) and baglam != beklenen:
            ihlal.append(f"+{no}: {s}  [bağlam {baglam}, beklenen {beklenen}]")
        if s.startswith("StrCpy $PEMF_VeriKoku") and "$APPDATA" in s and baglam != "current":
            ihlal.append(f"+{no}: {s}  [kullanıcı kökü `{baglam}` bağlamında çözülüyor]")
    return ihlal


def test_FIKSTUR_tauri_akisi_beklenen_bicimde():
    akis, tanimlar = _akis()
    assert tanimlar.get("INSTALLMODE") == "currentUser", tanimlar
    assert akis.index("; <makro NSIS_HOOK_PREUNINSTALL>") < next(i for i, s in enumerate(akis) if _KISAYOL.match(s)), (
        "fikstürde kısayol silmesi PREUNINSTALL'dan sonra değil — alıntı bozulmuş"
    )
    assert "; <makro NSIS_HOOK_POSTUNINSTALL>" in akis and akis[0] == "; <makro SetContext>"


def test_KRITIK_D267_D277_baglam_TAURI_baglamina_doner_kisayollar_ve_kullanici_dizinleri_current():
    akis, _ = _akis()
    assert baglam_ihlalleri(akis, "current") == []


def test_KRITIK_D277_gecici_current_AYNI_dalda_Tauri_baglamina_geri_doner():
    """Kanca kullanıcı dizininden okumak için `current`'a geçer; HER geçiş aynı dal içinde (bir sonraki `${Else}` / `${EndIf}` /
    makro sonundan önce) `PEMF_BAGLAMI_GERI_YUKLE` ile Tauri'nin bağlamına döner — currentUser'da eşdeğer görünür ama perMachine'de
    (Tauri `all`) dönülmezse şablonun geri kalanı kullanıcı bağlamında koşar."""
    kod = [s for s in _yorumsuz(HOOKS.read_text(encoding="utf-8")) if s]
    for makro in ("NSIS_HOOK_PREUNINSTALL", "NSIS_HOOK_POSTUNINSTALL"):
        g = _bolum(kod, f"!macro {makro}", "!macroend")
        for i, s in enumerate(g):
            if not re.match(r"SetShellVarContext\s+current\b", s, re.I):
                continue
            sonra = g[i + 1 :]
            sinir = next((j for j, x in enumerate(sonra) if re.match(r"^\$\{(Else|ElseIf|EndIf)\}", x)), len(sonra))
            assert "!insertmacro PEMF_BAGLAMI_GERI_YUKLE" in sonra[:sinir], (
                f"{makro}+{i}: geçici `current` aynı dalda geri alınmıyor — perMachine'de bağlam bozulur"
            )


def test_KRITIK_D277_kancada_SetShellVarContext_all_YOK():
    kod = _yorumsuz(HOOKS.read_text(encoding="utf-8"))
    hep = [s for s in kod if re.match(r"SetShellVarContext\s+all\b", s, re.I)]
    assert not hep, f"kanca `all` bağlamına geçiyor: {hep} — Tauri bağlamı (currentUser → current) bozulur"


def _langstring(kod: list[str], ad: str, dil: int) -> str:
    m = next((s for s in kod if s.startswith(f"LangString PEMF_{ad} {dil} ")), None)
    assert m, f"LangString PEMF_{ad} {dil} yok"
    return m


@pytest.mark.parametrize("dil", [1055, 1033])
@pytest.mark.parametrize("ad", ["kaldirildiKutu", "kayitlarKorundu", "estopDogrulanamadi", "estopDogrulanamadiKutu"])
def test_KRITIK_D277_KVKK_iletisi_GERCEK_koku_gosterir(dil, ad):
    kod = _yorumsuz(HOOKS.read_text(encoding="utf-8"))
    s = _langstring(kod, ad, dil)
    assert "$PEMF_VeriKoku" in s, f"{ad}/{dil}: ileti gerçek kökü göstermiyor: {s[:160]}"
    assert not re.search(r"[%$]APPDATA%?\\PEMF_GUI", s), f"{ad}/{dil}: sabit APPDATA yolu kaldı: {s[:160]}"


def test_KRITIK_D277_kok_E_STOPtan_ONCE_her_yolda_cozulur_kayit_ProgramData_APPDATA_sirasi():
    kod = _yorumsuz(HOOKS.read_text(encoding="utf-8"))
    pre = _bolum(kod, "!macro NSIS_HOOK_PREUNINSTALL", "!macroend")
    sira = [
        ('StrCpy $PEMF_VeriKoku ""', "sıfırlama"),
        ('FileOpen $0 "$INSTDIR\\veri_koku.txt" r', "launcher kaydı"),
        ("FileReadUTF16LE $0 $PEMF_VeriKoku", "UTF-16LE okuma (Türkçe kullanıcı adı)"),
        ("ReadEnvStr $0 PROGRAMDATA", "makine-geneli kök"),
        ('StrCpy $PEMF_VeriKoku "$0\\PEMF_System\\PEMF_GUI"', "makine-geneli kök ataması"),
        ('StrCpy $PEMF_VeriKoku "$APPDATA\\PEMF_GUI"', "kullanıcı kökü (düşüş)"),
    ]
    yer = []
    for parca, neden in sira:
        i = next((i for i, s in enumerate(pre) if s.startswith(parca)), None)
        assert i is not None, f"PREUNINSTALL'da {neden} yok: {parca}"
        yer.append(i)
    assert yer == sorted(yer), f"kök çözüm sırası bozuk: {list(zip(yer, [n for _, n in sira]))}"
    ilk_atlama = next(i for i, s in enumerate(pre) if re.match(r"(IfErrors|Goto|StrCmp)\b.*pemf_estop", s))
    estop = next(i for i, s in enumerate(pre) if "nsExec::" in s and "emergency_stop" in s)
    assert yer[-1] < ilk_atlama < estop, (
        "kök E-stop yolunun ATLAMASINDAN sonra çözülüyor — bazı yollarda ileti boş kalır"
    )


def test_KRITIK_D277_Var_LangString_blogundan_ONCE_bildirilir():
    ham = HOOKS.read_text(encoding="utf-8")
    assert re.search(r"^Var PEMF_VeriKoku\s*$", ham, re.M), "Var PEMF_VeriKoku yok"
    assert ham.index("Var PEMF_VeriKoku") < ham.index("; >>> I18N-DIL"), (
        "Var LangString bloğundan SONRA — makensis LangString'i tanımlarken değişkeni çözemez (ileti '$PEMF_VeriKoku' yazar)"
    )


def _katalog(dil: str) -> dict:
    return json.loads((KOK / "launcher" / "i18n" / f"{dil}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_D233_D276_arayuz_metni_SABIT_yol_tasimaz_konumu_yer_tutucuyla_alir(dil):
    ui = _katalog(dil)["ui"]
    assert "{{konum}}" in ui["uninBody"] and "{{ayrica}}" in ui["uninBody"], ui["uninBody"]
    assert "APPDATA" not in ui["uninBody"] and "PROGRAMDATA" not in ui["uninBody"], "uninBody'de sabit yol kaldı"
    assert "{{yollar}}" in ui["uninAyrica"]
    assert "PEMF_System\\PEMF_GUI" in ui["uninKonumBilinmiyor"] and "APPDATA%\\PEMF_GUI" in ui["uninKonumBilinmiyor"], (
        "komut düşerse yedek metin İKİ standart kökü birlikte söylemiyor"
    )


def test_KRITIK_D276_arayuz_konumu_launcher_KOMUTUNDAN_alir():
    html = INDEX.read_text(encoding="utf-8")
    bas = html.index('$("btn-uninstall").onclick')
    govde = html[bas : bas + 900]
    assert 'await invoke("kaldirma_veri_konumu")' in govde, "kaldırma diyaloğu gerçek konumu launcher'dan sormuyor"
    assert "askConfirm(t().uninTitle, uninMetni(k)" in govde, "diyalog gerçek konumla kurulmuyor"
    assert "t().uninBody" not in govde, "eski sabit metin hâlâ kullanılıyor"


_NODE = shutil.which("node")


@pytest.mark.skipif((_NODE is None) and not capraz.ZORUNLU, reason="node yok — yukarıdaki yapısal kapılar yine koşar")
@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_D233_arayuz_metni_GERCEKTE_konumu_ve_digerini_yazar(dil, tmp_path):
    """index.html'deki `tf` + `uninMetni` GERÇEK kaynaktan dilimlenip node'da değerlendirilir (sahte `t()` = katalog)."""
    html = INDEX.read_text(encoding="utf-8")
    tf = re.search(r"const tf = \(k, p\) => .*?;\n", html).group(0)
    bas = html.index("const uninMetni = (k) =>")
    son = html.index("});", bas) + 3
    js = (
        f"const UI = {json.dumps(_katalog(dil)['ui'], ensure_ascii=False)};\nconst t = () => UI;\n{tf}{html[bas:son]}\n"
        "const a = uninMetni({konum: 'C:\\\\ProgramData\\\\PEMF_System\\\\PEMF_GUI', diger: ['C:\\\\Users\\\\x\\\\AppData\\\\Roaming\\\\PEMF_GUI']});\n"
        "const b = uninMetni(null);\nconst c = uninMetni({konum: 'D:\\\\kok', diger: []});\n"
        "process.stdout.write(JSON.stringify([a, b, c]));\n"
    )
    (tmp_path / "s.js").write_text(js, encoding="utf-8")
    r = subprocess.run([_NODE, str(tmp_path / "s.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr[-800:]
    a, b, c = json.loads(r.stdout)
    assert "C:\\ProgramData\\PEMF_System\\PEMF_GUI" in a and "C:\\Users\\x\\AppData\\Roaming\\PEMF_GUI" in a, a
    assert "PEMF_System\\PEMF_GUI" in b and "APPDATA%\\PEMF_GUI" in b, b
    assert "D:\\kok" in c and "{{" not in c and _katalog(dil)["ui"]["uninAyrica"].split("{{")[0].strip() not in c, c


@pytest.mark.yalniz_yayin_makinesi  # CT1 c (Y324): yalnız yayın makinesi eseri — CI'da gerekçeli atlar, Y30'da atlarsa KIRMIZI
@pytest.mark.skipif(
    not os.environ.get("PEMF_TAURI_NSIS_DIZINI"), reason="PEMF_TAURI_NSIS_DIZINI yok (üretilmiş şablon dizini)"
)
def test_FIKSTUR_uretilmis_sablonla_AYNI():
    """Fikstür = üretilmiş şablonun birebir alıntısı mı (Tauri sürümü değişince yeniden alınmalı)."""
    d = Path(os.environ["PEMF_TAURI_NSIS_DIZINI"])
    gercek = {"installer.nsi": d.joinpath("installer.nsi").read_text(encoding="utf-8").splitlines()}
    gercek["utils.nsh"] = d.joinpath("utils.nsh").read_text(encoding="utf-8").splitlines()
    metin = SABLON.read_text(encoding="utf-8").splitlines()
    for i, s in enumerate(metin):
        m = re.match(r"; >>> (installer\.nsi|utils\.nsh):(\d+)(?:-(\d+))?$", s)
        if not m:
            continue
        a, b = int(m.group(2)), int(m.group(3) or m.group(2))
        alinti = metin[i + 1 : i + 1 + (b - a + 1)]
        assert alinti == gercek[m.group(1)][a - 1 : b], f"{m.group(1)}:{a}-{b} fikstürle AYNI değil — şablon değişmiş"
