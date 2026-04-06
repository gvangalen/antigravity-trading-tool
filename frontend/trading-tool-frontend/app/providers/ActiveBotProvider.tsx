"use client";

import { createContext, useContext, useState } from "react";

interface ActiveBotContextType {
  activeBot: any;
  setActiveBot: (bot: any) => void;
}

const ActiveBotContext = createContext<ActiveBotContextType | null>(null);

export function ActiveBotProvider({ children }: { children: React.ReactNode }) {
  const [activeBot, setActiveBot] = useState<any>(null);

  return (
    <ActiveBotContext.Provider value={{ activeBot, setActiveBot }}>
      {children}
    </ActiveBotContext.Provider>
  );
}

export function useActiveBot() {
  const context = useContext(ActiveBotContext);
  if (!context) {
    throw new Error("useActiveBot must be used inside ActiveBotProvider");
  }
  return context;
}
