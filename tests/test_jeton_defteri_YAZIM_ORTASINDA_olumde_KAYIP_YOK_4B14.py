# -*- coding: utf-8 -*-
"""4B-1.4 — çevrimdışı jeton defteri (`PEMF_DATA_DIR/jeton_bekleyen.json`) yazım ortasında süreç ölürse BEKLEYEN TÜKETİM KAYBOLUR.

`JetonYoneticisi._defteri_yaz` dosyayı YERİNDE yazıyordu (`Path.write_text` = önce kesip boşaltır, sonra yazar). D4.23 uzlaştırmayı
arka plandaki DAEMON iş parçacığına taşıdı (süreç kapanışında yarıda öldürülür; NSIS `taskkill /F` da aynı). Yarım kalan defter
`_defteri_oku`'da `except Exception: return []` ile SESSİZCE boş sayılır → `bekleyen` 0, çevrimdışı tavan sıfırlanır, bir sonraki
yazım bozuk dosyanın ÜZERİNE yalnız yeni kaydı yazar → uzlaşmamış tüm tüketim KALICI kaybolur (bedava analiz; Y24 geriye dönük düşüm
olmaz). Ölçüm: GERÇEK `servers.jeton` alt süreçte; defter dizinindeki bir dosya nesnesine ilk `write` çağrısında (bayt yazılmadan
önce) süreç `os._exit(9)` ile ölür (profil kancası — deterministik; yarış penceresine bağlı DEĞİL).
Ek kol: ürünün bu yollarda bıraktığı HER artık dosya (geçici / karantina) KVKK tam temizlik izinde (`scripts/pemf_footprint.ps1`)
defterle AYNI konumlarda ve AYNI kuralla bulunmalı (aksi hâlde "cihazı kaldırdım" diyen klinikte cihaz kimliği kalır)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
N = 2_000
DEFTER = "jeton_bekleyen.json"

_COCUK = textwrap.dedent(
    r"""
    import os, sys
    sys.path.insert(0, sys.argv[1])
    os.environ["PEMF_DATA_DIR"] = sys.argv[2]
    import servers.jeton as j
    y = j._defter_yoneticisi(sahip="s")
    N = int(sys.argv[3])
    y._defteri_yaz([{"istek_id": f"i{n}", "miktar": 1, "tur": "analiz", "detay": "goruntu", "cihaz_id": None, "sahip": "s"} for n in range(N)])
    dizin = os.path.normcase(os.path.abspath(sys.argv[2]))

    def _kanca(frame, olay, arg):
        # Defter dizinindeki HERHANGİ bir dosya nesnesine (defterin kendisi ya da geçici dosya) ilk `write` çağrısında,
        # bayt yazılmadan ÖNCE süreç ölür: yazım ORTASINDA ölüm (daemon iplik kapanışı / taskkill /F) — deterministik.
        if olay == "c_call" and getattr(arg, "__name__", "") in ("write", "writelines"):
            ad = getattr(getattr(arg, "__self__", None), "name", None)
            if isinstance(ad, str) and os.path.normcase(os.path.dirname(os.path.abspath(ad))) == dizin:
                os._exit(9)

    sys.setprofile(_kanca)
    y._bekleyene_ekle({"istek_id": "yeni", "miktar": 1, "tur": "analiz", "detay": "goruntu", "cihaz_id": None, "sahip": "s"})
    sys.setprofile(None)
    os._exit(0)
    """
)


def _jeton(tmp_path, monkeypatch):
    veri = tmp_path / "veri"  # conftest tmp_path'e kendi yalıtım dizinlerini koyar — defter kökü AYRI
    veri.mkdir(exist_ok=True)
    monkeypatch.setenv("PEMF_DATA_DIR", str(veri))
    import servers.jeton as j

    return j


def _cokme(veri: Path) -> subprocess.CompletedProcess:
    veri.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, "-c", _COCUK, str(KOK / "apps" / "backend"), str(veri), str(N)],
        capture_output=True, text=True, timeout=300,
    )  # fmt: skip


def _yarim_defter(j) -> tuple[Path, str]:
    kayitlar = [
        {"istek_id": f"i{n}", "miktar": 1, "tur": "analiz", "detay": "goruntu", "cihaz_id": None, "sahip": "s"}
        for n in range(5)
    ]
    yol = j._defter_yolu()
    tam = json.dumps(kayitlar)
    yol.write_text(tam[: len(tam) // 2], encoding="utf-8")  # önceki bir ölümden kalan yarım defter
    j._defter_yoneticisi(sahip="s")._bekleyene_ekle(
        {"istek_id": "yeni", "miktar": 1, "tur": "analiz", "detay": "goruntu", "cihaz_id": None, "sahip": "s"}
    )
    return yol, tam[: len(tam) // 2]


def _kurtarilabilir(p: Path, yarim: str) -> bool:
    metin = p.read_text(encoding="utf-8", errors="replace")
    if yarim in metin:
        return True
    for satir in metin.splitlines():
        try:
            d = json.loads(satir)
        except ValueError:
            continue
        if isinstance(d, dict) and any(v == yarim for v in d.values()):
            return True
    return False


def test_KRITIK_yazim_ortasinda_surec_olurse_bekleyen_tuketim_KAYBOLMAZ(tmp_path, monkeypatch):
    j = _jeton(tmp_path, monkeypatch)
    veri = tmp_path / "cokme"
    r = _cokme(veri)
    assert r.returncode in (0, 9), f"çocuk süreç beklenmedik biçimde bitti (rc={r.returncode}):\n{r.stderr[-1500:]}"
    okunan = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 0, tuketim_gonderici=lambda **k: False, defter_yolu=veri / DEFTER, sahip="s"
    )._defteri_oku()
    assert len(okunan) >= N, (
        f"yazım ortasında süreç öldü (rc={r.returncode}) ve defterde {len(okunan)}/{N} kayıt kaldı — "
        "uzlaşmamış çevrimdışı tüketim KAYBOLDU (defter yerinde yazılıyor, atomik değil)"
    )


def test_KRITIK_bozuk_defter_sonraki_yazimda_SESSIZCE_EZILMEZ(tmp_path, monkeypatch):
    j = _jeton(tmp_path, monkeypatch)
    yol, yarim = _yarim_defter(j)
    korunan = [p for p in yol.parent.iterdir() if p.is_file() and p != yol and _kurtarilabilir(p, yarim)]
    assert korunan, (
        "yarım defter bir sonraki yazımda ÜZERİNE yazıldı ve hiçbir yerde saklanmadı — içindeki uzlaşmamış tüketim "
        "elle bile kurtarılamaz"
    )
    assert json.loads(yol.read_text(encoding="utf-8")), "yeni defter geçerli JSON değil"


def test_KARSIT_saglam_defter_okunur_ve_eklenir_ARTIK_birakmaz(tmp_path, monkeypatch):
    j = _jeton(tmp_path, monkeypatch)
    y = j._defter_yoneticisi(sahip="s")
    for n in range(3):
        y._bekleyene_ekle(
            {"istek_id": f"k{n}", "miktar": 1, "tur": "analiz", "detay": "goruntu", "cihaz_id": None, "sahip": "s"}
        )
    assert y.sahibin_bekleyen_sayisi() == 3
    assert sorted(p.name for p in j._defter_yolu().parent.iterdir()) == [DEFTER], "geçici/karantina artığı kaldı"


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh yok")
def test_KRITIK_urunun_biraktigi_artik_dosyalar_KVKK_tam_temizlik_izinde(tmp_path, monkeypatch):
    j = _jeton(tmp_path, monkeypatch)
    _cokme(tmp_path / "cokme")
    yol, _ = _yarim_defter(j)
    artiklar = {p.name for p in (tmp_path / "cokme").iterdir() if p.name != DEFTER}
    artiklar |= {p.name for p in yol.parent.iterdir() if p.is_file() and p.name != DEFTER}
    surucu = tmp_path / "fp.ps1"
    surucu.write_text(
        "param([string]$F)\n. $F\n(Get-PemfFootprint).Paths | ForEach-Object { \"$($_.Kind)|$($_.Path)|$($_.Kvkk)\" }\n",
        encoding="utf-8-sig",
    )
    r = subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(surucu),
         str(KOK / "scripts" / "pemf_footprint.ps1")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        env={**__import__("os").environ, "POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"},
    )  # fmt: skip
    satirlar = [s.split("|") for s in r.stdout.splitlines() if s.count("|") == 2]
    defter_konumlari = {(k, p[: -len(DEFTER)], kv) for k, p, kv in satirlar if p.endswith("\\" + DEFTER)}
    assert len(defter_konumlari) == 3, (
        f"çıpa: footprint'te defterin 3 konumu yok: {defter_konumlari}\n{r.stderr[-600:]}"
    )
    eksik = sorted(
        f"{k}:{onek}{ad}" for ad in artiklar for (k, onek, kv) in defter_konumlari if [k, onek + ad, kv] not in satirlar
    )
    assert not eksik, f"ürünün bıraktığı defter artıkları KVKK tam temizlik izinde YOK (cihazda kalır): {eksik}"
