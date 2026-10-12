# -*- coding: utf-8 -*-
"""AII-1.4 (AI incelemesi, A1) — A2 "tek uygulama" kapısı yalnız BAYT-AYNI kopyayı görüyordu (KÖR KAPI).

ÖLÇÜLDÜ (`tests/test_cv_ortak_tek_uygulama.py`, SHA-256 ile grup): `cv_ortak/coord_transform.py`'nin başına guii'nin yazar
satırı (`# Author: …` — guii her dosyaya ekler) konup `petri_cv_v2/coord_transform_kopya.py` olarak, hocanın KENDİ
`phantom_cv_v3/cabin_config.py`'si (425 satır, ikinci CabinConfig uygulaması) `cabin_config_hoca_kopya.py` olarak diske konunca
kapı 18/18 YEŞİL kaldı; yalnız bayt-aynı kopya (karşıt) kırmızı. Hocanın bir sonraki teslimi tam bu biçimde gelir (kendi
`cabin_config.py` / `coord_transform.py` kopyaları) ve guii'nin yazar başlığı kuralı bayt eşitliğini kendiliğinden bozar → plan
§3.4'ün "kopya alınmaz" kuralı ölçülmüyordu.

Kapı (DOSYA SİSTEMİNDEN, git ls-files değil — A2'nin 2026-09-19 dersi):
  1. AD/AST: v2 / v3 profil dizinlerinde `cv_ortak` (cabin_config, coord_transform) üst düzey adlarından biri TANIMLANAMAZ
     (tek istisna: kabuğun `load_cabin_config` sarmalayıcısı — profil varsayılanını geçirir);
  2. NORMALİZE KOPYA: yorum / boş satır / satır sonu farkı atılınca `cv_ortak` gövdesiyle AYNI olan dosya ai_hub'da yok.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
ORTAK = ("cabin_config", "coord_transform")
PROFILLER = ("ai_hub/inference_em_fantom/phantom_cv_v3", "ai_hub/inference_petri_dish/petri_cv_v2")
#: Kabuk sarmalayıcısı — profil varsayılan YAML'ını ve MQTT kimliğini ortak yükleyiciye geçirir (gövde değil).
IZINLI = {("cabin_config.py", "load_cabin_config")}


def _ust_duzey(p: Path) -> set[str]:
    agac = ast.parse(p.read_text(encoding="utf-8"))
    return {n.name for n in agac.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _ortak_adlar() -> set[str]:
    out: set[str] = set()
    for m in ORTAK:
        out |= _ust_duzey(KOK / "ai_hub" / "cv_ortak" / f"{m}.py")
    assert len(out) >= 20, f"cv_ortak tanımları okunamadı ({len(out)}) — kapı boş dönerdi"
    return out


def _normalize(p: Path) -> str:
    satirlar = []
    for s in p.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n"):
        t = s.strip()
        if not t or t.startswith("#"):
            continue
        satirlar.append(s.rstrip())
    return "\n".join(satirlar)


def test_KRITIK_profil_dizinlerinde_cv_ortak_ADI_ikinci_kez_TANIMLANMAZ():
    ortak = _ortak_adlar()
    ihlal = []
    taranan = 0
    for d in PROFILLER:
        for p in sorted((KOK / d).rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            taranan += 1
            for ad in sorted(_ust_duzey(p) & ortak):
                if (p.name, ad) not in IZINLI:
                    ihlal.append(f"{p.relative_to(KOK).as_posix()}::{ad}")
    assert taranan >= 16, f"tarama dar ({taranan}) — kapı boş dönüyor olabilir"
    assert not ihlal, (
        "cv_ortak'ın tanımı profil dizininde İKİNCİ KEZ var (yakın kopya / ikinci uygulama):\n  " + "\n  ".join(ihlal)
    )


def test_KRITIK_ai_hub_altinda_cv_ortak_govdesinin_NORMALIZE_kopyasi_YOK():
    hedef = {hashlib.sha256(_normalize(KOK / "ai_hub" / "cv_ortak" / f"{m}.py").encode()).hexdigest(): m for m in ORTAK}
    bulunan = []
    for p in sorted((KOK / "ai_hub").rglob("*.py")):
        if "__pycache__" in p.parts or p.parent.name == "cv_ortak":
            continue
        h = hashlib.sha256(_normalize(p).encode()).hexdigest()
        if h in hedef:
            bulunan.append(f"{p.relative_to(KOK).as_posix()} == cv_ortak/{hedef[h]}.py")
    assert not bulunan, "cv_ortak gövdesinin (yorum/boşluk farkıyla) kopyası:\n  " + "\n  ".join(bulunan)
