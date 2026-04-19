"use client";

import { useAuth } from "@/components/auth/AuthProvider";
import { User, Mail, Shield, Zap, ArrowUpRight, Brain, LogOut, Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useModal } from "@/components/modal/ModalProvider";

export default function ProfilePage() {
  const { user, logout } = useAuth();
  const { showSnackbar } = useModal();
  const router = useRouter();
  const [loadingLogout, setLoadingLogout] = useState(false);

  if (!user) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  const handleLogout = async () => {
    setLoadingLogout(true);
    await logout();
    showSnackbar("You have been safely logged out ✔", "success");
    router.push("/login");
  };

  const fullName = `${user.first_name || ""} ${user.last_name || ""}`.trim() || user.email;
  const requestsUsed = user.ai_requests_used_day || 0;
  const requestsLimit = user.ai_requests_limit_day || 25;
  const usagePct = Math.min((requestsUsed / requestsLimit) * 100, 100);

  return (
    <div className="min-h-screen bg-background text-foreground transition-colors duration-300 p-8 pt-12">
      <div className="max-w-4xl mx-auto space-y-8 animate-fade-in">
        {/* HEADER */}
        <div className="border-l-4 border-blue-600 pl-8 mb-12">
          <div className="text-[11px] font-black text-blue-600 uppercase tracking-[0.3em] mb-2 opacity-80">
            Account Laboratory
          </div>
          <h1 className="text-5xl font-black text-foreground tracking-tight leading-none">
            User Profile
          </h1>
        </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        
        {/* 1. USER INFO BLOK */}
        <div className="bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10 flex flex-col justify-between transition-all hover:border-blue-600/20 group">
          <div className="space-y-8">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-2xl bg-blue-600 text-white flex items-center justify-center font-black text-xl shadow-lg shadow-blue-900/20">
                {fullName.charAt(0).toUpperCase()}
              </div>
              <div>
                <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1">Trader Identity</div>
                <div className="text-2xl font-black text-foreground tracking-tight">{fullName}</div>
              </div>
            </div>

            <div className="space-y-6">
              <div className="flex items-center gap-4">
                <div className="p-2.5 rounded-xl bg-[var(--color-border-subtle)] text-secondary">
                  <Mail size={18} />
                </div>
                <div>
                  <div className="text-[9px] font-black text-dim uppercase tracking-widest mb-0.5">Contact Port</div>
                  <div className="text-sm font-bold text-foreground">{user.email}</div>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <div className="p-2.5 rounded-xl bg-[var(--color-border-subtle)] text-secondary">
                  <Shield size={18} />
                </div>
                <div>
                  <div className="text-[9px] font-black text-dim uppercase tracking-widest mb-0.5">Authorization Level</div>
                  <div className="inline-flex items-center px-2 py-0.5 rounded-md bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 text-[10px] font-black uppercase tracking-tighter border border-blue-200 dark:border-blue-800">
                    {user.role || 'PRO'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 2. SUBSCRIPTION BLOK */}
        <div className="bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10 flex flex-col justify-between transition-all hover:border-blue-600/20 group relative overflow-hidden">
          {/* Subtle Accent Background */}
          <div className="absolute top-0 right-0 w-32 h-32 bg-blue-600/5 blur-3xl rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-1000" />
          
          <div className="relative z-10 space-y-12">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1">Service Tier</div>
                <div className="text-3xl font-black text-foreground tracking-tighter uppercase italic">
                  {user.ai_plan || 'Basis'} Plan
                </div>
              </div>
              <div className="px-3 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 text-[9px] font-black uppercase tracking-widest flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Active
              </div>
            </div>

            <div className="py-6 border-y border-[var(--color-border-subtle)]">
               <p className="text-[11px] font-bold text-dim leading-relaxed uppercase tracking-widest">
                 Professional access enabled. All intelligence nodes are fully synchronized with your account.
               </p>
            </div>

            <button className="w-full bg-foreground text-card hover:bg-slate-800 py-4 rounded-2xl text-[11px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 group/btn active:scale-95 shadow-xl">
              Upgrade to Pro Level
              <ArrowUpRight size={14} className="group-hover/btn:translate-x-0.5 group-hover/btn:-translate-y-0.5 transition-transform" />
            </button>
          </div>
        </div>

      </div>

      {/* 3. ACTIONS */}
      <div className="bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10">
        <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-6">Strategic Terminal Actions</div>
        
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Link 
            href="/admin/ai" 
            className="flex items-center gap-4 p-5 rounded-2xl bg-[var(--color-border-subtle)] border-2 border-transparent hover:border-blue-600/30 transition-all group"
          >
            <div className="p-3 rounded-xl bg-card text-blue-600 border border-[var(--color-border)]">
              <Brain size={20} />
            </div>
            <div>
              <div className="text-sm font-black text-foreground tracking-tight group-hover:text-blue-600 transition-colors">AI Settings Interface</div>
              <div className="text-[10px] font-bold text-dim uppercase tracking-widest">Adjust intelligence parameters</div>
            </div>
          </Link>

          <button 
            onClick={handleLogout}
            disabled={loadingLogout}
            className="flex items-center gap-4 p-5 rounded-2xl bg-[var(--color-border-subtle)] border-2 border-transparent hover:border-rose-600/30 transition-all group text-left"
          >
            <div className="p-3 rounded-xl bg-card text-rose-600 border border-[var(--color-border)]">
              {loadingLogout ? <Loader2 size={20} className="animate-spin" /> : <LogOut size={20} />}
            </div>
            <div>
              <div className="text-sm font-black text-foreground tracking-tight group-hover:text-rose-600 transition-colors">Sign Out Securely</div>
              <div className="text-[10px] font-bold text-dim uppercase tracking-widest">Terminate current session</div>
            </div>
          </button>
        </div>
      </div>
      </div>
    </div>
  );
}
