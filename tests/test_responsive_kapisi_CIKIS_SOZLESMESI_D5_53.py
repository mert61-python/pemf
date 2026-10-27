# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.53 (B-10.96 · B-10.165 · B-10.166) — responsive kapısının ÇIKIŞ KODU SÖZLEŞMESİ davranışla ölçülür.

Sözleşme (`scripts/responsive_kapisi.py` başlığı): 0 temiz · 1 YENİ bulgu · 2 kullanım/altyapı hatası · 3 ORTAM YOK (tarayıcı ya da
derleme çıktısı yok; `--zorunlu` ile 2'ye döner). `.github/workflows/site.yml` adımı bunu `… || KOD=$?` ile yakalar: yalnız 3 ATLANIR
(uyarı + 0), diğer her kod adımı KIRMIZI yapar.

ARIZA (kör kapı, ölçüldü): sözleşmeyi koruyan tek test (`test_tarayici_secimi_ACIK_beyan.py`) METİN arıyordu: `|| KOD=$?` → `|| true`
yapılınca (betik ne döndürürse dönsün adım YEŞİL) ve betikte `return 2 if a.zorunlu else 3` → `return 3` yapılınca kapı yeşil kalıyordu.

ÖLÇÜM:
  (a) site.yml'deki adımın `run:` betiği YAML'dan GERÇEK metniyle alınır; `python3` çağrısı kabuk işleviyle sahtelenir (çıkış 0/1/2/3)
      ve GitHub'ın varsayılan kabuğu gibi `bash -e -o pipefail` altında koşulur → 0→0, 1→1, 2→2, 3→0 (atla).
  (b) GERÇEK `main()`: `tarayici_bul` None döndürürken `--zorunlu` → 2, zorunsuz → 3. Tarayıcı BAŞLATILAMAZ: `tarayici_baslat` ve
      modülün `subprocess.Popen`'ı reddeden sahtelerle değişir (gerçek Edge/Chrome bu makinede olsa bile açılmaz).
  (c) launcher / pf hedeflerinin CI işine bağlanması ENGELLİ (A-40 / A-43: itme yok) — bu dosyada YOK.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
WF = KOK / ".github" / "workflows" / "site.yml"
BETIK = KOK / "scripts" / "responsive_kapisi.py"
ADIM = "Gorunum alani + dokunma hedefi kapisi"


def _git_bash() -> str | None:
    """GitHub ubuntu kabuğu yerine Git'in bash'i (Windows'ta System32\\bash.exe WSL başlatıcısıdır — KULLANILMAZ)."""
    if os.name != "nt":
        return shutil.which("bash")
    git = shutil.which("git")
    if not git:
        return None
    for kok in Path(git).resolve().parents[:3]:  # Git\cmd\git.exe · Git\mingw64\bin\git.exe
        for aday in (kok / "bin" / "bash.exe", kok / "usr" / "bin" / "bash.exe"):
            if aday.is_file():
                return str(aday)
    return None


def _adim_betigi() -> str:
    import yaml

    wf = yaml.safe_load(WF.read_text(encoding="utf-8"))
    for is_ in wf["jobs"].values():
        for adim in is_.get("steps", []):
            if adim.get("name") == ADIM:
                return adim["run"]
    raise AssertionError(f"site.yml'de '{ADIM}' adımı yok — kapı bayat")


@pytest.mark.parametrize("betik_kodu,beklenen", [(0, 0), (1, 1), (2, 2), (3, 0)])
def test_KRITIK_site_yml_adimi_cikis_kodunu_YUTMAZ_yalniz_3_ATLAR(tmp_path, betik_kodu, beklenen):
    bash = _git_bash()
    if not bash:
        import capraz

        if capraz.ZORUNLU:  # atlayan kapı zorunlu kipte DÜŞER
            pytest.fail("zorunlu kip ama bash bulunamadı — site.yml adım sözleşmesi ÖLÇÜLEMEDİ")
        pytest.skip("bash yok")
    run = _adim_betigi()
    assert "scripts/responsive_kapisi.py" in run, "adım responsive_kapisi.py'yi çağırmıyor — kapı bayat"
    betik = tmp_path / "adim.sh"
    betik.write_text(f"python3() {{ return {betik_kodu}; }}\n" + run, encoding="utf-8", newline="\n")
    r = subprocess.run([bash, "-e", "-o", "pipefail", str(betik)], capture_output=True, text=True, timeout=60)
    assert r.returncode == beklenen, (
        f"responsive_kapisi {betik_kodu} döndürünce site.yml adımı {r.returncode} ile bitti (beklenen {beklenen}): "
        "sözleşme 1/2 → KIRMIZI, yalnız 3 → atla (D5.53). Çıktı: " + (r.stdout + r.stderr)[-400:]
    )


def _modul(monkeypatch):
    spec = importlib.util.spec_from_file_location("responsive_kapisi_d553", BETIK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    def _yasak(*a, **k):
        raise AssertionError("TARAYICI BAŞLATILMAYA ÇALIŞILDI — kapı tarayıcısız kolu ölçmeli (D5.53)")

    monkeypatch.setattr(m, "tarayici_bul", lambda istenen: None)
    monkeypatch.setattr(m, "tarayici_baslat", _yasak)
    monkeypatch.setattr(m.subprocess, "Popen", _yasak)
    return m


@pytest.mark.parametrize("zorunlu,beklenen", [(True, 2), (False, 3)])
def test_KRITIK_tarayici_YOKSA_zorunlu_2_zorunsuz_3(tmp_path, monkeypatch, zorunlu, beklenen):
    m = _modul(monkeypatch)
    arg = ["--hedef", "site", "--cikti", str(tmp_path / "cikti"), "--site-dist", str(tmp_path / "dist")]
    kod = m.main(arg + (["--zorunlu"] if zorunlu else []))
    assert kod == beklenen, (
        f"tarayıcı yokken main({'--zorunlu' if zorunlu else 'zorunsuz'}) {kod} döndürdü, beklenen {beklenen} "
        "(--zorunlu: CI'da ortam yok = KIRMIZI; zorunsuz: ORTAM YOK = atla) (D5.53)"
    )
