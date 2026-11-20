// Author: mertaygn, cglrgrkn
/**
 * Y306 (sahip 19-11, madde 6): TEK MLX alan sensörü (MLX90393) var ve kabinde GEZDİRİLİYOR — firmware onu kartın kanal 6'sına yazar
 * (`PEMF_SENSOR_BOBIN_IDLERI`; firmware DEĞİŞMEZ). Değer bir BOBİNİN değil KABİNİN sensörüdür → her yerde "Kabin sensörü (MLX)" adıyla,
 * bobin satırlarından AYRI. Kanal → sensör eşlemesi TEK sabit (backend eşi `apps/backend/utils/kabin_sensoru.MLX_KANALI`). Eski seans
 * kayıtları da bu adla gösterilir (veri göçü YOK, yalnız gösterim). Değerin ölçülüp ölçülmediği yine `measuredFields`ten (Y6 / D1.67).
 */
export const KABIN_SENSORU_KANALI = 6;

/** Bu telemetri kanalı / kayıt `coil_id`'si kabin sensörü mü (metin ya da sayı). */
export function kabinSensoruKanaliMi(kanal: unknown): boolean {
  return kanal !== null && kanal !== undefined && kanal !== "" && Number(kanal) === KABIN_SENSORU_KANALI;
}

/** Kabin sensörü kanalının kartında alan (`magneticMt`) BOBİNİN ölçümü değildir → bobin kartı / paneli için ölçülen alanlardan çıkarılır.
 *  Başka kanallar AYNEN. Ölçüm listesi hiç gelmediyse (eski backend) kabin kanalında alan dışındakiler "ölçülüyor" sayılır. */
export function bobinOlcumAlanlari(kanal: unknown, measuredFields: string[] | undefined): string[] | undefined {
  if (!kabinSensoruKanaliMi(kanal)) return measuredFields;
  const liste = Array.isArray(measuredFields) ? measuredFields : ["objectTemp", "ambientTemp", "currentA"];
  return liste.filter((f) => f !== "magneticMt");
}

/** Bobin kartı verisi: kabin sensörü kanalında alan ve alan doğrulama bayrağı karttan çıkar (değer `KabinSensoruKarti`nda). */
export function bobinKartiVerisi<T extends { id?: unknown; measuredFields?: string[]; alanDogrulanamadi?: boolean }>(coil: T): T {
  if (!kabinSensoruKanaliMi(coil?.id)) return coil;
  return { ...coil, measuredFields: bobinOlcumAlanlari(coil.id, coil.measuredFields), alanDogrulanamadi: false };
}
