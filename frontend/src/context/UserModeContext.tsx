import React, { createContext, useContext, useState, ReactNode, useEffect } from 'react';

type UserMode = 'pet_owner' | 'veterinarian' | null;

interface UserModeContextType {
  userMode: UserMode;
  setUserMode: (mode: UserMode) => void;
  isExpert: boolean;
}

const UserModeContext = createContext<UserModeContextType | undefined>(undefined);

export const UserModeProvider = ({ children }: { children: ReactNode }) => {
  const [userMode, setUserModeState] = useState<UserMode>(null);

  // Basit bir localStorage entegrasyonu (Web için)
  useEffect(() => {
    try {
      const saved = localStorage.getItem('pemf_user_mode') as UserMode;
      if (saved) setUserModeState(saved);
    } catch (e) {
      console.warn("localStorage not available", e);
    }
  }, []);

  const setUserMode = (mode: UserMode) => {
    setUserModeState(mode);
    try {
      if (mode) {
        localStorage.setItem('pemf_user_mode', mode);
      } else {
        localStorage.removeItem('pemf_user_mode');
      }
    } catch (e) {
      console.warn("localStorage not available", e);
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
