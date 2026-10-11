# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.36 (B-10.201) · A-31 (sahip kararı: ONEFILE paket tanımı SİLİNİR) · Y26 — onedir spec'inde F4 sonrası ÖLÜ paket girdisi
(var olmayan yere bakan `os.path.exists` korumalı datas) kalmaz; onefile spec'i ve ona bağlı belge satırı / kapı kapsamı kaldırıldı.

Kusur [ÖLÇTÜM]: iki spec de `<proje>\\database\\*_template.db`yi `exists()` korumasıyla ekliyordu; F4 (`283c419`) şablonları
`apps/backend/database`e taşıdığından girdi paket hattında SESSİZCE düşüyordu. Yönlendirmek, Y26'nın kapattığı şablon-kopya yolunu
(D2.34) uyandırırdı → çözüm KALDIRMA. Onefile spec'i ölçülüp reddedilmiş bir biçimdi ama ikinci kopya olarak yaşıyor ve kapılar onu
da tarıyordu.

Ölçüm: spec PyInstaller OLMADAN, GERÇEK metniyle alt süreçte koşar (sahte `PyInstaller.utils.hooks` + Analysis/PYZ/EXE/COLLECT;
`os.path.exists` kayıtçı; çalışma dizini depo kökü → `project_path`). Depo kökü ALTINDA sorulup BULUNAMAYAN her yol, aşağıdaki
gerekçeli isteğe bağlı derleme girdisi listesinde olmalı — listede olmayan bulunamayan yol ÖLÜ girdidir.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SPEC = KOK / "build_tools" / "PEMF_Backend_onedir.spec"

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="spec yalnız Windows derlemesinde koşar (DLL/yol mantığı)"
)

# Derleme makinesinde bulunur, depoda YOKTUR — her biri spec'te açık uyarı/atla dalıyla.
_ISTEGE_BAGLI = {
    "data/cloud_mqtt_provision.json": "sahibe özel bulut provizyonu (make_cloud_provision.py üretir; yoksa spec UYARI basar)",
    "bin/cloudflared": "uzaktan erişim tüneli — elle eklenir (deploy/README §4)",
    "apps/ui/dist": "web arayüzü derleme çıktısı (expo export; build_installer önce üretir)",
    "dema-terapi-simülatörü/dist": "simülatör yerelde derlenir, depoda takipsiz (D1.91 denetimi gömmeden önce)",
    "build_tools/_static_password.py": "kaynak şifreleme parolası — .gitignore'da; yoksa şifresiz derleme",
}

_SURUCU = r'''
import json, os, sys, types
spec, cikti = sys.argv[1], sys.argv[2]
sorgular = []
_gercek = os.path.exists
def _kayitci(p):
    s = _gercek(p)
    sorgular.append([os.fspath(p), bool(s)])
    return s
os.path.exists = _kayitci
def _bos(*a, **k):
    return []
def _hepsi(*a, **k):
    return ([], [], [])
hooks = types.ModuleType("PyInstaller.utils.hooks")
hooks.collect_data_files = hooks.collect_dynamic_libs = hooks.copy_metadata = _bos
# D4.17: spec birinci-taraf paket toplaması BOŞ dönerse derlemeyi durdurur → sahte toplayıcı boş olmayan liste döner
# (bu sürücü datas'ı ölçer; gizli içe aktarmayı test_spec_BIRINCI_TARAF_paketleri_TOPLANIR_D417_D418 ölçer).
hooks.collect_submodules = lambda pkg, *a, **k: [pkg + '._sahte']
hooks.collect_all = _hepsi
pi, ut = types.ModuleType("PyInstaller"), types.ModuleType("PyInstaller.utils")
pi.utils, ut.hooks = ut, hooks
sys.modules.update({"PyInstaller": pi, "PyInstaller.utils": ut, "PyInstaller.utils.hooks": hooks})
yakalanan = {}
class Analysis:
    def __init__(self, scripts, **kw):
        yakalanan["datas"] = [[os.fspath(s), d] for s, d in kw.get("datas", [])]
        self.datas = [(os.path.join(d, os.path.basename(s)), s, "DATA") for s, d in kw.get("datas", [])]
        self.pure, self.scripts, self.binaries, self.zipfiles = [], [], [], []
class _Bos:
    def __init__(self, *a, **k):
        pass
g = {"__name__": "__main__", "__file__": spec, "Analysis": Analysis, "PYZ": _Bos, "EXE": _Bos, "COLLECT": _Bos}
exec(compile(open(spec, encoding="utf-8").read(), spec, "exec"), g)
yakalanan["exists"] = sorgular
json.dump(yakalanan, open(cikti, "w", encoding="utf-8"), ensure_ascii=False)
'''


@pytest.fixture(scope="module")
def kosum(tmp_path_factory) -> dict:
    d = tmp_path_factory.mktemp("spec_d236")
    surucu, cikti = d / "spec_surucu.py", d / "cikti.json"
    surucu.write_text(_SURUCU, encoding="utf-8")
    p = subprocess.run(
        [sys.executable, str(surucu), str(SPEC), str(cikti)],
        cwd=str(KOK),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert p.returncode == 0 and cikti.exists(), (
        f"spec koşmadı (rc={p.returncode}):\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}"
    )
    return json.loads(cikti.read_text(encoding="utf-8"))


def _depo_goreli(yol: str) -> str | None:
    tam = os.path.normcase(os.path.normpath(yol))
    kok = os.path.normcase(os.path.normpath(str(KOK)))
    if not tam.startswith(kok + os.sep):
        return None
    return tam[len(kok) + 1 :].replace("\\", "/")


def test_KRITIK_spec_OLU_paket_girdisi_YOK_bulunamayan_her_yol_GEREKCELI_istege_bagli_D236(kosum):
    istege = {k.lower() for k in _ISTEGE_BAGLI}
    olu = sorted(
        {
            g
            for yol, var in kosum["exists"]
            if not var and (g := _depo_goreli(yol)) is not None and g.lower() not in istege
        }
    )
    assert not olu, f"spec depoda OLMAYAN yere bakan paket girdisi taşıyor (sessiz düşüş, ölü girdi): {olu}"


def test_KRITIK_spec_sablon_DB_SORMAZ_ve_GOMMEZ_D236(kosum):
    sorulan = [y for y, _ in kosum["exists"] if y.lower().endswith("_template.db")]
    gomulen = [s for s, _ in kosum["datas"] if s.lower().endswith("_template.db")]
    assert not sorulan and not gomulen, (
        f"spec DB şablonu arıyor/gömüyor (Y26: kaldırıldı): sorulan={sorulan} gomulen={gomulen}"
    )


def test_KARSIT_spec_GERCEKTEN_kostu_zorunlu_girdiler_GOMULDU_D236(kosum):
    """Ölçüm boş geçmesin: spec sonuna dek koştu ve depodaki zorunlu girdiler datas'ta."""
    gomulen = {g.lower() for s, _ in kosum["datas"] if (g := _depo_goreli(s))}
    for zorunlu in (
        "deploy",
        "config/pemf_config.json",
        "frontend_version.json",
        "ai_hub/__init__.py",
        "bin/mosquitto",
    ):
        assert zorunlu in gomulen, (
            f"{zorunlu} datas'ta yok — sürücü spec'i koşturamadı mı? {sorted(g for g in gomulen if g)[:20]}"
        )


def test_KRITIK_A31_onefile_spec_SILINDI_belge_ve_kapilar_ANMAZ_D236():
    assert not (KOK / "build_tools" / "PEMF_Backend_onefile.spec").exists(), "A-31: onefile spec'i hâlâ depoda"
    kendi = Path(__file__).resolve()
    anan = [
        str(p.relative_to(KOK))
        for p in [KOK / "build_tools" / "README.md", *sorted((KOK / "tests").glob("test_*.py"))]
        if p.resolve() != kendi and "PEMF_Backend_onefile" in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert not anan, f"silinen onefile spec'ini anan belge/kapı: {anan}"
