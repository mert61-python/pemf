// Author: mertaygn, cglrgrkn
/**
 * D1.67 · A-47 madde 4 · Y6 — bir bobin alanının SAYISI gösterilebilir mi (1-D inceleme i2-F-3).
 *
 * Backend `measuredFields`'i yalnız TAZE ölçülen alanlardan yazar (D1.67): sensör susunca alan listeden düşer ama sayı
 * `_live_state`te DONMUŞ kalır; hiç sensörü olmayan alan 0.0 durur. Bu yüzden sayı göstermek için ölçüt `measuredFields`
 * üyeliğidir — değerin sıfırdan büyük olması DEĞİL. Panel (`CoilParameterPanel`) ve Sensör ekranı aynı ölçütü kullanır.
 *
 * `measuredFields` hiç YOKSA (alanı göndermeyen eski backend / aparat) karar çağıranın eski ölçütüne bırakılır (`true`).
 */
/**
 * TD2 (tezgâh Oturum 13 · K6): MLX90393 kazanç ayarı geri okunarak doğrulanamadıysa backend alanı YAZMAZ ve bobine
 * `alanDogrulanamadi: true` koyar (eski firmware'in işaretsiz `B=`'si ~5× olabilir). Üç ekran AYNI metni gösterir.
 */
export const ALAN_DOGRULANAMADI_METNI = "Alan sensörü doğrulanamadı — ölçülen değer gösterilmiyor";

/**
 * TD5 (tezgâh Oturum 13 · K4): ADC tavanına dayanmış ya da ACS712 aralığı dışı akım GÜVENİLMEZ — backend yazmaz, bobine
 * `akimGuvenilmez: true` koyar (takılı olmayan girişte 10–115 A "ölçülüyordu"). Ekranlar AYNI metni gösterir.
 */
export const AKIM_OLCUMU_YOK_METNI = "Akım ölçümü yok";

/**
 * CH4 · Y154 (sahip 2026-10-15): AKIM SENSÖRÜ (ACS712) TÜMDEN KAPALI — akım HİÇ GÖSTERİLMEZ (satır / sütun çizilmez). Tek bayrak
 * backend'de (`apps/backend/utils/akim_olcumu.py`, `PEMF_AKIM_OLCUMU`, varsayılan KAPALI) → anlık görüntünün `akimOlcumu` alanı.
 * Akım YALNIZ `true` iken çizilir; alanı göndermeyen eski backend → gizli (sahte akım gösterme riski yerine eksik satır).
 */
export function akimOlcumuAcik(snapshot: { akimOlcumu?: boolean } | null | undefined): boolean {
  return snapshot?.akimOlcumu === true;
}

export function alanGosterilebilir(coil: { measuredFields?: string[] } | null | undefined, alan: string): boolean {
  const mf = coil?.measuredFields;
  return Array.isArray(mf) ? mf.includes(alan) : true;
}
