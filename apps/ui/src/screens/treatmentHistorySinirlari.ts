// Author: mertaygn, cglrgrkn
/**
 * Seans geçmişi dışa aktarımının (Tümünü / görünen PDF ve CSV) ÜST SINIRLARI — `session_ids` sorgusu uzayınca URL 414 olmasın;
 * aşımda kullanıcı uyarılır ve ilk N kayıt gider (TreatmentHistoryScreen).
 *
 * KP-5 · 8: sınırlar ekran dosyasından bu küçük modüle taşındı — testler küçük sınırla sahteler (CSV sınırını 1001 kart çizerek
 * sınamak jest süre sınırını aşıyordu). Değerler AYNEN.
 */
export const PDF_MAX = 200;
export const CSV_MAX = 1000;
