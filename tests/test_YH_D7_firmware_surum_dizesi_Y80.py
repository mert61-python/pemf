# -*- coding: utf-8 -*-
"""YH D7 (Y80) — firmware yayın adayının sürüm dizesi artırıldı ve TEK değerdir; derleme kapısı uyarıyı da ölçer.

ÖLÇÜLEN (YH, 2026-10-22):
  · `main.c` banner'ı 2026-09'dan beri `DDS v2.3` — 120 ve 121 baytlık imajlar AYNI sürümü bastı (tezgâh 2026-10-14; Y80 kök nedeni:
    "hiç artırılmadı"). Yayın adayı `DDS v2.4`. Simülatör (`tools/stm32_simulator.py`, kum havuzu / ekran görüntüleri onu konuşur) ve
    firmware README'si sürümü AYRICA yazıyor → üçü aynı olmalı; v2.3'e geri dönüş (eski, ayırt edilemeyen imajların sürümü) kırmızı.
  · `scripts/firmware_derle.py` başarılı derlemede stderr'e HİÇ bakmıyor, yine de "temiz derlendi (-Wall -Wextra)" diyordu (uyarı
    sayılmadan — sahte yeşil); nesne adları `hash(str(k))`ten (PYTHONHASHSEED'e göre her koşuda başka ad).
Kapı: üç sürüm kaynağı aynı ve > 2.3; derleme betiği uyarıda 1 döner (sahte derleyici, gerçek araç zinciri GEREKMEZ) ve nesne adı sıradan.
Altın ikilinin belirlenimciliği (iki derleme bayt aynı) gerçek araç zinciriyle ÖLÇÜLDÜ — rapor D7 (bu kapı CI'da araç istemez).
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path

from betik_alt_sureci import betik_modulu
from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
MAIN_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
README = KOK / "firmware" / "stm32_pemf" / "README.md"
_SURUM = re.compile(r"DDS v(\d+(?:\.\d+)+)")


def _main_surumu() -> str:
    m = re.search(r'"-> STM_READY: DDS v(\d+(?:\.\d+)+) ', c_soy(MAIN_C.read_text(encoding="utf-8")))
    assert m, "main.c'de (yorum dışı) STM_READY sürüm dizesi yok"
    return m.group(1)


def test_KRITIK_Y80_main_c_simulator_ve_README_AYNI_surum_ve_v2_3_DEGIL():
    sys.path.insert(0, str(KOK))
    import tools.stm32_simulator as sim

    ana = _main_surumu()
    sim_m = _SURUM.search(sim.Stm32SimClient._kimlik_govdesi())
    readme = re.findall(r"Banner[^`\n]*`STM_READY: DDS v(\d+(?:\.\d+)+)", README.read_text(encoding="utf-8"))
    assert sim_m and sim_m.group(1) == ana, (
        f"simülatör {sim_m and sim_m.group(1)} ≠ main.c {ana} (kum havuzu ESKİ firmware'i konuşur)"
    )
    assert readme == [ana], f"README banner sürümü {readme} ≠ main.c {ana}"
    assert tuple(int(x) for x in ana.split(".")) > (2, 3), (
        f"main.c sürümü {ana}: Y80 — `DDS v2.3` 120 ve 121 baytlık imajların ORTAK (ayırt edilemeyen) sürümüdür; yayın adayı artırılır"
    )


def _sahte_derle(tmp_path, monkeypatch, stderr: str):
    fd = betik_modulu("firmware_derle")
    proje = tmp_path / "stm32_pemf"
    (proje / "Core" / "Src").mkdir(parents=True)
    (proje / "Core" / "Src" / "x.c").write_text("int x;\n", encoding="utf-8")
    (proje / "Core" / "Startup").mkdir(parents=True)
    (proje / "Core" / "Startup" / "startup_stm32f429zitx.s").write_text("\n", encoding="utf-8")
    (proje / "STM32F429ZITX_FLASH.ld").write_text("\n", encoding="utf-8")
    cagrilar: list[list[str]] = []

    def run(argv, **_k):
        argv = [str(a) for a in argv]
        cagrilar.append(argv)
        return fd.subprocess.CompletedProcess(argv, 0, "", stderr if "-c" in argv and argv[-3].endswith(".c") else "")

    monkeypatch.setattr(
        fd, "subprocess", types.SimpleNamespace(run=run, CompletedProcess=fd.subprocess.CompletedProcess)
    )
    monkeypatch.setattr(fd, "STM_PROJE", proje)
    monkeypatch.setattr(fd, "_stm_gcc", lambda: tmp_path / "sahte" / "arm-none-eabi-gcc.exe")
    monkeypatch.setattr(fd, "shutil", types.SimpleNamespace(which=lambda _ad: None))
    monkeypatch.setattr(fd, "printf_float_kapisi", lambda elf, nm: 0)
    return fd, cagrilar


def test_KRITIK_derleme_UYARISI_varken_TEMIZ_DEMEZ(tmp_path, monkeypatch, capsys):
    fd, _c = _sahte_derle(tmp_path, monkeypatch, "x.c:1:5: warning: unused variable 'y' [-Wunused-variable]\n")
    assert fd.derle_stm(zorunlu=True) == 1, "uyarılı derleme 0 döndü — '-Wall -Wextra temiz' ölçülmeden söyleniyor"
    cikti = capsys.readouterr().out
    assert "UYARISI" in cikti and "unused variable" in cikti, cikti[-500:]


def test_KARSIT_uyarisiz_derleme_gecer_ve_nesne_adi_SIRADAN(tmp_path, monkeypatch):
    fd, cagrilar = _sahte_derle(tmp_path, monkeypatch, "")
    assert fd.derle_stm(zorunlu=True) == 0
    nesne = [a[a.index("-o") + 1] for a in cagrilar if "-c" in a and a[-3].endswith(".c")]
    assert [Path(n).name for n in nesne] == ["000_x.o"], f"nesne adı sıradan değil (PYTHONHASHSEED'e bağlı?): {nesne}"
