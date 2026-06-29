"use client";

import NavBar from "@/components/ui/NavBar";
import TopBar from "@/components/ui/TopBar";
import AIAssistant from "@/components/ui/AIAssistant";
import AIFloatingButton from "@/components/ui/AIFloatingButton";
import ScrollToTop from "@/components/ui/ScrollToTop";
import { useState } from "react";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function ProtectedLayout({ children }) {
  const [isAIOpen, setIsAIOpen] = useState(false);
  const { locale } = useTranslation();
  return (
    <>
      {/* 🧱 SIDEBAR (NAVBAR handles its own mobile/desktop state) */}
      <NavBar />

      {/* 🕋 MAIN CONTENT SHELL */}
      <div 
        className="lg:pl-64 min-h-screen bg-white transition-all duration-200 h-auto"
        style={{ 
          paddingRight: isAIOpen ? (typeof window !== 'undefined' && window.innerWidth < 1024 ? "0px" : "400px") : "0px",
        }}
      >
        
        {/* 🛰️ TOPBAR (HIDDEN ON MOBILE to favor NavBar mobile header) */}
        <div className="top-bar hidden lg:block">
          <TopBar />
        </div>

        {/* 📄 PAGE CONTENT */}
        <main
          key={locale}
          className="pt-16 lg:pt-16 min-h-screen px-4 lg:px-10 h-auto overflow-visible"
        >
          {children}
        </main>
        
      </div>

      <AIAssistant isOpen={isAIOpen} setIsOpen={setIsAIOpen} />
      <AIFloatingButton isOpen={isAIOpen} onClick={() => setIsAIOpen(true)} />
      <ScrollToTop />
    </>
  );
}
