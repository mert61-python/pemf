# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KABİN KAMERASI — seçim (cihaz düzeyi) ve açılış. T2D-2 · Tezgâh-2 #3. AI Pro hazırlık önizlemesi ve seans döngüsü
kamerayı YALNIZ buradan açar.

ÖLÇÜLEN KUSUR (Tezgâh-2, 2026-10-23): `ai_router` sabit `cv2.VideoCapture(0)` açıyordu → dahili kameralı dizüstünde kabin
kamerası (Pusat, Windows'ta "FHD Camera") DEĞİL dahili kamera açıldı; çözünürlük istenmediği için kare 640×480 geldi
(1080p kalibrasyonu geçersiz, 640×480 ↔ 1080p görüş alanı farklı).

SÖZLEŞME:
  * Kamera cihaz düzeyinde SEÇİLİR (Ayarlar ▸ Kabin kamerası) ve `<veri kökü>/kabin_kamerasi.json`'da hatırlanır —
    hesaptan / profilden bağımsız (dil seçimi gibi, Y161).
  * Seçim yoksa kamera AÇILMAZ: `KameraSecilmedi` (çağıran eylem söyleyen iletiyi verir). 0 numaralı (çoğu dizüstünde dahili)
    kameraya SESSİZ düşüş YOK.
  * Açılır açılmaz, İLK okumadan ÖNCE 1920×1080 istenir — MSMF'de akış başladıktan sonra çözünürlük değiştirmek `(-215)
    _step >= minstep` hatası verir (Tezgâh-2 ölçümü). Kamera başka boyut verirse kare o boyutta gelir; K ölçeklemesi kenar
    oranı farklıysa reddedilir (`cv_ortak.coord_transform.olcekli_intrinsics`).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from pathlib import Path

KAMERA_DOSYASI = "kabin_kamerasi.json"
ORTAM_DEGISKENI = "PEMF_KABIN_KAMERASI"
#: OpenCV `CAP_PROP_FRAME_WIDTH` / `HEIGHT` (kararlı sayılar; cv2 sabiti yoksa).
_CAP_GENISLIK, _CAP_YUKSEKLIK = 3, 4
#: Tezgâh-2 sahip kararı (12:5x): "1080p kullanacağız" — kalibrasyon `ai_hub/cv_ortak/kalibrasyon/` bu boyutta.
ISTENEN_COZUNURLUK = (1920, 1080)
#: Ayarlar'daki taramada denenecek indeksler (0..N-1). OpenCV kamera ADI vermez; kullanıcı küçük önizlemeden tanır.
TARAMA_INDEKS_SAYISI = 4
_AZAMI_INDEKS = 63
_ONIZLEME_GENISLIK = 240


class KameraSecilmedi(RuntimeError):
    """Kabin kamerası seçilmemiş — kamera açılmadı (dahili kameraya sessiz düşüş yok)."""


def _veri_koku() -> Path:
    from utils.path_utils import get_app_data_directory

    return Path(get_app_data_directory())


def _gecerli_indeks(deger) -> int | None:
    if isinstance(deger, bool) or not isinstance(deger, int):
        return None
    return deger if 0 <= deger <= _AZAMI_INDEKS else None


def _ortam_indeksi() -> int | None:
    ham = (os.environ.get(ORTAM_DEGISKENI) or "").strip()
    try:
        return _gecerli_indeks(int(ham)) if ham else None
    except ValueError:
        return None


def secili_kamera() -> dict | None:
    """Seçili kabin kamerası `{"indeks": int, "kaynak": "ortam" | "ayar"}`; hiç seçilmemiş / dosya bozuk → None.
    `PEMF_KABIN_KAMERASI` (tezgâh / kiosk) ayarın ÖNÜNDEdir; sahada tanımlı değildir."""
    i = _ortam_indeksi()
    if i is not None:
        return {"indeks": i, "kaynak": "ortam"}
    try:
        veri = json.loads((_veri_koku() / KAMERA_DOSYASI).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    indeks = _gecerli_indeks(veri.get("indeks")) if isinstance(veri, dict) else None
    return None if indeks is None else {"indeks": indeks, "kaynak": "ayar"}


def kamera_sec(indeks) -> dict:
    """Seçimi atomik yazar (geçici dosya + os.replace). Geçersiz indeks → ValueError; disk hatası → OSError."""
    i = _gecerli_indeks(indeks)
    if i is None:
        raise ValueError(indeks)
    kok = _veri_koku()
    kok.mkdir(parents=True, exist_ok=True)
    fd, gecici = tempfile.mkstemp(dir=str(kok), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"indeks": i}, f)
        os.replace(gecici, kok / KAMERA_DOSYASI)
    except Exception:
        try:
            os.unlink(gecici)
        except OSError:
            pass
        raise
    return {"indeks": i, "kaynak": "ayar"}


def _cozunurluk_iste(cap, cv2) -> None:
    """1920×1080 isteği (ilk okumadan ÖNCE). Kamera desteklemezse OpenCV yok sayar; istek hatası kamerayı DÜŞÜRMEZ (günlük)."""
    w, h = ISTENEN_COZUNURLUK
    try:
        cap.set(getattr(cv2, "CAP_PROP_FRAME_WIDTH", _CAP_GENISLIK), float(w))
        cap.set(getattr(cv2, "CAP_PROP_FRAME_HEIGHT", _CAP_YUKSEKLIK), float(h))
    except Exception:
        logging.getLogger(__name__).warning("kabin kamerasi: %sx%s istegi uygulanamadi", w, h, exc_info=True)


def kamera_ac(cv2=None):
    """Seçili kabin kamerasını açar ve (açıldıysa) ilk okumadan ÖNCE 1920×1080 ister. @return (cap, indeks) — açılıp
    açılmadığını çağıran `cap.isOpened()` ile denetler. Seçim yoksa `KameraSecilmedi` (kamera hiç açılmaz)."""
    secim = secili_kamera()
    if secim is None:
        raise KameraSecilmedi()
    if cv2 is None:
        import cv2
    cap = cv2.VideoCapture(secim["indeks"])
    if cap.isOpened():
        _cozunurluk_iste(cap, cv2)
    return cap, secim["indeks"]


#: T3 · Y189: tek karede otomatik pozlama / beyaz dengesi oturana dek atılan ilk kare sayısı.
KARE_ISINMA = 5


def kare_al(cv2=None) -> dict | None:
    """T3 · Y189 (petri / fantom analizi "Kabin kamerasından çek"): SEÇİLİ kabin kamerasından TAM çözünürlüklü tek kare (JPEG,
    base64). `kamera_ac` ile açılır (1920×1080 ilk okumadan ÖNCE), ilk `KARE_ISINMA` kare atılır, son kare kodlanır, kamera
    HER durumda bırakılır. Seçim yok → `KameraSecilmedi`; açılamaz / okunamaz → None."""
    if cv2 is None:
        import cv2
    cap, indeks = kamera_ac(cv2)
    try:
        if not cap.isOpened():
            return None
        kare = None
        for _ in range(KARE_ISINMA + 1):
            ok, k = cap.read()
            if ok and k is not None:
                kare = k
        if kare is None:
            return None
        basarili, tampon = cv2.imencode(".jpg", kare, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not basarili:
            return None
        kh, kw = kare.shape[:2]
        return {
            "indeks": indeks,
            "genislik": int(kw),
            "yukseklik": int(kh),
            "image_base64": base64.b64encode(tampon).decode("ascii"),
        }
    finally:
        cap.release()


def kameralari_tara(cv2=None, sayi: int = TARAMA_INDEKS_SAYISI) -> list[dict]:
    """Ayarlar ▸ "Kameraları tara": 0..sayi-1 indekslerini KISA açar, 1920×1080 ister, bir kare okur, bırakır.
    @return açılanların listesi `[{"indeks", "genislik", "yukseklik", "onizleme"}]` (önizleme: küçük JPEG, base64; kare
    okunamazsa None). Yalnız kullanıcı eylemiyle çağrılır (açılış / arka plan taraması YOK)."""
    if cv2 is None:
        import cv2
    sonuc: list[dict] = []
    for i in range(max(0, int(sayi))):
        cap = cv2.VideoCapture(i)
        try:
            if not cap.isOpened():
                continue
            _cozunurluk_iste(cap, cv2)
            ok, kare = cap.read()
            oge = {
                "indeks": i,
                "genislik": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
                "yukseklik": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
                "onizleme": None,
            }
            if ok and kare is not None:
                kh, kw = kare.shape[:2]
                oge["genislik"], oge["yukseklik"] = int(kw), int(kh)
                olcek = min(1.0, _ONIZLEME_GENISLIK / float(max(1, kw)))
                kucuk = cv2.resize(kare, (max(1, int(kw * olcek)), max(1, int(kh * olcek))))
                basarili, tampon = cv2.imencode(".jpg", kucuk, [cv2.IMWRITE_JPEG_QUALITY, 60])
                if basarili:
                    oge["onizleme"] = base64.b64encode(tampon).decode("ascii")
            sonuc.append(oge)
        finally:
            cap.release()
    return sonuc
