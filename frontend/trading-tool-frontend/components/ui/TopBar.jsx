"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";
import AvatarMenu from "@/components/ui/AvatarMenu";
import { Search, ChevronRight } from "lucide-react";
import { useAuth } from "@/components/auth/AuthProvider";

export default function TopBar() {
  const pathname = usePathname();
  const [query, setQuery] = useState("");
  const { user } = useAuth();

  /* ======== Dynamische begroeting ======== */
  const hour = new Date().getHours();
  const greeting =
    hour < 12
      ? "Goedemorgen"
      : hour < 18
      ? "Goedemiddag"
      : "Goedenavond";

  const firstName = user?.first_name || "";
  const greetingText = firstName ? `${greeting}, ${firstName}` : greeting;

  /* ======== Breadcrumb Label ======== */
  const labels = {
    "/": "Scores",
    "/market": "Markt",
    "/macro": "Macro",
    "/technical": "Techniek",
    "/setup": "Setups",
    "/strategy": "Strategieën",
    "/bot": "Bots",
    "/report": "Rapporten",
  };

  const currentLabel = labels[pathname] || "Antigravity";

  return (
    <header className="h-full w-full flex items-center justify-between px-10">
      
      {/* LEFT — Breadcrumb (Deep V2 Pro Style) */}
      <div className="flex items-center gap-2 text-slate-400">
        <span className="text-[11px] font-black uppercase tracking-[0.2em] opacity-60">Antigravity</span>
        <ChevronRight size={12} className="opacity-40" />
        <span className="text-[11px] font-black uppercase tracking-[0.2em] text-blue-600">{currentLabel}</span>
      </div>

      {/* CENTER — Greeting (High Clarity) */}
      <div className="hidden lg:flex flex-1 justify-center">
        <p className="text-sm font-extrabold text-slate-800 tracking-tight">
          {greetingText}
        </p>
      </div>

      {/* RIGHT — Search + Avatar */}
      <div className="flex items-center gap-6">
        
        {/* Minimal High-Depth Search */}
        <div className="hidden md:flex items-center gap-3 px-4 py-2 bg-slate-50 border border-slate-200 rounded-xl focus-within:ring-4 focus-within:ring-blue-600/5 transition-all shadow-inner">
          <Search size={14} className="text-slate-400" />
          <input
            className="bg-transparent outline-none w-48 text-xs font-bold text-slate-900 placeholder-slate-400"
            placeholder="Zoeken..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {/* 👤 AVATAR MENU (Restored) */}
        <div className="pl-6 border-l-2 border-slate-100 flex items-center">
          <div className="p-0.5 rounded-full border-2 border-slate-100 shadow-sm hover:border-blue-600/20 transition-all">
            <AvatarMenu />
          </div>
        </div>

      </div>
    </header>
  );
}
