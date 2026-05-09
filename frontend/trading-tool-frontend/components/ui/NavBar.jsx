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
  ShieldAlert,
  Users
} from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { BRANDING } from "@/lib/branding";
import AssetSwitcher from "./AssetSwitcher";
import { useAuth } from "@/components/auth/AuthGuard"; // useAuth is actually in AuthProvider usually but AuthGuard re-exports sometimes, or use direct
// Actually AuthGuard.jsx has useAuth. Let's check imports.
// Ah, AuthGuard.jsx uses useAuth from AuthProvider. Wait.
import { useAuth as useAuthHook } from "@/components/auth/AuthProvider"; 
import { useWatchlist } from "@/hooks/useWatchlist";
import { useAsset } from "@/app/providers/AssetProvider";
import { Star, AlertTriangle } from "lucide-react";
import { useModal } from "@/components/modal/ModalProvider";

export default function NavBar() {
  const { t } = useTranslation();
  const { user } = useAuthHook();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isAdmin = user?.role === 'admin';

  const NAV_LINKS = [
    { href: "/dashboard", label: t.nav.dashboard, icon: <Gauge size={18} /> },
    { href: "/market", label: t.nav.market, icon: <DollarSign size={18} /> },
    { href: "/macro", label: t.nav.macro, icon: <Globe size={18} /> },
    { href: "/technical", label: t.nav.technical, icon: <LineChart size={18} /> },
    { href: "/setup", label: t.nav.setups, icon: <Layers size={18} /> },
    { href: "/strategy", label: t.nav.strategies, icon: <BarChart3 size={18} /> },
    { href: "/bot", label: t.nav.bots, icon: <Bot size={18} /> },
    { href: "/report", label: t.nav.reports, icon: <FileText size={18} /> },
  ];

  const ADMIN_LINKS = [];

  // Voeg Admin links toe aan de aparte adminNav array voor visual separation
  if (isAdmin) {
    ADMIN_LINKS.push(
      { href: "/admin/ai", label: t.nav.admin_ai, icon: <ShieldCheck size={18} /> },
      { href: "/admin/users", label: t.nav.users, icon: <Users size={18} /> },
      { href: "/admin/logs", label: t.nav.logs, icon: <FileText size={18} /> }
    );
  }


  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  return (
    <>
      {/* 📱 MOBILE HEADER */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-[60] bg-card dark:bg-[#020617] border-b border-slate-200 dark:border-slate-800 transition-colors">
        <div className="h-16 px-6 flex items-center justify-between">
          <button onClick={() => setMobileOpen(true)} className="text-muted hover:text-blue-600 transition-colors">
            <Menu size={24} />
          </button>
          <Link href="/dashboard" className="flex items-center gap-3 group">
            <img src="/tradamind_icon_v2.png" alt="TM" className="h-10 w-10 object-contain rounded-xl group-hover:scale-105 transition-transform" />
            <div className="flex flex-col justify-center">
              <div className="text-sm font-black text-slate-900 dark:text-white tracking-tight leading-none mb-0.5 group-hover:text-blue-600 transition-colors">
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
          </Link>
          <div className="w-10" />
        </div>
      </div>

      {/* 💻 DESKTOP BAR */}
      <aside className="hidden lg:flex fixed top-0 left-0 bottom-0 w-64 bg-card dark:bg-[#020617] border-r border-slate-200 dark:border-slate-800 flex-col z-50 transition-colors">
        <SidebarInner pathname={pathname} onNavigate={() => {}} navLinks={NAV_LINKS} adminLinks={ADMIN_LINKS} />
      </aside>

      {/* 🛸 MOBILE DRAWER */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              key="overlay"
              className="lg:hidden fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-sm"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileOpen(false)}
            />
            <motion.aside
              key="drawer"
              className="lg:hidden fixed top-0 left-0 bottom-0 w-72 bg-card dark:bg-[#020617] z-[80] flex flex-col shadow-2xl transition-colors"
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
              <SidebarInner pathname={pathname} onNavigate={() => setMobileOpen(false)} navLinks={NAV_LINKS} adminLinks={ADMIN_LINKS} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}

function SidebarInner({ pathname, onNavigate, navLinks, adminLinks }) {
  const { t } = require("@/app/providers/I18nProvider").useTranslation();
  return (
    <div className="flex flex-col h-full bg-card dark:bg-[#020617] transition-colors">
      <Link 
        href="/dashboard"
        className="p-8 pb-4 hidden md:block select-none group cursor-pointer"
      >
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
      </Link>

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

        {/* ⭐ WATCHLIST SECTION */}
        <WatchlistSidebar onNavigate={onNavigate} pathname={pathname} />

        {/* ADMIN SECTION */}
        {adminLinks.length > 0 && (
          <div className="pt-6 mt-4 border-t border-slate-100 dark:border-slate-800">
            <p className="px-5 text-[9px] font-black uppercase tracking-[0.3em] text-slate-400 mb-3 italic">{t.nav.command_center}</p>
            {adminLinks.map((link) => {
              const isActive = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={onNavigate}
                  className={`
                    flex items-center gap-4 px-5 py-4 rounded-xl text-[11px] font-black uppercase tracking-widest transition-all group mb-1
                    ${isActive 
                      ? "bg-slate-900 text-white shadow-lg" 
                      : "text-muted hover:bg-slate-50 dark:hover:bg-slate-900/50 hover:text-slate-900 dark:hover:text-white"
                    }
                  `}
                >
                  <span className={`${isActive ? "text-white" : "text-secondary group-hover:text-slate-600 dark:group-hover:text-slate-200"}`}>
                    {link.icon}
                  </span>
                  {link.label}
                </Link>
              );
            })}
          </div>
        )}
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

function WatchlistSidebar({ onNavigate, pathname }) {
  const router = require("next/navigation").useRouter();
  const { watchlist, remove } = useWatchlist();
  const { selectedAsset: activeSymbol, setSelectedAsset } = useAsset();
  const { setActiveSetup, setFocusedBotId } = require("@/app/providers/SetupProvider").useActiveSetup();
  const { openConfirm, showSnackbar } = useModal();

  if (!watchlist || watchlist.length === 0) return null;

  return (
    <div className="pt-6 mt-4 border-t border-slate-100 dark:border-slate-800">
      <p className="px-5 text-[9px] font-black uppercase tracking-[0.3em] text-slate-400 mb-3 flex items-center gap-2">
        <Star size={10} className="text-amber-400 fill-amber-400" />
        Watchlist (Engine)
      </p>
      <div className="space-y-1">
        {watchlist.map((symbol) => {
          const isActive = activeSymbol === symbol;
          return (
            <div
              key={symbol}
              className={`
                group flex items-center justify-between px-5 py-3 rounded-xl transition-all cursor-pointer border border-transparent
                ${isActive 
                  ? "bg-blue-50 dark:bg-blue-950/30 text-blue-600 dark:text-blue-400 font-black border-blue-100/50 dark:border-blue-900/30 shadow-sm" 
                  : "text-muted hover:bg-slate-50 dark:hover:bg-slate-900/50 hover:text-slate-900 dark:hover:text-white"
                }
              `}
              onClick={() => {
                // Clear focus and update global state
                setActiveSetup(null);
                setFocusedBotId(null);
                setSelectedAsset(symbol);
                
                // Navigate with URL param to force update on the current page
                router.push(`${pathname}?symbol=${symbol}`);
                
                // 🔥 TRIGGER INITIALIZATION: Ensure data is fresh
                import("@/lib/api/market").then(({ initializeAsset }) => {
                  initializeAsset(symbol).catch(err => console.error("❌ Init error:", err));
                });

                onNavigate();
              }}
            >
              <div className="flex items-center gap-4">
                <div className={`w-1.5 h-1.5 rounded-full ${isActive ? "bg-blue-600 animate-pulse" : "bg-slate-300 dark:bg-slate-700"}`} />
                <span className="text-[11px] font-black uppercase tracking-widest">{symbol}</span>
              </div>
              
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  openConfirm({
                    title: "Asset verwijderen?",
                    description: `Weet je zeker dat je ${symbol} wilt verwijderen van je watchlist? De asset is dan niet meer zichtbaar in je actieve tracking engine.`,
                    tone: "danger",
                    confirmText: "Verwijder",
                    cancelText: "Annuleer",
                    icon: <AlertTriangle size={20} />,
                    onConfirm: async () => {
                      await remove(symbol);
                      showSnackbar(`${symbol} verwijderd van watchlist`, "success");
                    }
                  });
                }}
                className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-500 transition-all"
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
