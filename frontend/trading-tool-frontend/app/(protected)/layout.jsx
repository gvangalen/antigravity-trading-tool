"use client";

import NavBar from "@/components/ui/NavBar";
import TopBar from "@/components/ui/TopBar";
import AIAssistant from "@/components/ui/AIAssistant";
import ScrollToTop from "@/components/ui/ScrollToTop";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function ProtectedLayout({ children }) {
  const { locale } = useTranslation();
  return (
    <>
      {/* 🧱 SIDEBAR (NAVBAR handles its own mobile/desktop state) */}
      <NavBar />

      {/* 🕋 MAIN CONTENT SHELL */}
      <div className="lg:pl-64 min-h-screen bg-white transition-all duration-200 h-auto">
        {/* 🛰️ TOPBAR (HIDDEN ON MOBILE to favor NavBar mobile header) */}
        <div className="top-bar hidden lg:block">
          <TopBar />
        </div>

        <div className="flex min-h-screen flex-col xl:flex-row">
          <div className="xl:hidden max-h-[70dvh] overflow-hidden border-b border-slate-100 dark:border-slate-800 bg-card dark:bg-[#0f172a]">
            <AIAssistant isOpen={true} setIsOpen={() => {}} persistent />
          </div>

          {/* 📄 PAGE CONTENT */}
          <main
            key={locale}
            className="pt-16 lg:pt-16 min-h-screen px-4 lg:px-10 h-auto overflow-visible flex-1"
          >
            {children}
          </main>

          <div className="hidden xl:block xl:w-[400px] xl:shrink-0 xl:sticky xl:top-0 xl:self-start">
            <AIAssistant isOpen={true} setIsOpen={() => {}} persistent />
          </div>
        </div>
      </div>

      <ScrollToTop />
    </>
  );
}
