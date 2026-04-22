"use client";

import Link from "next/link";
import Image from "next/image";
import { ArrowRight, Check, ShieldCheck, Zap, Brain, LineChart, Globe, DollarSign, ArrowUpRight, LayoutDashboard } from "lucide-react";
import { useAuth } from "@/components/auth/AuthProvider";

export default function LandingPage() {
  const { isAuthenticated, loading } = useAuth();

  return (
    <div className="min-h-screen bg-background text-foreground transition-colors duration-300 font-sans selection:bg-blue-600/30">
      
      {/* 1. HEADER */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-background/80 backdrop-blur-md border-b border-[var(--color-border-subtle)]">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <Link href={isAuthenticated ? "/dashboard" : "/"} className="flex items-center gap-3 group">
            <img src="/tradamind_icon_v2.png" alt="TM" className="h-12 w-12 object-contain rounded-xl group-hover:scale-105 transition-transform" />
            <div className="flex flex-col justify-center">
              <div className="text-lg font-black text-slate-900 dark:text-white tracking-tight leading-none mb-1 group-hover:text-blue-600 transition-colors">
                Tradamind
              </div>
              <div className="flex items-center gap-1.5 text-blue-600 dark:text-blue-500">
                <div className="animate-pulse-soft">
                  <ShieldCheck size={12} strokeWidth={2.5} className="text-blue-600" />
                </div>
                <div className="text-[8px] font-black uppercase tracking-[0.2em]">
                  Professional
                </div>
              </div>
            </div>
          </Link>
            {!isAuthenticated ? (
              <Link 
                href="/login" 
                className="px-6 py-2.5 rounded-xl border-2 border-[var(--color-border)] hover:border-blue-600/30 text-[11px] font-black uppercase tracking-widest transition-all"
              >
                Login
              </Link>
            ) : (
              <Link 
                href="/dashboard" 
                className="px-6 py-2.5 rounded-xl bg-blue-600 text-white text-[11px] font-black uppercase tracking-widest transition-all shadow-lg shadow-blue-600/20"
              >
                Dashboard
              </Link>
            )}
        </div>
      </header>

      <main className="pt-20">
        
        {/* 2. HERO SECTION */}
        <section className="relative px-6 py-24 sm:py-32 overflow-hidden">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-7xl h-full pointer-events-none overflow-hidden">
            <div className="absolute top-1/4 -right-1/4 w-[500px] h-[500px] bg-blue-600/5 blur-[120px] rounded-full" />
            <div className="absolute bottom-1/4 -left-1/4 w-[500px] h-[500px] bg-blue-600/5 blur-[120px] rounded-full" />
          </div>

          <div className="max-w-4xl mx-auto text-center relative z-10">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 text-[10px] font-black uppercase tracking-[0.2em] mb-8 border border-blue-200 dark:border-blue-800/50">
              <Zap size={12} className="fill-current" /> V1 Launch Protocol
            </div>
            <h1 className="text-6xl sm:text-8xl font-black text-foreground tracking-tighter leading-[0.9] mb-8">
              Your AI Trading <br />
              <span className="text-blue-600 italic">Copilot</span>
            </h1>
            <p className="text-xl sm:text-2xl font-bold text-secondary max-w-2xl mx-auto mb-12 leading-relaxed">
              Stop guessing your trades. Know exactly <br className="hidden sm:block" /> what to do — every time.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              {!isAuthenticated ? (
                <>
                  <Link 
                    href="/login" 
                    className="w-full sm:w-auto bg-foreground text-card hover:bg-slate-800 dark:hover:bg-slate-200 px-10 py-5 rounded-2xl text-[12px] font-black uppercase tracking-[0.1em] transition-all flex items-center justify-center gap-2 shadow-xl shadow-foreground/5 active:scale-95"
                  >
                    Start Free Trial
                    <ArrowRight size={16} />
                  </Link>
                  <Link 
                    href="/dashboard" 
                    className="w-full sm:w-auto px-10 py-5 rounded-2xl border-2 border-[var(--color-border)] hover:border-blue-600/30 text-[12px] font-black uppercase tracking-[0.1em] transition-all flex items-center justify-center gap-2 active:scale-95"
                  >
                    View Dashboard
                  </Link>
                </>
              ) : (
                <Link 
                  href="/dashboard" 
                  className="w-full sm:w-auto bg-blue-600 text-white hover:bg-blue-700 px-14 py-6 rounded-[2rem] text-[14px] font-black uppercase tracking-[0.2em] transition-all flex items-center justify-center gap-3 shadow-2xl shadow-blue-600/20 active:scale-95 animate-pulse-soft"
                >
                  <LayoutDashboard size={20} />
                  Main Dashboard
                  <ArrowRight size={18} />
                </Link>
              )}
            </div>
          </div>
        </section>

        {/* 3. FEATURES SECTION */}
        <section className="px-6 py-24 bg-[var(--color-border-subtle)]/30 border-y border-[var(--color-border-subtle)]">
          <div className="max-w-7xl mx-auto">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              
              {/* Feature 1 */}
              <div className="bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10 space-y-6 hover:border-blue-600/20 transition-all group">
                <div className="w-14 h-14 rounded-2xl bg-blue-600/10 border border-blue-600/20 flex items-center justify-center text-blue-600 font-bold group-hover:scale-110 transition-transform">
                  <Globe size={24} />
                </div>
                <div className="space-y-3">
                  <h3 className="text-xl font-black text-foreground uppercase tracking-tight">Market Intelligence</h3>
                  <p className="text-sm font-bold text-secondary leading-relaxed">
                    See what others miss. Get the full market picture in seconds.
                  </p>
                </div>
              </div>

              {/* Feature 2 */}
              <div className="bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10 space-y-6 hover:border-blue-600/20 transition-all group">
                <div className="w-14 h-14 rounded-2xl bg-blue-600/10 border border-blue-600/20 flex items-center justify-center text-blue-600 font-bold group-hover:scale-110 transition-transform">
                  <Brain size={24} />
                </div>
                <div className="space-y-3">
                  <h3 className="text-xl font-black text-foreground uppercase tracking-tight">AI Coach</h3>
                  <p className="text-sm font-bold text-secondary leading-relaxed">
                    Trade with an edge. Understand the "why" behind every move.
                  </p>
                </div>
              </div>

              {/* Feature 3 */}
              <div className="bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10 space-y-6 hover:border-blue-600/20 transition-all group">
                <div className="w-14 h-14 rounded-2xl bg-blue-600/10 border border-blue-600/20 flex items-center justify-center text-blue-600 font-bold group-hover:scale-110 transition-transform">
                  <LineChart size={24} />
                </div>
                <div className="space-y-3">
                  <h3 className="text-xl font-black text-foreground uppercase tracking-tight">Strategy Engine</h3>
                  <p className="text-sm font-bold text-secondary leading-relaxed">
                    Execute with precision. Follow a roadmap built for discipline.
                  </p>
                </div>
              </div>

            </div>
          </div>
        </section>

        {/* 4. LIVE PREVIEW */}
        <section className="px-6 py-24 overflow-hidden">
          <div className="max-w-7xl mx-auto">
            <div className="relative group">
              <div className="absolute -inset-1 bg-gradient-to-r from-blue-600/20 to-transparent blur-2xl opacity-50 group-hover:opacity-100 transition duration-1000" />
              <div className="relative bg-card border-2 border-[var(--color-border)] rounded-[3rem] overflow-hidden shadow-2xl">
                <Image 
                  src="/trading_dashboard_v1_mockup_1776106890631.png"
                  alt="Tradamind Live Dashboard Preview"
                  width={1920}
                  height={1080}
                  className="w-full h-auto"
                />
              </div>
            </div>
          </div>
        </section>

        {/* 5. PRICING SECTION */}
        <section className="px-6 py-24 bg-[var(--color-border-subtle)]/30 border-y border-[var(--color-border-subtle)]">
          <div className="max-w-4xl mx-auto text-center mb-16">
            <h2 className="text-4xl sm:text-5xl font-black text-foreground tracking-tighter mb-4">Simple pricing. No complexity.</h2>
            <p className="text-lg font-bold text-secondary uppercase tracking-widest">Select your tactical advantage</p>
          </div>

          <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-8 items-stretch">
            {/* BASIC */}
            <div className="bg-card border-2 border-[var(--color-border)] rounded-[3rem] p-12 flex flex-col justify-between hover:border-foreground/10 transition-all">
              <div className="space-y-10">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="text-2xl font-black text-foreground uppercase tracking-tight italic">Basic</h3>
                    <p className="text-[10px] font-black text-secondary uppercase tracking-widest mt-1">Foundational Intelligence</p>
                  </div>
                  <div className="text-4xl font-black text-foreground tracking-tighter">€89<span className="text-sm text-dim align-top mt-2 ml-1">/mo</span></div>
                </div>
                <div className="space-y-5">
                  {[
                    "AI Coach Access",
                    "Strategy Real-time Insights",
                    "Daily Performance Analysis",
                    "Technical Indicator Hub"
                  ].map((f) => (
                    <div key={f} className="flex items-center gap-4">
                      <div className="w-5 h-5 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center text-blue-600">
                        <Check size={12} strokeWidth={4} />
                      </div>
                      <span className="text-sm font-bold text-dim">{f}</span>
                    </div>
                  ))}
                </div>
              </div>
              <Link 
                href="/login" 
                className="w-full mt-12 py-5 rounded-2xl border-2 border-[var(--color-border)] hover:bg-foreground hover:text-card hover:border-foreground text-[11px] font-black uppercase tracking-[0.2em] transition-all text-center flex items-center justify-center gap-2 group active:scale-95"
              >
                Start Free Trial
                <ArrowUpRight size={14} className="group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
              </Link>
            </div>

            {/* PRO */}
            <div className="bg-foreground text-card border-2 border-foreground rounded-[3rem] p-12 flex flex-col justify-between shadow-2xl relative overflow-hidden group">
              <div className="absolute top-0 right-0 w-32 h-32 bg-blue-600/20 blur-3xl rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-1000" />
              
              <div className="relative z-10 space-y-10">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="inline-flex px-2 py-0.5 rounded-md bg-blue-600 text-white text-[9px] font-black uppercase tracking-widest mb-2">Most Popular</div>
                    <h3 className="text-2xl font-black text-card dark:text-slate-900 uppercase tracking-tight italic">Pro</h3>
                    <p className="text-[10px] font-black opacity-60 uppercase tracking-widest mt-1">High Velocity Alpha</p>
                  </div>
                  <div className="text-4xl font-black text-card dark:text-slate-900 tracking-tighter">€149<span className="text-sm opacity-60 align-top mt-2 ml-1">/mo</span></div>
                </div>
                <div className="space-y-5">
                  {[
                    "Everything in Basic",
                    "High-Frequency AI Signal",
                    "Unlimited Token Context",
                    "Priority Feature Access",
                    "Advanced Risk Management"
                  ].map((f) => (
                    <div key={f} className="flex items-center gap-4">
                      <div className="w-5 h-5 rounded-full bg-slate-800 dark:bg-slate-200 flex items-center justify-center text-white dark:text-slate-900">
                        <Check size={12} strokeWidth={4} />
                      </div>
                      <span className="text-sm font-bold opacity-80">{f}</span>
                    </div>
                  ))}
                </div>
              </div>
              <Link 
                href="/login" 
                className="relative z-10 w-full mt-12 py-5 rounded-2xl bg-white dark:bg-slate-100 text-slate-900 hover:bg-blue-600 hover:text-white text-[11px] font-black uppercase tracking-[0.2em] transition-all text-center flex items-center justify-center gap-2 group active:scale-95 border-none shadow-lg"
              >
                Start Free Trial
                <ArrowUpRight size={14} className="group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
              </Link>
            </div>
          </div>
        </section>

        {/* 6. CTA FOOTER */}
        <section className="px-6 py-32 text-center">
          <div className="max-w-4xl mx-auto space-y-12">
            <h2 className="text-5xl sm:text-7xl font-black text-foreground tracking-tighter leading-none">
              Start trading with clarity.
            </h2>
            <Link 
              href="/login" 
              className="inline-flex bg-foreground text-card hover:bg-slate-800 dark:hover:bg-slate-200 px-12 py-6 rounded-2xl text-[14px] font-black uppercase tracking-[0.2em] transition-all items-center gap-3 shadow-2xl active:scale-95"
            >
              Start Free Trial
              <ArrowRight size={18} />
            </Link>
            <div className="pt-24 border-t border-[var(--color-border-subtle)] flex flex-col sm:flex-row items-center justify-between gap-6 opacity-40">
              <div className="text-[10px] font-bold uppercase tracking-widest text-slate-400">© 2026 Tradamind. All strategic systems reserved.</div>
              <div className="flex gap-8 text-[10px] font-bold uppercase tracking-widest">
                <Link href="#" className="hover:text-foreground">Terms</Link>
                <Link href="#" className="hover:text-foreground">Privacy</Link>
                <Link href="#" className="hover:text-foreground">Security</Link>
              </div>
            </div>
          </div>
        </section>

      </main>
    </div>
  );
}
