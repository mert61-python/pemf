/**
 * AppNavContext — hafif uygulama-içi navigasyon + seçili hasta paylaşımı.
 * ====================================================================
 * PemfApp'te route state'i var ama ekranlar ona erişemiyordu (patient→session
 * stub'unun sebebi). Bu context: navigateTo(route) + seçili hasta'yı paylaşır.
 * Böylece Hastalar ekranından "Seans Başlat" → Kontrol ekranına gidip hastayı
 * seansta kullanabiliriz.
 */
import { createContext, useContext, useState } from "react";
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
  return (
    <AppNavContext.Provider value={{ navigateTo, selectedPatient, setSelectedPatient }}>
      {children}
    </AppNavContext.Provider>
  );
}

export function useAppNav(): AppNavValue {
  return useContext(AppNavContext);
}
