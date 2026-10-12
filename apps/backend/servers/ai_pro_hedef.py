# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI PRO HEDEF SAĞLAYICILARI — kapalı döngünün model-bağımsız arayüzü (Faz 1, 2026-09-08).

NEDEN: AI Pro kapalı döngüsünün güvenlik iskeleti (hazırlık → öneri → onay → seans, kare
sahipliği, hedef-kaybı STOP, E-stop teardown, 7 bobin per-coil sürüş) model-bağımsızdır; kediye
bağlılık `servers/ai_router.py`de beş noktada toplanır. Sahip isteğiyle araştırma modunda kedi
yerine iki model gelecek (Fantom Tümör, Petri Kuyu) → bu beş nokta tek bir arayüzün arkasına
alınır ki döngü, kilitler, cache, onay mührü ve teardown DEĞİŞMESİN.
Plan: docs/arastirma-ai-pro-fantom-petri-plani.md

⚠️ KEDİ KODU TAŞINMADI. `KediSaglayici` yalnız `ai_router`daki mevcut fonksiyonlara GEÇ BAĞLI
delegasyon yapar (`_get_or_load_kedi`, `_get_or_load_catorgan`, `_localize_organ_cpu/_gpu`,
`_predict_and_drive_cpu/_gpu`). Böylece 13+ testin monkeypatch çıpaları ETKİLİ kalır ve
veteriner davranışı bit-bit aynıdır. Fantom/petri sağlayıcıları Faz 2'de bu dosyaya eklenecek.

⚠️ ai_hub İMPORT'U MODÜL SEVİYESİNDE YASAK: `scripts/build_backend_exe.ps1` PYZ arşivinde
ai_hub bytecode'u görürse build'i durdurur (kod koruması: ai_hub yalnız .pyd olarak sevk edilir).
Tüm ai_hub erişimi fonksiyon gövdesinde olmalı — ai_router'ın kendi deseni de budur.
Kapı: tests/test_ai_pro_saglayici_delegasyon.py

SÖZLEŞMELER (kedi yolundan türetildi, DEĞİŞTİRİLMEDİ):
  localize(frame_bgr, hedef_id) -> (localized, x_mm, y_mm, z_mm, guven, overlay_bgr,
                                    ozne_var, guven_dokumu)   ← 8'li; ÇAĞIRANLAR YILDIZLI AÇAR
  predict(x_mm, y_mm, z_mm, hedef_id) -> (D[7], P[7], e_field)   ← HAM; duty kırpması
      `_predict_and_drive` ZARFINDA yapılır (tek yer, tüm sağlayıcılar için aynı).
"""

from __future__ import annotations

import functools
from typing import Protocol, runtime_checkable

# Kedi kapalı döngüsünün ekstra EM girdileri (ai_router'daki tarihsel sabitler; DEĞİŞMEDİ).
KEDI_ACHIEVED_B = 0.001  # Tesla (1 mT)
KEDI_DUTY_SUM = 1.5


@runtime_checkable
class HedefSaglayici(Protocol):
    """Kapalı döngünün bir hedef ailesinden beklediği her şey.

    `ad` istemciden `model` alanıyla gelir, onay mührüne (`specs.model`) yazılır ve seans
    başlangıcında MÜHÜRDEN okunur — "fantom öner, kedi başlat" yapısal olarak imkânsızdır.
    """

    ad: str
    """'kedi' | 'fantom' | 'petri' — tel sözleşmesindeki `model` değeri."""

    title: str
    """Kullanıcıya görünen ad ('Kedi Organ'). Seans mode dizesi `AI Pro · {title}` olur;
    ⚠️ 'AI' öneki korunmalı (api_server ve ai_router'da `startswith('AI')` kontrolleri var)."""

    subject_label: str
    """Kadrajda aranan ÖZNE ('hayvan' | 'fantom' | 'petri plakası') — ipucu metinleri için."""

    def hedef_idleri(self) -> "frozenset[int]":
        """Geçerli hedef kimlikleri. Kedi: 0-6 (0 = Tüm Vücut). Dört doğrulama noktası
        (propose/start/organ/hazirlik) bu kümeyi TEK KAYNAK olarak kullanır."""
        ...

    def yukle(self) -> None:
        """Ağır modelleri ısıt. Hazırlık ve seans döngüleri kamerayı açmadan ÖNCE çağırır."""
        ...

    def localize(self, frame_bgr, hedef_id: int) -> tuple:
        """Kareden hedefi bul → 8'li tuple (yukarıdaki sözleşme)."""
        ...

    def predict(self, x_mm: float, y_mm: float, z_mm: float, hedef_id: int) -> tuple:
        """EM doz modeli → (D[7], P[7], e_field). HAM değer döner; kırpma zarfta."""
        ...

    def hedef_adi(self, hedef_id: int) -> str:
        """UI/WS/mühür etiketi ('Mide')."""
        ...

    def ipucu(self, ozne_var: bool, hedef_adi: str) -> str:
        """409/şerit metni: operatöre NE YAPACAĞINI söyler (eylem söyleyen hata kuralı)."""
        ...

    def xai_sensitivity(self, x_mm: float, y_mm: float, z_mm: float, hedef_id: int):
        """Onay ekranı için hafif duyarlılık dökümü; hata öneriyi DÜŞÜRMEZ (zarif düşüş)."""
        ...


class KediSaglayici:
    """Mevcut kedi yolu (`cat_organ` lokalizasyon + `em_kedi` doz modeli) — DAVRANIŞ DEĞİŞMEZ.

    Her çağrı `ai_router`daki üretim fonksiyonlarına gider; bu dosyada kedi mantığının KOPYASI
    YOKTUR. `ai_router` importu fonksiyon içindedir (döngüsel import: ai_router bu modülü modül
    seviyesinde import eder).
    """

    ad = "kedi"
    title = "Kedi Organ"
    subject_label = "hayvan"
    achieved_B = KEDI_ACHIEVED_B
    duty_sum = KEDI_DUTY_SUM
    join_timeout_s = 6.0
    varsayilan_hedef = 0

    def hedef_idleri(self) -> "frozenset[int]":
        # em_kedi ORGAN_IDS = 0-6. cat_organ 7-10'u da lokalize eder ama em_kedi onları TEDAVİ
        # etmez (Audit P2: sessiz-sıfır) → kapalı döngüde 0-6 dışı reddedilir.
        return frozenset(range(0, 7))

    def yukle(self) -> None:
        from servers import ai_router as air

        air._get_or_load_kedi()
        air._get_or_load_catorgan()

    def localize(self, frame_bgr, hedef_id: int) -> tuple:
        """cat_organ ile lokalize et (GPU servisi açıksa oraya devret, hata → CPU-yerel).
        ⚠️ Gövde `_localize_organ`ın 2026-08-25'teki hâlidir; fallback deseni korunmuştur."""
        from servers import ai_router as air

        sonuc = None
        if air.ai_service_enabled():
            try:
                sonuc = air._localize_organ_gpu(frame_bgr, hedef_id)
            except Exception as e:
                air.logger.warning("AI Pro cat_organ GPU delegasyonu başarısız → CPU-yerel: %s", e)
        if sonuc is None:
            sonuc = air._localize_organ_cpu(frame_bgr, hedef_id)
        self._ood_isaretle(sonuc)
        return sonuc

    def _ood_isaretle(self, sonuc) -> None:
        """İG-5.22: hedef em_kedi'nin eğitim aralığı DIŞINDA mı? Eskiden kedi meta'sı hep boştu → `/propose` `ood` kedi
        hattında HEP false (D0: 50 rastgele hedefin 36'sı |z| > 2,5 iken). ⚠️ Y49: yalnız GÖSTERİM/İZ — `sonuc` değişmez,
        hedef aynen sürülür (yeni red ya da kıskaç YOK, Ö.4-Y9). Lokalize edilemeyen karede işaret YOK (bayat kalmaz)."""
        try:
            ood = bool(sonuc[0]) and _aralik_disi(
                _kedi_egitim_araligi(), float(sonuc[1]), float(sonuc[2]), float(sonuc[3])
            )
        except Exception:
            ood = False
        # AII-2.6 (yalnız METİN): organ bulundu (güven > 0) ama konum reddedildi — `_extract_organ_target` kabin DIŞI / geçersiz
        # konumda (0, 0, 0) + güven döner (düşük güvende kısılmış konum, organ yoksa güven 0) → ipucu açıyı değil KABİN İŞARETİNİ
        # söyler. Eşik OKUNMAZ (A-23 bağımsızlığı); meta'ya yazılmaz (veteriner sözleşmesi: yalnız `ood`). Sürüş değişmez.
        try:
            self._kabin_disi = not bool(sonuc[0]) and float(sonuc[4]) > 0.0 and not any(float(v) for v in sonuc[1:4])
        except Exception:
            self._kabin_disi = False
        self._meta = {"ood": ood}

    def predict(self, x_mm: float, y_mm: float, z_mm: float, hedef_id: int) -> tuple:
        """em_kedi ile D/P/E üret (GPU → CPU fallback). Duty kırpması ZARFTA yapılır."""
        from servers import ai_router as air

        if air.ai_service_enabled():
            try:
                return air._predict_and_drive_gpu(x_mm, y_mm, z_mm, hedef_id)
            except Exception as e:
                air.logger.warning("AI Pro em_kedi GPU delegasyonu başarısız → CPU-yerel: %s", e)
        return air._predict_and_drive_cpu(x_mm, y_mm, z_mm, hedef_id)

    def hedef_adi(self, hedef_id: int) -> str:
        from servers import ai_router as air

        return air._ORGAN_NAMES.get(int(hedef_id), "")

    def ipucu(self, ozne_var: bool, hedef_adi: str) -> str:
        """2026-08-24 sahip isteği: "hayvan yok" ile "hayvan var, organ görünmüyor" AYRI eylem
        gerektirir; metinler o günkü hâliyle korunur (kaynak-regex kapısı bunları arar)."""
        ad = hedef_adi or "hedef organ"
        if ozne_var and getattr(self, "_kabin_disi", False):
            return (
                f"{ad} konumu kabin DIŞINDA ölçüldü — açıyı değiştirmek çözmez: kabin işaretinin (arka duvardaki kare kod) "
                "kadrajda, düz ve parlamasız göründüğünü kontrol edin; sürerse kabin yapılandırmasını teknik desteğe doğrulatın."
            )
        if ozne_var:
            return f"Hayvan görünüyor ama {ad} seçilemedi — kamerayı biraz çevirip açıyı değiştirin."
        return "Kamerayı hastaya doğrultun; hayvan kadrajda görünmüyor."

    def son_lokalizasyon_meta(self) -> dict:
        """Kedi hattı kare üstü HEDEF ADAYI üretmez (organ seçimi çiplerden yapılır) → targets/method/E YOK.
        İG-5.22: yalnız `ood` (eğitim aralığı dışı — onay ekranı uyarısı) taşınır; veteriner sözleşmesi değişmez."""
        return dict(getattr(self, "_meta", None) or {})

    def xai_sensitivity(self, x_mm: float, y_mm: float, z_mm: float, hedef_id: int):
        from ai_hub.em_kedi import inference_em_kedi as _iek
        from servers import ai_router as air

        # ⚠️ BAZ NOKTASI DÜZELTMESİ (sahip kararı #9, 2026-09-09): açıklama, dozun FİİLEN
        # hesaplandığı ekstra girdilerle üretilmeli. Eskiden bu çağrı achieved_B/duty_sum
        # vermiyordu → modülün varsayılanları (0.001 / 2.0) kullanılıyor, oysa doz 1.5 duty_sum
        # ile üretiliyordu. "Dozu en çok ne belirledi" satırı başka bir çalışma noktasını
        # açıklıyordu (XAI vekil-nokta kayması).
        return _iek.xai_hizli_sensitivity(
            air._get_or_load_kedi(),
            x_mm,
            y_mm,
            z_mm,
            hedef_id,
            achieved_B=self.achieved_B,
            duty_sum=self.duty_sum,
        )


# Kayıt: anahtar = tel sözleşmesindeki `model` değeri. Araştırma sağlayıcıları dosyanın
# SONUNDA kayda eklenir (Faz 2) — tanımları KediSaglayici'dan sonra gelir.
SAGLAYICILAR: "dict[str, object]" = {
    KediSaglayici.ad: KediSaglayici(),
}

VARSAYILAN_MODEL = KediSaglayici.ad


def saglayici_al(model: "str | None"):
    """`model` adından sağlayıcı. Bilinmeyen ad → ValueError (çağıran 422'ye çevirir).

    Boş/None → varsayılan 'kedi': `model` alanını göndermeyen ESKİ istemciler (ve mobil kare
    yolu) bugünkü davranışı aynen sürdürür.
    """
    ad = (model or VARSAYILAN_MODEL).strip().lower()
    try:
        return SAGLAYICILAR[ad]
    except KeyError:
        gecerli = "|".join(sorted(SAGLAYICILAR))
        raise ValueError(f"Model '{model}' tanınmıyor (geçerli: {gecerli})") from None


# ══════════════════════════════════════════════════════════════════════════════════════════
# ARAŞTIRMA SAĞLAYICILARI — Fantom Tümör / Petri Kuyu (Faz 2, 2026-09-09)
# ══════════════════════════════════════════════════════════════════════════════════════════
# ⚠️ SÜRÜŞ BAYRAK ARKASINDA: `PEMF_ARASTIRMA_AIPRO` kapalıyken bu sağlayıcılarla ÖNERİ ve SEANS
# reddedilir (ai_router `_arastirma_aipro_kapisi`). Neden: phantom_cv_v3/petri_cv_v2 koordinat dönüşümü
# marker→kabin ROTASYONUNU uygulamıyor ve kesişimi kabin Z=plate_z düzleminde alıyor; kedi hattı
# kabin-merkezli PnP kullanıyor → iki hattın AYNI çerçeveyi ürettiği KANITLANMADI (plan kararı #6).
# Hazırlık/önizleme ve AI Hub tek-foto analizi bayraktan BAĞIMSIZ çalışır.

#: Kalibrasyon YÖNTEMİ tavanı (kararlar #4 ve #7). ArUco dışı yöntemlerde tavan `MIN_GUVEN`in
#: ALTINDA → hedef YAPISAL olarak "bulunamadı" sayılır: kapalı döngüde ArUco ZORUNLU (karar #4) ve
#: piksel/ölçek modunda koordinat kabin çerçevesinde değildir (nesne-merkezli, z=0).
YONTEM_TAVANI = {"aruco_pnp": 1.0}
YONTEM_TAVANI_VARSAYILAN = 0.25

#: Kedi hattındaki `_MIN_RELIABILITY` ile aynı eşik (0.3) — kedi tarafı DEĞİŞMEDİ.
MIN_GUVEN = 0.3

#: Hedef takibi: eşleşme mesafesi hedefin yarıçapının bu katından büyükse AYNI hedef sayılmaz.
TAKIP_YARICAP_KATI = 1.0


def _yontem_tavani(method: str) -> float:
    return YONTEM_TAVANI.get((method or "").strip().lower(), YONTEM_TAVANI_VARSAYILAN)


def _sayi_ya_da_none(v):
    """D1.E07: hesaplanmamış (None) ya da sonlu olmayan değer None kalır; sayı float'a çevrilir (0.0 uydurulmaz, Y6)."""
    import math

    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def kabin_yari_boyut_mm():
    """Kabin YARI boyutları (mm) — TEK KAYNAK: kedi hattının (`catorgan_predictor`) yüklediği AYNI paketli kabin
    yapılandırması (`geometry.cabin_extent_cm`; bugün [65, 50, 50] cm → (325, 250, 250) mm). Literal YAZILMAZ: kabin
    yeniden ölçülünce (A-17) sınır kendiliğinden izler. Okunamaz / geçersizse None (çağıran FAIL-CLOSED davranır)."""
    import math

    try:
        from ai_hub.inference_cat_organ.lib.cabin_config import load_cabin_config, varsayilan_kabin_yaml

        ext = (load_cabin_config(varsayilan_kabin_yaml()).get("geometry") or {}).get("cabin_extent_cm")
        yari = tuple(float(v) * 10.0 / 2.0 for v in ext)
    except Exception:
        import logging

        logging.getLogger(__name__).warning("Kabin boyutu okunamadı (kabin yapılandırması)", exc_info=True)
        return None
    if len(yari) != 3 or not all(math.isfinite(v) and v > 0 for v in yari):
        return None
    return yari


def _aralik_disi(aralik, x_mm: float, y_mm: float, z_mm: float) -> bool:
    """Konum (x, y, z) verilen [(alt, üst)] eğitim aralığının DIŞINDA mı? Aralık yoksa False (bilinmiyor ≠ dışarıda).
    TEK ölçüt: araştırma sağlayıcıları ve (İG-5.22) kedi hattı aynı kuralı kullanır. Sürüşü ENGELLEMEZ (gösterim/iz)."""
    if not aralik:
        return False
    for deger, (alt, ust) in zip((x_mm, y_mm, z_mm), aralik):
        if deger < alt or deger > ust:
            return True
    return False


@functools.lru_cache(maxsize=1)
def _kedi_egitim_araligi():
    """em_kedi'nin (x, y, z) eğitim aralığı — modülün `xai_ref_stats()` referans örnekleminden OKUNUR (sabit yazılmaz;
    model yeniden eğitilirse kendiliğinden güncellenir)."""
    from ai_hub.em_kedi import inference_em_kedi as iek

    bg = iek.xai_ref_stats()["background"]
    return tuple((float(bg[:, i].min()), float(bg[:, i].max())) for i in range(3))


def hedef_kabin_disi_nedeni(x_mm, y_mm, z_mm) -> str:
    """D1.85 (B-5.11): 3B hedef sürülebilir mi? "" = sonlu ve kabin İÇİNDE; değilse operatöre/günlüğe NEDEN.

    ⚠️ NEDEN: kedi hattında cm→mm ±300 kıskacı kabin DIŞI hedefi (Y/Z sınırı 250 mm) sessizce kenara çekip
    SÜRÜYORDU (telde 51/51 çerçeve (300,-300,-300) mm); NaN `min/max`tan 300 mm olarak çıkıyordu; araştırma
    sağlayıcılarında sınır denetimi hiç yoktu. Bu bir HEDEF GEÇERLİLİK (lokalizasyon) denetimidir — tedavi doz
    kıskacı değil (Ö.4-Y9 temiz); `normalize_*` değişmez. Kabin boyutu bilinmiyorsa hedef doğrulanamaz → red."""
    import math

    try:
        v = (float(x_mm), float(y_mm), float(z_mm))
    except (TypeError, ValueError):
        return "kabin denetimi: koordinat sayı değil"
    if not all(math.isfinite(a) for a in v):
        return f"kabin denetimi: sonlu olmayan koordinat {v}"
    yari = kabin_yari_boyut_mm()
    if yari is None:
        return "kabin boyutu okunamadı (kabin yapılandırması) — hedef doğrulanamadı"
    disari = [eksen for eksen, a, s in zip("xyz", v, yari) if abs(a) > s]
    if disari:
        return (
            f"kabin DIŞI hedef {tuple(round(a, 1) for a in v)} mm (kabin yarı boyutu {yari} mm, eksen "
            f"{''.join(disari)})"
        )
    return ""


def _hedef_tel(aday: dict, kare_w: int, kare_h: int) -> dict:
    """Aday → TEL SÖZLEŞMESİ sözlüğü; `pxn` = kare oranına göre 0..1 merkez.

    ⚠️ `pxn` ŞART: `px` ham kare pikselidir, WS önizlemesi kareyi 960 px'e küçültür ve
    `imageW/imageH` KÜÇÜLTÜLMÜŞ boyutu taşır. Panel halkalarını ham piksel/küçültülmüş
    genişlik ile yerleştirmek işaretleri hedeften kaydırır (aynı sınıf hata [S7 adım 6]'da
    overlay ölçeğinde yaşandı). 0..1 oranı hem /status hem WS hem /frame için ÖLÇEK-BAĞIMSIZ.
    """
    d = {k: v for k, v in aday.items() if k in ("id", "label", "px", "x", "y", "z", "organ_id", "reliability")}
    px = aday.get("px") or (0.0, 0.0)
    if kare_w > 0 and kare_h > 0:
        d["pxn"] = [
            round(min(1.0, max(0.0, float(px[0]) / float(kare_w))), 5),
            round(min(1.0, max(0.0, float(px[1]) / float(kare_h))), 5),
        ]
    return d


def _yaricap_px(bbox) -> float:
    """bbox (x, y, w, h) → yaklaşık yarıçap (px). Takip eşleşmesi için ölçek."""
    try:
        _x, _y, w, h = (float(v) for v in bbox)
        return max(1.0, max(w, h) / 2.0)
    except Exception:
        return 1.0


class _EmCvSaglayici:
    """phantom_cv_v3 / petri_cv_v2 ortak sağlayıcı iskeleti (hedef bulma + doz + takip).

    Alt sınıflar `_yukleyici`, `_pipeline_kur`, `_adaylar`, `_ozne_yok_hatalari`,
    `_ipucu_ozne_yok`, `_egitim_araligi` ve `_xai_modulu`nu verir.

    ⚠️ ÖNBELLEK PAYLAŞIMI ZORUNLU: `localize` her karede HAFİF bir pipeline kurar ama ağır modelleri
    (ONNX / YOLO) `ai_router._get_or_load_model` önbelleğinden ENJEKTE eder. Enjeksiyon olmazsa
    `PhantomCvPipeline.predictor` lazy property'si her karede 60 MB ONNX'i, petri her karede 90 MB
    YOLO'yu yeniden açar → kareler saniyelere çıkar. Analiz uçları da AYNI önbelleği kullanır.
    """

    ad = ""
    # AI-2: PEMF tüketim kapısının profili ("fantom" | "petri") — `ad`dan AYRI: test/alt sağlayıcı kendi adını taşıyabilir,
    # kapı profili ise yalnız bilinen iki CV hattından biri olabilir. Boş kalırsa kapı ValueError verir (sessiz geçiş YOK).
    kapi_modeli = ""
    title = ""
    subject_label = ""
    onbellek_anahtari = ""
    hedef_etiketi = "Hedef"
    join_timeout_s = 6.0
    varsayilan_hedef = 0
    #: Kabul edilen EN FAZLA hedef (0 = otomatik seçim, 1..N = kare üstünde elle seçim).
    azami_hedef = 8

    def __init__(self):
        import threading

        self._kilit = threading.Lock()
        self._meta: dict = {}
        self._kimlikler: list = []  # kalıcı kimlikler: {"id", "ad", "px", "organ_id"}
        # AII-2.1: kaybolan kimlikler (son konumlarıyla) ve verilmiş EN BÜYÜK kimlik — kimlik BAŞKA hedefe yeniden verilmez.
        self._kayip_kimlikler: dict = {}
        self._son_kimlik = 0

    # ── alt sınıf sözleşmesi ────────────────────────────────────────────────────────────
    def _yukleyici(self):
        raise NotImplementedError

    def _pipeline_kur(self, cache):
        raise NotImplementedError

    def _adaylar(self, result) -> list:
        raise NotImplementedError

    def _ozne_yok_hatalari(self) -> tuple:
        return ()

    def _ipucu_ozne_yok(self) -> str:
        raise NotImplementedError

    def _egitim_araligi(self):
        raise NotImplementedError

    def _xai_modulu(self):
        raise NotImplementedError

    # ── ortak ──────────────────────────────────────────────────────────────────────────
    @property
    def achieved_B(self) -> float:
        """Ekstra EM girdisi — kabin yapılandırmasından (karar #5: analiz paneliyle AYNI)."""
        try:
            return float(self._onbellek()["cfg"].phantom.achieved_B)
        except Exception:
            return 0.001

    @property
    def duty_sum(self) -> float:
        try:
            return float(self._onbellek()["cfg"].phantom.duty_sum)
        except Exception:
            return 2.4

    def hedef_idleri(self) -> "frozenset[int]":
        return frozenset(range(0, self.azami_hedef + 1))

    def _onbellek(self) -> dict:
        from servers import ai_router as air

        return air._get_or_load_model(self.onbellek_anahtari, self._yukleyici())

    def yukle(self) -> None:
        self._onbellek()

    def hedef_adi(self, hedef_id: int) -> str:
        hid = int(hedef_id)
        if hid == 0:
            return f"{self.hedef_etiketi} (otomatik)"
        with self._kilit:
            for k in self._kimlikler:
                if k.get("id") == hid:
                    return str(k.get("ad") or f"{self.hedef_etiketi} {hid}")
        return f"{self.hedef_etiketi} {hid}"

    def ipucu(self, ozne_var: bool, hedef_adi: str) -> str:
        if not ozne_var:
            return self._ipucu_ozne_yok()
        with self._kilit:
            yontem = str(self._meta.get("method") or "")
            kapi = dict(self._meta.get("pemf_kapisi") or {})
        if yontem and yontem != "aruco_pnp":
            return (
                "Konum ölçülemedi: kabin işareti (arka duvardaki kare kod) kadrajda görünmüyor. "
                "Kamerayı işaret ve hedef AYNI karede kalacak şekilde ayarlayın."
            )
        # AI-2: hocanın tüketim kapısı kareyi kestiyse NEDENİ ve EYLEMİ (pemf geçersiz / güvenilmez / yerleşim uyuşmuyor /
        # kontrol kuyucuğu / yeniden çekim) — "hedef seçilemedi" demek operatörü yanlış yere yönlendirirdi.
        if kapi and not kapi.get("surulebilir", True) and kapi.get("eylem"):
            return str(kapi["eylem"])
        return (
            f"{hedef_adi} seçilemedi — hedefi tepsinin ortasına alın, kabin ışığını artırın ve "
            "işaret üzerinde parlama olmadığından emin olun."
        )

    def son_lokalizasyon_meta(self) -> dict:
        with self._kilit:
            return dict(self._meta)

    def _kimlik_ata(self, adaylar: list) -> list:
        """Adaylara KALICI kimlik ver: merkez-yakınlıkla önceki karenin kimliğine eşle.

        Petri kuyuları her karede (cy//50, cx) ile yeniden sıralanır → sıra numarası KARARSIZDIR.
        Onay mührüne yazılan etiket ("Kuyu 3") seans şeridinde başka bir kuyuya kaymasın diye kimlik
        ATANIR ve korunur. Eşleşme hedefin yarıçapı İÇİNDE olmak zorundadır (uzaktaki komşu kuyuya
        kilitlenme yok).
        """
        with self._kilit:
            eski = list(self._kimlikler)
            kayip = list(self._kayip_kimlikler.values())
            son_kimlik = self._son_kimlik
        yeni, kullanilan = [], set()

        def _en_yakin(aday, havuz):
            px = aday.get("px") or (0.0, 0.0)
            r = _yaricap_px(aday.get("bbox"))
            en_iyi, en_iyi_d = None, None
            for k in havuz:
                if k["id"] in kullanilan:
                    continue
                kpx = k.get("px") or (0.0, 0.0)
                d = ((px[0] - kpx[0]) ** 2 + (px[1] - kpx[1]) ** 2) ** 0.5
                if d <= r * TAKIP_YARICAP_KATI and (en_iyi_d is None or d < en_iyi_d):
                    en_iyi, en_iyi_d = k, d
            if en_iyi is not None:
                kullanilan.add(en_iyi["id"])
                aday["id"] = en_iyi["id"]
                aday["label"] = en_iyi["ad"]

        for aday in adaylar:
            _en_yakin(aday, eski)
            yeni.append(aday)
        # ⚠️ AII-2.1 (A-16 · D1.60 2. katman): mühür ve döngü KİMLİĞİ karşılaştırır. Eskiden yeni kimlik "önceki karenin
        # en büyüğü + 1" idi → önceki karede görünmeyen (tespiti düşen) hedefin kimliği BAŞKA bir yeni adaya veriliyordu ve
        # döngü onaylanan tümör yerine komşusunu sürüyordu (ölçüldü). Eşleşmeyen aday önce KAYBOLAN bir kimliğin son konumuna
        # (yarıçap içinde) bakar — aynı hedef kimliğini geri alır; değilse HİÇ VERİLMEMİŞ bir kimlik alır.
        for aday in yeni:
            if not aday.get("id"):
                _en_yakin(aday, kayip)
        sonraki = max([son_kimlik] + [k["id"] for k in eski] + [a.get("id") or 0 for a in yeni] + [0]) + 1
        for aday in yeni:
            if not aday.get("id"):
                aday["id"] = sonraki
                # AI-2: CV SABİT kimliği (petri v2 kuyucuk A1–D6, fantom v3 KAYITLI tümör T1–T5) varsa etiket odur;
                # eşleşen (takip edilen) hedef ilk görüldüğü etiketi KORUR — mühürlü etiket karede değişmez.
                aday["label"] = aday.get("label") or f"{self.hedef_etiketi} {sonraki}"
                sonraki += 1
        with self._kilit:
            etkin = {a["id"] for a in yeni}
            for k in eski:
                if k["id"] not in etkin:
                    self._kayip_kimlikler[k["id"]] = k
            for kid in etkin:
                self._kayip_kimlikler.pop(kid, None)
            self._son_kimlik = max([self._son_kimlik] + list(etkin))
            self._kimlikler = [
                {"id": a["id"], "ad": a["label"], "px": a.get("px"), "organ_id": a.get("organ_id")} for a in yeni
            ]
        return yeni

    def _hedef_sec(self, adaylar: list, hedef_id: int):
        """hedef_id 0 → otomatik (en yüksek `oncelik`), aksi hâlde KALICI kimliğe göre."""
        if not adaylar:
            return None
        hid = int(hedef_id)
        if hid == 0:
            return max(adaylar, key=lambda a: (a.get("oncelik", 0.0), a.get("reliability", 0.0)))
        for a in adaylar:
            if a.get("id") == hid:
                return a
        return None

    def _egitim_araligi_disi(self, x_mm: float, y_mm: float, z_mm: float) -> bool:
        """Konum, modelin XAI referans dağılımının (eğitim örnekleminin) DIŞINDA mı?

        Onay ekranındaki "araştırma amaçlı model tahmini" uyarısını besler; sürüşü ENGELLEMEZ.
        Aralık testte/sabitte YAZILMAZ, modülün `xai_ref_stats()` background örnekleminden OKUNUR →
        model yeniden eğitilirse kendiliğinden güncellenir."""
        try:
            arali = self._egitim_araligi()
        except Exception:
            return False
        return _aralik_disi(arali, x_mm, y_mm, z_mm)  # İG-5.22: kedi hattıyla TEK ölçüt

    def localize(self, frame_bgr, hedef_id: int) -> tuple:
        """Kareden hedefi bul → kedi ile AYNI 8'li tuple sözleşmesi."""
        from servers import ai_router as air

        cache = self._onbellek()
        pl = self._pipeline_kur(cache)
        try:
            result, ctx = pl.process_image(frame_bgr, achieved_B=self.achieved_B, duty_sum=self.duty_sum)
        except Exception as e:
            air.logger.error("%s lokalizasyon hatası: %s", self.ad, e)
            with self._kilit:
                self._meta = {"model": self.ad, "hata": "pipeline", "targets": []}
            return (False, 0.0, 0.0, 0.0, 0.0, None, False, None)

        # Kare boyutu `pxn` (kare-oranlı hedef merkezi) için. ⚠️ SAVUNMALI okuma: boyutu
        # olmayan bir girdi lokalizasyonun TAMAMINI çökertmesin — `pxn` yalnız SUNUM alanıdır,
        # yokluğunda panel halkaları çizmez (liste yedeği çalışmaya devam eder).
        _boyut = getattr(frame_bgr, "shape", None)
        _kare_h, _kare_w = (int(_boyut[0]), int(_boyut[1])) if _boyut else (0, 0)
        basarili = bool(getattr(result, "success", False))
        hata = (getattr(result, "error", "") or "").strip()
        # Özne (fantom/plaka) kadrajda mı? Bu ayrım operatöre NE YAPACAĞINI söyler: özne yoksa
        # yerleşim, varsa açı/ışık/işaret sorunu (kedi hattındaki `kedi_var` mandalının karşılığı).
        ozne_var = basarili or hata not in self._ozne_yok_hatalari()
        overlay = self._overlay(pl, ctx, result) if basarili else None
        yontem = str(getattr(result, "method", "") or "")
        tavan = _yontem_tavani(yontem)

        adaylar = self._kimlik_ata(self._adaylar(result)) if basarili else []
        secili = self._hedef_sec(adaylar, hedef_id)

        meta = {
            "model": self.ad,
            "method": yontem,
            "mm_per_px": float(getattr(result, "mm_per_px", 1.0) or 1.0),
            "yontem_tavani": tavan,
            "frame_w": _kare_w,
            "frame_h": _kare_h,
            "targets": [_hedef_tel(a, _kare_w, _kare_h) for a in adaylar],
            "hata": hata,
        }
        # ⚠️ AI-2 (plan §3.9 · hocanın ENTEGRASYON §3): bobine giden yolda tüketim kapısı — `success`, `pemf_valid`,
        # fantomda `reliable`, engelleyici uyarılar (`layout_mismatch`, `control_cancer_missed`, `control_healthy_flagged`)
        # ve yeniden-çekim uyarıları (`oblique_view`, `low_resolution`, `ring_partial`). Geçmezse kare LOKALİZE SAYILMAZ:
        # `/propose` taze hedef bulamaz (409 + eylem), seans döngüsü sürmez, `_predict_and_drive` ÇAĞRILMAZ. FAIL-CLOSED ve
        # `PEMF_ARASTIRMA_AIPRO` bayrağından BAĞIMSIZ (bayrak sürüşü açar, bu kapı geçersiz sonucu yine keser). Hedef
        # adayları meta'da kalır (operatör ne görüldüğünü görür) ama hiçbiri seçili değildir.
        if basarili:
            from ai_hub.cv_ortak import pemf_kapisi

            kapi = pemf_kapisi.degerlendir(result, model=self.kapi_modeli)
            meta["pemf_kapisi"] = kapi
            if not kapi["surulebilir"]:
                air.logger.warning("%s karesi tüketim kapısında REDDEDİLDİ: %s", self.ad, kapi["nedenler"])
                with self._kilit:
                    self._meta = meta
                return (False, 0.0, 0.0, 0.0, 0.0, overlay, True, None)
        if secili is None:
            with self._kilit:
                self._meta = meta
            return (False, 0.0, 0.0, 0.0, 0.0, overlay, ozne_var, None)

        for t in meta["targets"]:
            t["secili"] = t.get("id") == secili.get("id")
        ham = float(secili.get("reliability", 0.0))
        guven = ham * tavan
        x_mm = float(secili.get("x", 0.0))
        y_mm = float(secili.get("y", 0.0))
        z_mm = float(secili.get("z", 0.0))
        meta.update(
            {
                "secili_id": secili.get("id"),
                "target_label": secili.get("label"),
                "secili_organ_id": int(secili.get("organ_id", 1)),
                "e_cancer": _sayi_ya_da_none(secili.get("E_cancer")),
                "e_healthy": _sayi_ya_da_none(secili.get("E_healthy")),
                "ood": self._egitim_araligi_disi(x_mm, y_mm, z_mm),
                "guven_ham": ham,
            }
        )
        dokum = {"yontem": yontem, "yontem_tavani": tavan, "ham_guven": ham, "kalibre": yontem == "aruco_pnp"}
        with self._kilit:
            self._meta = meta
        # ⚠️ D1.85 (B-5.11): araştırma hattında da kabin DIŞI / sonlu olmayan hedef SÜRÜLMEZ (kedi hattıyla aynı kural).
        _neden = hedef_kabin_disi_nedeni(x_mm, y_mm, z_mm)
        if _neden:
            air.logger.warning("%s hedefi kabin/geçerlilik denetiminde REDDEDİLDİ: %s", self.ad, _neden)
            return (False, 0.0, 0.0, 0.0, guven, overlay, ozne_var, dokum)
        # ⚠️ ArUco ZORUNLU (karar #4): tavan 0.25 < MIN_GUVEN 0.3 olduğundan ölçek/piksel modunda
        # bu koşul YAPISAL olarak sağlanamaz — eşik + tavan çift emniyet.
        return (guven >= MIN_GUVEN, x_mm, y_mm, z_mm, guven, overlay, ozne_var, dokum)

    def _overlay(self, pl, ctx, result):
        from servers import ai_router as air

        try:
            paneller = pl.render_panels(ctx, result, lang="tr")
            return paneller.get("07_combined")
        except Exception:
            air.logger.debug("%s overlay üretilemedi", self.ad, exc_info=True)
            return None

    def predict(self, x_mm: float, y_mm: float, z_mm: float, hedef_id: int) -> tuple:
        """EM doz modeli → (D[7], P[7], e_field). HAM döner; kırpma ai_router zarfında.

        ⚠️ EM `organ_id` = DOKU SINIFI (0 sağlıklı / 1 kanserli), UI hedef indeksi DEĞİL. Sınıf son
        lokalizasyonun SEÇİLİ hedefinden gelir; e_field o sınıfın E'sidir (`result_E_cancer` /
        `result_E_healthy`). Kedi modelinin tek `result_E` anahtarını okumak fantom/petri'de
        e_field'ı SESSİZCE 0 yapardı (keşif bulgusu)."""
        cache = self._onbellek()
        with self._kilit:
            sinif = int(self._meta.get("secili_organ_id", 1))
        out = cache["predictor"].predict(
            x=x_mm,
            y=y_mm,
            z=z_mm,
            organ_id=sinif,
            achieved_B=self.achieved_B,
            duty_sum=self.duty_sum,
        )
        D = [float(out.get(f"D{i}", 0.0)) for i in range(1, 8)]
        P = [float(out.get(f"P{i}", 0.0)) for i in range(1, 8)]
        e_anahtar = "result_E_cancer" if sinif == 1 else "result_E_healthy"
        e_field = float(out.get(e_anahtar, out.get("result_E_avg", 0.0)) or 0.0)
        return D, P, e_field

    def xai_sensitivity(self, x_mm: float, y_mm: float, z_mm: float, hedef_id: int):
        """Onay ekranı için hafif duyarlılık — dozun FİİLEN kullandığı baz noktasıyla (karar #9)."""
        modul = self._xai_modulu()
        cache = self._onbellek()
        with self._kilit:
            sinif = int(self._meta.get("secili_organ_id", 1))
        return modul.xai_hizli_sensitivity(
            cache["predictor"], x_mm, y_mm, z_mm, sinif, achieved_B=self.achieved_B, duty_sum=self.duty_sum
        )


class FantomSaglayici(_EmCvSaglayici):
    """Silikon fantomdaki tümör odakları (`phantom_cv_v3` — hocanın v3'ü, AI-2 — + `PhantomPredictor`)."""

    ad = "fantom"
    kapi_modeli = "fantom"
    title = "Fantom Tümör"
    subject_label = "fantom"
    onbellek_anahtari = "em_fantom_cv"
    hedef_etiketi = "Tümör"
    join_timeout_s = 8.0

    def _yukleyici(self):
        from servers import ai_router as air

        return air._yukle_em_fantom_cv

    def _pipeline_kur(self, cache):
        # ⚠️ manual_fallback=False ŞART: True olsa `manual_select` cv2 penceresi açıp headless
        # serviste bloklardı (döngü donar, E-stop ayrı yoldan çalışsa da sürüş güncellenmez).
        pl = cache["cls"](cache["cfg"], manual_fallback=False)
        pl._predictor = cache["predictor"]  # ENJEKSİYON: her karede ONNX yüklenmesin
        return pl

    def _ozne_yok_hatalari(self) -> tuple:
        # v3: lacivert hale kümesi hiç bulunamadıysa `tumor_cluster_not_found` (fantom kadrajda değil); fantom bulunup
        # içinde tümör yoksa `no_tumor_in_phantom` — o ÖZNE VAR durumudur (açı / ışık sorunu).
        return ("phantom_not_detected", "tumor_cluster_not_found")

    def _ipucu_ozne_yok(self) -> str:
        return (
            "Kadrajda fantom görünmüyor — fantomu tepsinin ortasına düz yerleştirin ve kabin "
            "işaretiyle birlikte kadraja alın."
        )

    def _egitim_araligi(self):
        from ai_hub.inference_em_fantom import inference_em_fantom as ief

        bg = ief.xai_ref_stats()["background"]
        return [(float(bg[:, i].min()), float(bg[:, i].max())) for i in range(3)]

    def _xai_modulu(self):
        from ai_hub.inference_em_fantom import inference_em_fantom as ief

        return ief

    def _adaylar(self, result) -> list:
        """Tümör odakları. Güven vekili (karar #7): fantom tespitinin `solidity` × mavi-nokta
        varlığı — `RegionPrediction`da güven alanı YOK, bu yüzden vekil türetilir."""
        tespit = (getattr(result, "phantom_detection", None) or {}).get("primary") or {}
        solidity = float(tespit.get("solidity", 0.0) or 0.0)
        mavi = 1.0 if float(tespit.get("n_blue_inside", 0) or 0) > 0 else 0.0
        ham = max(0.0, min(1.0, solidity * mavi))
        # AI-2: v3 tümör kimliği (T1–T5) YALNIZ yerleşim referansına KAYITLI sonuçta sabittir (`layout.rms_mm` var ve
        # `layout_mismatch` / `layout_unregistered` yok). ArUco kipinde kayıt yapılamıyor (ölçüldü) → kimlik konum sıralı →
        # etiket olarak KULLANILMAZ, sağlayıcının yarıçap sınırlı takip kimliği geçerlidir.
        uyarilar = [str(u) for u in (getattr(result, "warnings", None) or [])]
        kayitli = "rms_mm" in (getattr(result, "layout", None) or {}) and not any(
            u.startswith(("layout_mismatch", "layout_unregistered")) for u in uyarilar
        )
        out = []
        for r in list(getattr(result, "tumor_regions", []) or []):
            if r.centroid_cabin_mm is None:  # D1.100: geçersiz kesişim → konum yok → hedef olamaz
                continue
            tid = str(getattr(r, "tumor_id", "") or "")
            out.append(
                {
                    "px": tuple(float(v) for v in r.centroid_px),
                    "bbox": r.bbox_px,
                    "x": float(r.centroid_cabin_mm[0]),
                    "y": float(r.centroid_cabin_mm[1]),
                    "z": float(r.centroid_cabin_mm[2]),
                    "organ_id": int(r.organ_id or 1),
                    "reliability": ham,
                    "oncelik": float(r.area_px or 0),  # otomatik seçim: EN BÜYÜK odak
                    # D1.E07 (İG-5.76): doz hesaplanmadıysa (piksel kipi) None kalır — 0.0 "hesaplandı, sıfır" okunur.
                    "E_cancer": _sayi_ya_da_none(getattr(r, "E_cancer", None)),
                    "E_healthy": _sayi_ya_da_none(getattr(r, "E_healthy", None)),
                    "label": f"{self.hedef_etiketi} {tid}" if (kayitli and tid) else "",
                    "id": 0,
                }
            )
        return out


class PetriSaglayici(_EmCvSaglayici):
    """Petri plakasındaki kuyucuklar (`petri_cv_v2` — hocanın v2'si, AI-2: 24'lük plaka ızgarası, A1–D6 — + `PetriPredictor`)."""

    ad = "petri"
    kapi_modeli = "petri"
    title = "Petri Kuyu"
    subject_label = "petri plakası"
    onbellek_anahtari = "em_petri_cv"
    hedef_etiketi = "Kuyu"
    #: AI-2: v2 plaka kipi TÜM kuyucukları verir (24'lük: 24, 96'lık: 96) — eski 8'lik tavan kuyu 9–24'ü seçilemez
    #: kılardı (`hedef_idleri` dört doğrulama noktasının TEK kaynağı). En büyük standart plaka 96.
    azami_hedef = 96
    #: ÖLÇÜLDÜ (2026-09-09, bu makine, 06b_PetriKuyu_aruco.jpg): ilk yükleme ~5,1 s (artık döngü
    #: DIŞINDA, kameradan önce) ve kare başına ~0,34 s (YOLO11m-seg CPU dahil). README'deki 2,8 s
    #: bu ölçümle uyuşmuyor (orada cihaz belirtilmemiş). Kamera devrinde beklenen tek bir TUR
    #: olduğundan 8 s, yavaş bir klinik PC'sinde bile geniş pay bırakır (ölçümün ~20 katı).
    #: Kapı: tests/test_ai_pro_arastirma_gercek_pipeline.py bir kareyi kapsadığını doğrular.
    join_timeout_s = 8.0

    def _yukleyici(self):
        from servers import ai_router as air

        return air._yukle_em_petri_cv

    def _pipeline_kur(self, cache):
        # yolo_device="cpu" ŞART (headless, CUDA yok). YOLO + predictor ENJEKTE edilir.
        pl = cache["cls"](cache["cfg"], yolo_model_path=cache["yolo_path"], yolo_device="cpu")
        pl.yolo = cache["yolo"]
        pl._predictor = cache["predictor"]
        return pl

    def _ozne_yok_hatalari(self) -> tuple:
        # Makullik reddi (`not_a_petri_plate`) canlı döngüde İSTİSNA DEĞİL "özne yok" durumudur:
        # hazırlığı bitirmez, hedef bulunamamış sayılır ve şeritte eylem söyleyen ipucu gösterilir.
        from ai_hub.inference_petri_dish import plausibility as _pl

        # v2 plaka kipi: pembe/mor sıvı bölgesi hiç yoksa `plate_not_found` (plaka kadrajda değil).
        return ("yolo_no_well_detected", "plate_not_found", _pl.PETRI_REJECT)

    def _ipucu_ozne_yok(self) -> str:
        # ⚠️ AI Hub'ın YÜKLEME bağlamlı makullik metni kullanıcıya GİTMEZ ("yüklenen görüntü",
        # "modüle yükleyin", ortam değişkeni adı) — canlı kamera için ayrı, eylem söyleyen metin.
        return (
            "Kadrajda petri plakası görünmüyor — plakayı tepsiye düz yerleştirin, kamerayı tepeden "
            "tam kadraja alın ve kabin işaretinin görünür kaldığından emin olun."
        )

    def _egitim_araligi(self):
        from ai_hub.inference_em_petri import inference_em_petri as iep

        bg = iep.xai_ref_stats()["background"]
        return [(float(bg[:, i].min()), float(bg[:, i].max())) for i in range(3)]

    def _xai_modulu(self):
        from ai_hub.inference_em_petri import inference_em_petri as iep

        return iep

    def _adaylar(self, result) -> list:
        """Kuyucuklar. Güven `WellPrediction.reliability` (solidity × YOLO conf) — hazır geliyor.
        Otomatik seçim EN YÜKSEK güvenli KANSERLİ kuyu; sağlıklı kuyular yalnız ELLE seçilebilir
        (kontrol dozu, sahip kararı #2: kapalı-varsayılan anahtar)."""
        out = []
        for w in list(getattr(result, "wells", []) or []):
            if w.centroid_cabin_mm is None:  # D1.100: geçersiz kesişim → konum yok → hedef olamaz
                continue
            kanser = int(getattr(w, "organ_id", 0) or 0) == 1
            guven = max(0.0, min(1.0, float(getattr(w, "reliability", 0.0) or 0.0)))
            wid = str(getattr(w, "well_id", "") or "")
            out.append(
                {
                    "px": tuple(float(v) for v in w.centroid_px),
                    "bbox": w.bbox_px,
                    "x": float(w.centroid_cabin_mm[0]),
                    "y": float(w.centroid_cabin_mm[1]),
                    "z": float(w.centroid_cabin_mm[2]),
                    "organ_id": 1 if kanser else 0,
                    "reliability": guven,
                    "oncelik": (1000.0 if kanser else 0.0) + guven,
                    "E_cancer": _sayi_ya_da_none(getattr(w, "E_cancer", None)),
                    "E_healthy": _sayi_ya_da_none(getattr(w, "E_healthy", None)),
                    # AI-2: plaka kipinde kuyucuk kimliği ızgaradan (A1–D6) — etiket odur; tekil kipte (W1…) sıra
                    # karede değişebilir → etiket verilmez, takip kimliği geçerli.
                    "label": f"{self.hedef_etiketi} {wid}" if (wid and not wid.startswith("W")) else "",
                    "id": 0,
                }
            )
        return out


SAGLAYICILAR[FantomSaglayici.ad] = FantomSaglayici()
SAGLAYICILAR[PetriSaglayici.ad] = PetriSaglayici()
