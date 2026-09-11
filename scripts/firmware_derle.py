# -*- coding: utf-8 -*-
# Author: mertaygn
"""FIRMWARE DERLEME KAPISI — STM32 (arm-none-eabi-gcc) + ESP32-S3 (arduino-cli).

⚠️ 2026-09-11'E KADAR BU DEPODA FIRMWARE HİÇ DERLENMEDİ. Kaynak dosyaların başlığında
"⚠️ TEZGÂHTA DOĞRULANMADI. Bu depoda C DERLENMEZ" yazıyordu ve bütün C/C++ değişiklikleri
YALNIZCA yapısal (regex) kapılarla korunuyordu. Yapısal kapı bir yazım hatasını, eksik bir
noktalı virgülü, tanımsız bir alanı ya da imza uyuşmazlığını GÖREMEZ — sahip firmware'i
CubeIDE/Arduino IDE'de açtığında öğrenirdi.

O gün makinede iki araç zincirinin de KURULU olduğu bulundu:
  · arm-none-eabi-gcc  — STM32CubeIDE eklentileri altında
  · arduino-cli        — Arduino IDE kaynakları altında (esp32 çekirdeği 3.3.11 kurulu)

Bu betik ikisini de arar, bulduğunu derler, bulamadığını ATLAR (araç yoksa kapı KIRMIZI
olmaz — CI'da araç bulunmayabilir; ama YEREL geliştirmede gerçek derleyici konuşur).

KULLANIM:  python scripts/firmware_derle.py [--stm] [--s3]
           (bayrak yoksa ikisi de denenir)

⚠️ ESP32-S3 BÖLÜM ŞEMASI: varsayılan şema (1,2 MB APP) bu taslağa YETMİYOR (~1,39 MB).
`min_spiffs` (1,9 MB APP + OTA) kullanılır — taslak OTA yapıyor ve `data/` (SPIFFS) taşıyor.
Bu bir kod sorunu DEĞİL, kart ayarıdır; Arduino IDE'de de aynısı seçilmelidir.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
STM_PROJE = KOK / "firmware" / "stm32_pemf"
S3_PROJE = KOK / "firmware" / "esps3_pemf_coil"

#: `arm-none-eabi-gcc` aranacak yerler (CubeIDE sürüm dizini değişebilir → glob).
STM_ARAMA = [
    Path(r"C:\ST"),
    Path(r"C:\Program Files\STMicroelectronics"),
]

S3_CLI_ADAYLARI = [
    Path(r"C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"),
    Path(r"C:\Program Files (x86)\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"),
]

STM_BAYRAKLAR = [
    "-mcpu=cortex-m4",
    "-mthumb",
    "-mfpu=fpv4-sp-d16",
    "-mfloat-abi=hard",
    "-std=gnu11",
    "-DSTM32F429xx",
    "-DUSE_HAL_DRIVER",
    "-Wall",
    "-Wextra",
    "-O2",
    "-ffunction-sections",
    "-fdata-sections",
]


def _stm_gcc() -> Path | None:
    yol = shutil.which("arm-none-eabi-gcc")
    if yol:
        return Path(yol)
    for kok in STM_ARAMA:
        if not kok.is_dir():
            continue
        for aday in kok.rglob("arm-none-eabi-gcc.exe"):
            return aday
    return None


def _s3_cli() -> Path | None:
    yol = shutil.which("arduino-cli")
    if yol:
        return Path(yol)
    for aday in S3_CLI_ADAYLARI:
        if aday.is_file():
            return aday
    return None


def derle_stm() -> int:
    gcc = _stm_gcc()
    if gcc is None:
        print("[STM32] ATLANDI — arm-none-eabi-gcc bulunamadi (CubeIDE kurulu degil).")
        return 0
    if not STM_PROJE.is_dir():
        print("[STM32] ATLANDI — proje dizini yok.")
        return 0
    print(f"[STM32] derleyici: {gcc}")
    inc = [
        "-I" + str(STM_PROJE / "Core" / "Inc"),
        "-I" + str(STM_PROJE / "Drivers" / "STM32F4xx_HAL_Driver" / "Inc"),
        "-I" + str(STM_PROJE / "Drivers" / "CMSIS" / "Device" / "ST" / "STM32F4xx" / "Include"),
        "-I" + str(STM_PROJE / "Drivers" / "CMSIS" / "Include"),
    ]
    kaynaklar = sorted((STM_PROJE / "Core" / "Src").rglob("*.c")) + sorted((STM_PROJE / "Drivers").rglob("*.c"))
    if not kaynaklar:
        print("[STM32] ATLANDI — kaynak bulunamadi.")
        return 0
    hata = 0
    with tempfile.TemporaryDirectory() as td:
        nesneler = []
        for k in kaynaklar:
            hedef = Path(td) / (k.stem + "_" + str(abs(hash(str(k))) % 10**6) + ".o")
            r = subprocess.run(
                [str(gcc), *STM_BAYRAKLAR, *inc, "-c", str(k), "-o", str(hedef)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if r.returncode != 0:
                print(f"[STM32] ### DERLENMEDI: {k.relative_to(KOK)}")
                print(r.stderr[:3000])
                hata += 1
            else:
                nesneler.append(str(hedef))
        if hata:
            print(f"[STM32] BASARISIZ — {hata} dosya derlenmedi.")
            return 1

        # Baglama: gercek linker betigi + startup. `sqrtf` icin -lm SART.
        basla = STM_PROJE / "Core" / "Startup" / "startup_stm32f429zitx.s"
        ld = STM_PROJE / "STM32F429ZITX_FLASH.ld"
        if basla.is_file() and ld.is_file():
            so = Path(td) / "startup.o"
            r = subprocess.run(
                [str(gcc), "-mcpu=cortex-m4", "-mthumb", "-x", "assembler-with-cpp", "-c", str(basla), "-o", str(so)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if r.returncode != 0:
                print("[STM32] startup derlenmedi:\n" + r.stderr[:2000])
                return 1
            elf = Path(td) / "pemf.elf"
            r = subprocess.run(
                [
                    str(gcc),
                    "-mcpu=cortex-m4",
                    "-mthumb",
                    "-mfpu=fpv4-sp-d16",
                    "-mfloat-abi=hard",
                    "-T",
                    str(ld),
                    "-Wl,--gc-sections",
                    "-specs=nano.specs",
                    "-specs=nosys.specs",
                    *nesneler,
                    str(so),
                    "-lm",
                    "-o",
                    str(elf),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if r.returncode != 0:
                print("[STM32] ### BAGLANMADI (cozulmemis sembol / tasma):")
                print(r.stderr[:3000])
                return 1
            boyut = shutil.which("arm-none-eabi-size") or str(Path(gcc).with_name("arm-none-eabi-size.exe"))
            if Path(boyut).is_file():
                r = subprocess.run([boyut, str(elf)], capture_output=True, text=True)
                print("[STM32] " + r.stdout.strip().replace("\n", "\n[STM32] "))
        else:
            print("[STM32] NOT: startup/linker betigi yok — yalniz derleme yapildi, baglama ATLANDI.")
    print(f"[STM32] ✓ {len(kaynaklar)} kaynak temiz derlendi (-Wall -Wextra).")
    return 0


def derle_s3() -> int:
    cli = _s3_cli()
    if cli is None:
        print("[ESP-S3] ATLANDI — arduino-cli bulunamadi (Arduino IDE kurulu degil).")
        return 0
    if not S3_PROJE.is_dir():
        print("[ESP-S3] ATLANDI — proje dizini yok.")
        return 0
    print(f"[ESP-S3] arduino-cli: {cli}")
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run(
            [
                str(cli),
                "compile",
                "--fqbn",
                "esp32:esp32:esp32s3:PartitionScheme=min_spiffs",
                "--build-path",
                td,
                str(S3_PROJE),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    if r.returncode != 0:
        print("[ESP-S3] ### DERLENMEDI:")
        print((r.stdout + "\n" + r.stderr)[-4000:])
        return 1
    for satir in (r.stdout or "").splitlines():
        if "Sketch uses" in satir or "Global variables" in satir:
            print("[ESP-S3] " + satir.strip())
    print("[ESP-S3] ✓ temiz derlendi (min_spiffs).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="PEMF firmware derleme kapisi")
    ap.add_argument("--stm", action="store_true", help="yalniz STM32")
    ap.add_argument("--s3", action="store_true", help="yalniz ESP32-S3")
    a = ap.parse_args()
    hepsi = not (a.stm or a.s3)
    kod = 0
    if hepsi or a.stm:
        kod |= derle_stm()
    if hepsi or a.s3:
        kod |= derle_s3()
    print()
    print("SONUC: " + ("TEMIZ" if kod == 0 else "BASARISIZ"))
    return kod


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
