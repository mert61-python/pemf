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
export function alanGosterilebilir(coil: { measuredFields?: string[] } | null | undefined, alan: string): boolean {
  const mf = coil?.measuredFields;
  return Array.isArray(mf) ? mf.includes(alan) : true;
}
