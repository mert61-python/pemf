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
delegasyon yapar (`_get_or_load_kedi`, `_get_or_load_catorgan`, `_localize_organ_cpu/_gpu`; AP-17'den beri kedi SÜRÜŞÜ
yalnız ODAK'tan — `_predict_and_drive_cpu/_gpu` sürüş kaynağı değil). Böylece 13+ testin monkeypatch çıpaları ETKİLİ kalır ve
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

from utils import ceviri

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
    """Mevcut kedi yolu (`cat_organ` lokalizasyon) — sürüş ODAK'tan; ODAK ayarı yoksa SÜRMEZ (AP-17, `em_kedi` sürüş kaynağı değil).

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

    #: ODK (istem 45): mühürdeki ODAK ayarı (`odak_ayarla`) — varsa sürüş faz / duty'si ODAK'tan, YOKSA sürülmez (AP-17; Y142 kapalıyken
    #: kedi zaten SÜRÜLMEZ).
    odak_ayari: dict | None = None

    def localize(self, frame_bgr, hedef_id: int) -> tuple:
        """cat_organ ile lokalize et (GPU servisi açıksa oraya devret, hata → CPU-yerel).
        ⚠️ Gövde `_localize_organ`ın 2026-08-25'teki hâlidir; fallback deseni korunmuştur.
        ODK5: aynı karedeki organlardan ODAK kedi girdisi (gövde merkezi + yönü) `odak_kedi_girdisi()`nde (yoksa None). Veteriner META'SINA
        GİRMEZ (panel sözleşmesi: kedi meta'sı yalnız `ood`)."""
        from servers import ai_router as air

        air._kedi_organ_izi.organlar = None
        sonuc = None
        if air.ai_service_enabled():
            try:
                sonuc = air._localize_organ_gpu(frame_bgr, hedef_id)
            except Exception as e:
                air.logger.warning("AI Pro cat_organ GPU delegasyonu başarısız → CPU-yerel: %s", e)
        if sonuc is None:
            sonuc = air._localize_organ_cpu(frame_bgr, hedef_id)
        self._ood_isaretle(sonuc)
        try:
            self._odak_kedi = kedi_govde_geometrisi(getattr(air._kedi_organ_izi, "organlar", None))
        except Exception:
            air.logger.warning("ODAK kedi gövde geometrisi çıkarılamadı (öneri `kediGovdeYok` der)", exc_info=True)
            self._odak_kedi = None
        return sonuc

    def odak_kedi_girdisi(self) -> dict | None:
        """ODK5: son lokalizasyonun gövde merkezi + yönü (`kedi_govde_geometrisi`); yoksa None → öneri `kediGovdeYok`."""
        return getattr(self, "_odak_kedi", None)

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
        """ODK: mühürdeki ODAK ayarıyla (`odak_ayarla`) faz / duty ODAK'tan (CST alan tablosu). Duty kırpması ZARFTA yapılır.
        AP-17 (sahip 14 Kasım): ODAK ayarı YOKSA SIFIR (bobin sürülmez) — hocanın em_kedi doz modeli SÜRÜŞ KAYNAĞI OLMAZ (araştırma
        sağlayıcılarıyla aynı kural). Bugün Y142 kapalıyken kedi hiç sürülmez; bayrak açılırsa yalnız ODAK mühürlü seans sürer."""
        if not self.odak_ayari:
            return [0.0] * 7, [0.0] * 7, 0.0
        return _odak_predict(self, x_mm, y_mm, z_mm, hedef_id)

    def hedef_adi(self, hedef_id: int) -> str:
        from servers import ai_router as air

        return air._organ_adi(hedef_id)

    def hedef_adi_gosterim(self, hedef_id: int) -> str:
        """Kullanıcıya gösterilen organ adı (istek dili) — `hedef_adi` VERİ (Türkçe) kalır."""
        from servers import ai_router as air

        return air._organ_adi(hedef_id, None)

    def ipucu(self, ozne_var: bool, hedef_adi: str) -> str:
        """2026-08-24 sahip isteği: "hayvan yok" ile "hayvan var, organ görünmüyor" AYRI eylem
        gerektirir; metinler o günkü hâliyle korunur (kaynak-regex kapısı bunları arar)."""
        ad = hedef_adi or ceviri.t("ai.pro.hedefOrgan")
        if ozne_var and getattr(self, "_kabin_disi", False):
            return ceviri.t("ai.pro.ipucu.kabinDisi", ad=ad)
        if ozne_var:
            return ceviri.t("ai.pro.ipucu.hayvanGorunuyor", ad=ad)
        return ceviri.t("ai.pro.ipucu.hayvanYok")

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


def model_adi(saglayici) -> str:
    """Kullanıcıya gösterilen model adı (istek dili). `title` VERİ (`mode` / `modelName`; Türkçe) kalır."""
    ad = str(getattr(saglayici, "ad", "") or "")
    if ad == "kedi":
        return ceviri.t("ai.model.kedi")
    if ad == "fantom":
        return ceviri.t("ai.model.fantom")
    if ad == "petri":
        return ceviri.t("ai.model.petri")
    return str(getattr(saglayici, "title", "") or ceviri.t("ai.model.arastirma"))


def hedef_veri_adi(saglayici, hedef_id: int) -> str:
    """OTB T-9b: seans MOD metninin hedef parçası (VERİ, Türkçe — `mode`; gösterim `seans_durum.mod_etiketi` / `modEtiketi`): TÜM PETRİ
    seansında (mühür 0) "Tüm petri" — "Kuyu (otomatik)" değil (kum havuzu 19-11, canlı seans kartı)."""
    if int(hedef_id) == 0 and (getattr(saglayici, "odak_ayari", None) or {}).get("kip") == "TUM_PETRI":
        return TUM_PETRI_ETIKETI
    return saglayici.hedef_adi(hedef_id)


def hedef_gosterim_adi(saglayici, hedef_id: int) -> str:
    """Kullanıcıya gösterilen hedef adı (istek dili); sağlayıcı ayrı gösterim adı vermiyorsa `hedef_adi`."""
    # OTB T-9: TÜM PETRİ seansının hedefi BÜTÜN PLAKA (mühür 0) — canlı kart "Kuyu (otomatik)" demez.
    if int(hedef_id) == 0 and (getattr(saglayici, "odak_ayari", None) or {}).get("kip") == "TUM_PETRI":
        return ceviri.t("seans.aiProMod.tumPetri")
    yap = getattr(saglayici, "hedef_adi_gosterim", None) or saglayici.hedef_adi
    return yap(hedef_id)


# ══════════════════════════════════════════════════════════════════════════════════════════
# ODAK (istem 45 · Y268–Y274 · Y280): petri / fantom / kedi faz + duty'si ODAK modelinden (KNN + yerel alan, fizik denetimli).
# Hoca modelleri (em_fantom / em_petri / em_kedi) SİLİNMEZ ama SÜRÜŞ KAYNAĞI OLMAZ. ai_hub importu fonksiyon içinde (kod koruması).
# ══════════════════════════════════════════════════════════════════════════════════════════
ODAK_PETRI_KIPLERI = ("TUM_PETRI", "KUYUCUK")
#: OTB T-9: TÜM PETRİ önerisinin mühür / seans kaydı hedefi (VERİ, Türkçe saklanır — `kayit.hedef`); gösterim `seans.aiProMod.tumPetri`.
TUM_PETRI_ETIKETI = "Tüm petri"
#: Doz verilmeden istenen öneride başlangıç dozu = tavanın bu kesri (kullanıcı onay penceresinde değiştirir; sabit 1 mT YOK — Y273).
ODAK_VARSAYILAN_DOZ_KESRI = 0.8


#: ODAK'ın öneri / onay (ve mühürlü sürüş) kaynağı olduğu modeller. Kedi (ODK5): öneri + onay ekranı ODAK'tan (KEDI_TV tüm vücut /
#: KEDI_ORGAN); kedi SÜRÜŞÜ Y142 gereği KAPALI kalır (onay / başlatma / sürüş katı ayrı kapılarla).
ODAK_MODELLERI = ("petri", "fantom", "kedi")

#: Y283 (sahip 13 Kasım 2026): fantom çalışması İPTAL / ERTELENDİ — fantom AI Pro önerisi / sürüşü ODAK katmanında FAIL-CLOSED kapalı
#: (araştırma bayrağından BAĞIMSIZ; engel `fantomErtelendi`, TR + EN eylem söyler). Fantom yeniden eğitim / doğrulama / E-ortamı
#: benzetimi istem 45 "F"de; açmak bu sabiti değiştiren bir commit ister.
FANTOM_ODAK_ERTELENDI = True

#: ODK5 · kedi gövde ekseni organlardan: kranial grup (kalp, sağ / sol akciğer, karaciğer) ortalaması → kaudal grup (mesane, bağırsak)
#: ortalaması. Organ kimlikleri `ai_router._ORGAN_ADLARI` ile aynı. Güven eşiği kedi hattıyla aynı (0,3).
KEDI_KRANIAL = (7, 9, 10, 3)
KEDI_KAUDAL = (4, 6)
KEDI_GUVEN_ESIGI = 0.3
#: Kranial–kaudal yatay uzaklık bunun altındaysa yön belirsiz (aynı bölgedeki organlar) → geometri YOK.
KEDI_EKSEN_EN_AZ_MM = 40.0


def kedi_govde_geometrisi(organlar) -> dict | None:
    """cat_organ organ sözlüğü ({kimlik: {coord_cabin_cm | coord_3d_cm, reliability}}) → ODAK kedi girdisi
    {"merkez_P": [X, Y, Z] backend mm, "theta": rad (ölçüm çerçevesi; `oneri.kip_girdisi` boy ekseni (−sin θ, cos θ)), "organ_sayisi"}.
    Kranial VE kaudal grupta güvenilir (≥ eşik, sonlu, kabin içi) organ yoksa ya da eksen < 40 mm → None (öneri `kediGovdeYok` der)."""
    if not isinstance(organlar, dict) or not organlar:
        return None
    import numpy as np

    from ai_hub.odak.alan import backend_to_olcum

    def _nokta(kimlik):
        o = organlar.get(kimlik) or organlar.get(str(kimlik))
        if not isinstance(o, dict) or float(o.get("reliability") or 0.0) < KEDI_GUVEN_ESIGI:
            return None
        c = o.get("coord_cabin_cm") or o.get("coord_3d_cm")
        try:
            P = [float(v) * 10.0 for v in c[:3]]
        except (TypeError, ValueError, IndexError):
            return None
        if len(P) != 3 or hedef_kabin_disi_nedeni(*P):
            return None
        return P

    on = [p for p in (_nokta(k) for k in KEDI_KRANIAL) if p is not None]
    arka = [p for p in (_nokta(k) for k in KEDI_KAUDAL) if p is not None]
    if not on or not arka:
        return None
    on_b, arka_b = np.mean(on, axis=0), np.mean(arka, axis=0)
    a = backend_to_olcum(arka_b) - backend_to_olcum(on_b)
    if float(np.hypot(a[0], a[2])) < KEDI_EKSEN_EN_AZ_MM:
        return None
    return {
        "merkez_P": [float(v) for v in (on_b + arka_b) / 2.0],
        "theta": float(np.arctan2(-a[0], a[2])),
        "organ_sayisi": len(on) + len(arka),
    }


def odak_destekli(saglayici) -> bool:
    return getattr(saglayici, "ad", "") in ODAK_MODELLERI


def odak_kipi(saglayici, hedef_id: int, istenen: str = "") -> str:
    """petri: istenen (TUM_PETRI | KUYUCUK; varsayılan KUYUCUK) · fantom: FANTOM · kedi: 0 → KEDI_TV (Tüm Vücut), organ → KEDI_ORGAN."""
    ad = getattr(saglayici, "ad", "")
    if ad == "petri":
        k = str(istenen or "").strip().upper()
        return k if k in ODAK_PETRI_KIPLERI else "KUYUCUK"
    if ad == "fantom":
        return "FANTOM"
    if ad == "kedi":
        return "KEDI_TV" if int(hedef_id) == 0 else "KEDI_ORGAN"
    raise ValueError(ad)


def _etiket_eki(saglayici, etiket) -> str:
    """'Kuyu A1' → 'A1' (VERİ etiketi ön eki sağlayıcının `hedef_etiketi`)."""
    on = f"{getattr(saglayici, 'hedef_etiketi', '')} "
    e = str(etiket or "")
    return e[len(on) :] if on.strip() and e.startswith(on) else e


def _odak_engeli(kip: str, kod: str, doz_mT, ek=None) -> dict:
    return {"kip": kip, "doz_mT": doz_mT, "engel": kod, "engel_ek": dict(ek or {}), "duty": [0.0] * 7, "faz": [0.0] * 7}


def odak_plani(
    saglayici, konum: dict, hedef_id: int, doz_mT, istenen_kip: str = "", frek_hz: float | None = None
) -> dict:
    """Lokalizasyon (`konum`: x_mm / y_mm / z_mm / target_label, BACKEND kabin çerçevesi) + doz → ODAK planı (`ai_hub.odak.oneri.oner`).
    Kalibrasyon yok / bozuk / eski / eşleme doğrulanmamış → engelli plan (duty 0). `doz_mT` None → tavanın %80'i (başlangıç önerisi)."""
    from ai_hub.odak import alan as odak_alan
    from ai_hub.odak import oneri as odak_oneri

    kip = odak_kipi(saglayici, hedef_id, istenen_kip)
    if kip == "FANTOM" and FANTOM_ODAK_ERTELENDI:
        return _odak_engeli(kip, "fantomErtelendi", doz_mT)  # Y283: fantom ertelendi — SÜRMEZ
    try:
        A = odak_oneri.alan_modeli(duzlem_veri_koku(), frek_hz)
    except odak_alan.KalibrasyonHatasi as e:
        return _odak_engeli(kip, e.kod, doz_mT)
    except FileNotFoundError:
        # Y282: alan tablosu AI model katmanında — yoksa SÜRMEZ (eylem: AI model paketini kur / güncelle).
        return _odak_engeli(kip, "modelYok", doz_mT)
    if kip in ODAK_PETRI_KIPLERI:
        meta = saglayici.son_lokalizasyon_meta()
        girdi = {
            "kuyular": meta.get("odak_adaylar") or [],
            "hedef_etiket": _etiket_eki(saglayici, konum.get("target_label")),
        }
    elif kip in ("KEDI_TV", "KEDI_ORGAN"):
        # ODK5: gövde merkezi + yönü AYNI lokalizasyonun organlarından; KEDI_TV hedefi = gövde (Tüm Vücut lokalizasyonu 0,0,0 döner).
        geo = saglayici.odak_kedi_girdisi() if hasattr(saglayici, "odak_kedi_girdisi") else None
        if not geo:
            return _odak_engeli(kip, "kediGovdeYok", doz_mT)
        hedef = (
            geo["merkez_P"] if kip == "KEDI_TV" else [float(konum["x_mm"]), float(konum["y_mm"]), float(konum["z_mm"])]
        )
        girdi = {"hedef_P": hedef, "kedi": {"merkez_P": geo["merkez_P"], "theta": geo["theta"]}}
    else:
        girdi = {"hedef_P": [float(konum["x_mm"]), float(konum["y_mm"]), float(konum["z_mm"])]}
    # OTB T-2: doz verilmezse başlangıç önerisi MODELİN ulaşabildiği tavanın %80'i (`oner` içinde; fizik tavanının değil).
    return odak_oneri.oner(
        kip, A, None if doz_mT is None else float(doz_mT), varsayilan_kesir=ODAK_VARSAYILAN_DOZ_KESRI, **girdi
    )


def odak_tavanlari(saglayici, frek_hz: float | None = None) -> dict | None:
    """OTB T-1: petri onay penceresinin "Doz (en çok X)"i SEÇİLİ kip / kuyuya göre — son lokalizasyonun kuyularıyla her kip ve görülen
    her kuyu için MODELİN ulaşabildiği tavan (`oneri.petri_tavanlari`). Petri dışı ya da hesaplanamazsa None (pencere sayı göstermez)."""
    if getattr(saglayici, "ad", "") != "petri":
        return None
    from ai_hub.odak import oneri as odak_oneri

    try:
        A = odak_oneri.alan_modeli(duzlem_veri_koku(), frek_hz)
        return odak_oneri.petri_tavanlari(A, saglayici.son_lokalizasyon_meta().get("odak_adaylar") or [])
    except Exception:
        import logging

        logging.getLogger(__name__).warning("ODAK: kip / kuyu tavanları hesaplanamadı (yalnız gösterim)", exc_info=True)
        return None


def _odak_predict(saglayici, x_mm: float, y_mm: float, z_mm: float, hedef_id: int) -> tuple:
    """Döngü sürüşü (mühürlü ODAK ayarıyla): AYNI dozla yeniden hesap; plan ENGELLİ → SIFIR (bobin sürülmez)."""
    ayar = saglayici.odak_ayari
    konum = {"x_mm": x_mm, "y_mm": y_mm, "z_mm": z_mm, "target_label": ayar.get("hedef_etiket")}
    plan = odak_plani(saglayici, konum, hedef_id, ayar["doz_mT"], ayar.get("kip", ""), ayar.get("frek_hz"))
    if plan.get("engel"):
        from servers import ai_router as air

        air.logger.warning("%s ODAK planı ENGELLİ (%s) → sürülmez", saglayici.ad, plan.get("engel"))
        saglayici.son_odak_e = None
        # Y300 (ODD B-1): döngü sabit numunede tolerans STOP'unun NEDENİNİ buradan söyler (engel kodu + eki).
        saglayici.son_odak_engel = {"engel": plan.get("engel"), "engel_ek": dict(plan.get("engel_ek") or {})}
        return [0.0] * 7, [0.0] * 7, 0.0
    saglayici.son_odak_engel = None
    # ODK6: bu planın E'si (hedef / çevre, tepe V/m) — döngü sürüşten sonra canlı E çubuğuna yazar (`efield_live.odak_guncelle`);
    # ODK10: ortam "kuyu" (petri: kuyu sıvısı içinde) | "hava" (kedi: ortamsız CST) — arayüz etiketi buna göre
    saglayici.son_odak_e = {
        "cancer": plan.get("e_hedef_Vm"),
        "healthy": plan.get("e_cevre_Vm"),
        "ortam": plan.get("e_ortam"),
    }
    return [float(d) for d in plan["duty"]], [float(p) for p in plan["faz"]], 0.0


def _pk_fiziksel() -> tuple:
    from ai_hub.cv_ortak import pemf_kapisi as _pk

    return tuple(_pk.FIZIKSEL)


def _plaka_en_az() -> int:
    from ai_hub.odak import oneri as odak_oneri

    return int(odak_oneri.IZGARA_EN_AZ)


#: OTB T-6 / T-12: plaka engel metinlerinin yer tutucuları — eksik sayı "?" (metin yine NEDENİ söyler, genel metne düşmez).
_PLAKA_EK_ALANLARI = {
    "plakaYok": ("bulunan", "beklenen"),
    "plakaUyumsuz": ("bulunan", "sapma"),
    "plakaKaydi": ("gorulen", "sapma"),
}


def plaka_engel_plani(meta) -> dict | None:
    """OTB T-6 / T-12: son lokalizasyonun plaka engeli → `odak_engel_metni` girdisi ({"engel", "engel_ek"}); engel yoksa None."""
    kod = str((meta or {}).get("plaka_dogrulanmadi") or "")
    if kod not in _PLAKA_EK_ALANLARI:
        return None
    ek = dict((meta or {}).get("plaka_ayrinti") or {})
    return {"engel": kod, "engel_ek": {a: ("?" if ek.get(a) is None else ek[a]) for a in _PLAKA_EK_ALANLARI[kod]}}


def odak_engel_metni(plan: dict, dil: str | None = None) -> str:
    """Engel kodu → eylem söyleyen metin (`dil` yoksa istek dili). Sayılar 2 basamak."""
    ek = {k: (f"{float(v):.2f}" if isinstance(v, float) else v) for k, v in (plan.get("engel_ek") or {}).items()}
    return ceviri.t(f"ai.pro.odak.engel.{plan.get('engel')}", dil=dil, **ek)


def odak_ayarla(saglayici, odak, hedef_etiket: str = "") -> None:
    """Seans: MÜHÜRDEKİ ODAK ayarı (doz, kip, hedef etiketi) → döngünün `predict`i kullanır; None = temizle (durdurma).
    Kedi (ODK5): ayar tutulur; Y142 kapalıyken kedi seansı zaten BAŞLATILMAZ / SÜRÜLMEZ."""
    if not hasattr(saglayici, "odak_ayari"):
        return
    if hasattr(saglayici, "_sabit_izgara"):
        saglayici._sabit_izgara = None  # OTB T-8: her seans (ve durdurma) kendi sabit numune referansıyla
    if not odak or odak.get("doz_mT") is None:
        saglayici.odak_ayari = None
        return
    saglayici.odak_ayari = {
        "doz_mT": float(odak["doz_mT"]),
        "kip": str(odak.get("kip") or ""),
        "hedef_etiket": str(hedef_etiket or ""),
        # ODK8: mühürdeki frekans (yoksa 100 Hz — eski mühür)
        "frek_hz": float(odak.get("frek_hz") or 100.0),
    }


def kosulsuz_ayarla(saglayici, deger) -> bool:
    """T3 · Y189: araştırma sağlayıcısının (fantom / petri) KOŞULSUZ kipini ayarla; kedi sağlayıcısında yok sayılır (False).
    @return etkin değer. Hazırlık bunu istekten, seans ÖNERİ MÜHRÜNDEN (`specs.kosulsuz`) verir; durdurma False'a döndürür."""
    if not hasattr(saglayici, "kosulsuz"):
        return False
    saglayici.kosulsuz = deger is True
    return saglayici.kosulsuz


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
        raise ValueError(ceviri.t("ai.pro.hata.modelTanimsiz", model=model, gecerli=gecerli)) from None


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
YONTEM_TAVANI = {
    "aruco_pnp": 1.0,
    "sabit_duzlem": 1.0,
}  # KD · Y258: sabit düzlem kalibrasyonu da perspektif-doğru kabin konumu
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


# ── KD · SABİT DÜZLEM KALİBRASYONU (Y258–Y259, sahip 2026-11-10) ───────────────────────────────────────────────────────────────
# Kalibrasyon VERİ KÖKÜNDE (`cv_ortak.sabit_duzlem`, uygulama katmanı değil — güncelleme ezmez). Dosya varsa hatlar ArUco ARAMAZ.
# Araştırma sürüşü (petri / fantom) YALNIZ geçerli kalibrasyonla başlar ve sürer (`ai_router._duzlem_kalibrasyonu_kapisi`); kare başına
# fiziksel denetimler (sahne kayması, kuyu aralığı, fantom boyu) hatta → PEMF kapısı `FIZIKSEL` kodları (koşulsuzda da keser).


def duzlem_veri_koku():
    from utils.path_utils import get_app_data_directory

    return get_app_data_directory()


def duzlem_durumu() -> tuple:
    """`sabit_duzlem.yukle(veri kökü)` → (kal, hata). (None, None) = dosya YOK (ArUco kipi); okunamazsa (None, "okunamadi")."""
    try:
        from ai_hub.cv_ortak import sabit_duzlem as sd

        return sd.yukle(duzlem_veri_koku())
    except Exception:
        import logging

        logging.getLogger(__name__).warning("Sabit düzlem kalibrasyonu okunamadı", exc_info=True)
        return None, "okunamadi"


def secili_kamera_kimligi():
    """KD-2: seçili kabin kamerasının KİMLİĞİ (ad + VID/PID + aygıt yolu) — kalibrasyon kamerasıyla karşılaştırılır; yoksa None."""
    try:
        from utils import kabin_kamerasi as kk

        s = kk.secili_kamera()
        return None if s is None else s.get("kimlik")
    except Exception:
        return None


def gorus_alani_on_cm():
    """Kalibrasyondan ön camın dibindeki kör şerit (cm); kalibrasyon / bilgi yoksa None."""
    kal, hata = duzlem_durumu()
    if kal is None or hata:
        return None
    try:
        v = float((kal.get("gorus_alani") or {}).get("on"))
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def kor_bolge_ipucu() -> str:
    """Numune HİÇ bulunamadığında ipucuna eklenen kör bölge cümlesi (kalibrasyonda ön kör şerit varsa); yoksa boş."""
    cm = gorus_alani_on_cm()
    return "" if cm is None else " " + ceviri.t("ai.pro.ipucu.korBolge", cm=f"{cm:g}")


def secili_kamera_indeksi():
    """Seçili kabin kamerasının indeksi (kalibrasyon kamerasıyla karşılaştırılır); seçim yoksa None."""
    try:
        from utils import kabin_kamerasi as kk

        s = kk.secili_kamera()
        return None if s is None else int(s["indeks"])
    except Exception:
        return None


def duzlem_surus_engeli(saglayici) -> str | None:
    """Y259: araştırma sürüşünün KALİBRASYON ön koşulu → engel kodu (`pemf_kapisi.FIZIKSEL`) ya da None.

    Dosya yok → `kalibrasyon_yok` · bozuk → `kalibrasyon_bozuk` · seçili kamera kalibrasyon kamerası değil → `kalibrasyon_kamera_farkli` ·
    fantomda kalınlık / derinlik girilmemiş → `fantom_ayari_yok`. Kare başına denetimler (sahne / aralık / boy) hatta, her karede."""
    kal, hata = duzlem_durumu()
    if hata:
        return "kalibrasyon_bozuk"
    if kal is None:
        return "kalibrasyon_yok"
    from ai_hub.cv_ortak import sabit_duzlem as sd

    ayni = sd.kimlik_ayni(secili_kamera_kimligi(), (kal.get("kamera") or {}).get("kimlik"))
    if ayni is False:
        return "kalibrasyon_kamera_farkli"
    secili = secili_kamera_indeksi()
    ki = (kal.get("kamera") or {}).get("indeks")
    if ayni is None and secili is not None and ki is not None and int(secili) != int(ki):
        return "kalibrasyon_kamera_farkli"
    if str(getattr(saglayici, "ad", "") or "") == "fantom":
        ayar = kal.get("fantom") or {}
        try:
            kalinlik = float(ayar.get("kalinlik_mm"))
        except (TypeError, ValueError):
            kalinlik = 0.0
        if not (kalinlik > 0):
            return "fantom_ayari_yok"
    return None


def kapi_metni(kod: str) -> str | None:
    """KD: PEMF kapısının FİZİKSEL (kalibrasyon) nedeni → istek / cihaz dilinde EYLEM metni. ai_hub metni Türkçe TABANDIR (ai_hub
    backend'i içe aktarmaz); arayüze giden metin buradan. Bilinmeyen kod → None (hocanın metni olduğu gibi kalır)."""
    if kod == "kalibrasyon_yok":
        return ceviri.t("ai.pemf.kapi.kalibrasyonYok")
    if kod == "kalibrasyon_bozuk":
        return ceviri.t("ai.pemf.kapi.kalibrasyonBozuk")
    if kod == "kalibrasyon_kamera_farkli":
        return ceviri.t("ai.pemf.kapi.kameraFarkli")
    if kod == "kamera_oynamis":
        return ceviri.t("ai.pemf.kapi.kameraOynamis")
    if kod == "fantom_ayari_yok":
        return ceviri.t("ai.pemf.kapi.fantomAyariYok")
    if kod == "fantom_boyu_farkli":
        return ceviri.t("ai.pemf.kapi.fantomBoyuFarkli")
    if kod == "fantom_degil":
        return ceviri.t("ai.pemf.kapi.fantomDegil")
    if kod.startswith("kor_bolge_"):
        cm = gorus_alani_on_cm()
        ek = "" if cm is None else " " + ceviri.t("ai.pemf.kapi.korBolgeOnSerit", cm=f"{cm:g}")
        if kod == "kor_bolge_on":
            return ceviri.t("ai.pemf.kapi.korBolgeOn") + ek
        if kod == "kor_bolge_arka":
            return ceviri.t("ai.pemf.kapi.korBolgeArka") + ek
        if kod == "kor_bolge_sol":
            return ceviri.t("ai.pemf.kapi.korBolgeSol") + ek
        if kod == "kor_bolge_sag":
            return ceviri.t("ai.pemf.kapi.korBolgeSag") + ek
    return None


def kalibrasyon_eski_metni(payload) -> str | None:
    """KD-1 sahip kararı: "kalibre etmeden devam" edildiyse HER yanıtta kalıcı uyarı (istek dilinde); değilse None."""
    try:
        if isinstance(payload, dict) and bool((payload.get("kalibrasyon") or {}).get("eski")):
            return ceviri.t("ai.pemf.kapi.kalibrasyonEski")
    except Exception:
        return None
    return None


def kapi_cevir(kapi):
    """PEMF kapısı sözlüğünün FİZİKSEL kod mesajlarını (ve ilk eylemi) dile çevir; diğerleri AYNEN (hocanın metni)."""
    if not isinstance(kapi, dict):
        return kapi
    mesajlar = []
    for m in kapi.get("mesajlar") or []:
        m = dict(m) if isinstance(m, dict) else m
        if isinstance(m, dict):
            metin = kapi_metni(str(m.get("kod") or ""))
            if metin:
                m["metin"] = metin
        mesajlar.append(m)
    out = dict(kapi)
    if "mesajlar" in kapi:
        out["mesajlar"] = mesajlar
    if mesajlar and isinstance(mesajlar[0], dict) and kapi.get("eylem"):
        out["eylem"] = mesajlar[0].get("metin") or kapi.get("eylem")
    return out


def kapi_uyari_metni(kapi, hata: str = "", meta=None) -> str:
    """AP-B6 (istem 48 · S-AP.6, sahip 14-11 "neden + eylem"): canlı hazırlıkta kare tüketim kapısının FİZİKSEL OLMAYAN (kalite /
    yerleşim) nedeni ya da plaka makullik reddi → istek dilinde NEDEN + EYLEM. Eskiden arayüze hiç gelmiyordu: şerit "kuyu / plaka aranıyor"
    deyip 120 sn sonra kedi + telefon iletisi veriyordu (13-11 tezgâh: koşullu kipte her kare `few_candidates` / `ecc_failed` / makullik
    reddi). Hocanın `pemf_kapisi._EYLEM` metinleri (AI Hub tek-foto bağlamı, "yeniden çekin") sabit kabin kamerasında yanlış eylemdir → canlı
    metin ayrı (`ai.pemf.canliUyari.*`). Koşulsuz kip ÖNERİLMEZ (sahip). Fiziksel neden kendi metniyle gider (`kapi_metni` / `kapiEylem`)
    → burada "". Yalnız GÖSTERİM: kapı kararı değişmez."""
    from ai_hub.cv_ortak import pemf_kapisi as _pk
    from ai_hub.inference_petri_dish import plausibility as _pl

    _plaka = plaka_engel_plani(meta)
    if _plaka:
        # OTB T-12 / T-14: plaka doğrulanmadıysa gerçek neden SAYILARIYLA (görülen kuyu, sapma mm) — "Tümünü gör" artık bunu açar
        return odak_engel_metni(_plaka)
    if str(hata or "").startswith(_pl.PETRI_REJECT):
        return ceviri.t("ai.pemf.canliUyari.fewCandidates")  # plaka bölgesi var, ızgara (ECC + aday) doğrulanamadı
    if not isinstance(kapi, dict) or kapi.get("surulebilir") is not False:
        return ""
    nedenler = [str(n) for n in kapi.get("nedenler") or []]
    if any(n in _pk.FIZIKSEL for n in nedenler):
        return ""
    for n in nedenler:
        if n == "few_candidates":
            return ceviri.t("ai.pemf.canliUyari.fewCandidates")
        if n == "ecc_failed":
            return ceviri.t("ai.pemf.canliUyari.eccFailed")
        if n == "plate_cropped":
            return ceviri.t("ai.pemf.canliUyari.plateCropped")
        if n == "oblique_view":
            return ceviri.t("ai.pemf.canliUyari.obliqueView")
        if n == "layout_mismatch":
            return ceviri.t("ai.pemf.canliUyari.layoutMismatch")
        if n == "guvenilir_degil":
            return ceviri.t("ai.pemf.canliUyari.guvenilirDegil")
        if n in ("control_cancer_missed", "control_healthy_flagged"):
            return ceviri.t("ai.pemf.canliUyari.kontrolKuyusu")
        if n == "plaka_dogrulanmadi":
            return ceviri.t("ai.pemf.canliUyari.plakaDogrulanmadi")  # ODD B-5: koşulsuz kipte ODAK ızgarası oturmadı
    return ""


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
    # I18NI-A2.8: `etiketGosterim` YALNIZ-EK (eski istemci `label`'ı okumaya devam eder)
    d = {
        k: v
        for k, v in aday.items()
        if k in ("id", "label", "etiketGosterim", "px", "x", "y", "z", "organ_id", "reliability")
    }
    px = aday.get("px") or (0.0, 0.0)
    if kare_w > 0 and kare_h > 0:
        d["pxn"] = [
            round(min(1.0, max(0.0, float(px[0]) / float(kare_w))), 5),
            round(min(1.0, max(0.0, float(px[1]) / float(kare_h))), 5),
        ]
    return d


def _onizleme_karesi(panel, ctx):
    """AP-B7 (istem 48 · S-AP.3, tezgâh 13-11): AI Pro önizlemesinde gösterilen TEK panel, hedef halkalarının koordinatında.
    Eskiden `07_combined` (6 panel 3×2 ızgara + başlık bantları) yayınlanıyordu; halkaların `pxn`'i HAM kareye göre olduğundan halkalar
    özetin ortasına düşüyordu. Render panelleri ÜSTE başlık bandı ekler (vstack) — bant kırpılınca panel, hattın çizdiği kareyle (`img_und`,
    ham kareyle aynı boyut) AYNI piksel ızgarasındadır. Boyut uymazsa None → döngü ham kareyi yayınlar (halkalar yine doğru yerde)."""
    kare = (ctx or {}).get("img_und") if isinstance(ctx, dict) else None
    if panel is None or kare is None or not hasattr(panel, "shape"):
        return None
    h, w = kare.shape[:2]
    ph, pw = panel.shape[:2]
    if pw != w or ph < h:
        return None
    return panel[ph - h :]


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
    #: I18NI-A2.8: `hedef_etiketi` VERİ ön ekidir (onay mührü etiketi / `mode` kaydı — Türkçe kalır); ARAYÜZ gösterimi bu anahtardan.
    hedef_etiketi_anahtari = "ai.pro.hedefOnek.genel"
    join_timeout_s = 6.0
    varsayilan_hedef = 0
    #: Kabul edilen EN FAZLA hedef (0 = otomatik seçim, 1..N = kare üstünde elle seçim).
    azami_hedef = 8
    #: ODD B-5: koşulsuz kipte plaka ODAK ızgarasıyla doğrulanır mı (yalnız petri; fantomda ızgara yok).
    plaka_dogrulamasi = False
    #: AP-B7 (S-AP.3): önizlemede gösterilen render paneli (hedef halkaları bunun üstünde); alt sınıf verir, boşsa ham kare.
    onizleme_paneli = ""

    def __init__(self):
        import threading

        self._kilit = threading.Lock()
        self._meta: dict = {}
        self._kimlikler: list = []  # kalıcı kimlikler: {"id", "ad", "px", "organ_id"}
        # AII-2.1: kaybolan kimlikler (son konumlarıyla) ve verilmiş EN BÜYÜK kimlik — kimlik BAŞKA hedefe yeniden verilmez.
        self._kayip_kimlikler: dict = {}
        self._son_kimlik = 0
        #: T3 · Y189 KOŞULSUZ kip (`kosulsuz_ayarla`): PEMF kapısının engelleyici / yeniden-çekim / güvenilmez nedenleri ve
        #: yöntem tavanı + `MIN_GUVEN` eşiği sürüşü KESMEZ. Kalanlar: sonuç var, konum KABİN çerçevesinde (`pemf_valid`), kabin
        #: içi + sonlu hedef (D1.85), Y145 bayrağı, hekim onayı, ACİL DURDUR. Varsayılan False = davranış AYNI.
        self.kosulsuz = False
        #: ODAK (istem 45): seansın MÜHÜRLÜ doz / kip / hedef etiketi (`odak_ayarla`); None = sürüş yok.
        self.odak_ayari: dict | None = None
        #: OTB T-8: seansın İLK doğrulanan petri ızgarası (ODAK aday listesi) — sabit numune REFERANSI; `odak_ayarla` sıfırlar.
        self._sabit_izgara: list | None = None

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
        # ⚠️ AIK (Y143 eki): takip kimliği BAŞKA hedefe yeniden verilmez (AII-2.1) ve sayaç geri dönmez → fantom kaydırılınca
        # kimlikler `azami_hedef`i aşar (ÖLÇÜLDÜ: ~35 px kaydırma → 1–5 → 6–10; fantom tavanı 8) ve kimliği 9 / 10 olan hedef
        # seçilemiyordu (öneri / hedef değişimi 422). Y143 otomatik öneriyi seçili KİMLİKLE mühürlediği için başlatma da 422'ye
        # düşerdi. Sağlayıcının VERDİĞİ her kimlik geçerli hedeftir; verilmemiş kimlik yine reddedilir (dört doğrulama noktası bu
        # kümeyi TEK KAYNAK olarak kullanır). Kilit ALINMAZ: tamsayı okuması atomik, `_kimlik_ata` kilidi tutarken çağrılmaz.
        return frozenset(range(0, max(self.azami_hedef, int(getattr(self, "_son_kimlik", 0) or 0)) + 1))

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
            # ODD K-10: o karede görülmeyen (kaybolan) kimliğin adı da korunur — canlı seans kartı iç numarayı ("Kuyu 12") değil
            # plaka etiketini ("Kuyu C6") göstersin.
            for k in [*self._kimlikler, *self._kayip_kimlikler.values()]:
                if k.get("id") == hid:
                    return str(k.get("ad") or f"{self.hedef_etiketi} {hid}")
        return f"{self.hedef_etiketi} {hid}"

    def etiket_gosterim(self, etiket: str) -> str:
        """VERİ etiketinin (`"Tümör T1"`) kullanıcıya gösterilen hâli: Türkçe ön ek istek / cihaz dilinde (TR'de bayt bayt aynı)."""
        if etiket == TUM_PETRI_ETIKETI:
            return ceviri.t("seans.aiProMod.tumPetri")  # OTB T-9: bütün plaka
        on = f"{self.hedef_etiketi} "
        if etiket.startswith(on):
            return f"{ceviri.t(self.hedef_etiketi_anahtari)} {etiket[len(on) :]}"
        return etiket

    def hedef_adi_gosterim(self, hedef_id: int) -> str:
        """Kullanıcıya gösterilen hedef adı (canlı `organName` / `targetName`) — `hedef_adi` VERİ (Türkçe; `mode` kaydı) kalır."""
        if int(hedef_id) == 0:
            return ceviri.t("ai.pro.hedefOtomatik", onek=ceviri.t(self.hedef_etiketi_anahtari))
        return self.etiket_gosterim(self.hedef_adi(hedef_id))

    def ipucu(self, ozne_var: bool, hedef_adi: str) -> str:
        if not ozne_var:
            return self._ipucu_ozne_yok()
        with self._kilit:
            yontem = str(self._meta.get("method") or "")
            kapi = dict(self._meta.get("pemf_kapisi") or {})
        if yontem and yontem not in YONTEM_TAVANI:
            return ceviri.t("ai.pro.ipucu.konumOlculemedi")
        # AI-2: hocanın tüketim kapısı kareyi kestiyse NEDENİ ve EYLEMİ (pemf geçersiz / güvenilmez / yerleşim uyuşmuyor /
        # kontrol kuyucuğu / yeniden çekim) — "hedef seçilemedi" demek operatörü yanlış yere yönlendirirdi.
        if kapi and not kapi.get("surulebilir", True) and kapi.get("eylem"):
            # AP-13: fiziksel neden zaten dile çevrili (`kapi_cevir`); kalite / yerleşim nedeni canlı metinle (`kapi_uyari_metni`).
            return kapi_uyari_metni(kapi) or str(kapi["eylem"])
        return ceviri.t("ai.pro.ipucu.hedefSecilemedi", hedef_adi=hedef_adi)

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
                # OTB T-8: CV'nin BU karedeki etiketi (petri v2 A1–D6) ODAK ızgarası için saklanır — takip etiketi önceki kareden
                # taşınır ve ızgara kareden kareye değişince aynı karede YİNELENEN etiket üretiyordu (ölçüldü 19-11).
                aday.setdefault("cv_label", aday.get("label"))
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
        for a in yeni:  # I18NI-A2.8: ARAYÜZ gösterimi (`HedefSecici`); `label` VERİ kalır (onay mührü)
            a["etiketGosterim"] = self.etiket_gosterim(str(a.get("label") or ""))
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
            # ODAK (istem 45): bütün adaylar kabin konumuyla — petride 24 kuyu (TÜM PETRİ hedefi / KUYUCUK çevresi + onay haritası).
            "odak_adaylar": [
                {
                    # OTB T-8: ızgara geometrisi karenin KENDİ CV etiketiyle (takip etiketi değil — yinelenen etiket ızgarayı bozuyordu)
                    "etiket": _etiket_eki(self, a.get("cv_label") or a.get("label")),
                    "P": [float(a["x"]), float(a["y"]), float(a["z"])],
                    "px": a.get("px"),
                }
                for a in adaylar
            ],
        }
        # ⚠️ AI-2 (plan §3.9 · hocanın ENTEGRASYON §3): bobine giden yolda tüketim kapısı — `success`, `pemf_valid`,
        # fantomda `reliable`, engelleyici uyarılar (`layout_mismatch`, `control_cancer_missed`, `control_healthy_flagged`)
        # ve yeniden-çekim uyarıları (`oblique_view`, `low_resolution`, `ring_partial`). Geçmezse kare LOKALİZE SAYILMAZ:
        # `/propose` taze hedef bulamaz (409 + eylem), seans döngüsü sürmez, `_predict_and_drive` ÇAĞRILMAZ. FAIL-CLOSED ve
        # `PEMF_ARASTIRMA_AIPRO` bayrağından BAĞIMSIZ (bayrak sürüşü açar, bu kapı geçersiz sonucu yine keser). Hedef
        # adayları meta'da kalır (operatör ne görüldüğünü görür) ama hiçbiri seçili değildir.
        # KD: hat FİZİKSEL nedenle hedef üretmeden durduysa (fantom boyu ayardakinden farklı — boş kabin) kapı yine hesaplanır:
        # şerit "hedef seçilemedi" değil NEDENİ ve EYLEMİ söyler.
        from ai_hub.cv_ortak import pemf_kapisi

        fiziksel_hata = not basarili and any(k in pemf_kapisi.FIZIKSEL for k in pemf_kapisi.uyari_kodlari([hata]))
        if basarili or fiziksel_hata:
            kapi = kapi_cevir(pemf_kapisi.degerlendir(result, model=self.kapi_modeli, kosulsuz=self.kosulsuz))
            meta["pemf_kapisi"] = kapi
            if not kapi["surulebilir"]:
                air.logger.warning("%s karesi tüketim kapısında REDDEDİLDİ: %s", self.ad, kapi["nedenler"])
                if (
                    self.kosulsuz
                    and getattr(self, "plaka_dogrulamasi", False)
                    and len(meta["odak_adaylar"]) < _plaka_en_az()
                    and any(n in _pk_fiziksel() for n in kapi["nedenler"])
                ):
                    # OTB T-14 (boş kabin 19-11: "Kamera oynamış olabilir ya da taban yüksekliği yanlış"): plaka görülmüyorsa asıl
                    # neden PLAKA YOK — konum ölçüm hatasından (sahne eşleşmesi plakasız kabinde düşer) ÖNCE söylenir. T-15: ham kare.
                    meta.update(
                        {
                            "targets": [],
                            "plaka_dogrulanmadi": "plakaYok",
                            "plaka_ayrinti": {"bulunan": len(meta["odak_adaylar"]), "beklenen": _plaka_en_az()},
                        }
                    )
                    overlay = None
                with self._kilit:
                    self._meta = meta
                return (False, 0.0, 0.0, 0.0, 0.0, overlay, True, None)
        # ⚠️ ODD B-5 (ODK-B keşfi 18-11, sahip 12–14.png): KOŞULSUZ kipte hocanın tüketim kapısı (yerleşim / kontrol kuyusu) kesmez →
        # BOŞ kabinde iki bobin halkası "kuyu" sanılıyordu (2 hedef %92–94 güven, "Kuyu ✓ Bulundu", "Konumlandı ✓", "Kanser: 2"); öneri
        # ise ODAK kapısında duruyor, 2 dk sonra "Konumlandırma tamamlanamadı" (aynı ekranda çelişki). Bu kipte plaka, sürüşün de
        # kullandığı ODAK ızgara oturtmasıyla DOĞRULANIR (`petri_izgarasi` — tek kaynak): oturmayan karede hedef YOK (Y259 ilkesi:
        # boş kabinde 0 hedef), kare lokalize sayılmaz ve şerit NEDENİ söyler. Koşullu kip AYNEN (hocanın kapısı).
        if basarili and self.kosulsuz and self.plaka_dogrulamasi:
            _plaka_engeli = self._sabit_numune_karari(meta, self._plaka_engeli(meta["odak_adaylar"]))
            if _plaka_engeli:
                air.logger.warning("%s koşulsuz karede plaka DOĞRULANMADI (%s) → hedef yok", self.ad, _plaka_engeli)
                meta.update(
                    {
                        "targets": [],
                        "odak_adaylar": [],
                        "plaka_dogrulanmadi": _plaka_engeli,
                        "plaka_ayrinti": self._plaka_ayrintisi(_plaka_engeli, meta),
                        "pemf_kapisi": {
                            "surulebilir": False,
                            "pemf_gecerli": False,
                            "nedenler": ["plaka_dogrulanmadi"],
                            "eylem": ceviri.t("ai.pemf.canliUyari.plakaDogrulanmadi"),
                            "mesajlar": [],
                            "varsayimlar": [],
                        },
                    }
                )
                with self._kilit:
                    self._meta = meta
                # OTB T-15: plaka doğrulanmadıkça önizlemede hocanın kuyu çemberleri / sayacı ("Kanser: 2") YOK → ham kare
                return (False, 0.0, 0.0, 0.0, 0.0, None, True, None)
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
        dokum = {"yontem": yontem, "yontem_tavani": tavan, "ham_guven": ham, "kalibre": yontem in YONTEM_TAVANI}
        with self._kilit:
            self._meta = meta
        # ⚠️ D1.85 (B-5.11): araştırma hattında da kabin DIŞI / sonlu olmayan hedef SÜRÜLMEZ (kedi hattıyla aynı kural).
        _neden = hedef_kabin_disi_nedeni(x_mm, y_mm, z_mm)
        if _neden:
            air.logger.warning("%s hedefi kabin/geçerlilik denetiminde REDDEDİLDİ: %s", self.ad, _neden)
            return (False, 0.0, 0.0, 0.0, guven, overlay, ozne_var, dokum)
        # ⚠️ ArUco ZORUNLU (karar #4): tavan 0.25 < MIN_GUVEN 0.3 olduğundan ölçek/piksel modunda
        # bu koşul YAPISAL olarak sağlanamaz — eşik + tavan çift emniyet.
        # T3 · Y189 KOŞULSUZ: eşik + tavan KESMEZ (güven yine raporlanır). Buraya yalnız kapının geçirdiği (konumu KABİN çerçevesinde)
        # ve kabin içi / sonlu hedef gelir — koordinatı olmayan sonuç koşulsuzda da sürülmez.
        if self.kosulsuz:
            dokum["kosulsuz"] = True
            return (True, x_mm, y_mm, z_mm, guven, overlay, ozne_var, dokum)
        return (guven >= MIN_GUVEN, x_mm, y_mm, z_mm, guven, overlay, ozne_var, dokum)

    def _plaka_ayrintisi(self, engel: str, meta: dict) -> dict:
        """OTB T-12: plaka engelinin SAYILARI — `plakaKaydi`: görülen / sapma (sabit numune), `plakaUyumsuz` / `plakaYok`: ızgara oturtmasının
        eki (bulunan / sapma / beklenen)."""
        if engel == "plakaKaydi":
            k = meta.get("sabit_numune") or {}
            return {"gorulen": k.get("gorulen"), "sapma": k.get("sapma_mm")}
        return dict(getattr(self, "_plaka_ek", None) or {})

    def _sabit_numune_karari(self, meta: dict, engel: str) -> str:
        """OTB T-7 / T-8 (sahip 19-11: "kamera petriyi gördüğü sürece, kuyular bulunuyorsa devam"): SEANSTA (mühürlü ODAK ayarı) sabit
        numunenin İLK doğrulanan ızgarası referanstır. Sonraki karede görülen kuyular referansla `oneri.SABIT_NUMUNE_ESIGI_MM` içinde
        örtüşürse kare KABUL (ODAK planı REFERANSTAN — `meta["odak_adaylar"]`), değilse engel (`plakaKaydi`; plaka kalktıysa karenin
        kendi engeli) → Y300 son plan + 30 sn + STOP AYNEN. Hazırlıkta (seans yok) ve sabit olmayan numunede bugünkü kare doğrulaması
        AYNEN. → kalan engel kodu ("" = kabul)."""
        if not (getattr(self, "sabit_numune", False) and self.odak_ayari):
            return engel
        from ai_hub.odak import oneri as odak_oneri

        if self._sabit_izgara is None:
            if not engel:
                self._sabit_izgara = [dict(k) for k in meta["odak_adaylar"]]
            return engel
        k = odak_oneri.sabit_numune_ortusmesi(self._sabit_izgara, meta["odak_adaylar"], etiketli=not engel)
        meta["sabit_numune"] = k
        if k["ortusuyor"]:
            meta["odak_adaylar"] = [dict(a) for a in self._sabit_izgara]
            return ""
        # plaka görülüyor ama referansın yerinde değil → KAYDI; hiç / 3'ten az kuyu → karenin kendi nedeni (plaka yok / kalktı)
        return "plakaKaydi" if (not engel or k["gorulen"] >= odak_oneri.IZGARA_EN_AZ) else engel

    def _plaka_engeli(self, odak_adaylar) -> str:
        """ODD B-5: görülen kuyular ODAK plaka ızgarasına oturmuyorsa engel kodu (`plakaYok` / `plakaUyumsuz`), oturuyorsa "".
        Oturtma hesaplanamazsa (numune verisi yok / bozuk) FAIL-CLOSED `plakaYok` (ODAK planı da zaten sürmez)."""
        from ai_hub.odak import oneri as odak_oneri
        from servers import ai_router as air

        self._plaka_ek = {}
        try:
            odak_oneri.petri_izgarasi(odak_adaylar)
        except odak_oneri.Engel as e:
            self._plaka_ek = dict(e.ek)  # OTB T-12: neden sapmayı (mm) ve görülen kuyu sayısını söyler
            return str(e.kod)
        except Exception:
            air.logger.warning("%s plaka ızgarası hesaplanamadı → doğrulanmadı sayıldı", self.ad, exc_info=True)
            return "plakaYok"
        return ""

    def _overlay(self, pl, ctx, result):
        from servers import ai_router as air

        try:
            # I18NI-A3.3: önizleme döngüsü istek DIŞI → cihaz dili (`arayuz_dili.json`; yoksa tr = bugünkü görünüm).
            paneller = pl.render_panels(ctx, result, lang=ceviri.etkin_dil())
            return _onizleme_karesi(paneller.get(self.onizleme_paneli), ctx)
        except Exception:
            air.logger.debug("%s overlay üretilemedi", self.ad, exc_info=True)
            return None

    def predict(self, x_mm: float, y_mm: float, z_mm: float, hedef_id: int) -> tuple:
        """ODAK (istem 45) → (duty[7], faz[7], 0.0). Faz / duty MÜHÜRDEKİ doz + kiple ODAK modelinden (`odak_plani`; seans
        başlangıcında `odak_ayarla`). Hoca modeli (`cache["predictor"]`) SÜRÜŞ KAYNAĞI OLMAZ. Ayar YOK ya da plan ENGELLİ
        (fizik denetimi / kalibrasyon) → SIFIR (bobin sürülmez — `_predict_and_drive` sıfırı "doz yok" sayar)."""
        if not self.odak_ayari:
            return [0.0] * 7, [0.0] * 7, 0.0
        return _odak_predict(self, x_mm, y_mm, z_mm, hedef_id)

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
    hedef_etiketi_anahtari = "ai.pro.hedefOnek.tumor"
    join_timeout_s = 8.0
    onizleme_paneli = "04_tumors"  # AP-B7: tümör odakları işaretli kare

    def _yukleyici(self):
        from servers import ai_router as air

        return air._yukle_em_fantom_cv

    def _pipeline_kur(self, cache):
        # ⚠️ manual_fallback=False ŞART: True olsa `manual_select` cv2 penceresi açıp headless
        # serviste bloklardı (döngü donar, E-stop ayrı yoldan çalışsa da sürüş güncellenmez).
        pl = cache["cls"](cache["cfg"], manual_fallback=False)
        pl._predictor = cache["predictor"]  # ENJEKSİYON: her karede ONNX yüklenmesin
        # KD · Y258: veri kökündeki sabit düzlem kalibrasyonu (varsa ArUco ARANMAZ) + karenin geldiği kabin kamerası.
        pl.duzlem, pl.kamera_indeksi, pl.kamera_kimligi = (
            duzlem_durumu(),
            secili_kamera_indeksi(),
            secili_kamera_kimligi(),
        )
        return pl

    def _ozne_yok_hatalari(self) -> tuple:
        # v3: lacivert hale kümesi hiç bulunamadıysa `tumor_cluster_not_found` (fantom kadrajda değil); fantom bulunup
        # içinde tümör yoksa `no_tumor_in_phantom` — o ÖZNE VAR durumudur (açı / ışık sorunu).
        return ("phantom_not_detected", "tumor_cluster_not_found")

    def _ipucu_ozne_yok(self) -> str:
        return ceviri.t("ai.pro.ipucu.fantomYok") + kor_bolge_ipucu()

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
    hedef_etiketi_anahtari = "ai.pro.hedefOnek.kuyu"
    #: Y300 (ODD B-1): SABİT NUMUNE — seans döngüsünde doğrulanamayan yeniden ölçüm son onaylı planı `_SABIT_NUMUNE_TOLERANS_S`
    #: boyunca sürdürür (kedi: N turda STOP). Fantom bu işareti TAŞIMAZ (Y283: sürüşü fail-closed kapalı).
    sabit_numune = True
    #: ODD B-5: koşulsuz kipte plaka ODAK ızgara oturtmasıyla doğrulanır (boş kabinde sahte kuyu → hedef YOK).
    plaka_dogrulamasi = True
    onizleme_paneli = "04_classify"  # AP-B7: kuyular kanserli / sağlıklı renkte, A1–D6 etiketli kare
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
        # yolo_device="cpu" ŞART (headless, CUDA yok). YOLO + predictor ENJEKTE edilir. T3 · Y189: koşulsuz kip hatta da geçer.
        pl = cache["cls"](cache["cfg"], yolo_model_path=cache["yolo_path"], yolo_device="cpu", kosulsuz=self.kosulsuz)
        pl.yolo = cache["yolo"]
        pl._predictor = cache["predictor"]
        # KD · Y258: veri kökündeki sabit düzlem kalibrasyonu (varsa ArUco ARANMAZ) + karenin geldiği kabin kamerası.
        pl.duzlem, pl.kamera_indeksi, pl.kamera_kimligi = (
            duzlem_durumu(),
            secili_kamera_indeksi(),
            secili_kamera_kimligi(),
        )
        # OTB T-7: seansta sabit numune referansı varken Hough kuyu aralığı sapması engel değil uyarı (referans örtüşmesi denetler).
        pl.kuyu_araligi_uyari = self._sabit_izgara is not None
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
        return ceviri.t("ai.pro.ipucu.petriYok") + kor_bolge_ipucu()

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
