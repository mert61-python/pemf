# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.06 (B-8.14 · A-47 madde 5) — NTC ↔ ACS712 `#error` korkuluğu GERÇEK önişlemde çalışır.

ARIZA (ölçüldü, HEAD 5bc99be1): `PEMF_NTC_TERMAL_ENABLED` YALNIZ `main.c`'de tanımlıydı; `pemf_akim.c`'deki çakışma kapısı
(`#if defined(PEMF_NTC_TERMAL_ENABLED) && … #error`) başka bir çeviri birimindeydi ve makroyu HİÇ görmüyordu → bayrak `main.c`'de 1
yapılsa da (NTC bloğu ADC1'i kurar + ACS712 aynı beş kanalı okur → iki okuyucu, akım ve sıcaklık ikisi de yanlış) derleme TEMİZ bitiyordu.
Tek kapı (`test_stm_akim_firmware.py::…NTC_ile_ADC_CAKISMASI…`) yalnız `"#error" in kod` METNİNE bakıyordu.

ÖLÇÜM (davranışsal, derleyici ÖNİŞLEMCİSİ): `Core/Inc` + `main.c` + `pemf_akim.c` geçici bir ağaca kopyalanır (sürücü başlıkları
depodan, SALT OKUNUR). Bayrağın TEK tanım yeri kopyada bulunur ve 1 yapılır → `pemf_akim.c` önişlemi `#error` ile DÜŞMELİ; varsayılanda
iki çeviri birimi de makroyu (0) GÖRMELİ (`-E -dM`). Derleyici: `arm-none-eabi-gcc`, yoksa `gcc`/`cc`/`clang` (CI). Karta yakma YOK.
A-47: termal KESME EKLENMEZ — bu yalnız derleme korkuluğudur; belge kısmı Dalga 6.
MUTASYON: tanımı yeniden yalnız `main.c`'ye almak → KIRMIZI.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
STM = KOK / "firmware" / "stm32_pemf"
_TANIM = re.compile(r"^[ \t]*#define[ \t]+PEMF_NTC_TERMAL_ENABLED[ \t]+0\b", re.M)


def _derleyici() -> str:
    for ad in ("arm-none-eabi-gcc", "gcc", "cc", "clang"):
        yol = shutil.which(ad)
        if yol:
            return yol
    if capraz.ZORUNLU:
        pytest.fail("zorunlu kip ama C derleyicisi (arm-none-eabi-gcc / gcc / clang) yok — korkuluk ÖLÇÜLEMEDİ")
    pytest.skip("C derleyicisi yok")


def _agac(tmp: Path, bayrak_bir: bool) -> Path:
    kok = tmp / "stm"
    shutil.copytree(STM / "Core" / "Inc", kok / "Core" / "Inc")
    (kok / "Core" / "Src").mkdir(parents=True)
    for ad in ("main.c", "pemf_akim.c"):
        shutil.copyfile(STM / "Core" / "Src" / ad, kok / "Core" / "Src" / ad)
    if bayrak_bir:
        yerler = [
            p
            for p in (kok / "Core").rglob("*")
            if p.suffix in (".c", ".h") and _TANIM.search(p.read_text("utf-8", "replace"))
        ]
        assert len(yerler) == 1, (
            f"PEMF_NTC_TERMAL_ENABLED varsayılan tanımı TEK yerde olmalı, bulunan: {[p.name for p in yerler]}"
        )
        p = yerler[0]
        p.write_text(_TANIM.sub("#define PEMF_NTC_TERMAL_ENABLED 1", p.read_text("utf-8")), encoding="utf-8")
    return kok


def _onisle(cc: str, kok: Path, kaynak: str, *ek: str) -> subprocess.CompletedProcess:
    arg = [
        cc,
        "-E",
        *ek,
        "-DSTM32F429xx",
        "-DUSE_HAL_DRIVER",
        "-I",
        str(kok / "Core" / "Inc"),
        "-I",
        str(STM / "Drivers" / "STM32F4xx_HAL_Driver" / "Inc"),
        "-I",
        str(STM / "Drivers" / "CMSIS" / "Device" / "ST" / "STM32F4xx" / "Include"),
        "-I",
        str(STM / "Drivers" / "CMSIS" / "Include"),
        str(kok / "Core" / "Src" / kaynak),
    ]
    return subprocess.run(arg, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


def _makro(cikti: str) -> str | None:
    m = re.search(r"^#define PEMF_NTC_TERMAL_ENABLED (\S+)", cikti, re.M)
    return m.group(1) if m else None


def test_KRITIK_iki_ceviri_birimi_de_bayragi_GORUR_varsayilan_0(tmp_path):
    cc = _derleyici()
    kok = _agac(tmp_path, bayrak_bir=False)
    for kaynak in ("main.c", "pemf_akim.c"):
        r = _onisle(cc, kok, kaynak, "-dM")
        assert r.returncode == 0, f"{kaynak} önişlenemedi: {r.stderr[-800:]}"
        assert _makro(r.stdout) == "0", (
            f"{kaynak} PEMF_NTC_TERMAL_ENABLED'ı {_makro(r.stdout)!r} görüyor (beklenen '0') — tanım iki çeviri biriminin ORTAK "
            "başlığında değil; pemf_akim.c'nin NTC↔ACS712 korkuluğu ölü (D5.06)"
        )


def test_KRITIK_bayrak_KAYNAKTA_1_yapilinca_pemf_akim_ONISLEMDE_DURUR(tmp_path):
    cc = _derleyici()
    kok = _agac(tmp_path, bayrak_bir=True)
    m = _onisle(cc, kok, "main.c", "-dM")
    assert m.returncode == 0 and _makro(m.stdout) == "1", f"aparat: bayrak 1 main.c'ye ulaşmadı ({_makro(m.stdout)!r})"
    r = _onisle(cc, kok, "pemf_akim.c")
    assert r.returncode != 0 and "#error" in r.stderr and "ADC1" in r.stderr, (
        "NTC bayrağı 1 iken pemf_akim.c önişlemi TEMİZ bitti — NTC ve ACS712 aynı ADC1 kanallarını okur, derleme DURMALIYDI (D5.06):\n"
        + r.stderr[-600:]
    )


def test_KARSIT_global_D_ile_de_korkuluk_CALISIR(tmp_path):
    cc = _derleyici()
    kok = _agac(tmp_path, bayrak_bir=False)
    r = _onisle(cc, kok, "pemf_akim.c", "-DPEMF_NTC_TERMAL_ENABLED=1")
    assert r.returncode != 0 and "#error" in r.stderr, f"global -D ile korkuluk çalışmadı:\n{r.stderr[-400:]}"
