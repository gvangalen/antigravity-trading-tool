"use client";

import { useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bot,
  Brain,
  ChevronRight,
  ClipboardList,
  DollarSign,
  FileBarChart2,
  Layers3,
  LineChart,
  Orbit,
  Shield,
  ShieldCheck,
  TrendingUp,
  Workflow,
} from "lucide-react";

import NavBar from "@/components/ui/NavBar";
import ScrollToTop from "@/components/ui/ScrollToTop";
import WorkspaceCanvas from "@/components/workspaces/WorkspaceCanvas";
import AIAssistant from "@/components/ui/AIAssistant";
import AIFloatingButton from "@/components/ui/AIFloatingButton";
import AssetSearchBar from "@/components/ui/AssetSearchBar";
import AvatarMenu from "@/components/ui/AvatarMenu";
import { useAsset } from "@/app/providers/AssetProvider";
import { useAuth } from "@/components/auth/AuthProvider";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function FinnWorkspaceShell({ children }) {
  const pathname = usePathname();
  const { selectedAsset } = useAsset();
  const { user } = useAuth();
  const { t } = useTranslation();
  const [assistantOpen, setAssistantOpen] = useState(false);

  const activeWorkflow = useMemo(() => getWorkflowMeta(pathname, selectedAsset), [pathname, selectedAsset]);
  const ActiveWorkflowIcon = activeWorkflow.icon;
  const userName = user?.first_name || "Trader";
  const shellStatus = t?.ui?.shell?.appSlogan || "Professional";

  return (
    <>
      <NavBar />

      <div className="min-h-screen bg-[linear-gradient(180deg,#f8fbff_0%,#ffffff_42%,#f7f9fc_100%)] transition-all duration-200 lg:pl-64 dark:bg-[#020617]">
        <div className="pt-16 lg:pt-0">
          <header className="sticky top-16 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl dark:border-slate-800 dark:bg-[#020617]/90 lg:top-0">
            <div className="px-4 py-4 lg:px-8 lg:py-5">
              <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                <div className="min-w-0">
                  <div className="flex items-center gap-3">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/20">
                      <Bot size={24} />
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h1 className="text-2xl font-black tracking-tight text-slate-950 dark:text-slate-50">FINN</h1>
                        <span className="rounded-full bg-blue-50 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-blue-700 dark:bg-blue-950/40 dark:text-blue-300">
                          {shellStatus}
                        </span>
                      </div>
                      <p className="mt-1 text-[11px] font-black uppercase tracking-[0.28em] text-slate-500 dark:text-slate-400">
                        {userName} · {activeWorkflow.label} · {selectedAsset}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="hidden min-w-0 flex-1 px-6 lg:flex xl:max-w-xl">
                  <AssetSearchBar />
                </div>

                <div className="hidden lg:flex lg:items-center lg:gap-4">
                  <button
                    type="button"
                    onClick={() => setAssistantOpen(true)}
                    className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-slate-700 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-blue-900 dark:hover:bg-blue-950/30 dark:hover:text-blue-300"
                  >
                    <Brain size={16} />
                    Open FINN Chat
                  </button>
                  <div className="rounded-full border-2 border-slate-100 p-0.5 shadow-sm dark:border-slate-800">
                    <AvatarMenu />
                  </div>
                </div>
              </div>
            </div>
          </header>

          <WorkspaceCanvas>
            <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 py-6 lg:gap-8 lg:py-8">
              <section className="overflow-hidden rounded-[28px] border border-slate-200/80 bg-white shadow-[0_20px_60px_-35px_rgba(37,99,235,0.32)] dark:border-slate-800 dark:bg-[#0f172a]">
                <div className="border-b border-slate-100 px-6 py-5 dark:border-slate-800 lg:px-8">
                  <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/20">
                          <ActiveWorkflowIcon size={20} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h2 className="text-2xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                              {activeWorkflow.title}
                            </h2>
                            <span className="rounded-full bg-blue-50 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-blue-700 dark:bg-blue-950/40 dark:text-blue-300">
                              {activeWorkflow.context}
                            </span>
                          </div>
                          <p className="mt-1 text-[11px] font-black uppercase tracking-[0.28em] text-slate-500 dark:text-slate-400">
                            {activeWorkflow.kicker}
                          </p>
                        </div>
                      </div>

                      <div className="mt-5 flex flex-wrap items-center gap-3">
                        <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.18em] ${activeWorkflow.priorityTone}`}>
                          <Shield size={12} />
                          {activeWorkflow.priorityLabel}
                        </div>
                        <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                          <Orbit size={12} />
                          {activeWorkflow.assetLabel}
                        </div>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => setAssistantOpen(true)}
                      className="inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-lg shadow-blue-600/20 transition-colors hover:bg-blue-700"
                    >
                      {activeWorkflow.actionLabel}
                      <ChevronRight size={14} />
                    </button>
                  </div>
                </div>

                <div className="grid gap-5 px-6 py-6 lg:grid-cols-[minmax(0,1.35fr)_280px] lg:px-8">
                  <div>
                    <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.28em] text-slate-500 dark:text-slate-400">
                      <ShieldCheck size={12} className="text-blue-600 dark:text-blue-400" />
                      Active Briefing
                    </div>
                    <p className="mt-3 max-w-4xl whitespace-pre-line text-[15px] font-semibold leading-8 text-slate-800 dark:text-slate-200">
                      {activeWorkflow.briefing}
                    </p>
                  </div>

                  <div className="rounded-[24px] border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-900/60">
                    <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
                      <Workflow size={12} className="text-blue-600 dark:text-blue-400" />
                      Workflow Priority
                    </div>
                    <p className="mt-3 text-lg font-black tracking-tight text-slate-950 dark:text-slate-50">
                      {activeWorkflow.priorityHeadline}
                    </p>
                    <p className="mt-2 text-sm font-medium leading-6 text-slate-600 dark:text-slate-300">
                      {activeWorkflow.priorityBody}
                    </p>
                  </div>
                </div>
              </section>

              <section className="rounded-[32px] border border-slate-200/80 bg-white p-4 shadow-[0_18px_50px_-40px_rgba(15,23,42,0.35)] dark:border-slate-800 dark:bg-[#06101f] lg:p-6">
                <div className="mb-5 flex flex-col gap-3 border-b border-slate-100 pb-5 dark:border-slate-800 lg:flex-row lg:items-end lg:justify-between">
                  <div>
                    <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">
                      <ShieldCheck size={12} />
                      Workflow Canvas
                    </div>
                    <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                      {activeWorkflow.label}
                    </h2>
                    <p className="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">
                      Werk in deze flow terwijl FINN briefing en chat vast beschikbaar blijven.
                    </p>
                  </div>

                  <div className="inline-flex items-center gap-2 self-start rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                    Active Briefing Live
                  </div>
                </div>

                <div>{children}</div>
              </section>
            </div>
          </WorkspaceCanvas>
        </div>

        <AIFloatingButton isOpen={assistantOpen} onClick={() => setAssistantOpen((open) => !open)} />
        {assistantOpen ? (
          <div className="fixed inset-0 z-[75] flex items-center justify-center bg-slate-950/35 p-4 backdrop-blur-sm">
            <button
              type="button"
              aria-label="Close FINN chat backdrop"
              className="absolute inset-0 cursor-default"
              onClick={() => setAssistantOpen(false)}
            />
            <AIAssistant isOpen={assistantOpen} setIsOpen={setAssistantOpen} modal className="z-10" />
          </div>
        ) : null}
      </div>

      <ScrollToTop />
    </>
  );
}

function getWorkflowMeta(pathname, symbol) {
  const asset = symbol || "BTC";
  const workflows = {
    "/asset": {
      title: "FINN Overview",
      kicker: `Overview workflow · ${asset} · Daily operating brief`,
      context: "Overview",
      assetLabel: `${asset} focus`,
      priorityLabel: "Today first",
      priorityHeadline: `Review what needs attention around ${asset} first.`,
      priorityBody: "Use this flow to decide which review, risk, or execution question should lead your day before you act elsewhere.",
      briefing: `Good morning. ${asset} deserves a quick operating review before new decisions.\nStart with the item that is currently blocking confidence, then move through open reviews only if they still matter today.`,
      actionLabel: "Open overview chat",
      priorityTone: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300",
      icon: Activity,
    },
    "/bot": {
      title: "Portfolio & Bots",
      kicker: `Portfolio workflow · ${asset} · Allocation, risk, execution`,
      context: "Portfolio",
      assetLabel: `${asset} allocation`,
      priorityLabel: "Capital at risk",
      priorityHeadline: "Check allocation, active risk, and intervention points.",
      priorityBody: "This flow is for cash, exposure, performance, and bot-health checks before you approve changes or let live systems continue.",
      briefing: `Review allocation, concentration risk, and cash flexibility before changing your portfolio.\nIf a live bot is drifting from plan, handle that first and only then revisit performance.`,
      actionLabel: "Open portfolio chat",
      priorityTone: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-300",
      icon: Bot,
    },
    "/market": {
      title: "Market Context",
      kicker: `Market workflow · ${asset} · Regime, liquidity, sentiment`,
      context: "Market",
      assetLabel: `${asset} market`,
      priorityLabel: "Regime check",
      priorityHeadline: `Validate the market regime around ${asset}.`,
      priorityBody: "Scan liquidity, sentiment, and structural market tone here before you promote any setup into a live execution candidate.",
      briefing: `Check whether liquidity, positioning, and sentiment still support your current market assumptions.\nIf the regime is unclear, lower decision speed and avoid forcing fresh exposure.`,
      actionLabel: "Open market chat",
      priorityTone: "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/50 dark:bg-blue-950/20 dark:text-blue-300",
      icon: DollarSign,
    },
    "/macro": {
      title: "Macro Intelligence",
      kicker: `Macro workflow · ${asset} · DXY, yields, Fed, flows`,
      context: "Macro",
      assetLabel: "Macro drivers",
      priorityLabel: "Macro pressure",
      priorityHeadline: "Update the macro backdrop before trusting lower-level signals.",
      priorityBody: "Use this flow to review DXY, yields, Fed tone, and ETF-flow pressure so your workflow stays anchored in the broader environment.",
      briefing: `Read the macro layer first when cross-asset pressure is shaping crypto behavior.\nIf DXY, yields, or policy tone are fighting your thesis, your execution pace should slow down.`,
      actionLabel: "Open macro chat",
      priorityTone: "border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-300",
      icon: TrendingUp,
    },
    "/technical": {
      title: "Technical Intelligence",
      kicker: `Technical workflow · ${asset} · Trend, levels, momentum`,
      context: "Technical",
      assetLabel: `${asset} structure`,
      priorityLabel: "Level integrity",
      priorityHeadline: "Confirm trend strength, levels, and invalidation.",
      priorityBody: "This flow exists to decide whether technical structure still supports your setup logic or whether price has invalidated the plan.",
      briefing: `Validate trend direction, level integrity, and momentum before acting on any chart idea.\nIf price structure is no longer clean, do not let earlier conviction carry the trade for you.`,
      actionLabel: "Open technical chat",
      priorityTone: "border-cyan-200 bg-cyan-50 text-cyan-700 dark:border-cyan-900/50 dark:bg-cyan-950/20 dark:text-cyan-300",
      icon: LineChart,
    },
    "/setup": {
      title: "Setup Control",
      kicker: `Setup workflow · ${asset} · Candidates, validation, RR`,
      context: "Setups",
      assetLabel: `${asset} candidates`,
      priorityLabel: "Candidate quality",
      priorityHeadline: "Promote only setups that still deserve validation.",
      priorityBody: "Use this space to review setup candidates, entry logic, stop placement, and reward-to-risk quality before strategy work starts.",
      briefing: `Review your best setup candidates and validate whether their entry, stop, and reward profile still make sense.\nIf a setup needs stretching to look good, it is not ready for strategy or bot execution.`,
      actionLabel: "Open setups chat",
      priorityTone: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300",
      icon: Layers3,
    },
    "/strategy": {
      title: "Strategy Execution",
      kicker: `Strategy workflow · ${asset} · Active plans, deviations, optimization`,
      context: "Strategies",
      assetLabel: `${asset} plans`,
      priorityLabel: "Plan discipline",
      priorityHeadline: "Review which active strategies need tightening.",
      priorityBody: "This flow is for active strategy quality, plan drift, and optimization opportunities before you hand anything to automation.",
      briefing: `Check active strategies for drift, missing validation, and unnecessary complexity.\nA strategy that no longer matches the setup or the current market context should be corrected before it reaches a bot.`,
      actionLabel: "Open strategy chat",
      priorityTone: "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/50 dark:bg-blue-950/20 dark:text-blue-300",
      icon: ClipboardList,
    },
    "/report": {
      title: "Reports & Conclusions",
      kicker: `Reports workflow · ${asset} · Summaries, conclusions, follow-up`,
      context: "Reports",
      assetLabel: "Recent reports",
      priorityLabel: "Open conclusions",
      priorityHeadline: "Turn fresh reporting into concrete follow-up.",
      priorityBody: "Use reports to capture what changed, what stayed true, and which actions or reviews still remain open.",
      briefing: `Check whether new reports changed the operating picture or simply confirmed your plan.\nThe useful output here is not more reading, but a small number of concrete follow-up actions.`,
      actionLabel: "Open reports chat",
      priorityTone: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-300",
      icon: FileBarChart2,
    },
  };

  return workflows[pathname] || {
    title: "Workflow Briefing",
    kicker: `Workflow · ${asset}`,
    context: "Workflow",
    assetLabel: `${asset} context`,
    priorityLabel: "Current focus",
    priorityHeadline: "Review the current workflow before taking the next step.",
    priorityBody: "Finn keeps this shell available so the active workflow always starts with context, priority, and a safe next action.",
    briefing: `Use this workspace to orient first, then act.\nIf the next step is still unclear, open FINN before committing capital or changing the system.`,
    actionLabel: "Open FINN chat",
    priorityTone: "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300",
    icon: Workflow,
  };
}
