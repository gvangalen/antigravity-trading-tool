"use client";

import { useEffect } from "react";

export default function CacheKiller() {
  const CURRENT_BUILD = "d1d4507";

  useEffect(() => {
    if (typeof window !== "undefined") {
      const lastBuild = localStorage.getItem("tradamind_build_id");
      
      if (lastBuild !== CURRENT_BUILD) {
        localStorage.setItem("tradamind_build_id", CURRENT_BUILD);
        
        // Force clear cache and reload
        if (window.location.search.indexOf("v=") === -1) {
          window.location.href = window.location.pathname + "?v=" + Date.now();
        }
      }
    }
  }, []);

  return null;
}
