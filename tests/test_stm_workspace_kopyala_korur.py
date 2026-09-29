# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.16 (B-10.211) KAPISI — `stm_workspace_kopyala` aynı gün yeniden koşunca hedefteki workspace'i SİLMEZ.

ARIZA (DENETIM-10 B-10.211): hedef tarihli klasör varsa `shutil.rmtree(hedef)` onaysız ve yedeksiz
siliyordu → sahibin o gün CubeIDE'de yaptığı `main.c` düzenlemesi ve `.metadata` GERİ DÖNÜŞSÜZ gider.

KAPI: tmp hedef kökünde bugünkü tarihli klasöre betiğin ÜRETMEDİĞİ `sahip_notu.txt` ve elle
düzenlenmiş bir `main.c` konur; betiğin GERÇEK `main()`i aynı `--hedef` ile çağrılır (depodaki
`firmware/stm32_pemf` tmp'ye kopyalanır — gerçek hedef/masaüstü KULLANILMAZ). İddia: iki dosya da
SİLİNMEMİŞ — yerinde (betik durdu, ≠0) ya da bir yedek klasörde. Seçilen tasarım (yedeğe taşı, taze
kopya üret) ve taşıma başarısız olursa silmeye DÜŞMEME ayrıca pinlenir. Karşıt-kanıt: temiz kökte
betik kopyayı gerçekten üretir (kapı betiği işlemez hâle getirerek yeşil olamaz).
MUTASYON: koruma dalını kaldırıp koşulsuz `shutil.rmtree(hedef)`e dönmek → KIRMIZI.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
NOT_METNI = "sahibin elle yazdigi not"
DUZENLEME = "/* sahibin CubeIDE duzenlemesi */"


def _betik():
    spec = importlib.util.spec_from_file_location(
        "stm_workspace_kopyala_kapi", KOK / "scripts" / "stm_workspace_kopyala.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def betik():
    if not (KOK / "firmware" / "stm32_pemf").is_dir():
        pytest.skip("firmware/stm32_pemf yok")
    return _betik()


def _hedef(kok: Path) -> Path:
    return kok / f"PEMF_STM32_workspace_{_dt.date.today().isoformat()}"


def _sahip_calismasi(kok: Path) -> Path:
    """Bugünkü hedefte betiğin ÜRETMEDİĞİ iki dosya: bir not ve CubeIDE'de düzenlenmiş main.c."""
    hedef = _hedef(kok)
    (hedef / "stm32_pemf" / "Core" / "Src").mkdir(parents=True)
    (hedef / "sahip_notu.txt").write_text(NOT_METNI, encoding="utf-8")
    (hedef / "stm32_pemf" / "Core" / "Src" / "main.c").write_text(DUZENLEME, encoding="utf-8")
    return hedef


def _kos(betik, kok: Path, monkeypatch) -> int:
    monkeypatch.setattr(sys, "argv", ["stm_workspace_kopyala.py", "--hedef", str(kok)])
    return betik.main()


def _notlar(kok: Path) -> list[Path]:
    return [p for p in kok.rglob("sahip_notu.txt") if p.read_text(encoding="utf-8") == NOT_METNI]


def _duzenlemeler(kok: Path) -> list[Path]:
    return [p for p in kok.rglob("main.c") if p.read_text(encoding="utf-8", errors="replace") == DUZENLEME]


def test_KRITIK_ayni_gun_yeniden_kosum_SAHIBIN_dosyalarini_SILMEZ(betik, tmp_path, monkeypatch):
    _sahip_calismasi(tmp_path)
    rc = _kos(betik, tmp_path, monkeypatch)
    assert _notlar(tmp_path), f"betik hedefteki SAHİBİN dosyasını SİLDİ (rc={rc}) — onaysız ve yedeksiz (B-10.211)"
    assert _duzenlemeler(tmp_path), f"sahibin main.c düzenlemesi KAYBOLDU (rc={rc}) (B-10.211)"


def test_onceki_kopya_YEDEGE_tasinir_ve_TAZE_kopya_uretilir(betik, tmp_path, monkeypatch, capsys):
    hedef = _sahip_calismasi(tmp_path)
    assert _kos(betik, tmp_path, monkeypatch) == 0
    yedekler = sorted(p for p in tmp_path.iterdir() if p.name.startswith(f"{hedef.name}_yedek_"))
    assert len(yedekler) == 1, f"önceki kopya tek bir yedek klasöre taşınmadı: {[p.name for p in tmp_path.iterdir()]}"
    assert (yedekler[0] / "sahip_notu.txt").read_text(encoding="utf-8") == NOT_METNI
    assert (yedekler[0] / "stm32_pemf" / "Core" / "Src" / "main.c").read_text(encoding="utf-8") == DUZENLEME
    taze = (hedef / "stm32_pemf" / "Core" / "Src" / "main.c").read_text(encoding="utf-8", errors="replace")
    assert "NUM_COILS" in taze and taze != DUZENLEME, "taze kopya depo kaynağından üretilmedi"
    assert not (hedef / "sahip_notu.txt").exists(), "taze kopyaya betiğin üretmediği dosya karıştı"
    assert str(yedekler[0]) in capsys.readouterr().out, "yedeğin yeri kullanıcıya söylenmedi"


def test_KRITIK_tasima_basarisizsa_HICBIR_SEY_SILINMEZ_ve_durur(betik, tmp_path, monkeypatch):
    """CubeIDE klasörü açık tutarken (Windows `PermissionError`) betik silmeye DÜŞMEMELİ."""
    hedef = _sahip_calismasi(tmp_path)
    silinen: list[str] = []
    gercek_rmtree = shutil.rmtree

    def _rmtree_kaydi(yol, *a, **k):
        silinen.append(str(yol))
        return gercek_rmtree(yol, *a, **k)

    def _tasinamaz(self, *a, **k):
        raise PermissionError(13, "d0o16: klasor baska bir surecte acik", str(self))

    monkeypatch.setattr(shutil, "rmtree", _rmtree_kaydi)
    monkeypatch.setattr(Path, "rename", _tasinamaz)
    monkeypatch.setattr(Path, "replace", _tasinamaz)
    rc = _kos(betik, tmp_path, monkeypatch)
    assert rc != 0, "hedef yedeğe taşınamadığı hâlde betik devam etti (0 döndü)"
    assert not silinen, f"taşıma başarısız olunca betik SİLMEYE düştü: {silinen}"
    assert (hedef / "sahip_notu.txt").read_text(encoding="utf-8") == NOT_METNI
    assert (hedef / "stm32_pemf" / "Core" / "Src" / "main.c").read_text(encoding="utf-8") == DUZENLEME


def test_KARSIT_KANIT_temiz_kokte_kopya_URETILIR(betik, tmp_path, monkeypatch):
    assert _kos(betik, tmp_path, monkeypatch) == 0
    main_c = _hedef(tmp_path) / "stm32_pemf" / "Core" / "Src" / "main.c"
    assert main_c.is_file() and "NUM_COILS" in main_c.read_text(encoding="utf-8", errors="replace")
    assert not [p for p in tmp_path.iterdir() if "_yedek_" in p.name], "temiz kökte yedek klasörü açılmamalı"
