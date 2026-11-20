# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y306 (sahip 19-11, madde 6): TEK MLX alan sensörü (MLX90393) var ve kabinde GEZDİRİLİYOR — firmware onu kartın kanal 6'sına yazar
(`PEMF_SENSOR_BOBIN_IDLERI`; firmware DEĞİŞMEZ). Değer bir bobinin değil KABİNİN sensörüdür → raporlarda / dışa aktarımda "Kabin sensörü
(MLX)" adıyla, bobin satırlarından AYRI. Kanal → sensör eşlemesi TEK sabit (arayüz eşi `apps/ui/src/utils/kabinSensoru.ts`). Eski kayıtlar
da bu adla gösterilir — veri göçü YOK (DB'de `coil_id` 6 kalır)."""

MLX_KANALI = 6


def kabin_sensoru_kanali_mi(kanal) -> bool:
    """Kayıt / telemetri kanalı (metin ya da sayı) kabin sensörü mü."""
    try:
        return kanal is not None and str(kanal).strip() != "" and int(float(kanal)) == MLX_KANALI
    except (TypeError, ValueError):
        return False
