# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CI MODEL PAKETİ — testlerin istediği AI ağırlıkları / git-ignored eserler CI'a GİZLİ ANAHTARLA indirilir (KP-5 · Y279 · Y282).

NEDEN: CI-eşdeğeri (modelsiz) koşuda model / eser isteyen testler KIRMIZI (KP-4 [SAHİBE] 4 · KP5-LISTESI 13). Sahip kararı: CI'a model
KONUR, "eser yoksa atla" koruması YOK; ağırlıklar AÇIK DEPOYA GİRMEZ (Y279) — ODAK alan tablosu + ONNX modelleri de (Y282). Bu yüzden
paket depo DIŞINDA durur (özel bir GitHub sürüm varlığı); CI onu gizli anahtarla indirir, her dosyanın SHA-256'sını depodaki
listeyle (`scripts/ci_modelleri_listesi.json`) doğrular ve yerleştirir. İndirme / doğrulama düşerse ÇIKIŞ ≠ 0 → CI KIRMIZI.

KULLANIM:
    # sahip (yerelde, bir kez / modeller değişince): paketi kur, listeyi yaz
    python scripts/ci_modelleri.py paketle --modeller <release_assets/ai_models> --cikti <pemf_ci_modelleri.zip>
    # CI: indir + doğrula + yerleştir (PEMF_AI_MODELS_DIR'i GITHUB_ENV'e yazar)
    python scripts/ci_modelleri.py indir --hedef <dizin> [--github-env $GITHUB_ENV] [--yerel-zip <zip>]

LİSTE (`ci_modelleri_listesi.json`): {"kaynak": {...}, "dosyalar": [{"yol": "<kök>/<göreli>", "sha256": "..."}]} — kök `modeller/`
(→ PEMF_AI_MODELS_DIR altına; ürünün model kökü düzeni) ya da `depo/` (→ depo köküne; testlerin depo içinde aradığı git-ignored eserler,
ör. `ai_hub/PEMF_AI_Test_Girdileri/`). Zip içindeki yol listedekiyle AYNI.
KAYNAK: ortam `PEMF_CI_MODEL_KAYNAGI` (yoksa listedeki `kaynak.url`) — GitHub sürüm varlığı API adresi
(`https://api.github.com/repos/<sahip>/<depo>/releases/assets/<kimlik>`) ya da herhangi bir https adresi. Anahtar ortamda
(`PEMF_CI_MODEL_ANAHTARI`) varsa `Authorization: Bearer` gönderilir; yoksa anahtarsız denenir (kaynak herkese açıksa yeter).
Anahtar DEĞERİ hiçbir zaman basılmaz.
ÇIKIŞ: 0 = tamam · 1 = indirme / doğrulama / yerleştirme hatası · 2 = kullanım / liste hatası.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

KOK = Path(__file__).resolve().parents[1]
LISTE = KOK / "scripts" / "ci_modelleri_listesi.json"
KOKLER = ("modeller", "depo")


def _sha256(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            h.update(parca)
    return h.hexdigest()


def _guvenli_goreli(yol: str) -> tuple[str, PurePosixPath]:
    """Liste / zip yolunu (kök, göreli) ayırır; mutlak yol, `..`, ters bölü, bilinmeyen kök → ValueError (zip-slip savunması)."""
    if "\\" in yol or yol.startswith("/") or ":" in yol:
        raise ValueError(f"güvensiz yol: {yol!r}")
    p = PurePosixPath(yol)
    if any(parca in ("..", "") for parca in p.parts) or len(p.parts) < 2 or p.parts[0] not in KOKLER:
        raise ValueError(f"güvensiz / köksüz yol: {yol!r}")
    return p.parts[0], PurePosixPath(*p.parts[1:])


def liste_oku(yol: Path = LISTE) -> dict:
    veri = json.loads(yol.read_text(encoding="utf-8"))
    dosyalar = veri.get("dosyalar")
    if not isinstance(dosyalar, list) or not dosyalar:
        raise ValueError("listede dosya yok")
    gorulen = set()
    for d in dosyalar:
        _guvenli_goreli(d["yol"])
        if len(d.get("sha256", "")) != 64 or d["yol"] in gorulen:
            raise ValueError(f"liste kaydı geçersiz / çift: {d.get('yol')!r}")
        gorulen.add(d["yol"])
    return veri


def paketle(modeller: Path, depo: Path, cikti: Path, liste_yolu: Path = LISTE) -> int:
    """Listedeki HER dosyayı kaynağından (modeller/ → `modeller`, depo/ → `depo`) zip'e koyar ve listedeki özetleri YENİLER."""
    veri = liste_oku(liste_yolu)
    with zipfile.ZipFile(cikti, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for d in veri["dosyalar"]:
            kok, goreli = _guvenli_goreli(d["yol"])
            kaynak = (modeller if kok == "modeller" else depo) / Path(*goreli.parts)
            if not kaynak.is_file():
                print(f"!!! kaynak yok: {d['yol']} ({kaynak})")
                return 1
            d["sha256"] = _sha256(kaynak)
            d["bayt"] = kaynak.stat().st_size
            z.write(kaynak, d["yol"])
    liste_yolu.write_text(json.dumps(veri, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"paket: {cikti} · {len(veri['dosyalar'])} dosya · liste özetleri yazıldı ({liste_yolu.name})")
    return 0


def _indir(url: str, hedef: Path, anahtar: str | None, ac=urllib.request.urlopen) -> None:
    istek = urllib.request.Request(
        url, headers={"Accept": "application/octet-stream", "User-Agent": "pemf-ci-modelleri"}
    )
    if anahtar:
        istek.add_header("Authorization", f"Bearer {anahtar}")
    with ac(istek, timeout=600) as yanit, open(hedef, "wb") as f:
        shutil.copyfileobj(yanit, f)


def yerlestir(zip_yolu: Path, hedef: Path, depo: Path, veri: dict) -> list[str]:
    """Zip'i listeye göre doğrulayıp yerleştirir; sorun listesini döner (boş = tamam). Listede olmayan zip girdisi YOK sayılmaz → sorun."""
    sorun = []
    beklenen = {d["yol"]: d["sha256"] for d in veri["dosyalar"]}
    with zipfile.ZipFile(zip_yolu) as z:
        adlar = [i.filename for i in z.infolist() if not i.is_dir()]
        for ad in adlar:
            if ad not in beklenen:
                sorun.append(f"listede olmayan girdi: {ad}")
        for yol, ozet in beklenen.items():
            if yol not in adlar:
                sorun.append(f"pakette yok: {yol}")
                continue
            kok, goreli = _guvenli_goreli(yol)
            cikis = (hedef if kok == "modeller" else depo) / Path(*goreli.parts)
            cikis.parent.mkdir(parents=True, exist_ok=True)
            with z.open(yol) as kaynak, open(cikis, "wb") as f:
                shutil.copyfileobj(kaynak, f)
            if _sha256(cikis) != ozet:
                sorun.append(f"SHA-256 uyuşmuyor: {yol}")
    return sorun


def indir(
    hedef: Path,
    depo: Path,
    github_env: str | None,
    yerel_zip: Path | None,
    ac=urllib.request.urlopen,
    liste_yolu: Path = LISTE,
) -> int:
    veri = liste_oku(liste_yolu)
    hedef.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as gecici:
        zip_yolu = yerel_zip
        if zip_yolu is None:
            url = os.environ.get("PEMF_CI_MODEL_KAYNAGI") or veri.get("kaynak", {}).get("url", "")
            if not url.startswith("https://"):
                print("!!! model kaynağı yok / https değil (PEMF_CI_MODEL_KAYNAGI ya da liste `kaynak.url`)")
                return 1
            anahtar = os.environ.get("PEMF_CI_MODEL_ANAHTARI") or None
            print(f"indiriliyor: {url} · anahtar {'VAR' if anahtar else 'YOK (anahtarsız deneme)'}")
            zip_yolu = Path(gecici) / "paket.zip"
            try:
                _indir(url, zip_yolu, anahtar, ac)
            except OSError as e:  # urllib.error.URLError / HTTPError OSError'dur
                print(f"!!! indirilemedi: {type(e).__name__}: {e}")
                return 1
        try:
            sorun = yerlestir(zip_yolu, hedef, depo, veri)
        except (zipfile.BadZipFile, OSError, ValueError) as e:
            print(f"!!! paket açılamadı: {type(e).__name__}: {e}")
            return 1
    if sorun:
        print(f"!!! {len(sorun)} sorun:\n  " + "\n  ".join(sorun[:20]))
        return 1
    if github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"PEMF_AI_MODELS_DIR={hedef}\n")
    print(f"tamam: {len(veri['dosyalar'])} dosya doğrulandı · PEMF_AI_MODELS_DIR={hedef}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CI model paketi (KP-5 · Y279 · Y282)")
    alt = ap.add_subparsers(dest="komut", required=True)
    p = alt.add_parser("paketle")
    p.add_argument("--modeller", required=True, type=Path)
    p.add_argument("--depo", default=KOK, type=Path)
    p.add_argument("--cikti", required=True, type=Path)
    i = alt.add_parser("indir")
    i.add_argument("--hedef", required=True, type=Path)
    i.add_argument("--depo", default=KOK, type=Path)
    i.add_argument("--github-env")
    i.add_argument("--yerel-zip", type=Path)
    a = ap.parse_args(argv)
    try:
        if a.komut == "paketle":
            return paketle(a.modeller, a.depo, a.cikti, LISTE)
        return indir(a.hedef, a.depo, a.github_env, a.yerel_zip, liste_yolu=LISTE)
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"!!! liste hatası: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
