# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""[PETRİ KARE] KABİN KAMERASI KARE TOPLAYICI — petri kuyu dedektörünün (YOLO) yeniden eğitimi ve ızgara eşiklerinin ölçülmesi için
(AP · B8, istem 48 · sahip kararı S-AP.8 "ayrı betik").

NEDEN (13-11 tezgâhı, `DENETIM\\AIPRO-INCELEME.md` AP-8): bu kabinde YOLO kuyu adayı bulmuyor (95 karenin 87'sinde 0 aday) ve ince
hizalama (ECC, pembe besiyeri maskesi) düşüyor → koşullu kip hiç sürmüyor. YOLO tek petri KABI veri setiyle eğitildi ve ONNX 640'a sabit;
kabin karesinde kuyu ~24 px. Eşik / ön işleme kabinin RENKLİ karesi ölçülmeden değiştirilemez (yanlış plaka kabulü = sahte sürüş). Bu
betik o kareleri toplar; EĞİTİM YAPMAZ.

KULLANIM — UYGULAMA KAPALIYKEN (AI Pro / analiz kamerayı tutarken kamera açılmaz):
    python scripts\\petri_kare_topla.py                          # 60 kare, 2 sn arayla → Masaüstü\\PEMF_petri_kareleri_<tarih>
    python scripts\\petri_kare_topla.py --adet 120 --aralik 1.5  # daha çok kare
    python scripts\\petri_kare_topla.py --cikti D:\\kareler        # çıktı klasörünü sen ver
    python scripts\\petri_kare_topla.py --tanisiz                # yalnız kare (ızgara tanısı yok, daha hızlı)

Çıktı: `kare_0001.png …` (seçili KABİN kamerası, kabin kalibrasyonunun çözünürlüğü, renkli, kayıpsız) + `tani.csv` (kare başına ürünle
AYNI petri ızgara hattının tanısı: YOLO aday, doğrulanan kuyu, ECC, uyum skoru, uyarı kodları, pembe maske oranı, ortalama parlaklık).
Kareler arasında plakayı / ışığı / kuyu dolumunu değiştir (liste: `DENETIM\\ODAK.md` "Tezgâhta yapılacak").
Pencere AÇMAZ · ağa ÇIKMAZ (modeller yerel model katmanından; YOLO yoksa tanı Hough + ECC ile) · veri köküne (`ProgramData\\PEMF_System\\PEMF_GUI`)
YAZMAZ — çıktı orada istenirse reddeder.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ONEK = "[PETRİ KARE]"
ISINMA = 5
TANI_ALANLARI = (
    "kare",
    "zaman",
    "genislik",
    "yukseklik",
    "plaka",
    "yolo_aday",
    "dogrulanan",
    "ecc",
    "uyum",
    "uyarilar",
    "pembe_oran",
    "parlaklik",
)


def _kok() -> Path:
    return Path(__file__).resolve().parents[1]


def _yollari_kur() -> None:
    """Depo kökü (`ai_hub`) + `apps/backend` (`utils`) içe aktarılabilsin (betik depo dışından da çağrılabilir)."""
    for p in (_kok(), _kok() / "apps" / "backend"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def veri_koku_altinda_mi(yol: Path, veri_koku: Path) -> bool:
    try:
        Path(yol).resolve().relative_to(Path(veri_koku).resolve())
        return True
    except ValueError:
        return False


def varsayilan_cikti(simdi: datetime | None = None) -> Path:
    return Path.home() / "Desktop" / f"PEMF_petri_kareleri_{(simdi or datetime.now()).strftime('%Y%m%d_%H%M%S')}"


def png_yaz(yol: Path, kare, cv2) -> None:
    """Unicode-güvenli kayıpsız yazım (OpenCV `imwrite` ASCII dışı yolda sessizce düşer — AII-3.11 dersi)."""
    ok, tampon = cv2.imencode(".png", kare)
    if not ok:
        raise RuntimeError(f"kare kodlanamadı: {yol.name}")
    yol.write_bytes(tampon.tobytes())


def yolo_kur():
    """Ürünün petri YOLO'sunu YEREL model katmanından çöz (indirme YOK); yoksa None (tanı Hough + ECC ile).
    Dosya YOKSA petri paketi HİÇ içe aktarılmaz: paket içe aktarımı ürünün öteki petri modellerini de çözer (gereksiz yük; testte sahte
    yolu süreçteki sonraki petri testlerine taşıyordu)."""
    try:
        from utils.model_downloader import yan_dosya_coz

        goreli = "ai_hub/inference_petri_dish/yolo11m-seg.onnx"
        yol = yan_dosya_coz(str(_kok() / goreli), goreli)
        if not os.path.isfile(yol):
            print(f"{ONEK} YOLO modeli yerelde yok ({goreli}) — tanı YOLO'suz (Hough + ECC).")
            return None
        from ai_hub.inference_petri_dish.petri_cv_v2.petri_detector import PetriYoloDetector

        return PetriYoloDetector(yol, device="cpu")
    except Exception as e:  # noqa: BLE001 — tanı yardımcıdır; neden ekrana
        print(f"{ONEK} YOLO yüklenemedi ({type(e).__name__}: {e}) — tanı YOLO'suz (Hough + ECC).")
        return None


def tani_kur(yolo):
    """Kare → tanı sözlüğü (ürünün `detect_plate_wells` hattı, 24'lük plaka)."""
    import numpy as np

    from ai_hub.inference_petri_dish.petri_cv_v2 import plate_grid as pg

    def _tani(kare) -> dict:
        r = pg.detect_plate_wells(kare, 24, yolo=yolo)
        pembe = pg.medium_mask(kare)
        return {
            "plaka": bool(getattr(r, "success", False)),
            "yolo_aday": int(getattr(r, "n_yolo_candidates", 0) or 0),
            "dogrulanan": int(getattr(r, "n_inliers", 0) or 0),
            "ecc": bool(getattr(r, "ecc_ok", False)),
            "uyum": round(float(getattr(r, "fit_score", 0.0) or 0.0), 3),
            "uyarilar": " ".join(str(u).split(":")[0] for u in (getattr(r, "warnings", None) or []))
            or getattr(r, "error", "")
            or "",
            "pembe_oran": round(float(np.count_nonzero(pembe)) / float(pembe.size or 1), 4),
            "parlaklik": round(float(np.mean(kare)), 1),
        }

    return _tani


def topla(
    cap, adet: int, aralik_s: float, cikti: Path, tani=None, cv2=None, uyu=time.sleep, saat=datetime.now
) -> list[dict]:
    """Açık kameradan `adet` kare → `cikti` (PNG + `tani.csv`). Okunamayan kare atlanır (en çok 3 × adet deneme)."""
    if cv2 is None:
        import cv2
    cikti.mkdir(parents=True, exist_ok=True)
    satirlar: list[dict] = []
    deneme = 0
    with open(cikti / "tani.csv", "w", newline="", encoding="utf-8") as fh:
        yazar = csv.DictWriter(fh, fieldnames=TANI_ALANLARI)
        yazar.writeheader()
        while len(satirlar) < adet and deneme < 3 * adet:
            deneme += 1
            ok, kare = cap.read()
            if not ok or kare is None:
                uyu(0.2)
                continue
            no = len(satirlar) + 1
            ad = f"kare_{no:04d}.png"
            png_yaz(cikti / ad, kare, cv2)
            s = {
                "kare": ad,
                "zaman": saat().isoformat(timespec="seconds"),
                "genislik": kare.shape[1],
                "yukseklik": kare.shape[0],
            }
            if tani is not None:
                try:
                    s.update(tani(kare))
                except Exception as e:  # noqa: BLE001 — tanı hatası kareyi düşürmez
                    s["uyarilar"] = f"tani_hatasi: {type(e).__name__}"
            yazar.writerow({k: s.get(k, "") for k in TANI_ALANLARI})
            fh.flush()
            satirlar.append(s)
            print(
                f"{ONEK} {ad} {s.get('genislik')}×{s.get('yukseklik')} aday={s.get('yolo_aday', '-')} "
                f"dogrulanan={s.get('dogrulanan', '-')} ecc={s.get('ecc', '-')}"
            )
            if len(satirlar) < adet:
                uyu(aralik_s)
    return satirlar


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Kabin kamerasından petri kareleri topla (YOLO eğitimi / eşik ölçümü için)."
    )
    ap.add_argument("--adet", type=int, default=60)
    ap.add_argument("--aralik", type=float, default=2.0, help="kareler arası saniye")
    ap.add_argument("--cikti", type=Path, default=None)
    ap.add_argument("--tanisiz", action="store_true", help="ızgara tanısı yapma (yalnız kare)")
    a = ap.parse_args(argv)
    _yollari_kur()
    import cv2
    from utils import kabin_kamerasi
    from utils.path_utils import get_app_data_directory

    cikti = a.cikti or varsayilan_cikti()
    if veri_koku_altinda_mi(cikti, Path(get_app_data_directory())):
        print(f"{ONEK} !!! çıktı veri kökünün altında olamaz: {cikti} — Masaüstü ya da başka bir klasör verin.")
        return 2
    try:
        cap, indeks = kabin_kamerasi.kamera_ac(cv2)
    except kabin_kamerasi.KameraSecilmedi as e:
        print(f"{ONEK} !!! {kabin_kamerasi.secim_hatasi_metni(e)}")
        return 3
    try:
        if not cap.isOpened():
            print(
                f"{ONEK} !!! kabin kamerası (indeks {indeks}) açılamadı — uygulama AI Pro / analiz için kamerayı tutuyor olabilir; "
                "uygulamayı kapatıp yeniden deneyin."
            )
            return 4
        for _ in range(ISINMA):
            cap.read()
        tani = None if a.tanisiz else tani_kur(yolo_kur())
        print(f"{ONEK} {a.adet} kare, {a.aralik:g} sn arayla → {cikti}")
        satirlar = topla(cap, max(1, a.adet), max(0.0, a.aralik), cikti, tani=tani, cv2=cv2)
    finally:
        cap.release()
    print(f"{ONEK} bitti: {len(satirlar)} kare + tani.csv → {cikti}")
    return 0 if satirlar else 5


if __name__ == "__main__":
    sys.exit(main())
