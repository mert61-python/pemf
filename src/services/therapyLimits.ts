/**
 * therapyLimits — PEMF tedavi parametreleri için güvenlik sınırları (tek kaynak).
 * ============================================================================
 * Medikal cihaz güvenliği: bobin sürücüsüne sınır-dışı değer GİTMEMELİ. Tüm
 * başlatma yolları (Otomatik/Manuel/AI + per-coil panel) bu sınırları uygular.
 *
 * Aralıklar literatür preset'iyle uyumludur (freq~10 Hz, duty~25%). Donanım
 * spesifikasyonu netleştikçe burada tek noktadan güncellenebilir.
 * NOT: duration 0 = "süresiz" (geçerli); start dışı (stop) komutlarda clamp UYGULANMAZ.
 */
export const THERAPY_LIMITS = {
  freq: { min: 0.5, max: 100, label: "Frekans", unit: "Hz" },
  duty: { min: 1, max: 50, label: "Duty", unit: "%" },
  phase: { min: 0, max: 360, label: "Faz", unit: "°" },
  intensity: { min: 0.1, max: 20, label: "Yoğunluk", unit: "mT" },
  duration: { min: 0, max: 120, label: "Süre", unit: "dk" }, // 0 = süresiz
} as const;

export type TherapyParamKey = keyof typeof THERAPY_LIMITS;

/** Tek bir değeri güvenli aralığa çeker (NaN → min). */
export function clampParam(key: TherapyParamKey, value: number): number {
  const lim = THERAPY_LIMITS[key];
  if (isNaN(value)) return lim.min;
  return Math.min(lim.max, Math.max(lim.min, value));
}

/**
 * Verilen parametreleri güvenli aralığa çeker; sınır-dışı olanların kullanıcı
 * mesajını döndürür. (Reddetmek yerine clamp+bilgilendir → tedavi hep güvenli sürer.)
 */
export function clampTherapyParams(
  input: Partial<Record<TherapyParamKey, number>>
): { values: Record<TherapyParamKey, number>; warnings: string[] } {
  const values = {} as Record<TherapyParamKey, number>;
  const warnings: string[] = [];
  (Object.keys(input) as TherapyParamKey[]).forEach((k) => {
    const raw = input[k];
    if (raw == null) return;
    const clamped = clampParam(k, raw);
    values[k] = clamped;
    if (Math.abs(clamped - raw) > 1e-9) {
      const lim = THERAPY_LIMITS[k];
      warnings.push(`${lim.label} ${lim.min}–${lim.max} ${lim.unit} aralığına çekildi.`);
    }
  });
  return { values, warnings };
}
