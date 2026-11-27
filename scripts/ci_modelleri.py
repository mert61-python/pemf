# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CI MODEL PAKETİ — testlerin istediği AI ağırlıkları / git-ignored eserler CI'a GİZLİ ANAHTARLA indirilir (KP-5 · Y279 · Y282).

NEDEN: CI-eşdeğeri (modelsiz) koşuda model / eser isteyen testler KIRMIZI (KP-4 [SAHİBE] 4 · KP5-LISTESI 13). Sahip kararı: CI'a model
KONUR, "eser yoksa atla" koruması YOK; ağırlıklar AÇIK DEPOYA GİRMEZ (Y279) — ODAK alan tablosu + ONNX modelleri de (Y282). Bu yüzden
paket depo DIŞINDA durur (özel bir GitHub sürüm varlığı); CI onu gizli anahtarla indirir, her dosyanın SHA-256'sını depodaki
listeyle (`scripts/ci_modelleri_listesi.json`) doğrular ve yerleştirir. İndirme / doğrulama düşerse ÇIKIŞ ≠ 0 → CI KIRMIZI.

KULLANIM:
    # sahip (yerelde, bir kez / modeller değişince): paketi kur, listeyi yaz
    python scripts/ci_modelleri.py paketle --modeller <release_assets/ai_models> --cikti <pemf_ci_modelleri.zip> [--parca-mb 1900]
    # CI: indir + doğrula + yerleştir (PEMF_AI_MODELS_DIR'i GITHUB_ENV'e yazar)
    python scripts/ci_modelleri.py indir --hedef <dizin> [--github-env $GITHUB_ENV] [--yerel-zip <zip|parça…>] [--onbellek <dizin>]

PARÇALI PAKET (CT1 b, istem 66): tam ağırlık ağacı ~4,2 GB, GitHub sürüm varlığı dosya başına 2 GiB → `paketle` paketi ≤ 1900 MiB
parçalara böler (her dosya tek parçada) ve parça adı / SHA-256 / baytı listeye (`paket.parcalar`) yazar. Kaynak değişkeni
(`PEMF_CI_MODEL_KAYNAGI`) parça varlık adreslerini BOŞLUKLA ayrılmış taşır; adres sayısı ≠ parça sayısı ya da listede olmayan parça
özeti → çıkış 1.

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
#: CT1 b: GitHub sürüm varlığı sınırı 2 GiB / dosya — zip başlıkları ve sıkıştırılamayan veri için ~148 MiB pay.
PARCA_UST = 1900 * 1024 * 1024


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


def _parcalara_bol(ogeler: list[tuple[dict, Path, int]], ust: int) -> list[list[tuple[dict, Path, int]]]:
    """İlk-uyan-azalan: büyükten küçüğe, sığdığı ilk parçaya (parça başına açılmış toplam ≤ `ust`)."""
    kutular: list[list] = []  # [toplam, [öğe…]]
    for oge in sorted(ogeler, key=lambda o: -o[2]):
        for k in kutular:
            if k[0] + oge[2] <= ust:
                k[0] += oge[2]
                k[1].append(oge)
                break
        else:
            kutular.append([oge[2], [oge]])
    return [k[1] for k in kutular]


def paketle(modeller: Path, depo: Path, cikti: Path, liste_yolu: Path = LISTE, parca_ust: int = PARCA_UST) -> int:
    """Listedeki HER dosyayı kaynağından (modeller/ → `modeller`, depo/ → `depo`) zip'e koyar ve listedeki özetleri YENİLER.

    CT1 b: GitHub sürüm varlığı dosya başına 2 GiB → paket `parca_ust` baytlık PARÇALARA bölünür (tek parçaysa ad `cikti`, değilse
    `<ad>_1.zip`, `<ad>_2.zip` …); her dosya tek parçada. Parça adı / SHA-256 / bayt listeye (`paket.parcalar`) yazılır — `indir`
    bunlarla doğrular. Sınırı tek başına aşan dosya → çıkış 1 (hiçbir parça yazılmaz)."""
    veri = liste_oku(liste_yolu)
    ogeler = []
    for d in veri["dosyalar"]:
        kok, goreli = _guvenli_goreli(d["yol"])
        kaynak = (modeller if kok == "modeller" else depo) / Path(*goreli.parts)
        if not kaynak.is_file():
            print(f"!!! kaynak yok: {d['yol']} ({kaynak})")
            return 1
        bayt = kaynak.stat().st_size
        if bayt > parca_ust:
            print(f"!!! parça sınırını aşan dosya ({bayt} > {parca_ust} bayt; GitHub varlığı 2 GiB): {d['yol']}")
            return 1
        ogeler.append((d, kaynak, bayt))
    kutular = _parcalara_bol(ogeler, parca_ust)
    adlar = (
        [cikti]
        if len(kutular) == 1
        else [cikti.with_name(f"{cikti.stem}_{i}{cikti.suffix}") for i in range(1, len(kutular) + 1)]
    )
    parcalar = []
    for ad, kutu in zip(adlar, kutular):
        with zipfile.ZipFile(ad, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            for d, kaynak, bayt in sorted(kutu, key=lambda o: o[0]["yol"]):
                d["sha256"] = _sha256(kaynak)
                d["bayt"] = bayt
                z.write(kaynak, d["yol"])
        parcalar.append({"ad": ad.name, "sha256": _sha256(ad), "bayt": ad.stat().st_size, "dosya": len(kutu)})
    veri["paket"] = {"parca_ust_bayt": parca_ust, "parcalar": parcalar}
    liste_yolu.write_text(json.dumps(veri, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(
        f"paket: {len(parcalar)} parça ({', '.join(p['ad'] for p in parcalar)}) · {len(veri['dosyalar'])} dosya · "
        f"liste özetleri yazıldı ({liste_yolu.name})"
    )
    return 0


def _indir(url: str, hedef: Path, anahtar: str | None, ac=urllib.request.urlopen) -> None:
    istek = urllib.request.Request(
        url, headers={"Accept": "application/octet-stream", "User-Agent": "pemf-ci-modelleri"}
    )
    if anahtar:
        istek.add_header("Authorization", f"Bearer {anahtar}")
    with ac(istek, timeout=600) as yanit, open(hedef, "wb") as f:
        shutil.copyfileobj(yanit, f)


def yerlestir(zip_yolu, hedef: Path, depo: Path, veri: dict) -> list[str]:
    """Zip(ler)i listeye göre doğrulayıp yerleştirir; sorun listesini döner (boş = tamam). `zip_yolu` tek yol ya da parça listesi (CT1 b).
    Listede olmayan girdi, iki parçada birden bulunan girdi ve hiçbir parçada olmayan liste kaydı YOK sayılmaz → sorun."""
    zipler = [zip_yolu] if isinstance(zip_yolu, (str, Path)) else list(zip_yolu)
    sorun = []
    beklenen = {d["yol"]: d["sha256"] for d in veri["dosyalar"]}
    gorulen: set[str] = set()
    for zp in zipler:
        with zipfile.ZipFile(zp) as z:
            for ad in [i.filename for i in z.infolist() if not i.is_dir()]:
                if ad not in beklenen:
                    sorun.append(f"listede olmayan girdi: {ad}")
                    continue
                if ad in gorulen:
                    sorun.append(f"birden çok parçada: {ad}")
                    continue
                gorulen.add(ad)
                kok, goreli = _guvenli_goreli(ad)
                cikis = (hedef if kok == "modeller" else depo) / Path(*goreli.parts)
                cikis.parent.mkdir(parents=True, exist_ok=True)
                with z.open(ad) as kaynak, open(cikis, "wb") as f:
                    shutil.copyfileobj(kaynak, f)
                if _sha256(cikis) != beklenen[ad]:
                    sorun.append(f"SHA-256 uyuşmuyor: {ad}")
    sorun += [f"pakette yok: {yol}" for yol in beklenen if yol not in gorulen]
    return sorun


def _parcalari_getir(veri: dict, dizin: Path, onbellekli: bool, ac) -> list[Path] | None:
    """Kaynak adreslerinden (boşlukla ayrılmış; parça sayısı kadar) parçaları `dizin`e indirir. `onbellekli`: dizinde özeti listedeki
    parçalarla TUTAN dosyalar varsa (hepsi) indirme yapılmaz. Hata → ileti + None."""
    adresler = (os.environ.get("PEMF_CI_MODEL_KAYNAGI") or veri.get("kaynak", {}).get("url", "")).split()
    if not adresler or not all(a.startswith("https://") for a in adresler):
        print("!!! model kaynağı yok / https değil (PEMF_CI_MODEL_KAYNAGI ya da liste `kaynak.url`)")
        return None
    beklenen = {p["sha256"] for p in veri.get("paket", {}).get("parcalar", [])}
    if beklenen and len(adresler) != len(beklenen):
        print(
            f"!!! kaynakta {len(adresler)} adres var, paket {len(beklenen)} parça bekler "
            "(PEMF_CI_MODEL_KAYNAGI: parça varlık adresleri, boşlukla ayrılmış)"
        )
        return None
    dizin.mkdir(parents=True, exist_ok=True)
    if onbellekli and beklenen:
        hazir = {_sha256(p): p for p in sorted(dizin.glob("*.zip"))}
        if beklenen <= set(hazir):
            print(f"önbellekten: {len(beklenen)} parça (SHA-256 ✓) · indirme YOK")
            return [hazir[s] for s in sorted(beklenen)]
    anahtar = os.environ.get("PEMF_CI_MODEL_ANAHTARI") or None
    print(f"indiriliyor: {len(adresler)} parça · anahtar {'VAR' if anahtar else 'YOK (anahtarsız deneme)'}")
    yollar = []
    for i, url in enumerate(adresler, 1):
        yol = dizin / f"parca_{i}.zip"
        print(f"  {i}/{len(adresler)}: {url}")
        try:
            _indir(url, yol, anahtar, ac)
        except OSError as e:  # urllib.error.URLError / HTTPError OSError'dur
            print(f"!!! indirilemedi: {type(e).__name__}: {e}")
            return None
        yollar.append(yol)
    return yollar


def indir(
    hedef: Path,
    depo: Path,
    github_env: str | None,
    yerel_zip,
    ac=urllib.request.urlopen,
    liste_yolu: Path = LISTE,
    onbellek: Path | None = None,
) -> int:
    """`yerel_zip`: tek yol ya da parça listesi (yoksa adreslerden indirilir). `onbellek`: parçaların indirildiği / yeniden kullanıldığı
    dizin (CI'da actions/cache, anahtar = liste özeti) — verilmezse geçici dizin."""
    veri = liste_oku(liste_yolu)
    hedef.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as gecici:
        if yerel_zip is None:
            zipler = _parcalari_getir(veri, onbellek or Path(gecici), onbellek is not None, ac)
            if zipler is None:
                return 1
        else:
            zipler = [yerel_zip] if isinstance(yerel_zip, (str, Path)) else list(yerel_zip)
        beklenen = sorted(p["sha256"] for p in veri.get("paket", {}).get("parcalar", []))
        if beklenen and sorted(_sha256(Path(z)) for z in zipler) != beklenen:
            print(
                f"!!! parça SHA-256 listedekiyle (`paket.parcalar`, {len(beklenen)} parça) uyuşmuyor — eski / kurcalanmış paket"
            )
            return 1
        try:
            sorun = yerlestir(zipler, hedef, depo, veri)
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


def _konsol_utf8() -> None:
    """YS1a (Y320): GitHub `windows-latest` konsolu cp1252 → Türkçe "ğ / ı" yazımı `UnicodeEncodeError` ile çıkış 1 veriyordu (paket
    doğrulandıktan SONRA; `except` dalındaki yazım da düşüyordu). stdout / stderr UTF-8; yazılamayan karakter düşürmez, yerine '?' konur."""
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):  # konsolsuz süreçte None / yeniden yönlendirilmiş akış olabilir
            akis.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _konsol_utf8()
    ap = argparse.ArgumentParser(description="CI model paketi (KP-5 · Y279 · Y282)")
    alt = ap.add_subparsers(dest="komut", required=True)
    p = alt.add_parser("paketle")
    p.add_argument("--modeller", required=True, type=Path)
    p.add_argument("--depo", default=KOK, type=Path)
    p.add_argument("--cikti", required=True, type=Path)
    p.add_argument(
        "--parca-mb", type=int, default=PARCA_UST // (1024 * 1024), help="parça sınırı (MiB; GitHub varlığı 2 GiB)"
    )
    i = alt.add_parser("indir")
    i.add_argument("--hedef", required=True, type=Path)
    i.add_argument("--depo", default=KOK, type=Path)
    i.add_argument("--github-env")
    i.add_argument("--yerel-zip", type=Path, nargs="+", help="yerel paket ya da parçaları (indirme yok)")
    i.add_argument("--onbellek", type=Path, help="parça önbellek dizini (özeti tutan parça yeniden indirilmez)")
    a = ap.parse_args(argv)
    try:
        if a.komut == "paketle":
            return paketle(a.modeller, a.depo, a.cikti, LISTE, parca_ust=a.parca_mb * 1024 * 1024)
        return indir(a.hedef, a.depo, a.github_env, a.yerel_zip, liste_yolu=LISTE, onbellek=a.onbellek)
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"!!! liste hatası: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
