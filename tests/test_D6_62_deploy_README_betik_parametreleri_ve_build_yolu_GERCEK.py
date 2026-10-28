# Author: mertaygn, cglrgrkn
"""D6.62 (c) (B-3.101) — `deploy/README.md`'nin betik parametreleri, kurucu bayrağı ve build çıktı yolu iddiaları betiklerin KENDİSİYLE aynı.

KUSUR (ölçüldü, HEAD `ebf1c3fe`): §6 "Klinik tünel açıksa auth otomatik zorunlu (installer `-EnableTunnel` bunu yapar)" — Inno kurucusunun
çağırdığı `setup_services.ps1`'de `-EnableTunnel` parametresi YOK (tünel profilden, `deploy\\device.env`; zorunlu auth'u backend kendisi
uygular: `backend_service._force_auth_for_tunnel`); `-EnableTunnel` yalnız `install_backend_service.ps1`'in (A-11) parametresidir. §7
"Build: `scripts\\build_backend_exe.ps1` → `C:\\PEMF_BUILD\\dist\\PEMF_Backend\\`" — betiğin varsayılan çıktı kökü `guii\\PEMF_BUILD`
(`-BuildRoot` verilmezse); `C:\\PEMF_BUILD` yalnız `-BuildRoot C:\\PEMF_BUILD` ile.

KAPI: README'deki her `-Parametre`, aynı madde / satırda adı geçen betiğin (adı geçmiyorsa "kurucu / installer" = `setup_services.ps1`)
`param(...)` bloğunda TANIMLI olmalı; build yolu iddiası betiğin varsayılan `$BuildRoot` atamasıyla aynı olmalı. Kod çitleri (```) atlanır.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
README = KOK / "deploy" / "README.md"
#: "kurucu / installer" — Inno kurucusu (`build_tools/PEMF_Backend_Setup.iss`) `setup_services.ps1`'i çağırır (README §2).
KURUCU_BETIGI = "setup_services.ps1"


def _parametreler(betik: str) -> set[str]:
    metin = (KOK / "scripts" / betik).read_text(encoding="utf-8-sig")
    m = re.search(r"^param\s*\((.*?)^\)", metin, re.S | re.M | re.I)
    assert m, f"aparat: {betik} param bloğu yok"
    govde = "\n".join(s for s in m.group(1).splitlines() if not s.lstrip().startswith("#"))
    return {a.lower() for a in re.findall(r"\]\s*\$(\w+)", govde)}


def _gorunur() -> str:
    """README'nin okura GÖRÜNEN metni: kod çitleri (```) ve HTML yorumları atılır (yalnız yorumda kalan iddia SAYILMAZ)."""
    metin = re.sub(r"```.*?```", "", README.read_text(encoding="utf-8"), flags=re.S)
    return re.sub(r"<!--.*?-->", "", metin, flags=re.S)


def _maddeler() -> list[str]:
    """README'yi madde / paragraf birimlerine böl; her birim kendi satırları + devam satırlarıdır."""
    return [b for b in re.split(r"\n(?=\s*(?:[-*>|]|\d+\.)\s)|\n\s*\n", _gorunur()) if b.strip()]


def test_KRITIK_README_parametreleri_betiklerde_TANIMLI():
    betikler = sorted(p.name for p in (KOK / "scripts").glob("*.ps1"))
    hatalar = []
    for birim in _maddeler():
        adlar = {b for b in betikler if b in birim}
        # Her kod parçası (`…`) içindeki TÜM `-Parametre`ler (parça başına ilki değil — m2 mutantı ikinciyi kaçırıyordu).
        parametreler = [
            p for parca in re.findall(r"`([^`]*)`", birim) for p in re.findall(r"(?<![\w-])-([A-Z][A-Za-z]+)\b", parca)
        ]
        if not parametreler:
            continue
        if not adlar:
            if not re.search(r"installer|kurucu", birim, re.I):
                continue
            adlar = {KURUCU_BETIGI}
        tanimli = set().union(*(_parametreler(b) for b in adlar))
        hatalar += [
            f"-{p} ({', '.join(sorted(adlar))}): {birim.strip()[:120]}"
            for p in parametreler
            if p.lower() not in tanimli
        ]
    assert not hatalar, f"deploy/README betikte TANIMSIZ parametre anıyor: {hatalar}"


def test_KRITIK_kurucu_EnableTunnel_DEGIL_tunel_profilden_auth_backendde():
    assert "enabletunnel" not in _parametreler(KURUCU_BETIGI), (
        "aparat: kurucu betiği artık -EnableTunnel alıyor — belge yeniden yazılmalı"
    )
    assert "enabletunnel" in _parametreler("install_backend_service.ps1")
    bs = (KOK / "apps" / "backend" / "backend_service.py").read_text(encoding="utf-8")
    assert re.search(r"def _maybe_start_tunnel\(.*?\n    _force_auth_for_tunnel\(logger\)", bs, re.S), (
        "aparat: backend tünel açılırken auth'u artık zorlamıyor — README §6 iddiası yeniden ölçülmeli"
    )
    satir = [s for s in _gorunur().splitlines() if "Klinik tünel" in s]
    assert len(satir) == 1 and "_force_auth_for_tunnel" in satir[0] and "device.env" in satir[0], satir


def test_KRITIK_build_cikti_yolu_betigin_VARSAYILANI():
    betik = (KOK / "scripts" / "build_backend_exe.ps1").read_text(encoding="utf-8-sig")
    assert re.search(r'if \(-not \$BuildRoot\) \{ \$BuildRoot = Join-Path \$GuiRoot "PEMF_BUILD" \}', betik), (
        "aparat: build_backend_exe.ps1 varsayılan çıktı kökü değişti — README §7 yeniden yazılmalı"
    )
    build = [s for s in _gorunur().splitlines() if "build_backend_exe.ps1" in s and "→" in s]
    assert build, "README §7 build çıktı satırı yok"
    for s in build:
        hedef = s.split("→", 1)[1]
        assert r"guii\PEMF_BUILD\dist\PEMF_Backend" in hedef, f"build varsayılan çıktısı yanlış: {s}"
        assert r"C:\PEMF_BUILD" not in hedef or "-BuildRoot C:\\PEMF_BUILD" in hedef, (
            f"C:\\PEMF_BUILD yalnız -BuildRoot ile: {s}"
        )
