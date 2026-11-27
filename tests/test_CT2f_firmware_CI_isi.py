# -*- coding: utf-8 -*-
"""CT2 f / f2 (istem 66 · Y326 katman 9 · Y344-1) — KART YAZILIMI CI + ana döngü koşum takımının gcc portu.

· tests.yml `firmware` işi: STM32 derlemesi HER push'ta resmî Arm GNU Toolchain 12.3.rel1 ile (CubeIDE 1.17 "GNU Tools for STM32
  12.3.rel1" ile aynı GCC 12.3.1; sürüm + SHA-256 sabit) + boyut iş özetine; bilgisayar koşum takımı testleri winlibs GCC (sabit
  özet) + gcov → `scripts/firmware_kapsam.py --taban` (kart yazılımı tabanı) + fark kapsamı
· f2: ana döngü koşum takımı (ACİL DURDUR, komut ayrıştırma, bekçi) artık gcc'yle de derlenir (MSVC kolu AYNEN) — HAL `__weak`
  gcc'de gerçek zayıf sembol, TerminateProcess öncesi `__gcov_dump` (yalnız kapsam kipinde); `pemf_akim.c` ölçülür; sondanın
  eklediği satırlar ölçülmez. Ölçüldü (28-11): MSVC ↔ gcc 147 / 147 aynı sonuç; kart yazılımı %24,19 → %89,26.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("firmware_kapsam_ct2f", KOK / "scripts" / "firmware_kapsam.py")
fk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fk)
TAKIM = KOK / "tests" / "firmware_host" / "dongu"


def _is() -> dict:
    return yaml.safe_load((KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))["jobs"]["firmware"]


def _adimlar() -> str:
    return "\n".join(str(a.get("run", "")) for a in _is()["steps"])


def test_KRITIK_firmware_isi_ARM_12_3_rel1_SABIT_OZETLE_derler():
    is_ = _is()
    soz = json.loads((KOK / "scripts" / "ci_sozlesmesi.json").read_text(encoding="utf-8"))
    assert is_["name"] in {g["ad"] for g in soz["gerekli_isler"]} and "if" not in is_
    run = _adimlar()
    assert (
        "https://developer.arm.com/-/media/Files/downloads/gnu/12.3.rel1/binrel/arm-gnu-toolchain-12.3.rel1-mingw-w64-i686-arm-none-eabi.zip"
        in run
    )
    assert re.search(
        r'echo "d52888bf59c5262ebf3e6b19b9f9e6270ecb60fd218cf81a4e793946e805a654  \$z" \| sha256sum -c -', run
    )
    derle = [a for a in is_["steps"] if "scripts/firmware_derle.py --stm" in str(a.get("run", ""))]
    assert len(derle) == 1 and "if" not in derle[0], "STM32 derlemesi HER push'ta koşmuyor"
    assert "--fw-boyut" in run, "kart ikilisi boyutu iş özetine yazılmıyor"


def test_KRITIK_firmware_isi_GCOV_ile_olcer_TABAN_ve_FARK_kapsami():
    run = _adimlar()
    assert re.search(
        r'echo "3c69305081e4a647144339a936244fcf7d3d9e558319e1ad7be2cd2886d4b6a1  \$z" \| sha256sum -c -', run
    )
    assert 'echo "PEMF_CC=' in run and 'echo "PEMF_GCOV=' in run
    test = next(a for a in _is()["steps"] if "@fw_testleri.txt" in str(a.get("run", "")))
    assert test["env"]["PEMF_FW_KAPSAM"] == "1" and '--basetemp="$RUNNER_TEMP/fwtmp"' in test["run"]
    assert (
        "scripts/firmware_kapsam.py --kok \"$RUNNER_TEMP/fwtmp\" --gcov \"$PEMF_GCOV\" --lcov firmware.info --taban tests/kapsam_tabani.json"
        in run
    )
    assert "python scripts/fark_kapsami.py --lcov firmware.info:." in run


def test_KRITIK_gcc_portu_MSVC_kolu_AYNEN_GCC_kolu_VAR():
    cc = (TAKIM / "cmsis_compiler.h").read_text(encoding="utf-8")
    on = (TAKIM / "pemf_host_on.h").read_text(encoding="utf-8")
    for metin in (cc, on):
        assert "#if defined(_MSC_VER)" in metin and "#else" in metin
    assert "__declspec(noreturn)" in cc and "__attribute__((__noreturn__))" in cc
    msvc_on = on.split("#if defined(_MSC_VER)")[1].split("#else")[0]
    assert "#define __weak\n" in msvc_on and "pemf_host_ctz" in msvc_on, "MSVC kolu değişmiş"
    gcc_on = on.split("#else")[1].split("#endif")[0]
    assert "__weak" not in gcc_on, "gcc kolunda __weak ezilirse HAL zayıf sembolleri güçlüye döner"
    win = (TAKIM / "dongu_win.c").read_text(encoding="utf-8")
    blok = win[win.index("void dw_bitir(int kod)") :][:300]
    assert re.search(r"#if defined\(PEMF_FW_KAPSAM\)\s+__gcov_dump\(\);\s+#endif\s+TerminateProcess", blok), blok


def test_KRITIK_aparat_gcc_kolu_HAL_DONUSTURMEZ_kapsami_olculenlere_verir():
    t = (KOK / "tests" / "firmware_dongu_aparat.py").read_text(encoding="utf-8")
    assert 'if tur == "gcc":\n        return _derle_gcc(' in t
    gcc = t[t.index("def _derle_gcc(") : t.index("def kos(")]
    kod = gcc.split('"""', 2)[2]  # belge dizesi dışı
    assert "zayif_donustur(" not in kod and "#pragma comment" not in kod, "gcc kolu HAL'i MSVC biçimine dönüştürüyor"
    assert '"--coverage"' in gcc and "kaynak.name in OLCULEN" in gcc and "-DPEMF_FW_KAPSAM" in gcc
    assert set(re.findall(r'"(\w+\.c)"', t[t.index("OLCULEN = (") :].split(")")[0])) == {
        "main_host.c",
        "pemf_sensor_host.c",
        "pemf_akim.c",
    }


def _belge(dosya: str, satirlar: dict[int, int]) -> dict:
    return {
        "files": [
            {"file": dosya, "functions": [], "lines": [{"line_number": k, "count": v} for k, v in satirlar.items()]}
        ]
    }


def test_KRITIK_pemf_akim_ESLENIR_sonda_satirlari_OLCULMEZ():
    akim_satir = len(
        (KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "pemf_akim.c").read_text(encoding="utf-8").splitlines()
    )
    sonuc = fk.birlestir(
        [_belge("C:/x/Core/Src/pemf_akim.c", {10: 1, akim_satir: 1, akim_satir + 1: 0, akim_satir + 9: 0})]
    )
    assert sonuc == {"firmware/stm32_pemf/Core/Src/pemf_akim.c": {10: 1, akim_satir: 1}}, sonuc
    assert fk._satir_sayisi("yok/olmayan.c") > 10**9


def test_KRITIK_taban_ALTINDA_cikis_1_ustunde_0(tmp_path, monkeypatch, capsys):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "main_host.gcda").write_bytes(b"x")
    monkeypatch.setattr(fk, "gcov_oku", lambda g, gcov="gcov": [_belge("main_host.c", {20: 1, 21: 0})])
    taban = tmp_path / "t.json"
    taban.write_text(json.dumps({"paketler": {"kart_yazilimi": {"satir": 60.0}}}), encoding="utf-8")
    assert fk.main(["--kok", str(tmp_path), "--taban", str(taban)]) == 1
    assert "eşik DÜŞÜRÜLMEZ" in capsys.readouterr().out
    taban.write_text(json.dumps({"paketler": {"kart_yazilimi": {"satir": 50.0}}}), encoding="utf-8")
    assert fk.main(["--kok", str(tmp_path), "--taban", str(taban)]) == 0


def test_kapsam_tabani_kart_yazilimi_ANA_DONGU_dahil():
    k = json.loads((KOK / "tests" / "kapsam_tabani.json").read_text(encoding="utf-8"))["paketler"]["kart_yazilimi"]
    assert k["satir"] >= 89.26 and "ANA DÖNGÜ" in k["olcu"]
    assert not any("YALNIZ MSVC" in v for v in k["disarida"].values())
