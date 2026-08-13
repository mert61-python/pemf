// Author: mertaygn, cglrgrkn
import { RouteKey } from "@/types/domain";
import { UserMode } from "@/context/UserModeContext";

/**
 * Profil → erişilebilir rotalar (TEK KAYNAK). Hem PemfApp (render gating) hem AppShell (nav filtre)
 * bunu kullanır → iki yerin sürüklenmesi (drift) engellenir = medikal-güvenlik: yanlış profile
 * cihaz/tedavi ekranı SIZMAZ. Değişiklik yalnız burada yapılır.
 *
 * - pet_owner   : basit AI teşhis + ana ekran (cihaz/klinik yok).
 * - veterinarian: tam klinik — kontrol/tedavi, sensör, hasta, geçmiş, KPI, simülatör, AI (kedi modelleri).
 * - researcher  : Araştırma Modu — AI (6 araştırma modeli) + hasta/örnek kaydı + geçmiş. CİHAZ YOK
 *                 (kontrol/sensör/KPI/simülatör YOK — bilinçli izolasyon).
 *
 * SAHİP KARARI 2026-08-06 — DEĞİŞTİ: yukarıdaki "researcher = CİHAZ YOK" izolasyonu BİLEREK
 * kaldırıldı. Araştırma profiline control (tedavi kontrolü), sensors, kpi (raporlar) ve simulator
 * eklendi → cihaz erişimi artık veteriner ile AYNI. Eski gerekçe tarihsel kayıt olarak bırakıldı
 * (neyin, ne zaman, neden değiştiğini görebilmek için).
 * SONUÇ (bilinerek kabul edildi): araştırma profili ControlScreen üzerinden AI Pro / AI-Auto
 * otonom tedavi sekmelerine de erişir. ACİL DURDUR (GlobalEmergencyStop) AppShell'de
 * profil-BAĞIMSIZ render edildiği için her rotada erişilebilir kalır — bu invaryant bozulmamalı.
 *
 * NOT: "ai_history" (AI Analiz Geçmişi) Faz 3'te eklenecek — her üç profile de.
 */
export const ROUTE_ACCESS: Record<Exclude<UserMode, null>, RouteKey[]> = {
  // SAHİP KARARI 2026-08-08: pet_owner'a "patients" EKLENDİ. AI analizi artık hasta seçimi
  // ZORUNLU (PatientGate) ve sonuçlar hasta geçmişine yazılıyor → ev sahibinin de kendi
  // hayvanlarını yönetebileceği bir ekrana ihtiyacı var. Cihaz/tedavi rotaları (control,
  // sensors, kpi, simulator) BİLİNÇLİ OLARAK KAPALI kalıyor — izolasyonun asıl amacı oydu.
  pet_owner:    ["dashboard", "patients", "ai", "ai_history", "settings"],
  veterinarian: ["dashboard", "control", "patients", "sensors", "history", "kpi", "simulator", "ai", "ai_history", "settings"],
  // 2026-08-06: vet ile AYNI sıra ve AYNI küme (bkz. yukarıdaki sahip kararı). pet_owner'ın
  // izolasyonu DEĞİŞMEDİ — karar yalnız araştırma profilini kapsıyor.
  researcher:   ["dashboard", "control", "patients", "sensors", "history", "kpi", "simulator", "ai", "ai_history", "settings"],
};

/** `mode` profili `route`'a erişebilir mi (null profil → hayır). */
export function canAccess(mode: UserMode, route: RouteKey): boolean {
  return mode != null && ROUTE_ACCESS[mode].includes(route);
}
