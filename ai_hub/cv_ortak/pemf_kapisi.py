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

KOŞULSUZ KİP (T3 · Y189, sahip + Çağlar Hoca 2026-10-23: "engelleri tamamen kaldırdığın bir sürüm, düğmeyle; AI tek başına ne
bulacak"): `degerlendir(..., kosulsuz=True)` engelleyici / yeniden-çekim / güvenilmez nedenlerini SÜRÜŞÜ KESMEYEN uyarıya çevirir
(`atlanan`; `nedenler` ve `mesajlar` TAM kalır — operatör ne atlandığını görür). Kalan iki koşul fiziksel: sonuç var (`success`) ve
konum KABİN çerçevesinde (`pemf_valid`) — koordinat yoksa bobine gidecek hedef de yoktur. Varsayılan KOŞULLU (davranış aynı).
"""

from __future__ import annotations

import re

#: TD4 (tezgâh 2026-10-14): işaret kâğıdı ters takılı — kabin X / Y aynalanır, konumlar yanlış. Hat uyarısı
#: (`marker_upside_down: <bu metin>`) ve kapı eylemi AYNI metin.
ISARET_TERS_METNI = "Kabin işareti ters takılmış görünüyor — üst kenar tavana bakacak şekilde çevirin"

#: Hocanın §3'ü: bu uyarılardan biri varsa sonuç KULLANILMAZ. TD4: + `marker_upside_down` (aynalanmış kabin konumu).
ENGELLEYICI = ("layout_mismatch", "control_cancer_missed", "control_healthy_flagged", "marker_upside_down")
#: Hocanın §3'ü: bu uyarılardan biri varsa çekim TEKRARLANIR (kapalı döngüde kare sürülmez).
#: AII-1.1 (AI incelemesi): + hocanın petri README'sindeki çekim protokolü uyarıları — `plate_cropped` ("kadrajı genişlet"),
#: `few_candidates` ("sonucu gözle kontrol et": kapalı döngüde göz yok), `ecc_failed` ("ışık / odak kontrol"). ÖLÇÜLDÜ: kırpık
#: gerçek plakada uydurulan 24 kuyucuk (0/12 doğru, ~3 aralık kayık) yalnız bu ikisini taşıyıp "sürülebilir" geçiyordu.
#: T3 · Y191b `kuyu_skor_esigi` (ızgara hücresi skoru eşiğin altında — hücre kuyu sayılmadı) ARTIK BURADA DEĞİL — Y284 (sahip 13 Kasım
#: 2026: "yeniden çekim sayılmasın, yarı dolu plakayla da sürüş olabilmeli koşulluda"): deneyde kuyuların hepsi dolu OLMAZ; boş kuyu
#: koşullu kipte de sürüşü KESMEZ (uyarı kodu sonuçta kalır; hücre kuyu sayılmaz). Kırpık plakayı `plate_cropped` yakalar; ODAK
#: (ODK11) görülen kuyuları 24'lük düzene oturtur, sapma büyükse SÜRMEZ (`plakaUyumsuz`).
#: KD-2b · Y264: petri hattı `low_resolution` ÜRETMEZ (kuyu yarıçapı eşiği kaldırıldı — sabit kabin kamerasında kuyu 24 px);
#: kod burada fantom tümör eşiği (`tumor_detect`, < 6 px) için KALIR.
YENIDEN_CEKIM = (
    "oblique_view", "low_resolution", "ring_partial", "plate_cropped", "few_candidates", "ecc_failed",
)

#: KD · Y258–Y259 (sahip 2026-11-10): SABİT DÜZLEM kalibrasyonunun fiziksel engelleri (`cv_ortak.sabit_duzlem.ENGEL_KODLARI` +
#: AI Pro'nun `kalibrasyon_yok`u). Konum KABİN çerçevesinde geçersizdir → bobin HEDEFLENMEZ; KOŞULSUZ kipte de keser (fiziksel).
#: Sonuçta uyarı (`kod: açıklama`) ya da `error` olarak gelir (fantom boyu farklıysa hat hedef üretmez → `error`).
FIZIKSEL = (
    "kalibrasyon_yok",
    "kalibrasyon_bozuk",
    "kalibrasyon_kamera_farkli",
    "kamera_oynamis",
    "fantom_ayari_yok",
    "fantom_boyu_farkli",
    "fantom_degil",
    # KD-2 (sahip): numune görüş alanının kenarında (kör bölge) — kısmen görünen numuneye hedef VERİLMEZ, yön söylenir.
    "kor_bolge_on",
    "kor_bolge_arka",
    "kor_bolge_sol",
    "kor_bolge_sag",
)

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
    "marker_upside_down": ISARET_TERS_METNI + ".",
    "oblique_view": "Kamera {nesne_yalin} dik değil — kamerayı tam tepeden tutup yeniden çekin.",
    "low_resolution": "Görüntü çözünürlüğü düşük — yaklaşın ya da yakınlaştırıp yeniden çekin.",
    "ring_partial": "Yeşil bobin halkasının büyük kısmı kadrajda değil — halkayı kadraja alıp yeniden çekin.",
    "plate_cropped": "Plakanın bir kısmı kadraj dışında — plakanın tamamını kadraja alıp yeniden çekin.",
    "few_candidates": (
        "Kuyucuk ızgarası görüntüden yeterince doğrulanamadı — plakaya dik ve yakından, iyi ışıkta yeniden çekin."
    ),
    "ecc_failed": "Plaka ızgarası ince hizalanamadı — ışığı ve odağı denetleyip yeniden çekin.",
    "kuyu_skor_esigi": (
        "Bazı ızgara hücrelerinde besiyeri yok ya da ızgara plakadan taştı (hücre skoru eşiğin altında, kuyu sayılmadı) — "
        "kuyuların hepsinin dolu ve plakanın kadrajın ortasında olduğunu kontrol edip yeniden çekin."
    ),
    # KD · Y258–Y259 — Türkçe TABAN metni; arayüze giden metin sunucuda koddan çevrilir (`ai.pemf.kapi.<kod>`, TR + EN).
    "kalibrasyon_yok": "Kabin kalibrasyonu yok — Kabin kalibrasyonu bölümünde plakayı iki konumda ölçerek kalibre edin.",
    "kalibrasyon_bozuk": "Kabin kalibrasyonu okunamadı ya da bozuk — kabin kalibrasyonunu yeniden yapın.",
    "kalibrasyon_kamera_farkli": (
        "Kamera ya da çözünürlük kalibrasyondakinden farklı — kalibrasyon yapılan kabin kamerasını seçin ya da yeniden kalibre edin."
    ),
    "kamera_oynamis": (
        "Kamera oynamış olabilir ya da taban yüksekliği ayarı yanlış — yeniden kalibre edin ya da (kayma küçükse) kalibre etmeden devam edin."
    ),
    "kor_bolge_on": "Numune ön camın dibindeki kör bölgede (kısmen görünüyor) — numuneyi arkaya kaydırın.",
    "kor_bolge_arka": "Numune arka camın dibindeki kör bölgede (kısmen görünüyor) — numuneyi öne kaydırın.",
    "kor_bolge_sol": "Numune sol camın dibindeki kör bölgede (kısmen görünüyor) — numuneyi sağa kaydırın.",
    "kor_bolge_sag": "Numune sağ camın dibindeki kör bölgede (kısmen görünüyor) — numuneyi sola kaydırın.",
    "fantom_ayari_yok": "Fantom kalınlığı / tümör derinliği girilmedi — Kabin kalibrasyonu bölümünden girin.",
    "fantom_degil": (
        "Bulunan bölge fantom gibi görünmüyor (ışık yansıması ya da boş kabin) — fantomu kabine koyun; parlama varsa ışığı değiştirin."
    ),
    "fantom_boyu_farkli": (
        "Bulunan fantom boyu ayardakinden çok farklı (kabinde fantom yok ya da kalınlık / boy ayarı yanlış) — fantomu ve ayarı "
        "kontrol edin."
    ),
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


#: KOŞULSUZ kipte de sürüşü KESEN nedenler (fiziksel: sonuç yok / kabin çerçevesinde konum yok / KD kalibrasyon engeli).
KOSULSUZDA_KALAN = ("basarisiz", "pemf_gecersiz") + FIZIKSEL


def yanit_alanlari(sonuc, *, model: str, kosulsuz: bool = False) -> dict:
    """AI Hub analiz yanıtına EKLENEN v2/v3 alanları — gömülü uç (`ai_router`) ve GPU servisi (`ai_service`) AYNI kümeyi
    döndürsün diye tek yerde. Mevcut alanlar (`n_tumor`, `tumor_regions`, `n_wells`, `wells`, `centroid_cabin_mm`, `D`,
    `E_cancer`, `mm_per_px` …) çağıranın kendi sözlüğünde KALIR; bunlar yalnız EKTİR (eski istemci yok sayar).
    `well_id` / `tumor_id` kuyucuk / tümör sözlüklerinin içinde zaten gelir (`asdict`)."""
    d = {
        "pemf_valid": _al(sonuc, "pemf_valid") is True,
        "warnings": _uyari_listesi(_al(sonuc, "warnings")),
        "coord_frame": str(_al(sonuc, "coord_frame") or ""),
        "pemf_kapisi": degerlendir(sonuc, model=model, kosulsuz=kosulsuz),
        "kosulsuz": kosulsuz is True,
        # KD · Y258: sabit düzlem kalibrasyonu özeti (kip, geçerli, engeller, sahne / kuyu aralığı / fantom boyu ölçümü) — YALNIZ EK.
        "kalibrasyon": dict(_al(sonuc, "kalibrasyon") or {}),
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
        d["pemf_source"] = {"cabin_aruco": "aruco", "cabin_placement": "placement", "cabin_plane": "sabit_duzlem"}.get(
            d["coord_frame"], ""
        )
    return d


def degerlendir(sonuc, *, model: str, kosulsuz: bool = False) -> dict:
    """Hocanın §3 sırasıyla değerlendir → `{"surulebilir", "pemf_gecerli", "nedenler", "engelleyici", "yeniden_cekim",
    "uyari_kodlari", "eylem", "mesajlar", "varsayimlar"}`. `model`: "petri" | "fantom".

    `surulebilir` False ise sonuç bobine / `_predict_and_drive`'a GİTMEZ. AI Hub tek-foto analizi D/P/E'yi yine gösterir
    ama `mesajlar`daki eylem metniyle (D/P/E "geçersiz" etiketlidir).
    `kosulsuz` (Y189): yalnız `KOSULSUZDA_KALAN` nedenleri sürüşü keser; diğerleri `atlanan`da (uyarı) — modül docstring'i."""
    if model not in ("petri", "fantom"):
        raise ValueError(f"pemf kapısı: bilinmeyen model {model!r}")
    # Y189: YALNIZ gerçek True açar — doğruluk değeri taşıyan başka nesne (ör. doğrudan çağrıda FastAPI `Form(False)` FieldInfo'su)
    # koşullu kalır (fail-closed).
    kosulsuz = kosulsuz is True
    nesne = "plakanın" if model == "petri" else "fantomun"
    nesne_yalin = "plakaya" if model == "petri" else "fantoma"
    kodlar = uyari_kodlari(_al(sonuc, "warnings") or [])
    # KD: hat hedef üretmeden durduysa (`error` fiziksel kodla başlar: fantom boyu farklı) neden O koddur — "analiz sonuç üretmedi"
    # değil; uyarılarda gelen fiziksel kodlar da AYNI listeye.
    hata_kodlari = uyari_kodlari([_al(sonuc, "error")]) if _al(sonuc, "error") else []
    fiziksel = [k for k in FIZIKSEL if k in kodlar or k in hata_kodlari]
    nedenler: list[str] = []
    if _al(sonuc, "success") is not True and not any(k in hata_kodlari for k in FIZIKSEL):
        nedenler.append("basarisiz")
    pemf = _al(sonuc, "pemf_valid") is True
    if not pemf and not fiziksel:
        # Fiziksel neden zaten "konum neden yok"u söyler; genel (ArUco öneren) metin YANLIŞ yönlendirirdi.
        nedenler.append("pemf_gecersiz")
    nedenler += fiziksel
    if model == "fantom" and _al(sonuc, "reliable") is not True:
        nedenler.append("guvenilir_degil")
    engel = [k for k in ENGELLEYICI if k in kodlar]
    yeniden = [k for k in YENIDEN_CEKIM if k in kodlar]
    nedenler += engel + yeniden
    hata = str(_al(sonuc, "error") or "bilinmeyen hata")
    mesajlar = [
        {"kod": n, "metin": _EYLEM[n].format(nesne=nesne, nesne_yalin=nesne_yalin, hata=hata)} for n in nedenler
    ]
    # Y189: koşulsuz kipte yalnız fiziksel nedenler keser; geri kalanı ATLANIR ama listede kalır (uyarı olarak gösterilir).
    kesen = [n for n in nedenler if n in KOSULSUZDA_KALAN] if kosulsuz else list(nedenler)
    atlanan = [n for n in nedenler if n not in kesen]
    return {
        "surulebilir": not kesen,
        "kosulsuz": kosulsuz,
        "atlanan": atlanan,
        "pemf_gecerli": pemf,
        "nedenler": nedenler,
        "engelleyici": engel,
        "yeniden_cekim": yeniden,
        "uyari_kodlari": kodlar,
        "eylem": mesajlar[0]["metin"] if mesajlar else "",
        "mesajlar": mesajlar,
        "varsayimlar": varsayimlar(sonuc, model=model),
    }
