// Author: mertaygn, cglrgrkn
import React, { createContext, useContext, useState, useCallback, useMemo, ReactNode } from 'react';

export type UserMode = 'pet_owner' | 'veterinarian' | 'researcher' | null;

interface UserModeContextType {
  userMode: UserMode;
  setUserMode: (mode: UserMode) => void;
  isExpert: boolean;       // Veteriner Hekim (klinik + seans + kedi modelleri)
  // Araştırma Modu (klinik kanser araştırma analizleri). 2026-08-06 sahip kararı: bu profil ARTIK
  // cihaz ekranlarına da erişir (kontrol/sensör/rapor/simülasyon) — eski "cihaz YOK" notu geçersiz.
  // Rota erişiminin TEK KAYNAĞI config/access.ts'tir; bu bayrak yalnız AI Hub bölüşümü/etiket içindir.
  isResearcher: boolean;
  hasAiHub: boolean;       // modüler AI Hub erişimi (vet ‖ researcher); pet_owner basit ekran görür
}

const UserModeContext = createContext<UserModeContextType | undefined>(undefined);

export const UserModeProvider = ({ children }: { children: ReactNode }) => {
  // Profil seçimi BİLİNÇLİ olarak KALICI DEĞİL: her açılışta userMode=null ile başlar →
  // MainRouter WelcomeScreen'i (profil seçimi) hem mobilde hem webte HER SEFERİNDE gösterir.
  // (Eskiden AsyncStorage 'pemf_user_mode'a kaydedilip açılışta restore ediliyordu → kaldırıldı.)
  const [userMode, setUserModeState] = useState<UserMode>(null);

  // Yalnız oturum-içi state; hiçbir kalıcı depolamaya (AsyncStorage/localStorage) YAZILMAZ.
  // DÜŞÜK fix: setUserMode'u useCallback + value'yu useMemo ile sabitle → gereksiz tüketici-render önle.
  const setUserMode = useCallback((mode: UserMode) => setUserModeState(mode), []);

  const isExpert = userMode === 'veterinarian';
  const isResearcher = userMode === 'researcher';
  const hasAiHub = isExpert || isResearcher;

  const value = useMemo(
    () => ({ userMode, setUserMode, isExpert, isResearcher, hasAiHub }),
    [userMode, setUserMode, isExpert, isResearcher, hasAiHub],
  );

  return (
    <UserModeContext.Provider value={value}>
      {children}
    </UserModeContext.Provider>
  );
};

export const useUserMode = () => {
  const context = useContext(UserModeContext);
  if (context === undefined) {
    throw new Error('useUserMode must be used within a UserModeProvider');
  }
  return context;
};
