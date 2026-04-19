"use client";

import NavBar from "@/components/ui/NavBar";
import TopBar from "@/components/ui/TopBar";
import AuthGuard from "@/components/auth/AuthGuard";
import AppProviders from "@/app/providers/AppProviders";
import AIAssistant from "@/components/ui/AIAssistant";
import AIFloatingButton from "@/components/ui/AIFloatingButton";
import ScrollToTop from "@/components/ui/ScrollToTop";
import { useState } from "react";

export default function ProtectedLayout({ children }) {
  const [isAIOpen, setIsAIOpen] = useState(false);
  return (
    <AppProviders>
      <AuthGuard>

        {/* 🧱 SIDEBAR (NAVBAR handles its own mobile/desktop state) */}
        <NavBar />

        {/* 🕋 MAIN CONTENT SHELL */}
        <div 
          className="md:pl-64 min-h-screen bg-white transition-all duration-200"
          style={{ 
            paddingRight: isAIOpen ? (typeof window !== 'undefined' && window.innerWidth < 768 ? "0px" : "400px") : "0px",
            paddingLeft: typeof window !== 'undefined' && window.innerWidth < 768 ? "0px" : ""
          }}
        >
          
          {/* 🛰️ TOPBAR (HIDDEN ON MOBILE to favor NavBar mobile header) */}
          <div className="top-bar hidden md:block">
            <TopBar />
          </div>

          {/* 📄 PAGE CONTENT */}
          <main className="pt-16 md:pt-16 min-h-screen px-4 md:px-10">
            {children}
          </main>
          
        </div>

        <AIAssistant isOpen={isAIOpen} setIsOpen={setIsAIOpen} />
        <AIFloatingButton isOpen={isAIOpen} onClick={() => setIsAIOpen(true)} />
        <ScrollToTop />

      </AuthGuard>
    </AppProviders>
  );
}
