# -*- coding: utf-8 -*-
# Author: mertaygn
"""SEANS DURUMU — Türkçe gösterim etiketleri (backend dışa aktarımları için TEK KAYNAK).

===============================================================================
NEDEN VAR — SAHİP BİLDİRİMİ (2026-09-12)
===============================================================================
"bu csv de tamamlandı yazmalı ingilizce yazıyor completed onu düzelt."

Arayüz durumu Türkçeye çeviriyordu (`TreatmentHistoryScreen.tsx::STATUS_LABELS_TR`),
CSV ise DB'nin HAM İngilizce değerini (`completed`) yazıyordu. Operatör ekranda
"Tamamlandı", Excel'de "completed" görüyordu — aynı kaydın iki farklı dili.

⚠️ ÇEVİRİ YALNIZ GÖSTERİM İÇİNDİR. DB'deki ham değer (renk/durum mantığı, sorgular,
`session_status == "completed"` karşılaştırmaları) DEĞİŞMEZ. Bu modül veri katmanına
değil, YALNIZ dışa aktarım/gösterim sınırına uygulanır.

⚠️ İKİ DİLDE İKİ HARİTA VAR (burada Python, arayüzde TypeScript) ve ikisi SESSİZCE
ayrışabilir: backend yeni bir durum üretir, arayüz onu çevirir, CSV çevirmez (ya da
tersi). `tests/test_seans_durum_etiketi.py` iki haritayı ANAHTAR ANAHTAR karşılaştırır.
"""

from __future__ import annotations

import re

from utils import ceviri

#: Ham backend durumu (küçük harf) -> katalog ANAHTARI (`seans.durum.*`; metin istek dilinde — I18N-P1). Anahtar kümesi arayüz `STATUS_ANAHTARLARI` ile AYNI
#: (`tests/test_seans_durum_etiketi.py` iki tabloyu ANAHTAR ANAHTAR ve çözülen Türkçe etiketle karşılaştırır).
DURUM_ETIKETLERI: dict[str, str] = {
    "completed": "seans.durum.completed",
    "active": "seans.durum.active",
    "running": "seans.durum.running",
    "in_progress": "seans.durum.in_progress",
    "pending": "seans.durum.pending",
    "stopped": "seans.durum.stopped",
    "interrupted": "seans.durum.interrupted",
    "aborted_recovered": "seans.durum.aborted_recovered",
    "cancelled": "seans.durum.cancelled",
    "canceled": "seans.durum.canceled",
    "error": "seans.durum.error",
    "failed": "seans.durum.failed",
    "success": "seans.durum.success",
    # ⚠️ ÜRETİMDE KULLANILAN AMA HİÇBİR HARİTADA OLMAYAN İKİ DURUM (2026-09-12'de bulundu).
    # `database/treatment_history_db.py` bunları GERÇEKTEN yazıyor
    # (`SEANS_DURUMU_ACIL_DURDURMA`, güç-kesintisi mutabakatı) ama ne CSV ne de ekran
    # çevirebiliyordu → operatör "Emergency_stopped" görüyordu. Sahibin şikâyetiyle AYNI sınıf.
    "emergency_stopped": "seans.durum.emergency_stopped",
    "aborted_due_to_power": "seans.durum.aborted_due_to_power",
    # ⚠️ Donanım komutu reddetti → seans HİÇ başlamadı (2026-09-12 sahte-başarılı düzeltmesi).
    "hardware_rejected": "seans.durum.hardware_rejected",
    # ⚠️ Y207 (S-D5.3): kanıtı 3 açılış boyunca okunamayan seans "süre bilinmiyor" kapanır (`SEANS_DURUMU_SURE_BILINMIYOR`).
    "aborted_duration_unknown": "seans.durum.aborted_duration_unknown",
}


#: Seansa / DB'ye giden `mode` değeri -> katalog ANAHTARI (`seans.mod.*`). "AI" iki dilde aynıdır → tabloda YOK (aynen döner).
#: Anahtar kümesi arayüz `utils/seansDegerEtiketi.ts::modEtiketi` ile AYNI (`tests/test_seans_mod_hedef_etiketi_P1.py` karşılaştırır).
MOD_ETIKETLERI: dict[str, str] = {
    "Manuel": "seans.mod.manuel",
    "Otomatik": "seans.mod.otomatik",
}

#: Seansa / literatür aramasına giden `target_condition` değeri (arayüz `AUTO_TARGETS`) -> katalog ANAHTARI (`seans.hedef.*`).
HEDEF_ETIKETLERI: dict[str, str] = {
    "Doku İyileşmesi": "seans.hedef.dokuIyilesmesi",
    "Eklem Ağrısı": "seans.hedef.eklemAgrisi",
    "Kas Spazmı": "seans.hedef.kasSpazmi",
    "Kırık İyileşmesi": "seans.hedef.kirikIyilesmesi",
    "Enflamasyon Azaltma": "seans.hedef.enflamasyonAzaltma",
    "Sinir Rejenerasyonu": "seans.hedef.sinirRejenerasyonu",
    "Bağ Dokusu Tamiri": "seans.hedef.bagDokusuTamiri",
    "Ödem Azaltma": "seans.hedef.odemAzaltma",
}


#: I18NI-A1.9: AI Pro seans modu VERİSİ `AI Pro · <model> [· <hedef>]` (ai_router; Türkçe saklanır — profil türetimi buna bakar) parçaları.
AI_PRO_ONEK = "AI Pro · "
AI_PRO_MODEL = {"Kedi Organ": "ai.model.kedi", "Fantom Tümör": "ai.model.fantom", "Petri Kuyu": "ai.model.petri"}
AI_PRO_ORGAN = {
    "Tüm Vücut": "ai.organ.tumVucut",
    "Mide": "ai.organ.mide",
    "Böbrek": "ai.organ.bobrek",
    "Karaciğer": "ai.organ.karaciger",
    "Mesane": "ai.organ.mesane",
    "Pankreas": "ai.organ.pankreas",
    "Bağırsak": "ai.organ.bagirsak",
    "Kalp": "ai.organ.kalp",
    "Dalak": "ai.organ.dalak",
    "Akciğer (sağ)": "ai.organ.akcigerSag",
    "Akciğer (sol)": "ai.organ.akcigerSol",
}
AI_PRO_HEDEF_ETIKETI = {"Tümör": "seans.aiProMod.tumor", "Kuyu": "seans.aiProMod.kuyu"}
_OTOMATIK = re.compile(r"^(.+) \(otomatik\)$")
_NUMARALI = re.compile(r"^(.+) (\d+)$")
#: OTB T-9: AI Pro seans KAYDININ hedefi (`target_condition` — mühür etiketi): bütün plaka + "<Kuyu|Tümör> <C2|T1|3>".
AI_PRO_KAYIT_HEDEFI = {"Tüm petri": "seans.aiProMod.tumPetri"}
_AI_PRO_KAYIT_HEDEF_DESENI = re.compile(r"^(Kuyu|Tümör) ([A-Z]?\d+)$")


def _hedef_etiketi(e: str) -> str:
    etiket_anahtari = AI_PRO_HEDEF_ETIKETI.get(e)
    return ceviri.t(etiket_anahtari) if etiket_anahtari else e


def _ai_pro_hedef(h: str) -> str:
    organ_anahtari = AI_PRO_ORGAN.get(h)
    if organ_anahtari:
        return ceviri.t(organ_anahtari)
    if h in AI_PRO_KAYIT_HEDEFI:  # OTB T-9b: TÜM PETRİ seansının mod hedefi
        return _ai_pro_kayit_hedefi(h)
    m = _OTOMATIK.match(h)
    if m:
        return ceviri.t("seans.aiProMod.otomatikHedef", hedef=_hedef_etiketi(m[1]))
    m = _NUMARALI.match(h)
    if m and m[1] in AI_PRO_HEDEF_ETIKETI:
        return f"{_hedef_etiketi(m[1])} {m[2]}"
    return h


def mod_etiketi(mod):
    """Seans modunu (`Manuel` / `Otomatik` / `AI` / `AI Pro · …`) istek dilindeki gösterim etiketine çevirir. ⚠️ YALNIZ GÖSTERİM: DB'deki ham
    değer DEĞİŞMEZ. Bilinmeyen / metin olmayan değer (serbest metin, eski kayıt, `AI`, None) AYNEN döner — hücre boş kalmaz, değer yutulmaz.
    AI Pro modu parça parça (tanınmayan parça AYNEN); TR'de çıktı ham değerle bayt bayt aynı."""
    if not isinstance(mod, str):
        return mod
    mod_anahtari = MOD_ETIKETLERI.get(mod)
    if mod_anahtari:
        return ceviri.t(mod_anahtari)
    if mod.startswith(AI_PRO_ONEK):
        model, *hedef = mod[len(AI_PRO_ONEK) :].split(" · ")
        model_anahtari = AI_PRO_MODEL.get(model)
        model_g = ceviri.t(model_anahtari) if model_anahtari else model
        return " · ".join([AI_PRO_ONEK + model_g, *(_ai_pro_hedef(h) for h in hedef)])
    return mod


def _ai_pro_kayit_hedefi(h: str) -> str:
    """OTB T-9: AI Pro seans satırının hedefi (VERİ, Türkçe: "Tüm petri" / "Kuyu C2" / "Tümör T1") istek dilinde; tanınmayan AYNEN."""
    kayit_hedef_anahtari = AI_PRO_KAYIT_HEDEFI.get(h)
    if kayit_hedef_anahtari:
        return ceviri.t(kayit_hedef_anahtari)
    m = _AI_PRO_KAYIT_HEDEF_DESENI.match(h)
    return f"{_hedef_etiketi(m[1])} {m[2]}" if m else h


def hedef_etiketi(hedef):
    """Hedef durumunu (`AUTO_TARGETS` değeri) istek dilindeki gösterim etiketine çevirir. ⚠️ YALNIZ GÖSTERİM (değer seansa / aramaya
    Türkçe GİDER). Bilinmeyen / metin olmayan değer (serbest metin, eski kayıt, None) AYNEN döner. AI Pro hedefi (OTB T-9) parça parça."""
    if not isinstance(hedef, str):
        return hedef
    hedef_anahtari = HEDEF_ETIKETLERI.get(hedef)
    return ceviri.t(hedef_anahtari) if hedef_anahtari else _ai_pro_kayit_hedefi(hedef)


#: YS2 a (B1): AI Pro durdurma nedeni kodu (`session_parameters.durdurma_nedeni`) -> katalog ANAHTARI. Arayüz `durdurmaNedeni.*` ile AYNI.
DURDURMA_NEDENLERI: dict[str, str] = {
    "plaka_kaydi": "seans.durdurmaNedeni.plaka_kaydi",
    "plaka_dogrulanamadi": "seans.durdurmaNedeni.plaka_dogrulanamadi",
    "hedef_kaybi": "seans.durdurmaNedeni.hedef_kaybi",
}


def durum_etiketi(durum, neden=None) -> str:
    """Ham seans durumunu Türkçe gösterim etiketine çevirir.

    ⚠️ BİLİNMEYEN DURUM SİLİNMEZ: ham değer (baş harfi büyütülerek) döner. Etiket
    haritası bayatladığında hücre BOŞ kalsaydı, operatör "durum yok" sanırdı —
    oysa kayıt bir durum taşıyor, biz onu adlandıramıyoruz. Arayüzdeki
    `statusLabelTr()` ile AYNI kural.

    YS2 a (B1): `neden` (AI Pro durdurma nedeni kodu) biliniyorsa "Durduruldu (plaka kaydı)"; bilinmeyen / boş neden eklenmez.
    """
    if durum is None:
        return ""
    ham = str(durum).strip()
    if not ham:
        return ""
    durum_anahtari = DURUM_ETIKETLERI.get(ham.lower())
    etiket = ceviri.t(durum_anahtari) if durum_anahtari else ham[0].upper() + ham[1:]
    neden_anahtari = DURDURMA_NEDENLERI.get(str(neden or ""))
    if neden_anahtari:
        return ceviri.t("seans.durumNedenli", durum=etiket, neden=ceviri.t(neden_anahtari))
    return etiket
