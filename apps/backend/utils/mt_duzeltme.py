# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GEÇMİŞ ÖLÇÜLEN mT ÷5 — TEK KAYNAK (CH3 · Y152, sahip 2026-10-15). Yaprak modül (bağımlılık yok).

SAHİP KARARI (Y152): "Geçmiş seans kayıtlarındaki ölçülen mT değerleri 5'e BÖLÜNÜR" — yalnız doğrulanmamış eski kayıtlar, BİR KEZ
(idempotent), ORİJİNAL ayrı alanda SAKLANIR (geri alınabilir), ekranda / raporda / CSV'de "düzeltildi" notu.
NEDEN: TD2 öncesi firmware MLX90393 kazanç ayarını geri okumadan yazıyordu; sensör varsayılanında kalınca ölçülen alan TAM 5,00×
büyük basılıyordu (tezgâh Oturum 13 — Dünya alanı sınaması 4–5×). TD2'den (`e77537fc`) beri backend yalnız GERİ OKUNARAK
doğrulanmış (`GS=`) alanı kabul eder → TD2 sonrası yazılan her ölçülen alan doğru ölçekte.

İŞARET (`alan_duzeltme` sütunu — `sensor_samples` ve `sensor_run_summary`):
  ''      ESKİ kayıt (CH3 öncesi yazıldı, doğrulanmamış ölçek) → göç adayı (ölçülen alan NULL ise dokunulmaz)
  'yok'   TD2 sonrası kod yazdı → düzeltme GEREKMEZ, göç ASLA dokunmaz (her yeni yazım bunu taşır)
  'bolu5' ÷5 uygulandı; orijinal `magnetic_field_mt_orijinal` / `field_avg_orijinal` sütununda
Göç: `database/thdb_telemetri.TelemetriKarisimi._mt_bolu5_gocu` (tek işlem; sistem ayarı `mt_bolu5_goc`).
"""

from __future__ import annotations

#: Tezgâhta ölçülen ölçek hatası 4–5×; firmware kökü (kazanç ayarı varsayılanda) TAM 5,00× verir → bölen 5 (Y152).
BOLEN = 5.0

ESKI = ""
YOK = "yok"
BOLUNDU = "bolu5"

#: Sistem ayarı anahtarı — göç bir kez tamamlandı ("tamam").
GOC_ANAHTARI = "mt_bolu5_goc"

#: Ekranda / raporda / CSV'de düzeltilmiş kaydın yanında gösterilen not (Y152 metni — TEK kaynak; arayüz backend'in verdiğini gösterir).
NOT_METNI = "düzeltildi (÷5, yaklaşık — tezgâhta 4–5× ölçüldü)"


def duzeltildi_mi(isaret) -> bool:
    return isaret == BOLUNDU


def alan_notu(isaret) -> str:
    """Düzeltilmiş kaydın notu; değilse boş."""
    return NOT_METNI if duzeltildi_mi(isaret) else ""
