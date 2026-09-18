// Author: mertaygn, cglrgrkn
/**
 * ShellLayoutContext — AppShell'in ÖLÇTÜĞÜ içerik genişliğini aşağı taşır.
 * [S2, 2026-09-04 responsive denetimi]
 *
 * NEDEN: `ResponsiveGrid` ve `isCompact` pencere genişliğinden karar veriyordu; kenar çubuğu
 * (240 px) ve içerik boşluğu düşülmediği için 768 px tablet dikeyde 352 px'lik alana 2 sütun
 * kuruluyordu (hücre ≈176 px). Ölçülen genişlik tek kaynaktan paylaşılır.
 *
 * Kabuk DIŞINDAKİ ekranlarda (Welcome, Auth, MobileUpdateGate) sağlayıcı yoktur → `null` döner ve
 * `useResponsive` pencere tabanlı tahmine düşer (mevcut davranış korunur).
 */
import { createContext, useContext } from "react";

const ShellLayoutContext = createContext<number | null>(null);

export const ShellLayoutProvider = ShellLayoutContext.Provider;

/** AppShell içerik alanının ölçülen genişliği (px) — kabuk dışında `null`. */
export function useShellLayout(): number | null {
  return useContext(ShellLayoutContext);
}
