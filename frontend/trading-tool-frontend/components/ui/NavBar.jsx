"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";

import {
  Gauge,
  DollarSign,
  Globe,
  LineChart,
  Layers,
  BarChart3,
  FileText,
  Bot,
  Menu,
  X,
  ShieldCheck,
} from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { BRANDING } from "@/lib/branding";

export default function NavBar() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const NAV_LINKS = [
    { href: "/", label: t.nav.dashboard, icon: <Gauge size={18} /> },
    { href: "/market", label: t.nav.market, icon: <DollarSign size={18} /> },
    { href: "/macro", label: t.nav.macro, icon: <Globe size={18} /> },
    { href: "/technical", label: t.nav.technical, icon: <LineChart size={18} /> },
    { href: "/setup", label: t.nav.setups, icon: <Layers size={18} /> },
    { href: "/strategy", label: t.nav.strategies, icon: <BarChart3 size={18} /> },
    { href: "/bot", label: t.nav.bots, icon: <Bot size={18} /> },
    { href: "/report", label: t.nav.reports, icon: <FileText size={18} /> },
  ];

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  return (
    <>
      {/* 📱 MOBILE HEADER */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-[60] bg-card dark:bg-[#020617] border-b border-slate-200 dark:border-slate-800 transition-colors">
        <div className="h-16 px-6 flex items-center justify-between">
          <button onClick={() => setMobileOpen(true)} className="text-muted hover:text-blue-600 transition-colors">
            <Menu size={24} />
          </button>
          <div className="flex items-center gap-3">
            <img src="/tradamind_icon_v2.png" alt="TM" className="h-10 w-10 object-contain rounded-xl" />
            <div className="flex flex-col justify-center">
              <div className="text-sm font-black text-slate-900 dark:text-white tracking-tight leading-none mb-0.5">
                {BRANDING.APP_NAME}
              </div>
              <div className="flex items-center gap-1 text-blue-600 dark:text-blue-500">
                <div className="animate-pulse-soft">
                  <ShieldCheck size={10} strokeWidth={2.5} />
                </div>
                <div className="text-[7.5px] font-black uppercase tracking-[0.15em]">
                  {BRANDING.APP_SLOGAN}
                </div>
              </div>
            </div>
          </div>
          <div className="w-10" />
        </div>
      </div>

      {/* 💻 DESKTOP BAR */}
      <aside className="hidden md:flex fixed top-0 left-0 bottom-0 w-64 bg-card dark:bg-[#020617] border-r border-slate-200 dark:border-slate-800 flex-col z-50 transition-colors">
        <SidebarInner pathname={pathname} onNavigate={() => {}} navLinks={NAV_LINKS} />
      </aside>

      {/* 🛸 MOBILE DRAWER */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              key="overlay"
              className="md:hidden inset-0 z-[70] bg-slate-900/40 backdrop-blur-sm"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileOpen(false)}
            />
            <motion.aside
              key="drawer"
              className="md:hidden fixed top-0 left-0 bottom-0 w-72 bg-card dark:bg-[#020617] z-[80] flex flex-col shadow-2xl transition-colors"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
            >
              <div className="p-6 flex items-center justify-between border-b border-slate-100 dark:border-slate-800">
                <div className="flex items-center gap-3">
                  <img src="/tradamind_icon_v2.png" alt="TM" className="h-12 w-12 object-contain rounded-xl" />
                  <div className="flex flex-col justify-center">
                    <div className="text-lg font-black text-slate-900 dark:text-white tracking-tight leading-none mb-1">
                      Tradamind
                    </div>
                    <div className="flex items-center gap-1.5 text-blue-600 dark:text-blue-500">
                      <div className="animate-pulse-soft">
                        <ShieldCheck size={12} strokeWidth={2.5} />
                      </div>
                      <div className="text-[8px] font-black uppercase tracking-[0.2em] opacity-90">
                        Professional
                      </div>
                    </div>
                  </div>
                </div>
                <button onClick={() => setMobileOpen(false)} className="text-secondary hover:text-slate-900 dark:hover:text-slate-100 transition-colors">
                  <X size={20} />
                </button>
              </div>
              <SidebarInner pathname={pathname} onNavigate={() => setMobileOpen(false)} navLinks={NAV_LINKS} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}

function SidebarInner({ pathname, onNavigate, navLinks }) {
  return (
    <div className="flex flex-col h-full bg-card dark:bg-[#020617] transition-colors">
      {/* BRANDING */}
      <div className="p-8 pb-4 hidden md:block select-none group cursor-default">
        <div className="flex items-center gap-4 transition-transform duration-500 group-hover:scale-[1.03]">
          <div className="relative">
            <img 
              src="/tradamind_icon_v2.png" 
              alt="TM" 
              className="h-16 w-16 object-contain rounded-2xl transition-all duration-500" 
            />
          </div>
          <div className="flex flex-col justify-center">
            <div className="text-xl font-black text-slate-900 dark:text-white tracking-tight leading-none mb-1.5 transition-colors duration-300 group-hover:text-blue-600 dark:group-hover:text-blue-400">
              {BRANDING.APP_NAME}
            </div>
            <div className="flex items-center gap-1.5 text-blue-600 dark:text-blue-500">
              <div className="animate-pulse-soft">
                <ShieldCheck size={14} strokeWidth={2.5} />
              </div>
              <div className="text-[9px] font-black uppercase tracking-[0.25em] opacity-90">
                {BRANDING.APP_SLOGAN}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* LINKS */}
      <nav className="flex-1 px-4 space-y-2 overflow-y-auto no-scrollbar py-4">
        {navLinks.map((link) => {
          const isActive = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              onClick={onNavigate}
              className={`
                flex items-center gap-4 px-5 py-4 rounded-xl text-[11px] font-black uppercase tracking-widest transition-all group
                ${isActive 
                  ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20" 
                  : "text-muted hover:bg-slate-50 dark:hover:bg-slate-900/50 hover:text-slate-900 dark:hover:text-white"
                }
              `}
            >
              <span className={`${isActive ? "text-white" : "text-secondary group-hover:text-slate-600 dark:group-hover:text-slate-200"}`}>
                {link.icon}
              </span>
              {link.label}
              {isActive && (
                <div className="ml-auto w-1.5 h-6 bg-white/40 rounded-full animate-pulse" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* FOOTER - MISSION STATEMENT */}
      <div className="p-8 border-t border-slate-100 dark:border-slate-800 flex flex-col items-start gap-4">
        <div className="text-[7.5px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-[0.3em] leading-relaxed opacity-80">
           {BRANDING.MISSION_STATEMENT.map((line, i) => (
             <span key={i}>{line}<br/></span>
           ))}
        </div>
      </div>
    </div>
  );
}
