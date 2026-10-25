# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3.46 (B-10.200 · Y34, sahip) — Mac / Linux backend çıktısı korumasızsa ÜRETİLMEZ: kod koruması kapısı paketlemeden ÖNCE.

ÖLÇÜLEN (HEAD): Linux / macOS hedefleri aynı spec'i koşar ama compile_pyd'yi HİÇ koşmaz → `_internal/ai_hub` diskte DÜZ .py (koruma sıfır;
`pyz_koruma_kapisi.py` başlığında "bilinen" olarak kayıtlı). `linux-backend.yml` ve `build_mac.sh`ta bunu ölçen adım YOK — artefakt
sessizce üretiliyordu. Y34: korumasız çıktı ÜRETİLMEZ (kapı kırmızı); Cython zinciri gelene kadar Mac / Linux "Yakında".
Kapı: ortak sayaç `duz_py_var_mi(dist)` + `--yalniz-duz-py` kipi (PYZ okuyucu gerekmez) sahte dist ile; iş akışı YAML ayrıştırılarak ve
build_mac.sh sırasıyla doğrulanır. ⚠️ Bilinçli sonuç: bugünkü spec'le Mac / Linux CI artefaktı KIRMIZI olur (A-43: itilmedi).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "scripts"))
import pyz_koruma_kapisi as pk  # noqa: E402

BETIK = KOK / "scripts" / "pyz_koruma_kapisi.py"


def _dist(tmp_path: Path, dosyalar: list[str]) -> Path:
    d = tmp_path / "dist" / "PEMF_Backend"
    for rel in dosyalar:
        p = d / "_internal" / "ai_hub" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# sahte\n", encoding="utf-8")
    return d


def _kos(*arg) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BETIK), *map(str, arg)], capture_output=True, text=True, timeout=60)


def test_KRITIK_D3_46_duz_py_SAYILIR_ve_kip_KIRMIZI_doner(tmp_path):
    d = _dist(tmp_path, ["__init__.py", "inference_em_kedi/__init__.py", "inference_em_kedi/model.py", "x.py"])
    assert sorted(p.replace("\\", "/") for p in pk.duz_py_var_mi(d, "ai_hub")) == ["inference_em_kedi/model.py", "x.py"]
    r = _kos("--yalniz-duz-py", d)
    assert r.returncode == 1 and "KIRMIZI" in r.stdout, r.stdout + r.stderr


def test_KARSIT_D3_46_yalniz_init_ve_pyd_TEMIZ(tmp_path):
    d = _dist(
        tmp_path, ["__init__.py", "inference_em_kedi/__init__.py", "inference_em_kedi/model.cpython-310-darwin.so"]
    )
    assert pk.duz_py_var_mi(d, "ai_hub") == []
    assert _kos("--yalniz-duz-py", d).returncode == 0
    assert _kos("--yalniz-duz-py", tmp_path / "yok").returncode == 1  # sevk ağacı yoksa da geçmez


def _adimlar(dosya: str) -> list[dict]:
    w = yaml.safe_load((KOK / ".github" / "workflows" / dosya).read_text(encoding="utf-8"))
    return [a for is_ in (w.get("jobs") or {}).values() for a in (is_.get("steps") or [])]


def test_KRITIK_D3_46_linux_is_akisi_PYINSTALLER_ile_PAKETLEME_arasinda_kapi_BLOKLAR():
    adim = _adimlar("linux-backend.yml")
    run = [str(a.get("run", "")) for a in adim]
    i_py = next(i for i, r in enumerate(run) if "-m PyInstaller" in r)
    i_paket = next(i for i, r in enumerate(run) if "zip -rq ../base-linux.zip" in r)
    kapi = [i for i, r in enumerate(run) if "pyz_koruma_kapisi.py --yalniz-duz-py dist/PEMF_Backend" in r]
    assert len(kapi) == 1 and i_py < kapi[0] < i_paket, (i_py, kapi, i_paket)
    k = adim[kapi[0]]
    assert not k.get("continue-on-error") and "|| true" not in str(k.get("run")), "kapı bloklamıyor (süs)"


def test_KRITIK_D3_46_build_mac_PYINSTALLER_sonrasi_PAKETLEMEDEN_once_die():
    src = (KOK / "build_tools" / "build_mac.sh").read_text(encoding="utf-8")
    i_py = src.find("python -m PyInstaller")
    i_kapi = src.find('pyz_koruma_kapisi.py --yalniz-duz-py "$DIST_DIR/PEMF_Backend"')
    i_zip = src.find('zip -rqy "../$OUT_ZIP"')
    assert -1 < i_py < i_kapi < i_zip, (i_py, i_kapi, i_zip)
    assert "|| die" in src[i_kapi : i_kapi + 200], "kapı kırmızıyken build_mac DURMUYOR"
    mac = [str(a.get("run", "")) for a in _adimlar("mac-backend.yml")]
    assert any("./build_tools/build_mac.sh" in r for r in mac), "mac iş akışı build_mac.sh'i koşmuyor (kapı atlanır)"


def test_KARSIT_D3_46_windows_kipi_DEGISMEDI():
    """Windows yolu (EXE + PYZ + `--duz-py-de-kontrol`) aynen: exe verilmezse ve kip yoksa kullanım hatası."""
    r = _kos()
    assert r.returncode == 2 and "exe ya da --yalniz-duz-py" in r.stderr, r.stdout + r.stderr


@pytest.mark.parametrize("ad", ["linux-backend.yml", "mac-backend.yml"])
def test_D3_46_is_akislari_ayristirilir(ad):
    assert _adimlar(ad), f"{ad} adımsız (ayrıştırma boş — kör kapı)"
