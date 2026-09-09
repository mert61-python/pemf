# Author: mertaygn, cglrgrkn
"""A4 basılabilir ArUco marker sayfası — PEMF kabin kalibrasyonu (DICT_5X5_50 · ID 0 · kenar 15,0 cm).

Neden ayrı bir sayfa: eski `PEMF_ArUco_Marker_5X5_50_ID0_10cm.png` DPI bilgisi taşımıyordu; yazıcı
sürücüsü/görüntüleyici "sayfaya sığdır" ile ölçeği bozunca marker istenen boyutta çıkmıyor, ölçek (mm/px)
ve dolayısıyla 3B konum yanlış oluyordu. Bu sayfa 300 DPI'da A4 boyutundadır: %100 (gerçek boyut)
basıldığında siyah karenin kenarı TAM `KENAR_CM` kadardır; altındaki cetvel çubuğu basımı doğrular.

Kendi kendini doğrular: üretilen sayfada marker cv2.aruco ile ID 0 olarak bulunur ve kenarı
`KENAR_CM × 118,11` px (±4) ölçülür; değilse çıkış 2.

Kullanım:
  python scripts/kabin_marker_a4.py                 # ai_hub/ altına PDF + PNG
  python scripts/kabin_marker_a4.py --masaustu      # + Masaüstü kopyası
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

KOK = Path(__file__).resolve().parents[1]
DPI = 300
PX_CM = DPI / 2.54  # 118.11 px/cm
A4_PX = (int(round(21.0 * PX_CM)), int(round(29.7 * PX_CM)))  # 2480 x 3508
# ⚠️ TEK KAYNAK: bu deger cabin_config `aruco.real_cm` ile AYNI olmak ZORUNDA.
# 2026-09-09 sahip olcumu: kabin isareti kenari 15 cm (onceki sayfa 10 cm idi).
# Yanlis kenar = tespit CALISIR ama olcek yanlis olur ve 3B konum SESSIZCE kayar.
KENAR_CM = 15.0  # cabin_config: aruco.real_cm
SESSIZ_CM = 2.0  # beyaz sessiz bölge (her kenarda)
DICT_ADI = "DICT_5X5_50"
MARKER_ID = 0
AD = f"PEMF_ArUco_Marker_5X5_50_ID{MARKER_ID}_{KENAR_CM:g}cm_A4"


def _cm(x: float) -> int:
    return int(round(x * PX_CM))


def _font(boyut: int, kalin: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for aday in (
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / ("arialbd.ttf" if kalin else "arial.ttf"),
        Path(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if kalin
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
    ):
        if aday.exists():
            return ImageFont.truetype(str(aday), boyut)
    return ImageFont.load_default()


def marker_goruntusu(kenar_px: int) -> Image.Image:
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICT_ADI))
    m = cv2.aruco.generateImageMarker(d, MARKER_ID, kenar_px)  # uint8 0/255, siyah çerçeve dahil
    return Image.fromarray(m).convert("L")


def sayfa_uret() -> Image.Image:
    sayfa = Image.new("L", A4_PX, 255)
    ciz = ImageDraw.Draw(sayfa)
    W, H = A4_PX
    kenar = _cm(KENAR_CM)
    sessiz = _cm(SESSIZ_CM)
    dis = kenar + 2 * sessiz  # kesme karesi (14 cm)
    x0 = (W - dis) // 2
    y0 = _cm(4.2)

    # Başlık
    ciz.text((W // 2, _cm(1.4)), "PEMF Kabin Kalibrasyon Marker", fill=0, font=_font(72, True), anchor="mm")
    ciz.text(
        (W // 2, _cm(2.3)),
        f"ArUco {DICT_ADI} · ID {MARKER_ID} · siyah kare kenarı {KENAR_CM:.1f} cm · 3 pipeline için TEK ortak marker",
        fill=0,
        font=_font(40),
        anchor="mm",
    )
    # ÜST işareti (kesme karesinin DIŞINDA — sessiz bölge bembeyaz kalır)
    ciz.text((W // 2, y0 - _cm(0.55)), "▲ ÜST (bu kenar tavana yakın)", fill=0, font=_font(40, True), anchor="mm")

    # Kesme çizgisi (kesik) — 14 x 14 cm
    adim = _cm(0.4)
    for x in range(x0, x0 + dis, adim * 2):
        ciz.line([(x, y0), (min(x + adim, x0 + dis), y0)], fill=0, width=3)
        ciz.line([(x, y0 + dis), (min(x + adim, x0 + dis), y0 + dis)], fill=0, width=3)
    for y in range(y0, y0 + dis, adim * 2):
        ciz.line([(x0, y), (x0, min(y + adim, y0 + dis))], fill=0, width=3)
        ciz.line([(x0 + dis, y), (x0 + dis, min(y + adim, y0 + dis))], fill=0, width=3)

    # Marker
    sayfa.paste(marker_goruntusu(kenar), (x0 + sessiz, y0 + sessiz))

    # Kenar boyu kadar cetvel çubuğu (doğrulama)
    cy = y0 + dis + _cm(1.2)
    cx0 = (W - kenar) // 2
    ciz.rectangle([cx0, cy, cx0 + kenar, cy + _cm(0.5)], outline=0, width=4)
    for i in range(0, int(KENAR_CM) + 1):
        x = cx0 + _cm(i)
        ciz.line([(x, cy), (x, cy + _cm(0.5 if i % 5 == 0 else 0.3))], fill=0, width=4)
        ciz.text((x, cy + _cm(0.85)), str(i), fill=0, font=_font(32), anchor="mm")
    ciz.text(
        (W // 2, cy + _cm(1.5)),
        f"DOĞRULAMA: bu çubuk cetvelde tam {KENAR_CM:.1f} cm ise siyah karenin kenarı da "
        f"{KENAR_CM:.1f} cm'dir.".replace(".", ","),
        fill=0,
        font=_font(38, True),
        anchor="mm",
    )

    # Talimat kutusu
    satirlar = [
        "BASKI: %100 / 'gerçek boyut' — 'sayfaya sığdır' ve 'ölçekle' KAPALI. Mat kâğıt (parlama yok).",
        "KESME: kesik çizgiden kes (14 × 14 cm). Beyaz kenar (sessiz bölge) KALSIN — ArUco için zorunlu.",
        "YER: ARKA duvar (kameranın karşısı), SOL-ÜST köşe — marker MERKEZİ sol duvardan 8 cm,",
        "     tavandan 8 cm. Kabin frame: merkez = [-21.5, +14.0, +25.0] cm  (65 × 50 × 50 kabin).",
        "YÖN: siyah yüz kameraya (öne) baksın, '▲ ÜST' tavana. Düz yapıştır (kırışık/eğri değil).",
        "KAMERA: sağ-alt-ÖN köşe, lens [32.5, -25.0, -25.0] cm, kabin merkezine (origin) bakar.",
        "CONFIG: qr_to_origin_cm [21.5, -14.0, -25.0] · to_marker_cm 86.7 · to_origin_cm 48.0",
        "Farklı boyutta basarsan 3 cabin_config'te aruco.real_cm'i ölçtüğün kenara çek.",
    ]
    ty = cy + _cm(2.6)
    for s in satirlar:
        ciz.text((_cm(1.5), ty), s, fill=0, font=_font(34, s.split(":")[0].isupper()), anchor="lm")
        ty += _cm(0.75)
    ciz.text(
        (W // 2, H - _cm(1.0)),
        "Kılavuz: ai_hub/KABIN_KURULUM_KILAVUZU.md · üretim: scripts/kabin_marker_a4.py (300 DPI)",
        fill=0,
        font=_font(30),
        anchor="mm",
    )
    return sayfa


def dogrula(sayfa: Image.Image) -> tuple[bool, str]:
    img = np.array(sayfa)
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICT_ADI))
    det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())
    corners, ids, _ = det.detectMarkers(img)
    if ids is None or MARKER_ID not in ids.flatten().tolist():
        return False, f"marker bulunamadı (ids={None if ids is None else ids.flatten().tolist()})"
    c = corners[ids.flatten().tolist().index(MARKER_ID)][0]
    kenarlar = [float(np.linalg.norm(c[i] - c[(i + 1) % 4])) for i in range(4)]
    beklenen = KENAR_CM * PX_CM
    sapma = max(abs(k - beklenen) for k in kenarlar)
    return sapma <= 4.0, f"kenarlar px={['%.1f' % k for k in kenarlar]} beklenen={beklenen:.1f} sapma={sapma:.1f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cikti", default=str(KOK / "ai_hub"), help="çıktı dizini (varsayılan ai_hub/)")
    ap.add_argument("--masaustu", action="store_true", help="Masaüstü'ne de kopyala")
    a = ap.parse_args(argv)
    sayfa = sayfa_uret()
    ok, mesaj = dogrula(sayfa)
    print(("DOGRULAMA OK: " if ok else "DOGRULAMA HATA: ") + mesaj)
    if not ok:
        return 2
    cikti = Path(a.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    png = cikti / f"{AD}.png"
    pdf = cikti / f"{AD}.pdf"
    sayfa.save(png, dpi=(DPI, DPI), optimize=True)
    sayfa.save(pdf, resolution=float(DPI))
    print(f"yazildi: {png} ({png.stat().st_size // 1024} KB), {pdf} ({pdf.stat().st_size // 1024} KB)")
    if a.masaustu:
        masa = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
        if masa.exists():
            for p in (png, pdf):
                hedef = masa / p.name
                hedef.write_bytes(p.read_bytes())
                print(f"kopya: {hedef}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
