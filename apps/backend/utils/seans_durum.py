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

#: Ham backend durumu (küçük harf) -> Türkçe gösterim etiketi.
#: ⚠️ `apps/ui/src/screens/TreatmentHistoryScreen.tsx::STATUS_LABELS_TR` ile BİREBİR AYNI olmalı.
DURUM_ETIKETLERI: dict[str, str] = {
    "completed": "Tamamlandı",
    "active": "Aktif",
    "running": "Çalışıyor",
    "in_progress": "Devam Ediyor",
    "pending": "Bekliyor",
    "stopped": "Durduruldu",
    "interrupted": "Kesintiye Uğradı",
    "aborted_recovered": "Kurtarıldı",
    "cancelled": "İptal Edildi",
    "canceled": "İptal Edildi",
    "error": "Hata",
    "failed": "Başarısız",
    "success": "Başarılı",
    # ⚠️ ÜRETİMDE KULLANILAN AMA HİÇBİR HARİTADA OLMAYAN İKİ DURUM (2026-09-12'de bulundu).
    # `database/treatment_history_db.py` bunları GERÇEKTEN yazıyor
    # (`SEANS_DURUMU_ACIL_DURDURMA`, güç-kesintisi mutabakatı) ama ne CSV ne de ekran
    # çevirebiliyordu → operatör "Emergency_stopped" görüyordu. Sahibin şikâyetiyle AYNI sınıf.
    "emergency_stopped": "Acil Durduruldu",
    "aborted_due_to_power": "Elektrik Kesintisi",
    # ⚠️ Donanım komutu reddetti → seans HİÇ başlamadı (2026-09-12 sahte-başarılı düzeltmesi).
    "hardware_rejected": "Donanım Reddetti",
}


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
    etiket = DURUM_ETIKETLERI.get(ham.lower())
    if etiket:
        return etiket
    return ham[0].upper() + ham[1:]
