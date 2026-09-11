# -*- coding: utf-8 -*-
# Author: mertaygn
"""`make_manifest` TEK-PARÇA TAZELİK kapısı — doğru şeyi ölçtüğünü kanıtlar.

===============================================================================
KAPININ KORUDUĞU ARIZA (2026-08-09 denetimi)
===============================================================================
Katmanlar (`layers`) bu yayında YENİ üretilmiş ama tek-parça `runtimes` ÖNCEKİ
manifest'ten TAŞINMIŞSA ikisi FARKLI build'lerdendir. Sahada ölçüldü: 53 dosya
farklıydı, `PEMF_Backend.exe` dahil. Yani client ≤1.9.12 `base.zip`ten ESKİ backend'i,
≥1.9.13 `layers`tan YENİ backend'i kuruyordu — **aynı sürüm numarası altında iki farklı
yazılım**. Tıbbi cihazda bir arızanın hangi kodda olduğu bilinemez hale gelir.

===============================================================================
⚠️ KAPININ KENDİSİ 2026-09-11'DE ARIZALANDI — AYNI KÖR NOKTA **DÖRDÜNCÜ** YERDE
===============================================================================
Kapı, "yerelde `base.zip` yok" ile "önceki manifest'ten BAYAT bir base TAŞINIYOR"u aynı
şey sanıyordu. Monolit 1.9.48'de KALICI olarak yayından çıkarıldı → `base.zip` bir daha
asla üretilmiyor → kapı **her yayını bloke etmeye başladı** (1.9.49 yayını burada durdu).
Taşınacak bir tek-parça YOKSA ayrışacak iki yazılım da yoktur.

Aynı kök daha önce ÜÇ yerde bulunmuştu (hepsi 1.9.48'de):
  · launcher `platform_supported`  · bu dosyadaki "hiçbir base paketi yok" kapısı
  · `test_manifest_consistency` paket sayacı
Ortak hata: **tek-parça kopyayı kurulabilirliğin/tazeliğin TEK ölçütü saymak.**

Bu dosya ikisini birden kilitler: kapı BAYAT taşımada hâlâ KIRMIZI, monolitsiz dünyada
ise YEŞİL. Biri olmadan öteki bir regresyon.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "make_manifest.py"

pytestmark = pytest.mark.skipif(not BETIK.exists(), reason="make_manifest.py yok")


def _manifest_yaz(dizin: Path, runtimes: dict | None) -> None:
    """Önceki manifest'i kurar. `runtimes` None → monolitsiz dünya (1.9.48 sonrası)."""
    m = {
        "version": "1.9.40",
        "tag": "client-app-v1.9.40",
        "runtimes": runtimes or {},
        "models": {
            "vet": {
                "url": "https://x/vet.zip",
                "sha256": "a" * 64,
                "size": 10,
            }
        },
        "profiles": {
            "vet": {
                "url": "https://x/vet.zip",
                "sha256": "a" * 64,
                "size": 10,
            }
        },
        "layers": {
            "win-x64": {
                "app": {"url": "https://x/base-app.zip", "sha256": "b" * 64, "size": 10},
                "deps": {"url": "https://x/base-deps.zip", "sha256": "c" * 64, "size": 10},
            }
        },
        "launcher": {"version": "1.9.51"},
        "mobile": {"android": {"version": "2.3.34"}},
    }
    if runtimes:
        m["base"] = runtimes.get("win-x64")
    (dizin / "manifest.json").write_text(json.dumps(m), encoding="utf-8")


def _kos(dizin: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(BETIK),
            "--dir",
            str(dizin),
            "--version",
            "1.9.99",
            "--tag",
            "client-app-v1.9.99",
            "--repo",
            "mert61-python/pemf-update",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(KOK),
    )


def _paketleri_koy(dizin: Path, monolit: bool) -> None:
    (dizin / "base-app.zip").write_bytes(b"APP")
    (dizin / "base-deps.zip").write_bytes(b"DEPS")
    (dizin / "vet.zip").write_bytes(b"VET")
    if monolit:
        (dizin / "base.zip").write_bytes(b"MONO")


def test_KRITIK_monolit_YOKKEN_manifest_URETILIR(tmp_path):
    """1.9.48 sonrası dünya: tek-parça yayından çıktı, önceki manifest'te de YOK.

    ⚠️ Bu, kapının 2026-09-11'de ürettiği REGRESYONUN kapısıdır: kapı burada kırmızıysa
    **hiçbir yayın yapılamaz** — ve hata mesajı "base.zip üretin" diyerek operatörü
    kaldırılmış bir paketi geri getirmeye yönlendirir.

    MUTASYON: `if not ((prev.get("runtimes") or {}).get(plat)): continue` satırını sil
    → KIRMIZI.
    """
    _manifest_yaz(tmp_path, runtimes=None)
    _paketleri_koy(tmp_path, monolit=False)
    r = _kos(tmp_path)
    assert r.returncode == 0, "monolitsiz dunyada manifest URETILEMEDI -> HICBIR YAYIN YAPILAMAZ.\n" + r.stderr[-1500:]
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert m["version"] == "1.9.99"
    assert m["layers"]["win-x64"]["app"]["sha256"] != "b" * 64, "app katmani TAZELENMEDI"


def test_KRITIK_BAYAT_monolit_tasinirken_kapi_HALA_KIRMIZI(tmp_path):
    """Karşıt kanıt: kapı gevşetildi ama KORUDUĞU şeyi hâlâ koruyor mu?

    Önceki manifest tek-parça TAŞIYOR ama yerelde `base.zip` YOK → taze katmanlar bayat
    bir monolitle aynı sürüm altında yayınlanırdı. Kapı DURMALI.

    ⚠️ Bu iddia olmadan 1. testi geçirmenin en kolay yolu kapıyı tamamen silmek olurdu —
    ve o, 53 dosyalık ayrışmayı geri getirirdi.
    """
    _manifest_yaz(
        tmp_path,
        runtimes={"win-x64": {"url": "https://x/base.zip", "sha256": "d" * 64, "size": 10}},
    )
    _paketleri_koy(tmp_path, monolit=False)
    r = _kos(tmp_path)
    assert r.returncode != 0, "BAYAT monolit tasinirken manifest YAZILDI -> iki farkli yazilim"
    assert "İKİ FARKLI" in r.stderr or "IKI FARKLI" in r.stderr, f"beklenen gerekce yok:\n{r.stderr[-800:]}"


def test_KRITIK_monolit_de_TAZEYKEN_uretilir(tmp_path):
    """Üçü de yerelde taze → sorun yok, manifest yazılır (eski dünya hâlâ çalışır)."""
    _manifest_yaz(
        tmp_path,
        runtimes={"win-x64": {"url": "https://x/base.zip", "sha256": "d" * 64, "size": 10}},
    )
    _paketleri_koy(tmp_path, monolit=True)
    r = _kos(tmp_path)
    assert r.returncode == 0, "uc paket de tazeyken manifest uretilemedi:\n" + r.stderr[-1500:]
