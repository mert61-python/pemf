# -*- coding: utf-8 -*-
"""CT1 g (istem 66 · Y326): kart yazılımı kapsamı — `scripts/firmware_kapsam.py` (gcov JSON → gerçek kaynak → lcov) + koşum takımının
`PEMF_FW_KAPSAM=1` gcc kolu. Derleyici GEREKMEZ (gcov çıktısı sahte): kopya adı gerçek kaynağa eşlenir, CubeMX başlatma işlevleri DIŞARIDA,
eşlenmeyen dosya (koşum takımı / HAL) ölçülmez, birden çok derleme toplanır, .gcda yoksa kör → 2."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("firmware_kapsam_ct1g", KOK / "scripts" / "firmware_kapsam.py")
fk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fk)


def _belge(dosya: str, satirlar: dict[int, int], islevler=()) -> dict:
    return {
        "files": [
            {
                "file": dosya,
                "functions": [{"name": n, "demangled_name": n, "start_line": a, "end_line": b} for n, a, b in islevler],
                "lines": [{"line_number": k, "count": v} for k, v in satirlar.items()],
            }
        ]
    }


def test_KRITIK_kopya_GERCEK_kaynaga_eslenir_CubeMX_islevleri_DISARIDA_sayimlar_TOPLANIR():
    b1 = _belge(
        "main_host.c", {10: 0, 11: 3, 20: 0, 21: 0, 30: 1}, islevler=[("MX_GPIO_Init", 19, 22), ("pemf_estop", 9, 12)]
    )
    b2 = _belge("C:/tmp/x/main_host.c", {10: 2})
    b3 = _belge("isr_kosum.c", {1: 0})  # koşum takımının kendisi ölçülmez
    sonuc = fk.birlestir([b1, b2, b3])
    assert set(sonuc) == {"firmware/stm32_pemf/Core/Src/main.c"}
    assert sonuc["firmware/stm32_pemf/Core/Src/main.c"] == {10: 2, 11: 3, 30: 1}, "MX_*_Init satırları ölçüme girdi"
    assert fk.yuzde(sonuc) == 100.0
    assert fk.yuzde({}) == 0.0


@pytest.mark.parametrize(
    "ad", ["SystemClock_Config", "MX_TIM1_Init", "HAL_TIM_MspPostInit", "HAL_MspInit", "Error_Handler"]
)
def test_disarida_islev_deseni(ad):
    assert fk.DISARIDA_ISLEV.match(ad)


def test_KARSIT_guvenlik_islevleri_DISARIDA_DEGIL():
    for ad in (
        "pemf_estop_uygula",
        "komut_isle",
        "TIM1_UP_TIM10_IRQHandler",
        "watchdog_besle",
        "HAL_TIM_PeriodElapsedCallback",
    ):
        assert not fk.DISARIDA_ISLEV.match(ad), ad


def test_lcov_yazilir_ve_fark_kapisi_okur(tmp_path):
    olcum = {"firmware/stm32_pemf/Core/Src/main.c": {5: 1, 6: 0}}
    yol = tmp_path / "fw.info"
    fk.lcov_yaz(olcum, yol)
    t = yol.read_text(encoding="utf-8")
    assert "SF:firmware/stm32_pemf/Core/Src/main.c\nDA:5,1\nDA:6,0\nLF:2\nLH:1\nend_of_record" in t


def test_KRITIK_main_gcda_yoksa_KOR_cikis_2_gcov_dususu_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fk, "_konsol_utf8", lambda: None)  # pytest yakalama akışı yeniden yapılandırılmasın
    assert fk.main(["--kok", str(tmp_path)]) == 2
    assert "kör" in capsys.readouterr().out
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.gcda").write_bytes(b"x")

    def _dusen(*a, **k):
        return subprocess.CompletedProcess(a, 1, "", "bozuk gcda")

    monkeypatch.setattr(fk.subprocess, "run", _dusen)
    assert fk.main(["--kok", str(tmp_path)]) == 2
    assert "gcov düştü" in capsys.readouterr().out


def test_main_gcov_ciktisini_okur_lcov_yazar(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fk, "_konsol_utf8", lambda: None)  # pytest yakalama akışı yeniden yapılandırılmasın
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "isr.gcda").write_bytes(b"x")
    cikti = json.dumps(_belge("main_host.c", {1: 1, 2: 0}))
    cagri = []

    def _gcov(arg, **k):
        cagri.append((arg, k.get("cwd")))
        return subprocess.CompletedProcess(arg, 0, "gcov notu\n" + cikti + "\n", "")

    monkeypatch.setattr(fk.subprocess, "run", _gcov)
    assert fk.main(["--kok", str(tmp_path), "--gcov", "gcov-x", "--lcov", str(tmp_path / "fw.info")]) == 0
    assert cagri[0][0] == ["gcov-x", "--json-format", "--stdout", "isr.gcda"] and Path(cagri[0][1]) == tmp_path / "d"
    assert "%50.00" in capsys.readouterr().out and (tmp_path / "fw.info").is_file()


def test_KRITIK_kosum_takimi_gcc_kolu_PEMF_FW_KAPSAM_ile_coverage_bayragi():
    t = (KOK / "tests" / "firmware_host_aparat.py").read_text(encoding="utf-8")
    assert 'kapsam = ["--coverage"] if os.environ.get("PEMF_FW_KAPSAM") == "1" else []' in t
    # biçimden bağımsız (ruff satırı bölebilir): gcc komut listesinde `*kapsam` açılımı var
    assert re.search(r'"-w",\s*\*kapsam,', t), "gcc komutuna kapsam bayrağı eklenmiyor"


def test_konsol_utf8_reconfigure_olan_akisi_cevirir():
    class _A:
        ayar = None

        def reconfigure(self, **k):
            self.ayar = k

    a = _A()
    fk._konsol_utf8([a, object()])
    assert a.ayar == {"encoding": "utf-8", "errors": "replace"}
