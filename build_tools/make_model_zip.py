# Author: mertaygn, cglrgrkn
"""make_model_zip.py — Profil model paketlerini (`home/vet/research.zip`) üretir.

NEDEN VAR (2026-08-10). Bu paketler daha önce ELLE üretiliyordu; içerikleri hiçbir yerde
yazılı değildi. `inference_cat_organ` modellerinin `home.zip` içinde olduğu ancak yayındaki
zip'in merkezî dizini uzaktan okunarak keşfedildi ve "Veteriner profili Ev Sahibi'ne
bağımlı" hatasının kaynağı buydu. İçerik artık KODDA tek-kaynak.

ÇEKİRDEK MODEL KURALI. `inference_cat_organ` (AI Pro organ lokalizasyonu) ÇEKİRDEĞE alındı
(`make_base_zip.py::CORE_MODELS` → deps katmanı → frozen bundle). Bu yüzden profil
paketlerinde YER ALMAZ — aksi hâlde ev sahibi kullanıcı aynı ~209 MB'ı İKİ KEZ indirir.
Çözüm sırası dosya-başınadır (`utils/model_downloader.find_installed_model`), yani paketten
çıkarmak hiçbir profilde özelliği bozmaz; bkz. `tests/test_cekirdek_model_cozumu.py`.

Kullanım:  python build_tools/make_model_zip.py [home|vet|research] ...
           (argümansız → hepsi)
"""

from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KAYNAK = KOK / "release_assets" / "ai_models"
CIKTI = KOK / "pemf-app-packages"

# Deterministik zip: aynı girdi → aynı sha256. make_base_zip.py ile AYNI sabit.
SABIT_TARIH = (1980, 1, 1, 0, 0, 0)

# ⚠️ ÇEKİRDEKTE olan modeller — hiçbir profil paketine GİRMEZ (bkz. modül docstring'i).
CEKIRDEK_HARIC = ("ai_hub/inference_cat_organ/",)

# Profil → paket içeriği. Yollar `release_assets/ai_models` köküne GÖRELİ ve zip içinde
# `ai_models/<yol>` olarak yer alır (launcher `install_root/ai_models` altına açar;
# bkz. launcher/core/src/install.rs::models_dir).
PROFILLER: dict[str, tuple[str, ...]] = {
    # 2026-08-10 öncesi yayındaki home.zip 11 dosyaydı; 3 cat_organ ONNX'i ÇEKİRDEĞE taşındı.
    "home": (
        "ai_hub/cat_landmark/thresholds_calibrated.json",
        "ai_hub/cat_landmark/yolo26m-pose.onnx",
        "ai_hub/cat_segmentation/yolov8m-seg.onnx",
        "ai_hub/inference_cat_sound/EfficientNet_Lite0.onnx",
        "ai_hub/cat_disease/label_encoder.pkl",
        "ai_hub/cat_disease/scaler_X.pkl",
        "ai_hub/cat_disease/XGBoost.onnx",
        "ai_hub/cat_disease/XGBoost.pkl",
    ),
}


def dosyalari_topla(profil: str) -> list[tuple[Path, str]]:
    ciftler: list[tuple[Path, str]] = []
    for rel in PROFILLER[profil]:
        if rel.startswith(CEKIRDEK_HARIC):
            raise SystemExit(
                f"[HATA] '{rel}' CEKIRDEKTE — profil paketine konulamaz (cift indirme). "
                "Cekirdek modeller make_base_zip.py::CORE_MODELS ile paketlenir."
            )
        src = KAYNAK / rel
        if not src.is_file():
            raise SystemExit(f"[HATA] kaynak yok: {src}")
        ciftler.append((src, f"ai_models/{rel}"))
    return ciftler


def zip_yaz(profil: str) -> Path:
    ciftler = dosyalari_topla(profil)
    CIKTI.mkdir(parents=True, exist_ok=True)
    hedef = CIKTI / f"{profil}.zip"
    # ONNX/pkl zaten sıkışık; ZIP_STORED hem hızlı hem yayındaki paketlerle aynı boyut sınıfı.
    with zipfile.ZipFile(hedef, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for src, arc in ciftler:
            zi = zipfile.ZipInfo(arc, date_time=SABIT_TARIH)
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr = 0o644 << 16
            with open(src, "rb") as fh:
                z.writestr(zi, fh.read())
    return hedef


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dogrula(profil: str, hedef: Path) -> bool:
    with zipfile.ZipFile(hedef) as z:
        adlar = z.namelist()
    kapilar = {
        "cekirdek model YOK (cift indirme onlendi)": not any("inference_cat_organ" in n for n in adlar),
        "dosya sayisi beklenen": len(adlar) == len(PROFILLER[profil]),
        "hepsi ai_models/ onekli": all(n.startswith("ai_models/") for n in adlar),
    }
    ok = True
    for ad, gecti in kapilar.items():
        print(f"  [{'OK' if gecti else 'HATA'}] {ad}")
        ok = ok and gecti
    return ok


def main(argv: list[str]) -> int:
    istenen = argv or list(PROFILLER)
    bilinmeyen = [p for p in istenen if p not in PROFILLER]
    if bilinmeyen:
        print(f"[HATA] tanimsiz profil: {', '.join(bilinmeyen)}  (var: {', '.join(PROFILLER)})")
        return 2
    tamam = True
    for profil in istenen:
        hedef = zip_yaz(profil)
        boyut = hedef.stat().st_size
        print(f"\n{profil}.zip : {boyut} bayt ({boyut / 1e6:.1f} MB)  sha256 {sha256(hedef)}")
        tamam = dogrula(profil, hedef) and tamam
    print(f"\nVALIDATION: {'PASS' if tamam else 'FAIL'}")
    return 0 if tamam else 1


if __name__ == "__main__":
    raise SystemExit(main([a for a in sys.argv[1:] if not a.startswith("-")]))
