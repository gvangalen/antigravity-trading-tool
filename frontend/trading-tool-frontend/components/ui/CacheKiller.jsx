"use client";

import { useEffect } from "react";

export default function CacheKiller() {
  const CURRENT_BUILD = "v2190";

  useEffect(() => {
    if (typeof window !== "undefined") {
      const lastBuild = localStorage.getItem("tradamind_build_id");
      
      if (lastBuild !== CURRENT_BUILD) {
        console.log(`[CacheKiller] New build detected: ${CURRENT_BUILD}. Forcing refresh...`);
        localStorage.setItem("tradamind_build_id", CURRENT_BUILD);
        
        // Force clear cache and reload
        if (window.location.search.indexOf("v=") === -1) {
          window.location.href = window.location.pathname + "?v=" + Date.now();
        }
      }
    }
  }, []);

  return (
    <div className="fixed bottom-4 left-4 z-[9999] pointer-events-none opacity-20 text-[8px] font-mono text-slate-400">
      BUILD: {CURRENT_BUILD}
    </div>
  );
}
