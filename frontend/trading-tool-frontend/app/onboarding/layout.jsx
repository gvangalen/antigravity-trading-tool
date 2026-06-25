"use client";

import { useState } from "react";
import AIAssistant from "@/components/ui/AIAssistant";
import AIFloatingButton from "@/components/ui/AIFloatingButton";
import { useTranslation } from "@/app/providers/I18nProvider";
import Link from "next/link";
import { Rocket } from "lucide-react";

export default function OnboardingLayout({ children }) {
  const [isAIOpen, setIsAIOpen] = useState(false);
  const { t } = useTranslation();

  return (
    <>
        {/* 🧱 ONBOARDING FOCUS SHELL */}
        <div 
          className="min-h-screen bg-[#020617] text-slate-100 transition-all duration-300 relative overflow-hidden"
          style={{ 
            paddingRight: isAIOpen ? (typeof window !== "undefined" && window.innerWidth < 1024 ? "0px" : "400px") : "0px"
          }}
        >
          {/* ✨ BACKGROUND TREATMENT (CSS GRID) */}
          <div 
            className="absolute inset-0 pointer-events-none opacity-20"
            style={{
              backgroundImage: `radial-gradient(circle at 2px 2px, rgba(255,255,255,0.05) 1px, transparent 0)`,
              backgroundSize: '40px 40px'
            }}
          />
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-4xl h-96 bg-blue-600/10 blur-[120px] rounded-full pointer-events-none" />

          {/* 🛰️ ONBOARDING HEADER */}
          <header className="fixed top-0 left-0 right-0 z-50 h-16 border-b border-slate-800 bg-[#020617]/80 backdrop-blur-md flex items-center justify-between px-8">
            <div className="flex items-center gap-4">
              <Link href="/onboarding" className="flex items-center gap-3 group transition-all">
                <div className="p-2 bg-blue-600 rounded-xl shadow-lg shadow-blue-600/20 group-hover:scale-110 transition-transform">
                  <Rocket className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h1 className="text-sm font-black uppercase tracking-[0.2em] leading-none mb-1">
                    {t?.onboardingShell?.title}
                  </h1>
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest leading-none">
                    {t?.onboardingShell?.status}
                  </span>
                </div>
              </Link>
            </div>

            <div className="flex items-center gap-6">
              <div className="hidden md:flex items-center gap-2 px-4 py-1.5 bg-slate-900 border border-slate-800 rounded-full">
                <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{t?.onboardingShell?.assistantOnline}</span>
              </div>
            </div>
          </header>

          {/* 📄 MISSION CONTENT */}
          <main className="pt-24 pb-12 min-h-screen relative z-10 px-6 max-w-6xl mx-auto">
            {children}
          </main>
          
        </div>

        {/* 🧠 AI PILOT */}
        <AIAssistant isOpen={isAIOpen} setIsOpen={setIsAIOpen} />
        {!isAIOpen && (
          <AIFloatingButton isOpen={isAIOpen} onClick={() => setIsAIOpen(true)} />
        )}
    </>
  );
}
