# -*- coding: utf-8 -*-
"""K-6 · KATALOG PAKETE GİRER (T14) — her yüzeyin kataloğu sevk edilen pakette, çalışma anında DİSKTEN / AĞDAN aranmadan bulunur.

  * Sunucu: PyInstaller `datas` (`apps/backend/i18n` → `_internal/i18n`, AST) + app katmanı kökü (`make_base_zip.APP_ROOTS`, AST) +
    `ceviri.katalog_dizini()` donmuş dalı ÖNCE (`sys._MEIPASS/i18n`).
  * Launcher: `core/src/dil.rs` iki kataloğu `include_str!` ile İKİLİYE gömer; arayüz kataloğu `ui/i18n_katalog.js` (frontendDist `./ui`
    içinde, `index.html` onu modül betiğinden ÖNCE eşzamanlı yükler) ve katalogla AYNI.
  * Arayüz / site / DEMA: kataloglar STATİK içe aktarma (paketleyici gömer); `fetch` / `http` ile çalışma anı yükleme YOK; uygulama kökü
    i18n'i ilk içe aktarır.
Donmuş EXE'de gerçek okuma §6-C yerel kurulum dumanında ölçülür (paketli EXE'de `X-PEMF-Dil: en` ile bir ileti).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import launcher_uret, ortak  # noqa: E402


def _yorumsuz_ts(s: str) -> str:
    return ortak.ts_yorumsuz(s)  # I18NI-A2.5: dizgi farkında soyucu


def test_K6_sunucu_spec_datas_ve_app_katmani():
    spec = ast.parse((KOK / "build_tools" / "PEMF_Backend_onedir.spec").read_text(encoding="utf-8"))
    eklenen = {
        (ast.unparse(n.args[0].elts[0]), ast.unparse(n.args[0].elts[1]))
        for n in ast.walk(spec)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "append"
        and getattr(n.func.value, "id", "") == "datas"
        and n.args
        and isinstance(n.args[0], ast.Tuple)
        and len(n.args[0].elts) == 2
    }
    assert ("_i18n_dir", "'i18n'") in eklenen
    zipb = ast.parse((KOK / "build_tools" / "make_base_zip.py").read_text(encoding="utf-8"))
    kokler = []
    for n in zipb.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "APP_ROOTS":
            sol = n.value.left if isinstance(n.value, ast.BinOp) else n.value
            kokler = [e.value for e in sol.elts if isinstance(e, ast.Constant)]
    assert "PEMF_Backend/_internal/i18n" in kokler


def test_K6_sunucu_donmus_dal_once():
    src = (KOK / "apps/backend/utils/ceviri.py").read_text(encoding="utf-8")
    govde = src[src.index("def katalog_dizini") : src.index("def _duzlestir")]
    assert govde.index('getattr(sys, "frozen", False)') < govde.index("Path(__file__)"), (
        "donmuş dal yukarı yürüyen yoldan ÖNCE değil"
    )


def test_K6_launcher_katalogu_ikiliye_gomulu_ve_arayuz_katalogu_esit():
    rs = (KOK / "launcher/core/src/dil.rs").read_text(encoding="utf-8")
    for dil in ortak.DILLER:
        assert f'include_str!("../../i18n/{dil}.json")' in rs, f"launcher {dil} kataloğu ikiliye gömülmüyor"
    assert launcher_uret.main(["--denetle"]) == 0
    html = (KOK / "launcher/app/ui/index.html").read_text(encoding="utf-8")
    i_js, i_mod = html.find('<script src="i18n_katalog.js"></script>'), html.find('<script type="module">')
    assert 0 <= i_js < i_mod, "i18n_katalog.js modül betiğinden ÖNCE eşzamanlı yüklenmeli"
    conf = ortak.json_oku(KOK / "launcher/app/tauri.conf.json")
    assert conf["build"]["frontendDist"] == "./ui" and (KOK / "launcher/app/ui/i18n_katalog.js").is_file()


def test_K6_arayuz_site_dema_kataloglari_statik_ice_aktarma():
    for yol in (
        "apps/ui/src/i18n/kaynaklar.ts",
        "apps/web/src/i18n/kaynaklar.ts",
        "dema-terapi-simülatörü/src/i18n/index.ts",
    ):
        kod = _yorumsuz_ts((KOK / yol).read_text(encoding="utf-8"))
        assert re.search(r"""import\s+\w+\s+from\s+["']\./(tr|en)(/\w+)?\.json["']""", kod), (
            f"{yol}: statik JSON içe aktarması yok"
        )
        assert "fetch(" not in kod and "http" not in kod, f"{yol}: katalog çalışma anında yüklenmemeli"
    assert re.search(r'^import\s+"@/i18n";', (KOK / "apps/ui/app/_layout.tsx").read_text(encoding="utf-8"), re.M)
    assert re.search(
        r"""^import\s+['"]\./i18n['"]""", (KOK / "apps/web/src/main.tsx").read_text(encoding="utf-8"), re.M
    )
