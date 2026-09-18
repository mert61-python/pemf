// Author: mertaygn, cglrgrkn
/**
 * "DONANIM ŞU AN ÇALIŞIYOR MU" — tek kaynak (denetim bulgusu M4, 2026-08-23).
 *
 * ⚠️ `activeTreatment.isActive` TEK BAŞINA YETMEZ. Bobinler seans kaydı açılmadan da sürülebilir
 * (AI Pro akışı, bobin paneli, başka bir istemci) — o durumda `isActive` false kalır ama bobin
 * hastanın üzerinde ENERJİLİDİR. Depo bunu zaten biliyor ve başka yerlerde geniş ölçüyü
 * kullanıyor: `GlobalEmergencyStop` (bobin çalışırken görünür), `useTeardownGuard`,
 * `useApkGuncelleme` (`is_active || hardware_running`). Güncelleme bantlarının dar ölçüde kalması
 * bu deponun 1 numaralı hata deseniydi: aynı kural iki yerde, biri güncellenmiş öteki unutulmuş.
 *
 * KULLANIM: yönetimsel bir yüzeyi (bant, güncelleme önerisi, kurulum düğmesi) gizlemek için.
 * ⚠️ GÜVENLİK LİMİTİ DEĞİLDİR: acil durdurma yolunu hiçbir koşulda kapılamaz — tersine, acil
 * durdurma bu ölçü `true` iken GÖRÜNÜR olmalıdır.
 *
 * Bilinmiyorsa `false` döner: veri yokken bandı susturmak, kullanıcıyı bilgisiz bırakmak olurdu;
 * susturma kararı ancak POZİTİF bir "çalışıyor" sinyaliyle verilir.
 */
import { useLiveData } from "@/context/LiveDataContext";

export function useDonanimCalisiyor(): boolean {
  const { snapshot } = useLiveData();
  const seans = snapshot?.activeTreatment?.isActive === true;
  const bobin = (snapshot?.coils ?? []).some((c) => c?.running === true);
  return seans || bobin;
}
