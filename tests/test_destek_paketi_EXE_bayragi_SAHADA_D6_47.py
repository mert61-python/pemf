# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.47 (B-10.60 · Y32) — backend çökmüşken destek paketi SAHADA alınabilir: `PEMF_Backend.exe --destek-paketi`.

Kusur: RUNBOOK "Backend çökmüşse: `python tools\\destek_paketi.py`" diyordu (tools/README de aynı yolu anlatıyordu). Sahada Python
YOK; tek çalıştırılabilir launcher'ın kurduğu `PEMF_Backend.exe`dir ve aracın EXE'de alt komutu yoktu (spec yalnız `tools.kurtarma`yı
paketliyordu; araç donmuş EXE'de depo kökünü arayıp içe aktarmada ölürdü — D2.35'in ikizi). Destek tam da backend ayakta değilken
gerekir. Sahip kararı Y32: EXE'ye DESTEK PAKETİ bayrağı eklenir.

Kapı:
  (1) GERÇEK `backend_service.main(["--destek-paketi", …])` sunucuyu başlatmadan PII maskeli zip üretir;
  (2) donmuş EXE benzetimi (D2.35 deseni: araç depo DIŞINDAKİ paket dizininde, `sys.frozen`) — araç içe aktarılır ve `--help` verir;
  (3) `backend_service`in içe aktardığı her `tools.<araç>` PyInstaller spec'inin gizli içe aktarımlarında (pakete girer);
  (4) RUNBOOK "Destek paketi" bölümündeki komut satırları GERÇEK `_destek_paketi_mi`den geçen `PEMF_Backend.exe` çağrısıdır
      (`python tools…` yok); tools/README satırı EXE yolunu söyler.
"""

from __future__ import annotations

import ast
import json
import re
import shlex
import shutil
import zipfile
from pathlib import Path

from betik_alt_sureci import kostur, yalitik_ortam

DEPO = Path(__file__).resolve().parents[1]
RUNBOOK = DEPO / "docs" / "RUNBOOK.md"
SPEC = DEPO / "build_tools" / "PEMF_Backend_onedir.spec"


def _sozcukler(komut: str) -> list[str]:
    t = [s.strip('"') for s in shlex.split(komut, posix=False)]
    return t[1:] if t and t[0] == "&" else t  # PowerShell çağrı işleci


# ── (1) gerçek alt komut ──────────────────────────────────────────────────────
def test_KRITIK_EXE_destek_paketi_alt_komutu_SUNUCUSUZ_zip_uretir_D6_47(temp_app_data, tmp_path):
    import backend_service as bs

    hedef = tmp_path / "paket" / "destek.zip"
    try:
        rc = bs.main(["--destek-paketi", "--cikti", str(hedef), "--veri-dizini", str(temp_app_data)])
    except SystemExit as e:
        raise AssertionError(
            f"PEMF_Backend.exe'de `--destek-paketi` alt komutu YOK ya da argümanlarını araca ULAŞTIRMIYOR: bir ayrıştırıcı "
            f"çıktı (SystemExit {e.code})"
        ) from None
    assert rc == 0, f"destek paketi alt komutu başarısız (rc={rc})"
    assert hedef.is_file(), "destek paketi alt komutu zip yazmadı"
    with zipfile.ZipFile(hedef) as z:
        adlar = set(z.namelist())
    assert {"OZET.json", "saglik.json"} <= adlar, f"zip destek paketi değil: {sorted(adlar)}"


# ── (2) donmuş EXE benzetimi ──────────────────────────────────────────────────
_SURUCU = r"""
import json, sys
from pathlib import Path
PAKET, BACKEND, DEPO = {paket!r}, {backend!r}, {depo!r}
sys.frozen = True
sys._MEIPASS = PAKET
sys.path.insert(0, PAKET)
sys.path.append(BACKEND)
sonuc = {{}}
try:
    import tools.destek_paketi as d
    sonuc["ice_aktarma"] = "tamam"
    sonuc["depo_koku_yolda"] = any(p and Path(p).resolve() == Path(DEPO).resolve() for p in sys.path)
    try:
        sonuc["rc"] = d.main(["--help"])
    except SystemExit as e:
        sonuc["rc"] = e.code
except BaseException as e:
    sonuc["kacan"] = type(e).__name__ + ": " + str(e)[:300]
print("SONUC " + json.dumps(sonuc, default=str))
"""


def test_KRITIK_donmus_EXEde_depo_DISINDA_destek_paketi_ICE_AKTARILIR_D6_47(tmp_path):
    paket = tmp_path / "paket"
    (paket / "tools").mkdir(parents=True)
    shutil.copy2(DEPO / "tools" / "destek_paketi.py", paket / "tools" / "destek_paketi.py")
    (paket / "tools" / "__init__.py").write_text("", encoding="utf-8")
    surucu = tmp_path / "donmus_surucu.py"
    surucu.write_text(
        _SURUCU.format(paket=str(paket), backend=str(DEPO / "apps" / "backend"), depo=str(DEPO)), encoding="utf-8"
    )
    p = kostur([str(surucu)], cwd=tmp_path, env=yalitik_ortam(tmp_path / "ev"), sure=120)
    satir = next((s for s in p.stdout.splitlines() if s.startswith("SONUC ")), None)
    assert satir, f"aparat: donmuş sürücü sonuç basmadı (rc={p.returncode}):\n{(p.stdout + p.stderr)[-1500:]}"
    sonuc = json.loads(satir[len("SONUC ") :])
    assert "kacan" not in sonuc, f"`PEMF_Backend.exe --destek-paketi` İÇE AKTARMADA öldü: {sonuc['kacan']}"
    assert sonuc["rc"] == 0 and "--cikti" in p.stdout, f"araç `--help`i tanımadı: {sonuc}\n{p.stdout[-600:]}"
    assert not sonuc["depo_koku_yolda"], "donmuş araç depo kökünü sys.path'e ekledi (paketi gölgeleyebilir — D2.35)"


# ── (3) spec ──────────────────────────────────────────────────────────────────
def test_KRITIK_backend_servisinin_cagirdigi_HER_tools_araci_PAKETE_girer_D6_47():
    kaynak = (DEPO / "apps" / "backend" / "backend_service.py").read_text(encoding="utf-8")
    araclar = {
        d.module
        for d in ast.walk(ast.parse(kaynak))
        if isinstance(d, ast.ImportFrom) and d.module and d.module.startswith("tools.")
    }
    assert "tools.destek_paketi" in araclar, f"backend_service `tools.destek_paketi`yi çağırmıyor: {sorted(araclar)}"
    paketlenen = {d.value for d in ast.walk(ast.parse(SPEC.read_text(encoding="utf-8"))) if isinstance(d, ast.Constant)}
    eksik = sorted(araclar - paketlenen)
    assert not eksik, f"backend_service'in çağırdığı araç PyInstaller spec'inde YOK (sahada içe aktarılamaz): {eksik}"


# ── (4) belgeler ──────────────────────────────────────────────────────────────
def test_KRITIK_RUNBOOK_destek_paketi_komutlari_SAHADA_calisir_D6_47():
    import backend_service as bs
    from utils.backup_recovery import KURTARMA_EXE

    metin = RUNBOOK.read_text(encoding="utf-8")
    bolum = re.search(r"^## Destek paketi.*?(?=^## )", metin, re.S | re.M)
    assert bolum, "aparat: RUNBOOK'ta '## Destek paketi' bölümü yok"
    komutlar = [
        s.split("#", 1)[0].strip()
        for s in bolum.group(0).splitlines()
        if ("destek_paketi" in s or "--destek-paketi" in s) and not s.lstrip().startswith("#")
    ]
    assert komutlar, "RUNBOOK 'Destek paketi' bölümünde backend çökmüşken çalışan komut YOK"
    for komut in komutlar:
        t = _sozcukler(komut)
        assert t and Path(t[0].replace("\\", "/")).name == "PEMF_Backend.exe", (
            f"destek paketi komutu sahada ÇALIŞMAZ (Python yok; tek çalıştırılabilir PEMF_Backend.exe): {komut}"
        )
        assert t[0].replace("$env:LOCALAPPDATA", "%LOCALAPPDATA%") == KURTARMA_EXE.strip('"'), (
            f"destek paketi komutu launcher'ın kurduğu EXE yolunu göstermiyor: {t[0]}"
        )
        ayir = getattr(bs, "_destek_paketi_mi", None)
        assert ayir is not None and ayir(t[1:]) is not None, f"`--destek-paketi` alt komutu yok: {komut}"


def test_tools_README_destek_paketi_satiri_EXE_yolunu_soyler_D6_47():
    satirlar = [
        s for s in (DEPO / "tools" / "README.md").read_text(encoding="utf-8").splitlines() if "`destek_paketi.py`" in s
    ]
    assert len(satirlar) == 1, f"aparat: tools/README'de tek `destek_paketi.py` satırı bekleniyordu: {len(satirlar)}"
    assert "PEMF_Backend.exe --destek-paketi" in satirlar[0], "tools/README destek paketinin SAHADAKİ yolunu söylemiyor"
