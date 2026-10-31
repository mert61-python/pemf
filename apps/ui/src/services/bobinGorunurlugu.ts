// Author: mertaygn
/**
 * HANGİ BOBİNLER ÇİZİLİR — tek kaynak.
 *
 * ============================================================================
 * ⚠️ SAHA ARIZASI 2026-09-11: GÖRÜNMEYEN BOBİN DURDURULAMAZ
 * ============================================================================
 * Kontrol ekranı bobinleri `id <= 7` ile süzüyordu: slot 8 (ESP/MQTT) HİÇ çizilmiyordu.
 * ESP ağa bağlanınca slot 8 canlı durumda `running` olabiliyor, "Durdur" onu hedefliyor
 * (`runningIds`), ACK gelmeyince de şu uyarı çıkıyordu:
 *
 *     "Durdurma onaylanamadı — bobinler HÂLÂ ÇALIŞIYOR olabilir. ACİL DURDUR'a basın."
 *
 * ...ve operatörün o bobine dokunacak **hiçbir kontrolü yoktu**, çünkü ekranda yoktu.
 *
 * Eski karar da haklıydı ve KORUNUR: cihaz yokken kalıcı "Offline" bir kart göstermek,
 * olmayan bir bobini varmış gibi sunar. İkisini birden karşılayan kural aşağıdadır.
 *
 * ⚠️ `running` şartı BİLEREK ayrı: bağlantı düşse bile enerjili kalmış bir bobin
 * çizilmeye DEVAM eder. "Bağlı değil" ile "kapalı" aynı şey değildir — hasta üzerinde
 * enerjili kalmış bir bobini ekrandan silmek, arızayı gizlemektir.
 */

/** Bu modülün ihtiyacı olan asgari bobin şekli (tam `CoilStatus` gerekmez). */
export interface GorunurlukGirdisi {
  id: number;
  connected?: boolean;
  running?: boolean;
}

/** STM sürücüsüne bağlı, FİZİKSEL olarak var olan bobinler — daima çizilir. */
export const STM_BOBIN_SAYISI = 7;

/** Bobin STM sürücüsünde mi (1..{@link STM_BOBIN_SAYISI})? D5.42: bobin sınırı sabitleri (`id <= 7`, `STM_COIL_MAX_ID = 5`) yerine BU. */
export function stmBobiniMi(id: number): boolean {
  return id >= 1 && id <= STM_BOBIN_SAYISI;
}

/** Tüm slot kimlikleri: STM 1..{@link STM_BOBIN_SAYISI} + ESP slotu (ESP kodu silinmez; dönerse aynı slot — Y7 / A-04). */
export function tumSlotIdleri(): number[] {
  return Array.from({ length: STM_BOBIN_SAYISI + 1 }, (_, i) => i + 1);
}

/**
 * Çizilecek bobinleri süzer.
 *
 * · bobin 1..{@link STM_BOBIN_SAYISI} → DAİMA (STM'de fiziksel olarak varlar; çevrimdışı
 *   olsalar bile "Offline" göstermek doğrudur, çünkü gerçekten oradalar)
 * · slot 8+ (ESP/MQTT) → yalnız ORTAYA ÇIKINCA: `connected` **ya da** `running`
 */
export function gorunurBobinler<T extends GorunurlukGirdisi>(liste: readonly T[]): T[] {
  return liste.filter((c) => c.id <= STM_BOBIN_SAYISI || Boolean(c.connected) || Boolean(c.running));
}

/**
 * Y230 (BE 3 · sahip): ESP alt sistemi AÇIK mı — ESP / MQTT yüzeylerinin (Ana Ekran rozeti, Sistem Durumu satırları, ESP metinleri) TEK
 * kaynağı backend'in `esp_etkin()`i (`snapshot.espEtkin`). Alan yoksa (eski backend) KAPALI sayılır: ESP sahada sökülü (2026-09-11).
 * ⚠️ Çalışır görünen bir ESP yuvası bundan BAĞIMSIZ çizilmeye devam eder (`gorunurBobinler`) — durdurma görünürlüğü kapılanmaz.
 */
export function espEtkinMi(snapshot?: { espEtkin?: boolean } | null): boolean {
  return snapshot?.espEtkin === true;
}

/** Ekranda ESP slotu da var mı (başlık "1–8" mi "1–7" mi yazacak). */
export function espSlotuGorunur(liste: readonly GorunurlukGirdisi[]): boolean {
  return gorunurBobinler(liste).some((c) => c.id > STM_BOBIN_SAYISI);
}
