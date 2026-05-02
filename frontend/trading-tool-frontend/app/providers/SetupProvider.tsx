"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { fetchLastSetup } from "@/lib/api/setups";
import { useAuth } from "@/components/auth/AuthProvider";

type SetupContextType = {
  activeSetup: any;
  setActiveSetup: (setup: any) => void;
  setupLoading: boolean;
  focusedBotId: number | null;
  setFocusedBotId: (id: number | null) => void;
};

const SetupContext = createContext<SetupContextType | null>(null);

export function SetupProvider({ children }: { children: React.ReactNode }) {
  const [activeSetup, setActiveSetup] = useState<any>(null);
  const [setupLoading, setSetupLoading] = useState(true);
  const [focusedBotId, setFocusedBotId] = useState<number | null>(null);

  const { user, sessionChecked } = useAuth() as any;

  useEffect(() => {
    async function loadActiveSetup() {
      // 🛑 Only fetch if we have a definitive session and a user
      if (!sessionChecked || !user) {
        if (sessionChecked) setSetupLoading(false);
        return;
      }

      try {
        const { fetchActiveSetup } = await import("@/lib/api/setups");
        const active = await fetchActiveSetup();
        if (active) {
          setActiveSetup(active);
        } else {
          const last = await fetchLastSetup();
          setActiveSetup(last || null);
        }
      } catch (err) {
        console.error("❌ SetupProvider initial setup error:", err);
      } finally {
        setSetupLoading(false);
      }
    }
    loadActiveSetup();
  }, [user, sessionChecked]);

  return (
    <SetupContext.Provider value={{ 
      activeSetup, 
      setActiveSetup, 
      setupLoading,
      focusedBotId,
      setFocusedBotId
    }}>
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
