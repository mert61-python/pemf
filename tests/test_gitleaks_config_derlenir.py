# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GITLEAKS YAPILANDIRMASI DERLENEBILIR OLMALI (2026-08-22, yayin sirasinda bulundu).

OLCULEN ARIZA. 2. tur denetimi [2.2] icin `.gitleaks.toml`a iki ozel kural eklenmisti:
dusuk-entropili WiFi/MQTT parolalari varsayilan kurallarca yakalanmiyordu ve `git add -A` o
sinifi PUBLIC depoya tasiyabiliyordu. Kurallardan birinin `path` deseninde ayrac sinifi TEK
ters-bolukle yazilmisti. TOML literal dizesi ('''...''') kacis islemez; Go'ya kapanis
parantezi KACIRILMIS bir karakter sinifi ulasiyor, sinif hic kapanmiyor ve
`regexp.MustCompile` PANIK ediyor.

SONUC: gitleaks HER calismada cokuyordu. Yani sir tarama kapisi — eklendigi gunden beri —
HIC TARAMADI. Hem pre-commit kancasi hem CI ayni config'i okudugu icin iki kapi da olmustu.
Panik `git commit` ciktisinda bir Go yigin izi olarak goruluyordu; commit dusuyordu ama
"sizinti yok" gibi degil, "kanca hatasi" gibi. Yayin icin commit atilana kadar fark edilmedi.

DERS: bir GUVENLIK KAPISININ CALISTIGI, kapinin VARLIGINDAN ayri olarak dogrulanmalidir.
Yapilandirmayi eklemek yetmez; yuklenip derlendigini de olcmek gerekir.

Bu dosya: (1) her kural/allowlist deseninin derlendigini, (2) gitleaks ikilisi bulunabiliyorsa
config'i GERCEKTEN yukleyip cokmedigini olcer.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_CONFIG = _KOK / ".gitleaks.toml"

# TOML literal dizeleri: regex = '''...'''  /  path = '''...'''  /  liste ogeleri
_DESEN = re.compile(r"^\s*(?:regex|path)\s*=\s*'''(.*?)'''\s*$", re.M | re.S)
_LISTE_OGE = re.compile(r"^\s*'''(.*?)''',\s*$", re.M | re.S)


def _desenler() -> list[tuple[int, str]]:
    metin = _CONFIG.read_text(encoding="utf-8")
    bulunan: list[tuple[int, str]] = []
    for m in list(_DESEN.finditer(metin)) + list(_LISTE_OGE.finditer(metin)):
        satir = metin[: m.start()].count("\n") + 1
        bulunan.append((satir, m.group(1)))
    return bulunan


def test_KRITIK_her_desen_DERLENIR():
    """Dengesiz parantez/karakter sinifi hem Go'da hem Python'da patlar — vekil olarak yeterli."""
    desenler = _desenler()
    assert desenler, ".gitleaks.toml icinde hic desen bulunamadi (ayristirici bozulmus olabilir)"

    hatali = []
    for satir, desen in desenler:
        try:
            re.compile(desen)
        except re.error as e:
            hatali.append(f"  satir {satir}: {e}  ->  {desen}")

    assert not hatali, (
        "gitleaks yapilandirmasinda DERLENMEYEN desen(ler) var. Gitleaks bunlarda PANIK eder ve "
        "HICBIR SEY TARAMAZ — kapi sessizce olur:\n" + "\n".join(hatali)
    )


def test_KRITIK_gitleaks_config_i_GERCEKTEN_yukluyor():
    """Vekil degil, GERCEK olcum: gitleaks ikilisi bu config'le calisip cokmuyor mu?

    ⚠️ Ikili yoksa test ATLANIR (gelistirici makinesinde kurulu olmayabilir); ama CI'da
    pre-commit gitleaks'i indirdigi icin orada GERCEKTEN kosar.
    """
    ikili = shutil.which("gitleaks")
    if not ikili:
        adaylar = list((Path.home() / ".cache" / "pre-commit").glob("**/gitleaks.exe")) + list(
            (Path.home() / ".cache" / "pre-commit").glob("**/gitleaks")
        )
        ikili = str(adaylar[0]) if adaylar else None
    if not ikili:
        pytest.skip("gitleaks ikilisi bulunamadi (CI'da pre-commit indirir)")

    bos = _KOK / "tests" / "__gitleaks_bos__"
    bos.mkdir(exist_ok=True)
    try:
        r = subprocess.run(
            [ikili, "detect", "--config", str(_CONFIG), "--no-git", "--no-banner", "-s", str(bos)],
            capture_output=True,
            text=True,
            timeout=180,
        )
    finally:
        try:
            bos.rmdir()
        except OSError:
            pass

    cikti = (r.stdout or "") + (r.stderr or "")
    assert "panic:" not in cikti.lower(), (
        "gitleaks config'i yuklerken PANIK etti — kapi calismiyor demektir:\n" + cikti[:1200]
    )
    assert "MustCompile" not in cikti, "regex derleme hatasi (MustCompile):\n" + cikti[:1200]


def test_KARSIT_KANIT_ozel_kurallar_HALA_YERINDE():
    """Asiri-genisleme korumasi: 'derlensin' diye kurallari SILMEK de testi yesil yapardi.
    [2.2] kapisinin iki kurali duruyor mu?"""
    metin = _CONFIG.read_text(encoding="utf-8")
    for kural in ("pemf-firmware-secrets-h-gercek-deger", "pemf-firmware-config-json-gercek-deger"):
        assert kural in metin, f"[2.2] kurali kaybolmus: {kural}"


def test_KARSIT_KANIT_muafiyet_DAR_kalir():
    """Kapinin kendi test fikstürü muaf tutuldu; muafiyet dizin geneline genisletilmemeli —
    aksi hâlde `tests/` altina konan GERCEK bir sir de sessizce gecerdi."""
    metin = _CONFIG.read_text(encoding="utf-8")
    m = re.search(r"paths\s*=\s*\[(.*?)\]", metin, re.S)
    assert m, "allowlist paths blogu bulunamadi"
    for oge in re.findall(r"'''(.*?)'''", m.group(1)):
        assert not oge.strip().rstrip("/").endswith(("tests", "tests/.*", "tests/*")), (
            f"muafiyet TUM tests/ dizinini kapsiyor: {oge!r} — dosya bazinda dar tutun"
        )
