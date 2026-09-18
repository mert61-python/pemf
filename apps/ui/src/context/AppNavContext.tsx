// Author: mertaygn, cglrgrkn
/**
 * AppNavContext — hafif uygulama-içi navigasyon + seçili hasta paylaşımı.
 * ====================================================================
 * PemfApp'te route state'i var ama ekranlar ona erişemiyordu (patient→session
 * stub'unun sebebi). Bu context: navigateTo(route) + seçili hasta'yı paylaşır.
 * Böylece Hastalar ekranından "Seans Başlat" → Kontrol ekranına gidip hastayı
 * seansta kullanabiliriz.
 */
import { createContext, useContext, useState, useMemo } from "react";
import type { RouteKey } from "@/types/domain";

export interface SelectedPatient {
  id?: string;
  name?: string;
  species?: string;
}

interface AppNavValue {
  navigateTo: (route: RouteKey) => void;
  selectedPatient: SelectedPatient | null;
  setSelectedPatient: (p: SelectedPatient | null) => void;
  /**
   * AI Hub'dan Kontrol ekranına taşınan AI Pro HEDEF MODELİ ön-seçimi (Faz 3, araştırma).
   *
   * Akış: araştırmacı AI Hub'da fantom/petri ANALİZİ yapar, "Bu hedefe AI Pro seansı" der;
   * Kontrol ekranı açılır ve model kartı ZATEN seçili gelir. TEK KULLANIMLIKtır: panel değeri
   * uygulayınca temizler, böylece sonraki ziyaretlerde kullanıcının seçimini EZMEZ.
   *
   * ⚠️ AI Hub burada YALNIZ niyeti taşır; hiçbir `/ai/pro/*` çağrısı yapmaz (otonom onay kapısı
   * yalnız Kontrol → AI Pro panelinde — bkz. aiHubOtonomOnayKapisi testi).
   */
  aiProModeli: string;
  setAiProModeli: (m: string) => void;
}

const AppNavContext = createContext<AppNavValue>({
  navigateTo: () => {},
  selectedPatient: null,
  setSelectedPatient: () => {},
  aiProModeli: "",
  setAiProModeli: () => {},
});

export function AppNavProvider({
  navigateTo,
  children,
}: {
  navigateTo: (route: RouteKey) => void;
  children: React.ReactNode;
}) {
  const [selectedPatient, setSelectedPatient] = useState<SelectedPatient | null>(null);
  const [aiProModeli, setAiProModeli] = useState("");
  // DÜŞÜK fix: value'yu memoize et → her render'da yeni obje üretip tüm useAppNav tüketicilerini
  // gereksiz yere render etme (setSelectedPatient stabil setter, navigateTo stabil prop).
  const value = useMemo(
    () => ({ navigateTo, selectedPatient, setSelectedPatient, aiProModeli, setAiProModeli }),
    [navigateTo, selectedPatient, aiProModeli],
  );
  return (
    <AppNavContext.Provider value={value}>
      {children}
    </AppNavContext.Provider>
  );
}

export function useAppNav(): AppNavValue {
  return useContext(AppNavContext);
}
