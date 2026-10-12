# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""PEMF TÜKETİM KAPISI — hocanın petri v2 / fantom v3 sonuçlarının bobine giden yolda nasıl okunacağı (TEK KAYNAK).

Kaynak: Çağlar Hoca `ENTEGRASYON.md` §3 "Sonucu tüketirken kontrol edilecekler" (degisenler.zip, 2026-10-02) + plan
`DENETIM/AI-ENTEGRASYON-PLANI.md` §3.9. Bobine (ya da `_predict_and_drive` zarfına) bir şey göndermeden önce SIRAYLA:
  1. `success == true` (değilse `error`);
  2. `pemf_valid == true` — false ise D/P/E fiziksel olarak GEÇERSİZ (kabin konumu bilinmiyor), bobine GÖNDERİLMEZ;
  3. fantomda ayrıca `reliable == true`;
  4. `warnings`: `layout_mismatch`, `control_cancer_missed`, `control_healthy_flagged` → sonuç KULLANILMAZ;
     `oblique_view`, `low_resolution`, `ring_partial` → çekim TEKRARLANIR.

NEDEN TEK MODÜL (ai_hub'da, backend'de değil): üç tüketici aynı kuralı uygular — AI Pro sağlayıcıları
(`apps/backend/servers/ai_pro_hedef.py`, sürüş), AI Hub analiz uçları (`ai_router` gömülü + `ai_service/app.py` GPU servisi —
`docker/Dockerfile.ai` imaja yalnız `ai_hub/` + `ai_service/` kopyalar; `plausibility.py` ile aynı gerekçe) ve arayüz (bu
modülün ürettiği eylem metinleri). Kopyalanırsa sürüklenir. Saf fonksiyonlar; cv2 / numpy İÇE AKTARILMAZ.

⚠️ FAIL-CLOSED: alan YOKSA (eski v1 sonucu, bozuk yanıt) "geçerli" SAYILMAZ — `pemf_valid` / `reliable` eksikse sürülemez.
⚠️ Bu kapı `PEMF_ARASTIRMA_AIPRO` bayrağından BAĞIMSIZDIR: bayrak araştırma sürüşünü AÇAR, bu kapı geçersiz sonucu yine KESER.
⚠️ Bu bir HEDEF GEÇERLİLİK denetimidir (lokalizasyon) — tedavi doz kıskacı değil (Ö.4-Y9 temiz); ACİL DURDUR'a dokunmaz (Ö.4-Y8).
"""

from __future__ import annotations

import re

#: Hocanın §3'ü: bu uyarılardan biri varsa sonuç KULLANILMAZ.
ENGELLEYICI = ("layout_mismatch", "control_cancer_missed", "control_healthy_flagged")
#: Hocanın §3'ü: bu uyarılardan biri varsa çekim TEKRARLANIR (kapalı döngüde kare sürülmez).
YENIDEN_CEKIM = ("oblique_view", "low_resolution", "ring_partial")

_KOD = re.compile(r"^[a-z][a-z0-9_]*$")

#: Neden kodu → operatöre NE YAPACAĞINI söyleyen metin (hata mesajı eylem söylesin). `{nesne}` = "plakanın" / "fantomun".
_EYLEM = {
    "basarisiz": "Analiz sonuç üretmedi ({hata}) — görüntüyü kontrol edip yeniden çekin.",
    "pemf_gecersiz": (
        "PEMF değerleri geçersiz: {nesne} kabindeki konumu bilinmiyor — kabine ArUco koyun ya da konumu ayarlayın."
    ),
    "guvenilir_degil": (
        "Tümör tespiti güvenilir değil (düşük kontrast / düşük çözünürlük / zayıf şablon uyumu) — fantomu yakından, "
        "tepeden ve dik çekip yeniden deneyin."
    ),
    "layout_mismatch": (
        "Tümör yerleşimi referansla uyuşmuyor (yanlış tespit ya da farklı fantom) — sonuç kullanılamaz; doğru fantomu "
        "kadraja alın ya da bu fantom için yeni yerleşim referansı üretin."
    ),
    "control_cancer_missed": (
        "Boyalı (kanser) kontrol kuyucuğu kanser sınıflanmadı — bu plakada eşikler güvenilmez, sonuç kullanılamaz. "
        "Kontrol kuyucuklarını ve ışığı denetleyip yeniden çekin."
    ),
    "control_healthy_flagged": (
        "Sağlıklı kontrol kuyucuğu kanser işaretlendi — bu plakada eşikler güvenilmez, sonuç kullanılamaz. "
        "Kontrol kuyucuklarını ve ışığı denetleyip yeniden çekin."
    ),
    "oblique_view": "Kamera {nesne_yalin} dik değil — kamerayı tam tepeden tutup yeniden çekin.",
    "low_resolution": "Görüntü çözünürlüğü düşük — yaklaşın ya da yakınlaştırıp yeniden çekin.",
    "ring_partial": "Yeşil bobin halkasının büyük kısmı kadrajda değil — halkayı kadraja alıp yeniden çekin.",
}

#: VARSAYIM (laboratuvar maddesi) kodu → kullanıcıya gösterilen açıklama. Sürüşü kendi başına ENGELLEMEZ (pemf_valid
#: kararını hoca verir) ama sonuç yanında AÇIKÇA söylenir (plan §6, C8).
_VARSAYIM = {
    "pemf_axis_sign_assumed": (
        "VARSAYIM: fantom CST eğitim kutusuna eşlendi; eksen işareti (u→+y, v→+z) fotoğraftan doğrulanamaz "
        "(laboratuvar maddesi) — kabin ölçümü değildir."
    ),
    "halka_capi": (
        "VARSAYIM: yeşil halka çapı 184 mm (çapraz kalibrasyon; şerit metreyle ölçülmedi — laboratuvar maddesi)."
    ),
    "a1_kosesi": (
        "VARSAYIM: plakanın A1 köşesi görüntüden okunmuyor (yatay plaka = sol-üst, dikey = sağ-üst) — plaka 180° "
        "çevrildiyse kuyucuk adları ters olur."
    ),
    "kanser_esikleri": (
        "VARSAYIM: kanser eşikleri yalnız yapay boyayla doğrulandı ve bu analizde kontrol kuyucuğu verilmedi "
        "(laboratuvar maddesi) — her deneyde kontrol kuyucuğu kullanın."
    ),
}


def _uyari_listesi(uyarilar) -> list[str]:
    """AII-2.2: `warnings` tek DİZE (ya da bytes) gelirse karakterlerine bölünmez — tek uyarı sayılır (FAIL-CLOSED)."""
    if isinstance(uyarilar, (str, bytes)):
        uyarilar = [uyarilar]
    return [u.decode("utf-8", "replace") if isinstance(u, bytes) else str(u) for u in (uyarilar or [])]


def uyari_kodlari(uyarilar) -> list[str]:
    """`"ring_unavailable: ring_partial: halkanin %31'i ..."` → `["ring_unavailable", "ring_partial"]`.

    Hocanın uyarıları `kod: açıklama` biçimindedir ve iç içe kod taşıyabilir (`ring_unavailable: ring_partial: …`);
    `ring_partial` tam bu biçimde gelir — yalnız ilk kod okunsaydı yeniden-çekim kapısı onu GÖRMEZDİ."""
    kodlar: list[str] = []
    for u in _uyari_listesi(uyarilar):
        parcalar = u.split(":")
        # Son parça AÇIKLAMADIR (tek sözcük olsa bile kod sayılmaz); iki nokta yoksa uyarının tamamı koddur.
        adaylar = parcalar[:-1] if len(parcalar) > 1 else parcalar
        for parca in adaylar:
            # AII-2.2: büyük harf / kodsuz serbest metin öneki iç içe kodu GİZLEMEZ (eskiden `break` → tanınmıyordu).
            p = parca.strip().lower()
            if not _KOD.match(p):
                continue
            if p not in kodlar:
                kodlar.append(p)
    return kodlar


def _al(sonuc, ad, varsayilan=None):
    if isinstance(sonuc, dict):
        return sonuc.get(ad, varsayilan)
    return getattr(sonuc, ad, varsayilan)


def varsayimlar(sonuc, *, model: str) -> list[dict]:
    """Sonucun dayandığı LABORATUVAR VARSAYIMLARI (gösterim; sürüşü bu fonksiyon engellemez)."""
    kodlar = uyari_kodlari(_al(sonuc, "warnings") or [])
    out = []
    if model == "fantom":
        if "pemf_axis_sign_assumed" in kodlar or _al(sonuc, "pemf_source") == "cst_phantom_box":
            out.append({"kod": "pemf_axis_sign_assumed", "metin": _VARSAYIM["pemf_axis_sign_assumed"]})
        if _al(sonuc, "method") == "coil_ring":
            out.append({"kod": "halka_capi", "metin": _VARSAYIM["halka_capi"]})
    elif model == "petri":
        plaka = _al(sonuc, "plate") or {}
        if isinstance(plaka, dict) and plaka.get("plate_type"):
            out.append({"kod": "a1_kosesi", "metin": _VARSAYIM["a1_kosesi"]})
            sinif = _al(sonuc, "classification") or {}
            kontrol = (sinif.get("control_healthy") or sinif.get("control_cancer")) if isinstance(sinif, dict) else None
            if not kontrol:
                out.append({"kod": "kanser_esikleri", "metin": _VARSAYIM["kanser_esikleri"]})
    return out


def yanit_alanlari(sonuc, *, model: str) -> dict:
    """AI Hub analiz yanıtına EKLENEN v2/v3 alanları — gömülü uç (`ai_router`) ve GPU servisi (`ai_service`) AYNI kümeyi
    döndürsün diye tek yerde. Mevcut alanlar (`n_tumor`, `tumor_regions`, `n_wells`, `wells`, `centroid_cabin_mm`, `D`,
    `E_cancer`, `mm_per_px` …) çağıranın kendi sözlüğünde KALIR; bunlar yalnız EKTİR (eski istemci yok sayar).
    `well_id` / `tumor_id` kuyucuk / tümör sözlüklerinin içinde zaten gelir (`asdict`)."""
    d = {
        "pemf_valid": _al(sonuc, "pemf_valid") is True,
        "warnings": _uyari_listesi(_al(sonuc, "warnings")),
        "coord_frame": str(_al(sonuc, "coord_frame") or ""),
        "pemf_kapisi": degerlendir(sonuc, model=model),
    }
    if model == "fantom":
        d["reliable"] = _al(sonuc, "reliable") is True
        d["pemf_source"] = str(_al(sonuc, "pemf_source") or "")
        d["layout"] = dict(_al(sonuc, "layout") or {})
        d["phantom_frame"] = dict(_al(sonuc, "phantom_frame") or {})
        d["ring"] = {k: v for k, v in dict(_al(sonuc, "ring") or {}).items() if k != "contour_px"}
    else:
        d["plate"] = dict(_al(sonuc, "plate") or {})
        d["classification"] = dict(_al(sonuc, "classification") or {})
        d["pemf_source"] = {"cabin_aruco": "aruco", "cabin_placement": "placement"}.get(d["coord_frame"], "")
    return d


def degerlendir(sonuc, *, model: str) -> dict:
    """Hocanın §3 sırasıyla değerlendir → `{"surulebilir", "pemf_gecerli", "nedenler", "engelleyici", "yeniden_cekim",
    "uyari_kodlari", "eylem", "mesajlar", "varsayimlar"}`. `model`: "petri" | "fantom".

    `surulebilir` False ise sonuç bobine / `_predict_and_drive`'a GİTMEZ. AI Hub tek-foto analizi D/P/E'yi yine gösterir
    ama `mesajlar`daki eylem metniyle (D/P/E "geçersiz" etiketlidir)."""
    if model not in ("petri", "fantom"):
        raise ValueError(f"pemf kapısı: bilinmeyen model {model!r}")
    nesne = "plakanın" if model == "petri" else "fantomun"
    nesne_yalin = "plakaya" if model == "petri" else "fantoma"
    kodlar = uyari_kodlari(_al(sonuc, "warnings") or [])
    nedenler: list[str] = []
    if _al(sonuc, "success") is not True:
        nedenler.append("basarisiz")
    pemf = _al(sonuc, "pemf_valid") is True
    if not pemf:
        nedenler.append("pemf_gecersiz")
    if model == "fantom" and _al(sonuc, "reliable") is not True:
        nedenler.append("guvenilir_degil")
    engel = [k for k in ENGELLEYICI if k in kodlar]
    yeniden = [k for k in YENIDEN_CEKIM if k in kodlar]
    nedenler += engel + yeniden
    hata = str(_al(sonuc, "error") or "bilinmeyen hata")
    mesajlar = [
        {"kod": n, "metin": _EYLEM[n].format(nesne=nesne, nesne_yalin=nesne_yalin, hata=hata)} for n in nedenler
    ]
    return {
        "surulebilir": not nedenler,
        "pemf_gecerli": pemf,
        "nedenler": nedenler,
        "engelleyici": engel,
        "yeniden_cekim": yeniden,
        "uyari_kodlari": kodlar,
        "eylem": mesajlar[0]["metin"] if mesajlar else "",
        "mesajlar": mesajlar,
        "varsayimlar": varsayimlar(sonuc, model=model),
    }
