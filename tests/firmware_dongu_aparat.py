# Author: mertaygn, cglrgrkn
"""STM ANA DÖNGÜ KOŞUM TAKIMI — Python tarafı (Dalga 1 · 1-G · D1.106). ⚠️ pytest TOPLAMAZ (`test_` ön eki yok).

GERÇEK firmware (`main.c`, `pemf_sensor.c`, `pemf_akim.c`, `stm32f4xx_it.c`, `stm32f4xx_hal_msp.c`,
`system_stm32f4xx.c`) + GERÇEK vendored HAL 1.8.5 + `tests/firmware_host/dongu/dongu_kosum.c` MSVC x64'te ya da
(Y344-1, CT2 f2) GCC mingw-w64 x64'te derlenir (`PEMF_CC=<gcc>`; gcov ölçümü `PEMF_FW_KAPSAM=1` → `scripts/firmware_kapsam.py`)
(VEH + tek adım yazmaç modeli; ayrıntı C dosyasının başında). Derlemeden önceki biçim dönüşümleri (anlam aynı, sayıları
DOĞRULANIR — sıfır dönüşüm = aparat kör → hata; `__weak` dönüşümü YALNIZ MSVC — GCC'de gerçek zayıf sembol):
    main.c / pemf_sensor.c   `__asm volatile("nop");`  → `pemf_host_nop();`
    HAL .c                   `__weak <tür> AD(`         → `<tür> AD__zayif(` + `#pragma comment(linker, "/alternatename:AD=AD__zayif")`
                             (MSVC'de zayıf sembol yok; güçlü tanım — main.c / koşum takımı — varsa O bağlanır)
CMSIS `core_cm4.h` / `cmsis_version.h` / `mpu_armv7.h` DEĞİŞMEDEN derleme dizinine kopyalanır; yanlarındaki
`cmsis_compiler.h` koşum takımının MSVC katmanıdır.

⚠️ YALNIZ WINDOWS (VEH + VirtualProtect): derleyici YOKSA FAIL (SKIP değil); Windows dışı platformda çağıran test
açık gerekçeyle atlar (Linux portu YOK — rapor: açık madde).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import firmware_host_aparat as fw

KOK = Path(__file__).resolve().parents[1]
FW = KOK / "firmware" / "stm32_pemf"
CORE_SRC = FW / "Core" / "Src"
CORE_INC = FW / "Core" / "Inc"
HAL_SRC = FW / "Drivers" / "STM32F4xx_HAL_Driver" / "Src"
HAL_INC = FW / "Drivers" / "STM32F4xx_HAL_Driver" / "Inc"
CMSIS_INC = FW / "Drivers" / "CMSIS" / "Include"
CMSIS_DEV = FW / "Drivers" / "CMSIS" / "Device" / "ST" / "STM32F4xx" / "Include"
TAKIM = Path(__file__).resolve().parent / "firmware_host" / "dongu"

HAL_MODULLERI = [
    "stm32f4xx_hal.c",
    "stm32f4xx_hal_cortex.c",
    "stm32f4xx_hal_rcc.c",
    "stm32f4xx_hal_rcc_ex.c",
    "stm32f4xx_hal_gpio.c",
    "stm32f4xx_hal_uart.c",
    "stm32f4xx_hal_tim.c",
    "stm32f4xx_hal_tim_ex.c",
    "stm32f4xx_hal_dma.c",
    "stm32f4xx_hal_pwr.c",
    "stm32f4xx_hal_pwr_ex.c",
]
DOGRUDAN = ["pemf_akim.c", "stm32f4xx_it.c", "stm32f4xx_hal_msp.c", "system_stm32f4xx.c"]

_NOP = '__asm volatile("nop");'
#: main.c çeviri biriminin SONUNA eklenen salt-okur sonda: koşum takımı her ms bobinlerin ETKİN (g_active) duty
#: maskesini okur ve değişimi "A <t_us> <maske>" diye yazar (firmware davranışını DEĞİŞTİRMEZ — yalnız okur).
SONDA = """

/* ── ana makine sondası (firmware_dongu_aparat.py ekler; yalnız OKUR) ── */
uint32_t pemf_host_aktif_maske(void) {
  uint32_t m = 0U;
  for (uint32_t i = 0U; i < NUM_COILS; i++) {
    if (g_active.coil[i].duty > 0.0f) {
      m |= (1UL << i);
    }
  }
  return m;
}
"""
_ZAYIF = re.compile(r"^__weak\s+(?P<tip>[\w\s\*]*?\b)(?P<ad>[A-Za-z_]\w*)\s*\(", re.M)


def nop_donustur(kaynak: str) -> tuple[str, int]:
    return kaynak.replace(_NOP, "pemf_host_nop();"), kaynak.count(_NOP)


def zayif_donustur(kaynak: str) -> tuple[str, list[str]]:
    adlar: list[str] = []

    def _yer(m: re.Match) -> str:
        adlar.append(m.group("ad"))
        return f"{m.group('tip')}{m.group('ad')}__zayif("

    metin = _ZAYIF.sub(_yer, kaynak)
    if adlar:
        metin += "\n" + "".join(f'#pragma comment(linker, "/alternatename:{a}={a}__zayif")\n' for a in adlar)
    return metin, adlar


def derle(dizin: Path, main_metni: str | None = None, ek_tanimlar: tuple[str, ...] = ()) -> Path:
    """Koşum takımını `dizin`de derle → exe. `main_metni`: main.c METNİ (mutasyon için; varsayılan depodaki)."""
    tur, arac = fw.derleyici_gerekli()
    if tur == "gcc":
        return _derle_gcc(arac, dizin, main_metni, ek_tanimlar)
    assert tur == "msvc", f"ana döngü koşum takımı MSVC ya da GCC (mingw-w64) ile derlenir; bulunan: {tur}"
    dizin.mkdir(parents=True, exist_ok=True)
    main_c, n_main = nop_donustur(main_metni if main_metni is not None else fw.MAIN_C.read_text(encoding="utf-8"))
    assert n_main >= 2, f"aparat: main.c'de {n_main} NOP dönüştürüldü (biçim değişmiş)"
    (dizin / "main_host.c").write_text(main_c + SONDA, encoding="utf-8")
    sensor_c, n_sensor = nop_donustur((CORE_SRC / "pemf_sensor.c").read_text(encoding="utf-8"))
    assert n_sensor >= 1, "aparat: pemf_sensor.c'de NOP yok (biçim değişmiş)"
    (dizin / "pemf_sensor_host.c").write_text(sensor_c, encoding="utf-8")
    zayif_toplam = 0
    hal_hedef = []
    for ad in HAL_MODULLERI:
        metin, adlar = zayif_donustur((HAL_SRC / ad).read_text(encoding="utf-8", errors="replace"))
        zayif_toplam += len(adlar)
        hedef = ad.replace(".c", "_host.c")
        (dizin / hedef).write_text(metin, encoding="utf-8")
        hal_hedef.append(hedef)
    assert zayif_toplam >= 20, f"aparat: HAL'de yalnız {zayif_toplam} __weak tanımı dönüştürüldü"
    for ad in ("core_cm4.h", "cmsis_version.h", "mpu_armv7.h"):
        shutil.copyfile(CMSIS_INC / ad, dizin / ad)
    for ad in ("cmsis_compiler.h", "pemf_host_on.h", "dongu_kosum.c", "dongu_win.c"):
        shutil.copyfile(TAKIM / ad, dizin / ad)
    ic = " ".join(f'/I "{p}"' for p in (dizin, CORE_INC, HAL_INC, CMSIS_DEV, CMSIS_INC))
    tanim = " ".join(f"/D{t}" for t in ("STM32F429xx", "USE_HAL_DRIVER", "_CRT_SECURE_NO_WARNINGS", *ek_tanimlar))
    ortak = f"/nologo /std:c11 /W1 /utf-8 /Od /c {ic} {tanim} /FI pemf_host_on.h"
    dogrudan = " ".join(f'"{CORE_SRC / a}"' for a in DOGRUDAN)
    exe = dizin / "dongu_kosum.exe"
    (dizin / "derle.bat").write_text(
        "@echo off\r\n"
        f'call "{arac}" >nul || exit /b 91\r\n'
        f"cl {ortak} /Dmain=pemf_fw_main main_host.c || exit /b 92\r\n"
        f"cl {ortak} pemf_sensor_host.c dongu_kosum.c {' '.join(hal_hedef)} {dogrudan} || exit /b 93\r\n"
        "cl /nologo /std:c11 /W3 /utf-8 /Od /c dongu_win.c || exit /b 95\r\n"
        f"cl /nologo *.obj /Fe:{exe.name} || exit /b 94\r\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        ["cmd", "/c", str(dizin / "derle.bat")],
        cwd=str(dizin),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    assert r.returncode == 0 and exe.is_file(), (
        f"derleme başarısız (rc={r.returncode}):\n{(r.stdout or '')[-4000:]}\n{(r.stderr or '')[-1500:]}"
    )
    return exe


#: gcc kolunda gcov ile ÖLÇÜLEN çeviri birimleri (scripts/firmware_kapsam.py ESLEME ile aynı küme; HAL / koşum takımı ölçülmez)
OLCULEN = ("main_host.c", "pemf_sensor_host.c", "pemf_akim.c")


def _derle_gcc(gcc: str, dizin: Path, main_metni: str | None, ek_tanimlar: tuple[str, ...]) -> Path:
    """Y344-1 (sahip 27-11, istem 66 CT2 f2): AYNI koşum takımı GCC (mingw-w64 x64) ile — gcov ölçümü için (`PEMF_FW_KAPSAM=1`).

    MSVC kolundan farkı yalnız derleyiciye özgü katman: HAL `__weak` tanımları GERÇEK zayıf sembol kalır (hal_def.h GCC kolu —
    `/alternatename` dönüşümü YOK, HAL kaynakları DEĞİŞMEDEN derlenir), zorunlu başlık `-include`, iç işlevler cmsis_compiler.h GCC kolu.
    Firmware ürün kodu DEĞİŞMEZ (aynı NOP dönüşümü + salt-okur sonda)."""
    import os

    dizin.mkdir(parents=True, exist_ok=True)
    main_c, n_main = nop_donustur(main_metni if main_metni is not None else fw.MAIN_C.read_text(encoding="utf-8"))
    assert n_main >= 2, f"aparat: main.c'de {n_main} NOP dönüştürüldü (biçim değişmiş)"
    (dizin / "main_host.c").write_text(main_c + SONDA, encoding="utf-8")
    sensor_c, n_sensor = nop_donustur((CORE_SRC / "pemf_sensor.c").read_text(encoding="utf-8"))
    assert n_sensor >= 1, "aparat: pemf_sensor.c'de NOP yok (biçim değişmiş)"
    (dizin / "pemf_sensor_host.c").write_text(sensor_c, encoding="utf-8")
    for ad in ("core_cm4.h", "cmsis_version.h", "mpu_armv7.h"):
        shutil.copyfile(CMSIS_INC / ad, dizin / ad)
    for ad in ("cmsis_compiler.h", "pemf_host_on.h", "dongu_kosum.c", "dongu_win.c"):
        shutil.copyfile(TAKIM / ad, dizin / ad)
    kapsam_acik = os.environ.get("PEMF_FW_KAPSAM") == "1"
    ic = [f"-I{p}" for p in (dizin, CORE_INC, HAL_INC, CMSIS_DEV, CMSIS_INC)]
    tanim = [f"-D{t}" for t in ("STM32F429xx", "USE_HAL_DRIVER", *ek_tanimlar)]
    ortak = ["-std=gnu11", "-O0", "-w", *ic, *tanim, "-include", str(dizin / "pemf_host_on.h"), "-c"]
    birimler = [
        (dizin / "main_host.c", ["-Dmain=pemf_fw_main"]),
        (dizin / "pemf_sensor_host.c", []),
        (dizin / "dongu_kosum.c", []),
        *((HAL_SRC / ad, []) for ad in HAL_MODULLERI),
        *((CORE_SRC / ad, []) for ad in DOGRUDAN),
    ]
    komutlar = []
    for kaynak, ek in birimler:
        kapsam = ["--coverage"] if kapsam_acik and kaynak.name in OLCULEN else []
        komutlar.append([gcc, *ortak, *ek, *kapsam, str(kaynak), "-o", f"{kaynak.stem}.o"])
    komutlar.append(
        [
            gcc,
            "-std=gnu11",
            "-O0",
            *(["-DPEMF_FW_KAPSAM"] if kapsam_acik else []),
            "-c",
            "dongu_win.c",
            "-o",
            "dongu_win.o",
        ]
    )
    nesneler = [k[-1] for k in komutlar]
    exe = dizin / "dongu_kosum.exe"
    komutlar.append([gcc, *nesneler, *(["--coverage"] if kapsam_acik else []), "-o", exe.name])
    for k in komutlar:
        r = subprocess.run(
            k, cwd=str(dizin), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600
        )
        assert r.returncode == 0, (
            f"gcc derleme başarısız (rc={r.returncode}): {' '.join(k[-3:])}\n{(r.stderr or '')[-3000:]}"
        )
    assert exe.is_file(), "gcc: dongu_kosum.exe üretilmedi"
    return exe


def kos(exe: Path, senaryo: str, dizin: Path, ad: str = "senaryo", sinir_sn: int = 900) -> dict:
    """Senaryoyu koş → {"satirlar": [(bas_us, bitis_us, metin)], "son": {...}, "ham": [...]}"""
    yol = dizin / f"{ad}.txt"
    yol.write_text(senaryo, encoding="ascii")
    r = subprocess.run(
        [str(exe), str(yol), str(sinir_sn)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=sinir_sn + 60,
    )
    ham = (r.stdout or "").splitlines()
    son = next((s for s in ham if s.startswith("SON ")), None)
    assert r.returncode == 0 and son, (
        f"koşum takımı rc={r.returncode} (3 = asılı, 4 = süre aşımı, 5 = main döndü, 7 = ölümcül): "
        f"{[s for s in ham if s.startswith('!!!')][:3]} {(r.stderr or '')[-800:]}"
    )
    satirlar, aktif = [], []
    for s in ham:
        if s.startswith("L "):
            p = s.split(" ", 3)
            satirlar.append((int(p[1]), int(p[2]), p[3] if len(p) > 3 else ""))
        elif s.startswith("A "):
            p = s.split()
            aktif.append((int(p[1]), int(p[2])))
    return {"satirlar": satirlar, "aktif": aktif, "son": dict(x.split("=", 1) for x in son.split()[1:]), "ham": ham}


def windows_mu() -> bool:
    return sys.platform == "win32"
