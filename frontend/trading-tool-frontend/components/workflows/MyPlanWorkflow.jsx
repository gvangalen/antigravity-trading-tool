"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Activity,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  Layers3,
  Pencil,
  Plus,
  ShieldCheck,
  Sparkles,
  Target,
  Trash2,
  WalletCards,
} from "lucide-react";

import { useTranslation } from "@/app/providers/I18nProvider";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import { useModal } from "@/components/modal/ModalProvider";
import SetupForm from "@/components/setup/SetupForm";
import StrategyForm from "@/components/strategy/StrategyForm";
import Drawer from "@/components/ui/Drawer";
import { useStrategyData } from "@/hooks/useStrategyData";
import { deleteSetup } from "@/lib/api/setups";

const COPY = {
  nl: {
    eyebrow: "Mijn Plan",
    heading: "Wanneer handel je en hoe?",
    intro: "Koppel je marktvoorwaarden aan duidelijke uitvoeringsregels. Samen vormen ze een plan dat je consequent kunt volgen.",
    newPlan: "Nieuw plan",
    setupTerm: "Setup",
    setupHelp: "Wanneer mag ik handelen?",
    strategyTerm: "Strategie",
    strategyHelp: "Hoe voer ik de trade uit?",
    planTerm: "Plan",
    planHelp: "De combinatie die klaarstaat voor uitvoering.",
    finnLabel: "FINN planadvies",
    finishPlan: "Plan afmaken",
    activePlan: "Actief plan",
    selectedAsset: "Asset en ritme",
    execution: "Uitvoering",
    readyForAutomation: "Klaar voor Automation",
    notReady: "Nog niet compleet",
    editSetup: "Setup bewerken",
    editStrategy: "Strategie bewerken",
    addStrategy: "Strategie toevoegen",
    openAutomation: "Naar Automation",
    plansTitle: "Mijn plannen",
    plansIntro: "Setup en strategie blijven zichtbaar als twee onderdelen van hetzelfde plan.",
    allPlans: "Alle plannen",
    plans: "plannen",
    plan: "plan",
    active: "Actief",
    ready: "Klaar",
    concept: "Concept",
    missingStrategy: "Strategie ontbreekt",
    setupReady: "Setup gereed",
    strategyReady: "Strategie gereed",
    market: "markt",
    macro: "macro",
    technical: "technisch",
    amount: "Bedrag",
    entry: "Entry",
    stopLoss: "Stop-loss",
    targets: "Targets",
    fixed: "Vast bedrag",
    dynamic: "Dynamische sizing",
    noPlansTitle: "Maak je eerste plan",
    noPlansBody: "Begin met de voorwaarden waaronder je wilt handelen. Daarna voegen we de uitvoering toe.",
    createSetupTitle: "Stap 1 · Setup maken",
    createSetupSubtitle: "Wanneer mag ik handelen?",
    createStrategyTitle: "Stap 2 · Strategie instellen",
    createStrategySubtitle: "Hoe voer ik de trade uit?",
    editSetupTitle: "Setup bewerken",
    editStrategyTitle: "Strategie bewerken",
    deletePlan: "Plan verwijderen",
    deleteTitle: "Plan verwijderen?",
    deleteBody: "De gekoppelde strategie en setup worden verwijderd. Dit kan niet ongedaan worden gemaakt.",
    deleteLinkedStrategyBody: "Alleen deze strategie wordt verwijderd. De gedeelde setup blijft beschikbaar voor je andere plannen.",
    cancel: "Annuleren",
    delete: "Verwijderen",
    loading: "Plannen laden...",
    loadError: "De plannen konden niet worden geladen. Probeer de pagina opnieuw.",
    timeframe: "Timeframe",
  },
  en: {
    eyebrow: "My Plan",
    heading: "When do you trade and how?",
    intro: "Connect your market conditions to clear execution rules. Together they form a plan you can follow consistently.",
    newPlan: "New plan",
    setupTerm: "Setup",
    setupHelp: "When am I allowed to trade?",
    strategyTerm: "Strategy",
    strategyHelp: "How do I execute the trade?",
    planTerm: "Plan",
    planHelp: "The combination that is ready for execution.",
    finnLabel: "FINN plan check",
    finishPlan: "Finish plan",
    activePlan: "Active plan",
    selectedAsset: "Asset and cadence",
    execution: "Execution",
    readyForAutomation: "Ready for Automation",
    notReady: "Not complete yet",
    editSetup: "Edit setup",
    editStrategy: "Edit strategy",
    addStrategy: "Add strategy",
    openAutomation: "Open Automation",
    plansTitle: "My plans",
    plansIntro: "Setup and strategy remain visible as two parts of the same plan.",
    allPlans: "All plans",
    plans: "plans",
    plan: "plan",
    active: "Active",
    ready: "Ready",
    concept: "Draft",
    missingStrategy: "Strategy missing",
    setupReady: "Setup ready",
    strategyReady: "Strategy ready",
    market: "market",
    macro: "macro",
    technical: "technical",
    amount: "Amount",
    entry: "Entry",
    stopLoss: "Stop loss",
    targets: "Targets",
    fixed: "Fixed amount",
    dynamic: "Dynamic sizing",
    noPlansTitle: "Create your first plan",
    noPlansBody: "Start with the conditions under which you want to trade. Then add the execution rules.",
    createSetupTitle: "Step 1 · Create setup",
    createSetupSubtitle: "When am I allowed to trade?",
    createStrategyTitle: "Step 2 · Configure strategy",
    createStrategySubtitle: "How do I execute the trade?",
    editSetupTitle: "Edit setup",
    editStrategyTitle: "Edit strategy",
    deletePlan: "Delete plan",
    deleteTitle: "Delete plan?",
    deleteBody: "The linked strategy and setup will be deleted. This cannot be undone.",
    deleteLinkedStrategyBody: "Only this strategy will be deleted. The shared setup remains available to your other plans.",
    cancel: "Cancel",
    delete: "Delete",
    loading: "Loading plans...",
    loadError: "The plans could not be loaded. Please refresh the page.",
    timeframe: "Timeframe",
  },
  de: {
    eyebrow: "Mein Plan",
    heading: "Wann handelst du und wie?",
    intro: "Verbinde deine Marktbedingungen mit klaren Ausführungsregeln. Zusammen bilden sie einen Plan, dem du konsequent folgen kannst.",
    newPlan: "Neuer Plan",
    setupTerm: "Setup",
    setupHelp: "Wann darf ich handeln?",
    strategyTerm: "Strategie",
    strategyHelp: "Wie führe ich den Trade aus?",
    planTerm: "Plan",
    planHelp: "Die Kombination, die zur Ausführung bereitsteht.",
    finnLabel: "FINN Planprüfung",
    finishPlan: "Plan vervollständigen",
    activePlan: "Aktiver Plan",
    selectedAsset: "Asset und Rhythmus",
    execution: "Ausführung",
    readyForAutomation: "Bereit für Automation",
    notReady: "Noch nicht vollständig",
    editSetup: "Setup bearbeiten",
    editStrategy: "Strategie bearbeiten",
    addStrategy: "Strategie hinzufügen",
    openAutomation: "Zu Automation",
    plansTitle: "Meine Pläne",
    plansIntro: "Setup und Strategie bleiben als zwei Teile desselben Plans sichtbar.",
    allPlans: "Alle Pläne",
    plans: "Pläne",
    plan: "Plan",
    active: "Aktiv",
    ready: "Bereit",
    concept: "Entwurf",
    missingStrategy: "Strategie fehlt",
    setupReady: "Setup bereit",
    strategyReady: "Strategie bereit",
    market: "Markt",
    macro: "Makro",
    technical: "Technik",
    amount: "Betrag",
    entry: "Einstieg",
    stopLoss: "Stop-Loss",
    targets: "Ziele",
    fixed: "Fester Betrag",
    dynamic: "Dynamische Größe",
    noPlansTitle: "Erstelle deinen ersten Plan",
    noPlansBody: "Beginne mit den Bedingungen, unter denen du handeln möchtest. Füge danach die Ausführungsregeln hinzu.",
    createSetupTitle: "Schritt 1 · Setup erstellen",
    createSetupSubtitle: "Wann darf ich handeln?",
    createStrategyTitle: "Schritt 2 · Strategie festlegen",
    createStrategySubtitle: "Wie führe ich den Trade aus?",
    editSetupTitle: "Setup bearbeiten",
    editStrategyTitle: "Strategie bearbeiten",
    deletePlan: "Plan löschen",
    deleteTitle: "Plan löschen?",
    deleteBody: "Die verknüpfte Strategie und das Setup werden gelöscht. Dies kann nicht rückgängig gemacht werden.",
    deleteLinkedStrategyBody: "Nur diese Strategie wird gelöscht. Das gemeinsame Setup bleibt für deine anderen Pläne verfügbar.",
    cancel: "Abbrechen",
    delete: "Löschen",
    loading: "Pläne werden geladen...",
    loadError: "Die Pläne konnten nicht geladen werden. Bitte lade die Seite neu.",
    timeframe: "Zeitrahmen",
  },
};

function getCopy(locale) {
  return COPY[String(locale || "nl").toLowerCase()] || COPY.nl;
}

function normalizeId(value) {
  return value == null ? "" : String(value);
}

function hasUsableStrategy(strategy) {
  return Boolean(strategy?.id && String(strategy?.name || "").trim());
}

function strategyIsComplete(setup, strategy) {
  if (!setup || !hasUsableStrategy(strategy) || Number(strategy.base_amount || strategy.amount || 0) <= 0) return false;
  if (String(setup.setup_type || "").toLowerCase() === "dca") return true;
  const targets = Array.isArray(strategy.targets) ? strategy.targets.filter(Boolean) : [];
  return strategy.entry != null && strategy.entry !== "" && strategy.stop_loss != null && strategy.stop_loss !== "" && targets.length > 0;
}

function buildPlans(setups, strategies) {
  const setupIds = new Set(setups.map((setup) => normalizeId(setup.id)));
  const linked = new Map();

  strategies.forEach((strategy) => {
    const setupId = normalizeId(strategy.setup_id ?? strategy.setup?.id);
    if (!linked.has(setupId)) linked.set(setupId, []);
    linked.get(setupId).push(strategy);
  });

  const plans = setups.flatMap((setup) => {
    const matches = linked.get(normalizeId(setup.id)) || [];
    if (!matches.length) return [{ key: `setup-${setup.id}`, setup, strategy: null }];
    return matches.map((strategy) => ({ key: `strategy-${strategy.id}`, setup, strategy }));
  });

  strategies.forEach((strategy) => {
    const setupId = normalizeId(strategy.setup_id ?? strategy.setup?.id);
    if (!setupIds.has(setupId)) {
      plans.push({ key: `orphan-${strategy.id}`, setup: strategy.setup || null, strategy });
    }
  });

  return plans.map((plan) => ({
    ...plan,
    hasStrategy: hasUsableStrategy(plan.strategy),
    complete: strategyIsComplete(plan.setup, plan.strategy),
  }));
}

function getPlanName(plan, copy) {
  return (plan.hasStrategy ? plan.strategy?.name : null) || plan.setup?.name || copy.planTerm;
}

function getFinnMessage(copy, plan, totalPlans) {
  if (!totalPlans) return copy.noPlansBody;
  if (!plan?.hasStrategy) {
    return `${getPlanName(plan, copy)}: ${copy.setupReady.toLowerCase()}, ${copy.missingStrategy.toLowerCase()}.`;
  }
  if (!plan.complete) {
    return `${getPlanName(plan, copy)}: ${copy.strategyTerm.toLowerCase()} ${copy.notReady.toLowerCase()}.`;
  }
  return `${getPlanName(plan, copy)} ${copy.readyForAutomation.toLowerCase()}.`;
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "–";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(number);
}

function PlanStatus({ plan, copy }) {
  const isActive = Boolean(plan.strategy?.is_active && plan.complete);
  const label = isActive ? copy.active : plan.complete ? copy.ready : copy.concept;
  const tone = isActive
    ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300"
    : plan.complete
      ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/50 dark:bg-blue-950/30 dark:text-blue-300"
      : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300";

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.18em] ${tone}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}

export default function MyPlanWorkflow({ symbol = "BTC" }) {
  const searchParams = useSearchParams();
  const { locale } = useTranslation();
  const copy = getCopy(locale);
  const activeSymbol = String(searchParams.get("symbol") || symbol || "BTC").toUpperCase();
  const { activeSetup } = useActiveSetup();
  const { openConfirm, showSnackbar } = useModal();
  const {
    strategies,
    setups,
    loading,
    error,
    loadStrategies,
    loadSetups,
    addStrategy,
    saveStrategy,
    removeStrategy,
  } = useStrategyData();
  const [drawer, setDrawer] = useState(null);

  const plans = useMemo(() => {
    const result = buildPlans(setups, strategies);
    const activeSetupId = normalizeId(activeSetup?.id);
    return result.sort((a, b) => {
      const aActive = Number(Boolean(a.strategy?.is_active)) + Number(normalizeId(a.setup?.id) === activeSetupId);
      const bActive = Number(Boolean(b.strategy?.is_active)) + Number(normalizeId(b.setup?.id) === activeSetupId);
      if (aActive !== bActive) return bActive - aActive;
      if (a.complete !== b.complete) return Number(b.complete) - Number(a.complete);
      return getPlanName(a, copy).localeCompare(getPlanName(b, copy));
    });
  }, [activeSetup?.id, copy, setups, strategies]);

  const activePlan = useMemo(() => {
    const setupId = normalizeId(activeSetup?.id);
    return plans.find((plan) => plan.strategy?.is_active && normalizeId(plan.setup?.id) === setupId)
      || plans.find((plan) => plan.strategy?.is_active)
      || plans.find((plan) => normalizeId(plan.setup?.id) === setupId)
      || plans[0]
      || null;
  }, [activeSetup?.id, plans]);

  const closeDrawer = () => setDrawer(null);

  const openStrategyDrawer = (setup, strategy = null, mode = "edit-strategy") => {
    setDrawer({ type: mode, setup, strategy });
  };

  const handleSetupSaved = async (savedSetup) => {
    const refreshedSetups = await loadSetups();
    if (drawer?.type === "new-setup") {
      const setup = savedSetup?.id
        ? savedSetup
        : refreshedSetups.find((item) => item.symbol === activeSymbol) || refreshedSetups.at(-1);
      if (setup) {
        openStrategyDrawer(setup, null, "new-strategy");
        return;
      }
    }
    closeDrawer();
  };

  const handleStrategySubmit = async (payload) => {
    if (drawer?.strategy?.id) {
      await saveStrategy(drawer.strategy.id, payload);
    } else {
      await addStrategy(payload);
    }
    await Promise.all([loadSetups(), loadStrategies()]);
    closeDrawer();
  };

  const handleDeletePlan = (plan) => {
    const linkedStrategyCount = strategies.filter(
      (strategy) => normalizeId(strategy.setup_id ?? strategy.setup?.id) === normalizeId(plan.setup?.id)
    ).length;
    const removesSetup = !plan.strategy || linkedStrategyCount <= 1;
    openConfirm({
      title: copy.deleteTitle,
      description: removesSetup
        ? copy.deleteBody
        : copy.deleteLinkedStrategyBody,
      tone: "danger",
      confirmText: copy.delete,
      cancelText: copy.cancel,
      onConfirm: async () => {
        if (plan.strategy?.id) await removeStrategy(plan.strategy.id);
        if (removesSetup && plan.setup?.id) await deleteSetup(plan.setup.id);
        await Promise.all([loadSetups(), loadStrategies()]);
        showSnackbar(copy.deletePlan, "success");
      },
    });
  };

  const strategySeed = drawer?.strategy || (drawer?.setup ? {
    setup_id: drawer.setup.id,
    symbol: drawer.setup.symbol,
    timeframe: drawer.setup.timeframe,
  } : null);

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-[28px] border border-slate-200/80 bg-white shadow-[0_18px_50px_-40px_rgba(15,23,42,0.3)] dark:border-slate-800 dark:bg-[#0f172a]">
        <div className="flex flex-col gap-5 border-b border-slate-100 px-5 py-5 dark:border-slate-800 lg:flex-row lg:items-end lg:justify-between lg:px-6">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">{copy.eyebrow}</div>
            <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950 dark:text-white lg:text-3xl">{copy.heading}</h2>
            <p className="mt-1 max-w-2xl text-sm font-medium leading-relaxed text-slate-500 dark:text-slate-400">{copy.intro}</p>
          </div>
          <button
            type="button"
            onClick={() => setDrawer({ type: "new-setup", setup: null, strategy: null })}
            className="inline-flex min-h-11 items-center justify-center gap-2 self-start rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-black text-white shadow-sm shadow-blue-600/20 transition hover:bg-blue-700"
          >
            <Plus size={17} />
            {copy.newPlan}
          </button>
        </div>

        <div className="grid gap-px bg-slate-100 sm:grid-cols-3 dark:bg-slate-800">
          {[
            [Layers3, copy.setupTerm, copy.setupHelp],
            [Activity, copy.strategyTerm, copy.strategyHelp],
            [ShieldCheck, copy.planTerm, copy.planHelp],
          ].map(([Icon, label, description], index) => (
            <div key={label} className="flex items-center gap-3 bg-white px-5 py-4 dark:bg-[#0f172a]">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-300">
                <Icon size={17} />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-xs font-black text-slate-950 dark:text-white">
                  <span className="text-blue-600">{index + 1}</span>
                  {label}
                </div>
                <p className="mt-0.5 text-xs font-medium text-slate-500 dark:text-slate-400">{description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-[24px] border border-blue-100 bg-[linear-gradient(110deg,#eff6ff_0%,#ffffff_58%)] p-4 dark:border-blue-950 dark:bg-[linear-gradient(110deg,#0b1b35_0%,#0f172a_58%)]">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-sm shadow-blue-600/20">
            <Sparkles size={18} />
          </div>
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600 dark:text-blue-300">{copy.finnLabel}</div>
            <p className="mt-1 text-sm font-bold leading-relaxed text-slate-800 dark:text-slate-200">
              {getFinnMessage(copy, activePlan, plans.length)}
            </p>
          </div>
        </div>
      </section>

      {loading ? (
        <div className="rounded-[24px] border border-slate-200 bg-white px-6 py-12 text-center text-sm font-bold text-slate-500 dark:border-slate-800 dark:bg-[#0f172a]">{copy.loading}</div>
      ) : error ? (
        <div className="rounded-[24px] border border-rose-200 bg-rose-50 px-6 py-5 text-sm font-bold text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-300">{copy.loadError}</div>
      ) : activePlan ? (
        <section className="overflow-hidden rounded-[28px] border border-slate-200/80 bg-white shadow-[0_18px_50px_-40px_rgba(15,23,42,0.3)] dark:border-slate-800 dark:bg-[#0f172a]">
          <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between lg:px-6">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-950 text-white dark:bg-blue-600"><WalletCards size={17} /></span>
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">{copy.activePlan}</div>
                <h3 className="mt-0.5 text-lg font-black tracking-tight text-slate-950 dark:text-white">{getPlanName(activePlan, copy)}</h3>
              </div>
            </div>
            <PlanStatus plan={activePlan} copy={copy} />
          </div>

          <div className="grid lg:grid-cols-[1fr_auto_1fr_auto_0.78fr] lg:items-stretch">
            <PlanPart
              icon={Layers3}
              eyebrow={`${copy.setupTerm} · ${copy.setupHelp}`}
              title={activePlan.setup?.name || copy.setupTerm}
              meta={`${activePlan.setup?.symbol || activeSymbol} · ${activePlan.setup?.timeframe || "–"}`}
              detail={activePlan.setup ? `${activePlan.setup.min_market_score ?? 0}–${activePlan.setup.max_market_score ?? 100} ${copy.market} · ${activePlan.setup.min_macro_score ?? 0}–${activePlan.setup.max_macro_score ?? 100} ${copy.macro} · ${activePlan.setup.min_technical_score ?? 0}–${activePlan.setup.max_technical_score ?? 100} ${copy.technical}` : copy.notReady}
              actionLabel={copy.editSetup}
              onAction={() => setDrawer({ type: "edit-setup", setup: activePlan.setup, strategy: activePlan.strategy })}
            />
            <div className="hidden items-center justify-center text-slate-300 lg:flex"><ChevronRight size={20} /></div>
            <PlanPart
              icon={Target}
              eyebrow={`${copy.strategyTerm} · ${copy.strategyHelp}`}
              title={activePlan.hasStrategy ? activePlan.strategy.name : copy.missingStrategy}
              meta={activePlan.hasStrategy ? `${copy.amount} ${formatNumber(activePlan.strategy.base_amount || activePlan.strategy.amount)} · ${activePlan.strategy.execution_mode === "fixed" ? copy.fixed : copy.dynamic}` : copy.notReady}
              detail={activePlan.hasStrategy ? getExecutionSummary(activePlan, copy) : copy.strategyHelp}
              actionLabel={activePlan.hasStrategy ? copy.editStrategy : copy.addStrategy}
              onAction={() => openStrategyDrawer(activePlan.setup, activePlan.strategy, activePlan.strategy?.id ? "edit-strategy" : "new-strategy")}
              muted={!activePlan.hasStrategy}
            />
            <div className="hidden items-center justify-center text-slate-300 lg:flex"><ChevronRight size={20} /></div>
            <div className="flex flex-col justify-between border-t border-slate-100 bg-slate-50/70 p-5 dark:border-slate-800 dark:bg-slate-900/50 lg:border-l lg:border-t-0">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">{copy.planTerm}</div>
                <div className="mt-3 flex items-center gap-2">
                  {activePlan.complete ? <CheckCircle2 size={20} className="text-emerald-500" /> : <CircleDashed size={20} className="text-amber-500" />}
                  <span className="text-sm font-black text-slate-900 dark:text-white">{activePlan.complete ? copy.readyForAutomation : copy.notReady}</span>
                </div>
              </div>
              {activePlan.complete ? (
                <Link href={`/bot?symbol=${encodeURIComponent(activePlan.setup?.symbol || activeSymbol)}`} className="mt-5 inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-blue-600 px-3 text-xs font-black text-white transition hover:bg-blue-700">
                  <Bot size={15} /> {copy.openAutomation}
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={() => openStrategyDrawer(activePlan.setup, activePlan.strategy, activePlan.strategy?.id ? "edit-strategy" : "new-strategy")}
                  className="mt-5 inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-blue-600 px-3 text-xs font-black text-white transition hover:bg-blue-700"
                >
                  <Plus size={15} /> {activePlan.hasStrategy ? copy.finishPlan : copy.addStrategy}
                </button>
              )}
            </div>
          </div>
        </section>
      ) : null}

      <section className="overflow-hidden rounded-[28px] border border-slate-200/80 bg-white shadow-[0_18px_50px_-40px_rgba(15,23,42,0.3)] dark:border-slate-800 dark:bg-[#0f172a]">
        <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-800 sm:flex-row sm:items-end sm:justify-between lg:px-6">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600 dark:text-blue-400">{copy.allPlans}</div>
            <h3 className="mt-1 text-xl font-black tracking-tight text-slate-950 dark:text-white">{copy.plansTitle}</h3>
            <p className="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">{copy.plansIntro}</p>
          </div>
          <span className="self-start rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
            {plans.length} {plans.length === 1 ? copy.plan : copy.plans}
          </span>
        </div>

        {plans.length ? (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {plans.map((plan) => (
              <PlanRow
                key={plan.key}
                plan={plan}
                copy={copy}
                onEditSetup={() => setDrawer({ type: "edit-setup", setup: plan.setup, strategy: plan.strategy })}
                onEditStrategy={() => openStrategyDrawer(plan.setup, plan.strategy, plan.strategy ? "edit-strategy" : "new-strategy")}
                onDelete={() => handleDeletePlan(plan)}
              />
            ))}
          </div>
        ) : !loading ? (
          <div className="flex flex-col items-center px-6 py-12 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-300"><Layers3 size={21} /></span>
            <h4 className="mt-4 text-base font-black text-slate-950 dark:text-white">{copy.noPlansTitle}</h4>
            <p className="mt-1 max-w-md text-sm font-medium text-slate-500 dark:text-slate-400">{copy.noPlansBody}</p>
            <button type="button" onClick={() => setDrawer({ type: "new-setup", setup: null, strategy: null })} className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-black text-white">
              <Plus size={16} /> {copy.newPlan}
            </button>
          </div>
        ) : null}
      </section>

      <Drawer
        isOpen={drawer?.type === "new-setup" || drawer?.type === "edit-setup"}
        onClose={closeDrawer}
        title={drawer?.type === "edit-setup" ? copy.editSetupTitle : copy.createSetupTitle}
        subtitle={copy.createSetupSubtitle}
        width="max-w-3xl"
      >
        <SetupForm
          mode={drawer?.type === "edit-setup" ? "edit" : "new"}
          initialData={drawer?.setup || null}
          onSaved={handleSetupSaved}
        />
      </Drawer>

      <Drawer
        isOpen={drawer?.type === "new-strategy" || drawer?.type === "edit-strategy"}
        onClose={closeDrawer}
        title={drawer?.type === "edit-strategy" ? copy.editStrategyTitle : copy.createStrategyTitle}
        subtitle={copy.createStrategySubtitle}
        width="max-w-2xl"
      >
        <StrategyForm
          key={`${drawer?.type || "closed"}-${drawer?.strategy?.id || drawer?.setup?.id || "new"}`}
          setups={setups}
          strategy={strategySeed}
          isEdit={drawer?.type === "edit-strategy"}
          onSubmit={handleStrategySubmit}
        />
      </Drawer>
    </div>
  );
}

function PlanPart({ icon: Icon, eyebrow, title, meta, detail, actionLabel, onAction, muted = false }) {
  return (
    <div className={`p-5 lg:p-6 ${muted ? "bg-amber-50/40 dark:bg-amber-950/10" : ""}`}>
      <div className="flex items-start gap-3">
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${muted ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" : "bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-300"}`}><Icon size={17} /></span>
        <div className="min-w-0">
          <div className="text-[9px] font-black uppercase tracking-[0.2em] text-slate-400">{eyebrow}</div>
          <div className="mt-1 truncate text-base font-black text-slate-950 dark:text-white">{title}</div>
          <div className="mt-1 text-xs font-bold text-slate-500 dark:text-slate-400">{meta}</div>
        </div>
      </div>
      <p className="mt-4 line-clamp-2 text-xs font-medium leading-relaxed text-slate-500 dark:text-slate-400">{detail}</p>
      <button type="button" onClick={onAction} className="mt-4 inline-flex items-center gap-2 text-xs font-black text-blue-700 transition hover:text-blue-900 dark:text-blue-300">
        <Pencil size={13} /> {actionLabel}
      </button>
    </div>
  );
}

function PlanRow({ plan, copy, onEditSetup, onEditStrategy, onDelete }) {
  return (
    <div className="grid gap-4 px-5 py-4 transition hover:bg-slate-50/70 dark:hover:bg-slate-900/40 lg:grid-cols-[1.1fr_1fr_1fr_auto] lg:items-center lg:px-6">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="truncate text-sm font-black text-slate-950 dark:text-white">{getPlanName(plan, copy)}</h4>
          <PlanStatus plan={plan} copy={copy} />
        </div>
        <p className="mt-1 text-xs font-bold text-slate-500 dark:text-slate-400">{plan.setup?.symbol || plan.strategy?.symbol || "–"} · {plan.setup?.timeframe || plan.strategy?.timeframe || "–"}</p>
      </div>

      <button type="button" onClick={onEditSetup} className="flex min-w-0 items-center gap-3 rounded-xl border border-slate-100 px-3 py-2.5 text-left transition hover:border-blue-200 hover:bg-blue-50 dark:border-slate-800 dark:hover:border-blue-900 dark:hover:bg-blue-950/20">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-300"><Layers3 size={15} /></span>
        <span className="min-w-0">
          <span className="block text-[9px] font-black uppercase tracking-[0.18em] text-slate-400">{copy.setupTerm}</span>
          <span className="block truncate text-xs font-black text-slate-800 dark:text-slate-200">{plan.setup?.name || copy.notReady}</span>
        </span>
        {plan.setup ? <Check size={14} className="ml-auto shrink-0 text-emerald-500" /> : <CircleDashed size={14} className="ml-auto shrink-0 text-amber-500" />}
      </button>

      <button type="button" onClick={onEditStrategy} className={`flex min-w-0 items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition ${plan.complete ? "border-slate-100 hover:border-blue-200 hover:bg-blue-50 dark:border-slate-800 dark:hover:border-blue-900 dark:hover:bg-blue-950/20" : "border-dashed border-amber-200 bg-amber-50/60 hover:border-amber-300 dark:border-amber-900/60 dark:bg-amber-950/10"}`}>
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${plan.complete ? "bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-300" : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"}`}><Target size={15} /></span>
        <span className="min-w-0">
          <span className="block text-[9px] font-black uppercase tracking-[0.18em] text-slate-400">{copy.strategyTerm}</span>
          <span className="block truncate text-xs font-black text-slate-800 dark:text-slate-200">{plan.hasStrategy ? plan.strategy.name : copy.addStrategy}</span>
        </span>
        {plan.complete ? <Check size={14} className="ml-auto shrink-0 text-emerald-500" /> : plan.hasStrategy ? <CircleDashed size={14} className="ml-auto shrink-0 text-amber-600" /> : <Plus size={14} className="ml-auto shrink-0 text-amber-600" />}
      </button>

      <button type="button" onClick={onDelete} aria-label={copy.deletePlan} className="inline-flex h-9 w-9 items-center justify-center justify-self-end rounded-xl text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/20">
        <Trash2 size={16} />
      </button>
    </div>
  );
}

function getExecutionSummary(plan, copy) {
  const strategy = plan.strategy;
  if (!strategy) return copy.notReady;
  if (String(plan.setup?.setup_type || "").toLowerCase() === "dca") {
    return `${copy.amount}: ${formatNumber(strategy.base_amount || strategy.amount)} · ${strategy.execution_mode === "fixed" ? copy.fixed : copy.dynamic}`;
  }
  const targets = Array.isArray(strategy.targets)
    ? strategy.targets.map((target) => typeof target === "object" ? target.price : target).filter((value) => value != null)
    : [];
  return `${copy.entry}: ${formatNumber(strategy.entry)} · ${copy.stopLoss}: ${formatNumber(strategy.stop_loss)} · ${copy.targets}: ${targets.map(formatNumber).join(", ") || "–"}`;
}
