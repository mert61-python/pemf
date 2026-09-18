// Author: mertaygn, cglrgrkn
/**
 * HASTA DÜZENLEME PAYLOAD'I — LOST-UPDATE SAVUNMASI (denetim 2026-08-30).
 *
 * ⚠️ NEDEN: PatientScreen düzenlemede TÜM formu gönderiyordu (`{...normalized, id}`). İki cihaz
 * aynı hastayı aynı anda açıp FARKLI alanları değiştirirse, birinin formundaki BAYAT değer
 * diğerinin yeni değerini eziyordu (lost update):
 *     A: name "Boncuk"→"Pamuk" gönderir {name:Pamuk, owner:Ali}
 *     B: owner "Ali"→"Veli"   gönderir {name:Boncuk, owner:Veli}  (B'nin formunda name bayat!)
 *     Sonuç: name=Boncuk (A'nın değişikliği KAYBOLDU)
 * Backend `update_patient` field-merge yapar (gönderilmeyen alanı korur) ama frontend her alanı
 * "değişmiş" gönderdiği için koruma devreye girmiyordu.
 *
 * ÇÖZÜM: yalnız DEĞİŞEN alanları gönder. Backend gönderilmeyeni korur → iki cihaz çakışmaz.
 * - Karşılaştırma HAM `form` üzerinden (baseline ham yüklenir); gönderim `normalized` (nokta-ondalık).
 * - Boşaltma da bir değişikliktir (baseline "X" → form "") → boş gönderilir → backend temizler.
 * - `id` her zaman payload'da (hedef kaydı belirler), asla "değişen alan" sayılmaz.
 */
export function duzenlemePayloadu(
  form: Record<string, string>,
  baseline: Record<string, string>,
  normalized: Record<string, string>,
  editingId: string,
): Record<string, string> {
  const payload: Record<string, string> = { id: editingId };
  for (const k of Object.keys(form)) {
    if (k === "id") continue;
    if (form[k] !== (baseline[k] ?? "")) {
      payload[k] = normalized[k];
    }
  }
  return payload;
}
