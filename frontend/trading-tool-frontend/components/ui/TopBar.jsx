"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";
import AvatarMenu from "@/components/ui/AvatarMenu";
import { Search, ChevronRight } from "lucide-react";
import { useAuth } from "@/components/auth/AuthProvider";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function TopBar() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const [query, setQuery] = useState("");
  const { user } = useAuth();

  /* ======== Dynamic Greeting (Localized) ======== */
  const hour = new Date().getHours();
  const greetingKey =
    hour < 12
      ? t.greetings.morning
      : hour < 18
      ? t.greetings.afternoon
      : t.greetings.evening;

  const firstName = user?.first_name || "";
  const greetingText = firstName ? `${greetingKey}, ${firstName}` : greetingKey;

  /* ======== Breadcrumb Label (Localized) ======== */
  const labels = {
    "/": t.nav.dashboard,
    "/dashboard": t.nav.dashboard,
    "/market": t.nav.market,
    "/macro": t.nav.macro,
    "/technical": t.nav.technical,
    "/setup": t.nav.setups,
    "/strategy": t.nav.strategies,
    "/bot": t.nav.bots,
    "/report": t.nav.reports,
  };

  const currentLabel = labels[pathname] || "Tradamind";

  return (
    <header className="h-full w-full flex items-center justify-between px-10 bg-card dark:bg-[#020617] transition-colors border-b-2 border-slate-100 dark:border-slate-800">
      
      {/* LEFT — Breadcrumb (Deep V2 Pro Style) */}
        <div className="flex items-center gap-4">
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            {/* Branding removed for a cleaner look */}
          </div>
          <h2 className="text-xl font-bold text-foreground dark:text-slate-100 tracking-tight leading-none mt-1.5">
            {currentLabel}
          </h2>
        </div>
      </div>

      {/* CENTER — Greeting (High Clarity) */}
      <div className="hidden lg:flex flex-1 justify-center">
        <p className="text-sm font-extrabold text-foreground dark:text-slate-200 tracking-tight transition-colors">
          {greetingText}
        </p>
      </div>

        {/* RIGHT — Search + Avatar */}
        <div className="flex items-center gap-6">

        {/* Minimal High-Depth Search */}
        <div className="hidden md:flex items-center gap-3 px-4 py-2 bg-[var(--color-border-subtle)] dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl focus-within:ring-4 focus-within:ring-blue-600/5 transition-all shadow-inner">
          <Search size={14} className="text-secondary" />
          <input
            className="bg-transparent outline-none w-48 text-xs font-bold text-foreground dark:text-slate-100 placeholder-slate-400"
            placeholder={t.common.search}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {/* 👤 AVATAR MENU (Restored) */}
        <div className="pl-6 border-l-2 border-slate-100 dark:border-slate-800 flex items-center">
          <div className="p-0.5 rounded-full border-2 border-slate-100 dark:border-slate-800 shadow-sm hover:border-blue-600/20 transition-all">
            <AvatarMenu />
          </div>
        </div>

      </div>
    </header>
  );
}
