"use client";

import { useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";

import {
  LineChart,
  Layers,
  FileText,
  Bot,
  Wallet,
  Menu,
  X,
  ShieldCheck,
  ShieldAlert,
  Users,
  Activity
} from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useAsset } from "@/app/providers/AssetProvider";
import { BRANDING } from "@/lib/branding";
import AvatarMenu from "./AvatarMenu";
import { useAuth as useAuthHook } from "@/components/auth/AuthProvider"; 

export default function NavBar() {
  const { t } = useTranslation();
  const { user } = useAuthHook();
  const { selectedAsset } = useAsset();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [mobileOpen, setMobileOpen] = useState(false);
  const shellCopy = t?.ui?.shell || {};
  const appSlogan = shellCopy.appSlogan || BRANDING.APP_SLOGAN;
  const isAnalysisV3 = searchParams.get("variant") !== "legacy";
  const activeSymbol = String(
    searchParams.get("symbol") ||
      searchParams.get("asset") ||
      selectedAsset ||
      "BTC"
  )
    .trim()
    .toUpperCase();
  const analysisHref = isAnalysisV3
    ? `/asset?symbol=${encodeURIComponent(activeSymbol)}`
    : `/market?variant=legacy&symbol=${encodeURIComponent(activeSymbol)}`;

  const isAdmin = user?.role === 'admin';
  const NAV_ITEMS = [
    {
      href: "/portfolio",
      matchPathnames: ["/portfolio"],
      label: t?.nav?.portfolio,
      icon: <Wallet size={18} />,
    },
    {
      href: analysisHref,
      matchPathnames: ["/", "/asset", "/market", "/macro", "/technical"],
      label: t?.nav?.analysis,
      icon: <LineChart size={18} />,
    },
    {
      href: "/setup",
      matchPathnames: ["/setup", "/strategy"],
      label: t?.nav?.myPlan,
      icon: <Layers size={18} />,
    },
    {
      href: "/bot",
      matchPathnames: ["/bot"],
      label: t?.nav?.automation,
      icon: <Bot size={18} />,
    },
    {
      href: "/report",
      matchPathnames: ["/report"],
      label: t?.nav?.reflection,
      icon: <FileText size={18} />,
    },
  ];

  const ADMIN_LINKS = [];

  // Voeg Admin links toe aan de aparte adminNav array voor visual separation
  if (isAdmin) {
    ADMIN_LINKS.push(
      { href: "/admin/ai", label: t.nav.admin_ai, icon: <ShieldCheck size={18} /> },
      { href: "/admin/telemetry", label: t.nav.telemetry, icon: <Activity size={18} /> },
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
          <Link href={analysisHref} className="flex items-center gap-3 group">
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
                  {appSlogan}
                </div>
              </div>
            </div>
          </Link>
          <div className="flex items-center scale-90">
            <AvatarMenu />
          </div>
        </div>
      </div>

      {/* 💻 DESKTOP BAR */}
      <aside className="hidden lg:flex fixed top-0 left-0 bottom-0 w-64 bg-card dark:bg-[#020617] border-r border-slate-200 dark:border-slate-800 flex-col z-50 transition-colors">
        <SidebarInner
          pathname={pathname}
          onNavigate={() => {}}
          navItems={NAV_ITEMS}
          adminLinks={ADMIN_LINKS}
          analysisHref={analysisHref}
        />
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
                      {BRANDING.APP_NAME}
                    </div>
                    <div className="flex items-center gap-1.5 text-blue-600 dark:text-blue-500">
                      <div className="animate-pulse-soft">
                        <ShieldCheck size={12} strokeWidth={2.5} />
                      </div>
                      <div className="text-[8px] font-black uppercase tracking-[0.2em] opacity-90">
                        {appSlogan}
                      </div>
                    </div>
                  </div>
                </div>
                <button onClick={() => setMobileOpen(false)} className="text-secondary hover:text-slate-900 dark:hover:text-slate-100 transition-colors">
                  <X size={20} />
                </button>
              </div>
              <SidebarInner
                pathname={pathname}
                onNavigate={() => setMobileOpen(false)}
                navItems={NAV_ITEMS}
                adminLinks={ADMIN_LINKS}
                analysisHref={analysisHref}
              />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}

function SidebarInner({ pathname, onNavigate, navItems, adminLinks, analysisHref }) {
  const { t } = useTranslation();
  const shellCopy = t?.ui?.shell || {};
  const missionStatement = shellCopy.missionStatement || BRANDING.MISSION_STATEMENT;
  const appSlogan = shellCopy.appSlogan || BRANDING.APP_SLOGAN;
  return (
    <div className="flex flex-col h-full bg-card dark:bg-[#020617] transition-colors">
      <Link 
        href={analysisHref}
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
                {appSlogan}
              </div>
            </div>
          </div>
        </div>
      </Link>

      {/* LINKS */}
      <nav className="flex-1 px-4 space-y-2 overflow-y-auto no-scrollbar py-4">
        {navItems.map((link) => {
          const isActive = (link.matchPathnames || []).includes(pathname);
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
           {missionStatement.map((line, i) => (
             <span key={i}>{line}<br/></span>
           ))}
        </div>
      </div>
    </div>
  );
}
