// Author: mertaygn, cglrgrkn
/**
 * Türkçe-doğru arama normalizasyonu — TEK KAYNAK.
 *
 * ⚠️ DENETİM 2026-08-17. Üç arama filtresi de `toLowerCase()` kullanıyordu ve depoda
 * `toLocaleLowerCase` HİÇ geçmiyordu (`PatientScreen`, `TreatmentHistoryScreen`, `PatientGate`).
 * Ölçüldü:
 *     "İpek".toLowerCase() === "i̇pek"   → 'i' + U+0307 (COMBINING DOT ABOVE), 5 kod noktası
 *     "i̇pek".includes("ipek")           → false
 *     'IŞIK'.toLowerCase() === "işik"  ≠  'Işık'.toLowerCase() === "işık"
 *
 * Sonuç: adı `İ` içeren (İpek, İnci) ya da büyük `I` içeren (Işık, Ilgaz) bir hasta, doğal Türkçe
 * yazımla ARANDIĞINDA bulunamıyordu. En ağır etki `TreatmentHistoryScreen`: süzme yalnız
 * YÜKLENMİŞ sayfalar üzerinde çalıştığı için hekim "bu hastanın geçmişi yok" sonucuna varıyor ve
 * PDF/CSV dışa aktarımı `filteredSessions` üzerinden gittiği için **boş/eksik rapor** üretiyordu.
 *
 * Backend'de telafi YOK: `servers/patient_router.py`'de arama ucu yok, istemci `/patients`ın
 * tamamını çekip yerelde süzüyor (Python `.lower()` de aynı U+0307'yi üretir).
 *
 * ⚠️ KAPSAM YALNIZ İ/I KURALIDIR — aksan DÜZLEŞTİRİLMEZ. "Şirin" ile "Sirin"i birleştirmek bir
 * hasta-kimliği ekranında yanlış kayda bakmak demektir; ş/ç/ğ/ü/ö ayrımı korunur (karşıt-kanıt
 * testleri bunu kilitler).
 *
 * ⚠️ TEK KAYNAK OLMASI ŞART: bu bulgunun kök nedeni aynı kuralın üç yerde kopyalanmasıydı —
 * kopya, kuralın bir yerde düzeltilip diğerinde kalması demektir. Yapısal bir test üç yüzeyin de
 * bu modülü kullandığını denetler.
 *
 * Kilit: `__tests__/aramaNormalize.test.ts`.
 */

/** Karşılaştırma için metni Türkçe kurallarıyla küçült ve birleşik işaretleri toparla. */
export function aramaNormalize(metin: string | null | undefined): string {
  if (!metin) return "";
  // `toLocaleLowerCase("tr")`: İ→i, I→ı (Unicode varsayılanının aksine).
  // `normalize("NFC")`: kalan birleşik işaretleri (U+0307 gibi) tek kod noktasına toparlar —
  // farklı kaynaklardan (klavye, kopyala-yapıştır, DB) gelen metinler aynı biçimde karşılaşsın.
  return metin.toLocaleLowerCase("tr").normalize("NFC");
}

/** `metin` içinde `sorgu` geçiyor mu? (Türkçe-doğru, boş sorgu HER ŞEYLE eşleşir.) */
export function aramaEslesir(
  metin: string | null | undefined,
  sorgu: string | null | undefined,
): boolean {
  const q = aramaNormalize(sorgu).trim();
  if (!q) return true; // boş sorgu = süzme yok (mevcut davranış korunur)
  return aramaNormalize(metin).includes(q);
}
