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
 * NOT: "ai_history" (AI Analiz Geçmişi) Faz 3'te eklenecek — her üç profile de.
 */
export const ROUTE_ACCESS: Record<Exclude<UserMode, null>, RouteKey[]> = {
  pet_owner:    ["dashboard", "ai", "ai_history", "settings"],
  veterinarian: ["dashboard", "control", "patients", "sensors", "history", "kpi", "simulator", "ai", "ai_history", "settings"],
  researcher:   ["dashboard", "patients", "history", "ai", "ai_history", "settings"],
};

/** `mode` profili `route`'a erişebilir mi (null profil → hayır). */
export function canAccess(mode: UserMode, route: RouteKey): boolean {
  return mode != null && ROUTE_ACCESS[mode].includes(route);
}
