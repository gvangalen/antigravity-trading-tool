"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { fetchLastSetup } from "@/lib/api/setups";

type SetupContextType = {
  activeSetup: any;
  setActiveSetup: (setup: any) => void;
  setupLoading: boolean;
};

const SetupContext = createContext<SetupContextType | null>(null);

export function SetupProvider({ children }: { children: React.ReactNode }) {
  const [activeSetup, setActiveSetup] = useState<any>(null);
  const [setupLoading, setSetupLoading] = useState(true);

  useEffect(() => {
    async function loadActiveSetup() {
      try {
        const setup = await fetchLastSetup();
        setActiveSetup(setup || null);
      } catch (err) {
        console.error("❌ SetupProvider initial setup error:", err);
      } finally {
        setSetupLoading(false);
      }
    }
    loadActiveSetup();
  }, []);

  return (
    <SetupContext.Provider value={{ activeSetup, setActiveSetup, setupLoading }}>
      {children}
    </SetupContext.Provider>
  );
}

export function useActiveSetup() {
  const context = useContext(SetupContext);
  if (!context) {
    throw new Error("useActiveSetup must be used within a SetupProvider");
  }
  return context;
}
