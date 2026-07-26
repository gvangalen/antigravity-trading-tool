"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import {
  BarChart3,
  Bot,
  ClipboardCheck,
  ClipboardList,
  FileBarChart2,
  Lightbulb,
  ListChecks,
  Plus,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  TrendingUp,
  WalletCards,
  Workflow,
} from "lucide-react";

import NavBar from "@/components/ui/NavBar";
import ScrollToTop from "@/components/ui/ScrollToTop";
import WorkspaceCanvas from "@/components/workspaces/WorkspaceCanvas";
import AIAssistant, { FinnPanel } from "@/components/ui/AIAssistant";
import AvatarMenu from "@/components/ui/AvatarMenu";
import { useAsset } from "@/app/providers/AssetProvider";
import { useAuth } from "@/components/auth/AuthProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { FINN_COMMAND_OPEN_EVENT } from "@/lib/finnCommandSearch";

export default function FinnWorkspaceShell({ children }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { selectedAsset } = useAsset();
  const { user } = useAuth();
  const { t } = useTranslation();
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [composerQuery, setComposerQuery] = useState("");
  const [composerMenuOpen, setComposerMenuOpen] = useState(false);
  const [commandRequest, setCommandRequest] = useState(null);
  const commandNonceRef = useRef(0);
  const isAnalysisV3 = searchParams.get("variant") !== "legacy";
  const isAdminRoute = pathname?.startsWith("/admin");

  const workspaceCopy = t?.finnWorkspace || {};
  const activeWorkflow = useMemo(
    () => getWorkflowMeta(pathname, isAnalysisV3, workspaceCopy),
    [isAnalysisV3, pathname, workspaceCopy],
  );
  const userName = user?.first_name || "Trader";
  const shellStatus = t?.ui?.shell?.appSlogan || "Professional";
  const currentAsset = selectedAsset || "BTC";
  const composerCopy = workspaceCopy.composer || {};

  const openAssistant = () => {
    commandNonceRef.current += 1;
    setCommandRequest({ mode: "all", category: null, nonce: commandNonceRef.current });
    setAssistantOpen(true);
  };

  const openAssistantMode = (mode, category = null) => {
    commandNonceRef.current += 1;
    setComposerMenuOpen(false);
    setComposerQuery("");
    setCommandRequest({ mode, category, nonce: commandNonceRef.current });
    setAssistantOpen(true);
  };

  useEffect(() => {
    const openCommandCenter = (detail = {}) => {
      commandNonceRef.current += 1;
      setComposerQuery(detail.query || "");
      setCommandRequest({
        mode: detail.mode || "all",
        category: detail.category || null,
        context: detail.context || null,
        query: detail.query || "",
        autoSubmit: Boolean(detail.autoSubmit),
        nonce: commandNonceRef.current,
      });
      setAssistantOpen(true);
    };

    const handleCommandEvent = (event) => openCommandCenter(event?.detail || {});
    const handleShortcut = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openCommandCenter();
      }
    };

    window.addEventListener(FINN_COMMAND_OPEN_EVENT, handleCommandEvent);
    window.addEventListener("keydown", handleShortcut);
    return () => {
      window.removeEventListener(FINN_COMMAND_OPEN_EVENT, handleCommandEvent);
      window.removeEventListener("keydown", handleShortcut);
    };
  }, []);
  const handleComposerSubmit = (event) => {
    event.preventDefault();
    openAssistant();
  };

  if (isAdminRoute) {
    return (
      <>
        <NavBar />

        <div className="min-h-screen bg-[linear-gradient(180deg,#f8fbff_0%,#ffffff_42%,#f7f9fc_100%)] transition-all duration-200 lg:pl-64 dark:bg-[#020617]">
          <div className="pt-16 lg:pt-0">
            <WorkspaceCanvas>
              <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 pb-10 pt-6 lg:gap-8 lg:pb-12 lg:pt-8">
                {children}
              </div>
            </WorkspaceCanvas>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <NavBar />

      <div className="min-h-screen bg-[linear-gradient(180deg,#f8fbff_0%,#ffffff_42%,#f7f9fc_100%)] transition-all duration-200 lg:pl-64 dark:bg-[#020617]">
        <div className="pt-16 lg:pt-0">
          <header className="sticky top-16 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl dark:border-slate-800 dark:bg-[#020617]/90 lg:top-0">
            <div className="px-4 py-4 lg:px-8 lg:py-5">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <button type="button" onClick={() => {
                    commandNonceRef.current += 1;
                    setCommandRequest({ mode: "all", category: null, nonce: commandNonceRef.current });
                    setAssistantOpen(true);
                  }} className="flex items-center gap-3 text-left">
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
                  </button>
                </div>

                <div className="hidden lg:flex lg:items-center lg:gap-4">
                  <button
                    type="button"
                    onClick={() => {
                      commandNonceRef.current += 1;
                      setCommandRequest({ mode: "all", category: null, nonce: commandNonceRef.current });
                      setAssistantOpen(true);
                    }}
                    className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500 transition hover:border-blue-200 hover:text-blue-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400"
                  >
                    FINN
                    <span className="rounded-md border border-slate-200 px-1.5 py-0.5 text-[9px] dark:border-slate-700">⌘K</span>
                  </button>
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
                      {activeWorkflow.eyebrow || workspaceCopy.canvasEyebrow}
                    </div>
                    <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                      {activeWorkflow.label}
                    </h2>
                    <p className="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">
                      {activeWorkflow.description || workspaceCopy.defaultDescription}
                    </p>
                  </div>

                  {activeWorkflow.status !== null ? (
                    <div className="inline-flex items-center gap-2 self-start rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300">
                      <span className="h-2 w-2 rounded-full bg-emerald-500" />
                      {activeWorkflow.status || workspaceCopy.activeStatus}
                    </div>
                  ) : null}
                </div>

                <WorkspaceSteps steps={activeWorkflow.steps} />

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
                {composerMenuOpen ? (
                  <div className="absolute bottom-[calc(100%+10px)] left-0 z-20 w-60 overflow-hidden rounded-2xl border border-slate-200 bg-white p-1.5 shadow-xl shadow-slate-900/10 dark:border-slate-800 dark:bg-slate-950">
                    <button
                      type="button"
                      onClick={() => openAssistantMode("asset")}
                      className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold text-slate-800 transition hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-900"
                    >
                      <Search size={17} className="text-slate-500" />
                      {composerCopy.asset}
                    </button>
                    <button
                      type="button"
                      onClick={() => openAssistantMode("indicator")}
                      className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold text-slate-800 transition hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-900"
                    >
                      <SlidersHorizontal size={17} className="text-slate-500" />
                      {composerCopy.indicator}
                    </button>
                  </div>
                ) : null}
                <button
                  type="button"
                  aria-label={composerCopy.menu}
                  aria-expanded={composerMenuOpen}
                  onClick={() => setComposerMenuOpen((current) => !current)}
                  className="absolute left-3 top-1/2 z-10 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  <Plus size={23} className={`transition-transform ${composerMenuOpen ? "rotate-45" : ""}`} />
                </button>
                <input
                  type="text"
                  value={composerQuery}
                  onFocus={openAssistant}
                  onChange={(event) => {
                    setComposerMenuOpen(false);
                    setComposerQuery(event.target.value);
                    if (!assistantOpen) openAssistant();
                  }}
                  placeholder={composerCopy.placeholder}
                  className="w-full rounded-[22px] border border-slate-100 bg-slate-50 py-4 pl-16 pr-16 text-sm font-medium text-slate-900 outline-none transition focus:border-blue-200 focus:bg-white focus:ring-4 focus:ring-blue-600/5 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-blue-900 dark:focus:bg-slate-800"
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
              aria-label={workspaceCopy.closeBackdrop}
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
              commandRequest={commandRequest}
              autoFocusComposer
            />
          </div>
        ) : null}
      </div>

      <ScrollToTop />
    </>
  );
}

function WorkspaceSteps({ steps }) {
  if (!steps?.length) return null;

  return (
    <div className="mb-5 overflow-hidden rounded-[22px] border border-slate-200/80 bg-slate-100 dark:border-slate-800 dark:bg-slate-800">
      <div className="grid gap-px sm:grid-cols-3">
        {steps.map(({ description, icon: Icon, label }, index) => (
          <div
            key={label}
            className="flex min-w-0 items-center gap-3 bg-white px-4 py-3.5 dark:bg-[#06101f] lg:px-5 lg:py-4"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-300">
              <Icon size={19} strokeWidth={1.9} />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-black text-slate-950 dark:text-slate-50">
                <span className="text-blue-600 dark:text-blue-400">{index + 1}</span>
                <span>{label}</span>
              </div>
              <p className="mt-0.5 text-xs font-medium leading-5 text-slate-500 dark:text-slate-400">
                {description}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function getWorkflowMeta(pathname, isAnalysisV3, copy) {
  if (isAnalysisV3) {
    const icons = {
      analysis: [Search, BarChart3, Lightbulb],
      portfolio: [WalletCards, ShieldAlert, ListChecks],
      automation: [ClipboardList, Bot, ShieldCheck],
      reflection: [FileBarChart2, ClipboardCheck, TrendingUp],
    };
    const steps = Object.fromEntries(
      Object.entries(icons).map(([key, workflowIcons]) => [
        key,
        (copy?.steps?.[key] || []).map((step, index) => ({ ...step, icon: workflowIcons[index] })),
      ]),
    );
    const planCopy = { ...copy?.pages?.plan, status: null };
    const v3Workflows = {
      "/asset": { ...copy?.pages?.analysis, steps: steps.analysis },
      "/market": { ...copy?.pages?.analysis, steps: steps.analysis },
      "/macro": { ...copy?.pages?.analysis, steps: steps.analysis },
      "/technical": { ...copy?.pages?.analysis, steps: steps.analysis },
      "/bot": { ...copy?.pages?.automation, steps: steps.automation },
      "/setup": planCopy,
      "/strategy": planCopy,
      "/report": { ...copy?.pages?.reflection, steps: steps.reflection },
      "/portfolio": { ...copy?.pages?.portfolio, steps: steps.portfolio },
      "/dashboard": { ...copy?.pages?.analysis, steps: steps.analysis },
    };

    return v3Workflows[pathname] || { label: copy?.workspaceLabel };
  }

  const workflows = Object.fromEntries(
    Object.entries(copy?.legacyPages || {}).map(([path, label]) => [path, { label }]),
  );

  return workflows[pathname] || { label: copy?.workflowLabel };
}
