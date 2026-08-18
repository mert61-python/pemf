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
}

const AppNavContext = createContext<AppNavValue>({
  navigateTo: () => {},
  selectedPatient: null,
  setSelectedPatient: () => {},
});

export function AppNavProvider({
  navigateTo,
  children,
}: {
  navigateTo: (route: RouteKey) => void;
  children: React.ReactNode;
}) {
  const [selectedPatient, setSelectedPatient] = useState<SelectedPatient | null>(null);
  // DÜŞÜK fix: value'yu memoize et → her render'da yeni obje üretip tüm useAppNav tüketicilerini
  // gereksiz yere render etme (setSelectedPatient stabil setter, navigateTo stabil prop).
  const value = useMemo(() => ({ navigateTo, selectedPatient, setSelectedPatient }), [navigateTo, selectedPatient]);
  return (
    <AppNavContext.Provider value={value}>
      {children}
    </AppNavContext.Provider>
  );
}

export function useAppNav(): AppNavValue {
  return useContext(AppNavContext);
}
