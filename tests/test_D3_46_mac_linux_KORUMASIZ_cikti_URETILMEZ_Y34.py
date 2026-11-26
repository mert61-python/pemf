# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3.46 (B-10.200 · Y34, sahip) — Mac / Linux backend çıktısı korumasızsa ÜRETİLMEZ: kod koruması kapısı paketlemeden ÖNCE.

ÖLÇÜLEN (HEAD): Linux / macOS hedefleri aynı spec'i koşar ama compile_pyd'yi HİÇ koşmaz → `_internal/ai_hub` diskte DÜZ .py (koruma sıfır;
`pyz_koruma_kapisi.py` başlığında "bilinen" olarak kayıtlı). `linux-backend.yml` ve `build_mac.sh`ta bunu ölçen adım YOK — artefakt
sessizce üretiliyordu. Y34: korumasız çıktı ÜRETİLMEZ (kapı kırmızı); Cython zinciri gelene kadar Mac / Linux "Yakında".
Kapı: ortak sayaç `duz_py_var_mi(dist)` + `--yalniz-duz-py` kipi (PYZ okuyucu gerekmez) sahte dist ile; iş akışı YAML ayrıştırılarak ve
build_mac.sh sırasıyla doğrulanır. ⚠️ Bilinçli sonuç: bugünkü spec'le Mac / Linux CI artefaktı KIRMIZI olur (A-43: itilmedi).
YS1b · Y320 (sahip 25-11): CI yalnız Windows ürün hattı — `linux-backend.yml` + `mac-backend.yml` KALDIRILDI (git geçmişinde). Kapı artık
HİÇBİR iş akışının Mac / Linux backend paketi üretmediğini kilitler; biri geri gelirse PyInstaller → bu kapı → zip sırasıyla gelmeli.
"""

from __future__ import annotations

import re
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


IS_AKISLARI = KOK / ".github" / "workflows"


def _adimlar(dosya: str) -> list[dict]:
    w = yaml.safe_load((IS_AKISLARI / dosya).read_text(encoding="utf-8"))
    return [a for is_ in (w.get("jobs") or {}).values() for a in (is_.get("steps") or [])]


def test_KRITIK_D3_46_Y320_hicbir_is_akisi_MAC_LINUX_backend_paketi_URETMEZ():
    """Y320: Linux / macOS backend paketleme CI'dan KALKTI → korumasız Mac / Linux çıktısı CI'da hiç üretilmez. MUTASYON: bir iş
    akışına `base-linux.zip` / `base-mac.zip` paketlemesi ya da `build_mac.sh` adımı eklemek → KIRMIZI (geri gelen yol D3.46 kapısıyla
    — PyInstaller → `pyz_koruma_kapisi.py --yalniz-duz-py` → zip — ve bu testin güncellenmesiyle gelmeli)."""
    akislar = sorted(IS_AKISLARI.glob("*.yml"))
    assert len(akislar) >= 5, f"iş akışı listesi boş / eksik okunuyor (kör kapı): {[p.name for p in akislar]}"
    for ad in ("linux-backend.yml", "mac-backend.yml"):
        assert not (IS_AKISLARI / ad).exists(), f"{ad} geri gelmiş (Y320)"
    paketleyen = [
        f"{p.name}: {str(a.get('run', ''))[:80]!r}"
        for p in akislar
        for a in _adimlar(p.name)
        if re.search(r"base-(linux|mac)(-\w+)?\.zip|build_mac\.sh", str(a.get("run", "")))
    ]
    assert not paketleyen, f"Mac / Linux backend paketleyen CI adımı var (Y320 + D3.46): {paketleyen}"


def test_KRITIK_D3_46_build_mac_PYINSTALLER_sonrasi_PAKETLEMEDEN_once_die():
    src = (KOK / "build_tools" / "build_mac.sh").read_text(encoding="utf-8")
    i_py = src.find("python -m PyInstaller")
    i_kapi = src.find('pyz_koruma_kapisi.py --yalniz-duz-py "$DIST_DIR/PEMF_Backend"')
    i_zip = src.find('zip -rqy "../$OUT_ZIP"')
    assert -1 < i_py < i_kapi < i_zip, (i_py, i_kapi, i_zip)
    assert "|| die" in src[i_kapi : i_kapi + 200], "kapı kırmızıyken build_mac DURMUYOR"


def test_KARSIT_D3_46_windows_kipi_DEGISMEDI():
    """Windows yolu (EXE + PYZ + `--duz-py-de-kontrol`) aynen: exe verilmezse ve kip yoksa kullanım hatası."""
    r = _kos()
    assert r.returncode == 2 and "exe ya da --yalniz-duz-py" in r.stderr, r.stdout + r.stderr


@pytest.mark.parametrize("ad", ["tests.yml", "launcher.yml"])
def test_D3_46_is_akislari_ayristirilir(ad):
    assert _adimlar(ad), f"{ad} adımsız (ayrıştırma boş — Y320 taraması kör kalır)"
