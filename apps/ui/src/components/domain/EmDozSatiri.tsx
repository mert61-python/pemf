// Author: mertaygn, cglrgrkn
/**
 * EM araştırma hattı (fantom / petri) bölge satırı: E_kanser · E_sağlıklı · Alan.
 *
 * ⚠️ D1.E07 (İG-5.76): PİKSEL kipinde (ölçek yok) doz/E hesaplanmaz (`null`) ve piksel alanı mm² DEĞİLDİR.
 * Eskiden `Number(null).toFixed(4)` "0.0000" basıyordu ("hesaplandı, sıfır") ve piksel alanı "mm²" etiketiyle
 * gösteriliyordu. Hesaplanmamış değer '—'; mm² yoksa piksel alanı px² olarak açıkça yazılır.
 */
import React from "react";
import { Text, type StyleProp, type TextStyle } from "react-native";

import { colors } from "@/theme/tokens";
import i18n from "i18next";
import { Trans } from "react-i18next";

export interface EmBolge {
  E_cancer?: number | null;
  E_healthy?: number | null;
  area_mm2?: number | null;
  area_px?: number | null;
}

export function sayiMetni(v: unknown, basamak: number): string {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(basamak) : "—";
}

export function alanMetni(r: EmBolge): string {
  if (typeof r.area_mm2 === "number" && Number.isFinite(r.area_mm2)) return `${r.area_mm2.toFixed(1)} mm²`;
  if (typeof r.area_px === "number" && Number.isFinite(r.area_px)) {
    return i18n.t("kontrol.emDoz.pikselAlan", { px: Math.round(r.area_px) });
  }
  return "—";
}

/** D1.100 (B-5.16): konum çözülemediyse (ışın hedef düzlemini geçerli noktada kesmiyor) "(0, 0, 0)" değil açıkça söylenir. */
export function konumMetni(c: number[] | null | undefined, birim: string): string {
  if (!Array.isArray(c) || c.length < 3 || !c.every((v) => typeof v === "number" && Number.isFinite(v))) {
    return i18n.t("kontrol.emDoz.konumYok");
  }
  return `(${c[0].toFixed(1)}, ${c[1].toFixed(1)}, ${c[2].toFixed(1)}) ${birim}`;
}

/** Piksel kipinde sonuç kartının açıklaması; `olcekGirdisi` ölçeği hangi alanın verdiğini söyler. */
export function pikselKipiNotu(olcekGirdisi: string): string {
  return (
    i18n.t("kontrol.emDoz.pikselNotu", { olcekGirdisi })
  );
}

export function EmDozSatiri({ r, style }: { r: EmBolge; style?: StyleProp<TextStyle> }) {
  return (
    <Text style={style}>
      <Trans
        i18nKey="kontrol.emDoz.satir"
        values={{ kanser: sayiMetni(r.E_cancer, 4), saglikli: sayiMetni(r.E_healthy, 4), alan: alanMetni(r) }}
        components={{ kalin: <Text style={{ fontWeight: "bold", color: colors.danger }} /> }}
      />
    </Text>
  );
}
