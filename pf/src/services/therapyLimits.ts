// Author: mertaygn, cglrgrkn
/**
 * therapyLimits — PEMF tedavi parametreleri için arayüz sınırları (tek kaynak).
 * ============================================================================
 * SAHİP KARARI (2026-09-08): FREKANS ve DUTY arayüzde SINIRLANMAZ. Eski 1–100 Hz / 1–50 %
 * klempi ("Parametre güvenliği … aralığına çekildi") tezgâhta istenen değerin verilmesini
 * engelliyordu. Tek sınır artık CİHAZ FIRMWARE'İDİR ve geçersiz değer sessizce çekilmez,
 * cihaz REDDEDER (STM: STM_NACK; ESP8266: "freq/duty out of range" NACK → panelde
 * "Cihaz komutu REDDETTİ"). Firmware aralıkları: STM FREQ_MIN 1 Hz … FREQ_MAX (main.c),
 * duty firmware klempi (bipolar yarım-periyot / unipolar tam-periyot); ESP8266 1–1000 Hz,
 * duty 1–99 % (duty<1 = STOP). Backend safety-limit'i de sahip kararıyla YOK — GERİ EKLEME.
 *
 * Kalan sınırlar (kullanıcı istemedi, dokunulmadı): faz 0–360°, yoğunluk 0.1–20 mT,
 * süre 0–120 dk (0 = süresiz). Stop komutlarında clamp UYGULANMAZ.
 */
export const THERAPY_LIMITS = {
  phase: { min: 0, max: 360, label: "Faz", unit: "°" },
  intensity: { min: 0.1, max: 20, label: "Yoğunluk", unit: "mT" },
  duration: { min: 0, max: 120, label: "Süre", unit: "dk" }, // 0 = süresiz
} as const;

/** Arayüzde SINIRSIZ parametreler (sahip kararı 2026-09-08) — değer olduğu gibi cihaza gider. */
export const SINIRSIZ_PARAMLAR = ["freq", "duty"] as const;
type SinirsizKey = (typeof SINIRSIZ_PARAMLAR)[number];

export type TherapyParamKey = keyof typeof THERAPY_LIMITS | SinirsizKey;

function sinirsizMi(key: TherapyParamKey): key is SinirsizKey {
  return (SINIRSIZ_PARAMLAR as readonly string[]).includes(key);
}

/** Tek bir değeri arayüz aralığına çeker (NaN → min). freq/duty: olduğu gibi döner. */
export function clampParam(key: TherapyParamKey, value: number): number {
  if (sinirsizMi(key)) return value;
  const lim = THERAPY_LIMITS[key];
  if (isNaN(value)) return lim.min;
  return Math.min(lim.max, Math.max(lim.min, value));
}

/**
 * Verilen parametreleri arayüz aralığına çeker; sınır-dışı olanların kullanıcı mesajını döndürür.
 * freq/duty HİÇ çekilmez ve uyarı ÜRETMEZ (cihaz sınırı geçerlidir).
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
    if (!sinirsizMi(k) && Math.abs(clamped - raw) > 1e-9) {
      const lim = THERAPY_LIMITS[k];
      warnings.push(`${lim.label} ${lim.min}–${lim.max} ${lim.unit} aralığına çekildi.`);
    }
  });
  return { values, warnings };
}
