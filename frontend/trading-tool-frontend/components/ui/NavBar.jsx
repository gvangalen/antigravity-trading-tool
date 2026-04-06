"use client";

import { useEffect, useMemo, useState } from "react";
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
  Settings,
  Sun,
  Bot,
  Menu,
  X,
  ShieldCheck,
} from "lucide-react";

const NAV_LINKS = [
  { href: "/", label: "Scores", icon: <Gauge size={18} /> },
  { href: "/market", label: "Markt", icon: <DollarSign size={18} /> },
  { href: "/macro", label: "Macro", icon: <Globe size={18} /> },
  { href: "/technical", label: "Techniek", icon: <LineChart size={18} /> },
  { href: "/setup", label: "Setups", icon: <Layers size={18} /> },
  { href: "/strategy", label: "Strategieën", icon: <BarChart3 size={18} /> },
  { href: "/bot", label: "Bots", icon: <Bot size={18} /> },
  { href: "/report", label: "Rapporten", icon: <FileText size={18} /> },
];

export default function NavBar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  return (
    <>
      {/* 📱 MOBILE HEADER */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-[60] bg-white border-b border-slate-200">
        <div className="h-16 px-6 flex items-center justify-between">
          <button onClick={() => setMobileOpen(true)} className="text-slate-500 hover:text-blue-600 transition-colors">
            <Menu size={24} />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-black text-xl">A</div>
            <div className="font-bold text-slate-900 tracking-tight">Antigravity</div>
          </div>
          <div className="w-10" />
        </div>
      </div>

      {/* 💻 DESKTOP BAR */}
      <aside className="hidden md:flex fixed top-0 left-0 bottom-0 w-64 bg-white border-r border-slate-200 flex-col z-50">
        <SidebarInner pathname={pathname} onNavigate={() => {}} />
      </aside>

      {/* 🛸 MOBILE DRAWER */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              key="overlay"
              className="md:hidden fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-sm"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileOpen(false)}
            />
            <motion.aside
              key="drawer"
              className="md:hidden fixed top-0 left-0 bottom-0 w-72 bg-white z-[80] flex flex-col shadow-2xl"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
            >
              <div className="p-6 flex items-center justify-between border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-black text-xl">A</div>
                  <div className="font-bold text-slate-900 tracking-tight">Antigravity</div>
                </div>
                <button onClick={() => setMobileOpen(false)} className="text-slate-400 hover:text-slate-900 transition-colors">
                  <X size={20} />
                </button>
              </div>
              <SidebarInner pathname={pathname} onNavigate={() => setMobileOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}

function SidebarInner({ pathname, onNavigate }) {
  return (
    <div className="flex flex-col h-full">
      {/* BRANDING */}
      <div className="p-8 hidden md:block">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white font-black text-2xl shadow-lg shadow-blue-600/20">
            A
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 tracking-tight leading-none">Antigravity</h1>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1.5 flex items-center gap-1">
              <ShieldCheck size={10} className="text-blue-500" /> Professional
            </p>
          </div>
        </div>
      </div>

      {/* LINKS */}
      <nav className="flex-1 px-4 space-y-2">
        {NAV_LINKS.map((link) => {
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
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
                }
              `}
            >
              <span className={`${isActive ? "text-white" : "text-slate-400 group-hover:text-slate-600"}`}>
                {link.icon}
              </span>
              {link.label}
              {isActive && (
                <div className="ml-auto w-1.5 h-6 bg-white/40 rounded-full" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* FOOTER */}
      <div className="p-6 border-t border-slate-100 space-y-2">
        <button className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-semibold text-slate-500 hover:bg-slate-50 hover:text-slate-900 transition-all">
          <Settings size={16} />
          Instellingen
        </button>
        <button className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-semibold text-slate-500 hover:bg-slate-50 hover:text-slate-900 transition-all">
          <Sun size={16} />
          Thema
        </button>
      </div>
    </div>
  );
}
