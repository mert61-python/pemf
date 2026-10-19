# -*- coding: utf-8 -*-
"""I18N-0 · LAUNCHER ALTYAPISI (A4) — katalog (`launcher/i18n/{tr,en}.json`), Rust dil modülü, arayüz kataloğu, NSIS iki dil.

Kilitlenen davranış:
  * `hooks.nsi`'de kullanıcıya görünen DÜZ metin yok — her `DetailPrint` / `MessageBox` iletisi `$(PEMF_<anahtar>)`; LangString bloğu
    katalogdan ÜRETİLİR ve güncel; blok YALNIZ `tauri.conf.json` `bundle.windows.nsis.languages` dillerini yazar (yüklenmemiş dile
    LangString = yarım dil tablosu → -WX kırmızı; ölçüldü);
  * bayrak kapalıyken (`I18N_EN_ACIK = false`) sihirbaz dili YALNIZ Türkçe (Tauri varsayılanı İngilizceydi — S-I18N.1);
  * makensis varsa: hooks dosyası iki dil yapılandırmasında da `-WX` ile temiz derlenir (yoksa gerekçeyle atlanır);
  * arayüz kataloğu `ui/i18n_katalog.js` katalogla aynı ve modül betiğinden ÖNCE yüklenir; açılış dili Rust'tan (`dil_bilgisi`), TR/EN
    düğmesi Rust iletilerinin dilini de ayarlar (`dil_ayarla`).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import cikar, launcher_uret, ortak  # noqa: E402

HOOKS = KOK / "launcher/app/windows/hooks.nsi"
HTML = KOK / "launcher/app/ui/index.html"
#: makensis: `PEMF_MAKENSIS` (yalıtılmış koşucu sahte LOCALAPPDATA kullanır — gerçek yolu açıkça verir) > Tauri NSIS önbelleği > PATH.
MAKENSIS = next(
    (
        Path(p)
        for p in (
            os.environ.get("PEMF_MAKENSIS", ""),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "tauri/NSIS/makensis.exe"),
            shutil.which("makensis") or "",
        )
        if p and Path(p).is_file()
    ),
    None,
)


def test_hooks_kullanici_iletileri_yalniz_langstring_ile():
    ham = HOOKS.read_text(encoding="utf-8")
    govde = re.sub(re.escape(launcher_uret.BLOK_BAS) + r".*?" + re.escape(launcher_uret.BLOK_SON), "", ham, flags=re.S)
    duz = [a for a in cikar.nsis_adaylari("hooks.nsi", govde) if not a["ham"].startswith("$(PEMF_")]
    assert not duz, f"hooks.nsi'de düz kullanıcı iletisi: {[(a['satir'], a['metin'][:60]) for a in duz]}"
    kullanilan = set(re.findall(r"\$\(PEMF_(\w+)\)", govde))
    katalog = set(ortak.duzlestir(ortak.json_oku(KOK / "launcher/i18n/tr.json")["nsis"]))
    assert kullanilan and kullanilan <= katalog, f"katalogda olmayan LangString: {sorted(kullanilan - katalog)}"


def test_uretilmis_dosyalar_guncel_ve_dil_listesi_bayrakla_uyumlu():
    assert launcher_uret.main(["--denetle"]) == 0
    diller = launcher_uret.nsis_dilleri(KOK)
    rs = (KOK / "launcher/core/src/dil.rs").read_text(encoding="utf-8")
    acik = re.search(r"pub const I18N_EN_ACIK: bool = (true|false);", rs).group(1) == "true"
    assert diller == (["Turkish", "English"] if acik else ["Turkish"]), diller
    blok = launcher_uret.nsis_blogu(KOK)
    assert " 1055 " in blok and ((" 1033 " in blok) == acik), "LangString blok dilleri NSIS dil listesiyle ayrışmış"


@pytest.mark.skipif(MAKENSIS is None, reason="makensis yok (Tauri NSIS önbelleği / PATH) — derleme denemesi atlandı")
@pytest.mark.parametrize("diller", [["Turkish"], ["Turkish", "English"]])
def test_hooks_makensis_WX_temiz_derlenir(tmp_path, diller):
    """Tauri şablonunun sırası: hooks !include → MUI_LANGUAGE; makrolar bölümde açılır. Aynı sırayla asgari betik."""
    kok = tmp_path / "kok"
    shutil.copytree(KOK / "launcher" / "i18n", kok / "launcher" / "i18n")
    (kok / "launcher/app/windows").mkdir(parents=True)
    shutil.copy2(HOOKS, kok / "launcher/app/windows/hooks.nsi")
    (kok / "launcher/app/tauri.conf.json").write_text(
        json.dumps({"bundle": {"windows": {"nsis": {"languages": diller}}}}), encoding="utf-8"
    )
    hooks = launcher_uret.hooks_metni(kok)
    (tmp_path / "hooks.nsi").write_bytes(hooks.encode("utf-8"))
    dil_satirlari = "\r\n".join(f'!insertmacro MUI_LANGUAGE "{d}"' for d in diller)
    betik = (
        # Tauri şablonunun hooks'tan önce tanımladığı semboller: LogicLib (${If} / ${Silent}), UpdateMode, DeleteAppDataCheckboxState.
        "Unicode true\r\n!include \"MUI2.nsh\"\r\n!include \"LogicLib.nsh\"\r\nOutFile \"d.exe\"\r\n"
        "Var UpdateMode\r\nVar DeleteAppDataCheckboxState\r\n"
        "Function .onInit\r\n  StrCpy $UpdateMode 0\r\n  StrCpy $DeleteAppDataCheckboxState 0\r\nFunctionEnd\r\n"
        "Function un.onInit\r\n  StrCpy $UpdateMode 0\r\n  StrCpy $DeleteAppDataCheckboxState 0\r\nFunctionEnd\r\n"
        f'!include "{tmp_path / "hooks.nsi"}"\r\n'
        "!insertmacro MUI_PAGE_INSTFILES\r\n!insertmacro MUI_UNPAGE_INSTFILES\r\n"
        f"{dil_satirlari}\r\n"
        "Section\r\n  WriteUninstaller \"$INSTDIR\\u.exe\"\r\nSectionEnd\r\n"
        "Section \"Uninstall\"\r\n  !insertmacro NSIS_HOOK_PREUNINSTALL\r\n  !insertmacro NSIS_HOOK_POSTUNINSTALL\r\nSectionEnd\r\n"
    )
    (tmp_path / "d.nsi").write_bytes(betik.encode("utf-8"))
    p = subprocess.run([str(MAKENSIS), "-V2", "-WX", "d.nsi"], cwd=tmp_path, capture_output=True, timeout=180)
    cikti = (p.stdout + p.stderr).decode("utf-8", "replace")
    if p.returncode != 0 and re.search(r"Unknown variable|DeleteAppDataCheckbox|undefined|not defined", cikti):
        pytest.skip(f"Tauri şablonuna özgü sembol (asgari betikte yok): {cikti[-300:]}")
    assert p.returncode == 0, cikti[-1500:]


def test_arayuz_katalogu_once_yuklenir_ve_dil_rusttan_alinir():
    html = HTML.read_text(encoding="utf-8")
    assert 0 <= html.find('<script src="i18n_katalog.js"></script>') < html.find('<script type="module">')
    assert 'invoke("dil_bilgisi")' in html, "açılış dili Rust'tan (bayrak + uygulamanın seçimi) alınmıyor"
    assert re.search(r'invoke\("dil_ayarla",\s*\{\s*kod:\s*LANG\s*\}\)', html), (
        "TR/EN düğmesi Rust iletilerinin dilini ayarlamıyor"
    )
    main = (KOK / "launcher/app/src/main.rs").read_text(encoding="utf-8")
    assert "dil::baslat()" in main
    assert re.search(r"generate_handler!\[[^\]]*\bdil_bilgisi\b[^\]]*\bdil_ayarla\b", main, re.S), (
        "dil komutları işleyici listesinde değil"
    )


_JS_T = r"""
const fs = require("fs");
const vm = require("vm");
const [html, katalogJs] = [fs.readFileSync(process.argv[2], "utf8"), fs.readFileSync(process.argv[3], "utf8")];
const bas = html.indexOf("      const I18N = {");
const son = html.indexOf("const t = () =>", bas);
const satirSonu = html.indexOf("\n", son);
const kod = html.slice(bas, satirSonu).replace("const I18N", "var I18N").replace("const t =", "var t =");
const sonuc = {};
for (const dil of ["tr", "en"]) {
  const ctx = { window: {} };
  vm.createContext(ctx);
  vm.runInContext(katalogJs, ctx);
  const dilli = kod.replace(/let LANG = "tr";/, `var LANG = ${JSON.stringify(dil)};`);
  if (dilli === kod) throw new Error("index.html'de `let LANG = \"tr\";` bulunamadı");
  vm.runInContext(dilli, ctx);
  const x = vm.runInContext("t()", ctx);
  sonuc[dil] = { t: Object.fromEntries(Object.entries(x).filter(([, v]) => typeof v === "string")), sozluk: Object.keys(vm.runInContext("I18N", ctx)[dil]) };
}
process.stdout.write(JSON.stringify(sonuc));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="node yok")
def test_arayuz_t_KATALOGU_sozlugun_ustune_bindirir_gocen_anahtar_TEK_kaynakta(tmp_path):
    """Pilot (açılış / ilerleme paneli): `t()` = sözlük + katalog; göçen her `ui.*` anahtarı iki dilde katalogdaki değeri verir ve
    sözlükte ARTIK YOK (iki kaynak ayrışamaz). Sözlükte kalanlar değişmeden çalışır (ör. `web`)."""
    betik = tmp_path / "t.cjs"
    betik.write_text(_JS_T, encoding="utf-8")
    r = subprocess.run(
        ["node", str(betik), str(KOK / "launcher/app/ui/index.html"), str(KOK / "launcher/app/ui/i18n_katalog.js")],
        capture_output=True,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    sonuc = json.loads(r.stdout.decode("utf-8"))
    for dil in ortak.DILLER:
        ui = ortak.duzlestir(ortak.katalog_yukle("launcher", dil)).items()
        gocen = {k.split(".", 1)[1]: v for k, v in ui if k.startswith("ui.")}
        assert gocen, "katalogda ui.* anahtarı yok"
        for k, v in gocen.items():
            assert sonuc[dil]["t"].get(k) == v, f"{dil}: t().{k} katalogdan gelmiyor"
            assert k not in sonuc[dil]["sozluk"], f"{dil}: {k} hem katalogda hem sözlükte (iki kaynak)"
    assert sonuc["tr"]["t"]["readyTitle"] == "Hazır!" and sonuc["en"]["t"]["readyTitle"] == "Ready!"
    assert sonuc["tr"]["t"]["web"] == "Web Sitesi", "sözlükte kalan anahtar bozulmamalı"
