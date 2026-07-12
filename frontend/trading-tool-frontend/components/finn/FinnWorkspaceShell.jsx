"use client";

import { useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { Activity, Bot, ClipboardList, DollarSign, FileBarChart2, Layers3, LineChart, Send, TrendingUp, Workflow } from "lucide-react";

import NavBar from "@/components/ui/NavBar";
import ScrollToTop from "@/components/ui/ScrollToTop";
import WorkspaceCanvas from "@/components/workspaces/WorkspaceCanvas";
import AIAssistant, { FinnPanel } from "@/components/ui/AIAssistant";
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
  const [composerQuery, setComposerQuery] = useState("");

  const activeWorkflow = useMemo(() => getWorkflowMeta(pathname), [pathname]);
  const userName = user?.first_name || "Trader";
  const shellStatus = t?.ui?.shell?.appSlogan || "Professional";
  const currentAsset = selectedAsset || "BTC";
  const composerPlaceholder = t?.assistant?.uiText?.inputPlaceholder || "Ask Finn for context, risk, or the next step...";

  const openAssistant = () => setAssistantOpen(true);
  const handleComposerSubmit = (event) => {
    event.preventDefault();
    setAssistantOpen(true);
  };

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
                        {userName} · {activeWorkflow.label} · {currentAsset}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="hidden min-w-0 flex-1 px-6 lg:flex xl:max-w-xl">
                  <AssetSearchBar />
                </div>

                <div className="hidden lg:flex lg:items-center lg:gap-4">
                  <div className="rounded-full border-2 border-slate-100 p-0.5 shadow-sm dark:border-slate-800">
                    <AvatarMenu />
                  </div>
                </div>
              </div>
            </div>
          </header>

          <WorkspaceCanvas>
            <div
              className={`mx-auto flex w-full max-w-[1500px] flex-col gap-6 pt-6 lg:gap-8 lg:pt-8 ${
                assistantOpen ? "pb-8" : "pb-10 lg:pb-12"
              }`}
            >
              <section className="overflow-hidden rounded-[28px] border border-slate-200/80 bg-white shadow-[0_20px_60px_-35px_rgba(37,99,235,0.32)] dark:border-slate-800 dark:bg-[#0f172a]">
                <FinnPanel
                  previewSectionsOnly
                  eventsEnabled={!assistantOpen}
                  className="h-auto min-h-0"
                />
              </section>

              <section className="rounded-[32px] border border-slate-200/80 bg-white p-4 shadow-[0_18px_50px_-40px_rgba(15,23,42,0.35)] dark:border-slate-800 dark:bg-[#06101f] lg:p-6">
                <div className="mb-5 flex flex-col gap-3 border-b border-slate-100 pb-5 dark:border-slate-800 lg:flex-row lg:items-end lg:justify-between">
                  <div>
                    <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">
                      <Workflow size={12} />
                      Workflow Canvas
                    </div>
                    <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                      {activeWorkflow.label}
                    </h2>
                    <p className="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">
                      Werk in deze flow met de actieve FINN-briefing direct erboven.
                    </p>
                  </div>

                  <div className="inline-flex items-center gap-2 self-start rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                    Workflow Active
                  </div>
                </div>

                <div>{children}</div>
              </section>

              {!assistantOpen ? <div aria-hidden className="h-40 shrink-0 lg:h-48" /> : null}
            </div>
          </WorkspaceCanvas>
        </div>

        {!assistantOpen ? (
          <div className="pointer-events-none fixed inset-x-0 bottom-0 z-[70] flex justify-center px-4 pb-4">
            <form
              onSubmit={handleComposerSubmit}
              className="pointer-events-auto w-full max-w-[980px] rounded-[28px] border border-slate-200/90 bg-white/95 p-3 shadow-[0_20px_60px_-25px_rgba(15,23,42,0.35)] backdrop-blur-xl dark:border-slate-800 dark:bg-[#0f172a]/95"
            >
              <div className="relative">
                <input
                  type="text"
                  value={composerQuery}
                  onFocus={openAssistant}
                  onChange={(event) => {
                    setComposerQuery(event.target.value);
                    if (!assistantOpen) setAssistantOpen(true);
                  }}
                  placeholder={composerPlaceholder}
                  className="w-full rounded-[22px] border border-slate-100 bg-slate-50 py-4 pl-6 pr-16 text-sm font-medium text-slate-900 outline-none transition focus:border-blue-200 focus:bg-white focus:ring-4 focus:ring-blue-600/5 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-blue-900 dark:focus:bg-slate-800"
                />
                <button
                  type="submit"
                  disabled={!composerQuery.trim()}
                  className="absolute right-3 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-2xl bg-slate-900 text-white transition hover:bg-blue-600 disabled:opacity-50 dark:bg-blue-600 dark:hover:bg-blue-700"
                >
                  <Send size={18} />
                </button>
              </div>
            </form>
          </div>
        ) : null}
        {assistantOpen ? (
          <div className="fixed inset-0 z-[75] flex items-center justify-center bg-slate-950/35 p-4 backdrop-blur-sm">
            <button
              type="button"
              aria-label="Close FINN chat backdrop"
              className="absolute inset-0 cursor-default"
              onClick={() => setAssistantOpen(false)}
            />
            <AIAssistant
              isOpen={assistantOpen}
              setIsOpen={setAssistantOpen}
              modal
              className="z-10"
              eventsEnabled={assistantOpen}
              queryValue={composerQuery}
              onQueryChange={setComposerQuery}
              autoFocusComposer
            />
          </div>
        ) : null}
      </div>

      <ScrollToTop />
    </>
  );
}

function getWorkflowMeta(pathname) {
  const workflows = {
    "/asset": { label: "Overview", icon: Activity },
    "/bot": { label: "Bots", icon: Bot },
    "/market": { label: "Market", icon: DollarSign },
    "/macro": { label: "Macro", icon: TrendingUp },
    "/technical": { label: "Technical", icon: LineChart },
    "/setup": { label: "Setups", icon: Layers3 },
    "/strategy": { label: "Strategies", icon: ClipboardList },
    "/report": { label: "Reports", icon: FileBarChart2 },
  };

  return workflows[pathname] || { label: "Workflow", icon: Workflow };
}
