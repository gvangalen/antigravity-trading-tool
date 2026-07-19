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
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
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
  const { t, locale } = useTranslation();
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [composerQuery, setComposerQuery] = useState("");
  const [commandRequest, setCommandRequest] = useState(null);
  const commandNonceRef = useRef(0);
  const isAnalysisV3 = searchParams.get("variant") !== "legacy";

  const activeWorkflow = useMemo(() => getWorkflowMeta(pathname, isAnalysisV3, locale), [isAnalysisV3, locale, pathname]);
  const isPlanWorkspace = pathname === "/setup" || pathname === "/strategy";
  const userName = user?.first_name || "Trader";
  const shellStatus = t?.ui?.shell?.appSlogan || "Professional";
  const currentAsset = selectedAsset || "BTC";
  const composerPlaceholder = t?.assistant?.uiText?.inputPlaceholder || "Ask Finn for context, risk, or the next step...";

  const openAssistant = () => {
    commandNonceRef.current += 1;
    setCommandRequest({ mode: "all", category: null, nonce: commandNonceRef.current });
    setAssistantOpen(true);
  };

  useEffect(() => {
    const openCommandCenter = (detail = {}) => {
      commandNonceRef.current += 1;
      setComposerQuery(detail.query || "");
      setCommandRequest({
        mode: detail.mode || "all",
        category: detail.category || null,
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
              {!isPlanWorkspace ? (
                <section className="overflow-hidden rounded-[28px] border border-slate-200/80 bg-white shadow-[0_20px_60px_-35px_rgba(37,99,235,0.32)] dark:border-slate-800 dark:bg-[#0f172a]">
                  <FinnPanel
                    previewSectionsOnly
                    eventsEnabled={!assistantOpen}
                    className="h-auto min-h-0"
                  />
                </section>
              ) : null}

              <section className="rounded-[32px] border border-slate-200/80 bg-white p-4 shadow-[0_18px_50px_-40px_rgba(15,23,42,0.35)] dark:border-slate-800 dark:bg-[#06101f] lg:p-6">
                <div className="mb-5 flex flex-col gap-3 border-b border-slate-100 pb-5 dark:border-slate-800 lg:flex-row lg:items-end lg:justify-between">
                  <div>
                    <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">
                      <Workflow size={12} />
                      {activeWorkflow.eyebrow || (isAnalysisV3 ? "Analysis Canvas" : "Workflow Canvas")}
                    </div>
                    <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                      {activeWorkflow.label}
                    </h2>
                    <p className="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">
                      {activeWorkflow.description || (isAnalysisV3
                        ? "Bekijk een asset in drie contexten met de actieve FINN-briefing direct erboven."
                        : "Werk in deze flow met de actieve FINN-briefing direct erboven.")}
                    </p>
                  </div>

                  {activeWorkflow.status !== null ? (
                    <div className="inline-flex items-center gap-2 self-start rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300">
                      <span className="h-2 w-2 rounded-full bg-emerald-500" />
                      {activeWorkflow.status || (isAnalysisV3 ? "Live Analysis" : "Workflow Active")}
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
                <input
                  type="text"
                  value={composerQuery}
                  onFocus={openAssistant}
                  onChange={(event) => {
                    setComposerQuery(event.target.value);
                    if (!assistantOpen) openAssistant();
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

function getWorkflowMeta(pathname, isAnalysisV3, locale) {
  if (isAnalysisV3) {
    const workspaceCopies = {
      nl: {
        analysis: [
          { label: "Asset", description: "Wat analyseer ik?", icon: Search },
          { label: "Bewijs", description: "Wat zeggen Markt, Macro en Technisch?", icon: BarChart3 },
          { label: "Conclusie", description: "Wat betekent dit voor mijn plan?", icon: Lightbulb },
        ],
        portfolio: [
          { label: "Posities", description: "Wat bezit ik?", icon: WalletCards },
          { label: "Risico", description: "Waar zit mijn blootstelling?", icon: ShieldAlert },
          { label: "Actie", description: "Wat vraagt mijn aandacht?", icon: ListChecks },
        ],
        automation: [
          { label: "Plan", description: "Welke regels gelden?", icon: ClipboardList },
          { label: "Uitvoering", description: "Wat voert Automatisering uit?", icon: Bot },
          { label: "Bewaking", description: "Blijft alles binnen mijn risico?", icon: ShieldCheck },
        ],
        reflection: [
          { label: "Resultaat", description: "Wat gebeurde er?", icon: FileBarChart2 },
          { label: "Evaluatie", description: "Volgde ik mijn plan?", icon: ClipboardCheck },
          { label: "Verbetering", description: "Wat pas ik de volgende keer aan?", icon: TrendingUp },
        ],
      },
      en: {
        analysis: [
          { label: "Asset", description: "What am I analysing?", icon: Search },
          { label: "Evidence", description: "What do Market, Macro and Technical show?", icon: BarChart3 },
          { label: "Conclusion", description: "What does this mean for my plan?", icon: Lightbulb },
        ],
        portfolio: [
          { label: "Positions", description: "What do I own?", icon: WalletCards },
          { label: "Risk", description: "Where is my exposure?", icon: ShieldAlert },
          { label: "Action", description: "What needs my attention?", icon: ListChecks },
        ],
        automation: [
          { label: "Plan", description: "Which rules apply?", icon: ClipboardList },
          { label: "Execution", description: "What does Automation execute?", icon: Bot },
          { label: "Monitoring", description: "Does everything remain within my risk?", icon: ShieldCheck },
        ],
        reflection: [
          { label: "Result", description: "What happened?", icon: FileBarChart2 },
          { label: "Evaluation", description: "Did I follow my plan?", icon: ClipboardCheck },
          { label: "Improvement", description: "What will I change next time?", icon: TrendingUp },
        ],
      },
      de: {
        analysis: [
          { label: "Asset", description: "Was analysiere ich?", icon: Search },
          { label: "Evidenz", description: "Was zeigen Markt, Makro und Technik?", icon: BarChart3 },
          { label: "Fazit", description: "Was bedeutet das für meinen Plan?", icon: Lightbulb },
        ],
        portfolio: [
          { label: "Positionen", description: "Was besitze ich?", icon: WalletCards },
          { label: "Risiko", description: "Wo liegt meine Exposition?", icon: ShieldAlert },
          { label: "Aktion", description: "Was braucht meine Aufmerksamkeit?", icon: ListChecks },
        ],
        automation: [
          { label: "Plan", description: "Welche Regeln gelten?", icon: ClipboardList },
          { label: "Ausführung", description: "Was führt die Automatisierung aus?", icon: Bot },
          { label: "Überwachung", description: "Bleibt alles innerhalb meines Risikos?", icon: ShieldCheck },
        ],
        reflection: [
          { label: "Ergebnis", description: "Was ist passiert?", icon: FileBarChart2 },
          { label: "Auswertung", description: "Habe ich meinen Plan befolgt?", icon: ClipboardCheck },
          { label: "Verbesserung", description: "Was ändere ich beim nächsten Mal?", icon: TrendingUp },
        ],
      },
    };
    const localizedWorkspaces = workspaceCopies[String(locale || "nl").toLowerCase()] || workspaceCopies.nl;
    const planCopies = {
      nl: {
        label: "Mijn Plan",
        eyebrow: "Planwerkruimte",
        description: "Bouw en beheer je handelsplannen voor de geselecteerde asset.",
        status: null,
      },
      en: {
        label: "My Plan",
        eyebrow: "Plan Workspace",
        description: "Build and manage your trading plans for the selected asset.",
        status: null,
      },
      de: {
        label: "Mein Plan",
        eyebrow: "Plan-Arbeitsbereich",
        description: "Erstelle und verwalte deine Handelspläne für das ausgewählte Asset.",
        status: null,
      },
    };
    const planCopy = planCopies[String(locale || "nl").toLowerCase()] || planCopies.nl;
    const v3Workflows = {
      "/asset": { label: "Analyse", steps: localizedWorkspaces.analysis },
      "/market": { label: "Analyse", steps: localizedWorkspaces.analysis },
      "/macro": { label: "Analyse", steps: localizedWorkspaces.analysis },
      "/technical": { label: "Analyse", steps: localizedWorkspaces.analysis },
      "/bot": { label: "Automation", steps: localizedWorkspaces.automation },
      "/setup": planCopy,
      "/strategy": planCopy,
      "/report": { label: "Reflectie", steps: localizedWorkspaces.reflection },
      "/portfolio": { label: "Portfolio", steps: localizedWorkspaces.portfolio },
      "/dashboard": { label: "Analyse", steps: localizedWorkspaces.analysis },
    };

    return v3Workflows[pathname] || { label: "Workspace" };
  }

  const workflows = {
    "/asset": { label: "Overview" },
    "/bot": { label: "Bots" },
    "/market": { label: "Market" },
    "/macro": { label: "Macro" },
    "/technical": { label: "Technical" },
    "/setup": { label: "Setups" },
    "/strategy": { label: "Strategies" },
    "/report": { label: "Reports" },
  };

  return workflows[pathname] || { label: "Workflow" };
}
