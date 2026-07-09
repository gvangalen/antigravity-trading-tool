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

        <div className="pt-16 lg:grid lg:min-h-screen lg:grid-cols-[minmax(0,1fr)_400px]">
          {/* 📄 WORKSPACE CANVAS */}
          <main
            key={locale}
            className="min-h-[calc(100vh-4rem)] px-4 lg:px-10 h-auto overflow-visible"
          >
            {children}
          </main>

          {/* 🧠 FINN SHELL RAIL */}
          <aside className="border-t border-slate-200 bg-card dark:border-slate-800 dark:bg-[#0f172a] lg:sticky lg:top-16 lg:h-[calc(100vh-4rem)] lg:border-l lg:border-t-0">
            <AIAssistant isOpen={true} setIsOpen={() => {}} persistent />
          </aside>
        </div>
      </div>

      <ScrollToTop />
    </>
  );
}
