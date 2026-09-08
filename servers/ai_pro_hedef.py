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


# Kayıt: Faz 2'de 'fantom' ve 'petri' eklenecek. Anahtar = tel sözleşmesindeki `model` değeri.
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
