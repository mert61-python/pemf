# -*- coding: utf-8 -*-
# Author: mertaygn
"""AI GÖRSEL KODLAMA — kalite/kapak kapısı (AI Hub planı, ADIM 1).

Plan: `docs/ai-hub-gorsel-sahne-plani-2026-09-10.md` §4 ADIM 1 ("saf kazanç, davranış-nötr").

===============================================================================
NE ÖLÇÜLÜYOR
===============================================================================
`cv2.imencode(".jpg", img)` kalite argümanı verilmezse OpenCV **q95** kullanır. AI uçları
sonucu `image_base64` olarak döndürüyor ve beş uç + iki mozaik ucu argümansız çağırıyordu:

  · q95 → dosya ~2× büyük (aynı görüntü, gözle ayırt edilemez fark)
  · gömülü backend q95 / GPU mikroservisi q85 → **AYNI analiz dağıtıma göre 1,9× farklı**
  · fantom/petri `07_combined` 2×3 MOZAİKTİR; dikey telefon fotoğrafında 6048×12256'ya
    çıkıyor → kapak olmadan yalnız kalite düşürmek YETMEZ

===============================================================================
⚠️ MODEL GİRDİSİ ≠ GÖSTERİM ÇIKTISI
===============================================================================
`_localize_organ_gpu` içindeki `imencode` kaldı ve **kalmalı**: o kare operatöre
gösterilmiyor, GPU'ya ÇIKARIM GİRDİSİ olarak yükleniyor. Sıkıştırma artefaktı orada
tespit/segmentasyon sonucunu değiştirebilir ve bu bir tıbbi karar ekranını besler.
Bu dosya o ayrımı da kilitler — "hepsine kalite ekle" diyen bir regresyon KIRMIZI olur.
"""

from __future__ import annotations

import ast
import io
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

ROUTER = KOK / "apps" / "backend" / "servers" / "ai_router.py"

#: Bu uçlar sonucu operatöre GÖSTERİR → kodlama kalitesi AÇIKÇA verilmeli.
GOSTERIM_UCLARI = {
    "analyze_landmark",
    "analyze_segmentation",
    "analyze_thermal",
    "analyze_reticulocytes",
    "analyze_kidney_ct",
    "analyze_em_fantom",
    "analyze_em_petri",
    "analyze_cat_organ",
    "ai_pro_frame",
}

#: Model GİRDİSİ kodlayan yardımcılar — kalite argümanı BİLEREK YOK.
GIRDI_KODLAYICILAR = {"_localize_organ_gpu"}


def _agac():
    return ast.parse(io.open(ROUTER, encoding="utf-8", errors="replace").read())


def _fonksiyon_araliklari():
    araliklar = []
    for d in ast.walk(_agac()):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
            araliklar.append((d.lineno, getattr(d, "end_lineno", d.lineno), d.name))
    return araliklar


def _sahip_fonksiyon(satir: int) -> str:
    en_iyi = None
    for b, s, ad in _fonksiyon_araliklari():
        if b <= satir <= s and (en_iyi is None or b > en_iyi[0]):
            en_iyi = (b, ad)
    return en_iyi[1] if en_iyi else "?"


def _jpeg_kodlamalari():
    """(fonksiyon_adi, satir, kalite_verildi_mi) — AST'ten, satır numarası TAHMİNİ DEĞİL."""
    bulunan = []
    for d in ast.walk(_agac()):
        if not isinstance(d, ast.Call):
            continue
        ad = d.func.id if isinstance(d.func, ast.Name) else getattr(d.func, "attr", "")
        if ad == "_kapakli_kodla":
            # ⚠️ Bu yardımcı kaliteyi YAPISI GEREĞİ uygular (imza zorunlu kılıyor) → her
            # zaman "kaliteli" sayılır. Tarayıcıya eklenmezse fantom/petri "hiç kodlamıyor"
            # görünür ve karşıt-kanıt kapısı yanlışlıkla KIRMIZI olur (ilk yazımda oldu).
            kalite = True
        elif ad == "_encode_jpg_b64":
            kalite = any(k.arg == "quality" for k in d.keywords) or len(d.args) >= 2
        elif ad == "imencode":
            ilk = d.args[0] if d.args else None
            if not (isinstance(ilk, ast.Constant) and str(ilk.value).endswith(".jpg")):
                continue
            kalite = len(d.args) >= 3
        else:
            continue
        bulunan.append((_sahip_fonksiyon(d.lineno), d.lineno, kalite))
    return bulunan


# ============================================================================
# 1. ⚠️ ASIL KAPI — gösterim uçlarında kalitesiz kodlama KALMADI
# ============================================================================


def test_KRITIK_gosterim_uclarinda_KALITESIZ_kodlama_YOK():
    """MUTASYON: herhangi bir uçtan `quality=` argümanını sil → KIRMIZI.

    ⚠️ ÇIPA AST'YE PINLI: düz metin araması yorumlara ve hata mesajlarına takılır
    (bu depoda iki kez yaşandı).
    """
    kalitesiz = [(fn, satir) for fn, satir, kalite in _jpeg_kodlamalari() if not kalite and fn in GOSTERIM_UCLARI]
    assert not kalitesiz, (
        f"GOSTERIM ucunda kalite argumansiz JPEG kodlamasi var: {kalitesiz} -> OpenCV q95 kullanir, "
        "dosya ~2x buyur ve gomulu/GPU dagitimlari arasinda 1,9x boyut sapmasi geri gelir"
    )


def test_KRITIK_her_gosterim_ucu_GERCEKTEN_kodluyor():
    """Karşıt kanıt: kapı "hiç kodlama yok" diye geçilemesin.

    Bir uç kodlamayı tamamen bırakırsa yukarıdaki kapı boş listeyle YEŞİL kalırdı.
    """
    kodlayan = {fn for fn, _s, _k in _jpeg_kodlamalari()}
    eksik = GOSTERIM_UCLARI - kodlayan
    assert not eksik, f"bu gosterim uclari artik HIC JPEG kodlamiyor: {sorted(eksik)} -> capa BAYAT"


# ============================================================================
# 2. ⚠️ MODEL GİRDİSİ KORUNUYOR
# ============================================================================


def test_KRITIK_model_GIRDISI_kodlamasina_kalite_EKLENMEDI():
    """⚠️ "Hepsine kalite ekle" diyen bir regresyon KIRMIZI olmalı.

    `_localize_organ_gpu` karesi GPU'ya çıkarım girdisi olarak gider. Sıkıştırma artefaktı
    tespit/segmentasyon sonucunu değiştirebilir ve bu tıbbi karar ekranını besler.
    Düşürülecekse önce DOĞRULUK ÖLÇÜLMELİ — tahminle değil.

    MUTASYON: `_localize_organ_gpu`daki `imencode`a kalite ekle → KIRMIZI.
    """
    for fn, satir, kalite in _jpeg_kodlamalari():
        if fn in GIRDI_KODLAYICILAR:
            assert not kalite, (
                f"{fn} (satir {satir}) MODEL GIRDISINI sikistiriyor -> cikarim dogrulugu "
                "olculmeden degistirilemez (bkz. oradaki not)"
            )


# ============================================================================
# 3. MOZAİK KAPAĞI
# ============================================================================


def test_KRITIK_mozaik_kodlayicisi_KAPAK_uyguluyor():
    """Kalite tek başına yetmez: `07_combined` 2×3 mozaik, 6048×12256'ya çıkabiliyor.

    MUTASYON: `_kapakli_kodla`daki `cv2.resize` dalını sil → KIRMIZI (kapak uygulanmaz).
    """
    import cv2
    import numpy as np
    from servers.ai_router import MOZAIK_AZAMI_KENAR, _kapakli_kodla

    genis = np.zeros((400, 5000, 3), dtype=np.uint8)
    # ⚠️ ADIM 2'de imza (bayt, boyut) oldu: kapak kareyi KÜÇÜLTTÜĞÜ için istemcinin
    # oran kilidi ORİJİNAL değil KODLANAN boyutu almalı.
    bayt, boyut = _kapakli_kodla(genis)

    geri = cv2.imdecode(np.frombuffer(bayt, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert max(geri.shape[:2]) <= MOZAIK_AZAMI_KENAR, (
        f"kapak UYGULANMADI: {geri.shape[:2]} (azami {MOZAIK_AZAMI_KENAR})"
    )
    # ⚠️ BİLDİRİLEN BOYUT, GERÇEKTEN KODLANAN KARE OLMALI — orijinali (400×5000)
    # bildirmek istemcinin kutusunu bozar ve üzerine çizilen işaretleri kaydırır.
    assert boyut == {"image_w": geri.shape[1], "image_h": geri.shape[0]}, (
        f"bildirilen boyut {boyut} != kodlanan kare {geri.shape[1]}x{geri.shape[0]}"
    )


def test_KRITIK_kapak_kucuk_goruntuyu_BUYUTMEZ():
    """Küçük bir görüntüyü şişirmek dosyayı büyütür, bilgi eklemez.

    MUTASYON: `min(1.0, ...)` kısıtını kaldır → KIRMIZI.
    """
    import cv2
    import numpy as np
    from servers.ai_router import _kapakli_kodla

    kucuk = np.zeros((120, 200, 3), dtype=np.uint8)
    bayt, boyut = _kapakli_kodla(kucuk)
    geri = cv2.imdecode(np.frombuffer(bayt, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert geri.shape[:2] == (120, 200), f"kucuk goruntu BUYUTULDU: {geri.shape[:2]}"
    assert boyut == {"image_w": 200, "image_h": 120}, f"bildirilen boyut yanlis: {boyut}"


# ============================================================================
# 4. ÖLÇÜLEN KAZANÇ — iddia sayı ile kanıtlanır
# ============================================================================


def test_KRITIK_q85_gercekten_dosyayi_KUCULTUYOR():
    """⚠️ "q85 yarıya indirir" bir İDDİADIR — burada ÖLÇÜLÜR.

    Düz renk bir kare sıkıştırmada aldatıcıdır (her kalitede küçük çıkar), bu yüzden
    gürültülü (fotoğraf benzeri) bir kare kullanılır.
    """
    import cv2
    import numpy as np
    from servers.ai_router import GOSTERIM_JPEG_KALITESI

    rng = np.random.default_rng(42)
    foto = rng.integers(0, 255, (1200, 1600, 3), dtype=np.uint8)
    # Gerçek fotoğraflar tamamen rastgele değildir; hafif bulanıklık doğal içeriğe yaklaştırır.
    foto = cv2.GaussianBlur(foto, (5, 5), 0)

    _ok, q95 = cv2.imencode(".jpg", foto)  # argümansız = OpenCV varsayılanı
    _ok, q85 = cv2.imencode(".jpg", foto, [int(cv2.IMWRITE_JPEG_QUALITY), GOSTERIM_JPEG_KALITESI])

    assert len(q85) < len(q95), (
        f"q{GOSTERIM_JPEG_KALITESI} ({len(q85)} B) varsayilandan ({len(q95)} B) KUCUK DEGIL "
        "-> kalite sabiti etkisiz (varsayilan zaten dusuk mu?)"
    )
    kazanc = 1.0 - len(q85) / len(q95)
    assert kazanc > 0.15, f"kazanc yalniz %{kazanc * 100:.0f} -> beklenen anlamli kucultme yok"


def test_kalite_sabiti_MAKUL_aralikta():
    """Çok düşük kalite okunabilirliği bozar (plan: q85 altı UYGULANMAYACAK)."""
    from servers.ai_router import GOSTERIM_JPEG_KALITESI

    assert 80 <= GOSTERIM_JPEG_KALITESI <= 92, (
        f"kalite {GOSTERIM_JPEG_KALITESI} -> plan q85'i sabitledi; q80 alti okunabilirlikle celisir"
    )
