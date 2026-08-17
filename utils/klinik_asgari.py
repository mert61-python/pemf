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

    def __init__(self, mesaj: str):
        super().__init__(mesaj)
        self._mesaj = mesaj

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
    if not (0 < weight <= 30):
        problems.append("kilo (kg) 0-30 aralığında girilmeli")
    if not (0 < hr <= 400):
        problems.append("nabız (bpm) girilmeli (makul: ~120-220)")
    if not (0 < temp <= 50):
        problems.append("vücut sıcaklığı (°C) girilmeli (makul: ~37-39.5)")
    if age < 0:
        problems.append("yaş negatif olamaz")
    if problems:
        raise AsgariGirdiYok("Güvenilir hastalık tahmini için geçerli vital veriler gerekli: " + "; ".join(problems))


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


def ckd_dolu(features: dict) -> list:
    """DOLU sayılan alanların adları. ⚠️ Boş/boşluklu metin DOLU SAYILMAZ."""
    return [k for k, v in features.items() if v is not None and not (isinstance(v, str) and not v.strip())]


def ckd_kapisi(features: dict) -> list:
    """Yetersizse `AsgariGirdiYok` fırlatır; yeterliyse DOLU alan listesini döndürür.

    Liste döndürmesi kasıtlı: router yanıtında `filled_fields` şeffaflık alanı için gerekiyor."""
    dolu = ckd_dolu(features)
    cekirdek_dolu = [k for k in CKD_CEKIRDEK if k in dolu]
    if len(dolu) < CKD_MIN_ALAN or not cekirdek_dolu:
        eksik = ", ".join(CKD_ETIKET[k] for k in CKD_CEKIRDEK if k not in dolu)
        raise AsgariGirdiYok(
            f"Güvenilir bir tahmin için yeterli klinik veri yok "
            f"({len(dolu)}/{CKD_TOPLAM_ALAN} alan dolu; en az {CKD_MIN_ALAN} gerekli). "
            f"Ayrıca böbrek işlevine dair en az bir değer girilmeli — eksik olanlar: {eksik}. "
            f"Boş formla üretilen sonuç, hastanın verisini değil modelin genel "
            f"ortalamasını yansıtır ve yanıltıcıdır."
        )
    return dolu
