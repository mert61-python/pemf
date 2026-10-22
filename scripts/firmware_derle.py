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

#: --cikti verildiginde yakilabilir dosyalarin yazilacagi dizin (None = yazma).
_CIKTI_DIZINI = None

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


#: Ölçülmeden atlanan hedefler (SONUC satırı "TEMIZ" diyemez). 1-B bağımsız inceleme (i3): araç zinciri yokken
#: `--stm` AÇIKÇA istense de "ATLANDI" + 0 → "SONUC: TEMIZ" basılıyordu (stm_yak.py'nin `--bin` girdisi bu kipte üretilir).
_ATLANAN: list[str] = []


def _atla(hedef: str, sebep: str, zorunlu: bool) -> int:
    """Ölçülemeyen hedef: açıkça istendiyse (`--stm`/`--s3`) 1, `hepsi` kipinde 0 — ama kayda geçer."""
    _ATLANAN.append(hedef)
    if zorunlu:
        print(f"[{hedef}] ### {sebep} -> ACIKCA istenen hedef OLCULEMEDI (TEMIZ DEGIL).")
        return 1
    print(f"[{hedef}] ATLANDI — {sebep}.")
    return 0


def derle_stm(zorunlu: bool = False) -> int:
    gcc = _stm_gcc()
    if gcc is None:
        return _atla("STM32", "arm-none-eabi-gcc bulunamadi (CubeIDE kurulu degil)", zorunlu)
    if not STM_PROJE.is_dir():
        return _atla("STM32", "proje dizini yok", zorunlu)
    print(f"[STM32] derleyici: {gcc}")
    inc = [
        "-I" + str(STM_PROJE / "Core" / "Inc"),
        "-I" + str(STM_PROJE / "Drivers" / "STM32F4xx_HAL_Driver" / "Inc"),
        "-I" + str(STM_PROJE / "Drivers" / "CMSIS" / "Device" / "ST" / "STM32F4xx" / "Include"),
        "-I" + str(STM_PROJE / "Drivers" / "CMSIS" / "Include"),
    ]
    kaynaklar = sorted((STM_PROJE / "Core" / "Src").rglob("*.c")) + sorted((STM_PROJE / "Drivers").rglob("*.c"))
    if not kaynaklar:
        return _atla("STM32", "kaynak bulunamadi", zorunlu)
    hata = 0
    uyarilar: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        nesneler = []
        # YH D7: nesne adı SIRA numarasından (eskiden `hash(str(k))` — PYTHONHASHSEED'e göre her koşuda başka ad; belirlenimcilik).
        for sira, k in enumerate(kaynaklar):
            hedef = Path(td) / f"{sira:03d}_{k.stem}.o"
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
                # YH D7: başarılı derlemenin UYARILARI da ölçülür — eskiden stderr yalnız hatada basılıyor, sonuç yine
                # "temiz derlendi (-Wall -Wextra)" diyordu (uyarıya hiç bakılmadan; sahte yeşil).
                uyarilar += [
                    f"{k.relative_to(STM_PROJE)}: {s.strip()}" for s in (r.stderr or "").splitlines() if "warning:" in s
                ]
        if uyarilar:
            print(f"[STM32] ### {len(uyarilar)} DERLEYICI UYARISI (-Wall -Wextra) -> TEMIZ DEGIL:")
            print("\n".join(uyarilar[:40]))
            return 1
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
            # ⚠️⚠️ printf FLOAT KAPISI — 2026-09-11 saha arizasinin kapisi.
            #
            # `-specs=nano.specs` ile newlib-nano'nun float donusumu VARSAYILAN OLARAK
            # BAGLANMAZ. O zaman `snprintf(..., "%.3f", x)` hicbir sey basmaz, HATA DA
            # VERMEZ: butun STM_TELE satirlari sayisiz gider (`B=,T=,A=,I=`), backend
            # ayristiricisi satiri reddeder ve sicaklik/alan/akim BIR DAHA HIC GELMEZ.
            # Bobinler calismaya devam ettigi icin ariza "sensor bozuk" gibi gorunur.
            #
            # ⚠️ BAYRAK BURADAN VERILMEZ (`-u _printf_float` EKLENMEZ): eklenirse bu betik
            # kendi sagladigi bayragi dogrulamis olur ve sahibin CubeIDE'de urettigi ikiliyi
            # OLCMEZ. Tek kaynak main.c'deki `g_printf_float_zorla` basvurusudur; burasi
            # yalniz URUNU olcer.
            nm = shutil.which("arm-none-eabi-nm") or str(Path(gcc).with_name("arm-none-eabi-nm.exe"))
            if printf_float_kapisi(elf, nm):
                return 1

            boyut = shutil.which("arm-none-eabi-size") or str(Path(gcc).with_name("arm-none-eabi-size.exe"))
            if Path(boyut).is_file():
                r = subprocess.run([boyut, str(elf)], capture_output=True, text=True)
                print("[STM32] " + r.stdout.strip().replace("\n", "\n[STM32] "))

            # ── YAKILABİLİR ÇIKTI (--cikti) ────────────────────────────────────
            # ⚠️ NEDEN: sahip reflash'ı CubeIDE'de yapıyor ve CubeMX "Generate Code"
            # `main.c`i EZİYOR ([[pemf-firmware-cubeide]]). Buradan üretilen .bin/.hex,
            # CubeIDE'yi hiç açmadan STM32CubeProgrammer ile yakılabilir → ezme riski YOK
            # ve yakılan şeyin DEPODAKİ kaynak olduğu SHA256 ile kanıtlanır.
            if _CIKTI_DIZINI is not None:
                _CIKTI_DIZINI.mkdir(parents=True, exist_ok=True)
                objcopy = shutil.which("arm-none-eabi-objcopy") or str(Path(gcc).with_name("arm-none-eabi-objcopy.exe"))
                if not Path(objcopy).is_file():
                    print("[STM32] HATA: arm-none-eabi-objcopy yok -> .bin/.hex URETILEMEDI.")
                    return 1
                import hashlib
                import shutil as _sh

                _sh.copy2(elf, _CIKTI_DIZINI / "pemf.elf")
                for bicim, ad in (("binary", "pemf.bin"), ("ihex", "pemf.hex")):
                    r = subprocess.run(
                        [objcopy, "-O", bicim, str(elf), str(_CIKTI_DIZINI / ad)],
                        capture_output=True,
                        text=True,
                    )
                    if r.returncode != 0:
                        print(f"[STM32] HATA: objcopy {bicim} basarisiz: {r.stderr.strip()[:200]}")
                        return 1
                for ad in ("pemf.elf", "pemf.bin", "pemf.hex"):
                    p = _CIKTI_DIZINI / ad
                    ozet = hashlib.sha256(p.read_bytes()).hexdigest()
                    print(f"[STM32] cikti: {ad}  {p.stat().st_size} bayt  sha256={ozet[:16]}…")
                print(f"[STM32] ✓ yakilabilir cikti hazir: {_CIKTI_DIZINI}")
        else:
            # ⚠️ D1.29 (B-10.215): eskiden "NOT … baglama ATLANDI" deyip 0 donuyor, sonra "SONUC: TEMIZ"
            # basiliyordu — baglanmamis bir urun icin printf-float kapisi hic kosmamisken.
            print(
                "[STM32] ### startup/linker betigi YOK -> baglama YAPILAMADI; ELF uretilmedi ve OLCULMEDI.\n"
                "[STM32]     Yalniz-derleme sonucu 'TEMIZ' SAYILMAZ (_printf_float kapisi kosmadi)."
            )
            return 1
    print(f"[STM32] ✓ {len(kaynaklar)} kaynak temiz derlendi (-Wall -Wextra).")
    return 0


def printf_float_kapisi(elf: Path, nm: str | None) -> int:
    """`_printf_float` ELF'te mi? 0 = bagli · 1 = YOK ya da OLCULEMEDI (nm yok).

    ⚠️ D1.29 (B-10.215): nm yokken eskiden yalniz "UYARI … KOSULAMADI" basilip derleme TEMIZ sayiliyordu →
    `_printf_float`'siz (tum sensor telemetrisi sessizce olu) bir ELF yakilabilirdi. Olculemeyen urun
    temiz SAYILMAZ."""
    if not nm or not Path(nm).is_file():
        print(
            "[STM32] ### arm-none-eabi-nm YOK -> printf-float kapisi KOSULAMADI; urun OLCULMEDI.\n"
            "[STM32]     Bu sonuc 'TEMIZ' SAYILMAZ: arm-none-eabi araclarini (nm dahil) PATH'e ekleyin."
        )
        return 1
    r = subprocess.run([nm, str(elf)], capture_output=True, text=True, errors="replace")
    if "_printf_float" not in (r.stdout or ""):
        print(
            "[STM32] ### BAGLANDI AMA KULLANILAMAZ: `_printf_float` ELF'te YOK.\n"
            "[STM32]     newlib-nano float printf'i baglanmamis -> TUM STM_TELE\n"
            "[STM32]     satirlari sayisiz gider (B=, T=, A=, I=) ve backend onlari\n"
            "[STM32]     reddeder: sicaklik/alan/akim ARAYUZE HIC ULASMAZ.\n"
            "[STM32]     Duzeltme: main.c'deki `g_printf_float_zorla` basvurusu\n"
            "[STM32]     silinmis olmali — geri koyun (bkz. oradaki not)."
        )
        return 1
    print("[STM32] printf float destegi: BAGLI (_printf_float ELF'te).")
    return 0


def derle_s3(zorunlu: bool = False) -> int:
    cli = _s3_cli()
    if cli is None:
        return _atla("ESP-S3", "arduino-cli bulunamadi (Arduino IDE kurulu degil)", zorunlu)
    if not S3_PROJE.is_dir():
        return _atla("ESP-S3", "proje dizini yok", zorunlu)
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
    ap.add_argument(
        "--cikti",
        metavar="DIZIN",
        help="STM32 icin yakilabilir .bin/.hex/.elf uret (CubeIDE acmadan CubeProgrammer ile yakilir)",
    )
    a = ap.parse_args()
    if a.cikti:
        global _CIKTI_DIZINI
        _CIKTI_DIZINI = Path(a.cikti)
    hepsi = not (a.stm or a.s3)
    kod = 0
    if hepsi or a.stm:
        kod |= derle_stm(zorunlu=a.stm)
    if hepsi or a.s3:
        kod |= derle_s3(zorunlu=a.s3)
    print()
    if kod:
        print("SONUC: BASARISIZ")
    elif _ATLANAN:
        print("SONUC: TEMIZ DEGIL — olculmeden atlanan: " + ", ".join(_ATLANAN))
    else:
        print("SONUC: TEMIZ")
    return kod


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
