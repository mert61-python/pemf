import React, { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import AsyncStorage from "@react-native-async-storage/async-storage";

type UserMode = 'pet_owner' | 'veterinarian' | null;

interface UserModeContextType {
  userMode: UserMode;
  setUserMode: (mode: UserMode) => void;
  isExpert: boolean;
}

const UserModeContext = createContext<UserModeContextType | undefined>(undefined);

export const UserModeProvider = ({ children }: { children: ReactNode }) => {
  const [userMode, setUserModeState] = useState<UserMode>(null);

  // AsyncStorage: hem native (APK'de KALICI) hem web. Eskiden localStorage idi → APK'de kalmıyordu.
  useEffect(() => {
    AsyncStorage.getItem('pemf_user_mode')
      .then((saved) => {
        if (saved === 'pet_owner' || saved === 'veterinarian') setUserModeState(saved);
      })
      .catch(() => {});
  }, []);

  const setUserMode = (mode: UserMode) => {
    setUserModeState(mode);
    if (mode) {
      AsyncStorage.setItem('pemf_user_mode', mode).catch(() => {});
    } else {
      AsyncStorage.removeItem('pemf_user_mode').catch(() => {});
    }
  };

  const isExpert = userMode === 'veterinarian';

  return (
    <UserModeContext.Provider value={{ userMode, setUserMode, isExpert }}>
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
