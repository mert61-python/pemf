import React, { createContext, useContext, useState, ReactNode } from 'react';

interface ExpertModeContextType {
  isExpertMode: boolean;
  toggleExpertMode: () => void;
}

const ExpertModeContext = createContext<ExpertModeContextType | undefined>(undefined);

export const ExpertModeProvider = ({ children }: { children: ReactNode }) => {
  const [isExpertMode, setIsExpertMode] = useState(false);

  const toggleExpertMode = () => {
    setIsExpertMode((prev) => !prev);
  };

  return (
    <ExpertModeContext.Provider value={{ isExpertMode, toggleExpertMode }}>
      {children}
    </ExpertModeContext.Provider>
  );
};

export const useExpertMode = () => {
  const context = useContext(ExpertModeContext);
  if (context === undefined) {
    throw new Error('useExpertMode must be used within an ExpertModeProvider');
  }
  return context;
};
