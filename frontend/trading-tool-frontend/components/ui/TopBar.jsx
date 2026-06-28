"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import AvatarMenu from "@/components/ui/AvatarMenu";
import { useAuth } from "@/components/auth/AuthProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import AssetSearchBar from "./AssetSearchBar";

export default function TopBar() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const { user } = useAuth();

  /* ======== Dynamic Greeting (Localized & Safe) ======== */
  const [greetingText, setGreetingText] = useState("");

  useEffect(() => {
    const hour = new Date().getHours();
    const greetingKey =
      hour < 12
        ? t.greetings.morning
        : hour < 18
        ? t.greetings.afternoon
        : t.greetings.evening;

    const firstName = user?.first_name || "";
    setGreetingText(firstName ? `${greetingKey}, ${firstName}` : greetingKey);
  }, [t, user]);

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
    "/profile": localeAware(t?.traderProfile?.profilePage?.pageTitle, t?.traderProfile?.profilePage?.title),
    "/admin/ai": t.nav.admin_ai,
    "/admin/telemetry": t.nav.telemetry,
    "/admin/users": t.nav.users,
    "/admin/logs": t.nav.logs,
  };

  const currentLabel = labels[pathname] || t?.ui?.topBar?.defaultTitle;

  return (
    <header className="h-full w-full flex items-center justify-between px-10 bg-card dark:bg-[#020617] transition-colors border-b-2 border-slate-100 dark:border-slate-800">
      
      {/* LEFT — Breadcrumb & Greeting */}
        <div className="flex items-center gap-8">
        <div className="flex flex-col">
          <h2 className="text-xl font-bold text-foreground dark:text-slate-100 tracking-tight leading-none">
            {currentLabel}
          </h2>
          <p className="text-[10px] font-extrabold text-secondary dark:text-slate-500 tracking-widest uppercase mt-1">
            {greetingText}
          </p>
        </div>
      </div>

      {/* CENTER — Global Asset Search (Primary Control) */}
      <div className="hidden lg:flex flex-1 justify-center max-w-xl">
        <AssetSearchBar />
      </div>

      {/* RIGHT — Avatar & Profile */}
      <div className="flex items-center gap-6">

        {/* Avatar Menu (contains Notification setting) */}

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

function localeAware(value, fallback) {
  return value || fallback;
}
