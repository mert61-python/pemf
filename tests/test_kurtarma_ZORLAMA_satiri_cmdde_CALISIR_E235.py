# -*- coding: utf-8 -*-
"""E2-3.5 (2-E incelemesi A3) — aracın bastığı ZORLAMA satırı (`set PEMF_KURTARMA_USTUNE_YAZ=1 && … --kurtarma … --yaz`) Komut
İstemi'nde (cmd.exe) GERÇEKTEN zorlar.

D2.75 her yönergeyi "sahada ÇALIŞAN" `PEMF_Backend.exe --kurtarma …` biçimine indirdi; kapısı (`_komutlar`) `&&` ÖNCESİNİ ATAR —
`set` parçası hiç ölçülmez. cmd.exe'de `set AD=1   &&` değere `&&` öncesindeki BOŞLUKLARI da katar ("1   "); araç ise
`os.environ.get(...) != "1"` ile KATI karşılaştırır → zorlama satırı aynen yapıştırılınca araç YİNE "DURDURULDU" der (rc 3).
Launcher kurulumu = kur-ve-BAŞLAT (`install_and_launch`): yeni makinede backend bir kez açılıp YENİ anahtar ürettiğinden `--yaz`
her launcher kurtarmasında DURDURULDU'ya düşer → zorlama satırı felaket gününün KRİTİK yolundadır.

Kapı: aracın GERÇEK `main`i DURDURULDU satırını üretir (sır deposu `get_secret` düzeyinde "var"); satırın `&&` öncesi AYNEN
cmd.exe'de koşulur, `&&` sonrası (sahada `PEMF_Backend.exe --kurtarma …`) yerine AYNI argümanlarla aracı koşan sürücü konur
(sır deposu sürücüde yönlendirilir; gerçek kök yok). Ortam `betik_alt_sureci.yalitik_ortam`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from betik_alt_sureci import yalitik_ortam

DEPO = Path(__file__).resolve().parents[1]

_SURUCU = r"""
import os, sys
sys.path[:0] = [{backend!r}, {depo!r}]
from utils import secrets_manager as sm
yazilan = []
sm.get_secret = lambda ad, default="", generate=True: "var"   # makinede anahtar VAR (launcher bir kez açtı)
sm.set_secrets = lambda d: yazilan.extend(sorted(d))
if {deger_bas}:
    print("DEGER=" + repr(os.environ.get("PEMF_KURTARMA_USTUNE_YAZ")))
    raise SystemExit(0)
import tools.kurtarma as k
rc = k.main(["--zarf", {zarf!r}, "--kod", {kod!r}, "--yaz"])
print("RC=%s YAZILAN=%s" % (rc, ",".join(yazilan)))
"""


@pytest.fixture()
def zorlama(tmp_path, monkeypatch, capsys):
    from utils import backup_recovery as br
    from utils import secrets_manager as sm

    import tools.kurtarma as k

    kod = br.generate_recovery_code()
    zarf = tmp_path / br.ENVELOPE_NAME
    zarf.write_bytes(br.build_envelope(kod, {"sqlcipher_key": "e235-sql", "patient_fernet_key": "e235-fer"}))
    monkeypatch.delenv("PEMF_KURTARMA_USTUNE_YAZ", raising=False)
    monkeypatch.setattr(sm, "get_secret", lambda ad, default="", generate=True: "var")
    assert k.main(["--zarf", str(zarf), "--kod", kod, "--yaz"]) == 3
    satirlar = [s for s in capsys.readouterr().out.splitlines() if "PEMF_KURTARMA_USTUNE_YAZ" in s and "&&" in s]
    assert len(satirlar) == 1, f"aparat: DURDURULDU zorlama satırı bulunamadı: {satirlar}"
    onek = satirlar[0].split("&&")[0].lstrip()
    assert onek.lower().startswith("set "), f"aparat: zorlama satırı `set` ile başlamıyor: {onek!r}"

    def surucu(deger_bas: bool) -> Path:
        s = tmp_path / ("deger.py" if deger_bas else "surucu.py")
        s.write_text(
            _SURUCU.format(
                backend=str(DEPO / "apps" / "backend"), depo=str(DEPO), zarf=str(zarf), kod=kod, deger_bas=deger_bas
            ),
            encoding="utf-8",
        )
        return s

    return onek, surucu, yalitik_ortam(tmp_path / "ev")


def _cmd(onek: str, betik: Path, env: dict) -> str:
    satir = f'{onek}&& "{sys.executable}" "{betik}"'  # sahadaki satırın && öncesi AYNEN; sonrası sürücü
    p = subprocess.run(
        f'cmd.exe /d /s /c "{satir}"',
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        stdin=subprocess.DEVNULL,
    )
    return p.stdout + p.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe")
def test_KRITIK_zorlama_satiri_cmdde_ARACI_GERCEKTEN_zorlar_E235(zorlama):
    onek, surucu, env = zorlama
    cikti = _cmd(onek, surucu(False), env)
    assert "RC=0" in cikti and "sqlcipher_key" in cikti, (
        f"aracın bastığı zorlama satırı cmd'de aracı ZORLAMADI (yine DURDURULDU?) — önek {onek!r}:\n{cikti[-800:]}"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe")
def test_KRITIK_zorlama_satirinin_set_parcasi_DEGERI_tam_1_yapar_E235(zorlama):
    onek, surucu, env = zorlama
    cikti = _cmd(onek, surucu(True), env)
    assert "DEGER='1'" in cikti, f"cmd'de `{onek}` değeri tam '1' yapmıyor:\n{cikti[-400:]}"


@pytest.mark.parametrize("deger", ["1", "1 ", "1   "])
def test_KRITIK_arac_elle_yazilan_SON_BOSLUKLU_degeri_kabul_eder_E235(zorlama, deger):
    """Operatör satırı elle yazarsa (`set PEMF_KURTARMA_USTUNE_YAZ=1 && …`) cmd değere bir boşluk katar."""
    _onek, surucu, env = zorlama
    env = dict(env, PEMF_KURTARMA_USTUNE_YAZ=deger)
    p = subprocess.run(
        [sys.executable, str(surucu(False))],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        stdin=subprocess.DEVNULL,
    )
    assert "RC=0" in p.stdout, (
        f"PEMF_KURTARMA_USTUNE_YAZ={deger!r} ile araç zorlanmadı:\n{(p.stdout + p.stderr)[-600:]}"
    )


def test_KARSIT_zorlama_YOKKEN_arac_DURUR_E235(zorlama):
    _onek, surucu, env = zorlama
    p = subprocess.run(
        [sys.executable, str(surucu(False))],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        stdin=subprocess.DEVNULL,
    )
    assert "RC=3" in p.stdout and "YAZILAN=\n" in p.stdout + "\n", (p.stdout + p.stderr)[-600:]
