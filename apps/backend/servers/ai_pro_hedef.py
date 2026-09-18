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

        if air.ai_service_enabled():
            try:
                return air._localize_organ_gpu(frame_bgr, hedef_id)
            except Exception as e:
                air.logger.warning("AI Pro cat_organ GPU delegasyonu başarısız → CPU-yerel: %s", e)
        return air._localize_organ_cpu(frame_bgr, hedef_id)

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
        if ozne_var:
            return f"Hayvan görünüyor ama {ad} seçilemedi — kamerayı biraz çevirip açıyı değiştirin."
        return "Kamerayı hastaya doğrultun; hayvan kadrajda görünmüyor."

    def son_lokalizasyon_meta(self) -> dict:
        """Kedi hattı kare üstü HEDEF ADAYI üretmez (organ seçimi çiplerden yapılır) → boş meta.
        Araştırma sağlayıcıları burada targets/method/ood/E döndürür; tel sözleşmesi ORTAK ve
        kedi tarafında yalnız-ek alanlar BOŞ kalır (veteriner sözleşmesi değişmez)."""
        return {}

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
# reddedilir (ai_router `_arastirma_aipro_kapisi`). Neden: phantom_cv/petri_cv koordinat dönüşümü
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
    """phantom_cv / petri_cv ortak sağlayıcı iskeleti (hedef bulma + doz + takip).

    Alt sınıflar `_yukleyici`, `_pipeline_kur`, `_adaylar`, `_ozne_yok_hatalari`,
    `_ipucu_ozne_yok`, `_egitim_araligi` ve `_xai_modulu`nu verir.

    ⚠️ ÖNBELLEK PAYLAŞIMI ZORUNLU: `localize` her karede HAFİF bir pipeline kurar ama ağır modelleri
    (ONNX / YOLO) `ai_router._get_or_load_model` önbelleğinden ENJEKTE eder. Enjeksiyon olmazsa
    `PhantomCvPipeline.predictor` lazy property'si her karede 60 MB ONNX'i, petri her karede 90 MB
    YOLO'yu yeniden açar → kareler saniyelere çıkar. Analiz uçları da AYNI önbelleği kullanır.
    """

    ad = ""
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
        if yontem and yontem != "aruco_pnp":
            return (
                "Konum ölçülemedi: kabin işareti (arka duvardaki kare kod) kadrajda görünmüyor. "
                "Kamerayı işaret ve hedef AYNI karede kalacak şekilde ayarlayın."
            )
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
        yeni, kullanilan = [], set()
        for aday in adaylar:
            px = aday.get("px") or (0.0, 0.0)
            r = _yaricap_px(aday.get("bbox"))
            en_iyi, en_iyi_d = None, None
            for k in eski:
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
            yeni.append(aday)
        sonraki = max([k["id"] for k in eski] + [a.get("id") or 0 for a in yeni] + [0]) + 1
        for aday in yeni:
            if not aday.get("id"):
                aday["id"] = sonraki
                aday["label"] = f"{self.hedef_etiketi} {sonraki}"
                sonraki += 1
        with self._kilit:
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
        if not arali:
            return False
        for deger, (alt, ust) in zip((x_mm, y_mm, z_mm), arali):
            if deger < alt or deger > ust:
                return True
        return False

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
                "e_cancer": float(secili.get("E_cancer", 0.0)),
                "e_healthy": float(secili.get("E_healthy", 0.0)),
                "ood": self._egitim_araligi_disi(x_mm, y_mm, z_mm),
                "guven_ham": ham,
            }
        )
        dokum = {"yontem": yontem, "yontem_tavani": tavan, "ham_guven": ham, "kalibre": yontem == "aruco_pnp"}
        with self._kilit:
            self._meta = meta
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
    """Silikon fantomdaki mavi tümör odakları (`phantom_cv` + `PhantomPredictor`)."""

    ad = "fantom"
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
        return ("phantom_not_detected",)

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
        out = []
        for r in list(getattr(result, "tumor_regions", []) or []):
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
                    "E_cancer": float(getattr(r, "E_cancer", 0.0) or 0.0),
                    "E_healthy": float(getattr(r, "E_healthy", 0.0) or 0.0),
                    "label": "",
                    "id": 0,
                }
            )
        return out


class PetriSaglayici(_EmCvSaglayici):
    """Petri plakasındaki kuyucuklar (`petri_cv` YOLO11m-seg + `PetriPredictor`)."""

    ad = "petri"
    title = "Petri Kuyu"
    subject_label = "petri plakası"
    onbellek_anahtari = "em_petri_cv"
    hedef_etiketi = "Kuyu"
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

        return ("yolo_no_well_detected", _pl.PETRI_REJECT)

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
            kanser = int(getattr(w, "organ_id", 0) or 0) == 1
            guven = max(0.0, min(1.0, float(getattr(w, "reliability", 0.0) or 0.0)))
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
                    "E_cancer": float(getattr(w, "E_cancer", 0.0) or 0.0),
                    "E_healthy": float(getattr(w, "E_healthy", 0.0) or 0.0),
                    "label": "",
                    "id": 0,
                }
            )
        return out


SAGLAYICILAR[FantomSaglayici.ad] = FantomSaglayici()
SAGLAYICILAR[PetriSaglayici.ad] = PetriSaglayici()
