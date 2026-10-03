# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.64 · B-11.18 · Y36 — RUNBOOK saha modelini (launcher'ın doğurduğu süreç; `PemfBackend` servisi YOK) esas alır.

ÖLÇÜLEN KUSUR (Y36 saha ölçümü 2026-09-30): sahada backend `PEMFVetClient.exe`'nin çocuğu `PEMF_Backend.exe`; NSSM
`PemfBackend` servisi YOK. RUNBOOK ise yalnız servis komutlarını veriyordu: olay anında `nssm stop PemfBackend` sahada
HİÇBİR ŞEYİ durdurmaz ama belge "bobinlere önce STOP gider" diyordu — operatör bobinin durduğunu sanır (kat. 1).
Yeniden başlatma satırı da HEAD tabanlı derlemede oto-firmware yakma denemesi olduğunu (Y1/Y2) söylemiyordu.

KAPI (belge BLOKLARI üzerinden; bölüm düzeyi kör kalırdı — "Kötü güncelleme" bölümü başka yerde launcher'ı zaten anar):
  1. Servis komutu/eylemi geçen her blok (paragraf, liste maddesi, tablo satırı, kod bloğu) launcher karşılığını içerir.
  2. Durdurma geçen her blok ACİL DURDUR ucunu (`/api/hardware/emergency_stop`) verir — sahada gerçekten durduran yol.
  3. Yeniden başlatma komutu geçen her blok, kaynaktaki `PEMF_FW_AUTO_UPDATE` varsayılanı '1' iken (AST'den okunur —
     Y1 ile '0'a çekilince uyarı zorunluluğu kendiliğinden kalkar) oto-firmware uyarısını taşır.
  4. Giriş paragrafı saha modelini söyler (launcher; servis YOK).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
RUNBOOK = KOK / "docs" / "RUNBOOK.md"
BACKEND = KOK / "apps" / "backend"

_SERVIS = re.compile(
    r"\bnssm\b|PemfBackend|Restart-Service|Stop-Service|[Ss]ervis(?:i|in)?\s+(?:henüz\s+)?(?:\*\*)?(?:durdur|başlat|BAŞLAT)"
)
_DURDUR = re.compile(r"nssm\s+stop|Stop-Service|[Ss]ervisi?\s+durdur")
_YENIDEN = re.compile(r"nssm\s+restart|Restart-Service")
_LAUNCHER = re.compile(r"launcher|PEMF Vet Client", re.IGNORECASE)
_ESTOP = "/api/hardware/emergency_stop"


def _bloklar(metin: str) -> list[str]:
    """Markdown'ı bloklara böl: çitli kod bloğu tek blok; dışında boş satır paragrafı ayırır; liste maddesi ve tablo
    satırı kendi bloğudur (girintili devam satırları maddeye aittir)."""
    bloklar: list[str] = []
    cari: list[str] = []
    kodda = False

    def bitir():
        if cari:
            bloklar.append("\n".join(cari))
            cari.clear()

    for satir in metin.splitlines():
        if satir.lstrip().startswith("```"):
            if kodda:
                cari.append(satir)
                bitir()
                kodda = False
            else:
                bitir()
                cari.append(satir)
                kodda = True
            continue
        if kodda:
            cari.append(satir)
            continue
        if not satir.strip():
            bitir()
            continue
        if re.match(r"^\s{0,2}(?:[-*]\s|\d+\.\s|\|)", satir):
            bitir()
        cari.append(satir)
    bitir()
    return bloklar


def _fw_varsayilanlari() -> set[str]:
    """Backend kaynağındaki `os.environ.get("PEMF_FW_AUTO_UPDATE", <varsayılan>)` varsayılanları (AST)."""
    bulunan: set[str] = set()
    for py in BACKEND.rglob("*.py"):
        if "tests" in py.parts:
            continue
        agac = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for d in ast.walk(agac):
            if (
                isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr == "get"
                and len(d.args) >= 2
                and isinstance(d.args[0], ast.Constant)
                and d.args[0].value == "PEMF_FW_AUTO_UPDATE"
                and isinstance(d.args[1], ast.Constant)
            ):
                bulunan.add(str(d.args[1].value))
    return bulunan


def test_KRITIK_servis_komutu_gecen_HER_blok_launcher_karsiligini_verir():
    bloklar = _bloklar(RUNBOOK.read_text(encoding="utf-8"))
    servisli = [b for b in bloklar if _SERVIS.search(b)]
    assert len(servisli) >= 4, f"ön koşul: RUNBOOK'ta servis komutu geçen blok bulunamadı ({len(servisli)})"
    eksik = [b[:160] for b in servisli if not _LAUNCHER.search(b)]
    assert not eksik, (
        "servis komutu (sahada YOK — Y36) launcher karşılığı OLMADAN veriliyor; olay anında operatör sahada hiçbir "
        f"şeyi durdurmayan komutu uygular: {eksik}"
    )


def test_KRITIK_durdurma_gecen_HER_blok_ACIL_DURDUR_ucunu_verir():
    bloklar = _bloklar(RUNBOOK.read_text(encoding="utf-8"))
    durduran = [b for b in bloklar if _DURDUR.search(b)]
    assert durduran, "ön koşul: durdurma bloğu yok"
    eksik = [b[:160] for b in durduran if _ESTOP not in b]
    assert not eksik, f"durdurma yönergesi sahada GERÇEKTEN durduran ACİL DURDUR ucunu vermiyor: {eksik}"


def test_KRITIK_yeniden_baslatma_HEAD_derlemesinde_OTO_FIRMWARE_uyarisi_tasir():
    varsayilan = _fw_varsayilanlari()
    assert varsayilan, "ön koşul: backend'de PEMF_FW_AUTO_UPDATE varsayılanı AST'de bulunamadı (okuma yolu değişti)"
    acik = {v for v in varsayilan if v.strip() not in ("0", "false", "False")}
    bloklar = _bloklar(RUNBOOK.read_text(encoding="utf-8"))
    yeniden = [b for b in bloklar if _YENIDEN.search(b)]
    if not acik:
        return  # Y1 uygulandı (varsayılan KAPALI) — uyarı zorunlu değil
    assert yeniden, "ön koşul: yeniden başlatma bloğu yok"
    eksik = [b[:160] for b in yeniden if "PEMF_FW_AUTO_UPDATE" not in b or "firmware" not in b.lower()]
    assert not eksik, (
        f"kaynakta PEMF_FW_AUTO_UPDATE varsayılanı {sorted(acik)} (AÇIK) iken yeniden başlatma satırı oto-firmware "
        f"yakma denemesini (Y1/Y2) söylemiyor: {eksik}"
    )


def test_KRITIK_giris_paragrafi_SAHA_MODELINI_soyler():
    bloklar = _bloklar(RUNBOOK.read_text(encoding="utf-8"))
    giris = next(b for b in bloklar if not b.startswith("#"))
    assert _LAUNCHER.search(giris) and re.search(r"\byok(?:tur)?\b", giris, re.IGNORECASE), (
        f"giriş paragrafı saha modelini (launcher'ın başlattığı süreç; servis YOK) söylemiyor: {giris[:200]!r}"
    )


def test_KARSIT_blok_bolucu_kod_blogunu_ve_maddeleri_AYIRIR():
    """Aparat: maddeler/kod bloğu ayrı bloklar — yoksa komşu metindeki 'launcher' eksik bir maddeyi örterdi."""
    ornek = "Giriş launcher.\n\n1. ilk madde\n   devam nssm stop\n2. ikinci launcher\n\n```\nnssm stop X\n```\n| a | b |\n| c | d |\n"
    b = _bloklar(ornek)
    assert b == [
        "Giriş launcher.",
        "1. ilk madde\n   devam nssm stop",
        "2. ikinci launcher",
        "```\nnssm stop X\n```",
        "| a | b |",
        "| c | d |",
    ], b
