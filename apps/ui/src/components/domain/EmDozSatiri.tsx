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
    return `${Math.round(r.area_px)} px² (mm² hesaplanmadı)`;
  }
  return "—";
}

/** Piksel kipinde sonuç kartının açıklaması; `olcekGirdisi` ölçeği hangi alanın verdiğini söyler. */
export function pikselKipiNotu(olcekGirdisi: string): string {
  return (
    "Ölçek yok (piksel kipi): koordinatlar piksel farkıdır; doz (D1–D7) ve E hesaplanmadı. " +
    `Gerçek ölçek için ${olcekGirdisi} girip yeniden analiz edin.`
  );
}

export function EmDozSatiri({ r, style }: { r: EmBolge; style?: StyleProp<TextStyle> }) {
  return (
    <Text style={style}>
      E_kanser: <Text style={{ fontWeight: "bold", color: colors.danger }}>{sayiMetni(r.E_cancer, 4)}</Text>   ·   E_sağlıklı: {sayiMetni(r.E_healthy, 4)}   ·   Alan: {alanMetni(r)}
    </Text>
  );
}
