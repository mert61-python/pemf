# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Görüntü ALAN (modalite) denetimi — yanlış türde görüntüye GÜVENLE teşhis üretilmesini engeller.

NEDEN (2026-08-06, sahip bildirimi): Böbrek Patoloji modülüne bir **CT kesiti** yüklendiğinde model
hiç itiraz etmeden **"Grade 4 (en ileri) · güven %100"** döndürdü. Sınıflandırıcılar softmax üretir:
girdi eğitim dağılımının TAMAMEN dışında olsa bile olasılıklar 1'e toplanır ve model en yakın
sınıfa %100 "güvenir". Kullanıcı için bu, sessiz ve ikna edici bir YANLIŞ TEŞHİStir — tıbbi bir
cihazda kabul edilemez.

YAKLAŞIM: modelin kendi güvenine GÜVENME; girdinin modalitesini görüntünün fiziksel özelliklerinden
bağımsız olarak ölç ve modülün beklediğiyle karşılaştır. Ucuz, deterministik, model-bağımsız:

  * `grayscale` — CT / röntgen / ultrason: kanallar birbirinin AYNI (akromatik).
  * `stained`   — H&E boyalı patoloji: macenta/mor/pembe baskın, yüksek doygunluk.
  * `color`     — doğal renkli fotoğraf (kedi, petri kuyusu, fantom, laboratuvar).

KASITLI OLARAK MUHAFAZAKÂR: yalnız KESİN uyuşmazlıkta reddeder (ör. %95+ akromatik bir görüntü
gerçek bir H&E preparatı OLAMAZ). Kararsız kalırsa GEÇİRİR — meşru bir araştırma görüntüsünü
yanlışlıkla bloklamak da bir başarısızlıktır.

SINIRI (dürüstlük): modalite denetimi AYNI modalitedeki iki modülü ayıramaz — petri kuyusu ile
fantom fotoğrafı ikisi de `color`'dır (ölçüldü: petri achromatic=0.391, fantom 0.179). Onun için
modül-özel geometri denetimi gerekir → 2026-08-06'da eklendi:
`ai_hub/inference_petri_dish/plausibility.py` (petri yönü; fantom yönü zaten kapalıydı).
İKİ KATMAN BİRBİRİNİN YERİNE GEÇMEZ: CT kesitini modalite tutar, fantom fotoğrafını geometri.

KAPATMA: `PEMF_AI_DOMAIN_GUARD=0` → denetim tamamen devre dışı (araştırma kaçış kapağı).
"""

from __future__ import annotations

import logging
import os
import threading

import cv2
import numpy as np

logger = logging.getLogger(__name__)

GRAYSCALE = "grayscale"
STAINED = "stained"
COLOR = "color"
# DENETİM 2026-08-06: bozuk/boş girdide eskiden COLOR dönülüyordu. histopath {STAINED}'e
# daraltılınca bu, okunamayan bir görüntüde kullanıcıya ALAKASIZ bir "yanlış görüntü türü"
# mesajı gösterdi. Modalite BELİRLENEMİYORSA denetim yapılmamalı (fail-open): gerçekten
# bozuk görüntüyü zaten decode katmanı kendi net mesajıyla reddediyor.
UNKNOWN = "unknown"

_TR = {
    GRAYSCALE: "gri tonlamalı tıbbi görüntü (CT / röntgen / ultrason)",
    STAINED: "boyalı patoloji preparatı (H&E)",
    COLOR: "renkli fotoğraf",
}

# Modül etiketi (ai_router `_decode_image(label=...)`) → kabul edilen modaliteler.
# Etiketi burada OLMAYAN uç denetlenmez (yeni uç eklemek geriye-uyumlu kalsın).
EXPECTED: dict[str, set[str]] = {
    "kidney_ct": {GRAYSCALE},
    # DENETİM 2026-08-06 (SIZINTI — ilk sürümdeki KENDİ hatam düzeltildi): burası `{STAINED, COLOR}`
    # idi; gerekçem "bazı tarayıcılar düşük doygunluk verir" varsayımıydı. ÖLÇÜM bunu çürüttü:
    #   gerçek patoloji  08a/08b/08c → stain_ratio 0.748 / 0.352 / 0.882
    #   patoloji OLMAYAN kedi/segmentasyon/fantom/petri → 0.000 / 0.0002 / 0.0002 / 0.041
    # Yani COLOR'ı kabul etmek, kedi fotoğrafına "Grade 4 · %100" verilmesini SERBEST bırakıyordu —
    # sahibin bildirdiği CT vakasıyla AYNI sınıf hata, sadece başka bir girdiyle. {STAINED}'e
    # daraltıldı; aradaki 8 kat boşluk güvenli ayrım sağlıyor (bkz. _STAIN_RATIO marjı).
    "histopath": {STAINED},
    "reticulocytes": {STAINED, COLOR},
    "landmark": {COLOR},
    "segmentation": {COLOR},
    "cat_organ": {COLOR},
    # AI-2 (2026-10-12, YANLIŞ-POZİTİF — ÖLÇÜLDÜ): hocanın 2026-10-02 laboratuvar fotoğrafları pembe/mor (fenol kırmızılı
    # besiyeri, mor bobin, lacivert hale) → `stain_ratio` 0,15–0,23 → STAINED algılanıyor: 9 fantom fotoğrafının 2'si
    # (0,151 / 0,153) ve 6 plaka fotoğrafının 4'ü (0,169–0,229) bu uçlarda 422 "H&E gibi görünüyor" alıyordu (v1'de de —
    # kapı boru hattından ÖNCE çalışır). STAINED bu iki uca AÇILDI; H&E'yi tutan İKİNCİ KATMAN ölçüldü: gerçek patoloji
    # 08a / 08b / 08c → fantom v3 `tumor_cluster_not_found` (sonuç YOK), petri plaka kipi `not_a_petri_plate`
    # (plausibility.evaluate_plate, fail-closed), tekil kip `yolo_no_well_detected`. `histopath` {STAINED} DEĞİŞMEDİ ve
    # `_STAIN_RATIO` eşiği DEĞİŞMEDİ (patoloji ucunun ayrımı aynen). Kapı: tests/test_ai_hub_fantom_petri_v2v3_YANIT_ve_PARITE_AI2_C3.py
    "em_fantom": {COLOR, STAINED},
    # DENETİM 2026-08-06 (YANLIŞ-POZİTİF): burası yalnız {COLOR} idi ve GERÇEK bir petri girdisini
    # reddediyordu — `06b_PetriKuyu_aruco.jpg` achromatic_ratio=0.9937 (sat_mean=0.0048) ile
    # `grayscale` algılanıyor (renksiz kuyucuk + gri kabin zemini). Kullanıcı için sonuç
    # "petri modülü petri fotoğrafını kabul etmiyor" olurdu.
    # ⚠️ GEVŞETMENİN BEDELİ VAR — DOĞRULAMADA ÖLÇÜLDÜ: burası GRAYSCALE'e açılınca CT kesitlerini
    # bu uçta tutan TEK katman kalkar ve geometri katmanının O ANKİ saf 2-of-3 oyu onları
    # TUTMADI (07b/07c böbrek CT → HTTP 200, success=True, n_wells=1). Kapatan şey geometri
    # katmanına eklenen ALAN VETO'sudur (plausibility.py `area_ok`). BU İKİSİ BİRLİKTE ANLAMLI:
    # veto sökülürse burası da {COLOR}'a geri alınmalı, yoksa CT sessizce "kuyucuk" üretir.
    # AI-2: + STAINED (hocanın 24'lük plakaları 4/6 STAINED — yukarıdaki em_fantom notu; ikinci katman ölçümü aynı).
    "em_petri": {COLOR, GRAYSCALE, STAINED},
    # "thermal" BU SÖZLÜKTE DEĞİL: IR kamera hem gri hem renk-haritalı çıktı verebilir → gri / renkli sınıfı termali ayıramaz.
    # SG.G4 (2026-10-14): termal ucun KENDİ makullik kapısı var — aşağıdaki `termal_analiz` (palet uyumu), `check` çağırır.
    # "ai_pro_frame" KASITLI DIŞARIDA: canlı kamera karesi, kullanıcı yüklemesi değil.
}

# Eşikler — muhafazakâr (yanlış-pozitif reddi minimize et).
_ACHROMATIC_CHROMA = 12  # 0-255; bu farkın altındaki piksel "renksiz" sayılır
_GRAYSCALE_RATIO = 0.95  # görüntünün %95'i renksizse => gerçekten gri tonlama
_STAIN_HUE_LO, _STAIN_HUE_HI = 125, 178  # OpenCV H (0-179): mor→macenta→pembe
_STAIN_MIN_SAT = 0.18
# DENETİM 2026-08-06: eşik 0.30 idi. Ölçülen dağılım:
#   patoloji (STAINED olmalı)      : 0.352 (en düşük, 08b) … 0.882
#   patoloji-dışı (COLOR olmalı)   : 0.000 … 0.041 (en yüksek, petri)
# 0.30 eşiği en düşük gerçek patolojiye yalnız %17 pay bırakıyordu → solgun boyanmış bir preparat
# yanlışlıkla REDDEDİLEBİLİRDİ. 0.15, iki dağılımın TAM ORTASINA oturur: en yüksek yanlış-adayın
# 3.6 katı üstünde, en düşük gerçek patolojinin 2.3 katı altında → her İKİ yönde de marj.
_STAIN_RATIO = 0.15


class DomainMismatch(Exception):
    """Görüntü modalitesi modülün beklediğiyle uyuşmuyor."""

    def __init__(self, label: str, detected: str, expected: set[str], metrics: dict):
        self.label = label
        self.detected = detected
        self.expected = expected
        self.metrics = metrics
        super().__init__(self.user_message())

    def user_message(self) -> str:
        bekl = " veya ".join(sorted(_TR.get(e, e) for e in self.expected))
        return (
            f"Bu modül {bekl} bekliyor; yüklenen görüntü {_TR.get(self.detected, self.detected)} "
            f"gibi görünüyor. Yanlış görüntüyle üretilen sonuç yanıltıcı olur — lütfen doğru "
            f"türde bir görüntü yükleyin."
        )


#: A-24 (sahip kararı, 2026-10-01): modalite denetimi ÇALIŞTIRILAMAZSA analiz YAPILMAZ ve neden SÖYLENİR.
DENETIM_CALISMADI_MESAJI = (
    "Görüntü türü (modalite) denetimi çalıştırılamadı; yanlış türde görüntüyle yanıltıcı sonuç üretmemek için "
    "analiz YAPILMADI. Görüntüyü yeniden yükleyin; sürerse sunucu günlüğünü teknik desteğe iletin."
)


class DomainCheckError(Exception):
    """Modalite denetimi İÇ HATA ile çalıştırılamadı (A-24 — D4.09): kapı REDDEDER, analiz yapılmaz.

    Eskiden `analyze` istisnası DEBUG'a yazılıp denetim ATLANIYORDU (fail-open): kapı bozulursa yanlış modalite (CT →
    "Böbrek Patoloji Grade 4 · %100") sessizce analize giderdi. ⚠️ AYRI KALAN bilinçli geçiş: modalite BELİRLENEMEYEN
    (`UNKNOWN`) girdi ve kuralı OLMAYAN etiket denetlenmez — bunlar hata değil, karar."""

    def __init__(self, label: str, neden: str):
        self.label = label
        self.neden = neden
        super().__init__(f"{label}: {neden}")

    def user_message(self) -> str:
        return DENETIM_CALISMADI_MESAJI


def guard_enabled() -> bool:
    return os.getenv("PEMF_AI_DOMAIN_GUARD", "1") != "0"


def analyze(img: np.ndarray) -> tuple[str, dict]:
    """BGR görüntüden modalite + ölçümleri döndür. Saf fonksiyon, yan etkisiz."""
    if img is None or getattr(img, "size", 0) == 0:
        return UNKNOWN, {}
    # Büyük görüntüde tam çözünürlükte çalışmak gereksiz — istatistik için küçült (hız + gürültü azalır).
    h, w = img.shape[:2]
    if max(h, w) > 512:
        k = 512.0 / max(h, w)
        img = cv2.resize(img, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_AREA)
    if img.ndim == 2:
        return GRAYSCALE, {"achromatic_ratio": 1.0, "stain_ratio": 0.0}

    b, g, r = (img[:, :, i].astype(np.int16) for i in range(3))
    chroma = np.maximum(np.maximum(np.abs(r - g), np.abs(g - b)), np.abs(b - r))
    achromatic_ratio = float(np.mean(chroma <= _ACHROMATIC_CHROMA))

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(np.int16)
    sat = hsv[:, :, 1].astype(np.float32) / 255.0
    stain_mask = (hue >= _STAIN_HUE_LO) & (hue <= _STAIN_HUE_HI) & (sat >= _STAIN_MIN_SAT)
    # Boyalı doku oranı RENKLİ pikseller içinde anlamlı (siyah arka plan payı şişirmesin).
    colored = float(np.mean(chroma > _ACHROMATIC_CHROMA)) or 1e-6
    stain_ratio = float(np.mean(stain_mask))

    metrics = {
        "achromatic_ratio": round(achromatic_ratio, 4),
        "stain_ratio": round(stain_ratio, 4),
        "colored_ratio": round(colored, 4),
        "sat_mean": round(float(sat.mean()), 4),
    }

    if achromatic_ratio >= _GRAYSCALE_RATIO:
        return GRAYSCALE, metrics
    if stain_ratio >= _STAIN_RATIO:
        return STAINED, metrics
    return COLOR, metrics


# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# TERMAL MAKULLİK KAPISI — SG.G4 (2026-10-14, sahip gözlemi)
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# NEDEN: AI Hub "Termal Görüntü Analizi" CANLI kipte NORMAL web kamerasıyla (insan yüzü, oda) "Termal anormallik · %95 güven …
# Hasta (Riskli)" verdi. Termal yukarıdaki EXPECTED'de değildi → modüle giren HER görüntü softmax ile en yakın sınıfa "güvenle"
# teşhis alıyordu (2026-08-06 CT → "Grade 4 · %100" vakasının AYNI sınıfı).
# ÖLÇÜT (model-bağımsız, deterministik): termal kamera görüntüsü ya RENK PALETLİDİR (inferno / iron / jet / rainbow …: her renkli
# piksel renk uzayında TEK BOYUTLU bir palet eğrisinin üstündedir) ya da AKROMATİKTİR (white-hot / black-hot). Doğal fotoğrafın
# renkleri 3 boyutta dağılır, hiçbir palete oturmaz. "Palet uyumu" = RENKLİ piksellerin (kroma > _TERMAL_KROMA) en iyi uyan TEK
# palete (RGB uzaklığı < _TERMAL_TAU) düşen oranı; "yayılım" = o piksellerin palet indeksi p90 − p10 (paletin ne kadarını kullandığı).
# ÖLÇÜLEN DAĞILIM (2026-10-14, `DENETIM\DUZELTME-SG.md` G4; tau 30, kroma 20):
#   gerçek termal (hocanın paketi, 4)                  : uyum 0,967–0,975 · yayılım 73–86
#   sentetik termal (8 palet × 3 kaynak, q85 + q50)     : uyum 0,926–0,995 · yayılım 40–90
#   kamera kareleri (normal web kamerası, 3)            : uyum 0,000–0,010
#   doğal / laboratuvar / patoloji fotoğrafları (~60)   : uyum ≤ 0,512 (en yüksek petri fotoğrafı)
#   arayüz ekran görüntüleri (koyu lacivert, 12)        : uyum 0,66–0,94 AMA yayılım ≤ 22 (paletin yalnız koyu ucu)
# KARAR: renkli piksel < %10 → akromatik / kararsız (GEÇER, uyarılı) · uyum < 0,70 → KESİN uyumsuz (422) · uyum ≥ 0,90 ve
# yayılım ≥ 30 → termal paleti DOĞRULANDI · arası → kararsız (GEÇER, uyarılı). İki yönde marj: red eşiği doğal fotoğrafın en
# yükseğinin ×1,37 üstünde, en kötü sentetik termalin ×1,32 altında. Meşru termali bloklamamak için kararsız GEÇER (yukarıdaki
# muhafazakârlık ilkesi); ama sonuç "girdi termal olarak doğrulanamadı" uyarısını taşır (`termal_girdi_dogrulamasi`).
# SINIRI (dürüstlük): akromatik bir görüntü (white-hot termal ile CT / röntgen / gri fotoğraf) ayırt EDİLEMEZ → geçer, uyarılır.
# Tek renkli düz görüntü bir palet noktasına oturabilir (kararsız sayılır: yayılım 0). Kapı: tests/test_termal_makullik_kapisi_SG_G4.py
TERMAL_PALET = "termal_paleti"
TERMAL_AKROMATIK = "akromatik"
TERMAL_KARARSIZ = "kararsiz"
TERMAL_UYUMSUZ = "uyumsuz"

_TERMAL_KROMA = 20
_TERMAL_TAU = 30.0
_TERMAL_Q = 8  # renk küpü 32×32×32 kutu (kutu merkezinin en yakın palet noktasına uzaklığı önceden hesaplanır)
_TERMAL_RENKLI_ASGARI = 0.10
_TERMAL_RED_ESIGI = 0.70
_TERMAL_DOGRULAMA_ESIGI = 0.90
_TERMAL_YAYILIM_ASGARI = 30
_TERMAL_CV_PALETLERI = ("INFERNO", "MAGMA", "PLASMA", "HOT", "JET", "TURBO", "RAINBOW")
#: FLIR "Iron" (ironbow) yaklaşık çapaları (RGB), siyah → lacivert → mor → kırmızı → turuncu → sarı → beyaz.
_TERMAL_IRON = (
    (0, 0, 0),
    (0, 0, 80),
    (60, 0, 140),
    (140, 0, 160),
    (210, 30, 110),
    (240, 90, 30),
    (255, 160, 0),
    (255, 220, 40),
    (255, 255, 255),
)
_TERMAL_TABLO: dict | None = None
_TERMAL_KILIT = threading.Lock()

TERMAL_UYUMSUZ_MESAJI = (
    "Bu görüntü termal kamera görüntüsüne benzemiyor (renk paleti / sıcaklık eşlemesi yok). Termal kameradan çekin ya da "
    "termal görüntü yükleyin."
)
TERMAL_UYARILARI = {
    TERMAL_AKROMATIK: (
        "Girdi termal olarak doğrulanamadı: görüntü renksiz (gri tonlamalı). Beyaz-sıcak / siyah-sıcak termal görüntü olabilir "
        "ama gri bir fotoğraftan ya da tıbbi görüntüden ayırt edilemiyor — sonucu buna göre değerlendirin."
    ),
    TERMAL_KARARSIZ: (
        "Girdi termal olarak doğrulanamadı: renkleri bilinen bir termal kamera paletine tam oturmuyor. Termal kameradan "
        "çekilmiş görüntü kullanın; bu sonucu buna göre değerlendirin."
    ),
}


def _termal_tablosu() -> dict:
    """Palet başına {kutu → en yakın palet noktası uzaklığı, palet indeksi}. Bir kez (iş parçacığı güvenli) hesaplanır."""
    global _TERMAL_TABLO
    if _TERMAL_TABLO is not None:
        return _TERMAL_TABLO
    with _TERMAL_KILIT:
        if _TERMAL_TABLO is not None:
            return _TERMAL_TABLO
        lutlar = {}
        for ad in _TERMAL_CV_PALETLERI:
            cm = getattr(cv2, f"COLORMAP_{ad}")
            lutlar[ad.lower()] = (
                cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(-1, 1), cm).reshape(256, 3).astype(np.float32)
            )
        t = np.linspace(0.0, 1.0, len(_TERMAL_IRON))
        x = np.linspace(0.0, 1.0, 256)
        lutlar["iron"] = np.stack([np.interp(x, t, [c[k] for c in _TERMAL_IRON]) for k in (2, 1, 0)], axis=1).astype(
            np.float32
        )  # BGR
        merkez = (np.arange(256 // _TERMAL_Q) * _TERMAL_Q + _TERMAL_Q / 2).astype(np.float32)
        kutular = np.stack(np.meshgrid(merkez, merkez, merkez, indexing="ij"), -1).reshape(-1, 3)
        tablo = {}
        for ad, lut in lutlar.items():
            uzaklik = np.empty(len(kutular), np.float32)
            indeks = np.empty(len(kutular), np.int16)
            for i in range(0, len(kutular), 4096):
                d = kutular[i : i + 4096, None, :] - lut[None, :, :]
                d2 = (d * d).sum(-1)
                indeks[i : i + 4096] = np.argmin(d2, axis=1)
                uzaklik[i : i + 4096] = np.sqrt(d2.min(axis=1))
            tablo[ad] = (uzaklik, indeks)
        _TERMAL_TABLO = tablo
    return _TERMAL_TABLO


def termal_analiz(img: np.ndarray) -> tuple[str, dict]:
    """BGR görüntünün termal makulliği: (`TERMAL_*` durumu, ölçümler). Saf, yan etkisiz; iç hata yukarı fırlar (A-24: `check`
    onu REDDE çevirir). Boş / çözülemeyen girdi: `UNKNOWN` (yukarıdaki modalite ilkesi — decode katmanı kendi iletisini verir)."""
    if img is None or getattr(img, "size", 0) == 0:
        return UNKNOWN, {}
    if img.ndim == 2:
        return TERMAL_AKROMATIK, {"akromatik_oran": 1.0, "renkli_oran": 0.0}
    h, w = img.shape[:2]
    if max(h, w) > 256:
        k = 256.0 / max(h, w)
        img = cv2.resize(img, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_AREA)
    p = img[:, :, :3].reshape(-1, 3).astype(np.int16)
    kroma = p.max(axis=1) - p.min(axis=1)
    akromatik_oran = float(np.mean(kroma <= _ACHROMATIC_CHROMA))
    renkli = kroma > _TERMAL_KROMA
    renkli_oran = float(np.mean(renkli))
    olcum = {"akromatik_oran": round(akromatik_oran, 4), "renkli_oran": round(renkli_oran, 4)}
    if renkli_oran < _TERMAL_RENKLI_ASGARI:
        return (TERMAL_AKROMATIK if akromatik_oran >= _GRAYSCALE_RATIO else TERMAL_KARARSIZ), olcum
    q = (p[renkli] // _TERMAL_Q).astype(np.int32)
    kutu = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    en_ad, en_uyum, en_maske = "", -1.0, None
    for ad, (uzaklik, _indeks) in _termal_tablosu().items():
        maske = uzaklik[kutu] < _TERMAL_TAU
        uyum = float(np.mean(maske))
        if uyum > en_uyum:
            en_ad, en_uyum, en_maske = ad, uyum, maske
    secili = _termal_tablosu()[en_ad][1][kutu][en_maske]
    yayilim = float(np.percentile(secili, 90) - np.percentile(secili, 10)) if secili.size else 0.0
    olcum.update({"palet": en_ad, "palet_uyumu": round(en_uyum, 4), "palet_yayilimi": round(yayilim, 1)})
    if en_uyum < _TERMAL_RED_ESIGI:
        return TERMAL_UYUMSUZ, olcum
    if en_uyum >= _TERMAL_DOGRULAMA_ESIGI and yayilim >= _TERMAL_YAYILIM_ASGARI:
        return TERMAL_PALET, olcum
    return TERMAL_KARARSIZ, olcum


class TermalUyumsuz(DomainMismatch):
    """Termal uca termal kamera görüntüsüne benzemeyen (palete oturmayan) görüntü verildi — analiz YAPILMAZ (422)."""

    def __init__(self, metrics: dict):
        super().__init__("thermal", TERMAL_UYUMSUZ, {TERMAL_PALET, TERMAL_AKROMATIK}, metrics)

    def user_message(self) -> str:
        return TERMAL_UYUMSUZ_MESAJI


def termal_girdi_dogrulamasi(img: np.ndarray) -> dict:
    """Termal yanıtına eklenen girdi doğrulaması: {durum, dogrulandi, uyari, olcum}. Arayüz yalnız GÖSTERİR (kural burada).

    Kapı `check` içinde zaten koşmuş olur (uyumsuz girdi buraya gelmez); bu yalnız GEÇEN girdinin doğrulanıp doğrulanmadığını
    söyler. Hata fırlatmaz: hesap düşerse "doğrulanamadı" der (kapı kararı `check`te verildi, analiz ondan sonra koşar)."""
    if not guard_enabled():
        return {
            "durum": "kapali",
            "dogrulandi": False,
            "uyari": "Görüntü türü denetimi bu cihazda kapalı — girdi termal olarak doğrulanmadı; sonucu buna göre değerlendirin.",
            "olcum": {},
        }
    try:
        durum, olcum = termal_analiz(img)
    except Exception:
        logger.warning("termal girdi doğrulaması hesaplanamadı", exc_info=True)
        durum, olcum = UNKNOWN, {}
    if durum == TERMAL_PALET:
        return {"durum": durum, "dogrulandi": True, "uyari": None, "olcum": olcum}
    uyari = TERMAL_UYARILARI.get(durum) or TERMAL_UYARILARI[TERMAL_KARARSIZ]
    return {"durum": durum, "dogrulandi": False, "uyari": uyari, "olcum": olcum}


def check(img: np.ndarray, label: str) -> None:
    """`label` modülü için görüntü modalitesini denetle; uyuşmazsa DomainMismatch fırlat."""
    if not guard_enabled():
        return
    if label == "thermal":
        # SG.G4: termal ucun kendi makullik kapısı (yukarıda). İç hata = REDDET (A-24), KESİN uyumsuz = 422, gerisi geçer.
        try:
            durum, metrics = termal_analiz(img)
        except Exception as e:
            logger.warning("TERMAL MAKULLİK DENETİMİ ÇALIŞTIRILAMADI — analiz REDDEDİLDİ (A-24)", exc_info=True)
            raise DomainCheckError(label, f"{type(e).__name__}: {e}") from e
        if durum == TERMAL_UYUMSUZ:
            logger.warning("TERMAL UYUŞMAZLIĞI: termal kamera görüntüsüne benzemiyor ölçüm=%s", metrics)
            raise TermalUyumsuz(metrics)
        return
    expected = EXPECTED.get(label)
    if not expected:
        return
    try:
        detected, metrics = analyze(img)
    except Exception as e:
        # A-24: iç hatada REDDET (eskiden DEBUG + `return` = denetim sessizce atlanıyordu).
        logger.warning("MODALİTE DENETİMİ ÇALIŞTIRILAMADI [%s] — analiz REDDEDİLDİ (A-24)", label, exc_info=True)
        raise DomainCheckError(label, f"{type(e).__name__}: {e}") from e
    if detected == UNKNOWN or detected in expected:
        return  # UNKNOWN → modalite belirlenemedi, denetim yapma (fail-open, yukarıya bkz.)
    logger.warning(
        "ALAN UYUŞMAZLIĞI [%s]: beklenen=%s algılanan=%s ölçüm=%s", label, sorted(expected), detected, metrics
    )
    raise DomainMismatch(label, detected, expected, metrics)
