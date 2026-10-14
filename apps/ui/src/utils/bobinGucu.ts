// Author: mertaygn, cglrgrkn
/**
 * Bobin gücü — TEK KAYNAK (TD5 · A-64, tezgâh Oturum 13).
 * =====================================================
 * ÖLÇÜLEN KUSUR: KPI "Anlık Güç" `COIL_R = 0.5` sabiti × SAHTE akım² gösteriyordu (PSU kapalıyken 6,3 W; 38 A'de ≈ 0,7 kW) —
 * takılı olmayan ACS712 girişleri gürültüyü amper diye basıyordu. A-64 kararı: akım güvenilir olana dek GİZLİ.
 * Direnç: tezgâh LCR ölçümü (sahip, 2026-10-14) R = 8,9 Ω, L = 21,4 mH — BOBİN BAŞINA varsayıldı ([SAHİBE] teyit).
 * ⚠️ Gösterge açılırsa (ANLIK_GUC_GORUNUR) yalnız `akimGuvenilmez` OLMAYAN ve `measuredFields`'te `currentA` olan bobin sayılmalı.
 */

/** Bobin başına direnç (Ω) — tezgâh LCR, 2026-10-14. */
export const BOBIN_DIRENCI_OHM = 8.9;

/** A-64: akım ölçümü güvenilir olana dek "Anlık Güç" GİZLİ (KPI kartı + bobin tablosundaki W sütunu). */
export const ANLIK_GUC_GORUNUR = false;

/** I²·R (W). */
export function bobinGucuW(akimA: number): number {
  return akimA * akimA * BOBIN_DIRENCI_OHM;
}
