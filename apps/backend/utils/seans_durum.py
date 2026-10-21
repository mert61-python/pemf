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


def mod_etiketi(mod):
    """Seans modunu (`Manuel` / `Otomatik` / `AI`) istek dilindeki gösterim etiketine çevirir. ⚠️ YALNIZ GÖSTERİM: DB'deki ham değer DEĞİŞMEZ.
    Bilinmeyen / metin olmayan değer (serbest metin, eski kayıt, `AI`, None) AYNEN döner — hücre boş kalmaz, değer yutulmaz."""
    if not isinstance(mod, str):
        return mod
    mod_anahtari = MOD_ETIKETLERI.get(mod)
    return ceviri.t(mod_anahtari) if mod_anahtari else mod


def hedef_etiketi(hedef):
    """Hedef durumunu (`AUTO_TARGETS` değeri) istek dilindeki gösterim etiketine çevirir. ⚠️ YALNIZ GÖSTERİM (değer seansa / aramaya
    Türkçe GİDER). Bilinmeyen / metin olmayan değer (serbest metin, eski kayıt, None) AYNEN döner."""
    if not isinstance(hedef, str):
        return hedef
    hedef_anahtari = HEDEF_ETIKETLERI.get(hedef)
    return ceviri.t(hedef_anahtari) if hedef_anahtari else hedef


def durum_etiketi(durum) -> str:
    """Ham seans durumunu Türkçe gösterim etiketine çevirir.

    ⚠️ BİLİNMEYEN DURUM SİLİNMEZ: ham değer (baş harfi büyütülerek) döner. Etiket
    haritası bayatladığında hücre BOŞ kalsaydı, operatör "durum yok" sanırdı —
    oysa kayıt bir durum taşıyor, biz onu adlandıramıyoruz. Arayüzdeki
    `statusLabelTr()` ile AYNI kural.
    """
    if durum is None:
        return ""
    ham = str(durum).strip()
    if not ham:
        return ""
    durum_anahtari = DURUM_ETIKETLERI.get(ham.lower())
    if durum_anahtari:
        return ceviri.t(durum_anahtari)
    return ham[0].upper() + ham[1:]
