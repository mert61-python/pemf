# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ASGARİ KLİNİK GİRDİ KAPILARI — İKİ TRANSPORT İÇİN TEK KAYNAK.

Bu modül `servers/ai_router.py` içinde GÖMÜLÜ olan iki kapıyı çağrılabilir hâle getirir; kapıların
davranışı, eşikleri ve mesaj dizeleri BİT-AYNI taşınmıştır (sertleştirme ya da gevşetme YOK).

⚠️ NEDEN AYRI MODÜL (denetim 2026-08-17): `:8100` (`ai_service/app.py`) uçları **auth-muaftır** ve
backend'i atlayan bir istemci onları doğrudan çağırabilir. Kapı yalnız router'da kalırsa o
transportta HİÇ çalışmaz — deponun kendi kuralı bunu yazıyor
(`ai_hub/inference_petri_dish/plausibility.py`). Ölçüldü, AYNI boş gövde:

    POST  backend /api/ai/disease         {}  →  HTTP 422 "geçerli vital veriler gerekli"
    POST  :8100   /infer/disease          {}  →  HTTP 200 "Conjunctivitis %53", low_confidence:false
    POST  backend /api/ai/disease/kidney  {}  →  HTTP 422 "yeterli klinik veri yok"
    POST  :8100   /infer/kidney_disease   {}  →  HTTP 200 prob_pct 78.0, label "ckd"

%78 sayısı hastanın verisinden DEĞİL, eğitim setinin ön-olasılığından gelir — sahibin 2026-08-07
bildiriminin ("hiçbir veri girmeden analiz yaptığımda %78 çıkıyor") birebir kaynağı.

⚠️ YAPRAK MODÜL: yalnız stdlib kullanır (cv2/numpy/pandas/depo-içi import YOK) — `utils/image_domain`
ve `utils/ses_kalitesi` ile aynı sınıf, böylece `docker/Dockerfile.ai` imajına tek satırla girer.
⚠️ HTTP BİLMEZ: `AsgariGirdiYok` fırlatır, her transport onu kendi hata tipine çevirir
(`utils/image_domain.DomainMismatch` deseninin aynısı).
⚠️ `ai_hub/` ALTINA KONMADI: `pyproject.toml` coverage `omit */ai_hub/*` + mypy/ruff `exclude`
yüzünden kapı kalıcı kör noktaya girerdi.
"""

from __future__ import annotations


class AsgariGirdiYok(Exception):
    """Girdi, güvenilir bir tahmin için yetersiz. `user_message()` kullanıcıya gösterilebilir."""

    def __init__(self, mesaj: str, kod: str | None = None, ayrinti=None):
        super().__init__(mesaj)
        self._mesaj = mesaj
        #: I18N-P1: makine-okur neden ("vital" | "ckd") + ayrıntı — backend iletiyi istek dilinde KATALOGDAN kurar; `mesaj` (Türkçe) aynen kalır
        #: (AI mikroservisi bu modülü katalogsuz kullanır).
        self.kod = kod
        self.ayrinti = ayrinti

    def user_message(self) -> str:
        return self._mesaj


# ── 1) Kedi hastalık analizi: vital kapısı ───────────────────────────────────


def _sayi(v) -> float:
    """Sayıya çevir; çevrilemezse 0.0.

    ⚠️ `:8100` gövdesi Pydantic'ten GEÇMİYOR (`payload: dict = Body(...)`), yani `"4.2"` gibi metin
    gelebilir ve `0 < "4.2"` Python 3'te TypeError verirdi → kapı yeni bir 500 arıza modu doğururdu.
    Çevrilemeyen değer 0.0 sayılır ve zaten kapıya takılır (fail-closed)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def vital_kapisi(features: dict) -> None:
    """Sıfır/boş vital ile anlamsız tahmin üretilmesin (audit P1).

    Canlı bir kedide kilo/nabız/sıcaklık 0 olamaz; eksikse SESSİZ yanlış tahmin yerine hata."""
    weight = _sayi(features.get("weight"))
    hr = _sayi(features.get("hr"))
    temp = _sayi(features.get("temp"))
    age = _sayi(features.get("age"))

    problems = []
    kodlar = []  # I18N-P1: makine-okur sorun kodları (`AsgariGirdiYok.ayrinti`)
    if not (0 < weight <= 30):
        kodlar.append("kilo")
        problems.append("kilo (kg) 0-30 aralığında girilmeli")
    if not (0 < hr <= 400):
        kodlar.append("nabiz")
        problems.append("nabız (bpm) girilmeli (makul: ~120-220)")
    if not (0 < temp <= 50):
        kodlar.append("sicaklik")
        problems.append("vücut sıcaklığı (°C) girilmeli (makul: ~37-39.5)")
    if age < 0:
        kodlar.append("yas")
        problems.append("yaş negatif olamaz")
    if problems:
        raise AsgariGirdiYok(
            "Güvenilir hastalık tahmini için geçerli vital veriler gerekli: " + "; ".join(problems),
            kod="vital",
            ayrinti=kodlar,
        )


# ── 2) İnsan CKD (UCI): asgari alan + çekirdek belirteç kapısı ───────────────

#: KURAL (muhafazakâr, uydurma klinik eşik YOK):
#:   1) En az `CKD_MIN_ALAN` alan DOLU olmalı → "hiç veri girmeden sonuç" imkânsız.
#:   2) Böbrek işleviyle DOĞRUDAN ilgili en az bir belirteç olmalı → aksi hâlde tahminde renal
#:      sinyal yoktur, sayı yalnız demografiden türer.
CKD_MIN_ALAN = 6
CKD_CEKIRDEK = ("sc", "bu", "sg", "al", "hemo")  # kreatinin, üre, dansite, albümin, hemoglobin
CKD_ETIKET = {
    "sc": "serum kreatinin",
    "bu": "kan üresi",
    "sg": "idrar dansitesi",
    "al": "albümin",
    "hemo": "hemoglobin",
}
#: Mesajdaki payda. ⚠️ Tek kaynak `servers.ai_router.KidneyDiseaseInput` (24 alan); burada yalnız
#: SAYI tutuluyor — 24 isimli listeyi çoğaltmak iki kaynağın sessizce ayrışmasına yol açardı.
#: `:8100` gövdesi kısmi bir dict olabileceği için `len(features)` payda olarak KULLANILAMAZ
#: (router bugün 24 yazıyor; mesaj dizesi testlerle kilitli).
CKD_TOPLAM_ALAN = 24

#: D6.20 (B-5.21): 10 kategorik alanın EĞİTİM SÖZLÜĞÜ — `preprocessor.pkl` `OneHotEncoder.categories_` (ölçüldü:
#: `drop='first'`, `handle_unknown='ignore'`). Sözlük DIŞI değer ('evet', 'var', '1', 'true', 'anormal' …) modelde SESSİZCE
#: düşürülen ilk kategoriye ('abnormal' / 'notpresent' / 'no' / 'good') dönüşüyordu: `htn: "evet"` = hipertansiyon YOK
#: (ölçüldü: 'evet' 0,115 notckd ↔ 'yes' 0,795 ckd) — klinik anlam TERSİNE, 200 + `filled_fields` onu DOLU sayıyordu.
#: Arayüz (ve APK 2.3.34) yalnız bu kodları gönderir. Karşılaştırma modelin normalizasyonuyla (strip + lower).
CKD_KATEGORIK = {
    "rbc": ("normal", "abnormal"),
    "pc": ("normal", "abnormal"),
    "pcc": ("notpresent", "present"),
    "ba": ("notpresent", "present"),
    "htn": ("no", "yes"),
    "dm": ("no", "yes"),
    "cad": ("no", "yes"),
    "appet": ("good", "poor"),
    "pe": ("no", "yes"),
    "ane": ("no", "yes"),
}
#: Modelin EKSİK saydığı yer tutucular (`inference_human_kidney_disease._eksik` ile aynı küme) — impute edilir, DOLU sayılmaz.
_EKSIK_METIN = ("", "?", "NA", "NaN", "nan", "—", "-")


def _bos_mu(v) -> bool:
    """Model bu değeri EKSİK sayıp impute ediyor mu (None · float NaN · boş / yer tutucu metin)."""
    if v is None:
        return True
    if isinstance(v, float) and v != v:
        return True
    return isinstance(v, str) and v.strip() in _EKSIK_METIN


def ckd_dolu(features: dict) -> list:
    """DOLU sayılan alanların adları. ⚠️ Boş/boşluklu metin DOLU SAYILMAZ; D6.20: modelin eksik saydığı yer tutucular
    ('?', 'NA', '-', NaN …) da sayılmaz — `filled_fields` modelin GERÇEKTEN kullandığı alan sayısını söyler."""
    return [k for k, v in features.items() if not _bos_mu(v)]


def ckd_gecersiz_kategorik(features: dict) -> dict:
    """Sözlük DIŞI kategorik değerler → {alan: ham değer (≤ 40 karakter)}; eksik / yer tutucu değer geçersiz SAYILMAZ."""
    gecersiz = {}
    for alan, gecerli in CKD_KATEGORIK.items():
        v = features.get(alan)
        if _bos_mu(v):
            continue
        if str(v).strip().lower() not in gecerli:
            gecersiz[alan] = str(v)[:40]
    return gecersiz


def ckd_kapisi(features: dict) -> list:
    """Yetersizse `AsgariGirdiYok` fırlatır; yeterliyse DOLU alan listesini döndürür.

    Liste döndürmesi kasıtlı: router yanıtında `filled_fields` şeffaflık alanı için gerekiyor.
    D6.20: sözlük DIŞI kategorik değer ÖNCE reddedilir (`kod="ckd_kategorik"`; iki transport da 422)."""
    gecersiz = ckd_gecersiz_kategorik(features)
    if gecersiz:
        ayrinti = {"alanlar": [{"alan": k, "deger": v, "gecerli": list(CKD_KATEGORIK[k])} for k, v in gecersiz.items()]}
        raise AsgariGirdiYok(
            "Geçersiz kategorik değer: "
            + "; ".join(f"{d['alan']}='{d['deger']}' (geçerli: {', '.join(d['gecerli'])})" for d in ayrinti["alanlar"])
            + ". Bu alanlar yalnız sözlükteki değerleri kabul eder; model başka bir değeri sessizce ilk kategoriye "
            "('no', 'notpresent', 'abnormal', 'good') çevirir ve sonucun klinik anlamı tersine dönebilir — "
            "değeri düzeltip yeniden gönderin.",
            kod="ckd_kategorik",
            ayrinti=ayrinti,
        )
    dolu = ckd_dolu(features)
    cekirdek_dolu = [k for k in CKD_CEKIRDEK if k in dolu]
    if len(dolu) < CKD_MIN_ALAN or not cekirdek_dolu:
        eksik = ", ".join(CKD_ETIKET[k] for k in CKD_CEKIRDEK if k not in dolu)
        eksik_kodlar = [k for k in CKD_CEKIRDEK if k not in dolu]
        raise AsgariGirdiYok(
            f"Güvenilir bir tahmin için yeterli klinik veri yok "
            f"({len(dolu)}/{CKD_TOPLAM_ALAN} alan dolu; en az {CKD_MIN_ALAN} gerekli). "
            f"Ayrıca böbrek işlevine dair en az bir değer girilmeli — eksik olanlar: {eksik}. "
            f"Boş formla üretilen sonuç, hastanın verisini değil modelin genel "
            f"ortalamasını yansıtır ve yanıltıcıdır.",
            kod="ckd",
            ayrinti={"dolu": len(dolu), "toplam": CKD_TOPLAM_ALAN, "asgari": CKD_MIN_ALAN, "eksik": eksik_kodlar},
        )
    return dolu
